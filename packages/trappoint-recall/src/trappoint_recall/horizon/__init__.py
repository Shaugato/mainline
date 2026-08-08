# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""M4 CUE HORIZON — an empty result is representable only with a coverage certificate.

::

    observation  ->  certify()  ->  CoverageCertificate(verdict, coverage_basis, fingerprint)
                                        |
                                        +-- verdict == 'UNDETERMINED'
                                                 => build_receipt() REFUSES an exhaustion claim

The two halves of the mechanism are deliberately in different places, and neither is
sufficient alone. In the database, migration 0087's
``complete_needs_a_basis_that_can_establish_it`` refuses ``verdict='complete'`` on anything
but ``coverage_basis='full_scan'`` — for every writer, forever. In code,
:func:`~trappoint_recall.per.receipt.build_receipt` refuses to emit a receipt under an
``UNDETERMINED`` certificate unless the caller explicitly marks it ``not_exhaustive``. The
first stops an overclaim from being stored; the second stops one from being *made*.
"""

from __future__ import annotations

from trappoint_recall.horizon.certificate import (
    COVERAGE_BASES,
    VERDICTS,
    ArmCoverage,
    CoverageBasis,
    CoverageCertificate,
    CoverageObservation,
    Verdict,
    certify,
)
from trappoint_recall.horizon.errors import (
    CoverageRefused,
    HorizonRefused,
    UncountableCorpus,
)
from trappoint_recall.horizon.fingerprint import (
    FINGERPRINT_DOMAIN,
    IndexFingerprintInput,
    PrefixTree,
    fingerprint_preimage,
    index_fingerprint,
    trees_from_counts,
)

__all__ = [
    "COVERAGE_BASES",
    "FINGERPRINT_DOMAIN",
    "VERDICTS",
    "ArmCoverage",
    "CoverageBasis",
    "CoverageCertificate",
    "CoverageObservation",
    "CoverageRefused",
    "HorizonRefused",
    "IndexFingerprintInput",
    "PrefixTree",
    "UncountableCorpus",
    "Verdict",
    "certify",
    "fingerprint_preimage",
    "index_fingerprint",
    "trees_from_counts",
]
