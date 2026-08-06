# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MAINLINE domain algorithms — the deterministic, model-free core.

Import discipline for this distribution (decision D1, principle P7):

* **Nothing here may import a model SDK.**  Not ``boto3``, not ``anthropic``,
  not ``strands``, not transitively.  The lattice in this package decides a
  state transition, and no component that decides a state transition is allowed
  to reach a model.  Path B lives in ``mainline-delta-oracle`` and enters only
  through ``mainline_domain.contracts.DeltaOracle``.
* **Nothing here may call the builtin ``hash``.**  It is salted per process.
  Every hash in this package is ``hashlib`` (blake2b or sha256), because the
  outputs are evidence.
* **``mainline_domain.contracts`` is stdlib-only** and is the single shared
  vocabulary; it is owned by worker W1 and is not extended by other workers.

Submodules deliberately do *not* auto-import here: the canon and anchor
subpackages read committed data files at import time, and the migration runner
imports ``contracts`` alone.
"""

from __future__ import annotations

from typing import Final

__all__ = ["__version__"]

__version__: Final[str] = "0.1.0"
