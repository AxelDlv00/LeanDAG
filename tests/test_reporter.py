import json
import io
from contextlib import redirect_stdout, redirect_stderr

from leandag.reporter import Reporter


def test_json_emit_goes_to_stdout():
    rep = Reporter("json")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rep.step("scanning")          # diagnostic → stderr
        rep.emit({"a": 1, "b": [2, 3]})
    assert json.loads(out.getvalue()) == {"a": 1, "b": [2, 3]}
    assert "scanning" in err.getvalue()       # logs separated from data


def test_text_mode_uses_text_renderer():
    rep = Reporter("text")
    out = io.StringIO()
    with redirect_stdout(out):
        rep.emit({"x": 1}, rich=lambda: print("RICH"), text=lambda: print("TEXT"))
    assert out.getvalue().strip() == "TEXT"


def test_rich_mode_uses_rich_renderer():
    rep = Reporter("rich")
    out = io.StringIO()
    with redirect_stdout(out):
        rep.emit({"x": 1}, rich=lambda: print("RICH"), text=lambda: print("TEXT"))
    assert "RICH" in out.getvalue()


def test_text_table_has_no_ansi():
    rep = Reporter("text")
    out = io.StringIO()
    with redirect_stdout(out):
        rep.table(["a", "b"], [[1, 2], [3, 4]])
    s = out.getvalue()
    assert "\x1b[" not in s            # no ANSI escapes
    assert "a" in s and "3" in s
