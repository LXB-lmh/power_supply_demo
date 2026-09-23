# -*- coding: utf-8 -*-
"""逻辑性检测结果导出 Word（独立功能，不参与检测判定，也不参与年报生成/标黄）。

格式（依据用户确认）：
- 顶部总标题 + 一句统计概要；
- 按章输出，章标题为带大纲级别的蓝色标题（Word 导航窗格可直接跳转）；
- 条目全文连续编号，每条两段：
  「n.【类型标签】原文：…；」
  「问题：…；」
- 跨章矛盾（定位含多个章号）归到编号最小的章。
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from chapters.common.docx_style import (
    BODY_PT,
    _apply_body_paragraph,
    _apply_heading_paragraph,
    _run,
)
from chapters.common.word import new_report_document

# 导出文档主题蓝（与系统表头蓝 2F5597 同色系）
_EXPORT_BLUE = RGBColor(0x2E, 0x53, 0x95)

_CN_DIGITS = "零一二三四五六七八九十"


def _cn_number(value: int) -> str:
    """3~12 的阿拉伯数字转中文（章标题用），超出范围回退阿拉伯数字。"""
    if 0 <= value <= 10:
        return _CN_DIGITS[value]
    if 11 <= value <= 19:
        return "十" + _CN_DIGITS[value - 10]
    return str(value)


def _kind_tag(kind: str) -> str:
    """类型标签文案，与前端 kindLabel 保持一致。"""
    return {
        "typo": "错别字",
        "punct": "标点错误",
        "language": "语言不通顺",
        "logic": "计算错误",
        "year": "年份错误",
        "severe": "逻辑错误",
    }.get(kind, kind or "其它")


def _chapter_key(row: dict[str, Any]) -> int | None:
    """从定位文本取章号；跨章（第3章 / 第11章）取最小章；无章号返回 None。"""
    nums = [int(x) for x in re.findall(r"第\s*(\d{1,2})\s*章", str(row.get("section") or ""))]
    return min(nums) if nums else None


def _end_semicolon(text: str) -> str:
    """统一以全角分号结尾；去掉已有的句末标点避免重复。"""
    cleaned = str(text or "").rstrip().rstrip("。；;，,")
    return f"{cleaned}；"


def _set_outline_level(paragraph, level: int) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    outline = OxmlElement("w:outlineLvl")
    outline.set(qn("w:val"), str(max(level, 0)))
    p_pr.append(outline)


def _stat_text(summary: dict[str, Any], finding_count: int) -> str:
    s = summary or {}
    cols = (
        ("错别字", s.get("typo")),
        ("标点", s.get("punct")),
        ("语言", s.get("language")),
        ("计算", s.get("number")),
        ("年份", s.get("year")),
        ("逻辑", s.get("severe")),
    )
    detail = "、".join(f"{name} {int(val or 0)}" for name, val in cols)
    return f"共 {int(finding_count or 0)} 处：{detail}。"


def build_logic_export_doc(payload: dict[str, Any]) -> bytes:
    """把检测结果 payload 生成为 docx 字节。payload 字段同前端结果对象。

    必需/可选：findings、finding_count、summary、domain_label、assessment_year、
    mode、chapter_id、source。
    """
    findings = list(payload.get("findings") or [])
    finding_count = payload.get("finding_count")
    if finding_count is None:
        finding_count = len(findings)
    summary = payload.get("summary") or {}
    domain_label = str(payload.get("domain_label") or "评估报告").strip()
    year = payload.get("assessment_year")

    doc = new_report_document()

    # 总标题
    title = f"{domain_label} 逻辑性检测结果"
    if year:
        title += f"（{year}年）"
    p = doc.add_paragraph()
    _apply_heading_paragraph(p)
    _set_outline_level(p, 0)
    p.paragraph_format.space_after = Pt(6)
    _run(p, title, bold=True, size=17, color=_EXPORT_BLUE)

    # 统计概要
    p = doc.add_paragraph()
    _apply_body_paragraph(p)
    _run(p, _stat_text(summary, int(finding_count)), size=BODY_PT)

    # 按章分组（保持原数组在章内的顺序）
    groups: dict[int | None, list[dict[str, Any]]] = {}
    for row in findings:
        key = _chapter_key(row)
        groups.setdefault(key, []).append(row)
    ordered_keys = sorted((k for k in groups if k is not None))
    if None in groups:
        ordered_keys.append(None)

    number = 0
    for key in ordered_keys:
        rows = groups[key]
        # 章标题（带大纲级别，导航可查）
        p = doc.add_paragraph()
        _apply_heading_paragraph(p)
        _set_outline_level(p, 1)
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        heading = f"第{_cn_number(key)}章" if key is not None else "未定位章节"
        _run(p, heading, bold=True, size=15, color=_EXPORT_BLUE)

        for row in rows:
            number += 1
            tag = _kind_tag(str(row.get("kind") or ""))
            excerpt = str(row.get("excerpt") or "").strip() or "（该条无原文摘录）"
            note = str(row.get("note") or "").strip() or "（无问题说明）"

            # 第 1 段：编号 + 类型标签 + 原文
            p = doc.add_paragraph()
            _apply_body_paragraph(p)
            p.paragraph_format.space_before = Pt(6)
            _run(p, f"{number}.", bold=True)
            _run(p, f"【{tag}】", bold=True, color=_EXPORT_BLUE)
            _run(p, "原文：" + _end_semicolon(excerpt))

            # 第 2 段：问题说明
            p = doc.add_paragraph()
            _apply_body_paragraph(p)
            _run(p, "问题：", bold=True)
            _run(p, _end_semicolon(note))

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
