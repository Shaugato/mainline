# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The refusal vocabulary of the blame resolver.

Every name below is a *refusal*, not a bug report. The product's deliverable is a
refusal, so the words this package uses for the conditions it refuses on are a product
surface: they appear in operator messages, in the silence ledger's ``arithmetic``, and
in the console's ancestry ribbon.

Two of these deserve reading before the code:

* :class:`BlameClosureAbsent` — principle P3, fail closed on missing evidence. The
  absence of a closure row is not "no ancestry"; it is "we do not know the ancestry",
  and those must never look alike. The SQL side raises the same sentence from
  ``fn_check_project``; this is its Python twin, for the callers that resolve a pointer
  outside a gate transaction.
* :class:`InferenceActivated` — the DDL's ``inference_never_blocks`` CHECK, restated in
  Python. It is deliberate duplication: the constraint is the enforcement, and this is
  the assertion that catches a *read* of a row that should not exist, on the day
  somebody drops the constraint. A projection is enforced, never trusted, and that
  applies to our own reads of it too.
"""

from __future__ import annotations

__all__ = [
    "AncestryUnresolvable",
    "BlameClosureAbsent",
    "CartographerError",
    "ClosureInconsistent",
    "ClosureMismatch",
    "FloatInEvidentiaryPayload",
    "InferenceActivated",
    "QuoteAmbiguous",
    "QuoteUnbound",
    "StaleClosure",
]


class CartographerError(Exception):
    """Base class for every refusal this package raises."""


class BlameClosureAbsent(CartographerError):
    """No ``clause_blame_closure`` row exists for this clause version.

    P3: absence of a blame-closure row resolves toward the block. A caller that treats
    this as "no ancestry" has converted a missing record into a clean bill of health.
    """

    #: The sentence the SQL side raises, kept byte-identical so a log grep finds both.
    SQL_MESSAGE = "MAINLINE: no blame closure for this clause version — cannot arm a check"

    def __init__(self, clause_uuid: str, as_of_commit: str) -> None:
        """Name the clause version whose closure is missing."""
        self.clause_uuid = clause_uuid
        self.as_of_commit = as_of_commit
        super().__init__(
            f"{self.SQL_MESSAGE} (clause_uuid={clause_uuid}, as_of_commit={as_of_commit})"
        )


class ClosureMismatch(CartographerError):
    """The closure row handed in does not belong to the clause version asked about."""

    def __init__(self, expected: tuple[str, str], found: tuple[str, str]) -> None:
        """Name both keys, because the caller wired the wrong row in."""
        self.expected = expected
        self.found = found
        super().__init__(
            f"closure row is for (clause_uuid={found[0]}, as_of_commit={found[1]}) but the "
            f"pointer being resolved is (clause_uuid={expected[0]}, as_of_commit={expected[1]})"
        )


class ClosureInconsistent(CartographerError):
    """The closure row disagrees with itself."""

    def __init__(self, clause_uuid: str, detail: str) -> None:
        """Name the clause and what disagreed."""
        self.clause_uuid = clause_uuid
        self.detail = detail
        super().__init__(f"closure for clause {clause_uuid} is internally inconsistent: {detail}")


class AncestryUnresolvable(CartographerError):
    """An ancestor event id in the closure has no event row.

    The blame pointer is the product. A pointer that does not resolve is a precursor we
    cannot show a signer, and an unshowable precursor blocks rather than disappears.
    """

    def __init__(self, clause_uuid: str, missing: tuple[str, ...]) -> None:
        """Name the clause and every ancestor that did not resolve."""
        self.clause_uuid = clause_uuid
        self.missing = missing
        super().__init__(
            f"blame ancestry of clause {clause_uuid} names {len(missing)} event(s) with no "
            f"resolvable row: {list(missing)}. A blame pointer that does not resolve is "
            f"missing evidence, and missing evidence resolves toward the block (P3)."
        )


class StaleClosure(CartographerError):
    """The projected ``max_severity`` is below a severity observed in the ancestry.

    This is the one direction that is unsafe. Over-banding fails safe and is reported as
    a flag; under-banding would let the gate demand a weaker clearance than the ancestry
    justifies, which is the whole failure this system exists to prevent.
    """

    def __init__(self, clause_uuid: str, projected: int, observed: int, event_id: str) -> None:
        """Name the clause, both numbers and the event that exceeded the projection."""
        self.clause_uuid = clause_uuid
        self.projected = projected
        self.observed = observed
        self.event_id = event_id
        super().__init__(
            f"closure for clause {clause_uuid} projects max_severity={projected} but ancestor "
            f"event {event_id} carries severity_gate={observed}. The closure is stale or was "
            f"computed from a different edge set; refusing to resolve a pointer that would "
            f"under-band the gate."
        )


class InferenceActivated(CartographerError):
    """An ``inferred_semantic`` blame edge was seen, or built, in a state other than provisional.

    The DDL constraint ``inference_never_blocks`` makes this impossible to store. This
    exception fires when it is nonetheless *read* or *constructed*, which is the case
    that survives a dropped constraint.
    """

    def __init__(self, detail: str) -> None:
        """State what was seen or attempted."""
        self.detail = detail
        super().__init__(
            f"{detail}. An inferred link is a claim about the past; making it block converts "
            f"every model error into a rubber stamp (ARCHITECTURE.md §5.4, constraint "
            f"inference_never_blocks)."
        )


class QuoteUnbound(CartographerError):
    """A model-supplied quote does not occur verbatim in the text it claims to come from."""

    def __init__(self, where: str, quote: str) -> None:
        """Name the text that was searched and the quote that was not in it."""
        self.where = where
        self.quote = quote
        super().__init__(
            f"quote does not occur in {where}: {quote[:120]!r}. We compute offsets by exact "
            f"search and never trust a model-reported offset; an unbindable quote is discarded."
        )


class QuoteAmbiguous(CartographerError):
    """A model-supplied quote occurs more than once, so the span it names is not determined."""

    def __init__(self, where: str, quote: str, occurrences: int) -> None:
        """Name the text, the quote and how many times it occurred."""
        self.where = where
        self.quote = quote
        self.occurrences = occurrences
        super().__init__(
            f"quote occurs {occurrences} times in {where}: {quote[:120]!r}. An evidence span "
            f"that could be either of two places is not an evidence span."
        )


class FloatInEvidentiaryPayload(CartographerError):
    """A float reached a payload that gets hashed.

    IEEE-754 has no stable byte form across serialisers, so a hash over a payload
    containing one is not a commitment to anything (ADR 0042).
    """

    def __init__(self, path: str) -> None:
        """Name the JSON path at which the float was found."""
        self.path = path
        super().__init__(
            f"float found at {path} in a payload that is hashed into the record. Use integer "
            f"milli-units: IEEE-754 has no stable byte form (ADR 0042)."
        )
