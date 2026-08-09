# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The judge pack: Tier-3 verification questions, and the machinery that keeps them true.

``demo/VERIFY.md`` tells a judge what to paste. It cannot tell anyone whether what it says
to paste is still legal, still names columns that exist, or still fails where it must.
This package is that half:

``QUESTIONS.yaml``
    The questions as data — the ask, the exact statement, the view behind it, what a green
    answer proves and, mandatorily, what it does not.

``envelope``
    The Managed-MCP limits, re-implemented standalone so the judge path needs nothing
    installed, and cross-checked against ``packages/mainline-mcp`` when that is importable.

``pack``
    The pack loaded and made strict: positives must pass the envelope, negatives must be
    refused by the refusal they name, and no positive may ship an unbounded claim.

``drift``
    Agreement with the rest of the repository: the shipped ``CREATE VIEW`` projections, the
    vector widths, ``demo/VERIFY.md``, ``demo/REFUSAL-STRINGS.yaml``, and the repository's
    own claim-hygiene rules.

``render``
    ``PACK.md``, generated and committed, so the page a judge reads cannot drift away from
    the pack a validator checks.

``runner``
    Execution over the managed endpoint or over a local SQL connection, which reports
    ``NOT RUN`` and exits non-zero rather than ever reporting a pass it did not earn.

Nothing here imports the product. It reads files, refuses statements, and prints.
"""

from __future__ import annotations

__all__ = ["drift", "envelope", "pack", "render", "runner"]
