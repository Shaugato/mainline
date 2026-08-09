# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Follower reads, and the one combination that is never allowed.

ARCHITECTURE.md §9 gives this domain two rules that look like performance advice
and are not:

* audit, ancestry-report and fixity-patrol reads use
  ``AS OF SYSTEM TIME follower_read_timestamp()`` — roughly 4.2 s of staleness —
  **so patrol never contends with permit merges**;
* **gate reads never use follower or bounded-staleness reads.**

Read together they forbid one thing absolutely: a *stale read of a gate table*. A
patrol that answered a gate question from a follower read would be answering with
data that is 4.2 seconds old, and the failure would be invisible — the merge would
succeed, the finding would be recorded, and the two would disagree about a moment
nobody wrote down.

So this module makes both rules structural. Every patrol read is constructed
through :func:`patrol_read`, which welds the preamble on and refuses any statement
naming a table the merge gate reads. There is no other constructor in this
package, and a caller who wants one has to write the string themselves and get
past :func:`assert_patrol_safe`, which the emitter runs on everything.

Skipping the preamble is not merely slower: the scan then takes read locks on rows
a permit merge is trying to write, and the first symptom is a `40001` **on the
merge**, in a different process, minutes later.

*Verified-status note.* ``BEGIN; SET TRANSACTION AS OF SYSTEM TIME
follower_read_timestamp();`` is the documented CockroachDB idiom and is what these
statements emit. That ``cluster_logical_timestamp()`` inside such a transaction
returns that transaction's read timestamp — which is how ``patrol_run.as_of_hlc``
gets its value — is documented behaviour that **this repository has not yet
measured on v26.2**. ``tests/integration/fixity`` carries the assertion and skips
with a reason until a cluster is available; nothing here claims it has been
observed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .errors import GateReadFromPatrol, StaleFollowerRead

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "AS_OF_HLC_SQL",
    "GATE_TABLES",
    "PATROL_READ_PREAMBLE",
    "PATROL_ROLE",
    "Statement",
    "assert_patrol_safe",
    "patrol_read",
]

#: The SQL role this package's statements are written for. §11.2 and
#: `verticals/mainline/db/GRANTS.yaml`: INSERT on `observed_assertion`,
#: `patrol_run`, `drift_finding`, `time_witness` and `discordance_warrant`, and
#: SELECT on `mainline`. No UPDATE anywhere, on anything. Layer 5 of the
#: injection posture — capability starvation — is this line plus the grant that
#: backs it, and :func:`assert_patrol_safe` is what keeps the code inside it.
PATROL_ROLE: Final[str] = "agent_patroller"

#: Opened before every patrol read. `SET TRANSACTION AS OF SYSTEM TIME` must be
#: the first statement in the transaction, which is why this is a preamble and
#: not a clause bolted onto each `SELECT`: one timestamp for the whole scan means
#: every finding in a run describes the same instant, and `patrol_run.as_of_hlc`
#: is a fact about the run rather than about whichever row was read first.
PATROL_READ_PREAMBLE: Final[tuple[str, ...]] = (
    "BEGIN",
    "SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp()",
)

#: Read inside the follower-read transaction to record which instant the scan saw.
AS_OF_HLC_SQL: Final[str] = "SELECT cluster_logical_timestamp() AS as_of_hlc"

#: Tables the merge gate reads. A patrol statement that names one of these is
#: refused, whether or not it carries the preamble — the two rules compose into a
#: prohibition, and encoding it as a list means a table added to the gate is a
#: one-line change here rather than a review nobody schedules.
GATE_TABLES: Final[frozenset[str]] = frozenset(
    {
        "permit",
        "permit_event",
        "blocking_check",
        "disposition",
        "carried_disposition",
        "merge_record",
        "change_request",
        "exposure_line",
        "exposure_receipt",
        "clause_blame_closure",
        "clause_blame_current",
        "identity_residue",
        "ledger_checkpoint",
    }
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


@dataclass(frozen=True, slots=True)
class Statement:
    """One statement and its parameters. This package never holds a driver.

    ``preamble`` is the statements that must run first in the same transaction —
    empty for a write, the follower-read preamble for a read. Returning it as data
    rather than executing it is what keeps the SQL role, the connection and the
    transaction boundary in the caller's hands, where the grant matrix can see
    them.
    """

    sql: str
    params: tuple[Any, ...] = ()
    preamble: tuple[str, ...] = ()

    @property
    def is_follower_read(self) -> bool:
        """True when this statement runs at a follower-read timestamp."""
        return self.preamble == PATROL_READ_PREAMBLE

    def mentions(self, table: str) -> bool:
        """Report whether the statement names ``table``, schema-qualified or bare."""
        return table in _tables_named(self.sql)


def _tables_named(sql: str) -> frozenset[str]:
    """Every bare and schema-qualified identifier tail appearing in ``sql``.

    Deliberately over-inclusive: a column called ``permit_event`` would trip this
    check even though it is not a table. That direction of error costs one
    rename; the other direction costs a stale gate read that nobody notices.
    """
    names: set[str] = set()
    for match in _IDENTIFIER.finditer(sql):
        token = match.group(0)
        names.add(token)
        if "." in token:
            names.add(token.rsplit(".", 1)[1])
    return frozenset(names)


def assert_patrol_safe(statement: Statement) -> Statement:
    """Return ``statement`` unchanged, or refuse it.

    Two refusals, and they are independent:

    * a statement naming a gate table raises :class:`GateReadFromPatrol` —
      the patrol has no business reading, and no grant to write, any of them;
    * a ``SELECT`` without the follower-read preamble raises
      :class:`StaleFollowerRead`.

    Writes deliberately do **not** carry the preamble: an ``INSERT`` at a past
    timestamp is not a thing, and a write inside a follower-read transaction would
    be refused by the database anyway. The check is therefore on reads only, and
    the asymmetry is the reason the preamble is a field rather than a flag.
    """
    named = _tables_named(statement.sql)
    for table in sorted(GATE_TABLES):
        if table in named:
            raise GateReadFromPatrol(statement.sql, table)
    head = statement.sql.lstrip().split(None, 1)[0].upper() if statement.sql.strip() else ""
    if head in ("SELECT", "WITH") and not statement.is_follower_read:
        raise StaleFollowerRead(statement.sql)
    return statement


def patrol_read(sql: str, params: Sequence[Any] = ()) -> Statement:
    """Build a patrol read: preamble welded on, gate tables refused.

    This is the only read constructor in the package. A caller cannot forget the
    preamble, because there is no path that omits it, and cannot reach a gate
    table, because the check runs before the statement exists as a value.
    """
    return assert_patrol_safe(
        Statement(sql=sql, params=tuple(params), preamble=PATROL_READ_PREAMBLE)
    )
