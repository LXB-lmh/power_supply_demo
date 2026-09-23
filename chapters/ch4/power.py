# -*- coding: utf-8 -*-
"""供电 · 第四章 运营契合满意度。接触网第四章另开 overhead.py。

网页按章评估挂这个 HANDLER。全年报里的第四章由 power.write.write_ch4 再写一遍，抽取共用 build_pack。
"""
from __future__ import annotations

from typing import Any

from chapters.ch4.power_extract import build_pack
from chapters.ch4.power_style import STYLE_RULES
from chapters.ch4.power_write import write_docx
from chapters.spec import ChapterHandler


def _message(pack: dict[str, Any]) -> str:
    """完成提示带上是否抽到总表体量和几条线路故障原文，方便网页一眼看出材料够不够。"""
    msg = "第四章已按材料填入"
    if pack.get("volume_text"):
        msg += "（含总表体量）"
    n_lines = len(pack.get("fault_by_line") or {})
    if n_lines:
        msg += f"（含{n_lines}条线路故障原文）"
    return msg


def _extra(pack: dict[str, Any]) -> dict[str, Any]:
    """给网页结果页额外带上 4.1.2 口径摘要，不进入 Word 正文。"""
    return {
        "ch4_pack": {
            "grade_source": pack.get("grade_source"),
            "fault_source": pack.get("fault_source"),
            "volume_text": pack.get("volume_text"),
            "grade_counts": pack.get("grade_counts"),
        }
    }


HANDLER = ChapterHandler(
    chapter_id="ch4",
    domain_id="power_supply",
    no=4,
    name="运营契合满意度评估",
    domain_label="供电",
    cover_line="第四章  运营契合满足度评估（供电含能源系统）",
    upload_hint="设备评估结果总表，及其他相关评估材料。",
    report_hint="从上传材料中抽取已有信息填入本章。材料没有的不编造；出处只标在标题后的括号里。",
    style_rules=STYLE_RULES,
    extract=build_pack,
    write=write_docx,
    message_fn=_message,
    extra_result=_extra,
)
