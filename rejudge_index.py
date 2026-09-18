#!/usr/bin/env python3
"""Re-judge every cloud leaderboard entry in index.html with the TypeSafe Jev judge.

Each card in the cloud tab embeds its clock file (previews/... or cloud/...),
so the page itself is the source of truth for which HTML to audit. For every
entry this script runs typesafe_judge.evaluate_clock_typesafe() on that file,
recomputes the rubric score with runner.calculate_score(), then rewrites the
matching table row and card in place (dimension cells, overall, runs, rank)
and re-sorts both by the new score. Prose in card verdicts is left alone.

Usage:
    python rejudge_index.py --dry-run     # print before/after, touch nothing
    python rejudge_index.py               # rewrite index.html, write docs/rejudge-<date>.md
"""

import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_system"))

from runner import calculate_score  # noqa: E402
from typesafe_judge import evaluate_clock_typesafe  # noqa: E402
from add_model import _OVERALL_COLORS, score_to_grade  # noqa: E402

INDEX = "index.html"
ROW_RE = re.compile(r"<tr>.*?</tr>", re.S)
TBODY_RE = re.compile(r'(<table id="cloud-table"[^>]*>.*?<tbody>)(.*?)(</tbody>)', re.S)
GRID_RE = re.compile(r'(<div data-tab="cloud"[^>]*>.*?<div class="grid">)(.*?)(</div>\s*\n</div>)', re.S)


def _strip(html):
    return re.sub(r"<[^>]+>", "", html).strip()


def _fmt(v):
    return f"{v:.1f}" if isinstance(v, float) else str(v)


def parse_rows(tbody):
    rows = []
    for r in ROW_RE.findall(tbody):
        name = _strip(re.search(r"</td>\s*<td>(.*?)</td>", r, re.S).group(1))
        overall = float(re.search(r'class="r overall"[^>]*>([\d.]+)', r).group(1))
        rows.append({"html": r.strip(), "name": name, "overall": overall})
    return rows


def parse_cards(grid):
    cards = []
    for piece in re.split(r'(?=    <div class="card")', grid):
        if '<div class="card"' not in piece:
            continue
        name = re.search(r'class="name">(.*?)</span>', piece).group(1)
        src = re.search(r'iframe src="([^"]+)"', piece).group(1)
        cards.append({"html": piece.strip(), "name": name, "src": src})
    return cards


def rewrite_row(row_html, score, bd):
    dims = [bd["time"], bd["visual"], bd["dial"], bd["code"], bd["motion"]]
    it = iter(dims)
    row_html = re.sub(r'<td class="r">[\d.]+</td>', lambda m: f'<td class="r">{_fmt(next(it))}</td>', row_html, count=5)
    row_html = re.sub(r'(<td class="r runs">)[^<]*(</td>)', r"\g<1>1/1\g<2>", row_html)
    sc, _ = score_to_grade(score)
    row_html = re.sub(r'<td class="r overall"[^>]*>[\d.]+</td>',
                      f'<td class="r overall" style="color:{_OVERALL_COLORS[sc]}">{score}</td>', row_html)
    return row_html


def rewrite_card(card_html, score, bd):
    card_html = re.sub(r"#\d+ · [\d.]+", f"#0 · {score}", card_html)
    card_html = re.sub(
        r"Score: [\d.]+ \| Time:[\d.]+ Visual:[\d.]+ Dial:[\d.]+ Code:[\d.]+ Motion:[\d.]+",
        f"Score: {score} | Time:{_fmt(bd['time'])} Visual:{_fmt(bd['visual'])} "
        f"Dial:{_fmt(bd['dial'])} Code:{_fmt(bd['code'])} Motion:{bd['motion']}",
        card_html,
    )
    card_html = re.sub(r"Runs: [^<|]+", "Runs: 1/1", card_html)
    return card_html


def renumber(items, key):
    items.sort(key=lambda x: x[key], reverse=True)
    for i, it in enumerate(items, 1):
        sc, bc = score_to_grade(it[key])
        it["html"] = re.sub(r'<span class="badge [^"]*">\d+</span>', f'<span class="badge {bc}">{i}</span>', it["html"])
        it["html"] = re.sub(r"#\d+ · ([\d.]+)", f"#{i} · \\1", it["html"])
        it["html"] = re.sub(r'class="score s-\d+"', f'class="score {sc}"', it["html"])
        it["rank"] = i
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    content = open(INDEX).read()
    tb, grid = TBODY_RE.search(content), GRID_RE.search(content)
    rows, cards = parse_rows(tb.group(2)), parse_cards(grid.group(2))
    if len(rows) != len(cards):
        sys.exit(f"row/card count mismatch: {len(rows)} rows vs {len(cards)} cards")

    # Pair each table row with its card by display name (row text is the display
    # name followed by the model id; the card carries the display name alone).
    unpaired = list(cards)
    pairs = []
    for row in rows:
        match = max((c for c in unpaired if row["name"].startswith(c["name"])),
                    key=lambda c: len(c["name"]), default=None)
        if match is None:
            sys.exit(f"no card found for row {row['name']!r}")
        unpaired.remove(match)
        pairs.append((row, match))
    if unpaired:
        sys.exit(f"cards without a row: {[c['name'] for c in unpaired]}")

    report = []
    for old_rank, (row, card) in enumerate(pairs, 1):
        html = open(card["src"]).read()
        audit = evaluate_clock_typesafe(html)
        score, bd = calculate_score(audit)
        row["new"], card["new"] = score, score
        row["html"] = rewrite_row(row["html"], score, bd)
        card["html"] = rewrite_card(card["html"], score, bd)
        report.append({"name": card["name"], "file": card["src"], "old_rank": old_rank,
                       "old": row["overall"], "new": score, "bd": bd,
                       "probs": audit.get("typesafe_probs", {})})
        print(f"  {card['name']:<22} {row['overall']:>5} -> {score:<5}  "
              f"T{_fmt(bd['time'])} V{_fmt(bd['visual'])} D{_fmt(bd['dial'])} C{_fmt(bd['code'])} M{bd['motion']}")

    renumber(rows, "new")
    renumber(cards, "new")
    new_rank = {c["name"]: c["rank"] for c in cards}
    for r in report:
        r["new_rank"] = new_rank[r["name"]]

    lines = [
        f"# Cloud leaderboard re-judged with TypeSafe Jev ({datetime.date.today()})",
        "",
        "Every cloud entry re-audited from its committed clock file by `rejudge_index.py`; "
        "the twelve April entries were previously hand-scored, the rest by a generative LLM judge.",
        "",
        "| Model | File | Old rank | New rank | Old | New | Delta | Time | Visual | Dial | Code | Motion |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(report, key=lambda x: x["new_rank"]):
        b = r["bd"]
        lines.append(f"| {r['name']} | `{r['file']}` | {r['old_rank']} | {r['new_rank']} | {r['old']} | {r['new']} | "
                     f"{round(r['new'] - r['old'], 2):+} | {_fmt(b['time'])} | {_fmt(b['visual'])} | {_fmt(b['dial'])} | "
                     f"{_fmt(b['code'])} | {b['motion']} |")
    md = "\n".join(lines) + "\n"
    print("\n" + md)

    if args.dry_run:
        print("dry run: index.html not modified")
        return

    new_tbody = tb.group(1) + "\n" + "\n".join("      " + r["html"] for r in rows) + "\n    " + tb.group(3)
    content = content[:tb.start()] + new_tbody + content[tb.end():]
    grid = GRID_RE.search(content)
    new_grid = "\n" + "\n".join("    " + c["html"] for c in cards) + "\n  "
    content = content[:grid.start(2)] + new_grid + content[grid.end(2):]
    content = re.sub(
        r"<strong>[^<]*</strong> acted as judge[^<]*",
        "<strong>TypeSafe Jev</strong> acted as judge — one typed yes/no question per rubric criterion "
        "over each clock's source, scored by <code>rejudge_index.py</code>.",
        content, count=1,
    )
    open(INDEX, "w").write(content)

    os.makedirs("docs", exist_ok=True)
    out = f"docs/rejudge-{datetime.date.today()}.md"
    open(out, "w").write(md)
    print(f"Rewrote {INDEX} and wrote {out}")


if __name__ == "__main__":
    main()
