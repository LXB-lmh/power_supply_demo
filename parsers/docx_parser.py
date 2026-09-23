# -*- coding: utf-8 -*-
"""Word：按正文顺序抽出标题、段落、表、图占位、公式占位。

source_index 对应 body 子节点序号，成文贴图/贴公式时按它回原文件取。
自动编号（1）（2）由 numbering 还原进段落，避免故障稿丢序号。
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .document_model import Block, DocumentModel
from .numbering import NumberingReader, paragraph_visible_text

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# 修订容器：w:del（删除）、w:moveFrom（移动源）内的 run 视为已删除，不提取
_DEL_RUN_CONTAINERS = {qn("w:del"), qn("w:moveFrom")}


def _accepted_runs(paragraph: Paragraph):
    """遍历段内有效 run（等价于“接受所有修订”后的可见 run）。

    含 w:ins（插入修订）、w:hyperlink、w:moveTo 中的 run；
    排除 w:del、w:moveFrom 内的 run（被删除内容，Word 文本节点用 w:delText）。
    """
    p_elm = paragraph._p
    for run_elm in p_elm.iter(qn("w:r")):
        anc = run_elm.getparent()
        deleted = False
        while anc is not None and anc is not p_elm:
            if anc.tag in _DEL_RUN_CONTAINERS:
                deleted = True
                break
            anc = anc.getparent()
        if not deleted:
            yield Run(run_elm, paragraph)


def accepted_paragraph_text(paragraph: Paragraph) -> str:
    """接受修订后的段落可见文本（含插入修订，不含删除修订）。"""
    return "".join(run.text for run in _accepted_runs(paragraph))


def _table_vmerges(table: Table) -> list[tuple[int, int, int]]:
    """从 Word 表 XML 读竖合并范围 (col, start_row, end_row)，含表头行下标。

    成文按材料原合并还原；不要只靠「相同文字推断」，以免合错物料名称等列。
    """
    tbl = table._tbl
    rows_xml = tbl.findall(qn("w:tr"))
    active: dict[int, int] = {}
    done: list[tuple[int, int, int]] = []

    def _close(col: int, end_row: int) -> None:
        start = active.pop(col, None)
        if start is not None and end_row > start:
            done.append((col, start, end_row))

    for ri, tr in enumerate(rows_xml):
        grid_col = 0
        for tc in tr.findall(qn("w:tc")):
            tc_pr = tc.find(qn("w:tcPr"))
            span = 1
            vm: str | None = None
            if tc_pr is not None:
                gs = tc_pr.find(qn("w:gridSpan"))
                if gs is not None:
                    span = int(gs.get(qn("w:val") or "1"))
                vm_el = tc_pr.find(qn("w:vMerge"))
                if vm_el is not None:
                    raw = vm_el.get(qn("w:val"))
                    vm = "restart" if raw == "restart" else "continue"
            if vm == "restart":
                _close(grid_col, ri - 1)
                active[grid_col] = ri
            elif vm == "continue":
                if grid_col not in active:
                    active[grid_col] = ri
            else:
                _close(grid_col, ri - 1)
            grid_col += span
    last = len(rows_xml) - 1
    for col in list(active.keys()):
        _close(col, last)
    return done


def _iter_block_items(doc: Document):
    """段落与表交错遍历，保持原文档顺序。"""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _heading_level(paragraph: Paragraph) -> int | None:
    """Heading 1 / 标题1 视为一级；对不上样式的当普通段。"""
    style = paragraph.style
    if style is None or not style.name:
        return None
    name = style.name
    if name.startswith("Heading"):
        parts = name.split()
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
        return 1
    if name.startswith("标题"):
        for ch in name:
            if ch.isdigit():
                return int(ch)
        return 1
    return None


def _paragraph_format(paragraph: Paragraph) -> tuple[str, float, bool, bool]:
    """提取标题识别用的格式信号：(样式名, 可见 run 最大字号pt, 是否全加粗, 是否居中)。

    只取 run 上显式设置的字号/加粗，样式继承链不展开（章标题通常显式设置）；
    无显式值时字号记 0、加粗记 False，调用方按弱信号处理。
    """
    style_name = ""
    try:
        style_name = (paragraph.style.name or "") if paragraph.style is not None else ""
    except Exception:
        style_name = ""
    max_size = 0.0
    bold_flags: list[bool] = []
    for run in _accepted_runs(paragraph):
        if not (run.text or "").strip():
            continue
        try:
            if run.font.size is not None:
                max_size = max(max_size, float(run.font.size.pt))
        except Exception:
            pass
        try:
            bold_flags.append(bool(run.font.bold))
        except Exception:
            pass
    all_bold = bool(bold_flags) and all(bold_flags)
    centered = False
    try:
        # 1 == WD_ALIGN_PARAGRAPH.CENTER；不引入枚举常量，直接比较数值
        centered = paragraph.alignment is not None and int(paragraph.alignment) == 1
    except Exception:
        centered = False
    return style_name, max_size, all_bold, centered


def _has_drawing(paragraph_elm) -> bool:
    return bool(
        paragraph_elm.findall(".//" + qn("w:drawing"))
        or paragraph_elm.findall(".//" + qn("w:pict"))
        or paragraph_elm.findall(".//" + qn("w:object"))
    )


def _has_omml(paragraph_elm) -> bool:
    """段内是否含 Office Math（OMML）公式。"""
    if paragraph_elm is None:
        return False
    return bool(
        paragraph_elm.findall(f".//{{{M_NS}}}oMath")
        or paragraph_elm.findall(f".//{{{M_NS}}}oMathPara")
    )


def _looks_like_equation_caption(text: str) -> bool:
    """公式编号行，如（3-1）、(4-2)，常与公式对象同段。"""
    t = (text or "").strip()
    return bool(re.fullmatch(r"[（(]\s*\d+\s*[-–—]\s*\d+\s*[）)]", t))


_YELLOW_HIGHLIGHT = {"yellow"}
_YELLOW_FILL = {
    "FFFF00",
    "FFFFFF00",
    "FFFF99",
    "FFFF66",
    "FFF2CC",
    "FFEB9C",
    "FFC000",
    "FFD966",
    "FFE599",
    "FFE699",
    "FFF4CC",
    "FFFFCC",
}


def _shd_is_yellow(shd) -> bool:
    if shd is None:
        return False
    fill = (shd.get(qn("w:fill")) or "").strip().upper()
    if not fill or fill in {"AUTO", "FFFFFF", "FFFFFFFF"}:
        return False
    return fill in _YELLOW_FILL or fill == "YELLOW"


def paragraph_is_yellow(paragraph_elm) -> bool:
    """段底纹或任一可见文字 run 为黄高亮/黄底，即视为材料标黄段。"""
    if paragraph_elm is None:
        return False
    p_pr = paragraph_elm.find(qn("w:pPr"))
    if p_pr is not None and _shd_is_yellow(p_pr.find(qn("w:shd"))):
        return True
    for run in paragraph_elm.findall(".//" + qn("w:r")):
        texts = run.findall(qn("w:t"))
        if not any((node.text or "").strip() for node in texts):
            continue
        r_pr = run.find(qn("w:rPr"))
        if r_pr is None:
            continue
        hl = r_pr.find(qn("w:highlight"))
        if hl is not None and (hl.get(qn("w:val")) or "").strip().lower() in _YELLOW_HIGHLIGHT:
            return True
        if _shd_is_yellow(r_pr.find(qn("w:shd"))):
            return True
    return False


def _is_formula_paragraph(paragraph_elm, text: str) -> bool:
    """有 OMML，或「公式编号 + 嵌入对象」同段，整段按公式回拷。空图仍走 drawing。"""
    if _has_omml(paragraph_elm):
        return True
    if _has_drawing(paragraph_elm) and _looks_like_equation_caption(text):
        return True
    return False


def parse_docx(path: Path) -> DocumentModel:
    """解析一篇 docx。空段丢掉；有图无字仍留 drawing；有公式留 formula。"""
    doc = Document(str(path))
    numbering = NumberingReader(doc)
    blocks: list[Block] = []
    body = doc.element.body
    for index, child in enumerate(body.iterchildren()):
        if child.tag == qn("w:p"):
            item = Paragraph(child, doc)
            raw_text = accepted_paragraph_text(item)
            text = paragraph_visible_text(item, numbering, raw_text)
            has_drawing = _has_drawing(item._element)
            has_omml = _has_omml(item._element)
            if not text and not has_drawing and not has_omml:
                continue
            if _is_formula_paragraph(item._element, text):
                blocks.append(Block(type="formula", text=text, source_index=index))
                continue
            if text:
                level = _heading_level(item)
                yellow = paragraph_is_yellow(item._element)
                style_name, font_size, bold, centered = _paragraph_format(item)
                if level:
                    blocks.append(
                        Block(
                            type="heading",
                            text=text,
                            level=level,
                            source_index=index,
                            yellow=yellow,
                            style_name=style_name,
                            font_size=font_size,
                            bold=bold,
                            centered=centered,
                        )
                    )
                else:
                    blocks.append(
                        Block(
                            type="paragraph",
                            text=text,
                            source_index=index,
                            yellow=yellow,
                            style_name=style_name,
                            font_size=font_size,
                            bold=bold,
                            centered=centered,
                        )
                    )
            if has_drawing:
                blocks.append(Block(type="drawing", source_index=index))
        elif child.tag == qn("w:tbl"):
            item = Table(child, doc)
            rows: list[list[str]] = []
            for row in item.rows:
                rows.append(
                    [
                        "\n".join(accepted_paragraph_text(p) for p in cell.paragraphs)
                        .strip()
                        .replace("\n", " ")
                        for cell in row.cells
                    ]
                )
            # 空列表也保留：表示材料无竖合并，成文不要再靠同文误推断
            vmerge = _table_vmerges(item)
            has_text = any(any(str(c).strip() for c in row) for row in rows)
            if has_text:
                blocks.append(Block(type="table", rows=rows, source_index=index, vmerge=vmerge))
            elif _has_drawing(child):
                blocks.append(Block(type="drawing", source_index=index))
            elif rows:
                blocks.append(Block(type="table", rows=rows, source_index=index, vmerge=vmerge))
    return DocumentModel(
        source_name=path.name,
        source_path=str(path),
        suffix=".docx",
        blocks=blocks,
    )
