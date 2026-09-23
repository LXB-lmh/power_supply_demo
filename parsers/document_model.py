# -*- coding: utf-8 -*-
"""解析后的统一材料结构。后续抽取只认 Block，不再碰原 Word/Excel。

type：heading / paragraph / table / drawing / formula。
表格在 rows；图片/公式只记 source_index 占位，成文时回原文件拷贝。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


BlockType = Literal["heading", "paragraph", "table", "drawing", "formula"]


@dataclass
class Block:
    type: BlockType
    text: str = ""
    rows: list[list[str]] | None = None  # 仅 table：二维格子，已转成字符串
    level: int = 0  # 标题级别，1 最大
    source_index: int = -1  # 在原 Word body 里的序号，用来回找图/公式
    # 仅 table：材料里的竖合并 (列, 起行, 止行)，含表头行；成文按此还原，避免格式走样
    vmerge: list[tuple[int, int, int]] | None = None
    # 材料段落是否标黄（高亮或黄底纹）；成文同步标黄并加（原材料标黄）
    yellow: bool = False
    # 段落格式信号（仅 heading/paragraph）：样式名、最大字号(pt)、是否全加粗、是否居中。
    # 用于章标题识别（自动编号/正文样式章标题的兜底判定），不影响成文与表格。
    style_name: str = ""
    font_size: float = 0.0
    bold: bool = False
    centered: bool = False

    def to_text(self) -> str:
        if self.type == "table" and self.rows:
            lines = [" | ".join(cell.strip() for cell in row) for row in self.rows]
            return "\n".join(lines)
        return self.text.strip()


@dataclass
class DocumentModel:
    source_name: str
    source_path: str
    suffix: str
    blocks: list[Block] = field(default_factory=list)

    def to_text(self) -> str:
        """拼成纯文本，给分章预览或大模型兜底看表头/正文。"""
        parts: list[str] = [f"# 文件: {self.source_name}"]
        for block in self.blocks:
            chunk = block.to_text()
            if chunk:
                parts.append(chunk)
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_path": self.source_path,
            "suffix": self.suffix,
            "blocks": [asdict(b) for b in self.blocks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentModel":
        blocks = [Block(**b) for b in data.get("blocks", [])]
        return cls(
            source_name=data["source_name"],
            source_path=data["source_path"],
            suffix=data["suffix"],
            blocks=blocks,
        )
