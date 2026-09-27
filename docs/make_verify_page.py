#!/usr/bin/env python3
"""Build docs/verify.html: one clock worked end to end, for a one-time human
check of the judging method. Every rubric question with how it was answered
(measured / two judges / code), the evidence, each vote and the final answer.

Usage: python docs/make_verify_page.py previews/<clock>.html
"""
import base64
import datetime
import html as H
import json
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "benchmark_system"))
from render_check import BASE, TZ, _browser_path  # noqa: E402
from vision_judge import QUESTIONS as VISION_FIELDS  # noqa: E402

QUESTIONS = [
    ("Time", "time.hour_continuous", "Hour hand moves continuously (not jumping each hour)"),
    ("Time", "time.minute_continuous", "Minute hand moves continuously"),
    ("Time", "time.second_ms_precision", "Second hand uses millisecond precision"),
    ("Time", "time.correct_12_top", "Hands show the right time (12 at the top)"),
    ("Visual", "visual.has_shadows", "Shadows"),
    ("Visual", "visual.has_gradients", "Gradients"),
    ("Visual", "visual.has_hand_tails", "Hand tails past the pivot"),
    ("Visual", "visual.has_center_cap", "Center cap over the pivot"),
    ("Visual", "visual.has_bezel", "Bezel / rim"),
    ("Dial", "dial.hour_ticks_count", "12 hour ticks"),
    ("Dial", "dial.minute_ticks_count", "Minute ticks (48+)"),
    ("Dial", "dial.numerals_count", "12 numerals"),
    ("Dial", "dial.automated_marker_generation", "Markers generated in a loop"),
    ("Dial", "dial.skips_minute_at_hour", "Minute ticks skip the hour positions"),
    ("Code", "code.globals_count", "2 or fewer leaked globals"),
    ("Code", "code.is_responsive", "Resizes with the window"),
    ("Code", "code.uses_helpers", "Helper functions"),
    ("Code", "code.zero_dependencies", "No external dependencies"),
    ("Motion", "smoothness.method", "Update method (rAF / fast interval / 1 Hz)"),
    ("Motion", "smoothness.zero_latency_init", "Right time on the very first frame"),
]
THRESH = {"hour_ticks_count": 12, "minute_ticks_count": 48, "numerals_count": 12}


def as_bool(key, v):
    if key == "globals_count":
        return None if v is None else v <= 2
    if key in THRESH:
        return (v or 0) >= THRESH[key]
    return v


def fmt(v):
    if v is True:
        return '<span class="y">yes</span>'
    if v is False:
        return '<span class="n">no</span>'
    return "—" if v is None else H.escape(str(v))


def screenshot(src):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=_browser_path())
        ctx = b.new_context(viewport={"width": 480, "height": 480}, timezone_id=TZ)
        pg = ctx.new_page()
        pg.clock.install(time=BASE.replace(tzinfo=ZoneInfo(TZ)) - datetime.timedelta(seconds=3))
        pg.set_content(open(os.path.join(ROOT, src)).read(), wait_until="load")
        pg.clock.run_for(3000)
        img = pg.screenshot(animations="disabled")
        b.close()
    return base64.b64encode(img).decode()


def main(src):
    audit = json.load(open(os.path.join(ROOT, "audits.json")))[src]
    measured = audit.get("measured") or {}
    votes = audit.get("votes") or {}
    original = audit.get("judge_answers") or {}
    rows = []
    for dim, field, label in QUESTIONS:
        sec, key = field.split(".")
        final = audit.get(sec, {}).get(key)
        jev = original.get(field, final)
        m = measured.get(field)
        v = votes.get(field)
        if m and m.get("value") is not None:
            how, evidence = "Measured", m.get("evidence", "")
        elif v and "vision" in v:
            how = "Two judges" + (" + tie-break" if v.get("tiebreak") is not None else "")
            evidence = f"Jev (code): {'yes' if v['jev'] else 'no'} · Qwen (screenshot): {'yes' if v['vision'] else 'no'}"
            if v.get("tiebreak") is not None:
                evidence += f" · Qwen (code, tie-break): {'yes' if v['tiebreak'] else 'no'}"
        elif field == "smoothness.method":
            how, evidence = "Code check", "regex: requestAnimationFrame / setInterval interval"
        elif field in VISION_FIELDS:
            how, evidence = "Jev (code)", "screenshot judge gave different answers on two runs, so it abstained"
        elif m:
            how, evidence = "Jev (code)", f"measurement inconclusive ({m.get('evidence', '')}); judge's answer stands"
        else:
            how, evidence = "Jev (code)", "no measurement or picture can settle this; code judge only"
        fb = final if key == "method" else as_bool(key, final)
        jb = jev if key == "method" else as_bool(key, jev)
        changed = ' class="changed"' if jb != fb else ""
        rows.append(f"<tr{changed}><td>{dim}</td><td>{H.escape(label)}</td><td>{how}</td>"
                    f"<td>{H.escape(evidence)}</td><td>{fmt(jb)}</td><td><b>{fmt(fb)}</b></td></tr>")
    img = screenshot(src)
    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Judge Method Check</title><style>
:root{{--bg:#fafafa;--fg:#1a1a1a;--mut:#666;--line:#ddd;--y:#2e7d32;--n:#c0392b;--hl:#fff4d6}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#1a1a1a;--fg:#eee;--mut:#999;--line:#333;--y:#7ab86a;--n:#e07a6a;--hl:#3a3220}}}}
:root[data-theme="dark"]{{--bg:#1a1a1a;--fg:#eee;--mut:#999;--line:#333;--y:#7ab86a;--n:#e07a6a;--hl:#3a3220}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:var(--mut);margin:0 0 16px}}
.top{{display:flex;gap:20px;flex-wrap:wrap;align-items:flex-start}} img{{width:280px;max-width:100%;border:1px solid var(--line);border-radius:8px}}
.wrap{{overflow-x:auto;flex:1;min-width:300px}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}} th{{color:var(--mut);font-weight:600}}
.y{{color:var(--y)}} .n{{color:var(--n)}} tr.changed td{{background:var(--hl)}}
</style></head><body><main>
<h1>Judge method check — {H.escape(os.path.basename(src))}</h1>
<p>Clock frozen at 10:08:30. Each rubric question, how it was answered, the evidence, the first judge's (Jev) answer and the final one. Highlighted rows are where the final answer differs from Jev's.</p>
<div class="top"><img src="data:image/png;base64,{img}" alt="clock at 10:08:30">
<div class="wrap"><table><thead><tr><th>Dim</th><th>Question</th><th>Answered by</th><th>Evidence</th><th>Jev</th><th>Final</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></div></main></body></html>"""
    out = os.path.join(ROOT, "docs", "verify.html")
    open(out, "w").write(page)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
