# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Two token buckets at the door, and an honest account of what they do not bound.

WHY A RATE BOUND HAS TO LIVE **HERE**, IN PYTHON, AT THE TOP OF THE HANDLER
--------------------------------------------------------------------------
The demo is one Lambda **Function URL** with ``authorization_type = NONE`` — DECISION
**D1**, `docs/leads/ship-final.md` §1.4, because this AWS account is under a verification
hold that refuses new CloudFront distributions. That deployment shape removes every
rate-control mechanism AWS offers:

* **AWS WAF cannot attach to a Lambda Function URL.** WAF web ACLs associate with
  CloudFront, Application Load Balancers, API Gateway, AppSync and Cognito user pools. A
  Function URL is none of those, so its rate-based rules — the obvious place for this
  control — are simply not available. There is no CDN in front of this origin to put one
  on, which is the same fact that made the Function URL necessary in the first place.
* **The only knob on the URL itself is** ``authorization_type``, and the founder has ruled
  it out: judges click the link and it works, with no credential and no shared secret.
* **API Gateway throttling does not apply**, because there is no API Gateway.

So the first hop that can refuse anything is this module, and the request has already been
paid for by the time it gets here. That is not a defect in the design; it is the honest
consequence of the posture, and it is why :mod:`mainline_demo_api.ratelimit` is not the
whole cost control but only its cheapest layer.

THE TWO LAYERS, AND WHY NEITHER ALONE IS A CONTROL
--------------------------------------------------
**(a) The global bucket** bounds *this execution environment's* aggregate request rate. It
is the layer that bounds a **distributed** flood: a botnet with ten thousand source
addresses defeats any per-IP scheme by construction, and this one does not care how many
addresses the traffic arrives from. With the AWS account's concurrency ceiling of 10, the
fleet-wide bound is ``10 x MAINLINE_RATE_GLOBAL_RPS``. **What it does not bound is WHO is
refused** — once it is empty it refuses the next caller, judge or attacker alike, with no
way to tell them apart. On its own it converts a flood into an outage.

**(b) The per-IP bucket** bounds one caller, so a single noisy address cannot spend the
whole instance's budget and take the room's judges down with it. It is checked FIRST and
the global bucket is only consulted for a request the per-IP layer admitted, so an abusive
address burns its own tokens and not everybody's. **What it does not bound is a botnet**:
every fresh source address arrives with a full burst, so per-IP alone is defeated by
address rotation, which costs an attacker nothing.

Each layer is useless against the other's threat. That is why there are two, and it is
stated here so no reader has to derive it from the code.

WHAT NEITHER LAYER BOUNDS, AND THIS IS THE IMPORTANT PART
---------------------------------------------------------
**Lambda bills a 429 exactly like a 200.** The invocation happened, the execution
environment ran, and the request charge and the GB-second charge are indistinguishable
from a served response. This module therefore bounds:

* **egress bytes** — a refused request emits under 300 B instead of up to
  ``MAINLINE_MAX_RESPONSE_BYTES``, which is the largest term in a sustained-egress flood;
* **work** — a refused request touches no filesystem and opens no database connection, so
  the CockroachDB Basic cluster behind this demo (a separate bill, capped at USD 25) is
  never reached by traffic this module refuses.

and it bounds **neither the invocation count nor the request charge**. Worse, and said
plainly because it is counter-intuitive: at a fixed concurrency ceiling ``C`` the
invocation rate is ``C / duration``, and refusing early makes ``duration`` collapse, so
the number of *billed invocations* under a flood goes **up**, not down. Trading a
139 KB response for a 300 B one is worth doing and it is not a bill bound.

**The mechanism that bounds the bill is the cost-guard responder** — three alarms on three
timescales feeding one SNS topic feeding one Lambda that calls
``PutFunctionConcurrency(0)``. That is `docs/leads/cost-bound-plan.md` §0.2 and W5's
module, and it is the reason this one does not have to pretend to be more than it is.

CONFIGURATION (interface **I3**)
--------------------------------
====================================  =========================================
``MAINLINE_RATE_GLOBAL_RPS``          tokens per second, this instance, all callers
``MAINLINE_RATE_GLOBAL_BURST``        bucket capacity, this instance, all callers
``MAINLINE_RATE_IP_RPS``              tokens per second, per source address
``MAINLINE_RATE_IP_BURST``            bucket capacity, per source address
====================================  =========================================

Every one has a code default that is safe when Terraform publishes nothing, and every one
is parsed the way :func:`mainline_demo_api.static_site.max_response_bytes` parses its own:
**a value that does not parse falls back to the default and never to "unbounded".** That
includes the values that *do* parse and are still not rates — ``inf``, ``nan``, ``0``,
``-1``, and anything above :data:`MAX_RPS` / :data:`MAX_BURST`. A number that large is not
a rate limit, it is the absence of one, so it is refused for the same reason a typo is:
**there is no value of any environment variable that disarms this module.** Disarming it
is an in-process call (:func:`configure`), which a deploy cannot make and a measurement
harness can.

THE HOT PATH
------------
Both buckets are module-scope, so they live for the whole life of the execution
environment rather than for one invocation — a per-invocation bucket would be full on
every request and would bound nothing. Both are driven by :func:`time.monotonic`, never by
wall clock: an NTP step must not hand an attacker a free refill or strand a judge behind a
bucket that will not refill until the clock catches up.

The admitted path allocates nothing: two attribute reads, one subtraction, one comparison,
one ``OrderedDict`` lookup and one ``move_to_end``. The refused path builds two small dicts
around a **precomputed literal body** — no JSON encoding, no string formatting and nothing
caller-supplied — which is the discipline :func:`mainline_demo_api.static_site._too_large`
follows, and for the same reason: under a flood the refusal *is* the workload.

NO LOCK IS TAKEN. AWS gives one execution environment one event at a time, so there is no
concurrency to protect against in the deployment this exists for. Under a threaded local
harness the worst outcome is a token or two of drift, which is not a property anything
here asserts; the one operation that could raise under concurrent mutation — the reclaim
scan — is guarded.
"""

from __future__ import annotations

import logging
import math
import os
import time
from collections import OrderedDict
from collections.abc import Mapping
from typing import Any, Final, NamedTuple

from . import logbudget

__all__ = [
    "DEFAULT_GLOBAL_BURST",
    "DEFAULT_GLOBAL_RPS",
    "DEFAULT_IP_BURST",
    "DEFAULT_IP_RPS",
    "GLOBAL_BURST_ENV",
    "GLOBAL_RPS_ENV",
    "IP_BURST_ENV",
    "IP_KEY_LIMIT",
    "IP_RPS_ENV",
    "MAX_BURST",
    "MAX_KEYS",
    "MAX_RPS",
    "Settings",
    "check",
    "configure",
    "key_count",
    "refusals",
    "reset",
    "settings",
]

_log = logging.getLogger("mainline_demo_api")

# ── Interface I3: the four environment variables ────────────────────────────────────

GLOBAL_RPS_ENV: Final = "MAINLINE_RATE_GLOBAL_RPS"
GLOBAL_BURST_ENV: Final = "MAINLINE_RATE_GLOBAL_BURST"
IP_RPS_ENV: Final = "MAINLINE_RATE_IP_RPS"
IP_BURST_ENV: Final = "MAINLINE_RATE_IP_BURST"

#: Ten requests per second per execution environment, sustained. At the account's
#: concurrency ceiling of 10 that is a fleet bound of 100 rps. **Chosen from what the
#: demo must not refuse, not from a round number:** a judge loading the console fetches
#: ``index.html`` plus its hashed assets — under thirty requests — and then drives the
#: three-beat demo at roughly one request per second. Ten judges arriving at once is
#: comfortably inside ``10 x 10``; a flood is not.
DEFAULT_GLOBAL_RPS: Final = 10.0

#: One hundred requests may arrive instantly. This is the number that keeps the control
#: from breaking the demo: a page load is a *burst*, and a bucket sized to the sustained
#: rate would refuse the console's own assets on the first click. It is also the reason
#: a burst is a separate knob from a rate rather than derived from it.
DEFAULT_GLOBAL_BURST: Final = 100

#: Five per second from one address, and fifty at once. Half the global rate, so one
#: caller can never be more than half the instance's sustained budget, and a burst that
#: still swallows a whole page load in one go.
DEFAULT_IP_RPS: Final = 5.0
DEFAULT_IP_BURST: Final = 50

#: Above these, a value is not a rate limit; it is the absence of one, and it falls back
#: to the default exactly as a typo does. See the module docstring: nothing an environment
#: variable can say disarms this module.
MAX_RPS: Final = 10_000.0
MAX_BURST: Final = 100_000

#: How many source addresses may hold their own bucket at once. 1,024 buckets is about
#: 100 KB of resident memory — nothing at 256 MB — and it is a *hard* bound rather than a
#: hint: see :func:`_bucket_for`, which never grows past it.
MAX_KEYS: Final = 1024

#: How many entries the reclaim scan looks at before giving up. Keeps :func:`_bucket_for`
#: O(1)-amortised rather than O(MAX_KEYS) on the miss path an attacker controls.
_RECLAIM_SCAN: Final = 8

#: A source address is at most 45 characters (IPv6 with an embedded IPv4 literal), plus
#: room for a zone index. On a real Function URL AWS writes this field and a caller cannot,
#: but this handler is also driven by ``scripts/deploy/local_furl.py`` and by tests, and a
#: map key whose length a caller chooses is a memory amplifier however unlikely the path.
IP_KEY_LIMIT: Final = 64

#: The collapse key each layer's throttle line is logged under, and the counter's label.
_SCOPES: Final[tuple[str, str]] = ("ip", "global")

_NO_STORE: Final = "no-store"
_CONTENT_TYPE: Final = "application/json; charset=utf-8"

#: The refusal body, as a template with exactly four substitutions, all of them numbers or
#: literals this module owns. **Nothing caller-supplied appears in it** — not the path, not
#: the method, not the source address — so its length is fixed by construction and cannot
#: be chosen by the caller who provoked it. ``rps`` and ``burst`` are in the body for the
#: reason ``ceiling_bytes`` is in the 413: the enforced value comes from an environment
#: variable a deploy may set and a typo may mangle, so the refusal names what it actually
#: enforced rather than leaving the effective value to be inferred.
_BODY: Final = (
    '{{"error":{{"burst":{burst},"detail":"this instance is at its declared request '
    "rate; retry after the seconds in the retry-after header. Nothing about the request "
    'itself was refused.","kind":"rate_limited","rps":{rps},"scope":"{scope}",'
    '"status":429}}}}'
)

#: Every response this module can emit must stay under this, and ``test_ratelimit.py``
#: asserts it. The 429 is deliberately NOT measured against
#: ``static_site.max_response_bytes()``: a refusal that can itself be refused is not a
#: control, which is the same argument ``app._too_large`` makes about the 413.
REFUSAL_BODY_CEILING: Final = 300


class Settings(NamedTuple):
    """The four numbers actually in force, after parsing and fallback."""

    global_rps: float
    global_burst: int
    ip_rps: float
    ip_burst: int


# ── Parsing: a bad value falls back to the default, never to unbounded ──────────────


def _rate(name: str, default: float) -> float:
    """Parse a positive, finite rate from ``$name``. Never raises; never returns unbounded.

    ``float("inf")`` and ``float("nan")`` both *parse*, which is exactly why this cannot
    be a bare ``try: float(...)``. An infinite rate is a bucket that never empties, i.e. a
    limiter that is off, and an environment variable must not be able to say that.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        return default
    if not math.isfinite(value) or value <= 0.0 or value > MAX_RPS:
        return default
    return value


def _burst(name: str, default: int) -> int:
    """Parse a positive integer capacity from ``$name``. Never raises.

    ``int("1.5")`` raises rather than truncating, and that is the wanted behaviour: a
    fractional burst is a misunderstanding of the knob, and guessing which way to round it
    would be inventing an intent. It falls back, like every other value that is not a
    capacity.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    if value <= 0 or value > MAX_BURST:
        return default
    return value


# ── The bucket ──────────────────────────────────────────────────────────────────────


class _Bucket:
    """One token bucket. Mutated in place; never replaced, so the hot path allocates none.

    ``stamp`` starts at ``0.0`` rather than at a captured clock reading, which is not a
    bug: :func:`time.monotonic` is positive and monotonic, so the first :meth:`take` sees
    an enormous elapsed interval, refills, and clamps to ``capacity`` — which is where a
    fresh bucket starts anyway. One fewer branch on the path that runs every request.
    """

    __slots__ = ("capacity", "rate", "stamp", "tokens")

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.stamp = 0.0

    def refill(self, now: float) -> float:
        elapsed = now - self.stamp
        if elapsed > 0.0:
            self.stamp = now
            tokens = self.tokens + elapsed * self.rate
            self.tokens = tokens if tokens < self.capacity else self.capacity
        return self.tokens

    def take(self, now: float) -> bool:
        """Spend one token. ``True`` admits; ``False`` refuses and spends nothing."""
        tokens = self.refill(now)
        if tokens < 1.0:
            return False
        self.tokens = tokens - 1.0
        return True

    def replenished(self, now: float) -> bool:
        """Report whether this bucket is back at capacity, i.e. carries no debt.

        This is the whole reclaim rule. A bucket at capacity is *indistinguishable from a
        bucket that has never been used*, so discarding it loses nothing and a caller whose
        entry is discarded is treated exactly as a caller arriving for the first time. A
        bucket below capacity carries debt, and evicting it would hand its owner a free
        full burst — which is precisely the attack a per-IP limiter with a plain LRU
        invites, since rotating the source address would then cost the attacker nothing.
        """
        return self.refill(now) >= self.capacity

    def refill_window(self) -> float:
        """Seconds to refill from empty to full — the window throttle lines collapse over."""
        return self.capacity / self.rate

    def retry_after(self) -> int:
        """Whole seconds to advertise in ``retry-after``. Constant for a given rate.

        A refusal happens only when ``tokens < 1``, so the wait for one token is at most
        ``1 / rate`` seconds whatever the bucket's history. That makes the header a
        constant per configuration rather than a per-request computation, which is why the
        refusal can be a precomputed literal. RFC 9110 ``delay-seconds`` is a non-negative
        integer, so it is rounded up and floored at one: advertising ``0`` would invite an
        immediate retry that is certain to be refused again.
        """
        return max(1, math.ceil(1.0 / self.rate))


# ── Module-scope state: one process, one execution environment ──────────────────────

_GLOBAL = _Bucket(DEFAULT_GLOBAL_RPS, DEFAULT_GLOBAL_BURST)
_PER_IP: OrderedDict[str, _Bucket] = OrderedDict()
_IP_RATE = DEFAULT_IP_RPS
_IP_BURST = DEFAULT_IP_BURST

#: scope -> (body, retry-after header value). Rebuilt only by :func:`configure`.
_REFUSAL: dict[str, tuple[str, str]] = {}

#: scope -> how many requests this module has refused since import. Diagnostics only, and
#: the number the throttle line reports; two integers, so it cannot itself grow.
_REFUSALS: dict[str, int] = dict.fromkeys(_SCOPES, 0)


def _rebuild_refusals() -> None:
    _REFUSAL["global"] = (
        _BODY.format(burst=int(_GLOBAL.capacity), rps=_number(_GLOBAL.rate), scope="global"),
        str(_GLOBAL.retry_after()),
    )
    probe = _Bucket(_IP_RATE, _IP_BURST)
    _REFUSAL["ip"] = (
        _BODY.format(burst=_IP_BURST, rps=_number(_IP_RATE), scope="ip"),
        str(probe.retry_after()),
    )


def _number(value: float) -> str:
    """Render a rate as JSON without a trailing ``.0`` on a whole number."""
    return str(int(value)) if value.is_integer() else repr(value)


def configure(
    *,
    global_rps: float | None = None,
    global_burst: int | None = None,
    ip_rps: float | None = None,
    ip_burst: int | None = None,
) -> Settings:
    """Re-read interface **I3** from the environment and rebuild both buckets.

    Called once at import, and again by anything that needs a different configuration in
    the same process — a test, or ``scripts/deploy/measure_beats.py``, which drives this
    handler in a tight loop precisely to find out what one invocation costs and would
    otherwise measure this module refusing it.

    **Keyword overrides win over the environment.** That asymmetry is the point: there is
    no environment variable that disarms the limiter (see :func:`_rate`), so the only way
    to raise it past :data:`MAX_RPS` is an in-process call, which a deploy cannot make.

    A Lambda's environment is fixed for the life of an execution environment, so reading it
    once at import costs nothing in the deployment this exists for; the seam is here for
    the processes where that is not true.
    """
    global _IP_RATE, _IP_BURST  # noqa: PLW0603 - module-scope state IS the design; see
    # the module docstring. A bucket rebuilt per invocation is full on every request.

    resolved = Settings(
        global_rps=_rate(GLOBAL_RPS_ENV, DEFAULT_GLOBAL_RPS) if global_rps is None else global_rps,
        global_burst=_burst(GLOBAL_BURST_ENV, DEFAULT_GLOBAL_BURST)
        if global_burst is None
        else global_burst,
        ip_rps=_rate(IP_RPS_ENV, DEFAULT_IP_RPS) if ip_rps is None else ip_rps,
        ip_burst=_burst(IP_BURST_ENV, DEFAULT_IP_BURST) if ip_burst is None else ip_burst,
    )
    _GLOBAL.rate = resolved.global_rps
    _GLOBAL.capacity = float(resolved.global_burst)
    _GLOBAL.tokens = float(resolved.global_burst)
    _GLOBAL.stamp = 0.0
    _IP_RATE = resolved.ip_rps
    _IP_BURST = resolved.ip_burst
    _PER_IP.clear()
    _rebuild_refusals()
    return resolved


def settings() -> Settings:
    """Return the four numbers in force. Read from the buckets, not from the environment."""
    return Settings(
        global_rps=_GLOBAL.rate,
        global_burst=int(_GLOBAL.capacity),
        ip_rps=_IP_RATE,
        ip_burst=_IP_BURST,
    )


def reset() -> None:
    """Refill both layers and forget every source address. Configuration is unchanged.

    The seam a measurement harness needs between iterations, and the seam a test needs
    between cases. It is deliberately NOT reachable from the environment or from a
    request: nothing in :func:`check` calls it.
    """
    _GLOBAL.tokens = _GLOBAL.capacity
    _GLOBAL.stamp = 0.0
    _PER_IP.clear()
    for scope in _SCOPES:
        _REFUSALS[scope] = 0


def key_count() -> int:
    """How many source addresses currently hold a bucket. Never exceeds :data:`MAX_KEYS`."""
    return len(_PER_IP)


def refusals() -> dict[str, int]:
    """Return a copy of the per-scope refusal counters. Diagnostics; nothing routes on it."""
    return dict(_REFUSALS)


# ── The check ───────────────────────────────────────────────────────────────────────


def _source_ip(event: Mapping[str, Any]) -> str | None:
    """``requestContext.http.sourceIp``, clipped, or ``None`` when the event carries none.

    A missing address is not an error and is not a refusal: payload format 2.0 always
    carries one on a real Function URL, and an event that does not is a test or a local
    harness. Such a request still meets the global bucket, which is the layer that bounds
    the instance regardless of who is asking.
    """
    context = event.get("requestContext")
    if isinstance(context, Mapping):
        http = context.get("http")
        if isinstance(http, Mapping):
            address = http.get("sourceIp")
            if isinstance(address, str) and address:
                return address[:IP_KEY_LIMIT]
    return None


def _bucket_for(key: str, now: float) -> _Bucket | None:
    """Return *key*'s bucket, or ``None`` when the map is full and nothing is reclaimable.

    ``None`` means **fall back to the global bucket**, not **admit**. That distinction is
    the whole security content of this function: an attacker rotating source addresses
    would otherwise get an unlimited supply of fresh full buckets, and the per-IP layer
    would cost them nothing to defeat *and* would grow this map without bound while they
    did it.

    Reclaim is by least-recently-used order, but only from entries whose bucket is back at
    capacity — see :meth:`_Bucket.replenished`. Evicting a drained bucket is the free-reset
    bug; evicting a full one is lossless. The scan is bounded at :data:`_RECLAIM_SCAN`
    entries so the miss path an attacker controls stays cheap, and the reclaimed
    ``_Bucket`` object is reused rather than reallocated.
    """
    bucket = _PER_IP.get(key)
    if bucket is not None:
        _PER_IP.move_to_end(key)
        return bucket

    if len(_PER_IP) < MAX_KEYS:
        fresh = _Bucket(_IP_RATE, _IP_BURST)
        _PER_IP[key] = fresh
        return fresh

    victim: str | None = None
    try:
        for index, (candidate, held) in enumerate(_PER_IP.items()):
            if index >= _RECLAIM_SCAN:
                break
            if held.replenished(now):
                victim = candidate
                break
    except RuntimeError:  # pragma: no cover - only reachable under a threaded harness
        return None
    if victim is None:
        return None

    recycled = _PER_IP.pop(victim)
    recycled.rate = _IP_RATE
    recycled.capacity = float(_IP_BURST)
    recycled.tokens = float(_IP_BURST)
    recycled.stamp = now
    _PER_IP[key] = recycled
    return recycled


def _refuse(scope: str, address: str | None, window: float) -> dict[str, Any]:
    """Build the 429: a precomputed literal body, two small dicts, nothing caller-supplied.

    The throttle line is gated by :func:`mainline_demo_api.logbudget.claim` **before** the
    record exists, not filtered after it: under a flood this is the hottest path in the
    function, and a log record built once per refused request is a second bill that never
    appears in the egress arithmetic. One line per bucket refill window is enough to tell
    an operator the limiter is engaged; the count in that line carries the rest.
    """
    count = _REFUSALS[scope] + 1
    _REFUSALS[scope] = count
    if logbudget.claim(f"ratelimit.{scope}", window):
        _log.warning(
            "rate limit engaged: scope=%s refusals=%d source=%s",
            scope,
            count,
            logbudget.clip(address, 45) if address else "-",
        )
    body, retry_after = _REFUSAL[scope]
    return {
        "statusCode": 429,
        "headers": {
            "content-type": _CONTENT_TYPE,
            "cache-control": _NO_STORE,
            "retry-after": retry_after,
            "x-mainline-api": "demo-rate",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def check(event: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Admit or refuse one invocation. ``None`` admits; a finished 429 response refuses.

    Called from the very top of :func:`mainline_demo_api.app.handler`, before the OPTIONS
    branch and before the ``/v1`` fork, so a refused request never resolves a path, never
    reads the filesystem and never asks :mod:`mainline_demo_api.db` for a connection.

    **Per-IP is checked first and the global bucket is only consulted for a request the
    per-IP layer admitted.** The other order would let one address empty the shared bucket
    on requests that were going to be refused anyway, which is a denial of service handed
    to the attacker by the control meant to stop them.
    """
    now = time.monotonic()
    event = event or {}

    address = _source_ip(event)
    if address is not None:
        bucket = _bucket_for(address, now)
        if bucket is not None and not bucket.take(now):
            return _refuse("ip", address, bucket.refill_window())

    if not _GLOBAL.take(now):
        return _refuse("global", address, _GLOBAL.refill_window())
    return None


configure()
