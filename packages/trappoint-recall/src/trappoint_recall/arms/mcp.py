# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Managed-MCP envelope, as arithmetic rather than as a hope.

The public Managed MCP surface accepts **one statement per call**, at most **16 384
characters**, answers within **20 seconds**, and returns at most **10 KiB** — with ``SELECT``
capped at 25 rows by default. Those limits are why the proof of index use is asserted **one
arm per call** over that endpoint, and why the whole ``UNION ALL`` plan is asserted over
pgwire instead: a full arm set's plan does not fit in 10 KiB, and *a silently truncated proof
of index use is exactly the defect this product exists to refuse*.

This module contains no client. Building one is another domain's work, and duplicating it
here would create a second thing to keep correct. What lives here is the part that must be
checkable **without credentials**: whether a generated statement is legal for that envelope,
and how much room is left. A limit tested at 100 % of capacity breaches in front of an
audience the first time the corpus grows, so the check reports headroom as a number and
supports an explicit safety margin.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "MCP_MAX_RESPONSE_BYTES",
    "MCP_MAX_STATEMENT_CHARS",
    "MCP_SELECT_ROW_CAP",
    "MCP_TIMEOUT_SECONDS",
    "EnvelopeCheck",
    "check_envelope",
    "statement_count",
]

#: One statement per call.
MCP_STATEMENTS_PER_CALL: Final = 1
#: Verified surface limit: statement text length.
MCP_MAX_STATEMENT_CHARS: Final = 16_384
#: Verified surface limit: response body size.
MCP_MAX_RESPONSE_BYTES: Final = 10 * 1024
#: Verified surface limit: default `SELECT` row cap.
MCP_SELECT_ROW_CAP: Final = 25
#: Verified surface limit: per-call timeout.
MCP_TIMEOUT_SECONDS: Final = 20

#: Fraction of the statement cap a generated statement should stay within. 80 % leaves room
#: for a dimension bump or an extra projected column to be noticed in CI rather than in
#: production. The check reports both the hard limit and this margin, and never conflates them.
DEFAULT_SAFETY_MARGIN: Final = 0.8

_LINE_COMMENT: Final = re.compile(r"--[^\n]*")
_BLOCK_COMMENT: Final = re.compile(r"/\*.*?\*/", re.DOTALL)


def statement_count(sql: str) -> int:
    """Count top-level statements, ignoring semicolons inside strings and comments.

    A trailing semicolon does not create a second statement. Two real statements do, and that
    is a hard failure on this surface rather than a style preference.
    """
    stripped = _BLOCK_COMMENT.sub(" ", sql)
    stripped = _LINE_COMMENT.sub(" ", stripped)
    count = 0
    in_string = False
    i = 0
    n = len(stripped)
    body_since_semicolon = False
    while i < n:
        ch = stripped[i]
        if in_string:
            if ch == "'":
                if stripped.startswith("''", i):
                    i += 2
                    continue
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            body_since_semicolon = True
            i += 1
            continue
        if ch == ";":
            if body_since_semicolon:
                count += 1
            body_since_semicolon = False
            i += 1
            continue
        if not ch.isspace():
            body_since_semicolon = True
        i += 1
    if body_since_semicolon:
        count += 1
    return count


@dataclass(frozen=True, slots=True)
class EnvelopeCheck:
    """Whether one statement is legal for the Managed MCP surface, and by how much."""

    chars: int
    limit: int
    statements: int
    within_margin: bool
    margin_limit: int
    violations: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def headroom_chars(self) -> int:
        return self.limit - self.chars

    @property
    def utilisation(self) -> float:
        return self.chars / self.limit


def check_envelope(
    sql: str,
    *,
    limit: int = MCP_MAX_STATEMENT_CHARS,
    safety_margin: float = DEFAULT_SAFETY_MARGIN,
) -> EnvelopeCheck:
    """Check one generated statement against the surface's hard limits."""
    if not 0 < safety_margin <= 1:
        raise ValueError(f"safety_margin must be in (0, 1], got {safety_margin}")
    chars = len(sql)
    statements = statement_count(sql)
    margin_limit = int(limit * safety_margin)
    violations: list[str] = []
    if chars > limit:
        violations.append(
            f"statement is {chars} characters, over the {limit}-character cap by "
            f"{chars - limit}. At 1024 dimensions this is what happens when the query "
            "vector is printed twice: render the arm as EXPLAIN_MCP, which prints it once."
        )
    if statements != MCP_STATEMENTS_PER_CALL:
        violations.append(
            f"{statements} statements in one call; the surface accepts exactly "
            f"{MCP_STATEMENTS_PER_CALL}"
        )
    return EnvelopeCheck(
        chars=chars,
        limit=limit,
        statements=statements,
        within_margin=chars <= margin_limit,
        margin_limit=margin_limit,
        violations=tuple(violations),
    )


def check_response_size(
    payload: bytes | str, *, limit: int = MCP_MAX_RESPONSE_BYTES
) -> tuple[int, bool]:
    """Measured response size and whether it fits. Truncation must be detected, not assumed.

    Returns the byte count and whether it is within the cap, so a caller can record the
    number. A proof that fits *today* with two bytes to spare is a proof that will silently
    truncate tomorrow, and the only defence is writing the number down.
    """
    body = payload.encode("utf-8") if isinstance(payload, str) else payload
    return len(body), len(body) <= limit


def worst_case_statement(statements: Sequence[str]) -> str:
    """The longest statement in a set — the one that decides whether the set is shippable."""
    if not statements:
        raise ValueError("no statements to measure")
    return max(statements, key=len)
