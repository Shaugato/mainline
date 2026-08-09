# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The outcome model — and the rule that a ``SKIP`` is printed as loudly as a ``FAIL``.

Why this module is the first one to read
----------------------------------------
A verifier that quietly passes because it did not look is the single worst artefact this
project could ship. Every other file here is arithmetic; this one is the design decision
that keeps the arithmetic honest.

Three verdicts, and only three:

``PASS``
    The check ran, over real data, and held. A ``PASS`` may carry a **qualifier** —
    ``PASS(not-adverse)``, ``PASS(coarse)``, ``PASS(self-asserted-key)`` — which narrows
    what the pass means. A qualifier is not decoration: it is the difference between
    "verified" and "verified against something we supplied ourselves".

``FAIL``
    The check ran and did not hold. Exit code 1.

``SKIP(reason)``
    The check **did not run**, and the reason is mandatory — :func:`skipped` refuses to
    build one without it, because ``SKIP()`` with an empty reason is precisely the
    artefact this module exists to prevent.

Three consequences, all mechanical
----------------------------------
1. **Same weight.** ``FAIL`` and ``SKIP`` render with the identical style constant
   (:data:`_LOUD`). They are not distinguished by colour, only by the word. You cannot
   train your eye to skim past one and not the other.
2. **Same section, and it is the first one.** Skips are not a footnote under the summary.
   A run containing any skip opens with a ``NOT CHECKED`` banner that names every skipped
   check and why, *before* a single ``PASS`` is printed.
3. **A distinguishing exit code.** ``0`` is "everything was checked and everything held".
   A run in which nothing failed but something was not looked at exits
   :data:`EXIT_NOT_CHECKED` (``2``), never ``0``. A CI lane that treats non-zero as
   failure therefore cannot go green on a verifier that did not look, and a CI lane that
   wants to tolerate skips has to say so in writing.

Vocabulary (custody ruling CU-12)
---------------------------------
Every report leads with :data:`BANNER_SENTENCE` — *"this bundle records the preconditions
the database enforced before work was permitted to start"*. Evidence Act 1995 (Cth)
s.69(3) and s.147(3) exclude representations prepared in contemplation of a proceeding, so
a ledger described as an exhibit is a ledger arguing against its own admissibility. The
operational sentence is the accurate one and it is also the safe one.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import StrEnum
from typing import IO, Any, Final

__all__ = [
    "BANNER_SENTENCE",
    "EXIT_FINDINGS",
    "EXIT_NOT_CHECKED",
    "EXIT_OK",
    "EXIT_UNUSABLE",
    "Outcome",
    "Report",
    "Verdict",
    "failed",
    "passed",
    "skipped",
    "want_colour",
]

#: The one sentence every report opens with. See CU-12 in ``docs/leads/custody.md``.
BANNER_SENTENCE: Final[str] = (
    "this bundle records the preconditions the database enforced before work was permitted to start"
)

#: Every check ran and held.
EXIT_OK: Final[int] = 0
#: At least one check ran and did not hold.
EXIT_FINDINGS: Final[int] = 1
#: Nothing failed, but at least one check did not run. Distinct from :data:`EXIT_OK` on
#: purpose: "we found nothing" and "we did not look" are different facts and a shell
#: cannot tell them apart from a zero.
EXIT_NOT_CHECKED: Final[int] = 2
#: The bundle could not be read far enough to run any check at all. Not a finding about
#: the log — a finding about the file.
EXIT_UNUSABLE: Final[int] = 3


class Verdict(StrEnum):
    """The only three things a check may say."""

    PASS = "PASS"  # noqa: S105 — a verdict, not a credential.
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one check said, and everything a reader needs to argue with it.

    ``code`` is a stable machine token (``leaf-hash-mismatch``, ``within-mmd``) that tests
    and downstream tooling match on. Prose is for humans and changes; the code does not.
    """

    check_id: int
    name: str
    verdict: Verdict
    code: str
    headline: str
    reason: str = ""
    qualifier: str = ""
    detail: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a ``SKIP`` with no reason, at construction time."""
        if self.verdict is Verdict.SKIP and not self.reason:
            raise ValueError(
                f"check {self.check_id} produced SKIP with no reason. A skip whose cause "
                "is not stated is indistinguishable from a check that was silently "
                "dropped, which is the failure mode this verifier exists to refuse."
            )

    @property
    def label(self) -> str:
        """``PASS``, ``PASS(not-adverse)``, ``FAIL`` or ``SKIP(offline)``."""
        if self.verdict is Verdict.SKIP:
            return f"SKIP({self.reason})"
        if self.qualifier:
            return f"{self.verdict.value}({self.qualifier})"
        return self.verdict.value

    def as_json(self) -> dict[str, Any]:
        """Render this outcome as JSON, for the console and for CI summaries."""
        return {
            "check_id": self.check_id,
            "name": self.name,
            "verdict": self.verdict.value,
            "label": self.label,
            "code": self.code,
            "headline": self.headline,
            "reason": self.reason,
            "qualifier": self.qualifier,
            "detail": list(self.detail),
        }


def passed(
    check_id: int,
    name: str,
    code: str,
    headline: str,
    *,
    qualifier: str = "",
    detail: tuple[str, ...] = (),
) -> Outcome:
    """Build a ``PASS``. Pass ``qualifier`` when the pass is narrower than it looks."""
    return Outcome(
        check_id=check_id,
        name=name,
        verdict=Verdict.PASS,
        code=code,
        headline=headline,
        qualifier=qualifier,
        detail=detail,
    )


def failed(
    check_id: int,
    name: str,
    code: str,
    headline: str,
    *,
    detail: tuple[str, ...] = (),
) -> Outcome:
    """Build a ``FAIL``."""
    return Outcome(
        check_id=check_id,
        name=name,
        verdict=Verdict.FAIL,
        code=code,
        headline=headline,
        detail=detail,
    )


def skipped(
    check_id: int,
    name: str,
    reason: str,
    headline: str,
    *,
    detail: tuple[str, ...] = (),
) -> Outcome:
    """Build a ``SKIP``. ``reason`` is REQUIRED and is what appears in ``SKIP(...)``."""
    return Outcome(
        check_id=check_id,
        name=name,
        verdict=Verdict.SKIP,
        code=reason,
        headline=headline,
        reason=reason,
        detail=detail,
    )


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

#: FAIL and SKIP share this. That is the whole point: bold red for both, so that no
#: reader's eye learns that one of them is the quiet one.
_LOUD: Final[str] = "\x1b[1;31m"
_GOOD: Final[str] = "\x1b[32m"
_DIM: Final[str] = "\x1b[2m"
_BOLD: Final[str] = "\x1b[1m"
_OFF: Final[str] = "\x1b[0m"

#: Deliberately ASCII. A report may be read on a console whose encoding predates
#: Unicode, and decoration is the last thing that should test that.
_RULE: Final[str] = "-" * 78


def want_colour(choice: str, stream: IO[str] | None = None) -> bool:
    """Resolve ``--colour auto|always|never`` against the environment.

    ``NO_COLOR`` (any value) and ``TERM=dumb`` both disable ``auto``, per the informal
    convention every other CLI honours.
    """
    if choice == "always":
        return True
    if choice == "never":
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    target = stream if stream is not None else sys.stdout
    return bool(getattr(target, "isatty", lambda: False)())


def _paint(text: str, style: str, *, colour: bool) -> str:
    return f"{style}{text}{_OFF}" if colour else text


def _style_for(verdict: Verdict) -> str:
    return _GOOD if verdict is Verdict.PASS else _LOUD


@dataclass(slots=True)
class Report:
    """Every outcome of one run, plus the exit code the run is entitled to."""

    subject: str
    tool_version: str
    selection: tuple[int, ...] | None = None
    outcomes: list[Outcome] = field(default_factory=list)
    preamble: tuple[str, ...] = ()

    def add(self, outcome: Outcome) -> None:
        """Record one check's outcome."""
        self.outcomes.append(outcome)

    def extend(self, outcomes: list[Outcome]) -> None:
        """Record several."""
        self.outcomes.extend(outcomes)

    @property
    def failures(self) -> list[Outcome]:
        """Every ``FAIL``, in check order."""
        return [o for o in self.outcomes if o.verdict is Verdict.FAIL]

    @property
    def skips(self) -> list[Outcome]:
        """Every ``SKIP``, in check order."""
        return [o for o in self.outcomes if o.verdict is Verdict.SKIP]

    @property
    def passes(self) -> list[Outcome]:
        """Every ``PASS``, in check order."""
        return [o for o in self.outcomes if o.verdict is Verdict.PASS]

    @property
    def exit_code(self) -> int:
        """``1`` if anything failed, else ``2`` if anything was skipped, else ``0``."""
        if self.failures:
            return EXIT_FINDINGS
        if self.skips:
            return EXIT_NOT_CHECKED
        return EXIT_OK

    # -- rendering ---------------------------------------------------------------------

    def _banner(self, *, colour: bool) -> list[str]:
        lines: list[str] = []
        if self.selection is not None:
            selected = ", ".join(str(i) for i in self.selection)
            lines.append(_paint("SELECTED RUN", _LOUD, colour=colour))
            lines.append(
                f"  only checks {selected} were selected on the command line. Every other "
                "check in the"
            )
            lines.append(
                "  registry was NOT RUN. This report is evidence about the checks named "
                "above and about"
            )
            lines.append("  nothing else.")
            lines.append("")
        if not self.skips:
            return lines
        lines.append(
            _paint(
                f"NOT CHECKED — {len(self.skips)} of {len(self.outcomes)} checks did not run",
                _LOUD,
                colour=colour,
            )
        )
        for outcome in self.skips:
            lines.append(
                f"  {_paint('SKIP', _LOUD, colour=colour)}  check {outcome.check_id:>2}  "
                f"{outcome.name:<32}{outcome.reason}"
            )
            lines.extend(f"        {line}" for line in outcome.detail)
        lines.append("")
        lines.append("  A skipped check proves nothing. It is printed here, first, and in the same")
        lines.append(
            "  weight as a failure, because a verifier that passes because it did not look"
        )
        lines.append("  is worse than no verifier at all.")
        lines.append("")
        return lines

    def render(self, *, colour: bool = False) -> str:
        """Return the whole human-readable report as one string."""
        lines: list[str] = []
        lines.append(_paint(f"trappoint-verify {self.tool_version}", _BOLD, colour=colour))
        lines.append(_paint(BANNER_SENTENCE, _DIM, colour=colour))
        lines.append(f"subject: {self.subject}")
        lines.extend(self.preamble)
        lines.append(_RULE)
        lines.append("")
        lines.extend(self._banner(colour=colour))
        lines.append(_paint("CHECKS", _BOLD, colour=colour))
        for outcome in self.outcomes:
            token = _paint(
                f"{outcome.verdict.value:<4}", _style_for(outcome.verdict), colour=colour
            )
            lines.append(
                f"  {token}  check {outcome.check_id:>2}  {outcome.name:<32}{outcome.headline}"
            )
            if outcome.verdict is not Verdict.PASS or outcome.qualifier:
                lines.extend(f"        - {line}" for line in outcome.detail)
        lines.append("")
        lines.append(_RULE)
        summary = (
            f"{len(self.outcomes)} checks | {len(self.passes)} passed | "
            f"{len(self.failures)} failed | {len(self.skips)} not checked"
        )
        lines.append(_paint(summary, _BOLD, colour=colour))
        lines.append(self._verdict_sentence())
        return "\n".join(lines) + "\n"

    def _verdict_sentence(self) -> str:
        if self.failures:
            return (
                f"exit {EXIT_FINDINGS}: {len(self.failures)} finding(s). This bundle does "
                "not verify."
            )
        if self.skips:
            return (
                f"exit {EXIT_NOT_CHECKED}: everything that ran held, and "
                f"{len(self.skips)} check(s) did not run. This is NOT a clean verification."
            )
        return f"exit {EXIT_OK}: every registered check ran and held."

    def as_json(self) -> dict[str, Any]:
        """Render the whole report as JSON, with the same exit code as the text form."""
        return {
            "tool": "trappoint-verify",
            "tool_version": self.tool_version,
            "subject": self.subject,
            "statement": BANNER_SENTENCE,
            "selection": list(self.selection) if self.selection is not None else None,
            "counts": {
                "total": len(self.outcomes),
                "passed": len(self.passes),
                "failed": len(self.failures),
                "not_checked": len(self.skips),
            },
            "not_checked": [o.as_json() for o in self.skips],
            "outcomes": [o.as_json() for o in self.outcomes],
            "exit_code": self.exit_code,
        }

    def as_json_text(self) -> str:
        """Serialise :meth:`as_json`, sorted and newline-terminated, so two runs diff cleanly."""
        return json.dumps(self.as_json(), indent=2, sort_keys=True) + "\n"
