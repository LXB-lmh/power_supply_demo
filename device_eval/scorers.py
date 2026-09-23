# -*- coding: utf-8 -*-
"""把附录 A「评分计算规则」编成可执行的输入类型（硬规则，不用大模型）。"""
from __future__ import annotations

import re

from device_eval.grades import GRADE_LABEL

_SPACE = re.compile(r"\s+")
_GRADE_RE = re.compile(r"([优良中差])\s*[（(](.*?)[）)]")
_WEIGHT_RANGE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*[-~～—–]+\s*(\d+(?:\.\d+)?)\s*%"
)
_WEIGHT_ONE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def compact(text: str) -> str:
    return _SPACE.sub("", text or "")


def parse_weight_range(text: str) -> tuple[float | None, float | None]:
    raw = text or ""
    found = _WEIGHT_RANGE.search(raw)
    if found:
        return float(found.group(1)), float(found.group(2))
    ones = _WEIGHT_ONE.findall(raw)
    if len(ones) == 1:
        value = float(ones[0])
        return value, value
    if len(ones) >= 2:
        return float(ones[0]), float(ones[1])
    return None, None


def extract_options(rule: str) -> list[dict]:
    seen: set[str] = set()
    options: list[dict] = []
    mapping = {"优": "excellent", "良": "good", "中": "fair", "差": "poor"}
    for match in _GRADE_RE.finditer(rule or ""):
        grade = mapping[match.group(1)]
        if grade in seen:
            continue
        seen.add(grade)
        options.append(
            {
                "grade": grade,
                "value": grade,
                "label": f"{match.group(1)}：{match.group(2).strip()}",
                "text": match.group(2).strip(),
            }
        )
    return options


def _select_grade(options: list[dict], label: str) -> list[dict]:
    return [
        {
            "key": "grade",
            "label": label,
            "type": "select",
            "options": options,
        }
    ]


def _num(key: str, label: str, unit: str = "", default=None, hint: str = "") -> dict:
    field = {"key": key, "label": label, "type": "number", "unit": unit}
    if default is not None:
        field["default"] = default
    if hint:
        field["hint"] = hint
    return field


def _bands(rules: list[dict], unit: str = "", field: str = "value") -> dict:
    return {"kind": "bands", "field": field, "unit": unit, "rules": rules}


def _le_grades(thresholds: list[tuple[str, float]]) -> list[dict]:
    """按顺序：|x| 或 x 小于等于各档。"""
    rules = [{"grade": grade, "op": "le", "v": value} for grade, value in thresholds]
    return rules


def classify(name: str, hint: str, rule: str) -> dict:
    """返回 input / scorer / fields / options。"""
    options = extract_options(rule)
    c_rule = compact(rule)
    c_name = compact(name)

    if "弓架次" in name:
        return {
            "input": "bow",
            "options": [],
            "fields": [
                _num(
                    "bow_count",
                    "弓架次总和",
                    "次",
                    hint="团标公式：（1-弓架次总和/200万）×100",
                )
            ],
            "scorer": {"kind": "bow", "denom": 2_000_000},
        }

    if "规程年限" in rule and "max" in rule.lower():
        return {
            "input": "max_ratio",
            "options": [],
            "fields": [
                _num(
                    "max_ratio",
                    "max（部件使用年限×评估系数/规程年限）",
                    "",
                    hint="填 0～1 的小数，例如 0.40",
                )
            ],
            "scorer": {"kind": "max_ratio"},
        }

    if "100*（30" in c_rule or "100*(30" in c_rule.replace("－", "-"):
        return {
            "input": "life",
            "options": [],
            "fields": [_num("age", "使用年限", "年")],
            "scorer": {"kind": "life", "fixed_design": 30},
        }

    life_compact = c_rule.replace("（", "").replace("）", "").replace("－", "-")
    if "设计使用寿命-使用年限" in life_compact and "故障" not in c_name:
        fields = [
            _num("design_life", "设计使用寿命", "年"),
            _num("age", "使用年限", "年"),
        ]
        return {
            "input": "life",
            "options": [],
            "fields": fields,
            "scorer": {"kind": "life"},
        }

    if "故障率" in name and ("100－" in rule or "100-" in c_rule):
        return {
            "input": "fault_rate",
            "options": [],
            "fields": [
                _num("rate", "故障率", "%"),
                _num("n", "故障系数 n"),
                {
                    "key": "in_fault",
                    "label": "当前处于故障状态（故障状态下该参数不得分）",
                    "type": "checkbox",
                    "default": False,
                },
            ],
            "scorer": {"kind": "fault_rate"},
        }

    if ("100－" in rule or "100-" in c_rule) and "故障" in (name + rule):
        return {
            "input": "fault",
            "options": [],
            "fields": [
                _num("count", "全寿命周期累计故障数", "次"),
                _num("n", "故障系数 n"),
                {
                    "key": "in_fault",
                    "label": "当前处于故障状态（故障状态下该参数不得分）",
                    "type": "checkbox",
                    "default": False,
                },
            ],
            "scorer": {"kind": "fault"},
        }

    if "23~27" in c_rule or "23～27" in c_rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "℃")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "between", "lo": 23, "hi": 27},
                    {"grade": "good", "op": "between", "lo": 0, "hi": 23, "hi_inc": False},
                    {"grade": "fair", "op": "between", "lo": 27, "hi": 30, "lo_inc": False},
                    {
                        "grade": "poor",
                        "op": "or",
                        "items": [{"op": "lt", "v": 0}, {"op": "gt", "v": 30}],
                    },
                ],
                "℃",
            ),
        }

    if "温度0~26" in c_rule or "温度0～26" in c_rule:
        poor_items = [{"op": "gt", "v": 45}]
        if "低于0" in rule:
            poor_items.append({"op": "lt", "v": 0})
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "℃")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "between", "lo": 0, "hi": 26},
                    {"grade": "good", "op": "between", "lo": 26, "hi": 35, "lo_inc": False},
                    {"grade": "fair", "op": "between", "lo": 35, "hi": 45, "lo_inc": False},
                    {"grade": "poor", "op": "or", "items": poor_items},
                ],
                "℃",
            ),
        }

    if "%RH" in rule or "湿度0~65" in c_rule or "湿度0～65" in c_rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "%RH")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "between", "lo": 0, "hi": 65},
                    {"grade": "good", "op": "between", "lo": 65, "hi": 70, "lo_inc": False},
                    {"grade": "fair", "op": "between", "lo": 70, "hi": 75, "lo_inc": False},
                    {"grade": "poor", "op": "gt", "v": 75},
                ],
                "%RH",
            ),
        }

    if "ppm" in rule.lower() or "微水" in name:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "ppm")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "lt", "v": 100},
                    {"grade": "good", "op": "between", "lo": 100, "hi": 200, "hi_inc": False},
                    {"grade": "fair", "op": "between", "lo": 200, "hi": 300, "hi_inc": False},
                    {"grade": "poor", "op": "ge", "v": 300},
                ],
                "ppm",
            ),
        }

    if "容量100%" in c_rule:
        return {
            "input": "capacity",
            "options": options,
            "fields": [_num("value", "蓄电池当前容量", "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "ge", "v": 100},
                    {"grade": "good", "op": "gt", "v": 90},
                    {"grade": "fair", "op": "ge", "v": 80},
                    {"grade": "poor", "op": "lt", "v": 80},
                ],
                "%",
            ),
        }

    if "380V±" in c_rule or "380V±" in rule:
        return {
            "input": "voltage",
            "options": options,
            "fields": [
                _num("measured", "实测电压", "V"),
                _num("nominal", "额定电压", "V", default=380),
            ],
            "scorer": {
                "kind": "abs_pct",
                "rules": _le_grades(
                    [("excellent", 1), ("good", 3), ("fair", 5), ("poor", 999)]
                ),
            },
        }

    if "220V±" in c_rule:
        return {
            "input": "voltage",
            "options": options,
            "fields": [
                _num("measured", "实测电压", "V"),
                _num("nominal", "额定电压", "V", default=220),
            ],
            "scorer": {
                "kind": "abs_pct",
                "rules": _le_grades(
                    [("excellent", 5), ("good", 8), ("fair", 10), ("poor", 999)]
                ),
            },
        }

    if "额定容值" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "相对额定容值的偏差绝对值", "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "le", "v": 3},
                    {"grade": "good", "op": "le", "v": 5},
                    {"grade": "fair", "op": "le", "v": 10},
                    {"grade": "poor", "op": "gt", "v": 10},
                ],
                "%",
            ),
        }

    if "绝缘电阻值比" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "绝缘电阻值比（本次/上次×100）", "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "ge", "v": 80},
                    {"grade": "good", "op": "between", "lo": 75, "hi": 80, "hi_inc": False},
                    {"grade": "fair", "op": "between", "lo": 70, "hi": 75, "hi_inc": False},
                    {"grade": "poor", "op": "lt", "v": 70},
                ],
                "%",
            ),
        }

    if "1600kVA" in rule:
        return {
            "input": "winding_dc",
            "options": options,
            "fields": [
                {
                    "key": "kva_class",
                    "label": "变压器容量分档",
                    "type": "select",
                    "options": [
                        {"value": "gt_1600", "label": "1600kVA以上三相变压器"},
                        {"value": "le_1600", "label": "1600kVA及以下三相变压器"},
                    ],
                },
                _num("unbalance", "各相测得值相互差值占平均值", "%"),
            ],
            "scorer": {"kind": "winding_dc"},
        }

    if "20MΩ" in rule and "10MΩ" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "MΩ")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "gt", "v": 20},
                    {"grade": "good", "op": "gt", "v": 10},
                    {"grade": "fair", "op": "ge", "v": 5},
                    {"grade": "poor", "op": "lt", "v": 5},
                ],
                "MΩ",
            ),
        }

    if "≥10MΩ" in rule and "5MΩ" in rule and "3MΩ" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "MΩ")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "ge", "v": 10},
                    {"grade": "good", "op": "between", "lo": 5, "hi": 10, "hi_inc": False},
                    {"grade": "fair", "op": "between", "lo": 3, "hi": 5, "hi_inc": False},
                    {"grade": "poor", "op": "lt", "v": 3},
                ],
                "MΩ",
            ),
        }

    if "＞5MΩ" in rule or ">5MΩ" in c_rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "MΩ")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "gt", "v": 5},
                    {"grade": "good", "op": "gt", "v": 2},
                    {"grade": "fair", "op": "ge", "v": 0.5},
                    {"grade": "poor", "op": "lt", "v": 0.5},
                ],
                "MΩ",
            ),
        }

    if "μΩ" in rule or "μΩ" in c_rule or "回路电阻" in name:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "μΩ")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "lt", "v": 50},
                    {"grade": "good", "op": "between", "lo": 50, "hi": 100},
                    {"grade": "fair", "op": "between", "lo": 100, "hi": 150, "lo_inc": False},
                    {"grade": "poor", "op": "gt", "v": 150},
                ],
                "μΩ",
            ),
        }

    if "泄漏电流" in name or "mA" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "mA")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "lt", "v": 20},
                    {"grade": "good", "op": "lt", "v": 40},
                    {"grade": "fair", "op": "lt", "v": 50},
                    {"grade": "poor", "op": "ge", "v": 50},
                ],
                "mA",
            ),
        }

    if "无误差" in rule and ("2%" in rule or "＜2%" in rule):
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "动作数值误差", "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "lt", "v": 2},
                    {"grade": "fair", "op": "between", "lo": 2, "hi": 5, "hi_inc": False},
                    {"grade": "poor", "op": "ge", "v": 5},
                ],
                "%",
            ),
        }

    if "动作数值误差" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "动作数值误差", "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "lt", "v": 1},
                    {"grade": "good", "op": "lt", "v": 3},
                    {"grade": "fair", "op": "le", "v": 5},
                    {"grade": "poor", "op": "gt", "v": 5},
                ],
                "%",
            ),
        }

    if "出厂试验电压" in rule:
        return {
            "input": "withstand",
            "options": options,
            "fields": [
                {
                    "key": "reached",
                    "label": "试验电压达到出厂试验电压的 80%",
                    "type": "checkbox",
                    "default": False,
                }
            ],
            "scorer": {"kind": "withstand"},
        }

    if "CPU" in name or "负荷率" in name:
        if "小于65" in rule or "＜65" in c_rule:
            return {
                "input": "number",
                "options": options,
                "fields": [_num("value", name, "%")],
                "scorer": _bands(
                    [
                        {"grade": "excellent", "op": "lt", "v": 65},
                        {"grade": "poor", "op": "ge", "v": 65},
                    ],
                    "%",
                ),
            }
        if ("小于70" in rule or "＜70" in c_rule) and "通讯" in name:
            return {
                "input": "number",
                "options": options,
                "fields": [_num("value", name, "%")],
                "scorer": _bands(
                    [
                        {"grade": "excellent", "op": "lt", "v": 70},
                        {"grade": "poor", "op": "ge", "v": 70},
                    ],
                    "%",
                ),
            }
        if "<35" in rule or "＜35" in c_rule:
            return {
                "input": "number",
                "options": options,
                "fields": [_num("value", name, "%")],
                "scorer": _bands(
                    [
                        {"grade": "excellent", "op": "lt", "v": 35},
                        {"grade": "good", "op": "between", "lo": 35, "hi": 50},
                        {"grade": "fair", "op": "between", "lo": 50, "hi": 70, "lo_inc": False},
                        {"grade": "poor", "op": "gt", "v": 70},
                    ],
                    "%",
                ),
            }
        if "小于20" in rule or "<20" in rule or "＜20" in c_rule:
            return {
                "input": "number",
                "options": options,
                "fields": [_num("value", name, "%")],
                "scorer": _bands(
                    [
                        {"grade": "excellent", "op": "lt", "v": 20},
                        {"grade": "good", "op": "between", "lo": 20, "hi": 50},
                        {"grade": "fair", "op": "between", "lo": 50, "hi": 70, "lo_inc": False},
                        {"grade": "poor", "op": "gt", "v": 70},
                    ],
                    "%",
                ),
            }
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", name, "%")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "lt", "v": 30},
                    {"grade": "good", "op": "between", "lo": 30, "hi": 50},
                    {"grade": "fair", "op": "between", "lo": 50, "hi": 70, "lo_inc": False},
                    {"grade": "poor", "op": "gt", "v": 70},
                ],
                "%",
            ),
        }

    if "跳闸" in name:
        if "≤5" in rule or "跳闸次数≤5" in c_rule or "<=5" in c_rule:
            return {
                "input": "number",
                "options": options,
                "fields": [_num("value", "年度跳闸次数", "次")],
                "scorer": _bands(
                    [
                        {"grade": "excellent", "op": "eq", "v": 0},
                        {"grade": "good", "op": "le", "v": 5},
                        {"grade": "fair", "op": "le", "v": 10},
                        {"grade": "poor", "op": "gt", "v": 10},
                    ],
                    "次",
                ),
            }
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "年度跳闸次数", "次")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "eq", "v": 1},
                    {"grade": "fair", "op": "eq", "v": 2},
                    {"grade": "poor", "op": "ge", "v": 3},
                ],
                "次",
            ),
        }

    if "电缆破损" in name or "电缆绝缘破损" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "发现电缆绝缘破损次数", "次")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "le", "v": 2},
                    {"grade": "fair", "op": "le", "v": 5},
                    {"grade": "poor", "op": "gt", "v": 5},
                ],
                "次",
            ),
        }

    if "单回路电缆故障" in name or "造成1次电缆故障" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "电缆绝缘击穿故障次数", "次")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "eq", "v": 1},
                    {"grade": "fair", "op": "eq", "v": 2},
                    {"grade": "poor", "op": "ge", "v": 3},
                ],
                "次",
            ),
        }

    if "模块工作" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "工作不正常的模块数", "个")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "eq", "v": 1},
                    {"grade": "fair", "op": "eq", "v": 2},
                    {"grade": "poor", "op": "ge", "v": 3},
                ],
                "个",
            ),
        }

    if "靴轨冲突" in name or "轨靴冲突" in rule:
        return {
            "input": "number",
            "options": options,
            "fields": [_num("value", "轨靴冲突起数", "起")],
            "scorer": _bands(
                [
                    {"grade": "excellent", "op": "eq", "v": 0},
                    {"grade": "good", "op": "between", "lo": 1, "hi": 4},
                    {"grade": "fair", "op": "between", "lo": 5, "hi": 9},
                    {"grade": "poor", "op": "ge", "v": 10},
                ],
                "起",
            ),
        }

    if options:
        return {
            "input": "choice",
            "options": options,
            "fields": _select_grade(options, name),
            "scorer": {"kind": "choice"},
        }

    return {
        "input": "choice",
        "options": [
            {"grade": g, "value": g, "label": GRADE_LABEL[g], "text": GRADE_LABEL[g]}
            for g in ("excellent", "good", "fair", "poor")
        ],
        "fields": _select_grade(
            [
                {"grade": g, "value": g, "label": GRADE_LABEL[g], "text": GRADE_LABEL[g]}
                for g in ("excellent", "good", "fair", "poor")
            ],
            name,
        ),
        "scorer": {"kind": "choice"},
    }
