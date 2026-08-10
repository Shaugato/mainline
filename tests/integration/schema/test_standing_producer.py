# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The producer contract for ``mainline_meas.person_measure_policy`` and ``…standing``.

Migrations under test: ``0089a_person_measure_policy``, ``0089b_standing``,
``0149b_trg_person_measure_policy_append_only``.

**The gap these three files close was invisible to a census, and that is the finding worth
keeping.** Seven relations in this tree had consumers and no producer. Six of them announced
themselves in a SQLSTATE the moment the chain reached their consumer. The seventh —
``mainline_meas.person_measure_policy`` — never did, because CockroachDB reports only the
**first** absent relation in a statement, and ``mainline_meas.standing`` is named first in both
``0171_v_standing_components`` and ``0172_v_my_record``. A census that counted SQLSTATEs could
not have seen it. It was found by differencing referenced relations against ``CREATE TABLE``
statements, which is now ``trappoint migrate lint``'s ``producer-absent`` rule, and
:func:`test_the_producer_existence_lint_no_longer_names_this_pair` is the assertion that it
stays closed.

**What this suite claims, and in what order.**

1. The three files apply, and the eight consumers that were blocked behind them apply too —
   ``0171``, ``0172``, ``0187`` and ``0187a`` through ``0187e``.
2. The two tables have exactly the columns their consumers select. Applying is necessary;
   *selecting from the view* is the test. A table that applies and does not satisfy its
   consumers is the failure mode this wave was written to avoid.
3. SEC-3's four conditions are database behaviour and not prose:
   - condition (2), the pre-dating, refuses ``23514`` on ``within_policy``,
     ``notice_precedes_effect`` and ``instrument_precedes_effect``, and the authorising
     instrument is welded append-only (``P0001``) so the dates cannot be revised afterwards;
   - condition (3), the arithmetic, is ``components`` and the ``encode(…, 'hex')`` digests,
     which is why both digest columns carry a 32-byte constraint;
   - condition (4), the subject's own access, is ``mainline_qa.v_my_record`` — and the same
     person, on the same connection, sees **zero** rows in ``mainline_meas.standing`` through
     ``standing_blind``.
4. The projection is honest about what it does not buy.
   :func:`test_a_forged_projection_is_admitted_and_visible_in_the_view` asserts the
   **dangerous** behaviour deliberately: a writer holding INSERT may supply a
   ``policy_effective_from`` earlier than the instrument's real ``effective_from``, and the
   row is admitted. What ``0171`` buys is that the forgery is *visible* — the view discloses
   the instrument's own date beside the score, so the contradiction is a query. A test written
   to expect a refusal here would fail honestly today and be "repaired" tomorrow by relaxing
   it, at which point the finding is gone.

**SEC-1, before any RLS assertion below is read.** Row-level security is tenancy hygiene and
information partitioning. It is not tamper-evidence and not a defence against a privileged
operator: admin bypasses it, CDC ignores it, and ``BACKUP``/``RESTORE``/replication all bypass
it. Nothing here should be cited for a claim wider than that.

**Isolation.** This module builds its **own database** on the shared node and drops it, because
its subject is DDL and a shared database would interleave with every other schema test. The two
SQL roles it needs are cluster-global, so their names carry a per-run suffix and they are
dropped in teardown; a leaked ``w4_subject`` would collide with the next run.
"""

from __future__ import annotations

import contextlib
import os
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

psycopg = pytest.importorskip("psycopg", reason="psycopg 3 is required to talk to CockroachDB")

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

PRODUCERS = (
    "0089a_person_measure_policy",
    "0089b_standing",
    "0149b_trg_person_measure_policy_append_only",
)

#: The eight files that could not apply until the pair above existed. ``0171`` and ``0172``
#: JOIN both tables; ``0187``-``0187e`` are the RLS band ``RLS-MATRIX.yaml`` declares for
#: ``mainline_meas.standing``.
CONSUMERS = (
    "0171_v_standing_components",
    "0172_v_my_record",
    "0187_standing_rls_enable",
    "0187a_standing_rls_force",
    "0187b_policy_standing_blind",
    "0187c_policy_standing_assay_read",
    "0187d_policy_standing_assay_insert",
    "0187e_policy_standing_view_owner_read",
)

#: Verbatim from ARCHITECTURE.md §5.7 line 1543. Order is ordinal position, because the
#: consumers name columns and a reordering is not a defect — but an absence is.
POLICY_COLUMNS = (
    "policy_id",
    "measure_class",
    "instrument_sha256",
    "instrument_title",
    "approved_by_sub",
    "approved_at",
    "notice_given_at",
    "notice_sha256",
    "notice_jurisdiction",
    "adm_class_id",
    "effective_from",
    "effective_to",
)

#: Verbatim from ARCHITECTURE.md §5.7 line 1561.
STANDING_COLUMNS = (
    "actor_sub",
    "hazard_class",
    "window_from",
    "policy_id",
    "policy_effective_from",
    "s",
    "components",
    "computed_at",
)

#: What ``0171_v_standing_components`` selects from each side, checked column by column
#: before the view is ever executed, so a missing column is reported as a missing column
#: rather than as an unreadable view.
CONSUMED_BY_0171_FROM_STANDING = (
    "actor_sub",
    "hazard_class",
    "window_from",
    "s",
    "components",
    "computed_at",
    "policy_effective_from",
)
CONSUMED_BY_0171_FROM_POLICY = (
    "policy_id",
    "measure_class",
    "instrument_title",
    "instrument_sha256",
    "approved_by_sub",
    "approved_at",
    "notice_given_at",
    "notice_jurisdiction",
    "adm_class_id",
    "effective_from",
    "effective_to",
)
#: ``0172_v_my_record`` selects everything ``0171`` does from the policy side, and
#: ``notice_sha256`` besides — the subject gets the notice digest, the QA function does not.
CONSUMED_BY_0172_FROM_POLICY = (*CONSUMED_BY_0171_FROM_POLICY, "notice_sha256")

_KEY = re.compile(r"^(\d{4})([a-z]?)_")
_DIGEST_A = b"\x11" * 32
_DIGEST_B = b"\x22" * 32
_DIGEST_C = b"\x33" * 32
_DIGEST_D = b"\x44" * 32


def _apply_order(path: Path) -> tuple[int, str, str]:
    """Sort by the ``NNNN[a-z]_`` allocation key, which is what the runner orders on.

    This is why ``0089a`` may reference nothing and ``0089b`` may reference ``0089a``: there
    is no key between them, so no later file can be inserted between the policy and the
    foreign key that points at it.
    """
    match = _KEY.match(path.name)
    assert match is not None, f"{path.name} does not carry an allocation key (MR-5)"
    return (int(match.group(1)), match.group(2), path.name)


# ══════════════════════════════════════════════════════════════════════════════════════════
# The database this module builds for itself
# ══════════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Tree:
    """One applied migration tree, and the census of what happened to it."""

    dsn: str
    database: str
    applied: frozenset[str]
    failures: tuple[tuple[str, str, str], ...]

    def why(self, version: str) -> str:
        """Why *version* is not in :attr:`applied` — its SQLSTATE, or that it never ran."""
        for name, sqlstate, message in self.failures:
            if name == version:
                return f"[{sqlstate}] {message}"
        return "not attempted"


def _admin_dsn() -> str:
    for name in ("TRAPPOINT_DSN", "LOCAL_DSN"):
        value = os.environ.get(name)
        if value:
            return value
    pytest.skip(
        "no cluster: set TRAPPOINT_DSN (or LOCAL_DSN). For a local single-node node — "
        "`docker compose up -d crdb` then "
        "TRAPPOINT_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
    )


def _with_database(dsn: str, database: str) -> str:
    head, _, tail = dsn.partition("?")
    base = head.rsplit("/", 1)[0]
    return f"{base}/{database}" + (f"?{tail}" if tail else "")


def _sqlstate(exc: Exception) -> str:
    diag = getattr(exc, "diag", None)
    return (getattr(diag, "sqlstate", None) or "?????") if diag is not None else "?????"


def _refusal(conn: Any, statement: str, params: tuple[Any, ...] = ()) -> tuple[str, str]:
    """Run *statement* and return ``(sqlstate, message)``; ``00000`` when it was admitted.

    Autocommit is what makes this usable more than once per connection: a refusal inside a
    shared transaction poisons every following statement with ``25P02``, which is a different
    refusal from the one under test and would quietly replace it.
    """
    try:
        conn.execute(statement, params)
    except psycopg.Error as exc:
        return _sqlstate(exc), " ".join(str(exc).split())
    return "00000", "admitted"


@pytest.fixture(scope="module")
def tree() -> Iterator[Tree]:
    """A private database with the whole tree applied, continuing past failures.

    Continue-on-error, and the distinction matters: this suite's claim is *"these eight
    consumers apply"*, not *"the chain is green"*. The chain's forward-only run is W6's
    artefact and is a different, stronger claim over a different set of files. Applying with
    continue-on-error is what lets this module report on its own eight while another lane's
    unproduced relation is still outstanding — and :attr:`Tree.failures` keeps every one of
    those visible rather than swallowing them.
    """
    admin = _admin_dsn()
    database = f"w4_standing_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {database}")
    dsn = _with_database(admin, database)

    applied: set[str] = set()
    failures: list[tuple[str, str, str]] = []
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            for path in sorted(MIGRATIONS.glob("*.sql"), key=_apply_order):
                version = path.name[: -len(".sql")]
                try:
                    conn.execute(path.read_text(encoding="utf-8"))
                except psycopg.Error as exc:
                    failures.append((version, _sqlstate(exc), " ".join(str(exc).split())[:200]))
                else:
                    applied.add(version)
        yield Tree(
            dsn=dsn,
            database=database,
            applied=frozenset(applied),
            failures=tuple(failures),
        )
    finally:
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


@dataclass(frozen=True, slots=True)
class World:
    """The seeded state every behavioural assertion below reads.

    Three instruments and three scores, chosen so that each derived boolean in
    ``v_standing_components`` is observed in **both** truth values somewhere in this module.
    A boolean that is only ever True is a boolean nobody has evidence computes.
    """

    tree: Tree
    subject: str
    assay: str
    closed_policy: uuid.UUID
    open_policy: uuid.UUID
    late_policy: uuid.UUID
    adm_class: str


_INSERT_POLICY = """
INSERT INTO mainline_meas.person_measure_policy
    (policy_id, measure_class, instrument_sha256, instrument_title, approved_by_sub,
     approved_at, notice_given_at, notice_sha256, notice_jurisdiction, adm_class_id,
     effective_from, effective_to)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_INSERT_STANDING = """
INSERT INTO mainline_meas.standing
    (actor_sub, hazard_class, window_from, policy_id, policy_effective_from, s, components)
VALUES (%s, %s, %s, %s, %s, %s, %s)
"""


@pytest.fixture(scope="module")
def world(tree: Tree) -> Iterator[World]:
    """Seed one closed instrument, one open one, one late one, and three scores."""
    for version in (*PRODUCERS, *CONSUMERS):
        if version not in tree.applied:
            pytest.fail(
                f"{version} did not apply, so no behaviour below can be asserted: "
                f"{tree.why(version)}"
            )

    suffix = uuid.uuid4().hex[:8]
    subject = f"w4_subject_{suffix}"
    assay = f"w4_assay_{suffix}"
    adm_class = f"w4_standing_quorum_{suffix}"
    closed, open_, late = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    try:
        with psycopg.connect(tree.dsn, autocommit=True) as conn:
            # The APP 1.7 register entry `adm_class_id` points at. The real six rows are a
            # seed (db/seeds/00-lattice/adm_decision_class.sql) and seeds are not part of the
            # migration tree, so this module supplies its own rather than depending on a
            # provisioning step it does not run.
            conn.execute(
                "INSERT INTO mainline.adm_decision_class (class_id, description, "
                " personal_info_used, effect_on_individual, disclosure_text) "
                "VALUES (%s, 'W4 probe register entry', ARRAY['role title'], "
                " 'Quorum for a signed weakening', 'Probe disclosure text.')",
                (adm_class,),
            )
            conn.execute(
                _INSERT_POLICY,
                (
                    closed,
                    "standing",
                    _DIGEST_A,
                    "Ashgrove WHS QA Policy v3",
                    "officer_hse",
                    "2026-01-15T00:00:00Z",
                    "2025-12-20T00:00:00Z",
                    _DIGEST_B,
                    "AU-NSW",
                    adm_class,
                    "2026-02-01T00:00:00Z",
                    "2026-08-01T00:00:00Z",
                ),
            )
            conn.execute(
                _INSERT_POLICY,
                (
                    open_,
                    "peer_prediction",
                    _DIGEST_C,
                    "Open Instrument",
                    "officer_hse",
                    "2026-01-15T00:00:00Z",
                    "2025-12-20T00:00:00Z",
                    _DIGEST_D,
                    "AU-QLD",
                    None,
                    "2026-02-01T00:00:00Z",
                    None,
                ),
            )
            # The instrument the forged score cites: signed and effective LATER than the
            # window the score claims to cover.
            conn.execute(
                _INSERT_POLICY,
                (
                    late,
                    "standing",
                    _DIGEST_A,
                    "Late Instrument",
                    "officer_hse",
                    "2026-06-01T00:00:00Z",
                    "2026-05-01T00:00:00Z",
                    _DIGEST_B,
                    "AU-WA",
                    None,
                    "2026-07-01T00:00:00Z",
                    None,
                ),
            )
            conn.execute(
                _INSERT_STANDING,
                (
                    subject,
                    "isolation",
                    "2026-03-01T00:00:00Z",
                    closed,
                    "2026-02-01T00:00:00Z",
                    1.0,
                    '{"W": 1.0, "n": 3}',
                ),
            )
            conn.execute(
                _INSERT_STANDING,
                (
                    subject,
                    "ventilation",
                    "2026-04-01T00:00:00Z",
                    open_,
                    "2026-02-01T00:00:00Z",
                    1.0,
                    '{"W": 1.0}',
                ),
            )
            # The forgery: `policy_effective_from` projected two quarters before the
            # instrument's real `effective_from`. See the test that reads it.
            conn.execute(
                _INSERT_STANDING,
                (
                    "w4_forged_actor",
                    "dust",
                    "2026-03-01T00:00:00Z",
                    late,
                    "2026-01-01T00:00:00Z",
                    1.0,
                    '{"W": 1.0}',
                ),
            )

            # SQL roles are cluster-global; the per-run suffix is what keeps two runs, or two
            # workers on the shared node, from colliding.
            conn.execute(f"CREATE USER {subject}")
            conn.execute(f"CREATE USER {assay}")
            conn.execute(f"GRANT signer TO {subject}")
            conn.execute(f"GRANT agent_assay TO {assay}")
            conn.execute("GRANT USAGE ON SCHEMA mainline, mainline_meas, mainline_qa TO signer")
            conn.execute("GRANT USAGE ON SCHEMA mainline_meas TO agent_assay")
            # Deliberately MORE privilege than GRANTS.yaml issues: `signer` holds no SELECT
            # on this table in the deployment. Granting it here is what makes the next
            # assertion mean something — `standing_blind` is RESTRICTIVE `USING (false)`, so
            # the intended set is empty even for a reader who holds the privilege. Testing
            # blindness against a role with no grant would only test the missing grant.
            conn.execute("GRANT SELECT ON TABLE mainline_meas.standing TO signer")
            conn.execute("GRANT SELECT ON TABLE mainline_meas.standing TO agent_assay")
            conn.execute("GRANT SELECT ON mainline_qa.v_my_record TO signer")
        yield World(
            tree=tree,
            subject=subject,
            assay=assay,
            closed_policy=closed,
            open_policy=open_,
            late_policy=late,
            adm_class=adm_class,
        )
    finally:
        # Role membership and table privileges both have to go before the user can, and
        # both live in the tree's database, which is still standing at this point — the
        # `tree` fixture tears down after this one.
        with psycopg.connect(tree.dsn, autocommit=True) as conn:
            for role, granted in ((subject, "signer"), (assay, "agent_assay")):
                for statement in (
                    f"REVOKE {granted} FROM {role}",
                    f"DROP USER IF EXISTS {role}",
                ):
                    with contextlib.suppress(psycopg.Error):
                        conn.execute(statement)


@pytest.fixture
def conn(tree: Tree) -> Iterator[Any]:
    """An autocommit connection as the migrating identity."""
    with psycopg.connect(tree.dsn, autocommit=True) as connection:
        yield connection


def _connect_as(tree: Tree, user: str) -> Any:
    """Reconnect to the same database as *user*.

    Only the userinfo changes; the host, port, database and parameters are the tree's own, so
    a run against a different node needs no second environment variable.
    """
    scheme, _, rest = tree.dsn.partition("://")
    _, _, hostpart = rest.rpartition("@")
    return psycopg.connect(f"{scheme}://{user}@{hostpart or rest}", autocommit=True)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 1 · The files apply, and so do the eight that were blocked behind them
# ══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.slow
@pytest.mark.parametrize("version", PRODUCERS)
def test_the_producer_pair_and_its_weld_apply(tree: Tree, version: str) -> None:
    """0089a, 0089b and 0149b apply against a real cluster."""
    assert version in tree.applied, f"{version} did not apply: {tree.why(version)}"


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.parametrize("version", CONSUMERS)
def test_the_eight_blocked_consumers_apply(tree: Tree, version: str) -> None:
    """The point of the wave: eight files that refused ``42P01`` now apply.

    ``0171`` and ``0172`` refused on ``mainline_meas.standing`` — never on
    ``person_measure_policy``, because CockroachDB names the first absent relation and
    ``standing`` is named first in both. The policy table was the shadowed gap.
    """
    assert version in tree.applied, f"{version} did not apply: {tree.why(version)}"


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
def test_no_remaining_failure_in_the_tree_names_either_of_these_relations(tree: Tree) -> None:
    """Other lanes' unproduced relations may still fail; ours may not.

    This is the assertion that keeps the module honest while the wave is in flight. It does
    not require a green tree — that is W6's claim over W6's files — it requires that no
    residual failure anywhere in the tree is attributable to the two relations this worker
    owns.
    """
    ours = [
        (version, sqlstate, message)
        for version, sqlstate, message in tree.failures
        if "person_measure_policy" in message or "mainline_meas.standing" in message
    ]
    assert ours == [], "a migration still fails on a relation this worker produces: " + "; ".join(
        f"{v} [{s}] {m}" for v, s, m in ours
    )


@pytest.mark.shape
def test_the_producer_existence_lint_no_longer_names_this_pair() -> None:
    """``trappoint migrate lint``'s ``producer-absent`` rule is silent about both tables.

    Hermetic — no cluster. The rule is the thing that stops the eighth instance of this
    defect class, and a rule that has been satisfied by accident is a rule nobody can rely
    on, so the satisfaction is asserted rather than assumed.
    """
    lint = pytest.importorskip("trappoint_migrate.lint", reason="trappoint-migrate is required")
    report = lint.lint_paths([MIGRATIONS])
    named = [
        finding.render()
        for finding in report.findings
        if "person_measure_policy" in finding.detail or "mainline_meas.standing" in finding.detail
    ]
    assert named == [], "the producer-existence rule still names this pair: " + "; ".join(named)


@pytest.mark.shape
@pytest.mark.parametrize("version", PRODUCERS)
def test_the_three_files_carry_a_clean_header_and_no_banned_token(version: str) -> None:
    """Rules A, B, C, the sequence ban, the citation rule and the header block.

    Scoped to the three files this worker owns: a whole-tree assertion here would make this
    module red for another lane's file, and changing another lane's colour is that lane
    owner's decision.
    """
    lint = pytest.importorskip("trappoint_migrate.lint")
    header = pytest.importorskip("trappoint_migrate.header")
    path = MIGRATIONS / f"{version}.sql"
    catalogue = header.find_catalogue(MIGRATIONS)
    known = header.catalogue_ids(catalogue) if catalogue is not None else None
    findings = tuple(lint.lint_paths([path]).findings) + tuple(
        header.header_findings(path, path.read_text(encoding="utf-8"), known_mi_ids=known or None)
    )
    assert findings == (), "\n".join(f.render() for f in findings)


# ══════════════════════════════════════════════════════════════════════════════════════════
# 2 · The shape is the one the consumers select, column by column
# ══════════════════════════════════════════════════════════════════════════════════════════


def _columns(conn: Any, schema: str, table: str) -> dict[str, tuple[str, str]]:
    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    ).fetchall()
    return {name: (kind, nullable) for name, kind, nullable in rows}


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
def test_both_tables_carry_exactly_the_columns_5_7_specifies(conn: Any) -> None:
    """§5.7 verbatim: no column missing, and no column invented.

    Both halves are assertions. A missing column breaks a consumer; an *extra* column in a
    table this small is a shape somebody guessed, and a guessed column is one a test passes
    against and a deployment does not.
    """
    policy = _columns(conn, "mainline_meas", "person_measure_policy")
    standing = _columns(conn, "mainline_meas", "standing")
    assert set(policy) == set(POLICY_COLUMNS), (
        f"person_measure_policy is {sorted(policy)}, §5.7 says {sorted(POLICY_COLUMNS)}"
    )
    assert set(standing) == set(STANDING_COLUMNS), (
        f"standing is {sorted(standing)}, §5.7 says {sorted(STANDING_COLUMNS)}"
    )
    assert policy["adm_class_id"][1] == "YES", (
        "adm_class_id must stay nullable: `calibration` measures the system, not a person, "
        "and NOT NULL would force an inapplicable APP 1.7 register entry to be invented"
    )
    assert policy["effective_to"][1] == "YES", "an open-ended policy window is a real state"
    for column in ("policy_id", "policy_effective_from", "s", "components"):
        assert standing[column][1] == "NO", (
            f"standing.{column} is nullable; every one of these is what makes SEC-3's "
            "conditions structural rather than advisory"
        )


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.parametrize(
    ("table", "consumed"),
    [
        ("standing", CONSUMED_BY_0171_FROM_STANDING),
        ("person_measure_policy", CONSUMED_BY_0172_FROM_POLICY),
    ],
)
def test_every_column_the_two_views_select_exists(
    conn: Any, table: str, consumed: tuple[str, ...]
) -> None:
    """Column by column, before the view is executed.

    ``0171`` selects seven columns from ``standing`` and eleven from the policy; ``0172``
    selects the same eleven plus ``notice_sha256``, because the subject gets the notice
    digest and the QA function does not. Reported here as *missing columns* rather than
    discovered later as an unreadable view.
    """
    present = set(_columns(conn, "mainline_meas", table))
    missing = [column for column in consumed if column not in present]
    assert missing == [], f"mainline_meas.{table} is missing {missing}, which a view selects"


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
def test_the_constraints_are_named_because_the_name_is_the_exhibit(conn: Any) -> None:
    """A refusal exhibit is a constraint name, and a generated name is not a contract."""
    names = {
        row[0]
        for row in conn.execute(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_schema = 'mainline_meas' "
            "AND table_name IN ('person_measure_policy', 'standing')"
        ).fetchall()
    }
    for expected in (
        "person_measure_policy_pk",
        "instrument_sha256_is_a_digest",
        "notice_sha256_is_a_digest",
        "notice_precedes_effect",
        "instrument_precedes_effect",
        "fk_adm_class",
        "standing_pk",
        "within_policy",
        "fk_policy",
    ):
        assert expected in names, f"constraint {expected!r} is absent; found {sorted(names)}"


# ══════════════════════════════════════════════════════════════════════════════════════════
# 3 · SEC-3 condition (2): the instrument predates the data, and cannot be back-dated
# ══════════════════════════════════════════════════════════════════════════════════════════


def _policy_values(**overrides: Any) -> tuple[Any, ...]:
    row: dict[str, Any] = {
        "policy_id": uuid.uuid4(),
        "measure_class": "standing",
        "instrument_sha256": _DIGEST_A,
        "instrument_title": "Probe Instrument",
        "approved_by_sub": "officer_hse",
        "approved_at": "2026-01-15T00:00:00Z",
        "notice_given_at": "2025-12-20T00:00:00Z",
        "notice_sha256": _DIGEST_B,
        "notice_jurisdiction": "AU-NSW",
        "adm_class_id": None,
        "effective_from": "2026-02-01T00:00:00Z",
        "effective_to": None,
    }
    row.update(overrides)
    return tuple(row[key] for key in POLICY_COLUMNS)


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
@pytest.mark.parametrize(
    ("label", "overrides", "constraint"),
    [
        (
            "notice given after the policy takes effect",
            {"notice_given_at": "2026-03-01T00:00:00Z"},
            "notice_given_at <= effective_from",
        ),
        (
            "instrument approved after the policy takes effect",
            {"approved_at": "2026-03-01T00:00:00Z"},
            "approved_at <= effective_from",
        ),
    ],
)
@pytest.mark.usefixtures("world")
def test_an_instrument_that_does_not_predate_its_effect_is_refused(
    conn: Any, label: str, overrides: dict[str, Any], constraint: str
) -> None:
    """23514. SEC-3 condition (2) is a CHECK, not a paragraph.

    Workplace-surveillance notice is a *precondition*, so notice dated after the measurement
    started is not a late notice; it is no notice. Same for the officer's approval.
    """
    sqlstate, message = _refusal(conn, _INSERT_POLICY, _policy_values(**overrides))
    assert sqlstate == "23514", f"{label}: expected 23514, got {sqlstate} — {message}"
    assert constraint in message, f"{label}: the refusal does not name {constraint!r}: {message}"


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.parametrize("column", ["instrument_sha256", "notice_sha256"])
@pytest.mark.usefixtures("world")
def test_a_truncated_digest_is_refused(conn: Any, column: str) -> None:
    """23514. Both digests are disclosed as hex, so a short one reads as a digest.

    ``0171`` returns ``encode(instrument_sha256, 'hex')`` and ``0172`` returns both. ``encode``
    renders four bytes as eight characters without complaint, and a digest disclosed to the
    scored person that verifies against nothing is worse than no digest.
    """
    sqlstate, message = _refusal(conn, _INSERT_POLICY, _policy_values(**{column: b"\x11" * 4}))
    assert sqlstate == "23514", f"expected 23514 for a short {column}, got {sqlstate}"
    assert f"length({column})" in message, message


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.usefixtures("world")
def test_the_measure_class_vocabulary_is_closed(conn: Any) -> None:
    """23514. Five classes, and a pejorative sixth is not writable.

    I15 requires neutral names; an open vocabulary is how ``diligence`` gets written once and
    then forever.
    """
    sqlstate, message = _refusal(conn, _INSERT_POLICY, _policy_values(measure_class="diligence"))
    assert sqlstate == "23514", f"expected 23514 for an unlisted measure_class, got {sqlstate}"
    assert "measure_class" in message, message


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI01")
@pytest.mark.parametrize(
    ("verb", "statement"),
    [
        (
            "UPDATE",
            (
                "UPDATE mainline_meas.person_measure_policy "
                "SET approved_at = '2020-01-01T00:00:00Z' WHERE policy_id = %s"
            ),
        ),
        ("DELETE", "DELETE FROM mainline_meas.person_measure_policy WHERE policy_id = %s"),
    ],
)
def test_the_authorising_instrument_is_append_only(
    conn: Any, world: World, verb: str, statement: str
) -> None:
    """P0001 — and this is the assertion the whole legal argument rests on.

    ``instrument_precedes_effect`` constrains a *row*, and an UPDATE produces a different row
    that also satisfies it. Without 0149b, conditions (2) and (3) are unfalsifiable: every
    policy is correctly ordered at the moment you look at it, and no reader can distinguish
    one ordered when written from one reordered afterwards.
    """
    sqlstate, message = _refusal(conn, statement, (world.closed_policy,))
    assert sqlstate == "P0001", f"{verb} was not refused P0001, got {sqlstate} — {message}"
    assert "append-only" in message, message


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.usefixtures("world")
def test_standing_carries_no_trigger_because_its_matrix_already_declares_its_writes(
    conn: Any,
) -> None:
    """The negative assertion, deliberately.

    ``RLS-MATRIX.yaml`` declares ``mainline_meas.standing`` FORCE with exactly one write
    policy — ``standing_assay_insert``, PERMISSIVE FOR INSERT TO agent_assay — and no UPDATE
    or DELETE policy, which under FORCE is the control and not an omission. A second,
    undeclared control on a table whose matrix is committed is how a matrix stops describing
    the database.
    """
    triggers = conn.execute(
        "SELECT trigger_name FROM information_schema.triggers "
        "WHERE event_object_schema = 'mainline_meas' AND event_object_table = 'standing'"
    ).fetchall()
    assert triggers == [], f"standing carries undeclared trigger(s): {triggers}"
    policy_triggers = {
        row[0]
        for row in conn.execute(
            "SELECT trigger_name FROM information_schema.triggers "
            "WHERE event_object_schema = 'mainline_meas' "
            "AND event_object_table = 'person_measure_policy'"
        ).fetchall()
    }
    assert policy_triggers == {"append_only"}, (
        f"person_measure_policy's trigger set is {policy_triggers}, expected {{'append_only'}}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 4 · The two references: the APP 1.7 register, and the instrument itself
# ══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI01")
def test_an_unregistered_adm_class_is_refused_and_a_registered_one_is_admitted(
    conn: Any, world: World
) -> None:
    """23503, then 00000. Both halves, because a reference that refuses everything is broken.

    ``mainline.adm_decision_class`` (0020) is the APP 1.7 automated-decision register, and both
    views disclose ``adm_class_id`` — to the QA function and to the scored person. An
    unregistered string there discloses a decision class the register does not contain. The FK
    is expressible because the key types match: ``class_id STRING NOT NULL PRIMARY KEY``.
    """
    sqlstate, message = _refusal(
        conn, _INSERT_POLICY, _policy_values(adm_class_id="no_such_decision_class")
    )
    assert sqlstate == "23503", f"expected 23503, got {sqlstate} — {message}"
    assert "fk_adm_class" in message, message

    admitted, detail = _refusal(conn, _INSERT_POLICY, _policy_values(adm_class_id=world.adm_class))
    assert admitted == "00000", (
        f"a REGISTERED decision class was refused {admitted}: {detail}. A foreign key that "
        "refuses every value is not a control, it is an outage."
    )
    null_ok, detail = _refusal(conn, _INSERT_POLICY, _policy_values(adm_class_id=None))
    assert null_ok == "00000", (
        f"a NULL adm_class_id was refused {null_ok}: {detail}. MATCH SIMPLE admits the NULL, "
        "and `calibration` measures the system rather than a person"
    )


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
@pytest.mark.usefixtures("world")
def test_a_score_citing_an_unknown_instrument_is_refused(conn: Any) -> None:
    """23503 on ``fk_policy``. There is no such thing as an unauthorised standing score."""
    sqlstate, message = _refusal(
        conn,
        _INSERT_STANDING,
        (
            "w4_unauthorised",
            "isolation",
            "2026-03-01T00:00:00Z",
            uuid.uuid4(),
            "2026-02-01T00:00:00Z",
            1.0,
            '{"W": 1.0}',
        ),
    )
    assert sqlstate == "23503", f"expected 23503, got {sqlstate} — {message}"
    assert "fk_policy" in message, message


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
def test_within_policy_refuses_a_window_that_opens_before_the_policy(
    conn: Any, world: World
) -> None:
    """23514 naming ``within_policy`` — I15's OBSERVABLE row for this invariant.

    A score computed about a person, used against them, and derived from a policy that did
    not exist when the data was made is an allegation. Not insertable.

    Naming note for whoever owns the conformance corpus:
    ``spec/invariants/I15-allegation-firewall.md`` and ``spec/conformance/manifest.toml``
    (CF-68) both name this exhibit ``measure_policy_predates_data``, while ARCHITECTURE.md
    §5.7 names the constraint ``within_policy`` and three migrations (0171, 0187d, 0089b)
    cite that name. This test asserts the name the schema actually carries; the divergence is
    reported, not silently reconciled.
    """
    sqlstate, message = _refusal(
        conn,
        _INSERT_STANDING,
        (
            f"{world.subject}_early",
            "isolation",
            "2026-01-05T00:00:00Z",
            world.closed_policy,
            "2026-02-01T00:00:00Z",
            1.0,
            '{"W": 1.0}',
        ),
    )
    assert sqlstate == "23514", f"expected 23514, got {sqlstate} — {message}"
    assert "window_from >= policy_effective_from" in message, message


# ══════════════════════════════════════════════════════════════════════════════════════════
# 5 · SEC-3 condition (3): the arithmetic, through mainline_qa.v_standing_components
# ══════════════════════════════════════════════════════════════════════════════════════════


_VIEW_COLUMNS = (
    "actor_sub, hazard_class, window_from, s, components_head, components_truncated, "
    "measure_class, instrument_title, instrument_sha256_hex, approved_by_sub, approved_at, "
    "notice_given_at, notice_jurisdiction, adm_class_id, policy_effective_from, "
    "policy_effective_to, scored_within_policy, notice_preceded_effect, policy_window_closed, "
    "scored_before_policy_expiry"
)


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
def test_v_standing_components_returns_the_seeded_row_with_its_derived_booleans(
    conn: Any, world: World
) -> None:
    """The test the lead named: applying is necessary, *selecting from the view* is the test.

    Two rows, one per instrument, so that ``policy_window_closed`` is observed True on the
    closed instrument and False on the open one. A boolean that is only ever True is a
    boolean nobody has evidence computes.
    """
    rows = conn.execute(
        f"SELECT {_VIEW_COLUMNS} FROM mainline_qa.v_standing_components "  # noqa: S608
        "WHERE actor_sub = %s ORDER BY hazard_class",
        (world.subject,),
    ).fetchall()
    assert len(rows) == 2, f"expected the two seeded scores, got {len(rows)}: {rows}"
    by_hazard = {row[1]: row for row in rows}

    closed = by_hazard["isolation"]
    assert closed[4] == '{"W": 1.0, "n": 3}', f"components_head is {closed[4]!r}"
    assert closed[5] is False, "an 18-character components object is not truncated at 400"
    assert closed[6] == "standing"
    assert closed[7] == "Ashgrove WHS QA Policy v3"
    assert closed[8] == _DIGEST_A.hex(), "instrument_sha256_hex is not the 64-char digest"
    assert closed[13] == world.adm_class, "the APP 1.7 register entry is not disclosed"
    assert closed[16] is True, "scored_within_policy: 2026-03-01 >= 2026-02-01"
    assert closed[17] is True, "notice_preceded_effect: 2025-12-20 <= 2026-02-01"
    assert closed[18] is True, "policy_window_closed: effective_to is 2026-08-01"
    assert closed[19] is True, "scored_before_policy_expiry: 2026-03-01 <= 2026-08-01"

    open_ = by_hazard["ventilation"]
    assert open_[13] is None, "the open instrument declares no ADM class, and NULL is a state"
    assert open_[15] is None, "policy_effective_to is NULL on an open-ended window"
    assert open_[16] is True
    assert open_[17] is True
    assert open_[18] is False, (
        "policy_window_closed must be False for an open-ended instrument. MI28: an open window "
        "is a real state and is not the same state as a closed one, so it is reported rather "
        "than coalesced."
    )
    assert open_[19] is True, "an open window has not expired"


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI28")
@pytest.mark.usefixtures("world")
def test_a_forged_projection_is_admitted_and_visible_in_the_view(
    conn: Any,
) -> None:
    """**This test asserts the DANGEROUS behaviour on purpose. Do not "fix" it.**

    ``standing.policy_effective_from`` is a projection — §5.7 says so, because a CHECK cannot
    subquery — and a writer holding INSERT can supply a value earlier than the referenced
    instrument's real ``effective_from``. The row is ADMITTED: ``within_policy`` compares the
    score's window against the *projected* column, and the forgery satisfies it.

    What ``0171`` buys is that the forgery is visible. The view discloses the INSTRUMENT's own
    ``effective_from`` under ``policy_effective_from``, so a reader sees ``scored_within_policy
    = True`` beside a window that opens four months before the instrument existed, and the
    contradiction is a query rather than a promise. That is P2 applied to a person-measure:
    do not trust the projection, re-derive it.

    A test written to expect a refusal here would fail honestly today and be repaired tomorrow
    by relaxing it, at which point the finding is gone.
    """
    row = conn.execute(
        "SELECT window_from, policy_effective_from, scored_within_policy "
        "FROM mainline_qa.v_standing_components WHERE actor_sub = 'w4_forged_actor'"
    ).fetchone()
    assert row is not None, "the forged score was not admitted; the projection is not forgeable"
    window_from, instrument_effective_from, scored_within_policy = row
    assert scored_within_policy is True, (
        "the CHECK compares against the projected column, so the forgery passes it — that is "
        "the limitation this test exists to record"
    )
    assert window_from < instrument_effective_from, (
        "the seeded forgery is not forged: the view must disclose an instrument date LATER "
        "than the window the score claims, which is the visible contradiction"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════
# 6 · SEC-3 condition (4), and the blindness that makes it necessary
# ══════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
def test_0187b_shows_a_signer_nothing_at_all_including_their_own_row(world: World) -> None:
    """``standing_blind`` is RESTRICTIVE ``USING (false)``: the intended set is empty.

    Not "your own row only" — nothing. M10's peer-prediction channel is defeated by a
    participant who can see the scoring. The role under test holds SELECT on the table (the
    fixture grants more than GRANTS.yaml issues, deliberately), so this is the policy working
    and not a missing privilege.

    ``agent_assay`` is asserted in the same test because a policy that blinds everybody is not
    a partition, it is an outage.
    """
    with _connect_as(world.tree, world.subject) as signer:
        seen = signer.execute("SELECT count(*) FROM mainline_meas.standing").fetchone()
    assert seen == (0,), (
        f"a signer saw {seen} standing rows through the base table; standing_blind is "
        "RESTRICTIVE USING (false)"
    )
    with _connect_as(world.tree, world.assay) as assay:
        computed = assay.execute("SELECT count(*) FROM mainline_meas.standing").fetchone()
    assert computed is not None and computed[0] >= 3, (
        f"agent_assay saw {computed} rows; the role that computes the measure must be able to "
        "read back the window it is extending (0187c)"
    )


@pytest.mark.schema
@pytest.mark.integration
@pytest.mark.requires_cluster
@pytest.mark.mi("MI27")
def test_the_subject_reads_their_own_record_and_only_their_own(world: World) -> None:
    """SEC-3 condition (4), on the same connection that just saw nothing.

    This is the pairing that makes the design defensible rather than merely restrictive: the
    identical SQL identity is blind to ``mainline_meas.standing`` and sighted on
    ``mainline_qa.v_my_record``, where it gets its own score, the full untruncated arithmetic,
    both digests as hex and the authorising instrument's dates — and nobody else's row.

    ``current_user`` in the view body is the invoker, measured on CockroachDB v26.2.5, which
    is what makes the scope work at all: RLS policies cannot be defined on views, and the base
    table's policies would evaluate as the view's owner.
    """
    with _connect_as(world.tree, world.subject) as subject:
        rows = subject.execute(
            "SELECT actor_sub, hazard_class, score, components, "
            " authorising_policy_title, authorising_policy_sha256_hex, notice_sha256_hex, "
            " notice_jurisdiction, adm_class_id, policy_effective_from, policy_effective_to, "
            " scored_within_policy, notice_preceded_effect "
            "FROM mainline_qa.v_my_record ORDER BY hazard_class"
        ).fetchall()
    assert len(rows) == 2, f"the subject sees {len(rows)} of their own rows, expected 2: {rows}"
    assert {row[0] for row in rows} == {world.subject}, (
        "v_my_record returned a row belonging to somebody else; the scope is "
        "`WHERE st.actor_sub = current_user`"
    )
    isolation = next(row for row in rows if row[1] == "isolation")
    assert isolation[3] == {"W": 1.0, "n": 3}, (
        "the subject gets the arithmetic IN FULL and untruncated — condition (3) is "
        "recomputability and condition (4) is their own access; a truncated derivation "
        "satisfies neither"
    )
    assert isolation[5] == _DIGEST_A.hex(), "the instrument digest is not disclosed as hex"
    assert isolation[6] == _DIGEST_B.hex(), (
        "the NOTICE digest is not disclosed. 0172 discloses it and 0171 does not: the person "
        "under surveillance is entitled to check the notice they were given"
    )
    assert isolation[11] is True and isolation[12] is True
