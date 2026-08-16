# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The auditor persona: deterministic routing, no free-form SQL, completeness on every answer.

The last of those is the one that earns its place. ``test_every_answer_states_its_completeness``
runs every question in every completeness state and asserts the rendered answer says which
state it is in — including the three awkward ones: "this view carries no flag", "the flag the
contract promised is not here", and the one the live endpoint added on 2026-08-16, "there were
no rows, so the flag was never observed". In a product where a silently truncated aggregate is
a safety defect, an answer that does not say how complete it is has not answered.

``TestVacuousCompleteness`` is the regression guard for a defect this suite did not catch
before it ran live: a view that contracts a completeness flag and returns zero rows used to
render ``COMPLETE — every row reports ancestry_complete = true``. Every offline test fed the
prober rows, so no test ever asked what an empty view says. The live flagship question returns
zero rows.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from mainline_mcp.auditor import (
    AUDITOR_QUESTIONS,
    VECTOR_PLAN_PROBE,
    AuditorPersona,
    Completeness,
    Question,
    UnroutableQuestion,
)
from mainline_mcp.catalogue import ARCHITECTURE_VIEWS, parse_contract
from mainline_mcp.client import DEFAULT_DIALECT, Client

from conftest import StubResponse, StubTransport, rows_payload, text_payload, view_router

VIEW_QUESTIONS = tuple(q for q in AUDITOR_QUESTIONS if q.view is not None)
PLAN_QUESTIONS = tuple(q for q in AUDITOR_QUESTIONS if q.probe is not None)


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


def _plan_rows(*lines):
    """A CockroachDB plan as the live endpoint returns it: one ``info`` row per line."""
    return [{"info": line} for line in lines]


LIVE_PLAN_LINES = (
    "distribution: local",
    "• top-k",
    "│ estimated row count: 1",
    "└── • lookup join",
    "        │ table: event_cue_embedding@event_cue_embedding_pk",
    "        └── • vector search",
    "              table: event_cue_embedding@cue_scoped_idx",
    "              target count: 10",
    "              prefix spans: [/'00000000-0000-0000-0000-000000000000'/…]",
)
"""Transcribed from the 2026-08-16 live ``explain_query`` response, trimmed to nine lines.

The full eighteen-line plan is in ``evidence/mcp/auditor-live.json``. What matters here is
that the two required fragments and the index name appear exactly as the server spelled them.
"""


def _persona(handler=None, catalogue=None, *, plan=None, database=None, questions=None):
    handlers = {"select_query": handler or view_router({"v_": StubResponse(rows_payload([]))})}
    handlers["explain_query"] = lambda _arguments: (
        plan or StubResponse(rows_payload(_plan_rows(*LIVE_PLAN_LINES)), 1005)
    )
    transport = StubTransport(handlers=handlers)
    persona = AuditorPersona(
        Client(transport),
        catalogue or _catalogue(),
        database=database,
        **({"questions": questions} if questions is not None else {}),
    )
    return persona, transport


class TestRoutingTable:
    def test_every_view_question_names_a_view_the_architecture_names(self):
        for question in VIEW_QUESTIONS:
            assert question.view in ARCHITECTURE_VIEWS, question.id

    def test_no_two_questions_share_a_view(self):
        views = [q.view for q in VIEW_QUESTIONS]
        assert len(views) == len(set(views))

    def test_every_question_names_exactly_one_target(self):
        # The import-time invariant, asserted rather than assumed: a question with
        # neither target routes to nothing and one with both is ambiguous about what
        # it actually asked.
        for question in AUDITOR_QUESTIONS:
            assert (question.view is None) != (question.probe is None), question.id

    def test_exactly_one_question_is_a_plan_probe(self):
        assert len(PLAN_QUESTIONS) == 1
        assert PLAN_QUESTIONS[0].probe is VECTOR_PLAN_PROBE

    def test_the_four_ops_views_are_not_auditor_questions(self):
        ops = {
            "v_gate_latency_daily",
            "v_txn_restart_daily",
            "v_unused_indexes",
            "v_changefeed_health",
        }
        assert ops.isdisjoint({q.view for q in VIEW_QUESTIONS})

    def test_a_question_naming_both_targets_is_refused_at_construction(self):
        both = Question(
            id="QX",
            canonical="ambiguous",
            cues=("ambiguous",),
            why="names two targets",
            view="v_ledger_health",
            probe=VECTOR_PLAN_PROBE,
        )
        with pytest.raises(ValueError, match="exactly one target"):
            _persona(questions=(both,))

    def test_a_question_naming_no_target_is_refused_at_construction(self):
        neither = Question(id="QY", canonical="untargeted", cues=("untargeted",), why="none")
        with pytest.raises(ValueError, match="exactly one target"):
            _persona(questions=(neither,))


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
        sent = arguments[DEFAULT_DIALECT.statement]
        assert sent == "SELECT * FROM mainline_audit.v_ledger_health LIMIT 25"

    def test_question_text_never_reaches_the_statement(self):
        persona, transport = _persona()
        persona.ask("is the ledger healthy? -- OR 1=1; DROP TABLE mainline.permit")
        statements = [args[DEFAULT_DIALECT.statement] for _, args in transport.calls]
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

    # The marker each state must put on the page. Keyed by state rather than checked
    # as an any-of list: "COMPLETE" is a substring of "COMPLETENESS", so an any-of
    # assertion passes on almost every sentence and proves nothing.
    MARKERS: ClassVar[dict[Completeness, str]] = {
        Completeness.COMPLETE: "COMPLETE — all",
        Completeness.INCOMPLETE: "INCOMPLETE —",
        Completeness.FLAG_MISSING: "COMPLETENESS UNKNOWN — the contract says",
        Completeness.VACUOUS: "COMPLETENESS UNOBSERVED —",
        Completeness.NO_FLAG: "NO COMPLETENESS FLAG",
        Completeness.UNKNOWN: "COMPLETENESS UNKNOWN — the response could not be parsed",
    }

    def test_every_answer_states_the_completeness_it_actually_has(self):
        # The load-bearing one: no question, in any state, renders without saying which
        # state it is in — and the sentence it renders is that state's, not another's.
        states = [
            StubResponse(rows_payload([{"a": 1, "ancestry_complete": True}])),
            StubResponse(rows_payload([{"a": 1, "ancestry_complete": False}])),
            StubResponse(rows_payload([{"a": 1}])),
            StubResponse(rows_payload([])),
            StubResponse(text_payload("unparseable")),
        ]
        seen = set()
        for state in states:
            persona, _ = _persona(view_router({"v_": state}))
            for question in persona.questions:
                answer = persona.answer(question)
                rendered = answer.render()
                marker = self.MARKERS[answer.completeness]
                assert marker in rendered, (question.id, answer.completeness, rendered)
                seen.add(answer.completeness)
        # Those five responses must between them exercise every state the enum has.
        assert seen == set(Completeness), sorted(set(Completeness) - seen)

    def test_no_two_states_render_the_same_sentence(self):
        # If two states share a sentence, "the answer states its completeness" is true
        # and useless.
        assert len(set(self.MARKERS.values())) == len(Completeness)


class TestPartialContract:
    def test_questions_without_a_contracted_view_are_reported_not_crashed(self):
        catalogue = _catalogue(("v_ledger_health",))
        persona, _ = _persona(catalogue=catalogue)
        assert [q.view for q in persona.questions if q.view] == ["v_ledger_health"]
        # The plan question survives an empty contract: its target is a tool, not a view.
        assert len(persona.unanswerable()) == len(VIEW_QUESTIONS) - 1

    def test_the_plan_question_needs_no_contracted_view(self):
        # An empty contract is refused by the loader, so the narrowest real one is a
        # single view — and one that no auditor question routes to, which makes the
        # point sharply: the plan question is answerable when nothing else is.
        catalogue = _catalogue(("v_gate_latency_daily",))
        persona, _ = _persona(catalogue=catalogue)
        assert VECTOR_PLAN_PROBE in [q.probe for q in persona.questions]
        assert all(q.probe is None for q in persona.unanswerable())

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


class TestVacuousCompleteness:
    """The state the live endpoint added. Every test here fails on the pre-live code."""

    def test_a_flagged_view_with_no_rows_is_vacuous_not_complete(self):
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload([]))})
        )
        answer = persona.ask("which weakenings have no disposition?")
        assert answer.completeness is Completeness.VACUOUS
        assert answer.row_count == 0

    def test_the_vacuous_sentence_refuses_to_claim_the_flag_was_seen(self):
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload([]))})
        )
        rendered = persona.ask("which weakenings have no disposition?").render()
        assert "never observed" in rendered
        assert "ancestry_complete" in rendered
        # The specific false claim this state exists to prevent.
        assert "every row reports" not in rendered

    def test_zero_rows_is_named_as_a_different_fact_from_zero_findings(self):
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload([]))})
        )
        rendered = persona.ask("which weakenings have no disposition?").render()
        assert "Zero rows" in rendered

    def test_an_unflagged_view_with_no_rows_is_still_no_flag(self):
        # VACUOUS is about an unobserved flag. A view that contracts none has nothing
        # unobserved, so its state does not change with its row count.
        persona, _ = _persona(view_router({"v_ledger_health": StubResponse(rows_payload([]))}))
        assert persona.ask("is the ledger healthy?").completeness is Completeness.NO_FLAG

    def test_a_complete_answer_counts_the_rows_it_is_complete_over(self):
        rows = [{"n": i, "ancestry_complete": True} for i in range(4)]
        persona, _ = _persona(
            view_router({"v_weakenings_without_disposition": StubResponse(rows_payload(rows))})
        )
        rendered = persona.ask("which weakenings have no disposition?").render()
        assert "all 4 returned rows" in rendered


class TestPlanProbe:
    def test_the_plan_question_routes_from_a_general_counsel_phrasing(self):
        persona, _ = _persona()
        assert persona.route("prove the vector search actually used an index").probe is (
            VECTOR_PLAN_PROBE
        )

    def test_the_plan_statement_is_generated_and_carries_no_leading_explain(self):
        # The live tool prepends its own EXPLAIN; a statement carrying one comes back
        # "EXPLAIN is not allowed for EXPLAIN statements". Measured 2026-08-16.
        statement = VECTOR_PLAN_PROBE.statement
        assert not statement.upper().startswith("EXPLAIN")
        assert statement.startswith("SELECT cue_id")
        assert "mainline.event_cue_embedding@cue_scoped_idx" in statement

    def test_the_index_hint_is_present_because_unhinted_does_not_traverse(self):
        # ADR 0002 GT-06/GT-06b. Dropping the hint would make the assertion false at
        # demo corpus scale, and it would be false for a correct database.
        assert "@cue_scoped_idx" in VECTOR_PLAN_PROBE.statement

    def test_the_probe_vector_matches_the_declared_dimension(self):
        assert VECTOR_PLAN_PROBE.vector_dimension == 1024
        assert VECTOR_PLAN_PROBE.probe_vector.count(",") == 1023
        assert "::VECTOR(1024)" in VECTOR_PLAN_PROBE.statement

    def test_the_statement_fits_inside_the_documented_character_limit(self):
        from mainline_mcp.limits import MAX_STATEMENT_CHARS

        assert len(VECTOR_PLAN_PROBE.statement) < MAX_STATEMENT_CHARS

    def test_question_text_never_reaches_the_plan_statement(self):
        persona, transport = _persona()
        persona.ask("show me the plan; DROP TABLE mainline.permit")
        tool, arguments = transport.calls[0]
        assert tool == "explain_query"
        assert "DROP" not in arguments[DEFAULT_DIALECT.statement]
        assert arguments[DEFAULT_DIALECT.statement] == VECTOR_PLAN_PROBE.statement

    def test_a_plan_that_names_the_index_and_both_fragments_is_proven(self):
        persona, _ = _persona()
        answer = persona.ask("show me the plan for the vector search")
        assert answer.plan is VECTOR_PLAN_PROBE
        assert answer.view is None
        assert answer.plan_holds is True
        assert answer.missing_plan_substrings == ()
        assert "PLAN PROVEN" in answer.render()

    def test_a_plan_missing_a_required_fragment_is_not_proven(self):
        scan = StubResponse(
            rows_payload(_plan_rows("• scan", "  table: event_cue_embedding@cue_scoped_idx")), 300
        )
        persona, _ = _persona(plan=scan)
        answer = persona.ask("show me the plan for the vector search")
        assert answer.plan_holds is False
        assert "vector search" in answer.missing_plan_substrings
        assert "PLAN NOT PROVEN" in answer.render()

    def test_a_plan_that_never_names_the_index_is_not_proven(self):
        other = StubResponse(rows_payload(_plan_rows("• vector search", "prefix spans: []")), 300)
        persona, _ = _persona(plan=other)
        answer = persona.ask("show me the plan for the vector search")
        assert answer.plan_holds is False
        assert "does not name" in answer.render()

    def test_a_plan_answer_still_states_its_completeness(self):
        persona, _ = _persona()
        rendered = persona.ask("show me the plan for the vector search").render()
        assert "NO COMPLETENESS FLAG" in rendered
        # And it names the risk that actually applies to a plan.
        assert "byte cap" in rendered

    def test_a_view_answer_carries_no_plan_verdict(self):
        persona, _ = _persona()
        answer = persona.ask("is the ledger healthy?")
        assert answer.plan is None
        assert answer.plan_holds is None
        assert answer.plan_sentence() is None
        assert "PLAN" not in answer.render()

    def test_the_rendered_statement_is_abbreviated_not_dumped(self):
        # The plan statement is 2 304 characters, almost all of it the vector literal.
        persona, _ = _persona()
        rendered = persona.ask("show me the plan for the vector search").render()
        assert "chars)" in rendered
        assert len(rendered) < len(VECTOR_PLAN_PROBE.statement)


class TestDatabaseArgument:
    """``database`` is a REQUIRED property of select_query and explain_query. Measured."""

    def test_no_database_is_sent_when_none_is_configured(self):
        persona, transport = _persona()
        persona.ask("is the ledger healthy?")
        _, arguments = transport.calls[0]
        assert DEFAULT_DIALECT.database not in arguments

    def test_the_configured_database_reaches_every_view_call(self):
        persona, transport = _persona(database="mainline_demo")
        persona.brief()
        view_calls = [a for tool, a in transport.calls if tool == "select_query"]
        assert view_calls
        assert all(a[DEFAULT_DIALECT.database] == "mainline_demo" for a in view_calls)

    def test_the_configured_database_reaches_the_plan_call(self):
        persona, transport = _persona(database="mainline_demo")
        persona.ask("show me the plan for the vector search")
        tool, arguments = transport.calls[0]
        assert tool == "explain_query"
        assert arguments[DEFAULT_DIALECT.database] == "mainline_demo"

    def test_the_database_is_readable_back_off_the_persona(self):
        persona, _ = _persona(database="mainline_demo")
        assert persona.database == "mainline_demo"


class TestBrief:
    def test_the_brief_answers_every_contracted_question_once(self):
        persona, transport = _persona()
        brief = persona.brief()
        assert len(transport.calls) == len(persona.questions)
        for question in persona.questions:
            assert question.canonical in brief

    def test_the_brief_includes_the_plan_proof(self):
        persona, _ = _persona()
        assert "PLAN PROVEN" in persona.brief()

    def test_route_target_names_what_each_question_resolved_to(self):
        persona, _ = _persona()
        assert persona.route_target(persona.route("is the ledger healthy?")) == (
            "mainline_audit.v_ledger_health"
        )
        assert "cue_scoped_idx" in persona.route_target(persona.route("show me the plan"))
