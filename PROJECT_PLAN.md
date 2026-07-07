# Project Plan: Clock Bench v2 — Reproducible, Runtime-Verified Benchmark Platform

> **Context (the instantiated prompt).** I'm working on the **HTML Analog Clock Benchmark** — a public
> leaderboard that gives frontier LLMs one identical one-shot prompt and scores the resulting clock —
> **for anyone evaluating LLM coding ability**, because a simple-but-revealing task with a fixed rubric
> is more trustworthy than vibes, *but only if the scoring itself is trustworthy and reproducible*.
> **Current state:** working v1 pipeline (`benchmark_system/runner.py` + `add_model.py`) with an LLM
> judge, static regex prechecks, a unit-test suite, and a hand-maintained static leaderboard mutated by
> regex. **Constraints:** Python 3.11+, all model calls via OpenRouter, leaderboard stays a static site
> (GitHub Pages compatible), zero-cost idle (no servers required), one maintainer, existing `runs/`
> data must not be invalidated. **Goal:** a complete, implementation-ready plan to evolve this into a
> benchmark whose scores are runtime-verified, statistically grounded, and regenerated from a single
> data source — executable step-by-step with minimal further clarification.

---

## 1. Executive Summary

Clock Bench v1 works, but its credibility ceiling is low for four structural reasons, all visible in
the code today:

1. **The judge never runs the clock.** Scoring is a static code audit by an LLM
   (`runner.py:evaluate_clock`) plus three regex prechecks (`runner.py:static_precheck`). A clock
   that *mentions* `requestAnimationFrame` and `getMilliseconds()` but renders a blank page can
   outscore a working clock. Nothing measures whether the hands point at the right angles.
2. **The leaderboard's source of truth is HTML.** `add_model.py:update_index` splices table rows and
   cards into `index.html` with regex, and *re-parses scores back out of the HTML* to re-rank. Data
   lives in presentation. One markup change silently breaks inserts; historical data is scattered
   across `runs/<ts>/summary.json` files and the HTML itself.
3. **The rubric is triplicated.** Weights and criteria live in `benchmark_system/JUDGE_V1.md`
   (injected into the judge prompt), the root `JUDGE_V1.md` copy, and hardcoded constants in
   `runner.py:calculate_score`. They must be hand-synchronized; drift is undetectable.
4. **Single-sample scoring.** One generation per model, judged by one judge model (3 aggregated
   runs). Generation variance — often larger than the gap between adjacent leaderboard ranks — is
   never measured.

**The plan:** five phases over ~8–10 weeks of part-time effort. Phase 1 extracts all leaderboard data
into a canonical `results.json` and replaces regex splicing with a deterministic site generator.
Phase 2 adds a Playwright-based **runtime verifier** that loads each clock at a mocked, fixed time
and measures actual hand angles, motion method, and first-frame accuracy — converting the
highest-weight rubric criteria from LLM opinion to ground truth. Phase 3 makes the rubric
machine-readable (one `rubric.json` generating both the judge prompt and the scoring code) and
upgrades the judge to an ensemble scoped only to genuinely subjective criteria. Phase 4 adds
multi-sample generation with score distributions and confidence intervals. Phase 5 automates the
whole flow as GitHub Actions (add-a-model via workflow dispatch, site deploy via Pages).

Each phase ships independently and leaves the system working; v1 behavior is preserved behind the
existing CLIs throughout.

---

## 2. Success Criteria

The project is **done** when all of the following hold, each with a concrete verification step:

| # | Criterion | How to verify |
|---|-----------|---------------|
| S1 | `results.json` is the single source of truth; `index.html` is 100% generated. | Delete `index.html`, run `python build_site.py`, diff against committed version → byte-identical. CI enforces this ("generated file is stale" check). |
| S2 | Runtime verification produces deterministic scores for the time/motion criteria. | Run the verifier twice on every file in `cloud/` and `previews/` → identical verdicts both runs. A deliberately broken clock (hands frozen at 12:00) scores 0 on time accuracy regardless of what its source code claims. |
| S3 | Rubric is single-sourced. | `grep`-able: no weight constant appears in more than one file. Changing a weight in `rubric.json` changes both the judge prompt and the computed score with no other edit. A CI test regenerates the judge spec from `rubric.json` and fails on drift. |
| S4 | Every leaderboard entry has ≥3 independent generations with mean ± CI displayed. | Leaderboard shows `7.8 ± 0.4 (n=3)` style scores; `results.json` stores all samples, not just the aggregate. |
| S5 | Adding a model requires zero local setup. | Trigger the `add-model` GitHub Action with a model ID → PR appears with the new entry, screenshots, and regenerated site; merging it updates GitHub Pages. |
| S6 | Existing data survives. | Every model currently on the cloud leaderboard appears in `results.json` with its v1 score preserved and flagged `"scoring_version": 1`. |
| S7 | Tests and CI stay green. | `pytest tests/ -v` passes on 3.11 and 3.12 at every phase boundary (existing `.github/workflows/tests.yml`). |

**Non-goals (explicitly out of scope):** multi-prompt benchmark suites (other widgets), user-submitted
entries, a hosted backend (Flask `server.py` stays optional/local-only), and re-scoring the `local `
tab's hand-curated entries (they remain manual, clearly labeled as such).

---

## 3. Phases & Milestones

| Phase | Milestone | Depends on | Effort (focused days) |
|-------|-----------|------------|----------------------|
| 0 | Decisions locked, migration snapshot taken | — | 0.5 |
| 1 | **Data layer**: `results.json` + `build_site.py`; regex splicing deleted | 0 | 3–4 |
| 2 | **Runtime verifier**: Playwright harness measuring real clock behavior | 0 (parallel with 1) | 5–7 |
| 3 | **Rubric v2**: machine-readable rubric, judge ensemble, JUDGE_V2 | 1, 2 | 3–4 |
| 4 | **Statistics**: multi-sample generation, CIs, re-benchmark top models | 3 | 2–3 |
| 5 | **Automation**: GitHub Actions add-model flow + Pages deploy | 1 (fully useful after 4) | 2–3 |
| — | Buffer / re-benchmarking existing leaderboard under v2 | 4 | 3–5 |

Total: **~19–27 focused days**, realistically 8–10 calendar weeks part-time.

---

## 4. Phase 0 — Groundwork & Decisions (0.5 days)

### Description
Lock the decisions that everything downstream depends on, and snapshot current state so migration is
verifiable.

### Tasks
1. **Tag the repo** (`git tag v1-final`) so the pre-migration leaderboard is always recoverable.
2. **Freeze a golden corpus**: copy every HTML clock currently in `cloud/`, `previews/`, and
   `runs/*/` into `tests/fixtures/corpus/` (they're small). This corpus drives regression tests for
   the verifier and the migration. Include at least one known-broken file (create one) and one
   canvas-based clock.
3. **Decisions to lock now** (defaults recommended below in §9):
   - D1: Scoring version policy — v1 scores kept alongside v2, or full re-benchmark? → *Keep both;
     display v2, badge v1-only entries.*
   - D2: Verifier's authority — does runtime measurement override the judge on overlapping fields
     (like `static_precheck` does today) or replace those fields entirely? → *Replace entirely.*
   - D3: Where generated site data lives — `results.json` committed at repo root. → *Yes, committed;
     it IS the benchmark record.*

### Risks
None material; this phase exists to de-risk the rest.

---

## 5. Phase 1 — Data Layer & Site Generator (3–4 days)

### Description
Extract all leaderboard data into a canonical `results.json`; replace `update_index()`'s regex
splicing with a template-driven site generator. This is the highest leverage-to-risk ratio phase:
pure refactor, no scoring changes, and it unblocks Phases 3–5.

### Prerequisites
Phase 0 snapshot. No API keys needed (works offline on existing data).

### Task 1.1 — Define the schema and write the migration script
**Effort: 1 day. Complexity: medium (one-time parsing of hand-edited HTML).**

`results.json` schema (versioned from day one):

```json
{
  "schema_version": 2,
  "prompt": "Generate a single HTML file that displays a working analog clock...",
  "entries": [
    {
      "model_id": "anthropic/claude-opus-4.7",
      "display_name": "Anthropic Opus 4.7",
      "tab": "cloud",
      "scoring_version": 1,
      "samples": [
        {
          "run_id": "20260428_230837",
          "html_file": "previews/anthropic_claude-opus-4.7.html",
          "score": 9.2,
          "breakdown": {"time": 10, "visual": 8, "dial": 6, "code": 8, "motion": 10},
          "audit": { "...": "verbatim judge audit JSON" },
          "runtime": null,
          "judge_model": "anthropic/claude-3.7-sonnet",
          "judge_runs": 3,
          "latency_s": 41.2,
          "token_usage": {"prompt_tokens": 28, "completion_tokens": 2141},
          "actual_cost": 0.0182,
          "pricing": {"input_per_m": 15.0, "output_per_m": 75.0}
        }
      ],
      "aggregate": {"score_mean": 9.2, "score_ci95": null, "n": 1}
    }
  ]
}
```

**Migration** (`scripts/migrate_v1.py`, one-shot, kept in repo for auditability):
- Parse the existing `<table id="cloud-table">` tbody rows out of `index.html` — the same regexes
  `update_index()` already uses (`add_model.py:242-252`) prove this is parseable.
- Join against `runs/*/summary.json` and `runs/*/summary_eval_*.json` where model IDs match, to
  recover full audits, pricing, and token usage; fall back to HTML-only fields (score, breakdown,
  rank) where no summary exists.
- Emit `results.json`; print a reconciliation report (entries recovered fully / partially).
- **Verification:** entry count in `results.json` equals row count in the current cloud table; every
  score matches the HTML to 2 decimals.

Key decision: **`display_name` is stored, not recomputed** — `model_display_name()`'s OpenRouter
lookup (`add_model.py:76`) is a network call with mutable results; freeze names at insert time.

### Task 1.2 — Build `build_site.py`
**Effort: 1.5 days. Complexity: medium.**

- Split the current `index.html` into a **Jinja2 template** (`site/templates/index.html.j2`): keep
  all existing CSS/JS/tabs verbatim; replace only the cloud tbody and cloud card grid with
  `{% for %}` loops. The `local ` tab's content becomes a literal `{% include %}` block edited by
  hand, exactly as today (per CLAUDE.md, only the cloud tab is programmatic).
- Move row/card formatting logic (`_make_table_row`, `_make_card`, `score_to_grade`,
  `_cost_eff_class`, `_fmt_price`, `_fmt_run_date`) into a `site/render.py` module — the existing
  tests in `tests/test_formatters.py` and `tests/test_update_index.py` migrate with them.
- `python build_site.py` reads `results.json` → writes `index.html`. Sorting and rank numbering
  happen in Python on structured data, deleting the score-re-parsing regex dance entirely.
- Preview copying (currently inside `_make_card`, `add_model.py:195-202` — a rendering function with
  a filesystem side effect) moves to an explicit `sync_previews()` step in the pipeline.
- Add Jinja2 to `benchmark_system/requirements.txt`; also add Flask there (it's required by
  `server.py` but missing today — noted in CLAUDE.md).

**Byte-compatibility is NOT a goal** (whitespace may differ); *rendered-content* compatibility is.
Verify by extracting all `<td>` text + card verdict lines from old and new HTML and diffing those.

### Task 1.3 — Rewire entry points and delete dead paths
**Effort: 1 day. Complexity: low.**

- `add_model.py`: after scoring, **append a sample to `results.json`** (via a small
  `results_store.py` with load/validate/save + a lockfile for concurrent batch runs), then call
  `build_site.py`. Delete `update_index()` and its regex machinery. Keep the CLI surface identical
  (`--judge`, `--judge-runs`, `--no-index` now meaning "skip site rebuild").
- `batch_free_models.py` and `benchmark_system/cli.py`: same store, same rebuild call. Per-run
  `runs/<ts>/` artifacts (raw HTML, `summary.json`, self-contained report from `generate_report()`)
  are unchanged — they remain the raw-evidence layer.
- Update `tests/test_update_index.py` → `tests/test_build_site.py`: given a fixture
  `results.json`, assert ordering, rank badges, grade colors, and that a second build is idempotent.
- Add the **staleness CI check**: rebuild in CI and `git diff --exit-code index.html results.json`.

### Risks & mitigations
- *R: Hand-edits in `index.html` that the migration regexes miss (footnotes, manual tweaks inside
  rows).* → Migration prints a reconciliation diff; eyeball it once; the golden-corpus content diff
  (Task 1.2) catches anything dropped.
- *R: Concurrent `batch_free_models.py` workers corrupting `results.json`.* → Lockfile in
  `results_store.py`; batch script already serializes model runs, so this is belt-and-braces.

---

## 6. Phase 2 — Runtime Verification Harness (5–7 days)

### Description
The credibility centerpiece. A Playwright (Python) harness that loads each generated clock in
headless Chromium **at a mocked, fixed wall-clock time**, then measures what actually renders. This
replaces LLM opinion with ground truth for the criteria that dominate the score: Time Accuracy (30%),
Motion (10%), and the first-frame bonus (10%) — half the total weight.

### Prerequisites
Phase 0 corpus. Independent of Phase 1 (integrates with either data layer). Playwright + Chromium
(already available in the dev environment; CI installs via `playwright install chromium`).

### Task 2.1 — Core harness: load, freeze time, extract state
**Effort: 2 days. Complexity: high.**

```python
# benchmark_system/verifier.py — core loop (pseudocode)
FIXED_TIMES = ["2026-01-15T10:09:36.500", "2026-01-15T16:47:12.250", "2026-01-15T00:00:00.000"]
# 10:09:36 = classic asymmetric layout, all hands distinct; 16:47 = PM wraparound test;
# 00:00 = degenerate case (all hands up) — catches inverted/offset math that 10:09 can miss.

def verify(html_path) -> RuntimeReport:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 800})
        results = []
        for t in FIXED_TIMES:
            page.clock.install(time=t)          # Playwright clock API: mocks Date, setInterval, rAF timing
            page.goto(f"file://{html_path}")
            errors = collect_console_errors(page)
            page.clock.pause_at(t)
            first_frame = read_hand_angles(page) # measured BEFORE any ticks → first-frame bonus
            page.clock.run_for(2000)             # advance mocked time 2s
            after = read_hand_angles(page)
            results.append(sample(t, first_frame, after, errors))
        return aggregate(results)
```

`read_hand_angles(page)` — the hard part, two strategies:

- **Strategy A — DOM/CSS clocks** (the majority of the corpus): find candidate hand elements
  (heuristics: elements with a `transform: rotate(...)` whose computed matrix changes between two
  mocked-time snapshots; narrow-tall aspect ratio; positioned near the clock center). Read
  `getComputedStyle(el).transform`, decompose the matrix to an angle. Classify hour/minute/second by
  relative length and by *angular velocity* between two snapshots (second hand moves 6°/s, minute
  0.1°/s) — velocity classification is robust where length heuristics fail.
- **Strategy B — Canvas clocks**: no DOM to inspect. Screenshot at the mocked time, then radial
  pixel analysis: find the dial center (largest circle via simple scan or contour of non-background
  pixels), sample rays every 0.5°, score each ray by contiguous non-background run length from
  center; the three strongest distinct peaks are the hands, longest-run = second/minute by
  thickness. Pure-Python on the PNG (Pillow + numpy) — no OpenCV dependency.

**Expected angles** at mocked time `h:m:s.ms`:
`sec = 6*(s + ms/1000)`, `min = 6*m + 0.1*s`, `hour = 30*(h%12) + 0.5*m + (s/120)`.
Tolerance: ±2° = correct; ±2–8° = partial (catches "no minute-fraction in hour hand" as a specific,
diagnosable failure — a discontinuous hour hand is off by up to 27.5°); >8° = wrong.

### Task 2.2 — Verdict extraction: map measurements to rubric fields
**Effort: 1.5 days. Complexity: medium.**

`RuntimeReport` (stored under `samples[].runtime` in `results.json`):

```json
{
  "verifier_version": "2.0",
  "loads": true, "console_errors": [],
  "render_strategy": "dom",
  "hands_detected": {"hour": true, "minute": true, "second": true},
  "angle_errors_deg": {"hour": 0.3, "minute": 0.1, "second": 0.2},
  "hour_continuous": true, "minute_continuous": true,
  "second_sweep_hz": 60.0,
  "first_frame_correct": true,
  "motion_method_observed": "rAF",
  "screenshots": ["previews/shots/<model>_100936.png"]
}
```

Derivations, replacing today's static/judge fields (per D2, replace — not override):
- `time.correct_12_top`, `hour_continuous`, `minute_continuous` → from measured angles at the three
  fixed times (continuity is measurable: at 10:09:36 a discontinuous hour hand reads 300.0° instead
  of 304.8°).
- `time.second_ms_precision` + `smoothness.method` → advance the mocked clock in 100 ms steps for
  one second and count distinct second-hand angles: ≥10 distinct = smooth sweep, 1–2 = 1 Hz tick.
  This *observes* behavior instead of grepping for `getmilliseconds()`/`setinterval`
  (`static_precheck`, `runner.py:58-89`, which today can't see `performance.now()`-based sweeps or
  a rAF loop that quantizes to whole seconds).
- `smoothness.zero_latency_init` (first-frame bonus) → `first_frame_correct`.
- **New gating field:** `loads` — page throws on load / renders nothing → cap: time and motion
  scores are 0 whatever the code says. This is the S2 "broken clock" guarantee.

`static_precheck` shrinks to `zero_dependencies` only (a genuinely static property — and keep it:
under the verifier's `file://` + offline context, CDN loads would fail anyway, so also **block
network in the page context** (`page.route('**/*', abort)` for non-file URLs) to make
zero-dependency behavior observable too).

### Task 2.3 — Corpus regression suite + screenshots
**Effort: 1.5 days. Complexity: medium.**

- Run the verifier over the frozen corpus; hand-check ~10 diverse outputs (DOM, canvas, SVG,
  broken) against a browser; freeze the reports as `tests/fixtures/expected_runtime/*.json`.
- `tests/test_verifier.py`: corpus → expected reports (angles within tolerance, categorical fields
  exact). Marked `@pytest.mark.browser`, skipped when Playwright is absent; CI gets a second job
  with Chromium installed.
- Screenshots at 10:09:36 saved to `previews/shots/` and shown on leaderboard cards next to the
  live iframe — the leaderboard becomes visually auditable at a glance.

### Task 2.4 — Pipeline integration
**Effort: 1 day. Complexity: low.**

`add_model.py` order becomes: generate → **verify** → judge (Phase 3 shrinks the judge's scope; until
then, verifier fields simply replace the corresponding audit fields the way `static_precheck` results
do today, at `runner.py:186-191`) → score → store → build site. `--no-verify` escape hatch retained.
Verifier failures (Playwright crash, timeout) are recorded as `runtime: {"error": ...}` and fall back
to v1 scoring for that sample, flagged on the leaderboard — never silently dropped.

### Risks & mitigations
- *R (high): hand-detection heuristics fail on exotic clocks (SVG `<line>` rotations via attributes,
  clocks drawn as Unicode art).* → Three-tier fallback: DOM strategy → pixel strategy (works on
  anything visible, including SVG) → `hands_detected: false`, which scores time accuracy 0 *with the
  screenshot attached as evidence* so a human can appeal. Corpus regression keeps precision honest;
  target: correct hand detection on ≥90% of the corpus before integration.
- *R: `page.clock` doesn't perfectly emulate rAF timing for all patterns.* → The three-fixed-times
  design only needs Date mocking + deterministic stepping, both core `page.clock` features; the
  sweep-detection test steps the clock manually rather than relying on real frame timing.
- *R: verifier introduces nondeterminism (font rendering, GPU).* → Fixed viewport, headless, angle
  (not pixel) comparisons, tolerances; S2's run-twice check is a CI test.

---

## 7. Phase 3 — Rubric v2: Single Source + Scoped Judge Ensemble (3–4 days)

### Description
Make the rubric machine-readable and re-scope the LLM judge to only the criteria that genuinely need
judgment, now that Phase 2 measures the rest.

### Prerequisites
Phases 1 (store) and 2 (verifier fields exist).

### Task 3.1 — `rubric.json` as single source of truth
**Effort: 1.5 days. Complexity: medium.**

```json
{
  "rubric_version": "2.0",
  "dimensions": [
    {"key": "time", "weight": 0.30, "criteria": [
      {"key": "hour_continuous", "points": 2.5, "source": "runtime",
       "description": "Hour hand advances with minutes (measured angle within 2° at fixed times)"},
      {"key": "correct_12_top",  "points": 2.5, "source": "runtime", "description": "..."}
    ]},
    {"key": "visual", "weight": 0.20, "criteria": [
      {"key": "has_bezel", "points": 2.0, "source": "judge",
       "description": "Separate rim layer from the clock face", "judge_guidance": "..."}
    ]}
  ]
}
```

- Each criterion declares its `source`: `runtime` (verifier), `static` (regex), or `judge` (LLM).
- **Generate** `JUDGE_V2.md` from `rubric.json` (`scripts/gen_judge_spec.py`): the human-readable
  tables plus the Audit JSON schema, but containing **only `source: "judge"` criteria** — the judge
  no longer opines on things we measure, which also removes the temptation documented in CLAUDE.md
  ("don't let the LLM override these").
- **Generate scoring**: `calculate_score(audit, runtime, rubric)` becomes a generic fold over
  `rubric.json` — weights leave `runner.py:253` entirely. Non-boolean criteria (tick counts,
  `globals_count`, the motion method 10/7/2 ladder) get a small `threshold`/`enum_points` field in
  the criterion spec rather than code.
- CI drift test (S3): regenerate `JUDGE_V2.md`, `git diff --exit-code`. Delete the root
  `JUDGE_V1.md` copy (also fixes the README error that calls it "the exact prompt given to all
  models" — it's the judge spec; the generation prompt is `runner.py:16`).
- Port `tests/test_calculate_score.py` to rubric-driven scoring; add a **frozen-scores test**: the
  full v1 corpus scored under rubric v2 with recorded verdicts must reproduce checked-in expected
  scores (catches accidental rubric arithmetic changes forever).

### Task 3.2 — Judge ensemble + structured output
**Effort: 1.5 days. Complexity: medium.**

- Judge criteria remaining: visual depth (5), dial completeness (5, minus what the verifier can
  count from screenshots later), code architecture minus `zero_dependencies` (3). All genuinely
  interpretive.
- Replace single-judge×3-runs with **3 distinct judge models × 1 run each** (e.g. one Anthropic,
  one OpenAI, one Google — configured in `rubric.json`), aggregated by the existing
  `_aggregate_audits` majority/median/mode logic (`runner.py:208`), which needs no changes.
  Cross-family ensembles counter same-model bias (a judge grading its own family's output) far
  better than same-judge repetition, at identical call count.
- Use OpenRouter's `response_format: {"type": "json_object"}` where the judge model supports it
  (add capability check via the `/models` endpoint already fetched in `fetch_model_pricing`);
  keep the first-`{`-to-last-`}` fallback parser for models that don't.
- Record `judge_models: [...]` and per-judge raw audits in the sample for auditability.

### Task 3.3 — Judge calibration set
**Effort: 1 day. Complexity: low.**

- Hand-label the 10 corpus files from Task 2.3 for every `judge` criterion (the answer key).
- `scripts/calibrate_judge.py <model>`: runs a candidate judge over the calibration set, reports
  per-criterion agreement. Gate: a judge model must score ≥90% agreement to be eligible for the
  ensemble. This turns "which judge?" from taste into measurement, and is rerun whenever a judge
  model is swapped (they deprecate often — the current default `claude-3.7-sonnet` is already old).

### Risks & mitigations
- *R: rubric-as-data becomes an over-engineered mini-DSL.* → Only three criterion shapes exist in
  the actual rubric (boolean, threshold-on-int, enum ladder); support exactly those, nothing more.
- *R: judge ensemble triples visible cost.* → It doesn't triple total cost: call count is unchanged
  (3→3); marginal cost is only the price delta between judge models. Cap judge `max_tokens` (already
  parameterized) and record per-sample judge cost in the store.

---

## 8. Phase 4 — Statistical Rigor (2–3 days)

### Description
Score distributions instead of point estimates.

### Prerequisites
Phase 3 (so new samples are scored under v2 — don't burn API budget collecting samples that need
re-scoring).

### Task 4.1 — Multi-sample generation
**Effort: 1 day. Complexity: low.**

- `add_model.py --samples N` (default 3): N independent generations (temperature as provider
  default; record it), each verified+judged independently, each stored under `samples[]` (schema
  already supports this from Phase 1 — no migration).
- `aggregate` computed at store time: mean, sample std, 95% CI (t-distribution — n is tiny),
  min/max. Leaderboard ranks by mean; renders `8.1 ± 0.6 (n=3)`; entries whose CIs overlap the
  neighbor above get no visual "strictly better" treatment (same rank-color band).
- Cost note in docs: a 3× sample run costs ~3× generation + ~3× judging; `--samples 1` remains for
  cheap smoke runs and is labeled `n=1` on the board.

### Task 4.2 — Re-benchmark the current leaderboard under v2
**Effort: 1–2 days elapsed (mostly API wait). Complexity: low, budget-bound.**

- Rerun every current cloud-tab model at `--samples 3` under rubric v2. Old v1 entries stay in
  `results.json` (`scoring_version: 1`) for the historical record; the leaderboard shows v2 with a
  "v1" badge only for models no longer available on OpenRouter (they can't be rerun — display their
  v1 score, sorted within the same list, tooltip explaining the caveat).
- Publish a short `docs/V2_CHANGES.md` with a v1-vs-v2 score comparison table — the transparency
  artifact that makes the methodology change legible to readers.

### Risks
- *R: rankings shuffle and past claims look wrong.* → That's the feature, not the bug; the
  comparison doc frames it. *R: budget.* → Estimate before running: models × 3 samples ×
  (generation + 3 judge calls); print projected cost from OpenRouter pricing (already fetched) and
  require `--yes` above a threshold.

---

## 9. Phase 5 — Automation & Publishing (2–3 days)

### Task 5.1 — `add-model` GitHub Action
**Effort: 1.5 days. Complexity: medium.**

- `workflow_dispatch` with inputs: `model_id`, `samples` (default 3). Steps: checkout → install
  deps + Chromium → `python add_model.py <model> --samples N` (uses `OPENROUTER_API_KEY` from repo
  secrets) → commit `results.json`, `previews/`, `previews/shots/`, regenerated `index.html` to a
  branch → open a PR with the score summary and screenshots in the body.
- Human merges the PR = editorial control retained; nothing lands on the leaderboard unreviewed.
- Optional scheduled workflow (monthly): re-verify all `previews/*.html` with the current verifier
  and fail loudly if any stored verdict changes (verifier regression tripwire on real data).

### Task 5.2 — GitHub Pages deploy + repo hygiene
**Effort: 1 day. Complexity: low.**

- Pages workflow on push to `main`: run staleness check (S1), deploy root (already
  Pages-compatible — `previews/` exists precisely because `runs/` is gitignored, per the comment at
  `add_model.py:195`).
- Hygiene items batched here: add `flask` + `jinja2` + `playwright` to requirements files
  (dev vs. runtime split); README rewrite reflecting v2 methodology (that's the marketing surface —
  "runtime-verified" is the headline); update CLAUDE.md (it currently states "no test suite" —
  already false — plus the new architecture); decide **not** to rename the `local ` directory
  (CLAUDE.md marks it intentional; renaming breaks nothing valuable and risks link rot — defer
  unless Pages URL-encoding causes real issues).

---

## 10. Dependency Map & Sequencing

```
Phase 0 (snapshot + decisions)
   ├──────────────┐
   ▼              ▼
Phase 1 (data)   Phase 2 (verifier)      ← independent; parallelize if desired
   └──────┬───────┘
          ▼
     Phase 3 (rubric v2 + judge ensemble)
          ▼
     Phase 4 (multi-sample + re-benchmark)
          ▼
     Phase 5 (CI automation + Pages)      ← 5.2 hygiene can start any time after Phase 1
```

Hard orderings and why:
- **3 after 1 AND 2**: rubric v2 declares `source: runtime` fields (needs the verifier to exist) and
  the generated scorer writes into the store (needs the schema).
- **4 after 3**: never collect expensive multi-sample data under a scoring scheme about to change.
- **5.1 after 4**: the Action should run the final pipeline shape, not an interim one (5.2's Pages
  deploy only needs Phase 1).
- Within Phase 2: 2.1 → 2.2 → 2.3 → 2.4 strictly (each consumes the previous).

Ship-and-pause points: after Phase 1 (site is generator-driven, everything else works as v1), after
Phase 2 (verifier data displayed alongside v1 scores), after Phase 4 (fully credible board, manual
workflow). The project is never in a broken intermediate state at a phase boundary.

---

## 11. Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Owner phase |
|---|------|-----------|--------|------------|-------------|
| R1 | Hand-angle detection fails on exotic render styles (canvas art, SVG attr rotation, web components) | High | Medium — mis-scores time accuracy, the 30% dimension | Dual DOM+pixel strategy; ≥90% corpus detection gate before integration; screenshot evidence attached to every 0-score; manual `runtime_override` field in store as last resort | 2 |
| R2 | `page.clock` mocking interacts badly with some clocks' timing code | Medium | Medium | Design needs only Date mock + manual stepping; corpus regression catches breakage per-Playwright-upgrade; pin Playwright version | 2 |
| R3 | Migration drops or corrupts existing leaderboard data | Low | High — historical record is the product | v1-final git tag; reconciliation report; S6 count+score equality check; migration script kept in repo | 1 |
| R4 | Rubric v2 rescoring shuffles ranks, credibility questions from readers | High | Low–Medium | `docs/V2_CHANGES.md` comparison table; keep v1 scores in store; "runtime-verified" framing turns it into a strength | 4 |
| R5 | Judge models deprecate on OpenRouter (default judge is already dated) | High | Low | Ensemble of 3 (single deprecation degrades, not breaks); calibration script makes replacement a 30-min measured swap | 3 |
| R6 | API budget overrun on re-benchmark / batch runs | Medium | Low | Pre-run cost projection from fetched pricing + `--yes` gate; free-tier batch path already rate-limit aware | 4 |
| R7 | Malicious/degenerate generated HTML escapes the verifier sandbox or hangs it | Low | Medium | Headless browser is the sandbox; per-page network blocked, 30 s hard timeout per file, verifier errors recorded not fatal | 2 |
| R8 | Generated-site drift: someone hand-edits `index.html` post-Phase 1 | Medium | Low | CI staleness check fails the build; CLAUDE.md updated to say "edit templates, not index.html" | 1 |
| R9 | Scope creep toward multi-task benchmark suite mid-project | Medium | Medium | Explicit non-goal (§2); schema's `prompt` field keeps the door open for later without acting now | all |

---

## 12. Timeline / Roadmap (part-time, ~2–3 focused days per week)

| Week | Work | Exit milestone |
|------|------|----------------|
| 1 | Phase 0 + Tasks 1.1–1.2 | `results.json` exists and reconciles; generator renders content-identical site |
| 2 | Task 1.3 + start 2.1 | Regex splicing deleted; all entry points on the store; CI staleness check green |
| 3 | Tasks 2.1–2.2 | Verifier measures angles on DOM clocks; verdict schema settled |
| 4 | Tasks 2.3–2.4 | ≥90% corpus detection; verifier in the pipeline; screenshots on cards |
| 5 | Tasks 3.1–3.2 | `rubric.json` single-sources scoring + JUDGE_V2; ensemble live |
| 6 | Task 3.3 + Task 4.1 | Judges calibrated ≥90%; `--samples N` with CIs rendering |
| 7 | Task 4.2 (elapsed API time) + `docs/V2_CHANGES.md` | Full leaderboard re-benchmarked under v2 |
| 8 | Phase 5 | One-click add-model Action; Pages auto-deploy; docs/CLAUDE.md current |
| 9–10 | Buffer: R1 long-tail (exotic clocks), polish, announcement post | All success criteria S1–S7 verified |

---

## 13. Upfront Research & Open Decisions

Do these **before or during Phase 0** — everything else in the plan assumes their outcomes:

1. **Playwright `page.clock` spike (½ day, highest value).** Take 3 corpus clocks (one rAF, one
   `setInterval(1000)`, one canvas) and confirm: mocked Date is honored, `clock.run_for` advances
   rAF-driven animation deterministically, computed-transform reading works. This validates the
   Phase 2 design before committing 5–7 days. *If it fails:* fallback design is CDP
   `Emulation.setVirtualTimePolicy` + injected `Date` shim — same harness shape, ~1 extra day.
2. **D1–D3 (§4)** — recommended defaults given; confirm or amend.
3. **Ensemble judge lineup (½ day):** pick 3 candidate judges from different families currently on
   OpenRouter with JSON-mode support and sane pricing; final selection is decided by the Task 3.3
   calibration gate, not upfront debate.
4. **Budget ceiling for Task 4.2:** models-on-board × 3 samples × (1 gen + 3 judge calls); compute
   the projection with current pricing before committing. If it exceeds appetite, re-benchmark the
   top 10 + any model within 1.0 of the top 10, keep the tail on v1 badges.
5. **Not needed upfront** (explicitly deferred): static-site framework choice (plain Jinja2 is
   enough — one page), database (JSON file is fine at this scale: ~100 entries × ~few KB), and any
   multi-prompt suite design (R9).

---

## 14. Self-Review: Gaps Checked, Judgment Calls Made

- **Does anything break mid-migration?** No — Phase 1 keeps `runs/` artifacts and CLI flags
  identical; Phases 2–3 add fields before removing reliance on old ones; every phase boundary
  passes the existing test suite (S7).
- **Circular sync trap avoided:** `JUDGE_V2.md` is *generated*, never edited — the v1 disease
  (three rubric copies) can't recur because CI fails on drift (S3).
- **Verifier can't silently lie:** every runtime verdict ships with its screenshot; failures fall
  back to flagged v1 scoring rather than fake zeros; run-twice determinism is a CI test (S2).
- **Cheapest-first ordering:** the two riskiest unknowns (clock mocking, hand detection) are
  front-loaded as a half-day spike + a phase with an explicit 90% gate, before any API spend on
  re-benchmarking.
- **Known ambiguity left open deliberately:** whether dial tick-counting moves from judge to
  screenshot analysis (it's plausible but low-value — 15% weight, judges agree well on counting).
  Parked as a post-v2 candidate rather than padding Phase 2's risk.
- **Single-maintainer reality respected:** no service to operate, PR-gated automation, every
  destructive step (migration, rescore) leaves the prior state recoverable via git tag + preserved
  v1 records.
