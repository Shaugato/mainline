#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this program makes no database claim of its own. It is a recorder: it asks the
#     deployed read API five questions, writes down the bytes it got back, and asserts
#     nothing about them. Every claim in `docs/demo/memory-visible-CONTRACT.md` is sourced
#     from a file this program wrote, and `tests/demo/test_memory_loop_contract.py` replays
#     those files with the network unplugged.
"""Capture the store → retrieve → act loop from the deployed API, verbatim.

    python scripts/demo/capture_memory_loop.py                  # five GETs, nothing else
    python scripts/demo/capture_memory_loop.py --with-post      # the five GETs and ONE POST
    python scripts/demo/capture_memory_loop.py --print-manifest # what the last run recorded

WHY A RECORDER AND NOT A TEST. `docs/demo/memory-visible-plan.md` §4 fixes a table of
`data-cell` ids and the RFC 6901 pointer each is filled from. Four other workers build
against that table. If the table is checked against the live API only in the moment it is
written, it is a memory of a measurement; if the bytes are on disk, it is a measurement.
So this program's only job is to fetch and write, and to write the *raw* body — never a
re-serialised one. `json.dumps(json.loads(b))` would reorder nothing today and would still
be a different sequence of bytes from the one the origin sent, which is exactly the
substitution this repository's honesty rules exist to refuse.

── R-M8: NO IDENTIFIER IS WRITTEN DOWN HERE ──────────────────────────────────────────────
The plan's ruling R-M8 forbids a UUID literal in the loop's source. `scenario.EXPECTED`
derives a permit id by `uuid5` that is NOT the one the deployed Lambda answers on, because
the Lambda runs with `MAINLINE_DEMO_*` overrides — so an id transcribed into a source file
is a claim about a deployment, made by a file that cannot see it. This program therefore
addresses everything from `GET /v1/demo/subjects`: it reads `permit_id`, `clause_uuid` and
`run_id` out of that response and interpolates them. **There is no UUID literal in this
file, and there must never be one.** The captured payloads under `fixtures/memory-loop/`
are recordings and are exempt, as R-M8 says in its last line.

── GET-ONLY BY DEFAULT, AND THE ONE POST IS BEHIND A FLAG ────────────────────────────────
Four of the five reads are idempotent GETs against a public read API. The fifth beat of the
loop is `POST /v1/demo/gate-run`, which plays four beats inside one `SERIALIZABLE`
transaction and rolls it back — it writes nothing that survives, but it is still a POST
against the deployment every other lead is filming, and a program that fires one as a side
effect of being run is a program somebody will run twice by accident. `--with-post` is the
whole of the safety here, and one capture is enough: the payload is a recording, so a
second POST buys a different `run_id` and nothing else.

**This program never deploys, never writes an SSM parameter, never reads a credential and
sends no header but `accept`. The Function URL is public and unauthenticated.**

Exit codes: 0 every requested capture succeeded, 1 a capture failed, 2 usage or tooling.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The deployed Function URL. A host name, not an identifier — R-M8 bans UUID literals, and
#: this is the origin, which the page and every other worker must also address.
DEFAULT_BASE = "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws"

#: Where the recordings land. Named in `memory-visible-plan.md` §4 as W1's own path.
DEFAULT_OUT = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "fixtures" / "memory-loop"

MANIFEST_NAME = "manifest.json"

#: The subject keys this program reads out of `/v1/demo/subjects` and the path each one
#: addresses. The templates are `str.format` fields, so the only identifiers that ever
#: appear are the ones the API just handed us.
SUBJECT_ADDRESSED: tuple[tuple[str, str, str], ...] = (
    ("blocking-checks", "permit_id", "/v1/permits/{value}/blocking-checks"),
    ("ancestry", "clause_uuid", "/v1/clauses/{value}/ancestry"),
    ("recall-run", "run_id", "/v1/recall-runs/{value}"),
)

#: Captures that need no addressing at all.
UNADDRESSED: tuple[tuple[str, str], ...] = (("ledger", "/v1/ledger"),)

#: The one POST, and the body `cloud_contention.py:770` and `console_live_acceptance.py:970`
#: already send it: an empty JSON object. The driver takes its subjects from the server's
#: own environment, so there is nothing for a caller to choose.
GATE_RUN_NAME = "gate-run"
GATE_RUN_PATH = "/v1/demo/gate-run"
GATE_RUN_BODY = b"{}"

SUBJECTS_NAME = "subjects"
SUBJECTS_PATH = "/v1/demo/subjects"


class CaptureError(RuntimeError):
    """A request did not come back with a body we can write down."""


@dataclass(frozen=True)
class Capture:
    """One recorded exchange: what was asked, and the bytes that came back."""

    name: str
    method: str
    path: str
    status: int
    body: bytes
    received_at: str
    content_type: str | None

    @property
    def filename(self) -> str:
        return f"{self.name}.json"

    def manifest_row(self) -> dict[str, Any]:
        """The transport facts, which the body cannot carry about itself."""
        return {
            "name": self.name,
            "file": self.filename,
            "method": self.method,
            "path": self.path,
            "http_status": self.status,
            "byte_length": len(self.body),
            "sha256_hex": hashlib.sha256(self.body).hexdigest(),
            "content_type": self.content_type,
            "received_at": self.received_at,
        }


def _now() -> str:
    """This machine's clock, RFC 3339, UTC. The receipt time, and labelled as one.

    It is the CLIENT's time and is never presented as the server's: the payloads carry
    `observed_at` and `server_date` of their own, and the contract records both so a reader
    can see the difference rather than be handed one number and told it is both.
    """
    return _dt.datetime.now(tz=_dt.UTC).isoformat().replace("+00:00", "Z")


def fetch(
    base: str, path: str, *, method: str = "GET", body: bytes | None = None, timeout_s: float = 30.0
) -> Capture:
    """One exchange against *base* + *path*, recorded whatever it answers.

    A 4xx/5xx is a capture, not a crash: `R-M10` says a failure renders, and a contract that
    can only be written when everything is green is a contract that hides the day it isn't.
    The caller decides whether a non-200 is fatal.
    """
    url = base.rstrip("/") + path
    if not url.startswith("https://"):
        raise CaptureError(f"refusing a non-HTTPS URL: {url!r}")
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)  # noqa: S310
    name = path
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            status = int(response.status)
            raw = response.read()
            content_type = response.headers.get("content-type")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
        content_type = exc.headers.get("content-type") if exc.headers else None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CaptureError(f"{method} {name}: transport failed: {exc}") from exc
    return Capture(
        name=name,
        method=method,
        path=path,
        status=status,
        body=raw,
        received_at=_now(),
        content_type=content_type,
    )


def _renamed(capture: Capture, name: str) -> Capture:
    return Capture(
        name=name,
        method=capture.method,
        path=capture.path,
        status=capture.status,
        body=capture.body,
        received_at=capture.received_at,
        content_type=capture.content_type,
    )


def _subject(subjects_body: bytes, key: str) -> str:
    """Read one addressing key out of the subjects payload.

    Raises rather than defaulting. A missing key means the deployment is not the one this
    loop was designed against, and guessing an id would produce a 404 that reads like a
    bug in the endpoint instead of a bug in the assumption.
    """
    try:
        envelope = json.loads(subjects_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"{SUBJECTS_PATH} did not return JSON: {exc}") from exc
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict):
        raise CaptureError(f"{SUBJECTS_PATH} returned no `data` object")
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise CaptureError(
            f"{SUBJECTS_PATH} carries no addressing key {key!r}; this program refuses to "
            "invent one (R-M8)"
        )
    return value


def capture_all(base: str, *, with_post: bool, timeout_s: float = 30.0) -> list[Capture]:
    """The five GETs in order, then the one POST if it was asked for."""
    captures: list[Capture] = []

    subjects = _renamed(fetch(base, SUBJECTS_PATH, timeout_s=timeout_s), SUBJECTS_NAME)
    if subjects.status != 200:
        raise CaptureError(
            f"GET {SUBJECTS_PATH} answered {subjects.status}; every other capture is "
            "addressed from it, so there is nothing to ask next"
        )
    captures.append(subjects)

    for name, key, template in SUBJECT_ADDRESSED:
        path = template.format(value=_subject(subjects.body, key))
        captures.append(_renamed(fetch(base, path, timeout_s=timeout_s), name))

    for name, path in UNADDRESSED:
        captures.append(_renamed(fetch(base, path, timeout_s=timeout_s), name))

    if with_post:
        captures.append(
            _renamed(
                fetch(base, GATE_RUN_PATH, method="POST", body=GATE_RUN_BODY, timeout_s=timeout_s),
                GATE_RUN_NAME,
            )
        )
    return captures


def write_captures(captures: list[Capture], out_dir: Path, *, base: str) -> Path:
    """Write each raw body and rewrite the manifest, preserving untouched rows.

    A run without `--with-post` must not delete the gate-run recording a previous run
    made: the GETs are cheap and the POST is the one exchange we do not want to repeat.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST_NAME

    rows: dict[str, dict[str, Any]] = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        for row in previous.get("captures", []):
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                rows[row["name"]] = row

    for capture in captures:
        (out_dir / capture.filename).write_bytes(capture.body)
        rows[capture.name] = capture.manifest_row()

    order = [
        SUBJECTS_NAME,
        *(n for n, _, _ in SUBJECT_ADDRESSED),
        *(n for n, _ in UNADDRESSED),
        GATE_RUN_NAME,
    ]
    ordered = [rows[name] for name in order if name in rows]
    ordered.extend(row for name, row in sorted(rows.items()) if name not in order)

    manifest = {
        "captured_by": "scripts/demo/capture_memory_loop.py",
        "base_url": base,
        "note": (
            "Raw response bodies, byte for byte as the deployed API returned them. "
            "Nothing here was reformatted, pretty-printed or re-serialised. "
            "`received_at` is this client's clock at the moment the body finished "
            "arriving; each payload carries its own `observed_at` and `server_date`."
        ),
        "manifest_written_at": _now(),
        "captures": ordered,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record the memory loop from the deployed read API. GET-only unless "
        "--with-post is passed.",
    )
    parser.add_argument(
        "--base", default=DEFAULT_BASE, help="origin to read (default: the deployed Function URL)"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="fixture directory")
    parser.add_argument(
        "--with-post",
        action="store_true",
        help="also fire exactly ONE POST /v1/demo/gate-run. Off by default on purpose.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request seconds")
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="print the manifest of the last run and exit; makes no request",
    )
    args = parser.parse_args(argv)

    manifest_path = args.out / MANIFEST_NAME
    if args.print_manifest:
        if not manifest_path.exists():
            print(f"no manifest at {manifest_path}", file=sys.stderr)
            return 1
        sys.stdout.write(manifest_path.read_text(encoding="utf-8"))
        return 0

    try:
        captures = capture_all(args.base, with_post=args.with_post, timeout_s=args.timeout)
    except CaptureError as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1

    written = write_captures(captures, args.out, base=args.base)

    failed = 0
    for capture in captures:
        marker = "ok " if capture.status == 200 else "NOT 200"
        print(
            f"{marker} {capture.method:4s} {capture.path}  "
            f"{capture.status}  {len(capture.body)} B  -> {capture.filename}"
        )
        if capture.status != 200:
            failed += 1
    print(f"manifest -> {written}")
    if not args.with_post:
        print("no POST was made; pass --with-post to capture one gate-run")
    return 1 if failed else 0


if __name__ == "__main__":  # pragma: no cover - a CLI entry point
    raise SystemExit(main())
