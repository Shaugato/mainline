# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The ground-truth attestation — ruling `D5` made mechanical.

A capability under a dated `GT-*` check is a **render-time switch, never a runtime
branch**. Both branches of every switch emit committed, readable SQL, so the fallback is
something a reviewer reads rather than something a reviewer trusts.

What that requires of this module is one sentence: ``trappoint render`` will not run
without a ``g1-attestation.json`` that answers every capability the binding declares,
and an answer of ``UNKNOWN`` is not an answer.

Three states, and the difference between the second and the third is the point:

``PASS``
    measured, works, the primary branch renders.
``FALLBACK-SELECTED``
    measured, does **not** work, the fallback branch renders. A dated claim that
    depended on the capability is withdrawn in the same commit that selects this.
``UNKNOWN``
    not measured. Refused. `PL-3` forbids a dated path on an unproven capability, and a
    default is exactly how an unproven capability reaches production.

The attestation also states *where* each capability was measured, because "it worked on
my laptop" and "it worked on Cloud Basic" are different claims and the local node is
known to diverge from Cloud (`gc.ttlseconds`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AttestationRefused

__all__ = [
    "PASS",
    "STATUSES",
    "Attestation",
    "CapabilityAnswer",
    "load_attestation",
]

PASS = "PASS"
FALLBACK = "FALLBACK-SELECTED"
UNKNOWN = "UNKNOWN"
STATUSES: tuple[str, ...] = (PASS, FALLBACK, UNKNOWN)


@dataclass(frozen=True, slots=True)
class CapabilityAnswer:
    """One capability, measured or not."""

    name: str
    gate: str
    status: str
    selects: str
    measured_on: tuple[str, ...]
    measured_at: str
    evidence: str

    @property
    def answered(self) -> bool:
        """True when the capability was actually measured."""
        return self.status in (PASS, FALLBACK)


@dataclass(frozen=True, slots=True)
class Attestation:
    """A parsed ``g1-attestation.json``."""

    path: Path
    generated_at: str
    cluster: dict[str, Any]
    capabilities: dict[str, CapabilityAnswer]

    def require(self, name: str) -> CapabilityAnswer:
        """Return the answer for *name*, refusing when it is absent or ``UNKNOWN``.

        Raises:
            AttestationRefused: the capability is unlisted or unmeasured.
        """
        answer = self.capabilities.get(name)
        if answer is None:
            raise AttestationRefused(
                f"the ground-truth attestation {self.path} does not answer capability "
                f"{name!r}. A template declares `{{# @capability {name} #}}`, so the "
                "switch it selects is undecided, and an undecided switch may not reach a "
                "rendered migration (ruling D5)."
            )
        if not answer.answered:
            raise AttestationRefused(
                f"capability {name!r} ({answer.gate}) is {answer.status} in "
                f"{self.path}. PL-3 forbids a dated path on an unproven capability: "
                "measure it and record PASS, or select the fallback explicitly and "
                "record FALLBACK-SELECTED. There is no default."
            )
        return answer

    def agree(self, name: str, selected: str) -> None:
        """Refuse when the binding selects a branch the ground truth did not authorise.

        A binding that asks for ``stored_digest = "stored"`` while the attestation
        records ``FALLBACK-SELECTED`` is asking the renderer to emit SQL that the
        measurement says will not run. The binding does not get to overrule the
        measurement; that is what "ground truth" means.

        Raises:
            AttestationRefused: the binding and the attestation disagree.
        """
        answer = self.require(name)
        if answer.selects != selected:
            raise AttestationRefused(
                f"binding selects capabilities.{name} = {selected!r} but the ground "
                f"truth in {self.path} selects {answer.selects!r} ({answer.gate}, "
                f"{answer.status}). Change the binding, or re-measure and re-attest — "
                "the binding does not overrule the measurement."
            )


def _answer(name: str, raw: object, path: Path) -> CapabilityAnswer:
    if not isinstance(raw, dict):
        raise AttestationRefused(f"{path}: capabilities.{name} is not an object")
    status = raw.get("status")
    if status not in STATUSES:
        raise AttestationRefused(
            f"{path}: capabilities.{name}.status is {status!r}; legal values are "
            f"{', '.join(STATUSES)}"
        )
    selects = raw.get("selects")
    if not isinstance(selects, str) or not selects:
        raise AttestationRefused(
            f"{path}: capabilities.{name}.selects must name the branch this measurement "
            "authorises the renderer to emit"
        )
    measured_on = raw.get("measured_on", [])
    if not isinstance(measured_on, list) or not all(isinstance(m, str) for m in measured_on):
        raise AttestationRefused(f"{path}: capabilities.{name}.measured_on must be a string list")
    gate = raw.get("gate")
    if not isinstance(gate, str) or not gate:
        raise AttestationRefused(
            f"{path}: capabilities.{name}.gate must name the ground-truth check "
            "(e.g. 'GT-13'), so a reader can find what was measured"
        )
    return CapabilityAnswer(
        name=name,
        gate=gate,
        status=status,
        selects=selects,
        measured_on=tuple(measured_on),
        measured_at=str(raw.get("measured_at", "")),
        evidence=str(raw.get("evidence", "")),
    )


def load_attestation(path: Path) -> Attestation:
    """Read and validate a ``g1-attestation.json``.

    Raises:
        AttestationRefused: the file is absent, is not JSON, or is structurally wrong.
    """
    if not path.is_file():
        raise AttestationRefused(
            f"no ground-truth attestation at {path}. `trappoint render` does not run "
            "without one: every capability switch in the templates is decided by a dated "
            "measurement, and a missing measurement is not a permissive one (ruling D5)."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AttestationRefused(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise AttestationRefused(f"{path} must hold a JSON object")

    raw_caps = document.get("capabilities")
    if not isinstance(raw_caps, dict) or not raw_caps:
        raise AttestationRefused(f"{path} declares no capabilities")

    cluster = document.get("cluster")
    if not isinstance(cluster, dict):
        raise AttestationRefused(
            f"{path} does not say which cluster it was measured against. A capability "
            "answer without a substrate is not evidence."
        )

    return Attestation(
        path=path,
        generated_at=str(document.get("generated_at", "")),
        cluster=cluster,
        capabilities={name: _answer(name, raw_caps[name], path) for name in sorted(raw_caps)},
    )
