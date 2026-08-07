# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A small, careful SQL lexer: comment stripping and header extraction.

This exists for one reason. ``trappoint migrate lint`` bans ``CREATE SEQUENCE``,
``nextval(``, ``SERIAL`` and ``unique_rowid()`` from every migration file and every
rendered template (ruling D10). A naive ``grep`` gets that wrong in both directions:

* it fires on a comment that *explains* the ban, so the guard becomes annoying and
  then gets weakened, which is how guards die;
* it misses a token inside a dollar-quoted PL/pgSQL body, which is exactly where a
  trigger function would reintroduce a sequence.

So the lint runs over code with comments removed and **everything else kept**,
including string literals and dollar-quoted bodies. The distinction the lexer must get
right is therefore narrow and testable: what is a comment, and what merely looks like
one because it sits inside a quoted region.

Dollar quoting matters more than it looks: ``$$ … -- not a comment? yes it is … $$`` is
a function body, comments inside it ARE comments, and ``'it''s'`` is one string
literal, not two.
"""

from __future__ import annotations

import re

__all__ = ["collapse_whitespace", "header_comment", "strip_sql_comments"]

# `$$` or `$tag$`, where a tag is a SQL identifier. Anchored with `match()` at the
# `$` so a bare `$1` placeholder is never mistaken for the opening of a quoted region.
_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_]\w*)?\$")


def strip_sql_comments(sql: str) -> str:  # noqa: PLR0912, PLR0915
    """Return *sql* with ``--`` line comments and ``/* … */`` block comments removed.

    String literals (``'…'``), quoted identifiers (``"…"``) and dollar-quoted regions
    (``$$…$$``, ``$tag$…$tag$``) are preserved verbatim; comments *inside* a
    dollar-quoted region are removed, because a PL/pgSQL body is code.

    Removed comments are replaced by a single space so that token boundaries survive:
    ``CREATE/**/SEQUENCE`` must not become ``CREATESEQUENCE`` and thereby dodge the ban.

    PostgreSQL block comments nest; this follows that rule rather than PostgreSQL's
    ancestor, because CockroachDB accepts the PostgreSQL dialect.

    The branch and statement counts are suppressed rather than refactored: a lexer IS a
    branch per token class, and splitting it into six helpers that share a cursor would
    move the state between functions without removing any of it, while making the one
    thing a reader must check — that every quoting form is handled — harder to see.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]

        # ── line comment ────────────────────────────────────────────────────
        if ch == "-" and sql.startswith("--", i):
            end = sql.find("\n", i)
            if end == -1:
                out.append(" ")
                break
            out.append(" ")
            i = end  # keep the newline itself: line numbers must not move
            continue

        # ── block comment, nesting ──────────────────────────────────────────
        if ch == "/" and sql.startswith("/*", i):
            depth = 1
            j = i + 2
            while j < n and depth:
                if sql.startswith("/*", j):
                    depth += 1
                    j += 2
                elif sql.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    if sql[j] == "\n":
                        out.append("\n")  # again, keep line numbers honest
                    j += 1
            out.append(" ")
            i = j
            continue

        # ── single-quoted string, '' escapes ────────────────────────────────
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            continue

        # ── quoted identifier, "" escapes ───────────────────────────────────
        if ch == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(sql[i:j])
            i = j
            continue

        # ── dollar quoting ──────────────────────────────────────────────────
        if ch == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m is not None:
                tag = m.group(0)
                close = sql.find(tag, m.end())
                body_end = n if close == -1 else close + len(tag)
                body = sql[m.end() : n if close == -1 else close]
                # Comments inside a routine body are comments. Recurse on the body only.
                out.append(tag)
                out.append(strip_sql_comments(body))
                if close != -1:
                    out.append(tag)
                i = body_end
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def header_comment(sql: str) -> str:
    r"""Return the leading comment block of *sql*.

    "Leading" means every line before the first line carrying non-comment,
    non-whitespace text. This is the region ``trappoint migrate lint`` searches for an
    ``MI\\d\\d`` or ``I\\d\\d`` citation, and searching only the header is the point:
    ARCHITECTURE.md §18 requires every migration to *declare* which invariant it
    realises, at the top, where a reviewer reads it — not to happen to mention one
    three hundred lines down inside a constraint name.
    """
    lines: list[str] = []
    for raw in sql.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append(raw)
            continue
        if stripped.startswith("--"):
            lines.append(raw)
            continue
        break
    return "\n".join(lines)


def collapse_whitespace(text: str) -> str:
    """Collapse every run of whitespace to one space and strip the ends.

    Used only by the schema fingerprint. ``SHOW CREATE ALL TABLES`` does not guarantee
    formatting stability across versions, and a fingerprint that changes because a
    formatter changed is a fingerprint that gets ignored.
    """
    return " ".join(text.split())
