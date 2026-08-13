# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Interface **I5**: the bytes one invocation may log, and the lines it may repeat.

WHY THIS IS A COST FILE AND NOT A LOGGING FILE
-----------------------------------------------
`docs/leads/cost-bound-plan.md` §0.4 states the fact this module exists for: **a CloudWatch
log group has retention, not a quota.** ``log_retention_days = 7`` bounds *storage* and
bounds *ingestion* — the charged term, billed on arrival — not at all. So a log line on the
refusal path is a second bill, spent inside the control that exists to prevent the first
one, and invisible in every egress figure this project has published.

The two mechanisms are separate and this file tests them separately:

* **the collapse** (:func:`mainline_demo_api.logbudget.claim`) — a *pre-record* gate, asked
  before a :class:`logging.LogRecord` exists, so a suppressed line costs a dict lookup
  rather than a record and a format. This is what keeps the 429 path — the hottest path in
  the function under a flood — from writing a line per refusal;
* **the ceiling** (the :class:`logging.Filter`) — the hard per-invocation byte bound, at
  the exit, applying to every record on the ``mainline_demo_api`` logger whether or not its
  author knew this module existed.

**The collapse degrades to the ceiling and never to nothing**, which is asserted below:
when the collapse map is full :func:`claim` answers ``True``, because the byte bound is the
guarantee and a full map must not be able to silence an error nobody has seen yet.

WHAT IS NOT BOUNDED HERE, SO NOBODY LOOKS FOR IT
-------------------------------------------------
The Lambda platform's own ``START`` / ``END`` / ``REPORT`` / ``INIT_START`` lines are
written by the runtime, not by this logger, and no filter in this process can see them.
They are W6's surface (``system_log_level``). Neither is the invocation charge: Lambda
bills a dropped log line exactly as it bills a written one.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from mainline_demo_api import app, logbudget, ratelimit, static_site

_LOGGER: Final = logging.getLogger("mainline_demo_api")

_INDEX: Final = "<!doctype html><html><head><title>MAINLINE</title></head><body>ok</body></html>"


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """A fresh allowance and an empty collapse map before and after each test.

    Both modules hold module-scope state on purpose — a budget rebuilt per *test* is the
    same category error as a token bucket rebuilt per *request* — so the state has to be
    handed back in the shape the next test module expects to find it.
    """
    logbudget.reset()
    ratelimit.reset()
    yield
    logbudget.reset()
    ratelimit.configure()
    ratelimit.reset()


@pytest.fixture(autouse=True)
def _audible(caplog: pytest.LogCaptureFixture) -> None:
    """Records must reach a handler for any of this to be observable."""
    caplog.set_level(logging.DEBUG, logger="mainline_demo_api")


def _raise_with_a_long_detail() -> None:
    """Raise from a real frame, so the formatted traceback is a real traceback.

    The budget's job on this path is to truncate ``exc_text``, and ``exc_text`` is only
    interesting when there is a stack under it.
    """
    raise ValueError("a detail string that is itself " + "long " * 200)


def _event(path: str = "/v1/nope", *, ip: str | None = None) -> dict[str, Any]:
    http: dict[str, Any] = {"method": "GET", "path": path}
    if ip is not None:
        http["sourceIp"] = ip
    return {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": http},
    }


# ── (a) The ceiling: bytes per invocation ───────────────────────────────────────────


def test_the_filter_is_installed_on_the_logger_the_handler_actually_uses() -> None:
    """Installed at import of ``app``, not on the first request.

    A cold start is exactly when this handler logs — a missing DSN, a failed import, a
    connection that will not open — so a ceiling armed by the first *invocation* would
    leave the first invocation unbounded.
    """
    assert app.logbudget is logbudget
    assert any(type(f).__name__ == "_Ceiling" for f in _LOGGER.filters), _LOGGER.filters


def test_the_per_invocation_byte_cap_holds(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Two hundred records against a 512-byte allowance, and the allowance holds."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "512")
    logbudget.begin()

    for index in range(200):
        _LOGGER.warning("a line that is sixty-four bytes long, number %04d", index)

    assert logbudget.used() <= 512 + logbudget.OVERRUN_BOUND
    assert logbudget.dropped() > 150
    emitted = sum(len(record.getMessage().encode("utf-8")) for record in caplog.records)
    assert emitted <= 512 + logbudget.OVERRUN_BOUND, f"{emitted} B reached a handler"


def test_the_record_that_hits_the_ceiling_says_so_rather_than_vanishing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A budget that silently ate the record it stopped on would be indistinguishable from
    a handler that had nothing to say, which is the worst possible failure for a log."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "64")
    logbudget.begin()

    for index in range(20):
        _LOGGER.warning("filling the allowance, line %d", index)

    notices = [r for r in caplog.records if "log budget exhausted" in r.getMessage()]
    assert len(notices) == 1, "the notice must be emitted exactly once per invocation"
    assert logbudget.BUDGET_BYTES_ENV in notices[0].getMessage()
    assert "64" in notices[0].getMessage()
    assert caplog.records[-1] is notices[0], "records after the notice were not dropped"


def test_a_new_invocation_gets_a_new_allowance(monkeypatch: pytest.MonkeyPatch) -> None:
    """``begin`` is per invocation, which is the unit CloudWatch ingestion is driven by."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "128")
    logbudget.begin()
    for index in range(50):
        _LOGGER.warning("first invocation %d", index)
    first = logbudget.used()
    assert first >= 128

    logbudget.begin()
    assert logbudget.used() == 0
    assert logbudget.dropped() == 0
    _LOGGER.warning("second invocation")
    assert 0 < logbudget.used() < first


def test_the_bytes_charged_are_the_bytes_of_the_formatted_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Charged on what is emitted, not on the template, and measured in UTF-8 bytes.

    The distinction is not pedantry: ``%s`` is two characters and its argument may be four
    hundred, and CloudWatch bills the second number. A non-ASCII detail string is billed in
    bytes, not characters, which is why this is an ``encode`` and not a ``len``.
    """
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "4096")
    logbudget.begin()
    _LOGGER.warning("permit %s refused", "ü" * 10)

    formatted = "permit " + "ü" * 10 + " refused"
    assert len(formatted) == 25, "twenty-five characters…"
    assert len(formatted.encode("utf-8")) == 35, "…and thirty-five bytes"
    assert logbudget.used() == 35, "the budget charged characters, not bytes"


def test_an_over_long_message_is_clipped_before_it_is_charged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """One record must not be able to spend a whole invocation's allowance by itself."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "4096")
    logbudget.begin()
    _LOGGER.warning("%s", "z" * 100_000)

    message = caplog.records[-1].getMessage()
    assert len(message) < logbudget.MESSAGE_LIMIT + 64
    assert "100000 characters, clipped" in message
    assert logbudget.used() < logbudget.MESSAGE_LIMIT + 64


def test_a_traceback_is_truncated_to_the_room_that_is_left(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``log.exception`` is the biggest thing this handler can emit, so it is the test.

    The filter formats ``exc_info`` itself and stores the result in ``exc_text`` — which is
    the attribute :class:`logging.Formatter` reuses — so the traceback is measurable before
    any handler sees it and is formatted exactly once.
    """
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "300")
    logbudget.begin()
    try:
        _raise_with_a_long_detail()
    except ValueError:
        _LOGGER.exception("read permit raised")

    record = caplog.records[-1]
    assert record.exc_text is not None
    assert record.exc_text.endswith(logbudget.TRUNCATION_MARKER)
    assert logbudget.used() <= 300 + logbudget.OVERRUN_BOUND


def test_a_stack_info_attachment_is_charged_and_truncated_like_a_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``stack_info=True`` is the SECOND thing a ``Formatter`` appends, and it was free.

    MEASURED, not imagined. ``scripts/deploy/measure_log_bytes.py`` drove eight
    ``log.warning(..., stack_info=True)`` records through this filter at the 4,096-byte
    default on 2026-08-13 and recorded **9,776 bytes reaching a handler against a charge of
    224** — a 44x under-count, and not one record dropped, because ``record.stack_info``
    never entered ``spent`` and so never moved ``_used`` towards the limit. Every downstream
    :class:`logging.Formatter` appends it exactly as it appends ``exc_text``, so every one
    of those bytes was billed by CloudWatch and none of them was budgeted.

    It arrives by its own route: any call site may pass ``stack_info=True``, and so may
    ``log.error`` and ``log.exception``, which is the same unenumerable set of call sites
    the module docstring says this filter exists for.
    """
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "512")
    logbudget.begin()
    caplog.clear()

    _emit_with_stacks()

    reached = sum(_record_bytes(record) for record in caplog.records)
    assert logbudget.used() <= 512 + logbudget.OVERRUN_BOUND
    assert reached <= 512 + logbudget.OVERRUN_BOUND, f"{reached} B reached a handler"
    truncated = [
        r for r in caplog.records if r.stack_info and logbudget.TRUNCATION_MARKER in r.stack_info
    ]
    assert truncated, "a stack larger than the room left must carry the truncation marker"


def _emit_with_stacks(depth: int = 40) -> None:
    """Emit eight ``stack_info=True`` records from *depth* frames down.

    Split out so the recursion is the fixture and the assertion is the test. The depth
    matters: ``stack_info`` is the formatted stack of the CALL SITE, so a shallow frame
    produces a short attachment and would not exercise the truncation this exists to prove.
    """

    def descend(level: int) -> None:
        if level == 0:
            for index in range(8):
                _LOGGER.warning("a line with a stack attached, number %d", index, stack_info=True)
            return
        descend(level - 1)

    descend(depth)


def _record_bytes(record: logging.LogRecord) -> int:
    """Every byte of one record a :class:`logging.Formatter` would emit, in UTF-8.

    The message, the exception text and the stack text — the three parts
    :meth:`logging.Formatter.format` concatenates. Counting only the message is how a
    ``stack_info`` attachment stayed invisible for as long as it did, so this helper counts
    all three and the tests below weigh what a handler actually received.
    """
    total = len(record.getMessage().encode("utf-8", "replace"))
    if record.exc_text:
        total += len(record.exc_text.encode("utf-8", "replace"))
    if record.stack_info:
        total += len(record.stack_info.encode("utf-8", "replace"))
    return total


def _overrun_shapes() -> dict[str, Any]:
    """The four ways a per-invocation byte ceiling can be defeated, as callables.

    Each is a *whole invocation's worth* of abuse, and they are kept apart rather than run
    back to back for a reason the negative control taught rather than the code: the
    allowance is shared, so a shape that runs second against an already-exhausted budget
    takes the ``_used >= _limit`` branch — which clears ``exc_info``, ``exc_text`` and
    ``stack_info`` on its way past — and is therefore never measured at all. A single
    invocation cannot falsify four mechanisms; four invocations can.
    """

    def loop(log: logging.Logger) -> None:
        for index in range(2000):
            log.warning("an ordinary line in a loop, number %06d", index)

    def one_huge_message(log: logging.Logger) -> None:
        log.warning("%s", "z" * (256 * 1024))

    def exceptions(log: logging.Logger) -> None:
        def deep(level: int) -> None:
            if level == 0:
                raise ValueError("a detail string that is itself " + "long " * 400)
            deep(level - 1)

        for _ in range(8):
            try:
                deep(40)
            except ValueError:
                log.exception("read %s raised", "demo.permit")

    def stacks(log: logging.Logger) -> None:  # noqa: ARG001 - shape parity; see below
        _emit_with_stacks()

    return {
        "a_call_site_in_a_loop": loop,
        "one_message_larger_than_the_allowance": one_huge_message,
        "log_exception_with_a_deep_stack": exceptions,
        "stack_info_true": stacks,
    }


@pytest.mark.parametrize("shape", sorted(_overrun_shapes()))
def test_the_budget_holds_against_a_deliberate_overrun(
    shape: str, caplog: pytest.LogCaptureFixture
) -> None:
    """THE FALSIFICATION. Emit far more than the allowance and weigh what got out.

    This is the test the bound is worth having. Everything else in this file checks one
    mechanism from the inside; this one asks the only question a cost control has to answer
    — *if a call site tries as hard as it can, how many bytes reach CloudWatch?* — and
    answers it by weighing every part of every record that reached a handler, rather than by
    trusting :func:`logbudget.used`, which is the very number under test. A budget that
    under-counts what it lets out is not a bound, and only weighing the exit can tell the
    two apart; the last assertion below is exactly that check.

    Four shapes, one invocation each (see :func:`_overrun_shapes` for why they cannot
    share one), and each defeats a *different* mechanism:

    ============================================  =========================================
    ``a_call_site_in_a_loop``                     the byte ceiling itself
    ``one_message_larger_than_the_allowance``     :func:`clip` and ``MESSAGE_LIMIT``
    ``log_exception_with_a_deep_stack``           the ``exc_text`` truncation
    ``stack_info_true``                           the ``stack_info`` truncation
    ============================================  =========================================

    **OBSERVED GOING RED on 2026-08-13, both truncations, one at a time.**

    * ``if record.stack_info:`` block deleted → ``stack_info_true`` fails with
      **49,184 B reaching a handler against a 5,043 B ceiling, 8 records admitted and 0
      dropped** — nothing was even refused, because those bytes never entered ``spent`` and
      so never moved ``_used`` towards the limit. That is the defect
      ``scripts/deploy/measure_log_bytes.py`` measured independently at 9,776 B out against
      a 224 B charge before the block existed.
    * ``if record.exc_text:`` block deleted → ``log_exception_with_a_deep_stack`` fails
      with **23,496 B against the same 5,043 B ceiling**, 8 admitted and 0 dropped.

    Neither control was inferred from reading the filter. Each was applied to
    ``logbudget.py``, run, observed red, and reverted. A falsification nobody has watched
    fail is a decoration.
    """
    emit = _overrun_shapes()[shape]
    logbudget.begin()
    caplog.clear()
    emit(_LOGGER)

    ceiling = logbudget.DEFAULT_BUDGET_BYTES + logbudget.OVERRUN_BOUND
    reached = sum(_record_bytes(record) for record in caplog.records)
    assert reached <= ceiling, (
        f"{shape}: {reached} B reached a handler against a ceiling of {ceiling} B "
        f"({len(caplog.records)} records admitted, {logbudget.dropped()} dropped)"
    )
    assert logbudget.used() <= ceiling, "the budget's own accounting exceeded the ceiling"
    assert logbudget.used() >= reached - logbudget.OVERRUN_BOUND, (
        f"{shape}: the budget charged {logbudget.used()} B for {reached} B that reached a "
        "handler. An accounting that under-counts what it lets out is not a bound — it is "
        "the shape the stack_info defect had, and it is invisible to any assertion that "
        "reads `used()` instead of weighing the exit"
    )


def test_a_broken_format_string_is_logged_rather_than_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A mistyped log line is a bug in a call site, not a failed invocation — and not a
    second, unbudgeted write to CloudWatch either.

    ``getMessage`` raises when the arguments do not match the template. Raising that out of
    a filter would turn a typo into a 502 with no body, from inside a cost control. Merely
    *surviving* it in the filter is not enough: the record would raise again in the next
    ``Formatter``, and ``logging.Handler.handleError`` answers that by printing a traceback
    to ``stderr``, which on Lambda is CloudWatch, unbudgeted, on every such call. So the
    record is rewritten into something formattable, which this test asserts by formatting
    it — ``caplog``'s handler re-raises formatting failures rather than swallowing them,
    so a record that could still blow up would fail here.
    """
    logbudget.begin()
    _LOGGER.warning("two placeholders %s %s", "only-one")  # noqa: PLE1206 - the defect
    # under test: a template with two placeholders and one argument. Ruff is right about
    # the call site and this call site is the fixture.

    record = caplog.records[-1]
    assert record.args == ()
    assert "two placeholders %s %s" in record.getMessage()
    assert "unformattable log call" in record.getMessage()
    assert logbudget.used() > 0


# ── (b) Configuration: a bad value falls back, never to unbounded ────────────────────


@pytest.mark.parametrize(
    "value",
    ["banana", "", "  ", "0", "-1", "1.5", "0x40", "inf", "nan"],
    ids=["garbage", "empty", "whitespace", "zero", "negative", "float", "hex", "inf", "nan"],
)
def test_a_malformed_budget_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, value)
    logbudget.begin()
    for index in range(2000):
        _LOGGER.warning("line %d", index)
    assert logbudget.used() <= logbudget.DEFAULT_BUDGET_BYTES + logbudget.OVERRUN_BOUND
    assert logbudget.dropped() > 0


def test_an_absurd_budget_falls_back_rather_than_removing_the_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rule as ``ratelimit``: an environment variable may lower this, not remove it."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, str(logbudget.MAX_BUDGET_BYTES + 1))
    logbudget.begin()
    for index in range(5000):
        _LOGGER.warning("line %d", index)
    assert logbudget.used() <= logbudget.DEFAULT_BUDGET_BYTES + logbudget.OVERRUN_BOUND


def test_a_budget_that_does_parse_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fallback tests only mean something if the happy path reads the variable."""
    monkeypatch.setenv(logbudget.BUDGET_BYTES_ENV, "1024")
    logbudget.begin()
    for index in range(500):
        _LOGGER.warning("line %d", index)
    assert 1024 <= logbudget.used() <= 1024 + logbudget.OVERRUN_BOUND


@pytest.mark.parametrize("value", ["banana", "", "0", "-3", "inf", "nan"], ids=list("abcdef"))
def test_a_malformed_collapse_window_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(logbudget.COLLAPSE_SECONDS_ENV, value)
    assert logbudget.claim("probe") is True
    assert logbudget.claim("probe") is False, "an unbounded window would admit both"


# ── (c) The collapse ────────────────────────────────────────────────────────────────


def test_a_call_site_speaks_once_per_window_and_then_is_silent() -> None:
    assert logbudget.claim("k", window=60.0) is True
    for _ in range(10_000):
        assert logbudget.claim("k", window=60.0) is False
    assert logbudget.collapsed() == 10_000


def test_the_window_reopens() -> None:
    """A zero-length window is the degenerate case and it must reopen every time."""
    assert logbudget.claim("k", window=0.0) is True
    assert logbudget.claim("k", window=0.0) is True


def test_two_call_sites_do_not_silence_each_other() -> None:
    assert logbudget.claim("ratelimit.ip", window=60.0) is True
    assert logbudget.claim("ratelimit.global", window=60.0) is True
    assert logbudget.claim("ratelimit.ip", window=60.0) is False


def test_the_collapse_map_is_bounded_and_a_full_map_degrades_to_the_ceiling() -> None:
    """Bounded, because a key a caller could influence would otherwise grow it forever.

    And when it is full it answers ``True`` — it stops *collapsing*, it does not start
    *silencing*. The byte ceiling is the guarantee; the collapse is only the cheap way to
    stay well inside it, so the safe direction on exhaustion is to let the line through and
    let the ceiling weigh it.
    """
    for index in range(logbudget.MAX_CLAIM_KEYS * 4):
        logbudget.claim(f"site-{index}", window=3600.0)
    assert len(logbudget._CLAIMS) == logbudget.MAX_CLAIM_KEYS  # the bound IS the subject

    assert logbudget.claim("a-site-that-has-never-spoken", window=3600.0) is True


# ── (d) `clip`: a caller-derived string never reaches a record whole ─────────────────


def test_clip_truncates_and_names_what_it_truncated() -> None:
    assert logbudget.clip("short") == "short"
    clipped = logbudget.clip("y" * 5000, 20)
    assert clipped.startswith("y" * 20)
    assert "5000 characters, clipped" in clipped
    assert len(clipped) < 60


def test_clip_accepts_a_value_that_is_not_a_string() -> None:
    """It is a guard on the way into a log record, and the thing being guarded may be
    anything a caller put in a JSON body."""
    assert logbudget.clip(None) == "None"
    assert logbudget.clip(12345, 2).startswith("12")


# ── (e) Wired together: the 429 path is the one this exists for ─────────────────────


def test_a_flood_writes_one_throttle_line_per_bucket_refill_window(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The whole point, measured through the real handler.

    Four thousand refused requests. Without the collapse that is four thousand records at
    roughly seventy bytes each on the hottest path in the function; with it, one line per
    bucket refill window, carrying the running count so nothing is lost but the repetition.
    """
    ratelimit.configure(global_rps=0.01, global_burst=2, ip_rps=0.01, ip_burst=1)
    caplog.clear()

    codes = [int(app.handler(_event(ip="198.51.100.9"))["statusCode"]) for _ in range(4000)]
    assert codes.count(429) > 3900

    throttle = [r for r in caplog.records if "rate limit engaged" in r.getMessage()]
    assert 1 <= len(throttle) <= len(ratelimit.refusals()), (
        f"{len(throttle)} throttle lines for {codes.count(429)} refusals"
    )
    assert logbudget.collapsed() > 3900
    assert "refusals=" in throttle[0].getMessage()


def test_the_throttle_line_clips_the_caller_derived_field(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``sourceIp`` is AWS's field on a real Function URL and a caller's on a local one.

    Either way it is the only caller-derived value that reaches a log record from this
    path, so it is clipped on the way in rather than trusted to be short.
    """
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    caplog.clear()
    long_address = "b" * 4096
    app.handler(_event(ip=long_address))
    app.handler(_event(ip=long_address))

    throttle = [r for r in caplog.records if "rate limit engaged" in r.getMessage()]
    assert throttle, "the first refusal in a window must be logged"
    message = throttle[-1].getMessage()
    assert long_address not in message
    assert len(message) < 200


def test_the_refused_response_is_not_what_is_being_bounded_here(tmp_path: Path) -> None:
    """A sanity fence between the two controls: the 429 body is ``ratelimit``'s number.

    ``logbudget`` bounds what goes to CloudWatch; it must never be read as bounding what
    goes to the caller. Both are asserted, in their own files, against their own ceilings —
    and this one line is here so a reader of either file cannot conflate them.
    """
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    assert static_site.max_response_bytes() > 0

    app.handler(_event("/v1/nope"))
    refusal = app.handler(_event("/v1/nope"))
    assert refusal["statusCode"] == 429
    assert len(str(refusal["body"]).encode("utf-8")) < ratelimit.REFUSAL_BODY_CEILING
    assert json.loads(refusal["body"])["error"]["kind"] == "rate_limited"
