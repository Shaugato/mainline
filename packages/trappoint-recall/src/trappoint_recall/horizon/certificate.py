# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""M4 CUE HORIZON — the certified null.

The single most dangerous output this system can produce is *"no precursors found"*, because
to the person reading it that is indistinguishable from *"there are none"*. An empty or
partial retrieval result is therefore **representable only with a coverage certificate bound
to an index generation**, and where coverage cannot be certified the verdict is
``UNDETERMINED`` and Proof of Exhausted Recall may not claim exhaustion.

The three verdicts, and what each is allowed to mean
----------------------------------------------------
``complete``
    Every candidate in the corpus was examined. Only an exhaustive scan can establish this,
    which is why migration 0087 carries ``complete_needs_a_basis_that_can_establish_it``:
    ``verdict <> 'complete' OR coverage_basis = 'full_scan'``. ANN is approximate; an
    arms-based basis can never support this word, and the database refuses the overclaim
    rather than trusting the orchestrator not to make it.

``partial``
    A known, named set of prefix trees was searched with a known ``k`` per arm, under a
    generation and a structural fingerprint that did not move during the run. This is the
    ordinary result, and it is the verdict under which PER's claim — exhaustion **of the
    retrieval that ran** — is exactly true.

``UNDETERMINED``
    We do not know what was searched. The generation moved mid-run, the fingerprint did not
    match the one the receipt will be read against, an arm did not execute, an arm executed
    without traversing its index, or a tree could not be counted. This is not an error and
    not a degradation ladder rung: it is a first-class result that gets stored, carried into
    the receipt, and blocks the exhaustion claim in code.

Why a scan fallback is ``UNDETERMINED`` and not "even better coverage"
---------------------------------------------------------------------
Measured ground truth F1: on this cluster the optimizer will **not** choose a prefix-
constrained vector index at demo scale, so every arm pins its index by name. An arm that then
did *not* traverse the named index did not merely take a slower path — the hint failed, which
means the index it names is not in the shape the run assumed. Reading rows off a table under
a filter tells us nothing about the tree the receipt is about to be quoted against. The
honest verdict is that we do not know.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from trappoint_recall.horizon.errors import CoverageRefused
from trappoint_recall.horizon.fingerprint import (
    IndexFingerprintInput,
    index_fingerprint,
)

__all__ = [
    "COVERAGE_BASES",
    "VERDICTS",
    "ArmCoverage",
    "CoverageBasis",
    "CoverageCertificate",
    "CoverageObservation",
    "Verdict",
    "certify",
]

CoverageBasis = Literal[
    "full_scan",
    "index_arms",
    "index_arms_plus_sweep",
    "fingerprint_mismatch",
    "unavailable",
]
Verdict = Literal["complete", "partial", "UNDETERMINED"]

#: ``mainline_meas.recall_certificate.coverage_basis``'s closed vocabulary (migration 0087).
COVERAGE_BASES: Final[tuple[str, ...]] = (
    "full_scan",
    "index_arms",
    "index_arms_plus_sweep",
    "fingerprint_mismatch",
    "unavailable",
)

#: ``mainline_meas.recall_certificate.verdict``'s closed vocabulary (migration 0087).
VERDICTS: Final[tuple[str, ...]] = ("complete", "partial", "UNDETERMINED")

#: The only basis that can carry a verdict of ``complete``. Mirrors the database CHECK, in
#: code, so the overclaim is refused before the round trip as well as during it.
_EXHAUSTIVE_BASIS: Final = "full_scan"


@dataclass(frozen=True, slots=True)
class ArmCoverage:
    """What one ANN arm actually did, as observed — never as intended."""

    arm_id: str
    executed: bool
    index_traversed: bool
    k: int
    returned: int

    def __post_init__(self) -> None:
        """Refuse an observation that contradicts itself."""
        if not self.arm_id:
            raise CoverageRefused("an arm observation must name its arm")
        if self.k < 0 or self.returned < 0:
            raise CoverageRefused(f"{self.arm_id}: k and returned must be non-negative")
        if not self.executed and (self.returned or self.index_traversed):
            raise CoverageRefused(
                f"{self.arm_id}: an arm that did not execute cannot have returned rows or "
                "traversed an index"
            )

    @property
    def certifiable(self) -> bool:
        """Whether this arm's contribution to coverage is known at all."""
        return self.executed and self.index_traversed


@dataclass(frozen=True, slots=True)
class CoverageObservation:
    """Everything the orchestrator observed about the index during one run."""

    fingerprint_input: IndexFingerprintInput
    index_generation_at_start: str
    index_generation_at_end: str
    arms: tuple[ArmCoverage, ...]
    sweep_ran: bool = False
    degraded: bool = False
    exhaustive_scan: bool = False
    expected_fingerprint: bytes | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Refuse an observation whose own fields disagree."""
        if not self.index_generation_at_start or not self.index_generation_at_end:
            raise CoverageRefused(
                "an index generation must be observed at both ends of the run; a run that "
                "did not look cannot certify that nothing moved"
            )
        if self.exhaustive_scan and self.degraded:
            raise CoverageRefused(
                "a run cannot claim an exhaustive scan while reporting degraded channels"
            )


@dataclass(frozen=True, slots=True)
class CoverageCertificate:
    """A row of ``mainline_meas.recall_certificate``, as a value.

    ``permits_exhaustion_claim`` is the property the PER builder consults; it is the code
    half of the mechanism whose database half is 0087's CHECK.
    """

    index_generation: str
    index_fingerprint: bytes | None
    coverage_basis: CoverageBasis
    verdict: Verdict
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Enforce, in code, the constraint the database also enforces."""
        if self.verdict not in VERDICTS:
            raise CoverageRefused(f"verdict {self.verdict!r} is outside {VERDICTS}")
        if self.coverage_basis not in COVERAGE_BASES:
            raise CoverageRefused(
                f"coverage_basis {self.coverage_basis!r} is outside {COVERAGE_BASES}"
            )
        if self.verdict == "complete" and self.coverage_basis != _EXHAUSTIVE_BASIS:
            raise CoverageRefused(
                "complete_needs_a_basis_that_can_establish_it: a verdict of 'complete' "
                f"requires coverage_basis='{_EXHAUSTIVE_BASIS}', not "
                f"{self.coverage_basis!r}. ANN is approximate; only an exhaustive scan can "
                "establish that the corpus was seen."
            )

    @property
    def permits_exhaustion_claim(self) -> bool:
        """Whether PER may claim exhaustion of the retrieval that ran under this certificate."""
        return self.verdict != "UNDETERMINED"

    def to_row(self) -> dict[str, Any]:
        """Return the insertable shape of ``mainline_meas.recall_certificate`` (0087).

        ``run_id`` is supplied by the writer, not here: a certificate is a statement about a
        retrieval, and binding it to a run is the persistence layer's job.
        """
        return {
            "index_generation": self.index_generation,
            "index_fingerprint": self.index_fingerprint,
            "coverage_basis": self.coverage_basis,
            "verdict": self.verdict,
        }

    def to_json(self) -> dict[str, Any]:
        """Wire form, including the reasons — which the row deliberately does not store."""
        return {
            "index_generation": self.index_generation,
            "index_fingerprint": (
                None if self.index_fingerprint is None else self.index_fingerprint.hex()
            ),
            "coverage_basis": self.coverage_basis,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "permits_exhaustion_claim": self.permits_exhaustion_claim,
        }


def _undetermined(
    generation: str,
    basis: CoverageBasis,
    reasons: Sequence[str],
    fingerprint: bytes | None,
) -> CoverageCertificate:
    """Build the one verdict that is never an exception."""
    return CoverageCertificate(
        index_generation=generation,
        index_fingerprint=fingerprint,
        coverage_basis=basis,
        verdict="UNDETERMINED",
        reasons=tuple(reasons),
    )


def certify(observation: CoverageObservation) -> CoverageCertificate:  # noqa: PLR0911
    # PLR0911: the return count IS the rule count. This function is an ordered cascade of
    # seven coverage rules, each of which decides the verdict outright; folding them into a
    # single exit would replace a list a reader can check against the docstring with an
    # accumulator they would have to simulate. The ordering is load-bearing and documented.
    """Turn an observation of a completed retrieval into a coverage certificate.

    The rules fire in this order, and the first that matches decides:

    1. the index generation moved during the run → ``UNDETERMINED`` / ``fingerprint_mismatch``;
    2. a tree could not be counted → ``UNDETERMINED`` / ``unavailable``;
    3. the fingerprint differs from the one expected → ``UNDETERMINED`` /
       ``fingerprint_mismatch``;
    4. an exhaustive scan was performed → ``complete`` / ``full_scan``;
    5. the run was degraded, or no arm ran → ``UNDETERMINED`` / ``unavailable``;
    6. any arm failed to execute or failed to traverse its named index → ``UNDETERMINED`` /
       ``unavailable``;
    7. otherwise → ``partial``, over ``index_arms`` or ``index_arms_plus_sweep``.

    This function never raises for poor coverage. It raises only for an observation that
    could not have been made.
    """
    generation = observation.index_generation_at_end
    reasons: list[str] = list(observation.notes)

    if observation.index_generation_at_start != observation.index_generation_at_end:
        reasons.append(
            f"index generation moved during the run: "
            f"{observation.index_generation_at_start!r} -> "
            f"{observation.index_generation_at_end!r}. The trees searched at the start are "
            "not the trees the receipt would be read against."
        )
        return _undetermined(generation, "fingerprint_mismatch", reasons, None)

    if not observation.fingerprint_input.fully_counted:
        reasons.append(
            "prefix tree(s) could not be counted: "
            + ", ".join(observation.fingerprint_input.uncounted())
            + ". An uncountable tree is the absence of a fact, not a fact about an empty one."
        )
        return _undetermined(generation, "unavailable", reasons, None)

    observed = index_fingerprint(observation.fingerprint_input)

    if (
        observation.expected_fingerprint is not None
        and observation.expected_fingerprint != observed
    ):
        reasons.append(
            f"index fingerprint {observed.hex()} does not match the expected "
            f"{observation.expected_fingerprint.hex()}. INSPECT skips vector indexes, so this "
            "is the only signal that a C-SPANN tree was rebuilt or re-partitioned."
        )
        return _undetermined(generation, "fingerprint_mismatch", reasons, observed)

    if observation.exhaustive_scan:
        reasons.append(
            "every candidate in the corpus was examined by an exhaustive scan, so coverage "
            "is complete rather than approximate"
        )
        return CoverageCertificate(
            index_generation=generation,
            index_fingerprint=observed,
            coverage_basis="full_scan",
            verdict="complete",
            reasons=tuple(reasons),
        )

    if observation.degraded:
        reasons.append(
            "the run completed on the deterministic channels only; the probabilistic reach "
            "of this retrieval is unknown, so its coverage cannot be certified"
        )
        return _undetermined(generation, "unavailable", reasons, observed)

    if not observation.arms:
        reasons.append("no ANN arm executed, so no prefix tree was searched")
        return _undetermined(generation, "unavailable", reasons, observed)

    unexecuted = [arm.arm_id for arm in observation.arms if not arm.executed]
    if unexecuted:
        reasons.append(
            f"arm(s) {unexecuted} did not execute; the trees they name went unsearched and "
            "the run cannot say what is in them"
        )
        return _undetermined(generation, "unavailable", reasons, observed)

    untraversed = [arm.arm_id for arm in observation.arms if not arm.index_traversed]
    if untraversed:
        reasons.append(
            f"arm(s) {untraversed} executed without traversing their named vector index. "
            "Every arm pins its index explicitly (measured ground truth F1), so a "
            "non-traversal means the hint failed and the index is not in the shape the run "
            "assumed."
        )
        return _undetermined(generation, "unavailable", reasons, observed)

    basis: CoverageBasis = "index_arms_plus_sweep" if observation.sweep_ran else "index_arms"
    reasons.append(
        f"{len(observation.arms)} arm(s) traversed their named index under generation "
        f"{generation!r}"
        + (
            "; the 256-d coarse sweep also ran, so a taxonomy misclassification was covered"
            if observation.sweep_ran
            else "; the coarse sweep did not run, so a taxonomy misclassification was not covered"
        )
    )
    return CoverageCertificate(
        index_generation=generation,
        index_fingerprint=observed,
        coverage_basis=basis,
        verdict="partial",
        reasons=tuple(reasons),
    )
