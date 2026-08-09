# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Vendored code. Byte-identical copies, never edits.

``canon_v1.py`` here is a **byte-for-byte copy** of
``packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py``. It is not a port, not a subset
and not a tidied version, and it must never be reformatted — not even by a linter, not
even to fix a typo in a docstring.

Why a copy at all
-----------------
``trappoint-verify``'s dependency floor is ``cryptography`` and nothing else. That claim is
the product: a stranger installs one package, runs one command, and needs nothing from us.
Depending on ``trappoint-jcs`` to canonicalise would put a MAINLINE distribution inside the
verifier, and "zero MAINLINE dependencies" would become a sentence with an asterisk.

Why the copy is safe
--------------------
Because it is checked, not promised. ``scripts/custody/check_vendored_canon.py`` asserts
``sha256(this file) == sha256(the original)`` over LF-normalised bytes, and
``spec/custody/canon-registry.yaml`` pins that digest for every canonicaliser MAINLINE has
ever shipped. A pull request that edits either copy without the other fails the build with
*"the verifier's one-dependency claim is false while this differs"*.

Verifier check 10 closes the loop at runtime: ``canon_v1.canon_src_sha256()`` hashes this
file's own bytes and compares them against the ``canon:`` line inside every signed
checkpoint. The scheme's own code is therefore inside the scheme, and a canonicaliser
downgrade (attack A5) changes a value that is covered by the log signature.
"""

from __future__ import annotations

__all__: list[str] = []
