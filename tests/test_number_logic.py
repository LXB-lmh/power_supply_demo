# -*- coding: utf-8 -*-
"""数字合计逻辑：故障总分项、A/B/C/D 台项、均值、趋势、年份。"""
from chapters.common.number_logic import (
    has_number_logic_issue,
    has_year_logic_issue,
    number_logic_notes,
    year_logic_notes,
)
from chapters.common.word import needs_mark, set_assessment_year
from chapters.power.review import review_chapter


def test_line6_fault_sum_mismatch():
    text = (
        "2025年至今共发生故障9起，其中降压系统故障6项；牵引系统故障1项；"
        "电力监控系统故障0项；应急电源系统故障0项。"
    )
    notes = number_logic_notes(text)
    assert notes
    assert "9" in notes[0] and "7" in notes[0]
    assert has_number_logic_issue(text)
    assert needs_mark(text)


def test_line16_includes_cable_xiang_no_false_alarm():
    """「电力电缆5项」不带「故障」二字也必须计入分项，不能误报逻辑不通。"""
    set_assessment_year(None)
    text = (
        "2025年6月至今共发生故障127起，其中降压系统故障41项；牵引系统故障31项；"
        "电力监控系统故障17项；电力电缆5项；应急电源系统故障29项；杂散电流系统故障4项。"
    )
    assert not number_logic_notes(text)
    assert not has_number_logic_issue(text)
    assert not needs_mark(text)


def test_fault_sum_ok_not_flagged():
    text = "2025年至今共发生故障7起，其中降压系统故障6项；牵引系统故障1项；电力监控系统故障0项；应急电源系统故障0项。"
    assert not number_logic_notes(text)


def test_two_year_parallel_data_not_cross_summed():
    """同一段并列两年数据：2025 年分项只与 2025 年总数核对，2026 年同理，不得跨年相加。"""
    text = (
        "1号线，2025年总计发生141起设备故障，其中43起供电设备故障，98起为其他专业故障，"
        "2026年总计发生136起设备故障，其中43起供电设备故障，93起为其他专业故障。"
    )
    assert not number_logic_notes(text)
    text2 = (
        "3号线，2025年总计发生258起设备故障，其中245起为供电设备故障，13起为其他专业故障，"
        "2026年总计发生77起设备故障，其中53起为供电设备故障，24起为其他专业故障。"
    )
    assert not number_logic_notes(text2)


def test_mixed_part_sentence_patterns_all_counted():
    """分项句式混合（N起为XX故障、XX故障N起、N起XX故障）时，所有分项都必须计入，不得漏项。"""
    text = (
        "7号线，2025年总计发生25起设备故障，其中8起为触网隔离开关故障、绝缘部件故障7起，"
        "其它故障10起，2026年总计发生38起接触网设备故障。"
    )
    assert not number_logic_notes(text)
    # 若分项真的对不上（10 改成 11），仍应报出
    bad = (
        "7号线，2025年总计发生25起设备故障，其中8起为触网隔离开关故障、绝缘部件故障7起，"
        "其它故障11起，2026年总计发生38起接触网设备故障。"
    )
    notes = number_logic_notes(bad)
    assert notes and "25" in notes[0] and "8+7+11" in notes[0]


def test_abcd_sum_mismatch():
    text = "供电完成300项，其中A类设备73项，B类设备165项，C类设备59项，D类设备3项。"
    assert not number_logic_notes(text)
    bad = "供电完成300项，其中A类设备73项，B类设备165项，C类设备59项，D类设备4项。"
    notes = number_logic_notes(bad)
    assert notes
    assert "300" in notes[0]


def test_mean_and_trend_mismatch():
    text = (
        "共发生设备故障64起，共发生设备故障56起，共发生设备故障72起，"
        "前三年设备故障均值为64.67起，因此26年度设备故障趋势为0%。"
    )
    notes = number_logic_notes(text)
    assert any("均值" in n for n in notes)
    assert any("0%" in n or "趋势" in n for n in notes)


def test_mean_integer_rounding_not_flagged():
    """报告均值按整数四舍五入（57.67写58、207.33写207）时不得报计算错误。"""
    text = (
        "25年5月1日至26年4月30日，共发生设备故障62起，24年5月1日至25年4月30日，共发生设备故障64起，"
        "23年5月1日至24年4月30日，共发生设备故障47起，前三年设备故障均值为58起。"
    )
    assert not number_logic_notes(text)
    text2 = (
        "25年5月1日至26年4月30日，共发生设备故障143起，24年5月1日至25年4月30日，共发生设备故障242起，"
        "23年5月1日至24年4月30日，共发生设备故障237起，前三年设备故障均值为207起。"
    )
    assert not number_logic_notes(text2)


def test_trend_zero_correct_not_flagged():
    """趋势0% 的公式是当年值=前三年均值（历史各年不必相等）。"""
    text = (
        "3号线25年5月1日至26年4月30日，共发生设备故障64起，24年5月1日至25年4月30日，共发生设备故障56起，"
        "23年5月1日至24年4月30日，共发生设备故障72起，前三年设备故障均值为64起，因此26年度设备故障趋势为0%。"
    )
    assert not number_logic_notes(text)


def test_year_switch_without_total_declaration_truncated():
    """14号线场景：2026年只有“当年设备故障值15起”（无总数声明词），15 不得混入 2025 分项。"""
    text = (
        "14号线，2025年总计发生41起设备故障，其中17起为供电设备故障，24起为其他专业故障，"
        "2026年当年设备故障值15起。"
    )
    assert not number_logic_notes(text)


def test_stat_period_range_year_not_truncating_parts():
    """统计区间“2025年5月-2026年4月”含两个年份，同属当前统计期，分项不得被年份截断。"""
    text = (
        "2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障，"
        "其中43起为供电设备故障，93起为其他专业故障。"
    )
    assert not number_logic_notes(text)


def test_year_as_of_before_assessment():
    set_assessment_year(2026)
    text = "截至2025年6月底数据，共有5个供电专业可靠性指标。"
    notes = year_logic_notes(text, 2026)
    assert notes
    assert has_year_logic_issue(text, 2026)
    assert needs_mark(text)


def test_ch4_review_flags_line6_logic():
    pack = {
        "chapter_id": "ch4",
        "year": 2026,
        "volume_text": "供电系统评估设备10台，其中A级2台、B级3台、C级4台、D级1台。",
        "fault_source": "故障.docx",
        "fault_by_line": {
            "6号线": [
                {
                    "kind": "text",
                    "text": "2025年至今共发生故障9起，其中降压系统故障6项；牵引系统故障1项；电力监控系统故障0项；应急电源系统故障0项。",
                }
            ]
        },
        "mtbf_paras": ["截至年底共有5个供电专业可靠性指标。"],
        "mtbf_flow": [{"kind": "para", "text": "截至年底共有5个供电专业可靠性指标。"}],
        "scope_paras": ["供电评估对象包括各类子系统。"],
    }
    rows = review_chapter(pack, "ch4")
    logic = [x for x in rows if x.get("issue") == "逻辑不通" and "6号线" in x.get("section", "")]
    assert logic, rows
    assert "9" in (logic[0].get("note") or "")
