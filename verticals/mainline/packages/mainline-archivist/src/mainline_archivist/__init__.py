# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Archivist — ingest and appraise (ARCHITECTURE.md §8.4, row 1).

One sentence describes this package, and every module in it exists to make the sentence
structural rather than aspirational:

    **Every field of an event row is a coded fact, a verbatim span read out of the source,
    or a model rating capped one below the arming threshold.**

Read that as three claims and check each one against the code:

*a coded fact* — :class:`~mainline_archivist.ingest.CodedFacts` carries the site, the
kind, the occurrence time and the severity claims, and there is no signature in this
package that assembles an event without one.

*a verbatim span* — :class:`~mainline_archivist.verbatim.VerbatimSpan` has two
constructors and both read the source text. A model supplies characters; this package
supplies offsets, by exact string search, and re-derives every span again inside the
statement builders.

*capped* — :data:`~mainline_archivist.appraise.MODEL_GATE_CEILING` is 3, one below
:data:`~mainline_archivist.appraise.ARMING_THRESHOLD`, and the cap produces a
``silence_ledger`` row rather than a silence. The database says the same thing in
``CHECK model_cannot_arm``; that CHECK is the enforcement and this arithmetic is the
explanation.

Five modules, in the order data flows through them:

===================== =======================================================
:mod:`~mainline_archivist.source`    fetch the pinned bytes, extract the text
:mod:`~mainline_archivist.verbatim`  the only way text enters a row
:mod:`~mainline_archivist.appraise`  the severity decision this agent does not make
:mod:`~mainline_archivist.ingest`    the posture, with the model calls in the middle
:mod:`~mainline_archivist.emit`      statements and parameters; no driver, ever
===================== =======================================================

**This package holds no tool, no driver and no credential.** The model calls go through
``mainline_agentkit.call.quarantined_call``, which has no ``tools`` parameter; the writes
come back as :class:`~mainline_archivist.emit.Statement` objects for a caller holding
``agent_ingestor``; and ``boto3`` is an extra whose imports are inside the two methods
that use it. ``tests/unit/archivist/test_starvation.py`` walks this package's AST to keep
all three true.
"""

from __future__ import annotations

from .appraise import (
    ARMING_THRESHOLD,
    MAX_SEVERITY,
    MODEL_GATE_CEILING,
    SEVERITY_BASIS_VOCABULARY,
    Basis,
    Downgrade,
    SeverityAppraisal,
    SeverityClaim,
    appraise,
    downgrade_silence_rows,
    promote,
)
from .emit import (
    CONTROL_FAILURE_COLUMNS,
    EVENT_COLUMNS,
    INGEST_INSERTABLE_TABLES,
    INGEST_ROLE,
    ControlFailureDraft,
    EventDraft,
    Statement,
    assert_ingest_safe,
    insert_control_failure,
    insert_event,
    insert_intake_finding,
    statements_for_findings,
)
from .errors import (
    ArchivistError,
    DocumentNotAdmitted,
    EventKindNotCoded,
    ModelRatedCannotArm,
    SeverityOutOfRange,
    SeverityWithoutBasis,
    SeverityWithoutSpan,
    SourceUnavailable,
    SpanNotVerbatim,
    TextExtractionUnavailable,
    UnsignedPromotion,
    WriteOutsideGrant,
)
from .ingest import (
    ARCHIVIST_AGENT,
    ROUTE_FOR_KIND,
    SILENCE_SOURCE,
    CodedFacts,
    IngestOutcome,
    ModelSeverityReading,
    RouteDisagreement,
    ingest_document,
    require_admitted,
)
from .source import (
    CUSTODY_PREAMBLE_VERSION,
    ExtractedText,
    FetchedObject,
    LocalObjectStore,
    ObjectRef,
    ObjectStore,
    S3ObjectStore,
    TextExtractor,
    TextractExtractor,
    Utf8TextExtractor,
    custody_preamble,
)
from .verbatim import VerbatimSpan, assert_verbatim, sha256_hex, text_digest

#: Distribution version, kept in step with ``pyproject.toml`` by
#: ``tests/unit/archivist/test_starvation.py``.
__version__ = "0.1.0"

__all__ = [
    "ARCHIVIST_AGENT",
    "ARMING_THRESHOLD",
    "CONTROL_FAILURE_COLUMNS",
    "CUSTODY_PREAMBLE_VERSION",
    "EVENT_COLUMNS",
    "INGEST_INSERTABLE_TABLES",
    "INGEST_ROLE",
    "MAX_SEVERITY",
    "MODEL_GATE_CEILING",
    "ROUTE_FOR_KIND",
    "SEVERITY_BASIS_VOCABULARY",
    "SILENCE_SOURCE",
    "ArchivistError",
    "Basis",
    "CodedFacts",
    "ControlFailureDraft",
    "DocumentNotAdmitted",
    "Downgrade",
    "EventDraft",
    "EventKindNotCoded",
    "ExtractedText",
    "FetchedObject",
    "IngestOutcome",
    "LocalObjectStore",
    "ModelRatedCannotArm",
    "ModelSeverityReading",
    "ObjectRef",
    "ObjectStore",
    "RouteDisagreement",
    "S3ObjectStore",
    "SeverityAppraisal",
    "SeverityClaim",
    "SeverityOutOfRange",
    "SeverityWithoutBasis",
    "SeverityWithoutSpan",
    "SourceUnavailable",
    "SpanNotVerbatim",
    "Statement",
    "TextExtractionUnavailable",
    "TextExtractor",
    "TextractExtractor",
    "UnsignedPromotion",
    "Utf8TextExtractor",
    "VerbatimSpan",
    "WriteOutsideGrant",
    "__version__",
    "appraise",
    "assert_ingest_safe",
    "assert_verbatim",
    "custody_preamble",
    "downgrade_silence_rows",
    "ingest_document",
    "insert_control_failure",
    "insert_event",
    "insert_intake_finding",
    "promote",
    "require_admitted",
    "sha256_hex",
    "statements_for_findings",
    "text_digest",
]
