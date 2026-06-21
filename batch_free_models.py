#!/usr/bin/env python3
"""
Batch runner for all free OpenRouter models.
Rate-limit aware: pauses 3-4s between calls, saves progress for resume.
"""
import sys
import os
import json
import time
import datetime
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from benchmark_system.runner import generate_clock, evaluate_clock, calculate_score

PROGRESS_FILE = "batch_progress.json"

def fetch_free_models(api_key):
    import requests
    resp = requests.get("https://openrouter.ai/api/v1/models", headers={
        "Authorization": f"Bearer {api_key}"
    })
    resp.raise_for_status()
    models = resp.json()["data"]
    free = []
    for m in models:
        pid = m["id"]
        pricing = m.get("pricing", {})
        pc = float(pricing.get("prompt", 1))
        cc = float(pricing.get("completion", 1))
        if ":free" in pid or (pc == 0 and cc == 0):
            free.append(pid)
    return sorted(free)

def filter_suitable(model_ids):
    skip_patterns = [
        "content-safety",
        "lyria",
        "owl-alpha",
        "openrouter/free",
    ]
    return [m for m in model_ids if not any(p in m for p in skip_patterns)]

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "remaining": [], "judge": None}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Batch benchmark all free OpenRouter models")
    parser.add_argument("--judge", default="anthropic/claude-3.7-sonnet",
                        help="Judge model (default: anthropic/claude-3.7-sonnet)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from saved progress")
    parser.add_argument("--delay", type=float, default=3.5,
                        help="Delay between API calls in seconds (default: 3.5)")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip updating index.html")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set in .env")
        sys.exit(1)

    if args.resume and os.path.exists(PROGRESS_FILE):
        progress = load_progress()
        print(f"Resuming from saved progress ({len(progress['completed'])} completed, {len(progress['remaining'])} remaining)")
        models = progress["remaining"]
        completed = set(progress["completed"])
        failed = set(progress["failed"])
        judge = progress.get("judge", args.judge)
    else:
        print("Fetching free models from OpenRouter...")
        all_free = fetch_free_models(api_key)
        models = filter_suitable(all_free)
        print(f"\nFound {len(all_free)} free models, {len(models)} suitable for benchmarking:")
        for i, m in enumerate(models, 1):
            print(f"  {i:2d}. {m}")
        judge = args.judge
        completed = set()
        failed = set()

        print(f"\nJudge: {judge}")
        print(f"Delay: {args.delay}s between API calls")
        print(f"Estimated time: ~{len(models) * 2 * args.delay / 60:.1f} min for {len(models)} models\n")

        cont = input("Start benchmark? (Y/n): ").strip().lower()
        if cont == "n":
            print("Aborted.")
            return

    total = len(models) + len(completed) + len(failed)
    start_time = time.time()
    batch_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join("runs", f"batch_{batch_ts}")
    os.makedirs(run_dir, exist_ok=True)

    for idx, model in enumerate(models, 1):
        print(f"\n{'='*60}")
        print(f"[{len(completed)+1}/{total}] {model}")

        # Step 1: Generate clock
        print(f"  -> Generating clock...")
        gen_start = time.time()
        html, latency_s, usage = generate_clock(model)
        gen_elapsed = time.time() - gen_start

        if not html:
            print(f"  !! Generation FAILED for {model}")
            failed.add(model)
            progress = {
                "completed": list(completed),
                "failed": list(failed),
                "remaining": models[idx:],
                "judge": judge
            }
            save_progress(progress)
            time.sleep(args.delay)
            continue

        safe_name = model.replace("/", "_").replace(":", "_").replace(".", "_").replace("*", "_")
        file_path = os.path.join(run_dir, f"{safe_name}.html")
        with open(file_path, "w") as f:
            f.write(html)

        # Rate limit pause before judge call
        time.sleep(args.delay)

        # Step 2: Evaluate
        print(f"  -> Evaluating with judge ({judge})...")
        eval_start = time.time()
        audit = evaluate_clock(judge, html)
        eval_elapsed = time.time() - eval_start

        if not audit:
            print(f"  !! Evaluation FAILED for {model}")
            failed.add(model)
            progress = {
                "completed": list(completed),
                "failed": list(failed),
                "remaining": models[idx:],
                "judge": judge
            }
            save_progress(progress)
            time.sleep(args.delay)
            continue

        score, breakdown = calculate_score(audit)
        print(f"  -> Score: {score}  (time={breakdown['time']} visual={breakdown['visual']} dial={breakdown['dial']} code={breakdown['code']} motion={breakdown['motion']})")
        print(f"  -> Gen: {gen_elapsed:.0f}s | Eval: {eval_elapsed:.0f}s")

        model_id = model.replace(":free", "")
        result = {
            "model": model_id,
            "judge_model": judge,
            "timestamp": batch_ts,
            "file": file_path,
            "score": score,
            "breakdown": breakdown,
            "audit": audit,
            "latency_s": latency_s,
            "token_usage": usage,
        }
        with open(os.path.join(run_dir, "summary.json"), "w") as f:
            json.dump(result, f, indent=2)

        # Update index if needed
        if not args.no_index:
            try:
                from add_model import update_index, model_display_name
                update_index(
                    model_id, score, breakdown, file_path, f"batch_{batch_ts}",
                    latency=latency_s, model_id=model_id, run_date=batch_ts,
                    display_name=model_display_name(model_id),
                )
            except Exception as e:
                print(f"  Warning: index update ({e})")

        completed.add(model)
        progress = {
            "completed": list(completed),
            "failed": list(failed),
            "remaining": models[idx:],
            "judge": judge
        }
        save_progress(progress)

        # Rate limit pause before next model
        if idx < len(models):
            pause = args.delay + 1.0
            print(f"  -> Waiting {pause:.0f}s before next model...")
            time.sleep(pause)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Done! {len(completed)} completed, {len(failed)} failed in {elapsed/60:.1f} min")
    print(f"Completed: {', '.join(sorted(completed))}")
    if failed:
        print(f"Failed: {', '.join(sorted(failed))}")

    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("Progress file cleaned up.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\nInterrupted. Progress saved to {PROGRESS_FILE}. Resume with: python batch_free_models.py --resume")
        sys.exit(0)
