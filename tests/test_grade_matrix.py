# -*- coding: utf-8 -*-
"""设备评估结果总表口径：重复总表只抽一份；供电摘要按大类拆，主变全 / 行不生成摘要。"""
from parsers.document_model import Block, DocumentModel
from scope.grade_matrix import extract_grade_matrix, is_grade_matrix, summaries_from_matrix


def _matrix_doc():
    header = [
        "大类",
        "线路",
        "区段",
        "接触网（轨）设备",
        "应急电源设备",
        "配电系统（降压）",
        "配电系统（牵引）",
        "变压器设备",
        "电力电缆设备",
        "电力监控设备",
        "杂散电流设备",
        "配电设备",
        "能耗设备",
    ]
    rows = [
        header,
        ["供电", "_1号线", "正线", "B", "A", "C", "B", "B", "B", "B", "B", "/", "/"],
        ["能源系统", "_1号线", "正线", "/", "/", "/", "/", "/", "/", "/", "/", "/", "B"],
        ["主变电所", "_1号线", "正线", "/", "/", "/", "/", "/", "/", "/", "/", "/", "/"],
        ["供电", "_2号线", "正线", "A", "/", "B", "B", "A", "A", "A", "C", "/", "/"],
    ]
    return DocumentModel(
        source_name="设备评估结果总表（4月）.xlsx",
        source_path="x.xlsx",
        suffix=".xlsx",
        blocks=[Block(type="table", rows=rows)],
    )


def test_detect_grade_matrix():
    rows = _matrix_doc().blocks[0].rows
    assert is_grade_matrix(rows[0])
    assert is_grade_matrix(rows[0], rows)


def test_empty_or_slash_only_table_is_not_grade_matrix():
    header = _matrix_doc().blocks[0].rows[0]
    empty = [header]
    slash_only = [
        header,
        ["供电", "1号线", "正线", "/", "/", "/", "/", "/", "/", "/", "/", "/", "/"],
        ["主变电所", "1号线", "北北延伸", "/", "/", "/", "/", "/", "/", "/", "/", "/", "/"],
    ]
    assert is_grade_matrix(header, empty) is False
    assert is_grade_matrix(header, slash_only) is False
    doc = DocumentModel(
        source_name="空总表模板.xlsx",
        source_path="empty.xlsx",
        suffix=".xlsx",
        blocks=[Block(type="table", rows=slash_only)],
    )
    assert extract_grade_matrix([doc]) == []


def test_duplicate_zong_files_count_once():
    a = _matrix_doc()
    b = DocumentModel(
        source_name="设备评估结果总表（4月）_1.xlsx",
        source_path="y.xlsx",
        suffix=".xlsx",
        blocks=a.blocks,
    )
    c = DocumentModel(
        source_name="设备评估结果总表（4月）.xlsx",
        source_path="z.xlsx",
        suffix=".xlsx",
        blocks=a.blocks,
    )
    matrix = extract_grade_matrix([a, b, c])
    assert len(matrix) == 4  # 三份同内容总表只抽一次，得到供电两行+能源+主变（主变全 / 也留）
    assert matrix[0]["source_note"] == "设备评估结果总表（4月）_1.xlsx"  # 出处标带 _1 的那份


def test_extract_and_summaries():
    matrix = extract_grade_matrix([_matrix_doc()])
    assert len(matrix) == 4
    power = [row for row in matrix if row["category"] == "供电"]
    assert power[0]["grades"]["应急电源设备"] == "A"
    assert power[0]["grades"]["杂散电流设备"] == "B"
    main_rows = [row for row in matrix if row["category"] == "主变电所"]
    assert main_rows and not main_rows[0]["grades"]  # 全 / 行留下，等级字典为空
    emergency = summaries_from_matrix(matrix, "emergency_power", "power_supply")
    assert len(emergency) == 1  # 只取供电大类的应急电源，能源/主变不混入
    assert emergency[0]["line_id"] == "1号线"
    assert emergency[0]["grade"] == "A"
    assert emergency[0]["score_source"] == "grade_table"
    energy = summaries_from_matrix(matrix, "energy", "power_supply")
    assert len(energy) == 1
    assert energy[0]["grade"] == "B"
    stray = summaries_from_matrix(matrix, "stray_current", "power_supply")
    assert {row["line_id"] for row in stray} == {"1号线", "2号线"}
    two = next(row for row in stray if row["line_id"] == "2号线")
    assert two["grade"] == "C"
    main = summaries_from_matrix(matrix, "ms_emergency_power", "main_substation")
    assert main == []  # 主变应急电源列全是 /，不生成摘要


def test_all_slash_row_kept_in_ch3_tables():
    """主变 1号线 北北延伸 各列都是 /，3.3.2 表 3-4 仍要有这一行。"""
    from chapters.power.extract import extract_grade_tables
    from chapters.power.style import MS_COLS

    header = [
        "大类",
        "线路",
        "区段",
        "应急电源设备",
        "变压器设备",
        "电力电缆设备",
        "电力监控设备",
        "配电设备",
        "接触网（轨）设备",
        "配电系统（降压）",
        "配电系统（牵引）",
        "杂散电流设备",
        "能耗设备",
    ]
    rows = [
        header,
        ["主变电所", "1号线", "北北延伸", "/", "/", "/", "/", "/", "/", "/", "/", "/", "/"],
        ["主变电所", "1号线", "北延伸", "A", "B", "A", "A", "B", "/", "/", "/", "/", "/"],
    ]
    doc = DocumentModel(
        source_name="设备评估结果总表.xlsx",
        source_path="x.xlsx",
        suffix=".xlsx",
        blocks=[Block(type="table", rows=rows)],
    )
    pack = extract_grade_tables([doc])
    main = pack["main_table"]
    assert main[0][2:] == MS_COLS
    slash = next(r for r in main[1:] if r[0] == "1号线" and r[1] == "北北延伸")
    assert slash[2:] == ["/"] * len(MS_COLS)
    north = next(r for r in main[1:] if r[0] == "1号线" and r[1] == "北延伸")
    assert north[2] == "A"
