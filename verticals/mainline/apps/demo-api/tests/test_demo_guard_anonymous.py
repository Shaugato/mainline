# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The write guard, driven by an ANONYMOUS caller, against a real CockroachDB node.

WHY THIS FILE EXISTS, IN ONE PARAGRAPH
--------------------------------------
``infra/envs/demo/main.tf:312`` gives the demo Function URL ``authorization_type = NONE``.
The caller of every POST below is therefore a stranger on the internet, holding no token,
against a DSN role that carries the matching UPDATE and EXECUTE grants. Four of the five
POST resources commit — ``merge_permit``, ``suspend_permit``, ``materialise_checks``,
``sign_disposition`` — and three of those are irreversible on the one seeded subject a
hundred judges share. ``transitions._demo_guard`` is the ONLY thing between that stranger
and those four writes. This file drives all four as that stranger and requires a refusal
that left the database bit-for-bit where it found it.

THE NEAR-MISS THIS FILE IS THE ADVERSARIAL TEST FOR
---------------------------------------------------
``_demo_guard`` armed only when ``subject_id == scenario.permit_id``, and
``scenario.permit_id`` came from ``scenario.from_env()``, which reads
``MAINLINE_DEMO_PERMIT_ID`` and **falls back** to ``demo_uuid("permit")`` —
``077a6fdd-2167-559c-b2ff-8e3c8352504d``, a uuid5 derivation NOTHING HAS EVER SEEDED. The
only permit in Cloud ``mainline_demo`` is ``dec0de00-0006-4000-8000-000000000001``, which
the same public hostname hands out at ``/bundle/manifest.json``. So the guard was armed at
an identifier no caller would ever send, and the four committing POSTs were reachable by
anyone. That surface was inert only because of an unrelated ``KeyError`` on the refusal
path — an accident, removed on this same commit.

Terraform now publishes the seeded identifier under both names, so the guard arms TODAY.
**That is a configuration, and a configuration is disarmed by its own absence.** A deploy
from different tfvars, a hand-edited Lambda environment or a ``sam local`` drops the
variable and re-opens the hole with nothing anywhere saying so. So the property this file
pins is not "the guard is configured correctly today" — the deployment already asserts
that. It is: **a write path that cannot establish which subject is the protected demo
subject refuses rather than permits.**
:func:`test_the_four_posts_are_refused_with_the_permit_id_variable_unset` is that test, and
it FAILED against the code as it stood — measured, and recorded verbatim in
``evidence/deploy/demo-guard-armed.json``. A test that passes before the fix proves
nothing.

WHAT MAKES A REFUSAL A REFUSAL HERE
-----------------------------------
Not the status code. Every assertion below pairs the 423 with a snapshot taken **from a
second connection**, so what it reads is what COMMITTED — the state, ``head_seq``,
``gate_epoch`` and ``open_blocking`` of the subject, plus the row counts of every table
these four endpoints write. A refusal that still wrote something is not a refusal, and a
snapshot read back through the connection under test could not tell the difference between
"nothing was written" and "the write is sitting in an open transaction".

THE CONNECTION IS ``db.connection()``, NOT AN IMITATION OF IT
-------------------------------------------------------------
``db.py:309`` opens every production connection with ``row_factory=dict_row``. A test that
opened its own connection with psycopg's default ``tuple_row`` would not exercise the path
a Lambda takes — which is precisely how ``KeyError: 0`` survived into
``evidence/deploy/acceptance.json``. The fixture below calls the factory itself.
"""

from __future__ import annotations

import contextlib
import os
import re
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import psycopg
import pytest
from mainline_demo_api import db as db_mod
from mainline_demo_api import scenario as scenario_mod
from mainline_demo_api.transitions import handle_transition
from psycopg.rows import dict_row
from test_gate_run import w4_database  # noqa: F401 - re-exported so pytest can resolve it

# `conftest` is a bare absolute import into ONE `sys.modules` slot shared by all 55
# conftest.py files in this repository. It resolves to this directory's conftest because
# that file claims the name for the duration of its own collection — see the long comment
# at `tests/conftest.py:70`. `test_reads.py` and `test_envelope.py` import it the same way.
from conftest import REPO_ROOT

pytestmark = pytest.mark.requires_cluster

#: `mainline.disposition.rationale` carries a length CHECK and `_sign_disposition` caps the
#: input at 120 characters BEFORE the guard runs. A short rationale would therefore be a 422
#: that never reached the guard at all — a green test asserting nothing about the guard. The
#: body below is deliberately long enough to get past that validation and reach it.
_RATIONALE: Final = (
    "The recalled precursor is answered by a verified zero-energy isolation procedure that "
    "was re-issued after the incident, and this permit's scope is covered by it in full. "
    "Verification at zero is witnessed and recorded before any intrusive work begins."
)

#: The four committing POSTs, exactly as `app.py:179-182` routes them: the resource key, the
#: path parameter the router interpolates, and a body that is VALID — so that whatever
#: refuses is the guard and not a request-validation error wearing the same status.
_COMMITTING_POSTS: Final[tuple[tuple[str, str, dict[str, Any]], ...]] = (
    ("merge_permit", "permit_id", {}),
    ("suspend_permit", "permit_id", {"reason": "an anonymous caller asked for this"}),
    ("materialise_checks", "permit_id", {}),
    ("sign_disposition", "check_id", {"kind": "applied", "rationale": _RATIONALE}),
)

#: One statement, so every count is read at ONE moment and cannot be assembled out of two
#: different instants. `mainline.permit` is covered globally as well: a transition that
#: created a subject rather than moving one would otherwise pass a per-subject diff.
#:
#: THE GLOBAL CLAUSE CARRIES IDENTITIES AND NOT ONLY A COUNT, since 2026-08-13, and the
#: reason is written up in `docs/diagnosis/refusal-that-writes.md`. A count is weaker than
#: a set twice over. It cannot see an INSERT paired with a DELETE. And when it does
#: change, `116 != 117` is a number with no author: attributing that one took reconstructing
#: the baseline run from `opened_at` timestamps, and the answer turned out to be a row minted
#: by `test_transitions.py:137` in a SECOND pytest process sharing this scratch database.
#: `permit_ids` makes the same assertion strictly stronger and makes its failures name the
#: row, its `external_ref` and the moment it was opened — so the next reader is told in
#: one line whether the product wrote it or a stranger did.
_SNAPSHOT_SQL: Final = """
SELECT p.state::STRING, p.head_seq, p.gate_epoch, p.open_blocking,
       (SELECT count(*) FROM mainline.permit_event e WHERE e.permit_id = p.permit_id),
       (SELECT count(*) FROM mainline.merge_record m WHERE m.subject_id = p.permit_id),
       (SELECT count(*) FROM mainline.disposition d WHERE d.permit_id = p.permit_id),
       (SELECT count(*) FROM mainline.exposure_receipt r WHERE r.permit_id = p.permit_id),
       (SELECT count(*) FROM mainline.exposure_line l
          JOIN mainline.exposure_receipt r2 ON r2.receipt_id = l.receipt_id
         WHERE r2.permit_id = p.permit_id),
       (SELECT count(*) FROM mainline.blocking_check bc WHERE bc.permit_id = p.permit_id),
       (SELECT count(*) FROM mainline.permit),
       (SELECT coalesce(array_agg(q.permit_id::STRING), ARRAY[]::STRING[])
          FROM mainline.permit q)
  FROM mainline.permit p
 WHERE p.permit_id = %s
"""

_SNAPSHOT_FIELDS: Final = (
    "state",
    "head_seq",
    "gate_epoch",
    "open_blocking",
    "permit_event_rows",
    "merge_record_rows",
    "disposition_rows",
    "exposure_receipt_rows",
    "exposure_line_rows",
    "blocking_check_rows",
    "permit_rows_total",
    "permit_ids",
)

#: Where each `external_ref` prefix in this scratch database is minted. Nothing branches on
#: this table — it turns a uuid in a failure message into a file a reader can open, and a
#: prefix that is in none of these is reported as unattributed rather than guessed at.
_MINTED_BY: Final[tuple[tuple[str, str], ...]] = (
    ("PTW-W4-", "tests/test_transitions.py:137 (_seed_permit, via the fresh_history fixture)"),
    ("PTW-BARE-", "tests/test_transitions.py:267 (the bare_permit fixture)"),
    ("PTW-PROOF-", "scripts/proof/gate_refusal.py::seed_history — the demo subject itself"),
)


def snapshot(dsn: str, permit_id: str) -> dict[str, Any]:
    """Everything these four endpoints could write, read from a SECOND session.

    A second connection is the whole point. Read back through the connection under test,
    an uncommitted write is visible and a rolled-back one may or may not be, so the answer
    would not distinguish "nothing was written" from "the write has not landed yet". What
    another session can see is what committed, and what committed is what a judge who
    opens the demo an hour later will find.
    """
    with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as probe:
        row = probe.execute(_SNAPSHOT_SQL, (permit_id,)).fetchone()
    assert row is not None, f"the demo subject {permit_id} is not in this database"
    taken = dict(zip(_SNAPSHOT_FIELDS, row, strict=True))
    taken["permit_ids"] = frozenset(taken["permit_ids"])
    return taken


def _provenance(dsn: str, permit_ids: set[str]) -> list[str]:
    """Name each permit in *permit_ids*: its ``external_ref``, when it was opened, by whom.

    Diagnosis only — nothing here is asserted on. It runs on the failure path of
    :func:`changed`, where the question a reader actually has is not "how many" but
    "which row, and who wrote it".
    """
    if not permit_ids:
        return []
    with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as probe:
        rows = probe.execute(
            "SELECT permit_id::STRING, external_ref, opened_at FROM mainline.permit "
            "WHERE permit_id::STRING = ANY(%s) ORDER BY opened_at",
            (sorted(permit_ids),),
        ).fetchall()
    known = {pid: (ref, at) for pid, ref, at in rows}
    named = []
    for pid in sorted(permit_ids):
        ref, at = known.get(pid, ("(no longer present)", None))
        source = next(
            (where for prefix, where in _MINTED_BY if str(ref).startswith(prefix)),
            "no fixture in this suite mints that external_ref — this is the API's own write",
        )
        named.append(f"{pid} external_ref={ref!r} opened_at={at} minted by {source}")
    return named


def changed(dsn: str, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Every field that moved between two snapshots, with the permit set named rather than dumped.

    The assertion is unchanged and unweakened — ``after == before``, every field, the
    global permit set included. This only decides what a red SAYS: two frozensets of two
    hundred uuids printed in full are a diff nobody reads, whereas the rows that appeared,
    with the fixture that mints their ``external_ref``, are the answer.
    """
    moved: dict[str, Any] = {}
    for key in before:
        if before[key] == after[key]:
            continue
        if key == "permit_ids":
            appeared = set(after[key]) - set(before[key])
            vanished = set(before[key]) - set(after[key])
            if appeared:
                moved["permits_that_appeared"] = _provenance(dsn, appeared)
            if vanished:
                moved["permits_that_vanished"] = sorted(vanished)
        else:
            moved[key] = (before[key], after[key])
    return moved


@pytest.fixture
def anonymous_conn(w4_database: str) -> Iterator[psycopg.Connection[Any]]:  # noqa: F811
    """The REAL production connection — ``db.connection()`` — not an imitation of one.

    ``db.py`` opens it with ``row_factory=dict_row`` and ``autocommit=True``. Both are
    restored on the way out because ``transitions._prepare`` turns autocommit off and the
    connection is module-scoped and reused, exactly as it is on a warm Lambda.
    """
    conn = db_mod.connection(dsn=w4_database)
    try:
        yield conn
    finally:
        # `contextlib.suppress` rather than a bare try: the only way these raise is a
        # socket that died mid-test, and that is the test's failure to report, not this
        # fixture's to mask with a second exception on the way out.
        with contextlib.suppress(psycopg.Error):
            conn.rollback()
            conn.autocommit = True
        db_mod.close()


@pytest.fixture
def seeded(w4_database: str) -> dict[str, str]:  # noqa: F811
    """The seeded demo subject and one obligation on it, read out of the database.

    ``check_id`` is needed because ``sign_disposition`` is addressed by the OBLIGATION, not
    by the subject — its guard therefore runs inside ``_sign_disposition`` after the check
    has been resolved to its permit, and driving it needs a check that really belongs to
    the demo subject.
    """
    permit_id = os.environ["MAINLINE_DEMO_PERMIT_ID"]
    with psycopg.connect(w4_database, autocommit=True, connect_timeout=10) as probe:
        row = probe.execute(
            "SELECT check_id::STRING FROM mainline.blocking_check WHERE permit_id = %s "
            "ORDER BY check_id LIMIT 1",
            (permit_id,),
        ).fetchone()
    assert row is not None, (
        f"the seeded demo subject {permit_id} has no mainline.blocking_check, so "
        "sign_disposition cannot be driven at it and this file would silently test three "
        "endpoints while claiming four"
    )
    return {"permit_id": permit_id, "check_id": row[0]}


def drive(
    conn: psycopg.Connection[Any], seeded: Mapping[str, str], resource: str, param: str, body: Any
) -> tuple[int, dict[str, Any]]:
    """One POST, as the router would deliver it, with the connection left usable after."""
    try:
        return handle_transition(resource, {param: seeded[param]}, body, conn)
    finally:
        # `handle_transition` promises to leave no transaction in progress, and the demo
        # subject's own tests below re-read through other sessions anyway. This restores
        # the factory's autocommit so the NEXT call in the same test starts where a fresh
        # Lambda invocation would.
        conn.rollback()
        conn.autocommit = True


# ═══════════════════════════════════════════════════════════════════════════════════════
# the premise, measured rather than assumed
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_production_connection_is_the_one_db_py_opens(
    anonymous_conn: psycopg.Connection[Any],
) -> None:
    """Pin what every assertion below rests on: this is the Lambda's connection.

    A suite that opened its own ``tuple_row`` connection would prove nothing about a
    handler that runs on ``dict_row`` — which is exactly how ``KeyError: 0`` reached
    ``evidence/deploy/acceptance.json`` through a contract test written to catch it.
    """
    assert anonymous_conn.row_factory is dict_row
    assert anonymous_conn.autocommit is True


def test_the_uuid5_fallback_names_a_permit_that_is_not_in_this_database(
    w4_database: str,  # noqa: F811
) -> None:
    """THE NEAR-MISS, stated as a measurement: the old arming id is seeded nowhere.

    ``scenario.from_env`` falls back to ``demo_uuid("permit")`` when
    ``MAINLINE_DEMO_PERMIT_ID`` is absent. If that identifier were seeded, arming at it
    would be harmless and this whole file would be about nothing. It is not seeded — here,
    and (measured read-only on 2026-08-12) not in Cloud ``mainline_demo`` either, where the
    single permit is ``dec0de00-0006-4000-8000-000000000001``.
    """
    fallback = scenario_mod.from_env({}).permit_id
    assert fallback == scenario_mod.demo_uuid("permit")
    assert str(fallback) == scenario_mod.EXPECTED["permit"]

    with psycopg.connect(w4_database, autocommit=True, connect_timeout=10) as probe:
        found = probe.execute(
            "SELECT count(*) FROM mainline.permit WHERE permit_id = %s", (str(fallback),)
        ).fetchone()
    assert found is not None
    assert found[0] == 0, (
        f"{fallback} IS seeded in this database, which would make the guard's env-less "
        "fallback point at a real subject. That is a fine thing to have changed, but this "
        "file's whole premise is that it does not — re-measure before deleting anything."
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# all four committing POSTs, at the seeded subject, by an anonymous caller
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(("resource", "param", "body"), _COMMITTING_POSTS)
def test_every_committing_post_is_refused_at_the_seeded_demo_subject(
    anonymous_conn: psycopg.Connection[Any],
    seeded: dict[str, str],
    resource: str,
    param: str,
    body: dict[str, Any],
) -> None:
    """423, naming the endpoint that does this safely. All four, not the three easy ones."""
    status, payload = drive(anonymous_conn, seeded, resource, param, body)

    assert status == 423, payload
    assert payload["error"] == "demo_subject_write_protected"
    assert payload["use_instead"] == "POST /v1/demo/gate-run"
    # A client error is never dressed as a gate refusal: no envelope, no SQLSTATE, no
    # exhibit. The gate did not refuse this — the API did, before asking it.
    assert "envelope_version" not in payload
    assert "refusal" not in payload


def test_the_four_refusals_leave_the_subject_and_every_row_count_unchanged(
    anonymous_conn: psycopg.Connection[Any],
    seeded: dict[str, str],
    w4_database: str,  # noqa: F811
) -> None:
    """A refusal that still wrote something is not a refusal.

    Driven as one session would drive it — all four in a row, on one connection — because
    the failure worth catching is a guard that refuses the second call only after the first
    has left a transaction, a receipt or an event behind.
    """
    before = snapshot(w4_database, seeded["permit_id"])

    outcomes = {}
    for resource, param, body in _COMMITTING_POSTS:
        status, payload = drive(anonymous_conn, seeded, resource, param, body)
        outcomes[resource] = (status, payload.get("error"))

    after = snapshot(w4_database, seeded["permit_id"])

    assert outcomes == dict.fromkeys(
        (r for r, _, _ in _COMMITTING_POSTS), (423, "demo_subject_write_protected")
    )
    assert after == before, changed(w4_database, before, after)


def test_the_guard_does_not_refuse_traffic_that_is_not_the_demo_subject(
    anonymous_conn: psycopg.Connection[Any],
) -> None:
    """The fix must fail CLOSED, not fail SHUT.

    A guard that answered 423 to everything would pass every assertion above while making
    the API useless, so the negative control is part of the claim: a permit that is not the
    demo subject gets the ordinary 404, which is only reachable if the guard returned
    ``None`` and the transition ran.
    """
    absent = uuid.uuid5(uuid.NAMESPACE_URL, "mainline/w6-guard/absent-permit")
    try:
        status, payload = handle_transition(
            "merge_permit", {"permit_id": str(absent)}, {}, anonymous_conn
        )
    finally:
        anonymous_conn.rollback()
        anonymous_conn.autocommit = True
    assert status == 404, payload
    assert payload["error"] == "no_such_permit"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the deployed identifier and the armed identifier are the same identifier
# ═══════════════════════════════════════════════════════════════════════════════════════

#: `variable "scenario_permit_id" { … default = "…" }` in the module Terraform actually
#: applies. The pattern anchors `default` to the start of a line because the variable's own
#: `description` heredoc QUOTES the superseded uuid5 value in prose — a regex that took the
#: first UUID inside the block would read the near-miss identifier and assert the opposite
#: of what this test means.
_TF_DEFAULT: Final = re.compile(
    r'variable\s+"scenario_permit_id"\s*\{.*?^\s*default\s*=\s*"([0-9a-fA-F-]{36})"',
    re.DOTALL | re.MULTILINE,
)

#: The publication. A default that is not published under the name `scenario.from_env`
#: reads is a default that never reaches the guard — which was the SECOND half of the same
#: near-miss, and is why the module sets both names.
_TF_PUBLISHES: Final = re.compile(
    r"^\s*MAINLINE_DEMO_PERMIT_ID\s*=\s*var\.scenario_permit_id\s*$", re.MULTILINE
)

_MODULE_TF: Final[Path] = REPO_ROOT / "infra/modules/demo-api"


def _terraform_permit_id() -> str:
    """The deployed identifier, READ FROM THE FILE that deploys it.

    Restating the literal here would make this test a comparison of two copies of the same
    typo. The file is the artefact Terraform applies, so the file is what is read.
    """
    text = (_MODULE_TF / "variables.tf").read_text(encoding="utf-8")
    found = _TF_DEFAULT.search(text)
    assert found is not None, (
        "infra/modules/demo-api/variables.tf no longer declares a literal default for "
        'variable "scenario_permit_id". If the identifier moved to a tfvars file or a '
        "data source, this test must follow it there — deleting the assertion would leave "
        "the guard's arming identifier unchecked against the deployment's."
    )
    return found.group(1)


def test_the_deployed_permit_id_is_not_the_unseeded_uuid5_derivation() -> None:
    """The regression that would silently re-open the hole, pinned at its source."""
    deployed = uuid.UUID(_terraform_permit_id())
    assert deployed != scenario_mod.demo_uuid("permit"), (
        "infra/modules/demo-api/variables.tf has gone back to defaulting scenario_permit_id "
        f"to {deployed} — mainline_demo_api.scenario's uuid5 fallback, which NOTHING HAS "
        "EVER SEEDED. Deploying that arms _demo_guard at an identifier no caller sends and "
        "makes every gate run answer 422 demo_history_not_seeded."
    )


def test_the_deployed_permit_id_is_published_under_the_name_the_code_reads() -> None:
    """A default nothing publishes under ``MAINLINE_DEMO_PERMIT_ID`` never reaches the guard.

    ``scenario.from_env`` reads ``ENV_PREFIX + "PERMIT_ID"`` and nothing else.
    ``MAINLINE_SCENARIO_PERMIT_ID`` — the name the module was specified to publish — is
    inert on its own, which is the worst of the three possible states because it looks
    configured.
    """
    text = (_MODULE_TF / "main.tf").read_text(encoding="utf-8")
    assert _TF_PUBLISHES.search(text) is not None, (
        "infra/modules/demo-api/main.tf no longer sets MAINLINE_DEMO_PERMIT_ID from "
        "var.scenario_permit_id. That is the ONLY name mainline_demo_api.scenario.from_env "
        "reads; publishing the identifier under any other name leaves the override "
        "configured-looking and inert."
    )
    assert scenario_mod.ENV_PREFIX + "PERMIT_ID" == "MAINLINE_DEMO_PERMIT_ID"


def test_the_guard_arms_at_exactly_the_identifier_the_deployment_publishes(
    anonymous_conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Close the loop: put the deployed value in the environment and drive the endpoint.

    This is the assertion the audit wanted and did not have. It does not need that permit
    to exist here — the guard decides on the identifier before it touches a row, which is
    the property that makes it safe to state as a claim about the DEPLOYMENT from a test
    running on a laptop.
    """
    deployed = _terraform_permit_id()
    monkeypatch.setenv("MAINLINE_DEMO_PERMIT_ID", deployed)

    assert str(scenario_mod.from_env().permit_id) == deployed

    try:
        status, payload = handle_transition(
            "merge_permit", {"permit_id": deployed}, {}, anonymous_conn
        )
    finally:
        anonymous_conn.rollback()
        anonymous_conn.autocommit = True
    assert status == 423, payload
    assert payload["error"] == "demo_subject_write_protected"
    assert payload["subject_id"] == deployed


# ═══════════════════════════════════════════════════════════════════════════════════════
# THE NEAR-MISS, REPRODUCED — this is the test that had to fail first
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_four_posts_are_refused_with_the_permit_id_variable_unset(
    anonymous_conn: psycopg.Connection[Any],
    seeded: dict[str, str],
    w4_database: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drop the environment variable and drive all four at the seeded subject anyway.

    THIS IS THE WHOLE POINT OF THE FILE, and it is the only test here that could not have
    been written by reading the code and agreeing with it. Every other 423 test in this
    repository — ``test_transitions.py``, ``test_row_factory_contract.py`` — sets
    ``MAINLINE_DEMO_PERMIT_ID`` itself first, so all of them were green while the deployed
    Lambda was armed at an identifier nobody sends.

    With the variable gone, ``scenario.permit_id`` is the uuid5 derivation nothing seeded.
    The guard therefore CANNOT establish which subject is the protected one — and a write
    path that cannot establish that must refuse. It answers ``423
    demo_subject_unidentified``, which is a different sentence from "this is the demo
    subject" on purpose: claiming a subject is the demo subject when the deployment cannot
    say which one is would be a fabricated exhibit, and this API does not produce those.

    MEASURED BEFORE THE FIX, against the code as it stood: all four returned 2xx/4xx from
    the real transition, ``merge_record`` gained a row and the subject moved to ``merged``.
    ``evidence/deploy/demo-guard-armed.json`` records that run verbatim.
    """
    monkeypatch.delenv("MAINLINE_DEMO_PERMIT_ID", raising=False)
    assert scenario_mod.from_env().permit_id == scenario_mod.demo_uuid("permit")

    before = snapshot(w4_database, seeded["permit_id"])

    refused: dict[str, tuple[int, Any]] = {}
    for resource, param, body in _COMMITTING_POSTS:
        status, payload = drive(anonymous_conn, seeded, resource, param, body)
        refused[resource] = (status, payload.get("error"))

    after = snapshot(w4_database, seeded["permit_id"])

    assert refused == dict.fromkeys(
        (r for r, _, _ in _COMMITTING_POSTS), (423, "demo_subject_unidentified")
    ), (
        "with MAINLINE_DEMO_PERMIT_ID unset the guard cannot say which subject it protects, "
        "and it let a committing POST through. That is the near-miss, reproduced: on a "
        "Function URL with authorization_type = NONE these four are reachable by anyone. "
        f"Got: {refused}"
    )
    assert after == before, changed(w4_database, before, after)


def test_a_deployment_that_owns_its_database_can_still_lift_the_guard(
    anonymous_conn: psycopg.Connection[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed is not a brick: ``MAINLINE_DEMO_ALLOW_MUTATION`` still lifts it.

    Driven at a permit that does not exist, so the lifted guard cannot commit anything: the
    404 is proof the guard returned ``None``, and nothing was written to prove it.
    """
    monkeypatch.delenv("MAINLINE_DEMO_PERMIT_ID", raising=False)
    monkeypatch.setenv("MAINLINE_DEMO_ALLOW_MUTATION", "1")
    absent = uuid.uuid5(uuid.NAMESPACE_URL, "mainline/w6-guard/absent-permit-2")
    try:
        status, payload = handle_transition(
            "merge_permit", {"permit_id": str(absent)}, {}, anonymous_conn
        )
    finally:
        anonymous_conn.rollback()
        anonymous_conn.autocommit = True
    assert status == 404, payload
    assert payload["error"] == "no_such_permit"
