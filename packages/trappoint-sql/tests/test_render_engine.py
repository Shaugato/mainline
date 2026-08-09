# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""The render engine's own guarantees: determinism, and the guards over rendered text.

``trappoint render --check`` is a zero-diff assertion in CI, and the Authority Source
Contract is only binding while the committed SQL is what the declaration produced. Both
sentences are worth nothing if the same inputs can produce two different byte streams,
so determinism is tested as a property here rather than assumed from the Jinja settings.

The guards are the other half. Each one refuses a rendered file that would be legal SQL
and wrong for this repository:

``one statement per file``
    CockroachDB DDL is not transactional across statements, so a two-statement file that
    fails halfway leaves an undiagnosable ``dirty`` marker.
``an MI/I citation in the header``
    ARCHITECTURE.md §18. A migration that cannot say which invariant it realises is a
    migration nobody can review against anything.
``the banned tokens (ruling D10)``
    ``CREATE SEQUENCE`` / ``nextval(`` / ``SERIAL`` / ``unique_rowid()``. The ledger is
    gap-free by compare-and-swap, so a gap MEANS tampering — and one reintroduced
    sequence makes that sentence false everywhere, silently.
``R-1, the recaller covenant``
    The role that DETECTS a precursor may never be granted a write on one. Finding `S1`
    at compile time: a ``GRANT`` that quietly reunited those two roles leaves every
    constraint in place and every test green while the flagship claim becomes false.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from trappoint_sql.binding import load_binding
from trappoint_sql.errors import RenderRefused, TemplateRefused
from trappoint_sql.render import (
    RENDERED_BANNER,
    check_units,
    render_binding,
    split_units,
    write_units,
)

HEADER = (
    "{{{{ header(file='{file}', title='{title}', "
    "rationale='A fixture.', mi=['MI01'], i=['I01']) }}}}"
)
TABLE = "CREATE TABLE probe.a (x INT8 NOT NULL PRIMARY KEY);"


def unit(file: str, body: str, *, title: str = "a fixture") -> str:
    """A template emitting one file with a well-formed header."""
    return f"-- @file {file}\n" + HEADER.format(file=file, title=title) + f"\n\n{body}\n"


def one(stem: str, body: str = TABLE) -> list[tuple[str, str]]:
    """The one-template, one-file case, which most of this module wants."""
    return [(f"{stem}.sql.j2", unit(f"{stem}.sql", body))]


def render(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
    files: list[tuple[str, str]],
) -> object:
    """Load the minimal binding and render *files* against it."""
    return render_binding(load_binding(write_binding()), write_templates(files))


# ── determinism ─────────────────────────────────────────────────────────────────────


def test_two_renders_of_one_tree_are_byte_identical(
    repo_root_path: Path,
    templates_dir: Path,
) -> None:
    # The real templates and the real MAINLINE binding, rendered twice in one process.
    # Dictionary iteration, `set` ordering and template load order are all candidates for
    # a non-deterministic byte stream, and every one of them would surface here.
    binding = load_binding(repo_root_path / "verticals/mainline/vertical.toml")
    first = render_binding(binding, templates_dir)
    second = render_binding(binding, templates_dir)
    assert [u.name for u in first.units] == [u.name for u in second.units]
    assert [u.data for u in first.units] == [u.data for u in second.units]


def test_units_are_returned_in_filename_order(
    repo_root_path: Path,
    templates_dir: Path,
) -> None:
    # Filename order is migration order. A render whose units came back in template order
    # would make the report unreadable and any downstream consumer wrong.
    binding = load_binding(repo_root_path / "packages/trappoint-sql/refvertical/vertical.toml")
    names = [u.name for u in render_binding(binding, templates_dir).units]
    assert names == sorted(names)


def test_rendered_bytes_use_lf_and_end_with_exactly_one_newline(
    repo_root_path: Path,
    templates_dir: Path,
) -> None:
    # On Windows the default text mode would translate `\n` to `\r\n` and `--check` would
    # fail on every file for a reason that has nothing to do with the SQL.
    binding = load_binding(repo_root_path / "verticals/mainline/vertical.toml")
    for rendered in render_binding(binding, templates_dir).units:
        assert b"\r" not in rendered.data, f"{rendered.name} carries a CR"
        assert rendered.data.endswith(b"\n")
        assert not rendered.data.endswith(b"\n\n")


def test_write_units_leaves_unchanged_files_alone(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    result = render(write_binding, write_templates, one("9200_a"))
    assert write_units(result) == ["9200_a.sql"]  # type: ignore[arg-type]
    assert write_units(result) == [], "a second write must touch nothing"  # type: ignore[arg-type]
    assert check_units(result) == []  # type: ignore[arg-type]


# ── the file sentinel ───────────────────────────────────────────────────────────────


def test_text_before_the_first_sentinel_is_refused() -> None:
    with pytest.raises(TemplateRefused) as excinfo:
        split_units("SELECT 1;\n-- @file a.sql\nSELECT 2;\n", "t.j2")
    assert "t.j2:1" in str(excinfo.value), "the refusal must carry a line number"


def test_a_template_that_emits_nothing_is_refused() -> None:
    # A template that renders nothing is a template that silently stopped working, and
    # silence is the failure mode this whole repository exists to convert into a refusal.
    # The stream is blank rather than commented: a comment line before the first sentinel
    # is caught one rule earlier, and a fixture that trips two rules proves neither.
    with pytest.raises(TemplateRefused) as excinfo:
        split_units("\n   \n", "t.j2")
    assert "silently stopped working" in str(excinfo.value)


def test_a_comment_before_the_first_sentinel_is_refused_as_stray_text() -> None:
    with pytest.raises(TemplateRefused) as excinfo:
        split_units("-- nothing here\n-- @file a.sql\nSELECT 1;\n", "t.j2")
    assert "belongs to a named output file" in str(excinfo.value)


def test_one_template_naming_a_file_twice_is_refused() -> None:
    with pytest.raises(TemplateRefused) as excinfo:
        split_units("-- @file a.sql\nSELECT 1;\n-- @file a.sql\nSELECT 2;\n", "t.j2")
    assert "twice" in str(excinfo.value)


def test_two_templates_emitting_one_filename_is_refused(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # Output filenames ARE the migration version, and two files claiming one version is a
    # tree `trappoint migrate` refuses to discover.
    with pytest.raises(RenderRefused) as excinfo:
        render(
            write_binding,
            write_templates,
            [
                ("9200_a.sql.j2", unit("9200_a.sql", TABLE)),
                ("9201_b.sql.j2", unit("9200_a.sql", TABLE)),
            ],
        )
    assert "9200_a.sql" in str(excinfo.value)
    assert "9200_a.sql.j2" in str(excinfo.value)
    assert "9201_b.sql.j2" in str(excinfo.value)


# ── StrictUndefined ─────────────────────────────────────────────────────────────────


def test_an_undefined_name_is_a_refusal_not_an_empty_string(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The reason StrictUndefined is not a style preference: with the default undefined,
    # `GRANT SELECT ON t TO {{ role.recaler }}` renders `TO ;` — or worse, renders and
    # applies against a role name that silently became empty.
    template = unit("9202_typo.sql", "GRANT SELECT ON probe.t TO {{ role.recaler }};")
    with pytest.raises(TemplateRefused) as excinfo:
        render(write_binding, write_templates, [("9202_typo.sql.j2", template)])
    assert "9202_typo.sql.j2" in str(excinfo.value)


# ── one statement per file ──────────────────────────────────────────────────────────


def test_two_statements_in_one_file_are_refused(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    body = f"{TABLE}\nCREATE TABLE probe.b (x INT8 NOT NULL PRIMARY KEY);"
    with pytest.raises(RenderRefused) as excinfo:
        render(write_binding, write_templates, one("9203_two", body))
    message = str(excinfo.value)
    assert "2 statements in one file" in message
    assert "not transactional across statements" in message
    assert "lowercase letter suffix" in message, "the message must name the fix (ruling D7)"


def test_a_semicolon_inside_a_string_literal_is_not_a_statement(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The 0009x covenant comment is one statement containing eleven semicolons inside one
    # string literal. A naive split on ";" would refuse the real schema.
    body = "COMMENT ON SCHEMA probe IS 'one; two; three; four';"
    result = render(write_binding, write_templates, one("9204_comment", body))
    assert result.by_name["9204_comment.sql"].text.count(";") > 1  # type: ignore[attr-defined]


def test_a_semicolon_inside_a_line_comment_is_not_a_statement(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    render(write_binding, write_templates, one("9205_c", f"-- see also: a; b; c\n{TABLE}"))


# ── the §18 citation rule ───────────────────────────────────────────────────────────


def test_a_header_with_no_citation_is_refused_by_the_header_builder(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    template = (
        "-- @file 9206_uncited.sql\n"
        "{{ header(file='9206_uncited.sql', title='no citation', rationale='none') }}\n\n"
        f"{TABLE}\n"
    )
    with pytest.raises(TemplateRefused) as excinfo:
        render(write_binding, write_templates, [("9206_uncited.sql.j2", template)])
    assert "which invariant it realises" in str(excinfo.value)


def test_a_hand_written_header_with_no_citation_is_refused_by_the_unit_guard(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # Belt and braces on purpose: `header()` is the only sanctioned way to write a
    # header, and a template that bypasses it must still be refused, or the rule holds
    # only while everyone remembers to call the helper.
    template = (
        "-- @file 9207_raw.sql\n"
        "-- SPDX-License-Identifier: Apache-2.0\n"
        "-- a header with no invariant at all\n\n"
        f"{TABLE}\n"
    )
    with pytest.raises(RenderRefused) as excinfo:
        render(write_binding, write_templates, [("9207_raw.sql.j2", template)])
    assert "cites no MInn or Inn identifier" in str(excinfo.value)


# ── ruling D10: the sequence ban ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("sql", "token"),
    [
        ("CREATE SEQUENCE probe.s;", "CREATE SEQUENCE"),
        ("CREATE TABLE probe.a (x INT8 DEFAULT nextval('probe.s') PRIMARY KEY);", "nextval("),
        ("CREATE TABLE probe.a (x SERIAL8 PRIMARY KEY);", "SERIAL"),
        ("CREATE TABLE probe.a (x INT8 DEFAULT unique_rowid() PRIMARY KEY);", "unique_rowid()"),
    ],
)
def test_a_banned_token_refuses_the_render(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
    sql: str,
    token: str,
) -> None:
    with pytest.raises(RenderRefused) as excinfo:
        render(write_binding, write_templates, one("9208_banned", sql))
    message = str(excinfo.value)
    assert "ruling D10" in message
    assert "a gap MEANS tampering" in message
    assert token.split("(", 1)[0].split(maxsplit=1)[0].lower() in message.lower()


def test_the_word_sequence_in_a_comment_is_not_a_banned_token(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The guard strips comments before searching, and it has to: the real migrations
    # EXPLAIN the ban in prose, and a guard that could not tell an explanation from an
    # instance would make the ban undocumentable.
    body = f"-- There is no CREATE SEQUENCE anywhere here, and no nextval(.\n{TABLE}"
    render(write_binding, write_templates, one("9209_prose", body))


# ── R-1: the recaller covenant ──────────────────────────────────────────────────────


def test_r1_refuses_a_grant_of_insert_to_the_recaller_on_an_obligation_relation(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    body = "GRANT INSERT ON TABLE probe.blocking_check TO {{ role.recaller }};"
    with pytest.raises(RenderRefused) as excinfo:
        render(write_binding, write_templates, one("9210_grant", body))
    message = str(excinfo.value)
    assert "R-1" in message
    assert "agent_recaller" in message
    assert "blocking_check" in message
    assert "finding S1" in message


def test_r1_refuses_grant_all_just_as_readily(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # `GRANT ALL` is the spelling that would slip past a check looking for the word
    # INSERT, and it is strictly worse than the thing that check was written to stop.
    body = "GRANT ALL ON TABLE probe.blocking_check TO {{ role.recaller }};"
    with pytest.raises(RenderRefused) as excinfo:
        render(write_binding, write_templates, one("9211_grant", body))
    assert "R-1" in str(excinfo.value)


def test_r1_permits_the_recaller_a_read(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The covenant is about WRITES. A recaller that could not read the obligation table
    # could not do its job, and a rule that forbade that would be a different rule.
    body = "GRANT SELECT ON TABLE probe.blocking_check TO {{ role.recaller }};"
    result = render(write_binding, write_templates, one("9212_grant", body))
    assert "GRANT SELECT" in result.by_name["9212_grant.sql"].text  # type: ignore[attr-defined]


def test_r1_permits_the_gate_role_an_insert(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # Only the gate role materialises an obligation. If this were refused too, the rule
    # would be "nobody may write an obligation", which is a schema nobody can use.
    body = "GRANT INSERT ON TABLE probe.blocking_check TO {{ role.gate }};"
    result = render(write_binding, write_templates, one("9213_grant", body))
    assert "agent_gate" in result.by_name["9213_grant.sql"].text  # type: ignore[attr-defined]


# ── the rendered-by banner ──────────────────────────────────────────────────────────


def test_every_rendered_unit_carries_the_banner(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The banner is how `--check` finds a STALE file: one that carries it and that no
    # template produces any more. Without it, deleting a template leaves its output
    # applied forever.
    result = render(write_binding, write_templates, one("9214_a"))
    assert RENDERED_BANNER in result.by_name["9214_a.sql"].text  # type: ignore[attr-defined]


def test_check_reports_a_stale_rendered_file(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    result = render(write_binding, write_templates, one("9215_a"))
    write_units(result)  # type: ignore[arg-type]
    orphan = result.binding.output_dir / "9299_gone.sql"  # type: ignore[attr-defined]
    orphan.write_bytes(f"{RENDERED_BANNER}\n-- MI01\nSELECT 1;\n".encode())
    findings = check_units(result)  # type: ignore[arg-type]
    assert [(f.name, f.kind) for f in findings] == [("9299_gone.sql", "stale")]


def test_check_reports_a_hand_edited_file_as_a_diff(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    result = render(write_binding, write_templates, one("9216_a"))
    write_units(result)  # type: ignore[arg-type]
    target = result.binding.output_dir / "9216_a.sql"  # type: ignore[attr-defined]
    target.write_bytes(target.read_bytes().replace(b"probe.a", b"probe.z"))
    (finding,) = check_units(result)  # type: ignore[arg-type]
    assert finding.kind == "diff"
    assert "trappoint render --binding" in finding.detail, "the finding must name the fix"


def test_check_reports_a_never_written_file_as_missing(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    result = render(write_binding, write_templates, one("9217_a"))
    (finding,) = check_units(result)  # type: ignore[arg-type]
    assert finding.kind == "missing"
