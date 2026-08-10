#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Derive the mypy target list from the workspace on disk — and refuse when the
config has fallen behind it.

    mypy --config-file mypy.ini $(python scripts/qa/mypy_targets.py)
    python scripts/qa/mypy_targets.py --check     # CI gate: exit 1 on a gap
    python scripts/qa/mypy_targets.py --json      # machine-readable inventory
    python scripts/qa/mypy_targets.py --list      # one target per line

Why this file exists
--------------------
On 2026-08-10 the repository held twenty-seven distributions and ``mypy.ini``
held five ``mypy_path`` entries.  Two different mypy invocations were in use,
each of them printing ``unused section(s): …`` for the modules the other one
covered.  Between them they checked most of the code — but *no single run*
checked the substrate, so "the types are fine" was a claim assembled from two
partial measurements rather than something anyone had observed.  Worse, the
twenty-eighth distribution would have joined the tree with no section, no path
entry, and nothing anywhere that noticed.

Deriving the list from the filesystem removes the possibility.  A distribution
is whatever has a ``pyproject.toml`` with a ``[tool.hatch.build.targets.wheel]``
``packages`` entry: exactly what ships in the wheel is exactly what gets type
checked.  ``--check`` then closes the loop in the other direction, and it is the
half that matters, because a target list that silently shrinks is worse than no
target list at all.

``--check`` refuses on four conditions, each of them a way coverage rots:

1. **unregistered** — a distribution on disk with no ``[mypy-<module>.*]``
   section.  Without a section the module is checked at whatever the global
   ``[mypy]`` block happens to say, and its tier is an accident.
2. **unpathed** — a distribution whose ``src`` root is absent from ``mypy_path``.
   With ``explicit_package_bases`` set, a missing path entry means mypy cannot
   derive the module name; the section exists and covers nothing.
3. **lax substrate** — a ``trappoint_*`` distribution not at the strict tier.
   ``packages/trappoint-*`` is the Apache substrate a stranger forks; a fork's
   only protection against a wrong refusal is that the code says what it means.
4. **ambiguous tier** — a section that sets some strictness flags and not
   others.  Tiers are policy.  A half-set tier is a policy nobody decided.

Sections that name a module with no distribution on disk are reported, not
refused: this wave deliberately forward-declares ``trappoint_testkit`` (W2) and
``mainline_gate_svc`` (W6) so that neither can land unchecked.  mypy reports a
forward-declared section as ``unused section(s)`` until the package appears.
That note is expected, it is named in the ``--check`` output, and it is the only
one this configuration may print.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The six flags that separate the tiers. `--strict` is a command-line flag with
# no per-module spelling, so a tier is written out flag by flag; these are the
# `--strict` members that are NOT already set globally in `[mypy]`.
TIER_FLAGS: tuple[str, ...] = (
    "disallow_untyped_defs",
    "disallow_incomplete_defs",
    "disallow_untyped_calls",
    "disallow_untyped_decorators",
    "disallow_any_generics",
    "disallow_subclassing_any",
)

# Directories that never contain a workspace distribution. `out_*` are rendered
# reference trees: they carry their own `pyproject.toml` files and are outputs,
# not members.
PRUNED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".eggs",
        "__pycache__",
        "node_modules",
        "site-packages",
        "build",
        "dist",
        "htmlcov",
    }
)
PRUNED_DIR_PREFIXES: tuple[str, ...] = ("out_", ".")

SUBSTRATE_PREFIX = "trappoint_"


@dataclass(frozen=True)
class Distribution:
    """One workspace distribution, as the filesystem describes it."""

    name: str
    directory: str
    module: str
    package: str
    src_root: str
    exists: bool = True

    @property
    def section(self) -> str:
        return f"mypy-{self.module}.*"

    @property
    def is_substrate(self) -> bool:
        return self.module.startswith(SUBSTRATE_PREFIX)


@dataclass
class Policy:
    """What ``mypy.ini`` currently says."""

    path: Path
    mypy_path: list[str] = field(default_factory=list)
    tiers: dict[str, str] = field(default_factory=dict)  # section name -> tier
    module_sections: dict[str, str] = field(default_factory=dict)  # module -> section


def _prune(names: list[str]) -> list[str]:
    return [n for n in names if n not in PRUNED_DIR_NAMES and not n.startswith(PRUNED_DIR_PREFIXES)]


def discover_distributions(root: Path) -> list[Distribution]:
    """Walk ``root`` for ``pyproject.toml`` and read the wheel's package list.

    The wheel target is the authority on purpose.  A distribution's type-checked
    surface should be the surface it publishes; anything else lets a module ship
    to a stranger without having been checked in the tree that built it.
    """
    found: list[Distribution] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = _prune(dirnames)
        if "pyproject.toml" not in filenames:
            continue
        dist_dir = Path(dirpath)
        with (dist_dir / "pyproject.toml").open("rb") as handle:
            try:
                data = tomllib.load(handle)
            except tomllib.TOMLDecodeError as exc:  # pragma: no cover - malformed tree
                raise SystemExit(f"{dist_dir / 'pyproject.toml'}: {exc}") from exc
        wheel = (
            data.get("tool", {})
            .get("hatch", {})
            .get("build", {})
            .get("targets", {})
            .get("wheel", {})
        )
        packages = wheel.get("packages")
        if not packages:
            # The workspace root is a *virtual* workspace with no `[project]`
            # table and nothing to build. Absence here is correct, not a gap.
            continue
        name = str(data.get("project", {}).get("name", dist_dir.name))
        for entry in packages:
            package_dir = (dist_dir / str(entry)).resolve()
            found.append(
                Distribution(
                    name=name,
                    directory=dist_dir.resolve().relative_to(root).as_posix(),
                    module=package_dir.name,
                    package=package_dir.relative_to(root).as_posix(),
                    src_root=package_dir.parent.relative_to(root).as_posix(),
                    exists=package_dir.is_dir(),
                )
            )
    return sorted(found, key=lambda d: d.package)


def discover_src_roots(root: Path) -> list[str]:
    """Every ``src`` directory in the workspace, distribution or not.

    ``verticals/mainline/packages/mainline-corpus`` has sixty modules and no
    ``pyproject.toml`` (W1 owns that repair).  It is not a target — nothing
    publishes it — but it must be on ``mypy_path`` so that an import of it from
    a package that *is* a target resolves to the source rather than to nothing.
    """
    roots: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = _prune(dirnames)
        here = Path(dirpath)
        if here.name != "src":
            continue
        # `verticals/*/apps/console/src` is TypeScript. A path entry for a tree
        # with no Python in it is noise a reader has to disprove.
        if next(here.rglob("*.py"), None) is None:
            continue
        roots.add(here.resolve().relative_to(root).as_posix())
    return sorted(roots)


def _split_path_value(raw: str) -> list[str]:
    entries: list[str] = []
    for line in raw.replace(os.pathsep, ",").splitlines():
        for chunk in line.split(","):
            cleaned = chunk.strip().replace("\\", "/").rstrip("/")
            if cleaned:
                entries.append(cleaned)
    return entries


def _classify(section: configparser.SectionProxy) -> str:
    values = {flag: section.get(flag) for flag in TIER_FLAGS if flag in section}
    if not values:
        return "unset"
    if len(values) != len(TIER_FLAGS):
        return "ambiguous"
    truths = {str(v).strip().lower() in {"true", "1", "yes", "on"} for v in values.values()}
    if truths == {True}:
        return "strict"
    if truths == {False}:
        return "normal"
    return "ambiguous"


def read_policy(config_path: Path) -> Policy:
    parser = configparser.ConfigParser()
    if not config_path.is_file():
        raise SystemExit(f"config not found: {config_path}")
    with config_path.open(encoding="utf-8") as handle:
        parser.read_file(handle)
    policy = Policy(path=config_path)
    if parser.has_section("mypy"):
        policy.mypy_path = _split_path_value(parser["mypy"].get("mypy_path", ""))
    for name in parser.sections():
        if name == "mypy" or not name.startswith("mypy-"):
            continue
        body = parser[name]
        if "ignore_missing_imports" in body and _classify(body) == "unset":
            continue  # a third-party admission, not a distribution tier
        target = name[len("mypy-") :]
        policy.tiers[name] = _classify(body)
        if target.endswith(".*"):
            module = target[: -len(".*")]
            if "*" not in module:
                policy.module_sections[module] = name
    return policy


@dataclass
class Report:
    """The result of comparing the filesystem against the config."""

    unregistered: list[str] = field(default_factory=list)
    unpathed: list[str] = field(default_factory=list)
    lax_substrate: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    unbuilt: list[str] = field(default_factory=list)

    @property
    def failures(self) -> list[str]:
        return self.unregistered + self.unpathed + self.lax_substrate + self.ambiguous


def evaluate(dists: list[Distribution], policy: Policy) -> Report:
    report = Report()
    declared_paths = set(policy.mypy_path)
    modules = {d.module for d in dists}
    for dist in dists:
        if not dist.exists:
            # A `pyproject.toml` naming a package directory that is not there yet.
            # It is not a coverage gap: the distribution IS registered, and there
            # is no source for the type checker to miss. `hatch build` is the gate
            # for an empty wheel; this one is about escaping mypy.
            report.unbuilt.append(
                f"{dist.directory}: wheel names '{dist.package}', which does not exist yet"
            )
        section = policy.module_sections.get(dist.module)
        if section is None:
            report.unregistered.append(
                f"{dist.directory}: no [mypy-{dist.module}.*] section in {policy.path.name}"
            )
            continue
        tier = policy.tiers.get(section, "unset")
        if dist.src_root not in declared_paths:
            report.unpathed.append(f"{dist.directory}: '{dist.src_root}' is not in mypy_path")
        if tier == "ambiguous":
            report.ambiguous.append(
                f"[{section}]: sets some tier flags and not others; a tier is all six or none"
            )
        elif tier == "unset":
            report.ambiguous.append(
                f"[{section}]: declares no tier; set the six tier flags "
                f"True (strict) or False (normal)"
            )
        elif dist.is_substrate and tier != "strict":
            report.lax_substrate.append(
                f"[{section}]: tier is '{tier}'; packages/trappoint-* is the "
                f"substrate and must be strict"
            )
    for module, section in sorted(policy.module_sections.items()):
        if module not in modules:
            report.pending.append(
                f"[{section}]: forward-declared; no distribution on disk yet "
                f"(mypy will call this section unused until it lands)"
            )
    return report


def tier_of(dist: Distribution, policy: Policy) -> str:
    section = policy.module_sections.get(dist.module)
    if section is None:
        return "unregistered"
    return policy.tiers.get(section, "unset")


def build_inventory(root: Path, dists: list[Distribution], policy: Policy) -> dict[str, object]:
    report = evaluate(dists, policy)
    return {
        "root": root.as_posix(),
        "config": policy.path.name,
        "distributions": [
            {
                "name": d.name,
                "module": d.module,
                "dir": d.directory,
                "package": d.package,
                "src_root": d.src_root,
                "section": f"[mypy-{d.module}.*]",
                "tier": tier_of(d, policy),
            }
            for d in dists
        ],
        "targets": [d.package for d in dists if d.exists],
        "src_roots": discover_src_roots(root),
        "pending_sections": report.pending,
        "failures": report.failures,
    }


RATCHET_RELPATH = "qa/mypy-ratchet.json"
_ERROR_LINE = re.compile(r"^(?P<path>.+?):\d+(?::\d+)?: error: ")
_CHECKED = re.compile(r"checked (\d+) source files?")
_UNUSED = re.compile(r"unused section\(s\): (?P<sections>.+)$")


def _module_of(path: str, dists: list[Distribution]) -> str | None:
    normalised = path.replace("\\", "/")
    for dist in dists:
        if normalised.startswith(dist.package + "/") or normalised == dist.package:
            return dist.module
        # mypy prints paths relative to the invocation directory, but an absolute
        # path from a different cwd must still land on the right distribution.
        if f"/{dist.package}/" in normalised:
            return dist.module
    return None


def run_mypy(
    root: Path, config_path: Path, dists: list[Distribution]
) -> tuple[dict[str, int], list[str], int, str]:
    """Run the one whole-workspace invocation and tally errors per distribution."""
    targets = [d.package for d in dists if d.exists]
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(config_path),
            "--no-pretty",
            *targets,
        ],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    output = proc.stdout + proc.stderr
    counts: dict[str, int] = {d.module: 0 for d in dists if d.exists}
    unattributed = 0
    unused: list[str] = []
    checked = 0
    for line in output.splitlines():
        match = _ERROR_LINE.match(line)
        if match:
            module = _module_of(match.group("path"), dists)
            if module is None:
                unattributed += 1
            else:
                counts[module] = counts.get(module, 0) + 1
            continue
        found = _UNUSED.search(line)
        if found:
            unused = [s.strip() for s in found.group("sections").split(",") if s.strip()]
        seen = _CHECKED.search(line)
        if seen:
            checked = int(seen.group(1))
    if unattributed:
        counts["<unattributed>"] = unattributed
    return counts, unused, checked, output


def mypy_version(root: Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--version"],
        capture_output=True,
        text=True,
        cwd=str(root),
        check=False,
    )
    return proc.stdout.strip() or proc.stderr.strip()


RATCHET_PREAMBLE = (
    "The honest per-distribution mypy count, taken by one whole-workspace run. "
    "A count may go DOWN. An increase fails `mypy_targets.py --ratchet`. "
    "Regenerate with `--write-ratchet` and say in the commit why a number moved."
)


def ratchet_entries(
    dists: list[Distribution], policy: Policy, counts: dict[str, int]
) -> dict[str, dict[str, object]]:
    """One entry per distribution: where it lives, its tier, its honest count.

    A distribution whose section is forward-declared, or whose source has not
    landed yet, is recorded with ``errors: null`` rather than ``0``. Zero is a
    measurement; null is the absence of one, and conflating them is how a
    ratchet starts certifying packages nobody checked.
    """
    entries: dict[str, dict[str, object]] = {}
    for dist in sorted(dists, key=lambda d: d.module):
        entries[dist.module] = {
            "dir": dist.directory,
            "tier": tier_of(dist, policy) if dist.exists else "pending",
            "errors": counts.get(dist.module, 0) if dist.exists else None,
        }
    on_disk = {d.module for d in dists}
    for module, section in sorted(policy.module_sections.items()):
        if module not in on_disk:
            entries[module] = {
                "dir": None,
                "tier": "pending",
                "errors": None,
                "note": f"[{section}] is forward-declared; no distribution on disk",
            }
    return entries


def build_ratchet(
    root: Path,
    entries: dict[str, dict[str, object]],
    counts: dict[str, int],
    checked: int,
    unused: list[str],
) -> dict[str, object]:
    return {
        # JSON carries no comment syntax, so the REUSE tags are keys. Without
        # them this file joins the 4 459 unlicensed `.json` in the census.
        "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
        "SPDX-License-Identifier": "Apache-2.0",
        "$comment": RATCHET_PREAMBLE,
        "command": "mypy --config-file mypy.ini $(python scripts/qa/mypy_targets.py)",
        "mypy_version": mypy_version(root),
        "mypy_version_floor": ">=1.11",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "source_files_checked": checked,
        "total_errors": sum(v for v in counts.values()),
        "unused_sections": unused,
        "distributions": entries,
    }


def ratchet_command(
    root: Path, config_path: Path, dists: list[Distribution], policy: Policy, *, write: bool
) -> int:
    counts, unused, checked, output = run_mypy(root, config_path, dists)
    entries = ratchet_entries(dists, policy, counts)
    fresh = build_ratchet(root, entries, counts, checked, unused)
    path = root / RATCHET_RELPATH
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(fresh, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {RATCHET_RELPATH}: {fresh['total_errors']} error(s) over {checked} files")
        return 0
    if not path.is_file():
        print(f"{RATCHET_RELPATH} does not exist; run --write-ratchet", file=sys.stderr)
        return 1
    recorded = json.loads(path.read_text(encoding="utf-8"))["distributions"]
    regressions: list[str] = []
    improvements: list[str] = []
    for module, entry in entries.items():
        now = entry["errors"]
        if not isinstance(now, int):
            continue
        if module not in recorded:
            regressions.append(f"{module}: not in {RATCHET_RELPATH}; run --write-ratchet")
            continue
        was = recorded[module]["errors"]
        if was is None:
            if now:
                regressions.append(f"{module}: {now} error(s); the ratchet had it as pending")
            continue
        if now > was:
            regressions.append(f"{module}: {was} -> {now}")
        elif now < was:
            improvements.append(f"{module}: {was} -> {now}")
    for line in improvements:
        print(f"IMPROVED {line}  (run --write-ratchet to bank it)")
    for line in regressions:
        print(f"REGRESSED {line}", file=sys.stderr)
    if regressions:
        sys.stderr.write(output)
        return 1
    print(f"OK: {fresh['total_errors']} error(s), none above the recorded count.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mypy_targets.py",
        description=(
            "Emit the mypy target list for the whole workspace, or refuse when a "
            "distribution on disk has no section in mypy.ini."
        ),
    )
    default_root = Path(__file__).resolve().parents[2]
    parser.add_argument("--root", default=str(default_root), help="workspace root")
    parser.add_argument("--config", default=None, help="mypy config (default: <root>/mypy.ini)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="refuse on a coverage gap")
    mode.add_argument("--json", action="store_true", help="emit the inventory as JSON")
    mode.add_argument("--list", action="store_true", help="one target per line")
    mode.add_argument(
        "--ratchet", action="store_true", help="run mypy and refuse a per-distribution increase"
    )
    mode.add_argument("--write-ratchet", action="store_true", help=f"regenerate {RATCHET_RELPATH}")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = Path(args.config).resolve() if args.config else root / "mypy.ini"
    dists = discover_distributions(root)
    policy = read_policy(config_path)

    if args.ratchet or args.write_ratchet:
        return ratchet_command(root, config_path, dists, policy, write=args.write_ratchet)

    if args.json:
        json.dump(build_inventory(root, dists, policy), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.check:
        report = evaluate(dists, policy)
        print(f"distributions on disk : {len(dists)}")
        print(f"sections in {config_path.name:<10}: {len(policy.module_sections)}")
        strict = sum(1 for d in dists if tier_of(d, policy) == "strict")
        print(f"strict / normal       : {strict} / {len(dists) - strict}")
        for note in report.pending:
            print(f"PENDING  {note}")
        for note in report.unbuilt:
            print(f"UNBUILT  {note}")
        for failure in report.failures:
            print(f"REFUSED  {failure}", file=sys.stderr)
        if report.failures:
            print(
                f"\n{len(report.failures)} coverage gap(s). "
                "Every distribution must carry a section and a mypy_path entry, "
                "or the type checker is not checking it.",
                file=sys.stderr,
            )
            return 1
        print("OK: every distribution on disk is registered, pathed and tiered.")
        return 0

    targets = [d.package for d in dists if d.exists]
    if args.list:
        print("\n".join(targets))
    else:
        print(" ".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
