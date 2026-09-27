#!/usr/bin/env python3
import sys
import os
import argparse
import datetime
import json
import re
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from benchmark_system.runner import generate_clock, evaluate_clock, evaluate_clock_reliable, calculate_score, fetch_model_pricing, fetch_model_info, _fmt_run_date

LOG_FILE = "log.txt"

_PROVIDER_NAMES = {
    "minimax": "MiniMax",
    "moonshotai": "Kimi",
    "qwen": "Qwen",
    "google": "Gemini",
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "THUDM": "GLM",
    "z-ai": "Zhipu",
    "deepseek": "DeepSeek",
}

_MODEL_ALIASES = {
    "minimax-m3": "M3",
    "minimax-m2.7": "M2.7",
    "minimax-m2.5": "M2.5",
    "minimax-m2": "M2",
    "minimax-m1": "M1",
    "minimax-01": "01",
    "kimi-k2.7-code": "K2.7 Code",
    "kimi-k2.6": "K2.6",
    "kimi-k2.5": "K2.5",
    "qwen3.6-35b-a3b": "3.6 35B A3B",
    "qwen3-coder": "3 Coder",
    "qwen2.5-coder-14b": "2.5 Coder 14B",
    "qwen3.5-9b": "3.5 9B",
    "gemini-2.5-flash": "2.5 Flash",
    "gemini-3-flash-preview": "3 Flash Preview",
    "gemini-3.1-pro": "3.1 Pro",
    "gemini-4.26b-a4b-it-free": "4 26B A4B IT Free",
    "gemini-4-e4b": "4 E4B",
    "gemini-4-e4b-uncensored-hauhaucs-aggressive": "4 E4B Uncensored",
    "claude-sonnet-4.6": "Sonnet 4.6",
    "claude-sonnet-4.5": "Sonnet 4.5",
    "claude-sonnet-4": "Sonnet 4",
    "claude-3.5-haiku": "3.5 Haiku",
    "claude-3.7-sonnet": "3.7 Sonnet",
    "gpt-oss-120b-free": "OSS 120B Free",
    "gpt-oss-20b-free": "OSS 20B Free",
    "gpt-5.4-nano": "5.4 Nano",
    "grok-code-fast-1": "Code Fast 1",
    "dolphin-mistral-24b-venice-edition": "Mistral 24B Venice",
    "nemotron-nano-9b-v2": "Nano 9B v2",
    "gemma-4-31b-it-free": "4 31B IT Free",
    "deepseek-v4-flash": "V4 Flash",
    "deepseek-v4-pro": "V4 Pro",
    "deepseek-v3-flash": "V3 Flash",
}

def model_display_name(model_id):
    if not model_id:
        return ""
    parts = model_id.split("/")
    if len(parts) != 2:
        return model_id
    provider, model = parts
    provider_name = _PROVIDER_NAMES.get(provider, provider.title())
    model_lower = model.lower()
    if model_lower in _MODEL_ALIASES:
        return f"{provider_name} {_MODEL_ALIASES[model_lower]}"
    openrouter_name = fetch_model_info(model_id).get("name")
    if openrouter_name and openrouter_name != model_id:
        # Strip provider prefix if OpenRouter name includes it
        clean_name = openrouter_name
        provider_lower = provider.lower().replace("-", "").replace("_", "")
        prefixes_to_strip = [
            f"{provider}: ",
            f"{provider} ",
            f"{provider.lower()}: ",
            f"{provider.lower()} ",
            f"z-ai: ",
            f"z-ai ",
            f"z.ai: ",
            f"z.ai ",
        ]
        for prefix in prefixes_to_strip:
            if clean_name.lower().startswith(prefix.lower()):
                clean_name = clean_name[len(prefix):]
                break
        # If the clean name already starts with provider_name, don't duplicate
        if clean_name.lower().startswith(provider_name.lower()):
            return clean_name
        # Don't prepend provider if clean_name starts with a known brand name
        brand_names = ["GLM", "Kimi", "Qwen", "Gemini", "GPT", "Claude", "DeepSeek", "MiniMax", "Gemma", "Grok"]
        first_word = clean_name.split()[0] if clean_name else ""
        if first_word in brand_names:
            return clean_name
        return f"{provider_name} {clean_name}"
    model = model.replace("-", " ").replace("_", " ")
    model = re.sub(r'\s+', ' ', model).strip()
    return f"{provider_name} {model}"

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


AUDITS_FILE = "audits.json"


def load_audits():
    """Jev audits keyed by the clock path each card embeds (previews/... or cloud/...)."""
    try:
        with open(AUDITS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_audit(clock_path, audit):
    audits = load_audits()
    audits[clock_path] = audit
    with open(AUDITS_FILE, "w") as f:
        json.dump(audits, f, indent=1, sort_keys=True)


_DIMS = [("time", "Time"), ("visual", "Visual"), ("dial", "Dial"), ("code", "Code"), ("motion", "Motion")]


def _fmt_dim(v):
    return str(int(v)) if float(v) == int(v) else str(v)


def dims_html(breakdown):
    cells = []
    for key, label in _DIMS:
        v = breakdown[key]
        cls = "good" if v >= 10 else ("warn" if v >= 6 else "bad")
        cells.append(f'<div class="dim {cls}"><span>{label}</span><b>{_fmt_dim(v)}</b></div>')
    return '<div class="dims">' + "".join(cells) + "</div>"


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def why_html(audit):
    """Plain-language account of the score, derived from the same audit fields
    calculate_score() reads, so the text can't drift from the number."""
    t, v, d, c, s = (audit.get(k, {}) for k in ("time", "visual", "dial", "code", "smoothness"))
    rendered = (audit.get("render_check") or {}).get("ok")
    # (dimension summary when perfect, [(passed, win text, loss text, overall points)])
    checks = [
        ("correct, continuous time math", [
            (t.get("hour_continuous"), "continuous hour hand", "hour hand jumps between hours", 0.75),
            (t.get("minute_continuous"), "continuous minute hand", "minute hand jumps each minute", 0.75),
            (t.get("second_ms_precision"), "millisecond-precise second hand", "second hand ignores milliseconds", 0.75),
            (t.get("correct_12_top"), *(("hands verified at the right time when rendered",
                                         "hands show the wrong time when rendered")
                                        if rendered is not None else ("12 at the top", "12 is not at the top")), 0.75),
        ]),
        ("full visual finish (shadows, gradients, bezel, center cap, hand tails)", [
            (v.get("has_shadows"), "shadows", "no shadows", 0.4),
            (v.get("has_gradients"), "gradients", "no gradients", 0.4),
            (v.get("has_bezel"), "a bezel", "no bezel", 0.4),
            (v.get("has_center_cap"), "a center cap", "no center cap", 0.4),
            (v.get("has_hand_tails"), "hand tails", "no hand tails", 0.4),
        ]),
        ("a complete, loop-generated dial with numerals", [
            (d.get("hour_ticks_count", 0) >= 12, "all 12 hour ticks", "missing hour ticks", 0.3),
            (d.get("minute_ticks_count", 0) >= 48, "minute ticks", "no minute ticks", 0.3),
            (d.get("numerals_count", 0) >= 12, "numerals", "no numerals", 0.3),
            (d.get("automated_marker_generation"), "loop-generated markers", "hand-placed markers", 0.3),
            (d.get("skips_minute_at_hour"), "minute ticks that skip the hours", "minute ticks overlap hour ticks", 0.3),
        ]),
        ("clean code (scoped, responsive, helpers, no dependencies)", [
            (c.get("globals_count", 99) <= 2, "no global leaks", "leaks globals", 0.45),
            (c.get("is_responsive"), "responsive sizing", "fixed size", 0.45),
            (c.get("uses_helpers"), "helper functions", "no helper functions", 0.3),
            (c.get("zero_dependencies"), "no dependencies", "external dependencies", 0.3),
        ]),
    ]
    method = s.get("method")
    motion_checks = [
        (method == "rAF", "a smooth requestAnimationFrame sweep",
         "fast setInterval instead of rAF" if method == "high_freq" else "second hand ticks once a second",
         0.3 if method == "high_freq" else 0.8),
        (s.get("zero_latency_init"), "the right time on the first frame", "wrong or blank first frame", 1.0),
    ]
    checks.append(("a smooth rAF sweep that is right from the first frame", motion_checks))

    wins, losses = [], []
    for summary, items in checks:
        if all(ok for ok, *_ in items):
            wins.append(summary)
            continue
        passed = [win for ok, win, _, _ in items if ok]
        if passed:
            wins.append(_join(passed))
        losses += [(pts, loss) for ok, _, loss, pts in items if not ok]
    if method == "high_freq":
        wins.append("fast-interval motion")

    parts = []
    if wins:
        text = "; ".join(wins)
        parts.append(f"<b>Earned:</b> {text[0].upper() + text[1:]}.")
    if losses:
        losses.sort(key=lambda x: -x[0])
        lost = round(sum(p for p, _ in losses), 2)
        items = ", ".join(f"{loss} (−{p:g})" for p, loss in losses)
        parts.append(f"<b>Lost {lost:g}:</b> {items[0].upper() + items[1:]}.")
    else:
        parts.append("<b>Lost nothing</b> on the rubric.")
    return '<p class="why">' + " ".join(parts) + "</p>"


def make_verdict(breakdown, audit=None, model_id=None, run_date=None, latency=None,
                 actual_cost=None, judge_runs=None, judge_runs_attempted=None, original=None,
                 source=None, cost_estimated=False):
    meta = []
    if model_id:
        meta.append(f'<span class="model-id">{model_id}</span>')
    if source:
        meta.append(f"<span>{source}</span>")
    if run_date:
        meta.append(f"<span>Ran {run_date if not str(run_date)[:1].isdigit() else _fmt_run_date(run_date)}</span>")
    if latency is not None:
        meta.append(f"<span>Latency {latency}s</span>")
    if actual_cost is not None:
        meta.append(f'<span title="{EST_NOTE}">Cost {fmt_cost(actual_cost, True)}</span>' if cost_estimated
                    else f"<span>Cost {fmt_cost(actual_cost)}</span>")
    if judge_runs is not None:
        meta.append(f"<span>Judge runs {judge_runs}/{judge_runs_attempted or judge_runs}</span>")
    out = ['      <div class="verdict">', f"        {dims_html(breakdown)}"]
    if audit:
        out.append(f"        {why_html(audit)}")
    if meta:
        out.append('        <div class="meta">' + "".join(meta) + "</div>")
    if original:
        out.append(f'        <details class="orig"><summary>Original review (may describe an earlier score)</summary>{original}</details>')
    out.append("      </div>")
    return "\n".join(out)


# Cost floor for runs without billed usage (subscription runs, or runs whose
# usage wasn't captured): a model must at least emit the clock's HTML, so
# HTML tokens (~3.3 chars/token for these files) at the listed output price is
# a true lower bound. Hidden reasoning is billed on top and varies wildly: 1.1-
# 1.5x the HTML on older runs, 3-6x for heavy reasoners, and the seven models
# added 2026-09-26 billed ~10x their floor combined. So only the floor is shown.
EST_CHARS_PER_TOKEN = 3.3
EST_PROMPT_TOKENS = 30
EST_NOTE = ("Lower bound: the clock's HTML as output tokens at the listed API price. "
            "Reasoning tokens are billed on top and often cost several times more.")


def estimate_cost(html, pricing):
    if not pricing or pricing.get("input_per_m") is None:
        return None
    out_tokens = len(html) / EST_CHARS_PER_TOKEN
    return round((EST_PROMPT_TOKENS * pricing["input_per_m"] + out_tokens * pricing["output_per_m"]) / 1e6, 4)


def fmt_cost(cost, estimated=False):
    if cost is None:
        return "—"
    return f"≥${cost:.4f}" if estimated else f"${cost:.4f}"


def _make_table_row(model, rank, score, breakdown, latency=None, pricing=None,
                    actual_cost=None, model_id=None, run_date=None,
                    judge_runs=None, judge_runs_attempted=None, display_name=None, cost_estimated=False):
    score_class, badge_class = score_to_grade(score)
    overall_color = _OVERALL_COLORS[score_class]
    latency_str = f"{latency}s" if latency is not None else "—"
    run_date_str = _fmt_run_date(run_date) if run_date else "—"
    runs = judge_runs if judge_runs is not None else '—'
    runs_att = judge_runs_attempted if judge_runs_attempted is not None else runs
    runs_str = f"{runs}/{runs_att}" if runs != '—' else '—'
    cost_str = fmt_cost(actual_cost, cost_estimated)
    cost_attr = f' title="{EST_NOTE}"' if cost_estimated and actual_cost is not None else ""
    model_id_str = model_id or ""
    display = display_name or model

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
        f'        <td><div><a href="#card-{model_id_str}" class="model-link">{display}</a></div><span class="model-id">{model_id_str}</span></td>\n'
        f'        <td class="r run-date">{run_date_str}</td>\n'
        f'        <td class="r">{breakdown["time"]}</td>'
        f'<td class="r">{breakdown["visual"]}</td>'
        f'<td class="r">{breakdown["dial"]}</td>'
        f'<td class="r">{breakdown["code"]}</td>'
        f'<td class="r">{breakdown["motion"]}</td>\n'
        f'        <td class="r runs">{runs_str}</td>\n'
        f'        <td class="r overall" style="color:{overall_color}">{score}</td>\n'
        f'        <td class="r act-cost{" est" if cost_estimated else ""}"{cost_attr}>{cost_str}</td>\n'
        f'        {cost_td}\n'
        f'        {input_td}\n'
        f'        {output_td}\n'
        f'        <td class="r latency">{latency_str}</td>\n'
        f'      </tr>'
    )


def _make_card(model, rank, score, breakdown, file_path, timestamp, latency=None,
               model_id=None, run_date=None, actual_cost=None,
               judge_runs=None, judge_runs_attempted=None, display_name=None, audit=None,
                 cost_estimated=False):
    score_class, _ = score_to_grade(score)
    # Previews must live in a committed dir; runs/ is gitignored so iframes
    # pointing there 404 on GitHub Pages. Copy the generated HTML into previews/.
    basename = os.path.basename(file_path)
    previews_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "previews")
    os.makedirs(previews_dir, exist_ok=True)
    try:
        shutil.copyfile(file_path, os.path.join(previews_dir, basename))
    except (OSError, shutil.SameFileError):
        pass
    relative_path = f"previews/{basename}"
    display = display_name or model
    verdict = make_verdict(breakdown, audit, model_id=model_id, run_date=run_date, latency=latency,
                           actual_cost=actual_cost, judge_runs=judge_runs,
                           judge_runs_attempted=judge_runs_attempted, cost_estimated=cost_estimated)
    return (
        f'    <div class="card" id="card-{model_id or ""}">\n'
        f'      <header>\n'
        f'        <span class="name">{display}</span>\n'
        f'        <span class="score {score_class}">#{rank} · {score}</span>\n'
        f'      </header>\n'
        f'      <iframe src="{relative_path}"></iframe>\n'
        f'{verdict}\n'
        f'    </div>'
    )


def update_index(model, score, breakdown, file_path, timestamp, latency=None, pricing=None,
                 actual_cost=None, model_id=None, run_date=None,
                 judge_runs=None, judge_runs_attempted=None, display_name=None, audit=None,
                 cost_estimated=False):
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
        scored_rows.append([score, _make_table_row(model, 0, score, breakdown, latency, pricing,
                                                   actual_cost=actual_cost, model_id=model_id,
                                                   run_date=run_date, judge_runs=judge_runs,
                                                   judge_runs_attempted=judge_runs_attempted,
                                                   display_name=display_name, cost_estimated=cost_estimated)])
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

        # Split on card boundaries (4-space indented opening tag, with or without an id)
        card_pieces = re.split(r'(?=    <div class="card"[ >])', grid_content)
        scored_cards = []
        for piece in card_pieces:
            piece = piece.strip()
            if not piece:
                continue
            m = re.search(r'#\d+ · ([\d.]+)', piece)
            if m:
                scored_cards.append([float(m.group(1)), piece])

        scored_cards.append([score, _make_card(model, 0, score, breakdown, file_path, timestamp, latency,
                                               model_id=model_id, run_date=run_date, actual_cost=actual_cost,
                                               judge_runs=judge_runs, judge_runs_attempted=judge_runs_attempted,
                                               display_name=display_name, audit=audit,
                                               cost_estimated=cost_estimated)])
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
    parser.add_argument("--judge", default="typesafe/jev",
                        help="Judge model ID (default: typesafe/jev; any OpenRouter model id also works)")
    parser.add_argument("--no-index", action="store_true",
                        help="Skip updating index.html after benchmark")
    parser.add_argument("--judge-runs", type=int, default=3,
                        help="Number of judge evaluation runs to aggregate (default: 3)")
    args = parser.parse_args()

    model = args.model
    judge = args.judge

    log(f"Adding model: {model}")

    print(f"\nGenerating clock with {model}...")
    html, latency_s, usage = generate_clock(model)
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

    pricing = fetch_model_pricing(model)
    actual_cost = None
    if usage and pricing.get('input_per_m') is not None:
        inp = usage.get('prompt_tokens', 0) * pricing['input_per_m'] / 1_000_000
        out = usage.get('completion_tokens', 0) * pricing.get('output_per_m', 0) / 1_000_000
        actual_cost = round(inp + out, 6)
    cost_estimated = False
    if actual_cost is None:
        actual_cost = estimate_cost(html, pricing)
        cost_estimated = actual_cost is not None

    print(f"Evaluating with judge {judge}...")
    audit, judge_runs_completed = evaluate_clock_reliable(judge, html, n_runs=args.judge_runs)
    if not audit:
        log("ERROR: Evaluation failed")
        sys.exit(1)

    score, breakdown = calculate_score(audit)
    log(f"Score: {score} | Time:{breakdown['time']} Visual:{breakdown['visual']} Dial:{breakdown['dial']} Code:{breakdown['code']} Motion:{breakdown['motion']} | Latency:{latency_s}s | Cost:${actual_cost or 0:.4f} | Runs:{judge_runs_completed}/{args.judge_runs}")

    result = {
        "model": model,
        "model_id": model,
        "judge_model": judge,
        "timestamp": ts,
        "run_date": ts,
        "file": file_path,
        "score": score,
        "breakdown": breakdown,
        "audit": audit,
        "latency_s": latency_s,
        "pricing": pricing,
        "actual_cost": actual_cost,
        "cost_estimated": cost_estimated,
        "token_usage": usage,
        "judge_runs": judge_runs_completed,
        "judge_runs_attempted": args.judge_runs,
    }

    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(result, f, indent=2)

    if not args.no_index:
        display_name = model_display_name(model)
        update_index(model, score, breakdown, file_path, ts, latency=latency_s, pricing=pricing,
                     actual_cost=actual_cost, model_id=model, run_date=ts,
                     judge_runs=judge_runs_completed, judge_runs_attempted=args.judge_runs,
                     display_name=display_name, audit=audit, cost_estimated=cost_estimated)
        save_audit("previews/" + os.path.basename(file_path), audit)

    print(f"\nDone! Score: {score}")
    print(f"Clock saved to: {file_path}")

if __name__ == "__main__":
    main()