# -*- coding: utf-8 -*-
"""从上传材料抽取供电各章已有内容。认不出的不补。

口径要点（与第四章不要混）：
- 3.3.2 状态分布表只用 POWER_COLS / MS_COLS / ENERGY_COLS，不含接触网列
  （当年总表大约是供电 300 项、三系统合计 477 项）。4.1.2 供电含接触网列是 343 台，不是同一口径。
- 3.1 / 3.2 / 3.3.1 均为可复用体例段：认小节名字（评估方法和内容、评估标准、供电系统设备评估范围），不认编号；先今年材料，体例不足则复用去年完整报告（或项目 2025 保底），都没有则空（成文黄标题）。
- 3.5 两年对比读 prior_2025_snapshot.json，不从材料目录里的 /2025/ 文件夹现抽。
- 各线「评估报告」正文：第 1 章抽线路概述；第 10 章抽「使用环境符合性评估」按线汇总；第 11 章抽退运段补缺。第 3～9 章仍跳过线路整篇，避免污染。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from chapters.ch4.power_extract import build_pack as build_ch4_pack
from chapters.ch4.power_extract import count_grade_cells
# SKIP_GRADE_COLS 标明 3.3.2 故意丢掉的接触网列名；本文件用 POWER_COLS 间接排除，导入供口径对照。
from chapters.power.style import (
    ENERGY_COLS,
    MS_COLS,
    POWER_COLS,
    POWER_CONTROL_CATS,
    POWER_CONTROL_MIDS,
    RETIRE_SKIP,
    SKIP_GRADE_COLS,  # noqa: F401  口径对照，见上一行注释
)
from chapters.common.section_slice import (
    compact_text,
    dedupe_flow_items,
    dedupe_texts,
    hits_section_key,
    is_chapter_or_appendix_title,
    is_foreign_outline,
    is_outline_title_line,
    outline_num,
    slice_named_section,
)
from parsers.document_model import DocumentModel
from scope.grade_matrix import extract_grade_matrix
from scope.names import normalize_line, normalize_segment

# 3.5 对照用的 2025 年报表底，不是当年总表、也不是材料包里的 2025 文件夹。
PRIOR_PATH = Path(__file__).with_name("prior_2025_snapshot.json")
LINE_HEAD = re.compile(r"^(\d+号线)")
LINE_IN_NAME = re.compile(r"(\d+)\s*号?线")
SECTION_CH5 = (
    "法律法规的获取情况",
    "企业标准和制度",
    "制度、标准执行情况检查",
    "合规性评价",
    "特种设备",
    "强制年检",
)
SECTION_CH6 = ("修程修制匹配性评估", "对上一年度合规性评估建议的整改")


def _src(doc: DocumentModel) -> str:
    return doc.source_name or Path(doc.source_path or "").name


def extract_named_section(
    docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...] = (),
    after_keys: tuple[str, ...] = (),
    skip_line_reports: bool = True,
) -> dict[str, Any]:
    """按小节名字从今年材料切一段。有正文/表/图才算抽到；没有返回空，由成文黄标题。

    after_keys：先见到本章语境（如「合规性评价」「修程修制」）后，再认 start_keys。
    避免全材料里多个「评估小结」时误抽到别章。

    对照去年目录：paragraph 伪标题同样停；节号边界匹配（12.1 不误伤见图12.1 语境外仍用节号规则）。
    """
    return slice_named_section(
        docs,
        start_keys=start_keys,
        stop_keys=stop_keys,
        after_keys=after_keys,
        skip_doc=(_is_line_report if skip_line_reports else None),
        build_item=_flow_item,
        source_name=_src,
    )


def section_has_body(sec: dict[str, Any] | None) -> bool:
    sec = sec or {}
    if any(str(t).strip() for t in (sec.get("paras") or [])):
        return True
    for item in sec.get("flow") or []:
        if item.get("kind") in {"table", "drawing", "formula"}:
            return True
        if str(item.get("text") or "").strip():
            return True
    return False


def _body_index(block) -> int:
    idx = getattr(block, "source_index", -1)
    return int(idx) if idx is not None and int(idx) >= 0 else -1


def _drawing_item(doc: DocumentModel, block) -> dict[str, Any]:
    return {"kind": "drawing", "source_path": doc.source_path or "", "source_index": _body_index(block)}


def _formula_item(doc: DocumentModel, block) -> dict[str, Any]:
    return {
        "kind": "formula",
        "source_path": doc.source_path or "",
        "source_index": _body_index(block),
        "text": (block.text or "").strip(),
    }


def _table_item(block, doc: DocumentModel | None = None) -> dict[str, Any]:
    """表格进 flow。有 source_index 时成文整表回拷；否则按 rows 重建。"""
    if doc is not None:
        from chapters.common.table_copy import table_flow_item

        return table_flow_item(doc, block)
    item: dict[str, Any] = {"kind": "table", "rows": [list(r) for r in (block.rows or [])]}
    merges = getattr(block, "vmerge", None)
    if merges is not None:
        item["vmerge"] = [list(m) for m in merges]
    return item


def _flow_item(doc: DocumentModel, block) -> dict[str, Any] | None:
    if block.type == "formula":
        return _formula_item(doc, block)
    if block.type == "drawing":
        return _drawing_item(doc, block)
    if block.type == "table" and block.rows:
        return _table_item(block, doc)
    text = (block.text or "").strip()
    if text:
        from chapters.common.source_yellow import para_flow_item

        return para_flow_item(text, block)
    return None


def _append_flow(bucket: list[dict[str, Any]], doc: DocumentModel, block) -> None:
    item = _flow_item(doc, block)
    if item:
        bucket.append(item)


def _bare_heading(text: str) -> str:
    return re.sub(r"^[\d.、\s]+", "", (text or "").strip())


def _is_caption_text(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 2 or len(t) >= 80 or t[0] not in {"图", "表"}:
        return False
    return t[1].isdigit() or t[1] in " -"


from chapters.common.domain_filter import OVERHEAD_MARKS, prepare_power_docs


def _norm(text: str) -> str:
    return str(text or "").replace("\n", "").replace(" ", "").strip()


def _is_empty(val: str) -> bool:
    t = str(val or "").strip()
    return t in {"", "/", "-", "—", "无", "None"}


def _clean_measure(val: str) -> str:
    t = str(val or "").strip().strip("；; ")
    t = re.sub(r"[；;]{2,}", "；", t)
    return "" if _is_empty(t) else t


def _pdf_noise_line(text: str) -> bool:
    t = (text or "").strip()
    if not t or t.rstrip("：:") == "附件":
        return True
    if t.startswith("第") and t.endswith("页"):
        return True
    compact = t.replace(" ", "")
    if compact.isdigit():
        return True
    return bool(re.fullmatch(r"(?:[0-9A-Za-z]\s*){2,}", t) and len(compact) <= 8)


def _merge_pdf_pages(blocks) -> list[str]:
    """PDF 按页拆成碎行，拼回带「隐患/排查/整改」的句子。页码和附件行丢掉，不当第 8 章正文。"""
    pages: list[list[str]] = []
    buf: list[str] = []
    for block in blocks or []:
        t = (block.text or "").strip()
        if block.type == "heading" and t.startswith("第") and t.endswith("页"):
            if buf:
                pages.append(buf)
                buf = []
            continue
        if block.type != "paragraph" or _pdf_noise_line(t):
            continue
        buf.append(t)
    if buf:
        pages.append(buf)
    out: list[str] = []
    for lines in pages:
        joined = "".join(lines)
        if len(joined) < 18 or not any(ch in joined for ch in "。；"):
            continue
        for part in re.split(r"(?<=[。；])", joined):
            sent = part.strip()
            if len(sent) >= 12 and any(k in sent for k in ("隐患", "排查", "整改", "治理")):
                out.append(sent)
    return out


def _is_pdf(doc: DocumentModel) -> bool:
    return (doc.suffix or "").lower() == ".pdf" or _src(doc).lower().endswith(".pdf")


def _pdf_topic(doc: DocumentModel) -> str:
    """粗分 PDF 用途，避免把库存规定、退运扫描件误当成第 8 章隐患正文。"""
    name = _src(doc)
    blob = name + "\n" + "\n".join((b.text or "") for b in (doc.blocks or [])[:50])
    if any(k in blob for k in ("隐患排查", "动态治理", "事故隐患", "隐患清单")):
        return "hazard"
    if "库存管理规定" in name or ("安全库存" in blob and "企业标准" in blob):
        return "stock_rule"
    if "使用环境" in blob:
        return "env"
    if any(k in blob for k in ("退运", "报废")):
        return "retire"
    if "计划数量" in blob and "完成率" in blob:
        return "plan"
    return "other"


def inspect_pdfs(docs: list[DocumentModel]) -> list[dict[str, Any]]:
    """扫一遍 PDF 主题（隐患/库存规定/环境/退运/计划），给调试和缺材料判断，不把 PDF 噪声当正文。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for doc in docs or []:
        if not _is_pdf(doc):
            continue
        name = _src(doc)
        if name in seen:
            continue
        seen.add(name)
        topic = _pdf_topic(doc)
        out.append({"source": name, "topic": topic, "blocks": len(doc.blocks or [])})
    return out


def _stock_table_kind(rows: list[list[str]]) -> str:
    """第 9 章只要供电安全库存表。触网/接触轨表归接触网分册，不能进表 9-1。"""
    if not rows or not any(str(c).strip() for r in rows[1:] for c in r):
        return ""
    head = "".join(str(c) for c in (rows[0] if rows else []))
    sample = "".join(str(c) for r in rows[:4] for c in r)
    if any(k in sample for k in ("触网", "接触网", "接触轨", "柔性接触网", "刚性接触网")):
        return "overhead"
    if "安全库存" in head or ("物料名称" in head and ("规格型号" in head or "型号规格" in head)):
        return "power"
    return ""


def _is_line_report(doc: DocumentModel) -> bool:
    """各线评估报告：只给第 1 章概述。第 3～11 章必须跳过，否则线路稿会污染合规/隐患/退运。

    文件名带「管控措施」的不是线路报告——那是 3.4 / 附录 A 的设备树表。
    认路径含「线路报告」，或文件名带号线且像评估/安全评价专册——不绑死某维护部目录。
    """
    name = doc.source_name or ""
    path = (doc.source_path or "").replace("\\", "/")
    if "管控措施" in name:
        return False
    if "线路报告" in path:
        return True
    if _line_no_from_doc(doc) is None:
        return False
    return any(k in name for k in ("评估报告", "安全评价", "供电系统报告"))

def _compact_heading(text: str) -> str:
    return re.sub(r"[\s　]+", "", str(text or "").strip())


def _is_overhead_annual(doc: DocumentModel) -> bool:
    """接触网年报不进供电 3.1/3.2/3.3.1。只认文件名，正文提到接触网的供电年报仍留下。"""
    name = _src(doc)
    return any(k in name for k in OVERHEAD_MARKS)


def _looks_like_ch3_title(compact: str) -> bool:
    """第 3 章「设备功能有效性评估」章题，不含已编号的 3.x 小节。"""
    if "设备功能有效性" not in compact:
        return False
    if compact.startswith("3.") or compact.startswith("3．"):
        return False
    return (
        compact.startswith("3")
        or compact.startswith("第3章")
        or compact.startswith("第三章")
        or compact.startswith("设备功能有效性")
    )


def _looks_like_other_chapter(compact: str) -> bool:
    """离开第 3 章（第 1、2、4 章及以后）。"""
    if _looks_like_ch3_title(compact):
        return False
    if re.match(r"^第[12一二]章", compact) or compact.startswith("第一章") or compact.startswith("第二章"):
        return True
    if re.match(r"^第[4-9四五六七八九十]+章", compact) or compact.startswith("第四章"):
        return True
    if compact.startswith("4") and "运营契合" in compact:
        return True
    return False


def _bare_section_name(compact: str) -> str:
    """去掉 3.1 / 3.3.1 / 第3章 这类编号，只留小节名字。"""
    return re.sub(r"^(?:第[0-9一二三四五六七八九十]+章|[0-9]+(?:[\.．][0-9]+)*)", "", compact or "")


def match_ch3_prose_key(compact: str) -> str | None:
    """只认第 3 章小节全名。不认第二章的「评估方法」（那是实施方案导图，不是 3.1）。

    3.3.1 必须带「设备评估范围」等标题词，避免正文「评估范围包括…」误当成小节。
    """
    name = _bare_section_name(compact)
    if not name:
        return None
    if "评估标准" in name:
        return "standard"
    # 必须带「和内容」。单写「评估方法」是第 2 章导图节，不能当 3.1。
    if "评估方法和内容" in name:
        return "method"
    # 3.3.1 供电子系统设备评估范围（体例段，可复用去年/2025保底）
    if "设备评估范围" in name:
        return "scope"
    if name in {"评估范围", "供电子系统评估范围"}:
        return "scope"
    if name.endswith("评估范围") and any(k in name for k in ("供电", "子系统", "设备")):
        return "scope"
    return None


def _looks_like_ch3_prose(key: str, hit: dict[str, Any] | None) -> bool:
    """今年材料是否真有该体例段；过短/空壳不算有，应回退去年或保底。"""
    hit = hit or {}
    flow = hit.get("flow") or []
    paras = [str(p).strip() for p in (hit.get("paras") or []) if str(p).strip()]
    text_len = sum(len(p) for p in paras)
    has_table = any(x.get("kind") == "table" for x in flow)
    has_formula = any(x.get("kind") in {"formula", "formula_3_1"} for x in flow)
    has_drawing = any(x.get("kind") == "drawing" for x in flow)
    if key == "scope":
        # 3.3.1 历年多为说明+范围表
        return has_table or has_drawing or text_len >= 40
    if key == "method":
        return has_formula or text_len >= 30
    if key == "standard":
        return has_table or text_len >= 30
    return bool(paras or flow)


def _looks_like_ch3_stop(compact: str) -> bool:
    """第 3 章里不是这三节体例的小节，切段时在这里停下。"""
    if match_ch3_prose_key(compact):
        return False
    name = _bare_section_name(compact)
    if "状态分布" in name:
        return True
    if "管控措施" in name:
        return True
    if name == "供电子系统评估" or name.endswith("供电子系统评估"):
        return True
    if "两年对比" in name or "劣化" in name:
        return True
    # 第二章「评估方法」导图节，遇到也不继续吃正文。
    if name == "评估方法" or name.endswith("评估方法"):
        return True
    return False


def _is_short_numbered_title(compact: str, text: str) -> bool:
    if not compact or "。" in (text or "") or len(compact) > 48:
        return False
    return bool(re.match(r"^(?:第[0-9一二三四五六七八九十]+章|[0-9]+(?:[\.．][0-9]+)*)", compact))


def _is_ch3_prose_boundary(block, compact: str, text: str) -> bool:
    if block.type == "heading":
        return True
    if not text or "。" in text or len(compact) > 48:
        return False
    if match_ch3_prose_key(compact):
        return True
    if _looks_like_ch3_title(compact) or _looks_like_other_chapter(compact) or _looks_like_ch3_stop(compact):
        return True
    return _is_short_numbered_title(compact, text)


def _is_toc_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "……" in t or "..." in t:
        return True
    if "。" not in t and len(t) < 48 and re.search(r"\d+\s*$", t):
        if any(k in t for k in ("评估方法", "评估标准", "评估范围", "供电子系统")):
            return True
    return False


def _is_section_title_line(text: str) -> bool:
    """小节标题本身（含编号写错的），不是正文。正文即使提到「评估标准」也留下。"""
    t = (text or "").strip()
    if not t or "。" in t or "；" in t:
        return False
    compact = _compact_heading(t)
    if not match_ch3_prose_key(compact):
        return False
    leftover = _bare_section_name(compact)
    for token in ("评估方法和内容", "供电子系统设备评估范围", "设备评估范围", "评估标准", "评估方法"):
        leftover = leftover.replace(token, "")
    leftover = re.sub(r"[\d\.．、\-—\(\)（）]+", "", leftover)
    return len(leftover) <= 2


CH3_PROSE_KEYS = ("method", "standard", "scope")


def _is_formula_artifact(item: dict[str, Any]) -> bool:
    """无 source 的残缺公式行（空图、半截「其中」），在已有真公式时可丢掉。"""
    kind = item.get("kind")
    if kind == "formula":
        return False
    if kind in {"drawing", "formula_3_1"}:
        return True
    text = str(item.get("text") or "").strip()
    if not text:
        return True
    if text in {"其中：", "其中", "（3-1）", "(3-1)"}:
        return True
    if re.fullmatch(r"[swv](?:_?i)?", text, flags=re.I):
        return True
    if ("子系统" in text or text.startswith("—") or text.startswith("--") or text.startswith("——")) and len(text) < 48:
        return True
    return False


def _inject_formula_3_1(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """「综合评估表达式」后：优先保留源稿 formula；没有可回拷的公式时再退回体例 formula_3_1。"""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(flow):
        item = flow[i]
        text = str(item.get("text") or "").strip() if item.get("kind") == "para" else ""
        if "综合评估表达式" in text:
            out.append(item)
            i += 1
            chunk: list[dict[str, Any]] = []
            while i < len(flow) and (
                flow[i].get("kind") == "formula"
                or _is_formula_artifact(flow[i])
                or (
                    flow[i].get("kind") == "para"
                    and str(flow[i].get("text") or "").strip() in {"其中：", "其中"}
                )
            ):
                chunk.append(flow[i])
                i += 1
            formulas = [x for x in chunk if x.get("kind") == "formula"]
            if formulas:
                # 保留「其中：」说明行与真公式，丢掉空图/编号残片
                for x in chunk:
                    if x.get("kind") == "formula":
                        out.append(x)
                    elif x.get("kind") == "para" and str(x.get("text") or "").strip() in {"其中：", "其中"}:
                        out.append(x)
            else:
                out.append({"kind": "formula_3_1"})
            continue
        out.append(item)
        i += 1
    return out


def _pack_prose_flow(items: list[dict[str, Any]], source: str) -> dict[str, Any] | None:
    """丢掉目录行和节标题本身；有足够正文或有表才算抽到。"""
    flow: list[dict[str, Any]] = []
    paras: list[str] = []
    for item in items or []:
        kind = item.get("kind")
        if kind == "para":
            text = str(item.get("text") or "").strip()
            if not text or _is_toc_line(text) or _is_section_title_line(text):
                continue
            paras.append(text)
            flow.append(item)
        elif kind in {"table", "drawing", "formula"}:
            flow.append(item)
    flow = _inject_formula_3_1(flow)
    paras = [str(x.get("text") or "").strip() for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    has_table = any(x.get("kind") == "table" for x in flow)
    has_formula = any(x.get("kind") in {"formula", "formula_3_1"} for x in flow)
    if not paras and not has_table and not has_formula:
        return None
    return {"paras": paras, "flow": flow, "source": source}


def _best_prose_slice(slices: list[list[dict[str, Any]]], source: str) -> dict[str, Any] | None:
    packed = [hit for hit in (_pack_prose_flow(items, source) for items in slices) if hit]
    if not packed:
        return None

    def score(hit: dict[str, Any]) -> tuple[int, int]:
        n_table = sum(1 for x in hit.get("flow") or [] if x.get("kind") == "table")
        n_text = sum(len(t) for t in hit.get("paras") or [])
        return (n_table, n_text)

    return max(packed, key=score)


def _slice_ch3_prose(doc: DocumentModel) -> dict[str, list[list[dict[str, Any]]]]:
    """按名字切 3.1/3.2/3.3.1。编号写错（如 3.1 评估标准）仍归到评估标准。"""
    found: dict[str, list[list[dict[str, Any]]]] = {key: [] for key in CH3_PROSE_KEYS}
    current = ""
    buf: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current, buf
        if current and buf:
            found[current].append(list(buf))
        buf = []
        current = ""

    for block in doc.blocks or []:
        t = (block.text or "").strip()
        compact = _compact_heading(t)
        boundary = _is_ch3_prose_boundary(block, compact, t)
        if boundary:
            if _looks_like_ch3_title(compact):
                flush()
                continue
            if _looks_like_other_chapter(compact):
                flush()
                continue
            key = match_ch3_prose_key(compact)
            if key:
                flush()
                current = key
                continue
            if _looks_like_ch3_stop(compact) or (
                _is_short_numbered_title(compact, t) and not _is_caption_text(t)
            ):
                flush()
                continue
        if not current:
            continue
        item = _flow_item(doc, block)
        if item:
            buf.append(item)
    flush()
    return found


def extract_ch3_prose(docs: list[DocumentModel] | None) -> dict[str, dict[str, Any]]:
    """从一批材料按名字抽出 3.1/3.2/3.3.1。各线报告、接触网年报不看。"""
    empty = {"paras": [], "flow": [], "source": ""}
    out = {key: dict(empty) for key in CH3_PROSE_KEYS}
    for doc in docs or []:
        if _is_line_report(doc) or _is_overhead_annual(doc):
            continue
        sliced = _slice_ch3_prose(doc)
        source = _src(doc)
        for key in CH3_PROSE_KEYS:
            if out[key].get("paras") or out[key].get("flow"):
                continue
            hit = _best_prose_slice(sliced.get(key) or [], source)
            if hit:
                out[key] = hit
        if all(out[key].get("paras") or out[key].get("flow") for key in CH3_PROSE_KEYS):
            break
    return out


def resolve_ch3_prose(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, dict[str, Any]]:
    """3.1 / 3.2 / 3.3.1：均为可复用体例段。

    先今年材料（按名字）；体例不足再复用去年完整报告（或项目 2025 保底）。
    都没有则空（成文黄标题）。3.3.2 状态分布表不走这里。
    """
    year_hit = extract_ch3_prose(docs)
    prior_hit = extract_ch3_prose(prior_docs)
    out: dict[str, dict[str, Any]] = {}
    for key in CH3_PROSE_KEYS:
        y = year_hit.get(key) or {}
        p = prior_hit.get(key) or {}
        if _looks_like_ch3_prose(key, y):
            out[key] = {**y, "via": "year"}
        elif _looks_like_ch3_prose(key, p):
            out[key] = {**p, "via": "prior"}
        else:
            out[key] = {"paras": [], "flow": [], "source": "", "via": ""}
    return out


def resolve_ch3_method(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """兼容旧测试：只返回 3.1 评估方法和内容。"""
    return resolve_ch3_prose(docs, prior_docs)["method"]


def _in_year_folder(path: str, year: str) -> bool:
    """材料包里常夹着往年文件夹。第 11 章退运不能吃 /2025/ 里的旧说明。"""
    norm = (path or "").replace("/", "\\")
    return f"\\{year}\\" in norm


def load_prior_2025() -> list[list[list[str]]]:
    """读 3.5 用的 2025 年报表底：[供电表, 主变表, 能源表]。没有快照则 3.5 整节黄标题。"""
    if not PRIOR_PATH.exists():
        return []
    data = json.loads(PRIOR_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def matrix_table(rows: list[dict[str, Any]], cols: list[str], category: str) -> list[list[str]]:
    """把总表矩阵收成 3.3.2 一张表。cols 决定列，供电表用 POWER_COLS 故不含接触网列。"""
    out = [["线路", "区段", *cols]]
    for row in rows:
        if (row.get("category") or "") not in category.split("|"):
            continue
        grades = row.get("grades") or {}
        out.append(
            [
                row.get("line_id") or "",
                row.get("segment") or "",
                *[grades.get(c) or "/" for c in cols],
            ]
        )
    return out


def count_shown(table: list[list[str]]) -> Counter:
    """只数表里已经写出的 A～D 格。空格和「/」不算项，避免把未评估列吹进 3.3.2 概述。"""
    c: Counter = Counter()
    if len(table) < 2:
        return c
    for row in table[1:]:
        for cell in row[2:]:
            letter = str(cell).strip().upper()
            if letter in {"A", "B", "C", "D"}:
                c[letter] += 1
    return c


def grade_dist_note(table: list[list[str]]) -> str:
    """3.3.2 概述里「C 类分布于哪些中类、D 类在哪几条线」——只描述已出现的格，不推断原因。"""
    if len(table) < 2:
        return ""
    cols = table[0][2:]
    c_mids: list[str] = []
    d_by: dict[str, list[str]] = defaultdict(list)
    for row in table[1:]:
        line = row[0] if row else ""
        for i, col in enumerate(cols):
            letter = str(row[2 + i] if 2 + i < len(row) else "").strip().upper()
            if letter == "C" and col not in c_mids:
                c_mids.append(col)
            if letter == "D" and line and line not in d_by[col]:
                d_by[col].append(line)
    parts: list[str] = []
    if c_mids:
        parts.append("C类设备主要分布于" + "、".join(c_mids))
    if d_by:
        bits = [f"{'、'.join(lines)}{col}" for col, lines in d_by.items()]
        parts.append("D类设备分别为" + "；".join(bits))
    return "。".join(parts)


def volume_from_tables(power: list[list[str]], main: list[list[str]], energy: list[list[str]]) -> str:
    """3.3.2 开篇体量：供电（不含接触网）+ 主变 + 能源，单位是「项」。

    与 4.1.2「台」不同：这里按三张已裁列的表点数，当年大约 300 + 主变 + 能源 ≈ 477 项。
    """
    pc, mc, ec = count_shown(power), count_shown(main), count_shown(energy)

    def piece(label: str, c: Counter, table: list[list[str]]) -> str | None:
        total = c["A"] + c["B"] + c["C"] + c["D"]
        if not total:
            return None
        text = (
            f"{label}完成{total}项，其中A类设备{c['A']}项，B类设备{c['B']}项，"
            f"C类设备{c['C']}项，D类设备{c['D']}项"
        )
        note = grade_dist_note(table)
        return text + ("。" + note if note else "")

    grand = sum(c["A"] + c["B"] + c["C"] + c["D"] for c in (pc, mc, ec))
    if not grand:
        return ""
    text = (
        f"供电（不含接触网设备）、主变电所系统、能源系统设备评估{grand}项，"
        f"其中，A类设备{pc['A']+mc['A']+ec['A']}项，B类设备{pc['B']+mc['B']+ec['B']}项，"
        f"C类设备{pc['C']+mc['C']+ec['C']}项，D类设备{pc['D']+mc['D']+ec['D']}项。"
    )
    extras = [piece("供电", pc, power), piece("主变电", mc, main), piece("能源系统", ec, energy)]
    return text + "".join((p if p.endswith("。") else p + "。") for p in extras if p)


def extract_grade_tables(docs: list[DocumentModel]) -> dict[str, Any]:
    """第 3 章 3.3.2：总表 → 供电/主变/能源三张状态分布表。列集不含接触网。"""
    matrix = extract_grade_matrix(docs)
    source = ""
    if matrix:
        source = str(matrix[0].get("source_note") or "")
    power = matrix_table(matrix, POWER_COLS, "供电")
    main = matrix_table(matrix, MS_COLS, "主变电所|主变电")
    energy = matrix_table(matrix, ENERGY_COLS, "能源系统")
    return {
        "source": source,
        "power_table": power if len(power) > 1 else [],
        "main_table": main if len(main) > 1 else [],
        "energy_table": energy if len(energy) > 1 else [],
        "overview": volume_from_tables(power, main, energy),
        # counts 仍按总表全列（含接触网），给对照用；3.3.2 正文只用上面三张已裁列的表。
        "counts": {k: dict(v) for k, v in count_grade_cells(matrix).items()},
    }


def _measure_clauses(text: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[；;]", str(text or "")):
        clause = _clean_measure(part)
        if clause:
            out.append(clause)
    return out


def _merge_measure_texts(texts: list[str]) -> str:
    """多条措施拼成一句；相同分句只留一次（供电/主变常共用同一句故障影响）。"""
    clauses: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for clause in _measure_clauses(text):
            key = re.sub(r"\s+", "", clause)
            if key in seen:
                continue
            seen.add(key)
            clauses.append(clause)
    return "；".join(clauses)


def _collapse_control_raw(raw: list[dict[str, str]]) -> list[dict[str, str]]:
    """3.4 按线路+区段+中类合并。设备树里供电、主变电所都有应急电源时，不再写成两段同名。"""
    order: list[tuple[str, str, str]] = []
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in raw:
        key = (item.get("line") or "", item.get("segment") or "正线", (item.get("mid") or "").strip())
        if not key[0] or not key[2]:
            continue
        if key not in buckets:
            order.append(key)
            buckets[key] = {
                "line": key[0],
                "segment": key[1],
                "mid": key[2],
                "grade": item.get("grade") or "",
                "texts": [],
            }
        text = (item.get("text") or "").strip()
        if text:
            buckets[key]["texts"].append(text)
    out: list[dict[str, str]] = []
    for key in order:
        bucket = buckets[key]
        out.append(
            {
                "line": bucket["line"],
                "segment": bucket["segment"],
                "mid": bucket["mid"],
                "grade": bucket["grade"],
                "text": _merge_measure_texts(bucket["texts"]),
            }
        )
    return out


def _compact_label(text: str) -> str:
    """大类/中类比对用：去空白换行。"""
    return re.sub(r"[\s　\n\r]+", "", str(text or "").strip())


def _is_power_control_category(category: str) -> bool:
    """供电设备树大类：供电 / 主变电所系统 / 能源系统。接触网（轨）系统设备不算。"""
    cat = _compact_label(category)
    if not cat:
        return False
    if any(k in cat for k in ("接触网", "触网", "接触轨")):
        return False
    allowed = {_compact_label(x) for x in POWER_CONTROL_CATS}
    return cat in allowed


def _is_power_control_mid(mid: str) -> bool:
    """供电设备树中类白名单。可以缺，不能多出隔离开关/刚性接触网等。"""
    name = _compact_label(mid)
    if not name:
        return False
    allowed = {_compact_label(x) for x in POWER_CONTROL_MIDS}
    return name in allowed


def _table_is_controls(rows: list[list[str]]) -> bool:
    """设备树管控措施表。必须是线路+大类+中类+评估结果+管控措施。

    补充材料里的风险清单也有「管控措施」「本线路」，不能当成 3.4 设备树。
    接触网表用「子系统/设备」，且中类是刚性接触网等，不进供电 3.4。
    表体至少要有一条供电白名单中类，否则空模板/纯触网表不当供电管控措施。
    """
    head = "".join(_norm(c) for r in rows[:3] for c in r)
    if any(k in head for k in ("接触网专业", "风险点描述", "风险类别", "隐患描述")):
        return False
    # 触网设备树表头是子系统+设备，不是大类+中类。
    if "子系统" in head and "设备" in head and ("大类" not in head or "中类" not in head):
        return False
    if not (
        "管控措施" in head
        and "线路" in head
        and "大类" in head
        and "中类" in head
        and "评估结果" in head
    ):
        return False
    start = 0
    for i, row in enumerate(rows[:4]):
        if any("线路" in str(c) for c in row) and any("区段" in str(c) for c in row):
            start = i
            break
    for row in rows[start + 2 :]:
        cells = [str(c or "").strip() for c in row]
        if len(cells) < 5:
            continue
        if cells[0] and not cells[0].isdigit() and "号线" in cells[0]:
            category, mid = cells[2] if len(cells) > 2 else "", cells[3] if len(cells) > 3 else ""
        else:
            category, mid = cells[3] if len(cells) > 3 else "", cells[4] if len(cells) > 4 else ""
        if _is_power_control_category(category) and _is_power_control_mid(mid):
            return True
    return False


def extract_controls(docs: list[DocumentModel]) -> dict[str, Any]:
    """第 3 章 3.4 / 附录 A：设备树「管控措施」表。跳过接触网专业行；措施列空则成文黄该线标题。

    可同时吃多份管控措施 Excel（如设备树 + 月度补充），按线路/区段/中类合并；
    标题出处列出全部用到的文件名，不只留最后一份。
    """
    sources: list[str] = []
    raw: list[dict[str, str]] = []
    appendix: list[list[str]] = []
    sheet = ""
    headers = [
        "线路",
        "区段",
        "大类",
        "中类",
        "评估结果",
        "大修更新改造",
        "差异化管控",
        "核心部件更换",
        "成本内项目",
        "备件储备情况",
        "故障影响运营程度",
    ]
    for doc in docs or []:
        for block in doc.blocks:
            if block.type == "heading" and (block.text or "").startswith("工作表:"):
                sheet = (block.text or "").replace("工作表:", "").strip()
                continue
            if block.type != "table" or not block.rows:
                continue
            # 接触网专业工作表不进供电 3.4。
            if "接触网" in sheet:
                continue
            rows = [list(r) for r in block.rows]
            if not _table_is_controls(rows):
                continue
            name = _src(doc)
            if name and name not in sources:
                sources.append(name)
            # two-line header: 管控措施 subcols
            start = 0
            for i, row in enumerate(rows[:4]):
                if any("线路" in str(c) for c in row) and any("区段" in str(c) for c in row):
                    start = i
                    break
            if not appendix:
                appendix = [headers]
            for row in rows[start + 2 :]:
                cells = [str(c or "").strip() for c in row]
                if len(cells) < 6:
                    continue
                line = normalize_line(cells[1] if cells[0].isdigit() or cells[0] == "" else cells[0])
                if not line:
                    # 序号, 线路, 区段, ...
                    line = normalize_line(cells[1] if len(cells) > 1 else "")
                seg_i, cat_i, mid_i, grade_i = 2, 3, 4, 5
                if cells[0] and not cells[0].isdigit() and "号线" in cells[0]:
                    line = normalize_line(cells[0])
                    seg_i, cat_i, mid_i, grade_i = 1, 2, 3, 4
                segment = normalize_segment(cells[seg_i] if len(cells) > seg_i else "")
                category = cells[cat_i] if len(cells) > cat_i else ""
                mid = cells[mid_i] if len(cells) > mid_i else ""
                grade = cells[grade_i] if len(cells) > grade_i else ""
                rest = cells[grade_i + 1 :]
                while len(rest) < 6:
                    rest.append("")
                # 供电 3.4 只收白名单大类/中类；接触网表、隔离开关等一律丢掉。
                if not _is_power_control_category(category) or not _is_power_control_mid(mid):
                    continue
                appendix.append([line, segment, category, mid, grade, *rest[:6]])
                texts = [_clean_measure(x) for x in rest[:6]]
                texts = [x for x in texts if x]
                if texts:
                    raw.append(
                        {
                            "line": line,
                            "segment": segment,
                            "mid": mid,
                            "grade": grade,
                            "text": "；".join(texts),
                        }
                    )
    raw = _collapse_control_raw(raw)
    prose: list[dict[str, Any]] = []
    by_line: dict[str, list] = defaultdict(list)
    for item in raw:
        by_line[item["line"]].append(item)
    for i in range(1, 19):
        line = f"{i}号线"
        items = by_line.get(line) or []
        if not items:
            continue
        segs: dict[str, list] = defaultdict(list)
        for item in items:
            segs[item["segment"] or "正线"].append(item)
        blocks = []
        for seg, group in segs.items():
            lines = [f"{seg}：" if seg else ""]
            for item in group:
                lines.append(f"{item['mid']}：{item['text']}")
            blocks.append("\n".join(x for x in lines if x))
        prose.append({"line": line, "blocks": blocks})
    return {"source": "、".join(sources), "prose": prose, "appendix": appendix if len(appendix) > 1 else []}


def _compare_line_order(prior: list[list[str]], current: list[list[str]]) -> list[str]:
    """3.5 线路顺序：先当年出现的线，再补 2025 快照里多出来的线，避免把已退出区段丢掉。"""
    seen: list[str] = []
    for row in current[1:] + prior[1:]:
        line = row[0] if row else ""
        if line and line not in seen:
            seen.append(line)
    return seen


def _seg_related(a: str, b: str) -> bool:
    """新区段名是否挂在旧区段旁（「一期」与「一期南段」）。用来把两年对比行插在一起。"""
    if not a or not b or a == b:
        return bool(a) and a == b
    return a.startswith(b) or b.startswith(a)


def _compare_keys(prior: list[list[str]], current: list[list[str]]) -> list[tuple[str, str]]:
    """3.5 行序：先跟 2025 快照，新区段插到名称相关的旧区段后面（如「一期」旁跟「一期南段」）。"""
    prior_by: dict[str, list[tuple[str, str]]] = defaultdict(list)
    current_by: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in prior[1:]:
        prior_by[row[0]].append((row[0], row[1]))
    for row in current[1:]:
        current_by[row[0]].append((row[0], row[1]))
    keys: list[tuple[str, str]] = []
    for line in _compare_line_order(prior, current):
        olds = prior_by.get(line) or []
        news = current_by.get(line) or []
        if not olds:
            keys.extend(news)
            continue
        extras = [k for k in news if k not in olds]
        placed: set[tuple[str, str]] = set()
        group: list[tuple[str, str]] = []
        for old in olds:
            group.append(old)
            placed.add(old)
            for extra in extras:
                if extra not in placed and _seg_related(old[1], extra[1]):
                    group.append(extra)
                    placed.add(extra)
        for extra in extras:
            if extra not in placed:
                group.append(extra)
        keys.extend(group)
    return keys


def _grade_cells(vals: list[str] | None, n: int) -> list[str]:
    """某年缺该区段时填「/」，保持 3.5 两年并排列数一致，不删行。"""
    if not vals:
        return ["/"] * n
    out: list[str] = []
    for i in range(n):
        cell = str(vals[i]).strip() if i < len(vals) else ""
        out.append(cell if cell else "/")
    return out


def compare_years(prior: list[list[str]], current: list[list[str]], year_old: int, year_new: int) -> list[list[str]]:
    """第 3 章 3.5：按 2025 行序把两年等级并排。新区段挂在相关旧区段旁，缺的一年填「/」，不删旧行。"""
    if len(prior) < 2 or len(current) < 2:
        return []
    head = prior[0]
    if "时间" not in head:
        cols = head[2:]
        out_head = ["线路", "区段", "时间", *cols]
    else:
        cols = [c for c in head[3:]]
        out_head = ["线路", "区段", "时间", *cols]
        prior = [[r[0], r[1], *r[3:]] if len(r) > 3 else r for r in prior]
    old_map = {(r[0], r[1]): r[2:] for r in prior[1:]}
    new_map = {(r[0], r[1]): r[2:] for r in current[1:]}
    out = [out_head]
    n_cols = len(out_head) - 3
    for key in _compare_keys(prior, current):
        out.append([key[0], key[1], str(year_old), *_grade_cells(old_map.get(key), n_cols)])
        out.append([key[0], key[1], str(year_new), *_grade_cells(new_map.get(key), n_cols)])
    return out


def migrations(prior: list[list[str]], current: list[list[str]]) -> list[str]:
    """第 3 章 3.6：只记等级变差（A→B→C→D）的区段中类。变好的不写，避免小结编成全面改善。"""
    if len(prior) < 2 or len(current) < 2:
        return []
    cols = prior[0][2:]
    old_map = {(r[0], r[1]): r[2:] for r in prior[1:]}
    new_map = {(r[0], r[1]): r[2:] for r in current[1:]}
    notes = []
    for key, new in new_map.items():
        old = old_map.get(key)
        if not old:
            continue
        for i, col in enumerate(cols):
            a = (old[i] if i < len(old) else "").strip().upper()
            b = (new[i] if i < len(new) else "").strip().upper()
            if a in "ABCD" and b in "ABCD" and a != b and "ABCD".find(b) > "ABCD".find(a):
                notes.append(f"{key[0]}{key[1]}，{col}，由{a}迁移到{b}")
    return notes


def _empty_ch5() -> dict[str, Any]:
    return {
        "source": "",
        "special": [],
        "special_flow": [],
        "special_source": "",
        "special_via": "",
        "inspect": [],
        "inspect_flow": [],
        "inspect_source": "",
        "inspect_via": "",
        "law": [],
        "law_flow": [],
        "std_paras": [],
        "std_table": [],
        "std_flow": [],
        "exec": [],
        "exec_flow": [],
        "eval": [],
        "eval_flow": [],
        "drawings": [],
        "summary_paras": [],
        "summary_flow": [],
    }


def _empty_ch6() -> dict[str, Any]:
    return {
        "source": "",
        "intro": [],
        "intro_flow": [],
        "intro_via": "",
        "intro_source": "",
        "revise": [],
        "revise_flow": [],
        "tables": [],
        "count_table": [],
        "incomplete": False,
        "summary_paras": [],
        "summary_flow": [],
    }


def _flow_text_sig(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> str:
    parts = [compact_text(str(x.get("text") or "")) for x in (flow or []) if x.get("kind") == "para"]
    if not parts and paras:
        parts = [compact_text(p) for p in paras if str(p).strip()]
    return "|".join(parts[:24])


def _section_richness(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> int:
    flow = flow or []
    paras = paras or []
    n_draw = sum(1 for x in flow if x.get("kind") == "drawing")
    n_tab = sum(1 for x in flow if x.get("kind") == "table")
    n_para = sum(1 for x in flow if x.get("kind") == "para") or len([p for p in paras if str(p).strip()])
    return n_para + n_draw * 4 + n_tab * 3


def _looks_like_ch51(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> bool:
    """对照历年体例：5.1 应有规程表（或足够长的表+说明），不能只有一句空话。"""
    flow = flow or []
    if any(x.get("kind") == "table" for x in flow):
        return True
    text_len = sum(len(str(x.get("text") or "")) for x in flow) + sum(len(str(p)) for p in (paras or []))
    return text_len >= 80 and any(k in "".join(str(x.get("text") or "") for x in flow) for k in ("规程", "表5", "特种设备"))


def _looks_like_ch52(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> bool:
    """对照历年体例：5.2 应有检测/年检图或明确图题说明。"""
    flow = flow or []
    if any(x.get("kind") == "drawing" for x in flow):
        return True
    blob = "".join(str(x.get("text") or "") for x in flow) + "".join(str(p) for p in (paras or []))
    return ("如图" in blob or "图5" in blob) and len(blob) >= 40


def _is_short_section_title(compact: str, max_len: int = 48) -> bool:
    return bool(compact) and len(compact) <= max_len and compact[-1:] not in "。！？；"


def _match_ch5_sub(bare: str, compact: str, t: str) -> str | None:
    """只认短标题行，避免把「特种设备…如表5-1」导语当成新小节切走。"""
    if not _is_short_section_title(compact, 56):
        return None
    if hits_section_key(compact, ("5.1",)) or bare.startswith("特种设备、") or bare in {
        "特种设备、消防、防雷规程",
        "特种设备消防防雷规程",
    }:
        return "special"
    if hits_section_key(compact, ("5.2",)) or bare.startswith("强制年检"):
        return "inspect"
    if hits_section_key(compact, ("5.3",)) or bare.startswith("法律法规的获取") or t.startswith("法律法规的获取"):
        return "law"
    if hits_section_key(compact, ("5.4",)) or bare.startswith("企业标准和制度") or t.startswith("企业标准和制度"):
        return "std"
    if hits_section_key(compact, ("5.5",)) or bare.startswith("制度、标准执行") or bare.startswith("制度、标准") or t.startswith(
        "制度、标准"
    ):
        return "exec"
    if hits_section_key(compact, ("5.6",)) or bare.startswith("合规性评价") or t.startswith("合规性评价"):
        return "eval"
    return None


def _append_unique_para(paras: list[str], flow: list[dict[str, Any]], text: str) -> None:
    """同文档内连续重复句只留一句（材料里偶有双写「该步骤执行符合要求。」）。"""
    t = (text or "").strip()
    if not t:
        return
    if paras and paras[-1] == t:
        return
    paras.append(t)
    flow.append({"kind": "para", "text": t})


def _ch5_flow_target(ch5: dict[str, Any], sub: str) -> list[dict[str, Any]] | None:
    return {
        "special": ch5["special_flow"],
        "inspect": ch5["inspect_flow"],
        "law": ch5["law_flow"],
        "std": ch5["std_flow"],
        "exec": ch5["exec_flow"],
        "eval": ch5["eval_flow"],
        "summary": ch5["summary_flow"],
    }.get(sub)


_CH6_FOREIGN_TITLES = (
    "运维表现健康度",
    "运维表现",
    "风险隐患闭环",
    "风险隐患",
    "备件物资保障",
    "备件物资",
    "安全库存",
    "使用环境符合",
    "使用环境",
    "退运报废",
    "设备退运",
    "总结与建议",
    "生产计划执行",
    "设施设备运维质量",
)


def _should_parse_as_compliance(doc: DocumentModel, texts: list) -> bool:
    """判断是否当 ch5/ch6 合规稿解析。

    材料常无「6.x」标题：靠文件名与正文特征认。
    部门/线路「评估报告」即使正文出现「管理体系合规性」也不要整份灌进第6章。
    """
    name = _src(doc)
    joined = "\n".join(t for _, t, _ in texts)
    if any(k in name for k in ("合规性材料", "4&5", "5&6", "4＆5", "5＆6")):
        return True
    if "法律法规的获取情况" in joined and ("合规性评价" in joined or "制度、标准执行" in joined):
        return True
    if "修程修制" in joined and "对上一年度合规性" in joined:
        return True
    # 普通评估报告（维护部/号线）不进合规切段，避免把第7～10章吸进 intro
    if "评估报告" in name and "合规" not in name:
        return False
    return "管理体系合规性" in joined and (
        "法律法规的获取" in joined or "修程修制" in joined or "企业标准和制度" in joined
    )


def _is_ch6_exit_title(bare: str, compact: str, t: str) -> bool:
    """第6章内遇到其它章裸名/编号 → 退出，不再往 intro/revise 灌。"""
    if not _is_short_section_title(compact, 56):
        return False
    num = outline_num(compact) or ""
    if num.startswith(("7", "8", "9", "10", "11", "12")):
        return True
    if compact.startswith(("第7", "第8", "第9", "第七", "第八", "第九", "第十", "第十一", "第十二")):
        return True
    if is_chapter_or_appendix_title(compact) and not compact.startswith(("第5", "第6", "第五", "第六")):
        return True
    for key in _CH6_FOREIGN_TITLES:
        if bare.startswith(key) or compact.startswith(key) or t.startswith(key):
            return True
    return False


def _looks_like_ch6_count_table(rows: list[list[str]]) -> bool:
    """无标题时：规程分类/等级/多年份数量表 → 6.2。"""
    if not rows:
        return False
    head = "".join(str(c) for c in rows[0])
    return "等级" in head and bool(re.search(r"20\d{2}", head)) and (
        "2018" in head or "2017" in head or "专业" in head or "规程" in head
    )


def _looks_like_ch6_revise_table(rows: list[list[str]]) -> bool:
    """无标题时：名称+编号修订表 → 6.1。"""
    if not rows:
        return False
    head = "".join(str(c) for c in rows[0])
    return "名称" in head and "编号" in head


def _ch6_intro_polluted(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> bool:
    """intro 若已串进第7～10章内容，择优时应惩罚/丢弃。"""
    blob = "".join(str(x.get("text") or "") for x in (flow or []) if x.get("kind") == "para")
    blob += "".join(str(p) for p in (paras or []))
    return any(k in blob for k in _CH6_FOREIGN_TITLES) or "表7-" in blob or "表8-" in blob or "表10-" in blob


def _parse_one_compliance_doc(doc: DocumentModel) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """解析单份合规稿 → (ch5, ch6)。非合规稿返回 None。

    第6章对照去年体例：修程修制导语 → 对上一年度整改(+表) → 企业标准和制度(表6-1) → 小结。
    材料常无 6.x 编号：靠小节名与表特征判断归属。
    """
    texts = [(b.type, b.text or "", b) for b in doc.blocks]
    if not _should_parse_as_compliance(doc, texts):
        return None
    ch5 = _empty_ch5()
    ch6 = _empty_ch6()
    ch5["source"] = _src(doc)
    ch6["source"] = _src(doc)
    zone = "ch5"
    sub = ""
    for typ, text, block in texts:
        t = text.strip()
        if typ in {"drawing", "formula"}:
            item = _flow_item(doc, block)
            if not item:
                continue
            if zone == "ch5":
                if item.get("kind") == "drawing":
                    ch5["drawings"].append(item)
                target = _ch5_flow_target(ch5, sub)
                if target is not None:
                    target.append(item)
            elif zone == "ch6":
                if sub == "summary":
                    ch6["summary_flow"].append(item)
                elif sub == "intro":
                    # intro 只要短导语，图一般不进导语（去年第6章无图）
                    pass
                elif sub and sub != "count":
                    ch6["revise_flow"].append(item)
            continue
        if typ == "table" and block.rows:
            rows = [list(r) for r in block.rows]
            head = "".join(str(c) for c in rows[0])
            item = {"kind": "table", "rows": rows}
            # 无标题也能认：数量表→6.2，名称编号表在修程区内→6.1
            if _looks_like_ch6_count_table(rows):
                ch6["count_table"] = rows
                if zone == "ch6":
                    sub = "count"
                continue
            if zone == "ch6" and _looks_like_ch6_revise_table(rows) and sub != "count":
                if sub == "intro":
                    sub = "revise"
                ch6["tables"].append(rows)
                ch6["revise_flow"].append(item)
                continue
            if "等级" in head and re.search(r"20\d{2}", head):
                if "2018" in head or "2017" in head:
                    ch6["count_table"] = rows
                else:
                    ch5["std_table"] = rows
                    if zone == "ch5":
                        ch5["std_flow"].append(item)
            elif "名称" in head and "编号" in head:
                if zone == "ch5":
                    target = _ch5_flow_target(ch5, sub) or (
                        ch5["special_flow"] if "特种" in head or "规程" in head else None
                    )
                    if target is not None:
                        target.append(item)
                elif zone == "ch6" and sub != "count":
                    if sub == "intro":
                        sub = "revise"
                    ch6["tables"].append(rows)
                    ch6["revise_flow"].append(item)
            elif zone == "ch5":
                target = _ch5_flow_target(ch5, sub)
                if target is not None:
                    target.append(item)
            elif zone == "ch6" and sub == "summary":
                ch6["summary_flow"].append(item)
            elif zone == "ch6" and sub == "revise":
                ch6["revise_flow"].append(item)
                ch6["tables"].append(rows)
            # intro 下杂表不收，避免把后续章表灌进导语
            continue
        if not t:
            continue
        bare = _bare_heading(t)
        compact = compact_text(t)
        num = outline_num(compact) or ""
        # 第6章：别章裸名/编号一律退出
        if zone == "ch6" and _is_ch6_exit_title(bare, compact, t):
            zone = ""
            sub = ""
            continue
        if is_chapter_or_appendix_title(compact) or (
            is_outline_title_line(compact) and num and not num.startswith(("5", "6"))
        ):
            if num.startswith(("7", "8", "9", "10", "11", "12")) or compact.startswith(
                ("第7", "第8", "第9", "第七", "第八", "第九", "第十", "第十一", "第十二")
            ):
                zone = ""
                sub = ""
                continue
            if is_chapter_or_appendix_title(compact) and not compact.startswith(("第5", "第6", "第五", "第六")):
                zone = ""
                sub = ""
                continue
        if "评估小结" in t and len(t) < 40:
            sub = "summary"
            continue
        if (bare.startswith("修程修制") or t.startswith("修程修制")) and _is_short_section_title(compact):
            zone = "ch6"
            sub = "intro"
            continue
        if (
            "对上一年度合规性" in t
            or bare.startswith("对上一年度")
            or t.startswith("对上一年度")
            or (hits_section_key(compact, ("6.1",)) and "整改" in compact)
        ) and _is_short_section_title(compact, 64):
            zone = "ch6"
            sub = "revise"
            if "待提供" in t or "待完善" in t:
                ch6["incomplete"] = True
            continue
        # 无「6.2」标题时：短行「企业标准和制度」在修程章内 → 数量表区
        if zone == "ch6" and (
            bare.startswith("企业标准和制度") or t.startswith("企业标准和制度") or hits_section_key(compact, ("6.2",))
        ) and _is_short_section_title(compact):
            sub = "count"
            continue
        matched = _match_ch5_sub(bare, compact, t)
        if matched:
            if matched == "std" and zone == "ch6":
                sub = "count"
                continue
            zone = "ch5"
            sub = matched
            continue
        if bare.startswith("管理体系合规") or t.startswith("管理体系合规"):
            continue
        if not zone:
            continue
        if zone == "ch6":
            if sub == "count":
                continue
            if sub == "summary":
                _append_unique_para(ch6["summary_paras"], ch6["summary_flow"], t)
            elif sub == "intro":
                # 导语宜短；串台关键词直接停写 intro
                if any(k in t for k in _CH6_FOREIGN_TITLES):
                    zone = ""
                    sub = ""
                    continue
                if len(ch6["intro"]) >= 6:
                    continue
                _append_unique_para(ch6["intro"], ch6["intro_flow"], t)
            else:
                _append_unique_para(ch6["revise"], ch6["revise_flow"], t)
        else:
            if sub == "special":
                _append_unique_para(ch5["special"], ch5["special_flow"], t)
            elif sub == "inspect":
                _append_unique_para(ch5["inspect"], ch5["inspect_flow"], t)
            elif sub == "law":
                _append_unique_para(ch5["law"], ch5["law_flow"], t)
            elif sub == "std":
                _append_unique_para(ch5["std_paras"], ch5["std_flow"], t)
            elif sub == "exec":
                _append_unique_para(ch5["exec"], ch5["exec_flow"], t)
            elif sub == "eval":
                _append_unique_para(ch5["eval"], ch5["eval_flow"], t)
            elif sub == "summary":
                _append_unique_para(ch5["summary_paras"], ch5["summary_flow"], t)
    return ch5, ch6


_CH5_SECTION_KEYS = (
    ("special", "special_flow"),
    ("inspect", "inspect_flow"),
    ("law", "law_flow"),
    ("std_paras", "std_flow"),
    ("exec", "exec_flow"),
    ("eval", "eval_flow"),
    ("summary_paras", "summary_flow"),
)


def _pick_best_section(
    cands: list[dict[str, Any]],
    paras_key: str,
    flow_key: str,
) -> tuple[list[str], list[dict[str, Any]], str]:
    """多份合规材料同一小节只留最完整的一份，禁止叠写重复。

    intro 若串台（吸进第7～10章）直接跳过；合规性材料文件名加分。
    """
    best_paras: list[str] = []
    best_flow: list[dict[str, Any]] = []
    best_src = ""
    best_score = -1
    best_sig = ""
    for cand in cands:
        flow = list(cand.get(flow_key) or [])
        paras = list(cand.get(paras_key) or [])
        if not flow and not paras:
            continue
        if paras_key == "intro" and _ch6_intro_polluted(flow, paras):
            continue
        sig = _flow_text_sig(flow, paras)
        score = _section_richness(flow, paras)
        src = cand.get("source") or ""
        if "合规性材料" in src or "4&5" in src or "5&6" in src:
            score = score * 10 + 50
        else:
            score = score * 10
        # intro 宜短：过长扣分
        if paras_key == "intro" and len(paras) > 8:
            score -= (len(paras) - 8) * 5
        if score > best_score or (score == best_score and sig and sig != best_sig and len(sig) > len(best_sig)):
            best_score = score
            best_paras = paras
            best_flow = flow
            best_src = src
            best_sig = sig
    return best_paras, best_flow, best_src


def _merge_compliance_candidates(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    ch5 = _empty_ch5()
    ch6 = _empty_ch6()
    if not pairs:
        return ch5, ch6
    ch5_cands = [p[0] for p in pairs]
    ch6_cands = [p[1] for p in pairs]
    # source：取贡献小节最多的文档
    def _cand_weight(c: dict[str, Any]) -> int:
        return sum(_section_richness(c.get(fk), c.get(pk)) for pk, fk in _CH5_SECTION_KEYS)

    best_doc = max(ch5_cands, key=_cand_weight)
    ch5["source"] = best_doc.get("source") or ""
    ch6["source"] = max(ch6_cands, key=lambda c: len(c.get("revise") or []) + len(c.get("tables") or [])).get(
        "source"
    ) or ch5["source"]

    for paras_key, flow_key in _CH5_SECTION_KEYS:
        paras, flow, src = _pick_best_section(ch5_cands, paras_key, flow_key)
        flow = dedupe_flow_items(flow)
        paras = dedupe_texts(paras) or [
            str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        ch5[paras_key] = paras
        ch5[flow_key] = flow
        if paras_key == "special" and flow:
            ch5["special_source"] = src
            ch5["special_via"] = "year"
        if paras_key == "inspect" and flow:
            ch5["inspect_source"] = src
            ch5["inspect_via"] = "year"

    # 表 / 图桶：合并去重（图按 source_index）
    seen_draw: set[tuple[str, int]] = set()
    for c in ch5_cands:
        if c.get("std_table") and (not ch5["std_table"] or len(c["std_table"]) > len(ch5["std_table"])):
            ch5["std_table"] = c["std_table"]
        for d in c.get("drawings") or []:
            key = (str(d.get("source_path") or ""), int(d.get("source_index") or -1))
            if key in seen_draw:
                continue
            seen_draw.add(key)
            ch5["drawings"].append(d)

    # ch6：先定 6.1；导语只认同源材料，不跨文档借（避免 5&6 无导语却抄来 4&5 闲文）
    revise_paras, revise_flow, revise_src = _pick_best_section(ch6_cands, "revise", "revise_flow")
    ch6["revise"] = dedupe_texts(revise_paras) or [
        str(x.get("text") or "") for x in revise_flow if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ]
    ch6["revise_flow"] = dedupe_flow_items(revise_flow)

    same_src = [c for c in ch6_cands if (c.get("source") or "") == revise_src]
    # 无 6.1 时才在今年候选里择优导语
    intro_pool = same_src if revise_src else ch6_cands
    if intro_pool and any((c.get("intro") or c.get("intro_flow")) for c in intro_pool):
        paras, flow, intro_src_name = _pick_best_section(intro_pool, "intro", "intro_flow")
        ch6["intro_flow"] = dedupe_flow_items(flow)
        ch6["intro"] = dedupe_texts(paras) or [
            str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        ch6["intro_via"] = "year"
        ch6["intro_source"] = intro_src_name or revise_src
    else:
        ch6["intro"] = []
        ch6["intro_flow"] = []
        ch6["intro_via"] = ""
        ch6["intro_source"] = ""

    for paras_key, flow_key in (("summary_paras", "summary_flow"),):
        pool = same_src if any((c.get(paras_key) or c.get(flow_key)) for c in same_src) else ch6_cands
        paras, flow, _src_name = _pick_best_section(pool, paras_key, flow_key)
        flow = dedupe_flow_items(flow)
        paras = dedupe_texts(paras) or [
            str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        ch6[paras_key] = paras
        ch6[flow_key] = flow

    ch6["incomplete"] = False
    for c in ch6_cands:
        if (c.get("source") or "") == revise_src and c.get("incomplete"):
            ch6["incomplete"] = True
    # 数量表：优先合规性材料中更完整的一份
    count_cands = [c for c in ch6_cands if c.get("count_table")]
    if count_cands:

        def _count_score(c: dict[str, Any]) -> tuple[int, int]:
            name = c.get("source") or ""
            pref = 1 if ("合规" in name or "5&6" in name or "4&5" in name) else 0
            return pref, len(c.get("count_table") or [])

        ch6["count_table"] = max(count_cands, key=_count_score)["count_table"]
    # 整改表：与 revise 同源优先
    pool = same_src or ch6_cands
    best_tables = max(pool, key=lambda c: len(c.get("tables") or []))
    ch6["tables"] = list(best_tables.get("tables") or [])
    if best_tables.get("revise_flow") and not ch6["revise_flow"]:
        ch6["revise_flow"] = dedupe_flow_items(best_tables.get("revise_flow") or [])
        ch6["revise"] = dedupe_texts(best_tables.get("revise") or [])
    if revise_src:
        ch6["source"] = revise_src
    return ch5, ch6


def _slice_prior_ch5_section(
    prior_docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...],
) -> dict[str, Any]:
    return slice_named_section(
        prior_docs,
        start_keys=start_keys,
        stop_keys=stop_keys,
        build_item=_flow_item,
        source_name=_src,
    )


def _looks_like_ch6_chapter_intro(paras: list[str] | None) -> bool:
    """章导语：短散文；排除目录条目（检查企业…）和串台。"""
    paras = [str(p).strip() for p in (paras or []) if str(p).strip()]
    if not paras or _ch6_intro_polluted(None, paras):
        return False
    if len(paras) > 4:
        return False
    blob = "".join(paras)
    if blob.count("（") >= 3 and "检查企业" in blob:
        return False
    if "评估小结" in blob or blob.startswith("本年度对修程"):
        return False
    return any(len(p) >= 12 for p in paras)


def _extract_prior_ch6_intro(prior_docs: list[DocumentModel] | None) -> dict[str, Any]:
    """从去年报告取「6 修程修制」标题下、6.1 之前的短导语（跳过目录里的同名项）。"""
    empty: dict[str, Any] = {"paras": [], "flow": [], "source": ""}
    candidates: list[tuple[int, dict[str, Any]]] = []
    for doc in prior_docs or []:
        blocks = list(doc.blocks or [])
        for i, block in enumerate(blocks):
            t = (block.text or "").strip()
            if not t:
                continue
            bare = _bare_heading(t)
            compact = compact_text(t)
            if not (
                (bare.startswith("修程修制") or t.startswith("修程修制") or "修程修制匹配性评估" in t)
                and _is_short_section_title(compact, 48)
            ):
                continue
            paras: list[str] = []
            flow: list[dict[str, Any]] = []
            toc_like = False
            hit_61 = False
            for b2 in blocks[i + 1 :]:
                t2 = (b2.text or "").strip()
                if b2.type == "table":
                    break
                if not t2:
                    continue
                bare2 = _bare_heading(t2)
                compact2 = compact_text(t2)
                if (
                    "对上一年度合规性" in t2
                    or bare2.startswith("对上一年度")
                    or (hits_section_key(compact2, ("6.1",)) and ("整改" in compact2 or "合规" in compact2))
                ):
                    hit_61 = True
                    break
                if (
                    bare2.startswith("企业标准和制度")
                    or hits_section_key(compact2, ("6.2", "6.3"))
                    or "评估小结" in t2
                    or _is_ch6_exit_title(bare2, compact2, t2)
                ):
                    break
                if t2.startswith("（") and ("检查企业" in t2 or "维护维修" in t2):
                    toc_like = True
                    break
                if len(paras) >= 3:
                    break
                _append_unique_para(paras, flow, t2)
            if toc_like or not hit_61 or not _looks_like_ch6_chapter_intro(paras):
                continue
            blob = "".join(paras)
            score = len(blob)
            if "根据生产需求" in blob or "上级要求" in blob:
                score += 500
            candidates.append((score, {"paras": paras, "flow": flow, "source": _src(doc)}))
    if not candidates:
        return empty
    return max(candidates, key=lambda x: x[0])[1]


def _resolve_ch6_intro_from_prior(ch6: dict[str, Any], prior_docs: list[DocumentModel] | None) -> None:
    """大标题下导语：今年同源材料有则用；没有则用去年评估报告同位置。"""
    year_ok = _looks_like_ch6_chapter_intro(ch6.get("intro")) and not _ch6_intro_polluted(
        ch6.get("intro_flow"), ch6.get("intro")
    )
    if year_ok:
        ch6["intro_via"] = ch6.get("intro_via") or "year"
        return
    ch6["intro"] = []
    ch6["intro_flow"] = []
    ch6["intro_via"] = ""
    if not prior_docs:
        return
    hit = _extract_prior_ch6_intro(prior_docs)
    if not hit.get("paras"):
        return
    ch6["intro"] = list(hit["paras"])
    ch6["intro_flow"] = list(hit.get("flow") or [{"kind": "para", "text": p} for p in hit["paras"]])
    ch6["intro_via"] = "prior"
    ch6["intro_source"] = hit.get("source") or ""


def _resolve_ch51_ch52_from_prior(ch5: dict[str, Any], prior_docs: list[DocumentModel] | None) -> None:
    """5.1/5.2：今年材料体例不够（无表/无图）则复用去年完整报告同节（含图）。"""
    if not prior_docs:
        return
    if not _looks_like_ch51(ch5.get("special_flow"), ch5.get("special")):
        hit = _slice_prior_ch5_section(
            prior_docs,
            start_keys=("5.1", "特种设备、消防、防雷规程", "特种设备、消防、防雷", "特种设备、消防"),
            stop_keys=("5.2", "强制年检", "法律法规的获取", "5.3"),
        )
        if section_has_body(hit) and _looks_like_ch51(hit.get("flow"), hit.get("paras")):
            ch5["special"] = hit["paras"]
            ch5["special_flow"] = hit["flow"]
            ch5["special_source"] = hit["source"]
            ch5["special_via"] = "prior"
            ch5["source"] = ch5["source"] or hit["source"]
    if not _looks_like_ch52(ch5.get("inspect_flow"), ch5.get("inspect")):
        hit = _slice_prior_ch5_section(
            prior_docs,
            start_keys=("5.2", "强制年检或评估情况分析", "强制年检"),
            stop_keys=("5.3", "法律法规的获取", "企业标准和制度", "5.4"),
        )
        if section_has_body(hit) and _looks_like_ch52(hit.get("flow"), hit.get("paras")):
            ch5["inspect"] = hit["paras"]
            ch5["inspect_flow"] = hit["flow"]
            ch5["inspect_source"] = hit["source"]
            ch5["inspect_via"] = "prior"
            ch5["source"] = ch5["source"] or hit["source"]


def extract_compliance(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """第 5、6 章：从合规性材料按小标题切段。

    - 多份合规稿同一小节只保留最完整的一份（禁止 4&5 + 5&6 叠成两遍正文）。
    - 5.1/5.2：今年体例不足时复用去年报告同节（含表/图）；其它数据节不用去年顶。
    - 图进对应小节 flow，成文按 flow 回拷。
    """
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for doc in docs or []:
        if _is_line_report(doc):
            continue
        parsed = _parse_one_compliance_doc(doc)
        if parsed:
            pairs.append(parsed)
    ch5, ch6 = _merge_compliance_candidates(pairs)
    _resolve_ch51_ch52_from_prior(ch5, prior_docs)
    _resolve_ch6_intro_from_prior(ch6, prior_docs)
    # 再扫一遍：prior 回填或材料内双份粘贴
    for paras_key, flow_key in _CH5_SECTION_KEYS:
        ch5[flow_key] = dedupe_flow_items(ch5.get(flow_key))
        ch5[paras_key] = dedupe_texts(ch5.get(paras_key)) or [
            str(x.get("text") or "")
            for x in (ch5.get(flow_key) or [])
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
    for paras_key, flow_key in (("intro", "intro_flow"), ("revise", "revise_flow"), ("summary_paras", "summary_flow")):
        ch6[flow_key] = dedupe_flow_items(ch6.get(flow_key))
        ch6[paras_key] = dedupe_texts(ch6.get(paras_key)) or [
            str(x.get("text") or "")
            for x in (ch6.get(flow_key) or [])
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]

    # 合规稿里没切到小结时，再按名字扫一遍今年材料（给了就要用）。
    if not section_has_body({"paras": ch5["summary_paras"], "flow": ch5["summary_flow"]}):
        hit = extract_named_section(
            docs,
            start_keys=("评估小结",),
            stop_keys=("修程修制", "第6章", "第六章"),
            after_keys=("合规性评价", "管理体系合规", "法律法规的获取"),
        )
        if section_has_body(hit):
            ch5["summary_paras"] = hit["paras"]
            ch5["summary_flow"] = hit["flow"]
            ch5["summary_source"] = hit["source"]
    if not section_has_body({"paras": ch6["summary_paras"], "flow": ch6["summary_flow"]}):
        hit = extract_named_section(
            docs,
            start_keys=("评估小结",),
            stop_keys=("第7章", "第七章", "运维表现"),
            after_keys=("修程修制", "对上一年度合规性"),
        )
        if section_has_body(hit):
            ch6["summary_paras"] = hit["paras"]
            ch6["summary_flow"] = hit["flow"]
            ch6["summary_source"] = hit["source"]
    return {"ch5": ch5, "ch6": ch6}


def extract_stock(docs: list[DocumentModel]) -> dict[str, Any]:
    """第 9 章表 9-1：优先备件清单 Word/Excel；没有表才退回库存管理规定 PDF。跳过线路报告和触网表。"""
    preferred: dict[str, Any] | None = None
    from_rule: dict[str, Any] | None = None
    seen: set[str] = set()
    for doc in docs or []:
        if _is_line_report(doc):
            continue
        name = _src(doc)
        if name in seen:
            continue
        seen.add(name)
        is_rule = "管理规定" in name or (_is_pdf(doc) and _pdf_topic(doc) == "stock_rule")
        flow: list[dict[str, Any]] = []
        table: list[list[str]] = []
        table_vmerge: list[list[int]] | None = None
        extra_tables: list[list[list[str]]] = []
        for block in doc.blocks:
            if block.type in {"drawing", "formula"}:
                item = _flow_item(doc, block)
                if item:
                    flow.append(item)
                continue
            if block.type == "table" and block.rows:
                kind = _stock_table_kind(block.rows)
                # 接触网备件表不进供电第 9 章。
                if kind == "overhead":
                    continue
                item = _table_item(block, doc)
                if kind == "power" and not table:
                    table = item["rows"]
                    if "vmerge" in item:
                        table_vmerge = item["vmerge"]
                    flow.append(item)
                elif kind == "power" and table:
                    extra_tables.append(item["rows"])
                    flow.append(item)
                continue
            t = (block.text or "").strip()
            if _is_caption_text(t):
                flow.append({"kind": "para", "text": t})
        payload: dict[str, Any] = {
            "source": name,
            "table": table,
            "flow": flow,
            "extra_tables": extra_tables,
        }
        if table_vmerge is not None:
            payload["vmerge"] = table_vmerge
        if is_rule:
            if table:
                from_rule = payload
            continue
        if table:
            preferred = payload
            if "备件" in name:
                return preferred
        elif any(k in name for k in ("备件", "库存")) and flow and not preferred:
            preferred = payload
    return preferred or from_rule or {"source": "", "table": [], "flow": [], "extra_tables": []}


def enrich_stock_pack(docs: list[DocumentModel] | None, pack: dict[str, Any]) -> dict[str, Any]:
    """9.2 备品备件更新、9.3 小结：有材料就抽，没有空着。"""
    out = dict(pack or {})
    out["update"] = extract_named_section(
        docs,
        start_keys=("备品备件更新", "全网备品备件更新", "备件更新情况"),
        stop_keys=("评估小结", "使用环境", "第10章", "第十章"),
    )
    out["summary"] = extract_named_section(
        docs,
        start_keys=("评估小结",),
        stop_keys=("使用环境", "第10章", "第十章", "退运"),
        after_keys=("安全库存", "备品备件更新", "备件物资"),
    )
    return out


_RETIRE_TITLE = re.compile(
    r"(退运更换|设备退运|报废的情况说明|情况说明)$|^(关于).{0,40}(报废|退运)"
)
_RETIRE_FOOTER = re.compile(r"^(综上所述|上海地铁维护保障|申通地铁)")
_RETIRE_REPORT_BOILER = re.compile(
    r"^根据上海城市轨道交通设施设备运营评估规范|^根据《城市轨道交通设施设备日常维护"
)
_RETIRE_REPORT_STOP = (
    "评估结论",
    "总结与建议",
    "对上一周期",
    "评估小结",
    "第12章",
    "第十二章",
    "12.1",
    "12.2",
)


_CN_LINE_NO = {
    "十八": 18,
    "十七": 17,
    "十六": 16,
    "十五": 15,
    "十四": 14,
    "十三": 13,
    "十二": 12,
    "十一": 11,
    "十": 10,
    "九": 9,
    "八": 8,
    "七": 7,
    "六": 6,
    "五": 5,
    "四": 4,
    "三": 3,
    "二": 2,
    "一": 1,
}


def _retire_line_nos_in_text(text: str) -> list[int]:
    """正文/标题里的号线（含「十号线」等中文数字）。"""
    t = text or ""
    out: list[int] = [int(x) for x in re.findall(r"(\d+)\s*号线", t)]
    for cn, num in _CN_LINE_NO.items():
        if f"{cn}号线" in t:
            out.append(num)
    return list(dict.fromkeys(out))


def _retire_line_no(text: str) -> int | None:
    nos = _retire_line_nos_in_text(text)
    return nos[0] if nos else None


def _is_project_overview_label(text: str) -> bool:
    t = (text or "").strip()
    if t in {"概述", "工程概述", "工程概况", "报废原因", "设备报废"}:
        return True
    if re.match(r"^[一二三四五六七八九十\d]+[、．.]\s*(工程概述|工程概况|概述)$", t):
        return True
    if re.match(r"^[一二三四五六七八九十\d]+[、．.]\s*(设备报废|报废原因|报废情况)$", t):
        return True
    return False


def _is_project_overview_body(text: str) -> bool:
    """无报废要点的工程背景叙述，不进 11.1 正文。"""
    t = (text or "").strip()
    if not t or any(k in t for k in ("需报废", "设计使用年限", "暂无退运", "申请报废")):
        return False
    if "报废" in t and any(k in t for k in ("台", "套", "项", "原值")):
        return False
    if re.search(r"工程概述|接轨改造|西延伸工程|提质增效|移梁接驳|专项规划|枢纽连接", t) and len(t) > 40:
        return True
    if re.search(r"改建、新建范围|车站站厅、站台公共区", t) and len(t) > 40:
        return True
    if t.startswith("涉及") and "工程" in t and len(t) > 40:
        return True
    return False


def _is_prior_retire_path(path: str, year: int) -> bool:
    """报废说明目录常按申请年分文件夹：当年与上一年都收，更早的不要。"""
    m = re.search(r"[\\/](20\d{2})[\\/]", (path or "").replace("/", "\\"))
    if not m:
        return False
    folder_year = int(m.group(1))
    return folder_year < int(year) - 1


def _retire_skip_name(name: str) -> bool:
    """工器具/仪器仪表进 11.2；文件名带供电的说明仍可进 11.1。"""
    if any(k in name for k in RETIRE_SKIP) and "供电" not in name:
        return True
    return False


def _is_retire_section_title(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) >= 80:
        return False
    if t.endswith("退运更换") or t.endswith("报废") or "设备退运" in t:
        return True
    if t.startswith("关于") and ("报废" in t or "退运" in t):
        return True
    return bool(_RETIRE_TITLE.search(t))


def _is_retire_noise_para(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t in {"概述", "报废原因"}:
        return True
    if _RETIRE_FOOTER.search(t):
        return True
    if re.fullmatch(r"\d{4}年\d{1,2}月\d{1,2}日", t):
        return True
    return False


def _filter_retire_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """去掉汇编里的工程「概述」铺垫、落款日期；保留报废原因与设备说明。"""
    out: list[dict[str, Any]] = []
    skipping_overview = False
    for item in flow or []:
        kind = item.get("kind")
        if kind != "para":
            if not skipping_overview:
                out.append(item)
            continue
        text = str(item.get("text") or "").strip()
        if text in {"概述"} or (text.startswith("概述") and len(text) <= 6):
            skipping_overview = True
            continue
        if text in {"报废原因"} or (text.startswith("报废原因") and len(text) <= 8):
            skipping_overview = False
            continue
        if skipping_overview:
            if any(k in text for k in ("需报废", "报废", "设计使用年限", "申请报废")):
                skipping_overview = False
            else:
                continue
        if _is_retire_noise_para(text):
            continue
        out.append(item)
    return dedupe_flow_items(out)


def _parse_retire_docs(docs: list[DocumentModel]) -> tuple[str, list[dict[str, Any]]]:
    """按「…退运更换 / 报废」小标题切开。工器具/仪器仪表标题丢掉；空调等按材料收。"""
    sections: list[dict[str, Any]] = []
    source = ""
    for doc in docs or []:
        name = _src(doc)
        if _retire_skip_name(name):
            continue
        blocks = [
            b
            for b in doc.blocks
            if b.type in {"drawing", "formula", "table"}
            or (b.type in {"heading", "paragraph"} and (b.text or "").strip())
        ]
        if not any("退运" in (b.text or "") or "报废" in (b.text or "") for b in blocks):
            if "报废" not in name and "退运" not in name:
                continue
        source = source or name
        cur = None
        skipping_overview = False
        for block in blocks:
            if block.type in {"drawing", "formula"}:
                if cur is not None and not skipping_overview:
                    item = _flow_item(doc, block)
                    if item:
                        cur.setdefault("flow", []).append(item)
                continue
            if block.type == "table":
                if cur is not None and not skipping_overview:
                    cur.setdefault("flow", []).append(_table_item(block, doc))
                continue
            t = block.text.strip()
            title_skip = _retire_skip_name(t)
            if _is_retire_section_title(t):
                if title_skip:
                    cur = None
                    skipping_overview = False
                    continue
                cur = {
                    "title": t,
                    "paras": [],
                    "flow": [],
                    "source": name,
                    "source_path": doc.source_path or "",
                }
                sections.append(cur)
                skipping_overview = False
                continue
            if cur is None or title_skip:
                continue
            compact = compact_text(t)
            if is_foreign_outline(compact) or hits_section_key(
                compact,
                ("评估小结", "第12章", "第十二章", "总结与建议", "12.1", "12.2"),
                title_only_words=True,
            ):
                cur = None
                skipping_overview = False
                continue
            if _is_project_overview_label(t):
                # 「概述/概况」开始跳过；「报废原因/设备报废」结束跳过
                skipping_overview = ("概述" in t) or ("概况" in t)
                continue
            if skipping_overview:
                if any(k in t for k in ("需报废", "设计使用年限")) and not _is_project_overview_body(t):
                    skipping_overview = False
                else:
                    continue
            if _is_project_overview_body(t):
                continue
            if _is_retire_noise_para(t):
                continue
            if cur.get("paras") and cur["paras"][-1] == t:
                continue
            cur["paras"].append(t)
            cur.setdefault("flow", []).append({"kind": "para", "text": t})
        # 整份报废说明没有小标题时，用文件名当段
        if not any(s.get("source") == name for s in sections) and blocks:
            paras = []
            flow: list[dict[str, Any]] = []
            for block in blocks:
                if block.type == "table":
                    flow.append(_table_item(block, doc))
                    continue
                if block.type in {"drawing", "formula"}:
                    item = _flow_item(doc, block)
                    if item:
                        flow.append(item)
                    continue
                t = (block.text or "").strip()
                if not t or _is_retire_section_title(t) or _is_retire_noise_para(t):
                    continue
                paras.append(t)
                flow.append({"kind": "para", "text": t})
            if paras or flow:
                sections.append(
                    {
                        "title": name,
                        "paras": paras,
                        "flow": flow,
                        "source": name,
                        "source_path": doc.source_path or "",
                    }
                )
    best_by_key: dict[str, dict[str, Any]] = {}
    for sec in sections:
        title = compact_text(str(sec.get("title") or "")) or "sec"
        # 同名说明可能分属申请年文件夹（如 2025/2026），都要留，按线合并时再去重
        key = f"{title}|{compact_text(str(sec.get('source') or ''))}|{compact_text(str((sec.get('paras') or [''])[0])[:48])}"
        prev = best_by_key.get(key)
        score = _section_richness(sec.get("flow"), sec.get("paras"))
        if prev is None or score > _section_richness(prev.get("flow"), prev.get("paras")):
            sec = dict(sec)
            sec["flow"] = _filter_retire_flow(dedupe_flow_items(sec.get("flow")))
            sec["paras"] = [
                str(x.get("text") or "")
                for x in (sec.get("flow") or [])
                if x.get("kind") == "para" and str(x.get("text") or "").strip()
            ]
            best_by_key[key] = sec
    return source, [s for s in best_by_key.values() if s.get("paras") or s.get("flow")]


def _retire_folder_year(path: str) -> int | None:
    m = re.search(r"[\\/](20\d{2})[\\/]", (path or "").replace("/", "\\"))
    return int(m.group(1)) if m else None


def _retire_path_preference(path: str, name: str) -> tuple[int, int, int]:
    """同名材料多份时：正式编制材料优先于「4月份」备份夹；非汇编优先。"""
    p = (path or "").replace("/", "\\")
    # 越小越优先
    april = 1 if "4月份" in p else 0
    compiled = 1 if "11退运" in (name or "") else 0
    # 路径越短通常越接近正式目录
    return (april, compiled, len(p))


def _collect_retire_primary_docs(docs: list[DocumentModel] | None, year: int) -> list[DocumentModel]:
    """11退运汇编 + 当年报废/退运说明；跳过往年文件夹与线路整篇报告。

    材料包常同时塞「正式编制材料」和「4月份」两套相同报废说明——同名同申请年只留一份。
    """
    candidates: list[DocumentModel] = []
    seen_path: set[str] = set()
    for doc in docs or []:
        name = doc.source_name or ""
        path = doc.source_path or ""
        key = f"{path}|{name}"
        if key in seen_path:
            continue
        if _is_prior_retire_path(path, year):
            continue
        if _is_line_report(doc):
            continue
        if "评估报告" in name:
            continue
        if "11退运" not in name and "报废" not in name and "退运" not in name:
            continue
        if _retire_skip_name(name):
            continue
        seen_path.add(key)
        candidates.append(doc)

    # 同文件名 + 同申请年文件夹：只留最优先的一份（正式目录优于 4月份备份）
    best: dict[tuple[str, int | None], DocumentModel] = {}
    for doc in candidates:
        name = doc.source_name or ""
        path = doc.source_path or ""
        slot = (compact_text(name), _retire_folder_year(path))
        prev = best.get(slot)
        if prev is None or _retire_path_preference(path, name) < _retire_path_preference(
            prev.source_path or "", prev.source_name or ""
        ):
            best[slot] = doc
    return list(best.values())


def _is_retire_report_stop(text: str) -> bool:
    t = compact_text(text or "")
    if not t:
        return False
    if hits_section_key(t, _RETIRE_REPORT_STOP, title_only_words=True):
        return True
    if is_foreign_outline(t):
        return True
    if t.startswith("评估结论") or t.startswith("十一、") or t.startswith("十二、"):
        return True
    return False


def _retire_bits_from_reports(docs: list[DocumentModel] | None, year: int) -> dict[int, list[dict[str, Any]]]:
    """从各线/专业评估报告只切「退运报废倾向性评估」正文，按号线归入。"""
    by_line: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for doc in docs or []:
        name = _src(doc)
        path = doc.source_path or ""
        if "评估报告" not in name:
            continue
        if _is_prior_retire_path(path, year):
            continue
        blocks = [
            b
            for b in doc.blocks
            if b.type in {"drawing", "formula", "table"}
            or (b.type in {"heading", "paragraph"} and (b.text or "").strip())
        ]
        i = 0
        while i < len(blocks):
            t = (blocks[i].text or "").strip()
            if "退运报废倾向性评估" not in compact_text(t):
                i += 1
                continue
            if "不写" in t:
                break
            i += 1
            chunk: list[dict[str, Any]] = []
            while i < len(blocks):
                b = blocks[i]
                t2 = (b.text or "").strip()
                if b.type in {"heading", "paragraph"} and t2 and _is_retire_report_stop(t2):
                    break
                if b.type == "table":
                    chunk.append(_table_item(b, doc))
                elif b.type in {"drawing", "formula"}:
                    item = _flow_item(doc, b)
                    if item:
                        chunk.append(item)
                elif t2 and t2 != "退运报废倾向性评估" and not _RETIRE_REPORT_BOILER.match(t2):
                    if not _is_retire_noise_para(t2):
                        chunk.append({"kind": "para", "text": t2, "source": name})
                i += 1
            name_lines = _retire_line_nos_in_text(name)
            for item in chunk:
                text = str(item.get("text") or "")
                body_lines = _retire_line_nos_in_text(text)
                targets = body_lines or name_lines
                if not targets:
                    continue
                for ln in targets:
                    if 1 <= ln <= 18:
                        by_line[ln].append(dict(item))
            break
    return by_line


def _retire_sec_rank(sec: dict[str, Any]) -> tuple[int, int, int]:
    """供电类优先；同组按申请年升序（上年申请在前）；再按内容多少。"""
    title = str(sec.get("title") or "")
    if any(k in title for k in ("空调", "起重", "打印")):
        bucket = 2
    elif any(k in title for k in ("供电", "正线", "变压器", "短路器", "综保", "开关")):
        bucket = 0
    else:
        bucket = 1
    path = str(sec.get("source_path") or sec.get("source") or "")
    ym = re.search(r"[\\/](20\d{2})[\\/]", path.replace("/", "\\"))
    year_hint = int(ym.group(1)) if ym else 9999
    return (bucket, year_hint, -_section_richness(sec.get("flow"), sec.get("paras")))


def _retire_para_core(text: str) -> str:
    """去掉原值数字、条号前缀后再比，避免「有原值 / 无原值」两套稿并存。"""
    t = compact_text(text or "")
    t = re.sub(r"原值共计[\d,.]+元", "", t)
    t = re.sub(r"原值为[\d,.]+元", "", t)
    t = re.sub(r"[，,]{1,2}(?=[。．])", "", t)
    t = re.sub(r"^[1-9一二三四五六七八九十]+[、.．]", "", t)
    return t


def _retire_scrap_lead_key(text: str) -> str | None:
    """同一批「X号线需报废…」开段指纹；用于丢掉汇编与说明的重复稿。"""
    t = _retire_para_core(text)
    head = re.split(r"[。；;]", t, maxsplit=1)[0]
    head = re.sub(r"[、，,．：:()（）\s]", "", head)
    if not head:
        return None
    if "需报废" in head or ("报废" in head and re.search(r"\d+台", head)):
        return head[:80]
    # 起重机等：首句即「X号线…N台…」
    if re.search(r"\d+号线", head) and re.search(r"\d+台", head) and len(head) >= 16:
        return head[:80]
    return None


def _dedupe_contained_retire_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """去掉被更长段完全覆盖的短段（同批有/无原值的重复说明）。"""
    items = list(flow or [])
    para_idxs = [i for i, x in enumerate(items) if x.get("kind") == "para"]
    raw = {i: str(items[i].get("text") or "") for i in para_idxs}
    cores = {i: _retire_para_core(raw[i]) for i in para_idxs}
    drop: set[int] = set()
    for i in para_idxs:
        ti = cores[i]
        if not ti:
            drop.add(i)
            continue
        for j in para_idxs:
            if i == j or j in drop:
                continue
            tj = cores[j]
            if ti != tj and ti in tj and len(ti) < len(tj):
                drop.add(i)
                break
            # 核心相同：留更长 / 带原值的
            if ti == tj and i != j:
                ri, rj = raw[i], raw[j]
                if ("原值" in rj and "原值" not in ri) or (len(rj) > len(ri) + 4):
                    drop.add(i)
                    break
    for i in para_idxs:
        if i in drop:
            continue
        lead_i = _retire_scrap_lead_key(raw[i])
        if not lead_i:
            continue
        for j in para_idxs:
            if i == j or j in drop:
                continue
            lead_j = _retire_scrap_lead_key(raw[j])
            if lead_i != lead_j:
                continue
            # 同批开段：无原值让给有原值；同有原值留更长
            ri, rj = raw[i], raw[j]
            if "原值" in rj and "原值" not in ri:
                drop.add(i)
                break
            if "原值" in ri and "原值" not in rj:
                continue
            if len(cores[j]) > len(cores[i]) + 6:
                drop.add(i)
                break
    for i in para_idxs:
        ti = cores[i]
        if not ti or i in drop:
            continue
        for j in para_idxs:
            if i == j or j in drop:
                continue
            tj = cores[j]
            if len(ti) > 36 and len(tj) > 36 and ti[:36] == tj[:36] and len(tj) > len(ti) + 8:
                drop.add(i)
                break
            if (
                len(ti) > 28
                and len(tj) > 28
                and ti[:28] == tj[:28]
                and "原值" in raw[j]
                and "原值" not in raw[i]
            ):
                drop.add(i)
                break
    return dedupe_flow_items([x for i, x in enumerate(items) if i not in drop])


def _retire_leads_equivalent(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    # 「安装在…站」细节不同但同批空调/设备
    aa = re.split(r"安装在", a, maxsplit=1)[0]
    bb = re.split(r"安装在", b, maxsplit=1)[0]
    return bool(aa and aa == bb and len(aa) >= 14)


def _collapse_similar_retire_secs(secs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一线路多份来源：开段同批设备只留一份（单份报废说明优先于 11退运汇编）。"""
    ranked = sorted(
        secs,
        key=lambda s: (
            0 if "11退运" not in str(s.get("source") or "") else 1,
            0 if any("原值" in str(p) for p in (s.get("paras") or [])) else 1,
            -sum(len(str(p)) for p in (s.get("paras") or [])),
            -_section_richness(s.get("flow"), s.get("paras")),
        ),
    )
    kept: list[dict[str, Any]] = []
    seen_leads: list[str] = []
    for sec in ranked:
        first = str((sec.get("paras") or [""])[0] or "")
        lead = _retire_scrap_lead_key(first) or (_retire_para_core(first)[:48] if first else "")
        if lead and any(_retire_leads_equivalent(lead, x) for x in seen_leads):
            continue
        if lead:
            seen_leads.append(lead)
        kept.append(sec)
    return kept


def _merge_line_retire_flows(secs: list[dict[str, Any]], extra: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    flow: list[dict[str, Any]] = []
    for sec in sorted(_collapse_similar_retire_secs(secs), key=_retire_sec_rank):
        flow.extend(_filter_retire_flow(sec.get("flow")))
    if extra:
        flow.extend(_filter_retire_flow(extra))
    return _dedupe_contained_retire_flow(flow)


def _retire_flow_is_empty(flow: list[dict[str, Any]] | None, paras: list[str] | None = None) -> bool:
    texts = [
        str(x.get("text") or "").strip()
        for x in (flow or [])
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ] or [str(p).strip() for p in (paras or []) if str(p).strip()]
    if not texts:
        return True
    if len(texts) == 1 and texts[0] in {"无", "无。", "暂无", "/", "——"}:
        return True
    return False


def _is_weak_retire_report_para(text: str) -> bool:
    t = (text or "").strip()
    return any(k in t for k in ("无欠修", "未存在欠修", "暂无退运报废", "无退运报废"))


def extract_retire(docs: list[DocumentModel], *, year: int = 2026) -> dict[str, Any]:
    """第 11 章：报废/退运材料按 1～18 号线汇总成 11.1.x；缺线再补评估报告退运段。"""
    primary = _collect_retire_primary_docs(docs, year)
    source, raw_sections = _parse_retire_docs(primary)
    by_line: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for sec in raw_sections:
        ln = _retire_line_no(str(sec.get("title") or "")) or _retire_line_no(str(sec.get("source") or ""))
        if ln and 1 <= ln <= 18:
            by_line[ln].append(sec)
    report_bits = _retire_bits_from_reports(docs, year)
    sections: list[dict[str, Any]] = []
    src_names: list[str] = []
    for i in range(1, 19):
        secs = _collapse_similar_retire_secs(by_line.get(i) or [])
        extra = list(report_bits.get(i) or [])
        # 已有报废说明时，不再塞「无欠修/暂无」类报告套话
        if secs:
            extra = [x for x in extra if not _is_weak_retire_report_para(str(x.get("text") or ""))]
        flow = _merge_line_retire_flows(secs, extra)
        paras = [
            str(x.get("text") or "").strip()
            for x in flow
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        empty = _retire_flow_is_empty(flow, paras)
        if empty:
            flow, paras = [], []
        src = "、".join(
            dict.fromkeys(
                [str(s.get("source") or "") for s in secs if s.get("source")]
                + [str(x.get("source") or "") for x in extra if x.get("source")]
            )
        )
        if src:
            src_names.append(src)
        sections.append(
            {
                "line": f"{i}号线",
                "line_no": i,
                "title": f"轨道交通{i}号线",
                "paras": paras,
                "flow": flow,
                "source": src,
                "empty": empty,
            }
        )
    return {
        "source": source or ("、".join(dict.fromkeys(src_names))[:120]),
        "sections": sections,
        "year": int(year),
    }


def _ch8_slot_role(title: str) -> str:
    t = compact_text(title or "")
    if "评估小结" in t:
        return "summary"
    if "风险数据库" in t:
        return "risk_db"
    if "手册" in t:
        return "handbook"
    if "典型故障" in t:
        return "faults"
    if "突出事件" in t:
        return "events"
    return "body"


def resolve_ch8_outline(prior_docs: list[DocumentModel] | None) -> dict[str, Any]:
    """第 8 章骨架：从去年/保底报告检测；失败则用与检测结果同构的保底常量。"""
    from chapters.common.outline_detect import detect_chapter_outline
    from chapters.power.style import CH8_OUTLINE_FALLBACK

    detected = detect_chapter_outline(
        prior_docs,
        chapter_keys=("风险隐患闭环度评估",),
        stop_keys=("备件物资保障度评估", "使用环境符合性评估", "第9章", "第九章"),
        chapter_no=8,
    )
    if len(detected) >= 3 and any("风险数据库" in (x.get("title") or "") for x in detected):
        nodes = detected
        via = "prior"
    else:
        nodes = [dict(x) for x in CH8_OUTLINE_FALLBACK]
        via = "fallback"
    for node in nodes:
        node["role"] = _ch8_slot_role(node.get("title") or "")
    return {"nodes": nodes, "via": via, "source": (nodes[0].get("source") if nodes else "") or ""}


def _table_head_blob(rows: list[list[str]] | None, n: int = 3) -> str:
    rows = rows or []
    return "".join(str(c) for r in rows[:n] for c in r)


def _is_risk_detail_list(rows: list[list[str]]) -> bool:
    """明细风险清单（多列风险点描述+管控措施）不当作 8.1.1 汇总表。"""
    if not rows or len(rows[0]) >= 8:
        head = _table_head_blob(rows, 2)
        if "风险点描述" in head and "管控措施" in head:
            return True
    head = _table_head_blob(rows, 2)
    return "风险点描述" in head and "管控措施" in head and len(rows[0]) >= 7


def _score_risk_db_table(rows: list[list[str]]) -> int:
    """兼容 2025（类型/风险项/数量）与 2026（风险类别/划分单元/风险点/R1…）。"""
    if not rows or len(rows) < 2:
        return -1
    if _is_risk_detail_list(rows):
        return -1
    head = _table_head_blob(rows, 3)
    score = 0
    # 2025 汇总
    if "类型" in head and "风险项" in head and "数量" in head:
        score += 100
    # 2026 汇总
    if "风险类别" in head and ("划分单元" in head or "风险点" in head):
        score += 100
    if "R1" in head or "R1/R2" in head:
        score += 25
    if "风险点（个数）" in head or "风险点(个数)" in head:
        score += 20
    if any("合计" in "".join(str(c) for c in r) for r in rows[-2:]):
        score += 10
    # 行数适中的汇总表加分；过大可能是明细
    if 4 <= len(rows) <= 40:
        score += 15
    elif len(rows) > 80:
        score -= 40
    ncols = len(rows[0])
    if 3 <= ncols <= 6:
        score += 20
    elif ncols > 8:
        score -= 30
    return score


def _normalize_risk_db_rows(rows: list[list[str]]) -> list[list[str]]:
    """去掉说明行；保留双行表头（2026）或单行表头（2025）。"""
    rows = [list(r) for r in rows]
    while rows and (
        "说明" in "".join(str(c) for c in rows[0])
        and "风险类别" not in "".join(str(c) for c in rows[0])
        and "类型" not in "".join(str(c) for c in rows[0])
    ):
        rows = rows[1:]
    if len(rows) >= 2:
        h0 = "".join(str(c) for c in rows[0])
        h1 = "".join(str(c) for c in rows[1])
        # 0902 类：两行都写满「风险类别…」——保留两行作表头
        if "风险类别" in h0 and "一级" in h1 and "二级" in h1:
            return rows
        if "划分单元" in h0 and "一级" in h1:
            return rows
    return rows


def extract_risk_database_table(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """8.1.1 风险数据库表：只认当年材料；表头随年变化（25/26 皆可）。"""
    empty: dict[str, Any] = {"table": [], "flow": [], "source": "", "style": ""}
    best: tuple[int, dict[str, Any]] | None = None
    for doc in docs or []:
        if _is_line_report(doc) or _looks_like_compiled_annual_content(doc):
            continue
        name = _src(doc)
        for block in doc.blocks or []:
            if block.type != "table" or not block.rows:
                continue
            raw = [list(r) for r in block.rows]
            score = _score_risk_db_table(raw)
            if score < 50:
                continue
            if any(k in name for k in ("风险数据库", "风险清单", "风险辨识")):
                score += 30
            table = _normalize_risk_db_rows(raw)
            head = _table_head_blob(table, 2)
            style = "2026" if "风险类别" in head else "2025"
            cand = {
                "table": table,
                "flow": [{"kind": "table", "rows": table}],
                "source": name,
                "style": style,
            }
            if best is None or score > best[0]:
                best = (score, cand)
    return best[1] if best else empty


def _handbook_banner_and_header(rows: list[list[str]]) -> tuple[int, str, str]:
    """返回 (表头起行, 册名/横幅, 表头拼接)。横幅如「变电专业改造项目督查隐患排查手册」。"""
    if not rows:
        return 0, "", ""
    head0 = "".join(str(c) for c in rows[0])
    if "隐患描述" not in head0 and len(rows) > 1 and "隐患描述" in "".join(str(c) for c in rows[1]):
        return 1, head0, "".join(str(c) for c in rows[1])
    return 0, "", head0


def _prior_handbook_body_blob(prior_docs: list[DocumentModel] | None) -> str:
    """从去年年报「隐患排除/排查手册」节下样表取正文指纹（对照类型，不绑表名）。"""
    for doc in prior_docs or []:
        blocks = list(doc.blocks or [])
        take = False
        for i, block in enumerate(blocks):
            t = (block.text or "").strip()
            compact = compact_text(t)
            if t and _is_short_section_title(compact, 36) and any(
                k in compact for k in ("隐患排除手册", "隐患排查手册")
            ):
                take = True
                continue
            if not take:
                continue
            if t and _is_short_section_title(compact, 36) and any(
                k in compact for k in ("典型故障", "评估小结", "风险数据库")
            ):
                break
            if block.type == "table" and block.rows:
                return "".join(str(c) for r in block.rows[:8] for c in r)
    return ""


def _score_hazard_handbook_table(
    rows: list[list[str]],
    *,
    banner: str = "",
    sheet_hint: str = "",
    prior_blob: str = "",
) -> int:
    """按「手册子表类型」打分，不写死工作表名。

    年报成文要的是「改造项目督查」类（施工前/中/后 + 督查手册），
    不是文件里大量「现场作业人员」巡视/保养子表。类型信号来自表内正文与横幅。
    """
    if not rows or len(rows) < 2:
        return -1
    start, auto_banner, head = _handbook_banner_and_header(rows)
    banner = banner or auto_banner
    if "隐患描述" not in head or "作业" not in head:
        return -1
    body = "".join(str(c) for r in rows[start : start + 12] for c in r)
    blob = f"{banner}{sheet_hint}{head}{body}"
    score = 10
    # —— 改造项目督查类（对照去年样表内容型）——
    if "改造项目" in blob and "督查" in blob:
        score += 90
    if "督查隐患排查手册" in banner or "督查人员隐患排查手册" in banner:
        score += 40
    if "督查" in banner and "现场作业人员" not in banner:
        score += 25
    step_hits = sum(1 for k in ("施工前", "施工中", "施工后") if k in body)
    score += step_hits * 25
    if "改造项目" in body:
        score += 35
    # 供电总册：正文写「变电…改造」优于「接触网…改造」（内容词，非表名）
    if "变电" in blob and "改造" in blob:
        score += 20
    if "接触网" in blob and "改造" in blob and "变电" not in blob:
        score -= 25
    # —— 现场巡视/保养类降权（同文件里常见，但不是 8.1.2 成文样例类型）——
    if "现场作业人员隐患排查手册" in banner and "督查" not in banner and "改造" not in blob:
        score -= 50
    if any(k in blob for k in ("巡视", "清扫保养", "预防性试验", "停送电作业")) and "改造项目" not in blob:
        score -= 30
    # 与去年样表正文重合（气灭切换、施工前等），逐年可跟去年类型走
    if prior_blob:
        overlap = 0
        for key in ("改造项目", "施工前", "施工中", "施工后", "气灭", "工作许可人", "施工负责人", "督查"):
            if key in prior_blob and key in blob:
                overlap += 1
        score += overlap * 12
    # 行数：改造督查样表通常短（施工前中后数行），超长巡视表略降
    data_rows = max(0, len(rows) - start - 1)
    if 2 <= data_rows <= 8:
        score += 15
    elif data_rows > 20:
        score -= 20
    return score


def extract_hazard_handbook(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """8.1.2 隐患排除/排查手册：在手册文件的多子表中，按类型优选「改造项目督查」类。

    不绑工作表名；看横幅/作业项目/作业步骤内容。有去年样表时用其正文指纹对齐类型。
    """
    empty: dict[str, Any] = {"table": [], "flow": [], "source": "", "kind": ""}
    prior_blob = _prior_handbook_body_blob(prior_docs)
    best: tuple[int, dict[str, Any]] | None = None
    for doc in docs or []:
        if _is_line_report(doc):
            continue
        name = _src(doc)
        sheet_hint = ""
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if block.type == "heading" and t.startswith("工作表:"):
                sheet_hint = t
                continue
            if block.type != "table" or not block.rows:
                continue
            rows = [list(r) for r in block.rows]
            start, banner, head = _handbook_banner_and_header(rows)
            if "隐患描述" not in head or "作业" not in head:
                continue
            score = _score_hazard_handbook_table(
                rows,
                banner=banner,
                sheet_hint=sheet_hint,
                prior_blob=prior_blob,
            )
            if "手册" in name:
                score += 8
            if score < 40:
                continue
            table = rows[start : start + 20]
            kind = "reform_supervision" if ("改造项目" in banner + sheet_hint + "".join(str(c) for r in table[:6] for c in r) and "督查" in banner + sheet_hint) else "other"
            cand = {
                "table": table,
                "flow": [{"kind": "table", "rows": table}],
                "source": name,
                "kind": kind,
                "banner": banner,
                "sheet": sheet_hint,
            }
            if best is None or score > best[0]:
                best = (score, cand)
    return best[1] if best else empty


def _prior_fault_body_blob(prior_docs: list[DocumentModel] | None) -> str:
    """从去年年报「典型故障」节取正文指纹（只学体例标签，不顶今年事故）。"""
    hit = extract_named_section(
        prior_docs,
        start_keys=("典型故障", "8.1.3"),
        stop_keys=("评估小结", "8.2", "备件物资", "第9章", "第九章"),
        after_keys=("风险隐患闭环", "突出事件", "典型故障"),
        skip_line_reports=False,
    )
    paras = [str(p).strip() for p in (hit.get("paras") or []) if str(p).strip()]
    if paras:
        return "".join(paras[:40])
    for doc in prior_docs or []:
        take = False
        buf: list[str] = []
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if not t:
                continue
            compact = compact_text(t)
            if block.type == "heading" and "典型故障" in compact and _is_short_section_title(compact, 24):
                take = True
                continue
            if take and block.type == "heading" and _is_short_section_title(compact, 24):
                if any(k in compact for k in ("评估小结", "备件")):
                    break
            if take and t:
                buf.append(t)
            if len(buf) >= 40:
                break
        if buf:
            return "".join(buf)
    return ""


_FAULT_STRUCT_KEYS = ("故障现象", "故障原因分析", "原因分析", "处置措施", "整改措施", "整改措施及建议", "事件概况")
_FAULT_POWER_KEYS = (
    "变电",
    "直流开关",
    "主变",
    "牵引",
    "降压",
    "混变",
    "开关柜",
    "电缆",
    "综保",
    "框架保护",
    "PSCADA",
    "整流",
    "400V",
    "35kV",
    "10kV",
    "1500V",
    "抢修令",
    "二类故障",
)
_FAULT_OVERHEAD_KEYS = (
    "接触网",
    "接触轨",
    "锚段",
    "磨耗",
    "导高",
    "拉出值",
    "股道指示灯",
    "定位点",
    "柔性接触网",
    "刚性接触网",
    "检调",
)
# 8.1.3 成文条数上限（对照年报「精选数条」体例，可逐年复用）
CH8_FAULT_CASE_LIMIT = 4
_CN_CASE_ORD = "一二三四五六七八九十"


def _fault_case_start(text: str, *, loose: bool = False) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 100:
        return False
    if "故障分析" in t and re.match(r"^[一二三四五六七八九十\d]", t):
        return True
    if re.match(r"^[一二三四五六七八九十]+[、.．]", t):
        if loose:
            return True
        if "故障" in t or "跳闸" in t or "混变" in t or "主变" in t or "缺相" in t or "开关" in t:
            return True
    return False


def _split_paras_into_cases(paras: list[str], *, loose: bool = False) -> list[list[str]]:
    """把连续段落按「一、/二、…」切成多条独立案例。"""
    cases: list[list[str]] = []
    cur: list[str] = []
    for p in paras:
        t = str(p).strip()
        if not t:
            continue
        if _fault_case_start(t, loose=loose) and cur:
            cases.append(cur)
            cur = [t]
        else:
            cur.append(t)
    if cur:
        cases.append(cur)
    return cases


def _fault_event_fingerprint(blob: str) -> str:
    """事件指纹：线路 + 站名线索 + 开关号，用于跨文件去重。"""
    compact = compact_text(blob or "")
    line = ""
    m = re.search(r"(\d+)号线", compact)
    if m:
        line = m.group(1)
    sw = ""
    m2 = re.search(r"(\d{2,4})直流开关", compact)
    if m2:
        sw = m2.group(1)
    station = ""
    for key in ("混变", "主变", "牵引站", "降压站", "跟随"):
        idx = compact.find(key)
        if idx > 0:
            station = compact[max(0, idx - 12) : idx + len(key)]
            break
    return f"{line}|{station}|{sw}"


def _fault_coherence_penalty(blob: str) -> int:
    """现象/标题与原因明显不是同一事件（材料串文）则扣分。"""
    if "故障原因" not in blob and "原因分析" not in blob:
        return 0
    head = blob.split("故障现象")[0] if "故障现象" in blob else blob[:120]
    if "故障现象" in blob:
        phen = blob.split("故障现象", 1)[1]
        phen = re.split(r"故障原因|原因分析|处置措施|整改措施", phen, maxsplit=1)[0]
    else:
        phen = head
    reason = ""
    for sep in ("故障原因分析", "故障原因", "原因分析"):
        if sep in blob:
            reason = blob.split(sep, 1)[1]
            reason = re.split(r"处置措施|整改措施", reason, maxsplit=1)[0]
            break
    if not reason:
        return 0
    # 标题/现象侧设备词
    head_blob = head + phen
    penalty = 0
    if "整流变" in head_blob and any(k in reason for k in ("BA死机", "隔离放大器", "PRO装置")) and "整流" not in reason:
        penalty += 80
    if "电缆" in head_blob and "BA死机" in reason:
        penalty += 60
    # 原因里出现与标题完全不同的站名/开关号
    hm = re.search(r"(\d+)号线([^，。；]{2,12})(?:混变|主变|牵引)", head_blob)
    rm = re.search(r"(\d+)号线([^，。；]{2,12})(?:混变|主变|牵引)", reason)
    if hm and rm and (hm.group(1) != rm.group(1) or hm.group(2) != rm.group(2)):
        penalty += 50
    return penalty


def _fault_has_complete_triad(blob: str) -> bool:
    """是否具备完整三件套：故障现象 + 原因分析 + 处置/整改措施。"""
    if "故障现象" not in (blob or ""):
        return False
    has_reason = any(k in blob for k in ("故障原因分析", "故障原因", "原因分析"))
    has_action = any(k in blob for k in ("处置措施", "整改措施及建议", "整改措施"))
    return has_reason and has_action


def _score_fault_case(blob: str, prior_blob: str = "") -> int:
    """单条故障打分：完整三件套优先；串文/触网/残缺叙述降权。"""
    if not blob or len(blob) < 30:
        return -1
    score = 0
    complete = _fault_has_complete_triad(blob)
    # —— 完整度（最高优先）——
    if complete:
        score += 200
        if "故障原因分析" in blob:
            score += 20
        if "处置措施" in blob:
            score += 25
        elif "整改措施" in blob:
            score += 15
    else:
        # 残缺条明显降权，仅在凑不满 4 条完整稿时作候补
        score -= 80
        if "故障现象" in blob:
            score += 20
        if any(k in blob for k in ("故障原因分析", "原因分析")):
            score += 15
        if any(k in blob for k in ("处置措施", "整改措施")):
            score += 15
    if "故障分析" in blob:
        score += 20
    if "二类故障" in blob or "抢修令" in blob:
        score += 20
    if "二类故障" in blob and any(k in blob for k in ("直流开关", "混变", "主变", "综保")):
        score += 25
    if re.search(r"发布\d+#抢修令", blob) and "直流开关" in blob:
        score += 30
    if "施工完成送电" in blob or ("施工" in blob[:40] and "缺相" in blob):
        score -= 25
    if "抢修令" not in blob and "二类故障" not in blob and "差动保护" not in blob and not complete:
        score -= 40
    if len(blob) >= 120:
        score += 10
    if len(blob) >= 280 and complete:
        score += 15
    power = sum(1 for k in _FAULT_POWER_KEYS if k in blob)
    score += min(40, power * 6)
    oh = sum(1 for k in _FAULT_OVERHEAD_KEYS if k in blob)
    if oh and not any(k in blob for k in ("直流开关", "混变", "主变", "综保", "整流", "电缆")):
        score -= min(70, oh * 14)
    head = blob[:60]
    if any(k in head for k in ("接触网设备", "接触网断裂", "定位点", "磨耗偏大")):
        score -= 100
    if blob.count("典型故障：") + blob.count("典型故障:") >= 1 and not complete and len(blob) < 160:
        score -= 40
    if "共发生设备故障" in blob and not complete:
        score -= 50
    if "期间发生典型故障" in blob and not complete:
        score -= 30
    score -= _fault_coherence_penalty(blob)
    return score


def _paras_to_flow(paras: list[str]) -> list[dict[str, Any]]:
    return [{"kind": "para", "text": p} for p in paras if str(p).strip()]


def _collect_fault_cases_from_doc(doc: DocumentModel) -> list[dict[str, Any]]:
    """从单份材料收集「按条」故障候选（分析体 + 线报告长叙述），不绑文件名。"""
    name = _src(doc)
    out: list[dict[str, Any]] = []
    seen_fp: set[str] = set()

    def _add(paras: list[str]) -> None:
        paras = [str(p).strip() for p in paras if str(p).strip()]
        if len("".join(paras)) < 40:
            return
        blob = "".join(paras)
        fp = _fault_event_fingerprint(blob)
        # 同文件内相同指纹只留更长的
        for i, old in enumerate(out):
            if old.get("fp") == fp and fp:
                if len(blob) > len(old.get("blob") or ""):
                    out[i] = {"paras": paras, "flow": _paras_to_flow(paras), "source": name, "blob": blob, "fp": fp}
                return
        if fp and fp in seen_fp:
            return
        if fp:
            seen_fp.add(fp)
        out.append({"paras": paras, "flow": _paras_to_flow(paras), "source": name, "blob": blob, "fp": fp})

    # A) 「典型故障」小节 → 再按一、二、切开
    one = extract_named_section(
        [doc],
        start_keys=("典型故障", "8.1.3"),
        stop_keys=("评估小结", "8.2", "备件物资", "第9章", "第九章", "风险数据库", "隐患排除", "隐患排查"),
        after_keys=(),
        skip_line_reports=False,
    )
    if section_has_body(one):
        paras = [str(p).strip() for p in (one.get("paras") or []) if str(p).strip()]
        parts = _split_paras_into_cases(paras, loose=True)
        if len(parts) <= 1 and paras:
            # 可能只有「典型故障：」后跟（1）（2）短条：按编号短条再切
            buf: list[str] = []
            for p in paras:
                if re.match(r"^（\d+[）)]", p) or re.match(r"^\(\d+\)", p):
                    if buf and len("".join(buf)) >= 40:
                        _add(buf)
                    buf = [p]
                else:
                    buf.append(p)
            if buf:
                _add(buf)
        else:
            for part in parts:
                # 单条内部若误带下一条编号标题，再松切一次
                sub = _split_paras_into_cases(part, loose=True)
                for sp in sub:
                    _add(sp)

    # B) 全文再扫「一、…故障分析」独立条（线报告/专稿）
    blocks = list(doc.blocks or [])
    texts = [(b.text or "").strip() for b in blocks if (b.text or "").strip() and b.type in {"heading", "paragraph"}]
    i = 0
    while i < len(texts):
        if not _fault_case_start(texts[i]):
            i += 1
            continue
        j = i + 1
        while j < len(texts):
            if _fault_case_start(texts[j]):
                break
            c2 = compact_text(texts[j])
            if _is_short_section_title(c2, 28) and any(
                k in c2 for k in ("评估小结", "生产计划", "仪器仪表", "风险数据库", "隐患", "日常维修")
            ):
                break
            j += 1
        _add(texts[i:j])
        i = j

    # C) 线报告/变电专稿：无「一、」标题，但有二类故障/抢修令长叙述
    if _is_line_report(doc) or "变电" in name or "故障" in name:
        buf: list[str] = []
        for t in texts:
            if any(k in t for k in ("二类故障", "抢修令", "一类故障")) and len(t) >= 60:
                if buf and len("".join(buf)) >= 60:
                    _add(buf)
                buf = [t]
            elif buf:
                if len(t) >= 20 and not _is_short_section_title(compact_text(t), 24):
                    buf.append(t)
                if len("".join(buf)) > 800:
                    _add(buf)
                    buf = []
        if buf:
            _add(buf)

    return out


def _fault_case_title_core(text: str) -> str:
    """从首段抽短标题（线路+站+设备），避免整段当标题。"""
    t = (text or "").strip()
    t = re.sub(r"^[一二三四五六七八九十]+[、.．]\s*", "", t).strip()
    t = re.sub(r"^\d+[、.．]\s*", "", t).strip()
    t = re.sub(r"^[（(]\d+[）)]\s*", "", t).strip()
    m = re.search(
        r"\d+号线[^，。；]{0,16}(?:混变|主变|牵引站|降压站|跟随变电站)[^，。；]{0,20}(?:\d{2,4})?(?:直流开关|开关|电缆|整流变|综保|电力变)",
        t,
    )
    if m:
        return m.group(0).rstrip("，,；;。")
    m2 = re.search(r"\d+号线[^，。；]{4,40}", t)
    if m2:
        return m2.group(0).rstrip("，,；;。")
    return t[:40].rstrip("，,；;。")


def _renumber_fault_cases(cases: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """成文前重排为 一、二、三…（体例统一，不保留材料原编号）。"""
    paras_out: list[str] = []
    flow_out: list[dict[str, Any]] = []
    for i, case in enumerate(cases):
        ord_prefix = f"{_CN_CASE_ORD[i]}、" if i < len(_CN_CASE_ORD) else f"{i + 1}、"
        case_paras = [str(p).strip() for p in (case.get("paras") or []) if str(p).strip()]
        if not case_paras:
            continue
        first = case_paras[0]
        core = _fault_case_title_core(first)
        title = f"{ord_prefix}{core}"
        if "故障分析" not in title and "故障" not in title[-6:]:
            title = f"{title}故障分析"
        # 若首段本身就是短标题，正文从下一段起；若首段是长叙述，整段保留在标题后
        if _fault_case_start(first, loose=True) or re.match(r"^[（(]\d+[）)]", first) or len(first) < 70:
            body_paras = case_paras[1:]
        else:
            body_paras = case_paras
        cleaned = [title]
        for p in body_paras:
            if _fault_case_start(p, loose=True):
                break
            cleaned.append(p)
        paras_out.extend(cleaned)
        flow_out.extend(_paras_to_flow(cleaned))
    return paras_out, flow_out


def extract_typical_faults(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """8.1.3 典型故障：约 4 条；优先完整无误的「现象+原因+处置/整改」。

    通用规则（不绑文件名）：
    - 先收完整三件套且无串文的条目，不足再补较完整的叙述；
    - 触网短条/纯统计/串文剔除或降权；
    - 跨文件按事件指纹去重；标题后标注全部用到的文件。
    """
    empty: dict[str, Any] = {"paras": [], "flow": [], "source": "", "cases": []}
    prior_blob = _prior_fault_body_blob(prior_docs)
    complete_rank: list[tuple[int, dict[str, Any]]] = []
    partial_rank: list[tuple[int, dict[str, Any]]] = []
    for doc in docs or []:
        overhead = _is_overhead_specialty_doc(doc)
        for cand in _collect_fault_cases_from_doc(doc):
            blob = cand.get("blob") or ""
            if overhead:
                head = blob[:80]
                if any(k in head for k in ("接触网", "接触轨", "锚段", "磨耗", "定位点", "股道")):
                    continue
                if "故障现象" not in blob:
                    continue
            coh = _fault_coherence_penalty(blob)
            if coh >= 50:
                continue
            score = _score_fault_case(blob, prior_blob)
            if score < 40:
                continue
            item = dict(cand)
            item["complete"] = _fault_has_complete_triad(blob)
            item["score"] = score
            if item["complete"]:
                complete_rank.append((score, item))
            else:
                # 残缺条门槛更高，避免挤掉完整稿
                if score < 80:
                    continue
                partial_rank.append((score, item))
    complete_rank.sort(key=lambda x: -x[0])
    partial_rank.sort(key=lambda x: -x[0])

    def _take(pool: list[tuple[int, dict[str, Any]]], picked: list[dict[str, Any]], seen_fp: set[str], limit: int) -> None:
        for _score, cand in pool:
            if len(picked) >= limit:
                return
            fp = cand.get("fp") or _fault_event_fingerprint(cand.get("blob") or "")
            if fp and fp in seen_fp:
                continue
            if fp:
                seen_fp.add(fp)
            picked.append(cand)

    picked: list[dict[str, Any]] = []
    seen_fp: set[str] = set()
    # 先完整，再残缺凑满约 4 条
    _take(complete_rank, picked, seen_fp, CH8_FAULT_CASE_LIMIT)
    if len(picked) < CH8_FAULT_CASE_LIMIT:
        _take(partial_rank, picked, seen_fp, CH8_FAULT_CASE_LIMIT)
    if not picked:
        return empty
    paras, flow = _renumber_fault_cases(picked)
    sources: list[str] = []
    for c in picked:
        s = (c.get("source") or "").strip()
        if s and s not in sources:
            sources.append(s)
    return {
        "paras": paras,
        "flow": flow,
        "source": "、".join(sources),
        "cases": picked,
    }


def extract_hazards(docs: list[DocumentModel]) -> dict[str, Any]:
    """兼容旧调用：手册 + 治理 PDF。完整第 8 章请用 extract_ch8。"""
    handbook = extract_hazard_handbook(docs)
    pdf_paras: list[dict[str, str]] = []
    pdf_source = ""
    drawings: list[dict[str, Any]] = []
    flow: list[dict[str, Any]] = []
    for doc in docs or []:
        if _is_line_report(doc):
            continue
        name = _src(doc)
        if "隐患" in name and not name.lower().endswith(".pdf"):
            for block in doc.blocks:
                item = _flow_item(doc, block)
                if item and item.get("kind") in {"drawing", "table", "formula"}:
                    if item.get("kind") == "drawing":
                        drawings.append(item)
                    flow.append(item)
        if _is_pdf(doc) and (_pdf_topic(doc) == "hazard" or "隐患" in name):
            if name in {x.get("source") for x in pdf_paras}:
                continue
            pdf_source = pdf_source or name
            for sent in _merge_pdf_pages(doc.blocks):
                pdf_paras.append({"text": sent, "source": name})
    seen_pdf: set[str] = set()
    uniq_pdf: list[dict[str, str]] = []
    for row in pdf_paras:
        sig = compact_text(row.get("text") or "")
        if not sig or sig in seen_pdf:
            continue
        seen_pdf.add(sig)
        uniq_pdf.append(row)
    return {
        "pdf_source": pdf_source,
        "pdf_paras": uniq_pdf[:40],
        "handbook": handbook.get("table") or [],
        "handbook_source": handbook.get("source") or "",
        "drawings": dedupe_flow_items(drawings),
        "flow": dedupe_flow_items(flow),
    }


def extract_ch8(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """第 8 章：骨架从去年报告检测；正文/表只填当年材料（表头格式随材料，25/26 皆可）。"""
    outline = resolve_ch8_outline(prior_docs)
    risk = extract_risk_database_table(docs)
    handbook = extract_hazard_handbook(docs, prior_docs)
    faults = extract_typical_faults(docs, prior_docs)
    legacy = extract_hazards(list(docs or []))
    slots: dict[str, Any] = {
        "risk_db": risk,
        "handbook": {
            "table": handbook.get("table") or [],
            "flow": handbook.get("flow") or [],
            "source": handbook.get("source") or "",
        },
        "faults": faults,
        "summary": {"paras": [], "flow": [], "source": ""},
    }
    return {
        "outline": outline.get("nodes") or [],
        "outline_via": outline.get("via") or "",
        "outline_source": outline.get("source") or "",
        "slots": slots,
        # 兼容旧字段
        "handbook": handbook.get("table") or [],
        "handbook_source": handbook.get("source") or "",
        "pdf_paras": legacy.get("pdf_paras") or [],
        "pdf_source": legacy.get("pdf_source") or "",
        "drawings": legacy.get("drawings") or [],
        "flow": risk.get("flow") or [],
        "risk_table": risk.get("table") or [],
        "risk_source": risk.get("source") or "",
        "fault_paras": faults.get("paras") or [],
        "fault_flow": faults.get("flow") or [],
        "fault_source": faults.get("source") or "",
        "summary": {"paras": [], "flow": [], "source": ""},
    }


def block_has_handbook(doc: DocumentModel) -> bool:
    """材料是否带隐患排查手册表。给分类/调试用，抽取本身看表头「隐患描述」。"""
    if "手册" in (doc.source_name or ""):
        return True
    return any(b.type == "table" and b.rows and "隐患描述" in "".join(str(c) for c in b.rows[0]) for b in doc.blocks)


def _doc_text_chunks(doc: DocumentModel, *, limit: int = 120) -> list[str]:
    """抽样正文与表头，供内容判别（不看文件名）。"""
    out: list[str] = []
    for block in doc.blocks or []:
        if block.type == "table" and block.rows:
            head = "".join(str(c) for c in block.rows[0])
            if head.strip():
                out.append(head)
            if len(block.rows) > 1:
                out.append("".join(str(c) for c in block.rows[1][:8]))
        else:
            t = (block.text or "").strip()
            if t:
                out.append(t)
        if len(out) >= limit:
            break
    return out


def _content_weight(chunks: list[str], keys: tuple[str, ...]) -> int:
    w = 0
    for chunk in chunks:
        for k in keys:
            if k in chunk:
                w += 1
    return w


# 接触网专业内容信号（表头/正文），与文件名无关
_OVERHEAD_CONTENT_KEYS = (
    "锚段",
    "柔性接触网",
    "刚性接触网",
    "接触线",
    "接触轨",
    "磨耗",
    "导高",
    "拉出值",
    "各线路柔性",
    "各线路刚性",
)
# 供电生产计划语境
_PLAN_CONTENT_KEYS = (
    "生产计划执行",
    "日常维修计划",
    "日常维护计划",
    "计划数量",
    "完成率",
    "完成数量",
    "表7-1",
    "运维质量",
)


def _looks_like_compiled_annual_content(doc: DocumentModel) -> bool:
    """完整年报/多章汇编：正文里连续出现多章题，不当作「当年单一生产计划表」材料。

    上传到 _prior 或保底年报也视为汇编通道，避免把去年整册当今年 7.2。
    """
    path = (doc.source_path or "").replace("\\", "/")
    name = _src(doc)
    if "/_prior/" in path or "prior_baseline" in path or name.startswith("项目保底"):
        return True
    markers = (
        "设备功能有效性评估",
        "管理体系合规性",
        "修程修制匹配性",
        "运维表现健康度",
        "风险隐患闭环",
        "备件物资保障",
        "使用环境符合",
        "设备退运",
        "总结与建议",
    )
    hits = 0
    for chunk in _doc_text_chunks(doc, limit=200):
        c = compact_text(chunk)
        if not c or len(c) > 56:
            continue
        if any(m in c for m in markers):
            hits += 1
        if hits >= 4:
            return True
    return False


def _is_plan_exec_table(rows: list[list[str]] | None) -> bool:
    """表7-1 结构：计划数量 + 完成率/完成数量；排除接触网状态/评级表。"""
    if not rows:
        return False
    head = "".join(str(c) for c in rows[0])
    if "计划数量" not in head:
        return False
    if "完成率" not in head and "完成数量" not in head:
        return False
    if any(k in head for k in ("锚段", "接触网", "触网", "柔性", "刚性", "评级范围", "磨耗")):
        return False
    if "占比" in head and "完成率" not in head:
        return False
    return True


def _nearby_plan_caption(blocks: list, index: int) -> str:
    """表前邻近表题/小节名（内容），用于加分与过滤。"""
    for j in range(index - 1, max(-1, index - 5), -1):
        t = (blocks[j].text or "").strip()
        if not t:
            continue
        if (
            _is_caption_text(t)
            or "生产计划" in t
            or "执行情况" in t
            or "日常维修计划" in t
            or "日常维护计划" in t
            or "运维质量" in t
        ):
            return t
        # 碰到别的表题/章题就停
        if _is_caption_text(t) or (len(t) < 40 and any(k in t for k in ("接触网", "锚段", "风险评估"))):
            return t
        break
    return ""


def _looks_like_org_mode(sec: dict[str, Any] | None) -> bool:
    """生产组织模式正文：管辖/维护部等体例信号；过短或目录条不算。"""
    sec = sec or {}
    paras = [str(p).strip() for p in (sec.get("paras") or []) if str(p).strip()]
    if not paras and not any(
        x.get("kind") == "para" and str(x.get("text") or "").strip() for x in (sec.get("flow") or [])
    ):
        return False
    blob = "".join(paras) or "".join(
        str(x.get("text") or "") for x in (sec.get("flow") or []) if x.get("kind") == "para"
    )
    if len(blob) < 48:
        return False
    keys = ("维护一部", "维护二部", "维护三部", "管辖范围", "运维模式", "检修检测", "维护部")
    return sum(1 for k in keys if k in blob) >= 2


def extract_org_mode(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """7.1 生产组织模式：今年材料有则用；否则复用去年/保底同节；都没有则空（成文黄标题）。

    按小节名切段，不绑文件名、不写死某年管辖范围。
    """
    empty: dict[str, Any] = {"paras": [], "flow": [], "source": "", "via": ""}
    year = extract_named_section(
        docs,
        start_keys=("生产组织模式", "7.1"),
        stop_keys=(
            "设施设备运维质量",
            "7.2",
            "日常维修计划执行情况",
            "日常维修计划",
            "日常维护计划",
            "评估小结",
            "7.3",
            "风险隐患",
            "第8章",
            "第八章",
        ),
        after_keys=("运维表现健康度", "运维表现", "生产组织"),
    )
    if section_has_body(year) and _looks_like_org_mode(year):
        return {
            "paras": list(year.get("paras") or []),
            "flow": list(year.get("flow") or []),
            "source": year.get("source") or "",
            "via": "year",
        }
    prior = extract_named_section(
        prior_docs,
        start_keys=("生产组织模式", "7.1"),
        stop_keys=(
            "设施设备运维质量",
            "7.2",
            "日常维修计划执行情况",
            "日常维修计划",
            "日常维护计划",
            "评估小结",
            "7.3",
        ),
        after_keys=("运维表现健康度", "运维表现"),
        skip_line_reports=False,
    )
    if section_has_body(prior) and _looks_like_org_mode(prior):
        return {
            "paras": list(prior.get("paras") or []),
            "flow": list(prior.get("flow") or []),
            "source": prior.get("source") or "",
            "via": "prior",
        }
    return empty


def extract_plan_table(docs: list[DocumentModel]) -> dict[str, Any]:
    """第 7 章 7.2：按表结构与正文语境抽「生产计划执行表」。

    通用规则（不绑文件名、不绑某年）：
    - 认表头「计划数量 + 完成率/完成数量」；
    - 表题/邻段像生产计划则加分；邻段是接触网状态则丢；
    - 整篇接触网信号强、计划语境弱则整份跳过；
    - 多章汇编/去年通道不当作当年计划表；
    - flow 只收表题段落 + 表，绝不收图（避免莫名图片）。
    """
    empty: dict[str, Any] = {"source": "", "table": [], "flow": []}
    best: tuple[int, dict[str, Any]] | None = None
    for doc in docs or []:
        if _is_line_report(doc) or _looks_like_compiled_annual_content(doc):
            continue
        chunks = _doc_text_chunks(doc)
        oh = _content_weight(chunks, _OVERHEAD_CONTENT_KEYS)
        plan_ctx = _content_weight(chunks, _PLAN_CONTENT_KEYS)
        # 接触网专业稿：锚段/柔性等远多于计划语境
        if oh >= 5 and plan_ctx <= 2:
            continue
        name = _src(doc)
        blocks = list(doc.blocks or [])
        for i, block in enumerate(blocks):
            if block.type != "table" or not block.rows:
                continue
            if not _is_plan_exec_table(block.rows):
                continue
            caption = _nearby_plan_caption(blocks, i)
            if any(k in caption for k in ("锚段", "柔性接触网", "刚性接触网", "接触网状态", "表3-")):
                continue
            table = [list(r) for r in block.rows]
            head = "".join(str(c) for c in table[0])
            score = len(table)
            if "完成率" in head:
                score += 25
            if "线路" in head:
                score += 10
            if any(k in caption for k in ("表7-1", "生产计划执行", "日常维修计划", "日常维护计划")):
                score += 60
            elif caption:
                score += 15
            # 全篇语境：供电计划强于接触网
            score += min(40, plan_ctx * 8)
            score -= min(60, oh * 6)
            if score < 5:
                continue
            flow: list[dict[str, Any]] = []
            if caption and (
                _is_caption_text(caption)
                or "生产计划" in caption
                or "执行情况" in caption
                or "日常维修计划" in caption
                or "日常维护计划" in caption
            ):
                flow.append({"kind": "para", "text": caption})
            flow.append({"kind": "table", "rows": table})
            cand = {"source": name, "table": table, "flow": flow}
            if best is None or score > best[0]:
                best = (score, cand)
    return best[1] if best else empty


_CH7_72_STOP = (
    "日常维修计划执行情况",
    "日常维护计划执行情况",
    "生产计划执行方面",
    "1、生产计划执行方面",
    "①",
    "仪器仪表使用管理",
    "2、仪器仪表",
    "仪器仪表情况",
    "仪器仪表",
    "②",
    "部门年度培训",
    "3、部门年度培训",
    "3、年度培训",
    "年度培训方面",
    "培训情况",
    "③",
    "智能化应用",
    "4、智能化应用",
    "④",
    "维保管理",
    "新线路接管",
    "新技术应用",
    "故障处理流程",
    "7.2.1",
    "7.2.2",
    "7.2.3",
    "7.2.4",
    "评估小结",
    "7.3",
    "风险隐患",
    "第8章",
    "第八章",
    "评估结论",
    "备件物资",
    "使用环境",
    "退运报废",
    "第9章",
    "第10章",
    "第11章",
)


def _is_overhead_specialty_doc(doc: DocumentModel) -> bool:
    """接触网/触网专业线路稿：供电 7.2 不采。按文件名与正文信号。"""
    name = _src(doc)
    if any(k in name for k in ("接触网", "触网", "接触轨", "SCADA", "能耗")):
        return True
    chunks = _doc_text_chunks(doc, limit=40)
    return _content_weight(chunks, _OVERHEAD_CONTENT_KEYS) >= 8


_CN_LINE_NUMS: tuple[tuple[str, int], ...] = (
    ("十八", 18),
    ("十七", 17),
    ("十六", 16),
    ("十五", 15),
    ("十四", 14),
    ("十三", 13),
    ("十二", 12),
    ("十一", 11),
    ("十", 10),
)


def _line_label_from_doc(doc: DocumentModel) -> str:
    name = _src(doc)
    m = LINE_IN_NAME.search(name)
    return f"{int(m.group(1))}号线" if m else ""


def _line_no_from_doc(doc: DocumentModel) -> int | None:
    name = _src(doc)
    m = LINE_IN_NAME.search(name)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 18 else None
    # 「十号线 / 十一号线」等中文号线
    for cn, num in _CN_LINE_NUMS:
        if f"{cn}号线" in name or f"{cn}线路" in name:
            return num
    return None


def _leading_line_no(text: str) -> int | None:
    """段首（或序号后）点名的 1～18 号线；认不出则 None。不依赖文件名/目录。"""
    raw = (text or "").strip()
    if not raw:
        return None
    t = compact_text(raw)
    # 允许「1、11号线…」「（2）11号线…」后再写号线
    t = re.sub(r"^[（(]?\d+[)）、．.]\s*", "", t)
    m = re.match(r"^(\d{1,2})\s*[#＃]?\s*号线", t)
    if not m:
        m = re.match(r"^(\d{1,2})\s*[#＃]\s*线", t)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 18 else None
    for cn, num in _CN_LINE_NUMS:
        if t.startswith(f"{cn}号线") or t.startswith(f"{cn}线路"):
            return num
    return None


def _foreign_line_subject(text: str, host_line: int | None) -> int | None:
    """段首点名的号线若与文件名主线不同 → 归到该线（合订本/旁线段落通用，不绑某部某文件）。"""
    n = _leading_line_no(text)
    if n is None or n == host_line:
        return None
    return n


def _empty_ch7_line_sec(line_no: int) -> dict[str, Any]:
    return {
        "line_no": line_no,
        "line": f"{line_no}号线",
        "title": f"轨道交通{line_no}号线",
        "paras": [],
        "flow": [],
        "source": "",
        "empty": True,
    }


def _merge_ch7_line_items(
    sec: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    source: str,
) -> None:
    """把跨线摘出的段落并入目标号线（去重）。"""
    seen = {compact_text(str(p)) for p in (sec.get("paras") or []) if str(p).strip()}
    flow = list(sec.get("flow") or [])
    paras = list(sec.get("paras") or [])
    changed = False
    for item in items or []:
        if item.get("kind") == "table":
            flow.append(item)
            changed = True
            continue
        if item.get("kind") != "para":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        key = compact_text(text)
        if key in seen:
            continue
        seen.add(key)
        paras.append(text)
        flow.append({"kind": "para", "text": text})
        changed = True
    if not changed:
        return
    sec["paras"] = paras
    sec["flow"] = flow
    sec["empty"] = not (paras or any(x.get("kind") == "table" for x in flow))
    if source and not (sec.get("source") or "").strip():
        sec["source"] = source


def _is_ch7_power_line_doc(doc: DocumentModel) -> bool:
    """供电 7.2 按线路稿：1～18 号线变电类评估/专册。

    「变电专业、接触网专业」合订本要收；纯触网/SCADA/检测检修不要。不按维护部目录写死。
    """
    if not _is_line_report(doc):
        return False
    name = _src(doc)
    if any(k in name for k in ("检测检修", "SCADA", "能耗")):
        return False
    # 纯接触网专册跳过；文件名同时带变电的合订本保留
    if any(k in name for k in ("接触网", "触网", "接触轨")) and "变电" not in name:
        return False
    return _line_no_from_doc(doc) is not None


def _empty_ch7_aspect() -> dict[str, Any]:
    return {"paras": [], "flow": [], "source": "", "via": "", "lines": []}


def _ch7_non_line_docs(docs: list[DocumentModel] | None) -> list[DocumentModel]:
    return [
        d
        for d in (docs or [])
        if not _is_line_report(d)
        and not _looks_like_compiled_annual_content(d)
        and not _is_overhead_specialty_doc(d)
    ]


def _looks_like_ch7_lead(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 20 or len(t) > 220:
        return False
    if "几个方面" in t and ("运维质量" in t or "分析和评估" in t):
        return True
    return "设施设备运维质量" in t and "分析" in t


def _extract_ch7_lead(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None,
) -> dict[str, Any]:
    """7.2 开篇句：只认总述句；今年非线路稿 → 去年/保底 → 空。不从单线报告硬抠。"""

    def _from(docs2: list[DocumentModel] | None, via: str, *, non_line_only: bool) -> dict[str, Any] | None:
        pool = _ch7_non_line_docs(docs2) if non_line_only else list(docs2 or [])
        hit = extract_named_section(
            pool,
            start_keys=("设施设备运维质量分析", "7.2"),
            stop_keys=_CH7_72_STOP,
            after_keys=(),
            skip_line_reports=False,
        )
        paras = [str(p).strip() for p in (hit.get("paras") or []) if str(p).strip()]
        lead = []
        for p in paras[:4]:
            if any(
                k in p
                for k in (
                    "仪器仪表",
                    "部门年度培训",
                    "智能化应用",
                    "计划数量",
                    "维护一部",
                    "生产计划执行",
                )
            ):
                break
            if _looks_like_ch7_lead(p) or ("几个方面" in p) or ("分析和评估" in p and "运维" in p):
                lead.append(p)
                break
            # 短开场可收下，但下一句再判
            if len(p) < 80 and "运维质量" in p:
                lead.append(p)
                continue
            break
        if not lead or not any(_looks_like_ch7_lead(x) or "几个方面" in x for x in lead):
            # 退路：整材料里找一句体例开篇
            for doc in pool:
                for b in doc.blocks or []:
                    t = (b.text or "").strip()
                    if _looks_like_ch7_lead(t):
                        flow = [{"kind": "para", "text": t}]
                        return {"paras": [t], "flow": flow, "source": _src(doc), "via": via}
            return None
        flow = [{"kind": "para", "text": t} for t in lead]
        return {"paras": lead, "flow": flow, "source": hit.get("source") or "", "via": via}

    year = _from(docs, "year", non_line_only=True)
    if year:
        return year
    prior = _from(prior_docs, "prior", non_line_only=False)
    if prior:
        return prior
    return _empty_ch7_aspect()


def _filter_ch7_aspect_flow(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """丢掉串台的小节标题、评估结论等短标签。"""
    out: list[dict[str, Any]] = []
    skip_exact = {
        "仪器仪表",
        "培训",
        "智能化应用",
        "生产计划",
        "评估结论与建议",
        "评估结论",
        "维护仪器、仪表情况配置情况：",
        "年度培训覆盖情况：",
    }
    for item in flow or []:
        if item.get("kind") == "table":
            out.append(item)
            continue
        if item.get("kind") != "para":
            continue
        t = str(item.get("text") or "").strip()
        if not t or t in skip_exact:
            continue
        compact = compact_text(t)
        if len(compact) <= 24 and any(
            k in compact
            for k in (
                "仪器仪表",
                "年度培训",
                "智能化应用",
                "生产计划执行",
                "评估结论",
            )
        ):
            continue
        out.append({"kind": "para", "text": t})
    return out


def _extract_ch7_plan_prose(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """7.2.1 正文：只从非线路今年稿抽总述（如「共计xxxx项…详见下表」）；不并各线散文。"""
    hit = extract_named_section(
        _ch7_non_line_docs(docs),
        start_keys=(
            "日常维修计划执行情况",
            "日常维护计划执行情况",
            "生产计划执行情况",
            "7.2.1",
        ),
        stop_keys=_CH7_72_STOP,
        after_keys=("运维表现健康度", "运维表现", "设施设备运维质量", "生产组织"),
        skip_line_reports=False,
    )
    flow = _filter_ch7_aspect_flow(
        [x for x in (hit.get("flow") or []) if x.get("kind") in {"para", "table"}]
    )
    # 表留给 extract_plan_table；这里只要说明句
    paras = [str(x.get("text") or "").strip() for x in flow if x.get("kind") == "para"]
    paras = [p for p in paras if not _is_caption_text(p) and "表7-1" not in p and "表6-1" not in p]
    flow = [{"kind": "para", "text": p} for p in paras]
    if not paras:
        return _empty_ch7_aspect()
    return {
        "paras": paras,
        "flow": flow,
        "source": hit.get("source") or "",
        "via": "year",
        "lines": [],
    }


def _ch7_ops_section_flow(doc: DocumentModel) -> list[dict[str, Any]]:
    """从单线评估报告切出「运维表现健康度」整段（标题写法各异）。"""
    hit = extract_named_section(
        [doc],
        start_keys=(
            "运维表现健康度评估",
            "运维表现健康度",
            "六、运维表现健康度评估",
            "六、运维表现",
        ),
        stop_keys=(
            "评估结论",
            "风险隐患",
            "备件物资",
            "使用环境",
            "退运报废",
            "第8章",
            "第八章",
            "第9章",
            "第10章",
            "第11章",
            "第十章",
            "第十一章",
        ),
        after_keys=(),
        skip_line_reports=False,
    )
    return _filter_ch7_aspect_flow(
        [x for x in (hit.get("flow") or []) if x.get("kind") in {"para", "table"}]
    )


def _is_ch7_course_line(text: str) -> bool:
    """「1、2025.5《…》培训」年月课表行（不是四分法开段）。"""
    raw = (text or "").strip()
    compact = compact_text(raw)
    return bool(
        re.match(r"^\d+[、．.]\s*20\d{2}", raw)
        or re.match(r"^\d+[、．.]20\d{2}", compact)
        or re.match(r"^20\d{2}[\.．]\d{1,2}", compact)
    )


def _is_ch7_section_switch(text: str, marked: str | None) -> bool:
    """是否为分项开段（①②③④ / 1）2） / 「2、仪器仪表…」），排除「1、2025.5《…》培训」课表行。"""
    if not marked:
        return False
    raw = (text or "").strip()
    compact = compact_text(raw)
    # 带年份的条目清单：培训课表，不是四分法标题
    if _is_ch7_course_line(raw):
        return False
    if compact in {
        "仪器仪表",
        "仪器、仪表",
        "培训",
        "智能化应用",
        "智能化应用的使用情况",
        "生产计划执行",
        "生产计划执行方面",
    }:
        return True
    # ①②③④ 或 1）2）3）4）
    if re.match(r"^[（(]?[①②③④]", compact) or re.match(r"^[（(]?[1-4]）", compact):
        return True
    # 16 号线等：1)生产计划… / 5)…培训… / 6)智能化…
    if re.match(r"^\d+[)）]", compact):
        return True
    # 1、生产计划执行方面 / 2、仪器仪表使用管理方面
    if re.match(r"^[1-4][、．.]", compact) and any(
        k in compact
        for k in (
            "生产计划",
            "仪器仪表",
            "仪器、仪表",
            "管辖仪器",
            "部门年度培训",
            "年度培训",
            "智能化应用",
            "智能化",
        )
    ):
        return True
    return False


def _ch7_marker_aspect(text: str) -> str | None:
    """按开段标记/关键词判断属于计划/仪表/培训/智能哪一块（通用，不绑死某线写法）。"""
    raw = (text or "").strip()
    t = compact_text(raw)
    if not t:
        return None
    # 课表行「1、2025.5《…》培训」：培训正文，不当 1/2/3/4 分项标题
    if _is_ch7_course_line(raw):
        return "train" if "培训" in t else None
    # 16 号线等：1)… / 5)…培训… / 6)智能化…（括号序号，不是 1、课表）
    m_paren = re.match(r"^(\d+)[)）]", t)
    if m_paren:
        if "培训" in t:
            return "train"
        if "智能" in t:
            return "smart"
        if any(k in t for k in ("仪器", "仪表", "工具", "兆欧表", "万用表", "钳形表")):
            return "meter"
        if any(k in t for k in ("生产计划", "计划执行", "欠修")):
            return "plan"
    # 分项开段：①②③④ / 1）2）3）4） / 明确小标题（不要用普通「1、2、3、4、」清单号）
    if (
        re.match(r"^[（(]?[①1]）", t)
        or t.startswith("①")
        or t.startswith("生产计划执行")
        or t.startswith("1、生产计划")
        or (re.match(r"^[（(]?1）", t) and "计划" in t)
    ):
        if not any(k in t[:24] for k in ("培训", "智能", "仪器")):
            return "plan"
    if (
        re.match(r"^[（(]?[②2]）", t)
        or t.startswith("②")
        or t in {"仪器仪表", "仪器、仪表"}
        or t.startswith("仪器仪表")
        or t.startswith("2、仪器")
        or ("维护类工具" in t and "仪表" in t)
        or ("管辖仪器仪表" in t)
        or ("仪器、仪表没有缺少" in t)
        or (re.match(r"^[（(]?2）", t) and ("仪器" in t or "仪表" in t))
    ):
        return "meter"
    if (
        re.match(r"^[（(]?[③3]）", t)
        or t.startswith("③")
        or t == "培训"
        or t.startswith("部门年度培训")
        or t.startswith("年度培训")
        or (t.startswith("3、") and "培训" in t[:24])
        or (re.match(r"^[（(]?3）", t) and "培训" in t)
        or ("培训" in t[:16] and ("人次" in t or "月月练" in t or "共进行" in t))
    ):
        return "train"
    if (
        re.match(r"^[（(]?[④4]）", t)
        or t.startswith("④")
        or t.startswith("智能化")
        or t.startswith("4、智能")
        or (re.match(r"^[（(]?4）", t) and "智能" in t)
    ):
        return "smart"
    # 无标题时靠正文关键词（勿用清单号跳桶）
    if any(k in t for k in ("计量器具", "兆欧表", "万用表", "钳形表", "维护类工具、仪表", "甲供，多用表", "仪器、仪表没有缺少")):
        if "培训" in t and re.match(r"^\d+[、．.]", raw):
            return "train"
        return "meter"
    if any(
        k in t
        for k in (
            "月月练",
            "人次",
            "魔学院",
            "主题培训",
            "岗位能力评估及考核",
            "已经基本满足了培训要求",
            "培训大纲",
            "培训内容如下",
        )
    ):
        return "train"
    if any(
        k in t
        for k in (
            "智能运维平台",
            "巡检机器人",
            "故障录波",
            "视频查看所有的变电站",
            "辅助巡检功能",
            "PAD巡视",
            "智能温湿度计",
            "智能化应用的使用情况",
            "智能采集",
        )
    ):
        return "smart"
    if any(k in t for k in ("生产计划共计", "触发生产计划", "计划完成率", "不存在欠修", "无设备欠修", "生产计划总数")):
        return "plan"
    return None


def _split_ch7_ops_blob(flow: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """把运维表现整段按标记拆成 plan/meter/train/smart。

    只在分项开段换桶；「1、2025.5《培训》」课表行留在当前培训桶，不因序号误跳到仪器/智能。
    """
    buckets: dict[str, list[dict[str, Any]]] = {"plan": [], "meter": [], "train": [], "smart": []}
    cur: str | None = None
    for item in flow or []:
        if item.get("kind") == "table":
            if cur:
                buckets[cur].append(item)
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if "评估规范第7部分" in text or ("①统计生产计划" in text and "②统计" in text):
            continue
        marked = _ch7_marker_aspect(text)
        compact = compact_text(text)
        if _is_ch7_section_switch(text, marked):
            cur = marked
            if len(compact) > 36 or (
                marked
                and any(
                    k in compact
                    for k in ("没有缺少", "人次", "配置足额", "加装了", "共进行", "培训", "智能", "生产计划")
                )
            ):
                buckets[cur].append({"kind": "para", "text": text})
            continue
        # 尚无分项标题：正文关键词落桶；课表行不换桶；「1、视频查看…」等智能清单可换桶
        if cur is None and marked:
            cur = marked
        elif marked and marked != cur and not _is_ch7_course_line(text):
            cur = marked
        if cur is None:
            continue
        buckets[cur].append(item if item.get("kind") == "para" else {"kind": "para", "text": text})
    return buckets


def _trim_ch7_aspect_bleed(flow: list[dict[str, Any]] | None, aspect_id: str) -> list[dict[str, Any]]:
    """按标题切片后，若正文已进入其它分项（③培训/④智能等），从此截断，避免串进仪器节。"""
    out: list[dict[str, Any]] = []
    for item in flow or []:
        if item.get("kind") == "table":
            out.append(item)
            continue
        if item.get("kind") != "para":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        marked = _ch7_marker_aspect(text)
        # 仅在真正分项开段处截断；课表「1、2025.5《培训》」不截断
        if marked and marked != aspect_id and _is_ch7_section_switch(text, marked):
            break
        out.append(item)
    return out


def _harvest_ch7_named_line_paras(
    docs: list[DocumentModel] | None,
    *,
    aspect_id: str,
    by_no: dict[int, dict[str, Any]],
) -> None:
    """材料位置会变：不绑文件名/文件夹，凡段首点名 N 号线且能判定为本分项的段落，并入 N。

    专册标题切不到、或写在旁线合订本里时，靠这条补漏。
    """
    for d in docs or []:
        if not _is_ch7_power_line_doc(d):
            continue
        src = _src(d)
        for block in d.blocks or []:
            if getattr(block, "type", "") not in {"paragraph", "heading"}:
                continue
            text = str(getattr(block, "text", "") or "").strip()
            if len(text) < 12:
                continue
            ln = _leading_line_no(text)
            if ln is None:
                continue
            if _ch7_marker_aspect(text) != aspect_id:
                continue
            _merge_ch7_line_items(by_no[ln], [{"kind": "para", "text": text}], source=src)


def _extract_ch7_aspect_by_line(
    docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    aspect_id: str,
) -> dict[str, Any]:
    """7.2.2～7.2.4：按 1～18 号线填空；无线则黄空。不拿去年顶。

    归线规则（不写死材料落在哪个文件/哪个维护部）：
    1) 文件名主线 → 该线运维段分桶；
    2) 段首点名其它号线 → 改挂到该线；
    3) 全文再扫一遍段首号线+分项关键词，防止节名/位置变更漏抽。
    """
    by_no: dict[int, dict[str, Any]] = {i: _empty_ch7_line_sec(i) for i in range(1, 19)}
    host_done: set[int] = set()
    pool = sorted(
        [x for x in (docs or []) if _is_ch7_power_line_doc(x)],
        key=lambda x: (_line_no_from_doc(x) or 99, _src(x)),
    )
    for d in pool:
        host = _line_no_from_doc(d)
        # 优先①②③④整段分桶，避免「仪器」标题切片吃到后面培训/智能
        blob = _ch7_ops_section_flow(d)
        split_flow = _filter_ch7_aspect_flow(_split_ch7_ops_blob(blob).get(aspect_id) or [])
        if not split_flow:
            one = extract_named_section(
                [d],
                start_keys=start_keys,
                stop_keys=_CH7_72_STOP,
                after_keys=(),
                skip_line_reports=False,
            )
            split_flow = _trim_ch7_aspect_bleed(
                _filter_ch7_aspect_flow(
                    [x for x in (one.get("flow") or []) if x.get("kind") in {"para", "table"}]
                ),
                aspect_id,
            )
        host_items: list[dict[str, Any]] = []
        foreign: dict[int, list[dict[str, Any]]] = {}
        for item in split_flow or []:
            if item.get("kind") == "para":
                fl = _foreign_line_subject(str(item.get("text") or ""), host)
                if fl is not None:
                    foreign.setdefault(fl, []).append(item)
                    continue
            host_items.append(item)
        src = _src(d)
        if host is not None and host not in host_done:
            paras = [str(x.get("text") or "").strip() for x in host_items if x.get("kind") == "para"]
            paras = [p for p in paras if p]
            empty = not (paras or any(x.get("kind") == "table" for x in host_items))
            by_no[host] = {
                "line_no": host,
                "line": f"{host}号线",
                "title": f"轨道交通{host}号线",
                "paras": paras,
                "flow": host_items,
                "source": "" if empty else src,
                "empty": empty,
            }
            host_done.add(host)
        for fl, items in foreign.items():
            _merge_ch7_line_items(by_no[fl], items, source=src)

    # 位置变更补漏：不依赖运维节标题是否还叫「运维表现健康度」
    _harvest_ch7_named_line_paras(pool, aspect_id=aspect_id, by_no=by_no)

    lines = [by_no[i] for i in range(1, 19)]
    filled = [x for x in lines if not x.get("empty")]
    flat_paras: list[str] = []
    flat_flow: list[dict[str, Any]] = []
    for sec in filled:
        flat_paras.extend(sec.get("paras") or [])
        flat_flow.extend(sec.get("flow") or [])
    return {
        "paras": flat_paras,
        "flow": flat_flow,
        "source": "、".join(dict.fromkeys(s.get("source") or "" for s in filled if s.get("source")))[:160],
        "via": "year" if filled else "",
        "lines": lines,
    }


def extract_ch7_quality(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """第 7 章 7.2：固定骨架 + 按内容填空。

    - 开篇句：今年非线路总述 → 去年/保底 → 空（不成文乱抓单线稿）
    - 表7-1：只认当年生产计划表，没有则空（成文黄 7.2.1）
    - 7.2.1 正文：只认非线路总述，不把各线计划散文堆进来
    - 7.2.2～7.2.4：按线路从变电线报告填；无材料该线黄空；不用去年顶数
    """
    from chapters.power.style import CH7_72_SECTIONS

    plan_table = extract_plan_table(docs)
    lead = _extract_ch7_lead(docs, prior_docs)
    aspects: dict[str, Any] = {}
    for spec in CH7_72_SECTIONS:
        aid = spec["id"]
        if aid == "plan":
            aspects[aid] = _extract_ch7_plan_prose(docs)
            continue
        if spec.get("by_line"):
            aspects[aid] = _extract_ch7_aspect_by_line(
                docs,
                start_keys=tuple(spec["start_keys"]),
                aspect_id=aid,
            )
            continue
        aspects[aid] = _empty_ch7_aspect()
    # 今年已按四分法抽到线路正文时：开篇跟四分法体例，不用去年「维保管理/新线路接管」旧导语顶上来
    has_line_body = any(
        any(not ln.get("empty") for ln in ((aspects.get(aid) or {}).get("lines") or []))
        for aid in ("meter", "train", "smart")
    )
    if has_line_body:
        year_lead_ok = (lead.get("via") == "year") and bool(lead.get("paras") or lead.get("flow"))
        prior_old = (lead.get("via") == "prior") and any(
            k in "".join(lead.get("paras") or []) for k in ("维保管理", "新线路接管", "新技术应用", "故障处理流程")
        )
        if (not year_lead_ok and not (lead.get("paras") or lead.get("flow"))) or prior_old:
            from chapters.power.style import CH7_QUALITY_LEAD

            lead = {
                "paras": [CH7_QUALITY_LEAD],
                "flow": [{"kind": "para", "text": CH7_QUALITY_LEAD}],
                "source": "",
                "via": "style",
            }
    return {
        "lead": lead,
        "plan_table": plan_table,
        "aspects": aspects,
        "source": plan_table.get("source") or "",
        "table": plan_table.get("table") or [],
        "flow": plan_table.get("flow") or [],
    }


def extract_overviews(docs: list[DocumentModel], *, year: int = 2026) -> list[dict[str, Any]]:
    """第 1 章 1.2：从各线变电评估报告抽「线路概述」。接触网/SCADA/能耗等线路稿不要。"""
    by_line: dict[str, dict[str, Any]] = {}
    for doc in docs or []:
        if not _is_line_report(doc):
            continue
        name = _src(doc)
        # 第 1 章只要变电专业线路稿；接触网/检测检修/SCADA 线路报告不进 1.2。
        if any(k in name for k in ("接触网", "检测检修", "SCADA", "能耗")):
            continue
        found = LINE_IN_NAME.search(name)
        if not found:
            continue
        line = f"{int(found.group(1))}号线"
        if line in by_line:
            continue
        take = False
        paras: list[str] = []
        flow: list[dict[str, Any]] = []
        for block in doc.blocks:
            t = (block.text or "").strip()
            if block.type in {"heading", "paragraph"} and (
                t == "线路概述"
                or t.startswith("线路概述")
                or t.endswith("线路概述")
                or t in {"线路基本情况", "1.线路基本情况"}
                or t.startswith("1.线路基本情况")
            ):
                take = True
                continue
            if not take:
                continue
            if t in {"线路基本情况", "全线变电站汇总情况：", "全线变电站汇总情况"} or t.startswith("管辖线路"):
                continue
            if t.startswith(("日常工作", "设施设备", "功能有效性", "车站情况", "设备数量", "2.设备数量", "2.设备")):
                break
            if block.type == "table":
                head = "".join(str(c) for c in (block.rows or [[]])[0])
                if any(k in head for k in ("车站", "设备数量", "变电站", "公里")):
                    break
                flow.append(_table_item(block, doc))
                continue
            if block.type == "drawing":
                flow.append(_drawing_item(doc, block))
                continue
            if block.type == "formula":
                item = _flow_item(doc, block)
                if item:
                    flow.append(item)
                continue
            if t.startswith("图") and len(t) < 80 and len(t) > 1 and (t[1].isdigit() or t[1] in " -"):
                flow.append({"kind": "para", "text": t})
                continue
            if t and len(t) > 10:
                paras.append(t)
                flow.append({"kind": "para", "text": t})
            if len(paras) >= 4:
                break
        if paras or flow:
            by_line[line] = {"line": line, "source": name, "paras": paras, "flow": flow}
    return [by_line[f"{i}号线"] for i in range(1, 19) if f"{i}号线" in by_line]


def extract_env(docs: list[DocumentModel], *, year: int = 2026) -> dict[str, Any]:
    """第 10 章：从各线变电评估报告抽「使用环境符合性评估」，按 1～18 号线汇总。

    - 认小节全名，避免「从使用环境方面…」误触发；
    - 触网/弓架次类稿降权丢掉；变电粉尘/温湿度优先；
    - 同年优先，缺线可用上一年线路稿补。
    """
    stop = (
        "退运",
        "评估结论",
        "备件物资",
        "风险隐患",
        "11.1",
        "第11章",
        "第十一章",
        "评估小结",
        "运维表现",
        "管理体系合规",
        "修程修制",
        "运营契合",
    )
    by_line: dict[int, dict[str, Any]] = {}
    flat_candidates: list[dict[str, Any]] = []

    for doc in docs or []:
        name = _src(doc)
        path = doc.source_path or ""
        # 纯接触网分册不进供电第 10 章
        if _is_overhead_annual(doc) and "变电" not in name:
            continue
        if any(k in name for k in ("接触网", "触网")) and "变电" not in name:
            continue
        sliced = _slice_env_blocks(doc, stop=stop)
        if not sliced:
            continue
        paras = sliced["paras"]
        flow = sliced["flow"]
        score = _env_content_score(name, paras, flow)
        if score < 0:
            continue
        year_rank = _env_doc_year_rank(path, name, year)
        lines = [int(x) for x in LINE_IN_NAME.findall(name)]
        if not lines:
            lines = _retire_line_nos_in_text(name)
        payload = {
            "source": name,
            "source_path": path,
            "paras": paras,
            "flow": flow,
            "score": score,
            "year_rank": year_rank,
        }
        if not lines:
            flat_candidates.append(payload)
            continue
        for ln in lines:
            if not (1 <= ln <= 18):
                continue
            prev = by_line.get(ln)
            if prev is None or (year_rank, -score) < (prev["year_rank"], -prev["score"]):
                by_line[ln] = payload

    sections: list[dict[str, Any]] = []
    src_names: list[str] = []
    for i in range(1, 19):
        hit = by_line.get(i)
        if not hit:
            sections.append(
                {
                    "line": f"{i}号线",
                    "line_no": i,
                    "title": f"轨道交通{i}号线",
                    "paras": [],
                    "flow": [],
                    "source": "",
                    "empty": True,
                }
            )
            continue
        src_names.append(hit["source"])
        sections.append(
            {
                "line": f"{i}号线",
                "line_no": i,
                "title": f"轨道交通{i}号线",
                "paras": hit["paras"],
                "flow": hit["flow"],
                "source": hit["source"],
                "empty": False,
            }
        )

    filled = [s for s in sections if not s.get("empty")]
    # 无线路稿时：退回「单份最完整」的供电环境材料（兼容旧测试/汇总稿）
    if not filled and flat_candidates:
        best = max(flat_candidates, key=lambda c: (c["score"], -c["year_rank"]))
        return {
            "source": best["source"],
            "paras": best["paras"],
            "flow": best["flow"],
            "lead_paras": [],
            "lead_flow": [],
            "sections": sections,
            "year": int(year),
        }

    return {
        "source": "、".join(dict.fromkeys(src_names))[:160],
        "paras": [p for s in filled for p in (s.get("paras") or [])],
        "flow": [],
        "lead_paras": [],
        "lead_flow": [],
        "sections": sections,
        "year": int(year),
    }


def _is_env_section_start(text: str) -> bool:
    """认「使用环境符合性评估」小节，勿匹配「从使用环境方面降低故障率」。"""
    t = (text or "").strip()
    compact = compact_text(t)
    if not compact:
        return False
    if hits_section_key(compact, ("使用环境符合性评估", "使用环境符合", "环境符合性评估", "10.1")):
        return True
    if compact in {"使用环境", "10.1环境符合性评估"}:
        return True
    if compact.startswith("使用环境符合") and len(compact) <= 40:
        return True
    if compact.startswith("使用环境") and len(compact) <= 16 and "方面" not in compact:
        return True
    return False


def _env_doc_year_rank(path: str, name: str, year: int) -> int:
    """越接近评估年越好（0 最好）。"""
    blob = f"{path}|{name}"
    years = [int(x) for x in re.findall(r"(20\d{2})", blob)]
    if not years:
        return 40
    return min(abs(int(year) - y) for y in years)


def _env_content_score(name: str, paras: list[str], flow: list[dict[str, Any]] | None) -> int:
    """变电环境加分；触网弓架次/防雷参数表强降权。"""
    blob = name + "\n" + "\n".join(paras) + "\n".join(
        "|".join(str(c) for c in (item.get("rows") or [[]])[0])
        for item in (flow or [])
        if item.get("kind") == "table"
    )
    score = _section_richness(flow, paras)
    if any(k in name for k in ("维护五部", "维护六部", "维护七部", "接触网", "触网")) and "变电" not in name:
        score -= 120
    catenary_hits = sum(
        1
        for k in ("弓架次", "日弓架次", "避雷器间距", "承力索", "接触网防雷", "棘轮", "无张力补偿", "放电间隙")
        if k in blob
    )
    if catenary_hits >= 2:
        score -= 100
    if any(k in blob for k in ("变电站", "变电所", "除湿机", "粉尘", "温湿度", "电缆层", "凝露", "渗水")):
        score += 25
    if re.search(r"8\.2\.6条款的评估情况撰写", blob) and len(paras) <= 2:
        score -= 15
    return score


def _slice_env_blocks(doc: DocumentModel, *, stop: tuple[str, ...]) -> dict[str, Any] | None:
    paras: list[str] = []
    flow: list[dict[str, Any]] = []
    take = False
    for block in doc.blocks:
        t = (block.text or "").strip()
        compact = compact_text(t)
        if block.type in {"heading", "paragraph"} and _is_env_section_start(t):
            take = True
            continue
        if not take:
            continue
        if block.type in {"drawing", "formula"}:
            item = _flow_item(doc, block)
            if item:
                flow.append(item)
            continue
        if block.type == "table":
            # 弓架次统计表不进供电第 10 章
            head = "".join(str(c) for c in ((block.rows or [[]])[0]))
            if any(k in head for k in ("弓架次", "日弓架次")):
                continue
            flow.append(_table_item(block, doc))
            continue
        if block.type in {"heading", "paragraph"}:
            if hits_section_key(compact, stop, title_only_words=True) or is_foreign_outline(
                compact, keep_keys=("10", "10.1")
            ):
                break
            if re.match(r"^根据上海城市轨道交通设施设备运营评估规范.*8\.2\.6", t):
                continue
            if t in {"使用环境符合性评估", "环境符合性评估", "使用环境"}:
                continue
            if t and t not in paras:
                paras.append(t)
                flow.append({"kind": "para", "text": t})
    kept = [p for p in paras if len(p) > 8]
    keep = set(kept)
    flow = dedupe_flow_items(
        [x for x in flow if x.get("kind") in {"drawing", "table", "formula"} or x.get("text") in keep]
    )
    if not kept and not flow:
        return None
    return {"paras": kept, "flow": flow}


def extract_all(
    docs: list[DocumentModel],
    *,
    year: int = 2026,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """一次抽出第 1～11 章 pack。CLI 全年报和网页按章评估都先走这里，再按章取用。

    去年报告规则（全章统一）：
    - 平台上传了去年完整报告 → 用上传稿学目录/体例；
    - 未上传 → 自动用项目内 2025 供电年报保底。
    数据节（总表、4.4、合规 5.3～5.6 等）仍只用当年材料，不用保底顶数。
    ch3.compare_* 依赖 prior_2025_snapshot；没有快照或没有当年供电表则 3.5 为空（黄标题）。
    """
    from chapters.common.source_yellow import register_current_docs
    from chapters.power.prior_resolve import resolve_prior_docs

    docs = prepare_power_docs(docs)
    register_current_docs(docs)
    prior_hit = resolve_prior_docs(prior_docs)
    prior_only = prepare_power_docs(prior_hit.get("docs") or [])
    grades = extract_grade_tables(docs)
    prose = resolve_ch3_prose(docs, prior_only)
    prior = load_prior_2025()
    # 3.5：prior[0/1/2] 对应供电/主变/能源 2025 表，与当年 3.3.2 三张已裁列的表并排。
    cmp_power = compare_years(prior[0], grades["power_table"], year - 1, year) if prior and grades["power_table"] else []
    cmp_main = compare_years(prior[1], grades["main_table"], year - 1, year) if len(prior) > 1 and grades["main_table"] else []
    cmp_energy = compare_years(prior[2], grades["energy_table"], year - 1, year) if len(prior) > 2 and grades["energy_table"] else []
    moves = []
    if prior and grades["power_table"]:
        moves.extend(migrations(prior[0], grades["power_table"]))
    comp = extract_compliance(docs, prior_docs=prior_only)
    ch7_quality = extract_ch7_quality(docs, prior_only)
    ch7 = {
        "source": ch7_quality.get("source") or "",
        "table": ch7_quality.get("table") or [],
        "flow": ch7_quality.get("flow") or [],
        "lead_paras": list((ch7_quality.get("lead") or {}).get("paras") or []),
        "lead_flow": list((ch7_quality.get("lead") or {}).get("flow") or []),
        "lead_source": (ch7_quality.get("lead") or {}).get("source") or "",
        "lead_via": (ch7_quality.get("lead") or {}).get("via") or "",
        "aspects": ch7_quality.get("aspects") or {},
    }
    org = extract_org_mode(docs, prior_only)
    ch7["org_paras"] = list(org.get("paras") or [])
    ch7["org_flow"] = list(org.get("flow") or [])
    ch7["org_source"] = org.get("source") or ""
    ch7["org_via"] = org.get("via") or ""
    # 7.3 全册统一黄空，不抽小结正文（避免把后续章/整本年报吸进来）
    ch7["summary"] = {"paras": [], "flow": [], "source": ""}
    ch8 = extract_ch8(docs, prior_only)
    # 8.2 小结全册统一黄空
    ch8["summary"] = {"paras": [], "flow": [], "source": ""}
    ch9 = enrich_stock_pack(docs, extract_stock(docs))
    ch10 = extract_env(docs, year=year)
    ch10["summary"] = extract_named_section(
        docs,
        start_keys=("评估小结",),
        stop_keys=("退运", "第11章", "第十一章"),
        after_keys=("使用环境",),
    )
    ch11 = extract_retire(docs, year=year)
    ch11["tools"] = extract_named_section(
        docs,
        start_keys=("固定资产工器具", "工器具配置"),
        stop_keys=("评估小结", "第12章", "第十二章", "总结与建议"),
        after_keys=("退运", "报废", "设备退运"),
        skip_line_reports=True,
    )
    ch11["summary"] = extract_named_section(
        docs,
        start_keys=("评估小结",),
        stop_keys=("第12章", "第十二章", "总结与建议", "附录"),
        after_keys=("退运", "报废", "工器具配置", "固定资产工器具"),
    )
    ch2 = {
        "tech_route": extract_named_section(
            docs,
            start_keys=("评估技术路线",),
            stop_keys=("设备功能有效性", "第3章", "第三章"),
            skip_line_reports=False,
        )
    }
    ch12 = {
        "summary": extract_named_section(
            docs, start_keys=("总结", "12.1"), stop_keys=("建议和措施", "12.2", "附录")
        ),
        "advice": extract_named_section(
            docs, start_keys=("建议和措施", "12.2"), stop_keys=("附录",)
        ),
    }
    return {
        "year": year,
        "ch1": {"overviews": extract_overviews(docs, year=year)},
        "ch2": ch2,
        "ch3": {
            **grades,
            "method": prose["method"],
            "standard": prose["standard"],
            "scope": prose["scope"],
            "controls": extract_controls(docs),
            "compare_power": cmp_power,
            "compare_main": cmp_main,
            "compare_energy": cmp_energy,
            "migrations": moves,
            "prior_source": prior_hit.get("source")
            or ("上海轨道交通运营设施设备2025年年度评估报告（供电）" if prior else ""),
        },
        "ch4": build_ch4_pack(docs, year=year, prior_docs=prior_only),
        # 第 5～11 章各自跳过线路报告；线路稿只出现在 ch1.overviews。
        "ch5": comp["ch5"],
        "ch6": comp["ch6"],
        "ch7": ch7,
        "ch8": ch8,
        "ch9": ch9,
        "ch10": ch10,
        "ch11": ch11,
        "ch12": ch12,
        "pdfs": inspect_pdfs(docs),
        "prior_via": prior_hit.get("via") or "",
        "prior_source_label": prior_hit.get("source") or "",
    }


def extract_chapter(
    docs: list[DocumentModel],
    *,
    year: int,
    chapter_id: str,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """网页按章评估入口：仍跑 extract_all（材料一次上传、各章规则都要认），再标 chapter_id 给成文选用。"""
    pack = extract_all(docs, year=year, prior_docs=prior_docs)
    pack["chapter_id"] = chapter_id
    return pack
