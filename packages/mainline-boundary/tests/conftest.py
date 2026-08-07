# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Make the package importable from a bare checkout.

These four enforcements must never be unrunnable for a packaging reason. If the
uv workspace has not been synced, fall back to the source tree so a reviewer can
clone the repository and run ``pytest packages/mainline-boundary`` immediately.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
