# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The twelve reads, against a real migrated CockroachDB, checked against the real contracts.

THE CENTRAL TEST IS :func:`test_every_read_satisfies_its_committed_contract`. It runs each
of the twelve resources against a database built by applying every migration in
``verticals/mainline/db/migrations`` and seeded with a history that has something true to
say about all of them, then validates the response with the JSON Schema files the CONSOLE
loads — not a copy, not a subset, the same files ``src/data/schema.ts`` reads. A payload
that fails there is a payload the deployed console would refuse, and it should fail here
first.

Everything after it asserts something the schema cannot: that the constraint names came
from the catalog rather than from a list in Python, that the ancestor cap was parsed out
of a CHECK, that the inclusion proofs actually verify against the checkpoint root, that
the one hand-authored sentence in the silence payload is flagged and explained, and that
the resource with no producer tables is staged in full rather than served as an empty
list.

Every test in this module needs a cluster and skips with the reason there is none.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from mainline_demo_api import app, envelope, health, reads
from mainline_demo_api import db as demo_db

from conftest import MIGRATIONS_DIR, REPO_ROOT, SchemaRegistry

pytestmark = pytest.mark.requires_cluster

#: A lesson id for the staged propagation surface. Any UUID: no row is looked up, which
#: is exactly the property the staged flag exists to declare.
_LESSON_ID = "11111111-2222-4333-8444-555555555555"

#: The deploy program that writes the second migration ledger `/v1/health` reads. Its DDL
#: is borrowed rather than restated, so the marker table this suite builds is the marker
#: table the deploy builds.
CLOUD_CHAIN_PY = REPO_ROOT / "scripts" / "deploy" / "cloud_chain.py"


def _load_cloud_chain() -> ModuleType:
    """Load ``scripts/deploy/cloud_chain.py`` by path — ``scripts/`` is not a package.

    Import-time it is stdlib plus ``psycopg`` and a handful of constants; everything that
    touches a cluster, a secret or ``.env`` is behind ``main()``.

    Registered in ``sys.modules`` BEFORE execution: ``cloud_chain`` declares dataclasses,
    and ``dataclasses`` resolves a ``ClassVar`` annotation by looking its own module up in
    ``sys.modules``. Without the registration that lookup returns ``None`` and the import
    dies in the standard library with ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` — measured, not anticipated.
    """
    name = "mainline_cloud_chain_for_tests"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, CLOUD_CHAIN_PY)
    assert spec is not None and spec.loader is not None, CLOUD_CHAIN_PY
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def _dsn_for(admin: str, database: str) -> str:
    """*admin* with its path segment replaced by *database*. No credential is touched."""
    parts = urlsplit(admin)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _requests(seed: dict[str, str]) -> dict[str, tuple[dict[str, str], dict[str, str]]]:
    return {
        "permit": ({"permit_id": seed["permit_id"]}, {}),
        "change_request": ({"cr_id": seed["cr_id"]}, {}),
        "blocking_checks": ({"permit_id": seed["permit_id"]}, {}),
        "disposition": ({"check_id": seed["check_id"]}, {}),
        "exposure_receipt": ({"receipt_id": seed["receipt_id"]}, {}),
        # THE COMMIT THE BLOCKING CHECK CITES, which is the commit the CONSOLE addresses:
        # `features/gate/useGateData.ts` builds this very request with
        # `commit_id: subjectCheck?.commit_id`. `conftest._CHECK_SQL` reads `commit_id` off
        # that same `mainline.blocking_check` row, so the fixture and the console name one
        # commit. This used to read `seed["commit_v2"]`, a survivor of the parallel world
        # `5ddaa3a`'s conftest built; see docs/decisions/demo-clause-version-singleton.md.
        "clause_version": (
            {"clause_uuid": seed["clause_uuid"], "commit_id": seed["commit_id"]},
            {},
        ),
        "clause_ancestry": ({"clause_uuid": seed["clause_uuid"]}, {}),
        "ledger": ({}, {"site_code": seed["site_code"]}),
        "silence": ({"permit_id": seed["permit_id"]}, {}),
        "recall_run": ({"run_id": seed["run_id"]}, {}),
        "propagation": ({"lesson_id": _LESSON_ID}, {}),
        "audit": ({}, {}),
    }


@pytest.fixture(scope="session")
def payloads(demo_database: tuple[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Every read, performed once, against the session's database.

    Session-scoped because these are reads: performing them per test would assert nothing
    a single run does not, and would multiply a 12-statement suite into a 400-statement
    one. Each test below inspects the same twelve envelopes.
    """
    dsn, seed = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        return {
            key: reads.read_resource(conn, key, params, query)
            for key, (params, query) in _requests(seed).items()
        }
    finally:
        demo_db.reset_dsn_cache()


# ── The central test ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", sorted(reads.READS))
def test_every_read_satisfies_its_committed_contract(
    key: str, payloads: dict[str, dict[str, Any]], registry: SchemaRegistry
) -> None:
    """The payload must satisfy the exact ``$id`` the console will look it up by."""
    payload = payloads[key]
    schema_id = envelope.SCHEMA_IDS[key]
    assert payload["schema_id"] == schema_id
    assert payload["resource"] == key
    assert payload["envelope_version"] == 1
    errors = registry.validate(schema_id, payload)
    assert errors == [], f"{key} violates {schema_id}:\n  " + "\n  ".join(errors[:12])


@pytest.mark.parametrize("key", sorted(reads.READS))
def test_every_read_survives_the_clients_own_post_conditions(
    key: str, payloads: dict[str, dict[str, Any]]
) -> None:
    """The four checks ``transport.ts::finishExchange`` performs, in its order.

    A payload that fails any of them is refused at the client with a message about
    unverifiable claims, at deploy time. The point of restating them here is that they
    fail in CI instead.
    """
    payload = payloads[key]
    assert json.loads(json.dumps(payload)) == payload, "payload does not round-trip through JSON"
    assert payload["resource"] == key
    assert payload["schema_id"] == envelope.SCHEMA_IDS[key]
    assert payload["server_date"].endswith("Z"), payload["server_date"]


@pytest.mark.parametrize("key", sorted(reads.READS))
def test_every_provenance_pointer_addresses_something_real(
    key: str, payloads: dict[str, dict[str, Any]]
) -> None:
    """A chip beside nothing is worse than no chip.

    Every pointer is resolved against ``data`` as RFC 6901, and every chip is checked
    against the closed vocabulary. The contract permits an unclaimed field; it does not
    permit a claim about a field that is not there.
    """
    payload = payloads[key]
    for entry in payload["provenance"]:
        assert entry["chip"] in envelope.PROVENANCE_CHIPS
        node: Any = payload["data"]
        for segment in entry["pointer"].lstrip("/").split("/"):
            token = segment.replace("~1", "/").replace("~0", "~")
            if isinstance(node, list):
                assert token.isdigit(), f"{key}: {entry['pointer']} indexes a list with {token!r}"
                assert int(token) < len(node), f"{key}: {entry['pointer']} is out of range"
                node = node[int(token)]
            else:
                assert isinstance(node, dict), f"{key}: {entry['pointer']} descends into a scalar"
                assert token in node, f"{key}: {entry['pointer']} addresses nothing"
                node = node[token]


@pytest.mark.parametrize("key", sorted(reads.READS))
def test_no_read_silently_drops_a_provenance_claim(
    key: str, payloads: dict[str, dict[str, Any]]
) -> None:
    """On the seeded fixture nothing should be near the 256-pointer cap.

    The cap is real and the behaviour past it is deliberate, but a fixture that hits it
    would mean the tests above are checking a truncated list without saying so.
    """
    assert len(payloads[key]["provenance"]) <= envelope.PROVENANCE_CAP


# ── What the schema cannot assert ───────────────────────────────────────────────────


def test_the_permit_gate_constraints_come_from_the_catalog(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """Seven named refusals — the six gate constraints plus ``merge_evidence``.

    Selected by the predicate mentioning ``'merged'``, not by a list in Python: thirteen
    CHECKs are declared on ``mainline.permit`` and six of them (``ctr_nonneg``,
    ``permit_commit_sized``, …) are not gate refusals. The names and predicates below are
    ``pg_get_constraintdef``'s words.
    """
    data = payloads["permit"]["data"]
    by_name = {entry["constraint"]: entry for entry in data["constraints"]}
    assert set(by_name) == {
        "gate_closed_when_issued",
        "identity_conserved_when_issued",
        "conflicts_resolved_when_issued",
        "no_open_warrant_when_issued",
        "boundary_certified_when_issued",
        "reading_floor_when_issued",
        "merge_evidence",
    }

    gate = by_name["gate_closed_when_issued"]
    assert gate["counters"] == [
        {"column": "open_blocking", "value": data["counters"]["open_blocking"]}
    ]
    assert "open_blocking = 0" in gate["predicate"].replace("(", "").replace(")", "")
    # merge_evidence reads no counter at all, and the contract permits the empty array.
    assert by_name["merge_evidence"]["counters"] == []
    # reading_floor_when_issued reads two.
    assert {entry["column"] for entry in by_name["reading_floor_when_issued"]["counters"]} == {
        "unmet_floor_count",
        "countersigned_count",
    }
    # A GET carries no refusal payload, so nothing is blamed and the flag is `derived`.
    assert all(entry["blamed_by_refusal"] is False for entry in data["constraints"])
    chips = {entry["pointer"]: entry["chip"] for entry in payloads["permit"]["provenance"]}
    assert chips["/constraints/0"] == "db:constraint"
    assert chips["/counters/open_blocking"] == "db:column"


def test_the_projected_counter_agrees_with_the_re_derivation(
    payloads: dict[str, dict[str, Any]], demo_database: tuple[str, dict[str, str]]
) -> None:
    """P2 in one assertion: the counter is a PROJECTION, and here it agrees with the truth.

    THE SEED NEVER WRITES ``mainline.permit.open_blocking``. ``demo_permit.sql`` says so in
    its own header — *"THE COUNTER IS NOT WRITTEN HERE"* — and names the trigger that does:
    ``check_materialised`` (migration 0121 → ``mainline.fn_check_materialised``) raises it to
    1 when the blocking check is inserted. Nothing lowers it again, because **the demo seeds
    no disposition at all**. The obligation is left open so that a judge closes it, and the
    same header spells the three outcomes out — ``23514`` on ``gate_closed_when_issued``,
    then ``P0001`` from the re-derivation when the counter is forced to zero out of band,
    then ``00000`` *"after one signed disposition against ``dec0de00-0007-…``"*. That last
    one is beat 4. It belongs to the demo, not to the seed.

    THIS TEST USED TO ASSERT ``state == 'draft'`` AND A COUNTER OF ZERO, and both were
    readings of the parallel world the old conftest built at ``5ddaa3a``, in which the
    FIXTURE signed a disposition. The rewrite that made the fixture apply the deployment's
    own seed deleted that world; this file was not updated. See
    ``docs/decisions/demo-clause-version-singleton.md`` §5 — this is the same survivor class
    as ``commit_v2``, found by the same fixture refusing to invent a subject.

    ``mainline.subject_state`` has no member called ``open``: the alphabet is draft /
    checks_materialised / dispositioned / merged / suspended / closed / abandoned (migration
    0011), and ``dispositioned`` is the state in which the client CLAIMS every obligation now
    carries a signed disposition. It does not. That claim is precisely what the gate exists
    to disbelieve, and the whole demo is the database checking it instead of believing it.

    The second assertion is the interesting one, and it is the whole product in miniature:
    the projected counter and the count re-derived from the base tables agree. It is also
    STRICTLY STRONGER here than it was at zero. ``0 == 0`` is satisfied by a permit that has
    no obligations at all — by a projection that never counted anything — whereas ``1 == 1``
    is satisfied only by a projection that actually counted the open one. The gate's third
    beat is what happens when the two disagree.
    """
    import psycopg

    data = payloads["permit"]["data"]
    checks = payloads["blocking_checks"]["data"]["checks"]
    assert data["state"] == "dispositioned"
    assert len(checks) == 1, "one obligation was materialised"
    assert data["counters"]["open_blocking"] == sum(1 for check in checks if check["open"]) == 1

    dsn, seed = demo_database
    with psycopg.connect(dsn, autocommit=True) as raw:
        trigger = raw.execute(
            "SELECT count(*) FROM information_schema.triggers "
            "WHERE event_object_schema = 'mainline' AND event_object_table = 'blocking_check' "
            "AND trigger_name = 'check_materialised'"
        ).fetchone()
        rederived = raw.execute(
            "SELECT count(*) FROM mainline.blocking_check bc "
            " WHERE bc.permit_id = %s "
            "   AND NOT EXISTS (SELECT 1 FROM mainline.disposition d "
            "                    WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL)",
            (seed["permit_id"],),
        ).fetchone()
    assert trigger is not None and trigger[0] == 1, (
        "the projection trigger is absent, so the counter above was written by nobody. "
        "Before W1 produced mainline_ops.outbox, 0121_trg_check_materialised.sql could not "
        "apply and this was the true state of the tree."
    )
    assert rederived is not None
    assert data["counters"]["open_blocking"] == rederived[0]


def test_the_change_request_gate_is_smaller_and_says_so(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """Three counters and four named refusals. A smaller gate is still a gate."""
    data = payloads["change_request"]["data"]
    assert set(data["counters"]) == {"open_blocking", "open_residue", "open_conflicts"}
    assert {entry["constraint"] for entry in data["constraints"]} == {
        "cr_merge_evidence",
        "cr_gate_closed_when_merged",
        "cr_identity_conserved_when_merged",
        "cr_conflicts_resolved_when_merged",
    }


def test_open_is_derived_and_the_projections_are_columns(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """``severity``/``virulence``/``closure_gen`` are overwritten by ``fn_check_project``.

    ``demo_world.sql`` inserts the check with a severity and a virulence of its own choosing;
    the closure bands it ``blood_major`` at severity 4 and the trigger overwrites both on the
    way in. That is why ``db:column`` is the right chip: nobody who wrote the check chose
    these.

    ``open`` AND ``disposition_id`` ARE THE OTHER HALF, and they are ``derived`` rather than
    columns — no such columns exist. ``open`` is *"no non-retracted disposition names this
    check"*, and on the deployed seed that is TRUE: ``mainline.disposition`` holds **no
    rows**, by design (``demo_permit.sql``: ``disposition = NO ROWS``). So the positive claim
    this test makes is that the reader DERIVED an open check from an empty table rather than
    reporting a column, and that it reports ``None`` for the disposition it does not have
    instead of inventing one.

    THIS USED TO ASSERT THE OPPOSITE — ``open is False``, a non-null ``disposition_id`` and a
    precursor ``'INC-W3-1'`` — because the old conftest at ``5ddaa3a`` signed a disposition
    in the fixture and named its own incident after its own worker. The deployed seed's
    incident is ``DEMO-INC-0001``. Same survivor class as ``commit_v2``; see
    ``docs/decisions/demo-clause-version-singleton.md`` §5.
    """
    data = payloads["blocking_checks"]["data"]
    assert len(data["checks"]) == 1
    check = data["checks"][0]
    assert check["severity"] == 4
    assert check["virulence"] == "blood_major"
    assert check["open"] is True, (
        "the demo seeds NO disposition — the obligation is left open so that beat 4 signs it "
        "in front of a judge — so an open check here is the gate having something to refuse"
    )
    assert check["disposition_id"] is None, (
        "no disposition row names this check, and the honest report of that is null rather "
        "than an identifier for a row that is not there"
    )
    assert check["precursor"]["external_ref"] == "DEMO-INC-0001"

    chips = {entry["pointer"]: entry["chip"] for entry in payloads["blocking_checks"]["provenance"]}
    assert chips["/checks/0/open"] == "derived"
    assert chips["/checks/0/disposition_id"] == "derived"
    assert chips["/checks/0"] == "db:column"


def test_the_disposition_carries_the_lattice_and_the_projected_requirements(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """The lattice is every row for the virulence; a missing pair is a NON-EXISTENT option.

    ⚠ THIS TEST IS EXPECTED TO FAIL ON THE DEPLOYED SEED, AND THE FAILING ASSERTION IS LEFT
    STANDING DELIBERATELY. ``mainline.defeater_option`` holds **zero rows**, so the
    ``defeater_options`` assertion below fails. It has NOT been moved to match the seed,
    because on this one the seed is the side that is wrong. The evidence is entirely outside
    both the seed and this file:

    * ``0064_defeater_option.sql`` — *"generated per check, so no global 'N/A' exists"*. The
      vocabulary is per check by construction and there is no fallback anywhere.
    * ``console/src/a11y/contract.ts`` declares step ``id: 'defeater'`` —
      *"choose a defeater from the per-check vocabulary"*, ``pointerOnly: false`` — inside
      the path it asserts is *"the complete path from the refusal to the signature … with no
      pointer-only step"*. With an empty vocabulary that step has nothing to operate on and
      the declared path is broken at it.
    * ``console/src/app/surfaces.ts`` describes the disposition surface as carrying *"a
      per-check defeater vocabulary with no global 'not applicable'"*, and
      ``resources.ts`` describes the resource itself as carrying *"the per-check defeater
      vocabulary"*. ``types.generated.ts`` declares ``defeater_options`` non-optional.
    * **Nothing in this tree writes a ``mainline.defeater_option`` row** — not the seed, not
      a migration, not the runtime. Verified by search.

    So a judge who reaches the disposition screen cannot choose a defeater, and therefore
    cannot sign. Under the tiebreaker this repository already uses — the console is the
    authority for what the demo must CARRY — the seed owes this row set. Weakening this
    assertion to ``== set()`` would convert a real, currently-visible defect into a permanent
    invisible one, which is the single thing this repository has been burned by most. It is
    reported instead, and it belongs to ``demo_world.sql``'s owner.

    Everything after the ``defeater_options`` line was ALSO a reading of the old parallel
    world and has been corrected, so that when the vocabulary is seeded this test goes green
    on that change alone rather than requiring a second archaeology pass.
    """
    data = payloads["disposition"]["data"]
    assert data["virulence"] == "blood_major"
    assert {row["virulence"] for row in data["lattice"]} == {"blood_major"}
    assert len(data["lattice"]) >= 1
    # RE-BASELINED 2026-08-14 to the vocabulary the seed now offers, and this is the one
    # direction of travel the no-shortcut rule polices, so the reasoning is recorded here
    # rather than left to the diff.
    #
    # `MECHANISM_PRESENT_AND_VERIFIED` was never in question: the runtime, the proof seeder,
    # and the captured Cloud exhibit `beat-4-merge-admitted-00000.txt` (outcome ADMITTED) all
    # already name it, so the vocabulary had to offer it or beat 4 would sign a code that was
    # never on a screen. `SCOPE_EXCLUDES_HAZARD` was the opposite case: a repo-wide search put
    # it in exactly TWO places — this assertion, and `qa/cluster-known-red.json` quoting this
    # assertion's own failure text. It appears in no schema, no console file, no migration, no
    # runtime module, no capture and no document. It was a code this test invented and nothing
    # else ever offered, so seeding it to satisfy the assertion would have been the seed being
    # reshaped to match a test — the exact move that was caught and reverted on 2026-08-13,
    # merely pointing the other way.
    #
    # The three below are authored from the demo's own facts, per 0064's rule that a
    # vocabulary is generated PER CHECK so that a universal escape hatch would have to be
    # written specifically for this mechanism at this severity. The clause reads *"Before any
    # intrusive work, stored energy shall be isolated, locked and verified at zero by a
    # competent person"* (anchors LOTO, ZERO_ENERGY; severity 4; blood_major), and these are
    # the three ways that obligation can legitimately not bind — one per clause of the
    # sentence. None of them means "not applicable"; there is no such row in this product.
    assert {option["defeater_code"] for option in data["defeater_options"]} == {
        "ENERGY_SOURCE_ABSENT",
        "MECHANISM_PRESENT_AND_VERIFIED",
        "WORK_NOT_INTRUSIVE",
    }
    # The digest is the same on every row of one generation (0064), because it digests the
    # SET — so a signature pinning it pins the alternatives declined, not just the choice.
    assert len({option["vocab_sha256"] for option in data["defeater_options"]}) == 1, (
        "the options carry more than one vocab_sha256, so two generations are interleaved "
        "and a signature pinning either would pin a set that was never on one screen"
    )
    assert data["reading_floor"] is None, "S19's components are on no table in this tree"

    # NO SIGNATURE IS SEEDED. `mainline.disposition` holds no rows — `demo_permit.sql` says
    # `disposition = NO ROWS` — because signing is beat 4, performed in front of a judge.
    # `null` here is the positive claim that nothing has been signed yet; a fabricated
    # `signed` block would be the demo asserting the obligation was already answered, which
    # is the exact claim the gate exists to disbelieve.
    assert data["signed"] is None, (
        "the demo seeds no disposition, so the honest report is that this check carries no "
        "signature — not a signature block with nulls in it"
    )
    # The lattice is still fully populated even with nothing signed: it is the clearance
    # rows for the virulence, and it is what TELLS a signer what signing will require.
    lattice_applied = next(row for row in data["lattice"] if row["kind"] == "applied")
    assert lattice_applied["req_second_signer"] is not None
    assert lattice_applied["min_signer_rank"] is not None


def test_the_exposure_receipt_renders_its_hlc_as_an_exact_string(
    payloads: dict[str, dict[str, Any]],
) -> None:
    data = payloads["exposure_receipt"]["data"]
    assert isinstance(data["issued_hlc"], str)
    assert data["total_tokens"] == 200
    assert len(data["lines"]) == 1
    assert data["swept_at"] is None, "nothing has swept this receipt"
    assert len(data["receipt_digest"]) == 64


def test_the_clause_version_reports_its_witnesses_as_a_positive_claim(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """``[]`` and ``null`` are different sentences and this API makes the stronger one.

    THE DEMO HAS EXACTLY ONE CLAUSE VERSION. It is an ORIGIN version — ``gen`` 1,
    ``control_delta`` ``introduce``, anchors ``['LOTO', 'ZERO_ENERGY']``, no parent — and the
    ruling that it stays that way, with the console evidence that decided it, is
    ``docs/decisions/demo-clause-version-singleton.md``. This test previously described a
    second, ``strengthen`` version carrying a ``WITNESS`` anchor and an ``R6_VERIFICATION``
    witness. No such row has ever been in the deployed seed; the description survived the
    deletion of the parallel world the old conftest built at ``5ddaa3a``.

    THE POSITIVE CLAIM THE NAME PROMISES IS MADE HERE, AND IT IS SHARPER ON THIS SEED THAN
    IT WAS ON THE INVENTED ONE, because on this seed the witness list is EMPTY and an empty
    list is exactly where ``[]`` and ``null`` stop being interchangeable:

    * ``clause.schema.json`` ``$defs.delta_verdict`` — *"``witnesses`` may be null … which
      the console renders as WITNESS UNAVAILABLE. An empty array is a DIFFERENT claim: the
      emitter says there are none."*
    * ``console/src/features/diff/engine/witness.ts`` turns that into three states:
      ``witnesses === null ? 'unavailable' : witnesses.length === 0 ? 'asserted_none' :
      'present'``, and ``parts/WitnessTable.tsx`` renders **WITNESS UNAVAILABLE** for the
      first and **NO WITNESSES** — *"the emitter reports that there are none. That is a
      claim, and it is a different claim from an absent witness member"* — for the second.

    So ``witnesses == []`` asserts the console shows NO WITNESSES rather than WITNESS
    UNAVAILABLE. A reader that stopped querying ``mainline.delta_witness`` and emitted
    ``null`` would still satisfy the schema and would still render a screen — the wrong one.
    This catches that.

    ``minimal is None`` IS THE FALSIFIABLE ONE. ``read_clause_version`` computes it as
    ``all(minimal_flags) if minimal_flags else None``, and in Python ``all([])`` is ``True``.
    Drop the guard and this payload claims the empty witness set is a MINIMAL unsatisfiable
    subset — an unproven claim of minimality, which the contract calls *"worse than none"*.
    The assertion below is the only thing standing between that one-token edit and a demo
    that asserts a proof it never performed.
    """
    payload = payloads["clause_version"]
    data = payload["data"]
    version = data["version"]

    # The commit this payload is ABOUT is the commit the blocking check cites — the same
    # addressing `features/gate/useGateData.ts` performs when it builds this very request as
    # `commit_id: subjectCheck?.commit_id`. Cross-checked between two payloads rather than
    # against a literal, so a seed that re-pointed one and not the other fails here.
    assert version["commit_id"] == payloads["blocking_checks"]["data"]["checks"][0]["commit_id"]

    assert version["gen"] == 1
    assert version["control_delta"] == "introduce"
    assert version["delta_basis"] == "lattice"
    assert version["anchor_set"] == ["LOTO", "ZERO_ENERGY"]

    # AN ORIGIN VERSION, ASSERTED AS SUCH — which takes BOTH halves. `comparabilityOf()` in
    # `features/diff/engine/build.ts` reads `origin_version` only when the version NAMES no
    # parent *and* none was carried; a version that names one and carries none is
    # `parent_unresolved`, a different console screen ("NO DIFF — ANCESTOR NOT CARRIED"
    # against "NO DIFF — ORIGIN VERSION"). Asserting `parent is None` alone would be
    # satisfied by the broken one too, so both are asserted.
    assert version["parent_version"] is None, "an origin version names no parent"
    assert data["parent"] is None, "and so none is carried: this is `origin_version`"

    # `[]` and `null` are different sentences. This is the stronger one.
    assert data["delta"]["witnesses"] == [], (
        "the reader queried mainline.delta_witness and found no rows, so it asserts THERE "
        "ARE NONE. `null` would be WITNESS UNAVAILABLE — the emitter saying nothing — and "
        "the console renders a different panel for it"
    )
    assert data["delta"]["witnesses"] is not None
    assert data["delta"]["minimal"] is None, (
        "minimality of an empty witness set is not established by the absence of rows. "
        "`all([])` is True, so an unguarded `all(minimal_flags)` would claim it here"
    )

    # The verdict and the columns agree. `collectFindings` raises `verdict_disagrees_with_
    # column` / `basis_disagrees_with_column` as DISCREPANCIES when they do not, so these
    # two are the red panels a judge would otherwise be the first to see.
    assert data["delta"]["delta"] == version["control_delta"]
    assert data["delta"]["basis"] == version["delta_basis"]

    chips = {entry["pointer"]: entry["chip"] for entry in payload["provenance"]}
    assert chips["/delta/minimal"] == "derived"
    assert "/parent" not in chips, (
        "the reader chips `/parent` only when it carried one, so a chip beside an absent "
        "parent would be a provenance claim about nothing"
    )
    assert not any(pointer.startswith("/delta/witnesses/") for pointer in chips), (
        "no witness rows, so no per-witness chips"
    )


def test_the_ancestor_cap_is_parsed_out_of_the_check_that_declares_it(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """512, from ``CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512)``.

    Chipped ``db:constraint``. A migration that raised the cap would move this number
    without anyone editing Python, which is the only version of the field that survives
    a year.
    """
    payload = payloads["clause_ancestry"]
    data = payload["data"]
    assert data["truncation"]["cap"] == 512
    assert data["truncation"]["truncated"] is False
    assert data["truncation"]["ancestry_complete"] is True
    chips = {entry["pointer"]: entry["chip"] for entry in payload["provenance"]}
    assert chips["/truncation/cap"] == "db:constraint"
    assert chips["/truncation/ancestry_complete"] == "derived"


def test_the_ancestry_resolves_the_closure_into_events_edges_and_a_commit_chain(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """One incident, one blame edge, one commit in the chain — and each asserted as a fact.

    THE COMMIT CHAIN IS THE TELL. This test used to assert ``[link['gen'] for link in
    commit_chain] == [1, 2]`` — TWO clause generations — against a database that carries
    exactly one ``mainline.clause_version`` row. ``[1, 2]`` is not a thin reading of the
    deployed seed, it is a reading of a different database: the parallel world the old
    conftest built at ``5ddaa3a`` with ``clause-v1`` and ``clause-v2``. It is the same
    survivor as ``commit_v2`` two tests up, and it is settled by the same ruling —
    ``docs/decisions/demo-clause-version-singleton.md``. ``ancestor_count == 2``,
    ``len(events) == 2`` and ``len(blame_edges) == 2`` came from the same place.

    ``event_edges`` IS EMPTY AND THAT IS A CLAIM, not a gap. A ``recurrence_of`` edge is an
    edge BETWEEN two precursor events; the demo recalls one incident, so there is no second
    event for it to point at. An edge here would be an assertion that this incident recurred,
    which is a thing the seed does not know.
    """
    data = payloads["clause_ancestry"]["data"]
    assert data["closure"]["ancestor_count"] == 1
    assert data["closure"]["virulence"] == "blood_major"
    assert len(data["events"]) == 1
    assert data["events"][0]["external_ref"] == "DEMO-INC-0001"
    assert data["event_edges"] == [], (
        "one recalled incident, so there is no second event a `recurrence_of` edge could "
        "reach. An edge here would claim a recurrence the seed never observed"
    )
    assert len(data["blame_edges"]) == 1
    assert [link["gen"] for link in data["commit_chain"]] == [1], (
        "the demo has ONE clause version and it is the origin, so the chain is one link long"
    )
    assert data["corpus_root"] is not None, "the site has a checkpoint, so the root is a column"
    # NO PERSON APPEARS IN THIS CONTRACT. The events carry titles and severities.
    rendered = json.dumps(data)
    assert "w3.signer" not in rendered
    assert "w3.countersigner" not in rendered


def _root_from_inclusion(index: int, tree_size: int, leaf: bytes, path: list[bytes]) -> bytes:
    """RFC 6962 §2.1.1 verification, written independently of the generator under test."""
    node, last = index, tree_size - 1
    value = leaf
    for sibling in path:
        if last == 0:
            raise AssertionError("inclusion path is longer than the tree is deep")
        if node % 2 == 1 or node == last:
            value = hashlib.sha256(b"\x01" + sibling + value).digest()
            while node % 2 == 0 and node != 0:
                node //= 2
                last //= 2
        else:
            value = hashlib.sha256(b"\x01" + value + sibling).digest()
        node //= 2
        last //= 2
    assert last == 0, "inclusion path is shorter than the tree is deep"
    return value


def test_every_inclusion_proof_verifies_against_the_checkpoint_it_names(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """The proofs are ``derived``, and they are correct.

    This is the one place a ``derived`` chip earns more than a label: the console's
    verifier will recompute these in a Worker, and a proof that does not verify would
    surface as a red panel in front of a judge. It surfaces here instead.
    """
    data = payloads["ledger"]["data"]
    roots = {int(cp["tree_size"]): cp["root_hex"] for cp in data["checkpoints"]}
    leaves = {int(leaf["seq"]): leaf["leaf_hash_hex"] for leaf in data["leaves"]}
    assert data["inclusion_proofs"], "the fixture's window is dense from zero, so proofs exist"
    for proof in data["inclusion_proofs"]:
        recomputed = _root_from_inclusion(
            int(proof["seq"]),
            int(proof["tree_size"]),
            bytes.fromhex(leaves[int(proof["seq"])]),
            [bytes.fromhex(node) for node in proof["path_hex"]],
        )
        assert recomputed.hex() == roots[int(proof["tree_size"])], (
            f"inclusion proof for seq {proof['seq']} in tree {proof['tree_size']} does not "
            "reproduce the checkpoint root"
        )
    chips = {entry["pointer"]: entry["chip"] for entry in payloads["ledger"]["provenance"]}
    assert chips["/inclusion_proofs"] == "derived"
    assert chips["/checkpoints/0"] == "db:column"


def test_the_consistency_proof_between_the_two_checkpoints_is_present(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """RFC 6962 §2.1.2 — the check that catches delete-leaf-k-and-renumber.

    The link chain recomputes perfectly after that attack; the consistency proof does not.
    """
    data = payloads["ledger"]["data"]
    assert [(p["from_size"], p["to_size"]) for p in data["consistency_proofs"]] == [(2, 4)]
    assert data["consistency_proofs"][0]["path_hex"], "a 2→4 proof is not empty"
    assert [leaf["seq"] for leaf in data["leaves"]] == [0, 1, 2, 3]
    assert data["leaves"][0]["prev_link_hash_hex"] == "0" * 64, (
        "an explicit genesis, not a special case"
    )
    assert all(leaf["is_sandbox"] is False for leaf in data["leaves"])


def test_silence_flags_the_one_sentence_no_column_produced(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """The bound statement is staged, the note says why, and everything else is a column.

    ``s == n == 1``, AND THE EMPTY LEDGER IS THE CONSEQUENCE OF IT, not a thin seed. ``s`` is
    the boundary index and ``n`` the candidate count, under ``CHECK boundary_sane`` (``s <=
    n``, restated by the console at ``features/silence/model.ts::boundarySane``). ``s == n``
    is the state the console models as ``boundaryAtEnd`` — the boundary sits at the end of
    the score-sorted candidate multiset, so **nothing was excluded**, so
    ``mainline_meas.silence_ledger`` correctly holds no row. W1's ``boundary_proof`` is built
    for exactly this state and says so: ``'leaf_s_plus_1', 'null'::JSONB  -- s = n: nothing
    was excluded, so there is no s+1``. Asserting ``s == 2, n == 4`` here would now
    contradict the committed proof beside it.

    ``LedgerList.tsx`` renders the empty case as a first-class panel rather than a blank —
    *"The ledger carries no rows for this subject. That is the absence of a row, not proof
    that nothing was declined"* — so this is a screen the console offers, not one it breaks
    on. The old ``s == 2 / n == 4 / one below_tau entry`` was the parallel world again.
    """
    payload = payloads["silence"]
    data = payload["data"]
    assert payload["staged"] is True
    assert "bound.statement" in payload["staged_note"]
    assert "mainline_meas.silence_receipt" in payload["staged_note"]
    assert data["receipt"]["bound"]["statement"] == reads.PER_BOUND_SENTENCE
    assert data["receipt"]["bound"]["index_generation"] == "g1"
    assert data["receipt"]["s"] == 1
    assert data["receipt"]["n"] == 1
    assert data["receipt"]["s"] <= data["receipt"]["n"], "CHECK boundary_sane"
    assert data["entries"] == [], (
        "s == n, so the boundary is at the end of the candidate list and nothing was "
        "excluded. A ledger row here would name something silenced that the receipt says "
        "was not"
    )
    # The boundary proof is the disclosure that makes `s` checkable, and at `s == n` its
    # `leaf_s_plus_1` is null BECAUSE there is no s+1 — an explicit end, not a missing field.
    proof = data["receipt"]["boundary_proof"]
    assert proof["leaf_s"]["index"] == 0, "s == 1 and Merkle indices are 0-based"
    assert proof["leaf_s_plus_1"] is None, "nothing was excluded, so there is no next leaf"
    chips = {entry["pointer"]: entry["chip"] for entry in payload["provenance"]}
    assert chips["/receipt/bound/statement"] == "staged"
    assert chips["/receipt/bound/index_generation"] == "db:column"
    assert not any(pointer.startswith("/entries/") for pointer in chips), (
        "no ledger rows, so no per-entry chips: a chip beside nothing is worse than no chip"
    )


def test_the_recall_run_conserves_its_candidates(payloads: dict[str, dict[str, Any]]) -> None:
    """``candidates_conserved`` and ``bonded_fatalities_all_blocking``, added up by the reader.

    This API emits the seven counts and computes neither sum. The arithmetic below is the
    test doing what the console asks a human to do, which is the only version of the claim
    that is checkable.
    """
    counts = payloads["recall_run"]["data"]["counts"]
    assert counts["n_candidates"] == (
        counts["n_blocking"] + counts["n_advisory"] + counts["n_silenced"] + counts["n_deduped"]
    )
    assert counts["n_bonded_sev5_blocking"] == counts["n_bonded_sev5"]
    assert payloads["recall_run"]["data"]["arms_degraded"] is False
    assert "arms" not in payloads["recall_run"]["data"], "no per-arm table exists on this tree"


def test_propagation_is_staged_in_full_and_names_the_three_absent_tables(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """Not an empty list. An empty list would be the claim that there are no lessons."""
    payload = payloads["propagation"]
    assert payload["staged"] is True
    note = payload["staged_note"]
    for table in ("mainline.lesson", "mainline.propagation", "mainline.merge_conflict"):
        assert table in note
    assert {entry["chip"] for entry in payload["provenance"]} == {"staged"}
    assert payload["data"]["lesson"]["lesson_id"] == _LESSON_ID
    assert len(payload["data"]["propagations"]) == 3


def test_the_staged_propagation_payload_is_byte_stable(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """Two calls return the same bytes, so a reader can recompute every digest in it.

    That is the most a fabricated payload can honestly offer: not evidence, but
    reproducibility. The identifiers are UUID5 and the digests are SHA-256 of their own
    labels.
    """
    dsn, _ = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        first = reads.read_resource(conn, "propagation", {"lesson_id": _LESSON_ID}, {})
        second = reads.read_resource(conn, "propagation", {"lesson_id": _LESSON_ID}, {})
    finally:
        demo_db.reset_dsn_cache()
    assert envelope.dumps(first["data"]) == envelope.dumps(second["data"])


def test_the_audit_surface_reports_the_caps_it_ran_under(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """A payload that does not state its caps cannot be read as complete."""
    data = payloads["audit"]["data"]
    assert data["views"], "mainline_audit declares views on this tree"
    names = {view["view"] for view in data["views"]}
    assert "mainline_audit.v_open_gate_summary" in names
    for view in data["views"]:
        assert view["limits"]["row_cap"] == reads.AUDIT_ROW_CAP == 25
        assert view["limits"]["byte_cap"] == reads.AUDIT_BYTE_CAP
        assert view["limits"]["rows_returned"] == len(view["rows"])
        assert view["limits"]["bytes_returned"] <= reads.AUDIT_BYTE_CAP
        assert view["statement"].startswith("SELECT * FROM mainline_audit.")
        assert len(view["columns"]) >= 1
    # `calls` IS EMPTY, AND THE EMPTY LOG IS ITSELF THE CLAIM. `mainline_meas.agent_action`
    # is written by the Managed-MCP service account; the demo API connects as the demo's own
    # read role and never as that account — which is the very reason `unreachable` below
    # exists — so no call was carried into this database and none is reported. The console
    # renders that as a first-class row (`features/audit/parts/CallLog.tsx`): "No call was
    # carried. An empty log is a claim that nothing was recorded, not a claim that nothing
    # ran." The old `len(calls) == 1 / transport 'pgwire' / outcome 'ok'` described the row
    # the parallel-world conftest inserted for itself at `5ddaa3a`; the only INSERT into
    # that table anywhere in this tree today is in
    # `tests/integration/schema/test_agent_action_producer.py`, which is a test and not the
    # product. Emitting `[]` rather than omitting the member is what keeps this a claim.
    assert data["calls"] == [], (
        "nothing wrote mainline_meas.agent_action in this database, and an empty log is the "
        "honest report of that — not an omitted member and not an invented call"
    )
    # The negative assertion this API is NOT entitled to make.
    assert data["unreachable"][0]["outcome"] == "not_probed"


# ── Failure paths ───────────────────────────────────────────────────────────────────


def test_an_unknown_permit_is_404_naming_the_table(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    dsn, _ = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        with pytest.raises(reads.NotFound, match=r"mainline\.permit"):
            reads.read_resource(conn, "permit", {"permit_id": str(uuid.uuid4())}, {})
        with pytest.raises(reads.BadRequest, match="not a UUID"):
            reads.read_resource(conn, "permit", {"permit_id": "not-a-uuid"}, {})
        with pytest.raises(reads.BadRequest, match="hex"):
            reads.read_resource(
                conn, "clause_version", {"clause_uuid": str(uuid.uuid4()), "commit_id": "zz"}, {}
            )
    finally:
        demo_db.reset_dsn_cache()


def test_an_unknown_change_request_is_404_and_not_an_empty_envelope(
    demo_database: tuple[str, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``cr_id`` the seed does not carry is REFUSED, at the reader and at the route.

    THE OTHER HALF OF THE LEAD'S RULING. ``demo_world.sql`` §10 seeds the change request
    because the console declares the resource, and asserting a 404 *instead* would have
    certified the demo's second gated subject as furniture. But the 404 is a separate
    claim and it is worth its own test: the subject that exists and the subject that does
    not must be answered differently, and the failure this guards against is not a 500 —
    it is the reader that returns ``None`` for a missing row and lets the envelope go out
    with nulls in it, which reads to the console as "this change request exists and every
    field about it is unknown".

    Two levels, because they can fail independently: ``read_change_request``
    (``reads.py``) must RAISE, and the route (``app.py``) must turn that raise into a
    **404** carrying the resource name. A reader that raises behind a route that answers
    500 is still an outage as far as the console's error handling is concerned.
    """
    dsn, seed = demo_database
    absent = str(uuid.uuid4())
    assert absent != seed["cr_id"], "the point of this test is a cr_id the seed does not carry"

    monkeypatch.setenv("MAINLINE_DSN", dsn)
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        with pytest.raises(reads.NotFound, match=r"mainline\.change_request") as caught:
            reads.read_resource(conn, "change_request", {"cr_id": absent}, {})
        assert caught.value.resource == "change_request"
        assert caught.value.status == 404
        assert absent in str(caught.value), "the refusal names the id it could not find"

        # And the same absence over the real event shape, because the status code is the
        # only part of this the console ever sees.
        missing = app.handler(_event("GET", f"/v1/change-requests/{absent}"))
        assert missing["statusCode"] == 404, missing["body"]
        error = json.loads(missing["body"])["error"]
        assert error["kind"] == "notfound"
        assert error["resource"] == "change_request"

        # The seeded one is still a 200 through the same route, so the 404 above is about
        # THIS id and not about the resource being unreachable.
        present = app.handler(_event("GET", f"/v1/change-requests/{seed['cr_id']}"))
        assert present["statusCode"] == 200, present["body"]
        assert json.loads(present["body"])["data"]["cr_id"] == seed["cr_id"]
    finally:
        demo_db.reset_dsn_cache()


def test_an_undeclared_query_parameter_is_refused_rather_than_ignored(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """A silently-ignored filter is a filter the caller believes was applied.

    ``ledger`` declares ``site_code``, ``from_seq`` and ``to_seq``; ``permit`` declares
    none. Both refuse anything else with a 400 that names what IS declared.
    """
    dsn, seed = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        with pytest.raises(reads.BadRequest, match="does not declare query parameter"):
            reads.read_resource(
                conn, "permit", {"permit_id": seed["permit_id"]}, {"as_of": "deadbeef"}
            )
        with pytest.raises(reads.BadRequest, match="does not declare query parameter"):
            reads.read_resource(conn, "ledger", {}, {"site_code": seed["site_code"], "limit": "5"})
        # The declared ones are accepted, so the refusal above is about the NAME and not
        # about query parameters in general.
        payload = reads.read_resource(
            conn, "ledger", {}, {"site_code": seed["site_code"], "from_seq": "0", "to_seq": "1"}
        )
        assert [leaf["seq"] for leaf in payload["data"]["leaves"]] == [0, 1]
    finally:
        demo_db.reset_dsn_cache()


def test_a_dead_connection_is_replaced_rather_than_returned(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """A Lambda that froze across a cluster restart holds a socket that looks open.

    ``connection()`` proves it with ``SELECT 1`` on every acquisition. One extra round trip
    is the price of never handing a corpse to the next invocation of a warm container.
    """
    dsn, seed = demo_database
    demo_db.reset_dsn_cache()
    try:
        first = demo_db.connection(dsn=dsn)
        first.close()
        assert first.closed

        second = demo_db.connection(dsn=dsn)
        assert second is not first
        assert not second.closed
        # And it still works, which is the assertion that matters.
        payload = reads.read_resource(second, "permit", {"permit_id": seed["permit_id"]}, {})
        assert payload["data"]["permit_id"] == seed["permit_id"]
    finally:
        demo_db.reset_dsn_cache()


def test_a_dsn_change_replaces_the_cached_connection(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """So a test cannot inherit the previous test's database through the module cache."""
    dsn, _ = demo_database
    demo_db.reset_dsn_cache()
    try:
        first = demo_db.connection(dsn=dsn)
        again = demo_db.connection(dsn=dsn)
        assert again is first, "the same DSN must reuse the warm connection"
        other = demo_db.connection(dsn=f"{dsn}&application_name=w3-other")
        assert other is not first
        assert first.closed
    finally:
        demo_db.reset_dsn_cache()


def test_a_read_only_transaction_refuses_a_write(demo_database: tuple[str, dict[str, str]]) -> None:
    """25006, measured. Belt to the braces of the read-only SQL role."""
    import psycopg

    dsn, _ = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        with pytest.raises(psycopg.Error) as caught, demo_db.read_transaction(conn):
            conn.execute(
                "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, "
                "taxonomy_ver) VALUES (gen_random_uuid(), 'x', 'r', gen_random_uuid(), 1)"
            )
        assert caught.value.sqlstate == "25006"
    finally:
        demo_db.reset_dsn_cache()


# ── The whole handler, end to end ───────────────────────────────────────────────────


def _event(method: str, path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "&".join(f"{k}={v}" for k, v in (query or {}).items()),
        "queryStringParameters": query or None,
        "headers": {"accept": "application/json"},
        "requestContext": {"stage": "$default", "http": {"method": method, "path": path}},
        "isBase64Encoded": False,
    }


def test_the_handler_serves_a_read_over_the_lambda_event_shape(
    demo_database: tuple[str, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    registry: SchemaRegistry,
) -> None:
    """Payload format 2.0 in, ``{statusCode, headers, body}`` out, contract-valid in between."""
    dsn, seed = demo_database
    monkeypatch.setenv("MAINLINE_DSN", dsn)
    demo_db.reset_dsn_cache()
    try:
        response = app.handler(_event("GET", f"/v1/permits/{seed['permit_id']}"))
        assert response["statusCode"] == 200
        assert response["headers"]["content-type"] == "application/json; charset=utf-8"
        assert response["headers"]["cache-control"] == "public, max-age=10"
        assert "x-mainline-read-ms" in response["headers"]
        payload = json.loads(response["body"])
        assert registry.validate(envelope.SCHEMA_IDS["permit"], payload) == []

        missing = app.handler(_event("GET", f"/v1/permits/{uuid.uuid4()}"))
        assert missing["statusCode"] == 404
        assert json.loads(missing["body"])["error"]["kind"] == "notfound"
    finally:
        demo_db.reset_dsn_cache()


def test_health_is_200_with_a_real_schema_fingerprint(
    demo_database: tuple[str, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The numbers the honesty chrome shows, and the numbers the GitHub Actions cron checks.

    TWO APPLIERS KEEP TWO LEDGERS, AND THIS FIXTURE WRITES TO NEITHER.
    ``trappoint.schema_migration`` is written only by ``trappoint migrate up``
    (``trappoint_migrate/runner.py`` holds the single ``INSERT`` into it in this tree);
    ``trappoint.deploy_chain`` is written only by ``scripts/deploy/cloud_chain.py``.
    ``conftest._apply_chain`` bootstraps and then executes each migration file itself, so
    it can continue past a failure and report the whole census — and so it appears in
    neither ledger. ``migrations_applied`` is therefore **0 here, and that is correct**,
    not a bug being tolerated: it is the negative control for the whole endpoint, the
    assertion that proves the number is read out of a ledger rather than counted off the
    file tree.

    THE DEPLOYED CLUSTER REPORTS 0 IN THAT COLUMN TOO, and this docstring used to claim
    the opposite — that it "is migrated by W2 with the real command and reports 271". It
    is not and it does not. Cloud ``mainline_demo`` was built by ``cloud_chain.py``, which
    records its census in ``trappoint.deploy_chain`` instead. Read out of Cloud read-only
    on 2026-08-12 UTC: ``schema_migration`` holds **0 rows**, and the marker holds ``files
    271, applied 271, failed 0, applied_by "scripts/deploy/cloud_chain.py", applied_at
    2026-08-10T02:55:13Z``. Reproduced locally by re-running that same program against
    this node (``--database w_w5 --recreate`` → ``VERDICT APPLIED``, 271/271, 0 failed),
    where ``/v1/health`` answers ``migrations_applied 0`` with ``deploy_chain_applied
    271`` beside it. Both transcripts are in ``evidence/deploy/migrations-ledger.json``,
    and the shape is asserted in
    :func:`test_health_reads_the_deploy_chain_marker_when_the_database_has_one`.

    THIS DATABASE HAS NO MARKER AT ALL, which is the third case and the one the endpoint
    has to survive: ``trappoint.deploy_chain`` does not exist here, CockroachDB resolves
    every relation in a statement at plan time and fails the whole statement with ``42P01``
    when one is missing, and a 503 out of that would turn a healthy database into an
    outage. So the assertions below are the honest quartet — a real fingerprint from
    ``trappoint migrate bootstrap``, a bookkeeping count that says what the bookkeeping
    table holds, marker fields reported as ``None`` rather than invented, and **200**.
    """
    dsn, _ = demo_database
    monkeypatch.setenv("MAINLINE_DSN", dsn)
    demo_db.reset_dsn_cache()
    try:
        status, body = health.health()
        assert status == 200, body
        assert body["ok"] is True
        assert body["cluster_version"].startswith("CockroachDB")
        assert len(body["schema_fingerprint"]) == 64
        assert int(body["schema_fingerprint"], 16) >= 0
        assert body["database"].startswith("w3_demo_api_")
        assert body["seconds"] < 5.0
        assert body["migrations_applied"] == 0, (
            "this fixture applies the chain file by file rather than through "
            "`trappoint migrate up`, so trappoint.schema_migration is empty and the endpoint "
            "reports what the bookkeeping table holds. A number here would mean this endpoint "
            "had counted files instead of reading the ledger."
        )
        assert body["deploy_chain_applied"] is None, (
            "there is no trappoint.deploy_chain in this database, so the only honest report "
            "is no reading at all. A number here would mean the endpoint had found a marker "
            "somewhere other than this database, or invented one."
        )
        assert body["deploy_chain_files"] is None
        assert body["applied_by"] == "unrecorded", (
            "neither ledger holds a row, so no applier left a record and the endpoint must "
            "say so rather than guess. The fingerprint above is still real — bootstrap wrote "
            "it — which is exactly why `ok` keys on the fingerprint and not on these counts."
        )
        assert set(body) == {
            "ok",
            "cluster_version",
            "database",
            "schema_fingerprint",
            "migrations_applied",
            "deploy_chain_applied",
            "deploy_chain_files",
            "applied_by",
            "server_date",
            "seconds",
        }, (
            "the 200 body's key set is a contract: every 503 branch in health.py carries the "
            "same keys with None readings, so a caller cannot be written against a key that "
            f"disappears. Got {sorted(body)}."
        )

        response = app.handler(_event("GET", "/v1/health"))
        assert response["statusCode"] == 200
        assert response["headers"]["cache-control"] == "no-store"
        routed = json.loads(response["body"])
        assert routed["schema_fingerprint"] == body["schema_fingerprint"]
        assert routed["migrations_applied"] == 0
        assert routed["deploy_chain_applied"] is None
        assert routed["applied_by"] == "unrecorded"
    finally:
        demo_db.reset_dsn_cache()


def test_health_reads_the_deploy_chain_marker_when_the_database_has_one(
    admin_dsn: str,
) -> None:
    """The other applier's ledger, read out of a database the other applier's DDL built.

    The fixture above covers a database with no marker. This covers the case the DEPLOYED
    cluster is in, and it is the assertion that would fail if the marker subqueries were
    dropped, misspelled, or keyed on something other than ``current_database()``.

    Nothing here is a stand-in for the real thing where the real thing was affordable:
    ``trappoint.schema_attestation`` and ``trappoint.schema_migration`` are created by the
    real :func:`trappoint_migrate.bootstrap.bootstrap`, and ``trappoint.deploy_chain`` is
    created by ``cloud_chain.MARKER_DDL`` — the very string the deploy program executes,
    loaded out of the deploy program. Only the marker's numbers are the test's own, and
    they are taken from the migration tree so that the assertion moves when the tree does.

    Applying all 271 files here would be the fully real alternative, and it is what
    ``evidence/deploy/migrations-ledger.json`` does once rather than on every test run:
    two ``cloud_chain.py --database w_w5 --recreate`` runs against this node recorded
    ``total_seconds`` 57.5 and 57.7 for the chain, inside a wall clock of 136.7 s and
    68.4 s — the chain itself is steady, the wall clock also carries ``trappoint migrate
    bootstrap`` and connection setup and so moves with machine load. Either figure is
    minutes per test session, which is the cost this test declines to pay on every run.
    """
    from trappoint_migrate.bootstrap import bootstrap
    from trappoint_migrate.runner import DEFAULT_SCHEMA_PREFIXES, actor

    chain = _load_cloud_chain()
    files = len(list(MIGRATIONS_DIR.glob("*.sql")))
    assert files > 0, f"no migrations under {MIGRATIONS_DIR}"

    # The literal cloud_chain.py writes into applied_by. Asserted against its source, so
    # that the day the deploy program renames itself this test says so instead of quietly
    # comparing against a string nothing writes any more.
    applied_by = "scripts/deploy/cloud_chain.py"
    assert applied_by in CLOUD_CHAIN_PY.read_text(encoding="utf-8")

    database = "w5_deploy_chain_marker"
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")
        admin.execute(f"CREATE DATABASE {database}")
    dsn = _dsn_for(admin_dsn, database)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            bootstrap(conn, applied_by=actor(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)
            conn.execute(chain.MARKER_DDL)
            conn.execute(
                "UPSERT INTO trappoint.deploy_chain (marker_id, tree_fingerprint, "
                "live_fingerprint, files, applied, failed, retried, total_seconds, "
                "applied_at, applied_by) VALUES (%s, %s, %s, %s, %s, 0, 0, %s, now(), %s)",
                (database, b"\x11" * 32, b"\x22" * 32, files, files, 136.7, applied_by),
            )

        demo_db.reset_dsn_cache()
        status, body = health.health(dsn=dsn)
        assert status == 200, body
        assert body["ok"] is True
        assert body["database"] == database
        assert body["deploy_chain_applied"] == files
        assert body["deploy_chain_files"] == files
        assert body["applied_by"] == applied_by, (
            "the endpoint must name the applier with the ledger's own word for it, not with "
            "a string of its own choosing."
        )
        assert body["migrations_applied"] == 0, (
            "the two ledgers are independent and this database was never touched by "
            "`trappoint migrate up`. A number here would mean the endpoint had let the "
            "marker's count leak into the column that names the other applier's table."
        )
        assert len(body["schema_fingerprint"]) == 64
    finally:
        demo_db.close()
        demo_db.reset_dsn_cache()
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")


def test_the_health_statement_is_one_statement_and_names_both_ledgers() -> None:
    """One round trip is a cost decision, and the fallback is the same text minus a clause.

    ``/v1/health`` is polled by a GitHub Actions cron every few minutes because the
    CloudWatch Synthetics alternative was priced at $10.37/month — thirty times the rest
    of the stack. That is why the statement is one statement: a second round trip is a
    second wide-area latency on every poll, and Cloud is in ``aws-ap-southeast-1``.

    The last assertion is the one that matters most. The fallback is COMPOSED from the
    same text rather than written out again, so the four columns the two statements share
    cannot drift apart and quietly start reporting different things depending on whether
    the database happens to carry a marker.
    """
    full = health.HEALTH_STATEMENT
    short = health.HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN

    assert ";" not in full, f"one statement, no semicolons: {full}"
    assert full.count("SELECT version()") == 1
    assert "trappoint.schema_attestation" in full
    assert "trappoint.schema_migration" in full
    assert "trappoint.deploy_chain" in full

    assert "trappoint.deploy_chain" not in short, (
        "the fallback exists to be run when that relation is missing, so naming it there "
        "would make the 42P01 unrecoverable and turn a healthy database into a 503."
    )
    assert full.startswith(short.rstrip()), (
        "the fallback must be a PREFIX of the full statement, not a second copy of it: "
        "that is what makes the shared columns provably identical."
    )


def test_the_server_date_is_the_databases_clock_not_this_processs(
    demo_database: tuple[str, dict[str, str]],
) -> None:
    """The console computes skew from it, so reading a Lambda's clock would measure AWS's NTP.

    The assertion is an ORDERING, which is the only thing that distinguishes the two
    sources without assuming the clocks agree: a database ``now()`` taken before the read
    must not be after the ``server_date`` the read stamped, and one taken after must not be
    before it. A payload stamped from ``datetime.now()`` in this process would satisfy that
    only by coincidence, and would stop satisfying it the moment the two machines differed.
    """
    import datetime as dt

    dsn, seed = demo_database
    demo_db.reset_dsn_cache()
    conn = demo_db.connection(dsn=dsn)
    try:
        with demo_db.read_transaction(conn):
            before = demo_db.server_now(conn)
        payload = reads.read_resource(conn, "permit", {"permit_id": seed["permit_id"]}, {})
        with demo_db.read_transaction(conn):
            after = demo_db.server_now(conn)
    finally:
        demo_db.reset_dsn_cache()

    stamped = dt.datetime.strptime(payload["server_date"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=dt.UTC
    )
    assert before <= stamped <= after, (before, stamped, after)
    assert payload["observed_at"] == payload["server_date"]
