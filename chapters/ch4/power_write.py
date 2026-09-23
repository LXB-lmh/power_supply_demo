# -*- coding: utf-8 -*-
"""供电第四章成文：按年报目录填入，出处只标在标题后括号。

缺材料黄标题；故障句不通顺/数字年份错黄该句并黄该线路标题。
4.1.1：材料→去年报告→黄；4.1.2：总表句+材料变化段；4.4 小节标题不因缺句号误黄。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from chapters.ch4.power_extract import _is_volume_change_body
from chapters.ch4.power_style import CYCLE_TABLE
from chapters.common.drawings import copy_drawings_from_body_index, copy_formula_paragraph_from_body_index
from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts, is_chapter_or_appendix_title, outline_num
from chapters.common.word import (
    add_caption,
    add_cover,
    add_heading,
    add_para,
    add_table,
    any_needs_mark,
    is_section_title_line,
    needs_mark,
    new_report_document,
    set_assessment_year,
)


def _items(raw: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            out.append({"kind": "text", "text": item})
        elif isinstance(item, dict):
            out.append(item)
    return out


def _is_caption(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) >= 80 or t[0] not in {"图", "表"}:
        return False
    return t[1].isdigit() or t[1] in " -"


def _should_skip_leaked_title(text: str) -> bool:
    compact = compact_text(text)
    if is_chapter_or_appendix_title(compact):
        return True
    num = outline_num(compact)
    if num and is_section_title_line(text):
        try:
            return int(num.split(".", 1)[0]) != 4
        except ValueError:
            return False
    return False


def _write_paras(doc, texts: list[str] | None) -> None:
    for text in dedupe_texts(texts):
        t = str(text).strip()
        if not t or _should_skip_leaked_title(t):
            continue
        if _is_caption(t):
            add_caption(doc, t)
        elif is_section_title_line(t):
            add_heading(doc, t, 3, yellow=False)
        else:
            add_para(doc, t)


def _write_flow(doc, items: list[dict[str, Any]] | None) -> bool:
    items = dedupe_flow_items(items)
    if not items:
        return False
    for item in items:
        kind = item.get("kind")
        if kind == "formula":
            copy_formula_paragraph_from_body_index(
                item.get("source_path") or "",
                int(item.get("source_index") or -1),
                doc,
            )
            continue
        if kind == "drawing":
            copy_drawings_from_body_index(
                item.get("source_path") or "",
                int(item.get("source_index") or -1),
                doc,
            )
            continue
        if kind == "table":
            from chapters.common.table_copy import write_table_item

            if write_table_item(doc, item):
                continue
            merges = None
            if "vmerge" in item:
                raw = item.get("vmerge") or []
                merges = [
                    (int(m[0]), int(m[1]), int(m[2]))
                    for m in raw
                    if isinstance(m, (list, tuple)) and len(m) >= 3
                ]
            add_table(doc, item.get("rows") or [], vmerge=merges)
            continue
        text = str(item.get("text") or "").strip()
        if not text or _should_skip_leaked_title(text):
            continue
        if _is_caption(text):
            add_caption(doc, text)
        elif is_section_title_line(text):
            # 4.4.1～4.4.5：当标题写，无材料缺失/逻辑错误时不黄
            add_heading(doc, text, 3, yellow=False)
        else:
            add_para(doc, text, source_yellow=bool(item.get("source_yellow")))
    return True


def write_docx(pack: dict[str, Any], path: str | Path) -> Path:
    """网页第四章成文。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = new_report_document()
    year = pack.get("year") or 2026
    set_assessment_year(year)
    add_cover(doc, year=year, cover_line="第四章  运营契合满足度评估（供电含能源系统）")

    add_heading(doc, "4  运营契合满足度评估", 1)
    add_heading(doc, "4.1  设备体量和变化情况", 2)

    scope_ok = bool(pack.get("scope_paras") or pack.get("scope_flow"))
    add_heading(doc, "4.1.1  设备体量", 3, pack.get("scope_source") or "", yellow=not scope_ok)
    if scope_ok:
        if not _write_flow(doc, pack.get("scope_flow")):
            _write_paras(doc, pack.get("scope_paras"))
    else:
        # 无材料且无去年可复用时仍可写体例底稿？用户要求都没有就标黄——不写死 POWER_SCOPE
        pass

    volume = pack.get("volume_text") or ""
    plan = pack.get("plan_text") or ""
    # 防泄漏：材料跳节时切片可能带进 4.4 标题/正文，绝不当 4.1.2 写出
    changes = [
        str(x).strip()
        for x in (pack.get("volume_change_paras") or [])
        if _is_volume_change_body(str(x))
    ]
    has_412 = bool(volume or changes)
    add_heading(
        doc,
        "4.1.2  设备体量变化情况",
        3,
        pack.get("grade_source") or "",
        yellow=not has_412 or needs_mark(volume) or any_needs_mark(changes + ([plan] if plan else [])),
    )
    if volume:
        add_para(doc, volume)
    for para in changes:
        add_para(doc, para)
    if plan:
        add_para(doc, plan)

    # 目录固定对照去年：4.2 → 4.3 → 4.4 → 4.5；4.2 周期表可复用去年/体例
    add_heading(doc, "4.2  设备维护周期和维护内容", 2, pack.get("cycle_source") or "")
    add_para(doc, "设备维护周期和维护内容如下：")
    cycle_rows = pack.get("cycle_rows") or CYCLE_TABLE
    if cycle_rows and len(cycle_rows) > 1:
        add_table(doc, cycle_rows)

    by_line: dict[str, list] = pack.get("fault_by_line") or {}
    fault_src = pack.get("fault_source") or ""
    add_heading(doc, "4.3  各个线路基本情况", 2, fault_src, yellow=not (fault_src or by_line))
    if fault_src or by_line:
        for i in range(1, 19):
            line = f"{i}号线"
            items = _items(by_line.get(line))
            texts = [
                str(x.get("text") or "").strip()
                for x in items
                if x.get("kind") in {"text", "para"} and str(x.get("text") or "").strip()
            ]
            add_heading(doc, line, 3, yellow=not items or any_needs_mark(texts))
            for item in items:
                if item.get("kind") == "formula":
                    copy_formula_paragraph_from_body_index(
                        item.get("source_path") or "",
                        int(item.get("source_index") or -1),
                        doc,
                    )
                    continue
                if item.get("kind") == "drawing":
                    copy_drawings_from_body_index(
                        item.get("source_path") or "",
                        int(item.get("source_index") or -1),
                        doc,
                    )
                    continue
                if item.get("kind") == "table":
                    add_table(doc, item.get("rows") or [])
                    continue
                text = str(item.get("text") or "").strip()
                if text:
                    add_para(doc, text)

    mtbf_flow = pack.get("mtbf_flow") or []
    mtbf_ok = bool(mtbf_flow or pack.get("mtbf_paras") or pack.get("mtbf_table"))
    add_heading(doc, "4.4  各线路供电系统年度生产指标", 2, pack.get("mtbf_source") or "", yellow=not mtbf_ok)
    if mtbf_ok:
        if not _write_flow(doc, mtbf_flow):
            _write_paras(doc, pack.get("mtbf_paras"))
            if pack.get("mtbf_table"):
                add_table(doc, pack.get("mtbf_table"))

    add_heading(doc, "4.5  评估小结", 2, yellow=True)

    doc.save(str(path))
    return path


write_ch4_power_docx = write_docx
