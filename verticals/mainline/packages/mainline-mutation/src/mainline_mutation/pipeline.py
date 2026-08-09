# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Drive the real pipeline over one ancestor/descendant pair and record what it said.

    canon -> anchors -> CAT -> cat_key -> lattice -> resolution -> cascade -> residue

Every stage is ``mainline_domain``'s own code.  The harness re-implements
nothing that is under measurement; where a stage does not exist yet it is
recorded as absent rather than simulated, because a simulated stage would make
the published number a statement about the simulation.

WHAT IS DRIVEN TODAY, AND WHAT IS NOT — STATED SO NOBODY HAS TO GUESS
----------------------------------------------------------------------
========================  ==================================================
CANONHOLD                 driven — ``canon.canonicalise``
ANCHORLOCK                driven — ``anchors.extract_anchors``
CATSEAL                   driven — ``cat.extract_cat`` + ``cat.preimage.cat_key``
DIRECTRIX                 driven — the committed seed through the real loader
DELTALATTICE              driven — ``lattice.explain`` (or the crippled arm)
ABSTENTION RATCHET        driven — ``resolution.resolve`` with **no oracle**
CASCADE S1/S2/S3          driven — ``identity.candidates`` exact/anchor/lexical
CASCADE S4 (ANN)          NOT driven: it needs embeddings and a cluster, and
                          PL-3 forbids a dated path on either
MARGIN ASSIGNMENT (W8)    NOT LANDED — see :mod:`mainline_mutation.residue`
CBM LEDGER (W9)           NOT LANDED — recorded as ``cbm_available: false``
========================  ==================================================

THE VERDICT OF RECORD HERE IS PATH A, AND THE REASON IS A MEASUREMENT
----------------------------------------------------------------------
Path B is never consulted: it may only ever RAISE a verdict's force, so a
harness that supplied one could only make the kill rate look better, and a
residual-risk number a model can improve is a number about the model.  The
published figure is therefore the **model-free floor**, and a lower bound on the
whole system's detection rather than an estimate of it.

But "do not consult Path B" is not the same as "resolve with ``oracle=None``".
``resolution.explain`` treats an ABSENT oracle as an ABSTAINING one, and decision
D6 resolves an abstention to ``weaken`` — so ``resolve(path_a, None, theta)``
returns ``weaken`` for **every pair**, including a pure retypeset.  That is the
ABSTENTION RATCHET failing closed exactly as W5 specified, and it is measured
here rather than argued about: :attr:`PipelineOutcome.ratchet_delta_without_oracle`
records it on every row.

Judging on it would make the KILL catalogue score 100 % and the SURVIVE
catalogue score 0 %, which are not two measurements — they are one arithmetic
identity restated twice.  So the outcome is judged on **Path A's verdict**, the
column that actually varies with the mutation, and the ratchet's answer travels
beside it as the recorded fact that a deployment which never runs Path B blocks
on everything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from mainline_domain.anchors.extract import extract_anchors
from mainline_domain.canon import canonicalise
from mainline_domain.cat.extract import extract_cat
from mainline_domain.cat.preimage import cat_key
from mainline_domain.contracts import CAT, AnchorSet, CATResult, force
from mainline_domain.identity.candidates import (
    DEFAULT_BANDS,
    ClauseRecord,
    ClauseRef,
    LexicalCorpus,
    anchor_stage,
    exact_stage,
    lexical_stage,
)
from mainline_domain.resolution.resolve import resolve

from .directrix import HARNESS_COMMIT, HARNESS_SITE, registry
from .lattice_injection import explain_with
from .model import PipelineOutcome
from .residue import ResidueJudgement, derive_residue

__all__ = [
    "RESOLUTION_THETA",
    "ClauseView",
    "run_pair",
    "view_of",
]

#: theta for the abstention ratchet.  1.0 means "no oracle confidence can clear
#: the bar", which is the only honest setting when no oracle is consulted: it
#: makes the resolution's behaviour a function of Path A alone and removes any
#: chance that a tuned theta silently moved a published number.
RESOLUTION_THETA: Final[float] = 1.0

_ACTIVITY_ROOT: Final[str] = "mutation-harness"


@dataclass(frozen=True, slots=True)
class ClauseView:
    """One document, canonicalised and extracted.  The input to every comparison."""

    document: str
    canon_text: str
    canon_sha256: bytes
    anchors: AnchorSet
    cat_result: CATResult

    @property
    def cat(self) -> CAT | None:
        """The extracted tuple, or ``None`` when the text carries no clause at all."""
        return self.cat_result.cat

    @property
    def key(self) -> str | None:
        """``cat_key``, or ``None`` when there is no CAT to key."""
        return None if self.cat is None else cat_key(self.cat)


def view_of(document: str) -> ClauseView:
    """Canonicalise and extract one document, exactly as ingest would."""
    canon = canonicalise(document)
    anchors = extract_anchors(canon.canon_text)
    return ClauseView(
        document=document,
        canon_text=canon.canon_text,
        canon_sha256=canon.canon_sha256,
        anchors=anchors,
        cat_result=extract_cat(canon.canon_text, anchors=anchors),
    )


def _record(view: ClauseView, clause_uuid: uuid.UUID, commit: bytes) -> ClauseRecord:
    return ClauseRecord(
        ref=ClauseRef(clause_uuid=clause_uuid, commit_id=commit),
        site_id=HARNESS_SITE,
        activity_root=_ACTIVITY_ROOT,
        canon_text=view.canon_text,
        canon_sha256=view.canon_sha256,
        anchors=view.anchors,
    )


def _recover(ancestor: ClauseView, descendant: ClauseView) -> tuple[bool, str | None, float | None]:
    """Run S1, then S2, then S3 against a one-member corpus.  First stage that accepts wins.

    A one-member corpus is the honest shape for this measurement.  The question
    a SURVIVE mutant asks is "is the reformatted clause still recognisable as
    THIS ancestor", not "does it beat every other clause in the library" —
    which is worker W8's assignment problem and a different measurement.  A
    larger corpus would fold the matcher's discrimination into a number that
    claims to be about the canonicaliser.
    """
    ancestor_uuid = uuid.uuid5(uuid.NAMESPACE_OID, ancestor.canon_sha256.hex())
    record = _record(ancestor, ancestor_uuid, HARNESS_COMMIT)

    s1 = exact_stage(descendant.canon_sha256, [record])
    if s1.accepted(DEFAULT_BANDS.exact_accept):
        return True, "S1", 1.0

    s2 = anchor_stage(
        query_anchors=descendant.anchors,
        query_text=descendant.canon_text,
        corpus=[record],
    )
    accepted = s2.accepted(DEFAULT_BANDS.anchor_accept)
    if accepted:
        return True, "S2", accepted[0].score

    corpus = LexicalCorpus(HARNESS_SITE)
    corpus.add(record)
    s3 = lexical_stage(query_text=descendant.canon_text, corpus=corpus)
    accepted = s3.accepted(DEFAULT_BANDS.lexical_accept)
    if accepted:
        return True, "S3", accepted[0].score

    best = s3.best() or s2.best()
    return False, None, None if best is None else best.score


def run_pair(
    ancestor: ClauseView,
    descendant: ClauseView,
    *,
    disabled_rules: frozenset[str] = frozenset(),
) -> PipelineOutcome:
    """Drive the whole model-free pipeline over one pair and record every fact.

    Returns facts, never a judgement.  :func:`mainline_mutation.judge.judge`
    turns these into an outcome, and the split is what lets a reader of the
    artefact re-derive the verdict from the row rather than trusting it.
    """
    decision = explain_with(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        reference_anchors=ancestor.anchors,
        descendant_anchors=descendant.anchors,
        disabled=disabled_rules,
    )
    path_a = decision.verdict
    # Recorded, never judged on. See the module docstring: an absent oracle is an
    # abstention and D6 makes an abstention a weakening, so this is `weaken` on
    # every row and carries no information about the mutation.
    ratchet = resolve(path_a, None, theta=RESOLUTION_THETA)

    recovered, stage, score = _recover(ancestor, descendant)
    judgement: ResidueJudgement = derive_residue(
        ancestor=ancestor,
        descendant=descendant,
        recovered=recovered,
    )

    return PipelineOutcome(
        ancestor_canon_sha256=ancestor.canon_sha256.hex(),
        descendant_canon_sha256=descendant.canon_sha256.hex(),
        ancestor_cat_key=ancestor.key,
        descendant_cat_key=descendant.key,
        ancestor_cat_confidence=ancestor.cat_result.confidence,
        descendant_cat_confidence=descendant.cat_result.confidence,
        delta=path_a.delta.value,
        delta_basis=path_a.basis,
        delta_force=force(path_a.delta),
        ratchet_delta_without_oracle=ratchet.delta.value,
        witness_rule_ids=tuple(w.rule_id for w in path_a.witnesses),
        residue_reasons=judgement.reasons,
        identity_recovered=recovered,
        match_stage=stage,
        match_score=None if score is None else round(score, 6),
        anchors_considered=decision.anchors_considered,
        disabled_rules=tuple(sorted(disabled_rules)),
        residue_source=judgement.source,
    )
