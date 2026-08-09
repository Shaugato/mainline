# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A finding: the exact statement, the hash of what came back, and nobody's opinion.

**An LLM ops report is evidence that a review occurred, not evidence of a condition.**
That sentence is why this module is shaped the way it is, and the shape is the argument:

* ``statement`` is **generated, never authored**. A finding is built either from a
  contracted :class:`~mainline_mcp.catalogue.ViewSpec` — whose statement is
  ``SELECT * FROM <view> LIMIT <cap>``, produced by the contract and not by a caller — or
  from a :class:`~mainline_steward.ccloud.CcloudPage`, whose command this package
  assembled from typed methods. There is no constructor that takes free text, so no
  sentence a model produced can become the SQL an attestation says was run.

* ``result_sha256`` is taken over the **RFC 8785 canonical bytes of the returned rows**,
  before any summarising. A reader re-runs the statement, canonicalises the rows and
  compares 32 bytes. That is the whole checkability claim, and it does not depend on the
  narrative being true, or on the narrative existing at all.

* **There is no severity field, and there will not be one.** §8.4 is explicit that
  severity comes from a coded field, a regulator classification or a signed human — *a
  model-rated severity never arms the gate*. A Steward finding that carried a severity
  would be exactly that, one refactor away from being read as one.

* ``narrative`` is the model's prose, held in a field that is named as prose, beside the
  SQL and the hash that do not depend on it. It may be ``None``; a run with no narrative
  is a poorer report and an equally sound attestation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final

from mainline_mcp.auditor import Completeness
from mainline_mcp.catalogue import ViewSpec

from trappoint_jcs import canonicalise

from .ccloud import CcloudPage
from .digest import sha256_hex

__all__ = [
    "EVIDENCE_OF_REVIEW",
    "Finding",
    "FindingOutcome",
    "FindingSource",
    "completeness_of",
    "result_digest",
    "sentence",
]

EVIDENCE_OF_REVIEW: Final = (
    "an LLM ops report is evidence that a review occurred, not evidence of a condition"
)
"""The sentence bound into the runbook, the README and the emitter, and CI-grepped.

It is a constant rather than a comment so that the string in the code and the string in
the prose are the same object, and so a test can assert the payload carries it.
"""

_FINDING_ID_HEX: Final = 16


def sentence(text: str) -> str:
    """Return ``text`` as a sentence: first letter raised, the rest untouched.

    ``str.capitalize`` lower-cases everything after the first character, which turns
    "an LLM ops report" into "an llm ops report". The disclaimer is a quoted sentence and
    it has to read like one wherever it is printed.
    """
    return text[:1].upper() + text[1:] + "."


class FindingSource(StrEnum):
    """Where a finding's statement came from. Two sources, both generated."""

    MCP_VIEW = "mcp_view"
    CCLOUD = "ccloud"


class FindingOutcome(StrEnum):
    """Whether the read answered.

    ``ANSWERED`` says the surface returned something we could hash. It says nothing about
    whether what came back is good news, and no code in this package draws that
    inference.
    """

    ANSWERED = "answered"
    UNANSWERED = "unanswered"


def result_digest(rows: Sequence[Mapping[str, Any]] | None) -> str | None:
    """Return the SHA-256 of the RFC 8785 canonical bytes of ``rows``, or ``None``.

    ``canonicalise`` rather than ``canonicalise_payload``: an ops view legitimately
    returns ratios (``restart_ratio``, ``not_checked_ratio``) and those arrive as IEEE-754
    doubles from the server. The float ban (CU-5) governs what *we* put into an
    evidentiary payload, and it is honoured where it applies — this digest is a hex
    string by the time it reaches the ledger payload, and
    :func:`~mainline_steward.attestation.build_attestation` canonicalises that payload
    with the float-refusing entry point.

    Returns ``None`` when the rows could not be recovered from the response envelope. A
    digest of "we could not tell" would be a stable number attesting to nothing.
    """
    if rows is None:
        return None
    return sha256_hex(canonicalise([dict(row) for row in rows]))


def completeness_of(
    view: ViewSpec, rows: Sequence[Mapping[str, Any]] | None
) -> tuple[Completeness, int]:
    """Decide the completeness state of a view read and count the truncated rows.

    Deliberately re-stated here rather than reaching into ``mainline_mcp.auditor``'s
    private helper: this is a four-line rule, and importing another package's underscore
    name to save four lines would make this package's behaviour depend on a name that
    package is free to change.
    """
    if rows is None:
        return Completeness.UNKNOWN, 0
    if view.truncation_flag is None:
        return Completeness.NO_FLAG, 0
    flag = view.truncation_flag
    if any(flag not in row for row in rows):
        return Completeness.FLAG_MISSING, 0
    incomplete = sum(1 for row in rows if row.get(flag) is False)
    if incomplete:
        return Completeness.INCOMPLETE, incomplete
    return Completeness.COMPLETE, 0


@dataclass(frozen=True, slots=True)
class Finding:
    """One read: what was asked, what came back, how big it was, and what it hashed to."""

    finding_id: str
    source: FindingSource
    subject: str
    statement: str
    outcome: FindingOutcome
    row_count: int | None
    result_sha256: str | None
    response_bytes: int
    completeness: str
    incomplete_rows: int
    elapsed_ms: int
    skill_id: str | None
    detail: str
    narrative: str | None = None

    @classmethod
    def from_view_read(
        cls,
        *,
        view: ViewSpec,
        rows: Sequence[Mapping[str, Any]] | None,
        response_bytes: int,
        elapsed_ms: float,
        skill_id: str | None,
        detail: str = "",
    ) -> Finding:
        """Build a finding from a contracted view read. The statement comes from the contract."""
        completeness, incomplete = completeness_of(view, rows)
        digest = result_digest(rows)
        return cls(
            finding_id=_finding_id(FindingSource.MCP_VIEW, view.qualified, view.statement),
            source=FindingSource.MCP_VIEW,
            subject=view.qualified,
            statement=view.statement,
            outcome=FindingOutcome.ANSWERED,
            row_count=None if rows is None else len(rows),
            result_sha256=digest,
            response_bytes=response_bytes,
            completeness=str(completeness),
            incomplete_rows=incomplete,
            elapsed_ms=round(elapsed_ms),
            skill_id=skill_id,
            detail=detail,
        )

    @classmethod
    def unanswered_view(
        cls, *, view: ViewSpec, detail: str, skill_id: str | None, elapsed_ms: float = 0.0
    ) -> Finding:
        """Build a finding for a read that would not answer.

        Recorded rather than raised. Which of the contracted reads failed is itself an
        operational fact, and dropping it would make a partial reading indistinguishable
        from a clean one — which is the exact substitution this product refuses.
        """
        return cls(
            finding_id=_finding_id(FindingSource.MCP_VIEW, view.qualified, view.statement),
            source=FindingSource.MCP_VIEW,
            subject=view.qualified,
            statement=view.statement,
            outcome=FindingOutcome.UNANSWERED,
            row_count=None,
            result_sha256=None,
            response_bytes=0,
            completeness=str(Completeness.UNKNOWN),
            incomplete_rows=0,
            elapsed_ms=round(elapsed_ms),
            skill_id=skill_id,
            detail=detail,
        )

    @classmethod
    def from_ccloud_page(cls, page: CcloudPage, *, skill_id: str | None = None) -> Finding:
        """Build a finding from a ``ccloud`` page. The command is the statement."""
        return cls(
            finding_id=_finding_id(FindingSource.CCLOUD, page.source, page.command),
            source=FindingSource.CCLOUD,
            subject=page.source,
            statement=page.command,
            outcome=FindingOutcome.ANSWERED,
            row_count=None,
            result_sha256=page.page_sha256,
            response_bytes=len(page.canon_bytes),
            completeness=str(Completeness.NO_FLAG),
            incomplete_rows=0,
            elapsed_ms=0,
            skill_id=skill_id,
            detail="the Cloud API page, RFC 8785 canonicalised before hashing",
        )

    def with_narrative(self, narrative: str | None) -> Finding:
        """Return a copy carrying the model's prose.

        The only mutator on this type, and it can reach exactly one field. ``statement``
        and ``result_sha256`` are unreachable from anything a model produced, which is
        the property that makes the finding checkable independently of the narrative.
        """
        text = (narrative or "").strip()
        return replace(self, narrative=text or None)

    def to_payload(self) -> dict[str, Any]:
        """Return the attestation fragment for this finding."""
        return {
            "finding_id": self.finding_id,
            "source": str(self.source),
            "subject": self.subject,
            "statement": self.statement,
            "outcome": str(self.outcome),
            "row_count": self.row_count,
            "result_sha256": self.result_sha256,
            "response_bytes": self.response_bytes,
            "completeness": self.completeness,
            "incomplete_rows": self.incomplete_rows,
            "elapsed_ms": self.elapsed_ms,
            "skill_id": self.skill_id,
            "detail": self.detail,
            "narrative": self.narrative,
            "narrative_is_not_evidence": True,
        }

    def render(self) -> str:
        """One human-readable block, with the statement and the hash always present."""
        lines = [
            f"[{self.finding_id}] {self.subject}  ({self.outcome})",
            f"  statement : {self.statement}",
            f"  result    : rows={self.row_count} sha256={self.result_sha256}",
            (
                f"  size      : {self.response_bytes} bytes in {self.elapsed_ms} ms"
                f"   completeness={self.completeness}"
            ),
        ]
        if self.detail:
            lines.append(f"  detail    : {self.detail}")
        if self.narrative:
            lines.append(f"  narrative : {self.narrative}")
            lines.append(f"  ({EVIDENCE_OF_REVIEW})")  # prose, beside a hash that ignores it
        return "\n".join(lines)


def _finding_id(source: FindingSource, subject: str, statement: str) -> str:
    """Return a deterministic id: the same read produces the same id, forever.

    Not a random UUID. Two runs of the same schedule against the same view must produce
    findings a reader can line up without a join table, and a random id would make the
    diff between last night's report and tonight's a manual exercise.
    """
    return sha256_hex(f"{source}\x1f{subject}\x1f{statement}".encode())[:_FINDING_ID_HEX]
