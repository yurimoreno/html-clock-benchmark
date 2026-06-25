"""Tests for add_model.update_index — the regex splicing that mutates the
published index.html. This is the most failure-prone code in the repo: a bad
match silently corrupts the leaderboard.

update_index reads/writes "index.html" relative to the CWD, so each test runs
inside a tmp dir with a minimal-but-faithful fixture.
"""
import re
import pytest
import add_model
from add_model import update_index


FIXTURE = """<!DOCTYPE html>
<html><body>
<div data-tab="cloud" class="active">
  <table id="cloud-table" class="score-table">
    <thead><tr><th>x</th></tr></thead>
    <tbody>
      <tr>
        <td><span class="badge b-1">1</span></td>
        <td><div><a href="#card-x/alpha" class="model-link">Alpha</a></div><span class="model-id">x/alpha</span></td>
        <td class="r overall" style="color:#d6f5d6">9.0</td>
      </tr>
      <tr>
        <td><span class="badge b-4">2</span></td>
        <td><div><a href="#card-x/beta" class="model-link">Beta</a></div><span class="model-id">x/beta</span></td>
        <td class="r overall" style="color:#f5dcc6">7.5</td>
      </tr>
    </tbody>
  </table>
  </div>

  <div class="grid">
    <div class="card" id="card-x/alpha">
      <header>
        <span class="name">Alpha</span>
        <span class="score s-1">#1 · 9.0</span>
      </header>
      <iframe src="previews/x_alpha.html"></iframe>
      <div class="verdict">Score: 9.0 | <span class="model-id">x/alpha</span></div>
    </div>
    <div class="card" id="card-x/beta">
      <header>
        <span class="name">Beta</span>
        <span class="score s-4">#2 · 7.5</span>
      </header>
      <iframe src="previews/x_beta.html"></iframe>
      <div class="verdict">Score: 7.5 | <span class="model-id">x/beta</span></div>
    </div>
  </div>
</div>

<div data-tab="local"></div>
</body></html>
"""

BREAKDOWN = {"time": 10.0, "visual": 10.0, "dial": 10.0, "code": 10.0, "motion": 10}


def _write_fixture(tmp_path):
    p = tmp_path / "index.html"
    p.write_text(FIXTURE)
    return p


def _table_order(content):
    """Return [(rank, score), ...] in document order from the cloud table."""
    tbody = re.search(r'<tbody>(.*?)</tbody>', content, re.DOTALL).group(1)
    rows = re.findall(r'<tr>.*?</tr>', tbody, re.DOTALL)
    out = []
    for row in rows:
        rank = re.search(r'<span class="badge [^"]*">(\d+)</span>', row)
        score = re.search(r'<td class="r overall"[^>]*>([\d.]+)</td>', row)
        if rank and score:
            out.append((int(rank.group(1)), float(score.group(1))))
    return out


def _card_order(content):
    """Return [(rank, score), ...] in document order from the cloud card grid."""
    return [(int(r), float(s)) for r, s in re.findall(r'#(\d+) · ([\d.]+)', content)]


def test_table_insert_at_top_reorders_and_renumbers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_fixture(tmp_path)

    update_index("x/gamma", 9.8, BREAKDOWN, "runs/x_gamma.html", "20260101_000000",
                 model_id="x/gamma", run_date="20260101_000000",
                 display_name="Gamma")

    content = (tmp_path / "index.html").read_text()

    # Table: new model first, ranks renumbered 1,2,3, scores sorted desc.
    assert _table_order(content) == [(1, 9.8), (2, 9.0), (3, 7.5)]
    # New model actually present in both table and grid.
    assert content.count("x/gamma") >= 2
    assert "Gamma" in content


def test_table_insert_in_middle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_fixture(tmp_path)

    update_index("x/delta", 8.0, BREAKDOWN, "runs/x_delta.html", "20260101_000000",
                 model_id="x/delta", run_date="20260101_000000",
                 display_name="Delta")

    content = (tmp_path / "index.html").read_text()
    assert _table_order(content) == [(1, 9.0), (2, 8.0), (3, 7.5)]


@pytest.mark.xfail(
    reason="KNOWN BUG: _make_card emits <div class=\"card\" id=...> but the grid "
           "split regex in update_index only matches <div class=\"card\"> (no id). "
           "id'd cards get lumped, so the rank-renumber re.sub stamps a duplicate "
           "rank onto every card in the lump. The cloud table is unaffected.",
    strict=True,
)
def test_card_grid_ranks_should_match_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_fixture(tmp_path)

    update_index("x/delta", 8.0, BREAKDOWN, "runs/x_delta.html", "20260101_000000",
                 model_id="x/delta", run_date="20260101_000000",
                 display_name="Delta")

    content = (tmp_path / "index.html").read_text()
    # Desired behaviour: card grid mirrors the (correct) table ordering.
    assert _card_order(content) == [(1, 9.0), (2, 8.0), (3, 7.5)]


def test_existing_models_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_fixture(tmp_path)

    update_index("x/gamma", 9.8, BREAKDOWN, "runs/x_gamma.html", "20260101_000000",
                 model_id="x/gamma", run_date="20260101_000000", display_name="Gamma")

    content = (tmp_path / "index.html").read_text()
    for existing in ("x/alpha", "x/beta", "Alpha", "Beta"):
        assert existing in content


def test_missing_index_is_noop(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # no index.html written
    update_index("x/gamma", 9.8, BREAKDOWN, "runs/x_gamma.html", "20260101_000000",
                 model_id="x/gamma")
    assert not (tmp_path / "index.html").exists()
    assert "not found" in capsys.readouterr().out
