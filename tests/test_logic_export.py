# -*- coding: utf-8 -*-
"""逻辑性检测结果导出 Word：按章分组、类型标签、连续编号、跨章归最小章。"""
from io import BytesIO

from docx import Document

from chapters.common.logic_export import (
    _chapter_key,
    _cn_number,
    build_logic_export_doc,
)


def _payload():
    findings = [
        {
            "kind": "language",
            "issue": "语言不通顺",
            "section": "第3章",
            "note": "语句重复粘连，应合并重复分句",
            "excerpt": "跟随所通讯管理机更换，更换下设备作为应急备件使用跟随所通讯管理机更换",
            "via": "llm",
        },
        {
            "kind": "severe",
            "issue": "逻辑错误",
            "section": "第3章 / 第11章 轨道交通1号线",
            "note": "第3章评级为优，第11章却写明报废，评级与报废结论矛盾",
            "excerpt": "1号线需报废1台蓄电池屏",
            "via": "llm",
        },
        {
            "kind": "logic",
            "issue": "计算错误",
            "section": "第4章",
            "note": "表内合计行与分项求和不符",
            "excerpt": "",
            "via": "",
        },
    ]
    summary = {"typo": 0, "punct": 0, "language": 1, "number": 1, "year": 0, "severe": 1}
    return {
        "findings": findings,
        "finding_count": 3,
        "summary": summary,
        "domain_label": "供电报告",
        "assessment_year": 2026,
        "mode": "full",
        "chapter_id": "",
        "source": "sample.docx",
    }


def _render(payload):
    data = build_logic_export_doc(payload)
    text = "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)
    return data, text


def test_returns_openable_docx():
    data, _ = _render(_payload())
    assert data[:2] == b"PK"  # docx 为 zip 容器


def test_title_and_statistics():
    _, text = _render(_payload())
    assert "供电报告 逻辑性检测结果（2026年）" in text
    assert "共 3 处：" in text
    assert "错别字 0" in text
    assert "语言 1" in text
    assert "计算 1" in text
    assert "逻辑 1" in text


def test_chapter_headings_ordered_and_cross_chapter_merged():
    _, text = _render(_payload())
    i3 = text.index("第三章")
    i_severe = text.index("评级与报废结论矛盾")
    i4 = text.index("第四章")
    i_calc = text.index("表内合计行与分项求和不符")
    # 跨章矛盾归到最小章（第3章），不单独出现第十一章
    assert i3 < i_severe < i4 < i_calc
    assert "第十一章" not in text


def test_kind_tags_and_continuous_numbering():
    _, text = _render(_payload())
    assert "1.【语言不通顺】" in text
    assert "2.【逻辑错误】" in text
    assert "3.【计算错误】" in text


def test_missing_excerpt_placeholder():
    _, text = _render(_payload())
    assert "原文：（该条无原文摘录）；" in text


def test_chapter_key_helpers():
    assert _chapter_key({"section": "第3章 / 第11章 轨道交通1号线"}) == 3
    assert _chapter_key({"section": "第11章"}) == 11
    assert _chapter_key({"section": "正文"}) is None
    assert _cn_number(3) == "三"
    assert _cn_number(11) == "十一"
