# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``python -m trappoint_migrate`` — the same surface as the ``trappoint`` script.

CI installs the workspace and calls the console script; a contributor debugging a
resolution problem often has the package importable and the script not on PATH. Both
paths reach the same `main`, so there is no second code path to keep honest.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover - trivial dispatch
    sys.exit(main(["migrate", *sys.argv[1:]]))
