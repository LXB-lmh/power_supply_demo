# -*- coding: utf-8 -*-
"""从项目根 .env 读 DeepSeek。没有密钥时分章跳过模型，不挡规则抽取。"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")


def get_deepseek_config() -> dict[str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，请在 .env 文件中设置")
    return {"api_key": api_key, "base_url": base_url, "model": model}
