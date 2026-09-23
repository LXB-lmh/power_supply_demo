# -*- coding: utf-8 -*-
"""第8章：骨架从去年报告检测；风险数据库表头兼容25/26；正文只用当年材料。"""

from chapters.common.outline_detect import detect_chapter_outline
from chapters.power.extract import (
    extract_ch8,
    extract_risk_database_table,
    resolve_ch8_outline,
)
from chapters.power.prior_resolve import resolve_prior_docs
from chapters.power.write import write_chapter_docx
from parsers.document_model import Block, DocumentModel


def _doc(name: str, blocks: list[Block], path: str = "") -> DocumentModel:
    return DocumentModel(source_name=name, source_path=path or name, suffix=".docx", blocks=blocks)


def test_detect_ch8_outline_from_baseline():
    prior = resolve_prior_docs(None)
    nodes = detect_chapter_outline(
        prior.get("docs") or [],
        chapter_keys=("风险隐患闭环度评估",),
        stop_keys=("备件物资保障度评估", "第9章", "第九章"),
        chapter_no=8,
    )
    titles = [x["title"] for x in nodes]
    nums = [x["num"] for x in nodes]
    assert "风险隐患闭环度评估" in titles[0]
    assert any("风险数据库" in t for t in titles)
    assert any("手册" in t for t in titles)
    assert any("典型故障" in t for t in titles)
    assert any("评估小结" in t for t in titles)
    assert "8.1.1" in nums or any(n.startswith("8.1") for n in nums)


def test_resolve_ch8_outline_roles():
    hit = resolve_ch8_outline(resolve_prior_docs(None).get("docs"))
    roles = {n["num"]: n["role"] for n in hit["nodes"]}
    assert hit["via"] in {"prior", "fallback"}
    assert any(r == "risk_db" for r in roles.values())
    assert any(r == "handbook" for r in roles.values())
    assert any(r == "faults" for r in roles.values())
    assert any(r == "summary" for r in roles.values())


def test_risk_db_table_accepts_2025_and_2026_styles():
    style25 = _doc(
        "去年风格材料.docx",
        [
            Block(
                type="table",
                rows=[
                    ["类型", "风险项", "数量"],
                    ["检修施工", "轨行区施工；车场施工", "41"],
                    ["供电运维", "中高压设备；电缆", "193"],
                ],
            )
        ],
    )
    style26 = _doc(
        "供电分公司风险清单（新版辨识8.25）.xlsx",
        [
            Block(
                type="table",
                rows=[
                    ["供电分公司风险数据库说明", "", "", "", ""],
                    ["风险类别", "划分单元", "", "风险点（个数）", "R1/R2/R3/R4"],
                    ["", "一级", "二级", "", ""],
                    ["供电设施设备类", "1.变配电", "1.变压器 2.中高压设备", "87", "0/11/59/17"],
                    ["合计", "合计", "合计", "255", "1/13/147/93"],
                ],
            )
        ],
    )
    assert extract_risk_database_table([style25])["style"] == "2025"
    assert extract_risk_database_table([style25])["table"][1][0] == "检修施工"
    hit26 = extract_risk_database_table([style26])
    assert hit26["style"] == "2026"
    assert hit26["table"][0][0] == "风险类别" or "风险类别" in "".join(str(c) for c in hit26["table"][0])


def test_risk_detail_list_rejected():
    detail = _doc(
        "明细清单.xlsx",
        [
            Block(
                type="table",
                rows=[
                    ["序号", "风险类别", "划分单元", "", "风险点描述", "风险点位", "风险等级评估", "", "", "管控措施"],
                    ["", "", "一级", "二级", "", "", "可能性", "后果", "等级", "作业标准"],
                    ["1", "检修施工", "施工管理", "接触网作业", "冲突", "接触网", "标准", "严重", "R3", "指导书"],
                ],
            )
        ],
    )
    assert extract_risk_database_table([detail])["table"] == []


def test_extract_ch8_prefers_year_table_not_prior_numbers():
    year = _doc(
        "供电分公司风险清单.xlsx",
        [
            Block(
                type="table",
                rows=[
                    ["风险类别", "划分单元", "", "风险点（个数）", "R1/R2/R3/R4"],
                    ["", "一级", "二级", "", ""],
                    ["人员管理", "1.人员准入", "1.人员招录", "9", "0/0/8/1"],
                ],
            )
        ],
    )
    prior = _doc(
        "去年年报.docx",
        [
            Block(type="heading", text="风险隐患闭环度评估", level=1),
            Block(type="heading", text="设施设备年度突出事件分析", level=2),
            Block(type="heading", text="风险数据库", level=3),
            Block(type="table", rows=[["类型", "风险项", "数量"], ["检修施工", "轨行区", "41"]]),
            Block(type="heading", text="隐患排除手册", level=3),
            Block(type="heading", text="典型故障", level=3),
            Block(type="heading", text="评估小结", level=2),
            Block(type="heading", text="备件物资保障度评估", level=1),
        ],
    )
    pack = extract_ch8([year], [prior])
    assert pack["risk_table"][2][0] == "人员管理"
    assert pack["outline_via"] == "prior"
    assert any(n.get("role") == "risk_db" for n in pack["outline"])


def test_typical_faults_prefers_complete_triad_over_partial():
    """完整「现象+原因+处置」优先于只有抢修令长叙述；总数约 4 条。"""
    from chapters.power.extract import extract_typical_faults, CH8_FAULT_CASE_LIMIT

    doc = _doc(
        "混合.docx",
        [
            Block(type="paragraph", text="典型故障"),
            Block(type="paragraph", text="一、5号线环城东路混变211直流开关K0测试回路故障分析"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="5号线环城东路混变211直流开关跳闸，发布0564#抢修令。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="K0测试回路故障导致控制电源跳闸。"),
            Block(type="paragraph", text="处置措施："),
            Block(type="paragraph", text="更换综保与接触器后修复。"),
            Block(type="paragraph", text="二、8号线虹口足球场混变211直流开关综保装置故障分析"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="虹口足球场混变211直流开关分闸，发布0821#抢修令。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="输入板卡X11故障。"),
            Block(type="paragraph", text="处置措施："),
            Block(type="paragraph", text="更换综保装置后恢复。"),
            Block(type="paragraph", text="三、仅有叙述无结构"),
            Block(
                type="paragraph",
                text="2026年一起供电设备二类故障事件，9号线某站直流开关跳闸，发布0999#抢修令，现场处理后恢复。",
            ),
        ],
    )
    hit = extract_typical_faults([doc], [])
    assert len(hit.get("cases") or []) <= CH8_FAULT_CASE_LIMIT
    assert len(hit.get("cases") or []) >= 2
    assert all(c.get("complete") for c in (hit.get("cases") or [])[:2])
    body = "".join(hit["paras"])
    assert "环城东路" in body and "虹口足球场" in body
    assert "故障现象" in body and "处置措施" in body


def test_typical_faults_prefers_analysis_body_over_overhead_bullets():
    """按条打分：分析体优先；触网短条即使先出现也不取；出处列出用到的文件。"""
    from chapters.power.extract import extract_typical_faults

    overhead = _doc(
        "（维护七部）01-2026年评估报告.docx",
        [
            Block(type="paragraph", text="典型故障"),
            Block(type="paragraph", text="典型故障：14号线浦东大道站隔离开关PLC故障。"),
            Block(type="paragraph", text="典型故障：刚性段隧道壁腐蚀。"),
            Block(type="paragraph", text="典型故障：股道指示灯不亮。"),
        ],
    )
    analysis = _doc(
        "任意供电材料.docx",
        [
            Block(type="paragraph", text="典型故障"),
            Block(type="paragraph", text="一、5号线环城东路变211直流开关K0测试回路故障分析"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="1月2日7:48，5号线环城东路混变211直流开关跳闸，自动重合闸不成功。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="K0测试回路异常，涉及PLC与端子排。"),
            Block(type="paragraph", text="处置措施："),
            Block(type="paragraph", text="更换部件并修复回路后恢复。"),
            Block(type="paragraph", text="二、1号线灵石路主变电缆故障分析"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="主变侧电缆故障导致跳闸。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="电缆绝缘击穿。"),
            Block(type="paragraph", text="整改措施："),
            Block(type="paragraph", text="更换故障段电缆。"),
        ],
    )
    prior = _doc(
        "去年.docx",
        [
            Block(type="heading", text="典型故障", level=3),
            Block(type="paragraph", text="一、7号线芳华路混变直流开关故障"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="中央PSCADA显示系统未准备。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="BA装置异常。"),
            Block(type="paragraph", text="整改措施及建议："),
            Block(type="paragraph", text="加强巡视。"),
            Block(type="heading", text="评估小结", level=2),
        ],
    )
    hit = extract_typical_faults([overhead, analysis], [prior])
    body = "".join(hit["paras"])
    assert "环城东路" in body
    assert "故障现象" in body
    assert "灵石路" in body
    assert "股道指示灯" not in body
    assert "任意供电材料" in (hit.get("source") or "")
    assert "维护七部" not in (hit.get("source") or "")
    assert len(hit.get("cases") or []) >= 2


def test_typical_faults_splits_cases_and_penalizes_cross_paste():
    """同一文件多条切开；现象与原因串文的条目降权。"""
    from chapters.power.extract import extract_typical_faults

    doc = _doc(
        "评估材料（故障情况）.docx",
        [
            Block(type="paragraph", text="典型故障"),
            Block(type="paragraph", text="一、1号线灵石路主变33kV灵车牵开关差动保护跳闸"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="1号线灵石路主变33kV灵车牵开关差动保护跳闸，电缆破损。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="通河新村-共康路下行百米标228处33kV灵车牵B相电缆破损。"),
            Block(type="paragraph", text="整改措施及建议："),
            Block(type="paragraph", text="制作中间接头后修复。"),
            Block(type="paragraph", text="二、9号线松江南站混变1#整流变压器故障"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="9号线松江南站混变1#整流变压器A相筒体底部有放电现象。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="值班员到达现场查看211直流开关情况，确认PRO装置显示*号，初步判断为隔离放大器BA死机。"),
            Block(type="paragraph", text="整改措施及建议："),
            Block(type="paragraph", text="安排人员保驾。"),
            Block(type="paragraph", text="三、8号线虹口足球场混变211直流开关综保装置故障分析"),
            Block(type="paragraph", text="故障现象："),
            Block(type="paragraph", text="8号线虹口足球场混变211直流开关分闸，小车位置异常，发布0821#抢修令。"),
            Block(type="paragraph", text="故障原因分析："),
            Block(type="paragraph", text="综保装置输入板卡X11故障。"),
            Block(type="paragraph", text="处置措施："),
            Block(type="paragraph", text="更换综保装置后恢复双边供电。"),
        ],
    )
    hit = extract_typical_faults([doc], [])
    body = "".join(hit["paras"])
    assert "灵石路" in body
    assert "虹口足球场" in body or "X11" in body
    # 串文的松江南+BA死机不应压过正常条目成为唯一内容
    assert "BA死机" not in body or "灵石路" in body
    assert hit["source"] == "评估材料（故障情况）.docx"


def test_handbook_prefers_reform_supervision_type_not_patrol():
    """同文件多子表时，选「改造项目督查」类（施工前/中/后），不写死工作表名。"""
    from chapters.power.extract import extract_hazard_handbook

    doc = _doc(
        "隐患排查手册（巡视+作业+督查）.xlsx",
        [
            Block(type="heading", text="工作表:预防性试验", level=1),
            Block(
                type="table",
                rows=[
                    ["现场作业人员隐患排查手册", "", "", ""],
                    ["序号", "作业项目", "作业步骤", "隐患描述"],
                    ["1", "预防性试验", "作业前", "检查资质"],
                ],
            ),
            Block(type="heading", text="工作表:某专业改造项目督查", level=1),
            Block(
                type="table",
                rows=[
                    ["某某专业改造项目督查隐患排查手册", "", "", ""],
                    ["序号", "作业项目", "作业步骤", "隐患描述"],
                    ["1", "某某专业改造项目", "施工前", "气灭切换为手动"],
                    ["", "", "施工中", "检查安全措施"],
                    ["", "", "施工后", "气灭切回自动"],
                ],
            ),
            Block(type="heading", text="工作表:牵引变巡视", level=1),
            Block(
                type="table",
                rows=[
                    ["现场作业人员隐患排查手册", "", "", ""],
                    ["序号", "作业项目", "作业步骤", "隐患描述"],
                    ["1", "牵引变电站巡视", "入场安全措施", "确认身体无不适"],
                ],
            ),
        ],
    )
    prior = _doc(
        "去年.docx",
        [
            Block(type="heading", text="隐患排除手册", level=3),
            Block(
                type="table",
                rows=[
                    ["序号", "作业项目", "作业步骤", "隐患描述"],
                    ["1", "变电专业改造项目", "施工前", "气灭切换 工作许可人"],
                    ["1", "变电专业改造项目", "施工中", "施工负责人"],
                    ["1", "变电专业改造项目", "施工后", "施工许可人"],
                ],
            ),
            Block(type="heading", text="典型故障", level=3),
        ],
    )
    hit = extract_hazard_handbook([doc], [prior])
    assert hit["kind"] == "reform_supervision"
    body = "".join(str(c) for r in hit["table"] for c in r)
    assert "改造项目" in body and "施工前" in body
    assert "预防性试验" not in body
    assert "牵引变电站巡视" not in body


def test_write_ch8_emits_skeleton_not_dynamic_governance(tmp_path):
    from docx import Document

    pack = {
        "year": 2026,
        "ch8": extract_ch8(
            [
                _doc(
                    "风险清单.xlsx",
                    [
                        Block(
                            type="table",
                            rows=[
                                ["类型", "风险项", "数量"],
                                ["消防", "动火作业", "20"],
                            ],
                        )
                    ],
                ),
                _doc(
                    "隐患排查手册.xlsx",
                    [
                        Block(
                            type="table",
                            rows=[
                                ["序号", "作业项目", "作业步骤", "隐患描述"],
                                ["1", "试验", "作业前", "检查资质"],
                            ],
                        )
                    ],
                ),
                _doc(
                    "评估材料（故障情况）.docx",
                    [
                        Block(type="paragraph", text="典型故障"),
                        Block(type="paragraph", text="3号线发生典型故障1起，详情如下。"),
                        Block(type="paragraph", text="故障现象：开关跳闸。"),
                    ],
                ),
            ],
            resolve_prior_docs(None).get("docs"),
        ),
    }
    out = tmp_path / "ch8.docx"
    write_chapter_docx(pack, out, "ch8")
    texts = [p.text.strip() for p in Document(str(out)).paragraphs if p.text.strip()]
    joined = "\n".join(texts)
    assert "8.1.1" in joined and "风险数据库" in joined
    assert "手册" in joined
    assert "典型故障" in joined
    assert "评估小结" in joined
    assert "安全隐患排查动态治理" not in joined
    assert Document(str(out)).tables  # 至少有风险表或手册表
