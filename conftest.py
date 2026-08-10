# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The repository-root conftest: one cluster for the session, and no session that hangs.

This file exists because of two things measured on 2026-08-10, neither of them inferred.

**Thirteen clusters.** A full-suite run started thirteen private single-node CockroachDB
containers concurrently, each with ``--cache=.25 --max-sql-memory=.25``. All thirteen exited
7 or 8, took the real node ``mainline-crdb`` down with them, and left the Docker engine API
answering HTTP 500.

**A hang, not a red.** The run did not fail; it wedged, accumulating about one CPU-second per
wall minute. Fixtures connect without ``connect_timeout``, so a dead node is an infinite wait,
and ``pytest-timeout``'s thread method cannot interrupt a hang inside *session-scoped fixture
setup* — which is why ``timeout = 120`` in ``pyproject.toml`` never fired. Measured here, a
connect to a black-holed address raised ``ConnectionTimeout`` after **130.1 s** with no
``PGCONNECT_TIMEOUT`` and after **3.1 s** at ``PGCONNECT_TIMEOUT=3``.

**Nothing in this file edits a domain fixture, and nothing needs to.** All twenty-three
container-spawning files check an environment DSN *first* and only reach for Docker when it is
unset. Four spellings are in use — ``MAINLINE_TEST_DSN`` (28 occurrences), ``COCKROACH_URL``
(19), ``CRDB_URL`` (17), ``TRAPPOINT_DSN`` (3) — and one cluster published under all four
collapses thirteen into one. The same seam holds for the image: 33 files default to the
FLOATING tag ``cockroachdb/cockroach:latest-v26.2`` and every one of them reads
``MAINLINE_CRDB_IMAGE`` first, so publishing the ``compose.yaml`` pin means the floating
default is never reached.

Order matters, and it is why two things happen at **import** time rather than in
``pytest_configure``:

* ``PGCONNECT_TIMEOUT`` — anything that connects during collection must already have it.
* the image pin — thirty-three modules read ``MAINLINE_CRDB_IMAGE`` at *module import* time,
  which happens during collection, so an export that waited for a fixture would be too late.

The DSN cannot be published this early: the session has to find or start the cluster first,
and that belongs in ``pytest_configure``, which
:mod:`trappoint_testkit.plugin` provides. See ``pytest --crdb=auto|reuse|spawn|none``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_TESTKIT_SRC = ROOT / "packages" / "trappoint-testkit" / "src"
_PLUGIN = "trappoint_testkit.plugin"

# The workspace is not always installed — `uv.lock` describes a seven-member workspace against
# 27 distributions on disk, so a fresh checkout may have none of them importable. The testkit
# is the one package the session cannot start without, so it is made importable from source
# rather than assumed. `find_spec` rather than `import` so that an installed copy always wins
# and nothing is executed just to answer "is it there".
if (
    importlib.util.find_spec("trappoint_testkit") is None
    and _TESTKIT_SRC.is_dir()
    and str(_TESTKIT_SRC) not in sys.path
):  # pragma: no cover - which branch runs depends on whether the workspace is installed
    sys.path.insert(0, str(_TESTKIT_SRC))

#: The plugin is loaded EXACTLY ONCE, by whichever of the two routes is available, and naming
#: it here is conditional for a measured reason. The package registers a ``pytest11`` entry
#: point, which pytest loads before it imports this file; naming an already-imported module in
#: ``pytest_plugins`` makes pytest call ``mark_rewrite`` on it, which raises
#: ``PytestAssertRewriteWarning: Module already imported so cannot be rewritten`` — and
#: ``filterwarnings = ["error", …]`` in `pyproject.toml` turns that into a hard config-time
#: failure of the entire session. Observed exactly that way the moment the package was
#: installed into `.venv`. So: if the entry point already loaded it, say nothing; if nothing is
#: installed — a bare clone, which is the case this file exists for — name it.
pytest_plugins: list[str] = [] if _PLUGIN in sys.modules else [_PLUGIN]


#: Measured: 130.1 s unset versus 3.1 s at 3, connecting to a black-holed address. Five is
#: chosen over three because a cold container's first accept can be slow and a fixture that
#: gives up on a node that is genuinely coming up is its own kind of lie. An operator who has
#: already exported a value keeps it.
DEFAULT_PGCONNECT_TIMEOUT = "5"


def _prepare_environment() -> None:
    """Publish the connect timeout and the image pin before anything is collected."""
    if not os.environ.get("PGCONNECT_TIMEOUT"):
        os.environ["PGCONNECT_TIMEOUT"] = DEFAULT_PGCONNECT_TIMEOUT
    try:
        from trappoint_testkit import image
    except ImportError:
        # A checkout with no psycopg cannot run a cluster test anyway; the plugin will say so
        # in the header. Refusing to collect at all would be a worse failure than that.
        return
    try:
        image.export_pin(start=ROOT)
    except image.PinNotFound:
        # compose.yaml is the single source of the version constant. If it has moved, say
        # nothing here and let the plugin's header report it — a conftest that raises during
        # import turns a diagnosable problem into an uncollectable repository.
        return


_prepare_environment()
