# -*- coding: utf-8 -*-
"""材料分拣：按各章能否抽出内容建议，不按文件名绑死章节。总表今年两章都能抽到才会同时建议。"""
from pathlib import Path

from catalog.classify_materials import (
    _should_ask_llm,
    classify_document,
    classify_paths,
    pick_overhead_material,
    pick_power_material,
)
from parsers.document_model import Block, DocumentModel
from scope.grade_matrix import GRADE_COLUMNS


def _doc(name: str, blocks: list[Block], path: str = "") -> DocumentModel:
    return DocumentModel(source_name=name, source_path=path or name, suffix=Path(name).suffix, blocks=blocks)


def test_grade_matrix_goes_to_ch3_and_ch4():
    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    doc = _doc("设备评估结果总表（4月）_1.xlsx", [Block("table", rows=[header, row])])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    ids = {x["chapter_id"] for x in judged["chapters"]}
    assert ids == {"ch3", "ch4"}  # 两章都能从这份表抽出内容，不是文件名写死两章
    assert not judged["skip_reason"]


def test_controls_tree_goes_to_ch3_only():
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]
    doc = _doc("0管控措施（设备树）.xlsx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch3"]


def test_line_report_without_chapter_tables_not_forced():
    doc = _doc(
        "2026年上海市城市轨道交通设施设备运营评估报告（1号线）.docx",
        [Block("paragraph", "线路概述"), Block("paragraph", "本线共有变电站若干座。")],
        path=r"F:\材料\00-线路报告\1号线.docx",
    )
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged.get("bucket") == "power"
    assert judged["chapters"] == []
    assert "线路报告" not in (judged["skip_reason"] or "")


def test_grade_table_in_line_report_folder_still_classified():
    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    doc = _doc(
        "设备评估结果总表（4月）_1.xlsx",
        [Block("table", rows=[header, row])],
        path=r"F:\材料\00-线路报告\设备评估结果总表（4月）_1.xlsx",
    )
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    ids = {x["chapter_id"] for x in judged["chapters"]}
    assert "ch3" in ids and "ch4" in ids


def test_named_like_old_skip_still_classified_by_content():
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]
    doc = _doc("设备评估表.xlsx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch3"]


def test_overhead_file_skipped_for_power():
    doc = _doc("2026年接触网评估报告.docx", [Block("paragraph", "接触网刚性悬挂")])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged["chapters"] == []
    assert judged.get("bucket") == "overhead"
    assert "接触网" in judged["skip_reason"]
    assert pick_power_material(doc, use_llm=False)["bucket"] == "overhead"


def test_power_file_in_overhead_folder_still_classified():
    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    doc = _doc(
        "设备评估结果总表（4月）_1.xlsx",
        [Block("table", rows=[header, row])],
        path=r"F:\材料\补充材料\接触网\设备评估结果总表（4月）_1.xlsx",
    )
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    ids = {x["chapter_id"] for x in judged["chapters"]}
    assert ids == {"ch3", "ch4"}
    assert judged.get("bucket") in {"power", "mixed"}
    assert not judged["skip_reason"]


def test_named_overhead_but_power_content_still_classified():
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]
    doc = _doc("接触网专业月报.xlsx", [Block("table", rows=rows)], path=r"F:\材料\触网\接触网专业月报.xlsx")
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch3"]


def test_mixed_controls_workbook_keeps_power_drops_overhead_sheet():
    power_rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]
    oh_rows = [
        ["序号", "线路", "区段", "子系统", "设备", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "1号线", "正线", "接触网", "刚性接触网", "B", "接触线更换", "", "", "", "", ""],
    ]
    doc = _doc(
        "8月份设备管控措施（每月20号更新）(2).xlsx",
        [
            Block("heading", "工作表:变电专业", level=1),
            Block("table", rows=power_rows),
            Block("heading", "工作表:接触网专业", level=1),
            Block("table", rows=oh_rows),
        ],
        path=r"F:\材料\补充材料\8月份设备管控措施（每月20号更新）(2).xlsx",
    )
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged.get("bucket") == "mixed"
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch3"]
    from chapters.power.extract import extract_controls

    ctrl = extract_controls([doc])
    blob = " ".join(" ".join(str(c) for c in row) for row in (ctrl.get("appendix") or []))
    assert "变压器设备" in blob
    assert "刚性接触网" not in blob
    assert "接触线更换" not in blob


def test_overhead_only_sheet_not_assigned_to_power():
    oh_rows = [
        ["序号", "线路", "区段", "子系统", "设备", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "1号线", "正线", "接触网", "刚性接触网", "B", "接触线更换", "", "", "", "", ""],
    ]
    doc = _doc(
        "补充管控措施.xlsx",
        [
            Block("heading", "工作表:接触网专业", level=1),
            Block("table", rows=oh_rows),
        ],
        path=r"F:\材料\补充材料\补充管控措施.xlsx",
    )
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged["chapters"] == []
    assert judged.get("bucket") == "overhead"
    assert "接触网" in judged["skip_reason"]


def test_power_header_but_only_overhead_mids_not_ch3():
    """表头长得像设备树，但中类全是触网设备时，不能建议进供电第3章。"""
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "1号线", "正线", "接触网（轨）系统设备", "刚性接触网", "B", "接触线更换", "", "", "", "", ""],
        ["2", "1号线", "正线", "接触网（轨）系统设备", "隔离开关", "A", "集中修", "", "", "", "", ""],
    ]
    doc = _doc("假供电设备树.xlsx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert "ch3" not in {x["chapter_id"] for x in judged["chapters"]}
    from chapters.power.extract import extract_controls

    assert not extract_controls([doc]).get("appendix")
    assert not extract_controls([doc]).get("prose")


def test_risk_list_not_treated_as_controls_tree():
    rows = [
        ["序号", "风险类别", "划分单元", "", "风险点描述", "风险点位", "风险等级评估", "", "", "管控措施"],
        ["", "", "一级", "二级", "", "", "可能性判定标准", "后果严重程度", "风险等级", "作业标准"],
        [
            "1",
            "检修施工",
            "施工管理",
            "接触网作业",
            "轨行区作业冲突",
            "接触网专业",
            "过去一年本线路发生过作业冲突",
            "严重",
            "R3",
            "接触网维修作业指导书",
        ],
    ]
    doc = _doc("供电分公司风险清单（新版辨识8.25）.xlsx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged["chapters"] == []
    assert judged.get("bucket") in {"power", "mixed"}  # 供电分公司材料第一步要收下
    from chapters.power.extract import extract_controls

    ctrl = extract_controls([doc])
    assert not (ctrl.get("prose") or [])
    assert len(ctrl.get("appendix") or []) <= 1


def test_real_spare_docx_parses_to_ch9():
    path = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料\评估材料（备件）.docx")
    if not path.exists():
        return
    from parsers.dispatch import parse_file

    doc = parse_file(path)
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch9"]
    assert any(b.type == "table" and b.rows and "物料名称" in "".join(str(c) for c in b.rows[0]) for b in doc.blocks)


def test_stock_table_goes_to_ch9():
    rows = [
        ["序号", "设备大类", "设备中类", "设备小类", "物料名称", "规格型号", "计量单位", "安全库存数量"],
        ["1", "供电", "变压器", "干变", "套管", "10kV", "套", "1"],
    ]
    doc = _doc("评估材料（备件）.docx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert [x["chapter_id"] for x in judged["chapters"]] == ["ch9"]


def test_mtbf_section_goes_to_ch4_via_full_text():
    """4.4 生产指标即使埋在文件后半段，全文扫描也应建议第4章。"""
    filler = [Block("paragraph", f"前置说明第{i}段，与生产指标无关。") for i in range(60)]
    blocks = filler + [
        Block("heading", "4.4  各线路供电系统年度生产指标", level=2),
        Block("paragraph", "截至年底共有5个供电专业可靠性指标。"),
        Block(
            "table",
            rows=[
                ["序号", "指标名称", "指标单位", "当月值"],
                ["1", "供电变电所MTBF(R)", "万小时", "2.39"],
            ],
        ),
    ]
    doc = _doc("4&7评估报告材料.docx", blocks)
    judged = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert "ch4" in {x["chapter_id"] for x in judged["chapters"]}
    assert any("生产指标" in (x.get("reason") or "") or "MTBF" in (x.get("reason") or "") for x in judged["chapters"])


def test_prior_outline_adds_production_need():
    from catalog.classify_materials import build_prior_needs

    prior = _doc(
        "去年供电年报.docx",
        [
            Block("heading", "4  运营契合满足度评估", level=1),
            Block("heading", "4.4  各线路供电系统年度生产指标", level=2),
            Block("paragraph", "可靠性指标说明"),
        ],
    )
    needs = build_prior_needs([prior])
    assert needs["has_prior"]
    assert any("生产指标" in k or "MTBF" in k for k in needs["by_chapter"]["ch4"])


def test_overhead_domain_classifies_overhead_not_power_rules():
    """接触网域：纯供电总表（无触网列命中）不套供电规则乱分章；触网材料可分章。"""
    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    power_doc = _doc("设备评估结果总表（4月）_1.xlsx", [Block("table", rows=[header, row])])
    judged = classify_document(power_doc, domain_id="overhead", use_llm=False)
    # 纯供电总表在触网域应跳过或分不出触网章
    assert judged.get("bucket") in {"power", "overhead", "mixed", ""}
    if judged.get("bucket") == "power":
        assert judged["chapters"] == []
        assert "供电" in judged["skip_reason"] or "接触网" in judged["skip_reason"]

    oh = _doc(
        "接触网管控措施.xlsx",
        [
            Block("heading", "工作表:接触网专业", level=1),
            Block(
                "table",
                rows=[
                    ["线路", "区段", "子系统", "设备", "评估结果", "管控措施"],
                    ["1号线", "正线", "接触网", "刚性接触网", "B", "加强巡视"],
                ],
            ),
        ],
    )
    judged2 = classify_document(oh, domain_id="overhead", use_llm=False)
    assert judged2.get("bucket") in {"overhead", "mixed"}
    # 至少不应再报「规则尚未接入」
    assert "尚未接入" not in (judged2.get("skip_reason") or "")


def test_real_zong_table_if_present():
    zong = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料\设备功能有效性\设备评估结果总表（4月）_1.xlsx")
    if not zong.exists():
        return
    data = classify_paths([zong], domain_id="power_supply", use_llm=False)
    assert data["assigned"] == 1
    ids = {x["chapter_id"] for x in data["files"][0]["chapters"]}
    assert "ch3" in ids and "ch4" in ids


def test_same_content_suggested_once():
    from tempfile import TemporaryDirectory

    from openpyxl import Workbook

    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    ctrl = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]

    def write_xlsx(path: Path, rows: list[list[str]]) -> None:
        wb = Workbook()
        ws = wb.active
        for item in rows:
            ws.append(item)
        wb.save(path)

    with TemporaryDirectory() as folder:
        root = Path(folder)
        a = root / "设备评估结果总表（4月）.xlsx"
        b = root / "设备评估结果总表（4月）_1.xlsx"
        c = root / "备份包" / "设备评估结果总表（4月）.xlsx"
        d = root / "0管控措施（设备树）.xlsx"
        c.parent.mkdir()
        write_xlsx(a, [header, row])
        write_xlsx(b, [header, row])
        write_xlsx(c, [header, row])
        write_xlsx(d, ctrl)
        data = classify_paths([a, b, c, d], relpaths=[a.name, b.name, f"备份包/{c.name}", d.name], domain_id="power_supply", use_llm=False)
    names = [x["name"] for x in data["by_chapter"]["ch3"]]
    assert names.count("0管控措施（设备树）.xlsx") == 1
    assert names.count("设备评估结果总表（4月）_1.xlsx") == 1  # 重复总表只建议一份，留带 _1 的
    assert "设备评估结果总表（4月）.xlsx" not in names  # 同内容无后缀/备份不进建议
    assert data["assigned"] == 2  # 总表一份 + 管控措施一份
    assert data["power_picked"] == 2
    assert len(data.get("power_files") or []) == 2
    assert data["overhead_dropped"] == 0


def test_power_text_with_one_overhead_mention_is_kept():
    paras = [Block("paragraph", "变电站运行正常，整流机组负荷平稳。") for _ in range(6)]
    paras.append(Block("paragraph", "涉及接触网作业时注意停电"))
    doc = _doc("变电专业月报.docx", paras)
    assert pick_power_material(doc, use_llm=False)["bucket"] in {"power", "mixed"}


def test_late_table_row_still_picked_as_power():
    rows = [["序号", "设备"]] + [[str(i), "其他"] for i in range(1, 50)]
    rows.append(["50", "1号线变电站"])
    doc = _doc("设备清单.xlsx", [Block("table", rows=rows)])
    assert pick_power_material(doc, use_llm=False)["bucket"] in {"power", "mixed"}


def test_force_power_reclaims_overhead_file():
    doc = _doc("2026年接触网评估报告.docx", [Block("paragraph", "接触网刚性悬挂")])
    assert classify_document(doc, domain_id="power_supply", use_llm=False)["bucket"] == "overhead"
    judged = classify_document(doc, domain_id="power_supply", use_llm=False, force_power=True)
    assert judged["bucket"] == "power"
    assert judged.get("pick_via") == "manual"
    assert _should_ask_llm(doc, "overhead") is False


def test_overhead_excel_headers_auto_suggest_ch3_ch4():
    """文件名、工作表名都不带「接触网」时，仍应按表头自行建议第 3、4 章。"""
    flex = [
        ["序号", "线路", "锚段号", "承力索", "评价"],
        ["1", "1号线", "CW1", "90", "A"],
        ["2", "1号线", "CW2", "70", "C"],
    ]
    system = [
        ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏", "系统状态值S1", "系统状态等级"],
        ["_1号线", "正线", "/", "94", "/", "72", "94", "92", "A"],
    ]
    doc = _doc(
        "all new.xlsx",
        [
            Block("heading", "工作表:柔性明细", level=1),
            Block("table", rows=flex),
            Block("heading", "工作表:线路评分", level=1),
            Block("table", rows=system),
        ],
    )
    assert pick_power_material(doc, use_llm=False)["bucket"] == "overhead"
    picked = pick_overhead_material(doc, use_llm=False)
    assert picked["bucket"] == "overhead"
    assert "表头" in (picked.get("reason") or "")
    judged = classify_document(doc, domain_id="overhead", use_llm=False)
    ids = {x["chapter_id"] for x in judged["chapters"]}
    assert "ch3" in ids and "ch4" in ids
    assert any("表头" in (x.get("reason") or "") for x in judged["chapters"])


def test_compliance_pack_stays_in_overhead():
    from chapters.common.domain_filter import is_compliance_pack, is_power_only_doc, prepare_overhead_docs

    doc = _doc(
        "5&6合规性材料(2026).docx",
        [
            Block("paragraph", "管理体系合规性评估"),
            Block("paragraph", "对上一年度合规性评估建议的整改"),
            Block("paragraph", "（11）《接触网（轨）设备安装工艺细则》修订内容为："),
            Block("paragraph", "1号线变电站运行细则也在这份合订本里。"),
        ],
    )
    assert is_compliance_pack(doc)
    assert not is_power_only_doc(doc)
    assert prepare_overhead_docs([doc])


def test_shared_pack_stock_and_retire_stay_in_overhead():
    from chapters.common.domain_filter import is_power_only_doc, is_shared_domain_pack, prepare_overhead_docs

    stock = _doc(
        "附件1：《维保供电安全库存管理规定》（QSD-WBZ-FB-AQ-GDG59—2025）.pdf",
        [
            Block("paragraph", "本规定适用于供电专业安全库存管理。"),
            Block("paragraph", "变电所备件按附录执行。"),
            Block(
                "table",
                rows=[
                    ["序号", "大类", "中类", "物料名称", "型号", "安全库存配置总数量"],
                    ["1", "触网", "柔性接触网（通用）", "铜银接触线", "CTA-120", "6800"],
                ],
            ),
        ],
    )
    retire = _doc(
        "11退运材料.docx",
        [
            Block("heading", "退运报废倾向性评估"),
            Block("paragraph", "3号线需报废6台隔离开关，一台空气除湿机。"),
            Block("paragraph", "6号线共计9台整流变压器需报废。"),
        ],
    )
    power_plan = _doc(
        "4&7评估报告材料（ly）.docx",
        [
            Block("heading", "4.4 各线路供电系统年度生产指标"),
            Block("paragraph", "供电变电所MTBF指标涵盖110kV设备。"),
            Block("paragraph", "表6-1生产计划执行情况表"),
            Block(
                "table",
                rows=[["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"], ["1", "1号线", "5545", "5545", "100%"]],
            ),
        ],
    )
    oh_plan = _doc(
        "4^07评估报告材料（生产计划）(2).docx",
        [
            Block("paragraph", "表6-1变电生产计划执行情况表"),
            Block(
                "table",
                rows=[["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"], ["1", "1号线", "4609", "4609", "100%"]],
            ),
            Block("paragraph", "表6-1触网生产计划执行情况表"),
            Block(
                "table",
                rows=[["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"], ["1", "1号线", "1102", "1102", "100%"]],
            ),
        ],
    )
    assert is_shared_domain_pack(stock)
    assert not is_power_only_doc(stock)
    assert prepare_overhead_docs([stock])
    assert is_shared_domain_pack(retire)
    assert not is_power_only_doc(retire)
    assert prepare_overhead_docs([retire])
    assert not is_shared_domain_pack(power_plan)
    assert is_power_only_doc(power_plan)
    assert prepare_overhead_docs([power_plan]) == []
    assert is_shared_domain_pack(oh_plan)
    assert not is_power_only_doc(oh_plan)
    assert prepare_overhead_docs([oh_plan])


def test_power_fault_situation_stays_out_of_overhead():
    """供电 4.3「故障情况」稿不能进触网分拣/抽取。"""
    from chapters.common.domain_filter import (
        is_power_fault_situation_doc,
        is_power_only_doc,
        prepare_overhead_docs,
        prepare_power_docs,
    )

    doc = _doc(
        "评估材料（故障情况，黄色待更新）.docx",
        [
            Block("heading", "4.3 各个线路基本情况"),
            Block("paragraph", "1号线降压系统故障3起，牵引站直流开关动作，应急电源系统故障1起。"),
        ],
    )
    assert is_power_fault_situation_doc(doc)
    assert is_power_only_doc(doc)
    assert prepare_overhead_docs([doc]) == []
    assert prepare_power_docs([doc])
    judged_oh = classify_document(doc, domain_id="overhead", use_llm=False)
    assert judged_oh["bucket"] == "power"
    assert judged_oh["chapters"] == []
    judged_pw = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged_pw["bucket"] in {"power", "mixed"}
    assert "ch4" in {x["chapter_id"] for x in judged_pw["chapters"]}


def test_overhead_specialty_word_stays_out_of_power():
    """维护部接触网专稿不能进供电分拣/抽取。"""
    from chapters.common.domain_filter import is_overhead_only_doc, prepare_overhead_docs, prepare_power_docs

    doc = _doc(
        "（维护七部）01-2026年上海市城市轨道交通设施设备运营评估报告.docx",
        [
            Block("heading", "8.18号线接触网专业"),
            Block("paragraph", "各线路接触网故障趋势分析如下。刚性接触网状态总体稳定。"),
            Block("paragraph", "接触网设备状态分布见表。"),
        ],
    )
    assert is_overhead_only_doc(doc)
    assert prepare_power_docs([doc]) == []
    assert prepare_overhead_docs([doc])
    judged_pw = classify_document(doc, domain_id="power_supply", use_llm=False)
    assert judged_pw["bucket"] == "overhead"
    judged_oh = classify_document(doc, domain_id="overhead", use_llm=False)
    assert judged_oh["bucket"] in {"overhead", "mixed"}


def test_build_prior_needs_split_by_domain():
    from catalog.classify_materials import build_prior_needs

    prior = _doc(
        "去年年报.docx",
        [
            Block("heading", "4.3 各个线路基本情况"),
            Block("heading", "4.3 各线路接触网故障趋势分析"),
        ],
    )
    pw = build_prior_needs([prior], domain_id="power_supply")
    oh = build_prior_needs([prior], domain_id="overhead")
    assert any("各个线路基本情况" in k for k in pw["by_chapter"]["ch4"])
    assert not any("接触网故障" in k for k in pw["by_chapter"]["ch4"])
    assert any("接触网故障" in k for k in oh["by_chapter"]["ch4"])
    assert not any("各个线路基本情况" in k for k in oh["by_chapter"]["ch4"])


def test_named_overhead_but_power_content_dropped_in_overhead_domain():
    rows = [
        ["序号", "线路", "区段", "大类", "中类", "评估结果", "管控措施", "", "", "", "", ""],
        ["", "", "", "", "", "", "大修更新改造", "差异化管控", "核心部件更换", "成本内项目", "备件储备情况", "故障影响运营程度"],
        ["1", "2号线", "正线", "供电", "变压器设备", "A", "暂未纳入大修", "", "", "", "", ""],
    ]
    doc = _doc("接触网专业月报.xlsx", [Block("table", rows=rows)])
    judged = classify_document(doc, domain_id="overhead", use_llm=False)
    assert judged["bucket"] == "power"
    assert judged["chapters"] == []


def test_skip_llm_review_when_rules_enough(monkeypatch):
    from catalog import classify_materials as cm

    called: list[int] = []

    def boom(*_a, **_k):
        called.append(1)
        return []

    monkeypatch.setattr(cm, "_llm_review_chapters", boom)
    monkeypatch.setattr(cm, "_llm_domain", lambda _doc: "power")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")

    header = ["大类", "线路", "区段", *GRADE_COLUMNS[:6]]
    row = ["供电", "1号线", "正线", "A", "B", "B", "A", "A", "B"]
    xlsx = _doc("设备评估结果总表（4月）_1.xlsx", [Block("table", rows=[header, row])])
    judged = classify_document(xlsx, domain_id="power_supply", use_llm=True)
    assert {x["chapter_id"] for x in judged["chapters"]} == {"ch3", "ch4"}
    assert called == []

    rule = _doc("安全库存管理规定.pdf", [Block("paragraph", "库存数量按企业标准执行。")])
    assert cm._should_llm_review(rule, [{"chapter_id": "ch9", "reason": "x"}]) is False

    empty = _doc("月度说明.docx", [Block("paragraph", "本月设备运行平稳。")])
    assert cm._should_llm_review(empty, []) is True