# -*- coding: utf-8 -*-
"""供电 / 接触网材料隔离。分拣和成文都走这里，禁止互串。

只认文件名与正文/工作表，不认文件夹名。
混合工作簿：供电丢掉触网表，触网丢掉供电表。
"""
from __future__ import annotations

import re

from parsers.document_model import DocumentModel

OVERHEAD_MARKS = ("接触网", "触网", "接触轨")
OVERHEAD_SHEET_ALIASES = ("柔性锚段", "刚性锚段", "三轨区间", "隔离开关控制屏")
POWER_SHEET_MARKS = ("变电", "主变", "能源", "杂散电流", "应急电源", "电力监控", "供电专业")

# 整份 Word 的专业锚点（比零散词稳）
_OH_DOC_HINTS = (
    "接触网专业",
    "接触网分册",
    "各线路接触网故障趋势",
    "接触网故障趋势分析",
    "各线路柔性接触网状态",
    "各线路刚性接触网状态",
    "接触网设备状态分布",
)
_PW_DOC_HINTS = (
    "变电专业",
    "供电（含能源",
    "各线路供电系统年度生产指标",
    "降压系统故障",
    "应急电源系统故障",
    "变压系统故障",
)
_PW_BODY = ("变电所", "变电站", "杂散电流", "整流", "主变电", "降压设备", "降压系统", "应急电源")
_OH_BODY = ("接触网", "触网", "接触轨", "刚性接触网", "柔性接触网")


def _src_name(doc: DocumentModel) -> str:
    return (doc.source_name or "") + " " + (doc.source_path or "")


def has_extractable_body(doc: DocumentModel) -> bool:
    for block in doc.blocks or []:
        if block.type == "table" and block.rows:
            return True
        if block.type in {"drawing", "formula"}:
            return True
        if block.type in {"paragraph", "heading"}:
            text = (block.text or "").strip()
            if text and not text.startswith("工作表:"):
                return True
    return False


def sheet_is_overhead(title: str) -> bool:
    t = title or ""
    if any(k in t for k in OVERHEAD_MARKS):
        return True
    return any(k in t for k in OVERHEAD_SHEET_ALIASES)


def _plain_blob(doc: DocumentModel) -> str:
    return "\n".join((b.text or "") for b in (doc.blocks or []) if b.type != "table")


def is_power_fault_situation_doc(doc: DocumentModel) -> bool:
    """「评估材料（故障情况…）」是供电 4.3 各线变电故障，不是触网故障趋势。"""
    if "故障情况" not in _src_name(doc):
        return False
    blob = _plain_blob(doc)
    if "各线路接触网故障趋势" in blob or "接触网故障趋势分析" in blob:
        return False
    return any(k in blob for k in ("降压系统故障", "应急电源系统故障", "变压系统故障", "各个线路基本情况"))


def strip_overhead_sheets(doc: DocumentModel) -> DocumentModel:
    """供电抽取：同一本 Excel 里的接触网工作表拿掉。"""
    from chapters.overhead.excel_status import overhead_ledger_sheet_keys

    ledger = overhead_ledger_sheet_keys(doc)
    blocks: list = []
    skip = False
    for block in doc.blocks or []:
        if block.type == "heading" and (block.text or "").startswith("工作表:"):
            title = (block.text or "").split(":", 1)[-1]
            key = str(title or "").replace(" ", "").strip()
            skip = sheet_is_overhead(title) or (key in ledger)
            if skip:
                continue
        if skip:
            continue
        blocks.append(block)
    return DocumentModel(
        source_name=doc.source_name,
        source_path=doc.source_path,
        suffix=doc.suffix,
        blocks=blocks,
    )


def strip_power_sheets(doc: DocumentModel) -> DocumentModel:
    """触网抽取：同一本 Excel 里的变电/主变/能源工作表拿掉。"""
    blocks = []
    skip = False
    saw_sheet = False
    for block in doc.blocks or []:
        if block.type == "heading" and (block.text or "").startswith("工作表:"):
            saw_sheet = True
            title = (block.text or "").split(":", 1)[-1]
            if sheet_is_overhead(title):
                skip = False
                blocks.append(block)
                continue
            if any(k in title for k in POWER_SHEET_MARKS) and not any(k in title for k in OVERHEAD_MARKS):
                skip = True
                continue
            skip = False
            blocks.append(block)
            continue
        if skip:
            continue
        blocks.append(block)
    kept = DocumentModel(
        source_name=doc.source_name,
        source_path=doc.source_path,
        suffix=doc.suffix,
        blocks=blocks,
    )
    if saw_sheet and not has_extractable_body(kept):
        return doc
    return kept


def _has_workbook_sheets(doc: DocumentModel) -> bool:
    return any(
        b.type == "heading" and (b.text or "").startswith("工作表:")
        for b in (doc.blocks or [])
    )


def is_overhead_only_doc(doc: DocumentModel) -> bool:
    """去掉接触网工作表后没有正文，或整份是触网专稿。供电故障情况稿不算触网。"""
    if is_power_fault_situation_doc(doc):
        return False
    stripped = strip_overhead_sheets(doc)
    if not has_extractable_body(stripped) and has_extractable_body(doc):
        return True
    # 混合工作簿剥掉触网表后还有供电表，不能整份丢掉
    if _has_workbook_sheets(doc) and has_extractable_body(stripped):
        return False
    blob = _plain_blob(doc)
    if any(k in blob for k in _OH_DOC_HINTS) and not any(k in blob for k in _PW_DOC_HINTS):
        return True
    oh = sum(blob.count(k) for k in _OH_BODY)
    pw = sum(blob.count(k) for k in _PW_BODY)
    return oh > 0 and pw == 0


def is_compliance_pack(doc: DocumentModel) -> bool:
    """4&5 / 5&6 一类合规合订本：供电触网都用，按小节再切，不能整份丢掉。"""
    name = _src_name(doc)
    if "合规性材料" in name:
        return True
    if re.search(r"\d+\s*[&＆]\s*\d+\s*合规", name):
        return True
    if "修程修志" in name:
        return True
    return False


_OH_RETIRE_MARKS = ("隔离开关", "接触网", "触网", "接触轨", "接触线", "汇流排", "锚段")


def _has_overhead_plan_caption(doc: DocumentModel) -> bool:
    for block in doc.blocks or []:
        t = (block.text or "").strip()
        if t and "触网" in t and "生产计划" in t:
            return True
    return False


def is_shared_domain_pack(doc: DocumentModel) -> bool:
    """合订本/共用规定：供电触网都用，按小节或表行再切，不能整份丢掉。

    不含「故障情况」变电稿，也不含只有问答没有正文表的回复备忘。
    """
    if is_compliance_pack(doc):
        return True
    name = _src_name(doc)
    if "安全库存管理规定" in name:
        return True
    if "退运材料" in name or re.search(r"(?:^|[^0-9])11\s*退运", name):
        return True
    blob = _plain_blob(doc)
    if (
        "报废" in name
        and not any(k in name for k in ("工器具", "仪器仪表"))
        and any(k in blob for k in _OH_RETIRE_MARKS)
    ):
        return True
    if re.search(r"(?:评估报告材料|生产计划)", name) and _has_overhead_plan_caption(doc):
        return True
    return False


def is_power_only_doc(doc: DocumentModel) -> bool:
    """纯供电稿：触网抽取不看。文件名带接触网的不按这篇丢掉。"""
    if is_power_fault_situation_doc(doc):
        return True
    if is_shared_domain_pack(doc):
        return False
    name = _src_name(doc)
    if any(k in name for k in OVERHEAD_MARKS):
        return False
    stripped = strip_overhead_sheets(doc)
    if not has_extractable_body(stripped):
        return False
    blob = _plain_blob(doc)
    if any(k in blob for k in _PW_DOC_HINTS) and not any(k in blob for k in _OH_DOC_HINTS):
        return True
    oh = sum(blob.count(k) for k in _OH_BODY)
    pw = sum(blob.count(k) for k in _PW_BODY)
    if oh == 0 and pw > 0:
        return True
    if oh > 0 and pw >= oh * 3:
        return True
    return False


def prepare_power_docs(docs: list[DocumentModel] | None) -> list[DocumentModel]:
    """供电抽取入口：丢掉纯触网稿；混合工作簿只留非接触网表。"""
    out: list[DocumentModel] = []
    for doc in docs or []:
        if is_overhead_only_doc(doc):
            continue
        stripped = strip_overhead_sheets(doc)
        if has_extractable_body(stripped):
            out.append(stripped)
    return out


def prepare_overhead_docs(docs: list[DocumentModel] | None) -> list[DocumentModel]:
    """接触网抽取入口：丢掉纯供电稿（含故障情况变电稿）；混合工作簿只留触网表。"""
    out: list[DocumentModel] = []
    for doc in docs or []:
        if is_power_only_doc(doc):
            continue
        kept = strip_power_sheets(doc)
        if has_extractable_body(kept):
            out.append(kept)
    return out
