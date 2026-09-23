# -*- coding: utf-8 -*-
"""上传路径口径：嵌套相对路径落在工作根下；`..` 不能逃出目录。"""
from pathlib import Path

from api.main import _rel_dest


def test_nested_upload_path_stays_under_root(tmp_path: Path):
    dest = _rel_dest(tmp_path, "评估材料/99-26年/00-线路报告/1号线.docx", 0)
    assert dest.parent.exists()
    assert dest.name == "1号线.docx"
    assert "00-线路报告" in dest.parts
    dest.write_text("x", encoding="utf-8")
    dup = _rel_dest(tmp_path, "评估材料/99-26年/00-线路报告/1号线.docx", 1)
    assert dup.name == "1号线_1.docx"  # 同路径再次上传时加序号，不覆盖


def test_rejects_parent_escape(tmp_path: Path):
    dest = _rel_dest(tmp_path, "../secret.txt", 0)
    dest.resolve().relative_to(tmp_path.resolve())  # 若逃出根会抛错
    assert dest.name == "secret.txt"  # `..` 被剥掉，文件仍落在根下
