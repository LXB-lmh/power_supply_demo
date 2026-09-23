# -*- coding: utf-8 -*-
"""目录口径：供电与接触网分专业；供电子系统不含接触网；第4章仅供电规则就绪。"""
from catalog.taxonomy import get_chapter, get_subsystem, public_catalog


def test_catalog_power_and_overhead():
    catalog = public_catalog()
    ids = [d["id"] for d in catalog["domains"]]
    assert ids == ["power_supply", "overhead"]
    names = [d["name"] for d in catalog["domains"]]
    assert names == ["供电", "接触网"]
    assert "main_substation" not in ids  # 主变不是顶层专业，挂在供电下
    assert catalog["default_chapter"] == "ch3"
    assert len(catalog["chapters"]) == 9
    chapter_names = [c["name"] for c in catalog["chapters"]]
    assert chapter_names[0] == "设备功能有效性评估"
    assert chapter_names[1] == "运营契合满意度评估"
    assert chapter_names[-1] == "退运报废倾向性评估"
    power = next(d for d in catalog["domains"] if d["id"] == "power_supply")
    sub_names = [s["name"] for s in power["subsystems"]]
    assert "接触网(轨)" not in sub_names  # 供电专业子系统不含接触网
    assert "接触网" not in sub_names
    assert len(power["subsystems"]) == 8
    stray = get_subsystem("power_supply", "stray_current")
    assert stray["engine"] == "stray"
    assert stray["badge"] == "评分"
    trans = get_subsystem("power_supply", "transformer")
    assert trans["engine"] == "generic"
    main = get_subsystem("main_substation", "ms_distribution")
    assert "110kV GIS开关" in main["devices"]
    oh = get_subsystem("overhead", None)
    assert oh["domain_id"] == "overhead"
    assert oh["id"] == "oh_network"
    ch4 = get_chapter("ch4")
    assert ch4["no"] == 4
    assert ch4["rules_ready"] is False  # 全量未就绪；供电与接触网已由 ready_in 单独接入
    assert ch4["ready_in"] == ["power_supply", "overhead"]
    assert ch4["upload_hint"] == "设备评估结果总表，及其他相关评估材料。"
    assert ch4["upload_hint_by_domain"]["power_supply"].startswith("设备评估结果总表")
