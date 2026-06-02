from leandag.models import GraphNode, Edge, BlueprintDecl, LeanDecl


def test_graphnode_roundtrip():
    n = GraphNode(
        id="lem:foo", type="lemma", title="Foo", chapter="Ch 1",
        statement="$x + y = z$", uses=["def:bar"],
        lean_name="FooLemma", proved=False,
        proof_size_tex=100, effort_local=100, effort_total=300,
        dep_count=1, rdep_count=2,
    )
    n2 = GraphNode.from_dict(n.to_dict())
    assert n2.id          == "lem:foo"
    assert n2.type        == "lemma"
    assert n2.uses        == ["def:bar"]
    assert n2.effort_local  == 100
    assert n2.effort_total  == 300
    assert n2.dep_count     == 1
    assert n2.rdep_count    == 2
    assert n2.proved        is False


def test_graphnode_from_dict_defaults():
    n = GraphNode.from_dict({
        "id": "x", "type": "definition", "title": "", "chapter": "",
        "statement": "", "uses": [],
    })
    assert n.proved         is False
    assert n.has_sorry      is False
    assert n.dep_count      == 0
    assert n.rdep_count     == 0
    assert n.effort_total   is None
    assert n.proof_size_tex is None


def test_graphnode_none_effort_survives_roundtrip():
    n = GraphNode(id="a", type="theorem", title="", chapter="", statement="", uses=[])
    d = n.to_dict()
    assert d["effort_total"] is None
    n2 = GraphNode.from_dict(d)
    assert n2.effort_total is None


def test_lean_decl():
    ld = LeanDecl(name="foo", source="def foo := 1", proof_size=12, has_sorry=False)
    assert ld.proof_size == 12
    assert ld.has_sorry  is False


def test_blueprint_decl():
    bd = BlueprintDecl(
        id="lem:foo", type="lemma", title="Foo", chapter="Ch1",
        statement="S", uses=["a", "b"], proof_tex="P",
        lean_name="FooLemma", is_proved=True,
    )
    assert bd.uses      == ["a", "b"]
    assert bd.is_proved is True
