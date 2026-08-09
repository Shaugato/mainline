# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The catalogue ratchet, and the first deliberately-red case (PL-2).

Tier 0 in `docs/leads/datamodel.md` §5: **no cluster**. Everything here is a statement
about files — `verticals/mainline/db/invariants/mi_catalogue.yaml`, the migration tree's
`-- MI:` headers, `MI-CATALOGUE.md` — and about the two laws in `scripts/mi_ratchet.py`.
That is deliberate. The ratchet's whole job is to be trustworthy *while the schema is
still being built*, so it may not itself depend on the schema being built.

What is being asserted, in one paragraph
----------------------------------------
That the catalogue is a complete and well-formed statement about thirty invariants; that
`owning_migrations` is a **projection** of the `-- MI:` headers rather than a declaration,
and that the projection refuses when its source is absent instead of quietly reporting
that nothing enforces anything (P2); that reconciliation rewrites the projected field and
corrupts nothing else; and that both laws — `mi-red` and `mi-green` — actually bite,
tested against synthetic outcome maps rather than against a run whose colour we would have
to trust.

What is deliberately NOT asserted here
--------------------------------------
Whether the committed `owning_migrations` and `MI-CATALOGUE.md` are *current right now*.
That is a statement about the repository at a moment, not about the ratchet, and it is
enforced by a CI step:

    python scripts/mi_ratchet.py check      # exit 1 on drift, naming the fixing command

The reason is structural, not convenience. Eighty workers are landing migrations into this
tree concurrently; a currency assertion living in this file would turn every unrelated
migration into a second red case here, and PL-2's signal depends on this suite having
**exactly one** cause of redness. So the mechanism is tested here (drift *is* caught,
against a catalogue this suite mutates) and the moment is checked there. It is the same
split `schema.yml` already uses for `REFUSAL_DEPTH.md` and `ANOMALY_COVERAGE.md`: the
"committed and current" assertion is a workflow step.

The one red case
----------------
:func:`test_red_every_invariant_is_enforced` **fails right now, and is supposed to.**
PL-2: a suite for a product whose deliverable is a refusal, that has never been red,
asserts nothing. This is the assertion that the data-model domain is finished — *"the
domain is done when every MI in mi_catalogue.yaml reads `enforced`, and not one of them
was ever green before its mechanism existed"* (`docs/leads/datamodel.md` §7). It fails
with a count, it goes green exactly once, and on that day it becomes the regression test
that keeps the catalogue from being demoted back.

`scripts/mi_ratchet.py check` asserts this file holds **exactly one** `test_red_*` case,
so "the suite is red" always has a single nameable cause. Adding a second red case is a
failing build, not a matter of taste.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "mi_ratchet.py"


def _load_ratchet() -> ModuleType:
    """Import `scripts/mi_ratchet.py` by path — `scripts/` is not a package, on purpose.

    The ratchet is a script a stranger runs with bare `python`, with no workspace install
    and no `PYTHONPATH`. Importing it the way the tests do must not quietly require more
    than that.
    """
    spec = importlib.util.spec_from_file_location("mi_ratchet", SCRIPT_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - only if the file vanishes
        raise RuntimeError(f"cannot import {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mi = _load_ratchet()

PATHS = mi.Paths.under(REPO_ROOT)
NODE = "tests/integration/schema/test_synthetic.py::test_mi01_thing"


@pytest.fixture(scope="module")
def catalogue() -> object:
    return mi.load_catalogue(PATHS.catalogue)


@pytest.fixture(scope="module")
def citations() -> object:
    return mi.scan_migrations(PATHS.migrations)


@pytest.fixture(scope="module")
def universe() -> object:
    return mi.collect_universe(PATHS.test_root, PATHS.repo_root)


def _synthetic(statuses: dict[str, str]) -> object:
    """A thirty-entry catalogue whose statuses are whatever the law under test needs."""
    return mi._selftest_catalogue(statuses)


def _write(tmp_path: Path, text: str, name: str) -> Path:
    """Park a catalogue variant on disk so `load_catalogue` can read it back."""
    target = tmp_path / name
    target.write_text(text, encoding="utf-8")
    return target


def _witnesses(owning: set[str]) -> dict[str, object]:
    return {
        f"MI{n:02d}": mi.Witnesses(
            mi_id=f"MI{n:02d}",
            declared=(NODE,) if f"MI{n:02d}" in owning else (),
            discovered=(),
            unresolved=(),
        )
        for n in range(1, 31)
    }


# ── The catalogue is a complete, well-formed statement ────────────────────────────────


def test_the_catalogue_holds_thirty_invariants_numbered_in_order(catalogue) -> None:
    # NB: no function in this file may carry an `_miNN_` token in its name. The ratchet
    # reports such names as *mentions* of an invariant, and a suite that talks about the
    # catalogue would otherwise appear to witness half of it.
    assert catalogue.ids == tuple(f"MI{n:02d}" for n in range(1, 31))
    assert len(catalogue) == 30


def test_every_statement_and_mechanism_is_present(catalogue) -> None:
    for inv in catalogue:
        assert len(inv.statement) >= 20, f"{inv.mi_id} has no statement worth reading"
        assert len(inv.mechanism) >= 8, f"{inv.mi_id} names no mechanism"


def test_every_sqlstate_is_a_gate_refusal(catalogue) -> None:
    for inv in catalogue:
        assert inv.sqlstate, f"{inv.mi_id} names no SQLSTATE"
        assert set(inv.sqlstate) <= mi.GATE_SQLSTATES, inv.mi_id


def test_no_invariant_claims_the_one_retryable_code(catalogue) -> None:
    # ARCHITECTURE.md §16: "40001 is the only retryable code". A retry is not a refusal,
    # so an invariant that produced it would be an invariant nothing ever enforced.
    for inv in catalogue:
        assert mi.RETRYABLE_SQLSTATE not in inv.sqlstate, inv.mi_id


def test_the_loader_refuses_an_invariant_that_names_40001() -> None:
    with pytest.raises(mi.CatalogueError, match="RETRYABLE"):
        mi._validate_sqlstates(("40001",), "MI99")


def test_instantiates_is_a_trappoint_invariant_or_deliberately_absent(catalogue) -> None:
    for inv in catalogue:
        assert inv.instantiates is None or inv.instantiates in mi.TRAPPOINT_INVARIANTS


def test_exactly_three_invariants_map_to_no_trappoint_invariant(catalogue) -> None:
    # §16 marks three rows '—', "and that is the interesting case": these are the
    # statements MAINLINE makes that the substrate does not.
    unmapped = {inv.mi_id for inv in catalogue if inv.instantiates is None}
    assert unmapped == {"MI08", "MI10", "MI21"}


def test_seven_headline_invariants_are_the_ones_sixteen_bolds(catalogue) -> None:
    headline = {inv.mi_id for inv in catalogue if inv.headline}
    assert headline == {"MI16", "MI25", "MI26", "MI27", "MI28", "MI29", "MI30"}


def test_every_status_is_pending_or_enforced(catalogue) -> None:
    for inv in catalogue:
        assert inv.status in mi.STATUSES, f"{inv.mi_id} is {inv.status!r}"


def test_a_gap_in_the_numbering_is_refused(tmp_path: Path) -> None:
    # A duplicate parses fine entry by entry, so only the whole-catalogue ordering check
    # catches it. A gap here is an invariant nobody owns, which is the one thing a
    # catalogue may not have.
    text = PATHS.catalogue.read_text(encoding="utf-8").replace("- id: MI17", "- id: MI18", 1)
    broken = tmp_path / "gap.yaml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(mi.CatalogueError, match="exactly once each"):
        mi.load_catalogue(broken)


def test_an_identifier_outside_the_catalogue_range_is_refused(tmp_path: Path) -> None:
    text = PATHS.catalogue.read_text(encoding="utf-8").replace("- id: MI17", "- id: MI99", 1)
    broken = tmp_path / "outside.yaml"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(mi.CatalogueError, match="expected MI01"):
        mi.load_catalogue(broken)


# ── owning_migrations is enforced, never trusted (P2) ─────────────────────────────────


def test_the_projection_is_computed_from_the_headers_and_not_from_the_catalogue(
    tmp_path: Path,
) -> None:
    # The claim the whole file rests on: this column is written from the migration tree,
    # not from whatever the author of the catalogue believed. Asserted against a tree
    # this test builds, so that it states a property of the projection rather than a
    # fact about the repository at one moment.
    tree = tmp_path / "migrations"
    tree.mkdir()
    (tree / "0001a_alpha.sql").write_text("-- MI: MI02, MI30\nSELECT 1;\n", encoding="utf-8")
    (tree / "0002_beta.sql").write_text("-- MI: MI30\nSELECT 1;\n", encoding="utf-8")
    projection = mi.project_owning_migrations(mi.scan_migrations(tree))
    assert projection["MI30"] == ("0001a", "0002")
    assert projection["MI02"] == ("0001a",)
    assert projection["MI11"] == ()


def test_the_projection_refuses_when_the_migration_tree_is_missing(tmp_path: Path) -> None:
    # P2's second half: the trigger RAISEs when the authoritative table has no row. An
    # empty projection here would report that no migration enforces any invariant, which
    # is a far more dangerous sentence than "I cannot tell you".
    with pytest.raises(mi.SourceMissing, match="migration tree is absent"):
        mi.scan_migrations(tmp_path / "nowhere")


def test_the_projection_refuses_a_migration_with_no_mi_header(tmp_path: Path) -> None:
    tree = tmp_path / "migrations"
    tree.mkdir()
    (tree / "0001_thing.sql").write_text("-- I: I01\nCREATE SCHEMA x;\n", encoding="utf-8")
    with pytest.raises(mi.SourceMissing, match="`-- MI:` lines"):
        mi.scan_migrations(tree)


def test_the_projection_refuses_a_filename_it_cannot_number(tmp_path: Path) -> None:
    tree = tmp_path / "migrations"
    tree.mkdir()
    (tree / "thing.sql").write_text("-- MI: MI01\nCREATE SCHEMA x;\n", encoding="utf-8")
    with pytest.raises(mi.SourceMissing, match="migration number"):
        mi.scan_migrations(tree)


def test_a_header_citing_an_unknown_invariant_is_refused(tmp_path: Path) -> None:
    tree = tmp_path / "migrations"
    tree.mkdir()
    (tree / "0001_thing.sql").write_text("-- MI: MI47\nCREATE SCHEMA x;\n", encoding="utf-8")
    violations = mi.unknown_citations(mi.scan_migrations(tree))
    assert len(violations) == 1
    assert "MI47" in violations[0]


def test_every_mi_the_tree_cites_is_one_the_catalogue_holds(catalogue, citations) -> None:
    assert mi.unknown_citations(citations) == []
    cited = {mi_id for c in citations for mi_id in c.owning}
    assert cited <= set(catalogue.ids)


def test_drift_in_the_projection_is_detected(catalogue, citations) -> None:
    projection = dict(mi.project_owning_migrations(citations))
    projection["MI01"] = (*projection["MI01"], "9999")
    drift = mi.migration_drift(catalogue, projection)
    assert any(d.startswith("MI01.owning_migrations") for d in drift)


def test_reconciliation_is_idempotent(citations) -> None:
    original = PATHS.catalogue.read_text(encoding="utf-8")
    projection = mi.full_projection(citations)
    once = mi.rewrite_owning_migrations(original, projection)
    assert mi.rewrite_owning_migrations(once, projection) == once


def test_reconciliation_rewrites_the_projected_field_and_nothing_else(
    catalogue, tmp_path: Path
) -> None:
    # Line surgery rather than a YAML round-trip, because the prose in this file is the
    # point of it. The risk line surgery carries is that it corrupts something it was not
    # aiming at, so that is what is asserted here — not the state of the tree today.
    original = PATHS.catalogue.read_text(encoding="utf-8")
    forced = {inv.mi_id: ("0001a", "9999z") for inv in catalogue}
    forced["MI31"] = ("0001a",)
    rewritten = mi.rewrite_owning_migrations(original, forced)
    assert rewritten != original

    reloaded = mi.load_catalogue(_write(tmp_path, rewritten, "forced.yaml"))
    assert [inv.mi_id for inv in reloaded] == [inv.mi_id for inv in catalogue]
    for after, before in zip(reloaded, catalogue, strict=True):
        assert after.owning_migrations == ("0001a", "9999z")
        assert after.statement == before.statement
        assert after.mechanism == before.mechanism
        assert after.sqlstate == before.sqlstate
        assert after.instantiates == before.instantiates
        assert after.headline == before.headline
        assert after.owning_tests == before.owning_tests
        assert after.status == before.status
    # Every comment in the file survives, which a PyYAML round-trip would not manage.
    assert original.count("#") == rewritten.count("#")


def test_reconciliation_leaves_an_uncited_invariant_with_an_empty_projection(
    catalogue, tmp_path: Path
) -> None:
    original = PATHS.catalogue.read_text(encoding="utf-8")
    rewritten = mi.rewrite_owning_migrations(original, {})
    reloaded = mi.load_catalogue(_write(tmp_path, rewritten, "empty.yaml"))
    assert all(inv.owning_migrations == () for inv in reloaded)
    assert len(reloaded) == len(catalogue)


def test_migration_numbers_survive_the_yaml_round_trip(catalogue) -> None:
    # YAML 1.1 reads `0020` as octal and `0029` as decimal 29. A migration number that
    # silently becomes an integer is a projection that silently stops matching, so the
    # emitter quotes and the loader must see strings.
    numbers = [n for inv in catalogue for n in inv.owning_migrations]
    assert numbers, "the projection is empty, so this test proves nothing"
    assert all(isinstance(n, str) for n in numbers)
    assert "0020" in numbers or any(n.startswith("00") for n in numbers)


# ── Proposals are not invariants ──────────────────────────────────────────────────────


def test_the_tree_proposes_a_thirty_first_invariant_and_the_catalogue_answers_it(
    catalogue, citations
) -> None:
    # Six recall migrations carry `-- proposes: MI31`. §16 is a numbered catalogue that
    # spec/, the conformance corpus and the submission all cite by number, so a header
    # comment may not amend it — but the ask has to be visible, and answered.
    assert "MI31" in mi.project_proposals(citations)
    recorded = {p.mi_id for p in catalogue.proposed}
    assert recorded == {"MI31"}
    assert recorded.isdisjoint(catalogue.ids)
    answer = next(p for p in catalogue.proposed if p.mi_id == "MI31")
    assert "NOT ADOPTED" in answer.disposition
    assert "MI25" in answer.disposition, "an unadopted proposal must say what covers it"


def test_an_unanswered_proposal_is_refused(catalogue) -> None:
    drift = mi.proposal_drift(catalogue, {"MI44": ("0500",)})
    assert any("MI44" in d for d in drift)
    assert any("ADR" in d for d in drift)


def test_a_proposal_may_not_be_numbered_inside_the_catalogue_range() -> None:
    with pytest.raises(mi.CatalogueError, match="not a proposal"):
        mi._parse_proposal(
            {
                "id": "MI07",
                "statement": "a statement long enough",
                "proposed_by": "somebody",
                "owning_migrations": [],
                "disposition": "a disposition long enough",
            },
            0,
        )


# ── The rendering ─────────────────────────────────────────────────────────────────────


def test_the_rendered_catalogue_has_been_written(catalogue) -> None:
    # Existence is a stable fact; byte-identity is a statement about the repository at one
    # moment and is asserted by `mi_ratchet check` in CI, not here. See the module
    # docstring: nothing in this file may go red for a reason other than PL-2's one case.
    assert PATHS.rendered.exists(), "run `python scripts/mi_ratchet.py reconcile --write`"
    rendered = PATHS.rendered.read_text(encoding="utf-8")
    assert "GENERATED BY scripts/mi_ratchet.py" in rendered
    assert all(inv.mi_id in rendered for inv in catalogue)


def test_rendering_is_deterministic(catalogue) -> None:
    assert mi.render_markdown(catalogue) == mi.render_markdown(catalogue)


def test_the_rendering_names_every_invariant_and_its_status(catalogue) -> None:
    rendered = mi.render_markdown(catalogue)
    for inv in catalogue:
        assert inv.mi_id in rendered
        assert inv.statement.strip("`") in rendered or inv.statement in rendered
    pending = len(catalogue.with_status("pending"))
    enforced = len(catalogue.with_status("enforced"))
    assert f"**{pending} pending · {enforced} enforced" in rendered


def test_a_status_change_changes_the_rendering(catalogue, tmp_path: Path) -> None:
    text = PATHS.catalogue.read_text(encoding="utf-8").replace(
        "    status: pending\n    adr: null\n", "    status: enforced\n    adr: null\n", 1
    )
    promoted = mi.load_catalogue(_write(tmp_path, text, "promoted.yaml"))
    assert mi.render_markdown(promoted) != mi.render_markdown(catalogue)
    assert "**enforced**" in mi.render_markdown(promoted)


# ── The two laws bite ─────────────────────────────────────────────────────────────────


def test_the_red_law_fires_when_a_pending_invariant_is_all_green() -> None:
    violations = mi.red_violations(_synthetic({}), _witnesses({"MI01"}), {NODE: mi.PASSED})
    assert len(violations) == 1
    assert violations[0].startswith(
        "MI01 is pending but its tests pass — promote it in mi_catalogue.yaml"
    )


def test_the_red_law_is_silent_when_one_owning_test_fails() -> None:
    assert mi.red_violations(_synthetic({}), _witnesses({"MI01"}), {NODE: mi.FAILED}) == []


def test_the_red_law_treats_a_node_pytest_never_reported_as_not_passing() -> None:
    # A test that did not run has not proved anything. Counting it as green is exactly the
    # accident that would let a pending invariant be promoted on no evidence.
    assert mi.red_violations(_synthetic({}), _witnesses({"MI01"}), {}) == []


def test_the_red_law_ignores_an_invariant_nothing_witnesses() -> None:
    assert mi.red_violations(_synthetic({}), _witnesses(set()), {NODE: mi.PASSED}) == []


def test_an_unwitnessed_pending_invariant_is_still_reported() -> None:
    silent = mi.unwitnessed(_synthetic({}), _witnesses({"MI01"}), "pending")
    assert "MI01" not in silent
    assert len(silent) == 29


def test_the_green_law_fires_when_an_enforced_invariant_regresses() -> None:
    violations = mi.green_violations(
        _synthetic({"MI02": "enforced"}), _witnesses({"MI02"}), {NODE: mi.FAILED}
    )
    assert len(violations) == 1
    assert "MI02 is enforced but not green" in violations[0]


def test_the_green_law_refuses_to_certify_on_a_skip() -> None:
    # An invariant certified by a test that did not run is the assertion-free green PL-2
    # exists to forbid. `requires_cluster` skipping is precisely how that would happen.
    violations = mi.green_violations(
        _synthetic({"MI02": "enforced"}), _witnesses({"MI02"}), {NODE: mi.SKIPPED}
    )
    assert len(violations) == 1
    assert "skipped" in violations[0]


def test_the_green_law_refuses_an_enforced_invariant_no_test_witnesses() -> None:
    violations = mi.green_violations(
        _synthetic({"MI03": "enforced"}), _witnesses({"MI01"}), {NODE: mi.PASSED}
    )
    assert len(violations) == 1
    assert "no test resolves to it" in violations[0]


def test_the_green_law_is_silent_when_the_enforced_invariant_passes() -> None:
    assert (
        mi.green_violations(
            _synthetic({"MI02": "enforced"}), _witnesses({"MI02"}), {NODE: mi.PASSED}
        )
        == []
    )


def test_an_xpass_is_not_a_pass() -> None:
    # A test that was expected to fail and did not has not been read by anyone.
    violations = mi.green_violations(
        _synthetic({"MI02": "enforced"}), _witnesses({"MI02"}), {NODE: mi.XPASSED}
    )
    assert len(violations) == 1


# ── The ratchet is one-way ────────────────────────────────────────────────────────────


def test_demotion_without_an_adr_is_refused() -> None:
    before = _synthetic({"MI05": "enforced"})
    after = _synthetic({})
    violations = mi.demotion_violations(before, after, "chore: tidy up")
    assert len(violations) == 1
    assert "MI05" in violations[0]


def test_demotion_that_cites_an_adr_is_admitted() -> None:
    before = _synthetic({"MI05": "enforced"})
    after = _synthetic({})
    assert mi.demotion_violations(before, after, "revert the guard, see ADR-0011") == []


def test_a_promotion_is_always_admitted() -> None:
    before = _synthetic({})
    after = _synthetic({"MI05": "enforced"})
    assert mi.demotion_violations(before, after, "promote MI05") == []


def test_the_demotion_guard_reads_the_committed_catalogue(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    shutil.copyfile(PATHS.catalogue, base)
    argv = [
        "demote-check",
        "--repo-root",
        str(REPO_ROOT),
        "--base",
        str(base),
        "--message",
        "no change",
    ]
    assert mi.main(argv) == mi.EXIT_OK


# ── Resolution ────────────────────────────────────────────────────────────────────────


def test_every_selector_in_the_catalogue_is_well_formed(catalogue) -> None:
    for inv in catalogue:
        for selector in inv.owning_tests:
            parsed = mi.validate_selector(selector, inv.mi_id)
            assert parsed.relpath.startswith("tests/")


def test_a_selector_that_does_not_address_a_test_is_refused() -> None:
    with pytest.raises(mi.CatalogueError, match="under tests/"):
        mi.validate_selector("verticals/mainline/db/migrations/0001a_schema_mainline.sql", "MI01")


def test_a_selector_naming_a_non_test_function_is_refused() -> None:
    with pytest.raises(mi.CatalogueError, match="test_ function"):
        mi.validate_selector("tests/integration/schema/test_mi_gate.py::helper", "MI02")


def test_every_invariant_declares_at_least_one_owning_test(catalogue) -> None:
    for inv in catalogue:
        assert inv.owning_tests, f"{inv.mi_id} declares no owning test at all"


def test_resolution_finds_the_tests_that_already_exist(catalogue, universe) -> None:
    resolution = mi.resolve(catalogue, universe)
    witnessed = {mi_id for mi_id, w in resolution.items() if not w.is_unwitnessed}
    # These are the invariants some worker has already written a test for. The set only
    # ever grows; asserting a floor catches a rename that silently orphans an invariant.
    assert {"MI01", "MI10", "MI11", "MI14", "MI15", "MI19"} <= witnessed


def test_a_test_marked_with_an_invariant_is_discovered_without_a_catalogue_entry() -> None:
    universe = (mi.TestFn(relpath="tests/x/test_a.py", name="test_anything", marked=("MI09",)),)
    resolution = mi.resolve(_synthetic({}), universe)
    assert resolution["MI09"].discovered == ("tests/x/test_a.py::test_anything",)


def test_naming_an_invariant_is_a_mention_and_never_a_witness() -> None:
    # The distinction that keeps a green unit test from promoting a database invariant.
    # `@pytest.mark.mi` is the author claiming to prove it; a token in a name is not.
    named_only = mi.TestFn(
        relpath="tests/x/test_a.py",
        name="test_advisory_because_mi09_would_refuse_otherwise",
        marked=(),
        mentioned=("MI09",),
    )
    resolution = mi.resolve(_synthetic({}), (named_only,))
    assert resolution["MI09"].is_unwitnessed
    assert mi.mentions(_synthetic({}), (named_only,))["MI09"] == (named_only.nodeid,)
    # And therefore a passing mention cannot trip the promotion law.
    assert mi.red_violations(_synthetic({}), resolution, {named_only.nodeid: mi.PASSED}) == []


def test_the_repositorys_own_fixity_unit_test_is_a_mention_not_a_witness(
    catalogue, universe
) -> None:
    # The concrete case this rule exists for: a pure-Python fixity unit test whose name
    # refers to the invariant it reasons about, and which never touches the database.
    mentioned = mi.mentions(catalogue, universe)
    assert any("test_emit.py" in node for node in mentioned["MI21"])
    assert mi.resolve(catalogue, universe)["MI21"].is_unwitnessed


def test_a_selector_matching_nothing_is_reported_as_unresolved(catalogue, universe) -> None:
    resolution = mi.resolve(catalogue, universe)
    unresolved = {mi_id: w.unresolved for mi_id, w in resolution.items() if w.unresolved}
    # Forward-declared selectors are expected while the owning workers have not landed.
    # What must never happen is a selector that is *malformed*, and that is asserted above.
    assert unresolved, "every selector resolves, so the forward-declaration path is untested"
    for selectors in unresolved.values():
        for selector in selectors:
            assert "::" in selector or selector.endswith(".py")


# ── The ratchet's own shape and CLI ───────────────────────────────────────────────────


def test_this_suite_holds_exactly_one_deliberately_red_case() -> None:
    names = mi.red_case_names(PATHS.red_suite)
    assert names == ("test_red_every_invariant_is_enforced",), (
        f"PL-2 wants exactly one nameable cause for this suite being red; found {list(names)}"
    )


def test_check_catches_a_catalogue_that_has_drifted_from_the_tree(tmp_path: Path) -> None:
    # `check`'s verdict on the *real* repository is a CI step, not a test outcome. What is
    # asserted here is that it would catch drift if there were any — the mechanism, not
    # the moment.
    text = PATHS.catalogue.read_text(encoding="utf-8")
    drifted = _write(tmp_path, mi.rewrite_owning_migrations(text, {}), "drifted.yaml")
    violations = mi.check_violations(PATHS.with_overrides(catalogue=drifted))
    assert violations, "an emptied projection must not pass check"
    assert any("owning_migrations" in v for v in violations)


def test_check_catches_a_rendering_that_has_gone_stale(tmp_path: Path) -> None:
    stale = tmp_path / "MI-CATALOGUE.md"
    stale.write_text("# not the catalogue\n", encoding="utf-8")
    violations = mi.check_violations(PATHS.with_overrides(rendered=stale))
    assert any("drifted from the catalogue" in v for v in violations)


def test_check_names_the_one_command_that_fixes_a_stale_rendering(tmp_path: Path) -> None:
    stale = tmp_path / "MI-CATALOGUE.md"
    stale.write_text("stale\n", encoding="utf-8")
    violations = mi.check_violations(PATHS.with_overrides(rendered=stale))
    assert any("reconcile --write" in v for v in violations)


def test_the_selftest_subcommand_proves_both_laws_bite(capsys) -> None:
    assert mi.main(["selftest"]) == mi.EXIT_OK
    assert "laws bite" in capsys.readouterr().out


def test_the_report_subcommand_states_the_counts(capsys) -> None:
    assert mi.main(["report", "--repo-root", str(REPO_ROOT)]) == mi.EXIT_OK
    assert "pending /" in capsys.readouterr().out


def test_a_missing_catalogue_is_cannot_determine_not_a_violation(tmp_path: Path) -> None:
    # Exit 2 is reserved for "I could not measure", and it is a different sentence from
    # "the law was broken". A ratchet that conflates them reports colours it never saw.
    code = mi.main(["check", "--repo-root", str(REPO_ROOT), "--catalogue", str(tmp_path / "no")])
    assert code == mi.EXIT_CANNOT_DETERMINE


_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest">
<testcase classname="tests.integration.schema.test_x" name="test_a" time="0.1" />
<testcase classname="tests.integration.schema.test_x" name="test_b">
  <failure>boom</failure></testcase>
<testcase classname="tests.integration.schema.test_x" name="test_c"><skipped/></testcase>
<testcase classname="tests.integration.schema.test_x.TestGroup" name="test_d" time="0.1" />
<testcase classname="tests.integration.schema.test_x" name="test_e[param]" time="0.1" />
</testsuite></testsuites>
"""


def test_a_junit_report_is_read_back_into_outcomes(tmp_path: Path) -> None:
    report = tmp_path / "j.xml"
    report.write_text(_JUNIT, encoding="utf-8")
    outcomes = mi.read_junit(report).outcomes
    assert outcomes["tests/integration/schema/test_x.py::test_a"] == mi.PASSED
    assert outcomes["tests/integration/schema/test_x.py::test_b"] == mi.FAILED
    assert outcomes["tests/integration/schema/test_x.py::test_c"] == mi.SKIPPED
    # A test class shows up as a trailing capitalised component of `classname`; pytest's
    # xunit2 default omits the `file` attribute entirely, so this is the only signal.
    assert outcomes["tests/integration/schema/test_x.py::test_d"] == mi.PASSED
    # Parametrised ids collapse onto the function, which is what a selector addresses.
    assert outcomes["tests/integration/schema/test_x.py::test_e"] == mi.PASSED


def test_a_junit_report_that_names_nothing_is_refused(tmp_path: Path) -> None:
    report = tmp_path / "empty.xml"
    report.write_text('<?xml version="1.0"?><testsuites/>\n', encoding="utf-8")
    with pytest.raises(mi.SourceMissing, match="no test outcomes"):
        mi.read_junit(report)


def test_an_absent_junit_report_is_refused(tmp_path: Path) -> None:
    with pytest.raises(mi.SourceMissing, match="JUnit report is absent"):
        mi.read_junit(tmp_path / "never-written.xml")


def test_the_worst_phase_of_a_node_is_the_outcome_recorded() -> None:
    # setup / call / teardown are three reports for one node. A passing call after a
    # failing setup must not overwrite the failure, or an errored test reads as green.
    assert mi._severity(mi.ERROR) > mi._severity(mi.FAILED) > mi._severity(mi.SKIPPED)
    assert mi._severity(mi.SKIPPED) > mi._severity(mi.PASSED)


def test_the_lock_is_a_cross_check_and_not_the_authority(citations) -> None:
    # `migrations.lock.json` is a manifest derived from these headers. Where it has an
    # opinion it must agree; where it has fallen behind the tree that is the lock owner's
    # problem, not a corruption of the catalogue.
    lock = mi.load_lock(PATHS.lock)
    assert mi.lock_disagreements(citations, lock) == []


# ── PL-2 · THE ONE RED CASE ───────────────────────────────────────────────────────────


def test_red_every_invariant_is_enforced(catalogue) -> None:
    """RED BY DESIGN. The data-model domain is done when this passes, and not before.

    `docs/leads/datamodel.md` §7: *"The domain is done when every MI in mi_catalogue.yaml
    reads `enforced`, and not one of them was ever green before its mechanism existed."*

    Strata S1-S7 are inert tables; nothing refuses anything until S8 lands the functions
    and triggers, so this failure is the intended state of the build and DR-4 accepts it
    explicitly. Do not `xfail` it, do not skip it, do not delete it: an `xfail` would make
    this suite green, and a green suite here would assert precisely nothing.

    It goes green exactly once — the day the last invariant is promoted — and from then on
    it is the regression test that keeps the catalogue from quietly sliding back.
    """
    pending = [inv.mi_id for inv in catalogue if not inv.is_enforced]
    assert not pending, (
        f"{len(pending)} of {len(catalogue)} MAINLINE invariants are still pending: "
        f"{', '.join(pending)}. This is PL-2's red case and it is expected to fail until "
        f"every mechanism exists and its owning test has been observed to pass on a real "
        f"cluster. Promote in verticals/mainline/db/invariants/mi_catalogue.yaml."
    )
