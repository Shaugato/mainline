# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The application's trigram similarity must equal the cluster's ``similarity()``.

S2's floor is decided in Python so that the stage can be tested with no cluster,
and the same predicate appears in :data:`ANCHOR_STAGE_SQL` so that the stage can
be *pushed down* when there is one.  Two implementations of one threshold is a
place where a silent divergence would move a floor without anyone editing a
number — so the two are compared directly, over text drawn from this domain's
own vocabulary.

Also asserted here: the two trigram functions CockroachDB does **not** support
really are absent.  A test that assumes an absence is a test that will one day
be quietly wrong; this one checks.

Skips with a reason when no cluster is reachable.  Until then the Python
implementation's agreement with ``pg_trgm`` is **unverified** and is recorded as
such in ``novelty/minhash-band.yaml``.
"""

from __future__ import annotations

from typing import Any

import pytest
from mainline_domain.identity.candidates import trigram_similarity

pytestmark = pytest.mark.requires_cluster

SAMPLES = (
    "The authorised person shall isolate pump P-101A before breaking containment.",
    "The authorised person should isolate pump P-101A before breaking containment.",
    "The authorised person must isolate pump P-101B at ISOL-4471.",
    "Hot work in Zone 2 requires a gas test below 5 percent LEL on the permit.",
    "Records of calibration shall be retained for seven years at the site office.",
    "abc",
    "ab cd",
    "ab ce",
)


def test_similarity_matches_the_cluster_on_every_pair(cluster_conn: Any) -> None:
    mismatches: list[str] = []
    with cluster_conn.cursor() as cur:
        for left in SAMPLES:
            for right in SAMPLES:
                cur.execute("SELECT similarity(%s, %s)", (left, right))
                theirs = float(cur.fetchone()[0])
                ours = trigram_similarity(left, right)
                if abs(theirs - ours) > 1e-6:
                    mismatches.append(
                        f"{left[:32]!r} vs {right[:32]!r}: cluster={theirs:.6f} python={ours:.6f}"
                    )
    assert not mismatches, "trigram similarity diverges from pg_trgm:\n" + "\n".join(mismatches)


def test_the_containment_filter_never_excludes_a_pair_the_floor_would_keep(
    cluster_conn: Any,
) -> None:
    """``%`` is a pre-filter, and a pre-filter that drops a survivor is a bug.

    :data:`ANCHOR_STAGE_SQL` filters with ``%`` and scores with ``similarity()``
    because those are the two trigram facilities CockroachDB supports.  The
    stage's own floor is 0.55.  The only property that has to hold for the
    pushdown to be safe is one-directional: **anything at or above the floor
    must survive the filter.**  Asserting the converse would be asserting the
    server's default ``similarity_threshold``, which is a session setting and
    not this package's business.
    """
    with cluster_conn.cursor() as cur:
        for left in SAMPLES:
            for right in SAMPLES:
                if trigram_similarity(left, right) < 0.55:
                    continue
                # Both operands are cast explicitly.  ``SELECT $1 % $2`` with two
                # bare placeholders is refused by CockroachDB v26.2.5 with
                # ``42P18: could not determine data type of placeholder $1`` --
                # measured, not assumed.  It does not affect ANCHOR_STAGE_SQL,
                # where the left operand is the ``canon_text`` column and the
                # placeholder's type is therefore inferable; it affects only a
                # probe like this one that binds both sides.
                cur.execute("SELECT %s::STRING %% %s::STRING", (left, right))
                assert bool(cur.fetchone()[0]), (
                    f"`%` excluded a pair scoring {trigram_similarity(left, right):.3f}, "
                    f"above the 0.55 floor: {left[:24]!r} vs {right[:24]!r}"
                )


@pytest.mark.parametrize(
    "expression",
    [
        "word_similarity('abc', 'abc def')",
        "strict_word_similarity('abc', 'abc def')",
        "'abc' <-> 'abd'",
    ],
)
def test_the_unsupported_trigram_surface_really_is_unsupported(
    cluster_conn: Any, expression: str
) -> None:
    """If any of these starts working, ``anchor_stage.py``'s comments are stale.

    They are not aspirational comments: the design ruled out ordering by trigram
    distance because the operator does not exist.  A test that pins an absence
    is how that ruling stays honest rather than becoming folklore.
    """
    psycopg = pytest.importorskip("psycopg")
    with cluster_conn.cursor() as cur, pytest.raises(psycopg.Error):
        cur.execute(f"SELECT {expression}")
