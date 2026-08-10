# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The release lane's one irreducible assertion: the database refuses the merge.

This module runs ``scripts/proof/gate_refusal.py`` end to end against a cluster and
asserts, from the evidence the script emits, that:

* the migration chain reached ``0115_fn_permit_merge_gate``;
* every migration that did not apply is attributable to one of the five enumerated
  tables that have no producer — an *unexplained* failure fails this test, which is how
  a syntax error anywhere in the tree becomes visible here rather than three weeks later;
* a merge attempted with an open, undisposed obligation was **REFUSED**, with the exact
  SQLSTATE and the exact exhibit ``spec/conformance/manifest.toml`` fixes for CF-01;
* a merge attempted against a counter forced to zero was **REFUSED** by
  ``mainline.fn_permit_merge_gate`` (CF-03) — the case no CHECK can hold;
* the same merge was **ADMITTED** once a disposition was signed.

The last one is not a formality. **A gate that always refuses is a broken gate**, and a
release test that asserted only the refusal would pass against a schema in which nothing
can ever merge.

PL-2 — RED BEFORE GREEN
-----------------------
This test was written before the defect it depends on was fixed, run, and observed RED.
The verbatim output of that red run and of the green run that followed are recorded in
``docs/release/gate-refusal-proof.md``. A suite that has never been red asserts nothing.

THE CLUSTER
-----------
No container is started here. The DSN comes from the environment, under any of the four
spellings the repository's fixtures already honour — ``MAINLINE_TEST_DSN``,
``TRAPPOINT_DSN``, ``COCKROACH_URL``, ``CRDB_URL`` — so this test joins whatever session
cluster the testkit has stood up rather than adding a fourteenth one. With none set, or
with none reachable, the test SKIPS: "there was no database" is not evidence that the
gate admitted anything, and reporting it as a failure would train a reader to ignore it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROOF = REPO_ROOT / "scripts" / "proof" / "gate_refusal.py"

#: The seam recorded in `docs/leads/quality-repair.md` §1.4: every cluster fixture in the
#: repository checks these first, before reaching for Docker.
DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "TRAPPOINT_DSN", "COCKROACH_URL", "CRDB_URL", "LOCAL_DSN")

#: A database of its own, so this lane can never disturb another worker's cluster state.
PROOF_DATABASE = "release_gate_refusal_proof"

CF01_SQLSTATE, CF01_EXHIBIT = "23514", "gate_closed_when_issued"
CF03_SQLSTATE, CF03_EXHIBIT = "P0001", "mainline.fn_permit_merge_gate"


def _dsn() -> str | None:
    for name in DSN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return None


@pytest.fixture(scope="module")
def proof(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Run the proof once and hand every test the evidence it emitted."""
    dsn = _dsn()
    if dsn is None:
        pytest.skip(
            "no cluster DSN. Set one of " + ", ".join(DSN_ENV_NAMES) + " to run the release proof."
        )
    assert PROOF.is_file(), f"the proof script is missing: {PROOF}"

    out = tmp_path_factory.mktemp("gate-refusal") / "proof.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(PROOF),
            "--dsn",
            dsn,
            "--database",
            PROOF_DATABASE,
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=900,
        check=False,
    )
    if completed.returncode == 2:
        pytest.skip(
            "the proof could not reach a cluster (exit 2), which is not evidence about the "
            f"gate:\n{completed.stderr.strip()}"
        )
    assert out.is_file(), (
        "the proof wrote no evidence file. stdout:\n"
        f"{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    evidence = json.loads(out.read_text(encoding="utf-8"))
    evidence["_stdout"] = completed.stdout
    evidence["_stderr"] = completed.stderr
    evidence["_returncode"] = completed.returncode
    return evidence


def test_the_chain_reached_the_merge_gate(proof: dict) -> None:
    chain = proof["chain"]
    assert chain["reached_0115_fn_permit_merge_gate"], (
        "the migration chain never reached 0115_fn_permit_merge_gate, so nothing below is a "
        "statement about the gate. Unexplained failures: "
        + json.dumps(chain["failures_unexplained"], indent=2)
    )


def test_no_migration_failed_for_an_unexplained_reason(proof: dict) -> None:
    """Every migration that did not apply must name one of the five unproduced tables.

    This is the assertion that was RED before ``0049z_meas_mutation_result.sql`` stopped
    declaring a column called ``family`` — a CockroachDB reserved keyword — and returned
    ``42601`` at parse time, taking ``0149z`` down with it.
    """
    unexplained = proof["chain"]["failures_unexplained"]
    assert unexplained == [], (
        f"{len(unexplained)} migration(s) failed for a reason that is not one of the "
        f"enumerated unproduced tables {proof['chain']['unproduced_tables_enumerated']}:\n"
        + json.dumps(unexplained, indent=2)
    )


def test_every_gate_object_exists(proof: dict) -> None:
    absent = sorted(name for name, ok in proof["gate_objects"].items() if not ok)
    assert absent == [], f"gate objects absent from the applied schema: {absent}"


def test_the_merge_is_refused_when_the_precursor_has_no_disposition(proof: dict) -> None:
    """CF-01. The product, in one assertion."""
    refusal = proof["refusal"]
    assert refusal["outcome"] == "REFUSED", (
        "THE MERGE WAS ADMITTED with an open, undisposed obligation. This is the claim the "
        f"whole repository is about: {json.dumps(refusal, indent=2)}"
    )
    assert refusal["sqlstate"] == CF01_SQLSTATE
    assert refusal["constraint"] == CF01_EXHIBIT, (
        "the refusal carried the wrong exhibit. A refusal whose constraint name is not the "
        "one the manifest fixes is the right outcome for the wrong reason, and the exhibit "
        "is the product here."
    )


def test_the_refusal_is_written_to_the_refusal_ledger(proof: dict) -> None:
    ledger = proof["refusal"].get("refusal_ledger", {})
    assert ledger.get("written"), f"the refusal was not recorded: {ledger}"
    assert ledger.get("read_back"), f"the refusal row could not be read back: {ledger}"
    assert ledger["sqlstate"] == CF01_SQLSTATE
    assert ledger["constraint_name"] == CF01_EXHIBIT
    assert ledger["mus_cardinality"] >= 1


def test_a_forced_counter_is_refused_by_the_gate_function(proof: dict) -> None:
    """CF-03. The projection is enforced, never trusted (rule P-2)."""
    drift = proof["drift_refusal"]
    assert drift["outcome"] == "REFUSED", (
        "the merge was ADMITTED against a counter forced to zero out of band. The projection "
        f"was trusted rather than enforced: {json.dumps(drift, indent=2)}"
    )
    assert drift["sqlstate"] == CF03_SQLSTATE
    assert drift["constraint"] == CF03_EXHIBIT
    assert drift["constraint_source"] == "parsed", (
        "spec/errors.md §3.1: diag.constraint_name is empty for P0001, so the exhibit must be "
        "recorded as PARSED. A P0001 claiming a reported exhibit is over-stating its diagnosis."
    )


def test_the_merge_is_admitted_once_a_disposition_is_signed(proof: dict) -> None:
    """The other half. A gate that always refuses is a broken gate, not a safe one."""
    assert proof["disposition"]["signed"], (
        f"the disposition could not be signed: {json.dumps(proof['disposition'], indent=2)}"
    )
    admission = proof["admission"]
    assert admission["outcome"] == "ADMITTED", (
        "the merge was still REFUSED after a signed disposition. A gate that cannot be "
        f"satisfied has not been shown to be a gate: {json.dumps(admission, indent=2)}"
    )
    record = admission["merge_record"]
    assert record["present"], "the merge was admitted but wrote no merge_record"
    assert record["permit_state"] == "merged"
    assert record["permit_open_blocking"] == 0
    assert len(record["clearance_digest"]) == 64, "the clearance digest is not a SHA-256"


def test_the_proof_exits_zero(proof: dict) -> None:
    """The exit code the `just prove` recipe and the release workflow branch on."""
    assert proof["_returncode"] == 0, (
        f"gate_refusal.py exited {proof['_returncode']} — verdict {proof.get('verdict')!r}, "
        f"failures {json.dumps(proof.get('failures', []), indent=2)}\n"
        f"stdout:\n{proof['_stdout']}"
    )
    assert proof["verdict"] == "PROVEN"
