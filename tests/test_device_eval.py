# -*- coding: utf-8 -*-
"""团标附录 A 单台设备评估：硬规则，不进出报告生成。"""
from device_eval.catalog import get_device, public_standard
from device_eval.engine import evaluate_device
from device_eval.grades import GRADE_SCORE, abcd


def test_abcd_boundaries():
    """第 9.1 条：A≥90，B 为 75≤分＜90，C 为 60≤分＜75，D＜60。90 不是 B，75 不是 C。"""
    assert abcd(90) == "A"
    assert abcd(89.9) == "B"
    assert abcd(75) == "B"
    assert abcd(74.9) == "C"
    assert abcd(60) == "C"
    assert abcd(59.9) == "D"
    assert GRADE_SCORE["excellent"] == 100
    assert GRADE_SCORE["good"] == 80
    assert GRADE_SCORE["fair"] == 60
    assert GRADE_SCORE["poor"] == 40


def test_skip_accident_and_battery_panels():
    for sid in ("main_hv", "power"):
        names = [d["name"] for sub in public_standard(sid)["subsystems"] for d in sub["devices"]]
        assert "事故照明屏" not in names
        assert "蓄电池屏" not in names


def test_p6_p7_eps_voltage_weight_differs():
    p6 = get_device("main_hv", "main_hv:EPS")
    p7 = get_device("power", "power:EPS")
    w6 = next(p for p in p6["params"] if p["name"] == "输出电压")
    w7 = next(p for p in p7["params"] if p["name"] == "输出电压")
    assert w6["weight_min"] == 5
    assert w6["weight_max"] == 20
    assert w7["weight_min"] == 10
    assert w7["weight_max"] == 20


def test_mns_has_feeder_insulation_lv_has_relay():
    lv = get_device("power", "power:400V低压开关柜")
    mns = get_device("power", "power:400V MNS 低压开关柜")
    lv_names = [p["name"] for p in lv["params"]]
    mns_names = [p["name"] for p in mns["params"]]
    assert "继电保护测试" in lv_names
    assert "馈线电缆绝缘电阻测试" not in lv_names
    assert "馈线电缆绝缘电阻测试" in mns_names
    assert "继电保护测试" not in mns_names


def _eps_payload(temp, measured, capacity, grade, count, n, in_fault, age, design=30):
    weights = {
        "环境温度": 5,
        "输出电压": 15,
        "蓄电池容量": 25,
        "可维修性": 20,
        "设备故障状态": 20,
        "设备设计寿命": 15,
    }
    values = {
        "环境温度": {"value": temp},
        "输出电压": {"measured": measured, "nominal": 380},
        "蓄电池容量": {"value": capacity},
        "可维修性": {"grade": grade},
        "设备故障状态": {"count": count, "n": n, "in_fault": in_fault},
        "设备设计寿命": {"design_life": design, "age": age},
    }
    return weights, values


def test_eps_all_excellent_is_a():
    weights, values = _eps_payload(25, 380, 100, "excellent", 0, 10, False, 0)
    out = evaluate_device("main_hv", "main_hv:EPS", weights, values)
    assert out["ok"] is True
    assert out["score"] == 100
    assert out["grade"] == "A"
    repair = next(i for i in out["items"] if i["name"] == "可维修性")
    assert repair["note"] == "优：备件可采购，设备技术支持完善"


def test_eps_mixed_is_b_and_fault_state_zero():
    weights, values = _eps_payload(10, 390, 85, "good", 2, 10, False, 6)
    out = evaluate_device("main_hv", "main_hv:EPS", weights, values)
    assert out["ok"] is True
    # 5%*80 + 15%*80 + 25%*60 + 20%*80 + 20%*80 + 15%*80 = 75
    assert out["score"] == 75
    assert out["grade"] == "B"

    values["设备故障状态"]["in_fault"] = True
    out2 = evaluate_device("main_hv", "main_hv:EPS", weights, values)
    assert out2["ok"] is True
    assert out2["score"] == 59
    assert out2["grade"] == "D"
    fault = next(i for i in out2["items"] if i["name"] == "设备故障状态")
    assert fault["score"] == 0


def test_weight_sum_must_be_100():
    weights, values = _eps_payload(25, 380, 100, "excellent", 0, 10, False, 0)
    weights["环境温度"] = 6
    out = evaluate_device("main_hv", "main_hv:EPS", weights, values)
    assert out["ok"] is False
    assert any("100%" in e for e in out["errors"])


def test_p6_cable_life_uses_30_years():
    device = get_device("main_hv", "main_hv:35（33）kV 所内电缆")
    life = next(p for p in device["params"] if p["name"] == "设备设计寿命")
    assert life["scorer"].get("fixed_design") == 30
    weights = {p["id"]: p["weight_default"] for p in device["params"]}
    values = {
        "电缆破损": {"value": 0},
        "单回路电缆故障": {"value": 0},
        "电缆敷设环境": {"grade": "excellent"},
        "设备设计寿命": {"age": 6},
    }
    out = evaluate_device("main_hv", device["id"], weights, values)
    assert out["ok"] is True
    life_item = next(i for i in out["items"] if i["name"] == "设备设计寿命")
    assert life_item["score"] == 80  # (30-6)/30*100


def test_every_param_has_fields():
    for sid in ("main_hv", "power"):
        std = public_standard(sid)
        assert std["subsystems"]
        for sub in std["subsystems"]:
            assert sub["devices"]
            for device in sub["devices"]:
                assert device["params"]
                wsum = 0
                for param in device["params"]:
                    assert param["fields"]
                    wsum += float(param["weight_default"])
                assert abs(wsum - 100) < 0.2


def test_contact_line_continuation_merged():
    rail = get_device("power", "power:三轨")
    names = [p["name"] for p in rail["params"]]
    assert "防护罩" in names
    assert "缺陷" in names
    assert "设计使用寿命" in names


def test_api_catalog_and_evaluate():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    res = client.get("/api/device-eval/catalog", params={"standard_id": "main_hv"})
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "main_hv"
    assert body["subsystems"][0]["devices"]
    bands = {b["grade"]: b["line"] for b in body["abcd_bands"]}
    assert body["clause_9_1_lead"].startswith("9.1")
    assert "主变电系统" in body["clause_9_1_lead"]
    assert bands["A"] == "A：评价分≥90，表示状态为“好”“完好”或“完善”；"
    assert bands["B"] == "B：75≤评价分＜90，表示状态为“良”“良好”或“较完善”；"
    assert bands["C"] == "C：60≤评价分＜75，表示状态为“中”“一般”或“不太完善”；"
    res7 = client.get("/api/device-eval/catalog", params={"standard_id": "power"})
    assert "供电、能源系统" in res7.json()["clause_9_1_lead"]
    assert res7.json()["abcd_bands"][0]["line"] == body["abcd_bands"][0]["line"]
    device = next(d for sub in body["subsystems"] for d in sub["devices"] if d["name"] == "EPS")
    weights = {p["id"]: p["weight_default"] for p in device["params"]}
    values = {
        "环境温度": {"value": 25},
        "输出电压": {"measured": 380, "nominal": 380},
        "蓄电池容量": {"value": 100},
        "可维修性": {"grade": "excellent"},
        "设备故障状态": {"count": 0, "n": 10, "in_fault": False},
        "设备设计寿命": {"design_life": 30, "age": 0},
    }
    ev = client.post(
        "/api/device-eval/evaluate",
        json={"standard_id": "main_hv", "device_id": device["id"], "weights": weights, "values": values},
    )
    assert ev.status_code == 200
    data = ev.json()
    assert data["ok"] is True
    assert data["grade"] == "A"
    assert data["score"] == 100
    assert data["grade_line"] == "A：评价分≥90，表示状态为“好”“完好”或“完善”；"
    assert "完善" in data["grade_status"]


def test_bow_and_gis_sf6():
    from device_eval.engine import score_param

    gis = get_device("main_hv", "main_hv:110kV GIS开关")
    sf6 = next(p for p in gis["params"] if "微水" in p["name"])
    assert score_param(sf6, {"value": 150})["grade"] == "good"
    assert score_param(sf6, {"value": 80})["grade"] == "excellent"
    assert score_param(sf6, {"value": 300})["grade"] == "poor"

    flex = get_device("power", "power:柔性接触网（柔性地面、基地）")
    bow = next(p for p in flex["params"] if "弓架次" in p["name"])
    assert score_param(bow, {"bow_count": 0})["score"] == 100
    assert score_param(bow, {"bow_count": 1_000_000})["score"] == 50
