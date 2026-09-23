# -*- coding: utf-8 -*-
"""各章共用的解析 → 抽取 → 成文流程。文风和填法仍由各章 HANDLER 自己决定。

网页「按章评估」走这里；CLI 一次生成第 1～12 章全年报走 chapters.power.build，不经过本模块。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from catalog.taxonomy import get_subsystem
from chapters.registry import get_handler
from chapters.spec import ChapterHandler
from engine.report import write_json_report
from parsers.dispatch import parse_files
from scope.ledger import clamp_assessment_year
from scope.names import file_fingerprint
from scope.registry import register_report
from scope.slim import slim_result


def run_chapter(
    handler: ChapterHandler,
    file_paths: list[str | Path],
    *,
    output_dir: str | Path,
    job_id: str,
    subsystem_id: str = "stray_current",
    assessment_year: int | None = None,
    file_fingerprint_value: str = "",
    on_progress=None,
    prior_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    """跑通一章：解析材料 → HANDLER 抽取 → 按 2025 目录成文 → 审阅黄标。

    这是摘录填空，不算分：meta/subsystem 的 score_source 固定为 material，
    device_scores 留空。黄标列表 section_reviews 与 Word 黄标题/黄句子同一口径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    year = clamp_assessment_year(assessment_year)
    spec = get_subsystem(handler.domain_id, subsystem_id)
    paths = [str(p) for p in file_paths]
    state: dict[str, Any] = {
        "job_id": job_id,
        "status": "running",
        "step": "parse",
        "message": f"正在解析第{handler.no}章材料",
        "domain_id": spec["domain_id"],
        "subsystem_id": spec["id"],
        "chapter_id": handler.chapter_id,
        "file_paths": paths,
        "file_fingerprint": file_fingerprint_value or file_fingerprint(paths),
        "assessment_year": year,
    }

    def ping(**extra: Any) -> None:
        state.update(extra)
        if on_progress:
            on_progress(dict(state))

    ping(step="parse", message="正在读取 Word / Excel（已启用解析缓存）")
    docs = parse_files(paths, work_dir=output_dir / "_converted", use_cache=True)
    if handler.domain_id == "overhead":
        from chapters.overhead.prior_resolve import resolve_prior_docs
        from chapters.overhead.review import review_chapter as _review_chapter

        baseline_tip = "未上传去年报告，使用项目内2025接触网保底年报"
    else:
        from chapters.power.prior_resolve import resolve_prior_docs
        from chapters.power.review import review_chapter as _review_chapter

        baseline_tip = "未上传去年报告，使用项目内2025供电保底年报"

    prior_list = [str(p) for p in (prior_paths or []) if str(p).strip()]
    ping(
        step="parse",
        message="正在读取去年完整报告" if prior_list else baseline_tip,
    )
    prior_hit = resolve_prior_docs(prior_paths=prior_list or None, work_dir=output_dir / "_converted_prior")
    prior_docs = prior_hit.get("docs") or []
    via = prior_hit.get("via") or ""
    if via.startswith("baseline") and prior_list:
        ping(step="parse", message=f"去年报告无法解析，已改用保底年报：{prior_hit.get('source') or ''}")
    ping(step="extract", message=f"正在按第{handler.no}章规则抽取")
    # 触网抽取需要知道 prior 是上传还是保底，以便目录策略一致
    if handler.domain_id == "overhead":
        pack = handler.extract(
            docs,
            year=year,
            prior_docs=prior_docs,
            prior_via=prior_hit.get("via") or "",
        )
    else:
        pack = handler.extract_pack(docs, year=year, prior_docs=prior_docs)
    if isinstance(pack, dict):
        pack["prior_via"] = prior_hit.get("via") or ""
        pack["prior_source_label"] = prior_hit.get("source") or ""
    ping(step="write", message=f"正在按第{handler.no}章目录填入")
    json_path = output_dir / "assessment_result.json"
    docx_path = output_dir / "assessment_report.docx"
    handler.write_docx(pack, docx_path)
    extra = handler.extra_result(pack) if handler.extra_result else {}
    section_reviews = _review_chapter(pack, handler.chapter_id)
    result = {
        "meta": {
            "line_id": f"{handler.domain_label}第{handler.no}章",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "domain_id": spec["domain_id"],
            "domain_name": spec.get("domain_name") or handler.domain_label,
            "subsystem_id": spec["id"],
            "subsystem_name": handler.name,
            "chapter_id": handler.chapter_id,
            "assessment_year": year,
            "file_fingerprint": state["file_fingerprint"],
            "score_source": "material",
        },
        "subsystem": {"total_score": None, "grade": "摘录", "score_source": "material"},
        "line_results": pack.get("line_results") or [],
        "device_scores": [],
        "warnings": pack.get("warnings") or [],
        "section_reviews": section_reviews,
        "report_path": str(docx_path),
        "json_path": str(json_path),
        **extra,
    }
    write_json_report(slim_result(result), json_path)
    register_report(
        state["file_fingerprint"],
        {
            "job_id": job_id,
            "title": handler.job_title(year),
            "scopes": [{"line_id": x.get("line_id"), "segment": ""} for x in pack.get("line_results") or []],
            "report_path": str(docx_path),
            "domain_id": spec["domain_id"],
            "subsystem_id": spec["id"],
            "chapter_id": handler.chapter_id,
        },
    )
    ping(
        step="compose",
        status="completed",
        message=handler.message(pack),
        result=result,
        report_path=str(docx_path),
        json_path=str(json_path),
        line_results=pack.get("line_results") or [],
        device_scores=[],
        device_score_total=0,
        subsystem=result["subsystem"],
        warnings=pack.get("warnings") or [],
        section_reviews=section_reviews,
        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return state


def run_registered_chapter(
    file_paths: list[str | Path],
    *,
    domain_id: str,
    chapter_id: str,
    output_dir: str | Path,
    job_id: str,
    subsystem_id: str = "stray_current",
    assessment_year: int | None = None,
    file_fingerprint_value: str = "",
    on_progress=None,
    prior_paths: list[str | Path] | None = None,
) -> dict[str, Any] | None:
    """按专业+章号查找 HANDLER 再跑。未注册返回 None，接口层只收存、不套供电规则。"""
    handler = get_handler(domain_id, chapter_id)
    if not handler:
        return None
    return run_chapter(
        handler,
        file_paths,
        output_dir=output_dir,
        job_id=job_id,
        subsystem_id=subsystem_id,
        assessment_year=assessment_year,
        file_fingerprint_value=file_fingerprint_value,
        on_progress=on_progress,
        prior_paths=prior_paths,
    )
