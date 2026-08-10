# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The workspace guard, proven RED before it is trusted GREEN.

`scripts/qa/check_workspace_members.py` exists because on 2026-08-10 `uv.lock` named
**seven** members against **thirty** distributions on disk. The guard now reports that the
two sets are equal. So would a guard whose `glob` matched nothing, whose lockfile parser
returned `[]`, or whose comparison was `set() == set()` — *"the tree and uv.lock agree: 0
distributions, 0 locked members"* is the same sentence with the same exit code.

PL-2: a suite that has never been red asserts nothing. Every branch of the guard is
therefore driven twice — once against a synthetic workspace built specifically to break
it, and once against this repository. The synthetic half is what makes the green half mean
something.

The `done_when` clause is driven literally, at the bottom: delete a member from `uv.lock`
and the checker must exit non-zero *naming that member*. Not "exit non-zero" — a guard that
fails for the wrong reason is a guard that will pass for the wrong reason.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "qa" / "check_workspace_members.py"
LOCK = REPO_ROOT / "uv.lock"
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"

#: The measured member count on the day the drift was closed. A floor, not an equality:
#: the whole point of the globs is that a new distribution needs no edit here, and a test
#: that had to be edited by every package author would be edited without being read.
MEMBERS_AT_REPAIR = 30

#: The distribution this worker created, and the one whose absence caused the drift to be
#: noticed at all. If it ever falls out of the workspace again, this file says so by name.
CORPUS = "mainline-corpus"


def _load_guard() -> ModuleType:
    """Import the script by path; `scripts/` is deliberately not an importable package."""
    spec = importlib.util.spec_from_file_location("_check_workspace_members", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `dataclasses` resolves a class's own module out of
    # `sys.modules` while processing it, and a module that is not there yet fails with
    # `'NoneType' object has no attribute '__dict__'`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


SYNTHETIC_ROOT_PYPROJECT = """\
[tool.uv.workspace]
members = ["packages/*", "verticals/*/packages/*"]
exclude = ["**/node_modules"]
"""

SYNTHETIC_LOCK = """\
version = 1
revision = 3
requires-python = ">=3.13"

[manifest]
members = [
    "alpha-dist",
    "beta-dist",
]
"""


def make_distribution(root: Path, project: str, name: str) -> Path:
    """Create a minimal workspace distribution: a directory with a named `pyproject.toml`."""
    package = root / project
    package.mkdir(parents=True, exist_ok=True)
    (package / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    return package


@pytest.fixture
def synthetic(tmp_path: Path) -> Path:
    """A two-member workspace whose tree and lock agree. Every RED test breaks it."""
    make_distribution(tmp_path, "packages/alpha", "alpha-dist")
    make_distribution(tmp_path, "verticals/demo/packages/beta", "beta-dist")
    (tmp_path / "pyproject.toml").write_text(SYNTHETIC_ROOT_PYPROJECT, encoding="utf-8")
    (tmp_path / "uv.lock").write_text(SYNTHETIC_LOCK, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# RED first. The synthetic workspace, broken one way at a time.
# ---------------------------------------------------------------------------


def test_the_synthetic_baseline_is_green_or_nothing_below_means_anything(
    synthetic: Path,
) -> None:
    """The control. If this were red, every RED test below would pass for free."""
    report = guard.check(synthetic)
    assert report.ok, guard.render(report, synthetic / "uv.lock")
    assert report.tree_members == 2
    assert report.lock_members == 2


def test_a_distribution_on_disk_and_absent_from_the_lock_is_refused(synthetic: Path) -> None:
    """The drift that actually happened: 23 packages landed, the lock never moved."""
    make_distribution(synthetic, "packages/gamma", "gamma-dist")

    report = guard.check(synthetic)

    assert not report.ok
    assert [member.name for member in report.missing_from_lock] == ["gamma-dist"]
    rendered = guard.render(report, synthetic / "uv.lock")
    assert "gamma-dist" in rendered
    assert "packages/gamma" in rendered
    assert "uv lock" in rendered


def test_a_lock_member_with_no_distribution_on_disk_is_refused(synthetic: Path) -> None:
    """The reverse drift: a package renamed or deleted, the lock still naming the old one."""
    lock = synthetic / "uv.lock"
    lock.write_text(SYNTHETIC_LOCK.replace('"beta-dist",', '"beta-dist",\n    "ghost-dist",'))

    report = guard.check(synthetic)

    assert not report.ok
    assert report.missing_from_tree == ["ghost-dist"]
    assert "ghost-dist" in guard.render(report, lock)


def test_both_directions_are_reported_in_one_run(synthetic: Path) -> None:
    """A guard that stopped at the first finding would need N runs to clear N drifts."""
    make_distribution(synthetic, "packages/gamma", "gamma-dist")
    lock = synthetic / "uv.lock"
    lock.write_text(SYNTHETIC_LOCK.replace('"beta-dist",', '"beta-dist",\n    "ghost-dist",'))

    report = guard.check(synthetic)

    assert [member.name for member in report.missing_from_lock] == ["gamma-dist"]
    assert report.missing_from_tree == ["ghost-dist"]


def test_a_pyproject_with_no_project_name_is_reported_not_dropped(synthetic: Path) -> None:
    """A nested virtual workspace cannot be locked; saying nothing about it is the bug."""
    orphan = synthetic / "packages/delta"
    orphan.mkdir(parents=True)
    (orphan / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n", encoding="utf-8")

    report = guard.check(synthetic)

    assert not report.ok
    assert report.unnamed == ["packages/delta"]
    assert "packages/delta" in guard.render(report, synthetic / "uv.lock")


def test_the_globs_are_read_from_the_root_and_not_hardcoded(synthetic: Path) -> None:
    """Narrow the real globs and the guard must follow them, or it guards a fiction."""
    (synthetic / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["packages/*"]\n', encoding="utf-8"
    )

    report = guard.check(synthetic)

    assert report.globs == ["packages/*"]
    # `beta-dist` is no longer admitted by the globs, so the lock now names a member the
    # workspace does not contain. A guard carrying its own copy of the globs would have
    # reported `ok` here.
    assert not report.ok
    assert report.missing_from_tree == ["beta-dist"]


def test_an_excluded_directory_is_not_a_member(synthetic: Path) -> None:
    """`**/node_modules`: a pnpm tree can contain a `pyproject.toml` and must not count."""
    make_distribution(synthetic, "packages/node_modules", "vendored-dist")

    report = guard.check(synthetic)

    assert report.ok, guard.render(report, synthetic / "uv.lock")
    assert report.tree_members == 2


# ---------------------------------------------------------------------------
# The exit code and the stderr path, which are the only things CI reads
# ---------------------------------------------------------------------------


def test_main_exits_non_zero_on_drift(synthetic: Path) -> None:
    make_distribution(synthetic, "packages/gamma", "gamma-dist")
    assert guard.main(["--repo-root", str(synthetic)]) == 1


def test_main_exits_zero_when_the_sets_are_equal(synthetic: Path) -> None:
    assert guard.main(["--repo-root", str(synthetic)]) == 0


def test_main_exits_two_when_the_lockfile_is_absent(synthetic: Path) -> None:
    """Absent input is not the same verdict as drift, and must not be reported as one."""
    (synthetic / "uv.lock").unlink()
    assert guard.main(["--repo-root", str(synthetic)]) == 2


def test_main_exits_two_when_the_lockfile_has_no_manifest(synthetic: Path) -> None:
    (synthetic / "uv.lock").write_text('version = 1\n[[package]]\nname = "x"\n', encoding="utf-8")
    assert guard.main(["--repo-root", str(synthetic)]) == 2


# ---------------------------------------------------------------------------
# GREEN, against this repository
# ---------------------------------------------------------------------------


def test_this_repository_tree_and_lock_agree() -> None:
    report = guard.check(REPO_ROOT)
    assert report.ok, guard.render(report, LOCK)
    assert report.tree_members >= MEMBERS_AT_REPAIR
    assert report.lock_members == report.tree_members


def test_the_lock_names_every_distribution_the_globs_admit() -> None:
    """Stated as sets, so a failure prints the difference rather than two counts."""
    globs, exclude = guard.read_workspace_globs(ROOT_PYPROJECT)
    tree, unnamed = guard.discover_tree_members(REPO_ROOT, globs, exclude)
    assert unnamed == []
    assert {member.name for member in tree} == set(guard.read_lock_members(LOCK))


def test_mainline_corpus_is_a_member_of_both() -> None:
    """The distribution the drift was noticed through. It had 94 modules and no packaging."""
    globs, exclude = guard.read_workspace_globs(ROOT_PYPROJECT)
    tree, _ = guard.discover_tree_members(REPO_ROOT, globs, exclude)
    by_name = {member.name: member for member in tree}
    assert CORPUS in by_name
    assert by_name[CORPUS].path == "verticals/mainline/packages/mainline-corpus"
    assert CORPUS in guard.read_lock_members(LOCK)


def test_the_seven_member_era_is_over() -> None:
    """The literal historical fact, asserted so that a regression to it is named as one."""
    seven = {
        "mainline-boundary",
        "mainline-domain",
        "mainline-recall-agent",
        "trappoint-conformance",
        "trappoint-jcs",
        "trappoint-migrate",
        "trappoint-recall",
    }
    locked = set(guard.read_lock_members(LOCK))
    assert seven < locked
    assert len(locked - seven) >= 23


# ---------------------------------------------------------------------------
# The `done_when` clause, driven literally
# ---------------------------------------------------------------------------


def test_deleting_a_member_from_the_real_lock_makes_the_guard_refuse(tmp_path: Path) -> None:
    """`mainline-corpus` deleted from a copy of the real `uv.lock`: exit 1, named."""
    original = LOCK.read_text(encoding="utf-8")
    needle = f'\n    "{CORPUS}",'
    assert needle in original, "uv.lock no longer lists mainline-corpus in [manifest] members"

    doctored = tmp_path / "uv.lock"
    doctored.write_text(original.replace(needle, "", 1), encoding="utf-8")

    report = guard.check(REPO_ROOT, doctored)

    assert not report.ok
    assert [member.name for member in report.missing_from_lock] == [CORPUS]
    assert guard.main(["--repo-root", str(REPO_ROOT), "--lock", str(doctored)]) == 1


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
    assert payload["missing_from_lock"] == []
    assert payload["missing_from_tree"] == []
    assert payload["unnamed"] == []
    assert payload["tree_members"] >= MEMBERS_AT_REPAIR


# ---------------------------------------------------------------------------
# The two root-`pyproject.toml` repairs that shipped alongside the lock, asserted
# here because nothing else in the suite would notice them silently reverting
# ---------------------------------------------------------------------------


def test_testpaths_reaches_the_verticals() -> None:
    """146 tests under `verticals/*/packages/*/tests` had never run in a default pytest."""
    config = tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))
    ini = config["tool"]["pytest"]["ini_options"]
    assert "verticals/*/packages/*/tests" in ini["testpaths"]
    assert "tests" in ini["testpaths"]
    assert "packages" in ini["testpaths"]


def test_the_timeout_method_is_thread_because_windows_has_no_sigalrm() -> None:
    """pytest-timeout's default `signal` method is unavailable on the dev platform."""
    config = tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))
    assert config["tool"]["pytest"]["ini_options"]["timeout_method"] == "thread"


def test_the_dev_floors_are_not_below_what_is_installed() -> None:
    """A floor three majors below the resolved version is a comment, not a constraint."""
    config = tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))
    floors = dict(
        entry.split(">=", 1) for entry in config["dependency-groups"]["dev"] if ">=" in entry
    )
    assert tuple(int(p) for p in floors["pytest"].split(".")) >= (9, 1)
    assert tuple(int(p) for p in floors["mypy"].split(".")) >= (2, 3)
    assert tuple(int(p) for p in floors["ruff"].split(".")) >= (0, 16)


# ---------------------------------------------------------------------------
# `mainline-corpus` is not only locked, it is USABLE — which is a different claim
# ---------------------------------------------------------------------------
#
# The distribution is 94 Python modules and 19 non-Python files, and the second number
# is the one that can silently go wrong. `gazetteer/__init__.py` and `prompts/__init__.py`
# both resolve their data with `Path(__file__).resolve().parent`, not
# `importlib.resources`, so a build that shipped only `*.py` would import perfectly and
# then fail at first use — four stages into a corpus generation, which is the most
# expensive place to find out. "hatchling includes data files by default" is a sentence
# about hatchling; these are sentences about this build.


def test_the_workspace_venv_imports_the_corpus_with_no_pythonpath() -> None:
    """The `done_when` clause: a fresh `uv sync` and no `PYTHONPATH` in the shell.

    Run in a subprocess with `PYTHONPATH` explicitly removed, because this test session
    may well have inherited one — and a test that passes because of the developer's shell
    profile is exactly the situation `mainline-corpus` was in for its whole life.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    probe = (
        "import mainline_corpus, trappoint_testkit, mainline_gate_svc, "
        "trappoint_model, mainline_mutation; print(mainline_corpus.__version__)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=env,
        cwd=str(REPO_ROOT.parent),  # not the repo root: no accidental `src` on sys.path
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "0.1.0"


def test_every_gazetteer_file_is_beside_the_installed_module() -> None:
    """`checksum()` reads all eleven YAML files and raises by name if one is missing."""
    from mainline_corpus import gazetteer

    digest = gazetteer.checksum()
    assert len(digest) == 64
    for name, path in gazetteer.iter_files():
        assert path.is_file(), f"gazetteer file {name!r} did not ship beside the module"


def test_every_prompt_file_is_beside_the_installed_module() -> None:
    """Four prompt texts, parsed rather than merely stat-ed."""
    from mainline_corpus import prompts

    loaded = prompts.load_all()
    assert tuple(prompt.kind for prompt in loaded) == prompts.KINDS


def test_the_top_level_package_does_not_drag_in_its_subpackages() -> None:
    """`__init__.py` is inert on purpose; `mainline_boundary.greps` only wants the path.

    Asserted by importing it in a clean interpreter and checking that neither PyYAML nor
    Jinja2 was pulled in as a side effect.
    """
    probe = (
        "import sys, mainline_corpus; "
        "print(sorted(m for m in ('yaml', 'jinja2') if m in sys.modules))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "[]"


def _uv_executable() -> str | None:
    """`uv` from PATH, else the workspace venv's. None when it is installed nowhere."""
    found = shutil.which("uv")
    if found:
        return found
    for candidate in (
        REPO_ROOT / ".venv" / "Scripts" / "uv.exe",
        REPO_ROOT / ".venv" / "bin" / "uv",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def test_the_built_wheel_carries_the_data_files(tmp_path: Path) -> None:
    """The strong form of the two tests above: assert it of the artefact, not the checkout.

    A `uv sync` installs workspace members as editable, so every path assertion above is
    ultimately an assertion about the source tree. This one builds the wheel a stranger
    would install and looks inside it.

    Skipped with a reason rather than faked when `uv` is absent — which on 2026-08-10 was
    this machine's actual state, and is why the skip reason names the fix.
    """
    uv = _uv_executable()
    if uv is None:
        pytest.skip("uv is not installed; cannot build the wheel (fix: pip install uv)")

    completed = subprocess.run(
        [uv, "build", "--package", "mainline-corpus", "--wheel", "--out-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        cwd=str(REPO_ROOT),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheels = sorted(tmp_path.glob("mainline_corpus-*.whl"))
    assert len(wheels) == 1, [w.name for w in wheels]
    names = set(zipfile.ZipFile(wheels[0]).namelist())

    from mainline_corpus import gazetteer, prompts

    expected = {f"mainline_corpus/gazetteer/{name}.yaml" for name in gazetteer.FILES}
    expected |= {f"mainline_corpus/prompts/{kind}.md" for kind in prompts.KINDS}
    expected |= {"mainline_corpus/py.typed", "mainline_corpus/__init__.py"}

    missing = sorted(expected - names)
    assert not missing, f"the wheel imports but cannot run; absent from it: {missing}"
