# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The type checker must see the whole workspace, and must keep seeing it.

Measured on 2026-08-10, before this file existed: ``mypy.ini`` carried five
``mypy_path`` entries against twenty-seven distributions on disk, and *every*
invocation printed ``unused section(s): …`` for the modules the other invocation
covered.  Two invocations were in use; neither of them checked the substrate as
a whole.  Nothing was wrong with the code — ``129`` files yielded exactly one
error — but nothing proved the code was checked either, and a distribution added
tomorrow would have joined the tree with no section, no path entry and no
complaint from anything.

That is the same failure mode the ``import-linter-registry`` job exists to stop
for import contracts, so it gets the same mechanism: a script that derives the
truth from the filesystem and refuses when the config has fallen behind it.

These tests assert the refusal *first* (PL-2: a suite that has never been red
asserts nothing).  Each synthetic case plants a distribution the real
``mypy.ini`` cannot possibly know about and requires ``--check`` to fail, with a
reason a reader can act on; only then is the real tree asserted green.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "qa" / "mypy_targets.py"
REAL_CONFIG = REPO_ROOT / "mypy.ini"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the target script exactly as CI and the justfile do."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )


def plant_distribution(
    root: Path,
    dist_dir: str,
    module: str,
    *,
    project_name: str | None = None,
) -> Path:
    """Create a minimally-valid workspace distribution under ``root``."""
    dist = root / dist_dir
    package = dist / "src" / module
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""planted."""\n', encoding="utf-8")
    name = project_name or dist_dir.rsplit("/", 1)[-1]
    (dist / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.0.0"\n'
        "\n"
        "[tool.hatch.build.targets.wheel]\n"
        f'packages = ["src/{module}"]\n',
        encoding="utf-8",
    )
    return dist


def write_config(root: Path, body: str) -> Path:
    config = root / "mypy.ini"
    config.write_text(body, encoding="utf-8")
    return config


STRICT_BLOCK = "\n".join(
    f"{flag} = True"
    for flag in (
        "disallow_untyped_defs",
        "disallow_incomplete_defs",
        "disallow_untyped_calls",
        "disallow_untyped_decorators",
        "disallow_any_generics",
        "disallow_subclassing_any",
    )
)
NORMAL_BLOCK = STRICT_BLOCK.replace("True", "False")


def test_the_script_exists_and_is_executable_python() -> None:
    """Red first: before `scripts/qa/mypy_targets.py` landed, this failed."""
    assert SCRIPT.is_file(), f"{SCRIPT} does not exist"
    result = run_script("--help")
    assert result.returncode == 0, result.stderr


def test_check_refuses_a_distribution_with_no_mypy_section(tmp_path: Path) -> None:
    """A package added with no section must fail the gate, not slip through."""
    plant_distribution(tmp_path, "packages/trappoint-ghost", "trappoint_ghost")
    write_config(
        tmp_path,
        "[mypy]\nmypy_path =\n    packages/trappoint-ghost/src\n",
    )
    result = run_script("--check", "--root", str(tmp_path))
    assert result.returncode != 0, (
        "a distribution with no [mypy-trappoint_ghost.*] section was accepted\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "trappoint_ghost" in result.stdout + result.stderr


def test_check_refuses_a_distribution_missing_from_mypy_path(tmp_path: Path) -> None:
    """A section without a path entry type-checks nothing; that is not coverage."""
    plant_distribution(tmp_path, "packages/trappoint-ghost", "trappoint_ghost")
    write_config(
        tmp_path,
        f"[mypy]\nmypy_path =\n\n[mypy-trappoint_ghost.*]\n{STRICT_BLOCK}\n",
    )
    result = run_script("--check", "--root", str(tmp_path))
    assert result.returncode != 0, (
        "a distribution absent from mypy_path was accepted\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "mypy_path" in result.stdout + result.stderr


def test_check_refuses_a_substrate_distribution_at_the_normal_tier(tmp_path: Path) -> None:
    """`packages/trappoint-*` is the Apache substrate: strict is not optional."""
    plant_distribution(tmp_path, "packages/trappoint-ghost", "trappoint_ghost")
    write_config(
        tmp_path,
        "[mypy]\nmypy_path =\n    packages/trappoint-ghost/src\n"
        f"\n[mypy-trappoint_ghost.*]\n{NORMAL_BLOCK}\n",
    )
    result = run_script("--check", "--root", str(tmp_path))
    assert result.returncode != 0, (
        "a trappoint_* distribution at the normal tier was accepted\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "strict" in (result.stdout + result.stderr).lower()


def test_check_accepts_a_correctly_registered_distribution(tmp_path: Path) -> None:
    """The refusals above must be about the defect, not about synthetic trees."""
    plant_distribution(tmp_path, "packages/trappoint-ghost", "trappoint_ghost")
    write_config(
        tmp_path,
        "[mypy]\nmypy_path =\n    packages/trappoint-ghost/src\n"
        f"\n[mypy-trappoint_ghost.*]\n{STRICT_BLOCK}\n",
    )
    result = run_script("--check", "--root", str(tmp_path))
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_check_passes_on_the_real_tree() -> None:
    """The repository as it stands must satisfy its own gate."""
    result = run_script("--check")
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_every_distribution_on_disk_becomes_a_target() -> None:
    """One run, every distribution — the whole point of the exercise."""
    inventory = json.loads(run_script("--json").stdout)
    dist_dirs = {
        p.parent.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.glob("packages/*/pyproject.toml")
    } | {
        p.parent.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.glob("verticals/*/packages/*/pyproject.toml")
    }
    seen = {d["dir"] for d in inventory["distributions"]}
    assert dist_dirs <= seen, f"distributions on disk but not targeted: {dist_dirs - seen}"
    assert inventory["targets"], "no targets emitted"
    for target in inventory["targets"]:
        assert (REPO_ROOT / target).is_dir(), f"target does not exist: {target}"


def test_every_trappoint_distribution_is_strict() -> None:
    """The substrate's tier is data, and the data must say strict."""
    inventory = json.loads(run_script("--json").stdout)
    lax = [
        d["module"]
        for d in inventory["distributions"]
        if d["module"].startswith("trappoint_") and d["tier"] != "strict"
    ]
    assert not lax, f"substrate distributions not at the strict tier: {lax}"


def test_ratchet_records_every_distribution_and_the_mypy_version() -> None:
    """`qa/mypy-ratchet.json` is the published number; it must describe this tree."""
    ratchet_path = REPO_ROOT / "qa" / "mypy-ratchet.json"
    assert ratchet_path.is_file(), f"{ratchet_path} does not exist"
    ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
    assert ratchet["mypy_version"], "the ratchet does not say which mypy took the number"
    inventory = json.loads(run_script("--json").stdout)
    recorded = set(ratchet["distributions"])
    on_disk = {d["module"] for d in inventory["distributions"]}
    assert on_disk <= recorded, f"distributions with no ratchet entry: {on_disk - recorded}"
    for module, entry in ratchet["distributions"].items():
        assert entry["tier"] in {"strict", "normal", "pending"}, module
        assert "errors" in entry, module


def test_ratchet_refuses_an_increase(tmp_path: Path) -> None:
    """Red first, on a planted tree: a count that goes UP must fail the gate.

    The real ratchet cannot demonstrate this without breaking somebody else's
    file, so the demonstration happens on a distribution planted for the purpose:
    one module, one deliberate type error, a recorded count that is then lowered
    by hand.  If `--ratchet` accepts that, it accepts a regression.
    """
    dist = plant_distribution(tmp_path, "packages/trappoint-ghost", "trappoint_ghost")
    (dist / "src" / "trappoint_ghost" / "bad.py").write_text(
        '"""One error, on purpose."""\n\nWRONG: int = "not an int"\n', encoding="utf-8"
    )
    write_config(
        tmp_path,
        "[mypy]\npython_version = 3.13\nnamespace_packages = True\n"
        "explicit_package_bases = True\n"
        "mypy_path =\n    packages/trappoint-ghost/src\n"
        f"\n[mypy-trappoint_ghost.*]\n{STRICT_BLOCK}\n",
    )

    written = run_script("--write-ratchet", "--root", str(tmp_path))
    assert written.returncode == 0, written.stderr
    ratchet_path = tmp_path / "qa" / "mypy-ratchet.json"
    ratchet = json.loads(ratchet_path.read_text(encoding="utf-8"))
    assert ratchet["distributions"]["trappoint_ghost"]["errors"] == 1, ratchet

    held = run_script("--ratchet", "--root", str(tmp_path))
    assert held.returncode == 0, f"stdout:\n{held.stdout}\nstderr:\n{held.stderr}"

    ratchet["distributions"]["trappoint_ghost"]["errors"] = 0
    ratchet_path.write_text(json.dumps(ratchet, indent=2) + "\n", encoding="utf-8")
    risen = run_script("--ratchet", "--root", str(tmp_path))
    assert risen.returncode != 0, (
        f"the ratchet accepted 0 -> 1\nstdout:\n{risen.stdout}\nstderr:\n{risen.stderr}"
    )
    assert "REGRESSED" in risen.stdout + risen.stderr


@pytest.mark.slow
def test_one_run_covers_the_workspace_and_reports_no_unused_section() -> None:
    """The claim in one assertion: one invocation, nothing left over.

    ``unused section(s)`` is mypy telling you that a policy you wrote applies to
    nothing it looked at.  Two of those notes were how the split invocations hid
    from each other for months.
    """
    targets = run_script().stdout.split()
    assert targets, "no targets emitted"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(REAL_CONFIG),
            "--no-pretty",
            *targets,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    output = result.stdout + result.stderr
    assert "unused section(s)" not in output, output
    assert "checked" in output, output


@pytest.mark.parametrize("module", ["trappoint_testkit", "mainline_gate_svc"])
def test_the_two_distributions_this_wave_creates_are_pre_registered(module: str) -> None:
    """W2 and W6 land these; neither may arrive unchecked.

    Forward-declaring the section is what makes `--check` green the moment the
    package appears rather than a day later.  Until it appears mypy reports the
    section as unused, and `--check` says so out loud.
    """
    text = REAL_CONFIG.read_text(encoding="utf-8")
    assert f"[mypy-{module}.*]" in text, f"{module} has no section in mypy.ini"
