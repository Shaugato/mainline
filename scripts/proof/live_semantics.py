#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Six memory semantics, each proven to be a live anonymous GET, by seven GETs and nothing else.

WHY THIS FILE EXISTS
====================
The Official Rules say the Project *"must function as depicted in the video and/or expressed in
the text description"*. `README.md`, `docs/submission/DEVPOST.md` and
`docs/submission/JUDGING-AXES.md` are about to say that this system's memory has *semantics* —
provenance, ancestry, severity floors, logged silence, retrieval accounting, exposure — and that
each one is a **live, anonymous `GET`** a stranger can press. That sentence is true. This program
is what makes it **demonstrable**: it presses all six, records what came back, and asserts the
exact field each sentence leans on. If a field moves, the verdict here goes ``NOT PROVEN`` and
this artefact names the sentence that must be edited before the submission goes out.

It is the standing re-derivation of `docs/submission/extra-credit-plan.md` §2 EC-2. That table
was measured by hand on 2026-08-16; this file is the program that measures it again on demand.

WHAT IT SENDS. SEVEN GETS, AND THE TRANSCRIPT ASSERTS IT
========================================================
``GET /v1/demo/subjects`` · ``GET /v1/health`` · ``GET /v1/clauses/{clause_uuid}/ancestry`` ·
``GET /v1/permits/{permit_id}/blocking-checks`` · ``GET /v1/recall-runs/{run_id}`` ·
``GET /v1/permits/{permit_id}/silence`` · ``GET /v1/receipts/{receipt_id}``

**No ``POST``. No ``PUT``. No ``DELETE``. No write of any kind, of any shape, ever.** Not even
``POST /v1/demo/gate-run``, which is safe and which the sibling transcript
`scripts/proof/live_beats.py` owns; the *act* half of the loop is that file's claim and not this
one's. The request list this program actually built is asserted against that rule in
``request_discipline`` before any verdict is printed, so the sentence above is checked rather
than promised.

It reads **no credential**, no DSN, no AWS profile, no environment variable and no SSM parameter,
and it sends no header but ``accept``. There is therefore nothing in this transcript to redact,
which is why — unlike ``live_beats.py`` — it runs no masker: a masking pass over a document that
cannot contain a secret is theatre, and theatre in an evidence pipeline teaches its reader to
stop looking.

WHAT THIS PROGRAM CONTRIBUTES, STATED PRECISELY — AND HOW IT DIFFERS FROM ``memory_loop.py``
============================================================================================
``scripts/proof/memory_loop.py`` contributes **addresses only** and audits itself to prove no
measured value came out of its own source. This program deliberately contributes one more thing,
and says so on its own face rather than borrowing that stronger claim:

* **Identifiers — none.** Every subject is resolved from ``GET /v1/demo/subjects``, which answers
  entirely out of ``SELECT``s. There is no UUID literal in this file and ``source_audit`` counts
  them to prove it. ``--base-url`` is required for the same reason: a default origin here would
  be a value in the artefact that came from the artefact's own producer.
* **Expectations — yes, on purpose.** :data:`CLAIMS` carries the literal values the submission
  copy states, each tagged with ``says_who`` naming the document that states it. That is the
  point of a guard: ``live_beats.py`` asserts its four SQLSTATEs from a constant rather than
  reading them off the server's own verdict, for the same reason. A checker that only records
  what it was told cannot go red, and a check that cannot fail is decoration
  (``docs/regression/GUARD.md``).

So the honest one-line claim is: **this file writes down what the copy says and asks the
deployment whether it is still true.** It does not, and must not, claim that no value in the
artefact originates here.

RULING R4 — THE SILENCE LEDGER IS EMPTY, AND THAT IS MECHANISED HERE
====================================================================
``docs/submission/extra-credit-plan.md`` R4. ``GET /v1/permits/{permit_id}/silence`` returns a
**complete** Merkle receipt — ``corpus_root``, ``candidate_root``, ``theta``, ``s``, ``n``, a
boundary proof — **and an empty ``entries`` list**. The apparatus is live; the list is empty.
This program does not merely note that: it counts the entries, reads
``counts.n_silenced`` off a *different* response, and asserts the two agree. Two endpoints
agreeing about a withholding count is a fact about the database; one endpoint asserting it is a
fact about one reader. See :data:`R4_SENTENCE`, which is written into the artefact verbatim.

RULING R5 — THE ``staged`` FLAG IS QUOTED, NEVER TRIMMED
========================================================
Every envelope on this API carries a ``provenance`` array of per-field chips (``db:column``,
``derived``, ``staged``) and a top-level ``staged`` flag with a ``staged_note``. The silence
payload answers ``staged: true`` and its note names ``receipt.bound.statement`` as the single
value in that response that no database column produced. This program records the whole chip
array for every response and asserts that exactly one of the six envelopes claims ``staged``.
A payload that flags its own non-column field is rarer than the receipt itself.

WHAT THIS ARTEFACT DOES NOT PROVE
=================================
See ``not_proven_by_this_artefact`` in the written document. The load-bearing one: the corpus,
the site, the operator and the incident are **authored for this repository**
(``docs/HONESTY.md`` §SYNTHETIC). What is proven here is that the deployment answers these six
questions about that world with these fields — not that the world is anyone's.

Usage::

    .venv/Scripts/python.exe scripts/proof/live_semantics.py --base-url <the live URL>

Exit codes:

* ``0`` — PROVEN. Every route answered 200 and every assertion held.
* ``1`` — NOT PROVEN. **The evidence file is still written** and names every failed assertion.
  An assertion is never tuned to recover a verdict; the copy is edited instead.
* ``2`` — the invocation was wrong, or the deployment could not be walked at all. Distinct from
  ``1`` so that *"there was no deployment"* is never read as *"a semantic is not live"*.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

EXIT_PROVEN: Final = 0
EXIT_NOT_PROVEN: Final = 1
EXIT_USAGE: Final = 2

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "demo" / "live-semantics.json"
SOURCE_FILE: Final = Path(__file__).resolve()

#: A lowercase 64-hex SHA-256. Roots, digests and quote hashes are asserted by SHAPE and
#: recorded by VALUE: a root whose value this file knew in advance would be a root this file
#: could have written.
SHA256_HEX: Final = re.compile(r"^[0-9a-f]{64}$")

#: A UUID literal anywhere in this source would break the identifier rule in the docstring.
_HEX4: Final = "[0-9a-fA-F]{4}"
_UUID: Final = re.compile(rf"\b[0-9a-fA-F]{{8}}-{_HEX4}-{_HEX4}-{_HEX4}-[0-9a-fA-F]{{12}}\b")

#: RULING R4, written into the artefact verbatim and copied rather than paraphrased by every
#: document that mentions the silence ledger.
R4_SENTENCE: Final = (
    "This run withheld nothing. The silence receipt is complete — it carries corpus_root, "
    "candidate_root, theta, s, n and a boundary proof — and its entries list is EMPTY, which "
    "the recall run corroborates from a different response with counts.n_silenced = 0. What is "
    "demonstrated is the apparatus: the arithmetic a withholding would have to publish, bound "
    "to a corpus root and a threshold, on a run that suppressed no precursor at all. A reader "
    "who takes the empty list for a list of withheld precursors has read it backwards, and any "
    "sentence in this repository that could be read that way is a false claim."
)

#: RULING R5, likewise.
R5_SENTENCE: Final = (
    "Every envelope states, field by field, whether a database column produced the value: a "
    "provenance array of chips (db:column, derived, db:constraint, staged) addressed by RFC "
    "6901 pointer, plus a top-level staged flag. The silence payload answers staged: true and "
    "its staged_note names receipt.bound.statement as the one value in that response no column "
    "produced. That is quoted as a strength and never trimmed."
)


@dataclass(frozen=True, slots=True)
class Route:
    """One of the seven GETs. ``subject_key`` is the key its identifier is resolved from."""

    key: str
    template: str
    subject_key: str | None
    path_template: str
    why: str


#: THE SEVEN. Nothing else reaches the wire, and ``request_discipline`` asserts it.
#: ``subjects`` is sent first because the other five are unaddressable until it answers; an
#: identifier guessed rather than discovered would be a claim about a row this program never
#: found.
ROUTES: Final[tuple[Route, ...]] = (
    Route(
        "subjects",
        "GET /v1/demo/subjects",
        None,
        "/v1/demo/subjects",
        "discovery — the only source of every identifier used below",
    ),
    Route(
        "health",
        "GET /v1/health",
        None,
        "/v1/health",
        "is the deployment up, and is the deployed chain the chain on disk",
    ),
    Route(
        "ancestry",
        "GET /v1/clauses/{clause_uuid}/ancestry",
        "clause_uuid",
        "/v1/clauses/{value}/ancestry",
        "PROVENANCE and ANCESTRY — the incident that wrote the clause, and the commit DAG",
    ),
    Route(
        "blocking_checks",
        "GET /v1/permits/{permit_id}/blocking-checks",
        "permit_id",
        "/v1/permits/{value}/blocking-checks",
        "SEVERITY FLOORS — the obligation, and the severity a fatality pinned to it",
    ),
    Route(
        "recall_run",
        "GET /v1/recall-runs/{run_id}",
        "run_id",
        "/v1/recall-runs/{value}",
        "RETRIEVAL ACCOUNTING — the retrieval pass auditing itself",
    ),
    Route(
        "silence",
        "GET /v1/permits/{permit_id}/silence",
        "permit_id",
        "/v1/permits/{value}/silence",
        "LOGGED SILENCE — what the recall declined to surface, with its arithmetic (R4)",
    ),
    Route(
        "receipt",
        "GET /v1/receipts/{receipt_id}",
        "receipt_id",
        "/v1/receipts/{value}",
        "EXPOSURE — who was shown the memory, digested per line",
    ),
)

#: ``/v1/health`` answers a bare object rather than a MAINLINE envelope: no ``provenance``, no
#: ``staged``, no ``statement_refs``. That is recorded as a property of the route and not as a
#: failure, and the R5 assertions are scoped to the six that ARE envelopes.
ENVELOPE_ROUTES: Final = tuple(r.key for r in ROUTES if r.key != "health")

#: The six semantics, and the route each is read off. Two of them share one request, which is
#: itself part of the claim: provenance and ancestry are one lookup, not two.
SEMANTICS: Final[tuple[tuple[str, tuple[str, ...], str], ...]] = (
    (
        "provenance",
        ("ancestry",),
        "clause -> the incident that wrote it, and the digest of the quoted evidence",
    ),
    (
        "ancestry",
        ("ancestry",),
        "a commit DAG, walked: the memory names a clause VERSION, so it cannot slide",
    ),
    (
        "severity floors",
        ("blocking_checks",),
        "a fatality's relevance never decays: the floor is a column with a stated basis",
    ),
    (
        "logged silence",
        ("silence",),
        "what the recall declined to surface, with the arithmetic it would have to publish",
    ),
    (
        "retrieval accounting",
        ("recall_run",),
        "the retrieval run auditing itself: five counts and the digest of the plan it ran",
    ),
    (
        "exposure",
        ("receipt",),
        "who was shown the memory, when, and the digest of what they were shown",
    ),
)

EQUALS: Final = "equals"
SHA256: Final = "sha256"
PRESENT: Final = "present"


@dataclass(frozen=True, slots=True)
class Claim:
    """One field the submission copy leans on, and the test that decides whether it still holds.

    ``says_who`` names the document whose sentence would become false if this claim went red.
    That is the whole point of the file: a red line here is an editing instruction, not a bug.
    """

    claim_id: str
    semantic: str
    route: str
    pointer: str
    kind: str
    expected: Any
    says_who: str
    why: str


_EC2: Final = "docs/submission/extra-credit-plan.md §2 EC-2"
_R44: Final = "docs/submission/extra-credit-plan.md §4.4 (README's six live GETs)"
_R43: Final = "docs/submission/extra-credit-plan.md §4.3 (DEVPOST axis-1 OPEN THIS TO CHECK IT)"

#: THE CONTRACT THE COPY DEPENDS ON. Every literal below is a value a submission document
#: STATES; none is a measurement, and each is asserted against the wire.
CLAIMS: Final[tuple[Claim, ...]] = (
    # ── the deployment answered, and answered about the chain we shipped ────────────────
    Claim(
        "health_is_ok",
        "precondition",
        "health",
        "/ok",
        EQUALS,
        True,
        "docs/demo/DEMO-READY.md",
        "a semantic cannot be live on an origin that is not",
    ),
    # ── PROVENANCE ─────────────────────────────────────────────────────────────────────
    Claim(
        "provenance_basis_is_an_asserted_document",
        "provenance",
        "ancestry",
        "/data/blame_edges/0/basis",
        EQUALS,
        "asserted_document",
        _R44,
        "the blame edge says WHY it exists, and the answer is a document somebody asserted — "
        "not a similarity score, which is what a vector store would have offered instead",
    ),
    Claim(
        "provenance_carries_an_evidence_quote_digest",
        "provenance",
        "ancestry",
        "/data/blame_edges/0/evidence_quote_sha256",
        SHA256,
        None,
        _R44,
        "the quote the attribution rests on is digested, so 'that is not what the report said' "
        "is a checkable claim rather than an argument",
    ),
    # ── ANCESTRY ───────────────────────────────────────────────────────────────────────
    Claim(
        "ancestry_commit_delta_is_introduce",
        "ancestry",
        "ancestry",
        "/data/commit_chain/0/control_delta",
        EQUALS,
        "introduce",
        _R44,
        "the commit chain records what each version DID to the control, not merely that it "
        "changed: this one introduced it",
    ),
    Claim(
        "ancestry_closure_depth",
        "ancestry",
        "ancestry",
        "/data/closure/depth",
        EQUALS,
        1,
        _R44,
        "the ancestry is projected into a closure the gate reads in one lookup, and the "
        "closure states how far it walked",
    ),
    Claim(
        "ancestry_closure_ancestor_count",
        "ancestry",
        "ancestry",
        "/data/closure/ancestor_count",
        EQUALS,
        1,
        _R44,
        "how many events reach this clause version — the number the copy prints",
    ),
    # ── SEVERITY FLOORS ────────────────────────────────────────────────────────────────
    Claim(
        "severity_floor_gate",
        "severity floors",
        "blocking_checks",
        "/data/checks/0/precursor/severity_gate",
        EQUALS,
        4,
        _R43,
        "THE FIELD THAT DECIDES AXIS ONE. If this number were the client's own, memory here "
        "would be a cache and the axis-one claim would be falsified",
    ),
    Claim(
        "severity_floor_basis",
        "severity floors",
        "blocking_checks",
        "/data/checks/0/precursor/severity_basis",
        EQUALS,
        "human_rated",
        _R43,
        "and the basis of that severity is a column beside it, not an assumption",
    ),
    Claim(
        "severity_floor_origin",
        "severity floors",
        "blocking_checks",
        "/data/checks/0/origin",
        EQUALS,
        "blame_ancestry",
        _R43,
        "the obligation cites the memory as its cause: it exists BECAUSE of the ancestry",
    ),
    # ── LOGGED SILENCE ─────────────────────────────────────────────────────────────────
    Claim(
        "silence_corpus_root",
        "logged silence",
        "silence",
        "/data/receipt/corpus_root",
        SHA256,
        None,
        _R44,
        "the receipt is bound to a corpus root: it is about a stated body of memory, not "
        "about whatever happened to be indexed",
    ),
    Claim(
        "silence_candidate_root",
        "logged silence",
        "silence",
        "/data/receipt/candidate_root",
        SHA256,
        None,
        _R44,
        "and to the candidate set the pass actually scored",
    ),
    Claim(
        "silence_theta",
        "logged silence",
        "silence",
        "/data/receipt/theta",
        EQUALS,
        0.35,
        _R44,
        "the threshold the withholding decision was made at, published rather than implied",
    ),
    Claim(
        "silence_s",
        "logged silence",
        "silence",
        "/data/receipt/s",
        EQUALS,
        1,
        _R44,
        "how many candidates cleared the threshold",
    ),
    Claim(
        "silence_n",
        "logged silence",
        "silence",
        "/data/receipt/n",
        EQUALS,
        1,
        _R44,
        "out of how many were scored — s of n is the arithmetic, and both are columns",
    ),
    Claim(
        "silence_boundary_proof_leaf_hash",
        "logged silence",
        "silence",
        "/data/receipt/boundary_proof/leaf_s/leaf_hash_hex",
        SHA256,
        None,
        _R44,
        "the boundary proof pins the LAST candidate that cleared theta into the Merkle tree, "
        "so the cut can be verified rather than believed",
    ),
    Claim(
        "silence_boundary_proof_leaf_index",
        "logged silence",
        "silence",
        "/data/receipt/boundary_proof/leaf_s/index",
        PRESENT,
        None,
        _R44,
        "and names which leaf that was",
    ),
    Claim(
        "silence_policy_version",
        "logged silence",
        "silence",
        "/data/receipt/policy_version",
        PRESENT,
        None,
        _EC2,
        "under which retrieval policy the withholding decision was taken",
    ),
    # ── RETRIEVAL ACCOUNTING ───────────────────────────────────────────────────────────
    Claim(
        "recall_n_candidates",
        "retrieval accounting",
        "recall_run",
        "/data/counts/n_candidates",
        EQUALS,
        1,
        _R44,
        "how many memories the pass surfaced",
    ),
    Claim(
        "recall_n_blocking",
        "retrieval accounting",
        "recall_run",
        "/data/counts/n_blocking",
        EQUALS,
        1,
        _R44,
        "how many of them block — the retrieval decided this, not a human",
    ),
    Claim(
        "recall_n_advisory",
        "retrieval accounting",
        "recall_run",
        "/data/counts/n_advisory",
        EQUALS,
        0,
        _R44,
        "how many were advisory only",
    ),
    Claim(
        "recall_n_silenced",
        "retrieval accounting",
        "recall_run",
        "/data/counts/n_silenced",
        EQUALS,
        0,
        _R44,
        "how many were suppressed — none, and R4 is the sentence that says so out loud",
    ),
    Claim(
        "recall_n_deduped",
        "retrieval accounting",
        "recall_run",
        "/data/counts/n_deduped",
        EQUALS,
        0,
        _R44,
        "how many were folded into another finding",
    ),
    Claim(
        "recall_index_plan_digest",
        "retrieval accounting",
        "recall_run",
        "/data/index_plan_digest",
        SHA256,
        None,
        _R44,
        "the digest of the plan the pass ran, so the retrieval is REPRODUCIBLE rather than "
        "recalled — the difference between a memory system and a log of one",
    ),
    # ── EXPOSURE ───────────────────────────────────────────────────────────────────────
    Claim(
        "exposure_receipt_digest",
        "exposure",
        "receipt",
        "/data/receipt_digest",
        SHA256,
        None,
        _EC2,
        "the digest of what the signer was shown, so 'I was never told' is checkable",
    ),
    Claim(
        "exposure_actor",
        "exposure",
        "receipt",
        "/data/actor_sub",
        PRESENT,
        None,
        _EC2,
        "and WHO was shown it: a memory nobody was shown cannot bind anybody",
    ),
    Claim(
        "exposure_line_digest",
        "exposure",
        "receipt",
        "/data/lines/0/payload_digest",
        SHA256,
        None,
        _EC2,
        "digested per line, not per receipt, so one line can be produced without the rest",
    ),
)


@dataclass(frozen=True, slots=True)
class Identity:
    """A value from ONE response compared against a value from ANOTHER.

    Nothing here can hold by construction. Two endpoints agreeing about an identifier is a fact
    about the database; one endpoint asserting it is a fact about one reader.
    """

    claim_id: str
    claim: str
    left_route: str
    left_pointer: str
    right_route: str
    right_pointer: str


IDENTITIES: Final[tuple[Identity, ...]] = (
    Identity(
        "the_obligation_names_the_recall_run",
        "the obligation cites the retrieval pass that found it",
        "blocking_checks",
        "/data/checks/0/recall_run_id",
        "recall_run",
        "/data/run_id",
    ),
    Identity(
        "the_obligation_names_the_blamed_event",
        "the obligation's precursor is the event on the blame edge",
        "blocking_checks",
        "/data/checks/0/precursor_event_id",
        "ancestry",
        "/data/blame_edges/0/event_id",
    ),
    Identity(
        "the_obligation_cites_the_blamed_commit",
        "the obligation cites the clause VERSION the blame edge names",
        "blocking_checks",
        "/data/checks/0/commit_id",
        "ancestry",
        "/data/blame_edges/0/commit_id",
    ),
    Identity(
        "the_silence_receipt_is_of_that_run",
        "the silence receipt is about the retrieval pass that produced the obligation",
        "silence",
        "/data/receipt/run_id",
        "recall_run",
        "/data/run_id",
    ),
    Identity(
        "the_silence_receipt_is_bound_to_the_index_plan",
        "the receipt is bound to the digest of the plan the run recorded",
        "silence",
        "/data/receipt/bound/index_plan_digest",
        "recall_run",
        "/data/index_plan_digest",
    ),
    Identity(
        "the_exposure_receipt_names_that_silence_receipt",
        "what the signer was shown names the silence receipt for the same run",
        "receipt",
        "/data/silence_receipt_id",
        "silence",
        "/data/receipt/silence_receipt_id",
    ),
    Identity(
        "the_exposure_receipt_is_over_the_same_corpus",
        "and it is over the corpus root the silence receipt is bound to",
        "receipt",
        "/data/corpus_root",
        "silence",
        "/data/receipt/corpus_root",
    ),
    Identity(
        "the_exposure_line_names_the_obligation",
        "the receipt line names the obligation itself: the receipt is about THIS memory",
        "receipt",
        "/data/lines/0/check_id",
        "blocking_checks",
        "/data/checks/0/check_id",
    ),
    Identity(
        "retrieval_and_exposure_share_the_policy",
        "the receipt was issued under the policy the retrieval ran under",
        "receipt",
        "/data/policy_version",
        "recall_run",
        "/data/policy_version",
    ),
)

#: Stated in the artefact so a reader does not have to infer the aperture from what is absent.
#: Every line is a limit of THIS artefact, not a known defect of the product.
NOT_PROVEN_BY_THIS_ARTEFACT: Final[tuple[str, ...]] = (
    (
        "Not that the world these semantics are about is anyone's. The corpus, the site, the "
        "operator and the incident were authored for this repository — docs/HONESTY.md "
        "§SYNTHETIC — and the payloads say so in their own title and evidence_summary fields, "
        "which begin with the word SYNTHETIC. What is proven is that the deployment answers "
        "these six questions about that world with these fields."
    ),
    (
        "Not the ACT half of the loop. That is POST /v1/demo/gate-run, it is proven in "
        "evidence/demo/live-beats.json, and this program sends no POST at all — so a reader "
        "who wants the refusal's MUS and NAA must read that file, not this one."
    ),
    (
        "Not that a screen renders any of this. No browser ran; this is an HTTP client. That "
        "an operator surface displays these bytes is a separate claim with separate evidence."
    ),
    (
        "Not a latency figure. No duration is recorded here at all, because a GET envelope on "
        "this API carries no server-measured duration and a wall clock wearing a server's name "
        "is how a demo narrates its own reveal delay as database latency."
    ),
    (
        "Not that these semantics hold for every subject. One seeded subject was read, once, "
        "and every identifier it was read by is recorded in the subject block."
    ),
    (
        "Not that the store is CockroachDB rather than any PostgreSQL-wire server. What is "
        "recorded is the cluster_version string the deployment reported about itself."
    ),
)


class ProbeError(RuntimeError):
    """The deployment did not answer, or answered something this program cannot address."""


def _now() -> str:
    """This machine's clock, RFC 3339, UTC — the READING time, never the server's."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Fetched:
    key: str
    template: str
    path: str
    url: str
    status: int
    body: bytes
    read_at: str

    @property
    def doc(self) -> Any:
        """The parsed body, or ``None`` when it did not parse.

        ``None`` rather than an exception on purpose. A 502 from the Function URL arrives as
        HTML, and a program that raised here would exit on a traceback and write **no evidence
        file at all** — which is the one outcome the brief forbids. ``None`` flows into
        :func:`pointer_get`, every pointer misses, every claim on that route goes red, and the
        artefact is written saying exactly which route stopped answering JSON. The parse error
        itself is recorded beside the route in :func:`record_response`.
        """
        try:
            return json.loads(self.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @property
    def parse_error(self) -> str | None:
        """The reason the body did not parse, or ``None`` when it did."""
        try:
            json.loads(self.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return str(exc)
        return None


def get(base: str, route: Route, path: str, timeout_s: float) -> Fetched:
    """One ``GET``, and there is no other verb in this file.

    HTTPS is required. An evidence artefact taken over plaintext is an artefact anyone on the
    path could have written, and the origin this is aimed at is an HTTPS Function URL.
    """
    url = base.rstrip("/") + path
    if not url.startswith("https://"):
        raise ProbeError(f"refusing a non-HTTPS URL: {url!r}")
    request = urllib.request.Request(  # noqa: S310 - scheme asserted https on the line above
        url, method="GET", headers={"accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - same
            status, raw = int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        status, raw = int(exc.code), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError(f"GET {path}: transport failed: {exc}") from exc
    return Fetched(route.key, route.template, path, url, status, raw, _now())


_MISSING: Final = object()


def pointer_get(doc: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 pointer, returning :data:`_MISSING` rather than raising."""
    node = doc
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                return _MISSING
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                return _MISSING
            node = node[int(token)]
        else:
            return _MISSING
    return node


def jsonable(value: Any) -> Any:
    """``None`` for a pointer that missed, so a sentinel can never reach the artefact."""
    return None if value is _MISSING else value


def chip_for(envelope: Any, pointer: str) -> str | None:
    """The deployment's OWN provenance chip for *pointer*.

    ``provenance`` addresses ``/data``, so the pointer is rebased before the lookup, and the
    LONGEST matching entry wins: the envelope chips ``/checks/0`` as ``db:column`` and lets that
    cover every column of the row, so rebasing to the exact leaf first is what stops a field the
    envelope calls ``derived`` being reported as a column.
    """
    if not pointer.startswith("/data"):
        return None
    rebased = pointer[len("/data") :] or "/"
    entries = pointer_get(envelope, "/provenance")
    if not isinstance(entries, list):
        return None
    best: tuple[int, str] | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        candidate, chip = entry.get("pointer"), entry.get("chip")
        if not isinstance(candidate, str) or not isinstance(chip, str):
            continue
        if (rebased == candidate or rebased.startswith(candidate + "/")) and (
            best is None or len(candidate) > best[0]
        ):
            best = (len(candidate), chip)
    return None if best is None else best[1]


def resolve_identifiers(subjects: Fetched) -> dict[str, str]:
    """Read every identifier out of ``GET /v1/demo/subjects``. Nothing may be guessed."""
    data = pointer_get(subjects.doc, "/data")
    if not isinstance(data, dict):
        raise ProbeError("GET /v1/demo/subjects returned no data object; the walk is unaddressable")
    absent = data.get("absent")
    if absent:
        raise ProbeError(f"GET /v1/demo/subjects reports absent subjects: {absent!r}")
    ids: dict[str, str] = {}
    for route in ROUTES:
        key = route.subject_key
        if key is None:
            continue
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ProbeError(f"GET /v1/demo/subjects carries no {key!r}; nothing may be guessed")
        ids[key] = value
    return ids


def walk(base: str, timeout_s: float) -> tuple[dict[str, Fetched], dict[str, str]]:
    """The seven GETs, in the only order discovery permits."""
    subjects_route = ROUTES[0]
    subjects = get(base, subjects_route, subjects_route.path_template, timeout_s)
    if subjects.status != 200:
        raise ProbeError(f"GET {subjects_route.path_template} answered {subjects.status}")
    ids = resolve_identifiers(subjects)
    responses: dict[str, Fetched] = {subjects_route.key: subjects}
    for route in ROUTES[1:]:
        path = (
            route.path_template
            if route.subject_key is None
            else route.path_template.format(value=ids[route.subject_key])
        )
        responses[route.key] = get(base, route, path, timeout_s)
    return responses, ids


def curl_for(url: str) -> str:
    return f"curl -s '{url}' | python -m json.tool"


def envelope_note(route: Route, is_envelope: bool) -> str | None:
    """Why a response is not an envelope — a known property, or an unexpected answer.

    The two cases must not read alike. ``/v1/health`` answering a bare object is a documented
    property of that route; a semantic route answering something without an ``envelope_version``
    is the deployment having stopped answering the question this artefact is about, and saying
    so plainly is the difference between a caveat and a defect.
    """
    if is_envelope:
        return None
    if route.key == "health":
        return (
            "/v1/health answers a bare object, not a MAINLINE envelope: no provenance array, no "
            "staged flag, no statement_refs. Recorded as a property of the route rather than as "
            "a failure, and the R5 assertions are scoped to the six that are envelopes."
        )
    return (
        f"UNEXPECTED: {route.template} did not answer a MAINLINE envelope. Every claim addressed "
        "at this route will have missed its pointer and gone red; read json_parse_error and "
        "http_status beside this line before reading anything else in this file."
    )


def record_response(route: Route, fetched: Fetched) -> dict[str, Any]:
    """Everything about one response that a reader might want to check independently."""
    doc = fetched.doc
    parse_error = fetched.parse_error
    is_envelope = isinstance(doc, dict) and "envelope_version" in doc
    provenance = pointer_get(doc, "/provenance") if is_envelope else _MISSING
    chips = provenance if isinstance(provenance, list) else []
    return {
        "route": route.template,
        "why": route.why,
        "url": fetched.url,
        "curl": curl_for(fetched.url),
        "http_status": fetched.status,
        "method": "GET",
        "response_bytes": len(fetched.body),
        "response_sha256": hashlib.sha256(fetched.body).hexdigest(),
        "read_at": fetched.read_at,
        "json_parse_error": parse_error,
        "is_mainline_envelope": is_envelope,
        "envelope_note": envelope_note(route, is_envelope),
        "resource": jsonable(pointer_get(doc, "/resource")),
        "schema_id": jsonable(pointer_get(doc, "/schema_id")),
        "envelope_version": jsonable(pointer_get(doc, "/envelope_version")),
        "observed_at": jsonable(pointer_get(doc, "/observed_at")),
        "server_date": jsonable(pointer_get(doc, "/server_date")),
        "staged": jsonable(pointer_get(doc, "/staged")),
        "staged_note": jsonable(pointer_get(doc, "/staged_note")),
        "provenance_chips": chips,
        "provenance_chip_count": len(chips),
        "provenance_chip_kinds": sorted(
            {c["chip"] for c in chips if isinstance(c, dict) and isinstance(c.get("chip"), str)}
        ),
        "statement_refs": [
            {"kind": e.get("kind"), "object": e.get("object"), "sql_published": e.get("text")}
            for e in (pointer_get(doc, "/statement_refs") or [])
            if isinstance(e, dict)
        ]
        if is_envelope
        else [],
    }


def holds(kind: str, expected: Any, observed: Any) -> bool:
    """The three tests. A value asserted by SHAPE is one this program could not have written."""
    if observed is _MISSING:
        return False
    if kind == EQUALS:
        return bool(observed == expected) and type(observed) is type(expected)
    if kind == SHA256:
        return isinstance(observed, str) and SHA256_HEX.match(observed) is not None
    return observed is not None


def evaluate_claims(responses: dict[str, Fetched]) -> list[dict[str, Any]]:
    """Every field the copy leans on, with the document that would have to change if it moved."""
    out: list[dict[str, Any]] = []
    for claim in CLAIMS:
        doc = responses[claim.route].doc
        observed = pointer_get(doc, claim.pointer)
        out.append(
            {
                "id": claim.claim_id,
                "semantic": claim.semantic,
                "route": responses[claim.route].template,
                "pointer": claim.pointer,
                "test": claim.kind,
                "expected": (
                    claim.expected
                    if claim.kind == EQUALS
                    else ("a lowercase 64-hex sha256" if claim.kind == SHA256 else "a non-null")
                ),
                "observed": jsonable(observed),
                "provenance_chip": chip_for(doc, claim.pointer),
                "holds": holds(claim.kind, claim.expected, observed),
                "says_who": claim.says_who,
                "why": claim.why,
            }
        )
    return out


def evaluate_identities(responses: dict[str, Fetched]) -> list[dict[str, Any]]:
    """The joins that make six responses one world."""
    out: list[dict[str, Any]] = []
    for identity in IDENTITIES:
        left = jsonable(pointer_get(responses[identity.left_route].doc, identity.left_pointer))
        right = jsonable(pointer_get(responses[identity.right_route].doc, identity.right_pointer))
        out.append(
            {
                "id": identity.claim_id,
                "claim": identity.claim,
                "left": f"{responses[identity.left_route].template}{identity.left_pointer}",
                "right": f"{responses[identity.right_route].template}{identity.right_pointer}",
                "left_value": left,
                "right_value": right,
                "holds": left is not None and left == right,
                "cannot_hold_by_construction": True,
            }
        )
    return out


#: The fields that make the silence receipt COMPLETE. Recorded so a reader can see that the
#: apparatus is whole on a run whose entries list is empty — which is R4's entire point.
RECEIPT_FIELDS: Final = (
    "corpus_root",
    "candidate_root",
    "theta",
    "s",
    "n",
    "boundary_proof",
    "policy_version",
    "issued_at",
)


def silence_ledger(responses: dict[str, Fetched]) -> dict[str, Any]:
    """RULING R4, mechanised: the entries count is compared with a DIFFERENT response's count."""
    silence = responses["silence"].doc
    entries = pointer_get(silence, "/data/entries")
    counted = len(entries) if isinstance(entries, list) else None
    n_silenced = jsonable(pointer_get(responses["recall_run"].doc, "/data/counts/n_silenced"))
    return {
        "ruling": "R4 (docs/submission/extra-credit-plan.md §1)",
        "sentence": R4_SENTENCE,
        "entries_in_the_silence_payload": counted,
        "entries_read_from": "GET /v1/permits/{permit_id}/silence /data/entries",
        "n_silenced_in_the_recall_run": n_silenced,
        "n_silenced_read_from": "GET /v1/recall-runs/{run_id} /data/counts/n_silenced",
        "agree": counted is not None and counted == n_silenced,
        "receipt_is_complete": {
            field: jsonable(pointer_get(silence, f"/data/receipt/{field}"))
            for field in RECEIPT_FIELDS
        },
        "why_two_responses": (
            "one endpoint asserting a withholding count is a fact about one reader; two "
            "endpoints agreeing about it is a fact about the database"
        ),
    }


def provenance_and_staging(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """RULING R5: the chip arrays and the staged flags, recorded per response."""
    staged = {k: records[k]["staged"] for k in ENVELOPE_ROUTES}
    return {
        "ruling": "R5 (docs/submission/extra-credit-plan.md §1)",
        "sentence": R5_SENTENCE,
        "chips_per_response": {
            k: {
                "count": records[k]["provenance_chip_count"],
                "kinds": records[k]["provenance_chip_kinds"],
            }
            for k in ENVELOPE_ROUTES
        },
        "staged_per_response": staged,
        "staged_true_on": sorted(k for k, v in staged.items() if v is True),
        "staged_notes": {
            k: records[k]["staged_note"] for k in ENVELOPE_ROUTES if records[k]["staged_note"]
        },
        "health_is_not_an_envelope": records["health"]["envelope_note"],
    }


def request_discipline(responses: dict[str, Fetched], ids: dict[str, str]) -> dict[str, Any]:
    """The no-write rule, asserted against this program's own request list rather than trusted."""
    # `method` is a literal here rather than read back off the response for the reason the
    # docstring gives: there is one verb in this file, `get` is the only function that reaches
    # the network, and it hard-codes `method="GET"`. A count derived from that fact is the
    # honest one; a count derived from a field this program also wrote would be circular.
    sent: list[dict[str, str]] = [
        {"method": "GET", "path": f.path, "route": f.template, "status": str(f.status)}
        for f in responses.values()
    ]
    declared = sorted(r.template for r in ROUTES)
    return {
        "rule": (
            "seven GETs and nothing else. No POST, no PUT, no DELETE, no write of any kind, "
            "and no header but accept."
        ),
        "authority": "the founder's standing prohibition; docs/submission/extra-credit-plan.md §6",
        "declared_routes": declared,
        "requests_sent": sent,
        "total_requests": len(sent),
        "methods": sorted({s["method"] for s in sent}),
        "write_requests_sent": sum(1 for s in sent if s["method"] != "GET"),
        "routes_sent_match_routes_declared": sorted(s["route"] for s in sent) == declared,
        "identifiers": {
            "resolved_from": "GET /v1/demo/subjects",
            "values": dict(ids),
            "not_one_of_these_is_a_literal_in_this_program": True,
        },
        "credentials_used": (
            "none. No DSN, no AWS profile, no token, no environment variable, no SSM parameter, "
            "no knowledge of the seed — a stranger with the URL."
        ),
    }


def source_audit(base: str) -> dict[str, Any]:
    """What this file does and does not put into its own artefact, tested rather than asserted."""
    source = SOURCE_FILE.read_text(encoding="utf-8")
    host = urlsplit(base).netloc
    return {
        "claim": (
            "no identifier and no origin in this artefact originates in "
            "scripts/proof/live_semantics.py. The EXPECTED VALUES do, deliberately and by "
            "name: they are the contract the submission copy states, and a checker that only "
            "records what it was told cannot go red."
        ),
        "source": str(SOURCE_FILE).replace("\\", "/"),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_bytes": len(source.encode("utf-8")),
        "uuid_literals_in_the_source": len(_UUID.findall(source)),
        "origin_host_occurrences_in_the_source": source.count(host) if host else 0,
        "contrast": (
            "scripts/proof/memory_loop.py makes the STRONGER claim — that no measured value at "
            "all comes from its source — and audits 79 values to prove it. This file does not "
            "borrow that claim, because it would be false here."
        ),
    }


def health_block(responses: dict[str, Fetched]) -> dict[str, Any]:
    doc = responses["health"].doc
    keys = (
        "ok",
        "database",
        "deploy_chain_applied",
        "deploy_chain_files",
        "migrations_applied",
        "cluster_version",
        "schema_fingerprint",
        "server_date",
    )
    return {key: jsonable(pointer_get(doc, f"/{key}")) for key in keys}


def semantics_block(
    responses: dict[str, Fetched], claims: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The six, each with its command and the fields that prove it."""
    out: list[dict[str, Any]] = []
    for name, routes, sentence in SEMANTICS:
        rows = [c for c in claims if c["semantic"] == name]
        out.append(
            {
                "semantic": name,
                "sentence": sentence,
                "routes": [responses[r].template for r in routes],
                "curl": [curl_for(responses[r].url) for r in routes],
                "http_status": {responses[r].template: responses[r].status for r in routes},
                "proving_fields": [
                    {
                        "pointer": c["pointer"],
                        "observed": c["observed"],
                        "provenance_chip": c["provenance_chip"],
                        "holds": c["holds"],
                    }
                    for c in rows
                ],
                "assertions": [c["id"] for c in rows],
                "all_hold": all(c["holds"] for c in rows),
            }
        )
    return out


def assemble_assertions(
    claims: list[dict[str, Any]],
    identities: list[dict[str, Any]],
    ledger: dict[str, Any],
    staging: dict[str, Any],
    discipline: dict[str, Any],
    audit: dict[str, Any],
    health: dict[str, Any],
    records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """One flat ledger. Every clause of this artefact's claim, as something that can go red."""
    rows: list[dict[str, Any]] = [
        {
            "id": "every_route_answered_200",
            "claim": "all seven GETs answered 200",
            "holds": all(r["http_status"] == 200 for r in records.values()),
            "observed": ", ".join(f"{k}={v['http_status']}" for k, v in records.items()),
        },
        {
            "id": "exactly_the_seven_declared_routes_were_sent",
            "claim": discipline["rule"],
            "holds": discipline["routes_sent_match_routes_declared"]
            and discipline["total_requests"] == len(ROUTES),
            "observed": f"{discipline['total_requests']} requests, methods {discipline['methods']}",
        },
        {
            "id": "no_write_request_was_sent",
            "claim": "this program issues no POST, PUT or DELETE, of any shape, ever",
            "holds": discipline["write_requests_sent"] == 0,
            "observed": f"write_requests_sent={discipline['write_requests_sent']}",
        },
        {
            "id": "the_deployed_chain_is_the_chain_on_disk",
            "claim": "deploy_chain_applied equals deploy_chain_files",
            "holds": health["deploy_chain_applied"] == health["deploy_chain_files"],
            "observed": f"{health['deploy_chain_applied']}/{health['deploy_chain_files']}",
        },
    ]
    rows.extend(
        {"id": c["id"], "claim": c["why"], "holds": c["holds"], "observed": repr(c["observed"])}
        for c in claims
    )
    rows.extend(
        {"id": i["id"], "claim": i["claim"], "holds": i["holds"], "observed": i["left_value"]}
        for i in identities
    )
    rows.append(
        {
            "id": "the_silence_ledger_agrees_with_the_recall_run",
            "claim": "R4: the silence payload's entries count equals the run's n_silenced, and "
            "the two came off different responses",
            "holds": bool(ledger["agree"]),
            "observed": f"entries={ledger['entries_in_the_silence_payload']} "
            f"n_silenced={ledger['n_silenced_in_the_recall_run']}",
        }
    )
    rows.append(
        {
            "id": "every_envelope_published_its_provenance_chips",
            "claim": "R5: each of the six envelope responses states, field by field, whether a "
            "database column produced the value",
            "holds": all(records[k]["provenance_chip_count"] > 0 for k in ENVELOPE_ROUTES),
            "observed": json.dumps(
                {k: records[k]["provenance_chip_count"] for k in ENVELOPE_ROUTES}
            ),
        }
    )
    rows.append(
        {
            "id": "exactly_one_payload_declares_itself_staged",
            "claim": "R5: the silence payload answers staged true; the other five answer false",
            "holds": staging["staged_true_on"] == ["silence"]
            and all(records[k]["staged"] is False for k in ENVELOPE_ROUTES if k != "silence"),
            "observed": json.dumps(staging["staged_per_response"]),
        }
    )
    rows.append(
        {
            "id": "the_staged_note_names_the_field_no_column_produced",
            "claim": "R5: the note names receipt.bound.statement rather than merely flagging",
            "holds": isinstance(records["silence"]["staged_note"], str)
            and "receipt.bound.statement" in records["silence"]["staged_note"],
            "observed": repr((records["silence"]["staged_note"] or "")[:120]),
        }
    )
    rows.append(
        {
            "id": "the_staged_value_is_chipped_staged_in_the_provenance_array",
            "claim": "R5: and the chip array points at it by RFC 6901 pointer, not by prose",
            "holds": any(
                isinstance(c, dict)
                and c.get("chip") == "staged"
                and c.get("pointer") == "/receipt/bound/statement"
                for c in records["silence"]["provenance_chips"]
            ),
            "observed": json.dumps(
                [c for c in records["silence"]["provenance_chips"] if c.get("chip") == "staged"]
            ),
        }
    )
    rows.append(
        {
            "id": "no_identifier_is_a_literal_in_this_source",
            "claim": audit["claim"],
            "holds": audit["uuid_literals_in_the_source"] == 0
            and audit["origin_host_occurrences_in_the_source"] == 0,
            "observed": f"uuids={audit['uuid_literals_in_the_source']} "
            f"origin_host={audit['origin_host_occurrences_in_the_source']}",
        }
    )
    return rows


def build_document(
    *, base: str, argv: list[str], responses: dict[str, Fetched], ids: dict[str, str]
) -> dict[str, Any]:
    records = {r.key: record_response(r, responses[r.key]) for r in ROUTES}
    claims = evaluate_claims(responses)
    identities = evaluate_identities(responses)
    ledger = silence_ledger(responses)
    staging = provenance_and_staging(records)
    discipline = request_discipline(responses, ids)
    audit = source_audit(base)
    health = health_block(responses)
    assertions = assemble_assertions(
        claims, identities, ledger, staging, discipline, audit, health, records
    )
    failed = [a["id"] for a in assertions if not a["holds"]]
    return {
        "artefact": "live-semantics",
        "schema": "mainline.evidence/live-semantics/1",
        "generated_at": _now(),
        "generated_by": "scripts/proof/live_semantics.py",
        "owner": "extra-credit worker W5",
        "command": " ".join([".venv/Scripts/python.exe", "scripts/proof/live_semantics.py", *argv]),
        "base_url": base.rstrip("/"),
        "credentials_used": discipline["credentials_used"],
        "what_this_proves": (
            "that six memory semantics named in README.md, docs/submission/DEVPOST.md and "
            "docs/submission/JUDGING-AXES.md are live, anonymous GETs on the deployed origin, "
            "and that the exact field each sentence leans on still reads what the sentence "
            "says it reads. The Functionality rule requires the project to function as "
            "depicted; this is the standing re-derivation of that."
        ),
        "rulings": {
            "R4": R4_SENTENCE,
            "R5": R5_SENTENCE,
        },
        "deployment": health,
        "semantics": semantics_block(responses, claims),
        "routes": records,
        "claims": claims,
        "cross_response_identities": identities,
        "silence_ledger": ledger,
        "provenance_and_staging": staging,
        "request_discipline": discipline,
        "source_audit": audit,
        "assertions": assertions,
        "assertions_total": len(assertions),
        "assertions_held": sum(1 for a in assertions if a["holds"]),
        "assertions_failed": failed,
        "verdict": "PROVEN" if not failed else "NOT PROVEN",
        "not_proven_by_this_artefact": list(NOT_PROVEN_BY_THIS_ARTEFACT),
        "if_this_goes_red": (
            "an assertion is never tuned to recover a verdict. Each claim carries says_who "
            "naming the document whose sentence would become false; edit that sentence, or "
            "repair the deployment, and re-run."
        ),
        "reproduce": {
            "command": (
                ".venv/Scripts/python.exe scripts/proof/live_semantics.py --base-url " + base
            ),
            "needs": "python 3.13 and the URL. No credential, no database, no AWS access.",
            "expect": "exit 0 and VERDICT PROVEN, with different read_at stamps",
            "reader": "docs/demo/LIVE-SEMANTICS.md",
        },
    }


def summarise(document: dict[str, Any], out: Path) -> None:
    print("")
    print("MAINLINE - six memory semantics, live")
    print(f"  target        {document['base_url']}")
    print(f"  taken         {document['generated_at']}")
    print(f"  credentials   {document['credentials_used'].split('.')[0]}")
    health = document["deployment"]
    print(
        f"  health        ok={health['ok']} db={health['database']} "
        f"chain={health['deploy_chain_applied']}/{health['deploy_chain_files']}"
    )
    print("")
    for row in document["semantics"]:
        mark = "HELD" if row["all_hold"] else "RED "
        print(f"  {mark}  {row['semantic']:<22s} {len(row['proving_fields'])} field(s)")
    print("")
    ledger = document["silence_ledger"]
    print(
        f"  silence       entries={ledger['entries_in_the_silence_payload']} "
        f"n_silenced={ledger['n_silenced_in_the_recall_run']} agree={ledger['agree']}"
    )
    print(f"  staged true   {document['provenance_and_staging']['staged_true_on']}")
    print(
        f"  requests      {document['request_discipline']['total_requests']} "
        f"{document['request_discipline']['methods']} "
        f"writes={document['request_discipline']['write_requests_sent']}"
    )
    print(f"  assertions    {document['assertions_held']}/{document['assertions_total']} held")
    for assertion in document["assertions"]:
        if not assertion["holds"]:
            print(f"  FAILED        {assertion['id']}: {assertion['observed']}")
    print(f"  artefact      {out.resolve()}")
    print(f"VERDICT {document['verdict']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_semantics.py",
        description=(
            "Prove the six memory semantics are live anonymous GETs on the deployed origin. "
            "Seven GETs, no write of any kind. Writes evidence/demo/live-semantics.json."
        ),
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="the deployment's origin. REQUIRED: a default here would be a value this artefact "
        "took from its own source.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(args_list)

    parts = urlsplit(args.base_url)
    if parts.scheme != "https" or not parts.netloc:
        print(f"usage: --base-url must be an https origin, not {args.base_url!r}", file=sys.stderr)
        return EXIT_USAGE

    try:
        responses, ids = walk(args.base_url, args.timeout)
    except ProbeError as exc:
        print(f"the deployment could not be walked: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"the deployment answered something that is not JSON: {exc}", file=sys.stderr)
        return EXIT_USAGE

    document = build_document(base=args.base_url, argv=args_list, responses=responses, ids=ids)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summarise(document, args.out)
    return EXIT_PROVEN if document["verdict"] == "PROVEN" else EXIT_NOT_PROVEN


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
