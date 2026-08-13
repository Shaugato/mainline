# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Interface **I5** — a ceiling on the log bytes one invocation may emit, and a collapse.

WHY A LOG BUDGET IS A COST CONTROL AND NOT HOUSEKEEPING
-------------------------------------------------------
`docs/leads/cost-bound-plan.md` §0.4: **a CloudWatch log group has retention, not a
quota.** ``log_retention_days = 7`` bounds how long bytes are *stored* and bounds
*ingestion* not at all, and ingestion is the charged term — roughly USD 0.50 to 0.63 per
GB depending on region, billed on arrival, with the 7-day retention deleting bytes that have
already been paid for.

Under a flood the refusal path is the hottest path in this function. A single 120-byte log
line on it, at the invocation rates a fixed concurrency ceiling produces when every
invocation is cheap, is tens of megabytes a second of ingestion — **a second bill, and an
invisible one**, because every dollar of it is spent inside a control that exists to save
money. That is the defect this module exists to make impossible, and it is why the bound
is *bytes per invocation* rather than *lines per invocation*: a line's length is not a
constant, and the two log records this handler can emit with an exception attached carry a
formatted traceback whose length nobody declared.

There are exactly two mechanisms and they are not the same mechanism:

**(1) The collapse —** :func:`claim`. A *pre-record* gate for a named call site: it is
asked BEFORE a :class:`logging.LogRecord` exists, so a suppressed line costs one dict
lookup and one subtraction rather than a record, a format and a filter. This is what
:mod:`mainline_demo_api.ratelimit` uses to emit at most one throttle line per bucket
refill window.

**(2) The ceiling —** the :class:`logging.Filter` installed by :func:`install`. This is the
*hard* bound and it is at the exit, where every record on the ``mainline_demo_api`` logger
has to pass whether or not its author remembered this module existed. It is the same
discipline ``static_site._within_ceiling`` applies to response bytes, and for the same
reason: a control present on the paths somebody thought of and absent from the rest is not
a control.

**The collapse degrades to the ceiling, never to nothing.** :func:`claim` holds a bounded
map of call-site keys; when that map is full it stops collapsing and answers ``True``,
because the byte ceiling is the guarantee and the collapse is only the cheap way to stay
well inside it. Failing the other way — refusing to log because a map was full — would
make an unrelated flood silence a real error.

WHAT THIS DOES NOT BOUND, STATED SO NOBODY LOOKS FOR IT LATER
--------------------------------------------------------------
* **The Lambda platform's own lines.** ``START``, ``END``, ``REPORT``, ``INIT_START`` and
  the runtime's error frames are written by the runtime, not by this logger, and no filter
  in this process can see them. They are bounded only by ``system_log_level`` in the
  function's logging configuration, which is W6's surface.
* **Anything logged through a different logger.** A :class:`logging.Filter` attached to a
  logger sees the records that logger creates; a child logger's records reach the parent's
  *handlers* without passing the parent's *filters*. Every module in this package logs
  through ``logging.getLogger("mainline_demo_api")`` for exactly that reason, and
  :func:`install` accepts a logger so a future child can be covered explicitly rather than
  silently missed.
* **The invocation charge.** Same as everywhere else in this wave: bytes are bounded here,
  invocations are bounded by the cost-guard responder.

CONFIGURATION
-------------
====================================  ===========================================
``MAINLINE_LOG_BUDGET_BYTES``         bytes this handler may emit per invocation
``MAINLINE_LOG_COLLAPSE_SECONDS``     default window for :func:`claim`
====================================  ===========================================

Both parse the way every other number on this surface parses — see
:func:`mainline_demo_api.static_site.max_response_bytes`: **a malformed value falls back to
the safe default and never to unbounded.** Neither is required; both defaults are chosen to
be generous for a working handler and ruinous for none.
"""

from __future__ import annotations

import logging
import math
import os
import time
import traceback
from typing import Final

__all__ = [
    "BUDGET_BYTES_ENV",
    "COLLAPSE_SECONDS_ENV",
    "DEFAULT_BUDGET_BYTES",
    "DEFAULT_CLIP_LIMIT",
    "DEFAULT_COLLAPSE_SECONDS",
    "MAX_BUDGET_BYTES",
    "MESSAGE_LIMIT",
    "OVERRUN_BOUND",
    "TRUNCATION_MARKER",
    "begin",
    "claim",
    "clip",
    "collapsed",
    "dropped",
    "install",
    "reset",
    "used",
]

_LOGGER_NAME: Final = "mainline_demo_api"

BUDGET_BYTES_ENV: Final = "MAINLINE_LOG_BUDGET_BYTES"
COLLAPSE_SECONDS_ENV: Final = "MAINLINE_LOG_COLLAPSE_SECONDS"

#: 4 KiB per invocation. A handler answering normally emits nothing at all; the two call
#: sites that can emit anything are a database failure and an unhandled exception, and a
#: six-frame traceback is under 1 KiB. 4 KiB therefore never truncates a real diagnostic
#: and still bounds a pathological one, which is the shape a ceiling should have.
DEFAULT_BUDGET_BYTES: Final = 4096

#: Above this a "budget" is not a budget. Same rule as ``ratelimit.MAX_RPS``: an
#: environment variable may lower this control or leave it alone; it may not remove it.
MAX_BUDGET_BYTES: Final = 1_048_576

#: Ten seconds between identical throttle lines when no caller names a window. Chosen to
#: match the default refill window of both ``ratelimit`` buckets (capacity / rate = 10 s),
#: so the default here and the default there agree without either importing the other.
DEFAULT_COLLAPSE_SECONDS: Final = 10.0

#: The longest a single log record's message may be before the ceiling clips it. Long
#: enough for a SQLSTATE, a resource key and a driver's first line; short enough that one
#: record cannot consume the whole invocation's budget on its own.
MESSAGE_LIMIT: Final = 512

#: What :func:`clip` truncates to when a caller does not say. 200 matches
#: ``static_site._ECHO_LIMIT``, which bounds the same class of thing — a caller-derived
#: string on its way into an artefact whose length must not be the caller's to choose.
DEFAULT_CLIP_LIMIT: Final = 200

#: How many distinct call sites :func:`claim` will track. Two are in use today
#: (``ratelimit.ip`` and ``ratelimit.global``); the headroom is for call sites that do not
#: exist yet, and the bound is for the case where one of them keys on something a caller
#: influences.
MAX_CLAIM_KEYS: Final = 64

#: Appended to a traceback the ceiling had to cut. It is emitted even when there is no
#: room left for it, which is the one place this control may overrun its own number — see
#: :data:`OVERRUN_BOUND`. Saying "a diagnostic was cut here" is worth 46 bytes; leaving a
#: reader to wonder whether the stack simply ended is not.
TRUNCATION_MARKER: Final = "\n… [truncated by the per-invocation log budget]"

#: The one record this module writes itself, and it is a literal so its length is known
#: before it is emitted. It replaces the record that first exceeded the ceiling rather
#: than being logged separately, because logging from inside a filter re-enters the filter.
_NOTICE: Final = (
    "log budget exhausted: this invocation has emitted its %d-byte allowance and further "
    "records from it are dropped. Raise $%s if a diagnostic is being lost; the bound "
    "exists because CloudWatch bills ingestion and a log group has retention, not a quota."
)


#: **The ceiling is enforced at admission, so it can be overrun once, by this much.**
#:
#: A record is admitted while ``used < limit`` and then charged for what it costs, so the
#: last admitted record can carry the budget past its number: at most one clipped message,
#: plus a truncation marker for **each** of the two long attachments a record can carry
#: when neither had room for even the marker, plus the one-off exhaustion notice. Stated as
#: a computed number rather than as "roughly", and asserted in ``test_logbudget.py``,
#: because a bound nobody can evaluate is a hope.
#:
#: Making it exact instead would mean refusing the record that hits the line — i.e. losing
#: the diagnostic that was being written *at the moment the handler got into trouble*,
#: which is the one record most worth keeping. Under a kilobyte of slack is not a bill.
#:
#: **The marker term is counted twice as of 2026-08-13**, and the reason is a measurement
#: rather than a precaution: ``scripts/deploy/measure_log_bytes.py`` drove eight
#: ``stack_info=True`` records through this filter at the 4,096-byte default and observed
#: **9,776 bytes reach a handler while the budget charged 224** — a 44x under-count, because
#: ``record.stack_info`` was neither measured nor truncated here and every downstream
#: :class:`logging.Formatter` appends it. Truncating it costs one more marker in the worst
#: case, so the bound that describes this filter grew by exactly one marker. A bound left
#: at its old value while the filter gained a second truncatable field would have been a
#: false statement, which is worse than 46 bytes.
OVERRUN_BOUND: Final = (
    MESSAGE_LIMIT
    + 64  # `clip`'s "… (N characters, clipped)" suffix, generously
    + 2 * len(TRUNCATION_MARKER)  # one for `exc_text`, one for `stack_info`
    + len(_NOTICE % (MAX_BUDGET_BYTES, BUDGET_BYTES_ENV))
)


def _budget_bytes() -> int:
    """Return the per-invocation ceiling in force. Never raises; never unbounded."""
    raw = os.environ.get(BUDGET_BYTES_ENV)
    if raw is None:
        return DEFAULT_BUDGET_BYTES
    try:
        value = int(raw.strip())
    except ValueError:
        return DEFAULT_BUDGET_BYTES
    if value <= 0 or value > MAX_BUDGET_BYTES:
        return DEFAULT_BUDGET_BYTES
    return value


def _collapse_seconds() -> float:
    """Return the collapse window in force. Never raises; ``inf`` and ``nan`` fall back."""
    raw = os.environ.get(COLLAPSE_SECONDS_ENV)
    if raw is None:
        return DEFAULT_COLLAPSE_SECONDS
    try:
        value = float(raw.strip())
    except ValueError:
        return DEFAULT_COLLAPSE_SECONDS
    if not math.isfinite(value) or value <= 0.0:
        return DEFAULT_COLLAPSE_SECONDS
    return value


# ── (1) The collapse ────────────────────────────────────────────────────────────────

#: call-site key -> monotonic reading of the last line admitted for it.
_CLAIMS: dict[str, float] = {}
_COLLAPSED = [0]


def claim(key: str, window: float | None = None) -> bool:
    """Report whether *key* may emit a line now. Asked **before** a record is built.

    *window* defaults to ``$MAINLINE_LOG_COLLAPSE_SECONDS``. A caller that knows its own
    natural period — ``ratelimit`` passes its bucket's refill window — should pass it, so
    the collapse is one line per period rather than one line per arbitrary constant.

    Returns ``True`` when the map is full and *key* is not in it. That is the safe
    direction: the byte ceiling below is the guarantee, and a full collapse map must not
    be able to silence a call site that has never spoken.
    """
    now = time.monotonic()
    period = _collapse_seconds() if window is None else window
    last = _CLAIMS.get(key)
    if last is not None:
        if now - last < period:
            _COLLAPSED[0] += 1
            return False
        _CLAIMS[key] = now
        return True
    if len(_CLAIMS) >= MAX_CLAIM_KEYS:
        return True
    _CLAIMS[key] = now
    return True


def collapsed() -> int:
    """How many lines :func:`claim` has suppressed since import. Diagnostics only."""
    return _COLLAPSED[0]


def clip(value: object, limit: int = DEFAULT_CLIP_LIMIT) -> str:
    """Truncate a caller-derived value before it can reach a log record.

    The suffix names the original length, so a reader can tell a clipped value from a
    short one and can tell *how much* was clipped — which is the difference between
    "this field is empty" and "this field is a megabyte".
    """
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… ({len(text)} characters, clipped)"


# ── (2) The ceiling ─────────────────────────────────────────────────────────────────


class _Ceiling(logging.Filter):
    """The per-invocation byte cap, applied at the exit to every record on one logger.

    A :class:`logging.Filter` is used rather than a wrapper around each call site for the
    reason stated in the module docstring: the call sites are not the enumerable set. A
    filter that returns ``False`` stops the record before any handler formats it, so a
    dropped record costs nothing downstream.

    **The exceeding record is rewritten, not merely dropped.** A budget that silently
    swallowed the record that hit it would leave a reader unable to distinguish "nothing
    went wrong" from "the diagnostic was eaten by a cost control". Rewriting in place is
    also the only re-entrancy-safe way to say so: calling ``_log.warning`` from inside a
    filter would run this filter again.
    """

    def __init__(self) -> None:
        super().__init__()
        self._limit = DEFAULT_BUDGET_BYTES
        self._used = 0
        self._dropped = 0
        self._exhausted = False

    def begin(self) -> None:
        self._limit = _budget_bytes()
        self._used = 0
        self._dropped = 0
        self._exhausted = False

    def spent(self) -> int:
        return self._used

    def refused(self) -> int:
        return self._dropped

    def filter(self, record: logging.LogRecord) -> bool:
        if self._used >= self._limit:
            self._dropped += 1
            if self._exhausted:
                return False
            self._exhausted = True
            notice = _NOTICE % (self._limit, BUDGET_BYTES_ENV)
            record.msg = notice
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
            self._used += len(notice.encode("utf-8", "replace"))
            return True

        message, unformattable = _message(record)
        if unformattable or len(message) > MESSAGE_LIMIT:
            message = clip(message, MESSAGE_LIMIT)
            # Neutralised, not merely measured. A record whose template and arguments do
            # not agree raises again in every downstream `Formatter`, and the standard
            # handler answers that by printing the traceback to stderr — which on Lambda is
            # CloudWatch, unbudgeted, once per handler. Rewriting `msg` and emptying `args`
            # makes the record formattable by construction, so the bound holds through a
            # call site's typo instead of being defeated by one.
            record.msg = message
            record.args = ()
        spent = len(message.encode("utf-8", "replace"))

        # `exc_text` is what `logging.Formatter` emits for an exception, and it caches:
        # formatting it here means the traceback is measurable BEFORE a handler sees it,
        # and the handler then reuses this string rather than formatting it twice.
        if record.exc_info is not None and record.exc_text is None:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info))
        if record.exc_text:
            record.exc_text, charged = self._fit(record.exc_text, spent)
            spent += charged

        # `stack_info` is the SECOND thing `logging.Formatter.format` appends, and until
        # 2026-08-13 this filter neither measured nor truncated it. That was not a
        # theoretical hole. `scripts/deploy/measure_log_bytes.py` drove eight
        # `log.warning(..., stack_info=True)` records at the 4,096-byte default and
        # measured 9,776 bytes reaching a handler against a charge of 224 — the budget
        # was 44x under, and the records were not even dropped, because `stack_info` never
        # entered `spent` and so never moved `_used` towards the limit.
        #
        # It is a separate attribute from `exc_info` and arrives by a separate route: any
        # call site may pass `stack_info=True`, and `logging.Logger.error`/`.exception`
        # accept it too, so the set of call sites that can produce one is the same
        # unenumerable set this filter exists for. Charged and truncated exactly as
        # `exc_text` is, by the same helper, so the two cannot drift apart.
        if record.stack_info:
            record.stack_info, charged = self._fit(record.stack_info, spent)
            spent += charged

        self._used += spent
        return True

    def _fit(self, attachment: str, spent: int) -> tuple[str, int]:
        """Truncate *attachment* to the room left after *spent*, and report what it costs.

        The room is computed against ``self._used + spent`` rather than against
        ``self._used`` alone, so a record carrying both a traceback and a stack does not get
        to spend the same remaining bytes twice — which is precisely the arithmetic error a
        second copy of this block would have introduced.
        """
        room = self._limit - self._used - spent
        encoded = attachment.encode("utf-8", "replace")
        if len(encoded) > room:
            keep = max(0, room - len(TRUNCATION_MARKER))
            attachment = attachment[:keep] + TRUNCATION_MARKER
            encoded = attachment.encode("utf-8", "replace")
        return attachment, len(encoded)


def _message(record: logging.LogRecord) -> tuple[str, bool]:
    """``(text, unformattable)`` — a bad format string must not break the budget.

    ``getMessage`` applies ``%`` formatting and raises when the arguments do not match the
    template. That is a real bug in a call site, and it belongs in the log — as the
    unformatted template, with a note saying so — rather than as an exception raised from
    inside a filter, which would turn a mistyped log line into a failed invocation.

    The second element tells :meth:`_Ceiling.filter` to rewrite the record rather than
    merely charge for it; see the comment there for why measuring is not enough.
    """
    try:
        return record.getMessage(), False
    except (TypeError, ValueError):
        count = len(record.args) if isinstance(record.args, tuple) else 1
        return f"{record.msg!s}  [unformattable log call: {count} argument(s)]", True


_CEILING = _Ceiling()
_INSTALLED: set[str] = set()


def install(logger: logging.Logger | None = None) -> None:
    """Attach the ceiling to *logger* (default ``mainline_demo_api``). Idempotent.

    Called at import of :mod:`mainline_demo_api.app`, so the bound is in force for every
    invocation including the first — a control installed on the first *request* would
    leave cold-start logging unbounded, and a cold start is exactly when a handler logs.
    """
    target = logging.getLogger(_LOGGER_NAME) if logger is None else logger
    if target.name in _INSTALLED:
        return
    target.addFilter(_CEILING)
    _INSTALLED.add(target.name)


def begin() -> None:
    """Start a new invocation's allowance. Called at the top of ``app.handler``.

    Re-reads ``$MAINLINE_LOG_BUDGET_BYTES`` each time for the same reason
    ``static_site.max_response_bytes`` does: it costs one dict lookup and it makes the
    module testable without reloading it.
    """
    _CEILING.begin()


def used() -> int:
    """Bytes charged against the current invocation's allowance."""
    return _CEILING.spent()


def dropped() -> int:
    """Report how many records the ceiling refused during the current invocation."""
    return _CEILING.refused()


def reset() -> None:
    """Forget every collapse key and start a fresh allowance. A test seam, nothing else."""
    _CLAIMS.clear()
    _COLLAPSED[0] = 0
    _CEILING.begin()
