# -*- coding: utf-8 -*-
"""第6章抽取规则：目录骨架固定；无标题靠表/小节名；不把部门年报第7～10章灌进 intro。"""
from chapters.power.extract import (
    _is_ch6_exit_title,
    _looks_like_ch6_count_table,
    _looks_like_ch6_revise_table,
    _should_parse_as_compliance,
    extract_compliance,
)
from chapters.common.section_slice import compact_text
from parsers.document_model import Block, DocumentModel


def _doc(name: str, blocks: list[Block]) -> DocumentModel:
    return DocumentModel(source_name=name, source_path=name, suffix=".docx", blocks=blocks)


def test_dept_eval_report_not_treated_as_compliance():
    """普通维护部评估报告即使正文有「管理体系合规性」也不整份当合规稿。"""
    doc = _doc(
        "维护一部评估报告.docx",
        [
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="导语一句。"),
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="第7章内容不应进第6章。"),
        ],
    )
    texts = [(b.type, b.text or "", b) for b in doc.blocks]
    assert not _should_parse_as_compliance(doc, texts)
    assert extract_compliance([doc])["ch6"]["intro"] == []


def test_compliance_filename_accepted():
    doc = _doc(
        "5&6合规性材料(2026).docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="对照去年体例写短导语。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="已完成整改一项。"),
        ],
    )
    texts = [(b.type, b.text or "", b) for b in doc.blocks]
    assert _should_parse_as_compliance(doc, texts)


def test_bare_yunwei_exits_ch6_zone():
    """材料无「7」编号时，裸「运维表现…」标题也要退出第6章。"""
    bare = "运维表现健康度评估"
    assert _is_ch6_exit_title(bare, compact_text(bare), bare)


def test_polluted_intro_loses_to_clean_compliance():
    """脏 intro（含第7章串台）即使更长，也不应压过合规性材料短导语。"""
    dirty = _doc(
        "某部评估报告_带合规.docx",
        [
            Block(type="paragraph", text="管理体系合规性评估"),
            Block(type="paragraph", text="法律法规的获取情况"),
            Block(type="paragraph", text="清单已建立。"),
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="脏导语第一句。"),
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="这是第7章长文，不应进 intro。"),
            Block(type="paragraph", text="备件物资保障能力评估"),
            Block(type="paragraph", text="这是第9章。"),
        ],
    )
    # 文件名含评估报告且无合规 → 整份跳过；改成合规文件名测择优
    dirty = _doc(
        "4&5合规性材料_脏.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="脏导语第一句。"),
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="这是第7章长文，不应进 intro。"),
            Block(type="paragraph", text="备件物资保障能力评估"),
            Block(type="paragraph", text="这是第9章。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="脏整改。"),
        ],
    )
    clean = _doc(
        "5&6合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="清洁短导语：本年按生产需要修订修程修制相关规程。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="清洁整改说明。"),
            Block(
                type="table",
                rows=[["名称", "编号"], ["规程A", "Q-1"]],
            ),
        ],
    )
    # 脏稿解析后 intro 不应含第7章；择优时清洁稿胜出
    from chapters.power.extract import _parse_one_compliance_doc

    ch6_dirty = _parse_one_compliance_doc(dirty)[1]
    assert "第7章" not in "".join(ch6_dirty.get("intro") or [])
    assert not any("运维表现" in t for t in (ch6_dirty.get("intro") or []))

    ch6 = extract_compliance([dirty, clean])["ch6"]
    assert "清洁短导语" in "".join(ch6.get("intro") or [])
    assert "第7章" not in "".join(ch6.get("intro") or [])
    assert "清洁整改说明" in "".join(ch6.get("revise") or [])


def test_untitled_tables_go_to_61_and_62():
    """无 6.x 标题：名称+编号表→6.1；规程等级多年份表→6.2。"""
    count_rows = [
        ["专业", "等级", "2017", "2018", "2024", "2025"],
        ["供电", "企业级", "1", "2", "3", "4"],
    ]
    revise_rows = [["名称", "编号"], ["作业指导书A", "ZY-1"]]
    assert _looks_like_ch6_count_table(count_rows)
    assert _looks_like_ch6_revise_table(revise_rows)

    doc = _doc(
        "5&6合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="短导语。"),
            Block(type="table", rows=revise_rows),
            Block(type="table", rows=count_rows),
        ],
    )
    ch6 = extract_compliance([doc])["ch6"]
    assert ch6["tables"] and ch6["tables"][0][1][0] == "作业指导书A"
    assert ch6["count_table"] and "等级" in "".join(ch6["count_table"][0])


def test_incomplete_only_from_selected_revise_source():
    """incomplete 只跟选中的 6.1 来源，不因另一份候选「待完善」整章黄。"""
    incomplete = _doc(
        "4&5合规性材料_待完善.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="导语A。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改（待完善）"),
            Block(type="paragraph", text="只有一句。"),
        ],
    )
    complete = _doc(
        "5&6合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="导语B。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="完整整改说明一。"),
            Block(type="paragraph", text="完整整改说明二。"),
            Block(type="table", rows=[["名称", "编号"], ["规程", "Q-9"]]),
        ],
    )
    ch6 = extract_compliance([incomplete, complete])["ch6"]
    assert ch6.get("incomplete") is False
    assert any("完整整改" in t for t in (ch6.get("revise") or []))


def test_ch6_intro_falls_back_to_prior_when_revise_source_has_none():
    """5&6 有 6.1 无章导语时，不借用 4&5 闲文，改用去年报告导语。"""
    year_revise = _doc(
        "5&6合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="已完成整改说明。"),
            Block(type="table", rows=[["名称", "编号"], ["规程", "Q-1"]]),
        ],
    )
    year_other = _doc(
        "4&5合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(
                type="paragraph",
                text="由于引入了比较新的维保技术，因此，在维保规程上也进行了更新和完善。",
            ),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="短整改。"),
        ],
    )
    prior = DocumentModel(
        source_name="去年供电年报.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="6  修程修制匹配性评估", level=1),
            Block(
                type="paragraph",
                text="根据生产需求及上级要求，将应急处置内容加入变电站运维细则，对多本维护保养、电气试验、继电保护试验作业的作业指导书进行归纳、整理、合并工作。",
            ),
            Block(type="heading", text="6.1  对上一年度合规性评估建议的整改", level=2),
            Block(type="paragraph", text="去年整改正文。"),
        ],
    )
    ch6 = extract_compliance([year_other, year_revise], prior_docs=[prior])["ch6"]
    blob = "".join(ch6.get("intro") or [])
    assert "根据生产需求及上级要求" in blob
    assert "维保技术" not in blob
    assert ch6.get("intro_via") == "prior"
    assert "去年供电年报" in (ch6.get("intro_source") or "")


def test_ch6_intro_keeps_year_when_same_source_has_it():
    doc = _doc(
        "5&6合规性材料.docx",
        [
            Block(type="paragraph", text="修程修制匹配性评估"),
            Block(type="paragraph", text="本年材料自带的修程修制章导语，说明规程已按生产需要修订。"),
            Block(type="paragraph", text="对上一年度合规性评估建议的整改"),
            Block(type="paragraph", text="整改说明。"),
        ],
    )
    prior = DocumentModel(
        source_name="去年.docx",
        source_path="prior.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="6  修程修制匹配性评估", level=1),
            Block(type="paragraph", text="根据生产需求及上级要求，去年导语不应覆盖今年。"),
            Block(type="heading", text="6.1  对上一年度合规性评估建议的整改", level=2),
        ],
    )
    ch6 = extract_compliance([doc], prior_docs=[prior])["ch6"]
    assert "本年材料自带" in "".join(ch6.get("intro") or [])
    assert ch6.get("intro_via") == "year"


def test_line_revise_bullets_not_eaten_by_global_dedupe():
    """真实 5&6 材料：4号线 9 条修订应全进；8/9 号线不能因与前线同句而空壳。"""
    from pathlib import Path

    from parsers.dispatch import parse_file

    src = Path(r"F:\材料\2026供电评估_新\评估材料\补充材料\5&6合规性材料(2026).docx")
    if not src.exists():
        return
    ch6 = extract_compliance([parse_file(src)])["ch6"]
    paras = [x.get("text") or "" for x in (ch6.get("revise_flow") or []) if x.get("kind") == "para"]

    def bullets_under(label: str) -> list[str]:
        armed = False
        out: list[str] = []
        for t in paras:
            if label in t:
                armed = True
                continue
            if not armed:
                continue
            if t.startswith("（") and "修订内容" in t:
                break
            if t.startswith("——") or t.startswith("—"):
                out.append(t)
        return out

    b4 = bullets_under("4号线变电站运行细则")
    assert len(b4) == 9
    assert any("巡视、维护及试验周期" in t for t in b4)
    assert any("不合理描述" in t for t in b4)
    assert len(bullets_under("8号线变电站运行细则")) >= 1
    assert len(bullets_under("9号线变电站运行细则")) >= 1
    from chapters.common.word import needs_mark

    assert not needs_mark("——修订了钢轨电位限制装置一阶段、二阶段动作电压数值")
