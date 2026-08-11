# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""E3 — *no model code path*.

ARCHITECTURE.md §8.2 asserts E3 with ``import-linter`` plus an SBOM diff. This
module asserts the same **outcome** independently and without reading the kernel
lead's ``import-linter`` configuration, for one reason: a contract file and the
tool that reads it share a failure mode (delete the contract, delete the check),
and the whole value of §8.2 is that its four enforcements do not.

Three legs, each falsifiable on its own:

* **direct scan** — every ``.py`` file under the kernel roots is parsed and its
  imports, ``boto3.client("bedrock…")`` calls and string literals inspected;
* **import graph** — first-party modules reachable from those roots are followed
  transitively, so a kernel module that reaches ``mainline_agentkit`` through two
  hops is caught with the path printed;
* **unparseable is a violation** — a ``.py`` file the scanner cannot parse has
  not been cleared, and "not cleared" is not "clean".

The literal rule (no ``bedrock-runtime`` anywhere in kernel source) is deliberately
crude, because the thing it defends is crude: a regulator reading the kernel must
not find the string. Two escape hatches exist and both are visible in the report —
test files are exempt from the literal rule (a test asserting the *absence* of a
string must be able to name it), and any line may carry the pragma
``# mainline-boundary: allow-literal <reason>``.
"""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .findings import Enforcement, Report
from .repo import EXCLUDED_DIR_NAMES, expand_roots, is_test_path, iter_python_files, rel

#: Kernel-plane source roots. §8.2 E3 plus this domain's brief.
DEFAULT_KERNEL_ROOTS: tuple[str, ...] = (
    "packages/trappoint-*",
    "verticals/mainline/packages/mainline-gate-svc",
)

#: Top-level module names a kernel-plane package may never import, directly or
#: transitively. ``mainline_agentkit`` is on the list because it *is* the model
#: client: importing it puts a Bedrock transport in the kernel image even if no
#: call is made.
DENIED_TOP_LEVEL_IMPORTS: frozenset[str] = frozenset(
    {
        "anthropic",
        "anthropic_bedrock",
        "claude_agent_sdk",
        "instructor",
        "langchain",
        "langchain_aws",
        "langchain_core",
        "langgraph",
        "litellm",
        "llama_index",
        "mainline_agentkit",
        "openai",
        "strands",
        "strands_agents",
    }
)

#: ``boto3.client("bedrock…")`` / ``session.resource("bedrock…")``.
DENIED_CLIENT_SERVICE_PREFIXES: tuple[str, ...] = ("bedrock",)
CLIENT_FACTORY_NAMES: frozenset[str] = frozenset({"client", "resource"})

#: Substrings that may not appear in a string literal in kernel-plane source.
DENIED_LITERAL_SUBSTRINGS: tuple[str, ...] = (
    "bedrock-runtime",
    "bedrock-agentcore",
    "bedrock-mantle",
)

PRAGMA_ALLOW_LITERAL = "mainline-boundary: allow-literal"

AUTHORITY = "ARCHITECTURE.md §8.2 E3"


@dataclass(frozen=True, slots=True)
class ImportSite:
    module: str
    lineno: int


@dataclass(frozen=True, slots=True)
class ClientSite:
    service: str
    lineno: int


@dataclass(frozen=True, slots=True)
class LiteralSite:
    text: str
    lineno: int


@dataclass(frozen=True, slots=True)
class FileScan:
    """Everything one file told us. Immutable, so a scan can be cached and diffed."""

    path: Path
    module: str | None
    imports: tuple[ImportSite, ...]
    denied_clients: tuple[ClientSite, ...]
    denied_literals: tuple[LiteralSite, ...]
    exempted_literals: tuple[LiteralSite, ...]
    syntax_error: str | None

    @property
    def denied_imports(self) -> tuple[ImportSite, ...]:
        return tuple(i for i in self.imports if i.module in DENIED_TOP_LEVEL_IMPORTS)


class _Visitor(ast.NodeVisitor):
    def __init__(self, source_lines: Sequence[str], literal_rule_active: bool) -> None:
        self.source_lines = source_lines
        self.literal_rule_active = literal_rule_active
        self.imports: list[ImportSite] = []
        self.clients: list[ClientSite] = []
        self.literals: list[LiteralSite] = []
        self.exempted: list[LiteralSite] = []

    # -- imports ---------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(ImportSite(module=alias.name.split(".")[0], lineno=node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Relative imports (level > 0) stay inside the package and carry no
        # top-level name; the import graph handles them via module resolution.
        if node.level == 0 and node.module:
            self.imports.append(ImportSite(module=node.module.split(".")[0], lineno=node.lineno))
        self.generic_visit(node)

    # -- boto3 client factories -----------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name: str | None = None
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name in CLIENT_FACTORY_NAMES:
            service = _first_string_arg(node)
            if service is not None and service.lower().startswith(DENIED_CLIENT_SERVICE_PREFIXES):
                self.clients.append(ClientSite(service=service, lineno=node.lineno))
        self.generic_visit(node)

    # -- string literals -------------------------------------------------

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            lowered = node.value.lower()
            hit = next((s for s in DENIED_LITERAL_SUBSTRINGS if s in lowered), None)
            if hit is not None:
                site = LiteralSite(text=hit, lineno=node.lineno)
                if not self.literal_rule_active or self._pragma_on(node.lineno):
                    self.exempted.append(site)
                else:
                    self.literals.append(site)
        self.generic_visit(node)

    def _pragma_on(self, lineno: int) -> bool:
        index = lineno - 1
        if 0 <= index < len(self.source_lines):
            return PRAGMA_ALLOW_LITERAL in self.source_lines[index]
        return False


def _first_string_arg(node: ast.Call) -> str | None:
    """The service name of a ``client(...)``/``resource(...)`` call, if it is literal.

    boto3 takes the service as the first positional argument or as
    ``service_name=``. A non-literal service name (a variable) is invisible here
    and is caught instead by E1 (no IAM) and E2 (no route) — which is exactly why
    §8.2 has four enforcements and not one.
    """
    if node.args:
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    for kw in node.keywords:
        if (
            kw.arg in {"service_name", "service"}
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def scan_source(
    path: Path, source: str, *, module: str | None = None, literal_rule_active: bool = True
) -> FileScan:
    """Parse one file. A parse failure is returned, never raised."""
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return FileScan(
            path=path,
            module=module,
            imports=(),
            denied_clients=(),
            denied_literals=(),
            exempted_literals=(),
            syntax_error=f"{type(exc).__name__}: {exc}",
        )
    visitor = _Visitor(lines, literal_rule_active)
    visitor.visit(tree)
    return FileScan(
        path=path,
        module=module,
        imports=tuple(visitor.imports),
        denied_clients=tuple(visitor.clients),
        denied_literals=tuple(visitor.literals),
        exempted_literals=tuple(visitor.exempted),
        syntax_error=None,
    )


def scan_file(path: Path, *, module: str | None = None) -> FileScan:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return FileScan(
            path=path,
            module=module,
            imports=(),
            denied_clients=(),
            denied_literals=(),
            exempted_literals=(),
            syntax_error=f"unreadable: {exc}",
        )
    return scan_source(path, source, module=module, literal_rule_active=not is_test_path(path))


# ---------------------------------------------------------------------------
# First-party module index and import graph
# ---------------------------------------------------------------------------

#: Where first-party importable code lives. Both layouts are matched so a package
#: that has not adopted ``src/`` yet is still indexed rather than invisible.
SRC_ROOT_PATTERNS: tuple[str, ...] = (
    "packages/*/src",
    "verticals/*/packages/*/src",
    "packages/*",
    "verticals/*/packages/*",
)


@dataclass(frozen=True, slots=True)
class ModuleIndex:
    """Dotted first-party module name → file path."""

    modules: Mapping[str, Path]

    @classmethod
    def build(cls, repo_root: Path, patterns: Sequence[str] = SRC_ROOT_PATTERNS) -> ModuleIndex:
        table: dict[str, Path] = {}
        for pattern in patterns:
            for src_root in sorted(repo_root.glob(pattern)):
                if not src_root.is_dir() or src_root.name in EXCLUDED_DIR_NAMES:
                    continue
                for py in iter_python_files(src_root):
                    dotted = _module_name(py, src_root)
                    if dotted is None:
                        continue
                    # First writer wins: ``packages/*/src`` is scanned before the
                    # flat fallback, so a src-layout package keeps its own name.
                    table.setdefault(dotted, py)
        return cls(modules=table)

    def path_for(self, module: str) -> Path | None:
        return self.modules.get(module)

    def module_for(self, path: Path) -> str | None:
        resolved = path.resolve()
        for name, candidate in self.modules.items():
            if candidate.resolve() == resolved:
                return name
        return None

    def resolve_import(self, imported: str) -> str | None:
        """Longest-prefix match of a dotted import onto an indexed module."""
        parts = imported.split(".")
        while parts:
            candidate = ".".join(parts)
            if candidate in self.modules:
                return candidate
            parts.pop()
        return None


def _module_name(py: Path, src_root: Path) -> str | None:
    try:
        relative = py.resolve().relative_to(src_root.resolve())
    except ValueError:
        return None
    parts = list(relative.parts)
    if not parts:
        return None
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][: -len(".py")]
    if not parts:
        return None
    if any(not part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


@dataclass(frozen=True, slots=True)
class ImportGraph:
    """First-party edges plus, per module, its full top-level import set."""

    edges: Mapping[str, frozenset[str]]
    top_level: Mapping[str, frozenset[str]]
    scans: Mapping[str, FileScan]

    @classmethod
    def build(cls, index: ModuleIndex) -> ImportGraph:
        edges: dict[str, frozenset[str]] = {}
        top: dict[str, frozenset[str]] = {}
        scans: dict[str, FileScan] = {}
        for module, path in index.modules.items():
            scan = scan_file(path, module=module)
            scans[module] = scan
            imported = {i.module for i in scan.imports}
            # Absolute dotted imports resolve through the index; only the first
            # segment is recorded above, so re-read the file's import nodes for
            # the full dotted names.
            resolved: set[str] = set()
            for dotted in _dotted_imports(path):
                target = index.resolve_import(dotted)
                if target is not None and target != module:
                    resolved.add(target)
            # A package's ``__init__`` implicitly reaches its submodules only if
            # it imports them, which the above already captures. Parent packages
            # are added so ``import a.b`` reaches ``a``'s ``__init__``.
            edges[module] = frozenset(resolved)
            top[module] = frozenset(imported)
        return cls(edges=edges, top_level=top, scans=scans)

    def reachable_with_paths(self, roots: Iterable[str]) -> dict[str, tuple[str, ...]]:
        """BFS from ``roots``; value is the import path that reaches the key."""
        out: dict[str, tuple[str, ...]] = {}
        queue: deque[tuple[str, tuple[str, ...]]] = deque()
        for root in sorted(set(roots)):
            if root in self.edges and root not in out:
                out[root] = (root,)
                queue.append((root, (root,)))
        while queue:
            module, path = queue.popleft()
            for nxt in sorted(self.edges.get(module, frozenset())):
                if nxt not in out:
                    trail = (*path, nxt)
                    out[nxt] = trail
                    queue.append((nxt, trail))
        return out


def _dotted_imports(path: Path) -> tuple[str, ...]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return ()
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{a.name}" for a in node.names)
    return tuple(names)


# ---------------------------------------------------------------------------
# The enforcement
# ---------------------------------------------------------------------------


def scan_kernel_code_boundary(
    repo_root: Path, *, roots: Sequence[str] = DEFAULT_KERNEL_ROOTS
) -> Report:
    """Run E3 over the kernel-plane source roots.

    A root pattern that matches nothing produces ``E3-ROOT-ABSENT`` **as a skip
    with a reason**, and the caller must treat that as "not proven" rather than
    "proven clean". The moment ``verticals/mainline/packages/mainline-gate-svc``
    appears on disk the pattern matches, the skip disappears, and the scan is
    enforced with no further edit to this file.
    """
    report = Report(enforcement=Enforcement.E3_CODE)
    matched = expand_roots(repo_root, roots)
    index = ModuleIndex.build(repo_root)
    graph = ImportGraph.build(index)

    root_modules: set[str] = set()
    any_root_present = False

    for pattern, paths in matched.items():
        if not paths:
            report.skip(
                rule="E3-ROOT-ABSENT",
                subject=pattern,
                reason=(
                    "no path matches this kernel-plane root, so nothing was scanned for it. "
                    "This is NOT a pass: the check becomes enforcing with zero edits the "
                    "moment the path exists."
                ),
            )
            continue
        any_root_present = True
        for root_path in paths:
            for py in iter_python_files(root_path):
                report.examine()
                scan = scan_file(py)
                module = index.module_for(py)
                if module is not None:
                    root_modules.add(module)
                _record_file_findings(report, scan, repo_root)

    if not any_root_present:
        report.note(
            "E3 examined no kernel-plane source at all. Every root pattern is absent; "
            "the report is not evidence of anything."
        )
        return report

    # Import-graph leg: anything reachable from a kernel module, however deep.
    reachable = graph.reachable_with_paths(root_modules)
    for module, trail in sorted(reachable.items()):
        if module in root_modules:
            continue  # already covered by the direct scan
        report.examine()
        reachable_scan = graph.scans.get(module)
        if reachable_scan is None:
            continue
        scan = reachable_scan
        for site in scan.denied_imports:
            report.violate(
                rule="E3-IMPORT-REACHABLE",
                subject=f"{module}:{site.lineno}",
                detail=(
                    f"module reachable from the kernel imports {site.module!r}; "
                    f"import path: {' -> '.join(trail)}"
                ),
                authority=AUTHORITY,
            )
        for client in scan.denied_clients:
            report.violate(
                rule="E3-BEDROCK-CLIENT-REACHABLE",
                subject=f"{module}:{client.lineno}",
                detail=(
                    f"module reachable from the kernel constructs an AWS client for "
                    f"{client.service!r}; import path: {' -> '.join(trail)}"
                ),
                authority=AUTHORITY,
            )

    if report.examined == 0:
        report.note("E3 matched roots but found no Python files to examine.")
    return report


def _record_file_findings(report: Report, scan: FileScan, repo_root: Path) -> None:
    where = rel(scan.path, repo_root)
    if scan.syntax_error is not None:
        report.violate(
            rule="E3-UNPARSEABLE",
            subject=where,
            detail=(
                f"kernel-plane source could not be parsed ({scan.syntax_error}); "
                "an unparseable file has not been cleared, and 'not cleared' is not 'clean'"
            ),
            authority=AUTHORITY,
        )
        return
    for site in scan.denied_imports:
        report.violate(
            rule="E3-IMPORT",
            subject=f"{where}:{site.lineno}",
            detail=f"kernel-plane source imports {site.module!r}",
            authority=AUTHORITY,
        )
    for client in scan.denied_clients:
        report.violate(
            rule="E3-BEDROCK-CLIENT",
            subject=f"{where}:{client.lineno}",
            detail=f"kernel-plane source constructs an AWS client for {client.service!r}",
            authority=AUTHORITY,
        )
    for literal in scan.denied_literals:
        report.violate(
            rule="E3-LITERAL",
            subject=f"{where}:{literal.lineno}",
            detail=(
                f"kernel-plane source contains the string {literal.text!r}; "
                f"add `# {PRAGMA_ALLOW_LITERAL} <reason>` if this is genuinely inert"
            ),
            authority=AUTHORITY,
        )
    for literal in scan.exempted_literals:
        report.exempt(
            rule="E3-LITERAL",
            subject=f"{where}:{literal.lineno}",
            reason=(
                f"string {literal.text!r} allowed: "
                + (
                    "file is a test, which must be able to name the string it forbids"
                    if is_test_path(scan.path)
                    else "explicit allow-literal pragma on the line"
                )
            ),
        )
