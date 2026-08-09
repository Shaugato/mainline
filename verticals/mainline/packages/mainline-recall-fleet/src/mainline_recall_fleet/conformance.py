# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The model-call contract as findings, not as prose.

`docs/leads/agents-mcp.md` §3 publishes `spec/agents/model-call.contract.md` to *every
model caller in the repo, including `recall-providers`*.  A contract whose only
enforcement is a document is a contract that is true until someone is in a hurry.  This
module renders each clause as a named check that returns a :class:`Finding`, so the same
statement can be asserted by a test, printed by a reviewer and read by CI.

The checks are **pure**: they take a body or a leg and return findings.  Nothing here
sends anything, opens anything or reads the environment, which is why `audit_body` can be
run over the raw recall request as well as over the bound one — and that pair is the
honest evidence for the two gaps this binding closes:

    >>> from mainline_recall_fleet.conformance import audit_body, failures
    >>> [f.check for f in failures(audit_body(raw_recall_style_body))]
    ['A5.thinking_adaptive', 'A4.effort_declared']

Those two names are what `tests/agents/recall_fleet/test_body_contract.py` asserts red
before it asserts the bound body green.  PL-2 says a suite that has never been red
asserts nothing; for a binding whose deliverable is a *normalisation*, the red is the
un-normalised body, and it is checked in rather than described.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import (
    ANTHROPIC_VERSION,
    BANNED_SAMPLING_KEYS,
    BANNED_TOOL_KEYS,
    Effort,
)

from .legs import GATE_WRITING_ROLES, RECALL_LEGS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from .legs import RecallLeg

__all__ = [
    "BODY_CHECKS",
    "LEG_CHECKS",
    "Finding",
    "audit_body",
    "audit_leg",
    "audit_recall_fleet",
    "failures",
    "render_report",
]


@dataclass(frozen=True, slots=True)
class Finding:
    """One clause of the contract, evaluated against one subject.

    Attributes:
        check: the clause id, ``<decision>.<clause>``.  Stable: tests reference it.
        decision: the decision in `docs/leads/agents-mcp.md` this clause enforces.
        ok: whether the subject satisfies it.
        detail: what was observed.  Written to be readable in a CI log without the code
            beside it.
    """

    check: str
    decision: str
    ok: bool
    detail: str


#: The clause ids `audit_body` emits, in evaluation order.  A test reads this so a
#: silently deleted check fails rather than passes.
BODY_CHECKS: Final[tuple[str, ...]] = (
    "A3.anthropic_version",
    "A3.native_body_shape",
    "A5.thinking_adaptive",
    "A4.effort_declared",
    "A4.effort_vocabulary",
    "A7.structured_output",
    "A6.no_sampling_params",
    "A1.no_tool_surface",
    "A9.single_cache_breakpoint",
)

#: The clause ids `audit_leg` emits, in evaluation order.
LEG_CHECKS: Final[tuple[str, ...]] = (
    "A1.no_tools",
    "MI25.not_gate_writing_role",
    "MI25.no_blocking_check_write",
    "A5.thinking_floor_fits",
    "A8.silence_declared",
    "A13.prompt_version_declared",
)

#: Keys that would mean the body was built for a rejected transport.  `Converse` cannot
#: express `output_config.format`, and the Mantle client terminates on a different
#: endpoint whose policy surface is unverified — a residency claim resting on an
#: unverified endpoint policy is a claim we lose in the room.
_FOREIGN_TRANSPORT_KEYS: Final[frozenset[str]] = frozenset(
    {"inferenceConfig", "additionalModelRequestFields", "toolConfig", "modelId", "input"}
)


def audit_body(body: Mapping[str, Any]) -> tuple[Finding, ...]:
    """Evaluate every body clause of the model-call contract against ``body``.

    Never raises on a non-conforming body: it returns findings, because the point of this
    function is to be runnable over the *failing* case.
    """
    foreign = sorted(_FOREIGN_TRANSPORT_KEYS & set(body))
    findings: list[Finding] = [
        Finding(
            check="A3.anthropic_version",
            decision="A3",
            ok=body.get("anthropic_version") == ANTHROPIC_VERSION,
            detail=f"anthropic_version={body.get('anthropic_version')!r} "
            f"(contract: {ANTHROPIC_VERSION!r})",
        ),
        Finding(
            check="A3.native_body_shape",
            decision="A3",
            ok=not foreign,
            detail=(
                "no Converse/Mantle-shaped keys"
                if not foreign
                else f"foreign transport keys present: {foreign}"
            ),
        ),
    ]
    thinking = body.get("thinking")
    adaptive = isinstance(thinking, dict) and thinking.get("type") == "adaptive"
    findings.append(
        Finding(
            check="A5.thinking_adaptive",
            decision="A5",
            ok=adaptive,
            detail=(
                "thinking={'type': 'adaptive'}"
                if adaptive
                else f"thinking={thinking!r}; A5 requires it written explicitly on every "
                f"call, never omitted and never disabled"
            ),
        )
    )
    output_config = body.get("output_config")
    config = output_config if isinstance(output_config, dict) else {}
    effort = config.get("effort")
    findings.append(
        Finding(
            check="A4.effort_declared",
            decision="A4",
            ok=effort is not None,
            detail=(
                f"output_config.effort={effort!r}"
                if effort is not None
                else "output_config carries no effort; the fleet is differentiated by "
                "effort alone, so a body without one runs at the endpoint default"
            ),
        )
    )
    known_efforts = {str(item) for item in Effort}
    findings.append(
        Finding(
            check="A4.effort_vocabulary",
            decision="A4",
            ok=effort is None or str(effort) in known_efforts,
            detail=f"effort={effort!r} against {sorted(known_efforts)}",
        )
    )
    fmt = config.get("format")
    strict = (
        isinstance(fmt, dict)
        and fmt.get("type") == "json_schema"
        and bool(fmt.get("strict"))
        and isinstance(fmt.get("schema"), dict)
    )
    findings.append(
        Finding(
            check="A7.structured_output",
            decision="A7",
            ok=strict,
            detail=(
                "output_config.format is a strict json_schema"
                if strict
                else f"output_config.format={fmt!r}; structured output is the mechanism "
                f"by which a T1 proposal is schema-constrained"
            ),
        )
    )
    sampling = sorted(_keys_at_any_depth(body) & BANNED_SAMPLING_KEYS)
    findings.append(
        Finding(
            check="A6.no_sampling_params",
            decision="A6",
            ok=not sampling,
            detail="no sampling parameters" if not sampling else f"present: {sampling}",
        )
    )
    tools = sorted(_keys_at_any_depth(body) & BANNED_TOOL_KEYS)
    findings.append(
        Finding(
            check="A1.no_tool_surface",
            decision="A1",
            ok=not tools,
            detail="no tool surface" if not tools else f"present: {tools}",
        )
    )
    findings.append(_cache_breakpoint_finding(body.get("system")))
    return tuple(findings)


def audit_leg(leg: RecallLeg) -> tuple[Finding, ...]:
    """Evaluate the capability-matrix clauses against one registered leg."""
    blocking = [relation for relation in leg.writes if "blocking_check" in relation]
    return (
        Finding(
            check="A1.no_tools",
            decision="A1",
            ok=not leg.tools and not leg.may_write_gate_field,
            detail=f"tools={list(leg.tools)} may_write_gate_field={leg.may_write_gate_field}",
        ),
        Finding(
            check="MI25.not_gate_writing_role",
            decision="MI25",
            ok=leg.sql_role not in GATE_WRITING_ROLES,
            detail=f"sql_role={leg.sql_role!r} against {sorted(GATE_WRITING_ROLES)}",
        ),
        Finding(
            check="MI25.no_blocking_check_write",
            decision="ARCHITECTURE §8.3",
            ok=not blocking,
            detail=(
                "writes no obligation relation" if not blocking else f"claims writes to {blocking}"
            ),
        ),
        Finding(
            check="A5.thinking_floor_fits",
            decision="A5",
            ok=leg.thinking_floor_tokens < leg.max_tokens,
            detail=f"thinking_floor={leg.thinking_floor_tokens} max_tokens={leg.max_tokens}",
        ),
        Finding(
            check="A8.silence_declared",
            decision="A8",
            ok=bool(leg.silence_reasons) and "model_refusal" in leg.silence_reasons,
            detail=f"silence_reasons={sorted(leg.silence_reasons)}",
        ),
        Finding(
            check="A13.prompt_version_declared",
            decision="A13",
            ok=bool(leg.prompt_version.strip()),
            detail=f"prompt_version={leg.prompt_version!r}",
        ),
    )


def audit_recall_fleet() -> tuple[Finding, ...]:
    """Evaluate every registered leg.  This is the recall half of the capability matrix."""
    findings: list[Finding] = []
    for leg_id in sorted(RECALL_LEGS):
        for finding in audit_leg(RECALL_LEGS[leg_id]):
            findings.append(
                Finding(
                    check=f"{leg_id}::{finding.check}",
                    decision=finding.decision,
                    ok=finding.ok,
                    detail=finding.detail,
                )
            )
    return tuple(findings)


def failures(findings: Iterable[Finding]) -> list[Finding]:
    """Return only the findings that did not hold."""
    return [finding for finding in findings if not finding.ok]


def render_report(findings: Iterable[Finding]) -> str:
    """Render findings as one line each, for a CI log or a reviewer's terminal."""
    return "\n".join(
        f"{'PASS' if finding.ok else 'FAIL'}  {finding.check:<44} [{finding.decision}]  "
        f"{finding.detail}"
        for finding in findings
    )


# ── internals ───────────────────────────────────────────────────────────────────


def _cache_breakpoint_finding(system: Any) -> Finding:
    if not isinstance(system, list) or not system:
        return Finding(
            check="A9.single_cache_breakpoint",
            decision="A9",
            ok=False,
            detail=f"system={system!r}; there is no frozen prefix to cache",
        )
    marked = [
        index
        for index, block in enumerate(system)
        if isinstance(block, dict) and "cache_control" in block
    ]
    last = len(system) - 1
    return Finding(
        check="A9.single_cache_breakpoint",
        decision="A9",
        ok=marked == [last],
        detail=f"breakpoints at {marked}, last block index {last}",
    )


def _keys_at_any_depth(node: Any, *, opaque: Sequence[str] = ("schema",)) -> set[str]:
    """Every mapping key in ``node``, not descending into a JSON Schema.

    A JSON Schema is data.  A mining procedure genuinely has a ``temperature`` setpoint,
    and an extraction model with such a field must not be mistaken for a sampling
    parameter — descending would make the check fire on the corpus rather than on the
    request.  This mirrors `mainline_agentkit.transport._walk`'s opaque-subtree rule.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            if str(key) not in opaque:
                found |= _keys_at_any_depth(value, opaque=opaque)
    elif isinstance(node, (list, tuple)):
        for item in node:
            found |= _keys_at_any_depth(item, opaque=opaque)
    return found
