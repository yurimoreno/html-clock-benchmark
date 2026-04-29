#!/usr/bin/env python3
import sys
import os
import argparse
import datetime
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmark_system.runner import generate_clock, evaluate_clock, calculate_score

LOG_FILE = "log.txt"

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")

def score_to_grade(score):
    if score >= 9: return "s-1", "b-1"
    if score >= 8.5: return "s-2", "b-2"
    if score >= 7: return "s-3", "b-3"
    if score >= 6: return "s-4", "b-4"
    return "s-5", "b-5"

def update_index(model, score, breakdown, file_path, timestamp):
    index_path = "index.html"
    if not os.path.exists(index_path):
        print(f"Warning: {index_path} not found, skipping index update")
        return

    with open(index_path, "r") as f:
        content = f.read()

    rank = 1
    rank_pattern = re.compile(r'<td><span class="badge b-1">(\d+)</span></td>')
    for m in rank_pattern.finditer(content):
        rank = max(rank, int(m.group(1)) + 1)

    score_class, badge_class = score_to_grade(score)
    model_file_name = os.path.basename(file_path)
    relative_path = f"runs/{timestamp}/{model_file_name}"

    card = f"""
    <div class="card" data-new="true">
      <header>
        <span class="name">{model}</span>
        <span class="score {score_class}">#{rank} · {score}</span>
      </header>
      <iframe src="{relative_path}"></iframe>
      <div class="verdict">New model added via CLI. Score: {score} | Time:{breakdown['time']} Visual:{breakdown['visual']} Dial:{breakdown['dial']} Code:{breakdown['code']} Motion:{breakdown['motion']}</div>
    </div>
"""

    content = content.replace("  <div class=\"grid\">\n    <div class=\"card\">",
                              "  <div class=\"grid\">\n" + card.strip() + "\n    <div class=\"card\">")

    with open(index_path, "w") as f:
        f.write(content)
    print(f"Updated index.html with new model card")

def main():
    parser = argparse.ArgumentParser(description="Add a model to the HTML Clock Benchmark")
    parser.add_argument("model", help="Model ID to benchmark (e.g. google/gemini-2.5-flash)")
    parser.add_argument("--judge", default="anthropic/claude-3.7-sonnet",
                        help="Judge model ID (default: anthropic/claude-3.7-sonnet)")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip updating index.html after benchmark")
    args = parser.parse_args()

    model = args.model
    judge = args.judge

    log(f"Adding model: {model}")

    print(f"\nGenerating clock with {model}...")
    html = generate_clock(model)
    if not html:
        log("ERROR: Clock generation failed")
        sys.exit(1)

    safe_name = model.replace("/", "_").replace(":", "_")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join("runs", ts)
    os.makedirs(run_dir, exist_ok=True)
    file_path = os.path.join(run_dir, f"{safe_name}.html")

    with open(file_path, "w") as f:
        f.write(html)
    log(f"Clock saved to {file_path}")

    print(f"Evaluating with judge {judge}...")
    audit = evaluate_clock(judge, html)
    if not audit:
        log("ERROR: Evaluation failed")
        sys.exit(1)

    score, breakdown = calculate_score(audit)
    log(f"Score: {score} | Time:{breakdown['time']} Visual:{breakdown['visual']} Dial:{breakdown['dial']} Code:{breakdown['code']} Motion:{breakdown['motion']}")

    result = {
        "model": model,
        "judge_model": judge,
        "timestamp": ts,
        "file": file_path,
        "score": score,
        "breakdown": breakdown,
        "audit": audit
    }

    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(result, f, indent=2)

    if not args.no_index:
        update_index(model, score, breakdown, file_path, ts)

    print(f"\nDone! Score: {score}")
    print(f"Clock saved to: {file_path}")

if __name__ == "__main__":
    main()