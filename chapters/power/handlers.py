# -*- coding: utf-8 -*-
"""供电网页按章 HANDLER：第 3、5～11 章。第 4 章在 chapters.ch4.power。

第 1、2、12 章只有 CLI 全年报（build.py）才写，网页左侧不挂，避免空目录章被当成可评估。
各章共用 extract_chapter / write_chapter_docx，靠 chapter_id 分支；规则仍在 extract/write 里。
"""
from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

from chapters.power.extract import extract_chapter
from chapters.power.write import write_chapter_docx
from chapters.spec import ChapterHandler

HINTS = {
    "ch3": ("设备评估结果总表、管控措施（设备树）", "对照 2025 年报第 3 章：总表出状态分布表，管控措施出 3.4。缺材料只黄标题。"),
    "ch5": ("合规性材料（法律法规、企标、执行与评价）", "对照 2025 年报第 5 章目录填入。没有特种设备表、强制年检图则黄标题。"),
    "ch6": ("合规性材料中的修程修制、规程修订目录", "对照 2025 年报第 6 章。修订目录待完善则黄标题。"),
    "ch7": (
        "生产组织模式；运维质量开篇；生产计划执行表；仪器仪表/部门培训/智能化（按变电线报告）",
        "7.1：今年→去年→黄。7.2 固定 7.2.1～7.2.4；表7-1 只认当年；7.2.2～7.2.4 按线路 7.2.x.n 填空，无则黄，不拿别处顶。7.3 黄空。",
    ),
    "ch8": (
        "风险数据库汇总表、隐患排除/排查手册、典型故障专稿（按内容认）",
        "骨架从去年报告检测（8.1.1～8.1.3/8.2）。表与正文只用当年材料；风险库表头兼容 25/26；小结黄空。",
    ),
    "ch9": ("安全库存清单（备件）", "表 9-1 从备件材料抽取。有更新台账则填 9.2，没有则黄标题。"),
    "ch10": ("各线变电评估报告使用环境段", "按线路汇总成 10.1.x；触网弓架次稿不进供电第 10 章。"),
    "ch11": ("退运材料、报废情况说明、各线评估报告退运段", "按线路汇总成 11.1.x；工器具/仪器仪表进 11.2。"),
}

NAMES = {
    "ch3": (3, "设备功能有效性评估"),
    "ch5": (5, "管理体系合规性评估"),
    "ch6": (6, "修程修制匹配性评估"),
    "ch7": (7, "运维表现健康度评估"),
    "ch8": (8, "风险隐患闭环度评估"),
    "ch9": (9, "备件物资保障度评估"),
    "ch10": (10, "使用环境符合性评估"),
    "ch11": (11, "退运报废倾向性评估"),
}


def _extract(docs, *, year: int, chapter_id: str, prior_docs=None) -> dict[str, Any]:
    return extract_chapter(docs, year=year, chapter_id=chapter_id, prior_docs=prior_docs)


def _write(pack: dict[str, Any], path: str | Path, chapter_id: str) -> Path:
    return write_chapter_docx(pack, path, chapter_id)


def _message(pack: dict[str, Any], chapter_id: str) -> str:
    return f"第{NAMES[chapter_id][0]}章已按材料填入"


def make_handler(chapter_id: str) -> ChapterHandler:
    """组装一章 HANDLER。style_rules 写明：只抽已有信息、缺则黄标题、出处只在标题括号。"""
    no, name = NAMES[chapter_id]
    upload, report = HINTS[chapter_id]
    return ChapterHandler(
        chapter_id=chapter_id,
        domain_id="power_supply",
        no=no,
        name=name,
        domain_label="供电",
        cover_line=f"第{no}章  {name}（供电含能源系统）",
        upload_hint=upload,
        report_hint=report,
        style_rules="只从上传材料抽取已有信息，按 2025 供电年报本章目录填入。没有的只留黄标题，不编造。出处只标在标题后括号内。",
        extract=partial(_extract, chapter_id=chapter_id),
        write=partial(_write, chapter_id=chapter_id),
        message_fn=lambda pack, cid=chapter_id: _message(pack, cid),
    )


HANDLERS = [make_handler(cid) for cid in NAMES]
