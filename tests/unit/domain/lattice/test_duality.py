# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A strengthen is the exact dual of a weaken under field inversion.

Read the same edit backwards and every orderable finding must come back
inverted: a deontic downgrade becomes an upgrade, a widened band becomes a
narrowed one, a dropped anchor becomes an added one, a removed control becomes an
introduced one.  Stated as an equation over
:func:`~mainline_domain.lattice.order.dual` rather than as nine paragraphs.

WHY THIS IS WORTH A PROPERTY TEST AND NOT A CODE REVIEW
--------------------------------------------------------
A rule that fires only in the weakening direction is untestable against itself.
Nine such rules, each hand-written, is nine chances for a table to be
half-populated — and a half-populated table does not fail loudly.  It reports
``restate`` on a real weakening, which is exactly the silence this product
exists to refuse (risk R-A1: the delta false negative is the residual risk).
Requiring the inverse to exist makes the omission of a cell a **test failure**
instead of a quiet asymmetry.

THE TWO CELLS THAT ARE DELIBERATELY NOT DUAL
---------------------------------------------
``orderable=False`` findings are their own inverse and are ``weaken`` in both
directions.  There are exactly two categories and this suite enumerates them, so
a third one cannot appear without a test failing:

1. **Polarity inversion** — ``MUST`` ↔ ``MUST_NOT`` (R1), upper bound ↔ lower
   bound (R3).  The control was turned around; neither reading is a tightening.
2. **Fail-closed abstention** — the registry declined, two quantities are not
   comparable, a slot became unreadable.  Reversing "I cannot tell" gives another
   "I cannot tell", and decision D6 resolves both to ``weaken``.
"""

from __future__ import annotations

from collections import Counter

from _lattice_fixtures import AS_OF
from _lattice_strategies import anchor_sets, cats, registries
from hypothesis import HealthCheck, given, settings

from mainline_domain.contracts import ControlDelta, RULE_IDS
from mainline_domain.lattice import RuleFinding, dual, explain

_SETTINGS = settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


def _by_rule(findings: tuple[RuleFinding, ...], orderable: bool) -> dict[str, Counter[str]]:
    grouped: dict[str, Counter[str]] = {rule_id: Counter() for rule_id in RULE_IDS}
    for finding in findings:
        if finding.orderable is orderable:
            grouped[finding.rule_id][finding.delta.value] += 1
    return grouped


@_SETTINGS
@given(cats(), cats(), registries(), anchor_sets(), anchor_sets())
def test_every_orderable_finding_inverts_when_the_edit_is_read_backwards(  # type: ignore[no-untyped-def]
    reference, descendant, registry, reference_anchors, descendant_anchors
) -> None:
    forward = explain(
        reference,
        descendant,
        registry,
        AS_OF,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    )
    backward = explain(
        descendant,
        reference,
        registry,
        AS_OF,
        reference_anchors=descendant_anchors,
        descendant_anchors=reference_anchors,
    )

    forward_orderable = _by_rule(forward.findings, orderable=True)
    backward_orderable = _by_rule(backward.findings, orderable=True)

    for rule_id in RULE_IDS:
        dualised = Counter(
            {dual(ControlDelta(label)).value: n for label, n in forward_orderable[rule_id].items()}
        )
        assert dualised == backward_orderable[rule_id], (
            f"{rule_id} is not self-inverse: forward {dict(forward_orderable[rule_id])} "
            f"dualises to {dict(dualised)} but backwards gives "
            f"{dict(backward_orderable[rule_id])}"
        )


@_SETTINGS
@given(cats(), cats(), registries(), anchor_sets(), anchor_sets())
def test_every_non_orderable_finding_is_its_own_inverse_and_is_a_weakening(  # type: ignore[no-untyped-def]
    reference, descendant, registry, reference_anchors, descendant_anchors
) -> None:
    forward = explain(
        reference,
        descendant,
        registry,
        AS_OF,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    )
    backward = explain(
        descendant,
        reference,
        registry,
        AS_OF,
        reference_anchors=descendant_anchors,
        descendant_anchors=reference_anchors,
    )

    for decision in (forward, backward):
        for finding in decision.findings:
            if not finding.orderable:
                assert finding.delta is ControlDelta.WEAKEN, (
                    f"{finding.rule_id} produced a non-orderable "
                    f"{finding.delta.value}; the only fail-closed answer is weaken"
                )

    assert _by_rule(forward.findings, orderable=False) == _by_rule(
        backward.findings, orderable=False
    )


@_SETTINGS
@given(cats(), cats(), registries())
def test_a_verdict_is_never_silently_reversed_by_reading_the_diff_backwards(  # type: ignore[no-untyped-def]
    reference, descendant, registry
) -> None:
    """The coarse statement a reader can check without the finding-level detail.

    If the forward verdict is a strengthening (force 0 and not a restatement),
    the backward verdict must not also be one — otherwise both directions of one
    edit would be "safe", which is the shape of a lattice that has stopped
    discriminating.  The exception is a verdict resting entirely on non-orderable
    findings, which are weaken in both directions by design.
    """
    forward = explain(reference, descendant, registry, AS_OF)
    backward = explain(descendant, reference, registry, AS_OF)

    if forward.delta is ControlDelta.STRENGTHEN:
        assert backward.delta in (ControlDelta.WEAKEN, ControlDelta.REMOVE)
    if forward.delta is ControlDelta.REMOVE:
        assert backward.delta is ControlDelta.INTRODUCE
    if forward.delta is ControlDelta.RESTATE:
        assert backward.delta is ControlDelta.RESTATE


def test_the_two_non_dual_categories_are_reachable_and_are_the_only_two() -> None:
    """Names the exceptions out loud, with an example of each, so that a third
    category cannot be added without somebody editing this list."""
    from _lattice_fixtures import cat, empty_registry, qty, registry as make_registry

    from mainline_domain.registry.model import SafeDirection

    polarity = explain(cat(deontic="MUST"), cat(deontic="MUST_NOT"), empty_registry(), AS_OF)
    assert [f.orderable for f in polarity.findings] == [False]
    assert polarity.delta is ControlDelta.WEAKEN

    inversion = explain(
        cat(parameter="max_operating_pressure", comparator="<=", value=qty("50", "kPa")),
        cat(parameter="max_operating_pressure", comparator=">=", value=qty("50", "kPa")),
        make_registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa")),
        AS_OF,
    )
    assert any(not f.orderable for f in inversion.findings)
    assert inversion.delta is ControlDelta.WEAKEN

    abstention = explain(
        cat(parameter="vent_line_backpressure", comparator="<=", value=qty("10", "kPa")),
        cat(parameter="vent_line_backpressure", comparator="<=", value=qty("50", "kPa")),
        empty_registry(),
        AS_OF,
    )
    assert [f.orderable for f in abstention.findings] == [False]
    assert abstention.delta is ControlDelta.WEAKEN
