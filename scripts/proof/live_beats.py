#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The four beats, proven on the LIVE URL, in one sitting, by a caller with no credential.

WHAT THIS IS FOR
----------------
The film shows a refusal landing inside an operator screen. A judge who believes the screen is
believing a pixel. This program is the receipt behind the pixel: it drives the deployed demo over
HTTPS, records every request it made, and asserts the four beats against the SQLSTATEs the
database produced — ``00000``, ``23514``, ``P0001``, ``00000`` — with the constraint names and the
``constraint_source`` provenance attached to each.

It takes a base URL and nothing else. **No DSN, no AWS profile, no credential, no knowledge of the
seed.** The identifiers are discovered from ``GET /v1/demo/subjects``; nothing about the world is
hard-coded here, so a transcript from a differently-seeded deployment is a transcript of *that*
deployment rather than a mismatch against this one. Everything asserted is asserted about bytes
that came back over the wire.

WHAT IT DELIBERATELY DOES NOT REBUILD
-------------------------------------
``scripts/deploy/demo_acceptance.py --phase2`` already drives the gate twice and compares two
runs; ``scripts/deploy/judge_walk.py`` already walks every request the console artefact declares.
Neither produces the thing the film needs, which is **one composed transcript of one sitting** —
the world read, the gate driven, the trap recorded, all in a single ordered list with a byte count
and two different clocks against every line. So this program *imports* their work rather than
re-deriving it:

* ``demo_acceptance.EXPECTED_BEATS`` and ``check_beats`` — the beat table IS the acceptance
  criterion, and a second copy of it in this file would be a second place for it to be wrong.
* ``demo_acceptance.fetch`` — one round trip, non-2xx as a result rather than an exception.
* ``demo_acceptance.permit_snapshot_from_read`` / ``permit_snapshot_from_subject`` and
  ``PERMIT_INVARIANT_FIELDS`` — the four fields that must not move across a gate run.
* ``judge_walk.mask`` / ``say`` — every string that reaches stdout and the whole evidence document
  are masked, and stdout survives a console that cannot encode what the server said.

TWO CLOCKS, AND WHY THEY ARE NEVER ADDED TOGETHER
-------------------------------------------------
Every recorded request carries **``wall_ms``** — this machine's monotonic clock around the round
trip, which includes DNS, the TLS handshake, the trip to ap-southeast-1 and back, any Lambda cold
start, and JSON parsing — and **``payload_elapsed_ms``**, which is what the *server* said about
itself, taken from a named JSON pointer that is recorded beside the number.

They are different measurements of different things and conflating them is how a demo ends up
narrating its own reveal delay as database latency. A GET envelope on this API carries **no**
server-measured duration at all, so ``payload_elapsed_ms`` is ``null`` there and the pointer is
``null`` too — an absent measurement is written down as absent, never as a zero and never as the
wall clock wearing a server's name.

The gate run additionally carries a per-beat ``elapsed_ms``. Those four numbers sum to less than
the run's own ``elapsed_ms``, which is itself less than ``wall_ms``; the transcript records all
three levels and the deltas between them.

THE THIRD BEAT IS THE ONE TO READ TWICE, AND ITS DIAGNOSIS IS RECORDED WEAK
---------------------------------------------------------------------------
``mainline.permit.open_blocking`` is forced to zero out of band — exactly what a disarmed
projector or a careless ``UPDATE`` leaves behind — so beat 2's CHECK is now satisfied and would
admit the merge. It is refused anyway, because ``mainline.fn_permit_merge_gate`` re-derives the
open count from ``blocking_check LEFT JOIN disposition`` instead of trusting the column.

And on that, its best refusal, the system reports that it **cannot compute a nearest admissible
answer**: ``constraint_source: "parsed"`` (CockroachDB populates no PL/pgSQL context stack, so the
name was recovered from the kernel's own message), ``diagnosis: "none"``, ``naa: null``,
``naa_reason: "not_computable"``, and a single MUS atom of kind ``capability_gap``. That is
recorded here verbatim and asserted. A run whose exhibits were *inferred* must never look like a
run whose exhibits were *reported*, and a system that says out loud where its explanation engine
stops is making a Product-Readiness claim, not an apology.

THE 423 IS A DOCUMENTED TRAP, NOT A REFUSAL — RULING R4
--------------------------------------------------------
``POST /v1/permits/{permit_id}/merge`` against the seeded subject answers **423 Locked** with
``use_instead: "POST /v1/demo/gate-run"`` (``docs/deploy/gate-run-contract.md`` §7). It is a write
protection on a shared public row, and it is **not the gate refusing**. It is recorded here ONCE,
under ``documented_traps``, labelled, with its ``use_instead`` — precisely so that no operator
screen ever wires an ISSUE button to it. A 423 rendered as a refusal banner is a fabricated
exhibit in front of a judge.

That is the only non-``GET`` this program sends besides ``POST /v1/demo/gate-run``. There is no
``DELETE``, no ``PUT``, no second POST of any kind, and the transcript's own request list is
asserted against that rule before the verdict is printed.

ONE REQUEST, FOUR BEATS
------------------------
The operator screens reveal the beats one at a time. That is defensible only if the four beats
came from **one** response, because otherwise progressive disclosure is four requests wearing a
costume. So the transcript carries a line naming the single AWS request id
(``x-amzn-requestid``), the single response timestamp, and the beat count, and it asserts that
exactly one gate-run request was sent.

EXIT CODES
----------
``0`` PROVEN · ``1`` a beat or an exhibit differs (NOT PROVEN) · ``2`` usage · ``3`` the target
could not be reached at all. A different SQLSTATE is a regression even when a verdict still says
PROVEN, so the SQLSTATEs are asserted here rather than read off the server's own verdict.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.deploy.demo_acceptance import (  # noqa: E402 - sys.path is set immediately above
    EMULATOR_HEADER,
    EXIT_PROVEN,
    EXIT_UNREACHABLE,
    EXIT_USAGE,
    EXIT_WRONG,
    PERMIT_INVARIANT_FIELDS,
    Fetched,
    check_beats,
    describe_error_body,
    fetch,
    permit_snapshot_from_read,
    permit_snapshot_from_subject,
)
from scripts.deploy.judge_walk import mask, say  # noqa: E402 - same

#: Where the transcript lands. Owned by this worker; nothing else writes it.
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "demo" / "live-beats.json"

#: The one mutating call this program is allowed to make, plus the one trap it records.
GATE_RUN_PATH: Final = "/v1/demo/gate-run"
TRAP_PATH_TEMPLATE: Final = "/v1/permits/{permit_id}/merge"

#: A clearance digest is a SHA-256 rendered lowercase. Its VALUE is not asserted — the disposition
#: is minted fresh inside every run, so two runs legitimately produce two digests — but its SHAPE
#: is, because "admitted" with no server-computed exhibit is an assertion rather than evidence.
SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")

#: Beat 3's honest incompleteness, asserted field by field. See the module docstring and
#: `docs/deploy/gate-run-contract.md` §4 ("Beat 3's diagnosis is honestly incomplete").
BEAT3_EXPECTED_DIAGNOSIS: Final[dict[str, Any]] = {
    "constraint_source": "parsed",
    "diagnosis": "none",
    "naa": None,
    "naa_reason": "not_computable",
    "mus_kind": "capability_gap",
    "mus_capability": "mainline.fn_permit_merge_gate",
}

#: What the write protection must say. `docs/deploy/gate-run-contract.md` §7.
TRAP_EXPECTED: Final[dict[str, str]] = {
    "error": "demo_subject_write_protected",
    "use_instead": "POST /v1/demo/gate-run",
}

#: Stated in the artefact so a reader does not have to infer the aperture from what is absent.
#: Every line is a limit of THIS transcript, not a known defect of the product.
NOT_PROVEN_BY_THIS_TRANSCRIPT: Final[tuple[str, ...]] = (
    (
        "Nothing about the console or the operator screens. No browser ran; this is an HTTP "
        "client. That a screen renders these bytes is a separate claim with separate evidence."
    ),
    (
        "Not that the seeded history is true of the world. It is SYNTHETIC and the payload says "
        "so in its own evidence_summary; what is proven is that the gate re-derives from it."
    ),
    (
        "Not that the store is CockroachDB Cloud rather than any PostgreSQL-wire server. What is "
        "recorded is the cluster_version string the deployment reported about itself."
    ),
    (
        "Not that beat 4's signature was verified by an authenticator. The WebAuthn assertion is "
        "synthesised and the envelope declares staged; only the projected columns are real."
    ),
    (
        "Not a latency figure for a judge's network. wall_ms is this machine's path to this "
        "region at this hour, with an unknown warm/cold state; a measurement, not a service level."
    ),
    (
        "Not that the endpoint behaves this way for every subject. One seeded subject was driven, "
        "once, and the transcript names it."
    ),
    (
        "Not that nothing persisted forever. The permit is re-read after the run and after the "
        "trap and compared field by field, which proves the rollback happened, not that it "
        "always will."
    ),
    (
        "Not that the 423 trap is unreachable from a user interface. It proves the API refuses "
        "it; keeping it off an ISSUE button is the screen's job and this transcript is why."
    ),
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_date_to_iso(value: str | None) -> str | None:
    """RFC 7231 ``Date`` -> ISO 8601 Z. ``None`` when the header was absent or unparseable."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def payload_elapsed(document: Any) -> tuple[float | None, str | None]:
    """The server's own duration for this response, and the JSON pointer it came from.

    ``(None, None)`` is a real answer and the common one: a read envelope on this API carries
    ``observed_at`` and ``server_date`` but no duration at all. Returning the wall clock here, or
    a zero, would put a number the server never produced into a field named after the server.
    """
    if not isinstance(document, dict):
        return None, None
    data = document.get("data")
    if isinstance(data, dict) and isinstance(data.get("elapsed_ms"), (int, float)):
        return round(float(data["elapsed_ms"]), 3), "/data/elapsed_ms"
    if isinstance(document.get("elapsed_ms"), (int, float)):
        return round(float(document["elapsed_ms"]), 3), "/elapsed_ms"
    if isinstance(document.get("seconds"), (int, float)):
        return round(float(document["seconds"]) * 1000.0, 3), "/seconds (seconds x 1000)"
    return None, None


class Transcript:
    """Every request this program made, in order, with both clocks and the byte count."""

    def __init__(self, base: str, timeout: float) -> None:
        self.base = base
        self.timeout = timeout
        self.entries: list[dict[str, Any]] = []
        self.transport_failures: list[str] = []
        self.emulator_seen = False

    def send(
        self,
        method: str,
        path: str,
        *,
        label: str,
        why: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[Fetched, Any, dict[str, Any]]:
        url = urljoin(self.base, path.lstrip("/"))
        response = fetch(url, method=method, payload=payload, timeout=self.timeout)
        try:
            document: Any = response.json()
        except Exception:  # noqa: BLE001 - a non-JSON body is a result, recorded as such
            document = None

        server_ms, pointer = payload_elapsed(document)
        headers = response.headers
        if EMULATOR_HEADER in headers:
            self.emulator_seen = True

        entry: dict[str, Any] = {
            "seq": len(self.entries) + 1,
            "label": label,
            "why": why,
            "method": method,
            "path": path,
            "url": url,
            "status": response.status,
            "response_bytes": len(response.body),
            "wall_ms": response.elapsed_ms,
            "payload_elapsed_ms": server_ms,
            "payload_elapsed_pointer": pointer,
            "wall_minus_payload_ms": (
                round(response.elapsed_ms - server_ms, 3) if server_ms is not None else None
            ),
            "content_type": headers.get("content-type"),
            "request_id": headers.get("x-amzn-requestid"),
            "response_date_header": headers.get("date"),
            "response_date_iso": http_date_to_iso(headers.get("date")),
            "payload_observed_at": (
                document.get("observed_at") if isinstance(document, dict) else None
            ),
            "payload_server_date": (
                document.get("server_date") if isinstance(document, dict) else None
            ),
            "emulator_header": headers.get(EMULATOR_HEADER),
        }
        if response.error:
            entry["transport_error"] = response.error
            self.transport_failures.append(f"{method} {path}: {response.error}")
        self.entries.append(entry)
        return response, document, entry


def envelope_data(document: Any) -> dict[str, Any] | None:
    """The ``data`` member of a MAINLINE envelope, or ``None`` when this is not one."""
    if isinstance(document, dict) and isinstance(document.get("data"), dict):
        return document["data"]
    return None


def expect_200(response: Fetched, entry: dict[str, Any], failures: list[str]) -> bool:
    if response.status == 200:
        return True
    failures.append(
        f"{entry['method']} {entry['path']} answered {response.status}, not 200"
        f"{describe_error_body(response)}"
    )
    return False


def read_the_world(  # noqa: PLR0912, PLR0915 - one branch per read, and each read is a claim
    transcript: Transcript, failures: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discover the identifiers, then read every surface the operator screens read.

    Returns ``(ids, world)``. ``ids`` is empty when discovery failed, which is the one condition
    that stops the rest of the walk: a program that guessed a permit id would be asserting a fact
    about a row it never found.
    """
    world: dict[str, Any] = {}
    ids: dict[str, Any] = {}

    response, document, entry = transcript.send(
        "GET",
        "/v1/demo/subjects",
        label="discovery",
        why="which subjects does this database carry — the only source of identifiers used below",
    )
    if not expect_200(response, entry, failures):
        return ids, world
    data = envelope_data(document)
    if data is None:
        failures.append("GET /v1/demo/subjects did not answer an envelope with a data member")
        return ids, world

    for key in ("permit_id", "cr_id", "check_id", "receipt_id", "run_id", "clause_uuid"):
        value = data.get(key)
        if not value:
            failures.append(f"GET /v1/demo/subjects carries no {key}; the world is not seeded")
        ids[key] = value
    absent = data.get("absent")
    world["discovery"] = {
        "source": "GET /v1/demo/subjects",
        "note": (
            "mainline_demo_api.subjects answers this entirely out of SELECTs; not one identifier "
            "in that module is a Python constant. Nothing below is hard-coded in this script."
        ),
        "identifiers": dict(ids),
        "absent": absent,
        "permit": (data.get("subjects") or {}).get("permit"),
        "change_request": (data.get("subjects") or {}).get("change_request"),
        "event": (data.get("subjects") or {}).get("event"),
    }
    if absent:
        failures.append(f"GET /v1/demo/subjects reports absent subjects: {absent}")
    if not ids.get("permit_id"):
        return {}, world

    response, document, entry = transcript.send(
        "GET", "/v1/health", label="health", why="is the deployment up, and on which chain"
    )
    if expect_200(response, entry, failures) and isinstance(document, dict):
        world["health"] = {
            "ok": document.get("ok"),
            "database": document.get("database"),
            "deploy_chain_applied": document.get("deploy_chain_applied"),
            "deploy_chain_files": document.get("deploy_chain_files"),
            "migrations_applied": document.get("migrations_applied"),
            "cluster_version": document.get("cluster_version"),
            "schema_fingerprint": document.get("schema_fingerprint"),
            "server_date": document.get("server_date"),
            "seconds": document.get("seconds"),
        }
        if document.get("ok") is not True:
            failures.append(f"GET /v1/health answered ok={document.get('ok')!r}, not true")
        applied = document.get("deploy_chain_applied")
        files = document.get("deploy_chain_files")
        if applied != files:
            failures.append(
                f"GET /v1/health reports deploy_chain {applied} of {files}: the deployed chain "
                "is not the chain on disk"
            )

    permit_id = ids["permit_id"]
    response, document, entry = transcript.send(
        "GET",
        f"/v1/permits/{permit_id}",
        label="permit_before",
        why="the permit the supervisor's screen is about, read before the gate is driven",
    )
    before = None
    if expect_200(response, entry, failures) and envelope_data(document) is not None:
        before = permit_snapshot_from_read(document)
        world["permit_before"] = before
        counters = (envelope_data(document) or {}).get("counters") or {}
        if not isinstance(counters.get("open_blocking"), int) or counters["open_blocking"] < 1:
            failures.append(
                "the permit carries no open blocking obligation, so beats 2 and 3 would be about "
                "nothing: 'the gate did not refuse' and 'there was nothing to ask' are different "
                "findings and only one of them is about the product"
            )
    world["permit_before_snapshot"] = before

    response, document, entry = transcript.send(
        "GET",
        f"/v1/permits/{permit_id}/blocking-checks",
        label="blocking_checks",
        why="the obligation that is still open — what the gate will refuse about",
    )
    if expect_200(response, entry, failures):
        data = envelope_data(document) or {}
        checks = data.get("checks") or []
        open_checks = [c for c in checks if c.get("open")]
        world["blocking_checks"] = {
            "count": len(checks),
            "open_count": len(open_checks),
            "gate_epoch": data.get("gate_epoch"),
            "checks": [
                {
                    "check_id": c.get("check_id"),
                    "open": c.get("open"),
                    "origin": c.get("origin"),
                    "severity": c.get("severity"),
                    "virulence": c.get("virulence"),
                    "clause_label": c.get("clause_label"),
                    "clause_uuid": c.get("clause_uuid"),
                    "commit_id": c.get("commit_id"),
                    "precursor_external_ref": (c.get("precursor") or {}).get("external_ref"),
                    "precursor_occurred_at": (c.get("precursor") or {}).get("occurred_at"),
                    "precursor_severity_gate": (c.get("precursor") or {}).get("severity_gate"),
                    "evidence_summary": c.get("evidence_summary"),
                }
                for c in checks
            ],
            "severity_provenance": (
                "severity and virulence are supplied as 0 / 'routine' by the seed and are "
                "overwritten by mainline.fn_check_project from mainline.clause_blame_current "
                "(invariant MI25, docs/deploy/cloud-database.md:808). A 4 read back here is how "
                "you know the projection ran — nobody typed it."
            ),
        }
        if not open_checks:
            failures.append("no open blocking check came back; there is nothing for a gate to do")
        if ids.get("check_id") and ids["check_id"] not in [c.get("check_id") for c in checks]:
            failures.append(
                "the obligation named by GET /v1/demo/subjects is not among the permit's blocking "
                "checks: two endpoints disagree about the same world"
            )

    response, document, entry = transcript.send(
        "GET",
        f"/v1/permits/{permit_id}/silence",
        label="silence",
        why="the Proof of Exhausted Recall behind the obligation — what was searched, and to what",
    )
    if expect_200(response, entry, failures):
        data = envelope_data(document) or {}
        receipt = data.get("receipt") or {}
        world["silence"] = {
            "silence_receipt_id": receipt.get("silence_receipt_id"),
            "run_id": receipt.get("run_id"),
            "policy_version": receipt.get("policy_version"),
            "n": receipt.get("n"),
            "s": receipt.get("s"),
            "theta": receipt.get("theta"),
            "issued_at": receipt.get("issued_at"),
            "corpus_root": receipt.get("corpus_root"),
            "candidate_root": receipt.get("candidate_root"),
            "bound_statement": (receipt.get("bound") or {}).get("statement"),
            "entries": len(data.get("entries") or []),
        }

    cr_id = ids.get("cr_id")
    if cr_id:
        response, document, entry = transcript.send(
            "GET",
            f"/v1/change-requests/{cr_id}",
            label="change_request",
            why="the second subject — the proposal to edit the clause the permit relies on",
        )
        if expect_200(response, entry, failures):
            data = envelope_data(document) or {}
            world["change_request"] = {
                "cr_id": data.get("cr_id"),
                "external_ref": data.get("external_ref"),
                "state": data.get("state"),
                "gate_epoch": data.get("gate_epoch"),
                "head_seq": data.get("head_seq"),
                "merged_commit": data.get("merged_commit"),
                "target_ref": data.get("target_ref"),
                "counters": data.get("counters"),
            }

    response, document, entry = transcript.send(
        "GET",
        "/v1/ledger",
        label="ledger",
        why="the transparency log this site's checkpoints live in",
    )
    if expect_200(response, entry, failures):
        data = envelope_data(document) or {}
        world["ledger"] = {
            "site_code": data.get("site_code"),
            "leaves": len(data.get("leaves") or []),
            "nodes": len(data.get("nodes") or []),
            "checkpoints": len(data.get("checkpoints") or []),
            "cosignatures": len(data.get("cosignatures") or []),
            "inclusion_proofs": len(data.get("inclusion_proofs") or []),
            "consistency_proofs": len(data.get("consistency_proofs") or []),
            "unwitnessed_debt": data.get("unwitnessed_debt"),
        }

    return ids, world


def check_beat_three(beats: list[dict[str, Any]], failures: list[str]) -> dict[str, Any]:
    """Record beat 3's weaker diagnosis verbatim, and assert every part of it.

    This is the beat where the system says it cannot compute a nearest admissible answer. It is
    recorded exactly as it arrived, and it is asserted, because tidying it away would be claiming
    a stronger diagnosis than the engine produced — the one failure invariant I14 exists to
    prevent — and because a `naa` that quietly started coming back non-null would be a change in
    what the product says about itself.
    """
    beat = next((b for b in beats if b.get("name") == "projection_drift_attack"), None)
    if beat is None:
        failures.append("beat 3 (projection_drift_attack) is absent; its diagnosis cannot be read")
        return {"present": False}

    refusal = beat.get("refusal") or {}
    record: dict[str, Any] = {
        "present": True,
        "beat": beat.get("name"),
        "sqlstate": beat.get("sqlstate"),
        "constraint": beat.get("constraint"),
        "constraint_source": refusal.get("constraint_source"),
        "class": refusal.get("class"),
        "diagnosis": refusal.get("diagnosis"),
        "naa": refusal.get("naa"),
        "naa_reason": refusal.get("naa_reason"),
        "mus": refusal.get("mus"),
        "probe_calls": refusal.get("probe_calls"),
        "gate_epoch": refusal.get("gate_epoch"),
        "spec_version": refusal.get("spec_version"),
        "profile": refusal.get("profile"),
        "refusal_id": refusal.get("refusal_id"),
        "observed_at": refusal.get("observed_at"),
        "message": beat.get("message"),
        "why_this_is_recorded_and_not_tidied_away": (
            "On its strongest refusal the system reports that it cannot compute a nearest "
            "admissible answer: diagnosis 'none', naa null, naa_reason 'not_computable', and one "
            "MUS atom of kind capability_gap naming the function. trappoint.explain_refusal has "
            "no declarative decomposition for mainline.fn_permit_merge_gate and says so instead "
            "of shipping a plausible superset labelled declarative. That is a "
            "Product-Readiness point, not an embarrassment."
        ),
        "why_parsed_and_not_reported": (
            "CockroachDB populates no PL/pgSQL context stack, so psycopg's diag.constraint_name "
            "and diag.context are both None on a RAISE. The name is recovered from the kernel's "
            "own 'refused by <schema>.<object>' clause. parsed is a WEAKENED diagnosis and the "
            "payload says so, so a run whose exhibits were inferred never looks like a run whose "
            "exhibits were reported."
        ),
    }

    if refusal.get("constraint_source") != BEAT3_EXPECTED_DIAGNOSIS["constraint_source"]:
        failures.append(
            f"beat 3: constraint_source is {refusal.get('constraint_source')!r}, the contract "
            f"requires {BEAT3_EXPECTED_DIAGNOSIS['constraint_source']!r}"
        )
    if refusal.get("diagnosis") != BEAT3_EXPECTED_DIAGNOSIS["diagnosis"]:
        failures.append(
            f"beat 3: diagnosis is {refusal.get('diagnosis')!r}, the contract requires "
            f"{BEAT3_EXPECTED_DIAGNOSIS['diagnosis']!r} — a decomposition that started arriving "
            "here would be a change in what the product claims about its own explanation engine"
        )
    if refusal.get("naa") is not None:
        failures.append(
            f"beat 3: naa is {refusal.get('naa')!r}, the contract requires null on this refusal"
        )
    if refusal.get("naa_reason") != BEAT3_EXPECTED_DIAGNOSIS["naa_reason"]:
        failures.append(
            f"beat 3: naa_reason is {refusal.get('naa_reason')!r}, the contract requires "
            f"{BEAT3_EXPECTED_DIAGNOSIS['naa_reason']!r}"
        )
    mus = refusal.get("mus")
    if not isinstance(mus, list) or not mus:
        failures.append("beat 3: the MUS is empty; a refusal with no unsatisfiable core is bare")
    else:
        kinds = {atom.get("kind") for atom in mus if isinstance(atom, dict)}
        caps = {atom.get("capability") for atom in mus if isinstance(atom, dict)}
        record["mus_kinds"] = sorted(k for k in kinds if k)
        if BEAT3_EXPECTED_DIAGNOSIS["mus_kind"] not in kinds:
            failures.append(
                f"beat 3: the MUS carries kinds {sorted(k for k in kinds if k)}, and none is "
                f"{BEAT3_EXPECTED_DIAGNOSIS['mus_kind']!r}"
            )
        if BEAT3_EXPECTED_DIAGNOSIS["mus_capability"] not in caps:
            failures.append(
                f"beat 3: the MUS names {sorted(c for c in caps if c)}, not "
                f"{BEAT3_EXPECTED_DIAGNOSIS['mus_capability']!r}"
            )
    return record


def check_beat_four(beats: list[dict[str, Any]], failures: list[str]) -> dict[str, Any]:
    """The admission's exhibit: a clearance digest the SERVER computed, of the right shape."""
    beat = next((b for b in beats if b.get("name") == "admit"), None)
    if beat is None:
        failures.append("beat 4 (admit) is absent; there is no admission to exhibit")
        return {"present": False}
    observed = beat.get("observed") or {}
    record = observed.get("merge_record") or {}
    digest = record.get("clearance_digest")
    entry: dict[str, Any] = {
        "present": True,
        "sqlstate": beat.get("sqlstate"),
        "outcome": beat.get("outcome"),
        "clearance_digest": digest,
        "merged_commit": record.get("merged_commit"),
        "merged_at": record.get("merged_at"),
        "permit_state_inside_the_savepoint": record.get("permit_state"),
        "permit_open_blocking_inside_the_savepoint": record.get("permit_open_blocking"),
        "disposition_id": observed.get("disposition_id"),
        "disposition_kind": observed.get("disposition_kind"),
        "open_blocking_after_signature": observed.get("open_blocking_after_signature"),
        "computed_by": (
            "the server, over the sorted (check_id, disposition_id) set, inside the savepoint — "
            "then rolled back with the rest of the transaction"
        ),
        "value_is_observed_not_asserted": (
            "the disposition is minted fresh in every run, so two runs legitimately produce two "
            "digests; the SHAPE is asserted, the value is recorded"
        ),
        "why_a_fourth_beat_at_all": (
            "a gate that always refuses is broken, not safe: one signed disposition closes the "
            "counter through the projection trigger and the same merge succeeds"
        ),
    }
    if not isinstance(digest, str) or not SHA256_HEX.match(digest):
        failures.append(
            f"beat 4: clearance_digest is {digest!r}, which is not a lowercase 64-hex SHA-256"
        )
    return entry


def drive_the_gate(
    transcript: Transcript, failures: list[str]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One POST. Four beats. The whole product, in one SERIALIZABLE transaction that rolls back."""
    response, document, entry = transcript.send(
        "POST",
        GATE_RUN_PATH,
        label="gate_run",
        why="the four beats, in one transaction, on the deployed database",
        payload={},
    )
    record: dict[str, Any] = {"request": entry}
    if not expect_200(response, entry, failures):
        return record, None
    data = envelope_data(document)
    if data is None:
        failures.append("POST /v1/demo/gate-run did not answer an envelope with a data member")
        return record, None

    beats = data.get("beats") or []
    recorded, beat_failures = check_beats(data)
    failures.extend(beat_failures)

    persistence = data.get("persistence_check") or {}
    transaction = data.get("transaction") or {}
    beat_ms = [b.get("elapsed_ms") for b in beats if isinstance(b.get("elapsed_ms"), (int, float))]
    run_ms = data.get("elapsed_ms")

    record.update(
        {
            "run_id": data.get("run_id"),
            "generated_at": data.get("generated_at"),
            "outcome": data.get("outcome"),
            "verdict": data.get("verdict"),
            "server_failures": data.get("failures"),
            "persisted": data.get("persisted"),
            "schema_id": data.get("schema_id"),
            "subject": data.get("subject"),
            "transaction": transaction,
            "persistence_check": {
                "identical": persistence.get("identical"),
                "self_persisted": persistence.get("self_persisted"),
                "concurrent_writes": persistence.get("concurrent_writes"),
                "tables": persistence.get("tables"),
                "minted_disposition_id": (persistence.get("self_evidence") or {}).get(
                    "minted_disposition_id"
                ),
                "minted_disposition_rows_after_rollback": (
                    persistence.get("self_evidence") or {}
                ).get("minted_disposition_rows_after_rollback"),
                "permit_row_identical": (persistence.get("self_evidence") or {}).get(
                    "permit_row_identical"
                ),
                "note": persistence.get("note"),
                "how_to_read_identical": (
                    "identical answers 'did the DATABASE move', over unscoped whole-table counts, "
                    "so another judge's write between the two readings turns it false. "
                    "self_persisted answers 'did THIS RUN persist anything' and keys on the "
                    "minted disposition id no other writer could have produced. The verdict keys "
                    "on self_persisted (docs/deploy/gate-run-contract.md §3 amendment)."
                ),
            },
            "beats": recorded,
            "timing": {
                "wall_ms": entry["wall_ms"],
                "payload_run_elapsed_ms": run_ms,
                "beat_elapsed_ms": {
                    b.get("name"): b.get("elapsed_ms") for b in beats if isinstance(b, dict)
                },
                "beat_elapsed_ms_sum": round(sum(beat_ms), 3) if beat_ms else None,
                "network_and_cold_start_ms": (
                    round(entry["wall_ms"] - float(run_ms), 3)
                    if isinstance(run_ms, (int, float))
                    else None
                ),
                "why_three_levels": (
                    "wall_ms is this client's monotonic clock around the round trip; "
                    "payload_run_elapsed_ms is what the server said about the whole run; the "
                    "per-beat numbers are what it said about each statement. They are three "
                    "different measurements and the transcript never adds them together."
                ),
            },
        }
    )

    if data.get("verdict") != "PROVEN":
        failures.append(
            f"the server's own verdict is {data.get('verdict')!r} with failures "
            f"{data.get('failures')!r}"
        )
    if data.get("outcome") != "completed":
        failures.append(f"the run's outcome is {data.get('outcome')!r}, not 'completed'")
    if data.get("persisted") is not False:
        failures.append(f"the run reports persisted={data.get('persisted')!r}, not false")
    if persistence.get("self_persisted") is not False:
        failures.append(
            f"persistence_check.self_persisted is {persistence.get('self_persisted')!r}: this run "
            "persisted something and the demo's central claim is broken"
        )
    if transaction.get("single_transaction") is not True:
        failures.append(
            "transaction.single_transaction is not true: the two logical timestamps disagree, so "
            "the four beats did not share one transaction"
        )
    if transaction.get("isolation") != "SERIALIZABLE":
        failures.append(f"the transaction isolation is {transaction.get('isolation')!r}")
    if transaction.get("disposition") != "rolled_back":
        failures.append(
            f"the transaction disposition is {transaction.get('disposition')!r}, not rolled_back"
        )

    # Two clocks, and the assertion that they are two. A payload duration at or above the wall
    # clock would mean the number in the payload is not what it says it is.
    if isinstance(run_ms, (int, float)):
        if float(run_ms) >= entry["wall_ms"]:
            failures.append(
                f"the payload reports {run_ms} ms inside a round trip this client measured at "
                f"{entry['wall_ms']} ms: those cannot both be true, and conflating them is how a "
                "reveal delay gets narrated as database latency"
            )
        if beat_ms and round(sum(beat_ms), 3) > float(run_ms):
            failures.append(
                f"the four beats sum to {round(sum(beat_ms), 3)} ms inside a run the server timed "
                f"at {run_ms} ms"
            )

    record["beat_three_diagnosis"] = check_beat_three(beats, failures)
    record["beat_four_exhibit"] = check_beat_four(beats, failures)
    return record, data


def record_the_trap(transcript: Transcript, permit_id: str, failures: list[str]) -> dict[str, Any]:
    """RULING R4. Send the write-protected merge ONCE, and label what comes back a TRAP."""
    path = TRAP_PATH_TEMPLATE.format(permit_id=permit_id)
    response, document, entry = transcript.send(
        "POST",
        path,
        label="documented_trap",
        why="recorded once so that no operator screen ever wires an ISSUE button to it",
        payload={},
    )
    body = document if isinstance(document, dict) else {}
    record: dict[str, Any] = {
        "label": "DOCUMENTED TRAP — NOT A REFUSAL",
        "request": {"method": "POST", "path": path, "body": {}},
        "status": response.status,
        "response_bytes": entry["response_bytes"],
        "wall_ms": entry["wall_ms"],
        "payload_elapsed_ms": entry["payload_elapsed_ms"],
        "error": body.get("error"),
        "use_instead": body.get("use_instead"),
        "subject_id": body.get("subject_id"),
        "detail": body.get("detail"),
        "is_a_gate_refusal": False,
        "carries_a_sqlstate": False,
        "authority": "docs/deploy/gate-run-contract.md §7; proof-and-polish-plan.md ruling R4",
        "why_it_is_in_this_transcript": (
            "423 Locked is a write protection on a single shared public row, not the gate "
            "refusing. It carries no SQLSTATE, no constraint and no MUS. Rendering it in a "
            "refusal banner would put a fabricated exhibit in front of a judge, so it is recorded "
            "here once, labelled, with the endpoint it names instead — and every operator screen "
            "reads the label."
        ),
        "recorded_once": True,
    }
    if response.status != 423:
        failures.append(
            f"POST {path} answered {response.status}, not the documented 423 Locked"
            f"{describe_error_body(response)}"
        )
    for key, expected in TRAP_EXPECTED.items():
        if body.get(key) != expected:
            failures.append(f"the 423 body's {key} is {body.get(key)!r}, not {expected!r}")
    return record


def check_request_discipline(transcript: Transcript, failures: list[str]) -> dict[str, Any]:
    """R4 again, asserted against this program's own transcript rather than trusted."""
    methods: dict[str, int] = {}
    for entry in transcript.entries:
        methods[entry["method"]] = methods.get(entry["method"], 0) + 1
    posts = [e for e in transcript.entries if e["method"] == "POST"]
    gate_runs = [e for e in posts if e["path"] == GATE_RUN_PATH]
    traps = [e for e in posts if e["path"].endswith("/merge")]

    record = {
        "rule": (
            "against the live URL: every GET, POST /v1/demo/gate-run, and the one documented "
            "423 trap. Nothing else on the wire."
        ),
        "authority": "proof-and-polish-plan.md ruling R4",
        "methods": methods,
        "post_count": len(posts),
        "gate_run_count": len(gate_runs),
        "trap_count": len(traps),
        "total_requests": len(transcript.entries),
    }
    if len(gate_runs) != 1:
        failures.append(
            f"{len(gate_runs)} gate-run requests were sent; the 'one request, four beats' claim "
            "requires exactly one"
        )
    if len(traps) != 1:
        failures.append(f"{len(traps)} trap requests were sent; R4 permits exactly one")
    if len(posts) != len(gate_runs) + len(traps):
        failures.append("a POST was sent that is neither the gate run nor the documented trap")
    for entry in transcript.entries:
        if entry["method"] not in {"GET", "POST"}:
            failures.append(f"a {entry['method']} was sent to {entry['path']}; R4 forbids it")
    return record


def one_request_four_beats(
    gate: dict[str, Any], data: dict[str, Any] | None, failures: list[str]
) -> dict[str, Any]:
    """The line the operator screens' progressive disclosure stands on."""
    entry = gate.get("request") or {}
    beats = (data or {}).get("beats") or []
    timestamp = entry.get("response_date_iso") or entry.get("payload_observed_at")
    line = (
        f"one request - four beats - response received {timestamp}"
        f" (x-amzn-requestid {entry.get('request_id')})"
    )
    record = {
        "line": line,
        "line_as_written": (f"one request — four beats — response received {timestamp}"),
        "request_id": entry.get("request_id"),
        "request_id_header": "x-amzn-requestid",
        "request_id_issued_by": "the AWS Lambda Function URL that served this request",
        "run_id": (data or {}).get("run_id"),
        "response_timestamp": timestamp,
        "response_timestamp_source": "the HTTP Date header on the single gate-run response",
        "response_date_header": entry.get("response_date_header"),
        "payload_observed_at": entry.get("payload_observed_at"),
        "payload_generated_at": (data or {}).get("generated_at"),
        "beat_count": len(beats),
        "beat_names": [b.get("name") for b in beats],
        "response_bytes": entry.get("response_bytes"),
        "why_it_matters": (
            "the operator screens reveal the beats one at a time. That is defensible only "
            "because all four arrived in ONE response body, under one request id, at one "
            "timestamp — the reveal is a rendering choice, not four requests wearing a costume. "
            "Any delay a viewer sees between beats belongs to the screen and is never to be "
            "narrated as database latency."
        ),
    }
    if len(beats) != 4:
        failures.append(f"the single gate-run response carried {len(beats)} beats, not four")
    if not entry.get("request_id"):
        failures.append("the gate-run response carried no x-amzn-requestid to name")
    if not timestamp:
        failures.append("the gate-run response carried no timestamp to name")
    return record


def compare_permit(
    label: str,
    transcript: Transcript,
    permit_id: str,
    before: dict[str, Any] | None,
    why: str,
    failures: list[str],
) -> dict[str, Any]:
    """Re-read the permit and compare the four fields that must not have moved."""
    response, document, entry = transcript.send(
        "GET", f"/v1/permits/{permit_id}", label=label, why=why
    )
    if not expect_200(response, entry, failures) or envelope_data(document) is None:
        return {"read": False}
    after = permit_snapshot_from_read(document)
    drift = {
        field: {"before": (before or {}).get(field), "after": after.get(field)}
        for field in PERMIT_INVARIANT_FIELDS
        if before is not None and (before or {}).get(field) != after.get(field)
    }
    if drift:
        failures.append(
            f"the permit moved between the before-reading and {label}: {json.dumps(drift)}. "
            "open_blocking is the one that carries the argument — if beat 4's signature survived "
            "the rollback, the next judge sees a permit that merges with no refusal at all"
        )
    return {"read": True, "snapshot": after, "drift": drift, "unchanged": not drift}


def build_document(
    *,
    base: str,
    argv: list[str],
    transcript: Transcript,
    world: dict[str, Any],
    gate: dict[str, Any],
    trap: dict[str, Any],
    disclosure: dict[str, Any],
    discipline: dict[str, Any],
    invariant: dict[str, Any],
    failures: list[str],
) -> dict[str, Any]:
    proven = not failures and not transcript.transport_failures
    return {
        "artefact": "live-beats",
        "schema": "mainline.evidence/live-beats/1",
        "generated_at": utc_now(),
        "generated_by": "scripts/proof/live_beats.py",
        "owner": "proof-and-polish worker P2",
        "command": " ".join([".venv/Scripts/python.exe", "scripts/proof/live_beats.py", *argv]),
        "base_url": base,
        "credentials_used": "none - no DSN, no AWS profile, no token; a stranger with the URL",
        "target_is_local_emulator": transcript.emulator_seen,
        "verdict": "PROVEN" if proven else "NOT PROVEN",
        "failures": failures,
        "transport_failures": transcript.transport_failures,
        "what_is_asserted": {
            "beats": [
                "read 00000",
                "merge REFUSED 23514 gate_closed_when_issued (constraint_source reported)",
                (
                    "projection_drift_attack REFUSED P0001 mainline.fn_permit_merge_gate "
                    "(constraint_source parsed)"
                ),
                "admit ADMITTED 00000 with a server-computed clearance_digest",
            ],
            "note": (
                "the SQLSTATEs are asserted here, not read off the server's own verdict. A "
                "different SQLSTATE is a regression even when a verdict still says PROVEN."
            ),
            "beat_table_source": (
                "scripts/deploy/demo_acceptance.EXPECTED_BEATS (imported, not copied)"
            ),
        },
        "one_request_four_beats": disclosure,
        "request_discipline": discipline,
        "timing_discipline": {
            "wall_ms": (
                "this client's monotonic clock around the round trip: DNS, TLS, the trip to the "
                "region and back, any cold start, and JSON parsing"
            ),
            "payload_elapsed_ms": (
                "what the server said about itself, taken from the JSON pointer recorded beside "
                "it. null where the envelope carries no duration at all — which is every read on "
                "this API. An absent measurement is written down as absent, never as a zero and "
                "never as the wall clock wearing a server's name."
            ),
            "beat_elapsed_ms": "the server's own per-statement durations, inside the gate run",
            "they_are_never_added": (
                "wall_ms is not a database latency and the payload durations are not a user's "
                "experience. Both are recorded so a reader can see the gap rather than be told it."
            ),
        },
        "world": world,
        "gate_run": gate,
        "permit_invariant": invariant,
        "documented_traps": [trap],
        "requests": transcript.entries,
        "not_proven_by_this_transcript": list(NOT_PROVEN_BY_THIS_TRANSCRIPT),
        "reproduce": {
            "command": (".venv/Scripts/python.exe scripts/proof/live_beats.py --base-url " + base),
            "needs": "python 3.13 and the URL. No credential, no database, no AWS access.",
            "expect": (
                "exit 0 and VERDICT PROVEN, with different timings and a different "
                "clearance_digest — the digest is minted fresh in every run"
            ),
        },
        "redaction": {
            "applied": "scripts/deploy/judge_walk.mask over the whole document",
            "masks": "DSNs, URL credentials, password/token key-values, 12-digit account ids",
            "verified": "the four SQLSTATEs and the clearance digest are re-checked after masking",
        },
    }


def verify_redaction_did_not_touch_the_evidence(
    document: dict[str, Any], expected_sqlstates: list[str], digest: str | None
) -> list[str]:
    """A masker that quietly rewrote a measured value would be worse than no masker."""
    problems: list[str] = []
    beats = ((document.get("gate_run") or {}).get("beats")) or []
    seen = [b.get("sqlstate") for b in beats]
    if seen != expected_sqlstates:
        problems.append(
            f"the SQLSTATEs in the written document are {seen}, not {expected_sqlstates}: the "
            "redaction pass altered a measured value"
        )
    written = ((document.get("gate_run") or {}).get("beat_four_exhibit") or {}).get(
        "clearance_digest"
    )
    if digest is not None and written != digest:
        problems.append("the clearance digest was altered by the redaction pass")
    return problems


def summarise(document: dict[str, Any], out: Path) -> None:
    say("")
    say("MAINLINE - the four beats, live")
    say("  target      ", document["base_url"])
    say("  taken       ", document["generated_at"], "UTC")
    say("  credentials ", document["credentials_used"])
    health = (document.get("world") or {}).get("health") or {}
    if health:
        say(
            "  health      ",
            f"ok={health.get('ok')}",
            f"db={health.get('database')}",
            f"chain={health.get('deploy_chain_applied')}/{health.get('deploy_chain_files')}",
        )
    if document.get("target_is_local_emulator"):
        say("  NOTE         this target is the LOCAL EMULATOR, not a deployed demo URL")
    say("")
    for beat in ((document.get("gate_run") or {}).get("beats")) or []:
        exhibit = beat.get("constraint") or ""
        source = f"({beat.get('constraint_source')})" if beat.get("constraint_source") else ""
        say(
            f"  BEAT {beat.get('ordinal')}  {beat.get('name')!s:24s}"
            f"  {beat.get('sqlstate')!s:6s} {str(beat.get('outcome')).upper():9s}"
            f"  {exhibit} {source}".rstrip(),
            f" server {beat.get('ms')} ms",
        )
    exhibit4 = ((document.get("gate_run") or {}).get("beat_four_exhibit")) or {}
    if exhibit4.get("clearance_digest"):
        say("          clearance_digest", exhibit4["clearance_digest"])
    beat3 = ((document.get("gate_run") or {}).get("beat_three_diagnosis")) or {}
    if beat3.get("present"):
        say(
            "          beat 3 diagnosis",
            f"constraint_source={beat3.get('constraint_source')}",
            f"naa={beat3.get('naa')}",
            f"naa_reason={beat3.get('naa_reason')}",
            f"mus={beat3.get('mus_kinds')}",
        )
    say("")
    disclosure = (document.get("one_request_four_beats") or {}).get("line")
    if disclosure:
        say("  " + disclosure)
    timing = ((document.get("gate_run") or {}).get("timing")) or {}
    if timing:
        say(
            "  clocks       ",
            f"wall {timing.get('wall_ms')} ms",
            f"| server-run {timing.get('payload_run_elapsed_ms')} ms",
            f"| beats sum {timing.get('beat_elapsed_ms_sum')} ms",
        )
    # An absent trap is reported as absent. A summary line that printed `None -> None` beside
    # the words NOT A REFUSAL would be narrating a request that was never sent.
    trap = next(iter(document.get("documented_traps") or []), None)
    if trap and trap.get("status"):
        say(
            "  trap         ",
            f"POST {(trap.get('request') or {}).get('path')} -> {trap.get('status')}",
            f"use_instead {trap.get('use_instead')}  [NOT A REFUSAL]",
        )
    else:
        say("  trap          NOT RECORDED - the documented 423 was never reached")
    say("  requests     ", f"{len(document.get('requests') or [])} in this sitting")
    say("  transcript   ", str(out.resolve()))
    say("")
    for failure in document.get("failures") or []:
        say("  FAILURE      ", failure)
    for failure in document.get("transport_failures") or []:
        say("  UNREACHABLE  ", failure)
    say("VERDICT", document["verdict"])


#: A NEGATIVE CONTROL. Not a measurement, never written to the evidence file, never printed as
#: an outcome, and reachable only from ``--self-test``. It exists so that the beat assertions can
#: be FALSIFIED on a machine with no network: a guard nobody has driven red is decoration, and
#: this file's whole job is to go red when a SQLSTATE moves. The values below are the shape the
#: contract requires, so every mutation in ``self_test`` is a departure from the contract and
#: must produce a failure line.
def _negative_control_payload() -> dict[str, Any]:
    """A synthetic, well-formed gate run. SYNTHETIC — it never reaches the transcript."""
    return {
        "verdict": "PROVEN",
        "beats": [
            {
                "ordinal": 1,
                "name": "read",
                "outcome": "read",
                "sqlstate": "00000",
                "constraint": None,
                "constraint_source": None,
                "matched_expectation": True,
                "elapsed_ms": 0.0,
            },
            {
                "ordinal": 2,
                "name": "merge",
                "outcome": "refused",
                "sqlstate": "23514",
                "constraint": "gate_closed_when_issued",
                "constraint_source": "reported",
                "matched_expectation": True,
                "elapsed_ms": 0.0,
            },
            {
                "ordinal": 3,
                "name": "projection_drift_attack",
                "outcome": "refused",
                "sqlstate": "P0001",
                "constraint": "mainline.fn_permit_merge_gate",
                "constraint_source": "parsed",
                "matched_expectation": True,
                "elapsed_ms": 0.0,
                "refusal": {
                    "constraint_source": "parsed",
                    "diagnosis": "none",
                    "naa": None,
                    "naa_reason": "not_computable",
                    "mus": [
                        {
                            "kind": "capability_gap",
                            "capability": "mainline.fn_permit_merge_gate",
                        }
                    ],
                },
            },
            {
                "ordinal": 4,
                "name": "admit",
                "outcome": "admitted",
                "sqlstate": "00000",
                "constraint": None,
                "constraint_source": None,
                "matched_expectation": True,
                "elapsed_ms": 0.0,
                "observed": {"merge_record": {"clearance_digest": "0" * 64}},
            },
        ],
    }


def _beat(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(b for b in payload["beats"] if b["name"] == name)


def self_test() -> int:
    """Drive every assertion red on purpose. No network, no evidence file, no verdict.

    ``docs/regression/GUARD.md``: *"A guard nobody has falsified is decoration."* Each case below
    changes exactly one thing away from the contract and requires this program to notice. The
    first case changes nothing and requires SILENCE — a checker that fails on everything is as
    useless as one that fails on nothing.
    """
    cases: list[tuple[str, Any, bool]] = [
        ("the contract shape itself", lambda p: p, False),
        (
            "beat 3's SQLSTATE moved P0001 -> 23514",
            lambda p: _beat(p, "projection_drift_attack").update({"sqlstate": "23514"}) or p,
            True,
        ),
        (
            "beat 2's constraint renamed",
            lambda p: _beat(p, "merge").update({"constraint": "some_other_check"}) or p,
            True,
        ),
        (
            "beat 3 claims 'reported' provenance the platform cannot supply",
            lambda p: (
                _beat(p, "projection_drift_attack")["refusal"].update(
                    {"constraint_source": "reported"}
                )
                or _beat(p, "projection_drift_attack").update({"constraint_source": "reported"})
                or p
            ),
            True,
        ),
        (
            "beat 3 grew a nearest-admissible answer it cannot compute",
            lambda p: (
                _beat(p, "projection_drift_attack")["refusal"].update(
                    {"naa": {"open_blocking": 0}, "naa_reason": "computed"}
                )
                or p
            ),
            True,
        ),
        (
            "beat 3's MUS emptied",
            lambda p: _beat(p, "projection_drift_attack")["refusal"].update({"mus": []}) or p,
            True,
        ),
        (
            "beat 4 admitted with no clearance digest",
            lambda p: _beat(p, "admit")["observed"].update({"merge_record": {}}) or p,
            True,
        ),
        (
            "beat 4's digest is not a SHA-256",
            lambda p: (
                _beat(p, "admit")["observed"]["merge_record"].update(
                    {"clearance_digest": "not-a-digest"}
                )
                or p
            ),
            True,
        ),
    ]

    say("")
    say("SELF-TEST - the negative control. SYNTHETIC payloads; nothing here is a measurement,")
    say("            nothing is written to evidence/, and no request leaves this machine.")
    say("")
    wrong = 0
    for description, mutate, should_fail in cases:
        payload = mutate(_negative_control_payload())
        failures: list[str] = []
        _, beat_failures = check_beats(payload)
        failures.extend(beat_failures)
        check_beat_three(payload["beats"], failures)
        check_beat_four(payload["beats"], failures)
        went_red = bool(failures)
        verdict = "PASS" if went_red == should_fail else "WRONG"
        if verdict == "WRONG":
            wrong += 1
        expectation = "must go red" if should_fail else "must stay silent"
        say(f"  {verdict}  {description}  ({expectation}; {len(failures)} failure(s))")
        if verdict == "WRONG" and failures:
            for failure in failures:
                say("        unexpected:", failure)
    say("")
    if wrong:
        say(f"SELF-TEST FAILED - {wrong} case(s) did not behave as the contract requires")
        return EXIT_WRONG
    say(f"SELF-TEST PASSED - {len(cases)} cases, and the assertions can go red")
    return EXIT_PROVEN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_beats.py",
        description=(
            "Drive the deployed demo as a stranger with a URL and prove the four beats came off "
            "it. Writes evidence/demo/live-beats.json."
        ),
    )
    parser.add_argument(
        "--base-url",
        help="the demo origin, e.g. https://<id>.lambda-url.<region>.on.aws",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="falsify the beat assertions offline; writes nothing and sends no request",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help=f"where to write the transcript (default {DEFAULT_OUT})",
    )
    parser.add_argument("--timeout", type=float, default=90.0, help="per-request seconds")
    parser.add_argument("--print-json", action="store_true", help="also print the document")
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(args_list)

    if args.self_test:
        return self_test()
    if not args.base_url:
        say("usage: --base-url is required (or --self-test to falsify the assertions offline)")
        return EXIT_USAGE

    base = args.base_url if args.base_url.endswith("/") else args.base_url + "/"
    parts = urlsplit(base)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        say(f"usage: --base-url must be an http(s) origin, not {args.base_url!r}")
        return EXIT_USAGE

    failures: list[str] = []
    transcript = Transcript(base, args.timeout)

    ids, world = read_the_world(transcript, failures)
    permit_id = ids.get("permit_id")

    gate: dict[str, Any] = {}
    data: dict[str, Any] | None = None
    trap: dict[str, Any] = {}
    invariant: dict[str, Any] = {}

    if permit_id:
        before = world.get("permit_before_snapshot")
        gate, data = drive_the_gate(transcript, failures)
        if data is not None:
            subject_snapshot = permit_snapshot_from_subject(data.get("subject") or {})
            invariant["gate_run_subject_snapshot"] = subject_snapshot
        invariant["before"] = before
        invariant["after_gate_run"] = compare_permit(
            "permit_after_gate_run",
            transcript,
            permit_id,
            before,
            "the same four fields, after the gate ran — the rollback, proven from outside",
            failures,
        )
        trap = record_the_trap(transcript, permit_id, failures)
        invariant["after_trap"] = compare_permit(
            "permit_after_trap",
            transcript,
            permit_id,
            before,
            "and again after the 423, because a write protection that wrote would be worse",
            failures,
        )
        invariant["fields"] = list(PERMIT_INVARIANT_FIELDS)
        invariant["why"] = (
            "beat 4 signs a disposition, which closes the obligation and takes open_blocking to "
            "zero. If that survived the rollback the next judge would see a permit that merges "
            "with no refusal at all, and the demo would silently stop demonstrating anything."
        )
    else:
        failures.append(
            "no permit_id was discovered, so the gate was not driven: this is 'there was nothing "
            "to ask', which is a different finding from 'the gate did not refuse'"
        )

    disclosure = one_request_four_beats(gate, data, failures) if gate else {}
    discipline = check_request_discipline(transcript, failures)

    document = build_document(
        base=base,
        argv=args_list,
        transcript=transcript,
        world=world,
        gate=gate,
        trap=trap,
        disclosure=disclosure,
        discipline=discipline,
        invariant=invariant,
        failures=failures,
    )

    expected_sqlstates = [b.get("sqlstate") for b in (gate.get("beats") or [])]
    digest = (gate.get("beat_four_exhibit") or {}).get("clearance_digest")
    masked: dict[str, Any] = json.loads(mask(json.dumps(document, default=str)))
    redaction_problems = verify_redaction_did_not_touch_the_evidence(
        masked, expected_sqlstates, digest
    )
    if redaction_problems:
        masked["failures"] = [*masked.get("failures", []), *redaction_problems]
        masked["verdict"] = "NOT PROVEN"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(masked, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    summarise(masked, out)
    if args.print_json:
        say(json.dumps(masked, indent=2))

    if transcript.transport_failures and not any(e["status"] for e in transcript.entries):
        return EXIT_UNREACHABLE
    if masked["verdict"] != "PROVEN":
        return EXIT_WRONG
    return EXIT_PROVEN


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    sys.exit(main())
