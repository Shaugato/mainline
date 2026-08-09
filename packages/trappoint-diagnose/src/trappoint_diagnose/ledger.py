# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Recording a refusal: one INSERT into an append-only table, constraint name verbatim.

The table is migration ``0071c`` and it is append-only by trigger (``0133``), so this
module has exactly one verb. There is no ``update``, no ``delete`` and no upsert, and not
because they were left out — the database refuses all three, so writing them would be
writing code whose only possible outcome is a P0001.

Two properties this module is responsible for, both of which the table then re-checks:

* **The scalar columns and the payload cannot disagree.** Every column written here is
  derived from the payload in this function, and the table's CHECKs compare them again.
  Denormalising without that comparison is how an index and its evidence drift apart.
* **The constraint name is stored VERBATIM.** No prettifying, no translation, no mapping
  to a friendlier phrase. The constraint name is the exhibit, and *"the merge was refused
  by `gate_closed_when_issued`"* is a materially better sentence in a courtroom than
  *"a rule was violated"*.

``recorded_by`` is the identity of the PROCESS that observed the refusal, not of a person.
It exists so a ledger row can be traced to a service; it is not, and must never become, a
statement about who was at fault (invariant I15).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .model import RefusalPayload
from .oracle import Connection

__all__ = ["INSERT_TEMPLATE", "ledger_row", "record_refusal"]

INSERT_TEMPLATE = """
INSERT INTO {schema}.refusal_ledger (
  refusal_id, observed_at, spec_version, profile, sqlstate, constraint_name,
  constraint_source, message, subject_kind, subject_id, gate_epoch, diagnosis,
  probe_calls, mus_cardinality, naa_kind, naa_reason, payload, recorded_by
) VALUES (
  %(refusal_id)s, %(observed_at)s, %(spec_version)s, %(profile)s, %(sqlstate)s,
  %(constraint_name)s, %(constraint_source)s, %(message)s, %(subject_kind)s,
  %(subject_id)s, %(gate_epoch)s, %(diagnosis)s, %(probe_calls)s, %(mus_cardinality)s,
  %(naa_kind)s, %(naa_reason)s, %(payload)s::JSONB, %(recorded_by)s
)
"""


def ledger_row(payload: RefusalPayload, *, recorded_by: str) -> dict[str, Any]:
    """Derive every ledger column from the payload. Nothing here is supplied twice.

    The one exception is ``recorded_by``, which is a fact about the observer rather than
    about the refusal and therefore cannot come from the payload.
    """
    if not recorded_by:
        raise ValueError(
            "recorded_by names the process that observed the refusal; an unattributed "
            "ledger row cannot be traced to the service that wrote it"
        )
    wire = payload.to_wire()
    naa = wire.get("naa")
    return {
        "refusal_id": wire["refusal_id"],
        "observed_at": wire["observed_at"],
        "spec_version": wire["spec_version"],
        "profile": wire.get("profile"),
        "sqlstate": wire["sqlstate"],
        "constraint_name": wire["constraint"],
        "constraint_source": wire["constraint_source"],
        "message": wire["message"],
        "subject_kind": wire["subject_kind"],
        "subject_id": wire["subject_id"],
        "gate_epoch": wire["gate_epoch"],
        "diagnosis": wire["diagnosis"],
        "probe_calls": wire["probe_calls"],
        "mus_cardinality": len(wire["mus"]),
        "naa_kind": None if naa is None else naa["kind"],
        "naa_reason": wire["naa_reason"],
        "payload": json.dumps(wire, sort_keys=True, separators=(",", ":")),
        "recorded_by": recorded_by,
    }


def record_refusal(
    connection: Connection,
    payload: RefusalPayload,
    *,
    schema: str,
    recorded_by: str,
) -> Mapping[str, Any]:
    """Append *payload* to ``<schema>.refusal_ledger``. Returns the row that was written.

    The caller owns the transaction. That is deliberate: a gate service records the
    refusal in the same unit of work as whatever else it does about it, and a function
    that committed on its own behalf would take that choice away — and would sometimes
    commit a diagnosis for a transaction the caller then abandoned.

    *schema* is interpolated because a schema name cannot be a bind parameter in any
    dialect. It comes from the binding, never from a refusal or a document, and it is
    checked here rather than trusted.
    """
    if not schema.replace("_", "").isalnum():
        raise ValueError(f"{schema!r} is not a plain schema name")
    row = ledger_row(payload, recorded_by=recorded_by)
    cursor = connection.cursor()
    try:
        cursor.execute(INSERT_TEMPLATE.format(schema=schema), row)
    finally:
        cursor.close()
    return row
