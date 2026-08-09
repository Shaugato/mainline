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
from pathlib import Path
from typing import Any

import pytest
from _run_corpus import EXPECTED_COUNTS
from trappoint_recall.per.cli import main as per_cli
from trappoint_recall.per.receipt import PER_BOUND_SENTENCE
from trappoint_recall.per.verify import verify_receipt


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
    import trappoint_recall.per as per  # noqa: PLC0415 - the subject of the assertion

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
