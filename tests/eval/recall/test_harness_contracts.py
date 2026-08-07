# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Contracts the rest of the recall domain builds against. These must be GREEN.

Covers the parts of the harness that are interfaces rather than arithmetic: the time
wall and its refusal of ``AS OF SYSTEM TIME``, the qrels schema and its drift check, the
corpus loader's refusals, the CLI's exit codes, and the guarantee that no rendering path
in this package can emit a point estimate without its interval.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trappoint_recall.eval.ablation import AblationArm, DEFAULT_MATRIX, run_ablation_sync
from trappoint_recall.eval.backend import NullBackend, RetrievalBackend, RunTally, ScoredCandidate
from trappoint_recall.eval.cli import build_parser, main
from trappoint_recall.eval.corpus import CorpusError, EvalCorpus, EvalQuery, load_corpus
from trappoint_recall.eval.gates import G4ALPHA_GATE_IDS, evaluate_g4alpha, load_floors
from trappoint_recall.eval.harness import compute_metrics, run_evaluation_sync
from trappoint_recall.eval.qrels import (
    BLOCKING_RELEVANCE_FLOOR,
    Judgement,
    QrelError,
    QrelSet,
    load_qrels_jsonl,
    qrels_json_schema,
)
from trappoint_recall.eval.report import (
    PER_BOUND_STATEMENT,
    gate_status_document,
    render_gate_markdown,
    render_metrics_markdown,
)
from trappoint_recall.eval.splits import (
    AsOfSystemTimeRefused,
    SplitPolicy,
    SplitRecord,
    assert_no_as_of_system_time,
    refuse_as_of_system_time,
    temporally_blocked_split,
)

import g4alpha_lane as lane
from oracles import OracleBackend

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "packages" / "trappoint-recall"
SCHEMA_PATH = PACKAGE_ROOT / "src" / "trappoint_recall" / "eval" / "schema" / "qrels-v1.schema.json"


# --------------------------------------------------------------------------------------
# The time wall
# --------------------------------------------------------------------------------------


def test_as_of_system_time_is_refused_outright() -> None:
    """gc.ttlseconds is 4h; an AOST read cannot reach a wall months back (lead D12)."""
    with pytest.raises(AsOfSystemTimeRefused, match="gc.ttlseconds"):
        refuse_as_of_system_time("retro-recall time wall")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM event AS OF SYSTEM TIME '-3mo'",
        "select cue_id from event_cue as of system time follower_read_timestamp()",
        "SELECT 1 FROM t\n  AS  OF\tSYSTEM  TIME '2025-01-01'",
    ],
)
def test_a_query_carrying_as_of_system_time_is_refused(sql: str) -> None:
    with pytest.raises(AsOfSystemTimeRefused):
        assert_no_as_of_system_time(sql, context="corpus query")


def test_an_ordinary_query_is_not_refused() -> None:
    assert_no_as_of_system_time(
        "SELECT cue_id FROM event_cue WHERE occurred_at < $1 AND ingested_at < $1"
    )


def _record(doc: str, offset_days: int) -> SplitRecord:
    base = datetime(2025, 6, 1, tzinfo=UTC) + timedelta(days=offset_days)
    return SplitRecord(doc_id=doc, occurred_at=base, ingested_at=base, corpus_commit_at=base)


def test_the_wall_requires_all_three_predicates() -> None:
    wall = datetime(2025, 7, 1, tzinfo=UTC)
    policy = SplitPolicy(wall=wall, corpus_commit="sha256:deadbeef")
    before = datetime(2025, 5, 1, tzinfo=UTC)
    after = datetime(2025, 9, 1, tzinfo=UTC)

    assert policy.admits(
        SplitRecord(doc_id="ok", occurred_at=before, ingested_at=before, corpus_commit_at=before)
    )
    # Each predicate on its own is sufficient to exclude, which is the point: an event
    # that happened before the wall but was ingested after it is knowledge from the future.
    assert not policy.admits(
        SplitRecord(doc_id="late-ingest", occurred_at=before, ingested_at=after, corpus_commit_at=before)
    )
    assert not policy.admits(
        SplitRecord(doc_id="late-event", occurred_at=after, ingested_at=before, corpus_commit_at=before)
    )
    assert not policy.admits(
        SplitRecord(doc_id="late-commit", occurred_at=before, ingested_at=before, corpus_commit_at=after)
    )


def test_the_split_names_which_predicate_excluded_each_record() -> None:
    policy = SplitPolicy(wall=datetime(2025, 6, 15, tzinfo=UTC), corpus_commit="sha256:abc")
    split = temporally_blocked_split([_record("a", -20), _record("b", 20)], policy)
    assert split.indexable == ("a",)
    assert split.withheld == ("b",)
    assert split.rejections[0][1] == "occurred_at >= wall"


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SplitRecord(
            doc_id="naive",
            occurred_at=datetime(2025, 1, 1),  # noqa: DTZ001 - the defect under test
            ingested_at=datetime(2025, 1, 1, tzinfo=UTC),
            corpus_commit_at=datetime(2025, 1, 1, tzinfo=UTC),
        )


def test_a_split_policy_without_a_corpus_commit_is_refused() -> None:
    with pytest.raises(ValueError, match="corpus_commit"):
        SplitPolicy(wall=datetime(2025, 1, 1, tzinfo=UTC), corpus_commit="")


def test_the_policy_id_is_deterministic_and_legible() -> None:
    policy = SplitPolicy(wall=datetime(2025, 1, 1, tzinfo=UTC), corpus_commit="sha256:abc")
    twin = SplitPolicy(wall=datetime(2025, 1, 1, tzinfo=UTC), corpus_commit="sha256:abc")
    other = SplitPolicy(wall=datetime(2025, 1, 1, tzinfo=UTC), corpus_commit="sha256:def")
    assert policy.policy_id == twin.policy_id
    assert policy.policy_id != other.policy_id
    assert policy.policy_id.startswith("TB-2025-01-01-")


# --------------------------------------------------------------------------------------
# Judgements
# --------------------------------------------------------------------------------------


def test_grades_outside_the_umbrela_scale_are_refused() -> None:
    for bad in (-1, 4, 99):
        with pytest.raises(ValueError):
            Judgement(
                query_id="Q", doc_id="E", grade=bad, gold_set="G", judged_by="human"
            )


def test_contradictory_judgements_are_a_hard_error() -> None:
    with pytest.raises(QrelError, match="contradictory"):
        QrelSet.build(
            [
                Judgement(query_id="Q", doc_id="E", grade=3, gold_set="G", judged_by="human"),
                Judgement(query_id="Q", doc_id="E", grade=0, gold_set="G", judged_by="llm"),
            ]
        )


def test_unjudged_is_distinct_from_grade_zero() -> None:
    qrels = QrelSet.build(
        [Judgement(query_id="Q", doc_id="E-0", grade=0, gold_set="G", judged_by="human")]
    )
    assert qrels.grade("Q", "E-0") == 0
    assert qrels.grade("Q", "E-1") is None
    assert qrels.grade("Q-other", "E-0") is None


def test_the_relevance_floor_is_two() -> None:
    assert BLOCKING_RELEVANCE_FLOOR == 2
    qrels = QrelSet.build(
        [
            Judgement(query_id="Q", doc_id="E-1", grade=1, gold_set="G", judged_by="human"),
            Judgement(query_id="Q", doc_id="E-2", grade=2, gold_set="G", judged_by="human"),
        ]
    )
    assert qrels.relevant_docs("Q") == {"E-2"}


def test_the_committed_qrels_schema_has_not_drifted() -> None:
    """The schema file is generated from the model; a drift means one of them moved."""
    assert SCHEMA_PATH.is_file(), f"committed schema missing at {SCHEMA_PATH}"
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == qrels_json_schema(), (
        "the committed qrels JSON Schema no longer matches the pydantic model; "
        "regenerate with `trappoint-recall-eval schema --out <path>`"
    )


def test_a_malformed_qrels_line_names_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "qrels.jsonl"
    path.write_text(
        json.dumps(
            {"query_id": "Q", "doc_id": "E", "grade": 3, "gold_set": "G", "judged_by": "human"}
        )
        + "\n{ not json\n",
        encoding="utf-8",
    )
    with pytest.raises(QrelError, match=":2:"):
        load_qrels_jsonl(path)


# --------------------------------------------------------------------------------------
# Corpus refusals
# --------------------------------------------------------------------------------------


def test_a_retro_permit_without_a_time_wall_is_refused() -> None:
    with pytest.raises(CorpusError, match="time wall"):
        EvalQuery(
            query_id="Q",
            kind="retro",
            text="t",
            site_id="S",
            activity_path="/a",
            asset_class="x",
            severity=5,
            truth_doc_id="E-0",
        )


def test_a_routine_permit_carrying_a_truth_precursor_is_refused() -> None:
    with pytest.raises(CorpusError, match="negative control"):
        EvalQuery(
            query_id="Q",
            kind="routine",
            text="t",
            site_id="S",
            activity_path="/a",
            asset_class="x",
            truth_doc_id="E-0",
        )


def test_a_corpus_without_a_split_policy_is_refused(tmp_path: Path) -> None:
    (tmp_path / "queries.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "qrels.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(CorpusError, match="split.json is mandatory"):
        load_corpus(tmp_path)


def test_the_selftest_corpus_loads_and_declares_itself(corpus: EvalCorpus) -> None:
    assert len(corpus.queries) > 0
    assert corpus.split_policy_id.startswith("TB-")
    assert corpus.provenance


# --------------------------------------------------------------------------------------
# Floors
# --------------------------------------------------------------------------------------


def test_the_committed_floors_match_the_architecture() -> None:
    floors = load_floors()
    gates = floors["gates"]
    assert isinstance(gates, dict)
    assert set(gates) >= set(G4ALPHA_GATE_IDS)
    assert gates["retro_recall_at_3_sev5"]["point_floor"] == 0.90
    assert gates["retro_recall_at_3_sev5"]["lower_bound_floor"] == 0.80
    assert gates["p_at_block"]["point_floor"] == 0.75
    assert gates["nuisance_rate"]["ceiling"] == 0.03
    assert gates["mean_blocking_checks_per_permit"]["ceiling"] == 1.0
    assert gates["mean_blocking_checks_per_permit"]["hard_cap_probabilistic"] == 3
    assert floors["ratchet"] == "upward-only"


# --------------------------------------------------------------------------------------
# Rendering: the interval cannot be dropped
# --------------------------------------------------------------------------------------


def test_every_rendered_measurement_carries_its_interval(corpus: EvalCorpus) -> None:
    run = run_evaluation_sync(OracleBackend(), corpus, k=10)
    bundle = compute_metrics(run, corpus)
    for name, measurement in bundle.measurements.items():
        rendered = measurement.render()
        if measurement.defined:
            assert "[" in rendered and "]" in rendered, f"{name} rendered without an interval"
            assert f"n={measurement.n}" in rendered
            assert corpus.split_policy_id in rendered
        else:
            assert "UNDEFINED" in rendered


def test_reports_stamp_the_split_policy_and_the_per_bound(corpus: EvalCorpus) -> None:
    run = run_evaluation_sync(OracleBackend(), corpus, k=10)
    bundle = compute_metrics(run, corpus)
    gates = evaluate_g4alpha(bundle)
    metrics_md = render_metrics_markdown(bundle)
    gates_md = render_gate_markdown(bundle, gates)
    for document in (metrics_md, gates_md):
        assert corpus.split_policy_id in document
        assert PER_BOUND_STATEMENT in document
    assert "does not prove exhaustion of the corpus" in PER_BOUND_STATEMENT


def test_the_status_document_records_a_colour_not_a_skip(corpus: EvalCorpus) -> None:
    run = run_evaluation_sync(NullBackend(), corpus, k=10)
    bundle = compute_metrics(run, corpus)
    document = gate_status_document(bundle, evaluate_g4alpha(bundle))
    assert document["lane_colour"] == "RED"
    assert document["gates_total"] == len(G4ALPHA_GATE_IDS)
    assert document["gates_passed"] == 0
    assert json.dumps(document)  # must be serialisable for the CI artefact


# --------------------------------------------------------------------------------------
# Backend contract
# --------------------------------------------------------------------------------------


def test_a_raw_cosine_is_refused_as_a_probability() -> None:
    with pytest.raises(ValueError, match="calibrated probability"):
        ScoredCandidate(
            doc_id="E",
            rank=1,
            p_relevant=1.7,
            tau_applied=0.5,
            outcome="blocking",
            severity=5,
            channel="C",
            origin="recall_probabilistic",
        )


def test_the_null_backend_satisfies_the_protocol() -> None:
    backend: RetrievalBackend = NullBackend()
    assert isinstance(backend, RetrievalBackend)
    assert backend.name == "null"


def test_enumerating_a_tally_matches_the_candidates() -> None:
    candidates = [
        ScoredCandidate(
            doc_id=f"E-{i}",
            rank=i + 1,
            p_relevant=0.5,
            tau_applied=0.5,
            outcome=outcome,
            severity=5,
            channel="C",
            origin="recall_probabilistic",
        )
        for i, outcome in enumerate(("blocking", "advisory", "silenced", "deduped"))
    ]
    tally = RunTally.enumerate_from(candidates)
    assert tally.n_candidates == 4
    assert tally.conserved


# --------------------------------------------------------------------------------------
# Ablation and CLI
# --------------------------------------------------------------------------------------


def test_the_default_matrix_covers_the_published_ladder() -> None:
    ids = {arm.arm_id for arm in DEFAULT_MATRIX}
    assert {"L0-A", "L1-AB", "L2-ABC", "L3-ABCD", "L4-ABCD-rerank", "L5-ABCD-rerank-sga"} <= ids
    assert {"V-narrative", "V-noprefix", "V-256d"} <= ids
    assert len([a for a in DEFAULT_MATRIX if a.arm_id.startswith("V-beam")]) == 5


def test_rerank_without_a_probabilistic_channel_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing to rerank"):
        AblationArm(arm_id="bad", label="bad", channels=("A", "B"), rerank=True)


def test_the_ablation_table_renders_every_cell_with_an_interval(corpus: EvalCorpus) -> None:
    matrix = (
        AblationArm(arm_id="L0-A", label="A only", channels=("A",)),
        AblationArm(arm_id="L2-ABC", label="A+B+C", channels=("A", "B", "C")),
    )
    table = run_ablation_sync(lambda arm: OracleBackend(name=arm.arm_id), corpus, matrix=matrix)
    markdown = table.to_markdown()
    assert "| arm | configuration |" in markdown
    assert markdown.count("[") >= 2 * len(matrix)
    payload = json.loads(table.to_json())
    assert len(payload["rows"]) == len(matrix)
    assert table.delta("L2-ABC", "retro_recall_at_3_sev5") == pytest.approx(0.0)


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_parser().parse_args(["--help"])
    assert exit_info.value.code == 0
    assert "trappoint-recall-eval" in capsys.readouterr().out


def test_cli_gates_exits_one_when_the_lane_is_red(corpus_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "status.json"
    code = main(
        ["gates", "--corpus", str(corpus_path), "--format", "json", "--out", str(out)]
    )
    assert code == 1, "a red lane must not exit zero"
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["lane_colour"] == "RED"


def test_cli_reports_a_missing_corpus_as_a_usage_error(tmp_path: Path) -> None:
    code = main(["gates", "--corpus", str(tmp_path / "nope")])
    assert code == 2, "a missing corpus must be distinguishable from a failing gate"


def test_cli_floors_and_schema_round_trip(tmp_path: Path) -> None:
    floors_out = tmp_path / "floors.json"
    schema_out = tmp_path / "qrels.schema.json"
    assert main(["floors", "--out", str(floors_out)]) == 0
    assert main(["schema", "--out", str(schema_out)]) == 0
    assert json.loads(floors_out.read_text(encoding="utf-8"))["floors_version"]
    assert json.loads(schema_out.read_text(encoding="utf-8")) == qrels_json_schema()


def test_cli_selfcheck_passes(tmp_path: Path) -> None:
    assert main(["selfcheck", "--format", "json", "--out", str(tmp_path / "sc.json")]) == 0


# --------------------------------------------------------------------------------------
# The CI lane's decision table
# --------------------------------------------------------------------------------------
#
# The lane runs pytest in-process, so exercising ``run_lane`` from inside a pytest
# session would nest one run inside another. ``reconcile`` is pure for exactly this
# reason: the table below is the whole decision, tested without recursion.


def _outcome(test_name: str, outcome: str) -> lane.TestOutcome:
    return lane.TestOutcome(
        nodeid=f"tests/eval/recall/test_g4alpha_gates.py::{test_name}",
        test_name=test_name,
        gate_id=lane.GATE_TEST_NAMES[test_name],
        outcome=outcome,
        duration_s=0.0,
        detail="",
    )


def _full_suite(outcome: str) -> list[lane.TestOutcome]:
    return [_outcome(name, outcome) for name in lane.GATE_TEST_NAMES]


def test_the_lane_maps_every_gate_to_exactly_one_test() -> None:
    """A gate with no test, or a test with no gate, must be impossible to ship."""
    assert set(lane.GATE_TEST_NAMES.values()) == set(G4ALPHA_GATE_IDS)
    assert len(lane.GATE_TEST_NAMES) == len(G4ALPHA_GATE_IDS)


def test_the_committed_expectation_is_red_today() -> None:
    """PL-2: the repository currently commits to a RED G4-alpha lane."""
    expectation = lane.load_expectation()
    assert expectation.colour == "RED"
    assert expectation.gate_tests == len(G4ALPHA_GATE_IDS)
    assert expectation.flip_procedure, "flipping the expectation must have a written procedure"


def test_red_when_red_is_expected_exits_zero() -> None:
    expectation = lane.load_expectation()
    colour, verdict, code, _ = lane.reconcile(_full_suite("failed"), expectation)
    assert (colour, verdict, code) == ("RED", "AS_EXPECTED", lane.EXIT_MATCHES_EXPECTATION)


def test_green_while_the_repository_still_expects_red_fails_the_lane() -> None:
    """Going green is a real result that needs the expectation flipped in a PR."""
    expectation = lane.load_expectation()
    colour, verdict, code, message = lane.reconcile(_full_suite("passed"), expectation)
    assert (colour, verdict, code) == ("GREEN", "UNEXPECTED", lane.EXIT_UNEXPECTED_COLOUR)
    assert "pull request" in message


def test_a_regression_from_green_to_red_fails_the_lane() -> None:
    expectation = lane.Expectation(
        colour="GREEN",
        gate_tests=len(G4ALPHA_GATE_IDS),
        since="",
        reason="",
        flip_procedure="",
        authority="",
        source="synthetic",
    )
    colour, verdict, code, message = lane.reconcile(_full_suite("failed"), expectation)
    assert (colour, verdict, code) == ("RED", "UNEXPECTED", lane.EXIT_UNEXPECTED_COLOUR)
    assert "DEMOTE" in message, "the pre-committed response must be named in the failure"


@pytest.mark.parametrize("blocked", ["skipped", "errored", "xfailed", "xpassed"])
def test_a_gate_that_never_ran_is_undetermined_not_a_colour(blocked: str) -> None:
    """A release gate that can be skipped or xfailed is not a release gate."""
    expectation = lane.load_expectation()
    outcomes = _full_suite("failed")
    outcomes[0] = _outcome(outcomes[0].test_name, blocked)
    colour, verdict, code, message = lane.reconcile(outcomes, expectation)
    assert (colour, verdict, code) == (
        "UNDETERMINED",
        "UNDETERMINED",
        lane.EXIT_CANNOT_DETERMINE,
    )
    assert blocked in message


def test_an_empty_collection_is_undetermined_not_green() -> None:
    """A mistyped marker collects nothing; nothing must never read as a pass."""
    expectation = lane.load_expectation()
    colour, _, code, message = lane.reconcile([], expectation)
    assert (colour, code) == ("UNDETERMINED", lane.EXIT_CANNOT_DETERMINE)
    assert "g4alpha" in message


def test_a_missing_gate_test_is_undetermined() -> None:
    expectation = lane.load_expectation()
    outcomes = _full_suite("passed")[:-1]
    colour, _, code, message = lane.reconcile(outcomes, expectation)
    assert (colour, code) == ("UNDETERMINED", lane.EXIT_CANNOT_DETERMINE)
    assert "missing" in message


def test_the_expectation_file_must_be_unambiguous(tmp_path: Path) -> None:
    bad = tmp_path / "expected.json"
    bad.write_text(json.dumps({"expected": "maybe", "expected_gate_tests": 5}), encoding="utf-8")
    with pytest.raises(lane.LaneError, match="RED"):
        lane.load_expectation(bad)

    missing = tmp_path / "absent.json"
    with pytest.raises(lane.LaneError, match="will not infer"):
        lane.load_expectation(missing)
