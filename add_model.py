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
    if score >= 9.0: return "s-1", "b-1"
    if score >= 8.5: return "s-2", "b-2"
    if score >= 8.0: return "s-3", "b-3"
    if score >= 7.0: return "s-4", "b-4"
    return "s-5", "b-5"

_OVERALL_COLORS = {
    "s-1": "#d6f5d6", "s-2": "#dff5c6", "s-3": "#f5edd6",
    "s-4": "#f5dcc6", "s-5": "#f5c6c6"
}


def _cost_eff_class(cost_per_score):
    if cost_per_score is None:
        return "cost-eff"
    if cost_per_score <= 0.40:
        return "cost-eff green"
    if cost_per_score <= 0.80:
        return "cost-eff yellow"
    return "cost-eff red"


def _fmt_price(val):
    if val is None:
        return "—"
    return f"${int(val)}/M" if val == int(val) else f"${val}/M"


def _make_table_row(model, rank, score, breakdown, latency=None, pricing=None):
    score_class, badge_class = score_to_grade(score)
    overall_color = _OVERALL_COLORS[score_class]
    latency_str = f"{latency}s" if latency is not None else "—"

    if pricing and pricing.get("input_per_m") is not None:
        inp, out = pricing["input_per_m"], pricing["output_per_m"]
        cost_per_score = round((inp + out) / score, 2) if score else None
        cost_td = f'<td class="{_cost_eff_class(cost_per_score)}">${cost_per_score}</td>'
        input_td = f'<td class="price">{_fmt_price(inp)}</td>'
        output_td = f'<td class="price">{_fmt_price(out)}</td>'
    else:
        cost_td = '<td class="cost-eff">—</td>'
        input_td = '<td class="price">—</td>'
        output_td = '<td class="price">—</td>'

    return (
        f'      <tr>\n'
        f'        <td><span class="badge {badge_class}">{rank}</span></td>\n'
        f'        <td>{model}</td>\n'
        f'        <td class="r">{breakdown["time"]}</td>'
        f'<td class="r">{breakdown["visual"]}</td>'
        f'<td class="r">{breakdown["dial"]}</td>'
        f'<td class="r">{breakdown["code"]}</td>'
        f'<td class="r">{breakdown["motion"]}</td>\n'
        f'        <td class="r overall" style="color:{overall_color}">{score}</td>\n'
        f'        {cost_td}\n'
        f'        {input_td}\n'
        f'        {output_td}\n'
        f'        <td class="r latency">{latency_str}</td>\n'
        f'      </tr>'
    )


def _make_card(model, rank, score, breakdown, file_path, timestamp, latency=None):
    score_class, _ = score_to_grade(score)
    relative_path = f"runs/{timestamp}/{os.path.basename(file_path)}"
    latency_note = f" | Latency: {latency}s" if latency is not None else ""
    return (
        f'    <div class="card">\n'
        f'      <header>\n'
        f'        <span class="name">{model}</span>\n'
        f'        <span class="score {score_class}">#{rank} · {score}</span>\n'
        f'      </header>\n'
        f'      <iframe src="{relative_path}"></iframe>\n'
        f'      <div class="verdict">Score: {score} | '
        f'Time:{breakdown["time"]} Visual:{breakdown["visual"]} '
        f'Dial:{breakdown["dial"]} Code:{breakdown["code"]} '
        f'Motion:{breakdown["motion"]}{latency_note}</div>\n'
        f'    </div>'
    )


def update_index(model, score, breakdown, file_path, timestamp, latency=None, pricing=None):
    index_path = "index.html"
    if not os.path.exists(index_path):
        print(f"Warning: {index_path} not found, skipping index update")
        return

    with open(index_path, "r") as f:
        content = f.read()

    # ── 1. Update the cloud table tbody ──────────────────────────────────────
    tbody_match = re.search(
        r'(<table id="cloud-table"[^>]*>.*?<tbody>)(.*?)(</tbody>)',
        content, re.DOTALL
    )
    if tbody_match:
        existing_rows = re.findall(r'<tr>.*?</tr>', tbody_match.group(2), re.DOTALL)
        scored_rows = []
        for row in existing_rows:
            m = re.search(r'<td class="r overall"[^>]*>([\d.]+)</td>', row)
            if m:
                scored_rows.append([float(m.group(1)), row.strip()])

        # Append new row (rank=0 placeholder; will be overwritten below)
        scored_rows.append([score, _make_table_row(model, 0, score, breakdown, latency, pricing)])
        scored_rows.sort(key=lambda x: x[0], reverse=True)

        # Renumber all ranks
        new_rows_html = []
        for i, (s, row) in enumerate(scored_rows):
            rank_num = i + 1
            sc, bc = score_to_grade(s)
            row = re.sub(
                r'<span class="badge [^"]*">\d+</span>',
                f'<span class="badge {bc}">{rank_num}</span>',
                row
            )
            new_rows_html.append("      " + row)

        new_tbody = (
            tbody_match.group(1) + "\n"
            + "\n".join(new_rows_html) + "\n    "
            + tbody_match.group(3)
        )
        content = content[:tbody_match.start()] + new_tbody + content[tbody_match.end():]

    # ── 2. Update the cloud card grid ────────────────────────────────────────
    # Match the grid inside data-tab="cloud"
    grid_match = re.search(
        r'(<div data-tab="cloud"[^>]*>.*?<div class="grid">)(.*?)(</div>\s*\n</div>)',
        content, re.DOTALL
    )
    if grid_match:
        grid_content = grid_match.group(2)

        # Split on card boundaries (4-space indented opening tag)
        card_pieces = re.split(r'(?=    <div class="card">)', grid_content)
        scored_cards = []
        for piece in card_pieces:
            piece = piece.strip()
            if not piece:
                continue
            m = re.search(r'#\d+ · ([\d.]+)', piece)
            if m:
                scored_cards.append([float(m.group(1)), piece])

        scored_cards.append([score, _make_card(model, 0, score, breakdown, file_path, timestamp, latency)])
        scored_cards.sort(key=lambda x: x[0], reverse=True)

        # Renumber ranks in cards
        final_cards = []
        for i, (s, card) in enumerate(scored_cards):
            rank_num = i + 1
            sc, _ = score_to_grade(s)
            card = re.sub(r'#\d+ · ([\d.]+)', f'#{rank_num} · \\1', card)
            card = re.sub(r'class="score s-\d+"', f'class="score {sc}"', card)
            final_cards.append("    " + card.strip())

        new_grid = "\n" + "\n".join(final_cards) + "\n  "
        content = (
            content[:grid_match.start(2)]
            + new_grid
            + content[grid_match.end(2):]
        )

    with open(index_path, "w") as f:
        f.write(content)
    print(f"Updated index.html — inserted {model} at correct rank position")

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
    html, latency_s = generate_clock(model)
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
    log(f"Score: {score} | Time:{breakdown['time']} Visual:{breakdown['visual']} Dial:{breakdown['dial']} Code:{breakdown['code']} Motion:{breakdown['motion']} | Latency:{latency_s}s")

    result = {
        "model": model,
        "judge_model": judge,
        "timestamp": ts,
        "file": file_path,
        "score": score,
        "breakdown": breakdown,
        "audit": audit,
        "latency_s": latency_s,
    }

    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(result, f, indent=2)

    if not args.no_index:
        from benchmark_system.runner import fetch_model_pricing
        pricing = fetch_model_pricing(model)
        update_index(model, score, breakdown, file_path, ts, latency=latency_s, pricing=pricing)

    print(f"\nDone! Score: {score}")
    print(f"Clock saved to: {file_path}")

if __name__ == "__main__":
    main()