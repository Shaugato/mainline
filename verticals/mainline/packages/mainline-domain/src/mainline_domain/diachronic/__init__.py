# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ORIGINDIFF and COMMUTATION FOOTPRINT — the diachronic half of the delta.

Two mechanisms, one package, because they are the same idea twice: *what an edit
means depends on what came before it.*

**ORIGINDIFF** (:mod:`.origin`, :mod:`.ancestral_diff`) — the ``control_delta`` of
record is the more forceful of ``delta(parent → new)`` and ``delta(blame_origin →
new)``.  Twenty individually-neutral commits whose composition weakens a control
are refused at commit twenty, because the comparison never had a parent to hide
behind.  Migration ``0152_v_blame_origin.sql`` is the bounded, non-recursive
candidate query underneath it.

**COMMUTATION FOOTPRINT** (:mod:`.footprint`, :mod:`.commutation`) — two clause
edits commute iff their footprints — identity anchors, CAT parameter keys and the
implied control class — are disjoint.  Non-commuting pairs are dependency edges *derived* rather
than declared (invariant I06) and are stored in ``mainline.commutation_edge``
(migration ``0049b``), where ``overlap_nonempty`` refuses an edge that claims a
dependency it cannot name.

Import discipline, inherited from the distribution and restated because this
package is the one that reaches a database: **no model SDK, ever** (decision D1 /
principle P7), and no ``psycopg`` at module scope — the SQL sources take a
connection typed ``Any`` so the whole unit suite runs with no driver installed.

Nothing is auto-imported here.  :mod:`.ancestral_diff` pulls in the lattice, which
pulls in the unit registry and its committed definition files, and a caller that
only wants :func:`~mainline_domain.diachronic.footprint.control_class_key` should
not pay for that.
"""

from __future__ import annotations

__all__: tuple[str, ...] = ()
