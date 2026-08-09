# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Agreement with the repository: the shipped views, VERIFY.md, and the film's strings."""

from __future__ import annotations

from judge import drift
from judge.pack import parse_pack

CREATE_VIEW_SAMPLE = """
CREATE VIEW mainline_audit.v_example AS
  WITH g AS (
    SELECT p.site_id AS site_id, count(*) AS n FROM mainline.permit p GROUP BY p.site_id
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id      AS site_id,
         g.n            AS n,
         (SELECT count(*) FROM mainline.override_ledger o
           WHERE o.site_id = g.site_id) AS overrides_30d,
         t.group_count  AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.site_id
   LIMIT 25;
"""


class TestViewProjectionParser:
    def test_it_reads_the_outer_projection_and_not_the_ctes(self):
        columns = drift.view_columns(CREATE_VIEW_SAMPLE)
        assert columns == ("site_id", "n", "overrides_30d", "group_count", "rows_complete")

    def test_a_correlated_subquery_is_one_item_not_several(self):
        assert "overrides_30d" in drift.view_columns(CREATE_VIEW_SAMPLE)
        assert "count" not in drift.view_columns(CREATE_VIEW_SAMPLE)


class TestNormalisation:
    def test_wrapping_does_not_count_as_drift(self):
        a = "SELECT a,\n  b\n FROM t\n LIMIT 25;"
        b = "SELECT a, b FROM t LIMIT 25"
        assert drift.normalise_statement(a) == drift.normalise_statement(b)

    def test_a_changed_page_does_count_as_drift(self):
        a = drift.normalise_statement("SELECT a FROM t LIMIT 25;")
        b = drift.normalise_statement("SELECT a FROM t LIMIT 10;")
        assert a != b

    def test_a_trailing_comment_is_not_part_of_the_statement(self):
        assert (
            drift.normalise_statement("SELECT a FROM t LIMIT 25; -- must fail")
            == "SELECT a FROM t LIMIT 25"
        )


class TestShippedPackAgreesWithTheRepository:
    def test_no_drift_failures(self, pack, repo_root, judge_dir):
        findings = drift.check_drift(pack, repo_root=repo_root, judge_dir=judge_dir)
        failures = [f.render() for f in findings if f.severity == "fail"]
        assert not failures, "\n".join(failures)

    def test_every_authority_was_actually_read(self, pack, repo_root, judge_dir):
        # A warn from this module means an authority was ABSENT and the check did not run.
        # In this repository every one of them is present, so a warning here is a
        # regression in coverage rather than a cosmetic issue.
        findings = drift.check_drift(pack, repo_root=repo_root, judge_dir=judge_dir)
        warnings = [f.render() for f in findings if f.severity == "warn"]
        assert not warnings, "\n".join(warnings)

    def test_every_bound_explain_fits_the_character_cap(self, pack, repo_root):
        bounds = drift.bound_statements(pack, repo_root=repo_root)
        assert bounds, "the pack carries no EXPLAIN question to measure"
        for bound in bounds:
            assert bound.fits, f"{bound.qid}: {bound.statement_chars} characters"
            assert bound.sql

    def test_the_film_requires_substrings_of_the_plan(self, repo_root):
        required = drift.required_plan_substrings(repo_root)
        assert "vector search" in required
        assert "prefix spans" in required

    def test_a_prompt_dropped_from_the_pack_is_reported(self, pack, repo_root, judge_dir):
        # The drift check exists to notice a statement a judge still reads in VERIFY.md that
        # this pack no longer carries. Prove it notices.
        document = dict(pack.raw)
        document["questions"] = [q for q in document["questions"] if q.get("id") != "Q05"]
        document["verify_md_exemptions"] = []
        mutated = parse_pack(document, source=pack.source)
        findings = drift.check_drift(mutated, repo_root=repo_root, judge_dir=judge_dir)
        assert any(f.check == "verify-md-drift" and f.severity == "fail" for f in findings)
