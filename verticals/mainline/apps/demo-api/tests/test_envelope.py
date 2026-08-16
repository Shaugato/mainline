# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The contract this API is held to, checked without a database.

Every test here answers one of three questions.

**Does this API still agree with the console?** ``console/src/data/resources.ts`` is the
single declaration of what exists — key, method, path template, contract ``$id``. Three
tests below re-parse that TypeScript and compare it with :data:`envelope.SCHEMA_IDS`,
:data:`reads.READS` and :data:`app.ROUTES`. They exist because the failure they catch is
silent: a payload naming a contract the console does not hold is refused at the client
with a message about forward compatibility, at deploy time, in front of a judge.

**Does the envelope builder refuse what the schema refuses?**
``envelope.schema.json`` couples ``staged`` and ``staged_note`` and closes the chip
vocabulary. Those are decidable in this process, and catching them here means the failure
names the read function instead of arriving as a diff of two JSON blobs.

**Is the deployment package still what the pyproject claims?** The dependency list is the
claim, and the last section of this file is the mechanism — in two halves, because the
claim has two subjects. One half imports every shipped module in a FRESH INTERPRETER and
reports the closure that came with them; the other reads the built zip and reports the
bytes. Both are compared against one list, :data:`BANNED_IMPORT_ROOTS`, which is held
identical to ``scripts/deploy/bundle_manifest.py``'s ``DEFAULT_FORBIDDEN``.

The fresh interpreter is not decoration and it is the whole repair. Until 2026-08-13 the
first half read ``sys.modules`` in the pytest process, and on 2026-08-13 ``testpaths``
grew ``verticals/*/apps/demo-api/tests`` — so for the first time this file shared a
process with the rest of the monorepo. ``mainline_agentkit`` imports ``pydantic``,
``mainline_mcp.client`` imports ``httpx``, and ``tests/deploy/test_cost_guard_responder``
imports ``boto3``; none of the three is in the deployment package, all three were in
``sys.modules``, and the test printed *the deployment package pulled in
['boto3', 'botocore', 'httpx', 'pydantic']* into a public CI log. That was a false
attribution, in the one lane whose red is defined to mean REGRESSION. A check whose
verdict is decided by something other than its subject proves nothing about its subject —
which is the same defect as a test that cannot disagree with its code, wearing the other
costume: this one could not AGREE with it.
"""

from __future__ import annotations

import ast
import datetime as _dt
import decimal
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import pytest
from mainline_demo_api import app, envelope, health, reads

from conftest import (
    CONTRACTS_DIR,
    REPO_ROOT,
    RESOURCES_TS,
    SchemaRegistry,
)

# ── The console's declaration, re-read rather than re-typed ─────────────────────────

_DECLARE = re.compile(
    r"declare\(\s*'(?P<key>[a-z_]+)',\s*'(?P<method>GET|POST)',\s*"
    r"'(?P<template>[^']+)',\s*`\$\{C\}(?P<schema>[^`]+)`",
    re.MULTILINE,
)


def _declared() -> list[dict[str, str]]:
    if not RESOURCES_TS.is_file():
        pytest.skip(
            f"{RESOURCES_TS} is absent, so this API's agreement with the console cannot be "
            "checked against the console's own declaration"
        )
    return [
        match.groupdict() for match in _DECLARE.finditer(RESOURCES_TS.read_text(encoding="utf-8"))
    ]


def _declared_query_params() -> dict[str, list[str]]:
    """The optional 7th argument of each ``declare(...)`` call, as a key → names map.

    Parsed by slicing the source between consecutive ``declare(`` occurrences rather than
    by one heroic regex: the 6th argument is a multi-line prose string containing commas,
    brackets and apostrophes, and a regex that survived all sixteen of those would be
    harder to trust than the thing it checks.
    """
    text = RESOURCES_TS.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(r"\bdeclare\(", text)]
    out: dict[str, list[str]] = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        block = text[start:end]
        key_match = re.search(r"declare\(\s*'([a-z_]+)'", block)
        if key_match is None:  # pragma: no cover - the regex above found the call
            continue
        array = re.search(r"\[\s*((?:'[a-z_]+'\s*,?\s*)+)\]", block)
        names = re.findall(r"'([a-z_]+)'", array.group(1)) if array else []
        out[key_match.group(1)] = names
    return out


def test_the_console_declares_twenty_resources() -> None:
    """Guards the parser itself: if the regex stops matching, every test below passes vacuously.

    Sixteen until 2026-08-14, when the console declared ``demo_gate_run`` and closed the
    gap that left ``POST /v1/demo/gate-run`` reachable by ``curl`` and not from the
    artefact a judge drives. That seventeenth resource is a POST, and the GET count stayed
    at twelve.

    Eighteen from 2026-08-15, when the console declared ``demo_subjects`` —
    ``GET /v1/demo/subjects``, the read that tells a screen which identifier to address.
    That one moves the GET count to thirteen.

    Twenty since 2026-08-16 and the split moves on BOTH sides: ``cr_blocking_checks`` is
    the fourteenth GET — the change request's obligations, which nothing could list while
    its ``open_blocking`` counter said one was open — and ``cr_gate_run`` is the sixth
    POST, the change request's gate run. The split is asserted line by line rather than
    folded into the total precisely so that a change which moved the total without moving
    the split is still visible here.
    """
    declared = _declared()
    assert len(declared) == 20, [entry["key"] for entry in declared]
    assert sum(1 for entry in declared if entry["method"] == "GET") == 14
    assert sum(1 for entry in declared if entry["method"] == "POST") == 6


def test_declared_parameters_match_the_console() -> None:
    """Path and query parameters, compared with ``resources.ts`` name for name.

    The console refuses to SEND an undeclared query parameter; :func:`reads._check_request`
    refuses to ACCEPT one, because the console is not the only thing that can reach a
    public URL and a silently-ignored ``?site_code=`` is how a caller comes to believe a
    filter was applied.
    """
    query_by_key = _declared_query_params()
    for entry in _declared():
        if entry["method"] != "GET":
            continue
        key = entry["key"]
        expected_path = tuple(re.findall(r"\{([a-z_]+)\}", entry["template"]))
        expected_query = tuple(query_by_key.get(key, ()))
        assert reads._DECLARED_PARAMS[key] == (expected_path, expected_query), key

    # Guards the query parser: two resources declare query parameters and the rest declare
    # none, so an empty result everywhere would make the comparison above vacuous.
    assert query_by_key["clause_ancestry"] == ["as_of"]
    assert query_by_key["ledger"] == ["site_code", "from_seq", "to_seq"]


def test_schema_ids_match_the_console_declaration() -> None:
    """``envelope.schema_id`` must be the EXACT ``$id`` the console holds, for all twenty.

    ``finishExchange`` compares them as strings and refuses a mismatch outright:
    *a payload that names a contract we do not hold is not forward compatibility; it is
    an unverifiable claim.* Seven of the twenty name a file whose stem is not their key,
    and one of those seven — ``cr_blocking_checks`` — names the SAME file as
    ``blocking_checks``, which no rule from a key to a stem can produce at all. So this
    cannot be a derivation and has to be a comparison.

    The equality is two-directional and stays that way. ``demo_gate_run`` joined both
    sides on 2026-08-14 and ``cr_gate_run`` on 2026-08-16; those two are the entries whose
    contracts this package does not emit through :func:`envelope.read_envelope` —
    ``gate_run.py`` and ``cr_gate_run.py`` stamp their own ``$id`` onto their own payloads
    — so a reader tempted to drop either from :data:`envelope.SCHEMA_IDS` on the grounds
    that "nothing uses it" should read ``app.py``'s 501 branch first, and
    ``tests/test_routes_gate_run.py::test_the_transcribed_contract_id_is_the_one_the_handler_actually_stamps``
    second.
    """
    expected = {entry["key"]: f"{envelope.CONTRACT_BASE}{entry['schema']}" for entry in _declared()}
    assert expected == envelope.SCHEMA_IDS


def test_two_keys_may_name_one_contract_and_that_is_the_polymorphism() -> None:
    """``blocking_checks`` and ``cr_blocking_checks`` name ONE ``$id``, deliberately.

    ``blocking-check.schema.json``'s ``data`` requires ``subject_kind``, ``subject_id``,
    ``gate_epoch`` and ``checks``; ``permit_id`` is not in that required set, and
    ``common.schema.json#/$defs/subject_kind`` is the closed pair
    ``permit | change_request``. The contract was authored for both gated subjects, so
    reusing it is the contract being used as written rather than a second file being
    avoided — and the two properties this test pins are the ones that make that safe:
    ``subject_kind`` is a closed pair the CR value is IN, and the required set names no
    permit.

    ``finishExchange`` looks the ``$id`` up by the REQUESTED key, so two keys may share a
    contract and one key may never carry two ids.
    """
    shared = envelope.SCHEMA_IDS["blocking_checks"]
    assert envelope.SCHEMA_IDS["cr_blocking_checks"] == shared
    assert shared == f"{envelope.CONTRACT_BASE}blocking-check.schema.json"

    contract = json.loads((CONTRACTS_DIR / "blocking-check.schema.json").read_text("utf-8"))
    data_schema = next(
        branch["properties"]["data"]
        for branch in contract["allOf"]
        if "properties" in branch and "data" in branch["properties"]
    )
    assert "permit_id" not in data_schema["required"], data_schema["required"]
    assert set(data_schema["required"]) == {"subject_kind", "subject_id", "gate_epoch", "checks"}

    common = json.loads((CONTRACTS_DIR / "common.schema.json").read_text("utf-8"))
    assert common["$defs"]["subject_kind"]["enum"] == ["permit", "change_request"]


def test_every_contract_id_resolves_to_a_committed_file() -> None:
    """Each ``$id`` this API emits must be a file on disk under ``console/contracts/``."""
    held = {
        json.loads(path.read_text(encoding="utf-8"))["$id"]
        for path in CONTRACTS_DIR.glob("*.schema.json")
    }
    missing = sorted(set(envelope.SCHEMA_IDS.values()) - held)
    assert not missing, f"emitted schema ids with no contract file: {missing}"


def test_reads_implements_exactly_the_declared_gets() -> None:
    """Every GET key the console declares, no more and no fewer. W4 owns the six POSTs.

    Twelve until 2026-08-15, thirteen with ``demo_subjects``, fourteen since 2026-08-16
    and ``cr_blocking_checks``. The assertion is deliberately NOT a count: it is the set,
    so a GET that this API does not implement, and an implementation the console does not
    declare, both fail here and both name the key.
    """
    gets = {entry["key"] for entry in _declared() if entry["method"] == "GET"}
    assert set(reads.READS) == gets


def test_routes_match_the_console_path_templates() -> None:
    """Every declared template is routable and every routable template is declared.

    ``POST /v1/demo/gate-run`` was routed by this API and NOT declared by the console
    until **2026-08-14**. It was absent from ``app._routes()`` until 2026-08-11 — which is
    why ``evidence/deploy/acceptance.json`` records *"POST /v1/demo/gate-run (run 1)
    returned 404, expected 200"* — and absent from ``resources.ts`` for three days after
    that, which is why the deployed console rendered *"POST /v1/demo/gate-run is not
    addressable from this console"* in front of the founder.

    While that was true this test pinned the exception as an EXACT set difference,
    ``routed - declared == {demo_route}``, so a *second* undeclared route still failed.
    With the console declaring it the exception was collapsed, not enlarged: the
    assertion became plain set equality, which permits no undeclared route at all.

    **2026-08-15 added an eighteenth row to both tables in the same wave:**
    ``GET /v1/demo/subjects``, the demo's subject index, which exists because the console
    had no way to ASK which subjects a database carries and so shipped identifiers
    (``BLK-07``, a clause and a commit) that the deployed kernel answers 404 for. It is
    routed here, declared there, and implemented in ``reads.READS`` — so the assertion
    stays plain set equality, which permits no undeclared route and no unrouted
    declaration. That is the strongest form and nothing in this wave weakened it.

    **2026-08-16 added the nineteenth and twentieth the same way**, and they are the
    change request's: ``GET /v1/change-requests/{cr_id}/blocking-checks`` lists the
    obligations its ``open_blocking`` counter was counting with nothing able to name them,
    and ``POST /v1/demo/cr-gate-run`` drives the CR gate inside a transaction that is
    rolled back. Both landed on both sides in one wave; the comparison is still plain set
    equality.

    The two set assertions are joined by a COUNT over the list, because ``app.ROUTES`` is a
    list and the sets above cannot see a duplicate in it: two identical ``Route`` rows
    collapse into one member and every assertion below would still hold while ``route()``
    resolved to whichever came first. 20 declared = 20 routed, re-derived here rather than
    remembered — ``test_the_console_declares_twenty_resources`` pins the 20.
    """
    demo_route = ("POST", "/v1/demo/gate-run")
    subjects_route = ("GET", "/v1/demo/subjects")
    cr_checks_route = ("GET", "/v1/change-requests/{cr_id}/blocking-checks")
    cr_demo_route = ("POST", "/v1/demo/cr-gate-run")
    declared = {(entry["method"], entry["template"]) for entry in _declared()}
    routed = {(route.method, route.template) for route in app.ROUTES}
    assert declared - routed == set(), f"declared but not routed: {sorted(declared - routed)}"
    assert routed - declared == set(), f"routed but not declared: {sorted(routed - declared)}"
    assert declared == routed
    assert demo_route in declared, "the console has stopped declaring the demo endpoint"
    assert subjects_route in declared, "the console has stopped declaring the subject index"
    assert cr_checks_route in declared, "the console has stopped declaring the CR obligations"
    assert cr_demo_route in declared, "the console has stopped declaring the CR gate run"
    pairs = [(route.method, route.template) for route in app.ROUTES]
    duplicated = sorted(pair for pair in routed if pairs.count(pair) > 1)
    assert len(pairs) == len(declared) == 20, (
        f"app.ROUTES holds {len(pairs)} rows for {len(routed)} distinct (method, template) "
        f"pairs; a duplicate is unreachable and hides the row it shadows: {duplicated}"
    )


@pytest.mark.parametrize("entry", _declared(), ids=lambda entry: entry["key"])
def test_each_declared_template_resolves_to_its_own_key(entry: dict[str, str]) -> None:
    """Interpolating a template's parameters must route back to the key that declared it."""
    path = re.sub(r"\{[a-z_]+\}", "0f8f6e94-1a2b-4c3d-8e5f-6a7b8c9d0e1f", entry["template"])
    matched, params, _ = app.route(entry["method"], path)
    assert matched is not None, f"{entry['method']} {path} routed nowhere"
    assert matched.key == entry["key"]
    assert set(params) == set(re.findall(r"\{([a-z_]+)\}", entry["template"]))


# ── The envelope builder ────────────────────────────────────────────────────────────


def _now() -> _dt.datetime:
    return _dt.datetime(2026, 8, 10, 2, 30, 45, 123456, tzinfo=_dt.UTC)


def test_read_envelope_carries_the_version_the_reader_demands() -> None:
    built = envelope.read_envelope("permit", {"x": 1}, server_date=_now())
    assert built["envelope_version"] == 1
    assert built["resource"] == "permit"
    assert built["schema_id"] == envelope.SCHEMA_IDS["permit"]
    assert built["staged"] is False
    assert built["staged_note"] is None
    assert built["server_date"] == "2026-08-10T02:30:45.123456Z"
    # observed_at defaults to server_date: for a read served in one transaction those are
    # the same instant, and a second clock reading would imply precision we do not have.
    assert built["observed_at"] == built["server_date"]


def test_staged_true_without_a_note_is_refused() -> None:
    with pytest.raises(envelope.EnvelopeError, match="staged=true with no note"):
        envelope.read_envelope("propagation", {}, server_date=_now(), staged=True)


def test_a_note_beside_a_false_flag_is_refused() -> None:
    with pytest.raises(envelope.EnvelopeError, match="staged=false but carries a staged_note"):
        envelope.read_envelope("permit", {}, server_date=_now(), staged_note="because")


def test_an_unknown_resource_names_no_contract_and_is_refused() -> None:
    with pytest.raises(envelope.EnvelopeError, match="names no contract"):
        envelope.read_envelope("permits", {}, server_date=_now())


def test_the_chip_vocabulary_is_closed() -> None:
    with pytest.raises(envelope.EnvelopeError, match="is not one of"):
        envelope.Provenance().add("/x", "db:table")  # type: ignore[arg-type]


def test_a_provenance_pointer_must_be_a_json_pointer() -> None:
    with pytest.raises(envelope.EnvelopeError, match="RFC 6901"):
        envelope.Provenance().add("counters", "db:column")


def test_the_first_chip_for_a_pointer_wins() -> None:
    """So a read can claim the precise chip before the sweeping one and keep the precise one."""
    prov = envelope.Provenance().add("/checks/0/open", "derived").add("/checks/0/open", "db:column")
    assert prov.as_list() == [{"pointer": "/checks/0/open", "chip": "derived"}]


def test_provenance_stops_at_the_contract_cap_and_counts_what_it_dropped() -> None:
    """256 is ``field_provenance.maxItems``. Past it a pointer gets NO chip, by design."""
    prov = envelope.Provenance()
    for index in range(300):
        prov.add(f"/checks/{index}", "db:column")
    assert len(prov) == envelope.PROVENANCE_CAP
    assert prov.dropped == 300 - envelope.PROVENANCE_CAP


def test_rfc3339_renders_utc_with_a_literal_z() -> None:
    naive = _dt.datetime(2026, 8, 10, 2, 30, 45)  # noqa: DTZ001 - a naive datetime IS the input under test
    aware = _dt.datetime(2026, 8, 10, 12, 30, 45, tzinfo=_dt.timezone(_dt.timedelta(hours=10)))
    assert envelope.rfc3339(naive) == "2026-08-10T02:30:45Z"
    assert envelope.rfc3339(aware) == "2026-08-10T02:30:45Z"


def test_jsonable_renders_a_decimal_exactly_and_not_as_a_float() -> None:
    """``exposure_receipt.issued_hlc`` is a NUMERIC the contract types as a string."""
    value = decimal.Decimal("12345678901234567890.000000001")
    assert envelope.jsonable(value) == "12345678901234567890.000000001"
    assert envelope.jsonable(uuid.UUID(int=1)) == "00000000-0000-0000-0000-000000000001"
    assert envelope.jsonable(b"\xde\xad\xbe\xef") == "deadbeef"
    assert envelope.jsonable([_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC)]) == ["2026-01-01T00:00:00Z"]
    assert envelope.jsonable({"a": None}) == {"a": None}


def test_jsonable_refuses_a_type_nobody_anticipated() -> None:
    with pytest.raises(envelope.EnvelopeError, match="no JSON rendering"):
        envelope.jsonable(object())


def test_the_envelope_of_an_empty_read_satisfies_the_shared_contract(
    registry: SchemaRegistry,
) -> None:
    """Checked against ``envelope.schema.json`` itself, which every resource contract ``$ref``s."""
    built = envelope.read_envelope(
        "permit",
        {"anything": True},
        server_date=_now(),
        provenance=envelope.Provenance().add("/anything", "derived"),
        statement_refs=[envelope.statement_ref("table", "mainline.permit", text="SELECT 1")],
    )
    errors = registry.validate(f"{envelope.CONTRACT_BASE}envelope.schema.json", built)
    assert errors == []


# ── The router ──────────────────────────────────────────────────────────────────────


def test_a_path_parameter_cannot_contain_a_separator() -> None:
    """The console refuses to SEND one; this API refuses to accept one from anybody else."""
    matched, _, _ = app.route("GET", "/v1/permits/a/b")
    assert matched is None


def test_a_wrong_method_on_a_real_path_is_405_not_404() -> None:
    matched, _, other = app.route("GET", "/v1/permits/0f8f6e94-1a2b-4c3d-8e5f-6a7b8c9d0e1f/merge")
    assert matched is None
    assert other is True

    response = app.handler(
        {
            "version": "2.0",
            "rawPath": "/v1/permits/0f8f6e94-1a2b-4c3d-8e5f-6a7b8c9d0e1f/merge",
            "requestContext": {"stage": "$default", "http": {"method": "GET", "path": "/x"}},
        }
    )
    assert response["statusCode"] == 405
    assert json.loads(response["body"])["error"]["allow"] == ["POST"]


def test_an_undeclared_path_is_404_and_lists_what_is_declared() -> None:
    response = app.handler({"version": "2.0", "rawPath": "/v1/nope"})
    assert response["statusCode"] == 404
    body = json.loads(response["body"])
    assert body["error"]["kind"] == "no_route"
    assert "/v1/permits/{permit_id}" in body["error"]["declared"]


def test_a_stage_prefix_is_stripped_only_when_the_stage_is_named() -> None:
    named = {
        "version": "2.0",
        "rawPath": "/prod/v1/ledger",
        "requestContext": {"stage": "prod", "http": {"method": "GET", "path": "/prod/v1/ledger"}},
    }
    default = {
        "version": "2.0",
        "rawPath": "/v1/ledger",
        "requestContext": {"stage": "$default", "http": {"method": "GET", "path": "/v1/ledger"}},
    }
    assert app._path(named) == "/v1/ledger"
    assert app._path(default) == "/v1/ledger"


def test_a_post_answers_501_naming_the_module_that_owes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The read surface ships independently of the write surface. That is the mechanism.

    W4's ``transitions`` module is present in this working tree, so the absence has to be
    simulated — and simulating it takes BOTH steps below. ``from . import transitions``
    consults the package attribute first and only falls through to an import when the
    attribute is missing, so clearing ``sys.modules`` alone would leave the real module
    reachable and this test would silently exercise W4's code instead of the 501 path.
    """
    import mainline_demo_api

    monkeypatch.setenv("MAINLINE_DSN", "postgresql://root@127.0.0.1:1/none?sslmode=disable")
    from mainline_demo_api import db as demo_db

    demo_db.reset_dsn_cache()
    monkeypatch.setattr(demo_db, "connection", lambda **_: None)
    monkeypatch.delattr(mainline_demo_api, "transitions", raising=False)
    monkeypatch.setitem(sys.modules, "mainline_demo_api.transitions", None)

    response = app.handler(
        {
            "version": "2.0",
            "rawPath": "/v1/permits/0f8f6e94-1a2b-4c3d-8e5f-6a7b8c9d0e1f/merge",
            "requestContext": {"stage": "$default", "http": {"method": "POST"}},
            "body": "{}",
        }
    )
    demo_db.reset_dsn_cache()
    assert response["statusCode"] == 501
    body = json.loads(response["body"])
    assert "mainline_demo_api.transitions" in body["error"]["detail"]
    assert body["error"]["schema_id"] == envelope.SCHEMA_IDS["merge_permit"]


# ── Health, with no database at all ─────────────────────────────────────────────────


def test_health_is_503_when_no_dsn_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nobody told this function where the database is, and it says exactly that."""
    from mainline_demo_api import db as demo_db

    monkeypatch.delenv("MAINLINE_DSN", raising=False)
    monkeypatch.delenv("MAINLINE_DSN_PARAM", raising=False)
    demo_db.reset_dsn_cache()

    status, body = health.health()
    assert status == 503
    assert body["ok"] is False
    assert body["reason"] == "dsn_unset"
    assert "$MAINLINE_DSN" in body["detail"]
    assert body["schema_fingerprint"] is None


def test_health_is_503_when_the_database_does_not_answer() -> None:
    """And it costs the two seconds the DSN asked for, not the ten the module prefers.

    This node was the slowest in the suite — 10.05 s of a 50.9 s run — and every one of
    those seconds was ``db.connection()``: ``HEALTH_STATEMENT`` costs 0.003 s and nothing
    in ``health.py`` is implicated. The DSN below has always asked for
    ``connect_timeout=2``; ``db._open`` passed ``connect_timeout=10`` as a **keyword**,
    which outranks a DSN's query string, so it waited 10. Measured 2026-08-14: 10.055 s
    before, 2.033 s after.

    The timing line is the behavioural half of that control and it is honest about its
    reach: it bites on a host where ``127.0.0.1:1`` does not answer promptly (this one —
    the address refuses only after ~2 s under the Windows loopback stack), and passes
    without proving anything on a host that refuses instantly. The half that is
    deterministic everywhere is
    :func:`test_a_stated_connect_timeout_is_supplied_never_imposed`, which reads the
    budget libpq will actually apply instead of timing it.
    """
    from mainline_demo_api import db as demo_db

    demo_db.reset_dsn_cache()
    status, body = health.health(
        dsn="postgresql://root@127.0.0.1:1/none?sslmode=disable&connect_timeout=2"
    )
    demo_db.reset_dsn_cache()
    assert status == 503
    assert body["ok"] is False
    assert body["reason"] == "unreachable"
    # The DSN appears in the body with its password removed, never with it.
    assert "***" not in body["dsn"] or "@" in body["dsn"]
    assert body["seconds"] < demo_db.CONNECT_TIMEOUT_SECONDS, (
        f"the DSN asked for connect_timeout=2 and this connect took {body['seconds']}s. A "
        f"keyword argument in db._open outranks the DSN, so a caller that asks for a "
        f"shorter budget than {demo_db.CONNECT_TIMEOUT_SECONDS}s gets the module's instead"
    )


# ── The connect path: two mechanisms, two independent controls ──────────────────────
#
# Neither of these opens a database. They open loopback sockets, which is the subject:
# `/v1/health` took 10.1 s against a database that was HEALTHY and 0.003 s of it was the
# query. See `docs/diagnosis/health-connect-path.md` for the decomposition.


def _capture_open(dsn: str) -> dict[str, Any]:
    """Everything ``db._open`` hands psycopg for *dsn*, without opening a connection.

    The address selection underneath still runs for real — real sockets, real
    ``getaddrinfo`` (or the one the caller planted) — so what is faked here is only the
    driver call at the end, which is the one thing that would need a server.

    Its own ``MonkeyPatch`` context, deliberately: the callers below set environment
    variables through the fixture's, and an ``undo()`` here would roll those back too.
    Measured while writing this — ``$PGCONNECT_TIMEOUT=4`` was silently restored to the
    repository-root conftest's 5 between being set and being read.
    """
    import psycopg
    from mainline_demo_api import db as demo_db

    seen: dict[str, Any] = {}
    sentinel = object()

    def fake_connect(conninfo: str = "", **kwargs: Any) -> Any:
        seen.clear()
        seen.update(conninfo=conninfo, **kwargs)
        return sentinel

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(psycopg, "connect", fake_connect)
        assert demo_db._open(dsn) is sentinel
    return seen


def _effective_connect_timeout(seen: dict[str, Any]) -> int:
    """The budget libpq will apply to the call :func:`_capture_open` recorded.

    Computed with psycopg's own ``timeout_from_conninfo`` over the conninfo string merged
    with the keyword arguments, in psycopg's own precedence — keywords over the string —
    so this cannot drift away from what the driver will do with the same pair.
    """
    from psycopg.conninfo import conninfo_to_dict, timeout_from_conninfo

    params = dict(conninfo_to_dict(seen["conninfo"]))
    for key in ("connect_timeout", "hostaddr", "application_name"):
        if key in seen:
            params[key] = seen[key]
    return timeout_from_conninfo(params)


def test_a_stated_connect_timeout_is_supplied_never_imposed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mechanism (b). ``db.CONNECT_TIMEOUT_SECONDS`` is a default, not a policy.

    ``_open`` used to pass it as a keyword argument, and a keyword outranks both the DSN's
    query string and ``$PGCONNECT_TIMEOUT``. Two consequences, both measured: the 503 test
    above asked for 2 s and waited 10, and the repository-root ``conftest.py`` — which
    exports ``PGCONNECT_TIMEOUT=5`` for the express purpose that no fixture can hang — was
    overruled by a module that had never heard of it.

    The three readings below must be three different numbers. Reverting the fix makes all
    three 10, so the first assertion fails; a fix that removed the keyword without
    supplying anything makes the third 130 (psycopg's own default), so the third fails.
    Both wrong answers are excluded, which is what makes this a control rather than a
    demonstration.
    """
    from mainline_demo_api import db as demo_db

    monkeypatch.delenv(demo_db.CONNECT_TIMEOUT_ENV, raising=False)
    base = "postgresql://root@127.0.0.1:1/none?sslmode=disable"

    stated = _effective_connect_timeout(_capture_open(f"{base}&connect_timeout=2"))
    assert stated == 2, (
        "the DSN asked for a 2 s connect budget and libpq will be given "
        f"{stated} s. No caller can choose a budget shorter than this module's"
    )

    monkeypatch.setenv(demo_db.CONNECT_TIMEOUT_ENV, "4")
    from_env = _effective_connect_timeout(_capture_open(base))
    monkeypatch.delenv(demo_db.CONNECT_TIMEOUT_ENV, raising=False)
    assert from_env == 4, f"$PGCONNECT_TIMEOUT said 4 and libpq will be given {from_env}"

    silent = _effective_connect_timeout(_capture_open(base))
    assert silent == demo_db.CONNECT_TIMEOUT_SECONDS, (
        "nobody stated a budget, so this module must supply its own. Leaving it unset "
        f"hands libpq psycopg's 130 s default, which is longer than the Lambda's own "
        f"timeout and turns 'unreachable' into 'the function timed out'. Got {silent}"
    )
    assert len({stated, from_env, silent}) == 3, (
        f"the three budgets read the same source: {stated}, {from_env}, {silent}"
    )


def _plant_resolution(
    monkeypatch: pytest.MonkeyPatch, addresses: tuple[str, ...], port: int
) -> None:
    """Make ``getaddrinfo`` answer *addresses* for any host, in the order given.

    psycopg 3.3 resolves the host in Python (``_conninfo_attempts._resolve_hostnames``
    calls ``socket.getaddrinfo``) and yields one connection attempt per answer, so
    planting the resolver is what puts a known dead address in front of a known live one.
    Everything downstream — the race, the sockets, the choice — is the real thing.
    """
    import socket as _socket

    def fake_getaddrinfo(
        _host: object, _port: object, *_args: object, **_kwargs: object
    ) -> list[Any]:
        return [
            (
                _socket.AF_INET6 if ":" in address else _socket.AF_INET,
                _socket.SOCK_STREAM,
                _socket.IPPROTO_TCP,
                "",
                (address, port, 0, 0) if ":" in address else (address, port),
            )
            for address in addresses
        ]

    monkeypatch.setattr(_socket, "getaddrinfo", fake_getaddrinfo)


def test_a_dead_address_is_not_paid_for_one_whole_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mechanism (a). The budget bounds the WHOLE connect, not each address separately.

    ``getaddrinfo('localhost', 26257)`` answers ``[::1, 127.0.0.1]`` and the pinned
    container publishes IPv4 only. psycopg applies ``connect_timeout`` per attempt, so
    every cold connect waited out the entire budget against the dead one and then
    succeeded on the live one in half a millisecond. Measured: ``localhost`` 10.124 s,
    ``127.0.0.1`` 0.017 s, ``localhost:1`` — two dead addresses — 20.081 s, which is past
    the Lambda's own timeout.

    The live address here is a listening socket this test owns, so the assertion does not
    depend on a database, on the container, or on which family this host prefers. The dead
    one is the same port on the other family, where nothing is bound.

    Reverting the fix removes ``hostaddr`` from what ``_open`` passes, and every assertion
    below fails. Planting the live address FIRST and getting the same answer is what
    separates "chose the one that answers" from "always returns the second".
    """
    import socket as _socket

    from mainline_demo_api import db as demo_db

    with _socket.create_server(("127.0.0.1", 0)) as listener:
        port = int(listener.getsockname()[1])
        dsn = f"postgresql://root@two-families.invalid:{port}/none?sslmode=disable"

        _plant_resolution(monkeypatch, ("::1", "127.0.0.1"), port)
        from psycopg.conninfo import conninfo_to_dict

        params = dict(conninfo_to_dict(dsn))
        assert demo_db._targets(params) == [("::1", port), ("127.0.0.1", port)], (
            "the addresses raced must be the ones psycopg would have walked one timeout at "
            "a time, taken from its own conninfo_attempts and not resolved a second time"
        )
        dead_first = _capture_open(dsn)
        _plant_resolution(monkeypatch, ("127.0.0.1", "::1"), port)
        live_first = _capture_open(dsn)

    assert dead_first.get("hostaddr") == "127.0.0.1", (
        "the dead address was handed to psycopg, which will spend the whole connect budget "
        f"on it before falling back: {dead_first}"
    )
    assert live_first.get("hostaddr") == "127.0.0.1", live_first
    # The host name is left in place beside the address it resolved to, because that is
    # what `sslmode=verify-full` matches the certificate against and what SCRAM salts. An
    # address that replaced the name would silently disable the Cloud DSN's verification.
    assert "two-families.invalid" in dead_first["conninfo"]


def test_one_address_is_left_alone_and_no_address_is_a_bounded_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two edges of mechanism (a): nothing to choose, and nothing that answers.

    **Nothing to choose.** A host that resolves to one address gets no probe at all. That
    is not an optimisation detail — the probe costs one TCP round trip, and the deployed
    Cloud DSN pays it on every cold start if it is levied unconditionally. Where there is
    only one address the budget already bounds the whole connect, so there is nothing to
    buy with it.

    **Nothing that answers.** The budget is a TOTAL. An earlier draft of the fix fell
    through to psycopg when the race found nobody home, and ``localhost:1`` then cost
    22.1 s — 2.1 s to learn both loopback addresses were dead, then 20 s for psycopg to
    learn it again, ten seconds per address. Worse than the 20.1 s defect. So this case
    raises here, naming every address, and the error is the evidence that it did.
    """
    import socket as _socket

    import psycopg
    from mainline_demo_api import db as demo_db
    from psycopg.conninfo import conninfo_to_dict

    with _socket.create_server(("127.0.0.1", 0)) as probe:
        dead_port = int(probe.getsockname()[1])
    # `probe` is closed, so nothing is bound to `dead_port` on either family.

    single = f"postgresql://root@127.0.0.1:{dead_port}/none?sslmode=disable&connect_timeout=2"
    assert demo_db._targets(dict(conninfo_to_dict(single))) == [], (
        "an address literal resolves to one attempt; there is nothing to race and nothing "
        "to gain from a probe"
    )
    assert "hostaddr" not in _capture_open(single)

    _plant_resolution(monkeypatch, ("::1", "127.0.0.1"), dead_port)
    both_dead = (
        f"postgresql://root@two-families.invalid:{dead_port}/none?sslmode=disable&connect_timeout=2"
    )
    with pytest.raises(psycopg.OperationalError) as caught:
        demo_db._open(both_dead)
    message = str(caught.value)
    assert "::1" in message and "127.0.0.1" in message, message
    assert "within 2s" in message, (
        f"the failure must quote the budget the DSN asked for, not the module's: {message}"
    )
    assert "two-families.invalid" in message
    # A DSN carries the `mainline-sql` password. The diagnosis names the host, the port and
    # the addresses, and never the string it was read out of.
    assert "root@" not in message and "sslmode" not in message, message


# ── The one AWS-touching path, exercised without AWS ────────────────────────────────


class _FakeResponse:
    """Just enough of an ``http.client.HTTPResponse`` for :func:`urllib.request.urlopen`."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_the_ssm_call_is_sigv4_signed_and_the_value_is_cached_not_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`db.py` signs its one GetParameter with hashlib and hmac, and never has boto3.

    Three things are asserted, and all three would otherwise only ever be exercised in
    production against a live endpoint:

    * the request is a SigV4 ``POST /`` to the regional SSM endpoint with the JSON 1.1
      target header, and the ``Authorization`` header carries the credential scope,
      the signed-header list and a 64-hex signature;
    * the secret is fetched ONCE per execution environment — a second `resolve_dsn()`
      must not open a second socket;
    * the DSN never reaches a log record.
    """
    from mainline_demo_api import db as demo_db

    monkeypatch.delenv("MAINLINE_DSN", raising=False)
    monkeypatch.setenv("MAINLINE_DSN_PARAM", "/mainline/demo/dsn")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/EXAMPLEKEY")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "FQoGZXIvYXdzEXAMPLE")
    demo_db.reset_dsn_cache()

    secret = "postgresql://mainline-sql:hunter2@host.aws-ap-southeast-1.cockroachlabs.cloud:26257/defaultdb"
    seen: list[Any] = []

    def fake_urlopen(request: Any, timeout: float | None = None) -> _FakeResponse:
        seen.append(request)
        assert timeout == demo_db._SSM_TIMEOUT_SECONDS, (
            "the SSM call must carry a timeout: a Lambda that blocks on a secret store "
            "reports itself as a function timeout, which sends the reader to the wrong place"
        )
        return _FakeResponse(json.dumps({"Parameter": {"Value": secret}}).encode("utf-8"))

    monkeypatch.setattr(demo_db.urllib.request, "urlopen", fake_urlopen)

    with caplog.at_level("DEBUG"):
        assert demo_db.resolve_dsn() == secret
        assert demo_db.resolve_dsn() == secret  # cached: no second socket

    assert len(seen) == 1, "the secret was fetched more than once per execution environment"
    request = seen[0]
    assert request.full_url == "https://ssm.ap-southeast-1.amazonaws.com/"
    assert request.method == "POST"
    assert request.headers["X-amz-target"] == "AmazonSSM.GetParameter"
    assert request.headers["X-amz-security-token"] == "FQoGZXIvYXdzEXAMPLE"
    assert json.loads(request.data) == {"Name": "/mainline/demo/dsn", "WithDecryption": True}

    authorization = request.headers["Authorization"]
    assert authorization.startswith("AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/")
    assert "/ap-southeast-1/ssm/aws4_request" in authorization
    assert (
        "SignedHeaders=content-type;host;x-amz-date;x-amz-security-token;x-amz-target"
        in authorization
    )
    signature = authorization.rsplit("Signature=", 1)[1]
    assert len(signature) == 64 and int(signature, 16) >= 0

    assert demo_db.dsn_source() == "ssm:/mainline/demo/dsn@ap-southeast-1"
    assert "hunter2" not in caplog.text
    assert "hunter2" not in demo_db.dsn_source()
    demo_db.reset_dsn_cache()


def test_an_unsigned_environment_says_so_rather_than_failing_at_the_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mainline_demo_api import db as demo_db

    monkeypatch.delenv("MAINLINE_DSN", raising=False)
    monkeypatch.setenv("MAINLINE_DSN_PARAM", "/mainline/demo/dsn")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    demo_db.reset_dsn_cache()

    with pytest.raises(demo_db.DsnUnavailable, match="cannot be signed"):
        demo_db.resolve_dsn()

    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
    demo_db.reset_dsn_cache()
    with pytest.raises(demo_db.DsnUnavailable, match="AWS_REGION"):
        demo_db.resolve_dsn()
    demo_db.reset_dsn_cache()


def test_redact_removes_the_password() -> None:
    from mainline_demo_api import db as demo_db

    assert (
        demo_db.redact("postgresql://mainline-sql:hunter2@host:26257/defaultdb?sslmode=verify-full")
        == "postgresql://mainline-sql:***@host:26257/defaultdb?sslmode=verify-full"
    )
    assert "hunter2" not in demo_db.redact("postgresql://u:hunter2@h/db")


# ── The deployment package is what the pyproject says it is ─────────────────────────


#: The twelve roots ``pyproject.toml``'s dependency list excludes: six web frameworks and
#: the Lambda adapter, the AWS SDK and its core, and the three HTTP clients.
#:
#: There is no HTTP server in this artefact and there is no AWS SDK. A Lambda invocation
#: is already a function call with a dict argument, and ``db.py`` signs its one SSM call
#: with :mod:`hashlib` and :mod:`hmac` so the package's behaviour does not depend on which
#: boto3 the runtime image happens to ship this month.
BANNED_IMPORT_ROOTS = (
    "aiohttp",
    "boto3",
    "botocore",
    "django",
    "fastapi",
    "flask",
    "httpx",
    "mangum",
    "pydantic",
    "requests",
    "starlette",
    "uvicorn",
)

#: Run in a child interpreter. It discovers the shipped modules rather than listing them,
#: so a module added to the package next week is measured without anybody remembering to
#: add it here, and it reports what it imported so the caller can tell an empty banned
#: list from an empty run.
_CLOSURE_PROBE = """\
import importlib, json, pkgutil, sys

import mainline_demo_api as package

shipped = sorted(module.name for module in pkgutil.iter_modules(package.__path__))
for name in shipped:
    importlib.import_module("mainline_demo_api." + name)

stdlib = set(sys.stdlib_module_names)
json.dump(
    {
        "shipped": shipped,
        "third_party": sorted(
            {
                name.split(".")[0]
                for name in sys.modules
                if name.split(".")[0] not in stdlib
                and not name.startswith("_")
                and name.split(".")[0] != "mainline_demo_api"
            }
        ),
    },
    sys.stdout,
)
"""


def _import_closure() -> dict[str, list[str]]:
    """Import every shipped module in a FRESH interpreter and report what came with it.

    A subprocess, and the subprocess IS the assertion. ``sys.modules`` is a process
    global that every other test in the session writes to, so read in this process it
    answers "what has anything imported", not "what does this package import" — see this
    module's docstring for the false attribution that produced.

    The child is pointed at the package's own source root through ``PYTHONPATH`` and run
    from a temporary directory, so neither the repository root nor the tests directory is
    on its ``sys.path``: the closure it measures is the one a Lambda gets, where the zip
    root is the only thing on the path besides the runtime.
    """
    source_root = Path(app.__file__).resolve().parent.parent
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source_root)
    # Fixed argv, this interpreter, no shell. `S603` is already off for tests.
    completed = subprocess.run(
        [sys.executable, "-c", _CLOSURE_PROBE],
        capture_output=True,
        text=True,
        cwd=tempfile.gettempdir(),
        env=environment,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, (
        f"the import-closure probe exited {completed.returncode}, so it measured nothing "
        f"and the empty result below would be a vacuous pass.\n{completed.stderr}"
    )
    return json.loads(completed.stdout)


def test_no_web_framework_or_aws_sdk_is_imported() -> None:
    """The closure half of the claim: importing the whole package reaches only psycopg.

    Every module the zip ships is imported, not just the read spine, because the runtime
    can reach any of them — ``app.handler`` reaches ``transitions`` and ``gate_run`` on
    the first POST — and a dependency that arrives through the write surface is in the
    package exactly as much as one that arrives through ``reads``.
    """
    closure = _import_closure()
    third_party = closure["third_party"]

    present = sorted(root for root in BANNED_IMPORT_ROOTS if root in third_party)
    assert present == [], (
        f"the deployment package pulled in {present}. Importing the {len(closure['shipped'])} "
        f"shipped modules in a fresh interpreter reached {third_party}"
    )

    # Anti-vacuity, in both directions a silent pass could arrive from.
    #
    # `psycopg` is the positive control: it enters the closure only through `db.py`, so
    # its presence proves the probe both ran the imports and can SEE a third-party root.
    # Without it an empty `present` would be indistinguishable from a probe that imported
    # nothing at all -- which is precisely how the assertion this replaced managed to be
    # green when run alone and red in the suite while the package never changed.
    assert "psycopg" in third_party, (
        f"the probe reached no driver, so it cannot have imported db.py: {third_party}"
    )
    assert {"app", "db", "envelope", "health", "reads"} <= set(closure["shipped"]), (
        f"module discovery missed part of the package: {closure['shipped']}"
    )


# ── ... and the same claim about the bytes, not about the imports ───────────────────

_BUNDLE_MANIFEST_PY = REPO_ROOT / "scripts/deploy/bundle_manifest.py"


def _bundle_manifest() -> Any:
    """``scripts/deploy/bundle_manifest.py``, loaded by path rather than by import.

    ``scripts/`` is not on this distribution's dependency path and must not become so:
    that program's whole claim is that it reads a zip with no access to the repository.
    Loading it by file location keeps this test's use of it an inspection of a program
    that ships elsewhere, and works whichever way pytest was invoked.
    """
    spec = importlib.util.spec_from_file_location("_w5_bundle_manifest", _BUNDLE_MANIFEST_PY)
    assert spec is not None and spec.loader is not None, _BUNDLE_MANIFEST_PY
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_closure_claim_and_the_artefact_claim_name_the_same_roots() -> None:
    """One list, two subjects. A root removed from either side must be removed from both."""
    assert tuple(BANNED_IMPORT_ROOTS) == tuple(_bundle_manifest().DEFAULT_FORBIDDEN)


def test_the_package_gate_refuses_a_planted_sdk_and_a_planted_source_map(
    tmp_path: Path,
) -> None:
    """The falsifiability of the artefact gate, planted and measured here rather than claimed.

    The check below runs against a real zip only on a machine that has built one, and CI's
    hermetic lane does not build one. So the *teeth* are demonstrated on a synthetic
    package instead: a minimal well-formed one passes, the same package with ``boto3/`` and
    one ``web/**/*.map`` added is REFUSED, and the refusal names both. A gate nobody has
    watched bite is a gate nobody knows is connected.
    """
    manifest_tool = _bundle_manifest()

    def build(path: Path, *extra: tuple[str, bytes]) -> dict[str, Any]:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, payload in (
                ("mainline_demo_api/app.py", b"def handler(event):\n    return event\n"),
                ("psycopg/__init__.py", b""),
                ("web/index.html", b"<!doctype html>\n"),
                ("web/bundle/manifest.json", b"{}\n"),
                ("web/assets/index.js", b"export {};\n"),
                *extra,
            ):
                archive.writestr(name, payload)
        return manifest_tool.check(manifest_tool.describe(str(path)), forbid_source_maps=True)

    clean = build(tmp_path / "clean.zip")
    assert clean["verdict"] == "PASS", clean["refusals"]
    assert clean["forbidden_present"] == []
    assert clean["source_maps"]["entries"] == 0

    planted = build(
        tmp_path / "planted.zip",
        ("boto3/__init__.py", b"__version__ = '1.0.0'\n"),
        ("boto3/session.py", b"class Session:\n    pass\n"),
        ("web/assets/index.js.map", b'{"version":3}\n'),
    )
    assert planted["verdict"] == "REFUSED"
    assert planted["forbidden_present"] == ["boto3"]
    assert planted["source_maps"] == {
        "entries": 1,
        "bytes": len(b'{"version":3}\n'),
        "gating": True,
        "ok": False,
        "example": "web/assets/index.js.map",
    }
    reasons = "\n".join(planted["refusals"])
    assert "FORBIDDEN ROOT] boto3" in reasons, reasons
    assert "SOURCE MAPS] 1 entries" in reasons, reasons

    # And the two gates are independent: the source-map refusal is the flag's, so the same
    # bytes with the flag off must leave `boto3` refused and the map merely reported.
    unflagged = manifest_tool.check(manifest_tool.describe(str(tmp_path / "planted.zip")))
    assert unflagged["forbidden_present"] == ["boto3"]
    assert unflagged["source_maps"]["gating"] is False
    assert [line for line in unflagged["refusals"] if "SOURCE MAPS" in line] == []

    # A vendored path is not an importable root: `import boto3` cannot reach it, and a
    # matcher that flagged it would refuse psycopg for shipping a directory name.
    vendored = build(tmp_path / "vendored.zip", ("psycopg/_vendor/boto3/__init__.py", b""))
    assert vendored["verdict"] == "PASS", vendored["refusals"]


def test_a_built_package_carries_no_banned_distribution_and_no_source_maps() -> None:
    """The bytes half of the claim, against whatever ``build_lambda`` last produced.

    Skipped rather than faked when no package has been built: this repository's hermetic
    lane does not run the builder, and asserting about a file that is not there would be a
    green with no subject. The gate itself is not skipped anywhere that matters —
    ``build_lambda`` runs ``bundle_manifest.py`` on the finished zip and dies on exit 2,
    and the test above proves that gate bites.
    """
    packages = sorted((REPO_ROOT / "out/lambda").glob("mainline-demo-api-*.zip"))
    if not packages:
        pytest.skip(
            "no deployment package has been built in this tree, so there are no bytes to "
            "read. Build one with `scripts/deploy/build_lambda.sh` (or `.ps1`) and this "
            "test measures it; `bundle_manifest.py --forbid-source-maps <zip>` is the same "
            "check on the command line"
        )

    manifest_tool = _bundle_manifest()
    for package in packages:
        verdict = manifest_tool.check(
            manifest_tool.describe(str(package), hash_entries=False),
            forbid_source_maps=True,
        )
        assert verdict["forbidden_present"] == [], f"{package.name}: {verdict['refusals']}"
        assert verdict["source_maps"]["entries"] == 0, f"{package.name}: {verdict['refusals']}"
        assert verdict["verdict"] == "PASS", f"{package.name}: {verdict['refusals']}"


#: The five modules this distribution's read surface is made of. Named explicitly rather
#: than globbed, because ``mainline_demo_api`` is a SHARED package directory: W4's
#: transitions, gate driver, refusal parser and scenario live beside these, and their
#: dependency closure is their own to declare. Scoping this test to the read spine keeps
#: it a statement about what this worker shipped rather than about what landed next to it.
_READ_SPINE = ("__init__.py", "app.py", "db.py", "envelope.py", "health.py", "reads.py")


def _dynamic_import_target(node: ast.Call) -> str | None:
    """The literal module name of an ``__import__`` or ``importlib.import_module`` call."""
    function = node.func
    if isinstance(function, ast.Name):
        called = function.id
    elif isinstance(function, ast.Attribute):
        called = function.attr
    else:
        return None
    if called not in {"__import__", "import_module"} or not node.args:
        return None
    first = node.args[0]
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _imported_roots(path: Path) -> set[str]:
    """Every module root *path* imports, read from its SYNTAX TREE and not from its text.

    A regex over source lines cannot tell an import statement from prose that begins with
    the word ``from``, and this file was one docstring away from finding that out. Its
    neighbour did find out: on 2026-08-13
    ``test_static_site.py::test_static_site_imports_nothing_outside_the_standard_library``
    went red because ``static_site.py``'s own docstring contains a line beginning *"from
    whatever the build happened to produce…"*, and reported that the module imports
    ``whatever``. Nothing about the module had changed. A parser sees statements, so prose
    cannot reach it.

    Dynamic calls are read too. ``importlib.import_module("boto3")`` is the obvious way
    past a checker that only inspects import statements, and a checker that can be stepped
    around on purpose is not one. ``from . import x`` carries ``level > 0`` and is inside
    this package by construction, so it names no root.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text("utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            target = _dynamic_import_target(node)
            if target is not None:
                roots.add(target.split(".")[0])
    return roots


def test_the_only_third_party_import_in_the_read_spine_is_psycopg() -> None:
    """Static, not runtime: a lazily imported framework would pass the closure test above."""
    source_dir = Path(app.__file__).resolve().parent
    third_party: dict[str, str] = {}
    seen: set[str] = set()
    stdlib = set(sys.stdlib_module_names)
    for name in _READ_SPINE:
        path = source_dir / name
        assert path.is_file(), f"{path} is missing from the read spine"
        for root in _imported_roots(path):
            seen.add(root)
            if root in stdlib or root in {"mainline_demo_api", "__future__"}:
                continue
            third_party[root] = name
    assert set(third_party) == {"psycopg"}, third_party

    # Anti-vacuity for the parser, not for the assertion above. These four are what the
    # read spine is built out of -- `hashlib` and `hmac` are how `db.py` signs its one SSM
    # call without an SDK -- so a walk that stopped finding imports fails here by name
    # instead of silently narrowing `third_party` towards a set it can no longer fail.
    assert {"hashlib", "hmac", "json", "psycopg"} <= seen, sorted(seen)


def test_every_read_is_addressable_and_named_consistently() -> None:
    """A route's key must have an implementation, and an implementation must have a route.

    ``demo_subjects`` is in every one of the three tables — routed, implemented, contracted
    — with no exemption, which is why this is still a plain equality. The two lines at the
    end name it, because an equality between three consistent sets would still hold if the
    subject index had never been added to any of them.
    """
    from mainline_demo_api import subjects

    get_keys = {route.key for route in app.ROUTES if route.method == "GET"}
    assert get_keys == set(reads.READS)
    for key in reads.READS:
        assert key in envelope.SCHEMA_IDS
    assert subjects.SUBJECTS_RESOURCE in get_keys
    assert reads.READS[subjects.SUBJECTS_RESOURCE] is reads.read_demo_subjects
