# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Statements and parameters. This package never holds a driver or a credential.

Everything here returns a :class:`Statement`; the caller opens the connection, holds
``agent_ingestor``, and owns the transaction boundary. That absence is what
``mainline-boundary``'s E3 SBOM scan reads, and it is why a compromised ingest cannot
write anything the grant matrix does not already permit.

**There is no UPDATE and no DELETE in this module, and no path that could produce one.**
Not by convention — by grant. ``verticals/mainline/db/GRANTS.yaml`` gives ``agent_ingestor``
``INSERT`` on eleven tables and nothing else, so an ``UPDATE mainline.event SET
severity_gate = 5`` would be refused by the database anyway; writing one here would be a
statement that exists only to be refused. :func:`assert_ingest_safe` runs on every
statement this module produces; ``tests/unit/archivist/test_starvation.py`` walks this
module's AST for a string literal that *is* a mutating statement and separately asserts
every **rendered** statement is an ``INSERT`` into a granted table. The day someone adds
one, a test fails rather than production.

**Severity cannot be typed in.** :class:`EventDraft` takes a
:class:`~mainline_archivist.appraise.SeverityAppraisal`, not four integers, so there is no
signature in this package that accepts a hand-written ``severity_gate``. The MI14 ceiling
is upstream of the parameter list rather than beside it.

**Spans are re-read at the write boundary.** Every builder takes ``source_text`` and runs
:func:`~mainline_archivist.verbatim.assert_verbatim` over every span before it becomes a
parameter. A draft assembled by hand with plausible offsets and invented text does not
reach the database. Principle P2 in miniature: the field a downstream reader trusts is
checked against its authority at the moment it is written.

**Placeholders are ``%s``**, matching every other emitter in the vertical
(``mainline_fixity.emit``, ``mainline_recall_agent.taxonomy.sql``), so one driver
convention holds across the repository.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .errors import EventKindNotCoded, SpanNotVerbatim, WriteOutsideGrant
from .verbatim import assert_verbatim

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from .appraise import SeverityAppraisal
    from .verbatim import VerbatimSpan

__all__ = [
    "CONTROL_FAILURE_COLUMNS",
    "EVENT_COLUMNS",
    "INGEST_INSERTABLE_TABLES",
    "INGEST_ROLE",
    "INSERT_CONTROL_FAILURE_SQL",
    "INSERT_EVENT_SQL",
    "SQL_CONSTANTS",
    "ControlFailureDraft",
    "EventDraft",
    "Statement",
    "assert_ingest_safe",
    "insert_control_failure",
    "insert_event",
    "insert_intake_finding",
    "statements_for_findings",
]

#: ``CHECK source_sha256_is_a_digest`` on ``mainline.event``: a SHA-256 is 32 bytes.
SHA256_DIGEST_BYTES: Final[int] = 32

#: The SQL role every statement in this module is written for.
INGEST_ROLE: Final[str] = "agent_ingestor"

#: Exactly the tables ``GRANTS.yaml`` gives ``agent_ingestor`` ``INSERT`` on, transcribed
#: in the order they appear there. :func:`assert_ingest_safe` refuses anything else, so a
#: statement naming a table the role cannot write fails in Python with the grant quoted
#: rather than in the database with a 42501 a caller has to go and look up.
INGEST_INSERTABLE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "mainline.event",
        "mainline.control_failure",
        "mainline.event_cue",
        "mainline.event_cue_embedding",
        "mainline.event_cue_coarse",
        "mainline.event_cue_stage",
        "mainline.lex_posting",
        "mainline.lex_stats",
        "mainline.lex_doclen",
        "mainline.event_bond",
        "mainline.document_intake_finding",
    }
)

#: ``mainline.event``'s insertable columns, in migration 0033's own order. ``event_id``
#: and ``ingested_at`` are omitted deliberately: both have defaults, and a client-supplied
#: ``ingested_at`` is a client-supplied answer to "when did this system learn".
EVENT_COLUMNS: Final[tuple[str, ...]] = (
    "site_id",
    "external_ref",
    "occurred_at",
    "kind",
    "title",
    "narrative",
    "source_doc_id",
    "source_object_key",
    "source_sha256",
    "severity_actual",
    "severity_potential",
    "severity_gate",
    "severity_basis",
    "severity_span",
    "consequence_proxy",
    "cluster_id",
    "canon_version",
)

#: ``mainline.control_failure``'s insertable columns, in migration 0035's order.
CONTROL_FAILURE_COLUMNS: Final[tuple[str, ...]] = (
    "event_id",
    "control_class",
    "barrier_role",
    "failure_mode",
    "icam_tier",
    "hazard_energy",
    "evidence_span",
    "quote_sha256",
)

#: ``CHECK kind_closed`` on ``mainline.event``.
EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {"incident", "near_miss", "regulator_notice", "oem_alert", "audit_finding", "capa"}
)

#: ``CHECK barrier_role_closed``, ``failure_mode_closed``, ``hazard_energy_closed`` and
#: ``icam_tier_closed`` on ``mainline.control_failure``. Mirrored so a vocabulary error is
#: a named refusal here rather than a 23514 naming a constraint at the far end.
BARRIER_ROLES: Final[frozenset[str]] = frozenset({"preventive", "recovery"})
FAILURE_MODES: Final[frozenset[str]] = frozenset(
    {"absent", "ineffective", "bypassed", "degraded", "not_verified"}
)
HAZARD_ENERGIES: Final[frozenset[str]] = frozenset(
    {
        "gravity",
        "pressure",
        "electrical",
        "thermal",
        "chemical",
        "kinetic",
        "biological",
        "radiation",
    }
)
ICAM_TIERS: Final[frozenset[str]] = frozenset(
    {
        "absent_or_failed_defence",
        "individual_or_team_action",
        "task_or_environmental_condition",
        "organisational_factor",
    }
)


def _insert_sql(table: str, columns: Sequence[str], *, tail: str = "") -> str:
    """Render one parameterised INSERT. The only statement constructor in this package.

    Every statement goes through here so that the single place a column name is
    interpolated is one function with one guard, rather than three f-strings a reviewer
    has to check independently.

    Raises:
        ValueError: a column name that is not an identifier, or a table outside the
            grant. Both are refused *before* the string exists: the column list is
            interpolated, and only an identifier may be.
    """
    if table not in INGEST_INSERTABLE_TABLES:
        raise WriteOutsideGrant(
            f"{table} is not one of the eleven tables {INGEST_ROLE} may INSERT into"
        )
    for column in columns:
        if not column.isidentifier():
            raise ValueError(f"column {column!r} is not an identifier")
    placeholders = ", ".join(["%s"] * len(columns))
    # S608: `table` is checked against the grant list above, every column has been checked
    # with `str.isidentifier`, and every VALUE is a %s placeholder. There is no path from a
    # document, a model or a caller into the statement text.
    body = f"INSERT INTO {table} (\n  {', '.join(columns)}\n) VALUES ({placeholders})"  # noqa: S608
    return f"{body}\n{tail}".strip() if tail else body


INSERT_EVENT_SQL: Final[str] = _insert_sql(
    "mainline.event",
    EVENT_COLUMNS,
    # ON CONFLICT … DO NOTHING rather than an upsert: ingestion is at-least-once, and the
    # second delivery of one incident must be a no-op rather than a second version of the
    # record. An upsert here would let a redelivery quietly change a severity.
    tail="ON CONFLICT (site_id, external_ref) DO NOTHING\nRETURNING event_id",
)

INSERT_CONTROL_FAILURE_SQL: Final[str] = _insert_sql(
    "mainline.control_failure", CONTROL_FAILURE_COLUMNS, tail="RETURNING failure_id"
)

#: Every SQL literal this module can emit, for the starvation test's regex. A statement
#: built anywhere else in this package would not be in this tuple, and the test that
#: greps the source for `UPDATE`/`DELETE`/`GRANT` is what makes that observable.
SQL_CONSTANTS: Final[tuple[str, ...]] = (INSERT_EVENT_SQL, INSERT_CONTROL_FAILURE_SQL)

_LEADING_VERB = re.compile(r"^\s*([A-Za-z]+)")
_TABLE_AFTER_INTO = re.compile(r"\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_.]*)", re.IGNORECASE)
_FORBIDDEN_VERBS = re.compile(
    r"\b(UPDATE|DELETE|TRUNCATE|DROP|ALTER|GRANT|REVOKE)\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Statement:
    """One statement and its parameters. This package never holds a driver.

    Returning the SQL and the parameters as data rather than executing them is what keeps
    the SQL role, the connection and the transaction boundary in the caller's hands, where
    the grant matrix can see them.
    """

    sql: str
    params: tuple[Any, ...]
    table: str

    def mentions(self, table: str) -> bool:
        """Whether this statement names ``table``."""
        return table in self.sql


@dataclass(frozen=True, slots=True)
class EventDraft:
    """Everything ``mainline.event`` needs, in the only shapes this package will accept.

    Note what the types forbid. ``title`` and ``narrative`` are
    :class:`~mainline_archivist.verbatim.VerbatimSpan`, so they can only be text that was
    read out of the document. ``severity`` is a
    :class:`~mainline_archivist.appraise.SeverityAppraisal`, so it can only be the output
    of the ceiling arithmetic. ``kind`` is a plain string and is checked against the
    closed vocabulary — a model's triage route cannot reach it, because
    :func:`~mainline_archivist.ingest.ingest_document` never passes one here.

    Attributes:
        occurred_at: when the world changed. Timezone-aware, always: ``event`` is
            bitemporal and a naive timestamp makes ``ingested_before_occurrence``
            meaningless.
        source_object_key: the Object-Locked key the bytes came from.
        source_sha256: 32 raw bytes, computed by :mod:`mainline_archivist.source`.
        canon_version: which canonicalisation produced the extracted text.
    """

    site_id: str
    occurred_at: datetime
    kind: str
    title: VerbatimSpan
    narrative: VerbatimSpan
    source_object_key: str
    source_sha256: bytes
    severity: SeverityAppraisal
    canon_version: int = 1
    external_ref: str | None = None
    source_doc_id: str | None = None
    consequence_proxy: Mapping[str, Any] | None = None
    cluster_id: str | None = None

    def __post_init__(self) -> None:
        """Refuse a draft the table's CHECKs would refuse, naming the sentence not the code.

        Raises:
            EventKindNotCoded: the kind is empty or outside ``CHECK kind_closed``.
            ValueError: a naive ``occurred_at``, an empty object key, or a digest that is
                not 32 bytes.
        """
        if not self.kind:
            raise EventKindNotCoded(
                "an event draft has no kind. event.kind is a closed vocabulary and a "
                "triage route is a pipeline decision, not a classification of the "
                "incident: supply the coded kind or do not write the row."
            )
        if self.kind not in EVENT_KINDS:
            raise EventKindNotCoded(
                f"event kind {self.kind!r} is outside CHECK kind_closed ({sorted(EVENT_KINDS)})"
            )
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "occurred_at is naive. mainline.event is bitemporal and "
                "CHECK ingested_before_occurrence compares it with a timestamptz; a "
                "naive value makes the comparison depend on the server's timezone."
            )
        if not self.source_object_key.strip():
            raise ValueError(
                "source_object_key is empty; CHECK source_object_key_stated refuses it, "
                "and an event whose bytes cannot be found is not evidence"
            )
        if len(self.source_sha256) != SHA256_DIGEST_BYTES:
            raise ValueError(
                f"source_sha256 is {len(self.source_sha256)} bytes; "
                f"CHECK source_sha256_is_a_digest requires 32"
            )
        if self.canon_version < 1:
            raise ValueError("canon_version must be >= 1 (CHECK canon_version_positive)")


@dataclass(frozen=True, slots=True)
class ControlFailureDraft:
    """One barrier that did not hold, with the span of the document that says so.

    ``control_class`` is **the join key to a clause's CAT control class** (migration 0035),
    which is how a control failure in an incident finds the clauses that assert the same
    control. It is a coded value, never a model's phrase; the caller resolves it through
    the algorithms domain's CAT vocabulary.
    """

    event_id: str
    control_class: str
    barrier_role: str
    failure_mode: str
    hazard_energy: str
    evidence: VerbatimSpan
    icam_tier: str | None = None

    def __post_init__(self) -> None:
        """Refuse a draft outside migration 0035's four closed vocabularies."""
        _require_in("barrier_role", self.barrier_role, BARRIER_ROLES)
        _require_in("failure_mode", self.failure_mode, FAILURE_MODES)
        _require_in("hazard_energy", self.hazard_energy, HAZARD_ENERGIES)
        if self.icam_tier is not None:
            _require_in("icam_tier", self.icam_tier, ICAM_TIERS)
        if not self.control_class.strip():
            raise ValueError(
                "control_class is empty; CHECK control_class_stated refuses it, and an "
                "unclassed failure joins to no clause, which makes the row silent"
            )


def insert_event(draft: EventDraft, *, source_text: str) -> Statement:
    """Build the ``mainline.event`` INSERT for ``draft``.

    ``ON CONFLICT (site_id, external_ref) DO NOTHING`` rather than an upsert: ingestion is
    at-least-once (EventBridge redelivery, an operator re-running a batch), and the second
    delivery of one incident must be a no-op rather than a second version of the record.
    An upsert here would let a redelivery quietly change a severity.

    Args:
        draft: the event, with its appraisal.
        source_text: the extracted text every span in the draft indexes. Both spans are
            re-read from it, and any disagreement is a refusal.

    Raises:
        SpanNotVerbatim: a span does not match the source.
        WriteOutsideGrant: unreachable for this statement; the guard runs anyway.
    """
    title = assert_verbatim(draft.title, source_text)
    narrative = assert_verbatim(draft.narrative, source_text)
    severity = draft.severity.to_columns()
    _assert_span_in_text(severity["severity_span"], source_text)

    params: tuple[Any, ...] = (
        draft.site_id,
        draft.external_ref,
        draft.occurred_at,
        draft.kind,
        title.text,
        narrative.text,
        draft.source_doc_id,
        draft.source_object_key,
        draft.source_sha256,
        severity["severity_actual"],
        severity["severity_potential"],
        severity["severity_gate"],
        severity["severity_basis"],
        severity["severity_span"],
        _jsonb(draft.consequence_proxy),
        draft.cluster_id,
        draft.canon_version,
    )
    return assert_ingest_safe(
        Statement(sql=INSERT_EVENT_SQL, params=params, table="mainline.event")
    )


def insert_control_failure(draft: ControlFailureDraft, *, source_text: str) -> Statement:
    """Build the ``mainline.control_failure`` INSERT for ``draft``.

    ``quote_sha256`` is computed from the span's own text rather than accepted, so the
    digest on the row is a digest of the bytes the row points at.

    Raises:
        SpanNotVerbatim: the evidence span does not match the source.
    """
    evidence = assert_verbatim(draft.evidence, source_text)
    params: tuple[Any, ...] = (
        draft.event_id,
        draft.control_class,
        draft.barrier_role,
        draft.failure_mode,
        draft.icam_tier,
        draft.hazard_energy,
        list(evidence.pair),
        evidence.sha256_bytes(),
    )
    return assert_ingest_safe(
        Statement(sql=INSERT_CONTROL_FAILURE_SQL, params=params, table="mainline.control_failure")
    )


def insert_intake_finding(payload: Mapping[str, Any]) -> Statement:
    """Build the ``mainline.document_intake_finding`` INSERT for one quarantine finding.

    The column list is **derived from the payload** rather than declared here, and that is
    a deliberate ownership decision with two halves:

    * ``mainline_quarantine.finding.DocumentIntakeFinding.to_row`` is the single
      authoritative statement of this row's shape — its own docstring says so;
    * the DDL belongs to the data-model domain (``GRANTS.yaml`` line 314 records it as a
      DM-16 orphan: §11.2 grants the INSERT, §5 never defined the table) and **does not
      exist in ``verticals/mainline/db/migrations`` as of 2026-08-09**.

    Declaring a column order here would be this package inventing a table. Deriving it
    means the statement is always exactly the payload quarantine produced, and the day the
    DDL lands the only thing that can disagree is the payload — which is where the
    disagreement belongs.

    Args:
        payload: the mapping ``DocumentIntakeFinding.to_row()`` returns.

    Raises:
        ValueError: the payload is empty or names a column that is not an identifier.
    """
    if not payload:
        raise ValueError(
            "an empty intake-finding payload writes nothing. Layer 6 has no drop path: "
            "a refusal that records nothing turns an attack into a silence."
        )
    columns = tuple(str(key) for key in payload)
    return assert_ingest_safe(
        Statement(
            sql=_insert_sql("mainline.document_intake_finding", columns),
            params=tuple(payload[key] for key in payload),
            table="mainline.document_intake_finding",
        )
    )


def assert_ingest_safe(statement: Statement) -> Statement:
    """Refuse any statement outside ``agent_ingestor``'s eleven INSERTs.

    Three checks, and each one is a different mistake:

    * the leading verb must be ``INSERT`` — the role holds nothing else;
    * no forbidden verb may appear anywhere in the text, which catches a mutating
      statement smuggled into a CTE;
    * the target table must be one the grant matrix lists.

    Raises:
        WriteOutsideGrant: any of the three.
    """
    verb_match = _LEADING_VERB.match(statement.sql)
    verb = verb_match.group(1).upper() if verb_match else ""
    if verb != "INSERT":
        raise WriteOutsideGrant(
            f"statement begins with {verb or '<nothing>'!r}; {INGEST_ROLE} holds INSERT "
            f"and nothing else on eleven tables (verticals/mainline/db/GRANTS.yaml)"
        )
    forbidden = _FORBIDDEN_VERBS.search(statement.sql)
    if forbidden:
        raise WriteOutsideGrant(
            f"statement contains {forbidden.group(1).upper()!r}. There is no UPDATE and "
            f"no DELETE anywhere in the ingest plane: an event is a record of what a "
            f"document said, and a record that can be edited by the process that wrote "
            f"it is not a record."
        )
    named = _TABLE_AFTER_INTO.search(statement.sql)
    target = named.group(1) if named else ""
    if target not in INGEST_INSERTABLE_TABLES:
        raise WriteOutsideGrant(
            f"{target or '<no target>'} is not one of the eleven tables {INGEST_ROLE} may "
            f"INSERT into ({sorted(INGEST_INSERTABLE_TABLES)})"
        )
    if target != statement.table:
        raise WriteOutsideGrant(
            f"statement targets {target} but the Statement declares {statement.table}; a "
            f"declaration that disagrees with the SQL is worse than no declaration"
        )
    return statement


def statements_for_findings(payloads: Sequence[Mapping[str, Any]]) -> tuple[Statement, ...]:
    """Build one INSERT per quarantine finding, in the order the layers produced them."""
    return tuple(insert_intake_finding(payload) for payload in payloads)


def _assert_span_in_text(span: list[int] | None, source_text: str) -> None:
    """Refuse a severity span that does not index the text supplied at write time."""
    if span is None:
        return
    start, end = span
    if start < 0 or end > len(source_text) or end <= start:
        raise SpanNotVerbatim(
            f"severity_span {span} does not index the extracted text of "
            f"{len(source_text)} characters"
        )


def _require_in(name: str, value: str, vocabulary: frozenset[str]) -> None:
    """Refuse a value outside a closed CHECK vocabulary."""
    if value not in vocabulary:
        raise ValueError(f"{name} {value!r} is outside the closed vocabulary {sorted(vocabulary)}")


def _jsonb(value: Mapping[str, Any] | None) -> str | None:
    """Render a JSONB parameter as canonical JSON text, or ``None``.

    Sorted keys and no incidental whitespace: the column is read by
    ``mainline_audit`` views and quoted in refusals, and two ingests of one document
    should produce one string rather than two orderings of it.
    """
    if value is None:
        return None
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
