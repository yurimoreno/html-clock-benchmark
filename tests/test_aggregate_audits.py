"""Tests for runner._aggregate_audits — merges N judge runs to reduce LLM
variance: majority vote for booleans, median for ints, mode for strings.
"""
from benchmark_system.runner import _aggregate_audits


def test_boolean_majority_vote():
    audits = [
        {"time": {"hour_continuous": True}},
        {"time": {"hour_continuous": True}},
        {"time": {"hour_continuous": False}},
    ]
    assert _aggregate_audits(audits)["time"]["hour_continuous"] is True


def test_boolean_strict_majority_loses_on_tie():
    audits = [
        {"time": {"hour_continuous": True}},
        {"time": {"hour_continuous": False}},
    ]
    # sum(True) == 1 is not > len/2 == 1.0, so result is False
    assert _aggregate_audits(audits)["time"]["hour_continuous"] is False


def test_integer_median():
    audits = [
        {"dial": {"hour_ticks_count": 12}},
        {"dial": {"hour_ticks_count": 12}},
        {"dial": {"hour_ticks_count": 60}},
    ]
    assert _aggregate_audits(audits)["dial"]["hour_ticks_count"] == 12


def test_integer_median_truncates_even_count():
    audits = [
        {"dial": {"hour_ticks_count": 1}},
        {"dial": {"hour_ticks_count": 2}},
    ]
    # median is 1.5, cast to int => 1
    assert _aggregate_audits(audits)["dial"]["hour_ticks_count"] == 1


def test_string_mode():
    audits = [
        {"smoothness": {"method": "rAF"}},
        {"smoothness": {"method": "rAF"}},
        {"smoothness": {"method": "low_freq"}},
    ]
    assert _aggregate_audits(audits)["smoothness"]["method"] == "rAF"


def test_ragged_fields_are_unioned():
    audits = [
        {"time": {"hour_continuous": True}},
        {"time": {"minute_continuous": True}},
    ]
    result = _aggregate_audits(audits)
    # Each field present in only one run; single value passes through.
    assert result["time"]["hour_continuous"] is True
    assert result["time"]["minute_continuous"] is True


def test_ragged_sections_are_unioned():
    audits = [
        {"time": {"hour_continuous": True}},
        {"code": {"is_responsive": True}},
    ]
    result = _aggregate_audits(audits)
    assert result["time"]["hour_continuous"] is True
    assert result["code"]["is_responsive"] is True
