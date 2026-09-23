# -*- coding: utf-8 -*-
"""启动 FastAPI，并保证浏览器打开的是当前这次服务。

uvicorn 不热重载（reload=False）。改 Python 后必须关掉窗口再启动，
只刷新网页不会加载新的抽取/分章逻辑。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000


def _src_newer_than_dist(dist_html: Path) -> bool:
    """源码比上次打包新时，必须重新 npm run build，否则浏览器仍是旧页面。"""
    if not dist_html.exists():
        return True
    stamp = dist_html.stat().st_mtime
    src_root = ROOT / "frontend" / "src"
    if not src_root.exists():
        return False
    for path in src_root.rglob("*"):
        if path.is_file() and path.stat().st_mtime > stamp:
            return True
    extra = [ROOT / "frontend" / "index.html", ROOT / "frontend" / "vite.config.js"]
    return any(p.exists() and p.stat().st_mtime > stamp for p in extra)


def _npm_build() -> None:
    print("正在打包网页（npm run build），稍等……")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=ROOT / "frontend",
        check=False,
        shell=True,
    )
    if result.returncode != 0:
        print("网页打包失败。请在 frontend 目录执行 npm run build 查看报错。")


def ensure_frontend() -> Path:
    """有 dist 且不低于源码就用；源码更新过则重新打包。"""
    dist = ROOT / "frontend" / "dist" / "index.html"
    npm_dir = ROOT / "frontend" / "node_modules"
    if npm_dir.exists() and _src_newer_than_dist(dist):
        _npm_build()
    if not dist.exists():
        print("未找到 frontend/dist，将只提供接口页。请在 frontend 目录执行 npm run build。")
    return dist


def _port_open(host: str, port: int) -> bool:
    """本机该端口是否已有进程在听。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def _listening_pids(port: int) -> list[int]:
    """Windows netstat 查出占用端口的 PID，便于关掉上次没关干净的服务。"""
    try:
        raw = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    found: list[int] = []
    suffix = f":{port}"
    for line in raw.splitlines():
        if "LISTENING" not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[1]
        if not local.endswith(suffix):
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid not in found:
            found.append(pid)
    return found


def free_port(host: str, port: int) -> None:
    """8000 被旧窗口占用时先结束旧进程，避免打开的是上一版代码。"""
    if not _port_open(host, port):
        return
    mine = os.getpid()
    pids = [pid for pid in _listening_pids(port) if pid and pid != mine]
    if not pids:
        raise OSError(f"端口 {port} 已被占用，且无法识别占用进程。请关闭旧窗口后再试。")
    print(f"端口 {port} 被旧进程占用 {pids}，正在关闭……")
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
    for _ in range(20):
        if not _port_open(host, port):
            return
        time.sleep(0.2)
    raise OSError(f"端口 {port} 仍被占用。请手动结束旧的 Python 窗口后再启动。")


def _open_when_ready(health_url: str, page_url: str, timeout: float = 20.0) -> None:
    """等 /api/health 通了再开浏览器，避免打开空白页。"""
    def _go() -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                    if resp.status == 200:
                        webbrowser.open(page_url)
                        return
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.3)
        print(f"服务未在 {timeout:.0f} 秒内就绪，请手动打开 {page_url}")

    threading.Thread(target=_go, daemon=True).start()


def check_runtime() -> None:
    """启动前检查当前解释器是否装了年报所需依赖。"""
    missing: list[str] = []
    for name in ("fastapi", "uvicorn", "docx", "openai", "dotenv", "openpyxl", "pdfplumber"):
        try:
            __import__("docx" if name == "docx" else "dotenv" if name == "dotenv" else name)
        except ImportError:
            missing.append(name)
    if missing:
        raise RuntimeError(
            "当前解释器缺少依赖："
            + "、".join(missing)
            + f"\n解释器：{sys.executable}\n请对该环境执行：pip install -r requirements.txt"
        )


def run(host: str = HOST, port: int = PORT) -> None:
    check_runtime()
    ensure_frontend()
    free_port(host, port)
    page = f"http://{host}:{port}"
    print(f"解释器：{sys.executable}")
    print(f"网页地址：{page}")
    print("浏览器会在服务就绪后自动打开。关闭本窗口即停止服务。")
    _open_when_ready(f"{page}/api/health", page)
    import uvicorn

    # 不热重载：改代码必须重启本窗口
    uvicorn.run("api.main:app", host=host, port=port, reload=False)
