# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The committed JSON Schema and the Pydantic models are one contract, not two.

``packages/trappoint-recall/src/trappoint_recall/run/schema/candidate-set-v1.schema.json`` is
generated from :class:`~trappoint_recall.run.contract.CandidateSet` and committed. That is
deliberate rather than redundant: the models are what the recall agent validates against, the
committed file is what the kernel lead, the console and any future non-Python consumer read in
a pull request, and **this test is the only thing that stops the two from drifting**. A
hand-maintained schema beside a model always eventually describes a payload the model refuses.

The second half of the file is the more important half. A JSON Schema cannot express a
cross-field law, so a consumer who validated against this document and stopped there would
believe a schema-valid payload is a legal one. It is not. Three laws live in the validators and
in the database and nowhere in the schema — MI17 conservation, the probabilistic cap, MI16 —
and each is asserted here to be *refused by the model while the schema is silent about it*. If
one of those ever became expressible, this test would fail, and that failure would be the
notice to update the schema's own warning.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from trappoint_recall.run.contract import (
    BLOCKING_CAP_PROBABILISTIC,
    CONTRACT_SCHEMA_VERSION,
    Candidate,
    CandidateSet,
    Counts,
    ExposureCueRef,
)
from trappoint_recall.run.schema import (
    SCHEMA_ID,
    candidate_set_json_schema,
    committed_schema_path,
    render_schema,
    write_schema,
)

CLAUSE = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
COMMIT = "ab" * 32
DIGEST = "cd" * 32


def _cue() -> ExposureCueRef:
    return ExposureCueRef(
        facet="mechanism",
        cue_sha256="11" * 32,
        template_sha256="ff" * 32,
        gen_model="au.anthropic.claude-sonnet-5",
        prompt_version="recall.cue/1",
        embed_model="BAAI/bge-large-en-v1.5@fixture",
    )


def _candidate(
    marker: str,
    *,
    outcome: str = "blocking",
    origin: str = "recall_probabilistic",
    severity: int = 3,
    tau: float = 0.6,
    bonded: bool = False,
) -> Candidate:
    return Candidate(
        event_id=UUID(f"{marker * 8}-{marker * 4}-4{marker * 3}-8{marker * 3}-{marker * 12}"),
        clause_uuid=CLAUSE,
        commit_id=COMMIT,
        origin=origin,  # type: ignore[arg-type]
        channels=("C",),
        outcome=outcome,  # type: ignore[arg-type]
        rank=1,
        severity=severity,
        p_relevant=0.8,
        tau_applied=tau,
        evidence_summary="shared mechanism: uncontrolled release during line breaking",
        bonded_severity_5=bonded,
    )


def _set(candidates: tuple[Candidate, ...], **overrides: Any) -> CandidateSet:
    payload: dict[str, Any] = {
        "run_id": UUID("33333333-3333-4333-8333-333333333333"),
        "permit_id": UUID("44444444-4444-4444-8444-444444444444"),
        "site_id": UUID("55555555-5555-4555-8555-555555555555"),
        "policy_version": "recall/2026.08.08",
        "taxonomy_ver": 1,
        "corpus_commit": DIGEST,
        "index_generation": "gen-1",
        "index_plan_digest": DIGEST,
        "arms_degraded": False,
        "silence_receipt_id": UUID("66666666-6666-4666-8666-666666666666"),
        "candidate_root": DIGEST,
        "certificate_verdict": "partial",
        "exposure_cues": (_cue(),),
        "candidates": candidates,
        "counts": Counts.of(candidates),
    }
    payload.update(overrides)
    return CandidateSet(**payload)


# ── the schema and the models agree ──────────────────────────────────────────────────


def test_the_committed_schema_is_what_the_models_generate() -> None:
    """The drift test. Regenerate with ``python -m trappoint_recall.run.schema``."""
    path = committed_schema_path()
    assert path.is_file(), f"{path} is the published contract and must be committed"
    assert path.read_text(encoding="utf-8") == render_schema(), (
        f"{path.name} has drifted from CandidateSet. Regenerate it with\n"
        "    python -m trappoint_recall.run.schema\n"
        "and commit the result: the kernel lead and the console read the file, not the model."
    )


def test_the_committed_schema_is_parseable_and_identifies_itself() -> None:
    """A consumer resolves this document by ``$id``; a version bump must be visible in it."""
    document = json.loads(committed_schema_path().read_text(encoding="utf-8"))
    assert document["$id"] == SCHEMA_ID
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["properties"]["schema_version"]["const"] == CONTRACT_SCHEMA_VERSION


def test_the_schema_warns_that_validity_is_not_sufficiency() -> None:
    """The document says, in its own description, what it cannot check."""
    description = candidate_set_json_schema()["description"]
    for phrase in ("necessary and NOT sufficient", "MI17", "MI16", "blocking_check"):
        assert phrase in description, f"the schema's own warning has lost {phrase!r}"


def test_regeneration_is_byte_stable(tmp_path) -> None:
    """Two renderings of the same models are the same bytes, so a diff means a real change."""
    first = write_schema(tmp_path / "a.json").read_text(encoding="utf-8")
    second = write_schema(tmp_path / "b.json").read_text(encoding="utf-8")
    assert first == second
    assert first.endswith("\n"), "one trailing newline, so the file is diffable"


# ── what the schema cannot say, and the models therefore must ────────────────────────


def _keywords(node: Any, seen: set[str] | None = None) -> set[str]:
    """Every keyword and member name anywhere in the document."""
    found = set() if seen is None else seen
    if isinstance(node, dict):
        found.update(node)
        for value in node.values():
            _keywords(value, found)
    elif isinstance(node, list):
        for value in node:
            _keywords(value, found)
    return found


def test_conservation_is_refused_by_the_model_and_absent_from_the_schema() -> None:
    """MI17 is arithmetic across two objects; JSON Schema has no vocabulary for it.

    The document carries no conditional-validation keyword at all, so nothing in it can relate
    ``counts.n_candidates`` to the length of ``candidates``. Should that ever change — a future
    generator emitting ``if``/``then``, or a hand edit adding ``dependentSchemas`` — this fails,
    and the failure is the notice to revisit the schema's own "not sufficient" warning rather
    than to delete the assertion.
    """
    conditional = {"if", "then", "else", "dependentSchemas", "dependentRequired", "$data"}
    present = _keywords(candidate_set_json_schema()) & conditional
    assert not present, (
        f"the schema now carries conditional keywords {sorted(present)}; re-examine whether a "
        "cross-field law has become expressible, and update the description if so"
    )

    with pytest.raises(ValidationError, match="candidates_conserved"):
        Counts(n_candidates=4, n_blocking=1, n_advisory=1, n_silenced=1, n_deduped=0)


def test_the_probabilistic_cap_is_refused_by_the_model_only() -> None:
    """Recall lead D2. Four probabilistic blocking checks validate structurally and are illegal."""
    four = tuple(_candidate(marker, outcome="blocking") for marker in ("1", "2", "3", "4"))
    assert len(four) == BLOCKING_CAP_PROBABILISTIC + 1
    with pytest.raises(ValidationError, match="cap of 3"):
        _set(four)


def test_a_bonded_fatality_cannot_be_anything_but_blocking() -> None:
    """MI16. The wire refuses it before the CHECK ever sees the row."""
    with pytest.raises(ValidationError, match="fatality never decays"):
        _candidate("7", outcome="advisory", severity=5, bonded=True)


def test_graph_truth_is_never_thresholded_and_never_silenced() -> None:
    """Channels A and B are admitted unconditionally, so no tau is consulted for them."""
    with pytest.raises(ValidationError, match="channel A or B"):
        _candidate("8", outcome="silenced", origin="deterministic_ancestry", tau=0.0)
    with pytest.raises(ValidationError, match=r"tau_applied must be 0\.0"):
        _candidate("9", outcome="blocking", origin="bonded", tau=0.45)


def test_an_undetermined_verdict_cannot_travel_without_the_flag() -> None:
    """CUE HORIZON, on the wire: an uncertified reach may not be presented as exhausted."""
    with pytest.raises(ValidationError, match="UNDETERMINED"):
        _set((), certificate_verdict="UNDETERMINED")

    honest = _set((), certificate_verdict="UNDETERMINED", not_exhaustive=True)
    assert honest.not_exhaustive is True
    assert honest.open_blocking == 0


def test_a_round_trip_through_the_wire_preserves_the_partition() -> None:
    """Serialise, parse, and the counts a kernel reads are the counts the agent computed."""
    original = _set((_candidate("1"), _candidate("2", outcome="silenced")))
    restored = CandidateSet.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.counts.n_candidates == 2
    assert restored.open_blocking == 1
    assert len(restored.blocking()) == 1
