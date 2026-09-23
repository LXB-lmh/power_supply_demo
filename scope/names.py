# -*- coding: utf-8 -*-
"""线路、区段名称归一，以及上传文件指纹。

「1 号线」「_1号线」都变成「1号线」，总表去重和 3.3.2 行键都靠这个。
file_fingerprint 按文件名+内容，用来挂同一批材料的历史报告。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

LINE_RE = re.compile(r"(\d+)\s*号线")
SEG_HINTS = (
    "北北延伸",
    "西西延伸",
    "南延伸",
    "北延伸",
    "东延伸",
    "西延伸",
    "三期东延伸",
    "三期南延伸",
    "迪士尼段",
    "花桥段",
    "一期",
    "二期",
    "三期",
    "正线",
)


def normalize_line(value: object) -> str:
    """抽成「N号线」。抽不出则原样（可能是主变等非线路名）。"""
    text = str(value or "").strip()
    text = text.lstrip("_").replace(" ", "")
    if not text or text in {"/", "-", "—", "无"}:
        return ""
    match = LINE_RE.search(text)
    if match:
        return f"{match.group(1)}号线"
    if text.endswith("号线"):
        return text
    return text


def normalize_segment(value: object) -> str:
    """区段名去空白。空、斜杠、「本次评估」不当区段。"""
    text = str(value or "").strip()
    text = text.lstrip("_").replace(" ", "")
    if not text or text in {"/", "-", "—", "无", "本次评估"}:
        return ""
    return text


def scope_key(line_id: object, segment: object = "") -> str:
    """线路|区段，历史报告重叠判断用。"""
    return f"{normalize_line(line_id)}|{normalize_segment(segment)}"


def format_scope(line_id: object, segment: object = "") -> str:
    line = normalize_line(line_id) or "未知线路"
    seg = normalize_segment(segment)
    return f"{line}{seg}" if seg else line


def file_fingerprint(paths: list[str | Path]) -> str:
    """同一组文件内容不变则指纹不变，用于历史报告列表。"""
    digest = hashlib.sha256()
    for path in sorted((Path(p) for p in paths), key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def guess_device_type(sheet_or_header: str) -> str:
    """旧台账用：从表头猜杂散电流三类设备。年报总表不走这条。"""
    text = sheet_or_header or ""
    if "参比" in text or "参考电极" in text:
        return "参比电极"
    if "排流" in text:
        return "排流柜"
    if "单向" in text or "单项" in text or "单导" in text or "导通" in text:
        return "单向导通装置"
    return ""


def canonical_device_type(value: object) -> str:
    text = str(value or "").strip()
    return guess_device_type(text) or text
