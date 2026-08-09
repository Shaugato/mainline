# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The emitted shapes, and the one field that is derived rather than carried.

Nothing in this stage loads into a ``mainline.*`` table.  The reflow tree is **evidence about**
the corpus, not more corpus: the retypeset's effect on the database is already carried by
``clause_version.printed_label`` and ``clause_version.ordinal``, which the loader writes from
``injector_retypeset.jsonl``.  Every ``TableSpec`` this stage declares therefore has
``table=None``, and ``index.json`` says so, so a loader that grew a habit of importing whatever
JSONL it found would import none of this.

── THE FIELD THAT MATTERS ────────────────────────────────────────────────────────────────────

:attr:`ReflowPair.identity_is_label_free` is the stage's whole argument in one boolean, and it is
the only boolean here that is *computed against a refutation* rather than copied.  It is true
when the clause's identity equals the mint of its **birth** natural key and does **not** equal
the mint of its **post-reflow printed label**.  A corpus in which identity were a function of the
printed address would fail the second half for every clause the retypeset moved — which is all of
them — so the field cannot be true by accident, and a generator that faked it would have to fake
a SHA-1 collision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "Collision",
    "ReflowDocument",
    "ReflowPair",
    "RegisterScore",
]


@dataclass(frozen=True, slots=True)
class ReflowPair:
    """One clause, on both sides of the 2016 house change."""

    site_code: str
    doc_code: str
    clause_key: str
    clause_uuid: str
    control_class: str
    barrier_role: str
    revision_key: str
    effective_on: str
    is_spine: bool
    g1_printed_label: str
    g1_ordinal: int
    g1_shape: str
    g2_printed_label: str
    g2_ordinal: int
    g2_shape: str
    label_changed: bool
    ordinal_changed: bool
    ordinal_displacement: int
    #: ``uuid5(CORPUS_NS, "clause:<clause_key>")`` — recomputed here, never copied.
    birth_key_uuid: str
    #: ``uuid5(CORPUS_NS, "clause:<site>/<doc>/<g2 printed label>")`` — the identity this clause
    #: *would* have had if identity were a function of its printed address.
    g2_label_key_uuid: str
    identity_matches_birth_key: bool
    identity_is_label_free: bool

    def to_row(self) -> dict[str, Any]:
        return {
            "barrier_role": self.barrier_role,
            "birth_key_uuid": self.birth_key_uuid,
            "clause_key": self.clause_key,
            "clause_uuid": self.clause_uuid,
            "control_class": self.control_class,
            "doc_code": self.doc_code,
            "effective_on": self.effective_on,
            "g1_ordinal": self.g1_ordinal,
            "g1_printed_label": self.g1_printed_label,
            "g1_shape": self.g1_shape,
            "g2_label_key_uuid": self.g2_label_key_uuid,
            "g2_ordinal": self.g2_ordinal,
            "g2_printed_label": self.g2_printed_label,
            "g2_shape": self.g2_shape,
            "identity_is_label_free": self.identity_is_label_free,
            "identity_matches_birth_key": self.identity_matches_birth_key,
            "is_spine": self.is_spine,
            "label_changed": self.label_changed,
            "ordinal_changed": self.ordinal_changed,
            "ordinal_displacement": self.ordinal_displacement,
            "revision_key": self.revision_key,
            "site_code": self.site_code,
        }


@dataclass(frozen=True, slots=True)
class ReflowDocument:
    """One retypeset document: how far it moved, and whether that counts as a reflow."""

    site_code: str
    doc_code: str
    clause_count: int
    label_change_fraction: float
    ordinal_change_fraction: float
    kendall_tau_distance: float
    footrule_displacement: float
    g1_shapes: tuple[str, ...]
    g2_shapes: tuple[str, ...]
    shapes_disjoint: bool
    shared_shapes: tuple[str, ...]
    verdict: str
    verdict_reason: str

    def to_row(self) -> dict[str, Any]:
        return {
            "clause_count": self.clause_count,
            "doc_code": self.doc_code,
            "footrule_displacement": round(self.footrule_displacement, 6),
            "g1_shapes": list(self.g1_shapes),
            "g2_shapes": list(self.g2_shapes),
            "kendall_tau_distance": round(self.kendall_tau_distance, 6),
            "label_change_fraction": round(self.label_change_fraction, 6),
            "ordinal_change_fraction": round(self.ordinal_change_fraction, 6),
            "shapes_disjoint": self.shapes_disjoint,
            "shared_shapes": list(self.shared_shapes),
            "site_code": self.site_code,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
        }


@dataclass(frozen=True, slots=True)
class Collision:
    """One wrong or undecidable match a register proposed across the reflow boundary.

    ``failure_mode`` is the operational consequence, in the words the console and the voice-over
    use:

    ``false_merge``
        the register matched a post-2016 clause to a **different** pre-2016 clause, so one
        obligation's history is now attached to another obligation.  The blame walk that follows
        is confidently wrong.
    ``false_split``
        the register found no pre-2016 clause at all, so the obligation is reborn with no
        ancestry.  Every precursor it carried is silently discarded, which is the failure the
        merge gate exists to make impossible.
    ``ambiguous``
        the key matched more than one pre-2016 clause and the register cannot decide.  A human
        resolves it, or nobody does.
    """

    register: str
    failure_mode: str
    site_code: str
    doc_code: str
    key_value: str
    subject_clause_key: str
    subject_clause_uuid: str
    matched_clause_keys: tuple[str, ...]
    detail: str

    def to_row(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "doc_code": self.doc_code,
            "failure_mode": self.failure_mode,
            "key_value": self.key_value,
            "matched_clause_keys": list(self.matched_clause_keys),
            "register": self.register,
            "site_code": self.site_code,
            "subject_clause_key": self.subject_clause_key,
            "subject_clause_uuid": self.subject_clause_uuid,
        }


@dataclass(frozen=True, slots=True)
class RegisterScore:
    """How one register did over the whole retypeset."""

    register: str
    description: str
    pairs: int
    true_positive: int
    false_merge: int
    false_split: int
    ambiguous: int
    precision: float
    recall: float
    f1: float
    tautological: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "ambiguous": self.ambiguous,
            "description": self.description,
            "f1": round(self.f1, 6),
            "false_merge": self.false_merge,
            "false_split": self.false_split,
            "pairs": self.pairs,
            "precision": round(self.precision, 6),
            "recall": round(self.recall, 6),
            "tautological": self.tautological,
            "true_positive": self.true_positive,
        }
