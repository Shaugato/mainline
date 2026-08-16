#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE SECOND PROOF: the clause the blame reaches cannot be quietly EDITED AWAY either.

``scripts/proof/gate_refusal.py`` proves the first half of the claim against a database
this repository builds from scratch: a permit whose merge depends on a recalled precursor
is REFUSED, and the refusal names a constraint.  A reader who follows that far asks the
obvious next question out loud —

    *"fine, so couldn't somebody just rewrite the rule?"*

This script answers it, and it answers it **against the deployed kernel over the public
internet** rather than against a database it built itself.  The seeded world already
carries the mirror case: change request ``dec0de00-000c-…`` proposes to EDIT the very
clause the permit's obligation cites, it sits in ``checks_materialised`` with
``open_blocking = 1``, and its obligation ``dec0de00-000d-…`` is severity 4 /
``blood_major`` / origin ``blame_ancestry``.  **You cannot USE a clause the blame reaches,
and you cannot EDIT AWAY the clause the blame reaches either.**

WHAT THIS SCRIPT IS, AND WHAT IT DELIBERATELY IS NOT
----------------------------------------------------
It is an HTTP client.  It opens no database connection, holds no credential, reads no
environment variable that could carry one, and never writes to AWS.  Everything it records
is a byte the live origin sent, together with the status, the length and the elapsed time
of the request that produced it.  **If the live origin is wrong, this script records that
it is wrong** — it has no path by which it could record anything else, because it has no
source of truth other than the response.

It is NOT a deployer.  It runs after the orchestrator has deployed; it never invokes
``terraform``, never writes an SSM parameter and never prints a credential.

It is NOT a mutator.  The only ``POST`` it sends to a *changing* route is one the
deployment's own ``transitions._demo_guard`` answers ``423 Locked`` on the seeded subjects,
and it records that ``423`` as the regression evidence it is.  ``POST /v1/demo/gate-run``
and ``POST /v1/demo/cr-gate-run`` both roll their transaction back by contract, which is
the property this script *checks* rather than assumes — see :func:`_assert_cr_gate_run`,
where ``persisted: false`` is only accepted when the payload also carries the two
fingerprints it was concluded from.

THE THREE FINDINGS, AND WHY THEY HAVE DIFFERENT EXIT CODES
-----------------------------------------------------------
``gate_refusal.py`` keeps *"the gate did not refuse"* apart from *"there was nothing to
ask"* because only one of them is about the product.  The same split governs here, and it
matters more, not less, because this script's subject is a route that did not exist
yesterday:

* ``0`` — **PROVEN.**  The endpoint answered, the merge beat was refused with the SQLSTATE
  and the constraint the kernel reports, the drift beat was refused by the trigger
  function, the before and after fingerprints are identical, the two logical timestamps are
  equal, and every repeat press left the change-request row byte for byte where it was.
* ``1`` — **NOT PROVEN.**  The endpoint answered and the answer does not support the claim.
  The transcript is still written, it names the failing beat, and it is still published.
  **A NOT PROVEN run is never re-run until it is green**: the whole discipline is that the
  first answer is the answer.
* ``2`` — **UNANSWERABLE.**  There was no question to ask.  The origin was unreachable, or
  ``POST /v1/demo/cr-gate-run`` is not declared by the deployment (the 404 body enumerates
  what IS declared, and that enumeration is recorded verbatim).  A route that has not been
  deployed yet is not a gate that failed to refuse, and reporting one as the other would be
  the exact fabrication this repository exists to refuse.

WHAT IT ASSERTS, AND AGAINST WHAT
----------------------------------
Every assertion below is evaluated against the **payload the origin returned**, never
against a restatement of the plan.  Each one records the JSON pointer it read, the value it
expected, the value it observed and whether it holds, so a reader can disagree with a
comparison rather than guess at one.  The pointers are RESOLVED from the payload rather
than hard-coded by index: a beat is found by its ``name``, and the change-request row inside
the persistence fingerprint is found by shape.  Where a pointer could not be resolved that
is itself a recorded failure, not a silently skipped assertion.

The two exhibits this script pins are the ones the kernel's own catalogue carries:

    ``23514``  ``cr_gate_closed_when_merged``   the CHECK on ``mainline.change_request``
    ``P0001``  ``mainline.fn_cr_merge_gate``    the trigger function behind ``cr_merge_gate``

**They are different objects and the difference is load-bearing.**  ``cr_merge_gate``
(migration 0131) is the TRIGGER; ``cr_gate_closed_when_merged`` is the CHECK.  A run that
reported the trigger's name where the driver reported the constraint's would be making a
claim the kernel does not make.

REPEATABILITY IS PART OF THE SAFETY CLAIM, NOT A NICETY
--------------------------------------------------------
The demo URL carries ``authorization_type = NONE``.  The reason that is defensible is that
the endpoint persists nothing, so fifty judges pressing it at once is fifty rolled-back
transactions.  A single green run does not demonstrate that.  ``--runs`` (default 3) presses
the button in succession and requires the change-request row read back by EVERY run to be
byte-identical to the first — compared as a SHA-256 over canonical JSON, so "identical"
means identical and not "looked the same in the summary".

REGRESSION, IN THE SAME TRANSCRIPT
-----------------------------------
A new route that broke an old one would be a worse outcome than no new route.  So the same
invocation re-drives **all eighteen pre-existing ``Route`` rows** (``app.py::_routes()`` —
seventeen paths, because ``/v1/checks/{check_id}/disposition`` is declared twice) and
re-runs ``POST /v1/demo/gate-run``, and compares both against a previously recorded drive
of the same routes stored in the transcript file.  ``--phase baseline`` records the first
drive; the default phase compares against it.  A status change, a resource-key change or a
schema-id change on any pre-existing route is a hard failure.

Usage::

    # before the orchestrator deploys — record what the surface answers today
    python scripts/proof/cr_gate_refusal.py --phase baseline

    # after the deploy — prove the refusal and diff the eighteen against the baseline
    python scripts/proof/cr_gate_refusal.py --suite-junit qa/<run>.xml

Both write ``qa/cr-gate-live.json`` (the full transcript, every verbatim body) and
``evidence/deploy/cr-gate-live.json`` (the published evidence: assertions, verdict,
regression diff, suite numbers, and the verbatim bodies the assertions were read from).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

EXIT_PROVEN = 0
EXIT_NOT_PROVEN = 1
EXIT_UNANSWERABLE = 2

# ─────────────────────────────────────────────────────────────────────────────────────
# THE ORIGIN AND THE SUBJECTS
#
# The origin is a default rather than a constant so that a reader can point this at their
# own deployment; it is NOT read from the environment, because an evidence file whose
# subject depends on an unrecorded variable is an evidence file about nothing. Whatever
# origin was driven is written into the transcript.
# ─────────────────────────────────────────────────────────────────────────────────────
LIVE_ORIGIN = "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws"

#: The seeded change request that proposes to EDIT the clause the permit's obligation
#: cites, and the obligation that is open on it. Both are `db/seeds/demo/demo_world.sql`
#: identifiers, frozen by `tests/ci/test_demo_seed_is_frozen.py`, and both are read back
#: from `GET /v1/demo/subjects` in every run so that a seed change becomes a visible
#: mismatch instead of a silent one.
CR_ID = "dec0de00-000c-4000-8000-000000000001"
CR_CHECK_ID = "dec0de00-000d-4000-8000-000000000001"

#: The permit half of the mirror — the subject `POST /v1/demo/gate-run` drives. Present
#: here only so the regression drive can fill path parameters.
PERMIT_ID = "dec0de00-0006-4000-8000-000000000001"
CHECK_ID = "dec0de00-0007-4000-8000-000000000001"
RECEIPT_ID = "dec0de00-0008-4000-8000-000000000001"
RUN_ID = "dec0de00-0009-4000-8000-000000000001"
CLAUSE_UUID = "dec0de00-0004-4000-8000-000000000001"
LESSON_ID = "dec0de00-0005-4000-8000-000000000001"
COMMIT_ID = "9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39"

#: The change-request gate's two exhibits, as the kernel names them.
#:
#: `cr_gate_closed_when_merged` is the CHECK on `mainline.change_request`; the driver
#: REPORTS it in `diag.constraint_name`, which is why `constraint_source` must read
#: `reported` and not `parsed`. `mainline.fn_cr_merge_gate` is the function behind trigger
#: `cr_merge_gate` (0131); P0001 carries no `constraint_name` (`spec/errors.md` §3.1), so
#: its exhibit is recovered from the message the raising body wrote and is therefore
#: `parsed`. A run that reported `reported` for the P0001 beat would be claiming a
#: diagnosis the driver did not give it.
CR_MERGE_SQLSTATE = "23514"
CR_MERGE_CONSTRAINT = "cr_gate_closed_when_merged"
CR_MERGE_CONSTRAINT_SOURCE = "reported"
CR_DRIFT_SQLSTATE = "P0001"
CR_DRIFT_EXHIBIT = "mainline.fn_cr_merge_gate"
CR_DRIFT_CONSTRAINT_SOURCE = "parsed"

#: The permit gate's two, restated so the regression check on `POST /v1/demo/gate-run`
#: compares against something other than itself.
PERMIT_MERGE_SQLSTATE = "23514"
PERMIT_MERGE_CONSTRAINT = "gate_closed_when_issued"
PERMIT_DRIFT_SQLSTATE = "P0001"
PERMIT_DRIFT_EXHIBIT = "mainline.fn_permit_merge_gate"

#: The projected counter the seeded change request carries, and the value it must read
#: again after the transaction rolls back. Beat 4 forces it to zero IN the transaction —
#: the database admits that write, which is the whole point of the attack — so a `1` here
#: after the run is this run's own evidence that its own write disappeared.
CR_OPEN_BLOCKING = 1

#: The endpoint under test, and the read the console probes beside it.
CR_GATE_RUN_PATH = "/v1/demo/cr-gate-run"
CR_BLOCKING_CHECKS_PATH = f"/v1/change-requests/{CR_ID}/blocking-checks"
CR_READ_PATH = f"/v1/change-requests/{CR_ID}"

# ─────────────────────────────────────────────────────────────────────────────────────
# THE EIGHTEEN PRE-EXISTING ROUTES
#
# Transcribed from `app.py::_routes()` at repo HEAD 240cff1 — the routing table as it
# stood BEFORE this wave. Seventeen distinct paths and eighteen rows, because
# `/v1/checks/{check_id}/disposition` is declared twice (GET disposition, POST
# sign_disposition) and the 404 body dedupes by path. Every worker counts ROWS.
#
# FOUR OF THE EIGHTEEN ARE DELIBERATELY NOT DRIVEN, AND THAT IS NOT A GAP IN THE SWEEP.
# `materialise_checks`, `sign_disposition`, `merge_permit` and `suspend_permit` COMMIT
# irreversibly. They are refused `423 demo_subject_write_protected` on the seeded subject
# by `transitions._demo_guard`, and `evidence/deploy/demo-guard-armed.json` is the
# measurement that armed it — but `evidence/deploy/cloud-acceptance.json` already ruled on
# what follows from that, in words this script will not overturn:
#
#     "A probe whose safety depends on a guard holding is a probe that writes on the day
#      it does not, and the row it would write closes the demo's one obligation for every
#      judge after it."
#
# The demo's single obligation is the film. A regression sweep that closed it would cost
# more than the regression it was checking for. So those four are verified DECLARED —
# their path templates are read back out of the deployment's own 404 route enumeration,
# which is the same table `_routes()` builds — and are never sent. `drive=False` records
# the decision in the transcript instead of leaving a reader to notice the absence.
#
# `expect` is the status this script requires of the ones it does drive.
# ─────────────────────────────────────────────────────────────────────────────────────
PREEXISTING_ROUTES: tuple[tuple[str, str, str, int, bool], ...] = (
    ("GET", f"/v1/permits/{PERMIT_ID}", "permit", 200, True),
    ("GET", f"/v1/permits/{PERMIT_ID}/blocking-checks", "blocking_checks", 200, True),
    ("GET", f"/v1/permits/{PERMIT_ID}/silence", "silence", 200, True),
    ("GET", f"/v1/change-requests/{CR_ID}", "change_request", 200, True),
    ("GET", f"/v1/checks/{CHECK_ID}/disposition", "disposition", 200, True),
    ("GET", f"/v1/receipts/{RECEIPT_ID}", "exposure_receipt", 200, True),
    ("GET", f"/v1/clauses/{CLAUSE_UUID}/versions/{COMMIT_ID}", "clause_version", 200, True),
    ("GET", f"/v1/clauses/{CLAUSE_UUID}/ancestry", "clause_ancestry", 200, True),
    ("GET", "/v1/ledger", "ledger", 200, True),
    ("GET", f"/v1/recall-runs/{RUN_ID}", "recall_run", 200, True),
    ("GET", f"/v1/lessons/{LESSON_ID}/propagation", "propagation", 200, True),
    ("GET", "/v1/audit", "audit", 200, True),
    ("POST", f"/v1/permits/{PERMIT_ID}/checks:materialise", "materialise_checks", 423, False),
    ("POST", f"/v1/checks/{CHECK_ID}/disposition", "sign_disposition", 423, False),
    ("POST", f"/v1/permits/{PERMIT_ID}/merge", "merge_permit", 423, False),
    ("POST", f"/v1/permits/{PERMIT_ID}/suspend", "suspend_permit", 423, False),
    ("POST", "/v1/demo/gate-run", "demo_gate_run", 200, True),
    ("GET", "/v1/demo/subjects", "demo_subjects", 200, True),
)

#: The path templates `app.py::_routes()` declares for the four that are not driven. The
#: deployment's 404 enumeration must still carry every one of them, or a route row has
#: gone missing and this script goes red without ever having sent a write.
UNDRIVEN_TEMPLATES: tuple[str, ...] = (
    "/v1/permits/{permit_id}/checks:materialise",
    "/v1/checks/{check_id}/disposition",
    "/v1/permits/{permit_id}/merge",
    "/v1/permits/{permit_id}/suspend",
)

#: Why each undriven route was not sent. Recorded in the transcript, not merely omitted.
UNDRIVEN_REASON = (
    "commits irreversibly on the seeded demo subject; refused 423 "
    "demo_subject_write_protected by transitions._demo_guard, but a probe whose safety "
    "depends on a guard holding is a probe that writes on the day it does not — the ruling "
    "in evidence/deploy/cloud-acceptance.json, which this script does not overturn. "
    "Declaration is checked instead, from the deployment's own 404 route enumeration."
)

#: How many `Route` rows the pre-existing table has. Restated as a number so that a
#: truncated tuple above becomes a failure rather than a smaller regression sweep.
PREEXISTING_ROUTE_ROWS = 18

#: The path the deployment answers with its route enumeration. `GET /v1/routes` is not a
#: route, and that is exactly why it works: the 404 body lists what IS declared.
ROUTE_TABLE_PROBE = "/v1/routes"

_USER_AGENT = "mainline-cr-gate-refusal/1.0 (+scripts/proof/cr_gate_refusal.py)"


# ═════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve()).parent
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return Path.cwd()


def canonical(payload: Any) -> bytes:
    """Sorted-key, separator-tight JSON. The only definition of 'identical' used here."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical(payload)).hexdigest()


def pointer_get(document: Any, pointer: str) -> tuple[bool, Any]:
    """Resolve an RFC 6901 JSON pointer. Returns (found, value) — never raises.

    A pointer that does not resolve is a RECORDED failure, which is why this reports
    absence rather than raising: the transcript has to be able to say "the payload did not
    carry that field", which is a different finding from "the field held the wrong value".
    """
    if pointer in {"", "/"}:
        return True, document
    node = document
    for raw in pointer.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                return False, None
            node = node[token]
        elif isinstance(node, list):
            if not token.lstrip("-").isdigit():
                return False, None
            index = int(token)
            if index < 0 or index >= len(node):
                return False, None
            node = node[index]
        else:
            return False, None
    return True, node


# ═════════════════════════════════════════════════════════════════════════════════════
# the HTTP client
# ═════════════════════════════════════════════════════════════════════════════════════


class OriginUnreachable(Exception):
    """The origin did not answer at all. NOT a refusal, and never reported as one."""


class Answer:
    """One request and the bytes it produced. Nothing here is interpreted."""

    def __init__(
        self,
        *,
        name: str,
        method: str,
        path: str,
        status: int,
        headers: dict[str, str],
        body: bytes,
        elapsed_s: float,
    ) -> None:
        self.name = name
        self.method = method
        self.path = path
        self.status = status
        self.headers = headers
        self.body = body
        self.elapsed_s = elapsed_s

    @property
    def json(self) -> Any:
        """The decoded body, or None when it is not JSON. Never raises."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def as_record(self, *, include_body: bool = True) -> dict[str, Any]:
        payload = self.json
        record: dict[str, Any] = {
            "name": self.name,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "bytes": len(self.body),
            "elapsed_s": round(self.elapsed_s, 4),
            "content_type": self.headers.get("content-type"),
            "content_encoding": self.headers.get("content-encoding"),
            "body_sha256": hashlib.sha256(self.body).hexdigest(),
            "json_parsed": payload is not None,
        }
        if include_body:
            # Verbatim. When the body is JSON it is embedded as JSON so a reader can
            # navigate it; when it is not, it is embedded as text with its encoding named.
            # In neither case is anything summarised away.
            if payload is not None:
                record["body"] = payload
            else:
                record["body_text"] = self.body.decode("utf-8", errors="replace")
        return record


class Origin:
    """A very small HTTP client. No credentials, no cookies, no redirects followed."""

    def __init__(self, base: str, *, timeout: float = 60.0) -> None:
        split = urlsplit(base)
        if split.scheme not in {"http", "https"}:
            raise ValueError(f"origin must be http(s): {base!r}")
        if split.username or split.password:
            # An origin carrying userinfo would put a credential into the transcript.
            raise ValueError("origin must not carry userinfo")
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.log: list[Answer] = []

    def request(self, name: str, method: str, path: str, *, body: bytes | None = None) -> Answer:
        url = self.base + path
        request = urllib.request.Request(url, method=method, data=body)  # noqa: S310 - scheme checked in __init__
        request.add_header("User-Agent", _USER_AGENT)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read()
                status = int(response.status)
                headers = {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx is an ANSWER. It is the answer this script most often needs — the
            # 404 whose body enumerates the declared routes, and the 423 the demo guard
            # returns — so it is recorded exactly like a 200 and never raised past here.
            raw = exc.read()
            status = int(exc.code)
            headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        except urllib.error.URLError as exc:
            raise OriginUnreachable(f"{method} {path}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise OriginUnreachable(f"{method} {path}: timed out after {self.timeout}s") from exc
        answer = Answer(
            name=name,
            method=method,
            path=path,
            status=status,
            headers=headers,
            body=raw,
            elapsed_s=time.perf_counter() - started,
        )
        self.log.append(answer)
        return answer


# ═════════════════════════════════════════════════════════════════════════════════════
# assertions
# ═════════════════════════════════════════════════════════════════════════════════════


class Assertions:
    """A list of comparisons, each carrying the pointer it read and both values.

    `holds` is computed, never passed in. Nothing here can record an assertion as held
    without the two values it was computed from being in the same record.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(
        self,
        ident: str,
        statement: str,
        *,
        pointer: str,
        expected: Any,
        observed: Any,
        found: bool = True,
    ) -> bool:
        holds = bool(found) and observed == expected
        self.rows.append(
            {
                "id": ident,
                "statement": statement,
                "pointer": pointer,
                "expected": expected,
                "observed": observed if found else None,
                "pointer_resolved": bool(found),
                "holds": holds,
            }
        )
        return holds

    def check_in(
        self,
        ident: str,
        statement: str,
        *,
        pointer: str,
        needle: str,
        haystack: Any,
        found: bool = True,
    ) -> bool:
        holds = bool(found) and isinstance(haystack, str) and needle in haystack
        self.rows.append(
            {
                "id": ident,
                "statement": statement,
                "pointer": pointer,
                "expected_substring": needle,
                "observed": haystack if found else None,
                "pointer_resolved": bool(found),
                "holds": holds,
            }
        )
        return holds

    @property
    def held(self) -> int:
        return sum(1 for row in self.rows if row["holds"])

    @property
    def failures(self) -> list[str]:
        return [f"{row['id']}: {row['statement']}" for row in self.rows if not row["holds"]]

    def as_json(self) -> dict[str, Any]:
        return {
            "total": len(self.rows),
            "held": self.held,
            "rows": self.rows,
        }


# ═════════════════════════════════════════════════════════════════════════════════════
# resolving the payload — by shape, not by index
# ═════════════════════════════════════════════════════════════════════════════════════


def find_beat(payload: Any, name: str) -> tuple[str | None, dict[str, Any] | None]:
    """Locate a beat by its `name`, returning the pointer it was found at.

    Indexing `/data/beats/2` would make this script agree with a particular ORDER rather
    than with a particular beat, and the plan leaves beat 2 conditional on a measurement.
    Finding by name means a re-ordered or dropped beat is reported as a missing beat.
    """
    ok, beats = pointer_get(payload, "/data/beats")
    if not ok or not isinstance(beats, list):
        return None, None
    for index, beat in enumerate(beats):
        if isinstance(beat, dict) and beat.get("name") == name:
            return f"/data/beats/{index}", beat
    return None, None


def find_cr_row(node: Any, base_pointer: str) -> tuple[str | None, dict[str, Any] | None]:
    """Find the change-request row inside a persistence fingerprint, by shape.

    The row is the one dict that carries BOTH `state` and `open_blocking`. Searching by
    shape rather than by an agreed key name means this script does not have to be edited
    in lockstep with the endpoint's field naming, and — more importantly — that it reports
    "no change-request row in the fingerprint" as a failure rather than reading a key that
    happens to exist and asserting nothing.
    """
    if isinstance(node, dict):
        if "state" in node and "open_blocking" in node:
            return base_pointer, node
        for key, value in sorted(node.items()):
            pointer, row = find_cr_row(value, f"{base_pointer}/{key}")
            if row is not None:
                return pointer, row
    return None, None


def find_scalar(node: Any, base_pointer: str, *needles: str) -> tuple[str | None, Any]:
    """Find the first scalar whose key path contains every needle, depth-first, sorted.

    Used for the two CR-scoped counts (`cr_event`, `merge_record`). The pointer that was
    resolved is recorded beside the value, so a reader can see WHICH field was compared.
    """
    if isinstance(node, dict):
        for key, value in sorted(node.items()):
            pointer = f"{base_pointer}/{key}"
            if not isinstance(value, (dict, list)) and all(
                needle in pointer.lower() for needle in needles
            ):
                return pointer, value
            found, result = find_scalar(value, pointer, *needles)
            if found is not None:
                return found, result
    return None, None


# ═════════════════════════════════════════════════════════════════════════════════════
# the CR gate run
# ═════════════════════════════════════════════════════════════════════════════════════


def _assert_cr_gate_run(  # noqa: PLR0915 - one assertion per line; splitting it hides the list
    payload: Any, assertions: Assertions, *, run_index: int
) -> dict[str, Any]:
    """Assert one `POST /v1/demo/cr-gate-run` payload. Returns the run's own summary."""
    prefix = f"R{run_index}"
    summary: dict[str, Any] = {"run_index": run_index}

    # ── the merge beat ────────────────────────────────────────────────────────────────
    merge_pointer, merge = find_beat(payload, "merge")
    if merge is None:
        assertions.check(
            f"{prefix}-MERGE",
            "the payload carries a beat named 'merge'",
            pointer="/data/beats[name=merge]",
            expected="present",
            observed=None,
            found=False,
        )
    else:
        assertions.check(
            f"{prefix}-A1",
            "the merge beat was REFUSED with SQLSTATE 23514",
            pointer=f"{merge_pointer}/sqlstate",
            expected=CR_MERGE_SQLSTATE,
            observed=merge.get("sqlstate"),
        )
        assertions.check(
            f"{prefix}-A2",
            "the merge beat names the CHECK cr_gate_closed_when_merged",
            pointer=f"{merge_pointer}/constraint",
            expected=CR_MERGE_CONSTRAINT,
            observed=merge.get("constraint"),
        )
        assertions.check(
            f"{prefix}-A3",
            "the constraint name was REPORTED by the driver, not parsed out of a message",
            pointer=f"{merge_pointer}/constraint_source",
            expected=CR_MERGE_CONSTRAINT_SOURCE,
            observed=merge.get("constraint_source"),
        )
        assertions.check(
            f"{prefix}-A4",
            "the merge beat's outcome is 'refused'",
            pointer=f"{merge_pointer}/outcome",
            expected="refused",
            observed=merge.get("outcome"),
        )
        assertions.check(
            f"{prefix}-A5",
            "the merge beat matched the expectation it was written against",
            pointer=f"{merge_pointer}/matched_expectation",
            expected=True,
            observed=merge.get("matched_expectation"),
        )
        summary["merge_beat"] = {
            "pointer": merge_pointer,
            "sqlstate": merge.get("sqlstate"),
            "constraint": merge.get("constraint"),
            "constraint_source": merge.get("constraint_source"),
            "message": merge.get("message"),
        }

    # ── the projection-drift beat ─────────────────────────────────────────────────────
    drift_pointer, drift = find_beat(payload, "projection_drift_attack")
    if drift is None:
        assertions.check(
            f"{prefix}-DRIFT",
            "the payload carries a beat named 'projection_drift_attack'",
            pointer="/data/beats[name=projection_drift_attack]",
            expected="present",
            observed=None,
            found=False,
        )
    else:
        assertions.check(
            f"{prefix}-A6",
            "the drift beat was REFUSED with SQLSTATE P0001",
            pointer=f"{drift_pointer}/sqlstate",
            expected=CR_DRIFT_SQLSTATE,
            observed=drift.get("sqlstate"),
        )
        assertions.check(
            f"{prefix}-A7",
            "the drift beat names mainline.fn_cr_merge_gate",
            pointer=f"{drift_pointer}/constraint",
            expected=CR_DRIFT_EXHIBIT,
            observed=drift.get("constraint"),
        )
        assertions.check(
            f"{prefix}-A8",
            "the P0001 exhibit is PARSED from the message, as spec/errors.md 3.1 requires",
            pointer=f"{drift_pointer}/constraint_source",
            expected=CR_DRIFT_CONSTRAINT_SOURCE,
            observed=drift.get("constraint_source"),
        )
        assertions.check_in(
            f"{prefix}-A9",
            "the drift message names the function that refused",
            pointer=f"{drift_pointer}/message",
            needle=CR_DRIFT_EXHIBIT,
            haystack=drift.get("message"),
        )
        assertions.check(
            f"{prefix}-A10",
            "the drift beat matched the expectation it was written against",
            pointer=f"{drift_pointer}/matched_expectation",
            expected=True,
            observed=drift.get("matched_expectation"),
        )
        summary["drift_beat"] = {
            "pointer": drift_pointer,
            "sqlstate": drift.get("sqlstate"),
            "constraint": drift.get("constraint"),
            "constraint_source": drift.get("constraint_source"),
            "message": drift.get("message"),
        }

    # ── the persistence fingerprint ───────────────────────────────────────────────────
    before_ok, before = pointer_get(payload, "/data/persistence_check/before")
    after_ok, after = pointer_get(payload, "/data/persistence_check/after")
    assertions.check(
        f"{prefix}-A11",
        "the payload carries a persistence fingerprint taken BEFORE the transaction",
        pointer="/data/persistence_check/before",
        expected=True,
        observed=before_ok,
    )
    assertions.check(
        f"{prefix}-A12",
        "the payload carries a persistence fingerprint taken AFTER the transaction",
        pointer="/data/persistence_check/after",
        expected=True,
        observed=after_ok,
    )
    if before_ok and after_ok:
        assertions.check(
            f"{prefix}-A13",
            "the before and after fingerprints are IDENTICAL (sha256 over canonical JSON)",
            pointer="/data/persistence_check/{before,after}",
            expected=digest(before),
            observed=digest(after),
        )
        summary["fingerprint"] = {"before_sha256": digest(before), "after_sha256": digest(after)}

        cr_before_ptr, cr_before = find_cr_row(before, "/data/persistence_check/before")
        cr_after_ptr, cr_after = find_cr_row(after, "/data/persistence_check/after")
        assertions.check(
            f"{prefix}-A14",
            "the fingerprint carries the change-request row itself",
            pointer=str(cr_after_ptr),
            expected=True,
            observed=cr_after is not None,
        )
        if cr_before is not None and cr_after is not None:
            assertions.check(
                f"{prefix}-A15",
                "the change-request row is byte-identical before and after",
                pointer=f"{cr_before_ptr} vs {cr_after_ptr}",
                expected=digest(cr_before),
                observed=digest(cr_after),
            )
            assertions.check(
                f"{prefix}-A16",
                "open_blocking reads 1 again after the rollback — the run's own forged 0 is gone",
                pointer=f"{cr_after_ptr}/open_blocking",
                expected=CR_OPEN_BLOCKING,
                observed=cr_after.get("open_blocking"),
            )
            assertions.check(
                f"{prefix}-A17",
                "the change request is still in checks_materialised, not merged",
                pointer=f"{cr_after_ptr}/state",
                expected="checks_materialised",
                observed=cr_after.get("state"),
            )
            summary["cr_row"] = {
                "pointer_before": cr_before_ptr,
                "pointer_after": cr_after_ptr,
                "before": cr_before,
                "after": cr_after,
                "sha256": digest(cr_after),
            }

        # BOTH needles, and the first of them is `subject_row_counts`. The CR-scoped
        # reading is the one the brief asks for — the counts WHERE cr_id = … — and
        # `merge_record` also appears in the ten unscoped whole-table counts, which a
        # single-needle search would find first and silently compare instead. The pointer
        # each assertion resolved is recorded beside it so this can be checked, not taken.
        for ident, needles, label in (
            (
                f"{prefix}-A18",
                ("subject_row_counts", "cr_event"),
                "the cr_event count for this cr_id",
            ),
            (
                f"{prefix}-A19",
                ("subject_row_counts", "merge_record"),
                "the merge_record count for this cr_id",
            ),
        ):
            ptr_before, val_before = find_scalar(before, "/data/persistence_check/before", *needles)
            ptr_after, val_after = find_scalar(after, "/data/persistence_check/after", *needles)
            assertions.check(
                ident,
                f"{label} is unchanged across the transaction",
                pointer=f"{ptr_before} vs {ptr_after}",
                expected=val_before,
                observed=val_after,
                found=ptr_before is not None and ptr_after is not None,
            )
            # Keyed by the DISTINGUISHING needle, not the first one. Both searches share
            # `subject_row_counts` as their first term, so keying on it silently collapsed
            # the cr_event reading into the merge_record one — found by dry-running this
            # function against a payload shaped like the endpoint's before the endpoint
            # existed, which is the only reason it was not found by the live run.
            summary.setdefault("cr_scoped_counts", {})[needles[-1]] = {
                "pointer_before": ptr_before,
                "pointer_after": ptr_after,
                "before": val_before,
                "after": val_after,
            }

    # ── the single-transaction witness ────────────────────────────────────────────────
    opened_ok, opened = pointer_get(payload, "/data/transaction/opened_logical_timestamp")
    closed_ok, closed = pointer_get(payload, "/data/transaction/closed_logical_timestamp")
    assertions.check(
        f"{prefix}-A20",
        "the two cluster_logical_timestamp readings are EQUAL — one transaction, not four",
        pointer="/data/transaction/{opened,closed}_logical_timestamp",
        expected=opened,
        observed=closed,
        found=opened_ok and closed_ok,
    )
    assertions.check(
        f"{prefix}-A21",
        "the transaction ran at SERIALIZABLE",
        pointer="/data/transaction/isolation",
        expected="SERIALIZABLE",
        observed=pointer_get(payload, "/data/transaction/isolation")[1],
    )
    assertions.check(
        f"{prefix}-A22",
        "the transaction was ROLLED BACK",
        pointer="/data/transaction/disposition",
        expected="rolled_back",
        observed=pointer_get(payload, "/data/transaction/disposition")[1],
    )
    summary["transaction"] = {
        "opened_logical_timestamp": opened,
        "closed_logical_timestamp": closed,
        "equal": bool(opened_ok and closed_ok and opened == closed),
    }

    # ── the two conclusions the payload draws ─────────────────────────────────────────
    assertions.check(
        f"{prefix}-A23",
        "persisted is FALSE, beside the two fingerprints it was concluded from",
        pointer="/data/persisted",
        expected=False,
        observed=pointer_get(payload, "/data/persisted")[1],
    )
    assertions.check(
        f"{prefix}-A24",
        "the run's own verdict is PROVEN",
        pointer="/data/verdict",
        expected="PROVEN",
        observed=pointer_get(payload, "/data/verdict")[1],
    )
    assertions.check(
        f"{prefix}-A25",
        "the run reports no failures of its own",
        pointer="/data/failures",
        expected=[],
        observed=pointer_get(payload, "/data/failures")[1],
    )
    summary["verdict"] = pointer_get(payload, "/data/verdict")[1]
    summary["persisted"] = pointer_get(payload, "/data/persisted")[1]
    summary["failures"] = pointer_get(payload, "/data/failures")[1]

    # ── the admission that cannot be played, declared rather than faked ───────────────
    #
    # RULING R3: `mainline.disposition` cannot be signed against the CR's obligation
    # without an exposure receipt that showed it, no such receipt exists, and minting one
    # needs an INSERT privilege `mainline_api` does not hold. So there is no admitted beat
    # here, and the payload is REQUIRED to say so in words. A missing statement is as much
    # a failure as a false one: silence about an absent beat is how a run starts looking
    # like it proved something it did not.
    absent_ok, absent_reason = pointer_get(payload, "/data/admission_absent_reason")
    proved_ok, proved_by = pointer_get(payload, "/data/admission_proved_by")
    assertions.check(
        f"{prefix}-A26",
        "there is no admission beat, and the payload says so rather than staying silent",
        pointer="/data/admission_beat + /data/admission_absent_reason",
        expected=[None, True],
        observed=[
            pointer_get(payload, "/data/admission_beat")[1],
            bool(absent_ok and absent_reason),
        ],
    )
    assertions.check(
        f"{prefix}-A27",
        "the payload points at the endpoint where the admission IS proved",
        pointer="/data/admission_proved_by",
        expected="POST /v1/demo/gate-run",
        observed=proved_by if proved_ok else None,
        found=proved_ok,
    )
    assertions.check(
        f"{prefix}-A28",
        "the endpoint's own self_persisted reading is FALSE",
        pointer="/data/persistence_check/self_persisted",
        expected=False,
        observed=pointer_get(payload, "/data/persistence_check/self_persisted")[1],
    )
    # AND NO FOURTH BEAT. R3 forbids an admission this run cannot honestly play, so a beat
    # named `admit` appearing here is the fabrication the ruling was written against — and
    # nothing above would have caught it, because every other assertion asks about the
    # beats that ARE expected. Found by dry-running a payload with one added.
    beats_ok, beats = pointer_get(payload, "/data/beats")
    beat_names = [b.get("name") for b in beats] if beats_ok and isinstance(beats, list) else []
    assertions.check(
        f"{prefix}-A29",
        "the run carries exactly its three beats, and none of them is an admission",
        pointer="/data/beats/*/name",
        expected=["read", "merge", "projection_drift_attack"],
        observed=beat_names,
    )
    summary["beat_names"] = beat_names
    summary["admission"] = {
        "absent_reason": absent_reason if absent_ok else None,
        "proved_by": proved_by if proved_ok else None,
        "declared": bool(absent_ok and absent_reason),
    }
    return summary


def drive_cr_gate_run(
    origin: Origin, runs: int, *, first: Answer | None = None
) -> tuple[list[Answer], Assertions, dict[str, Any]]:
    """Press the button `runs` times in succession and assert every press.

    `first` is the probe that established the endpoint exists. It IS a press — it ran the
    same transaction and rolled it back — so it is asserted and counted rather than thrown
    away. Discarding it would mean the transcript recorded one more press than it examined,
    and an unexamined press against a public URL is exactly the thing this script is for.
    """
    assertions = Assertions()
    answers: list[Answer] = []
    summaries: list[dict[str, Any]] = []
    for index in range(1, runs + 1):
        if index == 1 and first is not None:
            answer = first
            answer.name = "cr_gate_run_1"
        else:
            answer = origin.request(f"cr_gate_run_{index}", "POST", CR_GATE_RUN_PATH, body=b"")
        answers.append(answer)
        assertions.check(
            f"R{index}-HTTP",
            "POST /v1/demo/cr-gate-run answered 200",
            pointer="<http status>",
            expected=200,
            observed=answer.status,
        )
        payload = answer.json
        if payload is None:
            assertions.check(
                f"R{index}-JSON",
                "the response body is JSON",
                pointer="<body>",
                expected=True,
                observed=False,
            )
            continue
        summaries.append(_assert_cr_gate_run(payload, assertions, run_index=index))

    # ── repeatability: fifty judges at once ───────────────────────────────────────────
    #
    # The safety claim for an unauthenticated Function URL is that the endpoint persists
    # nothing. One green run does not show that; N presses leaving the row byte-identical
    # does. `first` is the reference, and EVERY later run is compared to it — not to its
    # own predecessor, which would let the row drift one byte per press unnoticed.
    hashes = [s.get("cr_row", {}).get("sha256") for s in summaries if s.get("cr_row")]
    repeatability: dict[str, Any] = {
        "runs": len(summaries),
        "cr_row_sha256": hashes,
        "identical_across_runs": bool(hashes) and len(set(hashes)) == 1,
    }
    if hashes:
        assertions.check(
            "REPEAT",
            f"the change-request row is byte-identical after all {len(hashes)} presses",
            pointer="/data/persistence_check/**/change_request row · sha256",
            expected=[hashes[0]] * len(hashes),
            observed=hashes,
        )
    else:
        assertions.check(
            "REPEAT",
            "at least one press produced a change-request row to compare",
            pointer="<repeatability>",
            expected=True,
            observed=False,
        )
    repeatability["runs_summary"] = summaries
    return answers, assertions, repeatability


# ═════════════════════════════════════════════════════════════════════════════════════
# regression — the eighteen, and the permit gate run
# ═════════════════════════════════════════════════════════════════════════════════════


def drive_preexisting_routes(origin: Origin) -> list[dict[str, Any]]:
    """Drive all eighteen pre-existing `Route` rows and record the shape of each answer.

    `shape` is what the regression diff compares: the status, the envelope's `resource`
    key and its `schema_id`, plus the error code when the answer is an error. Comparing
    BYTES would go red on `observed_at`, which moves every second and proves nothing;
    comparing the shape goes red exactly when a route's contract moved.
    """
    records: list[dict[str, Any]] = []
    for method, path, key, expect, drive in PREEXISTING_ROUTES:
        if not drive:
            records.append(
                {
                    "method": method,
                    "path": path,
                    "route_key": key,
                    "expected_status": expect,
                    "driven": False,
                    "why_not_driven": UNDRIVEN_REASON,
                    "status_matches_expectation": True,
                    "shape": {"declaration_checked_instead": True},
                }
            )
            continue
        body = b"" if method == "POST" else None
        answer = origin.request(f"route::{key}", method, path, body=body)
        payload = answer.json
        shape: dict[str, Any] = {
            "status": answer.status,
            "resource": None,
            "schema_id": None,
            "error_code": None,
            "envelope_version": None,
        }
        if isinstance(payload, dict):
            shape["resource"] = payload.get("resource")
            shape["schema_id"] = payload.get("schema_id")
            shape["envelope_version"] = payload.get("envelope_version")
            error = payload.get("error")
            if isinstance(error, dict):
                shape["error_code"] = error.get("code")
        records.append(
            {
                "method": method,
                "path": path,
                "route_key": key,
                "expected_status": expect,
                "driven": True,
                "status_matches_expectation": answer.status == expect,
                "shape": shape,
                "bytes": len(answer.body),
                "elapsed_s": round(answer.elapsed_s, 4),
            }
        )
    return records


def diff_routes(
    baseline: list[dict[str, Any]], current: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Compare two route drives row by row. Any difference is named, none is tolerated."""
    by_key = {(row["method"], row["path"]): row for row in baseline}
    drifted: list[dict[str, Any]] = []
    failures: list[str] = []
    for row in current:
        key = (row["method"], row["path"])
        previous = by_key.get(key)
        if previous is None:
            drifted.append({"route": f"{key[0]} {key[1]}", "finding": "absent from the baseline"})
            failures.append(f"{key[0]} {key[1]} was not in the recorded baseline")
            continue
        if previous["shape"] != row["shape"]:
            drifted.append(
                {
                    "route": f"{key[0]} {key[1]}",
                    "finding": "shape changed",
                    "baseline": previous["shape"],
                    "current": row["shape"],
                }
            )
            failures.append(f"{key[0]} {key[1]}: shape changed since the baseline")
    return drifted, failures


def assert_permit_gate_run(payload: Any, assertions: Assertions) -> dict[str, Any]:
    """The permit gate run must still answer exactly as it did before this wave."""
    summary: dict[str, Any] = {}
    assertions.check(
        "G1",
        "POST /v1/demo/gate-run still answers verdict PROVEN",
        pointer="/data/verdict",
        expected="PROVEN",
        observed=pointer_get(payload, "/data/verdict")[1],
    )
    assertions.check(
        "G2",
        "POST /v1/demo/gate-run still persists nothing",
        pointer="/data/persisted",
        expected=False,
        observed=pointer_get(payload, "/data/persisted")[1],
    )
    ok, beats = pointer_get(payload, "/data/beats")
    names = [b.get("name") for b in beats] if ok and isinstance(beats, list) else []
    assertions.check(
        "G3",
        "POST /v1/demo/gate-run still carries its four beats, in order",
        pointer="/data/beats/*/name",
        expected=["read", "merge", "projection_drift_attack", "admit"],
        observed=names,
    )
    for ident, name, sqlstate, exhibit in (
        ("G4", "merge", PERMIT_MERGE_SQLSTATE, PERMIT_MERGE_CONSTRAINT),
        ("G5", "projection_drift_attack", PERMIT_DRIFT_SQLSTATE, PERMIT_DRIFT_EXHIBIT),
    ):
        pointer, beat = find_beat(payload, name)
        assertions.check(
            ident,
            f"the permit gate's {name} beat still refuses {sqlstate} {exhibit}",
            pointer=f"{pointer}/(sqlstate,constraint)",
            expected=[sqlstate, exhibit],
            observed=[beat.get("sqlstate"), beat.get("constraint")] if beat else None,
            found=beat is not None,
        )
        if beat is not None:
            summary[name] = {"sqlstate": beat.get("sqlstate"), "constraint": beat.get("constraint")}
    assertions.check(
        "G6",
        "the permit gate's persistence fingerprint is still identical before and after",
        pointer="/data/persistence_check/identical",
        expected=True,
        observed=pointer_get(payload, "/data/persistence_check/identical")[1],
    )
    summary["verdict"] = pointer_get(payload, "/data/verdict")[1]
    summary["persisted"] = pointer_get(payload, "/data/persisted")[1]
    summary["beat_names"] = names
    return summary


# ═════════════════════════════════════════════════════════════════════════════════════
# the suite numbers — from --junitxml, never from a terminal tail
# ═════════════════════════════════════════════════════════════════════════════════════

#: `scripts/qa/regression_guard.py::SUITE_BASELINE`, restated rather than imported. An
#: import would make the two agree BY CONSTRUCTION and the comparison would assert
#: nothing — the same reason that guard restates the kernel exhibits instead of importing
#: `gate_refusal`.
SUITE_BASELINE = {"collected": 998, "passed": 997, "failed": 0, "errors": 0}


def read_junit(path: Path) -> dict[str, Any]:
    """Read collected/passed/failed/errors off the junit ROOT ELEMENT.

    Never off a terminal tail. This suite is silent for minutes at a stretch and healthy
    runs have been killed for looking hung; the XML root carries the counts whether or not
    a summary line was ever printed.
    """
    root = ElementTree.parse(path).getroot()  # noqa: S314 - our own CI artefact
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals: dict[str, Any] = {"collected": 0, "failed": 0, "errors": 0, "skipped": 0}
    failing: list[str] = []
    for suite in suites:
        totals["collected"] += int(suite.get("tests", 0))
        totals["failed"] += int(suite.get("failures", 0))
        totals["errors"] += int(suite.get("errors", 0))
        totals["skipped"] += int(suite.get("skipped", 0))
        for case in suite.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                classname = (case.get("classname") or "").replace(".", "/")
                failing.append(f"{classname}::{case.get('name')}")
    totals["passed"] = totals["collected"] - totals["failed"] - totals["errors"] - totals["skipped"]
    # NAMED, never merely counted. "four failed" is a number somebody has to go and find;
    # the node ids are what a reader acts on, and they are what makes a red measurement a
    # finding rather than a reason to omit the section.
    totals["failing_node_ids"] = sorted(failing)
    totals["at_or_above_baseline"] = (
        totals["failed"] == 0
        and totals["errors"] == 0
        and totals["collected"] >= SUITE_BASELINE["collected"]
        and totals["passed"] >= SUITE_BASELINE["passed"]
    )
    return totals


def assert_suite(totals: dict[str, Any], assertions: Assertions, *, label: str) -> None:
    """Assert the suite, and when it is red, assert that the redness is fully NAMED.

    A red suite in the middle of a wave is a finding about the wave, not a reason to leave
    the section out. What is NOT tolerated is a red measurement that does not say which
    node ids were red — that is a number with nothing behind it — or one where this
    worker's own file is among them, which would be this worker reporting somebody else's
    problem while quietly having one.
    """
    assertions.check(
        f"S-{label}-1",
        f"the {label} suite collected at least {SUITE_BASELINE['collected']}",
        pointer="<junitxml root @tests>",
        expected=True,
        observed=totals["collected"] >= SUITE_BASELINE["collected"],
    )
    if totals["at_or_above_baseline"]:
        assertions.check(
            f"S-{label}-2",
            f"the {label} suite is at or above the baseline: 0 failed, 0 errors",
            pointer="<junitxml root @failures,@errors>",
            expected=[0, 0],
            observed=[totals["failed"], totals["errors"]],
        )
        return
    assertions.check(
        f"S-{label}-3",
        f"the {label} suite is RED, and every red node id is named",
        pointer="<junitxml testcase/failure>",
        expected=totals["failed"] + totals["errors"],
        observed=len(totals["failing_node_ids"]),
    )
    mine = [n for n in totals["failing_node_ids"] if "test_cr_gate_proof" in n]
    assertions.check(
        f"S-{label}-4",
        "none of the red node ids belongs to this worker's own test file",
        pointer="<junitxml testcase/failure>",
        expected=[],
        observed=mine,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


def _load_transcript(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": "mainline.proof.cr-gate-live/1", "phases": []}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": "mainline.proof.cr-gate-live/1", "phases": []}
    if not isinstance(loaded, dict) or not isinstance(loaded.get("phases"), list):
        return {"schema": "mainline.proof.cr-gate-live/1", "phases": []}
    return loaded


def _baseline_routes(transcript: dict[str, Any]) -> list[dict[str, Any]] | None:
    for phase in transcript.get("phases", []):
        routes = phase.get("preexisting_routes")
        if isinstance(routes, list) and routes:
            return routes
    return None


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any], dict[str, Any]]:  # noqa: PLR0912, PLR0915
    origin = Origin(args.origin, timeout=args.timeout)
    assertions = Assertions()
    failures: list[str] = []
    caveats: list[str] = []

    evidence: dict[str, Any] = {
        "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
        "SPDX-License-Identifier": "CC-BY-4.0",
        "schema": "mainline.proof.cr-gate-live/1",
        "produced_by": "scripts/proof/cr_gate_refusal.py",
        "worker": "W5",
        "lead_plan": "docs/demo/cr-gate-route-plan.md",
        "produced_at_utc": _now_utc(),
        "origin": origin.base,
        "phase": args.phase,
        "one_sentence": (
            "You cannot USE a clause the blame reaches, and this is the transcript of the "
            "deployed kernel refusing to let it be EDITED AWAY either."
        ),
        "no_apply_was_run": {
            "statement": (
                "This script is an HTTP client. No terraform was executed, no AWS API was "
                "called, no SSM parameter was written, no credential was read or printed, "
                "and no database connection was opened."
            ),
            "requests_sent": "GET and POST to the public Function URL, nothing else",
        },
    }

    # ── 0 · WHICH DEPLOYMENT. A transcript that does not name the build it drove is a
    # transcript about nothing in particular. `/v1/health` carries the cluster version, the
    # database, the applied-chain count and the schema fingerprint, so a later reader can
    # tell whether the kernel that refused is the kernel they are looking at.
    health = origin.request("health", "GET", "/v1/health")
    evidence["health"] = health.as_record()
    # `/v1/health` answers a BARE object, not an envelope — no `/data` wrapper. Pointers
    # are therefore at the root, which is worth stating because every other read on this
    # origin is enveloped and a copied `/data/...` pointer resolves to nothing here.
    evidence["deployment"] = {
        key: pointer_get(health.json, f"/{key}")[1]
        for key in (
            "ok",
            "database",
            "cluster_version",
            "deploy_chain_applied",
            "deploy_chain_files",
            "schema_fingerprint",
        )
    }
    assertions.check(
        "H1",
        "the deployment reports itself healthy",
        pointer="/ok",
        expected=True,
        observed=pointer_get(health.json, "/ok")[1],
    )
    assertions.check(
        "H2",
        "the deploy chain applied every file it carries",
        pointer="/deploy_chain_applied vs /deploy_chain_files",
        expected=pointer_get(health.json, "/deploy_chain_files")[1],
        observed=pointer_get(health.json, "/deploy_chain_applied")[1],
    )

    # ── 1 · SUBJECTS. Read the seeded identifiers back rather than trusting the constants
    subjects = origin.request("demo_subjects", "GET", "/v1/demo/subjects")
    evidence["subjects"] = subjects.as_record()
    live_cr_id = pointer_get(subjects.json, "/data/cr_id")[1]
    assertions.check(
        "SUB",
        "the deployment's own /v1/demo/subjects names the change request this run drives",
        pointer="/data/cr_id",
        expected=CR_ID,
        observed=live_cr_id,
    )

    # ── 2 · THE CR READ, verbatim
    cr_read = origin.request("cr_read", "GET", CR_READ_PATH)
    evidence["cr_read"] = cr_read.as_record()
    assertions.check(
        "CR1",
        f"GET {CR_READ_PATH} answers 200",
        pointer="<http status>",
        expected=200,
        observed=cr_read.status,
    )
    assertions.check(
        "CR2",
        "the change request is in checks_materialised with one open obligation",
        pointer="/data/state + /data/counters/open_blocking",
        expected=["checks_materialised", CR_OPEN_BLOCKING],
        observed=[
            pointer_get(cr_read.json, "/data/state")[1],
            pointer_get(cr_read.json, "/data/counters/open_blocking")[1],
        ],
    )
    # The CHECK the refusal will name, read out of `pg_constraint` by a DIFFERENT route.
    # Two independent readings of the same catalogue object is what makes the exhibit a
    # measurement rather than a string this script happens to carry.
    ok, constraints = pointer_get(cr_read.json, "/data/constraints")
    names = (
        [c.get("constraint") for c in constraints] if ok and isinstance(constraints, list) else []
    )
    assertions.check(
        "CR3",
        "the CR read already names the CHECK the merge beat will be refused by",
        pointer="/data/constraints/*/constraint",
        expected=True,
        observed=CR_MERGE_CONSTRAINT in names,
    )
    evidence["cr_read_constraints"] = names

    # ── 3 · THE CR BLOCKING-CHECKS READ, verbatim
    cr_checks = origin.request("cr_blocking_checks", "GET", CR_BLOCKING_CHECKS_PATH)
    evidence["cr_blocking_checks"] = cr_checks.as_record()
    cr_checks_declared = cr_checks.status != 404

    # ── 4 · THE ENDPOINT. Is there a question to ask at all?
    probe = origin.request("cr_gate_run_probe", "POST", CR_GATE_RUN_PATH, body=b"")
    evidence["cr_gate_run_probe"] = probe.as_record()
    endpoint_declared = probe.status != 404

    if not endpoint_declared:
        # UNANSWERABLE, and said in exactly those words. The 404 body enumerates what the
        # deployment DOES declare, and that enumeration is the evidence for the finding.
        declared = pointer_get(probe.json, "/error/declared")[1]
        evidence["status"] = "UNANSWERABLE"
        evidence["verdict"] = "UNANSWERABLE"
        evidence["why_unanswerable"] = {
            "finding": (
                f"POST {CR_GATE_RUN_PATH} is not declared by the deployment at "
                f"{origin.base}. The origin answered 404 and its body enumerates the "
                f"routes that ARE declared."
            ),
            "declared_paths": declared,
            "declared_path_count": len(declared) if isinstance(declared, list) else None,
            "cr_blocking_checks_declared": cr_checks_declared,
            "this_is_not_a_gate_that_failed_to_refuse": (
                "A route that has not been deployed is not a refusal that did not happen. "
                "Exit code 2, the same code gate_refusal.py uses for 'there was no cluster', "
                "keeps the two findings apart."
            ),
            "what_closes_it": (
                "The orchestrator deploys, then ONE command re-drives everything and "
                "rewrites both files in place: "
                "`python scripts/proof/cr_gate_refusal.py --suite-junit <run>.xml`. "
                "Exit 0 is PROVEN, 1 is NOT PROVEN with the failing beat named, 2 is this "
                "same finding again. tests/deploy/test_cr_gate_proof.py then asserts over "
                "the rewritten file with no network."
            ),
        }
    else:
        assertions.check(
            "EP",
            f"POST {CR_GATE_RUN_PATH} is declared by the deployment",
            pointer="<http status>",
            expected=True,
            observed=probe.status != 404,
        )
        assertions.check(
            "EP2",
            f"GET {CR_BLOCKING_CHECKS_PATH} is declared by the deployment",
            pointer="<http status>",
            expected=True,
            observed=cr_checks_declared,
        )

    # ── 4b · THE OBLIGATION ITSELF, when the list route is there to answer for it
    #
    # This is the read the film puts on screen beside the permit's, and the two have to be
    # the SAME SHAPE for the mirror to mean anything — `subject_kind` naming the change
    # request rather than a permit, and the obligation carrying the same severity, the same
    # virulence and the same origin as the one the permit's gate refused on. If those three
    # differ, the second use case is a different story wearing the first one's clothes.
    if cr_checks_declared and cr_checks.status == 200:
        checks_ok, checks = pointer_get(cr_checks.json, "/data/checks")
        obligation = next(
            (
                row
                for row in (checks if checks_ok and isinstance(checks, list) else [])
                if isinstance(row, dict) and row.get("check_id") == CR_CHECK_ID
            ),
            None,
        )
        assertions.check(
            "CC1",
            "the CR blocking-checks read names the change request as its subject",
            pointer="/data/(subject_kind,subject_id)",
            expected=["change_request", CR_ID],
            observed=[
                pointer_get(cr_checks.json, "/data/subject_kind")[1],
                pointer_get(cr_checks.json, "/data/subject_id")[1],
            ],
        )
        assertions.check(
            "CC2",
            "the CR's own obligation is in the list",
            pointer=f"/data/checks[check_id={CR_CHECK_ID}]",
            expected=True,
            observed=obligation is not None,
        )
        if obligation is not None:
            assertions.check(
                "CC3",
                "it is severity 4 / blood_major / blame_ancestry, and still open",
                pointer="/data/checks/*/(severity,virulence,origin,open)",
                expected=[4, "blood_major", "blame_ancestry", True],
                observed=[
                    obligation.get("severity"),
                    obligation.get("virulence"),
                    obligation.get("origin"),
                    obligation.get("open"),
                ],
            )
            assertions.check(
                "CC4",
                "no disposition has been signed against it",
                pointer="/data/checks/*/disposition_id",
                expected=None,
                observed=obligation.get("disposition_id"),
            )
            evidence["cr_obligation"] = obligation

    # ── 5 · THE PROOF ITSELF, when there is something to ask
    if endpoint_declared:
        answers, cr_assertions, repeatability = drive_cr_gate_run(origin, args.runs, first=probe)
        assertions.rows.extend(cr_assertions.rows)
        evidence["cr_gate_runs"] = [a.as_record() for a in answers]
        evidence["repeatability"] = repeatability
        # The probe was the first press, so its own record is not repeated beside them.
        evidence.pop("cr_gate_run_probe", None)

    # ── 6 · REGRESSION: the eighteen pre-existing routes
    #
    # The deployment's own route enumeration first. `GET /v1/routes` is deliberately not a
    # route; the 404 it answers lists every path template that IS declared, which is how
    # the four committing POSTs are checked without being sent.
    route_table = origin.request("route_table", "GET", ROUTE_TABLE_PROBE)
    evidence["route_table"] = route_table.as_record()
    declared_paths = pointer_get(route_table.json, "/error/declared")[1]
    declared_set = set(declared_paths) if isinstance(declared_paths, list) else set()
    missing_templates = [t for t in UNDRIVEN_TEMPLATES if t not in declared_set]
    assertions.check(
        "RR-DECL",
        "the four committing routes this script will not send are still DECLARED",
        pointer="/error/declared",
        expected=[],
        observed=missing_templates,
    )

    routes = drive_preexisting_routes(origin)
    evidence["preexisting_routes"] = routes
    evidence["undriven_routes"] = {
        "count": sum(1 for r in routes if not r["driven"]),
        "templates": list(UNDRIVEN_TEMPLATES),
        "why": UNDRIVEN_REASON,
        "declared_by_the_origin": [t for t in UNDRIVEN_TEMPLATES if t in declared_set],
    }
    assertions.check(
        "RR0",
        "all eighteen pre-existing Route rows were accounted for",
        pointer="<route sweep>",
        expected=PREEXISTING_ROUTE_ROWS,
        observed=len(routes),
    )
    assertions.check(
        "RR0b",
        "fourteen of the eighteen were driven; the four that commit were not sent",
        pointer="<route sweep>",
        expected=[14, 4],
        observed=[
            sum(1 for r in routes if r["driven"]),
            sum(1 for r in routes if not r["driven"]),
        ],
    )
    off_expectation = [
        f"{r['method']} {r['path']} -> {r['shape']['status']} (expected {r['expected_status']})"
        for r in routes
        if not r["status_matches_expectation"]
    ]
    assertions.check(
        "RR1",
        "every pre-existing route answered the status it answered before this wave",
        pointer="<route sweep>",
        expected=[],
        observed=off_expectation,
    )

    transcript = _load_transcript(args.transcript)
    baseline = _baseline_routes(transcript)
    if baseline is None:
        caveats.append(
            "no recorded route baseline in the transcript — this run IS the baseline, so "
            "the eighteen were compared against the statuses app.py::_routes() declares "
            "rather than against an earlier drive"
        )
        evidence["route_drift"] = {"compared_against": None, "drifted": []}
    else:
        drifted, drift_failures = diff_routes(baseline, routes)
        failures.extend(drift_failures)
        evidence["route_drift"] = {
            "compared_against": "the earliest route drive recorded in qa/cr-gate-live.json",
            "baseline_rows": len(baseline),
            "drifted": drifted,
        }
        assertions.check(
            "RR2",
            "no pre-existing route changed status or shape since the recorded baseline",
            pointer="<route drift>",
            expected=[],
            observed=[d["route"] for d in drifted],
        )

    # ── 7 · REGRESSION: the permit gate run
    gate_run = origin.request("gate_run", "POST", "/v1/demo/gate-run", body=b"")
    evidence["gate_run"] = gate_run.as_record()
    if gate_run.status == 200 and gate_run.json is not None:
        evidence["gate_run_summary"] = assert_permit_gate_run(gate_run.json, assertions)
    else:
        assertions.check(
            "G0",
            "POST /v1/demo/gate-run still answers 200 with a JSON body",
            pointer="<http status>",
            expected=200,
            observed=gate_run.status,
        )

    # ── 8 · REGRESSION: the suite
    suites: dict[str, Any] = {}
    for label, path in (("before", args.suite_junit_before), ("after", args.suite_junit)):
        if path is None:
            continue
        if not Path(path).is_file():
            flag = "--suite-junit-before" if label == "before" else "--suite-junit"
            failures.append(f"{flag}: {path} missing")
            continue
        totals = read_junit(Path(path))
        # The basename, not the absolute path. The XML is a session artefact under the
        # scratchpad rather than a committed one, so its full path names a machine and a
        # home directory instead of naming anything a reader could open.
        totals["junitxml"] = Path(path).name
        totals["junitxml_note"] = (
            "uncommitted session artefact; reproduce with the argv below and read the "
            "counts off the ROOT ELEMENT, never off a terminal tail"
        )
        totals["argv"] = (
            ".venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests "
            "tests/deploy --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=<out>"
        )
        suites[label] = totals
        assert_suite(totals, assertions, label=label)
    if suites:
        evidence["suite"] = {"baseline": SUITE_BASELINE, **suites}
    else:
        caveats.append("no --suite-junit given, so no suite numbers are recorded in this run")

    # ── 9 · THE VERDICT
    failures.extend(assertions.failures)
    evidence["assertions"] = assertions.as_json()
    evidence["failures"] = failures
    evidence["caveats"] = caveats
    if not endpoint_declared:
        code = EXIT_UNANSWERABLE
    elif failures:
        evidence["status"] = "NOT PROVEN"
        evidence["verdict"] = "NOT PROVEN"
        code = EXIT_NOT_PROVEN
    else:
        evidence["status"] = "PROVEN"
        evidence["verdict"] = "PROVEN"
        code = EXIT_PROVEN
    evidence["exit_code"] = code

    # ── 10 · THE TRANSCRIPT — every request, verbatim, in the order they were sent
    phase_record = {
        "phase": args.phase,
        "generated_utc": _now_utc(),
        "origin": origin.base,
        "verdict": evidence["verdict"],
        "exit_code": code,
        "preexisting_routes": routes,
        "requests": [a.as_record() for a in origin.log],
    }
    transcript.update(
        {
            "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
            "SPDX-License-Identifier": "CC-BY-4.0",
            "schema": "mainline.proof.cr-gate-live/1",
            "note": (
                "Raw transcript. Every entry is a request this script sent to the public "
                "Function URL and the bytes that came back. Phases are APPENDED; nothing "
                "here is ever rewritten, because the earliest drive is what the regression "
                "diff compares against."
            ),
            "produced_by": "scripts/proof/cr_gate_refusal.py",
        }
    )
    transcript["phases"].append(phase_record)
    return code, evidence, transcript


def _print_summary(evidence: dict[str, Any]) -> None:
    print(f"origin        {evidence['origin']}")
    print(f"phase         {evidence['phase']}")
    deployment = evidence.get("deployment", {})
    if deployment:
        print(
            f"deployment    {deployment.get('database')} · {deployment.get('cluster_version')} · "
            f"chain {deployment.get('deploy_chain_applied')} · fingerprint "
            f"{str(deployment.get('schema_fingerprint'))[:16]}…"
        )
    assertions = evidence.get("assertions", {})
    print(f"assertions    {assertions.get('held', 0)}/{assertions.get('total', 0)} held")
    for key, label in (("cr_read", "CR READ  "), ("cr_blocking_checks", "CR CHECKS")):
        record = evidence.get(key)
        if record:
            print(f"{label}     {record['status']} · {record['bytes']} B · {record['elapsed_s']} s")
    for index, record in enumerate(evidence.get("cr_gate_runs", []), start=1):
        print(
            f"cr-gate-run {index} {record['status']} · {record['bytes']} B · "
            f"{record['elapsed_s']} s"
        )
    repeat = evidence.get("repeatability")
    if repeat:
        print(
            f"repeatable    {repeat['identical_across_runs']} "
            f"over {repeat['runs']} presses · cr row sha256 "
            f"{(repeat['cr_row_sha256'] or ['-'])[0][:16]}…"
        )
    routes = evidence.get("preexisting_routes", [])
    off = [r for r in routes if not r["status_matches_expectation"]]
    driven = sum(1 for r in routes if r.get("driven"))
    print(
        f"routes        {len(routes)} accounted for · {driven} driven · "
        f"{len(routes) - driven} declared-only (they commit) · {len(off)} off expectation"
    )
    gate = evidence.get("gate_run_summary")
    if gate:
        print(f"gate-run      {gate.get('verdict')} · persisted {gate.get('persisted')}")
    suite = evidence.get("suite", {})
    for label in ("before", "after"):
        totals = suite.get(label)
        if totals:
            print(
                f"suite {label:<7} {totals['collected']} collected / {totals['passed']} passed / "
                f"{totals['failed']} failed / {totals['errors']} errors"
            )
    caveats = evidence.get("caveats", [])
    if not caveats:
        print("caveats       (none) — nothing in this run is unproven-but-tolerated")
    for caveat in caveats:
        print(f"caveat        {caveat}")
    for failure in evidence.get("failures", []):
        print(f"  ! {failure}")
    if evidence["verdict"] == "UNANSWERABLE":
        print(f"  ! {evidence['why_unanswerable']['finding']}")
    print(f"VERDICT       {evidence['verdict']}")


def build_parser() -> argparse.ArgumentParser:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="cr_gate_refusal",
        description=(
            "Drive the deployed kernel and record it refusing to MERGE a change request "
            "that would edit away a clause the blame reaches — and refusing again when the "
            "projected counter is forged. Nothing is persisted; nothing is deployed."
        ),
    )
    parser.add_argument("--origin", default=LIVE_ORIGIN, help="public origin to drive")
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="how many times to press POST /v1/demo/cr-gate-run in succession (default 3)",
    )
    parser.add_argument("--timeout", type=float, default=90.0, help="per-request timeout, seconds")
    parser.add_argument(
        "--phase",
        default="proof",
        choices=("baseline", "proof"),
        help="'baseline' records the pre-existing surface; 'proof' also diffs against it",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=root / "evidence" / "deploy" / "cr-gate-live.json",
        help="published evidence path",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        default=root / "qa" / "cr-gate-live.json",
        help="raw transcript path; phases are appended to it",
    )
    parser.add_argument("--suite-junit", default=None, help="junit XML of the post-wave suite run")
    parser.add_argument(
        "--suite-junit-before", default=None, help="junit XML of the pre-wave suite run"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.runs < 1:
        print("cr_gate_refusal: --runs must be at least 1", file=sys.stderr)
        return EXIT_UNANSWERABLE
    try:
        code, evidence, transcript = run(args)
    except OriginUnreachable as exc:
        # No origin is not a refusal. Same split, same reason, same exit code as
        # gate_refusal.py's "there was no cluster".
        print(f"cr_gate_refusal: could not reach the origin: {exc}", file=sys.stderr)
        return EXIT_UNANSWERABLE
    except ValueError as exc:
        print(f"cr_gate_refusal: {exc}", file=sys.stderr)
        return EXIT_UNANSWERABLE

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.transcript.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    args.transcript.write_text(json.dumps(transcript, indent=2) + "\n", encoding="utf-8")
    _print_summary(evidence)
    print(f"evidence      {args.evidence}")
    print(f"transcript    {args.transcript}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
