# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""MAINLINE recall agent.

The recall agent is a **T1 + T2** actor (ARCHITECTURE §8.4).  It proposes candidates and
writes ``recall_*`` and ``silence_*`` rows; it **cannot write ``blocking_check``** and it
makes no admission decision.  The gate transaction contains no model call at all — by the
time anyone presses merge, ``permit.open_blocking`` is already an integer.

This distribution currently ships one subpackage, ``providers``: the embedding and judge
adapters, the runtime inference-profile resolver, prompt caching, structured output and
the cassette layer that lets the whole domain run with no AWS account.  Fusion, admission
and the run loop live in sibling packages.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
