# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-59 — a recall run under a policy version that is not anchored.

Manifest: ``P0001`` on ``mainline.fn_recall_policy_anchored``, ``MI18``, invariant ``I07``; profile
``mainline`` only; milestone
``K4``; ``requires = ['mainline_meas.recall_policy']``.

Retro-tuning a threshold so that an omission looks reasonable is the cheapest
possible defence and the hardest to disprove — *the policy at the time would not have
surfaced it either*. It is closed by requiring the policy to **predate the retrieval** and
to be anchored where we cannot alter it: inside a cosigned checkpoint of the custody ledger.

``anchored_tree_size`` and ``anchored_at`` are paired by a ``CHECK``, and the guard refuses
a run citing a policy where either is NULL.

**Gated, and honestly so.** The relation this history writes is ``mainline_meas.recall_policy``
(migration 0080) and its guard (0112/0136). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-59")
def cf_59_policy_not_anchored(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Retrieve under a threshold nobody has committed to yet."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf59")
    world.run(
        "commit a policy that has never been anchored",
        "INSERT INTO {s}_meas.recall_policy "
        "(policy_version, taxonomy_ver, embed_model, gen_model, prompt_version, beam_size, "
        " tau, arms, calibration_set_sha256, author_sub, signature) "
        "VALUES ('cf59-unanchored', 1, 'titan-v2', 'claude', 'p1', 32, "
        "        '{{\"tau0\": 5}}'::JSONB, '{{}}'::JSONB, %s, 'conformance', %s)",
        (
            __import__("hashlib").sha256(b"cf59-cal").digest(),
            __import__("hashlib").sha256(b"cf59-sig").digest(),
        ),
    )
    return refusal(
        harness,
        "CF-59",
        (
            Step(
                label="run a recall under the unanchored policy",
                sql=world.sql(
                    "INSERT INTO {s}_meas.recall_run "
                    "(permit_id, site_id, corpus_commit, policy_version, index_plan_digest, "
                    " index_generation, n_candidates, n_blocking, n_advisory, n_silenced, "
                    " n_deduped) "
                    "VALUES (%s, %s, %s, 'cf59-unanchored', %s, 'g1', 0, 0, 0, 0, 0)"
                ),
                params=(
                    permit_id,
                    world.site_id,
                    __import__("hashlib").sha256(b"cf59-corpus").digest(),
                    __import__("hashlib").sha256(b"cf59-plan").digest(),
                ),
            ),
        ),
        relation="recall_run",
    )
