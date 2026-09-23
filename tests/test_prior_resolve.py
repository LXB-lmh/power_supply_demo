# -*- coding: utf-8 -*-
"""去年报告：有上传用上传，否则用项目内 2025 保底。"""
from chapters.power.prior_resolve import BASELINE_PRIOR_DOCX, resolve_prior_docs
from parsers.document_model import Block, DocumentModel


def test_baseline_file_exists():
    assert BASELINE_PRIOR_DOCX.is_file(), f"缺少保底年报：{BASELINE_PRIOR_DOCX}"


def test_resolve_uses_upload_when_provided():
    doc = DocumentModel(
        source_name="用户上传去年报告.docx",
        source_path="u.docx",
        suffix=".docx",
        blocks=[Block(type="heading", text="4.1 设备体量", level=2)],
    )
    hit = resolve_prior_docs([doc])
    assert hit["via"] == "upload"
    assert hit["docs"][0].source_name == "用户上传去年报告.docx"


def test_resolve_falls_back_to_baseline_when_empty():
    hit = resolve_prior_docs([])
    assert hit["via"] == "baseline_2025"
    assert hit["docs"]
    # 保底报告应能扫到第4/5章体例标题
    blob = " ".join((b.text or "") for d in hit["docs"] for b in (d.blocks or [])[:400])
    assert "运营契合" in blob or "4." in blob or "管理体系合规" in blob
