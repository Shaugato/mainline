# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The mutation operators, bound to the classes ``catalogue-v1.toml`` declares.

An operator is a pure function ``(Revision, random.Random) -> MutationApplication``.

Three properties hold for every one of them and are asserted by
``tests/e2e/mutation/test_operators.py``:

* **Deterministic given the ``Random``.**  The runner derives a per-mutant seed
  from the master seed, the class and the fixture, so two runs of one master
  seed produce byte-identical descendants.  An operator that reached for
  ``random`` at module scope, a clock, or ``os.urandom`` would make the
  published number unreproducible, which is the one thing a residual-risk
  figure may not be.
* **It changes something.**  An operator whose output equals its input has
  produced no trial, and a "kill rate" over no-op mutants is a number about
  nothing.  The registry checks this per mutant.
* **It says when it does not apply.**  :class:`~mainline_mutation.errors.
  OperatorInapplicable` means *no trial*, never *survived*.  A mutation that was
  never applied is not evidence about detection in either direction, and
  counting it as a survivor would understate the kill rate exactly as counting
  it as a kill would overstate it.
"""

from __future__ import annotations

from .kill import KILL_OPERATORS
from .survive import SURVIVE_OPERATORS

__all__ = ["KILL_OPERATORS", "SURVIVE_OPERATORS"]
