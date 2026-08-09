# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""End to end: a hostile wire, through the real call path, into the ratchet.

The property tests one directory over reason about ``OracleVerdict`` values
constructed in Python.  This module refuses that shortcut and drives the whole of
Path B — ``build_untrusted_text`` → ``quarantined_call`` → schema validation →
``to_verdict`` → ``resolve`` — from response bodies committed in
``tests/fixtures/domain/oracle/adversary/hostile_responses.json``.

The claim being made here cannot be made any other way: *no byte sequence an
attacker can return from the model clears a gate.*  A test that builds the verdict
itself has assumed away the parser, the schema, the deterministic verifier and the
band map, which is four of the five places the attack would actually land.

**The one thing that must NOT be an abstention.**  ``errors.py`` draws a line
between "the model could not answer" and "we are misconfigured", and folding the
second into the first would emit ledger rows saying a model declined to answer
questions that were never put to it.  ``test_an_unrecognised_failure_propagates``
is that line, asserted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from _adversary import path_a_verdict
from mainline_delta_oracle.cassettes import ScriptedTransport
from mainline_delta_oracle.oracle import PROMPT_VERSION, AdjudicationOracle
from mainline_delta_oracle.request import DeltaOracleRequest, OriginContext
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.resolution import abstention_code_of, explain, requires_silence_record

_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "domain"
    / "oracle"
    / "adversary"
    / "hostile_responses.json"
)

_CORPUS: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))
_CASES: list[dict[str, Any]] = _CORPUS["cases"]
_CASE_IDS = [case["name"] for case in _CASES]

_ORIGIN = OriginContext(
    event_summary=(
        "A fitter entered the P-101A housing during a shutdown while the discharge line "
        "remained pressurised. The atmosphere was not retested after the first hour. The "
        "fitter was overcome and did not recover."
    ),
    severity=5,
    occurred_on="2019-07-14",
)


def _request() -> DeltaOracleRequest:
    return DeltaOracleRequest(
        ancestor_text=_CORPUS["clause_a"],
        descendant_text=_CORPUS["clause_b"],
        ancestor_cat=None,
        descendant_cat=None,
        parameter_hint="gas_test_interval",
        prompt_version=PROMPT_VERSION,
        origin=_ORIGIN,
        source_sha256="",
    )


def _classify(bodies: list[dict[str, Any]]):
    oracle = AdjudicationOracle(transport=ScriptedTransport(bodies))
    return oracle.classify_with_provenance(_request())


# ── the corpus is real ──────────────────────────────────────────────────────────


def test_the_corpus_is_declared_synthetic_and_adversarial() -> None:
    """Provenance is stated, never implied — and never confused with a recording."""
    assert _CORPUS["provenance"] == "synthetic-adversarial"
    assert len(_CASES) >= 12
    assert len({case["name"] for case in _CASES}) == len(_CASES)
    assert all(case["bodies"] for case in _CASES)
    assert "120 minutes" in _CORPUS["clause_b"], "clause B must be a real weakening"
    assert "30 minutes" in _CORPUS["clause_a"]


# ── each hostile body, through the real path ────────────────────────────────────


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_each_hostile_body_reaches_its_declared_outcome(case: dict[str, Any]) -> None:
    """The fixture's expectation is the assertion; widening it is a visible diff."""
    outcome = _classify(list(case["bodies"]))
    verdict = outcome.verdict

    assert verdict.abstained is case["expect_abstained"], (
        f"{case['name']}: expected abstained={case['expect_abstained']}, "
        f"got {verdict.abstained} (rationale: {verdict.rationale[:160]!r})"
    )
    if case["expect_code"] is not None:
        assert abstention_code_of(verdict.rationale) == case["expect_code"]
    if case["expect_label"] is not None:
        assert verdict.label.value == case["expect_label"]
    assert 0.0 <= verdict.confidence <= 1.0, "a confidence outside the contract escaped the mapper"
    assert verdict.prompt_version == PROMPT_VERSION


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_no_hostile_body_clears_a_lattice_weakening(case: dict[str, Any]) -> None:
    """The money assertion, end to end, once per attack.

    Path A found a weakening.  The wire returns the attacker's best effort.  The
    delta of record still carries force, so the merge is still refused.
    """
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    verdict = _classify(list(case["bodies"])).verdict
    resolved = explain(weaken, verdict, theta=0.75)
    assert force(resolved.verdict.delta) >= force(ControlDelta.WEAKEN), (
        f"{case['name']} cleared a lattice weakening: {resolved.verdict.delta.value}"
    )
    assert resolved.verdict.witnesses == weaken.witnesses
    assert resolved.verdict.basis != "human"


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_every_abstention_is_ledgerable(case: dict[str, Any]) -> None:
    """P5: an abstention that writes no arithmetic is a silence nobody can audit."""
    verdict = _classify(list(case["bodies"])).verdict
    if not verdict.abstained:
        return
    resolved = explain(path_a_verdict(ControlDelta.RESTATE), verdict, theta=0.75)
    assert requires_silence_record(resolved) is True
    assert abstention_code_of(verdict.rationale) is not None, (
        "an abstention whose rationale carries no code cannot be classified in the ledger"
    )


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_provenance_survives_every_attack(case: dict[str, Any]) -> None:
    """§8.2 requires a replayability record on every agent action, including the failed ones."""
    provenance = _classify(list(case["bodies"])).provenance
    assert provenance["prompt_version"] == PROMPT_VERSION
    assert provenance["profile_id"] == "adjudication"
    assert provenance["outcome"] in {"ok", "abstained"}
    assert provenance.get("cassette_key") or provenance.get("input_sha256"), (
        "a call with no request identity cannot be tied back to what was sent"
    )


# ── the transport itself misbehaving ────────────────────────────────────────────


class ThrottlingException(Exception):
    """Shaped like the botocore error, without importing an SDK the offline lane lacks."""


class ReadTimeoutError(Exception):
    """Named the way botocore names it; the classifier matches on the class name."""


class ClientError(Exception):
    """A ``ClientError``-shaped exception whose code is read out of ``response``."""

    def __init__(self, code: str) -> None:
        """Build the minimal ``response`` mapping the classifier reads."""
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _RaisingTransport:
    """A transport that fails the way a hostile or broken network fails."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def invoke(
        self,
        request: object,  # noqa: ARG002 — the protocol's shape, deliberately unread
    ) -> object:
        raise self._error

    def warm(
        self,
        request: object,  # noqa: ARG002 — the protocol's shape, deliberately unread
        *,
        first_token: object,  # noqa: ARG002 — same
    ) -> object:
        raise self._error


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (ThrottlingException("slow down"), "throttled"),
        (ClientError("ServiceQuotaExceededException"), "throttled"),
        (ReadTimeoutError("read timed out"), "timeout"),
    ],
)
def test_a_transport_failure_is_an_abstention(error: Exception, expected_code: str) -> None:
    """A call that never completed is silence, and silence blocks."""
    oracle = AdjudicationOracle(transport=_RaisingTransport(error))  # type: ignore[arg-type]
    verdict = oracle.classify(_request())
    assert verdict.abstained is True
    assert abstention_code_of(verdict.rationale) == expected_code
    resolved = explain(path_a_verdict(ControlDelta.RESTATE), verdict, theta=0.75)
    assert force(resolved.verdict.delta) >= force(ControlDelta.WEAKEN)


def test_an_unrecognised_failure_propagates() -> None:
    """A broken deployment crashes; it does not manufacture a statement about a model.

    This is the assertion that stops ``classify`` from being a blanket swallow.  If
    it ever goes green by producing an abstention, the ledger has started
    recording model behaviour that never happened.
    """
    oracle = AdjudicationOracle(transport=_RaisingTransport(RuntimeError("driver exploded")))  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="driver exploded"):
        oracle.classify(_request())


def test_a_request_built_for_another_prompt_version_is_refused() -> None:
    """A prompt edit is a commit; answering under the wrong one falsifies the provenance."""
    stale = DeltaOracleRequest(
        ancestor_text=_CORPUS["clause_a"],
        descendant_text=_CORPUS["clause_b"],
        ancestor_cat=None,
        descendant_cat=None,
        parameter_hint=None,
        prompt_version="adjudication.v0+rubric.v0",
        origin=None,
        source_sha256="",
    )
    oracle = AdjudicationOracle(transport=ScriptedTransport([]))
    with pytest.raises(Exception, match="prompt_version") as raised:
        oracle.classify(stale)
    assert type(raised.value).__name__ == "PromptVersionMismatch"
