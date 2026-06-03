from leandag.models import BlueprintDecl, LeanDecl
from leandag.dag import DAG
from leandag.queries import Queries


def _dag():
    decls = [
        BlueprintDecl("A", "lemma",   "", "Ch1", "", [],         "", [],  True),   # proved
        BlueprintDecl("B", "theorem", "", "Ch1", "", ["A"],      "", [],  False),  # unproved, deps=[A]
        BlueprintDecl("C", "lemma",   "", "Ch2", "", ["A", "B"], "", [],  False),  # unproved, deps=[A,B]
    ]
    lean = {"SorryFn": LeanDecl("SorryFn", "sorry", None, True)}
    return DAG.from_sources(decls, {"B": "x" * 50}, lean)


def test_needs_lean_statement():
    # A has a resolved lean decl, B has none, C is lean_aux (skipped)
    from leandag.models import BlueprintDecl
    decls = [
        BlueprintDecl("A", "lemma", "", "", "", [], "", ["L"], False),
        BlueprintDecl("B", "lemma", "", "", "", [], "", [], False),
    ]
    lean = {"L": LeanDecl("L", "lemma L:True:=trivial", 21, False)}
    q = Queries(DAG.from_sources(decls, {}, lean))
    ids = {n.id for n in q.needs_lean_statement()}
    assert ids == {"B"}                       # A resolved; lean_aux excluded


def test_sort_by_impact():
    from leandag.models import BlueprintDecl
    decls = [
        BlueprintDecl("A", "lemma", "", "", "", [],        "", [], False),
        BlueprintDecl("B", "lemma", "", "", "", ["A"],     "", [], False),
        BlueprintDecl("C", "lemma", "", "", "", ["B"],     "", [], False),
    ]
    dag = DAG.from_sources(decls, {}, {})
    ordered = [n.id for n in Queries.sort_by_impact(dag.nodes)]
    assert ordered[0] == "A"                  # A unblocks the most (B, C)


def test_axioms():
    q = Queries(_dag())
    # A has no deps and is proved; lean:SorryFn has no deps
    ids = {n.id for n in q.axioms()}
    assert "A" in ids


def test_leaves():
    q = Queries(_dag())
    ids = {n.id for n in q.leaves()}
    assert "C" in ids


def test_unproved():
    q = Queries(_dag())
    ids = {n.id for n in q.unproved()}
    assert "B" in ids
    assert "C" in ids
    assert "A" not in ids
    # lean_aux nodes must not appear
    assert all(n.type != "lean_aux" for n in q.unproved())


def test_with_sorry():
    q = Queries(_dag())
    ids = {n.id for n in q.with_sorry()}
    assert "lean:SorryFn" in ids


def test_ready_to_prove():
    q = Queries(_dag())
    ids = {n.id for n in q.ready_to_prove()}
    # B: deps=[A], A is proved → ready
    assert "B" in ids
    # C: deps=[A,B], B not proved → not ready
    assert "C" not in ids
    # A: already proved → not in result
    assert "A" not in ids


def test_filter_unproved_only():
    q = Queries(_dag())
    nodes = q.filter(unproved_only=True)
    assert all(not n.proved for n in nodes)
    assert all(n.type != "lean_aux" for n in nodes)


def test_filter_chapter():
    q = Queries(_dag())
    nodes = q.filter(chapter="Ch2")
    assert all(n.chapter == "Ch2" for n in nodes)
    assert len(nodes) == 1 and nodes[0].id == "C"


def test_filter_type():
    q = Queries(_dag())
    nodes = q.filter(type_name="theorem")
    assert all(n.type == "theorem" for n in nodes)


def test_filter_max_deps():
    q = Queries(_dag())
    nodes = q.filter(max_deps=1)
    for n in nodes:
        assert n.dep_count <= 1


def test_filter_min_deps():
    q = Queries(_dag())
    nodes = q.filter(min_deps=2)
    for n in nodes:
        assert n.dep_count >= 2


def test_filter_min_effort():
    dag = _dag()
    q = Queries(dag)
    # B has proof_tex so effort_total = 50; A is proved so effort_total = 0
    nodes = q.filter(min_effort=1)
    for n in nodes:
        assert n.effort_total is not None and n.effort_total >= 1


def test_filter_max_effort():
    q = Queries(_dag())
    nodes = q.filter(max_effort=100)
    for n in nodes:
        assert n.effort_total is not None and n.effort_total <= 100


def test_filter_sorry_only():
    q = Queries(_dag())
    nodes = q.filter(sorry_only=True)
    assert all(n.has_sorry for n in nodes)


def test_sort_by_effort_excludes_proved_by_default():
    nodes = _dag().nodes
    result = Queries.sort_by_effort(nodes)
    assert all(not n.proved for n in result)


def test_sort_by_effort_include_proved():
    nodes = _dag().nodes
    result = Queries.sort_by_effort(nodes, exclude_proved=False)
    proved = [n for n in result if n.proved]
    assert len(proved) > 0


def test_sort_by_effort_none_last():
    nodes = _dag().nodes
    sorted_nodes = Queries.sort_by_effort(nodes, exclude_proved=False)
    seen_none = False
    for n in sorted_nodes:
        if n.effort_total is None:
            seen_none = True
        elif seen_none:
            assert False, "finite effort_total appeared after None"


def test_sort_by_effort_top():
    nodes = _dag().nodes
    result = Queries.sort_by_effort(nodes, top=2)
    assert len(result) <= 2


def test_sort_by_deps():
    dag = _dag()
    nodes = dag.nodes
    sorted_nodes = Queries.sort_by_deps(nodes)
    counts = [n.dep_count for n in sorted_nodes]
    assert counts == sorted(counts)
