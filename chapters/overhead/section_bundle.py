# -*- coding: utf-8 -*-
"""触网成文：按小节标题整段搬运（表题 + 原表 + 表后说明），不拆、不重排、不编造。

多份材料时：同线路/同段落以较新文件为准；仍不一致则保留新值并在 warnings 记录供标黄。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from chapters.common.drawings import drawing_flow_item
from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts
from chapters.common.table_copy import table_flow_item
from chapters.overhead.outline import CHAPTER_NAMES, CHAPTER_STOP_TITLES, is_peer_chapter_title
from parsers.document_model import Block, DocumentModel

_LINE_LEAD = re.compile(r"^(?:轨道交通)?(\d{1,2})号线\s*[：:]")
# 目录行：5.2 强制年检或评估情况分析 71
_TOC_LINE = re.compile(r"^\d+(?:[.．]\d+)+\s+\S.+\s+\d{1,4}$")
_TOC_COMPACT = re.compile(r"^\d+(?:[.．]\d+)+\S+\d{1,4}$")


def compliance_pack_rank(name: str) -> int:
    """5&6 比 4&5 新：同一次上传改时相同，用合订编号决胜。"""
    m = re.search(r"(\d+)\s*[&＆]\s*(\d+)\s*合规", name or "")
    if not m:
        return 0
    return int(m.group(1)) * 100 + int(m.group(2))


def doc_recency_key(doc: DocumentModel, list_index: int) -> tuple[float, int, int]:
    """越大越新：修改时间优先，其次合规合订编号，再其次列表靠后。"""
    path = Path(doc.source_path or "")
    try:
        mtime = path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        mtime = 0.0
    return (mtime, compliance_pack_rank(doc.source_name or ""), list_index)


def sort_docs_newest_last(docs: list[DocumentModel] | None) -> list[tuple[DocumentModel, int]]:
    """返回 (doc, 原下标)，按从旧到新排序，便于『后者覆盖前者』。"""
    pairs = [(d, i) for i, d in enumerate(docs or [])]
    pairs.sort(key=lambda x: doc_recency_key(x[0], x[1]))
    return pairs


def _heading_matches(title: str, keys: tuple[str, ...]) -> bool:
    c = compact_text(title or "")
    return any(compact_text(k) in c for k in keys if k)


def looks_like_toc_line(text: str) -> bool:
    """目录行带页码，不能当小节起点，否则正文图/表全被丢掉。"""
    t = (text or "").strip()
    if not t:
        return False
    if _TOC_LINE.match(t):
        return True
    return bool(_TOC_COMPACT.match(compact_text(t)))


def _title_like(text: str, *, heading: bool) -> bool:
    c = compact_text(text)
    if not c:
        return False
    if heading:
        return True
    if len(c) >= 48:
        return False
    return c[-1:] not in "。！？；"


def _starts_with_stop_title(text: str, stop_keys: tuple[str, ...]) -> bool:
    """标题后常跟括号说明，长度超过短行阈值也要停（如整改节带「参考…」）。"""
    c = compact_text(text)
    if not c or c[-1:] in "。！？":
        return False
    if len(c) > 96:
        return False
    for k in stop_keys:
        kk = compact_text(k)
        if kk and len(kk) >= 4 and (c == kk or c.startswith(kk)):
            return True
    return False


def _should_stop_section(
    text: str,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
    start_depth: int,
    heading: bool,
    depth: int,
) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    current = start_keys[0] if start_keys else ""
    if is_peer_chapter_title(t, current=current):
        return True
    stops = tuple(stop_keys or ()) + CHAPTER_STOP_TITLES
    if _starts_with_stop_title(t, stops) and not _heading_matches(t, start_keys):
        return True
    if not _title_like(t, heading=heading):
        return False
    if _heading_matches(t, stops) and not _heading_matches(t, start_keys):
        return True
    if heading and depth <= start_depth and t and not _heading_matches(t, start_keys):
        return True
    return False


def _chapter_seq_index(text: str) -> int:
    raw = compact_text(text or "")
    raw = re.sub(r"^第[0-9一二三四五六七八九十]+章", "", raw)
    raw = re.sub(r"^\d{1,2}(?:[.．、\s]+)?", "", raw)
    raw = re.sub(r"[（）()]+$", "", raw)
    if not raw:
        return -1
    for i, name in enumerate(CHAPTER_NAMES.values()):
        nc = compact_text(name)
        if raw == nc or raw.startswith(nc):
            return i
    return -1


_IMPLIED_CHAPTER_START = {
    compact_text("修程修制匹配性评估"): ("对上一年度合规性评估建议的整改",),
    compact_text("运维表现健康度评估"): (
        "生产组织模式",
        "日常维修计划",
        "生产计划执行",
        "设施设备运维质量分析",
    ),
    compact_text("风险隐患闭环度评估"): ("设施设备年度突出事件分析", "突出事件分析"),
    compact_text("备件物资保障度评估"): ("接触网安全库存", "安全库存"),
    compact_text("使用环境符合性评估"): ("环境差异性评估", "温度"),
    compact_text("退运报废倾向性评估"): ("报废原因", "设备退运更换", "退运更换"),
}


def _implied_chapter_start(blocks: list[Block], chapter_h1: str) -> int | None:
    """合订本省略章名时，用本章第一个专节（如 6.1 整改）当作章窗口起点。"""
    keys = _IMPLIED_CHAPTER_START.get(compact_text(chapter_h1 or "")) or ()
    if not keys:
        return None
    for i, block in enumerate(blocks):
        t = (block.text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        if _heading_matches(t, keys) and len(compact_text(t)) < 64:
            return i
    return None


def _in_chapter_body_window(blocks: list[Block], start_i: int, chapter_h1: str) -> bool:
    """起点必须落在本章正文：本章章名之后、下一章章名之前。

    材料常把第5、6章写在同一份里，同名小节（企业标准和制度）会出现两次；
    不能用文件名判断，只按章名窗口切。没有章名时，前面若已出现其他章标题则丢弃。
    """
    h1 = compact_text(chapter_h1 or "")
    if not h1:
        return True
    h1_i: int | None = None
    next_ch_i: int | None = None
    for i, block in enumerate(blocks):
        t = (block.text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        if h1_i is None:
            if _heading_matches(t, (chapter_h1,)) and len(compact_text(t)) < 40:
                h1_i = i
            continue
        if is_peer_chapter_title(t, current=chapter_h1):
            next_ch_i = i
            break
    if h1_i is None:
        implied = _implied_chapter_start(blocks, chapter_h1)
        if implied is not None:
            h1_i = implied
            for j in range(implied + 1, len(blocks)):
                t = (blocks[j].text or "").strip()
                if not t or looks_like_toc_line(t):
                    continue
                if is_peer_chapter_title(t, current=chapter_h1):
                    next_ch_i = j
                    break
        else:
            cur = _chapter_seq_index(chapter_h1)
            if cur < 0:
                return True
            for i in range(0, start_i):
                t = (blocks[i].text or "").strip()
                if not t or looks_like_toc_line(t):
                    continue
                if len(compact_text(t)) >= 40:
                    continue
                peer = _chapter_seq_index(t)
                if peer > cur:
                    return False
            return True
    if start_i < h1_i:
        return False
    if next_ch_i is not None and start_i >= next_ch_i:
        return False
    return True


def doc_has_outline_child_after_h1(
    doc: DocumentModel,
    chapter_h1: str,
    child_keys: tuple[str, ...],
) -> bool:
    """本章章名之后很快出现目录子节（如 6.1 整改），才当作汇编稿而非线路答题。"""
    if not chapter_h1 or not child_keys:
        return False
    armed = False
    seen = 0
    for block in doc.blocks or []:
        t = (block.text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        if not armed:
            if _heading_matches(t, (chapter_h1,)) and len(compact_text(t)) < 40:
                armed = True
            continue
        seen += 1
        if seen > 16:
            return False
        if is_peer_chapter_title(t, current=chapter_h1):
            return False
        if _heading_matches(t, child_keys) and len(compact_text(t)) < 64:
            return True
    return False


def _sheet_title(text: str) -> str:
    t = str(text or "").strip()
    if t.startswith("工作表:"):
        return t.split(":", 1)[-1].strip()
    return ""


def _drawing_item(doc: DocumentModel, block: Block) -> dict[str, Any]:
    return drawing_flow_item(doc, block)


def extract_subsection_bundle(
    doc: DocumentModel,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...] = (),
    table_predicate: Callable[[list[list[str]]], bool] | None = None,
    max_blocks: int = 80,
    require_table: bool = False,
    chapter_h1: str = "",
) -> dict[str, Any] | None:
    """从单份材料取一小节：标题后的段/表/图，直到下一同级标题。

    部门稿标题常带「2.1.1各线路柔性…」前缀，按关键词包含匹配。
    Excel 工作表名也可作起点。正文节（生产组织、环境因子）允许无表。
    有 chapter_h1 时只取该章窗口内的起点，避免跨章同名小节。
    """
    blocks = list(doc.blocks or [])
    for start_i, start_depth in _iter_section_starts(blocks, start_keys):
        if chapter_h1 and not _in_chapter_body_window(blocks, start_i, chapter_h1):
            continue
        flow = _collect_section_flow(
            doc,
            blocks,
            start_i=start_i,
            start_depth=start_depth,
            start_keys=start_keys,
            stop_keys=stop_keys,
            table_predicate=table_predicate,
            max_blocks=max_blocks,
        )
        if not flow:
            continue
        has_table = any(x.get("kind") == "table" for x in flow)
        has_para = any(x.get("kind") == "para" and str(x.get("text") or "").strip() for x in flow)
        has_draw = any(x.get("kind") == "drawing" for x in flow)
        if require_table and not has_table:
            continue
        if not has_table and not has_para and not has_draw:
            continue
        paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
        return {
            "flow": dedupe_flow_items(flow),
            "paras": dedupe_texts(paras),
            "source": doc.source_name or "",
            "empty": False,
            "from_bundle": True,
        }
    return None


def _iter_section_starts(blocks: list[Block], start_keys: tuple[str, ...]):
    """跳过目录行，按正文出现顺序找起点；目录命中后正文仍空则试下一处。"""
    for i, block in enumerate(blocks):
        t = (block.text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        sheet = _sheet_title(t)
        if sheet and _heading_matches(sheet, start_keys):
            yield i, int(block.level or 1)
            continue
        if block.type == "heading" and _heading_matches(t, start_keys):
            yield i, int(block.level or 2)
            continue
        if block.type == "paragraph" and len(compact_text(t)) < 64 and _heading_matches(t, start_keys):
            yield i, 4


def _collect_section_flow(
    doc: DocumentModel,
    blocks: list[Block],
    *,
    start_i: int,
    start_depth: int,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
    table_predicate: Callable[[list[list[str]]], bool] | None,
    max_blocks: int,
) -> list[dict[str, Any]]:
    flow: list[dict[str, Any]] = []
    for j in range(start_i + 1, min(len(blocks), start_i + max_blocks)):
        block = blocks[j]
        t = (block.text or "").strip()
        if block.type == "heading":
            sheet = _sheet_title(t)
            if sheet:
                break
            depth = int(block.level or 2)
            if _should_stop_section(
                t,
                start_keys=start_keys,
                stop_keys=stop_keys,
                start_depth=start_depth,
                heading=True,
                depth=depth,
            ):
                break
        elif block.type == "paragraph" and t:
            if _should_stop_section(
                t,
                start_keys=start_keys,
                stop_keys=stop_keys,
                start_depth=start_depth,
                heading=False,
                depth=4,
            ):
                break
        if block.type == "drawing":
            flow.append(_drawing_item(doc, block))
            continue
        if block.type == "table" and block.rows:
            if table_predicate and not table_predicate(block.rows):
                continue
            if len(block.rows) > 80:
                continue
            flow.append(table_flow_item(doc, block))
            continue
        if not t:
            continue
        from chapters.common.source_yellow import para_flow_item

        flow.append(para_flow_item(t, block))
    return flow


def merge_note_paragraphs(items: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """表后说明：同号线段落后写覆盖先写；全文完全相同的只留一句。"""
    from chapters.overhead.line_notes import merge_line_notes

    by_line, general, warnings = merge_line_notes(items)
    line_notes = [by_line[k] for k in sorted(by_line, key=lambda x: int(x))]
    return dedupe_texts(general + line_notes), warnings
