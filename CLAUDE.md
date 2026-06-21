# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A benchmark that gives frontier LLMs one identical one-shot prompt — "Generate a single HTML file that displays a working analog clock..." (`benchmark_system/runner.py:16`) — then has a designated "judge" model audit the generated code against a fixed rubric. Results are published as a static leaderboard in `index.html`.

## Commands

Dependencies: `pip install -r benchmark_system/requirements.txt` (requests, python-dotenv, inquirer). Flask is required for `server.py` but not listed there.

Requires `OPENROUTER_API_KEY` in `.env` at repo root — every model call (generation and judging) goes through OpenRouter.

```bash
# Add one model to the leaderboard (generate + judge + insert into index.html)
python add_model.py google/gemini-2.5-flash
python add_model.py openai/gpt-4o --judge anthropic/claude-3.7-sonnet
python add_model.py <model> --no-index      # skip index.html update
python add_model.py <model> --judge-runs 5  # default is 3

# Interactive multi-model benchmark / re-evaluation of an existing run folder
cd benchmark_system && python cli.py

# Batch all free OpenRouter models (rate-limit aware, resumable)
python batch_free_models.py --resume

# Optional Flask API + static server (serves index.html, cloud/, runs/)
python server.py   # localhost:5000
```

There is no test suite, linter, or build step. Validation is manual: open `index.html` (or a `runs/<ts>/index.html`) in a browser.

## Architecture

**`benchmark_system/runner.py` is the core** — every other entry point imports from it. Key functions:
- `generate_clock(model)` → `(html, latency_s, usage)`. Strips ```` ```html ```` fences from the response.
- `evaluate_clock(judge, html)` / `evaluate_clock_reliable(judge, html, n_runs)` → audit JSON. The "reliable" variant runs the judge N times and aggregates via `_aggregate_audits` (majority vote for booleans, median for ints, mode for strings) to reduce LLM variance.
- `calculate_score(audit)` → `(score, breakdown)`. Applies the weighted rubric.
- `static_precheck(html)` deterministically overrides three judge fields that regex can decide reliably: motion `method` (rAF / high_freq / low_freq), `zero_dependencies`, and `second_ms_precision` (only upgraded to True, never down). This is intentional — don't let the LLM override these.

**The rubric lives in two places that must stay in sync:** `benchmark_system/JUDGE_V1.md` (human-readable spec + the Audit JSON schema, injected verbatim into the judge prompt) and the hardcoded weights/thresholds in `calculate_score` (`runner.py:253`). Editing scoring means editing both. Final score formula: `time×0.3 + visual×0.2 + dial×0.15 + code×0.15 + motion×0.1 + bonus×1.0`.

**`add_model.py` owns leaderboard presentation.** It generates table rows and cards, then `update_index()` splices them into `index.html` via regex — matching `<table id="cloud-table">`'s tbody and the `<div data-tab="cloud">` grid. It re-sorts by score and renumbers ranks on every insert. `model_display_name()` maps raw model IDs to pretty names using `_PROVIDER_NAMES` / `_MODEL_ALIASES`, falling back to the OpenRouter API name. Score→color/grade mapping is in `score_to_grade` and `_OVERALL_COLORS`.

**`index.html` is a hand-maintained static site** with three tabs: `cloud`, `local`, and the auto-generated runs table. The `cloud/` and `local /` directories hold manually curated `.html` clock outputs with their own `SCORECARD.md`. Only the cloud table/grid is mutated programmatically; the local tab is edited by hand.

**`runs/<timestamp>/`** holds each benchmark's output: the generated `<model>.html`, a `summary.json`, and (for `cli.py`/batch runs) a self-contained `index.html` report from `generate_report()`. `add_model.py` runs write into `runs/` and additionally patch the top-level `index.html`.

## Gotchas

- **`local ` has a trailing space** in its directory name (referenced as `"local "` in code and `/local%20/` in `server.py`). Not a typo — don't "fix" it.
- **`generate_clock()` returns a 3-tuple `(html, latency_s, usage)`** — unpack it, don't assign the whole tuple. All four entry points (`add_model.py`, `cli.py`, `server.py`, `batch_free_models.py`) are kept in sync with this signature.
- Judge output is parsed loosely (first `{` to last `}`, with markdown-fence fallback). A judge model that won't emit clean JSON will fail evaluation.
