from __future__ import annotations

import colorsys
import json
import math
from pathlib import Path
from typing import Optional

from .dag import DAG
from .models import GraphNode


# ── Effort colour scale (graph canvas) ─────────────────────────────────────────
# Nodes are drawn as dots whose colour encodes the *local effort remaining*:
#   0 (already formalised) → green, a distinct "done" colour; growing finite
#   effort → yellow→orange ramp; ∞ (no proof to estimate from) → vivid red.
# The three regions (green / warm ramp / red) are visually disjoint — green is
# not part of the gradient — so state is readable at a glance.

_DONE_FILL, _DONE_BORDER = "#22c55e", "#15803d"   # effort 0 — formalised (green)
_INF_FILL,  _INF_BORDER  = "#ef4444", "#7f1d1d"   # effort ∞ — no estimate (red)
_GRAD_HUE_HI = 52    # yellow (smallest finite effort)
_GRAD_HUE_LO = 24    # orange (largest finite effort)


def _hsl_hex(hue: float, sat: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb(hue / 360.0, light, sat)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _effort_color(effort: Optional[int], max_effort: int) -> tuple[str, str]:
    """Return ``(background, border)`` hex for a node's local effort."""
    if effort is None:
        return _INF_FILL, _INF_BORDER
    if effort <= 0:
        return _DONE_FILL, _DONE_BORDER
    # sqrt-compress so the wide range of finite sizes spreads across the ramp
    t   = min(1.0, math.sqrt(effort) / math.sqrt(max_effort)) if max_effort > 0 else 0.0
    hue = _GRAD_HUE_HI - (_GRAD_HUE_HI - _GRAD_HUE_LO) * t
    return _hsl_hex(hue, 0.72, 0.55), _hsl_hex(hue, 0.6, 0.38)


class JSONExporter:
    """Serialise a DAG to a JSON file."""

    def export(self, dag: DAG, path: Path) -> None:
        data = {
            "nodes": [n.to_dict() for n in dag.nodes],
            "edges": [{"from": e.source, "to": e.target} for e in dag.edges],
            "meta":  {
                "num_nodes": len(dag.nodes),
                "num_edges": len(dag.edges),
                "axioms":    [n.id for n in dag.axioms],
                "leaves":    [n.id for n in dag.leaves],
                "macros":    dag.macros,
                "unmatched_lean": [list(x) for x in dag.unmatched_lean],
            },
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


class HTMLExporter:
    """Write an interactive vis-network HTML navigator for a DAG.

    The page hides isolated ``lean_aux`` nodes by default, lays the dependency
    graph out left→right, and lets you focus a node's dependency cone, filter by
    connected component or chapter, and search by id — so it stays usable even
    on large, sparse graphs (which previously rendered as a blank canvas).
    """

    def export(self, dag: DAG, path: Path) -> None:
        nodes = dag.nodes
        edges = dag.edges

        # Reference point for the gradient: the largest finite local effort.
        max_effort = max(
            (n.effort_local for n in nodes
             if n.effort_local is not None and n.effort_local > 0),
            default=1,
        )

        vis_nodes   = [self._vis_node(n, max_effort) for n in nodes]
        vis_edges   = [{"from": e.source, "to": e.target, "arrows": "to"} for e in edges]
        graph_json  = json.dumps({"nodes": vis_nodes, "edges": vis_edges}, ensure_ascii=False)
        detail_json = json.dumps({n.id: n.to_dict() for n in nodes}, ensure_ascii=False)
        macros_json = json.dumps(dag.macros, ensure_ascii=False)
        legend_items = (
            f'<span class="leg-dot" style="background:{_DONE_FILL}"></span>'
            '<span class="leg-txt">done</span>'
            '<span class="leg-bar"></span>'
            '<span class="leg-txt">more effort</span>'
            f'<span class="leg-dot" style="background:{_INF_FILL}"></span>'
            '<span class="leg-txt">∞ no proof</span>'
        )

        # Scalars/markup first, then the JSON payloads last so injected data is
        # never re-scanned for placeholders.
        html = (
            _HTML_TEMPLATE
            .replace("__NUM_NODES__",    str(len(nodes)))
            .replace("__NUM_EDGES__",    str(len(edges)))
            .replace("__LEGEND_ITEMS__", legend_items)
            .replace("__GRAPH_JSON__",   graph_json)
            .replace("__DETAIL_JSON__",  detail_json)
            .replace("__MACROS_JSON__",  macros_json)
        )
        path.write_text(html, encoding="utf-8")

    @staticmethod
    def _status_glyphs(n: GraphNode) -> str:
        """Compact per-node state markers (see the toolbar's symbol legend).

        Slot 1 — Lean side:  ✓ complete proof · ⚠ has sorry · λ declared only.
        Slot 2 — LaTeX side: ★ has a written proof · § statement only.
        """
        has_lean = bool(n.lean_source) or n.type == "lean_aux"
        if n.has_sorry:
            lean_g = "⚠"
        elif n.proof_size_lean is not None:
            lean_g = "✓"
        elif has_lean:
            lean_g = "λ"
        else:
            lean_g = ""

        if n.proof_size_tex is not None:
            tex_g = "★"
        elif n.type != "lean_aux":
            tex_g = "§"
        else:
            tex_g = ""

        return lean_g + tex_g

    @staticmethod
    def _vis_node(n: GraphNode, max_effort: int) -> dict:
        is_aux       = n.type == "lean_aux"
        is_inf       = n.effort_local is None
        fill, border = _effort_color(n.effort_local, max_effort)

        # ∞ nodes are drawn a touch larger so they read as the salient blockers.
        size = 16 if is_inf else 11

        glyphs = HTMLExporter._status_glyphs(n)
        label  = n.id.split(":")[-1] + (f"\n{glyphs}" if glyphs else "")

        return {
            "id":    n.id,
            "label": label,
            "shape": "dot",
            "size":  size,
            "color": {
                "background": fill,
                "border":     border,
                "highlight":  {"background": fill, "border": "#0f172a"},
            },
            "borderWidth": 2,
            "font":  {"size": 11, "multi": False,
                      "face": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                      "color": "#334155"},
            # lean_aux nodes (no blueprint entry) get a dashed ring to stay
            # distinguishable now that colour encodes effort rather than type.
            "shapeProperties": {"borderDashes": [3, 3]} if is_aux else {},
        }


# ── HTML template ──────────────────────────────────────────────────────────────
# NOTE: substitution is done with str.replace() on the __TOKEN__ placeholders
# below — NOT str.format — so the JavaScript can use { } freely.

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Blueprint dependency graph</title>
<link rel="stylesheet" href="https://unpkg.com/katex@0.16.9/dist/katex.min.css">
<script src="https://unpkg.com/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
:root {
  --sidebar-bg: #0f172a;
  --toolbar-bg: #1e293b;
  --surface:    #1a2744;
  --border:     #1e3a5f;
  --text:       #e2e8f0;
  --muted:      #64748b;
  --accent:     #60a5fa;
  --green:      #4ade80;
  --green-bg:   rgba(74,222,128,.12);
  --red:        #f87171;
  --red-bg:     rgba(248,113,113,.12);
  --orange:     #fb923c;
  --orange-bg:  rgba(251,146,60,.12);
  --code-bg:    #090d16;
  --radius:     7px;
  --mono: 'JetBrains Mono','Fira Code','Cascadia Code','Consolas','Monaco',monospace;
  --sans: -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
}

html { margin:0; padding:0; height:100%; overflow:hidden; }
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
body { font-family:var(--sans); display:flex; flex-direction:column;
       height:100%; background:#f8fafc; color:var(--text); }

/* ── Toolbar ─────────────────────────────────────────────────── */
#toolbar {
  background:var(--toolbar-bg); height:44px; padding:0 16px;
  display:flex; align-items:center; gap:14px; flex-shrink:0;
  border-bottom:1px solid #263045;
}
.brand { font-size:13px; font-weight:700; color:#f1f5f9; letter-spacing:.03em; }
.stat  { font-size:12px; color:#64748b; white-space:nowrap; }
.legend { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }
.leg-dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.leg-bar {
  width:54px; height:8px; border-radius:4px; display:inline-block;
  background:linear-gradient(90deg,#facc15,#f59e0b,#f97316);
}
.leg-txt { font-size:10px; font-weight:600; color:#94a3b8; }
.sym-legend { padding-left:10px; margin-left:4px; border-left:1px solid #334155; gap:8px; }
.hint { margin-left:auto; font-size:11px; color:#334155; white-space:nowrap; }

/* ── Controls bar ────────────────────────────────────────────── */
#controls {
  background:#16233b; min-height:40px; padding:6px 16px;
  display:flex; align-items:center; gap:10px; flex-shrink:0;
  border-bottom:1px solid #263045; flex-wrap:wrap;
}
#controls input[type=text], #controls select {
  background:#0f1f3d; color:var(--text); border:1px solid #1e3a5f;
  border-radius:5px; font-size:12px; padding:5px 8px;
  font-family:var(--sans); outline:none;
}
#controls input[type=text] { width:200px; }
#controls input[type=text]:focus, #controls select:focus { border-color:var(--accent); }
#controls select { max-width:260px; cursor:pointer; }
#controls .chk { font-size:12px; color:#94a3b8; display:flex; align-items:center; gap:5px; cursor:pointer; user-select:none; }
.btn {
  background:#1e293b; color:#cbd5e1; border:1px solid #334155;
  border-radius:5px; font-size:12px; padding:5px 12px; cursor:pointer;
}
.btn:hover { background:#263045; }
.pill {
  display:inline-flex; align-items:center; gap:7px;
  background:#172554; color:#93c5fd; border:1px solid #1e3a8a;
  border-radius:12px; font-size:11px; padding:3px 4px 3px 11px; cursor:pointer;
  max-width:280px;
}
.pill .lbl { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.pill .x { font-weight:700; padding:0 6px; border-radius:9px; }
.pill:hover .x { background:#1e3a8a; }

/* ── Main layout ─────────────────────────────────────────────── */
#main  { display:flex; flex:1; overflow:hidden; min-height:0; position:relative; }
#graph { flex:1; min-height:0; background:#f8fafc; }

/* ── Project-stats overlay ───────────────────────────────────── */
#stats-panel {
  position:absolute; top:12px; left:12px; z-index:5;
  background:rgba(15,23,42,.9); border:1px solid #1e3a5f; border-radius:8px;
  padding:10px 12px; min-width:188px; backdrop-filter:blur(3px);
  font-size:11px; color:#cbd5e1; box-shadow:0 4px 16px rgba(0,0,0,.25);
}
#stats-panel h4 {
  font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
  color:#64748b; margin-bottom:7px;
}
#stats-panel .row { display:flex; justify-content:space-between; gap:14px; line-height:1.7; }
#stats-panel .row .v { font-family:var(--mono); color:#f1f5f9; }
#stats-panel .v.done { color:var(--green); }
#stats-panel .v.work { color:var(--orange); }
#stats-panel .v.inf  { color:var(--red); }
#stats-panel .bar {
  height:6px; border-radius:3px; background:#1e293b; margin:7px 0 3px; overflow:hidden;
}
#stats-panel .bar > span { display:block; height:100%; background:var(--green); }
#stats-panel .sep { border-top:1px solid #1e3a5f; margin:7px 0; }
#graph canvas { display:block; }

/* ── Sidebar ─────────────────────────────────────────────────── */
#sidebar {
  width:340px; flex-shrink:0;
  background:var(--sidebar-bg);
  border-left:1px solid #1e293b;
  display:flex; flex-direction:column; overflow:hidden;
}
#sidebar-empty {
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:10px;
}
#sidebar-empty svg { opacity:.2; }
#sidebar-empty p { font-size:13px; color:#334155; }
#sidebar-content {
  flex:1; overflow-y:auto; padding:10px;
  display:flex; flex-direction:column; gap:8px;
}
#sidebar-content::-webkit-scrollbar { width:4px; }
#sidebar-content::-webkit-scrollbar-thumb { background:#1e3a5f; border-radius:2px; }

/* ── Cards ───────────────────────────────────────────────────── */
.card {
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:12px;
}
.card-title {
  font-size:10px; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; color:var(--muted); margin-bottom:10px;
}
.btn-focus {
  width:100%; margin-top:10px; background:#172554; color:#93c5fd;
  border:1px solid #1e3a8a; border-radius:5px; font-size:11px;
  font-weight:600; padding:7px; cursor:pointer; letter-spacing:.02em;
}
.btn-focus:hover { background:#1e3a8a; color:#bfdbfe; }

/* ── Header card ─────────────────────────────────────────────── */
.node-badges { display:flex; gap:5px; flex-wrap:wrap; margin-bottom:8px; }
.badge {
  display:inline-block; padding:2px 8px; border-radius:10px;
  font-size:10px; font-weight:700; letter-spacing:.04em;
}
.badge-type    { background:#172554; color:#93c5fd; border:1px solid #1e3a8a44; }
.badge-proved  { background:var(--green-bg);  color:var(--green);  border:1px solid rgba(74,222,128,.25); }
.badge-sorry   { background:var(--orange-bg); color:var(--orange); border:1px solid rgba(251,146,60,.25); }
.badge-unproved{ background:var(--red-bg);    color:var(--red);    border:1px solid rgba(248,113,113,.25); }
.node-title   { font-size:15px; font-weight:600; color:#f1f5f9; line-height:1.35; margin-bottom:5px; }
.node-id      { font-family:var(--mono); font-size:11px; color:#475569; }
.node-chapter { font-size:11px; color:#334155; margin-top:3px; }
.lean-ref     { font-size:11px; color:var(--muted); margin-top:6px; }
.lean-ref code{ font-family:var(--mono); color:var(--accent); }

/* ── Structure card ──────────────────────────────────────────── */
.degrees { display:flex; gap:20px; margin-bottom:10px; }
.degree  { display:flex; flex-direction:column; align-items:center; gap:2px; }
.degree-val   { font-size:22px; font-weight:700; color:#f1f5f9; line-height:1; }
.degree-label { font-size:10px; color:var(--muted); text-align:center; }
.deps-list  { display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px; }
.deps-sub   { font-size:10px; color:var(--muted); margin:6px 0 4px; letter-spacing:.03em; }
.dep-chip {
  font-family:var(--mono); font-size:10px; padding:3px 7px;
  background:#0f1f3d; border:1px solid #1e3a5f;
  border-radius:4px; color:var(--accent); cursor:pointer; transition:background .15s;
}
.dep-chip:hover { background:#172554; }
.no-deps { font-size:12px; color:var(--muted); font-style:italic; }

/* ── Metrics card ────────────────────────────────────────────── */
.metrics-grid {
  display:grid; grid-template-columns:auto 1fr 1fr;
  gap:5px 10px; align-items:center;
}
.col-head { font-size:10px; color:#334155; text-align:right; font-weight:600; }
.m-label  { font-size:11px; color:var(--muted); }
.m-val    { font-family:var(--mono); font-size:12px; color:#94a3b8; text-align:right; }
.m-done   { color:var(--green); font-weight:700; }
.m-inf    { color:var(--red);   font-weight:700; }
.m-work   { color:var(--orange); }

/* ── Section header ──────────────────────────────────────────── */
.sec-hdr {
  display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px;
}
.chars-pair { font-family:var(--mono); font-size:10px; color:#334155; }
.chars-inf  { color:var(--red); }
.chars-val  { color:#475569; }

/* ── LaTeX rendered block ────────────────────────────────────── */
.latex-rendered {
  font-family:var(--sans); font-size:13px; line-height:1.7;
  color:#94a3b8; overflow-x:auto; min-height:1.5em;
}
.latex-rendered .katex-display { margin:6px 0; overflow-x:auto; }
.latex-rendered em { font-style:italic; color:#cbd5e1; }
.latex-rendered strong { font-weight:600; color:#cbd5e1; }
.latex-rendered.empty { color:#1e3a5f; font-style:italic; }

/* ── Lean code block ─────────────────────────────────────────── */
.code-block {
  font-family:var(--mono); font-size:11px; line-height:1.6;
  background:var(--code-bg); color:#abb2bf;
  border:1px solid #1a2744; border-radius:5px;
  padding:10px 12px; white-space:pre; overflow:auto;
  max-height:220px;
}
.code-block::-webkit-scrollbar { width:4px; height:4px; }
.code-block::-webkit-scrollbar-thumb { background:#1e3a5f; border-radius:2px; }
.code-block.empty { color:#1e3a5f; font-style:italic; white-space:normal; }

/* ── Lean syntax colours (One Dark palette) ──────────────────── */
.hl-kw      { color:#c678dd; }
.hl-tactic  { color:#61afef; }
.hl-type    { color:#e5c07b; }
.hl-comment { color:#5c6370; font-style:italic; }
.hl-str     { color:#98c379; }
.hl-num     { color:#d19a66; }
</style>
</head>
<body>
<div id="toolbar">
  <span class="brand">Blueprint DAG</span>
  <span class="stat" id="stat">__NUM_NODES__ nodes &middot; __NUM_EDGES__ edges</span>
  <span class="legend">__LEGEND_ITEMS__</span>
  <span class="legend sym-legend">
    <span class="leg-txt">✓ Lean proof</span>
    <span class="leg-txt">⚠ sorry</span>
    <span class="leg-txt">λ Lean decl</span>
    <span class="leg-txt">★ LaTeX proof</span>
    <span class="leg-txt">§ statement</span>
  </span>
  <span class="hint">click = highlight cone &middot; double-click = focus &middot; ctrl+scroll = zoom</span>
</div>
<div id="controls">
  <input id="search" type="text" list="node-ids" placeholder="Search node id…" autocomplete="off" spellcheck="false">
  <datalist id="node-ids"></datalist>
  <select id="nodeset" title="Which declarations to include">
    <option value="union">All declarations</option>
    <option value="blueprint">Blueprint only</option>
    <option value="lean">Lean only</option>
  </select>
  <select id="component"><option value="">All components</option></select>
  <select id="chapter"><option value="">All chapters</option></select>
  <label class="chk"><input type="checkbox" id="orphans"> show isolated nodes</label>
  <span id="focus-pill" class="pill" style="display:none" title="Clear focus">
    <span class="lbl"></span><span class="x">&times;</span>
  </span>
  <button id="reset" class="btn">Reset view</button>
</div>
<div id="main">
  <div id="graph"></div>
  <div id="stats-panel"></div>
  <aside id="sidebar">
    <div id="sidebar-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
           stroke="#334155" stroke-width="1.2" stroke-linecap="round">
        <path d="M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>
        <line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="13" y2="13"/>
      </svg>
      <p>Click a node to inspect it</p>
    </div>
    <div id="sidebar-content" style="display:none"></div>
  </aside>
</div>

<script>
const graphData = __GRAPH_JSON__;
const allNodes  = __DETAIL_JSON__;
const katexMacros = __MACROS_JSON__;   // blueprint-defined \newcommand etc.

const $ = id => document.getElementById(id);

// ── Graph structure: adjacency, degree, components ──────────────────────────

const succ = {}, pred = {}, deg = {};
for (const id in allNodes) { succ[id] = []; pred[id] = []; deg[id] = 0; }
for (const e of graphData.edges) {
  if (succ[e.from]) succ[e.from].push(e.to);
  if (pred[e.to])   pred[e.to].push(e.from);
  deg[e.from] = (deg[e.from] || 0) + 1;
  deg[e.to]   = (deg[e.to]   || 0) + 1;
}
const isOrphan = id => !(deg[id] > 0);

// weakly-connected components via union-find (orphans excluded)
const parent = {};
function find(x) { while (parent[x] !== x) x = parent[x] = parent[parent[x]]; return x; }
for (const id in allNodes) parent[id] = id;
for (const e of graphData.edges)
  if (parent[e.from] !== undefined && parent[e.to] !== undefined)
    parent[find(e.from)] = find(e.to);

const compMembers = {};
for (const id in allNodes) {
  if (isOrphan(id)) continue;
  const r = find(id);
  (compMembers[r] = compMembers[r] || []).push(id);
}
const components = Object.values(compMembers).sort((a, b) => b.length - a.length);
const compOf = {};
components.forEach((m, i) => m.forEach(id => compOf[id] = i));

// ── Project-stats overlay ────────────────────────────────────────────────────

function renderStats() {
  const vals = Object.values(allNodes);
  const bp   = vals.filter(n => n.type !== "lean_aux");
  const proved = bp.filter(n => n.proved).length;
  const sorry  = vals.filter(n => n.has_sorry).length;
  const provedIds = new Set(vals.filter(n => n.proved).map(n => n.id));
  const ready = bp.filter(n => !n.proved &&
                  n.uses.every(d => !(d in allNodes) || provedIds.has(d))).length;
  const gaps  = bp.filter(n => !n.lean_source).length;

  let done = 0, remLower = 0, infNodes = 0;
  for (const n of vals) {
    if (n.proof_size_lean != null) done += n.proof_size_lean;
    if (n.effort_local == null) infNodes++; else remLower += n.effort_local;
  }
  const pct = bp.length ? Math.round(100 * proved / bp.length) : 0;
  const fmt = v => v.toLocaleString();

  $("stats-panel").innerHTML = `
    <h4>Project</h4>
    <div class="row"><span>Proved</span><span class="v done">${proved}/${bp.length} · ${pct}%</span></div>
    <div class="bar"><span style="width:${pct}%"></span></div>
    <div class="row"><span>With sorry</span><span class="v ${sorry ? 'inf' : ''}">${sorry}</span></div>
    <div class="row"><span>Ready to prove</span><span class="v">${ready}</span></div>
    <div class="row"><span>Needs \\lean{}</span><span class="v">${gaps}</span></div>
    <div class="sep"></div>
    <h4>Effort (chars)</h4>
    <div class="row"><span>Done</span><span class="v done">${fmt(done)}</span></div>
    <div class="row"><span>Remaining ≥</span><span class="v work">${fmt(remLower)}</span></div>
    <div class="row"><span>∞ nodes</span><span class="v inf">${infNodes}</span></div>
  `;
}
renderStats();

// a human label for each component: its highest-degree member
function compRepr(members) {
  let best = members[0];
  for (const id of members) if ((deg[id] || 0) > (deg[best] || 0)) best = id;
  return best.split(":").pop();
}

const chapters = [...new Set(
  Object.values(allNodes).map(n => n.chapter).filter(Boolean)
)].sort();

// ── Populate controls ───────────────────────────────────────────────────────

$("node-ids").innerHTML =
  Object.keys(allNodes).sort().map(id => `<option value="${id}">`).join("");

$("component").insertAdjacentHTML("beforeend",
  components.map((m, i) =>
    `<option value="${i}">#${i + 1} · ${m.length} nodes · ${compRepr(m)}</option>`
  ).join(""));

$("chapter").insertAdjacentHTML("beforeend",
  chapters.map(c => `<option value="${c.replace(/"/g, "&quot;")}">${c}</option>`).join(""));

// ── Visible-set state & computation ─────────────────────────────────────────

const state = { showOrphans: false, focus: null, component: null, chapter: null, nodeset: "union" };

// Which universe a node belongs to. A node "has Lean" if it carries Lean source
// (lean_aux nodes always do; blueprint nodes do once their \lean{} resolved).
const hasLean    = n => n.type === "lean_aux" || !!(n.lean_source && n.lean_source.length);
const inBlueprint = n => n.type !== "lean_aux";
function inNodeset(id) {
  const n = allNodes[id];
  if (state.nodeset === "blueprint") return inBlueprint(n);
  if (state.nodeset === "lean")      return hasLean(n);
  return true;                                   // union
}

function coneOf(id) {
  const out = new Set([id]);
  const walk = (adj, start) => {
    const st = [start];
    while (st.length) {
      const x = st.pop();
      for (const y of (adj[x] || [])) if (!out.has(y)) { out.add(y); st.push(y); }
    }
  };
  walk(pred, id);   // everything this node (transitively) depends on
  walk(succ, id);   // everything that (transitively) depends on it
  return out;
}

// all transitive predecessors of id (its full upstream dependency set)
function ancestorsOf(id) {
  const out = new Set();
  const st = [...(pred[id] || [])];
  while (st.length) {
    const x = st.pop();
    if (!out.has(x)) { out.add(x); for (const y of (pred[x] || [])) st.push(y); }
  }
  return out;
}

function visibleSet() {
  if (state.focus && allNodes[state.focus]) {
    return new Set([...coneOf(state.focus)].filter(inNodeset));
  }
  let ids = Object.keys(allNodes).filter(inNodeset);
  if (!state.showOrphans)      ids = ids.filter(id => !isOrphan(id));
  if (state.component !== null) ids = ids.filter(id => compOf[id] === state.component);
  if (state.chapter)            ids = ids.filter(id => allNodes[id].chapter === state.chapter);
  return new Set(ids);
}

// ── Network ─────────────────────────────────────────────────────────────────

const nodesDS = new vis.DataSet();
const edgesDS = new vis.DataSet();

// Force-directed layout: connected nodes attract, so each declaration settles
// next to what it depends on. Direction is conveyed by the arrows, not columns.
const N_TOTAL = graphData.nodes.length;
const PHYSICS_OPTS = {
  enabled: true,
  solver: "forceAtlas2Based",
  forceAtlas2Based: {
    gravitationalConstant: -45, centralGravity: 0.012,
    springLength: 85, springConstant: 0.08,
    damping: 0.45, avoidOverlap: 0.7,
  },
  stabilization: { enabled: true, iterations: 300, updateInterval: 25, fit: false },
  minVelocity: 0.75, maxVelocity: 30,
};

const network = new vis.Network(
  $("graph"),
  { nodes: nodesDS, edges: edgesDS },
  {
    // physics does the placement; improvedLayout seeds it (skip on huge graphs)
    layout: { improvedLayout: N_TOTAL <= 250 },
    physics: { enabled: false },   // enabled per-apply, then frozen once settled
    edges: {
      smooth: { enabled: false },
      color: { color: "#cbd5e1", highlight: "#64748b" },
      arrows: { to: { scaleFactor: .55 } },
      width: 1,
    },
    nodes: { shape: "dot" },
    interaction: { hover: true, tooltipDelay: 150, zoomView: false },
  }
);

// Once a settle finishes, freeze the simulation (so the view is stable and
// draggable) and frame the result.
network.on("stabilizationIterationsDone", () => {
  network.setOptions({ physics: false });
  fitFloored();
});

// ── Navigation: swipe = pan · Ctrl+scroll / pinch = zoom ─────────────────────

let ZOOM_MIN = 0.05;
const ZOOM_MAX = 3.0;
const FIT_FLOOR = 0.34;          // never auto-zoom below this — keeps nodes legible
let graphBounds = null;

function recomputeBounds() {
  const pts = Object.values(network.getPositions());
  if (pts.length) {
    const pad = 200;
    graphBounds = {
      left:   Math.min(...pts.map(p => p.x)) - pad,
      right:  Math.max(...pts.map(p => p.x)) + pad,
      top:    Math.min(...pts.map(p => p.y)) - pad,
      bottom: Math.max(...pts.map(p => p.y)) + pad,
    };
  } else graphBounds = null;
}

function fitFloored() {
  network.fit({ animation: false });
  const fitScale = network.getScale();
  // The most-zoomed-out limit tracks the graph's actual extent — a little past
  // the scale at which everything fits — instead of a fixed floor. So a small
  // graph can't be shrunk to a speck, and a huge one can still reach overview.
  ZOOM_MIN = Math.max(0.02, Math.min(fitScale * 0.7, ZOOM_MAX));
  // For very large graphs `fit` is sub-pixel; don't *start* there (keeps nodes
  // legible) but still allow zooming out to it.
  if (fitScale < FIT_FLOOR) network.moveTo({ scale: FIT_FLOOR, animation: false });
  recomputeBounds();
}

$("graph").addEventListener("wheel", e => {
  e.preventDefault();
  e.stopPropagation();
  const pos = network.getViewPosition();
  const sc  = network.getScale();
  if (e.ctrlKey) {
    const f        = e.deltaY > 0 ? 0.9 : 1 / 0.9;
    const newScale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, sc * f));
    network.moveTo({ scale: newScale, animation: false });
  } else {
    let nx = pos.x + e.deltaX / sc;
    let ny = pos.y + e.deltaY / sc;
    if (graphBounds) {
      nx = Math.max(graphBounds.left, Math.min(graphBounds.right,  nx));
      ny = Math.max(graphBounds.top,  Math.min(graphBounds.bottom, ny));
    }
    network.moveTo({ position: { x: nx, y: ny }, animation: false });
  }
}, { capture: true, passive: false });

// ── Apply current filter state to the canvas ────────────────────────────────

function apply() {
  const vis   = visibleSet();
  const nodes = graphData.nodes.filter(n => vis.has(n.id));
  const edges = graphData.edges.filter(e => vis.has(e.from) && vis.has(e.to));

  nodesDS.clear(); edgesDS.clear();
  nodesDS.add(nodes); edgesDS.add(edges);

  $("stat").innerHTML =
    `${nodes.length} / ${graphData.nodes.length} nodes &middot; ${edges.length} edges`;

  const pill = $("focus-pill");
  if (state.focus) {
    pill.style.display = "inline-flex";
    pill.querySelector(".lbl").textContent = "focus: " + state.focus.split(":").pop();
  } else {
    pill.style.display = "none";
  }

  // Re-settle the now-visible subset; the stabilization handler freezes and
  // fits when it finishes. A lone node needs no simulation.
  if (nodes.length > 1) {
    network.setOptions({ physics: PHYSICS_OPTS });
  } else {
    setTimeout(fitFloored, 0);
  }
}

function syncControls() {
  $("orphans").checked  = state.showOrphans;
  $("nodeset").value    = state.nodeset;
  $("component").value  = state.component === null ? "" : String(state.component);
  $("chapter").value    = state.chapter || "";
}

// ── Reveal-aware navigation ─────────────────────────────────────────────────

function goTo(id) {
  if (!allNodes[id]) return;
  if (!visibleSet().has(id)) {            // relax filters until the node is shown
    state.focus = null;
    state.component = null;
    state.chapter = null;
    if (!inNodeset(id)) state.nodeset = "union";
    if (isOrphan(id)) state.showOrphans = true;
    syncControls();
    apply();
  }
  setTimeout(() => jumpTo(id), 70);
}

function jumpTo(id) {
  if (!allNodes[id]) return;
  network.selectNodes([id]);
  network.focus(id, { scale: 1.2, animation: { duration: 400, easingFunction: "easeInOutQuad" } });
  renderNode(id);
  highlightCone(id);
}

function setFocus(id) {
  if (!allNodes[id]) return;
  state.focus = id;
  apply();
  renderNode(id);
  setTimeout(() => jumpTo(id), 70);
}

function clearFocus() { state.focus = null; apply(); }

function resetView() {
  state.showOrphans = false;
  state.focus = null;
  state.component = null;
  state.chapter = null;
  state.nodeset = "union";
  $("search").value = "";
  syncControls();
  apply();
}

// ── Control wiring ──────────────────────────────────────────────────────────

$("orphans").addEventListener("change", e => {
  state.showOrphans = e.target.checked; state.focus = null; apply();
});
$("nodeset").addEventListener("change", e => {
  state.nodeset = e.target.value; state.focus = null; apply();
});
$("component").addEventListener("change", e => {
  state.component = e.target.value === "" ? null : Number(e.target.value);
  state.focus = null; apply();
});
$("chapter").addEventListener("change", e => {
  state.chapter = e.target.value || null; state.focus = null; apply();
});
$("search").addEventListener("change", e => {
  const v = e.target.value.trim();
  if (allNodes[v]) goTo(v);
});
$("reset").addEventListener("click", resetView);
$("focus-pill").addEventListener("click", clearFocus);

// ── Lean syntax highlighter ─────────────────────────────────────────────────

function esc(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

const _KW      = /\b(def|lemma|theorem|instance|class|structure|inductive|abbrev|noncomputable|private|protected|section|namespace|end|open|variable|where|do|let|have|show|suffices|calc|if|then|else|return|for|in|fun|match|with|by|sorry)\b/g;
const _TACTIC  = /\b(simp|ext|rfl|exact|intro|intros|apply|refine|constructor|use|rw|rewrite|rcases|rintro|obtain|push_neg|norm_num|ring|group|linarith|omega|decide|trivial|assumption|congr|tauto|aesop|cases|induction|revert|clear|next|all_goals|repeat|try|first|solve|fin_cases|positivity|gcongr|field_simp)\b/g;
const _TYPE    = /\b(Nat|Int|Bool|String|List|Array|Option|Type|Prop|Sort|True|False|And|Or|Not|Iff|Eq|Subgroup|Group|Ring|Field|Fintype|Finite)\b/g;
const _NUM     = /\b(\d+)\b/g;
const _STR     = /("(?:[^"\\]|\\.)*")/g;

function highlightLean(raw) {
  return raw.split('\n').map(line => {
    let commentAt = -1;
    let inStr = false;
    for (let i = 0; i < line.length - 1; i++) {
      if (line[i] === '"' && (i === 0 || line[i-1] !== '\\')) inStr = !inStr;
      if (!inStr && line[i] === '-' && line[i+1] === '-') { commentAt = i; break; }
    }
    const code    = commentAt >= 0 ? line.slice(0, commentAt) : line;
    const comment = commentAt >= 0 ? line.slice(commentAt)    : '';
    let h = esc(code);
    h = h.replace(_STR,    m => `<span class="hl-str">${m}</span>`);
    h = h.replace(_KW,     m => `<span class="hl-kw">${m}</span>`);
    h = h.replace(_TACTIC, m => `<span class="hl-tactic">${m}</span>`);
    h = h.replace(_TYPE,   m => `<span class="hl-type">${m}</span>`);
    h = h.replace(_NUM,    m => `<span class="hl-num">${m}</span>`);
    const commentHtml = comment ? `<span class="hl-comment">${esc(comment)}</span>` : '';
    return h + commentHtml;
  }).join('\n');
}

// ── LaTeX renderer ───────────────────────────────────────────────────────────

function processNonMath(s) {
  return esc(s)
    .replace(/\\emph\{([^}]*)\}/g,   '<em>$1</em>')
    .replace(/\\textbf\{([^}]*)\}/g, '<strong>$1</strong>')
    .replace(/\\textit\{([^}]*)\}/g, '<em>$1</em>')
    .replace(/\\text\{([^}]*)\}/g,   '$1');
}

function renderLatex(el, text) {
  if (!text || !text.trim()) {
    el.classList.add('empty'); el.textContent = '—'; return;
  }
  // Match every math delimiter style leanblueprint uses: $$…$$ and \[…\]
  // (display) and \(…\) and $…$ (inline). $$ and \[ \] come first so the
  // single-$ branch can't grab a $$ opener.
  const re = /(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$(?:[^$\\]|\\.)+?\$)/g;
  let html = '', last = 0, m;
  while ((m = re.exec(text)) !== null) {
    html += processNonMath(text.slice(last, m.index));
    const raw = m[0];
    let disp, math;
    if      (raw.startsWith('$$'))  { disp = true;  math = raw.slice(2, -2); }
    else if (raw.startsWith('\\[')) { disp = true;  math = raw.slice(2, -2); }
    else if (raw.startsWith('\\(')) { disp = false; math = raw.slice(2, -2); }
    else                            { disp = false; math = raw.slice(1, -1); }
    if (window.katex) {
      try {
        html += katex.renderToString(math, {
          displayMode: disp, throwOnError: false, macros: katexMacros,
        });
      }
      catch (_) { html += esc(raw); }
    } else {
      html += `<span style="color:#94a3b8">${esc(raw)}</span>`;
    }
    last = re.lastIndex;
  }
  html += processNonMath(text.slice(last));
  el.innerHTML = html;
}

// ── Sidebar rendering ────────────────────────────────────────────────────────

function charVal(v) {
  if (v === null || v === undefined) return '<span class="m-val m-inf">∞</span>';
  return `<span class="m-val">${v.toLocaleString()}</span>`;
}
function workVal(v) {
  if (v === null || v === undefined) return '<span class="m-val m-inf">∞</span>';
  if (v === 0) return '<span class="m-val m-done">0 ✓</span>';
  return `<span class="m-val m-work">${v.toLocaleString()}</span>`;
}
function charsPair(rel, cum) {
  const f = v => (v === null || v === undefined)
    ? '<span class="chars-inf">∞</span>'
    : `<span class="chars-val">${v}</span>`;
  return `<span class="chars-pair">ℓ<sub>local</sub>=${f(rel)} &nbsp; ℓ<sub>total</sub>=${f(cum)}</span>`;
}

function renderNode(id) {
  const n = allNodes[id];
  if (!n) return;

  $("sidebar-empty").style.display = "none";
  const content = $("sidebar-content");
  content.style.display = "flex";

  const statusBadge = n.proved
    ? '<span class="badge badge-proved">✓ leanok</span>'
    : (n.has_sorry
        ? '<span class="badge badge-sorry">sorry</span>'
        : '<span class="badge badge-unproved">unproved</span>');

  const mkChip = u => `<span class="dep-chip" onclick="goTo('${esc(u)}')">${esc(u)}</span>`;
  const depsHtml = n.uses.length
    ? n.uses.map(mkChip).join('')
    : '<span class="no-deps">none — axiom</span>';

  // full transitive upstream, with the direct deps split out
  const anc       = ancestorsOf(id);
  const directSet = new Set(n.uses);
  const indirect  = [...anc].filter(x => !directSet.has(x)).sort();
  const transHtml = indirect.length
    ? indirect.map(mkChip).join('')
    : '<span class="no-deps">none beyond the direct ones</span>';

  const focusLabel = state.focus === id ? 'Clear focus' : 'Focus dependency cone';
  const focusCall  = state.focus === id ? 'clearFocus()' : `setFocus('${esc(id)}')`;

  content.innerHTML = `
    <div class="card">
      <div class="node-badges">
        <span class="badge badge-type">${n.type.toUpperCase()}</span>${statusBadge}
      </div>
      <div class="node-title">${esc(n.title || n.id)}</div>
      <div class="node-id">${esc(n.id)}</div>
      ${n.chapter   ? `<div class="node-chapter">§ ${esc(n.chapter)}</div>` : ''}
      ${n.lean_name ? `<div class="lean-ref">Lean: <code>${esc(n.lean_name)}</code></div>` : ''}
      <button class="btn-focus" onclick="${focusCall}">⊙ ${focusLabel}</button>
    </div>

    <div class="card">
      <div class="card-title">Structure</div>
      <div class="degrees">
        <div class="degree">
          <span class="degree-val">${n.dep_count}</span>
          <span class="degree-label">direct deps</span>
        </div>
        <div class="degree">
          <span class="degree-val">${anc.size}</span>
          <span class="degree-label">total upstream</span>
        </div>
        <div class="degree">
          <span class="degree-val">${n.rdep_count}</span>
          <span class="degree-label">used by</span>
        </div>
      </div>
      <div class="deps-sub">direct dependencies</div>
      <div class="deps-list">${depsHtml}</div>
      <div class="deps-sub">indirect (transitive) dependencies</div>
      <div class="deps-list">${transHtml}</div>
    </div>

    <div class="card">
      <div class="card-title">Complexity</div>
      <div class="metrics-grid">
        <span></span>
        <span class="col-head">local</span>
        <span class="col-head">total</span>
        <span class="m-label">LaTeX ℓ</span>${charVal(n.proof_size_tex)}${charVal(n.proof_size_tex_total)}
        <span class="m-label">Lean ℓ</span>${charVal(n.proof_size_lean)}${charVal(n.proof_size_lean_total)}
        <span class="m-label">Effort</span>${workVal(n.effort_local)}${workVal(n.effort_total)}
      </div>
    </div>

    <div class="card">
      <div class="sec-hdr"><span class="card-title" style="margin:0">LaTeX statement</span></div>
      <div class="latex-rendered" id="latex-stmt"></div>
    </div>

    <div class="card">
      <div class="sec-hdr">
        <span class="card-title" style="margin:0">LaTeX proof</span>
        ${charsPair(n.proof_size_tex, n.proof_size_tex_total)}
      </div>
      <div class="latex-rendered" id="latex-proof"></div>
    </div>

    <div class="card">
      <div class="sec-hdr">
        <span class="card-title" style="margin:0">Lean code</span>
        ${charsPair(n.proof_size_lean, n.proof_size_lean_total)}
      </div>
      <pre class="code-block" id="lean-code"></pre>
    </div>
  `;

  renderLatex($('latex-stmt'),  n.statement);
  renderLatex($('latex-proof'), n.proof_tex ? n.proof_tex.trim() : '');

  const leanEl = $('lean-code');
  if (n.lean_source) {
    leanEl.innerHTML = highlightLean(n.lean_source);
  } else {
    leanEl.classList.add('empty');
    leanEl.textContent = 'declaration not found';
  }
}

// ── Cone highlighting on click ───────────────────────────────────────────────
// Selecting a node lights up its WHOLE transitive cone — every ancestor and
// descendant and the edges between them — while everything else fades back.

const baseNodeById = {};
for (const vn of graphData.nodes) baseNodeById[vn.id] = vn;

const EDGE_BASE = { color: "#cbd5e1", highlight: "#64748b" };

function highlightCone(id) {
  const cone = coneOf(id);   // {id} ∪ ancestors ∪ descendants
  nodesDS.update(nodesDS.getIds().map(nid =>
    cone.has(nid)
      ? baseNodeById[nid]                                   // full styling
      : { id: nid, color: { background: "#e5e7eb", border: "#d1d5db" },
          font: { color: "#cbd5e1" } }                      // faded
  ));
  edgesDS.update(edgesDS.get().map(e => {
    const on = cone.has(e.from) && cone.has(e.to);
    return { id: e.id,
             color: on ? { color: "#475569", highlight: "#334155" } : { color: "#edf0f4" },
             width: on ? 2.5 : 1 };
  }));
}

function clearHighlight() {
  nodesDS.update(nodesDS.getIds().map(nid => baseNodeById[nid]));
  edgesDS.update(edgesDS.get().map(e => ({ id: e.id, color: EDGE_BASE, width: 1 })));
}

network.on("click", params => {
  if (params.nodes.length) { renderNode(params.nodes[0]); highlightCone(params.nodes[0]); }
  else                     { clearHighlight(); }
});
network.on("doubleClick", params => { if (params.nodes.length) setFocus(params.nodes[0]); });

// ── Initial render ───────────────────────────────────────────────────────────

apply();
</script>
</body>
</html>
"""
