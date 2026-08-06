# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""TRAPPOINT recall substrate.

This distribution holds the parts of recall that are *not* MAINLINE-specific: the
evaluation harness, the arm generator, the lexical scorer, the fusion arithmetic and
the exhausted-recall commitment. It contains no database driver, no cloud SDK and no
MAINLINE domain vocabulary, and it is licensed Apache-2.0 for that reason.

Nothing is imported eagerly here: importing :mod:`trappoint_recall` must stay cheap
so that a CI lane which only needs the metric arithmetic does not pay for numpy.
"""

from __future__ import annotations

from typing import Final

__all__ = ["__version__"]

__version__: Final = "0.1.0"
