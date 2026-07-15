# Golden corpus (Phase 0 freeze)

Frozen snapshot of every HTML clock in the repo at tag **`v1-final`**
(`6d5888ed8b0c6e0d9069bf6d544fbc921b13ff57`, 2026-07-15). Used as the
regression set for the Phase 2 runtime verifier and the Phase 1 migration
content checks.

## Layout

| Path | Source | Notes |
|------|--------|-------|
| `cloud/` | `cloud/*.html` (excl. `comparison.html`) | Spaces in filenames sanitized to `_` |
| `previews/` | `previews/*.html` | OpenRouter run previews committed to the site |
| `local/` | `local /*.html` (excl. `comparison.html`) | Source dir has a trailing space; fixture dir does not |
| `runs/` | `runs/*/*.html` (excl. per-run `index.html`) | Named `{run_id}__{original_basename}.html` |
| `synthetic/` | Hand-authored fixtures | Not from a model |

## Counts at freeze

- cloud: 11
- previews: 9
- local: 6
- runs: 39
- synthetic: 1 (`broken_frozen_1200.html`)
- **total: 66**

## Canvas-based clocks (Strategy B targets)

Verified via `getContext('2d')` at freeze time:

- `cloud/glm-5.1.html`
- `cloud/sonnet_4.6.html`
- `previews/deepseek_deepseek-v4-flash.html`
- `previews/deepseek_deepseek-v4-pro.html`
- `previews/qwen_qwen3.6-35b-a3b.html`
- `local/glm-4.6v-flash.html`
- `local/qwen2.5-coder-14b.html`
- plus matching copies under `runs/`

## Known-broken fixture

`synthetic/broken_frozen_1200.html` — hands fixed at 12:00 forever. Script
mentions `requestAnimationFrame` and `getMilliseconds()` so static precheck
can look “smooth”; runtime must score time accuracy **0**.

## Do not edit

Treat this tree as immutable history. New fixtures go under `synthetic/`
with a note here; model outputs land in live `cloud/` / `previews/` / `runs/`
and are not back-ported into this freeze.
