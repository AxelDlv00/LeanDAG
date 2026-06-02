from __future__ import annotations

from typing import Optional

from .dag import DAG
from .models import GraphNode


class Queries:
    """
    Filter and sort a DAG's nodes.

    All methods return a fresh list — the underlying DAG is never mutated.

    Typical usage::

        q = Queries(dag)
        q.ready_to_prove()                          # what can I work on now?
        q.filter(unproved_only=True, max_deps=3)    # simple targets
        Queries.sort_by_effort(nodes, top=10)       # cheapest first
    """

    def __init__(self, dag: DAG) -> None:
        self._dag = dag

    # ── Named filters ──────────────────────────────────────────────────────

    def axioms(self) -> list[GraphNode]:
        """Nodes with no dependencies (roots of the DAG)."""
        return self._dag.axioms

    def leaves(self) -> list[GraphNode]:
        """Nodes that nothing else depends on (frontier of the DAG)."""
        return self._dag.leaves

    def unproved(self) -> list[GraphNode]:
        """Blueprint nodes not yet marked ``leanok``."""
        return [n for n in self._dag.nodes if n.type != "lean_aux" and not n.proved]

    def with_sorry(self) -> list[GraphNode]:
        """Nodes whose Lean proof contains ``sorry``."""
        return [n for n in self._dag.nodes if n.has_sorry]

    def ready_to_prove(self) -> list[GraphNode]:
        """
        Blueprint nodes where every direct dependency is already proved
        but the node itself is not yet proved.
        """
        known  = {n.id for n in self._dag.nodes}
        proved = {n.id for n in self._dag.nodes if n.proved}
        return [
            n for n in self._dag.nodes
            if n.type != "lean_aux"
            and not n.proved
            and all(dep not in known or dep in proved for dep in n.uses)
        ]

    # ── Parametric filter ──────────────────────────────────────────────────

    def filter(
        self,
        *,
        min_deps:      Optional[int] = None,
        max_deps:      Optional[int] = None,
        min_effort:    Optional[int] = None,
        max_effort:    Optional[int] = None,
        chapter:       Optional[str] = None,
        type_name:     Optional[str] = None,
        unproved_only: bool = False,
        sorry_only:    bool = False,
    ) -> list[GraphNode]:
        """Return nodes matching all supplied criteria."""
        nodes = self._dag.nodes
        if unproved_only:
            nodes = [n for n in nodes if not n.proved and n.type != "lean_aux"]
        if sorry_only:
            nodes = [n for n in nodes if n.has_sorry]
        if min_deps is not None:
            nodes = [n for n in nodes if n.dep_count >= min_deps]
        if max_deps is not None:
            nodes = [n for n in nodes if n.dep_count <= max_deps]
        if min_effort is not None:
            nodes = [n for n in nodes
                     if n.effort_total is not None and n.effort_total >= min_effort]
        if max_effort is not None:
            nodes = [n for n in nodes
                     if n.effort_total is not None and n.effort_total <= max_effort]
        if chapter:
            nodes = [n for n in nodes if n.chapter == chapter]
        if type_name:
            nodes = [n for n in nodes if n.type == type_name]
        return nodes

    # ── Sort helpers ───────────────────────────────────────────────────────

    @staticmethod
    def sort_by_effort(
        nodes: list[GraphNode],
        *,
        top: Optional[int] = None,
        exclude_proved: bool = True,
    ) -> list[GraphNode]:
        """
        Sort ascending by ``effort_total`` (``None`` = ∞, goes last).

        By default proved nodes are excluded so the list surfaces genuine
        remaining work rather than trivially-done items.
        Pass ``exclude_proved=False`` to include them.
        """
        if exclude_proved:
            nodes = [n for n in nodes if not n.proved]
        result = sorted(nodes, key=lambda n: (n.effort_total is None, n.effort_total or 0))
        return result[:top] if top is not None else result

    @staticmethod
    def sort_by_deps(
        nodes: list[GraphNode],
        *,
        top: Optional[int] = None,
    ) -> list[GraphNode]:
        """Sort ascending by ``dep_count``."""
        result = sorted(nodes, key=lambda n: n.dep_count)
        return result[:top] if top is not None else result
