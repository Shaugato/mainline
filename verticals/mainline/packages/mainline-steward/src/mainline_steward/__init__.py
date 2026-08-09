# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-steward`` — the Steward's attestation emitter.

An LLM ops report is evidence that a review occurred, not evidence of a condition. This
distribution exists to make that weaker claim *checkable*: every finding carries the exact
statement that produced it and the SHA-256 of the rows that came back, so a reader can
re-run it without trusting a word of the narrative attached beside it.

The one write path in this distribution is
``mainline_mcp.client.Client.insert_external_attestation`` — a method with no parameter
that names a table, bound to ``mainline_meas.external_attestation``. There is no pgwire
driver here, no AWS SDK and no model SDK, and
``tests/integration/steward/test_no_other_write_path.py`` walks this package's AST to
keep it that way.
"""

from __future__ import annotations

from typing import Final

from .attestation import (
    ATTESTATION_KIND,
    ENTRY_KIND,
    AttestationRow,
    BytesEncoding,
    Emitter,
    OpsAttestation,
    RunOutcome,
    build_attestation,
)
from .ccloud import CcloudPage, CcloudShim, CustodianPatrol, FixtureCcloud, SubprocessCcloud
from .digest import sha256_hex, tree_file_count, tree_sha256
from .errors import (
    AttestationRefused,
    CcloudFieldMissing,
    CcloudUnavailable,
    ConfigurationRefused,
    OccurrenceAlreadyAttested,
    ReadFailed,
    ScheduleRefused,
    SkillPinRefused,
    StewardError,
)
from .findings import (
    EVIDENCE_OF_REVIEW,
    Finding,
    FindingOutcome,
    FindingSource,
    sentence,
)
from .guard import FileOccurrenceStore, MemoryOccurrenceStore, OccurrenceGuard
from .identity import AgentIdentity, resolve_identity
from .narrative import NarrativeSet, attach_narratives, read_transcript
from .prompts import render_prompt
from .run import RunConfig, RunResult, StewardRun
from .schedule import Occurrence, RunKind, Schedule, ScheduleBook, load_schedules
from .skills import MaterialisedSkill, SkillLock, SkillPin, default_lock, load_lock

__version__: Final = "0.1.0"

__all__ = [
    "ATTESTATION_KIND",
    "ENTRY_KIND",
    "EVIDENCE_OF_REVIEW",
    "AgentIdentity",
    "AttestationRefused",
    "AttestationRow",
    "BytesEncoding",
    "CcloudFieldMissing",
    "CcloudPage",
    "CcloudShim",
    "CcloudUnavailable",
    "ConfigurationRefused",
    "CustodianPatrol",
    "Emitter",
    "FileOccurrenceStore",
    "Finding",
    "FindingOutcome",
    "FindingSource",
    "FixtureCcloud",
    "MaterialisedSkill",
    "MemoryOccurrenceStore",
    "NarrativeSet",
    "Occurrence",
    "OccurrenceAlreadyAttested",
    "OccurrenceGuard",
    "OpsAttestation",
    "ReadFailed",
    "RunConfig",
    "RunKind",
    "RunOutcome",
    "RunResult",
    "Schedule",
    "ScheduleBook",
    "ScheduleRefused",
    "SkillLock",
    "SkillPin",
    "SkillPinRefused",
    "StewardError",
    "StewardRun",
    "SubprocessCcloud",
    "__version__",
    "attach_narratives",
    "build_attestation",
    "default_lock",
    "load_lock",
    "load_schedules",
    "read_transcript",
    "render_prompt",
    "resolve_identity",
    "sentence",
    "sha256_hex",
    "tree_file_count",
    "tree_sha256",
]
