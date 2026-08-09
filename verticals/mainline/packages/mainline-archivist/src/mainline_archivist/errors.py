# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Archivist's refusal vocabulary.

Every class here names a thing this agent will not do, and each one is the client-side
twin of something the database already refuses. That doubling is deliberate and it is
not redundancy: the CHECK is the enforcement, and the exception is the *explanation*.
A caller that trips ``model_cannot_arm`` in CockroachDB gets a 23514 naming a constraint;
a caller that trips :class:`ModelRatedCannotArm` gets the sentence that constraint exists
to enforce, three frames from where the mistake was made, before a row was built.

The kernel idiom is unchanged by any of this. **The refusal that counts is the one in
the database**, because it holds for every writer including a DBA with `psql` open, and
these exceptions hold only for callers who came through this package.
"""

from __future__ import annotations

__all__ = [
    "ArchivistError",
    "DocumentNotAdmitted",
    "EventKindNotCoded",
    "ModelRatedCannotArm",
    "SeverityOutOfRange",
    "SeverityWithoutBasis",
    "SeverityWithoutSpan",
    "SourceUnavailable",
    "SpanNotVerbatim",
    "TextExtractionUnavailable",
    "UnsignedPromotion",
    "WriteOutsideGrant",
]


class ArchivistError(Exception):
    """Base class for every refusal this package makes."""


class ModelRatedCannotArm(ArchivistError):
    """A model's severity rating was about to arm, or claim to have observed, the gate.

    The client-side twin of ``CHECK model_cannot_arm`` on ``mainline.event``
    (migration 0033, MI14): ``severity_gate < 4 OR severity_basis <> 'model_rated'``.

    Raised in two situations, which are the same sentence read in two directions:

    * a ``model_rated`` claim asserted ``severity_actual`` — a model may say what could
      have happened, never what did;
    * an appraisal came out with ``severity_basis = 'model_rated'`` at or above the
      arming threshold, which the ceiling arithmetic makes unreachable and which is
      therefore a bug in this package rather than a caller error.
    """


class SeverityWithoutSpan(ArchivistError):
    """A non-zero severity claim carried no byte range in the source document.

    Migration 0033: *a severity with no span is a number somebody typed.* The gate's
    refusal gets read aloud, so every severity this package admits has to be traceable
    to a range of bytes in a document whose digest is on the row.
    """


class SeverityOutOfRange(ArchivistError):
    """A severity outside 0-5, which the three range CHECKs on ``event`` would refuse."""


class SeverityWithoutBasis(ArchivistError):
    """An appraisal was asked for with no claims at all.

    ``severity_basis`` is ``NOT NULL`` and its vocabulary is closed, so an appraisal over
    an empty claim set would have to invent one. Refusing is the only honest answer:
    zero-with-a-made-up-basis is indistinguishable, downstream, from a coded zero.
    """


class UnsignedPromotion(ArchivistError):
    """A model rating was promoted to ``human_rated`` without a person and a credential.

    Migration 0033 permits the promotion — a model rating is *"allowed to be promoted by
    a person who puts their name on it"* — and this is what "puts their name on it"
    means in code: a person id and a signing-credential id, both recorded on the claim.
    """


class SpanNotVerbatim(ArchivistError):
    """A quoted span is not the bytes it claims to be.

    Raised when the text a draft carries is not what the source text holds at those
    offsets, or when a model-supplied quote cannot be found in the source at all.
    ``mainline_agentkit.profiles.extraction`` states the rule this enforces: *we compute
    the offsets by exact string search into the source. We never trust a model-reported
    offset.*
    """


class EventKindNotCoded(ArchivistError):
    """No coded event kind was supplied, and the model's route is not a substitute.

    ``event.kind`` has a closed CHECK vocabulary and a triage route is a *pipeline*
    decision, not a classification of the incident. The Archivist will record a
    disagreement between the two as a finding; it will not resolve one by promoting the
    model's answer.
    """


class DocumentNotAdmitted(ArchivistError):
    """A statement was requested for a document the posture refused.

    A defensive refusal: :func:`mainline_archivist.ingest.ingest_document` never reaches
    the emitters on a refused document, so this fires only for a caller that assembled
    the pieces by hand.
    """


class SourceUnavailable(ArchivistError):
    """The source object could not be fetched, or fetched bytes failed their digest."""


class TextExtractionUnavailable(ArchivistError):
    """No text could be extracted, or the configured extractor is not installed."""


class WriteOutsideGrant(ArchivistError):
    """A statement named a table or a verb ``agent_ingestor`` does not hold.

    ``verticals/mainline/db/GRANTS.yaml`` gives the ingest role ``INSERT`` on eleven
    tables and nothing else — no ``UPDATE``, no ``DELETE``, anywhere. The database would
    refuse such a statement regardless; this refusal happens before the connection is
    opened, so the mistake is attributable to the line of Python that made it.
    """
