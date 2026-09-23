# -*- coding: utf-8 -*-
"""逻辑性检测页：只返回条目，不生成报告，不走各章抽取。

供电 / 触网共用：错别字、标点、语言不通顺、段内总数、年份（截至/截止到早于评估年）。
完整报告额外核对第3章到第11章，并把「第3章评为 A 级、第11章写成报废」标成严重逻辑错误。
章节模式只查所选章，即使上传的是完整报告。
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from chapters.common.word import (
    is_incomplete,
    is_punct_issue,
    is_section_title_line,
    language_note,
    punct_note,
)
from chapters.common.number_logic import number_logic_notes
from chapters.common.logic_llm import llm_review_units as _llm_review_units
from chapters.common.grade_scrap_check import grade_scrap_findings as _grade_scrap_findings
from parsers.dispatch import parse_file

_UNITS = "种|类|项|台|套|个|起|座|条|处|架|根|副|面"
_TOTAL_KIND = re.compile(
    rf"(?:共有|总共|合计|共计|一共|总计|共)\s*(\d+)\s*({_UNITS})"
)
_AS_OF = re.compile(r"(?:截至|截止到|截止至|截止)\s*(\d{4})(?:\s*年)?")
# 完工/进度语境：其后「截止YYYY年M月D日完成…」是项目完工日期，属评估周期内的正常时点，不报年份偏早
_COMPLETION_CTX = re.compile(r"完成进度|完工|完成|交付|投产|竣工|已全部")
_LINE = re.compile(r"(\d{1,2})\s*号线")
_A_VERB = re.compile(
    r"(?:评为|评估为|评级为|状态为|属于|定为|评价为)\s*[AＡa]\s*[类级]"
)
_A_NEG = re.compile(r"(?:没有|无|未发现|不存在|未见|不是|非)\s*[AＡa]\s*[类级]")
_A_MARK = re.compile(r"[AＡa]\s*[类级]")
_CHAPTER_HEAD = re.compile(r"^第\s*(\d{1,2})\s*章")
_BARE_CHAPTER = re.compile(r"^(\d{1,2})\s+\S")
# 章名末尾的状态备注，如（待更新）、（设备体量，章节内结构调整待更新）。
# 支持中英文/六角/花括号，允许嵌套（如「（设备体量（含3.2节），待更新）」），可连续多组。
_NOTE_BRACKETS = {"（": "）", "(": ")", "【": "】", "[": "]", "〔": "〕", "｛": "｝", "{": "}"}
_NOTE_MAX_LEN = 120

_SCAN_FROM = 3
_SCAN_TO = 11

# 报告正文的章标题在 Word 里常是自动编号（解析后只剩章名，无「第N章」），
# 用各章名称的核心词兜底识别（供电/触网章名一致）。
_CHAPTER_NAME_CORE = {
    3: "设备功能有效性",
    4: "运营契合",
    5: "管理体系合规",
    6: "修程修制",
    7: "运维表现健康",
    8: "风险隐患闭环",
    9: "备件物资保障",
    10: "使用环境符合",
    11: "退运报废倾向",
}

# 长词在前，避免「牵引变压器」被拆成「变压器」。
POWER_DEVICES = (
    "牵引变压器",
    "配电变压器",
    "整流变压器",
    "继电保护装置",
    "直流开关柜",
    "交流开关柜",
    "变压器",
    "断路器",
    "开关柜",
    "继电保护",
    "整流器",
    "直流开关",
    "蓄电池",
    "隔离开关",
    "GIS",
)
OVERHEAD_DEVICES = (
    "分段绝缘器",
    "锚段关节",
    "膨胀接头",
    "中心锚结",
    "刚性悬挂",
    "柔性悬挂",
    "接触线",
    "汇流排",
    "接触轨",
    "承力索",
    "定位装置",
    "定位器",
    "隔离开关",
)

_SHARED_TYPOS = (
    ("松驰", "松弛"),
    ("做为", "作为"),
    ("既使", "即使"),
    ("必竟", "毕竟"),
    ("按装", "安装"),
    ("复盖", "覆盖"),
    ("帐号", "账号"),
    ("报费", "报废"),
    ("以经", "已经"),
    ("凑和", "凑合"),
)
_POWER_TYPOS = (("继电保护装制", "继电保护装置"), ("变电锁", "变电所"))
_OVERHEAD_TYPOS = (("驰度", "弛度"), ("接出网", "接触网"))

_KIND_ORDER = {"severe": 0, "logic": 1, "year": 2, "typo": 3, "language": 4, "punct": 5}


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())

# ── 逻辑检测页专用：非句子内容的标点豁免 ─────────────────────────────────
# 清单条目、图表数据/公式、表题图题、句末括号备注不是完整句，不应要求句末标点。
# 仅作用于逻辑检测页；报告生成共用的 is_punct_issue 规则不变。
_HARD_PUNCT = re.compile(r"；；|；。|。；")
# 培训/规程/修订清单条目
_LIST_DASH = re.compile(r"^[—\-]{1,2}")
_LIST_TRAIN = re.compile(r"^(?:\d{1,2}\s*[、.．]?\s*)?20\d{2}\.\d{1,2}\s*《")
_LIST_CIRCLED = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]")
_LIST_NUM_NOUN = re.compile(r"^\d{1,2}\s*[、.．]\s*[\u4e00-\u9fa5A-Za-z]{2,20}$")
_LIST_PAREN_NUM = re.compile(r"^[（(]\s*\d{1,2}\s*[）)]\s*[\u4e00-\u9fa5A-Za-z]{2,20}$")
_LIST_CN_FAULT = re.compile(r"^[一二三四五六七八九十百]+、.{0,40}故障分析$")
_LIST_GUICHENG = re.compile(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*)?\d{0,2}\s*[\u4e00-\u9fa5/、，A-Za-z]{2,28}(?:规程|制度|办法)$")
# 图表数据/公式
_CHART_TREND = re.compile(r"故障设备趋势\s*=|设备故障趋势\s*=")
_CHART_FORMULA = re.compile(r"^=\s*[\[\d（(]|\[\(当年设备故障值|前三年设备故障均值|当年设备故障值")
_CHART_GRADE = re.compile(r"子系统和设备状态是\s*[ABCD]\s*$")
_CHART_TIAOGONG = re.compile(r"条公里\s*$")
_CHART_PROGRESS = re.compile(r"完成进度\s*\d+\s*%")
_CHART_FREQ = re.compile(r"\d+\s*(?:[年月天]\s*/\s*次|次\s*/\s*[年月天])\s*[）)]?\s*$")
_TOOL_QTY = re.compile(r"[一二三四五六七八九十两\d]+\s*(?:个|台|把|套|只|块|根|件)")
# 表题/图题（「表格10-2」「图8-8」「3-10 …评估结果」）
_CAPTION_PREFIX = re.compile(r"^(?:表格|图|表)\s*\d")
_CAPTION_BARE = re.compile(r"^\d{1,2}\s*[-–]\s*\d{1,2}\s+\S")
# 完整句后的句末括号备注（如「…。（电力监控设备处于D）」）
_TRAIL_PAREN = re.compile(r"[。！？；;]\s*（[^（）]{0,120}）\s*$")
_BARE_PAREN_NOTE = re.compile(r"^（[^（）]{2,60}）$")
# 以左括号开头、未见右括号的备注片段（LLM 截取不完整，标点检查无意义）
_PAREN_OPEN_NOTE = re.compile(r"^（[^（）]{2,120}$")

# 标准/规程编号（CJJ/T 288、DG/TJ_08、GB/T 1234 等），其引用内容格式保留原文
_STD_REF = re.compile(r"[A-Z]{2,4}/[A-Z]{1,3}[\s_]*\d")
# 「…如图X所示：/如下：/如下图：」引出图表或列举
_LEAD_FIGURE = re.compile(r"(?:所示|如下|如下图|见图|如图)：$")


def _logic_non_sentence(text: str) -> bool:
    """逻辑检测页：该行是否属于清单/图表数据/表题/括号备注等非句子（不要求句末标点）。"""
    t = (text or "").strip()
    if not t:
        return True
    if _TRAIL_PAREN.search(t) or _BARE_PAREN_NOTE.match(t) or _PAREN_OPEN_NOTE.match(t):
        return True
    if _LIST_DASH.match(t) or _LIST_TRAIN.match(t):
        return True
    if _LIST_CIRCLED.match(t) and len(t) <= 40 and t[-1] not in "。！？；":
        return True
    if _LIST_NUM_NOUN.match(t) or _LIST_PAREN_NUM.match(t) or _LIST_CN_FAULT.match(t) or _LIST_GUICHENG.match(t):
        return True
    if (
        _CHART_TREND.search(t)
        or _CHART_FORMULA.search(t)
        or _CHART_GRADE.search(t)
        or _CHART_TIAOGONG.search(t)
        or _CHART_PROGRESS.search(t)
        or _CHART_FREQ.search(t)
    ):
        return True
    if _CAPTION_PREFIX.match(t) or _CAPTION_BARE.match(t):
        return True
    # 工器具/数量罗列式数据行（≥3 组数字+量词，且无句末标点）
    if len(_TOOL_QTY.findall(t)) >= 3 and t[-1] not in "。！？；":
        return True
    # 完整句后被并入的「数字序号+短名词」小标题（如整段以「…。3、隔离开关」结尾）
    tail = re.split(r"[。！？；;]", t)[-1].strip()
    if tail and tail != t and _LIST_NUM_NOUN.match(tail):
        return True
    return False

def _llm_punct_skippable(excerpt: str, note: str) -> bool:
    """LLM 标点提示在逻辑检测页是否应丢弃（非句子 / 与规则口径矛盾 / 引用原文）。

    连续标点硬伤（；；/；。/。；）一律保留。
    """
    raw_ex = excerpt or ""
    note = note or ""
    if _HARD_PUNCT.search(raw_ex):
        return False
    if _logic_non_sentence(raw_ex):
        return True
    # 片段只见右括号、无左括号，不能证明整句缺左括号（左括号可能在未摘录上文）
    if "括号" in note and raw_ex.count("（") < raw_ex.count("）"):
        return True
    # 全角分号「；」本就是合法句末（规则侧允许）；半角 ; 仍报
    if "分号" in note and raw_ex.rstrip().endswith("；"):
        return True
    # 称半角句点但摘录末字符为全角句号，属 LLM 误判
    if ("半角句点" in note or "半角句号" in note) and raw_ex.rstrip().endswith(("。", "！", "？")):
        return True
    # 「…如图X所示：/如下：」引出图表或列举，冒号为规范用法
    if _LEAD_FIGURE.search(raw_ex.rstrip()):
        return True
    # 标准/规程引用：编号、空格、下划线、句末格式保留原文（半角逗号等仍报）
    if _STD_REF.search(raw_ex) and any(k in note for k in ("空格", "下划线", "编号", "范围", "句末", "分号")):
        return True
    # 并列分句最后一句以句号收尾是正确的，不报「与上句分号不匹配/不一致」
    if "分号" in note and ("不匹配" in note or "不一致" in note) and raw_ex.rstrip().endswith("。"):
        return True
    # 规程/标准条款引用：句末标点按原文，不据此报错
    if "条款" in note and ("句末" in note or "句号" in note or "衔接" in note):
        return True
    return False




# 合法的「方位+延伸」线路区段名；双字如北北延伸、西西延伸表示延伸方向层级，不是叠字
_SEG_EXTEND_RE = re.compile(r"(?:[一二三四五六七八九十]+期)?[东南西北]{1,2}延伸")
_VALID_SEG_EXTEND = {
    "北北延伸", "西西延伸", "北延伸", "南延伸", "东延伸", "西延伸",
    "三期东延伸", "三期南延伸",
}


def _llm_typo_skippable(excerpt: str, note: str) -> bool:
    """LLM 把合法区段名（北北延伸、西西延伸等）当多字/叠字时丢弃。

    仅当原文出现的「方位延伸」词全部为合法区段名，且 LLM 指控的是多写/重复/
    应删去一个方位字时才跳过；原文若含其他非法方位词，照常上报。
    """
    excerpt = excerpt or ""
    note = note or ""
    segs = _SEG_EXTEND_RE.findall(excerpt)
    if not segs:
        return False
    if not set(segs).issubset(_VALID_SEG_EXTEND):
        return False
    return bool(re.search(r"多写|多了|多一个|重复|叠字|多字|删[去除]|应(?:为|改为)[^。]{0,6}延伸", note))


# language 通道中本质属于标点/格式的问题：归 punct 通道，避免同句双报
_LANG_END_PUNCT_RE = re.compile(
    r"句末缺标点|句末缺句号|缺句末标点|缺少句末标点|句末没有标点|没有句末标点|缺句号|未加句号|句末标点"
)
# 非句子（清单/图表/表题/括号备注）上的标点、分隔、粘连指控
_LANG_NONSENT_PUNCT_RE = re.compile(r"标点|分隔|句号|顿号|分号|粘连|分句|换行|分段|句末")
# 统计列举句中分号/句号后的「序号+设备名」，数字是编号而非数量，不缺量词
_ENUM_NUM_NOUN = re.compile(r"[；;。]\s*\d{1,2}\s*[\u4e00-\u9fa5]{2,}(?:设备|系统|装置|屏|柜|器|变压器|电源)")


def _llm_language_skippable(excerpt: str, note: str) -> bool:
    """LLM 把 language 用在标点/格式/清单上时丢弃；错别字、用词、句子结构保留。"""
    note = note or ""
    ex = excerpt or ""
    # 句末标点专归 punct 通道（规则与 LLM punct 已覆盖），避免同句 language/punct 双报
    if _LANG_END_PUNCT_RE.search(note):
        return True
    # 清单/图表/表题/备注等非句子上的标点、分隔、粘连，不按语言问题报
    if _logic_non_sentence(ex) and _LANG_NONSENT_PUNCT_RE.search(note):
        return True
    return False


def _llm_enum_skippable(excerpt: str, note: str) -> bool:
    """统计列举「…1项；4电力监控系统…」中数字是分号后的列举序号，不缺量词。"""
    note = note or ""
    ex = excerpt or ""
    if not re.search(r"缺[字量]|缺少量?词", note):
        return False
    if not re.search(r"应(?:为|改)[^。；]{0,6}?\d{1,2}\s*[项个台件]", note):
        return False
    return bool(_ENUM_NUM_NOUN.search(ex))


# LLM 复核返回的 kind → 界面 issue 文案（severe/year 由规则口径负责，不交给模型）
_LLM_KIND_LABEL = {
    "typo": "错别字",
    "language": "语言不通顺",
    "logic": "计算错误",
    "punct": "标点错误",
}


def _looks_like_toc_entry(text: str) -> bool:
    """Word 自动目录（TOC）条目：短行、无句末标点、以章/节编号开头、行尾跟页码。

    例：「第11章 退运报废倾向性评估……101」「11.3 评估小结 128」。
    目录不是正文，不查错别字/标点/语言/计算/年份，也不能当章标题。
    """
    t = (text or "").strip()
    if not t or len(t) > 64:
        return False
    if re.search(r"[。！？；]", t):
        return False
    # 行尾是 1~3 位页码，前面有空白/点线/制表符分隔
    if not re.search(r"(?:[.．…·\t\s]+\d{1,3}|\s+\d{1,3})$", t):
        return False
    # 章条目、多级编号节条目，或纯数字编号的末章条目（如「12 总结与建议 132」）
    return bool(
        re.match(r"^(第\s*\d{1,2}\s*章|\d+(?:[.．]\d+)+|\d{1,2})\s+\S", t)
    )


def norm_domain(domain_id: str) -> str:
    d = (domain_id or "").strip().lower()
    if d in {"power", "power_supply", "供电"}:
        return "power_supply"
    return "overhead"


def domain_label(domain_id: str) -> str:
    return "供电报告" if norm_domain(domain_id) == "power_supply" else "触网报告"


def _devices(domain_id: str) -> tuple[str, ...]:
    if norm_domain(domain_id) == "power_supply":
        return POWER_DEVICES
    return OVERHEAD_DEVICES


def _typos(domain_id: str) -> tuple[tuple[str, str], ...]:
    extra = _POWER_TYPOS if norm_domain(domain_id) == "power_supply" else _OVERHEAD_TYPOS
    return _SHARED_TYPOS + extra


def _chapter_no_from_id(chapter_id: str) -> int | None:
    m = re.search(r"(\d{1,2})", chapter_id or "")
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 15 else None


def _strip_one_trailing_note(text: str) -> str | None:
    """若文本末尾是一个完整括号组，返回去掉该组后的文本；否则返回 None。

    括号类型必须配对（开括号与闭括号同类型），允许同类型嵌套；
    括号前允许半角/全角空白；括号内为空或超过长度上限时不视为备注。
    """
    t = (text or "").rstrip()
    if not t:
        return None
    close = t[-1]
    open_ch = next((o for o, c in _NOTE_BRACKETS.items() if c == close), None)
    if open_ch is None:
        return None
    depth = 0
    for j in range(len(t) - 1, -1, -1):
        ch = t[j]
        if ch == close:
            depth += 1
        elif ch == open_ch:
            depth -= 1
            if depth == 0:
                inner = t[j + 1 : len(t) - 1].strip()
                if not inner or len(inner) > _NOTE_MAX_LEN:
                    return None
                return t[:j].rstrip()
    return None


def _strip_title_note(text: str) -> str:
    """去掉标题末尾的一组或多组括号备注（支持嵌套括号），供电、触网同一规则。

    备注不参与「是不是章标题」的判断，避免「（待更新）」把整章挤出检测范围。
    """
    t = (text or "").strip()
    while True:
        nxt = _strip_one_trailing_note(t)
        if nxt is None or not nxt:
            return t
        t = nxt


def heading_chapter(text: str) -> int | None:
    """「第3章 …」或「3 设备功能有效性评估」，不把「3.1」或叙述句当成章标题。

    先去掉末尾备注再认章，避免「（待更新）」把整章挤出检测范围。
    """
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return None
    t = re.sub(r"\s+", " ", _strip_title_note(raw))
    if not t or len(t) > 48:
        return None
    m = _CHAPTER_HEAD.match(t)
    if m:
        n = int(m.group(1))
        rest = t[m.end() :].strip(" ：:、")
        if not (1 <= n <= 15):
            return None
        if re.search(r"[。！？]", t):
            return None
        if re.search(r"评为|截止到|截止至|截至|其中|(?:应|需|已)报废", rest):
            return None
        return n
    if "。" in t or re.match(r"^\d+[\.．]", t):
        return None
    m = _BARE_CHAPTER.match(t)
    if not m:
        return None
    n = int(m.group(1))
    if 1 <= n <= 12 and "评估" in t and "评为" not in t:
        return n
    return None


def chapter_no_by_name(text: str) -> int | None:
    """按章名核心词识别无编号章标题（自动编号被解析掉的情形）。

    只认短标题；正文长句即使含「评估」等字样也不会命中。
    章名后的备注先去掉。供电、触网、全文、按章都走这里。
    """
    t = re.sub(r"\s+", "", _strip_title_note(text or ""))
    if not t or len(t) > 24 or re.search(r"[。！？，,；;：:、（）()【】\[\]]", t):
        return None
    for no, core in _CHAPTER_NAME_CORE.items():
        if core in t:
            return no
    return None


# 章标题候选行的长度上限（去空白后）
_CHAPTER_TITLE_MAX = 40
# 节编号开头，如 3.1、11．2（章标题不会是多级编号）
_SECTION_NUM_HEAD = re.compile(r"^\d{1,2}\s*[.．]\s*\d")
_SENTENCE_END = re.compile(r"[。！？!?；;]")
# 手工排版章标题的字号阈值（正文多为 12pt/小四，章标题多为四号 14pt 及以上）
_TITLE_FONT_SIZE = 13.5
# 规则采纳阈值与 LLM 兜底阈值
_RULE_SCORE_MIN = 42


def _is_chapter_candidate(unit: dict[str, Any]) -> bool:
    """是否可能是章标题候选：短行、非目录、非节编号、非完整句子。"""
    t = (unit.get("text") or "").strip()
    if not t or _looks_like_toc_entry(t):
        return False
    body = _compact(_strip_title_note(t))
    if not body or len(body) > _CHAPTER_TITLE_MAX:
        return False
    if _SENTENCE_END.search(body) or _SECTION_NUM_HEAD.match(body):
        return False
    return True


def _format_strong(unit: dict[str, Any]) -> bool:
    """手工排版章标题的格式信号：加粗、字号显著大于正文、或居中且强调。"""
    if unit.get("bold"):
        return True
    size = float(unit.get("font_size") or 0.0)
    if size >= _TITLE_FONT_SIZE:
        return True
    if unit.get("centered") and size >= _TITLE_FONT_SIZE:
        return True
    return False


def _candidate_score(unit: dict[str, Any], no: int) -> tuple[int, str]:
    """候选 unit 作为第 no 章标题的得分（0 表示不成立）与识别途径。

    综合编号（第N章/N 标题）、章名核心词、块样式（Heading/手工格式）与顺序；
    编号与核心词互相冲突时候选作废。
    """
    num = heading_chapter(unit.get("text") or "")
    name = chapter_no_by_name(unit.get("text") or "")
    if num is not None and name is not None and num != name:
        return 0, ""
    if num is not None and num != no:
        return 0, ""
    if name is not None and name != no:
        return 0, ""
    kind = unit.get("kind")
    level = int(unit.get("level") or 0)
    score = 0
    via = ""
    if name == no:
        if kind == "heading" and level == 1:
            score, via = 70, "章名+一级标题样式"
        elif kind == "heading":
            score, via = 58, "章名+标题样式"
        elif _format_strong(unit):
            score, via = 55, "章名+字体格式"
        else:
            score, via = 42, "章名+章节顺序"
    elif num == no:
        if kind == "heading" and level == 1:
            score, via = 62, "编号+一级标题样式"
        elif kind == "heading":
            score, via = 52, "编号+标题样式"
        elif _format_strong(unit):
            score, via = 48, "编号+字体格式"
        else:
            score, via = 45, "编号+章节顺序"
    if name == no and num == no:
        score += 25
        via = "编号+章名+样式"
    return score, via


def _confidence_of(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def resolve_chapters_rules(
    units: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], list[int]]:
    """规则多信号融合：按章号 3→11 顺序，在严格递增的位置上选最高分候选。

    缺章时游标不推进，后续章仍可定位；返回 {章号: 定位信息} 与缺失章号列表。
    """
    chapter_map: dict[int, dict[str, Any]] = {}
    used: set[int] = set()
    cursor = -1
    for no in range(_SCAN_FROM, _SCAN_TO + 1):
        best_idx = -1
        best_score = 0
        best_via = ""
        for idx, unit in enumerate(units):
            if idx <= cursor or idx in used:
                continue
            if not _is_chapter_candidate(unit):
                continue
            score, via = _candidate_score(unit, no)
            if score > best_score:
                best_score, best_idx, best_via = score, idx, via
        if best_idx >= 0 and best_score >= _RULE_SCORE_MIN:
            chapter_map[no] = {
                "no": no,
                "unit_idx": best_idx,
                "score": best_score,
                "via": best_via,
                "confidence": _confidence_of(best_score),
                "source": "rule",
            }
            used.add(best_idx)
            cursor = best_idx
    missing = [n for n in range(_SCAN_FROM, _SCAN_TO + 1) if n not in chapter_map]
    return chapter_map, missing


def _llm_chapter_candidates(
    units: list[dict[str, Any]],
    chapter_map: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """收集规则未定位、但疑似章标题的短行，供 LLM 兜底判断。"""
    used = {info["unit_idx"] for info in chapter_map.values()}
    out: list[dict[str, Any]] = []
    for idx, unit in enumerate(units):
        if idx in used or not _is_chapter_candidate(unit):
            continue
        kind = unit.get("kind")
        text = (unit.get("text") or "").strip()
        if kind == "heading":
            keep = True
        elif _format_strong(unit):
            keep = True
        else:
            # 正文样式短行：含章名核心词或「评估/倾向」等字样才送 LLM
            body = _compact(_strip_title_note(text))
            keep = ("评估" in body or "倾向" in body) or any(
                core in body for core in _CHAPTER_NAME_CORE.values()
            )
        if keep:
            out.append({"unit_idx": idx, "text": text})
    return out[:80]


def _blocks_to_units(doc) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for i, block in enumerate(doc.blocks or []):
        if block.type == "table" and block.rows:
            text = "；".join(" / ".join(str(c) for c in row) for row in block.rows[:80])
            if text.strip():
                units.append({"i": i, "kind": block.type, "text": text.strip(), "rows": block.rows})
            continue
        t = (block.text or "").strip()
        if not t:
            continue
        units.append(
            {
                "i": i,
                "kind": block.type,
                "text": t,
                "level": getattr(block, "level", 0),
                "style_name": getattr(block, "style_name", "") or "",
                "font_size": float(getattr(block, "font_size", 0.0) or 0.0),
                "bold": bool(getattr(block, "bold", False)),
                "centered": bool(getattr(block, "centered", False)),
            }
        )
    return units


def resolve_chapters(
    units: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], list[int]]:
    """章节识别总入口：规则多信号融合优先，缺章且 LLM 可用时再用 LLM 兜底。

    LLM 只填补规则缺失的章，不覆盖规则结果；无 Key/失败/测试环境静默降级。
    """
    chapter_map, missing = resolve_chapters_rules(units)
    if not missing:
        return chapter_map, missing
    try:
        from chapters.common.logic_llm import llm_resolve_chapters as _llm_resolve

        llm_map = _llm_resolve(units, chapter_map, _llm_chapter_candidates(units, chapter_map))
    except Exception:
        llm_map = {}
    for no, info in (llm_map or {}).items():
        if no in chapter_map or no not in missing:
            continue
        chapter_map[no] = info
    missing = [n for n in range(_SCAN_FROM, _SCAN_TO + 1) if n not in chapter_map]
    return chapter_map, missing


def _guess_section(units: list[dict[str, Any]], idx: int) -> str:
    for j in range(idx, -1, -1):
        t = units[j]["text"].strip()
        if len(t) <= 48 and (
            units[j]["kind"] == "heading"
            or heading_chapter(t) is not None
            or (units[j]["kind"] == "paragraph" and chapter_no_by_name(t) is not None)
            or bool(re.match(r"^\d+(?:[\.．]\d+)+", t))
            or t.startswith("第")
        ):
            return t[:40]
    return "正文"


def _annotate(
    units: list[dict[str, Any]],
    chapter_map: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """按多信号融合的章节定位结果标注每段所属章号；标题位置由 resolve_chapters 决定。"""
    title_at = {info["unit_idx"]: no for no, info in (chapter_map or {}).items()}
    current: int | None = None
    out: list[dict[str, Any]] = []
    for idx, unit in enumerate(units):
        # 目录条目不改变当前章号，也不参与规则检查
        if _looks_like_toc_entry(unit["text"]):
            item = dict(unit)
            item["chapter_no"] = current
            item["section"] = _guess_section(units, idx)
            out.append(item)
            continue
        if idx in title_at:
            current = title_at[idx]
        elif _is_afterword(unit["text"]):
            current = 0
        item = dict(unit)
        item["chapter_no"] = current
        item["section"] = _guess_section(units, idx)
        out.append(item)
    return out


def _loc(unit: dict[str, Any]) -> str:
    no = unit.get("chapter_no")
    sec = (unit.get("section") or "正文").strip()
    if not no:
        return sec or "正文"
    head = f"第{no}章"
    if not sec or sec == "正文":
        return head
    if head in sec:
        return sec
    return f"{head} {sec}"


def _add(
    out: list[dict[str, str]],
    *,
    kind: str,
    issue: str,
    section: str,
    note: str,
    excerpt: str = "",
    via: str = "",
) -> None:
    row = {
        "kind": kind,
        "issue": issue,
        "section": section or "正文",
        "note": note,
        "excerpt": (excerpt or "").replace("\n", " ")[:220],
        "via": via,
    }
    key = (row["kind"], row["section"], row["note"], row["excerpt"])
    if any((x["kind"], x["section"], x["note"], x["excerpt"]) == key for x in out):
        return
    out.append(row)


_TOTAL_ROW_WORDS = ("合计", "总计", "小计", "共计")
_NUMERIC_CELL_RE = re.compile(r"^[\d.]+$")


def _fmt_num(value: float) -> str:
    """整数不带小数位，其余保留 2 位以内。"""
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _is_index_column(parts: list[float], header: str) -> bool:
    """序号列不做合计核对。

    两种判据任一成立即可：
    1. 表头写「序号/编号/No/#」；
    2. 表头缺失时，分项数值是从 1 开始的连续自然数（1,2,3…）。
    """
    h = (header or "").strip().lower()
    if "序号" in h or "编号" in h or h in {"序", "no", "no.", "#"}:
        return True
    if len(parts) >= 3:
        ints = [int(p) for p in parts if abs(p - round(p)) < 1e-9]
        if len(ints) == len(parts) and ints == list(range(1, len(ints) + 1)):
            return True
    return False


def _table_sum_check(rows: list[list[Any]] | None, section: str) -> list[dict[str, str]]:
    """表内核对：找「合计/总计/小计/共计」行，把该行数值列与上方分项求和比较。

    只对至少 2 个可解析数字且合计单元格可解析的列做核对；文本单元格跳过；
    序号列（表头写序号/编号，或数值为连续自然数）不核对；
    合并单元格导致的空值不影响判断（空单元格不计入分项）。
    """
    if not rows or len(rows) < 3:
        return []
    header = [str(c) for c in rows[0]]
    total_idx: int | None = None
    for r in range(len(rows) - 1, 0, -1):
        if any(any(w in str(c) for w in _TOTAL_ROW_WORDS) for c in rows[r]):
            total_idx = r
            break
    if total_idx is None:
        return []
    out: list[dict[str, str]] = []
    ncols = max(len(r) for r in rows)
    for col in range(ncols):
        total_raw = str(rows[total_idx][col] if col < len(rows[total_idx]) else "").strip()
        try:
            total = float(total_raw)
        except ValueError:
            continue
        parts: list[float] = []
        for r in range(1, total_idx):
            cell = str(rows[r][col] if col < len(rows[r]) else "").strip()
            if any(w in cell for w in _TOTAL_ROW_WORDS):
                continue
            try:
                parts.append(float(cell))
            except ValueError:
                continue
        head = header[col].strip() if col < len(header) else ""
        if len(parts) < 2:
            continue
        if _is_index_column(parts, head):
            continue
        got = sum(parts)
        if abs(got - total) <= 0.5:
            continue
        colname = head if head and not _NUMERIC_CELL_RE.match(head) else f"第{col + 1}列"
        shown = "+".join(_fmt_num(p) for p in parts[:8])
        if len(parts) > 8:
            shown += f"…（共{len(parts)}项）"
        out.append(
            {
                "kind": "logic",
                "issue": "计算错误",
                "section": section,
                "note": f"表内{colname}合计行写 {_fmt_num(total)}，分项求和 {_fmt_num(got)}（{shown}），与合计不符",
                "excerpt": " / ".join(str(c) for c in rows[total_idx][:8]),
            }
        )
    return out


def _rule_paragraph_sum(text: str) -> list[str]:
    """同一句里声明总数，后面「其中」分项相加是否等于总数。"""
    t = _compact(text)
    if len(t) < 8:
        return []
    notes: list[str] = []
    for m in _TOTAL_KIND.finditer(t):
        total = int(m.group(1))
        unit = m.group(2)
        tail = t[m.end() :]
        stop = re.search(r"[。！？]", tail)
        chunk = tail[: stop.start()] if stop else tail[:180]
        if "其中" not in chunk:
            continue
        chunk = chunk[chunk.find("其中") :]
        # 同段并列下一年/下一组总数时，分项只属于当前总数，在下一个总数声明处截断
        next_decl = re.search(rf"(?:共有|总共|合计|共计|一共|总计|共)\s*\d+\s*{unit}", chunk)
        if next_decl:
            chunk = chunk[: next_decl.start()]
        parts = [int(x) for x in re.findall(rf"(\d+)\s*{unit}", chunk)]
        if len(parts) < 2:
            continue
        got = sum(parts)
        if got != total:
            expr = "+".join(str(x) for x in parts)
            notes.append(
                f"本句写共{total}{unit}，其中分项{expr}={got}{unit}，与总数不符，属于计算错误"
            )
    return notes


def _is_afterword(text: str) -> bool:
    """附录、附件、「总结与建议」等正文之后的标题。正文里的「如附件1所示」不算，避免把后文整段丢掉。"""
    raw = (text or "").strip()
    t = re.sub(r"\s+", "", raw)
    if not t or len(t) > 20 or re.search(r"[。！？，,；;]", raw):
        return False
    if "所示" in t or "详见" in t:
        return False
    if "总结与建议" in t:
        return True
    return bool(re.match(r"^(附录|附件)", t))


def _is_title(unit: dict[str, Any]) -> bool:
    t = unit.get("text") or ""
    return (
        unit.get("kind") == "heading"
        or heading_chapter(t) is not None
        or is_section_title_line(t)
    )


def _same_place_conflict(text: str, devices: tuple[str, ...]) -> str:
    """同一段里既评 A 级又写报废。"""
    graded = _device_hits(text, devices, _window_is_a)
    scrapped = _device_hits(text, devices, _window_is_scrap)
    if not graded or not scrapped:
        return ""
    a_keys = set(graded)
    for ln, device in scrapped:
        hit = ""
        if (ln, device) in a_keys or ("*", device) in a_keys:
            hit = ln
        elif ln == "*" and any(k[1] == device for k in a_keys):
            hit = next(k[0] for k in a_keys if k[1] == device)
        else:
            continue
        where = f"{hit}号线" if hit and hit != "*" else ""
        return f"同一处将{where}{device}评为A级，又写成报废，语言逻辑不通顺"
    return ""


def _scan_local(
    units: list[dict[str, Any]],
    year: int | None,
    typos: tuple[tuple[str, str], ...],
    devices: tuple[str, ...],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for unit in units:
        t = unit["text"]
        # 目录条目不查任何规则（不是正文）
        if _looks_like_toc_entry(t):
            continue
        sec = _loc(unit)
        title = _is_title(unit)
        if not title:
            for wrong, right in typos:
                if wrong in t:
                    _add(
                        out,
                        kind="typo",
                        issue="错别字",
                        section=sec,
                        note=f"「{wrong}」应为「{right}」",
                        excerpt=t,
                    )
        if unit.get("kind") != "table" and not title:
            if is_incomplete(t):
                _add(
                    out,
                    kind="language",
                    issue="语言不通顺",
                    section=sec,
                    note=language_note(t),
                    excerpt=t,
                )
            elif (
                is_punct_issue(t)
                and len(t) >= 12
                and not t.startswith(("——", "—", "--"))
                # 连续标点硬伤始终报；清单/图表数据/表题/括号备注等非句子不要求句末标点
                and (_HARD_PUNCT.search(t) or not _logic_non_sentence(t))
            ):
                _add(
                    out,
                    kind="punct",
                    issue="标点错误",
                    section=sec,
                    note=punct_note(t),
                    excerpt=t,
                )
        for note in _rule_paragraph_sum(t):
            _add(out, kind="logic", issue="计算错误", section=sec, note=note, excerpt=t)
        if unit.get("kind") != "table":
            # 报告侧更丰富的数字规则：故障总数/均值/趋势（段落级）
            for note in number_logic_notes(t):
                _add(out, kind="logic", issue="计算错误", section=sec, note=note, excerpt=t)
        else:
            # 表格核对：合计行 vs 分项求和
            for row in _table_sum_check(unit.get("rows"), sec):
                _add(
                    out,
                    kind=row["kind"],
                    issue=row["issue"],
                    section=row["section"],
                    note=row["note"],
                    excerpt=row["excerpt"],
                )
        conflict = "" if title else _same_place_conflict(t, devices)
        if conflict:
            _add(out, kind="language", issue="语言不通顺", section=sec, note=conflict, excerpt=t)
        if year:
            for ym in _AS_OF.finditer(t):
                y = int(ym.group(1))
                window = t[ym.start() : ym.end() + 24]
                if y < year and not _COMPLETION_CTX.search(window):
                    _add(
                        out,
                        kind="year",
                        issue="年份错误",
                        section=sec,
                        note=f"评估年为{year}年，文中写有「{ym.group(0).strip()}」，年份偏早",
                        excerpt=t,
                    )
    return out


def _window_is_a(window: str) -> bool:
    if _A_VERB.search(window):
        return True
    if _A_NEG.search(window):
        return False
    return bool(_A_MARK.search(window))


def _window_is_scrap(window: str) -> bool:
    w = re.sub(r"(?:无需|不需|暂不|尚未|没有|不予)报废", "", window)
    w = w.replace("不报废", "").replace("未报废", "")
    w = w.replace("报废倾向", "").replace("退运报废", "")
    return "报废" in w


def _device_hits(text: str, devices: tuple[str, ...], pred) -> list[tuple[str, str]]:
    covered: list[tuple[int, int]] = []
    hits: list[tuple[str, str]] = []
    for device in sorted(devices, key=len, reverse=True):
        for m in re.finditer(re.escape(device), text):
            if any(a <= m.start() < b for a, b in covered):
                continue
            lo = max(0, m.start() - 30)
            hi = min(len(text), m.end() + 30)
            if not pred(text[lo:hi]):
                continue
            covered.append((m.start(), m.end()))
            near = text[max(0, m.start() - 20) : min(len(text), m.end() + 8)]
            lines = _LINE.findall(near) or ["*"]
            for ln in lines:
                hits.append((ln, device))
    return hits


def _cross_chapter(
    units: list[dict[str, Any]],
    devices: tuple[str, ...],
) -> list[dict[str, str]]:
    """第3章 A 级与第11章报废对上同一线路、同一设备时，记严重逻辑错误。"""
    ch3 = [u for u in units if u.get("chapter_no") == 3 and not _is_title(u)]
    ch11 = [u for u in units if u.get("chapter_no") == 11 and not _is_title(u)]
    a_keys: set[tuple[str, str]] = set()
    for unit in ch3:
        for ln, device in _device_hits(unit["text"], devices, _window_is_a):
            a_keys.add((ln, device))
    if not a_keys:
        return []
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for unit in ch11:
        for ln, device in _device_hits(unit["text"], devices, _window_is_scrap):
            matched = ""
            if (ln, device) in a_keys:
                matched = ln
            elif ("*", device) in a_keys:
                matched = ln
            elif ln == "*" and any(k[1] == device for k in a_keys):
                matched = next(k[0] for k in a_keys if k[1] == device)
            else:
                continue
            key = (matched or ln, device)
            if key in seen:
                continue
            seen.add(key)
            where = f"{matched}号线" if matched and matched != "*" else ""
            _add(
                out,
                kind="severe",
                issue="逻辑错误",
                section=f"第3章 / {_loc(unit)}",
                note=(
                    f"第3章将{where}{device}评为A级，第11章却将该设备写成报废，前后矛盾"
                ),
                excerpt=unit["text"],
            )
    return out


def _chapter_internal(units: list[dict[str, Any]], devices: tuple[str, ...]) -> list[dict[str, str]]:
    """同一章里前后两段：前面评 A 级，后面写成报废。同一段的已由 _same_place_conflict 处理。"""
    groups: dict[int | None, list[dict[str, Any]]] = {}
    for unit in units:
        if _is_title(unit):
            continue
        groups.setdefault(unit.get("chapter_no"), []).append(unit)
    out: list[dict[str, str]] = []
    for group in groups.values():
        graded: dict[tuple[str, str], str] = {}
        for unit in group:
            if _same_place_conflict(unit["text"], devices):
                continue
            for ln, device in _device_hits(unit["text"], devices, _window_is_a):
                graded.setdefault((ln, device), unit["text"])
        seen: set[tuple[str, str]] = set()
        for unit in group:
            if _same_place_conflict(unit["text"], devices):
                continue
            for ln, device in _device_hits(unit["text"], devices, _window_is_scrap):
                matched = ""
                if (ln, device) in graded:
                    matched = ln
                elif ("*", device) in graded:
                    matched = ln
                elif ln == "*" and any(k[1] == device for k in graded):
                    matched = next(k[0] for k in graded if k[1] == device)
                else:
                    continue
                key = (matched or ln, device)
                if key in seen:
                    continue
                seen.add(key)
                where = f"{matched}号线" if matched and matched != "*" else ""
                _add(
                    out,
                    kind="language",
                    issue="语言不通顺",
                    section=_loc(unit),
                    note=f"本章前面将{where}{device}评为A级，这里又写成报废，语言逻辑不通顺",
                    excerpt=unit["text"],
                )
    return out


def _chapter_ranges(nos: list[int]) -> str:
    """把章号列表格式化为「3、5-7、11」形式。"""
    if not nos:
        return ""
    parts: list[str] = []
    start = prev = nos[0]
    for no in nos[1:]:
        if no == prev + 1:
            prev = no
            continue
        parts.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = no
    parts.append(str(start) if start == prev else f"{start}-{prev}")
    return "、".join(parts)


def _chapters_found(units: list[dict[str, Any]], chapter_map: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """把章节定位结果转成对外清单：章号、标题、块位置、单元数、识别途径、置信度。"""
    positions = sorted((info["unit_idx"], no) for no, info in chapter_map.items())
    out: list[dict[str, Any]] = []
    for k, (pos, no) in enumerate(positions):
        end = positions[k + 1][0] if k + 1 < len(positions) else len(units)
        info = chapter_map[no]
        title = _strip_title_note(units[pos].get("text") or "").strip()
        out.append(
            {
                "no": no,
                "title": title[:40],
                "block_index": units[pos].get("i", pos),
                "unit_count": max(0, end - pos - 1),
                "via": info.get("via", ""),
                "confidence": info.get("confidence", "low"),
                "source": info.get("source", "rule"),
            }
        )
    return out


def _select_units(
    units: list[dict[str, Any]],
    *,
    mode: str,
    chapter_id: str,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]], list[int]]:
    """解析章节 → 标注 → 按模式选单元。

    返回 (选中单元, 警告文案, 已识别章节清单, 缺失章号列表)。
    """
    chapter_map, missing = resolve_chapters(units)
    tagged = _annotate(units, chapter_map)
    found = _chapters_found(units, chapter_map)
    has_heads = bool(chapter_map)
    if (mode or "full") == "chapter":
        want = _chapter_no_from_id(chapter_id)
        if want is None:
            return [], "未选择章节", found, missing
        if not has_heads:
            for u in tagged:
                u["chapter_no"] = want
            return tagged, "", found, missing
        picked = [u for u in tagged if u.get("chapter_no") == want]
        if not picked:
            return (
                [],
                f"未在文中定位到第{want}章，请确认报告含第{want}章标题（章名后可带备注，如「（待更新）」）",
                found,
                missing,
            )
        return picked, "", found, missing
    if not has_heads:
        return (
            tagged,
            "未识别第3章至第11章标题，已按全文做章内检查，无法做跨章核对",
            found,
            missing,
        )
    selected = [u for u in tagged if u.get("chapter_no") in range(_SCAN_FROM, _SCAN_TO + 1)]
    warn = ""
    if missing:
        got = [n for n in range(_SCAN_FROM, _SCAN_TO + 1) if n not in missing]
        warn = f"已识别第{_chapter_ranges(got)}章，未识别第{_chapter_ranges(missing)}章，缺章相关内容未纳入检查"
    return selected, warn, found, missing


def summarize_findings(findings: list[dict[str, str]]) -> dict[str, int]:
    return {
        "typo": sum(1 for x in findings if x.get("kind") == "typo"),
        "punct": sum(1 for x in findings if x.get("kind") == "punct"),
        "language": sum(1 for x in findings if x.get("kind") == "language"),
        "logic": sum(1 for x in findings if x.get("kind") == "logic"),
        "year": sum(1 for x in findings if x.get("kind") == "year"),
        "severe": sum(1 for x in findings if x.get("kind") == "severe"),
        "number": sum(1 for x in findings if x.get("kind") == "logic"),
        "contradiction": sum(1 for x in findings if x.get("kind") == "severe"),
    }


def format_logic_message(
    findings: list[dict[str, str]],
    *,
    domain_id: str,
    mode: str,
    chapter_id: str = "",
    extra: str = "",
) -> str:
    label = domain_label(domain_id)
    if (mode or "full") == "chapter":
        no = _chapter_no_from_id(chapter_id)
        scope = f"第{no}章" if no else "所选章节"
    else:
        scope = "第3章至第11章"
    head = f"{label}{scope}"
    if extra:
        head = f"{head}（{extra}）"
    if not findings:
        return f"{head}：未发现错别字、标点、语言、计算、年份或跨章逻辑错误。"
    s = summarize_findings(findings)
    return (
        f"{head}：共检测到 {len(findings)} 处"
        f"（错别字 {s['typo']}，标点 {s['punct']}，语言 {s['language']}，"
        f"计算 {s['number']}，年份 {s['year']}，逻辑 {s['severe']}）"
    )


# ── LLM 结果去重：同一处错误被多次摘录（跨分块/单章与跨章）时只保留一条 ──────
# 引号内词句（「scada」「SCADA」）与百分比；用于判断两条诊断是否指向同一错误
_DUP_QUOTE_RE = re.compile(r"[「『“‘\"]([^」』”’\"]{1,24})[」』”’\"]")
_DUP_LCS_MIN = 24          # 同诊断核心时，最长公共子串至少 24 字
_DUP_PREFIX_MIN = 12      # 严格前缀去重的短边下限
_DUP_PREFIX_GAP = 8        # 长短边至少相差 8 字
_DUP_RULE_LCS_MIN = 30     # 规则×LLM 同段数字矛盾的公共子串下限


def _diag_core(note: str, kind: str) -> tuple:
    """诊断核心：引号词 + 百分比集合；logic 类再加整数集合。"""
    t = str(note or "")
    quoted = tuple(sorted(set(_DUP_QUOTE_RE.findall(t))))
    pcts = tuple(sorted(set(re.findall(r"\d+\.\d{1,2}\s*%", t))))
    if kind == "logic":
        nums = tuple(sorted(set(re.findall(r"\d+", t))))
        return ("logic", quoted, pcts, nums)
    return (kind, quoted, pcts)


def _lcs_len(a: str, b: str) -> int:
    """两串最长公共子串长度（去空白后比较）。"""
    if not a or not b:
        return 0
    return SequenceMatcher(None, a, b, autojunk=False).find_longest_match(
        0, len(a), 0, len(b)
    ).size


def _same_logic_fingerprint(n1: str, n2: str) -> bool:
    """规则与 LLM 的数字矛盾是否同源：整数集合交集占比足够高。"""
    a = set(re.findall(r"\d+", n1 or ""))
    b = set(re.findall(r"\d+", n2 or ""))
    if not a or not b:
        return False
    common = a & b
    if len(common) < 2:
        return False
    return len(common) / min(len(a), len(b)) >= 0.8


def _llm_dup_index(item: dict[str, Any], findings: list[dict[str, str]]) -> int:
    """新 LLM 条目与已存在条目重复时返回索引，否则 -1。

    判据（同 kind 下，按顺序）：
    1. 摘录完全相等；
    2. 一条是另一条的严格前缀/后缀（同一处文本被截取成一短一长，如 scada 两张卡）；
    3. 诊断核心相同（引号词/百分比一致）且一条几乎完全被另一条包含（同一句不同截取）；
    4. logic 类与规则条目同段（公共子串≥30 字且占比≥0.6）且数字指纹同源。
    模板化的多处同型错误（如两处「温室度」、两处「4月低」）摘录不同、
    仅差「我方」等少量前缀字，不构成重复，不会被误并。
    """
    kind = item.get("kind") or "logic"
    ne = _compact(item.get("excerpt") or "")
    nn = _compact(item.get("note") or "")
    if len(ne) < 8:
        return -1
    ne_core = _diag_core(nn, kind)
    for i, f in enumerate(findings):
        if f.get("kind") != kind:
            continue
        fe = _compact(f.get("excerpt") or "")
        fn = _compact(f.get("note") or "")
        if len(fe) < 8:
            continue
        # 1) 摘录相等
        if ne == fe:
            return i
        # 2) 严格前缀/后缀（从开头或结尾对齐，且长短差距足够大）
        short, long_ = (ne, fe) if len(ne) <= len(fe) else (fe, ne)
        if (
            len(short) >= _DUP_PREFIX_MIN
            and len(long_) - len(short) >= _DUP_PREFIX_GAP
            and (long_.startswith(short) or long_.endswith(short))
        ):
            return i
        # 3) 同诊断核心：短边几乎全部被长边包含，且长短差距足够大
        if (
            nn
            and fn
            and ne_core == _diag_core(fn, kind)
            and len(long_) - len(short) >= _DUP_PREFIX_GAP
        ):
            lcs = _lcs_len(ne, fe)
            if lcs >= _DUP_LCS_MIN and lcs >= len(short) * 0.9:
                return i
        # 4) 规则×LLM 同段数字矛盾
        if kind == "logic" and f.get("via") != "llm":
            lcs = _lcs_len(ne, fe)
            if (
                lcs >= _DUP_RULE_LCS_MIN
                and lcs >= min(len(ne), len(fe)) * 0.6
                and _same_logic_fingerprint(nn, fn)
            ):
                return i
    return -1


def _sort_findings(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    """按「章 → 节 → 严重程度 → 原文顺序」排列，使全文检测结果从第3章起逐章给出。

    跨章矛盾（如「第3章 / 第11章 …」）按其首次出现的章号归入该章；
    无章号（如「跨章数字核对」）排到最后。同一章同一节内，严重问题优先。
    """

    def chapter_key(section: str) -> int:
        m = re.search(r"第(\d+)章", section or "")
        return int(m.group(1)) if m else 99

    def section_key(section: str) -> tuple[int, ...]:
        # 节号 3.1 / 3.2.1：取「第N章」后的首个数字编号；无节号归章首
        m = re.search(r"(\d{1,2})[.．](\d{1,2})(?:[.．](\d{1,2}))?", section or "")
        return tuple(int(x) for x in m.groups() if x is not None) if m else (0,)

    indexed = list(enumerate(findings))
    indexed.sort(
        key=lambda t: (
            chapter_key(t[1].get("section") or ""),
            section_key(t[1].get("section") or ""),
            _KIND_ORDER.get(t[1].get("kind") or "", 9),
            t[0],
        )
    )
    return [f for _, f in indexed]


def _emit_progress(
    on_progress: Callable[[int, str], None] | None, percent: int, label: str
) -> None:
    """向前端推送一次真实阶段进度；回调缺失或回调内报错都不得影响检测。"""
    if on_progress is None:
        return
    try:
        on_progress(int(percent), str(label))
    except Exception:
        pass


def run_logic_page_check(
    path: str | Path,
    *,
    assessment_year: int | None = None,
    mode: str = "full",
    chapter_id: str = "",
    domain_id: str = "overhead",
    out_dir: Path | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    """检测入口。out_dir 保留兼容，不再生成标黄稿。

    规则先跑；有 LLM Key 时再做语义复核（错别字/语言/数字矛盾），
    模型发现必须带原文摘录且摘录在原文中可找到，否则丢弃。

    on_progress(percent, label)：按真实执行阶段回调（解析→识别章节→规则检查
    →逻辑矛盾核对→LLM 语义复核→汇总），仅用于前端进度展示，不改变检测结果。
    """
    del out_dir
    path = Path(path)
    year = int(assessment_year) if assessment_year else None
    domain = norm_domain(domain_id)
    _emit_progress(on_progress, 4, "正在解析文档内容…")
    parsed = parse_file(path)
    units = _blocks_to_units(parsed)
    _emit_progress(on_progress, 14, "正在识别第3～11章标题…")
    selected, warn, chapters_found, chapters_missing = _select_units(
        units,
        mode=mode or "full",
        chapter_id=chapter_id or "",
    )
    _emit_progress(on_progress, 26, "正在检查错别字、标点、语言、计算与年份…")
    findings = _scan_local(selected, year, _typos(domain), _devices(domain))
    findings.extend(_chapter_internal(selected, _devices(domain)))
    _emit_progress(on_progress, 50, "正在核对上下文逻辑矛盾…")
    if (mode or "full") != "chapter":
        findings.extend(_cross_chapter(selected, _devices(domain)))
        # 第3章评级表（A/B/C/D）与第11章报废清单的跨章矛盾
        for row in _grade_scrap_findings(selected, assessment_year=year):
            _add(
                findings,
                kind=row["kind"],
                issue=row["issue"],
                section=row["section"],
                note=row["note"],
                excerpt=row.get("excerpt", ""),
            )
    def _llm_progress(done: int, total: int) -> None:
        if total <= 0:
            return
        pct = 60 + round(32 * done / total)
        _emit_progress(
            on_progress, min(92, pct), f"LLM 语义复核中（{done}/{total}），请稍候…"
        )

    _emit_progress(on_progress, 58, "正在进行 LLM 语义复核…")
    llm_findings, llm_used = _llm_review_units(
        selected,
        domain_id=domain,
        mode=mode or "full",
        chapter_id=chapter_id or "",
        year=year,
        on_progress=_llm_progress,
    )
    if llm_findings:
        for item in llm_findings:
            ex = _compact(item.get("excerpt") or "")
            if not ex:
                continue
            no = item.get("chapter_no")
            sec = f"第{no}章" if isinstance(no, int) else "跨章数字核对"
            kind = item.get("kind") or "logic"
            if kind == "punct" and _llm_punct_skippable(
                item.get("excerpt") or "", item.get("note") or ""
            ):
                continue
            if kind == "typo" and _llm_typo_skippable(
                item.get("excerpt") or "", item.get("note") or ""
            ):
                continue
            if kind == "language" and (
                _llm_language_skippable(item.get("excerpt") or "", item.get("note") or "")
                or _llm_enum_skippable(item.get("excerpt") or "", item.get("note") or "")
            ):
                continue
            # 与规则结果或已并入的 LLM 结果重复（同处错误被多次摘录）
            dup_idx = _llm_dup_index(item, findings)
            if dup_idx >= 0:
                old = findings[dup_idx]
                # 规则条目定位更精确，永远保留；LLM 条目则保留摘录更完整的一条
                if old.get("via") == "llm" and len(ex) > len(_compact(old.get("excerpt") or "")) + 10:
                    old["note"] = item.get("note") or old["note"]
                    old["excerpt"] = (item.get("excerpt") or "").replace("\n", " ")[:220]
                continue
            _add(
                findings,
                kind=kind,
                issue=_LLM_KIND_LABEL.get(kind, "其它"),
                section=sec,
                note=item.get("note") or "",
                excerpt=item.get("excerpt") or "",
                via="llm",
            )
    _emit_progress(on_progress, 95, "正在汇总、去重并排序…")
    findings = _sort_findings(findings)
    summary = summarize_findings(findings)
    _emit_progress(on_progress, 100, "检测完成")
    return {
        "ok": True,
        "mode": mode or "full",
        "chapter_id": chapter_id or "",
        "domain_id": domain,
        "domain_label": domain_label(domain),
        "source": path.name,
        "unit_count": len(selected),
        "finding_count": len(findings),
        "summary": summary,
        "findings": findings,
        "llm_used": llm_used,
        "llm_finding_count": sum(1 for f in findings if f.get("via") == "llm"),
        "chapters_found": chapters_found,
        "chapters_missing": chapters_missing,
        "marked_report": "",
        "marked_url": "",
        "message": format_logic_message(
            findings,
            domain_id=domain,
            mode=mode or "full",
            chapter_id=chapter_id or "",
            extra=warn,
        ),
    }
