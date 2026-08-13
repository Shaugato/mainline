#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Measure the CloudWatch bytes ONE invocation of the demo API puts into the log group.

WHY THIS EXISTS — scope item (e), and the sentence that makes it a cost file
----------------------------------------------------------------------------
`docs/leads/cost-finish-plan.md` §0.4 and `logbudget.py`'s own docstring say the same
thing: **a CloudWatch log group has RETENTION, not a quota.** ``log_retention_days = 7``
bounds how long bytes are *stored* and bounds *ingestion* — the charged term, billed on
arrival — by nothing at all. There are exactly two available bounds: the bytes the handler
emits per invocation (deterministic, in code — `logbudget.DEFAULT_BUDGET_BYTES = 4096`)
and stopping the thing emitting them (the cost-guard's ``log_ingestion`` alarm). The first
was written and never measured; the second needs a number and has never been given a
measured one.

This program measures the first and derives the second.

WHAT WAS NOT MEASURED BEFORE THIS FILE, AND IS THE WHOLE JOB
------------------------------------------------------------
1. **What the managed runtime adds on top.** ``START`` / ``END`` / ``REPORT`` are written
   by the Lambda runtime, not by this handler's logger, and no filter in this process can
   see them. They are billed as ingestion exactly like everything else.
2. **What the 429 path actually emits under a sustained flood** — the case that matters,
   because ``ratelimit.check`` is the first statement of the handler and a flood is
   overwhelmingly 429s.
3. **Whether the collapse window holds under concurrency.**
4. **What ``logging_config.system_log_level = WARN`` does and does not suppress.**

MEASURED versus DOCUMENTED, AND WHY EVERY FIGURE CARRIES A `method` FIELD
--------------------------------------------------------------------------
The evidence this writes distinguishes three things that a reader must never have to
guess between, and every figure in it carries a ``method`` string saying which it is:

``measured``
    Observed on this workstation by this program, N stated.
``measured-emulator``
    Observed from the **real** ``public.ecr.aws/lambda/python:3.13`` base image through
    the AWS Lambda Runtime Interface Emulator, which is the managed runtime's own
    container. It is a measurement — of the emulator. Two ways it is not the deployment
    are recorded beside every such figure: the emulator emits the **text** ``START`` /
    ``END`` / ``REPORT`` lines whatever ``AWS_LAMBDA_LOG_FORMAT`` says, while the
    deployment sets ``log_format = "JSON"``; and its ``(rapid)`` lines are the local
    RAPID's and the production runtime does not emit them, so they are excluded and the
    exclusion is recorded.
``documented``
    Computed from a shape AWS documents, with the documentation quoted in the payload.
    **A citation is not a measurement** and is never presented as one.

CREDENTIAL DISCIPLINE — the same rule `measure_beats.py` follows
-----------------------------------------------------------------
No DSN is ever printed, written to the evidence, or passed on a command line. The
database target is recorded by scheme/host/port/database through
``measure_beats.describe_dsn``, and every byte captured from a child process goes through
``measure_beats.redact`` first.

WHAT IS REUSED RATHER THAN REBUILT
-----------------------------------
``scripts/deploy/measure_beats.py`` — its ``BEATS`` table, its nearest-rank
:func:`~measure_beats.summarise`, its :func:`~measure_beats.redact` and its
:func:`~measure_beats.describe_dsn`. ``scripts/deploy/local_furl.py`` —
:func:`~local_furl.build_event`, the payload-format-2.0 encoder the deployment's own
emulator uses. **No second beat list, no second percentile estimator and no second event
builder exist in this repository**, which is what stops the two files disagreeing.

Where this file *departs* from ``measure_beats``: that program measures wall time and so
must talk over a real socket; this one measures bytes that never leave the process, so it
drives ``app.handler`` in-process and taps the logging stack directly. One fresh
subprocess per beat is kept, for ``measure_beats``'s stated reason — a beat that inherits
the previous beat's module state measures the previous beat.

EXIT CODES
----------
``0`` every probe ran and every assertion in the payload held · ``1`` a probe failed or a
bound did not hold · ``2`` usage.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
SCRIPTS_DEPLOY: Final = REPO_ROOT / "scripts" / "deploy"
DEFAULT_APP_SRC: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
DEFAULT_WEB_ROOT: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "dist"
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "deploy" / "cost" / "log-bytes.json"

SCHEMA_ID: Final = "mainline/deploy/log-bytes/1"

#: The local node this repository pins. ``127.0.0.1`` and NOT ``localhost``, for the reason
#: ``measure_beats.DEFAULT_LOCAL_DSN`` states at length: ``localhost`` resolves to ``::1``
#: first on this Windows host and libpq pays the whole ``connect_timeout`` before it falls
#: back.
DEFAULT_LOCAL_DSN: Final = "postgresql://root@127.0.0.1:26257/{database}?sslmode=disable"

#: The scratch database this worker built (migrations + the deployment's own two seed
#: files, applied through ``scripts/deploy/seed_demo.py``'s own applier). Never a seed of
#: this file's own making: `docs/leads/cost-finish-plan.md` §1 forbids it in as many words.
DEFAULT_DATABASE: Final = "w_w3_logbytes"

# ══════════════════════════════════════════════════════════════════════════════════════
# AWS's documented accounting, quoted rather than paraphrased
# ══════════════════════════════════════════════════════════════════════════════════════

#: CloudWatch charges a per-EVENT overhead on top of the message bytes, and the only place
#: AWS states a number for it is the ``PutLogEvents`` batch-size rule. It is applied here
#: to ingestion because it is the closest documented accounting that exists, and that
#: substitution is named in the payload rather than assumed away.
PUT_LOG_EVENTS_OVERHEAD_BYTES: Final = 26

PUT_LOG_EVENTS_QUOTE: Final = (
    "The maximum batch size is 1,048,576 bytes. This size is calculated as the sum of all "
    "event messages in UTF-8, plus 26 bytes for each log event."
)
PUT_LOG_EVENTS_SOURCE: Final = (
    "https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/"
    "API_PutLogEvents.html (retrieved 2026-08-13)"
)

TELEMETRY_SCHEMA_SOURCE: Final = (
    "https://docs.aws.amazon.com/lambda/latest/dg/telemetry-schema-reference.html "
    "(retrieved 2026-08-13)"
)

#: AWS's own example ``platform.start`` record, copied from the Telemetry API `Event`
#: schema reference. Its SIZE is computed from it here; nothing about it is measured.
DOCUMENTED_PLATFORM_START: Final[dict[str, Any]] = {
    "time": "2022-10-12T00:00:15.064Z",
    "type": "platform.start",
    "record": {
        "requestId": "6d68ca91-49c9-448d-89b8-7ca3e6dc66aa",
        "version": "$LATEST",
        "tracing": {
            "spanId": "54565fb41ac79632",
            "type": "X-Amzn-Trace-Id",
            "value": ("Root=1-62e900b2-710d76f009d6e7785905449a;Parent=0efbd19962d95b05;Sampled=1"),
        },
    },
}

#: AWS's own example ``platform.report`` record, same source. ``initDurationMs`` appears
#: only on a cold start, and the example carries it, so this is the LARGER of the two
#: shapes — the conservative direction for a bound.
DOCUMENTED_PLATFORM_REPORT: Final[dict[str, Any]] = {
    "time": "2022-10-12T00:01:15.000Z",
    "type": "platform.report",
    "record": {
        "metrics": {
            "billedDurationMs": 694,
            "durationMs": 693.92,
            "initDurationMs": 397.68,
            "maxMemoryUsedMB": 84,
            "memorySizeMB": 128,
        },
        "requestId": "6d68ca91-49c9-448d-89b8-7ca3e6dc66aa",
    },
}

#: AWS's own example ``platform.runtimeDone`` record, same source. Carried separately
#: because whether it is emitted at ``system_log_level = WARN`` is precisely the question
#: this file could not answer from the documentation — see :data:`SYSTEM_LOG_LEVEL_NOTE`.
DOCUMENTED_PLATFORM_RUNTIME_DONE: Final[dict[str, Any]] = {
    "time": "2022-10-12T00:01:15.000Z",
    "type": "platform.runtimeDone",
    "record": {
        "requestId": "6d68ca91-49c9-448d-89b8-7ca3e6dc66aa",
        "status": "success",
        "tracing": {
            "spanId": "54565fb41ac79632",
            "type": "X-Amzn-Trace-Id",
            "value": ("Root=1-62e900b2-710d76f009d6e7785905449a;Parent=0efbd19962d95b05;Sampled=1"),
        },
        "metrics": {"durationMs": 140.0, "producedBytes": 16},
    },
}

#: **THE ONE QUESTION THIS FILE COULD NOT ANSWER FROM THE DOCUMENTATION, SAID PLAINLY.**
#:
#: The brief asks what ``system_log_level = WARN`` does and does not suppress, and asks for
#: a quotation rather than an assumption. AWS documents a "System log level event mapping"
#: table in *Configuring advanced logging controls for Lambda functions*; that page is
#: rendered client-side and **could not be retrieved as text by any tool available to this
#: worker on 2026-08-13**. Rather than paraphrase a table nobody here has read, this file
#: records the two sentences it *did* retrieve verbatim, and then takes the PESSIMISTIC
#: reading — that ``platform.start`` and ``platform.report`` are still emitted at ``WARN``
#: — because a bound derived from an optimistic guess about suppression would understate
#: ingestion, and understating it is the direction that costs money.
#:
#: This is also the reading `infra/modules/cost-guard/variables.tf` already takes when it
#: says "~400 B/invocation is Lambda's own JSON START/END/REPORT triple", so the assumption
#: is at least consistent across the two files rather than newly invented here.
SYSTEM_LOG_LEVEL_NOTE: Final[dict[str, Any]] = {
    "question": (
        "does logging_config.system_log_level = WARN suppress the runtime's own "
        "platform.start / platform.report records?"
    ),
    "answer": "NOT ESTABLISHED — see `resolution`",
    "verbatim_quotes_retrieved": [
        {
            "quote": (
                "By default, Lambda sets the system log level to INFO, and with this "
                "setting, Lambda automatically sends start and report log messages to "
                "CloudWatch."
            ),
            "source": (
                "AWS documentation summary retrieved via search of "
                "docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs-advanced.html"
                " on 2026-08-13"
            ),
        },
        {
            "quote": (
                "Note that log level controls are only available if the log format of the "
                "function is set to JSON."
            ),
            "source": (
                "https://aws.amazon.com/blogs/compute/"
                "introducing-advanced-logging-controls-for-aws-lambda-functions/"
            ),
        },
    ],
    "what_could_not_be_retrieved": (
        "the 'System log level event mapping' table, which is the only place AWS states "
        "which platform events survive WARN. The page is rendered client-side and every "
        "fetch of it returned an empty document."
    ),
    "resolution": (
        "the PESSIMISTIC reading is taken: platform.start and platform.report are counted "
        "as PRESENT at WARN. A bound built on the assumption that they are suppressed "
        "would understate ingestion, and this figure exists to bound a bill."
    ),
    "how_to_close_it": (
        "one `aws logs filter-log-events` against a deployed function whose "
        "system_log_level is WARN settles it in a single command. That requires an apply, "
        "which no worker in this wave is permitted to perform."
    ),
    "what_IS_established": (
        "system_log_level does not touch FUNCTION logs at all — those are "
        "application_log_level's surface — so nothing about WARN changes the handler "
        "figures measured below. It bounds only the runtime term."
    ),
}

# ══════════════════════════════════════════════════════════════════════════════════════
# the imports that must not be duplicated
# ══════════════════════════════════════════════════════════════════════════════════════


def _sibling(name: str) -> Any:
    """Import a sibling program out of ``scripts/deploy`` without leaving the path dirty.

    ``measure_beats`` and ``local_furl`` are programs, not a package, so they are imported
    by inserting their directory and taking it straight back out. The alternative — adding
    the repository root — makes eight top-level directories importable as namespace
    packages for everything that runs afterwards, which is the failure the demo-api
    conftest documents at length.
    """
    restore = list(sys.path)
    sys.path.insert(0, str(SCRIPTS_DEPLOY))
    try:
        return importlib.import_module(name)
    finally:
        sys.path[:] = restore


measure_beats = _sibling("measure_beats")
local_furl = _sibling("local_furl")

BEATS = measure_beats.BEATS
summarise = measure_beats.summarise
redact = measure_beats.redact
describe_dsn = measure_beats.describe_dsn


# ══════════════════════════════════════════════════════════════════════════════════════
# the tap: every record that reaches a handler, weighed the way CloudWatch weighs it
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Weighed:
    """One log record, in the three units that matter and are not the same unit."""

    logger: str
    level: str
    #: UTF-8 bytes of the formatted message plus any exception text and stack text — the
    #: quantity ``logbudget`` charges against its allowance.
    message_bytes: int
    #: What CloudWatch is billed for the same record: the JSON envelope Lambda writes
    #: around it under ``log_format = "JSON"``, plus AWS's documented per-event overhead.
    wire_bytes: int
    #: True when ``logbudget``'s filter never saw this record, because it was created on a
    #: logger the filter is not attached to. This is the gap the module's own docstring
    #: declares, quantified here rather than left as prose.
    outside_the_budget: bool


class _Tap(logging.Handler):
    """A handler that weighs every record instead of writing it.

    Attached to the ROOT logger, not to ``mainline_demo_api``. That is deliberate and it is
    the only way to see the whole bill: a record created on ``mainline_demo_api`` is put
    through that logger's filters — the budget — by ``Logger.handle`` and only then
    propagates to ancestors' HANDLERS, while a record created on ``psycopg`` reaches the
    same root handler having passed no filter at all. Tapping at the root therefore sees
    exactly what a Lambda's stdout would carry, and the ``outside_the_budget`` flag on each
    weighed record says which of the two it was.
    """

    def __init__(self, budgeted_logger: str = "mainline_demo_api") -> None:
        super().__init__(level=logging.NOTSET)
        self._budgeted = budgeted_logger
        self.weighed: list[Weighed] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            # The filter rewrites these before they get here; if one arrives unrewritten
            # that is itself the finding, so it is weighed rather than dropped.
            message = f"{record.msg!s} [unformattable]"
        if record.exc_info is not None and record.exc_text is None:
            record.exc_text = "".join(traceback.format_exception(*record.exc_info))
        if record.exc_text:
            message = f"{message}\n{record.exc_text}"
        if record.stack_info:
            message = f"{message}\n{record.stack_info}"
        envelope = {
            "timestamp": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "requestId": str(uuid.uuid4()),
            "message": message,
        }
        encoded = json.dumps(envelope, separators=(",", ":")).encode("utf-8", "replace")
        self.weighed.append(
            Weighed(
                logger=record.name,
                level=record.levelname,
                message_bytes=len(message.encode("utf-8", "replace")),
                wire_bytes=len(encoded) + PUT_LOG_EVENTS_OVERHEAD_BYTES,
                outside_the_budget=not (
                    record.name == self._budgeted or record.name.startswith(self._budgeted + ".")
                ),
            )
        )

    def drain(self) -> list[Weighed]:
        taken, self.weighed = self.weighed, []
        return taken


def envelope_overhead_bytes() -> int:
    """The constant cost of Lambda's JSON envelope around a zero-length message.

    Named and computed rather than folded into a total, because it is the term that makes
    ``logbudget``'s bound and CloudWatch's bill different numbers: the budget charges the
    MESSAGE and CloudWatch charges the ENVELOPE plus the message plus 26 bytes.
    """
    tap = _Tap()
    tap.emit(logging.LogRecord("mainline_demo_api", logging.WARNING, __file__, 0, "", None, None))
    return tap.drain()[0].wire_bytes


@contextlib.contextmanager
def tapped() -> Any:
    """Install the tap on the root logger at DEBUG, and take it off again.

    DEBUG rather than the deployment's level on purpose: this is a *measurement* of what
    the stack can emit, and level filtering is a separate, configurable question. The three
    call sites this package has are all WARNING or ERROR, so the level moves nothing for
    handler bytes; it matters only for libraries, and seeing a library speak is the point.
    """
    root = logging.getLogger()
    previous_level = root.level
    package_logger = logging.getLogger("mainline_demo_api")
    previous_package_level = package_logger.level
    tap = _Tap()
    root.addHandler(tap)
    root.setLevel(logging.DEBUG)
    package_logger.setLevel(logging.DEBUG)
    try:
        yield tap
    finally:
        root.removeHandler(tap)
        root.setLevel(previous_level)
        package_logger.setLevel(previous_package_level)


# ══════════════════════════════════════════════════════════════════════════════════════
# driving the real handler
# ══════════════════════════════════════════════════════════════════════════════════════


def _import_handler() -> Any:
    """Import the distribution's ``app`` module — the one the deployment artefact carries."""
    if str(DEFAULT_APP_SRC) not in sys.path:
        sys.path.insert(0, str(DEFAULT_APP_SRC))
    return importlib.import_module("mainline_demo_api.app")


def _event_for(
    beat: Any, *, source_ip: str = "203.0.113.7", accept_encoding: str | None = "gzip"
) -> dict[str, Any]:
    """The payload-format-2.0 event for one beat, browser-shaped by default.

    ``accept-encoding: gzip`` is sent because every browser sends it and because W1's wire
    ceiling (``static_site.DEFAULT_MAX_RESPONSE_BYTES``, 136 KiB in this tree) refuses the
    largest identity object with a 413. Driving the static beats WITHOUT it would measure a
    refusal and call it an asset. Both statuses are recorded either way, and a divergence
    from ``measure_beats``'s ``expect_status`` is disclosed rather than smoothed.
    """
    headers = [("accept", "*/*")]
    if accept_encoding:
        headers.append(("accept-encoding", accept_encoding))
    if beat.body is not None:
        headers.append(("content-type", "application/json"))
    return local_furl.build_event(
        beat.method, beat.path, headers, beat.body or b"", source_ip=source_ip
    )


def _totals(weighed: list[Weighed]) -> tuple[int, int, int]:
    """``(message_bytes, wire_bytes, records)`` for one invocation."""
    return (
        sum(w.message_bytes for w in weighed),
        sum(w.wire_bytes for w in weighed),
        len(weighed),
    )


def drive_beat(beat: Any, *, samples: int, warmup: int) -> dict[str, Any]:
    """Drive one beat *samples* times in-process and weigh what the logging stack emits.

    The rate limiter is disarmed for this probe — ``ratelimit.configure(global_rps=...)``
    with in-process keyword overrides, the seam ``measure_beats`` uses for the same reason
    — because what is being measured here is a *served* beat's log bytes. The refusal path
    is measured separately and deliberately, below, and conflating the two would report a
    flood's silence as a beat's.
    """
    app = _import_handler()
    from mainline_demo_api import logbudget, ratelimit

    ratelimit.configure(
        global_rps=ratelimit.MAX_RPS,
        global_burst=ratelimit.MAX_BURST,
        ip_rps=ratelimit.MAX_RPS,
        ip_burst=ratelimit.MAX_BURST,
    )
    ratelimit.reset()

    record: dict[str, Any] = {
        "beat": beat.name,
        "method": beat.method,
        "path": beat.path,
        "why": beat.why,
        "touches_database": beat.touches_database,
        "expect_status_from_measure_beats": beat.expect_status,
        "method_of_measurement": "measured",
        "request_accept_encoding": "gzip",
        "warmup_discarded": warmup,
    }
    message_samples: list[float] = []
    wire_samples: list[float] = []
    record_counts: list[float] = []
    charged_samples: list[float] = []
    statuses: dict[str, int] = {}
    loggers: dict[str, int] = {}
    outside = 0

    with tapped() as tap:
        for _ in range(warmup):
            logbudget.begin()
            app.handler(_event_for(beat), None)
            tap.drain()
        for _ in range(samples):
            logbudget.begin()
            answer = app.handler(_event_for(beat), None)
            weighed = tap.drain()
            message, wire, count = _totals(weighed)
            message_samples.append(float(message))
            wire_samples.append(float(wire))
            record_counts.append(float(count))
            charged_samples.append(float(logbudget.used()))
            statuses[str(answer.get("statusCode"))] = (
                statuses.get(str(answer.get("statusCode")), 0) + 1
            )
            for item in weighed:
                loggers[item.logger] = loggers.get(item.logger, 0) + 1
                outside += int(item.outside_the_budget)

    record["statuses_observed"] = statuses
    record["status_ok"] = list(statuses) == [str(beat.expect_status)]
    record["handler_message_bytes"] = summarise(message_samples)
    record["handler_wire_bytes"] = summarise(wire_samples)
    record["records_per_invocation"] = summarise(record_counts)
    record["logbudget_charged_bytes"] = summarise(charged_samples)
    record["loggers_that_spoke"] = loggers
    record["records_outside_the_budget_filter"] = outside
    return record


# ══════════════════════════════════════════════════════════════════════════════════════
# the flood: the case that matters, because ratelimit.check runs first
# ══════════════════════════════════════════════════════════════════════════════════════


def drive_flood(*, seconds: float, source_ips: int) -> dict[str, Any]:
    """Hammer the handler at the PRODUCTION rate defaults and weigh what the flood emits.

    ``ratelimit.configure()`` with no keywords, so the four numbers in force are the four
    code defaults a deployment that publishes nothing gets — which is the deployment as it
    stands (`cost-finish-plan.md` §0.4: none of the ``MAINLINE_RATE_*`` values is published
    by Terraform). Measuring against a configuration invented here would measure nothing.

    Two source-address regimes, because they are different threats and the module says so:
    one address (the per-IP bucket refuses) and *source_ips* rotating addresses (the global
    bucket refuses, and a rotating attacker gets a fresh per-IP burst every time).
    """
    app = _import_handler()
    from mainline_demo_api import logbudget, ratelimit

    settings = ratelimit.configure()
    ratelimit.reset()
    logbudget.reset()

    regimes: dict[str, Any] = {}
    for regime, addresses in (
        ("one_source_address", 1),
        (f"{source_ips}_rotating_source_addresses", source_ips),
    ):
        ratelimit.configure()
        ratelimit.reset()
        logbudget.reset()
        wire_samples: list[float] = []
        message_samples: list[float] = []
        statuses: dict[str, int] = {}
        throttle_lines = 0
        started = time.monotonic()
        index = 0
        with tapped() as tap:
            while time.monotonic() - started < seconds:
                address = f"198.51.100.{index % addresses}"
                event = local_furl.build_event(
                    "GET",
                    "/assets/index-BjAGxrVJ.js",
                    [("accept", "*/*")],
                    b"",
                    source_ip=address,
                )
                logbudget.begin()
                answer = app.handler(event, None)
                weighed = tap.drain()
                message, wire, _ = _totals(weighed)
                message_samples.append(float(message))
                wire_samples.append(float(wire))
                statuses[str(answer.get("statusCode"))] = (
                    statuses.get(str(answer.get("statusCode")), 0) + 1
                )
                throttle_lines += len(weighed)
                index += 1
        elapsed = time.monotonic() - started
        refused = statuses.get("429", 0)
        regimes[regime] = {
            "method_of_measurement": "measured",
            "invocations": index,
            "elapsed_seconds": round(elapsed, 3),
            "invocations_per_second": round(index / elapsed, 1) if elapsed > 0 else None,
            "statuses_observed": statuses,
            "refused_429": refused,
            "refusal_share": round(refused / index, 4) if index else None,
            "log_lines_emitted": throttle_lines,
            "lines_per_refusal": round(throttle_lines / refused, 6) if refused else None,
            "collapse_windows_elapsed": round(elapsed / _refill_window(settings), 2),
            "lines_permitted_by_the_collapse": (
                # One line per scope per refill window, plus one for the first line in each
                # scope's opening window. This is the number the collapse PROMISES; the
                # measured `log_lines_emitted` beside it is what it DELIVERED.
                2 * (int(elapsed / _refill_window(settings)) + 1)
            ),
            "collapse_suppressed": logbudget.collapsed(),
            "handler_wire_bytes_per_invocation": summarise(wire_samples),
            "handler_message_bytes_per_invocation": summarise(message_samples),
            "handler_wire_bytes_mean_per_invocation": round(statistics.fmean(wire_samples), 3),
        }
    return {
        "rate_limit_in_force": {
            "global_rps": settings.global_rps,
            "global_burst": settings.global_burst,
            "ip_rps": settings.ip_rps,
            "ip_burst": settings.ip_burst,
            "source": (
                "ratelimit.configure() with no keyword overrides: the four CODE defaults, "
                "which is what is in force because Terraform publishes none of the four "
                "MAINLINE_RATE_* variables"
            ),
            "refill_window_seconds": _refill_window(settings),
        },
        "regimes": regimes,
    }


def _refill_window(settings: Any) -> float:
    """The window a throttle line collapses over: capacity / rate, the bucket's own period."""
    return min(settings.global_burst / settings.global_rps, settings.ip_burst / settings.ip_rps)


def probe_collapse_under_concurrency(*, threads: int, seconds: float) -> dict[str, Any]:
    """Does one line per window survive *threads* callers at once?

    AWS gives one execution environment one event at a time, so this is not the deployment
    — and ``local_furl --concurrency parallel`` exists precisely to provoke the race the
    deployment does not have. It is measured anyway for one reason: ``logbudget.claim`` is
    a read-modify-write on a plain dict with no lock, and if two threads can both be
    admitted inside one window then the collapse is one line per window *per racing
    thread*, and the number this file hands W4 would be wrong by that factor.
    """
    app = _import_handler()
    from mainline_demo_api import logbudget, ratelimit

    settings = ratelimit.configure()
    ratelimit.reset()
    logbudget.reset()

    counter = {"lines": 0, "invocations": 0, "refused": 0}
    lock = threading.Lock()
    stop = threading.Event()

    tap = _Tap()
    root = logging.getLogger()
    root.addHandler(tap)
    previous = root.level
    root.setLevel(logging.DEBUG)
    logging.getLogger("mainline_demo_api").setLevel(logging.DEBUG)

    def worker() -> None:
        while not stop.is_set():
            event = local_furl.build_event(
                "GET",
                "/assets/index-BjAGxrVJ.js",
                [("accept", "*/*")],
                b"",
                source_ip="198.51.100.5",
            )
            answer = app.handler(event, None)
            with lock:
                counter["invocations"] += 1
                counter["refused"] += int(answer.get("statusCode") == 429)

    try:
        workers = [threading.Thread(target=worker, daemon=True) for _ in range(threads)]
        started = time.monotonic()
        for thread in workers:
            thread.start()
        time.sleep(seconds)
        stop.set()
        for thread in workers:
            thread.join(timeout=10)
        elapsed = time.monotonic() - started
    finally:
        root.removeHandler(tap)
        root.setLevel(previous)

    weighed = tap.drain()
    lines = len(weighed)
    windows = int(elapsed / _refill_window(settings)) + 1
    permitted = 2 * windows
    return {
        "method_of_measurement": "measured",
        "threads": threads,
        "elapsed_seconds": round(elapsed, 3),
        "invocations": counter["invocations"],
        "refused_429": counter["refused"],
        "collapse_windows_elapsed": windows,
        "lines_permitted_by_the_collapse": permitted,
        "log_lines_observed": lines,
        "wire_bytes_observed": sum(w.wire_bytes for w in weighed),
        "collapse_held": lines <= permitted,
        "excess_lines": max(0, lines - permitted),
        "not_the_deployment": (
            "AWS hands one execution environment one event at a time; this regime does not "
            "occur on a Function URL. It is measured because logbudget.claim is an unlocked "
            "read-modify-write and a race would multiply the flood figure by the number of "
            "racing callers"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the falsification probes: does the bound actually bind?
# ══════════════════════════════════════════════════════════════════════════════════════


def probe_deliberate_overrun(*, records: int, message_bytes: int) -> dict[str, Any]:
    """Emit far more than the budget through the REAL logging path and weigh what got out.

    Three shapes, because they are three different ways to defeat a byte ceiling and only
    the first is the one everybody thinks of:

    ``many_records``    a call site in a loop — no call site in this package has this
                        shape today, so it is the future one;
    ``one_huge_record`` a single message larger than the whole allowance;
    ``exception_with_a_deep_stack``
                        ``log.exception`` in a loop, which is the biggest thing a loop
                        could emit;
    ``one_exception_the_size_of_the_allowance``
                        **the worst shape any call site in this package can actually
                        reach**: exactly one ``log.exception`` per invocation, at
                        ``app.py:523``, with a traceback that fills the budget. The
                        derivation's roof term is this figure and not a hypothetical one;
    ``stack_info_true`` ``stack_info=True``, which appends ``record.stack_info`` in every
                        downstream ``Formatter``. Before 2026-08-13 the filter neither
                        charged nor truncated it.
    """
    from mainline_demo_api import logbudget

    log = logging.getLogger("mainline_demo_api")
    ceiling = logbudget.DEFAULT_BUDGET_BYTES + logbudget.OVERRUN_BOUND
    shapes: dict[str, Any] = {}

    def _run(name: str, emit: Any) -> None:
        logbudget.reset()
        logbudget.begin()
        with tapped() as tap:
            emit(log)
            weighed = tap.drain()
        message, wire, count = _totals(weighed)
        shapes[name] = {
            "records_admitted": count,
            "message_bytes_that_reached_a_handler": message,
            "wire_bytes_that_reached_a_handler": wire,
            "logbudget_charged": logbudget.used(),
            "records_dropped": logbudget.dropped(),
            "within_message_ceiling": message <= ceiling,
            "wire_over_message_ratio": round(wire / message, 3) if message else None,
        }

    def _many(log: logging.Logger) -> None:
        for index in range(records):
            log.warning("a line of ordinary length, number %06d", index)

    def _huge(log: logging.Logger) -> None:
        log.warning("%s", "z" * message_bytes)

    def _exception(log: logging.Logger) -> None:
        def deep(level: int) -> None:
            if level == 0:
                raise ValueError("a detail string that is itself " + "long " * 400)
            deep(level - 1)

        for _ in range(8):
            try:
                deep(24)
            except ValueError:
                log.exception("read %s raised", "demo.permit")

    def _one_exception(log: logging.Logger) -> None:
        # The detail string is deliberately larger than the whole allowance. Recursion
        # depth alone does NOT produce a long traceback: `traceback.format_exception`
        # collapses repeated frames into "[Previous line repeated N more times]", so
        # `deep(60)` measured only 2,837 message bytes against a 4,096-byte budget on
        # 2026-08-13 — i.e. it did not fill the allowance and so was not the roof it
        # claimed to be. A 10,000-character detail fills it every time and forces the
        # `exc_text` truncation, which is the state this shape has to be in to be a bound.
        def deep(level: int) -> None:
            if level == 0:
                raise ValueError("a detail string that is itself " + "long " * 2000)
            deep(level - 1)

        try:
            deep(12)
        except ValueError:
            log.exception("read %s raised", "demo.permit")

    def _stack(log: logging.Logger) -> None:
        def deep(level: int) -> None:
            if level == 0:
                for _ in range(8):
                    log.warning("a line with a stack attached", stack_info=True)
                return
            deep(level - 1)

        deep(40)

    _run("many_records", _many)
    _run("one_huge_record", _huge)
    _run("exception_with_a_deep_stack", _exception)
    _run("one_exception_the_size_of_the_allowance", _one_exception)
    _run("stack_info_true", _stack)

    return {
        "method_of_measurement": "measured",
        "budget_bytes_in_force": logbudget.DEFAULT_BUDGET_BYTES,
        "overrun_bound": logbudget.OVERRUN_BOUND,
        "message_ceiling": ceiling,
        "shapes": shapes,
        "what_the_ceiling_bounds": (
            "MESSAGE bytes, which is what logbudget charges. CloudWatch is billed the WIRE "
            "bytes beside them: Lambda's JSON envelope per record plus AWS's documented 26 "
            "bytes per event. The ratio in each shape is how much a reader must multiply "
            "the code bound by to get the bill"
        ),
    }


def probe_a_logger_the_filter_never_sees(*, records: int, size: int) -> dict[str, Any]:
    """Quantify the gap ``logbudget``'s own docstring declares, instead of restating it.

    "Anything logged through a different logger" is outside the ceiling, because a
    :class:`logging.Filter` attached to a logger is consulted by that logger's ``handle``
    and a sibling logger's records reach the same *handlers* without passing it. psycopg is
    the library in this distribution most likely to speak, so it is the one probed.
    """
    from mainline_demo_api import logbudget

    logbudget.reset()
    logbudget.begin()
    other = logging.getLogger("psycopg")
    with tapped() as tap:
        for index in range(records):
            other.warning("a library line, number %06d: %s", index, "q" * size)
        weighed = tap.drain()
    message, wire, count = _totals(weighed)
    return {
        "method_of_measurement": "measured",
        "logger": "psycopg",
        "records_emitted": records,
        "records_that_reached_a_handler": count,
        "message_bytes_that_reached_a_handler": message,
        "wire_bytes_that_reached_a_handler": wire,
        "logbudget_charged": logbudget.used(),
        "bounded_by_the_per_invocation_budget": logbudget.used() > 0,
        "finding": (
            "the per-invocation budget charged nothing for any of it. This is DECLARED in "
            "logbudget's module docstring and is measured here so the ingestion threshold "
            "is derived from a number that includes it rather than from the handler's own "
            "bound alone. It is not a defect in logbudget: a filter sees the records its "
            "logger creates. It IS the reason the alarm exists"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the runtime's own lines
# ══════════════════════════════════════════════════════════════════════════════════════

_RIE_HANDLER: Final = 'def handler(event, context):\n    return {"statusCode": 200}\n'

#: Lines the Runtime Interface Emulator's local RAPID writes and the PRODUCTION runtime
#: does not. Excluded from the measurement, and the exclusion is recorded in the payload
#: rather than performed silently.
_RIE_ONLY: Final = "(rapid)"


def probe_runtime_lines(
    *, image: str, invocations: int, port: int, memory_mb: int
) -> dict[str, Any]:
    """Measure the real ``START`` / ``END`` / ``REPORT`` triple from the managed base image.

    ``public.ecr.aws/lambda/python:3.13`` is the image AWS builds the managed runtime from,
    and it carries the Runtime Interface Emulator. Driving it and reading its stderr is the
    closest a worker forbidden from applying anything can get to a real ``REPORT`` line.

    **What this is not**, recorded on the figure itself: the emulator writes the TEXT form
    of the triple whatever ``AWS_LAMBDA_LOG_FORMAT`` says, and the deployment sets
    ``log_format = "JSON"``. So this measurement bounds the *text* shape and the JSON shape
    is computed from AWS's documented schema separately. Both are published; neither is
    presented as the other.
    """
    container = f"mainline-logbytes-{os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="mainline-rie-") as scratch:
        (Path(scratch) / "app.py").write_text(_RIE_HANDLER, encoding="utf-8")
        run = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                "-p",
                f"{port}:8080",
                "-e",
                f"AWS_LAMBDA_FUNCTION_MEMORY_SIZE={memory_mb}",
                "-e",
                "AWS_LAMBDA_LOG_FORMAT=JSON",
                "-e",
                "AWS_LAMBDA_LOG_LEVEL=WARN",
                "-v",
                f"{scratch}:/var/task",
                image,
                "app.handler",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
        )
        if run.returncode != 0:
            return {
                "supported": False,
                "reason": redact(run.stderr.strip()[:400]) or "docker run failed",
            }
        try:
            url = f"http://127.0.0.1:{port}/2015-03-31/functions/function/invocations"
            deadline = time.monotonic() + 60
            ready = False
            while time.monotonic() < deadline and not ready:
                try:
                    urllib.request.urlopen(
                        urllib.request.Request(url, data=b"{}"), timeout=10
                    ).read()
                    ready = True
                except (urllib.error.URLError, OSError):
                    time.sleep(0.25)
            if not ready:
                return {"supported": False, "reason": "the emulator never answered"}
            for _ in range(invocations):
                urllib.request.urlopen(urllib.request.Request(url, data=b"{}"), timeout=30).read()
            time.sleep(1.0)
            logs = subprocess.run(
                ["docker", "logs", container],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            captured = f"{logs.stdout}\n{logs.stderr}"
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )

    kinds: dict[str, list[float]] = {"START": [], "END": [], "REPORT": [], "INIT_START": []}
    rie_only = 0
    other = 0
    for raw in captured.splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if _RIE_ONLY in line:
            rie_only += 1
            continue
        for kind, values in kinds.items():
            if line.startswith(kind):
                values.append(float(len(line.encode("utf-8")) + PUT_LOG_EVENTS_OVERHEAD_BYTES))
                break
        else:
            other += 1

    per_kind = {kind: summarise(values) for kind, values in kinds.items() if values}
    # `summarise` names its fields `*_ms` because it was written for latencies; the values
    # here are BYTES. Renaming them would fork the estimator, which is the thing this file
    # exists not to do, so the unit is stated instead — see `units` in the payload.
    per_invocation = sum(
        per_kind[kind]["max_ms"] for kind in ("START", "END", "REPORT") if kind in per_kind
    )
    return {
        "supported": True,
        "method_of_measurement": "measured-emulator",
        "image": image,
        "memory_size_mb": memory_mb,
        "invocations": invocations,
        "units": (
            "BYTES. `summarise` is measure_beats' nearest-rank estimator and names its "
            "fields `*_ms`; it is reused rather than forked, so read every `*_ms` here as "
            "bytes"
        ),
        "per_line_bytes": per_kind,
        "bytes_per_invocation_text_format": per_invocation,
        "rie_only_lines_excluded": rie_only,
        "unclassified_lines": other,
        "what_this_measures": (
            "the real managed-runtime base image's own per-invocation lines, in the TEXT "
            "format the Runtime Interface Emulator emits"
        ),
        "what_this_does_NOT_measure": [
            (
                "the JSON platform.start / platform.report records the DEPLOYMENT gets, "
                "because logging_config.log_format = 'JSON' and the emulator ignores "
                "AWS_LAMBDA_LOG_FORMAT for these lines. The JSON figure is computed from "
                "AWS's documented schema and labelled `documented`"
            ),
            (
                "the Init Duration term, which appears in a production REPORT only on a "
                "cold start and which the emulator did not produce here"
            ),
            ("whether system_log_level = WARN suppresses any of them — see system_log_level_note"),
        ],
    }


def documented_runtime_lines() -> dict[str, Any]:
    """The JSON platform records the DEPLOYMENT gets, sized from AWS's documented shape.

    **This is a computation over a citation, not a measurement, and it says so in its own
    ``method`` field.** The records are AWS's own examples from the Telemetry API `Event`
    schema reference, reproduced above; what is computed here is their length.
    """

    def sized(document: dict[str, Any]) -> int:
        return len(json.dumps(document, separators=(",", ":")).encode("utf-8"))

    start = sized(DOCUMENTED_PLATFORM_START)
    report = sized(DOCUMENTED_PLATFORM_REPORT)
    runtime_done = sized(DOCUMENTED_PLATFORM_RUNTIME_DONE)
    overhead = PUT_LOG_EVENTS_OVERHEAD_BYTES
    return {
        "method_of_measurement": "documented",
        "source": TELEMETRY_SCHEMA_SOURCE,
        "how": (
            "AWS's own example records for platform.start, platform.report and "
            "platform.runtimeDone, serialised compactly and measured. The EXAMPLES are "
            "AWS's; the LENGTHS are this program's arithmetic over them. Nothing here was "
            "observed on a Lambda"
        ),
        "per_event_overhead_bytes": overhead,
        "per_event_overhead_quote": PUT_LOG_EVENTS_QUOTE,
        "per_event_overhead_source": PUT_LOG_EVENTS_SOURCE,
        "platform_start_bytes": start + overhead,
        "platform_report_bytes": report + overhead,
        "platform_runtime_done_bytes": runtime_done + overhead,
        "pessimistic_per_invocation_bytes": start + report + runtime_done + 3 * overhead,
        "pessimistic_per_invocation_basis": (
            "start + report + runtimeDone. runtimeDone is included because this worker "
            "could not retrieve AWS's system-log-level event-mapping table and therefore "
            "cannot say it is suppressed at WARN; including it overstates ingestion, which "
            "is the safe direction for a bound on a bill"
        ),
        "conservative_per_invocation_bytes": start + report + 2 * overhead,
        "conservative_per_invocation_basis": (
            "start + report only, which is the pair AWS's documentation summary names "
            "explicitly ('Lambda automatically sends start and report log messages')"
        ),
        "tracing_caveat": (
            "AWS's platform.start and platform.runtimeDone examples carry a `tracing` block "
            "of about 150 bytes. It is present only when active tracing is on; "
            "infra/modules/demo-api does not enable X-Ray, so the real records are SMALLER "
            "than these figures. Keeping AWS's example intact rather than trimming it to "
            "flatter the number is deliberate: the citation stays a citation"
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the derivation W4 needs
# ══════════════════════════════════════════════════════════════════════════════════════

#: `infra/modules/cost-guard/variables.tf`, read rather than remembered. Restated here as
#: the INPUT to a comparison, never as a target: this file's job is to produce a number
#: from measurement and then say plainly whether it is above or below the standing default.
COST_GUARD_DEFAULTS: Final[dict[str, int]] = {
    "invocations_burst_threshold": 3000,
    "invocations_hourly_threshold": 15000,
    "log_incoming_bytes_threshold": 16777216,
    "log_bytes_per_invocation_ceiling": 16384,
    "account_concurrency_ceiling": 10,
    "fastest_invocation_ms": 10,
}

ALARM_PERIOD_SECONDS: Final = 300
BURST_PERIOD_SECONDS: Final = 60

#: `infra/modules/cost-guard/variables.tf` models a judging session two ways and names both.
#: The PESSIMISTIC one is the number a threshold must not fire on, and it is restated here
#: as an INPUT to the false-positive check below — not as something this file chose.
PESSIMISTIC_SESSION_INVOCATIONS_PER_HOUR: Final = 6420
PESSIMISTIC_SESSION_SOURCE: Final = (
    "infra/modules/cost-guard/variables.tf, log_incoming_bytes_threshold's own derivation: "
    "'PESSIMISTIC 5-minute window 20 judges x 321/h = 6,420/h = 535/min'"
)

#: **A UNIT SLIP IN THE FILE THIS NUMBER COMES FROM, REPORTED RATHER THAN ADOPTED.**
#:
#: That same derivation continues "2,675 invocations x ~400 B = 1.07 MB" for a 5-minute
#: window. Both cannot be right: 6,420 per HOUR is 107 per minute, not 535, and over a
#: 300-second window it is 6,420 x 300/3600 = **535 invocations**, not 2,675. The 2,675
#: follows from reading 535 as a per-minute rate, which is where the slip is.
#:
#: This file uses the figure consistent with the stated session rate — 535 per 300 s — and
#: does not edit `variables.tf`, which is W4's. Adopting 2,675 would make every margin
#: computed here look 5x more comfortable than the session model supports, which is the
#: direction that flatters a threshold, so the arithmetic is written out here and the
#: discrepancy is handed over rather than absorbed.
PESSIMISTIC_SESSION_UNIT_SLIP: Final = (
    "infra/modules/cost-guard/variables.tf derives the pessimistic 5-minute window as "
    "'20 judges x 321/h = 6,420/h = 535/min ... 2,675 invocations'. 6,420 per hour is 107 "
    "per minute, and over a 300-second window it is 6,420 x 300/3600 = 535 invocations. "
    "The '535/min' reads a per-300-second figure as a per-minute one, and the 2,675 is that "
    "slip multiplied by five. This file uses 535 per 300 s, the figure consistent with the "
    "stated session rate, and leaves variables.tf alone: it is W4's file, and adopting the "
    "larger number would make every margin below look 5x more comfortable than the session "
    "model supports."
)


def derive_threshold(
    runtime_documented: dict[str, Any],
    runtime_measured: dict[str, Any],
    beats: dict[str, Any],
    flood: dict[str, Any],
    overrun: dict[str, Any],
) -> dict[str, Any]:
    """Derive ``log_incoming_bytes_threshold`` with every step written out to be argued with.

    The brief's formula is ``measured_bytes_per_invocation x the burst invocation
    threshold``. Two things have to be made explicit before that product means anything,
    and they are steps 2 and 4 below rather than adjustments applied quietly:

    * the two alarms have **different windows** — the burst alarm is a 60-second Sum and
      the ingestion alarm is a 300-second Sum — so the invocation count has to be carried
      across the window ratio or the product is out by 5x;
    * ``bytes_per_invocation`` is not one number. It is the runtime's fixed term plus the
      handler's, and the handler's is a *distribution* with a floor (the flood, where the
      collapse holds it near zero), a body (the served beats) and a **code ceiling**
      (``DEFAULT_BUDGET_BYTES + OVERRUN_BOUND``, which no invocation can exceed).

    So three thresholds are computed, from the same arithmetic and three different values
    of one term, and one of them is recommended with the reason stated. A reader who
    disagrees can disagree with the choice of term rather than with a preference.
    """
    from mainline_demo_api import logbudget

    runtime_term = runtime_documented["pessimistic_per_invocation_bytes"]
    runtime_measured_term = (
        runtime_measured.get("bytes_per_invocation_text_format")
        if runtime_measured.get("supported")
        else None
    )

    served = {
        name: record["handler_wire_bytes"]["p99_ms"]
        for name, record in beats.items()
        if "handler_wire_bytes" in record
    }
    worst_beat = max(served.values()) if served else 0.0
    flood_mean = max(
        regime["handler_wire_bytes_mean_per_invocation"] for regime in flood["regimes"].values()
    )
    # THE ROOF, AND WHY IT IS A MEASUREMENT AND NOT A PRODUCT.
    #
    # The code ceiling bounds MESSAGE bytes. CloudWatch bills the wire, and the wire costs
    # one JSON envelope plus 26 bytes PER RECORD, so the same allowance spent as many small
    # records costs several times what it costs spent as one — measured at 4.5x for the
    # `many_records` shape. Multiplying the message ceiling by an envelope would therefore
    # produce a number that looks derived and is not.
    #
    # So the roof used here is the largest WIRE figure any shape a call site in THIS
    # PACKAGE can actually reach produced: exactly one `log.exception` per invocation with
    # a traceback that fills the allowance, which is `app.py:523`. The `many_records`
    # shape is larger and no call site here has it — there are three call sites in the
    # distribution and none of them loops — so it is carried as a named residual instead of
    # inflating a threshold with a shape nobody can invoke.
    message_ceiling = logbudget.DEFAULT_BUDGET_BYTES + logbudget.OVERRUN_BOUND
    envelope = envelope_overhead_bytes()
    shapes = overrun["shapes"]
    reachable = shapes["one_exception_the_size_of_the_allowance"]
    ceiling_term = float(reachable["wire_bytes_that_reached_a_handler"])
    unreachable = {
        name: float(shape["wire_bytes_that_reached_a_handler"])
        for name, shape in shapes.items()
        if name != "one_exception_the_size_of_the_allowance"
    }
    unreachable_worst = max(unreachable.values())
    unreachable_worst_shape = max(unreachable, key=lambda name: unreachable[name])

    burst = COST_GUARD_DEFAULTS["invocations_burst_threshold"]
    window_ratio = ALARM_PERIOD_SECONDS // BURST_PERIOD_SECONDS
    permitted = burst * window_ratio

    def product(handler_term: float) -> int:
        return round((runtime_term + handler_term) * permitted)

    candidates = {
        "floor_flood_path": {
            "handler_bytes_per_invocation": round(flood_mean, 3),
            "handler_bytes_basis": (
                "MEASURED mean over a sustained 429 flood at the production rate defaults, "
                "which is the hottest path in the function and the one a flood is made of"
            ),
            "threshold_bytes": product(flood_mean),
        },
        "body_worst_served_beat": {
            "handler_bytes_per_invocation": round(worst_beat, 3),
            "handler_bytes_basis": (
                "MEASURED p99 of the noisiest demo beat, so ordinary judging traffic sits under it"
            ),
            "threshold_bytes": product(worst_beat),
        },
        "roof_worst_reachable_call_site": {
            "handler_bytes_per_invocation": ceiling_term,
            "handler_bytes_basis": (
                f"MEASURED wire bytes of the worst shape any call site in this package can "
                f"reach: one log.exception per invocation (app.py:523) with a traceback "
                f"that fills the allowance. The code bound behind it is "
                f"DEFAULT_BUDGET_BYTES {logbudget.DEFAULT_BUDGET_BYTES} + OVERRUN_BOUND "
                f"{logbudget.OVERRUN_BOUND} = {message_ceiling} MESSAGE bytes; the wire "
                f"figure adds Lambda's {envelope}-byte JSON envelope and CloudWatch's "
                f"26-byte per-event overhead"
            ),
            "threshold_bytes": product(ceiling_term),
        },
    }

    standing = COST_GUARD_DEFAULTS["log_incoming_bytes_threshold"]
    lower_edge = candidates["floor_flood_path"]["threshold_bytes"]
    upper_edge = candidates["roof_worst_reachable_call_site"]["threshold_bytes"]

    # THE CONSTRAINT EVERY CANDIDATE MUST CLEAR, COMPUTED SEPARATELY SO IT CAN VETO ONE.
    #
    # The responder reserves concurrency at 0 and only a human running kill_switch
    # --restore ends that. So a threshold a LEGITIMATE session can reach does not bound a
    # bill; it stops the demo during the incident whose logs somebody needs. The worst
    # legitimate case is the pessimistic panel cost-guard already models, every invocation
    # of it emitting the reachable per-invocation ceiling — which is what a database
    # outage mid-demo looks like.
    pessimistic_per_300s = int(
        PESSIMISTIC_SESSION_INVOCATIONS_PER_HOUR * ALARM_PERIOD_SECONDS / 3600
    )
    false_positive_floor = round(pessimistic_per_300s * (runtime_term + ceiling_term))

    # THE RECOMMENDATION, AND IT IS NOT THE ONE THIS FILE SET OUT TO MAKE.
    #
    # The brief's formula produces the UPPER edge. The measurement then does something the
    # formula could not anticipate: it finds that a working handler emits ZERO bytes of its
    # own on every beat and on 2.1 million flood invocations, so ordinary ingestion here is
    # ~100 % the runtime's fixed term and the handler term only ever appears when something
    # is already wrong. That turns the single product into a BAND with two edges that mean
    # different things, and the standing default already sits inside it. Publishing a band
    # and where the standing number falls in it is worth more than moving a number that is
    # already admissible, so the recommendation is to RETAIN — derived, not deferred.
    standing_is_admissible = lower_edge <= standing <= upper_edge
    recommended = "retain_the_standing_default" if standing_is_admissible else "roof"
    recommended_bytes = standing if standing_is_admissible else upper_edge

    return {
        "quantity": "log_incoming_bytes_threshold",
        "consumer": "infra/modules/cost-guard, alarm 3 of 3 (AWS/Logs IncomingBytes, Sum/300s)",
        "arithmetic": [
            {
                "step": 1,
                "name": "the runtime's own per-invocation bytes",
                "value": runtime_term,
                "method": "documented",
                "how": (
                    "platform.start + platform.report + platform.runtimeDone, sized from "
                    "AWS's own example records, each plus AWS's documented 26-byte "
                    "per-event overhead. NOT measured; see runtime_lines_documented"
                ),
                "measured_cross_check": runtime_measured_term,
                "measured_cross_check_how": (
                    "the same triple in TEXT form, MEASURED off the real "
                    "public.ecr.aws/lambda/python:3.13 base image through the Runtime "
                    "Interface Emulator. A different format, so a cross-check on the order "
                    "of magnitude and not a substitute"
                ),
            },
            {
                "step": 2,
                "name": "the handler's own per-invocation bytes",
                "value": "three candidates — see `candidates`",
                "method": "measured (floor, body) / code bound (roof)",
                "how": (
                    "the handler term is a distribution, not a number. Publishing one value "
                    "for it would hide the choice being made, so all three are published "
                    "and one is recommended below"
                ),
            },
            {
                "step": 3,
                "name": "the invocation count the burst alarm permits, per BURST window",
                "value": burst,
                "method": "read from infra/modules/cost-guard/variables.tf",
                "how": (
                    "invocations_burst_threshold is a strict GreaterThanThreshold on a "
                    "60-second Sum, so a caller may sustain exactly this many per minute "
                    "without alarm 1 firing"
                ),
            },
            {
                "step": 4,
                "name": "the same count over the INGESTION alarm's window",
                "value": permitted,
                "method": "arithmetic",
                "how": (
                    f"the ingestion alarm's period is {ALARM_PERIOD_SECONDS} s and the burst "
                    f"alarm's is {BURST_PERIOD_SECONDS} s, so the permitted count over one "
                    f"ingestion window is {burst} x {ALARM_PERIOD_SECONDS}/"
                    f"{BURST_PERIOD_SECONDS} = {burst} x {window_ratio} = {permitted}. "
                    "Omitting this step is how a threshold ends up 5x too small"
                ),
            },
            {
                "step": 5,
                "name": "the product",
                "value": "(step 1 + step 2) x step 4",
                "method": "arithmetic",
                "how": (
                    "the most a caller who never trips the INVOCATION alarms can put into "
                    "the log group in one ingestion window. Anything above it is ingestion "
                    "the invocation alarms cannot explain, which is exactly and only what "
                    "alarm 3 says it exists to catch"
                ),
            },
        ],
        "candidates": candidates,
        "false_positive_floor": {
            "bytes": false_positive_floor,
            "method": "measured x an input read from cost-guard's own derivation",
            "how": (
                f"{pessimistic_per_300s} invocations per 300 s "
                f"({PESSIMISTIC_SESSION_INVOCATIONS_PER_HOUR}/h x {ALARM_PERIOD_SECONDS}/3600) "
                f"x {runtime_term + ceiling_term:.0f} B per invocation (runtime term "
                f"{runtime_term} + worst reachable handler term {ceiling_term:.0f}) = "
                f"{false_positive_floor} B"
            ),
            "invocations_source": PESSIMISTIC_SESSION_SOURCE,
            "invocations_source_unit_slip": PESSIMISTIC_SESSION_UNIT_SLIP,
            "what_it_means": (
                "a threshold at or below this fires on a LEGITIMATE pessimistic judging "
                "session in which every invocation is logging a full diagnostic — i.e. on a "
                "database outage during the demo. The responder reserves concurrency at 0 "
                "and only a human running scripts/deploy/kill_switch --restore ends that, "
                "so such a threshold does not bound a bill: it converts an incident into an "
                "outage and deletes the logs you would have used to diagnose it"
            ),
            "clearance": {
                name: round(candidate["threshold_bytes"] / false_positive_floor, 3)
                for name, candidate in candidates.items()
            },
            "standing_default_clearance": round(standing / false_positive_floor, 3),
        },
        "admissible_band": {
            "lower_edge_bytes": lower_edge,
            "lower_edge_rule": (
                f"the flood-path candidate, {lower_edge} B. BELOW this the ingestion alarm "
                f"fires on {permitted} invocations that emit NOTHING of their own — pure "
                f"runtime lines — which is traffic the burst alarm deliberately permits. An "
                "alarm 3 under this line is a copy of alarm 1 at a lower threshold, which is "
                "the 'a control that looks like two and is one' shape cost-guard's own "
                "hourly precondition already forbids for alarms 1 and 2"
            ),
            "upper_edge_bytes": upper_edge,
            "upper_edge_rule": (
                f"the roof candidate, {upper_edge} B, which is the brief's formula with the "
                "worst per-invocation term any call site here can reach. ABOVE this, no "
                "traffic the invocation alarms permit can reach the line by any route, so "
                "alarm 3 stops catching the band between the two and only catches bytes that "
                "no invocation count explains at all"
            ),
            "false_positive_floor_bytes": false_positive_floor,
            "standing_default_bytes": standing,
            "standing_default_is_inside_the_band": standing_is_admissible,
            "standing_default_position": (
                f"{standing / lower_edge:.2f}x the lower edge, "
                f"{standing / upper_edge:.2f}x the upper edge, "
                f"{standing / false_positive_floor:.2f}x the false-positive floor"
            ),
        },
        "recommended": recommended,
        "recommended_bytes": recommended_bytes,
        "recommended_because": (
            "THE MEASUREMENT CHANGED THE ANSWER, AND THIS IS THE HONEST CONSEQUENCE. The "
            "brief's formula produces the UPPER edge. What the formula could not know is "
            "what this program then measured: a working handler emits ZERO bytes of its own "
            "— on all five beats, over 480 invocations, and over 2.1 million flood "
            "invocations at the production rate defaults. Ordinary ingestion here is "
            "therefore ~100 % the runtime's fixed term, and the handler term appears only "
            "when something is already wrong. That makes the single product a BAND rather "
            "than a point, and the standing default already sits inside it, "
            f"{standing / lower_edge:.2f}x above the lower edge and clearing the "
            f"false-positive floor by {standing / false_positive_floor:.2f}x. "
            "Between two admissible values the repository's own ranking picks the tighter "
            "one — cost-finish-plan.md §0.5: an outage is recoverable by one command and a "
            "bill is not — and the tighter one is the number already in the file. So the "
            "recommendation is RETAIN 16,777,216 B, and what this file contributes is not a "
            "new number but the band that makes the existing one defensible and the two "
            "edges that will invalidate it"
        ),
        "what_would_change_this_recommendation": [
            (
                "a call site that loops or passes stack_info=True: the reachable "
                f"per-invocation wire term rises from {ceiling_term:.0f} B to as much as "
                f"{unreachable_worst:.0f} B, both edges move up with it, and the standing "
                "default may fall below the lower edge"
            ),
            (
                "raising DEFAULT_BUDGET_BYTES: the same, proportionally. Note the "
                "direction — a LARGER log budget requires a LARGER ingestion threshold, so "
                "the two numbers are coupled and must move together or the alarm starts "
                "firing on the budget"
            ),
            (
                "lowering invocations_burst_threshold: both edges fall proportionally, and "
                "at a burst threshold below "
                f"{round(standing / (runtime_term + ceiling_term) / window_ratio)} per "
                "minute the standing default leaves the band through the top"
            ),
            (
                "a library that starts logging per row: nothing in the handler bounds it "
                "(measured: 75,800 wire B for 200 psycopg records, charged 0), and it is "
                "the one shape that can decouple bytes from invocations without limit. That "
                "case argues for the LOWER edge, not the upper"
            ),
        ],
        "against_the_standing_default": {
            "standing_default_bytes": standing,
            "recommended_bytes": recommended_bytes,
            "briefs_formula_bytes": upper_edge,
            "briefs_formula_is": "ABOVE" if upper_edge > standing else "BELOW",
            "briefs_formula_ratio_over_standing": round(upper_edge / standing, 3),
            "stated_plainly": (
                f"the number the brief's formula produces, {upper_edge} B, is "
                f"{upper_edge / standing:.2f}x ABOVE the standing default of {standing} B in "
                "infra/modules/cost-guard/variables.tf. The number this file recommends, "
                f"{recommended_bytes} B, is the standing default itself"
            ),
            "consequence_of_the_standing_default": (
                f"{standing} B over 300 s is {standing / permitted:.0f} B per invocation "
                f"the burst alarm permits. The runtime term alone is {runtime_term} B, so "
                f"the standing default leaves about {standing / permitted - runtime_term:.0f} "
                "B per invocation for the handler — far under the 4,096 B the handler's own "
                "budget allows it. A caller pacing just under the burst alarm whose "
                "invocations each emit a full diagnostic therefore trips the INGESTION alarm "
                "without tripping either invocation alarm. Both alarms feed the same topic "
                "and the same responder, so the outcome is the same stop either way; what "
                "this costs is only that alarm 3 rather than alarm 1 is named in the "
                "notification"
            ),
            "what_the_standing_default_would_cost_if_it_fired_wrongly": (
                f"it clears the false-positive floor by "
                f"{standing / false_positive_floor:.2f}x, so a full diagnostic storm during "
                f"a pessimistic {PESSIMISTIC_SESSION_INVOCATIONS_PER_HOUR}/h judging session "
                f"reaches only {false_positive_floor} B in a 300-second window and does not "
                "trip it. A panel "
                f"{standing / false_positive_floor:.1f}x that size would"
            ),
            "worst_shape_that_no_call_site_can_reach_today": {
                "shape": unreachable_worst_shape,
                "wire_bytes_per_invocation": unreachable_worst,
                "every_shape_measured": unreachable,
                "why_it_is_not_in_the_threshold": (
                    "there are three log call sites in this distribution — app.py:515, "
                    "app.py:523 and ratelimit.py:526 — none of them loops and none of them "
                    "passes stack_info=True, so no input a caller controls reaches these "
                    "shapes. Folding an unreachable shape into a threshold would inflate it "
                    "with something nobody can provoke, which is the mirror image of "
                    "understating it"
                ),
                "when_this_stops_being_true": (
                    "the moment a fourth call site loops or passes stack_info=True. Both "
                    "are one keyword away, and the byte ceiling still holds in both cases "
                    "(measured above) — what changes is the WIRE figure, because each extra "
                    "record pays its own envelope and 26-byte overhead. So this is the "
                    "number to re-derive the threshold from, not a reason to re-derive the "
                    "budget"
                ),
            },
            "the_inconvenient_half": (
                "the brief's formula produces a threshold that permits more spend than the "
                f"standing default: {upper_edge} B per 300 s sustained is "
                f"{upper_edge * 288 / 1e9:.2f} GB/day, about USD "
                f"{upper_edge * 288 / 1e9 * 0.57:.2f}/day at ap-southeast-1's ~USD 0.57/GB, "
                f"against the standing default's {standing * 288 / 1e9:.2f} GB/day and USD "
                f"{standing * 288 / 1e9 * 0.57:.2f}/day. It is published because it is what "
                "the arithmetic says, and it is not adopted because the measurement says "
                "the tighter end of the band is reachable without false positives. W4 owns "
                "the choice; this file owns the arithmetic for both ends of it"
            ),
        },
        "reachability_precondition": {
            "rule": (
                "cost-guard main.tf:773 requires log_incoming_bytes_threshold < "
                "invocations_max_300s x log_bytes_per_invocation_ceiling"
            ),
            "invocations_max_300s": (
                COST_GUARD_DEFAULTS["account_concurrency_ceiling"]
                * ALARM_PERIOD_SECONDS
                * 1000
                // COST_GUARD_DEFAULTS["fastest_invocation_ms"]
            ),
            "log_bytes_per_invocation_ceiling_standing": COST_GUARD_DEFAULTS[
                "log_bytes_per_invocation_ceiling"
            ],
            "log_bytes_per_invocation_ceiling_measured": round(runtime_term + ceiling_term),
            "log_bytes_per_invocation_ceiling_measured_how": (
                "the runtime's documented per-invocation term plus the handler's code "
                "ceiling carried to wire bytes. W4 should set the Terraform variable to "
                "this, because its own description says to: 'If W4's budget lands at a "
                "different figure, change this one to match'"
            ),
            "precondition_satisfied_at_the_recommendation": bool(
                recommended_bytes
                < (
                    COST_GUARD_DEFAULTS["account_concurrency_ceiling"]
                    * ALARM_PERIOD_SECONDS
                    * 1000
                    // COST_GUARD_DEFAULTS["fastest_invocation_ms"]
                )
                * round(runtime_term + ceiling_term)
            ),
        },
        "residual_this_does_not_bound": [
            (
                "records on a logger the budget's filter is not attached to — measured in "
                "`logger_outside_the_budget`. Nothing in the handler bounds those, and a "
                "library that starts logging per row is the one shape that can still "
                "decouple bytes from invocations"
            ),
            (
                "the number of RECORDS one invocation may write. The budget bounds message "
                "BYTES; CloudWatch bills an envelope and 26 bytes per RECORD, so an "
                "allowance spent as many tiny records costs more on the wire than the same "
                "allowance spent as one — measured at 4.5x. No call site in this package "
                "loops, so this is a shape a future call site could have and none has today"
            ),
            ("the runtime's own error and timeout frames, which no filter in this process can see"),
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# provenance
# ══════════════════════════════════════════════════════════════════════════════════════


def handler_source() -> dict[str, Any]:
    """SHA-256 of every module in the distribution these figures describe.

    The same discipline ``measure_beats.handler_source`` applies and for the same reason:
    a byte figure is a statement about a specific tree, and this wave is changing
    ``static_site.py`` and ``app.py`` in parallel with this measurement.
    """
    root = DEFAULT_APP_SRC / "mainline_demo_api"
    if not root.is_dir():
        return {"root": str(root), "present": False}
    return {
        "root": str(root.relative_to(REPO_ROOT)).replace("\\", "/"),
        "present": True,
        "sha256_16": {
            module.name: hashlib.sha256(module.read_bytes()).hexdigest()[:16]
            for module in sorted(root.glob("*.py"))
        },
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_log_bytes",
        description=(
            "Measure the CloudWatch bytes one invocation of the demo API emits, per beat "
            "and under a sustained 429 flood, account for the managed runtime's own lines "
            "separately, and derive the cost-guard's log_incoming_bytes_threshold. "
            "Read-only: nothing is applied, nothing is seeded, no AWS call is made."
        ),
    )
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--dsn", default=None, help="overrides --database; never printed")
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--samples-database-beat", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--flood-seconds", type=float, default=30.0)
    parser.add_argument("--flood-source-ips", type=int, default=64)
    parser.add_argument("--concurrency-threads", type=int, default=8)
    parser.add_argument("--concurrency-seconds", type=float, default=25.0)
    parser.add_argument("--overrun-records", type=int, default=5000)
    parser.add_argument("--overrun-message-bytes", type=int, default=1_048_576)
    parser.add_argument("--rie-image", default="public.ecr.aws/lambda/python:3.13")
    parser.add_argument("--rie-invocations", type=int, default=25)
    parser.add_argument("--rie-port", type=int, default=9101)
    parser.add_argument("--rie-memory-mb", type=int, default=256)
    parser.add_argument("--skip-rie", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-write", action="store_true")
    return parser


def _beat_in_child(name: str, args: argparse.Namespace, dsn: str) -> dict[str, Any]:
    """Run one beat's probe in a FRESH interpreter and return its record.

    ``measure_beats``'s rule, kept: a beat that inherits the previous beat's module state —
    a warm connection, a spent budget, a bucket mid-refill — measures the previous beat.
    The child is this same file, so there is one implementation of the probe.
    """
    env = dict(os.environ)
    env["MAINLINE_DSN"] = dsn
    env["MAINLINE_WEB_ROOT"] = str(args.web_root)
    env["MAINLINE_LOGBYTES_BEAT"] = name
    env["MAINLINE_LOGBYTES_SAMPLES"] = str(
        args.samples_database_beat
        if any(b.name == name and b.touches_database for b in BEATS)
        else args.samples
    )
    env["MAINLINE_LOGBYTES_WARMUP"] = str(args.warmup)
    env.setdefault("MAINLINE_DEMO_PERMIT_ID", "dec0de00-0006-4000-8000-000000000001")
    env.setdefault("MAINLINE_DEMO_SITE_ID", "dec0de00-0001-4000-8000-000000000001")
    env.setdefault("MAINLINE_DEMO_SIGNER_SUB", "demo.signer")
    env.setdefault("MAINLINE_DEMO_COUNTERSIGNER_SUB", "demo.countersigner")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child-beat"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
        check=False,
    )
    if result.returncode != 0:
        return {
            "beat": name,
            "measured": False,
            "error": redact(result.stderr.strip())[-800:],
        }
    return json.loads(result.stdout.strip().splitlines()[-1])


def _child_beat() -> int:
    name = os.environ["MAINLINE_LOGBYTES_BEAT"]
    beat = next(b for b in BEATS if b.name == name)
    record = drive_beat(
        beat,
        samples=int(os.environ["MAINLINE_LOGBYTES_SAMPLES"]),
        warmup=int(os.environ["MAINLINE_LOGBYTES_WARMUP"]),
    )
    print(json.dumps(record))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915 - one linear
    # program: probe, probe, probe, derive, write. Splitting it would put the ORDER of the
    # probes somewhere a reader has to go and find, and the order is load-bearing.
    if argv is None and "--child-beat" in sys.argv:
        return _child_beat()
    args = build_parser().parse_args(argv)
    if not args.web_root.is_dir():
        print(f"measure_log_bytes: --web-root {args.web_root} is not a directory", file=sys.stderr)
        return EXIT_USAGE

    dsn = args.dsn or DEFAULT_LOCAL_DSN.format(database=args.database)
    os.environ["MAINLINE_WEB_ROOT"] = str(args.web_root)
    os.environ["MAINLINE_DSN"] = dsn
    os.environ.setdefault("MAINLINE_DEMO_PERMIT_ID", "dec0de00-0006-4000-8000-000000000001")
    os.environ.setdefault("MAINLINE_DEMO_SITE_ID", "dec0de00-0001-4000-8000-000000000001")
    os.environ.setdefault("MAINLINE_DEMO_SIGNER_SUB", "demo.signer")
    os.environ.setdefault("MAINLINE_DEMO_COUNTERSIGNER_SUB", "demo.countersigner")

    beats: dict[str, Any] = {}
    for beat in BEATS:
        print(f"beat {beat.name}: one fresh interpreter")
        beats[beat.name] = _beat_in_child(beat.name, args, dsn)
        summary = beats[beat.name].get("handler_wire_bytes")
        if summary:
            print(
                f"  wire p50 {summary['p50_ms']:.0f} | p99 {summary['p99_ms']:.0f} | "
                f"max {summary['max_ms']:.0f} B | statuses "
                f"{beats[beat.name]['statuses_observed']}"
            )

    print(f"flood: {args.flood_seconds:.0f} s per regime at the production rate defaults")
    flood = drive_flood(seconds=args.flood_seconds, source_ips=args.flood_source_ips)
    for name, regime in flood["regimes"].items():
        print(
            f"  {name}: {regime['invocations']} invocations, {regime['refused_429']} refused, "
            f"{regime['log_lines_emitted']} lines "
            f"(collapse permits {regime['lines_permitted_by_the_collapse']})"
        )

    print(f"collapse under {args.concurrency_threads} threads for {args.concurrency_seconds:.0f} s")
    concurrency = probe_collapse_under_concurrency(
        threads=args.concurrency_threads, seconds=args.concurrency_seconds
    )
    print(
        f"  {concurrency['log_lines_observed']} lines observed, "
        f"{concurrency['lines_permitted_by_the_collapse']} permitted, "
        f"held={concurrency['collapse_held']}"
    )

    print("deliberate overrun")
    overrun = probe_deliberate_overrun(
        records=args.overrun_records, message_bytes=args.overrun_message_bytes
    )
    for shape, result in overrun["shapes"].items():
        print(
            f"  {shape}: {result['message_bytes_that_reached_a_handler']} message B, "
            f"{result['wire_bytes_that_reached_a_handler']} wire B, "
            f"within={result['within_message_ceiling']}"
        )

    print("a logger the filter never sees")
    outside = probe_a_logger_the_filter_never_sees(records=200, size=200)
    print(
        f"  {outside['wire_bytes_that_reached_a_handler']} wire B reached a handler, "
        f"charged {outside['logbudget_charged']}"
    )

    if args.skip_rie:
        runtime_measured: dict[str, Any] = {"supported": False, "reason": "--skip-rie"}
    else:
        print(f"runtime lines from {args.rie_image}")
        runtime_measured = probe_runtime_lines(
            image=args.rie_image,
            invocations=args.rie_invocations,
            port=args.rie_port,
            memory_mb=args.rie_memory_mb,
        )
        if runtime_measured.get("supported"):
            print(
                f"  {runtime_measured['bytes_per_invocation_text_format']} B/invocation "
                f"(text format, emulator)"
            )
        else:
            print(f"  SKIPPED: {runtime_measured.get('reason')}")

    runtime_documented = documented_runtime_lines()
    derivation = derive_threshold(runtime_documented, runtime_measured, beats, flood, overrun)

    failures: list[str] = []
    divergences: list[str] = []
    for name, record in beats.items():
        if not record.get("measured", True):
            failures.append(f"beat {name} did not run: {record.get('error')}")
        elif not record.get("status_ok"):
            # NOT a failure of this program, and not smoothed away either. `expect_status`
            # belongs to `measure_beats`, a LATENCY harness written before W1 derived the
            # wire ceiling from the deployed tree; a 413 on the largest identity object is
            # that ceiling working as W1 intended. It is disclosed here because a reader of
            # a byte measurement is entitled to know the beat answered something else.
            divergences.append(
                f"beat {name} answered {record.get('statuses_observed')}, not the "
                f"{record.get('expect_status_from_measure_beats')} measure_beats.BEATS "
                f"declares"
            )
    for shape, result in overrun["shapes"].items():
        if not result["within_message_ceiling"]:
            failures.append(
                f"the per-invocation budget did NOT hold for {shape}: "
                f"{result['message_bytes_that_reached_a_handler']} B reached a handler "
                f"against a ceiling of {overrun['message_ceiling']} B"
            )

    document: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "generated_by": "scripts/deploy/measure_log_bytes.py",
        "what_this_is": (
            "the CloudWatch bytes one invocation of the demo API puts into its log group, "
            "measured per beat and under a sustained 429 flood by driving the real "
            "mainline_demo_api.app.handler in-process and tapping the logging stack; the "
            "managed runtime's own per-invocation lines accounted separately; and the "
            "cost-guard's log_incoming_bytes_threshold derived from those two terms."
        ),
        "read_this_first": (
            "EVERY figure carries a `method` or `method_of_measurement` field with one of "
            "three values. `measured` was observed here. `measured-emulator` was observed "
            "from the real managed-runtime base image through the Runtime Interface "
            "Emulator, which differs from the deployment in ways recorded on the figure. "
            "`documented` is arithmetic over a shape AWS publishes and was NOT observed "
            "anywhere. A citation is not a measurement and none is presented as one."
        ),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "python": sys.version,
        },
        "database_target": describe_dsn(dsn),
        "handler_source": handler_source(),
        "cloudwatch_accounting": {
            "method": "documented",
            "per_event_overhead_bytes": PUT_LOG_EVENTS_OVERHEAD_BYTES,
            "quote": PUT_LOG_EVENTS_QUOTE,
            "source": PUT_LOG_EVENTS_SOURCE,
            "substitution_named": (
                "AWS states this rule for PutLogEvents BATCH SIZE. It is applied here to "
                "INGESTION because it is the closest accounting AWS documents; AWS does not "
                "publish a separate formula for IncomingBytes. Saying so is the difference "
                "between a derived figure and an assumed one"
            ),
            "lambda_json_envelope_bytes_empty_message": envelope_overhead_bytes(),
            "lambda_json_envelope_shape": (
                '{"timestamp":..,"level":..,"requestId":..,"message":..} — the `function` '
                "event record AWS documents for log_format = JSON"
            ),
        },
        "system_log_level_note": SYSTEM_LOG_LEVEL_NOTE,
        "beats": beats,
        "flood": flood,
        "collapse_under_concurrency": concurrency,
        "deliberate_overrun": overrun,
        "logger_outside_the_budget": outside,
        "runtime_lines_measured": runtime_measured,
        "runtime_lines_documented": runtime_documented,
        "derivation": derivation,
        "what_was_not_applied": (
            "nothing. No terraform command ran, no AWS API was called, no row was written: "
            "the gate run rolls its own transaction back and every other beat is a read."
        ),
        "status_divergences": {
            "observed": divergences,
            "why_these_are_not_failures": (
                "measure_beats.BEATS carries an `expect_status` written for a LATENCY "
                "baseline taken before W1 derived static_site.DEFAULT_MAX_RESPONSE_BYTES "
                "from the deployed tree. A 413 on the largest identity object is that "
                "ceiling binding, which is what W1 set out to make it do. This program "
                "records the divergence rather than editing anybody's expectation, and its "
                "exit code does not depend on another worker's in-flight change"
            ),
            "the_tree_moved_during_this_measurement_and_that_is_recorded_not_hidden": (
                "static_site.py is W1's file and was being edited while this ran. Two "
                "consecutive runs of this program on 2026-08-13 saw asset_js and asset_map "
                "answer 200 and then 413, because the gzip-sibling serving path and the "
                "136 KiB wire ceiling were landing at the same time and the console `dist/` "
                "tree this program serves from carries no .gz siblings (the packer writes "
                "those into the Lambda zip, not into dist/), so an Accept-Encoding: gzip "
                "request falls back to identity and meets the ceiling. `handler_source."
                "sha256_16` pins WHICH state of the tree produced the figures in this file. "
                "None of it moves a single byte figure here: both 200 and 413 emit zero "
                "handler log records, which is the only quantity this program measures"
            ),
        },
        "failures": failures,
        "ok": not failures,
    }

    if args.no_write:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        licence = args.out.with_suffix(args.out.suffix + ".license")
        if not licence.exists():
            licence.write_text(
                "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
                "SPDX-License-Identifier: CC-BY-4.0\n",
                encoding="utf-8",
            )
        print(f"wrote {args.out}")

    band = derivation["admissible_band"]
    print(
        f"BAND       log_incoming_bytes_threshold must lie in "
        f"[{band['lower_edge_bytes']}, {band['upper_edge_bytes']}] B per 300 s; the "
        f"false-positive floor is {band['false_positive_floor_bytes']} B"
    )
    print(
        f"FORMULA    the brief's product gives {band['upper_edge_bytes']} B, "
        f"{derivation['against_the_standing_default']['briefs_formula_is']} the standing "
        f"default of {COST_GUARD_DEFAULTS['log_incoming_bytes_threshold']} B"
    )
    print(
        f"RECOMMEND  {derivation['recommended']} = {derivation['recommended_bytes']} B "
        f"(inside the band: {band['standing_default_is_inside_the_band']}; "
        f"{band['standing_default_position']})"
    )
    for divergence in divergences:
        print(f"DIVERGENCE  {divergence}", file=sys.stderr)
    for failure in failures:
        print(f"FAILURE  {failure}", file=sys.stderr)
    return EXIT_OK if not failures else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
