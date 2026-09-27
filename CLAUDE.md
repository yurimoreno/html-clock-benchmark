# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A benchmark that gives frontier LLMs one identical one-shot prompt — "Generate a single HTML file that displays a working analog clock..." (`benchmark_system/runner.py:16`) — then has a designated "judge" model audit the generated code against a fixed rubric. Results are published as a static leaderboard in `index.html`.

## Commands

Dependencies: `pip install -r benchmark_system/requirements.txt` (requests, python-dotenv, inquirer). Flask is required for `server.py` but not listed there.

Requires `OPENROUTER_API_KEY` in `.env` at repo root — clock generation goes through OpenRouter. Judging defaults to TypeSafe's Jev (`typesafe/jev`), which needs `TYPESAFE_API_KEY` in the same `.env` (the optional second, vision judge reads `VISION_JUDGE_URL` and `VISION_JUDGE_MODEL` from there too); pass `--judge <openrouter-model-id>` to use a generative LLM judge instead.

```bash
# Add one model to the leaderboard (generate + judge + insert into index.html)
python add_model.py google/gemini-2.5-flash
python add_model.py openai/gpt-4o --judge anthropic/claude-3.7-sonnet   # generative judge instead of Jev
python add_model.py <model> --no-index      # skip index.html update
python add_model.py <model> --judge-runs 5  # default is 3

# Interactive multi-model benchmark / re-evaluation of an existing run folder
cd benchmark_system && python cli.py

# Batch all free OpenRouter models (rate-limit aware, resumable)
python batch_free_models.py --resume

# Local tab: build and judge are separate steps. build records the machine, server
# version and model path from the endpoint; pass recipe notes as the last argument.
python local_add.py build http://localhost:8888/v1/chat/completions <model> "<recipe notes>"
python local_add.py judge <model>

# Optional Flask API + static server (serves index.html, cloud/, runs/)
python server.py   # localhost:5000
```

There is no test suite, linter, or build step. Validation is manual: open `index.html` (or a `runs/<ts>/index.html`) in a browser.

## Architecture

**`benchmark_system/runner.py` is the core** — every other entry point imports from it. Key functions:
- `generate_clock(model)` → `(html, latency_s, usage)`. Strips ```` ```html ```` fences from the response.
- `evaluate_clock(judge, html)` / `evaluate_clock_reliable(judge, html, n_runs)` → audit JSON. The "reliable" variant runs the judge N times and aggregates via `_aggregate_audits` (majority vote for booleans, median for ints, mode for strings) to reduce LLM variance.
- `calculate_score(audit)` → `(score, breakdown)`. Applies the weighted rubric.
- `benchmark_system/typesafe_judge.py` is the default judge: one TypeSafe Jev call per clock with one Noul (yes/no) question per rubric criterion, assembled into the same Audit JSON. Count fields are threshold questions (Jev is weak at counting) and emit 12/60/0/99 sentinels that satisfy `calculate_score` thresholds. `benchmark_system/compare_judges.py` re-judges every stored run and writes `docs/typesafe-judge-comparison.md`.
- `static_precheck(html)` deterministically overrides three judge fields that regex can decide reliably: motion `method` (rAF / high_freq / low_freq), `zero_dependencies`, and `second_ms_precision` (only upgraded to True, never down). This is intentional — don't let the LLM override these.
- `apply_render_check(audit, html)` (runs inside `evaluate_clock_reliable`) renders the clock in headless Chromium via `benchmark_system/render_check.py` at four frozen times, diffs frames to isolate each hand, and measures its angle. A conclusive result overrides `time.correct_12_top` in either direction; an inconclusive one (hand too close to the background colour, pivot not found) leaves the judge's answer. It exists because source-reading judges missed clocks whose hands were rotated (DeepSeek V4 Pro applied the -90° offset twice). `rejudge_index.py --stored` re-scores the cloud tab from `audits.json` plus a fresh render check without calling Jev. `measure.py` extends the render check to 10 of the 20 rubric questions (time, first frame, shadows, gradients, globals, responsive, dependencies); every measurement runs twice and only counts if it reproduces. `vision_judge.py` is a second judge: a vision model (any OpenAI-compatible endpoint, set by `VISION_JUDGE_URL` / `VISION_JUDGE_MODEL` in `.env`; skipped if unset) looks at a screenshot for hand tails, center cap, bezel, ticks and numerals; when it splits with Jev, the same model reading the code breaks the tie, and its votes also must repeat to count. Order in `evaluate_clock_reliable`: Jev → `apply_second_judge` → `apply_render_check` (measurements win). `docs/make_verify_page.py <clock>` renders one clock's full audit trail.

**The rubric lives in two places that must stay in sync:** `benchmark_system/JUDGE_V1.md` (human-readable spec + the Audit JSON schema, injected verbatim into the judge prompt) and the hardcoded weights/thresholds in `calculate_score` (`runner.py:253`). Editing scoring means editing both. Final score formula: `time×0.3 + visual×0.2 + dial×0.15 + code×0.15 + motion×0.1 + bonus×1.0`.

**`add_model.py` owns leaderboard presentation.** It generates table rows and cards, then `update_index()` splices them into `index.html` via regex — matching `<table id="cloud-table">`'s tbody and the `<div data-tab="cloud">` grid. It re-sorts by score and renumbers ranks on every insert. Each card's verdict (dimension cells, an Earned/Lost summary, and a meta line) is built by `make_verdict()`; the summary comes from `why_html(audit)`, which reads the same audit fields as `calculate_score`, so every card's audit is stored in `audits.json` keyed by its clock path. `rejudge_index.py` refreshes those cards and audits in place. `model_display_name()` maps raw model IDs to pretty names using `_PROVIDER_NAMES` / `_MODEL_ALIASES`, falling back to the OpenRouter API name. Score→color/grade mapping is in `score_to_grade` and `_OVERALL_COLORS`.

**`index.html` is a hand-maintained static site** with three tabs: `cloud`, `local`, and the auto-generated runs table. The `cloud/` and `local /` directories hold manually curated `.html` clock outputs with their own `SCORECARD.md`. Only the cloud table/grid is mutated programmatically; the local tab is edited by hand.

**`runs/<timestamp>/`** holds each benchmark's output: the generated `<model>.html`, a `summary.json`, and (for `cli.py`/batch runs) a self-contained `index.html` report from `generate_report()`. `add_model.py` runs write into `runs/` and additionally patch the top-level `index.html`.

## Gotchas

- **`local ` has a trailing space** in its directory name (referenced as `"local "` in code and `/local%20/` in `server.py`). Not a typo — don't "fix" it.
- **`generate_clock()` returns a 3-tuple `(html, latency_s, usage)`** — unpack it, don't assign the whole tuple. All four entry points (`add_model.py`, `cli.py`, `server.py`, `batch_free_models.py`) are kept in sync with this signature.
- Judge output is parsed loosely (first `{` to last `}`, with markdown-fence fallback). A judge model that won't emit clean JSON will fail evaluation.
