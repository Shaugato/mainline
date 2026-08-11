# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The AWS execution fleet: one client contract, one redactor, one artefact envelope.

Every program under ``scripts/aws/`` imports :mod:`scripts.aws._common` and nothing
else AWS-shaped.  That is not tidiness — three of the fleet's standing prohibitions
are only enforceable at a chokepoint:

* **Residency.**  ``ARCHITECTURE §10.1`` says Australian safety narratives are embedded
  in ``ap-southeast-2`` or not at all.  A cross-region inference profile
  (``global.*``, ``us.*``, ``eu.*``, ``apac.*``) is the exact negation of that promise,
  and ``ap-southeast-2`` will happily serve one.  ``assert_in_region`` refuses it, and
  it can only refuse calls that pass through it.
* **Redaction.**  A 12-digit account id, a Cloud DSN password and an AWS key shape must
  not reach a committed file.  ``artefact()`` runs ``redact()`` over the whole payload
  on the way out, so a worker cannot forget.
* **Cost.**  Every call is priced against one table, so the fleet's spend is a sum of
  published ledger entries rather than nine independent guesses.

Programs here are run directly::

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/probe_bedrock.py

``scripts`` is a namespace package (it has no ``__init__.py``); this sub-package has one
so that ``from scripts.aws._common import ...`` resolves for tests that put the
repository root on ``sys.path``.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
