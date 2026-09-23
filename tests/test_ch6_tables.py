# -*- coding: utf-8 -*-
"""第六章表格口径：编号列表保留；表跟在「分别是」后不堆文末；不沿用第五章表号。"""
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from chapters.power.extract import extract_compliance
from chapters.power.write import write_chapter_docx
from parsers.dispatch import parse_file

SRC = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料\4&5合规性材料(2026).docx")


def test_parser_keeps_list_numbers():
    if not SRC.exists():
        return
    doc = parse_file(SRC)
    texts = [(b.text or "") for b in doc.blocks]
    assert any(t.startswith("（1）《供电智能运维系统") for t in texts)
    assert any(t.startswith("（2）《变电站设备保养细则") for t in texts)


def test_ch6_keeps_tables_in_place_not_at_end():
    if not SRC.exists():
        return
    pack = extract_compliance([parse_file(SRC)])["ch6"]
    kinds = [x["kind"] for x in pack["revise_flow"]]
    assert kinds.count("table") >= 4
    texts = [x.get("text") or "" for x in pack["revise_flow"]]
    assert not any("如表5-3" in t or t.startswith("表5-3") for t in texts)  # 第六章不沿用第五章表号
    assert not any("待提供后完善" in t for t in texts)
    i = next(i for i, t in enumerate(texts) if t.startswith("分别是"))
    assert pack["revise_flow"][i + 1]["kind"] == "table"  # 表紧跟「分别是」，不堆到文末
    assert pack["revise_flow"][i + 1]["rows"][1][1].startswith("SCADA")
    j = next(i for i, t in enumerate(texts) if "合并作业指导书" in t)
    assert pack["revise_flow"][j + 1]["kind"] == "table"
    assert any("（1）《供电智能运维系统" in t for t in texts)
    assert any("刚性接触网维修作业指导书" in "".join(c for r in x.get("rows") or [] for c in r) for x in pack["revise_flow"] if x.get("kind") == "table")


def test_write_ch6_puts_table_after_namely(tmp_path):
    if not SRC.exists():
        return
    pack = {"year": 2026, "ch6": extract_compliance([parse_file(SRC)])["ch6"]}
    out = tmp_path / "ch6.docx"
    write_chapter_docx(pack, out, "ch6")
    dest = Document(str(out))
    body = list(dest.element.body.iterchildren())
    texts = []
    for el in body:
        tag = el.tag.split("}")[-1]
        t = "".join(x.text or "" for x in el.findall(".//" + qn("w:t")))
        texts.append((tag, t))
    joined = [t for _, t in texts]
    assert any("（1）《供电智能运维系统" in t for t in joined)
    assert any("（2）《变电站设备保养细则" in t for t in joined)
    assert not any("如表5-3" in t for t in joined)

    def after(pred):
        i = next(i for i, (tag, t) in enumerate(texts) if pred(tag, t))
        return texts[i + 1]

    tag, _ = after(lambda tag, t: t.startswith("分别是"))
    assert tag == "tbl"  # 成文后 XML 顺序仍是段落后接表
    tag, _ = after(lambda tag, t: "合并作业指导书" in t)
    assert tag == "tbl"
    xml = dest.element.body.xml
    assert "SCADA系统设备及电能计量系统设备维修规程" in xml
    assert "杂散电流设备检查及保养作业指导书" in xml
    assert "刚性接触网维修作业指导书" in xml
