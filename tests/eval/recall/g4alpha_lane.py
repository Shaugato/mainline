# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The G4-alpha CI lane: run the five gates, record the colour, refuse to skip.

    python tests/eval/recall/g4alpha_lane.py --out evidence/recall/g4alpha-lane.json

This is the runner a CI job invokes. It exists because ``pytest -m g4alpha`` alone
cannot express the thing the lane has to enforce: **the suite is required to be RED
right now**, and a job that simply fails on red would be permanently broken from the
first commit, which is how a red-before-green discipline gets quietly deleted.

So the lane compares the *observed* colour against the *committed* expectation in
``g4alpha_expected.json`` and fails on the difference. Today the file says ``RED``, the
gates are red, and the lane is green. When a retriever lands and the gates go green, the
lane fails — loudly, with the flip procedure in the message — until someone changes the
expectation in a pull request that shows up in blame. After that flip, any regression to
RED fails the lane. The expectation ratchets; the colour is recorded either way.

Three outcomes, three exit codes
--------------------------------
=====  ==================================================================================
``0``  observed colour == committed expectation. The lane did its job.
``1``  observed colour != committed expectation. Either the gates regressed, or they went
       green and the expectation has not been flipped yet. Both need a human.
``2``  the lane could not determine a colour at all: a gate test was **skipped**, errored
       during setup, or the collected test set does not match the gate set. A lane that
       reports a colour it did not measure is worse than a lane that fails.
=====  ==================================================================================

Why "skipped" is exit 2 and not a shrug
----------------------------------------
A release gate that can be skipped because a corpus is missing, a plugin is absent or a
marker was mistyped is not a release gate. :mod:`corpus_resolution` already guarantees a
corpus always resolves (falling back to the committed self-test corpus, stamped SYNTHETIC
and PRELIMINARY), so there is no legitimate reason for one of these five tests to be
skipped. If one is, the lane refuses to publish a colour.

What the lane trusts
---------------------
pytest is the authority on the colour: the lane runs the marked suite in-process and
reads the per-test reports. The structured per-gate reasons in the artefact come from a
second, independent evaluation against the committed default backend
(:class:`~trappoint_recall.eval.backend.NullBackend`), recorded as
``reference_evaluation`` and clearly labelled. When the suite is later pointed at a real
retriever the two colours will differ; that is expected and is reported as a fact, never
as a failure — the lane must not become the thing that stops a working retriever from
being measured.

The cross-check that *is* fatal is structural: the set of tests carrying the ``g4alpha``
marker must correspond exactly to
:data:`~trappoint_recall.eval.gates.G4ALPHA_GATE_IDS`. That catches a gate added with no
test and a test deleted with no gate, and it cannot produce a false alarm when the
backend changes.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest

# ``corpus_resolution`` sits beside this file. When the lane is run as a script its own
# directory is already sys.path[0], but making it explicit means the lane also works when
# invoked through a wrapper that manipulates the path.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from corpus_resolution import (  # noqa: E402
    SUITE_DIR,
    corpus_provenance,
    ensure_import_paths,
    resolve_corpus_path,
)

ensure_import_paths()

from trappoint_recall.eval.backend import NullBackend  # noqa: E402
from trappoint_recall.eval.corpus import load_corpus  # noqa: E402
from trappoint_recall.eval.gates import (  # noqa: E402
    G4ALPHA_GATE_IDS,
    evaluate_g4alpha,
    overall_status,
)
from trappoint_recall.eval.harness import compute_metrics, run_evaluation_sync  # noqa: E402
from trappoint_recall.eval.report import gate_status_document, render_gate_markdown  # noqa: E402

__all__ = [
    "EXIT_CANNOT_DETERMINE",
    "EXIT_MATCHES_EXPECTATION",
    "EXIT_UNEXPECTED_COLOUR",
    "EXPECTATION_PATH",
    "GATE_TEST_NAMES",
    "Expectation",
    "LaneReport",
    "OutcomeCollector",
    "TestOutcome",
    "build_parser",
    "colour_from_outcomes",
    "disqualifying_outcomes",
    "load_expectation",
    "main",
    "reconcile",
    "run_lane",
]

EXIT_MATCHES_EXPECTATION: Final = 0
EXIT_UNEXPECTED_COLOUR: Final = 1
EXIT_CANNOT_DETERMINE: Final = 2

EXPECTATION_PATH: Final[Path] = SUITE_DIR / "g4alpha_expected.json"
GATE_SUITE_PATH: Final[Path] = SUITE_DIR / "test_g4alpha_gates.py"

GATE_TEST_NAMES: Final[Mapping[str, str]] = {
    "test_retro_recall_at_3_on_severity_5": "retro_recall_at_3_sev5",
    "test_precision_at_block": "p_at_block",
    "test_nuisance_rate": "nuisance_rate",
    "test_mean_blocking_checks_per_permit": "mean_blocking_checks_per_permit",
    "test_silence_conservation_law": "conservation_l3",
}
"""Test function name -> gate id. Committed here so the lane can prove the marked suite
covers every gate and nothing else. Adding a gate without a test, or deleting a test
without its gate, makes the lane exit 2 rather than publish a colour over a hole."""

_MAPPED_GATES = frozenset(GATE_TEST_NAMES.values())
if _MAPPED_GATES != frozenset(G4ALPHA_GATE_IDS):  # pragma: no cover - import-time guard
    raise RuntimeError(
        "g4alpha_lane.GATE_TEST_NAMES has drifted from gates.G4ALPHA_GATE_IDS: "
        f"lane maps {sorted(_MAPPED_GATES)}, package defines {sorted(G4ALPHA_GATE_IDS)}. "
        "One of the two was changed without the other; the lane refuses to run until "
        "they agree, because a lane that reports on four of five gates reports nothing."
    )

_DISQUALIFYING: Final[frozenset[str]] = frozenset({"skipped", "errored", "xfailed", "xpassed"})
"""Outcomes that make the run unusable as a colour measurement. ``xfailed`` and
``xpassed`` are in here on purpose: marking a release gate ``xfail`` converts a refusal
into a decoration, and the lane must notice that the same way it notices a skip."""

_OUTPUT_TAIL_CHARS: Final = 4000


# --------------------------------------------------------------------------------------
# Collecting outcomes from pytest
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TestOutcome:
    """What happened to one gate test, flattened across pytest's three phases."""

    nodeid: str
    test_name: str
    gate_id: str
    outcome: str
    duration_s: float
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "nodeid": self.nodeid,
            "test_name": self.test_name,
            "gate_id": self.gate_id,
            "outcome": self.outcome,
            "duration_s": round(self.duration_s, 4),
            "detail": self.detail,
        }


class OutcomeCollector:
    """A pytest plugin that records one flattened outcome per test.

    pytest reports setup, call and teardown separately. The lane needs one verdict per
    test, and it needs to distinguish *failed* (the gate is red, which is information)
    from *errored* and *skipped* (the gate was never evaluated, which is not).
    """

    def __init__(self) -> None:
        self.outcomes: dict[str, TestOutcome] = {}

    # pytest hook; the signature is fixed by pytest.
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        nodeid = report.nodeid
        test_name = nodeid.rpartition("::")[2]
        gate_id = GATE_TEST_NAMES.get(test_name, "")

        outcome: str | None = None
        if report.when in ("setup", "teardown") and report.failed:
            outcome = "errored"
        elif report.when == "setup" and report.skipped:
            outcome = "skipped"
        elif report.when == "call":
            if hasattr(report, "wasxfail"):
                outcome = "xpassed" if report.passed else "xfailed"
            elif report.skipped:
                outcome = "skipped"
            elif report.failed:
                outcome = "failed"
            elif report.passed:
                outcome = "passed"
        if outcome is None:
            return

        previous = self.outcomes.get(nodeid)
        # setup/teardown errors win over a call verdict: a test whose teardown blew up was
        # not cleanly measured, whatever the assertion said.
        if previous is not None and previous.outcome in _DISQUALIFYING | {"errored"}:
            return

        self.outcomes[nodeid] = TestOutcome(
            nodeid=nodeid,
            test_name=test_name,
            gate_id=gate_id,
            outcome=outcome,
            duration_s=float(getattr(report, "duration", 0.0)),
            detail=_first_line(report.longrepr),
        )


def _first_line(longrepr: object) -> str:
    if longrepr is None:
        return ""
    text = str(longrepr).strip()
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("E ") or stripped.startswith("E\t"):
            return stripped[1:].strip()
    return text.splitlines()[0].strip()


def colour_from_outcomes(outcomes: Sequence[TestOutcome]) -> str:
    """``GREEN`` only when every gate test passed. Anything else is ``RED``.

    Called only after :func:`disqualifying_outcomes` has come back empty, so "anything
    else" here means "failed", not "never ran".
    """
    if not outcomes:
        return "RED"
    return "GREEN" if all(o.outcome == "passed" for o in outcomes) else "RED"


def disqualifying_outcomes(outcomes: Sequence[TestOutcome]) -> tuple[TestOutcome, ...]:
    """Outcomes that mean a gate was never evaluated. Non-empty implies exit 2."""
    return tuple(o for o in outcomes if o.outcome in _DISQUALIFYING or o.outcome == "errored")


# --------------------------------------------------------------------------------------
# The committed expectation
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Expectation:
    """The colour this repository currently commits to, and why."""

    colour: str
    gate_tests: int
    since: str
    reason: str
    flip_procedure: str
    authority: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "expected": self.colour,
            "expected_gate_tests": self.gate_tests,
            "since": self.since,
            "reason": self.reason,
            "flip_procedure": self.flip_procedure,
            "authority": self.authority,
            "source": self.source,
        }


class LaneError(RuntimeError):
    """The lane cannot run or cannot trust what it measured. Always exit 2."""


def load_expectation(path: Path = EXPECTATION_PATH) -> Expectation:
    """Read ``g4alpha_expected.json``, refusing anything ambiguous."""
    if not path.is_file():
        raise LaneError(
            f"the committed expectation {path} is missing. The lane will not infer one: "
            "without it, a suite that silently went green would look like a pass."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LaneError(f"{path}: not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LaneError(f"{path}: expected a JSON object")

    colour = payload.get("expected")
    if colour not in ("RED", "GREEN"):
        raise LaneError(f"{path}: 'expected' must be exactly 'RED' or 'GREEN', got {colour!r}")
    gate_tests = payload.get("expected_gate_tests")
    if not isinstance(gate_tests, int) or isinstance(gate_tests, bool) or gate_tests < 1:
        raise LaneError(f"{path}: 'expected_gate_tests' must be a positive integer")
    return Expectation(
        colour=colour,
        gate_tests=gate_tests,
        since=str(payload.get("since", "")),
        reason=str(payload.get("reason", "")),
        flip_procedure=str(payload.get("flip_procedure", "")),
        authority=str(payload.get("authority", "")),
        source=str(path),
    )


# --------------------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LaneReport:
    """Everything the lane observed, and the single verdict it draws from it."""

    observed_colour: str
    expected_colour: str
    verdict: str
    exit_code: int
    message: str
    outcomes: tuple[TestOutcome, ...]
    expectation: Expectation
    corpus: Mapping[str, object]
    reference_evaluation: Mapping[str, object]
    pytest_exit_status: int
    pytest_output_tail: str

    @property
    def counts(self) -> dict[str, int]:
        tally = {
            "passed": 0,
            "failed": 0,
            "errored": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
        }
        for outcome in self.outcomes:
            tally[outcome.outcome] = tally.get(outcome.outcome, 0) + 1
        return tally

    @property
    def never_skipped(self) -> bool:
        return not disqualifying_outcomes(self.outcomes)

    def to_dict(self) -> dict[str, object]:
        reference_colour = self.reference_evaluation.get("lane_colour")
        return {
            "lane": "g4alpha",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "observed_colour": self.observed_colour,
            "expected_colour": self.expected_colour,
            "verdict": self.verdict,
            "exit_code": self.exit_code,
            "message": self.message,
            "never_skipped": self.never_skipped,
            "counts": self.counts,
            "tests": [o.to_dict() for o in self.outcomes],
            "gates_covered": sorted(o.gate_id for o in self.outcomes if o.gate_id),
            "expectation": self.expectation.to_dict(),
            "corpus": dict(self.corpus),
            "reference_evaluation": dict(self.reference_evaluation),
            "reference_colour_matches_observed": reference_colour == self.observed_colour,
            "reference_backend": "trappoint_recall.eval.backend:NullBackend",
            "pytest_exit_status": self.pytest_exit_status,
            "pytest_output_tail": self.pytest_output_tail,
        }

    def render(self) -> str:
        counts = self.counts
        tally = ", ".join(f"{k}={v}" for k, v in counts.items() if v) or "none collected"
        lines = [
            f"G4alpha lane: {self.verdict}",
            f"  observed colour : {self.observed_colour}",
            f"  expected colour : {self.expected_colour} (from {self.expectation.source})",
            f"  outcomes        : {tally}",
            f"  corpus          : {self.corpus.get('label', self.corpus.get('path'))}",
            f"  {self.message}",
        ]
        return "\n".join(lines)


def reconcile(
    outcomes: Sequence[TestOutcome], expectation: Expectation
) -> tuple[str, str, int, str]:
    """Turn observed outcomes into ``(colour, verdict, exit_code, message)``.

    Pure, so the decision table is testable without invoking pytest inside pytest.
    """
    observed_names = {o.test_name for o in outcomes}
    expected_names = set(GATE_TEST_NAMES)

    if not outcomes:
        return (
            "UNDETERMINED",
            "UNDETERMINED",
            EXIT_CANNOT_DETERMINE,
            "no test carrying the 'g4alpha' marker was collected. Either the marker was "
            "renamed or the suite did not import; both are lane failures, because an "
            "uncollected gate reports no colour at all.",
        )

    missing = sorted(expected_names - observed_names)
    unexpected = sorted(observed_names - expected_names)
    if missing or unexpected:
        return (
            "UNDETERMINED",
            "UNDETERMINED",
            EXIT_CANNOT_DETERMINE,
            "the marked suite does not correspond to the gate set: "
            f"missing {missing}, unexpected {unexpected}. Every gate in "
            "G4ALPHA_GATE_IDS must have exactly one marked test and vice versa.",
        )

    if len(outcomes) != expectation.gate_tests:
        return (
            "UNDETERMINED",
            "UNDETERMINED",
            EXIT_CANNOT_DETERMINE,
            f"collected {len(outcomes)} gate tests but the committed expectation names "
            f"{expectation.gate_tests}. The lane will not publish a colour measured over "
            "a different number of gates than it committed to.",
        )

    blocked = disqualifying_outcomes(outcomes)
    if blocked:
        detail = ", ".join(f"{o.test_name}={o.outcome}" for o in blocked)
        return (
            "UNDETERMINED",
            "UNDETERMINED",
            EXIT_CANNOT_DETERMINE,
            f"{len(blocked)} gate test(s) were never evaluated: {detail}. A release gate "
            "that can be skipped or xfailed is not a release gate; this lane records "
            "red or green and refuses to record anything else.",
        )

    observed = colour_from_outcomes(outcomes)
    if observed == expectation.colour:
        if observed == "RED":
            message = (
                "RED, as committed. PL-2 red-before-green: the gates are required to fail "
                "until a retriever exists, and they failed for the right reason — the "
                "floors were evaluated and not met, not skipped. " + expectation.reason
            )
        else:
            message = "GREEN, as committed. Any regression to RED will fail this lane from here on."
        return (observed, "AS_EXPECTED", EXIT_MATCHES_EXPECTATION, message)

    if observed == "GREEN" and expectation.colour == "RED":
        message = (
            "the gates now PASS but the repository still commits to RED. This is a real "
            "result and it needs a human: "
            + (expectation.flip_procedure or "flip the expectation to GREEN in a pull request.")
        )
    else:
        message = (
            "the gates REGRESSED to RED after the repository committed to GREEN. Failing "
            "gates cannot be waived by editing the expectation back; fix the retriever or "
            "execute the pre-committed DEMOTE response (channels C and D advisory-only)."
        )
    return (observed, "UNEXPECTED", EXIT_UNEXPECTED_COLOUR, message)


# --------------------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------------------


def _reference_evaluation(corpus_path: Path) -> tuple[Mapping[str, object], str]:
    """Evaluate the gates directly, for the structured per-gate reasons in the artefact.

    Independent of the pytest run and clearly labelled as such: this is what the
    *committed default backend* yields. It is evidence, never the verdict.
    """
    corpus = load_corpus(corpus_path)
    run = run_evaluation_sync(NullBackend(), corpus, k=10)
    bundle = compute_metrics(run, corpus)
    results = evaluate_g4alpha(bundle)
    document = gate_status_document(bundle, results)
    document["overall_status"] = overall_status(results)
    return document, render_gate_markdown(bundle, results)


def run_lane(
    *,
    corpus_path: Path | None = None,
    expectation_path: Path = EXPECTATION_PATH,
    extra_pytest_args: Sequence[str] = (),
) -> tuple[LaneReport, str]:
    """Run the marked suite, evaluate the reference gates, and reconcile.

    Returns the report and the rendered markdown of the reference evaluation.
    """
    expectation = load_expectation(expectation_path)
    resolved = corpus_path if corpus_path is not None else resolve_corpus_path()
    provenance = corpus_provenance(resolved)
    if not provenance.get("loaded", False):
        raise LaneError(
            f"the corpus at {resolved} would not load: {provenance.get('error')}. "
            "The lane reports this as an inability to run, never as a pass."
        )

    collector = OutcomeCollector()
    args = [
        str(GATE_SUITE_PATH),
        "-m",
        "g4alpha",
        "-p",
        "no:cacheprovider",
        "--no-header",
        "-q",
        *extra_pytest_args,
    ]
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        status = int(pytest.main(args, plugins=[collector]))
    output = captured.getvalue()

    outcomes = tuple(sorted(collector.outcomes.values(), key=lambda o: o.nodeid))
    colour, verdict, exit_code, message = reconcile(outcomes, expectation)
    reference, markdown = _reference_evaluation(resolved)

    report = LaneReport(
        observed_colour=colour,
        expected_colour=expectation.colour,
        verdict=verdict,
        exit_code=exit_code,
        message=message,
        outcomes=outcomes,
        expectation=expectation,
        corpus=provenance,
        reference_evaluation=reference,
        pytest_exit_status=status,
        pytest_output_tail=output[-_OUTPUT_TAIL_CHARS:],
    )
    return report, markdown


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g4alpha_lane",
        description=(
            "Run the five G4-alpha gates, record the colour, and compare it against the "
            "colour this repository commits to in g4alpha_expected.json."
        ),
        epilog=(
            "Exit codes: 0 observed colour matches the committed expectation, 1 it does "
            "not (the gates regressed, or they went green and the expectation has not "
            "been flipped), 2 the lane could not determine a colour — a gate was skipped, "
            "errored, or the marked suite does not match the gate set."
        ),
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help=(
            "corpus directory; default is the standard resolution order "
            "($TRAPPOINT_RECALL_CORPUS, then GS0, then the committed self-test corpus)"
        ),
    )
    parser.add_argument(
        "--expectation",
        type=Path,
        default=EXPECTATION_PATH,
        help="path to the committed expectation file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write the JSON lane artefact here (default: stdout)",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="also write the gate status page as markdown, for a CI job summary",
    )
    parser.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="extra argument passed through to pytest; repeatable",
    )
    return parser


def _write(text: str, out: Path | None) -> None:
    if out is None:
        sys.stdout.write(text)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    sys.stderr.write(f"written: {out}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report, markdown = run_lane(
            corpus_path=args.corpus,
            expectation_path=args.expectation,
            extra_pytest_args=list(args.pytest_arg),
        )
    except LaneError as exc:
        sys.stderr.write(f"g4alpha lane: cannot run: {exc}\n")
        return EXIT_CANNOT_DETERMINE

    _write(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", args.out)
    if args.markdown_out is not None:
        _write(markdown, args.markdown_out)
    sys.stderr.write(report.render() + "\n")
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
