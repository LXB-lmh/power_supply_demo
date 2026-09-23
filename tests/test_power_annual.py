# -*- coding: utf-8 -*-
"""供电年报版式与抽取口径：锁定 2025 宋体/表宽；3.3.2 表不含接触网；材料没有的不编造。"""
from pathlib import Path

from catalog.taxonomy import chapter_ready
from chapters.power.extract import extract_all
from chapters.power.write import write_full_docx
from chapters.registry import get_handler
from parsers.dispatch import parse_files


def test_report_uses_2025_songti():
    from docx.oxml.ns import qn

    from chapters.common.word import add_heading, add_para, new_report_document

    doc = new_report_document()
    add_heading(doc, "3.4  各线路管控措施", 2)
    add_heading(doc, "轨道交通2号线", 3)
    add_para(doc, "西延伸：暂未纳入大修更新改造规划。")
    from chapters.common.word import add_caption, add_table

    add_caption(doc, "表3-1 设备评级分类")
    add_table(doc, [["设备评级", "评级范围"], ["A类", "90≤评分≤100"]], widths=[2772, 5522])
    heading = next(p for p in doc.paragraphs if p.text.startswith("轨道交通"))
    body = next(p for p in doc.paragraphs if p.text.startswith("西延伸"))
    caption = next(p for p in doc.paragraphs if p.text.startswith("表3-1"))
    hr = heading.runs[0]
    br = body.runs[0]
    assert hr.font.name == "宋体"
    assert hr._element.rPr.find(qn("w:rFonts")).get(qn("w:eastAsia")) == "宋体"
    assert hr.font.size.pt == 12
    assert br.font.name == "宋体"
    assert br._element.rPr.find(qn("w:rFonts")).get(qn("w:eastAsia")) == "宋体"
    assert br.font.size.pt == 12
    theme = hr._element.rPr.find(qn("w:rFonts")).get(qn("w:eastAsiaTheme"))
    assert theme is None  # 不用主题字体，避免东亚文字落到 Calibri
    assert caption.alignment is not None
    assert int(caption.alignment) == 1  # 表题居中
    assert caption.paragraph_format.first_line_indent in (None, 0) or caption.paragraph_format.first_line_indent.pt == 0
    assert len(doc.tables) >= 1
    sec = doc.sections[0]
    assert abs(int(sec.page_width) - 7560310) < 200  # A4 宽度（EMU）贴 2025 年报
    assert abs(int(sec.left_margin) - 1143000) < 200


def test_ch3_locked_sections_match_2025_layout(tmp_path):
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX
    from docx.oxml.ns import qn

    from chapters.power.style import CH3_METHOD, CH3_METHOD_MISSING, GRADE_TEXT, SCOPE_LEAD
    from chapters.power.write import write_chapter_docx

    out = tmp_path / "ch3.docx"
    write_chapter_docx({"year": 2026, "ch3": {}}, out, "ch3")
    doc = Document(str(out))
    texts = [p.text.strip() for p in doc.paragraphs]
    heading_31 = next(p for p in doc.paragraphs if p.text.startswith("3.1"))
    heading_32 = next(p for p in doc.paragraphs if p.text.startswith("3.2"))
    heading_331 = next(p for p in doc.paragraphs if p.text.startswith("3.3.1"))
    assert "评估方法和内容" in heading_31.text
    assert "评估标准" in heading_32.text
    assert "供电子系统设备评估范围" in heading_331.text
    for heading in (heading_31, heading_32, heading_331):
        assert CH3_METHOD_MISSING in heading.text
        assert any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in heading.runs)
    assert CH3_METHOD not in texts
    assert GRADE_TEXT[0] not in texts
    assert SCOPE_LEAD not in texts
    assert not any(t.startswith("3.2.1") for t in texts)  # 3.2 不再拆 3.2.1

    h_indent = heading_32.paragraph_format.first_line_indent
    assert h_indent is None or int(h_indent) == 0
    assert heading_32._p.find(qn("w:pPr")).find(qn("w:numPr")) is None  # 节标题不用 Word 自动编号
    assert heading_32.runs[0].bold in (None, False)


def test_ch3_extracted_standard_and_scope_keep_2025_table_layout(tmp_path):
    from docx import Document
    from docx.oxml.ns import qn

    from chapters.power.style import CH3_FORMULA_LEAD, GRADE_TABLE, GRADE_TEXT, SCOPE_LEAD, SCOPE_TABLE
    from chapters.power.write import write_chapter_docx

    pack = {
        "year": 2026,
        "ch3": {
            "standard": {
                "paras": list(GRADE_TEXT),
                "flow": (
                    [{"kind": "para", "text": line} for line in GRADE_TEXT]
                    + [{"kind": "para", "text": "表3-1 设备评级分类"}, {"kind": "table", "rows": GRADE_TABLE}]
                ),
                "source": "去年报告.docx",
            },
            "scope": {
                "paras": [SCOPE_LEAD, CH3_FORMULA_LEAD],
                "flow": [
                    {"kind": "para", "text": SCOPE_LEAD},
                    {"kind": "para", "text": "表3-2 设施设备分类表"},
                    # SCOPE_TABLE 是大类列纵向合并的规格表；vmerge 模拟去年报告解析出的合并元数据
                    {"kind": "table", "rows": SCOPE_TABLE, "vmerge": [[0, 1, len(SCOPE_TABLE) - 1]]},
                    {"kind": "para", "text": CH3_FORMULA_LEAD},
                ],
                "source": "去年报告.docx",
            },
        },
    }
    out = tmp_path / "ch3_prose.docx"
    write_chapter_docx(pack, out, "ch3")
    doc = Document(str(out))
    texts = [p.text.strip() for p in doc.paragraphs]
    caption = next(p for p in doc.paragraphs if p.text == "表3-1 设备评级分类")
    assert int(caption.alignment) == 1
    body = next(p for p in doc.paragraphs if p.text.startswith("设备状态分为"))
    assert int(body.paragraph_format.first_line_indent) == 304800  # 正文首行缩进 2 字符（twips）

    t1 = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "设备评级")
    tbl_pr = t1._tbl.tblPr
    tw = tbl_pr.find(qn("w:tblW"))
    assert tw.get(qn("w:type")) == "dxa"
    # 单章预览路径（write_chapter_docx）表3-1 走通用宽度 6636；完整报告（write_full_docx）为 8294，
    # 后者已由用户检查确认符合 2025 版式。此处锁定单章路径现状，不改产品代码。
    assert tw.get(qn("w:w")) == "6636"
    grid = [g.get(qn("w:w")) for g in t1._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert grid == ["2220", "4416"]
    cell_sp = t1.cell(0, 0).paragraphs[0].paragraph_format.line_spacing
    assert cell_sp in (1.0, 1) or (cell_sp is not None and abs(float(cell_sp) - 1.0) < 0.05)
    assert t1.cell(0, 0).paragraphs[0].alignment is not None
    assert int(t1.cell(0, 0).paragraphs[0].alignment) == 1

    t2 = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "大类")
    vm = t2._tbl.findall(qn("w:tr"))[1].findall(qn("w:tc"))[0].find(qn("w:tcPr")).find(qn("w:vMerge"))
    assert vm is not None
    assert vm.get(qn("w:val")) == "restart"  # 大类列纵向合并从本行起
    jc2 = t2.rows[1].cells[2].paragraphs[0].alignment
    assert jc2 is not None and int(jc2) == 3  # 范围列两端对齐，贴 2025 表2
    assert any("综合评估表达式如下" in t for t in texts)
    assert any("子系统线路状态评分" in t for t in texts)
    assert any("（3-1）" in t for t in texts)


def test_formula_3_1_keeps_2025_layout():
    from chapters.common.word import add_formula_3_1, new_report_document

    doc = new_report_document()
    add_formula_3_1(doc)
    eq = next(p for p in doc.paragraphs if "（3-1）" in p.text)
    assert "Σ" in eq.text and "s =" in eq.text
    assert any((r.font.subscript or r.font.superscript) for r in eq.runs)
    joined = "".join(p.text for p in doc.paragraphs)
    assert "子系统线路状态评分" in joined
    assert "类设备的权重" in joined
    assert "类设备的评分" in joined


def test_ch3_result_tables_match_2025_layout(tmp_path):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.shared import Pt

    from chapters.power.style import CH3_T33_WIDTHS, CH3_T310_WIDTHS
    from chapters.power.write import write_chapter_docx

    power = [["线路", "区段", *["应急电源设备", "配电系统（降压）", "配电系统（牵引）", "变压器设备", "电力电缆设备", "电力监控设备", "杂散电流设备"]]]
    power.append(["1号线", "正线", "A", "B", "B", "A", "A", "B", "A"])
    compare = [["线路", "区段", "时间", "应急电源设备", "配电系统（降压）", "配电系统（牵引）", "变压器设备", "电力电缆设备", "电力监控设备", "杂散电流设备"]]
    compare.append(["1号线", "正线", "2025", "A", "B", "B", "A", "A", "B", "A"])
    compare.append(["1号线", "正线", "2026", "A", "C", "B", "A", "A", "B", "A"])
    pack = {
        "year": 2026,
        "ch3": {
            "power_table": power,
            "overview": "供电（不含接触网设备）、主变电所系统、能源系统设备评估1项，其中，A类设备1项，B类设备0项，C类设备0项，D类设备0项。供电完成1项，其中A类设备1项，B类设备0项，C类设备0项，D类设备0项。",
            "compare_power": compare,
            "migrations": ["1号线正线，配电系统（降压），由B迁移到C"],
        },
    }
    out = tmp_path / "ch3_tables.docx"
    write_chapter_docx(pack, out, "ch3")
    doc = Document(str(out))
    t3 = next(
        t
        for t in doc.tables
        if len(t.columns) >= 9 and t.rows[0].cells[2].text.strip() == "应急电源设备"
    )
    grid = [g.get(qn("w:w")) for g in t3._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert grid == [str(w) for w in CH3_T33_WIDTHS]
    assert t3.cell(1, 0).paragraphs[0].runs[0].font.size == Pt(11)
    t10 = next(t for t in doc.tables if len(t.columns) >= 4 and t.rows[0].cells[2].text.strip() == "时间")
    grid10 = [g.get(qn("w:w")) for g in t10._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert grid10 == [str(w) for w in CH3_T310_WIDTHS]
    vm = t10._tbl.findall(qn("w:tr"))[1].findall(qn("w:tc"))[0].find(qn("w:tcPr")).find(qn("w:vMerge"))
    assert vm is not None and vm.get(qn("w:val")) == "restart"
    lead = next(p for p in doc.paragraphs if p.text.startswith("与上一年度"))
    assert lead.paragraph_format.first_line_indent is None or int(lead.paragraph_format.first_line_indent) == 0  # 对比段不缩进
    cap3 = next(p for p in doc.paragraphs if p.text == "表3-3 供电各类设备评估结果表")
    assert int(cap3.alignment) == 1


def test_all_power_tables_use_2025_widths():
    from docx.oxml.ns import qn

    from chapters.common.word import add_table, new_report_document
    from chapters.power.format import FIGURE_MAX_CX, spec_for
    from chapters.power.style import GRADE_TABLE, WORKFLOW_TABLE
    from chapters.ch4.power_style import CYCLE_TABLE
    from chapters.common.drawings import scale_drawing_node
    from lxml import etree

    assert spec_for(GRADE_TABLE)["widths"] == [2772, 5522]
    assert spec_for(WORKFLOW_TABLE)["widths"] == [664, 1738, 3748, 2143]
    assert spec_for(CYCLE_TABLE)["widths"] == [1656, 2136, 3181]
    doc = new_report_document()
    add_table(doc, WORKFLOW_TABLE)
    grid = [g.get(qn("w:w")) for g in doc.tables[0]._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))]
    assert grid == ["664", "1738", "3748", "2143"]
    tw = doc.tables[0]._tbl.tblPr.find(qn("w:tblW"))
    assert tw.get(qn("w:type")) == "dxa"
    assert tw.get(qn("w:w")) == "8293"
    add_table(doc, CYCLE_TABLE)
    tw4 = doc.tables[1]._tbl.tblPr.find(qn("w:tblW"))
    assert tw4.get(qn("w:type")) == "dxa"
    assert tw4.get(qn("w:w")) == "6973"

    NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
    node = etree.fromstring(
        f'<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        f'xmlns:a="{NS}"><a:ext cx="10000000" cy="5000000"/></w:drawing>'
    )
    scale_drawing_node(node)
    ext = node.find(f"{{{NS}}}ext")
    assert int(ext.get("cx")) == FIGURE_MAX_CX
    assert int(ext.get("cy")) == int(5000000 * FIGURE_MAX_CX / 10000000)


def test_power_chapters_ready():
    for cid in ("ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11"):
        assert chapter_ready("power_supply", cid) is True
        assert get_handler("power_supply", cid) is not None
        assert get_handler("overhead", cid) is not None  # 接触网第3～11章已按触网体例独立接入


def test_annual_extract_no_invent(tmp_path):
    root = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料")
    zong = root / "设备功能有效性" / "设备评估结果总表（4月）_1.xlsx"
    if not zong.exists():
        return
    docs = parse_files([zong])
    pack = extract_all(docs, year=2026)
    assert pack["ch3"]["power_table"]
    assert pack["ch3"]["overview"]
    assert "接触网" not in "".join(pack["ch3"]["power_table"][0])  # 3.3.2 供电表不含接触网列
    assert not pack["ch5"]["law"]  # 只给了总表，不编第五章法规
    assert not pack["ch9"]["table"]
    out = tmp_path / "full.docx"
    write_full_docx(pack, out)
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document(str(out))
    titles = [p.text for p in doc.paragraphs if p.text.strip()]
    assert any(t.startswith("3.3.2") and "设备评估结果总表" in t for t in titles)
    assert any(t.startswith("表3-3") for t in titles)
    assert any(t.startswith("附录A") for t in titles)
    assert any(t.startswith("5.1") for t in titles)

    def yellow(p):
        return any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)

    yellow_titles = [p.text for p in doc.paragraphs if p.text.strip() and yellow(p)]
    # 5.1/5.2 已由「今年缺材料时复用去年项目保底报告」功能填充，不再标黄；5.3-5.6 仍缺材料标黄
    assert any(t.startswith("5.3") for t in yellow_titles)
    assert any(t.startswith("4.4") for t in yellow_titles)
    assert not any("【材料未提供】" in t for t in titles)  # 不写占位套话，只标黄


def test_compare_years_pairs_every_segment():
    from chapters.power.extract import compare_years
    from chapters.power.write import _compare_vmerge

    prior = [
        ["线路", "区段", "应急电源设备", "变压器设备"],
        ["1号线", "北北延伸", "/", "/"],
        ["1号线", "正线", "C", "B"],
        ["18号线", "一期", "A", "A"],
        ["18号线", "二期", "B", "A"],
    ]
    current = [
        ["线路", "区段", "应急电源设备", "变压器设备"],
        ["1号线", "正线", "B", "B"],
        ["18号线", "一期南段", "B", "A"],
        ["18号线", "一期北段", "B", "A"],
        ["18号线", "二期", "A", "A"],
    ]
    rows = compare_years(prior, current, 2025, 2026)
    body = rows[1:]
    assert [r[2] for r in body] == ["2025", "2026"] * (len(body) // 2)  # 每个区段成对出现两年
    keys = [(body[i][0], body[i][1]) for i in range(0, len(body), 2)]
    assert keys == [  # 上年区段与本年拆分段都保留，不合并成一条
        ("1号线", "北北延伸"),
        ("1号线", "正线"),
        ("18号线", "一期"),
        ("18号线", "一期南段"),
        ("18号线", "一期北段"),
        ("18号线", "二期"),
    ]
    south = next(r for r in body if r[1] == "一期南段" and r[2] == "2025")
    assert south[3:] == ["/", "/"]  # 本年才拆出的区段，上年填 /
    north26 = next(r for r in body if r[1] == "一期北段" and r[2] == "2026")
    assert north26[3:] == ["B", "A"]
    stub = next(r for r in body if r[1] == "一期" and r[2] == "2026")
    assert stub[3:] == ["/", "/"]  # 上年「一期」本年已拆段，当年行填 /
    assert body[-2][1] == "二期" and body[-1][1] == "二期"
    merges = _compare_vmerge(rows)
    assert len(merges) == len(keys) * 2  # 线路、区段两列都要纵向合并
