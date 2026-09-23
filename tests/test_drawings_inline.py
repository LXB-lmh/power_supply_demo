# -*- coding: utf-8 -*-
from pathlib import Path

from lxml import etree

from chapters.common.drawings import anchor_to_inline, copy_drawings_from_body_index
from chapters.common.word import new_report_document

WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
SRC_W6 = Path(
    r"F:\材料\供电材料2026\power_supply_demo\uploads\25b825cf396b"
    r"\评估材料\补充材料\（维护六部）线路评估（9.3改版).docx"
)


def test_anchor_to_inline_drops_wrap():
    xml = (
        f'<wp:anchor xmlns:wp="{WP}" xmlns:a="{A}">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:extent cx="100" cy="80"/>'
        "<wp:wrapTopAndBottom/>"
        '<wp:docPr id="1" name="pic"/>'
        "<a:graphic/>"
        "</wp:anchor>"
    )
    node = etree.fromstring(xml)
    out = anchor_to_inline(node)
    assert str(out.tag).endswith("}inline")
    locals_ = {str(c.tag).split("}")[-1] for c in out}
    assert "wrapTopAndBottom" not in locals_
    assert "extent" in locals_
    assert "graphic" in locals_


def test_inline_floating_drawings_nested_in_w_drawing():
    from chapters.common.drawings import inline_floating_drawings

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml = (
        f'<w:drawing xmlns:w="{W}" xmlns:wp="{WP}" xmlns:a="{A}">'
        f'<wp:anchor xmlns:wp="{WP}" xmlns:a="{A}">'
        '<wp:extent cx="100" cy="80"/>'
        "<wp:wrapTopAndBottom/>"
        '<wp:docPr id="1" name="pic"/>'
        "<a:graphic/>"
        "</wp:anchor>"
        "</w:drawing>"
    )
    root = etree.fromstring(xml)
    out = inline_floating_drawings(root)
    assert out.find(f".//{{{WP}}}anchor") is None
    assert out.find(f".//{{{WP}}}inline") is not None


def test_copy_xujing_figures_are_inline_not_wrap():
    if not SRC_W6.is_file():
        return
    dest = new_report_document()
    assert copy_drawings_from_body_index(SRC_W6, 200, dest) is True
    xml = dest.element.body.xml
    assert "wp:anchor" not in xml
    assert "wrapTopAndBottom" not in xml
    assert "wp:inline" in xml
    n_inline = xml.count("wp:inline")
    assert n_inline >= 2
