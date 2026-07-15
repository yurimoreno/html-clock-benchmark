# Phase 0 — Locked decisions

Recorded at tag **`v1-final`** before Phase 1 (`results.json` + site generator).
Source plan: [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) §4 / §13.

## Snapshot

| Item | Value |
|------|--------|
| Git tag | `v1-final` (annotated) |
| Commit | merge of PR #6 + this Phase 0 commit |
| Golden corpus | [`tests/fixtures/corpus/`](../tests/fixtures/corpus/MANIFEST.md) |
| Prior tag | `v1.0` remains (initial release); `v1-final` is the pre-v2-migration freeze |

## Decisions (D1–D3)

### D1 — Scoring version policy

**Keep both; display v2, badge v1-only entries.**

- Every migrated leaderboard row is stored with `"scoring_version": 1`.
- After Phase 4 re-benchmark, new samples use `"scoring_version": 2`.
- Leaderboard sorts on the best available v2 aggregate when present; otherwise
  shows the v1 score with a clear **v1** badge / tooltip (model unavailable to re-run).
- v1 rows are never deleted from `results.json` — they are the historical record.

### D2 — Verifier authority on overlapping fields

**Replace entirely** (same spirit as today’s `static_precheck`, but full replace).

When a runtime report is present for a sample, these fields come only from the
verifier — the LLM judge does not set or override them:

- time accuracy / hand continuity / 12-at-top geometry (from measured angles)
- second-hand ms precision and observed motion method (from stepped mock clock)
- first-frame / zero-latency init (from angles before any tick)
- page `loads` gate (hard cap of time + motion to 0 if the page fails)

Judge remains responsible only for subjective criteria (visual depth, dial
aesthetics, code architecture), once Phase 3 lands. Until then, verifier
fields overwrite the corresponding audit keys the way `static_precheck` does
today.

If the verifier errors (timeout, crash), store `runtime: {"error": ...}` and
**fall back to v1-style scoring for that sample**, flagged on the board — never
silent zeros.

### D3 — Where generated site data lives

**`results.json` committed at repo root.**

- It *is* the benchmark record (schema versioned from day one).
- `index.html` becomes a pure build artifact of `build_site.py` (Phase 1).
- CI enforces staleness: rebuild and `git diff --exit-code index.html results.json`.

## Deferred (not locked here)

- Playwright `page.clock` spike outcome → still required before Phase 2 commit
  (plan §13 item 1); failure mode is CDP virtual time + Date shim.
- Ensemble judge lineup → chosen at Task 3.3 calibration, not now.
- Budget ceiling for full re-benchmark → computed before Task 4.2 with live pricing.
- Renaming the `local ` directory → **not** doing (CLAUDE.md intentional).

## Phase 0 checklist

- [x] PR #6 merged (`PROJECT_PLAN.md` on `main`)
- [x] Tag `v1-final`
- [x] Golden corpus frozen under `tests/fixtures/corpus/`
- [x] Known-broken fixture + canvas samples identified
- [x] D1–D3 locked in this document

**Next:** Phase 1 — `scripts/migrate_v1.py` → `results.json`, then `build_site.py`.
See `PROJECT_PLAN.md` §5.
