# -*- coding: utf-8 -*-
"""从去年完整报告检测某章目录骨架（可逐年复用）。

规则：在正文区（非目录）定位章题，收集其下 heading / 短标题行，直到下一章；
按 Word 标题层级或行首节号生成 8 / 8.1 / 8.1.1 这类编号。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text, hits_section_key, outline_num
from parsers.document_model import DocumentModel

_BARE_NUM = re.compile(r"^[\d.、．\s]+")


def bare_title(text: str) -> str:
    t = (text or "").strip()
    t = _BARE_NUM.sub("", t).strip()
    return t


def _is_short_title(compact: str, limit: int = 48) -> bool:
    if not compact or len(compact) > limit:
        return False
    if compact[-1:] in "。！？；":
        return False
    return True


def _heading_depth(block, chapter_level: int) -> int:
    """相对章题的深度：1=章下一级（如 8.1），2=再下一级（8.1.1）。"""
    lv = int(getattr(block, "level", 0) or 0)
    if lv <= 0:
        return 1
    rel = lv - chapter_level
    if rel <= 0:
        return 1
    return min(rel, 4)


def _assign_nums(items: list[dict[str, Any]], chapter_no: int) -> list[dict[str, Any]]:
    """按 depth 赋号；若原文已带节号则优先用原文节号。"""
    out: list[dict[str, Any]] = []
    counters = [chapter_no, 0, 0, 0, 0]
    for it in items:
        depth = int(it.get("depth") or 0)
        explicit = it.get("explicit_num") or ""
        title = it.get("title") or ""
        if depth <= 0:
            num = str(chapter_no)
        elif explicit and explicit.startswith(str(chapter_no)):
            num = explicit
            parts = [int(x) for x in num.split(".") if x.isdigit()]
            for i, p in enumerate(parts):
                if i < len(counters):
                    counters[i] = p
            for i in range(len(parts), len(counters)):
                counters[i] = 0
        else:
            if depth >= len(counters):
                depth = len(counters) - 1
            counters[depth] += 1
            for i in range(depth + 1, len(counters)):
                counters[i] = 0
            num = ".".join(str(counters[i]) for i in range(0, depth + 1))
        out.append(
            {
                "num": num,
                "title": title,
                "bare": title,
                "depth": depth,
                "level": min(1 + depth, 4),
                "source": it.get("source") or "",
            }
        )
    return out


def detect_chapter_outline(
    docs: list[DocumentModel] | None,
    *,
    chapter_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
    chapter_no: int,
) -> list[dict[str, Any]]:
    """从去年报告检测一章目录。返回含章题在内的节点列表；找不到则空列表。"""
    best: tuple[int, list[dict[str, Any]]] | None = None
    for doc in docs or []:
        name = doc.source_name or ""
        blocks = list(doc.blocks or [])
        for i, block in enumerate(blocks):
            t = (block.text or "").strip()
            if not t:
                continue
            compact = compact_text(t)
            if not hits_section_key(compact, chapter_keys, title_only_words=False):
                continue
            if not _is_short_title(compact, 40):
                continue
            ch_level = int(getattr(block, "level", 0) or 0) or 1
            raw: list[dict[str, Any]] = [
                {
                    "title": bare_title(t) or compact_text(t),
                    "depth": 0,
                    "explicit_num": outline_num(compact) or str(chapter_no),
                    "source": name,
                }
            ]
            table_hits = 0
            for b2 in blocks[i + 1 :]:
                t2 = (b2.text or "").strip()
                c2 = compact_text(t2)
                if b2.type == "table" and b2.rows:
                    table_hits += 1
                    continue
                if not t2:
                    continue
                if hits_section_key(c2, stop_keys, title_only_words=False) and _is_short_title(c2, 40):
                    break
                # 目录骨架只认 Word 标题行，避免把「故障现象：」等正文短句收成伪小节
                if b2.type != "heading":
                    continue
                if not _is_short_title(c2, 40):
                    continue
                title = bare_title(t2) or c2
                if not title or title == raw[0]["title"]:
                    continue
                if title.startswith("图") or title.endswith(("：", ":")):
                    continue
                depth = _heading_depth(b2, ch_level)
                if "评估小结" in title:
                    depth = 1
                elif any(k in title for k in ("风险数据库", "隐患排除", "隐患排查", "典型故障")):
                    depth = 2
                elif "突出事件" in title:
                    depth = 1
                raw.append(
                    {
                        "title": title,
                        "depth": depth,
                        "explicit_num": outline_num(c2) or "",
                        "source": name,
                    }
                )
            if len(raw) < 2:
                continue
            scored = _assign_nums(raw, chapter_no)
            score = len(scored) * 10 + table_hits * 5
            if ch_level and ch_level <= 2:
                score += 50
            if ch_level >= 4:
                score -= 40
            blob = "".join(x["title"] for x in scored)
            if not any(k in blob for k in ("风险数据库", "突出事件", "隐患", "典型故障")):
                score -= 30
            if best is None or score > best[0]:
                best = (score, scored)
    return list(best[1]) if best else []


def outline_heading_text(node: dict[str, Any]) -> str:
    num = str(node.get("num") or "").strip()
    title = str(node.get("title") or node.get("bare") or "").strip()
    if not num:
        return title
    if title.startswith(num):
        return title
    return f"{num}  {title}"
