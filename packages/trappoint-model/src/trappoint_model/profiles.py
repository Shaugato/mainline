# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Settings profiles, and the counterexample corpus as a committed artefact.

**The corpus is part of the assurance case, not build detritus.** For a product whose
deliverable is a refusal, the accumulated set of histories that once broke the gate is
evidence — it says which shapes were tried and which are now regression-covered. So
``.hypothesis-corpus/`` is a :class:`DirectoryBasedExampleDatabase` at the repository
root and it is committed to git, in front of the ``.hypothesis/`` cache which is not.

:func:`example_database` multiplexes the two: Hypothesis reads from both and writes to
both, so a counterexample found on a laptop lands in a directory the next commit carries
and the next CI run replays before it generates anything new.

**Two deviations from the obvious configuration, both deliberate.**

*No* ``GitHubArtifactDatabase``. The design note proposed multiplexing a read-only
GitHub-artefact database as the second leg. It needs a token and a network call on every
test session, and ``PL-1`` says a milestone's proof must run on a stranger's machine with
no credential of ours — a suite that degrades or stalls without a GitHub token is not that
suite. ``nightly-differential.yml`` uploads the corpus as an artefact instead, which gives
the same recovery path without putting a credential on the inner loop.

*This is not the regression record.* ``DirectoryBasedExampleDatabase`` is a cache of
CURRENTLY-FAILING examples: it prunes an entry the moment the example stops reproducing,
which is the moment the bug is fixed. Measured — three shrunk counterexamples were on disk
while the model was wrong and the directory was empty on the first green run. The durable
half is ``.hypothesis-corpus/counterexamples.jsonl``, replayed by
:mod:`~trappoint_model.replay`.

Two profiles, and the difference between them is the whole budget argument:

=========  =============  ====================  =============================
profile    max_examples   stateful_step_count   where
=========  =============  ====================  =============================
``ci``     50             25                    every push, inside 12 minutes
``nightly``2000           120                   ``nightly-differential.yml``
=========  =============  ====================  =============================

``deadline=None`` on both. A per-example wall-clock deadline against a real cluster
measures the cluster's mood, and a flaky failure in a suite about refusals teaches people
to ignore it.
"""

from __future__ import annotations

import os
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis.database import (
    DirectoryBasedExampleDatabase,
    ExampleDatabase,
    MultiplexedDatabase,
)

__all__ = ["CORPUS_DIR", "active_profile", "example_database", "register_profiles"]

#: The committed corpus. Resolved from this file, so it is the same directory whether the
#: suite runs from the repository root or from the package.
CORPUS_DIR = Path(__file__).resolve().parents[4] / ".hypothesis-corpus"

_CACHE_DIR = Path(__file__).resolve().parents[4] / ".hypothesis" / "examples"


def example_database() -> ExampleDatabase:
    """Return the committed corpus, multiplexed with the local cache.

    Both are writable on purpose. A read-only corpus would replay yesterday's
    counterexamples and quietly discard today's, which is the opposite of an assurance
    artefact that accumulates.
    """
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    return MultiplexedDatabase(
        DirectoryBasedExampleDatabase(CORPUS_DIR),
        DirectoryBasedExampleDatabase(_CACHE_DIR),
    )


def register_profiles() -> None:
    """Register ``ci`` and ``nightly``. Idempotent; safe to call from every conftest.

    The two calls are written out rather than built from a shared ``**kwargs`` dict.
    ``settings.register_profile``'s fourth positional parameter is a parent ``settings``
    object, so a splatted dict type-checks against the wrong slot and the difference
    between the profiles — which is the only thing anyone reads this function for —
    stops being visible on one line each.
    """
    # `deadline=None` on both: a per-example wall-clock deadline against a real cluster
    # measures the cluster's mood, and a flaky failure in a suite about refusals teaches
    # people to ignore it. `filter_too_much` is deliberately NOT suppressed — if the
    # machine's preconditions start rejecting most draws, the generator has stopped
    # exploring and that is a defect worth failing on.
    suppressed = [HealthCheck.too_slow, HealthCheck.data_too_large]
    settings.register_profile(
        "ci",
        max_examples=50,
        stateful_step_count=25,
        deadline=None,
        database=example_database(),
        suppress_health_check=suppressed,
    )
    settings.register_profile(
        "nightly",
        max_examples=2000,
        stateful_step_count=120,
        deadline=None,
        database=example_database(),
        suppress_health_check=suppressed,
    )


def active_profile() -> str:
    """``$TRAPPOINT_HYPOTHESIS_PROFILE``, defaulting to ``ci``."""
    return os.environ.get("TRAPPOINT_HYPOTHESIS_PROFILE", "ci")
