# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The command surface the entrypoint drives, and the live lane that refuses to fake it.

Every verb `entrypoint.sh` calls is exercised here against the real app directory, because
a shell script whose commands have never been run is a shell script that works until the
first occurrence. The live lane — the one that would talk to
``https://cockroachlabs.cloud/mcp`` — **skips** with a reason naming the missing variable.
A suite that went green because it had nothing to talk to would be green-by-absence, which
is the failure mode this repository exists to refuse.
"""

from __future__ import annotations

import os
import re

import pytest
from mainline_steward.cli import EXIT_OK, EXIT_REFUSED, build_parser, main


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("CC_MCP_API_KEY") or os.environ.get("MAINLINE_MCP_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    return (api_key, cluster) if api_key and cluster else None


LIVE_REASON = (
    "no Managed-MCP credential: set CC_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID. This "
    "SKIPS rather than passing, because a green attest run with nothing to talk to would "
    "assert nothing about the one write path this package has."
)


@pytest.fixture
def app(paths) -> str:
    return str(paths["app"])


class TestTheVerbsTheEntrypointCalls:
    def test_schedules_lists_the_four_occurrences(self, app, capsys):
        assert main(["schedules", "--app-dir", app]) == EXIT_OK
        out = capsys.readouterr().out
        for schedule_id in (
            "observability-nightly",
            "security-weekly",
            "operations-weekly",
            "custodian-patrol",
        ):
            assert schedule_id in out

    def test_schedules_json_is_machine_readable_for_the_infra_lead(self, app, capsys):
        import json

        assert main(["schedules", "--app-dir", app, "--json"]) == EXIT_OK
        document = json.loads(capsys.readouterr().out)
        assert document["timezone"] == "Australia/Brisbane"
        assert {entry["schedule_id"] for entry in document["schedules"]} == {
            "observability-nightly",
            "security-weekly",
            "operations-weekly",
            "custodian-patrol",
        }

    def test_skills_commit_prints_one_object_name(self, app, capsys):
        assert main(["skills", "commit", "--app-dir", app]) == EXIT_OK
        printed = capsys.readouterr().out.strip()
        assert re.fullmatch(r"[0-9a-f]{40}", printed)

    def test_skills_verify_digests_a_checkout(self, app, skills_root, capsys):
        assert (
            main(
                [
                    "skills",
                    "verify",
                    "--app-dir",
                    app,
                    "--skills-root",
                    str(skills_root),
                    "--schedule-id",
                    "observability-nightly",
                ]
            )
            == EXIT_OK
        )
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(lines) == 3
        assert all("recorded_only" in line for line in lines)

    def test_skills_stage_copies_and_never_symlinks(self, app, skills_root, tmp_path):
        destination = tmp_path / "claude-skills"
        assert (
            main(
                [
                    "skills",
                    "stage",
                    "--app-dir",
                    app,
                    "--skills-root",
                    str(skills_root),
                    "--schedule-id",
                    "security-weekly",
                    "--destination",
                    str(destination),
                ]
            )
            == EXIT_OK
        )
        staged = sorted(p.name for p in destination.iterdir())
        assert staged == [
            "auditing-cloud-cluster-security",
            "configuring-audit-logging",
            "hardening-user-privileges",
        ]
        for entry in destination.iterdir():
            assert not entry.is_symlink()
            assert (entry / "SKILL.md").is_file()

    def test_stage_is_idempotent_across_two_occurrences(self, app, skills_root, tmp_path):
        destination = tmp_path / "claude-skills"
        argv = [
            "skills",
            "stage",
            "--app-dir",
            app,
            "--skills-root",
            str(skills_root),
            "--schedule-id",
            "operations-weekly",
            "--destination",
            str(destination),
        ]
        assert main(argv) == EXIT_OK
        assert main(argv) == EXIT_OK
        assert len(list(destination.iterdir())) == 3

    def test_prompt_version_only_prints_a_digest(self, app, capsys):
        assert (
            main(
                [
                    "prompt",
                    "--app-dir",
                    app,
                    "observability-nightly",
                    "2026-08-04T15:00:00Z",
                    "--version-only",
                ]
            )
            == EXIT_OK
        )
        assert re.fullmatch(r"[0-9a-f]{64}", capsys.readouterr().out.strip())

    def test_prompt_renders_a_complete_prompt(self, app, capsys):
        assert (
            main(["prompt", "--app-dir", app, "custodian-patrol", "2026-08-04T15:00:00Z"])
            == EXIT_OK
        )
        text = capsys.readouterr().out
        assert "Custody of the custodian" in text
        assert "{{" not in text

    def test_allowlist_mcp_only_returns_exactly_eight_verbs(self, app, capsys):
        assert main(["allowlist", "--app-dir", app, "--mcp-only"]) == EXIT_OK
        entries = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(entries) == 8
        assert all(entry.startswith("mcp__crdb__") for entry in entries)


class TestRefusalsAreExitCodesNotTracebacks:
    def test_an_unknown_schedule_is_a_refusal(self, app, capsys):
        assert main(["prompt", "--app-dir", app, "not-a-schedule", "2026-08-04T15:00:00Z"]) == (
            EXIT_REFUSED
        )
        assert "REFUSED" in capsys.readouterr().err

    def test_attest_without_a_credential_refuses_and_names_the_variables(
        self, app, monkeypatch, capsys
    ):
        monkeypatch.delenv("CC_MCP_API_KEY", raising=False)
        monkeypatch.delenv("MAINLINE_MCP_CLUSTER_ID", raising=False)
        monkeypatch.setenv("MAINLINE_SITE_CODE", "BLK-07")
        monkeypatch.setenv("MAINLINE_SCHEMA_VERSION", "sha256:x")
        monkeypatch.setenv("MAINLINE_STEWARD_TASK_ROLE_ARN", "arn:aws:iam::0:role/x")
        monkeypatch.setenv("MAINLINE_STEWARD_INFERENCE_PROFILE_ARN", "au.anthropic.claude-opus-5")
        monkeypatch.setenv("MAINLINE_STEWARD_CLAUDE_CODE_VERSION", "2.1.221")
        status = main(["attest", "--app-dir", app, "observability-nightly", "2026-08-04T15:00:00Z"])
        assert status == EXIT_REFUSED
        assert "CC_MCP_API_KEY" in capsys.readouterr().err

    def test_every_command_the_entrypoint_calls_is_a_verb_this_parser_declares(self, paths):
        # The reverse direction of the usual check: the shell is the caller, so what must
        # not drift is that every `mainline-steward <verb>` in it exists. A verb the
        # parser declares and the shell never calls is fine — `schedules --json` is for
        # the infra lead's OpenTofu, not for the container.
        entrypoint = (paths["app"] / "entrypoint.sh").read_text(encoding="utf-8")
        called = set(re.findall(r"mainline-steward ([a-z-]+)", entrypoint))
        assert called == {"skills", "prompt", "allowlist", "attest"}
        declared = {
            choice
            for action in build_parser()._subparsers._group_actions
            for choice in getattr(action, "choices", {})
        }
        assert called <= declared, (
            f"the entrypoint calls verbs that do not exist: {called - declared}"
        )
        assert "schedules" in declared


class TestTheLiveLaneSkipsRatherThanPasses:
    @pytest.mark.requires_cluster
    @pytest.mark.skipif(_credentials() is None, reason=LIVE_REASON)
    def test_the_managed_endpoint_advertises_the_eight_verbs_we_rely_on(
        self,
    ):  # pragma: no cover - never runs in CI
        from mainline_mcp.client import Client
        from mainline_mcp.limits import READ_VERBS, WRITE_VERB

        credentials = _credentials()
        assert credentials is not None
        api_key, cluster_id = credentials
        with Client.connect(api_key=api_key, cluster_id=cluster_id) as client:
            names = set(client.tool_names())
        assert set(READ_VERBS) <= names
        assert WRITE_VERB in names

    @pytest.mark.requires_cluster
    @pytest.mark.skipif(
        _credentials() is None or os.environ.get("MAINLINE_STEWARD_SEND") != "1",
        reason=(
            LIVE_REASON + " The write additionally requires MAINLINE_STEWARD_SEND=1, because "
            "insert_rows is a real append to a real evidentiary table and a test run is "
            "not a reason to add a row to one."
        ),
    )
    def test_one_real_occurrence_writes_exactly_one_row(
        self, run_config
    ):  # pragma: no cover - never runs in CI
        from dataclasses import replace

        from mainline_mcp.client import Client
        from mainline_steward import Emitter, StewardRun, load_schedules

        credentials = _credentials()
        assert credentials is not None
        api_key, cluster_id = credentials
        occurrence = (
            load_schedules(run_config.schedules_path)
            .by_id("custodian-patrol")
            .occurrence(os.environ["OCCURRENCE_TS"])
        )
        with Client.connect(api_key=api_key, cluster_id=cluster_id) as client:
            config = replace(run_config, mcp_cluster_id=cluster_id, dry_run=False)
            result = StewardRun(
                config, client=client, emitter=Emitter(client, dry_run=False)
            ).execute(occurrence)
        assert result.emitted is True
        assert result.row["subject_ref"].endswith(occurrence.occurrence_ts)
