# -*- coding: utf-8 -*-
"""解析去重口径：单元格内容相同的总表只留一份（优先文件名带 _1 的）。"""
from parsers.dedupe import drop_duplicate_tables, table_fingerprint
from parsers.document_model import Block, DocumentModel


def _doc(name: str, rows: list[list[str]], suffix: str = ".xlsx") -> DocumentModel:
    return DocumentModel(
        source_name=name,
        source_path=name,
        suffix=suffix,
        blocks=[
            Block(type="heading", text="工作表:评估结果", level=1),
            Block(type="table", rows=rows),
        ],
    )


HEADER = ["大类", "线路", "区段", "应急电源设备", "能耗设备"]
ROWS = [
    HEADER,
    ["供电", "1号线", "正线", "A", "/"],
    ["能源系统", "1号线", "正线", "/", "B"],
]


def test_same_cells_same_fingerprint():
    messy = [
        ["大类", "线路", "区段", "应急电源设备", "能耗设备", ""],
        ["供电", "1 号线", "正\n线", "A", "/", ""],
        ["能源系统", "1号线", "正线", "/", "B"],
    ]
    assert table_fingerprint(ROWS) == table_fingerprint(messy)  # 空列、换行、空格不改变指纹


def test_different_content_keeps_both():
    other = [HEADER, ["供电", "2号线", "正线", "C", "/"]]
    docs = [_doc("a.xlsx", ROWS), _doc("b.xlsx", other)]
    drop_duplicate_tables(docs)
    assert sum(1 for d in docs for b in d.blocks if b.type == "table") == 2


def test_same_content_different_names_keep_one():
    a = _doc("设备评估结果总表（4月）.xlsx", ROWS)
    b = _doc("备份-总表.xlsx", ROWS)
    c = _doc("设备评估结果总表（4月）_1.xlsx", ROWS)
    drop_duplicate_tables([a, b, c])
    tables = [(d.source_name, b) for d in (a, b, c) for b in d.blocks if b.type == "table"]
    assert len(tables) == 1  # 重复总表只留一份
    assert tables[0][0] == "设备评估结果总表（4月）_1.xlsx"  # 同内容时优先带 _1 的文件名


def test_row_order_does_not_double_count():
    shuffled = [HEADER, ROWS[2], ROWS[1]]
    docs = [_doc("old.xlsx", ROWS), _doc("copy.docx", shuffled, ".docx")]
    drop_duplicate_tables(docs)
    assert sum(1 for d in docs for b in d.blocks if b.type == "table") == 1  # 行序打乱仍算同一张表


def test_duplicate_sheet_in_one_file():
    doc = DocumentModel(
        source_name="一本.xlsx",
        source_path="一本.xlsx",
        suffix=".xlsx",
        blocks=[
            Block(type="heading", text="工作表:Sheet1", level=1),
            Block(type="table", rows=ROWS),
            Block(type="heading", text="工作表:Sheet1备份", level=1),
            Block(type="table", rows=ROWS),
        ],
    )
    drop_duplicate_tables([doc])
    assert [b.type for b in doc.blocks] == ["heading", "table"]  # 同一文件内重复工作表只留第一张
    assert doc.blocks[0].text == "工作表:Sheet1"
