# -*- coding: utf-8 -*-
"""按去年/2025 目录逐节从当年材料找内容。

体例（评估方法、维护周期规定等）材料没有才回退去年；状态/故障/库存/退运等数据节
只用当年材料，没有就黄标题，不拿去年数字顶。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text, slice_named_section
from chapters.overhead.outline import CHAPTER_NAMES, is_content_title, is_peer_chapter_title
from chapters.overhead.prior_fallback import fill_section_bundle_first, mark_fallback
from parsers.document_model import DocumentModel

# 这些节是「规定/方法」，可复用去年正文当体例。
PRIOR_BODY_OK = frozenset(
    {
        "评估方法和内容",
        "评估标准",
        "A类设备",
        "B类设备",
        "C类设备",
        "D类设备",
        "设备维护周期和维护内容",
        "接触网专业接触线磨耗预警值上报",
        "接触网 120mm²接触线磨耗预警值规定",
        "接触网 150 mm²接触线磨耗预警值规定",
        "生产组织模式",
        "设施设备运维质量分析",
        "特种设备，消防，防雷，高空作业规程",
        "强制年检或评估情况分析",
        "法律法规的获取情况",
        "制度、标准执行情况检查",
        "依据相关标准制定企业规范的管理制度",
        "关于识别和确认",
        "合规性评价",
        "标准规划流程",
    }
)

# 已有专用抽取（状态表合并等），缺材料也不要用 Excel 明细表顶。
SKIP_GENERIC = frozenset(
    {
        "接触网",
        "接触网设备状态分布",
        "各线路柔性接触网状态分布",
        "各线路刚性接触网状态分布",
        "接触轨状态分布",
        "各线路隔离开关状态分布",
        "各线路隔离开关控制屏状态分布",
        "各线路管控措施",
        "设备体量和变化情况",
        "设备体量",
        "各个线路基本情况",
        "接触网专业接触线磨耗预警值上报",
    }
)

TITLE_ALIASES: dict[str, tuple[str, ...]] = {
    "设备体量变化情况": ("设备体量变化",),
    "设备体量和变化情况": ("设备体量和变化情况", "设备体量变化情况"),
    "各个线路基本情况": ("各个线路基本情况",),
    "设备数量": ("设备数量",),
    "各线路接触网故障趋势分析": ("各线路接触网故障趋势", "接触网故障趋势", "故障趋势分析"),
    "特种设备，消防，防雷，高空作业规程": ("特种设备，消防，防雷，高空作业规程", "特种设备", "高空作业规程"),
    "强制年检或评估情况分析": ("强制年检",),
    "法律法规的获取情况": ("法律法规的获取", "法律法规"),
    "企业标准和制度": ("企业标准和制度", "企业标准"),
    "制度、标准执行情况检查": ("制度、标准执行",),
    "依据相关标准制定企业规范的管理制度": ("依据相关标准制定",),
    "关于识别和确认": ("识别和确认",),
    "合规性评价": ("合规性评价",),
    "标准规划流程": ("标准规划流程",),
    "对上一年度合规性评估建议的整改": ("对上一年度合规性评估建议的整改", "对上一年度合规性"),
    "日常维修计划执行情况": ("日常维修计划执行", "日常维修计划", "生产计划执行"),
    "仪器仪表使用管理方面": ("仪器仪表使用管理", "仪表使用"),
    "部门年度培训方面": ("部门年度培训", "年度培训"),
    "智能化应用": ("智能化应用", "新技术应用"),
    "各线路环境符合性评估": ("各线路环境符合性评估", "环境符合性评估"),
    "维保管理": ("维保管理",),
    "新线路接管": ("新线路接管",),
    "新技术应用": ("新技术应用", "智能化应用"),
    "设施设备年度突出事件分析": ("突出事件分析", "突出事件", "故障分析报告"),
    "接触网安全库存": ("接触网安全库存",),
    "接触网安全库存备品备件": ("接触网安全库存备品备件",),
    "环境差异性评估": ("环境差异性评估",),
    "外来侵限": ("外来侵限", "异物侵限"),
    "接触网专业接触线磨耗预警值上报": ("接触网专业接触线磨耗预警值上报", "磨耗预警值上报"),
    "接触网 120mm²接触线磨耗预警值规定": ("120mm²接触线磨耗预警", "120 mm²接触线磨耗预警"),
    "接触网 150 mm²接触线磨耗预警值规定": ("150mm²接触线磨耗预警", "150 mm²接触线磨耗预警"),
}

SHEET_TO_TITLES: dict[str, tuple[str, ...]] = {}

CHAPTER_H1 = {
    "ch3": "设备功能有效性评估",
    "ch4": "运营契合满足度评估",
    "ch5": "管理体系合规性评估",
    "ch6": "修程修制匹配性评估",
    "ch7": "运维表现健康度评估",
    "ch8": "风险隐患闭环度评估",
    "ch9": "备件物资保障度评估",
    "ch10": "使用环境符合性评估",
    "ch11": "退运报废倾向性评估",
}


def _nonempty(hit: dict[str, Any] | None) -> bool:
    if not hit or hit.get("empty"):
        return False
    if hit.get("paras") or hit.get("flow"):
        return True
    table = hit.get("table") or []
    return len(table) > 1


def _to_fill(hit: dict[str, Any]) -> dict[str, Any]:
    from chapters.overhead.extract import _fill

    table = hit.get("table") or []
    if not table:
        for item in hit.get("flow") or []:
            if item.get("kind") == "table" and item.get("rows"):
                table = item["rows"]
                break
    return _fill(
        paras=hit.get("paras"),
        flow=hit.get("flow"),
        table=table,
        source=hit.get("source") or "",
        sections=hit.get("sections"),
    )


def start_keys_for(title: str, year: int) -> tuple[str, ...]:
    keys = [title]
    keys.extend(TITLE_ALIASES.get(title) or ())
    if "设备退运更换情况" in title:
        keys.extend((f"{year}年设备退运更换", "退运更换", "设备退运"))
    if title.startswith("和") and "评估对比" in title:
        keys.extend(("两年评估对比", "和上年评估对比", f"和{year - 1}年评估对比"))
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        c = compact_text(k)
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(k)
    return tuple(out)


def _chapter_id_from_h1(chapter_h1: str) -> str:
    cur = compact_text(chapter_h1 or "")
    for cid, name in CHAPTER_H1.items():
        if compact_text(name) == cur:
            return cid
    return ""


def foreign_section_stop_titles(chapter_h1: str) -> list[str]:
    """其他章的一级小节名：本章切节时遇到就停，避免 5.6 吞进 6.1 整改。"""
    from chapters.overhead.outline import load_baseline_outlines

    current_id = _chapter_id_from_h1(chapter_h1)
    out: list[str] = []
    for cid, nodes in (load_baseline_outlines() or {}).items():
        if current_id and cid == current_id:
            continue
        for node in nodes or []:
            if int(node.get("depth") or 0) != 1:
                continue
            t = str(node.get("title") or "").strip()
            if t and t != "评估小结":
                out.append(t)
    return out


def stop_keys_for(
    outline: list[dict[str, Any]],
    index: int,
    chapter_h1: str = "",
) -> tuple[str, ...]:
    node = outline[index]
    depth = int(node.get("depth") or 0)
    title = str(node.get("title") or "")
    stops: list[str] = ["评估小结", "总结与建议", "评估结论与建议"]
    cur = compact_text(chapter_h1 or "")
    for name in CHAPTER_NAMES.values():
        if compact_text(name) != cur:
            stops.append(name)
    stops.append("运营契合满意度评估")
    for j in range(index + 1, len(outline)):
        other = outline[j]
        od = int(other.get("depth") or 0)
        ot = str(other.get("title") or "")
        if not ot or ot == title:
            continue
        if od > depth:
            # 短子题（雷电/粉尘）是父节正文里的分项，不是独立切节点
            if len(compact_text(ot)) >= 6:
                stops.append(ot)
            continue
        stops.append(ot)
        if od < depth:
            break
    for n in outline:
        if int(n.get("depth") or 0) == depth:
            ot = str(n.get("title") or "")
            if ot and ot != title:
                stops.append(ot)
    stops.extend(foreign_section_stop_titles(chapter_h1))
    seen: set[str] = set()
    out: list[str] = []
    for s in stops:
        c = compact_text(s)
        if c and c not in seen and c != compact_text(title):
            seen.add(c)
            out.append(s)
    return tuple(out[:120])


def _looks_like_spare_catalog(hit: dict[str, Any] | None) -> bool:
    """备件清册段落（「249 柔性接触网 … 个 8」）不能灌进合规/特种设备。"""
    import re

    n = 0
    for item in (hit or {}).get("flow") or []:
        t = str(item.get("text") or "").strip()
        if re.match(r"^\d{2,4}\s", t) and any(u in t for u in ("个", "米", "套", "台", "根")):
            n += 1
            if n >= 8:
                return True
    return False


def _flow_crossed_chapter(hit: dict[str, Any] | None, *, chapter_h1: str, title: str) -> bool:
    current = chapter_h1 or title
    n = 0
    for item in (hit or {}).get("flow") or []:
        if item.get("kind") != "para":
            continue
        t = str(item.get("text") or "")
        if is_peer_chapter_title(t, current=current):
            n += 1
            if n >= 1:
                return True
    return False


def _hit_para_texts(hit: dict[str, Any] | None) -> list[str]:
    paras = [str(p).strip() for p in ((hit or {}).get("paras") or []) if str(p).strip()]
    if paras:
        return paras
    return [
        str(x.get("text") or "").strip()
        for x in ((hit or {}).get("flow") or [])
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ]


def _looks_like_compact_fault_compare(hit: dict[str, Any] | None) -> bool:
    from chapters.overhead.extract import is_fault_compare_para

    return sum(1 for t in _hit_para_texts(hit) if is_fault_compare_para(t)) >= 3


def _looks_like_fault_trend_only(hit: dict[str, Any] | None) -> bool:
    """「和上年评估对比」不能灌进 4.3 典型故障叙述；线路故障次数对照句保留给 4.4。"""
    if _looks_like_compact_fault_compare(hit):
        return False
    blob = "".join(_hit_para_texts(hit))
    if "故障次数" not in blob and "自检自修" not in blob:
        return False
    return "系统状态" not in blob and "表3-10" not in blob and "刚性接触网" not in blob


def _reject_generic_hit(hit: dict[str, Any] | None, *, title: str, chapter_h1: str) -> bool:
    if not _nonempty(hit):
        return True
    if "安全库存" in title:
        return False
    if _looks_like_spare_catalog(hit):
        return True
    if _flow_crossed_chapter(hit, chapter_h1=chapter_h1, title=title):
        return True
    paras = hit.get("paras") or []
    flow = hit.get("flow") or []
    blob = " ".join(str(p) for p in paras[:25]) + " ".join(
        str(x.get("text") or "") for x in flow[:25] if x.get("kind") == "para"
    )
    if "退运" in title and ("不写" in blob[:400] or "（不写）" in blob):
        return True
    if "整改" in title:
        pw = (
            blob.count("变压器")
            + blob.count("整流机组")
            + blob.count("变电站")
            + blob.count("SCADA")
            + blob.count("电能计量")
            + blob.count("杂散电流")
        )
        oh = blob.count("接触网") + blob.count("触网") + blob.count("接触轨")
        if pw > oh:
            return True
    if "企业标准" in title and any(k in blob for k in ("安全库存管理规定", "物料名称", "QSD-WBZ-FB-AQ")):
        return True
    if title in {"湿度", "温度", "粉尘"}:
        pw = blob.count("变电") + blob.count("NK11") + blob.count("整流")
        oh = blob.count("接触网") + blob.count("触网") + blob.count("接触轨")
        if pw > oh + 2:
            return True
    if len(paras) > 40 or len(flow) > 50:
        if "整改" in title and any(k in blob for k in ("接触网", "触网", "接触轨")):
            return False
        return True
    return False


def _excel_sheet_hit(docs: list[DocumentModel], title: str) -> dict[str, Any] | None:
    wanted = compact_text(title)
    for sheet, titles in SHEET_TO_TITLES.items():
        if wanted not in {compact_text(t) for t in titles}:
            continue
        hit = fill_section_bundle_first(
            docs,
            None,
            start_keys=(sheet,),
            stop_keys=("工作表",),
            table_predicate=lambda rows: 1 < len(rows) <= 80,
        )
        if _nonempty(hit):
            return hit
    return None


def _search_year(
    docs: list[DocumentModel],
    *,
    title: str,
    starts: tuple[str, ...],
    stops: tuple[str, ...],
    chapter_h1: str,
    year: int | None = None,
) -> dict[str, Any]:
    empty = {"paras": [], "flow": [], "source": "", "empty": True}
    from chapters.overhead.material_merge import sanitize_overhead_bundle_hit

    hit = fill_section_bundle_first(
        docs,
        None,
        start_keys=starts,
        stop_keys=stops,
        table_predicate=lambda rows: 1 < len(rows) <= 80,
        chapter_h1=chapter_h1,
        max_blocks=240 if any(k in title for k in ("整改", "生产计划", "退运", "突出事件", "环境差异", "报废")) else 80,
        year=year if "整改" in title else None,
    )
    if _nonempty(hit) and not _reject_generic_hit(hit, title=title, chapter_h1=chapter_h1):
        return hit
    if chapter_h1:
        from chapters.overhead.ch3_status import extract_chapter_body_section

        hit = sanitize_overhead_bundle_hit(
            extract_chapter_body_section(
                docs,
                chapter_h1=chapter_h1,
                start_keys=starts,
                stop_keys=stops,
            )
        )
        if _nonempty(hit) and not _reject_generic_hit(hit, title=title, chapter_h1=chapter_h1):
            return hit
    hit = sanitize_overhead_bundle_hit(
        slice_named_section(
            docs,
            start_keys=starts,
            stop_keys=stops,
            after_keys=(chapter_h1,) if chapter_h1 else (),
        )
    )
    if _nonempty(hit) and not _reject_generic_hit(hit, title=title, chapter_h1=chapter_h1):
        return hit
    sheet = _excel_sheet_hit(docs, title)
    if sheet and not _reject_generic_hit(sheet, title=title, chapter_h1=chapter_h1):
        return sheet
    return empty


def _is_assignment_brief(text: str) -> bool:
    """部门稿里的出题说明（按规范某条撰写）不是年报正文。"""
    t = (text or "").strip()
    if not t:
        return True
    if "撰写" in t and any(k in t for k in ("评估规范", "条款", "评估情况")):
        return True
    return False


def _is_lead_caption(text: str) -> bool:
    """章导语不带图表题注（表已被丢掉，题注单独留下会像空挂）。"""
    t = (text or "").strip()
    if len(t) < 2 or len(t) >= 80 or t[0] not in {"图", "表"}:
        return False
    return t[1].isdigit() or t[1] in " -"


def _trim_chapter_lead(hit: dict[str, Any]) -> dict[str, Any]:
    """章标题下只留短导语：不要出题说明、附图、标准目录表和单设备作业细节。"""
    flow: list[dict[str, Any]] = []
    npara = 0
    for x in hit.get("flow") or []:
        kind = x.get("kind")
        if kind in {"drawing", "table", "formula"}:
            continue
        if kind == "para":
            t = str(x.get("text") or "").strip()
            if _is_assignment_brief(t) or _is_lead_caption(t):
                continue
            if re.match(r"^(?:轨道交通)?\d{1,2}号线", t):
                continue
            if any(k in t for k in ("钢轨电位", "降压变电站")):
                continue
            if len(t) > 160 and any(k in t for k in ("作业指导书内", "维护保养周期")):
                continue
            npara += 1
            if npara > 6:
                break
        flow.append(x)
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
    out = dict(hit)
    out["flow"] = flow
    out["paras"] = paras
    out["table"] = []
    out["empty"] = not paras
    return out


def fill_missing_outline_sections(
    docs: list[DocumentModel] | None,
    outline: list[dict[str, Any]],
    prior_docs: list[DocumentModel] | None,
    fills: dict[str, dict[str, Any]],
    *,
    chapter_id: str,
    year: int,
) -> dict[str, dict[str, Any]]:
    """给目录里尚未填上的小节补材料；已有专用结果不覆盖。"""
    out = dict(fills)
    filled_compact = {compact_text(k) for k, v in out.items() if v and not v.get("empty")}
    chapter_h1 = CHAPTER_H1.get(chapter_id) or ""
    material = list(docs or [])
    prior = list(prior_docs or [])

    for i, node in enumerate(outline):
        depth = int(node.get("depth") or 0)
        title = str(node.get("title") or "").strip()
        if not title:
            continue
        c = compact_text(title)
        if depth <= 0:
            if compact_text(title) != compact_text(chapter_h1):
                continue
            starts = start_keys_for(title, year)
            stops = stop_keys_for(outline, i, chapter_h1=chapter_h1)
            child_keys = tuple(
                str(outline[j].get("title") or "")
                for j in range(i + 1, len(outline))
                if int(outline[j].get("depth") or 0) == 1 and str(outline[j].get("title") or "")
            )[:8]
            from chapters.overhead.section_bundle import doc_has_outline_child_after_h1

            lead_docs = [
                d for d in material if doc_has_outline_child_after_h1(d, chapter_h1, child_keys)
            ]
            if not lead_docs:
                continue
            hit = fill_section_bundle_first(
                lead_docs,
                None,
                start_keys=starts,
                stop_keys=stops,
                chapter_h1=chapter_h1,
                max_blocks=16,
            )
            if _nonempty(hit):
                hit = _trim_chapter_lead(hit)
            if _nonempty(hit) and not _reject_generic_hit(hit, title=title, chapter_h1=chapter_h1):
                out[title] = _to_fill(hit)
                filled_compact.add(c)
            continue
        if node.get("content_child") or is_content_title(title):
            continue
        if c in filled_compact:
            continue
        if title in SKIP_GENERIC:
            continue
        if title == "评估小结":
            # 部门汇编稿里的「11.2评估结论」不能灌进各章小结；没有当年专节就黄标题。
            continue

        starts = start_keys_for(title, year)
        stops = stop_keys_for(outline, i, chapter_h1=chapter_h1)
        if "评估对比" in title:
            from chapters.overhead.ch3_status import extract_chapter_body_section

            ch4_compare = "运营契合" in compact_text(chapter_h1 or "")
            if not ch4_compare:
                # 第3章 3.5 只用系统状态对照表，不灌故障次数/典型故障。
                continue
            hit = extract_chapter_body_section(
                material,
                chapter_h1=chapter_h1,
                start_keys=starts,
                stop_keys=stops,
            )
            if not _nonempty(hit):
                hit = fill_section_bundle_first(
                    material,
                    None,
                    start_keys=starts,
                    stop_keys=stops,
                    table_predicate=lambda rows: 1 < len(rows) <= 80,
                    chapter_h1=chapter_h1,
                )
            if _nonempty(hit) and _looks_like_fault_trend_only(hit):
                hit = {"paras": [], "flow": [], "source": "", "empty": True}
            if _nonempty(hit) and not _reject_generic_hit(hit, title=title, chapter_h1=chapter_h1):
                out[title] = _to_fill(hit)
                filled_compact.add(c)
            continue
        hit = _search_year(
            material,
            title=title,
            starts=starts,
            stops=stops,
            chapter_h1=chapter_h1,
            year=year,
        )
        if not _nonempty(hit) and title in PRIOR_BODY_OK:
            hit = fill_section_bundle_first(
                    prior, None, start_keys=starts, stop_keys=stops, chapter_h1=chapter_h1
                )
            if _nonempty(hit):
                hit = mark_fallback(hit)
            else:
                from chapters.overhead.ch3_status import extract_chapter_body_section

                hit = extract_chapter_body_section(
                    prior,
                    chapter_h1=chapter_h1,
                    start_keys=starts,
                    stop_keys=stops,
                )
                if _nonempty(hit):
                    hit = mark_fallback(hit)
        if _nonempty(hit):
            out[title] = _to_fill(hit)
            filled_compact.add(c)
    _drop_parent_child_overlap(outline, out)
    return out


def _fill_para_set(fill: dict[str, Any] | None) -> set[str]:
    texts: set[str] = set()
    for p in (fill or {}).get("paras") or []:
        c = compact_text(str(p))
        if c:
            texts.add(c)
    for x in (fill or {}).get("flow") or []:
        if x.get("kind") != "para":
            continue
        c = compact_text(str(x.get("text") or ""))
        if c:
            texts.add(c)
    return texts


def _child_source_keys(fill: dict[str, Any] | None) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for x in (fill or {}).get("flow") or []:
        if x.get("kind") not in {"drawing", "table"}:
            continue
        idx = x.get("source_index")
        if idx is None:
            continue
        try:
            keys.add((str(x.get("source_path") or ""), int(idx)))
        except (TypeError, ValueError):
            continue
    return keys


def _strip_covered_fill(
    fill: dict[str, Any],
    child_fills: list[dict[str, Any]],
    child_titles: list[str],
) -> dict[str, Any]:
    covered = set()
    source_keys: set[tuple[str, int]] = set()
    for cf in child_fills:
        covered |= _fill_para_set(cf)
        source_keys |= _child_source_keys(cf)
    for t in child_titles:
        c = compact_text(t)
        if c:
            covered.add(c)
    new_flow: list[dict[str, Any]] = []
    for x in fill.get("flow") or []:
        kind = x.get("kind")
        if kind == "para":
            c = compact_text(str(x.get("text") or ""))
            if c in covered:
                continue
        elif kind in {"drawing", "table"}:
            idx = x.get("source_index")
            if idx is not None:
                try:
                    key = (str(x.get("source_path") or ""), int(idx))
                except (TypeError, ValueError):
                    key = ("", -1)
                if key in source_keys:
                    continue
        new_flow.append(x)
    new_paras = [p for p in (fill.get("paras") or []) if compact_text(str(p)) not in covered]
    hit = dict(fill)
    hit["flow"] = new_flow
    hit["paras"] = new_paras
    has_body = bool(new_paras) or any(
        x.get("kind") in {"para", "table", "drawing", "formula"} for x in new_flow
    ) or (len(hit.get("table") or []) > 1)
    hit["empty"] = not has_body
    return hit


def _drop_parent_child_overlap(outline: list[dict[str, Any]], fills: dict[str, dict[str, Any]]) -> None:
    """父节若整段搬进了子节正文，只留父节独有导语。"""
    for i, node in enumerate(outline):
        title = str(node.get("title") or "").strip()
        fill = fills.get(title)
        if not title or not _nonempty(fill):
            continue
        depth = int(node.get("depth") or 0)
        child_titles: list[str] = []
        child_fills: list[dict[str, Any]] = []
        for j in range(i + 1, len(outline)):
            other = outline[j]
            if int(other.get("depth") or 0) <= depth:
                break
            ct = str(other.get("title") or "").strip()
            if not ct or len(compact_text(ct)) < 6:
                continue
            child_titles.append(ct)
            cf = fills.get(ct)
            if _nonempty(cf):
                child_fills.append(cf)
        if not child_fills:
            continue
        fills[title] = _strip_covered_fill(fill, child_fills, child_titles)
