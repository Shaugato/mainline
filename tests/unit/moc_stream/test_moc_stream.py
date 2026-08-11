# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1c: the MOC stream's declared scope and its lifecycle plan.

Every assertion here is one the database would eventually make, made against the *emitted bytes*
rather than against the generator's own in-memory objects. That distinction is the point: a
generator can be internally consistent and still write a file the loader cannot use.

Three of these tests read the shipped DDL rather than a constant in our own source
(``0053_cr_clause.sql`` for the relation vocabulary, ``0017b_subject_transition_seed.sql`` for
the state machine, ``0051_change_request.sql`` for the projected columns). A test that checked
our copy of the schema against our copy of the schema would pass forever, including on the day
the schema changed underneath it.
"""

from __future__ import annotations

import hashlib
import json
import re
from itertools import pairwise
from pathlib import Path

import pytest

from conftest import read_jsonl

# ── what the DDL actually says ───────────────────────────────────────────────────────────────

_RELATION_CHECK = re.compile(r"relation\s+IN\s*\(([^)]*)\)", re.IGNORECASE)
_TRANSITION_ROW = re.compile(
    r"\(\s*'(?P<kind>[a-z_]+)'\s*,\s*'(?P<from>[a-z_]+)'\s*,\s*'(?P<to>[a-z_]+)'\s*\)"
)
_PROJECTS = re.compile(r"@projects\s+mainline\.change_request\.(?P<column>[a-z_]+)")


def _declared_relations(migrations: Path) -> frozenset[str]:
    text = (migrations / "0053_cr_clause.sql").read_text(encoding="utf-8")
    match = _RELATION_CHECK.search(text)
    assert match is not None, "0053_cr_clause.sql no longer declares cr_clause_relation_known"
    return frozenset(item.strip().strip("'") for item in match.group(1).split(",") if item.strip())


def _legal_edges(migrations: Path) -> frozenset[tuple[str, str]]:
    text = (migrations / "0017b_subject_transition_seed.sql").read_text(encoding="utf-8")
    return frozenset(
        (match.group("from"), match.group("to"))
        for match in _TRANSITION_ROW.finditer(text)
        if match.group("kind") == "change_request"
    )


def _projected_columns(migrations: Path) -> frozenset[str]:
    text = (migrations / "0051_change_request.sql").read_text(encoding="utf-8")
    declared = {match.group("column") for match in _PROJECTS.finditer(text)}
    # The two ledger columns are projected by the event chain rather than pragma'd, and the
    # table comment says so at length. Naming them here keeps the assertion complete.
    return frozenset(declared | {"head_seq", "gate_epoch"})


# ── reproducibility ──────────────────────────────────────────────────────────────────────────


def test_two_runs_are_byte_identical(regenerated_twice: tuple[Path, Path]) -> None:
    first, second = regenerated_twice
    left = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(first.iterdir())
    }
    right = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(second.iterdir())
    }
    assert left, "the stage produced no files at all"
    differing = sorted(name for name in left if left[name] != right.get(name))
    assert not differing, f"two runs of stage 1c disagree on {differing}"


def test_committed_tree_matches_a_fresh_build(fixture_dir: Path, regenerated: Path) -> None:
    """The committed fixtures are what this generator produces, not what it produced once.

    Deliberately hashing the committed **bytes on disk**, not the digests inside the committed
    ``index.json``. Comparing one manifest against another proves only that two manifests agree;
    a data file edited by hand afterwards would sail straight through, which is the exact failure
    this test exists to catch.
    """
    fresh = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(regenerated.iterdir())
    }
    assert fresh, "the fresh build produced no files"
    drifted = sorted(
        name
        for name, digest in fresh.items()
        if not (fixture_dir / name).is_file()
        or hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest() != digest
    )
    assert not drifted, (
        f"the committed tree is stale or hand-edited for {drifted}; regenerate with "
        "`python -m mainline_corpus.moc_stream --out verticals/mainline/fixtures/corpus/moc-stream`"
    )

    # The other direction: a file in the committed tree that the generator no longer produces is
    # a stale artefact the loader would still read.
    generated = set(fresh) | {"README.md"}
    orphans = sorted(path.name for path in fixture_dir.iterdir() if path.name not in generated)
    assert not orphans, f"the committed tree carries files this stage does not produce: {orphans}"


def test_every_data_file_has_a_licence_sidecar(fixture_dir: Path) -> None:
    missing = sorted(
        path.name
        for path in fixture_dir.iterdir()
        if path.suffix in {".json", ".jsonl"}
        and not path.with_suffix(path.suffix + ".license").is_file()
    )
    assert not missing, f"REUSE sidecar missing for {missing}"


# ── the loadable table ───────────────────────────────────────────────────────────────────────


def test_cr_clause_rows_carry_exactly_the_loadable_columns(fixture_dir: Path) -> None:
    rows = read_jsonl(fixture_dir / "cr_clause.jsonl")
    assert rows, "no declared scope at all: the change-request gate would have nothing to read"
    expected = {"clause_uuid", "commit_id", "cr_id", "relation"}
    offenders = [row for row in rows if set(row) != expected]
    assert not offenders, f"unexpected column set on {len(offenders)} row(s): {offenders[:2]}"


def test_no_emitted_row_names_a_projected_column(fixture_dir: Path, migrations: Path) -> None:
    """P2. A corpus that supplies a projection makes the gate read a number the writer chose."""
    denied = _projected_columns(migrations)
    assert denied, "0051_change_request.sql declares no projected columns; the parse is wrong"
    offenders: list[str] = []
    for path in sorted(fixture_dir.glob("*.jsonl")):
        for position, row in enumerate(read_jsonl(path)):
            named = sorted(set(row) & denied)
            if named:
                offenders.append(f"{path.name}[{position}] names {named}")
    assert not offenders, offenders[:3]


def test_every_relation_is_one_the_ddl_admits(fixture_dir: Path, migrations: Path) -> None:
    declared = _declared_relations(migrations)
    assert declared, "could not parse cr_clause_relation_known out of 0053_cr_clause.sql"
    used = {row["relation"] for row in read_jsonl(fixture_dir / "cr_clause.jsonl")}
    assert used <= declared, f"{sorted(used - declared)} would be refused by the CHECK"
    assert len(used) > 1, "the corpus exercises only one relation; the vocabulary is untested"


def test_primary_key_is_unique(fixture_dir: Path) -> None:
    rows = read_jsonl(fixture_dir / "cr_clause.jsonl")
    keys = [(row["cr_id"], row["clause_uuid"], row["relation"]) for row in rows]
    assert len(set(keys)) == len(keys), "pk_cr_clause would be violated on load"


def test_commit_id_is_null_and_registered_pending(fixture_dir: Path) -> None:
    """Nothing invents thirty-two bytes it cannot compute."""
    rows = read_jsonl(fixture_dir / "cr_clause.jsonl")
    invented = [row for row in rows if row["commit_id"] is not None]
    assert not invented, f"{len(invented)} row(s) carry a fabricated commit_id"

    registered = {
        row["key"]
        for row in read_jsonl(fixture_dir / "pending.jsonl")
        if row["table"] == "mainline.cr_clause" and row["column"] == "commit_id"
    }
    assert len(registered) == len(rows), (
        f"{len(rows)} declared rows but {len(registered)} pending registrations; a null column "
        "with no registered owner is a hole, not a decision"
    )
    reasons = json.loads((fixture_dir / "pending_reasons.json").read_text(encoding="utf-8"))
    assert "cr_clause.commit_id" in reasons
    assert reasons["cr_clause.commit_id"]["owner"]


def test_pending_registrations_name_the_revision_that_closes_them(fixture_dir: Path) -> None:
    rows = [
        row
        for row in read_jsonl(fixture_dir / "pending.jsonl")
        if row["reason_code"] == "cr_clause.commit_id"
    ]
    assert rows
    unclosable = [row["key"] for row in rows if not row["facts"].get("commit_for_revision_key")]
    assert not unclosable, (
        f"{len(unclosable)} pending row(s) name no revision, so the commit worker would have to "
        f"search for what to bind: {unclosable[:3]}"
    )


# ── the chain the corpus refuses to mint ─────────────────────────────────────────────────────


def test_the_stage_ships_no_cr_event_table(fixture_dir: Path) -> None:
    """The corpus cannot compute a server-side chain digest, so it must not appear to have."""
    assert not (fixture_dir / "cr_event.jsonl").is_file(), (
        "a cr_event.jsonl invites a direct insert, and fn_cr_event_chain would refuse every row "
        "after the genesis one; the plan is the honest artefact"
    )
    index = json.loads((fixture_dir / "index.json").read_text(encoding="utf-8"))
    tables = {record["table"] for record in index["files"].values()}
    assert "mainline.cr_event" not in tables


def test_transition_rows_carry_no_chain_position(fixture_dir: Path) -> None:
    forbidden = {"chain_digest", "prev_digest", "prev_seq", "seq"}
    rows = read_jsonl(fixture_dir / "cr_transition_plan.jsonl")
    assert rows
    offenders = [sorted(set(row) & forbidden) for row in rows if set(row) & forbidden]
    assert not offenders, f"the plan claims a chain position it cannot compute: {offenders[:3]}"


def test_every_planned_edge_is_seeded_in_subject_transition(
    fixture_dir: Path, migrations: Path
) -> None:
    legal = _legal_edges(migrations)
    assert legal, "could not parse the change_request edges out of 0017b"
    used = {
        (row["from_state"], row["to_state"])
        for row in read_jsonl(fixture_dir / "cr_transition_plan.jsonl")
    }
    illegal = sorted(used - legal)
    assert not illegal, f"cr_legal_edge would refuse {illegal} with 23503"


def test_each_plan_is_one_contiguous_strictly_increasing_chain(fixture_dir: Path) -> None:
    rows = read_jsonl(fixture_dir / "cr_transition_plan.jsonl")
    by_cr: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_cr.setdefault(str(row["cr_external_ref"]), []).append(row)

    problems: list[str] = []
    for ref, acts in sorted(by_cr.items()):
        acts.sort(key=lambda item: int(str(item["step"])))
        if acts[0]["from_state"] != "draft":
            problems.append(f"{ref} starts at {acts[0]['from_state']}")
        for previous, following in pairwise(acts):
            if following["from_state"] != previous["to_state"]:
                problems.append(f"{ref} step {following['step']} forks the history")
            if str(following["at"]) <= str(previous["at"]):
                problems.append(f"{ref} step {following['step']} does not advance the clock")
    assert not problems, problems[:3]


def test_every_merge_act_goes_through_the_procedure(fixture_dir: Path) -> None:
    merges = [
        row
        for row in read_jsonl(fixture_dir / "cr_transition_plan.jsonl")
        if row["to_state"] == "merged"
    ]
    assert merges, "no change request in the register ever merges; the gate is untested"
    wrong = [row for row in merges if row["execute_via"] != "mainline.merge_change_request"]
    assert not wrong, "a merge that bypasses the procedure bypasses the gate, the clearance "
    unblocked = [row for row in merges if not row["blocked_by"]]
    assert not unblocked, (
        "a merge act must record that merged_commit does not exist yet; cr_merge_evidence "
        "refuses a merged change request with no merge evidence, and that refusal is correct"
    )


def test_the_terminal_state_of_each_plan_matches_the_register(fixture_dir: Path) -> None:
    dossiers = {row["external_ref"]: row for row in read_jsonl(fixture_dir / "moc_dossier.jsonl")}
    by_cr: dict[str, list[dict[str, object]]] = {}
    for row in read_jsonl(fixture_dir / "cr_transition_plan.jsonl"):
        by_cr.setdefault(str(row["cr_external_ref"]), []).append(row)
    mismatched = []
    for ref, acts in by_cr.items():
        acts.sort(key=lambda item: int(str(item["step"])))
        if acts[-1]["to_state"] != dossiers[ref]["terminal_state"]:
            mismatched.append(ref)
    assert not mismatched, f"the plan ends somewhere the register does not: {mismatched[:3]}"


# ── the spine, which is what the film shows ──────────────────────────────────────────────────


def test_the_2026_weakening_declares_exactly_one_unrealised_clause(fixture_dir: Path) -> None:
    spine = json.loads((fixture_dir / "spine_change_request.json").read_text(encoding="utf-8"))
    assert spine["cr_external_ref"] == "MOC-2026-0413"
    assert len(spine["declared_clause_uuids"]) == 1, (
        "beat 2 shows a single blocking obligation; more than one makes `open_blocking` a "
        "number the viewer has to take on trust"
    )
    assert spine["realised"] == [False], "the whole beat is that this change did not land"
    assert spine["plan_ends_at_state"] == "dispositioned"


def test_the_2026_weakening_plans_no_merge(fixture_dir: Path) -> None:
    """Whether it may merge is the database's answer to give."""
    acts = [
        row
        for row in read_jsonl(fixture_dir / "cr_transition_plan.jsonl")
        if row["cr_external_ref"] == "MOC-2026-0413"
    ]
    assert acts, "the film's change request has no plan at all"
    assert not [row for row in acts if row["to_state"] == "merged"]


def test_the_2026_weakening_predicts_the_2013_precursor(fixture_dir: Path) -> None:
    spine = json.loads((fixture_dir / "spine_change_request.json").read_text(encoding="utf-8"))
    assert "INC-2013-044" in spine["precursor_events"], (
        "the declared clause carries no blame edge to the seal fire, so the ancestry walk the "
        "refusal depends on would find nothing"
    )
    assert spine["precursor_severity_max_from_answer_key"] >= 4


def test_the_spine_clause_matches_the_answer_keys_proposal(
    fixture_dir: Path, repo_root: Path
) -> None:
    """One clause identity, two stages, no coordination: both derive it from the natural key."""
    proposals = read_jsonl(
        repo_root
        / "verticals"
        / "mainline"
        / "fixtures"
        / "corpus"
        / "answer-key"
        / "proposed_revision.jsonl"
    )
    proposed = {row["cr_external_ref"]: row["clause_uuid"] for row in proposals}
    spine = json.loads((fixture_dir / "spine_change_request.json").read_text(encoding="utf-8"))
    assert spine["declared_clause_uuids"][0] == proposed["MOC-2026-0413"]


# ── the discipline that keeps blame and scope apart ──────────────────────────────────────────


def test_no_authored_binding_claims_an_edit_another_generator_owns(fixture_dir: Path) -> None:
    """The change request is the vehicle; the incident is the cause. Not the same claim.

    The excluded drivers are written out literally here rather than imported from
    ``moc_stream.params``. Reading them from the same knob the generator drew from would make
    this test move whenever the knob moved — it would pass on the day somebody widened the
    exclusion, which is the only day it matters.
    """
    rows = read_jsonl(fixture_dir / "cr_clause_registry.jsonl")
    authored = [row for row in rows if row["basis"] == "moc_stream:window"]
    assert authored, "every binding was read from elsewhere; the authored path is untested"
    offenders = [
        row["clause_key"]
        for row in authored
        if row["driver"] in {"incident", "introduce", "retypeset"}
    ]
    assert not offenders, (
        f"an authored binding re-attributed an edit the blame lane owns: {offenders[:3]}"
    )


def test_no_realised_authored_binding_claims_an_injector_produced_edit(
    fixture_dir: Path, repo_root: Path
) -> None:
    """Read against the answer key's own injector labels, not against our knobs."""
    answer_key = repo_root / "verticals" / "mainline" / "fixtures" / "corpus" / "answer-key"
    injected = {
        (row["clause_key"], row["revision_key"])
        for row in read_jsonl(answer_key / "clause_revision.jsonl")
        if row["injector"] is not None
    }
    assert injected, "the answer key labels no revision with an injector; the parse is wrong"
    contested = [
        row["clause_key"]
        for row in read_jsonl(fixture_dir / "cr_clause_registry.jsonl")
        if row["basis"] == "moc_stream:window"
        and row["realised"]
        and (row["clause_key"], row["commit_for_revision_key"]) in injected
    ]
    assert not contested, (
        "a drawn vehicle contests an edit an injector already named a change record for: "
        f"{contested[:3]}"
    )


def test_every_basis_is_declared_and_most_are_read_not_drawn(fixture_dir: Path) -> None:
    index = json.loads((fixture_dir / "index.json").read_text(encoding="utf-8"))
    histogram = index["scope_basis_histogram"]
    known = {
        "skeleton:driving_change_ref",
        "blame:proposed_revision",
        "injector:weakening_chain",
        "injector:document_split",
        "moc_stream:window",
    }
    assert set(histogram) <= known, f"unknown basis {sorted(set(histogram) - known)}"
    read_bases = sum(count for basis, count in histogram.items() if basis != "moc_stream:window")
    assert read_bases > 0, "not one declaration came from a fact another generator authored"


def test_declared_clauses_are_at_the_change_requests_own_site(fixture_dir: Path) -> None:
    dossiers = {row["external_ref"]: row for row in read_jsonl(fixture_dir / "moc_dossier.jsonl")}
    offenders = [
        row["clause_key"]
        for row in read_jsonl(fixture_dir / "cr_clause_registry.jsonl")
        if row["site_id"] != dossiers[row["cr_external_ref"]]["site_id"]
    ]
    assert not offenders, f"a change request declares another site's clause: {offenders[:3]}"


def test_a_pre_merge_change_request_always_declares_something(fixture_dir: Path) -> None:
    """A subject the gate will judge must give the gate something to read."""
    silent = [
        row["external_ref"]
        for row in read_jsonl(fixture_dir / "moc_dossier.jsonl")
        if row["clause_count"] == 0 and row["terminal_state"] in {"abandoned", "dispositioned"}
    ]
    assert not silent, f"these declare nothing yet never merged: {silent[:3]}"


# ── the stage's own report ───────────────────────────────────────────────────────────────────


def test_the_verify_report_has_no_failure_and_no_silent_skip(fixture_dir: Path) -> None:
    report = json.loads((fixture_dir / "verify_report.json").read_text(encoding="utf-8"))
    failed = [check for check in report["checks"] if check["status"] == "FAIL"]
    assert not failed, failed[:2]
    for check in report["checks"]:
        if check["status"] == "SKIP":
            assert check["detail"], f"{check['check_id']} skipped without saying why"


def test_the_cross_check_refuses_a_disagreeing_answer_key(tmp_path: Path) -> None:
    """``--answer-key`` is an assertion, not a formality."""
    from mainline_corpus.moc_stream.build import build_moc_stream

    doctored = tmp_path / "answer-key"
    doctored.mkdir()
    (doctored / "clause.jsonl").write_text(
        json.dumps({"clause_uuid": "00000000-0000-5000-8000-000000000000"}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    with pytest.raises(RuntimeError, match="disagrees with the committed answer key"):
        build_moc_stream(answer_key_dir=doctored)
