# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Version constants, and the rule for when each of them moves.

A published residual-risk number is worthless unless a reader can say *which
code produced it*.  Four separately-moving identifiers do that here, and the
separation is the point: if one number covered everything, every artefact would
differ from every other artefact and none of the differences would mean
anything.

``HARNESS_VERSION``
    Bumped when the RUNNER or the OPERATORS change.  A new operator, a changed
    text transformation, a changed judgement rule: all of these change what the
    number measures and all of them bump this.

``CATALOGUE_SHA256`` (computed, :mod:`mainline_mutation.resources`)
    The declared catalogue, the fixture revisions and the paraphrase cassettes,
    digested together.  Moves when the CLAIM moves — a class added, a magnitude
    changed, a fixture edited.

``OPERATOR_FINGERPRINT`` (computed, :mod:`mainline_mutation.catalogue`)
    The source text of every registered operator, digested.  This is the one
    that makes "traceable to the code that produced it" literally true rather
    than a promise about discipline: an operator edited without a
    ``HARNESS_VERSION`` bump still moves this digest.

``POLICY_SHA256`` (computed, from ``StageBands.fingerprint()``)
    D11's identity-policy fingerprint.  Retro-tuning the matcher to make a drop
    look reasonable moves it, exactly as M3 makes tuning tau visible.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "HARNESS_VERSION",
    "PARAPHRASE_PROFILE",
    "REPORT_SCHEMA",
]

#: Bumped when the runner or an operator changes.  ``mutation/<n>`` and nothing
#: cleverer: a semantic version would imply a compatibility promise that a
#: measurement harness cannot make.
HARNESS_VERSION: Final[str] = "mutation/1"

#: The schema identifier stamped into every published JSON artefact.  A reader
#: parsing an artefact from `evidence/mutation/` keys on this and nothing else.
REPORT_SCHEMA: Final[str] = "mainline/mutation/report/v1"

#: The cassette profile the adversarial-paraphrase class reads.  Named, and
#: carried into the artefact, because "adversarial paraphrase" is meaningless
#: without saying whose adversary.
PARAPHRASE_PROFILE: Final[str] = "adversarial-weakening.v1"
