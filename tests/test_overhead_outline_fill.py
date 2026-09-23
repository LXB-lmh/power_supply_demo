# -*- coding: utf-8 -*-
from chapters.overhead.extract import extract_chapter
from chapters.overhead.outline_fill import start_keys_for
from chapters.overhead.prior_resolve import resolve_prior_docs
from chapters.overhead.section_bundle import extract_subsection_bundle
from parsers.document_model import Block, DocumentModel


def test_bundle_allows_text_only_section():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2.1.5设备维护周期和维护内容", level=3),
            Block(type="paragraph", text="接触网巡视周期按检修规程执行，正线每月不少于一次。"),
            Block(type="heading", text="2.1.6接触网专业接触线磨耗预警值上报", level=3),
        ],
    )
    hit = extract_subsection_bundle(
        doc,
        start_keys=("设备维护周期和维护内容", "维护周期"),
        stop_keys=("磨耗预警",),
        require_table=False,
    )
    assert hit and not hit.get("empty")
    assert any("巡视周期" in (x.get("text") or "") for x in hit["flow"])


def test_ch4_fills_volume_change_and_quantity():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2.1.3设备体量和变化情况", level=2),
            Block(type="paragraph", text="18号线新增二期线路新增刚性接触网15.58条公里。"),
            Block(type="heading", text="2.1.4各个线路基本情况", level=2),
            Block(type="heading", text="设备数量", level=3),
            Block(type="paragraph", text="3号线柔性接触网179.15条公里。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    change = by["设备体量变化情况"].get("fill") or {}
    qty = by["设备数量"].get("fill") or {}
    change_blob = " ".join(change.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (change.get("flow") or []) if x.get("kind") == "para"
    )
    qty_blob = " ".join(qty.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (qty.get("flow") or []) if x.get("kind") == "para"
    )
    assert "15.58" in change_blob
    assert "179.15" in qty_blob


def test_ch10_env_item_from_dept_list():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="环境差异性评估", level=2),
            Block(type="paragraph", text="1）雷电"),
            Block(type="paragraph", text="沿线避雷器按规程检测，本年度动作记录见附表。"),
            Block(type="paragraph", text="2）粉尘"),
            Block(type="paragraph", text="车场粉尘较大区段增加清扫频次。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    env = by["环境差异性评估"].get("fill") or {}
    assert env and not env.get("empty")


def test_ch9_without_materials_stays_yellow():
    prior = resolve_prior_docs()
    pack = extract_chapter([], year=2026, chapter_id="ch9", prior_docs=prior["docs"], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    stock = by["接触网安全库存"].get("fill") or {}
    assert not any(x.get("kind") == "table" for x in (stock.get("flow") or []))
    assert not (stock.get("table") or [])
    assert "评估小结" in by


def test_start_keys_include_aliases():
    keys = start_keys_for("外来侵限", 2026)
    assert any("异物侵限" in k for k in keys)


def test_bundle_stops_at_next_chapter_paragraph():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路接触网故障趋势分析"),
            Block(type="paragraph", text="9号线，2025年自检自修类故障次数33次。"),
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="根据评估规范第7部分撰写。"),
        ],
    )
    hit = extract_subsection_bundle(
        doc,
        start_keys=("接触网故障趋势", "故障趋势分析"),
        stop_keys=("评估小结",),
    )
    blob = " ".join(x.get("text") or "" for x in (hit or {}).get("flow") or [])
    assert "自检自修" in blob
    assert "根据评估规范" not in blob


def test_ch9_skips_status_ledger_as_stock():
    flex = [
        ["序号", "线路", "锚段号", "评价"],
        ["1", "1号线", "CW1", "A"],
    ]
    stock = [
        ["物料名称", "规格型号", "安全库存数量"],
        ["铜银接触线", "CTA-120", "2"],
    ]
    docs = [
        DocumentModel(
            source_name="接触网系统（all new）.xlsx",
            source_path="x.xlsx",
            suffix=".xlsx",
            blocks=[
                Block(type="heading", text="工作表:柔性锚段", level=1),
                Block(type="table", rows=flex),
            ],
        ),
        DocumentModel(
            source_name="触网备件.xlsx",
            source_path="y.xlsx",
            suffix=".xlsx",
            blocks=[
                Block(type="heading", text="工作表:安全库存", level=1),
                Block(type="table", rows=stock),
            ],
        ),
    ]
    pack = extract_chapter(docs[:1], year=2026, chapter_id="ch9", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    assert not (by["接触网安全库存"].get("fill") or {}) or by["接触网安全库存"]["fill"].get("empty")
    pack2 = extract_chapter(docs, year=2026, chapter_id="ch9", prior_docs=[], prior_via="baseline_2025")
    by2 = {n["title"]: n for n in pack2["outline"]}
    fill = by2["接触网安全库存"].get("fill") or {}
    assert not any(x.get("kind") == "table" for x in (fill.get("flow") or []))
    assert not (fill.get("table") or [])


def test_ch11_flattens_retire_into_year_section():
    doc = DocumentModel(
        source_name="关于4号线供电系统设备报废的情况说明.docx",
        source_path="r4.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="4号线需报废4台隔离开关，原值共计147812.93元。4台隔离开关安装在宝山-海伦路区间。",
            ),
            Block(
                type="paragraph",
                text="隔离开关：因长期处于高污染区，隔离开关零部件已出现部分老化、锈蚀等情况。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch11", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通4号线" not in titles
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["2026年设备退运更换情况"].get("fill") or {})
    assert "147812.93" in blob
    assert "高污染区" in blob


def test_ch9_uses_prose_not_inventory_tables():
    doc = DocumentModel(
        source_name="修程修志.docx",
        source_path="x.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="备件物资保障度评估", level=1),
            Block(type="heading", text="接触网安全库存", level=2),
            Block(
                type="paragraph",
                text="评估将根据是否有安全库存，安全库存的数量进行评估。对于不同厂商，不同型号的核心部件或设施设备至少有一部/台安全备件。柔性接触网备件、刚性接触网和接触轨的备件数量满足安全库存要求，支持全路网库存要求。",
            ),
            Block(
                type="table",
                rows=[["物料名称", "规格型号", "安全库存数量"], ["铜银接触线", "CTA-120", "2"]],
            ),
            Block(type="heading", text="接触网安全库存备品备件", level=2),
            Block(type="paragraph", text="接触网安全库存备品备件详细数量如附录A、B、C所示。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch9", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    stock = by["接触网安全库存"].get("fill") or {}
    blob = " ".join(stock.get("paras") or [])
    assert "评估将根据是否有安全库存" in blob
    assert not any(x.get("kind") == "table" for x in (stock.get("flow") or []))
    app = by["接触网安全库存备品备件"].get("fill") or {}
    app_blob = " ".join(app.get("paras") or [])
    assert "附录" not in app_blob
    assert not any(x.get("kind") == "table" for x in (app.get("flow") or []))
    assert app.get("empty", True)


def test_ch10_does_not_clone_generic_env_onto_empty_lines():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="e.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="针对粉尘对接触网系统的影响，供电分公司已通过修订接触网检修规程规定明确对绝缘部件的清扫为一年一次，以此来有效减少粉尘对接触网系统安全运行的影响。",
            ),
            Block(
                type="paragraph",
                text="外部环境对触网系统可靠运行的影响不容忽视。一般电气设备都对工作环境有明确的要求。",
            ),
            Block(
                type="paragraph",
                text="2号线一期地下隧道段，环境因素主要为漏水、粉尘及侵限。针对漏水及外单位设备侵限因素，持续关注情况。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    lines = [n.get("title") for n in pack["outline"] if str(n.get("title") or "").startswith("轨道交通")]
    assert lines == ["轨道交通2号线"]
    by = {n["title"]: n for n in pack["outline"]}
    blob2 = " ".join((by["轨道交通2号线"].get("fill") or {}).get("paras") or [])
    assert "漏水、粉尘及侵限" in blob2
    assert "清扫为一年一次" not in blob2


def test_ch8_collects_fault_analysis_without_parent_heading():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="8号线联航路接触网设备断裂故障分析"),
            Block(type="paragraph", text="2025年11月26日联航路分段绝缘器断裂导致失电。"),
            Block(type="paragraph", text="备件物资保障度评估"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    assert any("断裂故障分析" in (n.get("title") or "") for n in pack["outline"])
    parent = by["设施设备年度突出事件分析"]
    assert parent.get("fill") and not parent["fill"].get("empty")


def test_ch7_instrument_from_inline_line_para():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="3号线接触网运维班组配置仪器仪表51台，均在检定周期内。"),
            Block(type="paragraph", text="4号线接触网运维班组配置仪器仪表20台。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通3号线" in titles
    assert "轨道交通4号线" in titles
    by = {n["title"]: n for n in pack["outline"]}
    inst = by["仪器仪表使用管理方面"].get("fill") or {}
    assert inst and not inst.get("empty")


def test_ch4_fault_trend_splits_to_line_headings():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="和2025年评估对比结果"),
            Block(type="paragraph", text="2号线，2025年自检自修类故障次数12次。"),
            Block(type="paragraph", text="6号线，2025年自检自修类故障次数8次。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通2号线" in titles
    assert "轨道交通6号线" in titles
    by = {n["title"]: n for n in pack["outline"]}
    cmp = by["和2025年评估对比结果"].get("fill") or {}
    blob = " ".join(cmp.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (cmp.get("flow") or []) if x.get("kind") == "para"
    )
    assert "自检自修" not in blob


def test_ch8_collects_event_analysis_alias():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="5号线莘庄车场触网闸刀控制屏柜PLC故障事件分析"),
            Block(type="paragraph", text="屏柜PLC模块损坏导致闸刀无法远方操作。"),
            Block(type="paragraph", text="备件物资保障度评估"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    assert any("PLC故障事件分析" in (n.get("title") or "") for n in pack["outline"])


def test_ch7_instrument_strips_list_prefix():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="2、9号线接触网运维涉及部门5个班组，我部共计在用维护仪器仪表136台。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通9号线" in titles
    assert "轨道交通2号线" not in titles


def test_ch3_controls_backfill_missing_line_from_word():
    excel = [
        ["序号", "线路", "区段", "子系统", "设备", "评估结果", "管控措施"],
        ["1", "1号线", "一期", "接触网", "柔性接触网", "C", "已纳入2021年1号线一北北大修更新改造项目，计划完成3站，已完成0站，完成率0%"],
        ["2", "5号线", "南延伸", "接触网", "刚性接触网", "B", ""],
    ]
    docs = [
        DocumentModel(
            source_name="接触网管控.xlsx",
            source_path="x.xlsx",
            suffix=".xlsx",
            blocks=[
                Block(type="heading", text="工作表:接触网专业", level=1),
                Block(type="table", rows=excel),
            ],
        ),
        DocumentModel(
            source_name="维护五部.docx",
            source_path="w.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="轨道交通5号线风险点及管控措施", level=2),
                Block(type="paragraph", text="隧道漏水：现有风险管控措施：定期查看并报工务处理。"),
                Block(type="paragraph", text="7号线设备状态："),
                Block(type="paragraph", text="柔性接触网：北延伸段纳入跟踪。"),
            ],
        ),
    ]
    pack = extract_chapter(docs, year=2026, chapter_id="ch3", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通1号线" not in titles
    assert "轨道交通5号线" in titles
    assert "轨道交通7号线" not in titles
    five = next(n for n in pack["outline"] if n.get("title") == "轨道交通5号线")
    blob = " ".join((five.get("fill") or {}).get("paras") or [])
    assert "隧道漏水" in blob
    assert "北延伸段" not in blob
    assert "完成率" not in blob


def test_ch3_controls_uses_overhaul_prose_not_excel_or_status_wear():
    docs = [
        DocumentModel(
            source_name="管控台账.xlsx",
            source_path="x.xlsx",
            suffix=".xlsx",
            blocks=[
                Block(type="heading", text="工作表:接触网专业", level=1),
                Block(
                    type="table",
                    rows=[
                        ["线路", "区段", "子系统", "设备", "评估结果", "管控措施"],
                        ["2号线", "正线", "接触网", "刚性接触网", "C", "已纳入2026年大修更新改造项目，未批复，完成率0%"],
                    ],
                ),
            ],
        ),
        DocumentModel(
            source_name="维护六部.docx",
            source_path="b.docx",
            suffix=".docx",
            blocks=[
                Block(type="paragraph", text="2号线C状态的区段是2号线西延伸。差异化管控是，加强巡视：接触线加强巡视，当接触线磨耗宽度达到10mm、接触线剩余高度达到10.5mm时对磨耗异常点进行标记跟踪。"),
                Block(type="heading", text="各线路管控措施", level=2),
                Block(type="heading", text="1.1.5轨道交通2号线", level=3),
                Block(type="paragraph", text="集中修项目：对2号线东延伸户外高架段及3个停车场开展集中修作业，需对2152个定位点开展集中修，需出动梯车数143台。"),
                Block(type="paragraph", text="大修更新改造：2号线西延伸已于2024年完成更新改造；2号线一期已于2025年完成更新改造。"),
                Block(type="paragraph", text="差异化管控：2号线东延伸户外段加强梯车巡视（原巡视频次1年/次调整为3月/次）。"),
                Block(type="heading", text="1.1.5轨道交通2号线", level=3),
                Block(type="paragraph", text="集中修项目：对2号线东延伸户外高架段及3个停车场开展集中修作业，需对2152个定位点开展集中修，需出动梯车数143台。"),
                Block(type="paragraph", text="大修更新改造：2号线西延伸已于2024年完成更新改造；2号线一期已于2025年完成更新改造。"),
                Block(type="paragraph", text="差异化管控：2号线东延伸户外段加强梯车巡视（原巡视频次1年/次调整为3月/次）。"),
                Block(type="heading", text="1.1.8轨道交通12号线", level=3),
                Block(type="paragraph", text="12号线一期、二期刚性接触网状态是B, 部分锚段是C状态。存在一些分险点。"),
                Block(type="paragraph", text="现有风险点的管控措施是：根据磨耗预警要求及时跟踪预警。"),
                Block(type="paragraph", text="1、差异化管控：12号线刚性段部分锚段接触线加速取流段磨耗较大。"),
            ],
        ),
        DocumentModel(
            source_name="维护五部.docx",
            source_path="w.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="1号线设备状态", level=2),
                Block(type="paragraph", text="接触网状态：1号线C状态的区段是北延伸。"),
                Block(type="paragraph", text="集中修项目：1）柔性户外集中修项目，对1号线北延伸及停车场区段开展集中修作业。"),
                Block(type="paragraph", text="大修更新改造：1号线北延伸段已纳入了2024年接触网更新改造项目。"),
                Block(type="paragraph", text="差异化管控：1号线南延伸区段加强走梯巡视（原巡视频次1年/次调整为3月/次）。"),
            ],
        ),
    ]
    pack = extract_chapter(docs, year=2026, chapter_id="ch3", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    two = " ".join((by["轨道交通2号线"].get("fill") or {}).get("paras") or [])
    one = " ".join((by["轨道交通1号线"].get("fill") or {}).get("paras") or [])
    assert two.count("2152") == 1
    assert "梯车巡视" in two
    assert "完成率" not in two
    assert "10.5mm" not in two
    assert "12号线刚性段" not in two
    twelve = " ".join((by["轨道交通12号线"].get("fill") or {}).get("paras") or [])
    assert "12号线刚性段" in twelve
    assert "集中修项目" in one
    assert "南延伸区段加强走梯巡视" in one
    assert "完成率" not in one


def test_ch4_compare_does_not_use_prior_year_numbers():
    material = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路接触网故障趋势分析"),
            Block(type="paragraph", text="2号线，2025年自检自修类故障次数12次。"),
        ],
    )
    prior = DocumentModel(
        source_name="上海轨道交通运营设施设备2025年年度评估报告（触网）.doc",
        source_path="p.doc",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="运营契合满足度评估", level=1),
            Block(type="heading", text="和2024年评估对比结果", level=2),
            Block(type="paragraph", text="与2024年相比，2025年接触网设备体量增加主要来自新线开通。"),
            Block(
                type="paragraph",
                text="1号线，2024年自检自修类故障次数13次，2025年总计发生141起设备故障。",
            ),
            Block(type="heading", text="评估小结", level=2),
        ],
    )
    pack = extract_chapter(
        [material],
        year=2026,
        chapter_id="ch4",
        prior_docs=[prior],
        prior_via="upload",
    )
    by = {n["title"]: n for n in pack["outline"]}
    cmp = by["和2025年评估对比结果"].get("fill") or {}
    blob = " ".join(cmp.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (cmp.get("flow") or []) if x.get("kind") == "para"
    )
    assert "2025年接触网设备体量增加" not in blob
    assert "141起" not in blob
    assert "自检自修" not in blob
    assert "体例回退" not in str(cmp.get("source") or "")


def test_ch8_collects_typical_fault_paragraph():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="（1）2号线典型故障：2025年12月世纪大道站发生拉弧，已开具抢修令处理完毕。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") or "" for n in pack["outline"]]
    assert any("2号线典型故障" in t or "世纪大道" in t for t in titles)


def test_ch8_collects_remote_title_without_fenxi():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="14号线浦东南路混变2111-2114触网闸刀中央无法遥控操作", level=2),
            Block(type="paragraph", text="中央无法遥控，现场确认辅助接点不到位。"),
            Block(type="heading", text="备件物资保障度评估", level=1),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") or "" for n in pack["outline"]]
    assert any("无法遥控" in t for t in titles)


def test_ch8_skips_chapter_wrapup_as_event():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="第五章：本年度共分析多起典型设备故障与突发事件，如8号线联航路接触网设备断裂故障抢修。",
            ),
            Block(type="heading", text="8号线联航路接触网设备断裂故障分析", level=2),
            Block(type="paragraph", text="2025年11月26日联航路分段绝缘器断裂，发布0866#抢修令。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") or "" for n in pack["outline"]]
    assert any("断裂故障分析" in t for t in titles)
    assert not any(t.startswith("第五章") for t in titles)


def test_ch8_collects_arc_and_refuse_close_without_typical_label():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="1号线新闸路上行车头处锚段关节位置存在拉弧，当晚数据并无异常，发布抢修令处理。",
            ),
            Block(
                type="paragraph",
                text="7号线后滩混变直流屏故障维修施工结束后2111-2114触网闸刀遥控、就地电动均无法合闸，肇嘉浜路-云台路上下行接触网单边供电。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    blob = " ".join(n.get("title") or "" for n in pack["outline"])
    assert "新闸路" in blob
    assert "后滩" in blob


def test_ch4_period_total_goes_to_trend_not_compare():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障。",
            ),
            Block(
                type="paragraph",
                text="1号线，2025年总计发生120起，2026年总计发生136起。",
            ),
            Block(
                type="paragraph",
                text="2号线，2025年总计发生80起，2026年总计发生90起。",
            ),
            Block(
                type="paragraph",
                text="3号线，2025年总计发生10起，2026年总计发生12起。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通1号线" in titles
    by = {n["title"]: n for n in pack["outline"]}
    line1 = by["轨道交通1号线"].get("fill") or {}
    blob1 = " ".join(line1.get("paras") or [])
    assert "期间" in blob1
    cmp = by["和2025年评估对比结果"].get("fill") or {}
    blobc = " ".join(cmp.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (cmp.get("flow") or []) if x.get("kind") == "para"
    )
    assert "2025年总计发生120起" in blobc
    assert "期间" not in blobc


def test_ch6_rectify_does_not_dump_power_chapter():
    doc = DocumentModel(
        source_name="维护二部.docx",
        source_path="d.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="变压器油色谱按周期检测，整流机组按修程执行。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="修正1本三级规程。"),
            Block(type="paragraph", text="《接触网（轨）设备安装工艺细则》修订内容为："),
            Block(type="paragraph", text="——新增刚性悬挂调整工艺条款。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch6", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    rect = by["对上一年度合规性评估建议的整改"].get("fill") or {}
    blob = " ".join(rect.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (rect.get("flow") or []) if x.get("kind") == "para"
    )
    titles = [n.get("title") or "" for n in pack["outline"]]
    assert "变压器油色谱" not in blob
    assert any("工艺细则" in t or "修正1本" in blob for t in titles) or "修正1本三级规程" in blob


def test_ch10_env_diff_does_not_use_use_env_alias():
    doc = DocumentModel(
        source_name="01-2025年线路变电专业、接触网专业.docx",
        source_path="e.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="使用环境符合性评估", level=1),
            Block(type="paragraph", text="变电站通风机房湿度超标，整流机组室粉尘较大。"),
            Block(type="paragraph", text="杂散电流监测装置按周期校验。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    env = by["环境差异性评估"].get("fill") or {}
    blob = " ".join(env.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (env.get("flow") or []) if x.get("kind") == "para"
    )
    assert "整流机组室" not in blob


def test_ch7_skips_power_instrument_para():
    doc = DocumentModel(
        source_name="维护二部.docx",
        source_path="d.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="2号线变电站配置仪器仪表30台，均在检定周期内。"),
            Block(type="paragraph", text="2号线接触网运维班组配置仪器仪表18台，均在检定周期内。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"] if n.get("title") == "轨道交通2号线"}
    node = by.get("轨道交通2号线") or {}
    blob = " ".join((node.get("fill") or {}).get("paras") or [])
    assert "接触网运维" in blob
    assert "变电站配置仪器仪表" not in blob


def test_ch7_instrument_follows_line_lead_without_keyword_in_heading():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="1号线：2025年05月01日~2026年04月30日共计完成生产计划1200项。"),
            Block(type="paragraph", text="我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(type="paragraph", text="年度培训：我部顺利完成《智能运维平台培训》。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通1号线" in titles
    blob = ""
    parent = ""
    for n in pack["outline"]:
        t = str(n.get("title") or "")
        if t == "仪器仪表使用管理方面":
            parent = t
        if t == "轨道交通1号线" and parent == "仪器仪表使用管理方面":
            blob = " ".join((n.get("fill") or {}).get("paras") or [])
            break
        if t in ("部门年度培训方面", "智能化应用", "日常维修计划执行情况"):
            parent = t
    assert "维护仪器" in blob


def test_ch8_event_keeps_cause_and_rectify():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="ev.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="8号线联航路接触网设备断裂故障分析", level=2),
            Block(type="paragraph", text="2025年11月26日22:48，8号线联航路混变214直流开关跳闸，发布0866#抢修令。"),
            Block(type="paragraph", text="处置情况"),
            Block(type="paragraph", text="1、现场更换联航路分段绝缘器由西门子型号更换为浙江旺隆型号；"),
            Block(type="paragraph", text="原因分析"),
            Block(type="paragraph", text="西门子重型分段绝缘器绝缘子存在生产工艺缺陷。"),
            Block(type="paragraph", text="整改措施"),
            Block(type="paragraph", text="11月底前完成同批次分段绝缘器更换。"),
            Block(type="heading", text="评估小结", level=2),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    blob = " ".join(
        " ".join((n.get("fill") or {}).get("paras") or [])
        for n in pack["outline"]
        if "联航路" in str(n.get("title") or "")
    )
    assert "处置情况" in blob
    assert "原因分析" in blob
    assert "生产工艺缺陷" in blob
    assert "整改措施" in blob


def test_ch8_drops_generic_plc_rate_typical():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="plc.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="典型故障：9号线三期东延伸隔离开关PLC故障导致,新华厂家PLC产品存在故障率较高的问题。",
            ),
            Block(
                type="paragraph",
                text="（1）2号线典型故障：2025年12月世纪大道站发生拉弧，已开具抢修令处理完毕。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    titles = " ".join(n.get("title") or "" for n in pack["outline"])
    assert "世纪大道" in titles
    assert "三期东延伸" not in titles


def test_ch8_keeps_followup_rectify_and_short_title():
    doc = DocumentModel(
        source_name="（维护五部）评估(9.7补充标注).docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="7号线后滩混变直流屏故障维修施工结束后2111-2114触网闸刀遥控、就地电动均无法合闸，肇嘉浜路-云台路上下行接触网单边供电，经检查发现k1继电器二极管导通，更换后故障修复。",
            ),
            Block(type="paragraph", text="经分析：该二极管故障系上级直流屏故障维修后带负载送电导致击穿。"),
            Block(type="paragraph", text="后续整改措施：恢复控制柜供电时不能带下级负载直接送电。"),
            Block(type="paragraph", text="当年设备故障值38；前三年设备故障均值42 26 24"),
            Block(type="paragraph", text="设备故障趋势=23.91%"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    node = next(n for n in pack["outline"] if "后滩" in str(n.get("title") or ""))
    title = str(node.get("title") or "")
    blob = " ".join((node.get("fill") or {}).get("paras") or [])
    assert "故障分析" in title
    assert "无法合闸，肇嘉浜路" not in title
    assert "经分析" in blob
    assert "后续整改措施" in blob
    assert "设备故障趋势" not in blob


def test_ch8_strips_source_heading_num_and_restarts_list():
    doc = DocumentModel(
        source_name="（维护七部）评估(9.2补充标注).docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="14号线浦东南路混变2111-2114触网闸刀中央无法遥控操作", level=3),
            Block(type="paragraph", text="2025年6月10日3:40，14号线浦东南路混变2111-2114触网闸刀中央无法遥控操作，发布抢修令。"),
            Block(type="paragraph", text="7.1.1.2 原因分析"),
            Block(type="paragraph", text="综合判断此次故障为 PLC模块故障。"),
            Block(type="paragraph", text="7.1.1.3管控措施"),
            Block(type="paragraph", text="针对本次PLC故障问题，联系厂家做进一步的故障原因分析。"),
            Block(type="paragraph", text="3)梳理14号线PLC故障历史数据。"),
            Block(type="paragraph", text="4)针对PLC故障问题设置专人监护。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    node = next(n for n in pack["outline"] if "浦东南路" in str(n.get("title") or ""))
    blob = " ".join((node.get("fill") or {}).get("paras") or [])
    assert "故障分析" in str(node.get("title") or "")
    assert "7.1.1.2" not in blob
    assert "原因分析" in blob
    assert "管控措施" in blob
    assert "1)梳理14号线PLC" in blob
    assert "3)梳理" not in blob


def test_ch8_strips_date_prefix_from_xinzhuang_title():
    doc = DocumentModel(
        source_name="（维护五部）评估.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="202511185号线莘庄车场触网闸刀控制屏柜PLC故障事件。2025年11月18日凌晨，莘庄车场隔离开关柜PLC出现故障，发布0560#抢修令。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    title = next(n.get("title") or "" for n in pack["outline"] if "莘庄" in str(n.get("title") or ""))
    assert title == "5号线莘庄车场触网闸刀控制屏柜PLC故障事件分析"
    assert "20251118" not in title
    assert "85号线" not in title


def test_ch8_dept_order_seven_six_five():
    docs = [
        DocumentModel(
            source_name="（维护五部）评估.docx",
            source_path="a5.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="1号线新闸路锚段关节拉弧故障分析", level=3),
                Block(type="paragraph", text="1号线新闸路锚段关节位置存在拉弧，发布抢修令。"),
            ],
        ),
        DocumentModel(
            source_name="（维护六部）评估.docx",
            source_path="a6.docx",
            suffix=".docx",
            blocks=[
                Block(
                    type="paragraph",
                    text="（1）2号线典型故障：2号线世纪大道下行进站列车有拉弧现象，发布0226#抢修令。分段绝缘器导滑板有拉弧痕迹。",
                ),
            ],
        ),
        DocumentModel(
            source_name="（维护七部）评估.docx",
            source_path="a7.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="8号线联航路接触网设备断裂故障分析", level=3),
                Block(type="paragraph", text="2025年11月26日联航路分段绝缘器断裂，发布0866#抢修令。"),
            ],
        ),
    ]
    pack = extract_chapter(docs, year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    ev = [str(n.get("title") or "") for n in pack["outline"] if n.get("content_child")]
    assert any("联航路" in t for t in ev)
    assert any("世纪大道" in t for t in ev)
    assert any("新闸路" in t for t in ev)
    i7 = next(i for i, t in enumerate(ev) if "联航路" in t)
    i6 = next(i for i, t in enumerate(ev) if "世纪大道" in t)
    i5 = next(i for i, t in enumerate(ev) if "新闸路" in t)
    assert i7 < i6 < i5


def test_ch8_skips_dongjing_without_known_place():
    doc = DocumentModel(
        source_name="（维护六部）评估.docx",
        source_path="a6.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="（4）6号线典型故障：6号线接触网送电过程中东靖路混变2114触网闸刀中央遥控、站控均无法合闸，发布0682#抢修令。",
            ),
            Block(
                type="paragraph",
                text="（1）2号线典型故障：2号线世纪大道下行进站列车有拉弧现象，发布0226#抢修令。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    titles = " ".join(n.get("title") or "" for n in pack["outline"])
    assert "世纪大道" in titles
    assert "东靖路" not in titles


def test_ch8_write_keeps_source_without_child_num(tmp_path):
    from chapters.overhead.write import write_chapter_docx
    from parsers.docx_parser import parse_docx

    doc = DocumentModel(
        source_name="（维护七部）01-2026年评估(9.2补充标注).docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="8号线联航路接触网设备断裂故障分析", level=3),
            Block(type="paragraph", text="2025年11月26日联航路分段绝缘器断裂，发布0866#抢修令。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    out = tmp_path / "ch8.docx"
    write_chapter_docx(pack, out, "ch8")
    written = parse_docx(out)
    texts = [(b.text or "").strip() for b in written.blocks or [] if (b.text or "").strip()]
    blob = "\n".join(texts)
    assert "8号线联航路接触网设备断裂故障分析" in blob
    assert "8.1.1" not in blob
    assert "9.2补充标注" in blob
    assert "评估小结" in blob


def test_ch7_instrument_numbered_item_is_not_line_two():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="m6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="仪器仪表使用管理方面", level=3),
            Block(
                type="paragraph",
                text="2、9号线接触网运维涉及部门5个班组，我部共计在用维护仪器仪表136台。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通9号线" in titles
    assert "轨道交通2号线" not in titles


def test_ch10_env_walks_thunder_dust_after_lead():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="env17.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路环境符合性评估", level=2),
            Block(
                type="paragraph",
                text="17号线是由地面段、隧道段、一体化段及地面高架段组成，不同区段的接触轨系统所受外部环境的影响也是不同的。",
            ),
            Block(type="paragraph", text="1）雷电"),
            Block(type="paragraph", text="17号线雷电影响的区段主要是高架段、地面停车场。地面高架段接触轨系统的防雷系统每年于雷雨季前进行维护保养，包括避雷器。"),
            Block(type="paragraph", text="2）粉尘"),
            Block(type="paragraph", text="针对粉尘对接触轨系统的影响，检修规程规定对绝缘部件的检查为一年一次。"),
            Block(type="paragraph", text="评估结论与建议（匹配后续大修、成本内、集中修等项目申报）"),
            Block(type="paragraph", text="12号线一期、二期地下隧道段，环境因素主要为漏水、粉尘及侵限。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line17 = " ".join((by["轨道交通17号线"].get("fill") or {}).get("paras") or [])
    assert "外部环境" in line17
    assert "雷电" in line17
    assert "避雷器" in line17
    assert "粉尘" in line17
    assert "评估结论与建议" not in line17


def test_ch10_env_line_from_leakage_para():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="1号线南延伸区段，由于支柱开裂，已增加支柱巡视差异化计划。在一号线隧道段内，存在区间隧道壁漏水，当前均已经对线索设备加装了绝缘护套。",
            ),
            Block(
                type="paragraph",
                text="17号线是由地面段、隧道段、一体化段及地面高架段组成，不同区段的接触轨系统所受外部环境的影响也是不同的。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通1号线" in titles
    assert "轨道交通17号线" in titles
    by = {n["title"]: n for n in pack["outline"]}
    line1 = " ".join((by["轨道交通1号线"].get("fill") or {}).get("paras") or [])
    line17 = " ".join((by["轨道交通17号线"].get("fill") or {}).get("paras") or [])
    assert "支柱开裂" in line1
    assert "地面段" in line17


def test_ch11_skips_do_not_write_and_keeps_switch_retire():
    skip = DocumentModel(
        source_name="维护五部.docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="退运报废倾向性评估（不写）", level=1),
            Block(type="paragraph", text="本部门退运报废倾向性评估（不写）。"),
        ],
    )
    keep = DocumentModel(
        source_name="报废说明.docx",
        source_path="r.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="4号线需报废4台隔离开关，原值共计147812.93元，已达设计使用年限。",
            ),
        ],
    )
    pack = extract_chapter([skip, keep], year=2026, chapter_id="ch11", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通4号线" not in titles
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["2026年设备退运更换情况"].get("fill") or {})
    assert "147812.93" in blob
    assert "不写" not in blob


def _blob(fill: dict) -> str:
    return " ".join(fill.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (fill.get("flow") or []) if x.get("kind") == "para"
    )


def test_bundle_skips_toc_and_keeps_drawing():
    doc = DocumentModel(
        source_name="2025触网年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="5.2\t强制年检或评估情况分析\t71"),
            Block(type="paragraph", text="5.3\t法律法规的获取情况\t72"),
            Block(type="heading", text="强制年检或评估情况分析", level=2),
            Block(type="paragraph", text="如图5-1所示，对特种设备，采用定期强制检测。"),
            Block(type="drawing", source_index=10),
            Block(type="paragraph", text="图5-1 检测报告"),
            Block(type="paragraph", text="如图5-2是报废注册登记表。"),
            Block(type="drawing", source_index=12),
            Block(type="paragraph", text="图5-2 报废注册登记表"),
            Block(type="heading", text="法律法规的获取情况", level=2),
        ],
    )
    hit = extract_subsection_bundle(
        doc,
        start_keys=("强制年检",),
        stop_keys=("法律法规",),
    )
    assert hit and not hit.get("empty")
    kinds = [x.get("kind") for x in hit["flow"]]
    assert kinds.count("drawing") == 2
    assert any(x.get("source_index") == 10 for x in hit["flow"] if x.get("kind") == "drawing")
    assert any("如图5-1" in (x.get("text") or "") for x in hit["flow"])


def test_ch5_parent_and_eval_do_not_swallow_neighbors():
    doc = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="管理体系合规性评估", level=1),
            Block(type="heading", text="制度、标准执行情况检查", level=2),
            Block(type="paragraph", text="依据相关标准制定企业规范的管理制度"),
            Block(type="paragraph", text="为确定生产运营活动中适用的作业指导书与国标一致，建立了获取渠道。"),
            Block(type="paragraph", text="该步骤执行符合要求。"),
            Block(type="paragraph", text="关于识别和确认"),
            Block(type="paragraph", text="根据轨道交通供电标准化管理体系要求编制供电分公司适用的各级操作规程。"),
            Block(type="paragraph", text="该步骤执行符合要求。"),
            Block(type="heading", text="合规性评价", level=2),
            Block(type="paragraph", text="标准规划流程"),
            Block(type="paragraph", text="标准的规划、起草、审核、公示、修订、废止等方面的设计流程如图5-4所示："),
            Block(type="drawing", source_index=20),
            Block(type="paragraph", text="1. 流程设计与实际实施比较相符；流程和上级规程获取合理；"),
            Block(type="paragraph", text="2. 实施中增加了专家评审环节，降低主管审批的风险。"),
            Block(
                type="paragraph",
                text="对上一年度合规性评估建议的整改（参考《2025年修订文件目录》更新）（待提供后完善）",
            ),
            Block(type="paragraph", text="修正1本二级规程。"),
            Block(
                type="table",
                rows=[["表号", "名称", "编号"], ["1", "SCADA系统设备维修规程", "Q/SD-WBZ"]],
            ),
            Block(type="heading", text="评估小结", level=2),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch5", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    parent = _blob(by["制度、标准执行情况检查"].get("fill") or {})
    child = _blob(by["关于识别和确认"].get("fill") or {})
    assert "根据轨道交通供电标准化" not in parent
    assert "根据轨道交通供电标准化" in child
    eval_blob = _blob(by["合规性评价"].get("fill") or {}) + _blob(by["标准规划流程"].get("fill") or {})
    assert "流程设计与实际实施比较相符" in eval_blob
    assert "修正1本二级规程" not in eval_blob
    assert "SCADA" not in eval_blob
    eval_flow = (by["合规性评价"].get("fill") or {}).get("flow") or []
    plan_flow = (by["标准规划流程"].get("fill") or {}).get("flow") or []
    assert any(x.get("kind") == "drawing" for x in eval_flow + plan_flow)


def test_ch6_uses_chapter_window_not_power_or_ch5():
    """同一份材料里先有供电整改和第5章企标，再写第6章：只取本章窗口。"""
    doc = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="对上一年度合规性评估建议的整改（参考目录更新）（待提供后完善）"),
            Block(type="paragraph", text="修正1本二级规程。"),
            Block(type="paragraph", text="《SCADA系统设备及电能计量系统设备维修规程》修订内容为："),
            Block(type="paragraph", text="——调整了规范性引用文件；"),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(type="paragraph", text="表5-3 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[["专业", "等级", "2018年"], ["接触网", "一级", "1"]],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="制定相关团标，对触网系统的整体运维制定统一的标准。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="修订了3本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(
                type="table",
                rows=[["序号", "名称", "编号"], ["1", "柔性接触网维修作业指导书", "Q1"]],
            ),
            Block(type="paragraph", text="（1）《柔性接触网维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了线路设备情况；"),
            Block(type="paragraph", text="2、新增了1本一级规程、2本作业指导书。"),
            Block(type="paragraph", text="《申通地铁集团接触网零部件技术要求》规定了接触网主要零部件。"),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    line_rpt = DocumentModel(
        source_name="01-2025年线路变电专业、接触网专业.docx",
        source_path="line.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(
                type="paragraph",
                text="钢轨电位限制器维护保养作业指导书内安全措施及注意事项要求：施工前变电所牵引设备已停电。",
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack = extract_chapter([doc, line_rpt], year=2026, chapter_id="ch6", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    titles = [n.get("title") or "" for n in pack["outline"]]
    chunks: list[str] = []
    for n in pack["outline"]:
        chunks.append(str(n.get("title") or ""))
        chunks.append(_blob(n.get("fill") or {}))
        for x in ((n.get("fill") or {}).get("flow") or []):
            if x.get("kind") == "table":
                chunks.append(str(x.get("rows") or ""))
    all_blob = " ".join(chunks)
    assert not any("SCADA" in t for t in titles)
    intro = _blob(by["修程修制匹配性评估"].get("fill") or {})
    assert "团标" in intro
    assert "SCADA" not in intro
    assert "撰写" not in intro
    assert "钢轨电位" not in intro
    assert "柔性接触网维修作业指导书" in all_blob
    assert "更新了线路设备情况" in all_blob
    assert "SCADA" not in all_blob
    assert "修正1本二级规程" not in all_blob
    assert any("作业指导书" in t for t in titles)
    std = by["企业标准和制度"].get("fill") or {}
    std_blob = _blob(std)
    assert "如表6-1" in std_blob
    assert "表5-3" not in std_blob
    assert "新增了1本一级规程" not in std_blob
    assert "接触网零部件技术要求" not in std_blob
    tbl = " ".join(str(x.get("rows") or "") for x in (std.get("flow") or []) if x.get("kind") == "table")
    assert "接触网" in tbl.replace(" ", "")


def test_ch6_newest_compliance_keeps_overhead_revision_only():
    """当年编号的触网行进 6.1；上年 2025 作业指导书丢掉；6.2 收企标表和新增。"""
    older = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="制定相关团标，对触网系统的整体运维制定统一的标准。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="修订了3本作业指导书。"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "刚性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ328-2025"],
                    ["2", "柔性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ327-2025"],
                    ["3", "接触轨维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ329-2025"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    newer = DocumentModel(
        source_name="5&6合规性材料(2026).docx",
        source_path="d.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="法律法规的获取情况"),
            Block(type="paragraph", text="①继电器相关规程"),
            Block(type="paragraph", text="企业标准和制度"),
            Block(type="paragraph", text="具体数量如表3-1："),
            Block(
                type="table",
                rows=[["专业", "等级", "2026"], ["供电专业", "一级", "11"]],
            ),
            Block(type="paragraph", text="合规性评价"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="修正11本三级规程"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "1号线变电站运行细则", "Q/SD-WBZ-FB-SS-GDJ305-2026"],
                    ["11", "接触网（轨）设备安装工艺细则", "Q/SD-WBGD-FB-SS-06070001-2026"],
                ],
            ),
            Block(type="paragraph", text="（1）《1号线变电站运行细则》修订内容为："),
            Block(type="paragraph", text="——新增了电缆层巡视要求；"),
            Block(type="paragraph", text="（11）《接触网（轨）设备安装工艺细则》修订内容为："),
            Block(type="paragraph", text="——新增了接触线更换；"),
            Block(type="paragraph", text="修订了5本作业指导书："),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "变电设备维护保养作业指导书", "Qb"],
                ],
            ),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(type="paragraph", text="表5-3 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2018年", "2026年"],
                    ["触 网 专 业", "一级", "2", "3"],
                    ["触 网 专 业", "总计", "21", "12"],
                ],
            ),
            Block(type="paragraph", text="新增了1本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(
                type="table",
                rows=[["序号", "名称", "编号"], ["1", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"]],
            ),
            Block(type="paragraph", text="（1）《接触网（轨）集中修作业指导书》新增内容为："),
            Block(type="paragraph", text="——线路设备情况"),
            Block(type="paragraph", text="——接触轨定位点工艺工法"),
        ],
    )
    pack = extract_chapter(
        [older, newer],
        year=2026,
        chapter_id="ch6",
        prior_docs=[],
        prior_via="baseline_2025",
    )
    by = {n["title"]: n for n in pack["outline"]}
    titles = [str(n.get("title") or "") for n in pack["outline"]]
    assert "修正1本三级规程" in titles
    assert any("接触网（轨）设备安装工艺细则》修订内容" in t for t in titles)
    tbl_node = by["修正1本三级规程"]
    tbl_blob = "".join(
        str(c)
        for x in ((tbl_node.get("fill") or {}).get("flow") or [])
        if x.get("kind") == "table"
        for r in (x.get("rows") or [])
        for c in r
    )
    assert "06070001-2026" in tbl_blob
    assert "变电站运行细则" not in tbl_blob
    assert "GDJ328-2025" not in tbl_blob
    body = _blob((by[[t for t in titles if "修订内容" in t][0]].get("fill") or {}))
    assert "接触线更换" in body
    assert "电缆层巡视" not in body
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "修订了3本作业指导书" not in all_blob
    assert "GDJ327-2025" not in all_blob
    std = by["企业标准和制度"].get("fill") or {}
    std_blob = _blob(std)
    assert "如表6-1" in std_blob
    assert "表6-1" in std_blob
    assert "表5-3" not in std_blob
    assert "新增了1本作业指导书" in std_blob
    assert "线路设备情况" in std_blob
    tbl = " ".join(str(x.get("rows") or "") for x in (std.get("flow") or []) if x.get("kind") == "table")
    assert "集中修" in tbl
    assert "触网" in tbl.replace(" ", "")
    assert "供电专业" not in tbl
    assert "变电设备维护" not in tbl


def test_ch6_prefers_compliance_pack_over_revision_notes():
    """修程修志通稿（3本作业指导书 + 新增零部件）不能盖掉 5&6 当年工艺细则和表6-1。"""
    notes = DocumentModel(
        source_name="（修程修志部分）2026年评估报告（接触网专业）.docx",
        source_path="xiu.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="根据评估规范第7部分8.2.2条款的评估情况撰写；针对目前的修程修制。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="1、修订了3本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(type="paragraph", text="（1）《柔性接触网维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了线路设备情况；"),
            Block(type="paragraph", text="（2）《刚性接触网维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了安全措施及注意事项；"),
            Block(type="paragraph", text="（3）《接触轨维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了各接触轨维修作业流程；"),
            Block(type="paragraph", text="2、新增了1本一级规程、2本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "申通地铁集团接触网零部件技术要求", "Q/SD-ZG-J-KS-06070007-2026"],
                    ["2", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"],
                    ["3", "接触网（轨）设备安装工艺细则", "Q/SD-WBGD-FB-SS-06070001-2026"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack45 = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(
                type="paragraph",
                text="由于引入了比较新的维保技术，因此，在维保规程上也进行了更新和完善，包括对不同类型的变压器的大修周期进行了明确的归类和说明，更加符合实际设备的应用和大修需求，符合管理逻辑和科学度的要求。",
            ),
            Block(type="paragraph", text="制定相关团标，对触网系统的整体运维制定统一的标准，并补充与智能运维有关的维保规程。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="修订了3本作业指导书。"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "刚性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ328-2025"],
                    ["2", "柔性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ327-2025"],
                    ["3", "接触轨维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ329-2025"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack56 = DocumentModel(
        source_name="5&6合规性材料(2026).docx",
        source_path="d.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="修正11本三级规程"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "1号线变电站运行细则", "Q/SD-WBZ-FB-SS-GDJ305-2026"],
                    ["11", "接触网（轨）设备安装工艺细则", "Q/SD-WBGD-FB-SS-06070001-2026"],
                ],
            ),
            Block(type="paragraph", text="（11）《接触网（轨）设备安装工艺细则》修订内容为："),
            Block(type="paragraph", text="——新增了接触线更换；"),
            Block(type="paragraph", text="——新增了承力索更换"),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(type="paragraph", text="表5-3 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2018年", "2026年"],
                    ["触 网 专 业", "一级", "2", "3"],
                    ["触 网 专 业", "总计", "21", "12"],
                ],
            ),
            Block(type="paragraph", text="新增了1本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(
                type="table",
                rows=[["序号", "名称", "编号"], ["1", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"]],
            ),
            Block(type="paragraph", text="（1）《接触网（轨）集中修作业指导书》新增内容为："),
            Block(type="paragraph", text="——线路设备情况"),
            Block(type="paragraph", text="——接触轨定位点工艺工法"),
        ],
    )
    pack = extract_chapter(
        [notes, pack45, pack56],
        year=2026,
        chapter_id="ch6",
        prior_docs=[],
        prior_via="baseline_2025",
    )
    by = {n["title"]: n for n in pack["outline"]}
    titles = [str(n.get("title") or "") for n in pack["outline"]]
    assert "修正1本三级规程" in titles
    assert any("接触网（轨）设备安装工艺细则》修订内容" in t for t in titles)
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "接触线更换" in all_blob
    assert "修订了3本作业指导书" not in all_blob
    assert "柔性接触网维修作业指导书" not in all_blob
    intro = _blob(by["修程修制匹配性评估"].get("fill") or {})
    assert "团标" in intro
    assert "变压器" in intro
    std = by["企业标准和制度"].get("fill") or {}
    std_blob = _blob(std)
    assert "如表6-1" in std_blob
    assert "新增了1本作业指导书" in std_blob
    assert "新增了1本一级规程" not in std_blob
    assert "线路设备情况" in std_blob
    tbl = " ".join(str(x.get("rows") or "") for x in (std.get("flow") or []) if x.get("kind") == "table")
    assert "集中修" in tbl
    assert "零部件技术要求" not in tbl
    assert "触网" in tbl.replace(" ", "")


def test_ch6_without_56_uses_notes_spec_and_45_count_table():
    """没传 5&6 时：修程修志新增里的工艺细则进 6.1，4&5 章前触网分类表进 6.2，只留集中修。"""
    notes = DocumentModel(
        source_name="（修程修志部分）2026年评估报告（接触网专业）.docx",
        source_path="xiu.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="根据评估规范第7部分8.2.2条款的评估情况撰写；针对目前的修程修制。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="1、修订了3本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(type="paragraph", text="（1）《柔性接触网维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了线路设备情况；"),
            Block(type="paragraph", text="（2）《刚性接触网维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了安全措施及注意事项；"),
            Block(type="paragraph", text="（3）《接触轨维修作业指导书》修订内容为："),
            Block(type="paragraph", text="——更新了各接触轨维修作业流程；"),
            Block(type="paragraph", text="2、新增了1本一级规程、2本作业指导书。"),
            Block(type="paragraph", text="分别是："),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "申通地铁集团接触网零部件技术要求", "Q/SD-ZG-J-KS-06070007-2026"],
                    ["2", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"],
                    ["3", "接触网（轨）设备安装工艺细则", "Q/SD-WBGD-FB-SS-06070001-2026"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack45 = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(type="paragraph", text="表5-3 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2018年", "2026年"],
                    ["触 网 专 业", "一级", "2", "3"],
                    ["触 网 专 业", "作业指导书（不含其它三级）", "15", "6"],
                    ["触 网 专 业", "总计", "21", "12"],
                ],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(
                type="paragraph",
                text="由于引入了比较新的维保技术，因此，在维保规程上也进行了更新和完善，包括对不同类型的变压器的大修周期进行了明确的归类和说明，更加符合实际设备的应用和大修需求，符合管理逻辑和科学度的要求。",
            ),
            Block(type="paragraph", text="制定相关团标，对触网系统的整体运维制定统一的标准，并补充与智能运维有关的维保规程。"),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="修订了3本作业指导书。"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "刚性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ328-2025"],
                    ["2", "柔性接触网维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ327-2025"],
                    ["3", "接触轨维修作业指导书", "Q/SD-WBZ-FB-SS-GDJ329-2025"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack = extract_chapter(
        [notes, pack45],
        year=2026,
        chapter_id="ch6",
        prior_docs=[],
        prior_via="baseline_2025",
    )
    by = {n["title"]: n for n in pack["outline"]}
    titles = [str(n.get("title") or "") for n in pack["outline"]]
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "修正1本三级规程" in titles
    tbl_node = by["修正1本三级规程"]
    tbl_blob = "".join(
        str(c)
        for x in ((tbl_node.get("fill") or {}).get("flow") or [])
        if x.get("kind") == "table"
        for r in (x.get("rows") or [])
        for c in r
    )
    assert "06070001-2026" in tbl_blob
    assert "修订了3本作业指导书" not in all_blob
    assert "柔性接触网维修作业指导书" not in all_blob
    intro = _blob(by["修程修制匹配性评估"].get("fill") or {})
    assert "变压器" in intro
    assert "团标" in intro
    std = by["企业标准和制度"].get("fill") or {}
    std_blob = _blob(std)
    assert "如表6-1" in std_blob
    assert "新增了1本作业指导书" in std_blob
    assert "新增了1本一级规程" not in std_blob
    tbl = " ".join(str(x.get("rows") or "") for x in (std.get("flow") or []) if x.get("kind") == "table")
    assert "集中修" in tbl
    assert "零部件技术要求" not in tbl
    assert "工艺细则" not in tbl
    assert "触网" in tbl.replace(" ", "")


def test_count_table_year_filled():
    from chapters.overhead.ch6_revision import count_table_year_filled

    rows = [
        ["专业", "等级", "2025年", "2026年"],
        ["触网专业", "一级", "2", "3"],
        ["触网专业", "二级", "3", ""],
    ]
    assert count_table_year_filled(rows, 2026) == 1
    assert count_table_year_filled(rows, 2025) == 2
    empty = [["专业", "等级", "2026年"], ["触网专业", "一级", ""]]
    assert count_table_year_filled(empty, 2026) == 0


def test_ensure_latest_compliance_skips_synthetic_docs():
    from chapters.overhead.ch6_revision import ensure_latest_compliance_docs

    doc = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[Block(type="paragraph", text="短。")],
    )
    out = ensure_latest_compliance_docs([doc], 2026)
    assert out == [doc]


def test_ch6_harvests_revision_and_addendum_bodies():
    """6.1 表来自修程修志时，仍要从 5&6 补修订内容；分类表要带评估年数字。"""
    notes = DocumentModel(
        source_name="（修程修志部分）2026年评估报告（接触网专业）.docx",
        source_path="xiu.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="heading", text="对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="新增了1本一级规程、2本作业指导书。"),
            Block(
                type="table",
                rows=[
                    ["序号", "名称", "编号"],
                    ["1", "接触网（轨）设备安装工艺细则", "Q/SD-WBGD-FB-SS-06070001-2026"],
                    ["2", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"],
                ],
            ),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    empty45 = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="具体数量如表5-3："),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2025年", "2026年"],
                    ["触 网 专 业", "一级", "2", ""],
                    ["触 网 专 业", "总计", "9", ""],
                ],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="heading", text="运维表现健康度评估", level=1),
        ],
    )
    pack56 = DocumentModel(
        source_name="5&6合规性材料(2026).docx",
        source_path="d.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="（11）《接触网（轨）设备安装工艺细则》修订内容为："),
            Block(type="paragraph", text="——新增了接触线更换；"),
            Block(type="paragraph", text="——新增了承力索更换"),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="具体数量如表5-3："),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2025年", "2026年"],
                    ["触 网 专 业", "一级", "2", "3"],
                    ["触 网 专 业", "总计", "9", "12"],
                ],
            ),
            Block(type="paragraph", text="新增了1本作业指导书。"),
            Block(
                type="table",
                rows=[["序号", "名称", "编号"], ["1", "接触网（轨）集中修作业指导书", "Q/SD-WBZ-FB-SS-GDJ332-2026"]],
            ),
            Block(type="paragraph", text="（1）《接触网（轨）集中修作业指导书》新增内容为："),
            Block(type="paragraph", text="——线路设备情况"),
            Block(type="paragraph", text="——接触轨定位点工艺工法"),
        ],
    )
    pack = extract_chapter(
        [notes, empty45, pack56],
        year=2026,
        chapter_id="ch6",
        prior_docs=[],
        prior_via="baseline_2025",
    )
    by = {n["title"]: n for n in pack["outline"]}
    titles = [str(n.get("title") or "") for n in pack["outline"]]
    assert "修正1本三级规程" in titles
    assert any("工艺细则》修订内容" in t for t in titles)
    assert "接触线更换" in _blob(by[[t for t in titles if "修订内容" in t][0]].get("fill") or {})
    std = by["企业标准和制度"].get("fill") or {}
    std_blob = _blob(std)
    assert "线路设备情况" in std_blob
    tbl = " ".join(str(x.get("rows") or "") for x in (std.get("flow") or []) if x.get("kind") == "table")
    assert "12" in tbl
    assert "3" in tbl


def test_ch5_chapter_lead_skips_standards_catalog():
    """修程修志章标题后的标准化编号目录表，不能灌进第五章章名下。"""
    catalog = DocumentModel(
        source_name="（修程修志部分）2026年评估报告（接触网专业）.docx",
        source_path="xiu.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="管理体系合规性评估", level=1),
            Block(
                type="paragraph",
                text="根据评估规范第7部分8.2.1条款的评估情况撰写；统计、梳理目前使用的修程修制。",
            ),
            Block(
                type="table",
                rows=[
                    ["序号", "标准化编号", "标准/规范名称", "标准等级"],
                    ["1", "Q/SD-WB-FB-SS-GD1010-2020", "接触网(轨)作业安全规程", "一级"],
                    ["2", "Q/SD-ZG-J-KS-06070007-2026", "申通地铁集团接触网零部件技术要求", "一级"],
                ],
            ),
            Block(type="drawing", source_index=9),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程，具体数量如表5-3："),
            Block(
                type="table",
                rows=[["专业", "等级", "2018年"], ["接触网", "一级", "1"]],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
        ],
    )
    pack = extract_chapter([catalog], year=2026, chapter_id="ch5", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    lead = by["管理体系合规性评估"].get("fill") or {}
    assert not lead or lead.get("empty")
    lead_blob = _blob(lead)
    assert "标准化编号" not in lead_blob
    assert "Q/SD-WB-FB" not in lead_blob
    assert not any(x.get("kind") == "table" for x in (lead.get("flow") or []))
    assert not (lead.get("table") or [])
    std = _blob(by["企业标准和制度"].get("fill") or {})
    assert "表5-3" in std


def test_ch5_enterprise_standard_keeps_overhead_table_before_figure():
    """4&5 供电规程表较新也不能盖掉修程修志触网表，更不能把流程图翻到表前。"""
    power = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="管理体系合规性评估", level=1),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表3-1："),
            Block(type="paragraph", text="表5-1 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2025年", "2026"],
                    ["供电专业", "一级", "11", ""],
                    ["", "二级", "9", ""],
                ],
            ),
            Block(type="paragraph", text="标准制定流程如图5-1："),
            Block(type="drawing", source_index=30),
            Block(type="paragraph", text="图5-1 标准制定流程示意图"),
            Block(type="heading", text="修程修制匹配性评估", level=1),
        ],
    )
    xiu = DocumentModel(
        source_name="（修程修志部分）2026年评估报告（接触网专业）.docx",
        source_path="xiu.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="管理体系合规性评估", level=1),
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(type="paragraph", text="表5-3 规程分类、等级和变化情况"),
            Block(
                type="table",
                rows=[
                    ["专业", "等级", "2017年", "2026年"],
                    ["触 网 专 业", "一级", "2", "3"],
                ],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
        ],
    )
    pack = extract_chapter(
        [xiu, power],
        year=2026,
        chapter_id="ch5",
        prior_docs=[],
        prior_via="baseline_2025",
    )
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["企业标准和制度"].get("fill") or {}
    flow = fill.get("flow") or []
    kinds = [x.get("kind") for x in flow]
    assert "table" in kinds and "drawing" in kinds
    assert kinds.index("table") < kinds.index("drawing")
    tbl_blob = " ".join(str(x.get("rows") or "") for x in flow if x.get("kind") == "table")
    assert "供电专业" not in tbl_blob
    assert "触网" in tbl_blob.replace(" ", "")
    blob = _blob(fill)
    assert "表5-1" not in blob
    assert "表5-3" in blob
    assert "标准制定流程" in blob


def test_ch5_law_keeps_material_regulation_list():
    """法律法规清单按材料原样搬运，不按专业裁行。"""
    doc = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="管理体系合规性评估", level=1),
            Block(type="heading", text="法律法规的获取情况", level=2),
            Block(type="paragraph", text="目前供电分公司获取相关法律法规的途径包括："),
            Block(type="paragraph", text="—上网查询；"),
            Block(type="paragraph", text="获取的标准涉及如下几个方面："),
            Block(type="paragraph", text="①继电器相关规程"),
            Block(type="paragraph", text="④SCADA相关规程"),
            Block(type="paragraph", text="③变压器相关规程"),
            Block(type="paragraph", text="⑥线缆相关规程"),
            Block(type="paragraph", text="⑧闸刀相关规程"),
            Block(type="paragraph", text="12安全规程"),
            Block(type="heading", text="企业标准和制度", level=2),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch5", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["法律法规的获取情况"].get("fill") or {})
    assert "线缆相关规程" in blob
    assert "闸刀相关规程" in blob
    assert "SCADA相关规程" in blob
    assert "继电器相关规程" in blob
    assert "变压器相关规程" in blob
    assert "安全规程" in blob


def test_ch5_enterprise_standard_still_fills_before_ch6():
    doc = DocumentModel(
        source_name="4&5合规性材料(2026).docx",
        source_path="c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="企业标准和制度", level=2),
            Block(type="paragraph", text="供电分公司制定对应的操作规程或作业指导书，具体数量如表5-3："),
            Block(
                type="table",
                rows=[["专业", "等级", "2018年"], ["接触网", "一级", "1"]],
            ),
            Block(type="heading", text="修程修制匹配性评估", level=1),
            Block(type="paragraph", text="制定相关团标。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch5", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["企业标准和制度"].get("fill") or {})
    assert "表5-3" in blob
    assert "团标" not in blob


def test_ch7_newest_plan_table_not_power_table():
    older = DocumentModel(
        source_name="（维护七部）线路评估.docx",
        source_path="old7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="日常维修计划执行情况", level=2),
            Block(type="paragraph", text="2025.5.1-2026.4.30周期内，3号线共需完成生产计划888条，目前已全部按时完成。"),
        ],
    )
    newer = DocumentModel(
        source_name="4^07评估报告材料（生产计划）(2).docx",
        source_path="plan.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表6-1变电生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"],
                    ["1", "1号线", "4609", "4609", "100%"],
                ],
            ),
            Block(type="paragraph", text="表6-1触网生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"],
                    ["1", "1号线", "1102", "1102", "100%"],
                    ["2", "2号线", "2083", "2083", "100%"],
                ],
            ),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["日常维修计划执行情况"].get("fill") or {}
    blob = _blob(fill) + "".join(str(c) for r in (fill.get("table") or []) for c in r)
    assert "1102" in blob
    assert "4609" not in blob
    assert "888" not in blob


def test_ch7_plan_table_keeps_fuller_table_not_newer_stub():
    """较新但只有两三条线路的残表，不能盖掉线路齐全的触网计划表。"""
    full = DocumentModel(
        source_name="4^07评估报告材料（生产计划）.docx",
        source_path="full.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表6-1触网生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "未完成数量（项）", "完成率", "备注"],
                    *[[str(i), f"{i}号线", "10", "10", "0", "100%", ""] for i in range(1, 19)],
                    ["", "合计（项）", "180", "180", "0", "100%", ""],
                ],
            ),
        ],
    )
    stub = DocumentModel(
        source_name="4^07评估报告材料（生产计划）(2).docx",
        source_path="stub.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表6-1触网生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"],
                    ["1", "1号线", "1102", "1102", "100%"],
                    ["2", "2号线", "2083", "2083", "100%"],
                ],
            ),
        ],
    )
    pack = extract_chapter([full, stub], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["日常维修计划执行情况"].get("fill") or {}
    rows = fill.get("table") or []
    blob = "".join(str(c) for r in rows for c in r)
    assert "18号线" in blob
    assert sum(1 for r in rows[1:] if any("号线" in str(c) for c in r)) >= 18


def test_ch7_plan_table_keeps_continuation():
    """原材料拆成两张续表时，后半段线路不能丢。"""
    doc = DocumentModel(
        source_name="4^07评估报告材料（生产计划）(2).docx",
        source_path="plan.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表6-1触网生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率", "备注"],
                    *[[str(i), f"{i}号线", "10", "10", "100%", ""] for i in range(1, 6)],
                ],
            ),
            Block(
                type="table",
                rows=[[str(i), f"{i}号线", "10", "10", "100%", ""] for i in range(6, 13)],
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["日常维修计划执行情况"].get("fill") or {}
    blob = "".join(str(c) for r in (fill.get("table") or []) for c in r)
    assert "5号线" in blob
    assert "12号线" in blob
    assert sum(1 for x in (fill.get("flow") or []) if x.get("kind") == "table") == 2


def test_ch7_instrument_prefers_newer_dept_file():
    older = DocumentModel(
        source_name="（维护五部）2025年评估报告.docx",
        source_path="old5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="1号线接触网运维班组配置仪器仪表10台，旧稿不应采用。"),
        ],
    )
    newer = DocumentModel(
        source_name="（维护五部）2025年评估报告(9.7补充标注)(2).docx",
        source_path="new5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="1号线接触网运维班组配置仪器仪表18台，均在检定周期内。"),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    blob = ""
    parent = ""
    for n in pack["outline"]:
        t = str(n.get("title") or "")
        if t in ("仪器仪表使用管理方面", "部门年度培训方面", "智能化应用"):
            parent = t
        if t == "轨道交通1号线" and parent == "仪器仪表使用管理方面":
            blob = " ".join((n.get("fill") or {}).get("paras") or [])
            break
    assert "18台" in blob
    assert "10台" not in blob


def _ch7_line_paras(pack, parent: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur = ""
    for n in pack["outline"]:
        t = str(n.get("title") or "")
        if t in (
            "仪器仪表使用管理方面",
            "部门年度培训方面",
            "智能化应用",
            "日常维修计划执行情况",
        ):
            cur = t
        if t.startswith("轨道交通") and cur == parent:
            out[t] = " ".join((n.get("fill") or {}).get("paras") or [])
    return out


def test_ch7_keeps_every_line_named_in_one_sentence():
    """一句里并列多条线时，每一条都要单独成节，不能收成通稿后丢掉。"""
    doc = DocumentModel(
        source_name="（维护三部）2025年评估报告.docx",
        source_path="m3.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="3号线、18号线接触网运维班组配置仪器仪表51台，均在检定周期内。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    meter = _ch7_line_paras(pack, "仪器仪表使用管理方面")
    assert "轨道交通3号线" in meter and "51台" in meter["轨道交通3号线"]
    assert "轨道交通18号线" in meter and "51台" in meter["轨道交通18号线"]


def test_ch7_reads_chinese_line_numbers_and_bare_line_heading():
    doc = DocumentModel(
        source_name="（维护一部）2025年评估报告.docx",
        source_path="m1.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="九号线接触网运维班组配置仪器仪表20台。"),
            Block(type="paragraph", text="12号线"),
            Block(type="paragraph", text="我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(type="paragraph", text="十八号线接触网运维班组配置仪器仪表8台。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    meter = _ch7_line_paras(pack, "仪器仪表使用管理方面")
    assert "轨道交通9号线" in meter and "20台" in meter["轨道交通9号线"]
    assert "轨道交通12号线" in meter and "缺、漏" in meter["轨道交通12号线"]
    assert "轨道交通18号线" in meter and "8台" in meter["轨道交通18号线"]


def test_ch7_older_line_sentence_fills_line_only_covered_by_newer_generic():
    """较新材料只有通稿时，较旧材料里写明的那条线仍要单独留下。"""
    older = DocumentModel(
        source_name="（维护三部）2025年评估报告.docx",
        source_path="old3.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="18号线接触网运维班组配置仪器仪表51台，均在检定周期内。"),
        ],
    )
    newer = DocumentModel(
        source_name="（维护三部）2025年评估报告(9.7补充标注).docx",
        source_path="new3.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="维护三部管辖范围有3号线接触网、18号线接触网。"),
            Block(type="paragraph", text="我部共计在用维护仪器仪表136台，均在检定周期内。"),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    meter = _ch7_line_paras(pack, "仪器仪表使用管理方面")
    assert "轨道交通3号线" in meter and "136台" in meter["轨道交通3号线"]
    assert "轨道交通18号线" in meter and "51台" in meter["轨道交通18号线"]
    assert "136台" not in meter["轨道交通18号线"]


def test_ch8_event_prefers_newer_file():
    older = DocumentModel(
        source_name="（维护六部）线路评估.docx",
        source_path="old6.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="典型故障：2号线世纪大道下行进站列车有拉弧现象，发布0226#抢修令。旧稿只有一句。",
            ),
        ],
    )
    newer = DocumentModel(
        source_name="（维护六部）线路评估（9.3改版).docx",
        source_path="new6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2号线世纪大道分段绝缘器拉弧故障分析", level=2),
            Block(type="paragraph", text="2026年5月1日2号线世纪大道下行进站列车有拉弧现象，发布0226#抢修令。"),
            Block(type="paragraph", text="原因分析：导滑板有拉弧痕迹，现场已打磨。"),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    blob = " ".join(
        " ".join((n.get("fill") or {}).get("paras") or [])
        for n in pack["outline"]
        if "世纪大道" in str(n.get("title") or "") or "拉弧" in str(n.get("title") or "")
    )
    assert "原因分析" in blob
    assert "旧稿只有一句" not in blob


def test_ch10_env_prefers_newer_file():
    older = DocumentModel(
        source_name="（维护六部）线路评估.docx",
        source_path="old6.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="2号线一期地下隧道段，环境因素主要为漏水。旧稿环境说明。",
            ),
        ],
    )
    newer = DocumentModel(
        source_name="（维护六部）线路评估（9.3改版).docx",
        source_path="new6.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="2号线一期地下隧道段，环境因素主要为漏水、粉尘及侵限。新稿已补充粉尘措施。",
            ),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"] if n.get("title") == "轨道交通2号线"}
    blob = " ".join((by["轨道交通2号线"].get("fill") or {}).get("paras") or [])
    assert "粉尘及侵限" in blob
    assert "旧稿环境说明" not in blob


def test_ch11_retire_from_mixed_pack():
    pack_doc = DocumentModel(
        source_name="11退运材料.docx",
        source_path="r.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="退运报废倾向性评估", level=1),
            Block(type="heading", text="报废原因", level=2),
            Block(type="paragraph", text="4号线需报废4台隔离开关，原值共计147812.93元。"),
            Block(type="paragraph", text="6号线共计9台整流变压器需报废，分别安装在航津路。"),
            Block(type="paragraph", text="目前工器具暂无缺少情况。"),
        ],
    )
    pack = extract_chapter([pack_doc], year=2026, chapter_id="ch11", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通4号线" not in titles
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["2026年设备退运更换情况"].get("fill") or {})
    assert "147812.93" in blob
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "整流变压器" not in all_blob
    tools = by.get("固定资产工器具配置情况") or {}
    tblob = _blob(tools.get("fill") or {})
    assert "暂无缺少" not in tblob


def test_ch9_stock_from_rule_pdf_keeps_touchwang_only():
    doc = DocumentModel(
        source_name="附件1：《维保供电安全库存管理规定》（QSD-WBZ-FB-AQ-GDG59—2025）.pdf",
        source_path="rule.pdf",
        suffix=".pdf",
        blocks=[
            Block(type="paragraph", text="本规定适用于供电分公司安全库存。变电所备件见附录。"),
            Block(
                type="table",
                rows=[
                    ["序号", "大类", "中类", "小类", "物料名称", "型号", "计量单位", "安全库存配置总数量"],
                    ["1", "触网", "柔性接触网（通用）", "接触线", "铜银接触线", "CTA-120", "米", "6800"],
                ],
            ),
            Block(
                type="table",
                rows=[
                    ["序号", "大类", "中类", "小类", "物料名称", "型号", "计量单位", "安全库存配置总数量"],
                    ["1", "触网", "刚性接触网（通用）", "汇流排", "铝合金汇流排", "AA-120", "米", "200"],
                ],
            ),
            Block(
                type="table",
                rows=[
                    ["序号", "设备大类", "设备中类", "物料名称", "规格型号", "计量单位", "安全库存数量"],
                    ["1", "综保装置", "10kV综合保护继电器", "P121", "台", "1"],
                ],
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch9", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["接触网安全库存"].get("fill") or {}
    blob = "".join(str(c) for r in (fill.get("table") or []) for c in r)
    flow_blob = "".join(
        "".join(str(c) for r in (x.get("rows") or []) for c in r)
        for x in (fill.get("flow") or [])
        if x.get("kind") == "table"
    )
    assert "CTA-120" not in blob and "CTA-120" not in flow_blob
    assert not (fill.get("table") or [])
    assert not any(x.get("kind") == "table" for x in (fill.get("flow") or []))
    spare = by["接触网安全库存备品备件"].get("fill") or {}
    spare_blob = "".join(
        "".join(str(c) for r in (x.get("rows") or []) for c in r)
        for x in (spare.get("flow") or [])
        if x.get("kind") == "table"
    )
    caps = " ".join(spare.get("paras") or [])
    assert "CTA-120" in spare_blob
    assert "AA-120" in spare_blob
    assert "P121" not in spare_blob
    assert "表D.1 柔性接触网安全库存" in caps
    assert "表E.1 刚性接触网安全库存" in caps
    assert "附录" not in caps


def test_ch9_spare_does_not_reuse_prior_appendix():
    prior = DocumentModel(
        source_name="项目保底2025触网.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="接触网安全库存备品备件", level=2),
            Block(type="paragraph", text="接触网安全库存备品备件详细数量如附录A、B、C所示。"),
            Block(
                type="table",
                rows=[
                    ["序号", "大类", "中类", "小类", "物料名称", "型号", "计量单位", "安全库存配置总数量"],
                    ["1", "触网", "柔性接触网（通用）", "接触线", "去年接触线", "OLD-1", "米", "1"],
                ],
            ),
        ],
    )
    pack = extract_chapter([], year=2026, chapter_id="ch9", prior_docs=[prior], prior_via="upload")
    by = {n["title"]: n for n in pack["outline"]}
    spare = by["接触网安全库存备品备件"].get("fill") or {}
    blob = " ".join(spare.get("paras") or []) + "".join(
        "".join(str(c) for r in (x.get("rows") or []) for c in r)
        for x in (spare.get("flow") or [])
        if x.get("kind") == "table"
    )
    assert spare.get("empty", True)
    assert "附录" not in blob
    assert "OLD-1" not in blob
    assert "去年接触线" not in blob


def test_ch9_stock_prose_does_not_reuse_prior():
    prior = DocumentModel(
        source_name="项目保底2025触网.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="接触网安全库存", level=2),
            Block(
                type="paragraph",
                text="评估将根据是否有安全库存。这是去年库存说明，数量为99台。柔性接触网备件支持全路网。",
            ),
        ],
    )
    pack = extract_chapter([], year=2026, chapter_id="ch9", prior_docs=[prior], prior_via="upload")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["接触网安全库存"].get("fill") or {}
    blob = " ".join(fill.get("paras") or [])
    assert "去年库存说明" not in blob
    assert fill.get("empty", True) or not blob.strip()


def test_ch11_tools_does_not_reuse_prior():
    prior = DocumentModel(
        source_name="项目保底2025触网.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="固定资产工器具配置情况", level=2),
            Block(type="paragraph", text="拟采购吊弦液压钳12把。这是去年工器具配置。"),
        ],
    )
    pack = extract_chapter([], year=2026, chapter_id="ch11", prior_docs=[prior], prior_via="upload")
    by = {n["title"]: n for n in pack["outline"]}
    fill = by["固定资产工器具配置情况"].get("fill") or {}
    blob = " ".join(fill.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (fill.get("flow") or []) if x.get("kind") == "para"
    )
    assert "去年工器具配置" not in blob
    assert "吊弦液压钳" not in blob
    assert fill.get("empty", True) or not blob.strip()


def test_ch7_intel_skips_tool_retire_note():
    retire = DocumentModel(
        source_name="关于轨道交通1号线工器具报废的情况说明.docx",
        source_path="retire.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="智能化应用", level=2),
            Block(
                type="paragraph",
                text="2、放线小车：该放线小车因长期使用，造成四个轮毂严重偏移，1号线已无法使用。",
            ),
            Block(
                type="paragraph",
                text="3、接触网接地、验电器：该设备经长时间使用，老化严重，外壳损坏。",
            ),
        ],
    )
    keep = DocumentModel(
        source_name="（维护五部）2025年评估报告(9.7补充标注)(2).docx",
        source_path="new5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="智能化应用", level=2),
            Block(
                type="paragraph",
                text="中科如铁检测小车在5号线进行使用，作为日常导高拉出值的检测工器具进行使用。",
            ),
        ],
    )
    pack = extract_chapter([retire, keep], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    intel = by["智能化应用"].get("fill") or {}
    blob = _blob(intel) + " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "检测小车" in blob
    assert "放线小车" not in blob
    assert "老化严重" not in blob
    titles = [n.get("title") for n in pack["outline"] if n.get("title")]
    assert "轨道交通5号线" in titles
    assert "轨道交通1号线" not in titles


def test_ch7_broadcasts_dept_training_and_intel_to_plan_lines():
    """③④通稿挂到该部①里出现过的线路；2、9号线仪表仍归9号线。"""
    doc = DocumentModel(
        source_name="（维护六部）线路评估（9.3改版).docx",
        source_path="m6.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="①统计生产计划执行数量，是否存在欠修；"),
            Block(type="paragraph", text="2025年2号线总体生产过程平稳，生产计划共计2062个，均已完成。"),
            Block(type="paragraph", text="9号线共需完成生产计划1417条，目前已全部按时完成。"),
            Block(type="paragraph", text="6号线周期内生产计划共计857个，均已完成。"),
            Block(type="paragraph", text="②统计部门管辖的维护仪器、仪表等工具，是否存在缺少情况；"),
            Block(
                type="paragraph",
                text="2、9号线接触网运维涉及部门5个班组，我部共计在用维护仪器仪表136台。",
            ),
            Block(
                type="paragraph",
                text="6号线接触网运维涉及部门2个班组，共计在用维护仪器仪表23台。",
            ),
            Block(type="paragraph", text="③年度培训是否覆盖需求"),
            Block(type="paragraph", text="2025.5.1-2026.4.30周期内年度培训计划包含智能运维平台使用及优化分析。"),
            Block(type="paragraph", text="④智能化应用的使用情况；"),
            Block(type="paragraph", text="1、推进接触网线岔检测装置使用"),
            Block(type="paragraph", text="通过线岔检测装置有效地对接触网线岔装置进行动态检测。"),
            Block(type="heading", text="风险隐患闭环度评估", level=1),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")

    def lines_under(parent: str) -> dict[str, str]:
        out: dict[str, str] = {}
        cur = ""
        for n in pack["outline"]:
            t = str(n.get("title") or "")
            if t in (
                "仪器仪表使用管理方面",
                "部门年度培训方面",
                "智能化应用",
                "日常维修计划执行情况",
            ):
                cur = t
            if t.startswith("轨道交通") and cur == parent:
                out[t] = " ".join((n.get("fill") or {}).get("paras") or [])
        return out

    meter = lines_under("仪器仪表使用管理方面")
    train = lines_under("部门年度培训方面")
    intel = lines_under("智能化应用")
    assert "轨道交通9号线" in meter and "136台" in meter["轨道交通9号线"]
    assert "轨道交通2号线" not in meter
    assert "轨道交通2号线" in train and "年度培训计划" in train["轨道交通2号线"]
    assert "轨道交通6号线" in train
    assert "轨道交通9号线" in train
    assert "轨道交通2号线" in intel and "线岔检测" in intel["轨道交通2号线"]
    assert "轨道交通6号线" in intel


def test_ch7_line_block_maps_bare_none_to_meter_and_skips_power_ops():
    w5 = DocumentModel(
        source_name="（维护五部）2025年评估报告(9.7补充标注)(2).docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="5号线：1、2025年5月1日-2026年4月30日期间共执行计划1033条，完成率100%，不存在欠修；"),
            Block(type="paragraph", text="不存在"),
            Block(type="paragraph", text="2、《智能运维平台培训》共计151人次；"),
            Block(type="paragraph", text="3、中科如铁检测小车在5号线进行使用。"),
            Block(type="paragraph", text="7号线：生产计划执行数量共计923条，完成率为100%。"),
            Block(type="paragraph", text="我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(type="paragraph", text="年度培训：我部顺利完成《智能运维平台培训》。"),
            Block(type="heading", text="风险隐患闭环度评估", level=1),
        ],
    )
    power = DocumentModel(
        source_name="01-2025年评估报告（16线路变电专业、接触网专业）.docx",
        source_path="p16.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="5)年度培训基本覆盖员工培训需求，后续16号线正在进行35kV、1500v、400V设备改造。"),
            Block(type="paragraph", text="6)智能化应用的使用情况；16号线全线未接入智能运维系统，交直流屏已运行14年，为铅酸电池。"),
            Block(type="heading", text="风险隐患闭环度评估", level=1),
        ],
    )
    pack = extract_chapter([w5, power], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通16号线" not in titles
    meter = train = intel = ""
    parent = ""
    for n in pack["outline"]:
        t = str(n.get("title") or "")
        if t in ("仪器仪表使用管理方面", "部门年度培训方面", "智能化应用"):
            parent = t
        if t == "轨道交通5号线":
            blob = " ".join((n.get("fill") or {}).get("paras") or [])
            if parent == "仪器仪表使用管理方面":
                meter = blob
            elif parent == "部门年度培训方面":
                train = blob
            elif parent == "智能化应用":
                intel = blob
    assert "不存在" in meter or "缺、漏" in meter
    assert "151人次" in train
    assert "检测小车" in intel
    assert "铅酸电池" not in " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])


def test_ch11_skips_instrument_tool_retire_note():
    tools = DocumentModel(
        source_name="关于1号线仪器仪表工器具报废的情况说明.docx",
        source_path="inst.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="1号线需报废8台仪器仪表及工具器械设备，原值共计360161.05元，包含2台接触网导线磨耗测量仪。",
            ),
        ],
    )
    pack_doc = DocumentModel(
        source_name="11退运材料.docx",
        source_path="r.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="退运报废倾向性评估", level=1),
            Block(type="paragraph", text="4号线需报废4台隔离开关，原值共计147812.93元。"),
        ],
    )
    pack = extract_chapter([tools, pack_doc], year=2026, chapter_id="ch11", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通4号线" not in titles
    assert "轨道交通1号线" not in titles
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "147812.93" in all_blob
    assert "360161.05" not in all_blob


def test_ch10_env_skips_status_eval_para():
    doc = DocumentModel(
        source_name="（维护五部）2025年评估报告(9.7补充标注)(2).docx",
        source_path="e.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路环境符合性评估", level=2),
            Block(
                type="paragraph",
                text="7号线通过高架段各专项整治措施的实施，提高了状态较差设备的评价，延缓了7号线北延伸户外段柔性接触网状态的下降趋势。通过7号线隧道段大修作业，显著提高了刚性接触网、隔离开关及其控制屏等设备的系统评价。",
            ),
            Block(
                type="paragraph",
                text="1号线南延伸区段，由于支柱开裂，已增加支柱巡视差异化计划。在一号线隧道段内，存在区间隧道壁漏水，当前均已经对线索设备加装了绝缘护套。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    titles = [n.get("title") for n in pack["outline"]]
    assert "轨道交通1号线" in titles
    all_blob = " ".join(_blob(n.get("fill") or {}) for n in pack["outline"])
    assert "状态的下降" not in all_blob
    assert "系统评价" not in all_blob


def test_ch10_dust_drops_older_same_dept_file():
    older = DocumentModel(
        source_name="（维护六部）线路评估.docx",
        source_path="old6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="使用环境符合性评估", level=1),
            Block(type="heading", text="粉尘", level=3),
            Block(type="paragraph", text="旧稿粉尘清扫按两年一次，不应采用。"),
        ],
    )
    newer = DocumentModel(
        source_name="（维护六部）线路评估（9.3改版).docx",
        source_path="new6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="使用环境符合性评估", level=1),
            Block(type="heading", text="粉尘", level=3),
            Block(type="paragraph", text="新稿针对粉尘对接触网系统的影响，清扫为一年一次。"),
        ],
    )
    pack = extract_chapter([older, newer], year=2026, chapter_id="ch10", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["粉尘"].get("fill") or {})
    assert "一年一次" in blob
    assert "两年一次" not in blob
    assert "旧稿粉尘" not in blob


def _ch7_lines(pack: dict, parent: str) -> dict[str, str]:
    out: dict[str, str] = {}
    cur = ""
    for n in pack["outline"]:
        t = str(n.get("title") or "")
        if t in (
            "仪器仪表使用管理方面",
            "部门年度培训方面",
            "智能化应用",
            "日常维修计划执行情况",
            "生产组织模式",
        ):
            cur = t
        if t.startswith("轨道交通") and cur == parent:
            out[t] = " ".join((n.get("fill") or {}).get("paras") or [])
    return out


def test_ch7_line_meter_item_does_not_reset_or_eat_next_line_train():
    """10号线「2、我部管辖仪表」不是②通稿切段；11号线培训不得串进10号线。"""
    doc = DocumentModel(
        source_name="（维护五部）2025年评估报告(9.7补充标注)(2).docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(
                type="paragraph",
                text="1号线：2025年5月1日-2026年4月30日共计完成生产计划1200项，完成率100%。",
            ),
            Block(type="paragraph", text="我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(
                type="paragraph",
                text="年度培训：我部顺利完成《智能运维平台培训》、《电力电缆维护培训》6项专项培训，累计总课时3060学时。",
            ),
            Block(
                type="paragraph",
                text="10号线：1、2025年5月1日-2026年4月30日共完成766个生产计划执行，完成率100%",
            ),
            Block(type="paragraph", text="2、我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(
                type="paragraph",
                text="3、《智能运维平台培训》、《电力电缆维护培训》共计151人次",
            ),
            Block(type="paragraph", text="4、中科如铁检测小车已在10号线进行日常使用。"),
            Block(
                type="paragraph",
                text="11号线：2025年05月01日~2025年04月30日共计完成生产计划1567项，兑现率100%。",
            ),
            Block(
                type="paragraph",
                text="2025年度培训计划已全部完成；在日常培训工作方面，我部门投入使用“魔学院”、“钉钉金牌团队”APP。",
            ),
            Block(type="heading", text="风险隐患闭环度评估", level=1),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    train = _ch7_lines(pack, "部门年度培训方面")
    meter = _ch7_lines(pack, "仪器仪表使用管理方面")
    intel = _ch7_lines(pack, "智能化应用")
    assert "轨道交通10号线" in train
    assert "151人次" in train["轨道交通10号线"]
    assert "3060学时" not in train["轨道交通10号线"]
    assert "魔学院" not in train["轨道交通10号线"]
    assert "轨道交通11号线" in train
    assert "魔学院" in train["轨道交通11号线"]
    assert "151人次" not in train["轨道交通11号线"]
    assert "轨道交通1号线" in train
    assert "3060学时" in train["轨道交通1号线"]
    assert "缺、漏" in meter.get("轨道交通10号线", "")
    assert "检测小车" in intel.get("轨道交通10号线", "")


def test_ch7_trailing_tool_none_is_not_pinned_on_last_line():
    """「目前工器具暂无缺少情况」是②通稿，不得只钉在最后一条线。"""
    doc = DocumentModel(
        source_name="（维护七部）01-2026年评估报告(9.2补充标注).docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(
                type="paragraph",
                text="3号线接触网运维涉及部门3个班组，我部共计在用维护仪器仪表51台。",
            ),
            Block(
                type="paragraph",
                text="18号线接触网运维涉及部门1个班组，我部共计在用维护仪器仪表45台。",
            ),
            Block(type="paragraph", text="目前工器具暂无缺少情况。"),
            Block(type="heading", text="风险隐患闭环度评估", level=1),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch7", prior_docs=[], prior_via="baseline_2025")
    meter = _ch7_lines(pack, "仪器仪表使用管理方面")
    assert "51台" in meter.get("轨道交通3号线", "")
    assert "45台" in meter.get("轨道交通18号线", "")
    assert "工器具暂无" not in meter.get("轨道交通18号线", "")
    assert "工器具暂无" not in meter.get("轨道交通3号线", "")
