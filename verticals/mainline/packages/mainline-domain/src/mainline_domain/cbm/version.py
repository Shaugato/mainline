# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Versions and thresholds for the CONSERVATION OF BLAME MASS ledger.

Every constant here is stamped onto a stored row or decides which rows are
counted, so each one is a versioned artefact rather than a tunable.  Changing
any of them changes what the arithmetic *means*, and the version string is what
makes an account computed under the old meaning distinguishable from one
computed under the new.
"""

from __future__ import annotations

from typing import Final

#: Written to ``mainline.cbm_account.projector_ver`` on every account.
#:
#: Bump this whenever :func:`mainline_domain.cbm.account.derive_account` or the
#: SQL in ``0140a_fn_cbm_account_guard.sql`` changes what it counts.  Two
#: accounts for the same commit with different ``projector_ver`` values and
#: different counters are a *versioning* story; the same version with different
#: counters is a *tampering* story, and the column is what keeps them apart.
PROJECTOR_VERSION: Final[str] = "cbm-projector-1"

#: An ancestor clause is BLOOD-BEARING at severity >= 4.
#:
#: This is not a tunable and there is no configuration file for it.  It is the
#: threshold in the conservation law as ARCHITECTURE.md states it ("every
#: ancestor clause carrying a blame edge to a severity >= 4 event"), it is
#: written literally into ``0140a_fn_cbm_account_guard.sql``'s derivation, and
#: ``tests/unit/domain/cbm/test_cbm_sql_shape.py`` asserts the two agree.  Lowering
#: it here without changing the SQL would make the Python and the database
#: disagree about what the account is an account OF, which the differential
#: test would catch and which nothing else would.
BLOOD_SEVERITY_THRESHOLD: Final[int] = 4

#: ``mainline_audit.v_cbm_ledger`` is capped at this many rows.
#:
#: The managed MCP surface caps a ``SELECT`` at 25 rows and a response at
#: 10 KiB (ARCHITECTURE.md section 17).  The view's ``LIMIT`` is that cap, and
#: ``ledger_truncated`` is how a reader of 25 rows learns whether 25 was all of
#: them.
LEDGER_ROW_CAP: Final[int] = 25
