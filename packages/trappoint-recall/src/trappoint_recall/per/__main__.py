# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``python -m trappoint_recall.per`` — the verifier, without an installed console script.

The packaged entry point is ``trappoint-recall-verify-per`` (declared in
``packages/trappoint-recall/pyproject.toml``, which this worker does not own — see the
cross-domain note). This module makes the command runnable from a source checkout today, and
it is also the form a stranger uses after ``pip download``-ing nothing at all: the verifier's
entire import graph is the standard library.
"""

from __future__ import annotations

from trappoint_recall.per.cli import main

raise SystemExit(main())
