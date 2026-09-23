# -*- coding: utf-8 -*-
"""评估任务存 jobs/{id}.json。网页轮询读摘要，不把整本文档塞进进度。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from paths import JOBS, ensure_dirs
from scope.names import format_scope, normalize_line, normalize_segment, scope_key
from scope.registry import list_reports
from scope.slim import slim_job, slim_line, slim_subsystem


def _path(job_id: str) -> Path:
    ensure_dirs()
    return JOBS / f"{job_id}.json"


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    disk = slim_job(dict(job))
    disk["updated_at"] = updated
    _path(disk["job_id"]).write_text(
        json.dumps(disk, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    job["updated_at"] = updated
    return disk


def load_job(job_id: str) -> dict[str, Any] | None:
    path = _path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _job_scopes(job: dict[str, Any]) -> list[dict[str, str]]:
    result = job.get("result") or {}
    rows = job.get("line_results") or result.get("line_results") or []
    out = []
    for item in rows:
        out.append(
            {
                "line_id": normalize_line(item.get("line_id")),
                "segment": normalize_segment(item.get("segment")),
                "label": format_scope(item.get("line_id"), item.get("segment")),
            }
        )
    return out


def _type_columns(job: dict[str, Any], result: dict[str, Any]) -> list[str]:
    names: list[str] = []
    rows = job.get("line_results") or result.get("line_results") or []
    for item in rows:
        for key in (item.get("type_scores") or {}).keys():
            if key and key not in names:
                names.append(key)
        for contrib in ((item.get("subsystem") or {}).get("contributions") or []):
            name = contrib.get("device_type")
            if name and name not in names:
                names.append(name)
    return names


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    """给网页的任务视图：进度、黄标审查、可下载与否、同批材料的历史稿。"""
    result = job.get("result") or {}
    subsystem = job.get("subsystem") or result.get("subsystem")
    fingerprint = job.get("file_fingerprint") or (result.get("meta") or {}).get("file_fingerprint")
    current_keys = {scope_key(x.get("line_id"), x.get("segment")) for x in _job_scopes(job)}
    previous = []
    subsystem_id = job.get("subsystem_id") or (result.get("meta") or {}).get("subsystem_id") or "stray_current"
    chapter_id = job.get("chapter_id") or (result.get("meta") or {}).get("chapter_id") or ""
    domain_id = job.get("domain_id") or (result.get("meta") or {}).get("domain_id") or "power_supply"
    for item in list_reports(fingerprint or "", subsystem_id, domain_id=domain_id, chapter_id=chapter_id or None):
        if item.get("job_id") == job.get("job_id"):
            continue
        overlap = []
        for sc in item.get("scopes") or []:
            key = scope_key(sc.get("line_id"), sc.get("segment"))
            if key in current_keys:
                overlap.append(format_scope(sc.get("line_id"), sc.get("segment")))
        row = dict(item)
        row["overlap"] = overlap
        previous.append(row)
    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "step": job.get("step"),
        "message": job.get("message"),
        "error": job.get("error"),
        "mode": job.get("mode"),
        "files": [Path(p).name for p in job.get("file_paths") or []],
        "pending": job.get("pending") or [],
        "records": job.get("records") or [],
        "warnings": (job.get("warnings") or [])[:20],
        "section_reviews": job.get("section_reviews") or (result.get("section_reviews") or []),
        "subsystem": slim_subsystem(subsystem) if subsystem else subsystem,
        "line_results": [
            slim_line(x) for x in (job.get("line_results") or result.get("line_results") or [])
        ],
        "device_scores": job.get("device_scores") or [],
        "device_score_total": job.get("device_score_total")
        or len(job.get("device_scores") or result.get("device_scores") or []),
        "file_fingerprint": fingerprint,
        "previous_reports": previous,
        "report_ready": bool(job.get("report_path")),
        "assessment_year": job.get("assessment_year") or (result.get("meta") or {}).get("assessment_year"),
        "calendar_year": datetime.now().year,
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "updated_at": job.get("updated_at"),
        "domain_id": job.get("domain_id") or (result.get("meta") or {}).get("domain_id") or "power_supply",
        "subsystem_id": job.get("subsystem_id") or (result.get("meta") or {}).get("subsystem_id") or "stray_current",
        "chapter_id": job.get("chapter_id") or (result.get("meta") or {}).get("chapter_id") or "",
        "type_columns": _type_columns(job, result),
    }
