# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The pragma scanner — the input side of the Authority Source Contract.

The contract can only refuse what the scanner finds, so a scanner that silently misses a
pragma is a contract that silently passes an unbacked column. That failure mode is
invisible: the render succeeds, the SQL is correct-looking, and the only thing missing
is authority.

Two design decisions are asserted here rather than described:

**Pragmas are Jinja comments.** They vanish from the rendered SQL, so they can never be
mistaken for executable text, and they cannot be introduced by a loop variable — the
scan is over the TEMPLATE SOURCE, and the contract is therefore decidable before a
single line of SQL exists.

**``@projects`` preserves order and duplicates.** A template naming one column twice is
a template whose author lost track, and the caller is entitled to see it. ``@capability``
sorts and de-duplicates instead, because its consumer asks a set question ("is every one
of these answered?") for which order carries nothing.
"""

from __future__ import annotations

import pytest

from trappoint_sql.pragma import capabilities_of, projected_columns_of, rendered_projection_header


def test_a_single_projected_column_is_found() -> None:
    assert projected_columns_of("{# @projects blocking_check.severity #}") == (
        "blocking_check.severity",
    )


def test_columns_may_be_comma_or_space_separated() -> None:
    body = (
        "{# @projects blocking_check.severity, blocking_check.virulence "
        "blocking_check.closure_gen #}"
    )
    assert projected_columns_of(body) == (
        "blocking_check.severity",
        "blocking_check.virulence",
        "blocking_check.closure_gen",
    )


def test_whitespace_control_markers_do_not_hide_a_pragma() -> None:
    # `{#- ... -#}` is how a template author stops a comment leaving a blank line. A
    # scanner that only matched `{# ... #}` would miss every pragma written that way, and
    # the miss would look exactly like a template that projects nothing.
    assert projected_columns_of("{#- @projects blocking_check.severity -#}") == (
        "blocking_check.severity",
    )


def test_pragmas_are_found_across_several_comments() -> None:
    source = (
        "{# @projects blocking_check.severity #}\n"
        "-- @file a.sql\n"
        "{# @projects disposition.signer_rank #}\n"
    )
    assert projected_columns_of(source) == ("blocking_check.severity", "disposition.signer_rank")


def test_order_and_duplicates_are_preserved() -> None:
    source = "{# @projects b.y, b.x #}\n{# @projects b.x #}\n"
    assert projected_columns_of(source) == ("b.y", "b.x", "b.x")


def test_a_template_with_no_pragma_yields_nothing() -> None:
    assert projected_columns_of("-- @file a.sql\nSELECT 1;\n") == ()


def test_the_word_projects_in_prose_is_not_a_pragma() -> None:
    # The templates EXPLAIN what a projection is, at length, in their own comments. A
    # scanner that could not tell an explanation from a declaration would make the
    # mechanism undocumentable — the same trap the D10 token guard has to avoid.
    source = "{# This template projects nothing; see authority-source.md for the pragma. #}"
    assert projected_columns_of(source) == ()


def test_a_sql_comment_is_not_a_pragma() -> None:
    # `-- @projects ...` is what the RENDERED file carries (authority-source.md §4). It
    # is output, not input, and treating it as input would let a rendered file re-declare
    # itself on the next pass.
    assert projected_columns_of("-- @projects blocking_check.severity\n") == ()


def test_capabilities_are_sorted_and_deduplicated() -> None:
    source = "{# @capability triggerdef #}\n{# @capability stored_digest triggerdef #}\n"
    assert capabilities_of(source) == ("stored_digest", "triggerdef")


def test_capabilities_of_a_plain_template_is_empty() -> None:
    assert capabilities_of("-- @file a.sql\nSELECT 1;\n") == ()


@pytest.mark.parametrize(
    "source",
    [
        "{# @projects blocking_check.severity #}",
        "{#@projects blocking_check.severity#}",
        "{#   @projects   blocking_check.severity   #}",
        "{#-\n  @projects blocking_check.severity\n-#}",
    ],
)
def test_spacing_never_changes_the_answer(source: str) -> None:
    assert projected_columns_of(source) == ("blocking_check.severity",)


def test_the_rendered_projection_header_states_the_whole_contract() -> None:
    # Three lines that authority-source.md §4 makes contractual: they are what lets
    # `--check` and the migration linter verify that the committed SQL still corresponds
    # to the declaration that produced it. The key rename is the reason the two sides are
    # printed separately — in MAINLINE the projected row carries `commit_id` while the
    # closure carries `as_of_commit`, and a header that collapsed them would document a
    # column that does not exist.
    header = rendered_projection_header(
        ("blocking_check.severity", "blocking_check.virulence"),
        "mainline.clause_blame_current",
        ("clause_uuid", "as_of_commit"),
        ("clause_uuid", "commit_id"),
    )
    assert header.splitlines() == [
        "-- @projects blocking_check.severity, blocking_check.virulence",
        (
            "-- @authority mainline.clause_blame_current (clause_uuid, as_of_commit) "
            "<= NEW (clause_uuid, commit_id)"
        ),
        "-- @on_missing raise",
    ]


def test_the_rendered_header_is_not_itself_a_pragma() -> None:
    # The round trip that must NOT close: a rendered projection header carries the same
    # words as the template pragma that produced it, and if the scanner read it back a
    # rendered file could satisfy the contract by quoting itself.
    header = rendered_projection_header(("b.x",), "s.r", ("k",), ("k",))
    assert projected_columns_of(header) == ()
