#!/usr/bin/env python3
"""Re-judge every local leaderboard entry and render it the way the cloud tab does.

Same pipeline as rejudge_index.py: TypeSafe Jev, the vision second judge, then
the browser render check. Each local card is rebuilt into the cloud format
(dimension cells, Earned/Lost summary, meta line with the machine it ran on)
and its hand-written review moves under "Original review". Audits are saved to
audits.json and rows/cards are re-ranked by the new score.

Usage:
    python rejudge_local.py --dry-run
    python rejudge_local.py
    python rejudge_local.py --stored     # reuse audits.json, re-run only the measurements
"""

import argparse
import re
import sys
import urllib.parse

from rejudge_index import (INDEX, _fmt, _strip, parse_cards, rewrite_row, renumber,
                           calculate_score, apply_render_check, apply_second_judge,
                           evaluate_clock_typesafe)
from add_model import make_verdict, save_audit, load_audits

TBODY_RE = re.compile(r'(<table id="local-table"[^>]*>.*?<tbody>)(.*?)(</tbody>)', re.S)
GRID_RE = re.compile(r'(<div data-tab="local"[^>]*>.*?<div class="grid">)(.*?)(</div>\s*\n</div>)', re.S)
ROW_RE = re.compile(r"<tr>.*?</tr>", re.S)


def parse_rows(tbody):
    rows = []
    for r in ROW_RE.findall(tbody):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        machine = re.search(r'<td class="machine">(.*?)<br><span[^>]*>(.*?)</span>', r, re.S)
        rows.append({
            "html": r.strip(),
            "name": _strip(re.sub(r'<span class="tip".*?</span>', "", cells[1], flags=re.S)),
            "overall": float(re.search(r'class="r overall"[^>]*>([\d.]+)', r).group(1)),
            "ran": _strip(cells[2]),
            "latency": _strip(cells[10]),
            "machine": f"{machine.group(1)} · {machine.group(2)}" if machine else None,
        })
    return rows


def rebuild_card(card, score, bd, audit, row):
    old = re.search(r'<div class="verdict">(.*?)</div>\s*$', card["html"], re.S)
    original = old.group(1).strip() if old else None
    if original and original.endswith("</div>"):  # the verdict's own closing tag, not part of the review
        original = original[:-len("</div>")].rstrip()
    if original and 'class="dims"' in original:  # already converted: keep its original review
        m = re.search(r'<details class="orig"><summary>.*?</summary>(.*?)</details>', original, re.S)
        original = m.group(1) if m else None
    latency = row["latency"][:-1] if row["latency"].endswith("s") else None
    verdict = make_verdict(bd, audit, source=row["machine"],
                           run_date=row["ran"] if row["ran"] != "—" else None,
                           latency=latency, judge_runs=1, original=original)
    head = card["html"][:card["html"].index('<div class="verdict">')].rstrip()
    head = re.sub(r"#\d+ · [\d.]+", f"#0 · {score}", head)
    return head + "\n" + verdict + "\n    </div>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stored", action="store_true")
    args = ap.parse_args()

    content = open(INDEX).read()
    tb, grid = TBODY_RE.search(content), GRID_RE.search(content)
    rows, cards = parse_rows(tb.group(2)), parse_cards(grid.group(2))
    by_name = {c["name"]: c for c in cards}
    if len(rows) != len(cards) or any(r["name"] not in by_name for r in rows):
        sys.exit(f"rows {[r['name'] for r in rows]} do not match cards {list(by_name)}")

    stored = load_audits() if args.stored else {}
    for row in rows:
        card = by_name[row["name"]]
        path = urllib.parse.unquote(card["src"])
        html = open(path).read()
        if args.stored:
            audit = dict(stored[path])
            for field, value in (audit.pop("judge_answers", None) or {}).items():
                section, key = field.split(".")
                audit[section] = dict(audit[section], **{key: value})
            for k in ("render_check", "measured", "votes"):
                audit.pop(k, None)
        else:
            audit = evaluate_clock_typesafe(html)
        audit = apply_second_judge(audit, html)
        audit = apply_render_check(audit, html)
        score, bd = calculate_score(audit)
        print(f"  {row['name']:<24} {row['overall']:>5} -> {score:<5}  "
              f"T{_fmt(bd['time'])} V{_fmt(bd['visual'])} D{_fmt(bd['dial'])} C{_fmt(bd['code'])} M{bd['motion']}")
        row["new"] = card["new"] = score
        row["html"] = rewrite_row(row["html"], score, bd)
        card["html"] = rebuild_card(card, score, bd, audit, row)
        if not args.dry_run:
            save_audit(path, audit)

    renumber(rows, "new")
    renumber(cards, "new")
    if args.dry_run:
        print("dry run: index.html not modified")
        return

    new_tbody = tb.group(1) + "\n" + "\n".join("      " + r["html"] for r in rows) + "\n    " + tb.group(3)
    content = content[:tb.start()] + new_tbody + content[tb.end():]
    grid = GRID_RE.search(content)
    new_grid = "\n" + "\n".join("    " + c["html"] for c in cards) + "\n  "
    content = content[:grid.start(2)] + new_grid + content[grid.end(2):]
    open(INDEX, "w").write(content)
    print(f"Rewrote the local tab in {INDEX}")


if __name__ == "__main__":
    main()
