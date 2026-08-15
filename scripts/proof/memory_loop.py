#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""STORE -> RETRIEVE -> SHOWN TO -> ACT, measured on the deployment and written down.

WHY THIS FILE EXISTS
====================
The hackathon's first judging criterion is Agentic Memory Design, the tie-break across the
five criteria is lexicographic, and that criterion is first. The organiser's own video tip
asks for *"a screen showing your agent store, retrieve and act on memory."* This repository
can prove that loop — the loop is what the gate is made of — and until this file it rendered
it nowhere. This program is the artefact: four words, each with a schema-qualified
``table.column`` behind it, the live HTTP route that returned it, the value, and the value's
timestamp. One ``curl`` per row, so a judge can re-run any single line of it.

RULING R7 — NO NEW ENDPOINT, AND NOTHING COMPOSED CLIENT-SIDE
=============================================================
``docs/demo/proof-and-polish-plan.md`` R7. Every word of the loop is already a live ``GET``
in the route table at ``verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py``
lines 229-252::

    STORE     GET /v1/clauses/{clause_uuid}/ancestry
    RETRIEVE  GET /v1/recall-runs/{run_id}
    SHOWN TO  GET /v1/receipts/{receipt_id}
    ACT       GET /v1/permits/{permit_id}/blocking-checks
              GET /v1/permits/{permit_id}          (the counter, and the CHECK over it)

Nothing is added to that table by this program and nothing is assembled here from a
constant. **This program contributes ADDRESSES; the deployment contributes VALUES.** The
addresses are the route templates, the RFC 6901 pointers and the relation names — and even
the relation names are not taken on trust: each is confirmed against the ``statement_refs``
the same response returned, so a row whose relation is wrong goes red rather than reading
plausibly. :func:`self_audit` then greps this file's own bytes for every value the artefact
records, and a hit is a hard NOT PROVEN.

NO IDENTIFIER IS WRITTEN DOWN HERE
==================================
There is no UUID literal in this file and there must never be one. Every subject is read out
of ``GET /v1/demo/subjects``, which answers entirely out of ``SELECT``s. An id transcribed
into a source file is a claim about a deployment made by a file that cannot see it — and it
is the exact shape of the offence this repository has already reverted a worker for.
``--base-url`` is REQUIRED for the same reason: a default origin baked in here would be a
value in the artefact that came from this source.

THE TEN SECONDS ARE COMPUTED, NEVER STATED
==========================================
``mainline_meas.recall_run.started_at`` and ``mainline.blocking_check.materialised_at`` are
both columns, both arrive over the wire in different responses, and the gap between them is
subtracted here. The number is not in this file. It is corroborated — separately, and
reported separately — against the two literals in ``verticals/mainline/db/seeds/demo/``,
by searching those files for the instants the deployment served.

RULING R9 — A FOUR WITH NO PROVENANCE IS A NUMBER SOMEBODY COULD HAVE TYPED
===========================================================================
Three different ``4``s appear in this loop and they were written by three different things.
``mainline.event.severity_gate`` is the seed's, and ``severity_basis`` beside it says so.
``mainline.clause_blame_current.max_severity`` carries its own ``computed_by`` and
``projector_ver`` columns, and both arrive in the response body.
``mainline.blocking_check.severity`` is neither: the seed supplies ``0`` / ``'routine'`` and
``mainline.fn_check_project`` (BEFORE INSERT, welded by ``0120_trg_check_project.sql``)
overwrites both from ``mainline.clause_blame_current`` under invariant **MI25**. Every one of
those three gets a ``written_by`` block naming who wrote it, and the two repository
citations behind the MI25 claim are located by search — file, line and the literal line —
never typed.

RULING R8 — THE INCIDENT IS 2019-03-14
======================================
``verticals/mainline/db/seeds/demo/demo_world.sql:272``, and the deployment serves it. The
superseded year that some drafts carried is asserted absent from every measured value and
from the whole finished document.

WHAT THIS PROGRAM WILL NOT DO
=============================
It opens no AWS client, knows no Terraform verb, reads no credential and sends no header but
``accept``. It issues ``GET`` and nothing else — not even ``POST /v1/demo/gate-run``, which
this artefact does not need and which belongs to the transcript worker. It writes exactly one
file, ``evidence/demo/memory-loop.json``, and it writes it on a red verdict too.

Usage::

    .venv/Scripts/python.exe scripts/proof/memory_loop.py --base-url <live URL>

Exit codes:

* ``0`` — PROVEN. Every row carried a value, every relation was confirmed by the response
  that produced it, the cross-response identities held, and the audit found nothing.
* ``1`` — NOT PROVEN. **The evidence file is still written** and names the failed assertion.
* ``2`` — the invocation was wrong, or the deployment did not answer. Distinct from 1 so
  that *"there was no deployment"* is never read as *"the loop did not close"*.
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
from typing import Any

EXIT_PROVEN = 0
EXIT_NOT_PROVEN = 1
EXIT_USAGE = 2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "evidence" / "demo" / "memory-loop.json"
SOURCE_FILE = Path(__file__).resolve()

#: The seeds this artefact corroborates itself against. Read-only, and searched for the
#: instants the DEPLOYMENT served rather than parsed for instants to compare against — a
#: presence check cannot be fooled by a regex that drifted.
SEED_DIR = REPO_ROOT / "verticals" / "mainline" / "db" / "seeds" / "demo"

#: The route table this loop is drawn from, so the artefact cites its own authority.
ROUTE_TABLE = ("verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:229-252",)

# ═════════════════════════════════════════════════════════════════════════════════════
# THE ADDRESSES — every one of them is a template, and not one of them is a value
# ═════════════════════════════════════════════════════════════════════════════════════

SUBJECTS_PATH = "/v1/demo/subjects"
HEALTH_PATH = "/v1/health"

#: ``name -> (route template as it appears in app.py, subject key, path template)``. The
#: subject key is read out of ``GET /v1/demo/subjects``; the path is then formatted with the
#: value the deployment handed back, so the only identifiers that ever exist here are its.
READS: tuple[tuple[str, str, str, str], ...] = (
    (
        "ancestry",
        "GET /v1/clauses/{clause_uuid}/ancestry",
        "clause_uuid",
        "/v1/clauses/{value}/ancestry",
    ),
    ("recall_run", "GET /v1/recall-runs/{run_id}", "run_id", "/v1/recall-runs/{value}"),
    ("receipt", "GET /v1/receipts/{receipt_id}", "receipt_id", "/v1/receipts/{value}"),
    (
        "blocking_checks",
        "GET /v1/permits/{permit_id}/blocking-checks",
        "permit_id",
        "/v1/permits/{value}/blocking-checks",
    ),
    ("permit", "GET /v1/permits/{permit_id}", "permit_id", "/v1/permits/{value}"),
)


@dataclass(frozen=True, slots=True)
class RowSpec:
    """One line of the artefact: a word, an address, and the relation it must confirm as."""

    word: str
    source: str
    pointer: str
    relation: str
    claim: str
    #: Pointer to the timestamp column that dates this row. Equal to ``pointer`` when the
    #: value IS a timestamp.
    stamp_pointer: str
    stamp_relation_column: str
    #: Key into :func:`four_written_by` for a value whose provenance R9 demands beside it.
    four: str | None = None
    #: The column's real name, when the envelope renamed it. Derived from the pointer's last
    #: segment otherwise, which is the key the RESPONSE used.
    column_override: str | None = None
    #: ``column`` when the value is one; ``catalogue_expression`` when the catalogue rendered
    #: it. Stating this is cheaper than letting a reader assume every row is a column.
    column_kind: str = "column"


#: THE LOOP. Order is the story's order and the words are the brief's words.
ROWS: tuple[RowSpec, ...] = (
    # ── STORE ─────────────────────────────────────────────────────────────────────────
    RowSpec(
        "STORE",
        "ancestry",
        "/data/events/0/external_ref",
        "mainline.event",
        "the incident this world was taught, by the reference an investigator would quote",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/events/0/occurred_at",
        "mainline.event",
        "when it happened — outside any garbage-collection window on any tier, deliberately",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/events/0/severity_gate",
        "mainline.event",
        "how badly it went, and on whose authority (severity_basis, next row)",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
        four="event",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/events/0/severity_basis",
        "mainline.event",
        "the basis of that severity, stated as a column rather than assumed",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/blame_edges/0/event_id",
        "mainline.blame_edge",
        "THE EDGE — one end of it is the incident",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/blame_edges/0/clause_uuid",
        "mainline.blame_edge",
        "the other end is the clause the permit relies on: this is what was stored",
        "/data/events/0/occurred_at",
        "mainline.event.occurred_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/blame_edges/0/commit_id",
        "mainline.blame_edge",
        "and it names the clause VERSION, not the clause — a commit, so the memory cannot slide",
        "/data/commit_chain/0/committed_at",
        "mainline.commit_obj.committed_at",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/closure/max_severity",
        "mainline.clause_blame_current",
        "the ancestry projected into a closure the gate can read in one lookup",
        "/data/closure/computed_at",
        "mainline.clause_blame_current.computed_at",
        four="closure",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/closure/virulence",
        "mainline.clause_blame_current",
        "the band that severity falls in, stored beside it",
        "/data/closure/computed_at",
        "mainline.clause_blame_current.computed_at",
        four="closure",
    ),
    RowSpec(
        "STORE",
        "ancestry",
        "/data/closure/ancestor_count",
        "mainline.clause_blame_current",
        "how many events reach this clause version — one, and it is the 2019 one",
        "/data/closure/computed_at",
        "mainline.clause_blame_current.computed_at",
    ),
    # ── RETRIEVE ──────────────────────────────────────────────────────────────────────
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/started_at",
        "mainline_meas.recall_run",
        "THE MOMENT THE MEMORY WAS READ BACK — a column, and the left edge of the gap",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/counts/n_candidates",
        "mainline_meas.recall_run",
        "how many memories the pass surfaced",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/counts/n_blocking",
        "mainline_meas.recall_run",
        "how many of them block — the retrieval decided this, not a human",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/counts/n_silenced",
        "mainline_meas.recall_run",
        "how many were suppressed: none, so nothing was hidden from the signer",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/policy_version",
        "mainline_meas.recall_run",
        "under which retrieval policy — an anchored one, or the row could not exist",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/index_generation",
        "mainline_meas.recall_run",
        "against which generation of the index",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/index_plan_digest",
        "mainline_meas.recall_run",
        "and the digest of the plan it ran, so the retrieval is reproducible rather than recalled",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    RowSpec(
        "RETRIEVE",
        "recall_run",
        "/data/corpus_commit",
        "mainline_meas.recall_run",
        "over which corpus commit — the same commit the blame edge above names",
        "/data/started_at",
        "mainline_meas.recall_run.started_at",
    ),
    # ── SHOWN TO ──────────────────────────────────────────────────────────────────────
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/actor_sub",
        "mainline.exposure_receipt",
        "WHO WAS SHOWN IT — a memory nobody was shown cannot bind anybody",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/issued_at",
        "mainline.exposure_receipt",
        "when they were shown it",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/receipt_digest",
        "mainline.exposure_receipt",
        "the digest of what they were shown, so 'I was never told' is a checkable claim",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/policy_version",
        "mainline.exposure_receipt",
        "under the same retrieval policy the run above ran under",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/lines/0/check_id",
        "mainline.exposure_line",
        "and the line names the obligation itself — the receipt is about THIS memory",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    RowSpec(
        "SHOWN TO",
        "receipt",
        "/data/lines/0/payload_digest",
        "mainline.exposure_line",
        "digested per line, not per receipt",
        "/data/issued_at",
        "mainline.exposure_receipt.issued_at",
    ),
    # ── ACT ───────────────────────────────────────────────────────────────────────────
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check",
        "THE MOMENT THE MEMORY BECAME AN OBLIGATION — the right edge of the gap",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/origin",
        "mainline.blocking_check",
        "why it exists: blame ancestry — the obligation cites the memory as its cause",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/precursor_event_id",
        "mainline.blocking_check",
        "and names the 2019 incident by id, on the obligation row itself",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/recall_run_id",
        "mainline.blocking_check",
        "and the retrieval that found it, so ACT points back at RETRIEVE by foreign key",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/severity",
        "mainline.blocking_check",
        "the severity the obligation carries — PROJECTED onto it, never typed (R9)",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
        four="projected",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/virulence",
        "mainline.blocking_check",
        "and the band, projected by the same trigger under the same invariant",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
        four="projected",
    ),
    RowSpec(
        "ACT",
        "blocking_checks",
        "/data/checks/0/disposition_id",
        "mainline.disposition",
        "still open: the reader's lookup for a non-retracted disposition comes back null",
        "/data/checks/0/materialised_at",
        "mainline.blocking_check.materialised_at",
    ),
    RowSpec(
        "ACT",
        "permit",
        "/data/counters/open_blocking",
        "mainline.permit",
        "THE COUNTER THE MEMORY DROVE — one open obligation on this subject",
        "/data/opened_at",
        "mainline.permit.opened_at",
    ),
    RowSpec(
        "ACT",
        "permit",
        "/data/gate_epoch",
        "mainline.permit",
        "and the epoch the same trigger bumped, pinning the subject to a new (id, epoch) pair",
        "/data/opened_at",
        "mainline.permit.opened_at",
    ),
    RowSpec(
        "ACT",
        "permit",
        "/data/state",
        "mainline.permit",
        "while the client's own claim is that every obligation is disposed of. It is not.",
        "/data/opened_at",
        "mainline.permit.opened_at",
    ),
)

#: The counter the refusing CHECK reads. A column NAME — an address, like a route — used to
#: LOCATE the constraint in the permit payload rather than to state what it says. Both the
#: constraint's name and its predicate then come off the wire.
GATE_COUNTER_COLUMN = "open_blocking"

# ═════════════════════════════════════════════════════════════════════════════════════
# THE R9 CITATIONS — located by search, so the artefact carries file, line and the line
# ═════════════════════════════════════════════════════════════════════════════════════

#: ``(label, repo-relative path, the marker searched for)``. Nothing here is a value in the
#: loop; each is a needle, and what the artefact records is the haystack's own line.
R9_CITATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "the weld that makes MI25 a property of the database",
        "verticals/mainline/db/migrations/0120_trg_check_project.sql",
        "MI: MI25",
    ),
    (
        "what the seed supplies for the permit's obligation",
        "verticals/mainline/db/seeds/demo/demo_permit.sql",
        "projected over by fn_check_project (MI25)",
    ),
    (
        "the ruling, in the deployment's own database document",
        "docs/deploy/cloud-database.md",
        "overwritten by `fn_check_project`",
    ),
)

PROJECTOR = "mainline.fn_check_project"
PROJECTOR_INVARIANT = "MI25"
PROJECTOR_WELD = "0120_trg_check_project.sql (BEFORE INSERT, FOR EACH ROW)"

#: The seed's supplied severity/virulence, parsed out of the line R9_CITATIONS[1] locates.
_SUPPLIED = re.compile(r"^\s*(\d+),\s*'([a-z_]+)',\s*(\d+),")

#: A hex token long enough to be a digest. Masked before the year scan, because a sha256 may
#: legitimately contain any four digits and a false red teaches its reader to ignore the check.
_HEX = re.compile(r"\b[0-9a-f]{32,}\b")

#: R8's superseded year, assembled rather than written, so that the string this program
#: searches for is not itself a token in the document it searches.
SUPERSEDED_YEAR = str(2000 + 24)

#: A UUID anywhere in this file would break the rule stated in the module docstring.
_HEX4 = "[0-9a-fA-F]{4}"
_UUID = re.compile(rf"\b[0-9a-fA-F]{{8}}-{_HEX4}-{_HEX4}-{_HEX4}-[0-9a-fA-F]{{12}}\b")

#: Values shorter than this are not searched for textually — a "1" or a "4" occurs in any
#: source file, and a check that always fires is not a check. They carry the deployment's own
#: provenance chip instead, and the audit lists every one it exempted.
MIN_AUDITED_LENGTH = 5


class LoopError(RuntimeError):
    """The deployment did not answer, or answered something this loop cannot address."""


# ═════════════════════════════════════════════════════════════════════════════════════
# transport — GET only, https only, one header
# ═════════════════════════════════════════════════════════════════════════════════════


def _now() -> str:
    """This machine's clock, RFC 3339, UTC — the READING time, never the server's."""
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Response:
    name: str
    template: str
    path: str
    url: str
    status: int
    body: bytes
    read_at: str

    @property
    def doc(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def fetch(base: str, name: str, template: str, path: str, timeout_s: float) -> Response:
    """One ``GET``. A non-200 is recorded and then refused by the caller, never guessed at."""
    url = base.rstrip("/") + path
    if not url.startswith("https://"):
        raise LoopError(f"refusing a non-HTTPS URL: {url!r}")
    request = urllib.request.Request(url, method="GET", headers={"accept": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            status, raw = int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        status, raw = int(exc.code), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LoopError(f"GET {path}: transport failed: {exc}") from exc
    return Response(name, template, path, url, status, raw, _now())


# ═════════════════════════════════════════════════════════════════════════════════════
# RFC 6901, and the envelope's own provenance
# ═════════════════════════════════════════════════════════════════════════════════════

_MISSING = object()


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

    ``provenance`` addresses ``/data``, so the pointer is rebased before the lookup. The
    longest matching entry wins: the envelope chips ``/checks/0`` as ``db:column`` and lets
    that cover every column of the row, and rebasing to the exact leaf first means a field
    the envelope calls ``derived`` is never reported as a column.
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
        candidate = entry.get("pointer")
        chip = entry.get("chip")
        if not isinstance(candidate, str) or not isinstance(chip, str):
            continue
        covers = rebased == candidate or rebased.startswith(candidate + "/")
        if covers and (best is None or len(candidate) > best[0]):
            best = (len(candidate), chip)
    return None if best is None else best[1]


def statement_ref(envelope: Any, relation: str) -> dict[str, Any] | None:
    """The response's own ``statement_refs`` entry for *relation*, or ``None``."""
    entries = pointer_get(envelope, "/statement_refs")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("object") == relation:
            return entry
    return None


def column_in_sql(ref: dict[str, Any] | None, column: str) -> dict[str, Any]:
    """Whether the SQL the response returned actually names *column*, and how.

    A column that arrives under an alias is reported as one. ``text`` is ``null`` for most
    refs — the reader names the relation without publishing the statement — and that is
    recorded as NOT PUBLISHED rather than as a failure, because it is the reader's choice
    and not evidence of anything.
    """
    if ref is None:
        return {"checked": False, "why": "the response returned no statement_ref for this relation"}
    text = ref.get("text")
    if not isinstance(text, str):
        return {"checked": False, "why": "the response published no SQL text for this relation"}
    alias = re.search(rf"(\S[^,\n]*?)\s+AS\s+{re.escape(column)}\b", text)
    if alias is not None:
        return {
            "checked": True,
            "named": True,
            "is_alias": True,
            "select_expression": alias.group(1).strip(),
        }
    named = bool(re.search(rf"\b{re.escape(column)}\b", text))
    return {"checked": True, "named": named, "is_alias": False}


# ═════════════════════════════════════════════════════════════════════════════════════
# the repository citations R9 demands
# ═════════════════════════════════════════════════════════════════════════════════════


def locate(relative: str, needle: str) -> dict[str, Any]:
    """Find *needle* in *relative* and record the file, the 1-based line, and the line."""
    path = REPO_ROOT / relative
    found: dict[str, Any] = {"file": relative, "needle": needle, "found": False}
    if not path.is_file():
        found["why"] = "the file is not on disk"
        return found
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            found.update({"found": True, "line": number, "text": line.rstrip()})
            return found
    found["why"] = "the marker is not in the file"
    return found


def seed_carries(instant: str) -> dict[str, Any]:
    """Is the instant the DEPLOYMENT served written in a seed in this repository?

    Presence, not parsing. The instant the wire served is re-spelled in the seed's own
    ``TIMESTAMPTZ`` form and searched for; what comes back is a file, a line and the literal
    line. This is a corroboration between two independent artefacts — the running database
    and the checked-in seed — and it is reported with its own status so that NOT FOUND can
    never be read as agreement. No instant is written in this file; the needle is built from
    the value the deployment returned.
    """
    spelled = instant.replace("T", " ").replace("Z", "+00")
    result: dict[str, Any] = {"served_by_the_deployment": instant, "sought_in_the_seed": spelled}
    if not SEED_DIR.is_dir():
        result.update({"status": "NOT READ", "why": f"{SEED_DIR} is not a directory"})
        return result
    for path in sorted(SEED_DIR.glob("*.sql")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if spelled in line:
                result.update(
                    {
                        "status": "AGREES",
                        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "line": number,
                        "text": line.strip(),
                    }
                )
                return result
    result.update({"status": "DISAGREES", "why": "no seed in this repository carries that instant"})
    return result


def four_written_by(
    kind: str, wire: dict[str, Any], citations: list[dict[str, Any]]
) -> dict[str, Any]:
    """R9. Beside every ``4``, the thing that wrote it.

    Three writers, three different answers, and the difference is the whole point. Two of
    them publish their own provenance in columns the response carries; the third publishes
    nothing, because a trigger that overwrites a value leaves no column saying so — which is
    exactly why the claim is cited to the migration that welds it and to the seed line that
    supplies the value it overwrote.
    """
    if kind == "event":
        return {
            "written_by": "the seed, and the row says so",
            "stated_in_the_response_at": "/data/events/0/severity_basis",
            "value": wire.get("severity_basis"),
            "projected": False,
        }
    if kind == "closure":
        return {
            "written_by": wire.get("computed_by"),
            "projector_ver": wire.get("projector_ver"),
            "stated_in_the_response_at": [
                "/data/closure/computed_by",
                "/data/closure/projector_ver",
            ],
            "projected": False,
            "note": (
                "this is the ancestry fact the projector READS FROM; it is not the value "
                "the projector wrote"
            ),
        }
    return {
        "written_by": PROJECTOR,
        "invariant": PROJECTOR_INVARIANT,
        "weld": PROJECTOR_WELD,
        "projected": True,
        "the_seed_supplied_instead": wire.get("supplied"),
        "citations": citations,
        "sentence": (
            "nobody typed the four: the seed wrote what the citations show, and the "
            f"projection under {PROJECTOR_INVARIANT} overwrote it before the row landed"
        ),
    }


def supplied_by_the_seed(citation: dict[str, Any]) -> dict[str, Any]:
    """Parse ``severity, virulence, closure_gen`` out of the seed line R9 located."""
    text = citation.get("text")
    if not isinstance(text, str):
        return {"read": False, "why": "the seed line was not located"}
    match = _SUPPLIED.match(text)
    if match is None:
        return {"read": False, "why": "the located line did not match the supplied-values shape"}
    return {
        "read": True,
        "severity": int(match.group(1)),
        "virulence": match.group(2),
        "closure_gen": int(match.group(3)),
        "file": citation.get("file"),
        "line": citation.get("line"),
    }


# ═════════════════════════════════════════════════════════════════════════════════════
# building the rows
# ═════════════════════════════════════════════════════════════════════════════════════


def curl_for(url: str) -> str:
    return f"curl -s '{url}' | python -m json.tool"


def build_row(
    spec: RowSpec, responses: dict[str, Response], extras: dict[str, Any]
) -> dict[str, Any]:
    """One line of the artefact, with the four things the brief demands and their basis."""
    response = responses[spec.source]
    envelope = response.doc
    column = spec.column_override or spec.pointer.rsplit("/", 1)[-1]
    value = pointer_get(envelope, spec.pointer)
    stamp = pointer_get(envelope, spec.stamp_pointer)
    ref = statement_ref(envelope, spec.relation)

    row: dict[str, Any] = {
        "word": spec.word,
        "claim": spec.claim,
        "table_column": f"{spec.relation}.{column}",
        "relation": spec.relation,
        "column": column,
        "column_kind": spec.column_kind,
        "column_name_source": (
            "the response's own key at this pointer"
            if spec.column_override is None
            else "the envelope renamed it; the relation's real name is recorded here"
        ),
        "route": response.template,
        "url": response.url,
        "http_status": response.status,
        "pointer": spec.pointer,
        "value": None if value is _MISSING else value,
        "value_present": value is not _MISSING,
        "timestamp": {
            "table_column": spec.stamp_relation_column,
            "pointer": spec.stamp_pointer,
            "value": None if stamp is _MISSING else stamp,
            "is_the_value_itself": spec.stamp_pointer == spec.pointer,
        },
        "observed_at": jsonable(pointer_get(envelope, "/observed_at")),
        "read_at": response.read_at,
        "provenance_chip": chip_for(envelope, spec.pointer),
        "relation_confirmed_by_statement_refs": ref is not None,
        "statement_ref_kind": None if ref is None else ref.get("kind"),
        "column_named_in_published_sql": column_in_sql(ref, column),
        "curl": curl_for(response.url),
    }
    if spec.four is not None:
        row["written_by"] = four_written_by(spec.four, extras[spec.four], extras["citations"])
    return row


def published_sql(responses: dict[str, Response]) -> dict[str, Any]:
    """Every statement the deployment chose to publish, keyed by the relation it names.

    This is not decoration. It is what turns a row's ``table.column`` from an assertion by
    this program into something a reader can check against the query the origin says it ran.
    Relations whose reader publishes no text are listed with ``null`` rather than omitted,
    so *"the response named this relation and did not publish its statement"* is visible.
    """
    out: dict[str, Any] = {}
    for response in responses.values():
        entries = pointer_get(response.doc, "/statement_refs")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("object")
            if isinstance(name, str) and (name not in out or out[name] is None):
                out[name] = entry.get("text")
    return out


def locate_gate_constraint(permit: Response) -> tuple[int | None, dict[str, Any]]:
    """Find the CHECK whose counter is the one the memory drove — by counter, not by index.

    The constraint's NAME and its PREDICATE both arrive in the body; this only says which
    element of the array to read them out of, and it says it by looking for the column the
    counter lives in rather than by trusting a position that a schema change could move.
    """
    constraints = pointer_get(permit.doc, "/data/constraints")
    if not isinstance(constraints, list):
        return None, {"located": False, "why": "the permit payload carried no constraints array"}
    for index, entry in enumerate(constraints):
        counters = entry.get("counters") if isinstance(entry, dict) else None
        if not isinstance(counters, list):
            continue
        if any(isinstance(c, dict) and c.get("column") == GATE_COUNTER_COLUMN for c in counters):
            return index, {"located": True, "by": f"counters[].column == {GATE_COUNTER_COLUMN!r}"}
    return None, {"located": False, "why": f"no constraint reads {GATE_COUNTER_COLUMN!r}"}


def gate_rows(index: int) -> list[RowSpec]:
    """The two rows that say what the CHECK is and what it refuses, at the located index."""
    return [
        RowSpec(
            "ACT",
            "permit",
            f"/data/constraints/{index}/constraint",
            "pg_catalog.pg_constraint",
            "THE CHECK THE MEMORY ARMED — named by the catalogue, not by us",
            "/data/opened_at",
            "mainline.permit.opened_at",
            column_override="conname",
        ),
        RowSpec(
            "ACT",
            "permit",
            f"/data/constraints/{index}/predicate",
            "pg_catalog.pg_constraint",
            "and its predicate, verbatim: this is the sentence the database refuses on",
            "/data/opened_at",
            "mainline.permit.opened_at",
            column_override="pg_get_constraintdef(oid)",
            column_kind="catalogue_expression",
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# the gap, computed
# ═════════════════════════════════════════════════════════════════════════════════════


def _parse(instant: Any) -> datetime | None:
    if not isinstance(instant, str):
        return None
    try:
        return datetime.fromisoformat(instant.replace("Z", "+00:00"))
    except ValueError:
        return None


def compute_gap(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """RETRIEVE -> ACT, subtracted from two columns that arrived in two different responses."""
    left = next(
        (r for r in rows if r["table_column"] == "mainline_meas.recall_run.started_at"), None
    )
    right = next(
        (r for r in rows if r["table_column"] == "mainline.blocking_check.materialised_at"), None
    )
    gap: dict[str, Any] = {
        "claim": "the gap between RETRIEVE and ACT is a subtraction of two columns",
        "from": None
        if left is None
        else {k: left[k] for k in ("word", "table_column", "route", "pointer", "value")},
        "to": None
        if right is None
        else {k: right[k] for k in ("word", "table_column", "route", "pointer", "value")},
        "computed_here": True,
        "stated_anywhere_in_this_program": False,
    }
    a = _parse(None if left is None else left["value"])
    b = _parse(None if right is None else right["value"])
    if a is None or b is None:
        gap.update({"seconds": None, "why": "one of the two columns did not parse as an instant"})
        return gap
    gap["seconds"] = (b - a).total_seconds()
    gap["how"] = "datetime(materialised_at) - datetime(started_at), both ISO-8601 off the wire"
    gap["corroboration"] = {
        "why": "the running database and the checked-in seed are two independent artefacts",
        "retrieve": seed_carries(left["value"]),  # type: ignore[index]
        "act": seed_carries(right["value"]),  # type: ignore[index]
    }
    return gap


# ═════════════════════════════════════════════════════════════════════════════════════
# the audit
# ═════════════════════════════════════════════════════════════════════════════════════


def _walk(node: Any, pointer: str = "") -> list[tuple[str, Any]]:
    if isinstance(node, dict):
        return [p for k, v in node.items() for p in _walk(v, f"{pointer}/{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in _walk(v, f"{pointer}/{i}")]
    return [(pointer, node)]


def measured_values(
    rows: list[dict[str, Any]], subject: dict[str, Any], health: dict[str, Any]
) -> list[tuple[str, Any]]:
    """Every value in this artefact that came off the wire, with where it sits."""
    values: list[tuple[str, Any]] = []
    for index, row in enumerate(rows):
        values.append((f"/loop/{index}/value", row["value"]))
        values.append((f"/loop/{index}/timestamp/value", row["timestamp"]["value"]))
    values.extend(_walk(subject, "/subject"))
    values.extend(_walk(health, "/deployment"))
    return [(p, v) for p, v in values if v is not None]


def _occurs(text: str, source: str) -> bool:
    """Does *text* occur in *source* AS ITSELF, rather than inside a longer identifier?

    Substring is the stronger test and is the one used, with one boundary rule: a match
    whose neighbours are identifier characters is not an occurrence of the value. The
    database is called by a name that is a PREFIX of the package that serves it, so a plain
    substring test reports the module path in this file's own route-table citation as though
    it were the database name copied out of a response. Refusing that is precision, not
    leniency — every other match still counts, including one inside a comment or a docstring,
    which is exactly how this audit first went red.
    """
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(text)}(?![A-Za-z0-9_])", source) is not None


def self_audit(
    rows: list[dict[str, Any]], subject: dict[str, Any], health: dict[str, Any]
) -> dict[str, Any]:
    """Grep this program's own bytes for every value the artefact records.

    The claim being tested is the brief's: *no value in the artefact originates in the
    script's own source*. It is tested rather than asserted, and its exemption is stated in
    the artefact rather than left implicit — a value of fewer than
    :data:`MIN_AUDITED_LENGTH` characters occurs in any source file by coincidence, so those
    are listed individually with the deployment's own provenance chip instead.
    """
    source = SOURCE_FILE.read_text(encoding="utf-8")
    values = measured_values(rows, subject, health)
    hits: list[dict[str, Any]] = []
    exempt: list[dict[str, Any]] = []
    for pointer, value in values:
        text = value if isinstance(value, str) else json.dumps(value)
        if len(text) < MIN_AUDITED_LENGTH:
            exempt.append({"pointer": pointer, "value": value})
            continue
        if _occurs(text, source):
            hits.append({"pointer": pointer, "value": value})
    return {
        "claim": "no value in this artefact originates in scripts/proof/memory_loop.py",
        "source": str(SOURCE_FILE).replace("\\", "/"),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_bytes": len(source.encode("utf-8")),
        "uuid_literals_in_the_source": len(_UUID.findall(source)),
        "values_audited": len(values) - len(exempt),
        "values_found_in_the_source": hits,
        "scope": (
            "every measured value: the loop's values and timestamps, the subjects, and the "
            "deployment identity. The ADDRESSES — route templates, RFC 6901 pointers and "
            "relation names — are this program's contribution and are named as such; the "
            "relation names are confirmed against each response's own statement_refs."
        ),
        "short_value_exemption": {
            "min_audited_length": MIN_AUDITED_LENGTH,
            "why": "a value of one to four characters occurs in any source file by coincidence",
            "boundary_rule": (
                "a match flanked by identifier characters is not an occurrence of the value: "
                "the database's name is a prefix of the package that serves it"
            ),
            "instead": "each carries the deployment's own provenance chip, listed in its row",
            "exempted": exempt,
        },
    }


def year_scan(document: str) -> dict[str, Any]:
    """R8. The superseded year appears in no non-digest text of this document."""
    masked, digests = _HEX.subn("<digest>", document)
    return {
        "ruling": "R8",
        "superseded_year_occurrences": masked.count(SUPERSEDED_YEAR),
        "incident_date_occurrences": masked.count("2019-03-14"),
        "digests_masked_before_scanning": digests,
        "why_masked": (
            "a sha256 may legitimately contain any four digits, and a check that fires on "
            "one teaches its reader to ignore it"
        ),
    }


# ═════════════════════════════════════════════════════════════════════════════════════
# the assertions
# ═════════════════════════════════════════════════════════════════════════════════════


def _v(rows: list[dict[str, Any]], table_column: str) -> Any:
    row = next((r for r in rows if r["table_column"] == table_column), None)
    return None if row is None else row["value"]


def cross_response_identities(rows: list[dict[str, Any]]) -> list[tuple[str, str, bool, str]]:
    """The loop is one loop, and these are the joins that make it one.

    Each compares a value from ONE response against a value from ANOTHER. Nothing here can
    hold by construction: two responses agreeing about an identifier is a fact about the
    database, not about this program.
    """
    pairs = (
        (
            "store_names_the_clause_version_the_obligation_cites",
            "the blame edge's commit is the commit on the obligation",
            "mainline.blame_edge.commit_id",
            "mainline.blocking_check.commit_id",
        ),
        (
            "store_is_the_precursor_the_obligation_names",
            "the blame edge's event is the obligation's precursor",
            "mainline.blame_edge.event_id",
            "mainline.blocking_check.precursor_event_id",
        ),
        (
            "act_points_back_at_retrieve",
            "the obligation names the recall run that found the memory",
            "mainline_meas.recall_run.run_id",
            "mainline.blocking_check.recall_run_id",
        ),
        (
            "shown_to_is_about_this_obligation",
            "the receipt line names the obligation",
            "mainline.exposure_line.check_id",
            "mainline.blocking_check.check_id",
        ),
        (
            "retrieve_and_shown_to_share_the_policy",
            "the receipt was issued under the policy the run ran under",
            "mainline_meas.recall_run.policy_version",
            "mainline.exposure_receipt.policy_version",
        ),
        (
            "retrieve_ran_over_the_clause_version_store_wrote",
            "the run's corpus commit is the commit the ancestry is as-of",
            "mainline_meas.recall_run.corpus_commit",
            "mainline.clause_blame_current.as_of_commit",
        ),
        (
            "the_projection_took_the_ancestry_severity",
            "the obligation's severity is the closure's, not the one the seed supplied",
            "mainline.clause_blame_current.max_severity",
            "mainline.blocking_check.severity",
        ),
        (
            "the_projection_took_the_ancestry_band",
            "the obligation's virulence is the closure's",
            "mainline.clause_blame_current.virulence",
            "mainline.blocking_check.virulence",
        ),
    )
    out: list[tuple[str, str, bool, str]] = []
    for name, claim, left_tc, right_tc in pairs:
        left, right = _v(rows, left_tc), _v(rows, right_tc)
        out.append(
            (
                name,
                claim,
                left is not None and left == right,
                f"{left_tc}={left!r} vs {right_tc}={right!r}",
            )
        )
    return out


def build_assertions(
    rows: list[dict[str, Any]],
    joins: list[dict[str, Any]],
    gap: dict[str, Any],
    supplied: dict[str, Any],
    audit: dict[str, Any],
    scan: dict[str, Any],
    responses: dict[str, Response],
    open_checks: int,
) -> list[dict[str, Any]]:
    """Every clause of the artefact's claim, as something that can turn the verdict red."""
    incident = _v(rows, "mainline.event.occurred_at")
    open_blocking = _v(rows, "mainline.permit.open_blocking")
    predicate = _v(rows, "pg_catalog.pg_constraint.pg_get_constraintdef(oid)")
    checks: list[tuple[str, str, bool, str]] = [
        (
            "every_route_answered_200",
            "each of the reads this loop is drawn from answered 200",
            all(r.status == 200 for r in responses.values()),
            ", ".join(f"{r.name}={r.status}" for r in responses.values()),
        ),
        (
            "every_row_carried_a_value",
            "no row's pointer missed in the body it addressed",
            all(r["value_present"] for r in rows),
            f"{sum(1 for r in rows if r['value_present'])}/{len(rows)}",
        ),
        (
            "every_relation_was_confirmed_by_the_response",
            "each row's relation appears in the statement_refs of the response that carried it",
            all(r["relation_confirmed_by_statement_refs"] for r in rows),
            f"{sum(1 for r in rows if r['relation_confirmed_by_statement_refs'])}/{len(rows)}",
        ),
        *[(j["id"], j["claim"], j["holds"], j["observed"]) for j in joins],
        (
            "retrieve_precedes_act",
            "the memory was read back before it became an obligation",
            isinstance(gap.get("seconds"), float) and gap["seconds"] > 0,
            f"gap={gap.get('seconds')}s",
        ),
        (
            "the_gap_is_corroborated_by_the_seed",
            "both instants the deployment served are written in a seed in this repository",
            gap.get("corroboration", {}).get("retrieve", {}).get("status") == "AGREES"
            and gap.get("corroboration", {}).get("act", {}).get("status") == "AGREES",
            (
                f"retrieve={gap.get('corroboration', {}).get('retrieve', {}).get('status')} "
                f"act={gap.get('corroboration', {}).get('act', {}).get('status')}"
            ),
        ),
        (
            "the_seed_line_was_read",
            "the values the seed supplies for the obligation were read off disk, not assumed",
            bool(supplied.get("read")),
            json.dumps(supplied),
        ),
        (
            "severity_was_projected_not_typed",
            "the severity on the obligation is not the severity the seed supplied",
            bool(supplied.get("read"))
            and _v(rows, "mainline.blocking_check.severity") != supplied.get("severity"),
            (
                f"wire={_v(rows, 'mainline.blocking_check.severity')!r} "
                f"seed={supplied.get('severity')!r}"
            ),
        ),
        (
            "virulence_was_projected_not_typed",
            "the band on the obligation is not the band the seed supplied",
            bool(supplied.get("read"))
            and _v(rows, "mainline.blocking_check.virulence") != supplied.get("virulence"),
            (
                f"wire={_v(rows, 'mainline.blocking_check.virulence')!r} "
                f"seed={supplied.get('virulence')!r}"
            ),
        ),
        (
            "the_counter_equals_the_open_obligations",
            "the counter the CHECK reads agrees with the obligations that are actually open",
            open_blocking == open_checks,
            f"open_blocking={open_blocking!r} open_obligations={open_checks}",
        ),
        (
            "the_check_reads_that_counter_and_demands_zero",
            "the predicate the catalogue returned demands the counter be zero to merge",
            isinstance(predicate, str) and f"{GATE_COUNTER_COLUMN} = 0" in predicate,
            repr(predicate),
        ),
        (
            "the_counter_is_not_zero",
            "so the subject cannot be merged while the memory stands",
            isinstance(open_blocking, int) and open_blocking > 0,
            f"open_blocking={open_blocking!r}",
        ),
        (
            "the_incident_is_the_2019_one",
            "R8: the precursor occurred on 2019-03-14 and nothing was rewritten",
            isinstance(incident, str) and incident.startswith("2019-03-14"),
            repr(incident),
        ),
        (
            "no_measured_value_originates_in_this_source",
            audit["claim"],
            not audit["values_found_in_the_source"] and audit["uuid_literals_in_the_source"] == 0,
            (
                f"hits={len(audit['values_found_in_the_source'])} "
                f"uuids={audit['uuid_literals_in_the_source']}"
            ),
        ),
        (
            "the_superseded_year_is_absent",
            "R8: the year this repository's rulings name as wrong appears nowhere",
            scan["superseded_year_occurrences"] == 0,
            f"occurrences={scan['superseded_year_occurrences']}",
        ),
        (
            "the_incident_date_is_present",
            "and the date that is right appears on the artefact's face",
            scan["incident_date_occurrences"] > 0,
            f"occurrences={scan['incident_date_occurrences']}",
        ),
    ]
    return [
        {"id": name, "claim": claim, "holds": holds, "observed": observed}
        for name, claim, holds, observed in checks
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


def read_subjects(base: str, timeout_s: float) -> tuple[Response, dict[str, Any]]:
    """Address the whole loop from the deployment's own answer to *which subjects are here*."""
    response = fetch(base, "subjects", f"GET {SUBJECTS_PATH}", SUBJECTS_PATH, timeout_s)
    if response.status != 200:
        raise LoopError(
            f"GET {SUBJECTS_PATH} answered {response.status}; the loop is unaddressable"
        )
    data = pointer_get(response.doc, "/data")
    if not isinstance(data, dict):
        raise LoopError(f"GET {SUBJECTS_PATH} returned no data object")
    return response, data


def collect(
    base: str, timeout_s: float
) -> tuple[dict[str, Response], dict[str, Any], Response, Response]:
    subjects_response, subjects = read_subjects(base, timeout_s)
    health = fetch(base, "health", f"GET {HEALTH_PATH}", HEALTH_PATH, timeout_s)
    responses: dict[str, Response] = {}
    for name, template, key, path_template in READS:
        value = subjects.get(key)
        if not isinstance(value, str):
            raise LoopError(f"{SUBJECTS_PATH} carried no {key!r}; nothing may be guessed")
        responses[name] = fetch(base, name, template, path_template.format(value=value), timeout_s)
    return responses, subjects, subjects_response, health


def assemble(base: str, timeout_s: float) -> tuple[dict[str, Any], bool]:
    responses, subjects, subjects_response, health = collect(base, timeout_s)

    citations = [
        {"what": what, **locate(relative, needle)} for what, relative, needle in R9_CITATIONS
    ]
    supplied = supplied_by_the_seed(citations[1])
    extras = {
        "event": jsonable(pointer_get(responses["ancestry"].doc, "/data/events/0")) or {},
        "closure": jsonable(pointer_get(responses["ancestry"].doc, "/data/closure")) or {},
        "projected": {"supplied": supplied},
        "citations": citations,
    }

    index, located = locate_gate_constraint(responses["permit"])
    specs = list(ROWS) + (gate_rows(index) if index is not None else [])
    rows = [build_row(spec, responses, extras) for spec in specs]

    # The identity columns the joins need, addressed the same way every other row is.
    for spec in (
        RowSpec(
            "ACT",
            "blocking_checks",
            "/data/checks/0/commit_id",
            "mainline.blocking_check",
            "the commit the obligation cites",
            "/data/checks/0/materialised_at",
            "mainline.blocking_check.materialised_at",
        ),
        RowSpec(
            "ACT",
            "blocking_checks",
            "/data/checks/0/check_id",
            "mainline.blocking_check",
            "the obligation's own identity",
            "/data/checks/0/materialised_at",
            "mainline.blocking_check.materialised_at",
        ),
        RowSpec(
            "RETRIEVE",
            "recall_run",
            "/data/run_id",
            "mainline_meas.recall_run",
            "the run's own identity",
            "/data/started_at",
            "mainline_meas.recall_run.started_at",
        ),
        RowSpec(
            "STORE",
            "ancestry",
            "/data/as_of_commit",
            "mainline.clause_blame_current",
            "the commit the ancestry is as-of",
            "/data/closure/computed_at",
            "mainline.clause_blame_current.computed_at",
        ),
    ):
        rows.append(build_row(spec, responses, extras))

    joins = [
        {"id": name, "claim": claim, "holds": holds, "observed": observed}
        for name, claim, holds, observed in cross_response_identities(rows)
    ]
    gap = compute_gap(rows)
    subject_block = {
        "resolved_from": f"GET {SUBJECTS_PATH}",
        "not_one_of_these_is_a_literal_in_this_program": True,
        "ids": {key: subjects.get(key) for _, _, key, _ in READS},
    }
    health_block = {
        "route": f"GET {HEALTH_PATH}",
        "url": health.url,
        "http_status": health.status,
        "body": health.doc if health.status == 200 else None,
    }
    audit = self_audit(rows, subject_block["ids"], health_block.get("body") or {})

    document: dict[str, Any] = {
        "artefact": "STORE -> RETRIEVE -> SHOWN TO -> ACT, measured on the deployment",
        "generated_at": _now(),
        "generated_by": "scripts/proof/memory_loop.py",
        "command": "python scripts/proof/memory_loop.py --base-url <the live URL>",
        "ruling": {
            "R7": "the loop needs no new endpoint; every word is already a live GET",
            "R8": "the incident is 2019-03-14 and nothing was rewritten",
            "R9": "the obligation's severity and band are projected; every 4 names its writer",
        },
        "route_table": list(ROUTE_TABLE),
        "base_url": base.rstrip("/"),
        "deployment": health_block,
        "subject": subject_block,
        "requests": [
            {
                "name": r.name,
                "route": r.template,
                "url": r.url,
                "http_status": r.status,
                "bytes": len(r.body),
                "sha256": hashlib.sha256(r.body).hexdigest(),
                "read_at": r.read_at,
                "resource": jsonable(pointer_get(r.doc, "/resource")),
                "schema_id": jsonable(pointer_get(r.doc, "/schema_id")),
                "observed_at": jsonable(pointer_get(r.doc, "/observed_at")),
                "curl": curl_for(r.url),
            }
            for r in (subjects_response, health, *responses.values())
        ],
        "the_gate_constraint_was_located": located,
        "published_sql": published_sql(responses),
        "loop": rows,
        "cross_response_identities": joins,
        "gap": gap,
        "projection": {
            "ruling": "R9",
            "projector": PROJECTOR,
            "invariant": PROJECTOR_INVARIANT,
            "weld": PROJECTOR_WELD,
            "supplied_by_the_seed": supplied,
            "citations": citations,
            "sentence": (
                "a 4 with no provenance is a number somebody could have typed; every 4 in "
                "this artefact carries the thing that wrote it"
            ),
        },
        "self_audit": audit,
    }
    scan = year_scan(json.dumps(document, ensure_ascii=False))
    document["year_scan"] = scan
    checks = pointer_get(responses["blocking_checks"].doc, "/data/checks")
    open_checks = (
        sum(1 for c in checks if isinstance(c, dict) and c.get("open") is True)
        if isinstance(checks, list)
        else -1
    )
    assertions = build_assertions(rows, joins, gap, supplied, audit, scan, responses, open_checks)
    document["assertions"] = assertions
    document["assertions_total"] = len(assertions)
    document["assertions_held"] = sum(1 for a in assertions if a["holds"])
    failed = [a for a in assertions if not a["holds"]]
    document["assertions_failed"] = [a["id"] for a in failed]
    document["verdict"] = "PROVEN" if not failed else "NOT PROVEN"
    return document, not failed


def summarise(document: dict[str, Any]) -> None:
    print(f"verdict            {document['verdict']}")
    print(f"base url           {document['base_url']}")
    print(f"rows               {len(document['loop'])}")
    print(f"assertions         {document['assertions_held']}/{document['assertions_total']} held")
    gap = document["gap"]
    print(f"gap                {gap.get('seconds')} s  (computed, not stated)")
    for word in ("STORE", "RETRIEVE", "SHOWN TO", "ACT"):
        rows = [r for r in document["loop"] if r["word"] == word]
        print(f"  {word:<9}        {len(rows)} rows")
    for failure in document["assertions"]:
        if not failure["holds"]:
            print(f"  FAILED  {failure['id']}: {failure['observed']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render STORE -> RETRIEVE -> SHOWN TO -> ACT off the live deployment."
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="the deployment's origin. REQUIRED: a default here would be a value this "
        "artefact took from its own source.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)

    try:
        document, proven = assemble(args.base_url, args.timeout)
    except LoopError as exc:
        print(f"the deployment could not be walked: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"the deployment answered something that is not JSON: {exc}", file=sys.stderr)
        return EXIT_USAGE

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summarise(document)
    print(f"wrote              {args.out.resolve()}")
    return EXIT_PROVEN if proven else EXIT_NOT_PROVEN


if __name__ == "__main__":
    raise SystemExit(main())
