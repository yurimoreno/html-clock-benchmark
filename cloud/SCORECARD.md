# HTML Analog Clock Benchmark — Cloud Models

Evaluated 2026-04-28. Same rubric as the local-models scorecard:
Time Accuracy ×3, Visuals ×2, Markers/Numbers ×1.5, Code Quality ×1.5, Smoothness ×1.

| Rank | File | Time | Visuals | Markers | Code | Smooth | **Overall /10** | **Input** | **Output** |
|------|------|------|---------|---------|------|--------|------------------|-----------|------------|
| 1 | glm-5.1.html | 10 | 9 | 10 | 9 | 9 | **9.5** | $1.05/M | $3.50/M |
| 2 | deepseek-v4-pro.html | 10 | 8 | 10 | 10 | 9 | **9.4** | $0.44/M | $0.87/M |
| 3 | opus 4.7.html | 10 | 9 | 9 | 9 | 9 | **9.3** | $5/M | $25/M |
| 4 | kimi k2.5.html | 10 | 9 | 9 | 7 | 9 | **9.0** | $0.44/M | $2/M |
| 5 | sonnet 4.6.html | 10 | 8 | 8 | 9 | 9 | **8.9** | $3/M | $15/M |
| 6 | kimi k2.6.html | 10 | 8 | 9 | 9 | 6 | **8.8** | $0.74/M | $4.66/M |
| 7 | gemini-3.1-pro.html | 10 | 8 | 7 | 7 | 6 | **8.1** | $2/M | $12/M |
| 8 | chatgpt-free.html | 9 | 7 | 8 | 7 | 5 | **7.6** | $1.75/M | $14/M |
| 9 | mimo-2.5-pro.html | 9 | 6 | 7 | 6 | 9 | **7.5** | $1/M | $3/M |
| 10 | qwen-3.6-plus.html | 9 | 6 | 7 | 6 | 5 | **7.1** | $0.325/M | $1.95/M |
| 11 | grok 4.2 expert.html | 8 | 4 | 8 | 7 | 8 | **6.9** | — | — |
| 12 | minimax-m2.7.html | 8 | 7 | 5 | 6 | 5 | **6.6** | $0.30/M | $1.20/M |

For context, the best local model (qwen2.5-coder-14b) scored **7.8** on the same rubric — still ahead of the bottom four cloud entries but behind the top seven.

---

## 1. glm-5.1.html — **9.5/10 (winner of the cloud set)**

What works
- Canvas, 400×400, full `requestAnimationFrame` loop. Smooth seconds.
- Beautiful, complete dial: warm radial gradient face, serif Roman numerals 1–12 properly placed, 12 hour markers, 48 minute markers (with the right ones skipped at hour positions), all with rounded line caps.
- Triangular hour and minute hands drawn as filled polygons with a small tail past the pivot — looks like a real watch.
- Second hand has a thin red sweep with a counterweight circle below the pivot.
- Two-layer center cap (dark outer, red inner), correct math, drawn at `(0, -length)` with `-Math.cos`/`Math.sin` so 12 is at top.

Nothing meaningfully broken. The polish-per-line-of-code ratio is the highest of the lot.

## 2. deepseek-v4-pro.html — **9.4/10**

The only **SVG** entry. Cleanest implementation in the entire benchmark — declarative DOM for face, ticks, and numbers; just transforms applied to three `<line>` elements for the hands.

What works
- `viewBox="-120 -120 240 240"` puts the SVG origin at the clock center, which means tick math, number math, and hand math all rotate around `(0, 0)`. No off-by-eight bugs are even possible. Every element shares the same coordinate frame.
- Tick generation uses `(i * 6 - 90)` (the `-90` to put 12 at top), with inner radius 95 (major) / 100 (minor) and outer 107 — clean shoulders against the bezel.
- Numbers placed at radius 80 with the same `-90` offset. All twelve land where they should.
- Hands are `<line x1="0" y1="0" x2="0" y2="-length"/>` — point straight up at 0° rotation, so the math is `seconds * 6`, `minutes * 6`, `hours * 30` with no offsets needed. Includes ms precision.
- 50 ms refresh, smooth seconds.

What drags it down
- Visuals are tasteful but minimal — flat lines, no gradients, no drop shadows, no triangular polygon hands, no counterweight detail. The face is solid color, not gradiented. That keeps it just behind glm-5.1 on aesthetics; on every other axis it's level or ahead.

If polish is worth a point, glm-5.1 is the winner; if you reward correctness-by-construction, deepseek wins.

## 3. opus 4.7.html — **9.3/10**

What works
- CSS clock with the full kit: numbers 1–12 placed via `cos/sin` (with the −90° offset to put 12 at top), 60 tick marks (12 major), three hands, layered center cap, and a faint "Quartz" brand mark.
- Tick `transform-origin: 50% 176px` is computed exactly to land the rotation pivot at the clock center — every tick orbits cleanly to the rim.
- Hand pattern is the canonical correct one: `bottom: 50%; left: 50%; transform-origin: 50% 100%;` with `margin-left: -halfWidth` and **no** `translateX(-50%)` reapplied in the rotate transform — pivots are exactly at the clock center.
- Correct math everywhere, including ms-precision second hand. 50 ms refresh.

Nothing real to dock. Most "wristwatch-like" of the bunch visually.

## 4. kimi k2.5.html — **9.0/10**

What works
- Numbers 1–12 using the standard parent-rotates / child-counter-rotates trick. 60 tick marks (12 major). Three hands with gradient fills. Glowing teal center dot. Embedded digital readout at the bottom. 50 ms refresh, correct math, smooth seconds with ms precision.

What drags it down
- The 60 tick marks are hand-written as 60 individual `<div>`s in the HTML. Functional, but bloats the file and is the kind of thing every other entry generates in a `for` loop. Code-quality dings rather than correctness.
- `transition: transform 0.05s cubic-bezier(0.4, 2.3, 0.6, 1)` plus a 50 ms timer means the second hand has a faint bouncy overshoot every tick — cute, not strictly accurate.

## 5. sonnet 4.6.html — **8.9/10**

What works
- Canvas, 300×300, `requestAnimationFrame`. Hour markers (with quarter-hour markers thicker), 48 minute markers, three hands with rounded caps and small tails on each, layered red/white center dot. Correct math with ms precision throughout.
- Cleanest, most concise code in the cloud set — the `drawHand(angle, length, width, color)` helper is the right abstraction.

What drags it down
- No numerals on the face — just markers. Visually a bit minimal next to glm-5.1, kimi, and opus.

## 6. kimi k2.6.html — **8.8/10**

Successor to k2.5 — same family of clock, cleaner source, weaker smoothness.

What works
- Dark gradient face with a glowing red bezel, all 12 numerals placed via `sin/cos` (with the canonical `-cos` for the y axis so 12 sits at top), 60 ticks (12 major), three differentiated hands (white hour, teal minute, red second), glowing center dot.
- Tick `transform-origin: 50% 150px` lands the rotation pivot exactly on the (150, 150) clock-face center — no border-box trap because `* { box-sizing }` isn't set, so the face is genuinely 300×300.
- Hand math is correct (`s * 6`, `(m + s/60) * 6`, `((h%12) + m/60) * 30`) and pivots are the canonical `bottom: 50% / left: 50% / transform-origin: bottom center / margin-left: -halfWidth` pattern.
- Clean refactor of k2.5's hand-coded 60 ticks into a `for` loop. Source is much shorter.

What drags it down
- 1 Hz `setInterval` and no ms term in the second-hand math — the second hand snaps each tick. The `transition: transform 0.02s cubic-bezier(0.4, 2.3, 0.6, 1)` softens it slightly, but k2.5's 50 ms smooth sweep is gone. This is a clear regression from the prior version.
- No digital readout or "Analog" brand mark from k2.5 — slightly less visually rich.

## 7. gemini-3.1-pro.html — **8.1/10**

Classic Wes-Bos-style CSS clock — clean white face, thick light bezel, drop shadow, twelve numerals with the standard parent-rotates / child-counter-rotates trick.

What works
- Hand math is correct; the `+ 90` offset matches the geometry (hands extend leftward from the center pivot, so a +90° rotation puts seconds=0 at 12). Verified at 0/15/30/45 sec, midnight, noon, and 3 pm.
- The `cubic-bezier(0.1, 2.7, 0.58, 1)` transition gives the second hand a tasteful overshoot-bounce on each tick — the most "wall-clock-feeling" of any entry.
- Includes the snap-glitch hack: when seconds rolls back from 59 → 0, transitions are zeroed for that frame so hands don't unwind 360°.
- Subtle `translateY(-3px)` on `.clock-face` to compensate for the 6 px hand height landing the bar slightly below center.

What drags it down
- No tick marks at all — only the 12 numerals.
- 1 Hz refresh, no millisecond term — the second hand ticks rather than sweeps. The bounce transition softens it but does not replace a smooth sweep.
- The `translateY(-3px)` compensation is sized for a 6 px hand, but the hour hand is 8 px and the second hand 3 px — the offset isn't uniform across hands. Sub-pixel-to-2-px wobble depending on which hand you measure.
- Number-positioning trick relies on inline-block default text flow, so the digits sit very close to the rim.

## 8. chatgpt-free.html — **7.6/10**

What works
- CSS clock with numbers 1–12, 60 ticks (12 major), three hands, center dot. Correct math for hour and minute. Hands use `translateX(-50%) rotate(...)` *without* a competing margin-left, so pivots are correctly centered.

What's broken / weak
- `setInterval(updateClock, 1000)` and `secondDeg = seconds * 6` (no ms term) — the second hand jumps a full step every second. Functional but jarring next to the smooth competitors.
- The number-positioning trick (just `translateY(12px)` on each span) places the digits much closer to the rim than the canonical pattern; readable, but cramped.

## 9. mimo-2.5-pro.html — **7.5/10**

Looks competitive at first glance — dark navy face inside a glowing red bezel, all 12 numerals, 60 ticks (12 major), correct ms-precision time math, and a `requestAnimationFrame` loop. Hands pivot exactly at the geometric clock center.

What's broken
- A `box-sizing: border-box` / hard-coded-coordinate mismatch. The `.clock` is `width: 320px` with an 8 px border, so the inner content area (and the `.clock-face` inside it) is **304 × 304**, with center at (152, 152). But the JS lays out the dial as if the face were 320 × 320 with center (160, 160):
  - Tick `transform-origin: center 150px` puts the tick rotation pivot at (152, **160**) — 8 px below the actual center.
  - Number positions use `x = 160 + radius * sin(angle) - 15` and `y = 160 - radius * cos(angle) - 15` — the number ring orbits (160, 160), 8 px right and 8 px down from the actual center.
- Net effect: hands rotate around the true center, the tick ring is shifted ~8 px down, and the number ring is shifted ~8 px down-right — the three reference frames don't agree. On a 304 px face that's a ~2.6% asymmetry, visible but not glaring. The fix is one substitution: replace the hard-coded `160` with `clockFace.offsetWidth / 2`.

Otherwise correct, smooth, and well-styled. Strong implementation undone by one off-by-eight bug.

## 10. qwen-3.6-plus.html — **7.1/10**

The same border-box offset bug as mimo-2.5-pro, plus a jumpier second hand.

Setup is clean — light face with dark border, 60 ticks (12 major), 12 numerals, classic red second hand, layered hour/minute hands, correct hand-pivot pattern (`bottom: 50%; left: 50%; transform-origin: bottom center;` with `margin-left: -halfWidth`).

What's broken
- `* { box-sizing: border-box }` plus `.clock { width: 300px; border: 8px solid }` makes the absolutely-positioned-children area **284 × 284** with center at (142, 142), but the JS uses hard-coded 150 throughout:
  - Tick `transform-origin: center 140px` puts the tick rotation pivot at (142, **150**) — 8 px low.
  - Number positions use `x = 150 + r·cos(angle) − 20` and `y = 150 + r·sin(angle) − 20` — number ring orbits (150, 150), 8 px right and 8 px down.
- So hands rotate around (142, 142), the tick ring around (142, 150), and the number ring around (150, 150) — three different centers in one clock, identical to the mimo bug.
- Second hand math is just `s * 6` with **no millisecond term** and a 1 Hz `setInterval`, so the second hand snaps a full step each tick.
- No special handling for the 59→0 rollover, so any future addition of `transition` would unwind 360° at every minute boundary.

Hour math `h * 30 + m * 0.5` uses raw `getHours()` (0–23) instead of `% 12`. It still renders correctly because rotations are mod 360, but it's a smell — at 13:00 you're feeding the browser 390°, not 30°.

Compared to mimo-2.5-pro: same offset bug (slightly larger in proportional terms because the face is smaller), but worse smoothness. That's the gap between the two scores.

## 11. grok 4.2 expert.html — **6.9/10** *(revised down from 7.6)*

The big-bezel 420 px clock looked good on a still inspection of the source, but the rendered output tells a different story: the layout breaks out of its container.

The cause: `.clock-container` is 420×420, but `.clock` inside it has `width: 100%; height: 100%; border: 24px solid` with no `box-sizing: border-box`. The clock's content area is therefore 420×420 *plus* a 48 px border, giving a total visible 468×468. The dark bezel spills out of the 420 px container box on every side. The whole thing is oversized for its own layout context.

This is on top of the bugs I already flagged in the previous pass:
- Hand `transform-origin: 0% 50%` with `top: 50%` puts each pivot half-the-hand's-height **below** the geometric center (2–6 px low).
- The second hand has `animation: pulse 1s infinite linear` — it fades in and out, which is not what a clock does.
- The face background is white inside a clock element with `overflow: hidden` and a circular clip, so the bezel and inner face are visually correct in shape *individually* — but the whole clock occupies a larger frame than intended.

Time math, ticks, numbers, and refresh rate are all fine. Marking down the visual score from 7 to 4 puts the overall in the right neighborhood: above minimax, behind everything else.

## 12. minimax-m2.7.html — **6.6/10**

What works
- Recognizable clock: red bezel, gold second hand, 12 hour markers (with 4 majors), three hands, center dot. Correct time math.

What's broken
- The hand divs already have `margin-left: -halfWidth` for centering, **and** the rotate JS reapplies `translateX(-50%) rotate(...)`. The two centering shifts compound, so each hand's pivot ends up `halfWidth` to the left of the actual clock center. The hour hand pivots ~3 px off; the minute and second hands ~1–2 px. Visible especially as the hands sweep.
- Only 12 hour markers — no minute markers and no numerals.
- 1 Hz refresh, no smooth seconds.

---

## Final cloud ranking

1. **glm-5.1** — best face, best detail (9.5)
2. **deepseek-v4-pro** — only SVG entry; correctness-by-construction, minimal styling (9.4)
3. **opus 4.7** — most polished CSS implementation (9.3)
4. **kimi k2.5** — feature-rich, slightly bloated source (9.0)
5. **sonnet 4.6** — cleanest correct canvas code (8.9)
6. **kimi k2.6** — k2.5 refactored cleaner but with a regression to 1 Hz seconds (8.8)
7. **gemini-3.1-pro** — classic JS30 look with bouncy seconds; correct but no tick marks and 1 Hz refresh (8.1)
8. **chatgpt-free** — correct but visually plain and the second hand jumps (7.6)
9. **mimo-2.5-pro** — dial drawn for 320 px face inside a 304 px box; ticks and numbers off-center from hands (7.5)
10. **qwen-3.6-plus** — same border-box offset bug as mimo, plus a jumpy 1 Hz second hand (7.1)
11. **grok 4.2 expert** — clock breaks out of its container; off-center pivots; pulsing seconds (6.9, revised from 7.6)
12. **minimax-m2.7** — compounded transform bug shifts hands off-center (6.6)

Cross-set note: the strongest local entry (qwen2.5-coder-14b, 7.8) would slot between #7 (gemini) and #8 (chatgpt) here.

*Pricing from openrouter.ai as of 2026-04-28. "—" indicates model not found on OpenRouter at lookup time. grok-4.2-expert was not in the registry under the name used in this benchmark; its cost may differ from the model-family prices shown.*
