#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Capture the Phase-1 demo EvidenceBundle from CockroachDB Cloud, and persist nothing.

    .venv/Scripts/python.exe scripts/deploy/capture_demo_bundle.py            # Cloud, from .env
    .venv/Scripts/python.exe scripts/deploy/capture_demo_bundle.py \\
        --dsn postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable \\
        --database w_w9_evidence_bundle                                       # local rehearsal

WHAT THIS PRODUCES AND WHY IT EXISTS
------------------------------------
``docs/leads/deploy-plan.md`` §0 states the bar: *"Provide a URL to your functional demo
app"* is Stage One, pass/fail, with no partial credit. Phase 1 is a static console over a
**cryptographically verified** EvidenceBundle captured from the Cloud cluster — no
backend, no database in the request path, nothing to fall over. This program is what makes
that bundle.

It writes ``verticals/mainline/apps/console/fixtures/bundles/demo-cloud/``:

    frames/   one file per captured exchange, named by the canonical request key
    sql/      the verbatim round trips, including the three beats' SQLSTATEs
    manifest.seed.json  the claims a human makes; input to sealing, never served

and then hands the directory to ``scripts/capture-bundle.ts seal`` — which is the ONLY
thing that writes ``manifest.json`` — and to ``check``, and fails the run if ``check``
disagrees with ``seal``.

THE FOUR PROPERTIES THIS PROGRAM IS RESPONSIBLE FOR
--------------------------------------------------
**1. The three beats happen in ONE transaction, and the whole thing is rolled back.**
``evidence/deploy/lead/savepoint-probe-20260810.txt`` established that CockroachDB honours
``ROLLBACK TO SAVEPOINT`` after a constraint refusal and that the transaction keeps taking
statements. Beat 4 SUCCEEDS and is rolled back with the rest, so capturing the bundle does
not mutate the world the live API later serves. :func:`_persistence_check` proves it with
row counts and the permit's own column values taken outside the transaction, before and
after — column values as well as counts, because the drift beat mutates a column without
changing a count.

**2. ``40001`` is retried, at the transaction level.** A single-node Docker cluster never
produces ``RETRY_SERIALIZABLE``; a managed multi-node cluster does, and it killed the first
Cloud run of 2026-08-10 (``docs/leads/deploy-plan.md`` §1.2). The retry wraps the WHOLE
capture, because the retry unit of a serializable transaction is the transaction.

**3. The fingerprint is observed, not declared.** ``cluster_fingerprint.source`` is
``observed`` and the version string, the cluster version, the region and the database are
read from the cluster during the capture and filed verbatim in
``sql/cluster-fingerprint.txt``. The console renders that block, so a value nobody measured
would be a lie on the screen rather than a lie in a file.

**4. Nothing is invented.** Every payload is produced by the SAME functions the live
Lambda serves — ``mainline_demo_api.reads`` for the twelve read resources and
``mainline_demo_api.transitions``'s envelope builders plus ``mainline_demo_api.refusal``
for the invoke results. Where a resource has no rows behind it the frame is OMITTED and
the omission is recorded with its reason; where a payload is emitted with the read API's
own ``staged`` flag that flag is carried through untouched. The two twin subjects
(§ :data:`_TWIN_CLONE`) carry ``staged: true`` with a verbatim note, because their rows
existed only inside the capture transaction — while their SQLSTATEs, constraint names and
messages are the cluster's own, taken off psycopg's ``Diagnostic``.

WHY NOT ``capture-bundle.ts capture``
-------------------------------------
Its sql step spawns one ``cockroach sql`` process per statement, so every statement lands
in its own session and its own implicit transaction, and a savepoint cannot span process
boundaries. ``seal`` and ``check`` are used unchanged. ``capture-plan.demo.json`` records
the same reasoning where a reader of the plan will meet it.

EXIT CODES
----------
``0`` captured, sealed, checked, and nothing persisted.
``1`` a beat did not match its expectation, or ``check`` disagreed, or the capture
      persisted something. The bundle on disk is not trustworthy and says so.
``2`` usage: no DSN, no plan, no seeded permit, or node/capture-bundle.ts unavailable.
``3`` the transaction stayed undecided (``40001``) after every retry. Not a refusal — the
      gate never got to say anything — and this program does not pretend otherwise.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as _dt
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Final

# ── The repository, and the two packages this program borrows rather than reimplements ──


def repo_root() -> Path:
    """The repository root, found by walking up from this file."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "verticals" / "mainline").is_dir():
            return candidate
    raise RuntimeError(f"cannot locate the repository root from {here}")


ROOT: Final = repo_root()
CONSOLE: Final = ROOT / "verticals" / "mainline" / "apps" / "console"
DEMO_API_SRC: Final = ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"

if str(DEMO_API_SRC) not in sys.path:
    sys.path.insert(0, str(DEMO_API_SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

# The read API and the transition API, imported rather than copied. These are the exact
# functions the Lambda serves; capturing from anything else would make LIVE and REPLAY two
# implementations wearing one badge.
from mainline_demo_api import reads as _reads  # noqa: E402
from mainline_demo_api import refusal as _refusal  # noqa: E402
from mainline_demo_api import transitions as _transitions  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

# The DSN rewriter and the redactor live in scripts/deploy/cloud_chain.py by design — the
# package docstring says the shared pieces live in one place so they cannot drift between
# the applier, the seeder and anything downstream. Imported, with a local fallback so this
# program still runs if it is copied out of the tree.
try:  # pragma: no cover - exercised by the absence of the module, not by a test
    from scripts.deploy.cloud_chain import redact as _redact
    from scripts.deploy.cloud_chain import rewrite_dsn as _rewrite_dsn
except Exception:  # noqa: BLE001 - any import failure means we use the fallback

    def _redact(text: str) -> str:
        import re

        return re.sub(r"//([^:/@\s]+):[^@/\s]*@", r"//\1:<redacted>@", text)

    def _rewrite_dsn(dsn: str, *, database: str) -> str:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(dsn)
        return urlunsplit(parts._replace(path=f"/{database}"))


EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2
EXIT_UNDECIDED: Final = 3

MAX_ATTEMPTS: Final = 6
BACKOFF_BASE_SECONDS: Final = 0.25
RETRYABLE: Final = "40001"

INVOKE_SCHEMA_ID: Final = _transitions.INVOKE_SCHEMA_ID
MERGE_PROCEDURE: Final = "trappoint.merge_permit"

DEFAULT_PLAN: Final = CONSOLE / "capture-plan.demo.json"
DEFAULT_OUT: Final = CONSOLE / "fixtures" / "bundles" / "demo-cloud"
DEFAULT_EVIDENCE: Final = ROOT / "evidence" / "deploy" / "bundle-capture.json"
DEFAULT_DATABASE: Final = "mainline_demo"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the canonical request key, and the frame file name derived from it
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Path templates, transcribed from ``console/src/data/resources.ts``. Transcribed rather
#: than imported because that file is TypeScript and this is Python;
#: :func:`_assert_resources_agree` reads the TypeScript back and refuses to run if the two
#: have drifted, so the duplication cannot rot silently.
_TEMPLATES: Final[dict[str, tuple[str, str]]] = {
    "permit": ("GET", "/v1/permits/{permit_id}"),
    "change_request": ("GET", "/v1/change-requests/{cr_id}"),
    "blocking_checks": ("GET", "/v1/permits/{permit_id}/blocking-checks"),
    "disposition": ("GET", "/v1/checks/{check_id}/disposition"),
    "exposure_receipt": ("GET", "/v1/receipts/{receipt_id}"),
    "clause_version": ("GET", "/v1/clauses/{clause_uuid}/versions/{commit_id}"),
    "clause_ancestry": ("GET", "/v1/clauses/{clause_uuid}/ancestry"),
    "ledger": ("GET", "/v1/ledger"),
    "silence": ("GET", "/v1/permits/{permit_id}/silence"),
    "recall_run": ("GET", "/v1/recall-runs/{run_id}"),
    "propagation": ("GET", "/v1/lessons/{lesson_id}/propagation"),
    "audit": ("GET", "/v1/audit"),
    "materialise_checks": ("POST", "/v1/permits/{permit_id}/checks:materialise"),
    "sign_disposition": ("POST", "/v1/checks/{check_id}/disposition"),
    "merge_permit": ("POST", "/v1/permits/{permit_id}/merge"),
    "suspend_permit": ("POST", "/v1/permits/{permit_id}/suspend"),
}

_UNRESERVED: Final = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
)


def _assert_resources_agree() -> None:
    """Refuse to run if :data:`_TEMPLATES` has drifted from ``resources.ts``.

    A frame filed under a stale path is a frame the console will never find, and the
    failure would present as an empty screen rather than as an error. Cheap to check, so
    it is checked every run.
    """
    source = (CONSOLE / "src" / "data" / "resources.ts").read_text(encoding="utf-8")
    import re

    found = dict(
        re.findall(r"declare\(\s*'([a-z_]+)',\s*'(?:GET|POST)',\s*'([^']+)'", source)
    )
    if not found:
        raise SystemExit(
            "capture_demo_bundle: could not read any resource declaration out of "
            "console/src/data/resources.ts. The transcription in _TEMPLATES cannot be "
            "checked, and an unchecked transcription is how a frame gets filed under a "
            "name nothing asks for."
        )
    drift = {
        key: (template, _TEMPLATES.get(key, ("", ""))[1])
        for key, template in found.items()
        if _TEMPLATES.get(key, ("", ""))[1] != template
    }
    if drift:
        raise SystemExit(
            "capture_demo_bundle: console/src/data/resources.ts and _TEMPLATES disagree "
            f"about {sorted(drift)}: {drift!r}. Update _TEMPLATES."
        )


def resolve_key(resource: str, path: dict[str, str] | None = None,
                query: dict[str, str] | None = None) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Return ``(key, method, interpolated_path, sorted_query)`` for one request.

    Mirrors ``resolveRequest`` in ``console/src/data/resources.ts``: the key is method,
    interpolated path and the query sorted by name then value — never a transport detail —
    which is what makes a frame captured here addressable by a player that has never seen
    this program.
    """
    method, template = _TEMPLATES[resource]
    interpolated = template
    for name, value in (path or {}).items():
        interpolated = interpolated.replace("{" + name + "}", value)
    if "{" in interpolated:
        raise KeyError(
            f"resource {resource!r} still has an unfilled path parameter: {interpolated}"
        )
    pairs = sorted((query or {}).items())
    from urllib.parse import quote

    encoded = "&".join(
        f"{quote(name, safe='')}={quote(value, safe='')}" for name, value in pairs
    )
    key = f"{method} {interpolated}" if not encoded else f"{method} {interpolated}?{encoded}"
    return key, method, interpolated, pairs


def frame_path_for_key(key: str) -> str:
    """Mirror of ``framePathForKey``: unreserved bytes pass through, the rest become ~XX."""
    out = []
    for byte in key.encode("utf-8"):
        char = chr(byte)
        out.append(char if char in _UNRESERVED else f"~{byte:02X}")
    return "frames/" + "".join(out) + ".json"


# ═══════════════════════════════════════════════════════════════════════════════════════
# the twin subjects
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Build one transaction-local copy of the seeded permit's whole history.
#:
#: Every statement is ``INSERT ... SELECT`` from the seeded rows rather than a literal, so
#: the twin is a copy of what is actually in the database rather than a second opinion
#: about it, and so a change to the seed cannot leave this list describing a permit that
#: no longer exists. The trigger chain is walked, not bypassed: inserting the blocking
#: check fires ``check_materialised``, which takes ``FOR UPDATE`` on the twin, increments
#: ``open_blocking`` to 1, bumps ``gate_epoch`` and writes the outbox row — which is why
#: no statement here sets a counter. ``severity``/``virulence``/``closure_gen`` are passed
#: as 0/'routine'/0 for the same reason the seed does: ``fn_check_project`` overwrites
#: them from ``mainline.clause_blame_current`` (invariant MI25), so supplying the real
#: values would be supplying inputs to nothing.
_TWIN_CLONE: Final[tuple[tuple[str, str], ...]] = (
    (
        "permit",
        """
INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name,
       opened_at, horizon_at)
SELECT %(new)s, site_id, site_role, %(ref)s, %(refname)s, opened_at, horizon_at
  FROM mainline.permit WHERE permit_id = %(src)s
""",
    ),
    (
        "permit_clause",
        """
INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation)
SELECT %(new)s, clause_uuid, commit_id, relation
  FROM mainline.permit_clause WHERE permit_id = %(src)s
""",
    ),
    (
        "boundary_certificate",
        """
INSERT INTO mainline.boundary_certificate (permit_id, cert_gen, asset_graph_version,
       tags_declared, tags_resolved, tags_unmodelled, under_declared, computed_at)
SELECT %(new)s, cert_gen, asset_graph_version, tags_declared, tags_resolved,
       tags_unmodelled, under_declared, computed_at
  FROM mainline.boundary_certificate WHERE permit_id = %(src)s
""",
    ),
    (
        "recall_run",
        """
INSERT INTO mainline_meas.recall_run (run_id, permit_id, site_id, corpus_commit,
       policy_version, index_plan_digest, index_generation, n_candidates, n_blocking,
       n_advisory, n_silenced, n_deduped, started_at)
SELECT %(run)s, %(new)s, site_id, corpus_commit, policy_version, index_plan_digest,
       index_generation, n_candidates, n_blocking, n_advisory, n_silenced, n_deduped,
       started_at
  FROM mainline_meas.recall_run WHERE permit_id = %(src)s
""",
    ),
    (
        "silence_receipt",
        """
INSERT INTO mainline_meas.silence_receipt (silence_receipt_id, run_id, permit_id,
       corpus_root, candidate_root, theta, s, n, boundary_proof, policy_version, issued_at)
SELECT %(sil)s, %(run)s, %(new)s, corpus_root, candidate_root, theta, s, n, boundary_proof,
       policy_version, issued_at
  FROM mainline_meas.silence_receipt WHERE permit_id = %(src)s
""",
    ),
    (
        "blocking_check",
        """
INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id,
       clause_uuid, commit_id, precursor_event_id, origin, severity, virulence,
       closure_gen, recall_run_id, evidence_summary, materialised_at)
SELECT %(chk)s, subject_kind, %(new)s, site_id, clause_uuid, commit_id, precursor_event_id,
       origin, 0, 'routine', 0, %(run)s, evidence_summary, materialised_at
  FROM mainline.blocking_check WHERE permit_id = %(src)s
""",
    ),
    (
        "exposure_receipt",
        """
INSERT INTO mainline.exposure_receipt (receipt_id, subject_kind, permit_id, actor_sub,
       issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, policy_version,
       total_tokens, receipt_digest)
SELECT %(rcpt)s, subject_kind, %(new)s, actor_sub, issued_at, issued_hlc, expires_at,
       corpus_root, %(sil)s, policy_version, total_tokens, receipt_digest
  FROM mainline.exposure_receipt WHERE permit_id = %(src)s
""",
    ),
    (
        "exposure_line",
        """
INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens)
SELECT %(rcpt)s, %(chk)s, l.payload_digest, l.tokens
  FROM mainline.exposure_line l
  JOIN mainline.exposure_receipt r ON r.receipt_id = l.receipt_id
 WHERE r.permit_id = %(src)s
""",
    ),
    (
        "permit_event seq 1",
        """
INSERT INTO mainline.permit_event (permit_id, seq, prev_seq, from_state, to_state,
       subject_kind, actor_sub, payload, prev_digest, at)
SELECT %(new)s, 1, 0, 'draft', 'checks_materialised', 'permit', actor_sub, payload,
       prev_digest, at
  FROM mainline.permit_event WHERE permit_id = %(src)s AND seq = 1
""",
    ),
    (
        "permit_event seq 2",
        """
INSERT INTO mainline.permit_event (permit_id, seq, prev_seq, from_state, to_state,
       subject_kind, actor_sub, payload, prev_digest, at)
SELECT %(new)s, 2, 1, 'checks_materialised', 'dispositioned', 'permit', src.actor_sub,
       src.payload, prior.chain_digest, src.at
  FROM mainline.permit_event src
  JOIN mainline.permit_event prior ON prior.permit_id = %(new)s AND prior.seq = 1
 WHERE src.permit_id = %(src)s AND src.seq = 2
""",
    ),
    (
        "head",
        """
UPDATE mainline.permit SET state = 'dispositioned', head_seq = 2 WHERE permit_id = %(new)s
""",
    ),
)

#: The signature that closes the counter. Copied from
#: ``mainline_demo_api.gate_run._DISPOSITION_SQL`` — the same column list the live gate-run
#: endpoint uses — because every column except the four a signer actually chooses is
#: PROJECTED by ``fn_disposition_project`` from authoritative rows (invariant I02) and the
#: values passed here are overwritten. What the signer chooses is the kind, the defeater
#: code, the rationale and the signature.
_DISPOSITION_SQL: Final = """
INSERT INTO mainline.disposition (
  disposition_id, check_id, receipt_id, subject_kind, permit_id, site_id, kind, virulence,
  closure_gen, defeater_code, defeater_vocab_sha256, rationale, evidence_sha256, signer_sub,
  signer_rank, signer_org, signer_credential_id, countersigner_sub,
  countersigner_credential_id, signature_alg, authenticator_data, client_data_json,
  user_verified, competency_snapshot, competency_source_id, competency_sha256,
  req_compensating, req_second_signer, req_foreign_org, req_predicate, req_reassert,
  min_signer_rank, severity_snapshot, deliberation_seconds, evidence_opened,
  prior_override_count)
VALUES (%s, %s, %s, 'permit', %s, %s, 'applied', 'routine', 0,
        'MECHANISM_PRESENT_AND_VERIFIED', %s, %s, %s, %s, 1, 'x', %s, %s, %s, 'ES256',
        %s, %s, true, %s, %s, %s, false, false, false, false, false, 1, 0, 0, true, 0)
"""

#: ``mainline.disposition`` declares ``CHECK (length(rationale) >= 120)`` — measured, this
#: run, as SQLSTATE 23514 on a shorter one. A signature whose reason fits in a tweet is not
#: a reason, and the schema says so.
_RATIONALE: Final = (
    "The recalled precursor is answered by a verified zero-energy isolation procedure "
    "re-issued after the incident, and this permit's scope is covered by that procedure "
    "in full. Verification at zero is witnessed and recorded before any intrusive work "
    "begins, so the mechanism the incident found missing is present and exercised here."
)

_MERGE_SQL: Final = "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)"
_FORCE_SQL: Final = "UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s"

_MERGE_RECORD_SQL: Final = """
SELECT encode(m.merged_commit, 'hex'), m.merged_at, encode(m.clearance_digest, 'hex'),
       m.gate_epoch
  FROM mainline.merge_record m WHERE m.subject_id = %s
"""

_PERMIT_ROW_SQL: Final = """
SELECT state::STRING, head_seq, gate_epoch, open_blocking, unmet_floor_count,
       countersigned_count, encode(merged_commit, 'hex')
  FROM mainline.permit WHERE permit_id = %s
"""


# ═══════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═══════════════════════════════════════════════════════════════════════════════════════


def rfc3339(moment: _dt.datetime | None = None) -> str:
    value = (moment or _dt.datetime.now(_dt.UTC)).astimezone(_dt.UTC)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha(*parts: bytes | str) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def canonical_json(payload: dict[str, Any]) -> bytes:
    """The client-supplied canonical bytes ``mainline.merge_permit`` takes.

    ``trappoint_jcs`` is the repository's authority and is used when it imports; the
    fallback coincides with RFC 8785 for the ASCII strings and small integers this payload
    contains and is NOT a general JCS implementation. Which one ran travels into the
    evidence, because a digest whose derivation is unstated is a digest nobody can
    recompute.
    """
    try:
        from trappoint_jcs import canonicalise
    except ImportError:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    canon = canonicalise(payload)
    return canon if isinstance(canon, bytes) else str(canon).encode("utf-8")


def canonicalisation_name() -> str:
    try:
        import trappoint_jcs  # noqa: F401
    except ImportError:
        return "capture_demo_bundle.canonical_json (sorted-key JSON; ASCII payloads only)"
    return "trappoint_jcs.canonicalise"


def load_dotenv(root: Path) -> None:
    """Read ``.env`` without overwriting anything already set. The DSN carries a password."""
    env_file = root / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sqlstate_of(exc: BaseException) -> str:
    state = getattr(exc, "sqlstate", None)
    if state:
        return str(state)
    diag = getattr(exc, "diag", None)
    return str(getattr(diag, "sqlstate", "") or "")


def one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:600]


# ═══════════════════════════════════════════════════════════════════════════════════════
# the bundle writer
# ═══════════════════════════════════════════════════════════════════════════════════════


class Bundle:
    """Accumulates frames and sql round trips, then writes them out.

    Held in memory until the run has succeeded so that a failed capture does not leave a
    half-written directory that ``seal`` would happily digest. A sealed half-bundle is
    worse than no bundle: it is a bundle with a manifest.
    """

    def __init__(self, out: Path) -> None:
        self.out = out
        self.files: dict[str, bytes] = {}
        self.frames: list[dict[str, Any]] = []

    def frame(
        self,
        *,
        resource: str,
        payload: dict[str, Any],
        status: int,
        path: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        duration_ms: float,
        via: str,
        source: str,
    ) -> str:
        key, method, interpolated, pairs = resolve_key(resource, path, query)
        rel = frame_path_for_key(key)
        body_text = json.dumps(payload, ensure_ascii=False, sort_keys=False, indent=2) + "\n"
        request_b64 = (
            None
            if method != "POST"
            else base64.b64encode(
                json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
        )
        frame = {
            "frame_version": 1,
            "key": key,
            "request": {
                "method": method,
                "path": interpolated,
                "query": [{"name": n, "value": v} for n, v in pairs],
                "body_b64": request_b64,
            },
            "response": {
                "status": status,
                "headers": [{"name": "content-type", "value": "application/json"}],
                "body_b64": base64.b64encode(body_text.encode("utf-8")).decode("ascii"),
            },
            "captured_at": rfc3339(),
            "duration_ms": round(duration_ms),
        }
        self.files[rel] = (json.dumps(frame, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self.frames.append(
            {
                "path": rel,
                "key": key,
                "resource": resource,
                "status": status,
                "source": source,
                "via": via,
                "staged": bool(payload.get("staged")),
                "bytes": len(self.files[rel]),
                "duration_ms": round(duration_ms, 3),
            }
        )
        return rel

    def text(self, rel: str, body: str) -> str:
        self.files[rel] = body.encode("utf-8")
        return rel

    def write(self, manifest_seed: dict[str, Any]) -> None:
        if self.out.exists():
            # A stale frame from a previous capture would be sealed, listed and served, and
            # would answer a request nobody made in this run. Remove rather than merge.
            for existing in sorted(self.out.rglob("*"), reverse=True):
                if existing.is_file():
                    existing.unlink()
                elif existing.is_dir():
                    with contextlib.suppress(OSError):
                        existing.rmdir()
        self.out.mkdir(parents=True, exist_ok=True)
        for rel, data in sorted(self.files.items()):
            target = self.out.joinpath(*rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (self.out / "manifest.seed.json").write_text(
            json.dumps(manifest_seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @property
    def total_bytes(self) -> int:
        return sum(len(data) for data in self.files.values())


# ═══════════════════════════════════════════════════════════════════════════════════════
# the round trip, written the way a stranger can read it
# ═══════════════════════════════════════════════════════════════════════════════════════


def round_trip_text(
    *,
    title: str,
    connection: str,
    transaction: str,
    statement: str,
    parameters: list[str],
    outcome: str,
    sqlstate: str,
    constraint: str | None,
    constraint_source: str | None,
    message: str,
    detail: str,
    hint: str,
    stdout: str,
    driver: str,
    note: str,
) -> str:
    """One verbatim round trip.

    The shape follows ``fixtures/bundles/blk-07/sql/*.txt`` — a command line, a statement,
    an outcome — with the sections a psycopg capture can fill honestly and no sections it
    cannot. There is no ``exit code`` block, because no process exited: this ran in a
    library, and a fabricated ``1`` would be the first invented byte in the bundle.
    """
    def block(name: str, body: str) -> str:
        return f"--- {name} ---\n{body.rstrip()}\n" if body.strip() else f"--- {name} ---\n(none)\n"

    return (
        f"# {title}\n"
        + block("connection", connection)
        + block("transaction", transaction)
        + block("statement", statement.strip())
        + block("parameters", "\n".join(parameters))
        + block("outcome", outcome)
        + block("sqlstate", sqlstate)
        + block(
            "constraint",
            "(none reported)"
            if not constraint
            else f"{constraint}\nsource: {constraint_source or 'unstated'}",
        )
        + block("message", message)
        + block("detail", detail)
        + block("hint", hint)
        + block("result", stdout)
        + block("driver", driver)
        + block("note", note)
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# the capture
# ═══════════════════════════════════════════════════════════════════════════════════════


class Undecided(RuntimeError):
    """``40001`` after every retry. The transaction never decided anything."""


def _counts_statement(tables: list[str]) -> str:
    """The count statements, as text for the round-trip file.

    A table name cannot be a bind parameter, so it is interpolated. The names come from
    capture-plan.demo.json's persistence_check.tables, which is a file in this repository
    — never a request parameter and never a database row.
    """
    return "\n".join(f"SELECT count(*) FROM {table};" for table in tables)  # noqa: S608


def _fingerprint(
    conn: psycopg.Connection[Any], tables: list[str], permit_id: uuid.UUID
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for table in tables:
        # The table names are interpolated because a table name cannot be a bind
        # parameter. They come from capture-plan.demo.json's persistence_check.tables,
        # which is a file in this repository, never from a request or a database row.
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        counts[table] = int(row[0]) if row else -1
    row = conn.execute(_PERMIT_ROW_SQL, (permit_id,)).fetchone()
    return {
        "row_counts": counts,
        "permit_row": None
        if row is None
        else {
            "state": row[0],
            "head_seq": int(row[1]),
            "gate_epoch": int(row[2]),
            "open_blocking": int(row[3]),
            "unmet_floor_count": int(row[4]),
            "countersigned_count": int(row[5]),
            "merged_commit": row[6],
        },
    }


def _cluster_fingerprint(
    conn: psycopg.Connection[Any], database: str
) -> tuple[dict[str, Any], str]:
    """Read what the cluster says about itself. `source` is `observed` because of this."""
    observed: dict[str, str] = {}
    for label, statement in (
        ("version", "SELECT version()"),
        ("cluster_version", "SHOW CLUSTER SETTING version"),
        ("current_database", "SELECT current_database()"),
        ("current_user", "SELECT current_user"),
        ("cluster_id", "SELECT crdb_internal.cluster_id()::STRING"),
        (
            "node_locality",
            (
                "SELECT COALESCE((SELECT locality FROM crdb_internal.gossip_nodes LIMIT 1),"
                " '(not visible to this user)')"
            ),
        ),
    ):
        try:
            row = conn.execute(statement).fetchone()
            observed[label] = "" if row is None or row[0] is None else str(row[0])
        except psycopg.Error as exc:
            conn.rollback()
            observed[label] = f"(refused: {sqlstate_of(exc)} {one_line(exc)[:120]})"

    version = observed.get("version", "")
    product = (
        "CockroachDB CCL" if "CockroachDB CCL" in version
        else version.split(" v")[0] or "unknown"
    )
    tag = ""
    for token in version.split():
        if token.startswith("v") and token[1:2].isdigit():
            tag = token.rstrip(",")
            break
    locality = observed.get("node_locality", "")
    region = "unknown"
    for part in locality.split(","):
        if part.startswith("region="):
            region = part.split("=", 1)[1]
            break
    if region == "unknown":
        host = ""
        with contextlib.suppress(Exception):
            host = str(conn.info.host or "")
        for candidate in ("aws-ap-southeast-1", "aws-ap-southeast-2", "aws-us-east-1"):
            if candidate in host:
                region = candidate
                break
        if region == "unknown" and host in ("127.0.0.1", "localhost", "::1"):
            region = "local (single-node Docker; no cloud region)"

    fingerprint = {
        "source": "observed",
        "product": product,
        "version": tag or "unknown",
        "cluster_version": observed.get("cluster_version") or None,
        "tier": None,
        "region": region,
        "evidence_ref": (
            "Read from the cluster during this capture by "
            "scripts/deploy/capture_demo_bundle.py; the verbatim round trip is "
            "sql/cluster-fingerprint.txt in this bundle. `source: observed` means exactly "
            "that and nothing more: it is a statement about the database that answered, "
            "not about where inference runs. Residency is split in this deployment — "
            "database in aws-ap-southeast-1 (Singapore), Bedrock in ap-southeast-2 "
            "(Sydney) — so no end-to-end Australian residency claim may be made from this "
            "bundle."
        ),
    }
    text = round_trip_text(
        title="Cluster fingerprint — what the cluster says about itself",
        connection=f"database {database}, user {observed.get('current_user', '?')}",
        transaction="autocommit; read-only statements",
        statement="SELECT version();\nSHOW CLUSTER SETTING version;\n"
        "SELECT current_database();\nSELECT current_user;\n"
        "SELECT crdb_internal.cluster_id();\n"
        "SELECT locality FROM crdb_internal.gossip_nodes LIMIT 1;",
        parameters=[],
        outcome="OK",
        sqlstate="00000",
        constraint=None,
        constraint_source=None,
        message="",
        detail="",
        hint="",
        stdout="\n".join(f"{name} = {value}" for name, value in observed.items()),
        driver=f"psycopg {psycopg.__version__}",
        note=(
            "This is the block manifest.cluster_fingerprint was derived from. Where a "
            "value reads '(refused: …)' the SQL user this capture ran as is not permitted "
            "to read it — recorded rather than omitted, because a missing line and a "
            "refused line are different facts."
        ),
    )
    return fingerprint, text


def _schema_version(conn: psycopg.Connection[Any], database: str) -> str:
    """The migration head this capture ran against, read from the applier's own marker.

    ``scripts/deploy/cloud_chain.py`` upserts one row per database into
    ``trappoint.deploy_chain`` carrying the file count, how many applied, how many failed
    and the tree fingerprint. That row is the only statement in the database about which
    schema is in it, so it is the only thing quoted here. When there is no such row the
    string says so — a bundle that cannot name its schema cannot be replayed against a
    claim about that schema, and inventing a head would be inventing the claim.
    """
    try:
        row = conn.execute(
            "SELECT files, applied, failed, encode(tree_fingerprint, 'hex'), applied_at "
            "FROM trappoint.deploy_chain WHERE marker_id = %s",
            (database,),
        ).fetchone()
    except psycopg.Error:
        conn.rollback()
        row = None
    if row is None:
        return (
            f"no trappoint.deploy_chain row for {database}; migration head not established "
            "by this capture"
        )
    return (
        f"chain {row[1]}/{row[0]} applied, {row[2]} failed; "
        f"tree_fingerprint {row[3][:32]}…; applied_at {row[4].isoformat()}"
    )


def _read_context(
    conn: psycopg.Connection[Any], resource: str, path: dict[str, str], query: dict[str, str]
) -> tuple[dict[str, Any], float]:
    """One read, through the live API's own handler, inside the caller's transaction.

    ``mainline_demo_api.db.connection`` opens with ``row_factory=dict_row`` and every read
    handler indexes its rows by column name. This program's own statements index by
    position, so the factory is swapped for the duration of the call rather than for the
    connection: a handler reading ``row["permit_id"]`` and a beat reading ``row[0]`` are
    both correct, and neither has to know about the other.

    The handler is called DIRECTLY rather than through ``read_resource``. That skips two
    wrappers and one behaviour: ``db.read_transaction`` would issue ``SET TRANSACTION READ
    ONLY`` inside a transaction that has already written (the twins), and ``db.read`` would
    add a second retry loop inside the one this program already owns. The SQL each resource
    runs is identical either way.
    """
    from psycopg.rows import dict_row

    handler = _reads.READS.get(resource)
    if handler is None:
        raise KeyError(f"no read handler for {resource!r}")
    previous = conn.row_factory
    conn.row_factory = dict_row
    started = time.perf_counter()
    try:
        payload = handler(conn, path, query)
    finally:
        conn.row_factory = previous
    return payload, (time.perf_counter() - started) * 1000.0


def _call_merge(conn: psycopg.Connection[Any], permit_id: uuid.UUID, signer: str) -> dict[str, Any]:
    payload = {
        "permit": str(permit_id),
        "merged_by": signer,
        "source": "scripts/deploy/capture_demo_bundle.py",
    }
    canon = canonical_json(payload)
    leaf = hashlib.sha256(b"\x00" + canon).digest()
    commit = uuid.uuid5(uuid.NAMESPACE_URL, f"mainline-demo/commit/{permit_id}").bytes * 2
    conn.execute(
        _MERGE_SQL,
        (permit_id, commit, signer, "human", Jsonb(payload), canon, 1, leaf),
    )
    return {"payload": payload, "canon": canon, "commit": commit}


def _clone_twin(
    conn: psycopg.Connection[Any], source: uuid.UUID, twin: dict[str, Any]
) -> list[str]:
    args = {
        "src": source,
        "new": uuid.UUID(twin["permit_id"]),
        "ref": twin["external_ref"],
        "refname": f"refs/permits/{twin['external_ref'].lower()}",
        "run": uuid.UUID(twin["recall_run_id"]),
        "sil": uuid.UUID(twin["silence_receipt_id"]),
        "chk": uuid.UUID(twin["check_id"]),
        "rcpt": uuid.UUID(twin["receipt_id"]),
    }
    trace: list[str] = []
    for label, statement in _TWIN_CLONE:
        cursor = conn.execute(statement, args)
        trace.append(f"{label:24s} rows={cursor.rowcount}")
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"twin {twin['external_ref']}: cloning {label} affected {cursor.rowcount} rows, "
                "not 1. The seeded history is not the shape this plan describes, and a twin "
                "built from a partial copy would be a subject the gate refuses for the wrong "
                "reason."
            )
    return trace


def _sign_disposition(
    conn: psycopg.Connection[Any], twin: dict[str, Any], permit_id: uuid.UUID, site_id: uuid.UUID
) -> uuid.UUID:
    disposition_id = uuid.UUID(twin["disposition_id"])
    signer, cosigner = "demo.signer", "demo.countersigner"
    creds = dict(
        conn.execute(
            "SELECT signer_sub, credential_id FROM mainline.signing_credential "
            "WHERE signer_sub = ANY(%s)",
            ([signer, cosigner],),
        ).fetchall()
    )
    missing = [sub for sub in (signer, cosigner) if sub not in creds]
    if missing:
        raise RuntimeError(
            f"mainline.signing_credential has no row for {missing}. A disposition's "
            "signer_credential_id is a foreign key onto an enrolled credential, and this "
            "capture does not enrol one — the seed does."
        )
    conn.execute(
        _DISPOSITION_SQL,
        (
            disposition_id,
            uuid.UUID(twin["check_id"]),
            uuid.UUID(twin["receipt_id"]),
            permit_id,
            site_id,
            _sha("defeater-vocab"),
            _RATIONALE,
            _sha("evidence", str(disposition_id)),
            signer,
            creds[signer],
            cosigner,
            creds[cosigner],
            _sha("authenticator", str(disposition_id)),
            canonical_json({"challenge": disposition_id.hex, "type": "webauthn.get"}),
            Jsonb({"authorisations": ["ISOLATION_AUTHORITY"]}),
            uuid.uuid5(uuid.NAMESPACE_URL, f"mainline-demo/competency/{disposition_id}"),
            _sha("competency", signer),
        ),
    )
    return disposition_id


_TWIN_NOTE: Final = (
    "OBSERVED, BUT TRANSIENT. Permit {ref} ({permit}) was built inside the capture "
    "transaction as a row-for-row copy of the seeded demo permit {source_ref}, driven "
    "through the same triggers, and the whole transaction was then rolled back — so this "
    "row is NOT in the database now, and the live API answers 404 for it. It exists "
    "because {why} What is not staged is the part that matters: the SQLSTATE, the "
    "constraint name and the message below are CockroachDB's own, taken off psycopg's "
    "Diagnostic object during the capture and filed verbatim at {sql}. Nothing on this "
    "screen was composed by hand."
)

_WHY_DRIFT: Final = (
    "the projection-drift beat needs a subject whose projected counter has been forced to "
    "zero out of band, and the seeded permit's counter reads 1 — two worlds cannot share "
    "one permit id, and a bundle frame is keyed by method and path."
)
_WHY_CLEARED: Final = (
    "the admission beat needs a subject carrying a signed disposition, and the seeded "
    "permit deliberately carries none — that absence is what the first beat refuses on."
)


def capture(  # noqa: PLR0915 - one straight line through the run; splitting it would hide the order
    plan: dict[str, Any],
    dsn: str,
    database: str,
    out: Path,
    *,
    quiet: bool = False,
) -> dict[str, Any]:
    """Run the whole capture and return the evidence record."""
    started = time.perf_counter()
    target = _rewrite_dsn(dsn, database=database)
    bundle = Bundle(out)
    say = (lambda *_a, **_k: None) if quiet else print

    tables = list(plan["persistence_check"]["tables"])
    twins = plan["twins"]
    beats_plan = {beat["name"]: beat for beat in plan["beats"]}

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE demo EvidenceBundle capture",
        "generated_at_utc": rfc3339(),
        "generated_by": "scripts/deploy/capture_demo_bundle.py",
        "plan": "verticals/mainline/apps/console/capture-plan.demo.json",
        "bundle_dir": under_root(out),
        "target": {"database": database, "dsn": _redact(target)},
        "honesty": (
            "No real incident, no real site, no real fatality. Every row behind these "
            "frames is synthetic and corresponds to nobody. See "
            "verticals/mainline/demo/DEMO-HONESTY.md and docs/deploy/replay-fallback.md."
        ),
        "frames": [],
        "omitted": [],
        "beats": [],
        "failures": [],
    }

    # ── OUTSIDE THE TRANSACTION: the fingerprint, the schema head, the BEFORE counts ────
    with psycopg.connect(target, autocommit=True, connect_timeout=30) as probe:
        fingerprint, fingerprint_text = _cluster_fingerprint(probe, database)
        schema_version = _schema_version(probe, database)

        subject = plan["subject"]
        permit_id = uuid.UUID(subject["permit_id"])
        row = probe.execute(
            "SELECT external_ref, site_id, state::STRING, gate_epoch, open_blocking "
            "FROM mainline.permit WHERE permit_id = %s",
            (permit_id,),
        ).fetchone()
        if row is None and subject.get("discover_if_absent"):
            row = probe.execute(
                "SELECT permit_id, external_ref, site_id, state::STRING, gate_epoch, open_blocking "
                "FROM mainline.permit WHERE external_ref = %s LIMIT 1",
                (subject["external_ref"],),
            ).fetchone()
            if row is not None:
                permit_id, row = row[0], row[1:]
        if row is None:
            raise SystemExit(
                f"capture_demo_bundle: no mainline.permit {permit_id} and none with "
                f"external_ref {subject['external_ref']!r} in database {database}. The demo "
                "history is seeded by scripts/deploy/seed_demo.py (w2-cloud-database); this "
                "program captures a database, it does not create one."
            )
        external_ref, site_id, state, gate_epoch, open_blocking = row
        site_code = probe.execute(
            "SELECT site_code FROM mainline.site WHERE site_id = %s", (site_id,)
        ).fetchone()[0]
        check_row = probe.execute(
            "SELECT check_id, clause_uuid, encode(commit_id, 'hex') "
            "FROM mainline.blocking_check WHERE permit_id = %s ORDER BY check_id LIMIT 1",
            (permit_id,),
        ).fetchone()
        receipt_row = probe.execute(
            "SELECT receipt_id FROM mainline.exposure_receipt WHERE permit_id = %s "
            "ORDER BY issued_at DESC LIMIT 1",
            (permit_id,),
        ).fetchone()
        run_row = probe.execute(
            "SELECT run_id FROM mainline_meas.recall_run WHERE permit_id = %s LIMIT 1",
            (permit_id,),
        ).fetchone()
        before = _fingerprint(probe, tables, permit_id)

    evidence["subject"] = {
        "permit_id": str(permit_id),
        "external_ref": external_ref,
        "site_id": str(site_id),
        "site_code": site_code,
        "state": state,
        "gate_epoch": int(gate_epoch),
        "open_blocking": int(open_blocking),
        "blocking_check_id": str(check_row[0]) if check_row else None,
        "clause_uuid": str(check_row[1]) if check_row else None,
        "commit_id": check_row[2] if check_row else None,
        "exposure_receipt_id": str(receipt_row[0]) if receipt_row else None,
        "recall_run_id": str(run_row[0]) if run_row else None,
    }
    evidence["cluster_fingerprint"] = fingerprint
    evidence["schema_version"] = schema_version
    bundle.text("sql/cluster-fingerprint.txt", fingerprint_text)

    expect = plan["subject"].get("expect", {})
    for name, want in expect.items():
        observed_now = {
            "state": state,
            "open_blocking": int(open_blocking),
            "gate_epoch": int(gate_epoch),
        }
        got = observed_now.get(name)
        if name == "dispositions":
            continue
        if got is not None and got != want:
            evidence["failures"].append(
                f"the seeded permit's {name} is {got!r}, the plan expects {want!r}. The "
                "capture continues so the mismatch is visible in the frames rather than "
                "hidden behind an early exit."
            )

    say(f"  subject      {external_ref}  {permit_id}  state={state} open_blocking={open_blocking}")
    say(
        f"  cluster      {fingerprint['product']} {fingerprint['version']}  "
        f"region={fingerprint['region']}"
    )

    # ── THE CAPTURE TRANSACTION ────────────────────────────────────────────────────────
    attempt_records: list[dict[str, Any]] = []

    def run_once(attempt: int) -> None:  # noqa: PLR0912, PLR0915 - the beats ARE the
        # branches, and they run in one order for one reason. Splitting this into four
        # functions would put the savepoint discipline in four places and the order they
        # must run in nowhere.
        # Everything except the cluster fingerprint (read outside the transaction) is
        # rebuilt from scratch on a retry. A 40001 retry that kept half the frames of the
        # aborted attempt would produce a bundle describing two different moments.
        bundle.files = {k: v for k, v in bundle.files.items() if k == "sql/cluster-fingerprint.txt"}
        bundle.frames.clear()
        evidence["frames"] = []
        evidence["omitted"] = []
        evidence["beats"] = []
        epochs: dict[str, int] = {}

        with psycopg.connect(target, autocommit=False, connect_timeout=30) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            opened_ts = conn.execute("SELECT cluster_logical_timestamp()::STRING").fetchone()[0]

            def capture_read(
                resource: str,
                path: dict[str, str],
                query: dict[str, str] | None = None,
                *,
                required: bool,
                staged_note: str | None = None,
            ) -> dict[str, Any] | None:
                """One read, filed as a frame, or an omission with its reason.

                Wrapped in its own savepoint because a statement that raises aborts the
                CockroachDB transaction, and a read that declines must not take the beats
                down with it. `40001` is re-raised: that is the transaction's business, not
                this read's.
                """
                query = query or {}
                conn.execute("SAVEPOINT ctx")
                try:
                    payload, elapsed = _read_context(conn, resource, path, query)
                except psycopg.Error as exc:
                    conn.execute("ROLLBACK TO SAVEPOINT ctx")
                    conn.execute("RELEASE SAVEPOINT ctx")
                    if sqlstate_of(exc) == RETRYABLE:
                        raise
                    reason = f"psycopg.Error {sqlstate_of(exc)}: {one_line(exc)}"
                    payload = None
                except _reads.ReadError as exc:
                    conn.execute("ROLLBACK TO SAVEPOINT ctx")
                    conn.execute("RELEASE SAVEPOINT ctx")
                    reason = f"{type(exc).__name__} ({exc.status}): {exc.detail}"
                    payload = None
                else:
                    conn.execute("RELEASE SAVEPOINT ctx")
                    if staged_note is not None:
                        payload["staged"] = True
                        payload["staged_note"] = staged_note
                    bundle.frame(
                        resource=resource, payload=payload, status=200, path=path,
                        query=query, duration_ms=elapsed, via="python-call", source="sql",
                    )
                    say(
                        f"  read         {resource:18s} {path.get('permit_id', '')[:8]:8s} "
                        f"{'STAGED' if payload.get('staged') else 'observed'}"
                    )
                    return payload

                evidence["omitted"].append(
                    {"resource": resource, "path": path, "query": query,
                     "reason": reason, "required": required}
                )
                say(f"  omitted      {resource:18s} {reason[:80]}")
                if required:
                    evidence["failures"].append(
                        f"required read {resource!r} produced no frame: {reason}"
                    )
                return None

            # ── context reads, on the seeded permit ───────────────────────────────────
            addresses: dict[str, tuple[dict[str, str], dict[str, str]]] = {
                "permit": ({"permit_id": str(permit_id)}, {}),
                "blocking_checks": ({"permit_id": str(permit_id)}, {}),
                "silence": ({"permit_id": str(permit_id)}, {}),
                "audit": ({}, {}),
                "ledger": ({}, {"site_code": site_code}),
            }
            if check_row is not None:
                addresses["disposition"] = ({"check_id": str(check_row[0])}, {})
                addresses["clause_version"] = (
                    {"clause_uuid": str(check_row[1]), "commit_id": check_row[2]}, {}
                )
                addresses["clause_ancestry"] = (
                    {"clause_uuid": str(check_row[1])}, {"as_of": check_row[2]}
                )
            if receipt_row is not None:
                addresses["exposure_receipt"] = ({"receipt_id": str(receipt_row[0])}, {})
            if run_row is not None:
                addresses["recall_run"] = ({"run_id": str(run_row[0])}, {})

            for step in plan["context"]:
                resource = step["resource"]
                required = bool(step.get("required"))
                if resource not in addresses:
                    evidence["omitted"].append(
                        {
                            "resource": resource,
                            "reason": (
                                "no row in the seeded history addresses this resource, so "
                                "there is nothing to read. No frame was written; a frame "
                                "here would have had to be invented."
                            ),
                            "required": required,
                        }
                    )
                    if required:
                        evidence["failures"].append(
                            f"required context read {resource!r} could not be addressed."
                        )
                    continue
                path, query = addresses[resource]
                payload = capture_read(resource, path, query, required=required)
                if resource == "permit" and payload is not None:
                    epochs["seeded"] = int(payload["data"]["gate_epoch"])

            seeded_epoch = epochs.get("seeded", int(gate_epoch))

            # ── BEAT 2 · the seeded permit, one obligation open ───────────────────────
            beat = beats_plan["refusal"]
            conn.execute("SAVEPOINT beat_2")
            started_beat = time.perf_counter()
            try:
                _call_merge(conn, permit_id, "demo.signer")
            except psycopg.Error as exc:
                if sqlstate_of(exc) == RETRYABLE:
                    raise
                # ROLLBACK TO SAVEPOINT, not ROLLBACK: the transaction survives a
                # constraint refusal and keeps taking statements, which is what lets the
                # refusal payload read the rows the refusal points at.
                conn.execute("ROLLBACK TO SAVEPOINT beat_2")
                _file_refusal(
                    bundle, conn, evidence, beat, permit_id, seeded_epoch, exc,
                    elapsed=(time.perf_counter() - started_beat) * 1000.0,
                    staged=False, staged_note=None, database=database,
                    statement=_MERGE_SQL, extra_statement=None, say=say,
                )
            else:
                conn.execute("ROLLBACK TO SAVEPOINT beat_2")
                evidence["failures"].append(
                    "beat 2 was ADMITTED with an open obligation — the gate did not hold. "
                    "No frame was written for it: a bundle that shows the gate admitting "
                    "what it must refuse is not a demo, it is a bug report."
                )
            conn.execute("RELEASE SAVEPOINT beat_2")

            # ── BEAT 3 · THE ATTACK, on the drift twin ───────────────────────────────
            beat = beats_plan["projection_drift_attack"]
            twin = twins["drift"]
            drift_permit = uuid.UUID(twin["permit_id"])
            drift_note = _TWIN_NOTE.format(
                ref=twin["external_ref"], permit=drift_permit, source_ref=external_ref,
                why=_WHY_DRIFT, sql=f"sql/{beat['sql_name']}.txt",
            )
            conn.execute("SAVEPOINT beat_3")
            trace = _clone_twin(conn, permit_id, twin)
            conn.execute(_FORCE_SQL, (drift_permit,))
            forged = conn.execute(
                "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s", (drift_permit,)
            ).fetchone()[0]
            derived = conn.execute(
                "SELECT count(*) FROM mainline.blocking_check bc WHERE bc.permit_id = %s "
                "AND NOT EXISTS (SELECT 1 FROM mainline.disposition d "
                "WHERE d.check_id = bc.check_id AND d.retracted_by IS NULL "
                "AND (d.expires_at IS NULL OR d.expires_at > now()))",
                (drift_permit,),
            ).fetchone()[0]
            bundle.text(
                "sql/twin-construction.txt",
                round_trip_text(
                    title="Twin construction — the two transient subjects, and what built them",
                    connection=f"database {database}",
                    transaction=(
                        "inside the capture transaction, under SAVEPOINT; rolled back with "
                        "everything else"
                    ),
                    statement="\n".join(sql.strip() for _label, sql in _TWIN_CLONE),
                    parameters=[
                        f"src     = {permit_id}   ({external_ref}, the seeded permit)",
                        (
                            f"drift   = {twins['drift']['permit_id']}   "
                            f"({twins['drift']['external_ref']})"
                        ),
                        (
                            f"cleared = {twins['cleared']['permit_id']}   "
                            f"({twins['cleared']['external_ref']})"
                        ),
                    ],
                    outcome="OK",
                    sqlstate="00000",
                    constraint=None,
                    constraint_source=None,
                    message="",
                    detail="",
                    hint="",
                    stdout="\n".join(trace),
                    driver=f"psycopg {psycopg.__version__}",
                    note=(
                        "Every statement is INSERT ... SELECT from the seeded rows, so a twin "
                        "is a copy of what is in the database rather than a second opinion "
                        "about it. No statement sets a counter: inserting the blocking check "
                        "fires check_materialised, which increments open_blocking and bumps "
                        "gate_epoch, and severity/virulence/closure_gen are overwritten by "
                        "fn_check_project from mainline.clause_blame_current (invariant MI25). "
                        "Both twins were rolled back; neither is in the database now."
                    ),
                ),
            )
            # Read the twin WITH the counter already forged. This is the screen the demo
            # exists for: permit.open_blocking reads 0 while blocking_checks still lists an
            # open obligation, and the gate refuses anyway.
            drift_payload = capture_read(
                "permit", {"permit_id": str(drift_permit)}, required=True, staged_note=drift_note
            )
            capture_read(
                "blocking_checks", {"permit_id": str(drift_permit)},
                required=True, staged_note=drift_note,
            )
            drift_epoch = (
                int(drift_payload["data"]["gate_epoch"]) if drift_payload else seeded_epoch
            )

            started_beat = time.perf_counter()
            conn.execute("SAVEPOINT beat_3_merge")
            try:
                _call_merge(conn, drift_permit, "demo.signer")
            except psycopg.Error as exc:
                if sqlstate_of(exc) == RETRYABLE:
                    raise
                # Back to beat_3_merge, NOT to beat_3: the twin must still exist while the
                # refusal payload reads the obligation the refusal names.
                conn.execute("ROLLBACK TO SAVEPOINT beat_3_merge")
                _file_refusal(
                    bundle, conn, evidence, beat, drift_permit, drift_epoch, exc,
                    elapsed=(time.perf_counter() - started_beat) * 1000.0,
                    staged=True, staged_note=drift_note, database=database,
                    statement=_MERGE_SQL,
                    extra_statement=(
                        f"{_FORCE_SQL}\n"
                        f"-- open_blocking forced to {forged}; the count re-derived from "
                        f"blocking_check LEFT JOIN disposition is {derived}"
                    ),
                    say=say,
                )
            else:
                conn.execute("ROLLBACK TO SAVEPOINT beat_3_merge")
                evidence["failures"].append(
                    "beat 3 was ADMITTED against a forged counter — the gate trusted its own "
                    "projection, which is the one thing it must never do. No frame written."
                )
            conn.execute("RELEASE SAVEPOINT beat_3_merge")
            conn.execute("ROLLBACK TO SAVEPOINT beat_3")
            conn.execute("RELEASE SAVEPOINT beat_3")

            # ── BEAT 4 · THE ADMISSION, on the cleared twin ──────────────────────────
            beat = beats_plan["admission"]
            twin = twins["cleared"]
            cleared_permit = uuid.UUID(twin["permit_id"])
            cleared_note = _TWIN_NOTE.format(
                ref=twin["external_ref"], permit=cleared_permit, source_ref=external_ref,
                why=_WHY_CLEARED, sql=f"sql/{beat['sql_name']}.txt",
            )
            conn.execute("SAVEPOINT beat_4")
            _clone_twin(conn, permit_id, twin)
            disposition_id = _sign_disposition(conn, twin, cleared_permit, site_id)
            closed = conn.execute(
                "SELECT open_blocking FROM mainline.permit WHERE permit_id = %s", (cleared_permit,)
            ).fetchone()[0]
            # Read the twin AFTER the signature and BEFORE the merge — the order a reader
            # drives the screen in. A read taken after the merge would describe a merged
            # permit and the attempt control would have nothing left to do.
            cleared_payload = capture_read(
                "permit", {"permit_id": str(cleared_permit)},
                required=True, staged_note=cleared_note,
            )
            capture_read(
                "blocking_checks", {"permit_id": str(cleared_permit)},
                required=True, staged_note=cleared_note,
            )
            capture_read(
                "disposition", {"check_id": twin["check_id"]},
                required=False, staged_note=cleared_note,
            )
            cleared_epoch = (
                int(cleared_payload["data"]["gate_epoch"]) if cleared_payload else seeded_epoch
            )

            started_beat = time.perf_counter()
            conn.execute("SAVEPOINT beat_4_merge")
            try:
                _call_merge(conn, cleared_permit, "demo.signer")
            except psycopg.Error as exc:
                if sqlstate_of(exc) == RETRYABLE:
                    raise
                conn.execute("ROLLBACK TO SAVEPOINT beat_4_merge")
                evidence["failures"].append(
                    f"beat 4 was REFUSED [{sqlstate_of(exc)}] {one_line(exc)}. A gate that "
                    "always refuses is broken, not safe, and this beat is the only thing "
                    "that proves ours is not."
                )
            else:
                record = conn.execute(_MERGE_RECORD_SQL, (cleared_permit,)).fetchone()
                elapsed = (time.perf_counter() - started_beat) * 1000.0
                committed = {
                    "merged_commit": record[0] if record else None,
                    "merged_at": rfc3339(record[1]) if record else rfc3339(),
                    "clearance_digest": record[2] if record else None,
                    "checkpoint_tree_size": None,
                    "ledger_seq": None,
                }
                data = _transitions._invoke(
                    MERGE_PROCEDURE, 200, "committed", str(cleared_permit),
                    int(record[3]) if record else cleared_epoch, committed=committed,
                )
                data["sql_round_trip"] = f"sql/{beat['sql_name']}.txt"
                payload = _transitions._envelope(
                    "merge_permit", INVOKE_SCHEMA_ID, data,
                    staged=True, staged_note=cleared_note,
                    statement_refs=[
                        _transitions._ref("procedure", "mainline.merge_permit"),
                        _transitions._ref("table", "mainline.merge_record"),
                    ],
                    provenance=list(_transitions._COMMITTED_PROVENANCE),
                )
                bundle.frame(
                    resource="merge_permit", payload=payload, status=200,
                    path={"permit_id": str(cleared_permit)},
                    body={
                        "subject_kind": "permit",
                        "subject_id": str(cleared_permit),
                        "expected_gate_epoch": cleared_epoch,
                    },
                    duration_ms=elapsed, via="python-call", source="sql",
                )
                bundle.text(
                    f"sql/{beat['sql_name']}.txt",
                    round_trip_text(
                        title=f"Beat {beat['ordinal']} · {beat['label']}",
                        connection=f"database {database}",
                        transaction=(
                            "one SERIALIZABLE transaction; SAVEPOINT beat_4 / beat_4_merge … "
                            "ROLLBACK TO SAVEPOINT; the whole transaction then rolled back"
                        ),
                        statement=f"{' '.join(_DISPOSITION_SQL.split())};\n{_MERGE_SQL}",
                        parameters=[
                            f"permit_id        = {cleared_permit}",
                            f"disposition_id   = {disposition_id}",
                            f"check_id         = {twin['check_id']}",
                            f"receipt_id       = {twin['receipt_id']}",
                            f"canonicalisation = {canonicalisation_name()}",
                        ],
                        outcome="ADMITTED",
                        sqlstate="00000",
                        constraint=None,
                        constraint_source=None,
                        message="",
                        detail="",
                        hint="",
                        stdout=(
                            f"open_blocking after the signature = {closed}\n"
                            f"merge_record.merged_commit        = {committed['merged_commit']}\n"
                            f"merge_record.clearance_digest     = {committed['clearance_digest']}\n"
                            f"merge_record.gate_epoch           = {data['gate_epoch']}\n"
                            f"merge_record.merged_at            = {committed['merged_at']}"
                        ),
                        driver=f"psycopg {psycopg.__version__}",
                        note=(
                            "A gate that always refuses is broken, not safe. The clearance "
                            "digest was computed by the SERVER over the sorted "
                            "(check_id, disposition_id) set; this program supplied none of it. "
                            "The merge_record row was read back inside the savepoint and then "
                            "undone with it."
                        ),
                    ),
                )
                evidence["beats"].append(
                    {
                        "ordinal": beat["ordinal"], "name": beat["name"],
                        "subject": str(cleared_permit), "outcome": "committed",
                        "sqlstate": "00000", "constraint": None, "constraint_source": None,
                        "expected": beat["expect"], "matched_expectation": True,
                        "sql_round_trip": f"sql/{beat['sql_name']}.txt",
                        "clearance_digest": committed["clearance_digest"],
                        "open_blocking_after_signature": int(closed),
                        "elapsed_ms": round(elapsed, 3),
                    }
                )
                say(
                    f"  beat 4       ADMITTED [00000]  "
                    f"clearance_digest={committed['clearance_digest']}"
                )
                conn.execute("ROLLBACK TO SAVEPOINT beat_4_merge")
            conn.execute("RELEASE SAVEPOINT beat_4_merge")
            conn.execute("ROLLBACK TO SAVEPOINT beat_4")
            conn.execute("RELEASE SAVEPOINT beat_4")

            closed_ts = conn.execute("SELECT cluster_logical_timestamp()::STRING").fetchone()[0]
            evidence["transaction"] = {
                "isolation": "SERIALIZABLE",
                "disposition": "rolled_back",
                "opened_logical_timestamp": opened_ts,
                "closed_logical_timestamp": closed_ts,
                # cluster_logical_timestamp() is constant within a CockroachDB transaction
                # and moves between them. Equal endpoints are a READ-ONLY witness that every
                # beat shared one transaction — not an assertion this program makes about
                # itself.
                "single_transaction": opened_ts == closed_ts,
                "savepoints": [
                    "beat_2", "beat_3", "beat_3_merge", "beat_4", "beat_4_merge", "ctx",
                ],
                "attempt": attempt,
            }
            # THE WHOLE TRANSACTION GOES BACK, including the beat that succeeded.
            conn.rollback()

    # The retry wraps the WHOLE transaction: the retry unit of a serializable transaction is
    # the transaction, and re-running one statement of an aborted one is how a caller gets
    # 25P02. See docs/leads/deploy-plan.md §1.2 for the run this exists because of.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            run_once(attempt)
            break
        except psycopg.Error as exc:
            if sqlstate_of(exc) != RETRYABLE:
                raise
            attempt_records.append(
                {"attempt": attempt, "sqlstate": RETRYABLE, "message": one_line(exc)}
            )
            say(f"  retry        attempt {attempt} hit 40001; backing off")
            if attempt == MAX_ATTEMPTS:
                raise Undecided(one_line(exc)) from exc
            time.sleep(random.uniform(0, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))))  # noqa: S311
    evidence["retries"] = attempt_records

    # ── OUTSIDE THE TRANSACTION AGAIN: prove nothing persisted ─────────────────────────
    with psycopg.connect(target, autocommit=True, connect_timeout=30) as probe:
        after = _fingerprint(probe, tables, permit_id)
    identical = before == after
    evidence["persistence_check"] = {
        "before": before,
        "after": after,
        "identical": identical,
        "tables": tables,
        "note": (
            "Row counts over every table the beats can write, taken on a separate "
            "autocommit connection BEFORE the capture transaction opened and AFTER it was "
            "rolled back, plus mainline.permit's own column values — because the drift beat "
            "mutates a column without changing a count."
        ),
    }
    if not identical:
        evidence["failures"].append(
            "the capture PERSISTED something: the affected tables are not identical before "
            "and after. The bundle must not be published."
        )
    bundle.text(
        "sql/persistence-check.txt",
        round_trip_text(
            title="Persistence check — the capture mutated nothing",
            connection=f"database {database}",
            transaction="autocommit, outside the capture transaction, before and after",
            statement=_counts_statement(tables)
            + "\n" + _PERMIT_ROW_SQL.strip(),
            parameters=[f"permit_id = {permit_id}"],
            outcome="IDENTICAL" if identical else "CHANGED",
            sqlstate="00000",
            constraint=None,
            constraint_source=None,
            message="",
            detail="",
            hint="",
            stdout="before:\n"
            + json.dumps(before, indent=2, default=str)
            + "\n\nafter:\n"
            + json.dumps(after, indent=2, default=str),
            driver=f"psycopg {psycopg.__version__}",
            note=(
                "The demo needs no per-visitor state, no reset button, no session table and "
                "no cleanup sweeper, because the transition beats roll back. This block is "
                "the check on that claim rather than the claim itself."
            ),
        ),
    )

    # ── the manifest seed, and the bundle on disk ──────────────────────────────────────
    manifest_seed = dict(plan["manifest"])
    manifest_seed.pop("checkpoint_note", None)
    manifest_seed.pop("$comment", None)
    manifest_seed["captured_at"] = rfc3339()
    manifest_seed["cluster_fingerprint"] = fingerprint
    manifest_seed["schema_version"] = schema_version
    staged_frames = [f for f in bundle.frames if f["staged"]]
    if staged_frames and manifest_seed.get("staged") is not True:
        # The manifest flag is bundle-wide and the schema makes it mean "any frame here is
        # not a plain observation". Two frames carry transaction-local subjects, so it is
        # true, and saying so costs a badge rather than a claim.
        manifest_seed["staged"] = True
        manifest_seed["staged_note"] = (
            "Captured from a live CockroachDB cluster: every SQLSTATE, constraint name, "
            "counter and digest in this bundle was produced by the database during the "
            "capture, and nothing in it was hand-authored. It is flagged STAGED because "
            f"{len(staged_frames)} of {len(bundle.frames)} frames describe two TRANSIENT "
            "subjects — permits DEMO-PTW-0002 and DEMO-PTW-0003 — which were built inside "
            "the capture transaction as copies of the seeded permit DEMO-PTW-0001 and "
            "rolled back with it. Those rows are not in the database now. They exist "
            "because the drift beat and the admission beat each need a different world "
            "from the one the seeded permit is in, and a bundle frame is keyed by method "
            "and path, so three worlds need three permit ids. Each such frame carries its "
            "own note saying the same thing. See docs/deploy/replay-fallback.md §4."
        )
    bundle.write(manifest_seed)

    evidence["frames"] = bundle.frames
    evidence["frame_count"] = len(bundle.frames)
    evidence["file_count"] = len(bundle.files)
    evidence["total_bytes"] = bundle.total_bytes
    evidence["manifest_seed"] = manifest_seed
    evidence["canonicalisation"] = canonicalisation_name()
    evidence["total_seconds"] = round(time.perf_counter() - started, 1)
    return evidence


def _file_refusal(
    bundle: Bundle,
    conn: psycopg.Connection[Any],
    evidence: dict[str, Any],
    beat: dict[str, Any],
    subject: uuid.UUID,
    gate_epoch: int,
    exc: psycopg.Error,
    *,
    elapsed: float,
    staged: bool,
    staged_note: str | None,
    database: str,
    statement: str,
    extra_statement: str | None,
    say: Any = print,
) -> None:
    """Turn one driver exception into a frame, a round trip and an evidence row.

    Nothing here composes a message. ``diagnose`` reads psycopg's ``Diagnostic``;
    ``refusal_payload`` is the live API's own builder and reads the rows the refusal
    points at. If ``classify`` says this is not a refusal, the beat FAILS — an SQLSTATE
    outside the taxonomy is a defect to be reported, not an edge case to be smoothed over.
    """
    found = _refusal.diagnose(exc)
    kind = _refusal.classify(found)
    expected = beat["expect"]
    sql_rel = f"sql/{beat['sql_name']}.txt"

    if kind != "refused":
        evidence["failures"].append(
            f"beat {beat['ordinal']} ({beat['name']}): SQLSTATE {found.sqlstate or '(none)'} "
            f"classified {kind!r}, not a refusal: {found.message}. No frame written."
        )
        return

    payload = _refusal.refusal_payload(
        conn, found, subject_kind="permit", subject_id=str(subject),
        gate_epoch=gate_epoch, attempt={"kind": "merge", "gate_epoch": gate_epoch},
    )
    data = _transitions._invoke(
        MERGE_PROCEDURE, 409, "refused", str(subject),
        int(payload.get("gate_epoch", gate_epoch)), refusal=payload,
    )
    data["sql_round_trip"] = sql_rel
    envelope = _transitions._envelope(
        "merge_permit", INVOKE_SCHEMA_ID, data,
        staged=staged, staged_note=staged_note,
        statement_refs=[_transitions._ref("procedure", "mainline.merge_permit")],
        provenance=list(_transitions._REFUSAL_PROVENANCE),
    )
    bundle.frame(
        resource="merge_permit", payload=envelope, status=409,
        path={"permit_id": str(subject)},
        body={
            "subject_kind": "permit",
            "subject_id": str(subject),
            "expected_gate_epoch": gate_epoch,
        },
        duration_ms=elapsed, via="python-call", source="sql",
    )
    matched = (
        found.sqlstate == expected["sqlstate"]
        and (expected["exhibit"] is None or found.constraint == expected["exhibit"])
        and (expected["constraint_source"] is None
             or found.constraint_source == expected["constraint_source"])
    )
    bundle.text(
        sql_rel,
        round_trip_text(
            title=f"Beat {beat['ordinal']} · {beat['label']}",
            connection=f"database {database}",
            transaction=f"one SERIALIZABLE transaction; SAVEPOINT beat_{beat['ordinal']} … "
            f"ROLLBACK TO SAVEPOINT beat_{beat['ordinal']}; the whole transaction rolled back",
            statement=(f"{extra_statement}\n{statement}" if extra_statement else statement),
            parameters=[
                f"permit_id        = {subject}",
                f"gate_epoch       = {gate_epoch}",
                f"canonicalisation = {canonicalisation_name()}",
            ],
            outcome="REFUSED",
            sqlstate=found.sqlstate or "(none)",
            constraint=found.constraint or None,
            constraint_source=found.constraint_source,
            message=found.message,
            detail=getattr(found, "detail", "") or "",
            hint=getattr(found, "hint", "") or "",
            stdout="",
            driver=(
                f"psycopg {psycopg.__version__} — Diagnostic.sqlstate, "
                "Diagnostic.constraint_name, Diagnostic.message_primary. "
                f"constraint_source={found.constraint_source!r}: 'reported' means the driver "
                "handed us the name; 'parsed' means it was read out of the message the "
                "procedure raised, because PL/pgSQL RAISE carries no constraint field."
            ),
            note=beat["why"],
        ),
    )
    evidence["beats"].append(
        {
            "ordinal": beat["ordinal"], "name": beat["name"], "subject": str(subject),
            "outcome": "refused", "sqlstate": found.sqlstate,
            "constraint": found.constraint or None,
            "constraint_source": found.constraint_source,
            "expected": expected, "matched_expectation": matched,
            "sql_round_trip": sql_rel, "elapsed_ms": round(elapsed, 3),
        }
    )
    if not matched:
        evidence["failures"].append(
            f"beat {beat['ordinal']} ({beat['name']}): expected {expected}, observed "
            f"sqlstate={found.sqlstate!r} constraint={found.constraint!r} "
            f"constraint_source={found.constraint_source!r}"
        )
    say(
        f"  beat {beat['ordinal']}       REFUSED [{found.sqlstate}] "
        f"{found.constraint or '(no exhibit)'}  ({found.constraint_source})"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# seal and check — capture-bundle.ts, unchanged, and the run fails if they disagree
# ═══════════════════════════════════════════════════════════════════════════════════════


def _node(mode: str, out: Path, node: str) -> tuple[int, str]:
    script = CONSOLE / "scripts" / "capture-bundle.ts"
    rel = os.path.relpath(out, CONSOLE).replace("\\", "/")
    proc = subprocess.run(
        [node, str(script), mode, "--dir", rel],
        cwd=str(CONSOLE), capture_output=True, text=True, check=False,
        # node writes UTF-8; the default here is the Windows ANSI code page, which turns
        # every em dash in capture-bundle.ts's own output into mojibake in the evidence.
        encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def seal_and_check(out: Path, node: str, evidence: dict[str, Any]) -> bool:
    """``seal`` writes manifest.json; ``check`` re-derives every digest and must agree."""
    code, output = _node("seal", out, node)
    evidence["seal"] = {"exit_code": code, "output": output}
    print(f"  seal         {output}")
    if code != 0:
        evidence["failures"].append(f"capture-bundle.ts seal failed ({code}): {output}")
        return False

    code, output = _node("check", out, node)
    evidence["check"] = {"exit_code": code, "output": output}
    print(f"  check        {output}")
    if code != 0:
        evidence["failures"].append(f"capture-bundle.ts check failed ({code}): {output}")
        return False

    manifest_path = out / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    evidence["manifest_digest"] = hashlib.sha256(manifest_bytes).hexdigest()
    evidence["manifest_bytes"] = len(manifest_bytes)
    evidence["manifest_files"] = len(manifest["files"])

    # The manifest digest is what the honesty chrome shows and what a reader re-derives
    # with `sha256sum manifest.json`. Recomputing every listed digest here as well is a
    # second, independent implementation of `check` — a producer that only trusts its own
    # checker has one implementation, not a check.
    disagreements = []
    for entry in manifest["files"]:
        path = out.joinpath(*entry["path"].split("/"))
        if not path.is_file():
            disagreements.append(f"{entry['path']}: listed, missing on disk")
            continue
        data = path.read_bytes()
        if len(data) != entry["bytes"]:
            disagreements.append(f"{entry['path']}: {entry['bytes']} declared, {len(data)} on disk")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            disagreements.append(f"{entry['path']}: sha256 disagrees")
    evidence["independent_digest_check"] = {
        "implementation": "hashlib.sha256 in capture_demo_bundle.py",
        "files": len(manifest["files"]),
        "disagreements": disagreements,
    }
    if disagreements:
        evidence["failures"].extend(disagreements)
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════════════
# entry point
# ═══════════════════════════════════════════════════════════════════════════════════════


def under_root(path: Path) -> str:
    """Repo-relative when it is inside the repository, absolute when it is not.

    ``--evidence`` and ``--out`` are allowed to point anywhere — a rehearsal writes its
    evidence to a scratch directory — and a path this program cannot make relative is not
    a reason to fail after the capture has already succeeded.
    """
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def summarise(evidence: dict[str, Any]) -> None:
    print()
    fp = evidence["cluster_fingerprint"]
    print(f"cluster       {fp['product']} {fp['version']}  "
          f"({fp['source']}, {fp['region']})")
    print(f"database      {evidence['target']['database']}")
    subject = evidence["subject"]
    print(f"subject       {subject['external_ref']}  {subject['permit_id']}")
    for beat in evidence["beats"]:
        mark = "OK " if beat["matched_expectation"] else "!! "
        exhibit = beat.get("constraint") or beat.get("clearance_digest") or ""
        print(f"beat {beat['ordinal']}        {mark}{beat['outcome'].upper():9s} "
              f"[{beat['sqlstate']}] {exhibit}")
    print(f"frames        {evidence.get('frame_count', 0)} "
          f"({sum(1 for f in evidence.get('frames', []) if f['staged'])} staged)")
    print(f"bytes         {evidence.get('total_bytes', 0)}")
    print(f"manifest      sha256 {evidence.get('manifest_digest', '(not sealed)')}")
    persisted = "nothing" if evidence["persistence_check"]["identical"] else "SOMETHING CHANGED"
    print(f"persisted     {persisted}")
    for failure in evidence["failures"]:
        print(f"FAILURE       {failure}")
    print(f"VERDICT       {evidence['verdict']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capture_demo_bundle",
        description=(
            "Capture the Phase-1 demo EvidenceBundle from a CockroachDB database, seal it "
            "with capture-bundle.ts, check it, and prove the capture persisted nothing."
        ),
    )
    parser.add_argument("--dsn", default=None, help="DSN (default: COCKROACH_DSN from .env)")
    parser.add_argument("--database", default=DEFAULT_DATABASE, help="target database")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--node", default="node", help="node executable (v24+ strips types)")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252, and this program prints the constraint names and
    # messages the database gave it — which contain em dashes and arrows. Re-encoding the
    # stream is the fix; stripping the characters out of the messages would be editing
    # evidence to suit a terminal.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    load_dotenv(ROOT)
    args = build_parser().parse_args(argv)
    args.dsn = args.dsn or os.environ.get("COCKROACH_DSN")
    if not args.dsn:
        print(
            "capture_demo_bundle: no DSN. Pass --dsn, or put COCKROACH_DSN in the repo-root "
            ".env.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not args.plan.is_file():
        print(f"capture_demo_bundle: no plan at {args.plan}", file=sys.stderr)
        return EXIT_USAGE

    _assert_resources_agree()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))

    print(f"capture_demo_bundle: {args.database} → {under_root(args.out)}")
    try:
        evidence = capture(plan, args.dsn, args.database, args.out, quiet=args.quiet)
    except Undecided as stop:
        print(
            f"capture_demo_bundle: UNDECIDED after {MAX_ATTEMPTS} attempts ({RETRYABLE}): "
            f"{stop}. That is not a refusal — the gate never got to say anything — and no "
            "bundle was written.",
            file=sys.stderr,
        )
        return EXIT_UNDECIDED
    except psycopg.OperationalError as exc:
        print(f"capture_demo_bundle: could not reach the cluster: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE

    sealed = seal_and_check(args.out, args.node, evidence)
    evidence["verdict"] = (
        "CAPTURED AND VERIFIED"
        if sealed and not evidence["failures"]
        else "NOT VERIFIED"
    )
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    summarise(evidence)
    print(f"evidence      {under_root(args.evidence)}")
    return EXIT_OK if evidence["verdict"] == "CAPTURED AND VERIFIED" else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
