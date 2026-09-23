# -*- coding: utf-8 -*-
"""第四章 运营契合满意度。供电与接触网分文件，互不套用抽取规则。

供电用 power.py 的 HANDLER；接触网第四章尚未接入时不要 from chapters.ch4.power 去套。
POWER 惰性导入，避免 ch4 包初始化时就把抽取链路拉进来。
"""

__all__ = ["POWER"]


def __getattr__(name):
    """惰性给出 POWER HANDLER，避免 import chapters.ch4 时就把抽取链路拉进来。"""
    if name == "POWER":
        from chapters.ch4.power import HANDLER as POWER

        return POWER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
