# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-model`` — the oracle, the differential, and the shrinkable interleaving.

Nothing in this package is imported by the substrate, the gate service or any Lambda. It
is a **test instrument**: it exists to disagree with the gate, and a disagreement is a
finding rather than a failure of this package. See ``README.md`` for the argument.
"""

from __future__ import annotations

from .model import Accept, Model, Refuse, Verdict

__all__ = ["Accept", "Model", "Refuse", "Verdict", "__version__"]

__version__ = "0.1.0"
