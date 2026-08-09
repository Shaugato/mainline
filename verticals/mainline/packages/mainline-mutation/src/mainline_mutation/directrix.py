# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""One DIRECTRIX registry, built from the committed seed, shared by the whole run.

The harness needs a ``SafeDirectionRegistry`` for two different reasons and it
must be the SAME registry for both, or the measurement is incoherent:

* the **setpoint operators** ask which way is dangerous, so that a nudge is a
  nudge *against* ``safe_direction`` rather than an arbitrary number change;
* the **lattice** is handed it as the registry in force at the commit under
  test.

It is built from ``mainline_domain``'s committed seed document through the real
loader — ``seed_source`` then ``load_registry`` — rather than by constructing a
``SafeDirectionRegistry`` directly.  Constructing one directly would skip
reachability, generation, retirement, encoding, status, signature and uniqueness,
which are the seven checks that decide whether an entry answers at all, and a
harness that skipped them would be measuring a registry no gate would ever see.

THE COMMIT AND SITE ARE FIXED CONSTANTS AND THAT IS DELIBERATE
--------------------------------------------------------------
``decide()`` refuses a registry whose ``as_of_commit`` is not the commit under
test, which is the retro-tuning defence.  The harness has no real commit DAG, so
it uses one fixed synthetic commit for both sides.  That is stated here rather
than hidden: the mutation ratchet measures the LATTICE and the MATCHER, not the
ancestry resolution, and a fixture set with a synthetic commit cannot and does
not claim anything about diachronic gating beyond the origin-baseline
comparison the salami classes make explicitly.

A MEASURED FINDING, RECORDED WHERE IT WILL BE READ
---------------------------------------------------
Of the 60 parameter keys ``data/lexicon/parameter.toml`` can extract, only 6 are
ratified in ``data/registry/safe-direction-seed.toml``:
``gas_test_interval``, ``lel_test_threshold``, ``max_operating_pressure``,
``min_ppe_level``, ``permit_validity_period``, ``relief_valve_set_pressure``.
Every other extracted parameter ABSTAINS, and decision D6 turns an abstention
into ``weaken``.  That is R-A4 failing closed exactly as designed — and it also
means a kill rate computed over unratified parameters would be measuring
registry coverage rather than the lattice's direction arithmetic.  The
setpoint-nudge classes therefore decline unratified fixtures, and
:func:`ratified_overlap` exists so the number above is recomputed on every run
instead of being a comment that can rot.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Final

from mainline_domain.registry import (
    SafeDirection,
    SafeDirectionRegistry,
    load_registry,
    seed_source,
)

__all__ = [
    "HARNESS_COMMIT",
    "HARNESS_SITE",
    "ratified_overlap",
    "registry",
    "safe_direction",
]

#: The one synthetic site the whole harness runs under.
HARNESS_SITE: Final[uuid.UUID] = uuid.UUID("11111111-2222-3333-4444-555555555555")

#: The one synthetic commit.  32 bytes because `commit_id` is a SHA-256 content
#: address everywhere in this system and a shorter one would be refused by the
#: DDL the harness's own SQL writes against.
HARNESS_COMMIT: Final[bytes] = bytes.fromhex("aa" * 32)


@lru_cache(maxsize=1)
def registry() -> SafeDirectionRegistry:
    """The DIRECTRIX registry in force for every mutant in the run."""
    source = seed_source(site_id=HARNESS_SITE, commit_id=HARNESS_COMMIT)
    return load_registry(source, site_id=HARNESS_SITE, as_of_commit=HARNESS_COMMIT)


def safe_direction(parameter: str) -> SafeDirection:
    """The direction, or :attr:`SafeDirection.ABSTAIN`.  Never a default."""
    if not parameter:
        return SafeDirection.ABSTAIN
    return registry().safe_direction(parameter)


def ratified_overlap() -> tuple[str, ...]:
    """Parameter keys the extractor can produce **and** DIRECTRIX ratifies.

    Recomputed on every run and printed into the published artefact.  A comment
    stating "only six of sixty" would be true today and silently false after one
    lexicon edit; a computed field is the same statement with an expiry date of
    never.
    """
    from mainline_domain.cat.lexicon import load_lexicons

    extractable = frozenset(load_lexicons().parameters.synonym.values())
    return tuple(sorted(extractable & registry().parameters()))
