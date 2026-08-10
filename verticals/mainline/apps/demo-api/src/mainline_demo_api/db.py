# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
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
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import hmac
import json
import os
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any, Final

import psycopg
from psycopg.rows import dict_row

__all__ = [
    "APPLICATION_NAME",
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
#: much less useful sentence.
CONNECT_TIMEOUT_SECONDS: Final = 10

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


def _open(dsn: str) -> psycopg.Connection[Any]:
    return psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        application_name=APPLICATION_NAME,
        row_factory=dict_row,
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
