# -*- coding: utf-8 -*-
"""7.1 生产组织：今年材料 → 去年/保底 → 黄空（不写死管辖范围）。"""
from chapters.power.extract import extract_org_mode
from chapters.power.write import write_chapter_docx
from parsers.document_model import Block, DocumentModel


def _doc(name: str, blocks: list[Block]) -> DocumentModel:
    return DocumentModel(source_name=name, source_path=name, suffix=".docx", blocks=blocks)


_ORG_BODY = [
    Block(type="paragraph", text="运维表现健康度评估"),
    Block(type="paragraph", text="生产组织模式"),
    Block(type="paragraph", text="目前上海地铁供电系统设施设备管理模式采用自主委外相结合的运维模式。"),
    Block(
        type="paragraph",
        text="维护部设置维护一部、维护二部等部门。维护一部管辖范围有1、5号线变电设备。",
    ),
    Block(type="paragraph", text="7.2  设施设备运维质量分析"),
    Block(type="paragraph", text="计划执行另述。"),
]


def test_org_mode_prefers_year_material():
    year = _doc("本年材料.docx", _ORG_BODY)
    prior = _doc(
        "去年年报.docx",
        [
            Block(type="heading", text="7  运维表现健康度评估", level=1),
            Block(type="heading", text="7.1  生产组织模式", level=2),
            Block(type="paragraph", text="去年旧的运维模式说明，维护三部管辖范围不应出现。"),
            Block(type="heading", text="7.2  设施设备运维质量分析", level=2),
        ],
    )
    hit = extract_org_mode([year], [prior])
    assert hit["via"] == "year"
    assert "维护一部" in "".join(hit["paras"])
    assert "去年旧的" not in "".join(hit["paras"])


def test_org_mode_falls_back_to_prior():
    year = _doc("本年无组织.docx", [Block(type="paragraph", text="只有别的内容。")])
    prior = _doc(
        "项目保底·2025供电年报",
        [
            Block(type="heading", text="运维表现健康度评估", level=1),
            Block(type="heading", text="生产组织模式", level=2),
            Block(type="paragraph", text="目前上海地铁供电系统设施设备管理模式采用自主委外相结合的运维模式。"),
            Block(type="paragraph", text="维护部按方案设置维护一部、维护二部，维护一部管辖范围有1号线。"),
            Block(type="heading", text="设施设备运维质量分析", level=2),
        ],
    )
    hit = extract_org_mode([year], [prior])
    assert hit["via"] == "prior"
    assert "运维模式" in "".join(hit["paras"])


def test_org_mode_empty_when_neither():
    hit = extract_org_mode(
        [_doc("a.docx", [Block(type="paragraph", text="无关。")])],
        [_doc("b.docx", [Block(type="paragraph", text="也无关。")])],
    )
    assert hit["via"] == ""
    assert hit["paras"] == []


def test_write_ch7_yellow_when_org_missing(tmp_path):
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    pack = {
        "year": 2026,
        "ch7": {
            "source": "",
            "table": [],
            "flow": [],
            "org_paras": [],
            "org_flow": [],
            "org_source": "",
            "org_via": "",
        },
    }
    out = tmp_path / "ch7.docx"
    write_chapter_docx(pack, out, "ch7")
    titles = []
    for p in Document(str(out)).paragraphs:
        t = p.text.strip()
        if not t.startswith("7.1"):
            continue
        yellow = any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)
        titles.append((t, yellow))
    assert titles
    assert titles[0][1] is True
