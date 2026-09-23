# -*- coding: utf-8 -*-
"""网页用的专业与评估章节目录。

顶栏为供电 / 接触网；左侧为第 3～11 章。主变电仍保留在后台目录中，不在网页顶栏展示。
某专业某章能否点「评估」，看 chapter_ready：已注册 HANDLER，或 public_chapter 给出的 ready_in 含该专业。
接触网不要套供电规则——overhead 有独立 HANDLER，与供电分册材料与报告互不串用。
"""
from __future__ import annotations

from typing import Any


# 左侧第 3～11 章。rules_ready 只影响提示文案；网页能否评估看 chapter_ready / ready_in。
CHAPTERS: list[dict[str, Any]] = [
    {
        "id": "ch3",
        "no": 3,
        "name": "设备功能有效性评估",
        "short": "功能有效性",
        "upload_hint": "设备评估结果总表、管控措施（设备树）",
        "report_hint": "对照 2025 年报第 3 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch4",
        "no": 4,
        "name": "运营契合满意度评估",
        "short": "运营契合",
        "upload_hint": "设备评估结果总表，及其他相关评估材料。",
        "report_hint": "对照 2025 年报第 4 章目录，从总表与故障材料抽取填入。出处只标在标题后括号内。",
    },
    {
        "id": "ch5",
        "no": 5,
        "name": "管理体系合规性评估",
        "short": "管理体系",
        "upload_hint": "合规性材料（法律法规、企标、执行与评价）",
        "report_hint": "对照 2025 年报第 5 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch6",
        "no": 6,
        "name": "修程修制匹配性评估",
        "short": "修程修制",
        "upload_hint": "合规性材料中的修程修制、规程修订目录",
        "report_hint": "对照 2025 年报第 6 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch7",
        "no": 7,
        "name": "运维表现健康度评估",
        "short": "运维表现",
        "upload_hint": "生产计划执行表等运维质量材料",
        "report_hint": "对照 2025 年报第 7 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch8",
        "no": 8,
        "name": "风险隐患闭环度评估",
        "short": "风险隐患",
        "upload_hint": "安全隐患排查动态治理、隐患排查手册",
        "report_hint": "对照 2025 年报第 8 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch9",
        "no": 9,
        "name": "备件物资保障度评估",
        "short": "备件物资",
        "upload_hint": "安全库存清单（备件）",
        "report_hint": "对照 2025 年报第 9 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch10",
        "no": 10,
        "name": "使用环境符合性评估",
        "short": "使用环境",
        "upload_hint": "各线变电评估报告（使用环境段）",
        "report_hint": "对照 2025 年报第 10 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
    {
        "id": "ch11",
        "no": 11,
        "name": "退运报废倾向性评估",
        "short": "退运报废",
        "upload_hint": "退运材料、报废情况说明",
        "report_hint": "对照 2025 年报第 11 章目录成文。评分规则接入后按本章执行，不套用其他章。",
        "rules_ready": False,
    },
]


def public_chapter(item: dict[str, Any]) -> dict[str, Any]:
    """给网页的章信息。ready_in 来自已注册 HANDLER 的专业列表，决定该章在哪些专业显示可评估。"""
    from chapters.registry import handlers_for_chapter, ready_domains

    handlers = handlers_for_chapter(item["id"])
    ready_in = ready_domains(item["id"]) or list(item.get("ready_in") or [])
    upload_by = {h.domain_id: h.upload_hint for h in handlers if h.upload_hint}
    report_by = {h.domain_id: h.report_hint for h in handlers if h.report_hint}
    upload_hint = item.get("upload_hint") or ""
    if not upload_hint and handlers:
        upload_hint = handlers[0].upload_hint
    report_hint = item.get("report_hint") or ""
    if not report_hint and handlers:
        report_hint = handlers[0].report_hint
    return {
        "id": item["id"],
        "no": item["no"],
        "name": item["name"],
        "short": item.get("short") or item["name"],
        "upload_hint": upload_hint or "设备评估结果总表，及其他相关评估材料。",
        "report_hint": report_hint,
        "upload_hint_by_domain": upload_by,
        "report_hint_by_domain": report_by,
        "rules_ready": bool(item.get("rules_ready")),
        "ready_in": ready_in,
    }


def list_chapters() -> list[dict[str, Any]]:
    """左侧章节列表，每章已带 ready_in。"""
    return [public_chapter(item) for item in CHAPTERS]


def get_chapter(chapter_id: str | None) -> dict[str, Any]:
    """按 id 或章号取一章；缺省或未识别时落到第 3 章。"""
    wanted = (chapter_id or "").strip() or "ch3"
    for item in CHAPTERS:
        if item["id"] == wanted or str(item["no"]) == wanted:
            return public_chapter(item)
    return public_chapter(CHAPTERS[0])


def chapter_ready(domain_id: str | None, chapter_id: str | None) -> bool:
    """网页是否显示可评估、任务是否真正跑抽取。

    有 (专业, 章) HANDLER 即 True；否则看 ready_in 是否含该专业。
    """
    from chapters.registry import has_handler

    if has_handler(domain_id, chapter_id):
        return True
    chapter = get_chapter(chapter_id)
    ready_in = chapter.get("ready_in") or []
    if ready_in:
        return (domain_id or "") in ready_in
    return bool(chapter.get("rules_ready"))


def _sub(
    *,
    id: str,
    name: str,
    devices: list[str],
    engine: str = "generic",
    hint: str = "",
    ledger_aliases: list[str] | None = None,
    upload_hint: str = "",
    badge: str | None = None,
) -> dict[str, Any]:
    """组装一个子系统条目。ledger_aliases 含设备名，供旧抽检台账对类型。"""
    aliases = list(ledger_aliases or [])
    aliases.extend(devices)
    aliases.append(name)
    seen: list[str] = []
    for item in aliases:
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text)
    return {
        "id": id,
        "name": name,
        "devices": devices,
        "engine": engine,
        "ready": True,
        "badge": badge or "评分",
        "hint": hint,
        "upload_hint": upload_hint,
        "ledger_aliases": seen,
    }


# 供电、主变电（后台）、接触网。接触网与供电分册分开，材料与报告互不串用、不套对方规则。
DOMAINS: list[dict[str, Any]] = [
    {
        "id": "power_supply",
        "name": "供电",
        "full_name": "供电（含能源系统）",
        "standard": "T/SHJX 089.7-2025",
        "standard_part": "089.7",
        "default": True,
        "public": True,
        "subtitle": "与接触网分册分开评估，材料与报告互不串用",
        "subsystems": [
            _sub(
                id="power_monitoring",
                name="电力监控系统",
                devices=["中央信号屏", "可视化接地系统", "SCADA系统", "控制中心后台服务器", "调度工作站", "控制中心网关机", "复视系统"],
                hint="已按团标附录 A/B 写入评分规则。优先读设备评估结果总表中的「电力监控设备」列，有明细表则一并读取。",
                ledger_aliases=["电力监控系统", "SCADA系统"],
                upload_hint="设备评估结果总表、电力监控/SCADA 线路报告或明细表",
            ),
            _sub(
                id="distribution",
                name="配电系统",
                devices=[
                    "35(33)kV GIS开关",
                    "10kV GIS开关柜",
                    "400V低压开关柜",
                    "400V电容柜",
                    "400V MNS低压开关柜",
                    "有源滤波柜",
                    "1500V直流高速开关",
                    "1500V正极闸刀柜",
                    "1500V负极闸刀柜",
                    "750V直流高速开关",
                    "750V正极开关柜",
                    "750V负极闸刀柜",
                    "车站断路器",
                    "整流器",
                    "低压配电系统设备",
                    "配电箱",
                ],
                hint="已按团标表 A.7～A.14、附录 B 配电权重写入规则。总表中降压、牵引分两列。",
                ledger_aliases=["牵引系统", "降压系统", "配电系统", "直流开关", "整流器", "10kV开关", "400V开关"],
                upload_hint="设备评估结果总表、配电相关线路报告或牵引/降压明细表",
            ),
            _sub(
                id="emergency_power",
                name="应急电源",
                devices=["UPS", "EPS", "交直流屏", "直流屏"],
                hint="已按团标表 A.1～A.3、权重 C11～C14 写入规则。总表对应「应急电源设备」列。",
                ledger_aliases=["应急电源系统", "应急电源", "UPS", "EPS", "直流屏", "交直流屏"],
                upload_hint="设备评估结果总表、应急电源线路报告或明细表",
            ),
            _sub(
                id="stray_current",
                name="杂散电流",
                devices=["参比电极", "排流柜", "单向导通装置"],
                engine="stray",
                hint="已按团标表 A.4～A.6 接入评分。总表有「杂散电流设备」列；有设备明细表时按明细计分。",
                ledger_aliases=["杂散电流", "参比电极", "排流柜", "单向导通", "单项导通"],
                upload_hint="设备评估结果总表、杂散电流明细表或线路报告",
            ),
            _sub(
                id="power_cable",
                name="电力电缆",
                devices=[
                    "35(33)kV站内电缆",
                    "35(33)kV环网电缆",
                    "10kV站内电缆",
                    "10kV环网电缆",
                    "1500V上网电缆",
                    "750V上轨电缆",
                    "直流电缆",
                ],
                hint="已按团标表 A.18～A.19、权重 C41～C45 写入规则。总表对应「电力电缆设备」列。",
                ledger_aliases=["电力电缆", "直流电缆", "交流电缆"],
                upload_hint="设备评估结果总表、电力电缆线路报告或明细表",
            ),
            _sub(
                id="production_aux",
                name="生产辅助系统",
                devices=["智能照明系统", "灯具"],
                hint="已按团标表 A.25、A.34、A.35 写入规则。总表无此列，有材料则抽取，没有则黄底。",
                ledger_aliases=["生产辅助", "智能照明", "照明"],
                upload_hint="照明或生产辅助相关说明（Word/PDF 亦可）",
                badge="材料",
            ),
            _sub(
                id="transformer",
                name="变压器",
                devices=["电力变压器", "整流变压器"],
                hint="已按团标表 A.15、权重 C31～C33 写入规则。总表对应「变压器设备」列。",
                ledger_aliases=["变压系统", "变压器", "电力变压器", "整流变压器"],
                upload_hint="设备评估结果总表、变压器线路报告或明细表",
            ),
            _sub(
                id="energy",
                name="能耗设备",
                devices=["电能计量柜", "电能计量设备"],
                hint="已按团标表 A.26、权重 C101/C102 写入规则。总表「能源系统」行对应「能耗设备」列。",
                ledger_aliases=["能耗系统", "能耗设备", "电能计量"],
                upload_hint="设备评估结果总表、能耗专业报告或计量明细",
            ),
        ],
    },
    {
        "id": "main_substation",
        "name": "主变电",
        "full_name": "主变电系统",
        "standard": "T/SHJX 089.6-2025",
        "standard_part": "089.6",
        "default": False,
        "public": False,
        "subtitle": "团标第6部分 · 后台保留，网页顶栏改为接触网",
        "subsystems": [
            _sub(
                id="ms_emergency_power",
                name="应急电源",
                devices=["EPS", "交直流屏"],
                hint="主变电应急电源。当前总表主变电所行多为空，请上传主变电明细或线路报告。",
                ledger_aliases=["应急电源系统", "应急电源", "EPS", "直流屏"],
                upload_hint="主变电应急电源明细、1/15号线主变材料或线路报告",
            ),
            _sub(
                id="ms_distribution",
                name="配电设备",
                devices=["110kV GIS开关", "35(33)kV GIS开关柜", "10kV GIS开关柜", "400V低压开关柜"],
                hint="主变电配电设备。优先读主变系统明细表首页类型均分和 S1。",
                ledger_aliases=["主变", "主变系统", "110kV开关", "35kV GIS", "10kV开关", "400V开关"],
                upload_hint="主变系统.xlsx、1/15号线主变材料或线路报告",
            ),
            _sub(
                id="ms_transformer",
                name="变压器",
                devices=["110kV主变压器", "电力变压器", "接地变压器"],
                hint="主变电变压器。有明细表则读取类型均分和 S1。",
                ledger_aliases=["变压系统", "主变压器", "接地变压器", "电力变压器"],
                upload_hint="主变电变压系统明细或线路报告",
            ),
            _sub(
                id="ms_monitoring",
                name="电力监控系统",
                devices=["中央信号屏", "现场采集设备"],
                hint="主变电电力监控。有明细表则读取类型均分和 S1。",
                ledger_aliases=["电力监控系统", "现场采集"],
                upload_hint="主变电电力监控明细或线路报告",
            ),
            _sub(
                id="ms_cable",
                name="电力电缆",
                devices=["35(33)kV站内电缆", "10kV站内电缆"],
                hint="主变电电力电缆。有明细表则读取类型均分和 S1。",
                ledger_aliases=["电力电缆", "站内电缆"],
                upload_hint="主变电电力电缆明细或线路报告",
            ),
            _sub(
                id="ms_aux",
                name="生产辅助系统",
                devices=[],
                hint="团标此栏暂无明确对应设备，材料有则抽取，无则在报告中写未记载。",
                ledger_aliases=["生产辅助"],
                upload_hint="相关说明材料（Word/PDF 亦可）",
                badge="材料",
            ),
        ],
    },
    {
        # 网页顶栏第二项。各章 HANDLER 已接入，与供电分册分开评估。
        "id": "overhead",
        "name": "接触网",
        "full_name": "接触网",
        "standard": "接触网分册",
        "standard_part": "",
        "default": False,
        "public": True,
        "subtitle": "与供电分册分开评估，材料与报告互不串用",
        "subsystems": [
            _sub(
                id="oh_network",
                name="接触网系统",
                devices=["刚性接触网", "柔性接触网", "接触轨", "隔离开关", "隔离开关控制屏"],
                hint="接触网第3～11章已按触网年报体例接入。放入去年触网报告则学其目录，否则默认学2025触网保底年报。",
                ledger_aliases=["接触网", "刚性接触网", "柔性接触网", "接触轨"],
                upload_hint="接触网状态表、管控措施、故障趋势、安全库存、环境与退运材料",
                badge="评估",
            ),
        ],
    },
]


# 网页顶栏只展示这两个专业；主变电 public=False，后台目录仍保留。
UI_DOMAIN_IDS = ("power_supply", "overhead")


def list_domains() -> list[dict[str, Any]]:
    """全部专业（含后台主变电），给内部用；网页目录走 public_catalog。"""
    return [public_domain(d) for d in DOMAINS]


def get_domain(domain_id: str | None) -> dict[str, Any]:
    """按 id 取专业；未识别时落到供电。"""
    wanted = (domain_id or "").strip() or "power_supply"
    for item in DOMAINS:
        if item["id"] == wanted:
            return item
    for item in DOMAINS:
        if item["id"] == "power_supply":
            return item
    return DOMAINS[0]


def get_subsystem(domain_id: str | None, subsystem_id: str | None) -> dict[str, Any]:
    """取某专业下的子系统。供电缺省落到杂散电流；其他专业落到该专业第一个。"""
    domain = get_domain(domain_id)
    wanted = (subsystem_id or "").strip()
    for item in domain["subsystems"]:
        if item["id"] == wanted:
            return dict(item, domain_id=domain["id"], domain_name=domain["name"], standard=domain["standard"])
    fallback_id = "stray_current" if domain["id"] == "power_supply" else domain["subsystems"][0]["id"]
    for item in domain["subsystems"]:
        if item["id"] == fallback_id:
            return dict(item, domain_id=domain["id"], domain_name=domain["name"], standard=domain["standard"])
    item = domain["subsystems"][0]
    return dict(item, domain_id=domain["id"], domain_name=domain["name"], standard=domain["standard"])


def public_domain(domain: dict[str, Any]) -> dict[str, Any]:
    """给网页的专业卡片：章列表 + 子系统（不含 ledger_aliases 等内部字段）。"""
    return {
        "id": domain["id"],
        "name": domain["name"],
        "full_name": domain.get("full_name") or domain["name"],
        "standard": domain.get("standard") or "",
        "standard_part": domain.get("standard_part") or "",
        "default": bool(domain.get("default")),
        "subtitle": domain.get("subtitle") or "",
        "chapters": list_chapters(),
        "subsystems": [
            {
                "id": item["id"],
                "name": item["name"],
                "devices": item["devices"],
                "engine": item["engine"],
                "ready": bool(item.get("ready")),
                "badge": item.get("badge") or "抽检",
                "hint": item.get("hint") or "",
                "upload_hint": item.get("upload_hint") or "",
            }
            for item in domain["subsystems"]
        ],
    }


def public_catalog() -> dict[str, Any]:
    """网页顶栏 + 左侧目录。只含 public 专业（供电、接触网），不含后台主变电。"""
    return {
        "default_domain": "power_supply",
        "default_chapter": "ch3",
        "default_subsystem": "stray_current",
        "chapters": list_chapters(),
        "domains": [public_domain(d) for d in DOMAINS if d.get("public", d["id"] in UI_DOMAIN_IDS)],
    }
