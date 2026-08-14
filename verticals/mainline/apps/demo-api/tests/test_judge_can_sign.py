# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""THE WHOLE JUDGE PATH, walked once through :func:`mainline_demo_api.app.handler`.

The product exists to tell one story: the gate REFUSES a merge while an obligation is
open, a judge reads the obligation, CHOOSES A DEFEATER from the vocabulary that check
offers, SIGNS, and the same merge is then ADMITTED. Every beat of it has been implemented
and tested somewhere in this suite; until this file, no test drove all five in order,
through the router, against the seed the deployment applies. Four NO-GO verdicts and one
``23503`` in front of a judge came out of exactly that gap — each part green, the arc
unwalked.

WHAT IS DRIVEN, AND WHY IT IS THE ROUTER RATHER THAN THE FUNCTIONS
-----------------------------------------------------------------
:func:`mainline_demo_api.app.handler` with payload-format-2.0 events, over three rows of
``app.ROUTES``:

===================================================  ==================================
``POST /v1/permits/{permit_id}/merge``               ``transitions.merge_permit``
``GET  /v1/checks/{check_id}/disposition``           ``reads.disposition``
``POST /v1/checks/{check_id}/disposition``           ``transitions.sign_disposition``
===================================================  ==================================

Not ``handle_transition`` and not ``read_resource``. The router is where a working beat
has been rendered unreachable before: ``app._routes()`` once returned sixteen rows with no
``/v1/demo/gate-run`` while every beat below it worked, and the demo answered 404 to the
one endpoint the console drives (``tests/test_routes_gate_run.py``,
``evidence/deploy/acceptance.json``). A test that calls the function under the route
proves the function.

WHY THIS WALK NEEDS A DATABASE OF ITS OWN, MEASURED RATHER THAN PREFERRED
------------------------------------------------------------------------
Beats 4 and 5 COMMIT, and the merge cannot be undone. That is not an inconvenience, it is
the schema working: ``mainline.merge_record`` and ``mainline.permit_event`` both carry the
``append_only`` weld (``0128_trg_refuse_mutation.sql``,
``0128c_trg_refuse_mutation_merge_record.sql``) which refuses UPDATE **and** DELETE. Read
out of ``information_schema.triggers`` on a freshly built database on 2026-08-14:

    blocking_check  INSERT+UPDATE+DELETE
    disposition     INSERT+UPDATE
    merge_record    UPDATE+DELETE
    permit_event    INSERT+UPDATE+DELETE

So a merged permit stays merged, and the session-scoped ``demo_database`` — which
``test_reads.py`` reads for ``state == 'dispositioned'``, ``open_blocking == 1`` and
``check['open'] is True``, and which is CACHED ACROSS SESSIONS by fingerprint — would be
consumed by this walk for every run after it. ``transitions._demo_guard`` says the same
thing from the product's side and names the remedy in its own refusal text: *"a permit is
never un-merged … Set MAINLINE_DEMO_ALLOW_MUTATION=1 in a deployment you own to lift
this."*

**This module owns one.** :func:`judge_walk` builds a ``w_w3_judge_path_…`` database
(:func:`_walk_database_name`) by applying the same 271 migrations and then
``scripts/deploy/seed_demo.SEED_FILES`` — ``demo_world.sql`` then ``demo_permit.sql``,
through the deployment's own applier, obtained by importing the file list rather than
restating it — and drops it again when the module is done. So the world walked here IS the
deployed seed and not a hand-built one; what is private is the copy, not the history.
Measured cost on TRAPPOINT, 2026-08-14, four builds: **78.7 s / 95.2 s / 119.0 s /
131.7 s** for the chain (271 files, 0 failures each time) plus ~**1 s** for the two seed
files, the spread being how many other workers were on the node. That is the price of
proving an irreversible arc, and it is stated here rather than hidden so that a lead can
weigh it.

Nothing is cached between sessions on purpose. A cached database would be a database whose
permit this walk has already merged, and ``demo-api/tests/conftest.py`` and RULING R8 both
say what that costs: *"a cached database built from an older copy of it"* is the failure
mode that already corrupted one published list. A build that is always fresh cannot be
adopted stale.

**The cheap alternative was tried and it does not work — measured, so that the next reader
does not re-derive it from first principles and ship the broken version.** Caching the
database and resetting the consumed subject with ``TRUNCATE`` over all 86 ``mainline*``
base tables plus a re-application of the two seed files fails on both counts. It is not
cheap: the TRUNCATE alone took **38.1 s**, against 78.7 s for the whole chain. And it is
not correct: the reference rows the MIGRATIONS insert go with it, so the re-seed dies at
``23503 cr_legal_edge`` — *"Key (subject_kind, from_state, to_state)=('change_request',
'draft', 'checks_materialised') is not present in table subject_transition"* — and the
database is left holding neither the old world nor a new one. ``mainline.subject_transition``
is a table of legal edges written by the chain, not by ``demo_world.sql``, and a reset that
truncates it has deleted part of the schema's meaning.

WHAT THIS MODULE PROMISES ABOUT THE SHARED DATABASE
---------------------------------------------------
:func:`test_the_shared_deployed_seed_database_is_untouched_by_this_walk` asserts it
directly: ``mainline.disposition`` still holds **no rows** there, the permit is still
``dispositioned`` with ``open_blocking == 1``, and ``mainline.merge_record`` is still
empty. ``demo_permit.sql`` seeds no disposition BECAUSE that absence is what beat 1
refuses on, and a test that signed one into the shared database would have deleted the
demo's first beat for the next reader without saying so.

EACH BEAT FAILS ON ITS OWN
--------------------------
The walk is performed once, by a module-scoped fixture that RECORDS and asserts nothing;
each test below reads one beat's record. So a wrong SQLSTATE in beat 1 does not hide a
wrong digest in beat 4, and the failure names the beat. If the walk itself cannot run —
no cluster, a build failure, a resolver refusal — the fixture RAISES and every test in
this module ERRORS with that reason. **Nothing here skips.** A skip is indistinguishable
from a green tick on a dashboard, and this is the one arc the product exists to show.

BEAT 3 IS A CONTROL, AND THE DATABASE IS THE THING IT CONTROLS FOR
------------------------------------------------------------------
``0066_disposition.sql`` gives ``mainline.disposition.defeater_code`` no foreign key onto
``mainline.defeater_option`` — only ``CONSTRAINT disposition_defeater_code_stated CHECK
(defeater_code <> '')``. So a signature naming a code no screen ever offered would commit,
admit, and report PROVEN, and nothing in the database would notice. RULING R9 forbids
adding the key four days from the deadline. :func:`test_beat_3_a_code_that_was_never_
offered_is_refused` is therefore the whole of that enforcement, and it asserts the ABSENCE
of the foreign key out of ``information_schema`` in the same breath — because the day
somebody adds it, this test should say so rather than quietly become redundant.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import psycopg
import pytest
from mainline_demo_api import app, envelope, ratelimit
from mainline_demo_api import db as demo_db
from mainline_demo_api.gate_run import DEMO_DEFEATER_CODE
from psycopg.rows import dict_row

import conftest as fixture
from conftest import REPO_ROOT, SchemaRegistry

pytestmark = pytest.mark.requires_cluster

#: The prefix every database this module builds carries. A leftover after a killed run
#: says whose it was and what it was for, which is the whole job a prefix has here.
WALK_PREFIX: Final = "w_w3_judge_path"

#: Written only when this name is set, so a normal test run leaves the working tree clean
#: and the committed artefact stays regenerable BY THE CODE THAT ASSERTS IT:
#:
#:     MAINLINE_W3_WALK_EVIDENCE=evidence/demo/judge-path-walk.json pytest \
#:         verticals/mainline/apps/demo-api/tests/test_judge_can_sign.py --crdb=reuse
#:
#: An evidence file a test rewrote on every run would make every run a dirty tree, and a
#: dirty tree is how a re-baseline stops being a conversation.
EVIDENCE_ENV: Final = "MAINLINE_W3_WALK_EVIDENCE"

#: ``sha256(b"defeater-vocab")`` — the constant BOTH signing paths bound until 2026-08-14,
#: and byte-for-byte the value the deployed CockroachDB Cloud recorded on its one signed
#: disposition (``console/fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json``,
#: ``signed.defeater_vocab_sha256``). It is written out as a literal rather than computed,
#: because a test that recomputed it would agree with any code that computed it the same
#: way — which is the exact defect shape this repository has been burned by three times.
#: Beat 4 asserts the recorded digest is NOT this.
CONSTANT_THAT_PINNED_NOTHING: Final = (
    "7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f"
)

#: A rationale over ``transitions._RATIONALE_MIN`` (120) that says something true about
#: this demo's obligation: ``DEMO-INC-0001`` is the recalled precursor and the clause
#: version's anchors are ``['LOTO', 'ZERO_ENERGY']``.
RATIONALE: Final = (
    "The recalled precursor DEMO-INC-0001 is answered by a zero-energy isolation "
    "procedure that is present on this permit and was verified at zero before any "
    "intrusive work: the LOTO and ZERO_ENERGY anchors of the cited clause version are "
    "both satisfied, witnessed, and recorded against this obligation."
)


# ══════════════════════════════════════════════════════════════════════════════════════
# the record
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Beat:
    """One observation. Nothing here is asserted; every field is what came back.

    ``staged`` names what this program supplied and ``measured`` names what the SERVER
    said, because a record that does not separate the two is a record a reader has to
    take on trust — the distinction the captured Cloud exhibits draw in their own
    ``--parameters--`` / ``--result--`` split, and the standard this file follows.
    """

    beat: int
    title: str
    request: dict[str, Any]
    status: int | None = None
    outcome: str | None = None
    sqlstate: str | None = None
    constraint: str | None = None
    constraint_source: str | None = None
    message: str | None = None
    detail: str | None = None
    read_back: dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class Walk:
    """Everything one walk observed, plus what it was walked against."""

    database: str
    permit_id: str
    check_id: str
    driver: str
    beats: dict[int, Beat] = field(default_factory=dict)
    offered: list[dict[str, Any]] = field(default_factory=list)
    disposition_payload: dict[str, Any] = field(default_factory=dict)
    signed_payload: dict[str, Any] | None = None
    foreign_keys_onto_defeater_option: list[str] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)

    def beat(self, index: int) -> Beat:
        """Return beat *index*, or fail naming which beat never ran.

        A ``KeyError`` here would be reported as an internal error in this file; the
        walk not reaching a beat is a finding about the PRODUCT and has to read like one.
        """
        recorded = self.beats.get(index)
        if recorded is None:
            raise AssertionError(
                f"beat {index} was never reached, so there is nothing to assert about it. "
                f"Beats recorded: {sorted(self.beats)}. The walk stops at the first beat "
                "that raises rather than continuing against a database in a state it did "
                "not expect."
            )
        return recorded


# ══════════════════════════════════════════════════════════════════════════════════════
# the events, and the environment the deployment publishes
# ══════════════════════════════════════════════════════════════════════════════════════


def _event(method: str, path: str, body: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One payload-format-2.0 event, the shape a Lambda Function URL delivers."""
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "",
        "queryStringParameters": None,
        "headers": {"accept": "application/json", "content-type": "application/json"},
        "requestContext": {
            "stage": "$default",
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.11",
                "userAgent": "mainline-tests/w3-judge-walk",
            },
        },
        "isBase64Encoded": False,
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


@contextlib.contextmanager
def _judge_environment(dsn: str, permit_id: str) -> Iterator[None]:
    """Point the handler at the walk database, and lift the demo write-lock ON IT ONLY.

    Three names, and each is a decision:

    ``MAINLINE_DSN`` — the walk database. ``db`` caches the resolved DSN and the
    connection for the life of an execution environment, and a pytest process IS one
    execution environment shared with every other module; without the reset around this
    the handler would answer against whichever database ran last.

    ``MAINLINE_DEMO_PERMIT_ID`` — ``infra/modules/demo-api/main.tf`` publishes it, and it
    is load-bearing twice over. ``scenario.from_env``'s fallback is the uuid5 derivation
    ``077a6fdd-…`` while the seed's permit is ``dec0de00-0006-…``, so without it
    ``_demo_guard`` cannot establish which subject it protects and refuses **423
    demo_subject_unidentified** — fail-closed, correctly, and this walk would prove
    nothing about the gate.

    ``MAINLINE_DEMO_ALLOW_MUTATION`` — the lock ``transitions._demo_guard`` puts on the
    demo subject, lifted here because this is *"a deployment you own"* in that refusal's
    own words: a database this module built, consumes, and drops. It is restored on the
    way out whatever happens; leaving it set would silently disarm the guard for
    ``test_demo_guard_anonymous.py``, which is the module whose whole subject is that the
    guard is armed.
    """
    # THE SIGNER SUBJECTS ARE BOUND HERE TOO, added 2026-08-14, and the omission was a real
    # order-dependent failure rather than tidiness.
    #
    # This fixture used to bind the DSN, the permit and the mutation flag and INHERIT the two
    # signer names. `scenario.from_env` reads all five, so the walk was binding part of a
    # scenario and adopting the rest from whatever the process happened to hold. Run alone,
    # nothing held them, the committed defaults `demo.signer` / `demo.countersigner` applied,
    # and all thirteen tests passed. Run in the full suite, `test_gate_run.py` and
    # `test_row_factory_contract.py` each bind them to `proof.signer` for the life of their
    # own world — both restore correctly, but their scope outlives this module — so beat 4
    # resolved a credential for a subject THIS database never enrolled and the walk failed:
    #
    #     422 — mainline.signing_credential holds no unrevoked credential for signer_sub
    #     'proof.signer' in this database
    #
    # which is `credentials.resolve_credential_id` doing exactly its job, against a scenario
    # half of which belonged to another module's world. A fixture that binds some of an
    # environment and inherits the rest has not bound an environment; it has bound a
    # coincidence, and the coincidence holds until the file runs beside its neighbours.
    #
    # `demo_world.sql` enrols `demo.signer` and `demo.countersigner`, and this walk applies
    # that seed, so the committed defaults are the correct values here — they are pinned
    # rather than relied upon, so a future change to the default is a visible change to this
    # module and not a silent one.
    previous = {
        name: os.environ.get(name)
        for name in (
            demo_db.DSN_ENV,
            "MAINLINE_DEMO_PERMIT_ID",
            "MAINLINE_DEMO_ALLOW_MUTATION",
            "MAINLINE_DEMO_SIGNER_SUB",
            "MAINLINE_DEMO_COUNTERSIGNER_SUB",
        )
    }
    try:
        os.environ[demo_db.DSN_ENV] = dsn
        os.environ["MAINLINE_DEMO_PERMIT_ID"] = permit_id
        os.environ["MAINLINE_DEMO_ALLOW_MUTATION"] = "1"
        os.environ["MAINLINE_DEMO_SIGNER_SUB"] = "demo.signer"
        os.environ["MAINLINE_DEMO_COUNTERSIGNER_SUB"] = "demo.countersigner"
        demo_db.reset_dsn_cache()
        yield
    finally:
        demo_db.close()
        demo_db.reset_dsn_cache()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _call(method: str, path: str, body: Mapping[str, Any] | None = None) -> tuple[int, Any]:
    """One request through the real handler. Returns ``(statusCode, decoded body)``.

    ``ratelimit.reset()`` first: the buckets are module-scope state belonging to one
    execution environment, and a neighbour that drained the global one would turn a beat
    into a 429 whose failure named the wrong module. Resetting refills; it cannot
    reconfigure, and no environment variable can disarm the limiter.
    """
    ratelimit.reset()
    response = app.handler(_event(method, path, body))
    return int(response["statusCode"]), json.loads(response["body"])


def _refusal_of(payload: Any) -> dict[str, Any]:
    """The refusal block out of an ``invoke`` envelope, or an empty mapping."""
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        refusal = payload["data"].get("refusal")
        if isinstance(refusal, dict):
            return refusal
    return {}


def _outcome_of(payload: Any) -> str | None:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        outcome = payload["data"].get("outcome")
        return str(outcome) if outcome is not None else None
    return None


# ══════════════════════════════════════════════════════════════════════════════════════
# the walk
# ══════════════════════════════════════════════════════════════════════════════════════


_FK_ONTO_DEFEATER_OPTION_SQL: Final = """
SELECT tc.constraint_name
  FROM information_schema.table_constraints tc
  JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.constraint_schema = tc.constraint_schema
 WHERE tc.constraint_type = 'FOREIGN KEY'
   AND tc.table_schema = 'mainline'
   AND tc.table_name = 'disposition'
   AND ccu.table_schema = 'mainline'
   AND ccu.table_name = 'defeater_option'
"""

_SIGNED_ROW_SQL: Final = """
SELECT d.disposition_id,
       d.defeater_code,
       encode(d.defeater_vocab_sha256, 'hex'),
       d.kind::STRING,
       d.rationale
  FROM mainline.disposition d
 WHERE d.check_id = %s
   AND d.retracted_by IS NULL
"""

_PERMIT_ROW_SQL: Final = (
    "SELECT p.state::STRING, p.open_blocking, "
    "(SELECT count(*) FROM mainline.merge_record m WHERE m.subject_id = p.permit_id) "
    "FROM mainline.permit p WHERE p.permit_id = %s"
)


def _walk(
    database: str, dsn: str, seed: Mapping[str, str], observer: psycopg.Connection[Any]
) -> Walk:
    """Perform the five beats in order and RECORD each. Asserts nothing.

    Every reading in :class:`Beat.read_back` is taken with *observer*, a plain connection
    that is not the one the handler uses, so the values are the ones the DATABASE holds
    after the transition committed rather than the ones the response claimed. A response
    is a claim; a read-back is a measurement, and a walk that only checked the response
    would certify a handler that had learned to say ``committed``.
    """
    walk = Walk(
        database=database,
        permit_id=seed["permit_id"],
        check_id=seed["check_id"],
        driver=f"psycopg {psycopg.__version__}",
    )
    permit_path = f"/v1/permits/{seed['permit_id']}/merge"
    disposition_path = f"/v1/checks/{seed['check_id']}/disposition"

    walk.foreign_keys_onto_defeater_option = [
        str(row[0]) for row in observer.execute(_FK_ONTO_DEFEATER_OPTION_SQL).fetchall()
    ]

    with _judge_environment(dsn, seed["permit_id"]):
        # ── BEAT 1 ────────────────────────────────────────────────────────────────────
        started = time.monotonic()
        status, payload = _call("POST", permit_path, {})
        walk.seconds["beat_1"] = round(time.monotonic() - started, 3)
        refusal = _refusal_of(payload)
        walk.beats[1] = Beat(
            beat=1,
            title="the merge is refused while the obligation is open",
            request={"method": "POST", "path": permit_path, "body": {}},
            status=status,
            outcome=_outcome_of(payload),
            sqlstate=refusal.get("sqlstate"),
            constraint=refusal.get("constraint"),
            constraint_source=refusal.get("constraint_source"),
            message=refusal.get("message"),
            detail=payload.get("detail") if isinstance(payload, dict) else None,
            read_back=_counters(observer, seed),
            note=(
                "MEASURED. Every field above except the request came from the server: the "
                "SQLSTATE and the constraint name are psycopg's Diagnostic fields, not this "
                "program's words. Nothing was persisted — a refused transaction is rolled "
                "back, and the merge_record count read back beside it is the check on that."
            ),
        )

        # ── BEAT 2 ────────────────────────────────────────────────────────────────────
        started = time.monotonic()
        status, payload = _call("GET", disposition_path)
        walk.seconds["beat_2"] = round(time.monotonic() - started, 3)
        data = payload.get("data") if isinstance(payload, dict) else None
        walk.disposition_payload = payload if isinstance(payload, dict) else {}
        walk.offered = list(data.get("defeater_options", [])) if isinstance(data, dict) else []
        walk.beats[2] = Beat(
            beat=2,
            title="the disposition offers a vocabulary a judge can choose from",
            request={"method": "GET", "path": disposition_path},
            status=status,
            read_back={
                "defeater_options": len(walk.offered),
                "codes": [str(option["defeater_code"]) for option in walk.offered],
                "distinct_vocab_sha256": sorted(
                    {str(option["vocab_sha256"]) for option in walk.offered}
                ),
                "signed": data.get("signed") if isinstance(data, dict) else None,
            },
            note=(
                "MEASURED. The codes, the prompts and the digest are rows of "
                "mainline.defeater_option as reads._DEFEATER_SQL returned them; this "
                "program supplied only the check_id in the path. `signed` is null here "
                "because demo_permit.sql seeds no disposition — that absence is what beat 1 "
                "refused on."
            ),
        )

        # ── BEAT 3 ────────────────────────────────────────────────────────────────────
        stranger = _code_that_was_never_offered(walk.offered)
        started = time.monotonic()
        status, payload = _call(
            "POST",
            disposition_path,
            {"kind": "applied", "defeater_code": stranger, "rationale": RATIONALE},
        )
        walk.seconds["beat_3"] = round(time.monotonic() - started, 3)
        walk.beats[3] = Beat(
            beat=3,
            title="a defeater code this check never offered is refused",
            request={
                "method": "POST",
                "path": disposition_path,
                "body": {"kind": "applied", "defeater_code": stranger, "rationale": "<180 chars>"},
            },
            status=status,
            outcome=_outcome_of(payload),
            detail=payload.get("detail") if isinstance(payload, dict) else None,
            message=payload.get("error") if isinstance(payload, dict) else None,
            read_back=_counters(observer, seed),
            note=(
                "STAGED INPUT, MEASURED OUTCOME. The code was composed by this program so "
                "that it could not be a member of the offered set; everything else is the "
                "server's. THERE IS NO SQLSTATE HERE AND THAT IS THE FINDING: no constraint "
                "refused this, because mainline.disposition has no foreign key onto "
                "mainline.defeater_option and 0066_disposition.sql constrains defeater_code "
                "only with CHECK (defeater_code <> ''). If this beat ever reports an "
                "SQLSTATE, a migration added the key and this control has become a "
                "duplicate of it. "
                + (
                    "The refusal observed IS the membership check — "
                    "mainline_demo_api.defeaters.DefeaterVocabulary.require — which is what "
                    "this beat is a control for."
                    if isinstance(payload, dict) and payload.get("error") == "unprocessable_request"
                    else "THE REFUSAL OBSERVED WAS NOT THE MEMBERSHIP CHECK: this check "
                    "offers no vocabulary at all, so resolve_defeater_vocabulary refused "
                    "before require() was reached and this beat controlled nothing. What "
                    "was measured is that an unseeded vocabulary refuses; what remains "
                    "unmeasured is that a SEEDED one refuses a non-member."
                )
            ),
        )

        # ── BEAT 4 ────────────────────────────────────────────────────────────────────
        started = time.monotonic()
        status, payload = _call(
            "POST",
            disposition_path,
            {"kind": "applied", "defeater_code": DEMO_DEFEATER_CODE, "rationale": RATIONALE},
        )
        walk.seconds["beat_4"] = round(time.monotonic() - started, 3)
        row = observer.execute(_SIGNED_ROW_SQL, (seed["check_id"],)).fetchall()
        walk.beats[4] = Beat(
            beat=4,
            title="a judge signs with a code the check actually offered",
            request={
                "method": "POST",
                "path": disposition_path,
                "body": {
                    "kind": "applied",
                    "defeater_code": DEMO_DEFEATER_CODE,
                    "rationale": "<180 chars>",
                },
            },
            status=status,
            outcome=_outcome_of(payload),
            detail=payload.get("detail") if isinstance(payload, dict) else None,
            read_back={
                "disposition_rows": len(row),
                "defeater_code": str(row[0][1]) if row else None,
                "defeater_vocab_sha256": str(row[0][2]) if row else None,
                "kind": str(row[0][3]) if row else None,
                **_counters(observer, seed),
            },
            note=(
                "STAGED INPUT. The kind, the code and the rationale are the four things "
                "0064 puts in a signer's gift and this program supplied them. "
                "defeater_vocab_sha256 is never supplied: it is resolved out of "
                "mainline.defeater_option by mainline_demo_api.defeaters. "
                + (
                    "MEASURED ROW: the values above were read back from the committed row "
                    "with a SECOND connection the handler never saw, so they are what the "
                    "database holds and not what the response claimed. The WebAuthn "
                    "assertion is synthesised and the envelope declares staged=true for it."
                    if row
                    else "NO ROW WAS WRITTEN. The signature was refused, so there is "
                    "nothing to read back and every read_back field about the disposition "
                    "is null because the row does not exist — not because it was not "
                    "looked for. The server's reason is in `detail` above."
                )
            ),
        )
        signed_status, signed_payload = _call("GET", disposition_path)
        if isinstance(signed_payload, dict) and isinstance(signed_payload.get("data"), dict):
            walk.signed_payload = dict(signed_payload["data"].get("signed") or {}) or None
        walk.beats[4].read_back["read_surface_status"] = signed_status

        # ── BEAT 5 ────────────────────────────────────────────────────────────────────
        started = time.monotonic()
        status, payload = _call("POST", permit_path, {})
        walk.seconds["beat_5"] = round(time.monotonic() - started, 3)
        committed = {}
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            committed = dict(payload["data"].get("committed") or {})
        walk.beats[5] = Beat(
            beat=5,
            title="the same merge is admitted",
            request={"method": "POST", "path": permit_path, "body": {}},
            status=status,
            outcome=_outcome_of(payload),
            sqlstate=_refusal_of(payload).get("sqlstate"),
            constraint=_refusal_of(payload).get("constraint"),
            detail=payload.get("detail") if isinstance(payload, dict) else None,
            read_back={
                "merged_commit": committed.get("merged_commit"),
                "clearance_digest": committed.get("clearance_digest"),
                "merged_at": committed.get("merged_at"),
                **_counters(observer, seed),
            },
            note=(
                "MEASURED. This is the SAME request as beat 1, byte for byte. "
                + (
                    "It refused there and committed here, and the only thing that changed "
                    "between them is one signature over a code the check offered. "
                    "clearance_digest was computed BY THE SERVER in mainline.merge_permit "
                    "step 4, over the sorted (check_id, disposition_id) set; this program "
                    "supplied none of it. Nothing is rolled back: mainline.merge_record and "
                    "mainline.permit_event refuse UPDATE and DELETE, which is why this walk "
                    "needs a database of its own."
                    if _outcome_of(payload) == "committed"
                    else "IT REFUSED AGAIN, with the same exhibit, because no signature was "
                    "recorded at beat 4 and the obligation is still open. The gate is "
                    "behaving correctly and the arc did not close: a gate that always "
                    "refuses is broken, not safe, and this run has not shown it admitting."
                )
            ),
        )
    return walk


def _counters(observer: psycopg.Connection[Any], seed: Mapping[str, str]) -> dict[str, Any]:
    """The three numbers every beat is about, read with a connection the handler never saw."""
    row = observer.execute(_PERMIT_ROW_SQL, (seed["permit_id"],)).fetchone()
    dispositions = observer.execute(
        "SELECT count(*) FROM mainline.disposition WHERE check_id = %s", (seed["check_id"],)
    ).fetchone()
    return {
        "permit_state": str(row[0]) if row else None,
        "open_blocking": int(row[1]) if row else None,
        "merge_records": int(row[2]) if row else None,
        "dispositions": int(dispositions[0]) if dispositions else None,
    }


def _code_that_was_never_offered(offered: list[dict[str, Any]]) -> str:
    """A defeater code guaranteed not to be in *offered*, composed rather than chosen.

    Derived from the offered set itself so that it cannot accidentally become a member if
    the vocabulary grows: it is the concatenation of every offered code's first character
    behind a prefix no vocabulary would author, and it is checked against the set before
    it is returned. A literal would be a hostage to whatever the seed adds next.
    """
    codes = {str(option["defeater_code"]) for option in offered}
    candidate = "NOT_OFFERED_BY_THIS_CHECK_" + "".join(sorted(code[:1] for code in codes))
    while candidate in codes:  # pragma: no cover - unreachable given the prefix
        candidate += "X"
    return candidate


# ══════════════════════════════════════════════════════════════════════════════════════
# the fixture
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def judge_walk(admin_dsn: str) -> Iterator[Walk]:
    """Build a private copy of the DEPLOYED seed, walk it once, record, and drop it.

    The chain and the seeds are applied by ``conftest``'s own helpers, which is what makes
    this the deployed history rather than a second definition of it: ``_apply_chain``
    walks ``verticals/mainline/db/migrations`` and ``_apply_seeds`` applies
    ``scripts/deploy/seed_demo.SEED_FILES`` through the deployment's applier. The
    identifiers come back out of the database with ``_identifiers`` — read, never parsed
    out of the SQL and never restated.

    ``_live_receipt`` is called for the reason ``conftest`` calls it on its own fresh-build
    path: ``demo_permit.sql`` pins the exposure receipt's ``expires_at`` to a literal
    ``2027-01-01``, so a database seeded from it after that date is BORN with a dead
    receipt and ``sign_disposition`` would answer ``422 no_live_exposure_receipt``. That is
    a fixture failure that would read as a product failure, so it is repaired here and the
    repair is refused loudly if it does not take.

    The teardown drops the database whatever happened, and sweeps any sibling a killed run
    left behind. A walk that died mid-arc leaves a half-merged permit, and nothing must be
    able to adopt it.
    """
    try:
        database, dsn, applied, chain_seconds, seed_seconds = _build(admin_dsn)

        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as reader:
            seed = fixture._identifiers(reader)
            unusable = fixture._live_receipt(reader, seed)
            if unusable is not None:
                raise AssertionError(
                    f"{database} carries the deployed seed but is not walkable: "
                    f"{unusable}. sign_disposition's composite foreign key lands on "
                    "(check_id, receipt_id), so a signature may only cite a receipt that "
                    "actually showed the signer this obligation."
                )

        with psycopg.connect(dsn, autocommit=True) as observer:
            walk = _walk(database, dsn, seed, observer)
        walk.seconds["build_chain"] = chain_seconds
        walk.seconds["build_seeds"] = seed_seconds
        walk.seconds["migrations_applied"] = float(applied)
        _maybe_write_evidence(walk)
        yield walk
    finally:
        demo_db.close()
        demo_db.reset_dsn_cache()
        _sweep(admin_dsn)


def _walk_database_name() -> str:
    """A name no earlier run can be holding, carrying the fingerprint of what built it.

    TWO PARTS, AND NEITHER IS DECORATION.

    The FINGERPRINT half is ``conftest._fingerprint()`` — a SHA-256 over every migration's
    name and bytes and over both seed files' bytes — for the reason RULING R8 gives: a
    leftover database whose name does not say which tree built it is a database somebody
    will eventually read a seed edit against.

    The RUN half is fresh per session, and it is what removes a measured failure rather
    than a hypothetical one. A fixed name has to be dropped before it is created, and
    CockroachDB's ``DROP DATABASE … CASCADE`` frees the name long before it has finished
    with the data: the drop enqueues a ``SCHEMA CHANGE GC`` job. Measured on TRAPPOINT on
    2026-08-14 with five other workers on the node, building into a just-dropped name:
    ``184/271`` applied on the first attempt (*"relation mainline.person does not exist"*
    at ``0128g``) and ``42/271`` on the second (*"[3F000] cannot create
    mainline.virulence_class because the target database or schema does not exist"* at
    ``0013``) — a chain that had applied **271/271** twice into a name nothing had just
    dropped. **A fresh name has nothing to race with.**

    This is not the thing R8 forbids. R8 refuses ``uuid4`` where a database is ADOPTED,
    because a random name fixes a collision and loses the ability to notice a stale build.
    Nothing here is ever adopted: this database is built, walked once and dropped, so there
    is no adoption to protect and the fingerprint is carried for the reader rather than for
    the lookup.
    """
    return f"{WALK_PREFIX}_{fixture._fingerprint()}_{uuid.uuid4().hex[:8]}"


def _sweep(admin_dsn: str) -> None:
    """Drop this module's databases — this run's and any a killed run orphaned.

    Best effort by design, and the ``suppress`` is the point rather than a shortcut: a
    teardown that raised because a GC job was still holding a sibling would replace a
    finished walk's result with a cleanup error, which is the failure reporting the wrong
    thing. What must not be skipped is the DROP itself; a leftover here holds a MERGED demo
    permit, and the sentence this module exists to prove is that the permit was not merged
    until a judge signed.
    """
    # `SHOW DATABASES` is read by POSITION and filtered in Python, not with a predicate on
    # a column name: CockroachDB calls that column `database_name` and PostgreSQL's
    # equivalent view calls it `datname`, so a `WHERE name LIKE …` is a sweep that raises
    # instead of sweeping — measured here as `42703 column "name" does not exist`, which
    # turned a finished walk into a teardown error. The first column of SHOW DATABASES is
    # the name on every version this repository runs against.
    with contextlib.suppress(psycopg.Error), psycopg.connect(admin_dsn, autocommit=True) as admin:
        stale = [
            str(row[0])
            for row in admin.execute("SHOW DATABASES").fetchall()
            if str(row[0]).startswith(WALK_PREFIX)
        ]
        for name in stale:
            with contextlib.suppress(psycopg.Error):
                admin.execute(f"DROP DATABASE IF EXISTS {name} CASCADE")


def _build_once(
    admin_dsn: str, database: str, dsn: str
) -> tuple[int, list[str], list[str], float, float]:
    """Create, apply the chain, apply the deployed seeds. Reports; refuses nothing."""
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        # The same zone the session fixture sets, for the same reason: a short GC TTL is
        # what a CockroachDB Cloud serverless database is configured with, and a walk that
        # ran under a different one would be a walk against a different storage policy.
        admin.execute(
            f"ALTER DATABASE {database} CONFIGURE ZONE USING "
            f"gc.ttlseconds = {fixture._CLOUD_GC_TTL_SECONDS}"
        )
    started = time.monotonic()
    applied, failures = fixture._apply_chain(dsn)
    chain_seconds = round(time.monotonic() - started, 1)
    started = time.monotonic()
    seed_failures = fixture._apply_seeds(dsn) if not failures else []
    seed_seconds = round(time.monotonic() - started, 1)
    return applied, failures, seed_failures, chain_seconds, seed_seconds


def _build(admin_dsn: str) -> tuple[str, str, int, float, float]:
    """Build the walk database, with ONE rebuild allowed, then fail with both censuses.

    THE REBUILD IS NOT A RETRY LOOP AND MUST NOT BECOME ONE. ``conftest._apply_chain``
    applies each of the 271 files in its own autocommit transaction and CONTINUES past a
    failure so it can report the whole census; one file that loses a schema-change race
    therefore takes every file that depends on it with it. Measured on TRAPPOINT on
    2026-08-14, on a node shared with five other workers' scratch databases and a queue of
    ``SCHEMA CHANGE GC`` jobs: the same tree applied **271/271** at 11:29 and **211/271** at
    11:47, the first failure being ``0149b_trg_person_measure_policy_append_only.sql
    [42P01] relation "mainline_meas.person_measure_policy" does not exist`` — a dependency
    that had itself failed moments earlier under contention.

    So a single census is not evidence about the migration tree, and this is the smallest
    thing that makes it one: build twice, into a SECOND fresh name, and if that fails too,
    say so with both counts. A chain that is genuinely broken fails both times and the
    report names it; a chain that lost a race applies cleanly on the retry. What is
    emphatically NOT done here is skipping, lowering a floor, or continuing against a
    partial schema — a walk against 211 of 271 migrations would be a walk against a
    database the deployment does not have, and every refusal it recorded would be about the
    wrong schema.
    """
    census = ""
    for attempt in (1, 2):
        database = _walk_database_name()
        dsn = fixture._dsn_for(admin_dsn, database)
        applied, failures, seed_failures, chain_seconds, seed_seconds = _build_once(
            admin_dsn, database, dsn
        )
        if not failures and not seed_failures:
            return database, dsn, applied, chain_seconds, seed_seconds
        census += (
            f" Attempt {attempt} ({database}): chain {applied}/{applied + len(failures)} "
            "applied"
            + (f", first failure {failures[0]}" if failures else "")
            + (f", seeds {seed_failures}" if seed_failures else "")
            + "."
        )
    raise AssertionError(
        "the deployed chain and seed did not build cleanly on EITHER attempt, into two "
        "freshly created databases, so this is the tree and not a schema-change race."
        + census
        + " The walk is not run against a partial schema: a refusal recorded against part "
        "of the chain names a constraint the deployment does not have, and the two seed "
        "files are what scripts/deploy/seed_demo.py applies to CockroachDB Cloud."
    )


def _maybe_write_evidence(walk: Walk) -> None:
    """Emit ``evidence/demo/judge-path-walk.json`` when this run was asked to."""
    target = os.environ.get(EVIDENCE_ENV, "").strip()
    if not target:
        return
    path = Path(target)
    if not path.is_absolute():
        path = REPO_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence_document(walk), indent=2) + "\n", encoding="utf-8")


def _arc_verdict(walk: Walk) -> tuple[str, dict[str, Any] | None]:
    """``(verdict, blocked_at)``, derived only from what was recorded.

    A record of a walk that did not finish must say so in its first few lines, or a later
    reader will quote its beat 1 as though the arc had closed. The predicate is deliberately
    narrow and mechanical — it asks each beat only for the outcome that beat is FOR — so
    that this function cannot become a second, softer copy of the assertions below.
    """
    expectations: tuple[tuple[int, str, Any, str], ...] = (
        (1, "status", 409, "the gate did not refuse the merge with the obligation open"),
        (2, "status", 200, "the disposition read did not answer"),
        # Beat 2's SUBSTANCE, checked before beats 3-5, because an empty vocabulary makes
        # every beat after it refuse for a reason that is not the one it was testing. A
        # verdict that named beat 4 here would send its reader to the sign path when the
        # debt is in the seed.
        (2, "offered", True, "the check offered no defeater vocabulary, so no judge could choose"),
        # Beat 3's SUBSTANCE, not merely its status: `422 demo_history_not_seeded` and
        # `422 unprocessable_request` are the same number and different findings, and only
        # the second is the membership refusal this beat is the control for.
        (3, "status", 422, "a code that was never offered was not refused"),
        (3, "message", "unprocessable_request", "the refusal was not the membership check"),
        (4, "status", 200, "the signature was not accepted"),
        (5, "status", 200, "the merge was not admitted after the signature"),
    )
    for index, attribute, expected, why in expectations:
        recorded = walk.beats.get(index)
        if recorded is None:
            return "INCOMPLETE", {"beat": index, "reason": "this beat was never reached"}
        observed = bool(walk.offered) if attribute == "offered" else getattr(recorded, attribute)
        if observed != expected:
            return "INCOMPLETE", {
                "beat": index,
                "reason": why,
                "field": attribute,
                "expected": expected,
                "observed": observed,
                "server_said": recorded.detail,
            }
    return "COMPLETE", None


def evidence_document(walk: Walk) -> dict[str, Any]:
    """The observation record, in the shape ``evidence/demo/judge-path-walk.json`` carries.

    Public because the committed artefact and this test must not be able to disagree
    about what was observed: the file is written from this function, by the run that made
    the observations.
    """
    verdict, blocked_at = _arc_verdict(walk)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "walk": "the judge path, end to end, through mainline_demo_api.app.handler",
        "verdict": verdict,
        "blocked_at": blocked_at,
        "driver": walk.driver,
        "database": walk.database,
        "subject": {"permit_id": walk.permit_id, "check_id": walk.check_id},
        "seconds": walk.seconds,
        "foreign_keys_onto_defeater_option": walk.foreign_keys_onto_defeater_option,
        "offered_vocabulary": walk.offered,
        "signed": walk.signed_payload,
        "beats": [
            {
                "beat": recorded.beat,
                "title": recorded.title,
                "request": recorded.request,
                "status": recorded.status,
                "outcome": recorded.outcome,
                "sqlstate": recorded.sqlstate,
                "constraint": recorded.constraint,
                "constraint_source": recorded.constraint_source,
                "message": recorded.message,
                "detail": recorded.detail,
                "read_back": recorded.read_back,
                "note": recorded.note,
            }
            for _, recorded in sorted(walk.beats.items())
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# BEAT 1 — the refusal the whole demo opens on
# ══════════════════════════════════════════════════════════════════════════════════════


def test_beat_1_the_merge_is_refused_while_the_obligation_is_open(judge_walk: Walk) -> None:
    """409, ``23514``, ``gate_closed_when_issued``, and the name came from the driver.

    ``demo_permit.sql``'s own header names this outcome — *"23514 on
    gate_closed_when_issued"* — so the expected values here are the seed's stated
    intention read from outside this file, not a transcription of what the code happened
    to do.

    ``constraint_source == 'reported'`` is the assertion that costs something. It means
    psycopg's ``Diagnostic.constraint_name`` carried the name, i.e. the DATABASE said it.
    ``'parsed'`` would mean it was read out of a message string, which is the honest
    fallback for a PL/pgSQL ``RAISE`` and the wrong answer for a plain CHECK. A refusal
    whose exhibit was composed by the application is the fabricated exhibit this
    repository refuses to produce.
    """
    beat = judge_walk.beat(1)
    assert beat.status == 409, f"expected a refusal, got {beat.status}: {beat.detail}"
    assert beat.outcome == "refused", beat.outcome
    assert beat.sqlstate == "23514", beat.sqlstate
    assert beat.constraint == "gate_closed_when_issued", beat.constraint
    assert beat.constraint_source == "reported", (
        "the constraint name must be the one the driver reported, not one this API parsed "
        f"out of a message: got {beat.constraint_source!r}"
    )
    assert beat.read_back["open_blocking"] == 1
    assert beat.read_back["merge_records"] == 0, "a refused merge must persist nothing"
    assert beat.read_back["dispositions"] == 0, (
        "the demo seeds no disposition; the obligation is open, which is what the gate has "
        "to refuse on"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# BEAT 2 — the vocabulary a judge chooses from
# ══════════════════════════════════════════════════════════════════════════════════════


def test_beat_2_the_disposition_offers_a_vocabulary(
    judge_walk: Walk, registry: SchemaRegistry
) -> None:
    """A non-empty ``defeater_options``, valid against the contract the console loads.

    This is blocker 1 in one assertion. With an empty array the console's declared path —
    ``a11y/contract.ts`` step ``id: 'defeater'``, inside the claim at line 288 that *"the
    complete path from the refusal to the signature … is operable with a keyboard
    alone"* — is broken at that step, and a judge cannot sign.
    """
    beat = judge_walk.beat(2)
    assert beat.status == 200, f"the disposition read failed: {beat.detail}"
    payload = judge_walk.disposition_payload
    schema_id = envelope.SCHEMA_IDS["disposition"]
    assert payload["schema_id"] == schema_id
    errors = registry.validate(schema_id, payload)
    assert errors == [], f"disposition violates {schema_id}:\n  " + "\n  ".join(errors[:12])

    assert judge_walk.offered, (
        "mainline.defeater_option holds no row for this check, so `defeater_options` is "
        "empty and a judge reaching the disposition screen cannot choose a defeater — and "
        "therefore cannot sign. The seed owes these rows: console/src/data/resources.ts "
        "describes the resource as carrying 'the per-check defeater vocabulary', "
        "src/app/surfaces.ts as 'a per-check defeater vocabulary with no global not "
        "applicable', types.generated.ts declares the member non-optional, and "
        "0064_defeater_option.sql says the vocabulary is 'generated per check, so no global "
        "N/A exists'. This assertion is upheld in kind; it is not weakened to == set()."
    )
    assert beat.read_back["signed"] is None, (
        "nothing is signed at beat 2 — the demo seeds no disposition, because signing is "
        "beat 4 and is performed in front of a judge"
    )


def test_beat_2_every_option_carries_a_question_rather_than_a_label(judge_walk: Walk) -> None:
    """``prompt`` is THE QUESTION, and 0064 is explicit about why that is not decoration.

    *"'Which precondition of this mechanism is absent?' is a question that can only be
    answered wrongly in a way a reviewer can see. A label — 'N/A', 'not applicable' —
    cannot be answered wrongly at all, which is exactly what makes it worthless."*
    ``defeater_prompt_stated`` refuses only the blank string, so the database enforces the
    weaker half; the sentence above is enforced here or nowhere.
    """
    assert judge_walk.offered, "no options were offered, so there are no prompts to check"
    for option in judge_walk.offered:
        code, prompt = str(option["defeater_code"]), str(option["prompt"])
        assert prompt.endswith("?"), (
            f"{code}'s prompt is not a question: {prompt!r}. 0064_defeater_option.sql — "
            "'prompt IS THE QUESTION, NOT A LABEL'. A statement here is a label with extra "
            "steps, and the CHECK constraint only refuses the empty string."
        )
        assert len(prompt.split()) >= 4, (
            f"{code}'s prompt is {prompt!r}, which is too short to be answerable wrongly in "
            "a way a reviewer can see"
        )
        assert prompt.strip().lower() not in {"n/a?", "not applicable?"}, (
            f"{code} offers the global escape hatch 0064 exists to make impossible"
        )
        assert code not in prompt, (
            f"{code}'s prompt restates the code rather than asking what it means: {prompt!r}"
        )


def test_beat_2_one_generation_means_one_digest(judge_walk: Walk) -> None:
    """Every offered row carries the SAME ``vocab_sha256``, and it is not the old constant.

    0064: *"vocab_sha256 IS THE SAME VALUE ON EVERY ROW OF ONE GENERATION. It digests the
    whole option set, not the row, so a signature that pins it pins the ALTERNATIVES the
    signer declined as well as the one they chose."* Several distinct values would mean two
    generations are interleaved and a signature pinning either would pin an option set that
    was never on one screen.
    """
    digests = {str(option["vocab_sha256"]) for option in judge_walk.offered}
    assert judge_walk.offered, "no options were offered, so there is no digest to be one of"
    assert len(digests) == 1, (
        f"{len(judge_walk.offered)} options carry {len(digests)} distinct vocab_sha256 "
        f"values {sorted(digests)}; 0064 says one generation carries one digest"
    )
    digest = digests.pop()
    assert len(digest) == 64 and int(digest, 16) >= 0, digest
    assert digest != CONSTANT_THAT_PINNED_NOTHING, (
        "the offered set's digest is sha256(b'defeater-vocab') — the SHA-256 of an ASCII "
        "string, which is what the deployed Cloud recorded on its one signed disposition. "
        "A constant pins nothing, and a vocabulary whose rows carry it was written to match "
        "the code rather than digested from the option set."
    )
    assert DEMO_DEFEATER_CODE in {str(o["defeater_code"]) for o in judge_walk.offered}, (
        f"{DEMO_DEFEATER_CODE} is not offered by this check, and beat 4 signs with it: "
        "gate_run.py hard-codes it into beat 4's INSERT, the captured Cloud SQL exhibit "
        "beat-4-merge-admitted-00000.txt records it as the ADMITTED merge's code, and a "
        "signature naming a code that was never offered is precisely the 'click-through "
        "with a signature on it' 0064's rationale exists to forbid"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# BEAT 3 — the control
# ══════════════════════════════════════════════════════════════════════════════════════


def test_beat_3_a_code_that_was_never_offered_is_refused(judge_walk: Walk) -> None:
    """422 with a stated reason, and NOTHING IN THE DATABASE WOULD HAVE CAUGHT IT.

    The second assertion is the control on the first. ``0066_disposition.sql`` gives
    ``defeater_code`` only ``CONSTRAINT disposition_defeater_code_stated CHECK
    (defeater_code <> '')`` — no foreign key onto ``mainline.defeater_option`` — so a
    signature naming a code no screen ever displayed reaches the row unopposed, records the
    digest of a set that did not contain it, commits, admits, and reports PROVEN. RULING
    R9 forbids adding the key four days from the deadline; this refusal is therefore the
    whole of the enforcement, and the ABSENCE it stands in for is asserted here so that the
    day somebody lands the migration, this test says so.
    """
    beat = judge_walk.beat(3)
    assert judge_walk.foreign_keys_onto_defeater_option == [], (
        "mainline.disposition now has a foreign key onto mainline.defeater_option "
        f"({judge_walk.foreign_keys_onto_defeater_option}). That is good news and it makes "
        "this test's premise stale: the refusal below is no longer the only thing standing "
        "between a signature and a code nobody offered. Re-read RULING R9, then decide "
        "whether this control keeps its second half."
    )
    assert beat.status == 422, f"expected a refusal, got {beat.status}: {beat.detail}"
    assert beat.message == "unprocessable_request", beat.message
    assert beat.detail and "is not offered by check" in beat.detail, beat.detail
    assert beat.sqlstate is None, (
        "a SQLSTATE here would mean the database refused this, and it cannot: there is no "
        f"constraint to refuse it. Got {beat.sqlstate!r}."
    )
    offered = {str(option["defeater_code"]) for option in judge_walk.offered}
    assert offered, "beat 3 proves nothing when nothing was offered"
    assert all(code in (beat.detail or "") for code in offered), (
        "the refusal must name what IS offered, or its reader has to go to the database to "
        f"find out what they could have said. Offered {sorted(offered)}, detail: {beat.detail}"
    )
    assert beat.read_back["dispositions"] == 0, "a refused signature must persist nothing"
    assert beat.read_back["open_blocking"] == 1, "and must not close the obligation"


# ══════════════════════════════════════════════════════════════════════════════════════
# BEAT 4 — the signature
# ══════════════════════════════════════════════════════════════════════════════════════


def test_beat_4_a_member_code_is_signed_and_committed(judge_walk: Walk) -> None:
    """200, ``committed``, one row, and the obligation is closed by the projection."""
    beat = judge_walk.beat(4)
    assert beat.status == 200, f"the signature was not accepted: {beat.detail}"
    assert beat.outcome == "committed", beat.outcome
    assert beat.read_back["disposition_rows"] == 1, beat.read_back
    assert beat.read_back["defeater_code"] == DEMO_DEFEATER_CODE
    assert beat.read_back["kind"] == "applied"
    assert beat.read_back["open_blocking"] == 0, (
        "the projection trigger did not close the counter, so the merge at beat 5 would be "
        "admitted or refused for a reason other than the signature"
    )


def test_beat_4_the_signature_pins_the_vocabulary_that_was_offered(judge_walk: Walk) -> None:
    """THE HALF OF THIS DEFECT THAT WAS INVISIBLE. The digest is the offered set's, not a constant.

    ``0064_defeater_option.sql``: the column *"digests the whole option set, not the row, so
    a signature that pins it pins the ALTERNATIVES the signer declined as well as the one
    they chose"*. ``disposition.schema.json``: *"Pins WHICH vocabulary was offered. A
    disposition records the same digest, so a later regeneration cannot silently
    reinterpret a past signature."*

    Both sentences were FALSE of this code until 2026-08-14. ``gate_run.py:608`` and
    ``transitions.py:1065`` bound ``_sha("defeater-vocab")``, and the deployed CockroachDB
    Cloud duly recorded that constant on its one signed disposition. Seeding the rows
    without closing this would have moved the visible half of the defect and left the
    invisible half, so the negative assertion below is the one that matters most: it is
    the only one that fails if the constant comes back.

    The positive half is cross-checked between two surfaces — the digest on the committed
    ROW against the digest the READ API offered at beat 2 — rather than against a literal
    in this file. A test that recomputed the digest itself would agree with any code that
    computed it the same way, which is character for character the credential defect that
    put ``23503`` in front of a judge behind 291 green tests.
    """
    beat = judge_walk.beat(4)
    recorded = beat.read_back["defeater_vocab_sha256"]
    offered = {str(option["vocab_sha256"]) for option in judge_walk.offered}
    assert offered, "nothing was offered, so there is no digest the signature could pin"
    assert recorded == offered.pop(), (
        f"the signature recorded {recorded!r}, which is not the digest the disposition read "
        "offered this judge. A disposition that pins a vocabulary other than the one on the "
        "screen is internally inconsistent, and nothing in the database would notice."
    )
    assert recorded != CONSTANT_THAT_PINNED_NOTHING, (
        "the signature recorded sha256(b'defeater-vocab') — the SHA-256 of an ASCII string, "
        "byte-for-byte what the deployed Cloud recorded before this wave. That value pins "
        "no vocabulary: it would be identical for every check, every generation and every "
        "option set, so a later regeneration could silently reinterpret this signature and "
        "the digest would not move."
    )


def test_beat_4_the_read_surface_shows_the_signature_the_console_would_render(
    judge_walk: Walk,
) -> None:
    """The console reads ``signed`` off the same resource, so the arc has to close there too.

    Beat 4's response says ``committed``. This asserts the GET a judge's browser performs
    next reports the same signature — the difference between a transition that committed
    and a screen that shows it, which have been separately broken in this repository
    before.
    """
    signed = judge_walk.signed_payload
    assert signed is not None, (
        "GET /v1/checks/{check_id}/disposition still reports `signed: null` after a "
        "committed signature, so the console would show an unsigned obligation over a "
        "signed row"
    )
    recorded = judge_walk.beat(4).read_back["defeater_vocab_sha256"]
    assert signed["defeater_code"] == DEMO_DEFEATER_CODE
    assert signed["defeater_vocab_sha256"] == recorded
    assert signed["defeater_vocab_sha256"] != CONSTANT_THAT_PINNED_NOTHING
    assert signed["rationale"] == RATIONALE
    assert signed["retracted_by"] is None


# ══════════════════════════════════════════════════════════════════════════════════════
# BEAT 5 — the admission
# ══════════════════════════════════════════════════════════════════════════════════════


def test_beat_5_the_same_merge_is_admitted(judge_walk: Walk) -> None:
    """The identical request that was refused at beat 1, admitted — and nothing else moved.

    A gate that always refuses is broken, not safe. The whole product is the difference
    between these two responses, and the only thing that changed between them is one
    signature over a code the check offered.
    """
    first, last = judge_walk.beat(1), judge_walk.beat(5)
    assert first.request == last.request, (
        "beat 5 must be the SAME request as beat 1, or the difference between refusal and "
        f"admission is not the signature: {first.request} vs {last.request}"
    )
    assert last.status == 200, f"the merge was not admitted: {last.detail}"
    assert last.outcome == "committed", last.outcome
    assert last.sqlstate is None and last.constraint is None, (
        f"an admitted merge reports no refusal exhibit: {last.sqlstate} {last.constraint}"
    )
    assert last.read_back["permit_state"] == "merged"
    assert last.read_back["open_blocking"] == 0
    assert last.read_back["merge_records"] == 1


def test_beat_5_the_clearance_digest_was_computed_by_the_server(judge_walk: Walk) -> None:
    """``mainline.merge_permit`` step 4 digests the cleared set; this program supplied none of it.

    It is SHA-256 over the sorted ``(check_id, disposition_id)`` pairs — exactly which
    obligations were cleared and by which signatures at the instant of the merge. The
    assertion that it is not the digest of the empty string is what makes it a claim about
    this walk: a subject with no obligations digests ``''``, so that value would mean the
    merge recorded a clearance set with nothing in it.
    """
    digest = judge_walk.beat(5).read_back["clearance_digest"]
    assert isinstance(digest, str) and len(digest) == 64, digest
    assert int(digest, 16) >= 0
    assert digest != hashlib.sha256(b"").hexdigest(), (
        "the clearance digest is SHA-256 of the empty string, which is what a merge over "
        "NO cleared obligations records. This walk cleared one."
    )
    assert judge_walk.beat(5).read_back["merged_commit"], "the merge recorded no commit"


# ══════════════════════════════════════════════════════════════════════════════════════
# what this module promises about everything it did not own
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_shared_deployed_seed_database_is_untouched_by_this_walk(
    judge_walk: Walk,  # noqa: ARG001 - ordering, not data: this must run AFTER the arc
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """The session's deployed-seed database still has an unsigned, unmerged demo subject.

    Depends on ``judge_walk`` so that it runs AFTER the arc, not before it. This is the
    assertion that ``mainline.disposition`` holds no rows where it matters: the shared
    database is cached across sessions by fingerprint and read by every other module in
    this suite, and a disposition left in it would delete the demo's first beat for the
    next reader — silently, because the counter would simply be zero and the gate would
    have nothing to refuse.
    """
    dsn, seed = demo_database
    with psycopg.connect(dsn, autocommit=True) as conn:
        dispositions = conn.execute("SELECT count(*) FROM mainline.disposition").fetchone()
        merges = conn.execute("SELECT count(*) FROM mainline.merge_record").fetchone()
        permit = conn.execute(
            "SELECT state::STRING, open_blocking FROM mainline.permit WHERE permit_id = %s",
            (seed["permit_id"],),
        ).fetchone()
    assert dispositions is not None and dispositions[0] == 0, (
        "mainline.disposition is not empty in the SHARED database. demo_permit.sql seeds no "
        "disposition because that absence is what beat 1 refuses on; a row here means this "
        "walk — or something like it — signed into the database the rest of the suite reads."
    )
    assert merges is not None and merges[0] == 0, "the shared demo permit has been merged"
    assert permit is not None
    assert permit[0] == "dispositioned", permit[0]
    assert permit[1] == 1, (
        f"open_blocking is {permit[1]} in the shared database; the demo's one obligation "
        "must still be open"
    )


def test_the_walk_was_driven_through_the_router_and_not_around_it() -> None:
    """The three routes this file drives are the three the console addresses.

    Asserted against ``app.ROUTES`` rather than against strings in this file, so a router
    that stopped declaring one of them fails here instead of turning a beat into a 404
    that this module would have reported as a product refusal.
    """
    declared = {(route.method, route.template) for route in app.ROUTES}
    for method, template in (
        ("GET", "/v1/checks/{check_id}/disposition"),
        ("POST", "/v1/checks/{check_id}/disposition"),
        ("POST", "/v1/permits/{permit_id}/merge"),
    ):
        assert (method, template) in declared, (
            f"{method} {template} is not in app.ROUTES, so the beat this file drives over "
            "it would have been answered 404 by the router rather than by the product"
        )


def test_the_evidence_document_records_what_was_observed(judge_walk: Walk) -> None:
    """The committed artefact and this walk cannot disagree: one function builds both.

    Also the assertion that the record separates what was MEASURED from what was STAGED.
    An evidence file that does not draw that line is a file a reader has to take on trust,
    and the captured Cloud exhibits draw it explicitly — which is the standard here.
    """
    document = evidence_document(judge_walk)
    assert [beat["beat"] for beat in document["beats"]] == [1, 2, 3, 4, 5]
    assert json.loads(json.dumps(document)) == document, "the record does not round-trip"
    for beat in document["beats"]:
        assert beat["note"], f"beat {beat['beat']} records no note"
        assert "MEASURED" in beat["note"] or "STAGED" in beat["note"], beat["note"]
    assert document["driver"].startswith("psycopg ")
    assert document["foreign_keys_onto_defeater_option"] == []
    assert document["offered_vocabulary"], "the record names no offered vocabulary"
    assert document["verdict"] == "COMPLETE", (
        "the walk did not close the arc, and the record says where it stopped: "
        f"{document['blocked_at']}. A record whose verdict is INCOMPLETE is a truthful "
        "artefact and an unfinished demo; it is not evidence that a judge can sign."
    )
    assert document["blocked_at"] is None
