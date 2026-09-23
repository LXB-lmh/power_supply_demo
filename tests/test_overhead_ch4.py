# -*- coding: utf-8 -*-
from chapters.overhead.extract import extract_chapter
from chapters.overhead.line_topics import harvest_fault_trend_paras, harvest_kilometre_paras
from parsers.document_model import Block, DocumentModel


def _blob(fill: dict) -> str:
    return " ".join(fill.get("paras") or []) + " ".join(
        str(x.get("text") or "") for x in (fill.get("flow") or []) if x.get("kind") == "para"
    )


def test_ch4_volume_change_keeps_km_not_appendix():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="——新增了接触网专用车梯摆放标准（附录AO）；"),
            Block(
                type="paragraph",
                text="1、差异化管控：再者，增加户外段接触网设备巡视频次。",
            ),
            Block(
                type="paragraph",
                text="设备体量变化情况：18号线新增二期线路（长江南路站-康文路站）新增刚性接触网15.58条公里。",
            ),
            Block(
                type="paragraph",
                text="本年度运营契合满足度评估围绕设备体量变化、维护周期执行情况及故障趋势展开。设备体量方面，18号线二期新增刚性接触网15.58条公里。",
            ),
        ],
    )
    hit = harvest_kilometre_paras([doc], change_only=True)
    blob = " ".join(hit.get("paras") or [])
    assert "15.58" in blob
    assert "车梯" not in blob
    assert "差异化" not in blob
    assert "评估围绕" not in blob
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    change = _blob(by["设备体量变化情况"].get("fill") or {})
    assert "15.58" in change
    assert "车梯" not in change


def test_ch4_qty_newest_wins_per_line():
    old = DocumentModel(
        source_name="维护七部.docx",
        source_path="old.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="18号线柔性接触网21.46条公里、刚性接触网100.18条公里。"),
            Block(type="paragraph", text="3号线柔性接触网179.15条公里。"),
        ],
    )
    new = DocumentModel(
        source_name="维护七部9.2.docx",
        source_path="new.docx",
        suffix=".docx",
        blocks=[
            Block(type="paragraph", text="18号线柔性接触网21.46条公里、刚性接触网103.1条公里。"),
            Block(type="paragraph", text="3号线柔性接触网179.15条公里。"),
        ],
    )
    hit = harvest_kilometre_paras([old, new], change_only=False)
    blob = " ".join(hit.get("paras") or [])
    assert "103.1" in blob
    assert "100.18" not in blob
    assert blob.count("18号线") == 1


def test_ch4_fault_trend_keeps_typical_drops_summary():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="a.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通1号线", level=3),
            Block(
                type="paragraph",
                text="2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障。",
            ),
            Block(type="paragraph", text="典型故障：1号线新闸路上行车头处锚段关节位置存在拉弧。"),
            Block(type="paragraph", text="当年设备故障值21；前三年设备故障均值26 60 69"),
            Block(type="paragraph", text="设备故障趋势=-6.5%"),
            Block(type="heading", text="轨道交通8号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，8号线总计发生35起设备故障。",
            ),
            Block(
                type="paragraph",
                text="第三章：本年度运营契合满足度评估围绕设备体量变化、维护周期执行情况及故障趋势展开。如8号线供电故障率略有上升。",
            ),
        ],
    )
    harvest = harvest_fault_trend_paras([doc])
    blob = " ".join(harvest.get("paras") or [])
    assert "典型故障" in blob
    assert "评估围绕" not in blob
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line1 = _blob(by["轨道交通1号线"].get("fill") or {})
    line8 = _blob(by["轨道交通8号线"].get("fill") or {})
    assert "典型故障" in line1
    assert "136起" in line1
    assert "评估围绕" not in line8
    wear = _blob((by["接触网专业接触线磨耗预警值上报"].get("fill") or {}))
    assert "磨耗宽度" not in wear
    assert "2.1.6" not in wear


def test_ch4_trend_skips_status_and_controls():
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="b.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="轨道交通2号线", level=3),
            Block(type="paragraph", text="接触网状态：C状态区段为西西延伸（主要分在北翟路停车场）。"),
            Block(type="paragraph", text="大修需求：东延伸及西西延伸接触网已超12年大修年限，亟需申报大修。"),
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通2号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，2号线总计发生22起设备故障。",
            ),
            Block(type="paragraph", text="典型故障：2号线世纪大道下行进站列车有拉弧现象。"),
            Block(type="heading", text="轨道交通8号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，8号线总计发生35起设备故障。",
            ),
            Block(type="paragraph", text="大修更新改造：8号线二期刚性接触网已纳入2023年大修项目。"),
            Block(
                type="paragraph",
                text="第三章：本年度运营契合满足度评估围绕设备体量变化展开。如8号线供电故障率略有上升。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line2 = _blob(by["轨道交通2号线"].get("fill") or {})
    line8 = _blob(by["轨道交通8号线"].get("fill") or {})
    assert "22起" in line2
    assert "典型故障" in line2
    assert "接触网状态" not in line2
    assert "大修需求" not in line2
    assert "35起" in line8
    assert "大修更新改造" not in line8
    assert "评估围绕" not in line8


def test_ch4_line_walks_until_trend_formula():
    """期间汇总写在日期后面时，仍要收到典型故障和设备故障趋势。"""
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(
                type="paragraph",
                text="2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障，其中43起为供电设备故障。",
            ),
            Block(type="paragraph", text="典型故障："),
            Block(
                type="paragraph",
                text="1号线新闸路上行车头处锚段关节位置存在拉弧，当时TL17锚段已换线。",
            ),
            Block(type="paragraph", text="经过此次事件，吸取教训，大修换线如遇短锚段需测量导高。"),
            Block(type="paragraph", text="2022年7月~2023年6月年设备故障值为69起；"),
            Block(type="paragraph", text="2023年7月~2024年6月年设备故障值为60起；"),
            Block(type="paragraph", text="2024年7月~2025年6月年设备故障值为26起；"),
            Block(type="paragraph", text="2025年5月~2026年4月设备故障值为21起；"),
            Block(
                type="paragraph",
                text="设备故障趋势=[(当年设备故障值-前三年设备故障均值)/前三年设备故障均值*100%]",
            ),
            Block(type="paragraph", text="=[21-(26+60+69)/3]/(26+60+69)/3*100%"),
            Block(type="paragraph", text="=-6.5%"),
            Block(type="paragraph", text="1号线吊弦专项整治共需完成510套，截止2025年11月3日完成进度100%"),
            Block(type="paragraph", text="表B.47  运营契合满意度的评估评价标准"),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，5号线总计发生59起设备故障。",
            ),
            Block(type="paragraph", text="当年设备故障值2；前三年设备故障均值9  2  2"),
            Block(type="paragraph", text="故障设备趋势=-38.46%"),
        ],
    )
    harvest = harvest_fault_trend_paras([doc])
    hblob = " ".join(harvest.get("paras") or [])
    assert "新闸路" in hblob
    assert "设备故障值为69起" in hblob
    assert "-6.5%" in hblob
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line1 = _blob(by["轨道交通1号线"].get("fill") or {})
    line5 = _blob(by["轨道交通5号线"].get("fill") or {})
    assert "136起" in line1
    assert "新闸路" in line1
    assert "69起" in line1
    assert "设备故障趋势" in line1
    assert "-6.5%" in line1
    assert "吊弦专项整治" not in line1
    assert "59起" not in line1
    assert "59起" in line5
    assert "-38.46%" in line5
    assert "新闸路" not in line5


def test_ch4_trend_keeps_same_line_typical_without_hint():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="e.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通1号线", level=3),
            Block(
                type="paragraph",
                text="2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障。",
            ),
            Block(type="paragraph", text="典型故障："),
            Block(type="paragraph", text="1号线新闸路上行车头处锚段关节位置存在拉弧。"),
            Block(type="heading", text="轨道交通5号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，5号线总计发生59起设备故障。",
            ),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，7号线总计发生38起接触网设备故障。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line1 = _blob(by["轨道交通1号线"].get("fill") or {})
    line5 = _blob(by["轨道交通5号线"].get("fill") or {})
    line7 = _blob(by["轨道交通7号线"].get("fill") or {})
    assert "新闸路" in line1
    assert "38起" not in line5
    assert "59起" in line5
    assert "38起" in line7


def test_ch4_typical_after_label_without_hint_words():
    """「典型故障：」后的正文即使没有「典型故障」四字，也要留在该线。"""
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5b.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，7号线总计发生38起接触网设备故障。",
            ),
            Block(type="paragraph", text="典型故障："),
            Block(
                type="paragraph",
                text="7号线后滩混变直流屏故障维修施工结束后2111-2114触网闸刀遥控、就地电动均无法合闸。",
            ),
            Block(type="paragraph", text="2022年7月~2023年6月年设备故障值为42起；"),
            Block(
                type="paragraph",
                text="设备故障趋势=[(当年设备故障值-前三年设备故障均值)/前三年设备故障均值*100%]",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line7 = _blob(by["轨道交通7号线"].get("fill") or {})
    assert "38起" in line7
    assert "后滩" in line7
    assert "42起" in line7
    assert "设备故障趋势" in line7


def test_ch4_keeps_same_line_typical_and_major_bodies():
    """钉住线路后，典型/重大故障正文不靠拉弧、抢修令等词才收下。"""
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w78.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通7号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，7号线总计发生38起接触网设备故障。",
            ),
            Block(type="paragraph", text="典型故障："),
            Block(
                type="paragraph",
                text="7号线后滩混变直流屏故障维修施工结束后2111-2114触网闸刀遥控、就地电动均无法合闸。",
            ),
            Block(type="paragraph", text="经分析：该二极管故障系上级直流屏故障维修后，带隔离开关控制柜一同送点导致二极管击穿失效。"),
            Block(type="paragraph", text="后续整改措施：明确先切断断路器控制柜电源施工。"),
            Block(
                type="paragraph",
                text="设备故障趋势=[(当年设备故障值-前三年设备故障均值)/前三年设备故障均值*100%]",
            ),
            Block(type="paragraph", text="=-23.91%"),
            Block(type="paragraph", text="我部管辖的维护仪器、仪表等工具不存在缺、漏情况。"),
            Block(type="heading", text="轨道交通8号线", level=3),
            Block(
                type="paragraph",
                text="1、已纳入2024年上海市轨道交通8号线二期高架段及浦江停车场接触网设备大修更新改造项目，2025起至2027年完成。",
            ),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，8号线总计发生除35起设备故障，其中17起为供电设备故障，18起为其他专业故障。",
            ),
            Block(type="paragraph", text="典型故障："),
            Block(
                type="paragraph",
                text="8号线航头路接触网2131触网闸刀显示异常，传动机构无法有效显示。",
            ),
            Block(
                type="paragraph",
                text="重大设备故障：8号线联航路接触网设备断裂故障，由于联航路分段绝缘器断裂导致严桥路-沈杜公路上行失电。",
            ),
            Block(type="paragraph", text="整改措施"),
            Block(
                type="paragraph",
                text="计划11月26日夜间，优先将户外段西门子重型分段绝缘器平替更换。",
            ),
            Block(type="paragraph", text="当年设备故障值 35；前三年设备故障均值 11 6 16"),
            Block(type="paragraph", text="故障设备趋势=+127.27%"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line7 = _blob(by["轨道交通7号线"].get("fill") or {})
    line8 = _blob(by["轨道交通8号线"].get("fill") or {})
    assert "后滩" in line7
    assert "无法合闸" in line7
    assert "经分析" in line7
    assert "-23.91%" in line7
    assert "维护仪器" not in line7
    assert "航头路" not in line7
    assert "航头路" in line8
    assert "2131" in line8
    assert "联航路" in line8
    assert "平替更换" in line8
    assert "+127.27%" in line8
    assert "后滩" not in line8
    assert "大修更新" not in line8
    assert "维护仪器" not in line8


def test_ch4_stops_at_trend_drops_later_typical():
    """算出设备故障趋势后，不再挂突出事件里另一条「N号线典型故障」。"""
    doc = DocumentModel(
        source_name="维护六部.docx",
        source_path="w6extra.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，9号线总计发生39起设备故障，其中33起为供电设备故障。",
            ),
            Block(
                type="paragraph",
                text="典型故障：9号线三期东延伸隔离开关PLC故障导致,新华厂家PLC产品存在故障率较高的问题。",
            ),
            Block(type="paragraph", text="重大故障：无。"),
            Block(type="paragraph", text="当年设备故障值39； 前三年设备故障均值32 21 26"),
            Block(type="paragraph", text="故障设备趋势=+48.7%"),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，2号线总计发生80起设备故障。",
            ),
            Block(type="paragraph", text="典型故障：2号线世纪大道下行进站列车有拉弧现象。"),
            Block(type="paragraph", text="故障设备趋势=-6.5%"),
            Block(type="heading", text="设施设备年度突出事件分析", level=2),
            Block(
                type="paragraph",
                text="（2）9号线典型故障：2025年10月30日自检巡视发现9号线张泾桥牵引2116触网闸刀合闸未到位。",
            ),
            Block(
                type="paragraph",
                text="（1）2号线典型故障：2026年5月1日 2号线世纪大道下行进站列车有拉弧现象，发布0226#抢修令。",
            ),
            Block(
                type="paragraph",
                text="（4）6号线典型故障：6号线接触网送电过程中东靖路混变2114触网闸刀中央遥控、站控均无法合闸。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line9 = _blob(by["轨道交通9号线"].get("fill") or {})
    line2 = _blob(by["轨道交通2号线"].get("fill") or {})
    assert "三期东延伸" in line9
    assert "+48.7%" in line9 or "48.7%" in line9
    assert "张泾桥" not in line9
    assert "80起" in line2
    assert "世纪大道" in line2
    assert "0226" not in line2
    assert "东靖路" not in line2


def test_ch4_keeps_numbered_typical_list_until_trend():
    """「N号线典型故障：」后的1、2、3条都要收到趋势，不能只留带PLC的那条。"""
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7l14.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="paragraph", text="14号线典型故障："),
            Block(
                type="paragraph",
                text="1、14号线浦东南路站隔离开关PLC故障导致,台达厂家PLC产品存在故障率较高的问题。",
            ),
            Block(
                type="paragraph",
                text="2、2026年6月29日1:32，14号线中央PSCADA显示歇浦路混变2111-2114触网闸刀状态异常且显示就地。",
            ),
            Block(
                type="paragraph",
                text="3、14号线刚性隧道内汇流排腐蚀；2025年5月1日-2026年4月30日期间，14号线总计发生汇流排腐蚀区段共6处。",
            ),
            Block(type="paragraph", text="重大设备故障："),
            Block(type="paragraph", text="无"),
            Block(type="paragraph", text="当年设备故障值 15； 前三年设备故障均值 6 9 2"),
            Block(type="paragraph", text="故障设备趋势=+164.71%"),
            Block(
                type="paragraph",
                text="14号线浦东南路混变2111-2114触网闸刀中央无法遥控操作，发布抢修令。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line14 = _blob(by["轨道交通14号线"].get("fill") or {})
    assert "浦东南路站隔离开关PLC" in line14
    assert "PSCADA" in line14
    assert "汇流排腐蚀" in line14
    assert "重大设备故障" in line14
    assert "+164.71%" in line14
    assert "发布抢修令" not in line14


def test_ch4_keeps_source_order_typical_before_period():
    """材料先写典型故障再写期间汇总时，成文不要倒过来。"""
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="w5order.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="paragraph", text="5号线典型故障"),
            Block(
                type="paragraph",
                text="202511185号线莘庄车场触网闸刀控制屏柜PLC故障事件。发布0560#抢修令。",
            ),
            Block(type="paragraph", text="后续整改措施：推进PLC平替工作。"),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，5号线总计发生59起设备故障，其中56起为供电设备故障。",
            ),
            Block(type="paragraph", text="当年设备故障值2；前三年设备故障均值9  2  2"),
            Block(type="paragraph", text="故障设备趋势=-38.46%"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    paras = (by["轨道交通5号线"].get("fill") or {}).get("paras") or []
    blob = " ".join(paras)
    assert "莘庄" in blob and "59起" in blob and "-38.46%" in blob
    i_typ = next(i for i, p in enumerate(paras) if "莘庄" in p or "典型故障" in p)
    i_period = next(i for i, p in enumerate(paras) if "期间" in p and "59起" in p)
    i_trend = next(i for i, p in enumerate(paras) if "38.46%" in p or "故障设备趋势" in p)
    assert i_typ < i_period < i_trend


def test_ch4_trend_without_section_heading_does_not_mix_lines():
    doc = DocumentModel(
        source_name="维护五部.docx",
        source_path="e2.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="轨道交通5号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，5号线总计发生59起设备故障。",
            ),
            Block(type="paragraph", text="202511185号线莘庄车场触网闸刀控制屏柜PLC故障事件。"),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，7号线总计发生38起接触网设备故障。",
            ),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line5 = _blob(by["轨道交通5号线"].get("fill") or {})
    line7 = _blob(by["轨道交通7号线"].get("fill") or {})
    assert "59起" in line5
    assert "PLC" in line5
    assert "38起" not in line5
    assert "38起" in line7


def test_ch4_compare_current_year_only():
    now = DocumentModel(
        source_name="维护六部.docx",
        source_path="now.docx",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="2号线，2025年自检自修类故障次数16次，2026年总计发生22起设备故障。",
            ),
            Block(
                type="paragraph",
                text="6号线，2025年自检自修类故障次数17次，2026年总计发生18起设备故障。",
            ),
            Block(
                type="paragraph",
                text="16号线，2024年自检自修类故障16次；2025年总计发生19起设备故障。",
            ),
        ],
    )
    prior = DocumentModel(
        source_name="2025触网年报.doc",
        source_path="prior.doc",
        suffix=".docx",
        blocks=[
            Block(
                type="paragraph",
                text="1号线，2024年自检自修类故障次数13次，2025年总计发生141起设备故障。",
            ),
        ],
    )
    pack = extract_chapter(
        [now],
        year=2026,
        chapter_id="ch4",
        prior_docs=[prior],
        prior_via="upload",
    )
    by = {n["title"]: n for n in pack["outline"]}
    blob = _blob(by["和2025年评估对比结果"].get("fill") or {})
    assert "2026年总计发生22起" in blob
    assert "141起" not in blob
    assert "1号线" not in blob
    assert blob.count("2号线") == 1


def test_ch4_skips_power_fault_situation_file():
    power = DocumentModel(
        source_name="评估材料（故障情况，黄色待更新）.docx",
        source_path="fault.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各个线路基本情况（待表述格式调整）", level=2),
            Block(type="paragraph", text="1号线："),
            Block(
                type="paragraph",
                text="2026年共发生故障起，其中变压系统故障3项；降压系统故障58项；应急电源系统故障34项。",
            ),
            Block(type="paragraph", text="3号线："),
            Block(
                type="paragraph",
                text="3号线2025年5月1日至2026年4月30日期间发生典型故障2起，详情如下：",
            ),
            Block(
                type="paragraph",
                text="（2）26年1月8日，3号线石龙路停车场牵引站215直流开关跳闸，发布0323#抢修令。",
            ),
        ],
    )
    oh = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通1号线", level=3),
            Block(
                type="paragraph",
                text="2025年05月01日-2026年04月30日期间，1号线总计发生136起设备故障。",
            ),
            Block(type="paragraph", text="典型故障：1号线新闸路上行车头处锚段关节位置存在拉弧。"),
        ],
    )
    pack = extract_chapter([power, oh], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    parent = by["各线路接触网故障趋势分析"].get("fill") or {}
    line1 = _blob(by["轨道交通1号线"].get("fill") or {})
    assert "136起" in line1
    assert "新闸路" in line1
    assert "降压系统" not in line1
    assert "直流开关" not in line1
    assert "故障情况" not in (parent.get("source") or "")
    assert "故障情况" not in (by["轨道交通1号线"].get("fill") or {}).get("source", "")


def test_ch4_trend_drops_wear_and_power_switch():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7b.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(type="heading", text="轨道交通3号线", level=3),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年04月30日期间，3号线总计发生77起设备故障。",
            ),
            Block(
                type="paragraph",
                text="10）3号线一期存在2处大磨耗，已达预警值。接触线磨耗超限会导致拉弧，更换后可恢复导电性能。",
            ),
            Block(
                type="paragraph",
                text="（2）26年1月8日，3号线石龙路停车场牵引站215直流开关跳闸，发布0323#抢修令。",
            ),
            Block(type="paragraph", text="典型故障：石龙路停4道股道指示灯不亮。"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line3 = _blob(by["轨道交通3号线"].get("fill") or {})
    assert "77起" in line3
    assert "股道指示灯" in line3
    assert "大磨耗" not in line3
    assert "直流开关" not in line3


def test_ch4_keeps_countermeasure_and_major_none():
    doc = DocumentModel(
        source_name="维护七部.docx",
        source_path="w7c.docx",
        suffix=".docx",
        blocks=[
            Block(type="heading", text="各线路接触网故障趋势分析", level=2),
            Block(
                type="paragraph",
                text="2025年5月1日-2026年4月30日期间，3号线总计发生77起设备故障。",
            ),
            Block(type="paragraph", text="典型故障：石龙路停4道股道指示灯不亮。"),
            Block(type="paragraph", text="应对措施:结合集中修项目对股道灯的二次电缆进行集中整治更换。"),
            Block(type="paragraph", text="重大设备故障：无"),
            Block(type="paragraph", text="当年设备故障值 53； 前三年设备故障均值 12 11 8"),
            Block(type="paragraph", text="故障设备趋势= +412.90%"),
            Block(type="paragraph", text="典型故障："),
            Block(
                type="paragraph",
                text="18号线隔离开关PLC故障导致远方无法操作,新华厂家PLC产品存在故障率较高的问题。",
            ),
            Block(type="paragraph", text="故障设备趋势=-50%"),
        ],
    )
    pack = extract_chapter([doc], year=2026, chapter_id="ch4", prior_docs=[], prior_via="baseline_2025")
    by = {n["title"]: n for n in pack["outline"]}
    line3 = _blob(by["轨道交通3号线"].get("fill") or {})
    line18 = _blob(by["轨道交通18号线"].get("fill") or {})
    assert "应对措施" in line3
    assert "重大设备故障" in line3
    assert "+412.90%" in line3
    assert "隔离开关PLC" in line18
    assert "77起" not in line18
