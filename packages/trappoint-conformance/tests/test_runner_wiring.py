# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The four wiring defects that stood between a live corpus and a demonstrated suite.

Each assertion below corresponds to a thing that was measured broken on 2026-08-10 and
each would have caught it. In order:

1. **The corpus was invisible to the tool that runs it.** ``trappoint-conform --profile
   mainline --list`` said ``implemented 1 / 71``; ``python -c "import cases;
   print(len(cases.load_all()))"`` from inside the package directory said ``71``. Two
   causes, one symptom: ``cli.py`` never called the loader, and ``cases/`` was absent from
   ``[tool.hatch.build.targets.wheel].packages`` so an installed environment could not
   import it from anywhere else. Both are asserted here **through a subprocess run from a
   directory that is not the package**, because an in-process assertion would be satisfied
   by ``conftest.py``'s own ``sys.path`` surgery and would therefore assert nothing about
   the installed distribution.

2. **One unbuildable world aborted the whole suite.** ``SetupRefused`` subclasses
   ``AssertionError``; ``runner.run()`` caught ``psycopg.Error`` and nothing else. The
   fabricated two-case run below is the regression test: case one refuses its world, case
   two still executes.

3. **A cannot-run must never read as green.** ``is_green`` is asserted false for a report
   whose only non-passing result is ``CANNOT_RUN``.

4. **A capability token must be resolved, not asserted by a human.** The prober is
   exercised twice — against a stub catalogue, so the assertion runs on any machine, and
   against the live cluster when one is configured.

None of it touches a ``cfNN_*.py``. The whole point of the wave's ruling D8 is that a
worker who can edit the cases can make the census green by editing them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from trappoint_conformance.capability import POLICY, RELATION, ROLE, parse_token, probe
from trappoint_conformance.harness import HistoryOutcome
from trappoint_conformance.manifest import Case, Manifest
from trappoint_conformance.runner import (
    CaseResult,
    RunReport,
    SetupRefused,
    Status,
    run,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
MANIFEST = REPO_ROOT / "spec" / "conformance" / "manifest.toml"

#: What the corpus holds today: seventy ``cfNN_*.py`` modules plus ``CF-01``, which the
#: runner registers itself. Hard-coded on purpose — a test that recomputed the number from
#: the directory it is checking would pass on an empty directory.
EXPECTED_IMPLEMENTED = 71


def _clean_env() -> dict[str, str]:
    """An environment with nothing that could put the package root on ``sys.path``."""
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# ─────────────────────────────────────────────────────────────────────────────
# 1 + 2 · the corpus is importable from anywhere, and the CLI imports it
# ─────────────────────────────────────────────────────────────────────────────


def test_installed_environment_loads_seventy_one_cases(tmp_path: Path) -> None:
    """``import cases`` resolves against the installed distribution, from a third directory.

    ``cwd`` is a temporary directory: neither the repository nor the package. If ``cases``
    is missing from the wheel's package list this raises ``ModuleNotFoundError`` and the
    subprocess exits non-zero, which is the packaging defect stated as a failure rather
    than as ``implemented 1 / 71`` three layers away.
    """
    proc = subprocess.run(
        [sys.executable, "-c", "import cases; print(len(cases.load_all()))"],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, (
        f"`import cases` failed from {tmp_path}. The corpus ships with the "
        f"trappoint-conformance distribution; check [tool.hatch.build.targets.wheel]."
        f"packages lists `cases`, and reinstall.\n{proc.stderr}"
    )
    assert proc.stdout.strip() == str(EXPECTED_IMPLEMENTED), proc.stdout + proc.stderr


def test_cli_list_reports_every_case_as_implemented(tmp_path: Path) -> None:
    """``--list`` counts implementations, from a cwd that is not the package.

    The manifest is passed explicitly because ``find_manifest`` walks up from the working
    directory by design — the runner asserts the specification in the tree it is run
    from and ships no copy of its own — and the working directory here is deliberately
    outside any tree.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "trappoint_conformance.cli",
            "--profile",
            "mainline",
            "--manifest",
            str(MANIFEST),
            "--list",
            "--json",
        ],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    listing = json.loads(proc.stdout)
    assert listing["pending"] == [], (
        "cli.py did not load the corpus: these cases have implementations in the tree and "
        f"the tool reported them PENDING: {listing['pending']}"
    )
    assert listing["selected"] == EXPECTED_IMPLEMENTED
    assert len(listing["implemented"]) == EXPECTED_IMPLEMENTED


# ─────────────────────────────────────────────────────────────────────────────
# 3 · one refused world is one result, not an aborted suite
# ─────────────────────────────────────────────────────────────────────────────


class _StubConnection:
    """Enough of a connection for :func:`run` to reach the implementations.

    ``Harness.__init__`` pins the isolation level and nothing else touches the connection
    on this path, because both implementations below are supplied by the test. A real
    connection would make this test about a database instead of about the loop.
    """

    isolation_level: Any = None

    def __init__(self) -> None:
        self.rolled_back = 0

    def rollback(self) -> None:  # pragma: no cover - exercised only via `_recover`
        self.rolled_back += 1


def _case(case_id: str, *, requires: tuple[str, ...] = ()) -> Case:
    return Case(
        id=case_id,
        title=f"fabricated {case_id}",
        cls="refuse",
        invariants=("MI01",),
        mi=("MI01",),
        anomaly="none",
        expect_sqlstate="23514",
        expect_constraint="gate_closed_when_issued",
        profiles=("mainline",),
        refusal_depth_min=1,
        milestone="K1",
        requires=requires,
    )


def _manifest(*cases: Case) -> Manifest:
    return Manifest(
        path=Path("fabricated"),
        spec_version="test",
        profiles=("mainline",),
        gate_taxonomy=(),
        cases=cases,
        declared_case_count=len(cases),
        declared_ref_profile_case_count=0,
    )


def _refused(case_id: str) -> HistoryOutcome:
    """A history that was refused exactly as ``_case`` says it must be."""
    return HistoryOutcome(
        case_id=case_id,
        completed=False,
        sqlstate="23514",
        constraint="gate_closed_when_issued",
        message="fabricated refusal",
    )


def test_setup_refused_is_one_cannot_run_and_does_not_abort_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect that turned 182 results into 182 errors, asserted as a two-case run."""
    from trappoint_conformance import runner as runner_module

    def refuses_its_world(*_: Any) -> HistoryOutcome:
        raise SetupRefused("CF-T1: building the LEGAL world failed at 'site'. Cause: boom")

    def refuses_the_history(*_: Any) -> HistoryOutcome:
        return _refused("CF-T2")

    monkeypatch.setitem(runner_module._REGISTRY, "CF-T1", refuses_its_world)
    monkeypatch.setitem(runner_module._REGISTRY, "CF-T2", refuses_the_history)

    report = run(
        _manifest(_case("CF-T1"), _case("CF-T2")),
        profile="mainline",
        conn=_StubConnection(),  # type: ignore[arg-type]
        run_id="wiring",
    )

    assert [r.case.id for r in report.results] == ["CF-T1", "CF-T2"], (
        "the run stopped at the case whose world would not build; every case after it is "
        "unreported, which is the abort this test exists to forbid"
    )
    assert report.results[0].status is Status.CANNOT_RUN
    assert "WORLD NOT BUILT" in report.results[0].detail
    assert "Cause: boom" in report.results[0].detail
    assert report.results[1].status is Status.PASSED
    assert report.count(Status.CANNOT_RUN) == 1
    assert report.count(Status.ERROR) == 0, (
        "a refused world is not a runner error: ERROR means the runner could not run the "
        "case at all, and this runner ran it and was told no by the setup"
    )


def test_cannot_run_is_rendered_counted_and_never_green() -> None:
    """``CANT``, in the summary, and out of ``is_green``."""
    result = CaseResult(_case("CF-T3"), Status.CANNOT_RUN, "WORLD NOT BUILT — because")
    assert result.render().startswith("CANT  CF-T3")
    assert "WORLD NOT BUILT — because" in result.render()

    report = RunReport(profile="mainline", schema="mainline", spec_version="test", run_id="r")
    report.results.append(CaseResult(_case("CF-T4"), Status.PASSED, "", _refused("CF-T4")))
    assert report.is_green

    report.results.append(result)
    assert not report.is_green, (
        "a run in which a legal world would not build has not exercised the gate on that "
        "case, so it cannot entitle anyone to the sentence a green run entitles them to"
    )
    assert "cannot_run 1" in report.summary()
    assert report.count(Status.SKIPPED) == 0


def test_a_probed_absent_requirement_is_cannot_run_and_an_unprobed_one_still_skips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``SKIPPED`` versus ``CANNOT_RUN`` is decided by whether anybody looked.

    Both statuses exist and both are honest; what would not be honest is reporting
    ``requires mainline.propagation`` when the runner has just read ``pg_class`` and can
    name the relation.
    """
    from trappoint_conformance import runner as runner_module

    monkeypatch.setitem(runner_module._REGISTRY, "CF-T5", lambda *_: _refused("CF-T5"))
    manifest = _manifest(_case("CF-T5", requires=("mainline.propagation",)))

    unprobed = run(
        manifest,
        profile="mainline",
        conn=_StubConnection(),
        run_id="r",  # type: ignore[arg-type]
    )
    assert unprobed.results[0].status is Status.SKIPPED
    assert unprobed.results[0].detail == "requires mainline.propagation"

    probed = run(
        manifest,
        profile="mainline",
        conn=_StubConnection(),  # type: ignore[arg-type]
        requirement_reasons={
            "mainline.propagation": 'relation "mainline.propagation" does not exist'
        },
        run_id="r",
    )
    assert probed.results[0].status is Status.CANNOT_RUN
    assert "mainline.propagation" in probed.results[0].detail
    assert "does not exist" in probed.results[0].detail

    declared = run(
        manifest,
        profile="mainline",
        conn=_StubConnection(),  # type: ignore[arg-type]
        satisfied_requirements=("mainline.propagation",),
        requirement_reasons={"mainline.propagation": "unreachable — the human declared it"},
        run_id="r",
    )
    assert declared.results[0].status is Status.PASSED, (
        "an explicit --requires must still win: it is additive to the probe, not overridden"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4 · the capability prober
# ─────────────────────────────────────────────────────────────────────────────


def test_tokens_parse_into_the_three_catalogues_they_are_probed_against() -> None:
    """Every token form the manifest uses, and the re-homing a non-MAINLINE profile needs."""
    assert parse_token("mainline.propagation", schema="mainline") == (
        RELATION,
        "mainline",
        "propagation",
    )
    assert parse_token("mainline_meas.person_measure_policy", schema="mainline") == (
        RELATION,
        "mainline_meas",
        "person_measure_policy",
    )
    assert parse_token("role:mainline_auditor", schema="mainline") == (
        ROLE,
        "",
        "mainline_auditor",
    )
    assert parse_token("policy:mainline.permit", schema="mainline") == (
        POLICY,
        "mainline",
        "permit",
    )
    # The manifest writes every token in MAINLINE's namespace whatever the profile, the
    # same convention `cases/_exhibit.MANIFEST_NAMESPACE` uses for P0001 exhibits.
    assert parse_token("mainline.propagation", schema="trappoint_ref") == (
        RELATION,
        "trappoint_ref",
        "propagation",
    )
    assert parse_token("mainline_meas.recall_policy", schema="trappoint_ref") == (
        RELATION,
        "trappoint_ref_meas",
        "recall_policy",
    )


class _StubCursor:
    """A catalogue that answers the prober's four reads from a canned fixture."""

    def __init__(self, present: bool) -> None:
        self._present = present
        self._rows: list[tuple[Any, ...]] = []

    def __enter__(self) -> _StubCursor:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, sql: str, _params: Any = ()) -> None:
        if "pg_namespace" in sql and "pg_class" not in sql:
            self._rows = [("mainline",)]
        elif "pg_class" in sql:
            self._rows = [("mainline", "permit", "r")] if self._present else []
        elif "pg_roles" in sql:
            self._rows = []
        else:
            self._rows = []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _StubCatalogue:
    def __init__(self, present: bool) -> None:
        self._present = present
        self.info = type("Info", (), {"dbname": "stub_db"})()

    def cursor(self) -> _StubCursor:
        return _StubCursor(self._present)


def test_prober_resolves_a_present_relation_and_names_an_absent_one() -> None:
    """The whole contract, on a catalogue this test controls."""
    found = probe(_StubCatalogue(present=True), ["mainline.permit"], schema="mainline")
    assert found.satisfied == {"mainline.permit"}
    assert found.reasons() == {}
    assert found.capabilities[0].detail == "table mainline.permit"

    missing = probe(_StubCatalogue(present=False), ["mainline.permit"], schema="mainline")
    assert missing.satisfied == frozenset()
    reason = missing.reasons()["mainline.permit"]
    assert "mainline.permit" in reason, "a reason that does not name the object is not a reason"
    assert "does not exist" in reason
    assert "stub_db" in reason, "a reason must say which database was asked"


def test_an_unrecognised_token_is_never_silently_satisfied() -> None:
    """A token nobody taught the prober about stays unsatisfied and says so."""
    report = probe(_StubCatalogue(present=True), ["extension:vector"], schema="mainline")
    assert report.satisfied == frozenset()
    assert "not a capability token this prober understands" in report.reasons()["extension:vector"]


# ─────────────────────────────────────────────────────────────────────────────
# the same claim, against a real cluster
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.db
def test_prober_against_the_live_cluster(conn: Any) -> None:
    """Resolve one relation that exists and one that cannot, on the database in front of us.

    The absent token is a UUID, so it names nothing any migration will ever create and the
    assertion cannot be invalidated by a later wave authoring a table. ``pg_class`` is the
    catalogue; if the connected database has no ``site`` relation the case is skipped with
    the reason rather than asserted around.
    """
    from trappoint_conformance.runner import resolve_schema

    schema = resolve_schema(os.environ.get("TRAPPOINT_PROFILE", "trappoint-ref"))
    absent = f"{schema}.absent_{uuid.uuid4().hex[:12]}"
    report = probe(conn, [f"{schema}.site", absent], schema=schema)

    if f"{schema}.site" not in report.satisfied:
        pytest.skip(
            f"SKIP WITH REASON: {report.reasons()[f'{schema}.site']} — this database is "
            "not migrated for the profile under test, so there is no present relation to "
            "resolve."
        )
    assert report.capabilities[0].satisfied
    assert absent not in report.satisfied
    assert absent in report.reasons()[absent]
    assert "does not exist" in report.reasons()[absent]
