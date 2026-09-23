# -*- coding: utf-8 -*-
"""规则抽完后的 keep/drop。模型不写正文、不改数字、不补小结。

有 DEEPSEEK_API_KEY 时启用；后期本地模型只需改 .env 的 BASE_URL / MODEL
（OpenAI 兼容接口）。测试设 OVERHEAD_LLM_GATE=0，避免打到真实接口。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterable

_FLAG: ContextVar[bool | None] = ContextVar("overhead_llm_gate", default=None)

KINDS: dict[str, str] = {
    "event": (
        "是否属于接触网/接触轨年度突出事件、典型故障或故障分析原文。"
        "磨耗预警、条公里、评估规范条款、第X章复盘、风险概述、状态分布、管控措施不是。"
    ),
    "intro": (
        "是否属于当前小节导语。评估规范撰写说明、其他章节正文、变电专段不是。"
    ),
    "env": (
        "是否描述该线路接触网/接触轨使用环境（漏水、粉尘、侵限、户外段、潮湿隧道等）。"
        "设备状态分布、集中修/差异化管控、变电站房间潮湿不是。"
    ),
    "instrument": "是否描述接触网运维仪器仪表配置。变电站仪表、纯生产计划、纯培训不是。",
    "training": "是否描述年度培训。检测小车/智能化、生产计划完成率、风险章节不是。",
    "intel": "是否描述接触网智能化、检测小车或验电器。纯生产计划、纯培训名单不是。",
    "control": (
        "是否属于该线路第3.4节各线路管控措施原文：集中修、大修更新、专项更换/整治、"
        "差异化跟踪、风险点及后续管控、备品平替、在执行项目。"
        "第3.3节是接触网设备状态分布（3.3.1接触网柔/刚、3.3.2接触轨、3.3.3隔离开关、"
        "3.3.4隔离开关控制屏），C/D状态区段或区间在哪、设备状态/接触网状态标题下的名单不是3.4。"
        "状态评级只是铺垫、后面马上写跟踪预警或管控动作的要留（如12号线状态是B后接分险点跟踪、"
        "15号线B类跟踪管控）。没把握则 keep=true。"
    ),
    "status": (
        "是否属于第3.3节状态分布表后说明：该设备类型C/D状态区段或区间在哪、没有C和D、"
        "接触网/接触轨/隔离开关/控制屏评级。"
        "第3.4节管控措施专节（管控策略包括、集中修项目、大修更新、专项更换、备品备件编号清单）不是。"
        "跟在C状态后面的「差异化管控是」表后短句要留。没把握则 keep=true。"
    ),
    "fault_trend": (
        "是否属于该线路第4.3节接触网故障趋势分析原文：评估期间总计发生、典型故障、重大故障、"
        "当年设备故障值、前三年均值、故障趋势公式或百分比。"
        "第3章小结、评估围绕设备体量、和环境因素、管控措施、磨耗预警规定、两年对照句（留给4.4）不是。"
        "没把握则 keep=true。"
    ),
}


def llm_enabled() -> bool:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return True
    try:
        from engine.config import get_deepseek_config

        return bool((get_deepseek_config().get("api_key") or "").strip())
    except Exception:
        return False


def gate_on() -> bool:
    if str(os.getenv("OVERHEAD_LLM_GATE") or "").strip().lower() in {"0", "false", "no"}:
        return False
    flag = _FLAG.get()
    if flag is False:
        return False
    if flag is True:
        return llm_enabled()
    return llm_enabled()


@contextmanager
def using_llm(flag: bool | None):
    token = _FLAG.set(flag)
    try:
        yield
    finally:
        _FLAG.reset(token)


def keep_mask(texts: list[str], *, kind: str, context: str = "") -> list[bool]:
    """对候选原文做保留判定。失败或未启用时全部保留（规则结果为准）。"""
    items = [str(t or "").strip() for t in texts]
    if not items:
        return []
    if not gate_on():
        return [True] * len(items)
    rubric = KINDS.get(kind) or KINDS["intro"]
    keep = [True] * len(items)
    for start in range(0, len(items), 36):
        chunk = items[start : start + 36]
        decided = _ask_keep(chunk, rubric=rubric, context=context)
        if decided is None:
            continue
        for i, ok in enumerate(decided):
            if start + i < len(keep):
                keep[start + i] = bool(ok)
    return keep


def filter_texts(texts: list[str], *, kind: str, context: str = "") -> list[str]:
    mask = keep_mask(texts, kind=kind, context=context)
    return [t for t, ok in zip(texts, mask) if ok]


def filter_flow(flow: list[dict[str, Any]], *, kind: str, context: str = "") -> list[dict[str, Any]]:
    paras = [str(x.get("text") or "") for x in flow if x.get("kind") == "para"]
    if not paras:
        return flow
    kept = set(filter_texts(paras, kind=kind, context=context))
    out = []
    for x in flow:
        if x.get("kind") == "para" and str(x.get("text") or "") not in kept:
            continue
        out.append(x)
    return out


def filter_event_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not sections or not gate_on():
        return sections
    texts = []
    for s in sections:
        lead = str((s.get("paras") or [""])[0] or "")
        texts.append(f"{s.get('title') or ''}。{lead}"[:400])
    mask = keep_mask(texts, kind="event", context="第8章设施设备年度突出事件分析")
    return [s for s, ok in zip(sections, mask) if ok]


def filter_topic_hit(hit: dict[str, Any], *, kind: str, context: str = "") -> dict[str, Any]:
    if not hit or not gate_on():
        return hit
    intro = filter_flow(list(hit.get("intro") or []), kind="intro", context=context)
    sections = []
    for s in hit.get("sections") or []:
        fill = dict(s.get("fill") or {})
        flow = filter_flow(list(fill.get("flow") or []), kind=kind, context=context)
        paras = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
        if not flow:
            continue
        fill["flow"] = flow
        fill["paras"] = paras
        fill["empty"] = False
        s = dict(s)
        s["fill"] = fill
        s["paras"] = paras
        s["empty"] = False
        sections.append(s)
    return {
        **hit,
        "intro": intro,
        "sections": sections,
        "empty": not intro and not sections,
    }


def _ask_keep(texts: list[str], *, rubric: str, context: str) -> list[bool] | None:
    lines = []
    for i, t in enumerate(texts):
        one = " ".join(str(t).split())[:280]
        lines.append(f"[{i}] {one}")
    user = (
        f"当前小节：{context or '未标注'}\n"
        f"判定标准：{rubric}\n"
        "下面是规则已经抽到的原文片段。只判断该不该留在这一节。"
        "禁止改写、禁止补充原文没有的数字或句子。没把握则 keep=true。\n"
        '只返回 JSON：{"keep":[true,false,...]}，数组长度必须与片段数相同。\n\n'
        + "\n".join(lines)
    )
    try:
        from engine.llm_client import chat_json

        data = chat_json(
            "你是接触网年报材料分拣员。只做 keep/drop，不写正文。",
            user,
            temperature=0,
        )
    except Exception:
        return None
    raw = data.get("keep") if isinstance(data, dict) else None
    if not isinstance(raw, list) or len(raw) != len(texts):
        return None
    return [bool(x) for x in raw]


def topic_kind_from_hints(hints: Iterable[str]) -> str:
    blob = " ".join(str(h) for h in hints)
    if "仪器" in blob:
        return "instrument"
    if "培训" in blob:
        return "training"
    if "智能化" in blob or "检测小车" in blob:
        return "intel"
    if "环境" in blob:
        return "env"
    if any(k in blob for k in ("故障次数", "典型故障", "故障趋势", "自检自修", "起设备故障")):
        return "fault_trend"
    return "intro"
