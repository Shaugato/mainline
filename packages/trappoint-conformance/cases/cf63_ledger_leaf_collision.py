# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-63 — write two ledger leaves at the same sequence position.

Manifest: ``23505`` on ``ledger_leaf_pkey``, ``MI24``, anomaly ``A9``; profile ``mainline`` only;
milestone
``K2``; ``requires = ['mainline.ledger_leaf']``.

**Gap-free by CAS, not by sequence.** ``CREATE SEQUENCE``, ``nextval(``,
``SERIAL`` and ``unique_rowid()`` are banned by a repository lint — and the lint is
load-bearing rather than decorative, because ``CREATE SEQUENCE`` succeeds perfectly well on
this cluster. A sequence gap means nothing: sequences are allowed to skip, so a missing
number is indistinguishable from a rolled-back transaction. A **CAS** gap means tampering,
which is the entire point of a custody ledger.

``PRIMARY KEY (site_code, seq)`` plus ``UNIQUE (site_code, prev_link_hash)`` is the
compare-and-swap: two sequencers that both believe the head is at *n* cannot both write it.

**Gated, and honestly so.** The relation this history writes is ``mainline.ledger_leaf`` (migration
0073) and the CAS append function (0119). Until the
capability token above is declared satisfied the runner **skips** this case with a printed
reason, and a skipped case is never counted as a passed one. That is the difference between
a suite that is honest about its coverage and one that grows green by omission.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, refusal


@register("CF-63")
def cf_63_ledger_leaf_collision(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Sequence two entries into one slot."""
    world = World(harness, scope, schema)
    world.site_row()
    return refusal(
        harness,
        "CF-63",
        (
            Step(
                label="claim a sequence position that is already taken",
                sql=world.sql(
                    "INSERT INTO {s}.ledger_leaf "
                    "(site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id) "
                    "SELECT l.site_code, l.seq, %s, %s, %s, %s, %s "
                    "  FROM {s}.ledger_leaf l ORDER BY l.seq DESC LIMIT 1"
                ),
                params=(
                    world.uid("cf63:entry"),
                    __import__("hashlib").sha256(b"cf63-leaf").digest(),
                    __import__("hashlib").sha256(b"cf63-prev").digest(),
                    __import__("hashlib").sha256(b"cf63-link").digest(),
                    world.uid("cf63:batch"),
                ),
            ),
        ),
        relation="ledger_leaf",
    )
