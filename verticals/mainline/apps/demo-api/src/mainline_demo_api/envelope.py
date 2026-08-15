# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The read envelope, its provenance chips, and the encoding that makes a driver row wire-legal.

READ ``console/src/data/transport.ts::finishExchange`` BEFORE CHANGING ANYTHING HERE.
That function is the client for every byte this module produces, and it enforces four
post-conditions in a fixed order:

1. the body parses as JSON;
2. it satisfies the resource's contract, ``envelope.schema.json`` included;
3. ``envelope.resource`` equals the key that was requested;
4. ``envelope.schema_id`` equals the exact ``$id`` the console holds for that key.

Rule 4 has no tolerance and is not meant to have one. Its own comment says so:

    *A payload that names a contract we do not hold is not forward compatibility; it is
    an unverifiable claim.*

:data:`SCHEMA_IDS` is therefore a transcription of ``console/src/data/resources.ts``
rather than a scheme for deriving ids from keys — ``change_request`` is governed by
``change-request.schema.json`` and ``exposure_receipt`` by ``exposure.schema.json``, and
no naming rule produces both of those from their keys.
``tests/test_envelope.py::test_schema_ids_match_the_console_declaration`` parses the
TypeScript and fails the build if this table drifts from it.

── THE PROVENANCE LIST IS NOT DECORATION ────────────────────────────────────────────
``common.schema.json`` fixes five chips, and each is a different claim about where a
number came from:

===============  =======================================================================
``db:column``    a column the database wrote. Not "a value that came out of a query" —
                 a *column*. A count this API computed is not one, however true it is.
``db:constraint``the name or text of a CHECK/FK exactly as the catalog reports it.
``recomputed``   the CONSOLE re-derived it from signed bytes in a Worker (D6). This API
                 never emits it: we are the emitter, and an emitter cannot vouch for a
                 recomputation the reader has not performed.
``derived``      computed by this read API from columns it names in ``statement_refs``.
``staged``       hand-authored, with no cluster behind it.
===============  =======================================================================

And the contract's own instruction for anything else, which this module implements
literally in :class:`Provenance`:

    *A pointer absent from this list has NO chip and is rendered without one — an
    unclaimed provenance is better than a comfortable default.*

── ``staged`` IS A COUPLED PAIR ─────────────────────────────────────────────────────
``envelope.schema.json`` binds ``staged`` and ``staged_note`` with an ``if/then/else``:
true demands a non-empty note, false demands the note be ``null``. :func:`read_envelope`
refuses to build a violating envelope in *this* process rather than letting the console
discover it over the wire, because a flag nobody has to justify is a flag that will be
set by whoever finds it convenient.
"""

from __future__ import annotations

import base64
import datetime as _dt
import decimal
import ipaddress
import json
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Literal

__all__ = [
    "CONTRACT_BASE",
    "ENVELOPE_VERSION",
    "PROVENANCE_CAP",
    "PROVENANCE_CHIPS",
    "SCHEMA_IDS",
    "STATEMENT_REF_CAP",
    "Chip",
    "EnvelopeError",
    "Provenance",
    "b64",
    "hexlify",
    "jsonable",
    "read_envelope",
    "rfc3339",
    "statement_ref",
]

#: The contract namespace. Every ``$id`` under ``console/contracts/`` begins with it.
CONTRACT_BASE: Final = "https://console.mainline.trappoint.org/contracts/1.0/"

#: ``envelope.schema.json`` pins this to ``const: 1``. A reader that does not recognise
#: the version refuses the payload rather than guessing at it, so bumping it is a
#: breaking change to every consumer at once — which is the point of having it.
ENVELOPE_VERSION: Final = 1

Chip = Literal["db:column", "db:constraint", "recomputed", "staged", "derived"]

#: ``common.schema.json#/$defs/provenance_chip``, closed.
PROVENANCE_CHIPS: Final[frozenset[str]] = frozenset(
    {"db:column", "db:constraint", "recomputed", "staged", "derived"}
)

#: ``common.schema.json#/$defs/field_provenance`` — ``maxItems: 256``.
PROVENANCE_CAP: Final = 256

#: ``envelope.schema.json`` — ``statement_refs.maxItems: 32``.
STATEMENT_REF_CAP: Final = 32

#: Resource key → the ``$id`` of the contract governing its ``data``.
#:
#: TRANSCRIBED, NOT DERIVED, from ``console/src/data/resources.ts``, and it is a
#: transcription of the console's **eighteen** ``declare()`` calls — thirteen reads and
#: five POSTs. Six of the reads name a file whose stem is not their key
#: (``change_request`` → ``change-request``, ``blocking_checks`` → ``blocking-check``,
#: ``exposure_receipt`` → ``exposure``, ``clause_version`` → ``clause``,
#: ``clause_ancestry`` → ``ancestry``, ``recall_run`` → ``recall-run``), so any rule that
#: computed these would be a rule with six exceptions. The POST keys are carried too:
#: this module implements none of them, but ``app.py`` must be able to route them and
#: name their contract when the transitions module is absent.
#:
#: ``demo_gate_run`` IS THE ONE ENTRY THAT IS NOT A CONSOLE READ CONTRACT. The other
#: sixteen name a contract some function in this package emits: the twelve GETs through
#: :func:`read_envelope`, the four kernel POSTs through the ``invoke.schema.json``
#: envelope ``transitions`` builds. This one names ``gate-run.schema.json``, which
#: ``gate_run.py`` holds as ``GATE_RUN_SCHEMA_ID`` and stamps onto its own payload; the
#: success path never consults this table. It is transcribed here anyway for the two
#: reasons the table exists at all — the console declared it on 2026-08-14 and
#: ``tests/test_envelope.py::test_schema_ids_match_the_console_declaration`` compares the
#: two lists key for key, and ``app.py``'s 501 branch reads ``SCHEMA_IDS.get(key)`` to
#: name the contract a caller was denied at the one moment ``gate_run`` cannot be
#: imported to be asked. Measured 2026-08-14: that body's ``error.schema_id`` was
#: ``null`` for this key before the entry and is the ``gate-run.schema.json`` ``$id``
#: after it. Nothing else in this package changes.
SCHEMA_IDS: Final[Mapping[str, str]] = {
    "permit": f"{CONTRACT_BASE}permit.schema.json",
    "change_request": f"{CONTRACT_BASE}change-request.schema.json",
    "blocking_checks": f"{CONTRACT_BASE}blocking-check.schema.json",
    "disposition": f"{CONTRACT_BASE}disposition.schema.json",
    "exposure_receipt": f"{CONTRACT_BASE}exposure.schema.json",
    "clause_version": f"{CONTRACT_BASE}clause.schema.json",
    "clause_ancestry": f"{CONTRACT_BASE}ancestry.schema.json",
    "ledger": f"{CONTRACT_BASE}ledger.schema.json",
    "silence": f"{CONTRACT_BASE}silence.schema.json",
    "recall_run": f"{CONTRACT_BASE}recall-run.schema.json",
    "propagation": f"{CONTRACT_BASE}propagation.schema.json",
    "audit": f"{CONTRACT_BASE}audit.schema.json",
    "materialise_checks": f"{CONTRACT_BASE}invoke.schema.json",
    "sign_disposition": f"{CONTRACT_BASE}invoke.schema.json",
    "merge_permit": f"{CONTRACT_BASE}invoke.schema.json",
    "suspend_permit": f"{CONTRACT_BASE}invoke.schema.json",
    "demo_gate_run": f"{CONTRACT_BASE}gate-run.schema.json",
    # Declared by the console on 2026-08-15 and served by :mod:`subjects`. Unlike
    # ``demo_gate_run`` this one IS emitted through :func:`read_envelope` — it is a GET, it
    # is in ``reads.READS``, and this entry is what lets that happen. It exists because the
    # console addresses seven surfaces by identifier and had no way to learn one, so three
    # screens shipped identifiers nobody had seeded and answered 404 on the live URL.
    "demo_subjects": f"{CONTRACT_BASE}subjects.schema.json",
}

#: ``envelope.schema.json`` — ``resource`` pattern.
_RESOURCE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")

#: ``common.schema.json`` — a ``pointer`` is an RFC 6901 pointer, so it starts with ``/``.
_POINTER = re.compile(r"^/")

_STATEMENT_REF_KINDS: Final[frozenset[str]] = frozenset({"table", "view", "procedure", "statement"})


class EnvelopeError(RuntimeError):
    """An envelope this process refused to emit.

    Raised only for violations of ``envelope.schema.json`` that are visible without a
    validator: an unknown chip, an unclaimed ``staged`` flag, a resource key with no
    contract. It is a 500, never a 4xx — the caller did nothing wrong; we did.
    """


# ── Encoding ────────────────────────────────────────────────────────────────────────


def rfc3339(value: _dt.datetime) -> str:
    """Render *value* as an RFC 3339 instant in UTC, with a literal ``Z``.

    ``common.schema.json#/$defs/timestamp`` asserts ``format: date-time``, and the
    console's validator (``src/data/schema.ts``) checks it *strictly*: a real calendar
    date, a real clock time, and either ``Z`` or a numeric offset. `2026-02-30T00:00:00Z`
    is refused there, so a naive ``str(datetime)`` — which emits ``2026-08-10 12:00:00+00:00``
    with a space — would be refused too. Hence this function rather than ``.isoformat()``.

    A naive datetime is treated as UTC. The read paths never produce one (every column
    is ``TIMESTAMPTZ`` and psycopg returns it aware), but a silent ``+00:00`` on a naive
    value is a better failure than a ``TypeError`` at ``json.dumps`` time in a Lambda.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.UTC)
    utc = value.astimezone(_dt.UTC)
    micros = f".{utc.microsecond:06d}" if utc.microsecond else ""
    return f"{utc:%Y-%m-%dT%H:%M:%S}{micros}Z"


def hexlify(value: bytes | memoryview | bytearray | None) -> str | None:
    """Lowercase hex for a ``BYTES`` column, or ``None``.

    Most reads ask the database for ``encode(col,'hex')`` instead, because the cast is
    then visible in the statement a ``statement_ref`` can name. This exists for the
    columns fetched as bytes because something else has to happen to them first.
    """
    if value is None:
        return None
    return bytes(value).hex()


def b64(value: bytes | memoryview | bytearray | None) -> str | None:
    """Encode a ``BYTES`` column as standard base64, or pass ``None`` through.

    Done here rather than with SQL ``encode(col,'base64')`` because that function wraps
    its output at 76 columns, and a signature with newlines in it is a signature every
    downstream reader has to remember to unwrap.
    """
    if value is None:
        return None
    return base64.b64encode(bytes(value)).decode("ascii")


def jsonable(value: Any) -> Any:  # noqa: PLR0911 - one return per driver type, and the
    # mapping from driver type to contract shape is exactly what this function IS
    """Convert a driver value into something ``json.dumps`` accepts, losslessly.

    The conversions, and why each is the one the contracts ask for:

    ``UUID``            → its textual form; ``common.schema.json#/$defs/uuid``.
    ``datetime``        → :func:`rfc3339`.
    ``date`` / ``time`` → ISO 8601. No contract uses one; present so a future column
                          cannot produce a ``TypeError`` in production.
    ``timedelta``       → ``str``. ``v_unused_indexes.snapshot_age`` is an ``INTERVAL``
                          and ``audit.schema.json`` admits a string in a row cell.
    ``Decimal``         → ``str``, NOT ``float``. ``exposure_receipt.issued_hlc`` is a
                          ``NUMERIC`` the contract types as a string, and the audit
                          views aggregate into ``NUMERIC`` that a float would round.
                          A cell contract that admits both should get the exact one.
    ``bytes``           → lowercase hex. Every ``BYTES`` column in these contracts is
                          either a ``sha256_hex``/``hex`` or is base64'd explicitly at
                          its call site, so hex is the safe default and base64 is opt-in.
    ``set``/``frozenset``→ a sorted list, so two runs of the same read are byte-identical.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, _dt.datetime):
        return rfc3339(value)
    if isinstance(value, (_dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return [jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, Sequence):
        return [jsonable(item) for item in value]
    # Anything else is a driver type nobody anticipated. Rendering it as its repr would
    # put a Python object into a contract-governed payload; refusing names the column.
    raise EnvelopeError(f"no JSON rendering for {type(value).__name__}: {value!r}")


def dumps(payload: Any) -> str:
    """Serialise a payload for the wire: UTF-8 text, stable key order, compact.

    ``sort_keys`` is on so two invocations that read the same rows produce the same
    bytes. That is what lets W9's evidence bundle be diffed against a live response and
    W10's acceptance run assert on a digest rather than on a shape.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ── Provenance ──────────────────────────────────────────────────────────────────────


class Provenance:
    """An ordered, capped, duplicate-free list of ``{pointer, chip}``.

    Two behaviours are load-bearing.

    **The cap is silent, and deliberately so.** ``field_provenance`` allows 256 entries.
    A ``blocking_checks`` payload may carry 512 checks, so a per-item chip for every
    field is not representable. Rather than degrade to one coarse chip over the whole
    array — which would claim ``db:column`` for the ``open`` flag this API *computes* —
    entries are added in priority order and everything past the cap simply gets no chip.
    That is the contract's own instruction, quoted in this module's docstring.

    **A pointer is claimed once.** The first chip for a pointer wins, so a caller can
    add the precise claim (``derived`` for ``/checks/3/open``) before the sweeping one
    (``db:column`` for ``/checks/3``) and get the precise one.
    """

    __slots__ = ("_entries", "_seen", "dropped")

    def __init__(self) -> None:
        self._entries: list[dict[str, str]] = []
        self._seen: set[str] = set()
        #: How many pointers were offered past the cap. Not on the wire — there is no
        #: field for it — but read by the tests, which assert it is 0 for the fixtures.
        self.dropped = 0

    def add(self, pointer: str, chip: Chip) -> Provenance:
        """Claim *pointer* as *chip*. Returns self so calls can be chained."""
        if chip not in PROVENANCE_CHIPS:
            raise EnvelopeError(
                f"chip {chip!r} is not one of {sorted(PROVENANCE_CHIPS)}; "
                "common.schema.json#/$defs/provenance_chip is a closed enumeration"
            )
        if _POINTER.match(pointer) is None:
            raise EnvelopeError(
                f"provenance pointer {pointer!r} is not an RFC 6901 pointer into data"
            )
        if len(pointer) > 256:
            raise EnvelopeError(f"provenance pointer {pointer!r} exceeds the 256-character cap")
        if pointer in self._seen:
            return self
        if len(self._entries) >= PROVENANCE_CAP:
            self.dropped += 1
            return self
        self._seen.add(pointer)
        self._entries.append({"pointer": pointer, "chip": chip})
        return self

    def add_many(self, pointers: Iterable[str], chip: Chip) -> Provenance:
        """Claim every pointer in *pointers* as *chip*, in the order given."""
        for pointer in pointers:
            self.add(pointer, chip)
        return self

    def columns(self, prefix: str, names: Iterable[str]) -> Provenance:
        """Claim ``{prefix}/{name}`` as ``db:column`` for each name.

        The common case: a row of a table, rendered field for field. Note the escaping
        is NOT performed — every field name in these contracts is a SQL identifier, so
        none contains ``~`` or ``/``, and a pointer escape here would be dead code
        pretending to handle an input that cannot occur.
        """
        return self.add_many((f"{prefix}/{name}" for name in names), "db:column")

    def as_list(self) -> list[dict[str, str]]:
        """Return the wire form."""
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def statement_ref(
    kind: Literal["table", "view", "procedure", "statement"],
    obj: str,
    *,
    text: str | None = None,
    sql_path: str | None = None,
) -> dict[str, Any]:
    """One ``common.schema.json#/$defs/statement_ref``.

    ``text`` is the statement VERBATIM when we carry one and ``None`` when we decline —
    the contract distinguishes those, and this API declines for the long read statements
    rather than shipping a kilobyte of SQL beside a two-field answer.
    """
    if kind not in _STATEMENT_REF_KINDS:
        raise EnvelopeError(
            f"statement_ref kind {kind!r} is not one of {sorted(_STATEMENT_REF_KINDS)}"
        )
    if not obj or len(obj) > 256:
        raise EnvelopeError(f"statement_ref object {obj!r} must be 1..256 characters")
    ref: dict[str, Any] = {"kind": kind, "object": obj, "text": text}
    if sql_path is not None:
        ref["sql_path"] = sql_path
    return ref


# ── The envelope ────────────────────────────────────────────────────────────────────


def read_envelope(
    resource: str,
    data: Any,
    *,
    server_date: _dt.datetime,
    observed_at: _dt.datetime | None = None,
    staged: bool = False,
    staged_note: str | None = None,
    provenance: Provenance | None = None,
    statement_refs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one read envelope, or refuse to.

    :param server_date: **the DATABASE's clock**, from its own ``now()``, never this
        process's. The console subtracts it from ``Date.now()`` to render clock skew in
        the honesty chrome; a Lambda's clock would make that number a measurement of
        AWS's NTP rather than of the cluster the judge is being shown.
    :param observed_at: when this payload was produced. Defaults to *server_date*,
        because for a read served in one transaction those are the same instant and a
        second clock reading would imply a precision we do not have.

    Every refusal below is a violation of ``envelope.schema.json`` that is decidable
    without a validator. Catching them here rather than at the console means the failure
    names the emitting read function instead of arriving as a diff of two JSON blobs.
    """
    if _RESOURCE_KEY.match(resource) is None:
        raise EnvelopeError(f"resource key {resource!r} does not match ^[a-z][a-z0-9_]*$")
    schema_id = SCHEMA_IDS.get(resource)
    if schema_id is None:
        raise EnvelopeError(
            f"resource {resource!r} names no contract. Declared: {sorted(SCHEMA_IDS)}. "
            "The console refuses a payload naming a schema it does not hold, so emitting "
            "one would produce an unverifiable claim rather than a forward-compatible read."
        )
    if staged and not (isinstance(staged_note, str) and staged_note.strip()):
        raise EnvelopeError(
            f"resource {resource!r} is staged=true with no note. envelope.schema.json requires "
            "staged_note to be a non-empty string exactly when staged is true: an unexplained "
            "flag is a flag nobody has to justify."
        )
    if not staged and staged_note is not None:
        raise EnvelopeError(
            f"resource {resource!r} is staged=false but carries a staged_note. The contract's "
            "else-branch requires staged_note to be null; a note beside a false flag is a claim "
            "about data that has not been made."
        )
    if staged_note is not None and len(staged_note) > 1024:
        raise EnvelopeError(f"resource {resource!r}: staged_note exceeds the 1024-character cap")
    if len(statement_refs) > STATEMENT_REF_CAP:
        raise EnvelopeError(
            f"resource {resource!r}: {len(statement_refs)} statement_refs exceeds the cap of "
            f"{STATEMENT_REF_CAP}"
        )

    envelope: dict[str, Any] = {
        "envelope_version": ENVELOPE_VERSION,
        "resource": resource,
        "schema_id": schema_id,
        "observed_at": rfc3339(observed_at if observed_at is not None else server_date),
        "server_date": rfc3339(server_date),
        "staged": staged,
        "staged_note": staged_note,
        "provenance": (provenance or Provenance()).as_list(),
        "data": data,
    }
    if statement_refs:
        envelope["statement_refs"] = [dict(ref) for ref in statement_refs]
    return envelope
