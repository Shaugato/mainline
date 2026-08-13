# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Controls for ``scripts/ci/cluster_lane_report.py`` — the lane's claim about itself.

WHY THIS FILE EXISTS, IN ONE SENTENCE FROM THE FILE IT CONTROLS.

``.github/workflows/cluster-tests.yml`` says of the report program:

    It also refuses a run whose JUnit XML records failures while its caller claims pytest
    exited 0 — which is the one rewiring that would let a fully-inventoried red run
    present as green. **Both properties are exercised by controls; see that file.**

Measured on 2026-08-14, that last sentence was FALSE: ``tests/ci/`` held exactly one file,
``test_demo_seed_is_frozen.py``, which is about the demo seed and says nothing about the
report. A report nobody can falsify is decoration, and a workflow comment claiming controls
that do not exist is worse than no comment — it spends the reader's trust on nothing. This
file is that sentence made true.

WHAT A CONTROL HAS TO DO HERE TO COUNT.

A test that asserts "the program refuses X" while the program would refuse X even with the
refusal deleted is not a control; it is a coincidence with a docstring. So **every property
below is demonstrated by MUTATION**: the real source is read off disk, one named anchor is
replaced by a version of itself with that property removed, the mutant is loaded as a live
module, and the same scenario is run through both. The control asserts

  * the REAL program gives the safe answer, and
  * the MUTANT gives the unsafe one.

If the second half ever stops holding, the assertion above it has stopped meaning anything,
and the test says so in as many words. ``_mutate`` refuses an anchor that does not appear
**exactly once** in the source, so a refactor cannot quietly turn these demonstrations into
no-ops: the day somebody reshapes ``cluster_lane_report.py``, these tests go red asking to
be re-anchored rather than passing while testing a mutation that never applied.

THE SIX PROPERTIES, and which control covers each.

1. ``--pytest-rc N`` IS NOT ADVISORY — a non-zero pytest status is final regardless of how
   the node ids classify, and the program exits with *that* status rather than merely with
   *a* non-zero one.  ``test_a_fully_inventoried_red_run_still_exits_with_pytests_status``
   and ``test_the_exit_status_is_pytests_own_value_not_just_non_zero``.
2. THE FLOOR refuses a run that obtained no cluster and skipped everything, and each half
   of it is load-bearing on its own.  ``test_the_floor_refuses_a_run_that_reached_no_cluster``,
   ``test_the_executed_floor_fires_on_its_own``, ``test_the_skip_ceiling_fires_on_its_own``.
2b. A gate that refuses everything is not a gate, so the floor has a POSITIVE control too:
   ``test_a_green_run_over_the_floor_is_the_only_thing_that_exits_zero``.
3. THE CEILING fails when an inventoried node id PASSES.
   ``test_the_ceiling_fails_when_an_inventoried_node_id_passes``.
4. A ``classname`` that resolves to no file on disk is a HARD FAILURE, not a silent
   non-match.  ``test_a_classname_that_names_no_file_is_a_hard_failure``.
5. An ``unstable`` entry with no measurement behind it is refused, and so is one that failed
   every run it was seen in.  ``test_an_unstable_entry_without_a_measurement_is_refused``,
   ``test_an_unstable_entry_that_failed_every_run_is_refused``.
6. A run whose XML records failures while the caller claims ``rc=0`` is refused — **in its
   summary attributes AND in its body**.  ``test_a_run_that_lost_pytests_status_is_refused``
   and ``test_a_body_full_of_failures_under_a_clean_summary_is_refused``.
7. EVERY ``Refusal`` PATH IS REACHED BY A SCENARIO, and none of them exits 0 or softens
   pytest's own status.  ``test_every_refusal_path_refuses_the_report`` and
   ``test_a_refusal_never_exits_zero_and_never_softens_pytests_status``, which sweep the
   eighteen malformed inventories and documents enumerated in ``REFUSALS``.
8. THE CLASSIFICATION IS A MESSAGE, NEVER THE VERDICT — a NEW, uninventoried failure is
   named in the log, and the exit status is still pytest's.
   ``test_a_new_failure_is_named_but_the_verdict_is_still_pytests``.

THE ONE PLACE A CONTROL PROVED THE PROGRAM WRONG, recorded because it is the only reason
this file was allowed to edit the program at all.

``test_a_body_full_of_failures_under_a_clean_summary_is_refused`` failed against the
program as committed at ``e944407``. Guard 0 read ``run["failures"] or run["errors"]`` —
the ``<testsuite>`` *summary attributes* — while the thing it is defending is the *body*:
a JUnit document whose summary says ``failures="0"`` while its ``<testcase>`` children
carry ``<failure>`` elements went through every gate and exited 0, provided the node ids
were inventoried. That is precisely the shape guard 0 exists to refuse, arriving through
the half of the document guard 0 was not reading. One clause was added
(``or run["bad"]``); nothing was relaxed. Against every honest pytest run the clause is
dead weight — pytest computes those attributes from the same cases — so the fix cannot
move the verdict of any real run, which is the property that made it safe to land.

WHAT THIS FILE DELIBERATELY DOES NOT DO.

It does not read, assert over, or edit ``qa/cluster-known-red.json``'s *contents* beyond
checking that the committed file still LOADS. The inventory's ``groups`` list is a ceiling
expected to be deleted rather than edited, it is owned by the cluster lane, and a control
that pinned its membership would be a second ceiling that has to be lowered twice.
"""

from __future__ import annotations

import json
import pathlib
from types import ModuleType
from typing import Any, Final

import pytest

#: ``tests/ci/<this file>`` -> the repository root. Asserted below rather than assumed.
REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]

REPORT_PATH: Final = REPO_ROOT / "scripts/ci/cluster_lane_report.py"
WORKFLOW_PATH: Final = REPO_ROOT / ".github/workflows/cluster-tests.yml"
COMMITTED_INVENTORY: Final = REPO_ROOT / "qa/cluster-known-red.json"

SCHEMA: Final = "mainline.qa.cluster-known-red/1"


def _source() -> str:
    assert REPORT_PATH.is_file(), (
        f"{REPORT_PATH} does not exist. This file is the control set for that program; if "
        "the program moved, these controls move with it in the same commit. A control set "
        "that cannot find its subject must fail, never skip."
    )
    return REPORT_PATH.read_text(encoding="utf-8")


def _load(source: str, name: str) -> ModuleType:
    """Execute ``source`` as a fresh module. Never registered in ``sys.modules``."""
    module = ModuleType(name)
    module.__file__ = str(REPORT_PATH)
    exec(compile(source, str(REPORT_PATH), "exec"), module.__dict__)  # noqa: S102
    return module


def real() -> ModuleType:
    """The program exactly as it is committed."""
    return _load(_source(), "cluster_lane_report_real")


def mutate(anchor: str, replacement: str, name: str) -> ModuleType:
    """The program with one named property removed.

    The anchor must appear EXACTLY ONCE. A mutation that fails to apply produces a mutant
    identical to the original, and a negative control against an unmutated program passes
    for the wrong reason — which is the failure mode this whole file exists to refuse.
    """
    source = _source()
    found = source.count(anchor)
    assert found == 1, (
        f"the mutation anchor for {name!r} appears {found} time(s) in "
        f"{REPORT_PATH.name}, expected exactly 1.\n"
        "\n"
        "THIS IS NOT A FAILURE OF THE PROGRAM. It means cluster_lane_report.py was "
        "reshaped and this control's demonstration no longer applies to it. Re-anchor the "
        "mutation against the new text IN THE SAME COMMIT. Do not delete the "
        "demonstration: an assertion with no demonstration behind it cannot tell you "
        "whether the property it names is still enforced.\n"
        "\n"
        f"anchor sought:\n{anchor}"
    )
    return _load(source.replace(anchor, replacement), name)


# ── the fixtures the scenarios are built from ──────────────────────────────────────────
#
# Both are written as FILES rather than as objects, because that is the program's real
# interface: it is handed two paths by a shell step. A control that called `report()` with
# hand-built dicts would skip `load_inventory` and `read_run`, which is where four of the
# six properties live.


def _suite_root(tmp_path: pathlib.Path, *modules: str) -> pathlib.Path:
    """A stand-in for the demo-api tests directory, holding only empty module files.

    ``resolve_nodeid`` resolves a JUnit ``classname`` against the FILESYSTEM, so these
    controls need real files and nothing else about them. Using a temporary root rather
    than the real suite keeps every scenario independent of what the demo-api tree happens
    to contain this week — these controls must not go red because a test module was added.
    """
    root = tmp_path / "suite"
    root.mkdir(exist_ok=True)
    for module in modules:
        (root / f"{module}.py").write_text("", encoding="utf-8")
    return root


def _junit(
    path: pathlib.Path,
    cases: list[tuple[str, str, str]],
    *,
    tests: int | None = None,
    skipped: int | None = None,
    failures: int | None = None,
    errors: int | None = None,
) -> pathlib.Path:
    """Write a JUnit document. Each case is ``(classname, name, outcome)``.

    The four summary counts default to being DERIVED from the cases, which is what pytest
    does. They are overridable on purpose: the summary disagreeing with the body is a
    scenario one of the controls below is entirely about, and a builder that could not
    express it could not test it.
    """
    body: list[str] = []
    derived = {"skipped": 0, "failures": 0, "errors": 0}
    for classname, name, outcome in cases:
        child = {
            "pass": "",
            "skip": '<skipped type="pytest.skip" message="no cluster"/>',
            "fail": '<failure message="assert 0">boom</failure>',
            "error": '<error message="setup">boom</error>',
        }[outcome]
        if outcome == "skip":
            derived["skipped"] += 1
        elif outcome == "fail":
            derived["failures"] += 1
        elif outcome == "error":
            derived["errors"] += 1
        body.append(f'<testcase classname="{classname}" name="{name}">{child}</testcase>')

    attrs = {
        "tests": len(cases) if tests is None else tests,
        "skipped": derived["skipped"] if skipped is None else skipped,
        "failures": derived["failures"] if failures is None else failures,
        "errors": derived["errors"] if errors is None else errors,
    }
    rendered = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    path.write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n<testsuite name="pytest" {rendered}>'
        + "".join(body)
        + "</testsuite>\n",
        encoding="utf-8",
    )
    return path


def _inventory(
    path: pathlib.Path,
    *,
    groups: list[dict[str, Any]] | None = None,
    unstable: list[dict[str, Any]] | None = None,
    min_executed: int = 440,
    max_skipped: int = 1,
    schema: str = SCHEMA,
) -> pathlib.Path:
    path.write_text(
        json.dumps(
            {
                "schema": schema,
                "floor": {"min_executed": min_executed, "max_skipped": max_skipped},
                "groups": groups or [],
                "unstable": unstable or [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _group(slug: str, *nodeids: str) -> dict[str, Any]:
    return {"slug": slug, "cause": "a cause, so the schema accepts it", "nodeids": list(nodeids)}


def _run(
    module: ModuleType,
    *,
    junit: pathlib.Path,
    known: pathlib.Path,
    suite_root: pathlib.Path,
    pytest_rc: int = 0,
    capsys: pytest.CaptureFixture[str] | None = None,
) -> tuple[int, str]:
    """Drive ``main()`` the way the workflow step drives it, and return (exit code, stdout)."""
    code = module.main(
        [
            "--junit",
            str(junit),
            "--known",
            str(known),
            "--suite-root",
            str(suite_root),
            "--pytest-rc",
            str(pytest_rc),
        ]
    )
    printed = capsys.readouterr().out if capsys is not None else ""
    return code, printed


def _passing_cases(count: int, classname: str = "tests.test_alpha") -> list[tuple[str, str, str]]:
    return [(classname, f"test_{index}", "pass") for index in range(count)]


# ── 0. the control set can find what it controls ───────────────────────────────────────


def test_the_repository_root_resolved_to_the_right_place() -> None:
    """A wrong root would make every path below miss, and a control that reads nothing passes."""
    assert (REPO_ROOT / "pyproject.toml").is_file(), (
        f"{REPO_ROOT} is not this repository's root; every path in this file is relative to it."
    )
    assert REPORT_PATH.is_file()
    assert WORKFLOW_PATH.is_file()


def test_the_committed_inventory_still_loads() -> None:
    """The lane cannot report at all if ``qa/cluster-known-red.json`` stops parsing.

    This is the one control that reads the committed inventory, and it reads it for
    LOADABILITY only. Its ``groups`` list is a ceiling that must reach empty; a control
    pinning its membership would have to be lowered every time the ceiling was, which is
    how a ceiling acquires a second owner and stops falling.
    """
    inventory = real().load_inventory(COMMITTED_INVENTORY)
    assert isinstance(inventory["floor"]["min_executed"], int)
    assert isinstance(inventory["floor"]["max_skipped"], int)


# ── 1. --pytest-rc is not advisory ─────────────────────────────────────────────────────

#: Removing the finality of ``--pytest-rc``: the program falls back to deciding on the
#: classification alone, which is exactly the state in which adding a node id to the
#: inventory would turn a red run green.
_RC_FINAL_ANCHOR: Final = "\n        return args.pytest_rc\n"
_RC_ADVISORY: Final = "\n        return 1 if verdicts else 0\n"
_RC_FLATTENED: Final = "\n        return 1\n"


def test_a_fully_inventoried_red_run_still_exits_with_pytests_status(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The suppression attempt, run end to end: every failure inventoried, pytest red.

    This is the doctored-inventory scenario the program's docstring promises it survives.
    Both failing node ids are named in ``groups`` with a cause, so the classification half
    produces no verdict at all — and the run still exits 2, because pytest did.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(
        tmp_path / "j.xml",
        [
            ("tests.test_alpha", "test_one", "fail"),
            ("tests.test_alpha", "test_two", "error"),
            *_passing_cases(500),
        ],
    )
    known = _inventory(
        tmp_path / "k.json",
        groups=[
            _group(
                "doctored",
                f"{suite.as_posix()}/test_alpha.py::test_one",
                f"{suite.as_posix()}/test_alpha.py::test_two",
            )
        ],
    )

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=2, capsys=capsys
    )
    assert code == 2, (
        "pytest exited 2 and every failing node id was inventoried; the program must still "
        f"exit 2. It exited {code}.\n{printed}"
    )
    assert "known    [doctored]" in printed, (
        "the failures should still be CLASSIFIED and printed - the inventory changes the "
        f"sentence beside a failure, never the verdict.\n{printed}"
    )

    mutant = mutate(_RC_FINAL_ANCHOR, _RC_ADVISORY, "rc_advisory")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=2, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED, which means the assertion above proves nothing. With "
        "`--pytest-rc` made advisory, this fully-inventoried red run was supposed to "
        f"present as GREEN (exit 0); it exited {mutant_code}. Either something else is now "
        "carrying the property - in which case say so here and re-aim this control at it - "
        "or the scenario stopped reaching the code path it was built for."
    )


def test_the_exit_status_is_pytests_own_value_not_just_non_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "Exits with pytest's status" is a stronger claim than "exits non-zero", and it is
    the claim the workflow makes.

    pytest's exit codes are a vocabulary, not a flag: 1 is *tests failed*, 2 is
    *interrupted*, 3 *internal error*, 4 *usage error*, 5 *no tests collected*. A lane that
    collapsed all of them to 1 would report a runner that was cancelled and a suite that
    failed as the same event. The mutant here does exactly that, and it is caught.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(500))
    known = _inventory(tmp_path / "k.json")

    for status in (2, 3, 4, 5):
        code, _ = _run(
            module, junit=junit, known=known, suite_root=suite, pytest_rc=status, capsys=capsys
        )
        assert code == status, f"pytest exited {status}; the lane exited {code}"

    mutant = mutate(_RC_FINAL_ANCHOR, _RC_FLATTENED, "rc_flattened")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=5, capsys=capsys
    )
    assert mutant_code == 1, (
        "THE DEMONSTRATION FAILED. A program that returned a constant 1 instead of pytest's "
        f"own status was supposed to answer 1 for a run pytest exited 5 on; it answered "
        f"{mutant_code}."
    )


def test_a_refusal_is_never_quieter_than_pytest(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """When the report cannot be produced at all, the run is not green and not downgraded.

    Two halves, and the second is the one that matters: a refusal on a run pytest exited 4
    on must exit 4, not 1. A program that flattened its refusals to 1 would be *quieter*
    than pytest about a usage error, and the only thing worse than a lane that fails is a
    lane that fails less loudly than the thing it wraps.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    known = _inventory(tmp_path / "k.json")
    missing = tmp_path / "never-written.xml"

    code, printed = _run(
        module, junit=missing, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"a run with no JUnit report at all must not exit 0; it exited {code}"
    assert "the cluster lane cannot be reported" in printed
    assert "pytest wrote no JUnit report" in printed

    code, _ = _run(module, junit=missing, known=known, suite_root=suite, pytest_rc=4, capsys=capsys)
    assert code == 4, (
        f"a refusal on a run pytest exited 4 on must exit 4, not {code}: the report may only "
        "ADD a failure, never soften one."
    )


# ── 2. the floor ───────────────────────────────────────────────────────────────────────

_FLOOR_EXECUTED_ANCHOR: Final = '    if run["executed"] < floor["min_executed"]:'
_FLOOR_SKIPPED_ANCHOR: Final = '    if run["skipped"] > floor["max_skipped"]:'
_DISABLED: Final = "    if False:  # MUTANT: this property removed"


def test_the_floor_refuses_a_run_that_reached_no_cluster(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The defect this lane was built around: pytest exits 0 when every test skips.

    ``release-proof.yml:219-320`` records it live in this repository. A cluster lane whose
    container failed to start runs a suite of skips, and pytest hands back 0. Both halves
    of the floor fire here, so the mutant removes both — a mutant that removed only one
    would still be caught by the other, and would demonstrate nothing.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(
        tmp_path / "j.xml", [("tests.test_alpha", f"test_{i}", "skip") for i in range(186)]
    )
    known = _inventory(tmp_path / "k.json")

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, (
        "186 tests collected, 186 skipped, nothing executed, pytest exited 0 - the lane "
        f"must refuse this run. It exited {code}.\n{printed}"
    )
    assert "the cluster lane proved nothing" in printed
    assert "the cluster lane skipped" in printed

    both_removed = _source()
    both_removed = both_removed.replace(_FLOOR_EXECUTED_ANCHOR, _DISABLED, 1)
    both_removed = both_removed.replace(_FLOOR_SKIPPED_ANCHOR, _DISABLED, 1)
    assert both_removed.count(_DISABLED) == 2, (
        "the floor's two anchors did not both apply; re-anchor them in the same commit that "
        "reshaped cluster_lane_report.py."
    )
    mutant = _load(both_removed, "floor_removed")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED. With both halves of the floor removed, a lane that "
        "obtained no cluster and skipped its entire suite was supposed to present as GREEN; "
        f"it exited {mutant_code}. The assertion above is therefore not evidence that the "
        "floor is what refuses this run."
    )


def test_the_executed_floor_fires_on_its_own(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that executed too little while skipping almost nothing — a partial collection.

    This is not the same event as a wall of skips. When the suite fails to IMPORT on the
    runner - ``mainline-demo-api`` is deliberately not a workspace member and puts its own
    ``src`` on ``sys.path`` - the tests are not skipped, they are absent. Only the
    ``min_executed`` half sees that, so it is demonstrated alone.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(30))
    known = _inventory(tmp_path / "k.json", min_executed=440, max_skipped=1)

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"30 executed against a floor of 440 must refuse; exited {code}\n{printed}"
    assert "the cluster lane proved nothing" in printed
    assert "the cluster lane skipped" not in printed, (
        "only the executed floor should have fired here; if the skip ceiling fired too, this "
        "scenario no longer isolates the half it claims to."
    )

    mutant = mutate(_FLOOR_EXECUTED_ANCHOR, _DISABLED, "executed_floor_removed")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the `min_executed` floor removed, a run of 30 tests "
        f"was supposed to present as green; it exited {mutant_code}."
    )


def test_the_skip_ceiling_fires_on_its_own(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that executed plenty and skipped more than one — the cluster went away mid-run.

    ``max_skipped`` is 1 in the committed inventory and the one skip it allows is named:
    ``test_gate_run.py``'s ``jsonschema is not a workspace dependency``, which has nothing
    to do with the database. Anything above that is a suite that could not reach the
    cluster this job started, and a skip is the same green tick as a pass on a dashboard.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    cases = _passing_cases(600) + [
        ("tests.test_alpha", f"test_skip_{i}", "skip") for i in range(13)
    ]
    junit = _junit(tmp_path / "j.xml", cases)
    known = _inventory(tmp_path / "k.json", min_executed=440, max_skipped=1)

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"13 skips against a ceiling of 1 must refuse; exited {code}\n{printed}"
    assert "the cluster lane skipped" in printed
    assert "the cluster lane proved nothing" not in printed, (
        "only the skip ceiling should have fired here; 600 tests executed against a floor of 440."
    )

    mutant = mutate(_FLOOR_SKIPPED_ANCHOR, _DISABLED, "skip_ceiling_removed")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the skip ceiling removed, a run that skipped 13 "
        f"tests was supposed to present as green; it exited {mutant_code}."
    )


def test_a_green_run_over_the_floor_is_the_only_thing_that_exits_zero(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The positive control, without which every assertion above is satisfied by a program
    that always exits 1.

    A gate that refuses everything is not a gate. This is the run that must pass: over the
    floor, under the skip ceiling, nothing failing, nothing inventoried, pytest green.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(
        tmp_path / "j.xml", [*_passing_cases(500), ("tests.test_alpha", "test_skip", "skip")]
    )
    known = _inventory(tmp_path / "k.json", min_executed=440, max_skipped=1)

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 0, f"a healthy green run must exit 0; it exited {code}\n{printed}"
    assert "500 executed" in printed


# ── 3. the ceiling ─────────────────────────────────────────────────────────────────────

_CEILING_ANCHOR: Final = '    fixed = sorted(nodeid for nodeid in known if nodeid in run["passed"])'
_CEILING_BLINDED: Final = "    fixed = []  # MUTANT: the ceiling never sees a fixed test"


def test_the_ceiling_fails_when_an_inventoried_node_id_passes(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A known-red test that PASSES is a defect somebody fixed and did not record.

    The inventory is a ceiling that must reach empty. A ceiling nobody is made to lower is
    a ceiling that never falls, which is how a list of "known failures" outlives the
    failures and becomes a list of tests nobody looks at. Note what this control asserts
    about the direction of the failure: the run is otherwise perfect - green pytest,
    nothing failing, over the floor - and it still exits 1.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    nodeid = f"{suite.as_posix()}/test_alpha.py::test_repaired"
    junit = _junit(
        tmp_path / "j.xml",
        [("tests.test_alpha", "test_repaired", "pass"), *_passing_cases(500)],
    )
    known = _inventory(tmp_path / "k.json", groups=[_group("was-red", nodeid)])

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, (
        "an inventoried node id passed; the lane must fail and name it so the line gets "
        f"deleted. It exited {code}.\n{printed}"
    )
    assert "known-red test(s) now PASS" in printed
    assert nodeid in printed, "the verdict must name the node id, or nobody can act on it"

    mutant = mutate(_CEILING_ANCHOR, _CEILING_BLINDED, "ceiling_removed")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the ceiling blinded, a repaired known-red test was "
        f"supposed to slip through silently; the mutant exited {mutant_code}."
    )


def test_an_unstable_entry_that_passes_is_a_notice_and_not_a_failure(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one category the ceiling does not police, and the reason that is not a loophole.

    An ``unstable`` entry that passes cannot be a failure - passing sometimes is the whole
    definition - but it must not be silent either, or the day the contamination is fixed is
    a day nothing says the exemptions can go. This control pins BOTH halves: exit 0, and a
    notice naming the node id.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    nodeid = f"{suite.as_posix()}/test_alpha.py::test_flappy"
    junit = _junit(
        tmp_path / "j.xml", [("tests.test_alpha", "test_flappy", "pass"), *_passing_cases(500)]
    )
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": nodeid,
                "runs_observed": 3,
                "runs_failed": 1,
                "reason": "measured over three identical runs",
            }
        ],
    )

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 0, f"an unstable entry that passed is not a failure; exited {code}\n{printed}"
    assert "(unstable, passed this run)" in printed
    assert nodeid in printed


# ── 4. a classname that names no file ──────────────────────────────────────────────────

_RESOLVE_REFUSAL: Final = (
    "    raise Refusal(\n"
    '        f"cannot resolve JUnit classname {classname!r} to a module under {suite_root}. "\n'
    '        "An id that resolves to nothing can never match the inventory, so it would be "\n'
    '        "reported NEW on every run or, if the matching were loosened, never reported."\n'
    "    )"
)
_RESOLVE_LOOSENED: Final = (
    '    return f"{suite_root.as_posix()}/{parts[-1]}.py::{name}"  # MUTANT: silent non-match'
)


def test_a_classname_that_names_no_file_is_a_hard_failure(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An id that resolves to nothing can never match the inventory — so it must not resolve.

    THE SCENARIO IS DELIBERATELY A **PASSING** TEST, and that choice is the whole control.
    An unresolvable id on a *failing* test would be reported NEW either way, so it cannot
    tell a hard failure apart from a loosened matcher. On a passing test the two answers
    diverge completely: the real program refuses the whole run, and a program whose matcher
    was loosened invents an id, matches nothing, says nothing, and exits 0.

    This is what "reported NEW on every run or, if the matching were loosened, never
    reported" means in practice, and it is why the refusal is not pedantry: the day the
    demo-api suite grows a subdirectory, this program must say so rather than quietly
    classify against ids that do not exist.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(
        tmp_path / "j.xml",
        [("tests.test_vanished", "test_one", "pass"), *_passing_cases(500)],
    )
    known = _inventory(tmp_path / "k.json")

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, (
        "a classname naming no module on disk must refuse the whole report, not be skipped "
        f"over. It exited {code}.\n{printed}"
    )
    assert "cannot resolve JUnit classname" in printed
    assert "tests.test_vanished" in printed, (
        "the refusal must name the classname it could not resolve, or it is unactionable"
    )

    mutant = mutate(_RESOLVE_REFUSAL, _RESOLVE_LOOSENED, "resolve_loosened")
    mutant_code, mutant_printed = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the resolver loosened into a silent non-match, this "
        f"run was supposed to sail through as green; it exited {mutant_code}.\n"
        f"{mutant_printed}"
    )


def test_the_resolver_rebuilds_a_real_copy_pasteable_node_id(tmp_path: pathlib.Path) -> None:
    """The positive half: JUnit's ``classname`` + ``name`` becomes the id a human can paste.

    Without this, ``test_a_classname_that_names_no_file_is_a_hard_failure`` is satisfied by
    a resolver that refuses everything - and a resolver that refuses everything makes the
    inventory unmatchable, which is the same defect wearing the opposite mask.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    assert (
        module.resolve_nodeid("tests.test_alpha", "test_one[silence]", suite)
        == f"{suite.as_posix()}/test_alpha.py::test_one[silence]"
    )
    assert (
        module.resolve_nodeid("tests.test_alpha.TestGroup", "test_one", suite)
        == f"{suite.as_posix()}/test_alpha.py::TestGroup::test_one"
    )


# ── 5. `unstable` must carry a measurement ─────────────────────────────────────────────

_UNSTABLE_MEASURED_ANCHOR: Final = (
    "        if not isinstance(observed, int) or not isinstance(failed, int) or observed <= 0:"
)
#: The measurement requirement removed, while leaving the *other* rule able to run: without
#: the second and third lines, `failed >= observed` would raise TypeError on the missing
#: values and the mutant would fail for a reason that is not the property under test.
_UNSTABLE_UNMEASURED: Final = (
    "        observed = observed if isinstance(observed, int) else 3  # MUTANT\n"
    "        failed = failed if isinstance(failed, int) else 1  # MUTANT\n"
    "        if False:"
)

_UNSTABLE_ALWAYS_ANCHOR: Final = "        if failed >= observed:"
_UNSTABLE_ALWAYS_ALLOWED: Final = "        if False:  # MUTANT: always-failing accepted"


def test_an_unstable_entry_without_a_measurement_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``unstable`` is the only category exempt from the ceiling, so it is the only place a
    failing test could be filed and forgotten. The measurement is what closes that.

    An entry that names how many runs it was seen over and how many it failed is a
    measurement somebody had to take. An entry without one is a node id somebody typed.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(500))
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": f"{suite.as_posix()}/test_alpha.py::test_flappy",
                "reason": "it is flaky, trust me",
            }
        ],
    )

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"an unmeasured `unstable` entry must refuse the report; exited {code}"
    assert "must carry measured `runs_observed`" in printed

    mutant = mutate(_UNSTABLE_MEASURED_ANCHOR, _UNSTABLE_UNMEASURED, "unstable_unmeasured")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the measurement requirement removed, an `unstable` "
        f"entry consisting of a node id and an opinion was supposed to be accepted and the "
        f"run to go green; it exited {mutant_code}."
    )


def test_an_unstable_entry_that_failed_every_run_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A test that failed every run it was seen in is not unstable. It is failing."""
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(500))
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": f"{suite.as_posix()}/test_alpha.py::test_always_red",
                "runs_observed": 3,
                "runs_failed": 3,
                "reason": "filed here because the ceiling does not police this list",
            }
        ],
    )

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"3 failures in 3 runs is not instability; exited {code}"
    assert "it is not unstable, it is failing" in printed

    mutant = mutate(_UNSTABLE_ALWAYS_ANCHOR, _UNSTABLE_ALWAYS_ALLOWED, "unstable_always")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with that rule removed, a test that failed 3 of 3 runs "
        f"was supposed to be accepted as `unstable`; the mutant exited {mutant_code}."
    )


def test_a_group_without_a_cause_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A node id recorded without the reason it fails is the shape a suppression list takes."""
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(500))
    known = tmp_path / "k.json"
    known.write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "floor": {"min_executed": 440, "max_skipped": 1},
                "groups": [{"slug": "quiet", "cause": "  ", "nodeids": []}],
                "unstable": [],
            }
        ),
        encoding="utf-8",
    )

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1
    assert "carries no `cause`" in printed


# ── 6. the caller's status, in the summary AND in the body ─────────────────────────────

_LOST_STATUS_ANCHOR: Final = (
    '    if pytest_rc == 0 and (run["failures"] or run["errors"] or run["bad"]):'
)
#: The state this line was in at ``e944407``, before the control below proved it wrong. It
#: is kept here as the MUTANT, so the fix cannot be reverted without this control noticing.
_LOST_STATUS_SUMMARY_ONLY: Final = '    if pytest_rc == 0 and (run["failures"] or run["errors"]):'
_LOST_STATUS_REMOVED: Final = "    if pytest_rc == 0 and False:  # MUTANT: guard removed"


def test_a_run_that_lost_pytests_status_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one rewiring that would let a fully-inventoried red run present as green.

    ``--pytest-rc`` being final protects nothing if the caller never passes the real value.
    Deleting ``--pytest-rc "${rc}"`` from the workflow step is a one-line edit that looks
    like tidying; this guard is what makes it a red run instead of a green one.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    nodeid = f"{suite.as_posix()}/test_alpha.py::test_one"
    junit = _junit(
        tmp_path / "j.xml", [("tests.test_alpha", "test_one", "fail"), *_passing_cases(500)]
    )
    known = _inventory(tmp_path / "k.json", groups=[_group("inventoried", nodeid)])

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, (
        "the XML records a failure while the caller claims pytest exited 0; the report must "
        f"refuse rather than let the inventory decide. It exited {code}.\n{printed}"
    )
    assert "the lane lost pytest's exit status" in printed

    mutant = mutate(_LOST_STATUS_ANCHOR, _LOST_STATUS_REMOVED, "lost_status_unguarded")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the guard removed, a red run whose status was "
        f"dropped and whose failures were all inventoried was supposed to present as green; "
        f"the mutant exited {mutant_code}."
    )


def test_a_body_full_of_failures_under_a_clean_summary_is_refused(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE CONTROL THAT FOUND A DEFECT. A JUnit document has two accounts of a run.

    The ``<testsuite>`` element carries summary attributes; the ``<testcase>`` children
    carry the outcomes. pytest computes the first from the second, so in any honest run
    they agree — but the guard above was reading only the summary, and the guard's whole
    subject is a *caller who has already been rewired*. A document whose summary reads
    ``failures="0"`` while its body carries ``<failure>`` children went through the floor,
    the classification and the ceiling and exited **0**, provided the node ids were
    inventoried. That is the exact outcome guard 0 exists to refuse, arriving through the
    half of the document it was not reading.

    ``run["bad"]`` — the parsed body — is the authoritative account, because it is the one
    the classification itself is computed from. The fix added it as a third clause and
    relaxed nothing. Against any real pytest run the clause is dead weight, which is what
    made it safe to land: it cannot move the verdict of a run pytest actually produced.

    The mutant here is the committed line as it stood at ``e944407``, so the defect cannot
    be reintroduced without this control saying so.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    nodeid = f"{suite.as_posix()}/test_alpha.py::test_one"
    junit = _junit(
        tmp_path / "j.xml",
        [("tests.test_alpha", "test_one", "fail"), *_passing_cases(500)],
        failures=0,
        errors=0,
    )
    known = _inventory(tmp_path / "k.json", groups=[_group("inventoried", nodeid)])

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, (
        "the JUnit body carries a <failure> while its summary claims none and the caller "
        f"claims pytest exited 0. The report must refuse. It exited {code}.\n{printed}"
    )
    assert "the lane lost pytest's exit status" in printed

    mutant = mutate(_LOST_STATUS_ANCHOR, _LOST_STATUS_SUMMARY_ONLY, "summary_only_guard")
    mutant_code, _ = _run(
        mutant, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED. With the guard reading only the <testsuite> summary "
        "attributes - which is how it stood at e944407 - this doctored document was "
        f"supposed to present as GREEN; the mutant exited {mutant_code}. If that is no "
        "longer true, some other line is now carrying the property and this control should "
        "be re-aimed at it rather than deleted."
    )


def test_the_guard_does_not_fire_on_an_honest_green_run(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The added clause must be dead weight on every run pytest actually produces.

    A guard that fired on honest runs would be a guard somebody removes. This is the
    regression control for the fix described above: a green run, an empty body of failures,
    a clean summary, ``rc=0`` — exit 0.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit = _junit(tmp_path / "j.xml", _passing_cases(500))
    known = _inventory(tmp_path / "k.json")
    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 0, f"an honest green run must exit 0; it exited {code}\n{printed}"
    assert "lost pytest's exit status" not in printed


# ── 7. the wiring the program's own safety rests on ────────────────────────────────────


def test_the_workflow_hands_the_report_pytests_real_status() -> None:
    """Every property above is conditional on the caller passing the real exit status.

    ``cluster-tests.yml`` captures ``rc=$?`` from the pytest invocation and hands it to the
    report as ``--pytest-rc "${rc}"``, in the SAME STEP, so there is nothing to delete that
    does not delete the run. This control reads that wiring, because the program cannot:
    the guard tested above catches a dropped status only for runs whose XML records
    failures, and a lane that dropped the status on a green run would look identical either
    way until the day it mattered.
    """
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "cluster_lane_report.py" in text, (
        "cluster-tests.yml no longer invokes the report this file controls."
    )
    assert "rc=$?" in text, (
        "cluster-tests.yml no longer captures pytest's exit status; --pytest-rc would be "
        "receiving something other than pytest's own answer."
    )
    assert '--pytest-rc "${rc}"' in text, (
        "cluster-tests.yml no longer hands pytest's captured status to the report. Every "
        "control in this file about --pytest-rc being final becomes vacuous the moment the "
        "caller stops passing the real value."
    )


def test_the_workflows_claim_about_these_controls_is_the_claim_this_file_answers() -> None:
    """The sentence that made this file necessary, kept attached to its evidence.

    ``cluster-tests.yml`` tells its reader that both properties are exercised by controls.
    That sentence was false when it was written. It is true now, and this assertion is what
    keeps the two facts in one place: if the sentence is ever reworded, whoever rewords it
    is made to look at whether the controls still say what it claims - and if the controls
    are deleted, this file goes with them and the claim loses its only support.
    """
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "Both properties are exercised by controls" in text, (
        "cluster-tests.yml no longer claims controls exist for the report's two properties. "
        "If that claim was withdrawn on purpose, delete this test in the same commit; if it "
        "was reworded, re-aim this test at the new wording. What must not happen is the "
        "claim standing with nothing behind it, which is the state this file was written to "
        "end."
    )


# ── 8. every Refusal path, and the invariant that binds all of them ────────────────────
#
# `Refusal` is the program's one exit that produces no classification at all. Nine `raise`
# sites reach it, and each names a way the inventory or the JUnit document could be
# malformed such that the report below it would mean something other than what it says. A
# refusal nobody has ever triggered is a refusal nobody knows still works, so every one of
# them is reached here by a scenario that provokes it.
#
# `main` catches `Refusal` and returns `args.pytest_rc or 1`. That expression carries two
# separate promises and the sweep below pins both:
#
#   * NEVER 0 — a report that cannot be produced is not a pass. This is the direction the
#     rest of this file cannot reach on its own: the controls above demonstrate that
#     specific gates FIRE, and a program that refused everything would satisfy all of them.
#   * NEVER QUIETER THAN PYTEST — a refusal on a run pytest exited 5 on exits 5, not 1. A
#     lane that flattened its refusals would report "no tests collected" as "tests failed",
#     which is a different event with a different owner.


def _raw(path: pathlib.Path, payload: object) -> pathlib.Path:
    """Write an inventory body verbatim, including bodies `_inventory` could not build."""
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _absent_from_the_run(suite: pathlib.Path) -> str:
    """A node id that is INVENTORIED BUT DOES NOT APPEAR IN THE RUN.

    Every inventory scenario below pairs with a run of 500 passing tests, none of which is
    this id. That is deliberate rather than incidental: if the id appeared in the run, a
    mutant that accepted the malformed inventory would then trip the CEILING and exit 1,
    and the negative half of section 9's demonstration would pass for a reason that has
    nothing to do with the rule under test.
    """
    return f"{suite.as_posix()}/test_alpha.py::test_never_ran"


#: `slug -> (builder, fragment)`. The builder is handed `tmp_path` and the suite root and
#: returns `(junit, known)`. The fragment must appear in the refusal text, because a
#: refusal that does not name what it refused is a refusal nobody can act on.
REFUSALS: Final[dict[str, tuple[Any, str]]] = {}


def _refusal(slug: str, fragment: str) -> Any:
    def register(builder: Any) -> Any:
        REFUSALS[slug] = (builder, fragment)
        return builder

    return register


@_refusal("the inventory file does not exist", "no known-red inventory at")
def _b_no_inventory(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    return _junit(tmp_path / "j.xml", _passing_cases(500)), tmp_path / "absent.json"


@_refusal("the inventory is not JSON", "is not valid JSON")
def _b_bad_json(tmp_path: pathlib.Path, _suite: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    known = tmp_path / "k.json"
    known.write_text('{"schema": "mainline.qa.cluster-known-red/1",', encoding="utf-8")
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("the inventory declares another schema", "declares schema")
def _b_wrong_schema(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _inventory(tmp_path / "k.json", schema="mainline.qa.cluster-known-red/2")
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("the inventory carries no floor", "carries no `floor` object")
def _b_no_floor(tmp_path: pathlib.Path, _suite: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    known = _raw(tmp_path / "k.json", {"schema": SCHEMA, "groups": [], "unstable": []})
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("floor.min_executed is not an integer", "floor.min_executed must be an integer")
def _b_floor_min_string(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _raw(
        tmp_path / "k.json",
        {
            "schema": SCHEMA,
            "floor": {"min_executed": "440", "max_skipped": 1},
            "groups": [],
            "unstable": [],
        },
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("floor.max_skipped is not an integer", "floor.max_skipped must be an integer")
def _b_floor_max_null(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _raw(
        tmp_path / "k.json",
        {
            "schema": SCHEMA,
            "floor": {"min_executed": 440, "max_skipped": None},
            "groups": [],
            "unstable": [],
        },
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("a group carries no slug", "a group carries no `slug`")
def _b_group_no_slug(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _raw(
        tmp_path / "k.json",
        {
            "schema": SCHEMA,
            "floor": {"min_executed": 440, "max_skipped": 1},
            "groups": [{"cause": "a cause with nobody's name on it", "nodeids": []}],
            "unstable": [],
        },
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("a group carries no cause", "carries no `cause`")
def _b_group_no_cause(
    tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _raw(
        tmp_path / "k.json",
        {
            "schema": SCHEMA,
            "floor": {"min_executed": 440, "max_skipped": 1},
            "groups": [{"slug": "quiet", "cause": "", "nodeids": [_absent_from_the_run(suite)]}],
            "unstable": [],
        },
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("one node id appears in two groups", "appears in two groups")
def _b_two_groups(tmp_path: pathlib.Path, suite: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    nodeid = _absent_from_the_run(suite)
    known = _inventory(
        tmp_path / "k.json", groups=[_group("first", nodeid), _group("second", nodeid)]
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("one node id is both known and unstable", "is both a known group member and `unstable`")
def _b_known_and_unstable(
    tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    nodeid = _absent_from_the_run(suite)
    known = _inventory(
        tmp_path / "k.json",
        groups=[_group("first", nodeid)],
        unstable=[{"nodeid": nodeid, "runs_observed": 4, "runs_failed": 1, "reason": "measured"}],
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("an unstable entry carries no node id", "an `unstable` entry carries no `nodeid`")
def _b_unstable_no_nodeid(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _inventory(
        tmp_path / "k.json",
        unstable=[{"runs_observed": 4, "runs_failed": 1, "reason": "measured over four runs"}],
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("an unstable entry was observed over zero runs", "must carry measured `runs_observed`")
def _b_unstable_zero_runs(
    tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": _absent_from_the_run(suite),
                "runs_observed": 0,
                "runs_failed": 0,
                "reason": "nobody has actually run it",
            }
        ],
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("an unstable entry failed every run it was seen in", "it is not unstable, it is failing")
def _b_unstable_always_failed(
    tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": _absent_from_the_run(suite),
                "runs_observed": 4,
                "runs_failed": 4,
                "reason": "filed here because the ceiling does not police this list",
            }
        ],
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("an unstable entry carries no reason", "carries no `reason`")
def _b_unstable_no_reason(
    tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    known = _inventory(
        tmp_path / "k.json",
        unstable=[
            {
                "nodeid": _absent_from_the_run(suite),
                "runs_observed": 4,
                "runs_failed": 1,
                "reason": "   ",
            }
        ],
    )
    return _junit(tmp_path / "j.xml", _passing_cases(500)), known


@_refusal("pytest wrote no JUnit report", "pytest wrote no JUnit report")
def _b_no_junit(tmp_path: pathlib.Path, _suite: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    return tmp_path / "never-written.xml", _inventory(tmp_path / "k.json")


@_refusal("the JUnit report is not parseable XML", "is not parseable XML")
def _b_junit_truncated(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    junit = tmp_path / "j.xml"
    junit.write_text('<?xml version="1.0"?>\n<testsuite tests="3"><testcase', encoding="utf-8")
    return junit, _inventory(tmp_path / "k.json")


@_refusal("the JUnit report carries no testsuite", "carries no <testsuite>")
def _b_junit_no_suite(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    junit = tmp_path / "j.xml"
    junit.write_text('<?xml version="1.0"?>\n<testsuites></testsuites>\n', encoding="utf-8")
    return junit, _inventory(tmp_path / "k.json")


@_refusal("a classname resolves to no module", "cannot resolve JUnit classname")
def _b_unresolvable(
    tmp_path: pathlib.Path, _suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path]:
    junit = _junit(
        tmp_path / "j.xml", [("tests.test_vanished", "test_one", "pass"), *_passing_cases(500)]
    )
    return junit, _inventory(tmp_path / "k.json")


def _scenario(
    slug: str, tmp_path: pathlib.Path, suite: pathlib.Path
) -> tuple[pathlib.Path, pathlib.Path, str]:
    builder, fragment = REFUSALS[slug]
    junit, known = builder(tmp_path, suite)
    return junit, known, fragment


@pytest.mark.parametrize("slug", sorted(REFUSALS))
def test_every_refusal_path_refuses_the_report(
    slug: str, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each `raise Refusal` site in the program, reached by a scenario that provokes it.

    The assertion has two halves and the second is what stops this being a coverage
    exercise: the refusal must NAME what it refused. The banner tells a reader that the
    lane gave up; the fragment is what tells them which of eighteen malformed things they
    are holding, and therefore what to go and fix.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit, known, fragment = _scenario(slug, tmp_path, suite)

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys
    )
    assert code == 1, f"{slug!r} must refuse the report; it exited {code}\n{printed}"
    assert "the cluster lane cannot be reported" in printed, (
        f"{slug!r} exited 1 without printing the refusal banner, so whatever produced that 1 "
        f"was not a Refusal and this control is no longer testing the path it names.\n{printed}"
    )
    assert fragment in printed, (
        f"{slug!r} refused, but the message never said {fragment!r}. A refusal that does not "
        f"name what it refused is a refusal nobody can act on.\n{printed}"
    )


#: The refusal handler's exit expression. Both halves are load-bearing; a mutant removes each.
_REFUSAL_EXIT_ANCHOR: Final = "        return args.pytest_rc or 1"
_REFUSAL_EXIT_ZERO: Final = "        return 0  # MUTANT: a report that cannot be produced passes"
_REFUSAL_EXIT_FLAT: Final = "        return 1  # MUTANT: refusals flattened to 'tests failed'"


@pytest.mark.parametrize("pytest_rc", [0, 1, 2, 5])
@pytest.mark.parametrize("slug", sorted(REFUSALS))
def test_a_refusal_never_exits_zero_and_never_softens_pytests_status(
    slug: str, pytest_rc: int, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`return args.pytest_rc or 1`, swept over every refusal and every status that matters.

    The program's stated contract is that it may only ADD a failure. A refusal is the case
    where it has nothing to add, and there are exactly two ways to get that wrong: report
    success, or report something quieter than what pytest had already said.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    junit, known, _ = _scenario(slug, tmp_path, suite)

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=pytest_rc, capsys=capsys
    )
    assert code != 0, f"{slug!r} refused and exited 0. A refusal is never a pass.\n{printed}"
    assert code == (pytest_rc or 1), (
        f"{slug!r} with pytest_rc={pytest_rc} exited {code}. A refusal exits with pytest's own "
        "status when there is one and 1 when pytest was green - never with a status that means "
        f"less than the one pytest returned.\n{printed}"
    )


def test_the_refusal_sweep_would_notice_a_handler_that_reported_success(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The negative half of the sweep above: both halves of the exit expression, mutated.

    Without this, the sweep is a sweep over a handler that could be anything at all. The
    first mutant turns every refusal into a green run; the second flattens a refusal on a
    run pytest exited 5 on down to 1.
    """
    suite = _suite_root(tmp_path, "test_alpha")
    junit, known, _ = _scenario("a classname resolves to no module", tmp_path, suite)

    green = mutate(_REFUSAL_EXIT_ANCHOR, _REFUSAL_EXIT_ZERO, "refusal_reports_success")
    code, _ = _run(green, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys)
    assert code == 0, (
        "THE DEMONSTRATION FAILED: with the refusal handler returning 0, an unreportable run "
        f"was supposed to present as green; it exited {code}. The sweep above is therefore not "
        "evidence that the handler is what keeps a refusal non-zero."
    )

    flat = mutate(_REFUSAL_EXIT_ANCHOR, _REFUSAL_EXIT_FLAT, "refusal_flattened")
    code, _ = _run(flat, junit=junit, known=known, suite_root=suite, pytest_rc=5, capsys=capsys)
    assert code == 1, (
        "THE DEMONSTRATION FAILED: with the refusal handler flattened to a constant 1, a "
        f"refusal on a run pytest exited 5 on was supposed to answer 1; it answered {code}."
    )


# ── 9. the three validity rules whose removal is SILENT, which is what makes them gates ─
#
# Every scenario in section 8 pairs a malformed inventory with a run of 500 passing tests
# and a node id that is inventoried but ABSENT from the run. So when one of these three
# rules is removed, nothing downstream objects: there is no failure to classify, no ceiling
# to trip and no floor to miss. The mutant exits 0 and says nothing. That is the whole
# point — these rules are the only thing between a malformed inventory and a green lane,
# and a rule whose absence would have been caught by something else is not a gate.

_SCHEMA_ANCHOR: Final = '    if data.get("schema") != SCHEMA:'
_SCHEMA_UNCHECKED: Final = "    if False:  # MUTANT: any document may be read as an inventory"

_TWO_GROUPS_ANCHOR: Final = "\n            if nodeid in known:\n"
_TWO_GROUPS_ALLOWED: Final = "\n            if False:  # MUTANT: an id may sit in two groups\n"

#: `if nodeid in known:` appears THREE times in the program - once per group member, once
#: per unstable entry, and once in the classification loop - so the anchor carries the line
#: below it. `mutate` refuses an ambiguous anchor, which is how that was caught rather than
#: silently mutating the wrong one.
_KNOWN_AND_UNSTABLE_ANCHOR: Final = (
    "        if nodeid in known:\n"
    '            raise Refusal(f"{path}: {nodeid} is both a known group member and `unstable`")'
)
_KNOWN_AND_UNSTABLE_ALLOWED: Final = (
    "        if False:  # MUTANT: an id may be known AND exempt\n"
    '            raise Refusal(f"{path}: {nodeid} is both a known group member and `unstable`")'
)


def _mutant_verdict(
    module: ModuleType, slug: str, tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    suite = _suite_root(tmp_path, "test_alpha")
    junit, known, _ = _scenario(slug, tmp_path, suite)
    return _run(module, junit=junit, known=known, suite_root=suite, pytest_rc=0, capsys=capsys)


def test_the_schema_check_is_what_stops_a_foreign_document_being_read_as_an_inventory(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A document of the wrong shape, read through `.get` defaults, is an EMPTY inventory.

    That is the hazard the schema string closes, and it is why removing the check produces
    no error at all: `groups`, `unstable` and every id in them simply vanish, the floor is
    whatever the foreign document happened to carry, and the lane reports a clean run over
    an inventory it never read. The mutant exits 0 in silence.
    """
    mutant = mutate(_SCHEMA_ANCHOR, _SCHEMA_UNCHECKED, "schema_unchecked")
    code, printed = _mutant_verdict(
        mutant, "the inventory declares another schema", tmp_path, capsys
    )
    assert code == 0, (
        "THE DEMONSTRATION FAILED: with the schema check removed, a document declaring "
        f"another schema was supposed to be read as an empty inventory and the run to go "
        f"green; it exited {code}.\n{printed}"
    )


def test_the_duplicate_group_rule_is_what_stops_one_id_having_two_owners(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A node id in two groups has two causes and two owners, so it has neither.

    `known` is a dict; the second group silently wins. The failure would then be reported
    under a cause that is not its own, and the group that really owns it would look empty
    and get deleted. The mutant accepts that and exits 0.
    """
    mutant = mutate(_TWO_GROUPS_ANCHOR, _TWO_GROUPS_ALLOWED, "two_groups_allowed")
    code, printed = _mutant_verdict(mutant, "one node id appears in two groups", tmp_path, capsys)
    assert code == 0, (
        "THE DEMONSTRATION FAILED: with the duplicate-group rule removed, an id named by two "
        f"groups was supposed to be accepted silently; the mutant exited {code}.\n{printed}"
    )


def test_the_known_and_unstable_rule_is_what_stops_an_id_holding_both_passports(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An id in `groups` AND in `unstable` is the one combination that defeats the ceiling.

    `groups` membership is policed by the CEILING: fix the test and the lane demands the
    line be deleted. `unstable` membership is exempt, by design, and only produces a
    notice. An id holding both is classified as `known` while a reader auditing the
    exemptions sees it listed as measured flakiness — and the day it is fixed, the lane
    fails asking for a deletion that leaves the other half of the entry behind. The mutant
    accepts it and exits 0.
    """
    mutant = mutate(_KNOWN_AND_UNSTABLE_ANCHOR, _KNOWN_AND_UNSTABLE_ALLOWED, "both_passports")
    code, printed = _mutant_verdict(
        mutant, "one node id is both known and unstable", tmp_path, capsys
    )
    assert code == 0, (
        "THE DEMONSTRATION FAILED: with that rule removed, an id that is both inventoried and "
        f"declared unstable was supposed to be accepted silently; it exited {code}.\n{printed}"
    )


# ── 10. the classification is a message, and the verdict is still pytest's ─────────────


def test_a_new_failure_is_named_but_the_verdict_is_still_pytests(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An uninventoried failure produces a NEW verdict — and pytest's status is what exits.

    This is the half of `report()` that has no gate of its own, and the control says why
    that is correct rather than an omission. A run with a failing test always reaches this
    program with a non-zero `--pytest-rc`, so the NEW verdict can never be the thing that
    decides the run: it decides the SENTENCE. The assertion is therefore about the log, and
    about the exit status being 1 because pytest said 1 — not because a verdict was raised.
    """
    module = real()
    suite = _suite_root(tmp_path, "test_alpha")
    nodeid = f"{suite.as_posix()}/test_alpha.py::test_unseen"
    junit = _junit(
        tmp_path / "j.xml", [("tests.test_alpha", "test_unseen", "fail"), *_passing_cases(500)]
    )
    known = _inventory(tmp_path / "k.json")

    code, printed = _run(
        module, junit=junit, known=known, suite_root=suite, pytest_rc=1, capsys=capsys
    )
    assert code == 1
    assert "NEW cluster failure(s)" in printed
    # `failure`, not `fail`: the program prints the JUnit ELEMENT NAME it matched, which is
    # the vocabulary of the document it read rather than of this file's scenario builder.
    # This assertion originally said `fail` and went red; the program's word is the correct
    # one and the expectation moved to it, not the other way about.
    assert f"  NEW      failure: {nodeid}" in printed, (
        "the NEW verdict must name the node id in the classification body, or the log tells a "
        f"reader that something new failed without telling them what.\n{printed}"
    )
    assert "these are not on qa/cluster-known-red.json" in printed.lower()

    # And the same run, with pytest's real status of 2, exits 2 - the classification did not
    # decide it. Without this half, "exit 1" above is indistinguishable from a NEW verdict
    # deciding the run on its own.
    code, _ = _run(module, junit=junit, known=known, suite_root=suite, pytest_rc=2, capsys=capsys)
    assert code == 2, (
        f"the same NEW failure under pytest_rc=2 exited {code}. The classification is a "
        "message; pytest's status is the verdict."
    )
