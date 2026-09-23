# -*- coding: utf-8 -*-
"""触网第3章状态分布表抽取。"""

from chapters.overhead.ch3_status import extract_status_distribution, is_status_distribution_table
from chapters.overhead.extract import extract_chapter
from chapters.overhead.prior_resolve import resolve_prior_docs
from parsers.document_model import Block, DocumentModel


def test_status_table_detector():
    rows = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["1号线", "179", "26", "14.52%", "3", "1.68%", "120", "67.04%", "30", "16.76%"],
    ]
    assert is_status_distribution_table(rows)
    assert not is_status_distribution_table([["线路", "区段", "接触网（轨）设备"], ["1号线", "正线", "A"]])


def test_merge_flexible_from_two_depts():
    docs = [
        DocumentModel(
            source_name="维护六部.docx",
            source_path="a.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="各线路柔性接触网状态分布", level=4),
                Block(type="paragraph", text="表3-5a 各线路柔性接触网状态"),
                Block(
                    type="table",
                    rows=[
                        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
                        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
                        ["2号线", "10", "1", "10%", "2", "20%", "3", "30%", "4", "40%"],
                        ["6号线", "20", "5", "25%", "5", "25%", "5", "25%", "5", "25%"],
                    ],
                ),
            ],
        ),
        DocumentModel(
            source_name="维护七部.docx",
            source_path="b.docx",
            suffix=".docx",
            blocks=[
                Block(type="heading", text="各线路柔性接触网状态分布", level=4),
                Block(type="paragraph", text="表3-5a 各线路柔性接触网状态"),
                Block(
                    type="table",
                    rows=[
                        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
                        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
                        ["1号线", "179", "26", "14.52%", "3", "1.68%", "120", "67.04%", "30", "16.76%"],
                        ["3号线", "167", "0", "0%", "67", "40.12%", "100", "59.88%", "0", "0.00%"],
                    ],
                ),
            ],
        ),
    ]
    hit = extract_status_distribution(docs)
    flex = hit["各线路柔性接触网状态分布"]
    lines = [r[0] for r in flex["table"][2:]]
    assert "1号线" in lines and "2号线" in lines and "6号线" in lines
    tbl = next(x for x in flex["flow"] if x.get("kind") == "table")
    assert tbl.get("widths") and tbl["widths"][0] >= 890
    assert tbl.get("force_rebuild")


def test_single_row_dept_table_accepted():
    rows = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["10号线", "12", "1", "8%", "2", "17%", "3", "25%", "4", "33%"],
    ]
    assert is_status_distribution_table(rows)


def test_reject_misaligned_row_as_anchor_total():
    from chapters.overhead.ch3_status import merge_status_tables

    rows_hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    merged = merge_status_tables(
        [
            {
                "rows": rows_hdr + [["1号线", "45.00%", "20", "10%", "1", "5%", "0", "0%", "0", "0%"]],
                "source": "错位表.docx",
                "caption": "表3-5a",
                "notes": [],
                "_recency": 2.0,
                "_idx": 0,
            },
            {
                "rows": rows_hdr + [["1号线", "179", "26", "14.52%", "3", "1.68%", "120", "67.04%", "30", "16.76%"]],
                "source": "正确表.docx",
                "caption": "表3-5a",
                "notes": [],
                "_recency": 1.0,
                "_idx": 1,
            },
        ],
        kind="各线路柔性接触网状态分布",
    )
    row1 = next(r for r in merged["table"] if str(r[0]).startswith("1"))
    assert row1[1] == "179"


def test_backfill_line10_from_older_bucket():
    from chapters.overhead.ch3_status import merge_status_tables

    rows_hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    merged = merge_status_tables(
        [
            {
                "rows": rows_hdr + [["10号线", "5", "1", "20%", "1", "20%", "1", "20%", "1", "20%"]],
                "source": "十号线专稿.docx",
                "caption": "表3-5a",
                "notes": ["10号线：", "十号线 C 类集中在某某段。"],
                "_recency": 1.0,
                "_idx": 0,
            },
            {
                "rows": rows_hdr
                + [["1号线", "179", "26", "14.52%", "3", "1.68%", "120", "67.04%", "30", "16.76%"]]
                + [["10号线", "0", "0", "0%", "0", "0%", "0", "0%", "0", "0%"]],
                "source": "新总表.docx",
                "caption": "表3-5a",
                "notes": ["10号线："],
                "_recency": 2.0,
                "_idx": 1,
            },
        ],
        kind="各线路柔性接触网状态分布",
    )
    row10 = next(r for r in merged["table"] if str(r[0]).replace(" ", "").startswith("10"))
    assert row10[1] == "5"
    note_blob = " ".join(x.get("text") or "" for x in merged["flow"] if x.get("kind") == "para")
    assert "十号线 C 类" in note_blob or "C 类集中" in note_blob


def test_newest_zero_row_does_not_erase_older_data():
    from chapters.overhead.ch3_status import merge_status_tables

    rows_hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    merged = merge_status_tables(
        [
            {
                "rows": rows_hdr + [["10号线", "50", "1", "2%", "2", "4%", "3", "6%", "4", "8%"]],
                "source": "旧部.docx",
                "caption": "表3-5a",
                "notes": [],
                "media": [],
                "_recency": 1.0,
                "_idx": 0,
            },
            {
                "rows": rows_hdr + [["10号线", "0", "0", "0%", "0", "0%", "0", "0%", "0", "0%"]],
                "source": "新部.docx",
                "caption": "表3-5a",
                "notes": [],
                "media": [],
                "_recency": 2.0,
                "_idx": 1,
            },
        ],
        kind="各线路柔性接触网状态分布",
    )
    row10 = next(r for r in merged["table"] if str(r[0]).startswith("10"))
    assert row10[1] == "50"


def test_merge_newest_file_wins_for_same_line():
    """同线路多文件：以后上传/较新文件为准，不用『非空更多』误选 228。"""
    rows_hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    from chapters.overhead.ch3_status import merge_status_tables

    merged = merge_status_tables(
        [
            {
                "rows": rows_hdr + [["1号线", "228", "0", "0%", "0", "0%", "0", "0%", "0", "0%"]],
                "source": "旧部.docx",
                "caption": "表3-5a",
                "notes": [],
                "_recency": 1.0,
                "_idx": 0,
            },
            {
                "rows": rows_hdr + [["1号线", "179", "26", "14.52%", "3", "1.68%", "120", "67.04%", "30", "16.76%"]],
                "source": "新部.docx",
                "caption": "表3-5a",
                "notes": [],
                "_recency": 2.0,
                "_idx": 1,
            },
        ]
    )
    data = merged["table"][2]
    assert data[1] == "179"
    # 同线路新旧文件冲突：默认静默采用新值（用户确认口径），不产生警告
    assert not any("1号线" in w for w in merged.get("warnings") or [])


def test_context_before_uses_nearest_caption():
    from chapters.overhead.ch3_status import _context_before, classify_status_kind

    hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    row = ["1号线", "10", "1", "10%", "1", "10%", "1", "10%", "0", "0%"]
    blocks = [
        Block(type="paragraph", text="各线路柔性接触网状态"),
        Block(type="table", rows=hdr + [row]),
        Block(type="paragraph", text="各线路刚性接触网状态"),
        Block(type="table", rows=hdr + [row]),
    ]
    assert classify_status_kind(_context_before(blocks, 1)) == "各线路柔性接触网状态分布"
    assert classify_status_kind(_context_before(blocks, 3)) == "各线路刚性接触网状态分布"
    from chapters.overhead.ch3_status import _split_after_status_table, packed_status_table_clusters

    hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    lines = [["1号线", "10", "1", "10%", "1", "10%", "1", "10%", "0", "0%"], ["10号线", "12", "1", "8%", "2", "17%", "3", "25%", "4", "33%"]]
    doc = DocumentModel(
        source_name="维护五部9.7.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路柔性接触网状态"),
            Block(type="table", rows=hdr + lines),
            Block(type="paragraph", text="各线路刚性接触网状态"),
            Block(type="table", rows=hdr + lines),
            Block(type="paragraph", text="各线路隔离开关状态"),
            Block(type="table", rows=hdr + lines),
            Block(type="paragraph", text="各线路隔离开关控制屏状态"),
            Block(type="table", rows=hdr + lines),
            Block(type="paragraph", text="1号线设备状态："),
            Block(type="paragraph", text="接触网状态：北延伸为A。"),
            Block(type="heading", text="轨道交通5号线风险点及管控措施", level=3),
            Block(type="paragraph", text="10号线接触网状态"),
            Block(type="paragraph", text="柔性接触网："),
            Block(type="paragraph", text="接触网状态：C状态区段为10号线一期（吴中路停车场）。"),
            Block(type="paragraph", text="11号线C、D状态的柔性主要集中在一期（嘉定北-桃浦洞口）。"),
        ],
    )
    idxs = [i for i, b in enumerate(doc.blocks) if b.type == "table"]
    clusters = packed_status_table_clusters(doc.blocks, idxs)
    assert clusters and len(clusters[0]) == 4
    _, notes = _split_after_status_table(doc.blocks, idxs[-1], doc, follow_line_sections=True)
    from chapters.overhead.line_notes import paragraphs_to_line_notes, slice_note_for_kind

    by, _ = paragraphs_to_line_notes(notes)
    assert "10" in by and "吴中路停车场" in by["10"]
    assert "11" in by and "嘉定北" in by["11"]
    flex = slice_note_for_kind(by["10"], "各线路柔性接触网状态分布")
    assert "吴中路停车场" in flex
    assert "海伦路" not in flex


def test_risk_control_section_not_sucked_into_switch_notes():
    from chapters.overhead.ch3_status import extract_status_distribution

    hdr = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
    ]
    row5 = ["5号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"]
    row7 = ["7号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"]
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路隔离开关状态"),
            Block(type="table", rows=hdr + [row5, row7]),
            Block(type="paragraph", text="5号线："),
            Block(type="paragraph", text="隔离开关：全线无C、D状态区段，维持现有管控。"),
            Block(type="heading", text="轨道交通5号线风险点及管控措施", level=3),
            Block(type="paragraph", text="隔离开关：现有风险管控措施：400mm²直流电缆已对全线电缆进行排查。"),
            Block(type="paragraph", text="隧道漏水：现有风险管控措施：定期查看。"),
            Block(type="paragraph", text="7号线设备状态："),
            Block(type="paragraph", text="隔离开关：北延伸无C、D状态区段。"),
        ],
    )
    hit = extract_status_distribution([doc])["各线路隔离开关状态分布"]
    blob = "\n".join(x.get("text") or "" for x in hit.get("flow") or [] if x.get("kind") == "para")
    assert "维持现有管控" in blob
    assert "400mm²" not in blob
    assert "隧道漏水" not in blob
    assert "北延伸无C" in blob


def test_kind_headers_not_globally_deduped():
    from chapters.overhead.ch3_status import extract_status_distribution

    hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    row10 = ["10号线", "12", "1", "8%", "2", "17%", "3", "25%", "4", "33%"]
    doc = DocumentModel(
        source_name="维护五部9.7.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路柔性接触网状态"),
            Block(type="table", rows=hdr + [row10]),
            Block(type="paragraph", text="各线路刚性接触网状态"),
            Block(type="table", rows=hdr + [row10]),
            Block(type="paragraph", text="各线路隔离开关状态"),
            Block(type="table", rows=hdr + [row10]),
            Block(type="paragraph", text="各线路隔离开关控制屏状态"),
            Block(type="table", rows=hdr + [row10]),
            Block(type="paragraph", text="7号线设备状态："),
            Block(type="paragraph", text="刚性接触网："),
            Block(type="paragraph", text="现7号线没有C和D状态的区段。"),
            Block(type="paragraph", text="10号线接触网状态"),
            Block(type="paragraph", text="刚性接触网："),
            Block(type="paragraph", text="接触网状态：C状态区段为10号线一期（海伦路）。"),
            Block(type="paragraph", text="柔性接触网："),
            Block(type="paragraph", text="接触网状态：C状态区段为10号线一期（吴中路停车场）。"),
        ],
    )
    hit = extract_status_distribution([doc])["各线路柔性接触网状态分布"]
    blob = "\n".join(x.get("text") or "" for x in hit.get("flow") or [] if x.get("kind") == "para")
    assert "吴中路停车场" in blob
    assert "海伦路" not in blob


def test_figure_title_does_not_stop_status_notes():
    from chapters.overhead.ch3_status import _is_status_caption, _split_after_status_table
    from chapters.overhead.line_notes import paragraphs_to_line_notes

    assert not _is_status_caption("图3-3 各线路刚性接触网状态")
    assert _is_status_caption("各线路刚性接触网状态")
    hdr = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
    ]
    doc = DocumentModel(
        source_name="维护六部9.3.docx",
        source_path="w6.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路刚性接触网状态分布"),
            Block(type="table", rows=hdr + [["2号线", "10", "1", "10%", "1", "10%", "1", "10%", "0", "0%"]]),
            Block(type="paragraph", text="图3-3 各线路刚性接触网状态"),
            Block(type="paragraph", text="其中："),
            Block(
                type="paragraph",
                text="2号线C状态的区段有2号线西西延伸（含国家会展中心至虹桥火车站上行等）。",
            ),
            Block(type="paragraph", text="6号线C、D状态的区段有灵岩南路-东方体育中心下行。"),
            Block(type="heading", text="1.1.2接触轨状态分布", level=3),
        ],
    )
    _, notes = _split_after_status_table(doc.blocks, 1, doc)
    by, _ = paragraphs_to_line_notes(notes)
    assert "2" in by and "国家会展中心" in by["2"]
    assert "6" in by and "灵岩南路" in by["6"]


def test_collect_multipara_notes_after_table():
    from chapters.overhead.ch3_status import _split_after_status_table
    from parsers.document_model import Block, DocumentModel

    doc = DocumentModel(
        source_name="线2.docx",
        source_path="线2.docx",
        suffix=".docx",
        blocks=[
            Block(type="table", rows=[["线路", "锚段数量", "A", "A"], ["1号线", "1", "0", "0%"]]),
            Block(type="paragraph", text="其中："),
            Block(type="paragraph", text="2号线："),
            Block(type="paragraph", text="C 类区段在龙阳路。"),
            Block(type="paragraph", text="3号线："),
            Block(type="paragraph", text="无 D 类。"),
        ],
    )
    _, notes = _split_after_status_table(doc.blocks, 0, doc)
    from chapters.overhead.line_notes import paragraphs_to_line_notes

    by_line, _ = paragraphs_to_line_notes(notes)
    assert "龙阳路" in by_line.get("2", "")
    assert "无 D" in by_line.get("3", "")


def test_note_dedupe_same_line():
    from chapters.overhead.section_bundle import merge_note_paragraphs

    paras, _ = merge_note_paragraphs(
        [
            {"notes": ["4号线：无 C、D 类设备，通过日常检查、集中修及差异化维护进行常规化管理。"]},
            {"notes": ["4号线：无 C、D 类设备，通过日常检查、集中修及差异化维护进行常规化管理。"]},
        ]
    )
    assert paras.count("4号线：无 C、D 类设备，通过日常检查、集中修及差异化维护进行常规化管理。") == 1


def test_slice_before_merge_keeps_flex_from_older_file():
    from chapters.overhead.ch3_status import _merge_table_notes_flow

    rows = [
        ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
        ["10号线", "12", "1", "8%", "2", "17%", "3", "25%", "4", "33%"],
    ]
    flow, _ = _merge_table_notes_flow(
        rows,
        [
            {
                "notes": ["10号线：", "柔性接触网：", "接触网状态：C状态区段为10号线一期（吴中路停车场）。"],
                "_recency": 1,
                "_idx": 0,
                "_source": "六部.docx",
            },
            {
                "notes": ["10号线：", "刚性接触网：", "接触网状态：C状态区段为10号线一期（海伦路）。"],
                "_recency": 2,
                "_idx": 1,
                "_source": "五部.docx",
            },
        ],
        None,
        "各线路柔性接触网状态分布",
    )
    blob = "\n".join(x.get("text") or "" for x in flow if x.get("kind") == "para")
    assert "吴中路停车场" in blob
    assert "海伦路" not in blob
    prior = resolve_prior_docs()
    pack = extract_chapter([], year=2026, chapter_id="ch3", prior_docs=prior["docs"], prior_via="baseline_2025")
    node33 = next(n for n in pack["outline"] if n["title"] == "接触网设备状态分布")
    assert not (node33.get("fill") and not node33["fill"].get("empty"))


def test_cluster_closing_after_backfilled_line_in_kind_merge():
    from chapters.overhead.ch3_status import _merge_table_notes_flow

    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["17号线", "164", "8", "5%", "154", "94%", "2", "1%", "0", "0%"],
        ["18号线", "132", "132", "100%", "0", "0%", "0", "0%", "0", "0%"],
    ]
    flow, _ = _merge_table_notes_flow(
        rows,
        [
            {
                "notes": [
                    "17号线C状态的区段是：17号线一期嘉松中路。17号线没有D状态的区段。",
                    "上述D状态的区间，建议进行大修或计划实施大修。",
                ],
                "_recency": 1,
                "_idx": 0,
                "_source": "六部.docx",
            },
        ],
        None,
        "各线路隔离开关状态分布",
    )
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    i17 = next(i for i, t in enumerate(texts) if t.startswith("17号线"))
    i18 = next(i for i, t in enumerate(texts) if t.startswith("18号线"))
    iclose = next(i for i, t in enumerate(texts) if t.startswith("上述"))
    assert i17 < i18 < iclose
    assert "没有C和D" in texts[i18]
    assert "嘉松中路" in texts[i17]


def test_switch_notes_skip_risk_dump_but_keep_next_line():
    from chapters.overhead.ch3_status import extract_status_distribution

    hdr = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
    ]
    row3 = ["3号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"]
    row4 = ["4号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"]
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="各线路隔离开关状态"),
            Block(type="table", rows=hdr + [row3, row4]),
            Block(type="paragraph", text="3号线：C状态的区段是：3号线北延伸（含宝钢1库）；"),
            Block(type="paragraph", text="正线触网子系统和设备状态是 C"),
            Block(type="paragraph", text="主要风险点："),
            Block(type="paragraph", text="1）3号中潭路渡线发生上部定位绳垂直吊弦断裂事件。"),
            Block(type="paragraph", text="现有管控措施是：开展年度生产计划与接触网集中修。"),
            Block(type="paragraph", text="4号线：没有C和D状态的区段，维持现有管控措施。"),
        ],
    )
    hit = extract_status_distribution([doc])["各线路隔离开关状态分布"]
    blob = "\n".join(x.get("text") or "" for x in hit.get("flow") or [] if x.get("kind") == "para")
    assert "中潭路" not in blob
    assert "开展年度生产计划" not in blob
    assert "没有C和D" in blob
