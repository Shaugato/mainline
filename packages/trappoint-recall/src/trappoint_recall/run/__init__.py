# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The recall run's public surfaces: the wire contract, its schema, and the view contract.

Three artefacts, three audiences:

``contract`` / ``schema``
    What the recall agent POSTs to the kernel's ``checks:materialise`` endpoint, as frozen
    Pydantic models and as a committed JSON Schema. The kernel lead owns the endpoint; this
    package owns the payload shape.

``views_contract.md``
    The columns ``mainline_audit.v_recall_conservation`` and ``v_silence_summary`` must
    expose. The MCP lead writes those views; this document is the requirement they are
    written against, so that a change to the tables under them is a change to a published
    contract rather than a surprise.

Nothing here touches a database or a model. The agent that does is
``verticals/mainline/packages/mainline-recall-agent``, under FSL-1.1-ALv2.
"""

from __future__ import annotations

from trappoint_recall.run.contract import (
    BLOCKING_CAP_PROBABILISTIC,
    CHANNELS,
    CONTRACT_SCHEMA_VERSION,
    DETERMINISTIC_ORIGINS,
    FACETS,
    KERNEL_ORIGIN,
    ORIGINS,
    OUTCOMES,
    Candidate,
    CandidateSet,
    Counts,
    ExposureCueRef,
)
from trappoint_recall.run.schema import (
    SCHEMA_FILENAME,
    SCHEMA_ID,
    candidate_set_json_schema,
    committed_schema_path,
    render_schema,
    write_schema,
)

__all__ = [
    "BLOCKING_CAP_PROBABILISTIC",
    "CHANNELS",
    "CONTRACT_SCHEMA_VERSION",
    "DETERMINISTIC_ORIGINS",
    "FACETS",
    "KERNEL_ORIGIN",
    "ORIGINS",
    "OUTCOMES",
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "Candidate",
    "CandidateSet",
    "Counts",
    "ExposureCueRef",
    "candidate_set_json_schema",
    "committed_schema_path",
    "render_schema",
    "write_schema",
]
