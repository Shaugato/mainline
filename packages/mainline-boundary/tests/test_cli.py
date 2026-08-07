# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The CLI, whose exit codes are the contract CI reads.

Exit 3 is the one that matters: a check that examined nothing and gave no reason
must not exit 0. "The check passed" and "the check did not happen" can never be
the same status.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mainline_boundary.cli import EXIT_OK, EXIT_SKIPPED, EXIT_VACUOUS, EXIT_VIOLATIONS, main

REPO_ROOT = Path(__file__).resolve().parents[3]
PLAN = REPO_ROOT / "tests" / "boundary" / "fixtures" / "plan.json"


@pytest.mark.parametrize("command", ["e1", "e2", "e4"])
def test_plan_commands_pass_against_the_fixture(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([command, "--repo-root", str(REPO_ROOT), "--plan", str(PLAN)])
    captured = capsys.readouterr()
    assert code == EXIT_OK, captured.out


def test_json_output_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    main(["e2", "--repo-root", str(REPO_ROOT), "--plan", str(PLAN), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["enforcement"] == "E2"
    assert payload["examined"] > 0


def test_greps_pass_over_the_repository(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["greps", "--repo-root", str(REPO_ROOT)])
    assert code == EXIT_OK, capsys.readouterr().out


def test_a_vacuous_run_does_not_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty tree has no kernel packages, so E3 must not report success."""
    code = main(["e3", "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert code in {EXIT_VACUOUS, EXIT_SKIPPED}, captured.out
    assert code != EXIT_OK


def test_strict_turns_a_reasoned_skip_into_a_failure(tmp_path: Path) -> None:
    assert main(["e3", "--repo-root", str(tmp_path), "--strict"]) == EXIT_VIOLATIONS


def test_fleet_command_reports_the_register_it_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["fleet", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == EXIT_SKIPPED
    assert "fleet.yaml" in out


def test_fleet_command_reads_an_explicit_register(capsys: pytest.CaptureFixture[str]) -> None:
    reference = Path(__file__).resolve().parent / "fixtures" / "fleet_reference.yaml"
    code = main(["fleet", "--repo-root", str(REPO_ROOT), "--fleet", str(reference)])
    assert code == EXIT_OK, capsys.readouterr().out
