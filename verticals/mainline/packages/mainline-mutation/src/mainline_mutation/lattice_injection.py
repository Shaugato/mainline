# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The injection point that lets the harness run against a DELIBERATELY CRIPPLED lattice.

WHY THIS EXISTS (PL-2)
----------------------
A harness that has only ever reported a kill rate of 1.0 has not been observed
to assert anything.  The first artefact this worker produces is a run in which a
named mutation class **survives**, and the way to produce one honestly is to
disable a rule and watch the class that rule owns stop being detected.

WHY IT IS HERE AND NOT IN ``mainline_domain.lattice``
------------------------------------------------------
Nothing in the lattice knows this exists.  ``decide()`` and ``explain()`` are
unchanged, un-parameterised and un-monkeypatched: this module re-runs the same
public ``RULES`` catalogue with a subset, using the same minimiser and the same
verdict constructor.  A ``disabled_rules`` argument threaded into the real
lattice would be a switch that could be reached from a gate path, and a gate
whose rules can be turned off by an argument is not a gate.

The consequence is worth stating plainly: the crippled run is not the lattice
with a flag set.  It is a **different function**, in a measurement package,
which happens to agree with the lattice exactly when ``disabled`` is empty —
and ``tests/e2e/mutation/test_injection.py`` asserts that agreement over every
fixture pair rather than assuming it.
"""

from __future__ import annotations

from mainline_domain.contracts import CAT, AnchorSet, DeltaVerdict, RuleId
from mainline_domain.lattice import (
    LatticeDecision,
    RuleFinding,
    RuleInput,
    explain,
)
from mainline_domain.lattice.order import NEUTRAL
from mainline_domain.lattice.rules import RULES
from mainline_domain.lattice.version import LATTICE_VERSION
from mainline_domain.lattice.witness import (
    minimal_correction_set,
    minimal_unsatisfiable_subset,
    verdict,
    verdict_of,
    witnesses_of,
)
from mainline_domain.registry.model import SafeDirectionRegistry

__all__ = ["ALL_RULE_IDS", "decide_with", "explain_with"]

ALL_RULE_IDS: tuple[RuleId, ...] = tuple(rule_id for rule_id, _ in RULES)


def explain_with(
    reference: CAT | None,
    descendant: CAT | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
    disabled: frozenset[str] = frozenset(),
) -> LatticeDecision:
    """Run the nine rules minus ``disabled`` and fold them exactly as the lattice does.

    With ``disabled`` empty this delegates to the real
    :func:`mainline_domain.lattice.explain` — not a copy of it — so the intact
    arm of every published run is the production code path and nothing else.

    :raises ValueError: when ``disabled`` names something that is not a rule id.
        A typo would silently disable nothing and the crippled run would report
        the intact number under a crippled label, which is the worst possible
        failure for a red-before-green artefact.
    """
    unknown = sorted(disabled - set(ALL_RULE_IDS))
    if unknown:
        raise ValueError(
            f"{unknown} are not rule ids; the nine are {list(ALL_RULE_IDS)}. A typo here would "
            "disable nothing and publish the intact number under a crippled label"
        )
    if not disabled:
        return explain(
            reference,
            descendant,
            registry,
            as_of,
            reference_anchors=reference_anchors,
            descendant_anchors=descendant_anchors,
        )

    inp = RuleInput(
        reference=reference,
        descendant=descendant,
        registry=registry,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    )
    findings: list[RuleFinding] = []
    for rule_id, predicate in RULES:
        if rule_id in disabled:
            continue
        findings.extend(predicate(inp))

    decided = verdict_of(findings) if findings else NEUTRAL
    minimal = minimal_unsatisfiable_subset(findings, decided)
    repair = minimal_correction_set(findings)
    return LatticeDecision(
        verdict=verdict(decided, "lattice", witnesses_of(minimal), minimal=True),
        findings=tuple(findings),
        minimal=minimal,
        repair=repair,
        anchors_considered=reference_anchors is not None and descendant_anchors is not None,
        lattice_version=f"{LATTICE_VERSION}+crippled({','.join(sorted(disabled))})",
        registry_commit=registry.as_of_commit,
    )


def decide_with(
    reference: CAT | None,
    descendant: CAT | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
    disabled: frozenset[str] = frozenset(),
) -> DeltaVerdict:
    """The verdict alone.  A thin projection of :func:`explain_with`."""
    return explain_with(
        reference,
        descendant,
        registry,
        as_of,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
        disabled=disabled,
    ).verdict
