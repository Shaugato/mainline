# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Building the one block of text Path B is allowed to see.

Everything in the block is document-derived and therefore **untrusted**: the two
canonical clause texts, the blame-origin summary that came out of an incident
report, and a diff computed from tuples extracted from both.  All of it goes into
a single ``UntrustedText``, which agentkit puts inside a per-request random
sentinel in a user turn — never in a system block, which is layer 1 of the
injection posture and is asserted by agentkit rather than promised here.

**The leakage guard runs on the shipped path, not in a test.**  Every block is
checked for the two vocabularies Path B must never receive:

* a ``rule_id`` (``R1_DEONTIC`` … ``R9_COVERAGE``).  A model that can name a rule
  id can emit something shaped like a Path-A witness, and the value of running
  two paths is precisely that neither can forge the other;
* the ``safe_direction`` registry, in any spelling.  DIRECTRIX decides which way
  a setpoint move is dangerous; a model told the answer would hand it straight
  back, and the second opinion would be an echo.

A guard that only runs under pytest runs against a different string than the one
that ships, so :func:`build_untrusted_text` calls it on every build and raises.
A clause whose *own text* contains one of these tokens therefore fails loudly.
That is the correct direction: the alternative is stripping it silently, and a
silent strip is an edit to evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import UntrustedText
from mainline_domain.contracts import RULE_IDS

from .catdiff import render_cat_diff
from .errors import DeltaOracleError
from .request import origin_of, source_digest_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mainline_domain.contracts import OracleRequest

__all__ = [
    "FORBIDDEN_TOKENS",
    "TRUSTED_CONTEXT",
    "PathALeakage",
    "assert_no_path_a_leakage",
    "build_untrusted_text",
    "render_block",
]


class PathALeakage(DeltaOracleError):
    """The block being sent to the model carries Path-A vocabulary."""


#: Tokens that must never reach Path B, matched case-insensitively.
FORBIDDEN_TOKENS: Final[tuple[str, ...]] = (
    *RULE_IDS,
    "safe_direction",
    "safe-direction",
    "directrix",
)

#: Operator framing.  Constant by design: everything that varies per pair is
#: document-derived and therefore belongs on the untrusted side of the boundary,
#: and a trusted context that varied would put caller-chosen strings into the
#: cassette key for no benefit.
TRUSTED_CONTEXT: Final[Mapping[str, Any]] = {
    "task": "clause_relation",
    "compare": "B_to_A",
    "note": (
        "This is one of two independent paths. The other path is deterministic and "
        "has already produced a verdict you will not be shown. Report only the "
        "relation you observe."
    ),
}

_HEADER_A = "CLAUSE A — the ancestor version"
_HEADER_B = "CLAUSE B — the version under review"
_HEADER_ORIGIN = "BLAME ORIGIN — the recorded incident that wrote clause A"
_HEADER_DIFF = "CONTROL TUPLE DIFF — extracted deterministically, for orientation only"
_HEADER_PARAMETER = "PARAMETER UNDER REVIEW"


def assert_no_path_a_leakage(text: str) -> None:
    """Refuse a block carrying rule ids or the safe-direction registry.

    Raises:
        PathALeakage: naming every offending token, because the diagnosis is the
            deliverable.
    """
    lowered = text.lower()
    offending = sorted({token for token in FORBIDDEN_TOKENS if token.lower() in lowered})
    if offending:
        raise PathALeakage(
            f"the block bound for Path B contains Path-A vocabulary {offending}. "
            f"The model returns a relation and evidence spans and nothing that can "
            f"masquerade as a lattice witness; the safe_direction registry is worker "
            f"W2's and a model told the answer returns the answer."
        )


def render_block(request: OracleRequest) -> str:
    """Render the untrusted block for one ancestor/descendant pair.

    Deterministic in its input: the same request renders the same bytes on any
    machine, in any process, in any order, which is what makes the cassette key
    stable.
    """
    origin = origin_of(request)
    sections: list[str] = [
        f"{_HEADER_A}\n{request.ancestor_text}",
        f"{_HEADER_B}\n{request.descendant_text}",
    ]
    if origin is not None:
        occurred = f", {origin.occurred_on}" if origin.occurred_on else ""
        sections.append(
            f"{_HEADER_ORIGIN}\ncoded severity {origin.severity}{occurred}\n"
            f"{origin.event_summary}"
        )
    if request.parameter_hint:
        sections.append(f"{_HEADER_PARAMETER}\n{request.parameter_hint}")
    sections.append(
        f"{_HEADER_DIFF}\n{render_cat_diff(request.ancestor_cat, request.descendant_cat)}"
    )
    return "\n\n".join(sections)


def build_untrusted_text(request: OracleRequest) -> UntrustedText:
    """Render the block and wrap it in agentkit's untrusted-text type.

    Raises:
        PathALeakage: when the rendered block carries Path-A vocabulary.
    """
    block = render_block(request)
    assert_no_path_a_leakage(block)
    return UntrustedText(
        text=block,
        source_sha256=source_digest_of(request),
        media_type="text/plain",
    )
