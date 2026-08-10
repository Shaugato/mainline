# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
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
import json
import uuid
from typing import Any

import pytest
from mainline_demo_api import app, envelope, health, reads
from mainline_demo_api import db as demo_db

from conftest import SchemaRegistry

pytestmark = pytest.mark.requires_cluster

#: A lesson id for the staged propagation surface. Any UUID: no row is looked up, which
#: is exactly the property the staged flag exists to declare.
_LESSON_ID = "11111111-2222-4333-8444-555555555555"


def _requests(seed: dict[str, str]) -> dict[str, tuple[dict[str, str], dict[str, str]]]:
    return {
        "permit": ({"permit_id": seed["permit_id"]}, {}),
        "change_request": ({"cr_id": seed["cr_id"]}, {}),
        "blocking_checks": ({"permit_id": seed["permit_id"]}, {}),
        "disposition": ({"check_id": seed["check_id"]}, {}),
        "exposure_receipt": ({"receipt_id": seed["receipt_id"]}, {}),
        "clause_version": (
            {"clause_uuid": seed["clause_uuid"], "commit_id": seed["commit_v2"]},
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

    The fixture never writes ``mainline.permit.open_blocking``. It inserts one
    ``blocking_check`` — ``check_materialised`` raises the counter to 1 — and then signs
    one disposition, at which point ``disposition_close`` lowers it to 0. The value this
    API reports is whatever those two triggers left behind, which is what makes
    ``db:column`` an honest chip for it.

    The second assertion is the interesting one, and it is the whole product in miniature:
    the projected counter and the count re-derived from the base tables agree. The gate's
    third beat is what happens when they do not.
    """
    import psycopg

    data = payloads["permit"]["data"]
    checks = payloads["blocking_checks"]["data"]["checks"]
    assert data["state"] == "draft"
    assert len(checks) == 1, "one obligation was materialised"
    assert data["counters"]["open_blocking"] == sum(1 for check in checks if check["open"]) == 0

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

    The fixture inserts the check with ``severity 0`` and ``virulence 'routine'``. The
    closure bands it ``blood_major`` at severity 4, and the trigger overwrites both on the
    way in. That is why ``db:column`` is the right chip: nobody who wrote the check chose
    these.
    """
    data = payloads["blocking_checks"]["data"]
    assert len(data["checks"]) == 1
    check = data["checks"][0]
    assert check["severity"] == 4
    assert check["virulence"] == "blood_major"
    assert check["open"] is False, "the fixture signs a disposition, so the check is closed"
    assert check["disposition_id"] is not None
    assert check["precursor"]["external_ref"] == "INC-W3-1"

    chips = {entry["pointer"]: entry["chip"] for entry in payloads["blocking_checks"]["provenance"]}
    assert chips["/checks/0/open"] == "derived"
    assert chips["/checks/0/disposition_id"] == "derived"
    assert chips["/checks/0"] == "db:column"


def test_the_disposition_carries_the_lattice_and_the_projected_requirements(
    payloads: dict[str, dict[str, Any]],
) -> None:
    """The lattice is every row for the virulence; a missing pair is a NON-EXISTENT option."""
    data = payloads["disposition"]["data"]
    assert data["virulence"] == "blood_major"
    assert {row["virulence"] for row in data["lattice"]} == {"blood_major"}
    assert len(data["lattice"]) >= 1
    assert {option["defeater_code"] for option in data["defeater_options"]} == {
        "MECHANISM_PRESENT_AND_VERIFIED",
        "SCOPE_EXCLUDES_HAZARD",
    }
    assert data["reading_floor"] is None, "S19's components are on no table in this tree"

    signed = data["signed"]
    assert signed is not None
    assert signed["kind"] == "applied"
    assert signed["signature"]["user_verified"] is True
    assert len(signed["rationale"]) >= 120, "CONSTRAINT substantive"
    # req_second_signer is PROJECTED onto the row from clearance_legal by a BEFORE
    # trigger; the fixture supplies false for every flag and the lattice decides.
    lattice_applied = next(row for row in data["lattice"] if row["kind"] == "applied")
    assert signed["requirements"]["req_second_signer"] == lattice_applied["req_second_signer"]
    assert signed["requirements"]["min_signer_rank"] == lattice_applied["min_signer_rank"]


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
    """``[]`` and ``null`` are different sentences and this API makes the stronger one."""
    data = payloads["clause_version"]["data"]
    assert data["version"]["control_delta"] == "strengthen"
    assert data["version"]["anchor_set"] == ["LOTO", "ZERO_ENERGY", "WITNESS"]
    assert data["parent"] is not None, "gen 1 is resolvable from parent_version"
    assert data["parent"]["gen"] == 1
    assert data["delta"]["witnesses"] is not None
    assert [witness["rule_id"] for witness in data["delta"]["witnesses"]] == ["R6_VERIFICATION"]
    assert data["delta"]["minimal"] is True
    chips = {entry["pointer"]: entry["chip"] for entry in payloads["clause_version"]["provenance"]}
    assert chips["/delta/minimal"] == "derived"


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
    data = payloads["clause_ancestry"]["data"]
    assert data["closure"]["ancestor_count"] == 2
    assert data["closure"]["virulence"] == "blood_major"
    assert len(data["events"]) == 2
    assert {edge["relation"] for edge in data["event_edges"]} == {"recurrence_of"}
    assert len(data["blame_edges"]) == 2
    assert [link["gen"] for link in data["commit_chain"]] == [1, 2]
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
    """The bound statement is staged, the note says why, and everything else is a column."""
    payload = payloads["silence"]
    data = payload["data"]
    assert payload["staged"] is True
    assert "bound.statement" in payload["staged_note"]
    assert "mainline_meas.silence_receipt" in payload["staged_note"]
    assert data["receipt"]["bound"]["statement"] == reads.PER_BOUND_SENTENCE
    assert data["receipt"]["bound"]["index_generation"] == "g1"
    assert data["receipt"]["s"] == 2
    assert data["receipt"]["n"] == 4
    assert len(data["entries"]) == 1
    assert data["entries"][0]["reason"] == "below_tau"
    chips = {entry["pointer"]: entry["chip"] for entry in payload["provenance"]}
    assert chips["/receipt/bound/statement"] == "staged"
    assert chips["/receipt/bound/index_generation"] == "db:column"
    assert chips["/entries/0"] == "db:column"


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
    # `calls` is a column: mainline_meas.agent_action has a producer on this tree.
    assert len(data["calls"]) == 1
    assert data["calls"][0]["transport"] == "pgwire"
    assert data["calls"][0]["outcome"] == "ok"
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
    """The number the honesty chrome shows, and the number the GitHub Actions cron checks.

    ``migrations_applied`` is **0 against this fixture, and that is correct**, not a bug
    being tolerated. ``conftest._apply_chain`` executes each migration file directly so it
    can continue past a failure and report the whole census; ``trappoint migrate up`` is
    what writes ``trappoint.schema_migration``, and it is not what runs here. The deployed
    cluster is migrated by W2 with the real command and reports 271.

    The FINGERPRINT is real either way: ``trappoint migrate bootstrap`` writes the genesis
    attestation, and that is the row this endpoint reads. So the assertion below is the
    honest pair — a real fingerprint, and a bookkeeping count that says what the
    bookkeeping table actually holds rather than what the file tree contains.
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

        response = app.handler(_event("GET", "/v1/health"))
        assert response["statusCode"] == 200
        assert response["headers"]["cache-control"] == "no-store"
        assert json.loads(response["body"])["schema_fingerprint"] == body["schema_fingerprint"]
    finally:
        demo_db.reset_dsn_cache()


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
