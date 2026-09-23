# -*- coding: utf-8 -*-
"""将 .doc / .xls 转为 docx / xlsx。

解析材料时自动转换：.doc→.docx，.xls→.xlsx。
顺序：LibreOffice → 本机 Word（PowerShell COM）→ 明确报错。
中文路径先拷到英文临时目录再转，避免 Word COM 路径问题。
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

_SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def find_soffice() -> str | None:
    for name in _SOFFICE_CANDIDATES:
        path = shutil.which(name) if "\\" not in name else Path(name)
        if isinstance(path, Path):
            if path.exists():
                return str(path)
        elif path:
            return path
    return None


def _powershell_exe() -> str:
    candidates = [
        shutil.which("powershell"),
        shutil.which("powershell.exe"),
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe",
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return str(item)
    raise RuntimeError("找不到 powershell.exe")


def _run_ps(script: str, *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as fh:
        fh.write(script)
        ps1 = Path(fh.name)
    try:
        return subprocess.run(
            [
                _powershell_exe(),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    finally:
        try:
            ps1.unlink(missing_ok=True)
        except Exception:
            pass


def _ascii_work_copy(path: Path, suffix: str) -> tuple[Path, Path]:
    """拷到 %TEMP%\\ps_oh_conv\\<hash>\\in.xxx，避免中文路径让 Word COM 失败。"""
    digest = hashlib.md5(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:12]
    root = Path(tempfile.gettempdir()) / "ps_oh_conv" / digest
    root.mkdir(parents=True, exist_ok=True)
    src_copy = root / f"in{suffix}"
    shutil.copy2(path, src_copy)
    return src_copy, root


def _convert_with_soffice(path: Path, dest_dir: Path, target: str) -> Path:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError("未检测到 LibreOffice")
    dest_dir.mkdir(parents=True, exist_ok=True)
    # soffice 对中文路径一般可用，仍优先用原路径
    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        target,
        "--outdir",
        str(dest_dir),
        str(path),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"LibreOffice 转换失败: {proc.stderr or proc.stdout}")
    converted = dest_dir / f"{path.stem}.{target}"
    if not converted.exists():
        matches = list(dest_dir.glob(f"{path.stem}*.{target}"))
        if matches:
            converted = matches[0]
    if not converted.exists():
        raise RuntimeError(f"LibreOffice 未生成 {converted.name}")
    return converted


def _convert_doc_with_word_ps(path: Path, dest: Path) -> Path:
    """本机 Word 另存为 .docx。先拷英文临时路径再转。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    src_copy, root = _ascii_work_copy(path, ".doc")
    tmp_out = root / "out.docx"
    if tmp_out.exists():
        tmp_out.unlink()

    src_lit = str(src_copy.resolve()).replace("'", "''")
    dst_lit = str(tmp_out.resolve()).replace("'", "''")
    ps = f"""
$ErrorActionPreference = 'Stop'
$src = '{src_lit}'
$dst = '{dst_lit}'
$word = $null
$doc = $null
try {{
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0
  $doc = $word.Documents.Open($src, $false, $true)
  # 16 = wdFormatXMLDocument
  $doc.SaveAs2($dst, 16)
  $doc.Close($false)
  $doc = $null
}} catch {{
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}} finally {{
  if ($null -ne $doc) {{ try {{ $doc.Close($false) }} catch {{}} }}
  if ($null -ne $word) {{
    try {{ $word.Quit() }} catch {{}}
    try {{ [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) }} catch {{}}
  }}
  [GC]::Collect(); [GC]::WaitForPendingFinalizers()
}}
if (-not (Test-Path -LiteralPath $dst)) {{ [Console]::Error.WriteLine('Word did not create output'); exit 1 }}
Write-Output 'OK'
"""
    ps1 = root / "conv.ps1"
    ps1.write_text(ps, encoding="utf-8-sig")
    proc = subprocess.run(
        [
            _powershell_exe(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=150,
    )
    if proc.returncode != 0 or not tmp_out.is_file():
        detail = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        raise RuntimeError(detail[:400])
    shutil.copy2(tmp_out, dest)
    return dest


def _convert_with_word_pywin32(path: Path, dest: Path) -> Path:
    try:
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise RuntimeError("无 pywin32") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_copy, root = _ascii_work_copy(path, ".doc")
    tmp_out = root / "out_py.docx"
    if tmp_out.exists():
        tmp_out.unlink()
    abs_src = str(src_copy.resolve())
    abs_dst = str(tmp_out.resolve())
    err: list[BaseException] = []

    def _run() -> None:
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            doc = word.Documents.Open(abs_src, ReadOnly=True, AddToRecentFiles=False)
            doc.SaveAs2(abs_dst, FileFormat=16)
            doc.Close(False)
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)
        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception:
                    pass

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=120)
    if th.is_alive():
        raise RuntimeError(f"Word 转换超时：{path.name}")
    if err:
        raise RuntimeError(str(err[0])) from err[0]
    if not tmp_out.is_file():
        raise RuntimeError(f"Word 未生成 {dest.name}")
    shutil.copy2(tmp_out, dest)
    return dest


def converted_sidecar(path: Path, dest_dir: Path | None, target: str) -> Path | None:
    """已转好的 .docx/.xlsx：work_dir、旁路 _converted、同名新后缀。"""
    path = Path(path)
    name = f"{path.stem}.{target}"
    cands = []
    if dest_dir is not None:
        cands.append(Path(dest_dir) / name)
    cands.append(path.parent / "_converted" / name)
    cands.append(path.with_suffix("." + target))
    seen: set[str] = set()
    for cand in cands:
        key = str(cand.resolve()) if cand.exists() else str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand
    return None


_CONVERT_LOCK = threading.Lock()


def convert_legacy(path: Path, dest_dir: Path) -> Path:
    """把老格式转成新格式；成功则返回目标路径。解析时会自动调用。"""
    path = Path(path)
    if path.name.startswith("~$"):
        raise RuntimeError(f"跳过 Office 临时锁文件：{path.name}")
    suffix = path.suffix.lower()
    target = {".doc": "docx", ".xls": "xlsx"}.get(suffix)
    if not target:
        raise ValueError(f"不支持的老格式: {path.suffix}")
    hit = converted_sidecar(path, dest_dir, target)
    if hit is not None and hit.stat().st_mtime >= path.stat().st_mtime:
        return hit

    dest_dir.mkdir(parents=True, exist_ok=True)
    converted = dest_dir / f"{path.stem}.{target}"
    if converted.is_file() and converted.stat().st_mtime >= path.stat().st_mtime:
        return converted

    with _CONVERT_LOCK:
        hit = converted_sidecar(path, dest_dir, target)
        if hit is not None and hit.stat().st_mtime >= path.stat().st_mtime:
            return hit
        if converted.is_file() and converted.stat().st_mtime >= path.stat().st_mtime:
            return converted

        errors: list[str] = []

        if find_soffice():
            try:
                return _convert_with_soffice(path, dest_dir, target)
            except Exception as exc:
                errors.append(f"LibreOffice: {exc}")

        if suffix == ".doc":
            try:
                return _convert_doc_with_word_ps(path, converted)
            except Exception as exc:
                errors.append(f"Word: {exc}")
            try:
                return _convert_with_word_pywin32(path, converted)
            except Exception as exc:
                errors.append(f"Word(pywin32): {exc}")

        tip = "；".join(errors) if errors else "无可用转换器"
        raise RuntimeError(
            f"无法将 {path.name} 转为 .{target}（{tip}）。"
            f"请确认已安装 Microsoft Word（推荐）或 LibreOffice；"
            f"也可在 Word 中另存为 .{target} 后再上传。"
        )
