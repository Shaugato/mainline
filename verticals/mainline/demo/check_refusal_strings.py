#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Assert that every string the film speaks is a string the database produces.

    python verticals/mainline/demo/check_refusal_strings.py
    python verticals/mainline/demo/check_refusal_strings.py --json

`REFUSAL-STRINGS.yaml` is the single source of every constraint name, SQLSTATE and
`RAISE` message that appears on camera, and a single source is only worth having if
something checks it against the thing it claims to mirror. This does, in six ways,
each of which corresponds to a way the film could be wrong in public:

1. **The SQLSTATE is modelled.** Every code named here appears in `spec/errors.md`
   §2 as one of the five modelled codes. A film showing a code outside the closed
   set would be showing a refusal nobody designed.
2. **The exhibit exists in the schema.** A constraint name is grepped for in the
   migration the entry names, so a rename in the kernel turns the video script red
   rather than turning the video into a lie.
3. **The message is verbatim.** Every `P0001` message is byte-matched against the
   migration line that raises it, em dash and all.
4. **The message obeys §3.2.** `<PREFIX>: <one sentence, lower case, no trailing
   full stop>`, with the prefix drawn from the closed set — because clients parse
   the prefix and `trappoint_core.errors.diagnose` recovers the raising object from
   the sentence.
5. **The synthetic-code ban holds (§3.3).** No entry may claim that procedural code
   raises `23514`, `23503`, `23505` or `40001`. A synthetic constraint-backed code
   carries no constraint name, which produces an exhibit nobody can name.
6. **Every match target is tape-safe.** `terminal_match` must be ASCII and must
   contain no forward slash, because vhs#592 makes a slash unescapable inside a
   `Wait` regex — a defect that costs a shoot day if it is found on capture day.

Plus two cheap consistency checks that catch renames: every `shot_ids` entry exists
in `SHOT-LIST.yaml`, and the vector index named in `explain_fragment` exists in the
migration that declares it.

**Absence is never a pass.** If `spec/errors.md` is missing the SQLSTATE check
WARNS and says it did not run; if the migration tree is missing the schema checks
WARN. Neither is reported as success. `spec/errors.md` is present in this
repository today, so check 1 is enforcing.

Exit status: ``0`` every enforceable check passed, ``1`` at least one failed.
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

HERE = Path(__file__).resolve().parent  # verticals/mainline/demo
REPO_ROOT = HERE.parents[2]  # …/demo → mainline → verticals → <root>

REFUSAL_STRINGS = HERE / "REFUSAL-STRINGS.yaml"
SHOT_LIST = HERE / "script/SHOT-LIST.yaml"
SPEC_ERRORS = REPO_ROOT / "spec/errors.md"
MIGRATIONS = REPO_ROOT / "verticals/mainline/db/migrations"

#: spec/errors.md §1: the closed set. `00000` is not an error but is a modelled
#: expectation, so an entry may legitimately name it (the DROP CONSTRAINT shot).
MODELLED = {"40001", "23514", "23503", "23505", "P0001", "42501", "00000"}
#: §3.3 — procedural code must never impersonate a constraint-backed code.
NEVER_RAISED = {"23514", "23503", "23505", "40001"}
#: §3.2 — the prefix is stable because clients parse it.
PREFIXES = ("TRAPPOINT", "MAINLINE")

MESSAGE_SHAPE = re.compile(r"^(?P<prefix>[A-Z][A-Z0-9_]*): (?P<sentence>.+)$")


@dataclass(slots=True)
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, entry: str, message: str) -> None:
        self.failures.append(f"{entry}: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.failures


def _load_yaml(path: Path, report: Report) -> dict[str, Any] | None:
    if not path.is_file():
        report.fail(path.name, "does not exist, so nothing in it was checked")
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        report.fail(path.name, f"does not parse: {exc}")
        return None
    if not isinstance(loaded, dict):
        report.fail(path.name, "is not a mapping")
        return None
    return loaded


def _migration_text(reference: str, report: Report, entry: str) -> str | None:
    """Resolve a ``path:line`` or ``path:from-to`` reference to file text."""
    raw = str(reference)
    path_part = raw.split(":", 1)[0]
    path = REPO_ROOT / path_part
    if not path.is_file():
        report.warn(
            f"{entry}: {path_part} is not present, so its exhibit and message were not checked"
        )
        return None
    return path.read_text(encoding="utf-8")


def check_entry(  # noqa: PLR0912 - six independent checks, each named in the docstring
    entry: dict[str, Any], report: Report, *, spec_present: bool
) -> None:
    ident = str(entry.get("id", "<unnamed>"))
    report.checked += 1

    sqlstate = entry.get("sqlstate")
    kind = str(entry.get("exhibit_kind", ""))
    exhibit = entry.get("exhibit")
    message = entry.get("message")

    # 1 · the SQLSTATE is modelled
    if sqlstate is not None:
        if not spec_present:
            report.warn(f"{ident}: spec/errors.md is absent, so its SQLSTATE was not checked")
        elif str(sqlstate) not in MODELLED:
            report.fail(
                ident,
                f"names SQLSTATE {sqlstate!r}, which is outside the closed set in "
                "spec/errors.md §1. A code nobody modelled is a defect, not an edge case",
            )

    # 5 · the synthetic-code ban
    if kind == "raising_object" and str(sqlstate) in NEVER_RAISED:
        report.fail(
            ident,
            f"claims procedural code raises {sqlstate!r}. spec/errors.md §3.3 forbids it: a "
            "synthetic constraint-backed code carries no constraint name, so the exhibit is "
            "one nobody can name",
        )

    text = None
    if entry.get("defined_in"):
        text = _migration_text(entry["defined_in"], report, ident)

    # 2 · the exhibit exists in the schema
    if (
        text is not None
        and kind == "constraint"
        and exhibit
        and f"CONSTRAINT {exhibit}" not in text
        and str(exhibit) not in text
    ):
        report.fail(
            ident,
            f"names constraint {exhibit!r}, which does not appear in {entry['defined_in']}",
        )
    if text is not None and kind == "raising_object" and exhibit:
        bare = str(exhibit).split(".")[-1]
        if bare not in text:
            report.fail(
                ident,
                f"names raising object {exhibit!r}, which does not appear in {entry['defined_in']}",
            )

    # 3 · the message is verbatim
    if message is not None:
        if text is not None and str(message) not in text:
            report.fail(
                ident,
                f"carries a message that does not appear verbatim in {entry['defined_in']}. "
                "Check the em dash and the exact wording",
            )
        # 4 · §3.2 shape
        shaped = MESSAGE_SHAPE.match(str(message))
        if shaped is None:
            report.fail(ident, "message does not match '<PREFIX>: <sentence>' (spec §3.2)")
        else:
            if shaped.group("prefix") not in PREFIXES:
                report.fail(
                    ident,
                    f"message prefix {shaped.group('prefix')!r} is not one of {PREFIXES}. "
                    "The prefix is stable because clients parse it",
                )
            sentence = shaped.group("sentence")
            if sentence.endswith("."):
                report.fail(ident, "message ends in a full stop; spec §3.2 says it must not")
            if sentence[:1].isupper():
                report.fail(ident, "message sentence starts upper case; spec §3.2 says lower")

    # 6 · the match target is tape-safe
    target = entry.get("terminal_match")
    if target is not None:
        target = str(target)
        if "/" in target:
            report.fail(
                ident,
                "terminal_match contains a forward slash. vhs#592: a slash cannot be escaped "
                "inside a Wait regex, and discovering that on capture day costs the shoot",
            )
        if not target.isascii():
            report.fail(
                ident,
                "terminal_match is not ASCII. A terminal's rendering of an em dash is not "
                "something a tape should have to match on",
            )
        if message is not None and str(sqlstate) == "P0001" and target not in str(message):
            report.fail(
                ident,
                f"terminal_match {target!r} is not a substring of the message it claims to "
                "match, so a tape waiting on it would hang",
            )


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912 - a linear check sequence
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    args = parser.parse_args(argv)

    report = Report()
    document = _load_yaml(REFUSAL_STRINGS, report)
    if document is None:
        print("\n".join(f"  FAIL  {f}" for f in report.failures))
        return 1

    spec_present = SPEC_ERRORS.is_file()
    if not spec_present:
        report.warn(
            "spec/errors.md is absent — the SQLSTATE checks did not run. This is not a pass; "
            "it becomes enforcing the moment the file lands"
        )
    declared = document.get("spec_errors_present")
    if declared is not None and bool(declared) != spec_present:
        report.fail(
            "REFUSAL-STRINGS.yaml",
            f"declares spec_errors_present={declared!r} but spec/errors.md "
            f"{'exists' if spec_present else 'does not exist'}",
        )

    refusals = document.get("refusals")
    if not isinstance(refusals, list) or not refusals:
        report.fail("REFUSAL-STRINGS.yaml", "lists no refusals")
        refusals = []
    for entry in refusals:
        if isinstance(entry, dict):
            check_entry(entry, report, spec_present=spec_present)

    # Every shot referenced must exist in the shot list.
    shot_ids: set[str] = set()
    if SHOT_LIST.is_file():
        shot_doc = yaml.safe_load(SHOT_LIST.read_text(encoding="utf-8")) or {}
        shot_ids = {str(s.get("shot_id")) for s in shot_doc.get("shots", []) if isinstance(s, dict)}
    else:
        report.warn("SHOT-LIST.yaml is absent, so shot_ids references were not checked")
    if shot_ids:
        for entry in refusals:
            if not isinstance(entry, dict):
                continue
            for shot in entry.get("shot_ids") or []:
                if str(shot) not in shot_ids:
                    report.fail(
                        str(entry.get("id")),
                        f"references shot {shot!r}, which is not in SHOT-LIST.yaml",
                    )
        fragment = document.get("explain_fragment") or {}
        for shot in fragment.get("shot_ids") or []:
            if str(shot) not in shot_ids:
                report.fail("explain_fragment", f"references unknown shot {shot!r}")

    # The vector index must exist where the fragment says it does.
    fragment = document.get("explain_fragment") or {}
    if fragment.get("defined_in") and fragment.get("index"):
        text = _migration_text(fragment["defined_in"], report, "explain_fragment")
        index_name = str(fragment["index"]).split("@")[-1]
        if text is not None and index_name not in text:
            report.fail(
                "explain_fragment",
                f"names index {index_name!r}, which does not appear in {fragment['defined_in']}",
            )

    if args.json:
        print(
            json.dumps(
                {
                    "ok": report.ok,
                    "checked": report.checked,
                    "failures": report.failures,
                    "warnings": report.warnings,
                },
                indent=2,
            )
        )
    else:
        print(f"  checked {report.checked} refusal string(s)")
        for warning in report.warnings:
            print(f"  WARN  {warning}")
        for failure in report.failures:
            print(f"  FAIL  {failure}")
        print(
            "  refusal strings agree with the kernel"
            if report.ok
            else f"  {len(report.failures)} disagreement(s)"
        )
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
