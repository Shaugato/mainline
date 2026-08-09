# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-65 — record an empty retrieval result with no coverage certificate.

Manifest: ``23514`` on ``empty_result_certified``, invariant ``I08``; profile ``mainline`` only;
milestone
``K4``; ``requires = ['mainline.coverage_certificate']``.

**"No precursors found" is not insertable as a bare fact.** An empty answer is a
claim about a *universe* — this corpus, at this commit, under this index generation, at
these thresholds — and without the certificate it is indistinguishable from a retrieval that
silently failed, an index that was half-built, or a filter that excluded everything.

The certificate binds the empty result to the index generation that produced it, which is
also what makes the claim re-checkable later against the same corpus.

**Gated, and honestly so.** The relation this history writes is ``mainline.coverage_certificate``,
owned by the recall milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-65")
def cf_65_empty_result_certified(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Say nothing was found, and be unable to say over what."""
    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf65")
    return refusal(
        harness,
        "CF-65",
        (
            Step(
                label="record an uncertified empty result",
                sql=world.sql(
                    "INSERT INTO {s}.retrieval_result "
                    "(site_id, permit_id, n_results, coverage_certificate_id) "
                    "VALUES (%s, %s, 0, NULL)"
                ),
                params=(world.site_id, permit_id),
            ),
        ),
        relation="retrieval_result",
    )
