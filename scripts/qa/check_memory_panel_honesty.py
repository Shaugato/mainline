#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The honesty audit for `/memory.html` — the store, retrieve, act panel.

    python scripts/qa/check_memory_panel_honesty.py                # audit + falsification
    python scripts/qa/check_memory_panel_honesty.py --audit-only    # audit only
    python scripts/qa/check_memory_panel_honesty.py --self-test     # falsification only
    python scripts/qa/check_memory_panel_honesty.py --check FILE... # audit named files
    python scripts/qa/check_memory_panel_honesty.py --list-rules

WHAT THIS GUARDS, AND WHY IT IS A STATIC AUDIT
----------------------------------------------
`docs/demo/memory-visible-plan.md` builds one page — `verticals/mainline/apps/console/public/`
`memory.html` plus its stylesheet and its two module scripts — whose entire claim is that
**every value on it came back over HTTP from the deployed kernel**. The four files are static
assets: Vite copies `public/` into `dist/` verbatim, so what is written in them is what a
judge downloads. A literal typed into any one of them is a value the page did not have to be
given, and one such literal is enough to make the whole panel a picture of a memory rather
than a memory.

`r1-judging` supplies the reason this is a rules matter and not only a conscience matter: the
Official Rules require the Project *"must function as depicted in the video"*, so a hard-coded
SQLSTATE, a pasted statement or a timer faking latency is a Functionality violation, judged by
people with this public repository open.

A static audit catches the class the browser tier cannot: the browser tier proves the page
behaved honestly **on the run it watched**; this proves the source contains nothing that could
behave dishonestly on a run nobody watched — including on a day the API is down, which is
exactly when a fallback literal would surface.

THE SEVEN RULES, EACH NAMING THE RULING IT ENFORCES
---------------------------------------------------
    M8-UUID     no UUID-shaped literal, and no `dec0de00`         (plan R-M8)
    M6-SQL      no pasted statement; statement text comes from
                `statement_refs[].text` or is declared absent      (plan R-M6)
    M7-STATE    no SQLSTATE literal outside a comment              (plan R-M7, R-M10)
    M11-ARCH    no `ARCHITECTURE.md` — it does not exist here      (plan R-M11)
    M11-YEAR    no `2024` — the incident is 2019-03-14, and
                `INC-2024-0117` is a STAGED payload we may not
                narrate                                            (plan R-M11)
    M9-RECALL   no embedding / vector / similarity / cosine
                vocabulary and no threshold claim                  (plan R-M9)
    M7-TIMER    no `setTimeout` / `setInterval` / `sleep` outside a
                scope that already holds a resolved response, and
                no timer that gates a request                      (plan R-M7.3)

EVERY RULE CARRIES A FALSIFICATION, AND IT RUNS BY DEFAULT
-----------------------------------------------------------
`scripts/qa/check_reuse.py` and `scripts/submission/check_submission_prose.py` both expose
`--self-test`, and both make it opt-in. This program makes it **opt-out** instead, because a
guard nobody has watched fail is not a guard, and the whole falsification suite costs a few
milliseconds of string scanning. Each rule declares its own planted violation and — where the
distinction has teeth — its own clean control that must stay green. A rule that cannot show
itself going red is a rule this program refuses to ship: `--self-test` fails if any planted
sample passes, and it also fails if a clean control goes red.

WHAT IS EXEMPT, AND WHY IT HAS TO BE
-------------------------------------
`verticals/mainline/apps/console/fixtures/memory-loop/**` is exempt from every rule (plan
R-M8, last line). Those files are response bodies captured off the wire by
`scripts/demo/capture_memory_loop.py`, byte for byte. They are FULL of UUIDs, SQLSTATEs and
statement text — that is what an honest capture of this API looks like, and rewriting one to
please a grep would be the exact act this repository has already reverted a worker for. The
exemption is unconditional and it is REPORTED, because "not scanned" and "passed" are
different results.

WHAT THIS PROGRAM DELIBERATELY DOES NOT DO
-------------------------------------------
It does not parse JavaScript into an AST — the standard library has no JS parser and vendoring
one to guard four files would be a larger unaudited surface than the thing audited. It reads
the files with a lexer that understands comments, strings, template literals and regular
expression literals well enough to blank them (`_scan_js`), and every rule states which view
of the text it scans and why. Where the lexer is approximate the approximation is toward
FLAGGING, never toward passing.

It also does not check whether the page *works*. That is
`verticals/mainline/apps/console/tests/browser/memory-loop.spec.ts`, which records the network
and asserts every visible value string appears in one of the five response bodies. The two are
complements: this one reads the source, that one watches the run.

SIBLINGS. `scripts/demo/claim_hygiene.py` guards published prose against the must-not-claim
table; `scripts/submission/check_submission_prose.py` extends it to the submission surface.
Neither reaches `public/**`, and neither asks these questions.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

# ── The surface ───────────────────────────────────────────────────────────────────────────

#: The four files plan §4 gives to W2, W3 and W4 — the whole of the page a judge downloads.
#: Repo-relative, POSIX separators; resolved against `--root`.
TARGET_PATHS: tuple[str, ...] = (
    "verticals/mainline/apps/console/public/memory.html",
    "verticals/mainline/apps/console/public/memory.css",
    "verticals/mainline/apps/console/public/memory-loop.js",
    "verticals/mainline/apps/console/public/memory-verify.js",
)

#: Path fragments that are never scanned, however they are reached — by glob, by `--check`,
#: or by a future caller pointing this program at a directory. See the module docstring.
EXEMPT_FRAGMENTS: tuple[str, ...] = (
    "fixtures/memory-loop",
    "node_modules",
    "__pycache__",
    "/dist/",
)


def _is_exempt(path: Path) -> bool:
    """True when *path* is captured evidence or build output rather than page source."""
    posix = path.as_posix()
    padded = f"/{posix.strip('/')}/"
    return any(fragment.strip("/") in posix for fragment in EXEMPT_FRAGMENTS) or "/dist/" in padded


# ── The lexer ─────────────────────────────────────────────────────────────────────────────
#
# Three views of one file, all the same length as the original so that any offset means the
# same thing in each of them and a finding can always be reported at its true line and column.
#
#   raw          the bytes as written
#   no_comments  comments blanked; strings, template text and regex bodies intact
#   code         comments blanked AND string bodies, template text and regex bodies blanked,
#                so that braces and parentheses balance and a keyword inside a string cannot
#                be mistaken for a keyword in code
#
# Blanking preserves newlines so line numbers survive.


@dataclass(frozen=True)
class Views:
    """One file, three ways of looking at it."""

    path: Path
    kind: str  # 'js' | 'css' | 'html'
    raw: str
    no_comments: str
    code: str


def _blank(buffer: list[str], start: int, end: int) -> None:
    """Replace `buffer[start:end]` with spaces, keeping newlines where they were."""
    for index in range(max(0, start), min(len(buffer), end)):
        if buffer[index] != "\n":
            buffer[index] = " "


_JS_REGEX_PRECEDING_CHARS = set("(,=:[!&|?+-*%~^<>;{}\n")
_JS_REGEX_PRECEDING_WORDS = frozenset(
    {
        "return",
        "typeof",
        "instanceof",
        "in",
        "of",
        "new",
        "delete",
        "void",
        "throw",
        "case",
        "do",
        "else",
        "yield",
        "await",
    }
)


def _regex_can_start_here(text: str, index: int) -> bool:
    """Heuristic: is the `/` at *index* the start of a regex literal rather than a division?

    The rule is the usual one — a regex may begin where an expression may begin. Where the
    heuristic is unsure it answers True, because treating a division as a regex blanks a few
    characters of arithmetic (harmless), while treating a regex as a division leaves its
    braces and slashes in the `code` view (which would corrupt brace matching and could hide
    a timer). The approximation runs toward flagging.
    """
    j = index - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0:
        return True
    previous = text[j]
    if previous in _JS_REGEX_PRECEDING_CHARS:
        return True
    if previous.isalnum() or previous in "_$":
        end = j + 1
        start = end
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "_$"):
            start -= 1
        return text[start:end] in _JS_REGEX_PRECEDING_WORDS
    # After `)` an expression cannot begin in valid JS except after a control head, e.g.
    # `if (x) /re/.test(y)`. Rare, and answering True only over-blanks.
    return previous in ")]"


def _js_comment(text: str, index: int) -> int:
    """The end of the comment beginning at *index*, or -1 when none begins there."""
    if not text.startswith("//", index) and not text.startswith("/*", index):
        return -1
    if text[index + 1] == "/":
        end = text.find("\n", index)
        return len(text) if end < 0 else end
    end = text.find("*/", index + 2)
    return len(text) if end < 0 else end + 2


def _js_quoted_end(text: str, index: int) -> int:
    """The end of the `'…'` or `"…"` literal opening at *index*."""
    quote = text[index]
    length = len(text)
    cursor = index + 1
    while cursor < length:
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == quote:
            return cursor + 1
        if char == "\n":  # unterminated; stop at the line end rather than eating the file
            return cursor
        cursor += 1
    return length


def _js_template_end(text: str, index: int, code: list[str]) -> int:
    """Blank the literal text of the template opening at *index*; return its end.

    `${` carries a `{` and its expression ends with the matching `}`, so leaving both in the
    `code` view keeps brace matching balanced. The expression itself IS code and stays
    readable, which is what stops a timer inside an interpolation from hiding here.
    """
    length = len(text)
    cursor = index + 1
    depth = 0
    while cursor < length:
        char = text[cursor]
        if char == "\\":
            if depth == 0:
                _blank(code, cursor, cursor + 2)
            cursor += 2
            continue
        if depth == 0:
            if char == "`":
                return cursor + 1
            if char == "$" and cursor + 1 < length and text[cursor + 1] == "{":
                depth = 1
                cursor += 2
                continue
            _blank(code, cursor, cursor + 1)
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        cursor += 1
    return length


def _js_regex_end(text: str, index: int) -> int:
    """The end of the regex literal opening at *index*, or -1 when it does not close."""
    length = len(text)
    cursor = index + 1
    in_class = False
    while cursor < length:
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "\n":
            return -1  # not a regex after all
        if in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
        elif char == "/":
            cursor += 1
            while cursor < length and text[cursor].isalpha():  # flags
                cursor += 1
            return cursor
        cursor += 1
    return -1


def _scan_js(text: str) -> tuple[str, str]:
    """Return `(no_comments, code)` for JavaScript."""
    length = len(text)
    no_comments = list(text)
    code = list(text)
    index = 0
    while index < length:
        char = text[index]

        comment_end = _js_comment(text, index)
        if comment_end >= 0:
            _blank(no_comments, index, comment_end)
            _blank(code, index, comment_end)
            index = comment_end
            continue

        if char in "\"'":
            end = _js_quoted_end(text, index)
            _blank(code, index + 1, end - 1)
            index = end
            continue

        if char == "`":
            index = _js_template_end(text, index, code)
            continue

        if char == "/" and _regex_can_start_here(text, index):
            end = _js_regex_end(text, index)
            if end >= 0:
                _blank(code, index + 1, end - 1)
                index = end
                continue

        index += 1

    return "".join(no_comments), "".join(code)


def _scan_css(text: str) -> tuple[str, str]:
    """Return `(no_comments, code)` for CSS: `/* */` comments and quoted strings."""
    length = len(text)
    no_comments = list(text)
    code = list(text)
    index = 0
    while index < length:
        char = text[index]
        following = text[index + 1] if index + 1 < length else ""
        if char == "/" and following == "*":
            end = text.find("*/", index + 2)
            end = length if end < 0 else end + 2
            _blank(no_comments, index, end)
            _blank(code, index, end)
            index = end
            continue
        if char in "\"'":
            cursor = index + 1
            while cursor < length:
                if text[cursor] == "\\":
                    cursor += 2
                    continue
                if text[cursor] == char:
                    cursor += 1
                    break
                if text[cursor] == "\n":
                    break
                cursor += 1
            _blank(code, index + 1, cursor - 1)
            index = cursor
            continue
        index += 1
    return "".join(no_comments), "".join(code)


def _scan_html(text: str) -> tuple[str, str]:
    """Return `(no_comments, code)` for HTML: `<!-- -->` comments.

    `memory.html` carries no inline `<script>` and no inline `<style>` — it links one
    stylesheet and two modules, all siblings — so there is no embedded language to lex. If
    one is ever added, the `code` view below still contains it and the JS rules do not run on
    `.html`; that gap is named here rather than left for somebody to find.
    """
    length = len(text)
    no_comments = list(text)
    index = 0
    while index < length:
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            end = length if end < 0 else end + 3
            _blank(no_comments, index, end)
            index = end
            continue
        index += 1
    joined = "".join(no_comments)
    return joined, joined


_SCANNERS: dict[str, Callable[[str], tuple[str, str]]] = {
    "js": _scan_js,
    "css": _scan_css,
    "html": _scan_html,
}

_KIND_BY_SUFFIX: dict[str, str] = {
    ".js": "js",
    ".mjs": "js",
    ".css": "css",
    ".html": "html",
    ".htm": "html",
}


def load_views(path: Path, text: str | None = None) -> Views:
    """Read *path* (or use *text*) and produce its three views."""
    kind = _KIND_BY_SUFFIX.get(path.suffix.lower(), "js")
    raw = path.read_text(encoding="utf-8") if text is None else text
    no_comments, code = _SCANNERS[kind](raw)
    return Views(path=path, kind=kind, raw=raw, no_comments=no_comments, code=code)


# ── Findings ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One violation, at one place, with the sentence that explains it."""

    rule: str
    path: Path
    line: int
    column: int
    excerpt: str
    detail: str

    def render(self, root: Path | None = None) -> str:
        shown = self.path
        if root is not None:
            try:
                shown = self.path.relative_to(root)
            except ValueError:
                shown = self.path
        return (
            f"  {shown.as_posix()}:{self.line}:{self.column}  [{self.rule}]\n"
            f"      found:  {self.excerpt}\n"
            f"      {self.detail}"
        )


def _position(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    return line, offset - start + 1


def _excerpt(text: str, start: int, end: int, width: int = 96) -> str:
    piece = text[start:end]
    piece = piece.replace("\n", "\\n").replace("\t", " ")
    if len(piece) > width:
        piece = piece[: width - 3] + "..."
    return piece


# ── The rules ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Rule:
    """One question this program asks of the page source.

    `plants` are the falsifications: each is a snippet that MUST produce at least one finding.
    `controls` are clean samples that must produce none — they exist for the rules where the
    line between honest and dishonest is a distinction rather than a keyword, because a rule
    that fires on everything is as useless as one that fires on nothing.
    """

    id: str
    ruling: str
    title: str
    kinds: frozenset[str]
    scan: Callable[[Views], list[Finding]]
    plants: tuple[tuple[str, str], ...]  # (filename, source)
    controls: tuple[tuple[str, str], ...] = ()


def _findings_for(
    views: Views,
    rule_id: str,
    view_text: str,
    pattern: re.Pattern[str],
    detail: str,
    *,
    predicate: Callable[[re.Match[str]], bool] | None = None,
) -> list[Finding]:
    """Every match of *pattern* in *view_text*, reported against the raw file's coordinates."""
    findings: list[Finding] = []
    for match in pattern.finditer(view_text):
        if predicate is not None and not predicate(match):
            continue
        line, column = _position(views.raw, match.start())
        findings.append(
            Finding(
                rule=rule_id,
                path=views.path,
                line=line,
                column=column,
                excerpt=_excerpt(views.raw, match.start(), match.end()),
                detail=detail,
            )
        )
    return findings


# — M8-UUID ————————————————————————————————————————————————————————————————————————————————

_UUID_FULL = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
#: The truncated shapes people paste when they are shortening an id for a comment. `dec0de00`
#: is called out by name because it is the demo world's prefix and because plan R-M8 names it.
_UUID_PARTIAL = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}\b")
_DEC0DE00 = re.compile(r"dec0de00", re.IGNORECASE)

_M8_DETAIL = (
    "R-M8: the page addresses every subject from GET /v1/demo/subjects. The deployed world's "
    "ids are not the ids a local scenario derives, so a literal here is a page that lies on "
    "the next deploy. Fetch the identifier; never type it."
)


def _scan_uuid(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    for pattern in (_UUID_FULL, _UUID_PARTIAL, _DEC0DE00):
        findings.extend(_findings_for(views, "M8-UUID", views.raw, pattern, _M8_DETAIL))
    # One offset can match both the full and the partial shape; report each place once.
    seen: set[tuple[int, int]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.line, finding.column)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


# — M6-SQL ————————————————————————————————————————————————————————————————————————————————
#
# Scanned over the RAW text, comments included. A statement in a comment is one uncomment away
# from being a statement on the page, and R-M6 is not a rule about where the characters sit —
# it is a rule that this page never carries a statement it was not handed. The two disclosures
# it does show are `<pre>` elements filled from `statement_refs[].text` at runtime.
#
# The uppercase patterns are canonical pasted SQL and do not occur in English prose. The
# lowercase ones each demand a verb AND a schema-qualified relation, which prose does not do.

_SQL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bSELECT\b[\s\S]{0,400}?\bFROM\b"),
    re.compile(r"\bINSERT\s+INTO\b"),
    re.compile(r"\bUPDATE\b[\s\S]{0,200}?\bSET\b"),
    re.compile(r"\bDELETE\s+FROM\b"),
    re.compile(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW|INDEX|FUNCTION|TRIGGER|SCHEMA)\b"),
    re.compile(r"\bALTER\s+TABLE\b"),
    re.compile(r"\b(?:GROUP|ORDER)\s+BY\b"),
    re.compile(r"\bDISTINCT\s+ON\b"),
    re.compile(r"\bRETURNING\b\s+[\w\"*]"),
    re.compile(r"\bWITH\b[\s\S]{0,120}?\bAS\s*\("),
    re.compile(r"\bselect\b[\s\S]{0,300}?\bfrom\s+[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*", re.I),
    re.compile(r"\binsert\s+into\s+[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*", re.I),
    re.compile(r"\bdelete\s+from\s+[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*", re.I),
    re.compile(r"\bupdate\s+[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s+set\b", re.I),
)

_M6_DETAIL = (
    "R-M6: statement text is rendered byte for byte from statement_refs[].text, or the gap is "
    "stated in the words 'statement text not returned by this endpoint'. Pasting SQL from a "
    "migration or a seed is forbidden - a query path we assert is worth less than one the "
    "server hands us, and the difference is the whole product."
)


def _scan_sql(views: Views) -> list[Finding]:
    findings: list[Finding] = []
    for pattern in _SQL_PATTERNS:
        findings.extend(_findings_for(views, "M6-SQL", views.raw, pattern, _M6_DETAIL))
    seen: set[tuple[int, int]] = set()
    unique: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (f.line, f.column)):
        key = (finding.line, finding.column)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


# — M7-STATE ———————————————————————————————————————————————————————————————————————————————
#
# Scanned over `no_comments`, which is what "as a value rather than as prose" means here: a
# comment explaining that beat 2 answers 23514 is documentation, and this file's own docstring
# would trip its own rule otherwise. Anything OUTSIDE a comment — a JS literal, a CSS string,
# HTML text content — is either a value the page can render or a value it can compare against,
# and both are the fabricated exhibit. Every SQLSTATE on the panel arrives in the POST body.

#: All-digit SQLSTATEs are indistinguishable from ordinary five-digit numbers (26257 is the
#: node's port; 86400 is a day in seconds), so the all-digit half of the vocabulary is a list
#: rather than a shape. It is drawn from the codes this kernel actually reports plus the
#: PostgreSQL classes a refusal can land in.
_SQLSTATE_DIGITS: frozenset[str] = frozenset(
    {
        "00000",
        "01000",
        "02000",
        "03000",
        "08000",
        "08003",
        "08006",
        "21000",
        "22001",
        "22003",
        "22004",
        "22007",
        "22012",
        "22023",
        "23000",
        "23001",
        "23502",
        "23503",
        "23505",
        "23514",
        "25000",
        "25001",
        "25006",
        "40000",
        "40001",
        "40002",
        "40003",
        "42501",
        "42601",
        "42602",
        "42703",
        "42804",
        "42830",
        "42883",
        "44000",
        "53100",
        "53200",
        "54000",
        "55000",
        "55006",
        "57014",
        "58030",
    }
)

#: The lettered shapes are unambiguous: `P0001` (raise_exception, which beat 3 answers with),
#: `42P01`, `55P03`, `0A000`. Nothing else in a stylesheet or a module looks like these.
_SQLSTATE_LETTERED = re.compile(r"\b(?:P0\d{3}|\d{2}[A-Z][0-9A-Z]{2}|0[A-Z][0-9A-Z]{3})\b")
_FIVE_DIGITS = re.compile(r"\b\d{5}\b")

_M7_STATE_DETAIL = (
    "Never fake a SQLSTATE. Every SQLSTATE on this panel arrives in the body of the one POST "
    "to /v1/demo/gate-run and is painted from /data/beats/N/sqlstate. A literal outside a "
    "comment is a value the page could show without being given it, which is a staged refusal "
    "and a Devpost Functionality violation."
)


def _scan_sqlstate(views: Views) -> list[Finding]:
    findings = _findings_for(
        views,
        "M7-STATE",
        views.no_comments,
        _FIVE_DIGITS,
        _M7_STATE_DETAIL,
        predicate=lambda match: match.group(0) in _SQLSTATE_DIGITS,
    )
    findings.extend(
        _findings_for(views, "M7-STATE", views.no_comments, _SQLSTATE_LETTERED, _M7_STATE_DETAIL)
    )
    return sorted(findings, key=lambda f: (f.line, f.column))


# — M11-ARCH and M11-YEAR ——————————————————————————————————————————————————————————————————

_ARCHITECTURE_MD = re.compile(r"\bARCHITECTURE\.md\b", re.IGNORECASE)
_M11_ARCH_DETAIL = (
    "R-M11: ARCHITECTURE.md does not exist in this tree (r2-memory warning 1). Citing a "
    "document a judge can click and not find costs more than the citation was worth."
)

_YEAR_2024 = re.compile(r"\b2024\b")
_M11_YEAR_DETAIL = (
    "R-M11: the incident this panel is built on is DEMO-INC-0001, 2019-03-14. INC-2024-0117 "
    "lives inside a STAGED payload and is forbidden to narrate, so 2024 has no honest place "
    "in these four files."
)


def _scan_architecture(views: Views) -> list[Finding]:
    return _findings_for(views, "M11-ARCH", views.raw, _ARCHITECTURE_MD, _M11_ARCH_DETAIL)


def _scan_year(views: Views) -> list[Finding]:
    return _findings_for(views, "M11-YEAR", views.raw, _YEAR_2024, _M11_YEAR_DETAIL)


# — M9-RECALL ——————————————————————————————————————————————————————————————————————————————
#
# Scanned over the RAW text, comments included, and that is deliberate. R-M9 is not satisfied
# by keeping the word out of the visible layer: `recall_candidate`, `event_cue`,
# `clause_embedding` and `lex_posting` are EMPTY in this demo world, the channel is
# `blame_ancestry`, and `demo_permit.sql:181-185` refuses to let anyone claim a threshold. The
# honest way to state the absence is the one the page already takes — render `origin` and the
# five recall counts from the response — not to type the vocabulary and negate it.

_RECALL_VOCABULARY = re.compile(
    r"\b(?:embedding|embeddings|vector|vectors|cosine|similarity|nearest[- ]neighbou?r|knn)\b",
    re.IGNORECASE,
)
_THRESHOLD_CLAIM = re.compile(
    r"(?:\bthreshold\b|\u03b8\s*[=:]?\s*[0-9]|\btau(?:_applied)?\b\s*[=:]?\s*[0-9])",
    re.IGNORECASE,
)
_M9_DETAIL = (
    "R-M9: the similarity tables are empty in this world and tau_applied is 0. A retrieval "
    "visual or a threshold claim would be a fabricated exhibit and the weaker story. State the "
    "absence the way the page does - origin blame_ancestry, and the counts the recall run "
    "returned."
)


def _scan_recall_vocabulary(views: Views) -> list[Finding]:
    findings = _findings_for(views, "M9-RECALL", views.raw, _RECALL_VOCABULARY, _M9_DETAIL)
    findings.extend(_findings_for(views, "M9-RECALL", views.raw, _THRESHOLD_CLAIM, _M9_DETAIL))
    return sorted(findings, key=lambda f: (f.line, f.column))


# — M7-TIMER ———————————————————————————————————————————————————————————————————————————————
#
# The structural rule, and the one with teeth. R-M7.3: "No setTimeout, requestAnimationFrame
# loop, or await sleep() may run before the response has resolved, and none may gate a fetch.
# The reveal timer is constructed inside the .then/await that already holds the parsed body."
#
# The test is lexical, exactly as the ruling words it. For each timer call site:
#
#   1. Find every brace-balanced block containing it, innermost outward, in the `code` view —
#      where strings, comments and regex bodies have been blanked, so braces really balance.
#   2. A block QUALIFIES when its HEADER plus the text of the block BEFORE the call site
#      already resolved a response: `await fetch(`, `await x.text()`, `await x.json()`,
#      `await getJson(`, `await Promise.all(`, or a `.then(` handler. The header is needed
#      because `.then((body) => { … })` puts the marker outside the brace it opens, and the
#      ruling names that handler explicitly; it reaches back only to the nearest `;`, `{` or
#      `}`, so a resolution belonging to an earlier statement cannot be borrowed.
#   3. No qualifying block, up to and including the file, is a violation: the timer can run
#      before any response exists, which is the shape of faked latency.
#   4. Separately, a timer whose callback contains a request gates that request, which the
#      ruling forbids outright however deep in a resolved scope it sits.
#
# The `code` view is load-bearing here, and one of the plants proves it: a comment or a string
# that merely contains the characters `.then(` cannot buy a timer a pass, because both have
# been blanked before this rule ever sees the file.

_TIMER_CALL = re.compile(r"\b(setTimeout|setInterval|requestAnimationFrame|sleep|delay)\s*\(")

_RESOLVED_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bawait\s+fetch\s*\("),
    re.compile(r"\bawait\s+[\w$.\[\]]*\.\s*(?:text|json|arrayBuffer|blob|formData)\s*\("),
    re.compile(r"\bawait\s+[\w$.]*(?:etchJson|getJson|fetchJson|postJson)\s*\("),
    re.compile(r"\bawait\s+Promise\s*\.\s*(?:all|allSettled|any|race)\s*\("),
    re.compile(r"\.\s*then\s*\("),
    re.compile(r"\bawait\s+[\w$.]*(?:[Ff]etch)\w*\s*\("),
)

_REQUEST_IN_CALLBACK = re.compile(
    r"\b(?:fetch|getJson|XMLHttpRequest|sendBeacon|EventSource|WebSocket|import)\s*\("
)

_M7_TIMER_DETAIL = (
    "R-M7.3: no timer may run before the response has resolved and none may gate a request. "
    "The progressive reveal is a display order over values that had ALL already arrived - it "
    "is constructed inside the scope holding the parsed body. A timer anywhere else is a "
    "latency this page did not measure, which is the one thing ?reveal=off exists to disprove."
)

_M7_GATING_DETAIL = (
    "R-M7.3: this timer's callback issues a request, so the timer gates it. Delaying a request "
    "makes the page's own clock part of the number a judge reads. Send the request, then order "
    "the painting of what came back."
)


def _enclosing_blocks(code: str, offset: int) -> list[tuple[int, int]]:
    """Brace-balanced blocks containing *offset*, innermost first.

    An unclosed `{` before the offset counts as a block reaching the end of the file, so a
    syntactically broken file cannot silently lose its enclosing scopes.
    """
    stack: list[int] = []
    blocks: list[tuple[int, int]] = []
    for index, char in enumerate(code):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            start = stack.pop()
            if start < offset < index:
                blocks.append((start, index))
    for start in stack:
        if start < offset:
            blocks.append((start, len(code)))
    blocks.sort(key=lambda block: block[0], reverse=True)
    return blocks


#: How far back a block's header may reach. Long enough for `fetchIt().then((body) => {`,
#: short enough that nothing from an earlier statement can be borrowed.
_HEADER_WINDOW = 400


def _block_header(code: str, start: int) -> str:
    """The expression that opens the block at *start* — `function f(x)`, `.then((body) =>`.

    Bounded backwards by the nearest `;`, `{` or `}`, so the header describes this block and
    only this block. A resolution that belongs to a previous statement ends at that statement's
    semicolon and cannot be picked up here.
    """
    floor = max(0, start - _HEADER_WINDOW)
    boundary = floor
    for index in range(start - 1, floor - 1, -1):
        if code[index] in ";{}":
            boundary = index + 1
            break
    return code[boundary:start]


def _balanced_call_argument(code: str, open_paren: int) -> tuple[int, int]:
    """The span between `(` at *open_paren* and its matching `)` (or the end of the file)."""
    depth = 0
    for index in range(open_paren, len(code)):
        char = code[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return open_paren + 1, index
    return open_paren + 1, len(code)


def _scan_timers(views: Views) -> list[Finding]:
    if views.kind != "js":
        return []
    findings: list[Finding] = []
    code = views.code
    for match in _TIMER_CALL.finditer(code):
        offset = match.start()
        resolved = False
        for start, _end in _enclosing_blocks(code, offset):
            prefix = _block_header(code, start) + code[start:offset]
            if any(marker.search(prefix) for marker in _RESOLVED_MARKERS):
                resolved = True
                break
        line, column = _position(views.raw, offset)
        if not resolved:
            findings.append(
                Finding(
                    rule="M7-TIMER",
                    path=views.path,
                    line=line,
                    column=column,
                    excerpt=_excerpt(views.raw, offset, match.end() + 40),
                    detail=_M7_TIMER_DETAIL,
                )
            )
            continue
        argument_start, argument_end = _balanced_call_argument(code, match.end() - 1)
        if _REQUEST_IN_CALLBACK.search(code[argument_start:argument_end]):
            findings.append(
                Finding(
                    rule="M7-TIMER",
                    path=views.path,
                    line=line,
                    column=column,
                    excerpt=_excerpt(views.raw, offset, min(argument_end + 1, offset + 120)),
                    detail=_M7_GATING_DETAIL,
                )
            )
    return findings


# ── The rule table ────────────────────────────────────────────────────────────────────────

_JS_ONLY = frozenset({"js"})
_ALL_KINDS = frozenset({"js", "css", "html"})

RULES: tuple[Rule, ...] = (
    Rule(
        id="M8-UUID",
        ruling="R-M8",
        title="no UUID-shaped literal and no dec0de00; subjects are addressed from the API",
        kinds=_ALL_KINDS,
        scan=_scan_uuid,
        plants=(
            ("planted.js", "const permit = 'dec0de00-0006-4000-8000-000000000001';\n"),
            ("planted.html", '<b data-cell="x">7f3d9b21-4c0a-4e11-9f52-0b1c2d3e4f50</b>\n'),
            ("planted.css", "/* comment */\n.cell::after { content: 'DEC0DE00'; }\n"),
        ),
        controls=(
            (
                "clean.js",
                (
                    "const ENDPOINTS = { subjects: '/v1/demo/subjects' };\n"
                    "const path = ENDPOINTS.checks.replace('{permit_id}', id);\n"
                ),
            ),
        ),
    ),
    Rule(
        id="M6-SQL",
        ruling="R-M6",
        title="no pasted statement; statement text comes from statement_refs[].text or is absent",
        kinds=_ALL_KINDS,
        scan=_scan_sql,
        plants=(
            (
                "planted.js",
                "const sql = 'SELECT closure_gen FROM mainline.clause_blame_current';\n",
            ),
            (
                "planted.html",
                "<pre>select severity from mainline.blocking_check where open</pre>\n",
            ),
            (
                "planted.js",
                "const q = `INSERT INTO mainline.disposition (check_id) VALUES ($1)`;\n",
            ),
        ),
        controls=(
            (
                "clean.js",
                (
                    "const NO_TEXT = 'statement text not returned by this endpoint';\n"
                    "// the ancestry read names mainline.clause_blame_current and the\n"
                    "// server returns its text; this module renders whatever came back.\n"
                    "const ref = refs.find((entry) => entry.object === OBJECT_NAME);\n"
                ),
            ),
        ),
    ),
    Rule(
        id="M7-STATE",
        ruling="R-M7 / R-M10",
        title="no SQLSTATE literal outside a comment; every SQLSTATE arrives in the POST body",
        kinds=_ALL_KINDS,
        scan=_scan_sqlstate,
        plants=(
            ("planted.js", "const REFUSAL = '23514';\n"),
            ("planted.js", "if (beat.sqlstate === 'P0001') paint(element, 'forged counter');\n"),
            ("planted.html", '<span data-cell="act.beat1.sqlstate">00000</span>\n'),
            ("planted.css", ".beat[data-beat='2'] .sqlstate::after { content: '23514'; }\n"),
        ),
        controls=(
            (
                "clean.js",
                (
                    "// Beat 2 answers 23514 and beat 3 answers P0001; both arrive in the\n"
                    "// payload and neither is written here. 00000 likewise.\n"
                    "return fromEnvelope(sources, 'gate', `/beats/${n - 1}/sqlstate`);\n"
                ),
            ),
            # 26257 is the local node's port and 86400 a day in seconds: five digits, not a
            # SQLSTATE. A rule that fired on these would be noise nobody would keep.
            ("clean.js", "const DSN_PORT = 26257;\nconst DAY_MS = 86400000;\nconst X = 86400;\n"),
        ),
    ),
    Rule(
        id="M11-ARCH",
        ruling="R-M11",
        title="no ARCHITECTURE.md citation; the file does not exist in this tree",
        kinds=_ALL_KINDS,
        scan=_scan_architecture,
        plants=(("planted.html", "<p>The design is described in ARCHITECTURE.md &sect;11.</p>\n"),),
        controls=(
            (
                "clean.html",
                "<p>docs/demo/memory-visible-plan.md is the specification for this page.</p>\n",
            ),
        ),
    ),
    Rule(
        id="M11-YEAR",
        ruling="R-M11",
        title="no 2024; the incident is 2019-03-14 and INC-2024-0117 is a STAGED payload",
        kinds=_ALL_KINDS,
        scan=_scan_year,
        plants=(
            ("planted.html", "<span>incident INC-2024-0117</span>\n"),
            ("planted.js", "const SINCE = '2024-01-17T00:00:00Z';\n"),
        ),
        controls=(
            ("clean.html", "<span>2019-03-14T06:20:00Z</span>\n"),
            ("clean.js", "// SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"),
        ),
    ),
    Rule(
        id="M9-RECALL",
        ruling="R-M9",
        title="no embedding / vector / similarity / cosine vocabulary and no threshold claim",
        kinds=_ALL_KINDS,
        scan=_scan_recall_vocabulary,
        plants=(
            ("planted.html", "<p>Recalled by cosine similarity over the clause embedding.</p>\n"),
            ("planted.js", "const THETA = 0.35; // similarity threshold\n"),
            ("planted.js", "const label = 'tau = 0.35';\n"),
            ("planted.css", ".vector-plot { display: grid; }\n"),
        ),
        controls=(
            (
                "clean.js",
                (
                    "// The channel is blame ancestry and the counts say what was and was\n"
                    "// not considered; the page prints origin and the five counts.\n"
                    "return fromEnvelope(sources, 'checks', '/checks/0/origin');\n"
                ),
            ),
        ),
    ),
    Rule(
        id="M7-TIMER",
        ruling="R-M7.3",
        title="no timer outside a scope holding a resolved response, and none that gates a request",
        kinds=_JS_ONLY,
        scan=_scan_timers,
        plants=(
            ("planted.js", "setTimeout(() => paintBeat(2), 600);\n"),
            (
                "planted.js",
                (
                    "function stagger(list) {\n  let n = 0;\n"
                    "  setInterval(() => paint(list[n++]), 400);\n}\n"
                ),
            ),
            (
                "planted.js",
                (
                    "async function run() {\n  await sleep(900);\n"
                    "  const response = await fetch(url);\n"
                    "  paint(await response.json());\n}\n"
                ),
            ),
            # Inside a resolved scope, but the callback issues the request: still forbidden,
            # because the timer is then part of the number on screen.
            (
                "planted.js",
                (
                    "async function run() {\n"
                    "  const response = await fetch(url);\n"
                    "  const body = await response.text();\n"
                    "  setTimeout(() => fetch(next), 500);\n}\n"
                ),
            ),
            # The lexer is load-bearing: a comment and a string that merely CONTAIN the
            # characters of a resolution buy the timer nothing, because both are blanked
            # before the rule reads the file.
            (
                "planted.js",
                (
                    "// resolved with .then((body) => paint(body))\n"
                    "const NOTE = 'await fetch(url)';\n"
                    "setTimeout(() => paintBeat(3), 700);\n"
                ),
            ),
            # A resolution in a SIBLING function is not this scope's resolution.
            (
                "planted.js",
                (
                    "async function load(url) {\n"
                    "  const response = await fetch(url);\n"
                    "  return response.json();\n}\n"
                    "function stagger() {\n  setTimeout(() => paintBeat(1), 300);\n}\n"
                ),
            ),
        ),
        controls=(
            # The shape memory-loop.js actually has: one timer, lexically inside the scope
            # that already holds the parsed body, ordering the painting of values that all
            # arrived together.
            (
                "clean.js",
                (
                    "async function runGateOnce() {\n"
                    "  const response = await fetch(url, { method: 'POST' });\n"
                    "  const text = await response.text();\n"
                    "  const body = JSON.parse(text);\n"
                    "  const reveal = (ordinal) => {\n"
                    "    paintGroup(ordinal);\n"
                    "    if (ordinal < body.data.beats.length) {\n"
                    "      setTimeout(() => reveal(ordinal + 1), step);\n"
                    "    }\n"
                    "  };\n"
                    "  reveal(1);\n"
                    "}\n"
                ),
            ),
            # A timer in a `.then` handler is equally inside a resolved scope.
            (
                "clean.js",
                (
                    "fetchIt().then((body) => {\n"
                    "  const next = () => { setTimeout(next, 100); };\n"
                    "  next();\n"
                    "});\n"
                ),
            ),
            # Comments and strings that merely NAME a timer are prose, not a timer.
            (
                "clean.js",
                (
                    "// No setTimeout runs before the response has resolved.\n"
                    "const NOTE = 'no setInterval(' + 'gates a request';\n"
                ),
            ),
        ),
    ),
)


def rules_for(kind: str) -> list[Rule]:
    return [rule for rule in RULES if kind in rule.kinds]


# ── The audit ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AuditResult:
    scanned: list[Path] = field(default_factory=list)
    exempted: list[Path] = field(default_factory=list)
    missing: list[Path] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def audit_paths(paths: Iterable[Path]) -> AuditResult:
    """Run every applicable rule over every non-exempt path."""
    result = AuditResult()
    for path in paths:
        if _is_exempt(path):
            result.exempted.append(path)
            continue
        if not path.is_file():
            result.missing.append(path)
            continue
        views = load_views(path)
        result.scanned.append(path)
        for rule in rules_for(views.kind):
            result.findings.extend(rule.scan(views))
    result.findings.sort(key=lambda f: (f.path.as_posix(), f.line, f.column, f.rule))
    return result


def collect_targets(root: Path) -> list[Path]:
    return [root / target for target in TARGET_PATHS]


# ── The falsification ─────────────────────────────────────────────────────────────────────


def _scan_sample(name: str, source: str, rule: Rule) -> list[Finding]:
    """Run one rule against an in-memory sample. Nothing is written to disk."""
    path = Path(name)
    views = load_views(path, text=source)
    if views.kind not in rule.kinds:
        return []
    return rule.scan(views)


def _falsify_rule(rule: Rule, stream) -> bool:
    """Watch one rule go red on every plant and stay green on every control."""
    if not rule.plants:
        print(f"  FAIL [{rule.id}] declares no planted violation", file=stream)
        return False
    ok = True
    for index, (name, source) in enumerate(rule.plants, start=1):
        findings = _scan_sample(name, source, rule)
        if findings:
            print(
                f"  red  [{rule.id}] plant {index} fired at line {findings[0].line} "
                f"({len(findings)} finding(s))",
                file=stream,
            )
            continue
        print(
            f"  FAIL [{rule.id}] plant {index} ({name}) did NOT fire - "
            f"the rule cannot catch what it exists to catch:\n"
            f"        {source.strip().splitlines()[0][:90]}",
            file=stream,
        )
        ok = False
    for index, (name, source) in enumerate(rule.controls, start=1):
        findings = _scan_sample(name, source, rule)
        if not findings:
            print(f"  green[{rule.id}] control {index} stayed green", file=stream)
            continue
        print(
            f"  FAIL [{rule.id}] control {index} ({name}) went red on honest source:\n"
            f"        {findings[0].excerpt}",
            file=stream,
        )
        ok = False
    return ok


def _prove_exemption(stream) -> bool:
    """Prove the capture exemption, rather than asserting it.

    The same bytes are dishonest in the page and honest in a capture, and the only difference
    is where they live. This walks the same door a caller uses, so an exemption that works only
    inside `_is_exempt` and not inside `audit_paths` is caught here.
    """
    ok = True
    captured = Path("verticals/mainline/apps/console/fixtures/memory-loop/blocking-checks.json")
    page = Path("verticals/mainline/apps/console/public/memory-loop.js")
    if _is_exempt(captured):
        print("  skip fixtures/memory-loop is exempt and is reported as unscanned", file=stream)
    else:
        print(f"  FAIL the capture directory is not exempt: {captured.as_posix()}", file=stream)
        ok = False
    if _is_exempt(page):
        print(f"  FAIL the page source was treated as exempt: {page.as_posix()}", file=stream)
        ok = False
    result = audit_paths([captured, page.parent / "does-not-exist.js"])
    if captured not in result.exempted:
        print("  FAIL audit_paths did not exempt a captured fixture", file=stream)
        ok = False
    if result.findings:
        print("  FAIL audit_paths produced findings for an exempt path", file=stream)
        ok = False
    return ok


def self_test(stream) -> bool:
    """Plant every violation, watch every rule go red, then prove the clean controls stay green.

    Returns True when the suite passed. A rule whose plant does not fire is reported by id and
    by the sample that failed to trip it, because "the guard is green" and "the guard is dead"
    look identical from outside.
    """
    print("falsification suite - every rule is watched failing before it is trusted", file=stream)
    # Every rule is exercised even after one has failed: a suite that stops at the first dead
    # guard tells you about one guard, and the question is how many are dead.
    ok = True
    for rule in RULES:
        if not _falsify_rule(rule, stream):
            ok = False
    if not _prove_exemption(stream):
        ok = False
    print(
        "  self-test OK - every rule fired on its plant and stayed silent on its control"
        if ok
        else "  self-test FAILED",
        file=stream,
    )
    return ok


# ── CLI ───────────────────────────────────────────────────────────────────────────────────


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _report(result: AuditResult, root: Path, stream) -> int:
    """Print what was scanned, what was exempt, what was missing, and every finding."""
    print("memory panel honesty audit", file=stream)
    for path in result.scanned:
        try:
            shown = path.relative_to(root).as_posix()
        except ValueError:
            shown = path.as_posix()
        print(f"  scanned  {shown}", file=stream)
    for path in result.exempted:
        print(f"  exempt   {path.as_posix()}  (captured evidence or build output)", file=stream)
    for path in result.missing:
        print(f"  MISSING  {path.as_posix()}", file=stream)

    exit_code = EXIT_OK
    if result.missing:
        # A target that is not on disk is not a pass. The page is four files; a page missing
        # one of them is a page nobody has audited.
        print(
            "\nFAIL: a target file is missing. This program audits what /memory.html ships; "
            "an absent file is an unaudited one, not an honest one.",
            file=stream,
        )
        exit_code = EXIT_FINDINGS

    if result.findings:
        print(f"\n{len(result.findings)} finding(s):\n", file=stream)
        for finding in result.findings:
            print(finding.render(root), file=stream)
        print(
            "\nFAIL: the page source carries a value it did not have to be given. "
            "Every figure on this panel arrives in one of five responses; fix the source, "
            "never the guard.",
            file=stream,
        )
        exit_code = EXIT_FINDINGS
    elif not result.missing:
        print(
            f"\nPASS: {len(result.scanned)} file(s), {len(RULES)} rules, no findings.",
            file=stream,
        )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_memory_panel_honesty.py",
        description=(
            "Static honesty audit over the four files that make /memory.html. Runs the "
            "falsification suite as well unless told not to."
        ),
    )
    parser.add_argument("--root", type=Path, default=_default_root(), help="repository root")
    parser.add_argument("--check", nargs="+", type=Path, default=None, help="audit these files")
    parser.add_argument("--audit-only", action="store_true", help="skip the falsification suite")
    parser.add_argument("--self-test", action="store_true", help="run only the falsification suite")
    parser.add_argument("--list-rules", action="store_true", help="print the rule table and exit")
    args = parser.parse_args(argv)

    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        # A Windows console defaults to cp1252 and would raise on the em dash in a matched
        # excerpt. A guard that crashes while reporting a finding reports nothing.
        with contextlib.suppress(ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if args.list_rules:
        for rule in RULES:
            print(f"{rule.id:10s} {rule.ruling:8s} {rule.title}", file=stream)
            print(f"{'':10s} {'':8s} applies to: {', '.join(sorted(rule.kinds))}", file=stream)
        return EXIT_OK

    if args.self_test:
        return EXIT_OK if self_test(stream) else EXIT_FINDINGS

    root: Path = args.root.resolve()
    paths = [p if p.is_absolute() else (root / p) for p in (args.check or [])]
    if not paths:
        paths = collect_targets(root)

    result = audit_paths(paths)
    exit_code = _report(result, root, stream)

    if not args.audit_only:
        print("", file=stream)
        if not self_test(stream):
            exit_code = EXIT_FINDINGS

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
