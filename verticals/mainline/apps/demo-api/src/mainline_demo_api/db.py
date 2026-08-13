# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One connection, one secret, and the retry a managed cluster actually needs.

THREE THINGS THIS MODULE EXISTS TO GET RIGHT.

**1. One connection per container, health-checked rather than assumed.**
A Lambda execution environment is reused for minutes. Opening a pgwire connection to
CockroachDB Cloud in Singapore costs a TLS handshake plus an auth round trip, and the
deployment lead measured 3.15 s for connect+query from Australia — so a connection per
invocation would make the demo feel broken. It is therefore opened lazily at module
scope and kept. But *kept* is not *trusted*: a connection idle across a freeze/thaw, a
Cloud maintenance event or a cluster restart is a socket that looks open and is not.
:func:`connection` proves it with ``SELECT 1`` on every acquisition and reconnects when
that fails. One extra round trip is the price of never returning a corpse.

**2. The DSN is a secret and is read as one.**
It carries the `mainline-sql` password. It is written into SSM Parameter Store as a
SecureString by the deploy script — never by Terraform, because a Terraform-managed
secret is a plaintext secret in the state file — and read here once per cold start by
name from ``$MAINLINE_DSN_PARAM``. It is cached for the life of the container and never
logged: :func:`redact` exists so that the one place that *would* be tempted to print it
has something correct to print instead.

The SSM call is signed with SigV4 out of :mod:`hashlib` and :mod:`hmac` rather than by
importing boto3. Not because boto3 is unavailable — it is in the runtime image — but
because the deployment package's behaviour would then depend on which boto3 AWS shipped
that month, and because a single ``GetParameter`` is about sixty lines of signing. The
handler's whole dependency closure stays `psycopg` plus the standard library, and
``tests/test_envelope.py`` asserts it.

**3. `40001` is retried on the read paths, and only there.**
A single-node Docker cluster never produces ``RETRY_SERIALIZABLE``. A managed multi-node
cluster does. The deployment lead's first Cloud run of 2026-08-10 died on exactly that,
with no retry loop anywhere in the repository:

    gate_refusal: could not reach the cluster: restart transaction:
    TransactionRetryWithProtoRefreshError: TransactionRetryError:
    retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)

:func:`read` retries the WHOLE callable — not a statement — because the retry unit of a
serializable transaction is the transaction, and re-running one statement of an aborted
one is how you get ``25P02``. It is exported as ``read`` and not as ``call`` on purpose:
a transition is NOT idempotent, ``40001`` there means UNDECIDED, and
``console/src/data/transport.ts`` bans a blanket retry for exactly that reason —
*"a helper that re-sends a merge because a socket closed is a helper that can issue a
permit twice."* The POST side gets no retry from this module.

**4. The connect budget is a TOTAL, and it belongs to the caller.**
Added 2026-08-14, after ``/v1/health`` was measured at 10.1 s against a HEALTHY database
and the whole of it turned out to be :func:`connection` — ``HEALTH_STATEMENT`` itself
costs 0.003 s. Two independent defects lived in :func:`_open`, and neither is in
``health.py``:

* **A dead address was paid for in full.** psycopg 3.3 resolves the host itself
  (:func:`psycopg.conninfo.conninfo_attempts` → one attempt per ``getaddrinfo`` answer)
  and then applies ``connect_timeout`` **per attempt**. ``getaddrinfo('localhost', 26257)``
  answers ``[::1, 127.0.0.1]`` and the pinned container publishes IPv4 only, so every cold
  connect waited out the entire budget against a black-holed ``::1`` and then succeeded on
  ``127.0.0.1`` in 0.5 ms. Measured on this host: ``localhost`` 10.124 s versus
  ``127.0.0.1`` 0.017 s, and ``localhost:1`` — two dead addresses — **20.081 s**, which is
  already past the Lambda's own timeout and therefore turns "the database is unreachable"
  into "the function timed out", the exact sentence the constant below exists to prevent.
  :func:`_address_that_answers` now races the resolved addresses at the TCP level with one
  non-blocking socket each and hands psycopg the one that answers, so the budget bounds the
  WHOLE connect instead of each attempt separately.
* **The caller's ``connect_timeout`` was silently overridden.** ``_open`` passed
  ``connect_timeout=CONNECT_TIMEOUT_SECONDS`` as a **keyword**, and a keyword outranks both
  the DSN's query string and ``$PGCONNECT_TIMEOUT``. So a DSN asking for
  ``connect_timeout=2`` waited 10 s (measured: 10.055 s) and no caller could choose a
  budget shorter than this module's. The constant is now SUPPLIED when nobody said
  anything and IMPOSED on nobody, in libpq's own precedence order.

The 130.1 s the repository-root ``conftest.py`` recorded on 2026-08-10 and attributed to
"a black-holed address" is the same mechanism seen without a budget: 130 is
``psycopg.conninfo._DEFAULT_CONNECT_TIMEOUT``, applied to the one dead address, plus the
0.101 s the live one then took. It is psycopg's default, not the operating system's TCP
timeout — which matters, because it means the number moves when the DSN says so.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import errno
import hashlib
import hmac
import json
import os
import random
import selectors
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any, Final

import psycopg
from psycopg.conninfo import conninfo_attempts, conninfo_to_dict, timeout_from_conninfo
from psycopg.rows import dict_row

__all__ = [
    "APPLICATION_NAME",
    "CONNECT_TIMEOUT_ENV",
    "CONNECT_TIMEOUT_SECONDS",
    "READ_RETRY_ATTEMPTS",
    "DsnUnavailable",
    "close",
    "connection",
    "dsn_source",
    "read",
    "read_transaction",
    "redact",
    "reset_dsn_cache",
    "resolve_dsn",
    "server_now",
]

#: Shows up in ``SHOW SESSIONS`` and in the Cloud console's slow-query view. A judge
#: watching the cluster while they drive the demo can see which sessions are ours.
APPLICATION_NAME: Final = "mainline-demo-api"

#: libpq ``connect_timeout``, seconds. Not optional: unset, a connect to a black-holed
#: address blocks for over two minutes — longer than the Lambda's own timeout, which
#: turns "the database is unreachable" into "the function timed out", a different and
#: much less useful sentence. (Measured 2026-08-14: "over two minutes" is 130 s exactly,
#: because that is ``psycopg.conninfo._DEFAULT_CONNECT_TIMEOUT`` and psycopg — not the
#: kernel — is what gives up.)
#:
#: It is a DEFAULT and not a policy. :func:`_open` supplies it only when neither the DSN
#: nor ``$PGCONNECT_TIMEOUT`` states one; see :func:`_supplied_connect_timeout`.
CONNECT_TIMEOUT_SECONDS: Final = 10

#: libpq's own environment name for the same budget. Named here so that the precedence in
#: :func:`_supplied_connect_timeout` is libpq's precedence rather than a second one
#: invented in this file.
CONNECT_TIMEOUT_ENV: Final = "PGCONNECT_TIMEOUT"

#: ``connect_ex`` on a non-blocking socket reports "started, not finished" as
#: ``EINPROGRESS`` on POSIX and as ``EWOULDBLOCK`` on Windows — measured here,
#: ``errno.EWOULDBLOCK`` is 10035 (``WSAEWOULDBLOCK``) and every pending loopback connect
#: returned it. Both spellings are accepted because the same file runs on a workstation
#: and in the Lambda.
_CONNECT_PENDING: Final = frozenset({errno.EINPROGRESS, errno.EWOULDBLOCK})

#: Attempts, not retries. 1 means "no retry".
READ_RETRY_ATTEMPTS: Final = 4

#: Backoff base, seconds. 50 ms, 100 ms, 200 ms — bounded so the worst case adds 350 ms
#: to a read, well inside a 10 s Lambda budget.
_BACKOFF_BASE_SECONDS: Final = 0.05

#: SQLSTATE 40001, ``serialization_failure``. CockroachDB's ``RETRY_SERIALIZABLE``.
_SERIALIZATION_FAILURE: Final = "40001"

#: Direct DSN. Set by the tests and by anyone running this against a local node. When it
#: is present SSM is never consulted, which is what lets the whole read surface be
#: exercised on a laptop with no AWS credentials at all.
DSN_ENV: Final = "MAINLINE_DSN"

#: The NAME of the SSM SecureString holding the DSN. Terraform is given this name; it is
#: never given the value.
DSN_PARAM_ENV: Final = "MAINLINE_DSN_PARAM"

_SSM_TIMEOUT_SECONDS: Final = 5
_SIGV4_ALGORITHM: Final = "AWS4-HMAC-SHA256"

#: Cached for the life of the execution environment. Never logged, never returned by any
#: handler path, never put in an envelope.
_dsn_cache: str | None = None
_dsn_source: str | None = None
_conn: psycopg.Connection[Any] | None = None


class DsnUnavailable(RuntimeError):
    """No DSN could be obtained.

    Distinct from a connection failure on purpose: ``health.py`` reports the two
    differently, because "nobody told this function where the database is" and "the
    database did not answer" are fixed by different people.
    """


def redact(dsn: str) -> str:
    """Render *dsn* with its password removed, safe for a log line or an error body.

    Everything between ``//user:`` and the next ``@`` becomes ``***``. Deliberately
    crude: it over-redacts a DSN with no password (leaving ``user:***@``) rather than
    under-redacting one that has an ``@`` in the password.
    """
    if "://" not in dsn:
        return "***"
    scheme, _, rest = dsn.partition("://")
    if "@" not in rest:
        return f"{scheme}://{rest}"
    authority, _, tail = rest.rpartition("@")
    user, sep, _password = authority.partition(":")
    return f"{scheme}://{user}{':***' if sep else ''}@{tail}"


# ── SigV4, for exactly one call ─────────────────────────────────────────────────────


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, stamp: str, region: str, service: str) -> bytes:
    dated = _sign(f"AWS4{secret}".encode(), stamp)
    return _sign(_sign(_sign(dated, region), service), "aws4_request")


def _ssm_get_parameter(name: str, region: str) -> str:
    """Fetch one SecureString from SSM Parameter Store, decrypted, over signed HTTPS.

    Credentials come from the environment, which is where the Lambda runtime puts the
    role's temporary ones (``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``,
    ``AWS_SESSION_TOKEN``). No credential file, no IMDS walk, no profile resolution —
    every one of those is a code path that behaves differently on a workstation than in
    a Lambda, and this function must behave the same way in both or it is untestable.
    """
    access_key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not access_key or not secret_key:
        raise DsnUnavailable(
            f"${DSN_PARAM_ENV} names SSM parameter {name!r} but neither $AWS_ACCESS_KEY_ID nor "
            "$AWS_SECRET_ACCESS_KEY is set, so the GetParameter call cannot be signed. In Lambda "
            "these are injected by the runtime; on a workstation, export them or set "
            f"${DSN_ENV} to a DSN directly."
        )

    host = f"ssm.{region}.amazonaws.com"
    endpoint = f"https://{host}/"
    target = "AmazonSSM.GetParameter"
    body = json.dumps({"Name": name, "WithDecryption": True}, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(body).hexdigest()

    now = _dt.datetime.now(_dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    stamp = now.strftime("%Y%m%d")

    headers = {
        "content-type": "application/x-amz-json-1.1",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": target,
    }
    if session_token:
        headers["x-amz-security-token"] = session_token

    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{key}:{headers[key].strip()}\n" for key in sorted(headers))
    canonical_request = "\n".join(
        ["POST", "/", "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{stamp}/{region}/ssm/aws4_request"
    to_sign = "\n".join(
        [
            _SIGV4_ALGORITHM,
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(secret_key, stamp, region, "ssm"), to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            **{key.title(): value for key, value in headers.items() if key != "host"},
            "Authorization": (
                f"{_SIGV4_ALGORITHM} Credential={access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_SSM_TIMEOUT_SECONDS) as response:  # noqa: S310
            document = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - needs a live AWS endpoint
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise DsnUnavailable(
            f"SSM GetParameter {name!r} in {region} answered HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
        raise DsnUnavailable(
            f"SSM GetParameter {name!r} in {region} did not answer: {exc}"
        ) from exc

    try:
        value = document["Parameter"]["Value"]
    except (KeyError, TypeError) as exc:  # pragma: no cover
        raise DsnUnavailable(
            f"SSM GetParameter {name!r} answered without Parameter.Value "
            f"(keys: {sorted(document) if isinstance(document, dict) else type(document).__name__})"
        ) from exc
    if not isinstance(value, str) or not value.strip():
        raise DsnUnavailable(f"SSM parameter {name!r} holds no value")
    return value.strip()


# ── The DSN ─────────────────────────────────────────────────────────────────────────


def resolve_dsn(*, refresh: bool = False) -> str:
    """Resolve the DSN, from the environment or from SSM, cached for the container's life.

    ``$MAINLINE_DSN`` wins when set. That ordering is what makes this module testable
    without AWS and is stated in the README, so nobody has to discover it by reading
    this function.
    """
    global _dsn_cache, _dsn_source  # noqa: PLW0603 - the cache IS the point: one
    # decryption per execution environment, never one per invocation.
    if _dsn_cache is not None and not refresh:
        return _dsn_cache

    direct = os.environ.get(DSN_ENV, "").strip()
    if direct:
        _dsn_cache, _dsn_source = direct, f"env:{DSN_ENV}"
        return _dsn_cache

    name = os.environ.get(DSN_PARAM_ENV, "").strip()
    if not name:
        raise DsnUnavailable(
            f"neither ${DSN_ENV} nor ${DSN_PARAM_ENV} is set, so this function does not know "
            "which database to read. In the deployed stack Terraform sets "
            f"${DSN_PARAM_ENV} to the name of the SecureString the deploy script wrote."
        )
    region = (
        os.environ.get("AWS_REGION", "").strip() or os.environ.get("AWS_DEFAULT_REGION", "").strip()
    )
    if not region:
        raise DsnUnavailable(
            f"${DSN_PARAM_ENV} is set to {name!r} but neither $AWS_REGION nor "
            "$AWS_DEFAULT_REGION is, so the SSM endpoint cannot be addressed."
        )
    _dsn_cache = _ssm_get_parameter(name, region)
    _dsn_source = f"ssm:{name}@{region}"
    return _dsn_cache


def dsn_source() -> str | None:
    """Where the cached DSN came from — a name, never a value. Safe to put in a body."""
    return _dsn_source


# ── The connection ──────────────────────────────────────────────────────────────────


def _supplied_connect_timeout(params: dict[str, Any]) -> int | None:
    """Return this module's budget, or ``None`` when somebody else has already stated one.

    libpq's precedence is DSN, then ``$PGCONNECT_TIMEOUT``, then a compiled default, and
    a **keyword argument outranks all three**. That is what made
    ``connect_timeout=CONNECT_TIMEOUT_SECONDS`` a defect rather than a default: a DSN
    asking for ``connect_timeout=2`` got 10 (measured: 10.055 s against a black-holed
    address that answered in 2.005 s when asked directly), and no caller — not a test, not
    an operator, not the repository-root ``conftest.py`` that exports
    ``PGCONNECT_TIMEOUT=5`` precisely so that no fixture can hang — could choose a shorter
    one.

    So this returns a value only when nobody has spoken. The bound the module docstring
    promises is still absolute: something always states a budget, and where nothing else
    does it is :data:`CONNECT_TIMEOUT_SECONDS`.
    """
    stated = params.get("connect_timeout")
    if stated is not None and str(stated).strip():
        return None
    if os.environ.get(CONNECT_TIMEOUT_ENV, "").strip():
        return None
    return CONNECT_TIMEOUT_SECONDS


def _targets(params: dict[str, Any]) -> list[tuple[str, int]]:
    """Return the addresses psycopg is about to try, in the order it would try them.

    Obtained from :func:`psycopg.conninfo.conninfo_attempts` rather than from a second
    ``getaddrinfo`` of our own, so the set raced below is *by construction* the set the
    driver would otherwise walk one full timeout at a time. psycopg 3.3 does this
    resolution in Python — ``_conninfo_attempts._resolve_hostnames`` — and
    ``Connection.connect`` then loops over the results applying
    ``timeout_from_conninfo(params)`` to each, which is the whole of mechanism (a).

    Returns an empty list wherever there is nothing to choose between, and the caller then
    leaves the DSN completely alone:

    * **fewer than two attempts** — a single address, an ``hostaddr`` the caller already
      resolved, a Unix socket path. The budget already bounds the whole connect and a
      probe would only add a round trip.
    * **more than one host name** — a comma-separated ``host`` list is a caller asking for
      specific hosts to be tried in a specific order, possibly with different ports,
      ``target_session_attrs`` or ``load_balance_hosts``. Racing them would silently
      re-decide a decision the caller made.
    """
    attempts = conninfo_attempts(params)
    if len(attempts) < 2 or len({attempt.get("host") for attempt in attempts}) != 1:
        return []
    targets: list[tuple[str, int]] = []
    for attempt in attempts:
        address = attempt.get("hostaddr")
        if not address:
            return []
        targets.append((str(address), int(str(attempt.get("port") or "5432"))))
    return targets


def _race(targets: list[tuple[str, int]], budget: float) -> tuple[str | None, dict[str, str]]:
    """Open one non-blocking socket per address at once; return the first that answers.

    Not a retry and not a thread: one ``connect_ex`` per address, all in flight together,
    and a single :mod:`selectors` wait over the lot. A dead address family therefore costs
    nothing at all rather than one full timeout — it simply never becomes writable, and the
    live one is already selected by then. Measured on this host, ``[::1, 127.0.0.1]`` at
    port 26257 resolves in 0.4 ms where the sequential walk cost 10.1 s.

    ``EVENT_WRITE`` is the right mask on both platforms: a failed connect is reported in
    the *exception* set on Windows, and :class:`selectors.SelectSelector` merges that set
    into the write set there (``r, w, x = select.select(r, w, w, timeout); return r, w + x``).
    ``SO_ERROR`` then separates "connected" from "failed" — being woken is not the same as
    having arrived.

    Returns ``(address, failures)``. The failures map is the whole diagnosis when nothing
    answered, and it distinguishes an address that REFUSED from one that never replied,
    because the caller treats those two differently.
    """
    deadline = time.monotonic() + budget
    failures: dict[str, str] = {}
    selector = selectors.DefaultSelector()
    pending: dict[Any, str] = {}
    try:
        for address, port in targets:
            sock, reason = _begin_connect(address, port)
            if sock is None and not reason:
                # Answered before we had to wait at all. Keep the resolver's order: the
                # first address that works is the one the operating system preferred.
                return address, failures
            if sock is None:
                failures[address] = reason
                continue
            selector.register(sock, selectors.EVENT_WRITE, address)
            pending[sock] = address

        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            events = selector.select(remaining)
            if not events:
                break
            for key, _mask in events:
                sock, address = key.fileobj, str(key.data)
                code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)  # type: ignore[union-attr]
                selector.unregister(sock)
                del pending[sock]
                if code == 0:
                    sock.close()  # type: ignore[union-attr]
                    return address, failures
                failures[address] = _errno_text(code)
                sock.close()  # type: ignore[union-attr]
        for address in pending.values():
            failures[address] = f"no answer within {budget:g}s"
    finally:
        for sock in pending:
            with contextlib.suppress(OSError):
                sock.close()
        selector.close()
    return None, failures


def _begin_connect(address: str, port: int) -> tuple[Any, str]:
    """Start one non-blocking connect and report which of three things happened.

    ``(socket, "")`` — in flight, hand it to the selector.
    ``(None, "")`` — answered immediately; there is nothing left to wait for.
    ``(None, reason)`` — failed outright, and *reason* is what to tell the operator.
    """
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setblocking(False)
        code = sock.connect_ex((address, port))
    except OSError as exc:  # pragma: no cover - a malformed address, not a dead one
        sock.close()
        return None, f"[{exc.errno}] {exc.strerror or exc}"
    if code == 0:
        sock.close()
        return None, ""
    if code in _CONNECT_PENDING:
        return sock, ""
    sock.close()
    return None, _errno_text(code)


def _errno_text(code: int) -> str:
    """``[10061] connection refused``. The number first, because Windows has no strings.

    ``os.strerror`` answers *Unknown error* for every ``WSAE*`` code — measured — so the
    numeric code is the part that is always true and it leads.
    """
    name = errno.errorcode.get(code, "")
    try:
        text = os.strerror(code)
    except (OverflowError, ValueError):  # pragma: no cover - defensive
        text = ""
    return f"[{code}{f' {name}' if name else ''}] {text}".strip()


def _address_that_answers(params: dict[str, Any]) -> str | None:
    """Which of the resolved addresses to hand psycopg, or ``None`` to hand it nothing.

    ``None`` means *do not touch the DSN*, and it is returned for exactly one reason:
    there was nothing to choose between (see :func:`_targets`).

    When there WAS something to choose between and nothing answered, this raises rather
    than falling through, because the budget is a total and falling through would spend it
    again once per address. Measured while building this: an earlier draft did fall
    through, and ``localhost:1`` cost **22.1 s** — 2.1 s to establish that both loopback
    addresses were dead, then 20 s for psycopg to establish it a second time, ten seconds
    per address. That is worse than the 20.1 s defect it was meant to fix, and it is the
    "the function timed out" failure :data:`CONNECT_TIMEOUT_SECONDS` exists to prevent.

    Nothing is lost by not deferring to psycopg's own message. Everything psycopg says
    that this cannot — the sslmode, the authentication method, the server's own
    complaint — is said AFTER a TCP connection exists, and an address that gets that far
    wins the race and is handed over. This branch is reachable only when no address
    accepted a connection at all, and there the per-address report below is strictly more
    informative than libpq's, which names only the last attempt.

    Never puts the DSN in the exception: it carries the ``mainline-sql`` password. Host,
    port and addresses only.
    """
    targets = _targets(params)
    if not targets:
        return None

    budget = timeout_from_conninfo(params)
    chosen, failures = _race(targets, budget)
    if chosen is not None:
        return chosen

    host = params.get("host") or "?"
    port = targets[0][1]
    detail = "; ".join(f"{address}: {failures.get(address, 'no answer')}" for address, _ in targets)
    raise psycopg.OperationalError(
        f"connection to {host}:{port} failed: none of the {len(targets)} resolved addresses "
        f"answered within {budget:g}s ({detail})"
    )


def _open(dsn: str) -> psycopg.Connection[Any]:
    """One connection, with the caller's budget and an address that is known to answer.

    ``application_name`` stays a keyword, and that is not an inconsistency with
    :func:`_supplied_connect_timeout` sitting beside it. :data:`APPLICATION_NAME` is what
    this module calls ITSELF in ``SHOW SESSIONS`` — a judge watching the cluster picks our
    sessions out by it — so a caller who could rename it would defeat the only thing it is
    for. ``connect_timeout`` is a budget, and the party that knows how long it can afford
    to wait is the caller. Identity is the module's; policy is the caller's.
    """
    params = dict(conninfo_to_dict(dsn))
    supplied = _supplied_connect_timeout(params)
    if supplied is not None:
        params["connect_timeout"] = str(supplied)

    extra: dict[str, Any] = {} if supplied is None else {"connect_timeout": supplied}
    chosen = _address_that_answers(params)
    if chosen is not None:
        extra["hostaddr"] = chosen

    # The caller's DSN string is passed through verbatim; `extra` only ever ADDS keywords
    # the DSN did not carry. Rebuilding it here would mean this module re-encoding a secret
    # on every cold start for no gain.
    return psycopg.connect(
        dsn,
        autocommit=True,
        application_name=APPLICATION_NAME,
        row_factory=dict_row,
        **extra,
    )


def _alive(conn: psycopg.Connection[Any]) -> bool:
    if conn.closed:
        return False
    try:
        conn.execute("SELECT 1").fetchone()
    except psycopg.Error:
        return False
    return True


def connection(*, dsn: str | None = None) -> psycopg.Connection[Any]:
    """Return the module-scope connection, proven alive.

    Opened lazily, reused across warm invocations, and replaced whenever ``SELECT 1``
    does not come back. Passing *dsn* bypasses :func:`resolve_dsn` and is what the tests
    use; it also replaces a cached connection that was opened against a different DSN,
    so a test cannot inherit the previous test's database.
    """
    global _conn  # noqa: PLW0603 - one connection per container is the whole design
    target = dsn if dsn is not None else resolve_dsn()

    if _conn is not None:
        if getattr(_conn, "_mainline_dsn", None) != target:
            close()
        elif _alive(_conn):
            return _conn
        else:
            close()

    conn = _open(target)
    # Stashed so a DSN change is detectable. `info.dsn` would do for libpq keyword DSNs
    # but normalises URLs, so two spellings of one database would compare unequal.
    conn._mainline_dsn = target  # type: ignore[attr-defined]
    _conn = conn
    return conn


def close() -> None:
    """Drop the cached connection. Idempotent, and never raises."""
    global _conn
    conn, _conn = _conn, None
    if conn is not None:
        # `contextlib.suppress` would read better and say less: the point is that a
        # socket already broken by the failure we are recovering from must not raise
        # a SECOND exception on the way out and mask the first.
        with contextlib.suppress(Exception):
            conn.close()


def reset_dsn_cache() -> None:
    """Forget the cached DSN and close the connection. For tests and for a rotated secret."""
    global _dsn_cache, _dsn_source  # noqa: PLW0603 - see resolve_dsn()
    _dsn_cache = None
    _dsn_source = None
    close()


def server_now(conn: psycopg.Connection[Any]) -> _dt.datetime:
    """Read the DATABASE's clock.

    Every envelope's ``server_date`` comes from here. The console subtracts it from its
    own ``Date.now()`` to render skew, so reading a Lambda's clock instead would show a
    judge how well AWS keeps time — a true statement about the wrong machine.
    """
    row = conn.execute("SELECT now() AS server_now").fetchone()
    if row is None:  # pragma: no cover - `SELECT now()` returns a row or raises
        raise psycopg.OperationalError("SELECT now() returned no row")
    value = row["server_now"]
    if not isinstance(value, _dt.datetime):  # pragma: no cover - typed TIMESTAMPTZ
        raise psycopg.OperationalError(f"SELECT now() returned {type(value).__name__}")
    return value


@contextlib.contextmanager
def read_transaction(conn: psycopg.Connection[Any]) -> Iterator[psycopg.Connection[Any]]:
    """One transaction in which the session cannot write, for the length of one read.

    Two properties, both needed:

    * **One snapshot.** Several of the twelve resources need four or five statements
      (``clause_ancestry`` needs six). Run in autocommit they would each see a different
      moment, and a payload whose ``closure.ancestor_count`` disagreed with its own
      ``events`` array would be a bug nobody could reproduce.
    * **Read-only, asserted by the cluster.** ``SET TRANSACTION READ ONLY`` makes a
      stray write fail with ``25006`` — measured on CockroachDB v26.2.5:
      ``cannot execute INSERT in a read-only transaction``. This is not a substitute for
      the read-only SQL role W2 grants; it is what protects the demo on a day someone
      points this handler at a DSN with more privilege than it should have.

    Deliberately NOT applied at session level (``default_transaction_read_only``),
    because ``app.py`` hands this same connection to ``transitions.handle_transition``,
    and the four POSTs must be able to write.
    """
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


def read[T](conn: psycopg.Connection[Any], work: Callable[[psycopg.Connection[Any]], T]) -> T:
    """Run *work* against *conn*, retrying SQLSTATE 40001 with bounded backoff.

    *work* must be idempotent and must be the WHOLE unit — typically a function that
    opens one transaction and performs every statement a resource needs, so the
    resource's several queries see one snapshot and a restart re-reads all of them.

    Backoff is exponential with full jitter, capped at :data:`READ_RETRY_ATTEMPTS`
    attempts. Anything that is not 40001 propagates on the first occurrence: this is a
    retry for one named, understood failure mode, not a swallow-and-hope.
    """
    last: psycopg.Error | None = None
    for attempt in range(READ_RETRY_ATTEMPTS):
        try:
            return work(conn)
        except psycopg.Error as exc:
            if exc.sqlstate != _SERIALIZATION_FAILURE:
                raise
            last = exc
            if attempt == READ_RETRY_ATTEMPTS - 1:
                break
            # A 40001 leaves an explicit transaction aborted. In autocommit with
            # `conn.transaction()` psycopg has already rolled it back; the belt-and-braces
            # rollback below costs nothing and makes the state unambiguous.
            with contextlib.suppress(psycopg.Error):
                conn.rollback()
            time.sleep(random.uniform(0, _BACKOFF_BASE_SECONDS * (2**attempt)))  # noqa: S311
    assert last is not None  # noqa: S101 - the loop only breaks with `last` set
    raise last
