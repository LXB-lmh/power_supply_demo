# -*- coding: utf-8 -*-
"""第5章：多份合规材料不叠写；5.1/5.2 无体例则复用去年。"""
from chapters.power.extract import extract_compliance
from parsers.document_model import Block, DocumentModel


def _compliance_doc(name: str, blocks: list[Block]) -> DocumentModel:
    return DocumentModel(source_name=name, source_path=name, suffix=".docx", blocks=blocks)


def test_eval_not_duplicated_across_two_compliance_docs():
    """5.6 合规性评价：两份材料各有一套时只留一份。"""
    body = [
        Block(type="paragraph", text="管理体系合规性评估"),
        Block(type="paragraph", text="合规性评价"),
        Block(type="paragraph", text="标准规划流程"),
        Block(type="paragraph", text="标准的规划、内容、审核、公示、修订、废止等确认过程流程图如图5-2所示。"),
        Block(type="drawing", source_index=43),
        Block(type="paragraph", text="图5-2 标准的规划流程图"),
        Block(type="paragraph", text="实施过程如图5-3所示。"),
        Block(type="drawing", source_index=46),
        Block(type="paragraph", text="图5-3 实施过程图"),
        Block(type="paragraph", text="1. 结合实际情况实施。"),
        Block(type="paragraph", text="2. 实施过程中专人跟踪。"),
    ]
    a = _compliance_doc("4&5合规性材料(2026).docx", body)
    b = _compliance_doc("5&6合规性材料(2026).docx", list(body))
    ch5 = extract_compliance([a, b])["ch5"]
    texts = [x.get("text") for x in ch5["eval_flow"] if x.get("kind") == "para"]
    assert texts.count("标准规划流程") == 1
    assert texts.count("实施过程如图5-3所示。") == 1
    assert sum(1 for x in ch5["eval_flow"] if x.get("kind") == "drawing") == 2


def test_dedupe_flow_collapses_exact_double_block():
    from chapters.common.section_slice import dedupe_flow_items

    half = [
        {"kind": "para", "text": "标准规划流程"},
        {"kind": "para", "text": "如图5-2所示。"},
        {"kind": "drawing", "source_path": "a.docx", "source_index": 1},
        {"kind": "para", "text": "图5-2 题注"},
    ]
    out = dedupe_flow_items(half + half)
    assert len(out) == 4
    assert [x.get("text") for x in out if x.get("kind") == "para"] == [
        "标准规划流程",
        "如图5-2所示。",
        "图5-2 题注",
    ]


def test_ch51_falls_back_to_prior_when_year_missing():
    year = _compliance_doc(
        "4&5合规性材料.docx",
        [
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="法律法规的获取情况"),
            Block(type="paragraph", text="已建立法律法规获取清单。"),
        ],
    )
    prior = DocumentModel(
        source_name="去年供电年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="5.1  特种设备、消防、防雷规程", level=2),
            Block(type="paragraph", text="供电分公司特种设备、消防、防雷相关规程如表5-1所示。"),
            Block(
                type="table",
                rows=[["特种设备名称", "规程编号", "名称"], ["锅炉", "Q/1", "操作规程"]],
            ),
            Block(type="paragraph", text="消防相关规程如表5-2所示。"),
            Block(
                type="table",
                rows=[["名称", "编号"], ["灭火器", "XF-1"]],
            ),
            Block(type="heading", text="5.2  强制年检或评估情况分析", level=2),
            Block(type="paragraph", text="检测报告如图5-1所示。"),
            Block(type="drawing", source_index=10),
            Block(type="paragraph", text="图5-1 检测报告"),
            Block(type="heading", text="5.3  法律法规的获取情况", level=2),
        ],
    )
    ch5 = extract_compliance([year], prior_docs=[prior])["ch5"]
    assert ch5["special_via"] == "prior"
    assert any(x.get("kind") == "table" for x in ch5["special_flow"])
    assert ch5["inspect_via"] == "prior"
    assert any(x.get("kind") == "drawing" for x in ch5["inspect_flow"])


def test_ch51_year_kept_when_format_like_prior():
    year = _compliance_doc(
        "4&5合规性材料.docx",
        [
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="5.1  特种设备、消防、防雷规程"),
            Block(type="paragraph", text="本年特种设备规程如表5-1。"),
            Block(
                type="table",
                rows=[["特种设备名称", "规程编号", "名称"], ["压力容器", "Q/2", "规程"]],
            ),
            Block(type="paragraph", text="法律法规的获取情况"),
            Block(type="paragraph", text="已建立清单。"),
        ],
    )
    prior = DocumentModel(
        source_name="去年.docx",
        source_path="p.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="5.1  特种设备、消防、防雷规程", level=2),
            Block(type="paragraph", text="旧年内容不应覆盖今年。"),
            Block(type="table", rows=[["特种设备名称", "规程编号"], ["旧", "0"]]),
            Block(type="heading", text="5.2  强制年检", level=2),
        ],
    )
    ch5 = extract_compliance([year], prior_docs=[prior])["ch5"]
    assert ch5["special_via"] == "year"
    blob = " ".join(str(x.get("text") or "") for x in ch5["special_flow"])
    assert "本年特种设备" in blob
    assert "旧年内容" not in blob
