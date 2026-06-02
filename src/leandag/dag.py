from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .models import BlueprintDecl, Edge, GraphNode, LeanDecl


class DAG:
    """
    Dependency graph of mathematical declarations.

    Nodes are :class:`GraphNode` instances.  Edges run from a predecessor to
    every node that depends on it (``\\uses{B}`` inside A creates edge B → A).

    Construction from sources::

        dag = DAG.from_sources(blueprint_decls, proofs, lean_decls)

    Reload from a saved file::

        dag = DAG.load(Path(".leandag/dag.json"))
    """

    def __init__(self, nodes: list[GraphNode], edges: list[Edge]) -> None:
        self._nodes  = nodes
        self._edges  = edges
        self._by_id: dict[str, GraphNode] = {n.id: n for n in nodes}

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def from_sources(
        cls,
        blueprint_decls: list[BlueprintDecl],
        proofs: dict[str, str],
        lean_decls: dict[str, LeanDecl],
    ) -> DAG:
        """
        Build a DAG from parsed blueprint declarations and Lean declarations.

        Lean declarations not referenced by any blueprint node are added as
        ``lean_aux`` nodes so formalization machinery counts toward complexity.
        """
        nodes = cls._build_nodes(blueprint_decls, proofs, lean_decls)
        cls._compute_degrees(nodes)
        cls._compute_metrics(nodes)
        edges = cls._build_edges(nodes)
        return cls(nodes, edges)

    @classmethod
    def load(cls, path: Path) -> DAG:
        """Reconstruct a :class:`DAG` from a serialised ``dag.json`` file."""
        data  = json.loads(path.read_text(encoding='utf-8'))
        nodes = [GraphNode.from_dict(d) for d in data["nodes"]]
        edges = [Edge(source=e["from"], target=e["to"]) for e in data["edges"]]
        return cls(nodes, edges)

    # ── Public interface ───────────────────────────────────────────────────

    @property
    def nodes(self) -> list[GraphNode]:
        return list(self._nodes)

    @property
    def edges(self) -> list[Edge]:
        return list(self._edges)

    @property
    def axioms(self) -> list[GraphNode]:
        """Nodes with no incoming edges (no blueprint dependencies)."""
        return [n for n in self._nodes if n.dep_count == 0]

    @property
    def leaves(self) -> list[GraphNode]:
        """Nodes that no other node depends on."""
        return [n for n in self._nodes if n.rdep_count == 0]

    def node(self, node_id: str) -> GraphNode:
        return self._by_id[node_id]

    def ancestors(self, node_id: str) -> set[str]:
        """Return ``{node_id}`` ∪ all transitive predecessors."""
        uses_of = {n.id: n.uses for n in self._nodes}
        visited: set[str] = {node_id}
        queue   = list(uses_of.get(node_id, []))
        while queue:
            curr = queue.pop()
            if curr not in visited:
                visited.add(curr)
                queue.extend(uses_of.get(curr, []))
        return visited

    # ── Assembly (private) ─────────────────────────────────────────────────

    @staticmethod
    def _build_nodes(
        blueprint_decls: list[BlueprintDecl],
        proofs: dict[str, str],
        lean_decls: dict[str, LeanDecl],
    ) -> list[GraphNode]:
        nodes: list[GraphNode] = []
        referenced_lean: set[str] = set()

        for decl in blueprint_decls:
            lean = lean_decls.get(decl.lean_name) if decl.lean_name else None
            if lean:
                referenced_lean.add(decl.lean_name)  # type: ignore[arg-type]

            proof_tex      = proofs.get(decl.id, '')
            proof_size_tex = DAG._count_tex_chars(proof_tex)

            nodes.append(GraphNode(
                id              = decl.id,
                type            = decl.type,
                title           = decl.title,
                chapter         = decl.chapter,
                statement       = decl.statement,
                uses            = decl.uses,
                lean_name       = decl.lean_name,
                proved          = decl.is_proved,
                proof_tex       = proof_tex,
                lean_source     = lean.source     if lean else "",
                proof_size_lean = lean.proof_size  if lean else None,
                has_sorry       = lean.has_sorry   if lean else False,
                proof_size_tex  = proof_size_tex,
            ))

        # Lean declarations not referenced in the blueprint: formalization
        # machinery that still contributes to overall complexity.
        for name, lean in sorted(lean_decls.items()):
            if name in referenced_lean:
                continue
            nodes.append(GraphNode(
                id              = f"lean:{name}",
                type            = "lean_aux",
                title           = name,
                chapter         = "",
                statement       = "",
                uses            = [],
                lean_name       = name,
                proved          = not lean.has_sorry,
                lean_source     = lean.source,
                proof_size_lean = lean.proof_size,
                has_sorry       = lean.has_sorry,
            ))

        return nodes

    @staticmethod
    def _compute_degrees(nodes: list[GraphNode]) -> None:
        ids:  set[str]      = {n.id for n in nodes}
        rdep: dict[str, int] = defaultdict(int)
        for n in nodes:
            for pred_id in n.uses:
                if pred_id in ids:
                    rdep[pred_id] += 1
        for n in nodes:
            n.dep_count  = len(n.uses)
            n.rdep_count = rdep[n.id]

    @staticmethod
    def _compute_metrics(nodes: list[GraphNode]) -> None:
        """
        Compute cumulative costs for every node.

        - ``effort_local``          = 0 if Lean proof complete, tex chars if draft, None if ∞
        - ``proof_size_tex_total``  = Σ proof_size_tex  over {v} ∪ ancestors(v)
        - ``proof_size_lean_total`` = Σ proof_size_lean over {v} ∪ ancestors(v)
        - ``effort_total``          = Σ effort_local    over {v} ∪ ancestors(v)

        Any sum containing a ``None`` term evaluates to ``None`` (representing ∞).
        """
        uses_of  = {n.id: n.uses            for n in nodes}
        rel_tex  = {n.id: n.proof_size_tex  for n in nodes}
        rel_lean = {n.id: n.proof_size_lean for n in nodes}

        def ancestors_incl(node_id: str) -> set[str]:
            visited: set[str] = {node_id}
            queue = list(uses_of.get(node_id, []))
            while queue:
                curr = queue.pop()
                if curr not in visited:
                    visited.add(curr)
                    queue.extend(uses_of.get(curr, []))
            return visited

        def sum_opt(ids: set[str], rel: dict[str, Optional[int]]) -> Optional[int]:
            total = 0
            for uid in ids:
                c = rel.get(uid)
                if c is None:
                    return None
                total += c
            return total

        def effort_local(n: GraphNode) -> Optional[int]:
            if n.proof_size_lean is not None:
                return 0
            if n.proof_size_tex is not None:
                return n.proof_size_tex
            return None

        rel_effort = {n.id: effort_local(n) for n in nodes}

        for n in nodes:
            anc = ancestors_incl(n.id)
            n.effort_local          = rel_effort[n.id]
            n.proof_size_tex_total  = sum_opt(anc, rel_tex)
            n.proof_size_lean_total = sum_opt(anc, rel_lean)
            n.effort_total          = sum_opt(anc, rel_effort)

    @staticmethod
    def _build_edges(nodes: list[GraphNode]) -> list[Edge]:
        ids: set[str] = {n.id for n in nodes}
        return [
            Edge(source=pred_id, target=n.id)
            for n in nodes
            for pred_id in n.uses
            if pred_id in ids
        ]

    @staticmethod
    def _count_tex_chars(proof: str) -> Optional[int]:
        """Character count of *proof* after stripping LaTeX % comments."""
        if not proof:
            return None
        out, i, n = [], 0, len(proof)
        while i < n:
            if proof[i] == '\\' and i + 1 < n:
                out.append(proof[i:i+2])
                i += 2
            elif proof[i] == '%':
                while i < n and proof[i] != '\n':
                    i += 1
            else:
                out.append(proof[i])
                i += 1
        stripped = ''.join(out).strip()
        return len(stripped) if stripped else None
