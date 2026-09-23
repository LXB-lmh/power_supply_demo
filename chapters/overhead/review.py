# -*- coding: utf-8 -*-
"""接触网各章审阅：缺材料、逻辑不通、年份错误、语言不通顺、标点错误。

与成文黄标同一口径：
- 整节没有材料 → 黄标题，网页记「缺失材料」；
- 数字合计对不上 → 黄该句和该节标题，网页记「逻辑不通」；
- 截止年早于评估年、对比不含评估年 → 黄该句和该节标题，网页记「年份错误」；
- 话说一半、标点坏 → 黄该句，网页记在左栏。
材料差异只上网页，不写进 Word。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.number_logic import number_logic_notes, year_logic_notes
from chapters.common.word import (
    is_incomplete,
    is_punct_issue,
    language_note,
    punct_note,
    split_clauses,
)

FAULT_NO_COUNT = re.compile(r"故障起(?!\d)")


def _add(out: list[dict[str, str]], section: str, kind: str, issue: str, note: str = "") -> None:
    key = (section, kind, issue, note)
    if any((x["section"], x["kind"], x["issue"], x.get("note") or "") == key for x in out):
        return
    item = {"section": section, "kind": kind, "issue": issue}
    if note:
        item["note"] = note
    out.append(item)


def _fill_empty(fill: dict[str, Any] | None) -> bool:
    if fill is None:
        return True
    if fill.get("paras") or (fill.get("table") and len(fill.get("table") or []) > 1):
        return False
    if fill.get("sections") and any(not s.get("empty") for s in fill["sections"]):
        return False
    if fill.get("flow"):
        return False
    return bool(fill.get("empty", True))


def _has_child_nodes(outline: list[dict[str, Any]], index: int) -> bool:
    depth = int(outline[index].get("depth") or 0)
    if index + 1 >= len(outline):
        return False
    return int(outline[index + 1].get("depth") or 0) > depth


def _section_texts(fill: dict[str, Any] | None) -> list[str]:
    """只扫本节正文。子节在目录里另有节点，避免同一句报两次。"""
    if not fill:
        return []
    texts: list[str] = []
    for item in fill.get("flow") or []:
        if not isinstance(item, dict) or item.get("kind") != "para":
            continue
        t = str(item.get("text") or "").strip()
        if t and t not in texts:
            texts.append(t)
    if not texts:
        for p in fill.get("paras") or []:
            t = str(p or "").strip()
            if t and t not in texts:
                texts.append(t)
    return texts


def _scan_texts(out: list[dict[str, str]], section: str, texts: list[str], *, year: int | None) -> None:
    for raw in texts:
        t = (raw or "").strip()
        if not t:
            continue
        for note in number_logic_notes(t):
            _add(out, section, "logic", "逻辑不通", note)
        for note in year_logic_notes(t, year):
            _add(out, section, "year", "年份错误", note)
        if "；；" in t or "；。" in t or "。；" in t:
            _add(out, section, "punct", "标点错误", punct_note(t))
        for clause in split_clauses(t) or [t]:
            clause = clause.strip()
            if not clause:
                continue
            packed = clause.replace(" ", "")
            if FAULT_NO_COUNT.search(packed) or is_incomplete(clause):
                _add(out, section, "language", "语言不通顺", language_note(clause))
            elif is_punct_issue(clause):
                _add(out, section, "punct", "标点错误", punct_note(clause))


def review_chapter(pack: dict[str, Any], chapter_id: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    year = pack.get("year")
    try:
        year_i = int(year) if year else None
    except (TypeError, ValueError):
        year_i = None
    outline = list(pack.get("outline") or [])
    for i, node in enumerate(outline):
        depth = int(node.get("depth") or 0)
        if depth <= 0:
            continue
        num = str(node.get("num") or "")
        title = str(node.get("title") or "").strip()
        label = f"{num} {title}".strip()
        fill = node.get("fill")
        empty = _fill_empty(fill)
        for w in (fill or {}).get("warnings") or []:
            note = str(w or "").strip()
            if note:
                _add(out, label or title or num, "missing", "材料差异", note)
        if empty and _has_child_nodes(outline, i):
            continue
        if empty:
            _add(out, label or title or num, "missing", "缺失材料", "接触网本章无对应材料，成文仅留黄标题")
            continue
        _scan_texts(out, label or title or num, _section_texts(fill), year=year_i)
    for w in pack.get("warnings") or []:
        note = str(w or "").strip()
        if note:
            _add(out, chapter_id, "missing", "材料差异", note)
    return out
