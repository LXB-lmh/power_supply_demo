# -*- coding: utf-8 -*-
"""单台设备附录 A 加权得分。权重合计须 100%；优/良/中/差 = 100/80/60/40。"""
from __future__ import annotations

from device_eval.catalog import get_device
from device_eval.grades import ABCD_BANDS, GRADE_LABEL, GRADE_SCORE, abcd, band_of, clamp_score


class EvalError(ValueError):
    pass


def _num(payload: dict, key: str):
    if key not in payload or payload[key] in (None, ""):
        return None
    try:
        return float(payload[key])
    except (TypeError, ValueError) as exc:
        raise EvalError(f"{key} 不是数字") from exc


def _match_op(op: dict, value: float) -> bool:
    kind = op["op"]
    if kind == "eq":
        return value == op["v"]
    if kind == "lt":
        return value < op["v"]
    if kind == "le":
        return value <= op["v"]
    if kind == "gt":
        return value > op["v"]
    if kind == "ge":
        return value >= op["v"]
    if kind == "between":
        lo_ok = value >= op["lo"] if op.get("lo_inc", True) else value > op["lo"]
        hi_ok = value <= op["hi"] if op.get("hi_inc", True) else value < op["hi"]
        return lo_ok and hi_ok
    if kind == "or":
        return any(_match_op(item, value) for item in op["items"])
    raise EvalError(f"未知比较 {kind}")


def _grade_result(grade: str, note: str = "") -> dict:
    return {
        "grade": grade,
        "grade_label": GRADE_LABEL.get(grade, grade),
        "score": GRADE_SCORE[grade],
        "note": note,
    }


def _option_note(param: dict, grade: str) -> str:
    """把团标选项原文写进说明，例如「优：备件可采购，设备技术支持完善」。"""
    label = GRADE_LABEL.get(grade, "")
    for opt in param.get("options") or []:
        if opt.get("grade") != grade and opt.get("value") != grade:
            continue
        text = (opt.get("text") or "").strip()
        if text:
            return f"{label}：{text}" if label else text
        picked = (opt.get("label") or "").strip()
        if picked:
            return picked
    return label


def _bands(scorer: dict, value: float) -> dict:
    for rule in scorer["rules"]:
        if _match_op(rule, value):
            return _grade_result(rule["grade"], f"取值 {value}{scorer.get('unit') or ''}")
    raise EvalError(f"取值 {value} 未落入团标分段")


def score_param(param: dict, payload: dict) -> dict:
    scorer = param["scorer"]
    kind = scorer["kind"]
    data = payload or {}

    if kind == "choice":
        grade = data.get("grade")
        allowed = {opt["grade"] for opt in param.get("options") or []}
        if grade not in GRADE_SCORE:
            raise EvalError(f"「{param['name']}」请选择 优/良/中/差")
        if allowed and grade not in allowed:
            raise EvalError(f"「{param['name']}」所选等级不在该参数团标选项中")
        return _grade_result(grade, _option_note(param, grade))

    if kind == "bands":
        value = _num(data, scorer.get("field") or "value")
        if value is None:
            raise EvalError(f"「{param['name']}」请填写数值")
        return _bands(scorer, value)

    if kind == "abs_pct":
        measured = _num(data, "measured")
        nominal = _num(data, "nominal")
        if measured is None or nominal is None:
            raise EvalError(f"「{param['name']}」请填写实测电压和额定电压")
        if nominal == 0:
            raise EvalError(f"「{param['name']}」额定电压不能为 0")
        pct = abs(measured - nominal) / abs(nominal) * 100
        result = _bands({"rules": scorer["rules"], "unit": "%"}, pct)
        result["note"] = f"偏差 {pct:.2f}%"
        return result

    if kind == "fault":
        if data.get("in_fault"):
            return {"grade": "", "grade_label": "故障状态不得分", "score": 0.0, "note": "当前故障"}
        count = _num(data, "count")
        n = _num(data, "n")
        if count is None or n is None:
            raise EvalError(f"「{param['name']}」请填写故障数和故障系数 n")
        score = clamp_score(100 - n * count)
        return {"grade": "", "grade_label": "公式", "score": score, "note": f"100−{n}×{count}"}

    if kind == "fault_rate":
        if data.get("in_fault"):
            return {"grade": "", "grade_label": "故障状态不得分", "score": 0.0, "note": "当前故障"}
        rate = _num(data, "rate")
        n = _num(data, "n")
        if rate is None or n is None:
            raise EvalError(f"「{param['name']}」请填写故障率和故障系数 n")
        score = clamp_score(100 - n * rate)
        return {"grade": "", "grade_label": "公式", "score": score, "note": f"100−{n}×{rate}"}

    if kind == "life":
        age = _num(data, "age")
        design = scorer.get("fixed_design")
        if design is None:
            design = _num(data, "design_life")
        if age is None or design is None:
            raise EvalError(f"「{param['name']}」请填写设计寿命和使用年限")
        if design <= 0:
            raise EvalError(f"「{param['name']}」设计寿命须大于 0")
        score = clamp_score((design - age) / design * 100)
        return {
            "grade": "",
            "grade_label": "公式",
            "score": score,
            "note": f"（{design}−{age}）/{design}×100",
        }

    if kind == "bow":
        bows = _num(data, "bow_count")
        if bows is None:
            raise EvalError(f"「{param['name']}」请填写弓架次总和")
        denom = float(scorer.get("denom") or 2_000_000)
        score = clamp_score((1 - bows / denom) * 100)
        return {
            "grade": "",
            "grade_label": "公式",
            "score": score,
            "note": f"（1−{bows}/{int(denom)}）×100",
        }

    if kind == "max_ratio":
        ratio = _num(data, "max_ratio")
        if ratio is None:
            raise EvalError(f"「{param['name']}」请填写 max（使用年限×评估系数/规程年限）")
        score = clamp_score((1 - ratio) * 100)
        return {"grade": "", "grade_label": "公式", "score": score, "note": f"（1−{ratio}）×100"}

    if kind == "winding_dc":
        klass = data.get("kva_class")
        unbalance = _num(data, "unbalance")
        if klass not in ("gt_1600", "le_1600") or unbalance is None:
            raise EvalError(f"「{param['name']}」请选择容量分档并填写相间差值百分比")
        if klass == "gt_1600":
            rules = [
                {"grade": "excellent", "op": "lt", "v": 0.5},
                {"grade": "good", "op": "lt", "v": 0.75},
                {"grade": "fair", "op": "lt", "v": 1},
                {"grade": "poor", "op": "ge", "v": 1},
            ]
        else:
            rules = [
                {"grade": "excellent", "op": "lt", "v": 1},
                {"grade": "good", "op": "lt", "v": 1.5},
                {"grade": "fair", "op": "lt", "v": 2},
                {"grade": "poor", "op": "ge", "v": 2},
            ]
        return _bands({"rules": rules, "unit": "%"}, unbalance)

    if kind == "withstand":
        reached = bool(data.get("reached"))
        grade = "excellent" if reached else "poor"
        return _grade_result(grade, _option_note(param, grade))

    raise EvalError(f"「{param['name']}」评分规则未实现")


def evaluate_device(standard_id: str, device_id: str, weights: dict, values: dict) -> dict:
    device = get_device(standard_id, device_id)
    errors: list[str] = []
    warnings: list[str] = []
    items = []
    weight_sum = 0.0

    for param in device["params"]:
        pid = param["id"]
        raw_w = (weights or {}).get(pid)
        if raw_w in (None, ""):
            errors.append(f"「{param['name']}」请填写权重")
            continue
        try:
            weight = float(raw_w)
        except (TypeError, ValueError):
            errors.append(f"「{param['name']}」权重须为数字")
            continue
        weight_sum += weight
        lo, hi = param.get("weight_min"), param.get("weight_max")
        if lo is not None and hi is not None and not (lo - 0.05 <= weight <= hi + 0.05):
            warnings.append(
                f"「{param['name']}」权重 {weight}% 不在建议取值范围 {lo:g}%–{hi:g}%"
            )
        try:
            scored = score_param(param, (values or {}).get(pid) or {})
        except EvalError as exc:
            errors.append(str(exc))
            continue
        contrib = weight / 100.0 * scored["score"]
        items.append(
            {
                "id": pid,
                "name": param["name"],
                "weight": weight,
                "score": round(scored["score"], 2),
                "contribution": round(contrib, 2),
                "grade": scored.get("grade") or "",
                "grade_label": scored.get("grade_label") or "",
                "note": scored.get("note") or "",
            }
        )

    if abs(weight_sum - 100) > 0.15:
        errors.append(f"权重合计为 {weight_sum:.1f}%，须为 100%")

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "items": items}

    total = round(sum(it["contribution"] for it in items), 2)
    grade = abcd(total)
    band = band_of(grade)
    return {
        "ok": True,
        "errors": [],
        "warnings": warnings,
        "device_id": device["id"],
        "device_name": device["name"],
        "score": total,
        "grade": grade,
        "grade_rule": band.get("rule") or "",
        "grade_status": band.get("status") or "",
        "grade_line": band.get("line") or "",
        "abcd_bands": [dict(x) for x in ABCD_BANDS],
        "items": items,
    }
