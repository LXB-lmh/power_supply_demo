# -*- coding: utf-8 -*-
"""按线路挂小节：仪表/培训/智能化/故障趋势/环境。材料没有的线路不编造。"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.list_number import restart_list_numbers_flow
from chapters.common.section_slice import compact_text, dedupe_flow_items
from chapters.common.source_yellow import para_flow_item
from chapters.common.table_copy import table_flow_item
from chapters.overhead.line_notes import merge_line_notes_with_sources, note_has_body
from chapters.overhead.outline import is_peer_chapter_title
from chapters.overhead.section_bundle import (
    _drawing_item,
    _heading_matches,
    doc_recency_key,
    sort_docs_newest_last,
)
from parsers.document_model import DocumentModel

_LINE_HEAD = re.compile(r"^(?:[（(]?\d{1,2}[、.．)）]\s*)?(?:轨道交通)?(\d{1,2})\s*号线")
_LINE_ANY = re.compile(r"(?:轨道交通)?(\d{1,2})\s*号线")
_KM_RE = re.compile(r"\d{1,2}\s*号线[\s\S]{0,80}条公里")
_CHANGE_RE = re.compile(r"新增|减少|缩短|增加")
_KM_ASSET_RE = re.compile(r"接触网|接触轨|柔性|刚性")
_KM_JUNK_RE = re.compile(
    r"评估围绕|本章小结|摆放标准|附录[A-Za-z]|车梯|差异化管控|预警值|环境因素|粉尘对接触网|磨耗跟踪"
)
_FAULT_RE = re.compile(r"故障次数|故障趋势|自检自修|总计发生|起设备故障|起接触网设备故障")
_TREND_KEEP_RE = re.compile(
    r"典型故障|重大故障|重大设备故障|应对措施|"
    r"当年设备故障值|年设备故障值|设备故障值为|"
    r"设备故障趋势|故障设备趋势|前三年设备故障|"
    r"起设备故障|起接触网设备故障|故障次数|自检自修|总计发生"
)
_TREND_FORMULA_RE = re.compile(
    r"^=|[+\-]?\d+(?:\.\d+)?%\s*$|设备故障趋势|故障设备趋势|"
    r"当年设备故障值|年设备故障值|设备故障值为|前三年设备故障"
)
_TREND_RESULT_RE = re.compile(
    r"^(?:=?\s*[+\-]?\d+(?:\.\d+)?%\s*)$|"
    r"(?:设备故障趋势|故障设备趋势)\s*=\s*[+\-]?\d+(?:\.\d+)?%"
)
_TREND_JUNK_RE = re.compile(r"评估围绕|本章小结|^第三章|^第四章|^第[一二三四五六七八九十0-9]+章")
_TREND_OFFTOPIC_RE = re.compile(
    r"^接触网状态|^当前状态|^大修需求|^大修安排|^大修更新|^集中修项目|"
    r"表B\.47|表3-5|状态分布|评估评价标准|各线路刚性接触网|各线路柔性接触网|"
    r"吊弦专项整治|共需完成\d+套|完成进度\d+%"
)
_POWER_ONLY_HINT = re.compile(
    r"变电所|变电站|整流|杂散电流|主变电|NK11|降压设备|"
    r"降压系统|降压站|牵引站|应急电源系统|变压系统|电力监控系统|直流开关"
)
_OH_HINT = re.compile(r"接触网|触网|接触轨")

LINE_TOPIC_KEYS: dict[str, tuple[str, ...]] = {
    "仪器仪表使用管理方面": ("仪器仪表使用管理", "仪表使用", "仪器仪表"),
    "部门年度培训方面": ("部门年度培训", "年度培训"),
    "智能化应用": ("智能化应用", "新技术应用"),
    "各线路环境符合性评估": ("各线路环境符合性评估", "环境符合性评估"),
    "各线路接触网故障趋势分析": ("各线路接触网故障趋势", "接触网故障趋势", "故障趋势分析"),
    "各线路管控措施": ("各线路管控措施", "接触系统各线路管控措施"),
}

# 正文里常写成「3号线接触网运维…仪器仪表51台」，没有「轨道交通3号线」标题。
# 管控措施只跟专节标题走，避免把第3章状态说明里的「差异化管控」扫进 3.4。
TOPIC_BODY_HINTS: dict[str, tuple[str, ...]] = {
    "仪器仪表使用管理方面": ("仪器仪表", "维护仪器"),
    "部门年度培训方面": ("年度培训",),
    "智能化应用": ("智能化应用", "检测小车"),
    "各线路接触网故障趋势分析": (
        "故障次数",
        "自检自修",
        "故障趋势",
        "典型故障",
        "重大故障",
        "当年设备故障值",
        "起设备故障",
        "起接触网设备故障",
        "设备故障趋势",
        "故障设备趋势",
    ),
    "各线路环境符合性评估": ("环境符合性", "使用环境", "环境因素"),
    "各线路管控措施": ("风险点及管控措施", "管控措施"),
}

EVENT_START_KEYS = ("设施设备年度突出事件分析", "突出事件分析", "突出事件")
# 「原因分析/风险概述」是事件正文小标题，不能当第8章结束。
EVENT_STOP_KEYS = ("评估小结", "备件物资", "接触网安全库存")
_EVENT_BODY_HEAD = (
    "处置情况",
    "原因分析",
    "整改措施",
    "管控措施",
    "后续整改措施",
    "经分析",
    "故障现象",
    "故障原因",
)
_EVENT_SKIP_HEADS = frozenset({"风险概述", "风险数据库"})
_EVENT_FLOW_CAP = 80
_SRC_HEAD_NUM = re.compile(r"^\d+(?:\.\d+)+\s*")
_SRC_HEAD_GLUE = re.compile(r"^\d+(?:\.\d+)+(?=[\u4e00-\u9fff])")
_EVENT_DATE_LEAD = re.compile(
    r"^(?:20\d{6}(?=\d{1,2}号线)|20\d{2}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{2})?)\s*"
)
_EVENT_LIST_LEAD = re.compile(r"^(?:[（(]?\d+[、.．)）]\s*)")
_EVENT_TYPICAL_LEAD = re.compile(
    r"^(?:重大设备故障[:：]\s*)?(?:典型故障[:：]\s*)?(?:\d{1,2}号线典型故障[:：]\s*)?"
)
_EVENT_LINE_SLICE = re.compile(r"^\d{1,2}号线(?:一期|二期|北延伸|南延伸|北北延伸)\s*$")
_CLAUSE_START = re.compile(
    r"^[①②③④⑤⑥⑦⑧⑨⑩]|^[1-9]\s*[、.．)）]\s*(?:统计|年度培训是否|智能化应用的使用)"
)
_WRAP_CH = re.compile(r"^第[一二三四五六七八九十0-9]+章")
_TOPIC_BREAK = re.compile(r"^(?:年度培训|智能化应用使用情况|智能化应用|日常维修计划|生产计划执行)")
_MULTI_LINE = re.compile(
    r"^(?:[（(]?\d{1,2}[、.．)）]\s*)?(?:"
    r"(\d{1,2})\s*号线\s*[、,，和及]\s*(\d{1,2})\s*号线|"
    r"(\d{1,2})\s*[和及]\s*(\d{1,2})\s*号线)"
)
_EVENT_PLACE = (
    "联航路",
    "莘庄",
    "世纪大道",
    "张泾桥",
    "徐泾",
    "浦东南路",
    "基隆路",
    "新闸路",
    "后滩",
)


def _line_title(n: int) -> str:
    return f"轨道交通{n}号线"


def _line_no(text: str) -> int | None:
    m = _LINE_HEAD.match((text or "").strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def _line_no_in(text: str) -> int | None:
    n = _line_no(text)
    if n:
        return n
    m = _LINE_ANY.search(text or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def _line_nos_lead(text: str) -> list[int]:
    t = (text or "").strip()
    m = _MULTI_LINE.match(t)
    if m:
        out = []
        for g in m.groups():
            if not g:
                continue
            n = int(g)
            if 1 <= n <= 18 and n not in out:
                out.append(n)
        return out
    n = _line_no(t)
    return [n] if n else []


def _is_bare_line_title(text: str) -> bool:
    t = re.sub(r"^(?:[（(]?\d+[、.．)）]\s*)", "", str(text or "").strip())
    return bool(re.match(r"^(?:轨道交通)?\d{1,2}\s*号线\s*$", t))


def _is_line_lead(text: str) -> bool:
    t = str(text or "").strip()
    if _is_bare_line_title(t):
        return True
    if not _line_nos_lead(t):
        return False
    return bool(re.match(r"^(?:轨道交通)?\d{1,2}\s*号线\s*[：:]", t))


def _hint_hit(text: str, hints: tuple[str, ...]) -> bool:
    return bool(hints) and any(h in (text or "") for h in hints)


def _junk_intro(text: str) -> bool:
    t = str(text or "").strip()
    if t.startswith("典型故障") or t.startswith("重大故障"):
        return False
    if re.match(r"^=", t) or re.match(r"^[+\-]?\d+(?:\.\d+)?%\s*$", t):
        return False
    if not t or len(t) < 8:
        return True
    if "评估情况撰写" in t or t in {"不存在", "无"}:
        return True
    if _WRAP_CH.match(t) or t.startswith("第七章") or t.startswith("第八章") or t.startswith("第九章"):
        return True
    return False


def _fault_trend_offtopic(text: str) -> bool:
    """4.3 不要状态分布、管控措施、规范表头、两年对照句。"""
    t = str(text or "").strip()
    if not t:
        return True
    if _WRAP_CH.match(t) or t.startswith("第三章") or t.startswith("第四章"):
        return True
    if _TREND_JUNK_RE.search(t) or _TREND_OFFTOPIC_RE.search(t):
        return True
    if "期间" not in t:
        years = set(re.findall(r"20\d{2}年", t))
        if len(years) >= 2 and any(k in t for k in ("总计发生", "自检自修", "故障次数")):
            return True
    if "典型故障" in t or "重大故障" in t or t.startswith("应对措施") or t.startswith("整改措施"):
        return False
    if "期间" in t and "故障" in t:
        return False
    if any(
        k in t
        for k in ("当年设备故障值", "年设备故障值", "设备故障值为", "设备故障趋势", "故障设备趋势", "前三年设备故障")
    ):
        return False
    if re.match(r"^=", t) or re.match(r"^[+\-]?\d+(?:\.\d+)?%\s*$", t):
        return False
    c = compact_text(t)
    if "C状态" in c and ("区段" in c or "区间" in c):
        return True
    if "D状态" in c and ("区段" in c or "区间" in c):
        return True
    if "没有刚性接触网" in c or "没有柔性接触网" in c:
        return True
    if "条公里" in t and "故障" not in t:
        return True
    if "大修更新" in t and "故障" not in t:
        return True
    if "差异化管控" in t or "管控措施" in t or "集中修" in t:
        return True
    if "大磨耗" in t or ("磨耗" in t and "更换" in t and "典型故障" not in t and "期间" not in t):
        return True
    return False


def is_ch4_trend_body(text: str) -> bool:
    """无专节时也只收故障趋势正文，不要把状态/环境续写进来。"""
    t = str(text or "").strip()
    if not t or _fault_trend_offtopic(t):
        return False
    if any(
        k in t
        for k in (
            "典型故障",
            "重大故障",
            "当年设备故障值",
            "年设备故障值",
            "设备故障趋势",
            "故障设备趋势",
            "前三年设备故障",
            "设备故障值为",
            "抢修令",
            "故障事件",
            "起设备故障",
            "起接触网设备故障",
            "拉弧",
        )
    ):
        return True
    if "期间" in t and "故障" in t:
        return True
    if _FAULT_RE.search(t) or _TREND_KEEP_RE.search(t):
        return True
    if _is_trend_continuation(t):
        return True
    return False


def _is_trend_continuation(text: str) -> bool:
    """同一线路 4.3：期间汇总之后的典型故障、历年故障值、趋势公式。"""
    t = str(text or "").strip()
    if not t:
        return False
    if t.startswith("表") or _TREND_OFFTOPIC_RE.search(t) or _TREND_JUNK_RE.search(t):
        return False
    if t.startswith("典型故障") or t.startswith("重大故障") or t.startswith("重大设备故障"):
        return True
    if t.startswith("应对措施") or t.startswith("整改措施"):
        return True
    if _TREND_FORMULA_RE.search(t):
        return True
    if any(k in t for k in ("经过此次", "吸取教训", "后续整改", "经分析")):
        return True
    if "拉弧" in t or "抢修令" in t:
        return True
    if "PLC" in t and any(k in t for k in ("典型故障", "无法操作", "无法遥控", "抢修令", "隔离开关PLC")):
        return True
    return False


def _is_trend_result(text: str) -> bool:
    """已经算出该线设备故障趋势（百分比结果），后面的专项整治等不再续写。"""
    t = compact_text(str(text or ""))
    t = re.sub(r"[（(][^）)]{0,24}[）)]", "", t).strip()
    if _TREND_RESULT_RE.search(t):
        return True
    return bool(len(t) <= 24 and re.fullmatch(r"=?[+\-]?\d+(?:\.\d+)?%", t))


def _same_trend_line(text: str, current: int | None) -> bool:
    """当前线未换线：无号线、或仍是本线。下一线开头则不是续写。"""
    if current is None:
        return False
    t = str(text or "").strip()
    if not t:
        return False
    leads = _line_nos_lead(t)
    if leads:
        return leads[0] == current
    n_in = _line_no_in(t)
    if n_in and n_in != current:
        return False
    return True


_OPEN_LABEL_LINE = re.compile(
    r"^(?:[（(]?\d{1,2}[、.．)）]\s*)?(?:轨道交通)?\d{1,2}\s*号线\s*"
    r"(?:典型故障|重大故障|重大设备故障)"
)


def _is_trend_open_label(text: str) -> bool:
    """典型/重大/整改标签：下一句即使没有拉弧、抢修令也是该线正文。"""
    t = str(text or "").strip()
    if t.startswith(("典型故障", "重大故障", "重大设备故障", "应对措施", "整改措施", "后续整改")):
        return True
    return bool(_OPEN_LABEL_LINE.match(t))


def _keep_trend_follow(text: str, current: int | None, *, open_body: bool) -> bool:
    """标签后的同线叙事、或趋势关键词续写。不把大修/仪表等无关键词段挂进来。"""
    if _is_trend_open_label(text) or _is_trend_continuation(text) or is_ch4_trend_body(text):
        return True
    return bool(open_body and _same_trend_line(text, current))


def _is_period_anchor(text: str) -> int | None:
    t = str(text or "").strip()
    n = _line_no_in(t)
    if not n or _fault_trend_offtopic(t):
        return None
    if ("期间" in t and "故障" in t) or "总计发生" in t:
        return n
    if "趋势分析" in t[:24]:
        return n
    if _FAULT_RE.search(t):
        return n
    return None


def _is_typical_head_anchor(text: str) -> int | None:
    t = str(text or "").strip()
    if not _OPEN_LABEL_LINE.match(t):
        return None
    return _line_no_in(t)


def _is_formula_tail(text: str) -> bool:
    t = str(text or "").strip()
    if not t or _is_trend_open_label(t) or "典型故障" in t[:16]:
        return False
    if _is_trend_result(t) or t.startswith("="):
        return True
    return bool(_TREND_FORMULA_RE.search(t) and "典型" not in t and len(t) < 200)


def _window_break_back(text: str, n: int) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    if is_peer_chapter_title(t) or _TREND_JUNK_RE.search(t) or _TREND_OFFTOPIC_RE.search(t):
        return True
    if t.startswith("表B") or t.startswith("表3"):
        return True
    if any(k in t for k in ("仪器仪表", "维护仪器", "年度培训", "智能化应用")):
        return True
    if _is_trend_result(t):
        return True
    leads = _line_nos_lead(t)
    if leads and leads[0] != n:
        return True
    other = _is_period_anchor(t)
    if other and other != n:
        return True
    return False


def clip_paras_after_trend(paras: list[str] | None) -> list[str]:
    """每条线只保留算到设备故障趋势的那一段，趋势后再出现的典型故障丢掉。"""
    out: list[str] = []
    seen = False
    for raw in paras or []:
        t = str(raw or "").strip()
        if not t:
            continue
        if seen:
            if _is_formula_tail(t):
                out.append(t)
                continue
            break
        out.append(t)
        if _is_trend_result(t):
            seen = True
    return out


def _harvest_windows_from_texts(texts: list[str]) -> dict[int, list[str]]:
    """每条线一个窗口：期间或「N号线典型故障」起，收到第一条趋势结果。"""
    periods: dict[int, list[int]] = {}
    typicals: dict[int, list[int]] = {}
    for i, t in enumerate(texts):
        n = _is_period_anchor(t)
        if n:
            periods.setdefault(n, []).append(i)
        n2 = _is_typical_head_anchor(t)
        if n2:
            typicals.setdefault(n2, []).append(i)
    activations: dict[int, list[int]] = {}
    for n in set(periods) | set(typicals):
        activations[n] = periods[n] if periods.get(n) else typicals[n]
    out: dict[int, list[str]] = {}
    for n, idxs in activations.items():
        start = idxs[0]
        j = start - 1
        looked = 0
        while j >= 0 and looked < 20:
            t = texts[j]
            if _window_break_back(t, n) or _fault_trend_offtopic(t) or _skip_power_topic_para(t):
                break
            if not _same_trend_line(t, n):
                break
            start = j
            j -= 1
            looked += 1
        end = start
        i = start
        got = False
        while i < len(texts):
            t = texts[i]
            if i > start:
                if is_peer_chapter_title(t) or _TREND_JUNK_RE.search(t) or t.startswith("表B") or t.startswith("表3"):
                    break
                leads = _line_nos_lead(t)
                if leads and leads[0] != n and not _is_trend_continuation(t) and not _is_formula_tail(t):
                    break
                other = _is_period_anchor(t)
                if other and other != n:
                    break
            if not (_fault_trend_offtopic(t) or _skip_power_topic_para(t) or t.startswith("表")):
                end = i
            if _is_trend_result(t):
                got = True
                k = i + 1
                while k < len(texts) and _is_formula_tail(texts[k]):
                    end = k
                    k += 1
                break
            i += 1
            if i > start + 28:
                break
        bag: list[str] = []
        seen: set[str] = set()
        last = end if got else min(end, start + 24)
        for t in texts[start : last + 1]:
            if _fault_trend_offtopic(t) or _skip_power_topic_para(t) or t.startswith("表"):
                continue
            if _is_bare_line_title(t):
                continue
            if not _same_trend_line(t, n) and not _is_formula_tail(t) and not _is_trend_open_label(t):
                leads = _line_nos_lead(t)
                if leads and leads[0] != n:
                    continue
            sig = compact_text(t)
            if sig in seen:
                continue
            seen.add(sig)
            bag.append(t)
        if bag:
            clipped = clip_paras_after_trend(bag)
            has_trend = any(_is_trend_result(p) for p in clipped)
            has_43 = any(
                _is_period_anchor(p) == n or "设备故障值" in p or "期间" in p or "总计发生" in p
                for p in clipped
            )
            if not has_trend and not has_43:
                continue
            out[n] = clipped
    return out


def _trend_blob_score(paras: list[str] | None) -> int:
    blob = "".join(paras or [])
    score = len(paras or [])
    if any(k in blob for k in ("设备故障趋势", "故障设备趋势")):
        score += 20
    if "设备故障值" in blob:
        score += 10
    if "典型故障" in blob or "拉弧" in blob or "抢修令" in blob:
        score += 8
    return score


def _is_topic_start_para(text: str) -> bool:
    t = str(text or "").strip()
    if len(compact_text(t)) >= 80:
        return False
    if "评估情况撰写" in t or "条款" in t:
        return False
    if _CLAUSE_START.match(t) or _WRAP_CH.match(t):
        return False
    if t.startswith("不存在"):
        return False
    return True


def _skip_power_topic_para(text: str) -> bool:
    """变电专段不进触网仪表/环境/培训。"""
    t = str(text or "")
    if _OH_HINT.search(t):
        return False
    return bool(_POWER_ONLY_HINT.search(t))


def _env_line_para(text: str) -> bool:
    """环境专节：要环境叙述，不要把第3章状态/管控段因含「漏水」扫进来。"""
    t = str(text or "").strip()
    head = t[:24]
    if any(k in head for k in ("接触网状态", "隔离开关", "集中修", "差异化管控", "柔性接触网", "刚性接触网")):
        return False
    if any(k in t for k in ("大修更新改造", "专项更换", "专项整治", "变电站", "35KV", "35kV", "冷水机组")):
        return False
    if t.startswith("典型故障"):
        return False
    if any(
        k in t
        for k in (
            "共计发现设备缺陷",
            "未发现A类缺陷",
            "C类缺陷",
            "B类缺陷",
            "D类跟踪",
            "状态的下降",
            "系统评价",
            "设备的评价",
        )
    ):
        return False
    return any(
        k in t
        for k in (
            "环境因素",
            "使用环境",
            "环境符合",
            "外部环境",
            "特殊区段",
            "针对漏水",
            "针对粉尘",
            "鸟害",
            "树木侵限",
            "漏水",
            "粉尘",
            "侵限",
            "潮湿",
            "户外段",
            "碎石道床",
            "轨靴",
            "防护罩移位",
            "禁停区",
            "内置式",
            "下锚棘轮",
            "大连路-提篮桥",
        )
    )


def _is_env_continuation(text: str) -> bool:
    """10.2：线路导语之后的雷电/粉尘/侵限分条。"""
    t = str(text or "").strip()
    if not t:
        return False
    if t.startswith("表") or t.startswith("评估结论") or _TREND_JUNK_RE.search(t):
        return False
    if is_peer_chapter_title(t):
        return False
    if re.match(r"^[1-9１-９][、.．)）]", t) and any(
        k in t for k in ("雷电", "粉尘", "异物", "侵限", "空气", "覆冰", "沉降", "湿度", "温度", "暴风")
    ):
        return True
    if t in {"雷电", "粉尘", "异物侵限", "空气污染", "覆冰", "沉降"}:
        return True
    if _env_line_para(t):
        return True
    if any(k in t for k in ("避雷器", "防雷", "驱鸟", "清扫", "绝缘部件", "工业重度污染")):
        return True
    return False


def _is_intel_continuation(text: str) -> bool:
    t = str(text or "").strip()
    if not t or t.startswith("表"):
        return False
    return any(
        k in t
        for k in (
            "检测小车",
            "4C小车",
            "线岔检测",
            "放线小车",
            "智能化",
            "在线监测",
            "吊弦预制",
            "隔离开关机构箱培训",
        )
    )


def _block_item(doc: DocumentModel, block) -> dict[str, Any] | None:
    if block.type == "drawing":
        return _drawing_item(doc, block)
    if block.type == "table" and block.rows:
        if len(block.rows) > 80:
            return None
        return table_flow_item(doc, block)
    t = (block.text or "").strip()
    if t:
        return para_flow_item(t, block)
    return None


def _sections_from_map(
    by_line: dict[int, list[dict[str, Any]]],
    sources: dict[int, str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in sorted(by_line):
        flow = dedupe_flow_items(by_line[n])
        paras = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
        empty = not any(
            (x.get("kind") == "para" and note_has_body(str(x.get("text") or "")))
            or x.get("kind") in {"table", "drawing"}
            for x in flow
        )
        if empty:
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


_DEPT_STEM = re.compile(r"维护[一二三四五六七八九十]+部")


def _dept_stem(name: str) -> str:
    m = _DEPT_STEM.search(name or "")
    return m.group(0) if m else ""


def _append_line_para(
    by_line: dict[int, list[dict[str, Any]]],
    line_src: dict[int, str],
    n: int,
    text: str,
    src: str,
    *,
    claimed: set[int] | None = None,
    writing: set[int] | None = None,
) -> None:
    if claimed is not None and n in claimed:
        return
    t = str(text or "").strip()
    if not t:
        return
    bag = by_line.setdefault(n, [])
    sig = compact_text(t)
    if any(compact_text(str(x.get("text") or "")) == sig for x in bag if x.get("kind") == "para"):
        return
    bag.append({"kind": "para", "text": t})
    line_src.setdefault(n, src)
    if writing is not None:
        writing.add(n)


def _append_line_item(
    by_line: dict[int, list[dict[str, Any]]],
    current: int | None,
    item: dict[str, Any],
    *,
    claimed: set[int] | None = None,
    writing: set[int] | None = None,
) -> bool:
    if current is None:
        return False
    if claimed is not None and current in claimed:
        return False
    by_line.setdefault(current, []).append(item)
    if writing is not None:
        writing.add(current)
    return True


def extract_topic_line_sections(
    docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...] = (),
    body_hints: tuple[str, ...] = (),
) -> dict[str, Any]:
    """标题后按「轨道交通N号线」切开；没有标题则按「N号线：」/「N号线…关键词」合并。"""
    by_line: dict[int, list[dict[str, Any]]] = {}
    line_src: dict[int, str] = {}
    intro: list[dict[str, Any]] = []
    intro_src = ""
    note_items: list[dict[str, Any]] = []
    stops = tuple(stop_keys) + tuple(LINE_TOPIC_KEYS.keys()) + ("评估小结",)
    hints = tuple(body_hints)
    if not hints:
        collected: list[str] = []
        start_blob = compact_text(" ".join(start_keys))
        for title, hs in TOPIC_BODY_HINTS.items():
            keys = (title,) + (LINE_TOPIC_KEYS.get(title) or ())
            if any(compact_text(k) and (compact_text(k) in start_blob or start_blob in compact_text(k)) for k in keys):
                collected.extend(hs)
        hints = tuple(dict.fromkeys(collected))

    from chapters.common.domain_filter import is_power_fault_situation_doc

    claimed_lines: set[int] = set()
    intro_depts: set[str] = set()
    for doc, idx in reversed(list(sort_docs_newest_last(docs or []))):
        if is_power_fault_situation_doc(doc):
            continue
        src_name = doc.source_name or ""
        if "报废" in src_name and any(k in src_name for k in ("情况说明", "工器具", "仪器仪表")):
            continue
        writing: set[int] = set()
        recency = doc_recency_key(doc, idx)[0]
        src = doc.source_name or ""
        blocks = list(doc.blocks or [])
        start_i: int | None = None
        start_depth = 4
        for i, block in enumerate(blocks):
            t = (block.text or "").strip()
            if not t:
                continue
            if not _heading_matches(t, start_keys):
                continue
            if block.type == "heading":
                start_i = i
                start_depth = int(block.level or 3)
                break
            if block.type == "paragraph" and _is_topic_start_para(t):
                start_i = i
                start_depth = 3
                break
        current: int | None = None
        paras_for_notes: list[str] = []
        saw_line = False
        if start_i is not None:
            open_body = False
            done: set[int] = set()
            for j in range(start_i + 1, min(len(blocks), start_i + 220)):
                block = blocks[j]
                t = (block.text or "").strip()
                if t and is_peer_chapter_title(t, current=start_keys[0] if start_keys else ""):
                    break
                if block.type == "heading" and t:
                    depth = int(block.level or 3)
                    if depth <= start_depth and not _line_no(t):
                        if _heading_matches(t, stops) or not _heading_matches(t, start_keys):
                            break
                    ln_heads = _line_nos_lead(t)
                    if ln_heads:
                        open_lns = [n for n in ln_heads if n not in claimed_lines]
                        if (_is_bare_line_title(t) or _hint_hit(t, hints)) and open_lns:
                            saw_line = True
                            current = open_lns[0]
                            open_body = False
                            for n in open_lns:
                                line_src[n] = src
                                writing.add(n)
                        else:
                            current = None
                            open_body = False
                        continue
                item = _block_item(doc, block)
                if not item:
                    continue
                para_txt = str(item.get("text") or "") if item.get("kind") == "para" else ""
                if para_txt and _TOPIC_BREAK.match(para_txt) and not _hint_hit(para_txt, hints):
                    current = None
                    open_body = False
                    continue
                ln_heads = _line_nos_lead(para_txt)
                envish = any(h in {"环境符合性", "使用环境", "环境因素"} for h in hints)
                intelish = any(h in {"智能化应用", "检测小车"} for h in hints)
                if envish:
                    topic_hit = _env_line_para(para_txt)
                else:
                    topic_hit = _hint_hit(para_txt, hints) or (
                        intelish and _is_intel_continuation(para_txt)
                    )
                if ln_heads and hints and topic_hit and not _skip_power_topic_para(para_txt):
                    if any(n in done for n in ln_heads):
                        current = None
                        open_body = False
                        continue
                    for n in ln_heads:
                        _append_line_para(
                            by_line, line_src, n, para_txt, src, claimed=claimed_lines, writing=writing
                        )
                    open_lns = [n for n in ln_heads if n not in claimed_lines]
                    if not open_lns:
                        current = None
                        open_body = False
                        continue
                    saw_line = True
                    current = open_lns[0]
                    open_body = _is_trend_open_label(para_txt)
                    paras_for_notes.append(para_txt)
                    continue
                faultish = any(h in {"故障次数", "典型故障", "故障趋势", "自检自修"} for h in hints)
                n_mid = _line_no_in(para_txt) if item.get("kind") == "para" else None
                period = bool(n_mid and (("期间" in para_txt and "故障" in para_txt) or "总计发生" in para_txt))
                if faultish and n_mid and n_mid in done:
                    current = None
                    open_body = False
                    continue
                if (
                    faultish
                    and n_mid
                    and (period or _hint_hit(para_txt, hints) or _is_trend_continuation(para_txt))
                    and not _skip_power_topic_para(para_txt)
                    and not _fault_trend_offtopic(para_txt)
                ):
                    _append_line_para(
                        by_line, line_src, n_mid, para_txt, src, claimed=claimed_lines, writing=writing
                    )
                    if n_mid in claimed_lines:
                        current = None
                        open_body = False
                        continue
                    saw_line = True
                    current = n_mid
                    open_body = _is_trend_open_label(para_txt)
                    paras_for_notes.append(para_txt)
                    continue
                if faultish and current is not None and item.get("kind") == "para":
                    if current in done:
                        current = None
                        open_body = False
                        continue
                    if _keep_trend_follow(para_txt, current, open_body=open_body):
                        if not _fault_trend_offtopic(para_txt) and not _skip_power_topic_para(para_txt):
                            _append_line_item(
                                by_line, current, item, claimed=claimed_lines, writing=writing
                            )
                            paras_for_notes.append(para_txt)
                            if _is_trend_open_label(para_txt):
                                open_body = True
                            if _is_trend_result(para_txt):
                                done.add(current)
                                current = None
                                open_body = False
                    continue
                if current is not None and current in claimed_lines:
                    current = None
                    open_body = False
                if envish and current is not None and item.get("kind") == "para":
                    if _is_env_continuation(para_txt) and not _skip_power_topic_para(para_txt):
                        _append_line_item(
                            by_line, current, item, claimed=claimed_lines, writing=writing
                        )
                        paras_for_notes.append(para_txt)
                    continue
                if intelish and current is not None and item.get("kind") == "para":
                    if _is_intel_continuation(para_txt) and not _skip_power_topic_para(para_txt):
                        _append_line_item(
                            by_line, current, item, claimed=claimed_lines, writing=writing
                        )
                        paras_for_notes.append(para_txt)
                    continue
                if ln_heads and hints and not topic_hit:
                    if current is None or ln_heads[0] != current:
                        current = None
                        open_body = False
                        continue
                if current is None:
                    stem = _dept_stem(src)
                    take_intro = not stem or stem not in intro_depts
                    if item.get("kind") == "para":
                        paras_for_notes.append(para_txt)
                        if take_intro and not saw_line and not _line_no(para_txt) and not _junk_intro(para_txt):
                            if len(intro) < 8:
                                intro.append(item)
                                intro_src = intro_src or src
                                if stem:
                                    intro_depts.add(stem)
                    elif take_intro and not saw_line and len(intro) < 8:
                        intro.append(item)
                        intro_src = intro_src or src
                        if stem:
                            intro_depts.add(stem)
                    continue
                n_in = _line_no_in(para_txt)
                if (
                    item.get("kind") == "para"
                    and n_in
                    and n_in != current
                    and hints
                    and _hint_hit(para_txt, hints)
                    and not _skip_power_topic_para(para_txt)
                ):
                    _append_line_para(
                        by_line, line_src, n_in, para_txt, src, claimed=claimed_lines, writing=writing
                    )
                    continue
                if item.get("kind") == "para" and n_in and n_in != current:
                    continue
                if item.get("kind") == "para" and (_skip_power_topic_para(para_txt) or _junk_intro(para_txt)):
                    continue
                if (
                    item.get("kind") == "para"
                    and any(h in {"环境符合性", "使用环境", "环境因素"} for h in hints)
                    and any(k in para_txt[:24] for k in ("接触网状态", "隔离开关", "集中修", "差异化管控"))
                ):
                    continue
                if item.get("kind") == "para" and any(
                    h in {"故障次数", "典型故障", "故障趋势", "自检自修"} for h in hints
                ):
                    if _fault_trend_offtopic(para_txt):
                        continue
                _append_line_item(by_line, current, item, claimed=claimed_lines, writing=writing)
                if item.get("kind") == "para":
                    paras_for_notes.append(para_txt)
                    if faultish and _is_trend_result(para_txt):
                        if current is not None:
                            done.add(current)
                        current = None
                        open_body = False
            if paras_for_notes:
                note_items.append(
                    {
                        "notes": paras_for_notes,
                        "_recency": recency,
                        "_idx": idx,
                        "_source": src,
                    }
                )
        loose = any(h in {"仪器仪表", "维护仪器", "年度培训", "智能化应用", "检测小车"} for h in hints)
        envish = any(h in {"环境符合性", "使用环境", "环境因素"} for h in hints)
        intelish = any(h in {"智能化应用", "检测小车"} for h in hints)
        if start_i is None and hints:
            current = None
            open_body = False
            for block in blocks:
                t = (block.text or "").strip()
                if not t:
                    continue
                if is_peer_chapter_title(t, current=start_keys[0] if start_keys else ""):
                    current = None
                    open_body = False
                    continue
                lns = _line_nos_lead(t)
                short = block.type == "heading" or _is_bare_line_title(t) or _is_line_lead(t)
                if envish:
                    topic_hit = _env_line_para(t)
                else:
                    topic_hit = _hint_hit(t, hints) or (
                        intelish and _is_intel_continuation(t)
                    )
                if lns and (short or topic_hit):
                    open_lns = [n for n in lns if n not in claimed_lines]
                    if open_lns and (topic_hit or _is_bare_line_title(t) or _is_line_lead(t) or (loose and short)):
                        current = open_lns[0]
                        open_body = _is_trend_open_label(t)
                        for n in open_lns:
                            line_src[n] = src
                            writing.add(n)
                    else:
                        current = None
                        open_body = False
                    continue
                if current is None:
                    continue
                if _TOPIC_BREAK.match(t) and not topic_hit:
                    current = None
                    open_body = False
                    continue
                item = _block_item(doc, block)
                if not item:
                    continue
                para_txt = str(item.get("text") or "") if item.get("kind") == "para" else ""
                if item.get("kind") == "para" and (
                    _skip_power_topic_para(para_txt) or _junk_intro(para_txt)
                ):
                    continue
                n_in = _line_no_in(para_txt)
                faultish = any(h in {"故障次数", "典型故障", "故障趋势", "自检自修"} for h in hints)
                if item.get("kind") == "para" and n_in and n_in != current:
                    if faultish and not is_ch4_trend_body(para_txt):
                        continue
                    if (
                        (envish and _env_line_para(para_txt))
                        or (not envish and _hint_hit(para_txt, hints))
                        or (faultish and is_ch4_trend_body(para_txt))
                    ):
                        _append_line_para(
                            by_line, line_src, n_in, para_txt, src, claimed=claimed_lines, writing=writing
                        )
                        if n_in not in claimed_lines:
                            current = n_in
                            open_body = _is_trend_open_label(para_txt)
                    continue
                if item.get("kind") == "para" and not _hint_hit(para_txt, hints):
                    if not (
                        (faultish and _keep_trend_follow(para_txt, current, open_body=open_body))
                        or (envish and _is_env_continuation(para_txt))
                        or (intelish and _is_intel_continuation(para_txt))
                    ):
                        continue
                if (
                    item.get("kind") == "para"
                    and faultish
                    and not _keep_trend_follow(para_txt, current, open_body=open_body)
                ):
                    continue
                _append_line_item(by_line, current, item, claimed=claimed_lines, writing=writing)
                if item.get("kind") == "para" and _is_trend_open_label(para_txt):
                    open_body = True
                if item.get("kind") == "para" and faultish and _is_trend_result(para_txt):
                    current = None
                    open_body = False
        # 没有专节标题时，仍按「N号线…关键词」收。4.3 不在全篇补挂，避免趋势后再收突出事件里的典型故障。
        if hints:
            faultish_scan = any(h in {"故障次数", "典型故障", "故障趋势", "自检自修"} for h in hints)
            for block in blocks:
                t = (block.text or "").strip()
                if not t or block.type not in {"paragraph", "heading"}:
                    continue
                lns = _line_nos_lead(t)
                if not lns:
                    continue
                if faultish_scan:
                    continue
                if any(h in {"环境符合性", "使用环境", "环境因素"} for h in hints):
                    if not _env_line_para(t) or _skip_power_topic_para(t):
                        continue
                elif not _hint_hit(t, hints) or _skip_power_topic_para(t):
                    continue
                if len(t) < 12:
                    continue
                for n in lns:
                    _append_line_para(
                        by_line, line_src, n, t, src, claimed=claimed_lines, writing=writing
                    )
        # 智能化导语：验电器/检测小车未写号线，挂父节不编线路
        if hints and any(h in {"智能化应用", "检测小车"} for h in hints):
            stem = _dept_stem(src)
            take_intro = not stem or stem not in intro_depts
            for block in blocks:
                t = (block.text or "").strip()
                if not t or block.type not in {"paragraph", "heading"}:
                    continue
                if _line_no_in(t) or _skip_power_topic_para(t) or _junk_intro(t):
                    continue
                if not any(k in t for k in ("验电器", "检测小车", "智能化")):
                    continue
                if not take_intro or len(t) < 12 or len(intro) >= 8:
                    continue
                intro.append({"kind": "para", "text": t})
                intro_src = intro_src or src
                if stem:
                    intro_depts.add(stem)
        if hints and any(h in {"智能化应用", "环境因素"} for h in hints):
            envish_scan = any(h in {"环境符合性", "使用环境", "环境因素"} for h in hints)
            for block in blocks:
                t = (block.text or "").strip()
                if not t or block.type not in {"paragraph", "heading"}:
                    continue
                if _skip_power_topic_para(t):
                    continue
                if envish_scan:
                    if not _env_line_para(t):
                        continue
                elif not any(h in t for h in hints):
                    continue
                ln = _line_no_in(t)
                if not ln or _line_no(t):
                    continue
                if len(t) < 12:
                    continue
                _append_line_para(
                    by_line, line_src, ln, t, src, claimed=claimed_lines, writing=writing
                )
        claimed_lines.update(writing)

    if note_items and not any(h in {"故障次数", "典型故障", "故障趋势", "自检自修"} for h in hints):
        line_map, _general, _w, src_map = merge_line_notes_with_sources(note_items)
        for key, text in line_map.items():
            if not note_has_body(text):
                continue
            n = int(key)
            if n in by_line:
                continue
            by_line[n] = [{"kind": "para", "text": text}]
            line_src[n] = src_map.get(key) or ""

    sections = _sections_from_map(by_line, line_src)
    intro = dedupe_flow_items(intro)
    hit = {
        "intro": intro,
        "sections": sections,
        "source": intro_src or "、".join(s for s in dict.fromkeys(line_src.values()) if s),
        "empty": not intro and not sections,
    }
    try:
        from chapters.overhead.llm_gate import filter_topic_hit, topic_kind_from_hints

        return filter_topic_hit(hit, kind=topic_kind_from_hints(hints), context=" ".join(start_keys[:4]))
    except Exception:
        return hit


def extract_event_sections(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """8.1 下各篇故障分析：标题收短、正文接到原因/整改，部门稿分段续写。"""
    cases: list[dict[str, Any]] = []
    intro: list[dict[str, Any]] = []
    for doc, idx in sort_docs_newest_last(docs or []):
        recency = doc_recency_key(doc, idx)
        src = doc.source_name or ""
        current_title = ""
        current_flow: list[dict[str, Any]] = []

        def _flush() -> None:
            nonlocal current_title, current_flow
            if current_title and current_flow:
                cases.append(
                    _event_child(current_title, current_flow[:_EVENT_FLOW_CAP], src, recency=recency)
                )
            current_title = ""
            current_flow = []

        for block in doc.blocks or []:
            t = (block.text or "").strip()
            title_like = block.type == "heading" or (
                block.type == "paragraph" and t and len(t) < 90 and t[-1:] not in "。！？"
            )
            if current_title and t and _event_section_break(t):
                _flush()
            if title_like and _is_event_title(t):
                if current_title and current_flow:
                    _flush()
                current_title = t
                current_flow = []
                continue
            ev = None
            if t and not _event_noise(t):
                ev = _typical_fault_as_event(t, src, recency=recency) or _incident_lead_event(
                    t, src, recency=recency
                )
            if ev:
                if current_title:
                    probe = _event_child(
                        current_title,
                        current_flow or [{"kind": "para", "text": current_title}],
                        src,
                    )
                    if _event_sig(ev) == _event_sig(probe):
                        ev = None
                    else:
                        _flush()
                if ev:
                    current_title = str(ev.get("title") or t)
                    current_flow = list((ev.get("fill") or {}).get("flow") or [])
                    continue
            if not current_title:
                if title_like and _heading_matches(t, EVENT_START_KEYS) and len(compact_text(t)) < 48:
                    continue
                continue
            item = _block_item(doc, block)
            if not item:
                continue
            if item.get("kind") == "para":
                raw = _normalize_event_para(str(item.get("text") or ""))
                if not raw or _event_noise(raw) or raw in _EVENT_SKIP_HEADS:
                    continue
                item = dict(item)
                item["text"] = raw
            current_flow.append(item)
            if len(current_flow) >= _EVENT_FLOW_CAP:
                _flush()
        if current_title and current_flow:
            _flush()
    by_sig: dict[str, dict[str, Any]] = {}
    for c in cases:
        title = str(c.get("title") or "")
        lead = str((c.get("paras") or [""])[0] or "")
        if _event_noise(title) or _event_noise(lead):
            continue
        recency = c.get("_recency")
        flow = [
            x
            for x in (c.get("fill") or {}).get("flow") or []
            if x.get("kind") != "para" or not _event_noise(str(x.get("text") or ""))
        ]
        if flow:
            c = _event_child(title, flow, str(c.get("source") or ""), recency=recency)
        if c.get("empty"):
            continue
        sig = _event_sig(c)
        prev = by_sig.get(sig)
        prev_rec = (prev or {}).get("_recency") or (0, 0, 0)
        cur_rec = c.get("_recency") or (0, 0, 0)
        plen = len((prev or {}).get("paras") or [])
        clen = len(c.get("paras") or [])
        if prev is None or cur_rec > prev_rec or (
            cur_rec == prev_rec and (clen > plen or (clen == plen and "故障分析" in title))
        ):
            by_sig[sig] = c
    sections = list(by_sig.values())
    sections.sort(key=lambda s: _event_dept_rank(str(s.get("source") or "")))
    try:
        from chapters.overhead.llm_gate import filter_event_sections

        sections = filter_event_sections(sections)
    except Exception:
        pass
    return {
        "intro": dedupe_flow_items(intro),
        "sections": sections,
        "empty": not sections and not intro,
        "source": "、".join(s.get("source") or "" for s in sections if s.get("source")),
    }


def _is_event_title(text: str) -> bool:
    t = re.sub(r"^(?:[（(]?\d+[、.．)）]\s*)", "", str(text or "").strip())
    t = _EVENT_DATE_LEAD.sub("", t).strip()
    if len(t) <= 8 or len(t) >= 90:
        return False
    if t[-1:] in "。！？" and not ("故障事件" in t and len(t) < 55):
        return False
    if any(k in t for k in ("故障分析", "故障事件分析", "故障事件")):
        return True
    if "情况说明" in t and any(k in t for k in ("侵限", "跳闸", "故障")):
        return True
    if _line_no_in(t) and re.search(r"无法遥控|拒动|拉弧|烧伤|断裂|合闸不到|短路接地", t):
        return True
    return False


def _normalize_event_para(text: str) -> str:
    t = str(text or "").strip()
    t = _SRC_HEAD_NUM.sub("", t).strip()
    t = _SRC_HEAD_GLUE.sub("", t).strip()
    if re.search(r"[#＃]抢修令$", t):
        t += "。"
    return t


def _event_section_break(text: str) -> bool:
    t = _EVENT_LIST_LEAD.sub("", str(text or "").strip())
    if not t:
        return False
    if is_peer_chapter_title(t) or _heading_matches(t, EVENT_STOP_KEYS):
        return True
    if _WRAP_CH.match(t):
        return True
    if "评估情况撰写" in t:
        return True
    if t.startswith("表B") or t.startswith("表B."):
        return True
    if any(
        k in t
        for k in ("当年设备故障值", "年设备故障值", "设备故障趋势", "故障设备趋势", "前三年设备故障")
    ):
        return True
    if _is_trend_result(t):
        return True
    if re.match(r"^\d{1,2}号线典型故障", t) or re.match(r"^典型故障[:：]?\s*$", t):
        return True
    if t.startswith("重大故障"):
        return True
    if _EVENT_LINE_SLICE.match(t):
        return True
    if "期间" in t and "总计发生" in t:
        return True
    if re.match(r"^和20\d{2}年评估对比", t):
        return True
    return False


def _event_dept_rank(src: str) -> int:
    n = src or ""
    if "维护七部" in n:
        return 0
    if "维护六部" in n:
        return 1
    if "维护五部" in n:
        return 2
    return 3


def _clean_event_title(raw: str, flow: list[dict[str, Any]] | None = None) -> str:
    blob = str(raw or "") + " " + " ".join(
        str(x.get("text") or "") for x in (flow or [])[:8] if x.get("kind") == "para"
    )
    t = str(raw or "").strip()
    t = _EVENT_LIST_LEAD.sub("", t)
    t = _EVENT_TYPICAL_LEAD.sub("", t)
    t = _EVENT_DATE_LEAD.sub("", t).strip(" ：:；;")
    t = t.split("。", 1)[0].strip()
    composed = _compose_event_title(blob)
    narrative = any(k in t for k in ("现象", "发布", "发现", "存在", "自检", "夜间", "施工结束"))
    looks_heading = (
        8 < len(t) < 48
        and t.endswith("分析")
        and not narrative
    )
    if looks_heading:
        return t
    if composed:
        return composed
    if t.endswith("事件") and 8 < len(t) < 48:
        return t + "分析"
    if 8 < len(t) < 40 and "号线" in t and not narrative:
        return t if t.endswith("分析") else f"{t}故障分析"
    return composed or t[:40]


def _compose_event_title(blob: str) -> str:
    blob = re.sub(r"20\d{6}(?=\d{1,2}号线)", "", blob)
    m = re.search(r"(?<!\d)(\d{1,2}号线)", blob)
    if not m:
        return ""
    line = m.group(1)
    place = next((k for k in _EVENT_PLACE if k in blob), "")
    if "断裂" in blob:
        return f"{line}{place}接触网设备断裂故障分析" if place else f"{line}接触网设备断裂故障分析"
    if "触网闸刀控制屏柜PLC故障事件" in blob or ("PLC" in blob and "故障事件" in blob):
        if "触网闸刀控制屏柜PLC故障事件" in blob:
            yard = "车场" if "车场" in blob and place and not place.endswith("车场") else ""
            return f"{line}{place}{yard}触网闸刀控制屏柜PLC故障事件分析"
        return f"{line}{place}PLC故障事件分析"
    if "无法遥控" in blob:
        m2 = re.search(r"混变[\d\-—]+触网闸刀中央无法遥控操作", blob)
        mid = m2.group(0) if m2 else "触网闸刀中央无法遥控操作"
        return f"{line}{place}{mid}故障分析"
    if "短路接地" in blob or ("XC04" in blob and "电缆" in blob):
        loc = f"{place}车场" if place and "车场" in blob else place
        extra = "XC04联络电缆短路接地" if "XC04" in blob else "联络电缆短路接地"
        return f"{line}{loc}{extra}故障分析"
    if "合闸不到" in blob or "合闸未到位" in blob:
        m2 = re.search(r"(\d{3,4})触网闸刀", blob)
        knife = m2.group(0) if m2 else "触网闸刀"
        mid = "牵引站" if "牵引" in blob else ""
        return f"{line}{place}{mid}{knife}合闸不到位故障分析"
    if "PLC" in blob:
        return f"{line}{place}PLC故障事件分析"
    if "烧伤" in blob:
        knife = "2111隔离开关静刀头" if "2111" in blob else "隔离开关静刀头"
        st = "站" if "站" in blob and place else ""
        return f"{line}{place}{st}{knife}烧伤故障分析"
    if "拉弧" in blob:
        if "锚段关节" in blob:
            return f"{line}{place}锚段关节拉弧故障分析"
        if "分段绝缘器" in blob:
            return f"{line}{place}分段绝缘器拉弧故障分析"
        return f"{line}{place}拉弧故障分析"
    if "无法合闸" in blob or "拒动" in blob:
        m2 = re.search(r"混变\s*[\d\-—]+", blob)
        if m2:
            mix = m2.group(0).replace(" ", "")
        else:
            m3 = re.search(r"([\d\-—]{3,})触网闸刀", blob)
            mix = f"混变{m3.group(1)}" if m3 and "混变" in blob else ""
        if place == "后滩" and mix:
            mix = mix.replace("-", "—")
        return f"{line}{place}{mix}触网闸刀拒动故障分析"
    if place:
        return f"{line}{place}故障分析"
    return ""


def _event_noise(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    if t in _EVENT_SKIP_HEADS:
        return True
    if t in _EVENT_BODY_HEAD or any(t.startswith(k) for k in _EVENT_BODY_HEAD):
        return False
    if _WRAP_CH.match(t):
        return True
    if "评估情况撰写" in t:
        return True
    if re.match(r"^\d+(?:\.\d+)+\s*风险", t):
        return True
    if any(k in t for k in ("大磨耗", "预警值", "条公里")) and "抢修令" not in t:
        return True
    return False


def _event_sig(child: dict[str, Any]) -> str:
    blob = str(child.get("title") or "") + " " + " ".join(str(p) for p in (child.get("paras") or [])[:1])
    blob = re.sub(r"20\d{6}(?=\d{1,2}号线)", "", blob)
    m = re.search(r"(?<!\d)(\d{1,2}号线)", blob)
    place = next((k for k in _EVENT_PLACE if k in blob), "")
    if m and place:
        return f"{m.group(1)}|{place}"
    return compact_text(str(child.get("title") or blob)[:40])


def _typical_fault_as_event(text: str, src: str, recency=None) -> dict[str, Any] | None:
    t = str(text or "").strip()
    if len(t) < 24 or len(t) > 2500:
        return None
    if "号线" not in t:
        return None
    if not any(k in t for k in ("典型故障", "故障事件", "重大设备故障")):
        return None
    if not any(k in t for k in _EVENT_PLACE):
        return None
    if not any(
        k in t
        for k in ("抢修令", "跳闸", "拉弧", "拒动", "断裂", "烧伤", "无法遥控", "短路", "合闸", "PLC", "失电")
    ):
        return None
    first = t.split("。", 1)[0].strip(" 。；")
    if 12 <= len(first) <= 80:
        title = re.sub(r"^(?:[（(]?\d+[、.．)）]\s*)", "", first).strip()
    else:
        m = re.search(r"(\d{1,2}号线.{0,24}(?:典型故障|故障事件))", t)
        title = m.group(1) if m else first[:40]
    return _event_child(title, [{"kind": "para", "text": t}], src, recency=recency)


def _incident_lead_event(text: str, src: str, recency=None) -> dict[str, Any] | None:
    """无「故障分析」标题时，收「N号线…拉弧/烧伤/拒动」首句+原文，不改写。"""
    t = str(text or "").strip()
    if len(t) < 24 or len(t) > 2500:
        return None
    first = t.split("。", 1)[0].strip(" 。；")
    if not _line_no(t) and not _line_no_in(first):
        return None
    if not any(k in t for k in _EVENT_PLACE):
        return None
    if any(k in first for k in ("差异化管控", "集中修", "大修需求", "状态分布", "后续整改", "大磨耗", "预警值")):
        return None
    hit = re.search(r"无法遥控|无法合闸|拒动|拉弧|烧伤|断裂|合闸不到|短路接地", first) or re.search(
        r"无法遥控|无法合闸|拒动|拉弧|烧伤|断裂", t[:100]
    )
    if not hit:
        return None
    if not any(k in t for k in ("抢修令", "故障事件", "典型故障", "故障分析", "无法遥控", "无法合闸", "拉弧", "烧伤")):
        return None
    if 12 <= len(first) <= 88:
        title = first
    else:
        m = re.search(
            r"(\d{1,2}号线.{0,24}(?:新闸路|后滩|拉弧|无法合闸|无法遥控|拒动|烧伤|断裂))",
            t,
        )
        title = m.group(1) if m else first[:40]
    return _event_child(title, [{"kind": "para", "text": t}], src, recency=recency)


def sections_from_line_paras(paras: list[str] | None, source: str = "") -> tuple[list[str], list[dict[str, Any]]]:
    """按号线收小节；没有号线的趋势续写（典型故障/历年值/公式）挂在上一线。"""
    by_line: dict[int, list[dict[str, Any]]] = {}
    line_src: dict[int, str] = {}
    general: list[str] = []
    current: int | None = None
    for raw in paras or []:
        t = str(raw or "").strip()
        if not t:
            continue
        n = _line_no(t) or _line_no_in(t)
        if n:
            current = n
            _append_line_para(by_line, line_src, n, t, source)
            if _is_trend_result(t):
                current = None
        elif current and not _fault_trend_offtopic(t) and not _skip_power_topic_para(t):
            _append_line_para(by_line, line_src, current, t, source)
            if _is_trend_result(t):
                current = None
        else:
            general.append(t)
    return general, _sections_from_map(by_line, line_src)


def _trim_event_lead_paras(title: str, flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉段首「（1）N号线典型故障：」和与标题重复的首句。"""
    title_c = compact_text(re.sub(r"(?:故障)?分析$", "", str(title or "")))
    out: list[dict[str, Any]] = []
    first_para = True
    for item in flow or []:
        if item.get("kind") != "para":
            out.append(item)
            continue
        t = str(item.get("text") or "").strip()
        if first_para:
            first_para = False
            t = _EVENT_LIST_LEAD.sub("", t)
            t = _EVENT_TYPICAL_LEAD.sub("", t)
            t = re.sub(r"^20\d{6}(?=\d{1,2}号线)", "", t)
            head, sep, rest = t.partition("。")
            if sep and title_c and compact_text(head) == title_c:
                t = rest.lstrip()
            if not t:
                continue
            item = dict(item)
            item["text"] = t
        out.append(item)
    return out


def _event_child(title: str, flow: list[dict[str, Any]], src: str, recency=None) -> dict[str, Any]:
    cleaned: list[dict[str, Any]] = []
    for item in flow or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "para":
            raw = _normalize_event_para(str(item.get("text") or ""))
            if not raw or raw in _EVENT_SKIP_HEADS or _event_noise(raw):
                continue
            item = dict(item)
            item["text"] = raw
        cleaned.append(item)
    flow = restart_list_numbers_flow(dedupe_flow_items(cleaned))
    title = _clean_event_title(title, flow)
    flow = _trim_event_lead_paras(title, flow)
    paras = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    out = {
        "title": title,
        "paras": paras,
        "empty": not flow,
        "source": src,
        "content_child": True,
        "fill": {
            "paras": paras,
            "flow": flow,
            "table": [],
            "sections": [],
            "source": src,
            "empty": not flow,
        },
    }
    if recency is not None:
        out["_recency"] = recency
    return out


def _iter_plain_and_row_texts(doc: DocumentModel):
    for block in doc.blocks or []:
        if block.type in {"paragraph", "heading"}:
            t = (block.text or "").strip()
            if t:
                yield t
            continue
        if block.type != "table":
            continue
        for row in block.rows or []:
            cells = [str(c or "").strip() for c in row]
            t = "".join(cells)
            if t:
                yield t


def is_km_junk_para(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    if _WRAP_CH.match(t) or t.startswith("第三章") or t.startswith("第四章"):
        return True
    return bool(_KM_JUNK_RE.search(t))


def is_km_change_para(text: str) -> bool:
    """4.1.1：某线接触网/接触轨条公里新增或减少，不是规程「新增附录」。"""
    t = str(text or "").strip()
    if not t or len(t) > 240 or is_km_junk_para(t):
        return False
    if "条公里" not in t or not _KM_ASSET_RE.search(t):
        return False
    if not _CHANGE_RE.search(t):
        return False
    return bool(_line_no_in(t) or _KM_RE.search(t))


def is_km_qty_para(text: str) -> bool:
    """4.2.1：各线现有条公里，不含二期新增句。"""
    t = str(text or "").strip()
    if not t or len(t) > 240 or is_km_junk_para(t):
        return False
    if "条公里" not in t or not _KM_RE.search(t):
        return False
    if is_km_change_para(t):
        return False
    return True


def harvest_kilometre_paras(docs: list[DocumentModel] | None, *, change_only: bool) -> dict[str, Any]:
    """设备数量=各线条公里（同线取较新）；体量变化=含新增/减少且带条公里的句子。"""
    by_line: dict[int, str] = {}
    src_line: dict[int, str] = {}
    general: list[str] = []
    general_src = ""
    for doc, _idx in sort_docs_newest_last(docs or []):
        src = doc.source_name or ""
        for t in _iter_plain_and_row_texts(doc):
            ok = is_km_change_para(t) if change_only else is_km_qty_para(t)
            if not ok:
                continue
            n = _line_no_in(t)
            if n:
                by_line[n] = t
                src_line[n] = src
            elif change_only:
                general = [t]
                general_src = src
    paras = [by_line[n] for n in sorted(by_line)]
    if change_only and not paras:
        paras = general
    sources = [src_line[n] for n in sorted(src_line) if src_line.get(n)]
    source = "、".join(dict.fromkeys(sources)) or general_src
    flow = [{"kind": "para", "text": p} for p in paras]
    return {
        "paras": paras,
        "flow": flow,
        "source": source,
        "empty": not paras,
    }


def is_ch4_trend_junk(text: str) -> bool:
    return _fault_trend_offtopic(text)


def is_fault_trend_para(text: str) -> bool:
    """4.3：期间总计、典型故障、趋势公式。两年对照句留给 4.4。"""
    t = str(text or "").strip()
    if not t or len(t) > 1200 or is_ch4_trend_junk(t):
        return False
    if is_peer_chapter_title(t):
        return False
    if "号线" not in t:
        return bool(_TREND_KEEP_RE.search(t) or _is_trend_continuation(t))
    if _FAULT_RE.search(t) or _TREND_KEEP_RE.search(t) or _is_trend_continuation(t):
        return True
    return False


def harvest_fault_trend_paras(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """4.3：每条线只取「期间/典型故障 → 设备故障趋势」这一段，趋势后不再加。"""
    from chapters.common.domain_filter import is_power_fault_situation_doc

    by_line: dict[int, list[str]] = {}
    line_src: dict[int, str] = {}
    for doc, _idx in sort_docs_newest_last(docs or []):
        if is_power_fault_situation_doc(doc):
            continue
        src = doc.source_name or ""
        texts = [
            (block.text or "").strip()
            for block in (doc.blocks or [])
            if block.type in {"paragraph", "heading"} and (block.text or "").strip()
        ]
        bag = _harvest_windows_from_texts(texts)
        for n, paras in bag.items():
            paras = clip_paras_after_trend(paras)
            if _trend_blob_score(paras) >= _trend_blob_score(by_line.get(n) or []):
                by_line[n] = paras
                line_src[n] = src
    paras: list[str] = []
    for n in sorted(by_line):
        paras.extend(by_line[n])
    source = "、".join(dict.fromkeys(line_src[n] for n in sorted(line_src) if line_src.get(n)))
    flow = [{"kind": "para", "text": p} for p in paras]
    mapped = {
        n: [{"kind": "para", "text": p} for p in items]
        for n, items in by_line.items()
    }
    return {
        "paras": paras,
        "flow": flow,
        "sections": _sections_from_map(mapped, line_src),
        "source": source,
        "empty": not paras,
    }


def scrub_fault_trend_sections(sections: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """线路小节里去掉第3章小结、两年对照句。"""
    out: list[dict[str, Any]] = []
    for sec in sections or []:
        fill = dict(sec.get("fill") or {})
        flow = []
        for item in fill.get("flow") or [{"kind": "para", "text": p} for p in (sec.get("paras") or [])]:
            if item.get("kind") == "para" and is_ch4_trend_junk(str(item.get("text") or "")):
                continue
            flow.append(item)
        flow = dedupe_flow_items(flow)
        paras = clip_paras_after_trend([x.get("text") or "" for x in flow if x.get("kind") == "para"])
        keep = {compact_text(p) for p in paras}
        flow = [
            x
            for x in flow
            if x.get("kind") != "para" or compact_text(str(x.get("text") or "")) in keep
        ]
        if not flow:
            continue
        fill["flow"] = flow
        fill["paras"] = paras
        fill["empty"] = False
        s = dict(sec)
        s["fill"] = fill
        s["paras"] = paras
        s["empty"] = False
        out.append(s)
    return out


def _section_paras(sec: dict[str, Any] | None) -> list[str]:
    if not sec:
        return []
    fill = sec.get("fill") or {}
    paras = [str(p) for p in (fill.get("paras") or sec.get("paras") or []) if str(p).strip()]
    if paras:
        return paras
    return [
        str(x.get("text") or "")
        for x in (fill.get("flow") or [])
        if x.get("kind") == "para" and str(x.get("text") or "").strip()
    ]


def _union_line_section(primary: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return primary
    seen = {compact_text(p) for p in _section_paras(primary)}
    flow = list((primary.get("fill") or {}).get("flow") or [{"kind": "para", "text": p} for p in _section_paras(primary)])
    for item in (extra.get("fill") or {}).get("flow") or [{"kind": "para", "text": p} for p in _section_paras(extra)]:
        if item.get("kind") != "para":
            continue
        t = str(item.get("text") or "").strip()
        c = compact_text(t)
        if t and c not in seen:
            seen.add(c)
            flow.append({"kind": "para", "text": t})
    paras = clip_paras_after_trend([str(x.get("text") or "") for x in flow if x.get("kind") == "para"])
    keep = {compact_text(p) for p in paras}
    flow = [x for x in flow if x.get("kind") != "para" or compact_text(str(x.get("text") or "")) in keep]
    src = (primary.get("source") or "") or (extra.get("source") or "")
    out = dict(primary)
    out["paras"] = paras
    out["empty"] = False
    out["source"] = src
    out["fill"] = {
        "paras": paras,
        "flow": flow,
        "table": [],
        "sections": [],
        "source": src,
        "empty": False,
    }
    return out


def merge_line_sections(
    preferred: list[dict[str, Any]] | None,
    fallback: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """同线路两袋合并：分高的那袋保留原文顺序，缺的句子补在后面。"""
    by: dict[str, dict[str, Any]] = {}
    for sec in fallback or []:
        key = compact_text(str(sec.get("title") or ""))
        if key:
            by[key] = sec
    for sec in preferred or []:
        key = compact_text(str(sec.get("title") or ""))
        if not key or sec.get("empty"):
            continue
        old = by.get(key)
        if old:
            if _trend_blob_score(_section_paras(old)) >= _trend_blob_score(_section_paras(sec)):
                sec = _union_line_section(old, sec)
            else:
                sec = _union_line_section(sec, old)
        by[key] = sec
    return sorted(by.values(), key=lambda s: (_line_no_in(str(s.get("title") or "")) or 99, str(s.get("title") or "")))


def harvest_regulation_revisions(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """6.1 整改：只收「修正规程」导语和《…》修订内容原文，不把整章修程修制灌进来。"""
    sections: list[dict[str, Any]] = []
    intro: list[dict[str, Any]] = []
    intro_src = ""
    for doc, _idx in sort_docs_newest_last(docs or []):
        src = doc.source_name or ""
        current = ""
        flow: list[dict[str, Any]] = []
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            if not t:
                continue
            if current and (
                is_peer_chapter_title(t)
                or t.startswith("评估小结")
                or t.startswith("企业标准")
                or t.startswith("日常维修")
            ):
                sections.append(_event_child(current, flow[:30], src))
                current, flow = "", []
            if re.search(r"修正.{0,16}规程", t) and len(t) < 80:
                if len(intro) < 6:
                    intro.append({"kind": "para", "text": t})
                    intro_src = src
                continue
            if "修订内容" in t and "《" in t and len(t) < 100:
                if current and flow:
                    sections.append(_event_child(current, flow[:30], src))
                current, flow = t, []
                continue
            if not current:
                continue
            item = _block_item(doc, block)
            if item:
                flow.append(item)
                if len(flow) >= 30:
                    sections.append(_event_child(current, flow, src))
                    current, flow = "", []
        if current and flow:
            sections.append(_event_child(current, flow[:30], src))
    by_title: dict[str, dict[str, Any]] = {}
    for s in sections:
        by_title[compact_text(s.get("title") or "")] = s
    out_sec = [s for s in by_title.values() if not s.get("empty")]
    return {
        "intro": dedupe_flow_items(intro),
        "sections": out_sec,
        "source": intro_src or "、".join(s.get("source") or "" for s in out_sec if s.get("source")),
        "empty": not intro and not out_sec,
    }


_RETIRE_KEEP = re.compile(r"接触网|触网|接触轨|隔离开关|接触线|汇流排|锚段")
_RETIRE_SKIP = re.compile(r"中央信号屏|蓄电池|变压器|整流|万用表|工器具报废|仪器仪表|工具器械")


def harvest_overhead_retire(docs: list[DocumentModel] | None, year: int) -> dict[str, Any]:
    """11.1：触网报废原文。部门稿写「不写」或纯变电报废不收，也不编造。"""
    by_line: dict[int, list[dict[str, Any]]] = {}
    line_src: dict[int, str] = {}
    intro: list[dict[str, Any]] = []
    claimed: set[int] = set()
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        src = doc.source_name or ""
        writing: set[int] = set()
        head = " ".join((b.text or "") for b in (doc.blocks or [])[:8])
        if "不写" in head and "退运" in head:
            continue
        texts = [
            (b.text or "").strip()
            for b in (doc.blocks or [])
            if b.type in {"paragraph", "heading"} and (b.text or "").strip()
        ]
        i = 0
        while i < len(texts):
            t = texts[i]
            if len(t) < 12 or len(t) > 2500 or "不写" in t:
                i += 1
                continue
            if "号线" not in t or not any(k in t for k in ("报废", "退运更换", "退运")):
                i += 1
                continue
            if "工器具" in src or "仪器仪表" in src:
                i += 1
                continue
            if "除湿机" in t or "空气除湿" in t:
                i += 1
                continue
            if _RETIRE_SKIP.search(t) or not _RETIRE_KEEP.search(t):
                i += 1
                continue
            n = _line_no_in(t)
            if not n:
                i += 1
                continue
            _append_line_para(by_line, line_src, n, t, src, claimed=claimed, writing=writing)
            j = i + 1
            grabbed = 0
            while j < len(texts) and grabbed < 5:
                nxt = texts[j]
                if "综上所述" in nxt or nxt.startswith("上海地铁"):
                    break
                nxt_n = _line_no_in(nxt)
                if nxt_n and nxt_n != n and any(k in nxt for k in ("报废", "退运")):
                    break
                if "除湿机" in nxt or "空气除湿" in nxt:
                    j += 1
                    continue
                if any(
                    k in nxt
                    for k in (
                        "隔离开关",
                        "机构箱",
                        "接触网设备主要特征",
                        "报废原因",
                        "锈蚀",
                        "烧蚀",
                        "设计使用年限",
                    )
                ):
                    _append_line_para(by_line, line_src, n, nxt, src, claimed=claimed, writing=writing)
                    grabbed += 1
                    j += 1
                    continue
                break
            i = j if grabbed else i + 1
        claimed.update(writing)
    sections = _sections_from_map(by_line, line_src)
    return {
        "intro": intro,
        "sections": sections,
        "source": "、".join(s for s in dict.fromkeys(line_src.values()) if s),
        "empty": not sections,
    }


def harvest_overhead_tools(docs: list[DocumentModel] | None) -> dict[str, Any]:
    """11.2：工器具配置原文。检测/除冰/异物工器具不收。"""
    for doc, _idx in reversed(list(sort_docs_newest_last(docs or []))):
        src = doc.source_name or ""
        for block in doc.blocks or []:
            if block.type not in {"paragraph", "heading"}:
                continue
            t = (block.text or "").strip()
            if not t or "工器具" not in t:
                continue
            if any(k in t for k in ("检测工器具", "专用工器具", "除冰工器具", "异物")):
                continue
            if any(k in t for k in ("暂无缺少", "配置情况", "不存在缺", "工器具配置")):
                return {
                    "paras": [t],
                    "flow": [{"kind": "para", "text": t}],
                    "source": src,
                    "empty": False,
                }
    return {"paras": [], "flow": [], "source": "", "empty": True}
