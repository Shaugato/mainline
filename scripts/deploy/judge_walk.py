#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE JUDGE'S WALK — one URL in, one record of what the deployment actually answers out.

WHY THIS FILE EXISTS, AND WHY IT IS NOT ``post_apply_verify.py``
================================================================
``docs/leads/package-and-verify-plan.md`` ruling **R8**. ``scripts/deploy/post_apply_verify.py``
is the operator's instrument: it reads ``terraform output`` for the Function URL, calls AWS
for alarm inventory and metric visibility, and drives the kill switch. Every one of those
needs credentials and a state file. A judge has neither, and neither does a founder opening
the demo on a laptop that never ran ``terraform init``.

So this program takes **a base URL and nothing else**. It runs from a bare checkout — from
no checkout at all, if the enumeration can be fetched from the origin — opens no AWS client,
knows no Terraform verb, and reads no credential. It exists so that the sentence *"the demo
works"* can be replaced by a file somebody else can regenerate.

WHAT IT MEASURES, IN ORDER
==========================
1. ``GET /`` is 200 and the bytes are the console shell — a doctype, the ``#root`` mount, and
   at least one ``./assets/*.js`` and one ``./assets/*.css`` reference. Measured 2026-08-14
   against the live Function URL: **200, 4,655 B**, referencing ``assets/index-DzVoV1YM.js``
   and ``assets/index-C498vmEA.css``.
2. **The transport badge, read out of the shipped bytes rather than off the screen.** There
   is no browser in this lane and none is added: the referenced entry chunks are fetched and
   the compiled ``VITE_MAINLINE_*`` literals are extracted with the same regex family
   ``scripts/deploy/build_lambda.sh`` uses (``ENV_LITERAL`` there, :data:`ENV_LITERAL` here),
   then ``src/app/source-select.ts``'s own rules are applied — ``trimmed()`` first, so an
   empty or whitespace value is **UNSET exactly as it is in the browser**, then the three
   selection rules. That is the whole of FAULT 1: the artefact that reached the founder
   carried ``VITE_MAINLINE_API_BASE:""`` and ``VITE_MAINLINE_BUNDLE_URL:"./bundle/"``, so
   ``selectSource`` returned REPLAY and every byte on screen was a recording.
3. ``GET /v1/health``.
4. **Every request the artefact itself declares.** Ruling **R10**: the EvidenceBundle the
   console ships is a machine-readable enumeration of every request the console makes, and
   the REPLAY counterpart of each. The walk reads ``manifest.json`` — from the origin, at the
   bundle URL *the artefact was compiled with*, falling back to the repository copy and
   **saying which one it used** — and drives every frame under ``frames/``. No endpoint list
   is re-derived here; a hand-written list is a list that drifts from the console silently.
5. ``POST /v1/demo/gate-run`` — the headline beat, and the one whose four SQLSTATEs
   (``00000 -> 23514 -> P0001 -> 00000``) are the demo's entire argument.

THE POINT OF THE WHOLE PROGRAM: THREE OUTCOMES, AND A CLOSED SET OF REASONS
===========================================================================
``dsn_unset`` is the **correct** answer today. The SSM parameter ``/mainline/demo/cockroach_dsn``
is the founder's step and nobody else's; until it lands, ``/v1/health`` answers
``ok=false reason=dsn_unset`` and every kernel route answers ``503 kind=dsn_unset``, each
naming ``ParameterNotFound`` as the cause. **The origin is up, the route is reachable, and
the SSM parameter is the founder's remaining step** — a 503 with a named cause is not a 404.

A walk that exits red for that would teach its reader to ignore it tomorrow. A walk that
exits green while saying nothing is worse. So there are exactly three outcomes —

    SATISFIED   the deployment answered what it was supposed to answer.
    REFUSED     it refused FOR A NAMED REASON, from the closed set below, and that refusal
                is the correct behaviour of a correct deployment in a known state.
    FAILED      anything else.

— and the reason set is **closed and written down** (:data:`NAMED_REASONS`). ``REFUSED``
without a reason from that table is not representable: :class:`Step` raises. That is the
anti-laundering property this program is built around, because a soft middle with an open
vocabulary is how "not satisfied" becomes "fine" one commit at a time.

Exit ``0`` when nothing FAILED. Exit ``1`` when anything did.

WHY A REPLAY ARTEFACT IS **FAILED** AND NOT A NAMED REASON
==========================================================
The two are not the same kind of thing and the exit code must not pretend they are.
``dsn_unset`` is a **correct deployment** answering correctly about a step that belongs to
somebody else; a REPLAY console is a **wrong artefact**, and it is the exact defect the
founder found by opening the URL. Filing FAULT 1 in the same exit-neutral drawer as the SSM
parameter would hand a judge a green walk while they look at a recording. So the transport
step FAILS, loudly, with the compiled literals quoted in its sentence.

Measured 2026-08-14 against the deployed Function URL, with this program:

    23 steps: 2 satisfied, 20 refused (dsn_unset), 1 FAILED (transport: REPLAY) -> exit 1
    with --allow-replay:  21 refused, 0 failed                                  -> exit 0

``--allow-replay`` is the only way to the second line and it must be **typed on the command
line** — ruling R7's shape, which ``build_lambda`` already uses for the same variable: *the
opt-out is a sentence somebody wrote, not a default.* A document produced that way is stamped
``allow_replay_declared: true`` and says so in the refusal, so it can never be cited as a
reading of a LIVE artefact. Once W1's rebuild and the orchestrator's redeploy land, the bare
command exits 0 with ``dsn_unset`` recorded, which is the state §6 of the lead's plan
describes.

WHAT THIS PROGRAM WILL NOT DO
=============================
* **It never applies anything and never redeploys.** It knows no Terraform verb and no AWS
  API. It makes HTTP requests and reads files.
* **It never writes ``/mainline/demo/cockroach_dsn``**, never asks for it, and never prints a
  DSN: :func:`mask` collapses every ``postgres(ql)://`` URL, every embedded ``user:password@``
  and every bare twelve-digit run before anything reaches stdout or the evidence file.
* **It never grades a synthetic answer as a live reading.** Every :class:`Step` carries
  ``source`` — ``"live"`` when a socket was opened, ``"synthetic"`` when a control in
  ``tests/deploy/test_judge_walk.py`` supplied the answer — and the document repeats it at
  the top level, so a run under fault injection can never be cited as a measurement.

THE SEAM, AND WHY IT IS NOT A MODE
==================================
:class:`Probes` bundles two collaborators: an HTTP client and a file reader. In production
both open real handles. In ``tests/deploy/test_judge_walk.py`` both are synthetics that answer
with constructed faults, which is how every refusal below is demonstrated **firing** — each
paired with a mutant of this file with that one check removed which does **not** refuse the
same input. There is no ``--simulate`` flag and no code path in which this program invents an
answer: an unscripted request in the controls is an error, never a 200.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

#: The three outcomes. There is no fourth, and no soft middle: "could not be attempted" is a
#: FAILED whose sentence says it could not be attempted.
SATISFIED = "SATISFIED"
REFUSED = "REFUSED"
FAILED = "FAILED"

OUTCOMES = (SATISFIED, REFUSED, FAILED)

#: The CLOSED set of reasons a refusal may name, each with the owner of the remaining step.
#: A reason not in this table cannot be recorded — :class:`Step` raises — which is what stops
#: this category from becoming the drawer everything inconvenient is filed in.
NAMED_REASONS: dict[str, str] = {
    "dsn_unset": (
        "the origin is up, the route is reachable, and the SSM parameter is the founder's "
        "remaining step. /mainline/demo/cockroach_dsn does not exist in ap-southeast-1, so "
        "the handler cannot open a database connection and says so in one word. A 503 that "
        "names its cause is a reachable route; a 404 would be an absent one."
    ),
    "retry_40001": (
        "the gate run was aborted by SQLSTATE 40001 and the transaction was UNDECIDED, which "
        "the contract says is NOT a refusal. gate-run.schema.json: 'this driver does not "
        "re-send on the caller's behalf.' Re-run the walk; a retry is contention, not a "
        "verdict."
    ),
    "console_replay_declared": (
        "the artefact serves a REPLAY console and the operator declared that in words with "
        "--allow-replay. The remaining step is a rebuild carrying VITE_MAINLINE_API_BASE and "
        "a redeploy by the orchestrator; see docs/leads/package-and-verify-plan.md R2. This "
        "run's document is stamped allow_replay_declared=true and cannot be cited as a "
        "reading of a LIVE artefact."
    ),
}

#: ``scripts/deploy/build_lambda.sh``'s ``ASSET_REF``, transcribed. The shell references its
#: chunks relative — ``src="./assets/index-*.js"`` — because the console must load from
#: ``file://`` and from an air-gapped static host.
ASSET_REF = re.compile(r'(?:src|href)="\./(assets/[^"?#]+)')

#: ``build_lambda.sh``'s ``ENV_LITERAL``, verbatim. One regex family for one fact: the packer
#: and the walk must read the same literals out of the same bytes, or the guard and the
#: measurement are two places holding one fact — which is precisely the disagreement
#: ``src/app/source-select.ts`` warns about and FAULT 1 was made of.
ENV_LITERAL = re.compile(r'(VITE_MAINLINE_[A-Z_]+):"((?:[^"\\]|\\.)*)"')
ENV_MODE = re.compile(r'MODE:"([^"]*)"')
BUILD_ID_LITERAL = re.compile(r'buildId:"((?:[^"\\]|\\.)*)"')

#: ``src/app/source-select.ts``'s two variables, by the source each selects.
SOURCE_VARIABLE = {"live": "VITE_MAINLINE_API_BASE", "replay": "VITE_MAINLINE_BUNDLE_URL"}

#: Where the bundle lives when the artefact does not name one. ``.env.demo`` compiles
#: ``./bundle/``; this is the fallback for an artefact built LIVE-only.
DEFAULT_BUNDLE_PATH = "bundle/"

#: The repository copy of the same EvidenceBundle, used only when the origin will not serve
#: it — and the document says which one was used, every time.
REPO_BUNDLE = "verticals/mainline/apps/console/fixtures/bundles/demo-cloud"

#: The demo route. Not addressable from the console as of 2026-08-14 (FAULT 2, W3's fix), but
#: reachable on the wire: the orchestrator measured 503 ``kind="dsn_unset"``, not 404.
GATE_RUN_PATH = "v1/demo/gate-run"
HEALTH_PATH = "v1/health"

#: The four beats and the SQLSTATE each must produce. TRANSCRIBED, with its source named:
#: ``scripts/deploy/demo_acceptance.py``'s ``EXPECTED_BEATS`` and
#: ``scripts/deploy/post_apply_verify.py``'s copy of it, both of which are checked against
#: ``verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`` and the prose contract
#: ``docs/deploy/gate-run-contract.md``. The committed schema is authoritative for what the
#: demo must carry; this table is derived from it and never the other way round.
#:
#: The schema pins the beat NAMES (``read``/``merge``/``projection_drift_attack``/``admit``)
#: and the SHAPE of each beat, but not the sequence of codes — so the sequence is carried
#: here AND cross-checked against each beat's own ``expected`` block, which the payload
#: carries precisely so that "a reader can check the driver's arithmetic instead of taking
#: matched_expectation on trust". Two independent statements of one fact are only a hazard
#: when nobody compares them; :func:`check_gate_run` compares them.
EXPECTED_BEATS: tuple[dict[str, Any], ...] = (
    {"ordinal": 1, "name": "read", "outcome": "read", "sqlstate": "00000", "constraint": None},
    {
        "ordinal": 2,
        "name": "merge",
        "outcome": "refused",
        "sqlstate": "23514",
        "constraint": "gate_closed_when_issued",
    },
    {
        "ordinal": 3,
        "name": "projection_drift_attack",
        "outcome": "refused",
        "sqlstate": "P0001",
        "constraint": "mainline.fn_permit_merge_gate",
    },
    {"ordinal": 4, "name": "admit", "outcome": "admitted", "sqlstate": "00000", "constraint": None},
)

#: A UUID, matched ONLY so that it can be left alone. The demo's subjects are UUIDs whose
#: last group is twelve digits — ``dec0de00-0006-4000-8000-000000000001`` — and a masker that
#: keyed on twelve digits alone collapsed the permit ids out of this walk's own record on the
#: first run against the live URL. Measured, not imagined. The alternation below puts this
#: branch FIRST, so at a UUID's start the whole UUID matches and its trailing group is never
#: offered to the account branch; an account id inside an ARN, which is delimited by ``:``
#: rather than by hex groups, still matches. Masking the demo's identifiers would not be
#: safety, it would be an evidence file a reader cannot check against the seed.
_UUID_TEXT = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

#: Any bare twelve-digit run — an AWS account id, most often inside an ARN in an error
#: message, which is exactly the message a failing walk records.
_UUID_OR_TWELVE_DIGITS = re.compile(rf"({_UUID_TEXT})|\b\d{{12}}\b")

#: ``kill_switch.sh``'s partial mask. Eight of twelve digits published forever is a narrower
#: search than twelve, not a private one, so it is collapsed rather than passed through.
_PARTIAL_MASK = re.compile(r"\b\d{4}REDACTED\d{4}\b")

#: Every shape a DSN can take on the way to a log line. The demo's answers carry none today,
#: but a walk records whatever the server said, and the server is one bad ``detail`` away
#: from carrying a connection string. Blunt on purpose.
_DSN = re.compile(r"(?i)\b(?:postgres|postgresql|cockroach|crdb)(?:ql)?://[^\s\"'<>]+")
_URL_CREDENTIAL = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*)://[^\s/:@\"']+:[^\s/@\"']+@")
_PASSWORD_KV = re.compile(r"(?i)\b(password|passwd|pgpassword|secret|token)\s*[=:]\s*[^\s,;\"']+")

#: ANSI escapes. A colour sequence pasted into a JSON evidence file makes the one sentence
#: that says WHY unreadable, and a diagnosis nobody can read is a diagnosis nobody reads.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

#: Hosts for which plain HTTP is admitted. A Function URL is HTTPS and a walk that could be
#: talked out of checking the certificate would convert a finding into a silence — but
#: ``scripts/deploy/local_furl.py`` serves the same handler on loopback for exactly this kind
#: of pre-flight, and refusing that would push the operator to a flag instead.
#: ``0.0.0.0`` is deliberately NOT here: it is a bind address, not a destination, and a walk
#: that accepted it as loopback would be accepting a host it cannot name.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def plain(text: str) -> str:
    """Strip ANSI escapes and collapse blank lines."""
    return "\n".join(
        line.rstrip() for line in _ANSI.sub("", text or "").splitlines() if line.strip()
    )


def mask(text: str) -> str:
    """Collapse every credential shape and every account id this program could ever hold.

    Applied to every string that reaches stdout and to the whole evidence document, not only
    to the fields somebody remembered. The masker that only knows the secret it has already
    read is the masker that misses the one in the message it could not read.
    """
    out = _DSN.sub("<dsn>", text or "")
    out = _URL_CREDENTIAL.sub(r"\1://<credential>@", out)
    out = _PASSWORD_KV.sub(r"\1=<redacted>", out)
    out = _PARTIAL_MASK.sub("<account>", out)
    return _UUID_OR_TWELVE_DIGITS.sub(lambda m: m.group(1) or "<account>", out)


def say(*parts: object) -> None:
    """Masked, and survivable on a console that cannot encode what the server said.

    Measured on this workstation: ``sys.stdout.encoding`` is ``cp1252``. The walk records
    whatever the deployment answers, and a ``detail`` carrying one non-Latin-1 character
    would otherwise end the run in a ``UnicodeEncodeError`` halfway through the summary --
    losing the sentence that says WHY, which is the only part that matters. The evidence file
    is written UTF-8 regardless and is unaffected.
    """
    line = " ".join(mask(str(part)) for part in parts)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        line.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        line = line.encode(encoding, "backslashreplace").decode(encoding, "replace")
    print(line)


def repo_root() -> Path | None:
    """The checkout this file sits in, or ``None`` when it does not sit in one.

    ``None`` is a real answer: the walk is meant to run with nothing but a URL, and the
    repository copy of the bundle is a FALLBACK, not a requirement. A program that refused to
    start outside a checkout would not be the artefact R8 asked for.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "verticals").is_dir() and (candidate / "packages").is_dir():
            return candidate
    return None


# ═════════════════════════════════════════════════════════════════════════════════════
# what a step produces
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Step:
    """One thing the walk measured, and which of the three outcomes it landed in.

    ``reason`` is the guard rail. It is required exactly when ``outcome`` is ``REFUSED`` and
    must be a key of :data:`NAMED_REASONS`; it is forbidden otherwise. A refusal whose reason
    is a free-text sentence somebody typed at 3 a.m. is a refusal that will be reused next
    week for something that is not the same thing at all, and the exit code will follow it.
    """

    id: str
    title: str
    outcome: str
    why: str
    reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    source: str = "live"

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"{self.id}: outcome {self.outcome!r} is not one of {OUTCOMES}.")
        if self.outcome == REFUSED:
            if self.reason is None:
                raise ValueError(
                    f"{self.id}: a REFUSED step must name its reason. An unnamed refusal is a "
                    "failure wearing a softer word."
                )
            if self.reason not in NAMED_REASONS:
                raise ValueError(
                    f"{self.id}: {self.reason!r} is not in the closed set of named reasons "
                    f"{sorted(NAMED_REASONS)}. Add it there, with the owner of the remaining "
                    "step, or record this as FAILED."
                )
        elif self.reason is not None:
            raise ValueError(
                f"{self.id}: only a REFUSED step carries a reason; this one is {self.outcome}."
            )

    @property
    def failed(self) -> bool:
        return self.outcome == FAILED

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "outcome": self.outcome,
            "why": mask(self.why),
            "reason": self.reason,
            "reason_text": NAMED_REASONS[self.reason] if self.reason else None,
            "source": self.source,
            "detail": json.loads(mask(json.dumps(self.detail, default=str))),
        }


class Unavailable(Exception):
    """A collaborator could not answer. Carries the sentence the step will print."""


# ═════════════════════════════════════════════════════════════════════════════════════
# the collaborators — the seams the controls inject into
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass
class HttpAnswer:
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float

    def decoded(self) -> bytes:
        """The body with ``content-encoding: gzip`` undone.

        This is not a nicety. Measured 2026-08-14 against the live Function URL:

            GET /assets/index-DzVoV1YM.js                      -> 413, 693 B
            GET /assets/index-DzVoV1YM.js  accept-encoding gzip -> 200, 124,177 B

        The identity object is 433,564 B, over ``DEFAULT_MAX_RESPONSE_BYTES`` (139,264), and
        interface I1 says it is reachable only through content negotiation. A walk that did
        not negotiate would read the transport badge out of a 413 body and report NO SOURCE
        for a build that carries two.
        """
        if self.headers.get("content-encoding", "").lower() == "gzip":
            try:
                return gzip.decompress(self.body)
            except (OSError, EOFError, gzip.BadGzipFile) as exc:
                raise Unavailable(
                    f"the answer claimed content-encoding: gzip and is not: {exc}"
                ) from exc
        return self.body

    def json(self) -> Any:
        return json.loads(self.decoded().decode("utf-8"))


class HttpClient:
    """HTTPS to anything that is not loopback, certificate verification ON, no way to disable.

    There is no ``verify=False``, no ``ssl._create_unverified_context`` and no flag that
    reaches one. Redirects are followed by ``urllib``'s default opener, which is what a
    browser does and therefore what a walk that claims to see what a judge sees must do.
    """

    def __init__(self, *, timeout: float = 60.0) -> None:
        self.timeout = timeout
        self._context = ssl.create_default_context()

    @staticmethod
    def _guard(url: str) -> None:
        split = urllib.parse.urlsplit(url)
        if split.scheme == "https":
            return
        if split.scheme == "http" and (split.hostname or "") in LOOPBACK_HOSTS:
            return
        raise Unavailable(
            f"refusing to walk {url!r}: the scheme is {split.scheme!r}. A demo URL that is not "
            "HTTPS has no certificate to verify and no confidentiality to offer, and this "
            "program has no flag that relaxes it. Plain HTTP is admitted for loopback only, "
            "which is what scripts/deploy/local_furl.py serves."
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpAnswer:
        self._guard(url)
        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - guarded
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(  # noqa: S310 - guarded above
                request, timeout=self.timeout, context=self._context
            ) as answer:
                return HttpAnswer(
                    status=answer.status,
                    headers={k.lower(): v for k, v in answer.headers.items()},
                    body=answer.read(),
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
        except urllib.error.HTTPError as exc:
            return HttpAnswer(
                status=exc.code,
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                body=exc.read(),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
        except (OSError, ssl.SSLError, ValueError) as exc:
            raise Unavailable(f"{method} {url} failed: {plain(str(exc))}") from exc


class FileReader:
    """The repository fallback for the enumeration. Reads; never writes."""

    def read_bytes(self, path: Path) -> bytes:
        try:
            return path.read_bytes()
        except OSError as exc:
            raise Unavailable(f"{path} could not be read: {exc}") from exc

    def exists(self, path: Path) -> bool:
        return path.is_file()


@dataclass
class Probes:
    """The two collaborators, and the stamp that says whether they opened anything.

    ``source`` travels onto every :class:`Step` and into the document. It is the reason a
    fault-injected run cannot be cited as a measurement, and it is set in exactly one place:
    :func:`main` constructs a ``live`` bundle, and the controls construct a ``synthetic`` one.
    """

    http: Any
    files: Any
    source: str = "live"


# ═════════════════════════════════════════════════════════════════════════════════════
# source-select.ts, transcribed
# ═════════════════════════════════════════════════════════════════════════════════════


def trimmed(value: str | None) -> str | None:
    """``source-select.ts:104-108``. Undefined is unset, and so is empty, and so is space.

    This one function is FAULT 1b. ``build_lambda.sh``'s old ``probe_console`` keyed on the
    variable NAME, so a compiled ``VITE_MAINLINE_API_BASE:""`` read as *carried* there and as
    *absent* in the browser. Two places held one fact and they disagreed; the badge became
    decoration and a judge read it.
    """
    if value is None:
        return None
    text = value.strip()
    return None if text == "" else text


def select_source(literals: dict[str, dict[str, list[str]]]) -> dict[str, Any]:
    """``selectSource``'s three rules, over literals gathered from any set of chunks.

    Both set → LIVE, with a control that can switch to REPLAY. One set → that one, with no
    control. Neither → nothing is built and every surface keeps its own NO SOURCE panel.

    The ``sorted()`` and the first-non-empty pick are ``build_lambda.sh``'s ``_classify``,
    transcribed, so the packer's guard and this walk answer identically for an artefact that
    somehow compiled a variable twice.
    """
    sources: dict[str, str | None] = {}
    for kind in ("live", "replay"):
        chosen = None
        for value in sorted(literals.get(SOURCE_VARIABLE[kind], {})):
            text = trimmed(value)
            if text is not None:
                chosen = text
                break
        sources[kind] = chosen
    initial = "live" if sources["live"] else ("replay" if sources["replay"] else None)
    return {
        "sources": sources,
        "effective": [kind for kind in ("live", "replay") if sources[kind]],
        "initial": initial,
        "switchable": bool(sources["live"] and sources["replay"]),
        "mode": {"live": "LIVE", "replay": "REPLAY"}.get(initial or "", "NO SOURCE"),
    }


# ═════════════════════════════════════════════════════════════════════════════════════
# reading an answer
# ═════════════════════════════════════════════════════════════════════════════════════


def sqlstates(payload: Any) -> list[dict[str, Any]]:
    """Every ``sqlstate`` this payload carries, with the JSON pointer that found it.

    Recursive and key-driven rather than pointed at one field, because the code lands in
    different places depending on what answered: ``/data/refusal/sqlstate`` on a merge
    refusal, ``/data/beats/N/sqlstate`` on a gate run, ``/data/retry_sqlstate`` when 40001
    aborted one. A walk that only looked where it expected the code would record silence for
    the answers that matter most.
    """
    found: list[dict[str, Any]] = []

    def visit(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{pointer}/{key}"
                if key in ("sqlstate", "retry_sqlstate") and not isinstance(value, (dict, list)):
                    found.append({"pointer": child, "sqlstate": value})
                else:
                    visit(value, child)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{pointer}/{index}")

    visit(payload, "")
    return found


def read_answer(answer: HttpAnswer) -> dict[str, Any]:
    """Status, kind, reason, detail and every SQLSTATE — the record for one request.

    ``kind`` is the error envelope's word (``{"error": {"kind": "dsn_unset", ...}}``);
    ``reason`` is ``/v1/health``'s (``{"ok": false, "reason": "dsn_unset"}``). Both are read
    because both spellings are on the wire, and a walk that knew only one of them would call
    half the deployment's honest refusals a failure.
    """
    record: dict[str, Any] = {
        "status": answer.status,
        "elapsed_ms": round(answer.elapsed_ms, 1),
        "content_type": answer.headers.get("content-type"),
        "content_encoding": answer.headers.get("content-encoding"),
    }
    try:
        body = answer.decoded()
    except Unavailable as exc:
        record["json"] = False
        record["body_note"] = str(exc)
        return record
    record["bytes"] = len(body)
    try:
        document = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        record["json"] = False
        record["body_head"] = body[:300].decode("utf-8", "replace")
        record["body_note"] = f"not JSON: {exc}"
        return record
    record["json"] = True
    error = document.get("error") if isinstance(document, dict) else None
    record["kind"] = error.get("kind") if isinstance(error, dict) else None
    record["reason"] = document.get("reason") if isinstance(document, dict) else None
    record["detail"] = (
        error.get("detail")
        if isinstance(error, dict)
        else (document.get("detail") if isinstance(document, dict) else None)
    )
    record["resource"] = document.get("resource") if isinstance(document, dict) else None
    record["envelope_version"] = (
        document.get("envelope_version") if isinstance(document, dict) else None
    )
    record["sqlstates"] = sqlstates(document)
    record["ok"] = document.get("ok") if isinstance(document, dict) else None
    return record


def is_dsn_unset(record: dict[str, Any]) -> bool:
    """The one refusal the deployment is CORRECT to make today.

    Keyed on the word the handler wrote, not on the status: ``dsn_unset`` reaches the wire as
    a 503 from the kernel routes and as a 503 with ``ok=false`` from ``/v1/health``, and
    keying on 503 alone would swallow a genuine unavailability that named something else.
    """
    return record.get("kind") == "dsn_unset" or record.get("reason") == "dsn_unset"


def envelope_shaped(record: dict[str, Any]) -> bool:
    """True when the answer is a MAINLINE envelope or a MAINLINE error envelope.

    The walk asserts REACHABILITY and well-formedness; it records status agreement with the
    recorded frame as data rather than asserting it, because the demo world is writable — the
    bundle carries a merge that succeeded (200) and re-driving it against a seeded cluster
    legitimately answers something else. An assertion that goes red for a legitimate state
    change is an assertion its reader learns to re-run until it is green.
    """
    return bool(record.get("json")) and (
        record.get("envelope_version") is not None or record.get("kind") is not None
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# the steps
# ═════════════════════════════════════════════════════════════════════════════════════


def join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def check_shell(probes: Probes, base: str) -> tuple[Step, list[str]]:
    """S1 — ``GET /`` is 200 and the bytes are the console shell."""
    title = "GET / serves the console shell"
    try:
        answer = probes.http.request("GET", join(base, ""), headers={"accept": "text/html"})
    except Unavailable as exc:
        return Step("shell", title, FAILED, str(exc), source=probes.source), []
    detail: dict[str, Any] = {
        "status": answer.status,
        "bytes": len(answer.body),
        "elapsed_ms": round(answer.elapsed_ms, 1),
        "content_type": answer.headers.get("content-type"),
    }
    if answer.status != 200:
        return (
            Step(
                "shell",
                title,
                FAILED,
                f"GET / answered {answer.status}. Nothing measured after this means anything: "
                "a judge opening the demo sees this response and no console at all.",
                detail={**detail, "body_head": answer.body[:300].decode("utf-8", "replace")},
                source=probes.source,
            ),
            [],
        )
    try:
        html = answer.decoded().decode("utf-8")
    except (Unavailable, UnicodeDecodeError) as exc:
        return (
            Step(
                "shell",
                title,
                FAILED,
                f"GET / answered 200 with bytes that are not text: {exc}",
                detail=detail,
                source=probes.source,
            ),
            [],
        )
    assets = ASSET_REF.findall(html)
    scripts = [asset for asset in assets if asset.endswith(".js")]
    styles = [asset for asset in assets if asset.endswith(".css")]
    detail["assets"] = assets
    detail["has_doctype"] = html.lstrip()[:120].lower().startswith("<!doctype html")
    detail["has_root_mount"] = 'id="root"' in html
    if not detail["has_doctype"] or not detail["has_root_mount"]:
        return (
            Step(
                "shell",
                title,
                FAILED,
                "GET / answered 200 but the bytes are not the console shell: "
                f"doctype={detail['has_doctype']}, #root mount={detail['has_root_mount']}. "
                "Something is serving this origin and it is not the console.",
                detail={**detail, "body_head": html[:300]},
                source=probes.source,
            ),
            [],
        )
    if not scripts or not styles:
        return (
            Step(
                "shell",
                title,
                FAILED,
                "the shell references "
                f"{len(scripts)} ./assets/*.js and {len(styles)} ./assets/*.css. A shell with "
                "no entry chunk boots nothing, and the transport badge cannot be read from an "
                "artefact whose bytes are not there.",
                detail=detail,
                source=probes.source,
            ),
            [],
        )
    return (
        Step(
            "shell",
            title,
            SATISFIED,
            f"200 in {detail['elapsed_ms']} ms, {detail['bytes']} B, doctype and #root present, "
            f"referencing {', '.join(assets)}.",
            detail=detail,
            source=probes.source,
        ),
        scripts,
    )


# One return per refusal, and the refusals ARE the check. Collapsing them into a single exit
# with an accumulated reason would turn the sentence a reader gets at 3 a.m. into a
# concatenation rather than the one thing that actually went wrong. Same justification
# post_apply_verify.py:776-778 records for check_beats.
def check_transport(  # noqa: PLR0911
    probes: Probes, base: str, scripts: list[str], *, allow_replay: bool
) -> tuple[Step, dict[str, Any]]:
    """S2 — the compiled transport, read out of the served bytes with the console's own rules.

    Not off the screen. There is no browser in this lane and none is added: the entry chunks
    the shell references are fetched, :data:`ENV_LITERAL` extracts what the compiler inlined,
    and :func:`select_source` applies ``source-select.ts``'s three rules to the result.

    LIVE is the requirement. REPLAY is FAULT 1 — the artefact that reached the founder — and
    it FAILS unless ``--allow-replay`` was typed on the command line, which turns it into a
    refusal with a named reason and stamps the document so that no exit-0 run made that way
    can be quoted as a LIVE reading. Ruling R7 established that shape for ``build_lambda``:
    *the opt-out is a sentence somebody wrote, not a default.*
    """
    title = "The artefact's compiled transport is LIVE"
    empty = {
        "sources": {"live": None, "replay": None},
        "effective": [],
        "initial": None,
        "switchable": False,
        "mode": "NO SOURCE",
    }
    if not scripts:
        return (
            Step(
                "transport",
                title,
                FAILED,
                "the shell referenced no entry chunk, so no compiled literal could be read.",
                source=probes.source,
            ),
            empty,
        )
    literals: dict[str, dict[str, list[str]]] = {}
    build_ids: dict[str, list[str]] = {}
    modes: set[str] = set()
    scanned: list[dict[str, Any]] = []
    for asset in scripts:
        url = join(base, asset)
        try:
            answer = probes.http.request(
                "GET", url, headers={"accept": "*/*", "accept-encoding": "gzip"}
            )
        except Unavailable as exc:
            return (
                Step(
                    "transport",
                    title,
                    FAILED,
                    f"the entry chunk {asset} could not be fetched: {exc}",
                    source=probes.source,
                ),
                empty,
            )
        if answer.status != 200:
            hint = ""
            if answer.status == 413:
                hint = (
                    " The identity object is over DEFAULT_MAX_RESPONSE_BYTES and interface I1 "
                    "serves it only through content negotiation; this request DID send "
                    "accept-encoding: gzip, so a 413 here means the .gz sibling is missing "
                    "from the package."
                )
            return (
                Step(
                    "transport",
                    title,
                    FAILED,
                    f"GET /{asset} answered {answer.status}, so the artefact's own bytes could "
                    f"not be read and its badge cannot be checked against them.{hint}",
                    detail={"asset": asset, "status": answer.status},
                    source=probes.source,
                ),
                empty,
            )
        try:
            text = answer.decoded().decode("utf-8", "replace")
        except Unavailable as exc:
            return (
                Step("transport", title, FAILED, f"{asset}: {exc}", source=probes.source),
                empty,
            )
        for key, value in ENV_LITERAL.findall(text):
            literals.setdefault(key, {}).setdefault(value, []).append(asset)
        for value in BUILD_ID_LITERAL.findall(text):
            build_ids.setdefault(value, []).append(asset)
        modes.update(ENV_MODE.findall(text))
        scanned.append(
            {
                "asset": asset,
                "wire_bytes": len(answer.body),
                "identity_bytes": len(answer.decoded()),
                "content_encoding": answer.headers.get("content-encoding"),
            }
        )
    selection = select_source(literals)
    detail = {
        "scanned": scanned,
        "literals": {k: sorted(v) for k, v in sorted(literals.items())},
        "build_ids": sorted(build_ids),
        "names_itself": "dev" not in build_ids,
        "vite_mode": sorted(modes)[0] if modes else None,
        "selection": selection,
        "rule": (
            "src/app/source-select.ts: trimmed() makes empty and whitespace UNSET; both set -> "
            "LIVE with a control, one set -> that one with no control, neither -> NO SOURCE."
        ),
    }
    if selection["initial"] == "live":
        return (
            Step(
                "transport",
                title,
                SATISFIED,
                f"the served bytes compile VITE_MAINLINE_API_BASE={selection['sources']['live']!r}"
                + (
                    f" and VITE_MAINLINE_BUNDLE_URL={selection['sources']['replay']!r}, so "
                    "selectSource starts LIVE and offers the control"
                    if selection["switchable"]
                    else ", and no bundle URL, so selectSource starts LIVE with no control"
                ),
                detail=detail,
                source=probes.source,
            ),
            selection,
        )
    compiled = (
        ", ".join(f"{key}={sorted(values)[0]!r}" for key, values in sorted(literals.items()))
        or "no VITE_MAINLINE_* literals at all"
    )
    sentence = (
        f"THE BADGE ON THIS DEPLOYMENT READS {selection['mode']}, NOT LIVE. The served bytes "
        f"compile {compiled}; source-select.ts trims empty to unset, so selectSource returns "
        f"{selection['mode']} and every byte a judge sees is "
        + (
            "a recording, not the kernel this console is sitting on. That is FAULT 1: a missing "
            "build input (VITE_MAINLINE_API_BASE=<origin>), not a bug in the selector."
            if selection["initial"] == "replay"
            else "nothing at all: every surface renders its own NO SOURCE panel."
        )
    )
    if allow_replay and selection["initial"] == "replay":
        return (
            Step(
                "transport",
                title,
                REFUSED,
                sentence,
                reason="console_replay_declared",
                detail=detail,
                source=probes.source,
            ),
            selection,
        )
    return (
        Step("transport", title, FAILED, sentence, detail=detail, source=probes.source),
        selection,
    )


def check_health(probes: Probes, base: str) -> Step:
    """S3 — ``GET /v1/health``. The cheapest database beat there is."""
    title = "GET /v1/health"
    try:
        answer = probes.http.request(
            "GET", join(base, HEALTH_PATH), headers={"accept": "application/json"}
        )
    except Unavailable as exc:
        return Step("health", title, FAILED, str(exc), source=probes.source)
    record = read_answer(answer)
    if is_dsn_unset(record):
        return Step(
            "health",
            title,
            REFUSED,
            f"/v1/health answered {record['status']} ok={record.get('ok')!r} "
            f"reason='dsn_unset'. {NAMED_REASONS['dsn_unset']}",
            reason="dsn_unset",
            detail=record,
            source=probes.source,
        )
    if answer.status != 200:
        return Step(
            "health",
            title,
            FAILED,
            f"/v1/health answered {answer.status} and did not name dsn_unset as the cause.",
            detail=record,
            source=probes.source,
        )
    if record.get("ok") is not True:
        return Step(
            "health",
            title,
            FAILED,
            "/v1/health answered 200 but its body does not carry ok=true. A 200 whose body "
            "reports a problem is a 200 a load balancer believes and a judge does not.",
            detail=record,
            source=probes.source,
        )
    return Step(
        "health",
        title,
        SATISFIED,
        f"200 in {record['elapsed_ms']} ms, body carries ok=true.",
        detail=record,
        source=probes.source,
    )


def _frames_from_manifest(document: Any) -> list[str]:
    files = document.get("files") if isinstance(document, dict) else None
    if not isinstance(files, list):
        raise Unavailable(
            "the bundle manifest carries no `files` array, so it declares no enumeration. "
            "A walk cannot drive what the artefact does not declare."
        )
    paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if isinstance(path, str) and path.startswith("frames/") and path.endswith(".json"):
            paths.append(path)
    return paths


# Long because it carries TWO readers of one enumeration -- the served origin and the
# repository copy -- and each records its own refusal sentence. Splitting them into free
# functions would move the shared `bundle_url` and `probes` into parameters and put the two
# halves of one decision in two places, which is the drift R10 exists to prevent.
def check_enumeration(  # noqa: PLR0915
    probes: Probes, base: str, selection: dict[str, Any], root: Path | None, prefer: str
) -> tuple[Step, list[dict[str, Any]]]:
    """S4a — read the request enumeration the ARTEFACT ships, and say where it came from.

    Ruling R10. ``console/fixtures/bundles/demo-cloud`` is an EvidenceBundle: ``manifest.json``
    lists every file with its digest and its request key, and each frame under ``frames/``
    carries ``request.method``, ``request.path``, ``request.query`` and ``request.body_b64``
    — the console's own traffic, machine-readable, already committed, and the REPLAY
    counterpart of every LIVE request. Driving it means LIVE and REPLAY are driven from ONE
    source; re-deriving a list of endpoints by hand would be a second place for that fact to
    live, which is the drift this whole wave was called for.

    The origin is preferred so that the walk drives WHAT IS DEPLOYED, at the bundle URL the
    artefact was compiled with. The repository copy is the fallback and the document says so
    in one word: a walk that quietly drove the developer's tree while claiming to have walked
    the deployment would be the same defect one level down.
    """
    title = "The request enumeration the artefact ships"
    attempts: list[dict[str, Any]] = []

    compiled_bundle = selection.get("sources", {}).get("replay")
    if compiled_bundle:
        bundle_url = urllib.parse.urljoin(base.rstrip("/") + "/", compiled_bundle)
        origin_from = "compiled"
    else:
        bundle_url = join(base, DEFAULT_BUNDLE_PATH)
        origin_from = "default"
    if not bundle_url.endswith("/"):
        bundle_url += "/"

    def from_origin() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        manifest_url = bundle_url + "manifest.json"
        answer = probes.http.request("GET", manifest_url, headers={"accept": "application/json"})
        if answer.status != 200:
            raise Unavailable(f"GET {manifest_url} answered {answer.status}")
        try:
            document = json.loads(answer.decoded().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Unavailable(f"{manifest_url} is not JSON: {exc}") from exc
        paths = _frames_from_manifest(document)
        frames = []
        for path in paths:
            frame_url = bundle_url + path
            frame_answer = probes.http.request(
                "GET", frame_url, headers={"accept": "application/json"}
            )
            if frame_answer.status != 200:
                raise Unavailable(
                    f"the manifest declares {path} and GET {frame_url} answered "
                    f"{frame_answer.status}. A declared frame that is not served is a bundle "
                    "the console itself could not replay."
                )
            try:
                frames.append({"path": path, "frame": json.loads(frame_answer.decoded())})
            except (ValueError, UnicodeDecodeError) as exc:
                raise Unavailable(f"{path} is not JSON: {exc}") from exc
        return frames, {
            "used": "origin",
            "bundle_url": bundle_url,
            "bundle_url_from": origin_from,
            "manifest_url": manifest_url,
            "bundle_id": document.get("bundle_id") if isinstance(document, dict) else None,
            "captured_at": document.get("captured_at") if isinstance(document, dict) else None,
            "declared_files": len(document.get("files", [])) if isinstance(document, dict) else 0,
        }

    def from_repo() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if root is None:
            raise Unavailable(
                "this program is not running inside a checkout, so there is no repository "
                "copy of the bundle to fall back to."
            )
        directory = root / REPO_BUNDLE
        manifest_path = directory / "manifest.json"
        if not probes.files.exists(manifest_path):
            raise Unavailable(f"{manifest_path} does not exist.")
        try:
            document = json.loads(probes.files.read_bytes(manifest_path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Unavailable(f"{manifest_path} is not JSON: {exc}") from exc
        frames = []
        for path in _frames_from_manifest(document):
            frame_path = directory / path
            if not probes.files.exists(frame_path):
                raise Unavailable(f"the manifest declares {path} and {frame_path} does not exist.")
            try:
                frames.append(
                    {"path": path, "frame": json.loads(probes.files.read_bytes(frame_path))}
                )
            except (ValueError, UnicodeDecodeError) as exc:
                raise Unavailable(f"{frame_path} is not JSON: {exc}") from exc
        return frames, {
            "used": "repo",
            "directory": str(directory),
            "manifest_path": str(manifest_path),
            "bundle_id": document.get("bundle_id") if isinstance(document, dict) else None,
            "captured_at": document.get("captured_at") if isinstance(document, dict) else None,
            "declared_files": len(document.get("files", [])) if isinstance(document, dict) else 0,
        }

    order = {"auto": ("origin", "repo"), "origin": ("origin",), "repo": ("repo",)}[prefer]
    frames: list[dict[str, Any]] = []
    provenance: dict[str, Any] = {}
    for which in order:
        try:
            frames, provenance = (from_origin if which == "origin" else from_repo)()
            break
        except Unavailable as exc:
            attempts.append({"source": which, "refused": str(exc)})
        except (OSError, TypeError) as exc:  # a malformed frame is a refusal, never a crash
            attempts.append({"source": which, "refused": f"{type(exc).__name__}: {exc}"})
    else:
        return (
            Step(
                "enumeration",
                title,
                FAILED,
                "the request enumeration could not be read from "
                + " or ".join(order)
                + ": "
                + "; ".join(f"{a['source']}: {a['refused']}" for a in attempts)
                + ". The walk drives what the artefact declares (R10) and will not invent a "
                "list of endpoints to drive instead.",
                detail={"attempts": attempts, "preference": prefer},
                source=probes.source,
            ),
            [],
        )

    requests: list[dict[str, Any]] = []
    malformed: list[str] = []
    for entry in frames:
        frame = entry["frame"]
        request = frame.get("request") if isinstance(frame, dict) else None
        if not isinstance(request, dict) or not request.get("method") or not request.get("path"):
            malformed.append(entry["path"])
            continue
        response = frame.get("response") if isinstance(frame, dict) else None
        requests.append(
            {
                "frame_path": entry["path"],
                "key": frame.get("key") or f"{request['method']} {request['path']}",
                "method": str(request["method"]).upper(),
                "path": str(request["path"]),
                "query": request.get("query") or [],
                "body_b64": request.get("body_b64"),
                "recorded_status": (response or {}).get("status")
                if isinstance(response, dict)
                else None,
            }
        )
    detail = {
        **provenance,
        "attempts": attempts,
        "frames": len(requests),
        "malformed": malformed,
        "keys": [r["key"] for r in requests],
    }
    if malformed:
        return (
            Step(
                "enumeration",
                title,
                FAILED,
                f"{len(malformed)} declared frame(s) carry no usable request block: "
                + ", ".join(malformed),
                detail=detail,
                source=probes.source,
            ),
            [],
        )
    if not requests:
        return (
            Step(
                "enumeration",
                title,
                FAILED,
                f"the enumeration read from {provenance.get('used')} declares NO frames. An "
                "empty enumeration would let this walk drive nothing and still exit 0, which "
                "is the shape of a check that has stopped checking.",
                detail=detail,
                source=probes.source,
            ),
            [],
        )
    return (
        Step(
            "enumeration",
            title,
            SATISFIED,
            f"{len(requests)} frames read from the {provenance.get('used').upper()} copy"
            + (
                f" at {provenance.get('manifest_url')}"
                if provenance.get("used") == "origin"
                else f" at {provenance.get('manifest_path')}"
            )
            + (
                " (the bundle URL compiled into the artefact)"
                if provenance.get("bundle_url_from") == "compiled"
                else ""
            ),
            detail=detail,
            source=probes.source,
        ),
        requests,
    )


def drive_frame(probes: Probes, base: str, request: dict[str, Any]) -> Step:
    """One declared request, driven against the deployment, recorded whatever it answers."""
    path = request["path"]
    query = [(q.get("name"), q.get("value")) for q in request["query"] if isinstance(q, dict)]
    url = join(base, path)
    if query:
        url += "?" + urllib.parse.urlencode(query)
    body = base64.b64decode(request["body_b64"]) if request.get("body_b64") else None
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    step_id = f"frame:{request['key']}"
    title = request["key"]
    try:
        answer = probes.http.request(request["method"], url, body=body, headers=headers)
    except Unavailable as exc:
        return Step(
            step_id,
            title,
            FAILED,
            str(exc),
            detail={"url_path": path, "query": query},
            source=probes.source,
        )
    record = read_answer(answer)
    record["recorded_status"] = request.get("recorded_status")
    record["status_matches_recording"] = record["status"] == request.get("recorded_status")
    record["url_path"] = path
    record["query"] = query
    record["frame_path"] = request["frame_path"]
    codes = [s["sqlstate"] for s in record.get("sqlstates", []) if s.get("sqlstate")]
    if is_dsn_unset(record):
        return Step(
            step_id,
            title,
            REFUSED,
            f"{record['status']} kind='dsn_unset'. The route is reachable and refused for the "
            "one reason the founder's remaining step explains.",
            reason="dsn_unset",
            detail=record,
            source=probes.source,
        )
    if answer.status in (404, 405):
        return Step(
            step_id,
            title,
            FAILED,
            f"{answer.status}: this deployment does not serve a request the artefact's own "
            "EvidenceBundle says the console makes. LIVE and REPLAY would show different "
            "screens, which is the D7 property the bundle exists to hold.",
            detail=record,
            source=probes.source,
        )
    if answer.status >= 500:
        return Step(
            step_id,
            title,
            FAILED,
            f"{answer.status} with kind={record.get('kind')!r}, which is not a named reason.",
            detail=record,
            source=probes.source,
        )
    if not envelope_shaped(record):
        return Step(
            step_id,
            title,
            FAILED,
            f"{answer.status} with a body that is not a MAINLINE envelope "
            f"({record.get('body_note') or 'no envelope_version and no error.kind'}).",
            detail=record,
            source=probes.source,
        )
    agreement = (
        "the status the bundle recorded"
        if record["status_matches_recording"]
        else f"NOT the recorded status ({request.get('recorded_status')}), recorded as data "
        "rather than asserted: the demo world is writable"
    )
    return Step(
        step_id,
        title,
        SATISFIED,
        f"{answer.status} in {record['elapsed_ms']} ms, envelope well-formed, {agreement}"
        + (f"; sqlstate {', '.join(codes)}" if codes else ""),
        detail=record,
        source=probes.source,
    )


# Ten returns and twenty branches because the headline beat has ten distinguishable answers
# and a reader at 3 a.m. needs the ONE sentence that names which. An accumulated reason would
# read "the gate run did not carry what the contract names" for a 404, a retry and a forged
# expectation alike.
def check_gate_run(probes: Probes, base: str) -> Step:  # noqa: PLR0911, PLR0912
    """S5 — ``POST /v1/demo/gate-run``: the headline beat, and its four SQLSTATEs.

    ``00000 -> 23514 -> P0001 -> 00000`` is the demo's whole argument: read the subject, be
    refused by a declarative CHECK, forge the projected counter and be refused ANYWAY because
    the gate re-derives it, then sign one disposition and be admitted. A run that produced
    three of the four would still render as a demo and would be arguing something else.

    The expectation is transcribed in :data:`EXPECTED_BEATS` AND cross-checked against each
    beat's own ``expected`` block, which the contract puts on the wire precisely so a reader
    can check the driver's arithmetic. Two statements of one fact, compared.
    """
    title = "POST /v1/demo/gate-run plays 00000 -> 23514 -> P0001 -> 00000"
    url = join(base, GATE_RUN_PATH)
    try:
        answer = probes.http.request(
            "POST",
            url,
            body=b"{}",
            headers={"content-type": "application/json", "accept": "application/json"},
        )
    except Unavailable as exc:
        return Step("gate_run", title, FAILED, str(exc), source=probes.source)
    record = read_answer(answer)
    if is_dsn_unset(record):
        return Step(
            "gate_run",
            title,
            REFUSED,
            f"POST /{GATE_RUN_PATH} answered {record['status']} kind='dsn_unset'. THE ROUTE "
            "EXISTS (a 404 would mean it did not) and the beat cannot play until the SSM "
            "parameter lands, which is the founder's step.",
            reason="dsn_unset",
            detail=record,
            source=probes.source,
        )
    if answer.status == 404:
        return Step(
            "gate_run",
            title,
            FAILED,
            f"POST /{GATE_RUN_PATH} answered 404: the route is not declared by this "
            "deployment's route table, so the headline beat is not reachable at all.",
            detail=record,
            source=probes.source,
        )
    if answer.status != 200:
        return Step(
            "gate_run",
            title,
            FAILED,
            f"POST /{GATE_RUN_PATH} answered {answer.status} with kind={record.get('kind')!r}.",
            detail=record,
            source=probes.source,
        )
    try:
        document = answer.json()
    except (ValueError, UnicodeDecodeError, Unavailable) as exc:
        return Step(
            "gate_run",
            title,
            FAILED,
            f"the gate run answered 200 with a body that is not JSON: {exc}",
            detail=record,
            source=probes.source,
        )
    payload = document.get("data", document) if isinstance(document, dict) else {}
    if not isinstance(payload, dict):
        return Step(
            "gate_run",
            title,
            FAILED,
            "the gate run answered 200 with no `data` object.",
            detail=record,
            source=probes.source,
        )
    record["outcome"] = payload.get("outcome")
    record["verdict"] = payload.get("verdict")
    record["failures"] = payload.get("failures")
    record["persisted"] = payload.get("persisted")
    if payload.get("outcome") == "retry":
        return Step(
            "gate_run",
            title,
            REFUSED,
            "the gate run answered 200 with outcome='retry': SQLSTATE 40001 aborted it and the "
            "transaction was UNDECIDED. " + NAMED_REASONS["retry_40001"],
            reason="retry_40001",
            detail=record,
            source=probes.source,
        )
    beats = payload.get("beats")
    if not isinstance(beats, list):
        return Step(
            "gate_run",
            title,
            FAILED,
            "the gate-run payload carries no `beats` array.",
            detail=record,
            source=probes.source,
        )
    record["beats"] = [
        {
            k: b.get(k)
            for k in (
                "ordinal",
                "name",
                "outcome",
                "sqlstate",
                "constraint",
                "constraint_source",
                "matched_expectation",
                "expected",
            )
        }
        for b in beats
        if isinstance(b, dict)
    ]
    failures: list[str] = []
    if len(beats) != len(EXPECTED_BEATS):
        failures.append(
            f"the payload carries {len(beats)} beats; the contract names {len(EXPECTED_BEATS)}"
        )
    by_name = {b.get("name"): b for b in beats if isinstance(b, dict)}
    for expected in EXPECTED_BEATS:
        found = by_name.get(expected["name"])
        if found is None:
            failures.append(f"beat {expected['ordinal']} ({expected['name']}) is absent")
            continue
        if found.get("sqlstate") != expected["sqlstate"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): sqlstate is "
                f"{found.get('sqlstate')!r}, the contract requires {expected['sqlstate']!r}"
            )
        if found.get("outcome") != expected["outcome"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): outcome is "
                f"{found.get('outcome')!r}, the contract requires {expected['outcome']!r}"
            )
        if expected["constraint"] is not None and found.get("constraint") != expected["constraint"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): constraint is "
                f"{found.get('constraint')!r}, the contract requires {expected['constraint']!r}"
            )
        # The payload's own expectation, compared against this program's transcription. Two
        # places holding one fact are a hazard only when nobody compares them.
        declared = found.get("expected")
        if isinstance(declared, dict):
            for key in ("outcome", "sqlstate"):
                if key in declared and declared[key] != expected[key]:
                    failures.append(
                        f"beat {expected['ordinal']} ({expected['name']}): the payload says it "
                        f"was written against {key}={declared[key]!r} and this walk's "
                        f"transcription of the contract says {expected[key]!r}. One of the two "
                        "is wrong and neither may be assumed."
                    )
    if payload.get("verdict") != "PROVEN":
        failures.append(
            f"verdict is {payload.get('verdict')!r}, not 'PROVEN'"
            + (
                f" ({'; '.join(map(str, payload.get('failures') or []))})"
                if payload.get("failures")
                else ""
            )
        )
    if payload.get("persisted") not in (False, None):
        failures.append(f"persisted is {payload.get('persisted')!r}; the run must persist nothing")
    record["assertion_failures"] = failures
    if failures:
        return Step(
            "gate_run",
            title,
            FAILED,
            "the gate run answered 200 and did not carry what the contract names: "
            + "; ".join(failures),
            detail=record,
            source=probes.source,
        )
    observed = " -> ".join(str(b.get("sqlstate")) for b in beats)
    return Step(
        "gate_run",
        title,
        SATISFIED,
        f"200 in {record['elapsed_ms']} ms, verdict PROVEN, beats {observed}, persisted nothing.",
        detail=record,
        source=probes.source,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# the walk
# ═════════════════════════════════════════════════════════════════════════════════════


def walk(
    probes: Probes, base: str, root: Path | None, *, enumeration: str, allow_replay: bool
) -> tuple[list[Step], dict[str, Any]]:
    steps: list[Step] = []
    shell, scripts = check_shell(probes, base)
    steps.append(shell)
    transport, selection = check_transport(probes, base, scripts, allow_replay=allow_replay)
    steps.append(transport)
    steps.append(check_health(probes, base))
    enumeration_step, requests = check_enumeration(probes, base, selection, root, enumeration)
    steps.append(enumeration_step)
    for request in requests:
        steps.append(drive_frame(probes, base, request))
    steps.append(check_gate_run(probes, base))
    # R10's last sentence, answered from the enumeration alone: does the headline beat have a
    # REPLAY counterpart? D7 requires LIVE and REPLAY to show the same screen, so a beat the
    # console can address with no frame behind it is a beat that renders in one mode only.
    # RECORDED, not graded: the remedy is a capture into the bundle, which belongs to whoever
    # owns capture_demo_bundle.py and the console's declaration -- not to this walk, and a
    # colour this program invented for somebody else's lane would be a colour nobody acts on.
    gate_run_frame = any(
        request["method"] == "POST" and request["path"].rstrip("/") == "/" + GATE_RUN_PATH
        for request in requests
    )
    context = {
        "base_url": base,
        "gate_run_has_replay_counterpart": gate_run_frame,
        "gate_run_counterpart_note": (
            "true when the shipped EvidenceBundle carries a frame for POST /v1/demo/gate-run, "
            "which is what lets the console render the headline beat in REPLAY as well as "
            "LIVE (D7). False is a finding for whoever owns the capture and the console's "
            "declaration; this walk records it and does not grade it."
        ),
        "transport_mode": selection.get("mode"),
        "transport_initial": selection.get("initial"),
        "compiled_sources": selection.get("sources"),
        "enumeration_preference": enumeration,
        "enumeration_used": enumeration_step.detail.get("used"),
        "frames_driven": len(requests),
        "allow_replay_declared": allow_replay,
        "checkout": str(root) if root else None,
        "writes_note": (
            "The enumeration is the console's own traffic and three of its frames are POST "
            "merges, one of which the bundle recorded as 200. Driving them against a live "
            "seeded cluster WRITES, exactly as a judge clicking the console writes. Nothing "
            "here is skipped to avoid that; scripts/deploy/seed_demo.py restores the world."
        ),
    }
    return steps, context


def build_document(steps: list[Step], context: dict[str, Any], probes: Probes) -> dict[str, Any]:
    failed = [s for s in steps if s.outcome == FAILED]
    refused = [s for s in steps if s.outcome == REFUSED]
    satisfied = [s for s in steps if s.outcome == SATISFIED]
    return {
        "schema": "mainline.deploy.judge-walk/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "program": "scripts/deploy/judge_walk.py",
        "source": probes.source,
        "source_note": (
            "live = a socket was opened to the base URL for every reading below. synthetic = a "
            "control in tests/deploy/test_judge_walk.py supplied the answers and NOTHING here "
            "is a measurement of any deployment."
        ),
        "masking": (
            "every twelve-digit run, every postgres/cockroach URL, every user:password@ and "
            "every password/secret/token assignment is collapsed before writing"
        ),
        "context": json.loads(mask(json.dumps(context, default=str))),
        "named_reasons": NAMED_REASONS,
        "steps_total": len(steps),
        "steps_satisfied": len(satisfied),
        "steps_refused": len(refused),
        "steps_failed": len(failed),
        "refused_reasons": sorted({s.reason for s in refused if s.reason}),
        "failed_ids": [s.id for s in failed],
        "verdict": ("WALKED, NOTHING FAILED" if not failed else f"{len(failed)} STEP(S) FAILED"),
        "exit_code": EXIT_OK if not failed else EXIT_FAILED,
        "steps": [s.as_json() for s in steps],
    }


def summarise(steps: list[Step], document: dict[str, Any]) -> None:
    say()
    say("judge walk of", document["context"]["base_url"])
    say(f"  readings are {document['source'].upper()}")
    say()
    for step in steps:
        say(f"  {step.outcome:<10} {step.id:<62} {step.title}")
        if step.outcome != SATISFIED:
            say(f"  {'':<10} why: {step.why}")
    failed = [s for s in steps if s.outcome == FAILED]
    refused = [s for s in steps if s.outcome == REFUSED]
    say()
    say(
        f"  {document['steps_satisfied']} satisfied, {document['steps_refused']} refused for a "
        f"named reason, {document['steps_failed']} failed, of {document['steps_total']}."
    )
    for reason in document["refused_reasons"]:
        count = sum(1 for s in refused if s.reason == reason)
        say(f"    REFUSED x{count}  {reason}: {NAMED_REASONS[reason]}")
    if not document["context"].get("gate_run_has_replay_counterpart"):
        say(
            "    NOTED (not graded)  the shipped EvidenceBundle carries NO frame for POST "
            f"/{GATE_RUN_PATH}, so the headline beat has no REPLAY counterpart and renders in "
            "LIVE only. D7 asks for one screen from two sources; this is a finding for the "
            "capture and the console declaration, not for this walk to colour."
        )
    if not failed:
        say()
        say(
            "  nothing FAILED. A refusal that names its reason is not a failure, and the "
            "reasons above are the state this deployment is honestly in."
        )
        return
    say()
    say(f"  {len(failed)} step(s) FAILED:")
    for step in failed:
        say(f"    - {step.id}: {step.why}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judge_walk.py",
        description=(
            "Walk a deployed MAINLINE demo from its URL and record what it answers. Needs no "
            "AWS credentials, no Terraform state and no browser. Never applies or deploys."
        ),
    )
    parser.add_argument("--base-url", required=True, help="the deployment's origin")
    parser.add_argument(
        "--enumeration",
        choices=("auto", "origin", "repo"),
        default="auto",
        help=(
            "where the request enumeration comes from: auto (default) prefers the served "
            "origin and falls back to the repository copy; the document always says which."
        ),
    )
    parser.add_argument(
        "--allow-replay",
        action="store_true",
        help=(
            "declare, in words, that this deployment is expected to serve a REPLAY console. "
            "Turns the transport step from FAILED into a refusal with a named reason and "
            "stamps the document, so no run made this way can be cited as a LIVE reading. "
            "There is no default that does this: R7, the opt-out is a sentence somebody "
            "wrote."
        ),
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="per-request seconds")
    parser.add_argument("--out", type=Path, default=None, help="write the evidence document here")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None, probes: Probes | None = None) -> int:
    args = build_parser().parse_args(argv)
    base = args.base_url.strip()
    if not base:
        print("judge_walk: --base-url is empty.", file=sys.stderr)
        return EXIT_USAGE
    if "://" not in base:
        print(
            "judge_walk: --base-url must carry a scheme, e.g. https://<id>.lambda-url."
            "<region>.on.aws. A bare hostname is a guess about a protocol.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.timeout <= 0:
        print("judge_walk: --timeout must be positive.", file=sys.stderr)
        return EXIT_USAGE

    root = repo_root()
    if probes is None:
        probes = Probes(http=HttpClient(timeout=args.timeout), files=FileReader(), source="live")

    steps, context = walk(
        probes, base, root, enumeration=args.enumeration, allow_replay=args.allow_replay
    )
    document = build_document(steps, context, probes)
    summarise(steps, document)

    out = args.out
    if out is None and root is not None:
        out = root / "evidence" / "deploy" / "judge-walk.json"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        sidecar = out.with_suffix(out.suffix + ".license")
        if not sidecar.exists():
            sidecar.write_text(
                "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
                "SPDX-License-Identifier: CC-BY-4.0\n",
                encoding="utf-8",
            )
        say(f"\n  evidence written to {out}")
    else:
        # Not a checkout and no --out. Say so rather than finishing silently: a reader who
        # expected a file and got none must be told which of the several possible nothings
        # this is, exactly as source-select.ts's NO SOURCE panel must.
        say(
            "\n  NO EVIDENCE FILE WAS WRITTEN. This program is not running inside a MAINLINE "
            "checkout, so there is no evidence/deploy/ to write into, and no --out was given. "
            "The summary above is the whole record of this walk. Pass --out <path> to keep it."
        )
    if args.print_json:
        say(json.dumps(document, indent=2))
    return int(document["exit_code"])


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    sys.exit(main())
