# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The standalone verifier, run against a receipt this suite actually produced.

Two people check this artefact and they get different bundles.

**Boundary mode** is what an opposing expert, a regulator or an insurer gets: the receipt
alone. It establishes that the cut is where the receipt says it is, against a root committed
before the dispute existed, and discloses nothing about the suppressed set.

**Full mode** is what a discovery order produces: the receipt *plus* the disclosed
``mainline_meas.recall_candidate`` rows. It recomputes the root from scratch, which is what
makes hand-exclusion detectable.

The excision tests are the point of the mechanism, so they are run twice over: the untampered
bundle must PASS, and each tampered bundle must FAIL **naming the check that caught it**. A
tamper test that only asserted "not ok" would pass against a verifier that had stopped
checking anything at all.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
from _run_corpus import EXPECTED_COUNTS

import trappoint_recall
from trappoint_recall.per.cli import main as per_cli
from trappoint_recall.per.receipt import PER_BOUND_SENTENCE
from trappoint_recall.per.verify import verify_receipt

#: ``…/packages/trappoint-recall/src`` — the one path a stranger needs on ``PYTHONPATH``.
PACKAGE_SRC = Path(trappoint_recall.__file__).resolve().parent.parent

#: The distribution root, for the entry-point declaration.
PACKAGE_ROOT = PACKAGE_SRC.parent

#: The console script the recall lead's plan and ``spec/wire/candidate-commitment.md`` name.
CONSOLE_SCRIPT = "trappoint-recall-verify-per"
CONSOLE_TARGET = "trappoint_recall.per.cli:main"


def disclosed_rows(outcome) -> list[dict[str, Any]]:
    """The disclosed candidate set, in ``mainline_meas.recall_candidate`` row form."""
    return [
        {
            "event_id": str(row.event_id),
            "p_relevant": row.p_relevant,
            "tau_applied": row.tau_applied,
            "outcome": row.outcome,
        }
        for row in outcome.candidates
    ]


def failed(report) -> set[str]:
    """The names of the checks that failed."""
    return {check.name for check in report.failures}


def test_the_verifier_accepts_an_honest_receipt_in_full_mode(clean_outcome) -> None:
    """Green half of the pair: without this, every failure below proves nothing."""
    report = verify_receipt(clean_outcome.receipt.to_json(), disclosed_rows(clean_outcome))
    assert report.mode == "full"
    assert report.ok, report.to_text()
    assert len(report.checks) > 10


def test_the_verifier_accepts_the_receipt_alone(clean_outcome) -> None:
    """Boundary mode discloses only the pair, and still establishes where the cut is."""
    report = verify_receipt(clean_outcome.receipt.to_json())
    assert report.mode == "boundary"
    assert report.ok, report.to_text()
    document = clean_outcome.receipt.to_json()
    assert "candidates" not in document, "the receipt must not carry the suppressed set"


def test_one_candidate_removed_breaks_the_root(clean_outcome) -> None:
    """The naive excision: drop a row and hope nobody recomputes the commitment."""
    rows = disclosed_rows(clean_outcome)
    kept = [row for row in rows if row["outcome"] == "silenced"]
    assert kept, "the corpus must silence something or this test asserts nothing"
    rows.remove(kept[0])

    report = verify_receipt(clean_outcome.receipt.to_json(), rows)
    assert not report.ok
    names = failed(report)
    assert "root_matches" in names
    assert "leaf_count" in names


def test_a_renumbered_excision_still_breaks_the_root(clean_outcome) -> None:
    """The careful excision: remove a leaf **and** renumber, so the ordinals stay contiguous.

    This is the attack the ordinal-inside-the-preimage design exists to defeat. The disclosed
    set is re-quantised and re-sorted from row form, so ordinals are contiguous, the order is
    correct, no candidate appears twice — and the root is still wrong, because every leaf
    after the removed one now hashes at a different position.
    """
    rows = [row for row in disclosed_rows(clean_outcome) if row["outcome"] != "deduped"]
    assert len(rows) == EXPECTED_COUNTS["n_candidates"] - EXPECTED_COUNTS["n_deduped"]

    report = verify_receipt(clean_outcome.receipt.to_json(), rows)
    assert not report.ok
    names = failed(report)
    assert "root_matches" in names, report.to_text()
    assert "ordinals_contiguous" not in names, (
        "the excision was performed carefully, so contiguity is not what catches it — the "
        "commitment is"
    )


def test_a_rescored_candidate_breaks_the_root(clean_outcome) -> None:
    """Retro-tuning one score after the fact is the same excision by another route."""
    rows = disclosed_rows(clean_outcome)
    target = next(row for row in rows if row["outcome"] == "silenced")
    target["p_relevant"] = 0.999999

    report = verify_receipt(clean_outcome.receipt.to_json(), rows)
    assert not report.ok
    assert "root_matches" in failed(report)


def test_a_moved_cut_is_caught_without_the_candidate_set(clean_outcome) -> None:
    """Retro-tuning ``s`` alone is refused by the boundary disclosure it contradicts."""
    document = clean_outcome.receipt.to_json()
    document["s"] = document["s"] - 1

    report = verify_receipt(document)
    assert not report.ok
    assert {"boundary_position[s]", "boundary_position[s+1]"} & failed(report)


def test_the_bound_travels_with_every_report(clean_outcome) -> None:
    """A proof that overclaims is worse than none, so the bound is a field, not a footnote."""
    report = verify_receipt(clean_outcome.receipt.to_json(), disclosed_rows(clean_outcome))
    assert report.to_json()["claim_bound"] == PER_BOUND_SENTENCE
    assert PER_BOUND_SENTENCE in report.to_text()
    assert clean_outcome.receipt.to_json()["claim_bound"] == PER_BOUND_SENTENCE


def test_the_verifier_depends_on_the_standard_library_alone() -> None:
    """The tool the other side checks us with must not be ours to change.

    A stranger with a stock Python and no wheels must be able to run it, which means no
    ``pydantic``, no ``numpy``, no ``cryptography``, and nothing from the rest of this
    package either.
    """
    from trappoint_recall import per

    root = Path(per.__file__).parent
    allowed_prefixes = ("trappoint_recall.per",)
    banned = {"pydantic", "numpy", "cryptography", "boto3", "anthropic", "psycopg"}
    for source in sorted(root.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            module = stripped.split()[1]
            root_module = module.split(".")[0]
            assert root_module not in banned, f"{source.name} imports {module}"
            if root_module == "trappoint_recall":
                assert module.startswith(allowed_prefixes), (
                    f"{source.name} imports {module}, which is outside the PER subpackage; "
                    "the verifier's whole dependency floor is the standard library"
                )


def test_the_cli_accepts_and_rejects_with_the_right_exit_status(
    clean_outcome, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``0`` verified, ``1`` refused, ``2`` unreadable — three answers, never confused."""
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(clean_outcome.receipt.to_json_text(), encoding="utf-8")

    honest = tmp_path / "candidates.json"
    honest.write_text(json.dumps(disclosed_rows(clean_outcome)), encoding="utf-8")

    assert per_cli([str(receipt_path)]) == 0
    assert per_cli([str(receipt_path), "--candidates", str(honest)]) == 0

    tampered_rows = disclosed_rows(clean_outcome)
    tampered_rows.pop()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(tampered_rows), encoding="utf-8")
    assert per_cli([str(receipt_path), "--candidates", str(tampered)]) == 1

    assert per_cli([str(tmp_path / "absent.json")]) == 2

    captured = capsys.readouterr()
    assert PER_BOUND_SENTENCE in captured.out


def test_the_cli_emits_a_machine_readable_report(
    clean_outcome, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--json`` is what a nightly patrol and an attestation payload consume."""
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(clean_outcome.receipt.to_json_text(), encoding="utf-8")
    assert per_cli([str(receipt_path), "--json"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["ok"] is True
    assert document["mode"] == "boundary"
    assert document["claim_bound"] == PER_BOUND_SENTENCE


def _stock_python(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the interpreter with ``-S``: no ``site``, therefore no installed distribution.

    ``-S`` removes ``site-packages`` from ``sys.path`` entirely, leaving the standard library,
    the interpreter's own directories and whatever ``PYTHONPATH`` names. Pointing
    ``PYTHONPATH`` at this distribution's ``src`` and nothing else reproduces, on this machine,
    the situation the dependency floor is a promise about: a stranger with a stock Python, this
    source tree, and not one wheel installed.
    """
    environment = dict(os.environ)
    # Overwritten, not appended: the parent process may have several workspace packages on
    # PYTHONPATH, and inheriting them would put the rest of the repository back within reach.
    environment["PYTHONPATH"] = str(PACKAGE_SRC)
    return subprocess.run(
        [sys.executable, "-S", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_the_isolation_this_suite_relies_on_is_real() -> None:
    """Green-half of the pair below: under ``-S`` the installed distributions are gone.

    Without this, the next test could pass because the verifier quietly imported ``pydantic``
    from a ``site-packages`` that was still on the path, and the dependency-floor claim would
    be asserted against an environment that never tested it.
    """
    present = _stock_python("-c", "import trappoint_recall.per.verify")
    assert present.returncode == 0, present.stderr

    absent = _stock_python("-c", "import pydantic")
    assert absent.returncode != 0, (
        "pydantic is importable under -S, so this environment does not isolate anything and "
        "the dependency-floor assertion below would be vacuous"
    )
    assert "ModuleNotFoundError" in absent.stderr


def test_the_verifier_runs_on_a_stock_interpreter_with_nothing_installed(
    clean_outcome, tmp_path: Path
) -> None:
    """The dependency floor, executed rather than reasoned about.

    ``spec/wire/candidate-commitment.md`` section 10 makes this a requirement of the *format*,
    not a property of one implementation: the person a silence receipt is written for does not
    trust us, so the tool they check it with cannot be ours to change. The static import scan
    above proves no banned name is written down; this proves the module tree actually loads and
    produces the right three exit statuses with no third-party package reachable at all.
    """
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(clean_outcome.receipt.to_json_text(), encoding="utf-8")

    honest = tmp_path / "candidates.json"
    honest.write_text(json.dumps(disclosed_rows(clean_outcome)), encoding="utf-8")

    tampered_rows = disclosed_rows(clean_outcome)
    tampered_rows.pop()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(tampered_rows), encoding="utf-8")

    verified = _stock_python("-m", "trappoint_recall.per", str(receipt_path))
    assert verified.returncode == 0, verified.stderr
    assert PER_BOUND_SENTENCE in verified.stdout

    full = _stock_python(
        "-m", "trappoint_recall.per", str(receipt_path), "--candidates", str(honest)
    )
    assert full.returncode == 0, full.stderr

    refused = _stock_python(
        "-m", "trappoint_recall.per", str(receipt_path), "--candidates", str(tampered)
    )
    assert refused.returncode == 1, refused.stderr
    assert "FAIL" in refused.stdout

    unreadable = _stock_python("-m", "trappoint_recall.per", str(tmp_path / "absent.json"))
    assert unreadable.returncode == 2


def test_the_console_script_is_declared_under_the_name_the_spec_publishes() -> None:
    """``trappoint-recall-verify-per`` is the name the specification tells a reader to run.

    The module invocation ``python -m trappoint_recall.per`` is asserted above and is what the
    specification calls the reference verifier, so nothing is *broken* while this declaration is
    absent — but the published name should resolve, and it lives in a file this worker does not
    own (``packages/trappoint-recall/pyproject.toml``, allocated to ``recall-eval-harness``).
    A missing declaration is therefore reported as a cross-domain dependency with the exact line
    to add, never silently passed over.
    """
    manifest = PACKAGE_ROOT / "pyproject.toml"
    assert manifest.is_file(), f"{manifest} is the distribution manifest and must exist"
    scripts = (
        tomllib.loads(manifest.read_text(encoding="utf-8")).get("project", {}).get("scripts", {})
    )
    if CONSOLE_SCRIPT not in scripts:
        pytest.skip(
            f"{manifest.name} does not declare {CONSOLE_SCRIPT!r}. It is one line in a file "
            f'owned by recall-eval-harness:  {CONSOLE_SCRIPT} = "{CONSOLE_TARGET}"  under '
            "[project.scripts]. Reported rather than assumed; the reference invocation "
            "'python -m trappoint_recall.per' is asserted by the tests above and works today."
        )
    assert scripts[CONSOLE_SCRIPT] == CONSOLE_TARGET
