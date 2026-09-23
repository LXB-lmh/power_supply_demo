# -*- coding: utf-8 -*-
"""按 2025 供电年报目录成文。出处只标标题后括号；缺材料或不通顺标黄标题和该句。

不编造正文占位句。没有材料就只留黄标题。网页按章写一章，CLI 全年报按 ch1～ch12 顺序拼。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from chapters.ch4.power_extract import _is_volume_change_body
from chapters.ch4.power_style import CYCLE_TABLE, MAIN_SCOPE, POWER_SCOPE
from chapters.ch4.power_write import _items
from chapters.common.drawings import copy_drawings_from_body_index, copy_formula_paragraph_from_body_index
from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts, is_chapter_or_appendix_title, outline_num
from chapters.power.extract import _ch6_intro_polluted
from chapters.common.word import (
    add_blank,
    add_caption,
    add_cover,
    add_formula_3_1,
    add_heading,
    add_para,
    add_table,
    any_needs_mark,
    is_section_title_line,
    needs_mark,
    new_report_document,
    set_assessment_year,
)
from chapters.power.style import (
    CH1_CONTENTS,
    CH3_METHOD_MISSING,
    CH3_SCORE_LEAD,
    CH3_T33_WIDTHS,
    CH3_T34_WIDTHS,
    CH3_T35_WIDTHS,
    CH3_T310_WIDTHS,
    CH3_T311_WIDTHS,
    CH3_T312_WIDTHS,
    CH7_72_SECTIONS,
    ENV_LEAD,
    ENV_LEAD_BRIDGE,
    GRADE_TABLE,
    LINES_SCOPE,
    PERIOD,
    PROJECT_LEAD,
    STOCK_LEAD,
    WORKFLOW_TABLE,
)


def _overview_paras(text: str) -> list[str]:
    """把 3.3.2 总述拆成「供电完成 / 主变电完成 / 能源系统完成」几段，对上 2025 分段。"""
    rest = (text or "").strip()
    if not rest:
        return []
    parts: list[str] = []
    for mark in ("供电完成", "主变电完成", "能源系统完成"):
        idx = rest.find(mark)
        if idx > 0:
            parts.append(rest[:idx].strip())
            rest = rest[idx:]
    if rest.strip():
        parts.append(rest.strip())
    return parts


def _compare_vmerge(rows: list[list[str]]) -> list[tuple[int, int, int]]:
    """3.5 两年对比：同一线路+区段的两行合并线路/区段列，对应 2025 年报表样式。"""
    out: list[tuple[int, int, int]] = []
    i = 1
    while i + 1 < len(rows):
        a, b = rows[i], rows[i + 1]
        if len(a) > 1 and len(b) > 1 and a[0] == b[0] and a[1] == b[1]:
            out.append((0, i, i + 1))
            out.append((1, i, i + 1))
            i += 2
        else:
            i += 1
    return out


def _draw(doc, item: dict[str, Any]) -> None:
    copy_drawings_from_body_index(item.get("source_path") or "", int(item.get("source_index") or -1), doc)


def _formula(doc, item: dict[str, Any]) -> bool:
    """源稿公式整段回拷；失败时若有可见文字则退成普通段。"""
    ok = copy_formula_paragraph_from_body_index(
        item.get("source_path") or "",
        int(item.get("source_index") or -1),
        doc,
    )
    if ok:
        return True
    text = str(item.get("text") or "").strip()
    if text:
        add_para(doc, text, source_yellow=bool(item.get("source_yellow")))
        return True
    return False


def _is_caption(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) >= 80:
        return False
    if t[0] not in {"图", "表"}:
        return False
    return t[1].isdigit() or t[1] in " -"


def _plain_texts(items: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for item in items or []:
        if item.get("kind") in {"drawing", "table", "formula", "formula_3_1"}:
            continue
        text = str(item.get("text") or "").strip()
        if text:
            out.append(text)
    return out


def _is_seg_heading(text: str) -> bool:
    """管控措施里的区段行，如「南延伸：」。设备中类「应急电源设备：…」不算标题。"""
    t = (text or "").strip()
    if not t.endswith("：") or len(t) > 24:
        return False
    if "设备" in t or "系统" in t:
        return False
    return True


def _should_skip_leaked_title(text: str, *, keep_chapter: int | None = None) -> bool:
    """成文时丢掉误吸的其它章标题行；同章 x.y 小节标题仍可写。"""
    compact = compact_text(text)
    if is_chapter_or_appendix_title(compact):
        return True
    num = outline_num(compact)
    if keep_chapter and num and is_section_title_line(text):
        try:
            top = int(num.split(".", 1)[0])
        except ValueError:
            return False
        return top != keep_chapter
    return False


def _write_paras(doc, texts: list[str] | None, *, keep_chapter: int | None = None) -> None:
    """只黄出错的那一分句；该区段标题一并黄。不改原文。"""
    items = [
        str(t).strip()
        for t in dedupe_texts(texts)
        if str(t).strip() and not _should_skip_leaked_title(str(t), keep_chapter=keep_chapter)
    ]
    i = 0
    while i < len(items):
        text = items[i]
        if _is_caption(text):
            add_caption(doc, text)
            i += 1
            continue
        if _is_seg_heading(text):
            j = i + 1
            while j < len(items) and not _is_seg_heading(items[j]) and not _is_caption(items[j]):
                j += 1
            kids = items[i + 1 : j]
            add_para(doc, text, yellow=any_needs_mark(kids))
            i += 1
            continue
        if is_section_title_line(text):
            add_heading(doc, text, 3, yellow=False)
            i += 1
            continue
        add_para(doc, text)
        i += 1


def _flow_table_vmerge(item: dict[str, Any]) -> list[tuple[int, int, int]] | None:
    """材料带了 vmerge 就原样用（含空列表=无合并）；没有字段再走推断。"""
    if "vmerge" not in item:
        return None
    raw = item.get("vmerge") or []
    out: list[tuple[int, int, int]] = []
    for m in raw:
        if isinstance(m, (list, tuple)) and len(m) >= 3:
            out.append((int(m[0]), int(m[1]), int(m[2])))
    return out


def _write_flow(doc, items: list[dict[str, Any]] | None, *, keep_chapter: int | None = None) -> bool:
    """按材料原顺序写图/表/段/公式。图与公式按 source_index 回原文件拷贝。

    成文前做通用去重，避免各章多份材料叠写出两遍正文。
    表格竖合并跟材料：有解析出的 vmerge 就还原，格式与源表一致（全章通用）。
    """
    items = dedupe_flow_items(items)
    if not items:
        return False
    wrote_formula = False
    for item in items:
        kind = item.get("kind")
        if kind == "formula":
            if _formula(doc, item):
                wrote_formula = True
            continue
        if kind == "formula_3_1":
            add_formula_3_1(doc)
            wrote_formula = True
            continue
        if kind == "drawing":
            _draw(doc, item)
            continue
        if kind == "table":
            from chapters.common.table_copy import write_table_item

            if not write_table_item(doc, item):
                add_table(doc, item.get("rows") or [], vmerge=_flow_table_vmerge(item))
            continue
        text = str(item.get("text") or "").strip()
        if not text or _should_skip_leaked_title(text, keep_chapter=keep_chapter):
            continue
        if _is_caption(text):
            add_caption(doc, text)
        elif is_section_title_line(text):
            add_heading(doc, text, 3, yellow=False)
        elif "综合评估表达式" in text:
            add_para(doc, text, source_yellow=bool(item.get("source_yellow")))
            # 仅有导语、没有可回拷公式时，补体例公式（3-1）。
            if not wrote_formula and not any(x.get("kind") in {"formula", "formula_3_1"} for x in items):
                add_formula_3_1(doc)
                wrote_formula = True
        else:
            add_para(doc, text, source_yellow=bool(item.get("source_yellow")))
    return True


def _row_sig(rows: list[list[str]] | None) -> tuple:
    return tuple(tuple(str(c) for c in (r or [])) for r in (rows or [])[:5])


def _is_same_table(item: dict[str, Any], rows: list[list[str]] | None) -> bool:
    return item.get("kind") == "table" and bool(rows) and _row_sig(item.get("rows")) == _row_sig(rows)


def _write_captioned_flow(
    doc,
    flow: list[dict[str, Any]] | None,
    table: list[list[str]] | None,
    caption: str = "",
    *,
    vmerge: list[list[int]] | list[tuple[int, int, int]] | None = None,
) -> bool:
    """flow 里若已有同一张表，表题插在该表前，避免表 7-1 / 9-1 出现两次。

    vmerge：优先用 flow 表项自带的材料合并；否则用调用方传入的 pack 级合并。
    """
    items = list(flow or [])
    if not items and not table:
        return False
    placed = False
    pack_vmerge = None if vmerge is None else {"vmerge": vmerge}

    def _merges_for(item: dict[str, Any] | None) -> list[tuple[int, int, int]] | None:
        if item and "vmerge" in item:
            return _flow_table_vmerge(item)
        if pack_vmerge is not None:
            return _flow_table_vmerge(pack_vmerge)
        return None

    for item in items:
        if table and _is_same_table(item, table):
            if caption:
                add_caption(doc, caption)
            add_table(doc, table, vmerge=_merges_for(item))
            placed = True
            continue
        _write_flow(doc, [item])
    if table and not placed:
        if caption:
            add_caption(doc, caption)
        add_table(doc, table, vmerge=_merges_for(None))
    return True


def write_ch1(doc, pack: dict[str, Any]) -> None:
    """第 1 章：项目内容/设备范围沿用 2025 体例；1.2 运营概况才用各线报告。缺某线则黄该线标题。"""
    year = pack.get("year") or 2026
    add_heading(doc, "1  项目概述", 1)
    add_heading(doc, "1.1  项目内容", 2)
    add_para(doc, PROJECT_LEAD.format(year=year))
    add_heading(doc, "评估对象", 3)
    add_para(doc, LINES_SCOPE)
    add_para(doc, "（2）供电（含能源系统）系统运营设备范围包括：")
    add_para(doc, POWER_SCOPE)
    add_para(doc, "（3）主变电系统运营设备范围包括：")
    add_para(doc, MAIN_SCOPE)
    add_heading(doc, "评估的内容", 3)
    for title, body in CH1_CONTENTS:
        add_heading(doc, title, 4)
        add_para(doc, body)
    overviews = (pack.get("ch1") or {}).get("overviews") or []
    src_1_2 = "各线路2026年变电专业评估报告" if overviews else ""
    add_heading(doc, "1.2  运营概况", 2, src_1_2, yellow=not overviews)
    if overviews:
        have = {x.get("line") for x in overviews}
        for i in range(1, 19):
            line = f"{i}号线"
            item = next((x for x in overviews if x.get("line") == line), None)
            flow = (item or {}).get("flow")
            paras = (item or {}).get("paras") or []
            texts = _plain_texts(flow) or [str(t).strip() for t in paras if str(t).strip()]
            add_heading(
                doc,
                f"{line}线路概述",
                3,
                (item or {}).get("source") or "",
                yellow=line not in have or any_needs_mark(texts),
            )
            if not _write_flow(doc, flow):
                _write_paras(doc, paras)
    add_heading(doc, "1.3  涵盖时间", 2)
    add_para(doc, "评估涵盖时间")
    for line in PERIOD:
        add_para(doc, line)


def write_ch2(doc, pack: dict[str, Any]) -> None:
    """第 2 章：依据/流程/评级表用体例；2.4 有技术路线材料就填，没有再黄。"""
    add_heading(doc, "2  评估依据、方法与流程", 1)
    add_heading(doc, "2.1  评估依据", 2)
    add_para(doc, "国际标准")
    add_para(doc, "EN 50126-1-2017  《轨道交通 可靠性、可用性、可维修性和安全性规范与示例》")
    add_para(doc, "EN 50125-1  《铁路应用－设备的环境条件》")
    add_para(doc, "国家标准")
    add_para(doc, "GB / T 30012-2013  《城市轨道交通运营管理规范》")
    add_para(doc, "GB / T 30013-2013  《城市轨道交通试运营基本条件》")
    add_para(doc, "评估还依据 T/SHJX 089.7-2025《上海城市轨道交通设施设备运营评估规范 第7部分：供电（含能源系统）》。")
    add_heading(doc, "2.2  评估工作流程", 2)
    add_para(doc, "上海轨道交通供电系统设备年度评估工作流程描述如表2-1。")
    add_caption(doc, "表2-1 年度评估工作流程描述")
    add_table(doc, WORKFLOW_TABLE)
    add_heading(doc, "2.3  评估规范", 2)
    add_para(doc, "直接或间接表征供电专业设备状态对运行的满足程度。设备状态分为A、B、C、D四类设备进行描述。")
    add_table(doc, GRADE_TABLE)
    _write_optional_section(doc, "2.4  评估技术路线", 2, (pack.get("ch2") or {}).get("tech_route"))


def _section_ok(sec: dict[str, Any] | None) -> bool:
    """小节有正文/表/图才算有材料。"""
    sec = sec or {}
    if any(str(t).strip() for t in (sec.get("paras") or [])):
        return True
    for item in sec.get("flow") or []:
        if item.get("kind") in {"table", "drawing", "formula", "formula_3_1"}:
            return True
        if str(item.get("text") or "").strip():
            return True
    return False


def _chapter_from_title(title: str) -> int | None:
    t = (title or "").strip()
    digits: list[str] = []
    for ch in t:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    if not digits:
        return None
    return int("".join(digits))


def _write_optional_section(doc, title: str, level: int, sec: dict[str, Any] | None) -> None:
    """有材料则填入并标出处；没有则黄标题留空。禁止写死永远黄。"""
    sec = sec or {}
    ok = _section_ok(sec)
    add_heading(doc, title, level, (sec.get("source") or "") if ok else "", yellow=not ok)
    if not ok:
        return
    keep = _chapter_from_title(title)
    if not _write_flow(doc, sec.get("flow"), keep_chapter=keep):
        _write_paras(doc, sec.get("paras"), keep_chapter=keep)


def _write_summary_hole(doc, title: str, level: int = 2) -> None:
    """各章「评估小结」：一律黄标题留空，不填材料、不算已有数据。"""
    add_heading(doc, title, level, yellow=True)


def _write_ch3_named(doc, title: str, level: int, section: dict[str, Any] | None) -> None:
    """有材料则原样填入并标出处；没有则黄标题 + 不能复用说明。"""
    sec = section or {}
    if _section_ok(sec):
        add_heading(doc, title, level, sec.get("source") or "")
        if not _write_flow(doc, sec.get("flow")):
            _write_paras(doc, sec.get("paras"))
        return
    add_heading(doc, title, level, CH3_METHOD_MISSING, yellow=True)


def write_ch3(doc, pack: dict[str, Any]) -> None:
    """第 3 章：3.1/3.2/3.3.1 按名字摘录或复用去年；3.3.2 总表（无接触网列）；3.4 管控措施；3.5 用 prior 快照对比。"""
    ch = pack.get("ch3") or {}
    add_heading(doc, "3  设备功能有效性评估", 1)
    _write_ch3_named(doc, "3.1  评估方法和内容", 2, ch.get("method"))
    _write_ch3_named(doc, "3.2  评估标准", 2, ch.get("standard"))
    add_heading(doc, "3.3  供电子系统评估", 2)
    _write_ch3_named(doc, "3.3.1  供电子系统设备评估范围", 3, ch.get("scope"))
    src = ch.get("source") or ""
    power_t, main_t, energy_t = ch.get("power_table") or [], ch.get("main_table") or [], ch.get("energy_table") or []
    has = bool(power_t or main_t or energy_t)
    # 3.3.2 出处只标总表文件名；没有三张表则黄标题，不写「材料未提供」。
    add_heading(doc, "3.3.2  各线路供电子系统状态分布", 3, src, yellow=not has)
    if has:
        add_heading(doc, "各系统评分情况", 4)
        add_para(doc, CH3_SCORE_LEAD)
        for para in _overview_paras(ch.get("overview") or ""):
            add_para(doc, para)
        if power_t:
            add_caption(doc, "表3-3 供电各类设备评估结果表")
            add_table(doc, power_t, widths=CH3_T33_WIDTHS[: len(power_t[0])], jc=None, font_pt=11)
            add_blank(doc)
        if main_t:
            add_caption(doc, "表3-4 主变电所系统各类设备评估结果表")
            add_table(doc, main_t, widths=CH3_T34_WIDTHS[: len(main_t[0])], jc=None, font_pt=11)
            add_blank(doc)
        if energy_t:
            add_caption(doc, "表3-5 能源系统各类设备评估结果表")
            add_table(doc, energy_t, widths=CH3_T35_WIDTHS[: len(energy_t[0])], jc=None, font_pt=12)
    ctrl = ch.get("controls") or {}
    prose = ctrl.get("prose") or []
    add_heading(doc, "3.4  各线路管控措施", 2, ctrl.get("source") or "", yellow=not prose)
    have = {item.get("line") for item in prose}
    for i in range(1, 19):
        line = f"{i}号线"
        item = next((x for x in prose if x.get("line") == line), None)
        paras = [p.strip() for block in (item or {}).get("blocks") or [] for p in str(block).split("\n") if p.strip()]
        add_heading(doc, f"轨道交通{line}", 3, yellow=line not in have or any_needs_mark(paras))
        if not item:
            continue
        _write_paras(doc, paras)
    cmp_ok = bool(ch.get("compare_power"))
    # 3.5 标题括号同时标 2025 年报与当年总表；没有 compare_power（缺快照或缺当年表）则整节黄标题。
    add_heading(
        doc,
        "3.5  最近两年评估对比结果",
        2,
        "、".join(x for x in [ch.get("prior_source"), src] if x),
        yellow=not cmp_ok,
    )
    if cmp_ok:
        add_caption(doc, "表3-10 供电各中类设备评估结果表")
        add_table(
            doc,
            ch["compare_power"],
            widths=CH3_T310_WIDTHS[: len(ch["compare_power"][0])],
            jc="center",
            font_pt=11,
            vmerge=_compare_vmerge(ch["compare_power"]),
        )
        add_blank(doc)
        if ch.get("compare_main"):
            add_caption(doc, "表3-11 主变电所系统各中类设备评估结果表")
            add_table(
                doc,
                ch["compare_main"],
                widths=CH3_T311_WIDTHS[: len(ch["compare_main"][0])],
                jc="center",
                font_pt=11,
                vmerge=_compare_vmerge(ch["compare_main"]),
            )
            add_blank(doc)
        if ch.get("compare_energy"):
            add_caption(doc, "表3-12 能源系统各中类设备评估结果表")
            add_table(
                doc,
                ch["compare_energy"],
                widths=CH3_T312_WIDTHS[: len(ch["compare_energy"][0])],
                jc="center",
                font_pt=12,
                vmerge=_compare_vmerge(ch["compare_energy"]),
            )
        moves = ch.get("migrations") or []
        if moves:
            add_para(doc, "与上一年度的评估结果对比，个别区段的系统有劣化情况，具体是：", indent=False)
            for item in moves:
                add_para(doc, item + "。", indent=False)
    _write_summary_hole(doc, "3.6  评估小结")


def write_ch4(doc, pack: dict[str, Any]) -> None:
    """第 4 章（全年报内嵌）。4.1.1 材料→去年→黄；4.1.2 总表+变化段；4.5 小结固定黄空。"""
    ch = pack.get("ch4") or {}
    set_assessment_year(pack.get("year") or ch.get("year") or 2026)
    add_heading(doc, "4  运营契合满足度评估", 1)
    add_heading(doc, "4.1  设备体量和变化情况", 2)
    scope_ok = bool(ch.get("scope_paras") or ch.get("scope_flow"))
    add_heading(doc, "4.1.1  设备体量", 3, ch.get("scope_source") or "", yellow=not scope_ok)
    if scope_ok:
        if not _write_flow(doc, ch.get("scope_flow")):
            _write_paras(doc, ch.get("scope_paras"))
    volume = ch.get("volume_text") or ""
    plan = ch.get("plan_text") or ""
    changes = [
        str(x).strip()
        for x in (ch.get("volume_change_paras") or [])
        if _is_volume_change_body(str(x))
    ]
    has_412 = bool(volume or changes)
    add_heading(
        doc,
        "4.1.2  设备体量变化情况",
        3,
        ch.get("grade_source") or "",
        yellow=not has_412 or needs_mark(volume) or any_needs_mark(changes + ([plan] if plan else [])),
    )
    if volume:
        add_para(doc, volume)
    for para in changes:
        add_para(doc, para)
    if plan:
        add_para(doc, plan)
    # 目录固定对照去年：不跳节；4.2 周期表可复用去年/体例
    add_heading(doc, "4.2  设备维护周期和维护内容", 2, ch.get("cycle_source") or "")
    add_para(doc, "设备维护周期和维护内容如下：")
    add_table(doc, ch.get("cycle_rows") or CYCLE_TABLE)
    by_line = ch.get("fault_by_line") or {}
    fault_src = ch.get("fault_source") or ""
    add_heading(doc, "4.3  各个线路基本情况", 2, fault_src, yellow=not (fault_src or by_line))
    if fault_src or by_line:
        for i in range(1, 19):
            line = f"{i}号线"
            items = _items(by_line.get(line))
            texts = [str(x.get("text") or "").strip() for x in items if x.get("kind") == "text" and str(x.get("text") or "").strip()]
            add_heading(doc, line, 3, yellow=not items or any_needs_mark(texts))
            for item in items:
                if item.get("kind") == "formula":
                    _formula(doc, item)
                    continue
                if item.get("kind") == "drawing":
                    _draw(doc, item)
                    continue
                if item.get("kind") == "table":
                    add_table(doc, item.get("rows") or [])
                    continue
                text = str(item.get("text") or "").strip()
                if text:
                    add_para(doc, text)
    mtbf_flow = ch.get("mtbf_flow") or []
    mtbf_ok = bool(mtbf_flow or ch.get("mtbf_paras") or ch.get("mtbf_table"))
    add_heading(doc, "4.4  各线路供电系统年度生产指标", 2, ch.get("mtbf_source") or "", yellow=not mtbf_ok)
    if mtbf_ok:
        if not _write_flow(doc, mtbf_flow):
            _write_paras(doc, ch.get("mtbf_paras"))
            if ch.get("mtbf_table"):
                add_table(doc, ch.get("mtbf_table"))
    _write_summary_hole(doc, "4.5  评估小结")


def write_ch5(doc, pack: dict[str, Any]) -> None:
    """第 5 章：按历年目录 5.1～5.6 填合规性材料。5.1/5.2 可复用去年；5.7 小结固定黄空。"""
    ch = pack.get("ch5") or {}
    src = ch.get("source") or ""
    add_heading(doc, "5  管理体系合规性评估", 1, src, yellow=not src)
    special = ch.get("special") or []
    src51 = ch.get("special_source") or (src if (special or ch.get("special_flow")) else "")
    add_heading(
        doc,
        "5.1  特种设备、消防、防雷规程",
        2,
        src51,
        yellow=not (special or ch.get("special_flow")) or any_needs_mark(special or _plain_texts(ch.get("special_flow"))),
    )
    if not _write_flow(doc, ch.get("special_flow"), keep_chapter=5):
        _write_paras(doc, special, keep_chapter=5)
    inspect = ch.get("inspect") or []
    src52 = ch.get("inspect_source") or (src if (inspect or ch.get("inspect_flow")) else "")
    add_heading(
        doc,
        "5.2  强制年检或评估情况分析",
        2,
        src52,
        yellow=not (inspect or ch.get("inspect_flow")) or any_needs_mark(inspect or _plain_texts(ch.get("inspect_flow"))),
    )
    if not _write_flow(doc, ch.get("inspect_flow"), keep_chapter=5):
        _write_paras(doc, inspect, keep_chapter=5)
    law = ch.get("law") or []
    add_heading(
        doc,
        "5.3  法律法规的获取情况",
        2,
        src,
        yellow=not (law or ch.get("law_flow")) or any_needs_mark(law or _plain_texts(ch.get("law_flow"))),
    )
    if not _write_flow(doc, ch.get("law_flow"), keep_chapter=5):
        _write_paras(doc, law, keep_chapter=5)
    std_ok = bool(ch.get("std_table") or ch.get("std_paras") or ch.get("std_flow"))
    add_heading(
        doc,
        "5.4  企业标准和制度",
        2,
        src,
        yellow=not std_ok or any_needs_mark(ch.get("std_paras") or _plain_texts(ch.get("std_flow"))),
    )
    if not _write_flow(doc, ch.get("std_flow"), keep_chapter=5):
        _write_paras(doc, ch.get("std_paras") or [], keep_chapter=5)
        if ch.get("std_table"):
            add_table(doc, ch["std_table"])
    exec_paras = ch.get("exec") or []
    add_heading(
        doc,
        "5.5  制度、标准执行情况检查",
        2,
        src,
        yellow=not (exec_paras or ch.get("exec_flow")) or any_needs_mark(exec_paras or _plain_texts(ch.get("exec_flow"))),
    )
    if not _write_flow(doc, ch.get("exec_flow"), keep_chapter=5):
        _write_paras(doc, exec_paras, keep_chapter=5)
    eval_paras = ch.get("eval") or []
    add_heading(
        doc,
        "5.6  合规性评价",
        2,
        src,
        yellow=not (eval_paras or ch.get("eval_flow")) or any_needs_mark(eval_paras or _plain_texts(ch.get("eval_flow"))),
    )
    if not _write_flow(doc, ch.get("eval_flow"), keep_chapter=5):
        _write_paras(doc, eval_paras, keep_chapter=5)
    _write_summary_hole(doc, "5.7  评估小结")


def write_ch6(doc, pack: dict[str, Any]) -> None:
    """第 6 章：对照去年目录骨架成文。

    6 修程修制匹配性评估（短导语）
    6.1 对上一年度合规性评估建议的整改（有表/段则填）
    6.2 企业标准和制度（表6-1；无数则黄）
    6.3 评估小结（全册统一：固定黄空）
    """
    ch = pack.get("ch6") or {}
    src = ch.get("source") or ""
    has = bool(ch.get("revise") or ch.get("tables") or ch.get("count_table") or ch.get("intro") or ch.get("revise_flow"))
    # 大标题出处跟导语走（去年回填则标去年报告名；今年材料则标该份材料）
    intro_src = ""
    if ch.get("intro") or ch.get("intro_flow"):
        intro_src = (ch.get("intro_source") or "").strip() or (src if ch.get("intro_via") == "year" else "")
    add_heading(doc, "6  修程修制匹配性评估", 1, intro_src or src, yellow=not has)
    intro_flow = ch.get("intro_flow") or []
    # 成文再挡一道：导语串台内容不写
    if intro_flow and not _ch6_intro_polluted(intro_flow, ch.get("intro")):
        if not _write_flow(doc, intro_flow, keep_chapter=6):
            for t in ch.get("intro") or []:
                if not _should_skip_leaked_title(t, keep_chapter=6):
                    add_para(doc, t)
    revise = ch.get("revise") or []
    revise_ok = bool(revise or ch.get("tables") or ch.get("revise_flow"))
    add_heading(
        doc,
        "6.1  对上一年度合规性评估建议的整改",
        2,
        src if revise_ok else "",
        yellow=not revise_ok or bool(ch.get("incomplete")) or any_needs_mark(revise or _plain_texts(ch.get("revise_flow"))),
    )
    if not _write_flow(doc, ch.get("revise_flow"), keep_chapter=6):
        _write_paras(doc, revise, keep_chapter=6)
        for table in ch.get("tables") or []:
            add_table(doc, table)
    add_heading(doc, "6.2  企业标准和制度", 2, src if ch.get("count_table") else "", yellow=not ch.get("count_table"))
    if ch.get("count_table"):
        add_para(doc, "供电分公司制定对应的操作规程或作业指导书，具体数量如表6-1：")
        add_caption(doc, "表6-1 规程分类、等级和变化情况")
        add_table(doc, ch["count_table"])
    _write_summary_hole(doc, "6.3  评估小结")


def write_ch7(doc, pack: dict[str, Any]) -> None:
    """第 7 章：固定骨架成文（可逐年复用）。

    7.1 生产组织模式：今年 → 去年/保底 → 黄
    7.2 设施设备运维质量分析
        开篇句：今年总述 → 去年/保底
        7.2.1 日常维修计划执行情况 + 表7-1（表只来自当年材料，无表黄；不堆各线散文）
        7.2.2～7.2.4：按 7.2.x.n 轨道交通N号线填空；无材料该线黄空
    7.3 评估小结（黄空）
    """
    ch = pack.get("ch7") or {}
    org_flow = [x for x in (ch.get("org_flow") or []) if isinstance(x, dict) and x.get("kind") in {"para", "table"}]
    org_paras = [str(t).strip() for t in (ch.get("org_paras") or []) if str(t).strip()]
    org_ok = bool(org_flow or org_paras)
    org_src = (ch.get("org_source") or "").strip() if org_ok else ""

    lead_flow = [x for x in (ch.get("lead_flow") or []) if isinstance(x, dict) and x.get("kind") == "para"]
    lead_paras = [str(t).strip() for t in (ch.get("lead_paras") or []) if str(t).strip()]
    lead_ok = bool(lead_flow or lead_paras)
    lead_src = (ch.get("lead_source") or "").strip() if lead_ok else ""

    plan_flow = [x for x in (ch.get("flow") or []) if isinstance(x, dict) and x.get("kind") in {"para", "table"}]
    has_plan_table = bool(ch.get("table"))
    plan_src = (ch.get("source") or "").strip() if has_plan_table else ""
    aspects = ch.get("aspects") or {}

    chapter_src = plan_src or org_src or lead_src
    add_heading(doc, "7  运维表现健康度评估", 1, chapter_src)
    add_heading(doc, "7.1  生产组织模式", 2, org_src, yellow=not org_ok)
    if org_ok:
        if not _write_flow(doc, org_flow, keep_chapter=7):
            for t in org_paras:
                if not _should_skip_leaked_title(t, keep_chapter=7):
                    add_para(doc, t)

    any_72 = lead_ok or has_plan_table or any(
        (aspects.get(spec["id"]) or {}).get("paras")
        or (aspects.get(spec["id"]) or {}).get("flow")
        or any(not (ln.get("empty")) for ln in ((aspects.get(spec["id"]) or {}).get("lines") or []))
        for spec in CH7_72_SECTIONS
    )
    add_heading(doc, "7.2  设施设备运维质量分析", 2, lead_src or plan_src, yellow=not any_72)
    if lead_ok:
        if not _write_flow(doc, lead_flow, keep_chapter=7):
            for t in lead_paras:
                add_para(doc, t)

    for spec in CH7_72_SECTIONS:
        aid = spec["id"]
        title = spec["title"]
        aspect = aspects.get(aid) or {}
        a_paras = [str(t).strip() for t in (aspect.get("paras") or []) if str(t).strip()]
        a_flow = [x for x in (aspect.get("flow") or []) if isinstance(x, dict) and x.get("kind") in {"para", "table"}]
        a_src = (aspect.get("source") or "").strip()
        line_secs = list(aspect.get("lines") or [])

        if aid == "plan":
            add_heading(doc, title, 3, plan_src or (a_src if a_paras or a_flow else ""), yellow=not has_plan_table)
            if a_paras or a_flow:
                if not _write_flow(doc, a_flow, keep_chapter=7):
                    for t in a_paras:
                        if not _should_skip_leaked_title(t, keep_chapter=7):
                            add_para(doc, t)
            if has_plan_table:
                _write_captioned_flow(doc, plan_flow, ch.get("table"), "表7-1生产计划执行情况表")
            continue

        # 7.2.2～7.2.4：有按线路块则写 7.2.x.n；否则整节黄空（不拿别处顶）
        has_line_body = any(not sec.get("empty") and (sec.get("flow") or sec.get("paras")) for sec in line_secs)
        ok = has_line_body or bool(a_paras or a_flow)
        add_heading(doc, title, 3, a_src if ok else "", yellow=not ok)
        if line_secs:
            # 小节号：7.2.2 → 第四级 7.2.2.n
            parent_num = title.split()[0] if title else "7.2"
            for sec in line_secs:
                line_no = int(sec.get("line_no") or 0)
                if not line_no:
                    continue
                empty = bool(sec.get("empty")) or not (sec.get("flow") or sec.get("paras"))
                heading = f"{parent_num}.{line_no}  轨道交通{line_no}号线"
                add_heading(
                    doc,
                    heading,
                    4,
                    (sec.get("source") or "") if not empty else "",
                    yellow=empty,
                )
                if empty:
                    continue
                flow = [x for x in (sec.get("flow") or []) if isinstance(x, dict) and x.get("kind") in {"para", "table"}]
                if not _write_flow(doc, flow, keep_chapter=7):
                    for t in sec.get("paras") or []:
                        if str(t).strip() and not _should_skip_leaked_title(str(t), keep_chapter=7):
                            add_para(doc, str(t).strip())
            continue
        if ok:
            if not _write_flow(doc, a_flow, keep_chapter=7):
                for t in a_paras:
                    if not _should_skip_leaked_title(t, keep_chapter=7):
                        add_para(doc, t)

    _write_summary_hole(doc, "7.3  评估小结")


def write_ch8(doc, pack: dict[str, Any]) -> None:
    """第 8 章：骨架来自去年报告检测；各小节只填当年材料；小结黄空。

    不另造「动态治理」等去年目录没有的标题。风险数据库表头随材料（25/26 皆可）。
    """
    from chapters.common.outline_detect import outline_heading_text

    ch = pack.get("ch8") or {}
    nodes = list(ch.get("outline") or [])
    if not nodes:
        from chapters.power.style import CH8_OUTLINE_FALLBACK

        nodes = [dict(x) for x in CH8_OUTLINE_FALLBACK]
        for n in nodes:
            n["role"] = n.get("role") or (
                "summary"
                if "小结" in (n.get("title") or "")
                else "risk_db"
                if "风险数据库" in (n.get("title") or "")
                else "handbook"
                if "手册" in (n.get("title") or "")
                else "faults"
                if "典型故障" in (n.get("title") or "")
                else "events"
                if "突出事件" in (n.get("title") or "")
                else "body"
            )

    slots = ch.get("slots") or {}
    risk = slots.get("risk_db") or {
        "table": ch.get("risk_table") or [],
        "flow": [{"kind": "table", "rows": ch.get("risk_table")}] if ch.get("risk_table") else [],
        "source": ch.get("risk_source") or "",
    }
    handbook = slots.get("handbook") or {
        "table": ch.get("handbook") or [],
        "flow": [{"kind": "table", "rows": ch.get("handbook")}] if ch.get("handbook") else [],
        "source": ch.get("handbook_source") or "",
    }
    faults = slots.get("faults") or {
        "paras": ch.get("fault_paras") or [],
        "flow": ch.get("fault_flow") or [],
        "source": ch.get("fault_source") or "",
    }

    def _slot_ok(role: str) -> bool:
        if role == "risk_db":
            return bool(risk.get("table"))
        if role == "handbook":
            return bool(handbook.get("table"))
        if role == "faults":
            return bool(faults.get("paras") or faults.get("flow"))
        if role == "summary":
            return False
        if role == "events":
            return bool(risk.get("table") or handbook.get("table") or faults.get("paras") or faults.get("flow"))
        return False

    def _slot_src(role: str) -> str:
        if role == "risk_db":
            return (risk.get("source") or "").strip()
        if role == "handbook":
            return (handbook.get("source") or "").strip()
        if role == "faults":
            return (faults.get("source") or "").strip()
        return ""

    for node in nodes:
        role = node.get("role") or _ch8_role_from_title(node.get("title") or "")
        num = str(node.get("num") or "")
        title = outline_heading_text(node)
        level = int(node.get("level") or (1 + int(node.get("depth") or 0)))
        if role == "summary" or num.endswith(".2") and "小结" in (node.get("title") or ""):
            _write_summary_hole(doc, title, level=level)
            continue
        ok = _slot_ok(role)
        src = _slot_src(role) if ok else ""
        # 章/8.1 级：任一子节有料则不黄
        if role in {"", "body"} and not num.count("."):
            ok = any(_slot_ok(r) for r in ("risk_db", "handbook", "faults", "events"))
            src = "、".join(x for x in (_slot_src("risk_db"), _slot_src("handbook"), _slot_src("faults")) if x)
        elif role == "events":
            ok = _slot_ok("events")
            src = "、".join(x for x in (_slot_src("risk_db"), _slot_src("handbook"), _slot_src("faults")) if x)
        add_heading(doc, title, level, src, yellow=not ok)
        if role == "risk_db" and risk.get("table"):
            add_table(doc, risk["table"])
        elif role == "handbook" and handbook.get("table"):
            add_table(doc, handbook["table"])
        elif role == "faults":
            flow = [x for x in (faults.get("flow") or []) if isinstance(x, dict) and x.get("kind") in {"para", "table", "drawing"}]
            if not _write_flow(doc, flow, keep_chapter=8):
                for t in faults.get("paras") or []:
                    if str(t).strip() and not _should_skip_leaked_title(str(t), keep_chapter=8):
                        add_para(doc, str(t).strip())


def _ch8_role_from_title(title: str) -> str:
    t = compact_text(title or "")
    if "评估小结" in t:
        return "summary"
    if "风险数据库" in t:
        return "risk_db"
    if "手册" in t:
        return "handbook"
    if "典型故障" in t:
        return "faults"
    if "突出事件" in t:
        return "events"
    return "body"


def write_ch9(doc, pack: dict[str, Any]) -> None:
    """第 9 章：9.1 安全库存；9.2/9.3 有材料就填，没有再黄。"""
    ch = pack.get("ch9") or {}
    src = ch.get("source") or ""
    add_heading(doc, "9  备件物资保障度评估", 1)
    add_heading(doc, "9.1  安全库存", 2, src, yellow=not (ch.get("table") or ch.get("flow")))
    add_para(doc, STOCK_LEAD)
    if ch.get("table"):
        add_para(doc, "如表9-1是安全库存的部分表单，对于不同厂商，不同型号的核心部件或设施设备至少有一套/台安全备件。")
    _write_captioned_flow(
        doc,
        ch.get("flow"),
        ch.get("table"),
        "表9-1 安全库存清单",
        vmerge=ch.get("vmerge"),
    )
    _write_optional_section(doc, "9.2  全网备品备件更新情况统计和分析", 2, ch.get("update"))
    _write_summary_hole(doc, "9.3  评估小结")


def write_ch10(doc, pack: dict[str, Any]) -> None:
    """第 10 章：开篇体例 + 按线路 10.1.x；无线路稿时退回整段 flow。"""
    ch = pack.get("ch10") or {}
    secs = ch.get("sections") or []
    filled = [s for s in secs if not s.get("empty") and (s.get("flow") or s.get("paras"))]
    flat_flow = ch.get("flow") or []
    flat_paras = ch.get("paras") or []
    has_body = bool(filled or flat_flow or flat_paras)
    add_heading(doc, "10  使用环境符合性评估", 1)
    add_heading(
        doc,
        "10.1  环境符合性评估",
        2,
        (ch.get("source") or "") if has_body else "",
        yellow=not has_body,
    )
    if filled:
        add_para(doc, ENV_LEAD)
        add_para(doc, ENV_LEAD_BRIDGE)
        for sec in secs:
            line_no = int(sec.get("line_no") or 0)
            if not line_no:
                continue
            heading = f"10.1.{line_no}  轨道交通{line_no}号线"
            empty = bool(sec.get("empty")) or not (sec.get("flow") or sec.get("paras"))
            add_heading(
                doc,
                heading,
                3,
                (sec.get("source") or "") if not empty else "",
                yellow=empty,
            )
            if empty:
                continue
            if not _write_flow(doc, sec.get("flow")):
                _write_paras(doc, sec.get("paras") or [])
    elif flat_flow or flat_paras:
        if not _write_flow(doc, flat_flow):
            _write_paras(doc, flat_paras)
    _write_summary_hole(doc, "10.2  评估小结")


def write_ch11(doc, pack: dict[str, Any]) -> None:
    """第 11 章：11.1 按线路 11.1.x；工器具与小结有材料就填。"""
    ch = pack.get("ch11") or {}
    year = int(ch.get("year") or pack.get("year") or 2026)
    src = ch.get("source") or ""
    secs = ch.get("sections") or []
    has_any = any(not (sec.get("empty") or not (sec.get("flow") or sec.get("paras"))) for sec in secs)
    add_heading(doc, "11  退运报废倾向性评估", 1)
    add_heading(doc, f"11.1  {year}年各线路设备退运更换情况", 2, src, yellow=not has_any)
    if not secs:
        add_heading(doc, "11.1.1  各线路设备退运更换", 3, yellow=True)
    for sec in secs:
        line_no = int(sec.get("line_no") or _retire_line_no_from_title(sec.get("title") or "") or 0)
        line = sec.get("line") or (f"{line_no}号线" if line_no else "")
        title = sec.get("title") or (f"轨道交通{line}" if line else "退运更换")
        if line_no:
            heading = f"11.1.{line_no}  {title if title.startswith('轨道交通') else f'轨道交通{line_no}号线'}"
        else:
            heading = title
        flow = sec.get("flow")
        items = sec.get("paras") or []
        texts = _plain_texts(flow) or [str(t).strip() for t in items if str(t).strip()]
        empty = bool(sec.get("empty")) or not texts
        add_heading(doc, heading, 3, (sec.get("source") or "") if not empty else "", yellow=False)
        if empty:
            add_para(doc, f"{line or '该线'}暂无退运报废设备。")
            continue
        if not _write_flow(doc, flow):
            _write_paras(doc, items)
    _write_optional_section(doc, "11.2  固定资产工器具配置情况", 2, ch.get("tools"))
    _write_summary_hole(doc, "11.3  评估小结")


def _retire_line_no_from_title(title: str) -> int | None:
    m = re.search(r"(\d+)\s*号线", title or "")
    return int(m.group(1)) if m else None


def write_ch12(doc, pack: dict[str, Any]) -> None:
    """第 12 章：总结与建议有材料就填；附录 A 挂第 3 章管控措施全表。"""
    ch = pack.get("ch12") or {}
    add_heading(doc, "12  总结与建议", 1)
    _write_optional_section(doc, "12.1  总结", 2, ch.get("summary"))
    _write_optional_section(doc, "12.2  建议和措施", 2, ch.get("advice"))
    appendix = ((pack.get("ch3") or {}).get("controls") or {}).get("appendix") or []
    src = ((pack.get("ch3") or {}).get("controls") or {}).get("source") or ""
    add_heading(doc, "附录A  供电（含能源系统）各线路管控措施", 1, src, yellow=not appendix)
    if appendix:
        add_table(doc, appendix)


WRITERS = {
    "ch1": write_ch1,
    "ch2": write_ch2,
    "ch3": write_ch3,
    "ch4": write_ch4,
    "ch5": write_ch5,
    "ch6": write_ch6,
    "ch7": write_ch7,
    "ch8": write_ch8,
    "ch9": write_ch9,
    "ch10": write_ch10,
    "ch11": write_ch11,
    "ch12": write_ch12,
}

COVERS = {
    "ch3": "第三章  设备功能有效性评估（供电含能源系统）",
    "ch4": "第四章  运营契合满足度评估（供电含能源系统）",
    "ch5": "第五章  管理体系合规性评估（供电含能源系统）",
    "ch6": "第六章  修程修制匹配性评估（供电含能源系统）",
    "ch7": "第七章  运维表现健康度评估（供电含能源系统）",
    "ch8": "第八章  风险隐患闭环度评估（供电含能源系统）",
    "ch9": "第九章  备件物资保障度评估（供电含能源系统）",
    "ch10": "第十章  使用环境符合性评估（供电含能源系统）",
    "ch11": "第十一章  退运报废倾向性评估（供电含能源系统）",
    "full": "供电（含能源系统）",
}


def write_chapter_docx(pack: dict[str, Any], path: str | Path, chapter_id: str) -> Path:
    """网页按章成文：封面 + 本章目录。缺材料只黄标题，出处只写在标题后括号里。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = new_report_document()
    year = pack.get("year") or 2026
    set_assessment_year(year)
    add_cover(doc, year=year, cover_line=COVERS.get(chapter_id) or f"{chapter_id}（供电含能源系统）")
    writer = WRITERS.get(chapter_id)
    if writer:
        writer(doc, pack)
    doc.save(str(path))
    return path


def write_full_docx(pack: dict[str, Any], path: str | Path) -> Path:
    """CLI 全年报：第 1～12 章按 2025 目录顺序写入同一份 Word。网页按章评估不走这里。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = new_report_document()
    year = pack.get("year") or 2026
    set_assessment_year(year)
    add_cover(doc, year=year, cover_line="供电（含能源系统）")
    for cid in ("ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11", "ch12"):
        WRITERS[cid](doc, pack)
    doc.save(str(path))
    return path
