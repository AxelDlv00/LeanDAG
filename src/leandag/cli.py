"""leandag CLI — build and query a dependency graph for Lean 4 + leanblueprint projects.

Output format is selectable for both humans and tooling/LLM agents:

    leandag --format json stats        # structured JSON on stdout
    leandag --plain build              # plain text, no colour/box-drawing
    leandag stats --json               # per-command shortcut, equivalent to -f json

In ``json``/``text`` mode, progress lines go to stderr and the structured
payload to stdout, so an agent can parse stdout cleanly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .dag import DAG
from .exporters import HTMLExporter, JSONExporter
from .models import GraphNode
from .parser import BlueprintParser
from .queries import Queries
from .reporter import Reporter
from .scanner import LeanScanner

app = typer.Typer(
    add_completion=False,
    help="Build and query a dependency graph for Lean 4 + leanblueprint projects.",
)

_DIR    = ".leandag"
_DAG    = "dag.json"
_HTML   = "graph.html"
_CONFIG = "config.toml"

_STATE = {"fmt": "rich"}


@app.callback()
def _main(
    fmt:   str  = typer.Option("rich", "--format", "-f",
                               help="Output format: rich | text | json."),
    plain: bool = typer.Option(False, "--plain",
                               help="Shorthand for --format text (no colour/boxes)."),
) -> None:
    """Dependency graph and complexity metrics for Lean 4 + leanblueprint."""
    if plain and fmt == "rich":
        fmt = "text"
    _STATE["fmt"] = fmt if fmt in ("rich", "text", "json") else "rich"


def _reporter(json_flag: bool = False) -> Reporter:
    return Reporter("json" if json_flag else _STATE["fmt"])


# ── Config / path helpers ──────────────────────────────────────────────────────

def _read_config(root: Path) -> dict:
    path = root / _DIR / _CONFIG
    if not path.exists():
        return {}
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        return tomllib.loads(path.read_text(encoding="utf-8")).get("leandag", {})
    except Exception:
        return {}


def _auto_detect_entry(root: Path) -> Optional[Path]:
    for rel in [
        "blueprint/src/web.tex",
        "blueprint/src/print.tex",
        "blueprint/src/content.tex",
    ]:
        p = root / rel
        if p.exists():
            return p
    return None


def _load_dag(root: Path, rep: Reporter) -> DAG:
    dag_path = root / _DIR / _DAG
    if not dag_path.exists():
        rep.error(f"No DAG found at {dag_path}. Run 'leandag build' first.")
        raise typer.Exit(code=1)
    return DAG.load(dag_path)


# ── Display helpers ────────────────────────────────────────────────────────────

def _fmt_effort(v: Optional[int]) -> str:
    if v is None:
        return "∞"
    if v == 0:
        return "0 ✓"
    return f"{v:,}"


def _node_brief(n: GraphNode) -> dict:
    """Compact, agent-friendly view of a node."""
    return {
        "id":               n.id,
        "type":             n.type,
        "chapter":          n.chapter,
        "proved":           n.proved,
        "has_sorry":        n.has_sorry,
        "lean_name":        n.lean_name,
        "effort_local":     n.effort_local,
        "effort_total":     n.effort_total,
        "dep_count":        n.dep_count,
        "descendant_count": n.descendant_count,
    }


def _emit_nodes(rep: Reporter, nodes: list[GraphNode], *, top: Optional[int] = None) -> None:
    if top is not None:
        nodes = nodes[:top]
    obj = [n.to_dict() for n in nodes]

    def render() -> None:
        if not nodes:
            rep.detail("— none —")
            return
        rep.table(
            ["ID", "Type", "Chapter", "Proved", "Effort", "Eff.total", "Deps", "Impact"],
            [[n.id, n.type, n.chapter or "—", "✓" if n.proved else "✗",
              _fmt_effort(n.effort_local), _fmt_effort(n.effort_total),
              n.dep_count, n.descendant_count] for n in nodes],
        )

    rep.emit(obj, rich=render, text=render)


# ── Commands ───────────────────────────────────────────────────────────────────

@app.command()
def init(
    entry:     Optional[str] = typer.Option(None, "--entry",     help="Blueprint entry .tex (relative to root)."),
    lean_root: str            = typer.Option(".",  "--lean-root", help="Lean project root (relative to root)."),
    root:      Path           = typer.Option(Path("."), "--root", help="Project root."),
) -> None:
    """Create (or update) .leandag/config.toml."""
    rep = _reporter()
    leandag_dir = root / _DIR
    leandag_dir.mkdir(exist_ok=True)

    if entry is None:
        detected = _auto_detect_entry(root)
        if detected:
            entry = str(detected.resolve().relative_to(root.resolve()))
            rep.detail(f"Auto-detected: {entry}")
        else:
            entry = "blueprint/src/web.tex"
            rep.warn(f"Entry not found; defaulting to {entry}")

    config_path = leandag_dir / _CONFIG
    config_path.write_text(
        f'[leandag]\nentry     = "{entry}"\nlean_root = "{lean_root}"\n',
        encoding="utf-8",
    )
    rep.ok(f"Wrote {config_path}")


@app.command()
def build(
    entry: Optional[Path] = typer.Argument(
        None,
        help="Entry .tex file. Reads config.toml if omitted, then auto-detects.",
        show_default=False,
    ),
    html:   bool          = typer.Option(False,    "--html",   help="Also write graph.html."),
    root:   Path          = typer.Option(Path("."), "--root",  help="Project root for scanning and config."),
    output: Optional[Path] = typer.Option(None,   "--output", "-o", help="Override JSON output path."),
    json_out: bool        = typer.Option(False,   "--json",   help="Emit a JSON build report on stdout."),
) -> None:
    """Parse blueprint + Lean sources and save the DAG to .leandag/."""
    rep = _reporter(json_out)
    rep.rule("leandag build")

    config = _read_config(root)

    if entry is None:
        raw = config.get("entry")
        entry = Path(raw) if raw else _auto_detect_entry(root)
        if entry and not Path(entry).is_absolute():
            entry = root / entry
    if entry is None:
        rep.error("No blueprint entry found. Run 'leandag init' or pass the .tex path.")
        raise typer.Exit(code=1)
    if not Path(entry).exists():
        rep.error(f"Entry file not found: {entry}")
        raise typer.Exit(code=1)

    lean_root = root / config.get("lean_root", ".")

    rep.step(f"Parsing blueprint  {entry}")
    parser = BlueprintParser(Path(entry))
    blueprint_decls, proofs = parser.parse()
    rep.detail(f"{len(blueprint_decls)} declarations · {len(proofs)} proof blocks · {len(parser.macros)} macros")

    rep.step(f"Scanning Lean      {lean_root}")
    scanner    = LeanScanner()
    lean_decls = scanner.scan(lean_root)
    rep.detail(f"{len(lean_decls)} declarations")

    rep.step("Building DAG")
    dag = DAG.from_sources(blueprint_decls, proofs, lean_decls, macros=parser.macros)

    ids = {n.id for n in dag.nodes}
    unknown_uses = [
        {"node": n.id, "uses": pred}
        for n in dag.nodes for pred in n.uses if pred not in ids
    ]

    leandag_dir = root / _DIR
    leandag_dir.mkdir(exist_ok=True)
    dag_path = output or (leandag_dir / _DAG)
    JSONExporter().export(dag, dag_path)

    if html:
        html_path = leandag_dir / _HTML
        HTMLExporter().export(dag, html_path)

    # ── assemble the structured report ──────────────────────────────────────
    conflicts = [{"name": c[0], "files": [c[1], c[2]]} for c in scanner.collisions]
    unmatched = [{"node": nid, "lean_name": ref} for nid, ref in dag.unmatched_lean]
    summary = {
        "blueprint_nodes": sum(1 for n in dag.nodes if n.type != "lean_aux"),
        "lean_aux_nodes":  sum(1 for n in dag.nodes if n.type == "lean_aux"),
        "proved":          sum(1 for n in dag.nodes if n.type != "lean_aux" and n.proved),
        "with_sorry":      sum(1 for n in dag.nodes if n.has_sorry),
        "edges":           len(dag.edges),
    }
    report = {
        "dag_path":         str(dag_path),
        "html_path":        str(leandag_dir / _HTML) if html else None,
        "summary":          summary,
        "effort":           dag.effort_summary(),
        "conflicts":        conflicts,
        "unmatched_lean":   unmatched,
        "unknown_uses":     unknown_uses,
    }

    def render() -> None:
        for c in conflicts[:10]:
            rep.warn(f"conflicting decl '{c['name']}' — {c['files'][0]} vs {c['files'][1]}")
        if len(conflicts) > 10:
            rep.detail(f"… and {len(conflicts) - 10} more conflicts")
        for u in unknown_uses[:25]:
            rep.warn(f"{u['node']} uses unknown id '{u['uses']}'")
        if unmatched:
            rep.warn(f"{len(unmatched)} \\lean{{}} reference(s) matched no Lean declaration:")
            for u in unmatched[:25]:
                rep.detail(f"{u['node']}: {u['lean_name']}")
            if len(unmatched) > 25:
                rep.detail(f"… and {len(unmatched) - 25} more")
        rep.ok(f"DAG saved  {dag_path}")
        if html:
            rep.ok(f"HTML saved {leandag_dir / _HTML}")
        rep.blank()
        eff = report["effort"]
        rep.table(
            ["metric", "value"],
            [["blueprint nodes", f"{summary['blueprint_nodes']} ({summary['proved']} proved)"],
             ["lean-aux nodes",  summary["lean_aux_nodes"]],
             ["edges",           summary["edges"]],
             ["with sorry",      summary["with_sorry"]],
             ["effort done (Lean chars)",     f"{eff['effort_done']:,}"],
             ["effort remaining (≥, finite)", f"{eff['effort_remaining_lower']:,}"],
             ["nodes with ∞ effort",          eff["effort_remaining_unknown_nodes"]]],
        )

    rep.emit(report, rich=render, text=render)


@app.command()
def html(
    root: Path          = typer.Option(Path("."), "--root"),
    out:  Optional[Path] = typer.Option(None,    "--out", "-o", help="Output HTML path."),
) -> None:
    """Regenerate the HTML visualisation from the cached DAG."""
    rep       = _reporter()
    dag       = _load_dag(root, rep)
    html_path = out or (root / _DIR / _HTML)
    HTMLExporter().export(dag, html_path)
    rep.ok(f"HTML written to {html_path}")


@app.command()
def stats(
    root:     Path = typer.Option(Path("."), "--root"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Print summary statistics for the project."""
    rep = _reporter(json_out)
    dag = _load_dag(root, rep)
    q   = Queries(dag)

    n_bp     = sum(1 for n in dag.nodes if n.type != "lean_aux")
    n_aux    = sum(1 for n in dag.nodes if n.type == "lean_aux")
    n_proved = sum(1 for n in dag.nodes if n.type != "lean_aux" and n.proved)
    n_sorry  = sum(1 for n in dag.nodes if n.has_sorry)
    n_ready  = len(q.ready_to_prove())
    n_gaps   = len(q.needs_lean_statement())
    n_leanok = len(q.needs_leanok())
    pct      = round(100 * n_proved / n_bp, 1) if n_bp else 0.0
    eff      = dag.effort_summary()

    obj = {
        "blueprint_nodes": n_bp,
        "lean_aux_nodes":  n_aux,
        "edges":           len(dag.edges),
        "proved":          n_proved,
        "proved_pct":      pct,
        "with_sorry":      n_sorry,
        "ready_to_prove":  n_ready,
        "needs_lean_statement": n_gaps,
        "needs_leanok":    n_leanok,
        "unmatched_lean":  len(dag.unmatched_lean),
        "axioms":          len(dag.axioms),
        "leaves":          len(dag.leaves),
        "effort":          eff,
    }

    def render() -> None:
        rep.table(
            ["metric", "value"],
            [["Blueprint nodes",  n_bp],
             ["Lean-aux nodes",   n_aux],
             ["Edges",            len(dag.edges)],
             ["Proved (leanok)",  f"{n_proved} ({pct}%)"],
             ["With sorry",       n_sorry],
             ["Ready to formalize", n_ready],
             ["Needs \\lean{}",   n_gaps],
             ["Needs \\leanok",   n_leanok],
             ["Unmatched \\lean{}", len(dag.unmatched_lean)],
             ["Axioms (dep=0)",   len(dag.axioms)],
             ["Leaves (rdep=0)",  len(dag.leaves)],
             ["— Effort —",       ""],
             ["Done (Lean chars)",            f"{eff['effort_done']:,}"],
             ["Remaining (≥, finite only)",   f"{eff['effort_remaining_lower']:,}"],
             ["Nodes with ∞ effort",          eff["effort_remaining_unknown_nodes"]],
             ["Remaining (total)",
              "∞" if eff["effort_remaining"] is None else f"{eff['effort_remaining']:,}"]],
        )

    rep.emit(obj, rich=render, text=render)


@app.command()
def focus(
    root:     Path          = typer.Option(Path("."), "--root"),
    top:      Optional[int] = typer.Option(20, "--top", "-n", help="Limit each list to N entries."),
    json_out: bool          = typer.Option(False, "--json"),
) -> None:
    """Where to put formalisation/blueprint effort next.

    Surfaces the actionable frontiers for an autoformalisation agent:
    nodes ready to formalise (deps done) ranked by how much they unblock,
    nodes still carrying ``sorry``, blueprint statements with no Lean link,
    and ``\\lean{}`` references that resolved to nothing.
    """
    rep = _reporter(json_out)
    dag = _load_dag(root, rep)
    q   = Queries(dag)

    ready  = Queries.sort_by_impact(q.ready_to_prove(), top=top)
    sorry  = Queries.sort_by_impact(q.with_sorry(),     top=top)
    gaps   = Queries.sort_by_impact(q.needs_lean_statement(), top=top)
    leanok = Queries.sort_by_impact(q.needs_leanok(),   top=top)
    unmatched = [{"node": nid, "lean_name": ref} for nid, ref in dag.unmatched_lean]

    obj = {
        "effort":               dag.effort_summary(),
        "ready_to_formalize":   [_node_brief(n) for n in ready],
        "has_sorry":            [_node_brief(n) for n in sorry],
        "needs_lean_statement": [_node_brief(n) for n in gaps],
        "needs_leanok":         [_node_brief(n) for n in leanok],
        "unmatched_lean":       unmatched[:top] if top else unmatched,
    }

    def render() -> None:
        eff = obj["effort"]
        rep.detail(
            f"done={eff['effort_done']:,}  remaining≥{eff['effort_remaining_lower']:,}  "
            f"(∞ nodes: {eff['effort_remaining_unknown_nodes']})"
        )
        sections = [
            ("READY TO FORMALIZE (deps done, work remaining, ranked by impact)", ready),
            ("HAS SORRY (finish the Lean proof)",                sorry),
            ("NEEDS \\lean{} (no Lean link yet)",                gaps),
            ("NEEDS \\leanok (Lean proof exists — just flag it)", leanok),
        ]
        for title, ns in sections:
            rep.blank()
            rep.detail(title)
            rep.table(
                ["ID", "Type", "Effort", "Impact", "Deps"],
                [[n.id, n.type, _fmt_effort(n.effort_local), n.descendant_count, n.dep_count]
                 for n in ns] or [["—", "", "", "", ""]],
            )
        if unmatched:
            rep.blank()
            rep.detail("UNMATCHED \\lean{} (rename or create the Lean declaration)")
            rep.table(["node", "lean_name"],
                      [[u["node"], u["lean_name"]] for u in unmatched[:top]] if top
                      else [[u["node"], u["lean_name"]] for u in unmatched])

    rep.emit(obj, rich=render, text=render)


_SHOW_CHOICES = ("axioms", "leaves", "unproved", "sorry", "ready", "gaps", "leanok")


@app.command()
def show(
    what:     str           = typer.Argument(..., help=f"One of: {', '.join(_SHOW_CHOICES)}"),
    root:     Path          = typer.Option(Path("."), "--root"),
    top:      Optional[int] = typer.Option(None, "--top", "-n", help="Limit output to N rows."),
    json_out: bool          = typer.Option(False, "--json"),
) -> None:
    """Show a named subset of nodes (axioms, leaves, unproved, sorry, ready, gaps)."""
    rep = _reporter(json_out)
    if what not in _SHOW_CHOICES:
        rep.error(f"Unknown filter '{what}'. Choose from: {', '.join(_SHOW_CHOICES)}")
        raise typer.Exit(code=1)

    dag = _load_dag(root, rep)
    q   = Queries(dag)

    nodes: list[GraphNode] = {
        "axioms":   q.axioms,
        "leaves":   q.leaves,
        "unproved": q.unproved,
        "sorry":    q.with_sorry,
        "ready":    q.ready_to_prove,
        "gaps":     q.needs_lean_statement,
        "leanok":   q.needs_leanok,
    }[what]()

    rep.rule(f"{what}  ({len(nodes)} nodes)")
    _emit_nodes(rep, nodes, top=top)


@app.command()
def query(
    root:          Path          = typer.Option(Path("."),  "--root"),
    min_deps:      Optional[int] = typer.Option(None,       "--min-deps",      help="Min direct dependencies."),
    max_deps:      Optional[int] = typer.Option(None,       "--max-deps",      help="Max direct dependencies."),
    min_effort:    Optional[int] = typer.Option(None,       "--min-effort",    help="Min effort_total."),
    max_effort:    Optional[int] = typer.Option(None,       "--max-effort",    help="Max effort_total."),
    chapter:       Optional[str] = typer.Option(None,       "--chapter",       help="Filter by chapter name."),
    type_name:     Optional[str] = typer.Option(None,       "--type",          help="Filter by node type (lemma, theorem…)."),
    unproved:      bool          = typer.Option(False,      "--unproved",      help="Only unproved blueprint nodes."),
    sorry:         bool          = typer.Option(False,      "--sorry",         help="Only nodes with sorry."),
    sort:          str           = typer.Option("effort",   "--sort",          help="Sort by: effort, deps, impact, id."),
    include_proved:bool          = typer.Option(False,      "--include-proved",help="Include already-proved nodes (only relevant with --sort effort)."),
    top:           Optional[int] = typer.Option(None,       "--top", "-n",     help="Limit to N results."),
    json_out:      bool          = typer.Option(False,      "--json"),
) -> None:
    """Query nodes with arbitrary filters and sorting.

    Examples:

        leandag query --unproved --max-deps 2 --sort effort --top 10

        leandag query --sort impact --unproved --top 10   # biggest blockers
    """
    rep = _reporter(json_out)
    dag = _load_dag(root, rep)
    q   = Queries(dag)

    nodes = q.filter(
        min_deps      = min_deps,
        max_deps      = max_deps,
        min_effort    = min_effort,
        max_effort    = max_effort,
        chapter       = chapter,
        type_name     = type_name,
        unproved_only = unproved,
        sorry_only    = sorry,
    )

    if sort == "effort":
        nodes = Queries.sort_by_effort(nodes, top=top, exclude_proved=not include_proved)
    elif sort == "deps":
        nodes = Queries.sort_by_deps(nodes, top=top)
    elif sort == "impact":
        nodes = Queries.sort_by_impact(nodes, top=top)
    elif sort == "id":
        nodes = sorted(nodes, key=lambda n: n.id)
        if top is not None:
            nodes = nodes[:top]
    else:
        rep.error(f"Unknown sort '{sort}'. Choose from: effort, deps, impact, id")
        raise typer.Exit(code=1)

    rep.rule(f"query  ({len(nodes)} results)")
    _emit_nodes(rep, nodes)
