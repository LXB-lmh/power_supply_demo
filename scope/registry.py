# -*- coding: utf-8 -*-
"""同一批上传文件对应的历史报告。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import JOBS, OUTPUT, UPLOADS, ensure_dirs
from scope.names import format_scope


def _path() -> Path:
    """历史报告索引文件：jobs/file_reports.json，按上传指纹分桶。"""
    ensure_dirs()
    return JOBS / "file_reports.json"


def _load() -> dict[str, list[dict[str, Any]]]:
    """读索引；文件坏了当空字典，避免网页历史列表整页挂掉。"""
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save(data: dict[str, list[dict[str, Any]]]) -> None:
    """整份索引写回。"""
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _scope_labels(item: dict[str, Any]) -> list[str]:
    """报告覆盖的线路/区段短标签；没有 scopes 时从标题按顿号拆。"""
    labels = []
    for scope in item.get("scopes") or []:
        label = format_scope(scope.get("line_id"), scope.get("segment"))
        if label and label not in labels:
            labels.append(label)
    if labels:
        return labels
    title = str(item.get("title") or "").strip()
    if not title:
        return []
    return [part for part in title.replace("，", "、").split("、") if part.strip()]


def _short_title(item: dict[str, Any]) -> str:
    """列表用短标题：区段少则全写，多则「首个 等N个区段」。"""
    labels = _scope_labels(item)
    if not labels:
        return "评估报告"
    if len(labels) <= 2:
        return "、".join(labels)
    return f"{labels[0]} 等{len(labels)}个区段"


def _report_exists(item: dict[str, Any]) -> bool:
    """磁盘上是否还能下到这份 Word（登记路径或默认 OUTPUT/job_id）。"""
    job_id = item.get("job_id") or ""
    path = Path(item.get("report_path") or "")
    if path.exists():
        return True
    fallback = OUTPUT / job_id / "assessment_report.docx"
    return fallback.exists()


def decorate_report(item: dict[str, Any]) -> dict[str, Any]:
    """网页历史列表用的短标题和是否还能下载。"""
    labels = _scope_labels(item)
    return {
        "job_id": item.get("job_id"),
        "title": _short_title(item),
        "full_title": item.get("title") or _short_title(item),
        "scopes": item.get("scopes") or [],
        "scope_labels": labels,
        "scope_count": len(labels),
        "report_path": item.get("report_path"),
        "created_at": item.get("created_at"),
        "report_ready": _report_exists(item),
        "domain_id": item.get("domain_id") or "power_supply",
        "subsystem_id": item.get("subsystem_id") or "stray_current",
        "chapter_id": item.get("chapter_id") or "",
    }


def list_reports(
    fingerprint: str,
    subsystem_id: str | None = None,
    *,
    domain_id: str | None = None,
    chapter_id: str | None = None,
) -> list[dict[str, Any]]:
    """同一批文件指纹下的历史报告，供网页「以往稿」列表。

    可按专业、章节过滤；未指定章节时再按子系统筛。新的在前。
    """
    if not fingerprint:
        return []
    items = list(_load().get(fingerprint) or [])
    wanted_sub = (subsystem_id or "").strip()
    wanted_domain = (domain_id or "").strip()
    wanted_chapter = (chapter_id or "").strip()
    if wanted_domain:
        items = [x for x in items if (x.get("domain_id") or "power_supply") == wanted_domain]
    if wanted_chapter:
        items = [x for x in items if (x.get("chapter_id") or "") == wanted_chapter]
    elif wanted_sub:
        items = [x for x in items if (x.get("subsystem_id") or "stray_current") == wanted_sub]
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return [decorate_report(x) for x in items]


def register_report(fingerprint: str, item: dict[str, Any]) -> None:
    """评估完成后挂到该批文件指纹下，同材料可看到以往章节稿。"""
    if not fingerprint:
        return
    data = _load()
    bucket = [x for x in data.get(fingerprint) or [] if x.get("job_id") != item.get("job_id")]
    packed = {
        "job_id": item.get("job_id"),
        "title": item.get("title") or "评估报告",
        "scopes": item.get("scopes") or [],
        "report_path": item.get("report_path"),
        "created_at": item.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "domain_id": item.get("domain_id") or "power_supply",
        "subsystem_id": item.get("subsystem_id") or "stray_current",
        "chapter_id": item.get("chapter_id") or "",
    }
    packed["title"] = _short_title(packed)
    bucket.append(packed)
    data[fingerprint] = bucket
    _save(data)


def _cleanup_job_files(job_id: str, report_path: str | None = None) -> None:
    """删掉该任务的 json、输出目录、上传目录和报告文件。"""
    if not job_id:
        return
    job_file = JOBS / f"{job_id}.json"
    if job_file.exists():
        job_file.unlink()
    for folder in (OUTPUT / job_id, UPLOADS / job_id):
        if folder.exists() and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)
    extra = Path(report_path or "")
    if extra.exists() and extra.is_file():
        extra.unlink()


def remove_reports(
    fingerprint: str,
    job_ids: list[str] | None = None,
    *,
    keep_job_id: str | None = None,
) -> list[str]:
    """从该批指纹下删掉指定任务（可保留 keep_job_id），并清理作业文件与报告。

    job_ids 为空且未指定 keep 时，清空该指纹下全部历史稿。
    """
    if not fingerprint:
        return []
    data = _load()
    bucket = list(data.get(fingerprint) or [])
    wanted = {str(x) for x in (job_ids or []) if x}
    removed: list[dict[str, Any]] = []
    keep: list[dict[str, Any]] = []
    for item in bucket:
        job_id = str(item.get("job_id") or "")
        if keep_job_id and job_id == keep_job_id:
            keep.append(item)
            continue
        if wanted and job_id not in wanted:
            keep.append(item)
            continue
        removed.append(item)
    if keep:
        data[fingerprint] = keep
    else:
        data.pop(fingerprint, None)
    _save(data)
    for item in removed:
        _cleanup_job_files(str(item.get("job_id") or ""), item.get("report_path"))
    return [str(x.get("job_id") or "") for x in removed]
