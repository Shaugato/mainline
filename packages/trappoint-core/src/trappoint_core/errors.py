# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal taxonomy, as types — and how the exhibit is recovered from a driver.

``spec/errors.md`` is normative and this module is its executable form. Four expectation
classes, one retryable code, and a closed set of modelled codes:

===========  ==========================================  ==========================
Class        SQLSTATE                                    This module
===========  ==========================================  ==========================
RETRY        ``40001``                                   handled by :mod:`.retry`
REFUSE       ``23514`` ``23503`` ``23505`` ``P0001``     :class:`GateRefused`
DENY         ``42501``                                   :class:`AuthorisationDenied`
(unmodelled) anything else                               :class:`UnmodelledRefusal`
===========  ==========================================  ==========================

**The exhibit is the deliverable, not the SQLSTATE.** A caller that learns only that
"an exception was raised" has learned nothing a product built on refusals can sell, so
every :class:`GateRefused` carries a ``constraint`` — the constraint or unique-index
name for the three constraint-backed codes, and the fully-qualified name of the raising
object for ``P0001``.

Recovering that name for ``P0001`` is where this module earns its keep, and the reason
is a measurement rather than a preference. On CockroachDB CCL v26.2.5 through psycopg
3.3.4, a PL/pgSQL ``RAISE`` arrives with:

* ``diag.constraint_name`` — ``None``. Expected: ``spec/errors.md`` §3.1 says so.
* ``diag.context`` — ``None``. **Not** expected: PostgreSQL populates a PL/pgSQL context
  stack naming the function and line, and CockroachDB does not.
* ``diag.source_function`` — ``'func397'``, a CockroachDB Go internal. Names nothing.

So the driver cannot supply the raising object on this platform, and ``spec/errors.md``
§2.5 requires the *message* to make it recoverable. The kernel's SQL templates therefore
emit every refusal as::

    <PREFIX>: merge refused by <schema>.<object> — <what and why>

and :func:`diagnose` reads the object out of it. That is a channel the substrate
controls, not a guess. When only the prefix can be recovered the diagnosis is reported
as **weakened**, logged at ``WARNING``, and carried on the exception — so a run whose
exhibits were inferred is never indistinguishable from a run whose exhibits were
reported (``spec/errors.md`` §3.2).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "DENIED_SQLSTATE",
    "MODELLED_SQLSTATES",
    "REFUSAL_SQLSTATES",
    "RETRYABLE_SQLSTATE",
    "AuthorisationDenied",
    "Diagnosis",
    "GateRefused",
    "RetryBudgetExhausted",
    "TrappointError",
    "UnmodelledRefusal",
    "diagnose",
    "gate_refused",
    "sqlstate_of",
]

logger = logging.getLogger("trappoint_core.errors")

#: The ONLY retryable code. ``spec/errors.md`` §2.1; changing this is a MAJOR bump.
RETRYABLE_SQLSTATE: Final = "40001"

#: The four codes that mean the gate decided *no*. Attempted exactly once, ever (§4).
REFUSAL_SQLSTATES: Final[frozenset[str]] = frozenset({"23514", "23503", "23505", "P0001"})

#: The writer never reached the gate: a missing grant or a row-level-security policy.
#: Never retried and never recorded as a gate refusal — it is a fact about the writer.
DENIED_SQLSTATE: Final = "42501"

#: Total over the gate path. Anything outside this set is a defect (§1.1).
MODELLED_SQLSTATES: Final[frozenset[str]] = REFUSAL_SQLSTATES | {RETRYABLE_SQLSTATE}

# `refused by mainline.fn_permit_merge_gate` -> `mainline.fn_permit_merge_gate`.
# Deliberately narrow: a lower-case, dot-qualified SQL identifier and nothing else, so a
# message that happened to contain the words cannot smuggle an arbitrary string into an
# exhibit that ends up in a ledger and in front of a court.
_EXHIBIT_RE: Final = re.compile(r"\brefused by ([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)")

# `MAINLINE: merge refused …` -> `MAINLINE`. The prefix is stable and clients parse it
# (`spec/errors.md` §3.2); the sentence after it is PATCH-mutable and nothing may depend
# on its wording, which is exactly why recovering only the prefix is a WEAKENED result.
_PREFIX_RE: Final = re.compile(r"^([A-Z][A-Z0-9_]*):")


class TrappointError(Exception):
    """Base class for every condition this client raises."""


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """What could be established about one database refusal, and how firmly.

    Attributes:
        sqlstate: the five-character code, verbatim from the driver.
        constraint: the exhibit — a constraint or unique-index name, or the
            fully-qualified name of the raising object for ``P0001``. Empty only when
            nothing at all could be recovered.
        message: the primary message, verbatim. Never edited: it is written to the
            refusal ledger and read in a console.
        weakened: the exhibit was inferred rather than reported. ``spec/errors.md``
            §3.2 requires this to be visible.
    """

    sqlstate: str
    constraint: str
    message: str
    weakened: bool


class GateRefused(TrappointError):
    """The gate decided *no*, and this is the decision with its exhibit attached.

    Raised for ``23514``, ``23503``, ``23505`` and ``P0001``, and for nothing else.
    **Never** raised for ``40001``: an undecided transaction is not a refusal and has no
    reason set (``spec/errors.md`` §5).
    """

    def __init__(
        self,
        sqlstate: str,
        constraint: str,
        message: str,
        subject_kind: str | None = None,
        subject_id: str | None = None,
        gate_epoch: int | None = None,
        *,
        weakened: bool = False,
    ) -> None:
        """Build a refusal.

        Args:
            sqlstate: one of :data:`REFUSAL_SQLSTATES`.
            constraint: the exhibit name.
            message: the database's own message, unedited.
            subject_kind: ``"permit"``/``"change_request"`` where known.
            subject_id: the subject the transition was attempted on.
            gate_epoch: the epoch read at the start of the attempt, where known. The
                epoch at refusal time is what makes a refusal payload reproducible.
            weakened: the exhibit was inferred rather than reported.
        """
        super().__init__(
            f"{sqlstate} {constraint}: {message}" if constraint else f"{sqlstate}: {message}"
        )
        self.sqlstate = sqlstate
        self.constraint = constraint
        self.message = message
        self.subject_kind = subject_kind
        self.subject_id = subject_id
        self.gate_epoch = gate_epoch
        self.weakened = weakened

    def as_dict(self) -> dict[str, Any]:
        """Return the fields ``spec/wire/refusal.md`` requires of every refusal payload.

        The minimal-unsatisfiable-subset and nearest-admissible-alternative fields are
        deliberately absent: they are computed by ``trappoint-diagnose`` against the
        database, and inventing them here would let the explanation disagree with the
        refusal.
        """
        return {
            "sqlstate": self.sqlstate,
            "constraint": self.constraint,
            "message": self.message,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "gate_epoch": self.gate_epoch,
            "weakened": self.weakened,
        }


class UnmodelledRefusal(TrappointError):
    """The database refused for a reason nobody modelled.

    Not a subclass of :class:`GateRefused`, and that is load-bearing: a caller that
    catches ``GateRefused`` is handling a decision the gate made, and an unmodelled code
    is the opposite — evidence that the taxonomy is no longer total over the gate path.
    ``spec/errors.md`` §1.1 makes any such code a suite failure rather than an edge case.
    """

    def __init__(self, sqlstate: str, message: str) -> None:
        """Build an unmodelled refusal from the code and message that produced it."""
        super().__init__(
            f"{sqlstate}: {message} — outside the refusal taxonomy "
            f"{sorted(MODELLED_SQLSTATES)}; the database refused for a reason nobody modelled"
        )
        self.sqlstate = sqlstate
        self.message = message


class AuthorisationDenied(TrappointError):
    """``42501``: the writer never reached the gate.

    Excluded from the taxonomy by definition rather than by exception — no gate
    condition was ever evaluated — and never recorded as a gate refusal, because
    emitting a reason set for it would leak the shape of rows the writer is not entitled
    to read (``spec/errors.md`` §5).
    """

    def __init__(self, message: str) -> None:
        """Build a denial from the driver's message."""
        super().__init__(f"{DENIED_SQLSTATE}: {message}")
        self.sqlstate = DENIED_SQLSTATE
        self.message = message


class RetryBudgetExhausted(TrappointError):
    """``40001`` survived the whole budget: the transaction is still undecided.

    Deliberately NOT a :class:`GateRefused`. A budget exhausted without a decision is a
    distinct condition and must not be represented as a refusal, because it is not one
    (``spec/errors.md`` §5) — the gate never said no, it never got to say anything.
    """

    def __init__(self, attempts: int, elapsed_s: float) -> None:
        """Build an exhaustion from the attempt count and the wall time spent."""
        super().__init__(
            f"{RETRYABLE_SQLSTATE} after {attempts} attempt(s) in {elapsed_s:.3f}s: the "
            "transaction is undecided, not refused"
        )
        self.attempts = attempts
        self.elapsed_s = elapsed_s


def sqlstate_of(exc: BaseException) -> str | None:
    """Return the SQLSTATE carried by *exc*, or ``None`` if it carries none.

    Reads the attribute rather than importing psycopg's exception hierarchy, so the
    function works on the driver's classes, on a subclass, and on a test double —
    without this module needing to know which of those it was handed.
    """
    state = getattr(exc, "sqlstate", None)
    return state if isinstance(state, str) and state else None


def _diag_field(exc: BaseException, name: str) -> str:
    diag = getattr(exc, "diag", None)
    value = getattr(diag, name, None) if diag is not None else None
    return value if isinstance(value, str) else ""


def diagnose(exc: BaseException) -> Diagnosis:
    """Establish the SQLSTATE, the exhibit and how firmly the exhibit is known.

    Three tiers, in order, and the order is the whole content of the function:

    1. ``diag.constraint_name`` — reported by the database. Not weakened.
    2. the ``refused by <schema>.<object>`` clause the kernel's own ``RAISE`` emits.
       Not weakened: the substrate controls that text and ``spec/errors.md`` §2.5
       requires it, because on CockroachDB v26.2.5 there is no other channel — measured,
       see the module docstring.
    3. the message prefix alone. **Weakened**, and logged as such.

    Args:
        exc: any exception carrying ``sqlstate``/``diag``, typically a ``psycopg.Error``.

    Returns:
        The diagnosis. ``sqlstate`` is ``""`` when the exception carries none, which the
        caller must treat as unmodelled rather than as a refusal.
    """
    sqlstate = sqlstate_of(exc) or ""
    message = _diag_field(exc, "message_primary") or str(exc)

    reported = _diag_field(exc, "constraint_name")
    if reported:
        return Diagnosis(sqlstate=sqlstate, constraint=reported, message=message, weakened=False)

    named = _EXHIBIT_RE.search(message)
    if named is not None:
        return Diagnosis(
            sqlstate=sqlstate, constraint=named.group(1), message=message, weakened=False
        )

    prefix = _PREFIX_RE.match(message)
    exhibit = prefix.group(1) if prefix is not None else ""
    logger.warning(
        "weakened diagnosis: %s carries no constraint_name and no `refused by <object>` "
        "clause; the exhibit was inferred as %r from the message prefix. spec/errors.md "
        "§3.2 — a run whose exhibits were inferred must never look like a run whose "
        "exhibits were reported.",
        sqlstate or "(no sqlstate)",
        exhibit,
    )
    return Diagnosis(sqlstate=sqlstate, constraint=exhibit, message=message, weakened=True)


def gate_refused(
    exc: BaseException,
    *,
    subject_kind: str | None = None,
    subject_id: str | None = None,
    gate_epoch: int | None = None,
) -> GateRefused:
    """Build a :class:`GateRefused` from a driver exception and the subject it concerned.

    Raises:
        ValueError: *exc* does not carry one of :data:`REFUSAL_SQLSTATES`. Constructing a
            refusal from a code that is not a refusal is the error this guard exists to
            make impossible; the caller should have raised
            :class:`UnmodelledRefusal` instead.
    """
    found = diagnose(exc)
    if found.sqlstate not in REFUSAL_SQLSTATES:
        raise ValueError(
            f"{found.sqlstate or '(no sqlstate)'} is not a refusal code; "
            f"expected one of {sorted(REFUSAL_SQLSTATES)}"
        )
    return GateRefused(
        found.sqlstate,
        found.constraint,
        found.message,
        subject_kind,
        subject_id,
        gate_epoch,
        weakened=found.weakened,
    )
