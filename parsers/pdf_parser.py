# -*- coding: utf-8 -*-
"""PDF 按页抽出表和行文本。扫描件 OCR 质量差时后面抽取会黄句，不编造。"""
from __future__ import annotations

from pathlib import Path

import pdfplumber

from .document_model import Block, DocumentModel


def parse_pdf(path: Path) -> DocumentModel:
    blocks: list[Block] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            blocks.append(Block(type="heading", text=f"第{i}页", level=1))
            tables = page.extract_tables() or []
            for table in tables:
                rows = [[(cell or "").strip() for cell in row] for row in table]
                if rows:
                    blocks.append(Block(type="table", rows=rows))
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if line:
                    blocks.append(Block(type="paragraph", text=line))
    return DocumentModel(
        source_name=path.name,
        source_path=str(path),
        suffix=".pdf",
        blocks=blocks,
    )
