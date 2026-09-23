# -*- coding: utf-8 -*-
"""接触网成文：标题严格按目录节点；有 fill 才写正文，否则只留黄标题。禁止编造。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from chapters.common.list_number import renumber_continued_list_flow, restart_list_after_prose_flow
from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts
from chapters.common.table_copy import collapse_cycle_maintain_tables
from chapters.common.number_logic import has_number_logic_issue, has_year_logic_issue
from chapters.common.word import (
    add_caption,
    add_cover,
    add_heading,
    add_para,
    get_assessment_year,
    new_report_document,
    set_assessment_year,
)
from chapters.overhead.style import ENV_LEAD, STOCK_LEAD


def _is_caption(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) >= 80 or t[0] not in {"图", "表"}:
        return False
    return t[1].isdigit() or t[1] in " -"


def _has_body(fill: dict[str, Any] | None) -> bool:
    if not fill or fill.get("empty"):
        return False
    if fill.get("paras"):
        return True
    if fill.get("table") and len(fill.get("table") or []) > 1:
        return True
    if fill.get("sections") and any(not s.get("empty") for s in fill["sections"]):
        return True
    flow = fill.get("flow") or []
    return any(x.get("kind") in {"para", "table", "drawing", "formula"} for x in flow)


def _fill_texts(fill: dict[str, Any] | None) -> list[str]:
    if not fill:
        return []
    texts: list[str] = []
    for item in fill.get("flow") or []:
        if isinstance(item, dict) and item.get("kind") == "para":
            t = str(item.get("text") or "").strip()
            if t:
                texts.append(t)
    if not texts:
        texts = [str(p or "").strip() for p in (fill.get("paras") or []) if str(p or "").strip()]
    return texts


def _logic_or_year(fill: dict[str, Any] | None) -> bool:
    """数字对不上或年份早于评估年：标题与句子一起黄。"""
    year = get_assessment_year()
    for t in _fill_texts(fill):
        if has_number_logic_issue(t) or has_year_logic_issue(t, year):
            return True
    return False


def _subtree_has_body(outline: list[dict[str, Any]], start: int) -> bool:
    """子节已有正文时，父标题不标黄（3.3/4.1/7.2 等容器节）。"""
    if start < 0 or start >= len(outline):
        return False
    depth = int(outline[start].get("depth") or 0)
    for j in range(start + 1, len(outline)):
        d = int(outline[j].get("depth") or 0)
        if d <= depth:
            break
        if _has_body(outline[j].get("fill")):
            return True
        if outline[j].get("content_child") and not outline[j].get("empty"):
            return True
    return False


def _write_flow(doc, flow: list[dict[str, Any]] | None, *, after_prose: bool = False) -> bool:
    wrote = False
    items = collapse_cycle_maintain_tables(dedupe_flow_items(flow))
    items = restart_list_after_prose_flow(items) if after_prose else renumber_continued_list_flow(items)
    for item in items:
        kind = item.get("kind")
        if kind == "para":
            t = (item.get("text") or "").strip()
            if t:
                if _is_caption(t):
                    add_caption(doc, t)
                else:
                    add_para(
                        doc,
                        t,
                        yellow=bool(item.get("yellow")),
                        source_yellow=bool(item.get("source_yellow")),
                    )
                wrote = True
        elif kind == "drawing":
            from chapters.common.drawings import copy_drawings_from_body_index

            path = str(item.get("source_path") or "")
            idx = int(item.get("source_index") or -1)
            if path and idx >= 0 and copy_drawings_from_body_index(path, idx, doc):
                wrote = True
        elif kind == "table" and item.get("rows"):
            from chapters.common.table_copy import write_table_item

            if write_table_item(doc, item, domain_id="overhead"):
                wrote = True
    return wrote


def _paras_not_in_flow(paras: list[str] | None, flow: list[dict[str, Any]] | None) -> list[str]:
    """slice / 保底切片的 paras 往往是 flow 段落的镜像，成文只写一遍。"""
    flow_texts = {
        compact_text(str(x.get("text") or ""))
        for x in (flow or [])
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    }
    if not flow_texts:
        return dedupe_texts(paras)
    out: list[str] = []
    for p in dedupe_texts(paras):
        if compact_text(p) not in flow_texts:
            out.append(p)
    return out


def _write_fill(doc, fill: dict[str, Any] | None) -> bool:
    if not _has_body(fill):
        return False
    assert fill is not None
    wrote = False
    flow = dedupe_flow_items(list(fill.get("flow") or []))
    extra_paras = _paras_not_in_flow(fill.get("paras"), flow)
    for p in extra_paras:
        t = str(p or "").strip()
        if not t:
            continue
        if _is_caption(t):
            add_caption(doc, t)
        else:
            add_para(doc, t)
        wrote = True
    if _write_flow(doc, flow, after_prose=bool(fill.get("_list_after_prose"))):
        wrote = True
    table = fill.get("table")
    if table and len(table) > 1 and not any(x.get("kind") == "table" for x in flow):
        from chapters.common.table_copy import write_table_item

        tbl_item: dict[str, Any] = {"kind": "table", "rows": table, "vmerge": fill.get("table_vmerge")}
        from chapters.overhead.ch3_status import is_status_distribution_table
        from chapters.overhead.style import status_table_widths

        if is_status_distribution_table(table):
            tbl_item["widths"] = status_table_widths(len(table[0]))
        if write_table_item(doc, tbl_item, domain_id="overhead"):
            wrote = True
    if fill.get("_children_promoted"):
        return wrote
    if fill.get("sections"):
        for sec in fill.get("sections") or []:
            if sec.get("content_child") or sec.get("empty"):
                continue
            sec_fill = sec.get("fill") or {
                "paras": sec.get("paras"),
                "flow": sec.get("flow"),
                "source": sec.get("source"),
                "empty": sec.get("empty"),
            }
            title = str(sec.get("title") or "").strip()
            if title:
                add_heading(doc, title, 3, (sec_fill or {}).get("source") or "", yellow=sec.get("empty", True))
            if _write_fill(doc, sec_fill):
                wrote = True
    return wrote


def write_chapter_docx(pack: dict[str, Any], path: str | Path, chapter_id: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = new_report_document()
    year = int(pack.get("year") or 2026)
    set_assessment_year(year)
    outline = pack.get("outline") or []
    chapter_name = pack.get("chapter_name") or (outline[0].get("title") if outline else chapter_id)
    no = int((chapter_id or "ch3").replace("ch", "") or 3)
    add_cover(doc, year=year, cover_line=f"第{no}章  {chapter_name}（接触网）")

    for i, node in enumerate(outline):
        depth = int(node.get("depth") or 0)
        level = int(node.get("level") or (1 + depth))
        num = str(node.get("num") or "")
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        event_child = chapter_id in {"ch8", "ch10", "ch11"} and bool(node.get("content_child"))
        heading = title if event_child else (
            f"{num}  {title}" if num and not title.startswith(num) else title
        )
        fill = node.get("fill")
        has = _has_body(fill)
        kids = _subtree_has_body(outline, i)
        is_summary = "评估小结" in title
        if is_summary:
            add_heading(doc, heading, min(level, 4), "", yellow=True)
            continue
        yellow = (depth > 0 and not has and not kids) or _logic_or_year(fill)
        src = ""
        if has:
            src = (fill or {}).get("source") or node.get("source") or ""
        add_heading(doc, heading, min(level, 4), src, yellow=yellow)

        if depth == 0:
            if has:
                _write_fill(doc, fill)
            continue
        if not has:
            if chapter_id == "ch9" and title == "接触网安全库存":
                add_para(doc, STOCK_LEAD)
            if chapter_id == "ch10" and title == "环境差异性评估":
                add_para(doc, ENV_LEAD)
            continue

        _write_fill(doc, fill)

    doc.save(str(path))
    return path
