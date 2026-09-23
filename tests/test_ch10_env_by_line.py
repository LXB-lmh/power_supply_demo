# -*- coding: utf-8 -*-
"""第 10 章使用环境：按线路汇总，拒触网弓架次稿。"""
from chapters.common.word import new_report_document
from chapters.power.extract import extract_env
from chapters.power.write import write_ch10
from parsers.document_model import Block, DocumentModel


def _doc(name: str, blocks: list[Block], path: str = "") -> DocumentModel:
    return DocumentModel(source_name=name, source_path=path or name, suffix=".docx", blocks=blocks)


def test_extract_env_groups_by_line_and_skips_false_start():
    line1 = _doc(
        "2026年评估报告（1号线）.docx",
        [
            Block(type="paragraph", text="措施：对设备仔细清扫保养，从使用环境方面降低其故障率；"),
            Block(type="paragraph", text="使用环境符合性评估"),
            Block(
                type="paragraph",
                text="1号线共有60个变电站，粉尘污染严重的有21个，电缆层积水的有9个，环境潮湿的有14个。",
            ),
            Block(type="paragraph", text="退运报废倾向性评估"),
            Block(type="paragraph", text="1号线暂无退运。"),
        ],
    )
    line2 = _doc(
        "01-2025年评估报告（2线路变电专业）.docx",
        [
            Block(type="paragraph", text="使用环境符合性评估"),
            Block(
                type="paragraph",
                text="2号线二期地下段变电站内环境潮湿，装设智能温湿度表计监控。",
            ),
            Block(type="paragraph", text="退运报废倾向性评估"),
        ],
        path=r"uploads\pack\2025\2.docx",
    )
    catenary = _doc(
        "（维护五部）接触网使用环境.docx",
        [
            Block(type="paragraph", text="使用环境符合性评估"),
            Block(type="paragraph", text="外部环境对触网系统可靠运行的影响不容忽视。"),
            Block(type="paragraph", text="表10-1是与避雷防雷有关的标准。"),
            Block(
                type="table",
                rows=[["线路", "区间", "日弓架次"], ["2号线", "广兰路-机场", "457"]],
            ),
            Block(type="paragraph", text="退运报废倾向性评估"),
        ],
    )
    data = extract_env([line1, line2, catenary], year=2026)
    assert len(data["sections"]) == 18
    blob1 = "\n".join(data["sections"][0]["paras"])
    assert "60个变电站" in blob1
    assert "从使用环境方面" not in blob1
    assert "暂无退运" not in blob1
    assert "2号线二期" in "\n".join(data["sections"][1]["paras"])
    # 触网弓架次稿不得覆盖变电线路
    assert all("弓架次" not in "\n".join(s.get("paras") or []) for s in data["sections"])
    assert all("触网系统" not in "\n".join(s.get("paras") or []) for s in data["sections"] if not s.get("empty"))


def test_extract_env_flat_fallback_keeps_table():
    data = extract_env(
        [
            _doc(
                "评估材料（使用环境）.docx",
                [
                    Block(type="heading", text="使用环境符合性评估"),
                    Block(type="paragraph", text="变电站环境总体满足运行要求，温湿度可控。"),
                    Block(type="table", rows=[["测点", "温度"], ["站1", "25"]]),
                ],
            )
        ],
        year=2026,
    )
    assert any(x.get("kind") == "table" for x in data["flow"])


def test_write_ch10_line_headings():
    pack = {
        "year": 2026,
        "ch10": extract_env(
            [
                _doc(
                    "2026年评估报告（1号线）.docx",
                    [
                        Block(type="paragraph", text="使用环境符合性评估"),
                        Block(type="paragraph", text="1号线共有60个变电站，粉尘污染严重的有21个。"),
                        Block(type="paragraph", text="退运报废倾向性评估"),
                    ],
                )
            ],
            year=2026,
        ),
    }
    doc = new_report_document()
    write_ch10(doc, pack)
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert any("10.1  环境符合性评估" in t for t in texts)
    assert any("各线路环境主要情况如下" in t for t in texts)
    assert any("10.1.1  轨道交通1号线" in t for t in texts)
    assert any("60个变电站" in t for t in texts)
