# -*- coding: utf-8 -*-
"""旧抽检台账评分：从杂散电流等抽检表直接抽设备打分，避免整表丢给大模型。

年报填空主要走 grade_matrix；本模块仍给杂散明细/系统汇总用。
评估年经 clamp_assessment_year 限制在 2015～今年，寿命分按该年减启用年。
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from parsers.document_model import DocumentModel
from scope.names import canonical_device_type, guess_device_type, normalize_line, normalize_segment

CODE_GRADE = {
    "1": "优",
    "2": "良",
    "3": "中",
    "4": "差",
}
# 这些抽检项在台账里按优/差两档记，不保留良/中。
BINARY_FIELDS = {
    "hardware_grade",
    "appearance_grade",
    "fault_signal_grade",
    "switch_operation_grade",
}
# 抽检台账里的设计寿命（年），超期时会把 design_life 抬到已用年数以免寿命分为负。
DESIGN_LIFE = {
    "参比电极": 20,
    "排流柜": 25,
    "单向导通装置": 25,
}
MISSING_SCORES = {"", "/", "-", "—", "–", "无", "\\", "nan", "none", "null"}
CONTROL_HINTS = ("大修", "更新改造", "专项维修", "备件", "纳入", "更换")
STRAY_HINTS = ("杂散", "参比", "排流", "单向", "单项", "单导")
# 系统汇总表上三类设备得分列的表头别名。
TYPE_SCORE_COLUMNS = (
    ("参比电极", ("参比电极", "参比")),
    ("排流柜", ("排流柜", "排流")),
    ("单向导通装置", ("单向导通装置", "单项导通装置", "单导")),
)


def _col(header: list[str], *needles: str) -> int | None:
    """表头从左找第一列。"""
    for i, cell in enumerate(header):
        text = str(cell or "")
        if any(n in text for n in needles):
            return i
    return None


def _col_last(header: list[str], *needles: str) -> int | None:
    """表头从左找最后一列（得分、等级常在表尾，避免误命中中间列）。"""
    found = None
    for i, cell in enumerate(header):
        text = str(cell or "")
        if any(n in text for n in needles):
            found = i
    return found


def _cell(row: list[str], index: int | None) -> str:
    """按列下标取单元格。"""
    if index is None or index >= len(row):
        return ""
    return str(row[index] or "").strip()


def _grade(raw: str, *, binary: bool = False) -> str | None:
    """优良中差或 1～4 码。binary 时非优一律记差。"""
    text = str(raw or "").strip()
    if not text:
        return None
    if text in {"优", "良", "中", "差"}:
        return "优" if not binary else ("优" if text == "优" else "差")
    code = re.sub(r"\D", "", text.split(".")[0])
    grade = CODE_GRADE.get(code)
    if not grade:
        return None
    if binary:
        return "优" if grade == "优" else "差"
    return grade


def _int(raw: str) -> int | None:
    """单元格转整数；空或非数字返回 None。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _excel_round0(value: float) -> int:
    """与 Excel ROUND(x,0) 一致（四舍五入，含 .5 进位）。"""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _excel_rounddown0(value: float) -> int:
    """向零方向取整，对应 Excel ROUNDDOWN(x,0)。"""
    return math.floor(value) if value >= 0 else math.ceil(value)


def _code_num(raw: str) -> int | None:
    """优良中差转 1～4，或直接读数字码。"""
    text = str(raw or "").strip()
    if not text:
        return None
    mapped = {"优": 1, "良": 2, "中": 3, "差": 4}
    if text in mapped:
        return mapped[text]
    try:
        return int(float(text))
    except ValueError:
        return None


def _life_points(year: int | None, today_year: int) -> int:
    """寿命分：按评估年减启用年，公式与抽检台账 Excel 一致。today_year 须已经 clamp。"""
    if not year:
        return 0
    used = today_year - year
    return max(0, _excel_round0(25 * (20 - used) / 20.0))


def _excel_device_score(row_type: str, values: list[str], cols: dict[str, int | None], today_year: int) -> float | None:
    """按抽检台账三类设备公式现算得分；缺关键列且无启用年则放弃，改读表上得分。"""
    year = _int(_cell(values, cols.get("year")))
    fault = _int(_cell(values, cols.get("fault"))) or 0
    life = _life_points(year, today_year)
    if row_type == "参比电极":
        env = _code_num(_cell(values, cols.get("env")))
        hw = _code_num(_cell(values, cols.get("hw")))
        data = _code_num(_cell(values, cols.get("data")))
        spare = _code_num(_cell(values, cols.get("spare")))
        if None in (env, hw, data, spare) and year is None:
            return None
        item = {1: 10, 2: 5, 3: 3}.get(env or 4, 1)
        item += 10 if hw == 1 else 5
        item += {1: 10, 3: 5}.get(data or 0, 0)
        item += {1: 20, 2: 15, 3: 10}.get(spare or 4, 5)
        item += 25 - 2 * fault
        item += life
        return float(item)
    if row_type == "排流柜":
        appear = _code_num(_cell(values, cols.get("appear")))
        current = _code_num(_cell(values, cols.get("current")))
        signal = _code_num(_cell(values, cols.get("signal")))
        spare = _code_num(_cell(values, cols.get("spare")))
        if None in (appear, current, signal, spare) and year is None:
            return None
        item = 10 if appear == 1 else 5
        item += 15 if current == 1 else 5
        item += 15 if signal == 1 else 5
        item += {1: 20, 2: 15, 3: 10}.get(spare or 4, 5)
        item += 15 - fault
        item += life
        return float(item)
    env = _code_num(_cell(values, cols.get("env")))
    signal = _code_num(_cell(values, cols.get("signal")))
    current = _code_num(_cell(values, cols.get("current")))
    switch = _code_num(_cell(values, cols.get("switch")))
    spare = _code_num(_cell(values, cols.get("spare")))
    if None in (env, signal, current, switch, spare) and year is None:
        return None
    item = {1: 5, 2: 3, 3: 1}.get(env or 4, 0)
    item += 10 if signal == 1 else 5
    item += 15 if current == 1 else 5
    item += 10 if switch == 1 else 5
    item += {1: 20, 2: 15, 3: 10}.get(spare or 4, 5)
    item += 15 - fault
    item += life
    return float(item)


def _optional_score(raw: str) -> float | None:
    """读表上已填的得分；空占位不当成 0 分。"""
    text = str(raw or "").strip()
    if text.lower() in MISSING_SCORES:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _letter_grade(raw: str) -> str | None:
    """系统状态等级只认 A～D。"""
    text = str(raw or "").strip().upper().replace("类", "").replace("级", "")
    if text in {"A", "B", "C", "D"}:
        return text
    return None


def _amps(raw: str) -> float | None:
    """额定电流：优先认带 A 的数字，否则当纯数字。"""
    text = str(raw or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*A", text, re.I)
    if match:
        return float(match.group(1))
    try:
        return float(text)
    except ValueError:
        return None


def _current_pair(nameplate: float | None, code: str) -> tuple[float | None, float | None]:
    """由铭牌电流和优/差码还原总电流（优=0.6 倍、差=1.1 倍），与台账反推口径一致。"""
    if nameplate is None:
        return None, None
    grade = _grade(code, binary=True)
    if grade == "优":
        return round(nameplate * 0.6, 2), nameplate
    if grade == "差":
        return round(nameplate * 1.1, 2), nameplate
    return None, nameplate


def _device_type_for_table(heading: str, header: list[str]) -> str:
    """从表标题和表头猜设备类型；认不出则整表跳过。"""
    joined = heading + " " + " ".join(str(c) for c in header)
    guessed = guess_device_type(joined)
    if guessed:
        return guessed
    return ""


def _is_system_rollup(header: list[str]) -> bool:
    """系统汇总表（有系统状态，或有三类设备列但无站名），不当成逐台抽检。"""
    if _col(header, "系统状态") is not None:
        return True
    has_types = _col(header, "参比电极") is not None and _col(header, "排流柜") is not None
    return has_types and _col(header, "站名", "车站") is None


def clamp_assessment_year(value: object | None) -> int:
    """把评估年夹在 2015～今年。

    选哪一年，寿命分就按哪一年减启用年（等同那年打开 Excel 的 YEAR(TODAY())）。
    未选或非法则用今年；早于 2015 提到 2015，晚于今年压到今年。
    """
    now = datetime.now().year
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        year = now
    return max(2015, min(now, year))


def extract_ledger_from_documents(
    docs: list[DocumentModel],
    assessment_year: int | None = None,
) -> list[dict[str, Any]]:
    """从抽检台账表抽逐台设备。跳过系统汇总表；评估年先 clamp 再算寿命分。"""
    year = clamp_assessment_year(assessment_year)
    records: list[dict[str, Any]] = []
    heading = ""
    for doc in docs:
        for block in doc.blocks:
            if block.type == "heading":
                heading = block.text
                continue
            if block.type != "table" or not block.rows:
                continue
            header = [str(c) for c in block.rows[0]]
            if _col(header, "线路") is None:
                continue
            if _is_system_rollup(header):
                continue
            joined = heading + " " + " ".join(header)
            if _col(header, "站名", "车站") is None and "参比" not in joined:
                continue
            device_type = _device_type_for_table(heading, header)
            if not device_type:
                continue
            records.extend(_rows_to_records(block.rows, device_type, heading, year))
    return records


def extract_system_summaries(docs: list[DocumentModel]) -> list[dict[str, Any]]:
    """读「杂散系统」这类汇总表上的类型均分、S1、等级，不现算。"""
    rows: list[dict[str, Any]] = []
    heading = ""
    for doc in docs:
        for block in doc.blocks:
            if block.type == "heading":
                heading = block.text
                continue
            if block.type != "table" or not block.rows:
                continue
            header = [str(c) for c in block.rows[0]]
            if not _is_system_rollup(header):
                continue
            line_i = _col(header, "线路")
            seg_i = _col(header, "区段")
            s1_i = _col(header, "系统状态值", "S1")
            grade_i = _col(header, "系统状态等级") or _col_last(header, "等级")
            type_cols = {
                name: _col(header, *needles) for name, needles in TYPE_SCORE_COLUMNS
            }
            for raw in block.rows[1:]:
                values = [str(c) if c is not None else "" for c in raw]
                line_id = normalize_line(_cell(values, line_i))
                if not line_id:
                    continue
                type_scores = {
                    name: _optional_score(_cell(values, index)) for name, index in type_cols.items()
                }
                rows.append(
                    {
                        "line_id": line_id,
                        "segment": normalize_segment(_cell(values, seg_i)),
                        "type_scores": type_scores,
                        "s1": _optional_score(_cell(values, s1_i)),
                        "grade": _letter_grade(_cell(values, grade_i)),
                        "source_note": heading or "杂散系统",
                    }
                )
    return rows


def _grade_from_s1(s1: float) -> str:
    """S1 定级：≥90 A、≥75 B、≥60 C，否则 D。"""
    if s1 >= 90:
        return "A"
    if s1 >= 75:
        return "B"
    if s1 >= 60:
        return "C"
    return "D"


def rollup_system_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按「杂散系统」公式现算：ROUND(均分) → ROUNDDOWN(三类平均) → 90/75/60 定级。"""
    buckets: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        score = record.get("official_score")
        if score is None:
            continue
        line_id = normalize_line(record.get("line_id"))
        if not line_id:
            continue
        device_type = canonical_device_type(record.get("device_type"))
        if device_type not in {"参比电极", "排流柜", "单向导通装置"}:
            continue
        key = (line_id, normalize_segment(record.get("segment")))
        buckets[key][device_type].append(float(score))
    rows: list[dict[str, Any]] = []
    for (line_id, segment), by_type in sorted(buckets.items()):
        type_scores: dict[str, float | None] = {}
        present: list[float] = []
        for name in ("参比电极", "排流柜", "单向导通装置"):
            scores = by_type.get(name) or []
            if not scores:
                type_scores[name] = None
                continue
            avg = _excel_round0(sum(scores) / len(scores))
            type_scores[name] = float(avg)
            present.append(float(avg))
        if not present:
            continue
        s1 = float(_excel_rounddown0(sum(present) / len(present)))
        rows.append(
            {
                "line_id": line_id,
                "segment": segment,
                "type_scores": type_scores,
                "s1": s1,
                "grade": _grade_from_s1(s1),
                "source_note": "按设备得分现算（与杂散系统公式一致）",
            }
        )
    return rows


def extract_control_notes(docs: list[DocumentModel], extra_text: str = "") -> list[str]:
    """从正文里抽与杂散相关的管控措施句（大修、更换、备件等），最多 12 条。"""
    chunks: list[str] = []
    for doc in docs:
        for block in doc.blocks:
            if block.type == "table":
                continue
            text = (block.text or "").strip()
            if text:
                chunks.append(text)
    if extra_text:
        chunks.extend(line.strip() for line in extra_text.splitlines() if line.strip())
    notes: list[str] = []
    seen: set[str] = set()
    for text in chunks:
        if len(text) < 10 or len(text) > 180:
            continue
        if text.startswith("#") or "工作表:" in text:
            continue
        if not any(h in text for h in CONTROL_HINTS):
            continue
        if not any(h in text for h in STRAY_HINTS):
            continue
        if text in seen:
            continue
        seen.add(text)
        notes.append(text)
        if len(notes) >= 12:
            break
    return notes


def _rows_to_records(
    rows: list[list[str]],
    device_type: str,
    heading: str,
    assessment_year: int | None = None,
) -> list[dict[str, Any]]:
    """一张抽检表转设备记录。能按公式现算则用现算分；否则退回表上得分/等级。"""
    header = [str(c) for c in rows[0]]
    seq_i = _col(header, "序号")
    line_i = _col(header, "线路")
    seg_i = _col(header, "区段")
    station_i = _col(header, "站名", "车站")
    loc_i = _col(header, "位置")
    env_i = _col(header, "运行环境")
    hw_i = _col(header, "硬件检测")
    data_i = _col(header, "数据采集")
    spare_i = _col(header, "可维修性")
    fault_i = _col(header, "故障数")
    used_i = _col(header, "设备运营年限")
    year_i = _col(header, "启用年限")
    appear_i = _col(header, "二次设备检查")
    current_i = _col(header, "支路电流", "总电流测量")
    signal_i = _col(header, "故障信号")
    switch_i = _col(header, "闸刀")
    fuse_i = _col(header, "熔丝", "额定电流")
    name_i = _col(header, "设备名称")
    score_i = _col_last(header, "得分")
    grade_i = _col_last(header, "评级", "评价")

    out: list[dict[str, Any]] = []
    for offset, row in enumerate(rows[1:], start=1):
        values = [str(c) if c is not None else "" for c in row]
        line_id = normalize_line(_cell(values, line_i))
        if not line_id:
            continue
        station = _cell(values, station_i) or _cell(values, loc_i) or "未知站"
        seq = _cell(values, seq_i) or str(offset)
        row_type = canonical_device_type(_cell(values, name_i)) or device_type
        record: dict[str, Any] = {
            "device_type": row_type,
            "device_id": f"{row_type[:2]}-{line_id}-{station}-{seq}",
            "line_id": line_id,
            "segment": normalize_segment(_cell(values, seg_i)),
            "station_id": station,
            "design_life_years": DESIGN_LIFE.get(row_type, 25),
            "used_years": _int(_cell(values, used_i)),
            "fault_count_lifetime": _int(_cell(values, fault_i)) if _cell(values, fault_i) != "" else 0,
            "fault_in_service": False,
            "source_note": heading or "抽检台账",
            "confidence": 0.85,
        }
        today_year = clamp_assessment_year(assessment_year)
        year = _int(_cell(values, year_i))
        if year:
            record["install_date"] = f"{year}-01-01"
            record["used_years"] = max(0, today_year - year)
        if record.get("used_years") is None:
            record["used_years"] = 0
        if record["used_years"] > record["design_life_years"]:
            record["design_life_years"] = record["used_years"]
        computed = _excel_device_score(
            row_type,
            values,
            {
                "env": env_i,
                "hw": hw_i,
                "data": data_i,
                "spare": spare_i,
                "fault": fault_i,
                "year": year_i,
                "appear": appear_i,
                "current": current_i,
                "signal": signal_i,
                "switch": switch_i,
            },
            today_year,
        )
        if computed is not None:
            record["official_score"] = computed
            record["official_grade"] = _grade_from_s1(computed)
        else:
            official_score = _optional_score(_cell(values, score_i))
            official_grade = _letter_grade(_cell(values, grade_i))
            if official_score is not None:
                record["official_score"] = official_score
            if official_grade:
                record["official_grade"] = official_grade

        if row_type == "参比电极":
            record["env_grade"] = _grade(_cell(values, env_i))
            record["hardware_grade"] = _grade(_cell(values, hw_i), binary=True)
            record["data_stability_grade"] = _grade(_cell(values, data_i))
            record["spare_parts_grade"] = _grade(_cell(values, spare_i))
        elif row_type == "排流柜":
            record["appearance_grade"] = _grade(_cell(values, appear_i), binary=True)
            record["fault_signal_grade"] = _grade(_cell(values, signal_i), binary=True)
            record["spare_parts_grade"] = _grade(_cell(values, spare_i))
            nameplate = _amps(_cell(values, fuse_i))
            total, plate = _current_pair(nameplate, _cell(values, current_i))
            record["nameplate_current_A"] = plate
            record["total_current_A"] = total
        else:
            record["env_grade"] = _grade(_cell(values, env_i))
            record["fault_signal_grade"] = _grade(_cell(values, signal_i), binary=True)
            record["switch_operation_grade"] = _grade(_cell(values, switch_i), binary=True)
            record["spare_parts_grade"] = _grade(_cell(values, spare_i))
            nameplate = _amps(_cell(values, fuse_i))
            total, plate = _current_pair(nameplate, _cell(values, current_i))
            record["nameplate_current_A"] = plate
            record["total_current_A"] = total
        out.append(record)
    return out
