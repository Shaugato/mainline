# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Deployment scripts for the MAINLINE demo on CockroachDB Cloud.

Three programs, run in this order, each idempotent and each writing its own evidence:

1. :mod:`scripts.deploy.cloud_chain`  — the migration chain into database ``mainline_demo``
2. :mod:`scripts.deploy.cloud_roles`  — the two SQL logins the deployment needs
3. :mod:`scripts.deploy.seed_demo`    — the static demo world and the one refusable permit

They are a package rather than three loose files so that the shared pieces — the DSN
rewriter, the ``40001`` retry loop, the evidence writer — live in one place and cannot
drift between the applier and the seeder. That matters here more than usual: the retry
loop is the difference between a chain that applies to a managed multi-node cluster and
one that dies halfway (``docs/leads/deploy-plan.md`` §1.2), so it must be the *same* loop
in all three.

Every entry point takes ``--dsn`` and falls back to ``COCKROACH_DSN``. **No program in
this package ever prints a DSN, a password, or any query string that could carry one.**
:func:`scripts.deploy.cloud_chain.redact` is the single chokepoint for that and is used
on every value that reaches stdout or an evidence file.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "1.0.0"
