# -*- coding: utf-8 -*-
"""3.4 管控措施：同一区段同一中类不因供电/主变各有一行而写两遍。"""
from chapters.power.extract import extract_controls
from parsers.document_model import Block, DocumentModel


def _tree(*data_rows: list[str]) -> DocumentModel:
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        *data_rows,
    ]
    return DocumentModel(
        source_name="0管控措施（设备树）.xlsx",
        source_path="x.xlsx",
        suffix=".xlsx",
        blocks=[Block(type="table", rows=rows)],
    )


def test_same_mid_under_power_and_main_written_once():
    doc = _tree(
        ["1", "1号线", "南延伸", "供电", "应急电源设备", "C", "暂未纳入大修更新改造规划", "", "", "", "PLC老化但有备件", "牵引变电站降级运营/牵引变电站退出运营"],
        ["2", "1号线", "南延伸", "主变电所系统", "应急电源设备", "C", "暂未纳入大修更新改造规划", "", "", "", "PLC老化但有备件", "牵引变电站降级运营/牵引变电站退出运营"],
        ["3", "1号线", "南延伸", "供电", "电力监控设备", "C", "已纳入2023-2026年SCADA系统改造项目", "", "", "", "", "SCADA系统通讯中断，调度远方无法操作，无法监控设备运行情况"],
        ["4", "1号线", "南延伸", "主变电所系统", "电力监控设备", "C", "暂未纳入大修更新改造规划", "开展网络质量检测", "", "", "", "SCADA系统通讯中断，调度远方无法操作，无法监控设备运行情况"],
        ["5", "1号线", "南延伸", "供电", "变压器设备", "A", "暂未纳入大修更新改造规划", "", "", "", "无备件", "主变电站降级运营"],
        ["6", "1号线", "南延伸", "主变电所系统", "变压器设备", "A", "暂未纳入大修更新改造规划", "", "", "", "无备件", "主变电站降级运营"],
    )
    ctrl = extract_controls([doc])
    blob = "\n".join(ctrl["prose"][0]["blocks"])
    assert blob.count("应急电源设备：") == 1
    assert blob.count("电力监控设备：") == 1
    assert blob.count("变压器设备：") == 1
    assert "已纳入2023-2026年SCADA系统改造项目" in blob
    assert "开展网络质量检测" in blob
    assert blob.count("SCADA系统通讯中断") == 1
    assert "南延伸：" in blob


def test_overhead_mids_not_written_into_power_controls():
    doc = _tree(
        ["1", "1号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
        ["2", "1号线", "正线", "接触网（轨）系统设备", "刚性接触网", "B", "接触线更换", "", "", "", "", ""],
        ["3", "1号线", "正线", "供电", "隔离开关", "B", "不应进入供电3.4", "", "", "", "", ""],
    )
    ctrl = extract_controls([doc])
    blob = "\n".join("\n".join(x.get("blocks") or []) for x in ctrl.get("prose") or [])
    assert "变压器设备：" in blob
    assert "刚性接触网" not in blob
    assert "隔离开关" not in blob
    assert "接触线更换" not in blob
    app = " ".join(" ".join(str(c) for c in row) for row in (ctrl.get("appendix") or []))
    assert "变压器设备" in app
    assert "刚性接触网" not in app


def test_subsystem_device_overhead_table_not_power_controls():
    rows = [
        ["序号", "线路", "区段", "子系统", "设备", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "1号线", "正线", "接触网（轨）系统设备", "刚性接触网", "B", "接触线更换", "", "", "", "", ""],
        ["2", "1号线", "正线", "接触网（轨）系统设备", "隔离开关", "A", "集中修", "", "", "", "", ""],
    ]
    doc = DocumentModel(
        source_name="8月份设备管控措施（每月20号更新）(2).xlsx",
        source_path="x.xlsx",
        suffix=".xlsx",
        blocks=[
            Block(type="heading", text="工作表:接触网专业", level=1),
            Block(type="table", rows=rows),
        ],
    )
    ctrl = extract_controls([doc])
    assert not ctrl.get("prose")
    assert not ctrl.get("appendix")


def test_two_control_excels_both_listed_in_source():
    """设备树 + 月度补充都进 3.4 时，标题出处要两份文件名都留着。"""
    tree = _tree(
        ["1", "1号线", "正线", "供电", "变压器设备", "A", "设备树措施甲", "", "", "", "", ""],
    )
    monthly = DocumentModel(
        source_name="8月份设备管控措施（每月20号更新）(2).xlsx",
        source_path="y.xlsx",
        suffix=".xlsx",
        blocks=[
            Block(type="heading", text="工作表:变电专业", level=1),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
                    ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
                    ["1", "1号线", "正线", "供电", "电力监控设备", "C", "月度补充措施乙", "", "", "", "", ""],
                ],
            ),
        ],
    )
    ctrl = extract_controls([tree, monthly])
    src = ctrl.get("source") or ""
    assert "0管控措施（设备树）.xlsx" in src
    assert "8月份设备管控措施（每月20号更新）(2).xlsx" in src
    blob = "\n".join("\n".join(x.get("blocks") or []) for x in ctrl.get("prose") or [])
    assert "设备树措施甲" in blob
    assert "月度补充措施乙" in blob
