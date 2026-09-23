# -*- coding: utf-8 -*-
"""把评估结果摘要写成 output/.../assessment_result.json，给网页「评估结果」展示。"""
from __future__ import annotations

import json
from pathlib import Path


def write_json_report(result: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
