# -*- coding: utf-8 -*-
"""各章切片：paragraph 伪标题停切；节号边界；不吞下一章。"""
from chapters.common.section_slice import hits_section_key, is_outline_title_line, slice_named_section
from chapters.power.extract import extract_env, extract_named_section
from parsers.document_model import Block, DocumentModel


def test_named_section_stops_on_paragraph_next_chapter():
    doc = DocumentModel(
        source_name="合规.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="5.6  合规性评价"),
            Block(type="paragraph", text="本章合规性评价结论如下。"),
            Block(type="paragraph", text="5.7  评估小结"),
            Block(type="paragraph", text="小结正文不应被上一节吞掉。"),
            Block(type="paragraph", text="6  修程修制匹配性评估"),
            Block(type="paragraph", text="第六章开头。"),
        ],
    )
    hit = extract_named_section(
        [doc],
        start_keys=("合规性评价", "5.6"),
        stop_keys=("评估小结", "5.7", "修程修制", "第6章", "第六章"),
        skip_line_reports=False,
    )
    texts = " ".join(hit["paras"])
    assert "合规性评价结论" in texts
    assert "小结正文" not in texts
    assert "第六章开头" not in texts


def test_section_num_boundary_not_substring():
    assert hits_section_key("4.2设备维护", ("4.2", "4.4"))
    assert not hits_section_key("4.4.2牵引网", ("4.2",))
    assert hits_section_key("12.1总结", ("12.1", "12.2"))
    assert not is_outline_title_line("截至2025年6月底数据，共有5个指标。")


def test_year_month_training_line_not_foreign_outline():
    """2024.7《主题培训》是课表，不能当 4.2 目录节号截断运维段。"""
    from chapters.common.section_slice import is_foreign_outline

    assert not is_outline_title_line("2024.7《施工管理规定》主题培训")
    assert not is_outline_title_line("2025.5《400V开关继电保护装置整定值查阅》培训")
    assert not is_foreign_outline(
        "2024.7《施工管理规定》主题培训",
        keep_keys=("运维表现健康度",),
    )
    assert is_outline_title_line("8.2评估小结")


def test_env_stops_before_chapter11_paragraph():
    doc = DocumentModel(
        source_name="环境.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="使用环境"),
            Block(type="paragraph", text="供电设备所处环境条件良好，温湿度可控。"),
            Block(type="paragraph", text="11.1  设备退运更换"),
            Block(type="paragraph", text="本年度报废变压器3台，不得进入第10章。"),
        ],
    )
    hit = extract_env([doc])
    assert hit["paras"]
    assert all("报废变压器" not in p for p in hit["paras"])
    assert all("11.1" not in p for p in hit["paras"])


def test_slice_named_keeps_same_chapter_subsections_out():
    """切 8.1 时遇到 8.2 / 第9章 都应停。"""
    doc = DocumentModel(
        source_name="隐患.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="8.1  突出事件"),
            Block(type="paragraph", text="本年突出事件共2起。"),
            Block(type="paragraph", text="8.2  评估小结"),
            Block(type="paragraph", text="小结内容。"),
            Block(type="paragraph", text="第9章  备件物资保障"),
            Block(type="paragraph", text="备件章节。"),
        ],
    )
    hit = slice_named_section(
        [doc],
        start_keys=("突出事件", "8.1"),
        stop_keys=("评估小结", "8.2", "第9章", "第九章", "备件"),
    )
    texts = " ".join(hit["paras"])
    assert "突出事件共2起" in texts
    assert "小结内容" not in texts
    assert "备件章节" not in texts


def test_dedupe_keeps_cross_section_dash_list_items():
    """6.1 各号线可写相同「——修订了…」，不能因全文去重删成空壳。"""
    from chapters.common.section_slice import dedupe_flow_items

    bullet = "——修订了变电站巡视、维护及试验周期等内容；"
    flow = [
        {"kind": "para", "text": "（1）《1号线变电站运行细则》修订内容为："},
        {"kind": "para", "text": bullet},
        {"kind": "para", "text": "——修订了变压器的投运和停运规定相关内容；"},
        {"kind": "para", "text": "（4）《4号线变电站运行细则》修订内容为："},
        {"kind": "para", "text": bullet},  # 与 1 号线相同，必须保留
        {"kind": "para", "text": "——对本文件行文中的不合理描述、已变更名称进行了统一修改。"},
        {"kind": "para", "text": "（8）《8号线变电站运行细则》修订内容为："},
        {"kind": "para", "text": bullet},
        {"kind": "para", "text": bullet},  # 连续双写才压掉
    ]
    out = dedupe_flow_items(flow)
    texts = [x.get("text") for x in out]
    assert texts.count(bullet) == 3  # 三处线路各留一句，连续重复去掉一句
    assert "（8）《8号线变电站运行细则》修订内容为：" in texts
