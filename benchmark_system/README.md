# HTML Analog Clock Benchmark System

Automated system for generating and evaluating HTML analog clocks across different LLMs using OpenRouter.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your OpenRouter API Key in a `.env` file or export it:
   ```bash
   export OPENROUTER_API_KEY='your_key_here'
   ```

## Usage

### Interactive CLI

Run the interactive CLI:
```bash
python cli.py
```

Choose between:
- **Run Full Benchmark**: Generate + audit new models (select multiple models and a judge)
- **Run Evaluation Only**: Re-evaluate an existing run folder with a different judge

### Single Model CLI

For adding one model to the benchmark without the interactive prompt:

```bash
python add_model.py <model_id> [--judge <judge_model>]
```

## How it works

1. **Generation**: It sends the prompt "Generate a single HTML file that displays a working analog clock showing the current time with hour, minute, and second hands." to each selected model.
2. **Storage**: Responses are saved as `.html` files in a timestamped folder under `runs/`.
3. **Evaluation**: The selected "Judge" model audits each file using the deterministic criteria defined in `JUDGE_V1.md`.
4. **Reporting**: A local `index.html` report is generated in the run folder with a scoreboard, execution metadata, and live previews.

## Scoring Rubric (v1)

- **Time Accuracy (30%)**: Continuous motion and correct offsets.
- **Visual Depth (20%)**: Shadows, gradients, and polished geometry.
- **Dial Completeness (15%)**: Proper markers and numerals.
- **Code Architecture (15%)**: Scope hygiene and responsiveness.
- **Motion Smoothness (10%)**: Update frequency and logic.
- **One-Shot Bonus (10%)**: Accurate initial frame.

## TypeSafe judge (alternative backend)

A second, non-generative judge is available: TypeSafe's System One model `Jev`
answers one typed Noul (yes/no) question per rubric criterion over the clock's
HTML source, then the answers are assembled into the same Audit JSON schema
from `JUDGE_V1.md`, so `calculate_score()` consumes it unchanged.

### Setup

`TYPESAFE_API_KEY` must be in the repo `.env` (alongside `OPENROUTER_API_KEY`):

```bash
TYPESAFE_API_KEY=ts_...
```

Install the SDK (`typesafe-sdk`, imported as `typesafe_sdk`; already listed in
`benchmark_system/requirements.txt`).

### Choosing the judge

`typesafe/jev` is now the default judge in `add_model.py` and `batch_free_models.py`; pass it explicitly elsewhere:

```bash
python add_model.py google/gemini-2.5-flash --judge typesafe/jev
```

`evaluate_clock()` / `evaluate_clock_reliable()` detect that id and route to
`typesafe_judge.evaluate_clock_typesafe()` (one Jev request per clock;
`n_runs` is ignored and `runs_completed` is 1). Any other id uses the normal
OpenRouter path. Each returned audit carries the raw Noul probabilities in
`typesafe_probs`, the resolved model in `typesafe_model`, and per-call token
usage in `typesafe_usage` (all ignored by `calculate_score()`).

### Comparison script

`benchmark_system/compare_judges.py` re-judges every stored run that has a
LLM `audit` and prints per-field agreement and per-run score deltas, writing
`runs/typesafe_comparison.json`:

```bash
python benchmark_system/compare_judges.py
```

### Count-field caveat

Jev counts poorly, so the four numeric fields are **thresholded Noul checks**,
not real tallies. The emitted ints only satisfy the thresholds `calculate_score`
uses (`>=12`, `>=48`, `>=12`, `<=2`):

| Field | Noul statement | yes -> | no -> |
| :-- | :-- | :-- | :-- |
| `dial.hour_ticks_count` | 12 hour markers rendered | 12 | 0 |
| `dial.minute_ticks_count` | minute markers between hours (48/60) | 60 | 0 |
| `dial.numerals_count` | all 12 numerals 1-12 shown | 12 | 0 |
| `code.globals_count` | at most 2 leaked globals | 0 | 99 |

So counts are pass/fail, not exact values; do not compare them to the LLM
judge's integers numerically, only through the same thresholds (the comparison
script does exactly this). `smoothness.method`, `code.zero_dependencies`, and
`time.second_ms_precision` are never asked of Jev — they come from
`static_precheck()` regex, identical to the LLM path.
