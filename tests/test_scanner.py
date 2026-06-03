from pathlib import Path
from leandag.scanner import LeanScanner


_LEAN_BASIC = """\
namespace Foo

theorem my_theorem (n : Nat) : n + 0 = n := by
  simp

def helper : Nat := 42

end Foo
"""

_LEAN_WITH_SORRY = """\
lemma broken : False := by
  sorry
"""

_LEAN_MULTIMOD = """\
-- Module header

def alpha : Nat := 1

lemma beta : alpha = 1 := by rfl

noncomputable def gamma : Nat := alpha + 1
"""


_LEAN_NESTED = """\
namespace AlgebraicGeometry.Cohomology

def aux : Nat := 0

end AlgebraicGeometry.Cohomology

namespace AlgebraicGeometry

namespace Scheme

noncomputable def toAbSheaf : Nat := 1

end Scheme

end AlgebraicGeometry
"""


def test_finds_declarations():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    # declarations are keyed by their fully-qualified (namespaced) name
    assert "Foo.my_theorem" in result
    assert "Foo.helper" in result


_LEAN_ATTR = """\
namespace Bar

@[simp] lemma decorated (n : Nat) : n = n := rfl

@[reducible]
def two : Nat := 2

end Bar
"""


def test_attribute_prefixed_declarations():
    # `@[attr] lemma …` (and an attribute on its own line) must still be found
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_ATTR)
    assert "Bar.decorated" in result
    assert "Bar.two" in result


def test_namespace_fully_qualified():
    # nested `namespace` directives compose into a dotted prefix, matching the
    # fully-qualified name a blueprint \lean{...} reference uses.
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_NESTED)
    assert "AlgebraicGeometry.Cohomology.aux" in result
    assert "AlgebraicGeometry.Scheme.toAbSheaf" in result


def test_sorry_detected():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_WITH_SORRY)
    assert result["broken"].has_sorry is True
    assert result["broken"].proof_size is None


def test_no_sorry_has_proof_size():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    assert result["Foo.my_theorem"].has_sorry is False
    assert result["Foo.my_theorem"].proof_size is not None
    assert result["Foo.my_theorem"].proof_size > 0


def test_multimod():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_MULTIMOD)
    assert "alpha" in result
    assert "beta"  in result
    assert "gamma" in result


def test_namespace_end_stripped():
    # "end Foo" must not appear in my_theorem's source
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    assert "end Foo" not in result["Foo.my_theorem"].source


def test_scan_directory(tmp_path):
    (tmp_path / "A.lean").write_text(_LEAN_BASIC)
    (tmp_path / "B.lean").write_text(_LEAN_WITH_SORRY)
    result = LeanScanner().scan(tmp_path)
    assert "Foo.my_theorem" in result
    assert "broken" in result


def test_lake_directory_skipped(tmp_path):
    lake = tmp_path / ".lake" / "packages" / "Mathlib"
    lake.mkdir(parents=True)
    (lake / "Hidden.lean").write_text(_LEAN_BASIC)
    result = LeanScanner().scan(tmp_path)
    assert "Foo.my_theorem" not in result


def test_name_field_matches_key():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    for key, decl in result.items():
        assert decl.name == key


_LEAN_COMMENTED = """\
/-
def fake_block : Nat := 0
-/

/-- def fake_doc : Nat := 1
A docstring whose body mentions def at line start. -/
theorem real (n : Nat) : n = n := rfl

-- def fake_line : Nat := 2
def realdef : Nat := 3
"""


def test_keywords_in_comments_are_not_declarations():
    # keywords inside block comments, docstrings and line comments must not be
    # mistaken for declarations
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_COMMENTED)
    assert set(result) == {"real", "realdef"}


_LEAN_MUTUAL = """\
namespace M

mutual
  def isEven : Nat → Bool
    | 0 => true
    | n + 1 => isOdd n
  def isOdd : Nat → Bool
    | 0 => false
    | n + 1 => isEven n
end

end M
"""


def test_indented_mutual_declarations_found():
    # the inner, indented defs of a `mutual` block are picked up and namespaced
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_MUTUAL)
    assert "M.isEven" in result
    assert "M.isOdd" in result


def test_admit_counts_as_incomplete():
    scanner = LeanScanner()
    result = scanner._extract_from_source("lemma stub : False := by admit\n")
    assert result["stub"].has_sorry is True
    assert result["stub"].proof_size is None


def test_inline_block_comment_does_not_fuse_tokens():
    scanner = LeanScanner()
    result = scanner._extract_from_source("def f /- note -/ : Nat := 0\n")
    assert "f" in result


def test_conflicting_fqn_recorded(tmp_path):
    # same name, *different* body → a real conflict
    (tmp_path / "A.lean").write_text("def dup : Nat := 1\n")
    (tmp_path / "B.lean").write_text("def dup : Nat := 2\n")
    scanner = LeanScanner()
    scanner.scan(tmp_path)
    assert any(c[0] == "dup" for c in scanner.collisions)


def test_identical_redefinition_not_flagged(tmp_path):
    # same name, identical body (e.g. a duplicated source tree) → not a conflict
    (tmp_path / "A.lean").write_text("def same : Nat := 1\n")
    (tmp_path / "B.lean").write_text("def same : Nat := 1\n")
    scanner = LeanScanner()
    scanner.scan(tmp_path)
    assert scanner.collisions == []


_LEAN_ROOT_ESCAPE = """\
namespace A.B

def local_one : Nat := 1

theorem _root_.C.global_one : True := trivial

end A.B
"""


def test_hidden_directories_skipped(tmp_path):
    # tooling/build dirs (.archon snapshots, .git, .lake) must be ignored
    (tmp_path / "Real.lean").write_text("def real : Nat := 0\n")
    for hidden in [".archon/lanes/snap", ".git", ".lake/packages/Mathlib"]:
        d = tmp_path / hidden
        d.mkdir(parents=True)
        (d / "Copy.lean").write_text("def hiddenCopy : Nat := 1\n")
    result = LeanScanner().scan(tmp_path)
    assert "real" in result
    assert "hiddenCopy" not in result


def test_blank_lines_collapsed():
    src = """\
def f : Nat :=
  /- a long
     block comment
     spanning lines -/
  42
"""
    scanner = LeanScanner()
    result = scanner._extract_from_source(src)
    # the block comment becomes blank lines — they must not pile up
    assert "\n\n\n" not in result["f"].source


def test_root_escape_namespace():
    # `_root_.` declarations are absolute — the enclosing namespace is dropped
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_ROOT_ESCAPE)
    assert "A.B.local_one" in result
    assert "C.global_one" in result
    assert "A.B._root_.C.global_one" not in result
