# -*- coding: utf-8 -*-
"""去年接触网评估报告：有上传用上传，否则用项目内 2025 触网保底年报。

规则与供电一致：
1. 平台放入了去年完整接触网报告 → 学目录/体例；
2. 没有放入 → 默认加载 prior_baseline_2025_overhead.docx。
3. 上传了但 .doc 无法转换 → 回退保底，不让整单失败。
数据节仍只用当年材料，不用保底报告顶数。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from parsers.document_model import DocumentModel
from parsers.dispatch import parse_file, parse_files

BASELINE_PRIOR_DOCX = Path(__file__).with_name("assets") / "prior_baseline_2025_overhead.docx"
BASELINE_SOURCE_LABEL = "项目保底·2025接触网年报"


def baseline_prior_path() -> Path | None:
    p = BASELINE_PRIOR_DOCX
    return p if p.is_file() else None


def _load_baseline(work_dir: str | Path | None = None) -> dict[str, Any]:
    base = baseline_prior_path()
    if base is None:
        return {"docs": [], "via": "", "source": "", "path": ""}
    try:
        if work_dir is not None:
            docs = parse_files([str(base)], work_dir=Path(work_dir))
        else:
            docs = [parse_file(base)]
        docs = [d for d in docs if d is not None]
        if docs:
            for d in docs:
                d.source_name = BASELINE_SOURCE_LABEL
            return {
                "docs": docs,
                "via": "baseline_2025",
                "source": BASELINE_SOURCE_LABEL,
                "path": str(base),
            }
    except Exception:
        pass
    return {"docs": [], "via": "", "source": "", "path": ""}


def resolve_prior_docs(
    prior_docs: list[DocumentModel] | None = None,
    *,
    prior_paths: list[str | Path] | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    uploaded = [d for d in (prior_docs or []) if d is not None]
    if uploaded:
        name = uploaded[0].source_name or Path(uploaded[0].source_path or "").name
        return {"docs": uploaded, "via": "upload", "source": name, "path": uploaded[0].source_path or ""}

    paths = [Path(p) for p in (prior_paths or []) if str(p).strip()]
    paths = [p for p in paths if p.is_file()]
    if paths:
        docs: list[DocumentModel] = []
        errors: list[str] = []
        for p in paths:
            try:
                if work_dir is not None:
                    docs.extend(parse_files([str(p)], work_dir=Path(work_dir)))
                else:
                    docs.append(parse_file(p))
            except Exception as exc:
                errors.append(f"{p.name}: {exc}")
        docs = [d for d in docs if d is not None]
        if docs:
            return {
                "docs": docs,
                "via": "upload",
                "source": docs[0].source_name or paths[0].name,
                "path": str(paths[0]),
            }
        # 上传 .doc 转不了时回退保底，避免整章评估失败
        hit = _load_baseline(work_dir)
        if hit.get("docs"):
            tip = "；".join(errors[:2]) if errors else "去年报告无法解析"
            hit = dict(hit)
            hit["via"] = "baseline_2025_fallback"
            hit["source"] = f"{BASELINE_SOURCE_LABEL}（上传失败已回退：{tip}）"
            hit["upload_error"] = tip
            return hit

    return _load_baseline(work_dir)
