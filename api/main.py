# -*- coding: utf-8 -*-
"""FastAPI：上传 → 分章建议 / 按章评估 → 下载 docx。

注意两条线不要混：
- POST /api/classify-materials → 「本章建议」文件名（按内容去重）
- POST /api/jobs → 真正抽取写 Word
未注册的章只收存材料，不套其它专业规则。供电与接触网已分别接入。
"""
from __future__ import annotations

import asyncio
import json
import queue
import re
import shutil
import sys
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.jobs import load_job, public_job, save_job  # noqa: E402
from catalog.classify_materials import classify_paths  # noqa: E402
from catalog.taxonomy import chapter_ready, get_chapter, get_subsystem, public_catalog  # noqa: E402
from paths import OUTPUT, UPLOADS, ensure_dirs  # noqa: E402
from scope.ledger import clamp_assessment_year  # noqa: E402
from scope.names import file_fingerprint  # noqa: E402
from scope.preview import preview_files  # noqa: E402
from scope.registry import list_reports, remove_reports  # noqa: E402
from chapters.run import run_registered_chapter  # noqa: E402
from chapters.common.logic_page_check import (  # noqa: E402
    format_logic_message,
    run_logic_page_check,
    summarize_findings,
)
from chapters.common.logic_export import (  # noqa: E402
    _cn_number,
    build_logic_export_doc,
)
from device_eval.catalog import public_standard, public_standards  # noqa: E402
from device_eval.engine import evaluate_device  # noqa: E402

app = FastAPI(title="供电评估智能报告生成系统", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class DeleteReportsBody(BaseModel):
    fingerprint: str
    job_ids: list[str] = []
    keep_job_id: str = ""
    subsystem_id: str = ""
    chapter_id: str = ""
    domain_id: str = ""


class DeviceEvalBody(BaseModel):
    standard_id: str
    device_id: str
    weights: dict[str, float]
    values: dict[str, dict[str, Any]] = {}


def _persist_state(state: dict) -> dict:
    job = load_job(state["job_id"]) or {}
    job.update(state)
    return save_job(job)


def _run_job(job_id: str) -> None:
    """后台跑一章：解析材料 → 该章 HANDLER 抽取 → 写 Word。失败写入 job.error。"""
    job = load_job(job_id)
    if not job:
        return
    try:
        job["status"] = "running"
        job["step"] = "parse"
        job["message"] = "正在解析材料，台账较大时请稍候"
        job["started_at"] = job.get("started_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_job(job)
        def on_progress(state: dict) -> None:
            state = dict(state)
            state["job_id"] = job_id
            _persist_state(state)

        chapter_id = job.get("chapter_id") or "ch3"
        domain_id = job.get("domain_id") or "power_supply"
        state = run_registered_chapter(
            job["file_paths"],
            domain_id=domain_id,
            chapter_id=chapter_id,
            output_dir=job.get("output_dir") or str(OUTPUT / job_id),
            job_id=job_id,
            subsystem_id=job.get("subsystem_id") or "stray_current",
            assessment_year=job.get("assessment_year"),
            file_fingerprint_value=job.get("file_fingerprint") or "",
            on_progress=on_progress,
            prior_paths=[job["prior_path"]] if job.get("prior_path") else None,
        )
        if state is None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state = {
                "job_id": job_id,
                "status": "completed",
                "step": "completed",
                "finished_at": now,
                "message": (
                    f"材料已收存（{domain_id} · {chapter_id}）。"
                    "本章评估规则尚未制定，不会套用其他专业或其他章节的评分。"
                ),
            }
        if state.get("status") == "completed":
            state["finished_at"] = state.get("finished_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _persist_state(state)
    except Exception as exc:
        job = load_job(job_id) or {"job_id": job_id}
        job["status"] = "failed"
        job["error"] = str(exc)
        job["message"] = str(exc)
        job["trace"] = traceback.format_exc()
        job["finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_job(job)


def _parse_json_form(raw: str, default):
    text = (raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"选择范围格式不正确：{exc}") from exc


def _rel_dest(root: Path, rel: str, index: int) -> Path:
    """按浏览器带来的相对路径落盘，挡住 .. 跳出上传目录。"""
    text = (rel or f"material_{index}").replace("\\", "/").lstrip("/")
    parts = [p for p in Path(text).parts if p not in {"", ".", ".."}]
    if not parts:
        parts = [f"material_{index}.bin"]
    dest = root.joinpath(*parts)
    try:
        dest.resolve().relative_to(root.resolve())
    except ValueError:
        dest = root / f"file_{index}_{parts[-1]}"
    if dest.exists():
        dest = dest.with_name(f"{dest.stem}_{index}{dest.suffix}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


async def _save_uploads(upload_dir: Path, files: list[UploadFile], relpaths_raw: str = "") -> list[str]:
    try:
        rels = json.loads(relpaths_raw or "[]")
    except json.JSONDecodeError:
        rels = []
    if not isinstance(rels, list):
        rels = []
    saved: list[str] = []
    for i, item in enumerate(files):
        rel = ""
        if i < len(rels) and rels[i]:
            rel = str(rels[i])
        if not rel:
            rel = item.filename or f"material_{i}.bin"
        dest = _rel_dest(upload_dir, rel, i)
        # 大文件落盘是同步 IO，放线程池，避免阻塞事件循环导致其他界面请求排队
        await asyncio.to_thread(dest.write_bytes, await item.read())
        saved.append(str(dest))
    return saved


@app.get("/api/parse-cache")
async def parse_cache_info(domain_id: str = "power_supply"):
    """上次分拣解析是否可复用（按专业，落盘在 parse_cache/）。"""
    from parsers.parse_cache import public_cache_info

    ensure_dirs()
    return await asyncio.to_thread(public_cache_info, domain_id)


@app.get("/api/parse-cache/file")
async def parse_cache_file(domain_id: str = "power_supply", relpath: str = ""):
    """读取上次分拣落盘的材料副本，供「本章建议」一键加入。"""
    from fastapi.responses import FileResponse

    from parsers.parse_cache import resolve_stored_material

    ensure_dirs()
    rel = str(relpath or "").strip()
    if not rel:
        raise HTTPException(400, "缺少 relpath")
    path = await asyncio.to_thread(resolve_stored_material, domain_id, rel)
    if not path:
        raise HTTPException(404, "缓存中找不到该文件，请重新完整解析一次")
    return FileResponse(path, filename=path.name)


@app.post("/api/classify-materials/reuse")
async def classify_materials_reuse(
    domain_id: str = Form("power_supply"),
    assessment_year: str = Form(""),
):
    """不重新解析：直接返回该专业上次成功的分拣结果（重启后仍有效）。"""
    from parsers.parse_cache import classify_cache_usable, load_classify_latest

    ensure_dirs()

    def _load_cached() -> dict | None:
        row = load_classify_latest(domain_id)
        return row if classify_cache_usable(row, domain_id) else None

    row = await asyncio.to_thread(_load_cached)
    if not row:
        raise HTTPException(404, "暂无可用缓存（需先完整解析且材料已落盘），请重新解析一次")
    year = clamp_assessment_year(assessment_year or None)
    result = dict(row["result"])
    result["reused_parse_cache"] = True
    result["parse_cache_saved_at"] = row.get("saved_at") or ""
    if year and row.get("assessment_year") and int(row["assessment_year"]) != int(year):
        result["parse_cache_year_note"] = f"缓存为 {row.get('assessment_year')} 年解析，当前选定 {year} 年"
    return result


@app.post("/api/classify-materials")
async def classify_materials(
    files: list[UploadFile] = File(...),
    file_relpaths: str = Form("[]"),
    domain_id: str = Form("power_supply"),
    use_llm: str = Form("true"),
    assessment_year: str = Form(""),
    force_power: str = Form("false"),
    prior_report: UploadFile | None = File(None),
    use_cached: str = Form("false"),
):
    """左侧「解析」：对照去年报告目录，全文扫描材料后分到第 3～11 章。"""
    if not files:
        raise HTTPException(400, "请至少放入一个文件或文件夹")
    ensure_dirs()
    preview_id = uuid.uuid4().hex[:8]
    upload_dir = UPLOADS / f"classify_{preview_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        saved = await _save_uploads(upload_dir, files, file_relpaths)
        rels = _parse_json_form(file_relpaths, [])
        want_llm = str(use_llm).strip().lower() not in {"0", "false", "no"}
        year = clamp_assessment_year(assessment_year or None)
        forced = str(force_power).strip().lower() not in {"0", "false", "no", ""}
        prior_paths: list[str] = []
        if prior_report is not None and (prior_report.filename or "").strip():
            prior_dir = upload_dir / "_prior"
            prior_dir.mkdir(parents=True, exist_ok=True)
            dest = _rel_dest(prior_dir, prior_report.filename, 0)
            await asyncio.to_thread(dest.write_bytes, await prior_report.read())
            prior_paths.append(str(dest))
        want_cached = str(use_cached).strip().lower() in {"1", "true", "yes"}

        def _cached_match() -> dict | None:
            """读取分拣缓存并比对材料指纹；整体放线程池，避免阻塞事件循环。"""
            from concurrent.futures import ThreadPoolExecutor, as_completed

            from parsers.parse_cache import (
                content_sha256,
                files_meta_match,
                load_classify_latest,
            )

            cached = load_classify_latest(domain_id)
            if not cached or not cached.get("result"):
                return None
            live_meta: list[dict[str, str]] = [{} for _ in saved]

            def _meta(i: int) -> tuple[int, dict[str, str]]:
                p = saved[i]
                rel = rels[i] if i < len(rels) else Path(p).name
                return i, {
                    "rel": str(rel).replace("\\", "/"),
                    "name": Path(p).name,
                    "content_sha256": content_sha256(p),
                }

            if len(saved) <= 1:
                hashed = [_meta(0)] if saved else []
            else:
                hashed = []
                with ThreadPoolExecutor(max_workers=min(8, len(saved))) as pool:
                    futs = [pool.submit(_meta, i) for i in range(len(saved))]
                    for fut in as_completed(futs):
                        hashed.append(fut.result())
            for i, meta in hashed:
                live_meta[i] = meta
            digest = content_sha256(prior_paths[0]) if prior_paths else ""
            if files_meta_match(live_meta, cached.get("files") or []) and (
                not prior_paths or str(cached.get("prior_digest") or "") == digest
            ):
                out = dict(cached["result"])
                out["reused_parse_cache"] = True
                out["parse_cache_saved_at"] = cached.get("saved_at") or ""
                return out
            return None

        if want_cached:
            cached_out = await asyncio.to_thread(_cached_match)
            if cached_out is not None:
                return cached_out
        return await asyncio.to_thread(
            classify_paths,
            saved,
            relpaths=rels,
            domain_id=domain_id,
            use_llm=want_llm,
            assessment_year=year,
            force_power=forced,
            prior_paths=prior_paths or None,
        )
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.post("/api/preview")
async def preview_upload(
    files: list[UploadFile] = File(...),
    file_relpaths: str = Form("[]"),
):
    if not files:
        raise HTTPException(400, "请至少上传一个评估材料文件")
    ensure_dirs()
    preview_id = uuid.uuid4().hex[:8]
    upload_dir = UPLOADS / f"preview_{preview_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        saved = await _save_uploads(upload_dir, files, file_relpaths)
        return await asyncio.to_thread(preview_files, saved)
    finally:
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.post("/api/jobs")
async def create_job(
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    mode: str = Form("llm"),
    auto_confirm: bool = Form(False),
    selected_lines: str = Form("[]"),
    selected_segments: str = Form("[]"),
    assessment_year: str = Form(""),
    domain_id: str = Form("power_supply"),
    subsystem_id: str = Form("stray_current"),
    chapter_id: str = Form("ch3"),
    file_relpaths: str = Form("[]"),
    prior_report: UploadFile | None = File(None),
):
    """创建评估任务。供电第 3～11 章后台抽取；规则未接入的章只收存。

    prior_report 是整专业共用的去年完整报告，单独落盘，不并进当年评估材料。
    """
    if not files:
        raise HTTPException(400, "请至少上传一个评估材料文件")
    ensure_dirs()
    spec = get_subsystem(domain_id, subsystem_id)
    chapter = get_chapter(chapter_id)
    lines = _parse_json_form(selected_lines, [])
    segments = _parse_json_form(selected_segments, [])
    year = clamp_assessment_year(assessment_year or None)
    job_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOADS / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = await _save_uploads(upload_dir, files, file_relpaths)
    prior_path = ""
    if prior_report is not None and (prior_report.filename or "").strip():
        prior_dir = upload_dir / "_prior"
        prior_dir.mkdir(parents=True, exist_ok=True)
        dest = _rel_dest(prior_dir, prior_report.filename, 0)
        await asyncio.to_thread(dest.write_bytes, await prior_report.read())
        prior_path = str(dest)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 指纹需读取全部材料字节做哈希，放线程池，避免大材料包阻塞事件循环
    fingerprint = await asyncio.to_thread(file_fingerprint, saved)
    job = {
        "job_id": job_id,
        "status": "queued",
        "step": "upload",
        "message": f"已接收 {len(saved)} 个文件（{spec['domain_name']} · {chapter['name']}）",
        "mode": mode,
        "auto_confirm": auto_confirm,
        "use_llm_writer": True,
        "file_paths": saved,
        "prior_path": prior_path,
        "selected_lines": lines,
        "selected_segments": segments,
        "assessment_year": year,
        "domain_id": spec["domain_id"],
        "subsystem_id": spec["id"],
        "chapter_id": chapter["id"],
        "started_at": now,
        "finished_at": None,
        "file_fingerprint": fingerprint,
        "output_dir": str(OUTPUT / job_id),
        "pending": [],
        "records": [],
    }
    if not chapter_ready(spec["domain_id"], chapter["id"]):
        job["status"] = "completed"
        job["step"] = "completed"
        job["finished_at"] = now
        job["message"] = (
            f"材料已收存（{spec['domain_name']} · 第{chapter['no']}章 {chapter['name']}）。"
            "本章评估规则尚未制定，不会套用其他专业或其他章节的评分。"
        )
        save_job(job)
        return public_job(job)
    save_job(job)
    background.add_task(_run_job, job_id)
    return public_job(job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return public_job(job)


@app.get("/api/catalog")
def catalog():
    return public_catalog()


# ── 逻辑性检测：临时落盘、多文件检测合并（线程内执行）、流式真实进度 ──────────
_LOGIC_DOMAINS = {"power_supply", "overhead", "power"}


async def _save_logic_uploads(
    upload_dir: Path, files: list[UploadFile], relpaths_raw: str
) -> list[Path]:
    """逻辑检测文件平铺落盘到临时目录，返回已保存路径。"""
    try:
        rels = json.loads(relpaths_raw or "[]")
    except Exception:
        rels = []
    if not isinstance(rels, list):
        rels = []
    saved: list[Path] = []

    def _stream_to_disk(up: UploadFile, dest: Path) -> None:
        with dest.open("wb") as f:
            shutil.copyfileobj(up.file, f)

    for i, up in enumerate(files or []):
        name = Path(up.filename or f"file_{i}.bin").name
        rel = str(rels[i] if i < len(rels) else name).replace("\\", "/")
        dest = upload_dir / Path(rel).name
        # 大报告同步落盘会阻塞事件循环，放线程池
        await asyncio.to_thread(_stream_to_disk, up, dest)
        saved.append(dest)
    return saved


def _logic_year(assessment_year: str) -> int | None:
    text = str(assessment_year or "").strip()
    return int(text) if text.isdigit() else None


def _logic_check_result(
    saved: list[Path],
    *,
    mode: str,
    chapter_id: str,
    domain_id: str,
    year: int | None,
    on_progress=None,
) -> dict[str, Any]:
    """对已落盘文件逐个检测并合并去重（CPU/IO 密集，须在线程内调用）。

    on_progress(percent, label) 推送真实阶段进度；多文件时把单文件 0~100 映射到全局分段。
    """
    n = len(saved)
    merged: list[dict[str, str]] = []
    sources: list[str] = []
    unit_count = 0
    llm_used = False
    llm_finding_count = 0
    single_message = ""
    chapter_found_map: dict[int, dict[str, Any]] = {}
    chapter_missing_sets: list[set[int]] = []
    hit: dict[str, Any] = {}
    for idx, path in enumerate(saved):
        if n > 1 and on_progress is not None:
            base = idx * 100 // n
            span = 100 // n

            def _cb(pct, label, _b=base, _s=span, _i=idx):
                global_pct = min(100, _b + round(_s * int(pct) / 100))
                on_progress(global_pct, f"（文件{_i + 1}/{n}）{label}")

            cb = _cb
        else:
            cb = on_progress
        try:
            hit = run_logic_page_check(
                path,
                assessment_year=year,
                mode=mode,
                chapter_id=chapter_id,
                domain_id=domain_id,
                on_progress=cb,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"无法解析 {path.name}：{exc}") from exc
        sources.append(hit.get("source") or path.name)
        unit_count += int(hit.get("unit_count") or 0)
        llm_used = llm_used or bool(hit.get("llm_used"))
        llm_finding_count += int(hit.get("llm_finding_count") or 0)
        single_message = hit.get("message") or single_message
        for row in hit.get("chapters_found") or []:
            no = int(row.get("no") or 0)
            if no and no not in chapter_found_map:
                chapter_found_map[no] = dict(row)
        chapter_missing_sets.append({int(x) for x in (hit.get("chapters_missing") or [])})
        for row in hit.get("findings") or []:
            row = dict(row)
            if n > 1:
                src = hit.get("source") or path.name
                row["section"] = f"{src} {row.get('section') or '正文'}".strip()
            merged.append(row)
    uniq: list[dict[str, str]] = []
    seen: set[tuple] = set()
    for row in merged:
        key = (row.get("kind"), row.get("section"), row.get("note"), row.get("excerpt"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    summary = summarize_findings(uniq)
    message = (
        single_message
        if n == 1
        else format_logic_message(
            uniq,
            domain_id=domain_id,
            mode=mode,
            chapter_id=chapter_id,
        )
    )
    return {
        "ok": True,
        "mode": mode,
        "chapter_id": chapter_id,
        "domain_id": hit.get("domain_id") if saved else domain_id,
        "domain_label": hit.get("domain_label") if saved else "",
        "source": "、".join(sources),
        "unit_count": unit_count,
        "finding_count": len(uniq),
        "summary": summary,
        "findings": uniq,
        "llm_used": llm_used,
        "llm_finding_count": llm_finding_count,
        "chapters_found": [chapter_found_map[k] for k in sorted(chapter_found_map)],
        "chapters_missing": (
            sorted(set.intersection(*chapter_missing_sets)) if chapter_missing_sets else []
        ),
        "message": message,
    }


@app.post("/api/logic-check")
async def logic_check(
    files: list[UploadFile] = File(...),
    file_relpaths: str = Form("[]"),
    mode: str = Form("full"),
    chapter_id: str = Form(""),
    domain_id: str = Form("overhead"),
    assessment_year: str = Form(""),
):
    """逻辑性检测页：只返回条目，不生成报告，不走各章评估抽取。"""
    ensure_dirs()
    check_id = uuid.uuid4().hex[:10]
    upload_dir = UPLOADS / f"logic_{check_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        saved = await _save_logic_uploads(upload_dir, files, file_relpaths)
        if not saved:
            raise HTTPException(400, "未收到文件")
        if (domain_id or "").strip() not in _LOGIC_DOMAINS:
            raise HTTPException(400, "请选择供电报告或触网报告")
        # 检测是 CPU/IO 密集的长任务，放线程池，避免阻塞事件循环
        return await asyncio.to_thread(
            _logic_check_result,
            saved,
            mode=mode or "full",
            chapter_id=chapter_id or "",
            domain_id=domain_id or "overhead",
            year=_logic_year(assessment_year),
        )
    finally:
        # 逻辑检测是临时分析，不留上传副本
        shutil.rmtree(upload_dir, ignore_errors=True)


@app.post("/api/logic-check/stream")
async def logic_check_stream(
    files: list[UploadFile] = File(...),
    file_relpaths: str = Form("[]"),
    mode: str = Form("full"),
    chapter_id: str = Form(""),
    domain_id: str = Form("overhead"),
    assessment_year: str = Form(""),
):
    """逻辑性检测（流式）：NDJSON 逐行推送真实阶段进度，最后一行为 result 或 error。"""
    ensure_dirs()
    check_id = uuid.uuid4().hex[:10]
    upload_dir = UPLOADS / f"logic_{check_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        saved = await _save_logic_uploads(upload_dir, files, file_relpaths)
    except Exception:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    if not saved:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(400, "未收到文件")
    if (domain_id or "").strip() not in _LOGIC_DOMAINS:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(400, "请选择供电报告或触网报告")
    year = _logic_year(assessment_year)
    q: queue.Queue = queue.Queue()
    sentinel = object()

    def _worker() -> None:
        try:
            q.put({"type": "progress", "percent": 2, "label": "已接收文件，开始检测…"})

            def _on_progress(pct: int, label: str) -> None:
                q.put({"type": "progress", "percent": int(pct), "label": str(label)})

            data = _logic_check_result(
                saved,
                mode=mode or "full",
                chapter_id=chapter_id or "",
                domain_id=domain_id or "overhead",
                year=year,
                on_progress=_on_progress,
            )
            q.put({"type": "result", "data": data})
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc) or "检测失败"
            q.put({"type": "error", "detail": str(detail)})
        finally:
            # 逻辑检测是临时分析，不留上传副本；检测线程结束后再清理
            shutil.rmtree(upload_dir, ignore_errors=True)
            q.put(sentinel)

    async def _event_stream():
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        while True:
            evt = await asyncio.to_thread(q.get)
            if evt is sentinel:
                break
            yield (json.dumps(evt, ensure_ascii=False) + "\n").encode("utf-8")

    return StreamingResponse(
        _event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/logic-check/export")
async def logic_check_export(req: Request):
    """导出检测结果 Word：前端回传结果 JSON，内存生成 docx 返回，不落盘、不影响检测。"""
    from urllib.parse import quote

    try:
        payload = await req.json()
    except Exception as exc:
        raise HTTPException(400, "导出数据格式不正确") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "导出数据格式不正确")
    data = await asyncio.to_thread(build_logic_export_doc, payload)

    domain = str(payload.get("domain_label") or "评估报告").strip()
    ymd = datetime.now().strftime("%Y%m%d")
    name = f"逻辑性检测结果-{domain}-{ymd}"
    if str(payload.get("mode")) == "chapter":
        m = re.search(r"(\d{1,2})", str(payload.get("chapter_id") or ""))
        if m:
            name += f"-第{_cn_number(int(m.group(1)))}章"
    filename = name + ".docx"
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"logic_export.docx\"; filename*=UTF-8''{quote(filename)}"
        )
    }
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


@app.get("/api/logic-check/download/{check_dir}/{filename}")
def logic_check_download(check_dir: str, filename: str):
    """下载逻辑性检测标黄稿（仅 uploads/logic_* 目录）。"""
    safe_dir = Path(check_dir).name
    safe_name = Path(filename).name
    if not safe_dir.startswith("logic_"):
        raise HTTPException(400, "无效路径")
    path = UPLOADS / safe_dir / safe_name
    if not path.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(
        path,
        filename=safe_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/reports")
def get_reports(fingerprint: str = "", subsystem_id: str = "", domain_id: str = "", chapter_id: str = ""):
    if not fingerprint:
        raise HTTPException(400, "缺少文件标识")
    return {
        "fingerprint": fingerprint,
        "reports": list_reports(
            fingerprint,
            subsystem_id or None,
            domain_id=domain_id or None,
            chapter_id=chapter_id or None,
        ),
    }


@app.post("/api/reports/delete")
def delete_reports(body: DeleteReportsBody):
    if not body.fingerprint:
        raise HTTPException(400, "缺少文件标识")
    removed = remove_reports(
        body.fingerprint,
        body.job_ids or None,
        keep_job_id=body.keep_job_id or None,
    )
    return {
        "removed": removed,
        "reports": list_reports(
            body.fingerprint,
            body.subsystem_id or None,
            domain_id=body.domain_id or None,
            chapter_id=body.chapter_id or None,
        ),
    }


@app.get("/api/jobs/{job_id}/report")
def download_report(job_id: str):
    job = load_job(job_id)
    path = Path((job or {}).get("report_path") or "")
    fallback = OUTPUT / job_id / "assessment_report.docx"
    if not path.exists():
        path = fallback
    if not path.exists():
        raise HTTPException(404, "报告尚未生成或不存在")
    spec = get_subsystem(job.get("domain_id"), job.get("subsystem_id")) if job else None
    chapter = get_chapter(job.get("chapter_id")) if job else None
    domain_name = (spec or {}).get("domain_name") or "评估"
    chapter_name = (chapter or {}).get("name") or (spec or {}).get("name") or "评估"
    return FileResponse(
        path,
        filename=f"{domain_name}-{chapter_name}-{job_id}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/device-eval/standards")
def device_eval_standards():
    """团标设备评估入口列表；与各章报告生成无关。"""
    return {"standards": public_standards()}


@app.get("/api/device-eval/catalog")
def device_eval_catalog(standard_id: str):
    try:
        return public_standard(standard_id)
    except KeyError:
        raise HTTPException(404, "未找到该评估标准") from None


@app.post("/api/device-eval/evaluate")
def device_eval_run(body: DeviceEvalBody):
    try:
        return evaluate_device(body.standard_id, body.device_id, body.weights, body.values)
    except KeyError:
        raise HTTPException(404, "未找到该设备") from None


@app.get("/api/health")
def health():
    return {"ok": True, "default_domain": "power_supply"}


frontend_dist = ROOT / "frontend" / "dist"
assets_dir = frontend_dist / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/")
def index_page():
    index = frontend_dist / "index.html"
    if index.exists():
        return FileResponse(
            index,
            media_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>供电评估</title></head>
<body>
<h1>接口已启动，网页文件尚未打包</h1>
<p>请在 frontend 目录执行 npm run build 后重新启动。</p>
<p><a href="/api/health">检查接口</a></p>
</body></html>""",
        status_code=200,
    )
