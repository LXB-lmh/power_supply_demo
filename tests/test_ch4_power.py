# -*- coding: utf-8 -*-
"""供电第四章抽取与成文口径：供电与接触网规则均就绪；材料缺字不补编；接触网第四章走触网体例成文。"""
from pathlib import Path

from catalog.taxonomy import chapter_ready, public_catalog
from chapters.ch4.power_extract import build_ch4_pack
from chapters.ch4.power_write import write_ch4_power_docx
from chapters.common.word import is_incomplete, is_punct_issue, needs_mark
from chapters.registry import get_handler
from parsers.dispatch import parse_files


def test_incomplete_detects_broken_material():
    assert is_incomplete("2026年共发生故障起，其中应急电源系统故障。")
    assert is_incomplete("对上一年度合规性评估建议的整改（待提供后完善）")
    assert is_incomplete("正线段杂散电流设备计划纳入大修更新改造项目（2")
    assert not is_incomplete("2026年共发生故障249起。")
    assert not is_incomplete("南延伸：")
    assert not is_incomplete("——更新了线路设备情况；")
    assert not is_incomplete("详情如下：")
    assert not is_incomplete("概述")
    assert not is_incomplete("应急电源故障主要集中在UPS配电柜触摸屏故障及蓄电池电池开关脱扣")
    assert is_punct_issue("应急电源故障主要集中在UPS配电柜触摸屏故障及蓄电池电池开关脱扣")  # 句子完整但缺句号，只算标点
    assert is_punct_issue("应急电源设备：1号线北延伸牵引变电站退出运营")  # 不能因「退出运营」免标点
    assert is_punct_issue("措施：已更换综保；。")
    assert is_punct_issue("使上海继北京、天津")
    assert needs_mark("应急电源故障主要集中在UPS配电柜触摸屏故障及蓄电池电池开关脱扣")
    assert not is_punct_issue("2026年共发生故障249起。")
    assert not is_punct_issue("南延伸：")


def test_chapter_ready_power_ch4_only():
    assert chapter_ready("power_supply", "ch4") is True
    assert chapter_ready("overhead", "ch4") is True
    assert chapter_ready("power_supply", "ch3") is True
    assert chapter_ready("overhead", "ch3") is True
    catalog = public_catalog()
    ch4 = next(c for c in catalog["chapters"] if c["id"] == "ch4")
    assert ch4["ready_in"] == ["power_supply", "overhead"]
    assert ch4["upload_hint_by_domain"]["power_supply"] == "设备评估结果总表，及其他相关评估材料。"
    handler = get_handler("power_supply", "ch4")
    assert handler is not None
    assert get_handler("overhead", "ch4") is not None  # 接触网第四章已接入，走触网体例成文
    assert get_handler("power_supply", "ch5") is not None
    assert get_handler("overhead", "ch5") is not None


def test_ch4_extract_from_user_materials(tmp_path):
    root = Path(r"F:\材料\2026供电评估_新\评估材料\99-26年评估报告编制材料")
    xlsx = root / "设备功能有效性" / "设备评估结果总表（4月）_1.xlsx"
    if not xlsx.exists():
        xlsx = root / "设备功能有效性" / "设备评估结果总表（4月）.xlsx"
    docx = root / "评估材料（故障情况，黄色待更新）.docx"
    if not xlsx.exists() or not docx.exists():
        return
    docs = parse_files([xlsx, docx])
    pack = build_ch4_pack(docs, year=2026)
    power = pack["grade_counts"].get("供电") or {}
    assert power.get("A", 0) + power.get("B", 0) + power.get("C", 0) + power.get("D", 0) == 343  # 总表供电台数口径
    assert "供电系统评估设备343台" in pack["volume_text"]
    assert pack["plan_text"] == ""  # 未上传生产计划就不编 4.4/4.5

    def texts(line):
        return [x["text"] for x in pack["fault_by_line"][line] if x.get("kind") == "text"]

    assert texts("1号线")
    assert texts("1号线")[0].startswith("2026年共发生故障起")  # 材料本身缺数字，不补编
    assert texts("7号线")[0].startswith("2026年共发生故障249起")
    assert texts("9号线")[1].startswith("9号线在2025年")
    assert all("运营延长" not in t for t in texts("18号线"))  # 非故障段落不进 4.3
    assert len(texts("18号线")) == 3
    assert any(x.get("kind") == "drawing" for x in pack["fault_by_line"]["6号线"])
    assert "设备评估结果总表" in pack["grade_source"]
    assert "故障情况" in pack["fault_source"]

    out = tmp_path / "ch4.docx"
    write_ch4_power_docx(pack, out)
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX
    gen = Document(str(out))
    titles = [p.text.strip() for p in gen.paragraphs if p.text.strip()]
    assert any(t.startswith("4.1.2") and "设备评估结果总表（4月）_1.xlsx" in t for t in titles)
    assert any(t.startswith("4.3") and "评估材料（故障情况，黄色待更新）.docx" in t for t in titles)
    assert not any("〔出处〕" in t or "【材料未提供】" in t for t in titles)
    assert not any("此外，根据生产计划工作表" in t for t in titles)
    assert is_incomplete(texts("1号线")[0])

    def yellow(p):
        return any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)

    paras = list(gen.paragraphs)
    first_l1 = None
    for i, p in enumerate(paras):
        if p.text.strip() == "1号线":
            assert yellow(p) is True
            first_l1 = paras[i + 1]
            break
    assert first_l1 is not None
    assert "共发生故障起" in first_l1.text
    assert yellow(first_l1) is True
    assert any("c:chart" in (p._element.xml or "") or "图表" in p.text for p in paras) or len(gen.inline_shapes) >= 1

