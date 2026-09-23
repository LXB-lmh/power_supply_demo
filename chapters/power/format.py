# -*- coding: utf-8 -*-
"""2025 供电年报版式：各章表格列宽、字号、图片限宽。按表头自动套用。

列宽来自 2025 原文 twip，不是按页面百分比重排。调用方传入的 widths 会覆盖自动匹配。
"""
from __future__ import annotations

from typing import Any

from chapters.power.style import (
    CH3_T31_WIDTHS,
    CH3_T32_WIDTHS,
    CH3_T33_WIDTHS,
    CH3_T34_WIDTHS,
    CH3_T35_WIDTHS,
    CH3_T310_WIDTHS,
    CH3_T311_WIDTHS,
    CH3_T312_WIDTHS,
)

from chapters.common.table_layout import CONTENT_TWIPS, even_widths, pad_widths  # noqa: F401 — 兼容旧引用

# 2025 正文区宽度约 14.64cm，图 4-1 按此落幅。
FIGURE_MAX_CX = 5264640
FIGURE_MIN_CX = 360000

# 按表头匹配 2025 各表。3.3.2 与 3.5 都是「线路+区段+设备列」，用有无「时间」列区分。
TABLE_SPECS: list[dict[str, Any]] = [
    {
        "heads": ("序号", "流程名称", "流程描述", "实施人员"),
        "widths": [664, 1738, 3748, 2143],
        "font_pt": 12,
        "jc": None,
    },
    {
        "heads": ("设备评级", "评级范围"),
        "widths": CH3_T31_WIDTHS,
        "font_pt": 12,
        "jc": "center",
        "header_bold": True,
    },
    {
        "heads": ("大类", "中类名称", "包含小类设备"),
        "widths": CH3_T32_WIDTHS,
        "font_pt": 12,
        "jc": None,
        "cell_mar": 0,
        "col_align": ["center", "center", "both"],
        "vmerge": [(0, 1, 10), (0, 11, 16)],
    },
    {
        "heads": ("线路", "区段", "应急电源设备", "配电系统（降压）", "配电系统（牵引）"),
        "widths": CH3_T33_WIDTHS,
        "font_pt": 11,
        "jc": None,
        "require": lambda h: "时间" not in h,
    },
    {
        "heads": ("线路", "区段", "应急电源设备", "变压器设备", "电力电缆设备"),
        "widths": CH3_T34_WIDTHS,
        "font_pt": 11,
        "jc": None,
        "require": lambda h: "时间" not in h and "配电设备" in h,
    },
    {
        "heads": ("线路", "区段", "能耗设备"),
        "widths": CH3_T35_WIDTHS,
        "font_pt": 12,
        "jc": None,
        "require": lambda h: "时间" not in h,
    },
    {
        "heads": ("线路", "区段", "时间", "应急电源设备", "配电系统（降压）"),
        "widths": CH3_T310_WIDTHS,
        "font_pt": 11,
        "jc": "center",
    },
    {
        "heads": ("线路", "区段", "时间", "应急电源设备", "变压器设备"),
        "widths": CH3_T311_WIDTHS,
        "font_pt": 11,
        "jc": "center",
        "require": lambda h: "配电设备" in h,
    },
    {
        "heads": ("线路", "区段", "时间"),
        "widths": CH3_T312_WIDTHS,
        "font_pt": 12,
        "jc": "center",
        "require": lambda h: len(h) == 4,
    },
    {
        "heads": ("大类", "工作项目", "维护周期", "维护内容"),
        "widths": [1035, 1480, 1733, 3181],
        "font_pt": 12,
        "jc": "center",
        "cell_mar": 0,
        "col_align": ["center", "center", "center", "left"],
    },
    {
        "heads": ("工作项目", "维护周期", "维护内容"),
        "widths": [1656, 2136, 3181],
        "font_pt": 12,
        "jc": "center",
        "col_align": ["center", "center", "left"],
    },
    {
        "heads": ("特种设备名称", "规程编号", "名称"),
        "widths": [1573, 2457, 4266],
        "font_pt": 12,
        "jc": None,
        "cell_mar": 0,
    },
    {
        "heads": ("专业", "等级", "2025年"),
        "widths": [1190, 5215, 1889],
        "font_pt": 12,
        "jc": None,
        "cell_mar": 0,
        "require": lambda h: len(h) == 3,
    },
    {
        "heads": ("专业", "等级"),
        "widths": [1190, 3326, 1889, 1889],
        "font_pt": 12,
        "jc": None,
        "cell_mar": 0,
        "require": lambda h: 4 <= len(h) <= 6,
    },
    {
        "heads": ("专业", "等级"),
        "widths": [415, 1293, 846, 846, 844, 844, 844, 844, 844, 845, 860],
        "font_pt": 12,
        "jc": None,
        "cell_mar": 0,
        "require": lambda h: len(h) >= 8,
    },
    {
        "heads": ("序号", "线路", "计划数量（项）", "完成数量（项）"),
        "widths": [631, 1287, 1650, 1647, 1740, 900, 615],
        "font_pt": 12,
        "jc": "center",
    },
    {
        "heads": ("类型", "风险项", "数量"),
        "widths": [2074, 6285, 992],
        "font_pt": 12,
        "jc": None,
    },
    {
        "heads": ("序号", "作业项目", "作业步骤", "隐患描述"),
        "widths": [884, 1467, 1620, 5306],
        "font_pt": 12,
        "jc": None,
    },
    {
        "heads": ("序号", "设备大类", "设备中类", "设备小类"),
        "widths": [567, 850, 1276, 1276, 1843, 1297, 966, 851],
        "font_pt": 10,
        "jc": "center",
    },
    {
        "heads": ("故障令号", "OA令号", "故障维修类型"),
        "widths": [1476, 1354, 1532, 1020, 1701, 1213],
        "font_pt": 10.5,
        "jc": None,
    },
    {
        "heads": ("序号", "名称", "编号"),
        "widths": [877, 3303, 4113],
        "font_pt": 12,
        "jc": None,
    },
    {
        "heads": ("线路", "区段", "大类", "中类", "评估结果"),
        "widths": [600, 700, 650, 750, 650, 820, 820, 820, 780, 850, 854],
        "font_pt": 9,
        "jc": "center",
        "require": lambda h: len(h) >= 10,
    },
]


def _norm_head(cell: Any) -> str:
    return str(cell or "").replace("\n", "").replace(" ", "").strip()


def spec_for(rows: list[list[Any]] | None) -> dict[str, Any]:
    """按首行表头套用 2025 列宽/字号。对不上则均分正文宽度，多列表格略缩小字号。"""
    if not rows:
        return {}
    head = tuple(_norm_head(c) for c in rows[0])
    raw = tuple(str(c or "").strip().replace("\n", "") for c in rows[0])
    for spec in TABLE_SPECS:
        keys = tuple(_norm_head(k) for k in spec["heads"])
        if head[: len(keys)] != keys and raw[: len(spec["heads"])] != spec["heads"]:
            continue
        require = spec.get("require")
        if require and not require(head) and not require(raw):
            continue
        out = {k: v for k, v in spec.items() if k not in {"heads", "require"}}
        out["widths"] = pad_widths(out.get("widths"), len(rows[0]))
        if len(head) >= 7 and "font_pt" not in out:
            out["font_pt"] = 11
        return out
    fallback: dict[str, Any] = {"jc": "center", "widths": even_widths(len(head))}
    if len(head) >= 7:
        fallback["font_pt"] = 11
    return fallback


def merge_table_kwargs(rows: list[list[Any]], kwargs: dict[str, Any]) -> dict[str, Any]:
    """自动套用 + 调用方覆盖。write 里显式传入的 widths/font_pt 优先于表头匹配。"""
    spec = spec_for(rows)
    merged = dict(spec)
    for key, val in kwargs.items():
        if val is not None:
            merged[key] = val
    ncols = len(rows[0]) if rows else 0
    if ncols:
        merged["widths"] = pad_widths(merged.get("widths"), ncols)
    return merged
