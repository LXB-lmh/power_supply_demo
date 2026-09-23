# -*- coding: utf-8 -*-
"""设备评估目录：启动时从附录 A 表编译一次。"""
from __future__ import annotations

from functools import lru_cache

from device_eval.catalog_build import STANDARDS, build_all
from device_eval.grades import ABCD_BANDS, CLAUSE_9_1_LEAD


@lru_cache(maxsize=1)
def _all() -> dict:
    return build_all()


def public_standards() -> list[dict]:
    return [
        {"id": s["id"], "name": s["name"], "short": s["short"], "standard": s["standard"]}
        for s in STANDARDS
    ]


def get_standard(standard_id: str) -> dict:
    data = _all()
    if standard_id not in data:
        raise KeyError(standard_id)
    return data[standard_id]


def get_device(standard_id: str, device_id: str) -> dict:
    std = get_standard(standard_id)
    for device in std["devices"]:
        if device["id"] == device_id:
            return device
    raise KeyError(device_id)


def _public_param(param: dict) -> dict:
    return {
        "id": param["id"],
        "name": param["name"],
        "hint": param.get("hint") or "",
        "rule_text": param.get("rule_text") or "",
        "weight_min": param.get("weight_min"),
        "weight_max": param.get("weight_max"),
        "weight_default": param.get("weight_default"),
        "input": param.get("input"),
        "fields": param.get("fields") or [],
        "options": param.get("options") or [],
    }


def public_standard(standard_id: str) -> dict:
    std = get_standard(standard_id)
    subsystems = []
    for sub in std["subsystems"]:
        subsystems.append(
            {
                "id": sub["id"],
                "name": sub["name"],
                "devices": [
                    {
                        "id": d["id"],
                        "name": d["name"],
                        "params": [_public_param(p) for p in d["params"]],
                    }
                    for d in sub["devices"]
                ],
            }
        )
    return {
        "id": std["id"],
        "name": std["name"],
        "short": std["short"],
        "standard": std["standard"],
        "abcd_bands": [dict(x) for x in ABCD_BANDS],
        "clause_9_1_lead": CLAUSE_9_1_LEAD.get(std["id"], ""),
        "subsystems": subsystems,
    }
