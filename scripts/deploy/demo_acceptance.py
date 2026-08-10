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
            # AN ADVISORY, NOT A FAILURE. `migrations_applied` counts rows in
            # `trappoint.schema_migration` whose state is 'applied'. Measured on 2026-08-10, that
            # table is EMPTY both on the local scratch database and on the live Cloud database
            # `mainline_demo` — neither `scripts/proof/gate_refusal.py` nor
            # `scripts/deploy/cloud_chain.py` writes a row into it. So a correctly deployed demo
            # will report 0 here while the submission says 271, and a judge who compares the two
            # will conclude the deployment is broken when it is the bookkeeping that is missing.
            # Failing the deploy over it would be wrong; letting it pass unremarked would be worse.
            if body.get("migrations_applied") == 0:
                advisories.append(
                    "/v1/health reports migrations_applied=0. trappoint.schema_migration is empty "
                    "on this database — the appliers do not record into it — so this number "
                    "contradicts the 271-file chain the submission describes. The schema "
                    "fingerprint above is the trustworthy identifier; this counter is not."
                )

    # ── 3 and 4. the gate, twice ─────────────────────────────────────────────────────────
    runs: list[dict[str, Any]] = []
    projections: list[dict[str, Any]] = []
    digests: list[str | None] = []
    for index in (1, 2):
        response = fetch(
            urljoin(base, "/v1/demo/gate-run"),
            method="POST",
            payload={},
            timeout=args.timeout,
            insecure=args.insecure,
        )
        record: dict[str, Any] = {"run": index, **response.summary()}
        if response.status != 200:
            record["body"] = response.body[:600].decode("utf-8", "replace")
            failures.append(
                f"POST /v1/demo/gate-run (run {index}) returned {response.status}, expected 200"
            )
            runs.append(record)
            continue
        try:
            envelope = response.json()
        except Exception as exc:  # noqa: BLE001
            failures.append(f"gate-run {index} did not return JSON: {exc}")
            runs.append(record)
            continue

        # The API answers with the full envelope; `data` is the gate run itself.
        data = envelope.get("data", envelope)
        record["envelope_version"] = envelope.get("envelope_version")
        record["staged"] = envelope.get("staged")
        record["verdict"] = data.get("verdict")
        record["persisted"] = data.get("persisted")
        record["outcome"] = data.get("outcome")

        if data.get("outcome") == "retry":
            # 40001. An undecided transaction has no reason set and is not a refusal; the
            # contract is explicit that this is a 503 and carries no refusal payload. Say so
            # rather than reporting it as a gate failure.
            failures.append(
                f"gate-run {index} came back outcome=retry (40001): the transaction was "
                "undecided, so nothing was proven or disproven. Re-run."
            )
            runs.append(record)
            continue

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
                f"run {index}: persistence_check.identical is {persistence.get('identical')!r}. "
                "A persisted=false beside a non-identical row-count check is the server "
                "contradicting itself."
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
                f"run {index}: transaction.single_transaction is not true, so the four beats did "
                "not share one transaction and the rollback proves nothing about all of them"
            )

        admit = next((b for b in data.get("beats", []) if b.get("name") == "admit"), None)
        merge_record = ((admit or {}).get("observed") or {}).get("merge_record") or {}
        digests.append(merge_record.get("clearance_digest"))
        projections.append(stable_projection(data))
        runs.append(record)

    evidence["checks"]["gate_runs"] = runs

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
    return evidence, failures


def phase1(args: argparse.Namespace, base: str) -> tuple[dict[str, Any], list[str]]:
    """The static path: the console, and every bundle file re-hashed from outside."""
    failures: list[str] = []
    evidence: dict[str, Any] = {"checks": {}}

    console = fetch(base, timeout=args.timeout, insecure=args.insecure)
    evidence["checks"]["console"] = console.summary()
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
    parser.add_argument("url", help="the public demo URL, e.g. https://dXXXXXXXX.cloudfront.net")
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
        default="fixtures/bundles/demo-cloud/manifest.json",
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
        "volatile_fields": list(VOLATILE_FIELDS),
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
