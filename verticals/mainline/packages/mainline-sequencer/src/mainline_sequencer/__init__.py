# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-sequencer`` — the singleton that turns intake into a dense, fork-free log.

Certificate Transparency splits *submission* from *merge*, and so do we: intake
(``mainline.ledger_intake``, random primary key, no hot row) scales with the cluster,
sequencing (``mainline.ledger_leaf``, dense, fork-free) is one writer per site. This
package is that writer.

Four properties are the whole deliverable, and each one is a mechanism rather than a
convention:

**1. ``seq`` is a compare-and-swap, never a sequence (CU-2).** It is derived inside the
appending transaction as ``COALESCE(max(seq), -1) + 1``. ``CREATE SEQUENCE``,
``nextval()``, ``SERIAL`` and ``unique_rowid()`` are banned repository-wide and
``trappoint migrate lint`` enforces the ban — which is load-bearing rather than
stylistic, because ``CREATE SEQUENCE`` *succeeds* on the target cluster
(``docs/adr/0002`` F4). Sequence increments survive rollback, so a sequence-numbered
ledger has legitimate gaps and a gap means nothing. A CAS-numbered ledger has none, so
**a gap MEANS tampering** — and that sentence is verifier check 9.

**2. The resulting ``23505`` is the only retryable ``23505`` in the repository, and it is
matched on CONSTRAINT NAME.** ``ledger_leaf_pkey`` and ``ledger_linear`` are contention.
``ledger_leaf_entry_unique`` is "already done". ``fk_site`` is a refusal. They share a
SQLSTATE and they are three different facts. :mod:`mainline_sequencer.append` bounds the
loop at eight attempts and lets every other constraint escape, because the one legitimate
retry becoming a laundry for real refusals is a far worse defect than the contention it
absorbs.

**3. Sequenced-ness is DERIVED, never written.** The batch is an anti-join against
``ledger_leaf``; there is no ``sequenced`` flag and there must never be one. The entire
ledger path is therefore ``INSERT`` + ``SELECT``, which is why the ``mainline_ledger``
role holds exactly those grants and why the Managed MCP server's insert-only write
surface is a structural match rather than a coincidence.

**4. The lease is a performance mechanism, not a correctness one.** CockroachDB has no
advisory locks, so one sequencer per site is elected by a CAS on
``mainline_ops.sequencer_lease.epoch``. Delete every lease row and the system still
cannot fork: correctness is ``ledger_leaf_pkey`` and ``ledger_linear``, which hold at any
isolation level and with no lease at all. Saying that plainly is what stops the lease
being quietly relied upon as the latter.

There is deliberately **no catch-all ``SequencerError``**. A caller able to catch
everything from the ledger path in one clause is a caller able to silence a refusal, and
in a product whose deliverable is a refusal that is the defect class rather than a style
nit. Each module raises named, specific exceptions.

Authority: ``ARCHITECTURE.md`` §5.6, §7.2 · ``spec/custody/ledger-schema.md`` §§1-6 ·
``spec/wire/checkpoint.md`` v1.0 · ``spec/wire/receipt.md`` v1.0 ·
``docs/leads/custody.md`` CU-1, CU-2 · ``docs/adr/0045-cas-sequencing-not-sequences.md``.
"""

from __future__ import annotations

from typing import Final

__version__: Final = "0.1.0"

__all__ = ["__version__"]

# NOTE ON THE ABSENCE OF RE-EXPORTS. Nothing is imported here on purpose. `handler.py`
# is a Lambda entry point and importing it eagerly would drag `psycopg` — and, through
# the runtime factory, `boto3` — onto the import path of anything that merely wants
# `mainline_sequencer.batch.SELECT_UNSEQUENCED` for a source-level assertion. The
# no-UPDATE-against-`ledger_*` test in the package's own suite reads module SOURCE, and
# a package whose `__init__` pulls in a driver cannot be inspected that cheaply.
