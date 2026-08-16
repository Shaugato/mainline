# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The response-budget prober, driven against measured responses of known size.

The prober's whole value is that it fails on numbers rather than on opinions, so every
test here fixes the number and asserts the verdict. Two of them are the ones that make
this a verification instead of a size check: an unparseable envelope is a **breach**, and
a missing completeness flag is a **breach** — neither is a skip, because a view that
cannot be measured has not been verified.

``TestUnobservedFlag`` is the third, and it was added on 2026-08-16 after the first live
run. ``truncation_flag_present`` used to be computed as ``... if rows else True`` — true
by vacuity over an empty result. Eight of the thirteen contracted views return zero rows
on the live cluster, and the one of those eight that also contracts a completeness flag is
``v_weakenings_without_disposition`` — the flagship question. So the boolean about to be
written into a committed evidence artefact was ``true``, for that question, on no rows.
It is now ``bool | None``, and ``None`` says exactly that nothing was observed.
"""

from __future__ import annotations

from mainline_mcp.budget import BudgetProber, row_bytes, row_key
from mainline_mcp.catalogue import parse_contract
from mainline_mcp.client import DEFAULT_DIALECT, Client
from mainline_mcp.limits import (
    BUDGET_RESPONSE_BYTES,
    BUDGET_ROWS,
    MAX_RESPONSE_BYTES,
    ResponseTooLarge,
)

from conftest import StubResponse, StubTransport, rows_payload, text_payload, view_router

CONTRACT = {
    "views": [
        {
            "name": "v_weakenings_without_disposition",
            "columns": ["site_id", "n", "ancestry_complete"],
            "truncation_flag": "ancestry_complete",
        },
        {"name": "v_ledger_health", "columns": ["site_code", "tree_size"]},
    ]
}


def _prober(handler, contract=CONTRACT, *, database=None):
    transport = StubTransport(handlers={"select_query": handler})
    return BudgetProber(Client(transport), parse_contract(contract), database=database)


def _prober_and_transport(handler, contract=CONTRACT, *, database=None):
    transport = StubTransport(handlers={"select_query": handler})
    prober = BudgetProber(Client(transport), parse_contract(contract), database=database)
    return prober, transport


def _rows(n, *, complete=True):
    return [{"site_id": f"s{i}", "n": i, "ancestry_complete": complete} for i in range(n)]


class TestUnderBudget:
    def test_a_small_view_passes_and_reports_its_numbers(self):
        report = _prober(view_router({"v_": StubResponse(rows_payload(_rows(3)), 900)})).run()
        assert report.ok
        assert len(report.measurements) == 2
        for measurement in report.measurements:
            assert measurement.row_count == 3
            assert measurement.response_bytes == 900
            assert measurement.headroom_bytes == MAX_RESPONSE_BYTES - 900

    def test_every_contracted_view_is_measured(self):
        report = _prober(view_router({"v_": StubResponse(rows_payload(_rows(1)), 300)})).run()
        assert [m.view for m in report.measurements] == [
            "v_weakenings_without_disposition",
            "v_ledger_health",
        ]

    def test_exactly_at_the_budget_is_not_a_breach(self):
        response = StubResponse(rows_payload(_rows(BUDGET_ROWS)), BUDGET_RESPONSE_BYTES)
        report = _prober(view_router({"v_": response})).run()
        assert report.ok


class TestBreaches:
    def test_one_byte_over_the_budget_breaches(self):
        response = StubResponse(rows_payload(_rows(2)), BUDGET_RESPONSE_BYTES + 1)
        report = _prober(view_router({"v_": response})).run()
        assert not report.ok
        breach = report.breached[0].breaches[0]
        assert breach.limit == "byte_budget"
        assert breach.observed == BUDGET_RESPONSE_BYTES + 1
        assert breach.budget == BUDGET_RESPONSE_BYTES

    def test_the_breach_fires_below_the_server_cap_leaving_headroom(self):
        response = StubResponse(rows_payload(_rows(2)), BUDGET_RESPONSE_BYTES + 1)
        report = _prober(view_router({"v_": response})).run()
        # AR-6: the alarm has to fire with 20% of the cap still unused.
        assert report.breached[0].headroom_bytes > 0
        assert report.breached[0].response_bytes < MAX_RESPONSE_BYTES

    def test_more_rows_than_the_cap_breaches(self):
        response = StubResponse(rows_payload(_rows(BUDGET_ROWS + 1)), 1000)
        report = _prober(view_router({"v_": response})).run()
        limits = {b.limit for m in report.breached for b in m.breaches}
        assert "row_budget" in limits

    def test_a_response_at_the_server_cap_is_a_truncation_breach(self):
        response = StubResponse(rows_payload(_rows(2)), MAX_RESPONSE_BYTES)
        report = _prober(view_router({"v_": response})).run()
        limits = {b.limit for m in report.breached for b in m.breaches}
        assert "response_cap" in limits

    def test_an_unparseable_envelope_is_a_breach_and_never_a_zero(self):
        response = StubResponse(text_payload("ERROR: relation does not exist"), 200)
        report = _prober(view_router({"v_": response})).run()
        assert not report.ok
        measurement = report.measurements[0]
        assert measurement.row_count is None
        assert "row_count_undetermined" in {b.limit for b in measurement.breaches}

    def test_a_missing_completeness_flag_is_a_breach(self):
        rows_without_flag = [{"site_id": "s1", "n": 1}]
        response = StubResponse(rows_payload(rows_without_flag), 300)
        report = _prober(view_router({"v_": response})).run()
        flagged = report.measurements[0]
        assert flagged.view == "v_weakenings_without_disposition"
        assert "truncation_flag_missing" in {b.limit for b in flagged.breaches}
        # The view with no contracted flag is untouched by that rule.
        assert report.measurements[1].ok

    def test_an_error_result_is_a_breach(self):
        response = StubResponse(text_payload("permission denied", is_error=True), 120)
        report = _prober(view_router({"v_": response})).run()
        assert "tool_error" in {b.limit for m in report.breached for b in m.breaches}

    def test_a_client_side_refusal_is_recorded_rather_than_raised(self):
        # A view whose contracted row cap is above the server maximum would be refused
        # by `enforce_statement`. The prober must record that, not die of it.
        contract = {"views": [{"name": "v_x", "row_cap": 20000}]}
        report = _prober(view_router({"v_": StubResponse(rows_payload([]), 100)}), contract).run()
        assert not report.ok
        assert "tool_error" in {b.limit for b in report.measurements[0].breaches}

    def test_a_transport_that_raises_the_cap_is_recorded_with_its_byte_count(self):
        # A transport that refuses an oversized response rather than returning it must
        # still yield a MEASUREMENT — the number is the whole point of the prober.
        def raising(_arguments):
            raise ResponseTooLarge(
                limit_value=MAX_RESPONSE_BYTES,
                observed=MAX_RESPONSE_BYTES,
                detail="simulated cap hit",
            )

        transport = StubTransport(handlers={"select_query": raising})
        report = BudgetProber(Client(transport), parse_contract(CONTRACT)).run()
        assert not report.ok
        measurement = report.measurements[0]
        assert measurement.response_bytes == MAX_RESPONSE_BYTES
        assert "response_cap" in {b.limit for b in measurement.breaches}


class TestWorstRow:
    def test_the_worst_row_is_recorded_even_when_the_view_passes(self):
        rows = [{"site_id": "s1", "n": 1}, {"site_id": "s2-with-a-much-longer-code", "n": 2}]
        report = _prober(view_router({"v_": StubResponse(rows_payload(rows), 500)})).run()
        worst = report.measurements[0].worst_row
        assert worst is not None
        assert worst.index == 1
        assert "s2-with-a-much-longer-code" in worst.key

    def test_row_bytes_is_stable_and_order_independent(self):
        assert row_bytes({"a": 1, "b": 2}) == row_bytes({"b": 2, "a": 1})

    def test_row_key_names_something_even_for_an_empty_row(self):
        assert row_key({}) == "(empty row)"


class TestIncompleteRows:
    def test_rows_reporting_incomplete_ancestry_are_counted(self):
        rows = _rows(3, complete=False)
        report = _prober(view_router({"v_": StubResponse(rows_payload(rows), 400)})).run()
        flagged = report.measurements[0]
        assert flagged.truncation_flag_present is True
        assert flagged.incomplete_rows == 3
        # An incomplete ancestry is a fact to surface, not a budget breach.
        assert flagged.ok


class TestUnobservedFlag:
    """Zero rows means the flag was not observed. Not confirmed, and not breached."""

    def test_an_empty_flagged_view_does_not_claim_the_flag_was_present(self):
        report = _prober(view_router({"v_": StubResponse(rows_payload([]), 109)})).run()
        flagged = report.measurements[0]
        assert flagged.view == "v_weakenings_without_disposition"
        assert flagged.row_count == 0
        # The pre-live code said True here, vacuously, and would have written it out.
        assert flagged.truncation_flag_present is None

    def test_an_empty_flagged_view_is_not_scored_as_a_breach(self):
        # An empty view genuinely has nothing to truncate. Turning this red would make
        # the prober cry wolf; turning it green-with-a-True would make it lie.
        report = _prober(view_router({"v_": StubResponse(rows_payload([]), 109)})).run()
        assert report.ok
        assert "truncation_flag_missing" not in {
            b.limit for m in report.measurements for b in m.breaches
        }

    def test_the_note_says_in_words_what_was_and_was_not_observed(self):
        report = _prober(view_router({"v_": StubResponse(rows_payload([]), 109)})).run()
        note = report.measurements[0].truncation_flag_note
        assert "no rows were returned" in note
        assert "not observed" in note
        assert "neither a confirmation nor a breach" in note

    def test_the_note_distinguishes_all_four_cases(self):
        present = _prober(view_router({"v_": StubResponse(rows_payload(_rows(2)), 300)})).run()
        assert "present on all 2 returned rows" in present.measurements[0].truncation_flag_note
        assert "declares no completeness flag" in present.measurements[1].truncation_flag_note

        absent_rows = [{"site_id": "s1", "n": 1}]
        absent = _prober(view_router({"v_": StubResponse(rows_payload(absent_rows), 300)})).run()
        assert "do not carry it" in absent.measurements[0].truncation_flag_note

        empty = _prober(view_router({"v_": StubResponse(rows_payload([]), 109)})).run()
        assert "was not observed" in empty.measurements[0].truncation_flag_note

    def test_the_unobserved_state_reaches_the_serialised_artefact(self):
        document = _prober(view_router({"v_": StubResponse(rows_payload([]), 109)})).run().to_json()
        flagged = document["views"][0]
        assert flagged["truncation_flag_present"] is None
        assert "not observed" in flagged["truncation_flag_note"]

    def test_a_tool_error_leaves_the_flag_unobserved_rather_than_absent(self):
        # The pre-live code wrote False on the error paths, which asserts the column
        # was missing. Nothing was observed at all: the call did not return rows.
        contract = {"views": [{"name": "v_x", "row_cap": 20000, "truncation_flag": "f"}]}
        report = _prober(view_router({"v_": StubResponse(rows_payload([]), 100)}), contract).run()
        assert report.measurements[0].truncation_flag_present is None
        assert "tool_error" in {b.limit for b in report.measurements[0].breaches}


class TestDatabaseArgument:
    """``database`` is a REQUIRED property of ``select_query``. Measured 2026-08-16."""

    def test_no_database_is_sent_when_none_is_configured(self):
        prober, transport = _prober_and_transport(
            view_router({"v_": StubResponse(rows_payload(_rows(1)), 300)})
        )
        prober.run()
        assert transport.calls
        assert all(DEFAULT_DIALECT.database not in a for _, a in transport.calls)

    def test_the_configured_database_reaches_every_measurement(self):
        prober, transport = _prober_and_transport(
            view_router({"v_": StubResponse(rows_payload(_rows(1)), 300)}),
            database="mainline_demo",
        )
        prober.run()
        assert len(transport.calls) == 2
        assert all(a[DEFAULT_DIALECT.database] == "mainline_demo" for _, a in transport.calls)

    def test_the_database_is_recorded_in_the_report_and_the_artefact(self):
        report = _prober(
            view_router({"v_": StubResponse(rows_payload(_rows(1)), 300)}),
            database="mainline_demo",
        ).run()
        assert report.database == "mainline_demo"
        assert report.to_json()["database"] == "mainline_demo"


class TestReport:
    def test_render_names_every_view_and_every_breach(self):
        response = StubResponse(rows_payload(_rows(2)), BUDGET_RESPONSE_BYTES + 1)
        report = _prober(view_router({"v_": response})).run()
        rendered = report.render()
        assert "v_ledger_health" in rendered
        assert "BREACH" in rendered
        assert "byte_budget" in rendered
        assert "headroom" in rendered

    def test_to_json_carries_the_numbers_a_nightly_diff_needs(self):
        report = _prober(view_router({"v_": StubResponse(rows_payload(_rows(2)), 700)})).run()
        document = report.to_json()
        assert document["ok"] is True
        assert document["byte_budget"] == BUDGET_RESPONSE_BYTES
        assert document["server_cap_bytes"] == MAX_RESPONSE_BYTES
        assert {v["view"] for v in document["views"]} == {
            "v_weakenings_without_disposition",
            "v_ledger_health",
        }
        assert all(v["response_bytes"] == 700 for v in document["views"])

    def test_the_worst_view_is_the_one_headroom_runs_out_on_first(self):
        handler = view_router(
            {
                "v_weakenings_without_disposition": StubResponse(rows_payload(_rows(1)), 400),
                "v_ledger_health": StubResponse(rows_payload(_rows(1)), 4000),
            }
        )
        report = _prober(handler).run()
        assert report.worst_view is not None
        assert report.worst_view.view == "v_ledger_health"
