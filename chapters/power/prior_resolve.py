# -*- coding: utf-8 -*-
"""去年评估报告统一解析：有上传用上传，否则用项目内 2025 保底年报。

全章同一规则：
1. 平台放入了去年完整评估报告 → 从该报告学目录/体例/可复用段；
2. 没有放入 → 默认加载项目内 prior_baseline_2025.docx（2025 供电年报保底）。

数据节（总表、故障、4.4、5.3～5.6 等）仍只用当年材料，不会用保底报告顶数。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from parsers.document_model import DocumentModel
from parsers.dispatch import parse_file, parse_files

# 项目内保底：2025 供电（含能源）完整年报，格式与内容样式以此为准
BASELINE_PRIOR_DOCX = Path(__file__).with_name("assets") / "prior_baseline_2025.docx"
BASELINE_SOURCE_LABEL = "项目保底·2025供电年报"


def baseline_prior_path() -> Path | None:
    p = BASELINE_PRIOR_DOCX
    return p if p.is_file() else None


def resolve_prior_docs(
    prior_docs: list[DocumentModel] | None = None,
    *,
    prior_paths: list[str | Path] | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """统一得到 prior_docs。

    返回：
      docs: list[DocumentModel]
      via: \"upload\" | \"baseline_2025\" | \"\"
      source: 来源说明（文件名或保底标签）
      path: 实际使用的路径（若有）
    """
    # 1) 已解析好的上传稿
    uploaded = [d for d in (prior_docs or []) if d is not None]
    if uploaded:
        name = uploaded[0].source_name or Path(uploaded[0].source_path or "").name
        return {"docs": uploaded, "via": "upload", "source": name, "path": uploaded[0].source_path or ""}

    # 2) 上传路径（尚未解析）
    paths = [Path(p) for p in (prior_paths or []) if str(p).strip()]
    paths = [p for p in paths if p.is_file()]
    if paths:
        docs: list[DocumentModel] = []
        for p in paths:
            try:
                if work_dir is not None:
                    docs.extend(parse_files([str(p)], work_dir=Path(work_dir)))
                else:
                    docs.append(parse_file(p))
            except Exception:
                continue
        docs = [d for d in docs if d is not None]
        if docs:
            return {
                "docs": docs,
                "via": "upload",
                "source": docs[0].source_name or paths[0].name,
                "path": str(paths[0]),
            }

    # 3) 项目内 2025 保底（上传失败或未上传都走这里）
    base = baseline_prior_path()
    if base is not None:
        try:
            if work_dir is not None:
                docs = parse_files([str(base)], work_dir=Path(work_dir))
            else:
                docs = [parse_file(base)]
            docs = [d for d in docs if d is not None]
            if docs:
                # 标题出处用保底标签，不用 prior_baseline_2025.docx 文件名
                for d in docs:
                    d.source_name = BASELINE_SOURCE_LABEL
                via = "baseline_2025_fallback" if paths else "baseline_2025"
                return {
                    "docs": docs,
                    "via": via,
                    "source": BASELINE_SOURCE_LABEL,
                    "path": str(base),
                }
        except Exception:
            pass

    return {"docs": [], "via": "", "source": "", "path": ""}
