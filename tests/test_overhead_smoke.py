# -*- coding: utf-8 -*-
"""接触网目录与 2025 保底稿一致；无材料只黄不瞎填。"""
from pathlib import Path

from chapters.overhead.extract import extract_chapter
from chapters.overhead.outline import baseline_outline, load_baseline_outlines
from chapters.overhead.prior_resolve import BASELINE_PRIOR_DOCX, resolve_prior_docs
from chapters.overhead.write import write_chapter_docx
from chapters.registry import has_handler
from parsers.document_model import Block, DocumentModel


def test_baseline_outline_json_matches_chapters():
    data = load_baseline_outlines()
    for cid in ("ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11"):
        assert cid in data and len(data[cid]) >= 2
    ch3_titles = [x["title"] for x in data["ch3"]]
    assert "接触网设备状态分布" in ch3_titles
    assert "各线路柔性接触网状态分布" in ch3_titles
    assert "和{prev_year}年评估对比结果" in ch3_titles
    assert not any(x.startswith("轨道交通") and x.endswith("号线") for x in ch3_titles)
    ch4_titles = [x["title"] for x in data["ch4"]]
    assert "设备体量变化情况" in ch4_titles
    assert "设备体量" not in ch4_titles
    assert "和{prev_year}年评估对比结果" in ch4_titles
    ch6_titles = [x["title"] for x in data["ch6"]]
    assert "企业标准和制度" in ch6_titles
    ch7_titles = [x["title"] for x in data["ch7"]]
    assert "仪器仪表使用管理方面" in ch7_titles
    assert "智能化应用" in ch7_titles
    ch10_titles = [x["title"] for x in data["ch10"]]
    assert "各线路环境符合性评估" in ch10_titles
    ch8_titles = [x["title"] for x in data["ch8"]]
    assert ch8_titles == ["风险隐患闭环度评估", "设施设备年度突出事件分析", "评估小结"]


def test_baseline_outline_year_substitution():
    nodes = baseline_outline("ch3", year=2026)
    titles = [n["title"] for n in nodes]
    assert "和2025年评估对比结果" in titles
    nodes11 = baseline_outline("ch11", year=2026)
    assert any(n["title"] == "2026年设备退运更换情况" for n in nodes11)


def test_empty_materials_method_falls_back_status_yellow(tmp_path: Path):
    hit = resolve_prior_docs([])
    pack = extract_chapter([], year=2026, chapter_id="ch3", prior_docs=hit["docs"], prior_via="baseline_2025")
    titles = {n["title"]: n for n in pack["outline"]}
    assert titles["设备功能有效性评估"]["title"] == "设备功能有效性评估"
    # 3.1/3.2 无材料时应回退保底体例
    assert titles["评估方法和内容"].get("fill") and not titles["评估方法和内容"]["fill"].get("empty")
    assert "体例回退" in (titles["评估方法和内容"]["fill"].get("source") or "")
    # 3.3 及状态子节无材料则黄
    assert titles["接触网设备状态分布"].get("empty")
    assert titles["各线路柔性接触网状态分布"].get("empty")
    out = tmp_path / "oh.docx"
    write_chapter_docx(pack, out, "ch3")
    assert out.is_file() and out.stat().st_size > 1000


def test_controls_fill_attaches_under_3_4():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="1号线设备状态", level=2),
            Block(type="paragraph", text="集中修项目：柔性户外集中修项目，对1号线北延伸及停车场区段开展集中修作业。"),
            Block(type="paragraph", text="大修更新改造：1号线北延伸段已纳入了2024年接触网更新改造项目。"),
            Block(type="paragraph", text="差异化管控：1号线南延伸区段加强走梯巡视。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch3", prior_docs=[], prior_via="baseline_2025")
    titles = [n["title"] for n in pack["outline"]]
    assert "各线路管控措施" in titles
    assert any("1号线" in t for t in titles)
    parent = next(n for n in pack["outline"] if n["title"] == "各线路管控措施")
    assert parent.get("empty") is False or any(
        "1号线" in (n.get("title") or "") and n.get("fill") for n in pack["outline"]
    )


def test_overhead_handlers_registered():
    assert BASELINE_PRIOR_DOCX.is_file()
    for cid in ("ch3", "ch4", "ch5", "ch6", "ch7", "ch8", "ch9", "ch10", "ch11"):
        assert has_handler("overhead", cid)
