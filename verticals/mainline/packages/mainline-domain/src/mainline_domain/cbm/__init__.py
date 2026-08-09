# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""CONSERVATION OF BLAME MASS — the client half of the ledger.

    inherited = carried + split_carried + merge_carried + residue_open + residue_disposed

The identity above is enforced by the DATABASE, not by this package:

======================================================  =====================================
``verticals/mainline/db/migrations/0049c_cbm_account.sql``   the table, the ``balanced`` STORED
                                                             column and ``CONSTRAINT cbm_balances``
``…/0140a_fn_cbm_account_guard.sql``                         re-derives all six counters and
                                                             overwrites the inserter's
``…/0140b_fn_residue_project.sql``                           projects ``identity_residue``'s
                                                             ``max_ancestral_severity``
``…/0140c_fn_cbm_gate_permit.sql`` · ``…/0140d_fn_cbm_gate_cr.sql``
                                                             refuse a merge whose cited commits
                                                             have no account, or a stale one
``…/0145a`` … ``…/0145d``                                    the four triggers that attach them
``…/0151_v_cbm_ledger.sql``                                  ``mainline_audit.v_cbm_ledger``
======================================================  =====================================

This package computes the same arithmetic so a projector can compare its own
answer with the database's and report a disagreement as a defect in itself.  It
decides nothing.  If it were deleted the refusals would be unchanged.
"""

from __future__ import annotations

from .account import (
    BLOOD_SEVERITY_THRESHOLD,
    BUCKET_PRECEDENCE,
    AncestorFacts,
    Bucket,
    CommitFacts,
    classify,
    derive_account,
    unaccounted_ancestors,
)
from .errors import CBMError, ClosureNotMaterialised, CommitUnknown, GenerationNotDense
from .project import (
    ANCESTOR_SQL,
    CLOSURE_MISSING_SQL,
    COMMIT_SQL,
    fetch_commit_facts,
    insert_account,
    next_account_gen,
    project_commit,
    read_account,
)
from .version import LEDGER_ROW_CAP, PROJECTOR_VERSION

__all__ = [
    "ANCESTOR_SQL",
    "BLOOD_SEVERITY_THRESHOLD",
    "BUCKET_PRECEDENCE",
    "CLOSURE_MISSING_SQL",
    "COMMIT_SQL",
    "LEDGER_ROW_CAP",
    "PROJECTOR_VERSION",
    "AncestorFacts",
    "Bucket",
    "CBMError",
    "ClosureNotMaterialised",
    "CommitFacts",
    "CommitUnknown",
    "GenerationNotDense",
    "classify",
    "derive_account",
    "fetch_commit_facts",
    "insert_account",
    "next_account_gen",
    "project_commit",
    "read_account",
    "unaccounted_ancestors",
]
