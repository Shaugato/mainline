# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ABSTENTION RATCHET — where Path A and Path B meet, and the model loses.

Worker W5.  Four modules, one guarantee:

==============  ================================================================
:mod:`table`    the resolution written out as 100 literal rows, so that
                "there is no cell in which the model lowers the verdict" is
                checkable by reading rather than by trusting
:mod:`resolve`  the pure function over ``(DeltaVerdict, OracleVerdict | None,
                theta)``, plus the four inputs it refuses
:mod:`silence`  the ``mainline_meas.silence_ledger`` row that every neutral and
                every abstention writes (P5)
:mod:`policy`   theta, read from ``identity_policy``, with no default anywhere
==============  ================================================================

**There is no model here and there never will be.**  Path B lives in the
physically separate distribution ``mainline-delta-oracle``, reaches this package
only through :class:`~mainline_domain.contracts.OracleVerdict`, and the
prohibition is asserted by an AST walk over every module in this distribution
(``tests/unit/domain/boundaries/test_no_model_in_domain.py``) rather than by
this sentence.

The honest shape of the claim, since it will be read under cross-examination:
the model **can** cause a merge to be refused, and often will.  What it cannot do
— in any cell, at any confidence, with any rationale — is cause one to be
allowed.
"""

from __future__ import annotations

from .policy import PolicyIncomplete, PolicyTheta, load_policy_theta, theta_from_policy
from .resolve import (
    AlreadyResolved,
    HumanVerdictNotResolvable,
    MalformedOracleVerdict,
    Resolution,
    ResolutionRefused,
    ThetaOutOfRange,
    WitnesslessWeakening,
    explain,
    resolve,
)
from .silence import (
    ABSTENTION_CODES,
    REASON_FOR_ABSTENTION_CODE,
    SILENCE_REASONS,
    SILENCE_SOURCES,
    SilenceRecord,
    abstention_code_of,
    requires_silence_record,
    silence_record,
    stamp_rationale,
)
from .table import (
    RESOLUTION,
    ROWS,
    TABLE_SHA256,
    TABLE_VERSION,
    ResolutionCell,
    ResolutionKey,
    ResolutionRule,
    cell_for,
)

__all__ = [
    "ABSTENTION_CODES",
    "REASON_FOR_ABSTENTION_CODE",
    "RESOLUTION",
    "ROWS",
    "SILENCE_REASONS",
    "SILENCE_SOURCES",
    "TABLE_SHA256",
    "TABLE_VERSION",
    "AlreadyResolved",
    "HumanVerdictNotResolvable",
    "MalformedOracleVerdict",
    "PolicyIncomplete",
    "PolicyTheta",
    "Resolution",
    "ResolutionCell",
    "ResolutionKey",
    "ResolutionRefused",
    "ResolutionRule",
    "SilenceRecord",
    "ThetaOutOfRange",
    "WitnesslessWeakening",
    "abstention_code_of",
    "cell_for",
    "explain",
    "load_policy_theta",
    "requires_silence_record",
    "resolve",
    "silence_record",
    "stamp_rationale",
    "theta_from_policy",
]
