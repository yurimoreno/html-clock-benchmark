#!/usr/bin/env python3
"""Build and judge a clock from a locally-served model, as two independent steps.

The build step only talks to the local model and saves the clock plus a
metadata file. The judge step only reads the saved clock. Either can be
re-run without the other, so a judge failure never costs a regeneration.

Usage:
  python local_add.py build http://localhost:8888/v1/chat/completions qwen3.8-flash-next
  python local_add.py judge qwen3.8-flash-next
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(ROOT, "local ")


def paths(model):
    base = os.path.join(LOCAL, model)
    return base + ".html", base + ".build.json", base + ".judge.json"


def build(url, model):
    import requests
    sys.path.insert(0, os.path.join(ROOT, "benchmark_system"))
    from runner import PROMPT

    t0 = time.time()
    resp = requests.post(url, json={
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 32768,
    }, timeout=1800)
    resp.raise_for_status()
    latency = time.time() - t0

    data = resp.json()
    choice = data["choices"][0]
    content = (choice["message"].get("content") or "").strip()

    # strip ```html fences the same way runner.generate_clock does
    m = re.search(r"```(?:html)?\s*(.*?)```", content, re.S)
    html = m.group(1).strip() if m else content

    html_path, build_path, _ = paths(model)
    with open(html_path, "w") as f:
        f.write(html)
    meta = {
        "model": model,
        "url": url,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "latency_s": round(latency, 1),
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage", {}),
        "html_bytes": len(html),
    }
    with open(build_path, "w") as f:
        json.dump(meta, f, indent=1)

    print(json.dumps(meta, indent=1))
    print(f"SAVED: {html_path}")
    if meta["finish_reason"] == "length":
        print("WARNING: generation hit the token limit, clock is likely truncated")


def judge(model):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    sys.path.insert(0, os.path.join(ROOT, "benchmark_system"))
    from runner import evaluate_clock_reliable, calculate_score

    html_path, _, judge_path = paths(model)
    with open(html_path) as f:
        html = f.read()

    audit, runs = evaluate_clock_reliable("typesafe/jev", html, n_runs=1)
    score, breakdown = calculate_score(audit)
    result = {
        "model": model,
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "judge": "typesafe/jev",
        "score": score,
        "breakdown": breakdown,
        "audit": audit,
    }
    with open(judge_path, "w") as f:
        json.dump(result, f, indent=1)

    print(f"SCORE: {score}")
    print(f"BREAKDOWN: {json.dumps(breakdown)}")
    print(f"SAVED: {judge_path}")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "judge":
        judge(sys.argv[2])
    else:
        sys.exit(__doc__)
