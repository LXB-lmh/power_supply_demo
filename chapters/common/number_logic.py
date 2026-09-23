# -*- coding: utf-8 -*-
"""成文审阅用的数字/年份逻辑：合计、均值、趋势、截止年对不上则记逻辑/年份错误并黄句。

不绑某年文件名。评估年由平台选择传入。
「其中」分项要认「电力电缆5项」这类不带「故障」二字的写法。
"""
from __future__ import annotations

import re


_FAULT_TOTAL = re.compile(
    r"(?:总计发生|共发生设备故障|共发生故障|发生故障|共发生|发生)\s*(\d+)\s*起"
)
# 下一个“总数声明”（无捕获），用于同段并列多年数据时把分项分组截断，避免跨年混算
_NEXT_TOTAL_QIS = re.compile(
    r"(?:总计发生|共发生设备故障|共发生故障|发生故障|共发生|发生)\s*\d+\s*起"
)
_NEXT_TOTAL_GRADE = re.compile(r"(?:评估(?:设备)?|完成)\s*\d+\s*(?:台|项)")
_GRADE_TOTAL = re.compile(r"(?:评估(?:设备)?|完成)\s*(\d+)\s*(?:台|项)")
_GRADE_PART = re.compile(r"[ABCD]\s*[类级]\s*(?:设备)?\s*(\d+)\s*(?:台|项)")
_XIANG = re.compile(r"(\d+)\s*项")
_ANY_QI = re.compile(r"(\d+)\s*起")
_FAULT_COUNT = re.compile(r"故障\s*(\d+)\s*起")
_MEAN = re.compile(r"均值[为是]\s*([\d.]+)\s*起")
_TREND_ZERO = re.compile(r"趋势为\s*0\s*%")
_AS_OF_YEAR = re.compile(r"截至\s*(\d{4})\s*年")
_YEAR_TOKEN = re.compile(r"(20\d{2})\s*年")
# 4 位年份（2025年）与 2 位简写年份（25年）都识别，用于同段年度切换处截断
_YEAR_TOKEN_ANY = re.compile(r"(20\d{2}|\d{2})\s*年")


def _year_norm(y: str) -> int:
    yi = int(y)
    return yi if yi >= 100 else 2000 + yi


def _years_before(t: str, pos: int, lookback: int = 48) -> set[int]:
    """总数声明位置之前（同一统计期描述内）出现的年份集合。"""
    return {_year_norm(y) for y in _YEAR_TOKEN_ANY.findall(t[max(0, pos - lookback) : pos])}


def _sum_parts(pattern: re.Pattern[str], blob: str) -> list[int]:
    return [int(x) for x in pattern.findall(blob or "")]


def _fault_parts_in_chunk(chunk: str) -> list[int]:
    """「其中」分组内的故障分项：优先按「项」，否则把分组内所有「N起」视为分项。

    分项句式多样（“43起供电设备故障”“8起为触网隔离开关故障”“绝缘部件故障7起”），
    统一按“N起”提取，避免只匹配“故障N起”漏掉数字在前的分项。
    """
    items = _sum_parts(_XIANG, chunk)
    if items:
        return items
    return _sum_parts(_ANY_QI, chunk)


def _cut_by_year(chunk: str, current_years: set[int] | None) -> str:
    """分组内出现不属于当前统计期的年份（年度切换）时，在该处截断。"""
    if not current_years:
        return chunk
    for ym in _YEAR_TOKEN_ANY.finditer(chunk):
        if _year_norm(ym.group(1)) not in current_years:
            return chunk[: ym.start()]
    return chunk


def _其中_chunk(
    tail: str,
    *,
    window: int = 240,
    next_total: re.Pattern[str] | None = None,
    current_years: set[int] | None = None,
) -> str | None:
    if "其中" not in (tail or "")[:24]:
        return None
    where = tail.find("其中")
    chunk = tail[where : where + window]
    stop = re.search(r"[。！？]", chunk)
    if stop:
        chunk = chunk[: stop.start()]
    if next_total is not None:
        # 同段并列下一年/下一组数据时，分项只属于当前总数，在下一个总数声明处截断
        nxt = next_total.search(chunk)
        if nxt:
            chunk = chunk[: nxt.start()]
    # 同段年度切换（如“2026年当年设备故障值15起”，无总数声明词）时截断
    chunk = _cut_by_year(chunk, current_years)
    return chunk


def number_logic_notes(text: str) -> list[str]:
    """返回本句里的数字合计/均值/趋势错误说明；无问题则空列表。"""
    t = (text or "").replace(" ", "").strip()
    if not t:
        return []
    notes: list[str] = []

    if "其中" in t:
        for m in _FAULT_TOTAL.finditer(t):
            total = int(m.group(1))
            current_years = _years_before(t, m.start())
            chunk = _其中_chunk(
                t[m.end() :],
                next_total=_NEXT_TOTAL_QIS,
                current_years=current_years,
            )
            if not chunk:
                continue
            parts = _fault_parts_in_chunk(chunk)
            if len(parts) >= 2:
                s = sum(parts)
                if s != total:
                    expr = "+".join(str(x) for x in parts)
                    notes.append(f"故障总数{total}起与分项合计{s}起（{expr}）不符")

        for m in _GRADE_TOTAL.finditer(t):
            total = int(m.group(1))
            current_years = _years_before(t, m.start())
            chunk = _其中_chunk(
                t[m.end() :],
                window=160,
                next_total=_NEXT_TOTAL_GRADE,
                current_years=current_years,
            )
            if not chunk:
                continue
            parts = _sum_parts(_GRADE_PART, chunk)
            if len(parts) >= 2:
                s = sum(parts)
                if s != total:
                    unit = "台" if "台" in m.group(0) else "项"
                    notes.append(
                        f"总数{total}{unit}与A/B/C/D分项合计{s}{unit}（{'+'.join(str(x) for x in parts)}）不符"
                    )

    # 均值：前文若干「故障N起」的算术平均；「其中」之后的分项不参与均值
    for m in _MEAN.finditer(t):
        stated = float(m.group(1))
        head = t[: m.start()]
        if "其中" in head:
            head = head[: head.find("其中")]
        nums = [int(x) for x in _FAULT_COUNT.findall(head)]
        if len(nums) >= 2:
            avg = sum(nums) / len(nums)
            # 报告均值常取整数（四舍五入）：声明为整数时按 0.5 取整容差；声明为小数时按 0.05
            tol = 0.5 if abs(stated - round(stated)) < 1e-9 else 0.05
            if abs(avg - stated) > tol:
                notes.append(
                    f"均值写{stated}起，按前文{len(nums)}个起数重算为{avg:.2f}起（{'+'.join(str(x) for x in nums)}）"
                )

    # 趋势为0%：按公式（当年值-前三年均值）/前三年均值，0% 当且仅当当年值≈均值；
    # 不能用“各年起数必须全等”判定（历史各年不必相等）
    zero_m = _TREND_ZERO.search(t)
    if zero_m:
        head = t[: zero_m.start()]
        if "其中" in head:
            head = head[: head.find("其中")]
        nums = [int(x) for x in _FAULT_COUNT.findall(head)]
        mean_m = _MEAN.search(t)
        ref = float(mean_m.group(1)) if mean_m else (sum(nums) / len(nums) if nums else None)
        if ref is not None and len(nums) >= 2:
            current = nums[0]  # 真实报告句式当年统计年在句首
            if abs(current - ref) > 0.5:
                notes.append(f"当年故障{current}起、前三年均值{ref:g}起，趋势写0%不符")

    seen: set[str] = set()
    out: list[str] = []
    for n in notes:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def year_logic_notes(text: str, assessment_year: int | None) -> list[str]:
    """评估年下的年份错误：截止到更早年份、时段对比不含评估年等。"""
    if not assessment_year:
        return []
    t = (text or "").replace(" ", "").strip()
    if not t:
        return []
    notes: list[str] = []
    year = int(assessment_year)

    for m in _AS_OF_YEAR.finditer(t):
        y = int(m.group(1))
        if y < year:
            notes.append(f"写了截至{y}年，早于评估年{year}年")

    # 「截至YYYY年M月底」已由上面覆盖（截至YYYY年）
    years = [int(x) for x in _YEAR_TOKEN.findall(t)]
    if years and year not in years and max(years) < year:
        # 时段对比/说明却完全没有评估年
        if re.search(r"至|对比|相比|趋势|故障", t) and any(y >= year - 3 for y in years):
            notes.append(f"文中年份为{min(years)}–{max(years)}年，未涉及评估年{year}年")

    seen: set[str] = set()
    out: list[str] = []
    for n in notes:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def has_number_logic_issue(text: str) -> bool:
    return bool(number_logic_notes(text))


def has_year_logic_issue(text: str, assessment_year: int | None) -> bool:
    return bool(year_logic_notes(text, assessment_year))


def number_logic_note(text: str) -> str:
    notes = number_logic_notes(text)
    return notes[0] if notes else ""


def year_logic_note(text: str, assessment_year: int | None) -> str:
    notes = year_logic_notes(text, assessment_year)
    return notes[0] if notes else ""
