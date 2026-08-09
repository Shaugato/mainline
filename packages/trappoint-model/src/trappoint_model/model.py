# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The oracle. Pure Python, no database, no substrate import — see README §1.

Every operation returns ``Accept`` or ``Refuse(sqlstate, constraint)``. The constraint is
part of the verdict because the constraint name is the exhibit: a model that predicted
only "refused" would agree with a gate that refused for the wrong reason. Read
:meth:`Model.attempt_merge` first — its four lines are the product.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Accept", "Model", "Refuse", "Verdict"]

_GATED = "trappoint_ref.fn_permit_merge_gate"
_MATERIALISE = "trappoint_ref.fn_check_materialised"
_RETRACT_ONLY = "trappoint_ref.fn_disposition_retract_only"
_DISPOSITION_PROJECT = "trappoint_ref.fn_disposition_project"


@dataclass(frozen=True, slots=True)
class Accept:
    """The gate admitted the write."""


@dataclass(frozen=True, slots=True)
class Refuse:
    """The gate said no, with the exhibit that says why."""

    sqlstate: str
    constraint: str


Verdict = Accept | Refuse


@dataclass(slots=True)
class _Subject:
    state: str = "draft"
    open_blocking: int = 0
    epoch: int = 0
    merged: bool = False


@dataclass(slots=True)
class _Obligation:
    subject: str
    # The one UNRETRACTED disposition, if any. `one_live_disposition` is a partial unique
    # index over `retracted_by IS NULL`, so expiry does NOT free the slot — an expired
    # verdict still occupies it while it stops covering the obligation. That asymmetry is
    # the whole of the drift case.
    live: str | None = None


@dataclass(slots=True)
class _Disposition:
    check: str
    subject: str
    retracted: bool = False
    expired: bool = False


@dataclass(slots=True)
class Model:
    """Subjects, obligations, dispositions, epochs — and the transition each op attempts."""

    subjects: dict[str, _Subject] = field(default_factory=dict)
    checks: dict[str, _Obligation] = field(default_factory=dict)
    dispositions: dict[str, _Disposition] = field(default_factory=dict)

    # ── derived ────────────────────────────────────────────────────────────────────
    def derived_open(self, sid: str) -> int:
        """Obligations with no live, unretracted, unexpired disposition. The anti-join."""
        return sum(
            1 for cid, ob in self.checks.items() if ob.subject == sid and not self._covered(cid)
        )

    def _covered(self, cid: str) -> bool:
        live = self.checks[cid].live
        return live is not None and not self.dispositions[live].expired

    # ── transitions ────────────────────────────────────────────────────────────────
    def create_subject(self, sid: str, parent: str | None = None) -> Verdict:
        """Open a subject in ``draft``. ``parent`` is a fork; the parent must exist."""
        if parent is not None and parent not in self.subjects:
            return Refuse("23503", "fk_parent_permit")
        self.subjects[sid] = _Subject()
        return Accept()

    def materialise_check(self, sid: str, cid: str) -> Verdict:
        """Materialise a precursor: close the gate, move the epoch (MI07)."""
        s = self.subjects.get(sid)
        if s is None or s.state == "merged":
            return Refuse("P0001", _MATERIALISE)
        if s.merged:
            # merged, then suspended. The trigger's state test no longer matches, so the
            # deterministic RAISE steps aside and the pin refuses instead — depth 2, at
            # runtime, on the one path that exercises it.
            return Refuse("23503", "epoch_pin_permit")
        self.checks[cid] = _Obligation(subject=sid)
        s.open_blocking += 1
        s.epoch += 1
        if s.state == "draft":
            s.state = "checks_materialised"
        return Accept()

    def sign_disposition(self, cid: str, did: str, *, expired: bool = False) -> Verdict:
        """One signature closes one obligation. ``expired`` signs a verdict already lapsed."""
        ob = self.checks.get(cid)
        if ob is None:
            return Refuse("P0001", _DISPOSITION_PROJECT)
        if ob.live is not None:
            return Refuse("23505", "one_live_disposition")
        s = self.subjects[ob.subject]
        self.dispositions[did] = _Disposition(cid, ob.subject, expired=expired)
        ob.live = did
        s.open_blocking -= 1
        if s.open_blocking == 0 and s.state == "checks_materialised":
            s.state = "dispositioned"
        return Accept()

    def retract(self, did: str, by: str) -> Verdict:  # noqa: PLR0911
        """Apply the one permitted UPDATE: re-open the obligation and move the epoch.

        Five branches, in the order MEASURED on v26.2.5 — trigger RAISE, then the
        subject's CHECKs and pin, then this row's CHECKs, then its foreign keys (F-M1).
        An UPDATE matching no row is not a refusal; it is a legal statement that changed
        nothing.
        """
        d = self.dispositions.get(did)
        if d is None:
            return Accept()
        if d.retracted:
            return Refuse("P0001", _RETRACT_ONLY)
        s = self.subjects[d.subject]
        if s.state == "merged":
            # MEASURED, and it contradicts the header of migration 0104. The row's own
            # CHECK is evaluated before the composite foreign key, so the counter refuses
            # and the pin never runs. Depth 2 either way; the exhibit is the counter's.
            return Refuse("23514", "gate_closed_when_issued")
        if s.merged:
            # Merged then suspended: `state <> 'merged'` satisfies that CHECK, so the
            # epoch bump reaches the pin. THIS is where epoch_pin_permit is observed.
            return Refuse("23503", "epoch_pin_permit")
        if by == did:
            return Refuse("23514", "retraction_not_reflexive")
        if by not in self.dispositions:
            return Refuse("23503", "disposition_retracted_by_fkey")
        d.retracted = True
        self.checks[d.check].live = None
        s.open_blocking += 1
        s.epoch += 1
        return Accept()

    def suspend(self, sid: str) -> Verdict:
        """Stop a merged subject: merged -> suspended is the only edge in, else 23503."""
        s = self.subjects.get(sid)
        if s is None or s.state != "merged":
            return Refuse("23503", "legal_edge")
        s.state = "suspended"
        return Accept()

    def attempt_merge(self, sid: str) -> Verdict:
        """Attempt THE TRANSITION THE DATABASE DEFENDS, in the order the refusals fire."""
        s = self.subjects.get(sid)
        if s is None or s.state != "dispositioned":
            return Refuse("23503", "legal_edge")  # the transition table, as data
        if s.open_blocking != 0:
            return Refuse("23514", "gate_closed_when_issued")  # the projected counter
        if self.derived_open(sid) != 0:
            return Refuse("P0001", _GATED)  # projection ≠ derivation: enforced, not trusted
        s.state = "merged"
        s.merged = True
        return Accept()

    # ── conservation laws (ARCHITECTURE §16.1) ─────────────────────────────────────
    def merged_subjects(self) -> list[str]:
        """Every subject carrying a completion record."""
        return [sid for sid, s in self.subjects.items() if s.merged]

    def l1_holds(self) -> bool:
        """L1 — no merged subject carries an open obligation.

        The model keeps no history, so this is the weaker, checkable half of the law:
        every path that could attach an obligation to a merged subject refuses above, so
        a violation here means a branch was added without one.
        """
        return all(
            self.subjects[sid].open_blocking == 0 and self.derived_open(sid) == 0
            for sid in self.merged_subjects()
        )
