"""Tests for runner.static_precheck — deterministic regex detection that
intentionally overrides the LLM judge for three objective fields.
"""
from benchmark_system.runner import static_precheck


def test_raf_detected():
    html = "<script>function tick(){ requestAnimationFrame(tick); } tick();</script>"
    assert static_precheck(html)["method"] == "rAF"


def test_high_freq_interval():
    html = "<script>setInterval(update, 50);</script>"
    assert static_precheck(html)["method"] == "high_freq"


def test_low_freq_interval():
    html = "<script>setInterval(update, 1000);</script>"
    assert static_precheck(html)["method"] == "low_freq"


def test_no_timer_defaults_to_low_freq():
    html = "<script>update();</script>"
    assert static_precheck(html)["method"] == "low_freq"


def test_multiple_intervals_pick_minimum():
    html = "<script>setInterval(a, 1000); setInterval(b, 40);</script>"
    assert static_precheck(html)["method"] == "high_freq"


def test_raf_wins_over_interval():
    html = "<script>setInterval(a, 1000); requestAnimationFrame(b);</script>"
    assert static_precheck(html)["method"] == "rAF"


def test_interval_exactly_100_is_low_freq():
    html = "<script>setInterval(update, 100);</script>"
    assert static_precheck(html)["method"] == "low_freq"


def test_zero_dependencies_inline_only():
    html = "<html><script>const x = 1;</script><style>body{}</style></html>"
    assert static_precheck(html)["zero_dependencies"] is True


def test_external_script_breaks_zero_dependencies():
    html = '<script src="app.js"></script>'
    assert static_precheck(html)["zero_dependencies"] is False


def test_cdn_breaks_zero_dependencies():
    for host in ["cdn.example.com", "googleapis.com", "unpkg.com", "jsdelivr.net", "cloudflare.com"]:
        html = f'<link href="https://{host}/x.css">'
        assert static_precheck(html)["zero_dependencies"] is False, host


def test_ms_precision_detected_case_insensitive():
    assert static_precheck("d.getMilliseconds()")["second_ms_precision"] is True
    assert static_precheck("d.getmilliseconds()")["second_ms_precision"] is True


def test_ms_precision_absent():
    assert static_precheck("d.getSeconds()")["second_ms_precision"] is False
