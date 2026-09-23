# -*- coding: utf-8 -*-
"""触网材料合并：默认最新文件；最新缺项/全 0/空说明时从其他材料补全，并记录引自哪份文件。"""
from __future__ import annotations

import re
from typing import Any, Callable

from chapters.common.section_slice import compact_text
from chapters.overhead.line_notes import (
    attach_negative_cd_clauses,
    status_note_suffix_from_note,
    negative_cd_sentences,
    note_asserts_no_cd,
    note_has_body,
    note_has_cd_status,
    note_lists_positive_c,
)


_OH_SPECIALTY = ("接触网", "触网", "接触轨")


def _recency_key(item: dict[str, Any]) -> tuple[float, float, int]:
    return (
        float(item.get("_recency") or 0),
        float(item.get("_pack") or 0),
        int(item.get("_idx") or 0),
    )


def _table_blob(rows: list[list[str]] | None) -> str:
    return compact_text("".join(str(c) for row in (rows or []) for c in row))


def table_is_power_specialty(rows: list[list[str]] | None) -> bool:
    """规程/企标表：专业列只有供电、没有触网。"""
    blob = _table_blob(rows)
    if not blob:
        return False
    if any(k in blob for k in _OH_SPECIALTY):
        return False
    return "供电专业" in blob


def table_has_overhead_specialty(rows: list[list[str]] | None) -> bool:
    blob = _table_blob(rows)
    return any(k in blob for k in _OH_SPECIALTY)


def _is_table_glue(item: dict[str, Any]) -> bool:
    if item.get("kind") != "para":
        return False
    t = str(item.get("text") or "").strip()
    if not t or len(t) >= 90:
        return False
    if t[0] == "表" and len(t) > 1 and (t[1].isdigit() or t[1] in " ：:-"):
        return True
    return "如表" in t


def _is_figure_glue(item: dict[str, Any]) -> bool:
    if item.get("kind") != "para":
        return False
    t = str(item.get("text") or "").strip()
    if not t or len(t) >= 90:
        return False
    return "如图" in t or (t[0] == "图" and len(t) > 1 and (t[1].isdigit() or t[1] in " ：:-"))


def strip_power_specialty_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """触网小节：去掉供电专业规程表及其题注。清单行按材料原样保留。"""
    out: list[dict[str, Any]] = []
    items = list(flow or [])
    i = 0
    while i < len(items):
        item = items[i]
        kind = item.get("kind")
        if kind == "table" and table_is_power_specialty(item.get("rows")):
            while out and _is_table_glue(out[-1]):
                out.pop()
            i += 1
            continue
        out.append(item)
        i += 1
    return out


def sanitize_overhead_bundle_hit(hit: dict[str, Any] | None) -> dict[str, Any]:
    if not hit:
        return {"paras": [], "flow": [], "source": "", "empty": True}
    flow = strip_power_specialty_flow(hit.get("flow") or [])
    out = dict(hit)
    out["flow"] = flow
    out["paras"] = [
        str(x.get("text") or "")
        for x in flow
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ]
    if table_is_power_specialty(out.get("table")):
        out["table"] = []
    out["empty"] = not (
        out["paras"]
        or any(x.get("kind") in {"table", "drawing", "formula"} for x in flow)
        or (out.get("table") and len(out.get("table") or []) > 1)
    )
    return out


def _hit_rank(hit: dict[str, Any]) -> tuple:
    """触网专表优先于上传时间，避免较新的供电合订稿盖掉触网表。"""
    flow = hit.get("flow") or []
    n_oh = sum(1 for x in flow if x.get("kind") == "table" and table_has_overhead_specialty(x.get("rows")))
    n_pw = sum(1 for x in flow if x.get("kind") == "table" and table_is_power_specialty(x.get("rows")))
    n_draw = sum(1 for x in flow if x.get("kind") == "drawing")
    recency, pack, idx = _recency_key(hit)
    return (n_oh, -n_pw, n_draw, recency, pack, idx)


def _drawing_cluster(flow: list[dict[str, Any]], drawing: dict[str, Any]) -> list[dict[str, Any]]:
    idx = -1
    for i, item in enumerate(flow):
        if item is drawing:
            idx = i
            break
        if (
            item.get("kind") == "drawing"
            and item.get("source_index") == drawing.get("source_index")
            and str(item.get("source_path") or "") == str(drawing.get("source_path") or "")
        ):
            idx = i
            break
    if idx < 0:
        return [drawing]
    out: list[dict[str, Any]] = []
    if idx > 0 and _is_figure_glue(flow[idx - 1]):
        out.append(flow[idx - 1])
    out.append(flow[idx])
    if idx + 1 < len(flow) and _is_figure_glue(flow[idx + 1]) and str(flow[idx + 1].get("text") or "").startswith("图"):
        out.append(flow[idx + 1])
    return out


def _hit_table_before_drawing(hit: dict[str, Any]) -> bool | None:
    kinds = [x.get("kind") for x in (hit.get("flow") or []) if x.get("kind") in {"table", "drawing"}]
    if "table" not in kinds or "drawing" not in kinds:
        return None
    return kinds.index("table") < kinds.index("drawing")


def _tables_before_drawings(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """源稿表在图前时，合并后也保持表→图，不把补进来的图插到段首。"""
    head: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    i = 0
    items = list(flow)
    while i < len(items):
        item = items[i]
        if item.get("kind") == "drawing":
            if i > 0 and _is_figure_glue(items[i - 1]) and head and head[-1] is items[i - 1]:
                figures.append(head.pop())
            figures.append(item)
            if i + 1 < len(items) and _is_figure_glue(items[i + 1]) and str(items[i + 1].get("text") or "").startswith("图"):
                figures.append(items[i + 1])
                i += 2
                continue
            i += 1
            continue
        head.append(item)
        i += 1
    return head + figures


def merge_overhead_bundle_hits(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """多份材料整段 bundle：触网专表优先，缺图/缺段从其他材料补；不把图插到段首。"""
    if not hits:
        return {"paras": [], "flow": [], "source": "", "empty": True}
    cleaned = [sanitize_overhead_bundle_hit(h) for h in hits]
    cleaned = [h for h in cleaned if h and not h.get("empty")]
    if not cleaned:
        return {"paras": [], "flow": [], "source": "", "empty": True}
    split_across = False
    if cleaned:
        has_tbl = any(any(x.get("kind") == "table" for x in (h.get("flow") or [])) for h in cleaned)
        has_drw = any(any(x.get("kind") == "drawing" for x in (h.get("flow") or [])) for h in cleaned)
        both_in_one = any(
            any(x.get("kind") == "table" for x in (h.get("flow") or []))
            and any(x.get("kind") == "drawing" for x in (h.get("flow") or []))
            for h in cleaned
        )
        split_across = has_tbl and has_drw and not both_in_one
    prefer_table_first = any(_hit_table_before_drawing(h) is True for h in hits) or split_across
    ordered = sorted(cleaned, key=_hit_rank)
    newest = ordered[-1]
    flow: list[dict[str, Any]] = list(newest.get("flow") or [])
    newest_has_oh_table = any(
        x.get("kind") == "table" and table_has_overhead_specialty(x.get("rows"))
        for x in flow
    )
    seen_para = {compact_text(str(x.get("text") or "")) for x in flow if x.get("kind") == "para"}
    seen_table = {compact_text(str(x.get("rows") or "")) for x in flow if x.get("kind") == "table"}
    sources: list[str] = []
    primary = str(newest.get("_source") or newest.get("source") or "")
    if primary:
        sources.append(primary)
    for h in reversed(ordered[:-1]):
        src = str(h.get("_source") or h.get("source") or "")
        src_flow = list(h.get("flow") or [])
        before = len(flow)
        for item in src_flow:
            kind = item.get("kind")
            if kind == "para":
                if newest_has_oh_table:
                    continue
                c = compact_text(str(item.get("text") or ""))
                if c and c not in seen_para:
                    seen_para.add(c)
                    flow.append(item)
            elif kind == "table":
                if newest_has_oh_table:
                    continue
                from chapters.common.table_copy import is_cycle_maintain_table

                if is_cycle_maintain_table(item.get("rows")) and any(
                    is_cycle_maintain_table(x.get("rows")) for x in flow if x.get("kind") == "table"
                ):
                    continue
                sig = compact_text(str(item.get("rows") or ""))
                if sig and sig not in seen_table:
                    seen_table.add(sig)
                    flow.append(item)
            elif kind == "drawing" and not any(x.get("kind") == "drawing" for x in flow):
                for piece in _drawing_cluster(src_flow, item):
                    if piece.get("kind") == "para":
                        c = compact_text(str(piece.get("text") or ""))
                        if not c or c in seen_para:
                            continue
                        seen_para.add(c)
                    flow.append(piece)
        if src and len(flow) > before and src not in sources:
            sources.append(src)
    if prefer_table_first and any(x.get("kind") == "table" for x in flow) and any(
        x.get("kind") == "drawing" for x in flow
    ):
        flow = _tables_before_drawings(flow)
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    src_out = primary
    if len(sources) > 1:
        src_out = f"主：{primary}；补：{'、'.join(sources[1:])}"
    return {
        "flow": flow,
        "paras": paras,
        "source": src_out,
        "empty": not paras and not any(x.get("kind") in {"table", "drawing"} for x in flow),
        "from_bundle": True,
    }


def newest_item(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not items:
        return None
    return max(items, key=_recency_key)


def merge_line_notes_backfill(
    items: list[dict[str, Any]],
    *,
    parse_paragraphs: Callable[[list[str]], tuple[dict[str, str], list[str]]],
) -> tuple[dict[str, str], list[str], list[str], dict[str, str]]:
    """同线路：较新且有正文 → 覆盖；较新只有空壳 → 保留较旧正文；冲突记 warnings。"""
    general_order: list[str] = []
    general_seen: set[str] = set()
    by_line: dict[str, str] = {}
    line_src: dict[str, str] = {}
    warnings: list[str] = []
    ordered = sorted(items, key=_recency_key)
    for item in ordered:
        src = str(item.get("_source") or item.get("source") or "").strip()
        paras = list(item.get("notes") or []) + list(item.get("paragraphs") or [])
        line_map, gens = parse_paragraphs(paras)
        for g in gens:
            c = compact_text(g)
            if c and c not in general_seen:
                general_seen.add(c)
                general_order.append(g)
        for key, text in line_map.items():
            prev = by_line.get(key)
            if not note_has_body(text):
                if prev is None:
                    by_line[key] = text
                    line_src[key] = src
                continue
            if prev and note_has_body(prev) and compact_text(prev) != compact_text(text):
                warnings.append(f"{key}号线表后说明多份材料不一致，已采用较新文件表述")
                if note_has_cd_status(prev) and not note_has_cd_status(text):
                    extra = status_note_suffix_from_note(text)
                    if extra and compact_text(extra) not in compact_text(prev):
                        prev = prev.rstrip() + "\n" + extra
                    by_line[key] = prev
                    continue
                if note_asserts_no_cd(prev) and note_lists_positive_c(text) and not note_asserts_no_cd(text):
                    by_line[key] = prev
                    continue
                extra = status_note_suffix_from_note(prev)
                if extra:
                    new_c = compact_text(text)
                    extra_parts = [
                        p
                        for p in extra.split("\n")
                        if compact_text(p) and compact_text(p) not in new_c
                    ]
                    if extra_parts:
                        text = text.rstrip() + "\n" + "\n".join(extra_parts)
                text = attach_negative_cd_clauses(text, negative_cd_sentences(prev))
            by_line[key] = text
            line_src[key] = src
    # 再扫一遍：较新文件只有「N号线：」空壳时，从较旧材料补正文
    for item in ordered:
        src = str(item.get("_source") or item.get("source") or "").strip()
        paras = list(item.get("notes") or []) + list(item.get("paragraphs") or [])
        line_map, _ = parse_paragraphs(paras)
        for key, text in line_map.items():
            if not note_has_body(text):
                continue
            if not note_has_body(by_line.get(key) or ""):
                by_line[key] = text
                line_src[key] = src
    return by_line, general_order, warnings, line_src


def table_row_backfill_notes(
    line_src: dict[str, str],
    *,
    primary_source: str,
) -> list[str]:
    primary = compact_text(primary_source or "")
    out: list[str] = []
    for line_name, src in sorted(line_src.items(), key=lambda x: int(re.search(r"(\d+)", x[0]).group(1)) if re.search(r"(\d+)", x[0]) else (99, x[0])):
        s = str(src or "").strip()
        if not s or compact_text(s) == primary:
            continue
        out.append(f"{line_name}表格数据引自「{s}」（最新材料该行为空或全0，已从其他材料补全）")
    return out


def backfill_source_notes(
    line_src: dict[str, str],
    *,
    primary_source: str,
) -> list[str]:
    """非最新材料补上的线路，生成体例说明（写入 warnings，成文时标【材料差异】）。"""
    primary = compact_text(primary_source or "")
    out: list[str] = []
    for key in sorted(line_src, key=lambda x: int(x)):
        src = str(line_src.get(key) or "").strip()
        if not src or compact_text(src) == primary:
            continue
        out.append(f"{key}号线表后说明引自「{src}」（最新材料未提供完整表述）")
    return out
