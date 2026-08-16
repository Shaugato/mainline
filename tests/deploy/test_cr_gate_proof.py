# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The change-request gate refusal, asserted over the RECORDED transcript.

``scripts/proof/cr_gate_refusal.py`` drives the deployed kernel over the public internet
and writes two files: ``evidence/deploy/cr-gate-live.json`` (the published evidence) and
``qa/cr-gate-live.json`` (the raw transcript, every request and every byte that came back).
**This file never opens a socket.** It asserts over what was recorded, so the assertion
survives a laptop on a plane, a CI runner with no egress, and the day the demo URL is torn
down — which is the point of recording bytes rather than describing them.

WHAT MAKES THIS MORE THAN A RUBBER STAMP
-----------------------------------------
An evidence file that a test merely *parses* proves nothing: anyone could write
``"verdict": "PROVEN"`` into it. Three properties are checked here that no hand edit can
satisfy without also editing the bytes underneath:

1. **Every recorded assertion is RECOMPUTED.** Each row carries the pointer it read, the
   value it expected and the value it observed. :func:`test_no_assertion_holds_without_the
   _two_values_it_was_computed_from` recomputes ``holds`` from those two values and
   requires agreement. Flipping a ``holds`` flag fails. Deleting the values fails.
2. **The pinned exhibits are re-read from the VERBATIM BODY**, not from the summary the
   script wrote beside it. ``23514``/``cr_gate_closed_when_merged`` and
   ``P0001``/``mainline.fn_cr_merge_gate`` are located inside
   ``evidence["cr_gate_runs"][i]["body"]`` — the payload the origin returned — so the
   summary and the body have to agree or the test fails.
3. **The fingerprints are re-hashed here.** ``persisted: false`` is only accepted when a
   SHA-256 taken in this process over the recorded ``before`` and ``after`` readings
   matches. A ``persisted: false`` with a moved row fails.

THE THREE FINDINGS, AND WHY NONE OF THEM IS SILENTLY GREEN
------------------------------------------------------------
The transcript records one of three statuses, and this file asserts hard in every branch —
there is no branch where a missing measurement quietly passes:

* ``PROVEN`` — the full pin set below is required.
* ``NOT PROVEN`` — the origin answered and the answer did not support the claim. The
  recorded failure list must be non-empty and must name the beat, and the assertions must
  agree with it. **This branch is a genuine finding, not an excuse**: it is what a wave
  publishes when the kernel says something other than what it was written against.
* ``UNANSWERABLE`` — ``POST /v1/demo/cr-gate-run`` was not declared by the deployment, so
  there was no question to ask. This branch requires the deployment's own 404 route
  enumeration to be recorded and to genuinely not contain the endpoint. *A route that has
  not been deployed is not a gate that failed to refuse*, and the two are kept apart here
  for the same reason ``gate_refusal.py`` gives them different exit codes.

Which branch is taken is read out of the file, and
:func:`test_the_recorded_status_follows_from_the_recorded_assertions` checks that the
status the file claims is the status its own contents support. So ``UNANSWERABLE`` cannot
be written over a run that reached the endpoint, and ``PROVEN`` cannot be written over a
run that did not.

WHAT ELSE IS PINNED
-------------------
* The four committing POSTs were **not sent**. The transcript must contain no request to
  ``…/checks:materialise``, ``…/merge``, ``…/suspend`` or ``POST /v1/checks/…/disposition``
  against the live origin — a safety ratchet, because *a probe whose safety depends on a
  guard holding is a probe that writes on the day it does not*, and the row it would write
  closes the demo's one obligation for every judge after it.
* ``POST /v1/demo/gate-run`` — the permit half of the mirror — is unchanged: ``PROVEN``,
  ``persisted: false``, its four beats in order, ``23514 gate_closed_when_issued`` and
  ``P0001 mainline.fn_permit_merge_gate``.
* The pre-existing route surface did not move — and the recorded "this route answered what
  it always did" flag is RECOMPUTED here from the two values it is a conclusion about,
  because falsification caught a route answering ``500`` behind a flag that said otherwise.
* The obligation open on the change request is the mirror of the permit's: severity 4,
  ``blood_major``, origin ``blame_ancestry``, open, undisposed.
* The suite, when a ``--junitxml`` was recorded, is either at or above 998/997/0/0 or it is
  RED WITH EVERY RED NODE ID NAMED — and this worker's own file is not among them. Counts
  come off the XML root element, never off a terminal tail. A wave in flight may leave the
  tree red for a while; what is refused is a red number with nothing behind it.

This file runs with ``--crdb=none``: nothing here needs a database, and nothing here needs
a network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
EVIDENCE_PATH: Final = REPO_ROOT / "evidence" / "deploy" / "cr-gate-live.json"
TRANSCRIPT_PATH: Final = REPO_ROOT / "qa" / "cr-gate-live.json"

# ── THE EXHIBITS, RESTATED RATHER THAN IMPORTED ──────────────────────────────────────
#
# Importing them from `scripts/proof/cr_gate_refusal.py` would make this test agree with
# the producer BY CONSTRUCTION: the two would move together and the comparison would
# assert nothing. The same reason `scripts/qa/regression_guard.py` restates the kernel
# exhibits instead of importing `gate_refusal`. If one of these is wrong, this file is the
# thing that has to be edited, in a diff a reviewer reads.
CR_MERGE_SQLSTATE: Final = "23514"
CR_MERGE_CONSTRAINT: Final = "cr_gate_closed_when_merged"
CR_MERGE_CONSTRAINT_SOURCE: Final = "reported"
CR_DRIFT_SQLSTATE: Final = "P0001"
CR_DRIFT_EXHIBIT: Final = "mainline.fn_cr_merge_gate"
CR_DRIFT_CONSTRAINT_SOURCE: Final = "parsed"

PERMIT_MERGE: Final = ("23514", "gate_closed_when_issued")
PERMIT_DRIFT: Final = ("P0001", "mainline.fn_permit_merge_gate")
PERMIT_BEATS: Final = ["read", "merge", "projection_drift_attack", "admit"]

CR_ID: Final = "dec0de00-000c-4000-8000-000000000001"
#: The obligation open on that change request — severity 4, `blood_major`,
#: origin `blame_ancestry`. The mirror of the permit's `dec0de00-0007-…`.
CR_CHECK_ID: Final = "dec0de00-000d-4000-8000-000000000001"
CR_OPEN_BLOCKING: Final = 1
CR_STATE: Final = "checks_materialised"
CR_GATE_RUN_PATH: Final = "/v1/demo/cr-gate-run"

#: `scripts/qa/regression_guard.py::SUITE_BASELINE`. A count may rise; it may not fall.
SUITE_BASELINE: Final = {"collected": 998, "passed": 997, "failed": 0, "errors": 0}

STATUSES: Final = ("PROVEN", "NOT PROVEN", "UNANSWERABLE")


# ═════════════════════════════════════════════════════════════════════════════════════
# loading
# ═════════════════════════════════════════════════════════════════════════════════════


def _load(path: Path) -> dict[str, Any]:
    """Load a recorded file, or stop the module.

    This runs inside a fixture, so a missing file surfaces as pytest ERROR rather than
    FAILURE — and that is the right colour. **'There was no transcript' and 'the
    transcript says the wrong thing' are different findings**, exactly the distinction
    this whole file is about, and pytest already has two words for them. A reader who
    sees errors here should go and produce the transcript; a reader who sees failures
    should go and read what the origin said.
    """
    assert path.is_file(), (
        f"{path.relative_to(REPO_ROOT)} is missing. It is produced by "
        f"`python scripts/proof/cr_gate_refusal.py`, which drives the public Function URL "
        f"and records every byte it received. Without it there is no transcript to assert "
        f"over, and this file will not invent one."
    )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict), f"{path.name} is not a JSON object"
    return loaded


@pytest.fixture(scope="module")
def evidence() -> dict[str, Any]:
    return _load(EVIDENCE_PATH)


@pytest.fixture(scope="module")
def transcript() -> dict[str, Any]:
    return _load(TRANSCRIPT_PATH)


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _bodies(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """The verbatim `POST /v1/demo/cr-gate-run` payloads, in the order they were pressed."""
    return [
        record["body"]["data"]
        for record in evidence.get("cr_gate_runs", [])
        if isinstance(record.get("body"), dict) and isinstance(record["body"].get("data"), dict)
    ]


def _beat(body: dict[str, Any], name: str) -> dict[str, Any]:
    for beat in body.get("beats", []):
        if isinstance(beat, dict) and beat.get("name") == name:
            return beat
    raise AssertionError(f"the recorded payload carries no beat named {name!r}")


def _is_forbidden(method: str, path: str) -> bool:
    """A committing POST against the seeded demo subject. GETs of the same paths are fine."""
    if method != "POST":
        return False
    return "/checks:materialise" in path or path.endswith(("/merge", "/suspend", "/disposition"))


def _pressed(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """The recorded presses, or ``[]`` after asserting that the absence is a real one.

    **THERE IS NO SKIP IN THIS FILE, DELIBERATELY.** A skip is indistinguishable from a
    deleted test — ``qa/skip-ratchet.json`` exists because this repository decided that —
    and a pin that quietly evaporated the day the route was not deployed would be worth
    nothing. So when there are no presses to assert over, every pin below instead asserts
    the *other* claim the file is making: that the endpoint genuinely was not there.

    Four things have to hold for that claim, and each is a byte the origin sent:

    * the recorded status is ``UNANSWERABLE`` — not ``NOT PROVEN``, which would be a
      statement about the gate rather than about the deploy;
    * ``POST /v1/demo/cr-gate-run`` was actually pressed and actually answered ``404``;
    * the deployment's own 404 route enumeration is recorded, and the endpoint genuinely
      is not in it;
    * the exit code was ``2`` — 'there was nothing to ask', the code ``gate_refusal.py``
      reserves for 'there was no cluster'.

    Fabricating any of those to dodge a pin fails here, and asserting a PROVEN run with no
    recorded press fails too.
    """
    bodies = _bodies(evidence)
    if bodies:
        assert evidence["status"] != "UNANSWERABLE", (
            "presses are recorded, so 'there was nothing to ask' is not what happened"
        )
        return bodies
    assert evidence["status"] == "UNANSWERABLE", (
        f"status {evidence['status']!r} claims the endpoint answered, but no "
        f"POST {CR_GATE_RUN_PATH} payload is recorded"
    )
    probe = evidence["cr_gate_run_probe"]
    assert probe["method"] == "POST"
    assert probe["path"] == CR_GATE_RUN_PATH
    assert probe["status"] == 404, (
        f"the endpoint answered {probe['status']}, which is an answer, so UNANSWERABLE is "
        f"not what the recorded bytes say"
    )
    declared = evidence["why_unanswerable"]["declared_paths"]
    assert isinstance(declared, list) and declared
    assert CR_GATE_RUN_PATH not in declared
    assert evidence["exit_code"] == 2
    return []


# ═════════════════════════════════════════════════════════════════════════════════════
# 1 · the transcript is what it says it is
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_evidence_names_its_origin_its_producer_and_its_status(
    evidence: dict[str, Any],
) -> None:
    assert evidence["schema"] == "mainline.proof.cr-gate-live/1"
    assert evidence["produced_by"] == "scripts/proof/cr_gate_refusal.py"
    assert evidence["origin"].startswith("https://"), "the origin driven must be recorded"
    assert evidence["status"] in STATUSES, f"unknown status {evidence['status']!r}"
    assert evidence["verdict"] == evidence["status"]
    # The absence of AWS in this run is a claim the file makes, so it is a claim this test
    # requires the file to make explicitly rather than one a reader has to infer.
    assert "no_apply_was_run" in evidence


def test_the_transcript_names_the_deployment_it_drove(evidence: dict[str, Any]) -> None:
    """A transcript that does not say which build answered is a transcript about nothing.

    ``/v1/health`` carries the four facts that identify the kernel: the database it is
    pointed at, the CockroachDB version, how many migration files the deploy chain applied
    and the schema fingerprint. All four are required to be present and non-null, so a
    later reader can tell whether the kernel that refused is the kernel in front of them.
    """
    deployment = evidence["deployment"]
    assert deployment["ok"] is True
    for key in ("database", "cluster_version", "deploy_chain_applied", "schema_fingerprint"):
        assert deployment[key] is not None, f"/v1/health did not report {key}"
    assert evidence["health"]["status"] == 200


def test_no_assertion_holds_without_the_two_values_it_was_computed_from(
    evidence: dict[str, Any],
) -> None:
    """Recompute every recorded `holds`. This is the anti-fabrication ratchet.

    A row claims `holds: true`. This recomputes it from the row's own `expected` and
    `observed`. Flipping the flag fails; deleting the values fails; changing one value
    without changing the verdict fails.
    """
    rows = evidence["assertions"]["rows"]
    assert rows, "an evidence file with no assertions asserts nothing"
    disagreements: list[str] = []
    for row in rows:
        if "expected_substring" in row:
            recomputed = bool(row["pointer_resolved"]) and (
                isinstance(row["observed"], str) and row["expected_substring"] in row["observed"]
            )
        else:
            recomputed = bool(row["pointer_resolved"]) and row["observed"] == row["expected"]
        if recomputed != row["holds"]:
            disagreements.append(
                f"{row['id']}: recorded holds={row['holds']} but expected="
                f"{row.get('expected', row.get('expected_substring'))!r} vs "
                f"observed={row['observed']!r} recomputes to {recomputed}"
            )
    assert not disagreements, "recorded assertions disagree with their own values:\n" + "\n".join(
        disagreements
    )
    counted = sum(1 for row in rows if row["holds"])
    assert counted == evidence["assertions"]["held"]
    assert len(rows) == evidence["assertions"]["total"]


def test_the_recorded_status_follows_from_the_recorded_assertions(
    evidence: dict[str, Any],
) -> None:
    """The status a file claims must be the status its own contents support."""
    status = evidence["status"]
    failures = evidence["failures"]
    reached_the_endpoint = bool(evidence.get("cr_gate_runs"))

    if status == "UNANSWERABLE":
        assert not reached_the_endpoint, (
            "UNANSWERABLE was recorded over a run that DID press the endpoint. "
            "'there was nothing to ask' cannot be written over an answer."
        )
        why = evidence["why_unanswerable"]
        declared = why["declared_paths"]
        assert isinstance(declared, list) and declared, (
            "the finding rests on the deployment's own route enumeration, so that "
            "enumeration has to be in the file"
        )
        assert CR_GATE_RUN_PATH not in declared, (
            f"{CR_GATE_RUN_PATH} IS in the deployment's declared route list, so "
            f"'not declared' is not what the recorded bytes say"
        )
        assert evidence["cr_gate_run_probe"]["status"] == 404
        assert evidence["exit_code"] == 2
        return

    assert reached_the_endpoint, (
        f"status {status!r} claims the endpoint answered, but no "
        f"POST {CR_GATE_RUN_PATH} payload is recorded"
    )
    if status == "PROVEN":
        assert not failures, f"PROVEN was recorded beside {len(failures)} failures"
        assert evidence["assertions"]["held"] == evidence["assertions"]["total"]
        assert evidence["exit_code"] == 0
    else:
        assert failures, "NOT PROVEN was recorded with no failure named"
        assert evidence["exit_code"] == 1


# ═════════════════════════════════════════════════════════════════════════════════════
# 2 · the safety ratchet — what was deliberately NOT sent
# ═════════════════════════════════════════════════════════════════════════════════════


def test_no_committing_post_was_ever_sent_to_the_live_origin(
    transcript: dict[str, Any],
) -> None:
    """The four irreversible POSTs must not appear anywhere in the transcript.

    They are refused ``423 demo_subject_write_protected`` today. That is not sufficient
    reason to send them: the guard is the only thing between the probe and a row that
    closes the demo's one obligation for every judge who comes after. Declaration is
    checked from the deployment's own 404 route enumeration instead.
    """
    sent = [
        f"{request['method']} {request['path']}"
        for phase in transcript["phases"]
        for request in phase["requests"]
        if _is_forbidden(request["method"], request["path"])
    ]
    assert not sent, "a committing POST was sent to the live origin: " + ", ".join(
        sorted(set(sent))
    )


def test_the_four_undriven_routes_are_still_declared_by_the_deployment(
    evidence: dict[str, Any],
) -> None:
    """Not driven is not unchecked. Their path templates come back off the 404 body."""
    undriven = evidence["undriven_routes"]
    assert undriven["count"] == 4
    declared = evidence["route_table"]["body"]["error"]["declared"]
    missing = [template for template in undriven["templates"] if template not in declared]
    assert not missing, f"route templates no longer declared by the deployment: {missing}"


# ═════════════════════════════════════════════════════════════════════════════════════
# 3 · the pinned refusals — read from the verbatim body, not the summary
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_merge_beat_is_refused_23514_cr_gate_closed_when_merged(
    evidence: dict[str, Any],
) -> None:
    for index, body in enumerate(_pressed(evidence), start=1):
        beat = _beat(body, "merge")
        assert beat["sqlstate"] == CR_MERGE_SQLSTATE, f"press {index}"
        assert beat["constraint"] == CR_MERGE_CONSTRAINT, f"press {index}"
        assert beat["constraint_source"] == CR_MERGE_CONSTRAINT_SOURCE, (
            f"press {index}: the CHECK name must be REPORTED by the driver. A 'parsed' "
            f"source would mean it was recovered from a message, which is a weaker "
            f"diagnosis and a different claim."
        )
        assert beat["outcome"] == "refused", f"press {index}"
        assert beat["matched_expectation"] is True, f"press {index}"


def test_the_drift_beat_is_refused_p0001_by_fn_cr_merge_gate(evidence: dict[str, Any]) -> None:
    for index, body in enumerate(_pressed(evidence), start=1):
        beat = _beat(body, "projection_drift_attack")
        assert beat["sqlstate"] == CR_DRIFT_SQLSTATE, f"press {index}"
        assert beat["constraint"] == CR_DRIFT_EXHIBIT, f"press {index}"
        assert beat["constraint_source"] == CR_DRIFT_CONSTRAINT_SOURCE, (
            f"press {index}: P0001 carries no constraint_name (spec/errors.md 3.1), so its "
            f"exhibit is PARSED out of the message. Recording it as 'reported' would claim "
            f"a diagnosis the driver did not give."
        )
        assert CR_DRIFT_EXHIBIT in (beat["message"] or ""), f"press {index}"
        assert beat["outcome"] == "refused", f"press {index}"


def test_the_two_exhibits_are_different_objects(evidence: dict[str, Any]) -> None:
    """The CHECK and the trigger function are not the same thing, and are not conflated.

    ``cr_merge_gate`` (migration 0131) is the TRIGGER; ``cr_gate_closed_when_merged`` is
    the CHECK on ``mainline.change_request``; ``mainline.fn_cr_merge_gate`` is the function
    the trigger calls. A transcript that named the trigger where the driver reported the
    constraint would be making a claim the kernel does not make.

    The two constants differ by inspection — mypy proves it, and an assertion saying so is
    dead weight the type checker rejects. What is NOT true by inspection is that the
    catalogue and the refusal agree, and that is what is checked below.
    """
    # The CR read reaches `pg_constraint` through a route that exists whether or not the
    # demo endpoint does, so this half is checkable in every branch: the catalogue must
    # carry the CHECK under the name the refusal will report.
    assert CR_MERGE_CONSTRAINT in evidence["cr_read_constraints"]
    for body in _pressed(evidence):
        assert (
            _beat(body, "merge")["constraint"]
            != _beat(body, "projection_drift_attack")["constraint"]
        )


# ═════════════════════════════════════════════════════════════════════════════════════
# 4 · nothing persisted, and the proof of that is re-hashed here
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_before_and_after_fingerprints_are_identical(evidence: dict[str, Any]) -> None:
    for index, body in enumerate(_pressed(evidence), start=1):
        check = body["persistence_check"]
        before, after = check["before"], check["after"]
        assert _digest(before) == _digest(after), (
            f"press {index}: the fingerprint taken before the transaction and the one "
            f"taken after it are not the same bytes"
        )
        assert check["identical"] is True, f"press {index}"
        assert check["self_persisted"] is False, f"press {index}"
        assert body["persisted"] is False, f"press {index}"


def test_the_change_request_row_came_back_exactly_where_it_was(
    evidence: dict[str, Any],
) -> None:
    """The forged zero this run wrote is gone, and the row is byte-identical.

    Beat 3 forces ``open_blocking`` to ``0`` inside the transaction — the database admits
    that write, which is the attack — so a ``1`` here afterwards is this run's own evidence
    about its own write, not a general statement about the database.
    """
    for index, body in enumerate(_pressed(evidence), start=1):
        check = body["persistence_check"]
        before = check["before"]["change_request_row"]
        after = check["after"]["change_request_row"]
        assert _digest(before) == _digest(after), f"press {index}: the CR row moved"
        assert after["open_blocking"] == CR_OPEN_BLOCKING, f"press {index}"
        assert after["state"] == CR_STATE, f"press {index}"
        assert after["merged_commit"] is None, f"press {index}: the change request MERGED"
        assert check["before"]["subject_row_counts"] == check["after"]["subject_row_counts"], (
            f"press {index}: the cr_event / merge_record counts for this cr_id moved"
        )


def test_the_row_is_byte_identical_after_every_press(evidence: dict[str, Any]) -> None:
    """Fifty judges at once is the safety claim; N presses in a row is the evidence."""
    bodies = _pressed(evidence)
    if not bodies:
        return
    assert len(bodies) >= 3, (
        f"the repeatability claim needs at least three presses; {len(bodies)} recorded"
    )
    hashes = [_digest(body["persistence_check"]["after"]["change_request_row"]) for body in bodies]
    assert len(set(hashes)) == 1, f"the CR row differs between presses: {hashes}"
    assert evidence["repeatability"]["identical_across_runs"] is True
    assert evidence["repeatability"]["cr_row_sha256"] == hashes, (
        "the recorded repeatability hashes disagree with the ones recomputed from the bodies"
    )


def test_the_beats_shared_one_transaction(evidence: dict[str, Any]) -> None:
    for index, body in enumerate(_pressed(evidence), start=1):
        transaction = body["transaction"]
        assert transaction["isolation"] == "SERIALIZABLE", f"press {index}"
        assert transaction["disposition"] == "rolled_back", f"press {index}"
        opened = transaction["opened_logical_timestamp"]
        closed = transaction["closed_logical_timestamp"]
        assert opened is not None and closed is not None, f"press {index}"
        assert opened == closed, (
            f"press {index}: cluster_logical_timestamp() moved between the first beat and "
            f"the last, so the beats did not share one transaction"
        )
        assert transaction["single_transaction"] is True, f"press {index}"


def test_the_admission_that_cannot_be_played_is_declared_not_faked(
    evidence: dict[str, Any],
) -> None:
    """RULING R3. No fifth beat dressed as passing, and no silence either."""
    for index, body in enumerate(_pressed(evidence), start=1):
        assert body["admission_beat"] is None, f"press {index}"
        assert body["admission_absent_reason"], f"press {index}: the absence must be in words"
        assert body["admission_proved_by"] == "POST /v1/demo/gate-run", f"press {index}"
        names = [beat.get("name") for beat in body["beats"]]
        assert "admit" not in names, (
            f"press {index}: an admission beat appeared in a run that cannot sign a "
            f"disposition. See R3 — this is the exact fabrication the ruling forbids."
        )


# ═════════════════════════════════════════════════════════════════════════════════════
# 5 · regression — the permit mirror, the routes, the suite
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_permit_gate_run_is_unchanged(evidence: dict[str, Any]) -> None:
    """The first proof still answers exactly as it did. Re-read from the verbatim body."""
    body = evidence["gate_run"]["body"]["data"]
    assert body["verdict"] == "PROVEN"
    assert body["persisted"] is False
    assert [beat["name"] for beat in body["beats"]] == PERMIT_BEATS
    merge = _beat(body, "merge")
    assert (merge["sqlstate"], merge["constraint"]) == PERMIT_MERGE
    drift = _beat(body, "projection_drift_attack")
    assert (drift["sqlstate"], drift["constraint"]) == PERMIT_DRIFT
    assert body["persistence_check"]["identical"] is True
    assert _digest(body["persistence_check"]["before"]) == _digest(
        body["persistence_check"]["after"]
    )


def test_every_pre_existing_route_is_accounted_for(evidence: dict[str, Any]) -> None:
    routes = evidence["preexisting_routes"]
    assert len(routes) == 18, "app.py::_routes() had eighteen Route rows before this wave"
    # RECOMPUTED, never read. `status_matches_expectation` is a boolean the producer wrote;
    # trusting it would let a route answer 500 and the flag say otherwise. Falsification
    # caught exactly that, so the comparison is redone here from the two values it is a
    # conclusion about.
    off = [
        f"{route['method']} {route['path']} -> {route['shape'].get('status')} "
        f"(expected {route['expected_status']})"
        for route in routes
        if route["driven"] and route["shape"].get("status") != route["expected_status"]
    ]
    assert not off, "pre-existing routes answered something new: " + "; ".join(off)
    disagreements = [
        route["path"]
        for route in routes
        if route["driven"]
        and route["status_matches_expectation"]
        != (route["shape"].get("status") == route["expected_status"])
    ]
    assert not disagreements, (
        f"the recorded status_matches_expectation flag disagrees with the recorded "
        f"status for: {disagreements}"
    )
    assert sum(1 for route in routes if route["driven"]) == 14
    assert sum(1 for route in routes if not route["driven"]) == 4


def test_no_pre_existing_route_changed_shape(evidence: dict[str, Any]) -> None:
    drift = evidence["route_drift"]
    if drift["compared_against"] is None:
        # The first recorded drive IS the baseline; there is nothing earlier to diff it
        # against, and the file has to say so rather than reporting an empty diff as if a
        # comparison had happened.
        assert any("baseline" in caveat for caveat in evidence["caveats"]), (
            "no route baseline was compared against, and no caveat says so"
        )
        return
    assert not drift["drifted"], f"pre-existing routes changed shape: {drift['drifted']}"


def test_the_change_request_is_still_the_seeded_one_with_its_obligation_open(
    evidence: dict[str, Any],
) -> None:
    data = evidence["cr_read"]["body"]["data"]
    assert data["cr_id"] == CR_ID
    assert data["state"] == CR_STATE
    assert data["counters"]["open_blocking"] == CR_OPEN_BLOCKING
    assert data["merged_commit"] is None
    assert CR_MERGE_CONSTRAINT in [row["constraint"] for row in data["constraints"]], (
        "the CHECK the refusal names is not among the ones the CR read reports from "
        "pg_constraint, so the two readings of the catalogue disagree"
    )


def test_the_obligation_on_the_change_request_mirrors_the_one_on_the_permit(
    evidence: dict[str, Any],
) -> None:
    """The two use cases are one story only if the two obligations are the same shape.

    Severity 4, ``blood_major``, origin ``blame_ancestry``, still open, no signed
    disposition — the same four facts the permit's gate refused on. If they differ, the
    second use case is a different story wearing the first one's clothes, and the film's
    claim that this is the mirror image would not be true.

    When the list route is not deployed there is no obligation read to check, and the
    branch instead requires the absence to be a real 404 with the route genuinely
    undeclared — the same discipline as :func:`_pressed`, for the same reason.
    """
    obligation = evidence.get("cr_obligation")
    if obligation is None:
        record = evidence["cr_blocking_checks"]
        assert record["status"] == 404, (
            f"the CR blocking-checks route answered {record['status']} but no obligation "
            f"was recorded from it"
        )
        declared = evidence["route_table"]["body"]["error"]["declared"]
        assert not any(
            path.endswith("/blocking-checks") and "change-request" in path for path in declared
        )
        return
    assert obligation["check_id"] == CR_CHECK_ID
    assert obligation["severity"] == 4
    assert obligation["virulence"] == "blood_major"
    assert obligation["origin"] == "blame_ancestry"
    assert obligation["open"] is True
    assert obligation["disposition_id"] is None
    data = evidence["cr_blocking_checks"]["body"]["data"]
    assert data["subject_kind"] == "change_request"
    assert data["subject_id"] == CR_ID


def test_the_suite_is_at_or_above_the_baseline_or_names_every_red_node(
    evidence: dict[str, Any],
) -> None:
    """Green is asserted. Red is asserted too — as a NAMED finding, never as an omission.

    A wave in flight can leave the tree red for a while, and a recorded red measurement is
    a finding about the wave. What this refuses is a red number with nothing behind it,
    and a red measurement in which this file is one of the red nodes: reporting somebody
    else's failure while quietly having one of your own is not a report.

    ``scripts/qa/regression_guard.py`` owns the repository-wide baseline. This is the same
    figures, read off the same XML root element, recorded beside the proof they were taken
    with — so that "the proof was green and the tree was red" cannot be told as one story.
    """
    suite = evidence.get("suite")
    if suite is None:
        assert any("suite" in caveat for caveat in evidence["caveats"]), (
            "no suite numbers were recorded and no caveat says so"
        )
        return
    assert suite["baseline"] == SUITE_BASELINE
    recorded = {label: suite[label] for label in ("before", "after") if label in suite}
    assert recorded, "a suite section with neither a before nor an after run"
    for label, totals in recorded.items():
        assert totals["collected"] >= SUITE_BASELINE["collected"], (
            f"{label}: collected {totals['collected']}, baseline "
            f"{SUITE_BASELINE['collected']}. A count that falls is a regression and is "
            f"never re-recorded downward to make a run green."
        )
        # RECOMPUTED from the four numbers, never read off the flag beside them.
        green = (
            totals["failed"] == 0
            and totals["errors"] == 0
            and totals["passed"] >= SUITE_BASELINE["passed"]
        )
        assert green == totals["at_or_above_baseline"], (
            f"{label}: the recorded at_or_above_baseline flag disagrees with the recorded "
            f"counts {totals['failed']} failed / {totals['errors']} errors / "
            f"{totals['passed']} passed"
        )
        if green:
            assert not totals["failing_node_ids"], f"{label}: green, with red node ids listed"
            continue
        assert len(totals["failing_node_ids"]) == totals["failed"] + totals["errors"], (
            f"{label}: {totals['failed'] + totals['errors']} red, but "
            f"{len(totals['failing_node_ids'])} node ids named. A red count with nothing "
            f"behind it is a number, not a finding."
        )
        mine = [node for node in totals["failing_node_ids"] if "test_cr_gate_proof" in node]
        assert not mine, f"{label}: this worker's own test file is red: {mine}"


# ═════════════════════════════════════════════════════════════════════════════════════
# 6 · the transcript and the evidence are the same bytes
# ═════════════════════════════════════════════════════════════════════════════════════


def test_the_evidence_bodies_appear_in_the_transcript_with_the_same_digest(
    evidence: dict[str, Any], transcript: dict[str, Any]
) -> None:
    """The published evidence is a selection from the transcript, never a retelling."""
    latest = transcript["phases"][-1]
    by_name = {request["name"]: request for request in latest["requests"]}
    pairs = [("cr_read", evidence["cr_read"]), ("gate_run", evidence["gate_run"])]
    pairs += [
        (f"cr_gate_run_{index}", record)
        for index, record in enumerate(evidence.get("cr_gate_runs", []), start=1)
    ]
    for name, record in pairs:
        assert name in by_name, f"{name} is in the evidence but not in the transcript"
        assert by_name[name]["body_sha256"] == record["body_sha256"], (
            f"{name}: the evidence and the transcript carry different bytes"
        )
        assert by_name[name]["status"] == record["status"]
        assert by_name[name]["bytes"] == record["bytes"]


def test_the_transcript_says_in_one_sentence_which_of_the_three_findings_it_is(
    evidence: dict[str, Any],
) -> None:
    """The finding is stated, not inferred, and it is stated where a reader will hit it.

    This is the test whose failure message a human reads first. It carries no new
    comparison — it re-states, in the terms the transcript itself uses, which of the three
    findings was recorded, so that a green suite on an ``UNANSWERABLE`` transcript can
    never be mistaken for a green suite on a proven one.
    """
    status = evidence["status"]
    assert status in STATUSES
    if status == "PROVEN":
        assert evidence["assertions"]["held"] == evidence["assertions"]["total"]
        assert len(_bodies(evidence)) >= 3
        return
    if status == "NOT PROVEN":
        assert evidence["failures"], (
            "NOT PROVEN with nothing named is not a finding. The failing beat has to be "
            "in the file — that is the whole discipline: the first answer is the answer, "
            "and a red run is published rather than re-run until it is green."
        )
        return
    # UNANSWERABLE. `_pressed` is what asserts the absence is real; calling it here means
    # this branch cannot be reached by a file that merely claims the route was missing.
    assert _pressed(evidence) == []
    assert evidence["why_unanswerable"]["finding"].startswith(f"POST {CR_GATE_RUN_PATH}")
