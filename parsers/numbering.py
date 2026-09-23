# -*- coding: utf-8 -*-
"""把 Word 自动编号还原进段落文字，避免（1）（2）只在编号域里。"""
from __future__ import annotations

from docx.oxml.ns import qn

CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _val(el, attr: str = "val") -> str:
    if el is None:
        return ""
    return el.get(qn(f"w:{attr}")) or ""


def _format_num(fmt: str, n: int) -> str:
    if fmt == "bullet":
        return ""
    if fmt == "decimalEnclosedCircleChinese":
        return CIRCLES[n - 1] if 1 <= n <= 10 else str(n)
    if fmt == "decimalEnclosedCircle":
        return CIRCLES[n - 1] if 1 <= n <= len(CIRCLES) else str(n)
    if fmt == "lowerLetter" and 1 <= n <= 26:
        return chr(ord("a") + n - 1)
    if fmt == "upperLetter" and 1 <= n <= 26:
        return chr(ord("A") + n - 1)
    if fmt == "lowerRoman":
        return ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x")[n - 1] if 1 <= n <= 10 else str(n)
    if fmt == "upperRoman":
        return ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")[n - 1] if 1 <= n <= 10 else str(n)
    return str(n)


class NumberingReader:
    """读取 docx 的 numbering.xml，把（1）（2）① 等还原进段落文字。"""
    def __init__(self, doc) -> None:
        self.levels: dict[str, dict[int, dict[str, str]]] = {}
        self.counts: dict[str, dict[int, int]] = {}
        self._load(doc)

    @staticmethod
    def _numbering_part(doc):
        # python-docx 的 numbering_part 在文件没有 numbering.xml 时会 NotImplementedError
        rels = getattr(getattr(doc, "part", None), "rels", None)
        if rels is None:
            return None
        try:
            items = rels.values()
        except Exception:
            return None
        for rel in items:
            if "numbering" in (getattr(rel, "reltype", "") or ""):
                return getattr(rel, "target_part", None)
        return None

    def _load(self, doc) -> None:
        part = self._numbering_part(doc)
        if part is None:
            return
        root = part._element
        abstracts: dict[str, dict[int, dict[str, str]]] = {}
        for absn in root.findall(qn("w:abstractNum")):
            levels: dict[int, dict[str, str]] = {}
            for lvl in absn.findall(qn("w:lvl")):
                ilvl = int(_val(lvl, "ilvl") or 0)
                fmt_el = lvl.find(qn("w:numFmt"))
                text_el = lvl.find(qn("w:lvlText"))
                start_el = lvl.find(qn("w:start"))
                levels[ilvl] = {
                    "fmt": _val(fmt_el) or "decimal",
                    "text": _val(text_el) or "%1",
                    "start": _val(start_el) or "1",
                }
            abstracts[_val(absn, "abstractNumId")] = levels
        for num in root.findall(qn("w:num")):
            nid = _val(num, "numId")
            abs_el = num.find(qn("w:abstractNumId"))
            if nid:
                self.levels[nid] = abstracts.get(_val(abs_el), {})

    def spec_for(self, paragraph) -> tuple[str, int, dict[str, str]] | None:
        num_pr = paragraph._element.find(".//" + qn("w:numPr"))
        if num_pr is None:
            return None
        nid = _val(num_pr.find(qn("w:numId")))
        if not nid or nid == "0":
            return None
        ilvl = int(_val(num_pr.find(qn("w:ilvl"))) or 0)
        spec = (self.levels.get(nid) or {}).get(ilvl)
        if not spec:
            return None
        return nid, ilvl, spec

    def take(self, nid: str, ilvl: int, spec: dict[str, str]) -> str:
        if spec.get("fmt") == "bullet":
            return ""
        counts = self.counts.setdefault(nid, {})
        for deeper in [k for k in counts if k > ilvl]:
            del counts[deeper]
        counts[ilvl] = counts.get(ilvl, int(spec.get("start") or 1) - 1) + 1
        out = spec.get("text") or "%1"
        for i in range(9):
            token = f"%{i + 1}"
            if token not in out:
                continue
            n = counts.get(i, 1)
            fmt = spec["fmt"] if i == ilvl else "decimal"
            out = out.replace(token, _format_num(fmt, n))
        return out


_TITLE_MARK = (
    "线路概述",
    "线路基本情况",
    "设施设备功能有效性",
    "运营契合",
    "管理体系合规",
    "修程修制",
    "对上一年度",
    "企业标准和制度",
    "法律法规",
    "退运更换",
    "设备退运",
)


def paragraph_visible_text(paragraph, numbering: NumberingReader | None, base_text: str | None = None) -> str:
    """可见文字 = 自动编号前缀 + 段内文字。短标题不加编号，避免「线路概述」变成「1线路概述」。

    base_text 为调用方已按“接受修订后”提取的段内文字（含 w:ins、不含 w:del）；
    不传时回退到 python-docx 的 paragraph.text（不含修订插入内容）。
    """
    if base_text is not None:
        text = base_text.strip()
    else:
        text = (paragraph.text or "").strip()
    if not text or numbering is None:
        return text
    found = numbering.spec_for(paragraph)
    if not found:
        return text
    nid, ilvl, spec = found
    template = spec.get("text") or ""
    fmt = spec.get("fmt") or ""
    enclosed = any(ch in template for ch in "（()）")
    circled = fmt in {"decimalEnclosedCircleChinese", "decimalEnclosedCircle"}
    if not enclosed and not circled:
        if any(k in text for k in _TITLE_MARK) and len(text) < 80:
            return text
        if len(text) < 40 and not any(ch in text for ch in "。！？；"):
            return text
    prefix = (numbering.take(nid, ilvl, spec) or "").strip()
    if not prefix:
        return text
    if text.startswith(prefix):
        return text
    if (text.startswith("（") and "）" in text[:8]) or (text.startswith("(") and ")" in text[:8]):
        return text
    return f"{prefix}{text}"
