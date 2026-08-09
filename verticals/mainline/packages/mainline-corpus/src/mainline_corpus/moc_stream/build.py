# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1c orchestration: scope the change register, plan its acts, write the tree.

The order is fixed and each step depends only on what precedes it::

    skeleton + answer key   stages 1 and 1b, rebuilt in memory
      -> scope              which clauses each change request declares it changes
      -> lifecycle          the ordered acts that carry it from draft to its terminal state
      -> dossiers           the per-change rollup, including what the gate should refuse
      -> verification       every check the database would eventually run, run here first
      -> emission

Stages 1 and 1b are **rebuilt** rather than read off disk, for the reason
``mainline_corpus.blame.build`` gives: a stage whose output can only be produced from another
worker's output *directory* cannot demonstrate its own reproducibility without first
demonstrating theirs.  ``--answer-key`` is accepted anyway and is used as a **cross-check** — the
rebuilt clause universe must agree with the committed ``clause.jsonl``, and a mismatch is a
refusal naming the difference.

Emission reuses ``blame.emit.AnswerKeyEmitter``.  Three canonicalisers in one package would be
three chances for a corpus to disagree with itself about what its own bytes are, and the
projected-column denylist is a shared safety property rather than a per-stage preference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..blame import params as blame_params
from ..blame.build import AnswerKey, build_answer_key
from ..blame.emit import AnswerKeyEmitter, TableSpec
from ..skeleton import clock
from ..skeleton import params as skeleton_params
from . import params, verify
from .dossier import build_dossiers
from .lifecycle import LifecycleResult, build_lifecycle
from .model import MocDossier, PendingField
from .scope import ScopeResult, build_scope

__all__ = ["BuildResult", "MocStream", "build_moc_stream", "generate"]


@dataclass(frozen=True, slots=True)
class MocStream:
    """Everything stage 1c knows, before any of it is written down."""

    key: AnswerKey
    scope: ScopeResult
    lifecycle: LifecycleResult
    dossiers: tuple[MocDossier, ...]
    report: verify.VerifyReport


@dataclass(frozen=True, slots=True)
class BuildResult:
    out_dir: Path
    counts: dict[str, int]
    file_digests: dict[str, str]
    index_sha256: str
    verify_summary: dict[str, int]
    unscoped: int


#: ``reason_code -> (table, column, owner, reason)``.  One string, one place: the register carries
#: the code on every row and ``pending_reasons.json`` carries the prose once.
PENDING_REASONS: dict[str, tuple[str, str, str, str]] = {
    "cr_clause.commit_id": (
        "mainline.cr_clause",
        "commit_id",
        "the worker that mints the commit DAG (commit_obj / commit_edge / ref)",
        (
            "Declared scope is pinned to a clause VERSION, not to a clause: the foreign key is "
            "onto (clause_uuid, commit_id) so a re-authored clause cannot silently carry an old "
            "declaration forward into text nobody read. commit_id is sha256 over the JCS envelope "
            "and cannot be chosen, and nothing in the corpus lane mints commits. Each row carries "
            "commit_for_revision_key in the registry, which is the natural key of the revision "
            "whose commit closes it, so this is closed deterministically rather than by search."
        ),
    ),
    "cr_event.prev_digest": (
        "mainline.cr_event",
        "prev_digest",
        (
            "the database: mainline.merge_change_request (0118 step 3) reads it; "
            "mainline.fn_cr_event_chain (0106) verifies it"
        ),
        (
            "chain_digest is a STORED generated column computed by the server over CockroachDB's "
            "own JSONB rendering, and fn_cr_event_chain refuses any row whose prev_digest is not "
            "byte-equal to the stored predecessor's. Reimplementing that normaliser in Python "
            "would stake reproducibility on our copy never diverging from the server's, and a "
            "digest the client can predict no longer proves the server saw the payload it hashed. "
            "The corpus therefore emits a PLAN of acts and the loader performs them, so the chain "
            "is minted where it can only honestly be minted."
        ),
    ),
    "cr_event.seq": (
        "mainline.cr_event",
        "seq",
        "the database: derived in-transaction and defended by UNIQUE (cr_id, prev_seq)",
        (
            "There is no generator anywhere in this schema and CREATE SEQUENCE is banned, which "
            "is what lets the ledger claim a gap MEANS tampering. A sequence position allocated "
            "outside the transaction that writes the row would destroy exactly that claim, so the "
            "corpus supplies an ORDER (step) and never a position."
        ),
    ),
}


def _pending_row(code: str, key: str, facts: dict[str, Any]) -> PendingField:
    table, column, owner, _reason = PENDING_REASONS[code]
    return PendingField(
        table=table, key=key, column=column, owner=owner, reason_code=code, facts=facts
    )


def _pending(stream: MocStream) -> list[PendingField]:
    out: list[PendingField] = []
    for row in stream.scope.rows:
        out.append(
            _pending_row(
                "cr_clause.commit_id",
                row.key,
                {
                    "clause_key": row.clause_key,
                    "commit_for_revision_key": row.commit_for_revision_key,
                    "realised": row.realised,
                    "relation": row.relation,
                },
            )
        )
    for act in stream.lifecycle.transitions:
        facts = {
            "edge": f"{act.from_state}->{act.to_state}",
            "execute_via": act.execute_via,
            "step": act.step,
        }
        out.append(_pending_row("cr_event.prev_digest", act.key, dict(facts)))
        out.append(_pending_row("cr_event.seq", act.key, dict(facts)))
    return out


def _cross_check(key: AnswerKey, answer_key_dir: Path) -> str:
    """Compare the rebuilt clause universe against the committed answer key.

    ``cr_clause``'s foreign key is onto a clause version, so a declared scope built from a
    universe that disagrees with the committed one would point at rows the corpus never wrote.
    That is worth one file read and a set comparison.
    """
    clauses_path = Path(answer_key_dir) / "clause.jsonl"
    if not clauses_path.is_file():
        raise FileNotFoundError(
            f"{answer_key_dir} is not an answer-key tree: clause.jsonl is missing"
        )
    on_disk = {
        str(json.loads(line)["clause_uuid"])
        for line in clauses_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    rebuilt = {clause.clause_uuid for clause in key.universe.clauses}
    if on_disk != rebuilt:
        only_disk = sorted(on_disk - rebuilt)[:3]
        only_memory = sorted(rebuilt - on_disk)[:3]
        raise RuntimeError(
            "the rebuilt clause universe disagrees with the committed answer key: "
            f"only on disk {only_disk}, only in memory {only_memory}. Every declared scope row "
            "would name a clause version the corpus does not contain."
        )
    return f"ok: {len(rebuilt)} clauses"


def build_moc_stream(
    *, answer_key_dir: Path | None = None, repo_root: Path | None = None
) -> MocStream:
    """Build the whole MOC stream in memory and falsify it before anyone can write it down."""
    key = build_answer_key()
    if answer_key_dir is not None:
        _cross_check(key, answer_key_dir)

    scope = build_scope(key)
    lifecycle = build_lifecycle(key, scope)
    dossiers = build_dossiers(key, scope, lifecycle)
    report = verify.run_checks(key, scope, lifecycle, dossiers, repo_root=repo_root)
    report.raise_on_failure()
    return MocStream(key=key, scope=scope, lifecycle=lifecycle, dossiers=dossiers, report=report)


_SPECS: tuple[TableSpec, ...] = (
    TableSpec(
        "cr_clause.jsonl",
        "mainline.cr_clause",
        lambda row: (str(row["cr_id"]), str(row["clause_uuid"]), str(row["relation"])),
        "declared scope: what each change request changes; commit_id is null and pending",
    ),
    TableSpec(
        "cr_clause_registry.jsonl",
        None,
        lambda row: (
            str(row["cr_external_ref"]),
            str(row["clause_key"]),
            str(row["relation"]),
        ),
        "corpus scaffolding: the basis of each declaration, the version it pins, and the delta",
    ),
    TableSpec(
        "cr_transition_plan.jsonl",
        None,
        lambda row: (str(row["cr_external_ref"]), int(row["step"])),
        "the ordered acts the loader performs; NOT cr_event rows, because the chain is the "
        "database's to mint",
    ),
    TableSpec(
        "moc_dossier.jsonl",
        None,
        lambda row: (str(row["external_ref"]),),
        "one row per change request: declared scope, plan shape, and the precursors the gate "
        "should find",
    ),
    TableSpec(
        "pending.jsonl",
        None,
        lambda row: (str(row["table"]), str(row["key"]), str(row["column"])),
        "columns this stage deliberately left null, and who closes each one",
    ),
)


def _spine_document(stream: MocStream) -> dict[str, Any] | None:
    refs = sorted({item.cr_external_ref for item in stream.key.proposed})
    if not refs:
        return None
    ref = refs[0]
    declared = stream.scope.for_cr(ref)
    acts = stream.lifecycle.for_cr(ref)
    dossier = next((item for item in stream.dossiers if item.external_ref == ref), None)
    return {
        "cr_external_ref": ref,
        "declared_clause_keys": [row.clause_key for row in declared],
        "declared_clause_uuids": [row.clause_uuid for row in declared],
        "declared_relations": [row.relation for row in declared],
        "first_act_at": clock.iso(acts[0].at) if acts else None,
        "opened_at": None if dossier is None else clock.iso(dossier.opened_at),
        "plan_ends_at_state": acts[-1].to_state if acts else None,
        "precursor_events": [] if dossier is None else list(dossier.precursor_events),
        "precursor_severity_max_from_answer_key": (
            None if dossier is None else dossier.precursor_severity_max_from_answer_key
        ),
        "realised": [row.realised for row in declared],
        "statement": (
            "One declared clause, unrealised, and a plan that stops short of the merge. The "
            "merge is not missing from the plan because it was forgotten; it is absent because "
            "whether it may happen is the database's answer to give, and the beat is that the "
            "answer is no."
        ),
        "transition_count": len(acts),
    }


def generate(
    out_dir: Path, *, answer_key_dir: Path | None = None, repo_root: Path | None = None
) -> BuildResult:
    """Build the MOC stream and write it to ``out_dir``."""
    stream = build_moc_stream(answer_key_dir=answer_key_dir, repo_root=repo_root)
    emitter = AnswerKeyEmitter(out_dir=Path(out_dir), repo_root=repo_root)

    payloads: dict[str, list[dict[str, Any]]] = {
        "cr_clause.jsonl": [row.to_row() for row in stream.scope.rows],
        "cr_clause_registry.jsonl": [row.to_registry_row() for row in stream.scope.rows],
        "cr_transition_plan.jsonl": [act.to_row() for act in stream.lifecycle.transitions],
        "moc_dossier.jsonl": [item.to_row() for item in stream.dossiers],
        "pending.jsonl": [item.to_row() for item in _pending(stream)],
    }

    digests: dict[str, str] = {}
    counts: dict[str, int] = {}
    for spec in _SPECS:
        record = emitter.write_table(spec, payloads[spec.filename])
        digests[spec.filename] = record.sha256
        counts[spec.filename.removesuffix(".jsonl")] = record.rows

    documents: list[tuple[str, dict[str, Any], str]] = [
        (
            "pending_reasons.json",
            {
                code: {"column": column, "owner": owner, "reason": reason, "table": table}
                for code, (table, column, owner, reason) in PENDING_REASONS.items()
            },
            "the prose behind pending.jsonl's reason_code, written once",
        ),
        (
            "verify_report.json",
            {
                "checks": [
                    {"check_id": check.check_id, "detail": check.detail, "status": check.status}
                    for check in stream.report.checks
                ],
                "summary": stream.report.summary(),
            },
            "every check the database would eventually run, run here first; SKIP carries a reason",
        ),
    ]
    spine = _spine_document(stream)
    if spine is not None:
        documents.append(
            (
                "spine_change_request.json",
                spine,
                "the 2026 weakening's declared scope and the act its plan deliberately omits",
            )
        )
    for filename, body, description in documents:
        record = emitter.write_document(filename, body, description=description)
        digests[filename] = record.sha256

    terminal_histogram: dict[str, int] = {}
    intent_histogram: dict[str, int] = {}
    for item in stream.dossiers:
        terminal_histogram[item.terminal_state] = terminal_histogram.get(item.terminal_state, 0) + 1
        intent_histogram[item.intent] = intent_histogram.get(item.intent, 0) + 1

    # Clauses two or more change requests declare. Not an error and not an accident: a document
    # reissue consolidates several approved changes, so two subjects claiming one clause is the
    # ordinary source of the situation `open_conflicts` exists to count.
    declarers: dict[str, set[str]] = {}
    for row in stream.scope.rows:
        declarers.setdefault(row.clause_uuid, set()).add(row.cr_external_ref)
    contested = sum(1 for refs in declarers.values() if len(refs) > 1)

    unscoped = len(stream.scope.unscoped)
    index_record = emitter.write_index(
        {
            "admissible_authored_drivers": sorted(params.ADMISSIBLE_R5_DRIVERS),
            "clauses_declared_by_multiple_change_requests": contested,
            "blame_generator_version": blame_params.GENERATOR_VERSION,
            "change_requests": len(stream.dossiers),
            "corpus_now": clock.iso(clock.NOW),
            "counts": dict(sorted(counts.items())),
            "declared_clause_rows": len(stream.scope.rows),
            "gazetteer_sha256": gaz.checksum(),
            "generator_version": params.GENERATOR_VERSION,
            "intent_histogram": dict(sorted(intent_histogram.items())),
            "realised_scope_rows": sum(1 for row in stream.scope.rows if row.realised),
            "scope_basis_histogram": stream.scope.basis_histogram(),
            "scope_relation_histogram": stream.scope.relation_histogram(),
            "scope_window_days": params.SCOPE_WINDOW_DAYS,
            "seed": rng.MASTER_SEED.decode("ascii"),
            "skeleton_generator_version": skeleton_params.GENERATOR_VERSION,
            "spine": spine,
            "stage": "moc-stream",
            "terminal_state_histogram": dict(sorted(terminal_histogram.items())),
            "transition_edge_histogram": stream.lifecycle.edge_histogram(),
            "unscoped_change_requests": unscoped,
            "verify": {
                "skipped": [check.check_id for check in stream.report.skipped],
                "summary": stream.report.summary(),
            },
        }
    )

    return BuildResult(
        out_dir=Path(out_dir),
        counts=dict(sorted(counts.items())),
        file_digests=dict(sorted(digests.items())),
        index_sha256=index_record.sha256,
        verify_summary=stream.report.summary(),
        unscoped=unscoped,
    )
