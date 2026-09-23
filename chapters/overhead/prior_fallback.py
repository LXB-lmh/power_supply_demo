# -*- coding: utf-8 -*-
"""体例小节回退：材料 → 前端去年报告 → 2025保底（prior 已解析好）。

只回退用户点名的「可复用体例」节，不拿去年数据顶当年状态/故障数。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from chapters.overhead.ch3_status import extract_chapter_body_section
from chapters.overhead.material_merge import merge_overhead_bundle_hits, sanitize_overhead_bundle_hit
from chapters.overhead.section_bundle import doc_recency_key, extract_subsection_bundle, sort_docs_newest_last
from parsers.document_model import DocumentModel

FillFn = Callable[[list[DocumentModel] | None], dict[str, Any]]

_EXCLUSIVE_NEWEST = ("整改", "生产计划", "安全库存", "退运更换", "报废原因")
_DEPT_STEM = re.compile(r"维护[一二三四五六七八九十]+部")


def _exclusive_newest_keys(start_keys: tuple[str, ...]) -> bool:
    blob = "".join(start_keys)
    return any(k in blob for k in _EXCLUSIVE_NEWEST)


def _dept_stem(name: str) -> str:
    m = _DEPT_STEM.search(name or "")
    return m.group(0) if m else ""


def _keep_newest_per_dept(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同维护部门只留最新一份，避免 9.x 补充稿再被旧部门稿补段。"""
    best: dict[str, dict[str, Any]] = {}
    leftover: list[dict[str, Any]] = []
    for hit in hits:
        stem = _dept_stem(str(hit.get("_source") or hit.get("source") or ""))
        rec = (hit.get("_recency") or 0, hit.get("_pack") or 0, hit.get("_idx") or 0)
        if not stem:
            leftover.append(hit)
            continue
        prev = best.get(stem)
        prev_rec = (
            (prev.get("_recency") or 0, prev.get("_pack") or 0, prev.get("_idx") or 0)
            if prev
            else None
        )
        if prev_rec is None or rec > prev_rec:
            best[stem] = hit
    return leftover + list(best.values())


def _nonempty(hit: dict[str, Any] | None) -> bool:
    if not hit or hit.get("empty"):
        return False
    if hit.get("paras") or hit.get("flow") or (hit.get("table") and len(hit.get("table") or []) > 1):
        return True
    if hit.get("sections") and any(not s.get("empty") for s in hit["sections"]):
        return True
    return False


def mark_fallback(hit: dict[str, Any]) -> dict[str, Any]:
    out = dict(hit)
    src = (out.get("source") or "").strip()
    if src and "体例回退" not in src:
        out["source"] = f"{src}（体例回退）"
    elif not src:
        out["source"] = "体例回退"
    out["empty"] = False
    return out


def fill_section_bundle_first(
    material_docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...] = (),
    table_predicate=None,
    chapter_h1: str = "",
    max_blocks: int = 80,
    year: int | None = None,
) -> dict[str, Any]:
    """通用：各材料整段搬运后合并——较新为主，较新缺项从较旧材料补（触网通用）。"""
    hits: list[dict[str, Any]] = []
    for doc, idx in reversed(list(sort_docs_newest_last(material_docs or []))):
        hit = extract_subsection_bundle(
            doc,
            start_keys=start_keys,
            stop_keys=stop_keys,
            table_predicate=table_predicate,
            chapter_h1=chapter_h1,
            max_blocks=max_blocks,
        )
        if _nonempty(hit):
            rec = sanitize_overhead_bundle_hit(hit)
            if any("整改" in k for k in start_keys):
                from chapters.overhead.ch6_revision import filter_overhead_revision_flow

                rec["flow"] = filter_overhead_revision_flow(rec.get("flow") or [], year=year)
                rec["paras"] = [
                    str(x.get("text") or "")
                    for x in rec["flow"]
                    if x.get("kind") == "para" and str(x.get("text") or "").strip()
                ]
                rec["empty"] = not rec["paras"] and not any(
                    x.get("kind") in {"table", "drawing"} for x in rec["flow"]
                )
            if rec.get("empty"):
                continue
            rec["_source"] = doc.source_name or ""
            rec_key = doc_recency_key(doc, idx)
            rec["_recency"] = rec_key[0]
            rec["_pack"] = rec_key[1] if len(rec_key) > 2 else 0
            rec["_idx"] = rec_key[-1]
            hits.append(rec)
    if hits:
        if _exclusive_newest_keys(start_keys):
            newest = max(hits, key=lambda h: (h.get("_recency") or 0, h.get("_pack") or 0, h.get("_idx") or 0))
            return newest
        hits = _keep_newest_per_dept(hits)
        if len(hits) == 1:
            return hits[0]
        return merge_overhead_bundle_hits(hits)
    for doc, _ in reversed(list(sort_docs_newest_last(prior_docs or []))):
        hit = extract_subsection_bundle(
            doc,
            start_keys=start_keys,
            stop_keys=stop_keys,
            table_predicate=table_predicate,
            chapter_h1=chapter_h1,
            max_blocks=max_blocks,
        )
        if _nonempty(hit):
            hit = sanitize_overhead_bundle_hit(hit)
            if hit.get("empty"):
                continue
            return mark_fallback(hit)
    return {"paras": [], "flow": [], "source": "", "empty": True}


def fill_with_prior_fallback(
    material_docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None,
    *,
    chapter_h1: str,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
    material_fn: FillFn | None = None,
    prior_fn: FillFn | None = None,
) -> dict[str, Any]:
    """先材料，再去年/保底。material_fn/prior_fn 可选（如表格专用抽取）。"""
    empty = {"paras": [], "flow": [], "table": [], "source": "", "empty": True}

    hit = fill_section_bundle_first(
        material_docs,
        None,
        start_keys=start_keys,
        stop_keys=stop_keys,
        chapter_h1=chapter_h1,
    )
    if _nonempty(hit):
        return hit

    if material_fn is not None:
        hit = material_fn(material_docs)
        if _nonempty(hit):
            return hit
    hit = extract_chapter_body_section(
        material_docs,
        chapter_h1=chapter_h1,
        start_keys=start_keys,
        stop_keys=stop_keys,
    )
    if _nonempty(hit):
        return hit

    if prior_fn is not None:
        hit = prior_fn(prior_docs)
        if _nonempty(hit):
            return mark_fallback(hit)
    hit = extract_chapter_body_section(
        prior_docs,
        chapter_h1=chapter_h1,
        start_keys=start_keys,
        stop_keys=stop_keys,
    )
    if _nonempty(hit):
        return mark_fallback(hit)
    return empty
