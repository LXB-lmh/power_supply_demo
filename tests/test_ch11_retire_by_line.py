# -*- coding: utf-8 -*-
"""第 11 章退运：按线路汇总成 11.1.x，合并汇编与报废说明。"""
from parsers.document_model import Block, DocumentModel

from chapters.power.extract import extract_retire
from chapters.power.write import write_ch11
from chapters.common.word import new_report_document


def _doc(name: str, blocks: list[Block], path: str = "") -> DocumentModel:
    return DocumentModel(source_name=name, source_path=path or name, suffix=".docx", blocks=blocks)


def test_extract_retire_groups_by_line():
    compiled = _doc(
        "11退运材料.docx",
        [
            Block(type="heading", text="1号线供电设备退运更换", level=2),
            Block(type="paragraph", text="1号线需报废3台中央信号屏、1台车站短路器，原值共计467115.74元。"),
            Block(type="heading", text="1号线电动单梁悬挂起重机退运更换", level=2),
            Block(type="paragraph", text="1号线梅陇基地的1台电动单梁悬挂起重机于1994年7月开始使用。"),
            Block(type="heading", text="2号线供电系统设备退运更换", level=2),
            Block(type="paragraph", text="2号线需报废2台蓄电池屏。"),
            Block(type="heading", text="3号线供电系统设备退运更换", level=2),
            Block(type="paragraph", text="概述"),
            Block(type="paragraph", text="宝山路站接轨改造工程是提质增效工程的核心组成部分，很长的工程背景叙述。"),
            Block(type="paragraph", text="报废原因"),
            Block(type="paragraph", text="3号线需报废6台隔离开关，一台空气除湿机。"),
        ],
    )
    extra = _doc(
        "关于1号线空调报废的情况说明.docx",
        [
            Block(type="heading", text="关于1号线空调报废的情况说明", level=1),
            Block(type="paragraph", text="1号线北延伸共计2台空调需报废，安装在共康路站、共富新村站。"),
            Block(type="paragraph", text="综上所述，故申请报废。"),
            Block(type="paragraph", text="上海地铁维护保障有限公司供电分公司"),
            Block(type="paragraph", text="2026年3月9日"),
        ],
    )
    tools = _doc(
        "关于1号线仪器仪表工器具报废的情况说明.docx",
        [
            Block(type="heading", text="关于1号线仪器仪表工器具报废的情况说明", level=1),
            Block(type="paragraph", text="报废万用表两台，不应进11.1。"),
        ],
    )
    data = extract_retire([compiled, extra, tools], year=2026)
    assert len(data["sections"]) == 18
    line1 = data["sections"][0]
    assert line1["title"] == "轨道交通1号线"
    blob = "\n".join(line1["paras"])
    assert "中央信号屏" in blob
    assert "起重机" in blob
    assert "空调" in blob
    assert "万用表" not in blob
    assert "综上所述" not in blob
    line3 = data["sections"][2]
    blob3 = "\n".join(line3["paras"])
    assert "隔离开关" in blob3
    assert "提质增效工程" not in blob3
    assert data["sections"][10]["empty"] is True  # 11号线无材料


def test_extract_retire_dedupes_compiled_and_folder_copies():
    """11退运汇编 + 单份说明 + 4月份同名备份，不应把同一批设备写两遍。"""
    compiled = _doc(
        "11退运材料.docx",
        [
            Block(type="heading", text="1号线供电设备退运更换", level=2),
            Block(type="paragraph", text="1号线需报废3台中央信号屏、1台车站短路器。3台中央信号屏，分别于1996年12月开始使用。"),
            Block(type="paragraph", text="中央信号屏：硬件老化。"),
        ],
        path=r"uploads\正式\退运报废倾向性\11退运材料.docx",
    )
    detail = _doc(
        "关于1号线供电设备报废的情况说明.docx",
        [
            Block(type="heading", text="关于1号线供电设备报废的情况说明", level=1),
            Block(
                type="paragraph",
                text="1号线需报废3台中央信号屏、1台车站短路器，原值共计467115.74元。3台中央信号屏，分别于1996年12月开始使用。",
            ),
            Block(type="paragraph", text="中央信号屏：硬件老化日渐上升。"),
        ],
        path=r"uploads\正式\退运报废倾向性\报废的情况说明\2026\关于1号线供电设备报废的情况说明.docx",
    )
    april_copy = _doc(
        "关于1号线供电设备报废的情况说明.docx",
        [
            Block(type="heading", text="关于1号线供电设备报废的情况说明", level=1),
            Block(
                type="paragraph",
                text="1号线需报废3台中央信号屏、1台车站短路器，原值共计467115.74元。3台中央信号屏，分别于1996年12月开始使用。",
            ),
            Block(type="paragraph", text="中央信号屏：硬件老化日渐上升。"),
        ],
        path=r"uploads\99-26年4月份评估报告编制材料(2)\退运报废倾向性\报废的情况说明\2026\关于1号线供电设备报废的情况说明.docx",
    )
    data = extract_retire([compiled, detail, april_copy], year=2026)
    paras = data["sections"][0]["paras"]
    blob = "\n".join(paras)
    assert blob.count("原值共计467115.74元") == 1
    assert blob.count("需报废3台中央信号屏") == 1
    assert "中央信号屏" in blob
    too_old = _doc(
        "关于6号线整流变压器报废的情况说明.docx",
        [Block(type="paragraph", text="6号线旧年材料不应进。")],
        path=r"uploads\pack\报废情况说明\2024\关于6号线整流变压器报废的情况说明.docx",
    )
    prev = _doc(
        "关于6号线整流变压器报废的情况说明.docx",
        [Block(type="paragraph", text="6号线共计9台整流变压器需报废。")],
        path=r"uploads\pack\报废情况说明\2025\关于6号线整流变压器报废的情况说明.docx",
    )
    data = extract_retire([too_old, prev], year=2026)
    blob = "\n".join(data["sections"][5]["paras"])
    assert "9台整流变压器" in blob
    assert "旧年材料" not in blob


def test_extract_retire_supplements_from_line_report():
    report = _doc(
        "2026年评估报告（12号线变电专业）.docx",
        [
            Block(type="paragraph", text="使用环境符合性评估"),
            Block(type="paragraph", text="退运报废倾向性评估"),
            Block(type="paragraph", text="根据上海城市轨道交通设施设备运营评估规范第7部分：供电（含能源系统）8.2.7条款的评估情况撰写；"),
            Block(type="paragraph", text="12号全线39套交直流屏投用11年，充电模块一直在运行状态且已达使用年限。"),
            Block(type="paragraph", text="评估结论与建议"),
        ],
    )
    data = extract_retire([report], year=2026)
    blob = "\n".join(data["sections"][11]["paras"])
    assert "交直流屏" in blob
    assert "8.2.7" not in blob


def test_write_ch11_line_headings(tmp_path):
    pack = {
        "year": 2026,
        "ch11": extract_retire(
            [
                _doc(
                    "11退运材料.docx",
                    [
                        Block(type="heading", text="1号线供电设备退运更换"),
                        Block(type="paragraph", text="1号线需报废1台车站短路器。"),
                    ],
                )
            ],
            year=2026,
        ),
    }
    doc = new_report_document()
    write_ch11(doc, pack)
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert any("11.1  2026年各线路设备退运更换情况" in t for t in texts)
    assert any("11.1.1  轨道交通1号线" in t for t in texts)
    assert any("11.1.11  轨道交通11号线" in t for t in texts)
    assert any("11号线暂无退运报废设备" in t for t in texts)
