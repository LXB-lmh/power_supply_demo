# -*- coding: utf-8 -*-
from chapters.overhead.line_notes import (
    build_notes_flow_after_table,
    explode_inline_line_leads,
    paragraphs_to_line_notes,
    row_all_zero_or_empty,
    slice_note_for_kind,
)


def test_multipara_after_line_header():
    paras = ["其中：", "2号线：", "C 类区段在某某站。", "另有整改计划一项。"]
    by_line, general = paragraphs_to_line_notes(paras)
    assert not general
    assert "2" in by_line
    assert "C 类区段" in by_line["2"]
    assert "整改计划" in by_line["2"]


def test_skip_note_when_row_all_zero():
    rows = [
        ["线路", "锚段数量", "A", "B"],
        ["线路", "锚段数", "占比", "占比"],
        ["4号线", "0", "0", "0%"],
        ["3号线", "10", "1", "10%"],
    ]
    assert row_all_zero_or_empty(rows[2])
    flow, _ = build_notes_flow_after_table(
        rows,
        {"3": "3号线：有 C 类设备。"},
        ["其中："],
    )
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    assert any("3号线" in t for t in texts)
    assert not any(t.startswith("4号线") for t in texts)


def test_newest_empty_line_note_keeps_older_body():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, src = merge_line_notes_with_sources(
        [
            {
                "notes": ["1号线：", "旧材料中的完整说明。"],
                "_recency": 1.0,
                "_idx": 0,
                "_source": "旧.docx",
            },
            {
                "notes": ["1号线："],
                "_recency": 2.0,
                "_idx": 1,
                "_source": "新.docx",
            },
        ]
    )
    assert "完整说明" in by.get("1", "")
    assert src.get("1") == "旧.docx"


def test_explode_inline_and_xianlu_alias():
    bits = explode_inline_line_leads(["4号线：没有C和D状态的区段。8号线C状态的区段是芦恒路。"])
    assert any(x.startswith("4号线") for x in bits)
    assert any("8号线" in x for x in bits)
    by, _ = paragraphs_to_line_notes(["8线路没有C和D状态的区段，维持现有管控措施。"])
    assert "8" in by
    assert "没有C和D" in by["8"]


def test_explode_keeps_same_line_continuation():
    bits = explode_inline_line_leads(
        ["接触网状态：1号线北延伸柔性接触网于2023年完成接触网大修，当前接触网锚段状态为A；1号线南延伸正处于大修期间，当前主要锚段状态为B。"]
    )
    assert len(bits) == 1
    assert "南延伸正处于大修" in bits[0]


def test_slice_flex_vs_rigid_from_combined_note():
    text = (
        "10号线接触网状态\n"
        "刚性接触网：C状态区段为10号线一期（海伦路）。\n"
        "柔性接触网：C状态区段为10号线一期（吴中路停车场）。\n"
        "隔离开关：一期隔离开关设备老化。\n"
        "管控策略包括：\n"
        "1、集中修项目：对10号线一期吴中车场开展集中修，需对530个柔性定位点集中修。"
    )
    flex = slice_note_for_kind(text, "各线路柔性接触网状态分布")
    rigid = slice_note_for_kind(text, "各线路刚性接触网状态分布")
    sw = slice_note_for_kind(text, "各线路隔离开关状态分布")
    assert "吴中路停车场" in flex
    assert "530个柔性定位点" not in flex
    assert "集中修项目" not in flex
    assert "海伦路" not in flex
    assert "海伦路" in rigid
    assert "吴中路停车场" not in rigid
    assert "隔离开关设备老化" in sw
    assert "吴中路停车场" not in sw
    assert "集中修项目" not in sw


def test_slice_strips_trailing_ctrl_lead_and_following_progress():
    rigid11 = slice_note_for_kind(
        "11号线C状态的刚性主要集中在二期与迪士尼段（江苏路-罗山路），管控策略包括：\n"
        "隧道段共13118处定位，目前完成10417处。",
        "各线路刚性接触网状态分布",
    )
    assert "江苏路-罗山路" in rigid11
    assert "管控策略包括" not in rigid11
    assert "13118" not in rigid11
    rigid7 = slice_note_for_kind(
        "7号线：2023年对7号线隧道段实施大修；已纳入2023年地下段接触网设备更新改造项目。\n"
        "现7号线没有C和D状态的区段，维持现有管控措施。",
        "各线路刚性接触网状态分布",
    )
    assert "没有C和D" in rigid7
    assert "实施大修" not in rigid7


def test_untyped_flex_note_keeps_overhaul_need():
    text = (
        "2号线：接触网状态：C状态区段为西西延伸（主要分在北翟路停车场）。\n"
        "当前状态：一期及西延伸经大修后状态良好。\n"
        "大修需求：东延伸及西西延伸接触网已超12年大修年限，亟需申报大修。\n"
        "集中修项目：对2号线东延伸户外高架段开展集中修作业。"
    )
    flex = slice_note_for_kind(text, "各线路柔性接触网状态分布")
    assert "北翟路停车场" in flex
    assert "大修需求" not in flex
    assert "集中修项目" not in flex


def test_slice_line_lead_flex_vs_rigid_rest():
    text = (
        "11号线C、D状态的柔性主要集中在一期（嘉定北-桃浦洞口）。\n"
        "集中修检验检测：共3136处定位点。\n"
        "11号线C状态的刚性主要集中在二期与迪士尼段（江苏路-罗山路）。\n"
        "集中修检验检测：11号线隧道段共13118处定位。\n"
        "11号线C状态的隔离开关主要集中在一期柔性（嘉定北-桃浦新村）。"
    )
    flex = slice_note_for_kind(text, "各线路柔性接触网状态分布")
    rigid = slice_note_for_kind(text, "各线路刚性接触网状态分布")
    sw = slice_note_for_kind(text, "各线路隔离开关状态分布")
    assert "嘉定北-桃浦洞口" in flex
    assert "3136处定位点" not in flex
    assert "江苏路-罗山路" not in flex
    assert "13118处定位" not in flex
    assert "江苏路-罗山路" in rigid
    assert "13118处定位" not in rigid
    assert "桃浦洞口" not in rigid
    assert "桃浦新村" in sw
    assert "江苏路-罗山路" not in sw


def test_slice_does_not_treat_switch_body_as_kind_header():
    text = (
        "11号线C、D状态的柔性主要集中在一期（嘉定北-桃浦洞口）。\n"
        "专项更换：\n"
        "川杨河基地隔离开关刀头更换总共需完成18套。\n"
        "差异化管控：\n"
        "加强巡视：接触线加强巡视，150mm²接触线剩余高度11.8一10.8mm时每六个月跟踪一次。\n"
        "11号线C状态的刚性主要集中在二期与迪士尼段（江苏路-罗山路）。\n"
        "集中修检验检测：11号线隧道段共13118处定位。\n"
        "差异化管控：\n"
        "加强巡视：接触线加强巡视，刚性接触网150mm²接触线剩余宽度到达12.3mm。"
    )
    flex = slice_note_for_kind(text, "各线路柔性接触网状态分布")
    rigid = slice_note_for_kind(text, "各线路刚性接触网状态分布")
    assert "嘉定北-桃浦洞口" in flex
    assert "11.8" not in flex
    assert "12.3mm" not in flex
    assert "13118" not in flex
    assert "江苏路-罗山路" in rigid
    assert "12.3mm" not in rigid
    assert "13118" not in rigid
    assert "11.8" not in rigid


def test_newer_status_keeps_older_ctrl_suffix():
    from chapters.overhead.material_merge import merge_line_notes_backfill

    items = [
        {
            "notes": [
                "13号线C状态的区段13号线一期西段；13号线没有D状态的区段；未纳入大修改造。差异化管控是，接触线加强巡视，10mm、接触线剩余高度达到10.5mm。"
            ],
            "_recency": 1,
            "_idx": 0,
            "_source": "七部旧.docx",
        },
        {
            "notes": [
                "13号线C状态的区段是：13号线一期西段含金运路上下行；13号线二期西段含长寿路上下行。13号线没有D状态的区段。"
            ],
            "_recency": 2,
            "_idx": 1,
            "_source": "七部新.docx",
        },
    ]
    by_line, _, _, _ = merge_line_notes_backfill(items, parse_paragraphs=paragraphs_to_line_notes)
    blob = by_line["13"]
    assert "长寿路" in blob
    assert "差异化管控" in blob
    assert "10.5mm" in blob


def test_notes_flow_one_para_per_chunk():
    rows = [
        ["线路", "锚段数量", "A", "B"],
        ["线路", "锚段数", "占比", "占比"],
        ["1号线", "10", "1", "10%"],
    ]
    flow, _ = build_notes_flow_after_table(
        rows,
        {"1": "1号线：接触网状态：南延伸为B。\n差异化管控：加强支柱巡视。"},
        [],
    )
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    assert len(texts) == 1
    assert texts[0].startswith("1号线")
    assert "南延伸为B" in texts[0]
    assert "差异化管控" not in "\n".join(texts)


def test_notes_flow_skips_duplicate_line_prefixed_chunk():
    rows = [
        ["线路", "总数量", "A"],
        ["线路", "数量", "占比"],
        ["5号线", "10", "1", "10%"],
    ]
    flow, _ = build_notes_flow_after_table(
        rows,
        {
            "5": "5号线：隔离开关：全线无C、D状态区段，维持现有管控。\n隔离开关：全线无C、D状态区段，维持现有管控。",
        },
        [],
    )
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    assert len(texts) == 1
    assert texts[0].startswith("5号线")
    assert "维持现有管控" in texts[0]


def test_missing_note_skips_empty_lead():
    rows = [
        ["线路", "锚段数量", "A"],
        ["线路", "锚段数", "占比"],
        ["2号线", "5", "1", "20%"],
    ]
    flow, _ = build_notes_flow_after_table(rows, {}, [])
    assert not any(x.get("missing_line_note") for x in flow)
    assert not any((x.get("text") or "").strip() in {"2号线：", "1号线："} for x in flow)


def test_skip_segment_labels_and_kind_headers():
    paras = [
        "1号线：",
        "接触网状态：北延伸为A。",
        "现有风险点的管控措施是：支柱开裂。",
        "北延伸",
        "5号线：",
        "柔性：",
        "接触网状态：C、D状态区段无。",
        "7号线：",
        "设备状态：",
        "柔性接触网：",
        "接触网状态：C状态区段为北延伸段。",
    ]
    by, _ = paragraphs_to_line_notes(paras)
    assert "支柱开裂" in by["1"]
    assert not by["1"].rstrip().endswith("北延伸")
    assert "C、D状态区段无" in by["5"]
    flow, _ = build_notes_flow_after_table(
        [
            ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
            ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
            ["5号线", "10", "5", "50%", "5", "50%", "0", "0%", "0", "0%"],
        ],
        by,
        [],
    )
    texts = "\n".join(x.get("text") or "" for x in flow)
    assert "柔性：" not in texts
    assert "C、D状态区段无" in texts


def test_zero_cd_row_drops_other_kind_c_list():
    from chapters.overhead.line_notes import strip_positive_cd_lists

    text = "8号线：没有D状态的区段。8号线C状态的区段是：8号线浦江镇停车场、二期柔性段芦恒路。"
    got = strip_positive_cd_lists(text)
    assert "柔性段" not in got
    flow, _ = build_notes_flow_after_table(
        [
            ["线路", "锚段数量", "A", "A", "B", "B", "C", "C", "D", "D"],
            ["线路", "锚段数量", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比", "锚段数", "占比"],
            ["8号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"],
        ],
        {"8": text},
        [],
    )
    blob = "\n".join(x.get("text") or "" for x in flow)
    assert "柔性段" not in blob


def test_collapse_duplicate_c_lists():
    by, _ = paragraphs_to_line_notes(
        [
            "13号线：",
            "C状态的区段是：13号线一期西段含金运路上下行；13号线没有D状态的区段。",
            "C状态的区段是：一期西段金运路，丰庄；13号线没有D状态的区段。",
        ]
    )
    blob = by["13"]
    assert blob.count("C状态的区段是") == 1
    assert "金运路上下行" in blob


def test_prefer_cd_note_over_commissioning_prose():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, _ = merge_line_notes_with_sources(
        [
            {
                "notes": ["15号线：接触网状态：15号线柔性没有C和D状态的区段，维持现有管控措施。"],
                "_recency": 1,
                "_idx": 0,
                "_source": "六部.docx",
            },
            {
                "notes": ["15号线：柔性接触网系统设备2021年投运，全线设备综合评级均为A类，运行状态良好。"],
                "_recency": 2,
                "_idx": 1,
                "_source": "七部.docx",
            },
        ]
    )
    assert "没有C和D" in by["15"]
    assert "2021年投运" not in by["15"]

    by2, _ = paragraphs_to_line_notes(
        [
            "15号线：柔性接触网系统设备2021年投运，全线设备综合评级均为A类，运行状态良好，无专项特殊管控需求。",
            "柔性没有C和D状态的区段，维持现有管控措施。",
        ]
    )
    assert "没有C和D" in by2["15"]
    assert "2021年投运" not in by2["15"]


def test_prefer_no_cd_over_other_kind_c_list():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, _ = merge_line_notes_with_sources(
        [
            {
                "notes": ["8号线没有C和D状态的，维持现有管控措施。"],
                "_recency": 1,
                "_idx": 0,
                "_source": "七部.docx",
            },
            {
                "notes": ["8号线：没有D状态的区段。8号线C状态的区段是：8号线浦江镇停车场、二期柔性段芦恒路。"],
                "_recency": 2,
                "_idx": 1,
                "_source": "六部.docx",
            },
        ]
    )
    assert "没有C和D" in by["8"]
    assert "柔性段" not in by["8"]


def test_slice_drops_risk_dump_from_switch_notes():
    text = (
        "3号线：C状态的区段是：3号线北延伸（含宝钢1库）；\n"
        "正线触网子系统和设备状态是 C\n"
        "主要风险点：\n"
        "1）3号中潭路渡线发生上部定位绳垂直吊弦断裂事件。\n"
        "现有管控措施是：开展年度生产计划与接触网集中修。\n"
        "4号线：没有C和D状态的区段。"
    )
    sw = slice_note_for_kind(text, "各线路隔离开关状态分布")
    assert "中潭路" not in sw
    assert "开展年度生产计划" not in sw


def test_slice_screen_drops_rigid_wear_prose():
    text = (
        "12号线：一期、二期刚性接触网状态是B, 部分锚段是C状态。存在一些分险点，"
        "如部分锚段加速取流段磨耗增长速度较快，目前已达11mm。"
    )
    screen = slice_note_for_kind(text, "各线路隔离开关控制屏状态分布")
    assert "11mm" not in screen
    assert "磨耗" not in screen


def test_zero_cd_missing_note_states_no_cd_from_table():
    flow, _ = build_notes_flow_after_table(
        [
            ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
            ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
            ["5号线", "20", "10", "50%", "10", "50%", "0", "0%", "0", "0%"],
        ],
        {},
        [],
    )
    blob = "\n".join(x.get("text") or "" for x in flow)
    assert "5号线" in blob
    assert "没有C和D" in blob


def test_keep_overhaul_need_from_older_flex_note():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, _ = merge_line_notes_with_sources(
        [
            {
                "notes": [
                    "2号线：接触网状态：C状态区段为西西延伸。",
                    "大修需求：东延伸及西西延伸接触网已超12年大修年限，亟需申报大修。",
                    "集中修项目：对2号线东延伸户外高架段开展集中修作业。",
                ],
                "_recency": 1,
                "_idx": 0,
                "_source": "旧.docx",
            },
            {
                "notes": ["2号线：接触网状态：C状态区段为西西延伸（主要分在北翟路停车场）。"],
                "_recency": 2,
                "_idx": 1,
                "_source": "新.docx",
            },
        ]
    )
    blob = by.get("2") or ""
    assert "北翟路停车场" in blob
    assert "大修需求" not in blob
    assert "集中修项目" not in blob


def test_collapse_keeps_no_d_from_shorter_c_list():
    by, _ = paragraphs_to_line_notes(
        [
            "7号线：",
            "C状态的区段是：7号线一期含龙阳路车场、龙华中路、上大路等；7号线北延伸含美兰湖、顾村公园。差异化管控是：龙阳路车场需对15台隔离开关开展集中修。",
            "C状态的区段是7号线一期正线含陈太路车辆段混合变电站；7号线没有D状态的区段。",
        ]
    )
    blob = by["7"]
    assert blob.count("C状态的区段是") == 1
    assert "龙阳路车场" in blob
    assert "没有D状态的区段" in blob


def test_c_nonzero_d_zero_appends_no_d():
    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["7号线", "238", "107", "44%", "78", "32%", "53", "22%", "0", "0%"],
    ]
    flow, _ = build_notes_flow_after_table(
        rows,
        {
            "7": "7号线：C状态的区段是：7号线一期含龙阳路车场。差异化管控是：集中修。2026年完成。",
        },
        [],
    )
    blob = "\n".join(x.get("text") or "" for x in flow)
    assert "龙阳路车场" in blob
    assert "7号线没有D状态的区段" in blob
    assert blob.count("没有D状态的区段") == 1


def test_already_has_no_d_not_duplicated():
    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["8号线", "204", "94", "46%", "14", "7%", "96", "47%", "0", "0%"],
    ]
    flow, _ = build_notes_flow_after_table(
        rows,
        {
            "8": "8号线：没有D状态的区段。8号线C状态的区段是：8号线浦江镇停车场。",
        },
        [],
    )
    blob = "\n".join(x.get("text") or "" for x in flow)
    assert blob.count("没有D") == 1


def test_c_and_d_nonzero_does_not_add_no_d():
    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["6号线", "159", "6", "4%", "52", "33%", "100", "63%", "1", "0.63%"],
    ]
    flow, _ = build_notes_flow_after_table(
        rows,
        {"6": "6号线：C状态的区段是：6号线正线含港城车场。6号线D状态的区段是6号线三林车场。"},
        [],
    )
    blob = "\n".join(x.get("text") or "" for x in flow)
    assert "没有D" not in blob
    assert "三林车场" in blob


def test_newer_c_list_keeps_older_no_d():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, _ = merge_line_notes_with_sources(
        [
            {
                "notes": [
                    "9号线C状态的区段是：9号线三期东延伸；9号线没有D状态的区段。",
                ],
                "_recency": 1,
                "_idx": 0,
                "_source": "五部旧.docx",
            },
            {
                "notes": [
                    "9号线C状态的区段是：9号线三期东延伸含曹路、顾唐路、金吉路等；9号线三期南延伸含松江新城、松江南站、醉白池。",
                ],
                "_recency": 2,
                "_idx": 1,
                "_source": "五部新.docx",
            },
        ]
    )
    blob = by["9"]
    assert "曹路" in blob
    assert "没有D状态的区段" in blob


def test_newer_d_list_does_not_keep_older_no_d():
    from chapters.overhead.line_notes import merge_line_notes_with_sources

    by, _, _, _ = merge_line_notes_with_sources(
        [
            {
                "notes": ["6号线C状态的区段是：港城车场。6号线没有D状态的区段。"],
                "_recency": 1,
                "_idx": 0,
                "_source": "五部旧.docx",
            },
            {
                "notes": [
                    "6号线C状态的区段是：6号线正线含港城车场。6号线D状态的区段是6号线三林车场。"
                ],
                "_recency": 2,
                "_idx": 1,
                "_source": "五部新.docx",
            },
        ]
    )
    blob = by["6"]
    assert "三林车场" in blob
    assert "没有D" not in blob


def test_cluster_closing_comes_after_all_line_notes():
    by, general = paragraphs_to_line_notes(
        [
            "17号线：C状态的区段是：17号线一期嘉松中路。17号线没有D状态的区段。",
            "上述D状态的区间，建议进行大修或计划实施大修。",
            "18号线：没有C和D状态的区段；维持现有管控措施。",
        ]
    )
    assert "嘉松中路" in by["17"]
    assert "上述" not in by["17"]
    assert "没有C和D" in by["18"]
    assert any("上述D状态的区间" in g for g in general)

    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["17号线", "164", "8", "5%", "154", "94%", "2", "1%", "0", "0%"],
        ["18号线", "132", "132", "100%", "0", "0%", "0", "0%", "0", "0%"],
    ]
    flow, _ = build_notes_flow_after_table(rows, by, general)
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    i17 = next(i for i, t in enumerate(texts) if t.startswith("17号线"))
    i18 = next(i for i, t in enumerate(texts) if t.startswith("18号线"))
    iclose = next(i for i, t in enumerate(texts) if t.startswith("上述"))
    assert i17 < i18 < iclose
    assert texts[iclose].startswith("上述D状态的区间")


def test_cluster_closing_inline_not_kept_on_line_17():
    by, general = paragraphs_to_line_notes(
        [
            "17号线C状态的区段是：17号线一期嘉松中路。17号线没有D状态的区段。上述D状态的区间，建议进行大修或计划实施大修。",
        ]
    )
    assert "嘉松中路" in by["17"]
    assert "上述" not in by["17"]
    assert any("上述D状态" in g for g in general)


def test_cluster_closing_before_backfilled_no_cd_line():
    by, general = paragraphs_to_line_notes(
        [
            "17号线：C状态的区段是：17号线一期嘉松中路。",
            "上述D状态的区间，建议进行大修或计划实施大修。",
        ]
    )
    rows = [
        ["线路", "总数量", "A", "A", "B", "B", "C", "C", "D", "D"],
        ["线路", "数量", "数量", "占比", "数量", "占比", "数量", "占比", "数量", "占比"],
        ["17号线", "164", "8", "5%", "154", "94%", "2", "1%", "0", "0%"],
        ["18号线", "132", "132", "100%", "0", "0%", "0", "0%", "0", "0%"],
    ]
    flow, _ = build_notes_flow_after_table(rows, by, general)
    texts = [x.get("text") or "" for x in flow if x.get("kind") == "para"]
    i18 = next(i for i, t in enumerate(texts) if t.startswith("18号线"))
    iclose = next(i for i, t in enumerate(texts) if "上述D状态" in t)
    assert i18 < iclose
    assert "没有C和D" in texts[i18]
