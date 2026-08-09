# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
r"""The attestation emitter.

**An LLM ops report is evidence that a review occurred, not evidence of a condition.**

That sentence is bound into this module's docstring, into
``verticals/mainline/apps/steward/runbooks/steward-operations.md`` and into this
distribution's ``README.md``; ``tests/integration/steward/test_evidence_sentence.py``
greps all three. It is repeated because it is the *only* claim a Steward run supports,
and every design decision below exists to make the weaker claim checkable:

* **The model does not produce the evidence.** The emitter runs the contracted reads
  itself, through :class:`mainline_mcp.client.Client`, and hashes the rows. The Claude
  Code session that consumed the CockroachDB Agent Skills produces *narrative*, attached
  to a finding whose statement and result hash were computed without it. A reader who
  distrusts the narrative entirely still has the SQL and 32 bytes to re-run it against.

* **The outcome reports run completeness, never a condition.** ``outcome`` is
  ``'verified'`` when every contracted read answered, ``'indeterminate'`` when one did
  not, and ``'failed'`` when the run could not be assembled. It is never derived from
  what the rows *said*. A Steward that wrote ``'failed'`` because it disliked a number
  would be rating a condition, which is the thing it has no authority to do.

* **One write, and it is bound in a type.** :meth:`Emitter.emit` calls
  ``Client.insert_external_attestation``, which has no parameter naming a table.
  ``tests/integration/steward/test_no_other_write_path.py`` walks this distribution's AST
  and fails if a second write path — a driver import, a ``probe_insert_rows_unbound``
  import, a second MCP write verb — ever appears.

**What the row carries, and why that shape.** ``mainline_meas.external_attestation`` is
five columns of claim plus a digest (``ARCHITECTURE.md`` §5.7):
``attestor``, ``attestor_kind``, ``subject_kind``, ``subject_ref``, ``outcome``,
``detail_sha256``. The full ``ops_attestation`` payload — identity, skills, findings,
statements, hashes — does not fit in a 10 KiB MCP response envelope and does not belong
in a column. So the payload is written beside the run as JSON, canonicalised under
RFC 8785, and its **leaf hash** (``SHA-256(0x00 ‖ canon_bytes)``, RFC 6962 §2.1 leaf
domain separation, exactly as ``mainline.ledger_intake`` computes it) is what
``detail_sha256`` commits to. The row is the commitment; the file is the detail; the
occurrence key is in ``subject_ref``.

**Two things about this path are unverified from this machine and are marked in the
code, not only here.** No MCP service-account key exists in this build (``VERIFY.md``),
so (a) whether ``insert_rows`` accepts a ``BYTES`` column as a ``\\x``-prefixed hex
string, and (b) whether it fires server-side triggers (``GT-09``), are both untested
against the live surface. (a) is isolated in :class:`BytesEncoding`, one enum with two
members, changed in one place — the same reasoning that put ``ToolDialect`` in
``mainline_mcp``. (b) is safe under either answer: ``external_attestation`` is
trigger-free by construction (risk AR-5).
"""

from __future__ import annotations

import hashlib
from base64 import b64encode
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

from mainline_mcp.client import Client
from mainline_mcp.limits import EXTERNAL_ATTESTATION_TABLE, MCP_ENDPOINT, McpClientError

from trappoint_jcs import CANON_VERSION, CanonicalisationError, canonicalise_payload

from .digest import sha256_hex
from .errors import AttestationRefused
from .findings import EVIDENCE_OF_REVIEW, Finding, FindingOutcome
from .identity import AgentIdentity
from .schedule import Occurrence
from .skills import MaterialisedSkill

__all__ = [
    "ATTESTATION_KIND",
    "ATTESTOR_KIND",
    "ENTRY_KIND",
    "LEAF_PREFIX",
    "SUBJECT_KIND",
    "AttestationRow",
    "BytesEncoding",
    "Emitter",
    "OpsAttestation",
    "RunOutcome",
    "build_attestation",
]

ENTRY_KIND: Final = "ops_attestation"
"""``mainline.ledger_intake.entry_kind`` for a Steward run (§8.3, §9.4)."""

ATTESTATION_KIND: Final = "ops_attestation"
"""Carried inside the payload as well, so the file is self-describing on its own."""

ATTESTOR_KIND: Final = "auditor"
"""One of the five values ``external_attestation.attestor_kind`` permits (§5.7)."""

SUBJECT_KIND: Final = "view_result"
"""One of the three values ``external_attestation.subject_kind`` permits.

Chosen with a stated reservation: the vocabulary has ``checkpoint``,
``exhibit_opening`` and ``view_result``, and none of them means "a scheduled ops review".
``view_result`` is the closest true statement — every finding in a run *is* the result of
reading a contracted view or a Cloud API page — and it is used rather than inventing a
value the ``CHECK`` would reject. Adding an ``ops_review`` member to that constraint is
recorded as a cross-domain note for the migration that creates the table.
"""

LEAF_PREFIX: Final = b"\x00"
"""RFC 6962 §2.1 leaf domain separation. The same byte ``ledger_intake.leaf_hash`` uses."""

_ATTESTOR: Final = "mainline-steward"
_PAYLOAD_SPEC_VERSION: Final = 1
_SUBJECT_REF_MAX = 512


class RunOutcome(StrEnum):
    """The three values ``external_attestation.outcome`` permits, and what they mean here.

    Read the meanings carefully, because the column's names invite the wrong reading:

    * ``VERIFIED`` — every contracted read answered and the attestation was assembled.
      **It is not a statement that the cluster is healthy.**
    * ``INDETERMINATE`` — at least one contracted read did not answer, so the review has
      a hole in it and the reader must not treat the remaining findings as coverage.
    * ``FAILED`` — the run could not be assembled at all.
    """

    VERIFIED = "verified"
    INDETERMINATE = "indeterminate"
    FAILED = "failed"


_OUTCOME_MEANS: Final[dict[RunOutcome, str]] = {
    RunOutcome.VERIFIED: (
        "every contracted read answered and the attestation was assembled; this is NOT a "
        "statement that the cluster is healthy"
    ),
    RunOutcome.INDETERMINATE: (
        "at least one contracted read did not answer, so the review has a hole in it and "
        "the remaining findings are not coverage"
    ),
    RunOutcome.FAILED: "the run could not be assembled",
}
"""What each ``outcome`` value means here, carried in the payload so a reader need not guess."""


class BytesEncoding(StrEnum):
    r"""How a ``BYTES`` column is rendered in an ``insert_rows`` JSON row.

    ``HEX_ESCAPE`` (``\x<hex>``) is CockroachDB's text-format literal for ``BYTES`` and
    is the default. ``BASE64`` is the alternative some JSON ingest paths take. Which one
    the Managed MCP ``insert_rows`` verb accepts was not verifiable from this machine, so
    it is one enum in one place rather than a string spelled inline — the same reasoning
    that isolated ``mainline_mcp.client.ToolDialect``.
    """

    HEX_ESCAPE = "hex_escape"
    BASE64 = "base64"

    def render(self, raw: bytes) -> str:
        """Render ``raw`` for a JSON row value."""
        if self is BytesEncoding.BASE64:
            return b64encode(raw).decode("ascii")
        return "\\x" + raw.hex()


@dataclass(frozen=True, slots=True)
class AttestationRow:
    """The single row this package is permitted to write, and nothing else."""

    attestor: str
    attestor_kind: str
    subject_kind: str
    subject_ref: str
    outcome: str
    detail_sha256: str

    def as_mapping(self) -> dict[str, Any]:
        """Return the row in the shape ``insert_rows`` takes."""
        return {
            "attestor": self.attestor,
            "attestor_kind": self.attestor_kind,
            "subject_kind": self.subject_kind,
            "subject_ref": self.subject_ref,
            "outcome": self.outcome,
            "detail_sha256": self.detail_sha256,
        }


@dataclass(frozen=True, slots=True)
class OpsAttestation:
    """One run's complete, canonicalised, hashed record."""

    payload: Mapping[str, Any]
    canon_bytes: bytes
    payload_ver: int
    leaf_hash: bytes
    occurrence_key: str
    outcome: RunOutcome

    @property
    def leaf_hash_hex(self) -> str:
        """``detail_sha256`` as lowercase hex."""
        return self.leaf_hash.hex()

    @property
    def canon_sha256(self) -> str:
        """SHA-256 of the canonical bytes *without* the leaf prefix.

        Recorded beside the leaf hash because the two are easy to confuse and a verifier
        that compares the wrong one reports a discrepancy that is not there.
        """
        return sha256_hex(self.canon_bytes)

    def row(self, *, encoding: BytesEncoding = BytesEncoding.HEX_ESCAPE) -> AttestationRow:
        """Build the one permitted row from this attestation."""
        subject_ref = f"{ENTRY_KIND}:{self.occurrence_key}"
        if len(subject_ref) > _SUBJECT_REF_MAX:
            raise AttestationRefused(f"subject_ref is {len(subject_ref)} characters")
        return AttestationRow(
            attestor=_ATTESTOR,
            attestor_kind=ATTESTOR_KIND,
            subject_kind=SUBJECT_KIND,
            subject_ref=subject_ref,
            outcome=str(self.outcome),
            detail_sha256=encoding.render(self.leaf_hash),
        )

    def write_detail(self, path: Path) -> Path:
        """Write the canonical bytes to ``path``. These bytes are what ``detail_sha256`` commits to.

        The **canonical** bytes are written, not a re-serialisation: a reader must be able
        to hash the file they were handed and get the recorded digest, and a pretty-printed
        copy would hash to something else and look like tampering.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.canon_bytes)
        return path


def _outcome_for(findings: Sequence[Finding]) -> RunOutcome:
    """Derive the run outcome from read completeness only. Never from what a row said."""
    if not findings:
        return RunOutcome.FAILED
    if any(f.outcome is FindingOutcome.UNANSWERED for f in findings):
        return RunOutcome.INDETERMINATE
    if any(f.result_sha256 is None for f in findings):
        return RunOutcome.INDETERMINATE
    return RunOutcome.VERIFIED


def build_attestation(
    *,
    occurrence: Occurrence,
    identity: AgentIdentity,
    site_code: str,
    mcp_cluster_id: str,
    skills: Sequence[MaterialisedSkill],
    findings: Sequence[Finding],
    runtime: Mapping[str, Any],
    started_at: datetime,
    finished_at: datetime,
) -> OpsAttestation:
    """Assemble, canonicalise and hash one ``ops_attestation``.

    Args:
        occurrence: the schedule and the instant it was delivered for.
        identity: the resolved ``agent_identity`` and its seven inputs in clear.
        site_code: the ledger partition this run belongs to.
        mcp_cluster_id: the cluster the ``mcp-cluster-id`` header pinned.
        skills: the consumed skills, with the digest actually computed over each.
        findings: the reads, each with its statement and its result hash.
        runtime: the Claude Code session facts — version, allowed tools, transcript digest.
        started_at: when the run began. Timezone-aware, always.
        finished_at: when it finished.

    Returns:
        The attestation, ready to write and to commit to.

    Raises:
        AttestationRefused: the payload will not canonicalise. The commonest cause is a
            float reaching an evidentiary payload (CU-5), and it is a refusal rather than
            a coercion because a silently rounded quantity in a record somebody later
            relies on is the defect this repository exists to make impossible.
    """
    if started_at.tzinfo is None or finished_at.tzinfo is None:
        raise AttestationRefused(
            "attestation timestamps must be timezone-aware; a naive instant in an "
            "evidentiary payload is an unanswerable question in cross-examination"
        )
    outcome = _outcome_for(findings)
    payload: dict[str, Any] = {
        "attestation_kind": ATTESTATION_KIND,
        "spec_version": _PAYLOAD_SPEC_VERSION,
        "disclaimer": EVIDENCE_OF_REVIEW,
        "run": {
            "schedule_id": occurrence.schedule.schedule_id,
            "schedule_kind": str(occurrence.schedule.kind),
            "schedule_expression": occurrence.schedule.expression,
            "occurrence_ts": occurrence.occurrence_ts,
            "occurrence_key": occurrence.key,
            "site_code": site_code,
            "started_at": _instant(started_at),
            "finished_at": _instant(finished_at),
            "outcome": str(outcome),
            "outcome_means": _OUTCOME_MEANS[outcome],
        },
        "identity": identity.to_payload(),
        "mcp": {
            "mcp_cluster_id": mcp_cluster_id,
            "mcp_endpoint": MCP_ENDPOINT,
            "write_surface": EXTERNAL_ATTESTATION_TABLE,
        },
        "runtime": dict(runtime),
        "skills": [skill.to_payload() for skill in skills],
        "findings": [finding.to_payload() for finding in findings],
    }
    try:
        canon = canonicalise_payload(payload)
    except CanonicalisationError as exc:
        raise AttestationRefused(
            f"the ops_attestation payload will not canonicalise: {exc}"
        ) from exc
    leaf = hashlib.sha256(LEAF_PREFIX + canon).digest()
    return OpsAttestation(
        payload=payload,
        canon_bytes=canon,
        payload_ver=CANON_VERSION,
        leaf_hash=leaf,
        occurrence_key=occurrence.key,
        outcome=outcome,
    )


def _instant(moment: datetime) -> str:
    """Render a timezone-aware datetime as a second-resolution UTC instant."""
    return moment.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class Emitter:
    """Writes the one permitted row. There is no second method, and no second target.

    An LLM ops report is evidence that a review occurred, not evidence of a condition —
    so what this class publishes is a commitment to a review's record, never an assertion
    about the cluster.
    """

    def __init__(
        self,
        client: Client,
        *,
        encoding: BytesEncoding = BytesEncoding.HEX_ESCAPE,
        dry_run: bool = False,
    ) -> None:
        """Bind the MCP client.

        Args:
            client: the Managed-MCP client. Its ``insert_external_attestation`` is the
                only write this distribution can express.
            encoding: how the ``BYTES`` digest is rendered in the JSON row.
            dry_run: build the row and do not send it. The default for every offline
                lane, because ``insert_rows`` is a real append to a real evidentiary
                table and a test run is not a reason to add a row to one.
        """
        self._client = client
        self._encoding = encoding
        self._dry_run = dry_run
        self._last_row: AttestationRow | None = None

    @property
    def dry_run(self) -> bool:
        """Whether this emitter will actually send."""
        return self._dry_run

    @property
    def last_row(self) -> AttestationRow | None:
        """The most recent row built, sent or not. Read by the CLI's report."""
        return self._last_row

    def emit(self, attestation: OpsAttestation) -> AttestationRow:
        """Write one row committing to ``attestation``.

        Returns:
            The row, whether or not it was sent.

        Raises:
            AttestationRefused: the surface rejected the write. Raised rather than logged:
                a run whose attestation did not land has not been attested, and reporting
                success would be the precise failure this package exists to prevent.
        """
        row = attestation.row(encoding=self._encoding)
        self._last_row = row
        if self._dry_run:
            return row
        try:
            result = self._client.insert_external_attestation([row.as_mapping()])
        except McpClientError as exc:
            raise AttestationRefused(f"the attestation write was refused: {exc}") from exc
        if result.is_error:
            raise AttestationRefused(
                f"the attestation write returned an error result: {result.text[:400]}"
            )
        return row
