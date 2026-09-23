# -*- coding: utf-8 -*-
"""年报 Word 共用入口：封面、标题、正文、黄标判断。

黄标题（add_heading yellow）对整节缺材料；黄句子（needs_mark / add_para yellow）对不通顺的那一句。
出处只用 source_name 填进标题括号。
"""
from chapters.common.word import (
    add_cover,
    add_heading,
    add_para,
    any_incomplete,
    any_needs_mark,
    is_incomplete,
    is_punct_issue,
    language_note,
    needs_mark,
    new_report_document,
    punct_note,
    split_clauses,
    source_name,
)

__all__ = [
    "add_cover",
    "add_heading",
    "add_para",
    "any_incomplete",
    "any_needs_mark",
    "is_incomplete",
    "is_punct_issue",
    "language_note",
    "needs_mark",
    "new_report_document",
    "punct_note",
    "split_clauses",
    "source_name",
]
