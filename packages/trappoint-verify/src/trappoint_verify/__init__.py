# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-verify`` — the offline verifier a stranger runs, with nothing of ours.

One command, one dependency, no network:

.. code-block:: console

    $ uvx trappoint-verify verify --bundle bundle.json

The deliverable of this package is not the code. It is the sentence *"checks 1-7 and 9-16
require no access to our database and no cooperation from us"* being **true when a hostile
expert tests it**. Three mechanisms keep that sentence honest, and each of them is a test
rather than a promise:

``tests/test_dependency_floor.py``
    walks the AST of every module under ``src/trappoint_verify`` and asserts the top-level
    import set is a subset of the standard library plus ``cryptography`` — and that
    ``trappoint_ledger`` and ``trappoint_jcs`` appear nowhere at all.

``tests/test_no_network.py``
    patches ``socket.socket`` to raise and runs the entire check suite. "Requires no
    cooperation from us" is a 200 ms assertion, not a claim in a README.

``scripts/custody/check_vendored_canon.py``
    asserts the vendored canonicaliser is byte-identical to the one the sequencer used.
    A verifier whose canonicaliser has drifted from the log's is a verifier that agrees
    with nothing.

And one that keeps the *output* honest: a check may report ``PASS``, ``FAIL`` or
``SKIP(reason)``, and a ``SKIP`` is printed in the same weight, in the same section and
under a ``NOT CHECKED`` banner at the top of the report — with its own exit code, so a
green CI lane cannot mean "we did not look". See :mod:`trappoint_verify.report`.
"""

from __future__ import annotations

from typing import Final

__all__ = ["__version__"]

#: Distribution version. Kept in step with ``pyproject.toml`` by
#: ``tests/test_dependency_floor.py::test_version_matches_pyproject``, because a report
#: that names a version the wheel does not have is a report nobody can reproduce.
__version__: Final[str] = "0.1.0"
