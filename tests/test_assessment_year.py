# -*- coding: utf-8 -*-
"""评估年份口径：空/非法回落到今年，未来年份也钳到今年。"""
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scope.ledger import clamp_assessment_year


def test_clamp():
    now = datetime.now().year
    assert clamp_assessment_year(None) == now
    assert clamp_assessment_year("") == now
    assert clamp_assessment_year("abc") == now
    assert clamp_assessment_year("2025") == 2025
    assert clamp_assessment_year(2026) == min(2026, now)  # 不超过当前年
    assert clamp_assessment_year(2099) == now  # 未来年份钳到今年


if __name__ == "__main__":
    test_clamp()
    print("PASS clamp defaults to this year")
