# -*- coding: utf-8 -*-
"""任务存盘和网页回传只保留摘要，避免两千台设备把进度卡住。"""
from __future__ import annotations

from typing import Any

# 这些键体积大，任务回传时直接丢掉。
HEAVY_KEYS = {
    "documents",
    "material_text",
    "audit",
    "trace",
    "extracted_records",
}


def slim_device(ds: dict[str, Any] | None) -> dict[str, Any]:
    """单台只留标识和分数，去掉抽检明细，避免两千台把进度卡住。"""
    row = ds or {}
    return {
        "device_type": row.get("device_type"),
        "device_id": row.get("device_id"),
        "line_id": row.get("line_id"),
        "segment": row.get("segment"),
        "station_id": row.get("station_id"),
        "total_score": row.get("total_score"),
        "grade": row.get("grade"),
        "score_source": row.get("score_source"),
        "ledger_score": row.get("ledger_score"),
        "ledger_grade": row.get("ledger_grade"),
        "engine_score": row.get("engine_score"),
        "engine_grade": row.get("engine_grade"),
    }


def slim_subsystem(sub: dict[str, Any] | None) -> dict[str, Any]:
    """子系统贡献只留权重和均分，供网页进度条。"""
    row = dict(sub or {})
    row["contributions"] = [
        {
            "device_type": item.get("device_type"),
            "weight_code": item.get("weight_code"),
            "weight": item.get("weight"),
            "device_count": item.get("device_count"),
            "avg_device_score": item.get("avg_device_score"),
            "weighted_contribution": item.get("weighted_contribution"),
        }
        for item in row.get("contributions") or []
    ]
    return row


def slim_line(item: dict[str, Any] | None) -> dict[str, Any]:
    """线路结果摘要。没有 type_scores 时从贡献均分回填，方便报告里写各类型分。"""
    row = item or {}
    subsystem = slim_subsystem(row.get("subsystem"))
    type_scores = dict(row.get("type_scores") or {})
    if not type_scores:
        for contrib in subsystem.get("contributions") or []:
            name = contrib.get("device_type")
            if name:
                type_scores[name] = contrib.get("avg_device_score")
    return {
        "line_id": row.get("line_id"),
        "segment": row.get("segment"),
        "label": row.get("label"),
        "subsystem": subsystem,
        "type_scores": type_scores,
        "device_count": row.get("device_count"),
    }


def slim_result(result: dict[str, Any] | None) -> dict[str, Any]:
    """评估结果去掉审计、原文和逐台全量，只留可回传的摘要。"""
    out = dict(result or {})
    for key in ("audit_trail", "extracted_records", "documents", "llm_analysis"):
        out.pop(key, None)
    out["device_scores"] = [slim_device(x) for x in out.get("device_scores") or []]
    out["line_results"] = [slim_line(x) for x in out.get("line_results") or []]
    if out.get("subsystem"):
        out["subsystem"] = slim_subsystem(out["subsystem"])
    return out


def slim_job(job: dict[str, Any]) -> dict[str, Any]:
    """任务回传：非待确认时清空 records；待确认最多 80 条；设备分只回前 40 台。"""
    out = {key: value for key, value in job.items() if key not in HEAVY_KEYS}
    awaiting = out.get("status") == "awaiting_confirmation"
    if not awaiting:
        out["records"] = []
        out["pending"] = out.get("pending") or []
    elif len(out.get("records") or []) > 80:
        out["records"] = list(out.get("records") or [])[:80]
    scores = list(job.get("device_scores") or (job.get("result") or {}).get("device_scores") or [])
    out["device_score_total"] = len(scores)
    out["device_scores"] = [slim_device(x) for x in scores[:40]]
    out["line_results"] = [slim_line(x) for x in out.get("line_results") or []]
    if out.get("subsystem"):
        out["subsystem"] = slim_subsystem(out["subsystem"])
    if out.get("result"):
        out["result"] = slim_result(out["result"])
    return out
