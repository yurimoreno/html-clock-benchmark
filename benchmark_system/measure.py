"""Measured answers to rubric questions: run the clock and observe it, instead
of asking a judge to read its source.

Each measurement returns True / False, or None when the observation isn't
clear enough (then the judge's answer stands). What's measured:

  time.correct_12_top          hands at the right angles at known times (render_check)
  time.second_ms_precision     second hand moves between :30.1 and :30.9
  time.minute_continuous       minute hand moves between :05 and :55 of one minute
  time.hour_continuous         hour hand moves between 10:02 and 10:22
  smoothness.zero_latency_init 50 ms after load matches the settled frame
  code.zero_dependencies       no network requests while loading
  code.globals_count           window properties added + top-level names declared
  code.is_responsive           the clock changes size between 320px and 900px viewports
  visual.has_gradients         a gradient is applied (canvas create*Gradient, CSS, or SVG fill)
  visual.has_shadows           a shadow is applied (canvas shadowBlur, CSS box/text/drop-shadow, SVG filter)

The continuity checks look for changed pixels along the expected hand's ray
from the pivot, so they only run when the time check passed (pivot located,
hands where they should be).
"""

import base64
import datetime
import math
import re
from zoneinfo import ZoneInfo

try:
    from render_check import (
        BASE, FRAMES, GRID, SETTLE_MS, SIZE, TZ, _DIFF_JS, _ang, _angdist, _browser_path,
        analyze, hand_angle,
    )
except ImportError:  # imported as benchmark_system.measure
    from benchmark_system.render_check import (
        BASE, FRAMES, GRID, SETTLE_MS, SIZE, TZ, _DIFF_JS, _ang, _angdist, _browser_path,
        analyze, hand_angle,
    )

T = lambda h, m, s, ms=0: datetime.datetime(2026, 1, 1, h, m, s, ms * 1000)

# (field, frame a, frame b, hand whose ray to watch, window half-width in degrees)
CONTINUITY = {
    # same page, 800 ms apart (a fresh page per frame would shift a 1 Hz timer's phase)
    "time.second_ms_precision": (T(10, 8, 30, 100), T(10, 8, 30, 900), "second"),
    "time.minute_continuous": (T(10, 8, 5), T(10, 8, 55), "minute"),
    "time.hour_continuous": (T(10, 2, 0), T(10, 22, 0), "hour"),
}
INIT_TIME = T(10, 8, 30, 500)  # mid-second, so a 1 Hz clock shows :30 in both frames
RESPONSIVE_SIZES = (320, 900)

_GLOBAL_PROBE_JS = """
([names, baseline]) => {
  const base = new Set(baseline);
  const ours = k => !base.has(k) && !k.startsWith('__pw') && k !== '__clockPaint';  // our own probes
  // var, function and implicit globals are own enumerable properties of window.
  // (Elements with an id are reachable as window.<id> too, but through the
  // prototype chain, so they don't show up here.)
  const added = Object.keys(window).filter(ours);
  // Top-level let/const/class live in the global lexical scope, not on window.
  // Redeclaring one with `let` in a fresh <script> throws "already been
  // declared" only if it really is a global binding.
  const lexical = names.filter(n => {
    if (!ours(n) || added.includes(n)) return false;
    let dup = false;
    const onErr = e => { if (/already been declared/.test(e.message || '')) dup = true; };
    window.addEventListener('error', onErr);
    const s = document.createElement('script');
    s.textContent = 'let ' + n + ';';
    document.head.appendChild(s); s.remove();
    window.removeEventListener('error', onErr);
    return dup;
  });
  return added.concat(lexical);
}
"""
# Runs before the page's own scripts: records canvas gradient/shadow use.
_CANVAS_SPY_JS = """
(() => {
  const used = window.__clockPaint = { gradient: 0, shadow: 0 };
  const P = CanvasRenderingContext2D.prototype;
  for (const f of ['createLinearGradient', 'createRadialGradient', 'createConicGradient']) {
    const orig = P[f];
    if (orig) P[f] = function (...a) { used.gradient++; return orig.apply(this, a); };
  }
  const d = Object.getOwnPropertyDescriptor(P, 'shadowBlur');
  Object.defineProperty(P, 'shadowBlur', { get() { return d.get.call(this); },
    set(v) { if (v > 0) used.shadow++; d.set.call(this, v); } });
  const c = Object.getOwnPropertyDescriptor(P, 'shadowColor');
  Object.defineProperty(P, 'shadowColor', { get() { return c.get.call(this); },
    set(v) { c.set.call(this, v); } });
})();
"""

# After load: which shadow/gradient effects are actually applied to rendered elements.
_PAINT_PROBE_JS = r"""
() => {
  const used = window.__clockPaint || { gradient: 0, shadow: 0 };
  const out = { canvasGradient: used.gradient, canvasShadow: used.shadow,
                cssGradient: 0, cssShadow: 0, svgGradient: 0, svgShadow: 0 };
  for (const el of document.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    for (const pseudo of [cs, getComputedStyle(el, '::before'), getComputedStyle(el, '::after')]) {
      if (/gradient\(/.test(pseudo.backgroundImage) || /gradient\(/.test(pseudo.borderImageSource)) out.cssGradient++;
      if ((pseudo.boxShadow && pseudo.boxShadow !== 'none') || (pseudo.textShadow && pseudo.textShadow !== 'none')
          || /drop-shadow/.test(pseudo.filter)) out.cssShadow++;
    }
    const fill = (cs.fill || '') + (cs.stroke || '');
    if (/url\(/.test(fill)) {
      const id = (fill.match(/url\(["']?#([^"')]+)/) || [])[1];
      const ref = id && document.getElementById(id);
      if (ref && /gradient/i.test(ref.tagName)) out.svgGradient++;
    }
    if (/url\(/.test(cs.filter || '')) {
      const id = (cs.filter.match(/url\(["']?#([^"')]+)/) || [])[1];
      const ref = id && document.getElementById(id);
      if (ref && ref.querySelector('feDropShadow, feGaussianBlur, feOffset')) out.svgShadow++;
    }
  }
  return out;
}
"""

_DECL_RE = re.compile(r"\b(?:var|let|const|function\*?|class)\s+([A-Za-z_$][\w$]*)")


def _moved_along(points, pivot, angles, half_width=6, min_points=4):
    """Changed pixels lying on the rays at `angles` (degrees) from the pivot."""
    cx, cy = pivot
    n = 0
    for x, y in points:
        dx, dy = x - cx, y - cy
        if dx * dx + dy * dy < 16:
            continue
        a = _ang(dx, dy)
        if any(_angdist(a, t) <= half_width for t in angles):
            n += 1
    return n >= min_points, n


def continuity_verdict(field, points, pivot):
    a, b, hand = CONTINUITY[field]
    start, end = hand_angle(a, hand), hand_angle(b, hand)
    # watch the arc the hand would sweep if it moves continuously
    steps = max(2, int(_angdist(start, end) / 3) + 1)
    arc = [(start + (end - start) * i / (steps - 1)) % 360 for i in range(steps)]
    moved, n = _moved_along(points, pivot, arc)
    if moved:
        return True, f"{n} px changed along the {hand} hand's path"
    if not points:
        # nothing at all changed; for the ms check that is exactly the failure
        # (page is known to be live: the time check passed)
        return False, f"nothing changed; the {hand} hand stayed put"
    others = len(points)
    return False, f"{others} px changed elsewhere but none along the {hand} hand's path"


def responsive_verdict(extents):
    small, large = extents
    if not small or not large:
        return None, "second hand not found at both sizes"
    ratio = large / small
    return ratio > 1.15, f"second-hand sweep {small:.0f}px at {RESPONSIVE_SIZES[0]}w vs {large:.0f}px at {RESPONSIVE_SIZES[1]}w"


def _extent(points, size):
    if len(points) < 5:
        return None
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    return max(max(xs) - min(xs), max(ys) - min(ys)) * size / GRID


def measure_clock(html, repeats=2):
    """Measure the clock `repeats` times; an answer counts only if every run
    gives the same one. Some pages still depend on real time somewhere (an
    infinite CSS animation, an async resize), and a flaky measurement must
    never override the judge, so disagreement between runs means None.
    Returns {"time": render_check result, "fields": {field: {"value", "evidence"}}}."""
    runs = [_measure_once(html) for _ in range(repeats)]
    first = runs[0]
    time_oks = {r["time"].get("ok") for r in runs}
    time = dict(first["time"])
    if len(time_oks) > 1:
        time.update(ok=None, reason="not reproducible across runs: " + ", ".join(map(str, sorted(time_oks, key=str))))
    fields = {}
    for field in first["fields"]:
        values = [r["fields"].get(field, {}).get("value") for r in runs]
        if all(v == values[0] for v in values):
            fields[field] = first["fields"][field]
        else:
            fields[field] = {"value": None, "evidence": "not reproducible across runs: " + ", ".join(map(str, values))}
    return {"time": time, "fields": fields, "repeats": repeats}


def _measure_once(html):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"time": {"ok": None, "reason": "playwright not installed", "hands": {}}, "fields": {}}
    fields = {}

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                path = _browser_path()
                if not path:
                    raise
                browser = p.chromium.launch(executable_path=path)

            def shot(t, size=SIZE, settle=SETTLE_MS, track=None, spy=False):
                ctx = browser.new_context(viewport={"width": size, "height": size}, timezone_id=TZ)
                page = ctx.new_page()
                if track is not None:
                    page.on("request", lambda r: track.append(r.url))
                start = t.replace(tzinfo=ZoneInfo(TZ)) - datetime.timedelta(milliseconds=settle)
                page.clock.install(time=start)
                if spy:
                    # a real navigation, so the spy runs before the page's scripts
                    page.add_init_script(_CANVAS_SPY_JS)
                    page.route("http://clock.local/", lambda r: r.fulfill(body=html, content_type="text/html"))
                    page.goto("http://clock.local/", wait_until="load", timeout=15000)
                else:
                    page.set_content(html, wait_until="load", timeout=15000)
                page.clock.run_for(settle)
                img = "data:image/png;base64," + base64.b64encode(page.screenshot(animations="disabled")).decode()
                return ctx, page, img

            def keep(t, **kw):
                ctx, _, img = shot(t, **kw)
                ctx.close()
                return img

            differ = browser.new_page()
            diff = lambda a, b: [tuple(pt) for pt in differ.evaluate(_DIFF_JS, [a, b, GRID])]

            # 1. dependencies + globals on one live page
            requests = []
            ctx, page, base_img = shot(BASE, track=requests, spy=True)
            external = sorted({u for u in requests if not u.startswith(("data:", "about:", "blob:", "http://clock.local/"))})
            fields["code.zero_dependencies"] = {
                "value": not external,
                "evidence": "no network requests" if not external else "loads " + ", ".join(external[:3])}
            blank = browser.new_page()
            baseline = blank.evaluate("Object.keys(window)")
            blank.close()
            names = sorted(set(_DECL_RE.findall(re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I))))
            try:
                leaked = page.evaluate(_GLOBAL_PROBE_JS, [names, baseline])
                fields["code.globals_count"] = {
                    "value": len(leaked),
                    "evidence": f"{len(leaked)} global(s)" + (": " + ", ".join(leaked[:6]) if leaked else "")}
            except Exception as e:
                fields["code.globals_count"] = {"value": None, "evidence": f"probe failed: {e}"}
            try:
                paint = page.evaluate(_PAINT_PROBE_JS)
                g = paint["canvasGradient"] + paint["cssGradient"] + paint["svgGradient"]
                sh = paint["canvasShadow"] + paint["cssShadow"] + paint["svgShadow"]
                detail = ", ".join(f"{k} {v}" for k, v in paint.items() if v)
                fields["visual.has_gradients"] = {"value": g > 0, "evidence": f"gradients applied: {g}" + (f" ({detail})" if detail else "")}
                fields["visual.has_shadows"] = {"value": sh > 0, "evidence": f"shadows applied: {sh}" + (f" ({detail})" if detail else "")}
            except Exception as e:
                for f in ("visual.has_gradients", "visual.has_shadows"):
                    fields[f] = {"value": None, "evidence": f"paint probe failed: {e}"}
            ctx.close()

            # 2. time check (render_check's frames)
            time_diffs = {hand: diff(base_img, keep(t)) for hand, t in FRAMES.items()}
            time_result = analyze(time_diffs)

            # 3. continuity checks need the located pivot and a clock showing the right time
            pivot = time_result.get("pivot")
            for field, (a, b, _) in CONTINUITY.items():
                if time_result.get("ok") is not True:
                    fields[field] = {"value": None, "evidence": "skipped: time check not passed"}
                    continue
                if field == "time.second_ms_precision":
                    ctx, page, first = shot(a)
                    page.clock.run_for(int((b - a).total_seconds() * 1000))
                    second = "data:image/png;base64," + base64.b64encode(page.screenshot(animations="disabled")).decode()
                    ctx.close()
                    pts = diff(first, second)
                else:
                    pts = diff(keep(a), keep(b))
                value, evidence = continuity_verdict(field, pts, pivot)
                fields[field] = {"value": value, "evidence": evidence}

            # 4. first frame: 50 ms after load vs fully settled, same wall time
            if time_result.get("ok") is True:
                early = keep(INIT_TIME, settle=50)
                settled = keep(INIT_TIME)
                pts = diff(early, settled)
                hands_now = [hand_angle(INIT_TIME, h) for h in ("hour", "minute", "second")]
                on_hands, n = _moved_along(pts, pivot, hands_now, half_width=8)
                # A hand that's missing or at 12:00 on the first frame changes about as
                # many pixels as a real hand movement; redraw/antialias noise along
                # the hands changes far fewer. Scale against the second hand's 90° move.
                reference = len(time_diffs["second"])
                if len(pts) < 5 or n < 0.25 * reference:
                    fields["smoothness.zero_latency_init"] = {
                        "value": True, "evidence": f"first frame already shows the time ({n} px of noise vs {reference} for a real move)"}
                elif on_hands and n / len(pts) > 0.5:
                    fields["smoothness.zero_latency_init"] = {"value": False, "evidence": "hands not in place 50 ms after load"}
                else:
                    fields["smoothness.zero_latency_init"] = {"value": None, "evidence": "first frame differs, but not only at the hands (intro animation?)"}
            else:
                fields["smoothness.zero_latency_init"] = {"value": None, "evidence": "skipped: time check not passed"}

            # 5. responsive: does the second hand's sweep change size with the viewport?
            extents = []
            for size in RESPONSIVE_SIZES:
                a = keep(BASE, size=size)
                b = keep(FRAMES["second"], size=size)
                extents.append(_extent(diff(a, b), size))
            value, evidence = responsive_verdict(extents)
            fields["code.is_responsive"] = {"value": value, "evidence": evidence}

            browser.close()
    except Exception as e:  # measuring is best-effort; never block judging
        return {"time": {"ok": None, "reason": f"render failed: {e}", "hands": {}}, "fields": fields}
    return {"time": time_result, "fields": fields}
