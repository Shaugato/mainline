# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The assertion CI must run: no model is reachable from the merge gate.

ARCHITECTURE.md §8.2 asserts "no model can reach the merge gate" four ways. E3 is the
code-path leg, and until this distribution existed E3 scanned a directory that was not
there — `mainline_boundary.astscan` recorded `E3-ROOT-ABSENT` as a skip-with-reason,
which was honest and which proved nothing. This module is the part of E3 that lives
inside the gate service itself, and it asserts the claim on **two independent surfaces**
because they fail differently:

**Surface one — the runtime closure.** Import `mainline_gate_svc` in a fresh interpreter
and walk `sys.modules`. This catches the thing that actually happens: a helper module
that does `import boto3` at the top for one convenience function, three commits after
anybody read the dependency list.

**Surface two — the declared closure.** Walk `importlib.metadata.requires` transitively
over the distribution metadata. This catches what surface one cannot: a dependency that
is *declared* and merely not imported on today's code path. A runtime absence with a
declared dependency is still a supply-chain reach — the wheel is in the image, the
transitive resolution pins it, an SBOM diff shows it, and a single future import turns it
on with no dependency review at all.

**Surface three — the source, without installing anything.** An AST scan over this
package's own `src/`, so the assertion still means something in a checkout where nothing
has been `pip install`ed.

PL-2, red before green: `test_the_declared_walk_catches_a_planted_dependency` and
`test_the_source_scan_catches_a_planted_import` drive the same two functions with a
planted reach and require them to fail. A suite that has never been red asserts nothing.
"""

from __future__ import annotations

import ast
import importlib.metadata
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "mainline_gate_svc"
DISTRIBUTION = "mainline-gate-svc"

# The ten names the brief names, verbatim, plus the three aliases that are the same
# reach under a different distribution name. `.importlinter` contract 5 carries the
# same list; it is repeated here rather than parsed out of that file on purpose — a
# check and the config it checks must not share a failure mode, and an sdist of this
# package contains `src`, `tests` and `README.md` but no repository configuration.
MODEL_MODULES: frozenset[str] = frozenset(
    {
        "anthropic",
        "boto3",
        "botocore",
        "langchain",
        "langchain_core",
        "llama_index",
        "openai",
        "sentence_transformers",
        "strands",
        "strands_agents",
        "torch",
        "transformers",
    }
)

#: The same names as PEP 503 normalised distribution names, for the metadata walk.
#: `sentence_transformers` ships as `sentence-transformers`; the module name and the
#: distribution name are different strings and a check that conflated them would miss.
MODEL_DISTRIBUTIONS: frozenset[str] = frozenset(
    name.replace("_", "-") for name in MODEL_MODULES
) | {"llama-index-core", "langchain-community", "anthropic-bedrock", "boto3-stubs"}

#: These MUST be reachable. Without them the walks below could report a clean closure
#: because they walked nothing, which is the failure mode this whole module exists to
#: refuse in the enforcement it belongs to.
REQUIRED_IN_CLOSURE: frozenset[str] = frozenset({"psycopg", "trappoint-core", "mainline-domain"})

_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRA_MARKER = re.compile(r"\bextra\s*==")


def normalise(name: str) -> str:
    """PEP 503 normalisation: lower case, runs of ``-_.`` collapsed to one ``-``."""
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(specifier: str) -> str:
    """Return the distribution name at the head of a PEP 508 requirement string.

    ``'psycopg[binary]>=3.3.4 ; python_version < "4"'`` -> ``'psycopg'``. Written by
    hand against a regex rather than with `packaging.requirements` because this test is
    the place where a dependency is counted, and counting dependencies with a dependency
    is how the count stops being trustworthy.
    """
    found = _REQUIREMENT_NAME.match(specifier)
    return normalise(found.group(1)) if found else ""


def is_extra_gated(specifier: str) -> bool:
    """True when the requirement only applies under an opt-in extra.

    ``'torch>=2 ; extra == "gpu"'`` is not in anyone's install unless they asked for
    ``[gpu]``. The distinction matters because the walk below crosses distributions we do
    not own: `pint` declaring `pytest-mpl` under `[test]` is not a reach by this gate
    service, and a check that said it was would be disabled within a week.
    """
    _, semicolon, marker = specifier.partition(";")
    return bool(semicolon) and _EXTRA_MARKER.search(marker) is not None


@dataclass(frozen=True, slots=True)
class Edge:
    """One declared requirement, and whether an opt-in extra guards it."""

    source: str
    target: str
    extra_gated: bool


@dataclass
class ClosureWalk:
    """The result of walking a declared dependency graph."""

    visited: set[str] = field(default_factory=set)
    unresolved: set[str] = field(default_factory=set)
    edges: list[Edge] = field(default_factory=list)

    @property
    def denied(self) -> list[tuple[str, str]]:
        """Every followed edge that reaches a model distribution."""
        return [
            (edge.source, edge.target)
            for edge in self.edges
            if edge.target in MODEL_DISTRIBUTIONS and not edge.extra_gated
        ]

    @property
    def denied_behind_an_extra(self) -> list[tuple[str, str]]:
        """Reaches that exist only under an opt-in extra, reported separately."""
        return [
            (edge.source, edge.target)
            for edge in self.edges
            if edge.target in MODEL_DISTRIBUTIONS and edge.extra_gated
        ]


def walk_declared_closure(
    roots: Iterable[str],
    requires_of: Callable[[str], list[str] | None],
    *,
    follow_extras_from: frozenset[str] = frozenset(),
) -> ClosureWalk:
    """Walk declared requirements transitively from *roots*.

    Args:
        roots: normalised distribution names to start from.
        requires_of: returns the PEP 508 requirement strings a distribution declares, or
            ``None`` when the distribution is not installed and cannot be interrogated.
        follow_extras_from: distributions whose *extra-gated* requirements are also
            followed. The gate service's own name goes here — we own its
            ``optional-dependencies`` and an opt-in model SDK is still a model SDK we
            declared. Third-party extras are recorded as edges but not traversed.

    Returns:
        The walk. ``unresolved`` matters as much as ``visited``: a node that could not be
        interrogated is a hole in the claim, and a claim with a hole in it must say so.
    """
    walk = ClosureWalk()
    followed_extras = frozenset(normalise(name) for name in follow_extras_from)
    queue = [normalise(root) for root in roots]
    while queue:
        current = queue.pop()
        if current in walk.visited:
            continue
        walk.visited.add(current)
        declared = requires_of(current)
        if declared is None:
            walk.unresolved.add(current)
            continue
        for specifier in declared:
            child = requirement_name(specifier)
            if not child:
                continue
            gated = is_extra_gated(specifier) and current not in followed_extras
            walk.edges.append(Edge(current, child, gated))
            if not gated and child not in walk.visited:
                queue.append(child)
    return walk


def _installed_requires(name: str) -> list[str] | None:
    try:
        return list(importlib.metadata.requires(name) or [])
    except importlib.metadata.PackageNotFoundError:
        return None


def _pyproject_requires() -> list[str]:
    """This package's own declared runtime and optional dependencies, off disk."""
    data = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project", {})
    declared: list[str] = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    return declared


def repository_requires_of(name: str) -> list[str] | None:
    """``requires_of`` for the real graph.

    For this distribution the answer is the UNION of what the installed metadata says
    and what `pyproject.toml` says. They should agree; when they do not, the disagreement
    is a stale editable install, and taking the union means the stricter of the two wins
    rather than whichever one happens to be read.
    """
    if normalise(name) == normalise(DISTRIBUTION):
        return sorted({*(_installed_requires(name) or []), *_pyproject_requires()})
    return _installed_requires(name)


# ---------------------------------------------------------------------------
# Surface one — the runtime closure, measured in a fresh interpreter
# ---------------------------------------------------------------------------

_PROBE = """
import json, sys
import mainline_gate_svc
import mainline_gate_svc.cli
import mainline_gate_svc.config
import mainline_gate_svc.service
print(json.dumps(sorted(sys.modules)))
"""


def _fresh_interpreter_modules() -> list[str]:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if completed.returncode != 0:
        pytest.fail(
            "importing mainline_gate_svc in a fresh interpreter failed, so the runtime "
            f"closure could not be measured at all:\n{completed.stderr.strip()}"
        )
    return list(json.loads(completed.stdout))


def test_importing_the_service_loads_no_model_module() -> None:
    """Import the package in a fresh interpreter; walk sys.modules; refuse any model."""
    modules = _fresh_interpreter_modules()
    present = sorted(MODEL_MODULES.intersection(modules))
    assert not present, (
        "importing mainline_gate_svc loaded model SDK module(s) "
        f"{present}. ARCHITECTURE.md §8.2 says no model can reach the merge gate; this "
        "process just did."
    )


def test_the_runtime_closure_measurement_is_not_vacuous() -> None:
    """A clean report must come from a walk that actually loaded the gate path."""
    modules = set(_fresh_interpreter_modules())
    for expected in ("mainline_gate_svc", "mainline_gate_svc.service", "psycopg", "trappoint_core"):
        assert expected in modules, (
            f"{expected!r} was not in sys.modules after importing the service, so the "
            "clean result above was measured over the wrong process"
        )


def test_importing_the_service_adds_no_model_module_in_process() -> None:
    """The same claim inside the running session, over the delta this import caused."""
    before = set(sys.modules)
    import mainline_gate_svc
    import mainline_gate_svc.cli
    import mainline_gate_svc.service

    assert mainline_gate_svc.__version__
    added = set(sys.modules) - before
    leaked = sorted(MODEL_MODULES.intersection(added))
    assert not leaked, f"importing the gate service pulled in {leaked}"


# ---------------------------------------------------------------------------
# Surface two — the DECLARED closure, transitively, over distribution metadata
# ---------------------------------------------------------------------------


def repository_walk() -> ClosureWalk:
    """The real declared closure of this distribution."""
    return walk_declared_closure(
        [DISTRIBUTION],
        repository_requires_of,
        follow_extras_from=frozenset({DISTRIBUTION}),
    )


def test_declared_dependency_closure_holds_no_model_distribution() -> None:
    """No model distribution appears anywhere in the transitive declared closure."""
    walk = repository_walk()
    assert not walk.denied, (
        "the declared dependency closure reaches a model distribution: "
        + "; ".join(f"{src} -> {dst}" for src, dst in walk.denied)
        + ". A runtime absence with a declared dependency is still a supply-chain reach."
    )


def test_this_distribution_declares_no_model_reach_even_behind_an_extra() -> None:
    """We own our own `optional-dependencies`; an opt-in model SDK is still one."""
    ours = {
        (src, dst)
        for src, dst in repository_walk().denied_behind_an_extra
        if src == normalise(DISTRIBUTION)
    }
    assert not ours, f"this distribution declares a model SDK behind an extra: {sorted(ours)}"


def test_the_declared_walk_is_not_vacuous() -> None:
    """The clean closure above must be a walk over the real three dependencies."""
    walk = repository_walk()
    missing = sorted(REQUIRED_IN_CLOSURE - walk.visited)
    assert not missing, (
        f"the declared closure did not reach {missing}; it visited {sorted(walk.visited)}. "
        "A closure that walked nothing reports clean for the wrong reason."
    )
    assert walk.visited - walk.unresolved, (
        "every node in the closure was unresolved, so nothing was actually interrogated"
    )


def test_the_declared_walk_catches_a_planted_dependency_two_levels_down() -> None:
    """PL-2. Plant an ordinary runtime reach two levels down; require it to be found."""
    planted = {
        normalise(DISTRIBUTION): ["trappoint-core", "psycopg[binary]>=3.3.4"],
        "trappoint-core": ["some-helper>=1.0"],
        "some-helper": ["boto3>=1.35"],
        "psycopg": [],
        "boto3": [],
    }
    walk = walk_declared_closure([DISTRIBUTION], lambda name: planted.get(normalise(name)))
    assert walk.denied == [("some-helper", "boto3")], (
        f"the transitive walk missed a planted reach; it found {walk.denied}"
    )


def test_the_declared_walk_catches_a_planted_reach_behind_our_own_extra() -> None:
    """PL-2. An extra WE declare is followed; an extra a stranger declares is not."""
    planted = {
        normalise(DISTRIBUTION): ['anthropic>=0.40 ; extra == "explain"'],
        "pint": ['torch>=2 ; extra == "test"'],
        "anthropic": [],
    }
    ours = walk_declared_closure(
        [DISTRIBUTION],
        lambda name: planted.get(normalise(name)),
        follow_extras_from=frozenset({DISTRIBUTION}),
    )
    assert ours.denied == [(normalise(DISTRIBUTION), "anthropic")]

    theirs = walk_declared_closure(["pint"], lambda name: planted.get(normalise(name)))
    assert theirs.denied == []
    assert theirs.denied_behind_an_extra == [("pint", "torch")]


def test_the_declared_walk_reports_what_it_could_not_interrogate() -> None:
    """An unresolvable node is recorded, not silently treated as a leaf."""
    walk = walk_declared_closure(
        ["root"], lambda name: ["ghost>=1"] if normalise(name) == "root" else None
    )
    assert walk.unresolved == {"ghost"}


@pytest.mark.parametrize(
    ("specifier", "gated"),
    [
        ("boto3>=1.35", False),
        ('boto3>=1.35 ; extra == "aws"', True),
        ('psycopg ; python_version >= "3.13"', False),
        ("psycopg[binary]", False),
    ],
)
def test_extra_gating_is_read_off_the_marker(specifier: str, gated: bool) -> None:
    assert is_extra_gated(specifier) is gated


@pytest.mark.parametrize(
    ("specifier", "expected"),
    [
        ("psycopg[binary]>=3.3.4", "psycopg"),
        ("Sentence_Transformers", "sentence-transformers"),
        ('boto3 >=1.35 ; extra == "aws"', "boto3"),
        ("trappoint-core", "trappoint-core"),
        ("", ""),
    ],
)
def test_requirement_name_reads_the_head_of_a_pep_508_string(specifier: str, expected: str) -> None:
    assert requirement_name(specifier) == expected


# ---------------------------------------------------------------------------
# Surface three — the source itself, with nothing installed
# ---------------------------------------------------------------------------


def top_level_imports(source: str) -> set[str]:
    """Return every top-level module name imported by *source*, absolute imports only."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def test_no_source_file_in_this_package_imports_a_model_sdk() -> None:
    """The claim, asserted over the source, in a checkout where nothing is installed."""
    offences: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        imported = top_level_imports(path.read_text(encoding="utf-8"))
        for name in sorted(MODEL_MODULES.intersection(imported)):
            offences.append(f"{path.relative_to(PACKAGE_ROOT).as_posix()} imports {name}")
    assert not offences, "; ".join(offences)


def test_the_source_scan_catches_a_planted_import() -> None:
    """PL-2 for surface three."""
    planted = "from botocore.session import Session\n\n\ndef go() -> None:\n    Session()\n"
    assert MODEL_MODULES.intersection(top_level_imports(planted)) == {"botocore"}


# ---------------------------------------------------------------------------
# Surface four — the ENVIRONMENT. A closure with no model SDK in it is still a
# process holding a usable credential if the variables are there.
# ---------------------------------------------------------------------------

CLEAN_ENVIRONMENT = {
    "PATH": "/usr/bin",
    "MAINLINE_GATE_DSN": "postgresql://root@localhost:26257/defaultdb?sslmode=disable",
}


def test_the_service_refuses_to_start_holding_an_aws_credential() -> None:
    from mainline_gate_svc.config import ModelEnvironmentPresent, load_config

    environ = {**CLEAN_ENVIRONMENT, "AWS_SECRET_ACCESS_KEY": "s3cr3t"}
    with pytest.raises(ModelEnvironmentPresent) as caught:
        load_config(environ)
    assert caught.value.variables == ("AWS_SECRET_ACCESS_KEY",)
    assert "s3cr3t" not in str(caught.value), "the refusal printed the credential it refused"


@pytest.mark.parametrize(
    "variable",
    [
        "AWS_PROFILE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "BEDROCK_ENDPOINT",
        "OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
        "COHERE_API_KEY",
        "HF_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "LANGCHAIN_TRACING_V2",
        "STRANDS_TELEMETRY",
    ],
)
def test_every_provider_variable_family_refuses_the_start(variable: str) -> None:
    from mainline_gate_svc.config import model_environment

    assert model_environment({**CLEAN_ENVIRONMENT, variable: "1"}) == (variable,)


def test_a_clean_environment_starts_and_finds_the_dsn() -> None:
    from mainline_gate_svc.config import load_config

    config = load_config(CLEAN_ENVIRONMENT)
    assert config.dsn == CLEAN_ENVIRONMENT["MAINLINE_GATE_DSN"]
    assert config.schema == "mainline"
    assert config.subject_kind == "permit"


def test_an_emptied_variable_is_absent_not_present() -> None:
    """`AWS_PROFILE=` is how a wrapper clears an inherited value; refusing it refuses the fix."""
    from mainline_gate_svc.config import model_environment

    assert model_environment({**CLEAN_ENVIRONMENT, "AWS_PROFILE": ""}) == ()


def test_no_dsn_is_a_distinct_condition_from_a_forbidden_environment() -> None:
    from mainline_gate_svc.config import MissingDsn, load_config

    with pytest.raises(MissingDsn):
        load_config({"PATH": "/usr/bin"})


@pytest.mark.parametrize(
    ("variable", "position"),
    [("MAINLINE_GATE_DSN", 0), ("MAINLINE_TEST_DSN", 1), ("TRAPPOINT_DSN", 2)],
)
def test_the_four_dsn_spellings_already_in_this_repository_are_honoured(
    variable: str, position: int
) -> None:
    from mainline_gate_svc.config import DSN_VARIABLES, load_config

    assert DSN_VARIABLES[position] == variable
    assert (
        load_config({variable: "postgresql://root@h:26257/d"}).dsn == "postgresql://root@h:26257/d"
    )


def test_the_dsn_is_redacted_before_it_reaches_a_log() -> None:
    from mainline_gate_svc.config import GateConfig

    config = GateConfig(dsn="postgresql://root:hunter2@node1:26257/defaultdb?sslmode=require")
    assert config.redacted_dsn() == "postgresql://node1:26257/defaultdb?sslmode=require"
    assert "hunter2" not in config.redacted_dsn()
