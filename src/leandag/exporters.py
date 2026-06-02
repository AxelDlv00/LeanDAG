from __future__ import annotations

import json
from pathlib import Path

from .dag import DAG
from .models import GraphNode


# ── Node colour palette (graph canvas) ────────────────────────────────────────

_TYPE_COLOR: dict[str, str] = {
    "definition":  "#bfdbfe",
    "lemma":       "#bbf7d0",
    "proposition": "#e9d5ff",
    "theorem":     "#fecaca",
    "corollary":   "#fde68a",
    "exercise":    "#fef9c3",
    "remark":      "#e2e8f0",
    "conjecture":  "#fed7aa",
    "lean_aux":    "#ffedd5",
}
_DEFAULT_COLOR   = "#e2e8f0"
_PROVED_BORDER   = "#16a34a"   # green  — fully formalised (leanok)
_UNPROVED_BORDER = "#dc2626"   # red    — not yet formalised
_AUX_BORDER      = "#c2410c"   # orange — lean_aux, no blueprint entry


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
            },
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


class HTMLExporter:
    """Write an interactive vis-network HTML visualisation of a DAG."""

    def export(self, dag: DAG, path: Path) -> None:
        nodes = dag.nodes
        edges = dag.edges

        vis_nodes   = [self._vis_node(n) for n in nodes]
        vis_edges   = [{"from": e.source, "to": e.target, "arrows": "to"} for e in edges]
        graph_json  = json.dumps({"nodes": vis_nodes, "edges": vis_edges},
                                 ensure_ascii=False, indent=2)
        detail_json = json.dumps(
            {n.id: n.to_dict() for n in nodes},
            ensure_ascii=False, indent=2,
        )
        legend_items = "".join(
            f'<span class="leg-chip" style="background:{c};color:#1e293b">'
            f'{t.replace("_", " ").title()}</span>'
            for t, c in _TYPE_COLOR.items()
        )

        html = _HTML_TEMPLATE.format(
            num_nodes    = len(nodes),
            num_edges    = len(edges),
            legend_items = legend_items,
            graph_json   = graph_json,
            detail_json  = detail_json,
        )
        path.write_text(html, encoding="utf-8")

    @staticmethod
    def _vis_node(n: GraphNode) -> dict:
        is_aux  = n.type == "lean_aux"
        color   = _TYPE_COLOR.get(n.type, _DEFAULT_COLOR)
        if is_aux:
            border = _AUX_BORDER
        elif n.proved:
            border = _PROVED_BORDER
        else:
            border = _UNPROVED_BORDER

        short_id = n.id.split(":")[-1]
        label    = ("? " if is_aux else n.type[0].upper() + ". ") + short_id
        if n.proved:
            label += " ✓"

        node_vis: dict = {
            "id":    n.id,
            "label": label,
            "color": {"background": color, "border": border},
            "borderWidth": 2,
            "font":  {"size": 12,
                      "face": "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                      "color": "#1e293b"},
            "margin": {"top": 8, "bottom": 8, "left": 12, "right": 12},
            "shapeProperties": {"borderRadius": 6},
        }
        if is_aux:
            node_vis["shapeProperties"]["borderDashes"] = [4, 4]
        return node_vis


# ── HTML template ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Blueprint dependency graph</title>
<link rel="stylesheet" href="https://unpkg.com/katex@0.16.9/dist/katex.min.css">
<script src="https://unpkg.com/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
:root {{
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
}}

html {{ margin:0; padding:0; height:100%; overflow:hidden; }}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ font-family:var(--sans); display:flex; flex-direction:column;
        height:100%; background:#f8fafc; color:var(--text); }}

/* ── Toolbar ─────────────────────────────────────────────────── */
#toolbar {{
  background:var(--toolbar-bg); height:44px; padding:0 16px;
  display:flex; align-items:center; gap:14px; flex-shrink:0;
  border-bottom:1px solid #263045;
}}
.brand {{ font-size:13px; font-weight:700; color:#f1f5f9; letter-spacing:.03em; }}
.stat  {{ font-size:12px; color:#64748b; }}
.legend {{ display:flex; gap:5px; flex-wrap:wrap; }}
.leg-chip {{
  display:inline-block; padding:2px 8px; border-radius:10px;
  font-size:10px; font-weight:600; border:1px solid rgba(0,0,0,.15);
}}
.hint {{ margin-left:auto; font-size:11px; color:#334155; }}

/* ── Main layout ─────────────────────────────────────────────── */
#main  {{ display:flex; flex:1; overflow:hidden; min-height:0; }}
#graph {{ flex:1; min-height:0; background:#f8fafc; }}
#graph canvas {{ display:block; }}

/* ── Sidebar ─────────────────────────────────────────────────── */
#sidebar {{
  width:340px; flex-shrink:0;
  background:var(--sidebar-bg);
  border-left:1px solid #1e293b;
  display:flex; flex-direction:column; overflow:hidden;
}}
#sidebar-empty {{
  flex:1; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:10px;
}}
#sidebar-empty svg {{ opacity:.2; }}
#sidebar-empty p {{ font-size:13px; color:#334155; }}
#sidebar-content {{
  flex:1; overflow-y:auto; padding:10px;
  display:flex; flex-direction:column; gap:8px;
}}
#sidebar-content::-webkit-scrollbar {{ width:4px; }}
#sidebar-content::-webkit-scrollbar-thumb {{ background:#1e3a5f; border-radius:2px; }}

/* ── Cards ───────────────────────────────────────────────────── */
.card {{
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--radius); padding:12px;
}}
.card-title {{
  font-size:10px; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; color:var(--muted); margin-bottom:10px;
}}

/* ── Header card ─────────────────────────────────────────────── */
.node-badges {{ display:flex; gap:5px; flex-wrap:wrap; margin-bottom:8px; }}
.badge {{
  display:inline-block; padding:2px 8px; border-radius:10px;
  font-size:10px; font-weight:700; letter-spacing:.04em;
}}
.badge-type    {{ background:#172554; color:#93c5fd; border:1px solid #1e3a8a44; }}
.badge-proved  {{ background:var(--green-bg);  color:var(--green);  border:1px solid rgba(74,222,128,.25); }}
.badge-sorry   {{ background:var(--orange-bg); color:var(--orange); border:1px solid rgba(251,146,60,.25); }}
.badge-unproved{{ background:var(--red-bg);    color:var(--red);    border:1px solid rgba(248,113,113,.25); }}
.node-title   {{ font-size:15px; font-weight:600; color:#f1f5f9; line-height:1.35; margin-bottom:5px; }}
.node-id      {{ font-family:var(--mono); font-size:11px; color:#475569; }}
.node-chapter {{ font-size:11px; color:#334155; margin-top:3px; }}
.lean-ref     {{ font-size:11px; color:var(--muted); margin-top:6px; }}
.lean-ref code{{ font-family:var(--mono); color:var(--accent); }}

/* ── Structure card ──────────────────────────────────────────── */
.degrees {{ display:flex; gap:20px; margin-bottom:10px; }}
.degree  {{ display:flex; flex-direction:column; align-items:center; gap:2px; }}
.degree-val   {{ font-size:22px; font-weight:700; color:#f1f5f9; line-height:1; }}
.degree-label {{ font-size:10px; color:var(--muted); text-align:center; }}
.deps-list  {{ display:flex; flex-wrap:wrap; gap:4px; }}
.dep-chip {{
  font-family:var(--mono); font-size:10px; padding:3px 7px;
  background:#0f1f3d; border:1px solid #1e3a5f;
  border-radius:4px; color:var(--accent); cursor:pointer; transition:background .15s;
}}
.dep-chip:hover {{ background:#172554; }}
.no-deps {{ font-size:12px; color:var(--muted); font-style:italic; }}

/* ── Metrics card ────────────────────────────────────────────── */
.metrics-grid {{
  display:grid; grid-template-columns:auto 1fr 1fr;
  gap:5px 10px; align-items:center;
}}
.col-head {{ font-size:10px; color:#334155; text-align:right; font-weight:600; }}
.m-label  {{ font-size:11px; color:var(--muted); }}
.m-val    {{ font-family:var(--mono); font-size:12px; color:#94a3b8; text-align:right; }}
.m-done   {{ color:var(--green); font-weight:700; }}
.m-inf    {{ color:var(--red);   font-weight:700; }}
.m-work   {{ color:var(--orange); }}

/* ── Section header ──────────────────────────────────────────── */
.sec-hdr {{
  display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px;
}}
.chars-pair {{ font-family:var(--mono); font-size:10px; color:#334155; }}
.chars-inf  {{ color:var(--red); }}
.chars-val  {{ color:#475569; }}

/* ── LaTeX rendered block ────────────────────────────────────── */
.latex-rendered {{
  font-family:var(--sans); font-size:13px; line-height:1.7;
  color:#94a3b8; overflow-x:auto; min-height:1.5em;
}}
.latex-rendered .katex-display {{ margin:6px 0; overflow-x:auto; }}
.latex-rendered em {{ font-style:italic; color:#cbd5e1; }}
.latex-rendered strong {{ font-weight:600; color:#cbd5e1; }}
.latex-rendered.empty {{ color:#1e3a5f; font-style:italic; }}

/* ── Lean code block ─────────────────────────────────────────── */
.code-block {{
  font-family:var(--mono); font-size:11px; line-height:1.6;
  background:var(--code-bg); color:#abb2bf;
  border:1px solid #1a2744; border-radius:5px;
  padding:10px 12px; white-space:pre; overflow:auto;
  max-height:220px;
}}
.code-block::-webkit-scrollbar {{ width:4px; height:4px; }}
.code-block::-webkit-scrollbar-thumb {{ background:#1e3a5f; border-radius:2px; }}
.code-block.empty {{ color:#1e3a5f; font-style:italic; white-space:normal; }}

/* ── Lean syntax colours (One Dark palette) ──────────────────── */
.hl-kw      {{ color:#c678dd; }}
.hl-tactic  {{ color:#61afef; }}
.hl-type    {{ color:#e5c07b; }}
.hl-comment {{ color:#5c6370; font-style:italic; }}
.hl-str     {{ color:#98c379; }}
.hl-num     {{ color:#d19a66; }}
</style>
</head>
<body>
<div id="toolbar">
  <span class="brand">Blueprint DAG</span>
  <span class="stat">{num_nodes} nodes &middot; {num_edges} edges</span>
  <span class="legend">{legend_items}</span>
  <span class="hint">click a node to inspect</span>
</div>
<div id="main">
  <div id="graph"></div>
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
const graphData = {graph_json};
const allNodes  = {detail_json};

// ── Graph ──────────────────────────────────────────────────────────────────

const network = new vis.Network(
  document.getElementById("graph"),
  {{
    nodes: new vis.DataSet(graphData.nodes),
    edges: new vis.DataSet(graphData.edges),
  }},
  {{
    layout: {{
      hierarchical: {{
        direction: "UD", sortMethod: "directed",
        levelSeparation: 100, nodeSpacing: 150,
      }},
    }},
    physics: {{ enabled: false }},
    edges: {{
      smooth: {{ type: "cubicBezier", forceDirection: "vertical" }},
      color: {{ color: "#94a3b8", highlight: "#475569" }},
      arrows: {{ to: {{ scaleFactor: .6 }} }},
      width: 1.5,
    }},
    nodes: {{ shape: "box" }},
    interaction: {{ hover: true, tooltipDelay: 150, zoomView: false }},
  }}
);

// ── Navigation: swipe = pan · Ctrl+scroll / pinch = zoom ──────────────────
let ZOOM_MIN = 0.05;
const ZOOM_MAX = 3.0;
let graphBounds = null;

setTimeout(() => {{
  network.fit({{ animation: false }});
  ZOOM_MIN = network.getScale();
  const pts = Object.values(network.getPositions());
  if (pts.length) {{
    const pad = 200;
    graphBounds = {{
      left:   Math.min(...pts.map(p => p.x)) - pad,
      right:  Math.max(...pts.map(p => p.x)) + pad,
      top:    Math.min(...pts.map(p => p.y)) - pad,
      bottom: Math.max(...pts.map(p => p.y)) + pad,
    }};
  }}
}}, 0);

document.getElementById("graph").addEventListener("wheel", e => {{
  e.preventDefault();
  e.stopPropagation();
  const pos = network.getViewPosition();
  const sc  = network.getScale();
  if (e.ctrlKey) {{
    const f        = e.deltaY > 0 ? 0.9 : 1 / 0.9;
    const newScale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, sc * f));
    network.moveTo({{ scale: newScale, animation: false }});
  }} else {{
    let nx = pos.x + e.deltaX / sc;
    let ny = pos.y + e.deltaY / sc;
    if (graphBounds) {{
      nx = Math.max(graphBounds.left,  Math.min(graphBounds.right,  nx));
      ny = Math.max(graphBounds.top,   Math.min(graphBounds.bottom, ny));
    }}
    network.moveTo({{ position: {{ x: nx, y: ny }}, animation: false }});
  }}
}}, {{ capture: true, passive: false }});

// ── Lean syntax highlighter ────────────────────────────────────────────────

function esc(s) {{
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

const _KW      = /\b(def|lemma|theorem|instance|class|structure|inductive|abbrev|noncomputable|private|protected|section|namespace|end|open|variable|where|do|let|have|show|suffices|calc|if|then|else|return|for|in|fun|match|with|by|sorry)\b/g;
const _TACTIC  = /\b(simp|ext|rfl|exact|intro|intros|apply|refine|constructor|use|rw|rewrite|rcases|rintro|obtain|push_neg|norm_num|ring|group|linarith|omega|decide|trivial|assumption|congr|tauto|aesop|cases|induction|revert|clear|next|all_goals|repeat|try|first|solve|fin_cases|positivity|gcongr|field_simp)\b/g;
const _TYPE    = /\b(Nat|Int|Bool|String|List|Array|Option|Type|Prop|Sort|True|False|And|Or|Not|Iff|Eq|Subgroup|Group|Ring|Field|Fintype|Finite)\b/g;
const _NUM     = /\b(\d+)\b/g;
const _STR     = /("(?:[^"\\]|\\.)*")/g;

function highlightLean(raw) {{
  return raw.split('\n').map(line => {{
    let commentAt = -1;
    let inStr = false;
    for (let i = 0; i < line.length - 1; i++) {{
      if (line[i] === '"' && (i === 0 || line[i-1] !== '\\')) inStr = !inStr;
      if (!inStr && line[i] === '-' && line[i+1] === '-') {{ commentAt = i; break; }}
    }}
    const code    = commentAt >= 0 ? line.slice(0, commentAt) : line;
    const comment = commentAt >= 0 ? line.slice(commentAt)    : '';
    let h = esc(code);
    h = h.replace(_STR,    m => `<span class="hl-str">${{m}}</span>`);
    h = h.replace(_KW,     m => `<span class="hl-kw">${{m}}</span>`);
    h = h.replace(_TACTIC, m => `<span class="hl-tactic">${{m}}</span>`);
    h = h.replace(_TYPE,   m => `<span class="hl-type">${{m}}</span>`);
    h = h.replace(_NUM,    m => `<span class="hl-num">${{m}}</span>`);
    const commentHtml = comment ? `<span class="hl-comment">${{esc(comment)}}</span>` : '';
    return h + commentHtml;
  }}).join('\n');
}}

// ── LaTeX renderer ─────────────────────────────────────────────────────────

function processNonMath(s) {{
  return esc(s)
    .replace(/\\emph\{{([^}}]*)\}}/g,   '<em>$1</em>')
    .replace(/\\textbf\{{([^}}]*)\}}/g, '<strong>$1</strong>')
    .replace(/\\textit\{{([^}}]*)\}}/g, '<em>$1</em>')
    .replace(/\\text\{{([^}}]*)\}}/g,   '$1');
}}

function renderLatex(el, text) {{
  if (!text || !text.trim()) {{
    el.classList.add('empty'); el.textContent = '—'; return;
  }}
  const re = /(\\\[[\s\S]*?\\\]|\$(?:[^$\\]|\\.)+?\$)/g;
  let html = '', last = 0, m;
  while ((m = re.exec(text)) !== null) {{
    html += processNonMath(text.slice(last, m.index));
    const raw  = m[0];
    const disp = raw.startsWith('\\[');
    const math = disp ? raw.slice(2, -2) : raw.slice(1, -1);
    if (window.katex) {{
      try {{ html += katex.renderToString(math, {{ displayMode: disp, throwOnError: false }}); }}
      catch (_) {{ html += esc(raw); }}
    }} else {{
      html += `<span style="color:#94a3b8">${{esc(raw)}}</span>`;
    }}
    last = re.lastIndex;
  }}
  html += processNonMath(text.slice(last));
  el.innerHTML = html;
}}

// ── Sidebar rendering ──────────────────────────────────────────────────────

function charVal(v) {{
  if (v === null || v === undefined) return '<span class="m-val m-inf">∞</span>';
  return `<span class="m-val">${{v.toLocaleString()}}</span>`;
}}
function workVal(v) {{
  if (v === null || v === undefined) return '<span class="m-val m-inf">∞</span>';
  if (v === 0) return '<span class="m-val m-done">0 ✓</span>';
  return `<span class="m-val m-work">${{v.toLocaleString()}}</span>`;
}}
function charsPair(rel, cum) {{
  const f = v => (v === null || v === undefined)
    ? '<span class="chars-inf">∞</span>'
    : `<span class="chars-val">${{v}}</span>`;
  return `<span class="chars-pair">ℓ<sub>local</sub>=${{f(rel)}} &nbsp; ℓ<sub>total</sub>=${{f(cum)}}</span>`;
}}

function renderNode(id) {{
  const n = allNodes[id];
  if (!n) return;

  document.getElementById("sidebar-empty").style.display = "none";
  const content = document.getElementById("sidebar-content");
  content.style.display = "flex";

  const statusBadge = n.proved
    ? '<span class="badge badge-proved">✓ leanok</span>'
    : (n.has_sorry
        ? '<span class="badge badge-sorry">sorry</span>'
        : '<span class="badge badge-unproved">unproved</span>');

  const depsHtml = n.uses.length
    ? n.uses.map(u => `<span class="dep-chip" onclick="jumpTo('${{esc(u)}}')">${{esc(u)}}</span>`).join('')
    : '<span class="no-deps">none — axiom</span>';

  content.innerHTML = `
    <div class="card">
      <div class="node-badges">
        <span class="badge badge-type">${{n.type.toUpperCase()}}</span>${{statusBadge}}
      </div>
      <div class="node-title">${{esc(n.title || n.id)}}</div>
      <div class="node-id">${{esc(n.id)}}</div>
      ${{n.chapter   ? `<div class="node-chapter">§ ${{esc(n.chapter)}}</div>` : ''}}
      ${{n.lean_name ? `<div class="lean-ref">Lean: <code>${{esc(n.lean_name)}}</code></div>` : ''}}
    </div>

    <div class="card">
      <div class="card-title">Structure</div>
      <div class="degrees">
        <div class="degree">
          <span class="degree-val">${{n.dep_count}}</span>
          <span class="degree-label">depends on</span>
        </div>
        <div class="degree">
          <span class="degree-val">${{n.rdep_count}}</span>
          <span class="degree-label">used by</span>
        </div>
      </div>
      <div class="deps-list">${{depsHtml}}</div>
    </div>

    <div class="card">
      <div class="card-title">Complexity</div>
      <div class="metrics-grid">
        <span></span>
        <span class="col-head">local</span>
        <span class="col-head">total</span>
        <span class="m-label">LaTeX ℓ</span>${{charVal(n.proof_size_tex)}}${{charVal(n.proof_size_tex_total)}}
        <span class="m-label">Lean ℓ</span>${{charVal(n.proof_size_lean)}}${{charVal(n.proof_size_lean_total)}}
        <span class="m-label">Effort</span>${{workVal(n.effort_local)}}${{workVal(n.effort_total)}}
      </div>
    </div>

    <div class="card">
      <div class="sec-hdr"><span class="card-title" style="margin:0">LaTeX statement</span></div>
      <div class="latex-rendered" id="latex-stmt"></div>
    </div>

    <div class="card">
      <div class="sec-hdr">
        <span class="card-title" style="margin:0">LaTeX proof</span>
        ${{charsPair(n.proof_size_tex, n.proof_size_tex_total)}}
      </div>
      <div class="latex-rendered" id="latex-proof"></div>
    </div>

    <div class="card">
      <div class="sec-hdr">
        <span class="card-title" style="margin:0">Lean code</span>
        ${{charsPair(n.proof_size_lean, n.proof_size_lean_total)}}
      </div>
      <pre class="code-block" id="lean-code"></pre>
    </div>
  `;

  renderLatex(document.getElementById('latex-stmt'),  n.statement);
  renderLatex(document.getElementById('latex-proof'), n.proof_tex ? n.proof_tex.trim() : '');

  const leanEl = document.getElementById('lean-code');
  if (n.lean_source) {{
    leanEl.innerHTML = highlightLean(n.lean_source);
  }} else {{
    leanEl.classList.add('empty');
    leanEl.textContent = 'declaration not found';
  }}
}}

function jumpTo(id) {{
  if (!allNodes[id]) return;
  network.selectNodes([id]);
  network.focus(id, {{ scale: 1.2, animation: {{ duration: 400, easingFunction: 'easeInOutQuad' }} }});
  renderNode(id);
}}

network.on("click", params => {{
  if (params.nodes.length) renderNode(params.nodes[0]);
}});
</script>
</body>
</html>
"""
