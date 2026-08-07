# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-conformance`` — the suite that gives the phrase "TRAPPOINT-compliant" a meaning.

A fork copies four hundred lines of SQL in an afternoon. *"Passes TRAPPOINT conformance
1.0, 45/45, refusal-depth min 2"* is a claim only this suite confers, and it is the
substrate's only real moat.

Two properties make it worth anything, and both are easy to lose:

**Exactness.** Every case asserts an exact SQLSTATE *and* an exact exhibit name. A case
that asserts "an exception was raised" has not tested a product whose deliverable is the
diagnosis.

**Redness.** Every case is written against a database that cannot yet satisfy it,
observed red, and only then made green by the migration that owns it. This package
currently ships one case, ``CF-01``, and it fails. That is the deliverable, not a defect.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
