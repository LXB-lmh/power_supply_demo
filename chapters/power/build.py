# -*- coding: utf-8 -*-
"""从今年评估材料目录生成完整供电年报。

这是 CLI 全年报入口。网页按章评估走 chapters.run，不经过本文件。
收文件时跳过接触网目录，以及用户自己的第四章 Word。
报废情况说明、空调/起重/打印等退运材料留给第 11 章按线路汇总。
"""
from __future__ import annotations

from pathlib import Path

from chapters.power.extract import extract_all
from chapters.power.write import write_full_docx
from parsers.dispatch import parse_files

SKIP_DIR = ("触网", "接触网评估报告")
# 不读用户已写成的第四章、接触网分册、旧总表（无 _1 的 4 月版）。3.5 不用这些当去年对照。
SKIP_NAME = (
    "供电评估报告_第四章",
    "故障台账导出",
    "设备评估结果总表（4月）.xlsx",
)
SKIP_RETIRE = ("工器具", "仪器仪表")


def canonical_files(root: Path, *, year: int = 2026) -> list[Path]:
    """从评估材料目录收供电年报该用的 Word/Excel/PDF。

    总表优先 _1.xlsx。线路报告只收各号线变电稿，不含管控措施以外的杂稿。
    交来的材料默认都收，不按路径/文件名里的年份当往年稿丢掉。
    报废情况说明（含上年申请年文件夹）要进第 11 章，不要整夹跳过。
    """
    pack = root / "评估材料" / "99-26年评估报告编制材料"
    if not pack.exists():
        pack = root
    files: list[Path] = []
    prefer_zong = pack / "设备功能有效性" / "设备评估结果总表（4月）_1.xlsx"
    if prefer_zong.exists():
        files.append(prefer_zong)
    for p in sorted(pack.rglob("*")):
        if not p.is_file() or p.name.startswith("~$"):
            continue
        if p.suffix.lower() not in {".docx", ".xlsx", ".pdf"}:
            continue
        rel = str(p.relative_to(pack)).replace("\\", "/")
        if any(k in rel for k in SKIP_DIR):
            continue
        if "4月份评估报告编制材料(2)" in rel:
            continue
        if "00-线路报告" in rel and "管控措施" not in p.name:
            name = p.name
            if p.suffix.lower() != ".docx":
                continue
            # 接触网分册不进；SCADA/能耗等专业稿留给第 11 章抽退运段
            if any(k in name or k in rel for k in ("接触网", "触网", "设备评估表")):
                continue
            if not any(
                f"{i}号线" in name or f"{i}线路" in name for i in range(1, 19)
            ) and not any(k in name for k in ("SCADA", "能耗", "应急电源", "检测检修")):
                continue
        if any(k in p.name for k in SKIP_NAME):
            continue
        if any(k in p.name for k in SKIP_RETIRE) and "供电" not in p.name:
            continue
        if p in files:
            continue
        files.append(p)
    return files


def build(root: str | Path, out_path: str | Path, *, year: int = 2026) -> Path:
    """CLI：解析 canonical 材料 → extract_all → 写出第 1～12 章全年报。网页按章不要调用。"""
    root = Path(root)
    files = canonical_files(root, year=year)
    docs = parse_files(files)
    pack = extract_all(docs, year=year)
    return write_full_docx(pack, out_path)


if __name__ == "__main__":
    demo = Path(__file__).resolve().parents[2]
    src = Path(r"F:\材料\2026供电评估_新")
    dest = demo / "output" / "2026年供电评估报告（供电含能源系统）.docx"
    path = build(src, dest)
    print(path)
