# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The MAINLINE demo read API — one Lambda handler, twelve GET resources, no framework.

WHAT THIS PACKAGE IS
--------------------
`verticals/mainline/apps/console` declares sixteen resources in `src/data/resources.ts`
and holds the JSON Schema that governs each response in `contracts/*.schema.json`. Until
this package existed nothing in the repository implemented any of them — a `grep` for
``fastapi|flask|starlette|uvicorn|aiohttp.web`` over every ``.py`` and ``.toml`` outside
``.venv`` returned nothing at all.

This package implements the twelve GETs and the spine the four POSTs plug into:

* :mod:`~mainline_demo_api.app` — routing and the Lambda entry point.
* :mod:`~mainline_demo_api.envelope` — the read envelope, its provenance chips, and the
  JSON encoding that turns driver values into contract-shaped ones.
* :mod:`~mainline_demo_api.db` — one connection reused across warm invocations, the DSN
  read from SSM Parameter Store, and the `40001` retry a managed multi-node cluster needs.
* :mod:`~mainline_demo_api.reads` — the twelve GET resources.
* :mod:`~mainline_demo_api.health` — ``GET /v1/health``.

The four POSTs live in ``mainline_demo_api.transitions``, which this package does NOT
provide. :func:`mainline_demo_api.app.handler` imports it lazily and answers ``501`` with
the module name when it is absent, so the read surface is deployable before the write
surface exists rather than after it.

THE CONTRACT IS NOT OURS TO CHANGE
----------------------------------
``console/src/data/transport.ts::finishExchange`` validates every byte this package
emits, and it rejects a payload whose ``envelope.resource`` differs from the requested
key, or whose ``envelope.schema_id`` is not the exact ``$id`` the console holds:

    *A payload that names a contract we do not hold is not forward compatibility; it is
    an unverifiable claim.*

So :data:`mainline_demo_api.envelope.SCHEMA_IDS` is a transcription of
``console/src/data/resources.ts``, and ``tests/test_envelope.py`` re-reads that TypeScript
file and refuses the build if the two ever disagree.
"""

from __future__ import annotations

#: Distribution version. Carried in no payload — the honesty chrome reads the schema
#: fingerprint of the DATABASE, which is the thing a judge can independently check.
__version__ = "0.1.0"

__all__ = ["__version__"]
