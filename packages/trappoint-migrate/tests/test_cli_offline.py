# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Everything the CLI can prove without a cluster.

The exit-code split is the point of most of these. CI and the `justfile` both branch on
it, and a runner that returned 1 for "you typed it wrong" would make a red conformance
lane indistinguishable from a broken invocation.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from trappoint_migrate.cli import EXIT_OK, EXIT_REFUSED, EXIT_USAGE, main, main_migrate
from trappoint_migrate.crdb import pinned_image
from trappoint_migrate.errors import UsageError

COMPOSE = """
services:
  crdb:
    # trappoint:crdb-image-pin
    image: cockroachdb/cockroach:v26.2.5
"""


def test_top_level_help_lists_delegated_verbs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == EXIT_OK
    out = capsys.readouterr().out
    assert "migrate" in out
    assert "render" in out
    assert "trappoint-sql" in out, "a fresh clone must be told which distribution owns the verb"


def test_unknown_verb_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["conjure"]) == EXIT_USAGE
    assert "unknown verb" in capsys.readouterr().err


def test_delegated_verb_names_its_distribution_when_absent(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # UNSTALED 2026-08-08. This test was written while `packages/trappoint-sql` was a
    # later worker's deliverable, so merely invoking `render` exercised the missing
    # -distribution path for free. trappoint-sql has since landed, and the call now
    # delegates for real and fails with a render error instead — so the assertion was
    # passing on an accident of build order and then broke on its own success.
    #
    # The guarantee is still worth holding: a fresh clone that has not run `uv sync`
    # must be told WHICH distribution owns the verb, not handed an ImportError. So the
    # absence is now simulated explicitly rather than relied upon.
    real_import = builtins.__import__

    def refuse_trappoint_sql(name: str, *a: object, **kw: object) -> object:
        if name.startswith("trappoint_sql"):
            raise ImportError(f"simulated: {name} is not installed")
        return real_import(name, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", refuse_trappoint_sql)

    code = main(["render", "--binding", "x"])
    assert code == EXIT_USAGE
    err = capsys.readouterr().err
    assert "trappoint-sql" in err
    assert "uv sync --package" in err


def test_delegated_verb_actually_delegates_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The other half, which the original test could not express because the
    # distribution did not exist yet: with trappoint-sql installed, `render` must reach
    # the real implementation. A non-existent binding is a RENDER error, and crucially
    # NOT the "not installed" message — that message reappearing here would mean
    # delegation had silently regressed to the fallback path.
    code = main(["render", "--binding", "x"])
    err = capsys.readouterr().err
    assert "uv sync --package" not in err, "delegation regressed to the not-installed path"
    assert code != EXIT_OK


def test_lint_on_an_empty_tree_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main_migrate(["lint", "--root", str(tmp_path)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "0 file(s) checked" in out
    assert "no findings" in out


def test_lint_reports_and_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "0001_x.sql").write_text("-- MI01\nCREATE TABLE t (id SERIAL);\n", encoding="utf-8")
    assert main_migrate(["lint", "--root", str(tmp_path)]) == EXIT_REFUSED
    assert "banned-token:serial" in capsys.readouterr().out


def test_missing_dsn_is_a_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TRAPPOINT_DSN", raising=False)
    monkeypatch.delenv("LOCAL_DSN", raising=False)
    assert main_migrate(["status", "--migrations", str(tmp_path)]) == EXIT_USAGE
    assert "no DSN" in capsys.readouterr().err


def test_unreachable_cluster_is_refused_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Port 1 is reserved and never listening. The distinction being asserted is that
    # "there was no database" surfaces as a refusal with a message, not a traceback.
    code = main_migrate(
        [
            "status",
            "--dsn",
            "postgresql://root@127.0.0.1:1/defaultdb?sslmode=disable&connect_timeout=1",
            "--migrations",
            str(tmp_path),
        ]
    )
    assert code == EXIT_REFUSED
    assert "trappoint migrate" in capsys.readouterr().err


def test_force_without_incident_is_rejected_by_the_parser() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main_migrate(["force", "0001_x", "--resolve", "applied", "--dsn", "x"])
    assert excinfo.value.code == EXIT_USAGE


def test_force_without_resolve_is_rejected_by_the_parser() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main_migrate(["force", "0001_x", "--incident", "INC-1", "--dsn", "x"])
    assert excinfo.value.code == EXIT_USAGE


def test_image_reads_the_single_version_constant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text(COMPOSE, encoding="utf-8")
    assert main_migrate(["image", "--compose", str(compose)]) == EXIT_OK
    assert capsys.readouterr().out.strip() == "cockroachdb/cockroach:v26.2.5"


def test_image_refuses_when_the_pin_marker_is_gone(tmp_path: Path) -> None:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  crdb:\n    image: cockroachdb/cockroach:v26.2.5\n", "utf-8")
    with pytest.raises(UsageError, match="crdb-image-pin"):
        pinned_image(compose)


def test_repository_compose_carries_the_pin() -> None:
    # The one constant, in one place, actually present in the shipped compose file.
    root = Path(__file__).resolve().parents[3]
    image = pinned_image(root / "compose.yaml")
    assert image.startswith("cockroachdb/cockroach:v")
