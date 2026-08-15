# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""LEG B — the privilege probe, asked of a database this file builds from the tree.

WHY THIS FILE EXISTS
====================
``verticals/mainline/db/GRANTS.yaml`` says, in its own header, that it is not the control::

    A GRANT is a claim about intent. A 42501 is evidence about behaviour.

and migration ``0009e_default_privileges_floor.sql`` — the marker that stands at the point
in the numbered sequence where a reader goes looking for ``GRANT`` statements and does not
find them — closes with the same sentence::

    The control was never the GRANT. It is the privilege probe that asserts 42501 for every
    (role, object) pair the matrix does NOT name.

Leg A (``verticals/mainline/apps/demo-api/tests/test_privilege_census.py``) compares two
documents: what the shipping demo-api source references against what the matrix declares.
It is fast, hermetic, and it would have gone red before the first deploy. It is still two
texts being diffed. **This file connects AS the login and asks the cluster.**

The subject is ``mainline_api`` — the role the Lambda behind a Function URL with
``authorization_type = NONE`` connects as, which makes it, precisely, what an anonymous
caller on the internet executes as.

BOTH DIRECTIONS, AND WHY NEITHER IS SUFFICIENT ALONE
====================================================
* every ``(object, verb)`` the matrix grants the role must **not** be refused with
  ``42501``;
* a deterministic, stratified sample of the pairs it does **not** grant must be refused
  with exactly ``42501``.

A login that can read nothing passes every negative test perfectly. That trap is named in
``cloud_roles.probe``'s docstring and it is the reason the positive direction is asserted
here at all — and the reason :func:`test_the_probe_discriminates` exists, which runs the
*same statements* as a *different role* and requires the answers to differ. A control that
has never discriminated has never controlled anything.

WHAT IS DERIVED AND WHAT IS TYPED OUT
=====================================
Nothing here restates a list. The roles, the memberships, the grants and the schemas come
from ``GRANTS.yaml`` through :mod:`trappoint_migrate.grants` — the runner that applies it,
so the matrix and the probe can disagree about privileges but cannot disagree about what
the file says. The relations come from ``information_schema`` on the database this file
builds. ``test_seed_covers_every_console_resource.py`` states the discipline: *a second
copy of a list is a second thing to drift.*

THE ONE SKIP, AND THE LANE THAT MUST MAKE IT IMPOSSIBLE
=======================================================
The only skip in this file is "there is no cluster", and it says so. **That skip must not
be allowed to become the normal outcome**: a green that means "I did not run" is the exact
failure this wave exists to end. `scripts/qa/skip_ratchet.py`'s first rule — *"adding a
cluster-backed test that no lane runs fails the build"* — is what makes that structural,
and W5 owns the wiring: this file belongs in ``.github/workflows/cluster-tests.yml``,
which already provisions a node, and it must be a required lane with no
``continue-on-error`` and no ``|| true``.

COST
====
The session fixture builds a database, applies all 271 migrations through
``trappoint migrate up --attest final``, applies the matrix and creates the login. Measured
on the development workstation on 2026-08-15, against a shared local node already holding
~140 other worker databases: **7m01s** for the chain. Every assertion afterwards is a
handful of zero-row statements and costs milliseconds.

The repository-wide ``timeout = 120`` **does** cover that setup, measured here on
2026-08-15: the first run of this file was killed mid-chain by ``pytest-timeout``'s thread
method, which dumped stacks and exited. (``conftest.py`` records that the thread method
cannot *interrupt* a hang inside session-scoped fixture setup; it can still end the session,
and it did.) Hence :data:`CHAIN_BUDGET_SECONDS` below, applied module-wide the way
``test_ops_producer.py`` applies its own. **W5's lane must budget for one chain build**, and
a job whose whole wall-clock allowance is twelve minutes cannot also run this leg — Leg B
belongs in ``cluster-tests.yml`` beside the other suites that pay for a migrated database.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(REPO_ROOT))

from scripts.qa.privilege_conformance import (  # noqa: E402 - after the sys.path bootstrap
    DEFAULT_MATRIX,
    DEFAULT_MIGRATIONS,
    DEFAULT_ROLE,
    DENY,
    OK,
    PROBE_VERBS,
    Check,
    Outcome,
    Pair,
    Relation,
    Report,
    Target,
    World,
    as_role,
    ensure_login,
    matrix_reach,
    matrix_schemas,
    probe_world,
    relations_in,
    run_probe,
    safe,
    statement_for,
    world,
)

#: The four spellings the testkit publishes a session cluster under (`plugin.export_dsn`),
#: then the two an operator exports by hand. Read in this order and never invented.
_DSN_ENV_NAMES = (
    "TRAPPOINT_DSN",
    "MAINLINE_TEST_DSN",
    "COCKROACH_URL",
    "CRDB_URL",
    "LOCAL_DSN",
)

#: EVERY ungranted pair, not a sample. ``0`` is :func:`privilege_conformance.checks_for`'s
#: "no cap", and it is what migration ``0009e`` and ``GRANTS.yaml``'s header both ask for in
#: those words: *42501 for every (role, object) pair the matrix does NOT name*. Measured on
#: this schema, 2026-08-15: the complement is ~300 pairs and each is a plan-time refusal, so
#: the whole negative direction costs seconds. A control that can afford to be exhaustive
#: and samples instead is choosing to be weaker for nothing.
NEGATIVE_SAMPLE = 0

#: `spec/errors.md` §3.1. The exhibit a 42501 carries, so a refusal found here is legible
#: beside every other refusal in the conformance corpus.
_GRANT_TOKEN = re.compile(r"^grant:[A-Z]+:[a-z_]+\.[a-z_0-9]+:[a-z_]+$")

#: The session fixture builds a database and drives all 271 migrations through
#: `trappoint migrate up`. Measured 2026-08-15 on the development workstation, against a
#: shared local node already holding ~140 other worker databases: **7m01s**. The
#: repository-wide default in `pyproject.toml` is 120 s and it covers SETUP as well as the
#: test body, so without this the run is killed mid-chain by `pytest-timeout` and reported
#: as a hang. `tests/integration/schema/test_ops_producer.py` sets a module-wide budget the
#: same way and for the same reason; `docs/diagnosis/retry-negative-control.md` records the
#: measurement that established the convention. This is a budget for a build, not a
#: loosened assertion: every assertion in this file still runs in milliseconds.
#: 7m01s was measured on a node that was merely busy. With four other workers driving the
#: same node it reached 95 of 271 files in 17 minutes, so a 30-minute budget would have
#: turned contention into a red that named nothing. An hour is deliberately generous for the
#: BUILD and changes nothing about what is asserted; a genuine hang still ends the session
#: with a stack, and the borrow path below is how a CI lane avoids paying it per run.
CHAIN_BUDGET_SECONDS = 3600
pytestmark = pytest.mark.timeout(CHAIN_BUDGET_SECONDS)

#: An ALREADY-MIGRATED database to probe instead of building one. Opt-in, and it is not an
#: escape hatch: every assertion below runs identically either way, and
#: :func:`privilege_conformance.chain_state` refuses a database whose applied count does not
#: equal the files on disk — so this cannot become a way to certify an empty cluster. It
#: exists because a CI lane that probes several roles should pay for one chain, once, and
#: `scripts/chain/apply_chain.py --keep` already leaves exactly such a database behind.
_BORROW_ENV = "MAINLINE_PRIVILEGE_DATABASE"

#: Anything that would be a credential leak in a report an operator pastes into a ticket: a
#: connection URL in any spelling, or the word ``password`` followed by a value that is not
#: already asterisks. The word alone is not a leak — ``password=***`` is the redactor
#: working — so the pattern is about VALUES and not about vocabulary.
_FORBIDDEN_IN_OUTPUT = re.compile(r"(?i)postgres(?:ql)?://|\bpassword\b\s*[=:]\s*'?(?!\*)")


# ── the cluster, or a skip that says what is missing ──────────────────────────────────


def _session_refusal(request: pytest.FixtureRequest) -> str | None:
    """What ``trappoint-testkit`` decided for this session, when the plugin is loaded.

    ``pytest --crdb=none`` is an instruction that this session has no cluster, and the
    plugin implements it by clearing the four DSN names it publishes and installing a guard
    against spawning one. It does **not** clear ``$LOCAL_DSN``, which an operator sets by
    hand — so a fixture that only read the environment would connect anyway and quietly
    overrule the flag. This asks the session first, and returns its reason when it says
    there is none.

    Absent plugin, absent decision: ``None``, and the environment read below applies. The
    plugin ships as a ``pytest11`` entry point and the repository-root ``conftest.py`` loads
    it from source when it is not installed, so ``None`` here means a checkout without it,
    not a session that quietly lost its cluster.
    """
    try:
        state = request.getfixturevalue("crdb_state")
    except Exception:  # noqa: BLE001 - no fixture by that name; the environment read applies
        return None
    # A `Skipped` raised inside `crdb_state` — "the plugin was not configured for this
    # session" — derives from BaseException and passes straight through the clause above,
    # deliberately: a session that never configured a cluster should say so in the plugin's
    # own words rather than be re-described here.
    if getattr(state, "cluster", None) is not None:
        return None
    return str(getattr(state, "skip_reason", "") or "no reason was recorded")


@pytest.fixture(scope="session")
def admin_target(request: pytest.FixtureRequest) -> Target:
    """The cluster to build on, or the one skip in this file.

    A skip and not an error, because PL-1 wants a stranger's machine to be able to
    reproduce the proof and a suite that errors on a missing cluster has stopped
    distinguishing "the gate refused" from "there was no gate". The reason names the lane
    that must make this branch unreachable in CI — see the module docstring.

    A :class:`Target` and not a ``str``, because pytest's long traceback prints the
    arguments of every frame it shows, and this value is an argument of every fixture below
    it. Measured in this file's own first run: a bare string put the whole DSN into the
    failure report. ``Target.__repr__`` is the cluster label and nothing else.
    """
    refusal = _session_refusal(request)
    if refusal is None:
        for name in _DSN_ENV_NAMES:
            value = os.environ.get(name)
            if value:
                return Target(value)
    cause = (
        f"this session decided it has no cluster - {refusal}"
        if refusal
        else "none of $" + ", $".join(_DSN_ENV_NAMES) + " is set"
    )
    pytest.skip(
        f"no CockroachDB: {cause}. Leg B of the privilege control asserts 42501 against a "
        "real cluster and asserts NOTHING when it is skipped. Start the local node "
        "(`docker compose up -d crdb`) or run with `--crdb=auto`. In CI this test belongs "
        "in the cluster lane, which provisions a node, so that this skip cannot become the "
        "normal outcome: a green that means 'I did not run' is the failure mode this "
        "control exists to end."
    )


@pytest.fixture(scope="session")
def probed(admin_target: Target) -> Iterator[World]:
    """Build an ephemeral database, apply the tree and the matrix, create the login, drop it.

    Its own database, every run, named like the ~140 other worker databases on the local
    node (``w_*``). Fresh because a halted migration leaves a version DIRTY and ``up``
    refuses to advance past it; the recovery is a new database, never
    ``trappoint migrate force``.

    ``$MAINLINE_PRIVILEGE_DATABASE`` borrows an already-migrated database instead, for a
    lane that probes more than one role and should pay the chain once. Borrowing is
    verified, not trusted: :func:`privilege_conformance.chain_state` compares the applied
    count against the files on disk and refuses anything short, because a part-migrated
    database would report the whole matrix as ABSENT and produce a green that meant "there
    was almost nothing here". Nothing is dropped that this fixture did not create.

    The login is created **without a password**: the local node runs ``--insecure`` and
    CockroachDB refuses one outright there — *"setting or updating a password is not
    supported in insecure mode"*. ``scripts/deploy/cloud_roles.py`` documents that branch;
    :func:`privilege_conformance.ensure_login` handles it the same way rather than
    discovering it as a failure mid-run. No password is generated by this suite at all.
    """
    if not DEFAULT_MATRIX.is_file():  # pragma: no cover - a checkout without the matrix
        pytest.fail(f"no grant matrix at {DEFAULT_MATRIX}; there is nothing to probe against")
    borrowed = os.environ.get(_BORROW_ENV) or None
    try:
        with world(
            admin_target,
            database=borrowed,
            role=DEFAULT_ROLE,
            migrations=DEFAULT_MIGRATIONS,
            matrix=DEFAULT_MATRIX,
        ) as built:
            print(f"\n[privilege] {built.database}: {built.chain_tail}")
            yield built
    except RuntimeError as exc:
        # The tree did not apply. That is a real failure of this leg's premise and is
        # reported as one — never a skip, which would certify the privileges of a database
        # that was never built.
        pytest.fail(safe(str(exc)))


@pytest.fixture(scope="session")
def report(probed: World) -> Report:
    """One probe of ``mainline_api``: both directions, run as the login itself."""
    return probe_world(
        probed,
        DEFAULT_ROLE,
        matrix=DEFAULT_MATRIX,
        sample=NEGATIVE_SAMPLE,
        schemas=matrix_schemas(DEFAULT_MATRIX),
    )


# ── the subject exists at all ─────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_the_matrix_declares_the_role_the_public_endpoint_runs_as(report: Report) -> None:
    """``mainline_api`` must be a first-class role in ``GRANTS.yaml``.

    Not a skip and not a soft pass. A role the matrix does not name has an empty reach,
    and an empty reach passes every negative probe in this file while proving nothing —
    which is precisely the vacuity this wave exists to end. If this fails, the deliverable
    that fixes it is named in the message.
    """
    assert report.reach.declared, (
        f"{DEFAULT_ROLE} is declared nowhere in {DEFAULT_MATRIX.name}: no role row, no "
        "membership, no schema privilege and no table privilege names it. Its entire "
        "privilege surface therefore lives in five Python tuples in "
        "scripts/deploy/cloud_roles.py (API_READ, API_GATE_READ, API_WRITE, AUDIT_VIEWS, "
        "API_MEMBERSHIPS), which no probe reads and no CI lane diffs.\n\n"
        "This is the deliverable of W2 in docs/leads/grants-in-migrations-plan.md: "
        f"'{DEFAULT_ROLE} and mainline_judge become first-class roles in GRANTS.yaml'. "
        "Until it lands this leg has no subject, and a probe with no subject is a green "
        "that means nothing."
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_the_probe_asked_the_database_something(report: Report) -> None:
    """Both directions must be non-empty, and the negative sample must be stratified.

    THE VACUITY GUARD. A probe that ran zero positive checks certifies a login that can
    reach nothing; a probe that ran zero negative checks certifies a login that is denied
    nothing. Either passes silently, and a silent pass is the failure mode this file was
    written against. The coverage claim is derived from the complement rather than from a
    number typed here: every ``(schema, verb)`` combination that occurs among the pairs the
    matrix does not name must occur in the sample.
    """
    assert report.positives, (
        f"the matrix names no probeable (object, verb) pair for {DEFAULT_ROLE}, so the "
        "positive direction asked nothing. A login that can read nothing passes every "
        "negative test below."
    )
    assert report.negatives, (
        f"every (object, verb) pair in {report.relations} relations is granted to "
        f"{DEFAULT_ROLE}, so the negative direction asked nothing. A role that is denied "
        "nothing is not a role."
    )

    if NEGATIVE_SAMPLE <= 0:
        assert len(report.negatives) == report.plan.complement, (
            f"this run asked about {len(report.negatives)} ungranted pairs out of "
            f"{report.plan.complement} in the complement, but NEGATIVE_SAMPLE is "
            f"{NEGATIVE_SAMPLE}, which means 'every one'. A negative direction that quietly "
            "shrank is a negative direction that stopped covering what it claims to cover."
        )
    asked_strata = {(o.check.pair.schema, o.check.pair.verb) for o in report.negatives}
    missing = sorted(f"{schema}/{verb}" for schema, verb in report.plan.strata - asked_strata)
    assert missing == [], (
        "the negative direction lost a (schema, verb) combination that occurs in the "
        f"complement: {missing}. The complement holds {report.plan.complement} probeable "
        f"pairs across {len(report.plan.strata)} strata; when a cap IS set the sample is "
        "stratified BEFORE it is filled, precisely so that no schema and no verb can fall "
        "out of it quietly."
    )
    # Scanner-rot guard. If `statement_for` ever stopped producing a shape for one of the
    # four verbs it would not fail — it would quietly return None and that verb would drop
    # out of every direction, leaving a suite that is green and blind. The verbs are asked
    # of the outcomes rather than counted in the source.
    asked = {o.check.pair.verb for o in report.outcomes}
    assert asked == set(PROBE_VERBS), (
        f"this run exercised {sorted(asked)} but this leg claims to probe "
        f"{sorted(PROBE_VERBS)}. A verb that silently produces no statement is a verb "
        "nothing in this file asserts anything about."
    )


# ── the two directions ────────────────────────────────────────────────────────────────


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_every_granted_pair_is_reachable(report: Report) -> None:
    """The POSITIVE direction: the matrix grants it, so the cluster must not refuse it.

    Each statement touched zero rows, so a ``42501`` here is the grant graph and nothing
    else — not a ``CHECK``, not an append-only trigger, not a row-level-security ``WITH
    CHECK`` clause, none of which a zero-row statement ever reaches.

    **"Not refused", not "succeeded".** A granted write can still end in a planner error:
    measured on v26.2.5, ``INSERT INTO mainline.exposure_line`` as a login that holds INSERT
    returns ``23502 missing "check_id" primary key column``, because column presence is
    checked whether or not a row arrives. Demanding ``00000`` would report a correct grant
    as a missing one, and the fix somebody would reach for is a weaker probe.

    A failure names every pair, the matrix row it came from and the statement that found it.
    """
    unreachable = [o for o in report.positives if not o.agreed]
    assert unreachable == [], report.failure_message()


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_every_ungranted_pair_is_refused_with_42501(report: Report) -> None:
    """The NEGATIVE direction: the matrix is silent, so the cluster must refuse.

    ``42501`` exactly, and no other SQLSTATE. A pair that the matrix does not name and the
    cluster allows is an over-grant on an endpoint an anonymous caller can reach, which is
    a defect and not a safety margin.
    """
    allowed = [o for o in report.negatives if not o.agreed]
    assert allowed == [], report.failure_message()


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_every_refusal_carries_the_house_exhibit(report: Report) -> None:
    """Every ``42501`` is labelled ``grant:<verb>:<object>:<role>``.

    ``packages/trappoint-conformance/cases/_privilege.py`` is the house treatment of this
    SQLSTATE and this file uses its token rather than inventing one. ``42501`` is the DENY
    class, excluded from the refusal taxonomy **by definition**: the writer was stopped by
    the grant graph or by a row-level-security policy before any gate condition was
    evaluated, so labelling it ``23514`` would say the gate refused something the gate
    never saw. The token is what makes a refusal recorded here legible beside every other
    refusal in the corpus, and the shape is `spec/errors.md` §3.1.
    """
    refusals = [o for o in report.outcomes if o.observed == DENY]
    assert refusals, "no refusal was observed at all; the negative direction proved nothing"
    malformed = [
        (str(o.check.pair), o.exhibit)
        for o in refusals
        if not (o.exhibit and _GRANT_TOKEN.match(o.exhibit))
    ]
    assert malformed == [], (
        "these 42501 outcomes carry no well-formed grant exhibit "
        f"(grant:<verb>:<object>:<role>, spec/errors.md 3.1): {malformed}"
    )
    wrong_role = [o.exhibit for o in refusals if not str(o.exhibit).endswith(f":{DEFAULT_ROLE}")]
    assert wrong_role == [], (
        f"a refusal by {DEFAULT_ROLE} carries another role's name in its exhibit: {wrong_role}. "
        "The token is synthesised from what the probe DID, so a mismatch means the probe "
        "connected as somebody else."
    )


# ── the falsification control: the same statements, a different role ──────────────────


def _probeable(relations: Mapping[str, Relation], pair: Pair) -> bool:
    relation = relations.get(pair.obj)
    return relation is not None and statement_for(relation, pair.verb) is not None


def _control_role(
    matrix: Path, subject: str, relations: Mapping[str, Relation]
) -> tuple[str, Pair, Pair]:
    """Find a declared role that differs from *subject* in BOTH directions.

    Returns ``(role, granted_to_the_subject_only, granted_to_the_control_only)``.
    Deterministic: roles are considered in the order the matrix declares them and each pair
    is the first in sorted order, so a failure is reproducible from the message alone and a
    re-run cannot quietly pick an easier pair.
    """
    from trappoint_migrate.grants import load_matrix

    subject_reach = matrix_reach(matrix, subject, relations)
    for row in load_matrix(matrix).get("roles") or []:
        name = str(row.get("name", ""))
        if not name or name == subject:
            continue
        other = matrix_reach(matrix, name, relations)
        mine = sorted(
            p for p in subject_reach.granted if p not in other.granted and _probeable(relations, p)
        )
        theirs = sorted(
            p for p in other.granted if p not in subject_reach.granted and _probeable(relations, p)
        )
        if mine and theirs:
            return name, mine[0], theirs[0]
    raise AssertionError(
        f"no role in {matrix.name} differs from {subject} in both directions, so this "
        "control cannot be run. That is itself a finding about the matrix: every declared "
        f"role is either a subset or a superset of {subject}."
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_the_probe_discriminates(probed: World) -> None:
    """THE 2x2. Two statements, two logins, and the answers must invert.

    A control that has never failed has never discriminated. Everything above asserts that
    ``mainline_api`` got the answers the matrix predicts; none of it can tell you whether
    the probe would have noticed different ones. So the identical statements are run again
    as a second login, which holds one of the two grants and not the other, and the four
    answers are required to form this grid:

    ========================  ===================  ==================
    statement                 as ``mainline_api``  as the control
    ========================  ===================  ==================
    granted to the subject    not ``42501``        ``42501``
    granted to the control    ``42501``            not ``42501``
    ========================  ===================  ==================

    **The control is a fresh login GRANTed the other role, not the role itself.** Every
    role in ``GRANTS.yaml`` except the two service identities is ``NOLOGIN`` by design —
    ``CURRENT_USER`` is the row-level-security scope token, so a role that can be logged in
    as directly is a role whose scope a credential holder chooses. ``test_mi_rls.py``
    established the same shape for the same reason: one login user per role under test,
    non-admin, because an admin bypasses RLS entirely and would be asserting against a
    session no policy ever applied to.

    If the probe were reporting "not refused" for everything — an admin connection, or a
    statement shape that never reaches a privilege check — this is the assertion that goes
    red while every other one in this file stays green.
    """
    with psycopg.connect(probed.target.dsn, autocommit=True) as admin:
        relations = relations_in(admin, matrix_schemas(DEFAULT_MATRIX))
    control_role, subject_only, control_only = _control_role(
        DEFAULT_MATRIX, DEFAULT_ROLE, relations
    )

    control_login = f"w4_control_{control_role}"[:60]
    ensure_login(probed.target, control_login, probed.database)
    with psycopg.connect(probed.target.dsn, autocommit=True) as admin:
        admin.execute(f'GRANT "{control_role}" TO "{control_login}"')

    def sql_for(pair: Pair) -> str:
        statement = statement_for(relations[pair.obj], pair.verb)
        if statement is None:  # pragma: no cover - _probeable filtered these out
            raise AssertionError(f"no statement shape for {pair}")
        return statement

    def grid(login: str, expectations: dict[Pair, str]) -> list[Outcome]:
        checks = [
            Check(pair=pair, expected=expected, sql=sql_for(pair), provenance="the 2x2 control")
            for pair, expected in expectations.items()
        ]
        return run_probe(as_role(probed.admin, login, probed.database), checks, login)

    try:
        observed = [
            *grid(DEFAULT_ROLE, {subject_only: OK, control_only: DENY}),
            *grid(control_login, {subject_only: DENY, control_only: OK}),
        ]
    finally:
        # A ROLE IS CLUSTER STATE and outlives the database that occasioned it — that is
        # the whole reason GRANTS.yaml is a re-asserted matrix and not a migration (DM-7).
        # This login exists for two statements; leaving it behind would add a principal to
        # a shared development node on every run, which is drift of exactly the kind this
        # file exists to detect. Failure to clean up is reported by the DROP itself and is
        # never allowed to mask the assertion below.
        #
        # The order is not cosmetic: CockroachDB refuses `DROP ROLE` while any grant on it
        # remains — measured, `cannot drop role/user …: grants still exist on <database>` —
        # so the membership and the CONNECT that `ensure_login` issued are both withdrawn
        # first. CONNECT is the one this test did not grant itself and would have missed.
        with psycopg.connect(probed.target.dsn, autocommit=True) as admin:
            admin.execute(f'REVOKE "{control_role}" FROM "{control_login}"')
            admin.execute(f'REVOKE ALL ON DATABASE "{probed.database}" FROM "{control_login}"')
            admin.execute(f'DROP ROLE IF EXISTS "{control_login}"')

    disagreed = [(o.check.pair, o.check.expected, o.observed) for o in observed if not o.agreed]
    assert disagreed == [], (
        f"the 2x2 control did not invert. Subject {DEFAULT_ROLE}; control {control_login}, "
        f"which holds {control_role} and nothing else.\n"
        f"  granted to {DEFAULT_ROLE} only: {subject_only}\n"
        f"  granted to {control_role} only: {control_only}\n"
        f"  disagreements (pair, expected, observed): {disagreed}\n\n"
        "Every other assertion in this file is only as good as this one: a probe that "
        "cannot tell two logins apart has greens that mean nothing."
    )


# ── properties of the report itself, which need no cluster ────────────────────────────


def _outcome(expected: str, observed: str) -> Outcome:
    pair = Pair(obj="mainline.permit", verb="SELECT")
    return Outcome(
        check=Check(pair=pair, expected=expected, sql="SELECT 1", provenance="a fixture"),
        observed=observed,
        detail="synthetic",
        exhibit="grant:SELECT:mainline.permit:mainline_api" if observed == DENY else None,
    )


def test_the_report_calls_a_difference_a_difference() -> None:
    """The reporting itself is falsifiable, and it is checked without a cluster.

    Four cases, one per quadrant, and the two that must be red are the point: a granted
    pair that was refused, and an ungranted pair that was allowed. A report that called
    either of those agreement would make every green in this file worthless, and no
    cluster is needed to find out.
    """
    assert _outcome(OK, OK).agreed
    assert _outcome(DENY, DENY).agreed
    assert not _outcome(OK, DENY).agreed, "a granted pair refused with 42501 is a difference"
    assert not _outcome(DENY, OK).agreed, "an ungranted pair that was allowed is a difference"


def test_an_absent_object_is_not_reported_as_a_refusal() -> None:
    """An object the tree does not create is ABSENT, and is not counted as a denial.

    ``GRANTS.yaml``'s own contract for ``grants apply`` says a row whose object is absent
    from the connected database is *"SKIPPED WITH A WARNING, never an error"*, and
    ``scripts/chain/apply_chain.py --grants`` publishes the census of them (producers-plan
    D12: reported, not authored — twelve of them on this tree, measured 2026-08-15). So
    ``42P01`` must not be allowed to masquerade as ``42501`` in either direction: the tree
    is what is incomplete, and the role's reach is not what is wrong.
    """
    absent = _outcome(OK, "42P01")
    assert absent.absent
    assert absent.agreed, "an absent object agrees vacuously and is counted on its own line"
    assert _outcome(DENY, "42P01").absent


def test_the_report_never_prints_a_dsn_or_a_password() -> None:
    """:func:`safe` removes anything DSN-shaped from every string this control emits.

    The probe is pointed at whatever DSN an operator passes it, including one with a
    password in it, and its output is a table an operator pastes into a ticket. Driver
    errors quote the connection string on almost every failure path, so the redaction is
    asserted here rather than trusted at each ``print``.
    """
    leaky = (
        "connection to postgresql://mainline_api:hunter2@db.example:26257/x failed; "
        "password = 's3cret' rejected"
    )
    cleaned = safe(leaky)
    assert "hunter2" not in cleaned
    assert "s3cret" not in cleaned
    assert "db.example" not in cleaned
    assert _FORBIDDEN_IN_OUTPUT.search(cleaned) is None, (
        f"safe() left something credential-shaped in {cleaned!r}"
    )


@pytest.mark.requires_cluster
@pytest.mark.schema
def test_the_rendered_report_leaks_no_credential(report: Report) -> None:
    """The real table and the real failure message, checked for the same property.

    The test above proves :func:`safe` works on a string built for it. This one proves the
    strings this run actually produced are clean — including whatever the driver said about
    the cluster it connected to, which is the text nobody remembers to redact.
    """
    for name, text in (
        ("summary", report.summary()),
        ("table", report.table()),
        ("failure_message", report.failure_message()),
    ):
        assert _FORBIDDEN_IN_OUTPUT.search(text) is None, (
            f"the rendered {name} contains something DSN- or password-shaped. This report "
            "is printed to a terminal and pasted into tickets; it names the cluster by its "
            "label (host, port, database) and by nothing else."
        )
