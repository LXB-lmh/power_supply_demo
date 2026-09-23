# -*- coding: utf-8 -*-
"""团标附录 A 单台设备功能有效性评估（独立模块，不进出报告生成）。"""

from device_eval.catalog import get_device, public_standard, public_standards
from device_eval.engine import evaluate_device

__all__ = ["evaluate_device", "get_device", "public_standard", "public_standards"]
