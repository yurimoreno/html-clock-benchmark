# HTML Analog Clock Benchmark

One-shot prompt: build an analog clock as a single HTML file. Scored on time accuracy, visuals, dial completeness, code quality, and smoothness.

## Background

The task is simple but revealing — give frontier LLMs the same one-shot prompt and see what they produce. No special concessions for any model; every LLM must infer clock geometry from the request alone.

Scores assigned by **Opus 4.7** acting as judge across five dimensions:

| Dimension | Weight | What it measures |
|---|---|---|
| Time Accuracy | ×3 | Correct hand angles using correct math |
| Visuals | ×2 | Bezel, face, hand differentiation, shadows, numerals |
| Markers & Numbers | ×1.5 | Hour/minute tick completeness and placement |
| Code Quality | ×1.5 | Single coordinate frame, proper pivot origins |
| Smoothness | ×1 | Smooth sweep (rAF + ms) vs. snapping tick (1 Hz setInterval) |

## Structure

```
html clock benchmark/
├── index.html              # Main benchmark site (cloud + local tabs)
├── cloud/                 # Cloud model HTML outputs
│   ├── SCORECARD.md
│   └── *.html
├── local /                # Local model outputs (note: trailing space)
│   ├── SCORECARD.md
│   └── *.html
├── benchmark_system/      # Judge prompt + runner
│   ├── JUDGE_V1.md
│   ├── runner.py
│   └── cli.py
└── JUDGE_V1.md            # The exact prompt given to all models
```

## The Prompt

```
Generate a single HTML file that displays a working analog clock showing the current time with hour, minute, and second hands.
```

## License

MIT — Copyright 2026 Yuri Moreno. Released for educational and personal use.
