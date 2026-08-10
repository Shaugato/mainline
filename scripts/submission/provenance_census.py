#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""PROVENANCE CENSUS: what this repository is made of, and when it was made.

Hackathon rule 7 asks two questions and accepts prose for both.  Prose is exactly
what this repository refuses to accept from itself, so this program answers them
mechanically instead:

  1. **Was the project created inside the submission window?**  Answered by walking
     every commit in ``git log`` and comparing its author *and* committer instants
     against a declared window.  The program **exits non-zero** if a single commit
     falls outside it.  A disclosure that says "created in the window" and a checker
     that would go red if it were false are different kinds of sentence, and only
     the second one is worth reading.

  2. **What pre-existing material is here that we did not write?**  Answered by a
     dependency census taken from every tracked ``pyproject.toml`` and every tracked
     ``package.json``, a scan for vendored trees, and a scan for foreign licence
     files.  ``docs/submission/DISCLOSURE.md`` is written against this output;
     neither document restates a number the other one measured.

Design commitments, in the style the repository already holds itself to.

* **Standard library only, and no network.**  No ``urllib``, no ``socket``, no
  third-party import anywhere in this file.  The only subprocess is ``git``.  An
  auditor can read this file top-to-bottom and know it phoned nobody.

* **The output is deterministic, and deliberately carries no clock.**  There is no
  ``generated_at`` field.  A wall-clock stamp would make the artefact differ from
  itself on every run, which would make ``--check`` — the mode that proves the
  committed JSON is the JSON this program produces — impossible.  The anchor is
  ``head``: the commit the census was taken at.  When HEAD moves, regenerate.

* **Licences are a declared table, audited against the machine — not read from it.**
  Reading ``importlib.metadata`` at generation time would make the artefact depend on
  whichever virtualenv happened to be active, and a fresh clone has no
  ``node_modules`` at all.  So the licence of each third-party distribution is a
  constant in this file, each entry carrying the exact metadata string it was read
  from and the version it was read at.  ``--check-licences`` re-reads the machine and
  **exits non-zero when the table and the installed distribution disagree**, so the
  table cannot rot silently.  A distribution that is not installed is reported
  ``SKIPPED``, never guessed.

* **First-party is computed, not asserted.**  The set of workspace distributions comes
  from the ``project.name`` of every tracked ``pyproject.toml``.  A requirement naming
  one of those is ours; everything else is somebody else's.

Usage::

    python scripts/submission/provenance_census.py
    python scripts/submission/provenance_census.py --window-start 2026-08-05 --window-end 2026-08-18
    python scripts/submission/provenance_census.py --check           # committed == generated
    python scripts/submission/provenance_census.py --check-licences  # table == installed
    python scripts/submission/provenance_census.py --self-test

Exit status
-----------
``0``  every commit inside the window, and whichever check was asked for passed.
``1``  a commit falls outside the window, or ``--check`` / ``--check-licences`` found
       a divergence, or the ``research/`` tree is tracked when it must not be.
``2``  the program could not run at all (not a git repository, ``git`` absent).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

# ======================================================================================
# Declared constants
# ======================================================================================

SCHEMA_VERSION: Final[int] = 1
GENERATOR: Final[str] = "scripts/submission/provenance_census.py"
REPOSITORY: Final[str] = "github.com/Shaugato/mainline"

DEFAULT_WINDOW_START: Final[str] = "2026-08-05"
DEFAULT_WINDOW_END: Final[str] = "2026-08-18"
# The rules page states the deadline in EDT (UTC-04:00).  A calendar window declared in
# one timezone and evaluated in another is how an entry lands one hour outside a window
# it was inside, so the timezone is an explicit, overridable input rather than "local".
DEFAULT_WINDOW_TZ: Final[str] = "-04:00"

WINDOW_RULE: Final[str] = (
    "Hackathon rule 7: the project must be newly created within the submission window, "
    "and any pre-existing code must be disclosed. Both the author instant and the "
    "committer instant of every commit are tested."
)

# The tree that must never be tracked here. It is the design corpus; it lives in a
# separate repository and `.gitignore` line 1 keeps it out of this one.
FORBIDDEN_TREE: Final[str] = "research/"

# Directory basenames that mean "code somebody else wrote, copied in".
VENDOR_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "vendor",
        "vendors",
        "_vendor",
        "third_party",
        "third-party",
        "thirdparty",
        "3rdparty",
        "node_modules",
    }
)

# Basenames that mean "a licence text travelling with the code it licenses".
LICENCE_FILE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)([._-][A-Za-z0-9._+-]+)?$", re.IGNORECASE
)

# Licence files that are the project's own and therefore not "foreign".
OWN_LICENCE_PATHS: Final[frozenset[str]] = frozenset({"LICENSE", "NOTICE"})
OWN_LICENCE_PREFIXES: Final[tuple[str, ...]] = ("LICENSES/",)

# The de-branded staging tree prepared for somebody else's repository. Outbound, not
# inbound — but it is derivative-work-shaped and a disclosure that ignores it is short.
OUTBOUND_TREE: Final[str] = "skills/upstream/"
OUTBOUND_TARGET: Final[str] = "https://github.com/cockroachlabs/cockroachdb-skills"

# ======================================================================================
# The licence table
#
# Measured 2026-08-10 on this machine, at the versions recorded here:
#
#   Python  .venv/Scripts/python.exe -c "import importlib.metadata as md; ..."
#           reading core metadata `License-Expression`, then `License`, then the
#           `License ::` trove classifiers, in that order.
#   npm     verticals/mainline/apps/console/node_modules/<name>/package.json  ->  .license
#
# `spdx`     — the SPDX expression this project records for the distribution.
# `observed` — the exact string the machine printed. Where it is not an SPDX expression
#              (scipy ships its full BSD text in the field; jinja2 and pint ship none)
#              `source` says where the SPDX reading came from instead.
# `--check-licences` compares `observed` against the machine and fails on divergence.
# ======================================================================================


@dataclass(frozen=True)
class LicenceRecord:
    spdx: str
    observed: str
    version: str
    source: str
    note: str = ""


PYPI_LICENCES: Final[dict[str, LicenceRecord]] = {
    "anthropic": LicenceRecord("MIT", "MIT", "0.120.2", "core-metadata:License"),
    "boto3": LicenceRecord(
        "Apache-2.0", "Apache-2.0", "1.43.66", "core-metadata:License-Expression"
    ),
    "cryptography": LicenceRecord(
        "Apache-2.0 OR BSD-3-Clause",
        "Apache-2.0 OR BSD-3-Clause",
        "50.0.0",
        "core-metadata:License-Expression",
        note="dual-licensed; either limb is permissive",
    ),
    "hypothesis": LicenceRecord(
        "MPL-2.0",
        "MPL-2.0",
        "6.165.2",
        "core-metadata:License-Expression",
        note="weak copyleft, file-scoped; a development dependency, never imported by shipped code",
    ),
    "httpx": LicenceRecord(
        "BSD-3-Clause", "BSD-3-Clause", "0.28.1", "core-metadata:License-Expression"
    ),
    "import-linter": LicenceRecord(
        "BSD-2-Clause",
        "BSD 2-Clause License",
        "2.13",
        "core-metadata:License",
        note="free-text field",
    ),
    "jinja2": LicenceRecord(
        "BSD-3-Clause",
        "",
        "3.1.6",
        "trove-classifier:License :: OSI Approved :: BSD License",
        note="no License field in core metadata; SPDX read from the classifier",
    ),
    "mypy": LicenceRecord("MIT", "MIT", "2.3.0", "core-metadata:License-Expression"),
    "numpy": LicenceRecord(
        "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
        "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
        "2.5.1",
        "core-metadata:License-Expression",
        note="compound expression covering numpy's own vendored components",
    ),
    "pint": LicenceRecord(
        "BSD-3-Clause",
        "BSD",
        "0.25.3",
        "core-metadata:License + trove-classifier",
        note="free-text 'BSD'; classifier says OSI Approved :: BSD License",
    ),
    "psycopg": LicenceRecord(
        "LGPL-3.0-only",
        "LGPL-3.0-only",
        "3.3.4",
        "core-metadata:License-Expression",
        note="COPYLEFT. Imported unmodified as a library; no psycopg source is copied into, "
        "or redistributed by, any MAINLINE distribution.",
    ),
    "psycopg-binary": LicenceRecord(
        "LGPL-3.0-only",
        "LGPL-3.0-only",
        "3.3.4",
        "core-metadata:License-Expression",
        note="pulled in by the psycopg[binary] extra",
    ),
    "psycopg-pool": LicenceRecord(
        "LGPL-3.0-only",
        "LGPL-3.0-only",
        "3.3.1",
        "core-metadata:License-Expression",
        note="pulled in by the psycopg[pool] extra",
    ),
    "pydantic": LicenceRecord("MIT", "MIT", "2.13.4", "core-metadata:License-Expression"),
    "pytest": LicenceRecord("MIT", "MIT", "9.1.1", "core-metadata:License-Expression"),
    "pytest-timeout": LicenceRecord("MIT", "MIT", "2.4.0", "core-metadata:License"),
    "pyyaml": LicenceRecord("MIT", "MIT", "6.0.3", "core-metadata:License"),
    "rapidfuzz": LicenceRecord("MIT", "MIT", "3.14.5", "core-metadata:License-Expression"),
    "ruff": LicenceRecord("MIT", "MIT", "0.16.1", "core-metadata:License-Expression"),
    "scikit-learn": LicenceRecord(
        "BSD-3-Clause", "BSD-3-Clause", "1.9.0", "core-metadata:License-Expression"
    ),
    "scipy": LicenceRecord(
        "BSD-3-Clause",
        "Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Develope",
        "1.18.0",
        "trove-classifier:License :: OSI Approved :: BSD License",
        note="License field holds the full text; the observed string is its first 60 characters",
    ),
    "sentence-transformers": LicenceRecord(
        "UNVERIFIED",
        "",
        "",
        "not-installed",
        note="declared only by the mainline-recall-agent [local-embed] extra, which is not "
        "installed in this environment. Not measured here, so not claimed here.",
    ),
    "types-pyyaml": LicenceRecord(
        "Apache-2.0", "Apache-2.0", "6.0.12.20260724", "core-metadata:License-Expression"
    ),
}

NPM_LICENCES: Final[dict[str, LicenceRecord]] = {
    "@axe-core/playwright": LicenceRecord(
        "MPL-2.0",
        "MPL-2.0",
        "4.12.1",
        "node_modules:package.json#license",
        note="weak copyleft; accessibility test tooling, never bundled into dist/",
    ),
    "@eslint/js": LicenceRecord("MIT", "MIT", "9.39.5", "node_modules:package.json#license"),
    "@playwright/test": LicenceRecord(
        "Apache-2.0", "Apache-2.0", "1.62.1", "node_modules:package.json#license"
    ),
    "@react-three/drei": LicenceRecord("MIT", "MIT", "10.7.8", "node_modules:package.json#license"),
    "@react-three/fiber": LicenceRecord("MIT", "MIT", "9.7.0", "node_modules:package.json#license"),
    "@testing-library/dom": LicenceRecord(
        "MIT", "MIT", "10.4.1", "node_modules:package.json#license"
    ),
    "@testing-library/jest-dom": LicenceRecord(
        "MIT", "MIT", "6.10.0", "node_modules:package.json#license"
    ),
    "@testing-library/react": LicenceRecord(
        "MIT", "MIT", "16.3.2", "node_modules:package.json#license"
    ),
    "@testing-library/user-event": LicenceRecord(
        "MIT", "MIT", "14.6.3", "node_modules:package.json#license"
    ),
    "@types/node": LicenceRecord("MIT", "MIT", "24.13.3", "node_modules:package.json#license"),
    "@types/react": LicenceRecord("MIT", "MIT", "19.2.18", "node_modules:package.json#license"),
    "@types/react-dom": LicenceRecord("MIT", "MIT", "19.2.4", "node_modules:package.json#license"),
    "@types/three": LicenceRecord("MIT", "MIT", "0.185.4", "node_modules:package.json#license"),
    "@vitejs/plugin-react": LicenceRecord(
        "MIT", "MIT", "5.2.0", "node_modules:package.json#license"
    ),
    "@vitest/coverage-v8": LicenceRecord(
        "MIT", "MIT", "3.2.7", "node_modules:package.json#license"
    ),
    "eslint": LicenceRecord("MIT", "MIT", "9.39.5", "node_modules:package.json#license"),
    "eslint-plugin-react-hooks": LicenceRecord(
        "MIT", "MIT", "6.1.1", "node_modules:package.json#license"
    ),
    "eslint-plugin-react-refresh": LicenceRecord(
        "MIT", "MIT", "0.5.3", "node_modules:package.json#license"
    ),
    "globals": LicenceRecord("MIT", "MIT", "16.5.0", "node_modules:package.json#license"),
    "jsdom": LicenceRecord("MIT", "MIT", "27.4.0", "node_modules:package.json#license"),
    "motion": LicenceRecord("MIT", "MIT", "12.43.0", "node_modules:package.json#license"),
    "react": LicenceRecord("MIT", "MIT", "19.2.8", "node_modules:package.json#license"),
    "react-dom": LicenceRecord("MIT", "MIT", "19.2.8", "node_modules:package.json#license"),
    "three": LicenceRecord("MIT", "MIT", "0.185.1", "node_modules:package.json#license"),
    "typescript": LicenceRecord(
        "Apache-2.0", "Apache-2.0", "5.9.3", "node_modules:package.json#license"
    ),
    "typescript-eslint": LicenceRecord("MIT", "MIT", "8.66.0", "node_modules:package.json#license"),
    "vite": LicenceRecord("MIT", "MIT", "7.1.12", "node_modules:package.json#license"),
    "vitest": LicenceRecord("MIT", "MIT", "3.2.7", "node_modules:package.json#license"),
}

CONSOLE_NODE_MODULES: Final[str] = "verticals/mainline/apps/console/node_modules"

UNKNOWN_LICENCE: Final[LicenceRecord] = LicenceRecord(
    "UNKNOWN",
    "",
    "",
    "absent-from-table",
    note="not in the declared licence table; run --check-licences",
)


# ======================================================================================
# git
# ======================================================================================


class GitError(RuntimeError):
    """git was absent, or refused."""


def git(root: Path, *args: str) -> str:
    """Run git inside ``root`` and return stdout. No network flags are ever passed."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment failure
        raise GitError("git is not on PATH") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed [{proc.returncode}]: {proc.stderr.strip()}")
    return proc.stdout


def find_repo_root(start: Path) -> Path:
    out = git(start, "rev-parse", "--show-toplevel").strip()
    return Path(out).resolve()


# ======================================================================================
# 1 · The commit window
# ======================================================================================

# Field separator chosen because it cannot appear in a hash, an ISO instant, an email or
# a name, and because subjects are taken last so an embedded separator cannot shift a
# column.
_LOG_SEP: Final[str] = "\x1f"
_LOG_FORMAT: Final[str] = _LOG_SEP.join(
    ["%H", "%h", "%an", "%ae", "%aI", "%cn", "%ce", "%cI", "%s"]
)


@dataclass(frozen=True)
class Commit:
    index: int
    hash: str
    short: str
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str
    subject: str


def collect_commits(root: Path) -> list[Commit]:
    """Every commit reachable from HEAD, oldest first."""
    raw = git(root, "log", "--reverse", f"--format={_LOG_FORMAT}")
    commits: list[Commit] = []
    for i, line in enumerate(raw.splitlines()):
        if not line.strip():
            continue
        parts = line.split(_LOG_SEP)
        if len(parts) != 9:
            raise GitError(f"unparsable git log line at index {i}: {line!r}")
        commits.append(Commit(i, *parts))  # type: ignore[arg-type]
    return commits


def parse_window(start: str, end: str, tz: str) -> tuple[datetime, datetime, timezone]:
    """Turn two calendar dates plus a UTC offset into a half-open-at-neither-end interval.

    ``start`` opens at 00:00:00 of its day; ``end`` closes at the last representable
    microsecond of its day. Both in ``tz``, which the caller declares rather than
    inherits from the machine.
    """
    sign = 1 if tz[0] != "-" else -1
    hh, _, mm = tz.lstrip("+-").partition(":")
    offset = timezone(sign * timedelta(hours=int(hh), minutes=int(mm or 0)))
    s = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=offset)
    e = datetime.strptime(end, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59, microsecond=999999, tzinfo=offset
    )
    if e < s:
        raise ValueError(f"window end {end} precedes window start {start}")
    return s, e, offset


def commit_window_verdict(
    commits: list[Commit], start: datetime, end: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (rows, violations). A violation is either instant outside the interval."""
    rows: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for c in commits:
        a = datetime.fromisoformat(c.author_date)
        k = datetime.fromisoformat(c.committer_date)
        a_in = start <= a <= end
        k_in = start <= k <= end
        rows.append(
            {
                "index": c.index,
                "hash": c.hash,
                "short": c.short,
                "author_name": c.author_name,
                "author_email": c.author_email,
                "author_date": c.author_date,
                "author_date_utc": a.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "committer_name": c.committer_name,
                "committer_email": c.committer_email,
                "committer_date": c.committer_date,
                "subject": c.subject,
                "author_inside_window": a_in,
                "committer_inside_window": k_in,
            }
        )
        if not (a_in and k_in):
            violations.append(
                {
                    "hash": c.hash,
                    "short": c.short,
                    "subject": c.subject,
                    "author_date": c.author_date,
                    "committer_date": c.committer_date,
                    "author_inside_window": a_in,
                    "committer_inside_window": k_in,
                }
            )
    return rows, violations


def identity_census(commits: list[Commit]) -> dict[str, Any]:
    """Who authored and who committed, counted. Sorted by count then identity."""

    def tally(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
        counts: dict[tuple[str, str], int] = {}
        for p in pairs:
            counts[p] = counts.get(p, 0) + 1
        return [
            {"name": n, "email": e, "commits": c}
            for (n, e), c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    authors = tally([(c.author_name, c.author_email) for c in commits])
    committers = tally([(c.committer_name, c.committer_email) for c in commits])
    return {
        "authors": authors,
        "committers": committers,
        "distinct_authors": len(authors),
        "distinct_committers": len(committers),
        "author_equals_committer_on_every_commit": all(
            c.author_name == c.committer_name and c.author_email == c.committer_email
            for c in commits
        ),
        "command": "git log --format='%an|%ae|%cn|%ce'",
    }


# ======================================================================================
# 2 · The forbidden tree
# ======================================================================================


def tracked_under(root: Path, prefix: str) -> list[str]:
    out = git(root, "ls-files", "--", prefix)
    return [ln for ln in out.splitlines() if ln.strip()]


def gitignore_rule(root: Path, prefix: str) -> str:
    """The exact `.gitignore` line that excludes ``prefix``, or the empty string."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "-v", prefix],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:  # pragma: no cover
        return ""
    return (
        proc.stdout.strip().splitlines()[0] if proc.returncode == 0 and proc.stdout.strip() else ""
    )


# ======================================================================================
# 3 · The dependency census
# ======================================================================================

# PEP 508 is bigger than this, but a requirement string in this repository is
# `name[extras]specifier ; marker` and nothing more exotic. The parser below refuses
# rather than guesses when it meets something it does not recognise.
_REQ_RE: Final[re.Pattern[str]] = re.compile(
    r"""^\s*
        (?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)
        \s*
        (?:\[(?P<extras>[^\]]*)\])?
        \s*
        (?P<rest>.*)$
    """,
    re.VERBOSE,
)


def normalise_pypi(name: str) -> str:
    """PEP 503 normalisation: lowercase, runs of -_. collapsed to a single hyphen."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Requirement:
    raw: str
    name: str
    normalised: str
    extras: tuple[str, ...]
    specifier: str
    marker: str


def parse_requirement(raw: str) -> Requirement:
    m = _REQ_RE.match(raw)
    if not m:
        raise ValueError(f"unparsable requirement: {raw!r}")
    rest = m.group("rest").strip()
    spec, _, marker = rest.partition(";")
    extras_raw = m.group("extras") or ""
    extras = tuple(sorted(e.strip() for e in extras_raw.split(",") if e.strip()))
    name = m.group("name")
    return Requirement(
        raw.strip(), name, normalise_pypi(name), extras, spec.strip(), marker.strip()
    )


@dataclass
class DepEntry:
    manifest: str
    distribution: str
    ecosystem: str
    kind: str  # runtime | optional | dev
    group: str  # "" | extra name | dependency-group name
    requirement: str
    name: str
    key: str
    party: str  # first | third
    licence: str
    licence_observed: str
    licence_version: str
    licence_source: str
    licence_note: str

    def as_json(self) -> dict[str, Any]:
        d = {
            "manifest": self.manifest,
            "distribution": self.distribution,
            "ecosystem": self.ecosystem,
            "kind": self.kind,
            "group": self.group,
            "requirement": self.requirement,
            "name": self.name,
            "party": self.party,
            "licence": self.licence,
            "licence_source": self.licence_source,
        }
        if self.licence_note:
            d["licence_note"] = self.licence_note
        return d


def licence_for(key: str, table: dict[str, LicenceRecord]) -> LicenceRecord:
    return table.get(key, UNKNOWN_LICENCE)


def python_manifests(root: Path) -> list[str]:
    return sorted(p for p in tracked_under(root, "*pyproject.toml") if "node_modules/" not in p)


def npm_manifests(root: Path) -> list[str]:
    return sorted(p for p in tracked_under(root, "*package.json") if "node_modules/" not in p)


def read_python_manifest(root: Path, rel: str) -> tuple[str | None, dict[str, Any]]:
    with (root / rel).open("rb") as fh:
        data = tomllib.load(fh)
    return (data.get("project", {}) or {}).get("name"), data


WORKSPACE_LICENCE: Final[LicenceRecord] = LicenceRecord(
    "workspace", "", "", "first-party", note="declared in this repository"
)


def _python_requirements(
    reqs: list[str],
    *,
    manifest: str,
    dist: str,
    kind: str,
    group: str,
    first_party: list[str],
) -> list[DepEntry]:
    """Expand one declaration list into census rows, extras included.

    A free function rather than a closure over the enclosing loop: a closure would
    capture ``manifest`` and ``dist`` by reference and produce rows attributed to
    whichever manifest happened to be last.
    """
    out: list[DepEntry] = []
    for raw in reqs:
        req = parse_requirement(raw)
        party = "first" if req.normalised in first_party else "third"
        rec = licence_for(req.normalised, PYPI_LICENCES) if party == "third" else WORKSPACE_LICENCE
        out.append(
            DepEntry(
                manifest=manifest,
                distribution=dist,
                ecosystem="pypi",
                kind=kind,
                group=group,
                requirement=req.raw,
                name=req.name,
                key=req.normalised,
                party=party,
                licence=rec.spdx,
                licence_observed=rec.observed,
                licence_version=rec.version,
                licence_source=rec.source,
                licence_note=rec.note,
            )
        )
        # An extra like psycopg[binary] resolves to a further distribution, with its
        # own licence. Naming only `psycopg` would under-count the closure by two.
        for extra in req.extras:
            sub = normalise_pypi(f"{req.name}-{extra}")
            if sub not in PYPI_LICENCES:
                continue
            r2 = PYPI_LICENCES[sub]
            out.append(
                DepEntry(
                    manifest=manifest,
                    distribution=dist,
                    ecosystem="pypi",
                    kind=kind,
                    group=group,
                    requirement=f"{req.raw}  (extra: {extra})",
                    name=sub,
                    key=sub,
                    party="third",
                    licence=r2.spdx,
                    licence_observed=r2.observed,
                    licence_version=r2.version,
                    licence_source=r2.source,
                    licence_note=r2.note,
                )
            )
    return out


def census_python(root: Path, manifests: list[str]) -> tuple[list[DepEntry], list[str]]:
    """Runtime / optional / dev requirements from every tracked pyproject.toml."""
    parsed: dict[str, tuple[str | None, dict[str, Any]]] = {}
    for rel in manifests:
        parsed[rel] = read_python_manifest(root, rel)
    first_party = sorted({normalise_pypi(n) for n, _ in parsed.values() if n})

    entries: list[DepEntry] = []
    for rel in manifests:
        dist_name, data = parsed[rel]
        dist = dist_name or "<virtual workspace root>"
        project = data.get("project", {}) or {}
        common = {"manifest": rel, "dist": dist, "first_party": first_party}

        entries += _python_requirements(
            list(project.get("dependencies", []) or []), kind="runtime", group="", **common
        )
        for extra, reqs in sorted((project.get("optional-dependencies", {}) or {}).items()):
            entries += _python_requirements(
                list(reqs or []), kind="optional", group=extra, **common
            )
        for grp, reqs in sorted((data.get("dependency-groups", {}) or {}).items()):
            entries += _python_requirements(
                [r for r in (reqs or []) if isinstance(r, str)], kind="dev", group=grp, **common
            )

    return entries, first_party


def census_npm(root: Path, manifests: list[str]) -> list[DepEntry]:
    entries: list[DepEntry] = []
    for rel in manifests:
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        dist = data.get("name") or "<unnamed>"
        for field_name, kind in (
            ("dependencies", "runtime"),
            ("devDependencies", "dev"),
            ("optionalDependencies", "optional"),
        ):
            for name, spec in sorted((data.get(field_name, {}) or {}).items()):
                rec = licence_for(name, NPM_LICENCES)
                entries.append(
                    DepEntry(
                        manifest=rel,
                        distribution=dist,
                        ecosystem="npm",
                        kind=kind,
                        group="",
                        requirement=f"{name}@{spec}",
                        name=name,
                        key=name,
                        party="third",
                        licence=rec.spdx,
                        licence_observed=rec.observed,
                        licence_version=rec.version,
                        licence_source=rec.source,
                        licence_note=rec.note,
                    )
                )
    return entries


# ======================================================================================
# 4 · Vendored code and foreign licence files
# ======================================================================================

_SPDX_COPYRIGHT_RE: Final[re.Pattern[str]] = re.compile(r"SPDX-FileCopyrightText:\s*(.+)")
_SPDX_LICENCE_RE: Final[re.Pattern[str]] = re.compile(r"SPDX-License-Identifier:\s*(\S+)")


def _spdx_of(root: Path, rel: str) -> tuple[str, str]:
    """(copyright, licence) read from the file's first 4 KiB or its `.license` sidecar."""
    for candidate in (root / f"{rel}.license", root / rel):
        try:
            head = candidate.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError:
            continue
        cop = _SPDX_COPYRIGHT_RE.search(head)
        lic = _SPDX_LICENCE_RE.search(head)
        if cop or lic:
            return (cop.group(1).strip() if cop else ""), (lic.group(1).strip() if lic else "")
    return "", ""


def vendor_scan(root: Path, tracked: list[str]) -> dict[str, Any]:
    """Tracked trees whose name says 'somebody else's code', plus foreign licence files.

    A hit is not a verdict. ``packages/trappoint-verify/.../vendor/`` is a *deliberate
    byte-identical copy of this repository's own canonicaliser*, kept so the verifier's
    one-dependency claim stays true; it is checked by
    ``scripts/custody/check_vendored_canon.py``. So each hit is classified by the SPDX
    copyright its files carry: our copyright means an internal copy, anything else means
    genuinely third-party code and the NOTICE file would be wrong.
    """
    dirs: dict[str, list[str]] = {}
    for rel in tracked:
        parts = rel.split("/")
        for i, seg in enumerate(parts[:-1]):
            if seg.lower() in VENDOR_DIR_NAMES:
                key = "/".join(parts[: i + 1]) + "/"
                dirs.setdefault(key, []).append(rel)
                break

    vendored: list[dict[str, Any]] = []
    for key in sorted(dirs):
        files = sorted(dirs[key])
        holders = sorted({_spdx_of(root, f)[0] for f in files} - {""})
        licences = sorted({_spdx_of(root, f)[1] for f in files} - {""})
        foreign = any("MAINLINE" not in h for h in holders) or not holders
        vendored.append(
            {
                "path": key,
                "file_count": len(files),
                "files": files,
                "copyright_holders": holders,
                "licences": licences,
                "classification": "third-party" if foreign else "internal-copy",
                "note": ""
                if foreign
                else (
                    "every file carries this project's own SPDX copyright, so this is a "
                    "copy of our code, not somebody else's"
                ),
            }
        )

    foreign_licence_files: list[dict[str, str]] = []
    own_licence_files: list[str] = []
    for rel in tracked:
        # Everything under `LICENSES/` is the project's own REUSE licence directory,
        # whatever the file is called — `Apache-2.0.txt` matches no LICENSE-shaped name.
        if rel.startswith(OWN_LICENCE_PREFIXES):
            own_licence_files.append(rel)
            continue
        base = rel.rsplit("/", 1)[-1]
        if not LICENCE_FILE_RE.match(base):
            continue
        if rel in OWN_LICENCE_PATHS:
            own_licence_files.append(rel)
            continue
        holder, lic = _spdx_of(root, rel)
        foreign_licence_files.append({"path": rel, "copyright": holder, "licence": lic})

    return {
        "vendor_directory_names_scanned": sorted(VENDOR_DIR_NAMES),
        "vendored_directories": vendored,
        "third_party_directory_count": sum(
            1 for v in vendored if v["classification"] == "third-party"
        ),
        "own_licence_files": sorted(own_licence_files),
        "foreign_licence_files": foreign_licence_files,
        "bundles_third_party_code": bool(foreign_licence_files)
        or any(v["classification"] == "third-party" for v in vendored),
        "command": "git ls-files | grep -E '(^|/)(vendor|third_party|_vendor|node_modules)(/|$)'",
    }


def outbound_scan(root: Path, tracked: list[str]) -> dict[str, Any]:
    """`skills/upstream/` — de-branded work prepared for another project's repository."""
    files = sorted(f for f in tracked if f.startswith(OUTBOUND_TREE))
    rows = []
    for f in files:
        if f.endswith(".license"):
            continue
        holder, lic = _spdx_of(root, f)
        rows.append(
            {
                "path": f,
                "licence": lic,
                "copyright": holder,
                "licence_carrier": "sidecar"
                if (root / f"{f}.license").exists()
                else "inline-header",
            }
        )
    return {
        "path": OUTBOUND_TREE,
        "direction": "outbound",
        "prepared_for": OUTBOUND_TARGET,
        "file_count": len(files),
        "files": rows,
        "meaning": (
            "Work authored here and shaped for another repository's layout. It is not "
            "pre-existing code taken in; it is a contribution not yet offered out. It "
            "carries no inbound licence obligation, and its outbound licence is whatever "
            "the receiving project's contribution terms turn out to require — a question "
            "that is open and is stated rather than assumed."
        ),
        "command": f"git ls-files {OUTBOUND_TREE}",
    }


# ======================================================================================
# Artefact assembly
# ======================================================================================


def build_commit_window(
    root: Path, window_start: str, window_end: str, window_tz: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    commits = collect_commits(root)
    if not commits:
        raise GitError("no commits reachable from HEAD")
    start, end, _ = parse_window(window_start, window_end, window_tz)
    rows, violations = commit_window_verdict(commits, start, end)
    head = git(root, "rev-parse", "HEAD").strip()
    research_files = tracked_under(root, FORBIDDEN_TREE)

    doc = {
        "artefact": "commit-window",
        "schema": SCHEMA_VERSION,
        "generator": GENERATOR,
        "repository": REPOSITORY,
        "determinism": (
            "no wall-clock field; the artefact is anchored to `head` and changes "
            "only when HEAD does"
        ),
        "window": {
            "start": window_start,
            "end": window_end,
            "timezone": window_tz,
            "start_instant": start.isoformat(),
            "end_instant": end.isoformat(),
            "rule": WINDOW_RULE,
        },
        "head": head,
        "commit_count": len(commits),
        "first_commit": rows[0],
        "last_commit": rows[-1],
        "all_commits_inside_window": not violations,
        "violations": violations,
        "identity_census": identity_census(commits),
        "commits": rows,
        "excluded_tree": {
            "path": FORBIDDEN_TREE,
            "tracked_file_count": len(research_files),
            "tracked_files": research_files,
            "gitignore_rule": gitignore_rule(root, FORBIDDEN_TREE),
            "command": f"git ls-files {FORBIDDEN_TREE} | wc -l",
            "expectation": (
                "0 — the design corpus lives in a separate repository and is never tracked here"
            ),
        },
        "commands": [
            "git log --reverse --format='%H|%an|%ae|%aI|%cn|%ce|%cI|%s'",
            "git rev-list --count HEAD",
            "git rev-parse HEAD",
            f"git ls-files {FORBIDDEN_TREE}",
        ],
    }
    return doc, violations


def build_third_party(root: Path) -> dict[str, Any]:
    tracked = [ln for ln in git(root, "ls-files").splitlines() if ln.strip()]
    py_manifests = python_manifests(root)
    js_manifests = npm_manifests(root)
    py_entries, first_party = census_python(root, py_manifests)
    js_entries = census_npm(root, js_manifests)
    entries = py_entries + js_entries

    third = [e for e in entries if e.party == "third"]

    def distinct(kinds: set[str], eco: str) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for e in third:
            if e.ecosystem != eco or e.kind not in kinds:
                continue
            row = seen.setdefault(
                e.key,
                {
                    "name": e.name,
                    "licence": e.licence,
                    "licence_source": e.licence_source,
                    "measured_version": e.licence_version,
                    "required_by": [],
                },
            )
            if e.licence_note and "licence_note" not in row:
                row["licence_note"] = e.licence_note
            ref = f"{e.distribution} [{e.kind}{':' + e.group if e.group else ''}]"
            if ref not in row["required_by"]:
                row["required_by"].append(ref)
        for row in seen.values():
            row["required_by"].sort()
        return [seen[k] for k in sorted(seen)]

    runtime_py = distinct({"runtime", "optional"}, "pypi")
    dev_py = distinct({"dev"}, "pypi")
    runtime_js = distinct({"runtime", "optional"}, "npm")
    dev_js = distinct({"dev"}, "npm")

    licence_counts: dict[str, int] = {}
    for group in (runtime_py, dev_py, runtime_js, dev_js):
        for row in group:
            licence_counts[row["licence"]] = licence_counts.get(row["licence"], 0) + 1

    vend = vendor_scan(root, tracked)

    return {
        "artefact": "third-party",
        "schema": SCHEMA_VERSION,
        "generator": GENERATOR,
        "repository": REPOSITORY,
        "head": git(root, "rev-parse", "HEAD").strip(),
        "determinism": (
            "licences come from the declared table in the generator, not from the machine; "
            "`--check-licences` re-reads the machine and fails on divergence"
        ),
        "tracked_file_count": len(tracked),
        "manifests": {
            "pyproject_toml": py_manifests,
            "pyproject_toml_count": len(py_manifests),
            "package_json": js_manifests,
            "package_json_count": len(js_manifests),
            "command": "git ls-files '*pyproject.toml' '*package.json'",
        },
        "first_party_distributions": first_party,
        "first_party_distribution_count": len(first_party),
        "declaration_count": {
            "total": len(entries),
            "first_party": len(entries) - len(third),
            "third_party": len(third),
        },
        "third_party": {
            "python_runtime": runtime_py,
            "python_development": dev_py,
            "npm_runtime": runtime_js,
            "npm_development": dev_js,
            "distinct_count": {
                "python_runtime": len(runtime_py),
                "python_development": len(dev_py),
                "npm_runtime": len(runtime_js),
                "npm_development": len(dev_js),
            },
        },
        "licence_summary": dict(sorted(licence_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "licence_summary_note": (
            "counted once per (bucket, package) across the four buckets above, so a package "
            "declared as both a runtime and a development dependency — hypothesis is — is "
            "counted twice. It is a census of declarations, not of distinct distributions."
        ),
        "copyleft_present": sorted(
            {
                row["name"]: row["licence"]
                for group in (runtime_py, dev_py, runtime_js, dev_js)
                for row in group
                if any(tag in row["licence"] for tag in ("GPL", "MPL", "EUPL", "CDDL"))
            }.items()
        ),
        "vendored_scan": vend,
        "outbound_contribution": outbound_scan(root, tracked),
        "notice_file_claim": {
            "path": "NOTICE",
            "text": "MAINLINE bundles no third-party code at this time.",
            "mechanically_supported": not vend["bundles_third_party_code"],
            "basis": (
                "No tracked directory holds code under a copyright other than this project's, "
                "and no foreign licence file is tracked. The claim is about *bundling* — copying "
                "somebody else's source into this tree — and it survives the scan. It says nothing "
                "about the dependency closure, which is what this artefact enumerates instead."
            ),
        },
    }


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_artefact(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(doc))


# ======================================================================================
# --check-licences
# ======================================================================================


def audit_licences(root: Path) -> tuple[list[str], list[str], list[str]]:
    """Compare the declared table against what is installed. (ok, skipped, mismatched)."""
    ok: list[str] = []
    skipped: list[str] = []
    bad: list[str] = []

    import importlib.metadata as md  # stdlib; imported here so the artefact path never touches it

    for key, rec in sorted(PYPI_LICENCES.items()):
        try:
            dist = md.distribution(key)
        except md.PackageNotFoundError:
            skipped.append(f"pypi:{key} — not installed in this environment")
            continue
        meta = dist.metadata
        observed = meta.get("License-Expression") or meta.get("License") or ""
        observed = observed[:60]
        if rec.observed and observed != rec.observed:
            bad.append(
                f"pypi:{key} — table says {rec.observed!r} at {rec.version}, "
                f"installed {dist.version} says {observed!r}"
            )
        elif not rec.observed and observed:
            bad.append(
                f"pypi:{key} — table records no License field, "
                f"installed {dist.version} has {observed!r}"
            )
        else:
            ok.append(f"pypi:{key} {dist.version}")

    nm = root / CONSOLE_NODE_MODULES
    if not nm.is_dir():
        skipped.append(f"npm:* — {CONSOLE_NODE_MODULES} is absent (pnpm install has not run here)")
    else:
        for name, rec in sorted(NPM_LICENCES.items()):
            pkg = nm / Path(name) / "package.json"
            if not pkg.is_file():
                skipped.append(f"npm:{name} — not installed")
                continue
            data = json.loads(pkg.read_text(encoding="utf-8"))
            observed = data.get("license") or ""
            if observed != rec.observed:
                bad.append(
                    f"npm:{name} — table says {rec.observed!r} at {rec.version}, "
                    f"installed {data.get('version')} says {observed!r}"
                )
            else:
                ok.append(f"npm:{name} {data.get('version')}")
    return ok, skipped, bad


# ======================================================================================
# --self-test
# ======================================================================================


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    e = dict(os.environ)
    if env:
        e.update(env)
    subprocess.run(cmd, cwd=str(cwd), env=e, check=True, capture_output=True, text=True)


class Checker:
    """Prints a PASS/FAIL line per assertion and remembers the failures."""

    def __init__(self) -> None:
        self.failures: list[str] = []

    def __call__(self, label: str, cond: object, detail: str = "") -> None:
        tail = f"  — {detail}" if detail and not cond else ""
        print(f"  {'PASS' if cond else 'FAIL'}  {label}{tail}")
        if not cond:
            self.failures.append(label)


def _st_requirements(check: Checker) -> None:
    print("self-test 1 — requirement parsing")
    cases = {
        "psycopg[binary,pool]>=3.3.4": ("psycopg", ("binary", "pool"), ">=3.3.4"),
        "trappoint-jcs": ("trappoint-jcs", (), ""),
        "pint>=0.24,<1.0": ("pint", (), ">=0.24,<1.0"),
        "mainline-agentkit[bedrock]": ("mainline-agentkit", ("bedrock",), ""),
        "types-PyYAML>=6.0": ("types-PyYAML", (), ">=6.0"),
    }
    for raw, (name, extras, spec) in cases.items():
        r = parse_requirement(raw)
        check(f"parse {raw!r}", (r.name, r.extras, r.specifier) == (name, extras, spec), f"got {r}")
    check("normalise types-PyYAML", normalise_pypi("types-PyYAML") == "types-pyyaml")
    check("normalise scikit_learn", normalise_pypi("scikit_learn") == "scikit-learn")
    try:
        parse_requirement("!!! not a requirement")
        check("refuses garbage requirement", False, "no exception raised")
    except ValueError:
        check("refuses garbage requirement", True)


def _st_window_on_real_git(check: Checker) -> None:
    print("self-test 2 — the window comparison, on a real git history")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "r"
        repo.mkdir()
        _run(["git", "init", "-q", "-b", "main"], repo)
        _run(["git", "config", "user.name", "Test Person"], repo)
        _run(["git", "config", "user.email", "test@example.invalid"], repo)
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _run(["git", "add", "-A"], repo)
        _run(
            ["git", "commit", "-q", "-m", "inside the window"],
            repo,
            {
                "GIT_AUTHOR_DATE": "2026-08-06T09:00:00+10:00",
                "GIT_COMMITTER_DATE": "2026-08-06T09:00:00+10:00",
            },
        )
        commits = collect_commits(repo)
        s, e, _ = parse_window("2026-08-05", "2026-08-18", "-04:00")
        _, viol = commit_window_verdict(commits, s, e)
        check("a commit inside the window produces no violation", viol == [], f"got {viol}")
        check("first commit hash is 40 hex", len(commits[0].hash) == 40)

        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _run(["git", "add", "-A"], repo)
        _run(
            ["git", "commit", "-q", "-m", "smuggled in from before the window"],
            repo,
            {
                "GIT_AUTHOR_DATE": "2026-07-01T09:00:00+10:00",
                "GIT_COMMITTER_DATE": "2026-07-01T09:00:00+10:00",
            },
        )
        commits = collect_commits(repo)
        _, viol = commit_window_verdict(commits, s, e)
        check("a commit before the window IS a violation", len(viol) == 1, f"got {viol}")
        check("the violation names the smuggled commit", viol and "smuggled" in viol[0]["subject"])

        # A rebased commit: authored before the window, committed inside it. The author
        # date is the one that gives the game away, which is why both are tested.
        (repo / "c.txt").write_text("c\n", encoding="utf-8")
        _run(["git", "add", "-A"], repo)
        _run(
            ["git", "commit", "-q", "-m", "rewritten history"],
            repo,
            {
                "GIT_AUTHOR_DATE": "2026-01-01T09:00:00+10:00",
                "GIT_COMMITTER_DATE": "2026-08-07T09:00:00+10:00",
            },
        )
        commits = collect_commits(repo)
        _, viol = commit_window_verdict(commits, s, e)
        rewritten = [v for v in viol if v["subject"] == "rewritten history"]
        check(
            "an old AUTHOR date with a fresh COMMITTER date is still a violation",
            len(rewritten) == 1
            and rewritten[0]["author_inside_window"] is False
            and rewritten[0]["committer_inside_window"] is True,
            f"got {rewritten}",
        )
        census = identity_census(commits)
        check(
            "identity census counts three commits by one author",
            census["authors"][0]["commits"] == 3,
        )
        check(
            "identity census sees author == committer",
            census["author_equals_committer_on_every_commit"] is True,
        )


def _st_window_parsing(check: Checker) -> None:
    print("self-test 3 — window parsing refuses a reversed interval")
    try:
        parse_window("2026-08-18", "2026-08-05", "-04:00")
        check("reversed window is refused", False, "no exception raised")
    except ValueError:
        check("reversed window is refused", True)
    s_utc, e_utc, _ = parse_window("2026-08-05", "2026-08-05", "+00:00")
    check("a one-day window spans that day", (e_utc - s_utc) < timedelta(days=1))


def _st_vendor_scan(check: Checker) -> None:
    print("self-test 4 — the vendored and foreign-licence scan")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "pkg/src/vendor").mkdir(parents=True)
        (root / "pkg/src/vendor/ours.py").write_text(
            "# SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "# SPDX-License-Identifier: Apache-2.0\n",
            encoding="utf-8",
        )
        (root / "libs/third_party/zlib").mkdir(parents=True)
        (root / "libs/third_party/zlib/LICENSE").write_text(
            "Copyright someone else\n", encoding="utf-8"
        )
        (root / "libs/third_party/zlib/z.c").write_text(
            "/* SPDX-FileCopyrightText: 1995 Jean-loup Gailly */\n", encoding="utf-8"
        )
        tracked = [
            "pkg/src/vendor/ours.py",
            "libs/third_party/zlib/LICENSE",
            "libs/third_party/zlib/z.c",
            "LICENSE",
            "NOTICE",
            "LICENSES/Apache-2.0.txt",
        ]
        (root / "LICENSE").write_text("x\n", encoding="utf-8")
        (root / "NOTICE").write_text("x\n", encoding="utf-8")
        (root / "LICENSES").mkdir()
        (root / "LICENSES/Apache-2.0.txt").write_text("x\n", encoding="utf-8")
        res = vendor_scan(root, tracked)
        paths = {v["path"]: v["classification"] for v in res["vendored_directories"]}
        check(
            "our own vendor/ copy is classified internal",
            paths.get("pkg/src/vendor/") == "internal-copy",
            str(paths),
        )
        check(
            "a foreign third_party/ tree is classified third-party",
            paths.get("libs/third_party/") == "third-party",
            str(paths),
        )
        check(
            "a foreign LICENSE file is reported",
            [f["path"] for f in res["foreign_licence_files"]] == ["libs/third_party/zlib/LICENSE"],
            str(res["foreign_licence_files"]),
        )
        check(
            "our own LICENSE/NOTICE/LICENSES are not reported as foreign",
            set(res["own_licence_files"]) == {"LICENSE", "NOTICE", "LICENSES/Apache-2.0.txt"},
        )
        check(
            "the planted tree makes bundles_third_party_code true",
            res["bundles_third_party_code"] is True,
        )

        clean = vendor_scan(root, ["LICENSE", "NOTICE", "pkg/src/vendor/ours.py"])
        check(
            "a clean tree makes bundles_third_party_code false",
            clean["bundles_third_party_code"] is False,
        )


def _st_dependency_census(check: Checker) -> None:
    print("self-test 5 — the dependency census, on a planted workspace")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "packages/alpha").mkdir(parents=True)
        (root / "packages/alpha/pyproject.toml").write_text(
            "[project]\nname = 'alpha'\ndependencies = ['psycopg[binary]>=3.3.4', 'beta']\n"
            "[project.optional-dependencies]\naws = ['boto3>=1.34']\n"
            "[dependency-groups]\ndev = ['pytest>=9.1']\n",
            encoding="utf-8",
        )
        (root / "packages/beta").mkdir(parents=True)
        (root / "packages/beta/pyproject.toml").write_text(
            "[project]\nname = 'beta'\ndependencies = []\n", encoding="utf-8"
        )
        (root / "app").mkdir()
        (root / "app/package.json").write_text(
            json.dumps(
                {
                    "name": "@x/app",
                    "dependencies": {"react": "19.2.8"},
                    "devDependencies": {"vite": "7.1.12"},
                }
            ),
            encoding="utf-8",
        )
        manifests = ["packages/alpha/pyproject.toml", "packages/beta/pyproject.toml"]
        entries, first_party = census_python(root, manifests)
        check(
            "first-party set is computed from project.name",
            first_party == ["alpha", "beta"],
            str(first_party),
        )
        by = {(e.name, e.kind, e.party) for e in entries}
        check(
            "a workspace sibling is first-party",
            ("beta", "runtime", "first") in by,
            str(sorted(by)),
        )
        check(
            "psycopg is third-party runtime", ("psycopg", "runtime", "third") in by, str(sorted(by))
        )
        check(
            "the [binary] extra expands to psycopg-binary",
            ("psycopg-binary", "runtime", "third") in by,
            str(sorted(by)),
        )
        check(
            "an optional extra is kind=optional",
            ("boto3", "optional", "third") in by,
            str(sorted(by)),
        )
        check("a dependency-group is kind=dev", ("pytest", "dev", "third") in by, str(sorted(by)))
        check(
            "psycopg carries its LGPL licence",
            any(e.name == "psycopg" and e.licence == "LGPL-3.0-only" for e in entries),
        )
        js = census_npm(root, ["app/package.json"])
        check(
            "npm runtime and dev are distinguished",
            {(e.name, e.kind) for e in js} == {("react", "runtime"), ("vite", "dev")},
        )
        check("an npm licence comes from the table", all(e.licence == "MIT" for e in js))


def _st_unknown_and_render(check: Checker) -> None:
    print("self-test 6 — an unknown distribution is reported, never guessed")
    check(
        "absent key yields UNKNOWN",
        licence_for("no-such-dist-anywhere", PYPI_LICENCES).spdx == "UNKNOWN",
    )

    print("self-test 7 — rendering is deterministic and LF-terminated")
    doc = {"b": 2, "a": [1, {"z": "é"}]}
    check("render is stable across calls", render(doc) == render(doc))
    check(
        "render ends in exactly one newline",
        render(doc).endswith("}\n") and not render(doc).endswith("\n\n"),
    )
    check("render keeps non-ASCII literal", "é" in render(doc))


def self_test() -> int:
    """Plant each failure this program exists to catch, and require it to fire."""
    check = Checker()
    for stage in (
        _st_requirements,
        _st_window_on_real_git,
        _st_window_parsing,
        _st_vendor_scan,
        _st_dependency_census,
        _st_unknown_and_render,
    ):
        stage(check)
    print()
    if check.failures:
        print(f"SELF-TEST FAILED — {len(check.failures)} check(s): {check.failures}")
        return 1
    print("SELF-TEST PASSED")
    return 0


# ======================================================================================
# main
# ======================================================================================


def _report(window: dict[str, Any], third: dict[str, Any]) -> None:
    w = window["window"]
    print("PROVENANCE CENSUS")
    print("=" * 78)
    print(f"repository        {window['repository']}")
    print(f"head              {window['head']}")
    print(f"commits           {window['commit_count']}")
    fc, lc = window["first_commit"], window["last_commit"]
    print(f"first commit      {fc['short']}  {fc['author_date']}  {fc['subject']}")
    print(f"last commit       {lc['short']}  {lc['author_date']}  {lc['subject']}")
    print(f"window            {w['start']} .. {w['end']} ({w['timezone']})")
    verdict = (
        "ALL INSIDE"
        if window["all_commits_inside_window"]
        else f"{len(window['violations'])} OUTSIDE"
    )
    print(f"window verdict    {verdict}")
    for v in window["violations"]:
        print(
            f"    OUTSIDE  {v['short']}  author={v['author_date']}  "
            f"committer={v['committer_date']}  {v['subject']}"
        )
    ic = window["identity_census"]
    print(f"authors           {ic['distinct_authors']} distinct")
    for a in ic["authors"]:
        print(f"    {a['commits']:>3}  {a['name']} <{a['email']}>")
    ex = window["excluded_tree"]
    print(
        f"{ex['path']:<18}{ex['tracked_file_count']} tracked file(s)   "
        f"[{ex['gitignore_rule'] or 'not ignored'}]"
    )
    print("-" * 78)
    m = third["manifests"]
    print(
        f"manifests         {m['pyproject_toml_count']} pyproject.toml, "
        f"{m['package_json_count']} package.json"
    )
    print(f"first-party dists {third['first_party_distribution_count']}")
    dc = third["third_party"]["distinct_count"]
    print(
        f"third-party       python runtime {dc['python_runtime']}, "
        f"python dev {dc['python_development']}, "
        f"npm runtime {dc['npm_runtime']}, npm dev {dc['npm_development']}"
    )
    print(f"licences          {third['licence_summary']}")
    if third["copyleft_present"]:
        print(f"copyleft          {third['copyleft_present']}")
    vs = third["vendored_scan"]
    for v in vs["vendored_directories"]:
        print(f"vendored          {v['path']}  {v['file_count']} file(s)  -> {v['classification']}")
    print(f"foreign licences  {len(vs['foreign_licence_files'])}")
    print(f"bundles 3rd-party {vs['bundles_third_party_code']}")
    ob = third["outbound_contribution"]
    print(f"outbound          {ob['path']}  {ob['file_count']} file(s) -> {ob['prepared_for']}")
    print("=" * 78)


def _run_licence_audit(root: Path) -> int:
    ok, skipped, bad = audit_licences(root)
    print("LICENCE TABLE AUDIT — declared table vs installed distributions")
    for line in bad:
        print(f"  MISMATCH  {line}")
    for line in skipped:
        print(f"  SKIPPED   {line}")
    print(f"  {len(ok)} verified, {len(skipped)} skipped, {len(bad)} mismatched")
    return 1 if bad else 0


def _drift_against_disk(root: Path, targets: dict[Path, dict[str, Any]]) -> list[str]:
    """Which committed artefacts differ from what this program would write now."""
    drift: list[str] = []
    for path, doc in targets.items():
        rel = path.relative_to(root).as_posix()
        want = render(doc)
        if not path.is_file():
            drift.append(f"{rel} — absent")
            continue
        have = path.read_text(encoding="utf-8")
        if have != want:
            drift.append(f"{rel} — differs ({len(have)} bytes on disk, {len(want)} generated)")
    return drift


def _refusals(args: argparse.Namespace, window_doc: dict[str, Any]) -> int:
    """Print every refusal this program is responsible for; return the exit code."""
    code = 0
    violations = window_doc["violations"]
    if violations:
        print(
            f"REFUSED: {len(violations)} commit(s) fall outside the declared submission "
            f"window {args.window_start}..{args.window_end} ({args.window_tz}).",
            file=sys.stderr,
        )
        code = 1
    tracked = window_doc["excluded_tree"]["tracked_file_count"]
    if tracked:
        print(
            f"REFUSED: {tracked} file(s) under {FORBIDDEN_TREE} are tracked; the design "
            f"corpus must not live in this repository.",
            file=sys.stderr,
        )
        code = 1
    return code


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="provenance_census",
        description=(
            "Prove the repository was created inside the submission window, "
            "and enumerate what it did not author."
        ),
    )
    ap.add_argument(
        "--repo", default=".", help="repository path (default: cwd, resolved to its git root)"
    )
    ap.add_argument(
        "--window-start",
        default=DEFAULT_WINDOW_START,
        help=f"inclusive, YYYY-MM-DD (default {DEFAULT_WINDOW_START})",
    )
    ap.add_argument(
        "--window-end",
        default=DEFAULT_WINDOW_END,
        help=f"inclusive, YYYY-MM-DD (default {DEFAULT_WINDOW_END})",
    )
    ap.add_argument(
        "--window-tz",
        default=DEFAULT_WINDOW_TZ,
        help=f"UTC offset the window is declared in (default {DEFAULT_WINDOW_TZ}, EDT)",
    )
    ap.add_argument(
        "--out-dir", default="evidence/provenance", help="where the two JSON artefacts are written"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if the committed JSON differs from the generated JSON",
    )
    ap.add_argument(
        "--check-licences",
        action="store_true",
        help="compare the declared licence table against installed distributions",
    )
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="plant each failure this program catches and require it to fire",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        root = find_repo_root(Path(args.repo).resolve())
    except GitError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.check_licences:
        return _run_licence_audit(root)

    try:
        window_doc, _ = build_commit_window(
            root, args.window_start, args.window_end, args.window_tz
        )
        third_doc = build_third_party(root)
    except (GitError, ValueError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    out = root / args.out_dir
    targets = {out / "commit-window.json": window_doc, out / "third-party.json": third_doc}

    if args.check:
        drift = _drift_against_disk(root, targets)
        _report(window_doc, third_doc)
        for d in drift:
            print(f"DRIFT  {d}")
        if drift:
            print("CHECK FAILED — regenerate with: python scripts/submission/provenance_census.py")
            return 1
        print("CHECK PASSED — the committed artefacts are what this program produces")
    else:
        for path, doc in targets.items():
            write_artefact(path, doc)
        _report(window_doc, third_doc)
        for path in targets:
            print(f"wrote  {path.relative_to(root).as_posix()}")
    return _refusals(args, window_doc)


if __name__ == "__main__":
    raise SystemExit(main())
