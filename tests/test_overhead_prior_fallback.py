# -*- coding: utf-8 -*-
from chapters.overhead.extract import extract_chapter
from chapters.overhead.prior_resolve import resolve_prior_docs


def test_body_sections_fallback_to_baseline():
    prior = resolve_prior_docs()
    cases = {
        "ch4": ("设备维护周期和维护内容", "接触网 120mm²接触线磨耗预警值规定"),
        "ch7": ("生产组织模式",),
        "ch5": ("特种设备，消防，防雷，高空作业规程", "强制年检或评估情况分析"),
    }
    for cid, titles in cases.items():
        pack = extract_chapter([], year=2026, chapter_id=cid, prior_docs=prior["docs"], prior_via="baseline_2025")
        by = {n["title"]: n for n in pack["outline"]}
        for title in titles:
            node = by[title]
            fill = node.get("fill") or {}
            assert fill and not fill.get("empty"), title
            assert "体例回退" in (fill.get("source") or "") or fill.get("paras") or fill.get("table") or fill.get("flow")
