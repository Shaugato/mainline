#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# I: QA-RATCHET-2 — licence coverage is a counted, published number that may fall and may
#    not rise. A number recorded at 0 is a hard gate.
# MI: CI-REGISTRY-1 — `.github/workflows/ci.yml` job `checkers` names this exact path and
#     exits 1 if it is absent; job `reuse` then runs it as `python3 scripts/qa/check_reuse.py`
#     with no arguments, no third-party package and egress blocked by harden-runner.
"""The REUSE guard: every tracked file names a licence, and every licence has a text.

WHAT THIS ASSERTS, IN FOUR SENTENCES.  Every tracked file resolves exactly one licence
identifier, by one of three mechanisms in a fixed order.  Every identifier so resolved has
a licence text on disk under `LICENSES/`.  Every text under `LICENSES/` is referenced by at
least one file, so the directory cannot silently accumulate licences the project does not
actually use.  And every *count* those three assertions produce is frozen in
`qa/reuse-ratchet.json`: it may fall, and it may not rise without a human running
`--write` and leaving the increase in a diff someone has to approve.

THE THREE MECHANISMS, IN PRECEDENCE ORDER (REUSE Specification 3.3).

  1. **Header.**  `SPDX-License-Identifier: <id>` inside the first 4 KiB of the file.
     4 KiB and not "anywhere in the file" on purpose: the root `LICENSE` is the Apache
     Software Foundation's text and that text quotes `SPDX-License-Identifier: Apache-2.0`
     inside its own appendix boilerplate, roughly 11 KiB in.  A parser that reads whole
     files decides the Apache licence text is a file licensed under Apache-2.0, which is a
     different statement and a false one.  A header is a header because of where it is.

  2. **Sidecar.**  An adjacent `<file>.license` holding the header the file cannot carry.

  3. **`REUSE.toml`.**  The last `[[annotations]]` table whose `path` glob matches wins —
     "exclusively the LAST matching table in the file is used" — and `precedence`
     decides whether it defers to a header (`closest`, the default) or replaces one
     (`override`).  4 518 of 7 120 tracked files cannot carry a header at all: 4 461 are
     `.json`, and JSON has no comment syntax.

WHY A COLON AND NOT A SUBSTRING.  This parser requires the literal `SPDX-License-Identifier:`.
`qa/mypy-ratchet.json` and `qa/test-state.json` carry the tag as a *JSON key*
(`"SPDX-License-Identifier": "Apache-2.0"`), and `REUSE.toml` carries it as a *TOML
assignment* (`SPDX-License-Identifier = "Apache-2.0"`).  Neither is a REUSE header;
REUSE reads comment headers.  A substring test would score all three as covered and would
therefore never notice that `REUSE.toml` is the one file in the tree that its own map does
not map.  It does not, this checker says so, and the exemption that keeps the build green
is declared in the baseline under `policy.exempt_paths`, printed on every run, and
counted in `census.exempt_by_policy` — so a second exemption cannot be added without
editing a committed list that a reviewer reads.  `[STALE-EXEMPTION]` refuses a declared
exemption whose path is no longer on disk.

WHY A RATCHET AND NOT ZERO.  The same licence is spelled two ways in this tree:
`FSL-1.1-ALv2` (not on the SPDX licence list, therefore not a legal identifier under the
spec) and `LicenseRef-FSL-1.1-ALv2` (legal).  Repairing that by rewriting every header
would touch files owned by all eight build domains at once and is forbidden by the
ownership rule; ruling L-1 in `docs/leads/submission-plan.md` chose instead to ship both
filenames in `LICENSES/` holding byte-identical text and to **publish the divergence as a
number that may fall and may not rise**.  A truthful counted divergence beats a silent
mass edit.  `docs/submission/LICENCE-CENSUS.md` prints the number and the command.

WHICH NUMBERS ARE GATED, AND WHY NOT ALL OF THEM.  `counted` is gated: every value there
may fall and may not rise.  `census` is recorded and printed but not gated, because those
are *coverage* totals — `tracked_files`, `covered_by_header` — and they move in both
directions with the ordinary life of the tree.  Gating them from rising would make adding
a file a red build; gating them from falling would make deleting one a red build.  The
number that actually carries the claim is `uncovered`, and it is gated at 0 both in total
and per top-level directory, so coverage cannot regress anywhere without naming the place.

RED FIRST (PL-2).  `--self-test` builds a synthetic repository in a temporary directory,
proves the checker passes on it, then plants one of every violation family in turn and
requires the checker to refuse each.  A lint that has never been red asserts nothing.

EXIT CODES.  0 pass · 1 a check refused · 2 tooling refusal (no git, no `REUSE.toml`, an
unreadable baseline).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "mainline.qa.reuse-ratchet/1"

#: The header window.  See the module docstring for why this is not "the whole file".
HEADER_WINDOW_BYTES = 4096

LICENCE_DIR = "LICENSES"
SIDECAR_SUFFIX = ".license"
LICENSE_REF_PREFIX = "LicenseRef-"
ROOT_BUCKET = "<root>"

_IDENT = r"[A-Za-z0-9.+-]+"
#: `SPDX-License-Identifier:` followed by an SPDX licence expression.  The identifier
#: character class deliberately excludes `"` and `,` so that a tag embedded in a Python or
#: JSON string literal (`"SPDX-License-Identifier: Apache-2.0\n"`) yields `Apache-2.0`
#: rather than `Apache-2.0\n",`.
HEADER_RE = re.compile(
    rf"SPDX-License-Identifier:[ \t]*({_IDENT}(?:[ \t]+(?:AND|OR|WITH)[ \t]+{_IDENT})*)"
)

#: Resolution mechanisms, in the order this checker tries them.
BY_HEADER = "header"
BY_SIDECAR = "sidecar"
BY_REUSE_TOML = "reuse_toml"
BY_REUSE_TOML_OVERRIDE = "reuse_toml_override"
EXEMPT_LICENCE_TEXT = "exempt_licence_text"
EXEMPT_SIDECAR_FILE = "exempt_sidecar_file"
EXEMPT_BY_POLICY = "exempt_by_policy"
UNCOVERED = "uncovered"

EXEMPTING = (EXEMPT_LICENCE_TEXT, EXEMPT_SIDECAR_FILE, EXEMPT_BY_POLICY)

#: Used only when no baseline exists yet, i.e. by the very first `--write`.  Never an
#: override: if `qa/reuse-ratchet.json` declares `policy`, that wins, because a guard
#: carrying its own copy of the policy would pass on the day someone narrowed the real one.
DEFAULT_POLICY: dict[str, object] = {
    "exempt_paths": ["REUSE.toml"],
    "exempt_paths_why": (
        "REUSE.toml declares `SPDX-License-Identifier` as a TOML assignment for OTHER "
        "files; it carries no header of its own and no [[annotations]] table in it "
        "matches its own path. REUSE Specification 3.3 exempts the LICENSES/ directory "
        "and `.license` files by name and does not name REUSE.toml, so this checker will "
        "not claim the spec exempts it. It is exempted here BY DECLARED POLICY, the "
        "exemption is printed on every run and recorded in census.exempt_by_policy, a "
        "declaration whose path leaves the tree is refused as [STALE-EXEMPTION], and the "
        "repair is a three-line [[annotations]] block in REUSE.toml — a file this "
        "checker's owner does not own. Cross-domain note, not a silent pass."
    ),
    "non_spdx_identifiers": ["FSL-1.1-ALv2"],
    "non_spdx_identifiers_why": (
        "The Functional Source License is not on the SPDX licence list, so REUSE 3.3 "
        "requires the `LicenseRef-` form. Both spellings exist in this tree and both "
        "ship a text in LICENSES/. Ruling L-1: publish the divergence as a counted "
        "number rather than mass-edit headers across eight ownership domains."
    ),
}


class ToolingError(RuntimeError):
    """Refusal for a reason that is not the tree's fault. Exit 2."""


# --------------------------------------------------------------------------------------
# Globs, per REUSE Specification 3.3: `*` matches anything except `/`, `**` matches
# anything including `/`. Nothing else is special. Translated literally — `packages/**/*.json`
# therefore requires at least one directory between the two, which is what the spec says
# and not what a shell would do.
# --------------------------------------------------------------------------------------


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a REUSE path glob into an anchored regular expression."""
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


@dataclass(frozen=True)
class Annotation:
    """One `[[annotations]]` table, flattened to (pattern, compiled, licence, precedence)."""

    index: int
    patterns: tuple[str, ...]
    regexes: tuple[re.Pattern[str], ...]
    licence: str
    precedence: str

    def matches(self, rel: str) -> bool:
        return any(rx.match(rel) for rx in self.regexes)


def load_annotations(reuse_toml: Path) -> list[Annotation]:
    """Parse `REUSE.toml` into ordered annotations. Order is meaning: last match wins."""
    if not reuse_toml.is_file():
        raise ToolingError(f"{reuse_toml} does not exist; there is no licence map to check")
    try:
        doc = tomllib.loads(reuse_toml.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ToolingError(f"{reuse_toml} is not readable TOML: {exc}") from exc

    tables = doc.get("annotations")
    if not isinstance(tables, list) or not tables:
        raise ToolingError(f"{reuse_toml} declares no [[annotations]] tables")

    out: list[Annotation] = []
    for i, table in enumerate(tables):
        raw = table.get("path")
        if raw is None:
            raise ToolingError(f"{reuse_toml}: [[annotations]] #{i} has no `path`")
        paths = tuple([raw] if isinstance(raw, str) else raw)
        licence = table.get("SPDX-License-Identifier")
        if not isinstance(licence, str) or not licence:
            raise ToolingError(
                f"{reuse_toml}: [[annotations]] #{i} ({paths[0]}) has no SPDX-License-Identifier"
            )
        out.append(
            Annotation(
                index=i,
                patterns=paths,
                regexes=tuple(glob_to_regex(p) for p in paths),
                licence=licence,
                precedence=str(table.get("precedence", "closest")),
            )
        )
    return out


# --------------------------------------------------------------------------------------
# The tree
# --------------------------------------------------------------------------------------


def git_ls_files(repo_root: Path) -> list[str]:
    """Every tracked path, NUL-separated so a path with a quote or a space survives."""
    git = shutil.which("git")
    if git is None:
        raise ToolingError("git is not on PATH; this checker enumerates via `git ls-files -z`")
    try:
        proc = subprocess.run(
            [git, "ls-files", "-z"],
            cwd=repo_root,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace").strip()
        raise ToolingError(f"`git ls-files -z` failed in {repo_root}: {stderr}") from exc
    raw = proc.stdout.decode("utf-8", "surrogateescape")
    return sorted(p for p in raw.split("\0") if p)


def header_identifier(path: Path) -> tuple[str | None, bool]:
    """Return (identifier or None, readable). Only the first `HEADER_WINDOW_BYTES` count."""
    try:
        with path.open("rb") as handle:
            head = handle.read(HEADER_WINDOW_BYTES)
    except OSError:
        return None, False
    match = HEADER_RE.search(head.decode("utf-8", "replace"))
    return (match.group(1) if match else None), True


#: The two spellings of the census command that `docs/submission/LICENCE-CENSUS.md`
#: publishes. They are RUN, not reimplemented, so the number in `qa/reuse-ratchet.json` and
#: the number a reader gets from the documented one-liner come from the same program.
#: `[^ ]*` stops at the first space and `.*` runs to end of line, which is the whole of the
#: difference between 1 167 and 1 163: four headers sit inside an HTML comment and end
#: `FSL-1.1-ALv2 -->`.
OCCURRENCE_PATTERNS = {
    "token": "SPDX-License-Identifier: [^ ]*",
    "line": "SPDX-License-Identifier: .*",
}


def occurrence_census(repo_root: Path, pattern: str) -> Counter[str]:
    """`git grep -h -o -E <pattern> | sed 's/.*: //' | sort | uniq -c`, in one call.

    Counts OCCURRENCES across whole files, not files, and therefore also counts the tag
    where it appears inside a string literal or a template. That is why this census is
    recorded and not gated: writing a test fixture that contains the string would
    otherwise be a red build.
    """
    git = shutil.which("git")
    if git is None:
        raise ToolingError("git is not on PATH")
    proc = subprocess.run(
        [git, "grep", "-h", "-o", "-E", pattern],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if proc.returncode not in (0, 1):  # 1 == no matches, which is not an error here
        stderr = proc.stderr.decode("utf-8", "replace").strip()
        raise ToolingError(f"`git grep -o -E {pattern!r}` failed: {stderr}")
    counter: Counter[str] = Counter()
    for raw in proc.stdout.decode("utf-8", "replace").splitlines():
        line = raw.rstrip("\r")
        if not line:
            continue
        # `sed 's/.*: //'` is greedy: it strips through the LAST ": " in the match.
        _, sep, rest = line.rpartition(": ")
        counter[rest if sep else line] += 1
    return counter


def top_level(rel: str) -> str:
    return rel.split("/", 1)[0] if "/" in rel else ROOT_BUCKET


@dataclass
class FileVerdict:
    rel: str
    resolved_by: str
    licence: str | None


@dataclass
class Report:
    """One complete observation of the tree."""

    repo_root: Path
    verdicts: list[FileVerdict] = field(default_factory=list)
    header_census: Counter[str] = field(default_factory=Counter)
    licence_texts: dict[str, str] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    orphan_sidecars: list[str] = field(default_factory=list)
    dead_patterns: list[str] = field(default_factory=list)
    pattern_hits: dict[str, int] = field(default_factory=dict)
    annotation_tables: int = 0
    policy: dict[str, object] = field(default_factory=dict)
    stale_exemptions: list[str] = field(default_factory=list)
    occurrences: dict[str, Counter[str]] = field(default_factory=dict)
    dead_but_present: dict[str, int] = field(default_factory=dict)

    # ---- derived -------------------------------------------------------------------

    @property
    def uncovered(self) -> list[str]:
        return [v.rel for v in self.verdicts if v.resolved_by == UNCOVERED]

    @property
    def exempt_by_policy(self) -> list[str]:
        return [v.rel for v in self.verdicts if v.resolved_by == EXEMPT_BY_POLICY]

    @property
    def resolved_census(self) -> Counter[str]:
        return Counter(v.licence for v in self.verdicts if v.licence is not None)

    @property
    def by_mechanism(self) -> Counter[str]:
        return Counter(v.resolved_by for v in self.verdicts)

    def identifiers_without_text(self) -> list[str]:
        return sorted(
            ident
            for ident in self.resolved_census
            if not licence_text_for(ident, self.licence_texts)
        )

    def unreferenced_texts(self) -> list[str]:
        used = set(self.resolved_census)
        satisfying: set[str] = set()
        for ident in used:
            name = licence_text_for(ident, self.licence_texts)
            if name is not None:
                satisfying.add(name)
        return sorted(set(self.licence_texts.values()) - satisfying)


def alias_forms(identifier: str) -> tuple[str, ...]:
    """The spellings under which a licence text may satisfy `identifier`.

    Ruling L-1: `FSL-1.1-ALv2` and `LicenseRef-FSL-1.1-ALv2` name the same licence and
    ship byte-identical texts, so either filename satisfies either identifier. The rule is
    stated once, here, and is mechanical rather than a hardcoded pair.
    """
    if identifier.startswith(LICENSE_REF_PREFIX):
        return (identifier, identifier[len(LICENSE_REF_PREFIX) :])
    return (identifier, LICENSE_REF_PREFIX + identifier)


def licence_text_for(identifier: str, texts: dict[str, str]) -> str | None:
    """The filename in `LICENSES/` that satisfies `identifier`, or None."""
    for form in alias_forms(identifier):
        if form in texts:
            return texts[form]
    return None


def read_licence_texts(repo_root: Path) -> dict[str, str]:
    """`LICENSES/<identifier>.txt` -> {identifier: filename}.

    Read from the working tree rather than from the index, because that is what a fork
    receives and what `reuse lint` would read.
    """
    directory = repo_root / LICENCE_DIR
    if not directory.is_dir():
        return {}
    out: dict[str, str] = {}
    for entry in sorted(directory.iterdir()):
        if entry.is_file():
            out[entry.stem if entry.suffix == ".txt" else entry.name] = entry.name
    return out


def exempt_class(rel: str, exempt_paths: set[str]) -> str | None:
    """The exemption this path falls under, or None if it must resolve a licence.

    The first two are REUSE 3.3's own exemptions — licence texts are not licensed
    material, and a `.license` sidecar IS the licensing information rather than a thing
    needing some. The third is this repository's, declared in `policy.exempt_paths` and
    counted.
    """
    if rel == LICENCE_DIR or rel.startswith(LICENCE_DIR + "/"):
        return EXEMPT_LICENCE_TEXT
    if rel.endswith(SIDECAR_SUFFIX):
        return EXEMPT_SIDECAR_FILE
    if rel in exempt_paths:
        return EXEMPT_BY_POLICY
    return None


def winning_annotation(
    rel: str, annotations: list[Annotation], hits: Counter[str]
) -> Annotation | None:
    """The LAST matching table, per REUSE 3.3. Records a hit for every pattern that matched.

    Every pattern is tried even after a table has matched, because the hit counter is what
    makes `reuse_toml_patterns_matching_nothing` meaningful: a pattern shadowed by its own
    neighbour is still a pattern that matched something.
    """
    winner: Annotation | None = None
    for ann in annotations:
        matched = False
        for pattern, rx in zip(ann.patterns, ann.regexes, strict=True):
            if rx.match(rel):
                hits[f"#{ann.index}:{pattern}"] += 1
                matched = True
        if matched:
            winner = ann
    return winner


def classify(
    rel: str,
    header: str | None,
    winner: Annotation | None,
    tracked: set[str],
    repo_root: Path,
) -> FileVerdict:
    """Apply the precedence order to one file: override, header, sidecar, annotation."""
    if winner is not None and winner.precedence == "override":
        return FileVerdict(rel, BY_REUSE_TOML_OVERRIDE, winner.licence)
    if header is not None:
        return FileVerdict(rel, BY_HEADER, header)
    sidecar = rel + SIDECAR_SUFFIX
    if sidecar in tracked or (repo_root / sidecar).exists():
        side_ident, _ = header_identifier(repo_root / sidecar)
        if side_ident is not None:
            return FileVerdict(rel, BY_SIDECAR, side_ident)
    if winner is not None:
        return FileVerdict(rel, BY_REUSE_TOML, winner.licence)
    return FileVerdict(rel, UNCOVERED, None)


def measure(repo_root: Path, policy: dict[str, object]) -> Report:
    """One pass over the tree. Everything downstream reads this and nothing re-measures."""
    annotations = load_annotations(repo_root / "REUSE.toml")
    tracked = git_ls_files(repo_root)
    tracked_set = set(tracked)
    declared = policy.get("exempt_paths")
    exempt_paths = {str(p) for p in declared} if isinstance(declared, list) else set()

    report = Report(repo_root=repo_root)
    report.licence_texts = read_licence_texts(repo_root)
    report.annotation_tables = len(annotations)
    report.policy = policy
    hits: Counter[str] = Counter()
    all_patterns = [f"#{a.index}:{p}" for a in annotations for p in a.patterns]

    for rel in tracked:
        # The header census counts EVERY tracked file, sidecars and licence texts
        # included, because it answers "how is this tree spelled", not "is it covered".
        ident, readable = header_identifier(repo_root / rel)
        if not readable:
            report.unreadable.append(rel)
        if ident is not None:
            report.header_census[ident] += 1

        exempt = exempt_class(rel, exempt_paths)
        if exempt is not None:
            target = rel[: -len(SIDECAR_SUFFIX)]
            if (
                exempt == EXEMPT_SIDECAR_FILE
                and target not in tracked_set
                and not (repo_root / target).exists()
            ):
                report.orphan_sidecars.append(rel)
            report.verdicts.append(FileVerdict(rel, exempt, None))
            continue

        winner = winning_annotation(rel, annotations, hits)
        report.verdicts.append(classify(rel, ident, winner, tracked_set, repo_root))

    report.pattern_hits = {p: hits.get(p, 0) for p in all_patterns}
    report.dead_patterns = sorted(p for p, n in report.pattern_hits.items() if n == 0)
    # A declared exemption for a path that is not there any more is a claim nobody is
    # checking. Deleting the line is the repair; leaving it is how an exemption list
    # outlives the reason it was written.
    report.stale_exemptions = sorted(p for p in exempt_paths if not (repo_root / p).exists())
    report.occurrences = {
        name: occurrence_census(repo_root, pattern) for name, pattern in OCCURRENCE_PATTERNS.items()
    }
    report.dead_but_present = dead_patterns_matching_untracked(
        repo_root, annotations, report.dead_patterns
    )
    return report


def dead_patterns_matching_untracked(
    repo_root: Path, annotations: list[Annotation], dead: list[str]
) -> dict[str, int]:
    """Of the globs that matched no TRACKED file, which match files that exist anyway?

    The distinction is the whole difference between a mistake and a queue. A glob written
    for a directory that has been created but not committed is not a dead glob; it is a
    glob waiting on a `git add`, and it will come alive — lowering the count — the moment
    someone runs one. Saying "5 dead globs" without saying which kind each is would be a
    number that misleads by being true.
    """
    if not dead:
        return {}
    lookup = {
        f"#{a.index}:{p}": rx
        for a in annotations
        for p, rx in zip(a.patterns, a.regexes, strict=True)
    }
    present: list[str] = []
    for path in repo_root.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            present.append(path.relative_to(repo_root).as_posix())
    out: dict[str, int] = {}
    for key in dead:
        rx = lookup.get(key)
        if rx is None:
            continue
        hits = sum(1 for rel in present if rx.match(rel))
        if hits:
            out[key] = hits
    return out


# --------------------------------------------------------------------------------------
# The baseline
# --------------------------------------------------------------------------------------


def counted_of(report: Report) -> dict[str, object]:
    """The gated numbers. Every value here may FALL and may not RISE."""
    policy = report.policy
    non_spdx = [str(x) for x in policy.get("non_spdx_identifiers", [])]  # type: ignore[union-attr]
    resolved = report.resolved_census
    uncovered_by_dir = Counter(top_level(rel) for rel in report.uncovered)
    dirs = sorted({top_level(v.rel) for v in report.verdicts})
    # NOT gated, deliberately: `files_exempt_by_policy`. The exemption list itself lives in
    # `policy.exempt_paths` in this same committed file, so a new exemption is already a
    # reviewed diff, and the COUNT moves for a second reason — a declared path that is on
    # disk but not yet tracked exempts nothing until it is committed. Gating it would turn
    # `git add REUSE.toml` into a red build. `stale_exemptions` is a structural refusal
    # instead, and the count is recorded in `census`.
    return {
        "uncovered_total": len(report.uncovered),
        "uncovered_by_top_level_directory": {d: uncovered_by_dir.get(d, 0) for d in dirs},
        "orphan_sidecars": len(report.orphan_sidecars),
        "unreadable_files": len(report.unreadable),
        "identifiers_without_licence_text": len(report.identifiers_without_text()),
        "unreferenced_licence_texts": len(report.unreferenced_texts()),
        "reuse_toml_patterns_matching_nothing": len(report.dead_patterns),
        "distinct_identifiers": len(resolved),
        "non_spdx_spelling": {ident: resolved.get(ident, 0) for ident in non_spdx},
    }


def census_of(report: Report) -> dict[str, object]:
    """The recorded numbers. Printed, diffed by eye, NOT gated. See the module docstring."""
    mech = report.by_mechanism
    per_dir: dict[str, dict[str, int]] = {}
    for verdict in report.verdicts:
        row = per_dir.setdefault(
            top_level(verdict.rel),
            {"files": 0, BY_HEADER: 0, BY_SIDECAR: 0, BY_REUSE_TOML: 0, "exempt": 0, UNCOVERED: 0},
        )
        row["files"] += 1
        if verdict.resolved_by == BY_REUSE_TOML_OVERRIDE:
            row[BY_REUSE_TOML] += 1
        elif verdict.resolved_by in EXEMPTING:
            row["exempt"] += 1
        else:
            row[verdict.resolved_by] += 1

    by_mechanism: dict[str, dict[str, int]] = {}
    for verdict in report.verdicts:
        if verdict.licence is None:
            continue
        cell = by_mechanism.setdefault(
            verdict.licence,
            {BY_HEADER: 0, BY_SIDECAR: 0, BY_REUSE_TOML: 0, BY_REUSE_TOML_OVERRIDE: 0},
        )
        cell[verdict.resolved_by] += 1

    return {
        "tracked_files": len(report.verdicts),
        "covered_by_header": mech[BY_HEADER],
        "covered_by_sidecar": mech[BY_SIDECAR],
        "covered_by_reuse_toml": mech[BY_REUSE_TOML] + mech[BY_REUSE_TOML_OVERRIDE],
        "covered_by_reuse_toml_override": mech[BY_REUSE_TOML_OVERRIDE],
        "exempt_licence_texts": mech[EXEMPT_LICENCE_TEXT],
        "exempt_sidecar_files": mech[EXEMPT_SIDECAR_FILE],
        "exempt_by_policy": mech[EXEMPT_BY_POLICY],
        "uncovered": mech[UNCOVERED],
        "reuse_toml_tables": report.annotation_tables,
        "reuse_toml_path_patterns": len(report.pattern_hits),
        "reuse_toml_patterns_matching_nothing": sorted(report.dead_patterns),
        "reuse_toml_patterns_matching_only_untracked": dict(
            sorted(report.dead_but_present.items())
        ),
        "licence_texts_on_disk": sorted(report.licence_texts.values()),
        "identifiers_resolved": dict(report.resolved_census.most_common()),
        "identifiers_resolved_by_mechanism": {k: by_mechanism[k] for k in sorted(by_mechanism)},
        "identifiers_in_headers": dict(report.header_census.most_common()),
        "identifiers_in_headers_note": (
            "one count per FILE: the FIRST match in the first "
            f"{HEADER_WINDOW_BYTES} bytes, over every tracked file including the 178 "
            "`.license` sidecars, which is why it exceeds `covered_by_header`"
        ),
        "identifier_occurrences": {
            name: dict(report.occurrences.get(name, Counter()).most_common(12))
            for name in OCCURRENCE_PATTERNS
        },
        "identifier_occurrences_note": (
            "one count per OCCURRENCE, whole file, from "
            "`git grep -h -o -E '<pattern>' | sed 's/.*: //' | sort | uniq -c | sort -rn`. "
            "`token` uses [^ ]* and `line` uses .*; the difference between them is headers "
            "whose line continues past the identifier, e.g. an HTML comment closing ` -->`. "
            "Top 12 buckets only. Recorded, never gated."
        ),
        "identifier_occurrence_commands": {
            name: f"git grep -h -o -E \"{pattern}\" | sed 's/.*: //' | sort | uniq -c | sort -rn"
            for name, pattern in OCCURRENCE_PATTERNS.items()
        },
        "by_top_level_directory": {d: per_dir[d] for d in sorted(per_dir)},
    }


def build_baseline(report: Report) -> dict[str, object]:
    return {
        "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
        "SPDX-License-Identifier": "Apache-2.0",
        "schema": SCHEMA,
        "$comment": (
            "Honest counts, not aspirations. Every number below was measured by "
            "`python3 scripts/qa/check_reuse.py --write` and none was chosen. Values under "
            "`counted` are GATED: each may fall and may not rise, and regenerating this "
            "file is the only way one rises. Values under `census` are recorded and "
            "printed but not gated, because they move in both directions with the ordinary "
            "life of the tree. See docs/submission/LICENCE-CENSUS.md."
        ),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checker": "scripts/qa/check_reuse.py",
        "commands": {
            "check": "python3 scripts/qa/check_reuse.py",
            "regenerate": "python3 scripts/qa/check_reuse.py --write",
            "self_test": "python3 scripts/qa/check_reuse.py --self-test",
        },
        "method": {
            "enumeration": "git ls-files -z",
            "header_window_bytes": HEADER_WINDOW_BYTES,
            "header_pattern": "SPDX-License-Identifier: <expression>, literal colon",
            "precedence": "header -> <file>.license sidecar -> last matching REUSE.toml glob",
            "override": (
                'an [[annotations]] table with precedence = "override" wins over a header'
            ),
            "glob": "REUSE 3.3: `*` matches anything except `/`, `**` matches anything",
            "licence_text_alias": (
                "an identifier is satisfied by LICENSES/<id>.txt or by "
                "LICENSES/LicenseRef-<id>.txt, and vice versa"
            ),
        },
        "snapshot_caveat": (
            "Taken while ten workers were writing to this tree. Two numbers here are "
            "snapshot-shaped and will move for reasons that are not regressions. (1) "
            "`reuse_toml_patterns_matching_nothing` counts globs that matched no TRACKED "
            "file; `census.reuse_toml_patterns_matching_only_untracked` names the ones "
            "that match files which exist on disk and have not been committed yet, and "
            "each of those FALLS to zero the moment someone runs `git add`. (2) the "
            "`census` identifier counts are re-derived live on every run and go stale in "
            "this file the instant a file lands; they are recorded, never gated. Re-take "
            "once on the merge commit with `--write` and quote the result in the PR body."
        ),
        "policy": report.policy,
        "counted": counted_of(report),
        "census": census_of(report),
    }


def load_baseline(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ToolingError(
            f"{path} does not exist. Take the baseline once with "
            "`python3 scripts/qa/check_reuse.py --write`."
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolingError(f"{path} is not readable JSON: {exc}") from exc
    if doc.get("schema") != SCHEMA:
        raise ToolingError(f"{path} declares schema {doc.get('schema')!r}, expected {SCHEMA!r}")
    if not isinstance(doc.get("counted"), dict):
        raise ToolingError(f"{path} has no `counted` object")
    return doc


def compare_counted(
    baseline: dict[str, object], measured: dict[str, object], prefix: str = ""
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements). A key absent from the baseline defaults to 0."""
    regressions: list[str] = []
    improvements: list[str] = []
    for key, value in sorted(measured.items()):
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            base_sub = baseline.get(key)
            sub_regs, sub_imps = compare_counted(
                base_sub if isinstance(base_sub, dict) else {},
                value,
                prefix=f"{name}.",
            )
            regressions.extend(sub_regs)
            improvements.extend(sub_imps)
            continue
        base = baseline.get(key, 0)
        if not isinstance(base, int):
            base = 0
        if not isinstance(value, int):
            raise ToolingError(f"counted.{name} is {type(value).__name__}, not an integer")
        if value > base:
            gate = " [HARD GATE: baseline is 0]" if base == 0 else ""
            regressions.append(f"metric={name} baseline={base} measured={value}{gate}")
        elif value < base:
            improvements.append(f"metric={name} baseline={base} measured={value}")
    return regressions, improvements


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def render_table(report: Report) -> str:
    census = census_of(report)
    rows: dict[str, dict[str, int]] = census["by_top_level_directory"]  # type: ignore[assignment]
    width = max([len("directory"), *(len(d) for d in rows)]) if rows else len("directory")
    heading = (
        f"{'directory':<{width}}  {'files':>7} {'header':>7} {'sidecar':>8} "
        f"{'REUSE.toml':>11} {'exempt':>7} {'UNCOVERED':>10}"
    )
    lines = [heading, "-" * (width + 56)]
    for name in sorted(rows):
        row = rows[name]
        lines.append(
            f"{name:<{width}}  {row['files']:>7} {row[BY_HEADER]:>7} {row[BY_SIDECAR]:>8} "
            f"{row[BY_REUSE_TOML]:>11} {row['exempt']:>7} {row[UNCOVERED]:>10}"
        )
    total = {
        "files": census["tracked_files"],
        BY_HEADER: census["covered_by_header"],
        BY_SIDECAR: census["covered_by_sidecar"],
        BY_REUSE_TOML: census["covered_by_reuse_toml"],
        "exempt": (
            int(census["exempt_licence_texts"])  # type: ignore[arg-type]
            + int(census["exempt_sidecar_files"])  # type: ignore[arg-type]
            + int(census["exempt_by_policy"])  # type: ignore[arg-type]
        ),
        UNCOVERED: census["uncovered"],
    }
    lines.append("-" * (width + 56))
    lines.append(
        f"{'TOTAL':<{width}}  {total['files']:>7} {total[BY_HEADER]:>7} "
        f"{total[BY_SIDECAR]:>8} {total[BY_REUSE_TOML]:>11} {total['exempt']:>7} "
        f"{total[UNCOVERED]:>10}"
    )
    return "\n".join(lines)


def render_identifiers(report: Report) -> str:
    lines = ["identifier                        resolved  header  LICENSES/ text"]
    lines.append("-" * 68)
    idents = sorted(
        set(report.resolved_census) | set(report.header_census),
        key=lambda i: (-report.resolved_census.get(i, 0), i),
    )
    for ident in idents:
        text = licence_text_for(ident, report.licence_texts)
        mark = text if text else "*** NONE ***"
        lines.append(
            f"{ident:<33} {report.resolved_census.get(ident, 0):>8} "
            f"{report.header_census.get(ident, 0):>7}  {mark}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------


def structural_failures(report: Report) -> list[str]:
    """The refusals that are NOT ratchetable. A broken licence map is not debt."""
    out: list[str] = []
    if report.uncovered:
        out.append(
            f"REFUSED [UNCOVERED] {len(report.uncovered)} tracked file(s) resolve no licence "
            "by header, by sidecar or by REUSE.toml"
        )
    missing = report.identifiers_without_text()
    if missing:
        out.append(
            f"REFUSED [NO-LICENCE-TEXT] {len(missing)} identifier(s) are declared by a file "
            f"and have no text in {LICENCE_DIR}/: {', '.join(missing)}"
        )
    orphans = report.unreferenced_texts()
    if orphans:
        out.append(
            f"REFUSED [ORPHAN-LICENCE-TEXT] {len(orphans)} text(s) in {LICENCE_DIR}/ are "
            f"referenced by no tracked file: {', '.join(orphans)}"
        )
    if report.stale_exemptions:
        out.append(
            f"REFUSED [STALE-EXEMPTION] policy.exempt_paths names "
            f"{len(report.stale_exemptions)} path(s) that are not on disk: "
            f"{', '.join(report.stale_exemptions)}. Delete the declaration; an exemption "
            "for a file that no longer exists is a claim nobody is checking."
        )
    return out


def _print_list(title: str, items: list[str], limit: int = 40) -> None:
    if not items:
        return
    print(f"{title} ({len(items)}):")
    for item in items[:limit]:
        print(f"    {item}")
    if len(items) > limit:
        print(f"    ... and {len(items) - limit} more")
    print()


def render_human(
    report: Report,
    baseline_path: Path,
    failures: list[str],
    improvements: list[str],
) -> None:
    print(f"REUSE coverage — {report.repo_root}")
    print(f"  enumeration : git ls-files -z          header window : {HEADER_WINDOW_BYTES} B")
    print(f"  baseline    : {baseline_path}")
    print()
    print(render_table(report))
    print()
    print(render_identifiers(report))
    print()
    if report.dead_patterns:
        print(
            f"REUSE.toml globs matching no TRACKED file "
            f"({len(report.dead_patterns)}) — counted, may not rise:"
        )
        for pattern in report.dead_patterns:
            present = report.dead_but_present.get(pattern, 0)
            note = (
                f"  <- matches {present} file(s) that exist but are NOT tracked; "
                "`git add` revives it"
                if present
                else "  <- matches nothing on disk either"
            )
            print(f"    {pattern}{note}")
        print()
    _print_list(
        "exempt by declared policy — see policy.exempt_paths_why in the baseline",
        report.exempt_by_policy,
    )
    _print_list("orphan .license sidecars — counted, may not rise", report.orphan_sidecars, 20)
    _print_list("UNREADABLE — counted, may not rise", report.unreadable, 20)
    _print_list("UNCOVERED — resolve a licence or annotate", report.uncovered)
    for line in improvements:
        print(f"  improved   {line}")
    for line in failures:
        print(line)


def render_json(
    report: Report, counted: dict[str, object], failures: list[str], improvements: list[str]
) -> None:
    print(
        json.dumps(
            {
                "ok": not failures,
                "counted": counted,
                "census": census_of(report),
                "uncovered": report.uncovered,
                "identifiers_without_licence_text": report.identifiers_without_text(),
                "unreferenced_licence_texts": report.unreferenced_texts(),
                "stale_exemptions": report.stale_exemptions,
                "reuse_toml_patterns_matching_nothing": report.dead_patterns,
                "reuse_toml_patterns_matching_only_untracked": report.dead_but_present,
                "orphan_sidecars": report.orphan_sidecars,
                "unreadable_files": report.unreadable,
                "failures": failures,
                "improvements": improvements,
            },
            indent=2,
            sort_keys=True,
        )
    )


def load_policy(baseline_path: Path, *, write: bool) -> dict[str, object]:
    """The policy the run will use, and the baseline it will compare against."""
    if not baseline_path.is_file():
        if not write:
            raise ToolingError(
                f"{baseline_path} does not exist. Take the baseline once with "
                "`python3 scripts/qa/check_reuse.py --write`."
            )
        return {}
    try:
        return load_baseline(baseline_path)
    except ToolingError:
        if not write:
            raise
        return {}


def run(repo_root: Path, baseline_path: Path, *, write: bool, as_json: bool) -> int:
    existing = load_policy(baseline_path, write=write)
    declared = existing.get("policy")
    report = measure(repo_root, declared if isinstance(declared, dict) else dict(DEFAULT_POLICY))

    counted = counted_of(report)
    failures = structural_failures(report)
    improvements: list[str] = []
    if not write:
        base = existing.get("counted")
        regressions, improvements = compare_counted(base if isinstance(base, dict) else {}, counted)
        failures.extend(f"REFUSED [RATCHET] {line}" for line in regressions)

    if as_json:
        render_json(report, counted, failures, improvements)
    else:
        render_human(report, baseline_path, failures, improvements)

    if write:
        if any("[RATCHET]" not in f for f in failures):
            if not as_json:
                print()
                print(
                    "--write REFUSED. `uncovered`, `identifiers_without_licence_text`, "
                    "`unreferenced_licence_texts` and `stale_exemptions` are broken states, "
                    "not debt: a baseline that recorded them would be a licence map that "
                    "admits it does not map. Fix the tree, then regenerate."
                )
            return 1
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n" so the artefact is byte-identical whether it was regenerated on
        # Windows or on the ubuntu-24.04 runner. A ratchet that churns its own line
        # endings produces a diff nobody reads.
        baseline_path.write_text(
            json.dumps(build_baseline(report), indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if not as_json:
            print(f"wrote {baseline_path}")
        return 0

    if failures:
        return 1
    if not as_json:
        print(
            f"OK — {len(report.verdicts)} tracked files, 0 uncovered, "
            f"{len(report.licence_texts)} licence texts, no counted number rose."
        )
    return 0


# --------------------------------------------------------------------------------------
# --self-test: the red half (PL-2)
# --------------------------------------------------------------------------------------

_FIXTURE_REUSE_TOML = """\
version = 1

SPDX-PackageName = "selftest"

[[annotations]]
path = ["data/**"]
precedence = "closest"
SPDX-FileCopyrightText = "2026 MAINLINE contributors"
SPDX-License-Identifier = "Apache-2.0"
"""

_TAG = "SPDX-License-Identifier"


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _git(repo: Path, env: dict[str, str], *args: str) -> None:
    git = shutil.which("git")
    if git is None:
        raise ToolingError("git is not on PATH; --self-test needs it to build a fixture index")
    subprocess.run([git, *args], cwd=repo, env=env, check=True, capture_output=True)


def _build_fixture(repo: Path) -> dict[str, str]:
    """A small, complete, GREEN repository: every family of resolution, nothing uncovered."""
    _write(repo, "REUSE.toml", _FIXTURE_REUSE_TOML)
    for name in ("Apache-2.0", "CC-BY-4.0", "FSL-1.1-ALv2", "LicenseRef-FSL-1.1-ALv2"):
        _write(repo, f"{LICENCE_DIR}/{name}.txt", f"Licence text for {name}.\n")
    _write(repo, "src/a.py", f"# {_TAG}: Apache-2.0\nprint('a')\n")
    # The deliberate two-spelling divergence, in miniature: one file of each.
    _write(repo, "src/b.py", f"# {_TAG}: FSL-1.1-ALv2\nprint('b')\n")
    _write(repo, "src/c.py", f"# {_TAG}: LicenseRef-FSL-1.1-ALv2\nprint('c')\n")
    _write(repo, "data/fixture.json", '{"no": "comment syntax"}\n')  # REUSE.toml covers it
    _write(repo, "docs/note.md", "prose that cannot carry a comment header\n")
    _write(repo, "docs/note.md.license", f"{_TAG}: CC-BY-4.0\n")
    # docs/** is matched by nothing, so docs/note.md is covered ONLY by its sidecar; that
    # is the point of putting it here rather than under data/.
    return {"reuse_toml": _FIXTURE_REUSE_TOML}


@dataclass
class Scenario:
    name: str
    why: str
    expect_ok: bool
    expect_token: str
    mutate: object  # Callable[[Path], None]
    flags: tuple[str, ...] = ()
    baseline_must_not_change: bool = False


def _self_test(verbose: bool = True) -> int:  # noqa: PLR0915 - a table of scenarios, read top to bottom
    checker = Path(__file__).resolve()

    def mutate_none(_repo: Path) -> None:
        return None

    def mutate_uncovered(repo: Path) -> None:
        _write(repo, "stray/orphan.txt", "no header, no sidecar, no annotation\n")

    def mutate_no_text(repo: Path) -> None:
        _write(repo, "src/e.py", f"# {_TAG}: MIT\nprint('e')\n")

    def mutate_orphan_text(repo: Path) -> None:
        _write(repo, f"{LICENCE_DIR}/BSD-3-Clause.txt", "a licence nothing references\n")

    def mutate_dead_glob(repo: Path) -> None:
        _write(
            repo,
            "REUSE.toml",
            _FIXTURE_REUSE_TOML
            + '\n[[annotations]]\npath = ["nowhere/**"]\nprecedence = "closest"\n'
            'SPDX-FileCopyrightText = "2026 MAINLINE contributors"\n'
            'SPDX-License-Identifier = "Apache-2.0"\n',
        )

    def mutate_count_rise(repo: Path) -> None:
        # A second file spelling the licence the non-SPDX way. Nothing is uncovered, no
        # licence text is missing, no glob is dead — the ONLY thing wrong is the count.
        _write(repo, "data/d.py", f"# {_TAG}: FSL-1.1-ALv2\nprint('d')\n")

    scenarios = [
        Scenario(
            "GREEN control",
            "a complete tree passes; a checker that always refuses is broken, not safe",
            True,
            "OK —",
            mutate_none,
        ),
        Scenario(
            "no header, no sidecar, no annotation",
            "the file nobody licensed",
            False,
            "[UNCOVERED]",
            mutate_uncovered,
        ),
        Scenario(
            "identifier with no text in LICENSES/",
            "a licence named but not shipped",
            False,
            "[NO-LICENCE-TEXT]",
            mutate_no_text,
        ),
        Scenario(
            "orphan text in LICENSES/",
            "a licence shipped but not used",
            False,
            "[ORPHAN-LICENCE-TEXT]",
            mutate_orphan_text,
        ),
        Scenario(
            "REUSE.toml glob matching nothing",
            "a map with a road to nowhere",
            False,
            "reuse_toml_patterns_matching_nothing",
            mutate_dead_glob,
        ),
        Scenario(
            "a counted number above the ratchet",
            "the divergent spelling grows by one",
            False,
            "non_spdx_spelling.FSL-1.1-ALv2",
            mutate_count_rise,
        ),
        # Kept LAST: it is the only scenario that could rewrite the baseline the five
        # above depend on, and the assertion is precisely that it does not.
        Scenario(
            "--write on a broken tree",
            "regeneration raises a number; it must never launder a broken one",
            False,
            "--write REFUSED",
            mutate_uncovered,
            flags=("--write",),
            baseline_must_not_change=True,
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="check_reuse_selftest_") as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        home = tmp_path / "home"
        repo.mkdir()
        home.mkdir()
        baseline = tmp_path / "baseline.json"

        env = dict(os.environ)
        env.update(
            {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "GIT_CONFIG_GLOBAL": str(home / "gitconfig-absent"),
                "GIT_CONFIG_SYSTEM": str(home / "gitconfig-absent"),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )

        pristine = _build_fixture(repo)
        _git(repo, env, "init", "-q")
        _git(repo, env, "add", "-A")

        def invoke(*flags: str) -> tuple[int, str]:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(checker),
                    "--repo-root",
                    str(repo),
                    "--baseline",
                    str(baseline),
                    *flags,
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            return proc.returncode, proc.stdout + proc.stderr

        code, out = invoke("--write")
        if code != 0:
            print("--self-test ABORTED: could not take a baseline on the clean fixture")
            print(out)
            return 2

        results: list[tuple[Scenario, int, bool]] = []
        for scenario in scenarios:
            added_before = set(_walk(repo))
            baseline_before = baseline.read_bytes()
            scenario.mutate(repo)  # type: ignore[operator]
            _git(repo, env, "add", "-A")
            code, out = invoke(*scenario.flags)
            ok_shape = (code == 0) if scenario.expect_ok else (code != 0)
            passed = ok_shape and (scenario.expect_token in out)
            if scenario.baseline_must_not_change and baseline.read_bytes() != baseline_before:
                passed = False
                out += "\nthe baseline WAS rewritten, which is the whole thing this forbids\n"
            results.append((scenario, code, passed))
            if verbose and not passed:
                print(f"--- output for failing scenario {scenario.name!r} ---")
                print(out)
            # revert
            for path in set(_walk(repo)) - added_before:
                (repo / path).unlink()
            _write(repo, "REUSE.toml", pristine["reuse_toml"])
            _git(repo, env, "add", "-A")

    width = max(len(s.name) for s in scenarios)
    print("--self-test — one synthetic repository, one planted violation per family")
    print(f"{'scenario':<{width}}  {'expect':>7} {'exit':>5}  result   why it is here")
    print("-" * (width + 60))
    failed = 0
    for scenario, code, passed in results:
        expect = "pass" if scenario.expect_ok else "REFUSE"
        verdict = "ok" if passed else "FAILED"
        if not passed:
            failed += 1
        print(f"{scenario.name:<{width}}  {expect:>7} {code:>5}  {verdict:<8} {scenario.why}")
    print("-" * (width + 60))
    if failed:
        print(f"{failed} of {len(results)} scenarios did not behave as declared.")
        return 1
    refusals = sum(1 for s in scenarios if not s.expect_ok)
    print(
        f"{len(results)} of {len(results)} scenarios behaved as declared: the checker passes "
        f"a complete tree and refuses each of the {refusals} planted violations."
    )
    return 0


def _walk(repo: Path) -> list[str]:
    out: list[str] = []
    for path in repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            out.append(path.relative_to(repo).as_posix())
    return sorted(out)


# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_reuse.py",
        description=(
            "Every tracked file names a licence; every licence has a text; every count is "
            "a ratchet that may fall and may not rise."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: two levels above this script)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="ratchet baseline (default: <repo-root>/qa/reuse-ratchet.json)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate the baseline from the measured tree — the only way a number rises",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="prove the checker is capable of refusing, on a synthetic tree",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    if args.self_test:
        try:
            return _self_test()
        except ToolingError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    repo_root: Path = args.repo_root.resolve()
    baseline: Path = (
        args.baseline if args.baseline is not None else repo_root / "qa" / "reuse-ratchet.json"
    )
    try:
        return run(repo_root, baseline, write=args.write, as_json=args.json)
    except ToolingError as exc:
        print(f"REFUSED [TOOLING] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
