from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BlueprintDecl:
    """A mathematical declaration extracted from a leanblueprint LaTeX source."""
    id:        str
    type:      str
    title:     str
    chapter:   str
    statement: str
    uses:      list[str]
    proof_tex: str
    lean_name: Optional[str]
    is_proved: bool


@dataclass
class LeanDecl:
    """A Lean 4 declaration extracted from .lean source files."""
    name:       str
    source:     str
    proof_size: Optional[int]
    has_sorry:  bool


@dataclass
class GraphNode:
    """
    A node in the dependency graph, combining blueprint and Lean data.

    All metric fields are populated by :class:`DAG`; they are ``None``
    when the underlying data is absent (treated as ∞ in complexity sums).
    """
    # Identity
    id:        str
    type:      str          # lemma | theorem | definition | … | lean_aux
    title:     str
    chapter:   str
    statement: str
    uses:      list[str]    # ids of direct predecessors

    # Blueprint-derived fields (absent for lean_aux nodes)
    lean_name: Optional[str] = None
    proved:    bool          = False
    proof_tex: str           = ""

    # Lean-derived fields
    lean_source:     str           = ""
    proof_size_lean: Optional[int] = None
    has_sorry:       bool          = False

    # Graph metrics (set by DAG)
    dep_count:  int = 0   # number of direct dependencies
    rdep_count: int = 0   # number of nodes that depend on this one

    # Complexity metrics (set by DAG)
    proof_size_tex:        Optional[int] = None
    effort_local:          Optional[int] = None   # 0 if proved, tex size if draft, ∞ if absent
    proof_size_tex_total:  Optional[int] = None   # cumulative over ancestor subtree
    proof_size_lean_total: Optional[int] = None
    effort_total:          Optional[int] = None

    # ── Serialisation ──────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id":                    self.id,
            "type":                  self.type,
            "title":                 self.title,
            "chapter":               self.chapter,
            "statement":             self.statement,
            "uses":                  self.uses,
            "lean_name":             self.lean_name,
            "proved":                self.proved,
            "proof_tex":             self.proof_tex,
            "lean_source":           self.lean_source,
            "proof_size_lean":       self.proof_size_lean,
            "has_sorry":             self.has_sorry,
            "dep_count":             self.dep_count,
            "rdep_count":            self.rdep_count,
            "proof_size_tex":        self.proof_size_tex,
            "effort_local":          self.effort_local,
            "proof_size_tex_total":  self.proof_size_tex_total,
            "proof_size_lean_total": self.proof_size_lean_total,
            "effort_total":          self.effort_total,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GraphNode:
        return cls(
            id        = d["id"],
            type      = d["type"],
            title     = d["title"],
            chapter   = d["chapter"],
            statement = d["statement"],
            uses      = d["uses"],
            lean_name  = d.get("lean_name"),
            proved     = d.get("proved", False),
            proof_tex  = d.get("proof_tex", ""),
            lean_source     = d.get("lean_source", ""),
            proof_size_lean = d.get("proof_size_lean"),
            has_sorry       = d.get("has_sorry", False),
            dep_count  = d.get("dep_count", 0),
            rdep_count = d.get("rdep_count", 0),
            proof_size_tex        = d.get("proof_size_tex"),
            effort_local          = d.get("effort_local"),
            proof_size_tex_total  = d.get("proof_size_tex_total"),
            proof_size_lean_total = d.get("proof_size_lean_total"),
            effort_total          = d.get("effort_total"),
        )


@dataclass
class Edge:
    source: str
    target: str
