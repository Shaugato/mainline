# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Every refusal in ``scripts/deploy/post_apply_verify.py``, demonstrated FIRING.

WHY THIS FILE EXISTS
====================
``docs/leads/cloud-hardening-final.md`` ruling **R8**: *"a verifier that has never failed
has never discriminated."* On the day the verifier was written the stack did not exist —

    aws lambda get-function --function-name mainline-demo-api --region ap-southeast-1
      -> ResourceNotFoundException

— so it could not be proven by running it against a good deployment. It is proven here
instead, and the proof has two halves for every property:

  * the **REAL** program, fed a fault, REFUSES; and
  * a **MUTANT** of the program with that one check removed, fed the same fault, does NOT.

The second half is the one that matters. An assertion that only ever runs against the real
program cannot tell you whether the property it names is still enforced — it passes just as
happily against a program in which the check has rotted into a no-op. That is the pattern
``tests/ci/test_cluster_lane_report.py`` established, and every scenario below is held to
it.

WHAT IS SYNTHETIC AND WHAT IS NOT
=================================
The AWS answers and the HTTP answers are synthetic; the **program is the committed one**,
read off disk every time (:func:`_source`). Nothing here monkeypatches an internal — the
faults arrive through :class:`Probes`, the same four collaborators production uses, and
each synthetic reading is stamped ``source="synthetic"`` so an evidence file produced under
fault injection can never be mistaken for a live one.

WHAT NONE OF THESE TESTS DO
===========================
No AWS call is made. No socket is opened. No Terraform verb runs. Nothing is applied and
the kill switch is never driven against a live function — the ``live`` scenarios below feed
a synthetic driver, which is the whole reason the seam exists.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from types import ModuleType
from typing import Any, Final

import pytest

REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]
PROGRAM: Final = REPO_ROOT / "scripts" / "deploy" / "post_apply_verify.py"
PROBE: Final = REPO_ROOT / "scripts" / "deploy" / "aws_live_probe.py"

#: The seven alarms the two Terraform modules declare. NOT a literal expectation: the tests
#: that use it derive it through the program's own derivation and assert the count, so a
#: module that grows an eighth alarm turns this file red rather than passing with seven.
EXPECTED_ALARM_COUNT: Final = 7


# ══════════════════════════════════════════════════════════════════════════════════════
#  loading the real program, and mutants of it
# ══════════════════════════════════════════════════════════════════════════════════════


def _source(path: pathlib.Path = PROGRAM) -> str:
    assert path.is_file(), (
        f"{path} does not exist. This file is the control set for that program; if the "
        "program moved, these controls move with it in the same commit. A control set that "
        "cannot find its subject must FAIL, never skip."
    )
    return path.read_text(encoding="utf-8")


def _load(source: str, name: str, path: pathlib.Path = PROGRAM) -> ModuleType:
    """Execute ``source`` as a fresh module.

    Registered in ``sys.modules`` for the duration of the exec and removed afterwards:
    ``dataclasses`` resolves the defining module out of ``sys.modules`` while it processes
    a class, and this program is full of dataclasses. Leaving it registered would let one
    scenario's mutant leak into the next, which is the failure mode that makes a mutation
    suite pass for the wrong reason.
    """
    module = ModuleType(name)
    module.__file__ = str(path)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def real() -> ModuleType:
    """The program exactly as it is committed."""
    return _load(_source(), "post_apply_verify_real")


def mutate(anchor: str, replacement: str, name: str, path: pathlib.Path = PROGRAM) -> ModuleType:
    """The program with one named property removed.

    The anchor must appear EXACTLY ONCE. A mutation that fails to apply produces a mutant
    identical to the original, and a negative control against an unmutated program passes
    for the wrong reason — which is the failure mode this whole file exists to refuse.
    """
    source = _source(path)
    found = source.count(anchor)
    assert found == 1, (
        f"the mutation anchor for {name!r} appears {found} time(s) in {path.name}, "
        "expected exactly 1.\n"
        "\n"
        "THIS IS NOT A FAILURE OF THE PROGRAM. It means the program was reshaped and this "
        "control's demonstration no longer applies to it. Re-anchor the mutation against "
        "the new text IN THE SAME COMMIT. Do not delete the demonstration: an assertion "
        "with no demonstration behind it cannot tell you whether the property it names is "
        "still enforced.\n"
        "\n"
        f"anchor sought:\n{anchor}"
    )
    return _load(source.replace(anchor, replacement), name, path)


# ══════════════════════════════════════════════════════════════════════════════════════
#  the synthetics — every one of them stamped, none of them a mode of the program
# ══════════════════════════════════════════════════════════════════════════════════════


class FakeTerraform:
    def __init__(self, outputs: dict[str, Any] | Exception) -> None:
        self._outputs = outputs

    def outputs(self) -> dict[str, Any]:
        if isinstance(self._outputs, Exception):
            raise self._outputs
        return self._outputs


class FakeHttp:
    """Answers by (method, path-suffix). An unscripted request is an error, never a 200.

    Defaulting an unscripted request to success is how a fault-injection harness comes to
    prove the wrong thing: the scenario forgets to script a call, the program takes a path
    nobody meant to exercise, and the control passes.
    """

    def __init__(
        self,
        module: ModuleType,
        script: dict[tuple[str, str], Any],
        tls: dict[str, Any] | Exception | None = None,
    ) -> None:
        self._module = module
        self._script = script
        self._tls = (
            tls
            if tls is not None
            else {
                "verified": True,
                "host": "example.invalid",
                "protocol": "TLSv1.3",
                "cipher": "TLS_AES_128_GCM_SHA256",
                "subject": "CN=*.lambda-url.ap-southeast-1.on.aws",
                "issuer": "CN=Amazon RSA 2048 M02",
                "not_after": "Nov 1 2026",
            }
        )
        self.calls: list[tuple[str, str]] = []

    # `url` is unused and must stay in the signature: these fakes stand in for the real
    # collaborators through the SAME calls the program makes, and a fake whose signature
    # drifted from its subject would let a scenario pass against a call production could
    # not make. Same for every other ARG002 below.
    def tls(self, url: str) -> dict[str, Any]:  # noqa: ARG002 - interface fidelity
        if isinstance(self._tls, Exception):
            raise self._tls
        return self._tls

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,  # noqa: ARG002 - interface fidelity
        headers: dict[str, str] | None = None,  # noqa: ARG002 - interface fidelity
    ) -> Any:
        suffix = url.rsplit("/", 1)[-1] if "gate-run" not in url else "gate-run"
        self.calls.append((method, suffix))
        for (want_method, want_suffix), scripted in self._script.items():
            if want_method == method and want_suffix == suffix:
                answer = scripted() if callable(scripted) else scripted
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise self._module.Unavailable(
            f"the control did not script {method} .../{suffix}; refusing to invent an answer."
        )


class FakeAws:
    def __init__(
        self,
        alarms: list[dict[str, Any]] | Exception,
        datapoints: dict[str, list[dict[str, Any]]] | Exception | None = None,
    ) -> None:
        self._alarms = alarms
        self._datapoints = datapoints if datapoints is not None else {}

    def describe_alarms(self, prefix: str) -> list[dict[str, Any]]:
        if isinstance(self._alarms, Exception):
            raise self._alarms
        return [a for a in self._alarms if str(a.get("AlarmName", "")).startswith(prefix)]

    def metric_statistics(
        self,
        namespace: str,  # noqa: ARG002 - interface fidelity
        metric: str,
        dimensions: list[dict[str, str]],  # noqa: ARG002 - interface fidelity
        start: str,  # noqa: ARG002 - interface fidelity
        end: str,  # noqa: ARG002 - interface fidelity
    ) -> list[dict[str, Any]]:
        if isinstance(self._datapoints, Exception):
            raise self._datapoints
        return self._datapoints.get(metric, [])


class World:
    """The one bit of state the kill switch and the origin have to agree about.

    Without it a scenario cannot express "stopped, then restored": a constant HTTP script
    would have to answer both 429 and 200 to the same request, and whichever it chose would
    make one of the two kill-switch checks unprovable. The origin therefore consults this
    flag, and only the kill-switch driver sets it — which is exactly the causal chain the
    two checks claim to measure.
    """

    def __init__(self) -> None:
        self.stopped = False


class FakeKillSwitch:
    def __init__(
        self,
        module: ModuleType,
        *,
        status: Any = None,
        dry: Any = None,
        stop: Any = None,
        restore: Any = None,
        world: World | None = None,
    ) -> None:
        self.world = world if world is not None else World()
        self._module = module
        self._status = status if status is not None else module.Ran(0, "reserved concurrency 0", "")
        self._dry = (
            dry
            if dry is not None
            else module.Ran(
                0,
                "WOULD RUN aws lambda put-function-concurrency\n"
                "WOULD RUN aws lambda delete-function-concurrency",
                "",
            )
        )
        self._stop = stop if stop is not None else module.Ran(0, "STOPPED", "")
        self._restore = restore if restore is not None else module.Ran(0, "RESTORED", "")
        self.performed: list[str] = []

    def status(self) -> Any:
        self.performed.append("status")
        return _raise_or(self._status)

    def dry_run(self) -> Any:
        self.performed.append("dry_run")
        return _raise_or(self._dry)

    def stop(self, *, expect_account: str | None) -> Any:  # noqa: ARG002 - interface fidelity
        self.performed.append("stop")
        answer = _raise_or(self._stop)
        if answer.returncode == 0:
            self.world.stopped = True
        return answer

    def restore(self, *, expect_account: str | None) -> Any:  # noqa: ARG002 - interface fidelity
        self.performed.append("restore")
        answer = _raise_or(self._restore)
        if answer.returncode == 0:
            self.world.stopped = False
        return answer


def _raise_or(value: Any) -> Any:
    if isinstance(value, Exception):
        raise value
    return value


# ── the healthy world every scenario perturbs exactly one thing in ─────────────────────


def _alarm(
    name: str,
    metric: str,
    namespace: str = "AWS/Lambda",
    state: str = "OK",
    dimensions: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "AlarmName": name,
        "MetricName": metric,
        "Namespace": namespace,
        "StateValue": state,
        "TreatMissingData": "missing",
        "Dimensions": dimensions
        if dimensions is not None
        else [{"Name": "FunctionName", "Value": "mainline-demo-api"}],
    }


def healthy_alarms() -> list[dict[str, Any]]:
    """All seven, named exactly as the Terraform modules build them."""
    return [
        _alarm("mainline-demo-api-errors", "Errors"),
        _alarm("mainline-demo-api-throttles", "Throttles"),
        _alarm("mainline-demo-api-duration-p99", "Duration"),
        _alarm("mainline-demo-api-concurrency", "ConcurrentExecutions", dimensions=[]),
        _alarm("mainline-demo-api-invocations-burst", "Invocations"),
        _alarm("mainline-demo-api-invocations-hourly", "Invocations"),
        _alarm(
            "mainline-demo-api-log-ingestion",
            "IncomingBytes",
            namespace="AWS/Logs",
            dimensions=[{"Name": "LogGroupName", "Value": "/aws/lambda/mainline-demo-api"}],
        ),
    ]


def healthy_datapoints() -> dict[str, list[dict[str, Any]]]:
    point = [{"Sum": 3.0, "SampleCount": 3.0}]
    return {"Invocations": point, "Duration": point, "ConcurrentExecutions": point}


def healthy_beats() -> list[dict[str, Any]]:
    return [
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
        {
            "ordinal": 4,
            "name": "admit",
            "outcome": "admitted",
            "sqlstate": "00000",
            "constraint": None,
            "observed": {"merge_record": {"clearance_digest": "a" * 63 + "b"}},
        },
    ]


def _answer(
    module: ModuleType, status: int, document: Any = None, body: bytes | None = None
) -> Any:
    payload = body if body is not None else json.dumps(document or {}).encode("utf-8")
    return module.HttpAnswer(
        status=status, headers={"content-type": "application/json"}, body=payload, elapsed_ms=12.5
    )


def healthy_http(module: ModuleType, world: World | None = None, **overrides: Any) -> FakeHttp:
    world = world if world is not None else World()
    script: dict[tuple[str, str], Any] = {
        # Phase-aware: 429 with an EMPTY body while the reservation is on, 200 otherwise.
        # That is what Lambda does — its own throttle answers before the handler runs — and
        # it is the difference the kill-switch checks are built to read.
        ("GET", "health"): lambda: (
            _answer(module, 429, body=b"")
            if world.stopped
            else _answer(module, 200, {"ok": True, "seconds": 0.01})
        ),
        ("POST", "gate-run"): _answer(
            module, 200, {"data": {"verdict": "PROVEN", "beats": healthy_beats()}}
        ),
    }
    script.update(overrides.pop("script", {}))
    return FakeHttp(module, script, **overrides)


# `module` IS used - `module.Probes` is constructed from it. ruff cannot see that through
# the ModuleType, so the directive is here with its reason rather than the parameter being
# renamed into something the call sites would then have to lie about.
def healthy_probes(module: ModuleType, **overrides: Any) -> Any:
    world = World()
    return module.Probes(
        terraform=overrides.get(
            "terraform",
            FakeTerraform(
                {"api_function_url": {"value": "https://abc123.lambda-url.ap-southeast-1.on.aws/"}}
            ),
        ),
        http=overrides.get("http", healthy_http(module, world)),
        aws=overrides.get("aws", FakeAws(healthy_alarms(), healthy_datapoints())),
        kill_switch=overrides.get("kill_switch", FakeKillSwitch(module, world=world)),
        source="synthetic",
    )


# `module` is taken and ignored on purpose: every helper in this file has the same
# (module, **overrides) shape so a scenario never has to remember which of them needs the
# module under test and which does not. A helper that dropped it would be the one call site
# that reads differently, and different-looking call sites are where mistakes hide.
def args_for(module: ModuleType, **overrides: Any) -> argparse.Namespace:  # noqa: ARG001
    values = {
        "tf_dir": REPO_ROOT / "infra" / "envs" / "demo",
        "region": "ap-southeast-1",
        "profile": "mainline-dev",
        "function_name": "mainline-demo-api",
        "alarm_prefix": "mainline-demo-api",
        "kill_switch": "live",
        "yes": True,
        "expect_account": None,
        "metric_lag_minutes": 5,
        "out": None,
        "print_json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def run(module: ModuleType, probes: Any, **arg_overrides: Any) -> dict[str, str]:
    """Run every check and return ``{check id: "" if satisfied else why}``."""
    checks, _ = module.verify(probes, args_for(module, **arg_overrides), REPO_ROOT)
    return {c.id: ("" if c.satisfied else c.why) for c in checks}


# ══════════════════════════════════════════════════════════════════════════════════════
#  0 · the control's own control — the healthy world must be green
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_healthy_world_satisfies_every_check():
    """If this goes red, every refusal below proves nothing.

    A fault-injection suite whose baseline is already failing cannot distinguish "the check
    caught my fault" from "the check fails on everything". This is that baseline, and it is
    the first assertion in the file on purpose.
    """
    module = real()
    outcome = run(module, healthy_probes(module))
    unsatisfied = {k: v for k, v in outcome.items() if v}
    assert not unsatisfied, (
        "the synthetic HEALTHY world does not satisfy every check, so no refusal "
        "demonstrated below is evidence of anything:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in unsatisfied.items())
    )
    assert len(outcome) == 9, (
        f"the program ran {len(outcome)} checks; this control set demonstrates 9. A check "
        "was added or removed without its demonstration moving in the same commit."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  1 · the Function URL — a missing function, and a URL that is not resolved from state
# ══════════════════════════════════════════════════════════════════════════════════════


_URL_ANCHOR: Final = """    raw = outputs[FUNCTION_URL_OUTPUT]
    value = raw.get("value") if isinstance(raw, dict) else raw
    if not value:"""
_URL_REMOVED: Final = """    raw = outputs[FUNCTION_URL_OUTPUT]
    value = raw.get("value") if isinstance(raw, dict) else raw
    value = value or "https://mutant.example.invalid/"  # MUTANT: null output accepted
    if not value:"""


def test_a_null_function_url_is_refused__and_the_mutant_that_accepts_it_is_not():
    """`outputs.tf` emits null when `enable_api = false`. That is an unapplied API, not a URL."""
    module = real()
    probes = healthy_probes(module, terraform=FakeTerraform({"api_function_url": {"value": None}}))
    outcome = run(module, probes)
    assert outcome["function_url"], (
        "a null api_function_url was accepted as a Function URL. outputs.tf emits null when "
        "enable_api is false; accepting it means this verifier will probe nothing and "
        "report a URL."
    )
    assert "null" in outcome["function_url"]

    mutant = mutate(_URL_ANCHOR, _URL_REMOVED, "url_null_accepted")
    mutant_outcome = run(
        mutant,
        healthy_probes(mutant, terraform=FakeTerraform({"api_function_url": {"value": None}})),
    )
    assert not mutant_outcome["function_url"], (
        "the MUTANT — the program with the null-output refusal removed — was supposed to "
        "accept the null and report the check satisfied. It refused anyway, so the "
        "assertion above is not evidence that the refusal is what caught it."
    )


def test_a_missing_function_is_refused_by_terraform_carrying_no_such_output():
    """The stack this program was written against did not exist. This is that reading."""
    module = real()
    probes = healthy_probes(
        module, terraform=FakeTerraform({"aws_region": {"value": "ap-southeast-1"}})
    )
    outcome = run(module, probes)
    assert outcome["function_url"], "state with no api_function_url output was accepted."
    assert "no output named" in outcome["function_url"]
    # The whole downstream chain must go with it: a verifier that reports TLS or health as
    # satisfied while holding no URL has invented a subject.
    for downstream in ("tls", "health", "beats", "clearance_digest"):
        assert outcome[downstream], (
            f"{downstream} reported SATISFIED while no Function URL was resolved. There was "
            "nothing to measure and it measured it anyway."
        )


def test_a_plain_http_url_is_refused():
    module = real()
    probes = healthy_probes(
        module,
        terraform=FakeTerraform(
            {"api_function_url": {"value": "http://abc123.lambda-url.ap-southeast-1.on.aws/"}}
        ),
    )
    outcome = run(module, probes)
    assert outcome["function_url"] and "HTTPS" in outcome["function_url"], (
        "a plain-HTTP demo URL was accepted. It has no certificate to verify and no "
        "confidentiality to offer, and it must never be published."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  2 · TLS
# ══════════════════════════════════════════════════════════════════════════════════════


_TLS_ANCHOR: Final = """    if not facts.get("verified"):"""
_TLS_REMOVED: Final = """    if False:  # MUTANT: unverified certificates accepted"""


def test_an_unverified_certificate_is_refused__and_the_mutant_that_accepts_it_is_not():
    module = real()
    unverified = {
        "verified": False,
        "host": "abc123.lambda-url.ap-southeast-1.on.aws",
        "protocol": "TLSv1.3",
    }
    outcome = run(module, healthy_probes(module, http=healthy_http(module, tls=unverified)))
    assert outcome["tls"], (
        "a handshake that completed WITHOUT the certificate verifying was reported as "
        "satisfied. That is measuring reachability and calling it security."
    )

    mutant = mutate(_TLS_ANCHOR, _TLS_REMOVED, "tls_verification_removed")
    mutant_outcome = run(mutant, healthy_probes(mutant, http=healthy_http(mutant, tls=unverified)))
    assert not mutant_outcome["tls"], (
        "the MUTANT with the verification refusal removed still refused, so the assertion "
        "above does not demonstrate that this refusal is the thing doing the work."
    )


def test_a_tls_error_is_refused_rather_than_reported_as_absence():
    module = real()
    broken = None
    real_module = module

    class _Boom(FakeHttp):
        pass

    http = healthy_http(
        module,
        tls=real_module.Unavailable(
            "TLS verification FAILED for abc.example: certificate has expired"
        ),
    )
    outcome = run(module, healthy_probes(module, http=http))
    assert outcome["tls"] and "FAILED" in outcome["tls"], (
        "an expired certificate produced something other than a refusal naming it."
    )
    assert broken is None and _Boom is not None  # the scenario used no other seam


# ══════════════════════════════════════════════════════════════════════════════════════
#  3 · health
# ══════════════════════════════════════════════════════════════════════════════════════


_HEALTH_ANCHOR: Final = (
    """    if not isinstance(document, dict) or document.get("ok") is not True:"""
)
_HEALTH_REMOVED: Final = (
    """    if False:  # MUTANT: a 200 whose body reports a problem is accepted"""
)


def test_a_200_health_body_that_is_not_ok_is_refused__and_the_mutant_is_not():
    """A 200 whose body reports a problem is a 200 a load balancer believes and a judge does not."""
    module = real()
    sick = {("GET", "health"): _answer(module, 200, {"ok": False, "detail": "no database"})}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=sick)))
    assert outcome["health"] and "ok=true" in outcome["health"]

    mutant = mutate(_HEALTH_ANCHOR, _HEALTH_REMOVED, "health_body_unchecked")
    sick_mutant = {("GET", "health"): _answer(mutant, 200, {"ok": False, "detail": "no database"})}
    mutant_outcome = run(
        mutant, healthy_probes(mutant, http=healthy_http(mutant, script=sick_mutant))
    )
    assert not mutant_outcome["health"], (
        "the MUTANT that ignores the health body still refused, so the body check is not "
        "what caught it."
    )


def test_a_non_200_health_is_refused():
    module = real()
    script = {("GET", "health"): _answer(module, 503, {"ok": False})}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["health"] and "503" in outcome["health"]


# ══════════════════════════════════════════════════════════════════════════════════════
#  4 · the beats and their SQLSTATEs
# ══════════════════════════════════════════════════════════════════════════════════════


_SQLSTATE_ANCHOR: Final = """        if found.get("sqlstate") != expected["sqlstate"]:"""
_SQLSTATE_REMOVED: Final = """        if False:  # MUTANT: the SQLSTATE is no longer compared"""


@pytest.mark.parametrize(
    ("beat_name", "wrong_sqlstate", "right_sqlstate"),
    [
        ("read", "23514", "00000"),
        ("merge", "23503", "23514"),
        ("projection_drift_attack", "23514", "P0001"),
        ("admit", "P0001", "00000"),
    ],
)
def test_a_beat_with_the_wrong_sqlstate_is_refused(beat_name, wrong_sqlstate, right_sqlstate):
    """Each of the four, one at a time. The demo's whole argument is this sequence.

    ``23503`` on beat 2 is not hypothetical: ``evidence/deploy/acceptance.json`` recorded a
    run whose fourth beat failed with ``23503 disposition_signer_credential_id_fkey`` and
    the payload still rendered. A verifier that does not compare the SQLSTATE would have
    published that run.
    """
    module = real()
    beats = healthy_beats()
    for beat in beats:
        if beat["name"] == beat_name:
            beat["sqlstate"] = wrong_sqlstate
    script = {
        ("POST", "gate-run"): _answer(module, 200, {"data": {"verdict": "PROVEN", "beats": beats}})
    }
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["beats"], (
        f"beat {beat_name!r} answered SQLSTATE {wrong_sqlstate} where the contract requires "
        f"{right_sqlstate}, and the verifier reported the beats satisfied."
    )
    assert wrong_sqlstate in outcome["beats"] and right_sqlstate in outcome["beats"], (
        "the refusal does not name both the observed and the required SQLSTATE, so the "
        "reader has to go and look it up at the moment they are least able to."
    )


def test_the_mutant_that_stops_comparing_sqlstates_accepts_a_wrong_one():
    module = real()
    beats = healthy_beats()
    beats[1]["sqlstate"] = "23503"
    script_real = {("POST", "gate-run"): _answer(module, 200, {"data": {"beats": beats}})}
    assert run(module, healthy_probes(module, http=healthy_http(module, script=script_real)))[
        "beats"
    ]

    mutant = mutate(_SQLSTATE_ANCHOR, _SQLSTATE_REMOVED, "sqlstate_comparison_removed")
    beats_mutant = healthy_beats()
    beats_mutant[1]["sqlstate"] = "23503"
    script = {("POST", "gate-run"): _answer(mutant, 200, {"data": {"beats": beats_mutant}})}
    mutant_outcome = run(mutant, healthy_probes(mutant, http=healthy_http(mutant, script=script)))
    assert not mutant_outcome["beats"], (
        "the MUTANT with the SQLSTATE comparison removed was supposed to accept "
        "23503 on the merge beat; it refused anyway, so the comparison is not what "
        "discriminates and this whole section proves nothing."
    )


def test_a_short_beat_array_is_refused():
    """Three beats still render as a demo, and they argue something else."""
    module = real()
    beats = healthy_beats()[:3]
    script = {("POST", "gate-run"): _answer(module, 200, {"data": {"beats": beats}})}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["beats"] and "3 beats" in outcome["beats"]


# ══════════════════════════════════════════════════════════════════════════════════════
#  5 · the clearance digest
# ══════════════════════════════════════════════════════════════════════════════════════


_DIGEST_ANCHOR: Final = """    digest = record.get("clearance_digest")"""
_DIGEST_REMOVED: Final = (
    '    digest = record.get("clearance_digest") or "a" * 64  # MUTANT: absence papered over'
)


def test_an_admission_with_no_clearance_digest_is_refused__and_the_mutant_is_not():
    """An ADMITTED with no server-computed exhibit is an assertion, not evidence."""
    module = real()
    beats = healthy_beats()
    beats[3]["observed"] = {"merge_record": {"merged_commit": "deadbeef"}}
    script = {("POST", "gate-run"): _answer(module, 200, {"data": {"beats": beats}})}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["clearance_digest"] and "no clearance_digest" in outcome["clearance_digest"]

    mutant = mutate(_DIGEST_ANCHOR, _DIGEST_REMOVED, "clearance_digest_presence_removed")
    beats_mutant = healthy_beats()
    beats_mutant[3]["observed"] = {"merge_record": {"merged_commit": "deadbeef"}}
    script_mutant = {("POST", "gate-run"): _answer(mutant, 200, {"data": {"beats": beats_mutant}})}
    mutant_outcome = run(
        mutant, healthy_probes(mutant, http=healthy_http(mutant, script=script_mutant))
    )
    assert not mutant_outcome["clearance_digest"], (
        "the MUTANT that no longer requires a clearance_digest still refused, so the "
        "presence check is not what caught the missing exhibit."
    )


def test_a_clearance_digest_that_is_not_a_sha256_hex_is_refused():
    """Shape is not provenance, but a value that is not the column's shape is not the column."""
    module = real()
    beats = healthy_beats()
    beats[3]["observed"] = {"merge_record": {"clearance_digest": "PROVEN"}}
    script = {("POST", "gate-run"): _answer(module, 200, {"data": {"beats": beats}})}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["clearance_digest"] and "64 lowercase hex" in outcome["clearance_digest"]


# ══════════════════════════════════════════════════════════════════════════════════════
#  6 · the alarms — the four-of-seven blindness, and a missing alarm
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_expected_alarm_set_is_derived_and_is_all_seven():
    """The defect R8 names: a hard-coded four over a deployment that creates seven.

    Derived through the program's own loader, so if the derivation regresses to a literal
    four this goes red — which is the point. The three it could not see are the guard's,
    and the guard's are the ones wired to the stop.
    """
    module = real()
    expected, underivable, provenance = module.load_expected_alarms(REPO_ROOT, "mainline-demo-api")
    assert underivable is None, f"the alarm set could not be derived: {underivable}"
    assert expected is not None
    assert len(expected) == EXPECTED_ALARM_COUNT, (
        f"the derivation produced {len(expected)} alarms: {expected}. The two Terraform "
        f"modules declare {EXPECTED_ALARM_COUNT}. If a module gained or lost an alarm, this "
        "number moves WITH the module in the same commit and never to obtain a green."
    )
    for guard_alarm in ("-invocations-burst", "-invocations-hourly", "-log-ingestion"):
        assert any(name.endswith(guard_alarm) for name in expected), (
            f"the derived set does not contain {guard_alarm}, which is one of the GUARD's "
            "three — the ones wired to the stop, and the exact three the previous "
            "hard-coded four could not see."
        )
    assert provenance["cross_check"]["agree"] is True, (
        "the set derived from the modules disagrees with the committed plan artefact. One "
        "of the two describes a tree that does not exist; the modules are authoritative "
        "(R7) and the artefact is regenerated, never the other way round."
    )


def test_the_derivation_reads_the_modules_and_not_a_literal(tmp_path):
    """Falsification: point the derivation at a tree whose modules declare something else.

    A derivation that ignores its input and returns the same four every time would pass
    every assertion above. This one is handed a scratch tree with ONE alarm in it, and must
    come back with one.
    """
    module = real()
    fake = tmp_path / "tree"
    (fake / "infra" / "modules" / "demo-api").mkdir(parents=True)
    (fake / "infra" / "modules" / "cost-guard").mkdir(parents=True)
    (fake / "scripts" / "deploy").mkdir(parents=True)
    (fake / "verticals").mkdir()
    (fake / "packages").mkdir()
    (fake / "infra" / "modules" / "demo-api" / "main.tf").write_text(
        'resource "aws_cloudwatch_metric_alarm" "only" {\n'
        '  alarm_name = "${var.function_name}-only-one"\n}\n',
        encoding="utf-8",
    )
    (fake / "infra" / "modules" / "cost-guard" / "main.tf").write_text(
        'resource "aws_cloudwatch_metric_alarm" "g" {\n'
        '  alarm_name = "${var.guarded_function_name}-guard-only"\n}\n',
        encoding="utf-8",
    )
    (fake / "scripts" / "deploy" / "aws_live_probe.py").write_text(_source(PROBE), encoding="utf-8")
    expected, underivable, _ = module.load_expected_alarms(fake, "x")
    assert underivable is None, underivable
    assert expected == ["x-guard-only", "x-only-one"], (
        f"the derivation answered {expected} over a scratch tree declaring two alarms with "
        "different names. It is not reading its input, which means it is a literal wearing "
        "a function's clothes."
    )


def test_an_alarm_this_program_cannot_read_makes_the_derivation_refuse(tmp_path):
    """An alarm named some other way is invisible to a prefix reader. Refuse, do not shorten."""
    module = real()
    fake = tmp_path / "tree"
    (fake / "infra" / "modules" / "demo-api").mkdir(parents=True)
    (fake / "infra" / "modules" / "cost-guard").mkdir(parents=True)
    (fake / "scripts" / "deploy").mkdir(parents=True)
    (fake / "verticals").mkdir()
    (fake / "packages").mkdir()
    (fake / "infra" / "modules" / "demo-api" / "main.tf").write_text(
        'resource "aws_cloudwatch_metric_alarm" "readable" {\n'
        '  alarm_name = "${var.function_name}-errors"\n}\n'
        'resource "aws_cloudwatch_metric_alarm" "opaque" {\n'
        "  alarm_name = local.something_else\n}\n",
        encoding="utf-8",
    )
    (fake / "infra" / "modules" / "cost-guard" / "main.tf").write_text(
        'resource "aws_cloudwatch_metric_alarm" "g" {\n'
        '  alarm_name = "${var.guarded_function_name}-burst"\n}\n',
        encoding="utf-8",
    )
    (fake / "scripts" / "deploy" / "aws_live_probe.py").write_text(_source(PROBE), encoding="utf-8")
    expected, underivable, _ = module.load_expected_alarms(fake, "x")
    assert expected is None and underivable, (
        "a module declaring two alarms of which only one has a readable name produced a "
        "set of one rather than a refusal. A quietly short set is the defect, not the fix."
    )
    assert "2" in underivable and "1" in underivable


_INVENTORY_ANCHOR: Final = """    if missing:"""
_INVENTORY_REMOVED: Final = """    if False:  # MUTANT: a missing alarm is no longer a finding"""


def test_a_missing_alarm_is_refused__and_the_mutant_that_ignores_it_is_not():
    """Exactly the four-of-seven world: the guard's three absent, the demo-api four present."""
    module = real()
    four_only = [
        a
        for a in healthy_alarms()
        if a["MetricName"] in {"Errors", "Throttles", "Duration", "ConcurrentExecutions"}
    ]
    outcome = run(module, healthy_probes(module, aws=FakeAws(four_only, healthy_datapoints())))
    assert outcome["alarm_inventory"], (
        "four alarms out of seven were reported as a complete inventory. That is the exact "
        "defect docs/deploy/PRE-APPLY.md §3 recorded: a reader that is complete-looking and "
        "is not, blind to the three wired to the stop."
    )
    for guard_alarm in ("invocations-burst", "invocations-hourly", "log-ingestion"):
        assert guard_alarm in outcome["alarm_inventory"], (
            f"the refusal does not name the missing {guard_alarm} alarm."
        )

    mutant = mutate(_INVENTORY_ANCHOR, _INVENTORY_REMOVED, "missing_alarm_ignored")
    mutant_outcome = run(
        mutant, healthy_probes(mutant, aws=FakeAws(four_only, healthy_datapoints()))
    )
    assert not mutant_outcome["alarm_inventory"], (
        "the MUTANT that no longer treats a missing alarm as a finding still refused."
    )


def test_a_relaxed_treat_missing_data_is_refused():
    """`missing` is correct and must not be relaxed. `notBreaching` renders silence as OK."""
    module = real()
    alarms = healthy_alarms()
    alarms[0]["TreatMissingData"] = "notBreaching"
    outcome = run(module, healthy_probes(module, aws=FakeAws(alarms, healthy_datapoints())))
    assert outcome["alarm_inventory"] and "notBreaching" in outcome["alarm_inventory"], (
        "an alarm carrying treat_missing_data='notBreaching' was accepted. Under that "
        "setting a metric nobody published renders as OK, which is a green that measured "
        "nothing."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  7 · alarm visibility — INSUFFICIENT_DATA, and a metric with no datapoints
# ══════════════════════════════════════════════════════════════════════════════════════


_VISIBILITY_ANCHOR: Final = """        if required and not points:"""
_VISIBILITY_REMOVED: Final = (
    """        if False:  # MUTANT: a metric with no datapoints is no longer a finding"""
)


def test_an_alarm_over_a_metric_with_no_datapoints_is_refused__and_the_mutant_is_not():
    """An alarm on a metric with no datapoints is not evidence, whatever colour it is.

    The alarms here are all state ``INSUFFICIENT_DATA``, which under
    ``treat_missing_data='missing'`` is the HONEST state of an alarm whose metric was never
    published. The check does not ask them to be OK — it asks whether the metric received a
    datapoint in the window this program was invoking the function. It did not.
    """
    module = real()
    alarms = [dict(a, StateValue="INSUFFICIENT_DATA") for a in healthy_alarms()]
    outcome = run(module, healthy_probes(module, aws=FakeAws(alarms, {})))
    assert outcome["alarm_visibility"], (
        "seven alarms whose metrics received NO datapoints in the window this program was "
        "calling the function were reported as able to see it."
    )
    assert "NO datapoints" in outcome["alarm_visibility"]
    assert "treat_missing_data" not in outcome["alarm_visibility"].replace(
        "treat_missing_data='missing'", ""
    ), "the refusal must not propose relaxing treat_missing_data as a remedy."

    mutant = mutate(_VISIBILITY_ANCHOR, _VISIBILITY_REMOVED, "datapoint_requirement_removed")
    mutant_outcome = run(mutant, healthy_probes(mutant, aws=FakeAws(alarms, {})))
    assert not mutant_outcome["alarm_visibility"], (
        "the MUTANT with the datapoint requirement removed still refused, so 'the alarms "
        "can see the invocations' is not what this check is measuring."
    )


def test_the_check_does_not_demand_a_datapoint_on_metrics_an_invocation_cannot_publish():
    """Falsification of the check's own scope: requiring Errors would require a broken demo.

    A visibility check that demanded an ``Errors`` datapoint could only pass on a system
    that was erroring. This asserts the opposite property — that a healthy world with
    Invocations/Duration/ConcurrentExecutions datapoints and no Errors datapoint SATISFIES —
    so that a future widening of the requirement turns this red rather than turning the
    demo red.
    """
    module = real()
    only_movable = healthy_datapoints()  # Errors, Throttles, IncomingBytes deliberately absent
    outcome = run(module, healthy_probes(module, aws=FakeAws(healthy_alarms(), only_movable)))
    assert not outcome["alarm_visibility"], (
        "the visibility check refused a world in which every metric an invocation can "
        "publish HAS datapoints and only Errors/Throttles/IncomingBytes do not. Demanding "
        "those would demand that the demo be broken before it could pass."
    )


def test_a_metric_read_that_fails_is_refused_rather_than_counted_as_zero():
    module = real()
    aws = FakeAws(
        healthy_alarms(), module.Unavailable("AccessDenied: cloudwatch:GetMetricStatistics")
    )
    outcome = run(module, healthy_probes(module, aws=aws))
    assert outcome["alarm_visibility"] and "could not be read" in outcome["alarm_visibility"], (
        "a refused metric read was folded into 'no datapoints'. An unreadable answer and a "
        "known-empty one are different incidents and must not share a sentence."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  8 · the kill switch — a stop that did not take, and a 429 that never cleared
# ══════════════════════════════════════════════════════════════════════════════════════


# The mutation removes the RE-PROBE, not one branch of the verdict. Removing only the
# `!= 429` arm leaves the `body_bytes` arm to refuse for an unrelated reason, and a mutant
# that still refuses — for any reason — proves nothing about the branch under test. What
# this control demonstrates is the property "the world is re-read after the call", so that
# is what the mutant loses.
_STOP_ANCHOR: Final = """        after = _probe_once(probes, base)"""
_STOP_REMOVED: Final = (
    '        after = {"status": 429, "body_bytes": 0}  # MUTANT: the origin is never re-probed'
)


def test_a_kill_switch_that_did_not_take_is_refused__and_the_mutant_is_not():
    """`--stop` exited 0 and the origin still serves. That is the worst of the three outcomes."""
    module = real()
    still_serving = {("GET", "health"): _answer(module, 200, {"ok": True})}
    probes = healthy_probes(module, http=healthy_http(module, script=still_serving))
    outcome = run(module, probes)
    assert outcome["kill_switch_stop"], (
        "kill_switch --stop exited 0, the origin kept answering 200, and the verifier "
        "reported the kill switch proven. That reports safety it has not produced."
    )
    assert "did not land" in outcome["kill_switch_stop"]

    mutant = mutate(_STOP_ANCHOR, _STOP_REMOVED, "post_stop_status_unchecked")
    mutant_probes = healthy_probes(
        mutant,
        http=healthy_http(mutant, script={("GET", "health"): _answer(mutant, 200, {"ok": True})}),
    )
    mutant_outcome = run(mutant, mutant_probes)
    assert not mutant_outcome["kill_switch_stop"], (
        "the MUTANT that never re-probes the origin after --stop still refused, so the "
        "re-probe is not what caught a stop that did not land."
    )


def test_a_429_that_carries_a_body_is_refused():
    """Lambda's own throttle answers 429 with nothing. A body means the handler ran."""
    module = real()
    script = {("GET", "health"): _answer(module, 429, body=b'{"error":"rate limited by the app"}')}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=script)))
    assert outcome["kill_switch_stop"] and "bytes of body" in outcome["kill_switch_stop"], (
        "a 429 carrying a body was accepted as proof of the reservation. The handler "
        "answered, so the reservation did not stop it."
    )


# Same shape as the stop mutation and for the same reason: the property is "re-read the
# origin after --restore", and a mutant that kept the re-probe would simply refuse via the
# neighbouring `!= 200` arm.
_RESTORE_ANCHOR: Final = """    back = _probe_once(probes, base)"""
_RESTORE_REMOVED: Final = (
    '    back = {"status": 200, "body_bytes": 12}  # MUTANT: the origin is never re-probed'
)


def test_a_429_that_never_cleared_is_refused__and_the_mutant_is_not():
    """`--restore` exited 0 and the demo is still dark. An outage the runbook believes it ended."""
    module = real()
    always_429 = {("GET", "health"): _answer(module, 429, body=b"")}
    outcome = run(module, healthy_probes(module, http=healthy_http(module, script=always_429)))
    assert outcome["kill_switch_restore"] and "never cleared" in outcome["kill_switch_restore"]

    mutant = mutate(_RESTORE_ANCHOR, _RESTORE_REMOVED, "restore_429_ignored")
    mutant_outcome = run(
        mutant,
        healthy_probes(
            mutant,
            http=healthy_http(mutant, script={("GET", "health"): _answer(mutant, 429, body=b"")}),
        ),
    )
    assert not mutant_outcome["kill_switch_restore"], (
        "the MUTANT that never re-probes the origin after --restore still refused, so the "
        "re-probe is not what caught the 429 that never cleared."
    )


def test_a_failed_restore_names_the_demo_as_still_stopped():
    """The one message an operator must not have to infer at 3 a.m."""
    module = real()
    probes = healthy_probes(
        module, kill_switch=FakeKillSwitch(module, restore=module.Ran(1, "", "boom"))
    )
    outcome = run(module, probes)
    assert outcome["kill_switch_restore"]
    assert (
        "STILL" in outcome["kill_switch_restore"] and "--restore" in outcome["kill_switch_restore"]
    )


def test_dry_mode_never_mutates_and_is_never_satisfied():
    """The default. It is honest, and honest is not green.

    This is the mode that ran today against the unapplied account. It must drive `--status`
    and `--dry-run` and NOTHING else, and it must report both kill-switch checks
    unsatisfied — because a stop nobody performed is a stop nobody has evidence for.
    """
    module = real()
    switch = FakeKillSwitch(module, status=module.Ran(4, "there is no function named ...", ""))
    outcome = run(module, healthy_probes(module, kill_switch=switch), kill_switch="dry")
    assert switch.performed == ["status", "dry_run"], (
        f"--kill-switch dry drove {switch.performed}. It must never reach stop or restore."
    )
    assert outcome["kill_switch_stop"] and outcome["kill_switch_restore"], (
        "dry mode reported a kill-switch check SATISFIED. Nothing was stopped, nothing "
        "answered 429, and nothing was restored."
    )


def test_skip_mode_is_not_a_pass():
    """A skip is indistinguishable from a green tick on a dashboard, so it is not offered as one."""
    module = real()
    switch = FakeKillSwitch(module)
    outcome = run(module, healthy_probes(module, kill_switch=switch), kill_switch="skip")
    assert switch.performed == [], "--kill-switch skip drove the switch anyway."
    assert outcome["kill_switch_stop"] and outcome["kill_switch_restore"]
    assert "Skipping is not a result" in outcome["kill_switch_stop"]


# ══════════════════════════════════════════════════════════════════════════════════════
#  9 · the program's own contract — exit code, masking, and no apply anywhere
# ══════════════════════════════════════════════════════════════════════════════════════


def test_an_unsatisfied_check_produces_a_non_zero_exit_and_names_itself(tmp_path, capsys):
    module = real()
    out = tmp_path / "dry.json"
    code = module.main(
        ["--kill-switch", "dry", "--out", str(out)],
        probes=healthy_probes(
            module, terraform=FakeTerraform({"api_function_url": {"value": None}})
        ),
    )
    assert code == module.EXIT_UNSATISFIED, (
        f"the program exited {code} with checks unsatisfied. A verifier that exits 0 on a "
        "reading it could not take is a verifier nobody needs."
    )
    printed = capsys.readouterr().out
    assert "COULD NOT BE SATISFIED" in printed
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["verdict"] == "NOT SATISFIED"
    assert document["unsatisfied_ids"], "the evidence names no unsatisfied check."
    for check in document["checks"]:
        assert check["source"] == "synthetic", (
            "a check produced under fault injection is recorded as a LIVE reading. That is "
            "how a synthetic result gets cited as a measurement."
        )


def test_a_fully_satisfied_run_exits_zero(tmp_path):
    """The other half of the exit contract. Without it, exit 1 could be unconditional."""
    module = real()
    code = module.main(
        ["--kill-switch", "live", "--yes", "--out", str(tmp_path / "green.json")],
        probes=healthy_probes(module),
    )
    assert code == module.EXIT_OK, (
        f"a world in which every check is satisfied exited {code}. If this program can only "
        "ever exit non-zero, its exit code carries no information."
    )


def test_live_kill_switch_without_yes_is_a_usage_error():
    module = real()
    assert (
        module.main(["--kill-switch", "live"], probes=healthy_probes(module)) == module.EXIT_USAGE
    )


def test_the_account_id_is_masked_everywhere_it_could_appear(tmp_path):
    """D2/R9: no account id in anything tracked. The masker is blunt and that is deliberate."""
    module = real()
    leaky = module.Unavailable(
        "User: arn:aws:iam::123456789012:user/mainline-dev is not authorized to perform "
        "cloudwatch:DescribeAlarms"
    )
    out = tmp_path / "masked.json"
    module.main(
        ["--kill-switch", "skip", "--out", str(out)],
        probes=healthy_probes(module, aws=FakeAws(leaky)),
    )
    text = out.read_text(encoding="utf-8")
    assert "123456789012" not in text, "an account id reached the evidence file."
    assert "<account>" in text, "the masker did not fire on the message that carried the id."


def test_the_kill_switches_own_partial_mask_is_collapsed_too(tmp_path):
    """Eight of twelve digits published forever is a narrower search, not a private one.

    ``kill_switch.sh`` prints ``0229REDACTED8246`` — right for a terminal, wrong for a
    tracked file. R9 says ``<account>`` in everything tracked, and a value that "looks
    masked already" is exactly the one that gets waved through.
    """
    module = real()
    out = tmp_path / "partial.json"
    switch = FakeKillSwitch(
        module,
        status=module.Ran(4, "account=1234REDACTED9012  region=ap-southeast-1", ""),
    )
    module.main(
        ["--kill-switch", "dry", "--out", str(out)],
        probes=healthy_probes(module, kill_switch=switch),
    )
    text = out.read_text(encoding="utf-8")
    assert "REDACTED" not in text, (
        "kill_switch.sh's first-four/last-four mask reached a tracked evidence file intact. "
        "Eight known digits plus a known region is not anonymity."
    )
    assert "<account>" in text


def test_the_program_knows_no_terraform_verb_but_output():
    """A grep, deliberately. `apply` must not be reachable from this file at all."""
    source = _source()
    for forbidden in ('"apply"', '"destroy"', '"taint"', '"import"', "'apply'"):
        assert forbidden not in source, (
            f"{forbidden!r} appears in post_apply_verify.py. This program reads state and "
            "measures a deployment; it never changes one, and the orchestrator applies only "
            "after the founder re-authorises."
        )
    assert '"output", "-json"' in source, (
        "the Terraform argument list is no longer the literal `output -json`. If it became "
        "assembled from input, a verb could be smuggled into it."
    )


def test_no_check_can_report_satisfied_without_a_reason():
    """Every Check carries a why. A green with no sentence behind it is a green nobody can audit."""
    module = real()
    checks, _ = module.verify(healthy_probes(module), args_for(module), REPO_ROOT)
    for check in checks:
        assert check.why.strip(), f"check {check.id!r} carries an empty `why`."
        assert isinstance(check.satisfied, bool), (
            f"check {check.id!r} reports {check.satisfied!r}. The vocabulary is a plain "
            "bool on purpose: a soft middle is where an unapplied stack eventually reads "
            "as a pass."
        )


# ══════════════════════════════════════════════════════════════════════════════════════
#  10 · the kill switch has two spellings, and "cannot be driven" must be true when said
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_powershell_spelling_of_every_flag_matches_kill_switch_ps1():
    """`--expect-account` -> `-ExpectAccount`. Checked against the .ps1's own parameters.

    Derived from the script rather than asserted here: a mapping that agreed with a
    remembered parameter list would keep agreeing after the script renamed one, and the
    failure would only appear the first time somebody reached for the kill switch.
    """
    module = real()
    ps1 = (REPO_ROOT / "scripts" / "deploy" / "kill_switch.ps1").read_text(encoding="utf-8")
    for flag in ("--status", "--dry-run", "--stop", "--restore", "--yes", "--expect-account"):
        spelled = module._powershell_flags([flag])[0]
        assert f".PARAMETER {spelled[1:]}" in ps1, (
            f"{flag} maps to {spelled}, which kill_switch.ps1 does not declare as a "
            "parameter. The two spellings of the lever have drifted, and the driver would "
            "hand PowerShell a flag it does not know at the moment the demo needs stopping."
        )


def test_a_missing_interpreter_is_a_refusal_and_not_a_pass(tmp_path):
    """ "The kill switch could not be driven" is unsatisfied, never skipped."""
    module = real()
    driver = module.KillSwitchDriver(tmp_path / "kill_switch.sh", function="x")
    with pytest.raises(module.Unavailable) as caught:
        driver.status()
    assert "NOT driven" in str(caught.value), (
        "the refusal does not say that the switch was not driven. An operator reading this "
        "at 3 a.m. must not be able to mistake it for a clean status."
    )
