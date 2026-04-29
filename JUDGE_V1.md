# HTML Analog Clock Benchmark — Judge Specification v1.0

This document defines the deterministic scoring rubric for the HTML Analog Clock Benchmark. The goal is to move from "subjective vibes" to a repeatable, mathematical audit of the generated code.

## 1. Scoring Summary
The final score is a weighted average of five dimensions (Total: /10):
- **Time Accuracy (30%)** — Mathematical correctness and precision.
- **Visual Depth (20%)** — Use of CSS/Canvas graphics primitives.
- **Dial Completeness (15%)** — Geometric placement of markers and numerals.
- **Code Architecture (15%)** — Maintainability, scope hygiene, and abstractions.
- **Motion Smoothness (10%)** — Frame rate and movement logic.
- **One-Shot Bonus (10%)** — Accuracy of the initial render frame.

---

## 2. Metric Breakdowns

### A. Time Accuracy (Weight: 3.0)
| Criteria | Logic Check | Points |
| :--- | :--- | :--- |
| **Continuous Hour** | Formula includes `(minutes / 60)`? | 2.5 |
| **Continuous Minute** | Formula includes `(seconds / 60)`? | 2.5 |
| **High-Res Seconds** | Formula includes `milliseconds`? | 2.5 |
| **Top-Center Bias** | Is 12 at the top (correct radian/degree offset)? | 2.5 |

### B. Visual Depth (Weight: 2.0)
| Criteria | Primitive Check | Points |
| :--- | :--- | :--- |
| **Shadows** | `box-shadow`, `drop-shadow`, or `shadowBlur`. | 2.0 |
| **Gradients** | `radial-gradient` or `linear-gradient` used. | 2.0 |
| **Hand Tails** | Hands extend past the pivot (counterweights). | 2.0 |
| **Center Cap** | Distinct visual element covering the pivot. | 2.0 |
| **Bezel** | Separate rim layer from the clock face. | 2.0 |

### C. Markers & Numbers (Weight: 1.5)
| Criteria | Audit Check | Points |
| :--- | :--- | :--- |
| **Hour Ticks** | Exactly 12 markers present? | 2.0 |
| **Minute Ticks** | 48 or 60 minute markers present? | 2.0 |
| **Numerals** | Exactly 12 numeric labels (1–12) present? | 2.0 |
| **Logical Loop** | Markers generated via Loop/JS (not manual HTML). | 2.0 |
| **Clean Intersect** | Skips minute markers at hour positions? | 2.0 |

### D. Code Architecture (Weight: 1.5)
| Criteria | Pattern Check | Points |
| :--- | :--- | :--- |
| **Namespace** | 2 or fewer global variables leaked? | 3.0 |
| **Responsiveness** | No hard-coded `px` for clock centering/size. | 3.0 |
| **DRY Pattern** | Uses helper functions for hands or ticks. | 2.0 |
| **No External** | Zero `<script src>` or CDN dependencies. | 2.0 |

### E. Motion & Logic (Weight: 1.0)
| Criteria | Implementation Check | Points |
| :--- | :--- | :--- |
| **Update Method** | `requestAnimationFrame` (10) or `<100ms` (7). | 10.0 |
| **First Frame** | Is the clock accurate on load (no 12:00 snap)? | +1 Bonus |

---

## 3. The Audit JSON
Frontier models (e.g., Opus) should analyze the code and return this JSON schema to generate the scorecard:

```json
{
  "time": {
    "hour_continuous": boolean,
    "minute_continuous": boolean,
    "second_ms_precision": boolean,
    "correct_12_top": boolean
  },
  "visual": {
    "has_shadows": boolean,
    "has_gradients": boolean,
    "has_hand_tails": boolean,
    "has_center_cap": boolean,
    "has_bezel": boolean
  },
  "dial": {
    "hour_ticks_count": integer,
    "minute_ticks_count": integer,
    "numerals_count": integer,
    "automated_marker_generation": boolean,
    "skips_minute_at_hour": boolean
  },
  "code": {
    "globals_count": integer,
    "is_responsive": boolean,
    "uses_helpers": boolean,
    "zero_dependencies": boolean
  },
  "smoothness": {
    "method": "rAF" | "high_freq" | "low_freq",
    "zero_latency_init": boolean
  }
}
```
