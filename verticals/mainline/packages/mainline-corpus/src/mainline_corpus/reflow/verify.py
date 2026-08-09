# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Fourteen checks over the reflow audit, run in process, before anything is written.

Every check here is *capable of failing*, and that is the property that makes the file worth
having (PL-2).  A suite that could only ever be green would assert nothing about a corpus whose
generator and whose auditor are in the same repository.  Three of them are adversarial by
construction and are the ones to read first:

``R03`` / ``R04``
    the re-derivation and the refutation.  ``R03`` recomputes every clause's identity from its
    birth natural key; ``R04`` recomputes it from the label the clause prints under *after* the
    reflow and demands the two differ.  Together they say: this identity is a function of where
    the obligation came from and not of where it currently sits on the page.  A corpus that
    minted identity from the printed address passes ``R03`` and fails ``R04`` on every clause.

``R10``
    the reflow must actually defeat a label-keyed register.  If it did not, the corpus would be
    demonstrating nothing and beat 1 would be a slide.

``R11``
    at least one register must be able to *misattribute* rather than merely lose.  A corpus in
    which every wrong answer is a visible blank is a corpus that has never met a document
    management system; the dangerous failure is the confident one, and it has to be present here
    for the console's silence ledger to have anything to point at.

Each check reports ``PASS``, ``FAIL`` or ``SKIP`` with a reason and the numbers it read, so the
report is legible without re-running anything.  ``SKIP`` is never used to hide an unmet
condition — the only skip in this file is an input that genuinely does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from . import params
from .model import Collision, ReflowDocument, ReflowPair, RegisterScore

__all__ = ["FORBIDDEN_ROW_FIELDS", "Check", "VerifyReport", "run_checks"]

#: Fields the injector's schedule stamps that this stage must not carry forward.  ``R14`` reads
#: it off the emitted row shape, so adding the field back to :meth:`ReflowPair.to_row` turns the
#: suite red rather than quietly restoring an unchecked claim.
FORBIDDEN_ROW_FIELDS: Final[frozenset[str]] = frozenset({"identity_held"})

#: A label-keyed register that still recovers more than this fraction of obligations across the
#: reflow would mean the retypeset was not a real reflow, and beat 1 would be showing nothing.
#: Measured 0.000.
LABEL_REGISTER_RECALL_CEILING: Final[float] = 0.05


@dataclass(frozen=True, slots=True)
class Check:
    check_id: str
    title: str
    status: str
    reason: str
    facts: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "facts": dict(self.facts),
            "reason": self.reason,
            "status": self.status,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class VerifyReport:
    checks: tuple[Check, ...]

    def failed_ids(self) -> tuple[str, ...]:
        return tuple(check.check_id for check in self.checks if check.status == "FAIL")

    def summary(self) -> str:
        passed = sum(1 for check in self.checks if check.status == "PASS")
        failed = sum(1 for check in self.checks if check.status == "FAIL")
        skipped = sum(1 for check in self.checks if check.status == "SKIP")
        return f"{passed} pass, {failed} fail, {skipped} skip"

    def to_payload(self) -> dict[str, Any]:
        return {
            "checks": [check.to_payload() for check in self.checks],
            "failed": list(self.failed_ids()),
            "summary": self.summary(),
        }


def _verdict(ok: bool, *, ok_reason: str, bad_reason: str) -> tuple[str, str]:
    return ("PASS", ok_reason) if ok else ("FAIL", bad_reason)


def _check_scale(pairs: Sequence[ReflowPair], documents: Sequence[ReflowDocument]) -> list[Check]:
    status, reason = _verdict(
        len(pairs) >= params.MIN_PAIRS,
        ok_reason=f"{len(pairs)} clauses were carried through the retypeset",
        bad_reason=(
            f"only {len(pairs)} clauses were carried through the retypeset; below "
            f"{params.MIN_PAIRS} the scoreboard's denominators stop meaning anything"
        ),
    )
    first = Check(
        check_id="R01",
        title="the retypeset carried enough clauses to measure",
        status=status,
        reason=reason,
        facts={"pairs": len(pairs), "floor": params.MIN_PAIRS},
    )
    status, reason = _verdict(
        len(documents) >= params.MIN_RETYPESET_DOCUMENTS,
        ok_reason=f"{len(documents)} documents were retypeset in one project, on one date",
        bad_reason=(
            f"only {len(documents)} documents were retypeset; decision D6 describes a whole-fonds "
            f"house change, which is at least {params.MIN_RETYPESET_DOCUMENTS} documents"
        ),
    )
    return [
        first,
        Check(
            check_id="R02",
            title="the retypeset was a project and not an amendment",
            status=status,
            reason=reason,
            facts={"documents": len(documents), "floor": params.MIN_RETYPESET_DOCUMENTS},
        ),
    ]


def _check_identity(pairs: Sequence[ReflowPair]) -> list[Check]:
    reminted = [pair.clause_key for pair in pairs if not pair.identity_matches_birth_key]
    status, reason = _verdict(
        not reminted,
        ok_reason=(
            f"all {len(pairs)} identities reproduce uuid5(CORPUS_NS, 'clause:' || clause_key) "
            "when recomputed here from the birth natural key"
        ),
        bad_reason=(
            f"{len(reminted)} clause(s) carry an identity that is not the mint of their birth "
            f"key (e.g. {reminted[:3]}); the reflow record invented an identity rather than "
            "carrying one, which is the survival claim asserting itself"
        ),
    )
    first = Check(
        check_id="R03",
        title="identity re-derived from the birth key, not copied",
        status=status,
        reason=reason,
        facts={"pairs": len(pairs), "reminted": len(reminted), "examples": reminted[:3]},
    )

    moved = [pair for pair in pairs if pair.label_changed]
    label_derived = [pair.clause_key for pair in moved if not pair.identity_is_label_free]
    status, reason = _verdict(
        bool(moved) and not label_derived,
        ok_reason=(
            f"for all {len(moved)} clauses whose printed label moved, the identity is NOT the "
            "mint of the label they now print under; identity is not a function of the address"
        ),
        bad_reason=(
            f"{len(label_derived)} clause(s) whose label moved carry an identity equal to the "
            f"mint of their new printed label (e.g. {label_derived[:3]}); identity would then be "
            "a function of the page, and a retypeset would destroy it"
            if moved
            else "no clause changed its printed label, so the refutation has nothing to refute"
        ),
    )
    return [
        first,
        Check(
            check_id="R04",
            title="identity refuted against the post-reflow printed label",
            status=status,
            reason=reason,
            facts={
                "label_moved": len(moved),
                "label_derived": len(label_derived),
                "examples": label_derived[:3],
            },
        ),
    ]


def _check_documents(
    pairs: Sequence[ReflowPair], documents: Sequence[ReflowDocument]
) -> list[Check]:
    checks: list[Check] = []

    partial = [
        f"{doc.site_code}/{doc.doc_code}"
        for doc in documents
        if doc.label_change_fraction < params.MIN_LABEL_CHANGE_FRACTION
    ]
    status, reason = _verdict(
        not partial,
        ok_reason="every clause of every retypeset document changed its printed label",
        bad_reason=(
            f"{len(partial)} document(s) kept some clause labels (e.g. {partial[:3]}); a "
            "retypeset renumbers everything, and a partial relabel is an amendment"
        ),
    )
    checks.append(
        Check(
            check_id="R05",
            title="the relabelling is total",
            status=status,
            reason=reason,
            facts={"floor": params.MIN_LABEL_CHANGE_FRACTION, "partial": partial[:5]},
        )
    )

    overlapping = [
        {"document": f"{doc.site_code}/{doc.doc_code}", "shared": list(doc.shared_shapes)}
        for doc in documents
        if not doc.shapes_disjoint
    ]
    status, reason = _verdict(
        not overlapping,
        ok_reason=(
            "no retypeset document shares a label grammar between its two generations; the "
            "schemes are structurally different and not the same scheme renumbered"
        ),
        bad_reason=(
            f"{len(overlapping)} document(s) share a label grammar across the reflow (e.g. "
            f"{overlapping[:2]}); decision D6 claims a different organising principle, and a "
            "shared address form is evidence against it"
        ),
    )
    checks.append(
        Check(
            check_id="R06",
            title="the two generations share no label grammar",
            status=status,
            reason=reason,
            facts={"overlapping": overlapping[:5]},
        )
    )

    flat = [
        {
            "document": f"{doc.site_code}/{doc.doc_code}",
            "kendall_tau_distance": round(doc.kendall_tau_distance, 6),
        }
        for doc in documents
        if doc.kendall_tau_distance < params.MIN_DOCUMENT_KENDALL_TAU
    ]
    taus = [doc.kendall_tau_distance for doc in documents]
    mean_tau = sum(taus) / len(taus) if taus else 0.0
    ok = not flat and mean_tau >= params.MIN_MEAN_KENDALL_TAU
    status, reason = _verdict(
        ok,
        ok_reason=(
            f"every document reordered at least {params.MIN_DOCUMENT_KENDALL_TAU:.0%} of its "
            f"clause pairs (min {min(taus):.3f}), mean {mean_tau:.3f}; a pure renumbering would "
            "score 0.000"
        ),
        bad_reason=(
            f"{len(flat)} document(s) below the per-document floor (e.g. {flat[:2]}), mean "
            f"{mean_tau:.3f} against a floor of {params.MIN_MEAN_KENDALL_TAU:.2f}; the clauses "
            "kept their relative order, so the scheme changed on paper only"
        ),
    )
    checks.append(
        Check(
            check_id="R07",
            title="the reflow reordered the clauses, it did not only renumber them",
            status=status,
            reason=reason,
            facts={
                "document_floor": params.MIN_DOCUMENT_KENDALL_TAU,
                "mean_floor": params.MIN_MEAN_KENDALL_TAU,
                "mean_kendall_tau_distance": round(mean_tau, 6),
                "min_kendall_tau_distance": round(min(taus), 6) if taus else None,
                "below_floor": flat[:5],
            },
        )
    )

    moved = sum(1 for pair in pairs if pair.ordinal_changed)
    fraction = moved / len(pairs) if pairs else 0.0
    status, reason = _verdict(
        fraction >= params.MIN_ORDINAL_CHANGE_FRACTION,
        ok_reason=(
            f"{moved} of {len(pairs)} clauses ({fraction:.1%}) sit at a different position in "
            "their document after the reflow"
        ),
        bad_reason=(
            f"only {fraction:.1%} of clauses moved position, against a floor of "
            f"{params.MIN_ORDINAL_CHANGE_FRACTION:.0%}"
        ),
    )
    checks.append(
        Check(
            check_id="R08",
            title="most clauses physically moved within their document",
            status=status,
            reason=reason,
            facts={
                "floor": params.MIN_ORDINAL_CHANGE_FRACTION,
                "moved": moved,
                "ordinal_change_fraction": round(fraction, 6),
                "pairs": len(pairs),
            },
        )
    )

    not_reflowed = [
        {"document": f"{doc.site_code}/{doc.doc_code}", "verdict": doc.verdict}
        for doc in documents
        if doc.verdict != "reflowed"
    ]
    status, reason = _verdict(
        not not_reflowed,
        ok_reason=f"all {len(documents)} documents are classified 'reflowed'",
        bad_reason=(
            f"{len(not_reflowed)} document(s) are not a reflow (e.g. {not_reflowed[:3]}); the "
            "corpus would be claiming a reflow it did not perform"
        ),
    )
    checks.append(
        Check(
            check_id="R09",
            title="every retypeset document earns the verdict 'reflowed'",
            status=status,
            reason=reason,
            facts={"not_reflowed": not_reflowed[:5]},
        )
    )
    return checks


def _check_registers(
    scores: Sequence[RegisterScore], collisions: Sequence[Collision]
) -> list[Check]:
    checks: list[Check] = []
    by_register = {score.register: score for score in scores}

    label = by_register.get("printed_label")
    if label is None:
        checks.append(
            Check(
                check_id="R10",
                title="the reflow defeats a register keyed on the printed clause number",
                status="FAIL",
                reason="the printed_label register was not scored, so the claim is unmeasured",
                facts={},
            )
        )
    else:
        status, reason = _verdict(
            label.recall <= LABEL_REGISTER_RECALL_CEILING,
            ok_reason=(
                f"a label-keyed register recovers {label.true_positive} of {label.pairs} "
                f"obligations across the reflow (recall {label.recall:.3f})"
            ),
            bad_reason=(
                f"a label-keyed register still recovers {label.recall:.1%} of obligations; the "
                "reflow is not adversarial enough for beat 1 to be showing anything"
            ),
        )
        checks.append(
            Check(
                check_id="R10",
                title="the reflow defeats a register keyed on the printed clause number",
                status=status,
                reason=reason,
                facts={
                    "ceiling": LABEL_REGISTER_RECALL_CEILING,
                    "false_split": label.false_split,
                    "recall": round(label.recall, 6),
                    "true_positive": label.true_positive,
                },
            )
        )

    merging = sorted(
        {score.register for score in scores if score.false_merge > 0 and not score.tautological}
    )
    merge_rows = sum(1 for item in collisions if item.failure_mode == "false_merge")
    status, reason = _verdict(
        bool(merging),
        ok_reason=(
            f"registers {merging} misattribute rather than merely lose: {merge_rows} confident "
            "wrong answers are on record in reflow_collision.jsonl"
        ),
        bad_reason=(
            "no non-tautological register produces a false merge, so every wrong answer in this "
            "corpus is a visible blank. The dangerous failure — history attached to the wrong "
            "obligation — is absent, and the silence ledger has nothing to point at"
        ),
    )
    checks.append(
        Check(
            check_id="R11",
            title="at least one register misattributes rather than merely losing",
            status=status,
            reason=reason,
            facts={"false_merge_rows": merge_rows, "registers": merging},
        )
    )

    identity = by_register.get("clause_uuid")
    caveat_ok = bool(params.MUST_NOT_CLAIM) and bool(params.TAUTOLOGICAL_REGISTERS)
    ok = identity is not None and identity.recall == 1.0 and identity.tautological and caveat_ok
    status, reason = _verdict(
        ok,
        ok_reason=(
            "the identity-keyed register recovers every obligation, is flagged tautological, and "
            f"ships with {len(params.MUST_NOT_CLAIM)} must-not-claim statements attached"
        ),
        bad_reason=(
            "the identity-keyed control is either not perfect, not flagged tautological, or not "
            "carrying its caveats. A perfect score presented without the caveat is the overclaim "
            "§11.7 forbids, and an imperfect one means the corpus lost an identity it minted"
        ),
    )
    checks.append(
        Check(
            check_id="R12",
            title="the identity control is perfect AND is labelled as a control",
            status=status,
            reason=reason,
            facts={
                "must_not_claim": len(params.MUST_NOT_CLAIM),
                "recall": round(identity.recall, 6) if identity else None,
                "tautological": identity.tautological if identity else None,
            },
        )
    )
    return checks


def _check_spine(spine: Mapping[str, Any], pairs: Sequence[ReflowPair]) -> list[Check]:
    agrees = bool(spine.get("agrees_with_anchors"))
    status, reason = _verdict(
        agrees,
        ok_reason=(
            f"the spine clause prints as {spine.get('measured_label_2011')} before the retypeset "
            f"and {spine.get('measured_label_2016')} after it, which is what anchors.yaml "
            "declares and what the voice-over says"
        ),
        bad_reason=(
            f"the spine clause measures {spine.get('measured_label_2011')} -> "
            f"{spine.get('measured_label_2016')} but anchors.yaml declares "
            f"{spine.get('declared_label_2011')} -> {spine.get('declared_label_2016')}; the film "
            "would be quoting a number the corpus does not contain"
        ),
    )
    first = Check(
        check_id="R13",
        title="beat 1's exhibit agrees with anchors.yaml",
        status=status,
        reason=reason,
        facts={
            "declared": [spine.get("declared_label_2011"), spine.get("declared_label_2016")],
            "measured": [spine.get("measured_label_2011"), spine.get("measured_label_2016")],
            "clause_uuid": spine.get("clause_uuid"),
        },
    )

    emitted_fields = set(pairs[0].to_row()) if pairs else set()
    carried = sorted(emitted_fields & FORBIDDEN_ROW_FIELDS)
    status, reason = _verdict(
        not carried,
        ok_reason=(
            "the emitted pair carries no field the injector merely asserted; the survival claim "
            "in this tree is the re-derivation and the refutation, and nothing else"
        ),
        bad_reason=(
            f"the emitted pair carries {carried}, a field the injector stamped rather than "
            "derived. Copying it here would make this tree a second home for an unchecked claim"
        ),
    )
    return [
        first,
        Check(
            check_id="R14",
            title="the injector's asserted boolean was dropped, not carried",
            status=status,
            reason=reason,
            facts={"carried": carried, "forbidden": sorted(FORBIDDEN_ROW_FIELDS)},
        ),
    ]


def run_checks(
    *,
    pairs: Sequence[ReflowPair],
    documents: Sequence[ReflowDocument],
    scores: Sequence[RegisterScore],
    collisions: Sequence[Collision],
    spine: Mapping[str, Any],
) -> VerifyReport:
    """Run every check, in id order, and return the report."""
    checks: list[Check] = []
    checks.extend(_check_scale(pairs, documents))
    checks.extend(_check_identity(pairs))
    checks.extend(_check_documents(pairs, documents))
    checks.extend(_check_registers(scores, collisions))
    checks.extend(_check_spine(spine, pairs))
    checks.sort(key=lambda check: check.check_id)
    return VerifyReport(checks=tuple(checks))
