"""leandag — dependency graph and complexity metrics for Lean 4 + leanblueprint projects."""

__version__ = "0.1.0"

from .dag import DAG
from .models import BlueprintDecl, Edge, GraphNode, LeanDecl
from .parser import BlueprintParser
from .queries import Queries
from .scanner import LeanScanner

__all__ = [
    "BlueprintDecl", "LeanDecl", "GraphNode", "Edge",
    "DAG", "BlueprintParser", "LeanScanner", "Queries",
    "__version__",
]
