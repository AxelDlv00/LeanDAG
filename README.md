# leandag

Dependency graph and complexity metrics for [Lean 4](https://lean-lang.org) + [leanblueprint](https://github.com/PatrickMassot/leanblueprint) projects.

Given a blueprint (LaTeX) and a Lean source tree, **leandag** builds a directed graph of every mathematical declaration, computes formalisation-effort metrics, and exposes it as a queryable CLI, a JSON API, and an interactive HTML graph. Output is selectable between human (rich) and machine (plain/JSON) formats, so an autoformalisation agent can drive it directly.

---

## Installation

```bash
pip install leandag          # or, from source:
git clone https://github.com/AxelDlv00/LeanDAG && cd LeanDAG && pip install -e .
```

Requires Python ≥ 3.10.

---

## Quick start

```bash
cd my-lean-project/          # root containing blueprint/ and *.lean files

leandag init                 # write .leandag/config.toml (auto-detects the entry .tex)
leandag build --html         # parse sources → .leandag/dag.json (+ graph.html)
leandag stats                # project overview, including effort done / remaining
leandag focus                # where to work next (ready / sorry / gaps / blockers)
```

Open `.leandag/graph.html` for the interactive graph.

---

## Output formats

Every command runs in three formats — pick per agent or human:

```bash
leandag --format json focus    # structured JSON on stdout (the agent contract)
leandag --plain build          # plain text, no colour/box-drawing
leandag stats --json           # per-command shortcut, equivalent to -f json
```

In `json`/`text` mode, progress lines go to **stderr** and the structured payload to **stdout**, so an agent reads clean data from stdout. `text`/`json` need no `rich` at runtime.

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `init` | Create `.leandag/config.toml` (`--entry`, `--lean-root`, `--root`). |
| `build [ENTRY]` | Parse sources, save `dag.json`. `--html` also writes the graph; `--json` emits a build report (counts, effort, conflicts, unmatched `\lean{}`, unknown `\uses`). |
| `html` | Regenerate `graph.html` from the cached DAG. |
| `stats` | Counts, proved %, ready/gaps/unmatched, isolated nodes, and the effort summary. |
| `focus` | Agent agenda: `ready_to_formalize` (ranked by impact), `has_sorry`, `needs_lean_statement`, `needs_leanok`, `unmatched_lean`. |
| `show WHAT` | A named subset: `axioms`, `leaves`, `isolated`, `unproved`, `sorry`, `ready`, `gaps`, `leanok`. |
| `query` | Arbitrary filter + sort (`--sort effort\|deps\|impact\|id`, `--unproved`, `--isolated`, `--sorry`, `--max-deps`, `--chapter`, `--type`, `--top`, …). |

The scanner runs in parallel across processes and skips hidden directories (`.lake`, `.git`, tooling/snapshot dirs, …) and re-symlinked copies, so stale duplicates don't pollute the graph.

---

## Metrics

| Metric | Definition |
|--------|-----------|
| `effort_local` | Cost to do this node alone: **0** if a Lean proof exists or it is `\mathlibok` (already in mathlib), **LaTeX-proof chars** if only a draft, **∞** (`null`) if nothing to estimate from. |
| `effort_total` | `effort_local` over the node and all transitive dependencies (`null` = ∞ somewhere upstream). |
| `proof_size_tex` / `proof_size_lean` | Raw char counts, comments stripped (`_total` = cumulative over ancestors). |
| `dep_count` / `rdep_count` | Direct dependencies / direct dependents. |
| `descendant_count` | Transitive dependents — **impact**: how much formalising this node unblocks. |

**Project effort** (`stats` / `focus` / `build --json`):

- `effort_done` — Σ Lean code already written (uncommented, sorry-free). `\mathlibok` nodes are effort-0 but contribute no chars here (no local code was written).
- `effort_remaining_lower` — Σ finite `effort_local` (a lower bound; ∞-nodes omitted).
- `effort_remaining_unknown_nodes` — count of ∞-nodes.
- `effort_remaining` — the bound, or `null` if any node is ∞.

**Lean-aux nodes** (`type = "lean_aux"`) are Lean declarations with no blueprint entry (helper lemmas, instances, infrastructure); they still carry real formalisation cost. See [MathematicalDetails.md](MathematicalDetails.md) for the precise effort/complexity definitions.

---

## Interactive graph

Force-directed layout (connected declarations cluster together; arrows show direction). Each node is a dot:

- **Colour = local effort** — green = done (0), blue = `\mathlibok` (in mathlib), yellow→orange = increasing draft effort, red = ∞ (no proof).
- **Glyphs** — `✓` complete Lean proof · `⚠` `sorry` · `ⓜ` in mathlib (`\mathlibok`) · `λ` Lean declaration · `★` LaTeX proof · `§` statement only.
- **Click** highlights a node's entire transitive cone (ancestors + descendants + edges); double-click focuses it; search jumps.
- A **project-stats overlay** shows proved %, sorry/ready/gap counts and effort done/remaining at a glance.
- **File view** (toolbar) tints the *whole* background by source file — Lean or LaTeX — colouring each pixel by its nearest node (an exact Voronoi map with clean borders) and listing a per-file colour legend, so you can see which declarations live together. Colours are derived from the file name, so they stay stable and distinct under focus/reset/filtering. Nodes keep their effort colours on top.
- Filter by **node-set** (all / blueprint / Lean), component, or chapter. The **show isolated (N)** toggle reveals declarations with no edges (laid out in a tidy grid); the count `N` is shown up front.

Blueprint `\newcommand`/`\def`/`\DeclareMathOperator` macros are extracted and fed to KaTeX, so blueprint notation (and `$…$`, `$$…$$`, `\(…\)`, `\[…\]`) renders.

---

## JSON / Python API

`dag.json` holds `nodes`, `edges`, and `meta` (`macros`, `unmatched_lean`, axioms/leaves). Node fields mirror the metrics above (`id`, `type`, `statement`, `uses`, `lean_name`, `proved`, `mathlib_ok`, `has_sorry`, `effort_local`, `effort_total`, `descendant_count`, `tex_file`, `lean_file`, …).

```python
from pathlib import Path
from leandag import BlueprintParser, LeanScanner, DAG, Queries

parser = BlueprintParser(Path("blueprint/src/web.tex"))
decls, proofs = parser.parse()
lean = LeanScanner().scan(Path("."))
dag  = DAG.from_sources(decls, proofs, lean, macros=parser.macros)
# or: dag = DAG.load(Path(".leandag/dag.json"))

q = Queries(dag)
q.ready_to_prove()                                 # what can I work on now?
q.isolated()                                        # declarations linked to nothing
q.needs_lean_statement()                           # blueprint statements lacking \lean{}
Queries.sort_by_impact(q.unproved(), top=10)       # biggest blockers
dag.effort_summary()                               # project effort accounting
```

---

## Project layout

```
src/leandag/
├── models.py     # BlueprintDecl, LeanDecl, GraphNode, Edge
├── parser.py     # BlueprintParser — leanblueprint LaTeX + macros
├── scanner.py    # LeanScanner — parallel .lean declaration extraction
├── dag.py        # DAG — graph, metrics, effort summary, load/save
├── queries.py    # Queries — filter / sort / focus helpers
├── exporters.py  # JSONExporter, HTMLExporter
├── reporter.py   # Reporter — rich / text / json output
└── cli.py        # Typer CLI
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
