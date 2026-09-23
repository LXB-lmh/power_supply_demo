# -*- coding: utf-8 -*-
"""按 (专业, 章节) 查找已实现的年报章。未注册的章只收存材料。

网页顶栏选专业、左侧选章后走这里。供电与接触网分别注册 HANDLER，互不串用。
"""
from __future__ import annotations

from chapters.spec import ChapterHandler

_HANDLERS: dict[tuple[str, str], ChapterHandler] = {}
_LOADED = False


def register(handler: ChapterHandler) -> None:
    """登记一章。同一 (专业, 章号) 后写覆盖前写，便于测试替换。"""
    _HANDLERS[(handler.domain_id, handler.chapter_id)] = handler


def load_handlers() -> None:
    """惰性导入各章 HANDLER，避免 registry ↔ 章实现循环依赖。供电与接触网分别注册。"""
    global _LOADED
    if _LOADED:
        return
    from chapters.ch4.power import HANDLER as ch4_power
    from chapters.power.handlers import HANDLERS as power_handlers
    from chapters.overhead.handlers import HANDLERS as overhead_handlers

    register(ch4_power)
    for handler in power_handlers:
        register(handler)
    for handler in overhead_handlers:
        register(handler)
    _LOADED = True


def get_handler(domain_id: str | None, chapter_id: str | None) -> ChapterHandler | None:
    """按专业+章号取 HANDLER。找不到返回 None，调用方应收存材料而不是报错或套别的章。"""
    load_handlers()
    return _HANDLERS.get(((domain_id or "").strip(), (chapter_id or "").strip()))


def has_handler(domain_id: str | None, chapter_id: str | None) -> bool:
    """网页用来判断该章能否「评估」，还是只上传不生成。"""
    return get_handler(domain_id, chapter_id) is not None


def handlers_for_chapter(chapter_id: str | None) -> list[ChapterHandler]:
    """同一章号可能对应多个专业（如供电 ch4 与将来的接触网 ch4）。"""
    load_handlers()
    wanted = (chapter_id or "").strip()
    return [h for (domain, cid), h in _HANDLERS.items() if cid == wanted]


def ready_domains(chapter_id: str | None) -> list[str]:
    """该章已实现的专业 id，保持注册顺序，不去重打乱。"""
    seen: list[str] = []
    for handler in handlers_for_chapter(chapter_id):
        if handler.domain_id not in seen:
            seen.append(handler.domain_id)
    return seen
