"""TypeSafe (System One / Jev) alternative judge for the HTML Clock Benchmark.

Instead of a generative LLM audit, this asks Jev one narrow Noul question per
semantic rubric criterion over the clock's HTML source (the "state"), then
assembles an Audit JSON dict that is byte-compatible with the schema in
JUDGE_V1.md, so runner.calculate_score() works on it unchanged.

Deterministic fields (`smoothness.method`, `code.zero_dependencies`,
`time.second_ms_precision`) are NOT asked of Jev: they come from
runner.static_precheck(), exactly as evaluate_clock() overrides them.

Count fields are expressed as threshold Nouls (Jev is weak at counting), so the
emitted ints only need to satisfy the thresholds calculate_score uses.
"""

import time

from dotenv import load_dotenv

from typesafe_sdk import Noul, TypeSafeClient

from runner import static_precheck

load_dotenv()

import os

TYPESAFE_MODEL = "jev-latest"
DEFAULT_THRESHOLD = 0.5

# Noul question id -> "section.field" (ids are plain dotted names; the same key
# is reused verbatim in the `typesafe_probs` map).
NOUL_QUESTIONS = {
    # --- A. Time Accuracy ---
    "time.hour_continuous": Noul(
        instructions=(
            "In the clock's JavaScript, the hour-hand angle formula includes a fractional "
            "minutes term, i.e. it is of the form hours*30 + minutes/60*30 (or equivalently "
            "hours*30 + minutes*0.5), so the hour hand moves continuously between whole hours."
        ),
        criteria={
            "true": (
                "The hour-hand computation adds a minutes-derived fraction (minutes/60 or "
                "minutes*0.5 or (minutes/60)*30) to the hour part."
            ),
            "false": (
                "The hour-hand angle uses only the whole-hour value (hours*30 with no minutes "
                "fraction), or no hour-hand angle is computed."
            ),
        },
    ),
    "time.minute_continuous": Noul(
        instructions=(
            "In the clock's JavaScript, the minute-hand angle formula includes a fractional "
            "seconds term, i.e. minutes*6 + seconds/60*6 (or minutes*6 + seconds*0.1), so the "
            "minute hand moves continuously between whole minutes."
        ),
        criteria={
            "true": (
                "The minute-hand computation adds a seconds-derived fraction (seconds/60 or "
                "seconds*0.1) to the minute part."
            ),
            "false": (
                "The minute-hand angle uses only the whole-minute value (minutes*6 with no "
                "seconds fraction), or no minute-hand angle is computed."
            ),
        },
    ),
    "time.correct_12_top": Noul(
        instructions=(
            "The clock face is drawn so that numeral 12 sits at the top of the circle: the "
            "marker/numeral angle offsets start at the top (e.g. angle 0 or -90 degrees, or "
            "index*30 degrees measured with a -90 degree rotation), so 12 is up, 3 right, 6 bottom."
        ),
        criteria={
            "true": (
                "Numeral/marker placement puts 12 at the 12 o'clock (top) position, e.g. via a "
                "-90 degree start offset or rotate(0deg) at the top."
            ),
            "false": (
                "12 is not at the top (e.g. numbering starts at the right/3 o'clock position with "
                "no -90 correction), or numerals are absent/unplaced."
            ),
        },
    ),
    # --- B. Visual Depth ---
    "visual.has_shadows": Noul(
        instructions=(
            "The stylesheet or canvas drawing uses a shadow primitive: a CSS box-shadow, "
            "drop-shadow(), text-shadow, or a canvas shadowBlur/shadowColor setting."
        ),
        criteria={
            "true": "At least one of box-shadow, drop-shadow(), text-shadow or shadowBlur appears.",
            "false": "None of those shadow primitives appear.",
        },
    ),
    "visual.has_gradients": Noul(
        instructions=(
            "The clock is painted with a gradient: a CSS radial-gradient(...) or linear-gradient(...) "
            "background, or a canvas gradient created with createRadialGradient/createLinearGradient/"
            "createConicGradient and used as a fill style."
        ),
        criteria={
            "true": (
                "At least one gradient (CSS radial-gradient/linear-gradient/conic-gradient or the "
                "canvas create*Gradient API) is defined and applied."
            ),
            "false": "No gradient function is used; only flat solid colors.",
        },
    ),
    "visual.has_hand_tails": Noul(
        instructions=(
            "The clock hands extend past the central pivot as a counterweight tail: a hand "
            "element is drawn/positioned so part of it lies on the opposite side of the center "
            "(e.g. a length that overshoots the pivot, a negative offset, or an extra tail element)."
        ),
        criteria={
            "true": "A hand visibly overshoots the pivot on the opposite side of the dial.",
            "false": "All hands stop at the center with no overshooting tail.",
        },
    ),
    "visual.has_center_cap": Noul(
        instructions=(
            "There is a distinct small visual element covering the pivot at the exact center of "
            "the dial, such as a circle/dot element or an arc/point drawn at the center."
        ),
        criteria={
            "true": "A separate central dot/circle/arc element exists at the pivot.",
            "false": "No distinct element is drawn at the pivot point.",
        },
    ),
    "visual.has_bezel": Noul(
        instructions=(
            "The clock has a rim (bezel) around the dial: a CSS border or outline on the clock "
            "circle, or a separate ring element / outer circle whose radius differs from the face."
        ),
        criteria={
            "true": (
                "A border, outline, or separate ring/circle forms the rim around the numbered face."
            ),
            "false": (
                "The dial is one flat circle/background with no border, outline, or ring at its edge."
            ),
        },
    ),
    # --- C. Markers & Numbers (count Nouls + two booleans) ---
    "dial.hour_ticks_count": Noul(
        instructions=(
            "The dial has a marker at each of the 12 hour positions that is distinguishable from "
            "any minute markers. This is satisfied by a loop of 12 hour ticks, OR by a single loop "
            "of 60 ticks where every 5th index (i % 5 === 0) is drawn longer, thicker, or in a "
            "different colour as a major/hour tick, OR by 12 explicit hour-marker elements."
        ),
        criteria={
            "true": (
                "Hour positions carry their own distinct marker: a 12-iteration tick loop, a "
                "60-iteration loop with an i % 5 === 0 major-tick branch, or 12 literal hour ticks."
            ),
            "false": (
                "No hour markers exist, only numerals with no tick marks, or a tick loop with no "
                "distinction at the hour positions."
            ),
        },
    ),
    "dial.minute_ticks_count": Noul(
        instructions="The clock renders minute markers between the hours (48 or 60 total).",
        criteria={
            "true": "Minute markers fill the gaps between hour markers, totalling 48 or 60.",
            "false": "Minute markers are missing or do not reach the 48-60 range.",
        },
    ),
    "dial.numerals_count": Noul(
        instructions=(
            "The clock face shows all 12 numerals 1-12 (or their Roman equivalents I-XII)."
        ),
        criteria={
            "true": "Every hour position carries its numeral label, 1 through 12.",
            "false": "Some hour positions have no numeral label.",
        },
    ),
    "dial.automated_marker_generation": Noul(
        instructions=(
            "The hour/minute markers and numerals are generated by code rather than hand-written: "
            "a loop or programmatic construction (for-loop, map/reduce over an array) creates the "
            "marker elements, instead of one literal HTML element per marker."
        ),
        criteria={
            "true": "A loop or programmatic builder produces the markers/numerals.",
            "false": "Each marker/numeral is listed as its own literal HTML element.",
        },
    ),
    "dial.skips_minute_at_hour": Noul(
        instructions=(
            "Minute markers are omitted at the positions already occupied by hour markers: the "
            "minute-marker loop skips indexes that are a multiple of 5 (e.g. `if (i % 5 === 0) continue`)."
        ),
        criteria={
            "true": "The code explicitly skips minute markers at hour positions.",
            "false": "Minute markers are drawn at every position including the hour positions.",
        },
    ),
    # --- D. Code Architecture ---
    "code.globals_count": Noul(
        instructions=(
            "The script leaks at most 2 identifiers into the global scope (everything else is "
            "inside a function, IIFE, module, class, or block)."
        ),
        criteria={
            "true": (
                "Two or fewer top-level declarations exist, e.g. one IIFE plus at most one other "
                "top-level const/let/var."
            ),
            "false": "Three or more top-level identifiers are declared.",
        },
    ),
    "code.is_responsive": Noul(
        instructions=(
            "The clock size and centering are not hard-coded pixel constants: sizes use relative "
            "units or are derived from the drawing surface (%, em, rem, vw/vh, min(), aspect-ratio, "
            "or the canvas width/height read at runtime)."
        ),
        criteria={
            "true": "Sizing/positioning relies on relative or runtime-derived units.",
            "false": "Fixed px values set the clock size and centering.",
        },
    ),
    "code.uses_helpers": Noul(
        instructions=(
            "The code factors repeated work into helper functions, such as a function that "
            "computes an angle or draws one hand/marker set, called more than once."
        ),
        criteria={
            "true": "At least one named helper function is defined and used for the drawing logic.",
            "false": "All logic sits inline with no helper abstraction.",
        },
    ),
    # --- E. Motion (only the first-frame bonus is asked of Jev) ---
    "smoothness.zero_latency_init": Noul(
        instructions=(
            "The clock is painted with the real current time on the very first render, i.e. the "
            "draw/update function is invoked once immediately (or requestAnimationFrame is started "
            "with the real time) instead of waiting for the first timer tick, so there is no "
            "12:00 snap-in on load."
        ),
        criteria={
            "true": "The render path runs once immediately with the current time at startup.",
            "false": "The clock shows a default 12:00 frame until the first timer tick fires.",
        },
    ),
}


def _call_system_one(client, state, questions):
    """One system_one call with a short bounded retry for 429/529 style errors."""
    from typesafe_sdk import TypeSafeRateLimitError, TypeSafeInternalServerError

    delay = 0.4
    last_error = None
    for attempt in range(4):
        try:
            return client.system_one(state, questions)
        except (TypeSafeRateLimitError, TypeSafeInternalServerError) as e:
            last_error = e
            time.sleep(delay)
            delay *= 2
    raise last_error


def evaluate_clock_typesafe(clock_code, threshold=DEFAULT_THRESHOLD):
    """Audit one clock HTML source with TypeSafe Jev (System One).

    Returns an Audit JSON dict (JUDGE_V1.md schema) plus two extra keys that
    calculate_score() ignores: `typesafe_probs` and `typesafe_model`.
    """
    if not clock_code:
        return None

    precheck = static_precheck(clock_code)

    with TypeSafeClient(api_key=os.getenv("TYPESAFE_API_KEY")) as client:
        result = _call_system_one(client, clock_code, NOUL_QUESTIONS)

    answers = result.raw_http_response.json().get("answers", {})

    def _noul(qid):
        entry = answers.get(qid) or {}
        value = entry.get("noul")
        return value if isinstance(value, (int, float)) else 0.0

    def _yes(qid):
        return _noul(qid) >= threshold

    probs = {qid: _noul(qid) for qid in NOUL_QUESTIONS}

    audit = {
        "time": {
            "hour_continuous": _yes("time.hour_continuous"),
            "minute_continuous": _yes("time.minute_continuous"),
            # Deterministic regex only (upgraded to True when found), same as evaluate_clock.
            "second_ms_precision": bool(precheck["second_ms_precision"]),
            "correct_12_top": _yes("time.correct_12_top"),
        },
        "visual": {
            "has_shadows": _yes("visual.has_shadows"),
            "has_gradients": _yes("visual.has_gradients"),
            "has_hand_tails": _yes("visual.has_hand_tails"),
            "has_center_cap": _yes("visual.has_center_cap"),
            "has_bezel": _yes("visual.has_bezel"),
        },
        "dial": {
            # Count fields as thresholded Nouls -> ints that satisfy calculate_score's
            # >=12 / >=48 / >=12 checks (0 when the Noul says no).
            "hour_ticks_count": 12 if _yes("dial.hour_ticks_count") else 0,
            "minute_ticks_count": 60 if _yes("dial.minute_ticks_count") else 0,
            "numerals_count": 12 if _yes("dial.numerals_count") else 0,
            "automated_marker_generation": _yes("dial.automated_marker_generation"),
            "skips_minute_at_hour": _yes("dial.skips_minute_at_hour"),
        },
        "code": {
            # <=2 check: 0 when the "at most 2 globals" Noul says yes, 99 otherwise.
            "globals_count": 0 if _yes("code.globals_count") else 99,
            "is_responsive": _yes("code.is_responsive"),
            "uses_helpers": _yes("code.uses_helpers"),
            # Deterministic regex override, same as evaluate_clock.
            "zero_dependencies": bool(precheck["zero_dependencies"]),
        },
        "smoothness": {
            # Deterministic regex override, same as evaluate_clock.
            "method": precheck["method"],
            "zero_latency_init": _yes("smoothness.zero_latency_init"),
        },
    }

    audit["typesafe_probs"] = probs
    audit["typesafe_model"] = result.raw_http_response.json().get("model") or TYPESAFE_MODEL
    if result.usage is not None:
        audit["typesafe_usage"] = result.usage.model_dump()
    return audit
