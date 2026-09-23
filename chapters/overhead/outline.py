# -*- coding: utf-8 -*-
"""接触网目录：默认=2025触网保底结构；上传了去年报告则从其 Heading 学结构。

内容型小节（线路名、突出事件题、退运项目名）不进骨架——有当年材料才挂上。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from chapters.common.outline_detect import bare_title
from chapters.common.section_slice import compact_text
from parsers.document_model import DocumentModel

CHAPTER_NAMES = {
    "ch3": "设备功能有效性评估",
    "ch4": "运营契合满足度评估",
    "ch5": "管理体系合规性评估",
    "ch6": "修程修制匹配性评估",
    "ch7": "运维表现健康度评估",
    "ch8": "风险隐患闭环度评估",
    "ch9": "备件物资保障度评估",
    "ch10": "使用环境符合性评估",
    "ch11": "退运报废倾向性评估",
}

# 部门稿常用「满意度」；切小节时一律当下一章标题停。
CHAPTER_STOP_TITLES: tuple[str, ...] = tuple(CHAPTER_NAMES.values()) + (
    "运营契合满意度评估",
    "总结与建议",
    "评估结论与建议",
    "接触系统各线路管控措施",
)


def is_peer_chapter_title(text: str, *, current: str = "") -> bool:
    """短行是否像另一章章名（含「8 风险隐患…」「风险隐患闭环度评估（）」）。"""
    raw = (text or "").strip()
    c = compact_text(raw)
    c = re.sub(r"[（）()]+$", "", c)
    if not c or len(c) > 40:
        return False
    if c.startswith("附录") and len(c) <= 24:
        return True
    c2 = re.sub(r"^第[0-9一二三四五六七八九十]+章", "", c)
    c2 = re.sub(r"^\d{1,2}(?:[.\s、．]+)?", "", c2)
    cur = compact_text(current)
    for name in CHAPTER_STOP_TITLES:
        nc = compact_text(name)
        if not nc or nc == cur:
            continue
        if c2 == nc or c2.startswith(nc):
            return True
    return False

_CONTENT_LINE = re.compile(r"^轨道交通\d{1,2}号线$|^\d{1,2}号线$")
_CONTENT_EVENT = re.compile(r"故障分析|情况说明|侵限|跳闸事件|关于")
_CONTENT_RETIRE = re.compile(r"号线.+退运|退运更换$")
_YEAR_RETIRE = re.compile(r"^20\d{2}年设备退运更换情况$")
_YEAR_COMPARE = re.compile(r"^和20\d{2}年评估对比结果$")

BASELINE_OUTLINE_JSON = Path(__file__).with_name("assets") / "outline_baseline_2025.json"


def is_content_title(text: str) -> bool:
    """线路/事件/退运项目等「材料题」，不是体例骨架。"""
    t = (text or "").strip()
    if not t:
        return False
    if _CONTENT_LINE.match(t):
        return True
    if _CONTENT_EVENT.search(t) and len(t) > 12:
        return True
    if _CONTENT_RETIRE.search(t) and "年设备退运" not in t and "固定资产" not in t:
        return True
    if t in {"概述", "报废原因"}:
        return True
    return False


def _apply_year(title: str, year: int) -> str:
    t = title or ""
    t = t.replace("{year}", str(year))
    t = t.replace("{prev_year}", str(year - 1))
    if _YEAR_RETIRE.match(t):
        return f"{year}年设备退运更换情况"
    if _YEAR_COMPARE.match(t):
        return f"和{year - 1}年评估对比结果"
    return t


@lru_cache(maxsize=1)
def load_baseline_outlines() -> dict[str, list[dict[str, Any]]]:
    if not BASELINE_OUTLINE_JSON.is_file():
        return {}
    data = json.loads(BASELINE_OUTLINE_JSON.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def baseline_outline(chapter_id: str, *, year: int) -> list[dict[str, Any]]:
    raw = list((load_baseline_outlines().get(chapter_id) or []))
    out = []
    for node in raw:
        item = dict(node)
        item["title"] = _apply_year(str(item.get("title") or ""), year)
        item["bare"] = item["title"]
        item["source"] = "2025触网保底目录"
        out.append(item)
    return out


def _headings(doc: DocumentModel) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in doc.blocks or []:
        if block.type != "heading":
            continue
        t = (block.text or "").strip()
        if not t:
            continue
        rows.append({"level": int(block.level or 0) or 1, "text": t, "bare": bare_title(t) or t})
    return rows


def outline_from_docs(
    docs: list[DocumentModel] | None,
    chapter_id: str,
    *,
    year: int,
    structural_only: bool = True,
) -> list[dict[str, Any]]:
    """从去年报告 Heading 提取本章结构。找不到返回空列表。"""
    name = CHAPTER_NAMES.get(chapter_id) or ""
    if not name:
        return []
    chapter_no = int(chapter_id.replace("ch", "") or 3)
    best: list[dict[str, Any]] = []
    for doc in docs or []:
        rows = _headings(doc)
        h1_idx = [i for i, r in enumerate(rows) if r["level"] == 1]
        starts = [i for i, r in enumerate(rows) if r["level"] == 1 and compact_text(r["text"]) == compact_text(name)]
        if not starts:
            # 宽松：标题包含章名且足够短
            starts = [
                i
                for i, r in enumerate(rows)
                if r["level"] == 1 and name in r["text"] and len(compact_text(r["text"])) <= len(compact_text(name)) + 4
            ]
        if not starts:
            continue
        i0 = starts[0]
        i1 = len(rows)
        for k in h1_idx:
            if k > i0:
                i1 = k
                break
        chunk = rows[i0:i1]
        nodes: list[dict[str, Any]] = []
        counters = [chapter_no, 0, 0, 0, 0]
        src = doc.source_name or ""
        for r in chunk:
            depth = max(0, int(r["level"]) - 1)
            title = _apply_year(r["text"], year)
            if structural_only and depth > 0 and is_content_title(title):
                continue
            if depth == 0:
                num = str(chapter_no)
                counters = [chapter_no, 0, 0, 0, 0]
            else:
                if depth >= len(counters):
                    depth = len(counters) - 1
                counters[depth] += 1
                for k in range(depth + 1, len(counters)):
                    counters[k] = 0
                num = ".".join(str(counters[k]) for k in range(0, depth + 1))
            nodes.append(
                {
                    "num": num,
                    "title": title,
                    "bare": title,
                    "depth": depth,
                    "level": min(1 + depth, 4),
                    "source": src,
                }
            )
        # 至少要有章题+一个小节
        if len(nodes) >= 2 and (not best or len(nodes) > len(best)):
            best = nodes
    return best


TITLE_REWRITE = {
    "维保管理": "仪器仪表使用管理方面",
    "新线路接管": "部门年度培训方面",
    "新技术应用": "智能化应用",
    "设备体量": "设备体量变化情况",
}


def _renumber_outline(nodes: list[dict[str, Any]], chapter_id: str) -> list[dict[str, Any]]:
    chapter_no = int(chapter_id.replace("ch", "") or 3)
    counters = [chapter_no, 0, 0, 0, 0]
    out: list[dict[str, Any]] = []
    for node in nodes:
        item = dict(node)
        depth = max(0, int(item.get("depth") or 0))
        if depth >= len(counters):
            depth = len(counters) - 1
            item["depth"] = depth
        if depth == 0:
            counters = [chapter_no, 0, 0, 0, 0]
            num = str(chapter_no)
        else:
            counters[depth] += 1
            for k in range(depth + 1, len(counters)):
                counters[k] = 0
            num = ".".join(str(counters[k]) for k in range(0, depth + 1))
        item["num"] = num
        item["level"] = min(1 + depth, 4)
        out.append(item)
    return out


def apply_current_year_outline(
    outline: list[dict[str, Any]],
    chapter_id: str,
    *,
    year: int,
) -> list[dict[str, Any]]:
    """去年目录补上当年成品有、去年没有的节；旧题名改到当年用名。不编造正文。"""
    if not outline:
        return baseline_outline(chapter_id, year=year)
    rewritten: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for node in outline:
        item = dict(node)
        t = str(item.get("title") or "").strip()
        if t in TITLE_REWRITE:
            t = TITLE_REWRITE[t]
            item["title"] = t
            item["bare"] = t
        c = compact_text(t)
        if c and c in seen_titles and int(item.get("depth") or 0) > 0:
            continue
        if c:
            seen_titles.add(c)
        rewritten.append(item)
    have = {compact_text(str(n.get("title") or "")) for n in rewritten}
    extra: list[dict[str, Any]] = []
    for node in baseline_outline(chapter_id, year=year):
        t = str(node.get("title") or "")
        c = compact_text(t)
        if not c or c in have:
            continue
        if int(node.get("depth") or 0) <= 0:
            continue
        extra.append(dict(node))
        have.add(c)
    if not extra:
        return _renumber_outline(rewritten, chapter_id)
    # 插在评估小结之前，保持小结垫底
    out: list[dict[str, Any]] = []
    inserted = False
    for node in rewritten:
        title = str(node.get("title") or "")
        if not inserted and title == "评估小结":
            out.extend(extra)
            inserted = True
        out.append(node)
    if not inserted:
        out.extend(extra)
    return _renumber_outline(out, chapter_id)


def resolve_chapter_outline(
    prior_docs: list[DocumentModel] | None,
    chapter_id: str,
    *,
    year: int,
    prior_via: str = "",
) -> list[dict[str, Any]]:
    """有上传 prior 且能检出目录 → 用上传；否则用 2025 触网保底结构。"""
    via = prior_via or ""
    # 保底稿：直接用与 2025 触网一致的结构 JSON（与成文默认标题一字不差）
    if via.startswith("baseline") or not prior_docs:
        return baseline_outline(chapter_id, year=year)
    detected = outline_from_docs(prior_docs, chapter_id, year=year, structural_only=True)
    if detected and len(detected) >= 2:
        first = compact_text(detected[0].get("title") or "")
        expect = compact_text(CHAPTER_NAMES.get(chapter_id) or "")
        if expect and expect in first:
            return apply_current_year_outline(detected, chapter_id, year=year)
    return baseline_outline(chapter_id, year=year)


def insert_content_children(
    outline: list[dict[str, Any]],
    *,
    parent_title_key: str,
    children: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """在指定体例标题下插入材料带来的内容小节（线路/事件等）。"""
    if not children:
        return outline
    out: list[dict[str, Any]] = []
    inserted = False
    parent_depth = None
    parent_num = ""
    for node in outline:
        out.append(node)
        title = str(node.get("title") or "")
        if inserted:
            continue
        if parent_title_key in title and int(node.get("depth") or 0) > 0:
            parent_depth = int(node.get("depth") or 1)
            parent_num = str(node.get("num") or "")
            child_depth = parent_depth + 1
            pf = node.get("fill")
            if isinstance(pf, dict):
                marked = dict(pf)
                marked["_children_promoted"] = True
                node["fill"] = marked
                out[-1] = node
            for i, ch in enumerate(children, start=1):
                num = f"{parent_num}.{i}" if parent_num else str(i)
                out.append(
                    {
                        "num": num,
                        "title": ch.get("title") or "",
                        "bare": ch.get("title") or "",
                        "depth": child_depth,
                        "level": min(1 + child_depth, 4),
                        "source": ch.get("source") or "",
                        "fill": ch.get("fill"),
                        "empty": ch.get("empty", False),
                        "content_child": True,
                    }
                )
            inserted = True
    return out
