"""Tests for the measured-answer verdicts (no browser needed)."""
import math
from benchmark_system.measure import continuity_verdict, responsive_verdict, CONTINUITY
from benchmark_system.render_check import hand_angle

PIVOT = (100, 100)


def _ray(angle, length=60):
    a = math.radians(angle)
    return [(round(PIVOT[0] + r * math.sin(a)), round(PIVOT[1] - r * math.cos(a))) for r in range(6, length)]


def test_continuous_minute_hand_detected():
    a, b, hand = CONTINUITY["time.minute_continuous"]
    pts = _ray(hand_angle(a, hand)) + _ray(hand_angle(b, hand)) + _ray(30) + _ray(330)
    assert continuity_verdict("time.minute_continuous", pts, PIVOT)[0] is True


def test_minute_hand_that_waits_for_the_minute_fails():
    # only the second hand moved (30° -> 330°); nothing along the minute hand's path
    pts = _ray(30) + _ray(330)
    assert continuity_verdict("time.minute_continuous", pts, PIVOT)[0] is False


def test_whole_second_hand_fails_ms_check():
    assert continuity_verdict("time.second_ms_precision", [], PIVOT)[0] is False


def test_responsive_needs_size_change():
    assert responsive_verdict([200, 320])[0] is True
    assert responsive_verdict([246, 248])[0] is False
    assert responsive_verdict([None, 300])[0] is None
