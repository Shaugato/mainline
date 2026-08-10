# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The registry guard, proven RED before it is trusted GREEN.

`.importlinter` has promised this mechanism since it was written:

    A new package is registered by CI refusing the build, not by anyone remembering.

On 2026-08-10 that promise was measured false — five `root_packages` against
twenty-seven distributions on disk — so the promise's implementation
(`scripts/qa/check_import_registry.py`) arrives with the same obligation every
enforcement in this repository carries: PL-2, a suite that has never been red asserts
nothing.

Every check the guard makes is therefore driven twice here: once against a synthetic
tree built to break it, and once against this repository. The synthetic half is what
makes the green half mean something — a guard that reports "all accounted for" over a
`glob` that matched nothing reports exactly the same sentence.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "qa" / "check_import_registry.py"
CONFIG = REPO_ROOT / ".importlinter"


def _load_guard() -> ModuleType:
    """Import the script by path; `scripts/` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location("_check_import_registry", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `dataclasses` resolves a class's own module out of
    # `sys.modules` while processing it, and a module that is not there yet fails with
    # `'NoneType' object has no attribute '__dict__'` — measured, not guessed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


MINIMAL_CONFIG = """\
[importlinter]
root_packages =
    alpha_pkg
include_external_packages = True

[importlinter:contract:only]
name = the only contract
type = forbidden
source_modules =
    alpha_pkg
forbidden_modules =
    beta_pkg
allow_indirect_imports = False
"""


def make_distribution(root: Path, project: str, module: str) -> None:
    """Create a minimal workspace distribution: a `pyproject.toml` and a `src/` module."""
    package = root / project
    (package / "src" / module).mkdir(parents=True, exist_ok=True)
    (package / "src" / module / "__init__.py").write_text("", encoding="utf-8")
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "{module.replace("_", "-")}"\nversion = "0"\n', encoding="utf-8"
    )


@pytest.fixture
def synthetic(tmp_path: Path) -> Path:
    """A two-distribution workspace: `alpha_pkg` rooted, `beta_pkg` forbidden."""
    make_distribution(tmp_path, "packages/alpha", "alpha_pkg")
    make_distribution(tmp_path, "verticals/demo/packages/beta", "beta_pkg")
    (tmp_path / ".importlinter").write_text(MINIMAL_CONFIG, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# RED first. Each of the three failure classes, driven until it fires.
# ---------------------------------------------------------------------------


def test_an_unregistered_distribution_is_refused_by_name(synthetic: Path) -> None:
    """The hole the promise was about: a distribution in no contract at all."""
    make_distribution(synthetic, "packages/gamma", "gamma_pkg")

    report = guard.check(synthetic, synthetic / ".importlinter")

    assert not report.ok
    assert [d.module for d in report.unregistered] == ["gamma_pkg"]
    assert "gamma_pkg" in guard.render(report, synthetic / ".importlinter")
    assert "packages/gamma" in guard.render(report, synthetic / ".importlinter")


def test_being_named_only_in_forbidden_modules_is_registration_enough(synthetic: Path) -> None:
    """`beta_pkg` is in no `root_packages`; who imports it IS checked, so it counts."""
    report = guard.check(synthetic, synthetic / ".importlinter")
    assert report.ok
    assert report.distributions == 2


def test_a_stale_root_package_is_refused(synthetic: Path) -> None:
    """One name with no distribution takes out every contract; find it in milliseconds."""
    config = synthetic / ".importlinter"
    config.write_text(
        MINIMAL_CONFIG.replace("    alpha_pkg\ninclude", "    alpha_pkg\n    ghost_pkg\ninclude"),
        encoding="utf-8",
    )

    report = guard.check(synthetic, config)

    assert not report.ok
    assert report.stale_roots == ["ghost_pkg"]
    assert "Could not find package" in guard.render(report, config)


def test_a_source_module_that_is_not_a_root_package_is_refused(synthetic: Path) -> None:
    """A contract cannot assert over a module outside the graph."""
    config = synthetic / ".importlinter"
    config.write_text(
        MINIMAL_CONFIG.replace(
            "source_modules =\n    alpha_pkg\n", "source_modules =\n    alpha_pkg\n    beta_pkg\n"
        ),
        encoding="utf-8",
    )

    report = guard.check(synthetic, config)

    assert not report.ok
    assert report.unrooted_sources == [("the only contract", "beta_pkg")]


def test_a_directory_that_cannot_be_a_module_is_not_a_distribution(synthetic: Path) -> None:
    """`src/.mypy_cache/` exists in this repository and is not a package."""
    (synthetic / "packages/alpha/src/.mypy_cache").mkdir(parents=True)
    (synthetic / "packages/alpha/src/__pycache__").mkdir(parents=True)

    report = guard.check(synthetic, synthetic / ".importlinter")

    assert report.ok
    assert report.distributions == 2


def test_a_package_directory_without_a_pyproject_is_not_a_distribution(synthetic: Path) -> None:
    """`mainline-corpus` has source and no `pyproject.toml`; it is registered elsewhere."""
    orphan = synthetic / "verticals/demo/packages/delta/src/delta_pkg"
    orphan.mkdir(parents=True)

    report = guard.check(synthetic, synthetic / ".importlinter")

    assert report.ok
    assert report.distributions == 2


# ---------------------------------------------------------------------------
# The exit code, which is the only thing CI reads
# ---------------------------------------------------------------------------


def test_main_exits_non_zero_on_an_unregistered_distribution(synthetic: Path) -> None:
    make_distribution(synthetic, "packages/gamma", "gamma_pkg")
    code = guard.main(["--repo-root", str(synthetic), "--config", str(synthetic / ".importlinter")])
    assert code == 1


def test_main_exits_zero_on_a_complete_registry(synthetic: Path) -> None:
    code = guard.main(["--repo-root", str(synthetic), "--config", str(synthetic / ".importlinter")])
    assert code == 0


def test_main_exits_two_when_there_is_no_configuration(tmp_path: Path) -> None:
    assert guard.main(["--repo-root", str(tmp_path), "--config", str(tmp_path / "absent")]) == 2


# ---------------------------------------------------------------------------
# GREEN, against this repository — and the `done_when` clause, driven directly
# ---------------------------------------------------------------------------


def test_this_repository_registers_every_distribution() -> None:
    report = guard.check(REPO_ROOT, CONFIG)
    assert report.ok, guard.render(report, CONFIG)
    assert report.distributions >= 29
    assert report.root_packages >= 29
    assert len(report.contracts) == 7


def test_removing_one_distribution_from_the_config_makes_the_guard_refuse(
    tmp_path: Path,
) -> None:
    """The `done_when` clause: delete a name, and the build must stop naming it.

    `mainline_gate_svc` is removed rather than an arbitrary name because it is the one
    the whole boundary claim rests on, and a registry that let *that* one fall out
    silently would be worse than no registry.
    """
    doctored = tmp_path / ".importlinter"
    original = CONFIG.read_text(encoding="utf-8")
    assert "\n    mainline_gate_svc\n" in original
    doctored.write_text(original.replace("\n    mainline_gate_svc", ""), encoding="utf-8")

    report = guard.check(REPO_ROOT, doctored)

    assert not report.ok
    assert [d.module for d in report.unregistered] == ["mainline_gate_svc"]
    assert guard.main(["--repo-root", str(REPO_ROOT), "--config", str(doctored)]) == 1


def test_the_configuration_names_the_seven_contracts_in_order() -> None:
    registry = guard.read_registry(CONFIG)
    numbers = [name.split(".")[0] for name in registry.contracts]
    assert numbers == ["1", "2", "3", "4", "5", "6", "7"]


def test_every_contract_source_module_is_a_root_package() -> None:
    registry = guard.read_registry(CONFIG)
    for contract, sources in registry.source_modules.items():
        missing = sorted(sources - registry.root_packages)
        assert not missing, f"{contract} sources {missing}, which are not root packages"


def test_the_guard_runs_as_a_script_and_prints_json() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["unregistered"] == []
    assert payload["stale_roots"] == []
    assert len(payload["contracts"]) == 7
