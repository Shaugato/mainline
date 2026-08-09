# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint render``'s exit codes — the only part of this package CI can read.

Every refusal in this distribution is a sentence someone reads. Only one thing about it
is machine-readable, and it is the exit code, so the exit code is what these tests
assert. The distinction between ``1`` and ``2`` is load-bearing and is not a stylistic
choice:

``0``  the command did what it said.
``1``  the renderer REFUSED — an unbacked projected column, an unmeasured capability, a
       banned token, a ``--check`` that found a diff.
``2``  the INVOCATION was wrong.

A wrapper that could not tell those apart would retry a wrong binding forever, or would
report a typo as an integrity failure. Both have happened to other people.

``--check`` writes nothing, ever. That is asserted here rather than asserted in prose,
because "safe to run on a read-only checkout" is the property that lets CI run it on a
tree it must not mutate.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from trappoint_sql.cli import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, discover_bindings, main

PROJECTING = """\
{# @projects blocking_check.reading_floor_met #}
-- @file 9300_gate.sql
{{ header(file='9300_gate.sql', title='an unbacked projection',
          rationale='Deliberately unbacked.', mi=['MI02'], i=['I02']) }}

CREATE TABLE {{ binding.schema }}.probe (x INT8 NOT NULL PRIMARY KEY);
"""


def test_check_over_the_real_tree_exits_zero(
    repo_root_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # THE COMPLETION TEST, as CI runs it: no --binding, so both bindings are discovered.
    monkeypatch.chdir(repo_root_path)
    assert main(["--check"]) == EXIT_OK
    out = capsys.readouterr().out
    assert out.count("check: zero diff") == 2, "both bindings must be checked, not one"


def test_check_writes_nothing(repo_root_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Safe on a read-only checkout. Asserted by mtime rather than by content: a --check
    # that rewrote a byte-identical file would pass a content comparison and would still
    # have written to a tree it was told not to touch.
    monkeypatch.chdir(repo_root_path)
    migrations = repo_root_path / "verticals/mainline/db/migrations"
    before = {p.name: p.stat().st_mtime_ns for p in sorted(migrations.glob("*.sql"))}
    assert main(["--check"]) == EXIT_OK
    after = {p.name: p.stat().st_mtime_ns for p in sorted(migrations.glob("*.sql"))}
    assert before == after


def test_an_unbacked_projection_exits_one_and_names_the_column(
    repo_root_path: Path,
    write_templates: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The worker's second completion clause, through the interface CI uses. The real
    # reference binding, a fake template set: nothing in the committed tree is touched,
    # and the refusal is the one an operator would actually see.
    monkeypatch.chdir(repo_root_path)
    templates = write_templates([("9300_gate.sql.j2", PROJECTING)])
    code = main(
        [
            "--binding",
            "packages/trappoint-sql/refvertical/vertical.toml",
            "--templates",
            str(templates),
        ]
    )
    assert code == EXIT_REFUSED
    err = capsys.readouterr().err
    assert "blocking_check.reading_floor_met" in err
    assert "REFUSED" in err


def test_a_missing_binding_is_a_usage_error_not_a_refusal(
    repo_root_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo_root_path)
    assert main(["--binding", "verticals/nonexistent/vertical.toml"]) == EXIT_USAGE
    assert "no binding at" in capsys.readouterr().err


def test_a_missing_template_directory_is_a_refusal(
    repo_root_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deliberately NOT a usage error: the path was well-formed and the tree is wrong.
    # A wrapper told "you typed it wrong" would prompt a human; told "refused", it stops.
    monkeypatch.chdir(repo_root_path)
    code = main(
        [
            "--check",
            "--binding",
            "packages/trappoint-sql/refvertical/vertical.toml",
            "--templates",
            str(tmp_path / "absent"),
        ]
    )
    assert code == EXIT_REFUSED


FIXTURE_TEMPLATE = (
    "-- @file 9301_a.sql\n"
    "{{ header(file='9301_a.sql', title='a fixture', rationale='x', mi=['MI01']) }}\n\n"
    "CREATE TABLE {{ binding.schema }}.a (x INT8 NOT NULL PRIMARY KEY);\n"
)


def test_check_exits_one_when_a_committed_file_was_hand_edited(
    write_binding: Callable[..., Path],
    write_templates: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # In the THROWAWAY workspace, so the real tree is never mutated. `--check` renders
    # in memory and compares bytes, so a hand edit is a red build rather than a silent
    # divergence — which is the sentence every rendered header ends with.
    binding = write_binding()
    templates = write_templates([("9301_a.sql.j2", FIXTURE_TEMPLATE)])
    monkeypatch.chdir(binding.parent)
    argv = ["--binding", str(binding), "--templates", str(templates)]
    assert main(argv) == EXIT_OK
    target = binding.parent / "sql" / "9301_a.sql"
    target.write_bytes(target.read_bytes().replace(b"probe.a", b"probe.zzz"))
    assert main([*argv, "--check"]) == EXIT_REFUSED
    assert "9301_a.sql: diff" in capsys.readouterr().err


def test_list_names_the_reference_vertical_first(
    repo_root_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Not cosmetic: the reference vertical is the binding that must render before any
    # real one is trusted, so when the output scrolls past, the substrate's own proof is
    # at the top rather than buried under a vertical's forty files.
    monkeypatch.chdir(repo_root_path)
    assert main(["--list"]) == EXIT_OK
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert "refvertical" in lines[0]
    assert "verticals" in lines[1]


def test_discovery_finds_exactly_the_two_committed_bindings(repo_root_path: Path) -> None:
    found = [p.relative_to(repo_root_path).as_posix() for p in discover_bindings(repo_root_path)]
    assert found == [
        "packages/trappoint-sql/refvertical/vertical.toml",
        "verticals/mainline/vertical.toml",
    ]


def test_a_bad_flag_exits_two(repo_root_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # argparse's own exit code for an unrecognised option is 2, which is the code this
    # CLI assigns to "the invocation was wrong". They agree on purpose.
    monkeypatch.chdir(repo_root_path)
    with pytest.raises(SystemExit) as excinfo:
        main(["--no-such-flag"])
    assert excinfo.value.code == EXIT_USAGE
