# -*- coding: utf-8 -*-
"""解析后去掉内容相同的表，只留一份。认格子，不认文件名。

「本章建议」分章和评估抽数都会用到：三份总表（含 _1、备份包）只保留一份，
优先文件名带 _1 的 Excel。行顺序不同、空格/换行不同仍视为同一张表。
"""
from __future__ import annotations

import hashlib
from typing import Any

from .document_model import Block, DocumentModel


def _norm_cell(raw: Any) -> str:
    """去空白；1.0 与 1 视为相同，避免 Excel 与 Word 拷贝对不上。"""
    text = str(raw or "").replace("\r", "").replace("\n", "").replace("\u3000", " ").strip()
    text = "".join(text.split())
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if number == int(number) and abs(number) < 1e12:
        return str(int(number))
    return text


def _norm_row(row: list[Any] | None) -> tuple[str, ...]:
    cells = [_norm_cell(c) for c in (row or [])]
    while cells and not cells[-1]:
        cells.pop()  # 去掉 Excel 右侧空列
    return tuple(cells)


def table_fingerprint(rows: list[list[Any]] | None) -> str:
    """表头保留顺序，表体排序后再哈希，行对调仍算同一张。"""
    body: list[tuple[str, ...]] = []
    for raw in rows or []:
        row = _norm_row(raw)
        if row:
            body.append(row)
    if not body:
        return ""
    header = body[0]
    rest = tuple(sorted(body[1:]))
    payload = "\n".join("|".join(row) for row in (header, *rest))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _keep_rank(doc: DocumentModel, block: Block, doc_index: int, block_index: int) -> tuple:
    """越小越优先留下：_1 文件名 > xlsx > 行数多。"""
    name = doc.source_name or ""
    prefer_revision = 0 if "_1" in name else 1
    prefer_xlsx = 0 if (doc.suffix or "").lower() == ".xlsx" else 1
    n_rows = sum(1 for row in (block.rows or []) if _norm_row(row))
    return (prefer_revision, prefer_xlsx, -n_rows, name, doc_index, block_index)


def _is_sheet_heading(block: Block) -> bool:
    return block.type == "heading" and (block.text or "").startswith("工作表:")


def drop_duplicate_tables(docs: list[DocumentModel | None] | None) -> dict[int, str]:
    """去掉内容相同的表。返回 {被去掉表的文件下标: 留下的那份文件名}。

    分章时：被掏空的重复文件不再出现在「本章建议」里。
    """
    items: list[tuple[str, tuple, int, int]] = []
    for di, doc in enumerate(docs or []):
        if doc is None:
            continue
        for bi, block in enumerate(doc.blocks):
            if block.type != "table" or not block.rows:
                continue
            fingerprint = table_fingerprint(block.rows)
            if not fingerprint:
                continue
            items.append((fingerprint, _keep_rank(doc, block, di, bi), di, bi))

    keep: dict[str, tuple[int, int]] = {}
    for fingerprint, rank, di, bi in items:
        current = keep.get(fingerprint)
        if current is None or rank < _keep_rank(docs[current[0]], docs[current[0]].blocks[current[1]], *current):
            keep[fingerprint] = (di, bi)

    drop = {(di, bi) for fingerprint, _rank, di, bi in items if keep.get(fingerprint) != (di, bi)}
    lost: dict[int, str] = {}
    for fingerprint, _rank, di, bi in items:
        kept = keep.get(fingerprint)
        if kept and kept != (di, bi):
            kept_doc = docs[kept[0]]
            lost[di] = (kept_doc.source_name if kept_doc else "") or ""
    for di, doc in enumerate(docs or []):
        if doc is None:
            continue
        kept_blocks: list[Block] = []
        for bi, block in enumerate(doc.blocks):
            if (di, bi) in drop:
                # 工作表标题下面的表没了，标题也去掉，避免空 Sheet 名
                if kept_blocks and _is_sheet_heading(kept_blocks[-1]):
                    kept_blocks.pop()
                continue
            kept_blocks.append(block)
        doc.blocks = kept_blocks
    return lost
