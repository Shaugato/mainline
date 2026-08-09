# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Versions and bounds for ORIGINDIFF and COMMUTATION FOOTPRINT.

Three constants, and each is here rather than inline for a different reason.

``DIACHRONIC_VERSION``
    Stamped into ``computed_by`` on every ``mainline.commutation_edge`` row this
    package writes.  I06 says a dependency edge a gate consumes is *computed*,
    never declared — and the only thing that distinguishes a computed edge from a
    declared one after the fact is that the computed one names the code that
    computed it.  A row with no deriver is a declaration wearing a derivation's
    costume.

``ORIGIN_DEPTH_BOUND``
    The maximum generation distance ``mainline.v_blame_origin`` will look back
    for a blame origin, and the maximum length of the first-parent walk in
    :mod:`mainline_domain.diachronic.origin`.  **The same number appears as a
    literal in ``0152_v_blame_origin.sql``**, and
    ``tests/integration/algorithms/diachronic/test_v_blame_origin_shape.py``
    parses the migration and asserts the two are equal.  Two copies of a bound
    that can drift is a bound nobody can rely on; two copies with a test between
    them is one bound written twice.

``FOOTPRINT_VERSION``
    Which footprint encoding produced an overlap set.  Changing what counts as
    "touched" changes which edits commute, which changes the derived dependency
    edges a gate reads — so it is a version, not a refactor.  Bumping it means
    the previously-derived ``commutation_edge`` rows were derived under a
    different definition and must be re-derived, not merged with.

None of these is a configuration value.  There is no environment variable, no
policy file and no constructor argument that changes any of them: an operator who
could widen ``ORIGIN_DEPTH_BOUND`` at runtime could move a blame origin out of
reach of the gate, which is the retro-tuning hazard M3 exists to make visible.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "DIACHRONIC_VERSION",
    "FOOTPRINT_VERSION",
    "ORIGIN_DEPTH_BOUND",
    "computed_by",
]

DIACHRONIC_VERSION: Final[str] = "origindiff-1"
"""The ORIGINDIFF / COMMUTATION FOOTPRINT implementation version."""

FOOTPRINT_VERSION: Final[str] = "footprint-1"
"""Which encoding produced a ``footprint_overlap`` array.  See :mod:`.footprint`."""

ORIGIN_DEPTH_BOUND: Final[int] = 4096
"""Maximum generation distance between a subject version and its blame origin.

Chosen, not guessed.  ``mainline.commit_obj.gen`` is ``1 + max(parent.gen)``, so a
generation is one commit on the mainline branch.  Four thousand commits is more
than a nine-year procedure library produces on one document family, and the bound
exists to make the join in ``v_blame_origin`` *provably* bounded rather than to
express a policy about how far back blame reaches.

The failure mode if it were ever reached is stated where it can be acted on: the
view would return no origin row, :func:`~mainline_domain.diachronic.origin.
resolve_origin` would report the mechanism inert, and the delta of record would
fall back to the parent diff — which is **fail-open**.  That is why
``origin_depth`` is projected by the view and why
:class:`~mainline_domain.diachronic.origin.BlameOrigin` carries
``depth_bound_reached``: a caller can see that it happened rather than discovering
it from a delta that came out quieter than it should have.
"""


def computed_by() -> str:
    """Return the ``computed_by`` string every derived row from this package carries."""
    return f"mainline_domain.diachronic/{DIACHRONIC_VERSION}"
