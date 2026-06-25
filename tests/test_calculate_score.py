"""Tests for the weighted rubric in runner.calculate_score.

calculate_score is pure (dict in, (score, breakdown) out) and is the single
most consequential function in the repo — it produces the leaderboard numbers.
"""
from benchmark_system.runner import calculate_score


def _perfect_audit():
    """An audit that should pass every rubric criterion."""
    return {
        "time": {
            "hour_continuous": True,
            "minute_continuous": True,
            "second_ms_precision": True,
            "correct_12_top": True,
        },
        "visual": {
            "has_shadows": True,
            "has_gradients": True,
            "has_hand_tails": True,
            "has_center_cap": True,
            "has_bezel": True,
        },
        "dial": {
            "hour_ticks_count": 12,
            "minute_ticks_count": 60,
            "numerals_count": 12,
            "automated_marker_generation": True,
            "skips_minute_at_hour": True,
        },
        "code": {
            "globals_count": 1,
            "is_responsive": True,
            "uses_helpers": True,
            "zero_dependencies": True,
        },
        "smoothness": {
            "method": "rAF",
            "zero_latency_init": True,
        },
    }


def test_empty_audit_scores_zero():
    score, breakdown = calculate_score(None)
    assert score == 0
    assert breakdown == {"time": 0, "visual": 0, "dial": 0, "code": 0, "motion": 0}


def test_perfect_audit_scores_ten():
    score, breakdown = calculate_score(_perfect_audit())
    assert score == 10.0
    assert breakdown == {
        "time": 10.0,
        "visual": 10.0,
        "dial": 10.0,
        "code": 10.0,
        "motion": 10,
    }


def test_missing_globals_count_fails_code_criterion():
    """globals_count defaults to 99 when absent, so it must fail the <=2 gate."""
    audit = _perfect_audit()
    del audit["code"]["globals_count"]
    _, breakdown = calculate_score(audit)
    # 3.0 (globals) lost, rest of code section intact => 7.0
    assert breakdown["code"] == 7.0


def test_dial_count_thresholds_are_inclusive():
    audit = _perfect_audit()
    audit["dial"]["hour_ticks_count"] = 12   # >= 12 passes
    audit["dial"]["minute_ticks_count"] = 48  # >= 48 passes
    audit["dial"]["numerals_count"] = 12      # >= 12 passes
    _, breakdown = calculate_score(audit)
    assert breakdown["dial"] == 10.0


def test_dial_count_below_threshold_fails():
    audit = _perfect_audit()
    audit["dial"]["hour_ticks_count"] = 11
    audit["dial"]["minute_ticks_count"] = 47
    audit["dial"]["numerals_count"] = 11
    _, breakdown = calculate_score(audit)
    # only automated_marker_generation + skips_minute_at_hour remain => 4.0
    assert breakdown["dial"] == 4.0


def test_motion_method_branches():
    for method, expected in [("rAF", 10), ("high_freq", 7), ("low_freq", 2), ("anything_else", 2)]:
        audit = _perfect_audit()
        audit["smoothness"]["method"] = method
        _, breakdown = calculate_score(audit)
        assert breakdown["motion"] == expected, method


def test_zero_latency_bonus_changes_total():
    with_bonus, _ = calculate_score(_perfect_audit())
    audit = _perfect_audit()
    audit["smoothness"]["zero_latency_init"] = False
    without_bonus, _ = calculate_score(audit)
    # bonus weight is 1.0 in the final formula
    assert round(with_bonus - without_bonus, 2) == 1.0


def test_weighting_formula():
    """Pin the exact weighted-sum formula with an asymmetric audit."""
    audit = {
        "time": {"hour_continuous": True},          # 2.5 raw
        "visual": {"has_shadows": True},             # 2.0 raw
        "dial": {"hour_ticks_count": 12},            # 2.0 raw
        "code": {"is_responsive": True},             # 3.0 raw
        "smoothness": {"method": "high_freq"},       # 7 motion, no bonus
    }
    score, breakdown = calculate_score(audit)
    expected = (
        breakdown["time"] * 0.3
        + breakdown["visual"] * 0.2
        + breakdown["dial"] * 0.15
        + breakdown["code"] * 0.15
        + breakdown["motion"] * 0.1
    )
    assert score == round(expected, 2)
