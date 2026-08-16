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

``MAINLINE_MCP_DATABASE`` names the database, defaulting to ``mainline_demo``.

── WHAT THE FIRST LIVE RUN CHANGED, 2026-08-16 ──────────────────────────────────────

This module was written in August 2026 and, until today, had **never executed**: no key
was present at build time, and the client it dials through sent the SQL statement under a
property the live server does not read (``statement``, not ``query``), so even with a key
it could not have passed. Three things the live surface proved wrong, each fixed here:

1. **``CRDB_CLUSTER`` is a cluster NAME, not a cluster id.** ``.env`` sets it to
   ``mainline-dev``; the header wants a UUID and the server answers
   ``HTTP 400: invalid cluster_id: must be a valid UUID, got "mainline-dev"``. Taking the
   name as an id turned every test in this directory into an HTTP 400 in fixture setup —
   a red that says nothing about what the suite asserts. It is now a skip that names the
   defect.

2. **``select_query`` needs a ``database``, and the fallback is not ours.** ``database``
   is required in the advertised schema; omitting it does not error — the call runs
   against a default database where ``mainline_audit`` does not exist. So a client with
   no database configured gets *plausible* answers to the wrong question. The client now
   carries one.

3. **The audit-surface contract is still absent**
   (``spec/mcp/audit-surface.contract.yaml``, owned by the fleet-contracts worker). That
   used to skip the whole module, which meant the *tool list* and the *audit views* — two
   things that need no contract at all — went unasserted along with the budget. The
   contract skip has moved down onto the fixture that needs it, so what can be measured
   without it now is.

The write test additionally required ``MAINLINE_MCP_ALLOW_WRITE=1``. It no longer runs at
all; see :class:`TestExternalAttestation` for the ruling and the measurement behind it.
"""

from __future__ import annotations

import json
import os
import re
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

#: Measured 2026-08-16: a cluster NAME in the ``mcp-cluster-id`` header is an HTTP 400.
_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)

#: The database every audit view lives in. Overridable, because a second deployment of
#: this vertical would name it something else; defaulted, because a missing database is
#: not a missing credential and must not read as one.
DATABASE = os.environ.get("MAINLINE_MCP_DATABASE") or "mainline_demo"

#: One aggregate view, asked as the positive control. It is the question the film asks —
#: *what is the gate refusing right now* — and it is the precondition every other
#: assertion in this directory rests on: if this view cannot be read, then a "refusal"
#: measured next door is a missing relation wearing a refusal's clothes.
CONTROL_VIEW = "mainline_audit.v_open_gate_summary"
CONTROL_STATEMENT = "SELECT * FROM mainline_audit.v_open_gate_summary LIMIT 25"


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if api_key and cluster and _UUID.match(cluster):
        return api_key, cluster
    return None


def _skip_reason() -> str:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if not api_key or not cluster:
        return (
            "no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID "
            "(or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes, because a "
            "green audit-surface run with nothing to talk to would assert nothing."
        )
    if not _UUID.match(cluster):
        return (
            f"the cluster id is {cluster!r}, which is a cluster NAME and not a UUID. Measured "
            "2026-08-16, the Managed MCP Server answers a name in the mcp-cluster-id header "
            'with `HTTP 400: invalid cluster_id: must be a valid UUID, got "mainline-dev"`. '
            "Set MAINLINE_MCP_CLUSTER_ID to the cluster UUID; evidence/ccloud/cluster-list.txt "
            "records it for this project's cluster."
        )
    return ""


_REASON = _skip_reason()

_NO_CONTRACT = (
    f"no audit-surface contract at {contract_path(_REPO_ROOT)}: it is owned by the "
    "fleet-contracts worker, and the prober cannot invent a budget for a view it has "
    "never been told about. The tool list and the audit views above do not need it and "
    "are measured live regardless."
)

pytestmark = [
    pytest.mark.requires_cluster,
    pytest.mark.skipif(bool(_REASON), reason=_REASON or "credential present"),
]


@pytest.fixture(scope="module")
def catalogue():
    # SKIPS HERE RATHER THAN AT MODULE LEVEL. Until 2026-08-16 a missing contract skipped
    # the whole file, so the absence of one worker's artefact silently withdrew the
    # assertions that had nothing to do with it. A skip should be as narrow as the thing
    # that is missing.
    if not contract_path(_REPO_ROOT).is_file():
        pytest.skip(_NO_CONTRACT)
    try:
        return load_contract(contract_path(_REPO_ROOT))
    except ContractError as exc:  # pragma: no cover - reached only with a malformed contract
        pytest.fail(f"the audit-surface contract is present but unusable: {exc}")


@pytest.fixture(scope="module")
def client():
    credentials = _credentials()
    assert credentials is not None
    api_key, cluster_id = credentials
    # `database` is not decoration. Measured 2026-08-16: omitting it does not fail, it
    # silently routes the statement at a default database in which `mainline_audit` does
    # not exist — so the connection detail has to be ours, or the answers are to a
    # question nobody asked.
    connected = Client.connect(api_key=api_key, cluster_id=cluster_id, database=DATABASE)
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


class TestTheAuditSurfaceAnswers:
    """The store → retrieve half, with no contract required and none of our code reading.

    These four assertions are what the module is *for*: a question about MAINLINE's memory,
    routed to a contracted ``mainline_audit`` view, answered over CockroachDB's own managed
    endpoint by the ``managed-mcp`` identity, with its completeness stated. They need no
    audit-surface contract, which is why they survive its absence.
    """

    def test_the_identity_on_the_far_end_is_the_scoped_one(self, client):
        result = client.select_query("SELECT current_user AS u")
        assert not result.is_error, result.text
        assert result.rows, f"SELECT current_user returned no rows: {result.text!r}"
        assert result.rows[0]["u"] == "managed-mcp", (
            f"the endpoint answered as {result.rows[0]['u']!r}. The whole audit-surface "
            "argument rests on this being a scoped identity and not an owner or a superuser."
        )

    def test_the_control_view_answers_in_this_database(self, client):
        result = client.select_query(CONTROL_STATEMENT)
        assert not result.is_error, (
            f"{CONTROL_VIEW} did not answer in database {DATABASE!r}: {result.text[:400]!r}. "
            "Set MAINLINE_MCP_DATABASE. Every negative assertion in this directory is "
            "meaningless until this one holds — an unreachable schema and an absent database "
            "produce the same shape of error."
        )
        assert result.row_count is not None, (
            f"{CONTROL_VIEW} answered with an envelope no row parser recognised: "
            f"{result.text[:200]!r}"
        )
        print(f"{CONTROL_VIEW}: {result.row_count} rows, {result.byte_count} bytes")

    def test_the_control_view_states_its_own_completeness(self, client):
        result = client.select_query(CONTROL_STATEMENT)
        assert not result.is_error, result.text
        if not result.rows:
            pytest.skip(
                f"{CONTROL_VIEW} is empty on this cluster, so there is no row to carry a "
                "completeness flag. The flag is a column, not a value, and an empty view "
                "cannot demonstrate one — seed the demo state and re-run."
            )
        assert "rows_complete" in result.rows[0], (
            f"{CONTROL_VIEW} returned {sorted(result.rows[0])} and no completeness flag. A "
            "reader cannot tell a complete answer from a truncated one."
        )

    def test_the_control_view_fits_the_budget_we_publish(self, client):
        result = client.select_query(CONTROL_STATEMENT)
        assert result.byte_count < BUDGET_RESPONSE_BYTES, (
            f"{CONTROL_VIEW} came back at {result.byte_count} bytes against our "
            f"{BUDGET_RESPONSE_BYTES}-byte budget ({MAX_RESPONSE_BYTES} is the server's cap, "
            "at which an answer may be a truncation rather than an answer)."
        )


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
    """The one permitted write, and why this suite no longer attempts it.

    ``insert_external_attestation`` is unchanged and untested against the live server. Two
    independent reasons, and the second is the one that matters:

    * **Ruling R4.** No worker calls ``insert_rows``, ``create_database`` or
      ``create_table`` against the live cluster this week. ``MAINLINE_MCP_ALLOW_WRITE=1``
      used to be the escape hatch for exactly that call; the hatch is closed rather than
      left ajar, because an environment variable is not a decision and this decision is
      the founder's.

    * **The call could not have proved what it claimed anyway.** Measured 2026-08-16, the
      live ``insert_rows`` schema is ``{cluster_id, database, query}``, ``query`` being a
      whole INSERT statement. Our method sends ``{table, rows}``. Against the live server
      that is refused for the *shape* of the arguments, never reaching the grant — so a
      green here would have recorded "the server dislikes our JSON", dressed as "the
      write surface is bound to one table".

    Speaking the live shape means composing SQL that names a table inside the one method
    whose published guarantee is that no parameter names a table. That guarantee is worth
    more than the call. The divergence is recorded in ``packages/mainline-mcp/README.md``
    and pinned by ``test_live_dialect.py::TestTheWriteVerbDivergence``, which reads
    ``insert_rows``'s schema without invoking it.
    """

    @pytest.mark.skip(
        reason=(
            "R4: no live insert_rows this week — and measured 2026-08-16 the live shape is "
            "{database, query} with a whole INSERT statement, not the typed {table, rows} this "
            "client sends, so the call would be refused on argument shape and never reach the "
            "grant it claims to test. The divergence is asserted instead, without calling the "
            "verb, by test_live_dialect.py::TestTheWriteVerbDivergence."
        )
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
