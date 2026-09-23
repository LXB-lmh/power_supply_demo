# -*- coding: utf-8 -*-
"""触网第3章：状态分布表抽取与合并；3.1/3.2 体例可回退去年/2025保底。

3.3 子节：接触网设备状态分布（3.3.1接触网柔/刚、3.3.2接触轨、3.3.3隔离开关、3.3.4控制屏）。
表后说明只写该类型 C/D 在哪、没有C和D；集中修/大修/专项等管控写进 3.4。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts
from chapters.common.table_copy import table_flow_item
from chapters.overhead.line_notes import (
    build_notes_flow_after_table,
    ensure_line_lead,
    is_cluster_closing_note,
    is_control_section_para,
    is_overhaul_progress_para,
    merge_line_notes_with_sources,
    note_has_body,
    paragraphs_to_line_notes,
    row_all_zero_or_empty,
    slice_note_for_kind,
)
from chapters.overhead.material_merge import newest_item, table_row_backfill_notes
from chapters.overhead.outline import is_peer_chapter_title
from chapters.overhead.section_bundle import (
    doc_recency_key,
    sort_docs_newest_last,
)
from parsers.document_model import DocumentModel

STATUS_TITLE_KEYS = {
    "柔性": "各线路柔性接触网状态分布",
    "刚性": "各线路刚性接触网状态分布",
    "接触轨": "接触轨状态分布",
    "控制屏": "各线路隔离开关控制屏状态分布",
    "隔离开关": "各线路隔离开关状态分布",
}

KIND_START_KEYS: dict[str, tuple[str, ...]] = {
    "各线路柔性接触网状态分布": ("各线路柔性接触网状态分布", "柔性接触网状态分布"),
    "各线路刚性接触网状态分布": ("各线路刚性接触网状态分布", "刚性接触网状态分布"),
    "接触轨状态分布": ("接触轨状态分布",),
    "各线路隔离开关状态分布": ("各线路隔离开关状态分布",),
    "各线路隔离开关控制屏状态分布": ("各线路隔离开关控制屏状态分布", "隔离开关控制屏状态分布"),
}

_CANONICAL_STATUS_HEADER: list[list[str]] = [
    ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
    ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
]

_CAPTION = {
    "各线路柔性接触网状态分布": "表3-5a 各线路柔性接触网状态",
    "各线路刚性接触网状态分布": "表3-5b 各线路刚性接触网状态",
    "接触轨状态分布": "表3-6 各线路接触轨状态",
    "各线路隔离开关状态分布": "表3-7 各线路隔离开关状态",
    "各线路隔离开关控制屏状态分布": "表3-8 各线路隔离开关控制屏状态",
}

_STOP_KEYS = (
    "各线路柔性接触网状态分布",
    "各线路刚性接触网状态分布",
    "接触轨状态分布",
    "各线路隔离开关状态分布",
    "各线路隔离开关控制屏状态分布",
    "和20",
    "年评估对比",
    "各线路管控措施",
    "评估小结",
)


def _src(doc: DocumentModel) -> str:
    return doc.source_name or ""


def _line_sort_key(line: str) -> tuple[int, str]:
    m = re.search(r"(\d{1,2})号线", line or "")
    if m:
        return (int(m.group(1)), line)
    if line == "全网络":
        return (99, line)
    return (98, line or "")


def _norm_line(cell: str) -> str:
    t = re.sub(r"\s+", "", str(cell or "").strip())
    if t in {"全网络", "合计", "总计"}:
        return t
    m = re.search(r"(\d{1,2})号线", t)
    if m:
        return f"{m.group(1)}号线"
    return t


def is_status_distribution_table(rows: list[list[str]] | None) -> bool:
    """认 2025 体例状态分布表：线路 + 锚段数量 + A/B/C/D（常为双行表头）。

    也认部门线路单表（仅 1 行数据 + 表头），避免 10 号线等只出现在小文件里时被漏掉。
    """
    if not rows or len(rows) < 2:
        return False
    head = [str(c or "").strip() for c in rows[0]]
    head_blob = "".join(head)
    if "线路" not in head_blob:
        return False
    letters = {c for c in head if c in {"A", "B", "C", "D"}}
    if len(letters) < 4:
        return False
    if "区段" in head and "锚段" not in head_blob and "锚段数量" not in head_blob:
        r1 = "".join(str(c or "") for c in (rows[1] if len(rows) > 1 else []))
        if "锚段" not in r1 and "数量" not in r1:
            return False
    _, start = _table_header_rows(rows)
    has_line = False
    for row in rows[start:]:
        if _line_no(str(row[0] if row else "")):
            has_line = True
            break
    return has_line


def _context_before(blocks, index: int, limit: int = 8) -> str:
    parts: list[str] = []
    for j in range(index - 1, max(-1, index - limit - 1), -1):
        b = blocks[j]
        t = (b.text or "").strip()
        if not t:
            continue
        c = compact_text(t)
        if b.type == "heading" or (
            len(c) < 48
            and (
                t.startswith("表")
                or "状态分布" in t
                or "各线路" in t
                or t.endswith("状态")
            )
        ):
            parts.append(t)
            break
        elif parts:
            break
    return " ".join(reversed(parts))


def classify_status_kind(context: str) -> str | None:
    c = compact_text(context or "")
    if not c:
        return None
    if "隔离开关控制屏" in c or "表3-8" in c:
        return "各线路隔离开关控制屏状态分布"
    if "接触轨" in c or "表3-6" in c:
        return "接触轨状态分布"
    if "柔性" in c or "表3-5a" in c:
        return "各线路柔性接触网状态分布"
    if "刚性" in c or "表3-5b" in c:
        return "各线路刚性接触网状态分布"
    if "隔离开关" in c or "表3-7" in c:
        return "各线路隔离开关状态分布"
    return None


def _table_header_rows(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    if len(rows) >= 2:
        r1 = "".join(str(c or "") for c in rows[1])
        if any(k in r1 for k in ("占比", "锚段数", "区段数", "数量")) and "号线" not in r1:
            return [list(rows[0]), list(rows[1])], 2
    return [list(rows[0])], 1


def _header_score(rows: list[list[str]] | None) -> int:
    header, _ = _table_header_rows(rows or [])
    blob = "".join(str(c or "") for r in header for c in r)
    score = 0
    if "锚段数量" in blob:
        score += 24
    elif "锚段" in blob:
        score += 12
    if "锚段数" in blob and "占比" in blob:
        score += 8
    if "总数量" in blob:
        score += 2
    return score


def _canonical_status_header(rows: list[list[str]] | None) -> list[list[str]]:
    header, start = _table_header_rows(rows or [])
    ncols = _expected_cols(header)
    if start == 2 and 8 <= ncols <= 11:
        out = [list(r) for r in _CANONICAL_STATUS_HEADER]
        if ncols != 10:
            for r in out:
                if len(r) < ncols:
                    r.extend([""] * (ncols - len(r)))
                del r[ncols:]
        return out
    fixed: list[list[str]] = []
    for r in header:
        cells = [str(c or "").strip() for c in r]
        for i, c in enumerate(cells):
            if c in {"总数量", "数量"} and i == 1:
                cells[i] = "锚段数量"
        fixed.append(cells)
    return fixed


def _col_looks_like_pct(cell: str) -> bool:
    return "%" in str(cell or "") or "％" in str(cell or "")


def _normalize_status_data_row(cells: list[str], ncols: int) -> list[str] | None:
    """列对齐校验：第二列不能是占比，避免把 A 类数量误当锚段总数。"""
    row = [str(c or "").strip() for c in cells]
    if len(row) < 2:
        return None
    if len(row) < ncols:
        row.extend([""] * (ncols - len(row)))
    row = row[:ncols]
    line = _norm_line(row[0])
    if not line or line in {"线路", "全网络", "合计", "总计"}:
        return None
    if _col_looks_like_pct(row[1]):
        return None
    return row


def _expected_cols(header: list[list[str]]) -> int:
    return max(len(r) for r in header) if header else 0


def _row_signature(cells: list[str], ncols: int) -> str:
    """用于判断同线路两行是否冲突；锚段数量列（第 2 列）权重最高。"""
    padded = [(cells[i] if i < len(cells) else "").strip() for i in range(ncols)]
    anchor = padded[1] if len(padded) > 1 else ""
    return "|".join([anchor] + padded)


def _data_line_count(rows: list[list[str]]) -> int:
    header, start = _table_header_rows(rows)
    n = 0
    for row in rows[start:]:
        line = _norm_line(row[0] if row else "")
        if line and line not in {"线路", "全网络", "合计", "总计"}:
            n += 1
    return n


_LINE_LEAD = re.compile(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]\s*(.*)$", re.DOTALL)
_LINE_ONLY = re.compile(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]?\s*$")
_EMPTY_LINE_LEAD = re.compile(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]\s*$")
_PACK_CAPTION = (
    "各线路柔性",
    "各线路刚性",
    "接触轨状态",
    "隔离开关状态",
    "控制屏状态",
    "柔性接触网状态",
    "刚性接触网状态",
)
_NOTE_STOP = (
    "评估小结",
    "设备体量",
    "故障分析",
    "突出事件",
    "和20",
    "年评估对比",
    "各线路管控",
    "风险点及管控",
)


def _is_empty_status_note(item: dict[str, Any] | None) -> bool:
    if not item or item.get("kind") != "para":
        return False
    if item.get("missing_line_note"):
        return True
    return bool(_EMPTY_LINE_LEAD.match(str(item.get("text") or "").strip()))


def _drawing_flow_item(doc: DocumentModel, block) -> dict[str, Any]:
    idx = int(block.source_index) if (block.source_index is not None and block.source_index >= 0) else -1
    item: dict[str, Any] = {"kind": "drawing"}
    if idx >= 0 and (doc.source_path or "").lower().endswith((".docx", ".doc")):
        item["source_path"] = doc.source_path or ""
        item["source_index"] = idx
    return item


def _doc_text_blob(doc: DocumentModel, limit: int = 12000) -> str:
    return compact_text(doc.to_text()[:limit] if doc else "")


def _doc_implies_kind(doc: DocumentModel, kind: str) -> bool:
    """单线路部门稿常无表前标题：用全文/文件名推断属于哪类状态表。"""
    name = str(doc.source_name or "")
    blob = _doc_text_blob(doc) + compact_text(name)
    if kind == "各线路柔性接触网状态分布":
        return any(k in blob for k in ("柔性", "表3-5a", "3-5a", "柔性接触网"))
    if kind == "各线路刚性接触网状态分布":
        return any(k in blob for k in ("刚性", "表3-5b", "3-5b", "刚性接触网"))
    if kind == "接触轨状态分布":
        return "接触轨" in blob or "表3-6" in blob
    if kind == "各线路隔离开关状态分布":
        return "隔离开关" in blob and "控制屏" not in blob
    if kind == "各线路隔离开关控制屏状态分布":
        return "控制屏" in blob or "表3-8" in blob
    return False


def _harvest_doc_status_notes(doc: DocumentModel, kind: str) -> list[str]:
    """整份材料扫描「其中 / N号线：」说明，避免只挂在某一张表后面。"""
    start_keys = KIND_START_KEYS.get(kind) or (kind,)
    stop_keys = (
        "和20",
        "年评估对比",
        "各线路刚性",
        "各线路柔性",
        "接触轨状态",
        "隔离开关",
        "评估小结",
        "表3-",
    )
    blocks = list(doc.blocks or [])
    paras: list[str] = []
    armed = False
    for block in blocks:
        t = (block.text or "").strip()
        c = compact_text(t)
        if not armed:
            if block.type in {"heading", "paragraph"} and t:
                if any(compact_text(k) in c for k in start_keys) or "表3-5" in c or "其中" == c.rstrip("：:"):
                    armed = True
            continue
        if block.type == "heading" and t and int(block.level or 0) <= 3:
            if any(compact_text(k) in c for k in stop_keys):
                break
        if t and is_peer_chapter_title(t):
            break
        if block.type == "table" and is_status_distribution_table(block.rows):
            continue
        if t:
            paras.append(t)
        if len(paras) >= 24:
            break
    return paras


def _rows_from_bucket_item(item: dict[str, Any], ncols: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    rows = item.get("rows") or []
    _, start = _table_header_rows(rows)
    for row in rows[start:]:
        line = _norm_line(row[0] if row else "")
        if not line or line in {"线路", "全网络", "合计", "总计"}:
            continue
        cells = [str(c or "").strip() for c in row]
        if cells:
            out[line] = cells
    return out


def _backfill_table_lines(
    by_line: dict[str, list[str]],
    line_src: dict[str, str],
    order: list[str],
    buckets: list[dict[str, Any]],
    ncols: int,
    warnings: list[str],
) -> None:
    """合并后再扫一遍：某线缺行或全 0 时，从其他材料取较新的非 0 行。"""
    for item in reversed(sorted(buckets, key=lambda x: (x.get("_recency") or 0, x.get("_idx") or 0))):
        src = item.get("source") or ""
        for line, cells in _rows_from_bucket_item(item, ncols).items():
            fixed = _normalize_status_data_row(cells, ncols)
            if fixed is None:
                continue
            cells = fixed
            if row_all_zero_or_empty(cells):
                continue
            cur = by_line.get(line)
            if cur is None or row_all_zero_or_empty(cur):
                if cur is not None and not row_all_zero_or_empty(cells):
                    warnings.append(f"{line}表格数据引自「{src}」（最新材料该行为空或全0，已从其他材料补全）")
                if line not in order:
                    order.append(line)
                by_line[line] = cells
                line_src[line] = src


def _is_status_caption(text: str) -> bool:
    """表前/表间标题。图题常写成「图3-3 各线路刚性接触网状态」，不能当成下一张表而截断表后说明。"""
    t = str(text or "").strip()
    if not t or t.startswith("图"):
        return False
    c = compact_text(t)
    return bool(c) and len(c) < 48 and any(k in c for k in _PACK_CAPTION)


def _is_line_like_heading(text: str) -> bool:
    """纯「轨道交通N号线」标题。带「风险点及管控措施」的是 3.4 专节，不能当表后线路标题跨过去。"""
    t = str(text or "").strip()
    m = re.match(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]?\s*(.*)$", t)
    if not m:
        return False
    rest = compact_text(m.group(2) or "")
    return not rest


def _is_ctrl_section_title(text: str) -> bool:
    t = str(text or "").strip()
    c = compact_text(t)
    if "风险点及管控" in c:
        return True
    if not re.match(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)", t):
        return False
    if "维持现有管控" in c or "没有C" in c or "无C" in c:
        return False
    if "管控措施" in c and "差异化" not in c[:12] and len(c) < 28:
        return True
    return False


def _is_status_line_resume(text: str) -> bool:
    """风险点专节里「3号线一期…」不能当表后说明恢复点。"""
    t = str(text or "").strip()
    if _is_ctrl_section_title(t):
        return False
    m = re.match(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]?\s*(.*)$", t)
    if not m:
        return False
    rest = (m.group(2) or "").strip()
    if not rest:
        return True
    rc = compact_text(rest)
    if rc.startswith(("隔离开关", "接触网", "柔性", "刚性", "接触轨", "设备状态", "管控策略")):
        return True
    from chapters.overhead.line_notes import note_has_cd_status

    return note_has_cd_status(t)


def _should_stop_status_notes(text: str) -> bool:
    t = str(text or "").strip()
    if t and is_peer_chapter_title(t):
        return True
    c = compact_text(t)
    if not c or len(c) > 48:
        return False
    return any(k in c for k in _NOTE_STOP)


def _only_captions_between(blocks, start: int, end: int) -> bool:
    for j in range(start + 1, end):
        b = blocks[j]
        if b.type == "drawing":
            continue
        t = (b.text or "").strip()
        if not t:
            continue
        if _is_status_caption(t):
            continue
        if b.type == "heading" and len(compact_text(t)) < 48:
            continue
        return False
    return True


def packed_status_table_clusters(blocks, table_indices: list[int]) -> list[list[int]]:
    clusters: list[list[int]] = []
    current: list[int] = []
    for i in table_indices:
        if not current:
            current = [i]
            continue
        if _only_captions_between(blocks, current[-1], i):
            current.append(i)
        else:
            clusters.append(current)
            current = [i]
    if current:
        clusters.append(current)
    return clusters


def _split_after_status_table(
    blocks, index: int, doc: DocumentModel, *, follow_line_sections: bool = False
) -> tuple[list[dict[str, Any]], list[str]]:
    """表后：先图题/插图，再「其中」与各线路说明（含「N号线：」后多段正文）。"""
    media_flow: list[dict[str, Any]] = []
    note_paras: list[str] = []
    phase = "media"
    cap = 100 if follow_line_sections else 24
    skip_ctrl = False
    skip_risk = False
    for j in range(index + 1, min(len(blocks), index + 220)):
        b = blocks[j]
        t = (b.text or "").strip()
        if t and _is_ctrl_section_title(t):
            skip_ctrl = True
            skip_risk = False
            continue
        if skip_ctrl:
            if t and _is_status_line_resume(t):
                skip_ctrl = False
            else:
                continue
        rc = compact_text(t) if t else ""
        if t and (
            rc.startswith("主要风险点")
            or "触网子系统和设备状态" in rc
            or rc.startswith("正线触网子系统")
            or rc.startswith("北延伸触网子系统")
        ):
            skip_risk = True
            continue
        if skip_risk:
            if t and _is_status_line_resume(t):
                skip_risk = False
            elif (
                not t
                or re.match(r"^\d+[、.．)）]", t)
                or rc.startswith("现有管控措施")
                or rc.startswith("后续的管控")
                or rc.startswith("北延伸触网")
            ):
                continue
            else:
                skip_risk = False
        if b.type == "heading":
            if follow_line_sections and _is_line_like_heading(t):
                continue
            break
        if b.type == "table" and is_status_distribution_table(b.rows):
            break
        if t and _should_stop_status_notes(t):
            break
        if b.type == "drawing":
            if media_flow or not note_paras:
                media_flow.append(_drawing_flow_item(doc, b))
            continue
        if not t:
            continue
        if t.startswith("表") and len(t) < 48:
            break
        if _is_status_caption(t) and not follow_line_sections:
            break
        if t.startswith("图") and len(t) < 64:
            if media_flow or not note_paras:
                media_flow.append({"kind": "para", "text": t})
            continue
        if (
            phase == "media"
            and not note_paras
            and not _LINE_LEAD.match(t)
            and not _LINE_ONLY.match(t)
            and t.rstrip("：:") != "其中"
            and not t.startswith("其中")
        ):
            if t.startswith("图"):
                media_flow.append({"kind": "para", "text": t})
                continue
        phase = "notes"
        note_paras.append(t)
        if len(note_paras) >= cap:
            break
    return media_flow, note_paras


def _line_no(name: str) -> int | None:
    m = re.search(r"(\d{1,2})", _norm_line(name))
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def _lines_in_table(rows: list[list[str]] | None) -> set[int]:
    _, start = _table_header_rows(rows or [])
    out: set[int] = set()
    for row in (rows or [])[start:]:
        ln = _line_no(str(row[0] if row else ""))
        if ln:
            out.add(ln)
    return out


def prior_status_lines(prior_docs: list[DocumentModel] | None, kind: str) -> list[int]:
    """去年同节表里的线路号，只作体例对照，不写入今年数据。"""
    found: set[int] = set()
    for doc in prior_docs or []:
        blocks = list(doc.blocks or [])
        for i, block in enumerate(blocks):
            if block.type != "table" or not block.rows:
                continue
            if not is_status_distribution_table(block.rows):
                continue
            if classify_status_kind(_context_before(blocks, i)) != kind:
                continue
            found |= _lines_in_table(block.rows)
    if found:
        return sorted(found)
    return list(range(1, 19))


def coverage_warnings(
    kind: str,
    table_rows: list[list[str]] | None,
    prior_docs: list[DocumentModel] | None,
) -> list[str]:
    if not table_rows:
        return [f"「{kind}」未抽到状态分布表"]
    if kind == "接触轨状态分布":
        return []
    have = _lines_in_table(table_rows)
    expect = prior_status_lines(prior_docs, kind)
    skip_nos: set[int] = set()
    if kind in {"各线路柔性接触网状态分布", "各线路刚性接触网状态分布"}:
        skip_nos.add(17)
    missing = [n for n in expect if n not in have and n not in skip_nos]
    out: list[str] = []
    if missing:
        sample = "、".join(f"{n}号线" for n in missing[:12])
        if len(missing) > 12:
            sample += f" 等共{len(missing)}条"
        out.append(f"对照去年报告体例，「{kind}」缺：{sample}（请在材料包中补全线路报告）")
    if len(expect) >= 10 and len(have) < len(expect) - 2:
        out.append(
            f"「{kind}」仅抽到{len(have)}条线路，去年同节约{len(expect)}条，请检查是否漏传部门线路稿"
        )
    return out


def _trim_trailing_empty_cols(rows: list[list[str]]) -> list[list[str]]:
    """去掉末列全空的幽灵列，避免 11 列均分把有效列压窄。"""
    if not rows:
        return rows
    n = max(len(r) for r in rows)
    while n > 10:
        if all(len(r) < n or not str(r[n - 1] if n - 1 < len(r) else "").strip() for r in rows):
            n -= 1
        else:
            break
    out: list[list[str]] = []
    for r in rows:
        cells = [str(c or "").strip() for c in r]
        if len(cells) < n:
            cells.extend([""] * (n - len(cells)))
        out.append(cells[:n])
    return out


def _status_table_flow_item(
    *,
    rows: list[list[str]],
    doc: DocumentModel | None = None,
    block=None,
    allow_copy: bool = True,
) -> dict[str, Any]:
    from chapters.overhead.style import status_table_widths

    rows = _trim_trailing_empty_cols([list(r) for r in rows])
    ncols = len(rows[0]) if rows else 10
    widths = status_table_widths(ncols)
    vm = getattr(block, "vmerge", None) if block else None
    if allow_copy and doc is not None and block is not None:
        src_rows = [list(r) for r in (block.rows or [])]
        if src_rows == rows:
            item = table_flow_item(doc, block)
            item["widths"] = widths
            if vm is not None:
                item["vmerge"] = [list(m) for m in vm]
            return item
    return {
        "kind": "table",
        "rows": rows,
        "widths": widths,
        "vmerge": [list(m) for m in vm] if vm else None,
        "force_rebuild": True,
    }


def _pick_primary_bucket(buckets: list[dict[str, Any]]) -> dict[str, Any]:
    """线路行数最多者优先；并列取较新文件。用于整表回拷，避免拼表压窄列宽。"""
    return max(
        buckets,
        key=lambda x: (
            _data_line_count(x.get("rows") or []),
            x.get("_recency") or 0,
            x.get("_idx") or 0,
        ),
    )


def _newest_media_flow(note_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for x in reversed(sorted(note_items, key=lambda z: (z.get("_recency") or 0, z.get("_idx") or 0))):
        media = x.get("media") or []
        if media:
            return list(media)
    return []


def _merge_table_notes_flow(
    table_rows: list[list[str]] | None,
    note_items: list[dict[str, Any]],
    prior_docs: list[DocumentModel] | None,
    kind: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    merge_in = []
    for x in note_items:
        notes = list(x.get("notes") or [])
        if kind:
            by_line, gen = paragraphs_to_line_notes(notes)
            sliced: list[str] = []
            for key, text in by_line.items():
                got = slice_note_for_kind(text, kind)
                if note_has_body(got):
                    sliced.append(ensure_line_lead(key, got))
            for g in gen:
                if is_cluster_closing_note(g):
                    sliced.append(g)
            notes = sliced
        merge_in.append(
            {
                "notes": notes,
                "_recency": x.get("_recency"),
                "_idx": x.get("_idx"),
                "_source": x.get("_source") or x.get("source") or "",
            }
        )
    primary_src = str((newest_item(merge_in) or {}).get("_source") or "")
    line_map, general, warnings, line_src = merge_line_notes_with_sources(merge_in)
    if kind:
        line_map = {
            key: got
            for key, text in line_map.items()
            if note_has_body(got := slice_note_for_kind(text, kind))
        }
    expect = prior_status_lines(prior_docs, kind)
    note_flow, w2 = build_notes_flow_after_table(
        table_rows,
        line_map,
        general,
        expect_lines=expect,
        line_note_sources=line_src,
        primary_source=primary_src,
    )
    note_flow = [
        x
        for x in note_flow
        if not (
            x.get("kind") == "para"
            and (
                is_control_section_para(str(x.get("text") or ""))
                or is_overhaul_progress_para(str(x.get("text") or ""))
            )
        )
    ]
    from chapters.overhead.llm_gate import filter_flow

    note_flow = filter_flow(
        note_flow,
        kind="status",
        context=f"第3.3节{kind or '接触网设备'}状态分布表后说明，只要C/D在哪，不要3.4管控专节",
    )
    return dedupe_flow_items(_newest_media_flow(note_items) + note_flow), warnings + w2


def _flow_from_primary(
    item: dict[str, Any],
    note_items: list[dict[str, Any]],
    *,
    table_rows: list[list[str]] | None,
    prior_docs: list[DocumentModel] | None,
    kind: str,
) -> list[dict[str, Any]]:
    flow: list[dict[str, Any]] = []
    cap = item.get("caption") or ""
    if cap:
        flow.append({"kind": "para", "text": cap})
    doc = item.get("doc")
    block = item.get("block")
    rows = _trim_trailing_empty_cols([list(r) for r in (table_rows or item.get("rows") or [])])
    flow.append(_status_table_flow_item(rows=rows, doc=doc, block=block, allow_copy=True))
    note_flow, _ = _merge_table_notes_flow(rows, note_items, prior_docs, kind)
    flow.extend(note_flow)
    return dedupe_flow_items(flow)


def merge_status_tables(
    tables: list[dict[str, Any]],
    *,
    prior_docs: list[DocumentModel] | None = None,
    kind: str = "",
) -> dict[str, Any]:
    """多部门拆表：表头取列最全的一份；同线路以后出现的文件为准；冲突写 warnings。"""
    if not tables:
        return {"table": [], "paras": [], "flow": [], "source": "", "empty": True, "warnings": []}
    tables_sorted = sorted(tables, key=lambda x: (x.get("_recency") or 0, x.get("_idx") or 0))
    best = max(
        tables_sorted,
        key=lambda x: (
            _header_score(x.get("rows")),
            len((x.get("rows") or [None])[0] or []),
            _data_line_count(x.get("rows") or []),
        ),
    )
    header = _canonical_status_header(best.get("rows"))
    ncols = _expected_cols(header)
    by_line: dict[str, list[str]] = {}
    line_src: dict[str, str] = {}
    order: list[str] = []
    warnings: list[str] = []
    sources: list[str] = []
    for item in tables_sorted:
        src = item.get("source") or ""
        if src and src not in sources:
            sources.append(src)
        rows = item.get("rows") or []
        _, start = _table_header_rows(rows)
        for row in rows[start:]:
            line = _norm_line(row[0] if row else "")
            if not line or line in {"线路"}:
                continue
            if line in {"全网络", "合计", "总计"}:
                continue
            cells = _normalize_status_data_row([str(c or "").strip() for c in row], ncols)
            if cells is None:
                continue
            if len(cells) < 2:
                continue
            if line not in by_line:
                order.append(line)
            prev_cells = by_line.get(line)
            if prev_cells is not None:
                if row_all_zero_or_empty(cells) and not row_all_zero_or_empty(prev_cells):
                    continue
                if (
                    not row_all_zero_or_empty(cells)
                    and not row_all_zero_or_empty(prev_cells)
                    and _row_signature(prev_cells, ncols) != _row_signature(cells, ncols)
                ):
                    warnings.append(
                        f"{line}在「{line_src.get(line) or '?'}」与「{src}」数据不一致，已采用较新文件"
                    )
                by_line[line] = cells
            line_src[line] = src
    _backfill_table_lines(by_line, line_src, order, tables_sorted, ncols, warnings)
    out_rows = [list(r) for r in header]
    for line in sorted(order, key=_line_sort_key):
        row = by_line.get(line)
        if row is None:
            # 该线路在所有材料中都为空/全0行：不进表，避免 order 有键而 by_line 无键的 KeyError
            continue
        out_rows.append(row)
    for item in reversed(tables_sorted):
        rows = item.get("rows") or []
        _, start = _table_header_rows(rows)
        for row in rows[start:]:
            if _norm_line(row[0] if row else "") == "全网络":
                out_rows.append([str(c or "").strip() for c in row])
                break
        else:
            continue
        break
    note_items_merge = [
        {
            "notes": item.get("notes") or [],
            "_recency": item.get("_recency"),
            "_idx": item.get("_idx"),
            "_source": item.get("source") or "",
            "media": item.get("media") or [],
        }
        for item in tables_sorted
    ]
    captions: list[str] = []
    for item in tables_sorted:
        cap = item.get("caption") or ""
        if cap and cap not in captions:
            captions.append(cap)
    flow: list[dict[str, Any]] = []
    cap_text = captions[-1] if captions else ""
    if cap_text:
        flow.append({"kind": "para", "text": cap_text})
    out_rows = _trim_trailing_empty_cols(out_rows)
    if len(out_rows) > len(header):
        primary = _pick_primary_bucket(tables_sorted)
        sole = primary if len(tables_sorted) == 1 else None
        use_copy = bool(
            sole
            and sole.get("doc")
            and sole.get("block")
            and _trim_trailing_empty_cols([list(r) for r in sole.get("rows") or []]) == out_rows
        )
        flow.append(
            _status_table_flow_item(
                rows=out_rows,
                doc=sole.get("doc") if use_copy else None,
                block=sole.get("block") if use_copy else None,
                allow_copy=use_copy,
            )
        )
    primary_src = str((newest_item(tables_sorted) or {}).get("source") or "")
    warnings.extend(table_row_backfill_notes(line_src, primary_source=primary_src))
    note_flow, note_warn = _merge_table_notes_flow(
        out_rows if len(out_rows) > len(header) else None,
        note_items_merge,
        prior_docs,
        kind,
    )
    warnings.extend(note_warn)
    flow.extend(note_flow)
    flow = dedupe_flow_items([x for x in flow if not _is_empty_status_note(x)])
    paras = dedupe_texts([x.get("text") or "" for x in flow if x.get("kind") == "para"])
    return {
        "table": out_rows if len(out_rows) > len(header) else [],
        "paras": paras,
        "flow": flow,
        "source": "、".join(sources),
        "empty": len(out_rows) <= len(header),
        "warnings": warnings,
    }


def extract_status_distribution(
    docs: list[DocumentModel] | None,
    *,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, dict[str, Any]]:
    """五类状态分布：Excel 子表按线路计评价个数为主，Word 只取表后说明。"""
    from chapters.overhead.excel_status import (
        compare_and_backfill,
        extract_excel_status_tables,
        keep_present_status_lines,
        rebuild_status_network_row,
    )

    kinds = list(STATUS_TITLE_KEYS.values())
    out: dict[str, dict[str, Any]] = {}
    doc_list = list(docs or [])
    excel_hits = extract_excel_status_tables(doc_list)

    for kind in kinds:
        buckets: list[dict[str, Any]] = []
        for doc, idx in sort_docs_newest_last(doc_list):
            blocks = list(doc.blocks or [])
            recency = doc_recency_key(doc, idx)[0]
            table_indices: list[int] = []
            for i, block in enumerate(blocks):
                if block.type != "table" or not block.rows:
                    continue
                rows = [list(r) for r in block.rows]
                if not is_status_distribution_table(rows):
                    continue
                ctx = _context_before(blocks, i)
                kind_hit = classify_status_kind(ctx)
                if kind_hit != kind:
                    if kind_hit is not None:
                        continue
                    if not _doc_implies_kind(doc, kind):
                        continue
                table_indices.append(i)
            if not table_indices:
                continue
            all_status = [
                i
                for i, block in enumerate(blocks)
                if block.type == "table" and block.rows and is_status_distribution_table(block.rows)
            ]
            clusters = packed_status_table_clusters(blocks, all_status)
            last_of_packed = {cl[-1]: cl for cl in clusters if len(cl) >= 2}
            cluster_notes: dict[int, list[str]] = {}
            for last_i in last_of_packed:
                _media, harvested = _split_after_status_table(
                    blocks, last_i, doc, follow_line_sections=True
                )
                cluster_notes[last_i] = harvested
            packed_owner = {ti: cl[-1] for cl in last_of_packed.values() for ti in cl}
            for i in table_indices:
                block = blocks[i]
                rows = [list(r) for r in block.rows]
                owner = packed_owner.get(i)
                media, notes = _split_after_status_table(
                    blocks, i, doc, follow_line_sections=owner is not None
                )
                if owner is not None and cluster_notes.get(owner):
                    notes = list(cluster_notes[owner])
                table_notes: list[str] = []
                prev_c = ""
                for p in notes:
                    c = compact_text(p)
                    if not c or c == prev_c:
                        continue
                    prev_c = c
                    table_notes.append(p)
                ctx = _context_before(blocks, i)
                caption = ""
                for part in ctx.split():
                    if part.startswith("表") and ("状态" in part or "3-" in part):
                        caption = part
                        break
                if not caption:
                    caption = _CAPTION.get(kind) or ""
                buckets.append(
                    {
                        "rows": rows,
                        "source": _src(doc),
                        "caption": caption,
                        "notes": table_notes,
                        "media": media,
                        "_recency": recency,
                        "_idx": idx,
                        "block": block,
                        "doc": doc,
                    }
                )

        word_hit: dict[str, Any] = {}
        if buckets:
            word_hit = merge_status_tables(buckets, prior_docs=prior_docs, kind=kind)
        excel_hit = excel_hits.get(kind) or {}
        if excel_hit.get("empty"):
            excel_hit = {}
        if not word_hit.get("table") and not excel_hit.get("table"):
            continue

        if excel_hit.get("table"):
            rail = kind == "接触轨状态分布"
            table, diff_warn = compare_and_backfill(
                excel_hit["table"],
                word_hit.get("table"),
                excel_source=str(excel_hit.get("source") or ""),
                word_source=str(word_hit.get("source") or ""),
                backfill_from_word=rail,
            )
            if rail:
                table = keep_present_status_lines(table)
            else:
                table = rebuild_status_network_row(table)
            sources = [excel_hit.get("source") or ""]
            if rail and word_hit.get("source") and word_hit.get("table"):
                sources.append(word_hit["source"])
            flow: list[dict[str, Any]] = []
            caption = str(excel_hit.get("caption") or _CAPTION.get(kind) or "")
            if caption:
                flow.append({"kind": "para", "text": caption})
            flow.append(_status_table_flow_item(rows=table, allow_copy=False))
            if word_hit.get("flow"):
                keep_lines = _lines_in_table(table) if rail else None
                for item in word_hit.get("flow") or []:
                    if item.get("kind") == "table":
                        continue
                    t = str(item.get("text") or "")
                    if caption and compact_text(t) == compact_text(caption):
                        continue
                    if t.startswith("表3-"):
                        continue
                    if _is_empty_status_note(item):
                        continue
                    if keep_lines:
                        ln = _line_no(t.split("：", 1)[0].split(":", 1)[0])
                        if ln and ln not in keep_lines:
                            continue
                        mentioned = {int(x) for x in re.findall(r"(\d{1,2})\s*号线", t)}
                        if mentioned and not (mentioned & keep_lines):
                            continue
                    flow.append(item)
            hit = {
                "table": table,
                "paras": [x.get("text") or "" for x in flow if x.get("kind") == "para"],
                "flow": dedupe_flow_items(flow),
                "source": "；".join(s for s in sources if s),
                "empty": False,
                "warnings": diff_warn,
            }
        else:
            hit = word_hit
            newest = newest_item(buckets)
            if newest and hit.get("source"):
                hit["source"] = f"{newest.get('source') or ''}（主）；全表材料：{hit.get('source')}"
            hit["warnings"] = list(hit.get("warnings") or [])
            if hit.get("table"):
                if kind == "接触轨状态分布":
                    hit["table"] = keep_present_status_lines(hit["table"])
                else:
                    hit["table"] = rebuild_status_network_row(hit["table"])
                for item in hit.get("flow") or []:
                    if item.get("kind") == "table":
                        item["rows"] = hit["table"]
                        item["force_rebuild"] = True
            hit["flow"] = [x for x in (hit.get("flow") or []) if not _is_empty_status_note(x)]

        hit["warnings"] = list(hit.get("warnings") or []) + coverage_warnings(kind, hit.get("table"), prior_docs)
        out[kind] = hit

    return out


def extract_chapter_body_section(
    docs: list[DocumentModel] | None,
    *,
    chapter_h1: str,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
) -> dict[str, Any]:
    """在指定章 H1 之后切小节（避免目录/第二章同名标题干扰）。"""
    empty = {"paras": [], "flow": [], "source": "", "empty": True}
    for doc in docs or []:
        blocks = list(doc.blocks or [])
        armed = False
        take = False
        flow: list[dict[str, Any]] = []
        for block in blocks:
            t = (block.text or "").strip()
            c = compact_text(t)
            if not armed:
                if t and chapter_h1:
                    h = compact_text(chapter_h1)
                    if h and h in c and len(c) <= len(h) + 12 and not re.search(r"\d{2,}$", c):
                        if block.type == "heading" and int(block.level or 0) == 1:
                            armed = True
                        elif block.type == "paragraph" and (c == h or c.endswith(h)):
                            armed = True
                continue
            if t and is_peer_chapter_title(t, current=chapter_h1):
                break
            if not take:
                if t and any(compact_text(k) in c for k in start_keys) and len(c) < 48:
                    take = True
                continue
            from chapters.overhead.section_bundle import _should_stop_section

            if t and _should_stop_section(
                t,
                start_keys=start_keys,
                stop_keys=stop_keys,
                start_depth=2,
                heading=block.type == "heading",
                depth=int(block.level or 4),
            ):
                break
            if block.type == "drawing":
                from chapters.common.drawings import drawing_flow_item

                flow.append(drawing_flow_item(doc, block))
                continue
            if block.type == "table" and block.rows:
                if len(block.rows) > 80:
                    continue
                flow.append(table_flow_item(doc, block))
                continue
            if t:
                from chapters.common.source_yellow import para_flow_item

                flow.append(para_flow_item(t, block))
        paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
        if paras or any(x.get("kind") in {"table", "drawing", "formula"} for x in flow):
            return {
                "paras": paras,
                "flow": dedupe_flow_items(flow),
                "source": _src(doc),
                "empty": False,
            }
    return empty


def fill_ch3_method_standard(
    material_docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None,
) -> dict[str, dict[str, Any]]:
    chapter = "设备功能有效性评估"
    out: dict[str, dict[str, Any]] = {}

    def pick(title: str, starts: tuple[str, ...], stops: tuple[str, ...]) -> dict[str, Any]:
        # 评估方法/标准/A-D 类是体例，优先去年整表拷贝（保留表3-2 底纹）。
        for docs, label in ((prior_docs, "去年/保底"), (material_docs, "材料")):
            hit = extract_chapter_body_section(docs, chapter_h1=chapter, start_keys=starts, stop_keys=stops)
            if not hit.get("empty"):
                hit = dict(hit)
                if label != "材料" and hit.get("source"):
                    hit["source"] = f"{hit['source']}（体例回退）"
                return hit
        return {"paras": [], "flow": [], "source": "", "empty": True}

    out["评估方法和内容"] = pick("评估方法和内容", ("评估方法和内容",), ("评估标准", "接触网设备状态"))
    out["评估标准"] = pick("评估标准", ("评估标准",), ("接触网设备状态", "各线路管控", "A类设备"))
    for letter in ("A", "B", "C", "D"):
        title = f"{letter}类设备"
        hit = pick(title, (title, f"{letter}类"), ("A类设备", "B类设备", "C类设备", "D类设备", "接触网设备状态分布"))
        if hit.get("empty"):
            hit = extract_chapter_body_section(
                material_docs,
                chapter_h1=chapter,
                start_keys=(title,),
                stop_keys=tuple(x for x in ("A类设备", "B类设备", "C类设备", "D类设备", "接触网设备状态分布") if x != title),
            )
            if hit.get("empty"):
                hit = extract_chapter_body_section(
                    prior_docs,
                    chapter_h1=chapter,
                    start_keys=(title,),
                    stop_keys=tuple(x for x in ("A类设备", "B类设备", "C类设备", "D类设备", "接触网设备状态分布") if x != title),
                )
                if not hit.get("empty") and hit.get("source"):
                    hit["source"] = f"{hit['source']}（体例回退）"
        if not hit.get("empty"):
            out[title] = hit
    return out
