# leandag

Dependency graph and complexity metrics for [Lean 4](https://lean-lang.org) + [leanblueprint](https://github.com/PatrickMassot/leanblueprint) projects.

Given a blueprint (LaTeX) and a Lean source tree, **leandag** builds a directed acyclic graph of every mathematical declaration, computes effort/complexity metrics, and exposes the result as a queryable CLI and a clean JSON API.

---

## Installation

```bash
pip install leandag
```

Or from source:

```bash
git clone https://github.com/AxelDlv00/LeanDAG
cd LeanDAG
pip install -e .
```

Requires Python ≥ 3.10.

---

## Quick start

```bash
cd my-lean-project/        # root containing blueprint/ and *.lean files

leandag init               # create .leandag/config.toml
leandag build --html       # parse sources, save DAG + HTML visualisation
leandag stats              # project overview
leandag show ready         # declarations ready to formalise now
leandag query --unproved --sort effort --top 10   # easiest remaining work
```

Open `.leandag/graph.html` in a browser for the interactive dependency graph.

---

## CLI reference

### `leandag init`

Create `.leandag/config.toml` (auto-detects the blueprint entry point).

```
Options:
  --entry TEXT        Blueprint entry .tex file (relative to root)
  --lean-root TEXT    Lean project root                [default: .]
  --root PATH         Project root                     [default: .]
```

### `leandag build`

Parse blueprint + Lean sources and save `.leandag/dag.json`.

```
Arguments:
  [ENTRY]             Entry .tex file (overrides config.toml)

Options:
  --html              Also write .leandag/graph.html
  --output, -o PATH   Override JSON output path
  --root PATH         Project root                     [default: .]
```

### `leandag html`

Regenerate `.leandag/graph.html` from the cached DAG (no re-parsing).

### `leandag stats [--json]`

Summary: node counts, proved %, ready-to-prove count, axioms, leaves.

### `leandag show WHAT [--json] [-n N]`

Show a named subset of nodes.

| `WHAT`    | Meaning |
|-----------|---------|
| `axioms`  | Nodes with no dependencies |
| `leaves`  | Nodes nothing else depends on |
| `unproved`| Blueprint nodes not yet `leanok` |
| `sorry`   | Nodes whose Lean proof contains `sorry` |
| `ready`   | Unproved nodes whose every dependency is already proved |

### `leandag query [OPTIONS] [--json]`

Arbitrary filter + sort.

```
Filter options:
  --min-deps N        Minimum direct dependencies
  --max-deps N        Maximum direct dependencies
  --min-effort N      Minimum effort_total
  --max-effort N      Maximum effort_total
  --chapter TEXT      Filter by chapter name
  --type TEXT         Filter by node type (lemma, theorem, …)
  --unproved          Only unproved blueprint nodes
  --sorry             Only nodes with sorry

Sort options:
  --sort TEXT         effort (default) | deps | id
  --include-proved    Include proved nodes in effort sort

Output:
  --top, -n N         Limit to N results
  --json              Machine-readable JSON array
```

---

## JSON schema

`dag.json` contains `nodes`, `edges`, and `meta`.

Every node object:

```jsonc
{
  "id":                    "lem:foo",       // unique label from \label{}
  "type":                  "lemma",         // lemma | theorem | definition | … | lean_aux
  "title":                 "Foo lemma",
  "chapter":               "Chapter 2",
  "statement":             "Let $G$ be …",  // LaTeX, blueprint commands stripped
  "uses":                  ["def:bar"],      // direct predecessor ids
  "lean_name":             "FooLemma",      // Lean declaration name (null if absent)
  "proved":                false,           // true iff \leanok in blueprint
  "proof_tex":             "…",             // body of nearest \begin{proof}
  "lean_source":           "lemma FooLemma …",
  "proof_size_lean":       null,            // char count after stripping comments (null if sorry)
  "has_sorry":             false,
  "dep_count":             1,               // number of direct dependencies
  "rdep_count":            3,               // number of nodes that depend on this
  "proof_size_tex":        240,             // char count of proof_tex (null if absent)
  "effort_local":          0,               // 0 if proved, proof_size_tex if draft, null if ∞
  "proof_size_tex_total":  480,             // Σ proof_size_tex over node + ancestors
  "proof_size_lean_total": 1200,
  "effort_total":          0                // Σ effort_local over node + ancestors (null = ∞)
}
```

`null` in any cumulative field means at least one ancestor has no proof at all (i.e., the cost is effectively infinite).

---

## Python API

```python
from leandag import BlueprintParser, LeanScanner, DAG, Queries

# Build from sources
blueprint_decls, proofs = BlueprintParser(Path("blueprint/src/web.tex")).parse()
lean_decls = LeanScanner().scan(Path("."))
dag = DAG.from_sources(blueprint_decls, proofs, lean_decls)

# Or reload from a saved file
dag = DAG.load(Path(".leandag/dag.json"))

# Query
q = Queries(dag)
q.ready_to_prove()                          # list[GraphNode]
q.filter(unproved_only=True, max_deps=3)
Queries.sort_by_effort(q.unproved(), top=10)

# Serialise
from leandag.exporters import JSONExporter, HTMLExporter
JSONExporter().export(dag, Path("dag.json"))
HTMLExporter().export(dag, Path("graph.html"))
```

---

## How complexity is measured

| Metric | Definition |
|--------|-----------|
| `effort_local` | Cost to prove this node alone: **0** if Lean proof exists, **tex chars** if only a LaTeX draft, **∞** (null) if no proof at all |
| `effort_total` | `effort_local` summed over the node and all its transitive dependencies |
| `proof_size_tex` / `proof_size_lean` | Raw character counts (comments stripped) |
| `*_total` variants | Cumulative over the ancestor subtree |

**Lean-aux nodes** (`type = "lean_aux"`) represent Lean declarations with no blueprint entry — helper lemmas, instances, infrastructure. They are included in the graph because they contribute real formalization cost even when invisible in the blueprint.

---

## Project layout

```
src/leandag/
├── models.py      # BlueprintDecl, LeanDecl, GraphNode, Edge
├── parser.py      # BlueprintParser — parses leanblueprint LaTeX
├── scanner.py     # LeanScanner — extracts declarations from .lean files
├── dag.py         # DAG — builds graph, computes metrics, loads/saves JSON
├── queries.py     # Queries — filter and sort layer
├── exporters.py   # JSONExporter, HTMLExporter
└── cli.py         # Typer CLI
```

---

## License

MIT
