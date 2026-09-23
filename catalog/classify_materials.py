# -*- coding: utf-8 -*-
"""全年材料分拣：先对照去年完整报告目录，再全文扫描材料分章。

流程：
1. 读去年报告，整理第 3～11 章「需要什么样的材料」；
2. 全年材料逐文件解析，正文/表从头到尾读完（不截前几页）；
3. 规则：供电/触网分流 + 各章抽取试跑 + 对照去年目录关键词命中；
4. 有大模型时再全文复核一遍，规则与模型结果取并集，尽量找全。

不因文件夹叫「接触网」整份丢掉。模型不得把已定为供电的文件改打成触网。
"""
from __future__ import annotations

import copy
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from parsers.dedupe import drop_duplicate_tables
from parsers.parse_cache import parse_file_cached, save_classify_result
from parsers.document_model import DocumentModel

# 左侧第 3～11 章。分章结果按这些 id 写入 by_chapter。
CHAPTERS = ("ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11")

POWER_CONTENT = (
    "变电专业",
    "变电所",
    "变电站",
    "主变电",
    "主变站",
    "应急电源",
    "整流器",
    "整流机组",
    "降压变电",
    "牵引变电",
    "杂散电流",
    "能源系统",
    "能源专业",
    "电力电缆",
    "电力监控",
    "直流开关",
    "交流开关柜",
    "变压器",
    "开关柜",
    "排流柜",
    "负极柜",
)
# 只看文件名，不看文件夹。文件名带「接触网」时，「供电分公司」这种单位名不算供电证据。
NAME_POWER = (
    "供电",
    "变电",
    "主变",
    "能源系统",
    "应急电源",
    "杂散电流",
    "设备评估结果总表",
)
NAME_POWER_STRONG = ("变电", "主变", "能源系统", "应急电源", "杂散电流")
NAME_OVERHEAD = ("接触网", "触网", "接触轨")
OVERHEAD_CONTENT = (
    "接触网专业",
    "接触网",
    "触网",
    "刚性接触网",
    "柔性接触网",
    "接触轨",
    "接触网（轨）",
    "接触线",
    "承力索",
    "柔性锚段",
    "刚性锚段",
    "三轨区间",
    "汇流排",
    "隔离开关控制屏",
    "系统状态等级",
)

# 大模型复核：供电 / 接触网各用各的词，禁止互套。
POWER_LLM_LEXICON = {
    "ch3": ("设备评估结果总表", "管控措施", "设备树", "应急电源设备", "杂散电流设备", "评估方法和内容", "评估标准"),
    "ch4": (
        "各个线路基本情况",
        "故障现象",
        "故障原因",
        "维护周期",
        "维护内容",
        "年度生产指标",
        "生产指标",
        "MTBF",
        "MCBF",
        "当月值",
        "设备体量",
    ),
    "ch5": ("法律法规的获取", "企业标准和制度", "合规性评价", "制度、标准执行", "特种设备", "强制年检"),
    "ch6": ("修程修制", "对上一年度合规性", "规程分类"),
    "ch7": ("计划数量", "完成率", "生产计划执行", "运维表现"),
    "ch8": ("隐患描述", "隐患排查手册", "安全隐患排查", "突出事件"),
    "ch9": ("安全库存", "物料名称", "规格型号", "备品备件"),
    "ch10": ("使用环境",),
    "ch11": ("退运", "报废", "工器具"),
}
OVERHEAD_LLM_LEXICON = {
    "ch3": ("接触网设备状态分布", "管控措施", "柔性接触网", "刚性接触网", "评估方法和内容", "评估标准", "设备评估结果总表"),
    "ch4": ("各线路接触网故障趋势", "接触网故障趋势", "维护周期", "维护内容", "设备体量", "接触线磨耗"),
    "ch5": ("法律法规的获取", "企业标准和制度", "合规性评价", "制度、标准执行", "特种设备", "强制年检"),
    "ch6": ("修程修制", "对上一年度合规性", "规程分类"),
    "ch7": ("计划数量", "完成率", "生产组织", "维保管理", "新技术应用"),
    "ch8": ("隐患描述", "突出事件", "隐患排查"),
    "ch9": ("接触网安全库存", "安全库存", "备品备件"),
    "ch10": ("环境差异性", "弓架次", "使用环境", "异物侵限"),
    "ch11": ("退运", "报废", "工器具"),
}

# 去年报告小节标题 → 章。供电 / 接触网各一张，避免「各个线路基本情况」进触网。
POWER_PRIOR_SECTION_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ch3", ("设备功能有效性", "评估方法和内容", "评估标准", "供电子系统", "管控措施", "两年评估对比", "最近两年")),
    ("ch4", ("运营契合", "设备体量", "维护周期", "维护内容", "各个线路基本情况", "年度生产指标", "生产指标", "MTBF", "MCBF")),
    ("ch5", ("管理体系合规", "特种设备", "强制年检", "法律法规", "企业标准和制度", "制度、标准执行", "合规性评价")),
    ("ch6", ("修程修制", "对上一年度合规性", "规程分类")),
    ("ch7", ("运维表现", "生产组织", "生产计划执行", "运维质量", "新技术应用", "维保管理")),
    ("ch8", ("风险隐患", "突出事件", "隐患排查")),
    ("ch9", ("备件物资", "安全库存", "备品备件")),
    ("ch10", ("使用环境",)),
    ("ch11", ("退运报废", "退运更换", "报废", "工器具配置")),
)
OVERHEAD_PRIOR_SECTION_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ch3", ("设备功能有效性", "评估方法和内容", "评估标准", "接触网设备状态", "管控措施", "两年评估对比", "最近两年")),
    ("ch4", ("运营契合", "设备体量", "维护周期", "维护内容", "各线路接触网故障趋势", "接触网故障", "接触线磨耗")),
    ("ch5", ("管理体系合规", "特种设备", "强制年检", "法律法规", "企业标准和制度", "制度、标准执行", "合规性评价")),
    ("ch6", ("修程修制", "对上一年度合规性", "规程分类")),
    ("ch7", ("运维表现", "生产组织", "生产计划执行", "运维质量", "新技术应用", "维保管理")),
    ("ch8", ("风险隐患", "突出事件", "隐患排查")),
    ("ch9", ("备件物资", "安全库存", "备品备件", "接触网安全库存")),
    ("ch10", ("使用环境", "环境差异性", "弓架次")),
    ("ch11", ("退运报废", "退运更换", "报废", "工器具配置")),
)

POWER_DEFAULT_NEED_KEYS: dict[str, tuple[str, ...]] = {cid: keys for cid, keys in POWER_LLM_LEXICON.items()}
OVERHEAD_DEFAULT_NEED_KEYS: dict[str, tuple[str, ...]] = {cid: keys for cid, keys in OVERHEAD_LLM_LEXICON.items()}

# 兼容旧引用：默认按供电。
LLM_LEXICON = POWER_LLM_LEXICON
PRIOR_SECTION_MAP = POWER_PRIOR_SECTION_MAP
DEFAULT_NEED_KEYS = POWER_DEFAULT_NEED_KEYS

# 去年标题扫进来时，丢掉对方专业的词。
_POWER_FOREIGN_NEED = ("接触网设备状态", "各线路接触网故障", "接触网故障趋势", "接触网安全库存", "弓架次", "柔性接触网", "刚性接触网")
_OH_FOREIGN_NEED = ("各个线路基本情况", "各线路供电系统年度生产", "MTBF", "MCBF", "降压系统", "应急电源系统", "杂散电流")


def _name(doc: DocumentModel) -> str:
    """显示用文件名，跳过规则和 LLM 摘录都用它。"""
    return doc.source_name or Path(doc.source_path or "").name


def _full_text(doc: DocumentModel) -> str:
    """从头到尾拼完全文：全部段落/标题 + 全部表单元格。分拣匹配禁止只看前几页。"""
    parts: list[str] = []
    for block in doc.blocks or []:
        if block.type == "table" and block.rows:
            for row in block.rows:
                parts.append(" ".join(str(c or "") for c in row))
        else:
            t = (block.text or "").strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def _inventory_for_llm(doc: DocumentModel, *, limit: int = 28000) -> str:
    """给大模型的全文结构清单：走完所有块；超长时仍保留全部标题与每表表头，正文按块截到上限。"""
    parts: list[str] = [f"文件名：{_name(doc)}"]
    used = 0
    for i, block in enumerate(doc.blocks or []):
        if block.type == "table" and block.rows:
            head = " | ".join(str(c or "") for c in (block.rows[0] or []))
            line = f"[表#{i} 共{len(block.rows)}行] {head}"
            # 再附前 2 行数据样例，帮助认 MTBF 等
            for row in block.rows[1:3]:
                line += " // " + " | ".join(str(c or "") for c in row)
        else:
            t = (block.text or "").strip()
            if not t:
                continue
            kind = "标题" if block.type == "heading" else "段"
            line = f"[{kind}] {t}"
        if used + len(line) + 1 > limit and block.type != "heading":
            # 标题尽量都留下；普通段超限则跳过正文但仍继续扫后面的标题/表头
            continue
        parts.append(line)
        used += len(line) + 1
    return "\n".join(parts)[: limit + 2000]


def _blob(doc: DocumentModel, limit: int = 8000) -> str:
    """兼容旧调用：改为基于全文截断，不再只取前 80 块。"""
    return _full_text(doc)[:limit]


def _sheet_titles(doc: DocumentModel) -> list[str]:
    out: list[str] = []
    for block in doc.blocks:
        text = (block.text or "").strip()
        if block.type == "heading" and text.startswith("工作表:"):
            out.append(text.split(":", 1)[-1].strip())
    return out


def _content_blob(doc: DocumentModel, limit: int = 18000) -> str:
    """供电/触网分流用：全文优先，仅在超长时截断。"""
    return _full_text(doc)[:limit]


def _keyword_score(text: str, keys: tuple[str, ...]) -> int:
    """按命中次数计分。长词优先，避免「接触网」再被「触网」算第二次。"""
    if not text:
        return 0
    accounted: list[str] = []
    score = 0
    for key in sorted(set(keys), key=len, reverse=True):
        if any(key != longer and key in longer for longer in accounted):
            continue
        n = text.count(key)
        if not n:
            continue
        accounted.append(key)
        score += n * (2 if len(key) >= 4 else 1)
    return score


def _domain_from_content(doc: DocumentModel) -> str:
    """用工作表名和正文判断：power / mixed / overhead / unknown。不看文件夹名。"""
    from chapters.common.domain_filter import is_overhead_only_doc, prepare_power_docs, strip_overhead_sheets
    from chapters.overhead.excel_status import detect_overhead_excel_capabilities

    titles = " ".join(_sheet_titles(doc))
    has_oh_sheet = any(k in titles for k in ("接触网", "触网", "接触轨", "柔性锚段", "刚性锚段", "三轨区间"))
    if detect_overhead_excel_capabilities(doc):
        has_oh_sheet = True
    has_power_sheet = any(k in titles for k in ("变电", "供电专业", "主变", "能源"))
    if has_oh_sheet and has_power_sheet:
        return "mixed"
    if is_overhead_only_doc(doc):
        return "overhead"
    leftover = prepare_power_docs([doc]) or [strip_overhead_sheets(doc)]
    text = _content_blob(leftover[0] if leftover else doc)
    power_score = _keyword_score(text, POWER_CONTENT)
    if "大类" in text and "供电" in text:
        power_score += 3
    oh_score = _keyword_score(text, OVERHEAD_CONTENT)
    if has_power_sheet:
        power_score += 4
    if has_oh_sheet:
        oh_score += 4
    if power_score and oh_score:
        if power_score >= oh_score or power_score >= 2:
            return "mixed"
        return "overhead"
    if power_score:
        return "power"
    if oh_score or has_oh_sheet:
        return "overhead"
    return "unknown"


def _llm_domain(doc: DocumentModel) -> str:
    """规则认不准时，让 DeepSeek 看正文判断供电 / 接触网 / 两者都有。"""
    import os

    if not os.getenv("DEEPSEEK_API_KEY"):
        return "unknown"
    excerpt = _blob(doc, 3500)
    try:
        from engine.llm_client import chat_json

        data = chat_json(
            "你判断这份材料对上海轨道交通「供电（含能源、主变电）」年报有没有用。"
            "必须根据正文和表头，不要只看文件名或文件夹。"
            "供电指变电、主变、能源、应急电源、整流/降压配电、杂散电流、电力电缆/监控等。"
            "接触网指刚性/柔性接触网、接触轨、接触线、隔离开关（接触网专业）等。"
            "只返回 JSON："
            "{\"domain\":\"power|overhead|mixed\",\"reason\":\"...\"}。"
            "power=主要是供电内容；overhead=只有接触网内容；mixed=两者都有。",
            excerpt,
            temperature=0,
        )
    except Exception:
        return "unknown"
    domain = str((data or {}).get("domain") or "").strip().lower()
    if domain in {"power", "overhead", "mixed"}:
        return domain
    return "unknown"


def _filename_power_hint(doc: DocumentModel) -> bool:
    """文件名像供电材料。文件夹名不算；文件名同时带接触网时，单位名「供电」不够。"""
    name = _name(doc)
    if any(k in name for k in NAME_OVERHEAD):
        return any(k in name for k in NAME_POWER_STRONG)
    return any(k in name for k in NAME_POWER)


def _should_ask_llm(doc: DocumentModel, domain: str) -> bool:
    """只问吃不准的文件。纯触网工作表、正文只有触网的材料不问。"""
    from chapters.common.domain_filter import is_overhead_only_doc, prepare_power_docs

    if domain in {"power", "mixed"}:
        return False
    if is_overhead_only_doc(doc):
        return False
    if domain == "unknown":
        return True
    if _filename_power_hint(doc):
        return True
    # 有工作表且剥掉触网表后还剩正文：可能是误判，问一次。
    if _sheet_titles(doc) and prepare_power_docs([doc]):
        return True
    text = _content_blob(doc, 8000)
    return _keyword_score(text, POWER_CONTENT) > 0


def pick_power_material(doc: DocumentModel, *, use_llm: bool) -> dict[str, str]:
    """第一步：从全年材料里挑供电。目标是挑全，宁可多留。

    返回 bucket: power / mixed / overhead
    - power、mixed：留给第二步各章分类（混合文件抽取时丢掉接触网工作表）
    - overhead：供电解析直接不看
    规则拿不准时问 DeepSeek，只许把「像触网」改判成供电/混合，不许把供电改打成触网。
    没有模型时 unknown 当作供电留下，避免漏挑。
    """
    from chapters.common.domain_filter import is_overhead_only_doc

    via = "rule"
    if is_overhead_only_doc(doc):
        domain = "overhead"
    else:
        domain = _domain_from_content(doc)
        if domain == "overhead" and _filename_power_hint(doc):
            domain = "mixed"
        if domain == "unknown" and _filename_power_hint(doc):
            domain = "power"
    if use_llm and _should_ask_llm(doc, domain):
        llm = _llm_domain(doc)
        if domain == "overhead" and llm in {"power", "mixed"}:
            domain = llm
            via = "llm"
        elif domain == "unknown" and llm in {"power", "mixed", "overhead"}:
            domain = llm
            via = "llm"
    if domain == "unknown":
        domain = "power"
    if domain == "overhead":
        return {"bucket": "overhead", "via": via, "reason": "纯接触网材料，供电解析不看"}
    if domain == "mixed":
        return {"bucket": "mixed", "via": via, "reason": "供电与接触网都有，供电只取供电部分"}
    return {"bucket": "power", "via": via, "reason": "供电材料"}


def pick_overhead_material(doc: DocumentModel, *, use_llm: bool) -> dict[str, str]:
    """接触网分拣第一步：挑触网材料，丢掉纯供电稿。

    返回 bucket: overhead / mixed / power
    - power：接触网解析不看
    - overhead / mixed：进入触网分章
    """
    from chapters.common.domain_filter import is_overhead_only_doc, is_power_only_doc, prepare_power_docs
    from chapters.overhead.excel_status import detect_overhead_excel_capabilities

    caps = detect_overhead_excel_capabilities(doc)
    if caps:
        leftover = prepare_power_docs([doc])
        if leftover:
            return {"bucket": "mixed", "via": "rule", "reason": "Excel 表头含接触网台账，且另有供电工作表"}
        sample = "、".join(str(x.get("sheet") or "") for x in caps[:4] if x.get("sheet"))
        return {
            "bucket": "overhead",
            "via": "rule",
            "reason": f"Excel 表头可汇总接触网状态（{sample}）",
        }

    if is_overhead_only_doc(doc):
        return {"bucket": "overhead", "via": "rule", "reason": "纯接触网材料"}
    if is_power_only_doc(doc):
        return {"bucket": "power", "via": "rule", "reason": "纯供电材料，接触网解析不看"}

    domain, via = _domain_from_content(doc), "rule"
    name = _name(doc)
    if any(k in name for k in NAME_OVERHEAD):
        if domain == "power":
            # 文件名带接触网、正文却是纯供电：触网域丢掉，避免混进触网分章
            if _keyword_score(_content_blob(doc), OVERHEAD_CONTENT) == 0:
                domain = "power"
            else:
                domain = "mixed"
        elif domain == "unknown":
            domain = "overhead"
    if domain == "unknown" and any(k in name for k in NAME_POWER_STRONG):
        domain = "power"
    if use_llm and _should_ask_llm(doc, domain):
        llm = _llm_domain(doc)
        if domain == "power" and llm in {"overhead", "mixed"}:
            domain = llm
            via = "llm"
        elif domain == "unknown" and llm in {"power", "mixed", "overhead"}:
            domain = llm
            via = "llm"
    if domain == "unknown":
        # 触网专业默认偏触网：文件名无供电强词则收下再分章
        domain = "overhead" if not any(k in name for k in NAME_POWER_STRONG) else "power"
    if domain == "power":
        return {"bucket": "power", "via": via, "reason": "纯供电材料，接触网解析不看"}
    if domain == "mixed":
        return {"bucket": "mixed", "via": via, "reason": "供电与接触网都有，接触网只取触网部分"}
    return {"bucket": "overhead", "via": via, "reason": "接触网材料"}


def build_prior_needs(prior_docs: list[DocumentModel] | None, domain_id: str = "power_supply") -> dict[str, Any]:
    """从去年完整报告扫目录：各章需要哪些标题/关键词。无 prior 时用默认词表。"""
    defaults = OVERHEAD_DEFAULT_NEED_KEYS if domain_id == "overhead" else POWER_DEFAULT_NEED_KEYS
    section_map = OVERHEAD_PRIOR_SECTION_MAP if domain_id == "overhead" else POWER_PRIOR_SECTION_MAP
    foreign = _OH_FOREIGN_NEED if domain_id == "overhead" else _POWER_FOREIGN_NEED
    needs: dict[str, list[str]] = {cid: list(defaults.get(cid) or ()) for cid in CHAPTERS}
    titles: list[str] = []
    for doc in prior_docs or []:
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if not t:
                continue
            compact = re.sub(r"\s+", "", t)
            if block.type == "heading" or (len(compact) < 48 and re.match(r"^(?:第?[3-9]|1[01]|[3-9]\.|1[01]\.)", compact)):
                titles.append(t)
            for cid, keys in section_map:
                if any(k in compact for k in keys):
                    if compact not in needs[cid] and not any(f in compact for f in foreign):
                        needs[cid].append(compact[:60])
                    for k in keys:
                        if k in compact and k not in needs[cid] and not any(f in k for f in foreign):
                            needs[cid].append(k)
    outline_lines = []
    for cid in CHAPTERS:
        outline_lines.append(f"{cid}: " + "、".join(needs[cid][:12]))
    return {
        "by_chapter": needs,
        "outline_text": "\n".join(outline_lines),
        "prior_titles": titles[:200],
        "has_prior": bool(prior_docs),
    }


# 单独命中即可建议该章的强特征（弱词如「管控措施」不够，须靠抽取试跑）。
STRONG_NEED_KEYS: dict[str, tuple[str, ...]] = {
    "ch3": ("设备评估结果总表", "评估方法和内容", "供电子系统设备评估范围", "最近两年评估对比", "两年评估对比"),
    "ch4": (
        "各线路供电系统年度生产指标",
        "年度生产指标",
        "生产指标",
        "MTBF",
        "MCBF",
        "各个线路基本情况",
        "当月值",
        "指标名称",
    ),
    "ch5": ("法律法规的获取", "合规性评价", "强制年检", "特种设备、消防"),
    "ch6": ("修程修制匹配性", "对上一年度合规性评估建议"),
    "ch7": ("生产计划执行", "计划数量", "完成率", "新技术应用", "维保管理"),
    "ch8": ("隐患排查手册", "安全隐患排查动态", "突出事件分析"),
    "ch9": ("安全库存", "备品备件更新"),
    "ch10": ("使用环境符合性", "使用环境"),
    "ch11": ("退运更换", "退运报废", "固定资产工器具"),
}

# 接触网分拣：对照触网年报目录的强特征（与供电词表分开，避免互套）。
OVERHEAD_STRONG_NEED_KEYS: dict[str, tuple[str, ...]] = {
    "ch3": (
        "接触网设备状态分布",
        "各线路管控措施",
        "柔性接触网状态",
        "刚性接触网状态",
        "设备评估结果总表",
        "管控措施",
        "柔性锚段",
        "刚性锚段",
        "三轨区间",
        "隔离开关控制屏",
        "系统状态等级",
    ),
    "ch4": ("设备体量", "各线路接触网故障趋势", "接触线磨耗", "维护周期", "系统状态值", "系统状态等级"),
    "ch5": ("特种设备", "强制年检", "法律法规的获取", "企业标准和制度", "合规性评价"),
    "ch6": ("对上一年度合规性评估建议", "修程修制", "修程修志"),
    "ch7": ("生产组织模式", "日常维修计划", "维保管理", "新线路接管", "新技术应用", "计划数量", "完成率"),
    "ch8": ("突出事件分析", "故障分析报告", "隐患排查"),
    "ch9": ("接触网安全库存", "安全库存", "备品备件"),
    "ch10": ("环境差异性", "弓架次", "使用环境", "异物侵限"),
    "ch11": ("退运更换", "报废原因", "工器具配置"),
}


def _hits_from_needs(full_text: str, needs: dict[str, Any] | None) -> list[dict[str, str]]:
    """对照去年目录的强特征做全文命中。弱词不单独分章，避免风险清单/触网表误进 ch3。"""
    if not full_text:
        return []
    by_chapter = (needs or {}).get("by_chapter") or {}
    out: list[dict[str, str]] = []
    for cid in CHAPTERS:
        strong = list(STRONG_NEED_KEYS.get(cid) or ())
        # 去年报告扫到的较长小节标题也可单独命中；丢掉触网专词
        for k in by_chapter.get(cid) or []:
            if k and len(k) >= 8 and k not in strong and not any(f in k for f in _POWER_FOREIGN_NEED):
                strong.append(k)
        hit_keys = [k for k in strong if k and k in full_text]
        if not hit_keys:
            continue
        sample = "、".join(hit_keys[:3])
        out.append({"chapter_id": cid, "reason": f"对照去年目录命中：{sample}", "via": "prior_need"})
    return out


def _merge_hits(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for group in groups:
        for item in group or []:
            cid = item.get("chapter_id") or ""
            if cid not in CHAPTERS or cid in seen:
                continue
            seen.add(cid)
            out.append(item)
    return out


def _hits_power(doc: DocumentModel, assessment_year: int | None = None) -> list[dict[str, str]]:
    """用各章抽取函数试跑：哪一章真抽出了内容，才建议哪一章。

    不写死「总表=第3章+第4章」。今年总表两章都能抽到（3.3.2 状态分布、4.1.2 台数），
    所以会同时出现；明年若某一章不再用这种表，该章抽空就不会再建议。
    同一文件仍可进多章，前提是各章各自抽到了东西。
    """
    from chapters.ch4.power_extract import build_pack as build_ch4
    from chapters.power.extract import (
        extract_compliance,
        extract_controls,
        extract_env,
        extract_grade_tables,
        extract_ch8,
        extract_org_mode,
        extract_plan_table,
        extract_ch7_quality,
        extract_retire,
        extract_stock,
        prepare_power_docs,
    )
    from scope.ledger import clamp_assessment_year

    year = clamp_assessment_year(assessment_year)
    prepared = prepare_power_docs([doc])
    if not prepared:
        return []
    docs = prepared
    hits: list[dict[str, str]] = []

    grades = extract_grade_tables(docs)
    if grades.get("power_table") or grades.get("main_table") or grades.get("energy_table"):
        hits.append({"chapter_id": "ch3", "reason": "抽出了设备评估结果总表（状态分布）"})

    ctrl = extract_controls(docs)
    if ctrl.get("prose") or ctrl.get("appendix"):
        hits.append({"chapter_id": "ch3", "reason": "抽出了管控措施（设备树）"})

    ch4 = build_ch4(docs, year=year)
    if ch4.get("volume_text"):
        hits.append({"chapter_id": "ch4", "reason": "抽出了设备评估结果总表（4.1.2 台数）"})
    if ch4.get("fault_by_line"):
        hits.append({"chapter_id": "ch4", "reason": "抽出了各线故障叙述"})
    if ch4.get("cycle_source"):
        hits.append({"chapter_id": "ch4", "reason": "抽出了维护周期表"})
    if ch4.get("plan_text"):
        hits.append({"chapter_id": "ch4", "reason": "抽出了生产计划完成句"})
    if ch4.get("mtbf_flow") or ch4.get("mtbf_paras") or ch4.get("mtbf_table"):
        hits.append({"chapter_id": "ch4", "reason": "抽出了年度生产指标/MTBF"})

    comp = extract_compliance(docs)
    ch5 = comp.get("ch5") or {}
    ch6 = comp.get("ch6") or {}
    if any(ch5.get(k) for k in ("law", "std_table", "std_paras", "exec", "eval", "drawings", "special", "inspect")):
        hits.append({"chapter_id": "ch5", "reason": "管理体系合规性正文或表"})
    if any(ch6.get(k) for k in ("revise", "tables", "count_table", "intro")):
        hits.append({"chapter_id": "ch6", "reason": "修程修制或规程修订目录"})

    plan = extract_plan_table(docs) or {}
    if plan.get("table"):
        hits.append({"chapter_id": "ch7", "reason": "生产计划执行表"})
    org = extract_org_mode(docs)
    if org.get("paras") or org.get("flow"):
        hits.append({"chapter_id": "ch7", "reason": "生产组织模式"})
    quality = extract_ch7_quality(docs)
    aspects = quality.get("aspects") or {}
    if any((aspects.get(k) or {}).get("paras") or (aspects.get(k) or {}).get("flow") for k in ("meter", "train", "smart")):
        hits.append({"chapter_id": "ch7", "reason": "运维质量分项（仪表/培训/智能化）"})
    if (quality.get("lead") or {}).get("paras"):
        hits.append({"chapter_id": "ch7", "reason": "运维质量开篇"})

    haz = extract_ch8(docs)
    if haz.get("risk_table") or (haz.get("slots") or {}).get("risk_db", {}).get("table"):
        hits.append({"chapter_id": "ch8", "reason": "风险数据库表"})
    if haz.get("handbook"):
        hits.append({"chapter_id": "ch8", "reason": "隐患排查手册表"})
    if haz.get("fault_paras") or haz.get("fault_flow"):
        hits.append({"chapter_id": "ch8", "reason": "典型故障"})
    if haz.get("pdf_paras"):
        hits.append({"chapter_id": "ch8", "reason": "隐患治理 PDF"})

    stock = extract_stock(docs) or {}
    if stock.get("table"):
        reason = "安全库存清单"
        if "管理规定" in (stock.get("source") or ""):
            reason = "已检查库存管理规定，采用变电附录（不含触网）"
        hits.append({"chapter_id": "ch9", "reason": reason})

    if (extract_env(docs) or {}).get("paras"):
        hits.append({"chapter_id": "ch10", "reason": "使用环境说明"})

    retire = extract_retire(docs) or {}
    if any(not (s or {}).get("empty") for s in (retire.get("sections") or [])):
        hits.append({"chapter_id": "ch11", "reason": "退运报废说明"})
    elif retire.get("paras") or retire.get("flow"):
        hits.append({"chapter_id": "ch11", "reason": "退运报废说明"})

    return _merge_hits(hits)


def _hits_from_overhead_excel(doc: DocumentModel) -> list[dict[str, str]]:
    """看全部工作表表头：能汇总状态/体量就建议第 3、4 章，不等用户点名。"""
    from chapters.overhead.excel_status import detect_overhead_excel_capabilities

    by_chapter: dict[str, list[str]] = {}
    for cap in detect_overhead_excel_capabilities(doc):
        reason = str(cap.get("reason") or "").strip()
        for cid in cap.get("chapters") or []:
            if cid not in CHAPTERS:
                continue
            by_chapter.setdefault(cid, [])
            if reason and reason not in by_chapter[cid]:
                by_chapter[cid].append(reason)
    out: list[dict[str, str]] = []
    for cid, reasons in by_chapter.items():
        out.append(
            {
                "chapter_id": cid,
                "reason": "；".join(reasons[:3]),
                "via": "excel_header",
            }
        )
    return out


def _hits_overhead(doc: DocumentModel, assessment_year: int | None = None) -> list[dict[str, str]]:
    """接触网各章抽取试跑：哪一章真抽出了内容，才建议哪一章。"""
    from chapters.overhead.extract import (
        chapter_has_content,
        extract_chapter,
        prepare_overhead_docs,
    )
    from scope.ledger import clamp_assessment_year

    excel_hits = _hits_from_overhead_excel(doc)
    year = clamp_assessment_year(assessment_year)
    prepared = prepare_overhead_docs([doc])
    hits: list[dict[str, str]] = []
    if prepared:
        for cid in CHAPTERS:
            try:
                pack = extract_chapter(prepared, year=year, chapter_id=cid, prior_docs=[])
            except Exception:
                continue
            if chapter_has_content(pack):
                hits.append({"chapter_id": cid, "reason": "接触网抽取命中本章", "via": "extract"})
    return _merge_hits(excel_hits, hits)


def _hits_from_needs_overhead(full_text: str, needs: dict[str, Any] | None) -> list[dict[str, str]]:
    """对照触网去年目录强特征全文命中。"""
    if not full_text:
        return []
    by_chapter = (needs or {}).get("by_chapter") or {}
    out: list[dict[str, str]] = []
    for cid in CHAPTERS:
        strong = list(OVERHEAD_STRONG_NEED_KEYS.get(cid) or ())
        for k in by_chapter.get(cid) or []:
            if k and len(k) >= 8 and k not in strong and not any(f in k for f in _OH_FOREIGN_NEED):
                strong.append(k)
        hit_keys = [k for k in strong if k and k in full_text]
        if not hit_keys:
            continue
        sample = "、".join(hit_keys[:3])
        out.append({"chapter_id": cid, "reason": f"对照触网去年目录命中：{sample}", "via": "prior_need"})
    return out


def _llm_review_chapters(
    doc: DocumentModel,
    *,
    prior_needs: dict[str, Any] | None,
    rule_hits: list[dict[str, str]],
    domain_id: str = "power_supply",
) -> list[dict[str, str]]:
    """规则分章之后，用大模型对照去年目录再从头看一遍，补漏。无 Key 则跳过。"""
    import os

    if not os.getenv("DEEPSEEK_API_KEY"):
        return []
    lexicon = OVERHEAD_LLM_LEXICON if domain_id == "overhead" else POWER_LLM_LEXICON
    defaults = OVERHEAD_DEFAULT_NEED_KEYS if domain_id == "overhead" else POWER_DEFAULT_NEED_KEYS
    inventory = _inventory_for_llm(doc)
    outline = (prior_needs or {}).get("outline_text") or "\n".join(
        f"{cid}: " + "、".join(defaults.get(cid) or ()) for cid in CHAPTERS
    )
    already = "、".join(sorted({x["chapter_id"] for x in rule_hits})) or "无"
    if domain_id == "overhead":
        role = "你是上海轨道交通接触网年报材料分拣员。"
        extra = "只分接触网章节。变电/降压/应急电源/各个线路基本情况等供电内容不要分给接触网。"
        review = "规则已初步分到：" + already + "。请复查是否还有遗漏，尤其是接触网故障趋势、状态分布、备件等。"
    else:
        role = "你是上海轨道交通供电年报材料分拣员。"
        extra = "只分供电章节。接触网故障趋势、接触网设备状态、弓架次不要分给供电。"
        review = "规则已初步分到：" + already + "。请复查是否还有遗漏，尤其是生产指标/MTBF、故障、合规、备件等。"
    try:
        from engine.llm_client import chat_json

        data = chat_json(
            role
            + "下面有「去年报告各章需要的内容」和「今年某份材料的全文结构清单（已从头扫完标题与表头）」。"
            "请判断这份材料应分配到第3～11章中的哪些章（可多选）。"
            "必须根据清单里的正文/表头，不能只看文件名。"
            + extra
            + review
            + "没把握的章不要选。只返回 JSON："
            '{"hits":[{"chapter_id":"ch4","reason":"..."}]}',
            f"去年各章需求：\n{outline}\n\n材料清单：\n{inventory}",
            temperature=0,
        )
    except Exception:
        return []
    raw = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    blob = inventory
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("chapter_id") or "")
        if cid not in lexicon:
            continue
        if not any(key in blob for key in lexicon[cid]):
            continue
        reason = str(item.get("reason") or "模型全文复核").strip()[:80]
        out.append({"chapter_id": cid, "reason": reason, "via": "llm"})
    return out


def _llm_guess(doc: DocumentModel, domain_id: str = "power_supply") -> list[dict[str, str]]:
    """无 prior、规则也抽空时的兜底。"""
    return _llm_review_chapters(doc, prior_needs=None, rule_hits=[], domain_id=domain_id)


def _should_llm_review(doc: DocumentModel, rule_hits: list[dict[str, str]]) -> bool:
    """规则已经能分章时不再全文问模型；管理规定/纯 Excel 命中也不问。"""
    name = _name(doc)
    if any(k in name for k in ("管理规定", "QSD-WBZ", "安全库存管理")):
        return False
    cids = {str(h.get("chapter_id") or "") for h in (rule_hits or []) if h.get("chapter_id")}
    if len(cids) >= 2:
        return False
    if cids and (doc.suffix or "").lower() in {".xlsx", ".xls"}:
        return False
    return True


def _classify_workers() -> int:
    raw = str(os.getenv("CLASSIFY_MAX_WORKERS") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        return max(1, min(8, int(raw)))
    return 4


def classify_document(
    doc: DocumentModel,
    *,
    domain_id: str = "power_supply",
    use_llm: bool = True,
    assessment_year: int | None = None,
    force_power: bool = False,
    prior_needs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """分拣：供电域挑供电并分章；接触网域挑触网并分章。互不套对方规则。

    force_power：网页从「触网不看」捡回时跳过第一步，按供电再分章。
    """
    name = _name(doc)
    empty = {
        "name": name,
        "chapters": [],
        "skip_reason": "",
        "bucket": "",
        "pick_via": "",
        "pick_reason": "",
    }

    if domain_id == "overhead":
        picked = pick_overhead_material(doc, use_llm=use_llm)
        empty["bucket"] = picked["bucket"]
        empty["pick_via"] = picked.get("via") or ""
        empty["pick_reason"] = picked.get("reason") or ""
        if picked["bucket"] == "power":
            empty["skip_reason"] = picked["reason"]
            return empty
        full = _full_text(doc)
        extract_hits = _hits_overhead(doc, assessment_year)
        need_hits = _hits_from_needs_overhead(full, prior_needs)
        rule_hits = _merge_hits(extract_hits, need_hits)
        llm_hits: list[dict[str, str]] = []
        if use_llm and _should_llm_review(doc, rule_hits):
            llm_hits = _llm_review_chapters(
                doc, prior_needs=prior_needs, rule_hits=rule_hits, domain_id="overhead"
            )
        hits = _merge_hits(rule_hits, llm_hits)
        return {
            "name": name,
            "chapters": hits,
            "skip_reason": "" if hits else "已定为接触网材料，但正文对不上第3～11章目录",
            "bucket": picked["bucket"],
            "pick_via": picked.get("via") or "",
            "pick_reason": picked.get("reason") or "",
        }

    if force_power:
        picked = {"bucket": "power", "via": "manual", "reason": "已从触网不看捡回供电包"}
    else:
        picked = pick_power_material(doc, use_llm=use_llm)
    empty["bucket"] = picked["bucket"]
    empty["pick_via"] = picked.get("via") or ""
    empty["pick_reason"] = picked.get("reason") or ""
    if picked["bucket"] == "overhead":
        empty["skip_reason"] = picked["reason"]
        return empty

    full = _full_text(doc)
    extract_hits = _hits_power(doc, assessment_year)
    need_hits = _hits_from_needs(full, prior_needs)
    rule_hits = _merge_hits(extract_hits, need_hits)
    llm_hits = []
    if use_llm and _should_llm_review(doc, rule_hits):
        llm_hits = _llm_review_chapters(
            doc, prior_needs=prior_needs, rule_hits=rule_hits, domain_id="power_supply"
        )
    hits = _merge_hits(rule_hits, llm_hits)
    return {
        "name": name,
        "chapters": hits,
        "skip_reason": "" if hits else "已定为供电材料，但正文对不上第3～11章目录",
        "bucket": picked["bucket"],
        "pick_via": picked.get("via") or "",
        "pick_reason": picked.get("reason") or "",
    }


def _has_body(doc: DocumentModel) -> bool:
    """去重后是否还剩正文或表。只剩空壳（重复表已被掏走）的文件不进 by_chapter。"""
    for block in doc.blocks:
        if block.type == "table" and block.rows:
            return True
        if block.type in {"paragraph", "heading"}:
            text = (block.text or "").strip()
            if text and not text.startswith("工作表:"):
                return True
    return False


def classify_paths(
    paths: list[str | Path],
    *,
    relpaths: list[str] | None = None,
    domain_id: str = "power_supply",
    use_llm: bool = True,
    assessment_year: int | None = None,
    force_power: bool = False,
    prior_paths: list[str | Path] | None = None,
) -> dict[str, Any]:
    """批量解析全年材料：先读去年报告建需求，再全文分章。

    先按表内容去重（优先留下 _1.xlsx）；被判定为重复且已无正文的文件
    只出现在 unused，不写入 by_chapter，避免同一张总表建议三次。
    """
    prior_docs: list[DocumentModel] = []
    prior_digest = ""
    for raw in prior_paths or []:
        try:
            doc, dig, _ = parse_file_cached(Path(raw))
            prior_docs.append(doc)
            prior_digest = dig
        except Exception:
            continue
    # 未上传去年报告 → 用对应专业项目内 2025 保底年报学目录
    if not prior_docs:
        if domain_id == "overhead":
            from chapters.overhead.prior_resolve import resolve_prior_docs
        else:
            from chapters.power.prior_resolve import resolve_prior_docs

        prior_hit = resolve_prior_docs()
        prior_docs = list(prior_hit.get("docs") or [])
        prior_via = prior_hit.get("via") or ""
    else:
        prior_via = "upload"
    prior_needs = build_prior_needs(prior_docs, domain_id=domain_id)

    files: list[dict[str, Any] | None] = []
    by_chapter: dict[str, list[dict[str, Any]]] = {cid: [] for cid in CHAPTERS}
    unused: list[dict[str, Any]] = []
    path_list = [Path(raw) for raw in paths]
    n = len(path_list)
    docs: list[DocumentModel | None] = [None] * n
    errors: list[str] = [""] * n
    files_meta: list[dict[str, Any]] = [{} for _ in range(n)]
    cache_hits = 0
    from parsers.parse_cache import content_sha256 as _content_sha256

    def _hash_one(i: int) -> tuple[int, str, str]:
        path = path_list[i]
        if not path.is_file():
            return i, "", "文件不存在"
        try:
            return i, _content_sha256(path), ""
        except Exception as exc:
            return i, "", str(exc)

    digests = [""] * n
    if n <= 1:
        hashed = [_hash_one(0)] if n else []
    else:
        hashed = []
        with ThreadPoolExecutor(max_workers=min(_classify_workers() + 2, n)) as pool:
            futs = [pool.submit(_hash_one, i) for i in range(n)]
            for fut in as_completed(futs):
                hashed.append(fut.result())
    for i, digest, err in hashed:
        digests[i] = digest
        errors[i] = err

    unique_index: dict[str, int] = {}
    to_parse: list[int] = []
    for i in range(n):
        if errors[i]:
            continue
        digest = digests[i]
        if digest and digest in unique_index:
            continue
        if digest:
            unique_index[digest] = i
        to_parse.append(i)

    def _parse_one(i: int) -> tuple[int, DocumentModel | None, bool, str]:
        try:
            doc, digest, from_cache = parse_file_cached(path_list[i])
            if digest:
                digests[i] = digest
            return i, doc, from_cache, ""
        except Exception as exc:
            return i, None, False, str(exc)

    parsed_map: dict[int, tuple[DocumentModel | None, bool, str]] = {}
    if len(to_parse) <= 1:
        parsed_rows = [_parse_one(to_parse[0])] if to_parse else []
    else:
        parsed_rows = []
        with ThreadPoolExecutor(max_workers=min(_classify_workers() + 2, len(to_parse))) as pool:
            futs = [pool.submit(_parse_one, i) for i in to_parse]
            for fut in as_completed(futs):
                parsed_rows.append(fut.result())
    for i, doc, from_cache, err in parsed_rows:
        parsed_map[i] = (doc, from_cache, err)

    for i in range(n):
        path = path_list[i]
        size = path.stat().st_size if path.is_file() else 0
        if errors[i] and i not in parsed_map:
            files_meta[i] = {"rel": path.name, "name": path.name, "content_sha256": "", "size": size}
            continue
        src = unique_index.get(digests[i], i)
        doc, from_cache, err = parsed_map.get(src, (None, False, errors[i]))
        if i != src and doc is not None:
            doc = copy.deepcopy(doc)
            doc.source_name = path.name
            try:
                doc.source_path = str(path.resolve())
            except Exception:
                doc.source_path = str(path)
            from_cache = True
        docs[i] = doc
        errors[i] = err
        if from_cache:
            cache_hits += 1
        files_meta[i] = {
            "rel": path.name,
            "name": path.name,
            "content_sha256": digests[i],
            "size": size,
        }
    lost = drop_duplicate_tables(docs)

    def _classify_one(i: int) -> tuple[int, dict[str, Any]]:
        path = path_list[i]
        rel = ""
        if relpaths and i < len(relpaths) and relpaths[i]:
            rel = str(relpaths[i]).replace("\\", "/")
        if not rel:
            rel = path.name
        if i < len(files_meta):
            files_meta[i]["rel"] = rel
        item: dict[str, Any] = {
            "relpath": rel,
            "name": path.name,
            "chapters": [],
            "skip_reason": "",
            "bucket": "",
            "pick_via": "",
            "pick_reason": "",
        }
        if errors[i]:
            item["skip_reason"] = f"无法解析：{errors[i]}"
            return i, item
        doc = docs[i]
        if doc is None:
            item["skip_reason"] = "无法解析"
            return i, item
        if i in lost and not _has_body(doc):
            kept = lost[i] or "另一份已建议材料"
            item["skip_reason"] = f"与 {kept} 内容相同，不重复建议"
            return i, item
        judged = classify_document(
            doc,
            domain_id=domain_id,
            use_llm=use_llm,
            assessment_year=assessment_year,
            force_power=force_power,
            prior_needs=prior_needs,
        )
        item["name"] = judged.get("name") or path.name
        item["chapters"] = judged.get("chapters") or []
        item["skip_reason"] = judged.get("skip_reason") or ""
        item["bucket"] = judged.get("bucket") or ""
        item["pick_via"] = judged.get("pick_via") or ""
        item["pick_reason"] = judged.get("pick_reason") or ""
        return i, item

    files = [None] * n  # type: ignore
    if n <= 1:
        classified = [_classify_one(0)] if n else []
    else:
        classified = []
        with ThreadPoolExecutor(max_workers=min(_classify_workers(), n)) as pool:
            futs = [pool.submit(_classify_one, i) for i in range(n)]
            for fut in as_completed(futs):
                classified.append(fut.result())
    for i, item in classified:
        files[i] = item
    files = [x for x in files if x is not None]
    for item in files:
        rel = item.get("relpath") or item.get("name") or ""
        if item["chapters"]:
            for hit in item["chapters"]:
                by_chapter.setdefault(hit["chapter_id"], []).append(
                    {
                        "relpath": rel,
                        "name": item["name"],
                        "reason": hit.get("reason") or "",
                    }
                )
        else:
            unused.append(item)
    assigned = sum(1 for x in files if x["chapters"])

    def _finish(payload: dict[str, Any]) -> dict[str, Any]:
        payload["parse_cache_hits"] = cache_hits
        payload["parse_cache_total"] = len(paths)
        try:
            from parsers.parse_cache import persist_classify_materials

            persist_classify_materials(domain_id, paths, relpaths)
            save_classify_result(
                domain_id,
                result=payload,
                files_meta=files_meta,
                assessment_year=assessment_year,
                prior_digest=prior_digest,
            )
        except Exception:
            pass
        return payload

    if domain_id == "overhead":
        kept = [x for x in files if x.get("bucket") in {"overhead", "mixed"}]
        dropped = [x for x in files if x.get("bucket") == "power"]
        return _finish(
            {
                "domain_id": domain_id,
                "total": len(files),
                "assigned": assigned,
                "kept_count": len(kept),
                "dropped_count": len(dropped),
                "kept_files": kept,
                "dropped_files": dropped,
                "power_picked": len(kept),
                "overhead_dropped": len(dropped),
                "unused_count": len(unused),
                "files": files,
                "power_files": kept,
                "overhead_files": dropped,
                "by_chapter": by_chapter,
                "unused": unused,
                "prior_used": bool(prior_docs),
                "prior_via": prior_via,
                "prior_outline": prior_needs.get("outline_text") or "",
            }
        )
    power_files = [x for x in files if x.get("bucket") in {"power", "mixed"}]
    overhead_files = [x for x in files if x.get("bucket") == "overhead"]
    return _finish(
        {
            "domain_id": domain_id,
            "total": len(files),
            "assigned": assigned,
            "kept_count": len(power_files),
            "dropped_count": len(overhead_files),
            "kept_files": power_files,
            "dropped_files": overhead_files,
            "power_picked": len(power_files),
            "overhead_dropped": len(overhead_files),
            "unused_count": len(unused),
            "files": files,
            "power_files": power_files,
            "overhead_files": overhead_files,
            "by_chapter": by_chapter,
            "unused": unused,
            "prior_used": bool(prior_docs),
            "prior_via": prior_via,
            "prior_outline": prior_needs.get("outline_text") or "",
        }
    )
