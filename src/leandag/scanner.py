from __future__ import annotations

import re
from pathlib import Path

from .models import LeanDecl


# Lines at column 0 that indicate we've left the declaration body.
_OUTSIDE_DECL_RE = re.compile(
    r'^(?:end\b|section\b|namespace\b|variable\b|open\b'
    r'|noncomputable\s+section|#check\b|#eval\b|#print\b)'
)

# Opening line of a Lean declaration.
# `example` and anonymous `instance :` are split points even with no name —
# `*` (not `+`) allows an empty capture group.
_DECL_RE = re.compile(
    r'^(?:(?:private|protected|noncomputable|irreducible|unsafe|scoped)\s+)*'
    r'(?:theorem|def|lemma|instance|abbrev|structure|class|inductive|example)\s+'
    r'([^\s{(\[:]*)' ,
    re.MULTILINE,
)


class LeanScanner:
    """
    Scan a Lean project tree and extract all named declarations.

    Usage::

        scanner = LeanScanner()
        decls = scanner.scan(Path("."))   # dict[name, LeanDecl]
    """

    def scan(self, root: Path) -> dict[str, LeanDecl]:
        """Return ``{name: LeanDecl}`` for every named declaration under *root*."""
        result: dict[str, LeanDecl] = {}
        for lean_file in sorted(root.glob('**/*.lean')):
            if '.lake' in lean_file.parts:
                continue
            try:
                raw = lean_file.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            result.update(self._extract_from_source(raw))
        return result

    def _extract_from_source(self, raw: str) -> dict[str, LeanDecl]:
        result: dict[str, LeanDecl] = {}
        matches = list(_DECL_RE.finditer(raw))

        for i, m in enumerate(matches):
            name = m.group(1).rstrip('.,;')
            if not name:
                # Anonymous example / unnamed instance — acts as a range
                # boundary but produces no LeanDecl entry.
                continue

            start  = m.start()
            end    = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            source = self._trim_to_decl(raw[start:end].strip())

            stripped  = self._strip_comments(source)
            has_sorry = bool(re.search(r'\bsorry\b', stripped))

            result[name] = LeanDecl(
                name       = name,
                source     = source,
                proof_size = None if has_sorry else len(stripped),
                has_sorry  = has_sorry,
            )

        return result

    @staticmethod
    def _trim_to_decl(source: str) -> str:
        """
        Strip trailing non-declaration content from a raw source slice.

        After splitting at declaration keywords the slice may include trailing
        infrastructure: ``section``/``end``/``variable``/``open``/``#check``
        lines and column-0 comment blocks.
        """
        lines  = source.splitlines()
        cutoff = len(lines)

        for i in range(1, len(lines)):
            line     = lines[i]
            stripped = line.strip()
            if not stripped:
                continue

            at_col0 = bool(line) and not line[0].isspace()
            if at_col0 and (
                _OUTSIDE_DECL_RE.match(stripped) or stripped.startswith('--')
            ):
                j = i
                while j > 0 and not lines[j - 1].strip():
                    j -= 1
                cutoff = j
                break

        return '\n'.join(lines[:cutoff]).rstrip()

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Remove Lean ``--`` line comments and ``/- -/`` block comments."""
        out, i, n = [], 0, len(text)
        while i < n:
            if text[i] == '-' and i + 1 < n and text[i + 1] == '-':
                while i < n and text[i] != '\n':
                    i += 1
            elif text[i] == '/' and i + 1 < n and text[i + 1] == '-':
                i += 2
                depth = 1
                while i < n and depth > 0:
                    if text[i] == '/' and i + 1 < n and text[i + 1] == '-':
                        depth += 1
                        i += 2
                    elif text[i] == '-' and i + 1 < n and text[i + 1] == '/':
                        depth -= 1
                        i += 2
                    else:
                        i += 1
            else:
                out.append(text[i])
                i += 1
        return ''.join(out)
