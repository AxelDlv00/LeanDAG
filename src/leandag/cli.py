"""leandag CLI — build and query a dependency graph for Lean 4 + leanblueprint projects."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich import box

from .dag import DAG
from .exporters import HTMLExporter, JSONExporter
from .models import GraphNode
from .parser import BlueprintParser
from .queries import Queries
from .scanner import LeanScanner

app = typer.Typer(
    add_completion=False,
    help="Build and query a dependency graph for Lean 4 + leanblueprint projects.",
)
console = Console()
err     = Console(stderr=True)

_DIR    = ".leandag"
_DAG    = "dag.json"
_HTML   = "graph.html"
_CONFIG = "config.toml"


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


def _load_dag(root: Path) -> DAG:
    dag_path = root / _DIR / _DAG
    if not dag_path.exists():
        err.print(
            f"  [red]✗[/red] No DAG found at [bold]{dag_path}[/bold].\n"
            "    Run [bold]leandag build[/bold] first."
        )
        raise typer.Exit(code=1)
    return DAG.load(dag_path)


# ── Display helpers ────────────────────────────────────────────────────────────

def _fmt_effort(v: Optional[int]) -> str:
    if v is None:
        return "∞"
    if v == 0:
        return "0 ✓"
    return f"{v:,}"


def _print_nodes(
    nodes: list[GraphNode],
    json_out: bool,
    *,
    top: Optional[int] = None,
) -> None:
    if top is not None:
        nodes = nodes[:top]

    if json_out:
        sys.stdout.write(json.dumps([n.to_dict() for n in nodes], indent=2, ensure_ascii=False))
        sys.stdout.write("\n")
        return

    if not nodes:
        console.print("  [dim]— none —[/dim]")
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("ID",           style="cyan",   no_wrap=True, max_width=36)
    table.add_column("Type",         style="dim",    no_wrap=True)
    table.add_column("Chapter",      style="dim",    no_wrap=True, max_width=22)
    table.add_column("Proved",       justify="center")
    table.add_column("Effort",       justify="right", style="yellow")
    table.add_column("Eff. total",   justify="right", style="yellow")
    table.add_column("Deps",         justify="right", style="dim")

    for n in nodes:
        proved_sym = "[green]✓[/green]" if n.proved else "[red]✗[/red]"
        table.add_row(
            n.id,
            n.type,
            n.chapter or "—",
            proved_sym,
            _fmt_effort(n.effort_local),
            _fmt_effort(n.effort_total),
            str(n.dep_count),
        )

    console.print(table)


# ── Commands ───────────────────────────────────────────────────────────────────

@app.command()
def init(
    entry:     Optional[str] = typer.Option(None, "--entry",     help="Blueprint entry .tex (relative to root)."),
    lean_root: str            = typer.Option(".",  "--lean-root", help="Lean project root (relative to root)."),
    root:      Path           = typer.Option(Path("."), "--root", help="Project root."),
) -> None:
    """Create (or update) .leandag/config.toml."""
    leandag_dir = root / _DIR
    leandag_dir.mkdir(exist_ok=True)

    if entry is None:
        detected = _auto_detect_entry(root)
        if detected:
            entry = str(detected.resolve().relative_to(root.resolve()))
            console.print(f"  [dim]Auto-detected:[/dim] [cyan]{entry}[/cyan]")
        else:
            entry = "blueprint/src/web.tex"
            console.print(f"  [yellow]![/yellow] Entry not found; defaulting to [cyan]{entry}[/cyan]")

    config_path = leandag_dir / _CONFIG
    config_path.write_text(
        f'[leandag]\nentry     = "{entry}"\nlean_root = "{lean_root}"\n',
        encoding="utf-8",
    )
    console.print(f"  [green]✓[/green] Wrote [bold]{config_path}[/bold]")

    gitignore = root / ".gitignore"
    if gitignore.exists() and _DIR not in gitignore.read_text():
        console.print(
            f"  [dim]Tip: add [cyan]{_DIR}/[/cyan] to [bold].gitignore[/bold] "
            "(generated artefacts)[/dim]"
        )


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
) -> None:
    """Parse blueprint + Lean sources and save the DAG to .leandag/."""
    console.print()
    console.print(Rule("[bold]leandag build[/bold]", style="dim"))
    console.print()

    config = _read_config(root)

    if entry is None:
        raw = config.get("entry")
        entry = Path(raw) if raw else _auto_detect_entry(root)
        if entry and not Path(entry).is_absolute():
            entry = root / entry
    if entry is None:
        err.print(
            "  [red]✗[/red] No blueprint entry found.\n"
            "    Run [bold]leandag init[/bold] or pass the .tex path as an argument."
        )
        raise typer.Exit(code=1)
    if not Path(entry).exists():
        err.print(f"  [red]✗[/red] Entry file not found: {entry}")
        raise typer.Exit(code=1)

    lean_root = root / config.get("lean_root", ".")

    console.print(f"  [dim]•[/dim] Parsing blueprint  [cyan]{entry}[/cyan]")
    parser = BlueprintParser(Path(entry))
    blueprint_decls, proofs = parser.parse()
    console.print(f"    [dim]{len(blueprint_decls)} declarations · {len(proofs)} proof blocks[/dim]")

    console.print(f"  [dim]•[/dim] Scanning Lean      [cyan]{lean_root}[/cyan]")
    lean_decls = LeanScanner().scan(lean_root)
    console.print(f"    [dim]{len(lean_decls)} declarations[/dim]")

    console.print("  [dim]•[/dim] Building DAG")
    dag = DAG.from_sources(blueprint_decls, proofs, lean_decls)

    ids = {n.id for n in dag.nodes}
    for n in dag.nodes:
        for pred in n.uses:
            if pred not in ids:
                console.print(f"  [yellow]![/yellow] {n.id} uses unknown id '{pred}'")

    leandag_dir = root / _DIR
    leandag_dir.mkdir(exist_ok=True)

    dag_path = output or (leandag_dir / _DAG)
    JSONExporter().export(dag, dag_path)
    console.print(f"  [green]✓[/green] DAG saved         [green]{dag_path}[/green]")

    if html:
        html_path = leandag_dir / _HTML
        HTMLExporter().export(dag, html_path)
        console.print(f"  [green]✓[/green] HTML saved        [green]{html_path}[/green]")
        console.print(f"    [dim]file://{html_path.resolve()}[/dim]")

    n_bp     = sum(1 for n in dag.nodes if n.type != "lean_aux")
    n_aux    = sum(1 for n in dag.nodes if n.type == "lean_aux")
    n_proved = sum(1 for n in dag.nodes if n.type != "lean_aux" and n.proved)
    n_sorry  = sum(1 for n in dag.nodes if n.has_sorry)

    console.print()
    console.print(f"  Blueprint nodes  [bold]{n_bp}[/bold]  ([green]{n_proved} proved[/green])")
    console.print(f"  Lean-aux nodes   [bold]{n_aux}[/bold]")
    console.print(f"  Edges            [bold]{len(dag.edges)}[/bold]")
    if n_sorry:
        console.print(f"  With sorry       [yellow]{n_sorry}[/yellow]")
    console.print()


@app.command()
def html(
    root: Path          = typer.Option(Path("."), "--root"),
    out:  Optional[Path] = typer.Option(None,    "--out", "-o", help="Output HTML path."),
) -> None:
    """Regenerate the HTML visualisation from the cached DAG."""
    dag       = _load_dag(root)
    html_path = out or (root / _DIR / _HTML)
    HTMLExporter().export(dag, html_path)
    console.print(f"  [green]✓[/green] HTML written to [bold]{html_path}[/bold]")
    console.print(f"    [dim]file://{html_path.resolve()}[/dim]")


@app.command()
def stats(
    root:     Path = typer.Option(Path("."), "--root"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Print summary statistics for the project."""
    dag = _load_dag(root)
    q   = Queries(dag)

    n_bp     = sum(1 for n in dag.nodes if n.type != "lean_aux")
    n_aux    = sum(1 for n in dag.nodes if n.type == "lean_aux")
    n_proved = sum(1 for n in dag.nodes if n.type != "lean_aux" and n.proved)
    n_sorry  = sum(1 for n in dag.nodes if n.has_sorry)
    n_ready  = len(q.ready_to_prove())
    pct      = round(100 * n_proved / n_bp, 1) if n_bp else 0.0

    if json_out:
        sys.stdout.write(json.dumps({
            "blueprint_nodes": n_bp,
            "lean_aux_nodes":  n_aux,
            "edges":           len(dag.edges),
            "proved":          n_proved,
            "proved_pct":      pct,
            "with_sorry":      n_sorry,
            "ready_to_prove":  n_ready,
            "axioms":          len(dag.axioms),
            "leaves":          len(dag.leaves),
        }, indent=2))
        sys.stdout.write("\n")
        return

    console.print()
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim", min_width=22)
    table.add_column(justify="right", style="bold")
    table.add_row("Blueprint nodes",  str(n_bp))
    table.add_row("Lean-aux nodes",   str(n_aux))
    table.add_row("Edges",            str(len(dag.edges)))
    table.add_row("Proved (leanok)",  f"{n_proved}  [dim]({pct}%)[/dim]")
    table.add_row("With sorry",       str(n_sorry))
    table.add_row("Ready to prove",   str(n_ready))
    table.add_row("Axioms (dep=0)",   str(len(dag.axioms)))
    table.add_row("Leaves (rdep=0)",  str(len(dag.leaves)))
    console.print(table)
    console.print()


_SHOW_CHOICES = ("axioms", "leaves", "unproved", "sorry", "ready")


@app.command()
def show(
    what:     str           = typer.Argument(..., help=f"One of: {', '.join(_SHOW_CHOICES)}"),
    root:     Path          = typer.Option(Path("."), "--root"),
    top:      Optional[int] = typer.Option(None, "--top", "-n", help="Limit output to N rows."),
    json_out: bool          = typer.Option(False, "--json"),
) -> None:
    """Show a named subset of nodes (axioms, leaves, unproved, sorry, ready)."""
    if what not in _SHOW_CHOICES:
        err.print(
            f"  [red]✗[/red] Unknown filter '{what}'.\n"
            f"    Choose from: {', '.join(_SHOW_CHOICES)}"
        )
        raise typer.Exit(code=1)

    dag = _load_dag(root)
    q   = Queries(dag)

    nodes: list[GraphNode] = {
        "axioms":   q.axioms,
        "leaves":   q.leaves,
        "unproved": q.unproved,
        "sorry":    q.with_sorry,
        "ready":    q.ready_to_prove,
    }[what]()

    if not json_out:
        console.print()
        console.print(Rule(
            f"[bold]{what}[/bold]  [dim]({len(nodes)} nodes)[/dim]", style="dim"
        ))
        console.print()

    _print_nodes(nodes, json_out, top=top)

    if not json_out:
        console.print()


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
    sort:          str           = typer.Option("effort",   "--sort",          help="Sort by: effort, deps, id."),
    include_proved:bool          = typer.Option(False,      "--include-proved",help="Include already-proved nodes (only relevant with --sort effort)."),
    top:           Optional[int] = typer.Option(None,       "--top", "-n",     help="Limit to N results."),
    json_out:      bool          = typer.Option(False,      "--json"),
) -> None:
    """Query nodes with arbitrary filters and sorting.

    Examples:

        leandag query --unproved --max-deps 2 --sort effort --top 10

        leandag query --min-effort 100 --max-effort 500 --type theorem --json
    """
    dag  = _load_dag(root)
    q    = Queries(dag)

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
    elif sort == "id":
        nodes = sorted(nodes, key=lambda n: n.id)
        if top is not None:
            nodes = nodes[:top]
    else:
        err.print(f"  [red]✗[/red] Unknown sort '{sort}'. Choose from: effort, deps, id")
        raise typer.Exit(code=1)

    if not json_out:
        console.print()
        console.print(Rule(
            f"[bold]query[/bold]  [dim]({len(nodes)} results)[/dim]", style="dim"
        ))
        console.print()

    _print_nodes(nodes, json_out)

    if not json_out:
        console.print()
