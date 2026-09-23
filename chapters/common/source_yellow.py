# -*- coding: utf-8 -*-
"""评估材料里标黄的段落：年报同样标黄，并在段末加（原材料标黄）。

只认当年材料 Block.yellow，不认去年体例稿。清单号/线名前缀被改写后仍按正文匹配。
缺材料、不通顺用的黄标走 add_para(yellow=True)，不加本后缀。
"""
from __future__ import annotations

import re
from typing import Any, Iterable

SOURCE_YELLOW_NOTE = "（原材料标黄）"

_LIST_LEAD = re.compile(r"^[（(]?\d{1,2}[、.．)）]\s*")
_LINE_LEAD = re.compile(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*")
_MIN_KEY = 6

_KEYS: set[str] = set()


def reset() -> None:
    _KEYS.clear()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def text_keys(text: str) -> list[str]:
    """同一段在材料/年报里可能改了序号或线名前缀，多把钥匙都收下。"""
    raw = _compact(text).replace(SOURCE_YELLOW_NOTE, "")
    if not raw:
        return []
    keys: list[str] = []
    for cand in (raw, _LIST_LEAD.sub("", raw)):
        body = _LINE_LEAD.sub("", cand)
        for item in (cand, body):
            if item and item not in keys:
                keys.append(item)
    return keys


def register_text(text: str) -> None:
    for key in text_keys(text):
        if len(key) >= _MIN_KEY:
            _KEYS.add(key)


def register_current_docs(docs: Iterable[Any] | None) -> None:
    """每次抽取当年材料时重置后再登记，避免串到上一份/去年稿。"""
    reset()
    for doc in docs or []:
        for block in getattr(doc, "blocks", None) or []:
            if getattr(block, "type", "") != "paragraph":
                continue
            if not getattr(block, "yellow", False):
                continue
            register_text(getattr(block, "text", "") or "")


def looks_source_yellow(text: str) -> bool:
    return any(key in _KEYS for key in text_keys(text))


def apply_source_yellow(text: str, *, source_yellow: bool = False) -> tuple[str, bool]:
    """返回 (写成文用的句子, 是否按原材料标黄)。已带后缀的不再追加。"""
    raw = text or ""
    t = raw.rstrip()
    if not t:
        return raw, False
    if not (source_yellow or looks_source_yellow(t)):
        return raw, False
    if SOURCE_YELLOW_NOTE not in t:
        t = t + SOURCE_YELLOW_NOTE
    return t, True


def para_flow_item(text: str, block: Any | None = None, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": "para", "text": text, **extra}
    if block is not None and getattr(block, "yellow", False):
        item["source_yellow"] = True
    return item
