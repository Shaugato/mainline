# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The result type shared by all four enforcements.

Three design rules, each of which exists because of a way this kind of check
usually rots:

1. **A skip is a first-class outcome with a reason attached.** A check that
   cannot run must say so in the report; it may not silently return an empty
   violation list, because an empty violation list is indistinguishable from a
   pass at the call site.
2. **Every report counts what it examined.** :attr:`Report.vacuous` is true when
   a report has no violations *and* examined nothing, and the test helpers turn
   that into a failure or an explicit skip — never a pass.
3. **Every exemption is recorded.** An exemption that is invisible in the output
   is a hole; an exemption that appears in the JSON artefact with its reason is a
   decision a reviewer can argue with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Enforcement(StrEnum):
    """The five independently-runnable checks, plus the grep family.

    ``E1`` to ``E4`` are ARCHITECTURE.md §8.2's four enforcements. They are separate
    modules, separate test files and separate CI jobs precisely so that they do
    not share a failure mode: one bad regex, one bad fixture path or one bad
    parser can take out at most one of them.
    """

    E1_IAM = "E1"
    E2_NETWORK = "E2"
    E3_CODE = "E3"
    E4_EGRESS = "E4"
    FLEET = "FLEET"
    GREP = "GREP"


@dataclass(frozen=True, slots=True)
class Finding:
    """A violation: a specific subject that breaks a specific named rule."""

    enforcement: str
    rule: str
    subject: str
    detail: str
    authority: str = ""

    def __str__(self) -> str:
        head = f"[{self.enforcement}/{self.rule}] {self.subject}: {self.detail}"
        return f"{head}  ({self.authority})" if self.authority else head

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": "violation",
            "enforcement": self.enforcement,
            "rule": self.rule,
            "subject": self.subject,
            "detail": self.detail,
            "authority": self.authority,
        }


@dataclass(frozen=True, slots=True)
class Skip:
    """A check that could not be performed, with the reason it could not."""

    enforcement: str
    rule: str
    subject: str
    reason: str

    def __str__(self) -> str:
        return f"[{self.enforcement}/{self.rule}] {self.subject}: SKIPPED — {self.reason}"

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": "skip",
            "enforcement": self.enforcement,
            "rule": self.rule,
            "subject": self.subject,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Exemption:
    """A subject deliberately excluded from a rule, with the reason."""

    enforcement: str
    rule: str
    subject: str
    reason: str

    def __str__(self) -> str:
        return f"[{self.enforcement}/{self.rule}] {self.subject}: EXEMPT — {self.reason}"

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": "exemption",
            "enforcement": self.enforcement,
            "rule": self.rule,
            "subject": self.subject,
            "reason": self.reason,
        }


@dataclass(slots=True)
class Report:
    """The outcome of one enforcement run."""

    enforcement: str
    examined: int = 0
    violations: list[Finding] = field(default_factory=list)
    skips: list[Skip] = field(default_factory=list)
    exemptions: list[Exemption] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -- recording -------------------------------------------------------

    def examine(self, count: int = 1) -> None:
        """Record that ``count`` subjects were actually inspected."""
        self.examined += count

    def violate(self, rule: str, subject: str, detail: str, authority: str = "") -> None:
        self.violations.append(
            Finding(
                enforcement=self.enforcement,
                rule=rule,
                subject=subject,
                detail=detail,
                authority=authority,
            )
        )

    def skip(self, rule: str, subject: str, reason: str) -> None:
        self.skips.append(
            Skip(enforcement=self.enforcement, rule=rule, subject=subject, reason=reason)
        )

    def exempt(self, rule: str, subject: str, reason: str) -> None:
        self.exemptions.append(
            Exemption(enforcement=self.enforcement, rule=rule, subject=subject, reason=reason)
        )

    def note(self, text: str) -> None:
        self.notes.append(text)

    def merge(self, other: Report) -> None:
        """Fold another report into this one, keeping this report's enforcement id."""
        self.examined += other.examined
        self.violations.extend(other.violations)
        self.skips.extend(other.skips)
        self.exemptions.extend(other.exemptions)
        self.notes.extend(other.notes)

    # -- interrogation ---------------------------------------------------

    @property
    def ok(self) -> bool:
        """True when nothing was violated. Says nothing about whether anything ran."""
        return not self.violations

    @property
    def vacuous(self) -> bool:
        """True when the report is clean but examined nothing — i.e. asserts nothing."""
        return not self.violations and self.examined == 0

    def skips_for(self, subject_fragment: str) -> tuple[Skip, ...]:
        return tuple(s for s in self.skips if subject_fragment in s.subject)

    def violations_for(self, rule: str) -> tuple[Finding, ...]:
        return tuple(v for v in self.violations if v.rule == rule)

    def rules_violated(self) -> frozenset[str]:
        return frozenset(v.rule for v in self.violations)

    # -- rendering -------------------------------------------------------

    def summary(self) -> str:
        parts = [
            f"{self.enforcement}: examined={self.examined} "
            f"violations={len(self.violations)} skips={len(self.skips)} "
            f"exemptions={len(self.exemptions)}"
        ]
        parts.extend(f"  {v}" for v in self.violations)
        parts.extend(f"  {s}" for s in self.skips)
        parts.extend(f"  {e}" for e in self.exemptions)
        parts.extend(f"  note: {n}" for n in self.notes)
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enforcement": self.enforcement,
            "examined": self.examined,
            "ok": self.ok,
            "vacuous": self.vacuous,
            "violations": [v.to_dict() for v in self.violations],
            "skips": [s.to_dict() for s in self.skips],
            "exemptions": [e.to_dict() for e in self.exemptions],
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)
