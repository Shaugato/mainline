# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The POSITIVE audit-surface suite, measured over CockroachDB's own public endpoint.

Every assertion in this file is made against ``https://cockroachlabs.cloud/mcp`` with
**none of our code in the path** — that sentence is the deliverable, and it is why the
suite exists separately from the offline tests in ``packages/mainline-mcp/tests``.

**This module never passes without a credential.** The skip is module-level and its
reason names the missing variable. A suite that went green because it had nothing to talk
to would be green-by-absence, which is the failure mode this repository exists to refuse —
so there is no test here that can succeed on a laptop with no key.

Credentials, in order of precedence:

* ``MAINLINE_MCP_API_KEY`` / ``MAINLINE_MCP_CLUSTER_ID`` — the scoped key for the
  throwaway ``mainline-verify`` cluster (see ``VERIFY.md``).
* ``CC_API_KEY`` / ``CRDB_CLUSTER`` — the local development pair.

The write test additionally requires ``MAINLINE_MCP_ALLOW_WRITE=1``, because
``insert_rows`` is a real append to a real evidentiary table and a test run is not a
reason to add a row to one by accident.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "packages" / "mainline-mcp" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_mcp.auditor import AuditorPersona, Completeness  # noqa: E402
from mainline_mcp.budget import BudgetProber  # noqa: E402
from mainline_mcp.catalogue import (  # noqa: E402
    ContractError,
    contract_path,
    load_contract,
)
from mainline_mcp.client import Client  # noqa: E402
from mainline_mcp.limits import (  # noqa: E402
    BUDGET_RESPONSE_BYTES,
    MAX_RESPONSE_BYTES,
    READ_VERBS,
    WRITE_VERB,
)


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if api_key and cluster:
        return api_key, cluster
    return None


def _skip_reason() -> str:
    if _credentials() is None:
        return (
            "no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID "
            "(or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes, because a "
            "green audit-surface run with nothing to talk to would assert nothing."
        )
    if not contract_path(_REPO_ROOT).is_file():
        return (
            f"no audit-surface contract at {contract_path(_REPO_ROOT)}: it is owned by the "
            "fleet-contracts worker, and the prober cannot invent a budget for a view it has "
            "never been told about."
        )
    return ""


_REASON = _skip_reason()

pytestmark = [
    pytest.mark.requires_cluster,
    pytest.mark.skipif(bool(_REASON), reason=_REASON or "credential and contract present"),
]


@pytest.fixture(scope="module")
def catalogue():
    try:
        return load_contract(contract_path(_REPO_ROOT))
    except ContractError as exc:  # pragma: no cover - reached only with a malformed contract
        pytest.fail(f"the audit-surface contract is present but unusable: {exc}")


@pytest.fixture(scope="module")
def client():
    credentials = _credentials()
    assert credentials is not None
    api_key, cluster_id = credentials
    connected = Client.connect(api_key=api_key, cluster_id=cluster_id)
    yield connected
    connected.close()


@pytest.fixture(scope="module")
def report(client, catalogue):
    measured = BudgetProber(client, catalogue).run()
    print("\n" + measured.render())
    destination = os.environ.get("MAINLINE_MCP_REPORT")
    if destination:
        Path(destination).write_text(
            json.dumps(measured.to_json(), indent=2, sort_keys=True), encoding="utf-8"
        )
    return measured


class TestSurface:
    def test_the_advertised_tools_include_every_verb_we_rely_on(self, client):
        names = set(client.tool_names())
        missing = set(READ_VERBS) - names
        assert not missing, f"the Managed MCP surface no longer advertises {sorted(missing)}"
        assert WRITE_VERB in names

    def test_the_contract_still_covers_every_view_the_architecture_names(self, catalogue):
        missing, extra = catalogue.divergence_from_architecture()
        assert not missing, (
            f"the contract has dropped {list(missing)} from the audit surface. A surface that "
            "can silently lose a view can silently stop answering the question that mattered."
        )
        if extra:
            print(f"contract adds views beyond ARCHITECTURE.md §17: {list(extra)}")


class TestBudget:
    def test_every_contracted_view_is_measured(self, report, catalogue):
        assert [m.view for m in report.measurements] == list(catalogue.names())
        for measurement in report.measurements:
            assert measurement.response_bytes > 0, f"{measurement.view} returned nothing at all"

    def test_no_view_exceeds_the_budget(self, report):
        assert report.ok, "\n" + report.render()

    def test_the_budget_leaves_headroom_below_the_server_cap(self, report):
        worst = report.worst_view
        assert worst is not None
        assert worst.response_bytes <= BUDGET_RESPONSE_BYTES, (
            f"{worst.view} is at {worst.response_bytes} bytes, "
            f"{worst.headroom_bytes} below the {MAX_RESPONSE_BYTES}-byte server cap"
        )

    def test_the_worst_row_is_recorded_for_every_view_that_returned_rows(self, report):
        # AR-6's accepted residual: one pathological row can spike one view, and the
        # cause has to be nameable when it happens.
        for measurement in report.measurements:
            if measurement.row_count:
                assert measurement.worst_row is not None
                assert measurement.worst_row.key

    def test_every_row_count_was_determinable(self, report):
        undetermined = [m.view for m in report.measurements if m.row_count is None]
        assert not undetermined, (
            f"rows could not be recovered from {undetermined}; a view whose row count cannot "
            "be measured has not been verified"
        )

    def test_contracted_completeness_flags_are_present_in_the_returned_rows(self, report):
        for measurement in report.measurements:
            if measurement.truncation_flag is not None and measurement.row_count:
                assert measurement.truncation_flag_present, (
                    f"{measurement.view} promises {measurement.truncation_flag!r} and did not "
                    "return it; a reader cannot tell a complete answer from a truncated one"
                )


class TestAuditorPersona:
    def test_every_contracted_question_answers(self, client, catalogue):
        persona = AuditorPersona(client, catalogue)
        assert persona.questions, "the contract covers none of the auditor's questions"
        for question in persona.questions:
            answer = persona.answer(question)
            assert answer.response_bytes < MAX_RESPONSE_BYTES
            assert answer.completeness is not Completeness.UNKNOWN, (
                f"{question.id} came back unparseable: {answer.statement}"
            )

    def test_every_rendered_answer_states_its_completeness(self, client, catalogue):
        persona = AuditorPersona(client, catalogue)
        markers = ("COMPLETE", "INCOMPLETE", "COMPLETENESS UNKNOWN", "NO COMPLETENESS FLAG")
        for question in persona.questions:
            rendered = persona.answer(question).render()
            assert any(marker in rendered for marker in markers), question.id

    def test_the_brief_is_one_call_per_question(self, client, catalogue):
        persona = AuditorPersona(client, catalogue)
        brief = persona.brief()
        print("\n" + brief)
        for question in persona.questions:
            assert question.canonical in brief


class TestExternalAttestation:
    @pytest.mark.skipif(
        os.environ.get("MAINLINE_MCP_ALLOW_WRITE") != "1",
        reason=(
            "insert_rows is a real append to a real evidentiary table; set "
            "MAINLINE_MCP_ALLOW_WRITE=1 to exercise it, and only against mainline-verify"
        ),
    )
    def test_the_one_permitted_write_succeeds(self, client):
        result = client.insert_external_attestation(
            [
                {
                    "verifier": "mainline-mcp integration suite",
                    "outcome": "reachability_probe",
                    "note": "a third party's claim about our log, never our claim about the world",
                }
            ]
        )
        assert not result.is_error, result.text
