# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Import bridge for ``mainline_domain`` before the uv workspace root exists.

The workspace root ``pyproject.toml``/``uv.lock`` are owned by the kernel
toolchain worker.  Until they land, this conftest puts the package ``src``
directory on ``sys.path`` so the domain unit tests are runnable standalone.
When the workspace exists and the package is installed the ``find_spec`` guard
makes this a no-op, so it never shadows the installed distribution.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"

if importlib.util.find_spec("mainline_domain") is None and _SRC.is_dir():
    sys.path.insert(0, str(_SRC))
