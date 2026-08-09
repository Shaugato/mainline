#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Validate the shot lists against the budget that decides whether we are eligible.

    python verticals/mainline/demo/script/validate_shotlist.py
    python verticals/mainline/demo/script/validate_shotlist.py --json

Three of BUILD_PLAN §5.5's four disqualifiers fail *silently* — nothing goes red,
the entry is simply not scored. The duration one is arithmetic, so it is checked
here rather than remembered, and it is checked against the plan before a frame is
shot rather than against the export afterwards, when the only remaining fix is to
cut a beat at 02:00.

What this asserts, and why each one is here rather than in a reviewer's head:

* **the schedule is internally consistent** — ``t`` values are the running sum of
  ``dur``. A shot list whose timecodes have drifted from its durations is a shot
  list two people will read differently on capture day;
* **the total is inside the envelope** — ``sum(dur) <= total_s <= 174`` with at
  least six seconds of headroom below the 180 s disqualifier;
* **every row carries ``requires_milestone`` and ``fallback``** — the fix for the
  hazard BUILD_PLAN §5.2 names: a beat scripted against a mechanism the plan
  deferred, discovered on the day. A row with no fallback is a row that becomes an
  improvisation;
* **the voice-over budget holds** — ``sum(word_count) <= 360``, and every
  ``word_count`` equals the words actually in its ``vo`` string, so the budget
  cannot be met by mistyping it;
* **the VO strings in the shot list and in VO.md are the same strings** — one
  line, two files, one assertion;
* **no seven-hex commit SHA and no bare invariant number appears** — the film
  cites constraint names, which are unambiguous, and cannot cite a SHA the DAG has
  not produced yet;
* **``never_cut`` rows are not in the scope-cut ladder** — a ladder that can reach
  the bypass beat is a ladder that will, at the exact moment judgement is worst.

Exit status: ``0`` clean, ``1`` at least one violation, ``2`` a file was missing or
unparseable. Absence is never reported as a pass.
"""

# ruff: noqa: T201 - this file is a CLI entry point and stdout IS its interface.
# ruff.toml exempts **/cli.py for exactly this reason; these scripts are the same
# shape under a different name, and a report nobody can read is not a control.

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]

MAIN_LIST = HERE / "SHOT-LIST.yaml"
MWS_LIST = HERE / "SHOT-LIST-MWS.yaml"
VO_FILE = HERE / "VO.md"
CAMERA_STRINGS = HERE / "CAMERA-STRINGS.yaml"
CARD = REPO_ROOT / "verticals/mainline/demo/honesty/card.html"
AUTHORED = REPO_ROOT / "verticals/mainline/fixtures/corpus/authored"

#: BUILD_PLAN §5.5 disqualifier 1. Silent, so it is arithmetic here.
HARD_CEILING_S = 180
#: The brief's schedule ceiling: total <= 174 with >= 6 s of headroom below 180.
PLAN_CEILING_S = 174
MIN_HEADROOM_S = 6
#: demo.yml's ffprobe gate. Not ours, but a plan that ignores it is a red CI run.
CI_HARD_FAIL_S = 176
#: research/06-build/demo-engineering.md §5 — ~150 wpm plus deliberate holds.
VO_WORD_BUDGET = 360
#: BUILD_PLAN §5.4 — the fallback cut, four beats, comfortably under the envelope.
MWS_CEILING_S = 160

REQUIRED_FIELDS = (
    "t",
    "dur",
    "shot_id",
    "on_screen",
    "vo",
    "word_count",
    "judging_criterion",
    "requires_milestone",
    "fallback",
    "evidence_artifact",
)

SHA7 = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{7}(?![0-9a-fA-F])")
BARE_INVARIANT = re.compile(r"(?<![A-Za-z0-9_])I\d{2}(?![0-9])")


@dataclass(slots=True)
class Result:
    """A tally that distinguishes a violation from a thing not checked."""

    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def fail(self, message: str) -> None:
        self.violations.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    @property
    def ok(self) -> bool:
        return not self.violations


def _words(text: str) -> int:
    return len([w for w in str(text).split() if w.strip()])


def _load(path: Path, result: Result) -> dict[str, Any] | None:
    if not path.is_file():
        result.fail(f"{path.relative_to(REPO_ROOT)} does not exist — nothing was checked")
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised by a malformed file
        result.fail(f"{path.relative_to(REPO_ROOT)} does not parse: {exc}")
        return None
    if not isinstance(loaded, dict) or not isinstance(loaded.get("shots"), list):
        result.fail(f"{path.relative_to(REPO_ROOT)} has no 'shots' list")
        return None
    return loaded


def check_shot_list(  # noqa: PLR0912, PLR0915 - one budget, checked in one place
    path: Path,
    result: Result,
    *,
    ceiling_s: int,
    require_headroom: bool,
    label: str,
) -> list[dict[str, Any]]:
    document = _load(path, result)
    if document is None:
        return []
    shots: list[dict[str, Any]] = [s for s in document["shots"] if isinstance(s, dict)]
    rel = path.relative_to(REPO_ROOT).as_posix()

    if not shots:
        result.fail(f"{rel} lists no shots")
        return []

    seen: set[str] = set()
    running = 0
    total_words = 0
    for index, shot in enumerate(shots):
        shot_id = str(shot.get("shot_id", f"<row {index}>"))
        for key in REQUIRED_FIELDS:
            if key not in shot or shot[key] is None or shot[key] == "":
                result.fail(f"{rel}:{shot_id} is missing a value for '{key}'")
        if shot_id in seen:
            result.fail(f"{rel}:{shot_id} is a duplicate shot_id")
        seen.add(shot_id)

        duration = shot.get("dur")
        if not isinstance(duration, int) or duration <= 0:
            result.fail(f"{rel}:{shot_id} has a non-positive integer duration {duration!r}")
            continue
        start = shot.get("t")
        if start != running:
            result.fail(
                f"{rel}:{shot_id} starts at t={start} but the running sum of durations "
                f"is {running} — the timecodes have drifted from the durations"
            )
        running += duration

        vo = str(shot.get("vo", ""))
        declared = shot.get("word_count")
        actual = _words(vo)
        if declared != actual:
            result.fail(
                f"{rel}:{shot_id} declares word_count={declared!r} but its vo holds "
                f"{actual} words — the budget cannot be met by mistyping it"
            )
        total_words += actual

        haystack = f"{shot.get('on_screen', '')}\n{vo}"
        for match in SHA7.finditer(haystack):
            result.fail(
                f"{rel}:{shot_id} contains the seven-hex literal {match.group(0)!r}. "
                "commit_id is sha256 over the JCS envelope and cannot be chosen; the "
                "film shows whatever the DAG produced"
            )
        for match in BARE_INVARIANT.finditer(vo):
            result.fail(
                f"{rel}:{shot_id} speaks the invariant number {match.group(0)!r}. "
                "BUILD_PLAN §5.2: the film cites constraint names, never numbers"
            )

    result.facts[f"{label}.total_s"] = running
    result.facts[f"{label}.shots"] = len(shots)
    result.facts[f"{label}.vo_words"] = total_words
    result.facts[f"{label}.headroom_s"] = HARD_CEILING_S - running

    if running > ceiling_s:
        result.fail(f"{rel} sums to {running} s, over its {ceiling_s} s ceiling")
    if require_headroom and (HARD_CEILING_S - running) < MIN_HEADROOM_S:
        result.fail(
            f"{rel} sums to {running} s, leaving {HARD_CEILING_S - running} s below the "
            f"{HARD_CEILING_S} s disqualifier — the plan requires at least {MIN_HEADROOM_S} s"
        )
    if require_headroom and running >= CI_HARD_FAIL_S:
        result.fail(f"{rel} sums to {running} s, at or over demo.yml's {CI_HARD_FAIL_S} s gate")
    if total_words > VO_WORD_BUDGET:
        result.fail(f"{rel} carries {total_words} spoken words, over the {VO_WORD_BUDGET} budget")

    declared_budget = document.get("budget")
    if isinstance(declared_budget, dict):
        stated = declared_budget.get("total_s")
        if stated is not None and stated != running:
            result.fail(f"{rel} declares budget.total_s={stated} but its shots sum to {running}")
        stated_headroom = declared_budget.get("headroom_s")
        if stated_headroom is not None and stated_headroom != HARD_CEILING_S - running:
            result.fail(
                f"{rel} declares headroom_s={stated_headroom} but the real headroom is "
                f"{HARD_CEILING_S - running}"
            )

    ladder = document.get("scope_cut_ladder")
    protected = {str(x) for x in document.get("never_cut", []) or []}
    if isinstance(ladder, list):
        for rung in ladder:
            if not isinstance(rung, dict):
                continue
            target = rung.get("cut") or rung.get("trim")
            if target and str(target) in protected:
                result.fail(
                    f"{rel} scope-cut ladder step {rung.get('step')} targets {target!r}, "
                    "which is on the never_cut list. The bypass beat is never cut for time"
                )
    for shot in shots:
        if shot.get("never_cut") and str(shot.get("shot_id")) not in protected:
            result.fail(
                f"{rel}:{shot.get('shot_id')} is marked never_cut but is absent from the "
                "document-level never_cut list, so the ladder does not know about it"
            )
    return shots


def check_vo_alignment(shots: list[dict[str, Any]], result: Result) -> None:
    """One line, two files, one assertion."""
    if not VO_FILE.is_file():
        result.fail("verticals/mainline/demo/script/VO.md does not exist — the VO is unchecked")
        return
    text = VO_FILE.read_text(encoding="utf-8")
    total = _words(text)
    result.facts["vo_md.words"] = total
    if total > VO_WORD_BUDGET:
        result.fail(f"VO.md holds {total} words, over the {VO_WORD_BUDGET} budget")
    normalised = " ".join(text.split())
    for shot in shots:
        line = " ".join(str(shot.get("vo", "")).split())
        if line and line not in normalised:
            result.fail(
                f"VO.md does not contain the line for {shot.get('shot_id')!r} verbatim: {line!r}"
            )
    for match in SHA7.finditer(text):
        result.fail(f"VO.md contains the seven-hex literal {match.group(0)!r}")
    for match in BARE_INVARIANT.finditer(text):
        result.fail(f"VO.md speaks the invariant number {match.group(0)!r}")


def check_camera_strings(result: Result) -> None:
    """One string, four files, one assertion.

    The 2013 commit message is the payload of beat 1 and the only piece of corpus
    prose that reaches the honesty card. It contains U+2192 and U+2014, and the
    assertion is byte-equality rather than resemblance — an ASCII ``->`` renders
    identically to a reader and is a different string to a test, which is exactly
    the kind of drift that survives review and appears on camera.

    The authored fixture is another worker's artefact. While it is absent this
    WARNS and says the check did not run; it becomes enforcing the moment the
    directory lands. Absence is never reported as a pass.
    """
    if not CAMERA_STRINGS.is_file():
        result.fail("CAMERA-STRINGS.yaml does not exist — the on-camera prose is unchecked")
        return
    document = yaml.safe_load(CAMERA_STRINGS.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not document.get("commit_message_2013"):
        result.fail("CAMERA-STRINGS.yaml carries no commit_message_2013")
        return
    message = str(document["commit_message_2013"])
    result.facts["camera.commit_message_chars"] = len(message)

    if "→" not in message or "—" not in message:
        result.fail(
            "commit_message_2013 has lost its U+2192 arrow or U+2014 em dash. Both are "
            "load-bearing: the equality test is byte-equal, not fuzzy"
        )

    required = {"SHOT-LIST.yaml": MAIN_LIST, "VO.md": VO_FILE}
    optional = {"honesty/card.html": CARD}
    for label, path in required.items():
        if not path.is_file():
            result.fail(f"{label} does not exist, so the camera string was not checked in it")
        elif message not in path.read_text(encoding="utf-8"):
            result.fail(f"{label} does not carry the 2013 commit message byte-identically")
    for label, path in optional.items():
        if not path.is_file():
            result.note(
                f"{label} has not been generated, so the camera string was not checked in it"
            )
        elif message not in path.read_text(encoding="utf-8"):
            result.fail(f"{label} does not carry the 2013 commit message byte-identically")

    if not AUTHORED.is_dir():
        result.note(
            "fixtures/corpus/authored/ does not exist yet (owner: corpus-spine-authored), so the "
            "authored fixture was not checked. This is not a pass — it enforces once the "
            "directory lands"
        )
    else:
        found = any(
            message in candidate.read_text(encoding="utf-8", errors="ignore")
            for candidate in AUTHORED.rglob("*")
            if candidate.is_file()
        )
        if not found:
            result.fail(
                "no file under fixtures/corpus/authored/ carries the 2013 commit message "
                "byte-identically — the script and the corpus disagree about what is on screen"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    result = Result()
    shots = check_shot_list(
        MAIN_LIST, result, ceiling_s=PLAN_CEILING_S, require_headroom=True, label="submission"
    )
    check_shot_list(MWS_LIST, result, ceiling_s=MWS_CEILING_S, require_headroom=True, label="mws")
    check_vo_alignment(shots, result)
    check_camera_strings(result)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "facts": result.facts,
                    "violations": result.violations,
                    "notes": result.notes,
                },
                indent=2,
            )
        )
    else:
        for key in sorted(result.facts):
            print(f"  {key:24s} {result.facts[key]}")
        for note in result.notes:
            print(f"  NOTE  {note}")
        for violation in result.violations:
            print(f"  FAIL  {violation}")
        print("  shot lists OK" if result.ok else f"  {len(result.violations)} violation(s)")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
