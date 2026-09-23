# -*- coding: utf-8 -*-
"""评估报告上下文逻辑性检测：评级与处置矛盾、数字合计、年份等。

通用规则，不绑死某年文件名。供「逻辑性检测」页：完整报告 / 单章报告。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from chapters.common.number_logic import number_logic_notes, year_logic_notes
from parsers.dispatch import parse_file


# 好评 / 差评矛盾：同窗内同时出现则记一条
_GOOD = re.compile(
    r"(?:评为|[为是]\s*)?[Aa]\s*[类级]|状态\s*[为属]?\s*良好|运行\s*正常|设备完好|"
    r"无需更换|暂不需要更换|满足运行要求|可靠性较高"
)
_BAD = re.compile(
    r"需报废|申请报废|应报废|必须更换|整体更换|无法继续使用|无再利用价值|"
    r"严重故障|存在极大的安全隐患|已无法满足|不能继续运行|立即更换"
)
_GRADE_A = re.compile(r"(?:评级|评估结果|状态等级|设备评级)?[^。；\n]{0,12}[Aa]\s*[类级]")
_SCRAP = re.compile(r"需报废|申请报废|应予报废|报废处置|无再利用价值")


def _blocks_to_units(doc) -> list[dict[str, Any]]:
    """把材料压成带序号的文本单元，表也摊成可读串。"""
    units: list[dict[str, Any]] = []
    for i, block in enumerate(doc.blocks or []):
        if block.type == "table" and block.rows:
            text = "；".join(" / ".join(str(c) for c in row) for row in block.rows[:40])
            if text.strip():
                units.append({"i": i, "kind": "table", "text": text.strip()})
            continue
        t = (block.text or "").strip()
        if not t:
            continue
        units.append({"i": i, "kind": block.type, "text": t})
    return units


def _window_text(units: list[dict[str, Any]], center: int, *, radius: int = 3) -> str:
    lo = max(0, center - radius)
    hi = min(len(units), center + radius + 1)
    return "\n".join(u["text"] for u in units[lo:hi])


def _add(
    out: list[dict[str, str]],
    *,
    kind: str,
    issue: str,
    section: str,
    note: str,
    excerpt: str = "",
) -> None:
    row = {
        "kind": kind,
        "issue": issue,
        "section": section or "正文",
        "note": note,
        "excerpt": (excerpt or "")[:180],
    }
    key = (row["kind"], row["section"], row["note"], row["excerpt"])
    if any((x["kind"], x["section"], x["note"], x["excerpt"]) == key for x in out):
        return
    out.append(row)


def _guess_section(units: list[dict[str, Any]], idx: int) -> str:
    for j in range(idx, -1, -1):
        t = units[j]["text"].strip()
        if len(t) <= 48 and (
            units[j]["kind"] == "heading"
            or bool(re.match(r"^\d+(?:[\.．]\d+)+", t))
            or t.startswith("第")
        ):
            return t[:40]
    return "正文"


def _scan_contradictions(units: list[dict[str, Any]], out: list[dict[str, str]]) -> None:
    for idx, unit in enumerate(units):
        win = _window_text(units, idx, radius=4)
        if _GRADE_A.search(win) and _SCRAP.search(win):
            _add(
                out,
                kind="logic",
                issue="上下文相悖",
                section=_guess_section(units, idx),
                note="附近同时出现 A 类/良好评级与报废、无再利用等表述，请核对是否同一设备或同一时段。",
                excerpt=win.replace("\n", " ")[:160],
            )
        if _GOOD.search(win) and _BAD.search(win):
            # 避免与上条完全重复：仅在未命中 A+报废 时再记「好坏并存」
            if not (_GRADE_A.search(win) and _SCRAP.search(win)):
                _add(
                    out,
                    kind="logic",
                    issue="上下文相悖",
                    section=_guess_section(units, idx),
                    note="同一上下文既写运行正常/良好，又写需更换、严重隐患或无法继续使用。",
                    excerpt=win.replace("\n", " ")[:160],
                )


def _fix_numeric_section(units: list[dict[str, Any]], out: list[dict[str, str]], year: int | None) -> None:
    """带正确小节名的数字/年份扫描。"""
    for idx, unit in enumerate(units):
        t = unit["text"]
        if len(t) < 12:
            continue
        sec = _guess_section(units, idx)
        for note in number_logic_notes(t):
            _add(out, kind="logic", issue="逻辑不通", section=sec, note=note, excerpt=t[:160])
        for note in year_logic_notes(t, year):
            _add(out, kind="year", issue="年份错误", section=sec, note=note, excerpt=t[:160])


def check_document_logic(
    path: str | Path,
    *,
    assessment_year: int | None = None,
    mode: str = "full",
    chapter_id: str = "",
) -> dict[str, Any]:
    """检测一份 Word/材料的上下文逻辑性。

    mode: full=完整报告；chapter=单章。
    """
    path = Path(path)
    year = int(assessment_year) if assessment_year else None
    doc = parse_file(path)
    units = _blocks_to_units(doc)
    findings: list[dict[str, str]] = []
    _scan_contradictions(units, findings)
    _fix_numeric_section(units, findings, year)

    # 表内等级 vs 邻近报废：表行含 A 且后文窗含报废
    for idx, unit in enumerate(units):
        if unit["kind"] != "table":
            continue
        if not re.search(r"(?:^|[/\s])A(?:[/\s]|$)", unit["text"]):
            continue
        win = _window_text(units, idx, radius=5)
        if _SCRAP.search(win):
            _add(
                findings,
                kind="logic",
                issue="上下文相悖",
                section=_guess_section(units, idx),
                note="表中出现 A 级，邻近正文出现报废/无再利用表述。",
                excerpt=win.replace("\n", " ")[:160],
            )

    summary = {
        "logic": sum(1 for x in findings if x["kind"] == "logic"),
        "year": sum(1 for x in findings if x["kind"] == "year"),
        "contradiction": sum(1 for x in findings if x["issue"] == "上下文相悖"),
    }
    return {
        "ok": True,
        "mode": mode,
        "chapter_id": chapter_id or "",
        "source": path.name,
        "unit_count": len(units),
        "finding_count": len(findings),
        "summary": summary,
        "findings": findings,
        "message": (
            f"共检测到 {len(findings)} 处可疑项（相悖 {summary['contradiction']}，"
            f"数字/其它逻辑 {summary['logic'] - summary['contradiction']}，年份 {summary['year']}）。"
            if findings
            else "未发现明显的上下文相悖或数字/年份逻辑问题。"
        ),
    }
