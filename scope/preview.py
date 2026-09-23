# -*- coding: utf-8 -*-
"""上传后解析文件里有哪些线路、区段。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from parsers.dispatch import parse_files
from parsers.document_model import DocumentModel
from scope.ledger import extract_ledger_from_documents
from scope.names import file_fingerprint, normalize_line, normalize_segment
from scope.registry import list_reports


def _col(header: list[str], *needles: str) -> int | None:
    """表头从左找含指定字样的列。"""
    for i, cell in enumerate(header):
        if any(n in str(cell or "") for n in needles):
            return i
    return None


def scan_documents(docs: list[DocumentModel]) -> dict[str, list[str]]:
    """从表头含「线路」的表收集线路→区段。表扫不到再退回抽检台账行。"""
    found: dict[str, set[str]] = defaultdict(set)
    for doc in docs:
        for block in doc.blocks:
            if block.type != "table" or not block.rows:
                continue
            header = [str(c) for c in block.rows[0]]
            line_i = _col(header, "线路")
            if line_i is None:
                continue
            seg_i = _col(header, "区段")
            for row in block.rows[1:]:
                line = normalize_line(row[line_i] if line_i < len(row) else "")
                if not line:
                    continue
                seg = normalize_segment(row[seg_i] if seg_i is not None and seg_i < len(row) else "")
                found[line].add(seg)
    if not found:
        for rec in extract_ledger_from_documents(docs):
            line = normalize_line(rec.get("line_id"))
            if line:
                found[line].add(normalize_segment(rec.get("segment")))
    return {line: sorted(segs - {""}) for line, segs in sorted(found.items())}


def preview_files(paths: list[str | Path]) -> dict[str, Any]:
    """上传后扫表里的线路/区段，给范围选择用。年报按章评估现在较少用这条。"""
    paths = [Path(p) for p in paths]
    docs = parse_files(paths)
    lines = scan_documents(docs)
    fingerprint = file_fingerprint(paths)
    options = [{"line_id": line, "segments": segs} for line, segs in lines.items()]
    return {
        "fingerprint": fingerprint,
        "files": [p.name for p in paths],
        "lines": options,
        "previous_reports": list_reports(fingerprint),
    }
