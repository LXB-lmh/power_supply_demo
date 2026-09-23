# -*- coding: utf-8 -*-
"""供电第四章抽取：总表台数、维护周期表、各线故障原文。

4.1.2 供电系统按总表该大类全部 A～D 格计数（含接触网列）→ 当年是 343 台。
第 3 章 3.3.2 用 POWER_COLS 去掉接触网列，大约是 300 项 / 三系统 477 项，不要拿来对 4.1.2。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from chapters.ch4.power_style import CYCLE_TABLE
from chapters.common.section_slice import (
    compact_text,
    hits_section_key,
    is_chapter_or_appendix_title,
    is_foreign_outline,
    is_outline_title_line,
    outline_num,
    slice_named_section,
)
from chapters.common.source_yellow import para_flow_item
from parsers.document_model import DocumentModel
from scope.grade_matrix import extract_grade_matrix

LINE_HEAD = re.compile(r"^(\d+号线)\s*[：:.．]?\s*$")
LINE_INLINE = re.compile(r"^(\d+号线)\s*[：:.．]\s*(.+)$")

# 兼容旧测试名
_outline_num = outline_num
_hits_section_key = hits_section_key
_is_outline_title_line = is_outline_title_line


def _line_title(text: str) -> tuple[str | None, str]:
    """识别「N号线」独立成行或「N号线：正文」。4.3 靠这个切段，不要把「各个线路基本情况」当成线路。"""
    t = (text or "").strip()
    m = LINE_HEAD.match(t)
    if m:
        return m.group(1), ""
    m = LINE_INLINE.match(t)
    if m:
        return m.group(1), m.group(2).strip()
    return None, t


def _is_other_section(block_type: str, text: str) -> bool:
    """4.3 在「运营延长」「计划部」或其它大纲标题处停切，避免把 4.4 等粘进某号线。"""
    t = (text or "").strip()
    compact = compact_text(t)
    if t.startswith("各个线路基本情况"):
        return True
    if t.startswith("运营延长") or t.startswith("计划部"):
        return True
    line, _ = _line_title(t)
    if line:
        return False
    # paragraph 伪标题也停（如「4.4 各线路…」）
    if hits_section_key(
        compact,
        ("4.4", "4.5", "年度生产指标", "各线路供电系统年度生产", "评估小结", "第5章", "第五章"),
        title_only_words=True,
    ):
        return True
    if is_foreign_outline(compact, keep_keys=("4.3",)):
        # 仅停「4.x / 5.x…」大纲标题，不把正文短句当边界
        if is_outline_title_line(compact) or is_chapter_or_appendix_title(compact):
            return True
    return block_type == "heading"


def repair_fault_text(text: str, line: str | None, year: int) -> str:
    """排版掉字：段首「号线」补回路名；「026年」补成评估年。只修明显截断，不改写故障内容。"""
    t = (text or "").strip()
    if not t:
        return t
    if line and t.startswith("号线"):
        num = re.match(r"(\d+)号线", line)
        if num:
            t = f"{num.group(1)}{t}"
    t = re.sub(r"(?<!\d)026年", f"{year}年", t)
    return t


def _fault_doc_score(doc: DocumentModel) -> int:
    """选故障稿：文件名带「故障情况」优先；PDF 和隐患/库存/退运等不要当成 4.3 来源。"""
    name = doc.source_name or ""
    if "故障情况" in name:
        return 100
    if (doc.suffix or "").lower() == ".pdf":
        return -1
    if any(key in name for key in ("隐患", "库存", "退运", "报废", "合规", "备件")):
        return -1
    texts = [(block.text or "") for block in doc.blocks]
    if any("各个线路基本情况" in t for t in texts):
        return 80
    n = sum(1 for t in texts if LINE_HEAD.match(t.strip()) or LINE_INLINE.match(t.strip()))
    return n if n >= 10 else 0


def split_fault_lines(
    docs: list[DocumentModel], *, year: int = 2026
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """4.3：按「N号线」切开故障原文，图和表跟在当前线路下。遇到「运营延长」「计划部」等非线路标题就停。"""
    by: dict[str, list[dict[str, Any]]] = {}
    source = ""
    ranked = sorted(((_fault_doc_score(doc), doc) for doc in docs or []), key=lambda x: -x[0])
    # 4.3 只取一份故障稿，避免把线路报告或别的 Word 再切一遍造成重复号线。
    chosen = [doc for score, doc in ranked if score > 0][:1]
    for doc in chosen:
        blocks = [
            block
            for block in doc.blocks
            if block.type in {"heading", "paragraph", "drawing", "formula", "table"}
            and (
                (block.text or "").strip()
                or block.type in {"drawing", "formula"}
                or (block.type == "table" and block.rows)
            )
        ]
        if not any("号线" in (block.text or "") for block in blocks):
            continue
        source = doc.source_name or source
        cur = None
        for block in blocks:
            if block.type == "formula":
                if cur:
                    by.setdefault(cur, []).append(
                        {
                            "kind": "formula",
                            "source_path": doc.source_path,
                            "source_index": block.source_index,
                            "text": (block.text or "").strip(),
                        }
                    )
                continue
            if block.type == "drawing":
                if cur:
                    by.setdefault(cur, []).append(
                        {
                            "kind": "drawing",
                            "source_path": doc.source_path,
                            "source_index": block.source_index,
                        }
                    )
                continue
            if block.type == "table":
                if cur:
                    by.setdefault(cur, []).append({"kind": "table", "rows": [list(r) for r in (block.rows or [])]})
                continue
            t = block.text.strip()
            if _is_other_section(block.type, t):
                cur = None
                continue
            line, rest = _line_title(t)
            if line:
                cur = line
                by.setdefault(cur, [])
                if rest:
                    by[cur].append({"kind": "text", "text": repair_fault_text(rest, cur, year)})
                continue
            if cur:
                by[cur].append({"kind": "text", "text": repair_fault_text(t, cur, year)})
    return by, source


def pick_plan_sentence(docs: list[DocumentModel]) -> str:
    """4.1.2 附句：材料里现成的「实际完成工作量」句。没有整句就返回空，避免写出「此外，根据生产计划工作表，。」半截。"""
    for doc in docs or []:
        for block in doc.blocks:
            if block.type not in {"heading", "paragraph"}:
                continue
            t = (block.text or "").strip()
            if "实际完成工作量" in t and "号线" in t:
                return t
            if t.startswith("此外，根据生产计划工作表") and "实际完成" in t:
                return t
    return ""


def _slice_named_ch4(
    docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
) -> tuple[list[dict[str, Any]], str]:
    """按小节名从材料/去年报告切一段（对照去年目录体例）。"""
    hit = slice_named_section(
        docs,
        start_keys=start_keys,
        stop_keys=stop_keys,
    )
    return hit.get("flow") or [], hit.get("source") or ""


def resolve_scope_411(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """4.1.1 设备体量：今年材料有则用；否则复用去年报告同节；都没有则空（成文黄标题）。"""
    stop = ("4.1.2", "设备体量变化", "维护周期", "4.2", "4.3", "4.4", "各个线路", "年度生产指标")
    start = ("4.1.1", "设备体量")
    for source_docs, via in ((docs, "year"), (prior_docs, "prior")):
        for doc in source_docs or []:
            take = False
            flow: list[dict[str, Any]] = []
            for block in doc.blocks or []:
                t = (block.text or "").strip()
                compact = compact_text(t)
                if not take:
                    # 认 4.1.1 / 「设备体量」标题，排除「设备体量变化」
                    if "体量变化" in compact:
                        continue
                    if hits_section_key(compact, start) or compact in {"设备体量", "4.1设备体量"} or (
                        compact.endswith("设备体量") and len(compact) < 24
                    ):
                        take = True
                    continue
                if block.type in {"heading", "paragraph"} and compact:
                    if hits_section_key(compact, stop) or "体量变化" in compact:
                        break
                    if is_outline_title_line(compact):
                        break
                if block.type == "table" and block.rows:
                    flow.append({"kind": "table", "rows": [list(r) for r in block.rows]})
                    continue
                if t:
                    flow.append(para_flow_item(t, block))
            paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
            if any(len(p) > 20 for p in paras) or any(x.get("kind") == "table" for x in flow):
                return {
                    "scope_flow": flow,
                    "scope_paras": paras,
                    "scope_source": doc.source_name or "",
                    "scope_via": via,
                }
    return {"scope_flow": [], "scope_paras": [], "scope_source": "", "scope_via": ""}


_VOLUME_CHANGE_LEAK = re.compile(
    r"^(?:4\.[2345]|设备维护周期|各个线路基本情况|各线路供电系统年度生产|年度生产指标|评估小结)"
)


def _is_volume_change_body(text: str) -> bool:
    """4.1.2 正文：丢掉总表句、其它节标题、以及误吸的 4.4 说明段。"""
    t = (text or "").strip()
    if not t:
        return False
    if re.match(r"^供电系统评估设备\d+台", t):
        return False
    compact = re.sub(r"\s+", "", t)
    if _VOLUME_CHANGE_LEAK.match(compact):
        return False
    if _is_outline_title_line(compact) and _outline_num(compact) not in {None, "4.1.2"}:
        return False
    # 误吸的指标说明（变电所系统涵盖…）不属于体量变化
    if re.match(r"^(变电所|牵引网|电力监控|应急电源|直流开关)系统涵盖", compact):
        return False
    if "可靠性指标" in compact or "MTBF指标" in compact or "MCBF指标" in compact:
        return False
    return True


def pick_volume_change_paras(docs: list[DocumentModel] | None) -> tuple[list[str], str]:
    """4.1.2 补充：材料里明确写的体量变化段（因…新增/减少…）。

    优先切「4.1.2 / 设备体量变化」小节；否则收含新增/减少+台数的说明段。
    材料若 4.1.2 后直接跳 4.4，必须在 4.4 处停，不能把生产指标灌进本节。
    """
    # 1) 按小节名切
    flow, src = _slice_named_ch4(
        docs,
        start_keys=("4.1.2", "4.1.2设备体量变化", "设备体量变化情况", "设备体量变化"),
        stop_keys=(
            "4.2",
            "4.3",
            "4.4",
            "4.5",
            "维护周期",
            "各个线路",
            "各线路供电系统年度生产指标",
            "年度生产指标",
            "评估小结",
        ),
    )
    paras = [
        str(x.get("text") or "").strip()
        for x in flow
        if x.get("kind") == "para" and _is_volume_change_body(str(x.get("text") or ""))
    ]
    if paras:
        return paras, src

    # 2) 散落段落：因…新增/减少
    out: list[str] = []
    source = ""
    for doc in docs or []:
        for block in doc.blocks or []:
            if block.type not in {"heading", "paragraph"}:
                continue
            t = (block.text or "").strip()
            if len(t) < 20 or not _is_volume_change_body(t):
                continue
            if re.search(r"(因.+?(新增|减少)|新线接管|设备报废|更新改造)", t) and re.search(
                r"(变压器|电力电缆|配电系统|应急电源|杂散电流|电力监控|接触网|主变电)", t
            ):
                if t not in out:
                    out.append(t)
                    source = source or (doc.source_name or "")
    return out, source


def count_grade_cells(matrix: list[dict[str, Any]]) -> dict[str, Counter]:
    """按大类点数总表里每一个 A～D 格。供电大类含接触网列，这是 4.1.2「343 台」的来源。"""
    by_cat: dict[str, Counter] = defaultdict(Counter)
    for row in matrix or []:
        cat = str(row.get("category") or "").strip() or "供电"
        for letter in (row.get("grades") or {}).values():
            if letter in {"A", "B", "C", "D"}:
                by_cat[cat][letter] += 1
    return by_cat


def volume_sentence(counts: dict[str, Counter]) -> str:
    """4.1.2 体量句：单位「台」，供电/主变/能源分述后再给总计。列口径含接触网，与 3.3.2「项」不同。"""
    def piece(label: str, cat: str) -> str | None:
        c = counts.get(cat)
        if not c:
            return None
        total = c["A"] + c["B"] + c["C"] + c["D"]
        return (
            f"{label}评估设备{total}台，其中A级{c['A']}台、B级{c['B']}台、"
            f"C级{c['C']}台、D级{c['D']}台"
        )

    parts = [
        piece("供电系统", "供电"),
        piece("主变电所系统", "主变电所") or piece("主变电所系统", "主变电"),
        piece("能源系统", "能源系统"),
    ]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    # 总计只加供电/主变/能源，且供电格已含接触网列（343 台那一档）。
    grand = 0
    for cat, c in counts.items():
        if cat in {"供电", "主变电所", "主变电", "能源系统"}:
            grand += c["A"] + c["B"] + c["C"] + c["D"]
    text = "；".join(parts) + "。"
    if grand:
        text += f"所有系统评估设备总计{grand}台。"
    return text


def _cycle_header_ok(row: list[str]) -> bool:
    """与去年年报 4.2 同结构：工作项目 / 维护周期 / 维护内容。带「大类」的触网表不要。"""
    cells = [str(c or "").strip() for c in (row or []) if str(c or "").strip()]
    if not cells:
        return False
    blob = "".join(cells)
    if "大类" in blob:
        return False
    return "工作项目" in blob and "维护周期" in blob and "维护内容" in blob


def _pick_cycle_from_docs(docs: list[DocumentModel] | None) -> tuple[list[list[str]], str]:
    for doc in docs or []:
        for block in doc.blocks:
            if block.type != "table" or not block.rows:
                continue
            if not _cycle_header_ok(block.rows[0]):
                continue
            rows = [list(r) for r in block.rows if any(str(x).strip() for x in r)]
            if len(rows) >= 2:
                return rows, doc.source_name or ""
    return [], ""


def _pick_cycle_from_prior(prior_docs: list[DocumentModel] | None) -> tuple[list[list[str]], str]:
    """从去年完整报告「设备维护周期和维护内容」小节抽同结构表。"""
    for doc in prior_docs or []:
        take = False
        for block in doc.blocks:
            t = (block.text or "").strip()
            if "设备维护周期和维护内容" in t or (t.endswith("维护周期和维护内容") and len(t) < 40):
                take = True
                continue
            if take and block.type in {"heading", "paragraph"}:
                compact = re.sub(r"\s+", "", t)
                if compact.startswith(("4.3", "4.4", "各个线路", "各线路供电系统年度生产")):
                    break
                if block.type == "heading" and "维护周期" not in t and len(t) < 40:
                    break
            if take and block.type == "table" and block.rows and _cycle_header_ok(block.rows[0]):
                rows = [list(r) for r in block.rows if any(str(x).strip() for x in r)]
                if len(rows) >= 2:
                    return rows, doc.source_name or ""
    return [], ""


def pick_cycle_table(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> tuple[list[list[str]], str]:
    """4.2：今年材料有与去年同表头的表就原样用；否则复用去年报告同节表；再没有才用体例 CYCLE_TABLE。"""
    rows, src = _pick_cycle_from_docs(docs)
    if rows:
        return rows, src
    rows, src = _pick_cycle_from_prior(prior_docs)
    if rows:
        return rows, src
    return [list(r) for r in CYCLE_TABLE], ""


def _mtbf_table_head(row: list[str]) -> bool:
    head = "".join(str(c or "") for c in (row or []))
    return ("指标名称" in head and "MTBF" in head) or (
        "指标名称" in head and "当月值" in head
    ) or ("指标名称" in head and "指标单位" in head)


def _slice_mtbf_flow(doc: DocumentModel) -> list[dict[str, Any]]:
    """按「各线路供电系统年度生产指标 / 生产指标」切到评估小结或下一章。

    停段只认章级标题，禁止用 startswith(\"5\")——会把「5月…」误当成第5章截断。
    """
    flow: list[dict[str, Any]] = []
    take = False
    for block in doc.blocks or []:
        t = (block.text or "").strip()
        compact = re.sub(r"\s+", "", t)
        if not take:
            if "各线路供电系统年度生产指标" in compact or (
                "年度生产指标" in compact and len(compact) < 40
            ) or (re.search(r"供电.*生产指标", compact) and len(compact) < 48):
                take = True
            continue
        if block.type in {"heading", "paragraph"} and compact:
            if compact.startswith(
                (
                    "4.5",
                    "第5章",
                    "第五章",
                    "第6章",
                    "第六章",
                    "第7章",
                    "第七章",
                    "评估小结",
                    "管理体系",
                    "运维表现",
                    "生产组织",
                    "修程修制",
                )
            ):
                break
            if "生产计划执行" in compact and len(compact) < 48:
                break
            # 5.1 / 7.1 才是下一章；「5月…」继续收
            if re.match(r"^[57][\.．、]", compact) and "MTBF" not in compact and "MCBF" not in compact:
                break
            if re.match(r"^5[^0-9月\.．、]", compact) and len(compact) < 36 and "MTBF" not in compact:
                if "管理" in compact or "合规" in compact or compact == "5":
                    break
            if re.match(r"^7[^0-9月\.．、]", compact) and len(compact) < 36:
                break
        if block.type == "table" and block.rows:
            flow.append({"kind": "table", "rows": [list(r) for r in block.rows]})
            continue
        if block.type == "drawing":
            flow.append(
                {
                    "kind": "drawing",
                    "source_path": doc.source_path or "",
                    "source_index": int(block.source_index or -1),
                }
            )
            continue
        if block.type == "formula":
            flow.append(
                {
                    "kind": "formula",
                    "source_path": doc.source_path or "",
                    "source_index": int(block.source_index or -1),
                    "text": t,
                }
            )
            continue
        if t:
            flow.append(para_flow_item(t, block))
    return flow


def _mtbf_from_loose_tables(docs: list[DocumentModel] | None) -> tuple[list[dict[str, Any]], str]:
    """今年材料未按 4.4 标题切段时，退而收 MTBF/生产指标表及紧前说明段。"""
    for doc in docs or []:
        blocks = list(doc.blocks or [])
        for i, block in enumerate(blocks):
            if block.type != "table" or not block.rows or not _mtbf_table_head(block.rows[0]):
                continue
            flow: list[dict[str, Any]] = []
            for j in range(max(0, i - 6), i):
                t = (blocks[j].text or "").strip()
                if t and any(k in t for k in ("生产指标", "MTBF", "可靠性", "截至")):
                    flow.append(para_flow_item(t, blocks[j]))
            flow.append({"kind": "table", "rows": [list(r) for r in block.rows]})
            return flow, doc.source_name or ""
    return [], ""


def resolve_mtbf_section(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """4.4 生产指标是当年数据：只从今年材料摘；没有则空（成文黄标题）。不复用去年报告。"""
    del prior_docs  # 接口保留与 build_pack 一致，但故意不用去年数据。
    for doc in docs or []:
        flow = _slice_mtbf_flow(doc)
        if flow:
            paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para"]
            return {
                "mtbf_flow": flow,
                "mtbf_paras": paras,
                "mtbf_table": next((x.get("rows") for x in flow if x.get("kind") == "table"), []),
                "mtbf_source": doc.source_name or "",
                "mtbf_via": "year",
            }
    flow, src = _mtbf_from_loose_tables(docs)
    if flow:
        paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para"]
        return {
            "mtbf_flow": flow,
            "mtbf_paras": paras,
            "mtbf_table": next((x.get("rows") for x in flow if x.get("kind") == "table"), []),
            "mtbf_source": src,
            "mtbf_via": "year",
        }
    return {
        "mtbf_flow": [],
        "mtbf_paras": [],
        "mtbf_table": [],
        "mtbf_source": "",
        "mtbf_via": "",
    }


def _slice_ch4_summary(doc: DocumentModel) -> list[dict[str, Any]]:
    """4.5：有则抽；停在第5章标题。禁止 startswith(\"5\")——会把「5月…」误截。"""
    flow: list[dict[str, Any]] = []
    take = False
    for block in doc.blocks or []:
        t = (block.text or "").strip()
        compact = compact_text(t)
        if not take:
            if compact in {"评估小结", "4.5评估小结"} or (
                compact.endswith("评估小结") and len(compact) < 20
            ):
                take = True
                continue
            continue
        if block.type in {"heading", "paragraph"} and compact:
            if hits_section_key(
                compact,
                ("5.1", "第5章", "第五章", "管理体系合规"),
                title_only_words=True,
            ):
                break
            if re.match(r"^[5][\.．、]", compact) and "MTBF" not in compact:
                break
            if re.match(r"^5[^0-9月\.．、]", compact) and len(compact) < 36:
                if "管理" in compact or "合规" in compact or compact == "5":
                    break
            if is_foreign_outline(compact, keep_keys=("4.5",)):
                break
        if block.type == "table" and block.rows:
            flow.append({"kind": "table", "rows": [list(r) for r in block.rows]})
        elif t:
            flow.append(para_flow_item(t, block))
    return flow


def resolve_ch4_summary(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """4.5 小结随当年材料；没有则空。不复用去年报告。"""
    del prior_docs
    for doc in docs or []:
        flow = _slice_ch4_summary(doc)
        if flow:
            return {
                "summary_flow": flow,
                "summary_paras": [str(x.get("text") or "") for x in flow if x.get("kind") == "para"],
                "summary_source": doc.source_name or "",
                "summary_via": "year",
            }
    return {"summary_flow": [], "summary_paras": [], "summary_source": "", "summary_via": ""}


def build_pack(docs: list[DocumentModel], *, year: int, prior_docs=None) -> dict[str, Any]:
    """供电第四章 pack：4.1.1 体量、4.1.2 台数+变化段、4.2 周期表、4.3 故障、4.4 指标、4.5 小结。"""
    prior_docs = prior_docs or []
    matrix = extract_grade_matrix(docs)
    counts = count_grade_cells(matrix)
    grade_source = ""
    if matrix:
        grade_source = str(matrix[0].get("source_note") or "")
    by_line, fault_source = split_fault_lines(docs, year=year)
    cycle_rows, cycle_source = pick_cycle_table(docs, prior_docs)
    plan_text = pick_plan_sentence(docs)
    change_paras, change_src = pick_volume_change_paras(docs)
    scope = resolve_scope_411(docs, prior_docs)
    mtbf = resolve_mtbf_section(docs, prior_docs)
    summary = resolve_ch4_summary(docs, prior_docs)
    line_results = []
    for i in range(1, 19):
        line = f"{i}号线"
        items = by_line.get(line) or []
        if not items:
            continue
        n_text = sum(1 for x in items if x.get("kind") == "text")
        line_results.append(
            {
                "line_id": line,
                "segment": "",
                "device_count": n_text or len(items),
                "subsystem": {"total_score": None, "grade": "已摘录", "score_source": "material"},
            }
        )
    src_412 = "、".join(x for x in [grade_source, change_src] if x)
    return {
        "year": year,
        "grade_source": src_412 or grade_source,
        "volume_text": volume_sentence(counts),
        "volume_change_paras": change_paras,
        "grade_counts": {k: dict(v) for k, v in counts.items()},
        "cycle_rows": cycle_rows,
        "cycle_source": cycle_source,
        "plan_text": plan_text,
        "fault_by_line": by_line,
        "fault_source": fault_source,
        **scope,
        **mtbf,
        **summary,
        "line_results": line_results,
        "warnings": []
        if (matrix or by_line or mtbf.get("mtbf_flow") or change_paras or scope.get("scope_paras"))
        else ["未从上传材料中识别到设备评估结果总表或各线故障叙述。"],
    }


build_ch4_pack = build_pack
