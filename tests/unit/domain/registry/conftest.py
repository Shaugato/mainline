# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Import bridge for ``mainline_domain`` before the uv workspace root exists.

Same shape as ``tests/unit/domain/anchors/conftest.py`` (worker W1) and for the
same reason: the workspace ``pyproject.toml``/``uv.lock`` are owned by the kernel
toolchain worker, and until they land these tests must still be runnable
standalone.  The ``find_spec`` guard makes this a no-op once the distribution is
installed, so it can never shadow it.

No shared fixtures live here on purpose.  Every test in this directory turns on
*which commit sees which version*, so each module builds its own commit DAG in
full view rather than inheriting one — a shared fixture would put the shape of
the history somewhere other than the test that depends on it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"

if importlib.util.find_spec("mainline_domain") is None and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
