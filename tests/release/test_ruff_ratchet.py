# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# I: QA-RATCHET-1 — the repository's lint debt is a counted, published number that may
#    fall and may not rise. A (rule, tree) pair recorded at 0 is a hard gate.
"""Tests for `scripts/qa/ruff_ratchet.py` — the counted ruff ratchet.

RED FIRST (PL-2: a suite that has never been red asserts nothing)
----------------------------------------------------------------
A ratchet that only ever prints "OK" proves nothing, so this file was run twice against
a deliberately neutered checker before it was accepted green. Both runs below were
executed on 2026-08-10 with ruff 0.16.1 / pytest 9.1.1 / CPython 3.13.14, command::

    .venv/Scripts/python.exe -m pytest tests/release/test_ruff_ratchet.py -q

RED RUN 1 — `scripts/qa/ruff_ratchet.py::compare` body replaced by `return [], []`,
i.e. a checker that measures the tree and then reports no regression. Verbatim result::

    FAILED ::test_the_checker_fires_when_a_baseline_entry_is_lower_than_reality
        AssertionError: expected exit 1 (ratchet regression), got 0
    FAILED ::test_a_zero_entry_is_a_hard_gate
        AssertionError: expected exit 1 (ratchet regression), got 0
    FAILED ::test_a_rule_absent_from_the_baseline_defaults_to_zero
        AssertionError: expected exit 1 (ratchet regression), got 0
    FAILED ::test_update_refuses_to_write_when_a_count_increased
        AssertionError: expected exit 1 (ratchet regression), got 0
    FAILED ::test_a_decrease_is_reported_as_an_improvement_not_a_regression
        assert 'improved' in 'ruff 0.16.1 | ... OK - no rule/tree count increased.\\n'
    FAILED ::test_update_tightens_a_stale_high_entry_downwards
        assert 165 == 160
    FAILED ::test_the_ratchet_passes_on_the_real_tree
    7 failed, 8 passed

`test_the_formatter_ratchet_refuses_an_increase` SURVIVED run 1, which is a fact worth
keeping: the formatter total is ratcheted by `compare_format` independently of the
per-rule `compare`, so neutering one does not disarm the other. Run 2 proved the other
half can fail too.

RED RUN 2 — `compare` restored; `compare_format` given `rec_total = max(rec_total,
total)`, i.e. a formatter ratchet that silently absorbs any increase. Verbatim result::

    FAILED ::test_the_formatter_ratchet_refuses_an_increase
    FAILED ::test_the_ratchet_passes_on_the_real_tree
    2 failed, 13 passed

Both edits were then reverted (`grep -c NEUTERED scripts/qa/ruff_ratchet.py` -> 0) and
the file was accepted green. Every regression assertion here is therefore known to be
capable of failing.

`test_the_ratchet_passes_on_the_real_tree` failed in both red runs for a THIRD and
unrelated reason, and the reason is worth stating: this wave has ten workers writing to
the tree concurrently, and `packages/trappoint-testkit/` grew by several modules while
these runs were in flight, taking the finding count from 793 to 820 in about twelve
minutes. That is the ratchet doing its job on live traffic rather than a fixture. The
published baseline is a snapshot; see qa/README.md for when to re-take it.

The tests below run ruff over the real tree exactly twice (a module-scoped fixture) and
replay that one measurement into every regression scenario, so each assertion is made
against measured reality rather than a fabricated fixture.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "qa" / "ruff_ratchet.py"
PUBLISHED_BASELINE = REPO_ROOT / "qa" / "ruff-ratchet.json"
SUBSTRATE = "packages/trappoint-*"


def _import_checker():
    spec = importlib.util.spec_from_file_location("ruff_ratchet_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        pytest.fail(f"cannot import {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rr = _import_checker()


@pytest.fixture(scope="module")
def measured():
    """One real observation of the tree. Ruff runs twice for the whole module."""
    ruff = rr.find_ruff()
    lint_counts, lint_total = rr.measure_lint(ruff)
    fmt_by_tree, fmt_total = rr.measure_format(ruff)
    return rr.Measurement(lint_counts, lint_total, fmt_by_tree, fmt_total)


@pytest.fixture
def replay(monkeypatch, measured, tmp_path):
    """Return run(doc, *flags) -> (exit_code, stdout, baseline_path).

    The measurement is replayed rather than re-taken so the tree cannot shift between
    the baseline being synthesised and the checker reading it.
    """
    monkeypatch.setattr(rr, "measure_lint", lambda _r: (measured.lint_counts, measured.lint_total))
    monkeypatch.setattr(rr, "measure_format", lambda _r: (measured.fmt_by_tree, measured.fmt_total))

    def run(doc, *flags, capsys):
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        capsys.readouterr()
        code = rr.main(["--baseline", str(path), *flags])
        return code, capsys.readouterr().out, path

    return run


@pytest.fixture
def truthful_doc(measured):
    """A baseline that agrees with the tree exactly. Every scenario below perturbs it."""
    ruff = rr.find_ruff()
    return rr.build_baseline(
        rr.ruff_version(ruff),
        measured.lint_counts,
        measured.lint_total,
        measured.fmt_by_tree,
        measured.fmt_total,
        {},
    )


def biggest(measured):
    """The (code, tree, count) with the largest count — a stable, obvious lever."""
    entries = [
        (code, tree, n) for code, trees in measured.lint_counts.items() for tree, n in trees.items()
    ]
    return max(entries, key=lambda e: (e[2], e[0], e[1]))


# --------------------------------------------------------------------------------------
# The regression half. Each of these was observed failing against a neutered `compare`.
# --------------------------------------------------------------------------------------


def test_the_checker_fires_when_a_baseline_entry_is_lower_than_reality(
    replay, truthful_doc, measured, capsys
):
    code, tree, n = biggest(measured)
    truthful_doc["lint"]["rules"][code][tree] = n - 1

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 1, f"expected exit 1 (ratchet regression), got {exit_code}"
    assert "REFUSED" in out
    assert f"rule={code}" in out
    assert f"tree={tree}" in out
    assert f"baseline={n - 1}" in out
    assert f"measured={n}" in out


def test_a_zero_entry_is_a_hard_gate(replay, truthful_doc, measured, capsys):
    code, tree, _ = biggest(measured)
    truthful_doc["lint"]["rules"][code][tree] = 0

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 1, f"expected exit 1 (ratchet regression), got {exit_code}"
    assert "[HARD GATE: baseline is 0]" in out
    assert f"rule={code}" in out


def test_a_rule_absent_from_the_baseline_defaults_to_zero(replay, truthful_doc, measured, capsys):
    code, _tree, _ = biggest(measured)
    del truthful_doc["lint"]["rules"][code]

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 1, f"expected exit 1 (ratchet regression), got {exit_code}"
    assert f"rule={code}" in out
    assert "baseline=0" in out


def test_the_formatter_ratchet_refuses_an_increase(replay, truthful_doc, measured, capsys):
    truthful_doc["format"]["unformatted_files"] = measured.fmt_total - 1

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 1, f"expected exit 1 (ratchet regression), got {exit_code}"
    assert "FORMAT REGRESSION" in out
    assert f"baseline={measured.fmt_total - 1}" in out
    assert f"measured={measured.fmt_total}" in out


def test_update_refuses_to_write_when_a_count_increased(replay, truthful_doc, measured, capsys):
    code, tree, n = biggest(measured)
    truthful_doc["lint"]["rules"][code][tree] = n - 1
    before = json.dumps(truthful_doc, indent=2)

    exit_code, out, path = replay(truthful_doc, "--update", capsys=capsys)

    assert exit_code == 1, f"expected exit 1 (ratchet regression), got {exit_code}"
    assert "REFUSED" in out
    assert path.read_text(encoding="utf-8") == before, "--update must never raise a count"


def test_ruff_version_drift_is_refused(replay, truthful_doc, capsys):
    truthful_doc["ruff_version"] = "0.0.1-not-a-real-ruff"

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 2, f"expected exit 2 (tooling refusal), got {exit_code}"
    assert "RUFF VERSION DRIFT" in out


# --------------------------------------------------------------------------------------
# The permissive half: falling counts are fine, and only --update writes.
# --------------------------------------------------------------------------------------


def test_a_decrease_is_reported_as_an_improvement_not_a_regression(
    replay, truthful_doc, measured, capsys
):
    code, tree, n = biggest(measured)
    truthful_doc["lint"]["rules"][code][tree] = n + 5

    exit_code, out, _ = replay(truthful_doc, capsys=capsys)

    assert exit_code == 0, f"a falling count is not a regression; got exit {exit_code}"
    assert "improved" in out
    assert f"rule={code}" in out


def test_update_tightens_a_stale_high_entry_downwards(replay, truthful_doc, measured, capsys):
    code, tree, n = biggest(measured)
    truthful_doc["lint"]["rules"][code][tree] = n + 5

    exit_code, _out, path = replay(truthful_doc, "--update", capsys=capsys)

    assert exit_code == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["lint"]["rules"][code][tree] == n


def test_a_truthful_baseline_is_not_rewritten_without_update(replay, truthful_doc, capsys):
    exit_code, out, path = replay(truthful_doc, capsys=capsys)

    assert exit_code == 0
    assert "REFUSED" not in out
    assert json.loads(path.read_text(encoding="utf-8"))["lint"] == truthful_doc["lint"]


# --------------------------------------------------------------------------------------
# The published artefact itself.
# --------------------------------------------------------------------------------------


def test_the_ratchet_passes_on_the_real_tree(capsys):
    """End to end, nothing patched: `python scripts/qa/ruff_ratchet.py` exits 0."""
    capsys.readouterr()
    exit_code = rr.main([])
    out = capsys.readouterr().out
    assert exit_code == 0, f"ratchet refused the tree as committed:\n{out}"


def test_the_published_baseline_records_the_ruff_that_took_it():
    doc = json.loads(PUBLISHED_BASELINE.read_text(encoding="utf-8"))
    installed = rr.ruff_version(rr.find_ruff())
    assert doc["ruff_version"] == installed, (
        f"baseline was taken with ruff {doc['ruff_version']} but ruff {installed} is "
        "installed; a ratchet taken with a different ruff is not a ratchet"
    )
    assert doc["schema"] == rr.SCHEMA


def test_the_load_bearing_families_are_hard_gated_at_zero_for_the_substrate():
    doc = json.loads(PUBLISHED_BASELINE.read_text(encoding="utf-8"))
    policy = doc["policy"]["zero_tolerance"]
    assert policy["tree"] == SUBSTRATE
    rules = doc["lint"]["rules"]
    for code in policy["at_zero_today"]:
        assert code in rules, f"{code} is declared a hard gate but is not recorded in lint.rules"
        assert rules[code].get(SUBSTRATE) == 0, (
            f"{code} is declared at zero for {SUBSTRATE} but the baseline records "
            f"{rules[code].get(SUBSTRATE)!r}"
        )


def test_declared_debt_is_recorded_at_its_true_count_not_waived():
    """T201/S608 in the substrate are debt, not exceptions. They must still be counted."""
    doc = json.loads(PUBLISHED_BASELINE.read_text(encoding="utf-8"))
    debt = doc["policy"]["zero_tolerance"]["declared_debt"]
    rules = doc["lint"]["rules"]
    for code in debt:
        assert rules.get(code, {}).get(SUBSTRATE, 0) > 0, (
            f"{code} is described as declared debt but the baseline records no findings "
            f"for it in {SUBSTRATE}; delete the debt note or fix the count"
        )


def test_the_checker_never_reformats_and_never_autofixes():
    """The ratchet's whole premise is that it does not rewrite other workers' files."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in ('"--fix"', '"--unsafe-fixes"', '"--fix-only"'):
        assert forbidden not in source, f"ratchet must never invoke ruff {forbidden}"
    assert source.count('"format", "--check"') == 1
    assert '"format", "."' not in source


def test_classify_buckets_every_tree():
    cases = {
        "packages/trappoint-jcs/src/x.py": SUBSTRATE,
        "packages/trappoint-recall/tests/t.py": SUBSTRATE,
        "packages/mainline-boundary/src/x.py": "packages/mainline-*",
        "packages/somethingelse/x.py": "other/",
        "verticals/mainline/packages/mainline-anchor/src/x.py": "verticals/",
        "tests/release/test_ruff_ratchet.py": "tests/",
        "scripts/qa/ruff_ratchet.py": "scripts/",
        "skills/whatever/scripts/x.py": "other/",
        "conftest.py": "other/",
    }
    for path, expected in cases.items():
        assert rr.classify(path) == expected, path
    assert set(cases.values()) <= set(rr.TREES)
