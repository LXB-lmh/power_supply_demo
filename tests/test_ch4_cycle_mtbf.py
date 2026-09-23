# -*- coding: utf-8 -*-
"""4.2 同表头才收；4.4 从去年报告复用。"""
from chapters.ch4.power_extract import pick_cycle_table, resolve_mtbf_section
from chapters.ch4.power_style import CYCLE_TABLE
from parsers.document_model import Block, DocumentModel


def test_cycle_rejects_overhead_four_col_table_uses_prior():
    bad = DocumentModel(
        source_name="触网维护.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="table",
                rows=[
                    ["大类", "工作项目", "维护周期", "维护内容"],
                    ["巡视", "柔性接触网", "三个月一次", "步行巡视"],
                ],
            )
        ],
    )
    prior = DocumentModel(
        source_name="去年供电年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="4.2  设备维护周期和维护内容", level=2),
            Block(type="paragraph", text="设备维护周期和维护内容如下："),
            Block(type="table", rows=[list(r) for r in CYCLE_TABLE]),
            Block(type="heading", text="4.3  各个线路基本情况", level=2),
        ],
    )
    rows, src = pick_cycle_table([bad], [prior])
    assert src == "去年供电年报.docx"
    assert rows[0] == ["工作项目", "维护周期", "维护内容"]
    assert rows[1][0] == "变电站"


def test_volume_change_stops_before_44_paragraph_title():
    """材料 4.1.2 后直接接段落写的 4.4，不得吞进体量变化（观感像跳过 4.2）。"""
    from chapters.ch4.power_extract import pick_volume_change_paras

    doc = DocumentModel(
        source_name="4&7.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="4.1.2  设备体量变化情况"),
            Block(
                type="paragraph",
                text="因3号线西延工程新增变压器12台，电力电缆增加约8公里。",
            ),
            Block(type="paragraph", text="4.4  各线路供电系统年度生产指标（2025年数据待更新）"),
            Block(
                type="paragraph",
                text="截至2025年6月底数据，共有5个供电专业可靠性指标，其中MTBF指标为：供电变电所。",
            ),
            Block(type="paragraph", text="变电所系统涵盖110kV、35kV设备。"),
        ],
    )
    paras, src = pick_volume_change_paras([doc])
    assert src == "4&7.docx"
    assert len(paras) == 1
    assert "新增变压器" in paras[0]
    assert all("4.4" not in p and "可靠性指标" not in p and "变电所系统涵盖" not in p for p in paras)


def test_slice_stops_on_paragraph_outline_not_substring_442():
    """停词「4.2」不得因「4.4.2」子串误截；应在真正的 4.2/4.4 标题处停。"""
    from chapters.ch4.power_extract import _hits_section_key

    assert _hits_section_key("4.2设备维护周期和维护内容", ("4.2", "4.4"))
    assert _hits_section_key("4.4各线路供电系统年度生产指标", ("4.2", "4.4"))
    assert not _hits_section_key("4.4.2牵引网系统MTBF（R）", ("4.2",))
    assert _hits_section_key("4.4.2牵引网系统MTBF（R）", ("4.4",))

    prior = DocumentModel(
        source_name="去年供电年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="4.4  各线路供电系统年度生产指标", level=2),
            Block(type="paragraph", text="截至2025年6月底数据，共有5个供电专业可靠性指标。"),
            Block(
                type="table",
                rows=[
                    ["序号", "指标名称", "指标单位", "当月值"],
                    ["1", "供电变电所MTBF(R)", "万小时", "2.95"],
                ],
            ),
            Block(type="heading", text="4.5  评估小结", level=2),
        ],
    )
    hit = resolve_mtbf_section([], [prior])
    assert hit["mtbf_via"] == ""
    assert not hit["mtbf_flow"]
    assert not hit["mtbf_paras"]


def test_mtbf_slice_keeps_五月_paragraph():
    """停段不得把「5月…」当成第5章截断。"""
    from chapters.ch4.power_extract import _slice_mtbf_flow

    doc = DocumentModel(
        source_name="4&7.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="4.4  各线路供电系统年度生产指标", level=2),
            Block(type="paragraph", text="截至数据说明。"),
            Block(type="heading", text="4.4.4  直流应急电源系统MTBF（R）", level=3),
            Block(
                type="paragraph",
                text="5月供电直流开关设备平均接报故障间隔为无穷大次，优于近6个月平均水平。",
            ),
            Block(type="heading", text="4.4.5  直流开关设备MCBF（R）", level=3),
            Block(type="paragraph", text="直流开关设备说明。"),
            Block(type="heading", text="4.5  评估小结", level=2),
        ],
    )
    flow = _slice_mtbf_flow(doc)
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    assert any("5月供电" in t for t in texts)
    assert any("4.4.5" in t for t in texts)
    assert any("直流开关设备说明" in t for t in texts)
