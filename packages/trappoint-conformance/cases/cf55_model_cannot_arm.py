# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-55 — a model-rated severity used to arm the gate.

Manifest: ``23514`` on ``model_cannot_arm``, ``MI14``, invariant ``I11``; profile ``mainline`` only;
milestone
``K3``; ``requires = ['mainline.event']``.

``CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')``. A model may
propose a severity and the proposal is kept — ``severity_actual``, ``severity_potential``
and ``severity_gate`` are three separate columns precisely so the arithmetic survives — but
a rating whose only source is a language model may not reach the band that blocks work.

The rule is small, unconditional, and the reason the rest of the system can use models
freely. Everything a model produces is admissible as an accusation and inadmissible as an
arming signal, which is the same shape as ``CF-54`` one table over.

**Gated, and honestly so.** The relation this history writes is ``mainline.event`` (migration 0033),
which exists; the token gates it until the vertical's ingestion path is green end to end. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-55")
def cf_55_model_cannot_arm(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Let a language model decide something is a fatality."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-55",
        (
            Step(
                label="ingest a model-rated fatality",
                sql=world.sql(
                    "INSERT INTO {s}.event "
                    "(site_id, occurred_at, kind, title, narrative, source_object_key, "
                    " source_sha256, severity_actual, severity_potential, severity_gate, "
                    " severity_basis, canon_version) "
                    "VALUES (%s, now() - INTERVAL '30 days', 'incident', %s, %s, %s, %s, "
                    "        5, 5, 5, 'model_rated', 1)"
                ),
                params=(
                    world.site_id,
                    "conformance: a model-rated event",
                    "The narrative the model read.",
                    f"s3://conformance/{scope.case_id}",
                    __import__("hashlib").sha256(b"cf55").digest(),
                ),
            ),
        ),
        relation="event",
    )
