# -*- coding: utf-8 -*-
"""第五章插图口径：合规性材料里的 Visio/OLE 进评估流，图5-3 题注前须有嵌入对象。"""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from chapters.common.drawings import copy_drawings_from_body_index
from chapters.common.word import new_report_document
from chapters.power.extract import extract_compliance
from chapters.power.write import write_chapter_docx
from parsers.dispatch import parse_file

SRC = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料\4&5合规性材料(2026).docx")


def test_parser_keeps_visio_ole_as_drawing():
    if not SRC.exists():
        return
    doc = parse_file(SRC)
    drawings = [b for b in doc.blocks if b.type == "drawing"]
    assert len(drawings) >= 3
    assert {b.source_index for b in drawings} >= {30, 43, 46}  # 合规性材料里 Visio 对象的正文位置


def test_extract_puts_figures_in_eval_flow():
    if not SRC.exists():
        return
    pack = extract_compliance([parse_file(SRC)])
    ch5 = pack["ch5"]
    assert len(ch5["drawings"]) >= 3
    kinds = [x["kind"] for x in ch5["eval_flow"]]
    assert kinds.count("drawing") >= 2
    assert any("如图5-2" in (x.get("text") or "") for x in ch5["eval_flow"])
    assert any("如图5-3" in (x.get("text") or "") for x in ch5["eval_flow"])
    idx = [x["source_index"] for x in ch5["eval_flow"] if x.get("kind") == "drawing"]
    assert 43 in idx and 46 in idx  # 图5-2 / 图5-3 对应的 OLE


def test_copy_ole_figure_into_report():
    if not SRC.exists():
        return
    dest = new_report_document()
    assert copy_drawings_from_body_index(SRC, 46, dest) is True
    xml = dest.element.body.xml
    assert "w:object" in xml or "w:drawing" in xml or "w:pict" in xml


def test_write_ch5_keeps_figure_5_3(tmp_path):
    if not SRC.exists():
        return
    docs = [parse_file(SRC)]
    pack = {"year": 2026, "ch5": extract_compliance(docs)["ch5"]}
    out = tmp_path / "ch5.docx"
    write_chapter_docx(pack, out, "ch5")
    dest = Document(str(out))
    objects = dest.element.body.findall(".//" + qn("w:object"))
    texts = [p.text for p in dest.paragraphs]
    assert any("如图5-3" in t for t in texts)
    assert any("图5-3" in t for t in texts)
    assert len(objects) >= 2
    # 图5-3 题注前应有嵌入对象
    body = list(dest.element.body.iterchildren())
    cap_i = next(i for i, el in enumerate(body) if "图5-3" in "".join(t.text or "" for t in el.findall(".//" + qn("w:t"))))
    assert any(el.findall(".//" + qn("w:object")) for el in body[max(0, cap_i - 3) : cap_i])
