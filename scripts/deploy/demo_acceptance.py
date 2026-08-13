#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Prove, from outside and with no credentials, that the deployed demo does what we claim.

WHAT THIS IS FOR
----------------
``scripts/deploy/deploy.sh`` runs this last and exits on it. **A deploy that cannot prove itself
is a failed deploy** — a green ``terraform apply`` says CloudFront exists, not that the gate
refuses. The only thing that establishes the submission's central claim is a stranger with a URL
and no credentials watching the database refuse a merge and then admit one.

So this program is written as that stranger. It takes a URL. It has no DSN, no AWS profile, no
knowledge of the seed. Everything it asserts, it asserts about bytes that came back over HTTPS.

THE TWO MODES, AND WHY THE MODE IS PRINTED FIRST
------------------------------------------------
``--phase2`` (default) is the live stack: the console, ``GET /v1/health``, and
``POST /v1/demo/gate-run`` against CockroachDB Cloud.

``--phase1`` is the fallback the deployment lead pre-committed to (``deploy-plan.md`` §4): the
static console over a cryptographically verified EvidenceBundle, no backend at all. It checks the
static path and re-verifies every file in the bundle manifest against its recorded SHA-256, from
outside, over the same CDN a judge uses.

**A green run against the wrong mode is worse than a red one**, because it certifies a claim
nobody made. So the mode is the first line of output, the first key in the evidence file, and
part of the verdict string. ``--phase2`` never silently degrades to ``--phase1``: if the API is
absent, this program fails and says the API is absent.

WHAT "IDENTICAL ACROSS TWO RUNS" MEANS, PRECISELY
-------------------------------------------------
The gate run is called twice and the two payloads are compared. They are NOT compared byte for
byte — ``run_id``, ``generated_at``, the elapsed timings, the logical timestamps and the
per-request identifiers all legitimately differ, and an assertion that they do not would fail on
a correct server.

What is compared is the **stable projection**: for each beat its ``name``, ``expected``,
``outcome``, ``sqlstate``, ``constraint``, ``constraint_source`` and ``matched_expectation``, plus
the run's ``verdict``, its ``persisted`` flag, the subject identifiers and
``persistence_check.identical``. That set is exactly the set of things the demo claims, and it is
the set that must not move between two judges pressing the same button. Every excluded field is
listed in the evidence file under ``volatile_fields`` so a reader can see what was not compared
rather than having to trust that the comparison was fair.

``clearance_digest`` is deliberately OBSERVED rather than asserted. It is computed over the sorted
``(check_id, disposition_id)`` set and the disposition is inserted fresh inside each run, so two
runs may legitimately produce two digests. The evidence records both and notes whether they
matched; it does not fail on a difference, because failing there would be asserting a property of
the seed rather than of the gate.

WHY ``persisted: false`` IS CHECKED AND NOT ASSUMED
----------------------------------------------------
It is the reason the demo needs no reset button, no session table and no lock, and therefore the
reason fifty judges can press the button at once. The payload proves it with row counts taken
before and after the transaction (``docs/deploy/gate-run-contract.md`` §3); this program asserts
both the flag and ``persistence_check.identical``, because a ``persisted: false`` beside a
``persistence_check.identical: false`` is a server contradicting itself and that is worth catching.

AND THEN IT IS CHECKED AGAIN, FROM OUTSIDE, WITH A DIFFERENT ENDPOINT
---------------------------------------------------------------------
``persisted: false`` is the server's word about itself. So after each gate run this program reads
``GET /v1/permits/{permit_id}`` — a different resource, a different code path, a different
transaction — and compares ``counters.open_blocking``, ``state``, ``gate_epoch`` and ``head_seq``
with what they were before. **If the four beats really rolled back, the committed permit is
byte-identical afterwards.** That is the property ``evidence/deploy/lead/savepoint-probe-20260810
.txt`` established by hand at the SQL layer; here it is established over HTTP by a caller with no
credentials, which is the only version a judge can reproduce.

A drift in ``open_blocking`` is the specific failure that would matter: the fourth beat signs a
disposition, which closes the obligation and takes the counter to zero. If that survived the
rollback, the second judge to press the button would see a permit that merges immediately and the
demo would silently stop demonstrating anything.

THE AFTER-READING IS TAKEN WHATEVER THE GATE RUN DID, AND THAT IS A CORRECTION
------------------------------------------------------------------------------
Until 2026-08-13 the re-read lived on the **success path**: a gate run that answered anything but
``200`` took a ``continue`` and the loop reached neither the after-reading nor the next one. So
``evidence/deploy/acceptance.json`` for 2026-08-11 carries one snapshot, ``before_run_1``, and a
failure line admitting the property could not be established — on the exact run where it was most
worth knowing. **A run that failed halfway is the case where "did anything persist?" has a real
answer**, because a request that errored after its third beat is precisely how a rollback would be
skipped. The reading is now unconditional: it is attempted after every gate run, 200 or not, and
the only thing that can prevent it is not knowing which permit to read.

The comparison is also no longer positional. It used to be ``snapshots[0]`` against
``snapshots[-1]``, which is satisfied by *any* two readings — including ``before_run_1`` against
``after_run_1``, leaving run 2 unbracketed. It is now by NAME: ``before_run_1`` must exist,
``after_run_2`` must exist, and **every** intermediate reading is compared against the before as
well, so a permit that moved during run 1 and moved back during run 2 is caught rather than
cancelling out.

THE TARGET MAY BE AN EMULATOR, AND THE EVIDENCE SAYS SO IN ITS OWN FIELD
-------------------------------------------------------------------------
``scripts/deploy/local_furl.py`` serves the real handler over a local socket so the demo can be
proven before ``terraform apply`` has ever run. It stamps ``X-Mainline-Emulator: local_furl`` on
every response; this program reads that header and writes ``target_is_local_emulator: true`` into
the evidence, with an advisory. A PROVEN verdict against the emulator is a true statement about
the handler, the console bundle and the database — and **not** a statement that a public demo URL
exists. Those two are different claims and the file keeps them apart.

EXIT CODES
----------
``0`` proven · ``1`` reachable and wrong · ``2`` usage · ``3`` not reachable at all.

Three-valued for the same reason the judge pack is: an operator, a CI job and a human all need
"we could not check" to be distinguishable from "we checked and it is wrong".
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import urljoin, urlsplit

EXIT_PROVEN: Final = 0
EXIT_WRONG: Final = 1
EXIT_USAGE: Final = 2
EXIT_UNREACHABLE: Final = 3

USER_AGENT: Final = "mainline-demo-acceptance/1.0 (+https://github.com/Shaugato/mainline)"

#: The four beats, in order, with what each must produce. This table IS the acceptance criterion;
#: it is transcribed from `docs/deploy/gate-run-contract.md` §1 and from the observed output of
#: `scripts/proof/gate_refusal.py`, and nothing else in this file hard-codes an expectation.
#:
#: Beat 3 is the one to read twice. The projected counter is forced to zero out of band — exactly
#: what a disarmed projector or a careless UPDATE leaves behind — so the CHECK constraint of beat
#: 2 is now satisfied and would admit the merge. It is refused anyway, because
#: `mainline.fn_permit_merge_gate` RE-DERIVES the open count instead of trusting the column. That
#: is the beat that distinguishes this product from a CHECK constraint, and it is why
#: `constraint_source` is asserted: `parsed` means the name was recovered from the kernel's own
#: message because CockroachDB populates no PL/pgSQL context stack. A run whose exhibits were
#: inferred must never look like a run whose exhibits were reported.
EXPECTED_BEATS: Final[tuple[dict[str, Any], ...]] = (
    {
        "ordinal": 1,
        "name": "read",
        "outcome": "read",
        "sqlstate": "00000",
        "constraint": None,
        "constraint_source": None,
        "why": "the permit and its open obligation, read from the cluster",
    },
    {
        "ordinal": 2,
        "name": "merge",
        "outcome": "refused",
        "sqlstate": "23514",
        "constraint": "gate_closed_when_issued",
        "constraint_source": "reported",
        "why": "a plain CHECK refuses the merge while an obligation is open",
    },
    {
        "ordinal": 3,
        "name": "projection_drift_attack",
        "outcome": "refused",
        "sqlstate": "P0001",
        "constraint": "mainline.fn_permit_merge_gate",
        "constraint_source": "parsed",
        "why": "the counter is forged to zero and the gate refuses anyway, by re-deriving it",
    },
    {
        "ordinal": 4,
        "name": "admit",
        "outcome": "admitted",
        "sqlstate": "00000",
        "constraint": None,
        "constraint_source": None,
        "why": (
            "one signed disposition, and the same merge succeeds — a gate that always "
            "refuses is broken"
        ),
    },
)

#: The permit fields that MUST NOT MOVE across two gate runs. Read from
#: ``GET /v1/permits/{permit_id}`` — a different endpoint from the one under test — and compared
#: with the same four fields as the gate run reported for its own subject before it started.
#:
#: ``open_blocking`` is the one that carries the argument. Beat 4 signs a disposition against the
#: open obligation, which closes it; if the transaction did not roll back, this reads 0 afterwards
#: and every subsequent judge sees a permit that merges with no refusal at all.
PERMIT_INVARIANT_FIELDS: Final[tuple[str, ...]] = (
    "open_blocking",
    "state",
    "gate_epoch",
    "head_seq",
)

#: How many times the gate is driven. TWO, and the number is named rather than spelled out at
#: each use, because the invariant check asks for a reading called ``after_run_{GATE_RUNS}`` by
#: name and a third run added without moving that expectation would leave the last one
#: unbracketed while every assertion still passed.
GATE_RUNS: Final = 2

#: Set by ``scripts/deploy/local_furl.py`` on every response. Its presence means the target is a
#: local emulator of a Lambda Function URL and NOT a deployed demo.
EMULATOR_HEADER: Final = "x-mainline-emulator"

#: Excluded from the two-run comparison, and named in the evidence so the exclusion is auditable.
VOLATILE_FIELDS: Final[tuple[str, ...]] = (
    "run_id",
    "generated_at",
    "observed_at",
    "refusal_id",
    "elapsed_ms",
    "ms",
    "seconds",
    "opened_logical_timestamp",
    "closed_logical_timestamp",
    "disposition_id",
    "clearance_digest",
    "message",
)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fetched:
    """One HTTP round trip, with the timing attached because latency is part of the claim."""

    __slots__ = ("body", "elapsed_ms", "error", "headers", "status", "url")

    def __init__(
        self,
        url: str,
        status: int,
        headers: dict[str, str],
        body: bytes,
        elapsed_ms: float,
        error: str | None = None,
    ) -> None:
        self.url = url
        self.status = status
        self.headers = headers
        self.body = body
        self.elapsed_ms = elapsed_ms
        self.error = error

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "ms": self.elapsed_ms,
            "bytes": len(self.body),
            "content_type": self.headers.get("content-type"),
            **({"error": self.error} if self.error else {}),
        }


def fetch(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 45.0,
    insecure: bool = False,
) -> Fetched:
    """One request. A non-2xx is a RESULT, not an exception — the status is the evidence.

    Only a transport failure (DNS, TLS, connection refused, timeout) produces ``status = 0``,
    which is what separates exit code 3 from exit code 1.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    # S310: the scheme is checked in main() before any request is built, so `file:` and
    # custom schemes cannot reach here.
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/json, text/html;q=0.9, */*;q=0.5")
    if data is not None:
        request.add_header("Content-Type", "application/json")

    context = ssl.create_default_context()
    if insecure:
        # Only for a local shim over plain HTTP or a self-signed staging host. Never a default,
        # and the evidence file records that it was used.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    started = time.monotonic()
    try:
        with urllib.request.urlopen(  # noqa: S310 - scheme checked in main()
            request, timeout=timeout, context=context
        ) as response:
            body = response.read()
            elapsed = round((time.monotonic() - started) * 1000, 1)
            headers = {k.lower(): v for k, v in response.headers.items()}
            return Fetched(url, response.status, headers, body, elapsed)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        elapsed = round((time.monotonic() - started) * 1000, 1)
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return Fetched(url, exc.code, headers, body, elapsed)
    except Exception as exc:  # noqa: BLE001 - transport failure of any kind is one outcome
        elapsed = round((time.monotonic() - started) * 1000, 1)
        return Fetched(url, 0, {}, b"", elapsed, error=f"{type(exc).__name__}: {exc}")


def stable_projection(data: dict[str, Any]) -> dict[str, Any]:
    """The part of a gate-run payload that must not move between two judges.

    See the module docstring. Everything omitted here is omitted on purpose and listed in
    ``VOLATILE_FIELDS``.
    """
    beats = []
    for beat in data.get("beats", []):
        beats.append(
            {
                "ordinal": beat.get("ordinal"),
                "name": beat.get("name"),
                "expected": beat.get("expected"),
                "outcome": beat.get("outcome"),
                "sqlstate": beat.get("sqlstate"),
                "constraint": beat.get("constraint"),
                "constraint_source": beat.get("constraint_source"),
                "matched_expectation": beat.get("matched_expectation"),
            }
        )
    persistence = data.get("persistence_check") or {}
    return {
        "verdict": data.get("verdict"),
        "outcome": data.get("outcome"),
        "persisted": data.get("persisted"),
        "persistence_identical": persistence.get("identical"),
        "subject": data.get("subject"),
        "beats": beats,
    }


def permit_snapshot_from_read(payload: dict[str, Any]) -> dict[str, Any]:
    """The four invariant fields, out of a ``GET /v1/permits/{id}`` envelope."""
    data = payload.get("data", payload)
    counters = data.get("counters") or {}
    return {
        "permit_id": data.get("permit_id"),
        "open_blocking": counters.get("open_blocking"),
        "state": data.get("state"),
        "gate_epoch": data.get("gate_epoch"),
        "head_seq": data.get("head_seq"),
    }


def permit_snapshot_from_subject(subject: dict[str, Any]) -> dict[str, Any]:
    """The same four fields, out of a gate run's ``subject`` block.

    ``scenario.ResolvedScenario.as_json`` reads them in ONE statement at the top of the run,
    before any beat has executed, so this is a legitimate "before" even though it arrives inside
    the payload of the thing being measured. It is labelled as such in the evidence.
    """
    return {
        "permit_id": subject.get("subject_id"),
        "open_blocking": subject.get("open_blocking"),
        "state": subject.get("state"),
        "gate_epoch": subject.get("gate_epoch"),
        "head_seq": subject.get("head_seq"),
    }


def payload_target_is_emulator(evidence: Mapping[str, Any]) -> bool:
    """Whether this run was taken against ``scripts/deploy/local_furl.py``."""
    return bool(evidence.get("target_is_local_emulator"))


def describe_error_body(response: Fetched) -> str:
    """Name what a non-2xx said, not merely that it was not 200.

    The API's error contract is ``{"error": {"kind", "status", "detail", …}}`` and the detail is
    where the SQLSTATE lives. A failure line that reports only the status sends whoever reads it
    to the server logs to learn what this response already told them.
    """
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 - a non-JSON body is reported as its own first line
        text = response.body[:200].decode("utf-8", "replace").strip()
        return f" body: {text!r}" if text else ""
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        parts = [str(error.get("kind"))]
        if error.get("resource"):
            parts.append(f"resource={error['resource']}")
        if error.get("detail"):
            parts.append(str(error["detail"])[:300])
        return " — " + " · ".join(p for p in parts if p and p != "None")
    return f" body: {json.dumps(body)[:300]}"


def check_beats(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Assert the four beats verbatim. Returns ``(recorded, failures)``."""
    failures: list[str] = []
    recorded: list[dict[str, Any]] = []
    beats = data.get("beats") or []

    if len(beats) != len(EXPECTED_BEATS):
        failures.append(
            f"the payload carries {len(beats)} beats; the contract names {len(EXPECTED_BEATS)}"
        )

    for expected in EXPECTED_BEATS:
        found = next((b for b in beats if b.get("name") == expected["name"]), None)
        if found is None:
            failures.append(f"beat {expected['ordinal']} ({expected['name']}) is absent")
            recorded.append({"name": expected["name"], "present": False})
            continue

        entry = {
            "ordinal": found.get("ordinal"),
            "name": found.get("name"),
            "label": found.get("label"),
            "outcome": found.get("outcome"),
            "sqlstate": found.get("sqlstate"),
            "constraint": found.get("constraint"),
            "constraint_source": found.get("constraint_source"),
            "matched_expectation": found.get("matched_expectation"),
            "message": (found.get("message") or "")[:400] or None,
            "ms": found.get("elapsed_ms"),
            "expected": {
                "outcome": expected["outcome"],
                "sqlstate": expected["sqlstate"],
                "constraint": expected["constraint"],
                "constraint_source": expected["constraint_source"],
            },
            "why_it_matters": expected["why"],
            "present": True,
        }

        for field in ("outcome", "sqlstate"):
            if found.get(field) != expected[field]:
                failures.append(
                    f"beat {expected['ordinal']} ({expected['name']}): {field} is "
                    f"{found.get(field)!r}, the contract requires {expected[field]!r}"
                )
        if expected["constraint"] is not None and found.get("constraint") != expected["constraint"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): constraint is "
                f"{found.get('constraint')!r}, the contract requires {expected['constraint']!r}"
            )
        if (
            expected["constraint_source"] is not None
            and found.get("constraint_source") != expected["constraint_source"]
        ):
            # This one is not pedantry. `parsed` is a WEAKENED diagnosis and the payload says so;
            # a run that reported `reported` where the platform can only parse would be claiming a
            # stronger provenance than the driver can supply.
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): constraint_source is "
                f"{found.get('constraint_source')!r}, the contract requires "
                f"{expected['constraint_source']!r}"
            )
        if found.get("matched_expectation") is False:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): the server itself reports "
                "matched_expectation=false"
            )
        recorded.append(entry)

    # The admission beat must carry a server-computed clearance digest, or the fourth beat is a
    # claim with no exhibit.
    admit = next((b for b in beats if b.get("name") == "admit"), None)
    digest = None
    if admit is not None:
        record = (admit.get("observed") or {}).get("merge_record") or {}
        digest = record.get("clearance_digest")
        if not digest:
            failures.append(
                "the admission beat carries no clearance_digest: an ADMITTED with no "
                "server-computed exhibit is an assertion, not evidence"
            )
    return recorded, failures


def phase2(  # noqa: PLR0912, PLR0915 - one branch per assertion, and the assertions ARE the
    # contract. Collapsing them into a loop over a table would make every failure message
    # generic, and the message is what tells an operator which of the four beats moved.
    args: argparse.Namespace,
    base: str,
) -> tuple[dict[str, Any], list[str]]:
    """The live stack: console, health, and two gate runs."""
    failures: list[str] = []
    advisories: list[str] = []
    evidence: dict[str, Any] = {"checks": {}, "advisories": advisories}

    # ── 1. the console ───────────────────────────────────────────────────────────────────
    console = fetch(base, timeout=args.timeout, insecure=args.insecure)
    evidence["checks"]["console"] = console.summary()

    # WHO ANSWERED. Declared before any assertion, because a PROVEN verdict against the local
    # emulator and a PROVEN verdict against a deployed Function URL are different claims and
    # only one of them can go in the submission form.
    emulator = console.headers.get(EMULATOR_HEADER)
    evidence["target_is_local_emulator"] = bool(emulator)
    # Every `x-mainline-*` header the target volunteered, recorded verbatim. It is the one piece
    # of provenance a credential-free caller can actually obtain about who answered, and copying
    # it costs nothing; `local_furl` uses this space to name its own file.
    evidence["checks"]["console"]["x_mainline_headers"] = {
        name: value
        for name, value in sorted(console.headers.items())
        if name.startswith("x-mainline-")
    }
    if emulator:
        evidence["emulator"] = emulator
        evidence["checks"]["console"][EMULATOR_HEADER] = emulator
        advisories.append(
            f"the target answered with {EMULATOR_HEADER}: {emulator}. This run was taken against "
            "scripts/deploy/local_furl.py — the REAL demo-api handler and the REAL console "
            "bundle, over a local socket, against the database named under /v1/health. It proves "
            "the handler, the site and the gate. It does NOT prove that a public demo URL "
            "exists; docs/submission/SUBMISSION.json holds UNRESOLVED until one does."
        )
    if console.status == 0:
        failures.append(f"the demo URL is not reachable at all: {console.error}")
        return evidence, failures
    if console.status != 200:
        failures.append(f"GET / returned {console.status}, expected 200")
    else:
        text = console.body.decode("utf-8", "replace").lower()
        markers = [m for m in ("<html", "<!doctype html", '<div id="root"', "<script") if m in text]
        evidence["checks"]["console"]["html_markers"] = markers
        if "<html" not in text and "<!doctype html" not in text:
            failures.append(
                "GET / did not return an HTML document; the console is not being served here"
            )

    # ── 2. health ────────────────────────────────────────────────────────────────────────
    health = fetch(urljoin(base, "/v1/health"), timeout=args.timeout, insecure=args.insecure)
    entry: dict[str, Any] = health.summary()
    evidence["checks"]["health"] = entry
    if health.status != 200:
        failures.append(f"GET /v1/health returned {health.status}, expected 200")
        try:
            entry["body"] = health.json()
        except Exception:  # noqa: BLE001
            entry["body"] = health.body[:400].decode("utf-8", "replace")
    else:
        try:
            body = health.json()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"GET /v1/health did not return JSON: {exc}")
        else:
            # The cluster's own word about itself, recorded so a judge can compare it with what
            # the submission claims.
            entry["cluster_version"] = body.get("cluster_version")
            entry["database"] = body.get("database")
            entry["schema_fingerprint"] = body.get("schema_fingerprint")
            entry["migrations_applied"] = body.get("migrations_applied")
            entry["server_date"] = body.get("server_date")
            entry["ok"] = body.get("ok")
            if not body.get("ok"):
                failures.append(
                    f"/v1/health reports ok=false: {body.get('reason')} — {body.get('detail')}"
                )
            if not body.get("schema_fingerprint"):
                failures.append(
                    "/v1/health carries no schema_fingerprint, so the cluster serving this demo "
                    "cannot be tied to the evidence bundle"
                )
            # AN ADVISORY, NOT A FAILURE, AND IT NOW SAYS WHAT THE FIELD MEANS RATHER THAN ONLY
            # THAT IT IS UNTRUSTWORTHY. The zero is not a reporting bug in `health.py`: the field
            # is exactly what it claims, a count of ONE table, and that table belongs to an
            # applier which did not build this database. Two appliers, two ledgers:
            #
            #   `trappoint migrate up`               -> writes trappoint.schema_migration
            #     (packages/trappoint-migrate/src/trappoint_migrate/runner.py:295, the ONLY
            #      INSERT into that table anywhere in the tree)
            #   `scripts/deploy/cloud_chain.py`      -> runs `trappoint migrate bootstrap` (which
            #     writes trappoint.schema_attestation, hence a non-null schema_fingerprint),
            #     executes the 271 files itself, and records ONE marker row in
            #     trappoint.deploy_chain carrying applied/failed/files.
            #
            # `cloud_chain.py` is what built `mainline_demo` and what builds every scratch
            # database, so schema_migration is empty BY CONSTRUCTION and 0 is the honest count of
            # it. Failing the deploy over it would be wrong; letting a judge read it as "no
            # migrations ran" would be worse.
            if body.get("migrations_applied") == 0:
                advisories.append(
                    "/v1/health reports migrations_applied=0, and that is a true count of the "
                    "wrong ledger rather than a broken deployment. health.py's statement counts "
                    "trappoint.schema_migration WHERE state='applied'; the only writer of that "
                    "table in the tree is trappoint_migrate/runner.py:295, i.e. `trappoint "
                    "migrate up`. This database was built by scripts/deploy/cloud_chain.py, "
                    "which bootstraps the attestation ledger (hence the non-null "
                    "schema_fingerprint above) and then applies the 271 files itself, recording "
                    "its count in trappoint.deploy_chain instead. So schema_migration is empty by "
                    "construction, 0 is honest about it, and the chain really is applied — the "
                    "schema_fingerprint above is the identifier that moves when the schema does. "
                    "Two appliers, two ledgers, and /v1/health reads only one of them."
                )

    # ── 3. the permit, BEFORE anything is driven ─────────────────────────────────────────
    # Only when a permit id was supplied. Without one the "before" comes from run 1's own
    # `subject` block, which the server reads in a single statement before the first beat — see
    # `permit_snapshot_from_subject`. Both provenances are recorded by name.
    snapshots: list[dict[str, Any]] = []
    permit_id: str | None = args.permit_id or None
    if permit_id:
        pre = fetch(
            urljoin(base, f"/v1/permits/{permit_id}"), timeout=args.timeout, insecure=args.insecure
        )
        if pre.status == 200:
            try:
                snapshots.append(
                    {
                        "when": "before_run_1",
                        "source": f"GET /v1/permits/{permit_id}",
                        **permit_snapshot_from_read(pre.json()),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"GET /v1/permits/{permit_id} did not return JSON: {exc}")
        else:
            failures.append(
                f"GET /v1/permits/{permit_id} returned {pre.status}, expected 200"
                f"{describe_error_body(pre)}"
            )

    # ── 4 and 5. the gate, twice, with the permit re-read after each ─────────────────────
    runs: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    digests: list[str | None] = []
    observed: list[dict[str, Any]] = []
    for index in range(1, GATE_RUNS + 1):
        response = fetch(
            urljoin(base, "/v1/demo/gate-run"),
            method="POST",
            payload={},
            timeout=args.timeout,
            insecure=args.insecure,
        )
        record: dict[str, Any] = {"run": index, **response.summary()}

        # `data` stays None for every outcome from which nothing can be concluded about the four
        # beats: a non-200, a body that is not JSON, or a 40001 retry. It is a FLAG rather than a
        # `continue` on purpose — the after-reading below must happen in all four cases, and a
        # `continue` is what stopped it happening on 2026-08-11.
        data: dict[str, Any] | None = None
        if response.status != 200:
            record["body"] = response.body[:600].decode("utf-8", "replace")
            failures.append(
                f"POST /v1/demo/gate-run (run {index}) returned {response.status}, expected 200"
                f"{describe_error_body(response)}"
            )
        else:
            try:
                envelope = response.json()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"gate-run {index} did not return JSON: {exc}")
            else:
                # The API answers with the full envelope; `data` is the gate run itself.
                candidate = envelope.get("data", envelope)
                record["envelope_version"] = envelope.get("envelope_version")
                record["staged"] = envelope.get("staged")
                record["verdict"] = candidate.get("verdict")
                record["persisted"] = candidate.get("persisted")
                record["outcome"] = candidate.get("outcome")
                if candidate.get("outcome") == "retry":
                    # 40001. An undecided transaction has no reason set and is not a refusal; the
                    # contract is explicit that this is a 503 and carries no refusal payload. Say
                    # so rather than reporting it as a gate failure.
                    failures.append(
                        f"gate-run {index} came back outcome=retry (40001): the transaction was "
                        "undecided, so nothing was proven or disproven. Re-run."
                    )
                else:
                    data = candidate

        if data is not None:
            beats, beat_failures = check_beats(data)
            record["beats"] = beats
            failures.extend(f"run {index}: {f}" for f in beat_failures)

            if data.get("persisted") is not False:
                failures.append(
                    f"run {index}: persisted is {data.get('persisted')!r}, and the demo's whole "
                    "concurrency story requires false"
                )
            persistence = data.get("persistence_check") or {}
            record["persistence_identical"] = persistence.get("identical")
            record["persistence_tables"] = len(persistence.get("tables") or [])
            if persistence.get("identical") is not True:
                failures.append(
                    f"run {index}: persistence_check.identical is "
                    f"{persistence.get('identical')!r}. A persisted=false beside a non-identical "
                    "row-count check is the server contradicting itself."
                )
            if data.get("verdict") != "PROVEN":
                failures.append(
                    f"run {index}: the server's own verdict is {data.get('verdict')!r} — "
                    f"{data.get('failures')}"
                )
            transaction = data.get("transaction") or {}
            record["single_transaction"] = transaction.get("single_transaction")
            if transaction.get("single_transaction") is not True:
                failures.append(
                    f"run {index}: transaction.single_transaction is not true, so the four beats "
                    "did not share one transaction and the rollback proves nothing about all of "
                    "them"
                )

            admit = next((b for b in data.get("beats", []) if b.get("name") == "admit"), None)
            merge_record = ((admit or {}).get("observed") or {}).get("merge_record") or {}
            digests.append(merge_record.get("clearance_digest"))
            projections.append(stable_projection(data))

            # THE FOUR SQLSTATES, VERBATIM, flattened so a reader — or a grep — finds them without
            # walking the envelope. Nothing here is composed: every value is the driver's.
            for beat in beats:
                if beat.get("present"):
                    observed.append(
                        {
                            "run": index,
                            "ordinal": beat.get("ordinal"),
                            "name": beat.get("name"),
                            "outcome": beat.get("outcome"),
                            "sqlstate": beat.get("sqlstate"),
                            "constraint": beat.get("constraint"),
                            "constraint_source": beat.get("constraint_source"),
                        }
                    )

            subject = data.get("subject") or {}
            if index == 1 and not snapshots and subject:
                snapshots.append(
                    {
                        "when": "before_run_1",
                        "source": (
                            "run 1's own subject block, read by the server in one statement "
                            "before the first beat"
                        ),
                        **permit_snapshot_from_subject(subject),
                    }
                )
            if permit_id is None:
                permit_id = subject.get("subject_id")

        # ── the after-reading, TAKEN WHATEVER THE RUN DID ────────────────────────────────
        # A DIFFERENT endpoint, in a DIFFERENT transaction. This is the part the server cannot
        # fake by setting a flag in its own payload, and it is exactly as informative after a
        # run that errored as after one that passed: a request that died between its third beat
        # and its rollback would leave the permit changed, and only this reading would say so.
        if permit_id:
            after = fetch(
                urljoin(base, f"/v1/permits/{permit_id}"),
                timeout=args.timeout,
                insecure=args.insecure,
            )
            record["permit_reread_status"] = after.status
            if after.status == 200:
                try:
                    snapshots.append(
                        {
                            "when": f"after_run_{index}",
                            "source": f"GET /v1/permits/{permit_id}",
                            "taken_after": (
                                "a gate run that answered 200"
                                if data is not None
                                else f"a gate run that answered {response.status} and was not "
                                "analysable; the reading was taken anyway"
                            ),
                            **permit_snapshot_from_read(after.json()),
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"GET /v1/permits/{permit_id} did not return JSON: {exc}")
            else:
                failures.append(
                    f"GET /v1/permits/{permit_id} after run {index} returned {after.status}, "
                    f"expected 200{describe_error_body(after)}"
                )
        else:
            record["permit_reread_status"] = None
            failures.append(
                f"after run {index} no permit id was known — neither --permit-id nor a subject "
                "block from a successful run — so no after-reading could be taken and the "
                "rollback claim cannot be checked from outside for this run"
            )
        runs.append(record)

    evidence["checks"]["gate_runs"] = runs
    evidence["observed_sqlstates"] = observed

    # ── the concurrency claim ────────────────────────────────────────────────────────────
    if len(projections) == 2:
        identical = projections[0] == projections[1]
        evidence["checks"]["repeatability"] = {
            "compared": "stable projection of the two runs",
            "identical": identical,
            "volatile_fields_excluded": list(VOLATILE_FIELDS),
            "clearance_digest_run_1": digests[0] if digests else None,
            "clearance_digest_run_2": digests[1] if len(digests) > 1 else None,
            "clearance_digest_stable": (digests[0] == digests[1] if len(digests) == 2 else None),
            "note": (
                "The digest is OBSERVED, not asserted: it is computed over the sorted "
                "(check_id, disposition_id) set and the disposition is inserted fresh inside "
                "each run, so two runs may legitimately differ. A difference here is not a "
                "failure; a difference in the stable projection is."
            ),
        }
        if not identical:
            first, second = projections
            differing = [k for k in first if first[k] != second.get(k)]
            failures.append(
                "the two gate runs did not agree on their stable projection "
                f"(fields: {differing}). The demo is then NOT safe for concurrent judges."
            )
    elif len(projections) < 2:
        failures.append(
            "fewer than two gate runs completed, so repeatability — the property that makes "
            "this demo safe for concurrent judges — was NOT established"
        )

    # ── the rollback claim, checked from outside ─────────────────────────────────────────
    invariant: dict[str, Any] = {
        "fields": list(PERMIT_INVARIANT_FIELDS),
        "permit_id": permit_id,
        "snapshots": snapshots,
        "why": (
            "the four beats run inside ONE transaction that is rolled back. If that is true, the "
            "committed permit is unchanged afterwards, and open_blocking in particular is still 1 "
            "rather than the 0 the signed disposition would leave behind."
        ),
    }
    # BY NAME, NOT BY POSITION. `snapshots[0]` vs `snapshots[-1]` was satisfied by any two
    # readings at all — including before_run_1 against after_run_1, which leaves the second run
    # unbracketed while the check still reports `unchanged: true`.
    before = next((s for s in snapshots if s.get("when") == "before_run_1"), None)
    final_when = f"after_run_{GATE_RUNS}"
    final = next((s for s in snapshots if s.get("when") == final_when), None)
    invariant["required_snapshots"] = ["before_run_1", final_when]
    invariant["snapshots_taken"] = [s.get("when") for s in snapshots]

    if before is None or final is None:
        invariant["unchanged"] = None
        invariant["bracketed"] = False
        missing = [
            name for name, snap in (("before_run_1", before), (final_when, final)) if snap is None
        ]
        failures.append(
            f"the seeded permit was not read both before and after the gate runs — {missing} "
            f"missing, taken {invariant['snapshots_taken']}. The claim that nothing persists was "
            "NOT established from outside; only the server's own persisted flag was available, "
            "and that is the claim under test."
        )
    else:
        invariant["bracketed"] = True
        invariant["compared"] = f"before_run_1 vs {final_when}"
        # EVERY reading is compared with the before, not merely the last one. A permit that moved
        # during run 1 and moved back during run 2 satisfies a first-versus-last comparison and is
        # still a demo that changes state under a judge.
        comparisons: list[dict[str, Any]] = []
        moved_any: list[str] = []
        for snapshot in snapshots:
            if snapshot is before:
                continue
            moved = [f for f in PERMIT_INVARIANT_FIELDS if before.get(f) != snapshot.get(f)]
            comparisons.append(
                {
                    "against": "before_run_1",
                    "reading": snapshot.get("when"),
                    "moved_fields": moved,
                    "identical": not moved,
                }
            )
            for field in moved:
                moved_any.append(field)
                failures.append(
                    f"the seeded permit's {field} moved from {before.get(field)!r} "
                    f"(before_run_1) to {snapshot.get(field)!r} ({snapshot.get('when')}). The "
                    "gate run's transaction did NOT roll back, so the demo changes state under a "
                    "judge and the next one sees a different permit."
                )
        invariant["comparisons"] = comparisons
        invariant["moved_fields"] = sorted(set(moved_any))
        invariant["unchanged"] = not moved_any

    ids = {s.get("permit_id") for s in snapshots if s.get("permit_id")}
    invariant["subjects_read"] = sorted(ids)
    if len(ids) > 1:
        invariant["unchanged"] = False
        failures.append(
            f"the permit snapshots do not all describe one subject: {sorted(ids)}. Nothing can "
            "be concluded about persistence from readings of different rows."
        )
    evidence["checks"]["permit_invariant"] = invariant
    return evidence, failures


def phase1(args: argparse.Namespace, base: str) -> tuple[dict[str, Any], list[str]]:
    """The static path: the console, and every bundle file re-hashed from outside."""
    failures: list[str] = []
    evidence: dict[str, Any] = {"checks": {}}

    console = fetch(base, timeout=args.timeout, insecure=args.insecure)
    evidence["checks"]["console"] = console.summary()
    evidence["target_is_local_emulator"] = bool(console.headers.get(EMULATOR_HEADER))
    if console.status == 0:
        failures.append(f"the demo URL is not reachable at all: {console.error}")
        return evidence, failures
    if console.status != 200:
        failures.append(f"GET / returned {console.status}, expected 200")
    elif b"<html" not in console.body.lower() and b"<!doctype html" not in console.body.lower():
        failures.append("GET / did not return an HTML document")

    manifest_url = urljoin(base, args.bundle_path.lstrip("/"))
    manifest_response = fetch(manifest_url, timeout=args.timeout, insecure=args.insecure)
    evidence["checks"]["manifest"] = manifest_response.summary()
    if manifest_response.status != 200:
        failures.append(
            f"the bundle manifest at {manifest_url} returned {manifest_response.status}; "
            "phase 1 has nothing to verify without it"
        )
        return evidence, failures
    try:
        manifest = manifest_response.json()
    except Exception as exc:  # noqa: BLE001
        failures.append(f"the bundle manifest is not JSON: {exc}")
        return evidence, failures

    evidence["checks"]["manifest"]["bundle_id"] = manifest.get("bundle_id")
    evidence["checks"]["manifest"]["captured_at"] = manifest.get("captured_at")
    evidence["checks"]["manifest"]["cluster_fingerprint"] = manifest.get("cluster_fingerprint")
    evidence["checks"]["manifest"]["staged"] = manifest.get("staged")

    files = manifest.get("files") or []
    base_dir = manifest_url.rsplit("/", 1)[0] + "/"
    verified: list[dict[str, Any]] = []
    limit = args.bundle_limit if args.bundle_limit > 0 else len(files)

    # RE-HASHED FROM OUTSIDE, over the same CDN a judge uses. Verifying the manifest against
    # itself would prove nothing; verifying the bytes CloudFront actually served is the claim.
    for descriptor in files[:limit]:
        url = urljoin(base_dir, descriptor["path"])
        got = fetch(url, timeout=args.timeout, insecure=args.insecure)
        digest = hashlib.sha256(got.body).hexdigest()
        agreed = got.status == 200 and digest == descriptor.get("sha256")
        verified.append(
            {
                "path": descriptor["path"],
                "status": got.status,
                "ms": got.elapsed_ms,
                "bytes": len(got.body),
                "expected_sha256": descriptor.get("sha256"),
                "observed_sha256": digest,
                "agreed": agreed,
            }
        )
        if not agreed:
            failures.append(
                f"bundle file {descriptor['path']}: status {got.status}, sha256 "
                f"{digest[:16]}… does not match the manifest's "
                f"{str(descriptor.get('sha256'))[:16]}…"
            )
    evidence["checks"]["bundle"] = {
        "files_in_manifest": len(files),
        "files_verified": len(verified),
        "all_agreed": all(v["agreed"] for v in verified) if verified else False,
        "results": verified,
    }
    if not verified:
        failures.append("the bundle manifest lists no files, so nothing was verified")
    return evidence, failures


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915 - argument parsing,
    # two transcript shapes and the evidence writer. Splitting it would move the transcript
    # away from the verdict it describes.
    parser = argparse.ArgumentParser(
        prog="demo_acceptance",
        description=(
            "Prove from outside, with no credentials, that the deployed demo loads, reports its "
            "cluster, and drives the gate through refusal and admission without persisting."
        ),
    )
    # TWO SPELLINGS OF ONE ARGUMENT, AND THAT IS DELIBERATE. The positional is what
    # `deploy.sh` has always passed. `--url` is what CI, the health lane and the orchestrator's
    # post-apply run pass, so the same program is pointed at the local emulator today and at
    # `https://<id>.lambda-url.ap-southeast-1.on.aws` after the apply WITH NO CODE CHANGE — the
    # target is an argument, never a constant in this file.
    parser.add_argument(
        "url",
        nargs="?",
        default=None,
        help="the demo URL, e.g. https://<id>.lambda-url.ap-southeast-1.on.aws",
    )
    parser.add_argument(
        "--url",
        dest="url_flag",
        default=None,
        help="the same value as the positional argument; use whichever reads better",
    )
    parser.add_argument(
        "--permit-id",
        default="",
        help=(
            "read GET /v1/permits/<id> BEFORE the first gate run as well as after each one. "
            "Without it the 'before' reading comes from run 1's own subject block."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--phase1",
        action="store_true",
        help="static console + cryptographically verified EvidenceBundle, no backend",
    )
    mode.add_argument(
        "--phase2", action="store_true", help="the live stack (default): health + gate-run"
    )
    parser.add_argument("--out", default="evidence/deploy/acceptance.json")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="skip TLS verification (a local shim or a self-signed staging host); recorded",
    )
    parser.add_argument(
        "--bundle-path",
        # `console/src/app/composition.tsx` resolves `./bundle/` against the document, and
        # `static_site.ASSET_PREFIXES` serves `/bundle/` as files rather than as SPA routes. So
        # the deployed manifest is at `/bundle/manifest.json`, not under `fixtures/`, which was
        # the repository path the console builds FROM.
        default="bundle/manifest.json",
        help="path to the EvidenceBundle manifest, relative to the demo URL (phase 1)",
    )
    parser.add_argument(
        "--bundle-limit",
        type=int,
        default=0,
        help="verify at most N bundle files; 0 means all of them (phase 1)",
    )
    parser.add_argument(
        "--note", default="", help="a sentence recorded verbatim in the evidence file"
    )
    parser.add_argument(
        "--corroborate",
        default="",
        help=(
            "embed a previously written acceptance file under `corroborating_run`. Used when "
            "THIS run is red for a reason outside the gate — a missing route, an unseeded "
            "subject — and a second run established that the gate itself behaves. The embedded "
            "run keeps its own verdict and its own note; it never changes this run's verdict."
        ),
    )
    args = parser.parse_args(argv)

    if args.url and args.url_flag and args.url != args.url_flag:
        print(
            f"demo_acceptance: two different URLs were given, {args.url!r} positionally and "
            f"{args.url_flag!r} with --url. Refusing to guess which one the evidence should name.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    args.url = args.url_flag or args.url
    if not args.url:
        print(
            "demo_acceptance: no URL. Pass one positionally or with --url. There is no default: "
            "a prover with a built-in target proves something about the target it remembered.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    scheme = urlsplit(args.url).scheme
    if scheme not in ("http", "https"):
        print(f"demo_acceptance: {args.url!r} is not an http(s) URL", file=sys.stderr)
        return EXIT_USAGE
    base = args.url if args.url.endswith("/") else args.url + "/"
    mode_name = "phase1" if args.phase1 else "phase2"

    started = time.monotonic()
    # THE MODE IS THE FIRST THING PRINTED. A green run against the wrong mode certifies a claim
    # nobody made.
    shape = "static bundle, no backend" if args.phase1 else "live stack"
    print(f"MODE          {mode_name}  ({shape})")
    print(f"URL           {args.url}")
    if args.insecure:
        print("TLS           NOT VERIFIED (--insecure)")

    runner = phase1 if args.phase1 else phase2
    evidence, failures = runner(args, base)

    total_ms = round((time.monotonic() - started) * 1000, 1)
    reachable = evidence["checks"].get("console", {}).get("status", 0) != 0
    verdict = "PROVEN" if not failures else "NOT PROVEN"

    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "mode": mode_name,
        "mode_description": (
            "static console over a cryptographically verified EvidenceBundle, no backend in the "
            "request path"
            if args.phase1
            else "the live stack: console, /v1/health, and two /v1/demo/gate-run calls against "
            "CockroachDB Cloud"
        ),
        "url": args.url,
        "tls_verified": not args.insecure,
        "verdict": verdict,
        "failures": failures,
        "total_ms": total_ms,
        "reachable": reachable,
        # Always present, so "was this a deployment or an emulator?" is answered by a field
        # rather than by the absence of one. `evidence` overwrites it with the measured value.
        "target_is_local_emulator": False,
        "volatile_fields": list(VOLATILE_FIELDS),
        "permit_invariant_fields": list(PERMIT_INVARIANT_FIELDS),
        "expected_beats": list(EXPECTED_BEATS),
        **evidence,
    }
    if args.note:
        payload["note"] = args.note
    if args.corroborate:
        # The embedded run is DATA, not a verdict. It is recorded so a reader can see the
        # transcript the note refers to without taking the note's word for it, and it is placed
        # under its own key so that no reader or grep mistakes its `"verdict": "PROVEN"` for this
        # run's. This program's own verdict is computed above and is never touched here.
        source = Path(args.corroborate)
        try:
            payload["corroborating_run"] = json.loads(source.read_text(encoding="utf-8"))
            payload["corroborating_run"]["_embedded_from"] = str(source)
            payload["corroborating_run"]["_this_is_not_the_verdict"] = (
                "This block is a SEPARATE run, embedded for reference. The verdict of the run "
                "this file documents is the top-level `verdict` key."
            )
        except Exception as exc:  # noqa: BLE001
            payload["corroborating_run"] = {"error": f"could not read {source}: {exc}"}

    # ── the human-readable transcript ────────────────────────────────────────────────────
    if mode_name == "phase2":
        health = evidence["checks"].get("health", {})
        print(f"HEALTH        {health.get('status')} {health.get('ms')}ms")
        if health.get("cluster_version"):
            print(f"  cluster     {health['cluster_version']}")
            print(f"  database    {health.get('database')}")
            print(f"  fingerprint {str(health.get('schema_fingerprint'))[:32]}…")
            print(f"  migrations  {health.get('migrations_applied')} applied")
        for run in evidence["checks"].get("gate_runs", []):
            print(f"GATE RUN {run['run']}    HTTP {run.get('status')} {run.get('ms')}ms")
            for beat in run.get("beats", []):
                if not beat.get("present"):
                    print(f"  ABSENT      {beat['name']}")
                    continue
                source = f" ({beat['constraint_source']})" if beat.get("constraint_source") else ""
                print(
                    f"  {str(beat.get('outcome')).upper():9} [{beat.get('sqlstate')}] "
                    f"{beat.get('constraint') or '—'}{source}"
                )
            print(f"  persisted   {run.get('persisted')}  verdict {run.get('verdict')}")
        repeat = evidence["checks"].get("repeatability")
        if repeat:
            print(f"REPEATABLE    {repeat['identical']}  (stable projection of two runs)")
        invariant = evidence["checks"].get("permit_invariant")
        if invariant:
            print(
                f"UNCHANGED     {invariant.get('unchanged')}  "
                f"({invariant.get('compared', 'not compared')})"
            )
            for snapshot in invariant.get("snapshots", []):
                print(
                    f"  {snapshot['when']:14} open_blocking={snapshot.get('open_blocking')} "
                    f"state={snapshot.get('state')} gate_epoch={snapshot.get('gate_epoch')} "
                    f"head_seq={snapshot.get('head_seq')}"
                )
        if payload_target_is_emulator(evidence):
            print("TARGET        LOCAL EMULATOR (x-mainline-emulator) — not a deployed demo URL")
    else:
        bundle = evidence["checks"].get("bundle", {})
        print(
            f"BUNDLE        {bundle.get('files_verified', 0)}/{bundle.get('files_in_manifest', 0)} "
            f"files re-hashed, all agreed: {bundle.get('all_agreed')}"
        )

    print(f"VERDICT       {verdict}  ({mode_name})")
    for failure in failures:
        print(f"  ! {failure}")
    for advisory in evidence.get("advisories", []):
        print(f"  ~ ADVISORY  {advisory}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"evidence      {out}")

    if not reachable:
        return EXIT_UNREACHABLE
    return EXIT_PROVEN if verdict == "PROVEN" else EXIT_WRONG


if __name__ == "__main__":
    raise SystemExit(main())
