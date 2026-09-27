"""Tests for the card verdict under each clock preview: the dimension cells and
the Earned/Lost summary generated from the audit."""
import re
from add_model import dims_html, why_html, make_verdict
from benchmark_system.runner import calculate_score

PERFECT = {
    "time": {"hour_continuous": True, "minute_continuous": True,
             "second_ms_precision": True, "correct_12_top": True},
    "visual": {"has_shadows": True, "has_gradients": True, "has_hand_tails": True,
               "has_center_cap": True, "has_bezel": True},
    "dial": {"hour_ticks_count": 12, "minute_ticks_count": 60, "numerals_count": 12,
             "automated_marker_generation": True, "skips_minute_at_hour": True},
    "code": {"globals_count": 0, "is_responsive": True, "uses_helpers": True,
             "zero_dependencies": True},
    "smoothness": {"method": "rAF", "zero_latency_init": True},
}


def _flawed():
    import copy
    a = copy.deepcopy(PERFECT)
    a["code"]["is_responsive"] = False
    a["dial"]["numerals_count"] = 0
    a["smoothness"]["method"] = "low_freq"
    return a


def test_perfect_audit_loses_nothing():
    assert "Lost nothing" in why_html(PERFECT)


def test_lost_total_matches_score():
    a = _flawed()
    score, _ = calculate_score(a)
    lost = float(re.search(r"<b>Lost ([\d.]+):</b>", why_html(a)).group(1))
    assert round(10 - score, 2) == lost


def test_losses_sorted_by_cost():
    text = why_html(_flawed()).lower()
    assert text.index("ticks once a second") < text.index("fixed size") < text.index("no numerals")


def test_dims_cells_classes():
    html = dims_html({"time": 10.0, "visual": 8.0, "dial": 2.0, "code": 7.5, "motion": 10})
    assert re.findall(r'class="dim (\w+)"><span>\w+</span><b>([\d.]+)</b>', html) == [
        ("good", "10"), ("warn", "8"), ("bad", "2"), ("warn", "7.5"), ("good", "10")]


def test_verdict_meta_omits_missing_fields():
    html = make_verdict(calculate_score(PERFECT)[1], PERFECT, model_id="x/a", run_date="20260101_000000")
    assert 'class="model-id">x/a<' in html and "Ran Jan 1" in html
    assert "Latency" not in html and "Cost" not in html


def test_cost_floor_is_html_tokens_at_output_price():
    from add_model import estimate_cost, fmt_cost
    html = "x" * 3300  # ~1000 tokens
    cost = estimate_cost(html, {"input_per_m": 0.0, "output_per_m": 10.0})
    assert cost == 0.01
    assert fmt_cost(cost, estimated=True) == "≥$0.0100"
    assert fmt_cost(cost) == "$0.0100"
    assert estimate_cost(html, None) is None
