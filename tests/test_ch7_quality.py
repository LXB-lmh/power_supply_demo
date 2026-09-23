# -*- coding: utf-8 -*-
"""7.2：固定骨架 7.2.1～7.2.4；开篇今年→去年；表7-1 只认当年；仪表/培训/智能按线路。"""
import re

from chapters.power.extract import extract_ch7_quality
from chapters.power.write import write_chapter_docx
from parsers.document_model import Block, DocumentModel


def _doc(name: str, blocks: list[Block], path: str = "") -> DocumentModel:
    return DocumentModel(source_name=name, source_path=path or name, suffix=".docx", blocks=blocks)


def test_lead_falls_back_to_prior():
    year = _doc("本年.docx", [Block(type="paragraph", text="无关内容。")])
    prior = _doc(
        "去年年报.docx",
        [
            Block(type="heading", text="7.2  设施设备运维质量分析", level=2),
            Block(
                type="paragraph",
                text="从日常维修计划执行情况、维保管理、新线路接管、新技术应用、故障处理流程等几个方面进行设施设备运维质量的分析和评估。",
            ),
            Block(type="heading", text="7.2.1  日常维修计划执行情况", level=3),
            Block(type="paragraph", text="计划正文。"),
        ],
    )
    hit = extract_ch7_quality([year], [prior])
    lead = hit["lead"]
    assert lead["via"] == "prior"
    assert "几个方面" in "".join(lead["paras"])


def test_lead_ignores_line_report_noise():
    """单线稿里的运维段落不能冒充 7.2 开篇总述。"""
    line = _doc(
        "2026年评估报告（6号线变电专业）.docx",
        [
            Block(type="paragraph", text="设施设备运维质量分析"),
            Block(
                type="paragraph",
                text="6号线每月对35座变电站进行月度不停电柜面维护保养计划以及直流屏切换试验。",
            ),
            Block(type="paragraph", text="1、生产计划执行方面"),
            Block(type="paragraph", text="本线计划完成。"),
        ],
        path="材料/线路报告/6号线变电.docx",
    )
    hit = extract_ch7_quality([line], [])
    assert not (hit["lead"].get("paras") or [])


def test_plan_table_not_from_prior():
    """表7-1 禁止用去年顶数；无当年表则 table 空。"""
    year = _doc("本年.docx", [Block(type="paragraph", text="无计划表。")])
    prior = _doc(
        "去年.docx",
        [
            Block(type="paragraph", text="表7-1生产计划执行情况表"),
            Block(
                type="table",
                rows=[
                    ["序号", "线路", "计划数量（项）", "完成数量（项）", "完成率"],
                    ["1", "1号线", "86477", "86477", "100%"],
                ],
            ),
        ],
    )
    hit = extract_ch7_quality([year], [prior])
    assert hit["table"] == []
    assert hit["plan_table"]["table"] == []


def test_plan_aspect_does_not_swallow_line_prose():
    """7.2.1 不把各线「生产计划执行方面」散文堆进来。"""
    line = _doc(
        "1号线变电评估报告.docx",
        [
            Block(type="paragraph", text="1、生产计划执行方面"),
            Block(type="paragraph", text="本线计划4119项全部完成，不应进7.2.1总述。"),
            Block(type="paragraph", text="2、仪器仪表使用管理方面"),
            Block(type="paragraph", text="仪表送检合格。"),
        ],
        path="材料/线路报告/1号线变电评估报告.docx",
    )
    hit = extract_ch7_quality([line], [])
    assert "4119" not in "".join((hit["aspects"]["plan"].get("paras") or []))
    assert "仪表送检" in "".join(hit["aspects"]["meter"]["paras"])


def test_aspects_from_line_reports_by_line():
    """变电线报告四分法 → 7.2.2～7.2.4 按线路块。"""
    line = _doc(
        "1号线变电评估报告.docx",
        [
            Block(type="paragraph", text="1.生产计划执行方面"),
            Block(type="paragraph", text="本线计划全部完成。"),
            Block(type="paragraph", text="2.仪器仪表使用管理方面"),
            Block(type="paragraph", text="仪表送检合格率100%。"),
            Block(type="paragraph", text="3.部门年度培训方面"),
            Block(type="paragraph", text="完成安全培训两期。"),
            Block(type="paragraph", text="4.智能化应用"),
            Block(type="paragraph", text="上线巡检机器人。"),
            Block(type="paragraph", text="评估结论与建议"),
            Block(type="paragraph", text="结论不应进智能化。"),
        ],
        path="材料/线路报告/1号线变电评估报告.docx",
    )
    hit = extract_ch7_quality([line], [])
    aspects = hit["aspects"]
    meter_lines = aspects["meter"]["lines"]
    assert len(meter_lines) == 18
    assert meter_lines[0]["empty"] is False
    assert "仪表送检" in "".join(meter_lines[0]["paras"])
    assert meter_lines[1]["empty"] is True
    assert "安全培训" in "".join(aspects["train"]["lines"][0]["paras"])
    assert "巡检机器人" in "".join(aspects["smart"]["lines"][0]["paras"])
    assert "结论不应进" not in "".join(aspects["smart"]["paras"])
    assert aspects["meter"]["via"] == "year"


def test_line9_training_list_not_in_meter():
    """9号线 1）2）3）4）+ 课表「1、2025.5《培训》」：仪器节只有仪器句，课表进培训。"""
    line = _doc(
        "9号线线路变电评估报告.docx",
        [
            Block(type="paragraph", text="六、运维表现健康度评估"),
            Block(type="paragraph", text="1）全年累计制定供电设备检修计划共4855项，实际执行完成4855项。"),
            Block(
                type="paragraph",
                text="2）九号线的仪器、仪表没有缺少的情况，主要问题是使用时间很长，存在设备不灵敏以及故障频次较高的情况。",
            ),
            Block(type="paragraph", text="3）9号线培训，共进行了5次，每次101人次，共1212人次。"),
            Block(type="paragraph", text="1、2025.5《400V开关继电保护装置整定值查阅》培训"),
            Block(type="paragraph", text="2、2025.6《直流开关送电前检查》培训"),
            Block(type="paragraph", text="12、2026.4《正确使用各类表计（万用表、钳形电流表、兆欧表等）》培训"),
            Block(type="paragraph", text="已经基本满足了培训要求。"),
            Block(type="paragraph", text="4）智能化应用的使用情况："),
            Block(type="paragraph", text="1、视频查看所有的变电站可视系统；"),
            Block(type="paragraph", text="2、八大系统的所有通讯状态、数据分析进行查看；"),
        ],
        path="材料/线路报告/9号线线路变电评估报告.docx",
    )
    hit = extract_ch7_quality([line], [])
    meter_blob = "\n".join(hit["aspects"]["meter"]["lines"][8]["paras"])
    train_blob = "\n".join(hit["aspects"]["train"]["lines"][8]["paras"])
    smart_blob = "\n".join(hit["aspects"]["smart"]["lines"][8]["paras"])
    assert "仪器、仪表没有缺少" in meter_blob
    assert "2025.5" not in meter_blob
    assert "培训" not in meter_blob
    assert "1212人次" in train_blob
    assert "2025.5" in train_blob
    assert "万用表" in train_blob  # 课表行留在培训
    assert "已经基本满足了培训要求" in train_blob
    assert "视频查看" in smart_blob
    assert "八大系统" in smart_blob


def test_line6_circled_numbers_do_not_bleed_into_meter():
    """六号线①计划②仪器③培训④智能：仪器节不得吃进培训/智能正文。"""
    line = _doc(
        "6线路变电评估报告.docx",
        [
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="①、2026年度共计需完成生产计划任务项2931项，已完成1901项。"),
            Block(type="paragraph", text="②、现六号线班组管辖仪器仪表"),
            Block(type="paragraph", text="甲供，多用表三个，兆欧表两个，绝缘电阻测试仪四个。"),
            Block(type="paragraph", text="自购，多用表三个，钳形表两个。"),
            Block(
                type="paragraph",
                text="③六号线运修班组以每月3--4次对班组员工进行技术技能业务知识培训，全年完成三表培训。",
            ),
            Block(type="paragraph", text="各班组各类文件学习，均在文件下发后组织员工宣贯、学习。"),
            Block(
                type="paragraph",
                text="④设备房内加装了智能温湿度计，使得现在可以使用智能运维系统进行远程监控。",
            ),
        ],
        path="材料/线路报告/6线路变电评估报告.docx",
    )
    hit = extract_ch7_quality([line], [])
    meter_blob = "\n".join(hit["aspects"]["meter"]["lines"][5]["paras"])
    train_blob = "\n".join(hit["aspects"]["train"]["lines"][5]["paras"])
    smart_blob = "\n".join(hit["aspects"]["smart"]["lines"][5]["paras"])
    assert "多用表三个" in meter_blob
    assert "培训" not in meter_blob
    assert "智能温湿度计" not in meter_blob
    assert "三表培训" in train_blob
    assert "智能温湿度计" in smart_blob


def test_aspects_from_unstructured_line_blob():
    """无「2、仪器仪表」标题时，仍能从运维表现整段按内容拆到各块。"""
    line = _doc(
        "3号线变电评估报告.docx",
        [
            Block(type="paragraph", text="运维表现健康度评估"),
            Block(type="paragraph", text="3号线26年度生产计划总数4212项，截至4月30日，已完成1416项。"),
            Block(type="paragraph", text="3号线根据维护需求配置足额维护类工具、仪表，详情如下表所示。"),
            Block(type="paragraph", text="26年度开展人员培训包含岗位能力评估及考核共计83人次。"),
            Block(type="paragraph", text="随着大修改进程推进及智能运维建设，3号线全线实现远程故障录波功能。"),
            Block(type="paragraph", text="评估结论与建议"),
            Block(type="paragraph", text="结论。"),
        ],
        path="材料/线路报告/3号线变电评估报告.docx",
    )
    hit = extract_ch7_quality([line], [])
    assert "维护类工具" in "".join(hit["aspects"]["meter"]["lines"][2]["paras"])
    assert "83人次" in "".join(hit["aspects"]["train"]["lines"][2]["paras"])
    assert "故障录波" in "".join(hit["aspects"]["smart"]["lines"][2]["paras"])


def test_write_ch7_emits_line_headings(tmp_path):
    """成文写出 7.2.2.n 轨道交通N号线；空线黄标题。"""
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    lines = []
    for i in range(1, 19):
        empty = i != 1
        lines.append(
            {
                "line_no": i,
                "line": f"{i}号线",
                "title": f"轨道交通{i}号线",
                "paras": ["仪表合格。"] if not empty else [],
                "flow": [{"kind": "para", "text": "仪表合格。"}] if not empty else [],
                "source": "1号线.docx" if not empty else "",
                "empty": empty,
            }
        )
    pack = {
        "year": 2026,
        "ch7": {
            "source": "",
            "table": [["序号", "线路", "计划数量（项）", "完成率"], ["1", "1号线", "10", "100%"]],
            "flow": [{"kind": "table", "rows": [["序号", "线路", "计划数量（项）", "完成率"], ["1", "1号线", "10", "100%"]]}],
            "lead_paras": ["从日常维修计划执行情况等方面进行设施设备运维质量的分析和评估。"],
            "lead_flow": [
                {
                    "kind": "para",
                    "text": "从日常维修计划执行情况等方面进行设施设备运维质量的分析和评估。",
                }
            ],
            "lead_source": "去年.docx",
            "org_paras": ["组织模式一句。"],
            "org_flow": [{"kind": "para", "text": "组织模式一句。"}],
            "org_source": "本年.docx",
            "aspects": {
                "plan": {"paras": [], "flow": [], "source": "", "via": "", "lines": []},
                "meter": {"paras": ["仪表合格。"], "flow": [{"kind": "para", "text": "仪表合格。"}], "source": "1号线.docx", "via": "year", "lines": lines},
                "train": {"paras": [], "flow": [], "source": "", "via": "", "lines": [
                    {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
                    for i in range(1, 19)
                ]},
                "smart": {"paras": [], "flow": [], "source": "", "via": "", "lines": [
                    {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
                    for i in range(1, 19)
                ]},
            },
        },
    }
    out = tmp_path / "ch7.docx"
    write_chapter_docx(pack, out, "ch7")
    texts = [p.text.strip() for p in Document(str(out)).paragraphs if p.text.strip()]
    joined = "\n".join(texts)
    assert "7.2.2.1  轨道交通1号线" in joined
    assert "7.2.2.18  轨道交通18号线" in joined
    assert "仪表合格" in joined

    def _yellow(prefix: str) -> bool | None:
        for p in Document(str(out)).paragraphs:
            t = p.text.strip()
            if t.startswith(prefix):
                return any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)
        return None

    assert _yellow("7.2.2.1") is False
    assert _yellow("7.2.2.2") is True
    assert _yellow("7.2.3") is True  # 整节无料


def test_write_ch7_always_emits_72_skeleton(tmp_path):
    """骨架标题必现；无表则 7.2.1 黄；缺分项则对应标题黄。"""
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    empty_lines = [
        {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
        for i in range(1, 19)
    ]
    pack = {
        "year": 2026,
        "ch7": {
            "source": "",
            "table": [],
            "flow": [],
            "lead_paras": ["从日常维修计划执行情况等方面进行设施设备运维质量的分析和评估。"],
            "lead_flow": [
                {
                    "kind": "para",
                    "text": "从日常维修计划执行情况等方面进行设施设备运维质量的分析和评估。",
                }
            ],
            "lead_source": "去年.docx",
            "lead_via": "prior",
            "org_paras": ["组织模式一句。"],
            "org_flow": [{"kind": "para", "text": "组织模式一句。"}],
            "org_source": "本年.docx",
            "org_via": "year",
            "aspects": {
                "plan": {"paras": [], "flow": [], "source": "", "via": "", "lines": []},
                "meter": {"paras": [], "flow": [], "source": "", "via": "", "lines": empty_lines},
                "train": {"paras": [], "flow": [], "source": "", "via": "", "lines": empty_lines},
                "smart": {"paras": [], "flow": [], "source": "", "via": "", "lines": empty_lines},
            },
        },
    }
    out = tmp_path / "ch7.docx"
    write_chapter_docx(pack, out, "ch7")
    texts = [p.text.strip() for p in Document(str(out)).paragraphs]
    joined = "\n".join(texts)
    assert "7.2.1" in joined and "日常维修计划执行情况" in joined
    assert "7.2.2" in joined and "仪器仪表使用管理方面" in joined
    assert "7.2.3" in joined and "部门年度培训方面" in joined
    assert "7.2.4" in joined and "智能化应用" in joined

    def _yellow_for(prefix: str) -> bool | None:
        for p in Document(str(out)).paragraphs:
            t = p.text.strip()
            if t.startswith(prefix) and (prefix.count(".") >= 2 or re.match(rf"^{re.escape(prefix)}\s", t)):
                return any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)
        return None

    assert _yellow_for("7.2.1") is True
    assert _yellow_for("7.2.2") is True
    assert _yellow_for("7.2.3") is True
    assert _yellow_for("7.2.4") is True
    h72 = next(p for p in Document(str(out)).paragraphs if re.match(r"^7\.2\s", p.text.strip()))
    assert not any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in h72.runs)


def test_write_ch7_plan_yellow_even_with_prose_no_table(tmp_path):
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    meter_lines = [
        {
            "line_no": 1,
            "empty": False,
            "paras": ["仪表合格。"],
            "flow": [{"kind": "para", "text": "仪表合格。"}],
            "source": "1号线.docx",
            "title": "轨道交通1号线",
        }
    ] + [
        {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
        for i in range(2, 19)
    ]
    pack = {
        "year": 2026,
        "ch7": {
            "source": "",
            "table": [],
            "flow": [],
            "lead_paras": [],
            "lead_flow": [],
            "lead_source": "",
            "org_paras": ["组织。"],
            "org_flow": [{"kind": "para", "text": "组织。"}],
            "org_source": "a.docx",
            "aspects": {
                "plan": {
                    "paras": ["本线计划全部完成。"],
                    "flow": [{"kind": "para", "text": "本线计划全部完成。"}],
                    "source": "1号线.docx",
                    "via": "year",
                    "lines": [],
                },
                "meter": {
                    "paras": ["仪表合格。"],
                    "flow": [{"kind": "para", "text": "仪表合格。"}],
                    "source": "1号线.docx",
                    "via": "year",
                    "lines": meter_lines,
                },
                "train": {"paras": [], "flow": [], "source": "", "via": "", "lines": [
                    {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
                    for i in range(1, 19)
                ]},
                "smart": {"paras": [], "flow": [], "source": "", "via": "", "lines": [
                    {"line_no": i, "empty": True, "paras": [], "flow": [], "source": "", "title": f"轨道交通{i}号线"}
                    for i in range(1, 19)
                ]},
            },
        },
    }
    out = tmp_path / "ch7b.docx"
    write_chapter_docx(pack, out, "ch7")
    for p in Document(str(out)).paragraphs:
        t = p.text.strip()
        if t.startswith("7.2.1"):
            assert any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)
        if t.startswith("7.2.2") and "轨道交通" not in t:
            assert not any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)
        if t.startswith("7.2.3") and "轨道交通" not in t:
            assert any(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in p.runs)


def test_train_keeps_year_month_courses_and_not_smart_bleed():
    """课表 2024.7《…》不得被切片截断；智能「1、视频查看」不得串进培训。"""
    line = _doc(
        "2026年评估报告（12号线变电专业）.docx",
        [
            Block(type="paragraph", text="六、运维表现健康度评估"),
            Block(type="paragraph", text="2、仪器仪表：工具齐全。"),
            Block(type="paragraph", text="部门级培训共进行了11次，每次17人，共计187人次。"),
            Block(type="paragraph", text="2024.7《施工管理规定》主题培训"),
            Block(type="paragraph", text="2024.8《供电设备维护保养要求及标准培训》主题培训"),
            Block(type="paragraph", text="班组级月月练及培训每项各进行了12次，每次74人，共计1776人次。"),
            Block(type="paragraph", text="1、视频查看所有的变电站监控系统；"),
            Block(type="paragraph", text="3、直流屏、UPS、EPS电池电压，充电电流等数据严密观察，巡检都规定了具体的查看异常要求；"),
            Block(type="paragraph", text="评估结论"),
            Block(type="paragraph", text="结论句。"),
        ],
        path="材料/线路报告/12号线变电.docx",
    )
    hit = extract_ch7_quality([line], [])
    train = next(x for x in hit["aspects"]["train"]["lines"] if x["line_no"] == 12)
    smart = next(x for x in hit["aspects"]["smart"]["lines"] if x["line_no"] == 12)
    train_blob = "\n".join(train["paras"])
    smart_blob = "\n".join(smart["paras"])
    assert "2024.7《施工管理规定》主题培训" in train_blob
    assert "1776人次" in train_blob
    assert "直流屏" not in train_blob and "UPS" not in train_blob
    assert "视频查看" in smart_blob
    assert "直流屏" in smart_blob


def test_cross_line_by_leading_line_no_not_filename():
    """归线看段首号线，不看文件名落在哪份合订本（位置变更仍能找到）。"""
    # 故意：写在 5 号线文件名里，正文段首是 14 号线智能
    line = _doc(
        "2026年评估报告（5号线变电专业）.docx",
        [
            Block(type="paragraph", text="六、运维表现健康度评估"),
            Block(type="paragraph", text="本线仪表齐全。"),
            Block(
                type="paragraph",
                text="14号线已接入智能运维平台，故障录波功能运行平稳。",
            ),
        ],
        path="材料/00-线路报告/任意目录/5号线.docx",
    )
    # 节名变更：不叫运维表现，段首号线+分项词仍应收
    other = _doc(
        "2026年评估报告（8号线变电专业）.docx",
        [
            Block(type="paragraph", text="其它章节标题"),
            Block(
                type="paragraph",
                text="11号线智能采集装置运行正常，直流故障录波已上线。",
            ),
        ],
        path="材料/线路报告/8号线.docx",
    )
    hit = extract_ch7_quality([line, other], [])
    smart14 = next(x for x in hit["aspects"]["smart"]["lines"] if x["line_no"] == 14)
    smart11 = next(x for x in hit["aspects"]["smart"]["lines"] if x["line_no"] == 11)
    smart5 = next(x for x in hit["aspects"]["smart"]["lines"] if x["line_no"] == 5)
    assert "智能运维平台" in "\n".join(smart14["paras"])
    assert "智能采集" in "\n".join(smart11["paras"])
    assert all("14号线" not in p for p in (smart5.get("paras") or []))


def test_mixed_power_overhead_filename_accepted_and_train_table():
    """「变电专业、接触网专业」合订本应收；5)培训+人次课时表进 7.2.3。"""
    line = _doc(
        "01-2025年评估报告（16线路变电专业、接触网专业）.docx",
        [
            Block(type="paragraph", text="六、运维表现健康度评估"),
            Block(type="paragraph", text="1)16号线共执行生产计划xx项，完成率100%，无设备欠修；"),
            Block(
                type="paragraph",
                text="4)16号线工具仪表老化，应补充兆欧表、万用表、钳形表，清单如下：",
            ),
            Block(
                type="table",
                rows=[["序号", "设备名称", "配备标准"], ["1", "兆欧表", "2"]],
            ),
            Block(
                type="paragraph",
                text="5)根据培训大纲对人员进行培训要求，后续培训内容如下：",
            ),
            Block(
                type="table",
                rows=[["项目名称", "人次", "项目总课时"], ["质量安全", "100", "800"]],
            ),
            Block(
                type="paragraph",
                text="6)智能化应用的使用情况：16号线全线未接入智能运维系统。",
            ),
        ],
        path="材料/线路报告/16变电接触网.docx",
    )
    hit = extract_ch7_quality([line], [])
    train = next(x for x in hit["aspects"]["train"]["lines"] if x["line_no"] == 16)
    smart = next(x for x in hit["aspects"]["smart"]["lines"] if x["line_no"] == 16)
    meter = next(x for x in hit["aspects"]["meter"]["lines"] if x["line_no"] == 16)
    assert not train["empty"]
    assert any(x.get("kind") == "table" for x in train["flow"])
    assert "培训大纲" in "\n".join(train["paras"])
    assert "人次" in "".join("".join(map(str, r)) for x in train["flow"] if x.get("kind") == "table" for r in (x.get("rows") or []))
    assert "智能运维" in "\n".join(smart["paras"])
    assert any(x.get("kind") == "table" for x in meter["flow"])
