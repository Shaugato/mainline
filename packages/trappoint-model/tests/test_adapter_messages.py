# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The exhibit recovery is pinned to the substrate's own text, and that pin is asserted.

``P0001`` carries no ``constraint_name`` on CockroachDB v26.2.5 — measured; see
``trappoint_core.errors``. The merge path solves that with a ``refused by
<schema>.<object>`` clause, but the projection family raises a bare sentence, so
:data:`~trappoint_model.adapter._BY_MESSAGE` maps sentence fragments onto raising
objects.

A mapping keyed on prose rots silently: someone rewords a ``RAISE``, the fragment stops
matching, the adapter starts reporting an empty exhibit, and the differential goes green
because the *model* would have to be wrong in the same place to notice. So every fragment
is asserted to still occur, verbatim, in the rendered tree — and when a message is
reworded this test fails first, which is the correct order.
"""

from __future__ import annotations

from trappoint_model.adapter import _BY_MESSAGE
from trappoint_model.refschema import tree_files


def test_every_message_fragment_still_occurs_in_the_rendered_tree() -> None:
    """A fragment that no longer appears is an exhibit the adapter can no longer recover."""
    tree = "\n".join(path.read_text(encoding="utf-8") for path in tree_files())
    missing = [fragment for fragment, _ in _BY_MESSAGE if fragment not in tree]
    assert not missing, (
        f"these message fragments no longer occur in the reference vertical: {missing}. "
        "The adapter recovers the raising object from them because the driver reports no "
        "constraint name for P0001; a stale fragment means a refusal is reported with an "
        "empty exhibit and the differential compares nothing."
    )


def test_every_named_object_still_exists_in_the_rendered_tree() -> None:
    """The right-hand side of the mapping is a real function, not a plausible name."""
    tree = "\n".join(path.read_text(encoding="utf-8") for path in tree_files())
    missing = sorted({obj for _, obj in _BY_MESSAGE if f"CREATE FUNCTION {obj}" not in tree})
    assert not missing, f"these objects are named as exhibits but are not created: {missing}"
