# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Singleton election by compare-and-swap, because CockroachDB has no advisory locks.

``pg_advisory_lock`` does not exist on this platform, so the lock is a row and the
election is a CAS on ``mainline_ops.sequencer_lease.epoch``. Migration 0079 states the
shape normatively and this module implements exactly it:

.. code-block:: sql

   UPDATE mainline_ops.sequencer_lease
      SET holder = $new_holder, epoch = $observed_epoch + 1, expires_at = $now + $ttl
    WHERE site_code = $1 AND epoch = $observed_epoch
      AND (holder = $new_holder OR expires_at < $now);

**Zero rows updated means somebody else holds it — that is the entire protocol.** The
invocation aborts cleanly and is *not* retried: EventBridge invokes every 15 s, so a lost
election costs one cycle, and a loser that retried would be the second writer the lease
exists to prevent.

**The ``epoch = $observed_epoch`` fence is not optional.** It is what makes a stale
holder's write lose even when its clock is wrong: a sequencer that sleeps through its own
expiry and wakes still believing it holds the lease observes an epoch that has moved and
updates nothing. A CAS written without the fence — ``WHERE site_code = $1 AND (expires_at
< now() OR holder = $me)`` — looks equivalent and is not: two invocations of the *same*
holder id (a warm Lambda container reused, a retry after a timeout) both match the
``holder = $me`` disjunct and both believe they won.

**This is the one genuinely mutable object in the custody plane, and it holds no
evidence.** Losing every row costs one sequencing cycle; the next invocation finds no
valid lease, takes one, and carries on from ``max(seq)`` in ``mainline.ledger_leaf``,
which is append-only and CAS-protected. An adversary who rewrites this table causes a
duplicate sequencer to run — and the duplicate then collides on ``ledger_leaf_pkey`` and
``ledger_linear`` and loses. It lives in ``mainline_ops`` rather than ``mainline`` so that
"everything in the ledger schema is append-only" stays a sentence with no footnote.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg

__all__ = [
    "ACQUIRE_SQL",
    "DEFAULT_TTL_SECONDS",
    "MAX_CONTEND_ATTEMPTS",
    "OBSERVE_SQL",
    "RELEASE_SQL",
    "Lease",
    "LeaseRowMissing",
    "acquire",
    "contend",
    "observe",
    "release",
]

#: The lease outlives four EventBridge ticks. Long enough that a slow batch does not lose
#: its own lease mid-append; short enough that a hard crash costs at most one minute of
#: sequencing. It is a wall clock on one node and nothing evidentiary reads it.
DEFAULT_TTL_SECONDS = 60

#: MEASURED, 2026-08-04 against CockroachDB CCL v26.2.5: sixteen Lambdas contending for
#: one lease row on the same EventBridge tick produce ``40001
#: TransactionRetryWithProtoRefreshError: WriteTooOldError`` on the CAS, not merely a
#: zero-row result. That is the *undecided* class, not the "somebody else won" class, and
#: the two must not be conflated: a ``40001`` swallowed as a lost election would leave a
#: site unsequenced for a tick while every contender believed it had lost. See
#: :func:`contend`.
MAX_CONTEND_ATTEMPTS = 8

# Shorter than the appender's backoff, and deliberately so: this contention is one row
# and no signing round trip, so a contender that has not resolved in a few tens of
# milliseconds has lost to somebody who is already sequencing.
_BASE_DELAY_S = 0.005
_CAP_DELAY_S = 0.2

# `now()` in CockroachDB is the TRANSACTION timestamp, so every comparison inside one
# invocation is taken against a single instant rather than against a clock that moves
# between the observe and the swap.

OBSERVE_SQL = """
SELECT holder, epoch, expires_at, expires_at < now() AS expired
  FROM mainline_ops.sequencer_lease
 WHERE site_code = %s
"""

ACQUIRE_SQL = """
UPDATE mainline_ops.sequencer_lease
   SET holder = %s, epoch = %s, expires_at = now() + %s
 WHERE site_code = %s
   AND epoch = %s
   AND (holder = %s OR expires_at < now())
RETURNING holder, epoch, expires_at
"""

# Release does NOT bump the epoch. It expires the lease in place, so the next invocation
# observes the epoch this holder wrote and beats it by one. Bumping here would produce an
# epoch nobody ever held, which is harmless but makes the epoch a poor forensic record of
# how many elections a site has actually had.
RELEASE_SQL = """
UPDATE mainline_ops.sequencer_lease
   SET expires_at = now()
 WHERE site_code = %s
   AND epoch = %s
   AND holder = %s
"""


class LeaseRowMissing(LookupError):
    """No ``sequencer_lease`` row exists for the site.

    The row is created once per site by the provisioning path; there is no ``INSERT`` in
    the steady-state loop, on purpose. A sequencer that inserted its own lease on finding
    none would hand the same position to two writers exactly under the partition the
    lease exists to survive — it would work in testing and fail in the only case that
    mattered. A missing row is therefore a provisioning fault and is raised as one.
    """


@dataclass(frozen=True, slots=True)
class Lease:
    """A lease this process holds, or observed another process holding."""

    site_code: str
    holder: str
    epoch: int
    expires_at: datetime


def observe(conn: psycopg.Connection[Any], *, site_code: str) -> tuple[Lease, bool]:
    """Read the current lease row and whether it has expired.

    Returns:
        The lease as recorded, and ``True`` when the cluster's own ``now()`` is past its
        expiry. Expiry is decided by the *database's* clock, never by the caller's: a
        Lambda whose clock has drifted must not be able to declare somebody else's live
        lease dead.

    Raises:
        LeaseRowMissing: if the site has no lease row.
    """
    with conn.cursor() as cur:
        cur.execute(OBSERVE_SQL, (site_code,))
        row = cur.fetchone()
    if row is None:
        raise LeaseRowMissing(
            f"mainline_ops.sequencer_lease has no row for site_code={site_code!r}. The "
            "row is created once per site by the provisioning path and the sequencer "
            "deliberately does not insert one: a sequencer that bootstrapped its own "
            "lease would start at epoch 0 beside a live holder and hand the same "
            "position to two writers."
        )
    holder, epoch, expires_at, expired = row
    return (
        Lease(site_code=site_code, holder=str(holder), epoch=int(epoch), expires_at=expires_at),
        bool(expired),
    )


def acquire(
    conn: psycopg.Connection[Any],
    *,
    site_code: str,
    holder: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> Lease | None:
    """Take the lease for *site_code*, or return ``None`` because somebody else holds it.

    Args:
        conn: an open connection. The observe and the swap MUST run in the same
            transaction — under ``SERIALIZABLE`` that is what makes the pair atomic, and
            it is why this function does not open one itself: the caller's transaction is
            the unit of atomicity.
        site_code: the log partition being sequenced.
        holder: an opaque identity — the Lambda request id, or the container id. It is
            compared and never parsed.
        ttl_seconds: how long the lease is good for.

    Returns:
        The lease now held, or ``None`` when another holder has an unexpired lease. A
        ``None`` return is an ordinary outcome and MUST NOT be retried inside the same
        invocation.

    Raises:
        LeaseRowMissing: if the site has no lease row.
        ValueError: if *holder* is empty or *ttl_seconds* is not positive. Both are
            refused by ``CHECK`` constraints in migration 0079 anyway; refusing them here
            turns a ``23514`` from a foreign transaction into a local message that names
            the argument.
    """
    if not holder:
        raise ValueError(
            "holder must be a non-empty opaque identity; migration 0079's holder_stated "
            "CHECK refuses the empty string, and an anonymous lease holder cannot be "
            "distinguished from its own predecessor"
        )
    if ttl_seconds <= 0:
        raise ValueError(f"ttl_seconds must be positive, got {ttl_seconds}")

    current, _expired = observe(conn, site_code=site_code)
    with conn.cursor() as cur:
        cur.execute(
            ACQUIRE_SQL,
            (
                holder,
                current.epoch + 1,
                timedelta(seconds=ttl_seconds),
                site_code,
                current.epoch,
                holder,
            ),
        )
        row = cur.fetchone()
    if row is None:
        # Zero rows: either the epoch moved between the observe and the swap, or the
        # incumbent's lease is still live. Both mean "not the leader", and neither is
        # retried — see the module docstring.
        return None
    won_holder, won_epoch, won_expires = row
    return Lease(
        site_code=site_code,
        holder=str(won_holder),
        epoch=int(won_epoch),
        expires_at=won_expires,
    )


def contend(
    conn: psycopg.Connection[Any],
    *,
    site_code: str,
    holder: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    max_attempts: int = MAX_CONTEND_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> Lease | None:
    """Run the election in its own transaction, retrying ``40001`` and nothing else.

    Two outcomes look similar from the outside and are entirely different facts, which is
    why they are handled differently here:

    * **Zero rows updated** — somebody else holds it. DECIDED. Returned as ``None`` and
      never retried, because retrying it would be a second writer trying again.
    * **``40001``** — the transaction is UNDECIDED. Retried, bounded at
      :data:`MAX_CONTEND_ATTEMPTS`, because re-running it re-observes the epoch and
      therefore cannot elect a second holder. Swallowing it as a lost election would
      leave a site unsequenced for a tick while every contender believed it had lost.

    Everything else propagates on the first attempt. ``LeaseRowMissing`` in particular is
    a provisioning fault and retrying it would only make the fault take longer to report.

    Returns:
        The lease now held, or ``None`` when another holder has an unexpired one.

    Raises:
        psycopg.errors.SerializationFailure: if every attempt was undecided. The
            invocation stands down; the next EventBridge tick is 15 seconds away.
    """
    jitter = rng if rng is not None else random.SystemRandom()
    last: psycopg.errors.SerializationFailure | None = None
    for attempt in range(max_attempts):
        try:
            with conn.transaction():
                return acquire(conn, site_code=site_code, holder=holder, ttl_seconds=ttl_seconds)
        except psycopg.errors.SerializationFailure as exc:
            last = exc
            if attempt + 1 < max_attempts:
                ceiling = min(_CAP_DELAY_S, _BASE_DELAY_S * (2**attempt))
                sleep(jitter.uniform(0.0, ceiling))
    raise last  # type: ignore[misc]


def release(conn: psycopg.Connection[Any], lease: Lease) -> bool:
    """Expire *lease* immediately so the next invocation can take over without waiting.

    Releasing is an optimisation and never a correctness step: a lease that is simply
    left to expire costs at most ``ttl_seconds`` of sequencing latency, and a release
    that fails is not an error.

    Returns:
        ``True`` if this holder's lease was the one expired, ``False`` if the lease had
        already moved on — which is information the caller may log and must not treat as
        a failure.
    """
    with conn.cursor() as cur:
        cur.execute(RELEASE_SQL, (lease.site_code, lease.epoch, lease.holder))
        return cur.rowcount == 1
