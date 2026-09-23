# -*- coding: utf-8 -*-
"""接触网各章抽取。

规则：
- 目录：默认 2025 触网保底结构；前端上传了去年报告则学其 Heading；
- 内容：只从当年材料抽取；认不准就不填，成文黄标题；禁止编造；
- DeepSeek：只做段落 keep/drop，不写正文、不编数字。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.list_number import renumber_continued_list_paras
from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts, slice_named_section
from chapters.common.table_copy import table_flow_item
from chapters.overhead.outline import (
    CHAPTER_NAMES,
    insert_content_children,
    resolve_chapter_outline,
)
from chapters.overhead.style import OVERHEAD_GRADE_COLS
from chapters.common.domain_filter import prepare_overhead_docs
from chapters.power.extract import (
    _src,
    _stock_table_kind,
    _table_item,
    count_shown,
    grade_dist_note,
    matrix_table,
)
from parsers.document_model import DocumentModel
from scope.grade_matrix import extract_grade_matrix

_LINE_RE = re.compile(r"(?:轨道交通)?(\d{1,2})\s*号线")


def extract_overhead_grade(docs: list[DocumentModel]) -> dict[str, Any]:
    matrix = extract_grade_matrix(docs)
    source = ""
    if matrix:
        source = str(matrix[0].get("source_note") or "")
    table = matrix_table(matrix, OVERHEAD_GRADE_COLS, "供电|接触网|接触网（轨）")
    if len(table) <= 1:
        table = [["线路", "区段", *OVERHEAD_GRADE_COLS]]
        for row in matrix:
            grades = row.get("grades") or {}
            if not any(grades.get(c) for c in OVERHEAD_GRADE_COLS):
                continue
            table.append(
                [
                    row.get("line_id") or "",
                    row.get("segment") or "",
                    *[grades.get(c) or "/" for c in OVERHEAD_GRADE_COLS],
                ]
            )
    counts = count_shown(table)
    overview = ""
    if len(table) > 1:
        total = sum(counts.values())
        overview = (
            f"接触网（轨）设备评估{total}项，"
            f"其中A类{counts.get('A', 0)}项、B类{counts.get('B', 0)}项、"
            f"C类{counts.get('C', 0)}项、D类{counts.get('D', 0)}项。"
        )
        note = grade_dist_note(table)
        if note:
            overview += note
    return {
        "source": source,
        "table": table if len(table) > 1 else [],
        "overview": overview,
        "counts": dict(counts),
    }


_CTRL_PROSE_RE = re.compile(
    r"^(?:\d+[、.．)）]\s*)?(集中修(?:项目|检验|检测)?|大修更新改造|大修需求|差异化管控|"
    r"现有风险点的管控|现有管控措施|后续风险管控|后续的管控措施|"
    r"专项更换|专项整治|专项改造|专项[：:]|备品备件|管控策略)"
)
_FAULT_CMP_RE = re.compile(
    r"(?:轨道交通)?(\d{1,2})\s*号线[，,：:\s].{0,48}(20\d{2}年).{0,24}(自检自修|总计发生|故障次数)"
)


def _ctrl_line_key(text: str) -> str | None:
    m = _LINE_RE.search(str(text or ""))
    if not m:
        return None
    n = int(m.group(1))
    return f"{n}号线" if 1 <= n <= 18 else None


def _is_progress_ledger(text: str) -> bool:
    c = compact_text(text)
    return "完成率" in c and ("已完成" in c or "计划完成" in c)


def _is_excel_ledger_cell(text: str) -> bool:
    t = str(text or "").strip()
    if _is_progress_ledger(t):
        return True
    c = compact_text(t)
    return c.startswith("已纳入") and ("大修" in c or "更新改造" in c)


_CD_LOCATION_KEYS = (
    "C状态的区段",
    "D状态的区段",
    "C状态区段",
    "D状态区段",
    "C状态区间",
    "D状态区间",
    "C状态的柔性",
    "C状态的刚性",
    "C、D状态的柔性",
    "C、D状态的刚性",
    "C状态的隔离开关",
    "D状态的隔离开关",
    "C状态的隔离开关控制屏",
)


def _is_status_cd_blob(text: str) -> bool:
    t = str(text or "").strip()
    if _CTRL_PROSE_RE.match(t) or _CTRL_PROSE_RE.match(_ctrl_rest(t)):
        return False
    c = compact_text(t)
    return any(
        k in c
        for k in (
            *_CD_LOCATION_KEYS,
            "没有C和D",
            "无C、D状态",
            "无C和D状态",
            "维持现有管控",
        )
    )


def _is_cd_location_inventory(text: str) -> bool:
    """C/D 设备在哪些区段/区间，不是在写管控动作。"""
    t = str(text or "").strip()
    if not t:
        return False
    if _CTRL_PROSE_RE.match(t) or _CTRL_PROSE_RE.match(_ctrl_rest(t)):
        return False
    c = compact_text(t)
    if any(k in c for k in ("没有C和D", "无C、D", "无C和D", "没有C、D")):
        return False
    if any(
        k in c
        for k in ("平替", "跟踪管控", "集中修", "专项更换", "专项整治", "差异化管控", "备品备件")
    ):
        return False
    if any(k in c for k in _CD_LOCATION_KEYS):
        return True
    return ("主要集中在" in c or "全线均匀分布" in c) and ("C状态" in c or "D状态" in c or "C、D" in c)


def _is_status_grade_inventory(text: str) -> bool:
    """3.3 状态分布（子系统/锚段 A/B/C/D），不是 3.4 管控措施。"""
    t = str(text or "").strip()
    rest = _ctrl_rest(t)
    if _CTRL_PROSE_RE.match(t) or _CTRL_PROSE_RE.match(rest):
        return False
    c = compact_text(t)
    if any(
        k in c
        for k in (
            "平替",
            "跟踪管控",
            "集中修",
            "专项更换",
            "专项整治",
            "备品备件",
            "分险点",
            "主要风险",
            "风险点的管控",
            "现有风险点",
        )
    ):
        return False
    if "触网子系统和设备状态" in c or "接触网子系统是" in c:
        return True
    if compact_text(rest).startswith(("正线触网子系统", "北延伸触网子系统")):
        return True
    if ("是A状态" in c or "是B状态" in c or "是C状态" in c or "是D状态" in c) and "管控策略包括" in c:
        return True
    return False


def _is_inline_status_wear(text: str) -> bool:
    """3.3 表后「C状态…差异化管控是，10mm…」不是 3.4 专节。"""
    t = str(text or "").strip()
    if _CTRL_PROSE_RE.match(t):
        return False
    c = compact_text(t)
    return "差异化管控是" in c or ("C状态" in c and "接触线剩余高度" in c)


_LINE_HEAD_RE = re.compile(
    r"^(?:\d+(?:[.．]\d+)+\s*)?(?:\d+[、.．)）]\s*)?(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)"
)
_CTRL_STOP_MARKS = (
    "评估小结",
    "评估结论",
    "年评估对比",
    "故障趋势",
    "设备体量",
    "各个线路基本情况",
)
_STATUS_KIND_TITLES = {
    "接触网状态",
    "隔离开关",
    "隔离开关控制屏",
    "柔性",
    "刚性",
    "接触轨",
    "柔性接触网",
    "刚性接触网",
    "设备状态",
    "管控措施",
}


def _line_heading_intent(text: str) -> str | None:
    """线路标题在干什么：status=3.3状态说明，control=3.4管控专节。

    看标题语义，不要求字面等于「设备状态」「接触网状态」。
    标题后头已经跟了一大段正文，或正文在报「状态是C」，不当成小节标题。
    """
    raw = str(text or "").strip()
    m = _LINE_HEAD_RE.match(raw)
    if not m:
        return None
    rest = raw[m.end() :].strip().lstrip("：:").strip()
    rest_c = compact_text(rest)
    if not rest_c:
        return None
    if len(rest_c) > 18:
        return None
    if any(k in rest_c for k in ("风险点", "管控措施", "管控策略")):
        if rest_c.startswith("差异化"):
            return None
        return "control"
    if any(k in rest_c for k in ("是", "为")):
        return None
    if rest_c in {"设备状态", "接触网状态", "触网状态", "子系统状态"}:
        return "status"
    if rest_c.startswith(("设备状态", "接触网状态", "触网状态")) and len(rest_c) <= 12:
        return "status"
    if rest_c.endswith("状态") and "管控" not in rest_c:
        return "status"
    return None


def _ctrl_rest(text: str) -> str:
    t = re.sub(r"^(?:\d+(?:[.．]\d+)+\s*)?(?:\d+[、.．)）]\s*)?", "", str(text or "").strip())
    return re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", t).strip()


def is_fault_compare_para(text: str) -> bool:
    """4.4 用的「N号线，20xx年…20yy年总计发生」对照句，不是 4.3 期间叙述。"""
    t = str(text or "").strip()
    if not t or t.startswith("典型故障") or "抢修令" in t or "故障设备趋势" in t:
        return False
    if "期间" in t:
        return False
    years = set(re.findall(r"20\d{2}年", t))
    if len(years) < 2:
        return False
    return "号线" in t and any(k in t for k in ("总计发生", "自检自修", "故障次数"))


def harvest_fault_year_compare(docs: list[DocumentModel] | None, year: int | None = None) -> dict[str, Any]:
    from chapters.overhead.section_bundle import sort_docs_newest_last

    by_line: dict[str, str] = {}
    src_line: dict[str, str] = {}
    score: dict[str, int] = {}
    for doc, _idx in sort_docs_newest_last(docs or []):
        if (doc.suffix or "").lower() in {".xlsx", ".xls"}:
            continue
        src = _src(doc)
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if not is_fault_compare_para(t):
                continue
            ln = _ctrl_line_key(t)
            if not ln:
                continue
            years = {int(x) for x in re.findall(r"(20\d{2})年", t)}
            sc = 2 if year and year in years and (year - 1) in years else 1
            if sc < score.get(ln, -1):
                continue
            by_line[ln] = t
            src_line[ln] = src
            score[ln] = sc
    paras = [by_line[k] for k in sorted(by_line, key=_line_sort_key)]
    sources: list[str] = []
    for k in sorted(by_line, key=_line_sort_key):
        s = src_line.get(k) or ""
        if s and s not in sources:
            sources.append(s)
    return {
        "paras": paras,
        "flow": [{"kind": "para", "text": p} for p in paras],
        "source": "、".join(sources),
        "empty": not paras,
    }


def _colon_body(rest: str) -> str:
    if "：" in rest:
        return rest.split("：", 1)[-1].strip()
    if ":" in rest:
        return rest.split(":", 1)[-1].strip()
    return rest.strip()


def _is_ctrl_attach_table(rows: list[list[str]] | None) -> bool:
    """3.4 线路节里的在执行项目/合同表，不要状态分布、培训人次或评分总表。"""
    if not rows or len(rows) < 2:
        return False
    head = compact_text("".join(str(c or "") for r in rows[:2] for c in r))
    if any(k in head for k in ("锚段数量", "系统状态等级", "系统状态值", "评价", "人次", "课时", "培训")):
        return False
    if "线路" in head[:8] and any(k in head for k in ("占比", "锚段", "总数量")):
        return False
    if "在执行项目" in head or "合同（标段）" in head or "项目类别" in head:
        return True
    return "项目名称" in head and ("合同" in head or "标段" in head)


def harvest_control_prose(docs: list[DocumentModel] | None) -> dict[str, dict[str, Any]]:
    """3.4：部门稿「集中修/大修/差异化管控」原文，不把 Excel 台账行和 3.3 状态段灌进来。"""
    from chapters.overhead.outline import is_peer_chapter_title
    from chapters.overhead.section_bundle import sort_docs_newest_last

    by_line: dict[str, list[str]] = {}
    by_flow: dict[str, list[dict[str, Any]]] = {}
    line_src: dict[str, str] = {}
    for doc, _idx in sort_docs_newest_last(docs or []):
        suf = (doc.suffix or "").lower()
        if suf in {".xlsx", ".xls"}:
            continue
        src = _src(doc)
        current: str | None = None
        in_named = False
        in_risk = False
        in_status_dist = False
        in_status_notes = False
        last_diff = False
        for block in doc.blocks or []:
            if block.type == "table":
                if current and not in_status_dist and _is_ctrl_attach_table(block.rows):
                    item = table_flow_item(doc, block)
                    sig = compact_text(str(item.get("rows") or ""))
                    bagf = by_flow.setdefault(current, [])
                    if sig and sig not in {
                        compact_text(str(x.get("rows") or "")) for x in bagf if x.get("kind") == "table"
                    }:
                        bagf.append(item)
                        line_src[current] = src
                continue
            t = (block.text or "").strip()
            if not t:
                continue
            c = compact_text(t)
            if is_peer_chapter_title(t, current="各线路管控措施") and "管控" not in c:
                current = None
                in_named = False
                in_risk = False
                in_status_dist = False
                in_status_notes = False
                last_diff = False
                continue
            if any(k in c for k in _CTRL_STOP_MARKS) and "管控" not in c:
                current = None
                in_named = False
                in_risk = False
                in_status_notes = False
                last_diff = False
                continue
            if "评估结论" in c and len(c) < 24:
                current = None
                in_named = False
                in_risk = False
                last_diff = False
                continue
            if "状态分布" in c and "管控" not in c and len(c) < 40:
                in_status_dist = True
                current = None
                last_diff = False
                continue
            if "各线路管控措施" in c or re.match(r"^3\.4", c):
                in_named = True
                in_risk = False
                in_status_dist = False
                in_status_notes = False
                last_diff = False
                if "号线" not in c:
                    current = None
                    continue
            if "风险点及管控" in c:
                current = _ctrl_line_key(t) or current
                in_risk = True
                in_named = True
                in_status_dist = False
                last_diff = False
                if block.type == "heading":
                    continue
            mhead = _LINE_HEAD_RE.match(t)
            if mhead:
                n = int(mhead.group(1))
                if 1 <= n <= 18:
                    current = f"{n}号线"
                    last_diff = False
                    intent = _line_heading_intent(t)
                    if intent == "control":
                        in_risk = True
                        in_status_notes = False
                    elif intent == "status":
                        in_status_notes = True
                        in_risk = False
                    else:
                        in_status_notes = False
            if in_status_dist:
                continue
            if current is None:
                continue
            rest = _ctrl_rest(t)
            if not rest:
                continue
            if rest.rstrip("：:") in _STATUS_KIND_TITLES:
                continue
            is_ctrl = bool(_CTRL_PROSE_RE.match(t) or _CTRL_PROSE_RE.match(rest))
            if "现有风险管控措施" in t or "现有管控措施是" in t or "后续的管控措施" in t:
                is_ctrl = True
            if in_named and ("平替" in c or ("管控措施" in c and len(c) > 40)):
                is_ctrl = True
            if is_ctrl:
                mln = re.search(r"(?:轨道交通)?(\d{1,2})\s*号线", rest[:48])
                if mln:
                    n = int(mln.group(1))
                    if 1 <= n <= 18:
                        current = f"{n}号线"
            in_ctrl_sec = (in_named or in_risk) and not in_status_notes
            if not is_ctrl and (
                _is_cd_location_inventory(t)
                or _is_cd_location_inventory(rest)
                or _is_status_grade_inventory(t)
                or _is_status_grade_inventory(rest)
            ):
                continue
            if (_is_status_cd_blob(t) or _is_status_cd_blob(rest)) and not is_ctrl:
                if in_status_notes or not in_ctrl_sec:
                    continue
            if _is_inline_status_wear(t) or _is_progress_ledger(t):
                continue
            keep = is_ctrl
            skip_title = rest.rstrip("：:") in _STATUS_KIND_TITLES
            line_head_only = bool(
                block.type == "heading" and mhead and "状态是" not in t and len(rest) < 12
            )
            if is_ctrl and not _colon_body(rest):
                last_diff = True
                keep = bool(in_ctrl_sec)
            if in_ctrl_sec and not keep:
                if (
                    "评估结论" not in c
                    and not c.startswith("表")
                    and not skip_title
                    and not line_head_only
                ):
                    keep = True
            if in_ctrl_sec and not keep and last_diff:
                if not rest.startswith("主要风险") and "状态是" not in rest[:24] and not line_head_only:
                    keep = True
            if "评估结论" in c:
                keep = False
                current = None
            if not keep:
                last_diff = bool(is_ctrl and not _colon_body(rest))
                continue
            if compact_text(rest) in {"大修安排无", "大修安排：无"}:
                continue
            bag = by_line.setdefault(current, [])
            if compact_text(t) in {compact_text(x) for x in bag}:
                continue
            if any(k in c for k in ("评估结论", "评估小结")):
                continue
            bag.append(t)
            by_flow.setdefault(current, []).append({"kind": "para", "text": t})
            line_src[current] = src
            last_diff = rest.startswith("差异化管控") or t.startswith("差异化管控")
    return {"by_line": by_line, "by_flow": by_flow, "sources": line_src}


_NUM_ITEM_RE = re.compile(r"^\d+[、.．)）]")


def _is_pure_no_cd_echo(text: str) -> bool:
    """3.3 表后「柔性/刚性没有C和D」原句，不是 3.4 专节正文。"""
    from chapters.overhead.line_notes import note_asserts_no_cd

    t = str(text or "").strip()
    if not note_asserts_no_cd(t):
        return False
    c = compact_text(t)
    return not any(k in c for k in ("集中修", "大修", "差异化", "专项", "平替", "跟踪管控", "投运"))


def _is_status_dump_for_controls(text: str) -> bool:
    """设备状态节里的 C/D 区段清单、柔性/刚性空标题，不是 3.4 管控措施。"""
    t = str(text or "").strip()
    rest = _ctrl_rest(t).rstrip("：:")
    if rest in _STATUS_KIND_TITLES:
        return True
    if _line_heading_intent(t) == "status":
        return True
    if _CTRL_PROSE_RE.match(t) or _CTRL_PROSE_RE.match(rest):
        return False
    if _is_cd_location_inventory(t):
        return True
    if _is_status_grade_inventory(t):
        return True
    c = compact_text(t)
    if "平替" in c or "跟踪管控" in c:
        return False
    return _is_status_cd_blob(t)


def _drop_status_echoes(paras: list[str]) -> list[str]:
    kept = [p for p in paras if not _is_pure_no_cd_echo(p) and not _is_status_dump_for_controls(p)]
    return kept or paras


def _device_kind_label(text: str) -> str | None:
    rest = compact_text(_ctrl_rest(text))
    if rest.startswith("刚性接触网"):
        return "刚性设备"
    if rest.startswith("柔性接触网"):
        return "柔性设备"
    if rest.startswith("隔离开关控制屏"):
        return "隔离开关控制屏"
    if rest.startswith("隔离开关"):
        return "隔离开关"
    return None


def _ensure_device_kind_leads(paras: list[str]) -> list[str]:
    """材料按刚性/柔性/隔离开关分段但没写 1、2、3 时，成文补上小标题。"""
    labels = [_device_kind_label(p) for p in paras]
    kinds = [x for x in labels if x]
    if len(set(kinds)) < 2:
        return paras
    if any(_NUM_ITEM_RE.match(str(p).strip()) for p in paras):
        return paras
    out: list[str] = []
    n = 0
    seen: set[str] = set()
    for p, lab in zip(paras, labels):
        if lab and lab not in seen:
            n += 1
            seen.add(lab)
            out.append(f"{n}、{lab}")
        out.append(p)
    return out


def _polish_control_flow(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    tables = [x for x in flow if x.get("kind") == "table"]
    paras = _ensure_device_kind_leads(_drop_status_echoes(paras))
    paras = renumber_continued_list_paras(paras)
    return [{"kind": "para", "text": p} for p in paras] + tables


def extract_overhead_controls(docs: list[DocumentModel]) -> dict[str, Any]:
    from chapters.overhead.llm_gate import filter_flow

    word = harvest_control_prose(docs)
    by_line: dict[str, list[str]] = dict(word.get("by_line") or {})
    by_flow: dict[str, list[dict[str, Any]]] = dict(word.get("by_flow") or {})
    sources: list[str] = []
    for src in (word.get("sources") or {}).values():
        if src and src not in sources:
            sources.append(src)

    keys = sorted(set(by_line) | set(by_flow), key=_line_sort_key)
    sections = []
    for line in keys:
        paras = [p for p in (by_line.get(line) or []) if str(p or "").strip()]
        flow = list(by_flow.get(line) or [])
        if not flow:
            flow = [{"kind": "para", "text": p} for p in paras]
        title = line if line.startswith("轨道交通") else f"轨道交通{line}" if "号线" in line else line
        if "号线" in line and not line.startswith("轨道交通"):
            m = _LINE_RE.search(line)
            title = f"轨道交通{m.group(1)}号线" if m else line
        flow = _polish_control_flow(flow)
        flow = filter_flow(
            flow,
            kind="control",
            context=f"第3.4节{title}管控措施，只要该线路怎么管，不要3.3状态区段清单",
        )
        paras = [
            str(x.get("text") or "")
            for x in flow
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ] or paras
        if not paras and not any(x.get("kind") in {"para", "table"} for x in flow):
            continue
        src = str((word.get("sources") or {}).get(line) or "、".join(sources))
        sections.append(
            {
                "title": title,
                "paras": paras,
                "empty": False,
                "source": src,
                "fill": {
                    "paras": paras,
                    "flow": flow,
                    "source": src,
                    "empty": False,
                },
            }
        )
    return {"sections": sections, "source": "、".join(sources)}


def backfill_controls_from_status_notes(
    ctrl: dict[str, Any],
    status: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """3.4 专节缺线或只剩一句备件时，用 3.3 表后已抽取的集中修/大修/没有C和D 补全，不编数字。"""
    from chapters.overhead.line_notes import ctrl_suffix_from_note, note_asserts_no_cd, paragraphs_to_line_notes

    extras: dict[str, list[str]] = {}
    no_cd: dict[str, bool] = {}
    for hit in (status or {}).values():
        paras = [
            str(x.get("text") or "")
            for x in (hit.get("flow") or [])
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        line_map, _ = paragraphs_to_line_notes(paras)
        for key, text in line_map.items():
            if note_asserts_no_cd(text):
                no_cd[key] = True
            extra = ctrl_suffix_from_note(text)
            if not extra:
                continue
            bag = extras.setdefault(key, [])
            seen = {compact_text(x) for x in bag}
            for p in extra.split("\n"):
                c = compact_text(p)
                if c and c not in seen:
                    seen.add(c)
                    bag.append(p)

    sections = list(ctrl.get("sections") or [])
    by_key: dict[str, dict[str, Any]] = {}
    for sec in sections:
        m = _LINE_RE.search(str(sec.get("title") or ""))
        if m:
            by_key[m.group(1)] = sec

    for n in range(1, 19):
        key = str(n)
        line = f"{n}号线"
        sec = by_key.get(key)
        old_flow = list((sec or {}).get("fill", {}).get("flow") or (sec or {}).get("flow") or [])
        tables = [x for x in old_flow if x.get("kind") == "table"]
        extra = list(extras.get(key) or [])
        paras = [p for p in list((sec or {}).get("paras") or []) if str(p or "").strip()]
        blob = compact_text("\n".join(paras))
        thin = (not paras) or (
            len(paras) <= 2 and "集中修" not in blob and "大修更新" not in blob and "大修需求" not in blob
        )
        if extra and thin:
            for p in extra:
                if compact_text(p) not in blob:
                    paras.append(p)
                    blob = compact_text("\n".join(paras))
        if not paras and no_cd.get(key):
            paras = [f"{line}没有C和D状态的区段，维持现有管控措施。"]
        if not paras and not tables:
            continue
        src = str((sec or {}).get("source") or "表后说明")
        paras = renumber_continued_list_paras(paras)
        flow = [{"kind": "para", "text": p} for p in paras] + tables
        fill = {
            "paras": paras,
            "flow": flow,
            "source": src,
            "empty": False,
        }
        if sec is None:
            sections.append(
                {
                    "title": f"轨道交通{line}",
                    "paras": paras,
                    "empty": False,
                    "source": src,
                    "fill": fill,
                }
            )
        else:
            sec["paras"] = paras
            sec["empty"] = False
            sec["fill"] = fill
    sections.sort(key=lambda s: _line_sort_key(str(s.get("title") or "")))
    out = dict(ctrl or {})
    out["sections"] = sections
    return out


def _line_sort_key(line: str) -> tuple[int, str]:
    m = _LINE_RE.search(line or "")
    if m:
        return (int(m.group(1)), line)
    return (99, line or "")


def _is_overhead_inventory_table(rows: list[list[str]] | None, name: str = "") -> bool:
    """第 9 章只要物料/安全库存表，不要把柔性锚段台账整表当备件。"""
    if not rows or len(rows) < 2 or len(rows) > 80:
        return False
    head = "".join(str(c or "") for r in rows[:2] for c in r)
    if "物料名称" not in head and "备件名称" not in head:
        return False
    if not any(k in head for k in ("安全库存", "规格型号", "型号规格", "库存数量", "备件")):
        return False
    if "评价" in head and any(k in head for k in ("锚段", "承力索", "汇流排")):
        return False
    sample = head + "".join(str(c or "") for r in rows[:6] for c in r)
    if any(k in sample for k in ("触网", "接触网", "接触轨", "柔性接触网", "刚性接触网")):
        return True
    return any(k in (name or "") for k in ("接触网", "触网", "备件", "库存"))


def extract_overhead_stock(docs: list[DocumentModel]) -> dict[str, Any]:
    """第 9 章：触网安全库存表。规定 PDF 里的触网表可用；综保/变电表丢掉。"""
    from chapters.overhead.section_bundle import doc_recency_key, sort_docs_newest_last

    hits: list[dict[str, Any]] = []
    for doc, idx in sort_docs_newest_last(docs or []):
        name = _src(doc)
        flow: list[dict[str, Any]] = []
        for block in doc.blocks or []:
            if block.type != "table" or not block.rows:
                continue
            if not _is_overhead_inventory_table(block.rows, name):
                continue
            kind = _stock_table_kind(block.rows)
            # 供电库存表丢掉；文件名已点名触网的备件表留下（表里常写接触线、不一定写「接触网」）
            if kind == "power" and not any(k in name for k in ("接触网", "触网", "接触轨")):
                continue
            flow.append(_table_item(block, doc))
            if len(flow) >= 40:
                break
        if not flow:
            continue
        prefer = any(k in name for k in ("接触网", "触网", "备件", "库存管理规定"))
        rec = doc_recency_key(doc, idx)
        hits.append(
            {
                "source": name,
                "table": flow[0]["rows"],
                "flow": flow,
                "empty": False,
                "_prefer": prefer,
                "_n": len(flow),
                "_recency": rec,
            }
        )
    if not hits:
        return {"source": "", "table": [], "flow": [], "empty": True}
    hits.sort(key=lambda x: (x.get("_prefer") or False, x.get("_recency") or (0, 0, 0), x.get("_n") or 0))
    best = hits[-1]
    return {
        "source": best["source"],
        "table": best["table"],
        "flow": best["flow"],
        "empty": False,
    }


def _looks_like_plan_table(rows: list[list[str]] | None) -> bool:
    if not rows or len(rows) < 3:
        return False
    head = "".join(str(c or "") for c in (rows[0] or []))
    return "计划数量" in head and ("完成率" in head or "完成数量" in head)


def _plan_table_has_numbers(rows: list[list[str]] | None) -> bool:
    for row in (rows or [])[1:]:
        if any(re.search(r"\d", str(c or "")) for c in (row or [])[2:7]):
            return True
    return False


def _plan_line_count(rows: list[list[str]] | None) -> int:
    n = 0
    for row in (rows or [])[1:]:
        if any("号线" in str(c or "") for c in (row or [])):
            n += 1
    return n


def _looks_like_plan_continuation(rows: list[list[str]] | None, ncols: int) -> bool:
    """续表：无新表头，行里仍是线路数字。"""
    if not rows:
        return False
    head = "".join(str(c or "") for c in (rows[0] or []))
    if "计划数量" in head:
        return False
    if any("号线" in str(c or "") for c in (rows[0] or [])):
        return True
    first = str((rows[0] or [""])[0] or "").strip()
    return first.isdigit() and len(rows[0]) >= max(3, ncols - 1)


def extract_overhead_plan_table(docs: list[DocumentModel]) -> dict[str, Any]:
    """7.2.1：线路最多的「触网生产计划」表；后面续表一并收。变电表、空表丢掉。"""
    from chapters.overhead.section_bundle import doc_recency_key, sort_docs_newest_last

    best: dict[str, Any] | None = None
    best_key: tuple | None = None
    for doc, idx in sort_docs_newest_last(docs or []):
        caption = ""
        blocks = list(doc.blocks or [])
        for bi, block in enumerate(blocks):
            t = (block.text or "").strip()
            if block.type in {"paragraph", "heading"} and t:
                if "生产计划" in compact_text(t) and len(compact_text(t)) < 48:
                    caption = t
                continue
            if block.type != "table" or not block.rows:
                continue
            cap = compact_text(caption)
            if "变电" in cap and "触网" not in cap:
                continue
            if "触网" not in cap:
                continue
            if not _looks_like_plan_table(block.rows) or not _plan_table_has_numbers(block.rows):
                continue
            extra = []
            ncols = len(block.rows[0])
            for nxt in blocks[bi + 1 :]:
                if nxt.type in {"paragraph", "heading"} and (nxt.text or "").strip():
                    nt = compact_text(nxt.text or "")
                    if len(nt) < 48 and ("生产计划" in nt or nt.startswith("表")):
                        break
                    if len(nt) >= 24:
                        break
                    continue
                if nxt.type != "table" or not nxt.rows:
                    continue
                if not _looks_like_plan_continuation(nxt.rows, ncols):
                    break
                extra.append(nxt)
            all_rows = list(block.rows)
            for nxt in extra:
                all_rows.extend(nxt.rows)
            n_lines = _plan_line_count(all_rows)
            rec = doc_recency_key(doc, idx)
            key = (n_lines, len(all_rows), rec[1], rec[0], rec[2])
            if best is None or key > best_key:
                best_key = key
                flow = []
                if caption:
                    flow.append({"kind": "para", "text": caption})
                flow.append(_table_item(block, doc))
                for nxt in extra:
                    flow.append(_table_item(nxt, doc))
                best = {
                    "source": _src(doc),
                    "table": all_rows,
                    "flow": flow,
                    "empty": False,
                }
    return best or {"source": "", "table": [], "flow": [], "empty": True}


def _control_style_paras(prior_docs: list[DocumentModel] | None) -> list[str]:
    """3.4 表3-9 之后的 A/B/C/D 管控口径，用去年体例，不拿去年表数字。"""
    from chapters.overhead.ch3_status import extract_chapter_body_section

    hit = extract_chapter_body_section(
        prior_docs,
        chapter_h1=CHAPTER_NAMES["ch3"],
        start_keys=("各线路管控措施",),
        stop_keys=("轨道交通1号线", "评估小结", "和20"),
    )
    out: list[str] = []
    for item in hit.get("flow") or []:
        if item.get("kind") != "para":
            continue
        t = str(item.get("text") or "").strip()
        if not t or t.startswith("表") or t.startswith("触网包括"):
            continue
        if t.startswith("对于设备或子系统状态") or t.startswith("结合各线路上述"):
            out.append(t)
    return out


def _fill(paras=None, flow=None, table=None, source="", sections=None) -> dict[str, Any]:
    flow = dedupe_flow_items(list(flow or []))
    paras = dedupe_texts([str(p).strip() for p in (paras or []) if str(p).strip()])
    if flow:
        mirrored = {
            compact_text(str(x.get("text") or ""))
            for x in flow
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        }
        if mirrored:
            paras = [p for p in paras if compact_text(p) not in mirrored]
    table = table or []
    sections = sections or []
    empty = not (
        paras
        or (table and len(table) > 1)
        or any(x.get("kind") in {"table", "drawing", "formula", "para"} for x in flow)
        or any(not s.get("empty") for s in sections)
    )
    return {
        "paras": paras,
        "flow": flow,
        "table": table,
        "sections": sections,
        "source": source or "",
        "empty": empty,
    }


def _slice_fill(docs, start_keys, stop_keys) -> dict[str, Any]:
    hit = slice_named_section(docs, start_keys=start_keys, stop_keys=stop_keys)
    return _fill(paras=hit.get("paras"), flow=hit.get("flow"), source=hit.get("source") or "")


def _exact_title_fill_map(fills: dict[str, dict[str, Any]], outline: list[dict[str, Any]]) -> None:
    """只按标题全文（去空白）精确挂载，禁止模糊串台。"""
    by_compact = {
        compact_text(k): v
        for k, v in fills.items()
        if k and (not str(k)[0].isdigit() or "年" in str(k))
    }
    for node in outline:
        title = str(node.get("title") or "")
        c = compact_text(title)
        fill = by_compact.get(c)
        if fill is None:
            # 允许节号键
            fill = fills.get(str(node.get("num") or ""))
        if fill and not fill.get("empty"):
            node["fill"] = fill
            node["empty"] = False
        else:
            node["empty"] = int(node.get("depth") or 0) > 0
            if "fill" in node and (node["fill"] or {}).get("empty", True):
                node.pop("fill", None)


def _chapter_fills(
    docs: list[DocumentModel],
    chapter_id: str,
    year: int,
    prior_docs: list[DocumentModel] | None = None,
    outline: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """标题 → fill。专用抽取优先，其余按目录从材料逐节查找。"""
    fills: dict[str, dict[str, Any]] = {}

    if chapter_id == "ch3":
        from chapters.overhead.ch3_status import extract_status_distribution, fill_ch3_method_standard

        # 3.1 / 3.2：材料 → 去年 → 2025保底
        for title, hit in fill_ch3_method_standard(docs, prior_docs).items():
            if hit and not hit.get("empty"):
                fills[title] = _fill(
                    paras=hit.get("paras"),
                    flow=hit.get("flow"),
                    source=hit.get("source") or "",
                )

        # 3.3 本体不灌总表；五类状态分布从线路报告表合并填入子节
        status = extract_status_distribution(docs, prior_docs=prior_docs)
        for title, hit in status.items():
            fill = _fill(
                paras=hit.get("paras"),
                flow=hit.get("flow"),
                table=hit.get("table"),
                source=hit.get("source") or "",
            )
            warns = list(hit.get("warnings") or [])
            if warns:
                fill["warnings"] = warns
                fill["material_conflict"] = True
            fills[title] = fill

        # 对比节：优先两年系统状态表；没有再切段落（排除第4章故障次数对照）
        from chapters.overhead.excel_status import extract_year_compare_table

        cmp_tbl = extract_year_compare_table(docs, year=year, prior_docs=prior_docs)
        fills[f"和{year - 1}年评估对比结果"] = _fill(
            paras=cmp_tbl.get("paras"),
            flow=cmp_tbl.get("flow"),
            table=cmp_tbl.get("table"),
            source=cmp_tbl.get("source") or "",
        )

        ctrl = extract_overhead_controls(docs)
        ctrl = backfill_controls_from_status_notes(ctrl, status)
        from chapters.overhead.excel_status import (
            SYSTEM_CAPTION,
            TABLE_3_9_LEAD,
            align_system_table_to_prior,
            extract_system_volume_table,
        )

        vol = extract_system_volume_table(docs)
        ctrl_flow: list[dict[str, Any]] = []
        ctrl_source = ctrl.get("source") or ""
        if vol and not vol.get("empty") and vol.get("table"):
            table39 = align_system_table_to_prior(vol["table"], prior_docs)
            ctrl_flow.append({"kind": "para", "text": TABLE_3_9_LEAD})
            ctrl_flow.append({"kind": "para", "text": SYSTEM_CAPTION})
            ctrl_flow.append({"kind": "table", "rows": table39, "force_rebuild": True})
            if vol.get("source"):
                ctrl_source = "；".join(s for s in (vol.get("source"), ctrl_source) if s)
        style_paras = _control_style_paras(prior_docs)
        for p in style_paras:
            ctrl_flow.append({"kind": "para", "text": p})
        if ctrl.get("sections") or ctrl_flow:
            fills["各线路管控措施"] = _fill(
                paras=[x.get("text") or "" for x in ctrl_flow if x.get("kind") == "para"],
                flow=ctrl_flow,
                sections=ctrl.get("sections") or [],
                source=ctrl_source,
            )
            fills["_control_children"] = ctrl  # type: ignore

    elif chapter_id == "ch4":
        from chapters.overhead.line_topics import (
            LINE_TOPIC_KEYS,
            extract_topic_line_sections,
            harvest_fault_trend_paras,
            harvest_kilometre_paras,
            merge_line_sections,
            scrub_fault_trend_sections,
            sections_from_line_paras,
        )

        change = harvest_kilometre_paras(docs, change_only=True)
        if change and not change.get("empty"):
            fills["设备体量变化情况"] = _fill(
                paras=change.get("paras"),
                flow=change.get("flow"),
                source=change.get("source") or "",
            )
        qty = harvest_kilometre_paras(docs, change_only=False)
        if qty and not qty.get("empty"):
            fills["设备数量"] = _fill(
                paras=qty.get("paras"),
                flow=qty.get("flow"),
                source=qty.get("source") or "",
            )
        trend_keys = LINE_TOPIC_KEYS.get("各线路接触网故障趋势分析") or ("各线路接触网故障趋势分析",)
        topic = extract_topic_line_sections(docs, start_keys=trend_keys)
        fault = harvest_fault_trend_paras(docs)
        leftover, fault_secs = sections_from_line_paras(fault.get("paras") or [], fault.get("source") or "")
        if fault.get("sections"):
            fault_secs = list(fault.get("sections") or [])
        topic_secs = scrub_fault_trend_sections(topic.get("sections") or [])
        fault_secs = scrub_fault_trend_sections(fault_secs)
        # 扫句袋按材料顺序；专节切开的句子只补缺，不把期间汇总提到典型故障前面。
        secs = merge_line_sections(topic_secs, fault_secs)
        leftover = [p for p in leftover if p and not compact_text(p).startswith("评估围绕")]
        if secs:
            src = topic.get("source") or fault.get("source") or ""
            fills["各线路接触网故障趋势分析"] = _fill(sections=secs, source=src)
            fills["_lines_各线路接触网故障趋势分析"] = {"sections": secs}
        elif leftover:
            fills["各线路接触网故障趋势分析"] = _fill(
                paras=leftover,
                flow=[{"kind": "para", "text": p} for p in leftover],
                source=fault.get("source") or "",
            )

        cmp_key = f"和{year - 1}年评估对比结果"
        now_cmp = harvest_fault_year_compare(docs, year=year)
        if now_cmp and not now_cmp.get("empty"):
            fills[cmp_key] = _fill(flow=now_cmp.get("flow"), source=now_cmp.get("source") or "")

    if chapter_id == "ch7":
        from chapters.overhead.ch7_quality import (
            CH7_QUALITY_LEAD,
            extract_overhead_ch7_aspects,
            extract_overhead_org,
            retitle_ch7_plan_captions,
        )

        plan = extract_overhead_plan_table(docs)
        if plan and not plan.get("empty") and (plan.get("table") or plan.get("flow")):
            flow = []
            for item in plan.get("flow") or []:
                new_item = dict(item)
                if new_item.get("kind") == "para":
                    new_item["text"] = retitle_ch7_plan_captions(str(new_item.get("text") or ""))
                flow.append(new_item)
            fills["日常维修计划执行情况"] = _fill(
                flow=flow,
                table=plan.get("table"),
                source=plan.get("source") or "",
            )
        org = extract_overhead_org(docs, prior_docs)
        if org and not org.get("empty"):
            fills["生产组织模式"] = _fill(
                flow=org.get("flow"),
                source=org.get("source") or "",
            )
        aspects = extract_overhead_ch7_aspects(docs)
        if any(
            hit and not hit.get("empty")
            for key, hit in aspects.items()
            if not str(key).startswith("_")
        ):
            old_lead = "".join(str(x.get("text") or "") for x in ((fills.get("设施设备运维质量分析") or {}).get("flow") or []))
            if any(k in old_lead for k in ("维保管理", "新线路接管", "故障处理流程")) or not old_lead.strip():
                fills["设施设备运维质量分析"] = _fill(
                    flow=[{"kind": "para", "text": CH7_QUALITY_LEAD}],
                    source="",
                )
        for key, hit in aspects.items():
            if hit and not hit.get("empty"):
                if str(key).startswith("_lines_"):
                    fills[key] = hit
                else:
                    fills[key] = _fill(
                        flow=hit.get("intro"),
                        source=hit.get("source") or "",
                        sections=hit.get("sections") or [],
                    )

    elif chapter_id == "ch9":
        from chapters.overhead.ch9_11 import extract_overhead_ch9

        for key, hit in extract_overhead_ch9(docs, prior_docs).items():
            if hit and not hit.get("empty"):
                fills[key] = hit

    elif chapter_id == "ch11":
        from chapters.overhead.ch9_11 import harvest_overhead_tools_v2
        from chapters.overhead.line_topics import harvest_overhead_retire

        year_title = f"{year}年设备退运更换情况"
        ret = harvest_overhead_retire(docs, year)
        if ret and not ret.get("empty"):
            fills[year_title] = _fill(
                flow=ret.get("intro"),
                sections=ret.get("sections") or [],
                source=ret.get("source") or "",
            )
        tools = harvest_overhead_tools_v2(docs)
        if tools and not tools.get("empty"):
            fills["固定资产工器具配置情况"] = _fill(
                paras=tools.get("paras"),
                flow=tools.get("flow"),
                source="",
            )

    from chapters.overhead.line_topics import LINE_TOPIC_KEYS, extract_event_sections, extract_topic_line_sections

    wanted_topics: tuple[str, ...] = ()
    if chapter_id == "ch4":
        wanted_topics = ()
    elif chapter_id == "ch7":
        wanted_topics = ()
    elif chapter_id == "ch10":
        wanted_topics = ("各线路环境符合性评估",)
    for title in wanted_topics:
        keys = LINE_TOPIC_KEYS.get(title) or (title,)
        hit = extract_topic_line_sections(docs, start_keys=keys)
        existing = fills.get(title)
        if hit.get("sections") and (not existing or existing.get("empty")):
            fills[title] = _fill(
                flow=hit.get("intro"),
                source=hit.get("source") or "",
                sections=hit["sections"],
            )
            fills[f"_lines_{title}"] = hit  # type: ignore
        elif hit.get("sections"):
            fills.setdefault(f"_lines_{title}", hit)  # type: ignore
        elif hit.get("intro") and (not existing or existing.get("empty")):
            fills[title] = _fill(flow=hit.get("intro"), source=hit.get("source") or "")

    if chapter_id == "ch8":
        ev = extract_event_sections(docs)
        if ev and not ev.get("empty"):
            fills["设施设备年度突出事件分析"] = _fill(
                flow=ev.get("intro"),
                sections=ev.get("sections"),
                source=ev.get("source") or "",
            )
            fills["_event_children"] = ev  # type: ignore

    from chapters.overhead.outline_fill import fill_missing_outline_sections

    if chapter_id == "ch6":
        from chapters.overhead.ch6_revision import extract_overhead_ch6

        for key, hit in extract_overhead_ch6(docs, year).items():
            if hit and not hit.get("empty"):
                fills[key] = hit

    fills = fill_missing_outline_sections(
        docs,
        list(outline or []),
        prior_docs,
        fills,
        chapter_id=chapter_id,
        year=year,
    )
    if chapter_id == "ch6":
        from chapters.overhead.ch6_revision import apply_ch6_layout

        fills = apply_ch6_layout(fills, year=year)
    if chapter_id == "ch9":
        from chapters.overhead.ch9_11 import apply_ch9_layout, extract_overhead_ch9

        fills = apply_ch9_layout(fills)
        ch9_hits = extract_overhead_ch9(docs, prior_docs)
        for key, hit in ch9_hits.items():
            if hit and not hit.get("empty"):
                fills[key] = hit
        if "接触网安全库存备品备件" not in ch9_hits:
            fills["接触网安全库存备品备件"] = {
                "paras": [],
                "flow": [],
                "table": [],
                "sections": [],
                "source": "",
                "empty": True,
            }
        fills = apply_ch9_layout(fills)
    if chapter_id == "ch10":
        from chapters.overhead.ch9_11 import (
            apply_ch10_parent_cleanup,
            backfill_env_lines,
            extract_ch10_lead,
            prefer_network_dust,
        )

        fills = apply_ch10_parent_cleanup(fills)
        fills = prefer_network_dust(fills, docs)
        lead = extract_ch10_lead(docs) or extract_ch10_lead(prior_docs)
        if lead:
            fills["环境差异性评估"] = lead
        env_key = "各线路环境符合性评估"
        env_hit = fills.get(f"_lines_{env_key}")
        if not isinstance(env_hit, dict):
            env_hit = {"sections": [], "intro": [], "empty": True}
        env_hit = backfill_env_lines(env_hit, docs)
        fills[f"_lines_{env_key}"] = env_hit  # type: ignore
        if env_hit.get("sections"):
            fills[env_key] = _fill(sections=env_hit["sections"], source="")
    if chapter_id == "ch11":
        from chapters.overhead.ch9_11 import apply_ch11_layout

        fills = apply_ch11_layout(fills, docs, year)
    return fills


def extract_chapter(
    docs: list[DocumentModel],
    *,
    year: int,
    chapter_id: str,
    prior_docs: list[DocumentModel] | None = None,
    prior_via: str = "",
    use_llm: bool | None = None,
) -> dict[str, Any]:
    from chapters.common.source_yellow import register_current_docs
    from chapters.overhead.llm_gate import using_llm

    prepared = prepare_overhead_docs(docs)
    register_current_docs(prepared)
    via = (prior_via or "").strip()
    if not via:
        if not prior_docs:
            via = "baseline_2025"
        elif all(str(d.source_name or "").startswith("项目保底") for d in prior_docs):
            via = "baseline_2025"
        else:
            via = "upload"
    outline = resolve_chapter_outline(prior_docs, chapter_id, year=year, prior_via=via)
    with using_llm(use_llm):
        fills = _chapter_fills(prepared, chapter_id, year, prior_docs=prior_docs, outline=outline)

    _exact_title_fill_map(fills, outline)

    # 管控措施 / 退运：材料线路挂到父节下
    ctrl = fills.get("_control_children")
    if isinstance(ctrl, dict) and ctrl.get("sections"):
        outline = insert_content_children(
            outline,
            parent_title_key="各线路管控措施",
            children=ctrl["sections"],
        )
    year_title = f"{year}年设备退运更换情况"
    retire_fill = fills.get(year_title)
    if chapter_id != "ch11" and retire_fill and retire_fill.get("sections"):
        outline = insert_content_children(
            outline,
            parent_title_key="年设备退运更换情况",
            children=retire_fill["sections"],
        )
    for key, hit in list(fills.items()):
        if not str(key).startswith("_lines_") or not isinstance(hit, dict):
            continue
        title = str(key)[len("_lines_") :]
        if hit.get("sections"):
            outline = insert_content_children(
                outline,
                parent_title_key=title,
                children=hit["sections"],
            )
    ev = fills.get("_event_children")
    if isinstance(ev, dict) and ev.get("sections"):
        outline = insert_content_children(
            outline,
            parent_title_key="设施设备年度突出事件分析",
            children=ev["sections"],
        )

    warnings: list[str] = []
    if not prepared:
        warnings.append("未识别到接触网可用材料（纯供电稿已跳过）")

    return {
        "year": year,
        "chapter_id": chapter_id,
        "domain_id": "overhead",
        "chapter_name": CHAPTER_NAMES.get(chapter_id) or "",
        "outline": outline,
        "fills": {k: v for k, v in fills.items() if not str(k).startswith("_")},
        "warnings": warnings,
        "line_results": [],
        "prior_outline_count": len(outline),
    }


def chapter_has_content(pack: dict[str, Any]) -> bool:
    for node in pack.get("outline") or []:
        fill = node.get("fill") or {}
        if fill and not fill.get("empty"):
            return True
    for key, fill in (pack.get("fills") or {}).items():
        if str(key).startswith("_"):
            continue
        if fill and not fill.get("empty"):
            return True
    return False
