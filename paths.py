# -*- coding: utf-8 -*-
"""项目根目录和三类落盘路径。

- output：各次评估生成的 Word / JSON
- jobs：任务进度 json（网页轮询用）
- uploads：上传材料副本
不要把正式年报手改进 output 里已生成的 docx，应改抽取规则后重跑。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
JOBS = ROOT / "jobs"
UPLOADS = ROOT / "uploads"
PARSE_CACHE = ROOT / "parse_cache"


def ensure_dirs() -> None:
    """三个目录不存在就建，避免首次启动写文件失败。"""
    for p in (OUTPUT, JOBS, UPLOADS, PARSE_CACHE):
        p.mkdir(parents=True, exist_ok=True)
