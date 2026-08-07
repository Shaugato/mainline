# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Make the suite runnable from anywhere, not only from the package root.

``[tool.pytest.ini_options].pythonpath`` in ``pyproject.toml`` already does this when
pytest resolves the rootdir to this package. It does not when a repository-level config
file wins the rootdir election — and a suite that only passes when invoked one particular
way is a suite that will be skipped by the person who most needs to run it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
for _entry in (_PACKAGE_ROOT / "src", _PACKAGE_ROOT / "tests" / "vectors"):
    _text = str(_entry)
    if _text not in sys.path:
        sys.path.insert(0, _text)
