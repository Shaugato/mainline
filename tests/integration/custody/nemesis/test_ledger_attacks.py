# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Attacks on the ledger tables themselves — A1-A6, A12, A14.

These are the T0/T1 attacks: somebody with SQL against the ledger. Every one of them leaves
the database in a state that is *internally consistent*, which is exactly the property that
makes an in-table hash chain a checksum rather than evidence. What catches them is a
commitment that already left the operator's control — the eight checkpoints seeded here are
the ones committed to this repository, timestamped and cosigned.

A1 is the one the whole design exists for, and it is criterion 1 of milestone K2.
"""

from __future__ import annotations

import re
from pathlib import Path

import attacks
import pytest
from nemesis_harness import FIXTURE_DDL, NemesisContext, OutcomeRecorder

#: Standing up a fresh database, applying the reduced schema and seeding 72 leaves
#: costs a few seconds per attack, and the repository's default 120 s per-test budget
#: is written for unit tests. Raised here rather than globally: a slow lane is a cost,
#: a hanging lane is a test that has stopped asserting.
pytestmark = pytest.mark.timeout(300)

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"


def _record(recorder: OutcomeRecorder, ctx: NemesisContext, outcome: attacks.AttackOutcome) -> None:
    recorder.environment.setdefault("cluster", ctx.provenance)
    recorder.environment.setdefault("verifier", outcome.verifier)
    recorder.environment.setdefault(
        "cryptography",
        "available" if attacks.CRYPTOGRAPHY_AVAILABLE else "ABSENT — checks 4 and 12 SKIP",
    )
    recorder.environment.setdefault("schema", "reduced nemesis fixture (see nemesis_harness.py)")
    recorder.record(outcome)


def _assert_detected(outcome: attacks.AttackOutcome, *, at_least: int = 1) -> None:
    assert len(outcome.detected_by) >= at_least, (
        f"{outcome.id} ({outcome.name}) ran and was detected by "
        f"{len(outcome.detected_by)} check(s). ATTACK-DEPTH: an attack detected by zero "
        f"checks is a hole in the argument, not a row in a table. Verifier: "
        f"{outcome.verifier}. Findings: {outcome.findings}"
    )


# =======================================================================================
# The reduction is guarded, not promised
# =======================================================================================


def test_fixture_names_the_same_constraints_as_the_migrations() -> None:
    """The nemesis fixture must use the migrations' constraint NAMES, or it tests nothing.

    ``ledger_leaf_pkey`` and ``ledger_linear`` are an interface: CU-2's retry predicate
    matches on constraint name, and A6 asserts refusal depth 2 by dropping them one at a
    time. A fixture that renamed one would let this suite pass against names the database
    does not use, which is the failure mode a reduced fixture exists to avoid and the reason
    this guard reads BOTH files rather than trusting a comment.

    ``FIXTURE_DDL`` is imported at module scope from ``nemesis_harness``. It used to be
    imported here, from ``conftest``, and that is how run 31388699452 turned this
    cross-check into an ``ImportError``: ``conftest`` is a name every conftest file in the
    repository claims, so by the time this function ran the name had been rebound to
    ``packages/trappoint-sql/tests/conftest.py``.
    """
    for migration, expected in (
        (
            "0073_ledger_leaf.sql",
            ("ledger_leaf_pkey", "ledger_linear", "ledger_leaf_entry_unique", "fk_intake"),
        ),
        (
            "0072_ledger_intake.sql",
            ("ledger_intake_pkey", "intake_site_entry_unique", "leaf_hash_is_sha256"),
        ),
        (
            "0075_ledger_checkpoint.sql",
            ("ledger_checkpoint_pkey", "root_hash_is_sha256", "log_sig_present"),
        ),
    ):
        source = (MIGRATIONS / migration).read_text(encoding="utf-8")
        declared = set(re.findall(r"CONSTRAINT\s+([a-z_][a-z0-9_]*)", source))
        for name in expected:
            assert name in declared, f"{migration} no longer declares CONSTRAINT {name}"
            assert name in FIXTURE_DDL, (
                f"the nemesis fixture does not declare CONSTRAINT {name}, which "
                f"{migration} does. The reduction has drifted from the migration and every "
                "attack below is now attacking a different schema."
            )


# =======================================================================================
# A1 — the attack the whole design exists for. K2 exit criterion 1.
# =======================================================================================


@pytest.mark.slow
def test_a1_delete_and_relink(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Delete leaf k, renumber, recompute every ``link_hash``. Caught by a consistency proof.

    After this attack the ledger table is perfectly self-consistent: ``seq`` is dense and
    every link recomputes. Detection by check 9 would mean the chain caught it, and the
    criterion explicitly excludes that. **Check 3 — the consistency proof against a root
    that already left our control — is what must fire.**
    """
    outcome = attacks.run_attack(nemesis, "A1", attacks.a1_delete_and_relink)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome, at_least=2)
    assert 3 in outcome.detected_by, (
        "K2.1: A1 was not detected by check 3 (consistency proof). The tamper must be "
        "caught by a proof against a commitment that left our control, not by inspecting "
        f"a chain the attacker recomputed. Detected by: {outcome.detected_by}"
    )


@pytest.mark.slow
def test_a2_renumber_only(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Shift ``seq`` without re-linking. Density is the cheap detector; the tree is the proof."""
    outcome = attacks.run_attack(nemesis, "A2", attacks.a2_renumber_only)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome, at_least=2)
    assert 9 in outcome.detected_by, (
        "A2 must be caught by check 9. There is no sequence generator in this system — "
        "CREATE SEQUENCE, nextval, SERIAL and unique_rowid() are banned repository-wide — "
        "so a gap MEANS tampering and nothing else."
    )


@pytest.mark.slow
def test_a3_payload_substitute(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Swap what a human reads, leave the bytes that were hashed."""
    outcome = attacks.run_attack(nemesis, "A3", attacks.a3_payload_substitute)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 1 in outcome.detected_by, (
        "A3 must be caught by check 1. The verifier hashes the carried canon_bytes and "
        "compares the parsed payload against them; if the two could drift silently, the "
        "exhibit and the proof would describe different documents."
    )


@pytest.mark.slow
def test_a4_canon_substitute(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Swap the bytes AND the hash together, so check 1 passes. Only the tree disagrees."""
    outcome = attacks.run_attack(nemesis, "A4", attacks.a4_canon_substitute)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome, at_least=2)
    assert 2 in outcome.detected_by or 3 in outcome.detected_by, (
        "A4 leaves every in-table relationship consistent. It must be caught by an "
        "inclusion or consistency proof against a checkpoint that predates the swap."
    )


@pytest.mark.slow
def test_a5_canon_version_downgrade(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Re-canonicalise an old leaf under a different ``payload_ver``."""
    outcome = attacks.run_attack(nemesis, "A5", attacks.a5_canon_version_downgrade)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)


@pytest.mark.slow
def test_a6_fork_has_refusal_depth_two(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Two rows claiming the same head — refused twice over, then caught once unwelded.

    CU-1 transplants the gate's ``UNIQUE (permit_id, prev_seq)`` compare-and-swap onto the
    ledger as ``UNIQUE (site_code, prev_link_hash)``, so the append is held to the same
    standard as the merge. This test unwelds one mechanism at a time, which is the only way
    to learn whether the second one was ever doing anything.
    """
    outcome = attacks.run_attack(nemesis, "A6", attacks.a6_fork)
    _record(recorder, nemesis, outcome)
    assert outcome.database_refusals, (
        "the fork was not refused by the database at all. Refusal depth 2 — "
        "ledger_leaf_pkey AND ledger_linear — is the claim; a fork that lands with both "
        "constraints armed means the claim is false."
    )
    _assert_detected(outcome)


@pytest.mark.slow
def test_a12_sandbox_smuggle(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """A guest demo write inside the tree an inspector would be handed."""
    outcome = attacks.run_attack(nemesis, "A12", attacks.a12_sandbox_smuggle)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 13 in outcome.detected_by, "A12 must be caught by check 13"


@pytest.mark.slow
def test_a14_receipt_orphan(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """A signed promise our own log contradicts, held by the party we gave it to.

    This is the only finding in the whole set that accuses the log operator of an *act*
    rather than reporting a mismatch, and check 15 is worded that way on purpose.
    """
    outcome = attacks.run_attack(nemesis, "A14", attacks.a14_receipt_orphan)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 15 in outcome.detected_by, (
        "A14 must be caught by check 15. Without it an unsequenced leaf is invisible; with "
        "it, the signer walks away holding proof of log misbehaviour."
    )
