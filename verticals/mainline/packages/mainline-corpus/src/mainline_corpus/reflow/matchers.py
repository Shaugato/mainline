# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Four registers, run over the 2016 reflow boundary and scored against the carried identity.

A *register* here is the simplest honest model of how an organisation actually tracks an
obligation through a document revision: it keys the clause on one field, and when the new
revision lands it looks up the old row by that key.  Four keys are run — the printed label, the
ordinal, the control class, and the clause identity — because those are, respectively, what a
paper register does, what a paragraph-walking importer does, what a subject-matter expert does
by hand, and what MAINLINE does.

── HOW A MATCH IS JUDGED ─────────────────────────────────────────────────────────────────────

For each post-2016 clause the register proposes the pre-2016 clause (or clauses) whose key
agrees.  Ground truth is the identity the document carried across the reflow.  Then:

* exactly one proposal, same identity      -> ``true_positive``
* exactly one proposal, other identity     -> ``false_merge`` (history on the wrong obligation)
* no proposal at all                       -> ``false_split`` (reborn with no ancestry)
* more than one proposal                   -> ``ambiguous`` (the register cannot decide)

``precision`` is over *decided* proposals — ``tp / (tp + false_merge)`` — and a register that
proposed nothing at all has no precision to report, so it is emitted as ``0.0`` and the
``true_positive`` and ``false_split`` counts carry the meaning.  ``recall`` is always over the
full pair set, because an obligation the register never found is exactly as lost as one it
misattributed, and a metric that hid that would be doing the register's public relations.

── THE HONEST LIMIT ──────────────────────────────────────────────────────────────────────────

The ``clause_uuid`` register scores 1.000 because the corpus carries ``clause_uuid`` across the
reflow.  That is the corpus's construction restated, not a measurement, and it is flagged
``tautological`` in every payload this module produces.  What the other three rows measure is
real: they are a property of the *permutation and the relabelling*, which were drawn by the
skeleton and the retypeset injector, not by this file.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Final

from . import params
from .model import Collision, ReflowPair, RegisterScore

__all__ = ["KEY_FUNCTIONS", "score_register", "score_registers"]

#: How each register reads its key off a pair.  ``before`` reads the pre-2016 side, ``after``
#: reads the post-2016 side, and the two are deliberately separate functions: for the label and
#: the ordinal the two sides differ, which is the entire point, and writing one accessor with a
#: generation flag would have made it possible to read the same side twice by accident and score
#: a perfect run.
_Reader = Callable[[ReflowPair], str]

KEY_FUNCTIONS: Final[Mapping[str, tuple[_Reader, _Reader]]] = {
    "printed_label": (lambda pair: pair.g1_printed_label, lambda pair: pair.g2_printed_label),
    "ordinal": (lambda pair: str(pair.g1_ordinal), lambda pair: str(pair.g2_ordinal)),
    "control_class": (lambda pair: pair.control_class, lambda pair: pair.control_class),
    "clause_uuid": (lambda pair: pair.clause_uuid, lambda pair: pair.clause_uuid),
}


def _scope(pair: ReflowPair) -> tuple[str, str]:
    """Return the lookup scope: a register finds a clause **within its own document**.

    Scoping the lookup to ``(site, document)`` is the charitable reading: a register that
    searched the whole fonds for a matching label would score worse, not better, so every number
    in the scoreboard is an upper bound on what that register could achieve.
    """
    return (pair.site_code, pair.doc_code)


def score_register(
    register: str, description: str, pairs: Sequence[ReflowPair]
) -> tuple[RegisterScore, tuple[Collision, ...]]:
    """Run one register over every reflow pair and return its score and its failures."""
    if register not in KEY_FUNCTIONS:
        raise KeyError(
            f"{register!r} is not a register this stage knows. Known: {sorted(KEY_FUNCTIONS)}"
        )
    read_before, read_after = KEY_FUNCTIONS[register]

    index: dict[tuple[str, str, str], list[ReflowPair]] = {}
    for pair in pairs:
        site, doc = _scope(pair)
        index.setdefault((site, doc, read_before(pair)), []).append(pair)

    true_positive = 0
    false_merge = 0
    false_split = 0
    ambiguous = 0
    collisions: list[Collision] = []

    for pair in sorted(pairs, key=lambda item: (item.site_code, item.doc_code, item.g2_ordinal)):
        site, doc = _scope(pair)
        key_value = read_after(pair)
        candidates = index.get((site, doc, key_value), [])
        if len(candidates) == 1:
            candidate = candidates[0]
            if candidate.clause_uuid == pair.clause_uuid:
                true_positive += 1
                continue
            false_merge += 1
            collisions.append(
                Collision(
                    register=register,
                    failure_mode="false_merge",
                    site_code=site,
                    doc_code=doc,
                    key_value=key_value,
                    subject_clause_key=pair.clause_key,
                    subject_clause_uuid=pair.clause_uuid,
                    matched_clause_keys=(candidate.clause_key,),
                    detail=(
                        f"after the retypeset {pair.clause_key} prints as {pair.g2_printed_label} "
                        f"at position {pair.g2_ordinal}; a register keyed on {register} resolves "
                        f"that to {candidate.clause_key}, a different obligation, and every "
                        "precursor the two carry is now attached to the wrong clause"
                    ),
                )
            )
            continue
        if not candidates:
            false_split += 1
            collisions.append(
                Collision(
                    register=register,
                    failure_mode="false_split",
                    site_code=site,
                    doc_code=doc,
                    key_value=key_value,
                    subject_clause_key=pair.clause_key,
                    subject_clause_uuid=pair.clause_uuid,
                    matched_clause_keys=(),
                    detail=(
                        f"{pair.clause_key} printed as {pair.g1_printed_label} before the 2016 "
                        f"retypeset and as {pair.g2_printed_label} after it; a register keyed on "
                        f"{register} finds no predecessor, so the obligation is reborn in 2016 "
                        "with no ancestry and every precursor it carried is discarded in silence"
                    ),
                )
            )
            continue
        ambiguous += 1
        collisions.append(
            Collision(
                register=register,
                failure_mode="ambiguous",
                site_code=site,
                doc_code=doc,
                key_value=key_value,
                subject_clause_key=pair.clause_key,
                subject_clause_uuid=pair.clause_uuid,
                matched_clause_keys=tuple(sorted(item.clause_key for item in candidates)),
                detail=(
                    f"{len(candidates)} pre-2016 clauses of {doc} share {register}={key_value!r}; "
                    "the register cannot decide which of them this clause continues, and an "
                    "undecided link is an unwalked ancestry"
                ),
            )
        )

    total = len(pairs)
    decided = true_positive + false_merge
    precision = (true_positive / decided) if decided else 0.0
    recall = (true_positive / total) if total else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    score = RegisterScore(
        register=register,
        description=description,
        pairs=total,
        true_positive=true_positive,
        false_merge=false_merge,
        false_split=false_split,
        ambiguous=ambiguous,
        precision=precision,
        recall=recall,
        f1=f1,
        tautological=register in params.TAUTOLOGICAL_REGISTERS,
    )
    return score, tuple(collisions)


def score_registers(
    pairs: Sequence[ReflowPair],
) -> tuple[tuple[RegisterScore, ...], tuple[Collision, ...]]:
    """Every register in :data:`mainline_corpus.reflow.params.REGISTER_KEYS`, in that order."""
    scores: list[RegisterScore] = []
    failures: list[Collision] = []
    for register, description in params.REGISTER_KEYS:
        score, collisions = score_register(register, description, pairs)
        scores.append(score)
        failures.extend(collisions)
    return tuple(scores), tuple(failures)
