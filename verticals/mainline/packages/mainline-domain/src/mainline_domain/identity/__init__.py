# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Clause identity — resolving *which ancestor clause this one came from*.

Identity has two axes and this subpackage is the first of them.

1. **Textual identity** — ``clause_uuid``, resolved by the cascade in
   :mod:`mainline_domain.identity.candidates` (stages S1-S4) and decided by the
   assignment stage (W8, S5).
2. **Obligation identity** — ``cat_key``, the hash of the normalised Control
   Assertion Tuple, which lives in the CATSEAL subpackage.  A rewrite that
   changes every word but preserves ``(actor, deontic, parameter, comparator,
   value, unit)`` re-attaches through axis 2 even when axis 1 misses.

The design inversion that makes any of this tractable is worth restating at the
top of the package that implements the *losing* half of it, because it is the
reason the losing half is acceptable:

    MAINLINE does not ask "does this new text match an old clause?".  It asks
    whether every blame-bearing ancestor is, in this commit, matched, matched
    through a recorded split/merge, or **explicitly absent with a signed
    disposition**.  There is no fourth state.

So a matcher failure does not produce a silent pass.  It produces an orphaned
blood-written obligation — a blocking row — which is a *louder* gate than the
weakening it was hiding.  Recall failure converts into an adjudicable false
positive rather than a fatal false negative.  That asymmetry is the whole
design, and it is why this subpackage optimises for **precision and recorded
uncertainty** rather than for recall.

Nothing here decides a state transition, writes a residue row, or calls a model.
"""

from __future__ import annotations

__all__: list[str] = []
