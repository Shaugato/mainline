#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The registry guard: no workspace distribution may be unlinted, and none may be stale.

`.importlinter`'s own preamble has always promised this mechanism:

    A new package is registered by CI refusing the build, not by anyone remembering.

It was a promise about a script that did not exist. On 2026-08-10 the configuration
declared **five** `root_packages` against **twenty-seven** distributions on disk; the
other twenty-two were linted by nothing, and the job that was supposed to say so either
was not running or was not working. This file is the mechanism, extracted from the inline
heredoc in `ci.yml` so that it can be run on a laptop, unit-tested, and — the part that
matters — *seen failing* before it is trusted.

THREE FAILURE CLASSES, and each is a different mistake:

1. **UNREGISTERED** — a distribution exists on disk and appears in neither
   `root_packages` (which checks what it imports) nor any contract's `forbidden_modules`
   (which checks who imports it). Nobody is told, and nothing is checked. This is the
   hole the promise was about.

2. **STALE ROOT** — `root_packages` names a module with no distribution on disk.
   Measured: import-linter fails the entire run with
   `Could not find package 'x' in your Python path`, so ONE stale name takes out all
   seven contracts. This check finds it in milliseconds without building an import graph
   and without needing the workspace installed.

3. **UNROOTED SOURCE** — a contract names a `source_modules` entry that is not a root
   package. Import-linter cannot assert over a module outside its graph, so the contract
   silently asserts less than it says, or fails outright. This is the exact shape of the
   trap `.importlinter` used to describe in prose: "`trappoint_verify` joins
   `source_modules` in the same commit that creates it".

WHAT THIS DELIBERATELY DOES NOT DO. It does not import anything and it does not build an
import graph — `lint-imports` does both, slowly and correctly. This runs first because a
cheap check that names the problem beats an expensive one that says
`Could not find package`.
"""

from __future__ import annotations

import argparse
import configparser
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_SECTION = "importlinter"
CONTRACT_PREFIX = "importlinter:contract:"

# The uv workspace members, from the root `pyproject.toml`'s `[tool.uv.workspace]`
# globs. Kept as literals rather than parsed out of that file because this script must
# work on a checkout where no TOML has been read and nothing has been installed, and
# because a divergence between these two lists is itself worth a red build.
DISTRIBUTION_GLOBS = ("packages/*/pyproject.toml", "verticals/*/packages/*/pyproject.toml")

SKIPPED_SRC_ENTRIES = frozenset({"__pycache__"})


def is_module_directory(name: str) -> bool:
    """True when a directory under `src/` could be an importable top-level module.

    Not cosmetic filtering. `packages/trappoint-recall/src/.mypy_cache/` exists on this
    machine (untracked: `git ls-files` returns nothing for it), and the inline registry
    script in `ci.yml` counted every directory under `src/`, so it would have reported
    `.mypy_cache` as an unregistered distribution and refused the build. A name that is
    not a Python identifier cannot be imported and cannot be a root package, so it is not
    a distribution; a dot-prefixed tool cache is the common case.
    """
    return name not in SKIPPED_SRC_ENTRIES and name.isidentifier()


@dataclass(frozen=True)
class Distribution:
    """One importable top-level module belonging to one workspace distribution."""

    module: str
    project: str

    def __str__(self) -> str:
        return f"{self.module}  ({self.project})"


@dataclass
class Registry:
    """What `.importlinter` declares."""

    root_packages: set[str] = field(default_factory=set)
    forbidden_modules: set[str] = field(default_factory=set)
    source_modules: dict[str, set[str]] = field(default_factory=dict)
    contracts: list[str] = field(default_factory=list)

    @property
    def declared(self) -> set[str]:
        """Every module the configuration mentions in a checkable position."""
        return self.root_packages | self.forbidden_modules


@dataclass
class Report:
    """The verdict, and enough detail to act on it without opening the config."""

    unregistered: list[Distribution] = field(default_factory=list)
    stale_roots: list[str] = field(default_factory=list)
    unrooted_sources: list[tuple[str, str]] = field(default_factory=list)
    distributions: int = 0
    contracts: list[str] = field(default_factory=list)
    root_packages: int = 0

    @property
    def ok(self) -> bool:
        return not (self.unregistered or self.stale_roots or self.unrooted_sources)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "distributions": self.distributions,
            "root_packages": self.root_packages,
            "contracts": self.contracts,
            "unregistered": [{"module": d.module, "project": d.project} for d in self.unregistered],
            "stale_roots": self.stale_roots,
            "unrooted_sources": [
                {"contract": contract, "module": module}
                for contract, module in self.unrooted_sources
            ],
        }


def _names(raw: str) -> set[str]:
    return {line.strip() for line in raw.splitlines() if line.strip()}


def read_registry(config_path: Path) -> Registry:
    """Parse `.importlinter` into the three lists this guard cares about.

    `configparser` rather than a regex over indented lines: the previous inline
    implementation matched `^\\s{4}([a-z_][a-z0-9_]*)\\s*$`, which is indistinguishable
    from a four-space-indented word anywhere in the file and misses a name indented by
    two spaces or eight.
    """
    parser = configparser.ConfigParser()
    parser.read_string(config_path.read_text(encoding="utf-8"), source=str(config_path))

    registry = Registry()
    if parser.has_option(CONFIG_SECTION, "root_packages"):
        registry.root_packages = _names(parser.get(CONFIG_SECTION, "root_packages"))
    if parser.has_option(CONFIG_SECTION, "root_package"):
        registry.root_packages |= _names(parser.get(CONFIG_SECTION, "root_package"))

    for section in parser.sections():
        if not section.startswith(CONTRACT_PREFIX):
            continue
        label = parser.get(section, "name", fallback=section[len(CONTRACT_PREFIX) :])
        registry.contracts.append(label)
        if parser.has_option(section, "forbidden_modules"):
            registry.forbidden_modules |= _names(parser.get(section, "forbidden_modules"))
        if parser.has_option(section, "source_modules"):
            registry.source_modules[label] = _names(parser.get(section, "source_modules"))
    return registry


def discover_distributions(repo_root: Path) -> list[Distribution]:
    """Every top-level module shipped by every workspace distribution, sorted.

    A directory under `src/` is a distribution's module. `mainline-corpus` has source but
    no `pyproject.toml`, so it is not an installable distribution and is not discovered
    here — the same rule the `import-linter-registry` job used, kept deliberately, so the
    two never disagree about what a distribution is.
    """
    found: list[Distribution] = []
    for pattern in DISTRIBUTION_GLOBS:
        for pyproject in sorted(repo_root.glob(pattern)):
            src = pyproject.parent / "src"
            if not src.is_dir():
                continue
            project = pyproject.parent.relative_to(repo_root).as_posix()
            for entry in sorted(src.iterdir()):
                if entry.is_dir() and is_module_directory(entry.name):
                    found.append(Distribution(module=entry.name, project=project))
    return found


def check(repo_root: Path, config_path: Path) -> Report:
    """Run all three checks and return the report."""
    registry = read_registry(config_path)
    distributions = discover_distributions(repo_root)
    modules = {dist.module for dist in distributions}

    report = Report(
        distributions=len(distributions),
        contracts=list(registry.contracts),
        root_packages=len(registry.root_packages),
    )
    report.unregistered = [d for d in distributions if d.module not in registry.declared]
    report.stale_roots = sorted(registry.root_packages - modules)
    report.unrooted_sources = sorted(
        (contract, module)
        for contract, sources in registry.source_modules.items()
        for module in sources
        if module not in registry.root_packages
    )
    return report


def render(report: Report, config_path: Path) -> str:
    """Return the human-readable report. Every failure line names the fix."""
    lines: list[str] = []
    if report.unregistered:
        lines.append(f"these distributions appear in no {config_path.name} contract:")
        lines.extend(f"  {dist}" for dist in report.unregistered)
        lines.append(
            "  fix: add each to `root_packages` (to check what IT imports) or to a "
            "contract's `forbidden_modules` (to check who imports IT)."
        )
    if report.stale_roots:
        lines.append("these `root_packages` name no distribution on disk:")
        lines.extend(f"  {name}" for name in report.stale_roots)
        lines.append(
            "  fix: remove them. import-linter fails the WHOLE run with "
            "`Could not find package '<name>' in your Python path`, so one stale name "
            "takes out every contract."
        )
    if report.unrooted_sources:
        lines.append("these contract `source_modules` are not root packages:")
        lines.extend(
            f"  {module}  (contract: {contract})" for contract, module in report.unrooted_sources
        )
        lines.append(
            "  fix: add each to `root_packages`. A contract cannot assert over a module "
            "that is not in the graph."
        )
    if report.ok:
        lines.append(
            f"every workspace distribution is accounted for: {report.distributions} "
            f"distributions, {report.root_packages} root packages, "
            f"{len(report.contracts)} contracts."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the guard. 0 when the registry is complete, 1 when it is not."""
    parser = argparse.ArgumentParser(
        prog="check_import_registry",
        description=(
            "Refuse a build in which a workspace distribution is linted by no "
            "import-linter contract."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: two levels above this script)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to .importlinter (default: <repo-root>/.importlinter)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    config_path: Path = args.config if args.config is not None else repo_root / ".importlinter"
    if not config_path.is_file():
        print(f"no import-linter configuration at {config_path}", file=sys.stderr)
        return 2

    report = check(repo_root, config_path)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render(report, config_path))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
