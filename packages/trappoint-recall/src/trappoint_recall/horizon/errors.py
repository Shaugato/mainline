# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Refusals raised while certifying — or failing to certify — a retrieval's coverage.

There is exactly one thing this module's callers must never be able to do: turn an
uncertifiable run into a clean one by catching an exception. So the refusals here are
raised only for inputs that are *structurally* unusable (a malformed observation, an
impossible count). An observation that simply shows poor coverage is not an error at all —
it produces a certificate whose verdict is ``UNDETERMINED``, which is a first-class result
that the database stores and the receipt carries.
"""

from __future__ import annotations

__all__ = ["CoverageRefused", "HorizonRefused", "UncountableCorpus"]


class HorizonRefused(ValueError):
    """Base: a coverage observation could not be turned into a certificate."""


class UncountableCorpus(HorizonRefused):
    """A prefix tree's row count is unknown, so no fingerprint can be taken over it.

    This is not the same as "the tree is empty". An empty tree is a fact with a count of
    zero; an uncountable one is the absence of a fact, and the two must never hash alike.
    """


class CoverageRefused(HorizonRefused):
    """An observation contradicts itself — e.g. an arm that returned rows without executing."""
