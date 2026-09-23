# -*- coding: utf-8 -*-
"""第 9–11 章体例。9.1/9.2 和工器具只用当年材料；环境只写材料里有的线路，不把粉尘段贴到没有专节的线上。"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text
from chapters.overhead.outline import is_peer_chapter_title
from chapters.overhead.section_bundle import sort_docs_newest_last
from parsers.document_model import DocumentModel

_STOCK_PROSE = (
    "评估将根据是否有安全库存",
    "对于不同厂商",
    "柔性接触网备件",
    "至少有一部",
    "至少保留必要安全备件",
    "支持全路网",
)
_STOCK_APPENDIX = ("附录A", "附录B", "附录C", "如附录")
_STOCK_STOP = ("评估小结", "使用环境符合性", "退运报废")
_ENV_LEAD_A = "针对粉尘对接触网系统的影响，供电分公司已通过修订"
_ENV_LEAD_B = "外部环境对触网系统可靠运行的影响不容忽视"
_ENV_LEAD_C = "各线路环境主要情况如下"
_FACTOR_CUT = re.compile(
    r"^(?:\d+[、.．)）]\s*)?(?:温度|湿度|粉尘|雷电|暴风|覆冰|沉降|异物侵限|外来侵限|"
    r"空气污染|运营延长|弓架次)\s*$"
)
_TOOLS_KEEP = (
    "拟采购",
    "拟增配",
    "吊弦液压钳",
    "蜈蚣梯",
    "GIS终端",
    "六个高质量",
    "超大规模供电系统",
    "生产组织模式进行优化",
)
_ENV_LINE_REJECT = (
    "大修更新改造",
    "专项更换",
    "专项整治",
    "变电站",
    "35KV",
    "35kV",
    "冷水机组",
    "整流变压器",
    "集中修项目",
)


def _paras(doc: DocumentModel) -> list[str]:
    out: list[str] = []
    for b in doc.blocks or []:
        if b.type in {"paragraph", "heading"} and (b.text or "").strip():
            out.append((b.text or "").strip())
    return out


def _ch9_prose_from(docs: list[DocumentModel] | None) -> dict[str, list[str]]:
    stock: list[str] = []
    appendix: list[str] = []
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        keep = False
        local_stock: list[str] = []
        local_app: list[str] = []
        for t in _paras(doc):
            if is_peer_chapter_title(t) and "备件" not in t and "安全库存" not in t:
                if keep:
                    break
                continue
            if any(k in t for k in ("备件物资保障度", "接触网安全库存")) and len(t) < 40:
                keep = True
                continue
            if keep and any(k in t for k in _STOCK_STOP):
                break
            if "评估情况撰写" in t:
                continue
            if any(k in t for k in _STOCK_APPENDIX) and ("详细数量" in t or "如附录" in t):
                if t not in local_app:
                    local_app.append(t)
                continue
            if keep and any(k in t for k in _STOCK_PROSE) and t not in local_stock:
                local_stock.append(t)
            elif any(k in t for k in _STOCK_PROSE) and "物料名称" not in t and t not in local_stock:
                local_stock.append(t)
        if local_stock and not stock:
            stock = local_stock
        if local_app and not appendix:
            appendix = local_app
        if stock and appendix:
            break
    return {"stock": stock, "appendix": appendix}


def _spare_table_kind(rows: list[list[str]] | None) -> str:
    """人工附录 A/B/C 对应规定里的表 D.1 / E.1 / F.1。变电清册不要。"""
    if not rows or len(rows) < 2:
        return ""
    head = "".join(str(c or "") for c in (rows[0] or []))
    if "物料名称" not in head:
        return ""
    if "安全库存" not in head and "型号" not in head:
        return ""
    body = "".join(str(c or "") for r in rows[1:16] for c in r)
    if "柔性接触网" in body:
        return "柔性"
    if "刚性接触网" in body:
        return "刚性"
    if "接触轨" in body:
        return "接触轨"
    return ""


def extract_ch9_spare_tables(docs: list[DocumentModel] | None) -> dict[str, Any] | None:
    """9.2 只取最新一份库存规定里的柔性/刚性/接触轨表。没有就空，不用去年。"""
    from chapters.common.table_copy import table_flow_item
    from chapters.overhead.section_bundle import doc_recency_key

    best_key: tuple | None = None
    best_groups: dict[str, list[dict[str, Any]]] | None = None
    best_src = ""
    for idx, doc in enumerate(docs or []):
        groups: dict[str, list[dict[str, Any]]] = {"柔性": [], "刚性": [], "接触轨": []}
        for block in doc.blocks or []:
            if block.type != "table" or not block.rows:
                continue
            kind = _spare_table_kind(block.rows)
            if not kind:
                continue
            groups[kind].append(table_flow_item(doc, block))
        if not any(groups.values()):
            continue
        key = doc_recency_key(doc, idx)
        if best_key is None or key >= best_key:
            best_key = key
            best_groups = groups
            best_src = doc.source_name or ""
    if not best_groups:
        return None
    captions = {
        "柔性": ("表D.1 柔性接触网安全库存", "表D.1 续"),
        "刚性": ("表E.1 刚性接触网安全库存", "表E.1 续"),
        "接触轨": ("表F.1 接触轨安全库存", "表F.1 续"),
    }
    flow: list[dict[str, Any]] = []
    for kind in ("柔性", "刚性", "接触轨"):
        tables = best_groups.get(kind) or []
        if not tables:
            continue
        lead, cont = captions[kind]
        flow.append({"kind": "para", "text": lead})
        for i, item in enumerate(tables):
            if i:
                flow.append({"kind": "para", "text": cont})
            flow.append(item)
    if not any(x.get("kind") == "table" for x in flow):
        return None
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para"]
    return {
        "paras": paras,
        "flow": flow,
        "table": [],
        "sections": [],
        "source": best_src,
        "empty": False,
    }


def extract_overhead_ch9(
    docs: list[DocumentModel] | None,
    prior_docs: list[DocumentModel] | None = None,
) -> dict[str, dict[str, Any]]:
    """9.1、9.2 都只用当年材料。去年说明和去年库存表都不带过来。"""
    del prior_docs
    hit = _ch9_prose_from(docs)
    out: dict[str, dict[str, Any]] = {}
    if hit["stock"]:
        flow = [{"kind": "para", "text": t} for t in hit["stock"]]
        out["接触网安全库存"] = {
            "paras": hit["stock"],
            "flow": flow,
            "table": [],
            "sections": [],
            "source": "",
            "empty": False,
        }
    spare = extract_ch9_spare_tables(docs)
    if spare:
        out["接触网安全库存备品备件"] = spare
    return out


def apply_ch9_layout(fills: dict[str, Any]) -> dict[str, Any]:
    """9.1 只留说明；9.2 留库存表，去掉「见附录」。"""
    for key in ("接触网安全库存", "接触网安全库存备品备件"):
        fill = fills.get(key)
        if not isinstance(fill, dict):
            continue
        flow = list(fill.get("flow") or [])
        if key == "接触网安全库存":
            flow = [x for x in flow if x.get("kind") != "table"]
            flow = [
                x
                for x in flow
                if "附录" not in str(x.get("text") or "")
                and compact_text(str(x.get("text") or "")) != compact_text("接触网安全库存备品备件")
            ]
        else:
            flow = [
                x
                for x in flow
                if x.get("kind") == "table"
                or (
                    x.get("kind") == "para"
                    and "附录" not in str(x.get("text") or "")
                    and "如附录" not in str(x.get("text") or "")
                )
            ]
        paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para"]
        if key == "接触网安全库存" and not paras:
            paras = [
                p
                for p in (fill.get("paras") or [])
                if "附录" not in p and compact_text(p) != compact_text("接触网安全库存备品备件")
            ]
            flow = [{"kind": "para", "text": p} for p in paras]
        has_table = any(x.get("kind") == "table" for x in flow)
        fill["flow"] = flow
        fill["paras"] = paras
        fill["table"] = []
        fill["empty"] = not paras and not has_table
        fills[key] = fill
    return fills


def _generic_env_paras(docs: list[DocumentModel] | None) -> list[str]:
    found: list[str] = []
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        for t in _paras(doc):
            if t.startswith(_ENV_LEAD_A) or t.startswith(_ENV_LEAD_B) or t.startswith(_ENV_LEAD_C):
                if t not in found:
                    found.append(t)
    ordered: list[str] = []
    for lead in (_ENV_LEAD_A, _ENV_LEAD_B, _ENV_LEAD_C):
        for t in found:
            if t.startswith(lead) and t not in ordered:
                ordered.append(t)
    return ordered[:3]


def extract_ch10_lead(docs: list[DocumentModel] | None) -> dict[str, Any] | None:
    paras = _generic_env_paras(docs)
    if not paras:
        return None
    flow = [{"kind": "para", "text": t} for t in paras]
    return {
        "paras": paras,
        "flow": flow,
        "table": [],
        "sections": [],
        "source": "",
        "empty": False,
    }


def trim_env_factor_flow(title: str, fill: dict[str, Any] | None) -> dict[str, Any] | None:
    if not fill:
        return fill
    want = compact_text(title)
    out_flow: list[dict[str, Any]] = []
    for item in fill.get("flow") or []:
        t = str(item.get("text") or "").strip()
        if item.get("kind") == "para" and _FACTOR_CUT.match(t) and want not in compact_text(t):
            break
        if item.get("kind") == "para" and t.startswith("3）") and want != compact_text("粉尘"):
            if "异物" in t or "侵限" in t:
                break
        if item.get("kind") == "para" and want == compact_text("粉尘") and (
            t.startswith("3）") or t.startswith("异物侵限")
        ):
            break
        out_flow.append(item)
    if want == compact_text("粉尘"):
        sweep = [x for x in out_flow if "清扫为一年一次" in str(x.get("text") or "")]
        check = [x for x in out_flow if "检查为一年一次" in str(x.get("text") or "")]
        if sweep and check:
            out_flow = [x for x in out_flow if "检查为一年一次" not in str(x.get("text") or "")]
    if want == compact_text("覆冰"):
        from chapters.common.list_number import restart_list_after_prose_flow

        out_flow = restart_list_after_prose_flow(out_flow)
        fill = dict(fill)
        fill["_list_after_prose"] = True
    if want == compact_text("湿度"):
        trimmed: list[dict[str, Any]] = []
        for item in out_flow:
            t = str(item.get("text") or "")
            if item.get("kind") == "para" and "例如" in t and "白色氧化物" in t:
                t = t.split("例如", 1)[0].rstrip("，,;； ")
                if t and not t.endswith("。"):
                    t += "。"
                item = dict(item)
                item["text"] = t
            trimmed.append(item)
        out_flow = trimmed
    if want == compact_text("空气污染"):
        net = [x for x in out_flow if "1号线北延伸" in str(x.get("text") or "") or "接触网系统受空气污染" in str(x.get("text") or "")]
        rail = [x for x in out_flow if "17号线部分户外段" in str(x.get("text") or "") or "接触轨系统受空气污染" in str(x.get("text") or "")]
        if net and rail:
            out_flow = [x for x in out_flow if x in net or x.get("kind") != "para" or (
                "17号线部分户外段" not in str(x.get("text") or "") and "接触轨系统受空气污染" not in str(x.get("text") or "")
            )]
    if want == compact_text("外来侵限"):
        open_line = [x for x in out_flow if "开放式高架线路" in str(x.get("text") or "")]
        bag = [x for x in out_flow if "塑料袋、风筝、绿植" in str(x.get("text") or "")]
        if open_line and bag:
            out_flow = [x for x in out_flow if x not in bag]
    paras = [str(x.get("text") or "") for x in out_flow if x.get("kind") == "para"]
    fill = dict(fill)
    fill["flow"] = out_flow
    fill["paras"] = paras
    fill["empty"] = not out_flow
    return fill


def _line_no_of(title: str) -> int | None:
    m = re.search(r"(\d{1,2})号线", title or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def env_line_rejected(text: str) -> bool:
    t = str(text or "")
    return any(k in t for k in _ENV_LINE_REJECT)


def keep_unique_env_section(sec: dict[str, Any]) -> bool:
    """有这条线自己的环境正文就留。不拿人工稿里的特征句当门槛。"""
    blob = " ".join(sec.get("paras") or []).strip()
    if not blob:
        return False
    return not env_line_rejected(blob)


def _strip_overhaul_paras(paras: list[str]) -> list[str]:
    return [p for p in paras if "大修需求" not in p and "大修年限" not in p]


_ENV_UNIQUE_SKIP = (
    "设备评分为",
    "SCADA",
    "整流器",
    "交直流屏",
    "事故照明",
    "UPS",
    "NK11",
    "C状态",
    "D状态",
    "刚性接触网状态",
    "柔性接触网状态",
    "惠南站",
    "跟随混变",
    "需要定期清理",
)


def _env_unique_para_ok(text: str) -> bool:
    t = str(text or "")
    if env_line_rejected(t) or "大修需求" in t:
        return False
    return not any(k in t for k in _ENV_UNIQUE_SKIP)


def _harvest_unique_line_paras(docs: list[DocumentModel] | None) -> dict[int, list[str]]:
    """按线路收环境正文。同一条线有多份材料时只留较新的一份，不要求对上某年的特征句。"""
    from chapters.overhead.line_topics import _env_line_para

    by: dict[int, list[str]] = {}
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        local: dict[int, list[str]] = {}
        for t in _paras(doc):
            if not _env_unique_para_ok(t) or not _env_line_para(t):
                continue
            n = _line_no_of(t)
            if not n or n in by:
                continue
            bag = local.setdefault(n, [])
            cleaned = t.replace("目前属于我部特殊区段管辖内容", "目前属于特殊区段管辖内容")
            if cleaned not in bag:
                bag.append(cleaned)
        for n, paras in local.items():
            if n not in by and paras:
                by[n] = paras
    return by


def _sec_from_paras(n: int, paras: list[str]) -> dict[str, Any]:
    paras = [p.replace("目前属于我部特殊区段管辖内容", "目前属于特殊区段管辖内容") for p in paras]
    flow = [{"kind": "para", "text": t} for t in paras]
    return {
        "title": f"轨道交通{n}号线",
        "paras": paras,
        "empty": False,
        "source": "",
        "content_child": True,
        "fill": {
            "paras": paras,
            "flow": flow,
            "table": [],
            "sections": [],
            "source": "",
            "empty": False,
        },
    }


def backfill_env_lines(hit: dict[str, Any], docs: list[DocumentModel] | None) -> dict[str, Any]:
    """只保留材料里写到的线路。没有专节的线路不拿粉尘或外部环境两段去补。"""
    harvested = _harvest_unique_line_paras(docs)
    sections = list(hit.get("sections") or [])
    kept: list[dict[str, Any]] = []
    have: set[int] = set()
    for sec in sections:
        n = _line_no_of(str(sec.get("title") or ""))
        paras = [p for p in _strip_overhaul_paras(list(sec.get("paras") or [])) if _env_unique_para_ok(p)]
        extra = harvested.get(n or 0) or []
        for t in extra:
            if t not in paras:
                paras.append(t)
        if n == 12:
            paras.sort(key=lambda t: 0 if "大连路" in t else 1)
        paras = [p.replace("目前属于我部特殊区段管辖内容", "目前属于特殊区段管辖内容") for p in paras]
        sec = dict(sec)
        sec["paras"] = paras
        fill = dict(sec.get("fill") or {})
        fill["paras"] = paras
        fill["flow"] = [{"kind": "para", "text": t} for t in paras]
        sec["fill"] = fill
        blob = " ".join(paras)
        if env_line_rejected(blob) or not keep_unique_env_section(sec):
            continue
        if n:
            have.add(n)
        kept.append(sec)
    for n, paras in harvested.items():
        if n in have:
            continue
        kept.append(_sec_from_paras(n, paras))
        have.add(n)
    kept.sort(key=lambda s: _line_no_of(str(s.get("title") or "")) or 99)
    hit = dict(hit)
    hit["sections"] = kept
    hit["empty"] = not kept
    return hit


def apply_ch10_parent_cleanup(fills: dict[str, Any]) -> dict[str, Any]:
    parent = fills.get("各线路环境符合性评估")
    if isinstance(parent, dict):
        parent = dict(parent)
        parent["paras"] = []
        parent["flow"] = []
        parent["empty"] = True
        parent["source"] = ""
        fills["各线路环境符合性评估"] = parent
    for title in ("温度", "湿度", "粉尘", "雷电", "暴风", "覆冰", "沉降", "外来侵限", "空气污染", "运营延长"):
        if title in fills and isinstance(fills[title], dict):
            fills[title] = trim_env_factor_flow(title, fills[title])
    if "弓架次" in fills and isinstance(fills["弓架次"], dict):
        fills["弓架次"] = order_bow_tables(fills["弓架次"])
    parent_h1 = fills.get("使用环境符合性评估")
    if isinstance(parent_h1, dict):
        parent_h1 = dict(parent_h1)
        parent_h1["paras"] = []
        parent_h1["flow"] = []
        parent_h1["empty"] = True
        parent_h1["source"] = ""
        fills["使用环境符合性评估"] = parent_h1
    return fills


def prefer_network_dust(fills: dict[str, Any], docs: list[DocumentModel] | None) -> dict[str, Any]:
    wanted: list[str] = []
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        for t in _paras(doc):
            if t.startswith("绝缘措施的到位") and "影响较大" in t and "接触轨系统" not in t:
                if t not in wanted:
                    wanted.append(t)
            if t.startswith("粉尘对于绝缘的影响较大") and "清扫为一年一次" in t:
                if "膨胀接头" in t or "需要定期清理" in t:
                    continue
                if t not in wanted:
                    wanted.append(t)
            if "膨胀接头卡滞" in t and "清扫为一年一次" not in t and t not in wanted:
                wanted.append(t)
    fill = fills.get("粉尘")
    if not wanted:
        if not isinstance(fill, dict):
            return fills
        paras = [str(x.get("text") or "") for x in (fill.get("flow") or []) if x.get("kind") == "para"]
        wanted = [
            t
            for t in paras
            if "检查为一年一次" not in t and "影响甚大" not in t and not t.startswith("3）")
        ]
    if wanted:
        fills["粉尘"] = {
            "paras": wanted,
            "flow": [{"kind": "para", "text": t} for t in wanted],
            "table": [],
            "sections": [],
            "source": "",
            "empty": False,
        }
    return fills


def order_bow_tables(fill: dict[str, Any] | None) -> dict[str, Any] | None:
    """人工 10.1 弓架次：柔性 → 刚性 → 接触轨，不要图注。"""
    if not fill:
        return fill
    order = ("柔性", "刚性", "接触轨")
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in order}
    leftover: list[dict[str, Any]] = []
    flow = list(fill.get("flow") or [])
    i = 0
    while i < len(flow):
        item = flow[i]
        t = str(item.get("text") or "")
        if item.get("kind") == "para" and ("弓架次分布如图" in t or "如图10-1" in t or "如图10－1" in t):
            i += 1
            continue
        bucket = next((k for k in order if item.get("kind") == "para" and "弓架次" in t and k in t), "")
        if bucket:
            groups[bucket].append(item)
            if i + 1 < len(flow) and flow[i + 1].get("kind") == "table":
                groups[bucket].append(flow[i + 1])
                i += 2
                continue
            i += 1
            continue
        leftover.append(item)
        i += 1
    captions = {
        "柔性": "表格10-2  不同线路弓架次数据（柔性）",
        "刚性": "表格10-3  不同线路弓架次数据（刚性）",
        "接触轨": "表格10-4 不同线路弓架次数据（接触轨）",
    }
    new_flow: list[dict[str, Any]] = []
    for k in order:
        items = groups[k]
        if items and items[0].get("kind") == "para":
            cap = dict(items[0])
            cap["text"] = captions[k]
            new_flow.append(cap)
            new_flow.extend(items[1:])
        else:
            new_flow.extend(items)
    new_flow.extend(x for x in leftover if x.get("kind") == "table")
    new_flow.extend(
        x
        for x in leftover
        if x.get("kind") == "para" and "全网日平均弓架次" not in str(x.get("text") or "")
    )
    fill = dict(fill)
    fill["flow"] = new_flow
    fill["paras"] = [str(x.get("text") or "") for x in new_flow if x.get("kind") == "para"]
    fill["empty"] = not new_flow
    return fill


def flatten_retire_to_parent(fill: dict[str, Any] | None) -> dict[str, Any] | None:
    """人工 11.1 是一段退运说明，不按线路拆 11.1.1。"""
    if not fill:
        return fill
    paras: list[str] = []
    for p in fill.get("paras") or []:
        t = str(p or "").strip()
        if t and "除湿机" not in t and "空气除湿" not in t and t not in paras:
            paras.append(t)
    for sec in fill.get("sections") or []:
        for p in sec.get("paras") or []:
            t = str(p or "").strip()
            if t and "除湿机" not in t and "空气除湿" not in t and t not in paras:
                paras.append(t)
    if len(paras) >= 2 and paras[0].startswith("4号线") and paras[1].startswith("隔离开关"):
        head = paras[0].rstrip("。") + "。"
        paras = ["4号线： " + head + paras[1]]
    elif paras and paras[0].startswith("4号线需报废") and not paras[0].startswith("4号线："):
        paras = ["4号线： " + paras[0]] + paras[1:]
    flow = [{"kind": "para", "text": t} for t in paras]
    fill = dict(fill)
    fill["paras"] = paras
    fill["flow"] = flow
    fill["sections"] = []
    fill["table"] = []
    fill["empty"] = not paras
    fill["source"] = ""
    return fill


def apply_ch11_layout(
    fills: dict[str, Any],
    docs: list[DocumentModel] | None,
    year: int,
) -> dict[str, Any]:
    year_title = f"{year}年设备退运更换情况"
    if year_title in fills and isinstance(fills[year_title], dict):
        fills[year_title] = flatten_retire_to_parent(fills[year_title])
    tools = fills.get("固定资产工器具配置情况")
    if isinstance(tools, dict) and "体例回退" in str(tools.get("source") or ""):
        tools = {
            "paras": [],
            "flow": [],
            "table": [],
            "sections": [],
            "source": "",
            "empty": True,
        }
        fills["固定资产工器具配置情况"] = tools
    blob = ""
    if isinstance(tools, dict):
        blob = " ".join(tools.get("paras") or []) + " ".join(
            str(x.get("text") or "") for x in (tools.get("flow") or []) if x.get("kind") == "para"
        )
    if (not tools or tools.get("empty") or "暂无缺少" in blob or "不存在缺" in blob):
        v2 = harvest_overhead_tools_v2(docs)
        if v2 and not v2.get("empty"):
            fills["固定资产工器具配置情况"] = v2
        elif isinstance(tools, dict) and ("暂无缺少" in blob or "不存在缺" in blob):
            fills["固定资产工器具配置情况"] = {
                "paras": [],
                "flow": [],
                "table": [],
                "sections": [],
                "source": "",
                "empty": True,
            }
    return fills


def harvest_overhead_tools_v2(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """11.2：要「拟采购/工装」原文，不要「暂无缺少」。"""
    best: list[str] = []
    src = ""
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        name = doc.source_name or ""
        buf: list[str] = []
        grab = 0
        for t in _paras(doc):
            if any(k in t for k in _TOOLS_KEEP):
                buf.append(t)
                grab = 2
                continue
            if grab and len(t) >= 16 and "评估情况撰写" not in t:
                buf.append(t)
                grab -= 1
            elif grab:
                grab = 0
        if buf and (not best or len("".join(buf)) > len("".join(best))):
            best = buf
            src = name
    if not best:
        return {"paras": [], "flow": [], "source": "", "empty": True}
    flow = [{"kind": "para", "text": t} for t in best]
    return {"paras": best, "flow": flow, "source": src, "empty": False}
