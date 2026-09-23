# -*- coding: utf-8 -*-
from chapters.common.list_number import (
    renumber_continued_list_flow,
    renumber_continued_list_paras,
    restart_list_after_prose_paras,
    restart_list_numbers_paras,
)
from chapters.overhead.extract import extract_overhead_controls
from parsers.document_model import Block, DocumentModel


def test_renumber_continues_after_another_source_list():
    paras = [
        "1、八号线刚性接触线进行差异化管控。",
        "2、集中修项目：刚性区段9635定位点。",
        "3、大修更新改造：已纳入2023年项目。",
        "1、已纳入2024年高架段大修，计划完成5站。",
        "2、集中修项目：柔性区段1451定位点。",
    ]
    out = renumber_continued_list_paras(paras)
    assert out[0].startswith("1、")
    assert out[1].startswith("2、")
    assert out[2].startswith("3、")
    assert out[3].startswith("4、")
    assert "计划完成5站" in out[3]
    assert out[4].startswith("5、")


def test_renumber_resets_on_new_measure_header():
    paras = [
        "1）3号中潭路渡线吊弦断裂。",
        "11）下锚钢丝绳断丝。",
        "现有管控措施是：开展年度生产计划与接触网集中修。",
        "3号线北延伸触网子系统和设备状态是B",
        "12）隔离开关控制电缆超年限。",
        "后续的管控措施是：",
        "1、专项更换：将全线58处横跨列入更换计划。",
        "2、大修更新改造：馈线绝缘子更换。",
    ]
    out = renumber_continued_list_paras(paras)
    assert out[0].startswith("1）")
    assert out[1].startswith("11）")
    assert out[4].startswith("12）")
    assert out[6].startswith("1、")
    assert out[7].startswith("2、")


def test_renumber_resets_on_kind_strategy_header():
    paras = [
        "管控策略包括：",
        "1、集中修项目：一期。",
        "2、大修更新改造：二期。",
        "刚性接触网的管控策略包括：",
        "1、集中修检验检测：隧道段。",
        "4、差异化管控：加强巡视。",
    ]
    out = renumber_continued_list_paras(paras)
    assert out[1].startswith("1、")
    assert out[2].startswith("2、")
    assert out[4].startswith("1、")
    assert out[5].startswith("4、")


def test_restart_list_after_prose_resets_second_group():
    out = restart_list_after_prose_paras(
        [
            "1.气温变化：结冰。",
            "2.降雪：积雪融化。",
            "3.风力：吹到电线上。",
            "一旦接触线被覆冰，就有可能对电力系统造成灾难性的影响。",
            "4. 接触不良：接触线上的冰会导致接触不良。",
            "5. 电压失常：接触线上的冰会导致电压失常。",
            "6. 接触线振动：风力使其振动。",
        ]
    )
    assert out[0].startswith("1.")
    assert out[2].startswith("3.")
    assert out[4].startswith("1.")
    assert out[5].startswith("2.")
    assert out[6].startswith("3.")


def test_restart_list_numbers_from_three():
    out = restart_list_numbers_paras(
        [
            "针对本次PLC故障问题，联系厂家。",
            "3)梳理14号线PLC故障历史数据。",
            "4)针对PLC故障问题设置专人监护。",
            "7）后续加强对班组人员管理。",
        ]
    )
    assert out[1].startswith("1)")
    assert out[2].startswith("2)")
    assert out[3].startswith("3）")


def test_renumber_flow_skips_tables():
    flow = [
        {"kind": "para", "text": "1、专项更换：横跨。"},
        {"kind": "para", "text": "2、大修更新改造：绝缘子。"},
        {"kind": "table", "rows": [["2025年在执行项目情况"]]},
        {"kind": "para", "text": "1、已纳入2024年项目。"},
    ]
    out = renumber_continued_list_flow(flow)
    assert out[0]["text"].startswith("1、")
    assert out[1]["text"].startswith("2、")
    assert out[2]["kind"] == "table"
    assert out[3]["text"].startswith("3、")


def test_controls_merge_renumbers_second_file_list():
    older = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通8号线", level=3),
            Block(type="paragraph", text="1、八号线刚性接触线进行差异化管控。"),
            Block(type="paragraph", text="2、集中修项目：刚性区段9635定位点。"),
            Block(type="paragraph", text="3、大修更新改造：已纳入2023年项目。"),
        ],
    )
    newer = DocumentModel(
        source_name="维护七部9.2.docx",
        source_path="w72.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通8号线", level=3),
            Block(type="paragraph", text="1、已纳入2024年高架段大修，计划完成5站。"),
            Block(type="paragraph", text="2、集中修项目：柔性区段1451定位点。"),
        ],
    )
    hit = extract_overhead_controls([older, newer])
    eight = next(s for s in hit["sections"] if "8号线" in s["title"])
    paras = eight["paras"]
    assert paras[0].startswith("1、")
    assert paras[2].startswith("3、")
    assert paras[3].startswith("4、")
    assert paras[4].startswith("5、")
    flow_nums = [x["text"][:2] for x in eight["fill"]["flow"] if x.get("kind") == "para"]
    assert flow_nums == ["1、", "2、", "3、", "4、", "5、"]
