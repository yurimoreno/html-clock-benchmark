#!/usr/bin/env python3
"""Build and judge a clock from a locally-served model, as two independent steps.

The build step only talks to the local model and saves the clock plus a
metadata file. The judge step only reads the saved clock. Either can be
re-run without the other, so a judge failure never costs a regeneration.

Usage:
  python local_add.py build http://localhost:8888/v1/chat/completions qwen3.8-flash-next ["recipe notes"]
  python local_add.py judge qwen3.8-flash-next [runs]
"""
import json
import os
import re
import socket
import sys
import time
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
LOCAL = os.path.join(ROOT, "local ")


def paths(model):
    base = os.path.join(LOCAL, model)
    return base + ".html", base + ".build.json", base + ".judge.json"


def server_info(url):
    """Which machine and server build answered, recorded next to every clock."""
    import requests
    host = urlparse(url).hostname
    machine = socket.gethostname() if host in ("localhost", "127.0.0.1", "::1") else host
    base = url.split("/v1/")[0]
    info = {"machine": machine}
    try:
        info["server_version"] = requests.get(base + "/version", timeout=5).json().get("version")
    except Exception:
        pass
    try:
        m = requests.get(base + "/v1/models", timeout=5).json()["data"][0]
        info["model_path"] = m.get("root")
        info["max_model_len"] = m.get("max_model_len")
    except Exception:
        pass
    return info


def build(url, model, recipe=None):
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
        **server_info(url),
        "recipe": recipe,
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


def judge(model, runs=1):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
    sys.path.insert(0, os.path.join(ROOT, "benchmark_system"))
    from runner import evaluate_clock_reliable, calculate_score

    html_path, _, judge_path = paths(model)
    with open(html_path) as f:
        html = f.read()

    audit, runs_done = evaluate_clock_reliable("typesafe/jev", html, n_runs=runs)
    score, breakdown = calculate_score(audit)
    result = {
        "model": model,
        "judged_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "judge": "typesafe/jev",
        "judge_runs": f"{runs_done}/{runs}",
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
    if len(sys.argv) in (4, 5) and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) == 5 else None)
    elif len(sys.argv) in (3, 4) and sys.argv[1] == "judge":
        judge(sys.argv[2], int(sys.argv[3]) if len(sys.argv) == 4 else 1)
    else:
        sys.exit(__doc__)
