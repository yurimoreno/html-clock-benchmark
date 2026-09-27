"""Second judge: a vision model looks at the rendered clock, not the source.

Jev reads code; this judge sees pixels. Different inputs mean different blind
spots, which is the point of having two. It answers only the six questions a
picture settles well: hand tails, center cap, bezel, hour ticks, minute ticks,
numerals. Shadows and gradients are subtle in a screenshot and are measured
instead (measure.py); "minute ticks skipped at the hours" is invisible when a
tick is drawn under another, so it stays with Jev.

When Jev and this judge disagree, tiebreak() asks the same local model a third
time, reading the source instead of the picture.

Default model: the local qwen3.8-flash-next on gx10 :8888 (free, has vision).
Override with VISION_JUDGE_URL / VISION_JUDGE_MODEL.
"""

import base64
import datetime
import json
import os
from zoneinfo import ZoneInfo

import requests

URL = os.getenv("VISION_JUDGE_URL", "http://localhost:8888/v1/chat/completions")
MODEL = os.getenv("VISION_JUDGE_MODEL", "qwen3.8-flash-next")

# field -> question. Counts are asked as yes/no thresholds, matching calculate_score.
QUESTIONS = {
    "visual.has_hand_tails": "Does at least one hand extend past the center pivot on the opposite side, as a short counterweight tail?",
    "visual.has_center_cap": "Is there a distinct round cap, dot or disc covering the point where the hands meet at the center?",
    "visual.has_bezel": "Is there a distinct rim or ring around the dial, visibly separate from the face (a border, case or ring of a different color or width)?",
    "dial.hour_ticks_count": "Are there tick marks at all 12 hour positions around the dial (numerals alone do not count)?",
    "dial.minute_ticks_count": "Are there small minute tick marks between the hour positions all the way around the dial (at least 48)?",
    "dial.numerals_count": "Does the dial show all 12 hour numerals (1 to 12, Arabic or Roman)?",
}

_PROMPT = (
    "You are auditing a rendered analog clock (a screenshot, and a 2x crop of its center). "
    "Answer each question about what is visible, strictly from the images. "
    "Answer true only if you can clearly see it.\n\n"
    + "\n".join(f"- {k}: {q}" for k, q in QUESTIONS.items())
)

_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "boolean"} for k in QUESTIONS},
    "required": list(QUESTIONS),
    "additionalProperties": False,
}


def _screenshots(html):
    """Full view plus a 2x crop around the middle, at a fixed time."""
    from playwright.sync_api import sync_playwright
    try:
        from render_check import BASE, TZ, _browser_path
    except ImportError:
        from benchmark_system.render_check import BASE, TZ, _browser_path
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            browser = p.chromium.launch(executable_path=_browser_path())
        ctx = browser.new_context(viewport={"width": 720, "height": 720}, timezone_id=TZ, device_scale_factor=2)
        page = ctx.new_page()
        page.clock.install(time=BASE.replace(tzinfo=ZoneInfo(TZ)) - datetime.timedelta(seconds=3))
        page.set_content(html, wait_until="load", timeout=15000)
        page.clock.run_for(3000)
        full = page.screenshot(animations="disabled", scale="css")
        crop = page.screenshot(animations="disabled", clip={"x": 180, "y": 180, "width": 360, "height": 360})
        browser.close()
    return full, crop


def judge_screenshot(images):
    content = [{"type": "text", "text": _PROMPT}]
    for img in images:
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + base64.b64encode(img).decode()}})
    r = requests.post(URL, timeout=180, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 400,
        "response_format": {"type": "json_schema", "json_schema": {"name": "clock_audit", "schema": _SCHEMA}},
        "chat_template_kwargs": {"enable_thinking": False},
    })
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


def _agreeing(a, b):
    """Keep only answers both runs gave; the model isn't perfectly repeatable
    even at temperature 0, and an answer that flips shouldn't vote."""
    return {k: v for k, v in a.items() if k in b and b[k] == v}


def vision_judge(html, repeats=2):
    """{field: bool} for the QUESTIONS the model answered the same way every
    time, or None if the judge is unavailable."""
    try:
        images = _screenshots(html)
        answers = judge_screenshot(images)
        for _ in range(repeats - 1):
            answers = _agreeing(answers, judge_screenshot(images))
        return answers
    except Exception as e:
        print(f"  vision judge unavailable: {e}")
        return None


_TIEBREAK_PROMPT = (
    "Below is the complete source of a single-file HTML analog clock. Read it and answer each "
    "question about what the clock draws when it runs. Answer true only if the code clearly "
    "produces it.\n\n{questions}\n\nSOURCE:\n{source}"
)


def tiebreak(html, fields, repeats=2):
    """Third vote on `fields` (a subset of QUESTIONS), from the source code.
    Like vision_judge, only answers that repeat count."""
    first = _tiebreak_once(html, fields)
    for _ in range(repeats - 1):
        if first is None:
            break
        again = _tiebreak_once(html, fields)
        first = _agreeing(first, again) if again is not None else None
    return first


def _tiebreak_once(html, fields):
    schema = {"type": "object", "properties": {k: {"type": "boolean"} for k in fields},
              "required": list(fields), "additionalProperties": False}
    prompt = _TIEBREAK_PROMPT.format(questions="\n".join(f"- {k}: {QUESTIONS[k]}" for k in fields),
                                     source=html[:60000])
    try:
        r = requests.post(URL, timeout=180, json={
            "model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 300,
            "response_format": {"type": "json_schema", "json_schema": {"name": "tiebreak", "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": False},
        })
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"  tie-break unavailable: {e}")
        return None
