# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Python vocabulary and the SQL vocabulary are the same vocabulary.

Parsed out of the migration files, with no cluster.  These are exactly the drifts
that would otherwise be discovered by a ``23514`` in a nightly job three weeks
after the edit that caused them:

* a column named in ``sql.py`` that the DDL does not have;
* an ``outcome`` the judge can emit that ``outcome_closed`` refuses;
* a residue reason the derivation can produce that ``residue_reason_closed``
  refuses — the boundary note in `docs/leads/algorithms.md` §4 says there is no
  sixth value and this is where that is held;
* a rule id the lattice can witness that ``witness_rule_ids_closed`` refuses.

They also hold the migration NUMBERS, because the number is the part a reader is
most likely to get from a stale document: the worker brief for this file says
``0209_meas_mutation.sql`` and ``0200``+ is UNALLOCATED.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mainline_domain.contracts import RULE_IDS
from mainline_mutation.judge import MATCHER_RESIDUE
from mainline_mutation.model import OUTCOMES
from mainline_mutation.sql import INSERT_RESULT, INSERT_RUN, RESULT_COLUMNS, RUN_COLUMNS

MIGRATIONS = Path(__file__).resolve().parents[3] / "verticals" / "mainline" / "db" / "migrations"
RUN_SQL = MIGRATIONS / "0049y_meas_mutation_run.sql"
RESULT_SQL = MIGRATIONS / "0049z_meas_mutation_result.sql"
TRIGGERS = (
    MIGRATIONS / "0149y_trg_mutation_run_append_only.sql",
    MIGRATIONS / "0149z_trg_mutation_result_append_only.sql",
)

#: The five values in `mainline.identity_residue`'s CHECK. There is no sixth
#: (docs/leads/algorithms.md §4, boundary note).
RESIDUE_REASONS = ("unmatched", "ambiguous", "anchor_drop", "opaque_control", "citation_unresolved")


def _body(path: Path) -> str:
    """The SQL with every ``--`` comment removed, whole-line and trailing alike.

    Trailing comments matter: ``-- the ORIGINDIFF measurement; NULL for 1-step``
    carries a semicolon, and a statement counter that did not strip it would
    report three statements in a one-statement file.  No string literal in these
    migrations contains ``--``, so splitting on it is safe here — and
    ``test_the_ban_on_sequences_holds`` reads the same body, so a mangled one
    would be visible rather than silent.
    """
    kept: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.split("--", 1)[0].rstrip()
        if code:
            kept.append(code)
    return "\n".join(kept)


def _declared_columns(path: Path) -> set[str]:
    body = _body(path)
    inner = body[body.index("(") + 1 : body.rindex(")")]
    columns: set[str] = set()
    for line in inner.splitlines():
        stripped = line.strip()
        match = re.match(r"^([a-z_][a-z0-9_]*)\s+[A-Z]", stripped)
        if match and not stripped.upper().startswith(("CONSTRAINT", "INDEX", "PRIMARY", "FOREIGN")):
            columns.add(match.group(1))
    return columns


def test_the_migrations_exist_where_the_allocation_grants_them():
    assert RUN_SQL.exists(), (
        "the run table must be at 0049y. The brief names 0209 and the migration reconciliation "
        "ruling of 2026-08-08 marks 0200+ UNALLOCATED; lint rule B refuses any file that claims "
        "a number no band grants"
    )
    assert RESULT_SQL.exists()
    for trigger in TRIGGERS:
        assert trigger.exists()


def test_no_file_of_this_worker_claims_an_unallocated_number():
    offenders = [p.name for p in MIGRATIONS.glob("02*.sql")] + [
        p.name for p in MIGRATIONS.glob("0209*")
    ]
    assert not offenders, f"{offenders} claim numbers the allocation marks UNALLOCATED"


@pytest.mark.parametrize("path", [RUN_SQL, RESULT_SQL, *TRIGGERS])
def test_one_top_level_statement_per_file(path):
    body = _body(path).strip()
    assert body.count(";") == 1, "MR-5: exactly one top-level SQL statement per file"
    assert body.endswith(";")


@pytest.mark.parametrize("path", [RUN_SQL, RESULT_SQL, *TRIGGERS])
def test_the_linted_header_keys_are_present(path):
    text = path.read_text(encoding="utf-8")
    for key in ("SPDX-License-Identifier:", "MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
        assert key in text, f"{path.name} is missing the linted header key {key!r}"
    assert "@rendered-by" not in text, (
        "these are AUTHORED files in an authored band; a rendered banner is a lint failure "
        "(allocation rule B)"
    )


def test_the_ban_on_sequences_holds():
    for path in (RUN_SQL, RESULT_SQL, *TRIGGERS):
        body = _body(path).lower()
        for banned in ("create sequence", "nextval(", "serial", "unique_rowid("):
            assert banned not in body, f"{path.name} uses {banned!r}, which is banned repo-wide"


def test_every_python_run_column_exists_in_the_ddl():
    declared = _declared_columns(RUN_SQL)
    missing = sorted(set(RUN_COLUMNS) - declared)
    assert not missing, f"sql.py names run columns the DDL does not have: {missing}"


def test_every_python_result_column_exists_in_the_ddl():
    declared = _declared_columns(RESULT_SQL)
    missing = sorted(set(RESULT_COLUMNS) - declared)
    assert not missing, f"sql.py names result columns the DDL does not have: {missing}"


def test_the_insert_statements_are_well_formed():
    assert INSERT_RUN.count("%s") == len(RUN_COLUMNS)
    assert INSERT_RESULT.count("%s") == len(RESULT_COLUMNS)
    assert "mainline_meas.mutation_run" in INSERT_RUN
    assert "mainline_meas.mutation_result" in INSERT_RESULT


#: CockroachDB v26.2.5 reserved words that this repository's migrations plausibly reach for
#: as column names. `FAMILY` is the one that actually bit (0049z, 42601); the rest are here
#: because the cost of listing them is one tuple and the cost of missing one is a migration
#: chain that stops before the merge gate.
RESERVED_COLUMN_NAMES = (
    "family",
    "index",
    "constraint",
    "table",
    "column",
    "order",
    "limit",
    "offset",
    "primary",
    "default",
    "user",
    "grant",
    "window",
    "range",
)


@pytest.mark.parametrize("path", [RUN_SQL, RESULT_SQL])
def test_no_column_is_spelled_with_a_reserved_keyword(path):
    """The 42601 that stood between this repository and its central claim.

    ``0049z`` declared ``family STRING NOT NULL``. ``FAMILY`` is reserved in CockroachDB —
    it introduces a column family, as ``0024_commit_obj.sql`` and ``0029_clause_version.sql``
    both use it — so the parser read the column name as the keyword and the file returned
    ``42601``. Its allocation key ``(49, "z")`` sorts before ``(50, "")``, so a forward-only
    runner never reached ``0050_permit.sql``, let alone ``0115_fn_permit_merge_gate.sql``.

    Quoting is NOT the repair and this test does not accept it. Measured on the live node:
    ``"family"`` survives the DDL and a quoted read, while ``INSERT INTO t (id, family)``,
    ``SELECT id, family`` and ``UPDATE t SET family = …`` all still return ``42601``. Since
    :data:`~mainline_mutation.sql.RESULT_COLUMNS` is interpolated into a column list
    unquoted, a quoted DDL would only have moved the failure from migration time to run
    time. The column is ``mutation_family``, and this assertion is what keeps it that way.
    """
    declared = _declared_columns(path)
    offenders = sorted(declared & set(RESERVED_COLUMN_NAMES))
    assert not offenders, (
        f"{path.name} declares column(s) whose bare name is a reserved keyword in "
        f"CockroachDB: {offenders}. Quoting the DDL is not enough — every unquoted "
        f"reference still returns 42601. Rename the column."
    )


def test_the_result_table_names_the_family_column_mutation_family():
    """The rename, asserted from both sides at once.

    ``RESULT_COLUMNS`` is what ``sql.py`` interpolates into the INSERT, so this is the
    single place where the Python vocabulary and the SQL vocabulary have to agree about
    the spelling. The Python attribute is still ``MutantResult.family``; that one is a
    dataclass field and never a SQL identifier.
    """
    assert "mutation_family" in RESULT_COLUMNS
    assert "family" not in RESULT_COLUMNS
    assert "mutation_family" in _declared_columns(RESULT_SQL)
    assert " family " not in INSERT_RESULT.replace(",", " ").replace("(", " ").replace(")", " ")


def test_the_outcome_vocabulary_matches_the_check():
    body = _body(RESULT_SQL)
    for outcome in OUTCOMES:
        assert f"'{outcome}'" in body, f"outcome {outcome!r} is not in outcome_closed"


def test_the_residue_vocabulary_matches_the_check_and_has_no_sixth():
    body = _body(RESULT_SQL)
    for reason in RESIDUE_REASONS:
        assert f"'{reason}'" in body
    assert set(RESIDUE_REASONS) >= MATCHER_RESIDUE, (
        "the judge treats a residue reason as matcher-manufactured that the DDL does not "
        "recognise; one of the two has grown a sixth value"
    )


def test_the_rule_id_vocabulary_matches_the_check():
    body = _body(RESULT_SQL)
    for rule_id in RULE_IDS:
        assert f"'{rule_id}'" in body


def test_the_result_table_is_welded_append_only():
    body = _body(TRIGGERS[1])
    assert "BEFORE UPDATE OR DELETE ON mainline_meas.mutation_result" in body
    assert "mainline.fn_refuse_mutation()" in body, (
        "reuse the substrate's function; a vertical copy is a second place for the "
        "append-only message to drift"
    )


def test_the_run_table_is_welded_append_only():
    body = _body(TRIGGERS[0])
    assert "BEFORE UPDATE OR DELETE ON mainline_meas.mutation_run" in body
    assert "mainline.fn_refuse_mutation()" in body


def test_the_run_table_refuses_an_inconsistent_arm():
    body = _body(RUN_SQL)
    assert "arm_is_consistent" in body
    assert "arm_closed" in body
    assert "kill_interval_ordered" in body
    assert "survive_interval_ordered" in body
