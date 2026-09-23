# -*- coding: utf-8 -*-
"""按年报小节对照抽取结果：缺材料、逻辑不通、语言不通顺、标点错误。不编造。

黄标与网页列表对齐：
- 缺材料：整节没有可填内容 → 黄标题；
- 措施未填：管控措施表有该线路行，但措施列全空（与「没这张表」不同）；
- 逻辑不通：数字合计对不上、文图表对不上等 → 黄该句/该节；
- 句子不通/标点坏 → 黄该句，并黄该小节标题。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.word import is_incomplete, is_punct_issue, is_section_title_line, language_note, punct_note, split_clauses
from chapters.common.number_logic import number_logic_notes, year_logic_notes
from chapters.power.style import CH3_METHOD_MISSING

FAULT_NO_COUNT = re.compile(r"故障起(?!\d)")

# review_chapter 写入，供 _scan_texts 做年份校验
_REVIEW_YEAR: int | None = None


def _add(out: list[dict[str, str]], section: str, kind: str, issue: str, note: str = "") -> None:
    """同一小节同一问题只记一条，避免网页黄标列表刷屏。"""
    key = (section, kind, issue, note)
    if any((x["section"], x["kind"], x["issue"], x.get("note") or "") == key for x in out):
        return
    item = {"section": section, "kind": kind, "issue": issue}
    if note:
        item["note"] = note
    out.append(item)


def _missing(out: list[dict[str, str]], section: str, note: str = "") -> None:
    """整节没有材料。成文侧只黄标题，不写「材料未提供」占位句。"""
    _add(out, section, "missing", "缺失材料", note)


def _language(out: list[dict[str, str]], section: str, note: str = "") -> None:
    """句子不通顺或话说一半。成文侧黄该句，并黄该小节标题。"""
    _add(out, section, "language", "语言不通顺", note)


def _logic(out: list[dict[str, str]], section: str, note: str = "") -> None:
    """文图表对不上（写了如图但没有图、第六章混入第五章表号等）。"""
    _add(out, section, "logic", "逻辑不通", note)


def _punct(out: list[dict[str, str]], section: str, note: str = "") -> None:
    """标点问题。成文黄该分句，并黄对应标题。说明写在 note 里。"""
    _add(out, section, "punct", "标点错误", note)


def _clip(text: str, n: int = 36) -> str:
    t = (text or "").replace("\n", "").strip()
    return t if len(t) <= n else t[:n] + "…"


def _year(out: list[dict[str, str]], section: str, note: str = "") -> None:
    """年份错误（截止到更早年、对比不含评估年等）。前端与逻辑不通同栏。"""
    _add(out, section, "year", "年份错误", note)


def _scan_texts(out: list[dict[str, str]], section: str, texts: list[str], *, year: int | None = None) -> None:
    """数字合计/均值/趋势 → 逻辑；年份 → 年份错误；残句/标点照旧。"""
    y = year if year is not None else _REVIEW_YEAR
    for raw in texts:
        t = (raw or "").strip()
        if not t:
            continue
        for note in number_logic_notes(t):
            _logic(out, section, note)
        for note in year_logic_notes(t, y):
            _year(out, section, note)
        if "；；" in t or "；。" in t or "。；" in t:
            _punct(out, section, punct_note(t))
        for clause in split_clauses(t) or [t]:
            clause = clause.strip()
            if not clause:
                continue
            packed = clause.replace(" ", "")
            if FAULT_NO_COUNT.search(packed):
                _language(out, section, language_note(clause))
            elif is_incomplete(clause):
                _language(out, section, language_note(clause))
            elif is_punct_issue(clause):
                _punct(out, section, punct_note(clause))


def _flow_texts(items: list[dict[str, Any]] | None) -> list[str]:
    return [str(x.get("text") or "").strip() for x in items or [] if x.get("kind") not in {"drawing", "table", "formula", "formula_3_1"}]


def _ch4(pack: dict[str, Any]) -> dict[str, Any]:
    """网页第四章 pack 可能平铺在根上，全年报则在 pack['ch4']。两处都要认。"""
    nested = pack.get("ch4")
    if isinstance(nested, dict) and (nested.get("fault_by_line") is not None or nested.get("volume_text") is not None):
        return nested
    if pack.get("fault_by_line") is not None or pack.get("volume_text") is not None:
        return pack
    return nested or {}


def _control_row_lines(controls: dict[str, Any]) -> tuple[set[str], set[str]]:
    """附录里有行的线路，以及措施列写过字的线路。

    有行无字 → 措施未填；连行都没有 → 缺材料。不要把空措施表报成「没上传管控措施」。
    """
    has_row: set[str] = set()
    has_measure: set[str] = set()
    empty = {"", "/", "-", "—", "无", "None"}
    for row in (controls.get("appendix") or [])[1:]:
        if not row:
            continue
        line = str(row[0] or "").strip()
        if not line:
            continue
        has_row.add(line)
        rest = row[5:] if len(row) > 5 else []
        if any(str(c or "").strip() not in empty for c in rest):
            has_measure.add(line)
    return has_row, has_measure


def _blank_measure(out: list[dict[str, str]], section: str) -> None:
    """有线路行但措施列没写字。网页单独标「措施未填」，不要误报成缺整张管控措施表。"""
    _add(out, section, "missing", "措施未填")


def _ch3_prose_missing(section: dict[str, Any] | None) -> bool:
    sec = section or {}
    if any(str(p).strip() for p in (sec.get("paras") or [])):
        return False
    for item in sec.get("flow") or []:
        if item.get("kind") in {"table", "drawing", "formula", "formula_3_1"}:
            return False
        if str(item.get("text") or "").strip():
            return False
    return True


def review_ch3(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 3 章：3.1/3.2/3.3.1 无体例段、3.3.2 无表、3.4 缺线或措施未填、3.5 无两年对比、3.6 无劣化条目。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch3") or {}
    if _ch3_prose_missing(ch.get("method")):
        _missing(out, "3.1", CH3_METHOD_MISSING)
    if _ch3_prose_missing(ch.get("standard")):
        _missing(out, "3.2", CH3_METHOD_MISSING)
    if _ch3_prose_missing(ch.get("scope")):
        _missing(out, "3.3.1", CH3_METHOD_MISSING)
    if not (ch.get("power_table") or ch.get("main_table") or ch.get("energy_table")):
        _missing(out, "3.3.2")
    else:
        overview = ch.get("overview") or ""
        if isinstance(overview, str) and overview.strip():
            _scan_texts(out, "3.3.2", [p.strip() for p in re.split(r"(?<=[。！？])", overview) if p.strip()])
        elif isinstance(overview, list):
            _scan_texts(out, "3.3.2", [str(x) for x in overview])
    controls = ch.get("controls") or {}
    prose = controls.get("prose") or []
    has_row, has_measure = _control_row_lines(controls)
    # 表里有该线路行但措施列全空 →「措施未填」；连行都没有才是缺材料。
    if not prose:
        if has_row and not has_measure:
            _blank_measure(out, "3.4")
        else:
            _missing(out, "3.4")
    else:
        for i in range(1, 19):
            line = f"{i}号线"
            item = next((x for x in prose if x.get("line") == line), None)
            if not item:
                if line in has_row and line not in has_measure:
                    _blank_measure(out, f"3.4 {line}")
                else:
                    _missing(out, f"3.4 {line}")
                continue
            paras = [p.strip() for block in item.get("blocks") or [] for p in str(block).split("\n") if p.strip()]
            _scan_texts(out, f"3.4 {line}", paras)
    if not ch.get("compare_power"):
        _missing(out, "3.5")
    else:
        _scan_texts(out, "3.5", list(ch.get("migrations") or []))
    _missing(out, "3.6")  # 各章评估小结一律留空黄标
    return out


def review_ch4(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 4 章：4.1.1/4.1.2/4.3/4.4；数字与年份逻辑；4.5 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = _ch4(pack)
    if not (ch.get("scope_paras") or ch.get("scope_flow")):
        _missing(out, "4.1.1")
    else:
        _scan_texts(out, "4.1.1", list(ch.get("scope_paras") or []) + _flow_texts(ch.get("scope_flow")))
    volume = ch.get("volume_text") or ""
    changes = [str(x).strip() for x in (ch.get("volume_change_paras") or []) if str(x).strip()]
    if not (volume or changes):
        _missing(out, "4.1.2")
    else:
        texts = ([volume] if volume else []) + changes
        if ch.get("plan_text"):
            texts.append(ch.get("plan_text") or "")
        _scan_texts(out, "4.1.2", texts)
    by_line = ch.get("fault_by_line") or {}
    if not (ch.get("fault_source") or by_line):
        _missing(out, "4.3")
    else:
        for i in range(1, 19):
            line = f"{i}号线"
            items = by_line.get(line) or []
            if not items:
                _missing(out, f"4.3 {line}")
                continue
            texts = [str(x.get("text") or "") for x in items if x.get("kind") not in {"drawing", "table", "formula", "formula_3_1"}]
            _scan_texts(out, f"4.3 {line}", texts)
    mtbf_ok = bool(ch.get("mtbf_paras") or ch.get("mtbf_flow") or ch.get("mtbf_table"))
    if not mtbf_ok:
        _missing(out, "4.4")
    else:
        # 小节标题行不做标点缺句号扫描；年份/数字仍扫正文
        texts = []
        for t in list(ch.get("mtbf_paras") or []) + _flow_texts(ch.get("mtbf_flow")):
            if is_section_title_line(t):
                for note in year_logic_notes(t, _REVIEW_YEAR):
                    _year(out, "4.4", note)
                continue
            texts.append(t)
        _scan_texts(out, "4.4", texts)
    _missing(out, "4.5")
    return out


def review_ch5(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 5 章各小节有无材料；写了「如图5-x」却没图记逻辑不通。5.7 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch5") or {}
    if not (ch.get("special") or ch.get("special_flow")):
        _missing(out, "5.1")
    else:
        _scan_texts(out, "5.1", ch.get("special") or _flow_texts(ch.get("special_flow")))
    if not (ch.get("inspect") or ch.get("inspect_flow")):
        _missing(out, "5.2")
    else:
        _scan_texts(out, "5.2", ch.get("inspect") or _flow_texts(ch.get("inspect_flow")))
    if not (ch.get("law") or ch.get("law_flow")):
        _missing(out, "5.3")
    else:
        _scan_texts(out, "5.3", ch.get("law") or _flow_texts(ch.get("law_flow")))
    if not (ch.get("std_table") or ch.get("std_paras") or ch.get("std_flow")):
        _missing(out, "5.4")
    else:
        _scan_texts(out, "5.4", ch.get("std_paras") or _flow_texts(ch.get("std_flow")))
        texts = " ".join(ch.get("std_paras") or [])
        if "如图5-1" in texts and not any(x.get("kind") == "drawing" for x in ch.get("std_flow") or []):
            _logic(out, "5.4", "写了如图5-1但没有图")
    if not (ch.get("exec") or ch.get("exec_flow")):
        _missing(out, "5.5")
    else:
        _scan_texts(out, "5.5", ch.get("exec") or _flow_texts(ch.get("exec_flow")))
    if not (ch.get("eval") or ch.get("eval_flow")):
        _missing(out, "5.6")
    else:
        _scan_texts(out, "5.6", ch.get("eval") or _flow_texts(ch.get("eval_flow")))
        joined = " ".join(ch.get("eval") or [])
        drawings = [x for x in ch.get("eval_flow") or [] if x.get("kind") == "drawing"]
        if "如图5-2" in joined and len(drawings) < 1:
            _logic(out, "5.6", "写了如图5-2但没有图")
        if "如图5-3" in joined and len(drawings) < 2:
            _logic(out, "5.6", "写了如图5-3但没有图")
    _missing(out, "5.7")
    return out


def review_ch6(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 6 章：待完善、混入第五章表号、写了「分别是」却没表。6.3 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch6") or {}
    has = bool(ch.get("revise") or ch.get("tables") or ch.get("revise_flow"))
    if not has:
        _missing(out, "6.1")
    else:
        _scan_texts(out, "6.1", ch.get("revise") or _flow_texts(ch.get("revise_flow")))
        if ch.get("incomplete"):
            _logic(out, "6.1", "材料标题写待完善")
        if any("如表5-" in t or t.startswith("表5-") for t in ch.get("revise") or []):
            _logic(out, "6.1", "第六章混入第五章表号")
        if "分别是" in " ".join(ch.get("revise") or []) and not (ch.get("tables") or []):
            _logic(out, "6.1", "写了分别是但没有表")
    if not ch.get("count_table"):
        _missing(out, "6.2")
    _missing(out, "6.3")
    return out


def review_ch7(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 7 章：7.1 组织模式；7.2 开篇/四分法小节；表7-1；按线路缺料；7.3 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch7") or {}
    if not (ch.get("org_paras") or ch.get("org_flow")):
        _missing(out, "7.1")
    else:
        _scan_texts(out, "7.1", ch.get("org_paras") or _flow_texts(ch.get("org_flow")))
    if not (ch.get("lead_paras") or ch.get("lead_flow")):
        _logic(out, "7.2", "缺开篇导语（材料与去年均无）")
    if not ch.get("table"):
        _missing(out, "7.2.1")
    else:
        _scan_texts(out, "7.2.1", _flow_texts(ch.get("flow")))
    aspects = ch.get("aspects") or {}
    for cid, key in (("7.2.2", "meter"), ("7.2.3", "train"), ("7.2.4", "smart")):
        aspect = aspects.get(key) or {}
        lines = aspect.get("lines") or []
        if lines:
            filled = [ln for ln in lines if not ln.get("empty") and (ln.get("paras") or ln.get("flow"))]
            if not filled:
                _missing(out, cid)
            else:
                for ln in filled:
                    label = f"{cid}.{ln.get('line_no')}" if ln.get("line_no") else cid
                    _scan_texts(out, label, ln.get("paras") or _flow_texts(ln.get("flow")))
        elif not (aspect.get("paras") or aspect.get("flow")):
            _missing(out, cid)
        else:
            _scan_texts(out, cid, aspect.get("paras") or _flow_texts(aspect.get("flow")))
    _missing(out, "7.3")
    return out


def review_ch8(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 8 章：按大纲节点缺料标缺；8.2 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch8") or {}
    slots = ch.get("slots") or {}
    risk_ok = bool((slots.get("risk_db") or {}).get("table") or ch.get("risk_table"))
    hand_ok = bool((slots.get("handbook") or {}).get("table") or ch.get("handbook"))
    fault_ok = bool(
        (slots.get("faults") or {}).get("paras")
        or (slots.get("faults") or {}).get("flow")
        or ch.get("fault_paras")
        or ch.get("fault_flow")
    )
    if not risk_ok:
        _missing(out, "8.1.1")
    if not hand_ok:
        _missing(out, "8.1.2")
    if not fault_ok:
        _missing(out, "8.1.3")
    elif fault_ok:
        _scan_texts(out, "8.1.3", (slots.get("faults") or {}).get("paras") or ch.get("fault_paras") or [])
    if not (risk_ok or hand_ok or fault_ok):
        _missing(out, "8.1")
    _missing(out, "8.2")
    return out


def review_ch9(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 9 章：9.1/9.2 按材料判缺；9.3 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch9") or {}
    if not (ch.get("table") or ch.get("flow")):
        _missing(out, "9.1")
    else:
        _scan_texts(out, "9.1", _flow_texts(ch.get("flow")))
    update = ch.get("update") or {}
    if not (update.get("paras") or update.get("flow")):
        _missing(out, "9.2")
    else:
        _scan_texts(out, "9.2", update.get("paras") or _flow_texts(update.get("flow")))
    _missing(out, "9.3")
    return out


def review_ch10(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 10 章：按线路有正文则扫各线；否则看整段 flow。10.2 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch10") or {}
    secs = ch.get("sections") or []
    filled = [s for s in secs if not s.get("empty") and (s.get("paras") or s.get("flow"))]
    if filled:
        for sec in filled:
            title = (sec.get("title") or sec.get("line") or "环境").strip()
            _scan_texts(out, f"10.1 {title}", sec.get("paras") or _flow_texts(sec.get("flow")))
    elif not (ch.get("paras") or ch.get("flow")):
        _missing(out, "10.1")
    else:
        _scan_texts(out, "10.1", ch.get("paras") or _flow_texts(ch.get("flow")))
    _missing(out, "10.2")
    return out


def review_ch11(pack: dict[str, Any]) -> list[dict[str, str]]:
    """第 11 章：退运按线路判；空线「暂无」不算缺；11.3 小结固定缺。"""
    out: list[dict[str, str]] = []
    ch = pack.get("ch11") or {}
    secs = ch.get("sections") or []
    if not secs:
        _missing(out, "11.1")
    else:
        filled = [sec for sec in secs if not sec.get("empty") and (sec.get("paras") or sec.get("flow"))]
        if not filled:
            _missing(out, "11.1")
        for sec in filled:
            title = (sec.get("title") or sec.get("line") or "退运更换").strip()
            texts = sec.get("paras") or _flow_texts(sec.get("flow"))
            _scan_texts(out, f"11.1 {title}", texts)
    tools = ch.get("tools") or {}
    if not (tools.get("paras") or tools.get("flow")):
        _missing(out, "11.2")
    else:
        _scan_texts(out, "11.2", tools.get("paras") or _flow_texts(tools.get("flow")))
    _missing(out, "11.3")
    return out


REVIEWERS = {
    "ch3": review_ch3,
    "ch4": review_ch4,
    "ch5": review_ch5,
    "ch6": review_ch6,
    "ch7": review_ch7,
    "ch8": review_ch8,
    "ch9": review_ch9,
    "ch10": review_ch10,
    "ch11": review_ch11,
}


def review_chapter(pack: dict[str, Any], chapter_id: str) -> list[dict[str, str]]:
    """网页按章审阅入口。未实现审阅的章（如全年报里的 1、2、12）返回空列表。"""
    global _REVIEW_YEAR
    _REVIEW_YEAR = pack.get("year") or (pack.get("ch4") or {}).get("year")
    fn = REVIEWERS.get(chapter_id)
    if not fn:
        return []
    return fn(pack)
