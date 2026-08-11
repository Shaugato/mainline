# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The auditor persona: deterministic routing, no free-form SQL, completeness on every answer.

The last of those is the one that earns its place. ``test_every_answer_states_its_completeness``
runs every question in every completeness state and asserts the rendered answer says which
state it is in — including the two awkward ones, "this view carries no flag" and "the flag
the contract promised is not here". In a product where a silently truncated aggregate is a
safety defect, an answer that does not say how complete it is has not answered.
"""

from __future__ import annotations

import pytest
from mainline_mcp.auditor import (
    AUDITOR_QUESTIONS,
    AuditorPersona,
    Completeness,
    UnroutableQuestion,
)
from mainline_mcp.catalogue import ARCHITECTURE_VIEWS, parse_contract
from mainline_mcp.client import Client

from conftest import StubResponse, StubTransport, rows_payload, text_payload, view_router


def _catalogue(names=ARCHITECTURE_VIEWS):
    return parse_contract(
        {
            "views": [
                {
                    "name": name,
                    "truncation_flag": (
                        "ancestry_complete"
                        if name in ("v_weakenings_without_disposition", "v_disposition_coverage")
                        else None
                    ),
                }
                for name in names
            ]
        }
    )


def _persona(handler=None, catalogue=None):
    transport = StubTransport(
        handlers={"select_query": handler or view_router({"v_": StubResponse(rows_payload([]))})}
    )
    return AuditorPersona(Client(transport), catalogue or _catalogue()), transport


class TestRoutingTable:
    def test_every_question_names_a_view_the_architecture_names(self):
        for question in AUDITOR_QUESTIONS:
            assert question.view in ARCHITECTURE_VIEWS, question.id

    def test_no_two_questions_share_a_view(self):
        views = [q.view for q in AUDITOR_QUESTIONS]
        assert len(views) == len(set(views))

    def test_the_four_ops_views_are_not_auditor_questions(self):
        ops = {
            "v_gate_latency_daily",
            "v_txn_restart_daily",
            "v_unused_indexes",
            "v_changefeed_health",
        }
        assert ops.isdisjoint({q.view for q in AUDITOR_QUESTIONS})


class TestRouting:
    @pytest.mark.parametrize(
        ("asked", "expected_view"),
        [
            (
                "which weakenings of blood-written controls have no disposition?",
                "v_weakenings_without_disposition",
            ),
            ("what did you decline to surface, and with what arithmetic?", "v_silence_summary"),
            ("is the ledger healthy?", "v_ledger_health"),
            ("what has the fleet been doing?", "v_agent_actions"),
            ("what is blocking merges right now?", "v_open_gate_summary"),
            ("show me undispositioned weakenings", "v_weakenings_without_disposition"),
            ("how much witness debt is open on the ledger", "v_ledger_health"),
            ("were any recall arms degraded yesterday", "v_recall_conservation"),
            ("where is the blame ancestry truncated", "v_blame_coverage"),
            ("are dispositions keeping up", "v_disposition_coverage"),
            ("what fixity patrol never checked anything", "v_fixity_coverage"),
        ],
    )
    def test_the_canonical_questions_route(self, asked, expected_view):
        persona, _ = _persona()
        assert persona.route(asked).view == expected_view

    def test_routing_is_deterministic_across_repeats(self):
        persona, _ = _persona()
        asked = "what did you decline to surface?"
        assert {persona.route(asked).id for _ in range(20)} == {persona.route(asked).id}

    def test_an_unrelated_question_is_refused_not_guessed(self):
        persona, transport = _persona()
        with pytest.raises(UnroutableQuestion) as excinfo:
            persona.ask("what is the weather in kalgoorlie")
        assert "Available" in str(excinfo.value)
        assert transport.calls == []

    def test_an_empty_question_is_refused(self):
        persona, _ = _persona()
        with pytest.raises(UnroutableQuestion):
            persona.route("   ")


class TestNoFreeFormSql:
    def test_the_statement_sent_is_generated_from_the_contract(self):
        persona, transport = _persona()
        persona.ask("is the ledger healthy?")
        _, arguments = transport.calls[0]
        assert arguments["statement"] == "SELECT * FROM mainline_audit.v_ledger_health LIMIT 25"

    def test_question_text_never_reaches_the_statement(self):
        persona, transport = _persona()
        persona.ask("is the ledger healthy? -- OR 1=1; DROP TABLE mainline.permit")
        statements = [args["statement"] for _, args in transport.calls]
        assert all("DROP" not in s for s in statements)
        assert statements == ["SELECT * FROM mainline_audit.v_ledger_health LIMIT 25"]


class TestCompleteness:
    def test_a_complete_answer_says_so(self):
        rows = [{"site_id": "s1", "n": 3, "ancestry_complete": True}]
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload(rows))})
        )
        answer = persona.ask("which weakenings have no disposition?")
        assert answer.completeness is Completeness.COMPLETE
        assert "COMPLETE" in answer.render()

    def test_an_incomplete_answer_names_the_rows_and_calls_the_counts_lower_bounds(self):
        rows = [
            {"site_id": "s1", "n": 3, "ancestry_complete": True},
            {"site_id": "s2", "n": 9, "ancestry_complete": False},
        ]
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload(rows))})
        )
        answer = persona.ask("which weakenings have no disposition?")
        assert answer.completeness is Completeness.INCOMPLETE
        assert answer.incomplete_rows == 1
        rendered = answer.render()
        assert "INCOMPLETE" in rendered
        assert "lower bounds" in rendered

    def test_a_promised_flag_that_is_absent_is_reported_as_unknown(self):
        rows = [{"site_id": "s1", "n": 3}]
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload(rows))})
        )
        answer = persona.ask("which weakenings have no disposition?")
        assert answer.completeness is Completeness.FLAG_MISSING
        assert "unverified" in answer.render()

    def test_a_view_with_no_contracted_flag_says_it_carries_none(self):
        rows = [{"site_code": "KAL", "tree_size": 900}]
        persona, _ = _persona(view_router({"v_ledger_health": StubResponse(rows_payload(rows))}))
        answer = persona.ask("is the ledger healthy?")
        assert answer.completeness is Completeness.NO_FLAG
        assert "NO COMPLETENESS FLAG" in answer.render()

    def test_an_unparseable_response_is_unknown_not_empty(self):
        persona, _ = _persona(view_router({"v_ledger_health": StubResponse(text_payload("boom"))}))
        answer = persona.ask("is the ledger healthy?")
        assert answer.completeness is Completeness.UNKNOWN
        assert answer.row_count is None
        assert "COMPLETENESS UNKNOWN" in answer.render()

    def test_every_answer_states_its_completeness(self):
        # The load-bearing one: no question, in any state, renders without saying how
        # complete it is.
        states = [
            StubResponse(rows_payload([{"a": 1, "ancestry_complete": True}])),
            StubResponse(rows_payload([{"a": 1, "ancestry_complete": False}])),
            StubResponse(rows_payload([{"a": 1}])),
            StubResponse(rows_payload([])),
            StubResponse(text_payload("unparseable")),
        ]
        markers = ("COMPLETE", "INCOMPLETE", "COMPLETENESS UNKNOWN", "NO COMPLETENESS FLAG")
        for state in states:
            persona, _ = _persona(view_router({"v_": state}))
            for question in persona.questions:
                rendered = persona.answer(question).render()
                assert any(marker in rendered for marker in markers), (question.id, rendered)


class TestPartialContract:
    def test_questions_without_a_contracted_view_are_reported_not_crashed(self):
        catalogue = _catalogue(("v_ledger_health",))
        persona, _ = _persona(catalogue=catalogue)
        assert [q.view for q in persona.questions] == ["v_ledger_health"]
        assert len(persona.unanswerable()) == len(AUDITOR_QUESTIONS) - 1

    def test_the_brief_names_what_it_could_not_answer(self):
        catalogue = _catalogue(("v_ledger_health",))
        persona, _ = _persona(catalogue=catalogue)
        brief = persona.brief()
        assert "NOT ANSWERABLE" in brief
        assert "v_silence_summary" in brief

    def test_a_question_routes_only_among_contracted_views(self):
        catalogue = _catalogue(("v_ledger_health",))
        persona, _ = _persona(catalogue=catalogue)
        with pytest.raises(UnroutableQuestion):
            persona.route("what did you decline to surface?")


class TestBrief:
    def test_the_brief_answers_every_contracted_question_once(self):
        persona, transport = _persona()
        brief = persona.brief()
        assert len(transport.calls) == len(persona.questions)
        for question in persona.questions:
            assert question.canonical in brief
