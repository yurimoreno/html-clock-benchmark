"""Tests for the rendered-time analysis (no browser needed): synthetic diffs of
a hand drawn as a line from the pivot at known angles."""
import math
from benchmark_system.render_check import analyze, hand_angle, BASE, FRAMES

PIVOT = (100, 100)


def _hand(angle, length=70, width=2):
    cx, cy = PIVOT
    pts = set()
    for r in range(4, length):
        for w in range(-width // 2, width // 2 + 1):
            a = math.radians(angle)
            x = cx + r * math.sin(a) + w * math.cos(a)
            y = cy - r * math.cos(a) + w * math.sin(a)
            pts.add((round(x), round(y)))
    return list(pts)


def _diffs(offset=0.0):
    return {h: _hand(hand_angle(BASE, h) + offset) + _hand(hand_angle(FRAMES[h], h) + offset)
            for h in FRAMES}


def test_correct_clock_passes():
    r = analyze(_diffs())
    assert r["ok"] is True
    assert math.dist(r["pivot"], PIVOT) < 3


def test_quarter_turn_bug_fails():
    # the DeepSeek V4 Pro bug: every hand rotated -90°
    assert analyze(_diffs(-90))["ok"] is False


def test_upside_down_fails():
    assert analyze(_diffs(180))["ok"] is False


def test_missing_hand_is_inconclusive_not_wrong():
    d = _diffs()
    d["minute"] = []
    assert analyze(d)["ok"] is None


def test_no_movement_is_inconclusive():
    assert analyze({h: [] for h in FRAMES})["ok"] is None
