# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The generated page cannot drift from the pack, and the validator has been red."""

from __future__ import annotations

from pathlib import Path

from judge.render import render_pack
from judge.runner import run_via_mcp, run_via_sql
from judge.selftest import self_test


class TestGeneratedPage:
    def test_the_committed_page_matches_the_pack(self, pack, repo_root, judge_dir: Path):
        expected = render_pack(pack, repo_root=repo_root)
        committed = (judge_dir / "PACK.md").read_text(encoding="utf-8")
        assert committed == expected, (
            "PACK.md has drifted from QUESTIONS.yaml. Run "
            "`python verticals/mainline/demo/judge/cli.py render`. A page a judge reads that "
            "the validator does not check is the failure this pack exists to prevent."
        )

    def test_rendering_twice_produces_the_same_bytes(self, pack, repo_root):
        assert render_pack(pack, repo_root=repo_root) == render_pack(pack, repo_root=repo_root)

    def test_the_page_carries_every_question(self, pack, judge_dir: Path):
        page = (judge_dir / "PACK.md").read_text(encoding="utf-8")
        for question in pack:
            assert f"### {question.qid} ·" in page, question.qid

    def test_the_page_states_the_measured_bound_length(self, judge_dir: Path):
        page = (judge_dir / "PACK.md").read_text(encoding="utf-8")
        assert "Measured, not assumed." in page
        assert "characters of headroom" in page


class TestValidatorGoesRed:
    def test_every_planted_violation_is_caught(self, repo_root, pack_path: Path, judge_dir: Path):
        result = self_test(repo_root=repo_root, source=pack_path, judge_dir=judge_dir)
        assert result.ok, "planted violations that went unnoticed:\n" + "\n".join(result.missed)
        assert len(result.caught) >= 10


class TestRunnerRefusesToPassVacuously:
    def test_no_dsn_is_a_not_run_and_exits_three(self, pack, repo_root, monkeypatch):
        for name in ("TRAPPOINT_DSN", "MAINLINE_DSN", "COCKROACH_URL"):
            monkeypatch.delenv(name, raising=False)
        report = run_via_sql(pack, repo_root=repo_root, dsn=None)
        assert not report.ran
        assert report.exit_code() == 3
        assert "NOTHING was executed" in report.reason

    def test_no_mcp_key_is_a_not_run_and_exits_three(self, pack, repo_root, monkeypatch):
        monkeypatch.delenv("MAINLINE_MCP_API_KEY", raising=False)
        monkeypatch.delenv("MAINLINE_MCP_CLUSTER_ID", raising=False)
        report = run_via_mcp(pack, repo_root=repo_root)
        assert not report.ran
        assert report.exit_code() == 3
        assert "NOTHING was sent" in report.reason or "not importable" in report.reason

    def test_the_negatives_are_never_scored_over_pgwire(self, pack):
        # Over a SQL connection as cluster admin these statements SUCCEED. Marking them
        # mcp_only is what stops a green local run from claiming the opposite of the truth.
        for question in pack.negatives():
            assert question.channel == "mcp_only", question.qid
