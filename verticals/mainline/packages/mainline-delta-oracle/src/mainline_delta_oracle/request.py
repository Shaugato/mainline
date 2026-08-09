# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What crosses the model boundary, and the two things this package adds to it.

``mainline_domain.contracts.OracleRequest`` is frozen by worker W1 and carries
text and tuples only — no identifiers, no site context, no commit ids — because
P7 keeps the thing on the other side of the boundary starved of anything it could
use to decide a state transition.  That minimal body is the contract, and this
package does not get to widen it.

Two pieces of evidence the brief calls for are nevertheless not in it: the
**blame-origin event summary** (research §6.3: Path B is given both texts, the
origin summary and the CAT diff) and the **source digest** of the document the
text was extracted from.  Both are additive and neither is an identifier, so they
travel on a subclass declared here.  :class:`DeltaOracleRequest` *is an*
``OracleRequest``: the ``DeltaOracle`` protocol is satisfied either way, and a
caller who has no origin summary passes the plain contract type and loses
nothing but a paragraph of context.

**What the origin summary may not contain, and why it is a type rather than a
string.**  ``severity`` is on :class:`OriginContext` so it is visibly *carried*,
not asked for: MI14 says a model-rated severity never arms the gate, so severity
reaches the model as a stated fact about an incident and never comes back.
Nothing here carries an event id, a person, a permit or a commit — the model is
told *what happened and how bad it was*, which is what makes the comparison
meaningful, and nothing it could use to address the record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

from mainline_domain.contracts import OracleRequest

__all__ = [
    "MAX_ORIGIN_SUMMARY_CHARS",
    "DeltaOracleRequest",
    "OriginContext",
    "origin_of",
    "source_digest_of",
    "text_pair_digest",
]

#: A blame-origin summary longer than this is a document, not a summary, and a
#: document in this slot is an unbounded prompt-injection surface for no gain.
MAX_ORIGIN_SUMMARY_CHARS: Final[int] = 2000

#: The coded severity scale (ARCHITECTURE.md §8.4).  Named rather than inlined so
#: that the bound in the refusal message and the bound in the comparison are one
#: fact, not two that can drift.
_MAX_CODED_SEVERITY: Final[int] = 5

_SEPARATOR: Final[bytes] = b"\x1f"


@dataclass(frozen=True, slots=True)
class OriginContext:
    """The incident that wrote the ancestor clause, as prose plus a coded severity."""

    event_summary: str
    severity: int
    occurred_on: str = ""

    def __post_init__(self) -> None:
        """Bound the summary and refuse a severity outside the coded scale."""
        if not 0 <= self.severity <= _MAX_CODED_SEVERITY:
            raise ValueError(
                f"severity {self.severity} is outside the coded 0..5 scale. Severity "
                f"comes from a coded field, a regulator classification or a signed "
                f"human (ARCHITECTURE.md §8.4); it is never inferred, least of all here."
            )
        if len(self.event_summary) > MAX_ORIGIN_SUMMARY_CHARS:
            raise ValueError(
                f"blame-origin summary is {len(self.event_summary)} characters, over the "
                f"{MAX_ORIGIN_SUMMARY_CHARS} limit. A summary that long is the incident "
                f"report itself, and pasting a report into a prompt is an unbounded "
                f"injection surface."
            )


@dataclass(frozen=True, slots=True)
class DeltaOracleRequest(OracleRequest):
    """An ``OracleRequest`` plus the origin summary and the source digest."""

    origin: OriginContext | None = None
    #: SHA-256 (hex) of the **source document bytes** the descendant text came
    #: from, out of the custody preamble.  Empty when the caller does not hold it,
    #: in which case :func:`text_pair_digest` stands in — see its docstring for
    #: exactly what that substitution does and does not claim.
    source_sha256: str = ""


def text_pair_digest(ancestor_text: str, descendant_text: str) -> str:
    """Compute a stand-in source digest from the two canonical texts.

    ``UntrustedText.source_sha256`` exists so a claim about a model call can be
    tied back to an Object-Locked object.  When the caller holds that digest it
    passes it and this function is not used.  When it does not, this is what goes
    on the wire, and it claims something strictly weaker and still true: *these
    exact two canonical texts were the input*.  It is not a document digest and
    must never be reported as one.
    """
    digest = hashlib.sha256()
    for part in (ancestor_text, descendant_text):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(_SEPARATOR)
    return digest.hexdigest()


def source_digest_of(request: OracleRequest) -> str:
    """Return the digest to stamp on the untrusted block for ``request``."""
    if isinstance(request, DeltaOracleRequest) and request.source_sha256:
        return request.source_sha256
    return text_pair_digest(request.ancestor_text, request.descendant_text)


def origin_of(request: OracleRequest) -> OriginContext | None:
    """Return the blame-origin context, when the caller supplied one."""
    return request.origin if isinstance(request, DeltaOracleRequest) else None
