# -*- coding: utf-8 -*-
"""接触网年报体例常量。完整目录以 assets/outline_baseline_2025.json 为准。"""
from __future__ import annotations

from chapters.common.table_layout import pad_widths

OVERHEAD_GRADE_COLS = ["接触网（轨）设备"]

STOCK_LEAD = (
    "接触网专业安全库存按照备件清单管理。对于不同厂商、不同型号的核心部件或设施设备，"
    "至少保留必要安全备件。"
)

ENV_LEAD = (
    "接触网设备受温度、湿度、粉尘、雷电、覆冰、沉降、外来侵限及弓架次等因素影响，"
    "按环境因子分项评估如下。"
)

# 表 3-2/3-3/3-4 列宽见 chapters.common.table_copy.WEIGHT_RULE_WIDTHS_7（去年实测，勿均分）。
# 表 3-5a/b 等：2025 触网年报 prior 实测 grid（10 列：线路+锚段数量+A/B/C/D×2）
OH_STATUS_DIST_WIDTHS_10 = [893, 1045, 839, 947, 835, 844, 835, 844, 936, 865]
# 4.2.2 维护周期：人工/去年年报四列表，合计 7429，不要沿用部门稿 108 边距
OH_CYCLE_4COL_WIDTHS = [1035, 1480, 1733, 3181]
OH_CYCLE_TBL_W = 7429
# 个别部门稿多 1 空列时，在末列后均分余宽
STATUS_DIST_TABLE_WIDTHS = pad_widths(OH_STATUS_DIST_WIDTHS_10, 11, total=8883)


def status_table_widths(ncols: int) -> list[int]:
    if ncols <= 0:
        return []
    if ncols == 10:
        return list(OH_STATUS_DIST_WIDTHS_10)
    if ncols == 11:
        return list(STATUS_DIST_TABLE_WIDTHS)
    return pad_widths(OH_STATUS_DIST_WIDTHS_10, ncols, total=8883)
