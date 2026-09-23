# -*- coding: utf-8 -*-
"""年报按章实现。加新章：在 chapters/chN/ 下为对应专业写 style、extract、write，
声明 HANDLER，并在 registry.load_handlers 里 register。接口层不要写 if 章节。"""
from chapters.registry import get_handler, has_handler, ready_domains
from chapters.run import run_chapter, run_registered_chapter

__all__ = [
    "get_handler",
    "has_handler",
    "ready_domains",
    "run_chapter",
    "run_registered_chapter",
]
