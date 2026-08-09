#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Layer 1 of the injection posture, proved over the tree instead of asserted in a docstring.

ARCHITECTURE.md 8.4 layer 1: *document text never enters a turn belonging to a
tool-holding agent; the extraction call has zero tools and zero write credentials.*
``mainline_agentkit.call.quarantined_call`` has no ``tools`` parameter, which is the
compile-time half. This script is the other half: **no ingest-reachable package may
construct a tool surface at all**, in a dict literal, in a keyword argument, or inside a
JSON body written as a string.

A parameter that does not exist cannot be passed. A key that CI refuses to let anyone
write cannot be added by a well-meaning future edit either, and that is the difference
between a design and a control.

WHAT IS SCANNED
---------------
Every ``src`` tree under ``packages/*`` and ``verticals/*/packages/*`` is scanned by
**discovery**, so a new package is covered the day it lands rather than the day someone
remembers to add it here. Exclusions are a short, committed list with a reason each
(:data:`EXCLUDED_PACKAGES`) and are printed in every report: a package is excluded only
when holding tools is its declared purpose *and* it is not on the path from a document to
a model.

WHAT COUNTS AS A TOOL SURFACE
-----------------------------
``tools``, ``tool_choice``, ``toolConfig``, ``toolChoice``, ``tool_config``,
``mcp_servers`` and ``mcpServers`` appearing as

* a key of a dict literal,
* a keyword argument of any call,
* a subscript assignment target (``body["tools"] = ...``),
* a plain assignment to a name that *is* one of those words, or
* a key of a JSON object inside a string literal.

TWO EXCEPTIONS, BOTH NARROW, BOTH THE OPPOSITE OF A HOLE
--------------------------------------------------------
**Declared absence.** A literal empty value (``[]``, ``{}``, ``()``, ``None``) is not a
tool surface. ``mainline_agentkit.profiles.CallProfile.describe`` emits ``"tools": []``
precisely to say the profile holds none, and refusing that would push the statement out
of the code and into prose. An opaque non-empty value is a finding, because this script
cannot prove it empty and a control that guesses is not a control.

**Same-name derivation.** A value derived from something already called ``tools`` -
``self.tools``, ``list(self.tools)``, ``sorted(grant.tools)``, ``spec.get("tools")`` - is
a *read* of a declared tool list, not the construction of a new one. The motivating case
is not this script's own author's: ``mainline_recall_fleet.legs`` raises
``FleetContractViolation(..., tools=list(self.tools))`` when a recall leg declares a
tool, and ``mainline_quarantine.capability`` compares what a process holds against the
register. Both are code that *enforces* the no-tools property, and a scan that failed on
them would be a scan that punished the control for existing.

The limit is worth stating: an author who genuinely wanted to build a tool surface could
name a local ``tools`` and pass it along, and the derivation rule would let the
pass-along through. It would not let the **definition** through - the assignment rule
above catches ``tools = [{"name": ...}]`` - and the runtime guard
``mainline_agentkit.transport.assert_no_tool_surface`` refuses the built body regardless.
Three checks, none of which is sufficient alone.

EXEMPTIONS
----------
Exactly one file is exempt, by exact path, never by pattern:
``packages/mainline-agentkit/src/mainline_agentkit/fallback_toolform.py``. It is AR-1's
pre-committed format fallback - forced single-turn tool use if ``output_config`` is ever
rejected on an ``au.*`` profile - and its own docstring specifies this exemption and the
marker string that must be present. Three things are checked about it, and any of them
failing is a finding:

* the file exists (a stale exemption is dead config, and dead config in a security scan
  is worse than no scan because it looks like coverage);
* it carries its marker;
* **nothing imports it.** A fallback that is never imported cannot become the default by
  accident, which is the whole basis on which the exemption was granted.

USAGE
-----
::

    python scripts/agents/assert_no_tool_construction.py            # scan the repo
    python scripts/agents/assert_no_tool_construction.py --json     # machine-readable
    python scripts/agents/assert_no_tool_construction.py --root DIR # scan one tree

Exit status is ``0`` when clean and ``1`` when any finding exists. ``--root`` scans an
explicit directory with no discovery and no exclusions, which is how
``tests/security/injection/test_layers.py`` points it at a fixture that deliberately
constructs a tool surface and asserts this script fails on it (PL-2: a scanner that has
never been red asserts nothing).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

BANNED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "tools",
        "tool_choice",
        "toolConfig",
        "toolChoice",
        "tool_config",
        "mcp_servers",
        "mcpServers",
    }
)

#: Package directory names that are NOT scanned, each with the reason. Holding a tool is
#: the declared purpose of both, and neither is on the path from an untrusted document to
#: a model call: they are Control-plane clients that talk to CockroachDB's own MCP
#: endpoint and to ours. If either ever grows an ingest path, it comes off this list.
EXCLUDED_PACKAGES: Final[dict[str, str]] = {
    "mainline-mcp": (
        "the Managed-MCP client. Its whole job is to enumerate and call the cluster's "
        "read tools; it never sees a customer document (ARCHITECTURE.md 9.1)."
    ),
    "trappoint-mcp": (
        "our own MCP server. It DEFINES four tools; a server that constructs no tool "
        "surface would serve nothing (decision A15)."
    ),
    "mainline-boundary": (
        "the determinism-boundary checker. It parses spec/agents/fleet.yaml, whose "
        "schema has a `tools` field, and holds no model call and no document path."
    ),
}

#: Exact repo-relative path -> (reason, required marker string).
_AR1_REASON: Final[str] = (
    "AR-1's pre-committed format fallback: forced single-turn tool use if "
    "output_config is rejected on an au.* profile ARN. tool_choice is forced, the "
    "tool has no implementation, no result is returned, and the loop terminates at "
    "one turn - so it is a format fallback, not a capability fallback. Exempt only "
    "while nothing imports it."
)

FILE_EXEMPTIONS: Final[dict[str, tuple[str, str]]] = {
    "packages/mainline-agentkit/src/mainline_agentkit/fallback_toolform.py": (
        _AR1_REASON,
        "mainline-scan-exemption: ar1-toolform-fallback",
    ),
}


@dataclass(frozen=True, slots=True)
class Finding:
    """One place a tool surface was constructed, or one exemption that went stale."""

    path: str
    line: int
    column: int
    kind: str
    key: str
    detail: str


def is_declared_absence(node: ast.AST | None) -> bool:
    """Whether a value is a literal empty collection or ``None``.

    That is the one shape that means "this holds no tools" rather than "this holds
    tools". Anything computed is refused: proving a name is empty is not this script's
    job and guessing is how a control becomes a comment.
    """
    if node is None:
        return True
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    return False


def derives_from_key(node: ast.AST | None, key: str) -> bool:
    """Whether a value expression reads an existing thing already named ``key``.

    Accepts three shapes anywhere in the expression, and nothing else:

    * ``tools`` as a bare name (``ast.Name``);
    * ``.tools`` as an attribute (``ast.Attribute``);
    * ``["tools"]`` as a constant subscript, or ``"tools"`` as an argument to a ``.get``
      call - the two ways a mapping is read under the key.

    A bare string ``"tools"`` sitting inside a tool definition does **not** count, which
    is why the constant case is restricted to those two positions.
    """
    if node is None:
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == key:
            return True
        if isinstance(child, ast.Attribute) and child.attr == key:
            return True
        if isinstance(child, ast.Subscript):
            index = child.slice
            if isinstance(index, ast.Constant) and index.value == key:
                return True
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in {"get", "pop", "setdefault"}
            and any(isinstance(arg, ast.Constant) and arg.value == key for arg in child.args)
        ):
            return True
    return False


def is_permitted(value: ast.AST | None, key: str) -> bool:
    """Whether a banned key's value is a declared absence or a same-name derivation."""
    return is_declared_absence(value) or derives_from_key(value, key)


class _ToolSurfaceVisitor(ast.NodeVisitor):
    """Walks one module and records every tool-surface construction in it."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[Finding] = []

    # -- dict literals ----------------------------------------------------------
    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value in BANNED_KEYS
                and not is_permitted(value, key.value)
            ):
                self._record(key, "dict_literal", key.value, "dict literal key")
        self.generic_visit(node)

    # -- keyword arguments ------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg in BANNED_KEYS and not is_permitted(keyword.value, keyword.arg):
                self._record(keyword.value, "kwarg", str(keyword.arg), "keyword argument")
        self.generic_visit(node)

    # -- body["tools"] = ... ----------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_subscript(target, node.value)
            self._check_name_binding(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_subscript(node.target, node.value)
        self._check_name_binding(node.target, node.value)
        self.generic_visit(node)

    # -- JSON bodies written as string literals ---------------------------------
    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            stripped = node.value.strip()
            if stripped[:1] in {"{", "["}:
                try:
                    payload = json.loads(stripped)
                except (ValueError, RecursionError):
                    payload = None
                if payload is not None:
                    for key in _json_tool_keys(payload):
                        self._record(node, "json_body", key, "JSON object key in a string literal")
        self.generic_visit(node)

    # -- internals --------------------------------------------------------------
    def _check_subscript(self, target: ast.AST, value: ast.AST | None) -> None:
        if not isinstance(target, ast.Subscript):
            return
        index = target.slice
        if (
            isinstance(index, ast.Constant)
            and isinstance(index.value, str)
            and index.value in BANNED_KEYS
            and not is_permitted(value, index.value)
        ):
            self._record(target, "subscript_assign", index.value, "subscript assignment")

    def _check_name_binding(self, target: ast.AST, value: ast.AST | None) -> None:
        """``tools = [{...}]`` is the DEFINITION of a tool surface, wherever it happens."""
        if not isinstance(target, ast.Name) or target.id not in BANNED_KEYS:
            return
        if is_permitted(value, target.id):
            return
        if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
            self._record(target, "name_binding", target.id, "assignment defining")

    def _record(self, node: ast.AST, kind: str, key: str, detail: str) -> None:
        self.findings.append(
            Finding(
                path=self.path,
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0),
                kind=kind,
                key=key,
                detail=(
                    f"{detail} {key!r} constructs a tool surface. The quarantined call "
                    f"shape holds no tools (ARCHITECTURE.md 8.4 layer 1)."
                ),
            )
        )


def _json_tool_keys(payload: Any) -> list[str]:
    """Every banned key with a non-empty value anywhere in a decoded JSON body."""
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in BANNED_KEYS and value not in ([], {}, None, ()):
                found.append(str(key))
            found.extend(_json_tool_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_json_tool_keys(item))
    return found


def discover_roots(repo_root: Path) -> list[Path]:
    """Every ``src`` tree under ``packages/*`` and ``verticals/*/packages/*``, minus exclusions."""
    roots: list[Path] = []
    patterns = ("packages/*/src", "verticals/*/packages/*/src")
    for pattern in patterns:
        for candidate in sorted(repo_root.glob(pattern)):
            if not candidate.is_dir():
                continue
            if candidate.parent.name in EXCLUDED_PACKAGES:
                continue
            roots.append(candidate)
    return roots


def python_files(root: Path) -> list[Path]:
    """Every ``.py`` file under a root, skipping caches and virtual environments."""
    skip = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
    return sorted(
        path for path in root.rglob("*.py") if not any(part in skip for part in path.parts)
    )


def scan_file(path: Path, repo_root: Path) -> list[Finding]:
    """Parse one module and return its findings. A syntax error is itself a finding."""
    relative = (
        path.relative_to(repo_root).as_posix() if path.is_relative_to(repo_root) else str(path)
    )
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Finding(relative, 0, 0, "unreadable", "", f"cannot read: {exc}")]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [Finding(relative, exc.lineno or 0, exc.offset or 0, "syntax_error", "", str(exc))]
    visitor = _ToolSurfaceVisitor(relative)
    visitor.visit(tree)
    return visitor.findings


def _module_imports(tree: ast.Module) -> list[tuple[str, int]]:
    """Every imported dotted name in a module, with its line."""
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            out.append((module, node.lineno))
            out.extend((f"{module}.{alias.name}".strip("."), node.lineno) for alias in node.names)
    return out


def check_exemptions(repo_root: Path, scanned: list[Path]) -> list[Finding]:
    """Verify every exemption is live, marked, and unimported."""
    findings: list[Finding] = []
    for relative, (reason, marker) in FILE_EXEMPTIONS.items():
        target = repo_root / relative
        if not target.is_file():
            findings.append(
                Finding(
                    relative,
                    0,
                    0,
                    "stale_exemption",
                    "",
                    f"exempt file does not exist. Delete the exemption: dead config in a "
                    f"security scan looks like coverage. Reason it carried: {reason}",
                )
            )
            continue
        source = target.read_text(encoding="utf-8")
        if marker not in source:
            findings.append(
                Finding(
                    relative,
                    0,
                    0,
                    "unmarked_exemption",
                    "",
                    f"exempt file does not carry its marker {marker!r}. The marker is the "
                    f"exemption's consent: without it the file is just a module that "
                    f"builds a tool surface.",
                )
            )
        module_name = target.stem
        for path in scanned:
            if path == target:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for imported, line in _module_imports(tree):
                if imported == module_name or imported.endswith(f".{module_name}"):
                    rel = path.relative_to(repo_root).as_posix()
                    findings.append(
                        Finding(
                            rel,
                            line,
                            0,
                            "exempt_module_imported",
                            module_name,
                            f"{rel} imports the exempt module {module_name!r}. The "
                            f"exemption holds only while nothing imports it: a fallback "
                            f"that can be reached is a fallback that can become the "
                            f"default without review.",
                        )
                    )
    return findings


def run(
    repo_root: Path,
    roots: list[Path] | None = None,
    *,
    check_exempt: bool = True,
) -> tuple[list[Finding], list[Path]]:
    """Scan and return ``(findings, files scanned)``."""
    scan_roots = roots if roots is not None else discover_roots(repo_root)
    exempt = {(repo_root / relative).resolve() for relative in FILE_EXEMPTIONS}

    files: list[Path] = []
    for root in scan_roots:
        files.extend(python_files(root))

    findings: list[Finding] = []
    for path in files:
        if path.resolve() in exempt:
            continue
        findings.extend(scan_file(path, repo_root))
    if check_exempt:
        findings.extend(check_exemptions(repo_root, files))
    return findings, files


def _report(findings: list[Finding], files: list[Path], roots: list[Path], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "roots": [root.as_posix() for root in roots],
                    "files_scanned": len(files),
                    "excluded_packages": EXCLUDED_PACKAGES,
                    "file_exemptions": {k: v[0] for k, v in FILE_EXEMPTIONS.items()},
                    "findings": [asdict(finding) for finding in findings],
                },
                indent=2,
            )
        )
        return
    print(f"assert_no_tool_construction: {len(files)} file(s) across {len(roots)} root(s)")
    for name, reason in EXCLUDED_PACKAGES.items():
        print(f"  excluded package: {name} - {reason}")
    for relative, (reason, _marker) in FILE_EXEMPTIONS.items():
        print(f"  exempt file: {relative} - {reason}")
    if not findings:
        print("OK: no ingest-reachable package constructs a tool surface.")
        return
    print(f"\nFAIL: {len(findings)} finding(s)")
    for finding in findings:
        print(f"  {finding.path}:{finding.line}:{finding.column} [{finding.kind}] {finding.detail}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit status."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="scan this directory instead of discovering package src trees (repeatable)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="repository root; defaults to the one this script lives in",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    roots = [Path(root).resolve() for root in args.root] if args.root else None
    findings, files = run(repo_root, roots, check_exempt=roots is None)
    _report(findings, files, roots if roots is not None else discover_roots(repo_root), args.json)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
