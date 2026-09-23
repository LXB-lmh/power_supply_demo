# -*- coding: utf-8 -*-
"""纯文本 / JSON 材料。JSON 若带 devices 列表则转成表，便于和 Excel 走同一套抽取。"""
from __future__ import annotations

import json
from pathlib import Path

from .document_model import Block, DocumentModel


def parse_text(path: Path) -> DocumentModel:
    text = path.read_text(encoding="utf-8")
    blocks: list[Block] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("一、", "二、", "三、", "四、", "五、", "#")):
            blocks.append(Block(type="heading", text=line.lstrip("# ").strip(), level=1))
        else:
            blocks.append(Block(type="paragraph", text=line))
    return DocumentModel(
        source_name=path.name,
        source_path=str(path),
        suffix=path.suffix.lower(),
        blocks=blocks,
    )


def parse_json_material(path: Path) -> DocumentModel:
    data = json.loads(path.read_text(encoding="utf-8"))
    blocks: list[Block] = []
    if isinstance(data, dict):
        meta = []
        for key in ("line", "workshop", "线路", "专业"):
            if key in data:
                meta.append(f"{key}: {data[key]}")
        if meta:
            blocks.append(Block(type="paragraph", text="；".join(meta)))
        devices = data.get("devices") or data.get("设备") or []
        if isinstance(devices, list) and devices and isinstance(devices[0], dict):
            headers = list(devices[0].keys())
            rows = [headers]
            for row in devices:
                rows.append([str(row.get(h, "")) for h in headers])
            blocks.append(Block(type="table", rows=rows))
        else:
            blocks.append(
                Block(type="paragraph", text=json.dumps(data, ensure_ascii=False, indent=2))
            )
    else:
        blocks.append(Block(type="paragraph", text=json.dumps(data, ensure_ascii=False)))
    return DocumentModel(
        source_name=path.name,
        source_path=str(path),
        suffix=".json",
        blocks=blocks,
    )
