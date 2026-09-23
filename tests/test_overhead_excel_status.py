# -*- coding: utf-8 -*-
from collections import Counter

from chapters.overhead.ch3_status import extract_status_distribution
from chapters.overhead.excel_status import (
    compare_and_backfill,
    counts_to_table,
    detect_overhead_excel_capabilities,
    extract_excel_status_tables,
    extract_system_volume_table,
    infer_sheet_kind,
)
from chapters.overhead.extract import extract_chapter
from parsers.document_model import Block, DocumentModel


def _xlsx_doc(name: str, sheet: str, rows: list[list[str]]) -> DocumentModel:
    return DocumentModel(
        source_name=name,
        source_path=name,
        suffix=".xlsx",
        blocks=[
            Block(type="heading", text=f"工作表:{sheet}", level=1),
            Block(type="table", rows=rows),
        ],
    )


def test_counts_to_table_line1_179():
    by = {"1号线": Counter(A=111, B=18, C=50, D=0)}
    rows = counts_to_table(by, count_label="锚段数量")
    line = next(r for r in rows if r[0] == "1号线")
    assert line[1] == "179"
    assert line[2] == "111"
    net = next(r for r in rows if r[0] == "全网络")
    assert net[1] == "179"
    assert net[2] == "111"
    assert rows[-1][0] == "全网络"


def test_excel_flexible_sheet_aggregates():
    rows = [
        ["序号", "线路", "锚段号", "总分", "评价"],
        ["1", "_1号线", "CW1", "90", "A"],
        ["2", "_1号线", "CW2", "70", "C"],
        ["3", "_10号线", "CW3", "80", "B"],
    ]
    doc = _xlsx_doc("接触网系统（all new）.xlsx", "柔性锚段", rows)
    hit = extract_excel_status_tables([doc])
    flex = hit["各线路柔性接触网状态分布"]
    table = flex["table"]
    r1 = next(r for r in table if r[0] == "1号线")
    r10 = next(r for r in table if r[0] == "10号线")
    assert r1[1] == "2" and r1[2] == "1"
    assert r10[1] == "1" and r10[4] == "1"
    assert not any(r[0] == "17号线" for r in table)
    net = next(r for r in table if r[0] == "全网络")
    assert net[1] == "3"
    assert table[-1][0] == "全网络"


def test_compare_marks_word_excel_mismatch():
    excel = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["1号线", "179", "111", "62.01%", "18", "10.06%", "50", "27.93%", "0", "0.00%"],
    ]
    word = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["1号线", "20", "9", "45.00%", "10", "50.00%", "1", "5.00%", "0", "0.00%"],
    ]
    table, warns = compare_and_backfill(excel, word, excel_source="接触网系统.xlsx", word_source="部门.docx")
    row = next(r for r in table if r[0] == "1号线")
    assert row[1] == "179"
    assert any("不一致" in w and "179" in w for w in warns)


def test_extract_status_prefers_excel_over_wrong_word():
    excel_rows = [
        ["序号", "线路", "锚段号", "评价"],
        ["1", "1号线", "a", "A"],
        ["2", "1号线", "b", "A"],
        ["3", "1号线", "c", "B"],
    ]
    word_rows = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["1号线", "20", "9", "45%", "10", "50%", "1", "5%", "0", "0%"],
    ]
    docs = [
        _xlsx_doc("接触网系统（all new）.xlsx", "柔性锚段", excel_rows),
        DocumentModel(
            source_name="维护六部.docx",
            source_path="b.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="各线路柔性接触网状态分布", level=4),
                Block(type="table", rows=word_rows),
                Block(type="paragraph", text="1号线：北延伸柔性接触网大修。"),
            ],
        ),
    ]
    hit = extract_status_distribution(docs)["各线路柔性接触网状态分布"]
    row = next(r for r in hit["table"] if str(r[0]).startswith("1"))
    assert row[1] == "3"
    blob = " ".join(hit.get("warnings") or [])
    assert "不一致" in blob
    note = " ".join(x.get("text") or "" for x in hit["flow"] if x.get("kind") == "para")
    assert "北延伸" in note or "1号线" in note


def test_ch4_does_not_repeat_system_sheet_as_volume():
    rows = [
        ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏", "系统状态值S1", "系统状态等级"],
        ["_1号线", "北延伸", "/", "98", "/", "72", "94", "88", "B"],
        ["_1号线", "正线", "/", "94", "/", "91", "92", "92", "A"],
    ]
    doc = _xlsx_doc("接触网系统（all new）.xlsx", "接触网系统", rows)
    vol = extract_system_volume_table([doc])
    assert not vol["empty"]
    assert vol["table"][1][0] == "1号线"
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    assert "设备体量" not in by
    assert "和2025年评估对比结果" in by
    vol_fill = (by.get("设备体量变化情况") or {}).get("fill") or {}
    blob = " ".join(str(x.get("text") or "") for x in (vol_fill.get("flow") or []))
    assert "表3-9" not in blob
    assert "表4-1" not in blob
    parent = (by.get("设备体量和变化情况") or {}).get("fill") or {}
    assert not parent.get("table")
    assert not any(x.get("kind") == "table" for x in (parent.get("flow") or []))


def test_table_39_goes_to_controls_not_33_parent():
    rows = [
        ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏", "系统状态值S1", "系统状态等级"],
        ["_1号线", "北延伸", "/", "98", "/", "72", "94", "88", "B"],
    ]
    flex = [
        ["序号", "线路", "锚段号", "承力索", "评价"],
        ["1", "1号线", "CW1", "90", "A"],
        ["2", "1号线", "CW2", "70", "C"],
    ]
    doc = DocumentModel(
        source_name="接触网系统（all new）.xlsx",
        source_path="x.xlsx",
        suffix=".xlsx",
        blocks=[
            Block(type="heading", text="工作表:接触网系统", level=1),
            Block(type="table", rows=rows),
            Block(type="heading", text="工作表:柔性锚段", level=1),
            Block(type="table", rows=flex),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch3", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    parent = by["接触网设备状态分布"]
    assert not (parent.get("fill") and not parent["fill"].get("empty"))
    flex_fill = by["各线路柔性接触网状态分布"]["fill"]
    line = next(r for r in flex_fill["table"] if r[0] == "1号线")
    assert line[1] == "2" and line[2] == "1"
    assert line[6] == "1"
    ctrl = by["各线路管控措施"]["fill"]
    blob = " ".join(x.get("text") or "" for x in (ctrl.get("flow") or []) if x.get("kind") == "para")
    assert "表3-9" in blob
    assert any(x.get("kind") == "table" for x in (ctrl.get("flow") or []))


def test_infer_kind_from_headers_not_sheet_name():
    flex = [
        ["序号", "线路", "锚段号", "承力索", "评价"],
        ["1", "1号线", "CW1", "90", "A"],
        ["2", "1号线", "CW2", "70", "C"],
    ]
    rigid = [
        ["序号", "线路", "锚段号", "汇流排", "评价"],
        ["1", "2号线", "G1", "88", "B"],
        ["2", "2号线", "G2", "60", "C"],
    ]
    system = [
        ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏", "系统状态值S1", "系统状态等级"],
        ["_3号线", "正线", "90", "94", "/", "72", "94", "88", "B"],
    ]
    flex_doc = _xlsx_doc("all new.xlsx", "柔性明细", flex)
    rigid_doc = _xlsx_doc("all new.xlsx", "刚网台账", rigid)
    sys_doc = _xlsx_doc("all new.xlsx", "线路评分", system)
    assert infer_sheet_kind("柔性明细", flex) == "各线路柔性接触网状态分布"
    assert infer_sheet_kind("刚网台账", rigid) == "各线路刚性接触网状态分布"
    assert infer_sheet_kind("线路评分", system) == "接触网设备状态分布"
    hit = extract_excel_status_tables([flex_doc, rigid_doc, sys_doc])
    assert "各线路柔性接触网状态分布" in hit
    assert "各线路刚性接触网状态分布" in hit
    assert "接触网设备状态分布" not in hit
    vol = extract_system_volume_table([sys_doc])
    assert not vol["empty"]
    caps = detect_overhead_excel_capabilities(flex_doc)
    assert caps and "ch3" in caps[0]["chapters"]
    sys_caps = detect_overhead_excel_capabilities(sys_doc)
    chapters = {c for item in sys_caps for c in item["chapters"]}
    assert "ch3" in chapters and "ch4" in chapters


def test_rail_table_only_nonzero_lines():
    rows = [
        ["序号", "线路", "区间", "评价"],
        ["1", "16号线", "a", "A"],
        ["2", "17号线", "b", "B"],
        ["3", "17号线", "c", "A"],
    ]
    doc = _xlsx_doc("接触网系统（all new）.xlsx", "三轨区间", rows)
    hit = extract_excel_status_tables([doc])["接触轨状态分布"]
    labels = [r[0] for r in hit["table"][2:]]
    assert labels == ["16号线", "17号线", "全网络"]
    assert hit["table"][0][1] == "区段数量"
    assert hit["table"][1][2] == "区段数"
    net = hit["table"][-1]
    assert net[1] == "3"
    assert net[2] == "2"
    assert net[4] == "1"


def test_rail_backfill_from_word_when_excel_misses_line():
    excel_rows = [
        ["序号", "线路", "区间", "评价"],
        ["1", "16号线", "a", "A"],
        ["2", "16号线", "b", "B"],
    ]
    word_rows = [
        ["线路", "区段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "区段数量", "区段数", "占比", "区段数", "占比", "区段数", "占比", "区段数", "占比"],
        ["1号线", "0", "0", "0.00%", "0", "0.00%", "0", "0.00%", "0", "0.00%"],
        ["16号线", "40", "24", "60.00%", "16", "40.00%", "0", "0.00%", "0", "0.00%"],
        ["17号线", "8", "0", "0.00%", "8", "100.00%", "0", "0.00%", "0", "0.00%"],
        ["全网络", "48", "24", "50.00%", "24", "50.00%", "0", "0.00%", "0", "0.00%"],
    ]
    docs = [
        _xlsx_doc("接触网系统（all new）.xlsx", "三轨区间", excel_rows),
        DocumentModel(
            source_name="维护.docx",
            source_path="rail.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="接触轨状态分布", level=4),
                Block(type="table", rows=word_rows),
                Block(type="paragraph", text="16号线没有C和D状态区段，维持现有管控措施。"),
            ],
        ),
    ]
    hit = extract_status_distribution(docs)["接触轨状态分布"]
    labels = [r[0] for r in hit["table"][2:]]
    assert "1号线" not in labels
    assert labels == ["16号线", "17号线", "全网络"]
    r16 = next(r for r in hit["table"] if r[0] == "16号线")
    assert r16[1] == "2"
    r17 = next(r for r in hit["table"] if r[0] == "17号线")
    assert r17[1] == "8"
    net = hit["table"][-1]
    assert net[0] == "全网络"
    assert net[1] == "10"
    blob = " ".join(x.get("text") or "" for x in hit["flow"] if x.get("kind") == "para")
    assert "没有C和D" in blob
    assert not any(
        str(x.get("text") or "").strip() in {"1号线：", "2号线："} for x in hit["flow"]
    )


def test_switch_table_uses_total_count_label():
    rows = [
        ["序号", "线路", "设备", "评价"],
        ["1", "1号线", "k1", "A"],
        ["2", "1号线", "k2", "B"],
    ]
    doc = _xlsx_doc("接触网系统（all new）.xlsx", "隔离开关", rows)
    table = extract_excel_status_tables([doc])["各线路隔离开关状态分布"]["table"]
    assert table[0][1] == "总数量"
    assert table[1][2] == "数量"
    assert table[-1][0] == "全网络"


def test_year_compare_table_from_two_system_sheets():
    from chapters.overhead.excel_status import extract_year_compare_table

    head = ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "系统状态值S1", "系统状态等级"]
    now = _xlsx_doc(
        "接触网系统（all new）.xlsx",
        "接触网系统",
        [head, ["_1号线", "北延伸", "/", "98", "/", "72", "88", "B"]],
    )
    prior = DocumentModel(
        source_name="2025接触网年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表3-9 各线路触网状态分布"),
            Block(type="table", rows=[head, ["1号线", "北延伸", "/", "67", "/", "73", "75", "B"]]),
        ],
    )
    hit = extract_year_compare_table([now], year=2026, prior_docs=[prior])
    assert not hit.get("empty")
    years = {r[2] for r in hit["table"][1:] if len(r) > 2}
    assert "2025" in years and "2026" in years
    row25 = next(r for r in hit["table"][1:] if r[2] == "2025")
    row26 = next(r for r in hit["table"][1:] if r[2] == "2026")
    assert "67" in row25
    assert "98" in row26
    assert row25[0] == "1号线" and row26[0] == "1号线"


def test_year_compare_normalizes_numeric_line_id():
    from chapters.overhead.excel_status import extract_year_compare_table

    head_now = ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "系统状态值S1", "系统状态等级"]
    now = _xlsx_doc(
        "接触网系统（all new）.xlsx",
        "接触网系统",
        [head_now, ["_1号线", "北延伸", "/", "98", "/", "72", "88", "B"]],
    )
    prior_head = ["线路", "区段", "时间", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "系统状态值S1", "系统状态等级"]
    prior = DocumentModel(
        source_name="2025接触网年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="表3-9 各线路触网状态分布"),
            Block(
                type="table",
                rows=[
                    prior_head,
                    ["1", "北延伸", "2024", "/", "50", "/", "70", "60", "C"],
                    ["1", "北延伸", "2025", "/", "67", "/", "73", "75", "B"],
                ],
            ),
        ],
    )
    hit = extract_year_compare_table([now], year=2026, prior_docs=[prior])
    years = [(r[0], r[1], r[2], r[4]) for r in hit["table"][1:]]
    assert ("1号线", "北延伸", "2025", "67") in years
    assert ("1号线", "北延伸", "2026", "98") in years
    assert ("1号线", "北延伸", "2024", "50") not in years


def test_control_prose_drops_assessment_conclusion():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="18号线评估.docx",
        source_path="l18.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="3.4.15 轨道交通18号线", level=3),
            Block(type="paragraph", text="现有管控措施是：差异化进行电缆专项检查。"),
            Block(type="heading", text="11.2 评估结论", level=2),
            Block(type="paragraph", text="第二章：本年度设备功能有效性评估基于多维度参数。"),
        ],
    )
    hit = harvest_control_prose([doc])
    paras = "\n".join((hit.get("by_line") or {}).get("18号线") or [])
    assert "电缆专项检查" in paras
    assert "评估结论" not in paras
    assert "多维度参数" not in paras


def test_control_prose_keeps_line_after_status_distribution():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="w6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.3.1 各线路柔性接触网状态分布", level=3),
            Block(type="paragraph", text="10号线接触网状态"),
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="3.4.10 轨道交通10号线", level=3),
            Block(type="paragraph", text="1、集中修项目：对10号线一期开展集中修作业，需对10659个刚性定位点进行集中修。"),
            Block(type="heading", text="3.4.11 轨道交通11号线", level=3),
            Block(type="paragraph", text="集中修项目:2026年3月10日-2026年6月10日，11号线户外段及车场全部完成。"),
            Block(type="heading", text="3.4.12 轨道交通15号线", level=3),
            Block(type="paragraph", text="现有管控措施是：差异化进行电缆专项检查，绝缘防护加固。"),
        ],
    )
    hit = harvest_control_prose([doc])
    by = hit.get("by_line") or {}
    assert "10659" in "\n".join(by.get("10号线") or [])
    assert "户外段及车场" in "\n".join(by.get("11号线") or [])
    assert "绝缘防护加固" in "\n".join(by.get("15号线") or [])


def test_control_prose_keeps_named_line_with_replacement_note():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通18号线", level=3),
            Block(
                type="paragraph",
                text="轨道交通18号线目前没有C和D状态的区段；维持现有日常维护的管控措施。18号线触网闸刀控制柜PLC设备平替已全部平替完成。",
            ),
        ],
    )
    hit = harvest_control_prose([doc])
    paras = "\n".join((hit.get("by_line") or {}).get("18号线") or [])
    assert "平替" in paras


def test_year_compare_drops_screen_col_absent_in_prior():
    from chapters.overhead.excel_status import extract_year_compare_table

    now_head = [
        "线路",
        "区段",
        "刚性接触网",
        "柔性接触网",
        "接触轨",
        "隔离开关",
        "隔离开关控制屏",
        "系统状态值S1",
        "系统状态等级",
    ]
    prior_head = ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "系统状态值S1", "系统状态等级"]
    now = _xlsx_doc(
        "接触网系统（all new）.xlsx",
        "接触网系统",
        [now_head, ["1号线", "北延伸", "/", "98", "/", "72", "80", "88", "B"]],
    )
    prior = DocumentModel(
        source_name="2025接触网年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="table", rows=[prior_head, ["1号线", "北延伸", "/", "67", "/", "73", "75", "B"]]),
        ],
    )
    hit = extract_year_compare_table([now], year=2026, prior_docs=[prior])
    assert "隔离开关控制屏" not in hit["table"][0]


def test_align_system_table_drops_screen_not_in_prior():
    from chapters.overhead.excel_status import align_system_table_to_prior

    now = [
        ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏", "系统状态值S1", "系统状态等级"],
        ["1号线", "北延伸", "/", "98", "/", "72", "80", "88", "B"],
    ]
    prior = DocumentModel(
        source_name="2025接触网年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="table",
                rows=[
                    ["线路", "区段", "刚性接触网", "柔性接触网", "接触轨", "隔离开关", "系统状态值S1", "系统状态等级"],
                    ["1号线", "北延伸", "/", "67", "/", "73", "75", "B"],
                ],
            )
        ],
    )
    got = align_system_table_to_prior(now, [prior])
    assert "隔离开关控制屏" not in got[0]
    assert "隔离开关" in got[0]


def test_backfill_controls_adds_missing_line_from_status_no_cd():
    from chapters.overhead.extract import backfill_controls_from_status_notes

    ctrl = {"sections": [], "source": ""}
    status = {
        "各线路柔性接触网状态分布": {
            "flow": [
                {"kind": "para", "text": "15号线：柔性没有C和D状态的区段，维持现有管控措施。"},
            ]
        }
    }
    got = backfill_controls_from_status_notes(ctrl, status)
    titles = [s.get("title") for s in got.get("sections") or []]
    assert any("15号线" in (t or "") for t in titles)
    blob = "\n".join((got["sections"][0].get("paras") or []))
    assert "没有C和D" in blob


def test_backfill_controls_fills_thin_line_from_status_overhaul():
    from chapters.overhead.extract import backfill_controls_from_status_notes

    ctrl = {
        "sections": [
            {
                "title": "轨道交通11号线",
                "paras": ["2、备品备件：新华PLC备件无法采购。"],
                "source": "五部.docx",
                "fill": {"paras": ["2、备品备件：新华PLC备件无法采购。"], "empty": False},
            }
        ],
        "source": "五部.docx",
    }
    status = {
        "各线路柔性接触网状态分布": {
            "flow": [
                {
                    "kind": "para",
                    "text": "11号线：C状态的柔性主要集中在一期。\n集中修检验检测：11号线户外段及车场全部完成，共3136处定位点。",
                }
            ]
        }
    }
    got = backfill_controls_from_status_notes(ctrl, status)
    blob = "\n".join((got["sections"][0].get("paras") or []))
    assert "新华PLC" in blob
    assert "3136处定位点" in blob



def test_control_prose_keeps_body_after_empty_ctrl_heading():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="3.4.11 轨道交通11号线", level=3),
            Block(type="paragraph", text="柔性接触网的管控策略包括："),
            Block(type="paragraph", text="1、集中修检验检测："),
            Block(
                type="paragraph",
                text="2026年3月10日-2026年6月10日，11号线户外段及车场全部完成，共3136处定位点。",
            ),
            Block(type="paragraph", text="2、备品备件：新华PLC备件无法采购。"),
        ],
    )
    hit = harvest_control_prose([doc])
    paras = "\n".join((hit.get("by_line") or {}).get("11号线") or [])
    assert "3136处定位点" in paras
    assert "新华PLC" in paras


def test_control_prose_keeps_named_no_cd_measure():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通15号线", level=3),
            Block(
                type="paragraph",
                text="15号线没有C和D状态的区段；维持现有日常维护的管控措施。",
            ),
        ],
    )
    hit = harvest_control_prose([doc])
    paras = "\n".join((hit.get("by_line") or {}).get("15号线") or [])
    assert "没有C和D" in paras


def test_control_prose_keeps_status_preamble_and_risk_topics():
    from chapters.overhead.extract import harvest_control_prose

    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="w6.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路管控措施", level=3),
            Block(type="heading", text="1.1.8轨道交通12号线", level=3),
            Block(
                type="paragraph",
                text="12号线一期、二期刚性接触网状态是B, 部分锚段是C状态。存在一些分险点，如部分锚段加速取流段磨耗增长速度较快，目前已达11mm。",
            ),
            Block(type="paragraph", text="现有风险点的管控措施是：根据磨耗预警要求及时跟踪预警。"),
            Block(type="heading", text="1.1.9轨道交通16号线", level=3),
            Block(type="paragraph", text="16号线开通至本年度已运行12年，部分设备老化，主要设备风险体现在以下几点："),
            Block(type="paragraph", text="维护六部对16号线端部弯头实行差异化检调策略，触发警戒值5mm立即更换。"),
            Block(type="paragraph", text="接触轨防护罩老化"),
            Block(type="paragraph", text="16号线接触轨防护罩已运行12年，存在严重老化、松脱现象。"),
            Block(type="paragraph", text="后续风险管控措施如下："),
            Block(type="paragraph", text="集中修项目：计划更换2500组新防护罩。"),
            Block(type="heading", text="1.1.10轨道交通17号线", level=3),
            Block(type="paragraph", text="17号线本年度经接触网设备整体更新改造，主要设备风险体现在以下几点："),
            Block(type="paragraph", text="暗埋电缆："),
            Block(
                type="paragraph",
                text="暗埋电缆主要布置在正线段过轨电缆以及徐泾车场、朱家角车场可视化接地柜。盖板覆盖形式为站台处最多的敷设方式，部分自攻丝对电缆外皮造成磨损，长期运行存在极大的接地风险。",
            ),
            Block(type="paragraph", text="现有管控措施是：差异化进行电缆专项检查。"),
        ],
    )
    hit = harvest_control_prose([doc])
    twelve = "\n".join((hit.get("by_line") or {}).get("12号线") or [])
    sixteen = "\n".join((hit.get("by_line") or {}).get("16号线") or [])
    seventeen = "\n".join((hit.get("by_line") or {}).get("17号线") or [])
    assert "状态是B" in twelve and "11mm" in twelve
    assert "开通至本年度" in sixteen
    assert "接触轨防护罩老化" in sixteen
    assert "5mm立即更换" in sixteen
    assert "暗埋电缆" in seventeen
    assert "盖板覆盖" in seventeen
    assert "自攻丝" in seventeen


def test_controls_keeps_line15_kind_measures_not_no_cd_echo():
    from chapters.overhead.extract import extract_overhead_controls

    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="轨道交通5号线风险点及管控措施", level=3),
            Block(type="paragraph", text="7号线设备状态："),
            Block(type="paragraph", text="接触网状态：C状态区段为北延伸段柔性段。"),
            Block(type="heading", text="轨道交通15号线", level=3),
            Block(
                type="paragraph",
                text="15号线刚性接触网系统（接触线、汇流排、定位点）设备2021年投运，全线共计51个锚段因磨耗较大纳入B类跟踪管控。",
            ),
            Block(
                type="paragraph",
                text="柔性接触网系统（接触线、定位装置、分段绝缘器）设备2021年投运，全线设备综合评级均为A类，运行状态良好，无专项特殊管控需求。",
            ),
            Block(
                type="paragraph",
                text="隔离开关2021年投运，其中3座车站设备状态评级为B类，受新华PLC退场影响。",
            ),
            Block(type="paragraph", text="15号线柔性没有C和D状态的区段，维持现有管控措施。"),
            Block(type="paragraph", text="15号线刚性没有C和D状态的区段，维持现有管控措施。"),
        ],
    )
    hit = extract_overhead_controls([doc])
    fifteen = next(s for s in hit["sections"] if "15号线" in s["title"])
    paras = fifteen["paras"]
    blob = "\n".join(paras)
    assert paras[0] == "1、刚性设备"
    assert "51个锚段" in blob
    assert "无专项特殊管控需求" in blob
    assert "新华PLC" in blob
    assert "没有C和D" not in blob
    assert any(p.startswith("2、柔性设备") for p in paras)
    assert any(p.startswith("3、隔离开关") for p in paras)


def test_control_prose_line7_keeps_measures_drops_status_dump():
    from chapters.overhead.extract import extract_overhead_controls

    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="轨道交通5号线风险点及管控措施", level=3),
            Block(type="paragraph", text="7号线设备状态："),
            Block(type="paragraph", text="柔性接触网："),
            Block(
                type="paragraph",
                text="接触网状态：C状态区段为北延伸段柔性段（含罗南新村至美兰湖上行等）一期。子系统为C状态，潘广路洞口-花木路接触线超限运行。",
            ),
            Block(
                type="paragraph",
                text="集中修项目：覆盖北延伸刚性段、一期及北延伸柔性段，共涉及大量定位点、隔离开关与分段绝缘器，投入车梯共计182台。",
            ),
            Block(type="paragraph", text="大修更新改造：北延伸及一期柔性段拟纳入2027年更新项目。"),
            Block(type="paragraph", text="专项更换：包括北延伸户外段及陈太路基地的接触线、尾支线等部件更换。"),
            Block(type="paragraph", text="差异化管控：加强北延伸中2区间巡视频次，并对龙阳路停车场受力部件进行全面更换。"),
            Block(type="paragraph", text="刚性接触网："),
            Block(
                type="paragraph",
                text="2023年对7号线隧道段实施大修；已纳入2023年“1号线一期、7号线地下段接触网设备更新改造项目”，2023起至2026年完成。",
            ),
            Block(type="paragraph", text="现7号线没有C和D状态的区段，维持现有管控措施。"),
            Block(type="paragraph", text="隔离开关："),
            Block(
                type="paragraph",
                text="7号线C状态的区段是：7号线一期含龙阳路车场、龙华中路、上大路等；7号线北延伸含美兰湖、顾村公园。",
            ),
            Block(type="paragraph", text="隔离开关控制屏："),
            Block(
                type="paragraph",
                text="7线路C状态的区段是7号线一期正线含陈太路车辆段混合变电站；7号线没有D状态的区段。",
            ),
            Block(type="paragraph", text="管控策略包括："),
            Block(
                type="paragraph",
                text="1、集中修项目：（1）对7号线北延伸刚性段开展集中修作业，需对2020个刚性定位点进行集中修。",
            ),
            Block(
                type="paragraph",
                text="2、大修更新改造：7号线北延伸及一期刚性段已纳入2023年更新改造项目，2024起至2026年完成。",
            ),
            Block(type="paragraph", text="3、专项更换：针对7号线户外段84套尾支线进行更换。"),
            Block(type="paragraph", text="4、差异化管控：对7号线北延伸中2区间加强巡视。"),
            Block(type="paragraph", text="10号线接触网状态"),
            Block(type="paragraph", text="隔离开关：C状态区间为10号线一期、二期的隔离开关，一期隔离开关设备老化。"),
            Block(type="paragraph", text="管控策略包括："),
            Block(type="paragraph", text="1、集中修项目：对10号线一期开展集中修作业，需对10659个刚性定位点进行集中修。"),
        ],
    )
    hit = extract_overhead_controls([doc])
    seven = next(s for s in hit["sections"] if "7号线" in s["title"])
    blob = "\n".join(seven["paras"])
    assert "投入车梯共计182台" in blob
    assert "拟纳入2027年更新项目" in blob
    assert "2020个刚性定位点" in blob
    assert "84套尾支线" in blob
    assert "设备状态" not in blob
    assert "柔性接触网" not in blob
    assert "接触网状态" not in blob
    assert "罗南新村至美兰湖" not in blob
    assert "龙阳路车场" not in blob
    assert "混合变电站" not in blob
    assert "没有C和D" not in blob
    assert "没有D状态" not in blob
    ten = next(s for s in hit["sections"] if "10号线" in s["title"])
    ten_blob = "\n".join(ten["paras"])
    assert "10659个刚性定位点" in ten_blob
    assert "C状态区间" not in ten_blob


def test_control_prose_understands_status_heading_aliases():
    from chapters.overhead.extract import extract_overhead_controls

    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2.1.2各线路管控措施", level=2),
            Block(type="paragraph", text="10号线触网状态"),
            Block(type="paragraph", text="隔离开关：C状态区间为10号线一期、二期的隔离开关，一期隔离开关设备老化。"),
            Block(type="paragraph", text="隔离开关控制屏：C状态区间为10号线一期；D状态区间为吴中路车场。"),
            Block(type="paragraph", text="管控策略包括："),
            Block(type="paragraph", text="1、集中修项目：对10号线一期开展集中修作业，需对10659个刚性定位点进行集中修。"),
            Block(type="paragraph", text="2、大修更新改造：10号线一期已于2026年开始大修更新改造项目。"),
        ],
    )
    hit = extract_overhead_controls([doc])
    ten = next(s for s in hit["sections"] if "10号线" in s["title"])
    blob = "\n".join(ten["paras"])
    assert "10659个刚性定位点" in blob
    assert "2026年开始大修" in blob
    assert "C状态区间" not in blob
    assert "D状态区间" not in blob
    assert "触网状态" not in blob


def test_control_prose_drops_line11_cd_location_inventory():
    from chapters.overhead.extract import extract_overhead_controls

    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="轨道交通5号线风险点及管控措施", level=3),
            Block(
                type="paragraph",
                text="11号线一期刚性段接触网子系统是A状态，一期柔性是C状态。管控策略包括：",
            ),
            Block(type="paragraph", text="集中修检验检测："),
            Block(
                type="paragraph",
                text="2026年3月10日-2026年6月10日，11号线户外段及车场全部完成，共3136处定位点，发现缺陷32处，已全部整改。",
            ),
            Block(type="paragraph", text="大修更新改造：11号线一期刚性段已大修完毕，目前处于验收阶段。"),
            Block(type="paragraph", text="专项更换：11号线吊弦专项整治共需完成510套。"),
            Block(type="paragraph", text="差异化管控：对设备评分为C的设备加强巡视，原巡视频次14天/次调整为7天/次。"),
            Block(
                type="paragraph",
                text="11号线C、D状态的柔性主要集中在一期（嘉定北-桃浦洞口），目前处于大修改造中，管控策略包括：",
            ),
            Block(
                type="paragraph",
                text="11号线C状态的刚性主要集中在二期与迪士尼段（江苏路-罗山路），预计30年成立改造项目，管控策略包括：",
            ),
            Block(
                type="paragraph",
                text="11号线C状态的隔离开关主要集中在一期柔性（嘉定北-桃浦新村），管控策略包括。",
            ),
            Block(
                type="paragraph",
                text="11号线C状态的隔离开关控制屏全线均匀分布（花桥站、嘉定北-桃浦新村），管控策略包括。",
            ),
            Block(type="paragraph", text="12、集中修检验检测：对该区段开展集中修作业，需对33台隔离开关控制屏开展集中修。"),
            Block(type="paragraph", text="13、备品备件：新华PLC备件无法采购、目前采用一期大修后遗留的旧件当备品。"),
        ],
    )
    hit = extract_overhead_controls([doc])
    eleven = next(s for s in hit["sections"] if "11号线" in s["title"])
    blob = "\n".join(eleven["paras"])
    assert "3136处定位点" in blob
    assert "一期刚性段已大修完毕" in blob
    assert "吊弦专项整治" in blob
    assert "14天/次调整为7天/次" in blob
    assert "新华PLC" in blob
    assert "33台隔离开关控制屏" in blob
    assert "主要集中在" not in blob
    assert "全线均匀分布" not in blob
    assert "嘉定北-桃浦洞口" not in blob
    assert "江苏路-罗山路" not in blob
    assert "子系统是A状态" not in blob






def test_control_prose_keeps_mainline_and_extension_status():
    from chapters.overhead.extract import harvest_control_prose

    older = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2.1.2各线路管控措施", level=2),
            Block(type="paragraph", text="3号线正线触网子系统和设备状态是 C"),
            Block(type="paragraph", text="主要风险点："),
            Block(type="paragraph", text="1）3号中潭路渡线发生上部定位绳垂直吊弦断裂事件。"),
            Block(type="paragraph", text="现有管控措施是：开展年度生产计划与接触网集中修。"),
            Block(type="paragraph", text="3号线北延伸触网子系统和设备状态是B"),
        ],
    )
    newer = DocumentModel(
        source_name="维护七部9.2.docx",
        source_path="w72.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="2.1.2各线路管控措施", level=2),
            Block(type="paragraph", text="3号线正线触网子系统和设备状态是 C"),
            Block(type="paragraph", text="现有管控措施是：开展年度生产计划与接触网集中修。"),
            Block(type="paragraph", text="3号线北延伸触网子系统和设备状态是B"),
            Block(type="paragraph", text="后续的管控措施是："),
            Block(type="paragraph", text="1、专项更换：将全线58处横跨列入更换计划。"),
        ],
    )
    hit = harvest_control_prose([older, newer])
    blob = "\n".join((hit.get("by_line") or {}).get("3号线") or [])
    assert "正线触网子系统和设备状态是 C" not in blob
    assert "北延伸触网子系统和设备状态是B" not in blob
    assert "中潭路" in blob
    assert "58处横跨" in blob


def test_control_prose_copies_in_progress_project_table():
    from chapters.overhead.extract import extract_overhead_controls

    rows = [
        ["2025年在执行项目情况", "", "", "", ""],
        ["序号", "项目类别", "项目类别2", "项目名称", "合同（标段）名称"],
        ["1", "大修更新改造项目", "", "2025年大修更新改造项目", "上海轨道交通 3/4 号线 供电系统更新改造工程"],
    ]
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通3号线", level=3),
            Block(type="paragraph", text="13、专项更换（集中修）：对3号线北延伸段馈线金属抱箍进行排查和整治。"),
            Block(type="paragraph", text="管控措施"),
            Block(type="table", rows=rows, source_index=8),
            Block(type="heading", text="轨道交通4号线", level=3),
            Block(type="paragraph", text="1、差异化管控：针对接口处分段每月检查一次。"),
        ],
    )
    hit = extract_overhead_controls([doc])
    three = next(s for s in hit["sections"] if "3号线" in s["title"])
    flow = (three.get("fill") or {}).get("flow") or []
    tables = [x for x in flow if x.get("kind") == "table"]
    assert tables
    blob = "".join(str(c) for r in tables[0]["rows"] for c in r)
    assert "在执行项目" in blob
    assert "3/4" in blob
    four = next(s for s in hit["sections"] if "4号线" in s["title"])
    four_flow = (four.get("fill") or {}).get("flow") or []
    assert not any(x.get("kind") == "table" for x in four_flow)


def test_control_prose_skips_training_table():
    from chapters.overhead.extract import extract_overhead_controls

    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="3.4 各线路管控措施", level=2),
            Block(type="heading", text="轨道交通16号线", level=3),
            Block(type="paragraph", text="现有管控措施是：差异化进行电缆专项检查。"),
            Block(
                type="table",
                rows=[
                    ["项目名称", "人次", "项目总课时"],
                    ["质量安全培训", "980", "9800"],
                ],
                source_index=9,
            ),
        ],
    )
    hit = extract_overhead_controls([doc])
    sixteen = next(s for s in hit["sections"] if "16号线" in s["title"])
    flow = (sixteen.get("fill") or {}).get("flow") or []
    assert not any(x.get("kind") == "table" for x in flow)



def test_overhead_stock_reads_rule_pdf_touchwang_tables():
    from chapters.overhead.extract import extract_overhead_stock

    doc = DocumentModel(
        source_name="附件1：《维保供电安全库存管理规定》（QSD-WBZ-FB-AQ-GDG59—2025）.pdf",
        source_path="rule.pdf",
        suffix=".pdf",
        blocks=[
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
                    ["序号", "设备大类", "设备中类", "物料名称", "规格型号", "计量单位", "安全库存数量"],
                    ["1", "综保装置", "10kV综合保护继电器", "P121", "台", "1"],
                ],
            ),
        ],
    )
    hit = extract_overhead_stock([doc])
    assert not hit.get("empty")
    blob = "".join(str(c) for r in (hit.get("table") or []) for c in r)
    assert "CTA-120" in blob or "铜银接触线" in blob
    assert "综保" not in blob
    assert "P121" not in "".join(str(c) for item in (hit.get("flow") or []) for r in (item.get("rows") or []) for c in r)


