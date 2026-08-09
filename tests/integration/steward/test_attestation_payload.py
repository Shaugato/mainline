# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The completion test: a fixture run produces a complete, checkable `ops_attestation`.

Every assertion here is one clause of the Steward's brief:

* the payload carries ``skill_sha256``, ``model_id``, ``prompt_version``,
  ``mcp_cluster_id`` and ``agent_identity``;
* every finding carries the exact SQL it ran and the SHA-256 of the result rows;
* the SQL came from the contract and not from the model;
* the leaf hash is the same construction ``mainline.ledger_intake`` uses, so a verifier
  written for the custody ledger recognises it;
* and the run is idempotent on ``(schedule_id, occurrence_ts)``.

No network, no cluster, no Cloud organisation, no AWS.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest
from mainline_steward import (
    ENTRY_KIND,
    EVIDENCE_OF_REVIEW,
    BytesEncoding,
    Emitter,
    OccurrenceAlreadyAttested,
    RunOutcome,
    StewardRun,
    load_schedules,
)
from mainline_steward.errors import AttestationRefused, ScheduleRefused
from mainline_steward.findings import sentence
from mainline_steward.schedule import parse_schedules

from trappoint_jcs import canonicalise, canonicalise_payload


@pytest.fixture
def runner(run_config, client):
    return StewardRun(run_config, client=client, emitter=Emitter(client, dry_run=True))


@pytest.fixture
def occurrence(run_config):
    book = load_schedules(run_config.schedules_path)
    return book.by_id("observability-nightly").occurrence("2026-08-04T15:00:00Z")


@pytest.fixture
def result(runner, occurrence):
    return runner.execute(occurrence)


class TestPayloadCarriesTheRequiredFacts:
    def test_the_five_named_fields_are_present_and_non_empty(self, result):
        payload = result.attestation.payload
        assert len(payload["identity"]["agent_identity"]) == 64
        assert payload["identity"]["model_id"] == "au.anthropic.claude-opus-5"
        assert len(payload["identity"]["prompt_version"]) == 64
        assert payload["mcp"]["mcp_cluster_id"] == "cl-steward-fixture"
        assert payload["skills"], "the observability run consumes three pinned skills"
        for skill in payload["skills"]:
            assert len(skill["skill_sha256"]) == 64
            assert len(skill["commit"]) == 40
            assert skill["pin_state"] in {"enforced", "recorded_only"}

    def test_the_disclaimer_is_in_the_payload_itself(self, result):
        assert result.attestation.payload["disclaimer"] == EVIDENCE_OF_REVIEW

    def test_the_seven_identity_inputs_are_carried_in_clear(self, result):
        identity = result.attestation.payload["identity"]
        for name in (
            "agent_name",
            "sql_role",
            "iam_role_arn",
            "prompt_version",
            "model_id",
            "inference_profile_arn",
            "schema_version",
        ):
            assert identity[name], f"{name} must be recomputable by a reader"
        assert identity["sql_role"] == "mainline_auditor"
        assert identity["identity_source"] in {"local_fallback", "explicit"} or identity[
            "identity_source"
        ].startswith("mainline_provenance")

    def test_the_runtime_records_the_allowlist_it_actually_ran_under(self, result):
        allowed = result.attestation.payload["runtime"]["allowed_tools"]
        assert any("select_query" in entry for entry in allowed)
        assert any("insert_rows" in entry for entry in allowed)
        assert not any("create_table" in entry for entry in allowed)


class TestEveryFindingIsCheckable:
    def test_each_finding_carries_its_statement_and_its_result_hash(self, result):
        assert result.findings
        for finding in result.attestation.payload["findings"]:
            assert finding["statement"].startswith("SELECT * FROM mainline_audit.")
            assert finding["result_sha256"] is not None
            assert len(finding["result_sha256"]) == 64
            assert finding["narrative_is_not_evidence"] is True

    def test_the_result_hash_is_reproducible_from_the_rows_the_server_sent(self, result, ops_rows):
        by_subject = {f.subject: f for f in result.findings}
        finding = by_subject["mainline_audit.v_gate_latency_daily"]
        expected = hashlib.sha256(
            canonicalise([dict(row) for row in ops_rows["v_gate_latency_daily"]])
        ).hexdigest()
        assert finding.result_sha256 == expected

    def test_the_statement_came_from_the_contract_not_from_a_model(
        self, result, runner, occurrence
    ):
        contracted = {view.statement for view in runner.resolve_views(occurrence)}
        for finding in result.findings:
            assert finding.statement in contracted

    def test_no_finding_carries_a_severity(self, result):
        for finding in result.attestation.payload["findings"]:
            assert "severity" not in finding
            assert "risk" not in finding
            assert "priority" not in finding


class TestTheNarrativeCannotBecomeEvidence:
    def test_prose_is_attached_only_to_findings_that_already_existed(self, result):
        by_subject = {f.subject: f for f in result.findings}
        assert by_subject["mainline_audit.v_gate_latency_daily"].narrative
        assert "mainline_audit.v_nonexistent_view" not in by_subject

    def test_a_narrative_for_an_unread_view_is_dropped_and_counted(self, result):
        assert result.narratives.dropped_subjects == ("mainline_audit.v_nonexistent_view",)
        assert result.attestation.payload["runtime"]["narrative_dropped_subjects"] == [
            "mainline_audit.v_nonexistent_view"
        ]

    def test_the_transcript_is_hashed_as_it_arrived(self, result, run_config):
        expected = hashlib.sha256(run_config.transcript.read_bytes()).hexdigest()
        assert result.attestation.payload["runtime"]["transcript_sha256"] == expected

    def test_an_unparseable_transcript_costs_prose_and_not_the_attestation(
        self, run_config, client, tmp_path, occurrence
    ):
        broken = tmp_path / "broken.json"
        broken.write_text("the model wrote prose and no envelope", encoding="utf-8")
        config = replace(run_config, transcript=broken, state_dir=tmp_path / "state-2")
        result = StewardRun(config, client=client, emitter=Emitter(client, dry_run=True)).execute(
            occurrence
        )
        assert result.narratives.source == "unparsed"
        assert result.attestation.outcome is RunOutcome.VERIFIED
        assert all(f.narrative is None for f in result.findings)


class TestTheCommitment:
    def test_the_leaf_hash_is_the_ledger_construction(self, result):
        expected = hashlib.sha256(b"\x00" + result.attestation.canon_bytes).digest()
        assert result.attestation.leaf_hash == expected
        assert result.attestation.leaf_hash_hex == expected.hex()

    def test_the_canonical_bytes_on_disk_are_what_the_digest_commits_to(self, result):
        assert result.detail_path is not None
        assert result.detail_path.read_bytes() == result.attestation.canon_bytes
        recomputed = hashlib.sha256(b"\x00" + result.detail_path.read_bytes()).hexdigest()
        assert recomputed == result.row["detail_sha256"].removeprefix("\\x")

    def test_the_payload_is_float_free_so_it_canonicalises_as_a_ledger_payload(self, result):
        # CU-5. The server returned floats (restart_ratio, not_checked_ratio); they were
        # hashed into result_sha256 and never carried into the evidentiary payload.
        assert canonicalise_payload(dict(result.attestation.payload))

    def test_the_row_is_the_one_permitted_shape(self, result):
        row = result.row
        assert set(row) == {
            "attestor",
            "attestor_kind",
            "subject_kind",
            "subject_ref",
            "outcome",
            "detail_sha256",
        }
        assert row["attestor_kind"] == "auditor"
        assert row["subject_kind"] == "view_result"
        assert row["outcome"] in {"verified", "indeterminate", "failed"}
        assert row["subject_ref"] == f"{ENTRY_KIND}:{result.occurrence.key}"

    def test_the_bytes_encoding_is_switchable_in_one_place(self, result):
        hex_row = result.attestation.row(encoding=BytesEncoding.HEX_ESCAPE)
        b64_row = result.attestation.row(encoding=BytesEncoding.BASE64)
        assert hex_row.detail_sha256.startswith("\\x")
        assert not b64_row.detail_sha256.startswith("\\x")
        assert hex_row.subject_ref == b64_row.subject_ref

    def test_a_dry_run_sends_nothing(self, result, transport):
        assert result.emitted is False
        assert not [name for name, _ in transport.calls if name == "insert_rows"]


class TestOutcomeReportsCompletenessNotCondition:
    def test_all_reads_answered_is_verified(self, result):
        assert result.attestation.outcome is RunOutcome.VERIFIED
        assert (
            "NOT a statement that the cluster is healthy"
            in (result.attestation.payload["run"]["outcome_means"])
        )

    def test_one_failed_read_makes_the_run_indeterminate(self, run_config, make_client, occurrence):
        client, _ = make_client(failing_views=["v_changefeed_health"])
        result = StewardRun(
            run_config, client=client, emitter=Emitter(client, dry_run=True)
        ).execute(occurrence)
        assert result.attestation.outcome is RunOutcome.INDETERMINATE
        unanswered = [f for f in result.findings if f.outcome == "unanswered"]
        assert len(unanswered) == 1
        assert unanswered[0].subject == "mainline_audit.v_changefeed_health"
        assert unanswered[0].detail, "the surface's refusal is recorded, not swallowed"

    def test_a_failed_read_still_carries_the_statement_a_reader_can_re_run(
        self, run_config, make_client, occurrence
    ):
        client, _ = make_client(failing_views=["v_ledger_health"])
        result = StewardRun(
            run_config, client=client, emitter=Emitter(client, dry_run=True)
        ).execute(occurrence)
        unanswered = next(f for f in result.findings if f.outcome == "unanswered")
        assert unanswered.statement.startswith("SELECT * FROM mainline_audit.v_ledger_health")
        assert unanswered.result_sha256 is None


class TestIdempotency:
    def test_the_occurrence_key_is_schedule_and_scheduled_time(self, occurrence):
        assert occurrence.key == "observability-nightly@2026-08-04T15:00:00Z"

    def test_a_redelivery_of_a_completed_occurrence_is_refused(self, runner, occurrence, result):
        assert result.attestation.outcome is RunOutcome.VERIFIED
        with pytest.raises(OccurrenceAlreadyAttested):
            runner.execute(occurrence)

    def test_a_failed_run_gives_its_claim_back(self, run_config, make_client, occurrence):
        class RefusingEmitter(Emitter):
            def emit(self, attestation):  # noqa: ARG002 — the refusal is the point
                raise AttestationRefused("the surface said no")

        client, _ = make_client()
        runner = StewardRun(run_config, client=client, emitter=RefusingEmitter(client))
        with pytest.raises(AttestationRefused):
            runner.execute(occurrence)
        # The second attempt reaches the emitter again rather than the guard, which is
        # what "a genuine retry of a failed occurrence can run" means.
        with pytest.raises(AttestationRefused):
            runner.execute(occurrence)

    def test_normalising_the_scheduled_time_collapses_three_spellings_into_one_key(
        self, run_config
    ):
        schedule = load_schedules(run_config.schedules_path).by_id("observability-nightly")
        keys = {
            schedule.occurrence(value).key
            for value in (
                "2026-08-04T15:00:00Z",
                "2026-08-04T15:00:00+00:00",
                "2026-08-05T01:00:00+10:00",
            )
        }
        assert len(keys) == 1


class TestCustodianPatrol:
    @pytest.fixture
    def patrol_result(self, run_config, client, tmp_path):
        book = load_schedules(run_config.schedules_path)
        occurrence = book.by_id("custodian-patrol").occurrence("2026-08-04T15:00:00Z")
        config = replace(run_config, state_dir=tmp_path / "state-patrol")
        return StewardRun(config, client=client, emitter=Emitter(client, dry_run=True)).execute(
            occurrence
        )

    def test_it_reads_the_three_i4_cloud_pages_and_hashes_each(self, patrol_result):
        sources = {f.subject for f in patrol_result.findings if f.source == "ccloud"}
        assert {"cluster_info", "backup_list", "audit_list"} <= sources
        for finding in patrol_result.findings:
            if finding.source == "ccloud":
                assert len(finding.result_sha256 or "") == 64

    def test_the_shim_provenance_is_a_finding_so_a_fixture_run_is_never_mistaken_for_live(
        self, patrol_result
    ):
        provenance = next(f for f in patrol_result.findings if f.subject == "shim_provenance")
        assert "fixtures:" in provenance.statement

    def test_the_audit_window_is_derived_from_the_occurrence_not_from_now(self, run_config):
        book = load_schedules(run_config.schedules_path)
        occurrence = book.by_id("custodian-patrol").occurrence("2026-08-04T15:00:00Z")
        assert occurrence.since == "2026-08-04T14:40:00Z"

    def test_the_report_renders_with_the_disclaimer_on_it(self, patrol_result):
        rendered = patrol_result.render()
        assert sentence(EVIDENCE_OF_REVIEW) in rendered
        assert "NOT SENT (dry run)" in rendered


class TestContractDiscipline:
    def test_the_contract_of_record_wins_when_it_exists(self, contract_path, contract_of_record):
        if contract_of_record.is_file():
            assert contract_path == contract_of_record

    def test_a_schedule_naming_an_uncontracted_view_is_refused(self, run_config, client):
        document = {
            "version": 1,
            "schedules": [
                {
                    "schedule_id": "invented-schedule",
                    "kind": "mcp_ops",
                    "expression": "rate(1 hour)",
                    "prompt": "observability-nightly.md",
                    "views": ["v_view_that_is_not_contracted"],
                }
            ],
        }
        occurrence = (
            parse_schedules(document).by_id("invented-schedule").occurrence("2026-08-04T15:00:00Z")
        )
        runner = StewardRun(run_config, client=client, emitter=Emitter(client, dry_run=True))
        with pytest.raises(ScheduleRefused):
            runner.resolve_views(occurrence)

    def test_the_pretty_report_and_the_canonical_bytes_are_the_same_document(self, result):
        pretty = json.loads(json.dumps(dict(result.attestation.payload)))
        assert canonicalise_payload(pretty) == result.attestation.canon_bytes
