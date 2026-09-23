# -*- coding: utf-8 -*-
"""命令行启动网页。浏览器会在服务就绪后打开 http://127.0.0.1:8000。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from web_server import run

if __name__ == "__main__":
    run()
