# -*- coding: utf-8 -*-
"""各章共用：按去年目录体例切材料，避免上一节吞进下一节。

材料里小节标题常是 paragraph 而非 Word heading；节号停词必须边界匹配
（「4.2」不得命中「4.4.2」）；短关键词只在标题级短行上认，避免正文误截。
"""
from __future__ import annotations

import re
from typing import Any, Callable

from parsers.document_model import DocumentModel

_CHAPTER_TITLE = re.compile(r"^第[0-9一二三四五六七八九十百]+章")
_OUTLINE_NUM = re.compile(r"^(\d+(?:[\.．]\d+)*)")
_OUTLINE_TITLE = re.compile(r"^\d+(?:[\.．]\d+)+\S")


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip())


def outline_num(compact: str) -> str | None:
    """行首节号，如 4.1.2 / 12.1。"""
    m = _OUTLINE_NUM.match(compact or "")
    if not m:
        return None
    return m.group(1).replace("．", ".")


def key_is_section_num(key: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)+", (key or "").replace("．", ".")))


def is_outline_title_line(compact: str) -> bool:
    """短行且以 x.y 编号开头 → 目录标题（含材料伪标题段落）。

    注意：2024.7《主题培训》是年月课表，不是 4.2 这类目录节号。
    """
    if not compact or len(compact) > 64:
        return False
    if compact[-1:] in "。！？；":
        return False
    # 20xx.m / 20xx.m.d 开头的培训课表、日志条目
    if re.match(r"^20\d{2}[\.．]\d{1,2}(?:[\.．]\d{1,2})?(?:《|主题培训|培训)", compact):
        return False
    if re.match(r"^20\d{2}[\.．]\d{1,2}", compact) and any(
        k in compact for k in ("培训", "《", "主题")
    ):
        return False
    return bool(_OUTLINE_TITLE.match(compact))


def is_chapter_or_appendix_title(compact: str) -> bool:
    if not compact or len(compact) > 48:
        return False
    if _CHAPTER_TITLE.match(compact):
        return True
    return compact.startswith("附录")


def hits_section_key(compact: str, keys: tuple[str, ...], *, title_only_words: bool = False) -> bool:
    """停/起关键词：节号边界匹配；章名/普通词默认短行或行首才认（防正文误伤）。"""
    if not compact or not keys:
        return False
    num = outline_num(compact)
    for k in keys:
        kk = (k or "").replace("．", ".").strip()
        if not kk:
            continue
        if key_is_section_num(kk):
            if num == kk or (num and num.startswith(kk + ".")):
                return True
            continue
        if kk not in compact:
            continue
        # 章名「第N章」
        if kk.startswith("第") and "章" in kk:
            if len(compact) < 48:
                return True
            continue
        if title_only_words or len(kk) <= 4:
            # 短词（备件/退运等）只在标题级短行或行首认
            if len(compact) < 48 or compact.startswith(kk) or is_outline_title_line(compact):
                return True
            continue
        if len(compact) < 64 or compact.startswith(kk) or is_outline_title_line(compact):
            return True
    return False


def is_foreign_outline(
    compact: str,
    *,
    keep_keys: tuple[str, ...] = (),
) -> bool:
    """其它编号节 / 章标题 / 附录 → 应停止当前切片。"""
    if is_chapter_or_appendix_title(compact):
        return True
    if not is_outline_title_line(compact):
        return False
    if hits_section_key(compact, keep_keys):
        return False
    return True


def filter_body_paras(
    texts: list[str] | None,
    *,
    keep_keys: tuple[str, ...] = (),
    reject_prefixes: tuple[str, ...] = (),
) -> list[str]:
    """成文前丢掉误吸的其它节标题行。"""
    out: list[str] = []
    for raw in texts or []:
        t = str(raw or "").strip()
        if not t:
            continue
        compact = compact_text(t)
        if reject_prefixes and any(compact.startswith(p) for p in reject_prefixes):
            continue
        if is_foreign_outline(compact, keep_keys=keep_keys):
            continue
        out.append(t)
    return out


def filter_flow_items(
    flow: list[dict[str, Any]] | None,
    *,
    keep_keys: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """flow 里丢掉误吸的大纲标题段落；表/图/公式保留。"""
    out: list[dict[str, Any]] = []
    for item in flow or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind in {"table", "drawing", "formula"}:
            out.append(item)
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        if is_foreign_outline(compact_text(text), keep_keys=keep_keys):
            continue
        out.append(item)
    return out


def flow_item_signature(item: dict[str, Any] | None) -> tuple:
    """用于跨文档/整段叠写去重的稳定指纹。"""
    item = item or {}
    kind = str(item.get("kind") or "para")
    if kind in {"text", "para"}:
        return ("p", compact_text(str(item.get("text") or "")))
    if kind == "drawing":
        return ("d", str(item.get("source_path") or ""), int(item.get("source_index") or -1))
    if kind == "formula":
        return ("f", str(item.get("source_path") or ""), int(item.get("source_index") or -1), compact_text(str(item.get("text") or "")))
    if kind == "table":
        rows = item.get("rows") or []
        head = tuple(str(c) for c in (rows[0] if rows else []))
        body = tuple(tuple(str(c) for c in (r or [])[:6]) for r in rows[1:4])
        return ("t", head, body)
    return (kind, compact_text(str(item.get("text") or "")), str(item)[:120])


def is_dash_list_item(text: str | None) -> bool:
    """「——修订了…」类清单条目：各线路常写相同句，不能按全文指纹删。"""
    t = (text or "").strip()
    return t.startswith("——") or t.startswith("—") or t.startswith("--")


def dedupe_flow_items(flow: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """去掉整段叠写：先折叠「前半=后半」，再按指纹保序去重。

    各章多份材料/同文件双份粘贴都会叠出 5.5/5.6 两遍；成文与抽取都应走这里。
    破折号清单条目允许跨小节重复（只压连续双写），避免 6.1 各号线修订条目被误删。
    """
    items = [x for x in (flow or []) if isinstance(x, dict)]
    if not items:
        return []
    sigs = [flow_item_signature(x) for x in items]
    n = len(sigs)
    # 整段复制两遍（含图/表交错）
    if n >= 4 and n % 2 == 0 and sigs[: n // 2] == sigs[n // 2 :]:
        items = items[: n // 2]
        sigs = sigs[: n // 2]
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for item, sig in zip(items, sigs):
        if not sig[-1] and sig[0] == "p":
            continue
        if sig in seen:
            # 清单条目：各线可共用同一句，只丢掉「紧挨着又写一遍」
            if sig[0] == "p" and is_dash_list_item(str(item.get("text") or "")):
                if out and flow_item_signature(out[-1]) == sig:
                    continue
                out.append(item)
                continue
            continue
        seen.add(sig)
        out.append(item)
    return out


def dedupe_texts(texts: list[str] | None) -> list[str]:
    """段落列表去重（折叠整段双份 + 指纹去重；破折号清单可跨段重复）。"""
    items = [{"kind": "para", "text": str(t)} for t in (texts or []) if str(t).strip()]
    return [str(x.get("text") or "") for x in dedupe_flow_items(items)]


FlowBuilder = Callable[[DocumentModel, Any], dict[str, Any] | None]


def slice_named_section(
    docs: list[DocumentModel] | None,
    *,
    start_keys: tuple[str, ...],
    stop_keys: tuple[str, ...] = (),
    after_keys: tuple[str, ...] = (),
    skip_doc: Callable[[DocumentModel], bool] | None = None,
    build_item: FlowBuilder | None = None,
    source_name: Callable[[DocumentModel], str] | None = None,
) -> dict[str, Any]:
    """按小节名切一段。paragraph 伪标题同样停；节号边界匹配。

    build_item：可选，把 block 建成 flow 项（含图/表/公式）；默认只收段落与表。
    """
    empty: dict[str, Any] = {"paras": [], "flow": [], "source": ""}

    def _src(doc: DocumentModel) -> str:
        if source_name:
            return source_name(doc)
        return doc.source_name or ""

    for doc in docs or []:
        if skip_doc and skip_doc(doc):
            continue
        armed = not after_keys
        take = False
        flow: list[dict[str, Any]] = []
        for block in doc.blocks or []:
            t = (block.text or "").strip()
            compact = compact_text(t)
            if not armed:
                if compact and hits_section_key(compact, after_keys, title_only_words=False):
                    armed = True
                continue
            if not take:
                if hits_section_key(compact, start_keys, title_only_words=False):
                    take = True
                continue
            if block.type in {"heading", "paragraph"} and compact:
                if stop_keys and hits_section_key(compact, stop_keys, title_only_words=True):
                    break
                # 再次碰到本节标题才停；正文里偶含 start 词不要截断
                if hits_section_key(compact, start_keys) and (
                    is_outline_title_line(compact)
                    or (len(compact) < 28 and compact[-1:] not in "。！？；")
                ):
                    break
                if is_foreign_outline(compact, keep_keys=start_keys):
                    break
            if build_item:
                item = build_item(doc, block)
                if item:
                    flow.append(item)
                continue
            if block.type == "drawing":
                from chapters.common.drawings import drawing_flow_item

                flow.append(drawing_flow_item(doc, block))
                continue
            if block.type == "table" and block.rows:
                from chapters.common.table_copy import table_flow_item

                flow.append(table_flow_item(doc, block))
                continue
            if t:
                from chapters.common.source_yellow import para_flow_item

                flow.append(para_flow_item(t, block))
        paras = [
            str(x.get("text") or "").strip()
            for x in flow
            if x.get("kind") == "para" and str(x.get("text") or "").strip()
        ]
        if paras or any(x.get("kind") in {"table", "drawing", "formula"} for x in flow):
            return {"paras": paras, "flow": flow, "source": _src(doc)}
    return empty
