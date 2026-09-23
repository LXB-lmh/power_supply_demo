# -*- coding: utf-8 -*-
"""接触网网页按章 HANDLER：第 3～11 章（含第 4 章）。

与供电同链路：分拣 → 本章建议 → 抽取 → 按去年/2025触网目录成文。
不套用供电抽取规则。
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from chapters.overhead.extract import chapter_has_content, extract_chapter
from chapters.overhead.write import write_chapter_docx
from chapters.spec import ChapterHandler

HINTS = {
    "ch3": ("接触网状态表、管控措施（接触网设备树）", "对照触网年报第 3 章：状态分布 + 各线管控措施。缺材料只黄标题。"),
    "ch4": ("设备体量变化、各线条公里、维护周期、各线接触网故障趋势", "对照触网年报第 4 章。表3-9 不在本章重复。4.4 对比无材料则黄标题。"),
    "ch5": ("合规性材料（特种设备、法律法规、企标、执行与评价）", "对照触网年报第 5 章目录填入。"),
    "ch6": ("修程修制、上一年度建议整改材料", "对照触网年报第 6 章。"),
    "ch7": ("生产组织模式、维修计划执行、维保/接管/新技术", "对照触网年报第 7 章。7.1 材料→去年→2025保底；其余缺项黄标题。"),
    "ch8": ("突出事件分析、故障专稿、隐患材料", "对照触网年报第 8 章。"),
    "ch9": ("接触网安全库存、备品备件清单", "对照触网年报第 9 章。9.1 说明和 9.2 库存表都只用当年材料；供电备件表不进。"),
    "ch10": ("使用环境、弓架次等环境因子材料", "对照触网年报第 10 章环境差异性分项。"),
    "ch11": ("退运更换说明、工器具配置", "对照触网年报第 11 章。"),
}

NAMES = {
    "ch3": (3, "设备功能有效性评估"),
    "ch4": (4, "运营契合满足度评估"),
    "ch5": (5, "管理体系合规性评估"),
    "ch6": (6, "修程修制匹配性评估"),
    "ch7": (7, "运维表现健康度评估"),
    "ch8": (8, "风险隐患闭环度评估"),
    "ch9": (9, "备件物资保障度评估"),
    "ch10": (10, "使用环境符合性评估"),
    "ch11": (11, "退运报废倾向性评估"),
}


def _extract(docs, *, year: int, chapter_id: str, prior_docs=None, prior_via: str = "") -> dict[str, Any]:
    return extract_chapter(
        docs,
        year=year,
        chapter_id=chapter_id,
        prior_docs=prior_docs,
        prior_via=prior_via,
        use_llm=True,
    )


def _write(pack: dict[str, Any], path: str | Path, chapter_id: str) -> Path:
    return write_chapter_docx(pack, path, chapter_id)


def _message(pack: dict[str, Any], chapter_id: str) -> str:
    no = NAMES[chapter_id][0]
    if chapter_has_content(pack):
        return f"第{no}章已按接触网材料填入"
    return f"第{no}章目录已生成（材料不足处已黄标题）"


def make_handler(chapter_id: str) -> ChapterHandler:
    no, name = NAMES[chapter_id]
    upload, report = HINTS[chapter_id]
    return ChapterHandler(
        chapter_id=chapter_id,
        domain_id="overhead",
        no=no,
        name=name,
        domain_label="接触网",
        cover_line=f"第{no}章  {name}（接触网）",
        upload_hint=upload,
        report_hint=report,
        style_rules="只从上传材料抽取已有信息，按触网年报本章目录填入。没有的只留黄标题，不编造。出处只标在标题后括号内。",
        extract=partial(_extract, chapter_id=chapter_id),
        write=partial(_write, chapter_id=chapter_id),
        message_fn=lambda pack, cid=chapter_id: _message(pack, cid),
    )


HANDLERS = [make_handler(cid) for cid in NAMES]
