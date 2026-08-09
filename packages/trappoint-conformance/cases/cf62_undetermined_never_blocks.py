# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-62 — an UNDETERMINED fixity result used to block.

Manifest: ``23514`` on ``undetermined_never_blocks``, ``MI21``, invariant ``I08``; profile
``mainline`` only; milestone
``K7``; ``requires = ['mainline.observed_assertion']``.

**The one place unknown does NOT block, and it is deliberate.** Everywhere else
in this system absence refuses: a missing closure, a missing person row, a missing boundary
certificate. Here the polarity reverses, because an *undetermined* fixity comparison — the
document could not be fetched, the digest could not be computed — is not a finding about
the world. Treating it as one manufactures alarm fatigue with no argument behind it, and
alarm fatigue is how the findings that matter stop being read.

Stating the exception explicitly is part of the claim. A system that says *unknown always
blocks* and then quietly excepts one case has a rule nobody can rely on.

**Gated, and honestly so.** The relation this history writes is ``mainline.observed_assertion``,
owned by the fixity-drift milestone. Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-62")
def cf_62_undetermined_never_blocks(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Treat a comparison that could not be made as a finding."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-62",
        (
            Step(
                label="raise a blocking finding from an undetermined comparison",
                sql=world.sql(
                    "INSERT INTO {s}.observed_assertion "
                    "(site_id, subject_key, verdict, blocking) "
                    "VALUES (%s, %s, 'UNDETERMINED', true)"
                ),
                params=(world.site_id, "cf62:document"),
            ),
        ),
        relation="observed_assertion",
    )
