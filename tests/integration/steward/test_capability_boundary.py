# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The allowlist is the capability boundary, and here is what it is allowed to contain.

The Steward holds a tool loop. What makes that safe is not the prompt — a prompt is
advice — but that the process is *starved*: eight MCP verbs, two read scopes, and in
``claude -p`` there is nobody present to approve anything else.

This module asserts the four artefacts that express the boundary agree with each other:
``settings.json``, ``.mcp.json``, ``entrypoint.sh`` and the runbook. Four files that each
half-express one rule is how a control quietly stops being a control.

**The trap this suite exists for**, in the words of the brief: never let a Steward finding
write anything the gate reads, and never let it hold a SQL role that can. So the checks
below are about *absence* at least as much as presence — no gate table, no `mainline_qa`,
no `UPDATE`, no second MCP server, no write verb beyond the one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

READ_VERBS = (
    "list_databases",
    "list_tables",
    "get_table_schema",
    "select_query",
    "explain_query",
    "show_statement",
    "show_running_queries",
)
WRITE_VERB = "insert_rows"
FORBIDDEN_WRITE_VERBS = ("create_database", "create_table")


@pytest.fixture(scope="module")
def app_dir(request) -> Path:
    return request.config.rootpath / "verticals" / "mainline" / "apps" / "steward"


@pytest.fixture(scope="module")
def settings(app_dir) -> dict:
    return json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mcp_config(app_dir) -> dict:
    return json.loads((app_dir / ".mcp.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entrypoint(app_dir) -> str:
    return (app_dir / "entrypoint.sh").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def runbook(app_dir) -> str:
    return (app_dir / "runbooks" / "steward-operations.md").read_text(encoding="utf-8")


class TestTheAllowlist:
    def test_it_is_an_allowlist_and_it_is_not_empty(self, settings):
        allow = settings["permissions"]["allow"]
        assert allow, (
            "capability starvation is expressed as configuration here; an empty allowlist "
            "is either a broken Steward or a capability escape depending on how the empty "
            "case is read, and neither is acceptable"
        )

    @pytest.mark.parametrize("verb", [*READ_VERBS, WRITE_VERB])
    def test_every_permitted_verb_appears_in_both_naming_forms(self, settings, verb):
        allow = set(settings["permissions"]["allow"])
        assert f"MCP(crdb.{verb})" in allow
        assert f"mcp__crdb__{verb}" in allow

    def test_the_only_mcp_entries_are_the_seven_reads_plus_the_one_write(self, settings):
        allowed_mcp = {
            entry
            for entry in settings["permissions"]["allow"]
            if entry.startswith(("MCP(", "mcp__"))
        }
        expected = {f"MCP(crdb.{verb})" for verb in (*READ_VERBS, WRITE_VERB)} | {
            f"mcp__crdb__{verb}" for verb in (*READ_VERBS, WRITE_VERB)
        }
        assert allowed_mcp == expected, (
            "the allowlist is written to match the SQL grant exactly — mcp:read plus "
            "INSERT on mainline_meas.external_attestation and nothing else (S13)"
        )

    @pytest.mark.parametrize("verb", FORBIDDEN_WRITE_VERBS)
    def test_the_other_write_verbs_are_denied_explicitly_not_merely_omitted(self, settings, verb):
        deny = set(settings["permissions"]["deny"])
        assert f"MCP(crdb.{verb})" in deny
        assert f"mcp__crdb__{verb}" in deny

    @pytest.mark.parametrize("tool", ["Bash", "Write", "Edit", "WebFetch", "WebSearch", "Task"])
    def test_the_dangerous_built_ins_are_denied(self, settings, tool):
        assert tool in settings["permissions"]["deny"]

    def test_the_session_cannot_read_its_own_idempotency_state(self, settings):
        deny = set(settings["permissions"]["deny"])
        assert "Read(/opt/steward/state/**)" in deny, (
            "the state directory decides whether this run is a duplicate; a session that "
            "could read it could reason about being one"
        )

    def test_no_allow_entry_reaches_a_gate_table_or_the_qa_schema(self, settings):
        blob = json.dumps(settings["permissions"]["allow"]).lower()
        for forbidden in ("mainline_qa", "permit", "blocking_check", "disposition", "merge_record"):
            assert forbidden not in blob, (
                f"the allowlist names {forbidden!r}. A Steward finding must never be able "
                "to write anything the gate reads, and it must not hold a role that can"
            )

    def test_hooks_and_shell_execution_inside_skills_are_disabled(self, settings):
        assert settings["disableAllHooks"] is True
        assert settings["disableSkillShellExecution"] is True, (
            "the consumed skills are third-party text; a skill that can run a shell is a "
            "third party running a shell in a container holding a database credential"
        )


class TestTheMcpConfig:
    def test_there_is_exactly_one_server_and_it_is_the_managed_endpoint(self, mcp_config):
        servers = mcp_config["mcpServers"]
        assert list(servers) == ["crdb"]
        assert servers["crdb"]["type"] == "http"
        assert servers["crdb"]["url"] == "https://cockroachlabs.cloud/mcp"

    def test_the_cluster_pin_header_is_present(self, mcp_config):
        headers = mcp_config["mcpServers"]["crdb"]["headers"]
        assert headers["mcp-cluster-id"] == "${MAINLINE_MCP_CLUSTER_ID}"
        assert headers["Authorization"] == "Bearer ${CC_MCP_API_KEY}"

    def test_neither_variable_carries_a_default(self, mcp_config):
        blob = json.dumps(mcp_config["mcpServers"]["crdb"])
        assert ":-" not in blob, (
            "a default would turn a missing secret into a silent connection to whatever "
            "the default named; a Steward that cannot prove which cluster it is pinned to "
            "must not read one"
        )

    def test_no_credential_is_baked_into_the_file(self, mcp_config):
        blob = json.dumps(mcp_config)
        assert "Bearer ${" in blob
        assert "CCDB" not in blob
        assert not any(len(token) > 40 and token.isalnum() for token in blob.split('"'))


class TestTheEntrypointAgrees:
    def test_it_pins_the_mcp_config_strictly(self, entrypoint):
        assert "--strict-mcp-config" in entrypoint, (
            "without it a user-scope server, a plugin server or a claude.ai connector "
            "could add a second tool surface to a capability-starved process"
        )

    def test_it_passes_the_allowlist_on_the_command_line_as_well(self, entrypoint):
        assert "--allowedTools" in entrypoint
        assert "mainline-steward allowlist" in entrypoint, (
            "the flag is fed from settings.json rather than restated, so the two cannot "
            "drift; a settings file that failed to load must not degrade into a "
            "permissive session"
        )

    def test_it_refuses_a_non_australian_inference_profile(self, entrypoint):
        assert "au.*" in entrypoint or "*au.*" in entrypoint
        assert "MAINLINE_STEWARD_INFERENCE_PROFILE_ARN" in entrypoint

    def test_it_requires_every_attested_variable_before_reading_anything(self, entrypoint):
        for name in (
            "SCHEDULE_ID",
            "OCCURRENCE_TS",
            "MAINLINE_SITE_CODE",
            "MAINLINE_MCP_CLUSTER_ID",
            "CC_MCP_API_KEY",
            "MAINLINE_SCHEMA_VERSION",
            "MAINLINE_STEWARD_TASK_ROLE_ARN",
        ):
            assert f'"${{{name}:?' in entrypoint, f"{name} is not required before the reads"

    def test_the_write_is_opt_in(self, entrypoint):
        assert "MAINLINE_STEWARD_SEND" in entrypoint
        assert "--send" in entrypoint

    def test_there_is_no_inline_python_or_shell_json_parsing(self, entrypoint):
        message = "every rule belongs in a verb that can be tested off the container"
        assert "<<'PY'" not in entrypoint, message
        assert "<<PY" not in entrypoint, message

    def test_the_session_is_allowed_to_fail_and_the_attestation_is_not(self, entrypoint):
        assert "the run continues with no narrative" in entrypoint
        assert entrypoint.rstrip().endswith('"${SCHEDULE_ID}" "${OCCURRENCE_TS}"')


class TestTheRunbookAndTheFileAgree:
    def test_the_runbook_documents_the_allowlist_section(self, runbook):
        assert "The allowlist is the capability boundary" in runbook

    def test_the_runbook_explains_why_insert_rows_is_on_a_read_only_list(self, runbook):
        assert "insert_rows" in runbook
        assert "external_attestation" in runbook

    def test_the_runbook_states_the_crdb_internal_substitution(self, runbook):
        assert "crdb_internal" in runbook
        for view in (
            "v_gate_latency_daily",
            "v_txn_restart_daily",
            "v_unused_indexes",
            "v_changefeed_health",
        ):
            assert view in runbook

    def test_the_runbook_states_that_exactly_once_is_not_claimed(self, runbook):
        assert "Exactly-once is not claimed" in runbook

    def test_the_sidecar_points_at_the_runbook_section(self, app_dir):
        sidecar = (app_dir / "settings.json.license").read_text(encoding="utf-8")
        assert "SPDX-License-Identifier" in sidecar
        assert "The allowlist is the capability" in sidecar
