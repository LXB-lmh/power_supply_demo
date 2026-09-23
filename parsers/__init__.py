# -*- coding: utf-8 -*-
"""材料解析入口：Word / Excel / PDF 等到统一的 DocumentModel。

评估抽数和「本章建议」分章都走这里。parse_files 会按表格内容去重，
相同格子只留一份，避免总表备份把项数加成三倍。
"""
from .dispatch import parse_file, parse_files
from .document_model import Block, DocumentModel

__all__ = ["parse_file", "parse_files", "Block", "DocumentModel"]
