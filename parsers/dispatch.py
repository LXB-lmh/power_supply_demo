# -*- coding: utf-8 -*-
"""按后缀选解析器。老 .doc / .xls 先转成 docx / xlsx。

parse_file：单份材料，去掉本文件里重复工作表。
parse_files：一次评估的全部材料，跨文件去重（认格子不认文件名）。
Office 临时文件 ~$xxx 直接丢掉。
"""
from __future__ import annotations

from pathlib import Path

from .dedupe import drop_duplicate_tables
from .document_model import DocumentModel
from .docx_parser import parse_docx
from .office_convert import convert_legacy
from .pdf_parser import parse_pdf
from .text_parser import parse_json_material, parse_text
from .xlsx_parser import parse_xlsx


def _parse_file(path: str | Path, work_dir: Path | None = None) -> DocumentModel:
    """只解析、不去重。供 parse_files 先读完再统一 drop_duplicate_tables。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"材料不存在: {path}")

    suffix = path.suffix.lower()
    work_dir = work_dir or path.parent / "_converted"

    if suffix in {".doc", ".xls"}:
        path = convert_legacy(path, work_dir)
        suffix = path.suffix.lower()

    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".xlsx":
        return parse_xlsx(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".json":
        return parse_json_material(path)
    if suffix in {".txt", ".md"}:
        return parse_text(path)
    raise ValueError(f"暂不支持的文件格式: {suffix}（{path.name}）")


def parse_file(path: str | Path, work_dir: Path | None = None) -> DocumentModel:
    """解析单文件，并去掉该文件内部内容相同的表。"""
    doc = _parse_file(path, work_dir=work_dir)
    drop_duplicate_tables([doc])
    return doc


def parse_files(
    paths: list[str | Path],
    work_dir: Path | None = None,
    *,
    use_cache: bool = True,
) -> list[DocumentModel]:
    """解析一批文件后按表格内容去重。评估抽数走这一条。默认读磁盘解析缓存。"""
    if use_cache:
        from parsers.parse_cache import parse_files_cached

        docs, stats = parse_files_cached(paths, work_dir=work_dir)
        errs = [e for e in (stats.get("errors") or []) if e]
        if errs:
            raise RuntimeError(errs[0])
        return [d for d in docs if d is not None]
    kept = [p for p in paths if not Path(p).name.startswith("~$")]
    docs = [_parse_file(p, work_dir=work_dir) for p in kept]
    drop_duplicate_tables(docs)
    return docs
