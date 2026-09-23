# -*- coding: utf-8 -*-
"""一章一套的约定。后续加章时按此声明 HANDLER，不要把规则写进接口层。

抽取口径、黄标规则、2025 目录填法都放在各章 extract/write/style 里；
本文件只规定 HANDLER 要带哪些字段，避免网页或 jobs 出现 if chapter_id。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from parsers.document_model import DocumentModel

ExtractFn = Callable[..., dict[str, Any]]
WriteFn = Callable[..., Path]
MessageFn = Callable[[dict[str, Any]], str]
ExtraFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ChapterHandler:
    """某个专业下的某一章：自己的建议材料、文风、抽取和成文。"""

    chapter_id: str
    domain_id: str
    no: int
    name: str
    domain_label: str
    cover_line: str
    upload_hint: str
    report_hint: str
    style_rules: str
    extract: ExtractFn
    write: WriteFn
    message_fn: MessageFn | None = None
    extra_result: ExtraFn | None = None
    # 可选：额外提示用的缺材料小节列表；成文/审阅以实际抽取结果为准，禁止政策写死永远黄。
    yellow_holes: tuple[str, ...] = field(default_factory=tuple)

    def job_title(self, year: int) -> str:
        """任务标题，如「2026年供电第3章设备功能有效性评估」。"""
        return f"{year}年{self.domain_label}第{self.no}章{self.name}"

    def message(self, pack: dict[str, Any]) -> str:
        """任务完成时的短句。有 message_fn 时带上「抽到了什么」（如总表体量、线路数）。"""
        if self.message_fn:
            return self.message_fn(pack)
        return f"第{self.no}章已按材料填入"

    def extract_pack(
        self,
        docs: list[DocumentModel],
        *,
        year: int,
        prior_docs: list[DocumentModel] | None = None,
    ) -> dict[str, Any]:
        """从已解析材料抽出本章 pack。认不出的键留空，由 write 黄标题，不在这里编造。

        prior_docs 是单独放入的去年完整报告，不与今年材料混抽总表/管控措施。
        不接收该参数的章抽取函数走 TypeError 回退。
        """
        try:
            return self.extract(docs, year=year, prior_docs=prior_docs or [])
        except TypeError:
            return self.extract(docs, year=year)

    def write_docx(self, pack: dict[str, Any], path: str | Path) -> Path:
        """按 2025 本章目录填空。出处只标标题后括号；缺材料黄标题。"""
        return self.write(pack, path)
