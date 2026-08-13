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
collapses thirteen into one. **The same was claimed of the image and was measured false on
2026-08-13.** Twenty files carried a hard-coded image, 34 occurrences between them. Fourteen
read ``MAINLINE_CRDB_IMAGE`` first, so the export below did displace their default — but
**six named the image outright, with no environment read at all**, and no export could reach
those. They ran on a tag that moves, which is the dev/CI skew the schema fingerprint exists
to catch. All twenty now read the pin out of ``compose.yaml`` through
:func:`trappoint_testkit.pinned_image`, and ``MAINLINE_CRDB_IMAGE`` still outranks it when an
operator sets one. The export below is now an optimisation — one parse for the session
instead of twenty — and no longer the thing that makes the version right.

Order matters, and it is why two things happen at **import** time rather than in
``pytest_configure``:

* ``PGCONNECT_TIMEOUT`` — anything that connects during collection must already have it.
* the image pin — twenty modules resolve their image at *module import* time, which happens
  during collection, so an export that waited for a fixture would be too late.

The DSN cannot be published this early: the session has to find or start the cluster first,
and that belongs in ``pytest_configure``, which
:mod:`trappoint_testkit.plugin` provides. See ``pytest --crdb=auto|reuse|spawn|none``.

**The testkit imports without a database driver, and that is a property this file relies on.**
Measured on 2026-08-10, run 31372088311: all seven ``boundary`` jobs died here, before a
single assertion, with ``ModuleNotFoundError: No module named 'psycopg'`` raised while pytest
imported the plugin named below. Those lanes install ``mainline-boundary`` and ``pytest`` and
nothing else, deliberately — E3 measures what a *minimal* kernel-plane environment can reach.
``trappoint_testkit`` now imports the driver inside the functions that open a socket, so
registering ``--crdb`` and reading the image pin cost nothing, and a lane with no driver gets
a header line saying so rather than a traceback.

The corollary, and the reason ``_report`` below exists: if the plugin ever again becomes
unimportable, that must arrive as **one sentence naming the cause**, followed by pytest's own
hard error. Not as a silent ``except ImportError: return``, which is what this file used to
do. Since the twenty fixture modules import :mod:`trappoint_testkit` themselves, a testkit
this file cannot import is a testkit *they* cannot import either: the session now ends in a
collection error rather than in a quiet run against a version nobody chose. The sentence
below is what turns that error into a diagnosis.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_TESTKIT_SRC = ROOT / "packages" / "trappoint-testkit" / "src"
_PLUGIN = "trappoint_testkit.plugin"

#: Prefixed so the line is greppable in a CI log that is mostly pytest's own output.
_TAG = "conftest[trappoint-testkit]:"


def _report(message: str) -> None:
    """Write one diagnostic line to stderr, flushed, so it survives a hard exit after it.

    stderr rather than ``warnings.warn``: ``pyproject.toml`` sets
    ``filterwarnings = ["error", …]``, and a warning raised at conftest *import* time — before
    pytest has installed its filters — is a different thing on every pytest version. A line on
    stderr is the same thing everywhere, and it is what a judge reading the Actions log sees.

    ``sys.stderr.write`` rather than ``print``: every branch that calls this is a branch that
    precedes a possible hard failure, and the explicit flush is the whole value of the line.
    """
    sys.stderr.write(f"{_TAG} {message}\n")
    sys.stderr.flush()


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
    """Publish the connect timeout and the image pin before anything is collected.

    Nothing here raises. A conftest that raises during import turns a diagnosable problem
    into an uncollectable repository, and the repository is the thing being demonstrated.
    Nothing here is silent either: every branch that gives up says on stderr what it gave up
    on, what the consequence is, and what would fix it.
    """
    if not os.environ.get("PGCONNECT_TIMEOUT"):
        os.environ["PGCONNECT_TIMEOUT"] = DEFAULT_PGCONNECT_TIMEOUT
    try:
        from trappoint_testkit import image
    except ImportError as exc:
        # `trappoint_testkit.image` is one regex over `compose.yaml` and has no third-party
        # dependency of any kind, so reaching here means the package is not on the path at
        # all — not that some driver is missing. Say which path was tried; the answer is
        # almost always that `packages/trappoint-testkit/src` is absent from the checkout.
        _report(
            f"cannot import trappoint_testkit.image ({exc}). The CockroachDB image pin was "
            f"NOT published, and the twenty cluster fixtures import the same module to read "
            f"it, so they are about to fail collection for this one reason. No fixture "
            f"invents a version to carry on with — that is the whole point — so this line is "
            f"the cause and everything after it is consequence. Looked for the package on "
            f"sys.path and at {_TESTKIT_SRC}."
        )
        return
    try:
        image.export_pin(start=ROOT)
    except image.PinNotFound as exc:
        # compose.yaml is the single source of the version constant. Each cluster fixture
        # calls pinned_image() itself when this export does not happen, so it will raise the
        # same PinNotFound during collection. That is the designed behaviour — a fixture that
        # invented a version here would reintroduce the dev/CI skew the schema fingerprint
        # exists to catch — and this line is what names the cause before pytest names twenty
        # symptoms.
        _report(
            f"the CockroachDB version constant could not be read ({exc}). Every cluster "
            f"fixture reads it the same way and will raise the same error during collection. "
            f"Restore the 'trappoint:crdb-image-pin' marker above the crdb service's "
            f"image: key in compose.yaml."
        )
        return


def _check_the_plugin_can_load() -> None:
    """Say in one sentence why the plugin will not import, *before* pytest says it in forty.

    This does not swallow anything: the module is named in ``pytest_plugins`` either way, so
    an unimportable plugin still fails the session hard, with pytest's own traceback. What
    this adds is the sentence that traceback does not contain — which of the two loading
    routes was in play, and what the missing name means for the run. Run 31372088311 is the
    case in point: forty lines of ``importlib`` frames whose operative content was one
    module name.

    ``find_spec`` rather than ``import``: importing the plugin here would put it in
    ``sys.modules`` and make the ``pytest_plugins`` guard above go quiet, and the plugin
    would then be loaded by nobody and the ``--crdb`` option would not exist.
    """
    try:
        found = importlib.util.find_spec(_PLUGIN)
    except Exception as exc:  # noqa: BLE001 - a broken parent package raises anything at all
        _report(
            f"{_PLUGIN} cannot even be located: importing its parent package raised "
            f"{type(exc).__name__}: {exc}. pytest is about to fail this session while "
            f"loading it. Note that trappoint_testkit is stdlib-only to import by design — "
            f"a third-party ModuleNotFoundError here means a module-scope import has been "
            f"reintroduced into trappoint_testkit/cluster.py or __init__.py."
        )
        return
    if found is None:
        _report(
            f"{_PLUGIN} is not importable from this environment and is not on "
            f"{_TESTKIT_SRC}; pytest will refuse the session in a moment. Install the "
            f"workspace, or run from a checkout that carries packages/trappoint-testkit."
        )


_check_the_plugin_can_load()
_prepare_environment()
