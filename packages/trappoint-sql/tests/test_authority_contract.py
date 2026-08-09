# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE AUTHORITY SOURCE CONTRACT — rules `A-1` … `A-9`, each as an exit code.

This is the suite for the sixty lines the render worker exists to write. `P-2` says a
projection trigger derives its value from a declared authority source and never from the
inserted row; `S1` is the adversarial finding that a *supplied* column is invisible to
every other check in the repository, because nothing is missing except authority.

What makes that testable is that the contract's whole output is a **refusal**, so every
test here asserts:

1. the render is refused — not warned, not logged;
2. the message NAMES the offending column or relation, because the operator reading it
   has just been told their vertical may not generate a schema and has to know which
   clause to fix;
3. and, for `A-1`, that the identical render **succeeds** once the declaration is added.
   A refusal test with no passing counterpart cannot distinguish a working contract from
   a renderer that refuses everything.

Three of the nine rules are unreachable through a committed TOML file because
``spec/binding/vertical.schema.json`` rejects them earlier — ``on_missing`` is a
``const``, and ``relation`` carries a qualified-name ``pattern``. Those are exercised
against ``check_authority_contract`` directly and the double coverage is stated at the
test, because "the schema catches it" is a claim that stops being true the moment
someone loosens the schema.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from trappoint_sql.binding import check_authority_contract, load_binding
from trappoint_sql.errors import AuthoritySourceRefused
from trappoint_sql.model import AuthoritySource
from trappoint_sql.render import render_binding

SPEC_VERSION = "1.0.0-rc.1"

# A template that projects one gate column. The pragma is the entire point of the file;
# the CREATE TABLE exists only because the renderer refuses an empty unit.
PROJECTING = """\
{# @projects blocking_check.severity #}
-- @file 9001_probe.sql
{{ header(file='9001_probe.sql', title='a projection',
          rationale='Exists to carry a @projects pragma.', mi=['MI02'], i=['I02']) }}

CREATE TABLE {{ binding.schema }}.probe (x INT8 NOT NULL PRIMARY KEY);
"""

INERT = """\
-- @file 9002_inert.sql
{{ header(file='9002_inert.sql', title='no projection at all',
          rationale='Renders without declaring any projected column.', mi=['MI01'], i=['I01']) }}

CREATE TABLE {{ binding.schema }}.inert (x INT8 NOT NULL PRIMARY KEY);
"""

# Move the binding's one declaration onto a relation NO template renders. The projected
# column is then unbacked (A-1) and the declaration is pending rather than stale (A-5),
# so exactly one rule can refuse. See the isolation note on the A-1 test.
_UNBACKED: tuple[tuple[str, str], ...] = (
    ('projects    = ["blocking_check.severity"]', 'projects    = ["disposition.signer_rank"]'),
    ('relation    = "probe.clause_blame_current"', 'relation    = "probe.person"'),
    ('key         = ["clause_uuid"]', 'key         = ["signer_sub"]'),
    ('key_columns = ["clause_uuid"]', 'key_columns = ["signer_sub"]'),
    ('columns     = ["max_severity"]', 'columns     = ["rank"]'),
)


def source(**overrides: object) -> AuthoritySource:
    """A well-formed authority source, with named fields overridden."""
    fields: dict[str, object] = {
        "projects": ("blocking_check.severity",),
        "relation": "probe.clause_blame_current",
        "key": ("clause_uuid",),
        "key_columns": ("clause_uuid",),
        "columns": ("max_severity",),
        "on_missing": "raise",
        "raise_via": "p0001",
        "strictest": {},
    }
    fields.update(overrides)
    return AuthoritySource(**fields)  # type: ignore[arg-type]


class Fake:
    """The three attributes ``check_authority_contract`` reads off a binding."""

    def __init__(self, entries: tuple[AuthoritySource, ...], *, spec_version: str = SPEC_VERSION):
        self.authority_sources = entries
        self.vertical = type("V", (), {"spec_version": spec_version, "schema": "probe"})()
        self.source = Path("probe/vertical.toml")
        self.subject_tables = frozenset({"permit"})
        self.obligation_relations = frozenset({"probe.blocking_check"})


def check(entries: tuple[AuthoritySource, ...], projections: dict[str, tuple[str, ...]]) -> object:
    """Run the contract over a fake binding."""
    return check_authority_contract(
        Fake(entries),  # type: ignore[arg-type]
        projections,
        tree_spec_version=SPEC_VERSION,
    )


# ── A-1: the rule the worker exists for ─────────────────────────────────────────────


def test_a1_refuses_an_unbacked_projected_column_and_names_it(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The binding declares an authority for a DIFFERENT relation entirely, so A-5 has
    # nothing to say and A-1 is the only rule that can fire. That isolation is not
    # fussiness: a mutation run that cut A-1 while leaving the fixture declaring another
    # column of `blocking_check` still saw a refusal — from A-5 — and a suite that
    # accepted it would have reported a working contract over a cut one.
    binding = load_binding(write_binding(*_UNBACKED))
    templates = write_templates([("9001_probe.sql.j2", PROJECTING)])
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        render_binding(binding, templates)
    message = str(excinfo.value)
    assert message.startswith("unbacked projected column: blocking_check.severity")
    assert "9001_probe.sql.j2" in message, "the operator must know WHICH template declared it"
    # The message must say what to ADD, not only what is wrong.
    assert 'on_missing = "raise"' in message


def test_a1_the_same_render_succeeds_once_the_declaration_is_added(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # The passing counterpart. Without it, a renderer that refused unconditionally would
    # satisfy every other test in this file.
    binding = load_binding(write_binding())
    templates = write_templates([("9001_probe.sql.j2", PROJECTING)])
    result = render_binding(binding, templates)
    assert result.authority.backed == ("blocking_check.severity",)
    assert result.authority.pending == ()
    assert [unit.name for unit in result.units] == ["9001_probe.sql"]


def test_a1_fires_before_a_single_file_is_written(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # An unbacked projection must not produce SQL that is then thrown away: a partially
    # written output directory is a tree `trappoint migrate` would happily apply.
    binding = load_binding(write_binding(*_UNBACKED))
    templates = write_templates([("9001_probe.sql.j2", PROJECTING), ("9002_inert.sql.j2", INERT)])
    with pytest.raises(AuthoritySourceRefused):
        render_binding(binding, templates)
    written = list(binding.output_dir.iterdir())
    assert written == [], "nothing may be written before the contract passes"


def test_a1_is_scoped_to_projected_columns_not_to_every_column(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
) -> None:
    # A template that projects nothing needs no declaration. The contract governs gate
    # columns a trigger writes, not every identifier in the schema.
    binding = load_binding(write_binding())
    templates = write_templates([("9002_inert.sql.j2", INERT)])
    result = render_binding(binding, templates)
    assert result.authority.backed == ()
    assert result.authority.pending == ("blocking_check.severity",)


# ── A-2: on_missing has exactly one legal value ─────────────────────────────────────


def test_a2_refuses_any_on_missing_other_than_raise() -> None:
    # Unreachable through a committed TOML file (`on_missing` is a JSON Schema `const`),
    # and enforced here anyway: "the schema catches it" stops being true the moment
    # someone loosens the schema, and this is the rule that makes absence of evidence
    # refuse rather than default.
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check((source(on_missing="default"),), {"t.j2": ("blocking_check.severity",)})
    assert "A-2" in str(excinfo.value)
    assert "raise" in str(excinfo.value)


# ── A-3 / A-9: positional lists must line up ────────────────────────────────────────


def test_a3_refuses_a_projects_columns_length_mismatch(write_binding: Callable[..., Path]) -> None:
    # An off-by-one here writes a severity into a generation counter and the gate keeps
    # working, wrongly. That is why the length check is a refusal and not a warning.
    path = write_binding(
        (
            'projects    = ["blocking_check.severity"]',
            'projects    = ["blocking_check.severity", "blocking_check.virulence"]',
        ),
    )
    binding = load_binding(path)
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)
    assert "A-3" in str(excinfo.value)
    assert "probe.clause_blame_current" in str(excinfo.value)


def test_a9_refuses_a_key_key_columns_length_mismatch(write_binding: Callable[..., Path]) -> None:
    path = write_binding(
        ('key         = ["clause_uuid"]', 'key         = ["clause_uuid", "commit_id"]'),
    )
    binding = load_binding(path)
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)
    assert "A-9" in str(excinfo.value)


def test_key_columns_defaults_to_key_when_the_two_sides_share_names(
    write_binding: Callable[..., Path],
) -> None:
    # MAINLINE renames (`commit_id` on the projected row, `as_of_commit` on the closure),
    # so the two lists cannot be collapsed — but a binding that does not rename must not
    # be forced to repeat itself, and the default must not then trip A-9.
    path = write_binding(('key_columns = ["clause_uuid"]\n', ""))
    binding = load_binding(path)
    entry = binding.authority_sources[0]
    assert entry.key_columns == entry.key == ("clause_uuid",)
    check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)


# ── A-4: one column, one authority ──────────────────────────────────────────────────


def test_a4_refuses_a_column_projected_from_two_authorities() -> None:
    entries = (
        source(),
        source(relation="probe.other_closure"),
    )
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check(entries, {"t.j2": ("blocking_check.severity",)})
    message = str(excinfo.value)
    assert "A-4" in message
    assert "probe.clause_blame_current" in message
    assert "probe.other_closure" in message


# ── A-5: a declaration for a relation this tree already renders is stale ────────────


def test_a5_refuses_a_stale_declaration_for_an_already_rendered_relation() -> None:
    # `blocking_check.severity` is projected by a template, so `blocking_check` is in
    # scope. A declaration for `blocking_check.closure_gen` that no template projects is
    # then stale rather than early, and the message says so.
    entries = (source(), source(projects=("blocking_check.closure_gen",), columns=("closure_gen",)))
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check(entries, {"t.j2": ("blocking_check.severity",)})
    message = str(excinfo.value)
    assert "A-5" in message
    assert "blocking_check.closure_gen" in message


def test_a5_calls_a_declaration_for_an_unrendered_relation_pending_not_stale() -> None:
    # The scoping decision `binding.py` documents, asserted rather than described: the
    # gate templates land several workers after the binding, and a renderer that refused
    # a correct declaration for a table that does not exist yet would force every binding
    # to be written backwards.
    report = check((source(), source(projects=("disposition.signer_rank",), columns=("rank",))), {})
    assert report.backed == ()
    assert set(report.pending) == {"blocking_check.severity", "disposition.signer_rank"}


def test_a5_scope_comes_from_the_templates_and_cannot_be_configured_away() -> None:
    # The property that matters: scope is derived from the template set. The binding
    # below is byte-identical in both calls; only the templates differ, and only the
    # template set decides whether the second declaration is stale.
    entries = (source(), source(projects=("blocking_check.closure_gen",), columns=("closure_gen",)))
    check(entries, {})  # no template projects onto blocking_check: pending
    with pytest.raises(AuthoritySourceRefused):
        check(entries, {"t.j2": ("blocking_check.severity",)})


# ── A-6: the authority may not be a relation the gated writer can write ─────────────


def test_a6_refuses_an_unqualified_relation() -> None:
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check((source(relation="clause_blame_current"),), {})
    assert "A-6" in str(excinfo.value)


def test_a6_refuses_a_subject_table_as_its_own_authority(
    write_binding: Callable[..., Path],
) -> None:
    # THE FAILURE THIS RULE EXISTS FOR. Declaring the gated table as its own authority
    # keeps every constraint in place and makes the projection derived from the inserter
    # with one extra step — P-2 violated while the declaration looks correct.
    path = write_binding(
        ('relation    = "probe.clause_blame_current"', 'relation    = "probe.permit"'),
    )
    binding = load_binding(path)
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)
    assert "A-6" in str(excinfo.value)
    assert "derived from the inserter" in str(excinfo.value)


def test_a6_refuses_a_declared_obligation_relation_as_an_authority(
    write_binding: Callable[..., Path],
) -> None:
    path = write_binding(
        ('relation    = "probe.clause_blame_current"', 'relation    = "probe.blocking_check"'),
    )
    binding = load_binding(path)
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)
    assert "A-6" in str(excinfo.value)


# ── A-7: strictest_projection must be total ─────────────────────────────────────────


def test_a7_refuses_strictest_projection_missing_a_column(
    write_binding: Callable[..., Path],
) -> None:
    # Ruling D3: a missing clearance row projects the STRICTEST requirements so the REAL
    # composite FK fires with its constraint name. A `strictest` map that omits a column
    # would leave that column NULL and emit 23502 — outside the taxonomy, with no
    # constraint name, which is the whole thing D3 was written to prevent.
    path = write_binding(
        (
            'raise_via   = "p0001"',
            'raise_via   = "strictest_projection"\nstrictest   = { max_severity = 5 }',
        ),
        (
            'projects    = ["blocking_check.severity"]',
            'projects    = ["blocking_check.severity", "blocking_check.virulence"]',
        ),
        ('columns     = ["max_severity"]', 'columns     = ["max_severity", "virulence"]'),
    )
    binding = load_binding(path)
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)
    assert "A-7" in str(excinfo.value)
    assert "virulence" in str(excinfo.value)


def test_a7_accepts_a_total_strictest_map(write_binding: Callable[..., Path]) -> None:
    path = write_binding(
        (
            'raise_via   = "p0001"',
            'raise_via   = "strictest_projection"\nstrictest   = { severity = 5 }',
        ),
    )
    binding = load_binding(path)
    check_authority_contract(binding, {}, tree_spec_version=SPEC_VERSION)


# ── A-8: a MAJOR mismatch means a different set of invariants ───────────────────────


def test_a8_refuses_a_major_spec_version_mismatch() -> None:
    with pytest.raises(AuthoritySourceRefused) as excinfo:
        check_authority_contract(
            Fake((source(),), spec_version="2.0.0"),  # type: ignore[arg-type]
            {},
            tree_spec_version=SPEC_VERSION,
        )
    assert "A-8" in str(excinfo.value)
    assert "2.0.0" in str(excinfo.value)


def test_a8_permits_a_minor_or_patch_difference() -> None:
    # Adding an invariant is a MAJOR bump. A MINOR difference is a binding written
    # against fewer optional features, not against different invariants, so refusing it
    # would make every vertical unmergeable on the day the spec gets a new section.
    check_authority_contract(
        Fake((source(),), spec_version="1.4.2"),  # type: ignore[arg-type]
        {},
        tree_spec_version=SPEC_VERSION,
    )


# ── the report ──────────────────────────────────────────────────────────────────────


def test_the_report_separates_backed_from_pending() -> None:
    # `pending` is the honest half. Printing it is what stops "the contract passed" being
    # read as "every projection in the design is backed".
    report = check(
        (source(), source(projects=("disposition.signer_rank",), columns=("rank",))),
        {"t.j2": ("blocking_check.severity",)},
    )
    assert report.backed == ("blocking_check.severity",)
    assert report.pending == ("disposition.signer_rank",)
    assert "1 projected column(s) backed" in report.summary
    assert "1 declared-and-pending" in report.summary
