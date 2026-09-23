# -*- coding: utf-8 -*-
"""从接触网 Excel 台账汇总状态分布，并与 Word 表对照。

认表头（线路+评价），不要求工作表名固定。
柔性锚段/刚性锚段/三轨/隔离开关/控制屏 → 第 3 章表 3-5～3-8（按线路计评价个数）。
接触网系统子表 → 第 3 章 3.4 的表3-9（原表，不是状态分布）；不进第 4 章。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from chapters.common.section_slice import compact_text
from chapters.overhead.line_notes import row_all_zero_or_empty
from chapters.overhead.section_bundle import doc_recency_key, sort_docs_newest_last
from parsers.document_model import DocumentModel

_LINE_RE = re.compile(r"(\d{1,2})\s*号线")

SHEET_TO_KIND = {
    "柔性锚段": "各线路柔性接触网状态分布",
    "刚性锚段": "各线路刚性接触网状态分布",
    "三轨区间": "接触轨状态分布",
    "隔离开关": "各线路隔离开关状态分布",
    "隔离开关控制屏": "各线路隔离开关控制屏状态分布",
}

KIND_COUNT_LABEL = {
    "各线路柔性接触网状态分布": "锚段数量",
    "各线路刚性接触网状态分布": "锚段数量",
    "接触轨状态分布": "区段数量",
    "各线路隔离开关状态分布": "总数量",
    "各线路隔离开关控制屏状态分布": "总数量",
}

KIND_COUNT_UNIT = {
    "各线路柔性接触网状态分布": "锚段数",
    "各线路刚性接触网状态分布": "锚段数",
    "接触轨状态分布": "区段数",
    "各线路隔离开关状态分布": "数量",
    "各线路隔离开关控制屏状态分布": "数量",
}

RAIL_KIND = "接触轨状态分布"
FLEX_KIND = "各线路柔性接触网状态分布"
RIGID_KIND = "各线路刚性接触网状态分布"
# 17 号线为接触轨线路，柔/刚状态表不列全 0 行。
KIND_SKIP_LINES = {
    FLEX_KIND: frozenset({"17号线"}),
    RIGID_KIND: frozenset({"17号线"}),
}

SYSTEM_SHEET = "接触网系统"
SYSTEM_KIND = "接触网设备状态分布"
SYSTEM_CAPTION = "表3-9 各线路触网状态分布"
TABLE_3_9_LEAD = (
    "触网包括如下内容：接触网（刚、柔），三轨、隔离开关、隔离开关控制屏，"
    "各线路触网状态分布如下表3-9："
)

KIND_CAPTION = {
    "各线路柔性接触网状态分布": "表3-5a 各线路柔性接触网状态",
    "各线路刚性接触网状态分布": "表3-5b 各线路刚性接触网状态",
    "接触轨状态分布": "表3-6 各线路接触轨状态",
    "各线路隔离开关状态分布": "表3-7 各线路隔离开关状态",
    "各线路隔离开关控制屏状态分布": "表3-8 各线路隔离开关控制屏状态",
}

STATUS_LINE_NOS = tuple(range(1, 19))


def canonical_line_labels(n_max: int = 18) -> list[str]:
    return [f"{i}号线" for i in range(1, n_max + 1)]


def line_labels_for_kind(kind: str) -> list[str]:
    skip = KIND_SKIP_LINES.get(kind) or frozenset()
    return [ln for ln in canonical_line_labels() if ln not in skip]


def _norm_line(cell: str) -> str:
    t = re.sub(r"\s+", "", str(cell or "").strip().lstrip("_"))
    if t in {"全网络", "合计", "总计"}:
        return t
    m = _LINE_RE.search(t)
    if m:
        return f"{int(m.group(1))}号线"
    if t.isdigit() and 1 <= int(t) <= 18:
        return f"{int(t)}号线"
    return t


def _letter(raw: str) -> str:
    t = str(raw or "").strip().upper().replace("类", "").replace("级", "")
    return t if t in {"A", "B", "C", "D"} else ""


def _sheet_title(text: str) -> str:
    t = str(text or "").strip()
    if t.startswith("工作表:"):
        return t.split(":", 1)[-1].strip()
    return ""


def _norm_sheet(name: str) -> str:
    return str(name or "").replace(" ", "").strip()


def _header_index(header: list[str], *needles: str) -> int | None:
    packed = [compact_text(h) for h in header]
    for needle in needles:
        key = compact_text(needle)
        for i, item in enumerate(packed):
            if key and key == item:
                return i
    for needle in needles:
        key = compact_text(needle)
        for i, item in enumerate(packed):
            if key and key in item:
                return i
    return None


def _grade_col(header: list[str]) -> int | None:
    i = _header_index(header, "评价", "系统状态等级")
    if i is not None:
        return i
    packed = [compact_text(h) for h in header]
    for i, h in enumerate(packed):
        if h.endswith("评价") or h.endswith("等级"):
            return i
    return None


def _canonical_header(count_label: str, unit: str = "锚段数") -> list[list[str]]:
    return [
        ["线路", count_label, "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", count_label, unit, "占比", unit, "占比", unit, "占比", unit, "占比"],
    ]


def _pct(n: int, total: int) -> str:
    if total <= 0:
        return "0.00%"
    return f"{n * 100 / total:.2f}%"


def _line_sort_key(line: str) -> tuple[int, str]:
    m = re.search(r"(\d{1,2})号线", line or "")
    if m:
        return (int(m.group(1)), line)
    if line == "全网络":
        return (99, line)
    return (98, line or "")


def counts_to_table(
    by_line: dict[str, Counter],
    *,
    count_label: str,
    line_labels: list[str] | None = None,
    add_network: bool = True,
    only_nonzero: bool = False,
    unit: str = "锚段数",
    skip_lines: set[str] | frozenset[str] | None = None,
) -> list[list[str]]:
    """按线路汇总 A/B/C/D 个数与占比。

    柔性/刚性：1～18 缺线填 0，17 号线（接触轨）不列；末行全网络。
    隔离开关/控制屏：1～18 缺线填 0，末行全网络。
    接触轨：只列有数据的线路，末行全网络。
    """
    rows = _canonical_header(count_label, unit=unit)
    if only_nonzero:
        labels = [
            ln
            for ln in sorted(by_line, key=_line_sort_key)
            if ln not in {"全网络", "合计", "总计"} and int(sum((by_line.get(ln) or Counter()).values())) > 0
        ]
    else:
        labels = list(line_labels) if line_labels is not None else canonical_line_labels()
        seen = set(labels)
        extra = [
            ln
            for ln in sorted(by_line, key=_line_sort_key)
            if ln not in seen and ln not in {"全网络", "合计", "总计"}
        ]
        skip = set(skip_lines or ())
        extra = [ln for ln in extra if ln not in skip]
        labels = [ln for ln in (labels + extra) if ln not in skip]
    totals: Counter = Counter()
    for line in labels:
        c = by_line.get(line) or Counter()
        n = int(sum(c.values()))
        a, b, cc, d = int(c["A"]), int(c["B"]), int(c["C"]), int(c["D"])
        rows.append(
            [
                line,
                str(n),
                str(a),
                _pct(a, n),
                str(b),
                _pct(b, n),
                str(cc),
                _pct(cc, n),
                str(d),
                _pct(d, n),
            ]
        )
        if n:
            totals.update(c)
    if add_network:
        tn = int(sum(totals.values()))
        rows.append(
            [
                "全网络",
                str(tn),
                str(totals["A"]),
                _pct(totals["A"], tn),
                str(totals["B"]),
                _pct(totals["B"], tn),
                str(totals["C"]),
                _pct(totals["C"], tn),
                str(totals["D"]),
                _pct(totals["D"], tn),
            ]
        )
    return rows


def _iter_workbook_tables(docs: list[DocumentModel] | None):
    for doc, idx in sort_docs_newest_last(docs or []):
        recency = doc_recency_key(doc, idx)[0]
        sheet = ""
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if block.type == "heading" and t.startswith("工作表:"):
                sheet = _sheet_title(t)
                continue
            if block.type != "table" or not block.rows:
                continue
            if not sheet:
                continue
            yield doc, sheet, [list(r) for r in block.rows], recency, idx


def _sample_has_letter_grades(rows: list[list[str]], grade_i: int, *, limit: int = 40) -> bool:
    if grade_i < 0:
        return False
    n = 0
    for raw in rows[1 : limit + 1]:
        vals = [str(c or "").strip() for c in raw]
        if grade_i < len(vals) and _letter(vals[grade_i]):
            n += 1
            if n >= 2:
                return True
    return n >= 1


def infer_sheet_kind(sheet: str, rows: list[list[str]] | None) -> str | None:
    """根据表头/样例行判断子表用途，不依赖文件名或固定工作表名。"""
    if not rows:
        return None
    header = [str(c or "").strip() for c in rows[0]]
    if _header_index(header, "线路") is None:
        return None
    blob = compact_text(sheet + "".join(header))
    if _header_index(header, "系统状态等级", "系统状态值S1", "系统状态值") is not None and (
        _header_index(header, "柔性接触网") is not None or _header_index(header, "刚性接触网") is not None
    ):
        return SYSTEM_KIND
    grade_i = _grade_col(header)
    if grade_i is None or not _sample_has_letter_grades(rows, grade_i):
        return None
    if any(k in blob for k in ("控制屏", "PLC", "控制柜")):
        return SHEET_TO_KIND["隔离开关控制屏"]
    if any(k in blob for k in ("三轨", "防护罩", "接触轨区间", "接触轨")):
        return SHEET_TO_KIND["三轨区间"]
    if any(k in blob for k in ("汇流排", "刚性定位", "刚柔过渡")):
        return SHEET_TO_KIND["刚性锚段"]
    if any(k in blob for k in ("承力索", "软横跨", "硬横跨", "柔性定位")):
        return SHEET_TO_KIND["柔性锚段"]
    if "隔离开关" in blob and "控制屏" not in blob:
        return SHEET_TO_KIND["隔离开关"]
    if "锚段号" in blob or "接触线磨耗" in blob:
        if "刚性" in blob:
            return SHEET_TO_KIND["刚性锚段"]
        if "柔性" in blob:
            return SHEET_TO_KIND["柔性锚段"]
    sheet_key = _norm_sheet(sheet)
    for name, kind in SHEET_TO_KIND.items():
        nk = _norm_sheet(name)
        if nk and (nk == sheet_key or nk in sheet_key or sheet_key in nk):
            return kind
    if _norm_sheet(SYSTEM_SHEET) in sheet_key:
        return SYSTEM_KIND
    return None


def detect_overhead_excel_capabilities(doc: DocumentModel | None) -> list[dict[str, Any]]:
    """扫描全部工作表表头，报告能支撑第 3/4 章哪些表。供分拣与抽取共用。"""
    if doc is None:
        return []
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for _doc, sheet, rows, _recency, _idx in _iter_workbook_tables([doc]):
        kind = infer_sheet_kind(sheet, rows)
        if not kind:
            continue
        key = (_norm_sheet(sheet), kind)
        if key in seen:
            continue
        seen.add(key)
        chapters = ["ch3"]
        if kind == SYSTEM_KIND:
            chapters.append("ch4")
        found.append(
            {
                "sheet": sheet.strip(),
                "kind": kind,
                "chapters": chapters,
                "reason": (
                    f"工作表「{sheet.strip()}」表头含线路+评价/系统等级，"
                    f"可汇总「{kind}」"
                ),
            }
        )
    return found


def overhead_ledger_sheet_keys(doc: DocumentModel | None) -> set[str]:
    """可被认定为触网台账的工作表名（去空白），供电抽取时整表跳过。"""
    return {_norm_sheet(str(item.get("sheet") or "")) for item in detect_overhead_excel_capabilities(doc)}


def _aggregate_sheet_rows(rows: list[list[str]]) -> dict[str, Counter]:
    if not rows:
        return {}
    header = [str(c or "").strip() for c in rows[0]]
    line_i = _header_index(header, "线路")
    grade_i = _grade_col(header)
    if line_i is None or grade_i is None:
        return {}
    by_line: dict[str, Counter] = defaultdict(Counter)
    for raw in rows[1:]:
        vals = [str(c or "").strip() for c in raw]
        line = _norm_line(vals[line_i] if line_i < len(vals) else "")
        g = _letter(vals[grade_i] if grade_i < len(vals) else "")
        if not line or line in {"线路", "全网络"} or not g:
            continue
        by_line[line][g] += 1
    return dict(by_line)


def extract_excel_status_tables(docs: list[DocumentModel] | None) -> dict[str, dict[str, Any]]:
    """每种状态表取较新工作簿；该子表无评价行时用较旧工作簿补。"""
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc, sheet, rows, recency, idx in _iter_workbook_tables(docs):
        kind = infer_sheet_kind(sheet, rows)
        if not kind or kind == SYSTEM_KIND:
            continue
        counts = _aggregate_sheet_rows(rows)
        n = sum(sum(c.values()) for c in counts.values())
        by_kind[kind].append(
            {
                "counts": counts,
                "n": n,
                "source": doc.source_name or "",
                "sheet": sheet.strip(),
                "rows": rows,
                "_recency": recency,
                "_idx": idx,
            }
        )

    out: dict[str, dict[str, Any]] = {}
    for kind, items in by_kind.items():
        ordered = sorted(items, key=lambda x: (x.get("_recency") or 0, x.get("_idx") or 0))
        chosen = None
        sources: list[str] = []
        for item in reversed(ordered):
            src = f"{item.get('source') or ''}（工作表：{item.get('sheet') or ''}）"
            if src not in sources:
                sources.append(src)
            if (item.get("n") or 0) > 0:
                chosen = item
                break
        if not chosen:
            continue
        label = KIND_COUNT_LABEL.get(kind) or "锚段数量"
        unit = KIND_COUNT_UNIT.get(kind) or "锚段数"
        table = counts_to_table(
            chosen["counts"],
            count_label=label,
            unit=unit,
            add_network=True,
            only_nonzero=(kind == RAIL_KIND),
            line_labels=None if kind == RAIL_KIND else line_labels_for_kind(kind),
            skip_lines=KIND_SKIP_LINES.get(kind),
        )
        if kind == RAIL_KIND:
            has_line = any(
                _norm_line(r[0] if r else "") not in {"", "线路", "全网络", "合计", "总计"}
                for r in table[2:]
            )
            if not has_line:
                continue
        out[kind] = {
            "table": table,
            "counts": chosen["counts"],
            "source": "；".join(sources),
            "sheet": chosen.get("sheet") or "",
            "caption": KIND_CAPTION.get(kind) or "",
            "raw_rows": chosen.get("rows") if kind == SYSTEM_KIND else None,
            "empty": len(table) <= 2,
        }
    return out


def extract_system_volume_table(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """表3-9 用的接触网系统子表（线路×区段评分 + 系统状态等级）。不进第 4 章。"""
    candidates: list[dict[str, Any]] = []
    for doc, sheet, rows, recency, idx in _iter_workbook_tables(docs):
        if infer_sheet_kind(sheet, rows) != SYSTEM_KIND:
            continue
        if not rows or len(rows) < 2:
            continue
        candidates.append(
            {
                "rows": rows,
                "source": doc.source_name or "",
                "sheet": sheet.strip(),
                "_recency": recency,
                "_idx": idx,
            }
        )
    if not candidates:
        return {"table": [], "flow": [], "source": "", "empty": True}
    best = max(candidates, key=lambda x: (x.get("_recency") or 0, x.get("_idx") or 0, len(x.get("rows") or [])))
    header = [str(c or "").strip() for c in best["rows"][0]]
    line_i = _header_index(header, "线路") or 0
    out_rows = [header]
    for raw in best["rows"][1:]:
        vals = [str(c or "").strip() for c in raw]
        if line_i < len(vals) and vals[line_i]:
            vals[line_i] = _norm_line(vals[line_i]) or vals[line_i]
        if not any(vals):
            continue
        out_rows.append(vals)
    src = f"{best.get('source') or ''}（工作表：{best.get('sheet') or SYSTEM_SHEET}）"
    return {
        "table": out_rows,
        "flow": [{"kind": "table", "rows": out_rows, "force_rebuild": True}],
        "source": src,
        "empty": len(out_rows) <= 1,
        "caption": SYSTEM_CAPTION,
    }


def _is_system_score_table(rows: list[list[str]] | None) -> bool:
    if not rows or len(rows) < 2:
        return False
    head = "".join(str(c or "") for r in rows[:2] for c in r)
    if "线路" not in head:
        return False
    if "系统状态" not in head:
        return False
    return "刚性接触网" in head or "柔性接触网" in head


def _fill_down_line_seg(rows: list[list[str]], line_i: int, seg_i: int | None) -> list[list[str]]:
    out: list[list[str]] = []
    last_line, last_seg = "", ""
    for raw in rows:
        vals = [str(c or "").strip() for c in raw]
        if line_i < len(vals) and vals[line_i]:
            last_line = _norm_line(vals[line_i]) or vals[line_i]
            vals[line_i] = last_line
        elif line_i < len(vals):
            vals[line_i] = last_line
        if seg_i is not None:
            if seg_i < len(vals) and vals[seg_i]:
                last_seg = vals[seg_i]
            elif seg_i < len(vals):
                vals[seg_i] = last_seg
        if any(vals):
            out.append(vals)
    return out


def _system_row_key(vals: list[str], line_i: int, seg_i: int | None) -> tuple[str, str]:
    line = _norm_line(vals[line_i] if line_i < len(vals) else "") or ""
    seg = str(vals[seg_i] if seg_i is not None and seg_i < len(vals) else "").strip()
    return (line, seg)


def _system_table_map(
    rows: list[list[str]],
    *,
    year: int | None = None,
) -> tuple[list[str], int, int | None, dict[tuple[str, str], list[str]]]:
    header = [str(c or "").strip() for c in rows[0]]
    line_i = _header_index(header, "线路") or 0
    seg_i = _header_index(header, "区段")
    time_i = _header_index(header, "时间", "年份")
    body = _fill_down_line_seg(rows[1:], line_i, seg_i)
    mapped: dict[tuple[str, str], list[str]] = {}
    for vals in body:
        if year is not None and time_i is not None and time_i < len(vals):
            ym = re.search(r"(20\d{2})", str(vals[time_i] or ""))
            if ym and ym.group(1) != str(year):
                continue
        key = _system_row_key(vals, line_i, seg_i)
        if not key[0] or key[0] in {"线路", "全网络", "合计", "总计"}:
            continue
        mapped[key] = vals
    return header, line_i, seg_i, mapped


def _years_in_table(rows: list[list[str]], year: int) -> set[str]:
    found: set[str] = set()
    header = [str(c or "").strip() for c in rows[0]]
    time_i = _header_index(header, "时间", "年份")
    if time_i is not None:
        for r in rows[1:]:
            if time_i < len(r):
                m = re.search(r"(20\d{2})", str(r[time_i] or ""))
                if m:
                    found.add(m.group(1))
    blob = " ".join(str(c or "") for r in rows[:12] for c in r)
    found.update(re.findall(r"20\d{2}", blob))
    return found


def extract_year_compare_table(
    docs: list[DocumentModel] | None,
    *,
    year: int,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """3.5：优先用当年材料里带「时间」列的两年对照表；否则用当年系统表 + 去年报告同表对照。"""
    best: dict[str, Any] | None = None
    for doc, idx in sort_docs_newest_last(docs or []):
        recency = doc_recency_key(doc, idx)[0]
        for block in doc.blocks or []:
            if block.type != "table" or not _is_system_score_table(block.rows):
                continue
            head = "".join(str(c or "") for r in block.rows[:2] for c in r)
            years = _years_in_table(block.rows, year)
            has_time = "时间" in head or "年份" in head
            if has_time and str(year) in years and str(year - 1) in years:
                score = (2, recency, idx, len(block.rows))
            elif has_time:
                score = (1, recency, idx, len(block.rows))
            else:
                continue
            if best is None or score > best["_score"]:
                best = {
                    "table": [[str(c or "").strip() for c in r] for r in block.rows],
                    "source": doc.source_name or "",
                    "doc": doc,
                    "block": block,
                    "_score": score,
                }
    if best and best["_score"][0] >= 2:
        cap = f"表3-10 {year}年对比{year - 1}年接触网系统评估结果"
        return {
            "table": best["table"],
            "flow": [
                {"kind": "para", "text": cap},
                {"kind": "table", "rows": best["table"], "force_rebuild": True},
            ],
            "source": best["source"],
            "empty": False,
            "caption": cap,
        }
    built = _build_year_compare_from_system(docs, prior_docs, year)
    if built and not built.get("empty"):
        return built
    return {"table": [], "flow": [], "source": "", "empty": True, "caption": ""}


def _pick_system_score_rows(docs: list[DocumentModel] | None) -> tuple[list[list[str]], str]:
    excel = extract_system_volume_table(docs)
    if excel and not excel.get("empty") and excel.get("table"):
        return list(excel["table"]), str(excel.get("source") or "")
    best: tuple[tuple[int, int, int], list[list[str]], str] | None = None
    for doc, idx in sort_docs_newest_last(docs or []):
        recency = int(doc_recency_key(doc, idx)[0])
        for block in doc.blocks or []:
            if block.type != "table" or not _is_system_score_table(block.rows):
                continue
            rows = [[str(c or "").strip() for c in r] for r in block.rows]
            score = (recency, idx, len(rows))
            if best is None or score > best[0]:
                best = (score, rows, doc.source_name or "")
    if not best:
        return [], ""
    return best[1], best[2]


def _build_year_compare_from_system(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None,
    year: int,
) -> dict[str, Any]:
    """当年接触网系统表 + 去年同结构表，按线路/区段做成带「时间」列的对照表。不编数字。"""
    now_rows, now_src = _pick_system_score_rows(docs)
    prior_rows, prior_src = _pick_system_score_rows(prior_docs)
    if not now_rows:
        return {"table": [], "flow": [], "source": "", "empty": True, "caption": ""}
    now_head, line_i, seg_i, now_map = _system_table_map(now_rows, year=year)
    prior_map: dict[tuple[str, str], list[str]] = {}
    prior_head: list[str] = []
    p_line_i, p_seg_i = line_i, seg_i
    if prior_rows:
        prior_head, p_line_i, p_seg_i, prior_map = _system_table_map(prior_rows, year=year - 1)

    def col_of(header: list[str], *names: str) -> int | None:
        return _header_index(header, *names)

    value_names = (
        ("刚性接触网",),
        ("柔性接触网",),
        ("接触轨",),
        ("隔离开关",),
        ("隔离开关控制屏", "控制屏"),
        ("系统状态值S1", "系统状态值"),
        ("系统状态等级",),
    )
    out_head = ["线路", "区段", "时间"]
    now_cols: list[int | None] = []
    prior_cols: list[int | None] = []
    prior_has_screen = bool(prior_head and col_of(prior_head, "隔离开关控制屏", "控制屏") is not None)
    for names in value_names:
        ni = col_of(now_head, *names)
        if names[0] in {"隔离开关控制屏", "控制屏"}:
            if prior_head and not prior_has_screen:
                continue
            if ni is None:
                continue
        out_head.append(names[0])
        now_cols.append(ni)
        prior_cols.append(col_of(prior_head, *names) if prior_head else None)

    keys = list(now_map.keys())
    if prior_map:
        extra = [k for k in prior_map if k not in now_map]
        keys.extend(extra)

    def _k_sort(item: tuple[str, str]) -> tuple[int, str, str]:
        m = _LINE_RE.search(item[0] or "")
        n = int(m.group(1)) if m else 99
        return (n, item[0], item[1])

    out = [out_head]
    for key in sorted(keys, key=_k_sort):
        line, seg = key
        now_vals = now_map.get(key)
        prior_vals = prior_map.get(key)
        if prior_vals and prior_cols:
            prow = [line, seg, str(year - 1)]
            for ci in prior_cols:
                val = prior_vals[ci] if ci is not None and ci < len(prior_vals) else "/"
                prow.append(val.strip() or "/")
            out.append(prow)
        if now_vals:
            nrow = [line, seg, str(year)]
            for ci in now_cols:
                val = now_vals[ci] if ci is not None and ci < len(now_vals) else "/"
                nrow.append(val.strip() or "/")
            out.append(nrow)
    if len(out) <= 1:
        return {"table": [], "flow": [], "source": "", "empty": True, "caption": ""}
    cap = f"表3-10 {year}年对比{year - 1}年接触网系统评估结果"
    sources = [s for s in (now_src, prior_src) if s]
    return {
        "table": out,
        "flow": [
            {"kind": "para", "text": cap},
            {"kind": "table", "rows": out, "force_rebuild": True},
        ],
        "source": "；".join(sources),
        "empty": False,
        "caption": cap,
    }


def align_system_table_to_prior(
    rows: list[list[str]] | None,
    prior_docs: list[DocumentModel] | None,
) -> list[list[str]]:
    """表3-9 列随去年同表：去年没有「隔离开关控制屏」就不要多出一列。"""
    rows = [list(r) for r in (rows or [])]
    if not rows:
        return rows
    prior_rows, _ = _pick_system_score_rows(prior_docs)
    if not prior_rows:
        return rows
    now_head = [str(c or "").strip() for c in rows[0]]
    prior_head = [compact_text(c) for c in prior_rows[0]]
    keep: list[int] = []
    for i, name in enumerate(now_head):
        n = compact_text(name)
        if n in {"线路", "区段"}:
            keep.append(i)
            continue
        if n in {"时间", "年份"}:
            continue
        if n in prior_head:
            keep.append(i)
    if len(keep) < 4:
        return rows
    return [[(r[i] if i < len(r) else "") for i in keep] for r in rows]


def _word_line_counts(table_rows: list[list[str]] | None) -> dict[str, list[str]]:
    from chapters.overhead.ch3_status import _table_header_rows, _norm_line as _nl

    if not table_rows:
        return {}
    _, start = _table_header_rows(table_rows)
    out: dict[str, list[str]] = {}
    for row in table_rows[start:]:
        line = _nl(row[0] if row else "")
        if not line or line in {"线路", "全网络", "合计", "总计"}:
            continue
        out[line] = [str(c or "").strip() for c in row]
    return out


def compare_and_backfill(
    excel_table: list[list[str]],
    word_table: list[list[str]] | None,
    *,
    excel_source: str,
    word_source: str,
    backfill_from_word: bool = False,
) -> tuple[list[list[str]], list[str]]:
    """以 Excel 汇总为主。缺线保持 0，不拿 Word 数字顶；不一致只记说明供网页展示。"""
    warnings: list[str] = []
    if not excel_table:
        return list(word_table or []), warnings
    from chapters.overhead.ch3_status import _table_header_rows

    header, start = _table_header_rows(excel_table)
    excel_by: dict[str, list[str]] = {}
    for row in excel_table[start:]:
        line = _norm_line(row[0] if row else "")
        if line == "全网络":
            continue
        if line:
            excel_by[line] = [str(c or "").strip() for c in row]
    word_by = _word_line_counts(word_table)
    for line, wrow in word_by.items():
        if row_all_zero_or_empty(wrow):
            continue
        erow = excel_by.get(line)
        if erow is None:
            if backfill_from_word:
                extra = [
                    ln
                    for ln, wr in word_by.items()
                    if ln not in {"全网络", "合计", "总计", "线路"} and not row_all_zero_or_empty(wr)
                ]
                # 接触轨只补「Word 本身也只有少数线路」时的缺行；1～18 全表不往 Excel 上叠。
                if len(extra) <= 4 or line in {"16号线", "17号线"}:
                    if line in extra:
                        excel_by[line] = wrow
                        warnings.append(
                            f"{line}在 Excel（{excel_source}）中无评价行，已用 Word「{word_source}」补入"
                        )
            continue
        e_n = erow[1] if len(erow) > 1 else ""
        w_n = wrow[1] if len(wrow) > 1 else ""
        if str(e_n).strip() in {"", "0"} and str(w_n).strip() in {"", "0"}:
            continue
        e_sig = "|".join(erow[1:3])
        w_sig = "|".join(wrow[1:3])
        if e_n != w_n or e_sig != w_sig:
            warnings.append(
                f"{line}状态表不一致：Excel {e_n}（A列{erow[2] if len(erow)>2 else ''}）"
                f" / Word「{word_source}」{w_n}（A列{wrow[2] if len(wrow)>2 else ''}），已采用 Excel 汇总"
            )
    if not backfill_from_word:
        return [list(r) for r in excel_table], warnings
    out = [list(r) for r in header]
    for line in sorted(excel_by, key=_line_sort_key):
        out.append(excel_by[line])
    return rebuild_status_network_row(out), warnings


def keep_present_status_lines(table: list[list[str]] | None) -> list[list[str]]:
    """接触轨：只保留有数量的线路，再按行合计全网络。"""
    if not table:
        return []
    from chapters.overhead.ch3_status import _table_header_rows

    header, start = _table_header_rows(table)
    data: list[list[str]] = []
    for row in table[start:]:
        line = _norm_line(row[0] if row else "")
        if not line or line in {"线路", "全网络", "合计", "总计"}:
            continue
        cells = [str(c or "").strip() for c in row]
        if row_all_zero_or_empty(cells):
            continue
        data.append(cells)
    return rebuild_status_network_row([list(r) for r in header] + data)


def rebuild_status_network_row(table: list[list[str]] | None) -> list[list[str]]:
    """用各线路锚段/区段数重算全网络，不抄 Word 合计。"""
    if not table:
        return []
    from chapters.overhead.ch3_status import _table_header_rows

    header, start = _table_header_rows(table)
    data: list[list[str]] = []
    totals: Counter = Counter()
    for row in table[start:]:
        line = _norm_line(row[0] if row else "")
        if not line or line in {"线路", "全网络", "合计", "总计"}:
            continue
        cells = [str(c or "").strip() for c in row]
        data.append(cells)
        try:
            totals["n"] += int(float(re.sub(r"[^\d.\-]", "", cells[1] or "0") or 0))
        except ValueError:
            pass
        for letter, idx in (("A", 2), ("B", 4), ("C", 6), ("D", 8)):
            if idx >= len(cells):
                continue
            try:
                totals[letter] += int(float(re.sub(r"[^\d.\-]", "", cells[idx] or "0") or 0))
            except ValueError:
                pass
    tn = int(totals["n"])
    data.append(
        [
            "全网络",
            str(tn),
            str(int(totals["A"])),
            _pct(int(totals["A"]), tn),
            str(int(totals["B"])),
            _pct(int(totals["B"]), tn),
            str(int(totals["C"])),
            _pct(int(totals["C"]), tn),
            str(int(totals["D"])),
            _pct(int(totals["D"]), tn),
        ]
    )
    return [list(r) for r in header] + data
