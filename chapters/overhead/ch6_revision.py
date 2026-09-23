# -*- coding: utf-8 -*-
"""第6章修程修制：合订合规稿里只留触网修订/新增，修订归 6.1，新增归 6.2。

6.1 认评估年编号：名称+编号表里编号以当年结尾的触网行才进，并抽出对应《…》修订内容。
上年编号（如 2025）的作业指导书表丢掉。当年工艺细则即使写在「新增」表里也改挂 6.1。
6.2 用触网规程分类表（可在修程章名之前）+ 集中修类新增指导书；零部件/工艺细则不进新增。
不写死书名、条号、文件名。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from chapters.common.section_slice import compact_text, dedupe_flow_items, dedupe_texts
from parsers.document_model import DocumentModel

_OH = ("接触网", "触网", "接触轨")
_PW = (
    "变电站",
    "变电设备",
    "变电所",
    "SCADA",
    "杂散电流",
    "应急电源",
    "电能计量",
    "电气设备试验",
    "直流应急",
    "整流机组",
    "主变压器",
)
_LEAD_RE = re.compile(r"(修正|修订了)\s*\d+\s*本")
_COUNT_LEAD_RE = re.compile(r"(修正|修订了|新增了)\s*\d+\s*(本\S*)")
_BOOK_RE = re.compile(r"《([^》]+)》")
_ITEM_NO_RE = re.compile(r"^[（(]?\d+[）)、.．、]\s*")
_YEAR_TAIL = re.compile(r"(20\d{2})\s*$")
_YEAR_DASH = re.compile(r"-(20\d{2})(?:\D|$)")
_CH6_H1 = "修程修制匹配性评估"
_PROCESS_SPEC_MARK = ("安装工艺细则", "工艺细则")
_STALE_GUIDE_MARK = (
    "柔性接触网维修作业指导书",
    "刚性接触网维修作业指导书",
    "接触轨维修作业指导书",
)
_DROP_NEW_MARK = ("零部件技术要求", "安装工艺细则", "工艺细则")


def book_domain(text: str) -> str:
    """overhead / power / mixed / unknown。"""
    t = compact_text(text or "")
    oh = any(k in t for k in _OH)
    pw = any(k in t for k in _PW)
    if oh and not pw:
        return "overhead"
    if pw and not oh:
        return "power"
    if oh and pw:
        return "mixed"
    return "unknown"


def is_addendum_lead(text: str) -> bool:
    t = compact_text(text or "")
    if "新增" not in t or "本" not in t:
        return False
    return any(k in t for k in ("规程", "指导书", "作业指导"))


def is_revision_lead(text: str) -> bool:
    t = compact_text(text or "")
    return bool(_LEAD_RE.search(t))


def is_book_body_lead(text: str) -> bool:
    t = compact_text(text or "")
    return "《" in (text or "") and any(k in t for k in ("修订内容", "新增内容"))


def _name_col(rows: list[list[str]]) -> int:
    if not rows:
        return 1
    for i, cell in enumerate(rows[0]):
        if "名称" in str(cell):
            return i
    return 1 if len(rows[0]) > 1 else 0


def _code_col(rows: list[list[str]]) -> int:
    if not rows:
        return -1
    for i, cell in enumerate(rows[0]):
        if "编号" in str(cell):
            return i
    return -1


def _looks_like_name_code_table(rows: list[list[str]] | None) -> bool:
    if not rows or len(rows) < 2:
        return False
    head = compact_text("".join(str(c) for c in rows[0]))
    return "名称" in head and ("编号" in head or "序号" in head)


def _looks_like_grade_count_table(rows: list[list[str]] | None) -> bool:
    if not rows or len(rows) < 2:
        return False
    head = "".join(str(c) for c in rows[0])
    return "等级" in head and bool(re.search(r"20\d{2}", head))


def cell_year(text: str) -> int | None:
    t = compact_text(text or "")
    m = _YEAR_TAIL.search(t)
    if m:
        return int(m.group(1))
    m = _YEAR_DASH.search(t)
    if m:
        return int(m.group(1))
    return None


def _row_name(row: list[str], name_i: int) -> str:
    if name_i < len(row):
        return str(row[name_i] or "")
    return " ".join(str(c) for c in row)


def _row_code(row: list[str], code_i: int) -> str:
    if code_i < 0 or code_i >= len(row):
        return " ".join(str(c) for c in row)
    return str(row[code_i] or "")


def filter_revision_table(
    rows: list[list[str]] | None,
    year: int | None = None,
    *,
    allow_unyear: bool = False,
) -> list[list[str]] | None:
    """名称+编号表只留触网行；给了评估年后，优先留编号尾年为当年的行。

    触网行全是上年编号 → 整表丢掉（那是上一评估年的修订目录）。
    编号没有年份时：allow_unyear 才留下（新增目录常截断年份）。
    """
    if not rows or len(rows) < 2:
        return list(rows or [])
    if not _looks_like_name_code_table(rows):
        return list(rows)
    name_i = _name_col(rows)
    code_i = _code_col(rows)
    oh_rows: list[list[str]] = []
    for row in rows[1:]:
        cells = [str(c) for c in row]
        if book_domain(_row_name(cells, name_i)) != "overhead":
            continue
        oh_rows.append(list(row))
    if not oh_rows:
        return None
    years = [cell_year(_row_code([str(c) for c in r], code_i)) for r in oh_rows]
    if year:
        dated = [r for r, y in zip(oh_rows, years) if y == year]
        if dated:
            oh_rows = dated
        elif any(y is not None and y != year for y in years):
            return None
        elif not allow_unyear and any(y is not None for y in years):
            return None
    kept = [list(rows[0])]
    for i, row in enumerate(oh_rows, start=1):
        new_row = list(row)
        if new_row and str(new_row[0]).isdigit():
            new_row[0] = str(i)
        kept.append(new_row)
    return kept


def _name_is_process_spec(name: str) -> bool:
    t = compact_text(name or "")
    return any(k in t for k in _PROCESS_SPEC_MARK)


def _name_is_stale_guide(name: str) -> bool:
    t = compact_text(name or "")
    return any(k in t for k in _STALE_GUIDE_MARK)


def _name_keep_new(name: str) -> bool:
    """6.2 新增目录只留集中修类指导书，不把工艺细则/零部件再列一遍。"""
    t = compact_text(name or "")
    if not t:
        return False
    if any(k in t for k in _DROP_NEW_MARK) or _name_is_stale_guide(t):
        return False
    return "指导书" in t or "集中修" in t


def filter_new_book_table(
    rows: list[list[str]] | None,
    year: int | None = None,
) -> list[list[str]] | None:
    filtered = filter_revision_table(rows, year=year, allow_unyear=True)
    if not filtered:
        return None
    name_i = _name_col(filtered)
    kept = [list(filtered[0])]
    n = 0
    for row in filtered[1:]:
        if not _name_keep_new(_row_name([str(c) for c in row], name_i)):
            continue
        n += 1
        new_row = list(row)
        if new_row and str(new_row[0]).isdigit():
            new_row[0] = str(n)
        kept.append(new_row)
    return kept if n else None


def rewrite_count_lead(text: str, n: int, *, names: list[str] | None = None) -> str:
    """修正11本三级规程 → 修正1本三级规程。条数跟留下的表行走。"""
    t = (text or "").strip()
    m = _COUNT_LEAD_RE.search(t)
    if not m:
        return t
    verb = m.group(1)
    bag = [compact_text(x) for x in (names or []) if compact_text(x)]
    if bag and all("指导书" in x for x in bag):
        unit = "本作业指导书"
    elif bag and all(any(k in x for k in ("细则", "工艺")) for x in bag):
        unit = "本三级规程"
    else:
        unit = m.group(2) or "本"
        if unit and not unit.startswith("本"):
            unit = "本" + unit
    return f"{verb}{n}{unit}。".replace("。。", "。")


def _book_title(text: str) -> str:
    m = _BOOK_RE.search(text or "")
    return compact_text(m.group(1)) if m else ""


def _strip_item_no(text: str) -> str:
    return _ITEM_NO_RE.sub("", (text or "").strip())


def _is_glue(text: str) -> bool:
    t = compact_text(text or "")
    if t.startswith("分别是"):
        return True
    if len(t) < 24 and t.startswith("表") and (len(t) < 2 or t[1].isdigit() or t[1] in " ：:-"):
        return True
    return False


def _replace_table_rows(item: dict[str, Any], filtered: list[list[str]]) -> dict[str, Any]:
    """筛过行的表不能再按 source_index 整表回拷，否则变电行会原样贴回来。"""
    new_item = dict(item)
    new_item["rows"] = filtered
    orig = item.get("rows") or []
    if [list(r) for r in filtered] != [list(r) for r in orig]:
        new_item["force_rebuild"] = True
        new_item.pop("source_index", None)
        new_item.pop("vmerge", None)
    return new_item


def _pop_lead_glue(out: list[dict[str, Any]]) -> None:
    while out:
        last = out[-1]
        t = str(last.get("text") or "")
        if last.get("kind") == "para" and (is_revision_lead(t) or is_addendum_lead(t) or _is_glue(t)):
            out.pop()
            continue
        break


def filter_overhead_revision_flow(
    flow: list[dict[str, Any]] | None,
    year: int | None = None,
    *,
    allow_unyear: bool = False,
) -> list[dict[str, Any]]:
    """合订整改里去掉变电/SCADA 组，只留接触网书和表；编号按评估年筛。"""
    items = list(flow or [])
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(items):
        item = items[i]
        kind = item.get("kind")
        text = str(item.get("text") or "")
        if kind == "table" and _looks_like_name_code_table(item.get("rows")):
            filtered = filter_revision_table(item.get("rows"), year=year, allow_unyear=allow_unyear)
            if not filtered:
                _pop_lead_glue(out)
                i += 1
                while i < len(items):
                    nxt = items[i]
                    nt = str(nxt.get("text") or "")
                    if nxt.get("kind") == "para" and (
                        is_revision_lead(nt) or is_addendum_lead(nt)
                    ):
                        break
                    if nxt.get("kind") == "table" and _looks_like_name_code_table(nxt.get("rows")):
                        break
                    i += 1
                continue
            new_item = _replace_table_rows(item, filtered)
            new_n = len(filtered) - 1
            if out and is_revision_lead(str(out[-1].get("text") or "")):
                lead = dict(out[-1])
                names = [
                    _row_name([str(c) for c in r], _name_col(filtered))
                    for r in filtered[1:]
                ]
                lead["text"] = rewrite_count_lead(str(lead.get("text") or ""), new_n, names=names)
                out[-1] = lead
            out.append(new_item)
            i += 1
            continue
        if kind == "para" and book_domain(text) == "power" and (is_book_body_lead(text) or is_revision_lead(text)):
            i += 1
            while i < len(items):
                nxt = items[i]
                nt = str(nxt.get("text") or "")
                if nxt.get("kind") == "para" and (
                    is_revision_lead(nt) or is_book_body_lead(nt) or is_addendum_lead(nt)
                ):
                    break
                if nxt.get("kind") == "table" and _looks_like_name_code_table(nxt.get("rows")):
                    break
                i += 1
            continue
        out.append(item)
        i += 1
    kept_rev, kept_add = _names_by_side(out)
    trimmed: list[dict[str, Any]] = []
    skip_body = False
    for item in out:
        text = str(item.get("text") or "")
        if item.get("kind") == "para" and is_book_body_lead(text):
            name = _book_title(text)
            pool = kept_add if "新增内容" in compact_text(text) else kept_rev
            skip_body = bool(name) and bool(pool) and name not in pool
            if skip_body:
                continue
        elif skip_body:
            if item.get("kind") == "para" and (
                is_book_body_lead(text) or is_revision_lead(text) or is_addendum_lead(text)
            ):
                skip_body = False
            else:
                continue
        if skip_body:
            continue
        trimmed.append(item)
    return trimmed


def _names_by_side(flow: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """修订表名 / 新增表名分开，避免新增目录把修订《书》正文裁掉。"""
    rev: set[str] = set()
    add: set[str] = set()
    side = rev
    for item in flow or []:
        if item.get("kind") == "para" and is_addendum_lead(str(item.get("text") or "")):
            side = add
        if item.get("kind") != "table":
            continue
        rows = item.get("rows") or []
        if not _looks_like_name_code_table(rows):
            continue
        idx = _name_col(rows)
        for row in rows[1:]:
            side.add(compact_text(_row_name([str(c) for c in row], idx)))
    return rev, add


def _names_from_tables(flow: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in flow:
        if item.get("kind") != "table":
            continue
        rows = item.get("rows") or []
        if not _looks_like_name_code_table(rows):
            continue
        idx = _name_col(rows)
        for row in rows[1:]:
            names.add(compact_text(_row_name([str(c) for c in row], idx)))
    return names


def split_revision_and_new(flow: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """「新增了N本…」之后的块给 6.2，前面修订留 6.1。"""
    rev: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    side = rev
    for item in flow or []:
        if item.get("kind") == "para" and is_addendum_lead(str(item.get("text") or "")):
            side = new
        side.append(item)
    return rev, new


def _renumber_name_table(header: list, rows: list[list]) -> list[list[str]]:
    kept = [list(header)]
    for i, row in enumerate(rows, start=1):
        new_row = list(row)
        if new_row and str(new_row[0]).isdigit():
            new_row[0] = str(i)
        kept.append(new_row)
    return kept


def promote_process_spec(
    rev: list[dict[str, Any]],
    new: list[dict[str, Any]],
    year: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """新增表里的当年工艺细则改挂 6.1，不再当作 6.2 新书。"""
    spec_items: list[dict[str, Any]] = []
    rest_new: list[dict[str, Any]] = []
    i = 0
    items = list(new or [])
    while i < len(items):
        item = items[i]
        text = str(item.get("text") or "")
        if item.get("kind") == "table" and _looks_like_name_code_table(item.get("rows")):
            rows = item.get("rows") or []
            name_i = _name_col(rows)
            code_i = _code_col(rows)
            spec_rows: list[list] = []
            other_rows: list[list] = []
            for row in rows[1:]:
                cells = [str(c) for c in row]
                name = _row_name(cells, name_i)
                y = cell_year(_row_code(cells, code_i))
                year_ok = not year or y == year or y is None
                if _name_is_process_spec(name) and book_domain(name) != "power" and year_ok:
                    spec_rows.append(list(row))
                else:
                    other_rows.append(list(row))
            if spec_rows:
                spec_items.append(_replace_table_rows(item, _renumber_name_table(rows[0], spec_rows)))
                if other_rows:
                    rest_new.append(_replace_table_rows(item, _renumber_name_table(rows[0], other_rows)))
                i += 1
                continue
        if item.get("kind") == "para" and is_book_body_lead(text):
            name = _book_title(text)
            if _name_is_process_spec(name) and "修订内容" in compact_text(text):
                spec_items.append(item)
                i += 1
                while i < len(items):
                    nxt = items[i]
                    nt = str(nxt.get("text") or "")
                    if nxt.get("kind") == "para" and (
                        is_book_body_lead(nt) or is_addendum_lead(nt) or is_revision_lead(nt)
                    ):
                        break
                    if nxt.get("kind") == "table":
                        break
                    spec_items.append(nxt)
                    i += 1
                continue
        rest_new.append(item)
        i += 1
    if not spec_items:
        return list(rev or []), list(new or [])
    already = any(_name_is_process_spec(n) for n in _names_from_tables(rev or []))
    if already:
        extra = [x for x in spec_items if not (x.get("kind") == "table" and _looks_like_name_code_table(x.get("rows")))]
        return list(rev or []) + extra, rest_new
    lead = {"kind": "para", "text": "修正1本三级规程。"}
    return [lead, *spec_items, *(rev or [])], rest_new


def _drop_orphan_revision_leads(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """「修订了3本作业指导书」后面若没有名称编号表，就是通稿空导语，丢掉。"""
    items = list(flow or [])
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(items):
        item = items[i]
        text = str(item.get("text") or "")
        if item.get("kind") == "para" and is_revision_lead(text):
            j = i + 1
            while j < len(items) and items[j].get("kind") == "para" and _is_glue(str(items[j].get("text") or "")):
                j += 1
            if j < len(items) and items[j].get("kind") == "table" and _looks_like_name_code_table(items[j].get("rows")):
                out.append(item)
                i += 1
                continue
            i = j
            continue
        out.append(item)
        i += 1
    return out


def _n_spec(flow: list[dict[str, Any]] | None) -> int:
    return sum(1 for n in _names_from_tables(flow or []) if _name_is_process_spec(n))


def _addendum_book_names(flow: list[dict[str, Any]] | None) -> set[str]:
    return {n for n in _names_from_tables(flow or []) if _name_keep_new(n)}


def _is_count_caption(text: str) -> bool:
    t = compact_text(text or "")
    if "规程分类" in t:
        return True
    if "如表6-1" in t or "如表5-3" in (text or ""):
        return True
    return bool(re.match(r"表\s*\d+\s*-\s*\d+", (text or "").strip()))


def _merge_ent_flows(
    count_flow: list[dict[str, Any]],
    add_flow: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """分类表来自一份材料、新增指导书来自另一份时拼成 6.2。"""
    out: list[dict[str, Any]] = []
    for item in count_flow or []:
        text = str(item.get("text") or "")
        if item.get("kind") == "table" and _looks_like_name_code_table(item.get("rows")):
            continue
        if item.get("kind") == "para" and (
            is_addendum_lead(text) or is_book_body_lead(text)
        ):
            continue
        out.append(item)
    for item in add_flow or []:
        text = str(item.get("text") or "")
        if item.get("kind") == "table" and _looks_like_grade_count_table(item.get("rows")):
            continue
        if item.get("kind") == "para" and _is_count_caption(text) and not is_addendum_lead(text):
            continue
        out.append(item)
    return out


def _to_fill(hit: dict[str, Any], flow: list[dict[str, Any]], sections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    flow = dedupe_flow_items(list(flow or []))
    paras = dedupe_texts(
        [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    )
    table: list[list[str]] = []
    for x in flow:
        if x.get("kind") == "table" and x.get("rows"):
            table = x["rows"]
            break
    sections = list(sections or [])
    empty = not (
        paras
        or (table and len(table) > 1)
        or any(x.get("kind") in {"table", "drawing", "para"} for x in flow)
        or any(not s.get("empty") for s in sections)
    )
    return {
        "paras": paras,
        "flow": flow,
        "table": table,
        "sections": sections,
        "source": hit.get("source") or "",
        "empty": empty,
    }


def _child(title: str, flow: list[dict[str, Any]], source: str) -> dict[str, Any]:
    flow = dedupe_flow_items(list(flow or []))
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    table: list[list[str]] = []
    for x in flow:
        if x.get("kind") == "table" and x.get("rows"):
            table = x["rows"]
            break
    empty = not flow
    return {
        "title": title,
        "paras": paras,
        "empty": empty,
        "source": source,
        "content_child": True,
        "fill": {
            "paras": paras,
            "flow": flow,
            "table": table,
            "sections": [],
            "source": source,
            "empty": empty,
        },
    }


def layout_revision_sections(flow: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """6.1.1 修正 N 本…（表）+ 6.1.2 《书》修订内容。标题跟材料导语走，不写死书名。"""
    sections: list[dict[str, Any]] = []
    items = list(flow or [])
    i = 0
    while i < len(items):
        item = items[i]
        kind = item.get("kind")
        text = str(item.get("text") or "").strip()
        if kind == "para" and is_revision_lead(text):
            table_items: list[dict[str, Any]] = []
            j = i + 1
            while j < len(items):
                nxt = items[j]
                nt = str(nxt.get("text") or "").strip()
                if nxt.get("kind") == "table" and _looks_like_name_code_table(nxt.get("rows")):
                    table_items.append(nxt)
                    j += 1
                    break
                if nxt.get("kind") == "para" and (
                    is_book_body_lead(nt) or is_revision_lead(nt) or is_addendum_lead(nt)
                ):
                    break
                if nxt.get("kind") == "para" and _is_glue(nt):
                    j += 1
                    continue
                j += 1
            n = max(0, len((table_items[0].get("rows") or [])) - 1) if table_items else 0
            if table_items and n:
                names = [
                    _row_name([str(c) for c in r], _name_col(table_items[0].get("rows") or []))
                    for r in (table_items[0].get("rows") or [])[1:]
                ]
                sections.append(_child(rewrite_count_lead(text, n, names=names).rstrip("。"), table_items, source))
            i = j
            continue
        if kind == "para" and is_book_body_lead(text) and "修订内容" in compact_text(text):
            body: list[dict[str, Any]] = []
            j = i + 1
            while j < len(items):
                nxt = items[j]
                nt = str(nxt.get("text") or "").strip()
                if nxt.get("kind") == "para" and (
                    is_book_body_lead(nt) or is_revision_lead(nt) or is_addendum_lead(nt)
                ):
                    break
                body.append(nxt)
                j += 1
            sections.append(_child(_strip_item_no(text), body, source))
            i = j
            continue
        if kind == "table" and _looks_like_name_code_table(item.get("rows")):
            n = max(0, len(item.get("rows") or []) - 1)
            if n:
                sections.append(_child(f"修正{n}本三级规程", [item], source))
            i += 1
            continue
        i += 1
    return [s for s in sections if not s.get("empty")]


def _prof_col(rows: list[list[str]]) -> int:
    for i, cell in enumerate(rows[0]):
        if "专业" in str(cell):
            return i
    return 0


def filter_count_table_overhead(rows: list[list[str]] | None) -> list[list[str]] | None:
    """规程分类多年份表只留触网专业行（含其后空专业续行和总计）。"""
    if not rows or len(rows) < 2:
        return None
    if not _looks_like_grade_count_table(rows):
        return list(rows)
    pcol = _prof_col(rows)
    kept = [list(rows[0])]
    taking = False
    for row in rows[1:]:
        cells = [str(c) for c in row]
        prof = compact_text(cells[pcol] if pcol < len(cells) else "")
        blob = compact_text("".join(cells))
        if any(k in prof or k in blob[:12] for k in _OH):
            taking = True
            kept.append(list(row))
            continue
        if any(k in prof for k in ("供电", "变电")) and not any(k in prof for k in _OH):
            taking = False
            continue
        if taking:
            kept.append(list(row))
    if len(kept) < 2:
        return None
    return kept


def retitle_ch6_captions(text: str) -> str:
    """第六章企标不沿用第五章表号。"""
    t = text or ""
    if "如表" in t or "规程分类" in t or re.match(r"表\s*\d+-\d+", t.strip()):
        return re.sub(r"表\s*\d+\s*-\s*\d+", "表6-1", t)
    return t


def layout_enterprise_flow(flow: list[dict[str, Any]] | None, year: int | None = None) -> list[dict[str, Any]]:
    """6.2：触网分类表 + 当年新增触网指导书 + 对应新增内容。"""
    items = list(flow or [])
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(items):
        item = items[i]
        kind = item.get("kind")
        text = str(item.get("text") or "")
        if kind == "table" and _looks_like_grade_count_table(item.get("rows")):
            filtered = filter_count_table_overhead(item.get("rows"))
            if not filtered:
                _pop_lead_glue(out)
                i += 1
                continue
            new_item = _replace_table_rows(item, filtered)
            out.append(new_item)
            i += 1
            continue
        if kind == "table" and _looks_like_name_code_table(item.get("rows")):
            filtered = filter_new_book_table(item.get("rows"), year=year)
            if not filtered:
                _pop_lead_glue(out)
                i += 1
                continue
            new_item = _replace_table_rows(item, filtered)
            new_n = len(filtered) - 1
            if out and is_addendum_lead(str(out[-1].get("text") or "")):
                lead = dict(out[-1])
                names = [
                    _row_name([str(c) for c in r], _name_col(filtered))
                    for r in filtered[1:]
                ]
                lead["text"] = rewrite_count_lead(str(lead.get("text") or ""), new_n, names=names)
                out[-1] = lead
            out.append(new_item)
            i += 1
            continue
        if kind == "para" and book_domain(text) == "power" and is_book_body_lead(text):
            i += 1
            while i < len(items):
                nxt = items[i]
                nt = str(nxt.get("text") or "")
                if nxt.get("kind") == "para" and (
                    is_book_body_lead(nt) or is_addendum_lead(nt) or is_revision_lead(nt)
                ):
                    break
                if nxt.get("kind") == "table":
                    break
                i += 1
            continue
        if kind == "para":
            new_item = dict(item)
            new_item["text"] = retitle_ch6_captions(text)
            out.append(new_item)
            i += 1
            continue
        out.append(item)
        i += 1
    kept_names = _addendum_book_names(out)
    trimmed: list[dict[str, Any]] = []
    skip_body = False
    skip_orphan_add = False
    skip_dropped_body = False
    for item in out:
        text = str(item.get("text") or "")
        if item.get("kind") == "para" and is_addendum_lead(text) and not kept_names:
            skip_orphan_add = True
            continue
        if skip_orphan_add:
            if item.get("kind") == "para" and _is_glue(text):
                continue
            skip_orphan_add = False
        if item.get("kind") == "para" and any(k in compact_text(text) for k in _DROP_NEW_MARK):
            skip_dropped_body = True
            continue
        if item.get("kind") == "para" and "《" in text:
            t = compact_text(text)
            if "规定了" in t and "新增内容" not in t and "修订内容" not in t:
                skip_dropped_body = True
                continue
        if skip_dropped_body:
            if item.get("kind") == "table":
                skip_dropped_body = False
            elif item.get("kind") == "para" and (
                "《" in text or is_addendum_lead(text) or is_book_body_lead(text)
            ):
                skip_dropped_body = False
            else:
                continue
        if item.get("kind") == "para" and is_book_body_lead(text):
            name = _book_title(text)
            skip_body = bool(name) and name not in kept_names
            if skip_body:
                continue
        elif skip_body:
            if item.get("kind") == "para" and (is_book_body_lead(text) or is_addendum_lead(text)):
                skip_body = False
            else:
                continue
        if skip_body:
            continue
        trimmed.append(item)
    return trimmed


def _year_oh_score(flow: list[dict[str, Any]], year: int) -> tuple[int, int]:
    n_year = 0
    n_body = 0
    for item in flow:
        if item.get("kind") == "table" and _looks_like_name_code_table(item.get("rows")):
            rows = item.get("rows") or []
            code_i = _code_col(rows)
            name_i = _name_col(rows)
            for row in rows[1:]:
                cells = [str(c) for c in row]
                if book_domain(_row_name(cells, name_i)) != "overhead":
                    continue
                if cell_year(_row_code(cells, code_i)) == year:
                    n_year += 1
        if item.get("kind") == "para" and is_book_body_lead(str(item.get("text") or "")):
            if book_domain(str(item.get("text") or "")) == "overhead":
                n_body += 1
    return n_year, n_body


def _hit_flow(doc: DocumentModel, start_keys: tuple[str, ...], stop_keys: tuple[str, ...]) -> dict[str, Any]:
    from chapters.overhead.material_merge import sanitize_overhead_bundle_hit
    from chapters.overhead.section_bundle import extract_subsection_bundle

    hit = extract_subsection_bundle(
        doc,
        start_keys=start_keys,
        stop_keys=stop_keys,
        chapter_h1=_CH6_H1,
        max_blocks=320,
    )
    rec = sanitize_overhead_bundle_hit(hit)
    rec["_source"] = doc.source_name or ""
    rec["source"] = doc.source_name or ""
    return rec


def _hit_enterprise_before_h1(doc: DocumentModel) -> dict[str, Any]:
    """4&5 常把触网分类表写在修程章名之前；章窗口切掉后从章名前回取。"""
    from chapters.overhead.material_merge import sanitize_overhead_bundle_hit
    from chapters.overhead.section_bundle import (
        _collect_section_flow,
        _heading_matches,
        looks_like_toc_line,
    )

    blocks = list(doc.blocks or [])
    h1_i: int | None = None
    for i, block in enumerate(blocks):
        t = (block.text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        if _heading_matches(t, (_CH6_H1,)) and len(compact_text(t)) < 40:
            h1_i = i
            break
    empty = {"paras": [], "flow": [], "source": doc.source_name or "", "empty": True}
    if h1_i is None or h1_i <= 0:
        return empty
    start_i: int | None = None
    for i in range(h1_i - 1, -1, -1):
        t = (blocks[i].text or "").strip()
        if not t or looks_like_toc_line(t):
            continue
        if getattr(blocks[i], "type", "") == "heading" and int(getattr(blocks[i], "level", 0) or 0) == 1:
            break
        if _heading_matches(t, ("企业标准和制度", "企业标准")) and len(compact_text(t)) < 64:
            start_i = i
            break
    if start_i is None:
        return empty
    start = blocks[start_i]
    flow = _collect_section_flow(
        doc,
        blocks,
        start_i=start_i,
        start_depth=int(getattr(start, "level", 0) or 2),
        start_keys=("企业标准和制度", "企业标准"),
        stop_keys=(_CH6_H1, "修程修制匹配性", "评估小结", "运维表现健康度评估"),
        table_predicate=None,
        max_blocks=80,
    )
    hit = {
        "flow": flow,
        "paras": [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()],
        "source": doc.source_name or "",
        "empty": not flow,
    }
    rec = sanitize_overhead_bundle_hit(hit)
    rec["_source"] = doc.source_name or ""
    rec["source"] = doc.source_name or ""
    return rec


def _laid_fill(raw: dict[str, Any], flow: list[dict[str, Any]]) -> dict[str, Any]:
    hit = dict(raw)
    hit["flow"] = flow
    hit["paras"] = [
        str(x.get("text") or "")
        for x in flow
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ]
    hit["empty"] = not flow
    return hit


def _ent_has_count(flow: list[dict[str, Any]]) -> bool:
    return any(x.get("kind") == "table" and _looks_like_grade_count_table(x.get("rows")) for x in flow)


def _ent_has_add(flow: list[dict[str, Any]]) -> bool:
    if _addendum_book_names(flow):
        return True
    return any(x.get("kind") == "para" and is_addendum_lead(str(x.get("text") or "")) for x in flow)


def count_table_year_filled(rows: list[list[str]] | None, year: int | None) -> int:
    """分类表里评估年列有数字的行数。空的 2026 列不能当今年表。"""
    if not rows or not year:
        return 0
    col = None
    for i, cell in enumerate(rows[0]):
        if str(year) in compact_text(str(cell)):
            col = i
            break
    if col is None:
        return 0
    n = 0
    for row in rows[1:]:
        if col < len(row) and re.search(r"\d", str(row[col] or "").strip()):
            n += 1
    return n


def _flow_year_filled(flow: list[dict[str, Any]], year: int) -> int:
    best = 0
    for item in flow or []:
        if item.get("kind") == "table" and _looks_like_grade_count_table(item.get("rows")):
            best = max(best, count_table_year_filled(item.get("rows"), year))
    return best


def _name_matches_book(title: str, names: set[str]) -> bool:
    t = compact_text(title or "")
    if not t:
        return False
    bag = {compact_text(n) for n in names if compact_text(n)}
    if t in bag:
        return True
    for n in bag:
        if t in n or n in t:
            return True
        if _name_is_process_spec(t) and _name_is_process_spec(n):
            return True
        if "集中修" in t and "集中修" in n:
            return True
    return False


def _flow_has_kind_body(flow: list[dict[str, Any]], kind: str) -> bool:
    return any(
        x.get("kind") == "para"
        and is_book_body_lead(str(x.get("text") or ""))
        and kind in compact_text(str(x.get("text") or ""))
        for x in flow or []
    )


def harvest_book_bodies(
    docs: list[DocumentModel] | None,
    names: set[str],
    kind: str,
    year: int,
) -> list[dict[str, Any]]:
    """跨材料补《书》修订内容/新增内容，优先较新的合规合订。"""
    from chapters.overhead.section_bundle import compliance_pack_rank, doc_recency_key, sort_docs_newest_last

    if not names:
        return []
    best: list[dict[str, Any]] = []
    best_key: tuple | None = None
    for doc, idx in sort_docs_newest_last(docs or []):
        rec = doc_recency_key(doc, idx)
        flow: list[dict[str, Any]] = []
        blocks = list(doc.blocks or [])
        i = 0
        while i < len(blocks):
            text = (blocks[i].text or "").strip()
            if is_book_body_lead(text) and kind in compact_text(text):
                if _name_matches_book(_book_title(text), names):
                    flow.append({"kind": "para", "text": text})
                    i += 1
                    while i < len(blocks):
                        nxt = blocks[i]
                        nt = (nxt.text or "").strip()
                        if getattr(nxt, "type", "") == "table":
                            break
                        if nt and (
                            is_book_body_lead(nt) or is_addendum_lead(nt) or is_revision_lead(nt)
                        ):
                            break
                        if nt:
                            flow.append({"kind": "para", "text": nt})
                        i += 1
                    continue
            i += 1
        if not flow:
            continue
        key = (len(flow), compliance_pack_rank(doc.source_name or ""), rec[0], rec[2])
        if best_key is None or key > best_key:
            best_key = key
            best = flow
    return best


def _material_roots_from_docs(docs: list[DocumentModel] | None) -> list[Path]:
    roots: list[Path] = []
    for doc in docs or []:
        p = Path(doc.source_path or "")
        if not p.is_file():
            continue
        for parent in p.parents:
            if parent.name == "评估材料":
                roots.append(parent)
                break
    base = Path(r"F:\材料")
    if base.is_dir():
        try:
            for child in base.iterdir():
                if child.is_dir() and "供电评估" in child.name:
                    cand = child / "评估材料"
                    if cand.is_dir():
                        roots.append(cand)
        except OSError:
            pass
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def ensure_latest_compliance_docs(
    docs: list[DocumentModel] | None,
    year: int,
) -> list[DocumentModel]:
    """任务没传最新合规合订时，从评估材料目录补入更高编号的 5&6 一类稿。"""
    from chapters.common.domain_filter import prepare_overhead_docs
    from chapters.overhead.section_bundle import compliance_pack_rank

    docs = list(docs or [])
    if not any(Path(d.source_path or "").is_file() for d in docs):
        return docs
    have_rank = max((compliance_pack_rank(d.source_name or "") for d in docs), default=0)
    have_names = {Path(d.source_name or d.source_path or "").name for d in docs}
    best: Path | None = None
    best_key: tuple | None = None
    for root in _material_roots_from_docs(docs):
        if not root.is_dir():
            continue
        try:
            paths = root.rglob("*.docx")
        except OSError:
            continue
        for path in paths:
            name = path.name
            if name.startswith("~$") or "合规" not in name:
                continue
            if name in have_names:
                continue
            rank = compliance_pack_rank(name)
            if rank <= have_rank:
                continue
            try:
                key = (rank, int(str(year) in name), path.stat().st_mtime)
            except OSError:
                continue
            if best_key is None or key > best_key:
                best_key = key
                best = path
    if best is None:
        return docs
    try:
        from parsers.dispatch import parse_file

        extra = parse_file(best)
    except OSError:
        return docs
    extra.source_name = best.name
    extra.source_path = str(best)
    kept = prepare_overhead_docs([extra])
    return docs + kept if kept else docs


def extract_overhead_ch6(docs: list[DocumentModel] | None, year: int) -> dict[str, dict[str, Any]]:
    """当年工艺细则 → 6.1；触网分类表 + 集中修新增 → 6.2。"""
    from chapters.overhead.section_bundle import doc_recency_key, sort_docs_newest_last

    docs = ensure_latest_compliance_docs(docs, year)
    revise_best: tuple | None = None
    revise_hit: dict[str, Any] | None = None
    count_best: tuple | None = None
    count_hit: dict[str, Any] | None = None
    add_best: tuple | None = None
    add_hit: dict[str, Any] | None = None

    def consider_ent(raw: dict[str, Any], laid: list[dict[str, Any]], rec: tuple) -> None:
        nonlocal count_best, count_hit, add_best, add_hit
        if not laid:
            return
        has_count = _ent_has_count(laid)
        has_add = _ent_has_add(laid)
        n_add = _year_oh_score(laid, year)[0]
        n_year_cells = _flow_year_filled(laid, year)
        packed = _laid_fill(raw, laid)
        if has_count:
            keyc = (n_year_cells, int(rec[1]), int(has_add), n_add, rec[0], rec[2])
            if count_best is None or keyc > count_best:
                count_best = keyc
                count_hit = packed
        if has_add or n_add:
            keya = (n_add, int(rec[1]), rec[0], rec[2])
            if add_best is None or keya > add_best:
                add_best = keya
                add_hit = packed

    for doc, idx in sort_docs_newest_last(docs or []):
        rec = doc_recency_key(doc, idx)
        raw = _hit_flow(
            doc,
            ("对上一年度合规性评估建议的整改", "对上一年度合规性"),
            ("企业标准和制度", "评估小结", "运维表现健康度评估"),
        )
        flow = filter_overhead_revision_flow(raw.get("flow") or [], year=year)
        rev_only, new_side = split_revision_and_new(flow)
        rev_only, new_side = promote_process_spec(rev_only, new_side, year)
        rev_only = _drop_orphan_revision_leads(rev_only)
        rev_only = filter_overhead_revision_flow(rev_only, year=year)
        n_year, n_body = _year_oh_score(rev_only, year)
        n_spec = _n_spec(rev_only)
        if n_spec or n_year or n_body:
            # 工艺细则优先于通稿「修订了3本作业指导书」；5&6 合订优先于修程修志。
            key = (n_spec, n_year, rec[1], n_body, rec[0], rec[2])
            if revise_best is None or key > revise_best:
                revise_best = key
                revise_hit = _laid_fill(raw, rev_only)
        consider_ent(raw, layout_enterprise_flow(new_side, year=year), rec)
        raw2 = _hit_flow(
            doc,
            ("企业标准和制度", "企业标准"),
            ("评估小结", "运维表现健康度评估"),
        )
        consider_ent(raw2, layout_enterprise_flow(raw2.get("flow") or [], year=year), rec)
        raw3 = _hit_enterprise_before_h1(doc)
        consider_ent(raw3, layout_enterprise_flow(raw3.get("flow") or [], year=year), rec)

    out: dict[str, dict[str, Any]] = {}
    if revise_hit:
        rev = list(revise_hit.get("flow") or [])
        names = _names_from_tables(rev)
        if names and not _flow_has_kind_body(rev, "修订内容"):
            extra = harvest_book_bodies(docs, names, "修订内容", year)
            if extra:
                rev = rev + extra
                revise_hit = _laid_fill(revise_hit, rev)
        sections = layout_revision_sections(rev, revise_hit.get("source") or "")
        fill = _to_fill(revise_hit, [] if sections else rev, sections)
        fill["empty"] = not sections and not rev
        out["对上一年度合规性评估建议的整改"] = fill
        if sections:
            out["_lines_对上一年度合规性评估建议的整改"] = {
                "sections": sections,
                "source": revise_hit.get("source") or "",
                "empty": False,
            }
    ent_hit: dict[str, Any] | None = None
    if count_hit and add_hit:
        cflow = list(count_hit.get("flow") or [])
        aflow = list(add_hit.get("flow") or [])
        if _addendum_book_names(cflow) and _flow_year_filled(cflow, year) >= _flow_year_filled(aflow, year):
            ent_hit = count_hit
        else:
            ent_hit = _laid_fill(count_hit, _merge_ent_flows(cflow, aflow))
    elif count_hit:
        ent_hit = count_hit
    elif add_hit:
        ent_hit = add_hit
    if ent_hit and not ent_hit.get("empty"):
        flow = list(ent_hit.get("flow") or [])
        names = _addendum_book_names(flow)
        if names and not _flow_has_kind_body(flow, "新增内容"):
            extra = harvest_book_bodies(docs, names, "新增内容", year)
            if extra:
                flow = flow + extra
                ent_hit = _laid_fill(ent_hit, flow)
        if flow:
            out["企业标准和制度"] = _to_fill(ent_hit, flow)
    return out


def apply_ch6_layout(fills: dict[str, dict[str, Any]], year: int | None = None) -> dict[str, dict[str, Any]]:
    """6.1 只留修订；6.2 收新增；供电书从整改里拿掉。已按年结构化的不再拆。"""
    out = dict(fills)
    key61 = next((k for k in out if "对上一年度合规性评估建议的整改" in k and not str(k).startswith("_")), "")
    key62 = next((k for k in out if compact_text(k) == compact_text("企业标准和制度")), "")
    if not key61:
        return out
    hit = out.get(key61) or {}
    if hit.get("sections"):
        return out
    if hit.get("empty"):
        return out
    flow = filter_overhead_revision_flow(hit.get("flow") or [], year=year)
    rev, new = split_revision_and_new(flow)
    rev, new = promote_process_spec(rev, new, year)
    rev = filter_overhead_revision_flow(_drop_orphan_revision_leads(rev), year=year)
    sections = layout_revision_sections(rev, hit.get("source") or "")
    out[key61] = _to_fill(hit, [] if sections else rev, sections)
    if sections:
        out["_lines_对上一年度合规性评估建议的整改"] = {
            "sections": sections,
            "source": hit.get("source") or "",
            "empty": False,
        }
    other = out.get(key62) if key62 else None
    if new and (not other or other.get("empty")):
        title = key62 or "企业标准和制度"
        out[title] = _to_fill(hit, layout_enterprise_flow(new, year=year))
    return out
