# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Taxonomy failures, each named after the thing it refuses.

Nothing in this module carries a ``silence_reason``.  A silence-ledger row is a *fact
about the corpus* — a candidate that was scored and not admitted.  Every failure here is
a fact about **us**: a label that is not a function, a level-1 node that is not on the
buyer's register, an archival path with a hole in it, a bond whose ancestors were not
closed.  Recording any of those as silence would file a defect as evidence, so they are
exceptions that stop the run.

The one exception to "stop the run" is :class:`LabelRejected`, which is raised only by the
strict entry point.  Induction uses the non-raising verdict form and *records* rejected
model proposals on the :class:`~mainline_recall_agent.taxonomy.versioning.TaxonomyVersion`,
because a model proposing a thing instead of a function is a fact about the prompt and
belongs in the version record where a reader can see how often it happened.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ArchivalPathError",
    "BondClosureError",
    "ClassifierArtefactInvalid",
    "ClassifierNotFitted",
    "CueEmissionError",
    "EvalPackageUnavailable",
    "HoldoutTooSmall",
    "InductionQualityError",
    "LabelRejected",
    "Level1OffRegister",
    "Level1Repartition",
    "Level1Unfrozen",
    "RegisterMalformed",
    "TaxonomyError",
    "TaxonomyVersionError",
]


class TaxonomyError(Exception):
    """Base class for every failure raised by the taxonomy subpackage.

    Same ergonomics as ``providers.errors.ProviderError`` — a message plus keyword
    context that renders into ``str()`` — deliberately *without* inheriting from it.
    A taxonomy defect is not a provider outcome and must never be handled by a caller
    that is catching provider failures in order to write silence.
    """

    def __init__(self, message: str, /, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:  # pragma: no cover - trivial
        if not self.context:
            return self.message
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} [{rendered}]"


# --------------------------------------------------------------------------------------
# Labels
# --------------------------------------------------------------------------------------


class LabelRejected(TaxonomyError):
    """A proposed activity label does not name a function performed.

    Carries ``reason`` (a stable code from :mod:`~mainline_recall_agent.taxonomy.labels`)
    so a caller can aggregate rejections by cause rather than by message text.
    """


# --------------------------------------------------------------------------------------
# The frozen level-1 register
# --------------------------------------------------------------------------------------


class RegisterMalformed(TaxonomyError):
    """The ICMM MUE register file is missing, unparseable, or outside its size bounds."""


class Level1OffRegister(TaxonomyError):
    """A level-1 node was proposed whose ``activity_root`` is not on the register.

    Level 1 *is* the vector-index prefix.  A fonds that exists in the row store but not on
    the buyer's Material Unwanted Event register is a K-means tree nobody audits.
    """


class Level1Unfrozen(TaxonomyError):
    """A level-1 node was proposed with ``frozen = false``.

    The database refuses this too (``CONSTRAINT l1_frozen``).  It is refused here as well
    so the writer never composes a statement the database is going to reject: a caller
    that learns about the constraint from a 23514 has already decided to try.
    """


class Level1Repartition(TaxonomyError):
    """An attempt to re-induct level 1 — that is, to change the prefix set.

    Not an update.  C-SPANN maintains one K-means tree per distinct prefix value, so the
    level-1 code is baked into the physical index; changing it orphans every vector filed
    under the old prefix rather than moving them.
    """


# --------------------------------------------------------------------------------------
# Paths, cues and bonds
# --------------------------------------------------------------------------------------


class ArchivalPathError(TaxonomyError):
    """A resolved archival path is not a contiguous fonds -> series -> file chain.

    Raised when the path does not start at level 1, skips a level, crosses a site, mixes
    taxonomy versions, or contains a parent link the node table does not corroborate.
    """


class CueEmissionError(TaxonomyError):
    """The LMB writer was asked to emit something it must not emit.

    Unknown facet, blank cue text on a facet declared populated, or a duplicate
    ``(scope_id, facet)`` pair — the last of which would collide with
    ``event_cue_one_per_scope_facet_prompt`` and, worse, would double-count one incident
    in a graded arm.
    """


class BondClosureError(TaxonomyError):
    """Ancestor closure could not be completed for a bond.

    A missing ancestor means the bond set is *not* closed, and channel B's whole claim is
    that "a fatality never decays" is a set-membership question.  A half-closed set answers
    that question wrongly and silently, so the writer emits nothing at all.
    """


# --------------------------------------------------------------------------------------
# Induction, classification, holdout
# --------------------------------------------------------------------------------------


class InductionQualityError(TaxonomyError):
    """Induction produced a taxonomy that cannot honestly be frozen.

    Two triggers: too large a share of the model's proposals failed label validation (the
    prompt is not doing its job, and quietly keeping the survivors would publish a
    taxonomy shaped by the validator rather than by the corpus), or the surviving pool is
    empty.
    """


class ClassifierNotFitted(TaxonomyError):
    """The bulk-assignment classifier was used before it was fitted."""


class ClassifierArtefactInvalid(TaxonomyError):
    """A committed classifier artefact is malformed, or its digest does not match.

    The artefact is JSON coefficients precisely so that this check is possible; a pickle
    would be neither auditable nor safe to load, and this classifier decides which
    K-means tree an incident is filed into.
    """


class EvalPackageUnavailable(TaxonomyError):
    """``trappoint_recall.eval`` is not importable, so no Wilson bound can be computed.

    Refused rather than substituted.  A holdout number without an interval is exactly the
    kind of bare point estimate ``scripts/recall/no_bare_point_estimates.py`` exists to
    keep out of the repository, and a locally reimplemented interval would be a second
    definition of the confidence the release gates use.
    """


class HoldoutTooSmall(TaxonomyError):
    """Fewer holdout documents than the acceptance test requires."""


class TaxonomyVersionError(TaxonomyError):
    """A version record is internally inconsistent (bad parent link, empty snapshot)."""
