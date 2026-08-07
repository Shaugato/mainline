# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-migrate`` — forward-only CockroachDB migrations with a schema attestation.

Why this exists rather than golang-migrate, which is otherwise the right tool:
**the runner must write the schema attestation inside the same connection discipline
that writes the ledger.** An external binary applies the DDL and then a wrapper attests
it from a second connection, which means there is a window in which the schema has
changed and nothing has recorded what it changed to. For a system whose value
proposition is that the record is trustworthy, that window is the product.

Everything else follows from CockroachDB facts rather than from taste:

* one DDL statement per file, because a multi-statement file is not atomic here;
* ``SHOW JOBS`` polled to terminal success, because the statement returns before the
  schema change finishes;
* a real lock table, because there are no advisory locks;
* no sequences anywhere, enforced by ``trappoint migrate lint``, because the ledger's
  gap-free-by-CAS claim is worth nothing if one migration reintroduces one.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
