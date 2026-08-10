# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A driver exception, turned into the wire refusal payload — with nothing added.

``spec/wire/refusal.md`` and ``spec/wire/refusal.schema.json`` govern the payload; this
module is the one place in the demo API that produces one, and it produces it from two
sources and no third:

1. **The driver's error object** — the SQLSTATE, the constraint name, the message. Read,
   never composed. :func:`diagnose` is the working reference from
   ``scripts/proof/gate_refusal.py`` (``_constraint`` / ``_message``) with the one field
   that file names but does not model added: ``constraint_source``.
2. **``trappoint.explain_refusal``** — the minimal unsatisfiable subset and the nearest
   admissible alternative, computed by the SAME engine that produced the refusal
   (migration ``0119a``). The API does not decompose refusals. If it did, the explanation
   could disagree with the refusal, and an explanation that can disagree with its refusal
   is worse than no explanation.

THE THREE THINGS THIS MODULE REFUSES TO DO
------------------------------------------

**It never composes a message.** ``message`` is ``diag.message_primary`` verbatim, or
``str(exc)`` when the driver supplies no primary. Truncation to the contract's 2048
characters is the only edit, and it is applied to the tail.

**It never infers an exhibit it cannot justify.** ``constraint_source`` is ``reported``
when ``diag.constraint_name`` carried it and ``parsed`` when it was recovered from the
kernel's own ``refused by <schema>.<object>`` clause — the channel ``spec/errors.md`` §2.5
requires precisely because, measured on CockroachDB v26.2.5 through psycopg 3.3.4, a
PL/pgSQL ``RAISE`` arrives with ``constraint_name``, ``context`` and ``source_function``
all useless (see ``trappoint_core.errors``). Every ``P0001`` therefore lands in the parsed
case, and the console renders parsed as the weaker diagnosis it is. When neither channel
yields a name the diagnosis is ``absent`` and the caller **must not** claim a refusal: a
refusal with no exhibit is not evidence, and the contract's ``minLength: 1`` on
``constraint`` says so in a form a validator can enforce.

**It never treats ``40001`` as a refusal.** An undecided transaction has no reason set
(``spec/errors.md`` §5). :func:`classify` returns ``retry`` and the caller decides. There
is no retry helper in this package and there will not be one — a helper that re-sends a
merge because a socket closed is a helper that can issue a permit twice.

SAFE INSIDE AN OPEN TRANSACTION
-------------------------------
:func:`refusal_payload` calls a PL/pgSQL function that can itself ``RAISE`` — by design:
``0119a`` refuses to emit a plausible reason set when the counter it would decompose has
already drifted. A raise inside the caller's transaction would abort it, so the call is
wrapped in its own ``SAVEPOINT``. That is what makes this module usable from
:mod:`mainline_demo_api.gate_run`, which must keep one transaction alive across four
beats.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import psycopg

__all__ = [
    "DENIED_SQLSTATE",
    "MAX_MESSAGE_CHARS",
    "REFUSAL_SQLSTATES",
    "RETRYABLE_SQLSTATE",
    "SPEC_VERSION",
    "Diagnosis",
    "classify",
    "diagnose",
    "refusal_payload",
    "rfc3339",
]

#: The four codes that mean the gate decided *no*. ``spec/errors.md`` §2.1, and the same
#: closed set the wire contract's ``sqlstate`` enum carries.
REFUSAL_SQLSTATES: Final[frozenset[str]] = frozenset({"23514", "23503", "23505", "P0001"})

#: The ONLY retryable code. Never a refusal.
RETRYABLE_SQLSTATE: Final = "40001"

#: The writer never reached the gate. A fact about the writer, not a gate decision.
DENIED_SQLSTATE: Final = "42501"

#: ``spec/wire/refusal.schema.json`` caps ``message`` here.
MAX_MESSAGE_CHARS: Final = 2048

#: What ``trappoint.explain_refusal`` stamps into every payload it returns. Repeated here
#: only as the fallback for a payload that function could not produce, so the two cannot
#: silently disagree about which specification a refusal claims to satisfy.
SPEC_VERSION: Final = "1.0.0-rc.1"

# `refused by mainline.fn_permit_merge_gate` -> `mainline.fn_permit_merge_gate`.
#
# Deliberately narrow — a lower-case, dot-qualified SQL identifier and nothing else. The
# recovered string becomes an exhibit that is written to a refusal ledger and shown to a
# reader as the name of the thing that refused; a pattern loose enough to capture
# arbitrary text would let a message smuggle a name the database never used. Identical in
# intent to `trappoint_core.errors._EXHIBIT_RE`, and narrower than
# `scripts/proof/gate_refusal.py::_REFUSED_BY`, which admits a bare unqualified word.
_REFUSED_BY: Final = re.compile(r"\brefused by ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)")

#: The contract's own pattern for `constraint`. Applied before the name is used, so a
#: driver that reported something unquotable produces `absent` rather than a payload that
#: fails validation at the console — a failure the console reports as a TAMPERED transport
#: rather than as a defect here.
_EXHIBIT_OK: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$]{0,127}$")


def rfc3339(moment: datetime | None = None) -> str:
    """Return *moment* (default: now) as an RFC 3339 UTC instant, seconds resolution."""
    return (moment or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """What could be established about one database refusal, and how firmly.

    Attributes:
        sqlstate: the five-character code, verbatim from the driver. ``""`` when the
            exception carried none, which the caller must treat as unmodelled.
        constraint: the exhibit — a constraint or unique-index name, or the
            fully-qualified name of the raising object for ``P0001``. ``""`` when neither
            channel yielded one.
        constraint_source: ``reported`` from driver diagnostics, ``parsed`` from the
            message text, ``absent`` when there is no exhibit. The wire contract admits
            only the first two; ``absent`` exists so that "we could not name it" is a
            distinguishable state rather than an empty string in a courtroom exhibit.
        message: the database's own message, unedited apart from the contract's length
            cap.
    """

    sqlstate: str
    constraint: str
    constraint_source: str
    message: str

    @property
    def is_refusal(self) -> bool:
        """True when this is a REFUSE-class outcome that carries a usable exhibit."""
        return self.sqlstate in REFUSAL_SQLSTATES and self.constraint_source != "absent"


def _diag_field(exc: BaseException, name: str) -> str:
    diag = getattr(exc, "diag", None)
    value = getattr(diag, name, None) if diag is not None else None
    return value if isinstance(value, str) else ""


def diagnose(exc: BaseException) -> Diagnosis:
    """Establish the SQLSTATE, the exhibit, how the exhibit was obtained, and the message.

    Two channels, in order, and the order is the whole content of the function:

    1. ``diag.constraint_name`` — the database reported it. ``constraint_source`` is
       ``reported``.
    2. the ``refused by <schema>.<object>`` clause the kernel's own ``RAISE`` emits.
       ``constraint_source`` is ``parsed``.

    There is no third tier. ``trappoint_core.errors.diagnose`` has one — the bare message
    prefix, flagged ``weakened`` — and this module deliberately stops short of it, because
    ``MAINLINE`` is not a constraint name and putting it in the contract's ``constraint``
    field would satisfy the validator while telling the reader nothing.

    Args:
        exc: any exception carrying ``sqlstate`` / ``diag``, typically a ``psycopg.Error``.

    Returns:
        The diagnosis. Never raises.
    """
    sqlstate = getattr(exc, "sqlstate", None)
    sqlstate = sqlstate if isinstance(sqlstate, str) and sqlstate else ""

    message = _diag_field(exc, "message_primary") or str(exc)
    message = " ".join(message.split())[:MAX_MESSAGE_CHARS]

    reported = _diag_field(exc, "constraint_name")
    if reported and _EXHIBIT_OK.match(reported):
        return Diagnosis(sqlstate, reported, "reported", message)

    named = _REFUSED_BY.search(message)
    if named is not None and _EXHIBIT_OK.match(named.group(1)):
        return Diagnosis(sqlstate, named.group(1), "parsed", message)

    return Diagnosis(sqlstate, "", "absent", message)


def classify(diagnosis: Diagnosis) -> str:
    """Return the transition outcome this diagnosis implies.

    ``refused`` — the gate decided no and named the thing that decided it.
    ``retry``    — ``40001``. UNDECIDED, not failed. The caller decides whether to
                   re-attempt; this package never decides for it.
    ``denied``   — ``42501``. The writer never reached the gate.
    ``unmodelled`` — anything else, including a refusal code whose exhibit could not be
                   recovered. ``spec/errors.md`` §1.1 makes this a defect to be reported,
                   not an edge case to be smoothed over.
    """
    if diagnosis.sqlstate == RETRYABLE_SQLSTATE:
        return "retry"
    if diagnosis.sqlstate == DENIED_SQLSTATE:
        return "denied"
    if diagnosis.is_refusal:
        return "refused"
    return "unmodelled"


def _explain(
    conn: psycopg.Connection[Any],
    subject_kind: str,
    subject_id: str,
    constraint: str,
    attempt: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Ask the database to decompose the refusal. Returns ``(payload, why_not)``.

    The call is fenced by its own ``SAVEPOINT``. ``0119a`` raises rather than emit a
    plausible reason set when the counter it would decompose no longer supports one, and
    an unfenced raise here would abort a transaction that must survive — :mod:`gate_run`
    keeps one open across four beats and this function is called inside it three times.
    """
    from psycopg.types.json import Jsonb  # local: keeps module import cost off cold start

    conn.execute("SAVEPOINT trappoint_explain")
    try:
        row = conn.execute(
            "SELECT trappoint.explain_refusal(%s, %s, %s, %s)",
            (subject_kind, subject_id, constraint, Jsonb(attempt) if attempt else None),
        ).fetchone()
    except psycopg.Error as exc:
        conn.execute("ROLLBACK TO SAVEPOINT trappoint_explain")
        conn.execute("RELEASE SAVEPOINT trappoint_explain")
        return None, " ".join(str(exc).split())[:512]
    conn.execute("RELEASE SAVEPOINT trappoint_explain")
    return (row[0] if row and isinstance(row[0], dict) else None), None


def refusal_payload(
    conn: psycopg.Connection[Any],
    diagnosis: Diagnosis,
    *,
    subject_kind: str,
    subject_id: str,
    gate_epoch: int,
    attempt: dict[str, Any] | None = None,
    observed_at: str | None = None,
    refusal_id: str | None = None,
) -> dict[str, Any]:
    """Build the ``spec/wire/refusal.schema.json`` payload for *diagnosis*.

    Args:
        conn: a live connection in a usable transaction state. If the caller has just
            taken an error, it must have rolled back (to a savepoint or wholly) first —
            a connection in the aborted state cannot answer, and this function does not
            paper over that.
        diagnosis: from :func:`diagnose`. Must satisfy ``is_refusal``.
        subject_kind: ``permit`` or ``change_request``.
        subject_id: the gated subject the transition was attempted on.
        gate_epoch: the epoch read at the start of the attempt. Used only when the
            database declines to state one; ``explain_refusal`` reads it from the row and
            its answer wins, because the row is authoritative and the caller's copy is a
            memory of a read.
        attempt: what the database cannot know because the attempt was rolled back — the
            verdict kind tried, the check it was tried against, the epoch the completion
            carried. Optional; the three-argument diagnosis is legal and degrades to the
            parts the rows can still prove.
        observed_at: RFC 3339 instant. Defaults to now.
        refusal_id: an identifier for THIS OBSERVATION of the refusal. Minted here when
            absent. It is deliberately not a ``mainline.refusal_ledger`` primary key: the
            demo's gate run rolls back, so a ledger row would not survive the response
            that referenced it, and a payload naming a row nobody can fetch would be a
            worse lie than a payload naming an observation.

    Returns:
        A dict satisfying the refusal contract.

    Raises:
        ValueError: *diagnosis* is not a refusal, or carries no exhibit. Building a
            refusal payload out of something that is not a refusal is the error this
            guard exists to make impossible.
    """
    if not diagnosis.is_refusal:
        raise ValueError(
            f"{diagnosis.sqlstate or '(no sqlstate)'}/{diagnosis.constraint_source} is not a "
            f"refusal with an exhibit; expected one of {sorted(REFUSAL_SQLSTATES)} carrying a "
            "constraint name. A refusal with no exhibit is not evidence."
        )

    explained, why_not = _explain(conn, subject_kind, subject_id, diagnosis.constraint, attempt)

    if explained is None:
        # HONEST INCOMPLETENESS, in the shape the contract provides for it. `diagnosis:
        # none` says the reason set is a candidate and not a proven minimal one, and
        # `naa_reason: not_computable` says no alternative was computed. Emitting a
        # confident-looking `declarative` here would be the single failure invariant I14
        # exists to prevent.
        detail = (
            "trappoint.explain_refusal did not produce a decomposition for this exhibit"
            + (f": {why_not}" if why_not else "")
        )
        explained = {
            "spec_version": SPEC_VERSION,
            "profile": "mainline",
            "class": "gate",
            "constraint": diagnosis.constraint,
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "gate_epoch": gate_epoch,
            "diagnosis": "none",
            "probe_calls": 0,
            "mus": [
                {
                    "kind": "capability_gap",
                    "capability": diagnosis.constraint[:128],
                    "detail": detail[:512],
                }
            ],
            "naa": None,
            "naa_reason": "not_computable",
        }

    payload: dict[str, Any] = dict(explained)
    payload["refusal_id"] = refusal_id or str(uuid.uuid4())
    payload["observed_at"] = observed_at or rfc3339()
    payload["sqlstate"] = diagnosis.sqlstate
    payload["message"] = diagnosis.message
    payload["constraint_source"] = diagnosis.constraint_source
    # `explain_refusal` reads the epoch from the subject row; a NULL there means it could
    # not, and the caller's read is then the only number anyone has.
    if payload.get("gate_epoch") is None:
        payload["gate_epoch"] = gate_epoch
    if payload.get("naa") is not None:
        payload["naa_reason"] = None
    return payload
