"""Tests for the small pure formatting/grading helpers in add_model.py and
runner.py. These feed the published leaderboard, so boundary behaviour matters.
"""
from add_model import score_to_grade, _cost_eff_class, _fmt_price
from benchmark_system.runner import _fmt_run_date


def test_score_to_grade_boundaries():
    assert score_to_grade(9.0) == ("s-1", "b-1")
    assert score_to_grade(8.99) == ("s-2", "b-2")
    assert score_to_grade(8.5) == ("s-2", "b-2")
    assert score_to_grade(8.49) == ("s-3", "b-3")
    assert score_to_grade(8.0) == ("s-3", "b-3")
    assert score_to_grade(7.99) == ("s-4", "b-4")
    assert score_to_grade(7.0) == ("s-4", "b-4")
    assert score_to_grade(6.99) == ("s-5", "b-5")
    assert score_to_grade(0) == ("s-5", "b-5")


def test_cost_eff_class():
    assert _cost_eff_class(None) == "cost-eff"
    assert _cost_eff_class(0.40) == "cost-eff green"
    assert _cost_eff_class(0.80) == "cost-eff yellow"
    assert _cost_eff_class(0.81) == "cost-eff red"


def test_fmt_price():
    assert _fmt_price(None) == "—"
    assert _fmt_price(5.0) == "$5/M"
    assert _fmt_price(5.5) == "$5.5/M"


def test_fmt_run_date_valid():
    assert _fmt_run_date("20260428_230837") == "Apr 28"


def test_fmt_run_date_invalid_falls_back():
    assert _fmt_run_date("not-a-date") == "—"
    assert _fmt_run_date("") == "—"
