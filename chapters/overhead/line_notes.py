# -*- coding: utf-8 -*-
"""表后按线路说明：材料里常为「N号线：」单独一段 + 后接多段正文；较新文件覆盖较旧。"""
from __future__ import annotations

import re
from typing import Any

from chapters.common.section_slice import compact_text
from parsers.document_model import DocumentModel

_LINE_LEAD = re.compile(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]?\s*(.*)$", re.DOTALL)
_LINE_ONLY = re.compile(r"^(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)\s*[：:]?\s*$")
_QIZHONG = re.compile(r"^其中\s*[：:]?\s*(.*)$", re.S)
_INLINE_LINE = re.compile(
    r"(?<=[。；;])\s*(?=(?:轨道交通)?\d{1,2}\s*(?:号线|线路))"
)
_CLUSTER_CLOSE_HEAD = re.compile(
    r"^上述[CD、,和与/／\s]{0,12}状态的?(?:区间|区段)"
)
_CLUSTER_CLOSE_SPLIT = re.compile(
    r"(?<=[。；;])\s*(?=上述[CD、,和与/／\s]{0,12}状态的?(?:区间|区段))"
)
_KIND_TARGET = {
    "各线路柔性接触网状态分布": "柔",
    "各线路刚性接触网状态分布": "刚",
    "各线路隔离开关状态分布": "开",
    "各线路隔离开关控制屏状态分布": "屏",
    "接触轨状态分布": "轨",
}
_CTRL_LEAD = re.compile(
    r"^(管控策略|集中修|大修更新|大修安排|大修需求|专项|差异化|禁停区|现有风险|条运维|管控措施|备品备件)"
)
_SEGMENT_LABEL = re.compile(
    r"^(?:正线|南延伸|北延伸|北北延伸|东延伸|西延伸|西西延伸|"
    r"接触网状态|设备状态|"
    r"其中)\s*[：:]?\s*$"
)
_KIND_HEADER_ONLY = re.compile(
    r"^(?:柔性接触网|刚性接触网|柔性|刚性|接触轨|"
    r"隔离开关控制屏|隔离开关)\s*[：:]?\s*$"
)
_CD_MARKS = (
    "C状态的区段",
    "D状态的区段",
    "C状态区段",
    "D状态区段",
    "没有C和D",
    "无C、D状态",
    "无C和D状态",
    "C、D状态区段无",
    "维持现有管控",
)
_CD_LIST_RE = re.compile(r"C状态的区段是|C状态区段为|C状态的区段有|C状态区段是")
_D_LIST_RE = re.compile(
    r"D状态的区段是|D状态区段为|D状态的区段有|D状态区段是|D状态的区段的区段"
)


def _norm_line_key(n: int | str) -> str:
    return str(int(n))


def is_segment_label(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    rest = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", t).strip()
    return bool(_SEGMENT_LABEL.match(rest or t))


def ensure_line_lead(key: str, text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return t
    if _LINE_LEAD.match(t):
        return t
    return f"{int(key)}号线：{t}"


def _note_rest(text: str) -> str:
    t = str(text or "").strip()
    return re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", t).strip()


def is_status_inline_diff_para(text: str) -> bool:
    """C/D 分布句后的「差异化管控是」，仍算 3.3 表后说明，不是 3.4 专节。"""
    rest = _note_rest(text)
    c = compact_text(rest)
    if c.startswith("差异化管控是"):
        return True
    return "差异化管控是" in compact_text(text) and note_has_cd_status(text)


def peel_trailing_ctrl_lead(text: str) -> tuple[str, bool]:
    """状态句末尾粘着的「管控策略包括：」揭掉，后面按 3.4 专节处理。"""
    t = str(text or "").rstrip()
    n = re.sub(r"[，,。；;]?\s*管控策略包括[：:。.]?\s*$", "", t)
    n = n.strip()
    return n, n != t.strip()


def is_control_section_para(text: str) -> bool:
    """3.4 各线路管控措施段落，不能写进 3.3 状态分布表后。"""
    t = str(text or "").strip()
    if not t or is_status_inline_diff_para(t):
        return False
    rest = _note_rest(t)
    if _CTRL_LEAD.match(t) or _CTRL_LEAD.match(rest) or compact_text(rest).startswith("管控"):
        return True
    return bool(re.match(r"^\d+[、.．)）]\s*(集中修|大修|专项|差异化|备品|管控)", rest))


def is_overhaul_progress_para(text: str) -> bool:
    """没有 C/D 分布、只报大修进度的句子，属于 3.4。"""
    t = str(text or "").strip()
    if not t or note_has_cd_status(t) or note_asserts_no_cd(t) or is_status_inline_diff_para(t):
        return False
    if is_control_section_para(t):
        return False
    c = compact_text(_note_rest(t))
    if "已纳入" in c and "大修" in c:
        return True
    return "实施大修" in c and "更新改造" in c


def _skip_in_status_notes(text: str) -> bool:
    return is_control_section_para(text) or is_overhaul_progress_para(text)


def is_kind_header_only(text: str) -> bool:
    """「柔性接触网：」这类小节标题要留给分种切片，成文时不再单独成段。"""
    t = str(text or "").strip()
    if not t:
        return False
    rest = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", t).strip()
    return bool(_KIND_HEADER_ONLY.match(rest or t))


def note_has_cd_status(text: str) -> bool:
    c = compact_text(text)
    return any(k in c for k in _CD_MARKS)


def note_asserts_no_cd(text: str) -> bool:
    c = compact_text(text)
    return any(
        k in c
        for k in (
            "没有C和D",
            "无C和D",
            "无C、D",
            "C、D状态区段无",
            "C、D状态的区段无",
            "C、D状态区段无",
        )
    )


def note_asserts_no_d(text: str) -> bool:
    """材料或成文已写明没有 D（含「没有C和D」）。"""
    if note_asserts_no_cd(text):
        return True
    c = compact_text(text)
    return bool(re.search(r"(没有|无)D(状态|类)|D状态的区段无|无D状态区段", c))


def note_asserts_no_c(text: str) -> bool:
    """材料或成文已写明没有 C（含「没有C和D」）。"""
    if note_asserts_no_cd(text):
        return True
    c = compact_text(text)
    return bool(re.search(r"(没有|无)C(状态|类)|C状态的区段无|无C状态区段", c))


def note_lists_positive_c(text: str) -> bool:
    c = compact_text(text)
    if "没有C" in c or "无C" in c:
        return False
    return bool(_CD_LIST_RE.search(c))


def note_lists_positive_d(text: str) -> bool:
    c = compact_text(text)
    if note_asserts_no_d(text) and not _D_LIST_RE.search(c):
        return False
    return bool(_D_LIST_RE.search(c))


def is_risk_dump_para(text: str) -> bool:
    """部门稿里的「主要风险点 / 子系统状态」长文，不是状态表后的 C/D 说明。"""
    c = compact_text(text)
    return (
        c.startswith("主要风险点")
        or "触网子系统和设备状态" in c
        or c.startswith("正线触网子系统")
        or c.startswith("北延伸触网子系统")
    )


def row_grade_count_nonzero(row: list[str] | None, grade: str) -> bool:
    """状态分布表 A/B/C/D「个数」列（第 3/5/7/9 列，0 起算 2/4/6/8）是否有正数。"""
    idx = {"A": 2, "B": 4, "C": 6, "D": 8}.get(str(grade or "").upper())
    if idx is None or not row or len(row) <= idx:
        return False
    return not _cell_is_zeroish(row[idx])


def row_cd_nonzero(row: list[str] | None) -> bool:
    """状态分布表 C/D「个数」列（第 7、9 列，0 起算 6、8）是否有正数。"""
    return row_grade_count_nonzero(row, "C") or row_grade_count_nonzero(row, "D")


def _end_sentence(text: str) -> str:
    t = str(text or "").rstrip()
    if t and t[-1] not in "。；;！":
        t += "。"
    return t


def negative_cd_sentences(text: str) -> list[str]:
    """抽出「没有C/D状态的区段」一类结论句，供折叠/合并时回贴。"""
    out: list[str] = []
    seen: set[str] = set()
    for bit in re.split(r"(?<=[。；;])", str(text or "")):
        raw = bit.strip()
        if not raw:
            continue
        if note_lists_positive_c(raw) and not note_asserts_no_d(raw) and not note_asserts_no_cd(raw):
            continue
        if not (note_asserts_no_cd(raw) or note_asserts_no_d(raw) or note_asserts_no_c(raw)):
            continue
        sent = _end_sentence(raw)
        sig = compact_text(sent)
        if not sig or sig in seen:
            continue
        seen.add(sig)
        out.append(sent)
    return out


def attach_negative_cd_clauses(text: str, clauses: list[str]) -> str:
    """把「没有D/没有C」接到 C 状态清单句后；没有清单则接到段末。不重复已有结论。"""
    t = str(text or "").strip()
    blob = compact_text(t)
    pending: list[str] = []
    for cl in clauses:
        s = _end_sentence(str(cl or "").strip())
        if not s:
            continue
        if compact_text(s) in blob:
            continue
        if note_asserts_no_cd(s) and note_asserts_no_cd(t):
            continue
        if note_asserts_no_d(s) and (note_asserts_no_d(t) or note_lists_positive_d(t)):
            continue
        if note_asserts_no_c(s) and not note_asserts_no_d(s) and (
            note_asserts_no_c(t) or note_lists_positive_c(t)
        ):
            continue
        pending.append(s)
        blob += compact_text(s)
    if not pending:
        return t
    extra = "".join(pending)
    if not t:
        return extra
    paras = t.split("\n")
    for i, p in enumerate(paras):
        if _CD_LIST_RE.search(compact_text(p)):
            paras[i] = _end_sentence(p) + extra
            return "\n".join(paras)
    return _end_sentence(t) + extra


def ensure_table_negative_cd(text: str, line_no: int, *, c_pos: bool, d_pos: bool) -> str:
    """表上 C>0 且 D=0（或反过来）时，补「没有D/没有C」；不编造区段清单。"""
    t = str(text or "").strip()
    if not t or (not c_pos and not d_pos):
        return t
    clauses: list[str] = []
    n = int(line_no)
    if c_pos and not d_pos and not note_asserts_no_d(t):
        clauses.append(f"{n}号线没有D状态的区段。")
    if d_pos and not c_pos and not note_asserts_no_c(t):
        clauses.append(f"{n}号线没有C状态的区段。")
    return attach_negative_cd_clauses(t, clauses)


def _collapse_cd_lists(parts: list[str]) -> list[str]:
    """同一设备类型下多份「C状态区段是…」只留最长一条；柔/刚/开关分节后分别折叠。"""
    groups: list[list[str]] = []
    cur: list[str] = []
    for p in parts:
        if _note_header_kind(p) in {"柔", "刚", "开", "屏", "轨"}:
            if cur:
                groups.append(cur)
            cur = [p]
        else:
            cur.append(p)
    if cur:
        groups.append(cur)
    out: list[str] = []
    for g in groups:
        idxs = [i for i, x in enumerate(g) if _CD_LIST_RE.search(compact_text(x))]
        if len(idxs) <= 1:
            out.extend(g)
            continue
        best = max(idxs, key=lambda i: len(compact_text(g[i])))
        salvage: list[str] = []
        for i in idxs:
            if i == best:
                continue
            salvage.extend(negative_cd_sentences(g[i]))
        new_g = [x for i, x in enumerate(g) if i not in idxs or i == best]
        if salvage:
            for j, x in enumerate(new_g):
                if x is g[best]:
                    new_g[j] = attach_negative_cd_clauses(x, salvage)
                    break
        out.extend(new_g)
    return out


def _dedupe_repeated_clauses(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return ""
    bits = re.split(r"(?<=[。；;])", t)
    out: list[str] = []
    seen: set[str] = set()
    for bit in bits:
        c = compact_text(bit)
        if c and c in seen:
            continue
        if c:
            seen.add(c)
        out.append(bit)
    return "".join(out).strip()


def strip_commissioning_if_has_no_cd(text: str) -> str:
    """同一线既有「没有C和D」又有投运/评级长文时，只留 C/D 结论。"""
    t = str(text or "").strip()
    if not t or not note_asserts_no_cd(t):
        return t
    kept: list[str] = []
    for para in t.split("\n"):
        p = para.strip()
        if not p:
            continue
        c = compact_text(p)
        if note_asserts_no_cd(p) or note_has_cd_status(p):
            kept.append(p)
            continue
        if "投运" in c or "综合评级均为A" in c or ("运行状态良好" in c and "无专项" in c):
            continue
        if "备品备件储备缺口" in c or "PLC平替" in c:
            continue
        kept.append(p)
    return "\n".join(kept).strip() or t


def strip_positive_cd_lists(text: str) -> str:
    """本表 C/D 个数为 0 时，不写「C状态区段是…」清单（常是别的设备类型串台）。"""
    out_paras: list[str] = []
    for para in str(text or "").split("\n"):
        para = str(para or "").strip()
        if not para:
            continue
        kept_bits: list[str] = []
        for bit in re.split(r"(?<=[。；;])", para):
            c = compact_text(bit)
            if _CD_LIST_RE.search(c) and "没有C" not in c and "无C" not in c:
                continue
            kept_bits.append(bit)
        para_out = _dedupe_repeated_clauses("".join(kept_bits).strip())
        if para_out:
            out_paras.append(para_out)
    return "\n".join(out_paras).strip()


def _cell_is_zeroish(cell: str) -> bool:
    t = str(cell or "").strip().replace("％", "%").replace(",", "")
    if not t or t in {"/", "—", "-", "－", "无", "NA", "N/A"}:
        return True
    t = t.rstrip("%").strip()
    if not t:
        return True
    if t in {"0", "0.0", "0.00", "0.000"}:
        return True
    try:
        return abs(float(t)) < 1e-9
    except ValueError:
        return False


def row_all_zero_or_empty(row: list[str] | None) -> bool:
    """数据行除线路名外全是 0 / 0% / 空 → 不写表后说明、不标黄。"""
    if not row or len(row) < 2:
        return True
    for c in row[1:]:
        if not _cell_is_zeroish(c):
            return False
    return True


def _first_line_no(text: str) -> str | None:
    m = re.search(r"(?:轨道交通)?(\d{1,2})\s*(?:号线|线路)", str(text or ""))
    return m.group(1) if m else None


def explode_inline_line_leads(paragraphs: list[str]) -> list[str]:
    """「……。8号线……」拆成两段，避免后一线挤进前一段、丢掉段首缩进。

    「……为A；1号线南延伸……」仍是同一线续写，不能拆，否则接触网状态被切碎、后段顶格。
    """
    out: list[str] = []
    for raw in paragraphs:
        t = str(raw or "").strip()
        if not t:
            continue
        bits = [b.strip() for b in _INLINE_LINE.split(t) if b and b.strip()]
        if len(bits) <= 1:
            out.append(t)
            continue
        lead_n = _first_line_no(bits[0])
        buf = bits[0]
        for bit in bits[1:]:
            nxt = _first_line_no(bit)
            if nxt and nxt != lead_n:
                out.append(buf)
                buf = bit
                lead_n = nxt
            else:
                sep = "" if buf.endswith(("。", "；", ";", "，", "、")) else "；"
                buf = buf + sep + bit
        out.append(buf)
    return out


def is_cluster_closing_note(text: str) -> bool:
    """「上述D状态的区间，建议大修」是整张表的收束，不是某一线正文。"""
    t = str(text or "").strip()
    if not t:
        return False
    rest = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", t).strip()
    return bool(_CLUSTER_CLOSE_HEAD.match(rest or t))


def peel_cluster_closings(text: str) -> tuple[str, list[str]]:
    """把「上述C/D状态的区间…」从线路说明里剥离。"""
    t = str(text or "").strip()
    if not t:
        return "", []
    bits = [b.strip() for b in _CLUSTER_CLOSE_SPLIT.split(t) if b and b.strip()]
    if len(bits) <= 1:
        if is_cluster_closing_note(t):
            return "", [t]
        return t, []
    body: list[str] = []
    closings: list[str] = []
    for b in bits:
        if is_cluster_closing_note(b):
            closings.append(b)
        else:
            body.append(b)
    return "\n".join(body).strip(), closings


def explode_cluster_closings(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    for raw in paragraphs:
        t = str(raw or "").strip()
        if not t:
            continue
        body, closings = peel_cluster_closings(t)
        if body:
            out.append(body)
        out.extend(closings)
    return out


def _note_header_kind(text: str) -> str | None:
    """只认小节标题（柔性接触网：/C状态的刚性），正文里偶尔出现「隔离开关」「柔性」不当切节。"""
    t = str(text or "").strip()
    rest = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)", "", t).strip()
    rest = rest.lstrip("：:").strip()
    c = compact_text(rest or t)
    if (
        c.startswith("隔离开关控制屏")
        or rest.startswith("隔离开关控制屏")
        or "状态的隔离开关控制屏" in c[:28]
    ):
        return "屏"
    if (
        c.startswith("隔离开关")
        or rest.startswith("隔离开关")
        or ("状态的隔离开关" in c[:24] and "控制屏" not in c[:28])
    ):
        return "开"
    if c.startswith("接触轨") or rest.startswith("接触轨"):
        return "轨"
    if c.startswith("刚性") or rest.startswith("刚性") or "状态的刚性" in c[:24]:
        return "刚"
    if c.startswith("柔性") or rest.startswith("柔性") or "状态的柔性" in c[:24]:
        return "柔"
    if _CTRL_LEAD.match(t) or _CTRL_LEAD.match(rest) or c.startswith("管控"):
        return "管"
    return None


def _管_belongs(last_dev: str | None, target: str) -> bool:
    """柔/刚小节后面的集中修只属于该小节；开关/控制屏之后的总管控按关键词再分。"""
    if last_dev in {"柔", "刚"}:
        return last_dev == target
    return True


def _管控_keep(text: str, target: str) -> bool:
    c = compact_text(text)
    if target == "柔":
        if "刚性接触网" in c and "柔性" not in c:
            return False
        return "柔性" in c or "接触网" in c or "锚段" in c or "定位" in c or not any(
            k in c for k in ("隔离开关控制屏", "隔离开关")
        )
    if target == "刚":
        if "柔性接触网" in c and "刚性" not in c:
            return False
        return "刚性" in c or "接触网" in c or "锚段" in c or "定位" in c or not any(
            k in c for k in ("隔离开关控制屏", "隔离开关")
        )
    if target == "开":
        if "控制屏" in c[:24]:
            return False
        if "定位点" in c:
            return False
        return "隔离开关" in c
    if target == "屏":
        return "控制屏" in c
    if target == "轨":
        return "接触轨" in c
    return True


def slice_note_for_kind(text: str, kind: str) -> str:
    """维护五部把柔/刚/隔离开关写在同一线说明里：按表种只留对应小节。"""
    t = str(text or "").strip()
    if not t:
        return ""
    target = _KIND_TARGET.get(kind or "")
    if not target:
        return t
    parts = [p.strip() for p in t.split("\n") if p.strip()]
    typed = False
    cur: str | None = None
    out: list[str] = []
    preamble: list[str] = []
    skip_risk = False
    for p in parts:
        p_keep, started_ctrl = peel_trailing_ctrl_lead(p)
        if not p_keep and started_ctrl:
            cur = "管"
            continue
        h = _note_header_kind(p_keep or p)
        pc = compact_text(p)
        if is_risk_dump_para(p):
            skip_risk = True
            continue
        if skip_risk:
            if h in {"柔", "刚", "开", "屏", "轨", "管"}:
                skip_risk = False
            elif (
                re.match(r"^\d+[、.．)）]", p)
                or pc.startswith("北延伸触网")
                or pc.startswith("现有管控措施")
                or pc.startswith("后续的管控")
            ):
                continue
            else:
                skip_risk = False
        if h in {"柔", "刚", "开", "屏", "轨"}:
            typed = True
            cur = h
            if cur == target and p_keep and not _skip_in_status_notes(p_keep):
                out.append(p_keep)
            if started_ctrl:
                cur = "管"
            continue
        if is_status_inline_diff_para(p_keep or p):
            if cur is None:
                preamble.append(p_keep or p)
            elif cur == target:
                out.append(p_keep or p)
            continue
        if h == "管" or _skip_in_status_notes(p_keep or p) or started_ctrl:
            cur = "管"
            continue
        if cur == "管":
            continue
        if cur is None:
            if p_keep and not _skip_in_status_notes(p_keep):
                preamble.append(p_keep)
        elif cur == target:
            if p_keep and not _skip_in_status_notes(p_keep):
                out.append(p_keep)
        if started_ctrl:
            cur = "管"
    if not typed:
        blob = compact_text(t)
        cleaned = "\n".join(p for p in preamble if not _skip_in_status_notes(p)).strip()
        extra_ctrl = "\n".join(out).strip()
        if extra_ctrl:
            cleaned = f"{cleaned}\n{extra_ctrl}".strip() if cleaned else extra_ctrl
        if not cleaned:
            if is_risk_dump_para(t) or "主要风险点" in blob:
                return ""
            cleaned = "\n".join(
                p for p in parts if not _skip_in_status_notes(p) and not is_risk_dump_para(p)
            ).strip()
            if not cleaned:
                return ""
        if target == "刚" and "柔性段" in blob and "刚性" not in blob:
            return ""
        if target == "柔" and "刚性接触网" in blob and "柔性" not in blob:
            return ""
        if target == "轨":
            if "接触轨" in blob:
                return cleaned
            if any(k in blob for k in ("隔离开关", "控制屏", "柔性段")):
                return ""
            return cleaned if note_has_cd_status(cleaned) else ""
        if target in {"柔", "刚"}:
            return cleaned
        if target == "开":
            if "控制屏" in blob and "隔离开关" not in blob[:24]:
                return ""
            return cleaned
        if target == "屏":
            if "刚性接触网" in blob and "控制屏" not in blob:
                return ""
            if "控制屏" in blob or note_has_cd_status(cleaned):
                return cleaned
            return ""
        return ""
    if target in {"柔", "刚"}:
        extra: list[str] = []
        for p in preamble:
            c = compact_text(p)
            if target == "刚" and "柔性" in c and "刚性" not in c:
                continue
            if target == "柔" and "刚性" in c and "柔性" not in c:
                continue
            extra.append(p)
        out = extra + out
    return "\n".join(p for p in out if not _skip_in_status_notes(p)).strip()


def paragraphs_to_line_notes(paragraphs: list[str]) -> tuple[dict[str, str], list[str]]:
    """多段正文合并为「N号线：…」；返回 general 段（其中/无线路号）。"""
    by_line: dict[str, list[str]] = {}
    general: list[str] = []
    current: str | None = None
    seen_qizhong = False
    paragraphs = explode_cluster_closings(explode_inline_line_leads(paragraphs))

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        parts = [p for p in by_line.get(current, []) if p.strip()]
        by_line[current] = parts
        current = None

    for raw in paragraphs:
        t = str(raw or "").strip()
        if not t:
            continue
        if t.startswith("图") and len(t) < 48:
            flush()
            continue
        if t.startswith("表") and len(t) < 48:
            flush()
            continue
        if is_cluster_closing_note(t):
            flush()
            if compact_text(t) not in {compact_text(x) for x in general}:
                general.append(t)
            continue
        m = _LINE_LEAD.match(t)
        if m:
            flush()
            current = _norm_line_key(m.group(1))
            by_line.setdefault(current, [])
            rest = (m.group(2) or "").strip()
            if rest and not is_segment_label(rest):
                by_line[current].append(rest)
            continue
        if is_segment_label(t):
            continue
        m2 = _LINE_ONLY.match(t)
        if m2:
            flush()
            current = _norm_line_key(m2.group(1))
            by_line.setdefault(current, [])
            continue
        q = _QIZHONG.match(t)
        if q or t.rstrip("：:") == "其中":
            flush()
            seen_qizhong = True
            rest = (q.group(1) if q else "").strip()
            if rest and _LINE_LEAD.match(rest):
                mrest = _LINE_LEAD.match(rest)
                if mrest:
                    current = _norm_line_key(mrest.group(1))
                    by_line.setdefault(current, [])
                    tail = (mrest.group(2) or "").strip()
                    if tail:
                        by_line[current].append(tail)
            continue
        if current is not None:
            if is_segment_label(t):
                continue
            by_line[current].append(t)
            continue
        if seen_qizhong:
            continue
        general.append(t)

    flush()
    out: dict[str, str] = {}
    for k, parts in by_line.items():
        parts = _collapse_cd_lists([_dedupe_repeated_clauses(p) for p in parts if p.strip()])
        uniq: list[str] = []
        seen_p: set[str] = set()
        for p in parts:
            head, closings = peel_cluster_closings(p)
            for cl in closings:
                if compact_text(cl) not in {compact_text(x) for x in general}:
                    general.append(cl)
            p = head
            if not p:
                continue
            sig = compact_text(p)
            if sig and sig in seen_p:
                continue
            if sig:
                seen_p.add(sig)
            uniq.append(p)
        parts = uniq
        body = strip_commissioning_if_has_no_cd("\n".join(p for p in parts if p.strip()).strip())
        if not body:
            out[k] = f"{k}号线："
        elif "号线" in body.split("\n", 1)[0][:12]:
            out[k] = body
        else:
            out[k] = f"{k}号线：{body}"
    return out, general


def merge_line_notes(items: list[dict[str, Any]]) -> tuple[dict[str, str], list[str], list[str]]:
    """多份材料：较新优先；最新缺正文时保留其他材料表述。"""
    from chapters.overhead.material_merge import merge_line_notes_backfill

    by_line, general, warnings, _src = merge_line_notes_backfill(
        items, parse_paragraphs=paragraphs_to_line_notes
    )
    return by_line, general, warnings


def merge_line_notes_with_sources(
    items: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str], list[str], dict[str, str]]:
    from chapters.overhead.material_merge import (
        backfill_source_notes,
        merge_line_notes_backfill,
        newest_item,
    )

    by_line, general, warnings, line_src = merge_line_notes_backfill(
        items, parse_paragraphs=paragraphs_to_line_notes
    )
    primary = str((newest_item(items) or {}).get("_source") or (newest_item(items) or {}).get("source") or "")
    warnings.extend(backfill_source_notes(line_src, primary_source=primary))
    return by_line, general, warnings, line_src


_CTRL_PARA_START = re.compile(
    r"^(?:\d+[、.．)）]\s*)?(集中修|大修需求|大修安排|大修更新|禁停区|差异化管控|"
    r"专项更换|专项整治|现有风险点的管控|现有管控措施|管控策略)"
)


def has_ctrl_marker(text: str) -> bool:
    c = compact_text(text)
    return any(
        k in c
        for k in (
            "差异化管控",
            "管控策略包括",
            "集中修项目",
            "大修需求",
            "大修更新改造",
            "禁停区管理",
        )
    )


def status_note_suffix_from_note(text: str) -> str:
    """3.3 只补「差异化管控是」这类跟 C/D 分布绑在一起的句子，不把集中修专节补进去。"""
    t = str(text or "").strip()
    if not t:
        return ""
    parts = [p.strip() for p in t.split("\n") if p.strip()]
    out: list[str] = []
    for p in parts:
        if not is_status_inline_diff_para(p) and "差异化管控是" not in p:
            continue
        m = re.search(r"差异化管控是", p)
        if m and note_has_cd_status(p):
            chunk = p[m.start() :].strip()
            if chunk:
                out.append(chunk)
        else:
            out.append(p)
    return "\n".join(out).strip()


def ctrl_suffix_from_note(text: str) -> str:
    """3.4 补缺：从较旧说明抽出集中修/大修需求/差异化管控等段落。"""
    t = str(text or "").strip()
    if not t:
        return ""
    parts = [p.strip() for p in t.split("\n") if p.strip()]
    out: list[str] = []
    taking = False
    for p in parts:
        rest = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", p).strip()
        if not taking:
            m = re.search(r"差异化管控[是：:，,]", p)
            if m:
                chunk = p[m.start() :].strip()
                if chunk:
                    out.append(chunk)
                taking = True
            elif _CTRL_PARA_START.match(rest) or _CTRL_PARA_START.match(p) or _note_header_kind(p) == "管":
                out.append(p)
                taking = True
            continue
        h = _note_header_kind(p)
        if h in {"柔", "刚", "开", "屏", "轨"}:
            break
        out.append(p)
    return "\n".join(out).strip()


def note_has_body(text: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return False
    m = _LINE_LEAD.match(t)
    if m:
        return bool((m.group(2) or "").strip())
    if _LINE_ONLY.match(t):
        return False
    return len(t) > 6


def _data_start_row(rows: list[list[str]]) -> int:
    if len(rows) >= 2:
        r1 = "".join(str(c or "") for c in rows[1])
        if any(k in r1 for k in ("占比", "锚段数", "区段数", "数量")) and "号线" not in r1:
            return 2
    return 1


def _line_no_from_cell(cell: str) -> int | None:
    t = re.sub(r"\s+", "", str(cell or ""))
    m = re.search(r"(\d{1,2})号线", t)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 18 else None


def build_notes_flow_after_table(
    table_rows: list[list[str]] | None,
    line_notes: dict[str, str],
    general_notes: list[str] | None,
    *,
    prior_docs: list[DocumentModel] | None = None,
    expect_lines: list[int] | None = None,
    line_note_sources: dict[str, str] | None = None,
    primary_source: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    """按合并后的表行决定写哪些线路说明；缺材料且该行非全 0 则黄字占位。"""
    flow: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not table_rows:
        return flow, warnings

    start = _data_start_row(table_rows)
    table_line_nums: list[int] = []
    for row in table_rows[start:]:
        ln = _line_no_from_cell(str(row[0] if row else ""))
        if ln:
            table_line_nums.append(ln)

    order = sorted(set(table_line_nums))
    if expect_lines:
        rank = {n: i for i, n in enumerate(expect_lines)}
        order = sorted(order, key=lambda n: (rank.get(n, 999), n))

    trailing: list[str] = []
    trailing_seen = {compact_text(g) for g in (general_notes or []) if compact_text(g)}

    for ln in order:
        row = next(
            (r for r in table_rows[start:] if _line_no_from_cell(str(r[0] if r else "")) == ln),
            None,
        )
        if row is not None and row_all_zero_or_empty(row):
            continue
        key = _norm_line_key(ln)
        text = (line_notes.get(key) or "").strip()
        has_cd_cols = row is not None and len(row) >= 9
        if has_cd_cols and not row_cd_nonzero(row):
            text = strip_positive_cd_lists(text)
            if not note_asserts_no_cd(text) and not row_all_zero_or_empty(row):
                text = f"{ln}号线：没有C和D状态的区段，维持现有管控措施。"
        elif has_cd_cols and note_has_body(text):
            text = ensure_table_negative_cd(
                text,
                ln,
                c_pos=row_grade_count_nonzero(row, "C"),
                d_pos=row_grade_count_nonzero(row, "D"),
            )
        text, closings = peel_cluster_closings(text)
        for cl in closings:
            sig = compact_text(cl)
            if sig and sig not in trailing_seen:
                trailing_seen.add(sig)
                trailing.append(cl)
        if note_has_body(text):
            chunks = [
                p.strip()
                for p in text.split("\n")
                if p.strip() and not is_segment_label(p) and not is_kind_header_only(p)
            ]
            if chunks and not _LINE_LEAD.match(chunks[0]) and not is_segment_label(chunks[0]) and not is_kind_header_only(chunks[0]):
                chunks[0] = f"{ln}号线：{chunks[0]}"
            prev_sig = ""
            for chunk in chunks:
                if is_segment_label(chunk) or is_kind_header_only(chunk):
                    continue
                if is_control_section_para(chunk) or is_overhaul_progress_para(chunk):
                    continue
                body = re.sub(r"^(?:轨道交通)?\d{1,2}\s*(?:号线|线路)\s*[：:]?\s*", "", chunk).strip()
                if is_segment_label(body) or is_kind_header_only(body) or is_control_section_para(body) or is_overhaul_progress_para(body):
                    continue
                body, _ = peel_trailing_ctrl_lead(body)
                chunk, _ = peel_trailing_ctrl_lead(chunk)
                if not body or not chunk:
                    continue
                sig = compact_text(body or chunk)
                if sig and sig == prev_sig:
                    continue
                prev_sig = sig
                flow.append({"kind": "para", "text": chunk})
    for g in list(general_notes or []) + trailing:
        t = str(g or "").strip()
        if not t or _LINE_ONLY.match(t):
            continue
        flow.append({"kind": "para", "text": t})
    return flow, warnings
