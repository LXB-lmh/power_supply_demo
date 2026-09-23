# -*- coding: utf-8 -*-
"""共用列宽算法。供电/触网各自的表头规格仍放在本专业 format/style 里。"""
from __future__ import annotations

# 2025 多数表 grid 合计约 8294 twip，不要再拉成通栏 100%。
CONTENT_TWIPS = 8294


def even_widths(n: int, total: int = CONTENT_TWIPS) -> list[int]:
    """把正文区宽度均分到各列。"""
    if n <= 0:
        return []
    base, rem = divmod(int(total), n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def pad_widths(widths: list[int] | None, ncols: int, total: int = CONTENT_TWIPS) -> list[int]:
    """列数比底稿多时，把余宽分给新列，避免表格撑出页边。"""
    if ncols <= 0:
        return []
    if not widths:
        return even_widths(ncols, total)
    used = [int(w) for w in widths[:ncols]]
    if len(used) < ncols:
        extra_n = ncols - len(used)
        leftover = total - sum(used)
        if leftover >= 300 * extra_n:
            used.extend(even_widths(extra_n, leftover))
        else:
            used.extend(even_widths(extra_n, 400 * extra_n))
            s = sum(used)
            if s > total > 0:
                used = [max(200, int(w * total / s)) for w in used]
                used[-1] += total - sum(used)
    return used
