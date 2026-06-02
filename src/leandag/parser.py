from __future__ import annotations

import re
from pathlib import Path

from .models import BlueprintDecl


NODE_ENVS: frozenset[str] = frozenset({
    "definition", "lemma", "proposition", "theorem",
    "corollary", "exercise", "remark", "conjecture", "notation",
})

_STRIP_CMDS = re.compile(
    r'\\(?:label|lean|uses|leanok|notready|mathlibok|discussion)'
    r'(?:\*)?'
    r'(?:\s*\{[^}]*\})?'
)

_LABEL_RE   = re.compile(r'\\label\{([^}]+)\}')
_LEAN_RE    = re.compile(r'\\lean\{([^}]+)\}')
_USES_RE    = re.compile(r'\\uses\{([^}]+)\}')
_LEANOK_RE  = re.compile(r'\\leanok\b')
_CHAPTER_RE = re.compile(r'\\chapter\*?\{([^}]+)\}')
_INPUT_RE   = re.compile(r'\\input\{([^}]+)\}')
_PROOF_RE   = re.compile(r'\\begin\{proof\}(.*?)\\end\{proof\}', re.DOTALL)


class BlueprintParser:
    """
    Parse a leanblueprint LaTeX project rooted at an entry ``.tex`` file.

    Usage::

        parser = BlueprintParser(Path("blueprint/src/web.tex"))
        decls, proofs = parser.parse()
    """

    def __init__(self, entry: Path) -> None:
        self._entry = entry

    def parse(self) -> tuple[list[BlueprintDecl], dict[str, str]]:
        """
        Return ``(declarations, proof_bodies)``.

        ``proof_bodies`` maps a declaration id to the raw LaTeX text
        inside its nearest ``proof`` environment.
        """
        text   = self._load_tex(self._entry, visited=set())
        decls  = self._extract_declarations(text)
        proofs = self._extract_proofs(text, decls)
        for decl in decls:
            decl.proof_tex = proofs.get(decl.id, '')
        return decls, proofs

    def _load_tex(self, path: Path, visited: set[Path]) -> str:
        """Recursively load a .tex file, expanding \\input{{}} directives."""
        path = path.resolve()
        if path in visited:
            return ''
        visited.add(path)
        text = self._strip_comments(
            path.read_text(encoding='utf-8', errors='replace')
        )

        def _expand(m: re.Match) -> str:
            fname = m.group(1).strip()
            if not fname.endswith('.tex'):
                fname += '.tex'
            child = (path.parent / fname).resolve()
            return self._load_tex(child, visited) if child.exists() else ''

        return _INPUT_RE.sub(_expand, text)

    def _extract_declarations(self, text: str) -> list[BlueprintDecl]:
        chapter_positions = [
            (m.start(), m.group(1).strip()) for m in _CHAPTER_RE.finditer(text)
        ]

        def chapter_at(pos: int) -> str:
            name = ""
            for cpos, cname in chapter_positions:
                if cpos <= pos:
                    name = cname
            return name

        decls: list[BlueprintDecl] = []
        for env_type in NODE_ENVS:
            begin_pat = re.compile(
                rf'\\begin\{{{re.escape(env_type)}\}}'
                rf'(?:\s*\[([^\]]*)\])?'
            )
            end_pat = re.compile(rf'\\end\{{{re.escape(env_type)}\}}')

            for bm in begin_pat.finditer(text):
                em = end_pat.search(text, bm.end())
                if em is None:
                    continue

                body  = text[bm.end():em.start()]
                title = (bm.group(1) or '').strip()

                label_m = _LABEL_RE.search(body)
                if label_m is None:
                    continue

                lean_m = _LEAN_RE.search(body)
                uses_m = _USES_RE.search(body)

                label     = label_m.group(1).strip()
                lean_name = lean_m.group(1).strip() if lean_m else None
                is_proved = bool(_LEANOK_RE.search(body))
                uses_raw  = uses_m.group(1) if uses_m else ''
                uses      = [u.strip() for u in uses_raw.split(',') if u.strip()]

                stmt = _STRIP_CMDS.sub('', body)
                stmt = re.sub(r'\n{3,}', '\n\n', stmt).strip()

                decls.append(BlueprintDecl(
                    id        = label,
                    type      = env_type,
                    title     = title,
                    chapter   = chapter_at(bm.start()),
                    statement = stmt,
                    uses      = uses,
                    proof_tex = '',
                    lean_name = lean_name,
                    is_proved = is_proved,
                ))

        label_pos = {m.group(1).strip(): m.start() for m in _LABEL_RE.finditer(text)}
        decls.sort(key=lambda d: label_pos.get(d.id, 0))
        return decls

    def _extract_proofs(
        self,
        text: str,
        decls: list[BlueprintDecl],
    ) -> dict[str, str]:
        label_pos     = {m.group(1).strip(): m.start() for m in _LABEL_RE.finditer(text)}
        sorted_labels = sorted(label_pos.items(), key=lambda x: x[1])

        proofs: dict[str, str] = {}
        for pm in _PROOF_RE.finditer(text):
            preceding = [(lid, pos) for lid, pos in sorted_labels if pos < pm.start()]
            if preceding:
                node_id        = max(preceding, key=lambda x: x[1])[0]
                proofs[node_id] = pm.group(1)
        return proofs

    @staticmethod
    def _strip_comments(text: str) -> str:
        """Remove LaTeX % comments, respecting \\%."""
        out, i, n = [], 0, len(text)
        while i < n:
            if text[i] == '\\' and i + 1 < n:
                out.append(text[i:i+2])
                i += 2
            elif text[i] == '%':
                while i < n and text[i] != '\n':
                    i += 1
            else:
                out.append(text[i])
                i += 1
        return ''.join(out)
