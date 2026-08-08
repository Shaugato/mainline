# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""THE RED TEST (PL-2).  The ratchet has exactly one property and this file is it.

*There exists no input under which Path B lowers the Path-A verdict.*

Everything else in worker W5 — the oracle package, the cassettes, the silence
records — exists to make that sentence true and auditable.  So this file is
written first, run first, and observed **red** first: for a product whose
deliverable is a refusal, a suite that has never failed asserts nothing.

The property is stated over ``mainline_domain.contracts.force``, not over prose.
``force`` is the order in which the *database* must react — ``introduce`` /
``strengthen`` / ``restate`` = 0, ``weaken`` = 2, ``remove`` = 3 — so
"monotone upward in force" is exactly "the model can only ever move the verdict
toward a refusal".

Three independent shapes of the same claim:

* **Exhaustive.**  The full cross product of (Path-A delta) x (oracle label) x
  (confidence band relative to theta) x (abstained flag).  5 x 5 x 3 x 2 = 150
  concrete cells, every one of them named in the failure message.
* **Generative.**  Hypothesis over the same domain with continuous confidence
  and continuous theta, which catches a boundary written with the wrong
  comparison operator.
* **Absent Path B.**  ``oracle=None`` — no model ran at all — must behave like
  an abstention (P3, fail closed on missing evidence), not like a pass.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mainline_domain.contracts import ControlDelta, DeltaVerdict, DeltaWitness, OracleVerdict, force
from mainline_domain.resolution import resolve

_DELTAS = tuple(ControlDelta)

_WITNESS = DeltaWitness(
    rule_id="R1_DEONTIC",
    field="deontic",
    from_repr="MUST",
    to_repr="SHOULD",
    note="deontic downgrade",
)


def _path_a(delta: ControlDelta) -> DeltaVerdict:
    """A well-formed Path-A verdict.

    ``weaken``/``remove`` carry a witness because decision D8 makes a
    witness-free lattice weakening unrepresentable; the resolver refuses one on
    the way in, and that refusal is asserted in ``test_resolve_rules.py`` rather
    than here, so this file tests the ratchet and nothing else.
    """
    witnesses = (_WITNESS,) if force(delta) > 0 else ()
    return DeltaVerdict(delta=delta, basis="lattice", witnesses=witnesses, minimal=bool(witnesses))


def _oracle(label: ControlDelta, confidence: float, *, abstained: bool) -> OracleVerdict:
    return OracleVerdict(
        label=label,
        confidence=confidence,
        rationale="model_abstained: synthetic" if abstained else "synthetic",
        cited_spans=(),
        model_id="au.anthropic.claude-opus-5",
        prompt_version="adjudication.v1+rubric.v1",
        abstained=abstained,
    )


_THETA = 0.75
_CONFIDENCES = {
    "below_theta": _THETA - 0.01,
    "at_theta": _THETA,
    "above_theta": _THETA + 0.01,
}


@pytest.mark.parametrize("path_a_delta", _DELTAS, ids=lambda d: f"A={d.value}")
@pytest.mark.parametrize("oracle_label", _DELTAS, ids=lambda d: f"B={d.value}")
@pytest.mark.parametrize("band", sorted(_CONFIDENCES), ids=lambda b: b)
@pytest.mark.parametrize("abstained", [False, True], ids=["answered", "abstained"])
def test_no_cell_lowers_the_path_a_force(
    path_a_delta: ControlDelta,
    oracle_label: ControlDelta,
    band: str,
    abstained: bool,
) -> None:
    """Every cell of the resolution table, one assertion each."""
    a = _path_a(path_a_delta)
    b = _oracle(oracle_label, _CONFIDENCES[band], abstained=abstained)
    resolved = resolve(a, b, theta=_THETA)
    assert force(resolved.delta) >= force(a.delta), (
        f"the oracle LOWERED the verdict: Path A said {path_a_delta.value} "
        f"(force {force(a.delta)}), the model said {oracle_label.value} at "
        f"confidence {_CONFIDENCES[band]} (abstained={abstained}), and the "
        f"resolution was {resolved.delta.value} (force {force(resolved.delta)}). "
        f"The abstention ratchet is the whole claim of this worker."
    )


@settings(max_examples=500)
@given(
    path_a_delta=st.sampled_from(_DELTAS),
    oracle_label=st.sampled_from(_DELTAS),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    theta=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    abstained=st.booleans(),
)
def test_monotone_upward_over_continuous_confidence_and_theta(
    path_a_delta: ControlDelta,
    oracle_label: ControlDelta,
    confidence: float,
    theta: float,
    abstained: bool,
) -> None:
    """The same property with theta and confidence free, which is where an
    off-by-one comparison operator lives."""
    a = _path_a(path_a_delta)
    b = _oracle(oracle_label, confidence, abstained=abstained)
    resolved = resolve(a, b, theta=theta)
    assert force(resolved.delta) >= force(a.delta)


@pytest.mark.parametrize("path_a_delta", _DELTAS, ids=lambda d: d.value)
def test_an_absent_oracle_never_lowers_and_never_clears(path_a_delta: ControlDelta) -> None:
    """P3: absence of a model response resolves toward the block.

    ``oracle=None`` is not "neutral" and is not "unknown". Path B not running is
    missing evidence, and missing evidence fails closed.
    """
    a = _path_a(path_a_delta)
    resolved = resolve(a, None, theta=_THETA)
    assert force(resolved.delta) >= force(a.delta)
    assert force(resolved.delta) >= force(ControlDelta.WEAKEN)
    assert resolved.basis == "abstain_to_weaken"


def test_the_model_can_never_produce_a_zero_force_resolution_from_a_weakening() -> None:
    """The single sentence a regulator will ask about, asserted on its own.

    Path A found a deontic downgrade over blood-written ancestry. There is no
    oracle output — not the most confident ``entails`` the model can emit — that
    turns that into a pass.
    """
    a = _path_a(ControlDelta.WEAKEN)
    for label in _DELTAS:
        for confidence in (0.0, 0.5, 1.0):
            for abstained in (False, True):
                resolved = resolve(a, _oracle(label, confidence, abstained=abstained), theta=0.0)
                assert force(resolved.delta) >= force(ControlDelta.WEAKEN), (
                    f"label={label.value} confidence={confidence} abstained={abstained}"
                )
