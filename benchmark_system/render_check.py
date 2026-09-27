"""Rendered time check: does the clock actually show the right time?

The judges read source code, so a clock whose math *looks* right can still
point its hands the wrong way (e.g. applying the -90° "12 at the top" offset
to hands that are already drawn pointing up). This module renders the clock
in headless Chromium with the time frozen and measures where the hands point.

Method: render four frames that differ in exactly one hand's position —
    base      10:08:30
    +15 s     10:08:45   (second hand moves 90°)
    +15 min   10:23:30   (minute hand moves 90°)
    +3 h      01:08:30   (hour hand moves 90°)
Diffing base against each frame isolates one hand at two known angles. The
pivot is the point from which the changed pixels are most concentrated along
a few rays; the angular histogram around it then gives each hand's measured
angle, which is compared to the expected one.

Only an unambiguous result overrides the judge: if a hand can't be found
(no diff, too much noise), the check returns ok=None and the judge's own
answer stands.
"""

import datetime
import glob
import math
import os

TZ = "America/Los_Angeles"
BASE = datetime.datetime(2026, 1, 1, 10, 8, 30)
FRAMES = {
    "second": BASE + datetime.timedelta(seconds=15),
    "minute": BASE + datetime.timedelta(minutes=15),
    "hour": BASE + datetime.timedelta(hours=3),
}
SIZE = 480           # viewport px
GRID = 200           # analysis resolution (px)
TOLERANCE = 20.0     # degrees a measured hand may be off (the bugs this catches are 90°+)
SETTLE_MS = 3000     # let intro animations finish before capturing

# Decode two screenshots in the page, diff them, and return changed pixels on
# a GRID x GRID raster. Doing this in the browser avoids numpy/Pillow.
_DIFF_JS = """
async ([a, b, grid]) => {
  const load = src => new Promise(r => { const i = new Image(); i.onload = () => r(i); i.src = src; });
  const [ia, ib] = await Promise.all([load(a), load(b)]);
  const px = img => {
    const c = document.createElement('canvas'); c.width = grid; c.height = grid;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0, grid, grid);
    return g.getImageData(0, 0, grid, grid).data;
  };
  const da = px(ia), db = px(ib), out = [];
  for (let i = 0; i < da.length; i += 4) {
    const d = Math.abs(da[i]-db[i]) + Math.abs(da[i+1]-db[i+1]) + Math.abs(da[i+2]-db[i+2]);
    if (d > 60) { const p = i / 4; out.push([p % grid, Math.floor(p / grid)]); }
  }
  return out;
}
"""


def hand_angle(t, hand):
    """Clockwise degrees from 12 o'clock for a hand at wall time t."""
    s = t.second + t.microsecond / 1e6
    m = t.minute + s / 60
    h = (t.hour % 12) + m / 60
    return {"second": s * 6, "minute": m * 6, "hour": h * 30}[hand] % 360


def _ang(dx, dy):
    return math.degrees(math.atan2(dx, -dy)) % 360


def _angdist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def hough_lines(points, n=4, grid=GRID):
    """The n strongest straight lines through `points`, as (theta_deg, rho, votes)."""
    cos = [math.cos(math.radians(t)) for t in range(180)]
    sin = [math.sin(math.radians(t)) for t in range(180)]
    off = 2 * grid
    acc = {}
    for x, y in points:
        for t in range(180):
            key = (t, int(round(x * cos[t] + y * sin[t])) + off)
            acc[key] = acc.get(key, 0) + 1
    lines = []
    for _ in range(n):
        if not acc:
            break
        (t, r), votes = max(acc.items(), key=lambda kv: kv[1])
        if votes < 5:
            break
        lines.append((t, r - off, votes))
        # suppress near-duplicates (same hand, slightly different fit)
        for key in [k for k in acc if min(abs(k[0] - t), 180 - abs(k[0] - t)) <= 10 and abs(k[1] - r) <= 8]:
            del acc[key]
    return lines


def _intersect(l1, l2):
    (t1, r1, _), (t2, r2, _) = l1, l2
    a1, b1 = math.cos(math.radians(t1)), math.sin(math.radians(t1))
    a2, b2 = math.cos(math.radians(t2)), math.sin(math.radians(t2))
    det = a1 * b2 - a2 * b1
    if abs(det) < 0.3:  # nearly parallel: no reliable crossing
        return None
    return ((r1 * b2 - r2 * b1) / det, (a1 * r2 - a2 * r1) / det)


def find_pivot(diffs, max_points=800):
    """Each diff shows one hand at two positions 90° apart (rotation and
    mirroring preserve that, so it holds for broken clocks too). Among the
    strongest lines, take the best-supported pair that is ~90° apart; they
    cross at the pivot. Other changing content, like a digital readout, rarely
    forms such a pair. Median over the three diffs."""
    xs, ys = [], []
    for pts in diffs.values():
        if len(pts) < 5:
            continue
        pts = pts if len(pts) <= max_points else pts[:: len(pts) // max_points + 1]
        lines = hough_lines(pts)
        pairs = [(a[2] + b[2], a, b) for i, a in enumerate(lines) for b in lines[i + 1:]
                 if abs(min(abs(a[0] - b[0]), 180 - abs(a[0] - b[0])) - 90) <= 15]
        if pairs:
            _, a, b = max(pairs)
            c = _intersect(a, b)
            if c:
                xs.append(c[0]); ys.append(c[1])
    if len(xs) < 2:
        return None
    px, py = sorted(xs)[len(xs) // 2], sorted(ys)[len(ys) // 2]
    # the diffs must agree on where the pivot is, or one of them is noise
    agree = sum(math.hypot(x - px, y - py) <= GRID * 0.07 for x, y in zip(xs, ys))
    return (px, py) if agree >= 2 else None


def ray_peaks(points, pivot, bins=72, n=2):
    """The n strongest ray directions (degrees) from pivot, with their share of points."""
    cx, cy = pivot
    hist = [0.0] * bins
    total = 0
    for x, y in points:
        dx, dy = x - cx, y - cy
        r2 = dx * dx + dy * dy
        if r2 < 9:
            continue
        hist[int(_ang(dx, dy) / 360 * bins) % bins] += 1
        total += 1
    if not total:
        return []
    # smooth over neighbours so a hand straddling two bins is one peak
    sm = [hist[i - 1] + hist[i] + hist[(i + 1) % bins] for i in range(bins)]
    peaks = []
    for _ in range(n):
        i = max(range(bins), key=lambda k: sm[k])
        if sm[i] <= 0:
            break
        peaks.append(((i + 0.5) * 360 / bins, sm[i] / total))
        for k in range(-3, 4):  # suppress ±15° around the peak
            sm[(i + k) % bins] = 0
    return peaks


def analyze(diffs):
    """diffs: {hand: [(x, y), ...]} changed pixels between base and that hand's frame.
    Returns {"ok": True/False/None, "hands": {...}, "pivot": (x, y)}."""
    union = [p for pts in diffs.values() for p in pts]
    if len(union) < 20:
        return {"ok": None, "reason": "no hand movement detected", "hands": {}}
    pivot = find_pivot(diffs)
    if pivot is None:
        return {"ok": None, "reason": "could not locate the pivot", "hands": {}}
    hands, verdicts = {}, []
    for hand, pts in diffs.items():
        expected = sorted([hand_angle(BASE, hand), hand_angle(FRAMES[hand], hand)])
        # Top four rays: the other hands shift slightly between frames too
        # (the minute hand moves 1.5° in 15 s), leaving thin slivers in the diff.
        peaks = [a for a, share in ray_peaks(pts, pivot, bins=144, n=4) if share >= 0.06]
        # A hand that was really isolated shows up as two rays 90° apart; if no
        # such pair exists the diff is only slivers/noise (e.g. a hand too close
        # to the background colour), so this hand is inconclusive, not wrong.
        paired = any(abs(_angdist(a, b) - 90) <= 12 for i, a in enumerate(peaks) for b in peaks[i + 1:])
        if len(pts) < 5 or not paired:
            hands[hand] = {"expected": expected, "measured": sorted(round(a, 1) for a in peaks) or None}
            verdicts.append(None)
            continue
        err = max(min(_angdist(e, a) for a in peaks) for e in expected)
        hands[hand] = {"expected": [round(a, 1) for a in expected],
                       "measured": sorted(round(a, 1) for a in peaks), "error": round(err, 1)}
        verdicts.append(err <= TOLERANCE)
    if False in verdicts:
        ok = False
    elif verdicts and all(v is True for v in verdicts):
        ok = True
    else:
        ok = None
    return {"ok": ok, "hands": hands, "pivot": pivot}


def _browser_path():
    for pat in ("/opt/pw-browsers/chromium*/chrome-linux/chrome",
                os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell"),
                os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    return None


def check_rendered_time(html):
    """Render `html` at the four frames and analyze. Returns the analyze() dict,
    or {"ok": None, "reason": ...} when rendering isn't possible."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": None, "reason": "playwright not installed", "hands": {}}
    import base64
    from zoneinfo import ZoneInfo
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception:
                path = _browser_path()
                if not path:
                    raise
                browser = p.chromium.launch(executable_path=path)
            shots = {}
            for name, t in [("base", BASE), *FRAMES.items()]:
                ctx = browser.new_context(viewport={"width": SIZE, "height": SIZE}, timezone_id=TZ)
                page = ctx.new_page()
                start = t.replace(tzinfo=ZoneInfo(TZ)) - datetime.timedelta(milliseconds=SETTLE_MS)
                page.clock.install(time=start)
                page.set_content(html, wait_until="load", timeout=15000)
                page.clock.run_for(SETTLE_MS)
                shots[name] = "data:image/png;base64," + base64.b64encode(page.screenshot(animations="disabled")).decode()
                ctx.close()
            page = browser.new_page()
            diffs = {hand: [tuple(pt) for pt in page.evaluate(_DIFF_JS, [shots["base"], shots[hand], GRID])]
                     for hand in FRAMES}
            browser.close()
    except Exception as e:  # rendering is best-effort; never block judging
        return {"ok": None, "reason": f"render failed: {e}", "hands": {}}
    return analyze(diffs)
