# -*- coding: utf-8 -*-
import pytest


@pytest.fixture(autouse=True)
def _disable_overhead_llm_gate(monkeypatch):
    """单测默认不打 DeepSeek；需要时在用例里打开 OVERHEAD_LLM_GATE。"""
    monkeypatch.setenv("OVERHEAD_LLM_GATE", "0")
    monkeypatch.setenv("LOGIC_LLM_GATE", "0")


@pytest.fixture(autouse=True)
def _reset_source_yellow():
    from chapters.common.source_yellow import reset

    reset()
    yield
    reset()
