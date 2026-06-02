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


def test_finds_declarations():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    assert "my_theorem" in result
    assert "helper" in result


def test_sorry_detected():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_WITH_SORRY)
    assert result["broken"].has_sorry is True
    assert result["broken"].proof_size is None


def test_no_sorry_has_proof_size():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    assert result["my_theorem"].has_sorry is False
    assert result["my_theorem"].proof_size is not None
    assert result["my_theorem"].proof_size > 0


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
    assert "end Foo" not in result["my_theorem"].source


def test_scan_directory(tmp_path):
    (tmp_path / "A.lean").write_text(_LEAN_BASIC)
    (tmp_path / "B.lean").write_text(_LEAN_WITH_SORRY)
    result = LeanScanner().scan(tmp_path)
    assert "my_theorem" in result
    assert "broken" in result


def test_lake_directory_skipped(tmp_path):
    lake = tmp_path / ".lake" / "packages" / "Mathlib"
    lake.mkdir(parents=True)
    (lake / "Hidden.lean").write_text(_LEAN_BASIC)
    result = LeanScanner().scan(tmp_path)
    assert "my_theorem" not in result


def test_name_field_matches_key():
    scanner = LeanScanner()
    result = scanner._extract_from_source(_LEAN_BASIC)
    for key, decl in result.items():
        assert decl.name == key
