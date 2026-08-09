# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Binding failures, and why none of them is silence.

Every exception here subclasses ``mainline_recall_agent.providers.errors.ProviderError``
with ``silence_reason = None``.  That is the whole design decision: a *contract*
violation — a prompt version the register does not know, a budget that drifted, a
sampling parameter that appeared in a body — is a **defect in our code**, not a fact
about the corpus.  The recall package's own rule (``errors.py``) is that a
``ProviderError`` carrying ``silence_reason = None`` must crash the run rather than be
recorded as silence, and these inherit it rather than restating it.

The three exceptions that *are* facts about the world — the model refused, the answer
was truncated, the provider could not be reached — are **not defined here**.  The
transport translates them into the recall package's own ``ModelRefusal``,
``ModelTruncated`` and ``ProviderUnavailable`` so that the orchestrator's degraded path
(complete on channels A+B, set ``arms_degraded``, write the silence rows, and STILL
BLOCK THE MERGE) fires on exactly the classes it already catches.  A binding that
introduced a new exception class for a refusal would be a binding that silently disabled
the degraded path.
"""

from __future__ import annotations

from mainline_recall_agent.providers.errors import ProviderError

__all__ = [
    "BudgetDrift",
    "FleetContractViolation",
    "PromptVersionDrift",
    "UnregisteredLeg",
]


class FleetContractViolation(ProviderError):
    """A request or a body breaks the fleet's model-call contract.

    Raised before anything reaches the wire.  Carries the decision it enforces (``A3``,
    ``A5``, ``A6``, ``A9`` …) in its context so the traceback names the rule rather than
    only the symptom.
    """


class UnregisteredLeg(ProviderError):
    """A model call was attempted through a leg the recall fleet register does not name.

    The register is the complete statement of what the recall agent may ask a model to
    do (``spec/agents/fleet.yaml``'s ``call_profiles`` column, decision A14's capability
    matrix).  An unregistered leg is a capability nobody declared, so it is refused
    rather than served.
    """


class PromptVersionDrift(ProviderError):
    """The request carries a ``prompt_version`` the register does not pin.

    Decision A13: *prompt edits are commits, not deploys.*  A prompt whose bytes moved
    without the register moving would produce ``agent_action_provenance`` rows claiming a
    prompt version that never ran, and a quiet prompt edit that suppressed a class of
    precursor is exactly what A13 exists to make attributable.
    """


class BudgetDrift(ProviderError):
    """The request carries a ``max_tokens`` the register does not pin.

    Decision A5: ``max_tokens`` caps thinking **plus** text, so the budget is part of
    what identifies a call.  A run record that pins 4096 while the wire carries 1024 is a
    record that cannot explain a truncation.
    """
