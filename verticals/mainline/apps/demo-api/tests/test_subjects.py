# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``GET /v1/demo/subjects`` — the kernel names its own subjects, and cannot invent one.

WHAT THIS FILE EXISTS TO PREVENT COMING BACK
--------------------------------------------
The console shipped ``DEFAULT_SITE_CODE = 'BLK-07'`` and a clause/commit pair, both of
which the deployed kernel answers **404** for, because a screen needs a subject identifier
and had no way to ask for one. This route is the way to ask. Its entire value is that the
answer is ``SELECT``ed, so the tests below are written against the two ways that value can
be lost:

**By fabrication** — a constant in the emitter that happens to match today's seed. That is
the defect being fixed, wearing a Python costume, and it would pass every "does the screen
render" test ever written. :func:`test_no_subject_identifier_is_a_literal_in_the_emitter`
parses the module and fails on any UUID-shaped or digest-shaped literal in it.

**By silence** — a subject the database does not carry, rendered as a plausible-looking
placeholder so a screen stays green. :func:`test_a_database_with_no_demo_seed_is_a_named_404`
runs the read against a database that has the whole 271-file migration chain and **no seed**
and requires a 404 naming what was looked for.

Everything in between is checked against the seeded world the DEPLOYMENT applies, through
``app.handler`` — the Lambda entry point — rather than by calling the read function, because
a route that works when called and 404s when addressed is the defect this repository has
already shipped once.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from mainline_demo_api import app, envelope, reads, subjects
from mainline_demo_api import db as demo_db

from conftest import CONTRACTS_DIR, MIGRATIONS_DIR, SchemaRegistry

_HERE = Path(__file__).resolve().parent
SUBJECTS_CONTRACT = _HERE.parents[0] / "contracts" / "subjects.schema.json"

#: Anything shaped like an identifier this route is supposed to READ. A UUID, a 32-byte
#: digest, or the demo seed's own ``dec0de00`` prefix in any casing.
_IDENTIFIER_SHAPED = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"|[0-9a-f]{64}"
    r"|(?i:dec0de00)"
)


def _event(method: str, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    """A Lambda Function URL payload-format-2.0 event, the shape AWS actually sends."""
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
    }
    if query:
        event["queryStringParameters"] = dict(query)
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


@contextlib.contextmanager
def _pointed_at(dsn: str) -> Iterator[None]:
    """Point ``app.handler`` at *dsn* the way the deployment does: through the environment.

    ``handler`` calls ``db.connection()`` with no argument, which resolves ``$MAINLINE_DSN``
    (or the SSM parameter named by ``$MAINLINE_DSN_PARAM``). Handing the module a
    connection directly would test a path the Lambda does not take. The DSN cache is reset
    on both sides so no test can inherit or leave a database.
    """
    patch = pytest.MonkeyPatch()
    patch.setenv("MAINLINE_DSN", dsn)
    patch.delenv("MAINLINE_DSN_PARAM", raising=False)
    demo_db.reset_dsn_cache()
    try:
        yield
    finally:
        patch.undo()
        demo_db.reset_dsn_cache()


# ── The contract, and the registry that can resolve it ──────────────────────────────


@pytest.fixture(scope="session")
def subjects_registry(tmp_path_factory: pytest.TempPathFactory) -> SchemaRegistry:
    """The console's contracts, with the **demo-api's own copy** of this one staged over them.

    The two copies of ``subjects.schema.json`` must be byte-identical — the test below
    asserts it — so this fixture would compile the same document either way. It stages the
    API's copy deliberately anyway: this suite is the API's, the API is the emitter, and a
    validator that silently preferred the client's copy would report the console's opinion
    of a payload the console did not produce.
    """
    if not CONTRACTS_DIR.is_dir():
        pytest.skip(f"the console's contracts are not present at {CONTRACTS_DIR}")
    staged = tmp_path_factory.mktemp("subjects-contracts")
    for path in CONTRACTS_DIR.glob("*.schema.json"):
        shutil.copy2(path, staged / path.name)
    shutil.copy2(SUBJECTS_CONTRACT, staged / SUBJECTS_CONTRACT.name)
    return SchemaRegistry(staged)


def test_the_contract_is_committed_and_names_the_id_the_module_stamps() -> None:
    """Two constants, two files, one wire value — and nothing but this makes them agree.

    The same argument ``test_routes_gate_run.py`` makes about ``GATE_RUN_SCHEMA_ID``: the
    console looks a contract up by this string and refuses a payload naming one it does not
    hold, so a drift here is an unverifiable claim rather than a forward-compatible read.
    """
    document = json.loads(SUBJECTS_CONTRACT.read_text(encoding="utf-8"))
    assert document["$id"] == subjects.SUBJECTS_SCHEMA_ID
    assert document["$id"] == f"{envelope.CONTRACT_BASE}subjects.schema.json"
    assert (SUBJECTS_CONTRACT.parent / f"{SUBJECTS_CONTRACT.name}.license").is_file(), (
        "REUSE sidecar is missing; JSON admits no comment syntax and the licence has to "
        "live beside the file"
    )


def test_the_two_copies_of_the_contract_are_byte_identical() -> None:
    """The API serves against one file and the console validates against another.

    ``gate-run.schema.json`` is already kept this way, byte for byte, and for the reason
    that matters here: two copies of one contract that drift produce a payload the emitter
    thinks is valid and the client refuses, at deploy time, in front of a judge. The
    demo-api's copy is the original — its ``$comment`` says so — and the console's is the
    copy its bundler imports with ``?raw``.
    """
    console_copy = CONTRACTS_DIR / SUBJECTS_CONTRACT.name
    if not console_copy.is_file():
        pytest.skip(f"{console_copy} is absent, so the two copies cannot be compared")
    assert console_copy.read_bytes() == SUBJECTS_CONTRACT.read_bytes(), (
        f"{console_copy} and {SUBJECTS_CONTRACT} have drifted. The demo-api's copy is the "
        "original; copy it over the console's rather than editing either one alone."
    )


def test_the_envelope_is_the_one_read_envelope_builds() -> None:
    """Not a mirror of the read envelope — the read envelope.

    ``subjects`` is an ordinary read: the console declares it, ``SCHEMA_IDS`` names its
    contract, and it goes out through :func:`envelope.read_envelope` like the other twelve.
    An earlier draft of this module built the envelope itself, because the key was not in
    ``SCHEMA_IDS`` and ``read_envelope`` refuses an unknown key; that draft would have been
    a second writing of one shape, and two writings drift. This asserts the second writing
    is gone.
    """
    source = Path(subjects.__file__).read_text(encoding="utf-8")
    assert "read_envelope(" in source
    assert '"envelope_version"' not in source, (
        "subjects.py is constructing an envelope member by hand again; envelope.read_envelope "
        "is the one builder and a second one cannot be kept in step with it"
    )


def test_no_subject_identifier_is_a_literal_in_the_emitter() -> None:
    """No UUID, no 64-hex digest and no ``dec0de00`` anywhere in ``subjects.py``.

    THE ONE UNFORGIVABLE MOVE. A worker who pastes ``dec0de00-0006-…`` into this module has
    rebuilt ``BLK-07`` with a luckier value: it works today, fails the moment the seed
    changes, and cannot say which of the two it is doing. Read from the SYNTAX TREE, so
    prose in the docstring cannot trip it and a literal cannot hide behind one.

    The scan covers every string and bytes constant in the module, including default
    arguments and dictionary values — the three places a fallback identifier would most
    plausibly be written. **Docstrings are excluded, and only docstrings**: a bare string
    expression is documentation and cannot be returned to a caller, and the module's own
    prose has to be able to name the identifier it is forbidden to contain. Every other
    constant, in every position, is in scope.
    """
    source = Path(subjects.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=subjects.__file__)
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    offenders: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (str, bytes))
            and id(node) not in documentation
        ):
            text = node.value if isinstance(node.value, str) else node.value.decode("latin-1")
            match = _IDENTIFIER_SHAPED.search(text)
            if match is not None:
                offenders.append(f"line {node.lineno}: {match.group(0)!r}")
    assert offenders == [], (
        "subjects.py carries an identifier-shaped literal. Every identifier this route "
        "returns must be SELECTed: " + "; ".join(offenders)
    )


def test_the_module_declares_its_parameters_through_reads_and_takes_none() -> None:
    """The parameter contract is one table, and this resource is in it."""
    assert reads._DECLARED_PARAMS[subjects.SUBJECTS_RESOURCE] == ((), ())
    assert reads.READS[subjects.SUBJECTS_RESOURCE] is reads.read_demo_subjects


# ── Against the seeded world the deployment applies ─────────────────────────────────


@pytest.fixture(scope="session")
def subjects_payload(demo_database: tuple[str, dict[str, str]]) -> dict[str, Any]:
    """The envelope, produced ONCE through ``app.handler`` against the seeded database.

    Through the handler and not through :func:`subjects.read_subjects`, because "the
    function returns the right thing" and "the route returns the right thing" are different
    sentences and this repository has already shipped a demo where only the first was true.
    """
    dsn, _seed = demo_database
    with _pointed_at(dsn):
        response = app.handler(_event("GET", "/v1/demo/subjects"))
    assert response["statusCode"] == 200, response["body"]
    assert response["headers"]["content-type"] == "application/json; charset=utf-8"
    assert response["headers"]["cache-control"] == "public, max-age=10"
    assert "x-mainline-read-ms" in response["headers"]
    return json.loads(response["body"])


@pytest.mark.requires_cluster
def test_the_payload_satisfies_its_committed_contract(
    subjects_payload: dict[str, Any], subjects_registry: SchemaRegistry
) -> None:
    """The exact ``$id`` the console will look it up by, against the file on disk."""
    assert subjects_payload["resource"] == subjects.SUBJECTS_RESOURCE
    assert subjects_payload["schema_id"] == subjects.SUBJECTS_SCHEMA_ID
    errors = subjects_registry.validate(subjects.SUBJECTS_SCHEMA_ID, subjects_payload)
    assert errors == [], "subject index violates its contract:\n  " + "\n  ".join(errors[:12])


@pytest.mark.requires_cluster
def test_every_identifier_is_the_one_the_seeded_database_holds(
    subjects_payload: dict[str, Any], seed: dict[str, str]
) -> None:
    """Compared against ``conftest``'s identifiers, which are themselves read out of the seed.

    Neither side of this equality is written down anywhere: the fixture queries the
    database the deployment's own seed files built, and the route queries the same
    database. A constant on either side makes this fail rather than pass.

    Both arrangements are compared, because they are two renderings of one choice and the
    defect that would hide here is the two disagreeing about which permit the demo means.
    """
    data = subjects_payload["data"]
    got = data["subjects"]
    assert got["site"]["site_id"] == seed["site_id"]
    assert got["site"]["site_code"] == seed["site_code"]
    assert got["permit"]["permit_id"] == seed["permit_id"]
    assert got["blocking_check"]["check_id"] == seed["check_id"]
    assert got["clause"]["clause_uuid"] == seed["clause_uuid"]
    assert got["change_request"]["cr_id"] == seed["cr_id"]
    assert got["recall_run"]["run_id"] == seed["run_id"]
    assert got["exposure_receipt"]["receipt_id"] == seed["receipt_id"]

    assert data["site_id"] == got["site"]["site_id"]
    assert data["site_code"] == got["site"]["site_code"]
    assert data["permit_id"] == got["permit"]["permit_id"]
    assert data["check_id"] == got["blocking_check"]["check_id"]
    assert data["cr_id"] == got["change_request"]["cr_id"]
    assert data["receipt_id"] == got["exposure_receipt"]["receipt_id"]
    assert data["clause_uuid"] == got["clause"]["clause_uuid"]
    assert data["commit_id"] == got["clause"]["head_commit"]
    assert data["run_id"] == got["recall_run"]["run_id"]
    assert data["lesson_id"] == got["event"]["event_id"]


@pytest.mark.requires_cluster
def test_every_returned_identifier_addresses_a_route_that_answers_200(
    subjects_payload: dict[str, Any], demo_database: tuple[str, dict[str, str]]
) -> None:
    """The point of the index: every id it hands out must be one the API can be asked for.

    Driven through ``app.handler`` at the same paths the console builds, so this is the
    local counterpart of the ``curl`` transcript taken against the live URL. An id that
    parses, satisfies the schema and 404s is worth nothing to a screen.
    """
    dsn, _ = demo_database
    got = subjects_payload["data"]
    paths = [
        (f"/v1/permits/{got['permit_id']}", None),
        (f"/v1/permits/{got['permit_id']}/blocking-checks", None),
        (f"/v1/permits/{got['permit_id']}/silence", None),
        (f"/v1/checks/{got['check_id']}/disposition", None),
        (f"/v1/clauses/{got['clause_uuid']}/ancestry", None),
        (f"/v1/clauses/{got['clause_uuid']}/versions/{got['commit_id']}", None),
        (f"/v1/lessons/{got['lesson_id']}/propagation", None),
        (f"/v1/change-requests/{got['cr_id']}", None),
        (f"/v1/recall-runs/{got['run_id']}", None),
        (f"/v1/receipts/{got['receipt_id']}", None),
        ("/v1/ledger", {"site_code": got["site_code"]}),
    ]
    with _pointed_at(dsn):
        outcomes = {path: app.handler(_event("GET", path, query)) for path, query in paths}
    failed = {
        path: (response["statusCode"], response["body"][:200])
        for path, response in outcomes.items()
        if response["statusCode"] != 200
    }
    assert failed == {}, f"identifiers the index handed out that do not resolve: {failed}"


@pytest.mark.requires_cluster
def test_the_chosen_check_is_the_open_one_the_blocking_checks_read_agrees_is_open(
    subjects_payload: dict[str, Any], demo_database: tuple[str, dict[str, str]]
) -> None:
    """One derivation of ``open``, asserted against the other reader of it.

    ``open`` is not a column — it is the absence of a live ``mainline.disposition`` row —
    and this module and ``reads.read_blocking_checks`` compute it separately. Two
    computations of one predicate can disagree; this is where that disagreement surfaces.
    """
    dsn, _ = demo_database
    chosen = subjects_payload["data"]["subjects"]["blocking_check"]
    permit_id = subjects_payload["data"]["permit_id"]
    with _pointed_at(dsn):
        conn = demo_db.connection()
        checks = reads.read_resource(conn, "blocking_checks", {"permit_id": permit_id}, {})["data"]
    open_ids = [c["check_id"] for c in checks["checks"] if c["open"]]
    assert chosen["check_id"] in open_ids, (
        f"the index chose {chosen['check_id']}, which read_blocking_checks does not call "
        f"open. Open there: {open_ids}"
    )
    assert chosen["count"] == len(open_ids), (
        f"the index reports {chosen['count']} open checks and read_blocking_checks sees "
        f"{len(open_ids)}"
    )


@pytest.mark.requires_cluster
def test_every_count_equals_an_independently_asked_count(
    subjects_payload: dict[str, Any], demo_database: tuple[str, dict[str, str]]
) -> None:
    """``count(*) OVER ()`` beside the chosen row, checked against a plain ``count(*)``.

    The count is the promise that a choice was made among several rather than that exactly
    one existed. A window function that silently counted the post-LIMIT rows would report
    1 forever and nobody would see it.
    """
    dsn, _ = demo_database
    got = subjects_payload["data"]["subjects"]
    site_id = subjects_payload["data"]["site_id"]
    permit_id = subjects_payload["data"]["permit_id"]
    expected = {
        "site": ("SELECT count(*) AS n FROM mainline.site", ()),
        "permit": ("SELECT count(*) AS n FROM mainline.permit WHERE site_id = %s", (site_id,)),
        "clause": ("SELECT count(*) AS n FROM mainline.clause WHERE site_id = %s", (site_id,)),
        "event": ("SELECT count(*) AS n FROM mainline.event WHERE site_id = %s", (site_id,)),
        "change_request": (
            "SELECT count(*) AS n FROM mainline.change_request WHERE site_id = %s",
            (site_id,),
        ),
        "recall_run": (
            "SELECT count(*) AS n FROM mainline_meas.recall_run WHERE permit_id = %s",
            (permit_id,),
        ),
        "exposure_receipt": (
            "SELECT count(*) AS n FROM mainline.exposure_receipt WHERE permit_id = %s",
            (permit_id,),
        ),
    }
    with _pointed_at(dsn):
        conn = demo_db.connection()
        for name, (sql, args) in expected.items():
            row = conn.execute(sql, args).fetchone()
            assert row is not None
            assert got[name]["count"] == int(dict(row)["n"]), name


@pytest.mark.requires_cluster
def test_the_seeded_world_leaves_nothing_absent_and_absent_is_the_only_alternative(
    subjects_payload: dict[str, Any],
) -> None:
    """On the full seed every indexed subject is present, so ``absent`` is empty.

    Stated as an equality rather than a length so that a future seed change reports WHICH
    subject went missing. The complementary property — a missing subject appears in
    ``absent`` and never as a placeholder in ``subjects`` — is what the schema's
    ``additionalProperties: false`` and the absence entry's ``required`` members enforce,
    and what the no-seed test below exercises end to end.

    The addressing vector is asserted complete in the same breath: on the full seed no slot
    may be ``null``, because a null slot is a screen that opens on nothing.
    """
    data = subjects_payload["data"]
    assert data["absent"] == [], data["absent"]
    assert sorted(data["subjects"]) == [
        "blocking_check",
        "change_request",
        "clause",
        "event",
        "exposure_receipt",
        "permit",
        "recall_run",
        "site",
    ]
    empty = sorted(name for name in subjects.ADDRESSED_SLOTS if data[name] is None)
    assert empty == [], f"the seeded world leaves these addressed slots null: {empty}"


@pytest.mark.requires_cluster
def test_every_provenance_pointer_addresses_something_real(
    subjects_payload: dict[str, Any],
) -> None:
    """A chip beside nothing is worse than no chip. Same check the twelve reads get."""
    for entry in subjects_payload["provenance"]:
        assert entry["chip"] in envelope.PROVENANCE_CHIPS
        node: Any = subjects_payload["data"]
        for segment in entry["pointer"].lstrip("/").split("/"):
            if isinstance(node, list):
                assert segment.isdigit() and int(segment) < len(node), entry["pointer"]
                node = node[int(segment)]
            else:
                assert isinstance(node, dict) and segment in node, entry["pointer"]
                node = node[segment]


@pytest.mark.requires_cluster
def test_a_declared_parameter_it_does_not_have_is_a_400_naming_the_declared_set(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """``?site_code=OTHER`` must be refused, not ignored.

    A resource that quietly drops a filter has told the caller the filter was applied. This
    route declares no query parameter at all, so every one of them is undeclared, and the
    refusal names that.
    """
    dsn, _ = demo_database
    with _pointed_at(dsn):
        response = app.handler(_event("GET", "/v1/demo/subjects", {"site_code": "BLK-07"}))
    assert response["statusCode"] == 400, response["body"]
    body = json.loads(response["body"])
    assert body["error"]["resource"] == subjects.SUBJECTS_RESOURCE
    assert "site_code" in body["error"]["detail"]
    assert body["error"]["schema_id"] == subjects.SUBJECTS_SCHEMA_ID


# ── A database with the whole chain and no seed at all ──────────────────────────────


def _migrations_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _database_named(admin: str, database: str) -> str:
    parts = urlsplit(admin)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


@pytest.fixture(scope="session")
def unseeded_dsn(admin_dsn: str) -> str:
    """A database carrying the migration chain and NOT ONE SEEDED ROW.

    Built by applying the same files ``conftest`` applies, minus the seed step, and cached
    under the migrations' own fingerprint so a second run costs one probe. The adoption
    probe is a query, not a marker: a marker says the database was built and never says it
    is still usable, which is the failure this suite's main fixture documents at length.
    """
    name = f"w1_no_seed_{_migrations_fingerprint()}"
    dsn = _database_named(admin_dsn, name)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {name}")
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            row = conn.execute("SELECT count(*) FROM mainline.site").fetchone()
        if row is not None and int(row[0]) == 0:
            return dsn
        pytest.skip(f"{name} unexpectedly carries {row} site rows; refusing to empty it")
    except psycopg.Error:
        pass  # the chain has not been applied to this database yet

    from conftest import _apply_chain

    applied, failures = _apply_chain(dsn)
    assert not failures, f"{name}: {len(failures)} migrations did not apply: {failures[:3]}"
    assert applied > 0
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("SELECT count(*) FROM mainline.site").fetchone()
    assert row is not None and int(row[0]) == 0, "the unseeded database is not unseeded"
    return dsn


@pytest.mark.requires_cluster
def test_a_database_with_no_demo_seed_is_a_named_404(unseeded_dsn: str) -> None:
    """THE TEST THAT MAKES THE ROUTE HONEST.

    A subject index that answered 200 on an empty database would be answering with
    something it invented, and there is exactly one thing it could invent: the identifiers
    somebody remembered. So the empty case must be a refusal, it must name what it looked
    for, and it must name the seed files that would provide it. Anything less and the next
    reader repairs the 404 by hard-coding a row.
    """
    with _pointed_at(unseeded_dsn):
        response = app.handler(_event("GET", "/v1/demo/subjects"))

    assert response["statusCode"] == 404, response["body"]
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "notfound"
    assert body["error"]["resource"] == subjects.SUBJECTS_RESOURCE
    detail = body["error"]["detail"]
    assert "mainline.site" in detail
    assert "demo_world" in detail and "demo_permit" in detail
    # And nothing that looks like an answer came back with the refusal.
    assert _IDENTIFIER_SHAPED.search(response["body"]) is None, (
        "the 404 body carries an identifier-shaped string, which is the placeholder this "
        "route must never emit"
    )
