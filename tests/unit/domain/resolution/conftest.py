# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Import bridge for the two distributions this worker owns.

Identical in intent to ``tests/unit/domain/cat/conftest.py``: until the uv
workspace is re-locked with the new ``mainline-delta-oracle`` member, the
package ``src`` directories are put on ``sys.path`` here.  Each insert is
guarded by ``find_spec`` so it is a no-op once the distribution is installed and
never shadows the real package.

``mainline_agentkit`` is bridged too, because ``mainline_delta_oracle`` calls
Bedrock **through** it rather than holding a second model surface of its own.
That direction is the only one permitted: the oracle may import agentkit and the
domain, and neither may import the oracle.
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
