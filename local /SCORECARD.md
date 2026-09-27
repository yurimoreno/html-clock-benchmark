# HTML Analog Clock Benchmark — Judge's Scorecard

Evaluated 2026-04-28; qwen3.8-flash-next added 2026-09-26 (TypeSafe Jev judge + vision second judge + browser render check). Rubric: each clock scored 0–10 across five dimensions, with a weighted overall.

Scores re-judged 2026-09-26 with the same pipeline as the cloud tab (`rejudge_local.py`: TypeSafe Jev, vision second judge, browser render check). The per-clock notes below are the original reviews and keep their original scores.

Machines: the 2026-04 entries ran in LM Studio on the Mac Mini M2 Pro (quantizations in the index.html Machine column). qwen3.8-flash-next ran on the GX10 under vLLM 0.30 with the bilikaz/qwen38-flash-next-recipe; its exact server build is in `qwen3.8-flash-next.build.json`. claude-sonnet-5 was written in a Claude Code session, not by a local model.

| Rank | File | Time Accuracy (×3) | Visuals (×2) | Markers/Face (×1.5) | Code Quality (×1.5) | Smoothness (×1) | **Overall /10** |
|------|------|---------------------|--------------|----------------------|---------------------|-----------------|------------------|
| 1 | claude-sonnet-5.html | 10 | 10 | 10 | 10 | 10 | **10.0** |
| 2 | qwen3.8-flash-next.html | 10 | 10 | 8 | 4 | 10 | **8.8** |
| 3 | gemma-4-e4b.html | 7.5 | 6 | 0 | 8 | 7 | **6.35** |
| 4 | glm-4.6v-flash.html | 5 | 4 | 8 | 2 | 10 | **5.8** |
| 5 | qwen3.5-9b.html | 10 | 6 | 0 | 2 | 2 | **5.7** |
| 6 | gemma-4-e4b-uncensored-hauhaucs-aggressive.html | 7.5 | 6 | 2 | 2 | 2 | **5.25** |
| 7 | qwen2.5-coder-14b.html | 7.5 | 0 | 8 | 2 | 2 | **4.95** |
| 8 | lfm2.5-1.2b.html | 2.5 | 2 | 0 | 5 | 2 | **2.1** |

---

## Original reviews

## 1. claude-sonnet-5.html — **10.0/10 — not a fair comparison, see caveat**

Added 2026-09-01. Every other entry on this page is a **blind** one-shot generation — the model never saw the grading rubric. This one didn't come from a locally-hosted model at all: the local model server (`deepseek-v4-flash-0731`) was tied up, so this file was written directly by Claude Sonnet 5 inside a Claude Code session, **with the full `JUDGE_V1.md` rubric already in context**. It legitimately satisfies every checked criterion (verified line-by-line, not rubber-stamped) — continuous hour/minute/ms-precision time math, correct 12-at-top offset, gradient bezel + face + drop shadow, hand tails, a distinct center cap, exactly 12 hour ticks + 48 minute ticks + 12 numerals via loops (no manual duplication, minute ticks skip the hour positions), zero leaked globals (IIFE), viewport-relative sizing, helper-function decomposition, zero external dependencies, and a `requestAnimationFrame` loop whose first paint already reflects the real time. Kept as a **reference/upper-bound** entry, not a leaderboard-topping result — a real head-to-head needs a model that hasn't seen the answer key.

## 2. qwen3.8-flash-next.html — **8.8/10 — best blind entry**

Added 2026-09-26, blind one-shot against the local vLLM serve (`qwen3.8-flash-next`, hibrid48-uncensored). Built in 17s with 37 reasoning tokens: a plain 400px canvas clock with 12 numerals and 60 ticks drawn in loops, a `requestAnimationFrame` loop with `getMilliseconds()` precision, and correct time from the first frame. The browser render check confirmed the hands point right at frozen times. Zero dependencies.

What it lost: code quality (4/10). The canvas is fixed at 400px and doesn't scale, it leaks a handful of globals, and the minute ticks are drawn over the hour positions.

Note on the first attempt: the server's chat template was injecting a "Reasoning effort is set to xhigh" system prompt that no other entry gets. That run spent ~7,200 reasoning tokens and 6.5 minutes on a 38 KB watch-station dashboard that scored ~7.0 with unverifiable time. The template default was fixed to add nothing, and this entry is the rerun with the bare prompt.

## 3. qwen2.5-coder-14b.html — **7.8/10 — best timekeeping of the older models**

**The first clock in the benchmark that gets *everything* about timekeeping right.**

What works
- Clean canvas implementation using the canonical `save / translate / rotate / draw / restore` pattern. Hour ticks, minute ticks, and all three hands rotate around the true center (150, 150).
- Correct orientation: hands and ticks are drawn at `(0, -length)` so untransformed they point straight up (12 o'clock) — no 90° rotation bug.
- Correct rotational math:
  - Hour: `(π/6) · h + (π/360) · m` → 30°/hour + 0.5°/minute. The `0 → 12` correction is applied (`hours = hours ? hours : 12`).
  - Minute: `(π/30) · m + (π/1800) · s` → 6°/min + 0.1°/sec.
  - Second: `(π/30) · s` → 6°/sec.
- All twelve hour ticks AND the 48 minute ticks are correctly positioned around the dial — no other clock in the benchmark managed both.
- Second hand has a small tail past the pivot, classic clock detail.

What's broken / weak
- No center pivot dot. Hand bases just meet at a point on a flat black-and-white face.
- `setInterval(drawClock, 1000)` — the second hand ticks once per second, no smooth sweep.
- Visually plain: white face, black ticks, black hour/minute hands, red second hand. No shadows, no numerals, no bezel.
- Minor: line widths are set on hands but never reset before drawing the face/ticks, so the *first* frame's ticks render with whatever lineWidth happened to be at canvas init (1px). Cosmetically fine, but slightly leaky.

## 4. gemma-4-e4b-uncensored-hauhaucs-aggressive.html — **6.5/10**

Only other clock that tells time correctly. Hands pivot at true center, math is right. Hour markers are broken — all stacked at 12 because the CSS `rotate()` is applied without a `translateY()` to push them to the rim, and only 4 of 12 nth-child rules are even defined.

## 5. gemma-4-e4b.html — **5.4/10**

Cleanest code of the CSS entries, smooth 50ms loop, correct rotation formulas. But hand geometry puts the pivot ~20px above the actual clock center, so hands orbit instead of rotate. No markers.

## 6. glm-4.6v-flash.html — **5.1/10**

Most complete face among the runners-up — full hour and minute ticks, three hands, smooth `requestAnimationFrame` loop. But Math.cos/sin angle 0 = 3 o'clock in canvas coordinates and the code never offsets by π/2, so the **entire dial is rotated 90° clockwise**. At 12:00 sharp the hour hand points right.

## 7. qwen3.5-9b.html — **4.6/10**

Prettiest dial (dark blue background, white face with bezel, "12" numeral, drop shadow). But the hour-hand formula `((h*30)+(m/2)) % (360/12) * 12` collapses the hour position — at 3:00 it computes 0° instead of 90°. JS `transform = rotate(...)` also overrides the base `translateX(-50%)`, so hands sit half-width to the right of center.

## 8. lfm2.5-1.2b.html — **0.7/10**

Non-functional. Hands have no defined size; JS sets `width` from the time value (so hand "length" grows over the day), height stays 0. Empty white circle.

---

## Final ranking

1. **claude-sonnet-5** — reference entry, generated with the rubric in-context; not a blind comparison.
2. **qwen3.8-flash-next** — best blind entry; correct and verified in the browser, loses on code quality.
3. **gemma-4-e4b** — correct continuous time, clean code; no dial markers.
4. **glm-4.6v-flash** — complete face and smooth motion; hands measured wrong in the browser.
5. **qwen3.5-9b** — judged correct on time, but the browser check couldn't find its hour hand and the original review found broken hour math.
6. **gemma-4-e4b-uncensored-hauhaucs-aggressive** — correct time, broken markers, ticking second hand.
7. **qwen2.5-coder-14b** — correct time verified in the browser; plain visuals, ticking second hand, fixed size.
8. **lfm2.5-1.2b** — does not function as a clock.
