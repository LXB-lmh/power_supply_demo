# -*- coding: utf-8 -*-
"""第7章运维质量：部门稿按①计划/②仪表/③培训/④智能切，通稿挂到该部各线。

不写死书名、条号、部门。材料没有的线路不编造。
"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text, dedupe_flow_items
from chapters.overhead.line_topics import (
    _block_item,
    _line_title,
    _skip_power_topic_para,
)
from chapters.overhead.outline import is_peer_chapter_title
from chapters.overhead.section_bundle import sort_docs_newest_last
from parsers.document_model import DocumentModel

ASPECT_TITLES = {
    "meter": "仪器仪表使用管理方面",
    "train": "部门年度培训方面",
    "smart": "智能化应用",
}

# 与 7.2.1～7.2.4 骨架一致的开篇（无数字）；有线路分项时不用去年「维保管理」旧导语。
CH7_QUALITY_LEAD = (
    "从日常维修计划执行情况、仪器仪表使用管理方面、部门年度培训方面、智能化应用等几个方面"
    "进行设施设备运维质量的分析和评估。"
)
_LINE_LEAD = re.compile(
    r"^(?:[（(]?\d{1,2}[、.．)）]\s*)?(?:轨道交通)?(\d{1,2})\s*号线"
    r"(?:\s*[：:]|接触网|接触轨|：)"
)
_LINE_ANY = re.compile(r"(?:轨道交通)?(\d{1,2})\s*号线")
_BARE_LINE = re.compile(r"^(?:轨道交通)?(\d{1,2})\s*号线\s*$")
_CN_LINE = (
    ("十八", "18"),
    ("十七", "17"),
    ("十六", "16"),
    ("十五", "15"),
    ("十四", "14"),
    ("十三", "13"),
    ("十二", "12"),
    ("十一", "11"),
    ("十", "10"),
    ("九", "9"),
    ("八", "8"),
    ("七", "7"),
    ("六", "6"),
    ("五", "5"),
    ("四", "4"),
    ("三", "3"),
    ("二", "2"),
    ("一", "1"),
)
_BARE_NONE = re.compile(r"^(不存在|无|无一缺漏|暂无缺少情况|目前工器具暂无缺少情况)[。；;！!]*$")
_ASSIGN = re.compile(r"评估情况撰写|评估规范第7部分")
_COURSE = re.compile(r"^\d+[、．.]\s*20\d{2}")
_STOP_CH = (
    "风险隐患闭环度",
    "备件物资保障",
    "使用环境符合",
    "退运报废倾向",
    "评估结论与建议",
)
_POWER_WIN = ("交直流屏", "铅酸电池", "35kV", "35KV", "1500v设备改造", "继保箱", "综保装置")
_OH_WIN = ("接触网运维", "接触轨运维", "检测小车", "在用维护仪器仪表")
_GENERIC_WHO = ("我部", "本部门", "各供电维护", "各触网部门", "我单位")


def _norm_lines(text: str) -> str:
    """九号线、十八号线写成 9号线、18号线，后面统一按数字认。"""
    t = text or ""
    for cn, num in _CN_LINE:
        t = t.replace(f"{cn}号线", f"{num}号线")
    return t


def _lines_in(text: str) -> list[int]:
    out: list[int] = []
    for m in _LINE_ANY.finditer(_norm_lines(text)):
        n = int(m.group(1))
        if 1 <= n <= 18 and n not in out:
            out.append(n)
    return out


def _jurisdiction_lines(text: str) -> list[int]:
    """「管辖……接触网/接触轨」里点到的每一条线都算，不因中间出现一次「接触网」就停。"""
    t = _norm_lines(text)
    if "管辖" not in t:
        return []
    found: list[int] = []
    for part in re.split(r"[。；;]", t):
        if "管辖" not in part:
            continue
        if "接触网" not in part and "接触轨" not in part:
            continue
        for n in _lines_in(part):
            if n not in found:
                found.append(n)
    return found


def _line_lead(text: str) -> int | None:
    t = _norm_lines(text).strip()
    bare = _BARE_LINE.match(t)
    if bare:
        n = int(bare.group(1))
        return n if 1 <= n <= 18 else None
    m = _LINE_LEAD.match(t)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def _is_assign(text: str) -> bool:
    t = text or ""
    if _ASSIGN.search(t) and ("①" in t or "统计生产计划" in t):
        return True
    return "①统计生产计划" in compact_text(t) and "②统计" in compact_text(t)


def _is_clause_switch(text: str) -> str | None:
    """①②③④ / 智能化应用使用情况 开段。课表「1、2025.5《培训》」不算。"""
    raw = (text or "").strip()
    t = compact_text(raw)
    if not t or _COURSE.match(raw):
        return None
    if t.startswith("①") or t.startswith("1）") or t.startswith("1)"):
        # ① 计划开段且不含培训/智能/仪器时才判为计划；否则落入后续 ②③④ 判断
        if "计划" in t[:24] and not any(k in t[:20] for k in ("培训", "智能", "仪器")):
            return "plan"
    if (
        t.startswith("②")
        or t.startswith("2）")
        or t.startswith("2)")
        or t.startswith("②统计部门管辖")
        or t.startswith("统计部门管辖的维护仪器")
    ):
        if "仪器" in t or "仪表" in t or "工具" in t:
            return "meter"
    if t.startswith("③") or t.startswith("3）") or t.startswith("3)") or t.startswith("③年度培训"):
        if "培训" in t:
            return "train"
    if (
        t.startswith("④")
        or t.startswith("4）")
        or t.startswith("4)")
        or t.startswith("智能化应用使用情况")
        or t.startswith("④智能化")
    ):
        if "智能" in t or t.startswith("智能化应用使用情况"):
            return "smart"
    if re.match(r"^[1-4][、．.]", t) and any(
        k in t[:36]
        for k in ("生产计划执行", "仪器仪表使用", "部门年度培训", "年度培训方面", "智能化应用")
    ):
        if "生产计划" in t[:36]:
            return "plan"
        if "仪器" in t[:36] or "仪表" in t[:36]:
            return "meter"
        if "培训" in t[:36]:
            return "train"
        if "智能" in t[:36]:
            return "smart"
    if t in {"智能化应用使用情况", "智能化应用的使用情况", "年度培训是否覆盖需求"}:
        return "smart" if "智能" in t else "train"
    return None


def _classify_body(text: str) -> str | None:
    raw = (text or "").strip()
    t = compact_text(raw)
    if not t:
        return None
    if _BARE_NONE.match(raw):
        return "meter"
    if "年度培训" in t or (
        "培训" in t
        and any(k in t for k in ("人次", "学时", "魔学院", "培训计划", "专项培训", "培训周期", "培训工作"))
        and "培训平台" not in t
    ):
        return "train"
    if any(k in t for k in ("仪器仪表", "维护仪器", "在用维护仪器", "工器具暂无缺少", "不存在缺、漏")):
        if "报废" in t and "原值" in t:
            return None
        return "meter"
    if any(
        k in t
        for k in (
            "检测小车",
            "4C小车",
            "线岔检测",
            "放线小车",
            "吊弦预制",
            "智能化应用",
            "验电器",
            "验放电",
            "智能水平仪",
            "在线监测装置",
            "线盘搬运",
            "培训平台",
        )
    ):
        return "smart"
    if any(k in t for k in ("生产计划", "欠修", "完成率")) and "培训" not in t[:12]:
        return "plan"
    return None


def _header_only(text: str, aspect: str) -> bool:
    t = compact_text(text or "")
    if len(t) <= 36 and _is_clause_switch(text) == aspect:
        return True
    if t in {"智能化应用使用情况", "智能化应用的使用情况：", "智能化应用的使用情况"}:
        return True
    return False


def _mentions_single_line(text: str) -> int | None:
    ns = _lines_in(text)
    if len(ns) == 1:
        return ns[0]
    return None


def _is_generic_who(text: str) -> bool:
    t = text or ""
    if _mentions_single_line(t) and not any(k in t for k in _GENERIC_WHO):
        return False
    if any(k in t for k in _GENERIC_WHO):
        return True
    if _mentions_single_line(t):
        return False
    return True


def _numbered_line_item(text: str) -> bool:
    return bool(re.match(r"^[1-4][、．.]", (text or "").strip()))


def _generic_flag(text: str) -> bool:
    t = text or ""
    if _numbered_line_item(t):
        return False
    return bool(any(k in t for k in _GENERIC_WHO) and _mentions_single_line(t) is None)


def _looks_plan_table(rows: list[list[str]] | None) -> bool:
    if not rows:
        return False
    head = "".join(str(c) for c in rows[0])
    return "计划数量" in head and "完成" in head


def _window_is_power(texts: list[str]) -> bool:
    blob = "".join(t for t in texts if t and not _is_assign(t))
    if any(k in blob for k in _OH_WIN):
        return False
    return any(k in blob for k in _POWER_WIN)


def _skip_retire_doc(doc: DocumentModel) -> bool:
    name = doc.source_name or ""
    return "报废" in name and any(k in name for k in ("情况说明", "工器具", "仪器仪表"))


def _iter_window(doc: DocumentModel) -> list:
    blocks = list(doc.blocks or [])
    start = None
    for i, b in enumerate(blocks):
        t = (b.text or "").strip()
        if not t:
            continue
        if "运维表现健康度" in t and len(compact_text(t)) < 40:
            start = i
            break
    if start is None:
        return blocks
    out = []
    for j in range(start, len(blocks)):
        b = blocks[j]
        t = (b.text or "").strip()
        if t and j > start and (
            is_peer_chapter_title(t, current="运维表现健康度评估")
            or any(k in t[:16] for k in _STOP_CH)
        ):
            break
        out.append(b)
    return out


def harvest_ch7_doc(doc: DocumentModel) -> dict[str, Any]:
    """一份部门稿 → 分项按线路 + 通稿。"""
    empty = {
        "dept_lines": set(),
        "specific": {k: {} for k in ASPECT_TITLES},
        "generic": {k: [] for k in ASPECT_TITLES},
        "source": doc.source_name or "",
    }
    if _skip_retire_doc(doc):
        return empty
    blocks = _iter_window(doc)
    texts = [(b.text or "").strip() for b in blocks if (b.text or "").strip()]
    if _window_is_power(texts):
        return empty

    dept_lines: set[int] = set()
    specific: dict[str, dict[int, list]] = {k: {} for k in ASPECT_TITLES}
    generic: dict[str, list] = {k: [] for k in ASPECT_TITLES}
    current_line: int | None = None
    current_aspect: str | None = None

    def put(aspect: str, item: dict[str, Any], line: int | None, *, as_generic: bool = False) -> None:
        if aspect not in ASPECT_TITLES or not item:
            return
        if line is not None:
            bag = specific[aspect].setdefault(line, [])
            sig = compact_text(str(item.get("text") or ""))
            if sig and any(compact_text(str(x.get("text") or "")) == sig for x in bag if x.get("kind") == "para"):
                return
            bag.append(item)
            dept_lines.add(line)
        if as_generic or (line is None):
            g = generic[aspect]
            sig = compact_text(str(item.get("text") or ""))
            if sig and any(compact_text(str(x.get("text") or "")) == sig for x in g if x.get("kind") == "para"):
                return
            if not sig and item.get("kind") not in {"table", "drawing"}:
                return
            g.append(item)

    for block in blocks:
        t = (block.text or "").strip()
        if t and _is_assign(t):
            current_line = None
            current_aspect = None
            dept_lines.update(_jurisdiction_lines(t))
            continue
        if t:
            dept_lines.update(_jurisdiction_lines(t))
        item = _block_item(doc, block)
        if not item:
            continue
        if item.get("kind") == "table" and _looks_plan_table(item.get("rows")):
            current_line = None
            current_aspect = None
            continue
        if item.get("kind") != "para":
            if current_aspect in ASPECT_TITLES:
                put(current_aspect, item, current_line, as_generic=current_line is None)
            continue
        if _skip_power_topic_para(t):
            continue
        if t.startswith("①统计") or (t.startswith("维护") and "办公地点" in t and "管辖范围" in t):
            dept_lines.update(_jurisdiction_lines(t))
            if "管辖范围" in t and "接触网" in t:
                current_line = None
            continue

        lead = _line_lead(t)
        switch = _is_clause_switch(t)
        body = _classify_body(t)

        if switch:
            current_aspect = switch
            current_line = None
            if switch == "plan" or _header_only(t, switch):
                continue
            if switch in ASPECT_TITLES:
                put(switch, item, None, as_generic=True)
            continue

        if lead is not None:
            current_line = lead
            dept_lines.add(lead)
            rest_body = _classify_body(t)
            if rest_body == "plan":
                current_aspect = "plan"
                dept_lines.update(_lines_in(t))
                continue
            if rest_body in ASPECT_TITLES:
                current_aspect = rest_body
                put(rest_body, item, lead, as_generic=_generic_flag(t))
            continue

        named = _lines_in(t)
        if body in ASPECT_TITLES and len(named) >= 2:
            current_aspect = body
            for n in named:
                put(body, item, n)
            current_line = named[-1]
            continue

        if _BARE_NONE.match(t) and current_aspect in {None, "plan", "meter"}:
            current_aspect = "meter"
            if current_line is not None and ("工器具暂无" in t or "目前工器具" in t) and _mentions_single_line(t) is None:
                put("meter", item, None, as_generic=True)
            elif current_line is not None:
                put("meter", item, current_line)
            else:
                put("meter", item, None, as_generic=True)
            continue

        aspect = body or current_aspect
        if aspect == "plan":
            current_aspect = "plan"
            dept_lines.update(_lines_in(t))
            continue
        if aspect not in ASPECT_TITLES:
            continue
        if body:
            current_aspect = body
        single = _mentions_single_line(t)
        if single and single != current_line and body in ASPECT_TITLES:
            put(body, item, single)
            continue
        if current_line is not None:
            trailing_generic = (
                aspect == "meter"
                and _mentions_single_line(t) is None
                and ("工器具暂无" in t or "目前工器具" in t)
            )
            if trailing_generic:
                put(aspect, item, None, as_generic=True)
            else:
                put(aspect, item, current_line, as_generic=_generic_flag(t))
        else:
            put(aspect, item, None, as_generic=True)

    if not dept_lines:
        for asp in ASPECT_TITLES:
            dept_lines.update(specific[asp].keys())
    return {
        "dept_lines": dept_lines,
        "specific": specific,
        "generic": generic,
        "source": doc.source_name or "",
    }


def _thin_flow(items: list[dict[str, Any]]) -> bool:
    paras = [str(x.get("text") or "").strip() for x in items if x.get("kind") == "para"]
    if any(x.get("kind") in {"table", "drawing"} for x in items):
        return False
    if not paras:
        return True
    return all(_BARE_NONE.match(p) or len(p) <= 6 for p in paras)


def _sections_from_map(
    by_line: dict[int, list[dict[str, Any]]],
    sources: dict[int, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in sorted(by_line):
        flow = dedupe_flow_items(by_line[n])
        paras = [x.get("text") or "" for x in flow if x.get("kind") == "para" and str(x.get("text") or "").strip()]
        if not paras and not any(x.get("kind") in {"table", "drawing"} for x in flow):
            continue
        src = sources.get(n) or ""
        out.append(
            {
                "title": _line_title(n),
                "paras": paras,
                "empty": False,
                "source": src,
                "content_child": True,
                "fill": {
                    "paras": paras,
                    "flow": flow,
                    "table": [],
                    "sections": [],
                    "source": src,
                    "empty": False,
                },
            }
        )
    return out


def extract_overhead_ch7_aspects(docs: list[DocumentModel] | None) -> dict[str, dict[str, Any]]:
    """7.2.2～7.2.4：按线路填。较新的专线正文优先；只有通稿时，较旧材料里的专线句子仍要补上。"""
    chosen: dict[str, dict[int, dict[str, Any]]] = {k: {} for k in ASPECT_TITLES}

    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        rec = harvest_ch7_doc(doc)
        src = rec.get("source") or ""
        dept = set(rec.get("dept_lines") or ())
        for asp in ASPECT_TITLES:
            slot = chosen[asp]
            gen = rec["generic"].get(asp) or []
            for n, items in (rec["specific"].get(asp) or {}).items():
                if not items:
                    continue
                prev = slot.get(n)
                if prev and prev["kind"] == "specific":
                    continue
                if _thin_flow(items):
                    if prev:
                        continue
                    slot[n] = {"items": items, "source": src, "kind": "thin"}
                    continue
                slot[n] = {"items": items, "source": src, "kind": "specific"}
            if not gen:
                continue
            targets = dept or set((rec["specific"].get(asp) or {}).keys())
            for n in sorted(targets):
                prev = slot.get(n)
                if prev and prev["kind"] in {"specific", "generic"}:
                    continue
                slot[n] = {"items": gen, "source": src, "kind": "generic"}

    out: dict[str, dict[str, Any]] = {}
    for asp, title in ASPECT_TITLES.items():
        by_line: dict[int, list] = {}
        src_map: dict[int, str] = {}
        for n, row in chosen[asp].items():
            by_line[n] = list(row["items"])
            src_map[n] = row["source"]
        sections = _sections_from_map(by_line, src_map)
        src = "、".join(dict.fromkeys(src_map.values()))
        out[title] = {
            "intro": [],
            "sections": sections,
            "source": src,
            "empty": not sections,
        }
        out[f"_lines_{title}"] = {
            "sections": sections,
            "source": src,
            "empty": not sections,
        }
    return out


def _is_org_title_para(text: str) -> bool:
    t = compact_text(text or "")
    t = re.sub(r"^7\.1", "", t)
    if t in {"生产组织模式", "生产组织"}:
        return True
    return t.startswith("生产组织") and len(t) <= 16 and "自主" not in t and "维护" not in t


def _strip_org_title(flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        x
        for x in flow
        if not (
            x.get("kind") == "para"
            and _is_org_title_para(str(x.get("text") or ""))
        )
    ]


def extract_overhead_org(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, Any]:
    """7.1：完整组织模式（自主委外 / 多维护部）。单部「管辖范围」不当总述。"""
    from chapters.overhead.section_bundle import extract_subsection_bundle

    def _full_org(flow: list[dict[str, Any]]) -> bool:
        blob = "".join(str(x.get("text") or "") for x in flow if x.get("kind") == "para")
        if "自主委外" in blob:
            return True
        return "维护一部" in blob and "维护五部" in blob

    def _pack(flow: list[dict[str, Any]], source: str) -> dict[str, Any]:
        flow = _strip_org_title(dedupe_flow_items(flow))
        return {
            "flow": flow,
            "paras": [str(x.get("text") or "") for x in flow if str(x.get("text") or "").strip()],
            "source": source,
            "empty": not flow,
        }

    def _from(pool: list[DocumentModel] | None) -> dict[str, Any] | None:
        for doc, _idx in sort_docs_newest_last(pool or []):
            hit = extract_subsection_bundle(
                doc,
                start_keys=("生产组织模式", "生产组织"),
                stop_keys=("设施设备运维质量", "日常维修计划", "仪器仪表"),
                chapter_h1="运维表现健康度评估",
                max_blocks=60,
            )
            flow = [x for x in (hit or {}).get("flow") or [] if x.get("kind") == "para"]
            if hit and _full_org(flow):
                return _pack(flow, doc.source_name or "")
            paras: list[dict[str, Any]] = []
            take = False
            for block in doc.blocks or []:
                t = (block.text or "").strip()
                if not t:
                    continue
                if "自主委外" in t or (t.startswith("生产组织") and len(t) < 20):
                    take = True
                    if _is_org_title_para(t):
                        continue
                if take:
                    if is_peer_chapter_title(t, current="生产组织模式"):
                        break
                    if any(k in t[:12] for k in ("设施设备运维", "日常维修", "仪器仪表")):
                        break
                    if _is_org_title_para(t):
                        continue
                    paras.append({"kind": "para", "text": t})
                    if len(paras) >= 24:
                        break
            if _full_org(paras):
                return _pack(paras, doc.source_name or "")
        return None

    def _append_year_tail(pack: dict[str, Any], pool: list[DocumentModel] | None) -> dict[str, Any]:
        """九部总述之后，当年部门稿里计划维修段后的平推/差异化句补上（不把部门计划表当总述）。"""
        have = {compact_text(str(x.get("text") or "")) for x in pack.get("flow") or []}
        extra: list[str] = []
        for doc, _idx in reversed(list(sort_docs_newest_last(pool or []))):
            take = False
            bag: list[str] = []
            for block in doc.blocks or []:
                t = (block.text or "").strip()
                if not t:
                    continue
                if "计划维修、故障维修" in t:
                    take = True
                    continue
                if not take:
                    continue
                if any(
                    k in t[:20]
                    for k in (
                        "根据20",
                        "日常维修计划执行",
                        "生产计划执行情况",
                        "风险隐患闭环",
                        "①统计",
                        "设施设备运维质量",
                        "仪器仪表",
                    )
                ):
                    break
                if is_peer_chapter_title(t, current="生产组织模式"):
                    break
                if _is_org_title_para(t) or len(t) < 8:
                    continue
                bag.append(t)
            if len(bag) >= 3:
                extra = bag
                break
        flow = list(pack.get("flow") or [])
        paras = list(pack.get("paras") or [])
        for t in extra:
            c = compact_text(t)
            if c in have:
                continue
            flow.append({"kind": "para", "text": t})
            paras.append(t)
            have.add(c)
        pack["flow"] = flow
        pack["paras"] = paras
        pack["empty"] = not flow
        return pack

    hit = _from(docs)
    if hit:
        return _append_year_tail(hit, docs)
    hit = _from(prior_docs)
    if hit:
        src = hit.get("source") or ""
        hit["source"] = f"{src}（体例回退）" if src else "体例回退"
        return _append_year_tail(hit, docs)
    return {"flow": [], "paras": [], "source": "", "empty": True}


def retitle_ch7_plan_captions(text: str) -> str:
    t = text or ""
    if "生产计划" in t or "如表" in t or re.match(r"表\s*\d+-\d+", t.strip()):
        return re.sub(r"表\s*\d+\s*-\s*\d+", "表7-1", t)
    return t
