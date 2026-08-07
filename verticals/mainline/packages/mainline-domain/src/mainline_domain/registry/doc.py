# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where the ``safe_direction`` registry lives, and why it is not a table.

The registry is a **document in the gated commit DAG**, ``doc_code =
'REG-SAFE-DIRECTION'``, one clause per parameter.  That is the DIRECTRIX
recursion and it is the whole originality claim of this worker: the table that
decides which way a setpoint move is dangerous is itself governed by the gate
that reads it.

WHAT A TABLE WOULD HAVE COST
----------------------------
Put ``safe_direction`` in ``mainline.safe_direction (parameter, direction)`` and
the cheapest attack on the entire product is an ``UPDATE`` on two columns.
Flip ``max_operating_pressure`` from ``lower_is_safer`` to ``higher_is_safer``
and every subsequent pressure increase is classified ``strengthen``.  Nothing
else in the system changes.  No commit, no signature, no blame edge, no residue,
no refusal — the gate keeps working perfectly and gives the opposite answer.
Grants and audit logging do not close that: they make the edit *attributable*
after the fact, and the product's claim is that the database *refuses*, not that
somebody can reconstruct who broke it.

WHAT BEING A DOCUMENT BUYS
--------------------------
Because each parameter is a ``clause_version`` in a document:

* editing one is a ``change_request`` against a protected branch, so it goes
  through the same merge gate as any other control change;
* the entry carries **blame edges** like any other clause, so a direction
  written after an incident is answerable to that incident, and a later edit to
  it is a weakening of a blood-written control;
* the ratifying act is a **signed commit**, so "who decided that lower is safer"
  has the same answer shape as "who decided the isolation procedure";
* reading the registry is ``as_of_commit``-parameterised, so a verdict issued
  last March can be re-derived under the registry that existed last March
  instead of the one that exists now.

That last point is the one an opposing expert will press on, and it is the
reason :func:`mainline_domain.registry.loader.load_registry` takes a commit and
holds no cache.
"""

from __future__ import annotations

from typing import Final

__all__ = ["DOC_CODE", "DOC_TITLE"]

DOC_CODE: Final[str] = "REG-SAFE-DIRECTION"

DOC_TITLE: Final[str] = "Safe-direction registry (DIRECTRIX)"
