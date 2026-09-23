# -*- coding: utf-8 -*-
from chapters.overhead.llm_gate import filter_event_sections, keep_mask, using_llm
from chapters.overhead.extract import extract_chapter
from parsers.document_model import Block, DocumentModel


def test_keep_mask_without_llm_keeps_all(monkeypatch):
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "0")
    texts = ["8号线联航路接触网设备断裂故障分析", "3号线一期存在2处大磨耗，已达预警值"]
    assert keep_mask(texts, kind="event") == [True, True]


def test_keep_mask_uses_model_drop(monkeypatch):
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    def fake_json(system, user, temperature=0):
        return {"keep": [True, False]}

    monkeypatch.setattr("engine.llm_client.chat_json", fake_json)
    texts = ["8号线联航路接触网设备断裂故障分析 发布抢修令", "3号线一期存在2处大磨耗，已达预警值"]
    with using_llm(True):
        assert keep_mask(texts, kind="event") == [True, False]


def test_keep_mask_control_kind_drops_status_inventory(monkeypatch):
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("engine.llm_client.chat_json", lambda *a, **k: {"keep": [False, True]})
    texts = [
        "隔离开关：C状态区间为10号线一期、二期的隔离开关",
        "1、集中修项目：对10号线一期开展集中修作业，需对10659个刚性定位点进行集中修",
    ]
    with using_llm(True):
        assert keep_mask(texts, kind="control") == [False, True]


def test_filter_event_sections_drops_wear(monkeypatch):
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("engine.llm_client.chat_json", lambda *a, **k: {"keep": [True, False]})
    sections = [
        {"title": "8号线联航路断裂故障分析", "paras": ["发布0866#抢修令"], "empty": False, "fill": {"flow": [], "paras": ["发布0866#抢修令"]}},
        {"title": "3号线一期大磨耗", "paras": ["已达预警值"], "empty": False, "fill": {"flow": [], "paras": ["已达预警值"]}},
    ]
    with using_llm(True):
        out = filter_event_sections(sections)
    assert len(out) == 1
    assert "联航路" in out[0]["title"]


def test_extract_chapter_default_skips_llm(monkeypatch):
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "0")

    def boom(*args, **kwargs):
        raise AssertionError("tests must not call DeepSeek")

    monkeypatch.setattr("engine.llm_client.chat_json", boom)
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="8号线联航路接触网设备断裂故障分析"),
            Block(type="paragraph", text="2025年11月26日联航路分段绝缘器断裂，发布0866#抢修令。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch8", prior_docs=[], prior_via="baseline_2025")
    assert any("断裂故障分析" in (n.get("title") or "") for n in pack["outline"])
