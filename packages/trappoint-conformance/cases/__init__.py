# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The corpus: one module per conformance case, and the loader that installs them.

``spec/conformance/manifest.toml`` declares the cases. This package *implements* them, one
module each, and :func:`load_all` is what turns a directory of modules into entries in
``trappoint_conformance.runner``'s registry.

**Why discovery and not a hand-written list.** A hand-written import list is a second place
to declare the corpus, and a second declaration is a place for the corpus to silently shrink
— a module deleted in a rebase, an import removed to fix a lint. Discovery over the
directory means the only way to remove a case is to remove its file, and
``tests/test_manifest_totality.py`` fails the moment the set of implementations stops
matching the manifest in either direction.

**CF-01 is not here, deliberately.** It belongs to the toolchain worker and is registered by
``trappoint_conformance.runner`` itself: it is the case that was **observed red against an
empty database**, and that observation is the proof artefact ``PL-2`` demands. Re-registering
it here would raise — the registry refuses duplicates, because the winner would be decided by
import order — and, more to the point, taking ownership of another worker's red-before-green
evidence would destroy the thing that makes it evidence.

Load order does not matter and must not: each module registers exactly one case id, and the
registry refuses a second implementation of the same id.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from trappoint_conformance.runner import implemented_case_ids

__all__ = ["CASE_MODULE_PREFIX", "case_modules", "load_all"]

# Every module implementing a case is named `cfNN_<slug>`. Modules starting with `_` are
# machinery — the world builder, the exhibit registry, the privilege helper — and are
# imported by the cases that need them rather than by the loader.
CASE_MODULE_PREFIX = "cf"

_PACKAGE = __name__
_HERE = Path(__file__).resolve().parent


def case_modules() -> tuple[str, ...]:
    """Every case module in this package, in sorted order.

    Sorted so a report reads in case order and a failure in module *n* does not change
    which module is *n + 1* between runs.
    """
    return tuple(
        sorted(
            info.name
            for info in pkgutil.iter_modules([str(_HERE)])
            if info.name.startswith(CASE_MODULE_PREFIX)
        )
    )


def load_all() -> frozenset[str]:
    """Import every case module and return the ids now implemented.

    Idempotent: Python caches modules, so a second call re-imports nothing and registers
    nothing. That matters because both the CLI path and the pytest path call it, and a
    loader that double-registered would raise on the second caller.
    """
    for name in case_modules():
        importlib.import_module(f"{_PACKAGE}.{name}")
    return implemented_case_ids()
