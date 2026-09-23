# -*- coding: utf-8 -*-
"""成文清单号：多份材料拼到同一节时，小标题要接着编，不能各自从 1 再起。"""
from __future__ import annotations

import re
from typing import Any

_NUM_LEAD_RE = re.compile(r"^(\d+)([、.．)）])(\s*)(.*)$")
_LIST_RESET_RE = re.compile(
    r"^(?:(?:轨道交通)?\d{1,2}\s*号线.{0,24}|"
    r".{0,16}的)?"
    r"(?:主要风险点|后续的管控措施|后续风险管控(?:措施)?|管控策略包括|"
    r"现有风险点的管控措施是|现有管控措施是)"
    r"[:：]?\s*$"
)


def _punct_key(mark: str) -> str:
    if mark in "）)":
        return ")"
    if mark == "、":
        return "、"
    return "."


def _is_list_reset(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_LIST_RESET_RE.match(t))


def renumber_continued_list_paras(paras: list[str] | None) -> list[str]:
    """同一套标点的清单若又从 1 起号，改成接在上一份后面；新起段标题才重置。"""
    last: dict[str, int] = {}
    out: list[str] = []
    for raw in paras or []:
        t = str(raw or "")
        s = t.strip()
        if _is_list_reset(s):
            last.clear()
            out.append(t)
            continue
        m = _NUM_LEAD_RE.match(s)
        if not m:
            out.append(t)
            continue
        n = int(m.group(1))
        mark = m.group(2)
        key = _punct_key(mark)
        prev = last.get(key, 0)
        if prev and n <= prev:
            n = prev + 1
        last[key] = n
        out.append(f"{n}{mark}{m.group(3)}{m.group(4)}")
    return out


def _map_flow_paras(flow: list[dict[str, Any]] | None, mapper) -> list[dict[str, Any]]:
    items = [x for x in (flow or []) if isinstance(x, dict)]
    paras = [str(x.get("text") or "") for x in items if x.get("kind") == "para"]
    mapped = iter(mapper(paras))
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") != "para":
            out.append(item)
            continue
        nxt = dict(item)
        nxt["text"] = next(mapped)
        out.append(nxt)
    return out


def renumber_continued_list_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """只改段落小标题号，表/图原样保留。"""
    return _map_flow_paras(flow, renumber_continued_list_paras)


def restart_list_numbers_paras(paras: list[str] | None) -> list[str]:
    """同一事件内清单从 1 重计（部门稿常从 3) 抄来）。"""
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in paras or []:
        t = str(raw or "")
        s = t.strip()
        m = _NUM_LEAD_RE.match(s)
        if not m:
            out.append(t)
            continue
        mark = m.group(2)
        key = _punct_key(mark)
        seen[key] = seen.get(key, 0) + 1
        out.append(f"{seen[key]}{mark}{m.group(3)}{m.group(4)}")
    return out


def restart_list_numbers_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return _map_flow_paras(flow, restart_list_numbers_paras)


def restart_list_after_prose_paras(paras: list[str] | None) -> list[str]:
    """中间隔了说明句后，清单重新从 1 起（覆冰原因/表现各一套 1.2.3）。"""
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in paras or []:
        t = str(raw or "")
        s = t.strip()
        m = _NUM_LEAD_RE.match(s)
        if not m:
            seen.clear()
            out.append(t)
            continue
        mark = m.group(2)
        key = _punct_key(mark)
        seen[key] = seen.get(key, 0) + 1
        out.append(f"{seen[key]}{mark}{m.group(3)}{m.group(4)}")
    return out


def restart_list_after_prose_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return _map_flow_paras(flow, restart_list_after_prose_paras)
