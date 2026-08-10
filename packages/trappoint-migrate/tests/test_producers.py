# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Rule D — every relation a tree names, some file in that tree CREATEs.

The defect this rule exists for shipped seven times into one schema and was found by a
deployment: five tables (then seven) had their triggers, views and RLS policies written
and nobody wrote the ``CREATE TABLE``. Every consumer file passed every other rule in
:mod:`trappoint_migrate.lint` — they cite an invariant, they carry one statement, they
use no sequence, their numbers sit in bands whose mode is right — because every other
rule is a statement about *a file*, and this is a statement about *a tree*.

Two directions matter here and the second is the harder one:

1. a reference with no producer **fires** — otherwise the rule asserts nothing;
2. a type cast, a function call, a view and a procedure **do not** fire — otherwise the
   rule is noise, an author adds a lookahead for ``::`` and ``(``, the lookahead is
   fragile, and two releases later somebody turns the rule off. The way this module
   avoids that is not a heuristic: it collects the producer set from *every* object
   kind, so a type that is cast to is a type that was created.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trappoint_migrate.producers import (
    ALLOWLISTED_SCHEMAS,
    GOVERNED_SCHEMAS,
    PRODUCER_ABSENT_RULE,
    absent_detail,
    census,
    producers_in,
    references_in,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
CENSUS_BEFORE = REPO_ROOT / "evidence" / "producers" / "producer-census-before.json"

HEADER = "-- MI02: why this file exists.\n"

#: The seven relations the producer-completion wave of 2026-08-10 was called to author.
#: Recorded here as a **ratchet, not a target**: the live tree may hold fewer of these as
#: the wave lands and must hold zero when it is finished, but an eighth name appearing
#: means a new instance of the defect class and the suite says so the day it lands.
WAVE_SEVEN = frozenset(
    {
        "mainline_ops.outbox",
        "mainline.identity_assignment",
        "mainline.patrol_run",
        "mainline_meas.agent_action",
        "mainline_meas.standing",
        "mainline_meas.person_measure_policy",
        "mainline_ops.site_register_signal",
    }
)


def tree(tmp_path: Path, **files: str) -> Path:
    """Materialise a synthetic migration tree and return its root."""
    root = tmp_path / "migrations"
    root.mkdir(exist_ok=True)
    for name, body in files.items():
        (root / name.replace("__", ".")).write_text(HEADER + body, encoding="utf-8")
    return root


def absent(root: Path) -> set[str]:
    return {a.relation for a in census(root).absent}


# ── (1) a reference with no producer fires ──────────────────────────────────────────


def test_a_reference_with_no_producer_in_the_tree_is_reported(tmp_path: Path) -> None:
    trigger = "CREATE TRIGGER t AFTER INSERT ON mainline_ops.outbox\n"
    root = tree(tmp_path, **{"0121_trg_check_materialised__sql": trigger})
    assert absent(root) == {"mainline_ops.outbox"}


def test_the_producer_may_live_in_any_file_of_the_tree(tmp_path: Path) -> None:
    # The whole point of a tree-level rule: 0099 creates it, 0121 uses it, and neither
    # file alone tells you whether the schema is complete.
    root = tree(
        tmp_path,
        **{
            "0099_outbox__sql": "CREATE TABLE mainline_ops.outbox (id UUID PRIMARY KEY);\n",
            "0121_trg__sql": "CREATE TRIGGER t AFTER INSERT ON mainline_ops.outbox\n",
        },
    )
    assert absent(root) == set()


def test_a_finding_names_the_referencing_file_the_line_and_the_relation(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        **{"0163_v_fixity__sql": "SELECT 1;\nSELECT 2;\nSELECT * FROM mainline.patrol_run;\n"},
    )
    (gap,) = census(root).absent
    assert gap.relation == "mainline.patrol_run"
    assert gap.first.path.name == "0163_v_fixity.sql"
    # Line 4: the one-line header, then two SELECTs. Comment stripping preserves
    # newlines precisely so this number is the line a reader will open the file to.
    assert gap.first.line == 4
    detail = absent_detail(gap, root=root)
    assert "mainline.patrol_run" in detail
    assert "0163_v_fixity.sql:4" in detail


def test_one_finding_per_relation_however_many_files_name_it(tmp_path: Path) -> None:
    # Eight files name `mainline_meas.standing` in the real tree. Eight findings would be
    # eight copies of one fact whose remedy is one file, so the rule reports the relation
    # once, anchored where the forward-only chain will actually halt.
    root = tree(
        tmp_path,
        **{
            "0171_v_a__sql": "SELECT * FROM mainline_meas.standing;\n",
            "0172_v_b__sql": "SELECT * FROM mainline_meas.standing;\n",
            "0187_rls__sql": "ALTER TABLE mainline_meas.standing ENABLE ROW LEVEL SECURITY;\n",
        },
    )
    (gap,) = census(root).absent
    assert gap.first.path.name == "0171_v_a.sql"
    assert [r.path.name for r in gap.references] == [
        "0171_v_a.sql",
        "0172_v_b.sql",
        "0187_rls.sql",
    ]
    assert "3 site(s)" in absent_detail(gap, root=root)


def test_a_body_only_reference_still_counts(tmp_path: Path) -> None:
    # This is the 0101/0121 case exactly. `CREATE FUNCTION` does not resolve table
    # references inside a PL/pgSQL body on CockroachDB v26.2.5, so the function applies
    # clean and the trigger that binds it is where the chain dies. The rule must see
    # into the body or it misses the relation that actually stopped the deployment.
    body = (
        "CREATE FUNCTION mainline.fn_check_materialised() RETURNS TRIGGER AS $$\n"
        "BEGIN\n"
        "  INSERT INTO mainline_ops.outbox (kind) VALUES ('check_opened');\n"
        "  RETURN NEW;\n"
        "END;\n"
        "$$ LANGUAGE plpgsql;\n"
    )
    root = tree(tmp_path, **{"0101_fn__sql": body})
    assert absent(root) == {"mainline_ops.outbox"}


# ── (2) a view producer does not fire ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("producer", "consumer"),
    [
        ("CREATE VIEW mainline_audit.v_ledger AS SELECT 1;", "mainline_audit.v_ledger"),
        (
            "CREATE MATERIALIZED VIEW mainline_qa.v_profile AS SELECT 1;",
            "mainline_qa.v_profile",
        ),
        ("CREATE OR REPLACE VIEW mainline.v_safe AS SELECT 1;", "mainline.v_safe"),
        ("CREATE TABLE IF NOT EXISTS mainline.site (id UUID);", "mainline.site"),
        ("CREATE OR REPLACE PROCEDURE mainline.merge_permit() AS $$ $$;", "mainline.merge_permit"),
        (
            "CREATE TYPE IF NOT EXISTS mainline.subject_state AS ENUM ('a');",
            "mainline.subject_state",
        ),
    ],
)
def test_every_object_kind_counts_as_a_producer(
    tmp_path: Path, producer: str, consumer: str
) -> None:
    root = tree(
        tmp_path,
        **{"0010_produce__sql": producer + "\n", "0200_consume__sql": f"SELECT {consumer};\n"},
    )
    assert absent(root) == set()


# ── (3) a function call and a type cast are not absent relations ────────────────────


def test_a_type_cast_does_not_fire_because_the_type_has_a_producer(tmp_path: Path) -> None:
    # The naive version of this rule — CREATE TABLE only — reports `mainline.subject_state`
    # as an absent relation, and the fix an author reaches for is a lookahead for `::`.
    # Collecting the producer set from every object kind removes the problem instead of
    # papering over it, and this test is what keeps that property.
    root = tree(
        tmp_path,
        **{
            "0011_type__sql": "CREATE TYPE mainline.subject_state AS ENUM ('open', 'closed');\n",
            "0050_permit__sql": (
                "CREATE TABLE mainline.permit (\n"
                "  state mainline.subject_state NOT NULL DEFAULT 'open'::mainline.subject_state\n"
                ");\n"
            ),
        },
    )
    assert absent(root) == set()


def test_a_function_call_does_not_fire_because_the_function_has_a_producer(
    tmp_path: Path,
) -> None:
    root = tree(
        tmp_path,
        **{
            "0107_fn__sql": (
                "CREATE FUNCTION mainline.fn_refuse_mutation() RETURNS TRIGGER AS $$\n"
                "BEGIN RAISE EXCEPTION 'append-only'; END;\n"
                "$$ LANGUAGE plpgsql;\n"
            ),
            "0128_trg__sql": (
                "CREATE TRIGGER append_only BEFORE UPDATE ON mainline.permit\n"
                "  FOR EACH ROW EXECUTE FUNCTION mainline.fn_refuse_mutation();\n"
            ),
        },
    )
    # `mainline.permit` has no producer here and is reported; the *function call* is not.
    assert absent(root) == {"mainline.permit"}


def test_a_mention_in_a_comment_is_not_a_reference(tmp_path: Path) -> None:
    # `-- requires: mainline_ops.outbox` is a header convention in this repository. If a
    # comment created a reference, every well-documented consumer would be a finding and
    # the rule would be uninstallable.
    root = tmp_path / "migrations"
    root.mkdir()
    (root / "0121_trg.sql").write_text(
        "-- MI02: the projection weld.\n"
        "-- requires: mainline_ops.outbox · mainline_meas.standing\n"
        "/* also mainline.patrol_run */\n"
        "SELECT 1;\n",
        encoding="utf-8",
    )
    assert absent(root) == set()


def test_a_commented_out_producer_does_not_satisfy_the_rule(tmp_path: Path) -> None:
    # The inverse, and the more dangerous direction: comment stripping runs on both
    # halves, so a `-- CREATE TABLE …` cannot be mistaken for the table.
    root = tmp_path / "migrations"
    root.mkdir()
    (root / "0099_outbox.sql").write_text(
        "-- MI02\n-- CREATE TABLE mainline_ops.outbox (id UUID);\nSELECT 1;\n", encoding="utf-8"
    )
    (root / "0121_trg.sql").write_text(
        HEADER + "CREATE TRIGGER t AFTER INSERT ON mainline_ops.outbox\n", encoding="utf-8"
    )
    assert absent(root) == {"mainline_ops.outbox"}


# ── (4) the allowlist ───────────────────────────────────────────────────────────────


def test_the_substrate_and_catalog_schemas_are_never_reported(tmp_path: Path) -> None:
    # `trappoint.*` is created by `trappoint migrate bootstrap` before the first
    # migration runs, and the other four belong to the engine. None of them is ever
    # produced by a migration, so without the allowlist the rule would report five
    # findings on a perfectly healthy tree.
    body = "\n".join(
        f"ALTER TABLE {schema}.some_object ADD COLUMN x INT8;" for schema in ALLOWLISTED_SCHEMAS
    )
    root = tree(tmp_path, **{"0001_probe__sql": body + "\n"})
    assert absent(root) == set()


def test_the_allowlist_holds_even_when_the_governed_set_is_widened(tmp_path: Path) -> None:
    # The default governed set cannot match an allowlisted schema, so the allowlist would
    # be untested — and an untested allowlist is one that silently stops working when the
    # governed set grows. Widen it here so the filter is the only thing standing between
    # `trappoint.schema_migration` and a finding.
    root = tree(tmp_path, **{"0001_probe__sql": "SELECT * FROM trappoint.schema_migration;\n"})
    widened = (*GOVERNED_SCHEMAS, "trappoint")
    assert census(root, governed_schemas=widened).absent == ()
    hits = references_in("SELECT * FROM trappoint.schema_migration;", governed_schemas=widened)
    assert hits == []


def test_an_ungoverned_schema_is_simply_not_this_tree_s_business(tmp_path: Path) -> None:
    root = tree(tmp_path, **{"0001_probe__sql": "SELECT * FROM someone_elses.table_x;\n"})
    assert absent(root) == set()


# ── the walk itself ─────────────────────────────────────────────────────────────────


def test_only_migration_shaped_files_are_walked(tmp_path: Path) -> None:
    root = tmp_path / "migrations"
    root.mkdir()
    (root / "README.sql").write_text("SELECT * FROM mainline.never_created;\n", encoding="utf-8")
    (root / "GRANTS.yaml").write_text("relation: mainline.also_never_created\n", encoding="utf-8")
    assert census(root).files == ()
    assert absent(root) == set()


def test_an_absent_tree_produces_an_empty_census(tmp_path: Path) -> None:
    report = census(tmp_path / "not-rendered-yet")
    assert report.files == ()
    assert report.absent == ()
    assert report.ok


def test_producers_in_ignores_unqualified_names() -> None:
    # `CREATE TRIGGER trg_x ON mainline.permit` names the trigger unqualified; the
    # reference pattern only ever yields `schema.object`, so an unqualified producer
    # could not answer one and inventing a qualification for it would be a guess.
    found = producers_in("CREATE TRIGGER trg_x AFTER INSERT ON mainline.permit")
    assert found == set()


def test_producers_in_reads_index_and_policy_targets_as_references_not_producers() -> None:
    sql = "CREATE UNIQUE INDEX one_live ON mainline.disposition (subject_id) WHERE live;"
    assert producers_in(sql) == set()
    assert [relation for relation, _ in references_in(sql)] == ["mainline.disposition"]


# ── the committed tree, and the red that was recorded ───────────────────────────────


def test_the_committed_tree_grows_no_eighth_gap() -> None:
    """A RATCHET, not a target.

    The producer-completion wave of 2026-08-10 was called to author seven relations. This
    assertion holds at every point of that wave — seven before it starts, fewer as the
    files land, zero when it is finished — and fails the moment an *eighth* name appears,
    which is a new instance of the defect class rather than the one being repaired.

    It is deliberately not ``== 7``: pinning the count would turn every landed producer
    into a broken test, and a test that a worker has to edit to make progress is a test
    that gets edited until it says nothing.
    """
    if not MIGRATIONS.is_dir():
        pytest.skip("the vertical's migration tree is absent from this checkout")
    observed = absent(MIGRATIONS)
    unexpected = sorted(observed - WAVE_SEVEN)
    assert unexpected == [], (
        f"{len(unexpected)} relation(s) are referenced by this tree and created by no "
        f"file in it, and they are not among the seven the producer-completion wave was "
        f"called to author: {unexpected}. A consumer without a producer applies clean "
        f"until the first statement that resolves it and then halts the forward-only "
        f"chain; the remedy is to write the producer, never to delete the reference."
    )


def test_the_observed_red_is_recorded_and_names_exactly_the_seven() -> None:
    """PL-2: a lint that has never been observed red asserts nothing.

    ``evidence/producers/producer-census-before.json`` is that observation — the rule run
    over the 261-file tree at the commit named in the artefact, before any producer
    landed. This test keeps the artefact honest about what it recorded; it does not read
    the live tree, which has moved on by design.
    """
    if not CENSUS_BEFORE.is_file():
        pytest.skip("the producer census artefact is absent from this checkout")
    document = json.loads(CENSUS_BEFORE.read_text(encoding="utf-8"))
    assert document["rule"] == PRODUCER_ABSENT_RULE
    before = document["before"]
    assert before["files"] == 261
    assert set(before["absent_relations"]) == set(WAVE_SEVEN)
    for entry in before["absent"]:
        assert entry["references"], entry["relation"]
        # This rule reads files. Nothing was executed, so there is no SQLSTATE to quote —
        # which is the entire advantage over discovering the same fact at file 156.
        assert entry["sqlstate"] is None
        for site in entry["references"]:
            assert site["file"].endswith(".sql")
            assert site["line"] >= 1
