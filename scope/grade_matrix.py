# -*- coding: utf-8 -*-
"""设备评估结果总表：按大类 + 线路 + 区段去重后的 A～D 等级行。不是逐台抽检明细。

多份总表时优先文件名带 _1 的 xlsx。GRADE_COLUMNS 含接触网列，抽取时一律读入；
是否计入由调用方决定：第 3 章 POWER_COLS 不含接触网，第 4 章 count_grade_cells 含接触网列。
"""
from __future__ import annotations

from typing import Any

from parsers.document_model import DocumentModel
from scope.names import normalize_line, normalize_segment

# 总表常见列（不含能耗、配电设备、接触网）。子系统列映射仍以这份为准。
RESULT_TABLE_HEADERS = [
    "线路",
    "区段",
    "应急电源设备",
    "配电系统（降压）",
    "配电系统（牵引）",
    "变压器设备",
    "电力电缆设备",
    "电力监控设备",
    "杂散电流设备",
]
RESULT_COLUMN_MAP = {
    # 子系统 id → 总表列名。配电供电看降压+牵引两列，主变电配电只看降压列。
    "emergency_power": ["应急电源设备"],
    "ms_emergency_power": ["应急电源设备"],
    "distribution": ["配电系统（降压）", "配电系统（牵引）"],
    "ms_distribution": ["配电系统（降压）"],
    "transformer": ["变压器设备"],
    "ms_transformer": ["变压器设备"],
    "power_cable": ["电力电缆设备"],
    "ms_cable": ["电力电缆设备"],
    "power_monitoring": ["电力监控设备"],
    "ms_monitoring": ["电力监控设备"],
    "stray_current": ["杂散电流设备"],
}

MISSING = {"", "/", "-", "—", "–", "无", "\\", "nan", "none", "null"}
# 总表里可能出现的等级列（含接触网）。识别表头和抽行都用这份；计入哪几列由调用方裁。
GRADE_COLUMNS = [
    *RESULT_TABLE_HEADERS[2:],
    "能耗设备",
    "配电设备",
    "接触网（轨）设备",
]
SUBSYSTEM_GRADE_COLS = {
    # 各子系统计分列；空列表表示总表无对应列（生产辅助）。接触网列不在此映射里。
    **{key: list(cols) for key, cols in RESULT_COLUMN_MAP.items()},
    "energy": ["能耗设备"],
    "ms_aux": [],
    "production_aux": [],
}


def _norm(text: str) -> str:
    """表头比对用：去掉换行和空格。"""
    return str(text or "").replace("\n", "").replace(" ", "").strip()


def _col(header: list[str], *needles: str) -> int | None:
    """在表头里找列下标；needle 去空白后做包含匹配。"""
    packed = [_norm(h) for h in header]
    for needle in needles:
        key = _norm(needle)
        for i, item in enumerate(packed):
            if key and key in item:
                return i
    return None


def _cell(values: list[str], index: int | None) -> str:
    """按列下标取单元格；缺列返回空串。"""
    if index is None or index < 0 or index >= len(values):
        return ""
    return str(values[index] or "").strip()


def _letter(raw: str) -> str | None:
    """只认 A～D（可带「类」「级」）；空占位符不当作成绩。"""
    text = str(raw or "").strip().upper().replace("类", "").replace("级", "")
    if text.lower() in MISSING:
        return None
    if text in {"A", "B", "C", "D"}:
        return text
    return None


def is_grade_header(header: list[str]) -> bool:
    """总表表头：须有线路、区段，且 GRADE_COLUMNS 至少命中 4 列（含接触网列也算）。"""
    if _col(header, "线路") is None or _col(header, "区段") is None:
        return False
    packed = [_norm(h) for h in header]
    hits = 0
    for col in GRADE_COLUMNS:
        key = _norm(col)
        if any(key and (key in item or item in key) for item in packed if item):
            hits += 1
    return hits >= 4


def table_has_letter_grades(header: list[str], rows: list[list[str]] | None) -> bool:
    """正文等级列里至少出现过一次 A～D。空表、全 / 的模板不当总表。"""
    col_index = [i for i in (_col(header, name) for name in GRADE_COLUMNS) if i is not None]
    if not col_index:
        return False
    for raw in (rows or [])[1:]:
        values = [str(c) if c is not None else "" for c in raw]
        for index in col_index:
            if _letter(_cell(values, index)):
                return True
    return False


def is_grade_matrix(header: list[str], rows: list[list[str]] | None = None) -> bool:
    """是否设备评估结果总表：表头对上，且（若给了整表）正文要有 A～D 评级。"""
    if not is_grade_header(header):
        return False
    if rows is None:
        return True
    return table_has_letter_grades(header, rows)


def _grade_doc_rank(doc: DocumentModel) -> tuple[int, int, str]:
    """越小越优先：文件名含 _1 的总表先读，后面相同「大类+线路+区段」不再写入。"""
    name = doc.source_name or ""
    n_tables = sum(
        1
        for b in doc.blocks
        if b.type == "table" and b.rows and is_grade_matrix([str(c) for c in b.rows[0]], b.rows)
    )
    prefer = 0 if "_1" in name else 1
    return (prefer, -n_tables, name)


def extract_grade_matrix(docs: list[DocumentModel] | None) -> list[dict[str, Any]]:
    """抽出总表行。键为 (大类, 线路, 区段)，先出现的留下；文档顺序已按 _1 优先排。

    评估列全是 / 的行仍保留，供 3.3.2 原样写出；摘要/点数只认 A～D，不会把 / 算进项或台。
    """
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    ordered = sorted((d for d in docs or []), key=_grade_doc_rank)
    for doc in ordered:
        source = doc.source_name or "评估材料"
        for block in doc.blocks:
            if block.type != "table" or not block.rows:
                continue
            header = [str(c) for c in block.rows[0]]
            if not is_grade_matrix(header, block.rows):
                continue
            cat_i = _col(header, "大类")
            line_i = _col(header, "线路")
            seg_i = _col(header, "区段")
            col_index = {name: _col(header, name) for name in GRADE_COLUMNS}
            for raw in block.rows[1:]:
                values = [str(c) if c is not None else "" for c in raw]
                line_id = normalize_line(_cell(values, line_i))
                if not line_id:
                    continue
                grades = {
                    name: _letter(_cell(values, index))
                    for name, index in col_index.items()
                    if index is not None
                }
                grades = {k: v for k, v in grades.items() if v}
                # 等级全是 / 的行也要留下（3.3.2 原样写出 /）；没有线路才跳过。
                # 同一大类+线路+区段只留先读到的一行（_1 文件已排在前面）。
                key = (_cell(values, cat_i) or "供电", line_id, normalize_segment(_cell(values, seg_i)))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "category": _cell(values, cat_i) or "供电",
                        "line_id": line_id,
                        "segment": normalize_segment(_cell(values, seg_i)),
                        "grades": grades,
                        "source_note": source,
                    }
                )
    return rows


def filter_matrix_domain(rows: list[dict[str, Any]], domain_id: str, subsystem_id: str = "") -> list[dict[str, Any]]:
    """按大类筛行：能耗看「能源系统」，主变电看主变电所，其余看「供电」。"""
    if subsystem_id == "energy":
        wanted = {"能源系统"}
    elif domain_id == "main_substation":
        wanted = {"主变电所", "主变电"}
    else:
        wanted = {"供电"}
    return [row for row in rows if (row.get("category") or "供电") in wanted]


def summaries_from_matrix(
    rows: list[dict[str, Any]],
    subsystem_id: str,
    domain_id: str = "power_supply",
) -> list[dict[str, Any]]:
    """把总表行收成某子系统的线路摘要。等级取该子系统列里最差的一档（A<B<C<D 取 max）。"""
    cols = list(SUBSYSTEM_GRADE_COLS.get(subsystem_id) or [])
    if not cols:
        return []
    out: list[dict[str, Any]] = []
    for row in filter_matrix_domain(rows, domain_id, subsystem_id):
        grades = row.get("grades") or {}
        letters = [grades[name] for name in cols if grades.get(name)]
        if not letters:
            continue
        rank = lambda g: "ABCD".find(g) if g in "ABCD" else -1
        grade = max(letters, key=rank)
        out.append(
            {
                "line_id": row.get("line_id"),
                "segment": row.get("segment"),
                "type_scores": {name: grades.get(name) for name in cols},
                "s1": None,
                "grade": grade,
                "source_note": row.get("source_note") or "设备评估结果总表",
                "score_source": "grade_table",
            }
        )
    return out


def merge_summary_lists(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """按线路+区段合并两份摘要。primary 覆盖 secondary（后写入为准）。"""
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in secondary + primary:
        key = (row.get("line_id") or "", row.get("segment") or "")
        buckets[key] = row
    return list(buckets.values())
