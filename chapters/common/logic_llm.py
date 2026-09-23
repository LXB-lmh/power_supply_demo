# -*- coding: utf-8 -*-
"""逻辑性检测页的 LLM 语义复核（只读，不生成报告，不改写原文）。

与规则检测互补：
- 规则查错别字词表、标点、段内总数、年份、A级/报废跨章矛盾；
- LLM 补查错别字/用词、语句不通顺、同章数字前后矛盾、跨章数字不一致。

安全约束（与项目红线一致）：
- 模型不写正文、不改数字、不补结论；
- 每条发现必须给出原文完整摘录，摘录在原文中找不到就丢弃（防幻觉）；
- 没有 DEEPSEEK_API_KEY 或调用失败时静默降级，规则结果不受影响；
- 门控：环境变量 LOGIC_LLM_GATE=0 关闭；单测默认关闭。

后期本地部署：改 .env 的 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL 即可，无需改本模块。
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from typing import Any, Callable

_FLAG: ContextVar[bool | None] = ContextVar("logic_llm_gate", default=None)

# LLM 只许报这几类；severe/year 由规则口径负责，不让模型下结论。
_KIND_LABEL = {
    "typo": "错别字",
    "language": "语言不通顺",
    "logic": "计算错误",
    "punct": "标点错误",
}

_CHAPTER_LINE = re.compile(r"第\s*(\d{1,2})\s*章")
_LINE_NOUN = re.compile(r"(\d{1,2})\s*号线")

# 模型有时会把「核对一致」的验证说明也放进 findings（如「应为8年，与计算一致」）。
# 先识别确凿的错误信号；无错误信号且结论为「一致/无矛盾/正确」的条目一律丢弃。
_ERROR_RE = re.compile(
    r"不一致|不符合|不相符|不吻合|不符|对不上|存在(?:明显)?(?:矛盾|差异|出入|错误)"
    r"|相差|多算|少算|多计|少计|多了|少了|有误|错误|矛盾"
    r"|应为[^。；]{0,24}(?:但|而|却|原文|实际|写成|写的)"
)
# 模型明确给出「不是问题」的最终结论（即使中途提到了不一致等字样，也整条丢弃）。
_NON_ISSUE_PATTERN = re.compile(
    r"不构成[^。；]{0,8}矛盾|未发现[^。；]{0,10}矛盾|不存在[^。；]{0,10}矛盾"
    r"|不属于跨章核对|无直接可比性|无矛盾|没有矛盾|不矛盾"
    r"|无确凿依据[^。；]{0,4}不报|暂不列为|不列为[^。；]{0,6}问题"
    r"|非错别字|用字正确|属格式问题|无问题|没有问题"
)
# logic（计算错误）类只收确凿结论；「疑似/易造成/需核对」属猜测性提示，不当作错误。
_SPECULATIVE_RE = re.compile(r"疑似|易造成|需核对|待核实")
# 「起始年月—至今已使用X年」的年限算术：统计基准日（上年末/评估年）与月份取整
# 规则不在模型侧，机械做年份差必然误报，一律过滤。
_YEAR_SPAN_RE = re.compile(r"(?:至|—|–)\s*(?:评估年)?\s*20\d{2}\s*年[^。；]{0,12}(?:为|约|是)\s*\d+\s*年")
_USAGE_RE = re.compile(r"(?:至今|实际)(?:已)?使用\s*\d+\s*年")
# 同章内多个报废汇总句（不同批次、不同原值、不同安装年份）的数量对比，不属矛盾。
_BATCH_SCRAP_RE = re.compile(r"报废|需报废")
_OTHER_PLACE_RE = re.compile(r"另一处|同章|两处|一处[^。；]{0,12}(?:台|合计)|后文|前文")
_QTY_RE = re.compile(r"\d+\s*台")
_OK_RE = re.compile(
    r"一致|无矛盾|没有矛盾|相符|吻合|无误|正确|未见异常|没有问题|无问题|准确"
)

# 模型自我否决：算了一通后结论是「不报告/不在核对范围」，这类说明一律不展示
_NO_REPORT_RE = re.compile(
    r"不在本次核对|不在核对范围|不属本次核对|不属于本次|不纳入本次|不做核对|不进行核对"
    r"|超出核对范围|无需报告|不需报告|不报告|不予以?报告|不列出|不作为(?:错误|问题)"
)
# 纯排版/格式指责：逻辑检测在解析后的纯文本上进行，不查段落划分、标题排版、项目符号
_FORMAT_RE = re.compile(
    r"未另起段|另起段|未分段|没有分段|需要分段|应分段|未单独成段|单独成段|换行"
    r"|混排|段落划分|段落格式|排版|格式不当|格式问题|格式不规范|格式/语句|衔接不当"
    r"|标题与正文|与正文混排|项目符号|缩进|顶格|紧接[^。；]{0,10}句末"
)
# language 类二选一/不确定诊断（如「缺改造或的」），没有确定结论不报
_VAGUE_RE = re.compile(
    r"缺[^。；，,]{0,6}或|应(?:为|补|改|删|加|删除)[^。；，,]{0,6}或"
    r"|可能(?:缺|为|是|漏)|抑或"
)
# 模型自套未规定的趋势/同比/环比公式算出「不一致」：业务口径不在模型侧，过滤
_TREND_TOPIC_RE = re.compile(r"趋势|同比|环比|增长率|增幅|降幅|均值变化|平均变化")
_TREND_CALC_RE = re.compile(r"[（(][^）)]*[0-9][^）)]*[)）][^。；]{0,12}(?:≈|=|＝|计算得|算出)")
# 占比四舍五入/截断造成的 0.0X 个百分点差异（报告中常见，非计算错误）
_ROUNDING_NOISE_RE = re.compile(
    r"舍入[^。；]{0,14}0\.0\d\s*个百分点|0\.0\d\s*个百分点[^。；]{0,14}舍入"
)
# 百分比相加后与 100% 仅差 0.01~0.02 个百分点（如 92.06%+7.93%=99.99%）
_PCT_SUM_RE = re.compile(
    r"((?:\d+\.\d{1,2}\s*%\s*[+＋]\s*)+\d+\.\d{1,2}\s*%)\s*[=＝]\s*(\d+\.\d{1,2})\s*%"
)
# 分数验算 a/b=X% 与其后原文 Y% 对比（如 15/189=7.94%，原文 7.93%）
_PCT_DIV_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*[=＝]\s*(\d+\.\d{1,2})\s*%")
# 整数数量层面的错误结论（用于舍入保护：整数统计真错了则不视为舍入噪音）
_INT_CONFLICT_RE = re.compile(
    r"不一致|不符合|不相符|不吻合|不符|对不上|相差|多算|少算|多计|少计|多了|少了|有误|错误|矛盾|缺少|不等于"
)


def _is_rounding_noise_note(note: str) -> bool:
    """百分比占比因四舍五入/截断产生的 0.01~0.02 个百分点差异，不属计算错误。

    两类典型：
    1. 占比相加 92.06%+7.93%=99.99%，模型称「不等于 100%」；
    2. 模型自算 15/189=7.94%，原文写 7.93%（截断），称「不符」。
    保护：不含 % 的分句里若出现整数数量矛盾，不判为噪音。
    """
    t = str(note or "")
    if "%" not in t:
        return False
    hit = False
    for m in _PCT_SUM_RE.finditer(t):
        terms = [float(x) for x in re.findall(r"(\d+\.\d{1,2})\s*%", m.group(1))]
        rhs = float(m.group(2))
        if terms and abs(sum(terms) - rhs) <= 0.02 and abs(rhs - 100.0) <= 0.02:
            hit = True
            break
    if not hit:
        for m in _PCT_DIV_RE.finditer(t):
            calc = float(m.group(3))
            window = t[m.end() : m.end() + 80]
            for y in re.finditer(r"(\d+\.\d{1,2})\s*%", window):
                if abs(calc - float(y.group(1))) <= 0.02:
                    hit = True
                    break
            if hit:
                break
    if not hit:
        return False
    # 保护：不含 % 的分句里不得有整数数量矛盾结论
    for seg in re.split(r"[；;。！？，,、（）()]", t):
        if seg.strip() and "%" not in seg and _INT_CONFLICT_RE.search(seg):
            return False
    return True
# 模型自行假设的推算（「若…各N次/假设…/按…计算」），并非原文给出的数字关系
_HYPOTHETICAL_RE = re.compile(r"若[^。；]{0,24}(?:各|每)\s*\d|假设[^。；]{0,24}计算|若按[^。；]{0,20}(?:计算|推算|口径)")


def _is_non_issue_note(note: str, kind: str = "") -> bool:
    """判断 note 是否为「核对一致、无问题」的结论性说明（是则丢弃，不当作错误）。"""
    t = str(note or "")
    if _NON_ISSUE_PATTERN.search(t):
        return True
    if str(kind).lower() == "logic":
        if _SPECULATIVE_RE.search(t):
            return True
        if _YEAR_SPAN_RE.search(t) and _USAGE_RE.search(t):
            return True
        if _BATCH_SCRAP_RE.search(t) and _OTHER_PLACE_RE.search(t) and _QTY_RE.search(t):
            return True
    # 「无矛盾」「没有矛盾」含「矛盾」二字，先摘出再判错误信号
    guard = t.replace("无矛盾", "").replace("没有矛盾", "").replace("不矛盾", "")
    if _ERROR_RE.search(guard):
        return False
    return bool(_OK_RE.search(t))


def _is_llm_false_positive(note: str, kind: str = "") -> bool:
    """逻辑检测页 LLM 提示的确定性误报过滤（规则外、不可靠的结论）。"""
    t = str(note or "")
    k = str(kind or "").lower()
    # 核对一致 / 无问题
    if _is_non_issue_note(t, k):
        return True
    # 模型自己声明不报告 / 不在核对范围
    if _NO_REPORT_RE.search(t):
        return True
    # 纯排版/分段/标题格式问题（逻辑检测不查版式）
    if k in {"language", "punct"} and _FORMAT_RE.search(t):
        return True
    # language 二选一/不确定诊断
    if k == "language" and _VAGUE_RE.search(t):
        return True
    # 自定趋势/同比/环比公式算出的不一致（口径不在模型侧）
    if k in {"logic", "language"} and _TREND_TOPIC_RE.search(t) and _TREND_CALC_RE.search(t):
        return True
    # 占比舍入仅 0.0X 个百分点的噪音
    if k in {"logic", "language"} and (
        _ROUNDING_NOISE_RE.search(t) or _is_rounding_noise_note(t)
    ):
        return True
    # 模型自行假设的推算（非原文数字关系）
    if k == "logic" and _HYPOTHETICAL_RE.search(t):
        return True
    return False

_SINGLE_CHUNK_LIMIT = 6000   # 单章给模型的字符上限
_CROSS_CHAPTER_MAX = 140     # 跨章数字候选句总条数上限
_PER_CHAPTER_MAX = 20        # 每章候选句条数上限


def _key_available() -> bool:
    if str(os.getenv("DEEPSEEK_API_KEY") or "").strip():
        return True
    try:
        from engine.config import get_deepseek_config

        return bool((get_deepseek_config().get("api_key") or "").strip())
    except Exception:
        return False


def logic_llm_enabled() -> bool:
    """门控：环境变量显式关 → 关；ContextVar 显式设 → 按设置；否则看是否有 Key。"""
    if str(os.getenv("LOGIC_LLM_GATE") or "").strip().lower() in {"0", "false", "no"}:
        return False
    flag = _FLAG.get()
    if flag is False:
        return False
    if flag is True:
        return _key_available()
    return _key_available()


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _chat(system: str, user: str) -> dict[str, Any] | None:
    """调一次模型。任何失败返回 None，由调用方降级。"""
    try:
        from engine.llm_client import chat_json

        data = chat_json(system, user, temperature=0)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _excerpt_valid(excerpt: str, blob: str) -> bool:
    """摘录必须原样出现在原文里（去空白后包含），防模型编造。"""
    ex = _norm(excerpt)
    if len(ex) < 8:
        return False
    return ex in _norm(blob)


def _clean_findings(raw: list[Any], blob: str) -> list[dict[str, str]]:
    """校验模型返回：kind 白名单、摘录必须在原文、note 非空、结论为「一致/无矛盾」的丢弃、去重。"""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in _KIND_LABEL:
            continue
        excerpt = str(item.get("excerpt") or "").strip()
        note = str(item.get("note") or "").strip()
        if not _excerpt_valid(excerpt, blob) or not note:
            continue
        if _is_llm_false_positive(note, kind):
            continue
        key = (kind, _norm(excerpt))
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "excerpt": excerpt[:220], "note": note[:240]})
    return out


def _chapter_blob(units: list[dict[str, Any]], chapter_no: int) -> str:
    """单章可读文本：只取该章标题+段落，表格跳过（表格数字靠规则核对）。"""
    parts: list[str] = []
    for u in units:
        if u.get("kind") == "table":
            continue
        if u.get("chapter_no") != chapter_no:
            continue
        t = (u.get("text") or "").strip()
        if not t:
            continue
        parts.append(t)
    return "\n".join(parts)


def _hard_atoms(text: str, limit: int) -> list[str]:
    """超长句兜底：按逗号/顿号切，仍超长才硬切（报告中极少出现）。"""
    out: list[str] = []
    for sub in re.split(r"(?<=[，,、])", text):
        if not sub:
            continue
        if len(sub) <= limit:
            out.append(sub)
        else:
            for i in range(0, len(sub), limit):
                out.append(sub[i : i + limit])
    return out


def _chunk_blob(blob: str, limit: int = _SINGLE_CHUNK_LIMIT) -> list[str]:
    """把单章文本切成不超过 limit 的完整块，只在段落/句子/逗号边界切。

    不在词或句子中间截断，避免把「更新改造项目」切成「更新改造项」使模型误判缺字；
    长章分块后可覆盖全文，而非只查前 limit 字。
    """
    blob = blob or ""
    if len(blob) <= limit:
        return [blob] if blob.strip() else []
    atoms: list[str] = []
    for para in blob.split("\n"):
        if len(para) <= limit:
            atoms.append(para)
        else:
            for sent in re.split(r"(?<=[。！？；!?])", para):
                if not sent:
                    continue
                if len(sent) <= limit:
                    atoms.append(sent)
                else:
                    atoms.extend(_hard_atoms(sent, limit))
    chunks: list[str] = []
    buf = ""
    for a in atoms:
        sep = "\n" if buf else ""
        if len(buf) + len(sep) + len(a) <= limit:
            buf += sep + a
        else:
            if buf:
                chunks.append(buf)
            buf = a
    if buf:
        chunks.append(buf)
    return [c for c in chunks if c.strip()]

def _review_chapter(
    chapter_no: int,
    blob: str,
    *,
    domain_label: str,
    year: int | None,
) -> list[dict[str, str]]:
    """单章一次调用：错别字/用词/语句/同章数字矛盾。"""
    sys = (
        f"你是上海轨道交通{domain_label}年报审稿人。只做只读审查，禁止改写原文、禁止补充原文没有的内容。"
        "下面是年报某章正文片段（段落与标题，表格已省略）。"
        "只报告确有依据的问题："
        "1. 错别字、明显用词不当（kind=typo）；但线路区段名「北北延伸、北延伸、南延伸、"
        "西西延伸、东延伸、西延伸、三期东延伸、三期南延伸」是固定专有名称，"
        "其中「北北延伸」「西西延伸」表示延伸方向的层级，并非多写/叠字，禁止报告；"
        "2. 语句不通顺、句子残破、明显缺字（kind=language）；必须指出唯一确定的错误字和唯一改法，"
        "若属于「缺A或B」等多种改法、无法确定的猜测，不要报告；"
        "「北北延伸」「北延伸」「南延伸」「东延伸」「西延伸」等区段小标题（可带✓或冒号），即使紧跟在句末或单独成行，也不是语病，不要报；"
        "段落是否另起、是否换行、标题与正文是否混排、项目符号、缩进、顶格等排版格式问题一律不查、不报；"
        "并列统计句中分号后的「序号+设备名」（如「开关柜故障1项；4电力监控系统故障16项」），数字是列举编号而非数量，不缺量词，不要报缺字；"
        "3. 同章内数字前后矛盾，如总数与分项不符、同一指标两处数字不同（kind=logic）；"
        "但以下情形不得报告：①「开始使用年月—至今已使用X年/实际使用X年」的年限算术"
        "（统计基准日与月份取整规则不在本次核对范围，禁止做年份差推算）；"
        "②同一线路存在多个报废设备汇总句时，各句对应不同批次、不同原值、不同安装年份的设备，"
        "数量不同不属矛盾，只有同一句内总数与分项相加不符才算错误；"
        "③严禁自行套用趋势、同比、环比、增长率、均值变化等业务公式去复算：原文未给出公式，"
        "你的口径与报告编制口径可能不同，复算不符即误报；只核对原文明确写出算式、可直接代入验证的数字关系；"
        "4. 明显标点错误，如连续分号、半角标点误用、完整句末缺标点（kind=punct）。"
        "培训/规程/修订清单条目（如「1、2025.5《…》培训」「——新增…」「⑤…规程」）、"
        "图表数据与公式（如「故障设备趋势=-14.0%」「前三年设备故障均值28 22 27」）、"
        "表题图题（如「表格10-2…」「图8-8…」）、完整句后的括号备注（如「…。（设备处于D）」）"
        "都不是完整句，不要求句末标点，禁止报告；"
        "不要报告：目录条目、页码、正常的历史年份描述、没有确凿证据的怀疑，"
        "以及结论为「不报告/不在核对范围/不属本次核对」的条目——这类结论直接不要输出。"
        "核对一致、计算正确、没有问题的内容一律不得输出，"
        "禁止输出「应为X年，与计算一致」这类验证说明（即使它是正确的核对结论）。"
        "每条必须给出原文中完整出现的摘录 excerpt（照抄原文，不得改写）。"
        '只返回 JSON：{"findings":[{"kind":"typo|language|logic|punct","excerpt":"...","note":"..."}]}。'
        "没发现问题返回 {\"findings\":[]}。"
    )
    head = f"第{chapter_no}章"
    if year:
        head += f"（评估年{year}年）"
    data = _chat(sys, f"{head}：\n{blob}")
    if data is None:
        return []
    return _clean_findings(data.get("findings"), blob)


def _candidate_sentences(units: list[dict[str, Any]]) -> list[tuple[int | None, str]]:
    """跨章数字核对候选句：带线路名或长数字的非表格句，按章限量。"""
    per: dict[int | None, list[tuple[int | None, str]]] = {}
    for u in units:
        if u.get("kind") == "table":
            continue
        t = (u.get("text") or "").strip()
        if len(t) < 12 or len(t) > 400:
            continue
        if not _LINE_NOUN.search(t) and not re.search(r"\d{2,}", t):
            continue
        no = u.get("chapter_no")
        per.setdefault(no, []).append((no, t))
    out: list[tuple[int | None, str]] = []
    for no in sorted(per, key=lambda x: (x is None, x or 0)):
        for item in per[no][:_PER_CHAPTER_MAX]:
            out.append(item)
        if len(out) >= _CROSS_CHAPTER_MAX:
            break
    return out


def _review_cross_chapter(
    candidates: list[tuple[int | None, str]],
    *,
    domain_label: str,
) -> list[dict[str, str]]:
    """跨章一次调用：同一线路/设备在不同章数字明显不一致。"""
    lines = [f"[第{no}章] {t}" if no else f"[未知章] {t}" for no, t in candidates]
    blob = "\n".join(lines)
    sys = (
        f"你是上海轨道交通{domain_label}年报审稿人。只做只读审查。"
        "下面是年报第3～11章中涉及线路或设备的句子（已标注章号）。"
        "请找出同一线路或同一设备在不同章节里数字明显不一致的矛盾，"
        "如第4章某线故障5起、第8章同一线写成12起；设备台数、完成率等对不上。"
        "只比较不同章节之间的同一指标；单句内部的「起始年份—使用年限」算术核对"
        "（如「2017年开始使用，至今已使用8年」）不属于跨章核对，无论算对算错都不要报告。"
        "同章内（尤其第11章）同一线路出现多个报废汇总句、数量不同，通常是不同批次、"
        "不同原值的设备，不属跨章矛盾，不要报告。"
        "不要自行套用趋势、同比、环比、增长率、均值变化等业务公式复算；结论为「不报告/不在核对范围」的条目不要输出。"
        "没有确凿矛盾的不要报；核对一致、计算正确、无矛盾的内容一律不得输出，"
        "禁止输出「应为X年，与计算一致」「无矛盾」「不构成矛盾」「不属于跨章核对」这类验证说明。"
        "每条必须给出原文中完整出现的摘录 excerpt（照抄原文）。"
        '只返回 JSON：{"findings":[{"kind":"logic","excerpt":"...","note":"..."}]}。'
        "没发现问题返回 {\"findings\":[]}。"
    )
    data = _chat(sys, blob)
    if data is None:
        return []
    return _clean_findings(data.get("findings"), blob)


def _is_skippable(unit: dict[str, Any]) -> bool:
    """标题、目录、空块不送给模型。"""
    if unit.get("kind") == "table":
        return True
    t = (unit.get("text") or "").strip()
    if not t or len(t) < 8:
        return True
    if _CHAPTER_LINE.match(t):
        return True
    return False


def llm_review_units(
    units: list[dict[str, Any]],
    *,
    domain_id: str = "power_supply",
    mode: str = "full",
    chapter_id: str = "",
    year: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """对已标注章号的 units 做 LLM 语义复核。

    返回 (findings, used)。findings 结构：
    {"kind", "chapter_no"|None, "excerpt", "note"}；跨章矛盾 chapter_no=None。
    未启用/无 Key/失败时返回 ([], False)，不抛异常。

    on_progress(done, total)：每完成一个分块任务回调一次，用于真实进度展示；
    回调内异常不得影响检测。
    """
    if not logic_llm_enabled():
        return [], False
    usable = [u for u in units if not _is_skippable(u)]
    if len(usable) < 3:
        return [], False
    domain_label = "接触网" if (domain_id or "").strip().lower() == "overhead" else "供电"
    findings: list[dict[str, str]] = []
    tasks: list[tuple[str, Any]] = []

    if (mode or "full") == "chapter":
        no = None
        m = re.search(r"(\d{1,2})", chapter_id or "")
        if m:
            no = int(m.group(1))
        if no:
            blob = _chapter_blob(units, no)
            for chunk in _chunk_blob(blob):
                if len(_norm(chunk)) >= 200:
                    tasks.append(("single", (no, chunk)))
    else:
        by_no: dict[int, str] = {}
        for u in units:
            c = u.get("chapter_no")
            if c is None or not isinstance(c, int) or c not in range(3, 12):
                continue
            blob = _chapter_blob([u], c)
            if blob.strip():
                by_no[c] = by_no.get(c, "") + "\n" + blob
        for no, blob in by_no.items():
            if len(_norm(blob)) >= 200:
                for chunk in _chunk_blob(blob):
                    if len(_norm(chunk)) >= 200:
                        tasks.append(("single", (no, chunk)))
        candidates = _candidate_sentences(units)
        if len(candidates) >= 2:
            tasks.append(("cross", candidates))

    if not tasks:
        return [], False

    def _run(task: tuple[str, Any]) -> list[dict[str, str]]:
        kind, payload = task
        if kind == "single":
            no, blob = payload
            items = _review_chapter(no, blob, domain_label=domain_label, year=year)
            for it in items:
                it["chapter_no"] = no
            return items
        return _review_cross_chapter(payload, domain_label=domain_label)

    used = False
    total_tasks = len(tasks)
    done_tasks = 0

    def _report_progress() -> None:
        if on_progress is None:
            return
        try:
            on_progress(done_tasks, total_tasks)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=min(3, total_tasks)) as pool:
        futs = {pool.submit(_run, task): task for task in tasks}
        for fut in as_completed(futs):
            used = True
            done_tasks += 1
            _report_progress()
            try:
                findings.extend(fut.result())
            except Exception:
                continue
    return findings, used
def llm_resolve_chapters(
    units: list[dict[str, Any]],
    chapter_map: dict[int, dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """LLM 兜底章标题识别：规则未定位的章，让模型从候选短行中选择。

    返回 {章号: 定位信息}；门控关闭、无候选、调用失败、交叉校验不通过均返回 {}。
    交叉校验：只填补缺失章、核心词不冲突、位置严格落在相邻已定位章之间。
    """
    # 延迟导入避免循环依赖
    from chapters.common.logic_page_check import chapter_no_by_name

    if not logic_llm_enabled() or not candidates:
        return {}
    missing = [n for n in range(3, 12) if n not in chapter_map]
    if not missing:
        return {}
    lines = [f"[{k}] {(c.get('text') or '').strip()[:60]}" for k, c in enumerate(candidates)]
    known_text = "；".join(
        f"第{n}章(候选行序号前的文档位置约{info.get('unit_idx')})" for n, info in sorted(chapter_map.items())
    ) or "无"
    sys = (
        "你在处理上海轨道交通年度评估报告的章标题定位。规则识别可能漏掉两类章标题："
        "①章名后带括号备注（如「（待更新）」「（内容与标题不符）」）；②章标题被排成了正文样式。"
        "下面给出文档中按出现顺序排列的疑似标题行（每行以[序号]开头），以及规则已定位的章。"
        "请判断候选行中哪些是第3～11章中【缺失章】的章标题。各章章名含义："
        "第3章设备功能有效性、第4章运营契合满足度、第5章管理体系合规性、第6章修程修制匹配性、"
        "第7章运维表现健康度、第8章风险隐患闭环度、第9章备件物资保障度、第10章使用环境符合性、"
        "第11章退运报废倾向性。章标题是一行短标题（章名后可带括号备注），必须严格按章号递增、"
        "位于相邻已定位章之间；节标题（如3.1、设备维护周期）、目录条目、正文句子都不是章标题。"
        '只返回 JSON：{"assign":[{"no":章号,"cand":候选序号}]}，没有把握的章不要返回。'
    )
    user = (
        f"规则已定位：{known_text}\n"
        f"待补章号：{missing}\n"
        f"候选行（按文档顺序）：\n" + "\n".join(lines)
    )
    data = _chat(sys, user)
    if not data or not isinstance(data.get("assign"), list):
        return {}
    known_pos = {n: info["unit_idx"] for n, info in chapter_map.items()}
    picked: list[tuple[int, int]] = []
    used_cand: set[int] = set()
    for item in data["assign"]:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
            ci = int(item.get("cand"))
        except (TypeError, ValueError):
            continue
        if no not in missing or not (0 <= ci < len(candidates)) or ci in used_cand:
            continue
        text = (candidates[ci].get("text") or "").strip()
        # 核心词交叉校验：该行若含某章核心词，必须与 LLM 判定章号一致
        name_no = chapter_no_by_name(text)
        if name_no is not None and name_no != no:
            continue
        unit_idx = candidates[ci]["unit_idx"]
        lower = [p for n, p in known_pos.items() if n < no]
        upper = [p for n, p in known_pos.items() if n > no]
        if lower and unit_idx <= max(lower):
            continue
        if upper and unit_idx >= min(upper):
            continue
        used_cand.add(ci)
        picked.append((no, unit_idx))
    # 补入的章之间也要严格递增
    picked.sort(key=lambda x: x[0])
    out: dict[int, dict[str, Any]] = {}
    last_pos = max((p for n, p in known_pos.items() if n < min(missing)), default=-1)
    for no, unit_idx in picked:
        if unit_idx <= last_pos:
            continue
        last_pos = unit_idx
        out[no] = {
            "no": no,
            "unit_idx": unit_idx,
            "score": 35,
            "via": "LLM语义兜底",
            "confidence": "low",
            "source": "llm",
        }
    return out
