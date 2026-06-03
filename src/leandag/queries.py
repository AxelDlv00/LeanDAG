from __future__ import annotations

from typing import Optional

from .dag import DAG
from .models import GraphNode


def is_done(n: GraphNode) -> bool:
    """A node needs no further formalisation work.

    True when it is marked ``leanok`` *or* a sorry-free Lean proof/declaration
    already exists for it (``effort_local == 0``). The second case matters: a
    node can be fully formalised in Lean while ``\\leanok`` was never added to
    the blueprint, and such a node must not be reported as "ready to do".
    """
    return n.proved or n.effort_local == 0


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
        Blueprint nodes that still need work and whose every direct dependency
        is already done — i.e. actionable right now. "Done" means proved or
        already formalised in Lean (see :func:`is_done`), so nodes that are
        ``0 ✓`` are neither listed here nor block their dependents.
        """
        known = {n.id for n in self._dag.nodes}
        done  = {n.id for n in self._dag.nodes if is_done(n)}
        return [
            n for n in self._dag.nodes
            if n.type != "lean_aux"
            and not is_done(n)
            and all(dep not in known or dep in done for dep in n.uses)
        ]

    def needs_leanok(self) -> list[GraphNode]:
        """Nodes with a complete Lean proof (``effort_local == 0``) that are not
        yet flagged ``\\leanok`` — a cheap win: just mark them in the blueprint."""
        return [
            n for n in self._dag.nodes
            if n.type != "lean_aux" and not n.proved and n.effort_local == 0
        ]

    def needs_lean_statement(self) -> list[GraphNode]:
        """Blueprint nodes with no ``\\lean{}`` link at all.

        These are the pure formalisation gaps — a statement exists in the
        blueprint but no Lean declaration is named for it. (A ``\\lean{}`` that
        is written but points at a missing name shows up in the DAG's
        ``unmatched_lean`` list instead, not here.)
        """
        return [
            n for n in self._dag.nodes
            if n.type != "lean_aux" and not n.lean_name
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

    @staticmethod
    def sort_by_impact(
        nodes: list[GraphNode],
        *,
        top: Optional[int] = None,
    ) -> list[GraphNode]:
        """Sort descending by ``descendant_count`` — most-unblocking first."""
        result = sorted(nodes, key=lambda n: n.descendant_count, reverse=True)
        return result[:top] if top is not None else result
