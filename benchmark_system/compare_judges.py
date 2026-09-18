"""Compare the OpenRouter LLM judge audits stored in runs/ against the TypeSafe
(Jev / System One) judge, and write runs/typesafe_comparison.json.

Usage:
    python benchmark_system/compare_judges.py
"""

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from runner import BASE_DIR, RUNS_DIR, calculate_score
from typesafe_judge import evaluate_clock_typesafe


def _as_bool(value):
    if isinstance(value, bool):
        return value
    return None


def _normalized_fields(audit):
    """Flatten an audit to the comparison-ready view: count fields thresholded
    exactly as calculate_score() does, so counts compare as booleans."""
    out = {}
    for sec in ("time", "visual", "dial", "code", "smoothness"):
        block = audit.get(sec, {}) or {}
        for field, value in block.items():
            out[f"{sec}.{field}"] = value

    # Count / numeric fields -> the same boolean the scorer effectively uses.
    if "dial.hour_ticks_count" in out:
        out["dial.hour_ticks_count"] = out["dial.hour_ticks_count"] >= 12
    if "dial.minute_ticks_count" in out:
        out["dial.minute_ticks_count"] = out["dial.minute_ticks_count"] >= 48
    if "dial.numerals_count" in out:
        out["dial.numerals_count"] = out["dial.numerals_count"] >= 12
    if "code.globals_count" in out:
        out["code.globals_count"] = out["code.globals_count"] <= 2
    return out


def _iter_judged_runs():
    for summary_path in sorted(RUNS_DIR.glob("*/summary.json")):
        try:
            with open(summary_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"skip {summary_path}: {e}")
            continue
        entries = []
        if isinstance(data, dict):
            if "audit" in data:
                entries.append(data)
            for r in data.get("results", []) or []:
                if isinstance(r, dict) and "audit" in r:
                    entries.append(r)
        for entry in entries:
            html_path = entry.get("file")
            if not html_path:
                continue
            # summary.json stores repo-relative paths ("runs/<ts>/<model>.html");
            # resolve against the repo root so the script works from any cwd.
            if not os.path.isabs(html_path):
                html_path = os.path.join(BASE_DIR, html_path)
            if not os.path.exists(html_path):
                continue
            yield summary_path, entry, html_path


def main():
    field_stats = {}   # field -> {n, agree}
    rows = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    model_ids = set()

    for summary_path, entry, html_path in _iter_judged_runs():
        with open(html_path, "r") as f:
            html = f.read()

        llm_audit = entry["audit"]
        start = time.time()
        try:
            ts_audit = evaluate_clock_typesafe(html)
        except Exception as e:
            print(f"TypeSafe call failed for {html_path}: {e}")
            continue
        elapsed = time.time() - start
        if not ts_audit:
            print(f"TypeSafe returned no audit for {html_path}")
            continue

        llm_score, _ = calculate_score(llm_audit)
        ts_score, _ = calculate_score(ts_audit)

        llm_f = _normalized_fields(llm_audit)
        ts_f = _normalized_fields(ts_audit)

        disagreements = []
        for field in sorted(set(llm_f) | set(ts_f)):
            if field.startswith("typesafe"):
                continue
            a, b = llm_f.get(field), ts_f.get(field)
            if field not in llm_f or field not in ts_f:
                continue
            stat = field_stats.setdefault(field, {"n": 0, "agree": 0})
            stat["n"] += 1
            if bool(a) == bool(b):
                stat["agree"] += 1
            else:
                disagreements.append(f"{field}: llm={a} typesafe={b}")

        usage = ts_audit.get("typesafe_usage") or {}
        total_usage["input_tokens"] += int(usage.get("input_tokens") or 0)
        total_usage["output_tokens"] += int(usage.get("output_tokens") or 0)
        if ts_audit.get("typesafe_model"):
            model_ids.add(ts_audit["typesafe_model"])

        run_id = str(summary_path.parent)
        rows.append({
            "run": run_id,
            "model": entry.get("model") or entry.get("model_id"),
            "llm_judge": entry.get("judge_model"),
            "llm_score": llm_score,
            "typesafe_score": ts_score,
            "delta": round(ts_score - llm_score, 2),
            "disagreements": disagreements,
            "typesafe_latency_s": round(elapsed, 3),
            "typesafe_usage": usage,
            # Raw Noul probabilities, kept so thresholds can be re-tuned offline.
            "typesafe_probs": ts_audit.get("typesafe_probs", {}),
        })

    out = {
        "typesafe_model": ", ".join(sorted(model_ids)) or None,
        "runs_compared": len(rows),
        "totals": {
            "input_tokens": total_usage["input_tokens"],
            "output_tokens": total_usage["output_tokens"],
        },
        "per_field": [
            {
                "field": field,
                "n": s["n"],
                "agree": s["agree"],
                "disagree": s["n"] - s["agree"],
                "agreement_pct": round(100.0 * s["agree"] / s["n"], 1) if s["n"] else None,
            }
            for field, s in sorted(field_stats.items())
        ],
        "per_run": rows,
    }

    out_path = RUNS_DIR / "typesafe_comparison.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print("\n=== PER-FIELD AGREEMENT (LLM judge vs TypeSafe Jev) ===")
    print(f"{'FIELD':<34}{'N':>4}{'AGREE':>7}{'DISAGREE':>10}{'AGREE %':>10}")
    for row in out["per_field"]:
        print(f"{row['field']:<34}{row['n']:>4}{row['agree']:>7}{row['disagree']:>10}{row['agreement_pct']:>9}%")

    print("\n=== PER-RUN SCORES ===")
    print(f"{'RUN':<20}{'MODEL':<32}{'LLM':>6}{'TYPESAFE':>10}{'DELTA':>8}  DISAGREEING FIELDS")
    for r in rows:
        print(f"{r['run'][-15:]:<20}{str(r['model']):<32}{r['llm_score']:>6}{r['typesafe_score']:>10}{r['delta']:>8}  "
               + ("; ".join(r["disagreements"]) or "-"))

    n_all = sum(s["n"] for s in field_stats.values())
    a_all = sum(s["agree"] for s in field_stats.values())
    print(f"\nRuns compared: {out['runs_compared']} | field checks: {n_all} | "
          f"overall agreement: {100.0 * a_all / n_all:.1f}% "
          f"| model: {out['typesafe_model']} | tokens in/out: "
          f"{out['totals']['input_tokens']}/{out['totals']['output_tokens']}")
    print(f"Wrote {out_path}")

    md_path = BASE_DIR / "docs" / "typesafe-judge-comparison.md"
    md_path.parent.mkdir(exist_ok=True)
    lines = [
        "# TypeSafe Jev judge vs LLM judge",
        "",
        f"Generated by `benchmark_system/compare_judges.py`. Runs compared: {out['runs_compared']}, "
        f"field checks: {n_all}, overall agreement: {100.0 * a_all / n_all:.1f}%, "
        f"model: {out['typesafe_model']}, input tokens: {out['totals']['input_tokens']}.",
        "",
        "Count fields are compared after the same thresholds `calculate_score()` applies "
        "(hour ticks >= 12, minute ticks >= 48, numerals >= 12, globals <= 2).",
        "",
        "## Per-field agreement",
        "",
        "| Field | N | Agree | Disagree | Agreement |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in out["per_field"]:
        lines.append(f"| `{row['field']}` | {row['n']} | {row['agree']} | {row['disagree']} | {row['agreement_pct']}% |")
    lines += [
        "",
        "## Per-run scores (delta = TypeSafe - LLM)",
        "",
        "| Run | Model | LLM judge | LLM | TypeSafe | Delta | Disagreeing fields |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for r in rows:
        dis = "<br>".join(f"`{d}`" for d in r["disagreements"]) or "-"
        lines.append(f"| {r['run'][-15:]} | {r['model']} | {r['llm_judge']} | {r['llm_score']} | "
                     f"{r['typesafe_score']} | {r['delta']} | {dis} |")
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
