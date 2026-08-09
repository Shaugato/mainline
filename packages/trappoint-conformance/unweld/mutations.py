# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The unwelding matrix: one mechanism, removed, at a time.

``merge-gate-invariant.md`` §3.5 asserts defence in depth — *"delete the ``RAISE`` and the
write still fails twice over"*. Today that is a sentence in a document. This module is the
list that turns it into an experiment, and :mod:`unweld.harness` is what runs it.

**Every removal is paired with its restoration, in committed SQL, in the same record.** Two
reasons, and the second is the one that matters. First, one disposable container can run the
whole matrix instead of forty containers. Second — and this is the honest part — writing the
restoration down forces the mutation to be *specific*: a removal whose inverse cannot be
written is a removal that changed more than one thing, and a matrix built from those would
measure nothing. If you cannot say how to put it back, you do not know what you took away.

**The restoration text is duplicated from the migration on purpose, and it is checked.**
``unweld/test_unweld.py::test_restoration_matches_the_migration`` asserts that every
restoration clause appears in the migration tree that owns the object, so a constraint whose
definition changes cannot leave this file quietly re-adding the old one — which would make
every subsequent row of the matrix a measurement of a schema nobody ships.

**Grants and RLS are absent from this matrix, deliberately.** ``CF-47``, ``CF-48`` and
``CF-69`` test the privilege layer from the outside, as a role that does not hold the
privilege, which is the only way to test it that means anything. Dropping a ``REVOKE`` while
connected as ``root`` would measure nothing at all, because ``root`` was never subject to it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MECHANISMS", "Mutation", "for_case", "mechanism_names"]


@dataclass(frozen=True, slots=True)
class Mutation:
    """One independent refusal mechanism, and how to take it away and put it back."""

    name: str
    """``<relation>.<object>`` for a constraint or index, ``<relation>@<trigger>`` for a
    trigger. It is the identity used in ``REFUSAL_DEPTH.md`` and in the assertion that the
    surviving refusal came from something else."""

    kind: str
    """``check`` · ``foreign_key`` · ``unique`` · ``index`` · ``trigger``."""

    sqlstate: str
    """The code this mechanism produces when it is the one that refuses. Used only to make
    the matrix readable; the assertion compares mechanism identities, not codes, because two
    mechanisms can share a code and sharing a code is not sharing a mechanism."""

    remove: str
    """DDL that removes exactly this mechanism. ``{s}`` is the profile's schema."""

    restore: str
    """DDL that puts it back. Asserted against the migration tree."""

    cases: tuple[str, ...]
    """The histories this mechanism is capable of refusing."""

    removable: bool = True
    """False where the mechanism **cannot** be taken away without taking something else
    with it. Such a mechanism is still counted as present at baseline and is still listed
    in ``REFUSAL_DEPTH.md``, marked ``unremovable``; it is simply never the removed
    mechanism in a probe, because a probe that removed two things at once would measure
    neither. Recording the reason is the point: an untested mechanism silently omitted from
    a matrix is exactly the kind of gap this suite exists to make visible."""

    unremovable_reason: str = ""
    """Why, in one sentence. Required when ``removable`` is False."""


# ─────────────────────────────────────────────────────────────────────────────
# The mechanisms, grouped by the claim each one supports.
# ─────────────────────────────────────────────────────────────────────────────

MECHANISMS: tuple[Mutation, ...] = (
    # ── the merge gate on a permit ───────────────────────────────────────────
    Mutation(
        name="permit.gate_closed_when_issued",
        kind="check",
        sqlstate="23514",
        remove="ALTER TABLE {s}.permit DROP CONSTRAINT gate_closed_when_issued",
        restore=(
            "ALTER TABLE {s}.permit ADD CONSTRAINT gate_closed_when_issued "
            "CHECK (state <> 'merged' OR open_blocking = 0)"
        ),
        cases=("CF-01", "CF-02", "CF-03", "CF-05", "CF-10", "CF-40", "CF-45", "CF-70"),
    ),
    Mutation(
        name="permit.merge_evidence",
        kind="check",
        sqlstate="23514",
        remove="ALTER TABLE {s}.permit DROP CONSTRAINT merge_evidence",
        restore=(
            "ALTER TABLE {s}.permit ADD CONSTRAINT merge_evidence "
            "CHECK (state <> 'merged' OR merged_commit IS NOT NULL)"
        ),
        cases=("CF-04",),
    ),
    Mutation(
        name="permit.reading_floor_when_issued",
        kind="check",
        sqlstate="23514",
        remove="ALTER TABLE {s}.permit DROP CONSTRAINT reading_floor_when_issued",
        restore=(
            "ALTER TABLE {s}.permit ADD CONSTRAINT reading_floor_when_issued "
            "CHECK (state <> 'merged' OR unmet_floor_count = 0 OR countersigned_count > 0)"
        ),
        cases=("CF-05",),
    ),
    Mutation(
        name="permit@permit_merge_gate",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.permit DISABLE TRIGGER permit_merge_gate",
        restore="ALTER TABLE {s}.permit ENABLE TRIGGER permit_merge_gate",
        cases=("CF-01", "CF-02", "CF-03", "CF-05", "CF-06", "CF-45", "CF-70"),
    ),
    # ── the merge gate on a change request ───────────────────────────────────
    Mutation(
        name="change_request.cr_gate_closed_when_merged",
        kind="check",
        sqlstate="23514",
        remove="ALTER TABLE {s}.change_request DROP CONSTRAINT cr_gate_closed_when_merged",
        restore=(
            "ALTER TABLE {s}.change_request ADD CONSTRAINT cr_gate_closed_when_merged "
            "CHECK (state <> 'merged' OR open_blocking = 0)"
        ),
        cases=("CF-31",),
    ),
    Mutation(
        name="change_request@cr_merge_gate",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.change_request DISABLE TRIGGER cr_merge_gate",
        restore="ALTER TABLE {s}.change_request ENABLE TRIGGER cr_merge_gate",
        cases=("CF-31",),
    ),
    # ── PIN ──────────────────────────────────────────────────────────────────
    Mutation(
        name="merge_record.epoch_pin_permit",
        kind="foreign_key",
        sqlstate="23503",
        remove="ALTER TABLE {s}.merge_record DROP CONSTRAINT epoch_pin_permit",
        restore=(
            "ALTER TABLE {s}.merge_record ADD CONSTRAINT epoch_pin_permit "
            "FOREIGN KEY (permit_id, gate_epoch) "
            "REFERENCES {s}.permit (permit_id, gate_epoch) "
            "ON UPDATE RESTRICT ON DELETE RESTRICT"
        ),
        cases=("CF-10", "CF-40"),
    ),
    Mutation(
        name="blocking_check@check_materialised",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.blocking_check DISABLE TRIGGER check_materialised",
        restore="ALTER TABLE {s}.blocking_check ENABLE TRIGGER check_materialised",
        cases=("CF-10",),
    ),
    # ── the projection that arms everything ──────────────────────────────────
    Mutation(
        name="blocking_check@check_project",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.blocking_check DISABLE TRIGGER check_project",
        restore="ALTER TABLE {s}.blocking_check ENABLE TRIGGER check_project",
        cases=("CF-42",),
    ),
    Mutation(
        name="blocking_check.fk_check_version",
        kind="foreign_key",
        sqlstate="23503",
        remove="ALTER TABLE {s}.blocking_check DROP CONSTRAINT fk_check_version",
        restore=(
            "ALTER TABLE {s}.blocking_check ADD CONSTRAINT fk_check_version "
            "FOREIGN KEY (clause_uuid, commit_id) "
            "REFERENCES {s}.clause_version (clause_uuid, commit_id)"
        ),
        cases=("CF-42",),
    ),
    # ── append-only, and the closure ─────────────────────────────────────────
    Mutation(
        name="clause_blame_closure@append_only",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.clause_blame_closure DISABLE TRIGGER append_only",
        restore="ALTER TABLE {s}.clause_blame_closure ENABLE TRIGGER append_only",
        cases=("CF-08",),
    ),
    Mutation(
        name="permit_event@append_only",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.permit_event DISABLE TRIGGER append_only",
        restore="ALTER TABLE {s}.permit_event ENABLE TRIGGER append_only",
        cases=("CF-39",),
    ),
    Mutation(
        name="disposition@disposition_retract_only",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.disposition DISABLE TRIGGER disposition_retract_only",
        restore="ALTER TABLE {s}.disposition ENABLE TRIGGER disposition_retract_only",
        cases=("CF-38", "CF-40"),
    ),
    # ── the chain, and the compare-and-swap behind it ────────────────────────
    Mutation(
        name="permit_event@permit_event_chain",
        kind="trigger",
        sqlstate="P0001",
        remove="ALTER TABLE {s}.permit_event DISABLE TRIGGER permit_event_chain",
        restore="ALTER TABLE {s}.permit_event ENABLE TRIGGER permit_event_chain",
        cases=("CF-16", "CF-17"),
    ),
    Mutation(
        name="permit_event.linear",
        kind="unique",
        sqlstate="23505",
        remove="ALTER TABLE {s}.permit_event DROP CONSTRAINT linear",
        restore="ALTER TABLE {s}.permit_event ADD CONSTRAINT linear UNIQUE (permit_id, prev_seq)",
        cases=("CF-14", "CF-17"),
    ),
    Mutation(
        name="cr_event.cr_linear",
        kind="unique",
        sqlstate="23505",
        remove="ALTER TABLE {s}.cr_event DROP CONSTRAINT cr_linear",
        restore="ALTER TABLE {s}.cr_event ADD CONSTRAINT cr_linear UNIQUE (cr_id, prev_seq)",
        cases=("CF-15",),
    ),
    Mutation(
        name="permit_event.legal_edge",
        kind="foreign_key",
        sqlstate="23503",
        remove="ALTER TABLE {s}.permit_event DROP CONSTRAINT legal_edge",
        restore=(
            "ALTER TABLE {s}.permit_event ADD CONSTRAINT legal_edge "
            "FOREIGN KEY (subject_kind, from_state, to_state) "
            "REFERENCES {s}.subject_transition (subject_kind, from_state, to_state) "
            "ON UPDATE RESTRICT ON DELETE RESTRICT"
        ),
        cases=("CF-13",),
    ),
    # ── the clearance lattice and the exposure binding ───────────────────────
    Mutation(
        name="disposition.fk_clearance",
        kind="foreign_key",
        sqlstate="23503",
        remove="ALTER TABLE {s}.disposition DROP CONSTRAINT fk_clearance",
        restore=(
            "ALTER TABLE {s}.disposition ADD CONSTRAINT fk_clearance "
            "FOREIGN KEY (virulence, kind) "
            "REFERENCES {s}.clearance_legal (virulence, kind)"
        ),
        cases=("CF-07", "CF-23", "CF-71"),
    ),
    Mutation(
        name="disposition.fk_exposure",
        kind="foreign_key",
        sqlstate="23503",
        remove="ALTER TABLE {s}.disposition DROP CONSTRAINT fk_exposure",
        restore=(
            "ALTER TABLE {s}.disposition ADD CONSTRAINT fk_exposure "
            "FOREIGN KEY (receipt_id, check_id) "
            "REFERENCES {s}.exposure_line (receipt_id, check_id)"
        ),
        cases=("CF-18",),
    ),
    Mutation(
        name="disposition.one_live_disposition",
        kind="index",
        sqlstate="23505",
        remove="DROP INDEX {s}.disposition@one_live_disposition",
        restore=(
            "CREATE UNIQUE INDEX one_live_disposition ON {s}.disposition (check_id) "
            "WHERE retracted_by IS NULL"
        ),
        cases=("CF-12",),
    ),
    # ── the completion record ────────────────────────────────────────────────
    Mutation(
        name="merge_record.merge_record_pkey",
        kind="unique",
        sqlstate="23505",
        remove="",
        restore="",
        cases=("CF-09", "CF-44"),
        removable=False,
        unremovable_reason=(
            "a primary key cannot be dropped without replacing it, and CockroachDB retains "
            "the old key as a unique index when the primary key is altered — so every "
            "available spelling of 'remove this mechanism' either removes two things or "
            "removes none, and a probe built on either would report a number that means "
            "nothing"
        ),
    ),
)


def mechanism_names() -> tuple[str, ...]:
    """Every mechanism identity, sorted."""
    return tuple(sorted(m.name for m in MECHANISMS))


def for_case(case_id: str) -> tuple[Mutation, ...]:
    """Return the mechanisms capable of refusing *case_id*, in declaration order."""
    return tuple(m for m in MECHANISMS if case_id in m.cases)
