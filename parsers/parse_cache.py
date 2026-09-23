# -*- coding: utf-8 -*-
"""解析结果磁盘缓存：按文件内容 SHA256 存 DocumentModel；分拣结果按专业存 latest。

重启后仍可用。材料内容未变则跳过 Word/Excel 重解析。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import PARSE_CACHE, ensure_dirs
from parsers.document_model import DocumentModel

_DOCS = PARSE_CACHE / "docs"
_CLASSIFY = PARSE_CACHE / "classify"
_MATERIALS = PARSE_CACHE / "materials"
_CHUNK = 1024 * 1024
_SAVE_LOCK = threading.Lock()


def _safe_domain(domain_id: str) -> str:
    return (domain_id or "power_supply").replace("/", "_").replace("\\", "_")


def _safe_rel(rel: str) -> str:
    rel = str(rel or "").replace("\\", "/").strip()
    parts = [p for p in Path(rel).parts if p not in ("..", ".", "")]
    return "/".join(parts) if parts else Path(rel).name


def materials_dir(domain_id: str) -> Path:
    return _MATERIALS / _safe_domain(domain_id)


def persist_classify_materials(
    domain_id: str,
    paths: list[str | Path],
    relpaths: list[str] | None = None,
) -> None:
    """分拣成功后把材料副本落盘，重启后「本章建议」仍可一键加入。"""
    ensure_dirs()
    base = materials_dir(domain_id)
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    rels = relpaths or []
    for i, raw in enumerate(paths):
        src = Path(raw)
        if not src.is_file():
            continue
        rel = _safe_rel(rels[i] if i < len(rels) else src.name)
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def resolve_stored_material(domain_id: str, rel: str) -> Path | None:
    safe = _safe_rel(rel)
    if not safe:
        return None
    base = materials_dir(domain_id).resolve()
    dest = (base / safe).resolve()
    if not str(dest).startswith(str(base)):
        return None
    return dest if dest.is_file() else None


def count_stored_materials(domain_id: str, files_meta: list[dict[str, Any]]) -> int:
    n = 0
    for row in files_meta or []:
        rel = str(row.get("rel") or row.get("name") or "")
        if resolve_stored_material(domain_id, rel):
            n += 1
    return n


def classify_cache_usable(row: dict[str, Any] | None, domain_id: str) -> bool:
    """有分拣结果且材料副本齐全，才允许「使用上次解析」。"""
    if not row or not row.get("result"):
        return False
    result = row.get("result") or {}
    files = row.get("files") or []
    if not files:
        return False
    if int(result.get("assigned") or 0) <= 0 and not result.get("by_chapter"):
        return False
    stored = count_stored_materials(domain_id, files)
    return stored > 0 and stored == len(files)


def content_sha256(path: str | Path) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _doc_path(digest: str) -> Path:
    return _DOCS / f"{digest}.json"


def _cache_has_yellow_schema(data: dict[str, Any]) -> bool:
    """旧缓存没有 yellow 字段，不能复用，否则材料标黄会丢。"""
    blocks = data.get("blocks") or []
    if not blocks:
        return True
    return any(isinstance(b, dict) and "yellow" in b for b in blocks)


def load_document(digest: str) -> DocumentModel | None:
    path = _doc_path(digest)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not _cache_has_yellow_schema(data):
            return None
        return DocumentModel.from_dict(data)
    except Exception:
        return None


def save_document(digest: str, doc: DocumentModel) -> None:
    ensure_dirs()
    _DOCS.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(doc.to_dict(), ensure_ascii=False, separators=(",", ":"))
    with _SAVE_LOCK:
        _doc_path(digest).write_text(payload, encoding="utf-8")


def _resolved_source_path(original: Path, parsed_path: str, work_dir: Path | None) -> str:
    """.doc/.xls 成文回拷必须指向已转换的 docx/xlsx，不能改回原路径。"""
    from parsers.office_convert import converted_sidecar, convert_legacy

    suffix = original.suffix.lower()
    if suffix not in {".doc", ".xls"}:
        return str(original.resolve())
    target = "docx" if suffix == ".doc" else "xlsx"
    parsed = Path(parsed_path) if parsed_path else None
    if parsed is not None and parsed.suffix.lower() == f".{target}" and parsed.is_file():
        return str(parsed.resolve())
    hit = converted_sidecar(original, work_dir, target)
    if hit is not None:
        return str(hit.resolve())
    try:
        dest = Path(work_dir) if work_dir is not None else original.parent / "_converted"
        return str(convert_legacy(original, dest).resolve())
    except Exception:
        return str(original.resolve())


def parse_file_cached(path: str | Path, work_dir: Path | None = None) -> tuple[DocumentModel, str, bool]:
    """返回 (doc, content_sha256, from_cache)。"""
    from parsers.dispatch import _parse_file
    from parsers.dedupe import drop_duplicate_tables

    p = Path(path)
    digest = content_sha256(p)
    hit = load_document(digest)
    if hit is not None:
        hit.source_name = p.name
        hit.source_path = _resolved_source_path(p, hit.source_path or "", work_dir)
        return hit, digest, True
    doc = _parse_file(p, work_dir=work_dir)
    drop_duplicate_tables([doc])
    doc.source_name = p.name
    doc.source_path = _resolved_source_path(p, doc.source_path or "", work_dir)
    save_document(digest, doc)
    return doc, digest, False


def _parse_workers() -> int:
    raw = str(os.getenv("PARSE_MAX_WORKERS") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return max(1, min(12, int(raw)))
    cpu = os.cpu_count() or 4
    return max(2, min(8, cpu))


def parse_files_cached(
    paths: list[str | Path],
    work_dir: Path | None = None,
) -> tuple[list[DocumentModel | None], dict[str, Any]]:
    """批量解析，跨文件去重；相同内容只解析一次。"""
    from parsers.dedupe import drop_duplicate_tables

    kept = [Path(p) for p in paths if not Path(p).name.startswith("~$")]
    if not kept:
        return [], {"cache_hits": 0, "cache_misses": 0, "total": 0}

    workers = min(_parse_workers(), len(kept))
    path_digest: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(content_sha256, p): p for p in kept}
        for fut in as_completed(futs):
            p = futs[fut]
            path_digest[str(p)] = fut.result()

    unique: list[Path] = []
    seen: set[str] = set()
    for p in kept:
        dig = path_digest[str(p)]
        if dig in seen:
            continue
        seen.add(dig)
        unique.append(p)

    parsed: dict[str, tuple[DocumentModel | None, bool, str]] = {}

    def _one(p: Path) -> tuple[str, DocumentModel | None, bool, str]:
        try:
            doc, dig, hit = parse_file_cached(p, work_dir=work_dir)
            return dig, doc, hit, ""
        except Exception as exc:
            return path_digest.get(str(p), ""), None, False, str(exc)

    if len(unique) == 1:
        dig, doc, hit, err = _one(unique[0])
        parsed[dig] = (doc, hit, err)
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(unique))) as pool:
            futs = [pool.submit(_one, p) for p in unique]
            for fut in as_completed(futs):
                dig, doc, hit, err = fut.result()
                parsed[dig] = (doc, hit, err)

    docs: list[DocumentModel | None] = []
    hits = 0
    used: set[int] = set()
    errors: list[str] = []
    for p in kept:
        dig = path_digest[str(p)]
        doc, from_cache, err = parsed[dig]
        errors.append(err)
        if from_cache or (doc is not None and id(doc) in used):
            hits += 1
        if doc is not None and id(doc) in used:
            doc = copy.deepcopy(doc)
        if doc is not None:
            doc.source_name = p.name
            doc.source_path = _resolved_source_path(p, doc.source_path or "", work_dir)
            used.add(id(doc))
        docs.append(doc)
    drop_duplicate_tables(docs)
    first_err = next((e for e in errors if e), "")
    if first_err and not any(docs):
        raise RuntimeError(first_err)
    return docs, {
        "cache_hits": hits,
        "cache_misses": max(0, len(kept) - hits),
        "total": len(docs),
        "unique_files": len(unique),
        "errors": errors,
        "digests": [path_digest[str(p)] for p in kept],
    }


def _classify_latest_path(domain_id: str) -> Path:
    safe = (domain_id or "power_supply").replace("/", "_")
    return _CLASSIFY / f"{safe}_latest.json"


def save_classify_result(
    domain_id: str,
    *,
    result: dict[str, Any],
    files_meta: list[dict[str, Any]],
    assessment_year: int | None,
    prior_digest: str = "",
) -> dict[str, Any]:
    ensure_dirs()
    _CLASSIFY.mkdir(parents=True, exist_ok=True)
    payload = {
        "domain_id": domain_id,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assessment_year": assessment_year,
        "prior_digest": prior_digest or "",
        "files": files_meta,
        "batch_key": _batch_key(files_meta, prior_digest, assessment_year),
        "result": result,
    }
    path = _classify_latest_path(domain_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
    return payload


def load_classify_latest(domain_id: str) -> dict[str, Any] | None:
    path = _classify_latest_path(domain_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _batch_key(files_meta: list[dict[str, Any]], prior_digest: str, year: int | None) -> str:
    parts = [f"{m.get('rel') or ''}:{m.get('content_sha256') or ''}" for m in sorted(files_meta, key=lambda x: x.get("rel") or "")]
    blob = "|".join(parts) + f"|prior:{prior_digest}|y:{year or ''}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def files_meta_match(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """当前上传与缓存是否同一批材料（比相对路径 + 内容哈希）。"""
    def norm(rows: list[dict[str, Any]]) -> set[str]:
        out: set[str] = set()
        for r in rows or []:
            rel = str(r.get("rel") or r.get("name") or "").replace("\\", "/")
            dig = str(r.get("content_sha256") or "")
            if rel and dig:
                out.add(f"{rel}:{dig}")
        return out

    return norm(a) == norm(b) and len(a) == len(b)


def public_cache_info(domain_id: str) -> dict[str, Any]:
    row = load_classify_latest(domain_id)
    if not row:
        return {"available": False, "domain_id": domain_id}
    files = row.get("files") or []
    stored = count_stored_materials(domain_id, files)
    usable = classify_cache_usable(row, domain_id)
    return {
        "available": usable,
        "domain_id": domain_id,
        "saved_at": row.get("saved_at") or "",
        "assessment_year": row.get("assessment_year"),
        "file_count": len(files),
        "stored_count": stored,
        "file_names": [str(f.get("rel") or f.get("name") or "") for f in files[:40]],
        "batch_key": row.get("batch_key") or "",
    }
