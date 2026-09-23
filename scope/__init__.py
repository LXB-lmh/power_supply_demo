# -*- coding: utf-8 -*-
"""范围名、预览、历史报告登记。台账抽检（ledger）是旧评分路径，年报填空主要用 grade_matrix。"""
from scope.names import file_fingerprint, format_scope, normalize_line, normalize_segment, scope_key
from scope.preview import preview_files
from scope.registry import list_reports, register_report
