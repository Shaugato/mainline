# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Invariant mutation testing — "unwelding" — and the refusal-depth matrix it produces.

``merge-gate-invariant.md`` §3.5 says *"delete the ``RAISE`` and the write still fails twice
over."* That is a claim in a document, and CockroachDB v26.2 shipped ``ALTER TABLE …
ENABLE/DISABLE TRIGGER``, which turns it into a one-line experiment.

**This package is the only place the structural-redundancy claim is made.** At runtime the
deterministic ``RAISE`` fires first — adversarial-review finding ``S4`` — so no case in
``cases/`` asserts a second mechanism and none may be written that does. Redundancy is a
property of the schema, and the only way to observe a property of the schema is to change
the schema.

Everything here is ``@pytest.mark.schema`` and runs with ``-p no:xdist`` on a container it
creates and destroys. It must never be pointed at the cluster the conformance suite
parallelises over; :mod:`unweld.container` refuses the two DSNs where that would happen.
"""

from __future__ import annotations

import sys
from pathlib import Path

# `cases/` and `unweld/` sit beside `src/` rather than inside it: they are the corpus and
# the mutation matrix, not part of the distributed runner, and the package's build config
# ships only `src/trappoint_conformance`. Under `uv sync --all-packages` the runner is
# installed and only the sibling `cases` package needs finding; in a bare checkout neither
# is on the path. Both are added here, at import time, ahead of every relative import
# below — a conftest cannot do it, because importing the conftest imports this module
# first.
_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_ROOT, _ROOT / "src"):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

__all__ = ["MECHANISMS", "collect", "render_report"]

from .harness import collect, render_report  # noqa: E402
from .mutations import MECHANISMS  # noqa: E402
