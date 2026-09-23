# -*- coding: utf-8 -*-
"""第3章设备评级（A/B/C/D）与第11章退运报废清单的跨章矛盾核对。

业务口径（2026-09 与需求方确认）：
- 认 A、B 或 C：同一线路、同一设备中类，在第3章评级表任一区段评过 A、B 或 C，
  第11章又写明同线路报废该中类设备，记为严重逻辑矛盾（severe）；
  仅评 D（差，60 分以下）时不报。
- 评级表未覆盖的设备类别（如生产辅助类的空调、起重机），忽略不报。
- 小类→中类映射：优先用报告自带的「中类→包含小类设备」表，
  再叠加本模块显式映射；LLM 门控开启时，对仍未覆盖的设备名做一次
  归类兜底（只能从评级表实际列名中选，选不上即忽略）。

模块只读，不生成报告、不改写原文。供电与触网报告通用。
"""
from __future__ import annotations

import re
from typing import Any

_GRADE_CH = 3
_SCRAP_CH = 11
_GRADE_MARKS = {"A", "B", "C", "D"}

# 中类（报告映射表用词）→ 评级表列名。
# 生产辅助系统、接触网系统等在评级表中没有评级列，不出现在此表中（即忽略）。
_MID_TO_COL = {
    "应急电源系统": "应急电源设备",
    "应急电源": "应急电源设备",
    "杂散系统": "杂散电流设备",
    "配电系统（降压）": "配电系统（降压）",
    "配电系统（牵引）": "配电系统（牵引）",
    "变压系统": "变压器设备",
    "电力监控系统": "电力监控设备",
    "电力电缆": "电力电缆设备",
    "能耗设备": "能耗设备",
    "配电设备": "配电设备",
}

# 显式小类→中类：报告映射表未列、但口径明确的报废设备名。
_SMALL_TO_MID = {
    "中央信号屏": "电力监控系统",
    "信号屏": "电力监控系统",
    "监控屏": "电力监控系统",
    "复视系统": "电力监控系统",
    "复示系统": "电力监控系统",
    "交换机柜": "电力监控系统",
    "服务器": "电力监控系统",
    "公共单元测控屏": "电力监控系统",
    "工控机屏": "电力监控系统",
    "前置机屏": "电力监控系统",
    "综合自动化屏": "电力监控系统",
    "变压器保护屏": "电力监控系统",
    "线路保护屏": "电力监控系统",
    "接地变保护屏": "电力监控系统",
    "主变调压屏": "电力监控系统",
    "蓄电池屏": "应急电源系统",
    "事故照明屏": "应急电源系统",
    "动力变压器": "变压系统",
    "电力变压器": "变压系统",
    "整流变压器": "变压系统",
    "站用变压器": "变压系统",
    "主变": "变压系统",
    "高压开关": "配电系统（牵引）",
    "馈线屏": "配电系统（牵引）",
    "中压开关柜": "配电系统（降压）",
    "低压开关柜": "配电系统（降压）",
    "配电柜": "配电设备",
}

_GENERIC_NAMES = {"供电系统设备", "设备", "系统设备", "各类设备", "其它设备", "其他设备"}
_SMALL_SPLIT_RE = re.compile(r"[，,、；;/\s]+")
_LINE_CELL_RE = re.compile(r"(\d{1,2})\s*号线")
_LINE_BARE_RE = re.compile(r"^(\d{1,2})$")
_LINE_HEAD_RE = re.compile(r"轨道交通\s*(\d{1,2})\s*号线")
_QTY_DEVICE_RE = re.compile(
    r"(\d+)\s*台\s*([一-龥A-Za-z0-9#][一-龥A-Za-z0-9（）()·#]{1,16}?)"
    r"(?=\s*[，、,；。]|需报废|\d+\s*台|原值|安装|于\s*\d|$)"
)

# 非设备类列名：定位列、时间列、综合状态列等。
_NON_DEVICE_HEADERS = (
    "线路", "区段", "区间", "时间", "年份", "年度", "系统状态值", "状态值",
    "系统状态等级", "状态等级", "综合得分", "综合", "序号", "备注", "说明",
    "大类", "中类", "小类", "项目",
)


def _is_non_device_header(name: str) -> bool:
    t = str(name).strip()
    return any(k in t for k in _NON_DEVICE_HEADERS)


def _grade_from_cell(cell: Any) -> str:
    """单元格→等级：A/B/C/D 字母直接用；0~100 的分数按团标区间换算（A≥90，B≥75，C≥60，D<60）。"""
    s = str(cell).strip().upper()
    if s in _GRADE_MARKS:
        return s
    m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)(?:分)?", s)
    if not m:
        return ""
    v = float(m.group(1))
    if not 0 <= v <= 100:
        return ""
    if v >= 90:
        return "A"
    if v >= 75:
        return "B"
    if v >= 60:
        return "C"
    return "D"


def _norm_col(name: str) -> str:
    """列名归一化：全角括号转半角、去空白。"""
    return re.sub(r"\s+", "", str(name)).replace("（", "(").replace("）", ")")


def _extract_device_mapping(units: list[dict[str, Any]]) -> dict[str, str]:
    """从报告自带的「大类/中类名称/包含小类设备」表提取小类→中类映射。"""
    small_to_mid = dict(_SMALL_TO_MID)
    for u in units:
        if u.get("kind") != "table":
            continue
        rows = u.get("rows") or []
        if not rows:
            continue
        head = [str(c).strip() for c in rows[0]]
        joined = "".join(head)
        if "中类" not in joined or "小类" not in joined:
            continue
        i_mid = next((i for i, h in enumerate(head) if "中类" in h), None)
        i_small = next((i for i, h in enumerate(head) if "小类" in h), None)
        if i_mid is None or i_small is None:
            continue
        for r in rows[1:]:
            if max(i_mid, i_small) >= len(r):
                continue
            mid = str(r[i_mid]).strip()
            if not mid:
                continue
            for token in _SMALL_SPLIT_RE.split(str(r[i_small])):
                name = token.strip(" （）()·")
                if len(name) >= 2:
                    small_to_mid.setdefault(name, mid)
    return small_to_mid


def _grade_table(rows: list[list[Any]] | None) -> tuple[list[str], int] | None:
    """识别评级表：表头含「线路」且表内至少 6 个评级（字母 A~D 或 0~100 分数）。返回 (表头, 线路列下标)。"""
    if not rows or len(rows) < 3:
        return None
    head = [str(c).strip() for c in rows[0]]
    line_cols = [i for i, h in enumerate(head) if "线路" in h]
    if not line_cols:
        return None
    marks = 0
    for r in rows[1:]:
        for c in r:
            s = str(c).strip().upper()
            if s in _GRADE_MARKS or re.fullmatch(r"\d{1,3}(?:\.\d+)?", s):
                marks += 1
    if marks < 6:
        return None
    return head, line_cols[0]


def _extract_grades(
    rows: list[list[Any]],
    head: list[str],
    line_i: int,
    assessment_year: int | None = None,
) -> dict:
    """评级表 → {(线路, 归一化列名): [(区段, 评级), ...]}。

    - 线路列支持「N号线」或纯数字（合并单元格向下填充）；
    - 「时间/年份」列存在时，只保留评估年（2026 年）的对比行；
    - 评级单元格支持 A~D 字母或 0~100 分数（按团标区间换算）；
    - 综合状态列、时间列、定位列等非设备列不参与。
    """
    out: dict[tuple[int, str], list[tuple[str, str]]] = {}
    section_i = next((i for i, h in enumerate(head) if "区段" in h or "区间" in h), None)
    year_i = next((i for i, h in enumerate(head) if "时间" in h or "年份" in h or "年度" in h), None)
    cur_line: int | None = None
    for r in rows[1:]:
        if line_i < len(r):
            cell = str(r[line_i]).strip()
            m = _LINE_CELL_RE.search(cell) or _LINE_BARE_RE.match(cell)
            if m:
                cur_line = int(m.group(1))
        if cur_line is None:
            continue
        # 有年份对比列时，只取评估年的行
        if year_i is not None and assessment_year is not None and year_i < len(r):
            y = re.sub(r"\D", "", str(r[year_i]))
            if y and not y.startswith(str(assessment_year)):
                continue
        section = ""
        if section_i is not None and section_i < len(r):
            section = str(r[section_i]).strip()
        for ci, col in enumerate(head):
            col = str(col).strip()
            if ci == line_i or ci == section_i or ci == year_i or not col:
                continue
            if _is_non_device_header(col):
                continue
            v = _grade_from_cell(r[ci]) if ci < len(r) else ""
            if v:
                out.setdefault((cur_line, _norm_col(col)), []).append((section, v))
    return out


def _clean_device_name(raw: str) -> str:
    """清洗正则抽到的设备名：去尾随后缀与「需报废」残留。"""
    return re.sub(r"需报废$", "", raw).strip(" （）()，,、；。于：:")


def _extract_scrap(units: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """第11章报废清单 → {线路: [{device, qty, sentence}]}。

    - 按句号（不按分号）切分大句：含「需报废」的大句，其分号子句属于
      同一批设备的数量明细，一并抽取（如「…需报废…1台A；2台B；…」）；
    - 「需报废」前的总述项（如「2台变压器」）若被其后分述的具体设备
      （「1台动力变压器、1台整流变压器」）同类等量覆盖，丢弃总述，避免重复计数；
    - 线路优先取句中的「N号线」（触网报告无「轨道交通N号线」小标题），
      其次取「轨道交通N号线」小节标题；
    - 「评估小结」「总结」及其后的复述段落一律跳过。
    """
    out: dict[int, list[dict[str, Any]]] = {}
    cur: int | None = None
    in_summary = False

    def _emit(line: int, m: re.Match, sentence: str) -> None:
        qty = int(m.group(1))
        name = _clean_device_name(m.group(2))
        if qty <= 0 or len(name) < 2 or name in _GENERIC_NAMES:
            return
        if not re.search(r"[一-龥]", name):
            return
        out.setdefault(line, []).append(
            {"device": name, "qty": qty, "sentence": sentence.strip()}
        )

    for u in units:
        if u.get("kind") == "heading":
            t = (u.get("text") or "").strip()
            in_summary = ("小结" in t) or ("总结" in t)
            m = _LINE_HEAD_RE.match(t)
            if m:
                cur = int(m.group(1))
            continue
        if u.get("kind") != "paragraph" or in_summary:
            continue
        t = (u.get("text") or "").strip()
        for big in re.split(r"[。\n]", t):
            if "需报废" not in big:
                continue
            lm = re.search(r"(\d{1,2})\s*号线", big)
            line = int(lm.group(1)) if lm else cur
            if line is None:
                continue
            pos = big.index("需报废")
            before = list(_QTY_DEVICE_RE.finditer(big[:pos]))
            after = list(_QTY_DEVICE_RE.finditer(big[pos:]))
            covered: set[int] = set()
            if after:
                after_names = [_clean_device_name(m.group(2)) for m in after]
                for i, mb in enumerate(before):
                    nb = _clean_device_name(mb.group(2))
                    same = [
                        ma for ma, na in zip(after, after_names)
                        if nb and na and nb in na
                    ]
                    if same and sum(int(ma.group(1)) for ma in same) >= int(mb.group(1)):
                        covered.add(i)
            for i, m in enumerate(before):
                if i not in covered:
                    _emit(line, m, big)
            for m in after:
                _emit(line, m, big)
    return out


def _map_device(name: str, small_to_mid: dict[str, str], llm_extra: dict[str, str]) -> str:
    """小类设备名 → 中类；找不到返回空串。

    只做「已知小类名出现在报废设备名中」的包含匹配（如「中央信号屏」∈「1#中央信号屏」），
    不反向匹配（短名「变压器」不得命中「变压器保护屏」），避免误归类。
    """
    if name in small_to_mid:
        return small_to_mid[name]
    for key in sorted(small_to_mid, key=len, reverse=True):
        if len(key) >= 2 and key in name:
            return small_to_mid[key]
    return llm_extra.get(name, "")


def _match_col_by_name(name: str, grade_cols: set[str] | list[str]) -> str:
    """报废设备名直接匹配评级列名（触网报告中类名与评级列同名，如「隔离开关」）。

    完全相等优先，其次互相包含（取最长列名），防止短名误中长列名。
    """
    n = _norm_col(name)
    best = ""
    for c in grade_cols:
        cn = _norm_col(c)
        if cn == n:
            return cn
        if len(cn) >= 2 and (cn in n or (len(n) >= 2 and n in cn)):
            if len(cn) > len(best):
                best = cn
    return best


def _llm_map_unknown(names: list[str], grade_cols: list[str]) -> dict[str, str]:
    """LLM 兜底：把未覆盖的设备名归入评级表实际列名之一；归不上返回「无法对应」。"""
    if not names:
        return {}
    try:
        from chapters.common.logic_llm import logic_llm_enabled

        if not logic_llm_enabled():
            return {}
        from engine.llm_client import chat_json
    except Exception:
        return {}
    cols = "、".join(grade_cols)
    sys = (
        "你是上海轨道交通供电设备台账分类员。把报废设备小类名称归入给定的设备中类。"
        f"只能从这些中类中选择：{cols}。无法明确对应时输出「无法对应」。"
        '只返回 JSON：{"mapping":{"设备名":"中类名或无法对应"}}，不要输出其他内容。'
    )
    user = "待分类设备：\n" + "、".join(names)
    try:
        data = chat_json(sys, user, temperature=0)
        raw = (data or {}).get("mapping") or {}
    except Exception:
        return {}
    allowed = {_norm_col(c) for c in grade_cols}
    out: dict[str, str] = {}
    items = raw.items() if isinstance(raw, dict) else []
    for name, col in items:
        col = str(col).strip()
        if col and col != "无法对应" and _norm_col(col) in allowed:
            out[str(name).strip()] = col
    return out


def grade_scrap_findings(
    units: list[dict[str, Any]], assessment_year: int | None = None
) -> list[dict[str, str]]:
    """跨章核对入口。findings 为 severe 条目，结构同 logic_page_check。"""
    ch3 = [u for u in units if u.get("chapter_no") == _GRADE_CH]
    ch11 = [u for u in units if u.get("chapter_no") == _SCRAP_CH]
    if not ch3 or not ch11:
        return []

    small_to_mid = _extract_device_mapping(ch3)

    grades: dict[tuple[int, str], list[tuple[str, str]]] = {}
    grade_cols: set[str] = set()
    for u in ch3:
        rows = u.get("rows")
        found = _grade_table(rows)
        if not found:
            continue
        head, line_i = found
        for (line, col), cells in _extract_grades(rows, head, line_i, assessment_year).items():
            grade_cols.add(col)
            grades.setdefault((line, col), []).extend(cells)
    if not grades:
        return []

    scrap = _extract_scrap(ch11)
    if not scrap:
        return []

    # 先收集规则未覆盖的设备名，再用一次 LLM 兜底归类。
    unknown: set[str] = set()
    mapped_preview: dict[tuple[int, str], dict[str, int]] = {}
    sentences: dict[tuple[int, str], str] = {}

    def _bucket(line: int, col_key: str, item: dict[str, Any]) -> None:
        devs = mapped_preview.setdefault((line, col_key), {})
        devs[item["device"]] = devs.get(item["device"], 0) + item["qty"]
        cur_sent = sentences.get((line, col_key), "")
        if len(item["sentence"]) > len(cur_sent):
            sentences[(line, col_key)] = item["sentence"]

    for line, items in scrap.items():
        for item in items:
            mid = _map_device(item["device"], small_to_mid, {})
            col = _MID_TO_COL.get(mid) or _match_col_by_name(item["device"], grade_cols)
            if not col:
                unknown.add(item["device"])
                continue
            _bucket(line, _norm_col(col), item)

    # LLM 兜底结果归一化为评级列名。
    if unknown:
        col_list = sorted(grade_cols)
        for name, col in _llm_map_unknown(sorted(unknown), col_list).items():
            for line, items in scrap.items():
                for item in items:
                    if item["device"] != name:
                        continue
                    _bucket(line, _norm_col(col), item)

    out: list[dict[str, str]] = []
    seen: set[tuple[int, str]] = set()

    def _grade_phrase(sections: set[str], grade: str) -> str:
        """生成「在X、Y区段评级为A（状态优，90~100分）」措辞；无区段名时省略区段。"""
        band = {
            "A": "状态优，90~100分",
            "B": "状态良，75~90分",
            "C": "状态中，60~75分",
        }[grade]
        named = sorted(s for s in sections if s)
        if named:
            return f"在{'、'.join(named)}区段评级为{grade}（{band}）"
        return f"评级为{grade}（{band}）"

    for (line, col), devs in sorted(mapped_preview.items()):
        cells = grades.get((line, col))
        if not cells:
            continue
        # 同一区段在多张评级表（如供电子系统表、主变电系统表）中评级可能不同，
        # 取最高评级（A>B>C>D），避免同一区段在文案中同时出现 A 与 B。
        best: dict[str, str] = {}
        rank = {"A": 0, "B": 1, "C": 2, "D": 3}
        for sec, g in cells:
            if g not in rank:
                continue
            if sec not in best or rank[g] < rank[best[sec]]:
                best[sec] = g
        a_sections = {s for s, g in best.items() if g == "A"}
        b_sections = {s for s, g in best.items() if g == "B"}
        c_sections = {s for s, g in best.items() if g == "C"}
        if not a_sections and not b_sections and not c_sections:
            continue
        key = (line, col)
        if key in seen:
            continue
        seen.add(key)
        total = sum(devs.values())
        dev_text = "、".join(f"{name}{qty}台" for name, qty in sorted(devs.items()))
        grade_text = "、".join(
            p for p in (
                _grade_phrase(a_sections, "A") if a_sections else "",
                _grade_phrase(b_sections, "B") if b_sections else "",
                _grade_phrase(c_sections, "C") if c_sections else "",
            ) if p
        )
        out.append(
            {
                "kind": "severe",
                "issue": "逻辑错误",
                "section": f"第3章 / 第11章 轨道交通{line}号线",
                "note": (
                    f"第3章评级表中，{line}号线{col}{grade_text}，"
                    f"第11章却写明{line}号线需报废{dev_text}（共{total}台，属{col}），"
                    f"评级与报废结论矛盾。"
                ),
                "excerpt": sentences.get(key, "").replace("\n", " ")[:220],
            }
        )
    return out
