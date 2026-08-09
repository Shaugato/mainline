# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 3r orchestration: rebuild the world, audit the reflow, write the tree.

The order is fixed and each step depends only on what precedes it::

    blame.build.build_answer_key()      stages 1 and 1b, rebuilt in memory
      -> injectors.retypeset.schedule_rows()   the schedule this stage AUDITS
      -> pairs                          identity re-derived and refuted, per clause
      -> documents                      displacement, per document
      -> registers                      four registers scored over the boundary
      -> spine                          beat 1's exhibit, checked against anchors.yaml
      -> verification                   fourteen checks, then five self-refutations
      -> emission

── WHY THE WORLD IS REBUILT AND NOT READ ─────────────────────────────────────────────────────

``--answer-key`` is a **cross-check**, never a source.  Stage 1b makes the argument and it holds
here with more force: a stage whose whole claim is "this survival was derived, not asserted"
cannot take its inputs from a directory it did not produce and still say the derivation was
independent of the assertion.  So the schedule is rebuilt from
:func:`mainline_corpus.injectors.retypeset.schedule_rows`, and if a committed tree is offered the
two must agree row for row — a mismatch is a refusal naming the difference.

── WHAT THIS STAGE REFUSES TO DO ─────────────────────────────────────────────────────────────

**It does not carry ``identity_held`` forward.**  The injector's schedule stamps that boolean on
every row.  This stage reads the schedule and drops the field, replacing it with
``identity_matches_birth_key`` (a re-derivation) and ``identity_is_label_free`` (a refutation).
Copying the boolean would have made this stage a second place the same unchecked claim lives.

**It does not write a ``mainline.*`` table.**  Every ``TableSpec`` here declares ``table=None``.
The reflow's effect on the database is already carried by ``clause_version.printed_label`` and
``clause_version.ordinal``; this tree is evidence about the corpus, not more corpus.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..blame.build import AnswerKey, build_answer_key
from ..blame.emit import AnswerKeyEmitter, TableSpec
from ..injectors import retypeset
from . import matchers, measure, nemesis, params, verify
from .model import Collision, ReflowDocument, ReflowPair, RegisterScore

__all__ = ["BuildResult", "ReflowAudit", "build_reflow", "generate"]


@dataclass(frozen=True, slots=True)
class ReflowAudit:
    """Everything stage 3r knows, before any of it is written down."""

    pairs: tuple[ReflowPair, ...]
    documents: tuple[ReflowDocument, ...]
    scores: tuple[RegisterScore, ...]
    collisions: tuple[Collision, ...]
    spine: dict[str, Any]
    report: verify.VerifyReport
    mutations: tuple[nemesis.MutationOutcome, ...]

    def survivors(self) -> tuple[str, ...]:
        """Mutation ids the audit failed to notice.  Non-empty means the audit is decorative."""
        return tuple(
            outcome.mutation_id for outcome in self.mutations if outcome.verdict != "KILLED"
        )


@dataclass(frozen=True, slots=True)
class BuildResult:
    out_dir: Path
    counts: dict[str, int]
    file_digests: dict[str, str]
    index_sha256: str
    verify_summary: str
    failed_checks: tuple[str, ...]
    nemesis_summary: str
    survivors: tuple[str, ...]


# ── pairs ────────────────────────────────────────────────────────────────────────────────────


def _clause_uuid_for(clause_key: str) -> str:
    """``uuid5(CORPUS_NS, "clause:<clause_key>")`` — the corpus's one identity mint.

    Called twice per pair with two different keys: the clause's birth key, which must reproduce
    its identity, and a key built from its post-reflow printed label, which must not.
    """
    return str(rng.sid("clause", clause_key))


def _build_pairs(key: AnswerKey) -> tuple[ReflowPair, ...]:
    """One :class:`ReflowPair` per scheduled clause, with identity re-derived and refuted."""
    schedule = retypeset.schedule_rows(key.walk.retypeset_entries)
    universe = key.universe
    pairs: list[ReflowPair] = []
    for row in schedule:
        clause_key = str(row["clause_key"])
        clause = universe.by_key.get(clause_key)
        if clause is None:
            raise RuntimeError(
                f"the retypeset schedule names {clause_key!r}, which is not a clause in the "
                "universe. The reflow audit would be measuring a document the corpus does not "
                "contain."
            )
        site_code = str(row["site_code"])
        doc_code = str(row["doc_code"])
        g1_label = str(row["g1_printed_label"])
        g2_label = str(row["g2_printed_label"])
        g1_ordinal = int(row["g1_ordinal"])
        g2_ordinal = int(row["g2_ordinal"])
        birth_key_uuid = _clause_uuid_for(clause_key)
        g2_label_key_uuid = _clause_uuid_for(f"{site_code}/{doc_code}/{g2_label}")
        matches_birth = clause.clause_uuid == birth_key_uuid
        label_changed = g1_label != g2_label
        # Label-free means: the identity is the birth mint AND is *not* the mint of the label the
        # clause now prints under. The second conjunct is only informative where the label moved,
        # so where it did not, the clause cannot testify and the field records that honestly by
        # requiring only the first conjunct.
        label_free = matches_birth and (clause.clause_uuid != g2_label_key_uuid)
        pairs.append(
            ReflowPair(
                site_code=site_code,
                doc_code=doc_code,
                clause_key=clause_key,
                clause_uuid=clause.clause_uuid,
                control_class=str(row["control_class"]),
                barrier_role=clause.barrier_role,
                revision_key=str(row["revision_key"]),
                effective_on=str(row["effective_on"]),
                is_spine=clause.is_spine,
                g1_printed_label=g1_label,
                g1_ordinal=g1_ordinal,
                g1_shape=measure.label_shape(g1_label),
                g2_printed_label=g2_label,
                g2_ordinal=g2_ordinal,
                g2_shape=measure.label_shape(g2_label),
                label_changed=label_changed,
                ordinal_changed=g1_ordinal != g2_ordinal,
                ordinal_displacement=abs(g2_ordinal - g1_ordinal),
                birth_key_uuid=birth_key_uuid,
                g2_label_key_uuid=g2_label_key_uuid,
                identity_matches_birth_key=matches_birth,
                identity_is_label_free=label_free,
            )
        )
    return tuple(pairs)


# ── documents ────────────────────────────────────────────────────────────────────────────────


def _verdict(tau: float, label_fraction: float, disjoint: bool) -> tuple[str, str]:
    """Classify one document's reflow.  Three outcomes, and only one of them is the claim."""
    if label_fraction < 1.0:
        return (
            "partial_relabel",
            f"{label_fraction:.1%} of clauses changed label; a retypeset renumbers all of them",
        )
    if not disjoint:
        return (
            "renumbered",
            (
                "the two generations share a label grammar, so this is the same scheme with "
                "different numbers in it"
            ),
        )
    if tau < params.MIN_DOCUMENT_KENDALL_TAU:
        return (
            "relabelled_not_reordered",
            (
                f"Kendall tau distance {tau:.3f} is below "
                f"{params.MIN_DOCUMENT_KENDALL_TAU:.2f}; the clauses kept their relative order, "
                "so the scheme changed on paper only"
            ),
        )
    return (
        "reflowed",
        (
            f"every label changed, the two grammars are disjoint, and {tau:.1%} of clause pairs "
            "changed relative order"
        ),
    )


def _build_documents(pairs: Sequence[ReflowPair]) -> tuple[ReflowDocument, ...]:
    grouped: dict[tuple[str, str], list[ReflowPair]] = {}
    for pair in pairs:
        grouped.setdefault((pair.site_code, pair.doc_code), []).append(pair)

    documents: list[ReflowDocument] = []
    for (site_code, doc_code), members in sorted(grouped.items()):
        ordered = sorted(members, key=lambda item: item.g1_ordinal)
        before = [item.g1_ordinal for item in ordered]
        after = [item.g2_ordinal for item in ordered]
        count = len(ordered)
        label_changed = sum(1 for item in ordered if item.label_changed)
        ordinal_changed = sum(1 for item in ordered if item.ordinal_changed)
        disjoint, shared = measure.schemes_are_disjoint(
            (item.g1_printed_label for item in ordered),
            (item.g2_printed_label for item in ordered),
        )
        tau = measure.kendall_tau_distance(before, after)
        label_fraction = label_changed / count
        verdict, reason = _verdict(tau, label_fraction, disjoint)
        documents.append(
            ReflowDocument(
                site_code=site_code,
                doc_code=doc_code,
                clause_count=count,
                label_change_fraction=label_fraction,
                ordinal_change_fraction=ordinal_changed / count,
                kendall_tau_distance=tau,
                footrule_displacement=measure.footrule_displacement(before, after),
                g1_shapes=measure.scheme_shapes(item.g1_printed_label for item in ordered),
                g2_shapes=measure.scheme_shapes(item.g2_printed_label for item in ordered),
                shapes_disjoint=disjoint,
                shared_shapes=shared,
                verdict=verdict,
                verdict_reason=reason,
            )
        )
    return tuple(documents)


# ── the spine exhibit ────────────────────────────────────────────────────────────────────────


def _build_spine(pairs: Sequence[ReflowPair], spine_clause_key: str) -> dict[str, Any]:
    """Beat 1's exhibit: one clause, two schemes, one identity — checked against the gazetteer."""
    anchors = gaz.load("anchors")
    declared = anchors["spine"]
    matching = [pair for pair in pairs if pair.clause_key == spine_clause_key]
    if len(matching) != 1:
        raise RuntimeError(
            f"the spine clause {spine_clause_key!r} appears {len(matching)} times in the "
            "retypeset schedule. Beat 1 shows exactly one reflow of exactly one clause; anything "
            "else is a different film."
        )
    pair = matching[0]
    declared_before = str(declared["clause_label_2011"])
    declared_after = str(declared["clause_label_2016"])
    return {
        "agrees_with_anchors": (
            pair.g1_printed_label == declared_before and pair.g2_printed_label == declared_after
        ),
        "clause_key": pair.clause_key,
        "clause_uuid": pair.clause_uuid,
        "declared_label_2011": declared_before,
        "declared_label_2016": declared_after,
        "doc_code": pair.doc_code,
        "effective_on": pair.effective_on,
        "identity_is_label_free": pair.identity_is_label_free,
        "measured_label_2011": pair.g1_printed_label,
        "measured_label_2016": pair.g2_printed_label,
        "ordinal_2011": pair.g1_ordinal,
        "ordinal_2016": pair.g2_ordinal,
        "site_code": pair.site_code,
        "statement": (
            f"{pair.doc_code} clause {pair.g1_printed_label} became clause "
            f"{pair.g2_printed_label} on {pair.effective_on}, and moved from position "
            f"{pair.g1_ordinal} to position {pair.g2_ordinal} of its document. Its identity, "
            f"{pair.clause_uuid}, is the mint of the natural key it was born at in 2011, and it "
            "is not the mint of the address it prints under today. Identity is anchored where "
            "the obligation came from, not where it currently sits on the page. That is what "
            "beat 1 shows, and it is the reason the 2013 incident is still attached to it in "
            "2026."
        ),
        "would_be_identity_if_label_derived": pair.g2_label_key_uuid,
    }


# ── cross-check ──────────────────────────────────────────────────────────────────────────────


def _cross_check(schedule: Sequence[Mapping[str, Any]], answer_key_dir: Path) -> None:
    """Compare the rebuilt schedule against a committed stage-1b tree.  Refuse on difference."""
    path = answer_key_dir / "injector_retypeset.jsonl"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing, so {answer_key_dir} is not a stage-1b answer-key tree and there "
            "is nothing to cross-check the rebuilt retypeset schedule against."
        )
    on_disk = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    rebuilt = {
        (str(row["clause_key"]), str(row["g2_printed_label"]), int(row["g2_ordinal"]))
        for row in schedule
    }
    committed = {
        (str(row["clause_key"]), str(row["g2_printed_label"]), int(row["g2_ordinal"]))
        for row in on_disk
    }
    if rebuilt != committed:
        only_memory = sorted(rebuilt - committed)[:3]
        only_disk = sorted(committed - rebuilt)[:3]
        raise RuntimeError(
            "the rebuilt 2016 retypeset disagrees with the committed answer key: only in memory "
            f"{only_memory}, only on disk {only_disk}. The reflow audit would be measuring a "
            "retypeset the corpus does not ship."
        )


# ── assembly ─────────────────────────────────────────────────────────────────────────────────


def build_reflow(
    *, answer_key_dir: Path | None = None, repo_root: Path | None = None
) -> ReflowAudit:
    """Rebuild the world and audit its reflow.  No clock, no network, no randomness."""
    del repo_root  # accepted for symmetry with the other stages; nothing here reads the tree
    key = build_answer_key()
    if answer_key_dir is not None:
        _cross_check(retypeset.schedule_rows(key.walk.retypeset_entries), Path(answer_key_dir))

    pairs = _build_pairs(key)
    documents = _build_documents(pairs)
    scores, collisions = matchers.score_registers(pairs)
    spine = _build_spine(pairs, key.universe.spine_clause_key)
    report = verify.run_checks(
        pairs=pairs, documents=documents, scores=scores, collisions=collisions, spine=spine
    )
    return ReflowAudit(
        pairs=pairs,
        documents=documents,
        scores=scores,
        collisions=collisions,
        spine=spine,
        report=report,
        mutations=nemesis.run_nemesis(pairs, spine),
    )


# ── emission ─────────────────────────────────────────────────────────────────────────────────

_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        filename="reflow_pair.jsonl",
        table=None,
        sort_key=lambda row: (row["site_code"], row["doc_code"], row["g1_ordinal"]),
        description=(
            "one row per clause carried through the 2016 retypeset; identity re-derived from the "
            "birth key and refuted against the post-reflow printed label"
        ),
    ),
    TableSpec(
        filename="reflow_document.jsonl",
        table=None,
        sort_key=lambda row: (row["site_code"], row["doc_code"]),
        description=(
            "one row per retypeset document: label-change and ordinal-change fractions, Kendall "
            "tau distance, normalised footrule displacement, and the reflow verdict"
        ),
    ),
    TableSpec(
        filename="reflow_collision.jsonl",
        table=None,
        sort_key=lambda row: (
            row["register"],
            row["site_code"],
            row["doc_code"],
            row["subject_clause_key"],
        ),
        description=(
            "every wrong or undecidable match the four registers proposed across the reflow "
            "boundary, with the operational consequence spelled out"
        ),
    ),
)


def _scoreboard(audit: ReflowAudit) -> dict[str, Any]:
    by_register = {score.register: score for score in audit.scores}
    label = by_register["printed_label"]
    identity = by_register["clause_uuid"]
    return {
        "headline": (
            f"Across one retypeset of {len({(d.site_code, d.doc_code) for d in audit.documents})} "
            f"controlled documents, a register keyed on the printed clause number recovers "
            f"{label.true_positive} of {label.pairs} obligations. A register keyed on the "
            f"identity the document carries recovers {identity.true_positive}."
        ),
        "must_not_claim": list(params.MUST_NOT_CLAIM),
        "registers": {score.register: score.to_payload() for score in audit.scores},
        "retypeset_effective_on": audit.pairs[0].effective_on if audit.pairs else None,
        "scored_against": (
            "the clause identity the corpus carries across the reflow; see must_not_claim"
        ),
        "tautological_registers": list(params.TAUTOLOGICAL_REGISTERS),
    }


def _thresholds() -> dict[str, Any]:
    return {
        "measured_when_written": dict(params.MEASURED),
        "min_document_kendall_tau": params.MIN_DOCUMENT_KENDALL_TAU,
        "min_label_change_fraction": params.MIN_LABEL_CHANGE_FRACTION,
        "min_mean_kendall_tau": params.MIN_MEAN_KENDALL_TAU,
        "min_ordinal_change_fraction": params.MIN_ORDINAL_CHANGE_FRACTION,
        "min_pairs": params.MIN_PAIRS,
        "min_retypeset_documents": params.MIN_RETYPESET_DOCUMENTS,
    }


def generate(
    out_dir: Path, *, answer_key_dir: Path | None = None, repo_root: Path | None = None
) -> BuildResult:
    """Build the reflow audit and write it to ``out_dir``."""
    audit = build_reflow(answer_key_dir=answer_key_dir, repo_root=repo_root)
    emitter = AnswerKeyEmitter(out_dir=Path(out_dir), repo_root=repo_root)

    payloads: dict[str, list[dict[str, Any]]] = {
        "reflow_pair.jsonl": [pair.to_row() for pair in audit.pairs],
        "reflow_document.jsonl": [document.to_row() for document in audit.documents],
        "reflow_collision.jsonl": [collision.to_row() for collision in audit.collisions],
    }

    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for spec in _SPECS:
        record = emitter.write_table(spec, payloads[spec.filename])
        digests[spec.filename] = record.sha256
        counts[spec.filename.removesuffix(".jsonl")] = record.rows

    documents_written: tuple[tuple[str, dict[str, Any], str], ...] = (
        (
            "reflow_scoreboard.json",
            _scoreboard(audit),
            "four registers scored over the reflow boundary, with the caveats attached",
        ),
        (
            "spine_reflow.json",
            audit.spine,
            "beat 1's exhibit: one clause, two numbering schemes, one identity",
        ),
        (
            "reflow_thresholds.json",
            _thresholds(),
            "the floors this stage enforces, and the values measured when they were chosen",
        ),
        (
            "verify_report.json",
            audit.report.to_payload(),
            "every check this stage runs, its verdict, and the numbers behind it",
        ),
        (
            "reflow_nemesis.json",
            {
                "principle": (
                    "PL-2: a suite that has never been red asserts nothing. Each mutation below "
                    "is a plausible defect applied to the honest audit; a mutation the checks do "
                    "not refuse is a check that measures something other than what it says."
                ),
                "mutations": [outcome.to_payload() for outcome in audit.mutations],
                "survivors": list(audit.survivors()),
                "summary": (
                    f"{sum(1 for m in audit.mutations if m.verdict == 'KILLED')} killed, "
                    f"{len(audit.survivors())} survived, of {len(audit.mutations)}"
                ),
            },
            "five deliberate defects, and which checks refused each of them",
        ),
    )
    for filename, body, description in documents_written:
        record = emitter.write_document(filename, body, description=description)
        digests[filename] = record.sha256

    index = emitter.write_index(
        {
            "stage": params.STAGE,
            "title": params.STAGE_TITLE,
            "loads_into_database": False,
            "loads_into_database_reason": (
                "the reflow's effect on the schema is already carried by "
                "clause_version.printed_label and clause_version.ordinal; this tree is evidence "
                "about the corpus, not more corpus"
            ),
            "must_not_claim": list(params.MUST_NOT_CLAIM),
            "nemesis_survivors": list(audit.survivors()),
            "verify": audit.report.summary(),
        }
    )

    killed = sum(1 for outcome in audit.mutations if outcome.verdict == "KILLED")
    return BuildResult(
        out_dir=Path(out_dir),
        counts=counts,
        file_digests=digests,
        index_sha256=index.sha256,
        verify_summary=audit.report.summary(),
        failed_checks=audit.report.failed_ids(),
        nemesis_summary=f"{killed}/{len(audit.mutations)} mutations killed",
        survivors=audit.survivors(),
    )
