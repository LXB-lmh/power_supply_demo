# -*- coding: utf-8 -*-
"""专业与章节目录。网页顶栏供电 / 接触网；左侧第 3～11 章。

供电各章抽取规则已在 chapters 注册；taxonomy 里部分 rules_ready 仍为 False
只影响提示文案，真正能否评估看 chapters.registry.has_handler。
接触网不要套用供电 HANDLER。
"""
from catalog.taxonomy import get_chapter, get_domain, get_subsystem, list_chapters, list_domains, public_catalog, chapter_ready

__all__ = [
    "chapter_ready",
    "get_chapter",
    "get_domain",
    "get_subsystem",
    "list_chapters",
    "list_domains",
    "public_catalog",
]
