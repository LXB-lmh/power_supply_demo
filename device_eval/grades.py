# -*- coding: utf-8 -*-
"""设备状态等级：两份团标第 9.1 条及附录 D 表 D.1、附录 C 各等级划分表口径一致。

A：评价分≥90
B：75≤评价分＜90
C：60≤评价分＜75
D：评价分＜60

附录 A 参数里的优/良/中/差是单项评分档，不是最终 A/B/C/D。
团标未给出优/良/中/差的百分换算数，按已确认口径：优=100、良=80、中=60、差=40。
"""

GRADE_SCORE = {
    "excellent": 100.0,
    "good": 80.0,
    "fair": 60.0,
    "poor": 40.0,
}

GRADE_LABEL = {
    "excellent": "优",
    "good": "良",
    "fair": "中",
    "poor": "差",
}

LABEL_TO_GRADE = {v: k for k, v in GRADE_LABEL.items()}

# 第 9.1 条 A/B/C/D 四档原文（第6部分、第7部分相同）
ABCD_BANDS = (
    {
        "grade": "A",
        "rule": "评价分≥90",
        "status": "“好”“完好”或“完善”",
        "line": "A：评价分≥90，表示状态为“好”“完好”或“完善”；",
    },
    {
        "grade": "B",
        "rule": "75≤评价分＜90",
        "status": "“良”“良好”或“较完善”",
        "line": "B：75≤评价分＜90，表示状态为“良”“良好”或“较完善”；",
    },
    {
        "grade": "C",
        "rule": "60≤评价分＜75",
        "status": "“中”“一般”或“不太完善”",
        "line": "C：60≤评价分＜75，表示状态为“中”“一般”或“不太完善”；",
    },
    {
        "grade": "D",
        "rule": "评价分＜60",
        "status": "“差”或“不完善”",
        "line": "D：评价分＜60，表示状态为“差”或“不完善”。",
    },
)

CLAUSE_9_1_LEAD = {
    "main_hv": "9.1　主变电系统的设施设备的状态评估等级可分为A、B、C和D四个等级。",
    "power": "9.1　供电、能源系统的设施设备的状态评估等级可分为A、B、C和D四个等级。",
}


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def abcd(score: float) -> str:
    """A≥90；B 为 75≤分＜90；C 为 60≤分＜75；D＜60。90 归 A，75 归 B，60 归 C。"""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def band_of(grade: str) -> dict:
    for item in ABCD_BANDS:
        if item["grade"] == grade:
            return dict(item)
    return {"grade": grade, "rule": "", "status": ""}
