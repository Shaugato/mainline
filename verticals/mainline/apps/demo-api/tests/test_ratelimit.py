# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The rate bound at the door: that it binds, where it stops binding, and that it is real.

This file exists because of a finding, not because of a style. Two independent adversarial
verifications reported that **nothing in this repository bounded the request rate of a
public Lambda Function URL with** ``authorization_type = NONE``; the only bound in force
was an AWS account concurrency quota of 10 that nobody chose and that AWS marks
``Adjustable: true``. :mod:`mainline_demo_api.ratelimit` is the mechanism; this file is the
part that makes the mechanism a claim somebody can check.

THE ONE TEST THAT MATTERS MOST IS THE ONE THAT DELETES THE CONTROL
------------------------------------------------------------------
``test_removing_the_check_from_app_py_puts_the_flood_back_to_200`` reads
``app.py`` off disk, deletes the three lines that call
:func:`mainline_demo_api.ratelimit.check`, executes the result as a module, and runs the
**same flood** through it. The unmutated handler answers 429; the mutated one answers 200
for every request. A control whose removal changes no test result is not being tested — it
is being described — and that is precisely the defect class this wave was convened to
close: a test that cannot disagree with the code it tests proves nothing.

WHAT IS DELIBERATELY NOT ASSERTED HERE
--------------------------------------
That the limiter saves money. It does not, on its own: Lambda bills a 429 exactly like a
200, and refusing early *shortens* the invocation, which at a fixed concurrency ceiling
**raises** the number of billed invocations. What it bounds is egress bytes and work — see
the module docstring, which says so at length — and the bill is bounded by W5's cost-guard
responder. Nothing in this file should be quoted as evidence of a spend bound.
"""

from __future__ import annotations

import json
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest
from mainline_demo_api import app, logbudget, ratelimit, static_site

#: The exact three lines ``app.handler`` uses to consult the limiter. The falsification
#: test deletes this literal, so if somebody reformats the block the test fails loudly
#: rather than quietly mutating nothing and passing — a falsification that falsifies
#: nothing is worse than no falsification, because it reads as proof.
_GUARD: Final = (
    "    refused = ratelimit.check(event)\n    if refused is not None:\n        return refused\n"
)

_INDEX: Final = "<!doctype html><html><head><title>MAINLINE</title></head><body>ok</body></html>"


# ── Fixtures ────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """Refill both buckets before and after every test in this file.

    **After** matters as much as before. The buckets are module-scope by design — a bucket
    rebuilt per invocation is full on every request and bounds nothing — so a test that
    drained them and walked away would hand the next test module in the session a limiter
    with no tokens in it. That is not a defect in the limiter; it is the difference between
    one execution environment and one pytest process, and this fixture is where the
    difference is paid.
    """
    ratelimit.reset()
    logbudget.reset()
    yield
    ratelimit.configure()
    ratelimit.reset()
    logbudget.reset()


@pytest.fixture
def web_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A bundled site, so ``GET /`` is a 200 and a flood has something to be refused from."""
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_bytes(_INDEX.encode("utf-8"))
    monkeypatch.setenv(static_site.WEB_ROOT_ENV, str(root))
    return root


def _event(path: str = "/v1/nope", *, method: str = "GET", ip: str | None = None) -> dict[str, Any]:
    http: dict[str, Any] = {"method": method, "path": path}
    if ip is not None:
        http["sourceIp"] = ip
    return {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"stage": "$default", "http": http},
    }


def _codes(count: int, **kwargs: Any) -> list[int]:
    """*count* invocations of the real handler, as status codes.

    The default path is ``/v1/nope``, which answers **404** and needs neither a bundled
    site nor a database — so a status of 404 in the lists below reads "admitted", and the
    tests that need a real 200 ask for ``/`` and take the ``web_root`` fixture.
    """
    return [int(app.handler(_event(**kwargs))["statusCode"]) for _ in range(count)]


# ── (a) The bucket: it refills, and burst is a separate knob from rate ───────────────


def test_a_bucket_refills_at_its_declared_rate() -> None:
    """The arithmetic, on an injected clock, so nothing here depends on how fast CI is.

    ``_Bucket.take`` takes ``now`` as an argument rather than reading the clock itself, and
    this test is the reason: refill is a statement about elapsed time, and a statement
    about elapsed time tested with :func:`time.sleep` is a statement about the scheduler.
    """
    bucket = ratelimit._Bucket(rate=4.0, capacity=2)  # the injected-clock seam

    assert bucket.take(100.0) is True
    assert bucket.take(100.0) is True
    assert bucket.take(100.0) is False, "capacity was 2 and three were taken"

    # 0.2 s at 4 tokens/s is 0.8 of a token: closer, and still not one.
    assert bucket.take(100.2) is False
    # 0.5 s from empty is 2.0 tokens, which is also the capacity: refill, then spend one.
    assert bucket.take(100.5) is True
    assert bucket.tokens == pytest.approx(1.0)


def test_a_bucket_never_refills_above_its_capacity() -> None:
    """An idle century must not buy a century's burst. This is why ``capacity`` exists."""
    bucket = ratelimit._Bucket(rate=1000.0, capacity=3)  # see above
    bucket.refill(0.0)
    assert bucket.refill(1_000_000.0) == pytest.approx(3.0)


def test_a_refill_is_visible_through_the_real_handler_on_the_real_clock() -> None:
    """The integration form: drain it, wait, and the door opens again by itself.

    Deliberately a *fast* bucket — 40 tokens a second — so the wait is 150 ms rather than a
    second, and still 25 ms per token, which is two orders of magnitude more than one
    invocation of this handler costs in-process. The unit test above owns the exact
    arithmetic; this one owns the claim that the thing wired into ``handler`` is the thing
    that was measured.
    """
    ratelimit.configure(global_rps=40.0, global_burst=2, ip_rps=40.0, ip_burst=2)
    assert _codes(3) == [404, 404, 429]

    time.sleep(0.15)  # six tokens' worth at 40/s; the capacity of 2 is the cap.
    assert _codes(3) == [404, 404, 429]


def test_the_burst_is_admitted_whole_and_the_next_request_is_refused(web_root: Path) -> None:
    """Burst is a separate knob because a page load is a burst.

    A judge clicking the demo URL fetches ``index.html`` and its hashed assets in one go.
    A bucket sized to the sustained rate would refuse the console's own bundle on the first
    click — a cost control that broke the thing it was protecting. So: seventeen at once,
    all served, the eighteenth refused, with the refill rate set low enough that nothing
    trickles back during the test.
    """
    assert web_root.is_dir()
    ratelimit.configure(global_rps=0.01, global_burst=17, ip_rps=0.01, ip_burst=1000)
    codes = _codes(25, path="/", ip="203.0.113.4")
    assert codes[:17] == [200] * 17
    assert set(codes[17:]) == {429}


# ── (b) The two layers, and the order they are consulted in ─────────────────────────


def test_one_abusive_address_cannot_spend_the_whole_instances_budget() -> None:
    """Per-IP is checked FIRST, and that ordering is the whole point of having it.

    If the global bucket were consulted first, a single address could empty the shared
    budget on requests the per-IP layer was about to refuse anyway — the control handing
    the attacker a denial of service against everybody else. Checked in this order, an
    abuser burns its own tokens and the next caller is still served.
    """
    ratelimit.configure(global_rps=0.01, global_burst=20, ip_rps=0.01, ip_burst=3)

    noisy = _codes(12, ip="198.51.100.1")
    assert noisy[:3] == [404, 404, 404]
    assert set(noisy[3:]) == {429}

    # Nine of the twelve never reached the global bucket, so it still holds 17 tokens.
    assert _codes(1, ip="198.51.100.2") == [404]
    assert ratelimit.refusals()["global"] == 0


def test_the_scope_in_the_refusal_says_which_layer_refused() -> None:
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    assert _codes(1, ip="192.0.2.10") == [404]

    same_caller = app.handler(_event(ip="192.0.2.10"))
    assert json.loads(same_caller["body"])["error"]["scope"] == "ip"

    other_caller = app.handler(_event(ip="192.0.2.11"))
    assert json.loads(other_caller["body"])["error"]["scope"] == "global"


def test_an_event_with_no_source_address_still_meets_the_global_bucket() -> None:
    """A missing ``sourceIp`` is a local harness or a test, and it is not a bypass."""
    ratelimit.configure(global_rps=0.01, global_burst=2, ip_rps=0.01, ip_burst=1)
    assert _codes(3) == [404, 404, 429]
    assert ratelimit.key_count() == 0


# ── (c) The key map is bounded, and full does not mean open ─────────────────────────


def test_the_per_ip_map_cannot_be_grown_without_limit_by_rotating_addresses() -> None:
    """Three times the capacity in distinct addresses, and the map holds exactly the bound.

    This is the memory half of the same threat the buckets answer: an attacker who cannot
    exhaust the tokens can still try to exhaust the *map*, and a per-IP limiter keyed on an
    unbounded dict is a denial of service with extra steps.
    """
    ratelimit.configure(global_rps=1e-6, global_burst=1, ip_rps=1e-6, ip_burst=1)
    for index in range(ratelimit.MAX_KEYS * 3):
        app.handler(_event(ip=f"10.{index // 65536 % 256}.{index // 256 % 256}.{index % 256}"))
    assert ratelimit.key_count() == ratelimit.MAX_KEYS


def test_when_the_map_is_full_a_new_address_falls_back_to_the_global_bucket() -> None:
    """Full must not mean admitted. The plain-LRU version of this is the free-reset bug.

    With a naive LRU, an attacker rotating source addresses would evict a drained bucket
    and receive a brand-new full one on every request — the per-IP layer defeated at zero
    cost. Here, a bucket below capacity carries debt and is never evicted, so the arrival
    falls through to the global bucket, which is empty, and is refused with ``scope:
    global`` rather than served.
    """
    ratelimit.configure(global_rps=1e-6, global_burst=1, ip_rps=1e-6, ip_burst=1)
    for index in range(ratelimit.MAX_KEYS):
        app.handler(_event(ip=f"10.{index // 256 % 256}.{index % 256}.1"))
    assert ratelimit.key_count() == ratelimit.MAX_KEYS

    newcomer = app.handler(_event(ip="203.0.113.200"))
    assert newcomer["statusCode"] == 429
    assert json.loads(newcomer["body"])["error"]["scope"] == "global"
    assert ratelimit.key_count() == ratelimit.MAX_KEYS


def test_a_replenished_entry_is_reclaimed_so_the_map_does_not_freeze_forever() -> None:
    """The other half: bounded must not mean permanently owned by whoever arrived first.

    A bucket back at capacity is indistinguishable from one that never existed, so
    discarding it loses nothing and its owner is treated exactly as a first-time caller.
    Without this the map would be a fixed set of addresses chosen by whoever raced to it.
    """
    ratelimit.configure(global_rps=1e6, global_burst=1_000_000, ip_rps=1e6, ip_burst=2)
    for index in range(ratelimit.MAX_KEYS):
        app.handler(_event(ip=f"10.{index // 256 % 256}.{index % 256}.2"))
    assert ratelimit.key_count() == ratelimit.MAX_KEYS

    assert app.handler(_event(ip="203.0.113.201"))["statusCode"] == 404
    assert ratelimit.key_count() == ratelimit.MAX_KEYS
    assert "203.0.113.201" in ratelimit._PER_IP  # the map IS what this test is about


def test_a_caller_cannot_choose_the_length_of_a_map_key() -> None:
    """AWS writes ``sourceIp`` on a real Function URL; a local harness is not AWS."""
    ratelimit.configure(global_rps=1e6, global_burst=1_000_000, ip_rps=1e6, ip_burst=10)
    app.handler(_event(ip="a" * 4096))
    assert max(len(key) for key in ratelimit._PER_IP) <= ratelimit.IP_KEY_LIMIT


# ── (d) Configuration: a bad value falls back to the default, never to unbounded ─────


@pytest.mark.parametrize(
    "value",
    ["banana", "", "   ", "0", "-1", "-0.5", "inf", "-inf", "nan", "1e400", "0x10", "1,5"],
    ids=[
        "garbage",
        "empty",
        "whitespace",
        "zero",
        "negative",
        "negative-fraction",
        "infinity",
        "negative-infinity",
        "not-a-number",
        "overflows-to-inf",
        "hexadecimal",
        "european-decimal",
    ],
)
@pytest.mark.parametrize(
    ("variable", "attribute", "default"),
    [
        (ratelimit.GLOBAL_RPS_ENV, "global_rps", ratelimit.DEFAULT_GLOBAL_RPS),
        (ratelimit.GLOBAL_BURST_ENV, "global_burst", ratelimit.DEFAULT_GLOBAL_BURST),
        (ratelimit.IP_RPS_ENV, "ip_rps", ratelimit.DEFAULT_IP_RPS),
        (ratelimit.IP_BURST_ENV, "ip_burst", ratelimit.DEFAULT_IP_BURST),
    ],
    ids=["global-rps", "global-burst", "ip-rps", "ip-burst"],
)
def test_a_malformed_value_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, variable: str, attribute: str, default: float, value: str
) -> None:
    """``inf`` and ``nan`` are in this list on purpose: both *parse*.

    A bare ``try: float(...)`` would accept ``inf`` and produce a bucket that never empties
    — a limiter that is off, switched off by an environment variable, which is exactly what
    the module docstring promises cannot happen. ``1e400`` is the same defect arriving
    through overflow rather than through a keyword.
    """
    monkeypatch.setenv(variable, value)
    assert getattr(ratelimit.configure(), attribute) == default


@pytest.mark.parametrize(
    ("variable", "attribute", "default"),
    [
        (ratelimit.GLOBAL_RPS_ENV, "global_rps", ratelimit.DEFAULT_GLOBAL_RPS),
        (ratelimit.GLOBAL_BURST_ENV, "global_burst", ratelimit.DEFAULT_GLOBAL_BURST),
        (ratelimit.IP_RPS_ENV, "ip_rps", ratelimit.DEFAULT_IP_RPS),
        (ratelimit.IP_BURST_ENV, "ip_burst", ratelimit.DEFAULT_IP_BURST),
    ],
    ids=["global-rps", "global-burst", "ip-rps", "ip-burst"],
)
def test_an_absurdly_large_value_falls_back_rather_than_disarming_the_limiter(
    monkeypatch: pytest.MonkeyPatch, variable: str, attribute: str, default: float
) -> None:
    """A number that large is not a rate limit; it is the absence of one, spelled out."""
    monkeypatch.setenv(variable, "999999999999")
    assert getattr(ratelimit.configure(), attribute) == default


def test_no_environment_at_all_still_leaves_a_limiter_in_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interface I3 has four variables and W6 publishes them; none of them is required."""
    for variable in (
        ratelimit.GLOBAL_RPS_ENV,
        ratelimit.GLOBAL_BURST_ENV,
        ratelimit.IP_RPS_ENV,
        ratelimit.IP_BURST_ENV,
    ):
        monkeypatch.delenv(variable, raising=False)
    resolved = ratelimit.configure()
    assert resolved == ratelimit.Settings(
        ratelimit.DEFAULT_GLOBAL_RPS,
        ratelimit.DEFAULT_GLOBAL_BURST,
        ratelimit.DEFAULT_IP_RPS,
        ratelimit.DEFAULT_IP_BURST,
    )
    assert 429 in _codes(ratelimit.DEFAULT_GLOBAL_BURST + 5)


def test_the_four_variables_are_read_and_honoured_when_they_do_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fallback tests are only meaningful if the happy path actually reads them."""
    monkeypatch.setenv(ratelimit.GLOBAL_RPS_ENV, " 2.5 ")
    monkeypatch.setenv(ratelimit.GLOBAL_BURST_ENV, "7")
    monkeypatch.setenv(ratelimit.IP_RPS_ENV, "1")
    monkeypatch.setenv(ratelimit.IP_BURST_ENV, "3")
    assert ratelimit.configure() == ratelimit.Settings(2.5, 7, 1.0, 3)
    assert ratelimit.settings() == ratelimit.Settings(2.5, 7, 1.0, 3)


def test_an_unparsed_environment_never_reaches_the_bucket_as_infinity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The behavioural half of the fallback: ``inf`` must not produce an open door."""
    monkeypatch.setenv(ratelimit.GLOBAL_RPS_ENV, "inf")
    monkeypatch.setenv(ratelimit.GLOBAL_BURST_ENV, "inf")
    monkeypatch.setenv(ratelimit.IP_RPS_ENV, "inf")
    monkeypatch.setenv(ratelimit.IP_BURST_ENV, "inf")
    ratelimit.configure()
    codes = _codes(ratelimit.DEFAULT_GLOBAL_BURST + 10, ip="203.0.113.77")
    assert 429 in codes


# ── (e) The refusal itself ──────────────────────────────────────────────────────────


def test_the_refusal_body_is_under_the_declared_ceiling_on_both_scopes() -> None:
    """Under a flood the refusal IS the workload, so its size is the thing being emitted."""
    ratelimit.configure(global_rps=1.0, global_burst=1, ip_rps=1.0, ip_burst=1)
    app.handler(_event(ip="192.0.2.30"))

    by_ip = app.handler(_event(ip="192.0.2.30"))
    by_global = app.handler(_event(ip="192.0.2.31"))
    for response in (by_ip, by_global):
        assert response["statusCode"] == 429
        size = len(str(response["body"]).encode("utf-8"))
        assert size < ratelimit.REFUSAL_BODY_CEILING, f"the 429 body is {size} B"
        assert response["headers"]["retry-after"] == "1"
        assert response["headers"]["cache-control"] == "no-store"
        assert response["isBase64Encoded"] is False
        assert set(response) == {"statusCode", "headers", "body", "isBase64Encoded"}


def test_the_refusal_echoes_nothing_the_caller_chose() -> None:
    """The 429 is the one response not weighed against the per-response ceiling.

    It cannot be — a refusal that can itself be refused is not a control, which is the same
    argument ``app._too_large`` makes about the 413. Being unweighed makes its length an
    obligation rather than an observation, and the only way to keep that obligation is for
    nothing the caller supplied to appear in it: not the path, not the method, not the
    source address, not a header.
    """
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    marker = "Zq7wEnCanary"
    event = _event(f"/v1/{marker}/{'x' * 4000}", method="GET", ip="203.0.113.99")
    event["headers"] = {"user-agent": marker, "x-forwarded-for": "203.0.113.99"}
    event["rawQueryString"] = f"probe={marker}"

    assert app.handler(event)["statusCode"] in (404, 429)
    refusal = app.handler(event)
    assert refusal["statusCode"] == 429
    body = str(refusal["body"])
    assert marker not in body
    assert "203.0.113.99" not in body
    assert "xxxx" not in body
    assert len(body.encode("utf-8")) < ratelimit.REFUSAL_BODY_CEILING


def test_the_refusal_names_the_numbers_it_enforced() -> None:
    """Same obligation the 413 carries: the enforced value must be readable from the refusal.

    The value in force comes from an environment variable a deploy may set and a typo may
    mangle. The refusal is the one artefact that always tells the truth about what was
    actually applied.
    """
    ratelimit.configure(global_rps=3.0, global_burst=1, ip_rps=2.0, ip_burst=1)
    app.handler(_event(ip="192.0.2.40"))
    error = json.loads(app.handler(_event(ip="192.0.2.40"))["body"])["error"]
    assert error["kind"] == "rate_limited"
    assert error["status"] == 429
    assert error["scope"] == "ip"
    assert error["rps"] == 2
    assert error["burst"] == 1


def test_retry_after_is_a_whole_second_and_never_zero() -> None:
    """RFC 9110 ``delay-seconds`` is a non-negative integer, and ``0`` invites a retry
    that is certain to be refused again.

    The value is a **constant per configuration**, not a per-request computation: a
    refusal happens only when the bucket holds under one token, so the wait for one token
    is at most ``1 / rate`` whatever the bucket's history. That is what lets the whole
    refusal be a precomputed literal, which is what keeps it cheap on the path a flood
    makes hottest.
    """
    ratelimit.configure(global_rps=1.0, global_burst=1, ip_rps=1.0, ip_burst=1)
    app.handler(_event())
    assert app.handler(_event())["headers"]["retry-after"] == "1"

    ratelimit.configure(global_rps=0.25, global_burst=1, ip_rps=0.25, ip_burst=1)
    app.handler(_event())
    assert app.handler(_event())["headers"]["retry-after"] == "4"


# ── (f) A refused request does no work ──────────────────────────────────────────────


def test_a_refused_request_touches_neither_the_filesystem_nor_the_database(
    monkeypatch: pytest.MonkeyPatch, web_root: Path
) -> None:
    """The check is above the OPTIONS branch and above the ``/v1`` fork for this reason.

    Below the fork it would have bounded the API and left the static surface — the largest
    bodies this origin emits — outside the control entirely.
    """
    assert web_root.is_dir()
    ratelimit.configure(global_rps=0.01, global_burst=1, ip_rps=0.01, ip_burst=1)
    assert app.handler(_event("/"))["statusCode"] == 200

    def _forbidden(*_: Any, **__: Any) -> Any:
        raise AssertionError("a refused request reached past the rate check")

    monkeypatch.setattr(app.static_site, "serve", _forbidden)
    monkeypatch.setattr(app.db, "connection", _forbidden)

    for path, method in (("/", "GET"), ("/v1/health", "GET"), ("/v1/permits/abc", "OPTIONS")):
        response = app.handler(_event(path, method=method))
        assert response["statusCode"] == 429, f"{method} {path} was not refused first"


# ── (g) Falsification: delete the control and the flood comes back ──────────────────


def _handler_without_the_rate_check() -> types.ModuleType:
    """``app.py`` with the three guard lines removed, executed as its own module.

    Executed rather than edited on disk: the file under test is never modified, the two
    handlers exist side by side in one process, and the same flood can be run through both
    in the same test. ``__package__`` is set so the relative imports at the top of
    ``app.py`` resolve to the real package — this is the real module, minus one control.
    """
    source = Path(app.__file__ or "").read_text(encoding="utf-8")
    assert source.count(_GUARD) == 1, (
        "the guard block in app.handler no longer matches this file's _GUARD literal, so "
        "the falsification below would delete nothing and pass by accident. Re-copy the "
        "three lines; do not delete this assertion."
    )
    module = types.ModuleType("mainline_demo_api._app_without_the_rate_check")
    module.__file__ = app.__file__
    module.__package__ = "mainline_demo_api"
    exec(compile(source.replace(_GUARD, ""), app.__file__ or "app.py", "exec"), module.__dict__)  # noqa: S102 - deleting the control under test is the point
    return module


def test_removing_the_check_from_app_py_puts_the_flood_back_to_200(web_root: Path) -> None:
    """**The falsification.** With the control: 429. Without it: 200, every time.

    If this test passes with the guard deleted, the guard is decoration. That is the
    failure mode this repository has now hit three times — a test that agrees with the code
    by construction — and it is the reason the assertion below is written as a *difference*
    between two handlers rather than as a property of one.
    """
    assert web_root.is_dir()
    ratelimit.configure(global_rps=0.01, global_burst=5, ip_rps=0.01, ip_burst=1000)
    flood = 40

    with_control = _codes(flood, path="/", ip="198.51.100.55")
    assert with_control[:5] == [200] * 5
    assert set(with_control[5:]) == {429}

    ratelimit.reset()
    unguarded = _handler_without_the_rate_check()
    without_control = [
        int(unguarded.handler(_event("/", ip="198.51.100.55"))["statusCode"]) for _ in range(flood)
    ]
    assert set(without_control) == {200}, (
        "app.py without the ratelimit.check block still refused a flood, so the 429s above "
        "are being produced by something other than the control this file tests."
    )
    assert ratelimit.refusals() == {"ip": 0, "global": 0}


def test_the_guard_is_the_first_thing_in_the_handler() -> None:
    """Structural, because ordering is a property behaviour alone cannot pin.

    The behavioural test above proves the check refuses. It cannot prove the check runs
    *before* ``_method``, ``_path``, the OPTIONS branch and the ``/v1`` fork — a limiter
    placed after them would still refuse, and would still have read the filesystem to do
    it. This reads the source and pins the order.
    """
    source = Path(app.__file__ or "").read_text(encoding="utf-8")
    body = source[source.index("    started = time.monotonic()") :]
    guard = body.index("ratelimit.check(event)")
    for later in ("_method(event)", "_path(event)", 'method == "OPTIONS"', "is_api_path"):
        assert guard < body.index(later), f"{later} is evaluated before the rate check"
    assert body.index("logbudget.begin()") < guard, "the throttle line is charged to nobody"
