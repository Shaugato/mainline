# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Import bridge for the three distributions the adversary suite drives.

Same shape and same reason as ``tests/unit/domain/resolution/conftest.py``: until
the uv workspace is re-locked with ``mainline-delta-oracle`` as a member, the
package ``src`` directories go on ``sys.path`` here.  Every insert is guarded by
``find_spec`` so it is a no-op once the distribution is installed and can never
shadow a real package.

The import direction is the boundary and it is one-way: this suite may import the
domain and the oracle, the oracle may import agentkit and the domain, and the
domain may import neither.  That last leg is not a convention — it is asserted by
an AST walk in ``tests/unit/domain/boundaries/test_no_model_in_domain.py``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]

_SRC_ROOTS = {
    "mainline_domain": _REPO_ROOT
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-domain"
    / "src",
    "mainline_delta_oracle": _REPO_ROOT
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-delta-oracle"
    / "src",
    "mainline_agentkit": _REPO_ROOT / "packages" / "mainline-agentkit" / "src",
}

for _module, _src in _SRC_ROOTS.items():
    if importlib.util.find_spec(_module) is None and _src.is_dir():
        sys.path.insert(0, str(_src))
