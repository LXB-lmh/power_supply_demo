# -*- coding: utf-8 -*-
"""从附录 A 评定表 JSON 编出设备目录（跳过事故照明屏、蓄电池屏：无独立评定表）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from device_eval.scorers import classify, parse_weight_range

DATA_DIR = Path(__file__).resolve().parent / "data"

SKIP_DEVICES = ("事故照明屏", "蓄电池屏")

STANDARDS = (
    {
        "id": "main_hv",
        "name": "主变电系统设备评估",
        "short": "主变电系统",
        "file": "tables_p6.json",
        "standard": "上海轨道交通运营设施设备状态评估规范 第6部分：主变电系统",
    },
    {
        "id": "power",
        "name": "供电（含能源系统）设备评估",
        "short": "供电（含能源系统）",
        "file": "tables_p7.json",
        "standard": "上海城市轨道交通设施设备运营评估规范 第7部分：供电（含能源系统）",
    },
)

_TITLE_NUM = re.compile(r"^表\s*A?\s*\d+\s*")


def _clean(text: str) -> str:
    return (text or "").replace("\u3000", " ").replace("　", " ").strip()


def normalize_title(title: str) -> str:
    text = _clean(title)
    text = _TITLE_NUM.sub("", text)
    text = text.replace("（续）", "").replace("(续)", "")
    if text.endswith("设备评定表"):
        text = text[: -len("设备评定表")]
    elif text.endswith("评定表"):
        text = text[: -len("评定表")]
    return re.sub(r"\s+", " ", text).strip()


def split_device_names(core: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in core:
        if ch in "（(":
            depth += 1
            buf.append(ch)
        elif ch in "）)":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch in "/、" and depth == 0:
            item = "".join(buf).strip()
            if item:
                parts.append(item)
            buf = []
        else:
            buf.append(ch)
    item = "".join(buf).strip()
    if item:
        parts.append(item)
    return parts or [core]


def _parse_param_row(row: list[str]) -> dict | None:
    cells = [_clean(c) for c in (row or [])]
    if not cells or not cells[0]:
        return None
    name = cells[0]
    if name in ("状态参数", "组成设备", "权重"):
        return None
    if name.startswith("注释"):
        return None
    hint, weight_text, rule = "", "", ""
    if len(cells) >= 4:
        hint, weight_text, rule = cells[1], cells[2], cells[3]
    elif len(cells) == 3:
        if "建议取值范围" in cells[1]:
            weight_text, rule = cells[1], cells[2]
        else:
            hint, rule = cells[1], cells[2]
            if "建议取值范围" in cells[2]:
                weight_text, rule = cells[2], cells[1]
    elif len(cells) == 2:
        rule = cells[1]
    else:
        return None
    applies = None
    match = re.search(r"^(.*?)\s*/\s*[（(]([^）)]+)[）)]\s*$", name)
    if match:
        name = match.group(1).strip()
        applies = match.group(2).strip()
    lo, hi = parse_weight_range(weight_text)
    spec = classify(name, hint, rule)
    return {
        "name": name,
        "hint": hint,
        "rule_text": rule,
        "weight_min": lo,
        "weight_max": hi,
        "applies_tag": applies,
        **spec,
    }


def _devices_for_tag(tag: str | None, names: list[str]) -> list[str]:
    if not tag:
        return names
    compact_tag = re.sub(r"\s+", "", tag)
    exact = [n for n in names if re.sub(r"\s+", "", n) == compact_tag]
    if exact:
        return exact
    hits = [n for n in names if tag in n]
    return hits or names


def _scale_defaults(params: list[dict]) -> None:
    if not params:
        return
    mids = []
    for param in params:
        lo, hi = param.get("weight_min"), param.get("weight_max")
        if lo is None and hi is None:
            mids.append(0.0)
        elif lo is None:
            mids.append(float(hi))
        elif hi is None:
            mids.append(float(lo))
        else:
            mids.append((float(lo) + float(hi)) / 2)
    total = sum(mids)
    n = len(params)
    if total <= 0:
        even = round(100 / n, 1)
        for i, param in enumerate(params):
            param["weight_default"] = round(100 - even * (n - 1), 1) if i == n - 1 else even
        return
    raw = [m / total * 100 for m in mids]
    rounded = [round(x, 1) for x in raw[:-1]]
    rounded.append(round(100 - sum(rounded), 1))
    for param, weight in zip(params, rounded):
        param["weight_default"] = weight


def _param_id(name: str, used: set[str]) -> str:
    pid = re.sub(r"\s+", "_", name)
    base = pid
    i = 2
    while pid in used:
        pid = f"{base}_{i}"
        i += 1
    used.add(pid)
    return pid


def _subsystem_for(standard_id: str, name: str) -> tuple[str, str]:
    n = name
    if standard_id == "main_hv":
        if n in ("EPS", "交直流屏"):
            return "emergency", "应急电源"
        if any(k in n for k in ("主变压器", "接地变压器", "电力变压器")):
            return "transformer", "变压器"
        if "电缆" in n:
            return "cable", "电力电缆"
        if any(k in n for k in ("采集", "现场")):
            return "aux", "生产辅助系统"
        if "信号屏" in n:
            return "scada", "电力监控系统"
        return "distribution", "配电系统"

    if n in ("EPS", "UPS", "交直流屏"):
        return "emergency", "应急电源"
    if any(k in n for k in ("参比", "排流", "单项导通")):
        return "stray", "杂散电流"
    if any(k in n for k in ("信号变压器", "电力变压器", "整流变压器")):
        return "transformer", "变压器"
    if "750V" in n or n.startswith("APM"):
        return "apm", "APM系统"
    if any(k in n for k in ("配电箱", "智能照明", "照明灯具")):
        return "lv400", "低压配电系统（400V）"
    if any(k in n for k in ("接触网", "隔离开关")) or (n == "三轨"):
        return "oh", "接触网（轨）"
    if "电缆" in n:
        return "cable", "电力电缆"
    if "电能计量" in n:
        return "energy", "能耗设备"
    if any(k in n for k in ("中央信号", "复视", "复示", "调度工作站", "网关机", "SCADA")):
        return "scada", "电力监控系统"
    if any(k in n for k in ("采集", "可视化接地")):
        return "aux", "生产辅助系统"
    return "distribution", "配电系统"


def build_standard(tables: list[dict], spec: dict) -> dict:
    grouped: dict[str, list[list[str]]] = {}
    order: list[str] = []
    for table in tables:
        title = _clean(table.get("title") or "")
        if "权重分配" in title:
            continue
        if "评定" not in title and "状态参数" not in " ".join(
            (table.get("rows") or [[]])[0]
        ):
            continue
        core = normalize_title(title)
        if not core:
            continue
        grouped.setdefault(core, [])
        if core not in order:
            order.append(core)
        grouped[core].extend(table.get("rows") or [])

    devices: list[dict] = []
    for core in order:
        names = [n for n in split_device_names(core) if n not in SKIP_DEVICES]
        if not names:
            continue
        parsed: list[dict] = []
        for row in grouped[core]:
            item = _parse_param_row(row)
            if item:
                parsed.append(item)
        for name in names:
            used: set[str] = set()
            params = []
            for item in parsed:
                allowed = _devices_for_tag(item.get("applies_tag"), names)
                if name not in allowed:
                    continue
                param = {k: v for k, v in item.items() if k != "applies_tag"}
                param["id"] = _param_id(item["name"], used)
                params.append(param)
            if not params:
                continue
            _scale_defaults(params)
            sub_id, sub_name = _subsystem_for(spec["id"], name)
            devices.append(
                {
                    "id": f"{spec['id']}:{name}",
                    "name": name,
                    "table": core,
                    "subsystem_id": sub_id,
                    "subsystem_name": sub_name,
                    "params": params,
                }
            )

    sub_order: list[str] = []
    sub_map: dict[str, dict] = {}
    for device in devices:
        sid = device["subsystem_id"]
        if sid not in sub_map:
            sub_order.append(sid)
            sub_map[sid] = {
                "id": sid,
                "name": device["subsystem_name"],
                "devices": [],
            }
        sub_map[sid]["devices"].append(device)

    return {
        "id": spec["id"],
        "name": spec["name"],
        "short": spec["short"],
        "standard": spec["standard"],
        "subsystems": [sub_map[i] for i in sub_order],
        "devices": devices,
    }


def load_tables(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def build_all() -> dict[str, dict]:
    out = {}
    for spec in STANDARDS:
        out[spec["id"]] = build_standard(load_tables(spec["file"]), spec)
    return out
