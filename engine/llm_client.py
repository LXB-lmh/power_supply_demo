# -*- coding: utf-8 -*-
"""DeepSeek / 本地 OpenAI 兼容接口。

用途：材料分章、段落 keep/drop、成文后逻辑校对。
禁止：编造年报数字、评估小结、整改建议正文。
没有 DEEPSEEK_API_KEY 时跳过模型，规则抽取仍可用。
后期本地部署：改 .env 的 DEEPSEEK_BASE_URL、DEEPSEEK_MODEL 即可。
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .config import get_deepseek_config


def llm_enabled() -> bool:
    try:
        cfg = get_deepseek_config()
    except Exception:
        return False
    return bool((cfg.get("api_key") or "").strip())


def get_client() -> OpenAI:
    cfg = get_deepseek_config()
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60.0)


def _parse_json_object(text: str) -> Any:
    raw = (text or "").strip() or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise
        return json.loads(m.group(0))


def chat_json(system: str, user: str, temperature: float = 0.1) -> Any:
    """要模型只回 JSON。分章、keep/drop 用。"""
    cfg = get_deepseek_config()
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    try:
        resp = client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    text = resp.choices[0].message.content or "{}"
    return _parse_json_object(text)


def chat_text(system: str, user: str, temperature: float = 0.3) -> str:
    """纯文本对话。年报成文不要走这里补句子。"""
    cfg = get_deepseek_config()
    client = get_client()
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def parse_json_array(payload: dict) -> list[dict]:
    if "devices" in payload and isinstance(payload["devices"], list):
        return payload["devices"]
    for v in payload.values():
        if isinstance(v, list):
            return v
    raise ValueError(f"LLM 返回 JSON 中未找到 devices 数组: {list(payload.keys())}")
