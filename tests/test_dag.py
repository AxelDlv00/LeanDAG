from leandag.models import BlueprintDecl, LeanDecl
from leandag.dag import DAG
from leandag.exporters import JSONExporter


def _decl(id, uses=None, lean_name=None, is_proved=False, proof_tex=""):
    return BlueprintDecl(
        id=id, type="lemma", title="", chapter="", statement="",
        uses=uses or [], proof_tex=proof_tex, lean_name=lean_name,
        is_proved=is_proved,
    )


def _lean(name, has_sorry=False):
    src = "lemma foo : True := trivial"
    return LeanDecl(name=name, source=src, proof_size=len(src), has_sorry=has_sorry)


# ── Structure tests ────────────────────────────────────────────────────────────

def test_node_and_edge_count():
    decls = [_decl("A"), _decl("B", uses=["A"]), _decl("C", uses=["A", "B"])]
    dag = DAG.from_sources(decls, {}, {})
    assert len(dag.nodes) == 3
    assert len(dag.edges) == 3


def test_axioms_and_leaves():
    decls = [_decl("A"), _decl("B", uses=["A"]), _decl("C", uses=["A", "B"])]
    dag = DAG.from_sources(decls, {}, {})
    assert {n.id for n in dag.axioms} == {"A"}
    assert {n.id for n in dag.leaves} == {"C"}


def test_degrees():
    decls = [_decl("A"), _decl("B", uses=["A"])]
    dag = DAG.from_sources(decls, {}, {})
    assert dag.node("A").dep_count  == 0
    assert dag.node("A").rdep_count == 1
    assert dag.node("B").dep_count  == 1
    assert dag.node("B").rdep_count == 0


def test_lean_aux_nodes_added():
    decls = [_decl("A")]
    lean  = {"helper": _lean("helper")}
    dag = DAG.from_sources(decls, {}, lean)
    assert "lean:helper" in {n.id for n in dag.nodes}
    assert dag.node("lean:helper").type == "lean_aux"


def test_lean_aux_not_duplicated_when_referenced():
    decls = [_decl("A", lean_name="FooLemma")]
    lean  = {"FooLemma": _lean("FooLemma")}
    dag = DAG.from_sources(decls, {}, lean)
    # FooLemma is referenced, so no lean_aux duplicate
    assert "lean:FooLemma" not in {n.id for n in dag.nodes}
    assert dag.node("A").lean_source != ""


# ── Metric tests ───────────────────────────────────────────────────────────────

def test_effort_local_zero_when_lean_proof_exists():
    lean  = {"FooLemma": _lean("FooLemma")}
    decls = [_decl("A", lean_name="FooLemma")]
    dag = DAG.from_sources(decls, {}, lean)
    assert dag.node("A").effort_local == 0


def test_effort_local_tex_chars_when_no_lean():
    decls = [_decl("A")]
    dag = DAG.from_sources(decls, {"A": "some proof text"}, {})
    assert dag.node("A").effort_local == len("some proof text")


def test_effort_local_none_when_no_proof():
    decls = [_decl("A")]
    dag = DAG.from_sources(decls, {}, {})
    assert dag.node("A").effort_local is None


def test_effort_total_cumulative():
    # A has proof_tex=10, B depends on A and has proof_tex=20
    decls = [_decl("A"), _decl("B", uses=["A"])]
    proofs = {"A": "a" * 10, "B": "b" * 20}
    dag = DAG.from_sources(decls, proofs, {})
    assert dag.node("A").effort_total == 10
    assert dag.node("B").effort_total == 30  # A(10) + B(20)


def test_effort_total_none_propagates():
    # C has no proof → effort_local=None → effort_total of dependents is None
    decls = [_decl("C"), _decl("D", uses=["C"])]
    dag = DAG.from_sources(decls, {}, {})
    assert dag.node("C").effort_total is None
    assert dag.node("D").effort_total is None


def test_proved_field():
    lean  = {"X": _lean("X")}
    decls = [_decl("A", lean_name="X", is_proved=True), _decl("B")]
    dag = DAG.from_sources(decls, {}, lean)
    assert dag.node("A").proved is True
    assert dag.node("B").proved is False


# ── Load/save roundtrip ────────────────────────────────────────────────────────

def test_json_roundtrip(tmp_path):
    decls = [_decl("A"), _decl("B", uses=["A"])]
    dag   = DAG.from_sources(decls, {"B": "proof"}, {})
    p = tmp_path / "dag.json"
    JSONExporter().export(dag, p)
    dag2 = DAG.load(p)
    assert len(dag2.nodes) == 2
    assert len(dag2.edges) == 1
    b = dag2.node("B")
    assert b.dep_count  == 1
    assert b.effort_local is not None


def test_ancestors():
    decls = [_decl("A"), _decl("B", uses=["A"]), _decl("C", uses=["B"])]
    dag = DAG.from_sources(decls, {}, {})
    assert dag.ancestors("C") == {"A", "B", "C"}
    assert dag.ancestors("A") == {"A"}
