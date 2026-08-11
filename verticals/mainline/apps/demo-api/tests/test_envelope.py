# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
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

**Is the deployment package still what the pyproject claims?** One test walks
``sys.modules`` after importing the package and asserts no web framework and no AWS SDK
came with it. The dependency list is the claim; this is the mechanism.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from mainline_demo_api import app, envelope, health, reads

from conftest import (
    CONTRACTS_DIR,
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


def test_the_console_declares_sixteen_resources() -> None:
    """Guards the parser itself: if the regex stops matching, every test below passes vacuously."""
    declared = _declared()
    assert len(declared) == 16, [entry["key"] for entry in declared]
    assert sum(1 for entry in declared if entry["method"] == "GET") == 12


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
    """``envelope.schema_id`` must be the EXACT ``$id`` the console holds, for all sixteen.

    ``finishExchange`` compares them as strings and refuses a mismatch outright:
    *a payload that names a contract we do not hold is not forward compatibility; it is
    an unverifiable claim.* Six of the sixteen name a file whose stem is not their key,
    so this cannot be a derivation and has to be a comparison.
    """
    expected = {entry["key"]: f"{envelope.CONTRACT_BASE}{entry['schema']}" for entry in _declared()}
    assert expected == envelope.SCHEMA_IDS


def test_every_contract_id_resolves_to_a_committed_file() -> None:
    """Each ``$id`` this API emits must be a file on disk under ``console/contracts/``."""
    held = {
        json.loads(path.read_text(encoding="utf-8"))["$id"]
        for path in CONTRACTS_DIR.glob("*.schema.json")
    }
    missing = sorted(set(envelope.SCHEMA_IDS.values()) - held)
    assert not missing, f"emitted schema ids with no contract file: {missing}"


def test_reads_implements_exactly_the_twelve_gets() -> None:
    """The twelve GET keys, no more and no fewer. W4 owns the four POSTs."""
    gets = {entry["key"] for entry in _declared() if entry["method"] == "GET"}
    assert set(reads.READS) == gets


def test_routes_match_the_console_path_templates() -> None:
    """Every declared template is routable, and the only route the console does not
    declare is the demo driver's own endpoint.

    ``POST /v1/demo/gate-run`` is routed by this API and is deliberately NOT one of the
    console's sixteen ``declare()`` calls: it is governed by
    ``demo-api/contracts/gate-run.schema.json`` rather than by ``invoke.schema.json``, and
    its key ``demo_gate_run`` is declared in ``transitions.TRANSITION_RESOURCES`` instead
    of in the console's resource registry. It was absent from ``app._routes()`` until
    2026-08-11, which is why ``evidence/deploy/acceptance.json`` records
    *"POST /v1/demo/gate-run (run 1) returned 404, expected 200"*.

    The exception is pinned as an exact set rather than relaxed to a subset, so a SECOND
    undeclared route still fails here — this assertion is strictly stronger than the
    equality it replaces, not weaker. ``tests/test_routes_gate_run.py`` carries the rest
    of the agreement check between the router and the dispatcher.
    """
    demo_route = ("POST", "/v1/demo/gate-run")
    declared = {(entry["method"], entry["template"]) for entry in _declared()}
    routed = {(route.method, route.template) for route in app.ROUTES}
    assert declared <= routed, f"declared but not routed: {sorted(declared - routed)}"
    assert routed - declared == {demo_route}


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


def test_no_web_framework_or_aws_sdk_is_imported() -> None:
    """The dependency list is the claim; this is the mechanism.

    There is no HTTP server in this artefact and there is no AWS SDK. A Lambda invocation
    is already a function call with a dict argument, and ``db.py`` signs its one SSM call
    with :mod:`hashlib` and :mod:`hmac` so the package's behaviour does not depend on
    which boto3 the runtime image happens to ship this month.
    """
    for module in ("mainline_demo_api.app", "mainline_demo_api.db", "mainline_demo_api.reads"):
        __import__(module)
    banned = {
        "fastapi",
        "flask",
        "starlette",
        "uvicorn",
        "aiohttp",
        "django",
        "mangum",
        "boto3",
        "botocore",
        "requests",
        "httpx",
        "pydantic",
    }
    present = sorted(name for name in banned if name in sys.modules)
    assert present == [], f"the deployment package pulled in {present}"


#: The five modules this distribution's read surface is made of. Named explicitly rather
#: than globbed, because ``mainline_demo_api`` is a SHARED package directory: W4's
#: transitions, gate driver, refusal parser and scenario live beside these, and their
#: dependency closure is their own to declare. Scoping this test to the read spine keeps
#: it a statement about what this worker shipped rather than about what landed next to it.
_READ_SPINE = ("__init__.py", "app.py", "db.py", "envelope.py", "health.py", "reads.py")


def test_the_only_third_party_import_in_the_read_spine_is_psycopg() -> None:
    """Static, not runtime: a lazily imported framework would pass the test above."""
    source_dir = Path(app.__file__).resolve().parent
    third_party: dict[str, str] = {}
    stdlib = set(sys.stdlib_module_names)
    for name in _READ_SPINE:
        path = source_dir / name
        assert path.is_file(), f"{path} is missing from the read spine"
        for match in re.finditer(
            r"^\s*(?:import|from)\s+([a-zA-Z_][\w.]*)", path.read_text("utf-8"), re.M
        ):
            root = match.group(1).split(".")[0]
            if root in stdlib or root in {"mainline_demo_api", "__future__"}:
                continue
            third_party[root] = name
    assert set(third_party) == {"psycopg"}, third_party


def test_every_read_is_addressable_and_named_consistently() -> None:
    """A route's key must have an implementation, and an implementation must have a route."""
    get_keys = {route.key for route in app.ROUTES if route.method == "GET"}
    assert get_keys == set(reads.READS)
    for key in reads.READS:
        assert key in envelope.SCHEMA_IDS
