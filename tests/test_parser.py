import textwrap
from pathlib import Path
from leandag.parser import BlueprintParser


_TEX = textwrap.dedent(r"""
    \chapter{First Chapter}

    \begin{lemma}[Foo lemma]
      \label{lem:foo}
      \lean{FooLemma}
      \uses{def:bar}
      Some statement about $x + y$.
      \leanok
    \end{lemma}
    \begin{proof}
      Obvious by definition.
    \end{proof}

    \begin{definition}
      \label{def:bar}
      A definition without a Lean name.
    \end{definition}

    \begin{theorem}[Main]
      \label{thm:main}
      \uses{lem:foo, def:bar}
      The main result.
    \end{theorem}
""")

_TEX_WITH_INPUT = textwrap.dedent(r"""
    \chapter{Root}
    \begin{lemma}
      \label{lem:root}
      Root lemma.
    \end{lemma}
    \input{child}
""")

_TEX_CHILD = textwrap.dedent(r"""
    \begin{definition}
      \label{def:child}
      Child definition.
    \end{definition}
""")


def _parser(tmp_path: Path, tex: str) -> BlueprintParser:
    p = tmp_path / "web.tex"
    p.write_text(tex)
    return BlueprintParser(p)


def test_finds_all_declarations(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    ids = {d.id for d in decls}
    assert ids == {"lem:foo", "def:bar", "thm:main"}


def test_lean_name(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    foo = next(d for d in decls if d.id == "lem:foo")
    assert foo.lean_name == "FooLemma"


def test_leanok(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    foo = next(d for d in decls if d.id == "lem:foo")
    assert foo.is_proved is True


def test_uses_parsed(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    thm = next(d for d in decls if d.id == "thm:main")
    assert set(thm.uses) == {"lem:foo", "def:bar"}


def test_chapter_assigned(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    assert all(d.chapter == "First Chapter" for d in decls)


def test_proof_body_extracted(tmp_path):
    decls, proofs = _parser(tmp_path, _TEX).parse()
    assert "lem:foo" in proofs
    assert "Obvious" in proofs["lem:foo"]


def test_proof_tex_on_decl(tmp_path):
    decls, _ = _parser(tmp_path, _TEX).parse()
    foo = next(d for d in decls if d.id == "lem:foo")
    assert "Obvious" in foo.proof_tex


def test_input_expansion(tmp_path):
    (tmp_path / "web.tex").write_text(_TEX_WITH_INPUT)
    (tmp_path / "child.tex").write_text(_TEX_CHILD)
    decls, _ = BlueprintParser(tmp_path / "web.tex").parse()
    ids = {d.id for d in decls}
    assert "lem:root"  in ids
    assert "def:child" in ids


def test_unlabeled_env_skipped(tmp_path):
    tex = r"\begin{lemma} No label here. \end{lemma}"
    decls, _ = _parser(tmp_path, tex).parse()
    assert decls == []
