# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The ``ccloud`` leg of the custodian patrol: pages in, one folded document out.

``ARCHITECTURE.md`` §9.3 fixes three rules and this module is all three, mechanically.

**One shim.** The cloud lead owns ``cc()``. This package consumes it through
:class:`CcloudShim` and never invokes the binary itself — there is deliberately no
subprocess implementation here, because a second invoker of ``ccloud`` is a second
place for the undocumented unattended-auth story (GT-21) to be got wrong.

**Parse the JSON, never screen-scrape, and a missing field is fatal.** Every read goes
through :func:`require_field` or :func:`require_sequence`; nothing in this module uses
``.get()`` on a ``ccloud`` response. *A silently renamed field is how a provisioning
agent lies*, and a renamed field that degrades to a default produces an attestation
that says "zero audit events" when it means "I could not find the audit events".

**Pagination is refused rather than guessed.** GT-21 leaves the cursor flag unresolved
— ``--starting-from`` is documented, the *next-page* argument is not — so a response
carrying a non-null cursor makes :func:`audit_list` and :func:`backup_list` **refuse**
unless the caller supplies :class:`PageCursor`. Attesting page 1 of *n* as though it
were the window is an omission, and non-omission is the proposition plaintiffs
actually attack (``docs/leads/custody.md`` §0). The day GT-21 is answered, one
``PageCursor`` at the call site turns paging on; nothing here has to change.

**Canonicalisation, twice, for two different purposes.** The folded document goes to
Object Lock through :func:`trappoint_jcs.canonicalise` — RFC 8785 *in full*, floats
included, because CockroachDB Cloud authored those bytes and we do not get to impose a
profile on them. The ledger *leaf* built in :mod:`~mainline_custody_patrol.collect`
carries only the digest and metadata and is canonicalised with
``canonicalise_payload``, which refuses floats (CU-5). No IEEE-754 float ever enters a
leaf; every byte of the foreign document is still committed to, exactly as received.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_jcs import canonicalise

__all__ = [
    "AUDIT_LIST_FIXTURE",
    "BACKUP_LIST_FIXTURE",
    "DEFAULT_CURSOR_FIELD",
    "DEFAULT_PAGE_LIMIT",
    "DEFAULT_PAGINATION_FIELD",
    "CcloudFieldMissing",
    "CcloudFold",
    "CcloudPage",
    "CcloudPaginationUnresolved",
    "CcloudShim",
    "CcloudUnavailable",
    "FixtureCcloud",
    "PageCursor",
    "audit_list",
    "backup_list",
    "require_field",
    "require_sequence",
    "resolve_shim",
    "rfc3339",
]

#: Fixture file names. An explicit table, not a slug guess: an unmapped command is a
#: refusal rather than a quietly wrong file.
AUDIT_LIST_FIXTURE: Final = "audit-list.json"
BACKUP_LIST_FIXTURE: Final = "cluster-backup-list.json"

#: The response members the fold reads. Named constants because GT-21 lists *field
#: names* as a day-1 output: when the real names land, they land here and in the
#: fixtures, and every call site is already parameterised.
DEFAULT_PAGINATION_FIELD: Final = "pagination"
DEFAULT_CURSOR_FIELD: Final = "next_page"

#: A hard ceiling on pages followed in one fold. A cursor loop that never terminates
#: is a Lambda that never terminates, and a patrol that hangs reports nothing at all.
DEFAULT_PAGE_LIMIT: Final = 64

_PROVIDER_ENV: Final = "MAINLINE_CUSTODY_CCLOUD_PROVIDER"
_FIXTURES_ENV: Final = "MAINLINE_CUSTODY_CCLOUD_FIXTURES"
_PROVISION_MODULE: Final = "mainline_provision"
_PROVISION_ATTRIBUTE: Final = "cc"

#: Written into every folded document so a reader can tell which build produced it.
COLLECTOR_ID: Final = "mainline-custody-patrol/0.1.0"


class CcloudUnavailable(RuntimeError):
    """No ``ccloud`` shim could be resolved, or the shim itself failed.

    Raised rather than returning an empty page. An unrun custodian patrol must never be
    indistinguishable from a clean one.
    """


class CcloudFieldMissing(RuntimeError):
    """A ``ccloud`` response did not carry a field the fold requires.

    The message names the command, the missing field and **what the response did
    carry**, because the realistic cause is a renamed field in a new CLI build and the
    new name is the one piece of information the operator needs.
    """

    def __init__(self, command: str, field: str, present: Sequence[str]) -> None:
        """Build the refusal message from the command, the field and what was present."""
        self.command = command
        self.field = field
        self.present = tuple(present)
        listed = ", ".join(self.present) if self.present else "(no members at all)"
        super().__init__(
            f"`{command}` returned no `{field}` member. Present members: {listed}. "
            "A missing field is a hard failure here and is never defaulted: a silently "
            "renamed field would otherwise turn 'I could not find the records' into "
            "'there were no records', which is the one mistake an attestation may not make."
        )


class CcloudPaginationUnresolved(RuntimeError):
    """The response carried a next-page cursor and no :class:`PageCursor` was supplied.

    GT-21 (``ARCHITECTURE.md`` §19) records the ``ccloud`` cursor argument as an
    unresolved day-1 output. Guessing a flag name would produce a silently truncated
    window; attesting the first page as if it were the whole window would produce an
    omission. So the fold refuses, and the refusal names the cursor it saw.
    """


@runtime_checkable
class CcloudShim(Protocol):
    """The cloud lead's ``cc()``: an argv in, decoded JSON out, an exception on failure.

    Narrow on purpose. This patrol needs two read commands and holds no verb that
    creates, deletes, restores or scales anything. A Protocol wide enough to express
    ``cluster delete`` would be a capability the custodian patrol has no business
    holding, and Protocol width is the only place that capability is bounded — the
    process credential is the cloud lead's to scope.

    The implementation is responsible for appending ``-o json``; every documented
    ``ccloud`` verb accepts the global flag, and putting it in the argv here would
    double it when the shim adds its own.
    """

    def __call__(self, argv: Sequence[str]) -> Any:
        """Run one ``ccloud`` command and return the decoded document."""
        ...


@dataclass(frozen=True, slots=True)
class PageCursor:
    """How to ask for the next page, once GT-21 is answered.

    Attributes:
        argv_for: builds the *extra* argv tokens for a cursor value, e.g.
            ``lambda token: ("--page-token", token)``. Supplied by the caller because
            this repository does not hard-code a guess at an undocumented flag.
        pagination_field: the response member holding the pagination object.
        cursor_field: the member inside it holding the next cursor, or ``null``.
        limit: maximum pages followed in one fold.
    """

    argv_for: Callable[[str], Sequence[str]]
    pagination_field: str = DEFAULT_PAGINATION_FIELD
    cursor_field: str = DEFAULT_CURSOR_FIELD
    limit: int = DEFAULT_PAGE_LIMIT


@dataclass(frozen=True, slots=True)
class CcloudPage:
    """One ``ccloud`` response, canonicalised and hashed.

    ``canon_bytes`` is RFC 8785 over the *decoded* document, never over raw stdout: two
    ``ccloud`` builds that differ only in key order or whitespace must produce the same
    page digest, or the patrol reports drift on every CLI upgrade and a reader learns to
    ignore it.
    """

    ordinal: int
    command: str
    document: Any
    canon_bytes: bytes
    page_sha256: str

    @classmethod
    def build(cls, ordinal: int, command: str, document: Any) -> CcloudPage:
        """Canonicalise and hash one decoded ``ccloud`` document."""
        canon = canonicalise(document)
        return cls(
            ordinal=ordinal,
            command=command,
            document=document,
            canon_bytes=canon,
            page_sha256=hashlib.sha256(canon).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class CcloudFold:
    """Every page of one ``ccloud`` read, folded into a single evidentiary document.

    This is what goes to Object Lock. ``sha256`` is what goes into
    ``mainline.custodian_attestation.payload_sha256`` and, through the leaf, into the
    Merkle tree.
    """

    kind: str
    command: str
    window_from: datetime
    window_to: datetime
    pages: tuple[CcloudPage, ...]
    document: dict[str, Any]
    canon_bytes: bytes
    sha256: bytes
    row_count: int

    @property
    def sha256_hex(self) -> str:
        """The payload digest as lowercase hex, the form the ledger leaf carries."""
        return self.sha256.hex()


def rfc3339(moment: datetime) -> str:
    """Format *moment* as RFC 3339 UTC with a literal ``Z`` and no sub-second part.

    Windows are minute-grained and a fold's document is hashed, so a representation
    that varies with the platform's microsecond resolution would make two collections
    of the same window hash differently for no reason a reader could see.

    Raises:
        ValueError: if *moment* is naive. A naive datetime in an evidentiary payload is
            an unanswerable question in cross-examination.
    """
    if moment.tzinfo is None:
        raise ValueError(
            "a naive datetime cannot enter an attestation window: the offset is the "
            "difference between a time and a guess about a time"
        )
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def require_field(document: Any, field: str, *, command: str) -> Any:
    """Return ``document[field]``, or refuse naming what the response did carry."""
    if not isinstance(document, Mapping):
        raise CcloudFieldMissing(command, field, ())
    if field not in document:
        raise CcloudFieldMissing(command, field, tuple(str(key) for key in document))
    return document[field]


def require_sequence(document: Any, field: str, *, command: str) -> list[Any]:
    """Return ``document[field]`` after asserting it is a JSON array.

    A scalar where an array was expected is the same class of failure as an absent
    member — the response changed shape — and it is reported the same way rather than
    being coerced into a one-element list.
    """
    value = require_field(document, field, command=command)
    if not isinstance(value, list):
        raise CcloudFieldMissing(
            command,
            f"{field} (as a JSON array)",
            (f"{field}: {type(value).__name__}",),
        )
    return value


class FixtureCcloud:
    """A shim that answers from committed JSON. The default on every offline machine.

    The fixtures are real response *shapes*. They exist so that the parsing, the
    canonicalisation, the hashing, the pagination refusal and the missing-field refusal
    are all exercised on a machine with no CockroachDB Cloud organisation — which is
    every machine in this build (``VERIFY.md``).
    """

    def __init__(self, directory: Path) -> None:
        """Bind a fixture directory, refusing immediately if it is not there."""
        if not directory.is_dir():
            raise CcloudUnavailable(
                f"no ccloud fixture directory at {directory}. The fixture shim is the only "
                "path available without a Cloud organisation, and inventing an empty "
                "response would make an unrun patrol look like a clean one"
            )
        self._directory = directory

    @property
    def directory(self) -> Path:
        """The fixture directory in use."""
        return self._directory

    def __call__(self, argv: Sequence[str]) -> Any:
        """Answer an argv from the fixture its verb prefix maps to."""
        command = " ".join(["ccloud", *argv])
        return self.read(_fixture_for(argv), command=command)

    def read(self, name: str, *, command: str) -> Any:
        """Load one fixture by file name."""
        path = self._directory / name
        if not path.is_file():
            raise CcloudUnavailable(f"{command}: no fixture at {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CcloudUnavailable(f"{command}: fixture {path} is not valid JSON: {exc}") from exc


def _fixture_for(argv: Sequence[str]) -> str:
    """Map an argv to its fixture file. Explicit table; no slug guessing."""
    verbs = tuple(token for token in argv if not token.startswith("-"))
    table = {
        ("cluster", "backup", "list"): BACKUP_LIST_FIXTURE,
        ("audit", "list"): AUDIT_LIST_FIXTURE,
    }
    for prefix, name in table.items():
        if verbs[: len(prefix)] == prefix:
            return name
    raise CcloudUnavailable(
        f"no fixture is mapped for `ccloud {' '.join(argv)}`. The map is explicit so an "
        "unmapped command is a refusal rather than a quietly wrong file"
    )


def _provider_from_environment() -> tuple[CcloudShim, str] | None:
    spec = os.environ.get(_PROVIDER_ENV, "").strip()
    if not spec:
        return None
    if ":" not in spec:
        raise CcloudUnavailable(f"{_PROVIDER_ENV}={spec!r} must be 'module:attribute'")
    module_name, _, attribute = spec.partition(":")
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise CcloudUnavailable(f"{_PROVIDER_ENV}={spec!r}: {exc}") from exc
    shim = getattr(module, attribute, None)
    if not callable(shim):
        raise CcloudUnavailable(f"{_PROVIDER_ENV}={spec!r}: {attribute!r} is not callable")
    typed: CcloudShim = shim
    return typed, spec


def _provider_from_provision_package() -> tuple[CcloudShim, str] | None:
    """Use ``mainline_provision.cc`` when the cloud lead's package is installed."""
    try:
        module = import_module(_PROVISION_MODULE)
    except ImportError:
        return None
    shim = getattr(module, _PROVISION_ATTRIBUTE, None)
    if not callable(shim):
        return None
    typed: CcloudShim = shim
    return typed, f"{_PROVISION_MODULE}:{_PROVISION_ATTRIBUTE}"


def resolve_shim(
    *,
    explicit: CcloudShim | None = None,
    fixtures: Path | None = None,
) -> tuple[CcloudShim, str]:
    """Resolve the shim and name where it came from.

    Order, and every step is a named place rather than a search: an explicitly passed
    shim, then ``MAINLINE_CUSTODY_CCLOUD_PROVIDER``, then ``mainline_provision.cc``,
    then a fixture directory.

    There is no subprocess step. This package does not run ``ccloud``; the cloud lead's
    ``cc()`` does, and consuming it means the undocumented unattended-auth path
    (``ARCHITECTURE.md`` §9.3, GT-21) has exactly one implementation to get right.

    Returns:
        ``(shim, source)``. ``source`` is written into the folded document, so a reader
        can tell a live patrol from a fixture one without reading our code — which is
        the difference between evidence and a screenshot.

    Raises:
        CcloudUnavailable: nothing could be resolved. There is deliberately no silent
            default.
    """
    if explicit is not None:
        return explicit, "explicit"
    resolved = _provider_from_environment() or _provider_from_provision_package()
    if resolved is not None:
        return resolved
    directory = fixtures or (
        Path(os.environ[_FIXTURES_ENV]) if os.environ.get(_FIXTURES_ENV) else None
    )
    if directory is not None:
        return FixtureCcloud(directory), f"fixtures:{directory}"
    raise CcloudUnavailable(
        f"no ccloud shim: set {_PROVIDER_ENV} to the cloud lead's cc(), or "
        f"{_FIXTURES_ENV} to a fixture directory, or pass one explicitly. There is "
        "deliberately no silent default — an unrun custodian patrol must not be "
        "reportable as a clean one"
    )


def _collect_pages(
    shim: CcloudShim,
    base_argv: Sequence[str],
    *,
    row_field: str,
    cursor: PageCursor | None,
) -> tuple[tuple[CcloudPage, ...], int]:
    """Read one or more pages, refusing to invent either a cursor flag or an ending."""
    pagination_field = cursor.pagination_field if cursor else DEFAULT_PAGINATION_FIELD
    cursor_field = cursor.cursor_field if cursor else DEFAULT_CURSOR_FIELD
    limit = cursor.limit if cursor else 1

    pages: list[CcloudPage] = []
    rows = 0
    argv = list(base_argv)
    for ordinal in range(max(limit, 1)):
        command = "ccloud " + " ".join(argv)
        document = shim(argv)
        rows += len(require_sequence(document, row_field, command=command))
        pages.append(CcloudPage.build(ordinal, command, document))

        pagination = require_field(document, pagination_field, command=command)
        token = require_field(pagination, cursor_field, command=command)
        if token is None:
            return tuple(pages), rows
        if cursor is None:
            raise CcloudPaginationUnresolved(
                f"`{command}` returned a non-null `{pagination_field}.{cursor_field}` "
                f"({token!r}) and no PageCursor was supplied. The ccloud next-page "
                "argument is an unresolved day-1 output (GT-21) and this repository does "
                "not hard-code a guess at an undocumented flag. Attesting the first page "
                "as though it were the whole window would be an omission, and non-omission "
                "is the proposition this ledger exists to defend — so the collection "
                "refuses instead."
            )
        argv = [*base_argv, *cursor.argv_for(str(token))]

    raise CcloudPaginationUnresolved(
        f"`ccloud {' '.join(base_argv)}` was still returning a next-page cursor after "
        f"{limit} pages. The fold stops rather than paging without bound: a patrol that "
        "does not finish reports nothing, which is worse than a patrol that refuses."
    )


def _fold(
    *,
    kind: str,
    pages: tuple[CcloudPage, ...],
    row_count: int,
    window_from: datetime,
    window_to: datetime,
    source: str,
    row_field: str,
) -> CcloudFold:
    document: dict[str, Any] = {
        "attestation_kind": kind,
        "collector": COLLECTOR_ID,
        "shim_source": source,
        "row_field": row_field,
        "command": pages[0].command,
        "window_from": rfc3339(window_from),
        "window_to": rfc3339(window_to),
        "page_count": len(pages),
        "row_count": row_count,
        "pages": [
            {
                "ordinal": page.ordinal,
                "command": page.command,
                "page_sha256": page.page_sha256,
                "document": page.document,
            }
            for page in pages
        ],
    }
    canon = canonicalise(document)
    return CcloudFold(
        kind=kind,
        command=pages[0].command,
        window_from=window_from,
        window_to=window_to,
        pages=pages,
        document=document,
        canon_bytes=canon,
        sha256=hashlib.sha256(canon).digest(),
        row_count=row_count,
    )


def audit_list(
    shim: CcloudShim,
    *,
    starting_from: datetime,
    window_to: datetime,
    source: str = "unknown",
    cursor: PageCursor | None = None,
) -> CcloudFold:
    """``ccloud audit list --starting-from <ts>`` — the record an admin does not author.

    This is the load-bearing one. Any ``DROP TRIGGER`` or
    ``ALTER TABLE … DISABLE TRIGGER`` performed by a cluster admin (threat tier T1)
    appears in the CockroachDB Cloud audit stream, which that admin does not control;
    folding the stream into the ledger every fifteen minutes is what makes the
    disappearance of a gate visible to someone other than the person who did it
    (``ARCHITECTURE.md`` §8.6 I4, attack A13).

    Raises:
        CcloudFieldMissing: the response lacks ``entries`` or ``pagination.next_page``.
        CcloudPaginationUnresolved: the window did not fit in the pages we can ask for.
    """
    if window_to < starting_from:
        raise ValueError(
            f"the audit window ends before it starts ({rfc3339(window_to)} < "
            f"{rfc3339(starting_from)}); `window_ordered` on mainline.custodian_attestation "
            "would refuse the row anyway, and refusing here names the caller instead"
        )
    argv = ["audit", "list", "--starting-from", rfc3339(starting_from)]
    pages, rows = _collect_pages(shim, argv, row_field="entries", cursor=cursor)
    return _fold(
        kind="ccloud_audit",
        pages=pages,
        row_count=rows,
        window_from=starting_from,
        window_to=window_to,
        source=source,
        row_field="entries",
    )


def backup_list(
    shim: CcloudShim,
    *,
    cluster_id: str,
    at: datetime,
    source: str = "unknown",
    cursor: PageCursor | None = None,
) -> CcloudFold:
    """``ccloud cluster backup list`` — a restore nobody can point at is not a backup.

    Snapshot-shaped, so the attestation window is a point: ``window_from == window_to``,
    which ``window_ordered`` on ``mainline.custodian_attestation`` admits deliberately
    (migration 0078). Inventing an end time for a statement about an instant is exactly
    the invented value that band refuses everywhere else.
    """
    if not cluster_id:
        raise ValueError("backup_list needs the cluster id whose backups are being attested")
    argv = ["cluster", "backup", "list", cluster_id]
    pages, rows = _collect_pages(shim, argv, row_field="backups", cursor=cursor)
    return _fold(
        kind="ccloud_backup",
        pages=pages,
        row_count=rows,
        window_from=at,
        window_to=at,
        source=source,
        row_field="backups",
    )
