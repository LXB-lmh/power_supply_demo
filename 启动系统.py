# -*- coding: utf-8 -*-
"""IDE 运行入口：启动本机网页服务（http://127.0.0.1:8000）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 保证从任意工作目录启动时都能 import 到项目包
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def start_web() -> None:
    from web_server import run

    run()


if __name__ == "__main__":
    start_web()
