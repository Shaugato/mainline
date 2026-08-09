# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The differential state machine: every step runs twice and the two answers must match.

This is the answer to the oracle problem. Nobody can write down, in advance, what the
right refusal is for the four-thousandth step of a generated history — but two
independent implementations can be compared, and a disagreement is a bug in one of them
without anyone having to say which in advance.

The comparison is on the **verdict**, which is ``(sqlstate, constraint)`` and not just
"refused". A model that predicted only refusal would agree with a gate that refused
everything for the wrong reason, and the constraint name is the courtroom exhibit.

Between steps, :func:`~trappoint_model.invariants.check_all` runs against the cluster.
That is deliberately *between steps* rather than at the end: an invariant that broke at
step 7 and was repaired by step 40 is a gate that was open for thirty-three steps.

**What this machine cannot see**, said here rather than in a footnote:

* It is single-threaded, so it explores the *sequential* state space only. Interleavings
  live in :mod:`~trappoint_model.scheduler`, and the concurrency lane in
  ``tests/concurrency/`` fires the real parallel merges. A state machine that never ran
  two transactions at once has said nothing about what happens when two do.
* It drives the ``permit`` subject only. ``change_request`` has its own gate function, its
  own epoch pin and its own merge procedure — rendered from the same templates, which is
  what makes one kind a meaningful sample and not half the job, but a sample nonetheless.
* It observes which mechanism fires **first**. Refusal *depth* — that a second mechanism
  would have refused had the first been removed — is the unwelding matrix's claim and
  nothing here may be cited for it.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
from hypothesis import note
from hypothesis.stateful import Bundle, RuleBasedStateMachine, invariant, precondition, rule
from hypothesis.strategies import booleans

from .adapter import Adapter
from .invariants import check_all
from .model import Model, Verdict
from .refschema import Fixture

__all__ = ["GateMachine", "make_machine"]


class GateMachine(RuleBasedStateMachine):
    """Eight rules, four invariants, and one assertion repeated after every step.

    Subclass and set :attr:`conn` and :attr:`fixture` before use — Hypothesis instantiates
    the class itself, so per-run state arrives as class attributes. :func:`make_machine`
    does that binding.
    """

    #: Bound by :func:`make_machine`. An autocommit connection to the cluster under test.
    conn: psycopg.Connection[Any]
    #: Bound by :func:`make_machine`. The tenancy every generated row lands in.
    fixture: Fixture
    #: Bound by :func:`make_machine`. Where authority-source rows are seeded; usually the
    #: same connection. See :class:`~trappoint_model.adapter.Adapter`.
    setup_conn: psycopg.Connection[Any] | None = None

    subjects = Bundle("subjects")
    checks = Bundle("checks")
    dispositions = Bundle("dispositions")

    def __init__(self) -> None:
        """Start one history: a fresh oracle over the connection's existing rows.

        The oracle starts EMPTY while the database does not — earlier histories in the
        same run left rows behind, because this substrate is append-only and a suite that
        deleted them would be exercising a path the product refuses to have. That is
        sound: the oracle only ever predicts verdicts for subjects it created, and the
        conservation laws are evaluated over the whole database, so the residue makes the
        invariant checks strictly stronger rather than weaker.
        """
        super().__init__()
        self.model = Model()
        self.adapter = Adapter(self.conn, self.fixture, self.setup_conn)

    # ── the comparison ─────────────────────────────────────────────────────────────
    def _agree(self, label: str, want: Verdict, got: Verdict) -> None:
        note(f"{label}: model={want} db={got}")
        # S101: the differential IS an assertion. `-O` would strip it, which is why
        # nothing in this repository runs pytest under optimisation.
        assert want == got, (  # noqa: S101
            f"DIFFERENTIAL DISAGREEMENT on {label}\n"
            f"  oracle : {want}\n"
            f"  cluster: {got}\n"
            "One of the two is wrong. File the counterexample; do not edit the model to "
            "match the cluster until the cluster's answer has been explained."
        )

    # ── rules ──────────────────────────────────────────────────────────────────────
    @rule(target=subjects)
    def create_subject(self) -> uuid.UUID:
        """Open a new permit in ``draft``."""
        sid = uuid.uuid4()
        self._agree(
            "create_subject",
            self.model.create_subject(str(sid)),
            self.adapter.create_subject(sid),
        )
        return sid

    @rule(target=subjects, parent=subjects)
    def fork_child(self, parent: uuid.UUID) -> uuid.UUID:
        """Fork: the declared remedy for a post-completion fact, cleared afresh."""
        sid = uuid.uuid4()
        self._agree(
            "fork_child",
            self.model.create_subject(str(sid), str(parent)),
            self.adapter.create_subject(sid, parent),
        )
        return sid

    @rule(target=checks, subject=subjects)
    def materialise_check(self, subject: uuid.UUID) -> uuid.UUID:
        """Materialise a precursor: the counter closes the gate and the epoch moves."""
        cid = uuid.uuid4()
        self._agree(
            "materialise_check",
            self.model.materialise_check(str(subject), str(cid)),
            self.adapter.materialise_check(subject, cid),
        )
        return cid

    @rule(target=dispositions, check=checks, expired=booleans())
    def sign_disposition(self, check: uuid.UUID, expired: bool) -> uuid.UUID:
        """Sign one obligation closed. ``expired`` signs a verdict already lapsed."""
        did = uuid.uuid4()
        self._agree(
            f"sign_disposition(expired={expired})",
            self.model.sign_disposition(str(check), str(did), expired=expired),
            self.adapter.sign_disposition(check, did, expired=expired),
        )
        return did

    @rule(target=dispositions, check=checks)
    def expire_override(self, check: uuid.UUID) -> uuid.UUID:
        """Sign a verdict whose window has already closed.

        Named for the rule in the brief, and it is the *deterministic* form of it: no
        sleeping, no clock control. ``expires_at`` in the past is legal at insert —
        ``ttl_enforced`` bounds the far end of the window, not the near one — so the
        counter decrements while the anti-join keeps counting. The projected counter reads
        zero and the derivation reads one, which is the case no CHECK over a scalar can
        see and ``fn_permit_merge_gate`` exists for.
        """
        did = uuid.uuid4()
        self._agree(
            "expire_override",
            self.model.sign_disposition(str(check), str(did), expired=True),
            self.adapter.sign_disposition(check, did, expired=True),
        )
        return did

    @rule(disposition=dispositions, by=dispositions)
    def retract(self, disposition: uuid.UUID, by: uuid.UUID) -> None:
        """Retract: the one permitted UPDATE in the operational zone."""
        self._agree(
            "retract",
            self.model.retract(str(disposition), str(by)),
            self.adapter.retract(disposition, by),
        )

    @rule(subject=subjects)
    def attempt_merge(self, subject: uuid.UUID) -> None:
        """Attempt THE TRANSITION THE DATABASE DEFENDS."""
        self._agree(
            "attempt_merge",
            self.model.attempt_merge(str(subject)),
            self.adapter.attempt_merge(subject),
        )

    @rule(subject=subjects)
    def suspend(self, subject: uuid.UUID) -> None:
        """Stop a merged subject. It is never un-merged."""
        self._agree("suspend", self.model.suspend(str(subject)), self.adapter.suspend(subject))

    # ── invariants ─────────────────────────────────────────────────────────────────
    @invariant()
    def conservation(self) -> None:
        """L1, no-fork, counter fidelity, drift direction and ledger density, per step."""
        violations, skipped = check_all(self.conn)
        assert not violations, "CONSERVATION LAW BROKEN\n  " + "\n  ".join(  # noqa: S101
            str(v) for v in violations
        )
        if skipped:
            note(f"laws not applicable to this binding: {', '.join(skipped)}")

    @precondition(lambda self: bool(self.model.merged_subjects()))
    @invariant()
    def oracle_l1(self) -> None:
        """Assert the ORACLE's own L1.

        A model that broke its own law would hide a cluster that broke the real one.
        """
        assert self.model.l1_holds(), (  # noqa: S101
            "the ORACLE violated L1 — a merged subject in the model carries an open "
            "obligation, so the model has a branch that should have refused and did not"
        )


def make_machine(
    conn: psycopg.Connection[Any],
    fixture: Fixture,
    setup_conn: psycopg.Connection[Any] | None = None,
) -> type[GateMachine]:
    """Bind a connection and a tenancy to a fresh :class:`GateMachine` subclass.

    Hypothesis constructs the machine class itself and passes nothing, so per-run state
    has to be class-level. A fresh subclass per binding rather than mutating
    :class:`GateMachine` keeps two parametrised runs — SERIALIZABLE and READ COMMITTED —
    from writing over each other's connection.
    """
    return type(
        "BoundGateMachine",
        (GateMachine,),
        {"conn": conn, "fixture": fixture, "setup_conn": setup_conn},
    )
