import json
import textwrap
from pathlib import Path

from typer.testing import CliRunner

from leandag.cli import app

runner = CliRunner()

_TEX = textwrap.dedent(r"""
    \chapter{Test Chapter}
    \begin{lemma}[Alpha]
      \label{lem:alpha}
      \lean{AlphaLemma}
      \leanok
      Statement alpha.
    \end{lemma}
    \begin{proof}
      Because it is.
    \end{proof}
    \begin{theorem}[Beta]
      \label{thm:beta}
      \uses{lem:alpha}
      Statement beta.
    \end{theorem}
""")

_LEAN = textwrap.dedent("""\
    lemma AlphaLemma : True := trivial
    def helper : Nat := 0
""")


def _project(tmp_path: Path) -> Path:
    bp = tmp_path / "blueprint" / "src"
    bp.mkdir(parents=True)
    (bp / "web.tex").write_text(_TEX)
    (tmp_path / "Foo.lean").write_text(_LEAN)
    return tmp_path


# ── build ──────────────────────────────────────────────────────────────────────

def test_build_creates_dag(tmp_path):
    _project(tmp_path)
    r = runner.invoke(app, ["build", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".leandag" / "dag.json").exists()


def test_build_with_html(tmp_path):
    _project(tmp_path)
    r = runner.invoke(app, ["build", "--html", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".leandag" / "graph.html").exists()


def test_build_custom_output(tmp_path):
    _project(tmp_path)
    out = tmp_path / "custom.json"
    r = runner.invoke(app, ["build", "--output", str(out), "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert out.exists()


def test_build_missing_entry(tmp_path):
    r = runner.invoke(app, ["build", "--root", str(tmp_path)])
    assert r.exit_code != 0


def test_build_dag_content(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    data = json.loads((tmp_path / ".leandag" / "dag.json").read_text())
    ids = {n["id"] for n in data["nodes"]}
    assert "lem:alpha" in ids
    assert "thm:beta"  in ids
    assert "lean:helper" in ids   # unreferenced lean decl → lean_aux


# ── html ───────────────────────────────────────────────────────────────────────

def test_html_command(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["html", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert (tmp_path / ".leandag" / "graph.html").exists()


def test_html_without_dag_fails(tmp_path):
    r = runner.invoke(app, ["html", "--root", str(tmp_path)])
    assert r.exit_code != 0


# ── stats ──────────────────────────────────────────────────────────────────────

def test_stats_human(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "Blueprint nodes" in r.output


def test_stats_json(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["stats", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["blueprint_nodes"] == 2
    assert data["proved"] == 1


def test_stats_without_dag_fails(tmp_path):
    r = runner.invoke(app, ["stats", "--root", str(tmp_path)])
    assert r.exit_code != 0


# ── show ───────────────────────────────────────────────────────────────────────

def test_show_leaves(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["show", "leaves", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output


def test_show_unproved(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["show", "unproved", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    ids = {n["id"] for n in nodes}
    assert "thm:beta"  in ids
    assert "lem:alpha" not in ids   # lem:alpha is proved


def test_show_ready(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["show", "ready", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    # thm:beta depends only on lem:alpha which is proved → should be ready
    ids = {n["id"] for n in nodes}
    assert "thm:beta" in ids


def test_show_unknown_filter(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["show", "foobar", "--root", str(tmp_path)])
    assert r.exit_code != 0


def test_show_top_limit(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["show", "leaves", "--json", "--top", "1", "--root", str(tmp_path)])
    assert r.exit_code == 0
    assert len(json.loads(r.output)) <= 1


# ── query ──────────────────────────────────────────────────────────────────────

def test_query_all_json(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    data = json.loads(r.output)
    assert isinstance(data, list)


def test_query_unproved(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--unproved", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    assert all(not n["proved"] for n in nodes)


def test_query_sort_invalid(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--sort", "banana", "--root", str(tmp_path)])
    assert r.exit_code != 0


def test_query_effort_excludes_proved_by_default(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--sort", "effort", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    # lem:alpha is proved → must not appear in default effort sort
    assert all(not n["proved"] for n in nodes)


def test_query_include_proved(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--sort", "effort", "--include-proved", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    proved = [n for n in nodes if n["proved"]]
    assert len(proved) > 0


def test_query_min_deps(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--min-deps", "1", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    assert all(n["dep_count"] >= 1 for n in nodes)


def test_query_min_max_effort(tmp_path):
    _project(tmp_path)
    runner.invoke(app, ["build", "--root", str(tmp_path)])
    r = runner.invoke(app, ["query", "--min-effort", "0", "--max-effort", "9999", "--json", "--root", str(tmp_path)])
    assert r.exit_code == 0
    nodes = json.loads(r.output)
    for n in nodes:
        assert n["effort_total"] is not None
        assert 0 <= n["effort_total"] <= 9999


# ── init ───────────────────────────────────────────────────────────────────────

def test_init_writes_config(tmp_path):
    _project(tmp_path)
    r = runner.invoke(app, ["init", "--root", str(tmp_path)])
    assert r.exit_code == 0, r.output
    config = (tmp_path / ".leandag" / "config.toml").read_text()
    assert "entry" in config
    assert "lean_root" in config


def test_init_custom_entry(tmp_path):
    r = runner.invoke(app, [
        "init", "--entry", "my/blueprint.tex", "--root", str(tmp_path)
    ])
    assert r.exit_code == 0
    config = (tmp_path / ".leandag" / "config.toml").read_text()
    assert "my/blueprint.tex" in config
