# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Import bridge for ``mainline_domain`` before the uv workspace root exists.

Identical in intent to ``tests/unit/domain/canon/conftest.py``: the workspace
root ``pyproject.toml``/``uv.lock`` are owned by the kernel toolchain worker, so
until they land this puts the package ``src`` directory on ``sys.path``.  The
``find_spec`` guard makes it a no-op once the distribution is installed, so it
never shadows the real package.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"

if importlib.util.find_spec("mainline_domain") is None and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
