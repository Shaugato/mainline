# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The shared AWS client contract for the whole ``scripts/aws/`` fleet.

Nine programs import this module.  Its public surface is therefore frozen by agreement,
not by convenience, and every name below was specified before any dependent was written:

===========================  =============================================================
name                         contract
===========================  =============================================================
``REGION``                   ``"ap-southeast-2"``.  The only region this fleet talks to.
``session()``                a ``boto3.Session`` honouring ``AWS_PROFILE`` (default
                             ``mainline-dev``), cached per profile.
``bedrock_runtime()``        ``bedrock-runtime`` client, region-pinned.
``bedrock_control()``        ``bedrock`` control-plane client, region-pinned.
``cloudwatch()``             ``cloudwatch`` client, region-pinned.  **Read-only by fleet
                             rule** — nothing here provisions or publishes a metric.
``assert_in_region(mid)``    raises :class:`ResidencyError` for a cross-region routing
                             prefix; returns the id unchanged when it is legal.
``redact(obj)``              recursive scrub of account ids, ARN account fields, DSN
                             passwords and AWS key shapes.
``sha256_hex(data)``         lowercase hex SHA-256 of ``bytes``.
``artefact(...)``            writes the evidence envelope, redacted, deterministically.
``USD_PER_1K_TOKENS``        model id -> price, USD per 1 000 tokens, in/out.
``token_ledger_entry(...)``  one priced row of the fleet's token ledger.
``crdb(database=None)``      ``psycopg`` connection to ``COCKROACH_DSN`` from ``.env``.
``with_retry(fn, attempts)`` ``(value, retries_40001)``; retries ``40001`` and nothing else.
``ResidencyError``           residency violation.
``CostCeilingExceeded``      a run priced above the fleet ceiling.
===========================  =============================================================

**Standard library plus ``boto3`` and ``psycopg``.**  No ``tenacity`` / ``backoff`` /
``retrying`` — ``tests/boundary/test_ci_greps.py`` bans them, because a blanket retry
helper cannot tell a serialization restart from a gate refusal, and this fleet writes
to a database whose whole point is refusing things.

MEASURED, on this workstation, 2026-08-11, profile ``mainline-dev``:

* ``sts.get_caller_identity()`` -> an IAM user ARN in a 12-digit account; the account id
  appears nowhere in this repository and this module is the reason.
* ``bedrock.list_foundation_models()`` -> 64 summaries in ``ap-southeast-2``.
* ``bedrock.list_inference_profiles()`` -> 29 SYSTEM_DEFINED profiles: 13 ``global.``,
  8 ``apac.``, 8 ``au.`` (counted in ``evidence/aws/probe/model-availability.json``).
  ``assert_in_region`` exists because the first of those numbers is not zero.
* ``psycopg.connect("postgresql://root@localhost:26257/...", connect_timeout=8)`` ->
  ``ConnectionTimeout``.  The local node is **not** running; ``crdb()`` therefore
  defaults to the Cloud DSN in ``.env`` and no program in this fleet may require Docker.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

__all__ = [
    "REDACTED",
    "REGION",
    "RUN_USD_CEILING",
    "USD_PER_1K_TOKENS",
    "CostCeilingExceeded",
    "ResidencyError",
    "artefact",
    "assert_in_region",
    "bedrock_control",
    "bedrock_runtime",
    "check_cost_ceiling",
    "cloudwatch",
    "crdb",
    "dotenv",
    "redact",
    "repo_root",
    "session",
    "sha256_hex",
    "token_ledger_entry",
    "with_retry",
]

# ═══════════════════════════════════════════════════════════════════════════════════════
# 0 · Constants
# ═══════════════════════════════════════════════════════════════════════════════════════

#: The residency region.  ``ARCHITECTURE §10.1`` and
#: ``providers/bedrock_titan.py::REQUIRED_REGION`` say the same word, and this fleet is
#: the third place it has to be true.
REGION: Final[str] = "ap-southeast-2"

#: The AWS profile used when ``AWS_PROFILE`` is unset.  Named rather than implicit so a
#: machine with several profiles cannot silently bill the wrong account.
DEFAULT_PROFILE: Final[str] = "mainline-dev"

#: What every scrubbed value becomes.  One token, so ``grep -c '<redacted>'`` over
#: ``evidence/`` is a meaningful census.
REDACTED: Final[str] = "<redacted>"

#: Fleet spend ceiling for a single program's run, from the AWS-execution plan §6.6.
#: A worker that would exceed it stops and records why instead of spending.
RUN_USD_CEILING: Final[float] = 0.50

#: The retryable SQLSTATE, and the only one.  ``40001`` is CockroachDB's serialization
#: failure.  Every other state is a fact about the SQL, and retrying it is a way of
#: reporting the same defect eight times.
RETRYABLE_SQLSTATE: Final[str] = "40001"

#: Routing prefixes that leave the residency region.  ``global.`` is the loud one: on
#: this account it is the *only* identifier that can serve ``cohere.embed-v4``, so the
#: choice at v4 is residency versus that model, and this constant is where that choice
#: is made rather than forgotten.
CROSS_REGION_PREFIXES: Final[frozenset[str]] = frozenset({"global", "us", "eu", "apac"})


class ResidencyError(RuntimeError):
    """A model identifier would route the call outside :data:`REGION`."""


class CostCeilingExceeded(RuntimeError):
    """A priced run exceeds :data:`RUN_USD_CEILING`."""


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · Repository location and ``.env``
# ═══════════════════════════════════════════════════════════════════════════════════════


def repo_root() -> Path:
    """The repository root, found by walking up from this file.

    Not ``Path.cwd()``: these programs are run from the repository root *and* from an
    editor's scratch directory, and an evidence path that depends on the caller's shell
    is an evidence path that lands in two places.
    """
    return Path(__file__).resolve().parents[2]


_DOTENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def dotenv(path: Path | None = None) -> dict[str, str]:
    """Parse ``.env`` into a plain dict.  Missing file -> empty dict, never an error.

    Deliberately not ``python-dotenv``: this fleet's dependency surface is stdlib plus
    ``boto3`` plus ``psycopg``, and the file is eight ``KEY=value`` lines.  Quotes are
    stripped, ``#`` comments and blank lines are skipped, and **nothing read here is ever
    logged** — the caller gets values, :func:`redact` guards the exits.
    """
    target = path or (repo_root() / ".env")
    out: dict[str, str] = {}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _DOTENV_LINE.match(raw)
        if match is None:
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key] = value
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · Sessions and region-pinned clients
# ═══════════════════════════════════════════════════════════════════════════════════════

_SESSIONS: dict[str, Any] = {}


def session(profile: str | None = None) -> Any:
    """A ``boto3.Session`` for *profile*, honouring ``AWS_PROFILE``, cached per profile.

    Resolution order — ``profile`` argument, then ``AWS_PROFILE``, then
    :data:`DEFAULT_PROFILE`.  If the named profile does not exist but ambient
    credentials do (``AWS_ACCESS_KEY_ID`` in the environment, an instance role, a CI
    OIDC role), the session is built without a profile rather than failing: CI has no
    ``~/.aws/config`` and a fleet that only runs on one laptop proves nothing.

    ``boto3`` is imported inside the function on purpose.  ``tests/unit/aws/`` must run
    with no credentials, no network and — in a minimal environment — no ``boto3`` at all,
    and it imports :func:`redact` and :func:`assert_in_region` from this same module.
    """
    import boto3  # local import: see docstring
    from botocore.exceptions import ProfileNotFound

    name = profile or os.environ.get("AWS_PROFILE") or DEFAULT_PROFILE
    cached = _SESSIONS.get(name)
    if cached is not None:
        return cached
    try:
        made = boto3.Session(profile_name=name, region_name=REGION)
    except ProfileNotFound:
        if not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_ROLE_ARN")):
            raise
        made = boto3.Session(region_name=REGION)
    _SESSIONS[name] = made
    return made


def _client(service: str, *, profile: str | None = None) -> Any:
    return session(profile).client(service, region_name=REGION)


def bedrock_runtime(*, profile: str | None = None) -> Any:
    """``bedrock-runtime``, pinned to :data:`REGION`.  Invocation and Converse live here."""
    return _client("bedrock-runtime", profile=profile)


def bedrock_control(*, profile: str | None = None) -> Any:
    """``bedrock`` control plane, pinned to :data:`REGION`.

    Used for ``list_foundation_models`` / ``list_inference_profiles`` only.  The fleet is
    forbidden from changing model access, creating provisioned throughput, or enabling
    invocation logging; this client is a census instrument.
    """
    return _client("bedrock", profile=profile)


def cloudwatch(*, profile: str | None = None) -> Any:
    """``cloudwatch``, pinned to :data:`REGION`, **read-only by fleet rule**.

    ``AWS/Bedrock`` publishes ``Invocations`` / ``InputTokenCount`` / ``OutputTokenCount``
    per ``ModelId`` at no cost and without any provisioning, which makes it an AWS-side
    attestation that our code ran.  No program in this fleet calls ``put_metric_data``,
    creates an alarm, or creates a log group.
    """
    return _client("cloudwatch", profile=profile)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · Residency
# ═══════════════════════════════════════════════════════════════════════════════════════


def assert_in_region(model_id: str) -> str:
    """Return *model_id*, or raise :class:`ResidencyError` if it routes out of region.

    The rule is the **first dot-separated segment**, because that is what Bedrock's
    inference-profile naming actually encodes:

    * ``global.`` / ``us.`` / ``eu.`` / ``apac.`` are cross-region routing profiles —
      refused.  ``apac.`` is refused with the others even though ``ap-southeast-2`` is in
      APAC: an APAC profile may serve the request from Tokyo or Mumbai, and "somewhere in
      Asia-Pacific" is not the promise ``ARCHITECTURE §10.1`` makes.
    * ``au.`` is an Australia-only profile — allowed.
    * A bare vendor id (``amazon.titan-embed-text-v2:0``, ``cohere.embed-english-v3``)
      has no routing prefix at all and is served in-region on demand — allowed.

    Measured: of the 29 SYSTEM_DEFINED profiles visible in ``ap-southeast-2``, **13 carry
    ``global.``, 8 carry ``apac.`` and 8 carry ``au.``** — counted in
    ``evidence/aws/probe/model-availability.json``.  The refusal is not hypothetical; the
    ids it refuses are one string edit away in every dependent script.
    """
    if not isinstance(model_id, str) or not model_id:
        raise ResidencyError(f"not a model identifier: {model_id!r}")
    prefix = model_id.split(".", 1)[0].lower()
    if prefix in CROSS_REGION_PREFIXES:
        raise ResidencyError(
            f"{model_id!r} routes through the {prefix!r} cross-region inference profile; "
            f"MAINLINE embeds and reasons over Australian safety narratives in {REGION} "
            "or not at all (ARCHITECTURE §10.1). Use an 'au.' profile or a bare "
            "in-region model id."
        )
    return model_id


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Redaction
# ═══════════════════════════════════════════════════════════════════════════════════════

#: A bare 12-digit AWS account id.  Two guards, both put there by a false positive this
#: fleet actually produced rather than by imagination:
#:
#: * the boundaries are *alphanumeric*, not ``\b``, so a 12-digit run inside a
#:   64-character SHA-256 digest is not mangled;
#: * the run may not sit immediately after ``<digit>.`` or before ``.<digit>``, because
#:   the first artefact written by ``probe_bedrock.py`` recorded an L2 norm of
#:   ``1.000000060059`` and a naive rule reads its fraction as an account id.
#:
#: An evidence file whose numbers have been silently corrupted by its own redactor is
#: worse than one that leaks, because it looks fine.
_ACCOUNT_ID = re.compile(r"(?<![0-9A-Za-z])(?<!\d\.)\d{12}(?![0-9A-Za-z])(?!\.\d)")

#: The account field of an ARN, matched structurally as well, so that a future account id
#: that is not twelve digits still gets stripped.
_ARN_ACCOUNT = re.compile(r"(arn:aws[a-z0-9-]*:[a-z0-9-]*:[a-z0-9-]*:)([0-9]{4,})(:)")

#: A password in a connection string.  ``psycopg.OperationalError`` quotes the DSN on
#: almost every failure path, which is exactly the string that ends up in an artefact.
_DSN_PASSWORD = re.compile(r"(?i)\b(postgres(?:ql)?://[^:/@\s]+):[^@\s]*@")
_KV_PASSWORD = re.compile(r"(?i)\b(password|passwd|pwd)\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s&;]+)")

#: AWS access-key ids.  The prefix set is AWS's own unique-id prefix list.
_ACCESS_KEY_ID = re.compile(
    r"(?<![0-9A-Za-z])(?:AKIA|ASIA|AIDA|AROA|AGPA|AIPA|ANPA|ANVA|APKA|ABIA|ACCA)"
    r"[0-9A-Z]{16}(?![0-9A-Za-z])"
)

#: A secret-access-key / session-token shape: a base64-ish run of 40 characters or more.
#: Restricted to runs that contain at least one of ``+ / =`` so it cannot swallow a
#: 40-hex-character identifier or a 64-character SHA-256 digest — this fleet publishes
#: digests, and a redactor that eats its own evidence has destroyed what it was
#: protecting.  An all-alphanumeric secret is caught by its key name instead
#: (:data:`_SENSITIVE_KEY`, :data:`_NAMED_SECRET`).
_SECRET_SHAPE = re.compile(
    r"(?<![0-9A-Za-z+/=])(?=[A-Za-z0-9+/=]{40,}(?![0-9A-Za-z+/=]))"
    r"[A-Za-z0-9+/=]*[+/=][A-Za-z0-9+/=]*"
)

#: A ``SESSION``/``API`` style opaque credential quoted after its own name.
_NAMED_SECRET = re.compile(
    r"(?i)\b(aws_secret_access_key|aws_session_token|secret_?access_?key|session_?token|"
    r"api[_-]?key|cc_api_key)\b(\s*[:=]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s,&;}]+)"
)

#: Dict keys whose *value* is a credential whatever it looks like.  Deliberately anchored
#: and enumerated rather than a substring match on ``token``: ``inputTextTokenCount``,
#: ``inputTokens`` and ``token_ledger`` are the numbers this fleet exists to publish, and
#: a redactor that eats them has destroyed the evidence to protect it.
_SENSITIVE_KEY = re.compile(
    r"(?i)^(?:aws[_-]?)?("
    r"secret|secrets|secret[_-]?access[_-]?key|secretaccesskey|"
    r"access[_-]?key|access[_-]?key[_-]?id|accesskeyid|"
    r"session[_-]?token|sessiontoken|security[_-]?token|"
    r"password|passwd|pwd|passphrase|"
    r"api[_-]?key|apikey|cc[_-]?api[_-]?key|"
    r"authorization|auth[_-]?token|credential|credentials|dsn|conn(?:ection)?[_-]?string"
    r")$"
)


def _redact_text(text: str) -> str:
    text = _ARN_ACCOUNT.sub(rf"\1{REDACTED}\3", text)
    text = _ACCOUNT_ID.sub(REDACTED, text)
    text = _DSN_PASSWORD.sub(rf"\1:{REDACTED}@", text)
    text = _KV_PASSWORD.sub(rf"\1={REDACTED}", text)
    text = _ACCESS_KEY_ID.sub(REDACTED, text)
    text = _NAMED_SECRET.sub(rf"\1\2{REDACTED}", text)
    return _SECRET_SHAPE.sub(REDACTED, text)


def redact(obj: Any) -> Any:
    """Recursively scrub *obj* of anything that must not reach a committed file.

    Four classes, each one a real leak path observed in this repository's own history:

    1. the **12-digit account id**, bare or inside an ARN's account field;
    2. a **DSN password** — the Cloud connection string carries one and every driver
       error quotes it back;
    3. an **AWS key shape** — ``AKIA…``/``ASIA…`` ids, a 40-character secret, or any
       value sitting under a key named for a credential;
    4. ``CC_API_KEY``, the CockroachDB Cloud service-account key in ``.env``.

    Containers are rebuilt, not mutated: the caller's object is untouched, so redaction
    at the exit cannot corrupt the in-memory value a program is still computing with.
    Non-string scalars pass through unchanged **unless their key is sensitive**, which is
    how a numeric-looking credential is still caught.

    ``tuple`` becomes ``list`` and non-string mapping keys become strings, because the
    output of this function is destined for :func:`json.dump` and a value that cannot be
    serialised is a failure at the worst possible moment.
    """
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            name = key if isinstance(key, str) else str(key)
            if _SENSITIVE_KEY.match(name.strip()):
                out[_redact_text(name)] = REDACTED
            else:
                out[_redact_text(name)] = redact(value)
        return out
    if isinstance(obj, (list, tuple)):
        return [redact(item) for item in obj]
    if isinstance(obj, (set, frozenset)):
        # ``key=str`` rather than natural ordering: a heterogeneous set would otherwise
        # raise a TypeError here, after the AWS calls have been made and paid for.
        return sorted((redact(item) for item in obj), key=str)
    if isinstance(obj, (bool, int, float)) or obj is None:
        return obj
    if isinstance(obj, (bytes, bytearray)):
        obj = bytes(obj).decode("utf-8", "replace")
    elif isinstance(obj, datetime):
        # ``boto3`` hands back tz-aware datetimes in control-plane listings; a naive
        # datetime in an evidentiary payload is an unanswerable question later.
        obj = obj.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return _redact_text(obj if isinstance(obj, str) else str(obj))


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · Hashing and the evidence envelope
# ═══════════════════════════════════════════════════════════════════════════════════════


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256.  ``bytes`` only — a caller that has to choose an encoding
    should choose it visibly, at the call site, where the choice is reviewable."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"sha256_hex takes bytes, got {type(data).__name__}")
    return sha256(bytes(data)).hexdigest()


def _generated_by() -> str:
    """The program that wrote the artefact, as a repository-relative path.

    Falls back to the interpreter's own description rather than to a placeholder: an
    envelope that cannot name its producer should say so loudly.
    """
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if not argv0:
        return "python -c (no argv[0])"
    try:
        return Path(argv0).resolve().relative_to(repo_root()).as_posix()
    except (ValueError, OSError):
        return Path(argv0).name or "unknown"


def artefact(
    path: str | Path,
    payload: Any,
    *,
    kind: str,
    caveats: Sequence[str],
    synthetic: bool = False,
) -> Path:
    """Write *payload* to *path* inside the fleet's evidence envelope.  Returns the path.

    The envelope is fixed and every field earns its place::

        {"artefact":     repository-relative path, so a quoted fragment can be found again
         "kind":         what a reader should expect, e.g. "bedrock-probe"
         "generated_by": the program that wrote it
         "generated_at": UTC, ISO-8601, 'Z'
         "region":       ap-southeast-2, restated per file so residency is auditable
         "synthetic":    is the *subject matter* fabricated?
         "caveats":      what this file does NOT prove — required, may be empty
         "payload":      the measurement}

    ``caveats`` is a **required keyword** because the failure mode this fleet is trying to
    avoid is an artefact that reads as broader than its evidence.  Passing ``[]`` is a
    claim that there are none, made deliberately.

    ``synthetic`` defaults to ``False`` and describes the *subject*, never the *call*: a
    live Bedrock invocation over a fabricated incident narrative is ``synthetic=True``.
    A worker embedding ``trappoint_recall.corpora.synthetic`` must pass ``True``.

    Determinism: ``sort_keys``, ``indent=2``, one trailing newline, and the timestamp
    lives *inside* the JSON rather than in the filename, so a re-run overwrites in place
    and ``git diff`` shows what actually changed.  Everything — payload, caveats, and the
    envelope itself — passes through :func:`redact` before it is serialised.
    """
    target = Path(path)
    if not target.is_absolute():
        target = repo_root() / target
    try:
        relative = target.resolve().relative_to(repo_root()).as_posix()
    except (ValueError, OSError):
        relative = target.name
    envelope = {
        "artefact": relative,
        "kind": kind,
        "generated_by": _generated_by(),
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "region": REGION,
        "synthetic": bool(synthetic),
        "caveats": list(caveats),
        "payload": payload,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(redact(envelope), sort_keys=True, indent=2, ensure_ascii=False)
    target.write_text(text + "\n", encoding="utf-8")
    return target


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · Prices and the token ledger
# ═══════════════════════════════════════════════════════════════════════════════════════

#: **Published on-demand list prices, USD per 1 000 tokens, ``ap-southeast-2``, recorded
#: 2026-08-11.**  These are declared, not measured: this fleet has read no bill and the
#: AWS Price List API is not in its permission set.  Every ledger entry carries
#: :data:`PRICE_BASIS` so no downstream document can quote a cost as an observation.
#:
#: Embedding models bill input only; ``output`` is ``0.0`` for them and that zero is a
#: statement about the billing model, not a missing number.
USD_PER_1K_TOKENS: Final[dict[str, dict[str, float]]] = {
    "amazon.titan-embed-text-v2:0": {"input": 0.00002, "output": 0.0},
    "cohere.embed-english-v3": {"input": 0.0001, "output": 0.0},
    "cohere.embed-multilingual-v3": {"input": 0.0001, "output": 0.0},
    "cohere.embed-v4:0": {"input": 0.00012, "output": 0.0},
    "global.cohere.embed-v4:0": {"input": 0.00012, "output": 0.0},
    "au.anthropic.claude-haiku-4-5-20251001-v1:0": {"input": 0.001, "output": 0.005},
    "au.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 0.003, "output": 0.015},
}

#: Attached to every ledger entry.  A cost with no stated basis is a cost that will be
#: quoted as measured by the third document that repeats it.
PRICE_BASIS: Final[str] = (
    "published on-demand list price for ap-southeast-2, recorded 2026-08-11; declared, "
    "not measured — no bill or Price List API response backs this number"
)


def check_cost_ceiling(usd: float, *, ceiling: float = RUN_USD_CEILING, what: str = "run") -> float:
    """Return *usd*, or raise :class:`CostCeilingExceeded` if it is above *ceiling*.

    Called with an **estimate before spending**, which is the only moment at which the
    exception is useful.  :func:`token_ledger_entry` deliberately does *not* raise: a
    program that has already made the calls must still be able to write its evidence, and
    an over-ceiling entry that never reached disk is an unexplained gap, not a saving.
    """
    if usd > ceiling:
        raise CostCeilingExceeded(
            f"{what} is priced at USD {usd:.4f}, above the fleet ceiling of "
            f"USD {ceiling:.2f}. Stop and record why instead of spending."
        )
    return usd


def token_ledger_entry(
    model_id: str,
    calls: int,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    """One priced row of the fleet's token ledger.

    An unknown model id is **not** an error and **not** silently priced at zero: the row
    is returned with ``priced: false`` and null costs, so an unpriced model shows up as a
    hole in the ledger rather than as a free one.

    ``over_ceiling`` is reported, never raised — see :func:`check_cost_ceiling`.
    """
    price = USD_PER_1K_TOKENS.get(model_id)
    usd_in = None if price is None else round(price["input"] * input_tokens / 1000.0, 8)
    usd_out = None if price is None else round(price["output"] * output_tokens / 1000.0, 8)
    total = None if price is None else round((usd_in or 0.0) + (usd_out or 0.0), 8)
    return {
        "model_id": model_id,
        "calls": int(calls),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "priced": price is not None,
        "usd_per_1k_input": None if price is None else price["input"],
        "usd_per_1k_output": None if price is None else price["output"],
        "usd_input": usd_in,
        "usd_output": usd_out,
        "usd_total": total,
        "over_ceiling": bool(total is not None and total > RUN_USD_CEILING),
        "price_basis": PRICE_BASIS,
    }


def ledger_total(entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum a sequence of :func:`token_ledger_entry` rows, keeping unpriced rows visible."""
    rows = list(entries)
    priced = [r for r in rows if r.get("priced")]
    return {
        "entries": len(rows),
        "unpriced_entries": len(rows) - len(priced),
        "calls": sum(int(r.get("calls", 0)) for r in rows),
        "input_tokens": sum(int(r.get("input_tokens", 0)) for r in rows),
        "output_tokens": sum(int(r.get("output_tokens", 0)) for r in rows),
        "usd_total": round(sum(float(r.get("usd_total") or 0.0) for r in priced), 8),
        "usd_ceiling_per_run": RUN_USD_CEILING,
        "price_basis": PRICE_BASIS,
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · CockroachDB
# ═══════════════════════════════════════════════════════════════════════════════════════

_DSN_DB = re.compile(r"^(?P<head>[a-z+]+://[^/]+)/(?P<db>[^/?]*)(?P<tail>.*)$", re.IGNORECASE)


def _substitute_database(dsn: str, database: str) -> str:
    match = _DSN_DB.match(dsn)
    if match is None:
        raise ValueError("COCKROACH_DSN is not a URI this helper can rewrite")
    return f"{match.group('head')}/{database}{match.group('tail')}"


def _with_connect_timeout(dsn: str, seconds: int) -> str:
    if re.search(r"[?&]connect_timeout=", dsn):
        return re.sub(r"([?&]connect_timeout=)\d+", rf"\g<1>{seconds}", dsn)
    return f"{dsn}{'&' if '?' in dsn else '?'}connect_timeout={seconds}"


def crdb(database: str | None = None, *, dsn: str | None = None, autocommit: bool = True) -> Any:
    """Open a ``psycopg`` connection to ``COCKROACH_DSN``, optionally against *database*.

    The DSN comes from the process environment first and ``.env`` second, so CI can
    inject one without editing a file, and a laptop needs no exports.  ``connect_timeout``
    is forced to **30 seconds**: the target is CockroachDB Cloud Basic in
    ``aws-ap-southeast-1``, cold-start latency is real, and psycopg's default is *no
    timeout at all* — a hang in a session-scoped fixture is the one failure
    ``pytest-timeout`` cannot interrupt (``pyproject.toml``, ``timeout_method``).

    ``autocommit=True`` by default because CockroachDB DDL inside a multi-statement
    transaction can fail at ``COMMIT`` even when every statement succeeded, which would
    let one late failure retroactively un-apply work already reported as applied.

    **The DSN is never returned, logged or stored.**  A caller that wants to name the
    target names the database, which is not a secret.
    """
    import psycopg  # local import: the unit tests must run without a driver present

    raw = dsn or os.environ.get("COCKROACH_DSN") or dotenv().get("COCKROACH_DSN")
    if not raw:
        raise RuntimeError(
            "COCKROACH_DSN is not set in the environment and not present in .env; "
            "no database target"
        )
    if database:
        raw = _substitute_database(raw, database)
    return psycopg.connect(_with_connect_timeout(raw, 30), autocommit=autocommit)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 8 · The 40001 retry loop
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Backoff base, seconds.  ``RETRY_SERIALIZABLE`` clears on the next timestamp push, not
#: after an exponentially long quiet period, so the schedule is linear-scaled with full
#: jitter rather than doubling; a doubling schedule here mostly buys sleep.
BACKOFF_BASE: Final[float] = 0.05
BACKOFF_MAX: Final[float] = 2.0


def with_retry[T](
    fn: Callable[[], T],
    attempts: int = 8,
    *,
    sleep: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
) -> tuple[T, int]:
    """Call *fn*, retrying **only** SQLSTATE ``40001``.  Returns ``(value, retries)``.

    Cloud is a managed multi-node cluster and produces
    ``TransactionRetryWithProtoRefreshError: RETRY_SERIALIZABLE`` under ordinary
    contention; a single-node Docker node never does, which is precisely why this loop
    exists and why the local node cannot be the place a fleet proof is validated.

    **The trip count is returned, not swallowed.**  Insurance whose premium is never
    quoted is indistinguishable from superstition: a caller must publish
    ``retries_40001`` so a reader can see whether the loop fired or merely existed.

    Anything that is not ``40001`` is re-raised immediately and unchanged.  A gate
    refusal (``23514``, ``P0001``) is a *result* in this system, and retrying it would be
    a way of asking the same forbidden question eight times.

    ``sleep`` and ``rand`` are injectable so the loop's behaviour is unit-testable with no
    wall-clock cost and no cluster.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    retries = 0
    while True:
        try:
            return fn(), retries
        except Exception as exc:
            if getattr(exc, "sqlstate", None) != RETRYABLE_SQLSTATE:
                raise
            retries += 1
            if retries >= attempts:
                raise
            # Full jitter over a linearly growing window: bounded, unsynchronised, and
            # never zero-length, so N concurrent writers do not re-collide in lockstep.
            sleep(min(BACKOFF_MAX, BACKOFF_BASE * retries) * (0.5 + rand()))
