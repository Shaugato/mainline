# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Per-case tenancy isolation.

Cases are isolated by a **fresh tenancy scope per case**, not by a transaction rollback
and not by truncating tables between runs. Three reasons, and the third is the one that
actually forces it:

1. The suite parallelises against one cluster, so cases must not see each other's rows.
2. Several of the objects under test are **append-only**; a suite that cleaned up after
   itself would be exercising a delete path the product refuses to have.
3. Row-level security is scoped by ``site_id``. A suite that shared one site would be
   testing the gate with the security model switched off, which is the one configuration
   nobody ships.

Scope ids are **deterministic**: ``uuid5(namespace, f"{run_id}:{case_id}")``. A failing
case can therefore be re-run on its own and land in exactly the same tenancy, so the
rows it left behind are the rows you inspect. A random id would make every re-run a
different investigation.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

__all__ = ["CONFORMANCE_NAMESPACE", "SiteScope", "new_run_id", "scope_for", "scoped"]

# A fixed UUIDv5 namespace for the suite. Derived once from the DNS namespace and the
# suite's own name so that two independent checkouts compute identical scope ids for the
# same (run_id, case_id) pair, which is what makes a failure reproducible across
# machines.
CONFORMANCE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "conformance.trappoint.spec")


@dataclass(frozen=True, slots=True)
class SiteScope:
    """The tenancy one case runs in."""

    run_id: str
    case_id: str
    site_id: uuid.UUID

    @property
    def external_ref(self) -> str:
        """A per-case natural key, for tables carrying ``UNIQUE (site_id, external_ref)``."""
        return f"conf-{self.case_id.lower()}"

    def label(self) -> str:
        """One line identifying the scope in a failure report."""
        return f"{self.case_id} · run {self.run_id} · site {self.site_id}"


def new_run_id(explicit: str | None = None) -> str:
    """Return a run identifier.

    ``TRAPPOINT_CONFORM_RUN_ID`` pins it, which is how CI makes a re-run of a failed job
    land in the same tenancy as the original — the rows are still there to look at.
    """
    if explicit:
        return explicit
    from_env = os.environ.get("TRAPPOINT_CONFORM_RUN_ID")
    if from_env:
        return from_env
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def scope_for(run_id: str, case_id: str) -> SiteScope:
    """Derive the deterministic scope for one case within one run."""
    return SiteScope(
        run_id=run_id,
        case_id=case_id,
        site_id=uuid.uuid5(CONFORMANCE_NAMESPACE, f"{run_id}:{case_id}"),
    )


@contextmanager
def scoped(run_id: str, case_id: str) -> Iterator[SiteScope]:
    """Context manager form.

    It does **not** clean up. The rows a case wrote are the evidence of what it did, and
    a suite whose teardown deletes from an append-only table is a suite exercising a
    path the product does not have. Disposal is the container's job
    (``just nuke``), which is also the only disposal the unwelding harness may use.
    """
    yield scope_for(run_id, case_id)
