# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The ``ccloud`` leg: one shim behind a Protocol, JSON parsed, a missing field fatal.

``ARCHITECTURE.md`` §9.3 fixes three rules and this module is all three, mechanically:

* **Every call routes through one shim.** The cloud lead owns ``cc()``; this package
  consumes it through :class:`CcloudShim` and never shells out to ``ccloud`` on its own
  except through :class:`SubprocessCcloud`, which is that same Protocol implemented here
  for the case where the shim has not landed yet.
* **Parse the JSON, never screen-scrape.** Every accessor goes through
  :func:`require_field`, and a missing field raises
  :class:`~mainline_steward.errors.CcloudFieldMissing` —
  *a silently renamed field is how a provisioning agent lies.*
* **Each page is canonicalised and hashed.** :class:`CcloudPage` carries the RFC 8785
  bytes and their SHA-256, so the custodian-patrol attestation commits to what the Cloud
  API said rather than to our summary of it.

**Honest constraints, unchanged.** Unattended ``ccloud`` authentication is undocumented:
``--no-redirect`` exists for headless login, and no API-key flag or environment variable
is published. So the subprocess shim is **opt-in** (``MAINLINE_STEWARD_CCLOUD_LIVE=1``),
the fixture shim is the default in CI and on any machine without the binary, and a run
that could reach neither refuses rather than reporting an empty custodian patrol. An
empty finding that looks like a clean one is the failure this whole package exists to
avoid.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_jcs import canonicalise

from .digest import sha256_hex
from .errors import CcloudFieldMissing, CcloudUnavailable, ConfigurationRefused

__all__ = [
    "AUDIT_LIST_FIXTURE",
    "BACKUP_LIST_FIXTURE",
    "CLUSTER_INFO_FIXTURE",
    "CcloudPage",
    "CcloudShim",
    "CustodianPatrol",
    "FixtureCcloud",
    "SubprocessCcloud",
    "require_field",
    "resolve_shim",
]

CLUSTER_INFO_FIXTURE: Final = "cluster-info.json"
BACKUP_LIST_FIXTURE: Final = "cluster-backup-list.json"
AUDIT_LIST_FIXTURE: Final = "audit-list.json"

_PROVIDER_ENV: Final = "MAINLINE_STEWARD_CCLOUD_PROVIDER"
_FIXTURES_ENV: Final = "MAINLINE_STEWARD_CCLOUD_FIXTURES"
_LIVE_ENV: Final = "MAINLINE_STEWARD_CCLOUD_LIVE"
_PROVISION_MODULE: Final = "mainline_provision"
_PROVISION_ATTRIBUTE: Final = "cc"
_SUBPROCESS_TIMEOUT_SECONDS: Final = 60.0


@runtime_checkable
class CcloudShim(Protocol):
    """The cloud lead's ``cc()``: an argv in, parsed JSON out, an exception on failure.

    Narrow on purpose. This package needs three read commands and holds no verb that
    creates, deletes, restores or scales anything — the Steward decides nothing that
    mutates ``mainline`` or ``mainline_meas`` (§8.4, agent 8), and a shim Protocol wide
    enough to express ``cluster delete`` would be a capability this package is not
    supposed to have.
    """

    def __call__(self, argv: Sequence[str]) -> Any:
        """Run one ``ccloud`` command with ``-o json`` and return the decoded document."""
        ...


@dataclass(frozen=True, slots=True)
class CcloudPage:
    """One ``ccloud`` response, canonicalised and hashed.

    ``canon_bytes`` is RFC 8785 over the *decoded* document, not the raw stdout: two
    ``ccloud`` builds that differ only in key order or whitespace must produce the same
    page digest, or the custodian patrol would report drift every time the CLI is
    upgraded and a reader would learn to ignore it.
    """

    command: str
    document: Any
    canon_bytes: bytes
    page_sha256: str
    source: str

    @classmethod
    def build(cls, command: str, document: Any, *, source: str) -> CcloudPage:
        """Canonicalise and hash a decoded ``ccloud`` document."""
        canon = canonicalise(document)
        return cls(
            command=command,
            document=document,
            canon_bytes=canon,
            page_sha256=sha256_hex(canon),
            source=source,
        )


def require_field(document: Any, field: str, *, command: str) -> Any:
    """Return ``document[field]``, or refuse naming what the response did carry.

    §9.3's rule, implemented once. Nothing in this module reaches into a ``ccloud``
    response with ``.get()`` — every read is this function, so "the field was absent"
    can never become "the value was empty".
    """
    if not isinstance(document, Mapping):
        raise CcloudFieldMissing(command, field, ())
    if field not in document:
        raise CcloudFieldMissing(command, field, tuple(str(k) for k in document))
    return document[field]


class FixtureCcloud:
    """A shim that answers from committed JSON fixtures. The default everywhere offline.

    The fixtures are real response shapes, recorded in
    ``tests/integration/steward/fixtures/ccloud/``. They exist so the custodian patrol's
    parsing, canonicalisation, hashing and refusal behaviour are all exercised on a
    machine with no CockroachDB Cloud organisation — which is every machine in this
    build (``VERIFY.md``).
    """

    def __init__(self, directory: Path) -> None:
        """Bind to a fixture directory, refusing immediately if it is not there."""
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

    def read(self, name: str, *, command: str) -> Any:
        """Load one fixture by file name."""
        path = self._directory / name
        if not path.is_file():
            raise CcloudUnavailable(f"{command}: no fixture at {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CcloudUnavailable(f"{command}: fixture {path} is not valid JSON: {exc}") from exc

    def __call__(self, argv: Sequence[str]) -> Any:
        """Answer an argv from the fixture whose name the verb maps to."""
        command = " ".join(["ccloud", *argv])
        name = _fixture_for(argv)
        return self.read(name, command=command)


def _fixture_for(argv: Sequence[str]) -> str:
    """Map an argv to its fixture file. Explicit table; no slug guessing."""
    verbs = tuple(token for token in argv if not token.startswith("-"))
    table = {
        ("cluster", "info"): CLUSTER_INFO_FIXTURE,
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


class SubprocessCcloud:
    """The real ``ccloud`` binary, ``-o json``, opt-in and time-bounded.

    Off unless ``MAINLINE_STEWARD_CCLOUD_LIVE=1``. Two reasons, both from §9.3: the
    unattended-auth path is undocumented, so a live call in CI would fail in a way that
    teaches nobody anything; and ``ccloud`` reaches a real Cloud organisation, which a
    test run is not a reason to touch.
    """

    def __init__(self, binary: str | None = None, *, timeout: float = _SUBPROCESS_TIMEOUT_SECONDS):
        """Locate ``ccloud`` on PATH, or refuse. No partial path is ever executed."""
        located = binary or shutil.which("ccloud")
        if not located:
            raise CcloudUnavailable(
                "`ccloud` is not on PATH. It is resolved to an absolute path before it is "
                "executed, so a directory earlier on PATH cannot substitute a binary"
            )
        self._binary = str(Path(located).resolve())
        self._timeout = timeout

    @property
    def binary(self) -> str:
        """The absolute path of the binary that will be executed."""
        return self._binary

    def __call__(self, argv: Sequence[str]) -> Any:
        """Run one command and decode its stdout as JSON."""
        command = " ".join([self._binary, *argv])
        # S603: the argv is built by this module from typed methods, never from a model
        # and never from a caller-supplied string; the binary is an absolute path resolved
        # once in __init__; `shell` is left False so no token is ever re-parsed by a shell.
        completed = subprocess.run(  # noqa: S603
            [self._binary, *argv, "-o", "json"],
            capture_output=True,
            text=True,
            timeout=self._timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise CcloudUnavailable(
                f"{command} exited {completed.returncode}: {completed.stderr.strip()[:400]}"
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CcloudUnavailable(
                f"{command} produced output that is not JSON. We parse the JSON and never "
                f"screen-scrape, so unparseable output is a failure: {exc}"
            ) from exc


def _provider_from_environment() -> tuple[CcloudShim, str] | None:
    spec = os.environ.get(_PROVIDER_ENV, "").strip()
    if not spec:
        return None
    if ":" not in spec:
        raise ConfigurationRefused(f"{_PROVIDER_ENV}={spec!r} must be 'module:attribute'")
    module_name, _, attribute = spec.partition(":")
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise ConfigurationRefused(f"{_PROVIDER_ENV}={spec!r}: {exc}") from exc
    shim = getattr(module, attribute, None)
    if not callable(shim):
        raise ConfigurationRefused(f"{_PROVIDER_ENV}={spec!r}: {attribute!r} is not callable")
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

    Order, and each step is a named place rather than a search: an explicitly passed
    shim, then ``MAINLINE_STEWARD_CCLOUD_PROVIDER``, then ``mainline_provision.cc``, then
    the live binary if ``MAINLINE_STEWARD_CCLOUD_LIVE=1``, then a fixture directory.

    Returns:
        ``(shim, source)`` where ``source`` is written into the attestation, so a reader
        can tell a live custodian patrol from a fixture one without reading our code.

    Raises:
        CcloudUnavailable: nothing could be resolved. The run refuses rather than
            emitting a patrol with no pages in it.
    """
    if explicit is not None:
        return explicit, "explicit"
    resolved = _provider_from_environment() or _provider_from_provision_package()
    if resolved is not None:
        return resolved
    if os.environ.get(_LIVE_ENV) == "1":
        return SubprocessCcloud(), "subprocess:ccloud"
    directory = fixtures or (
        Path(os.environ[_FIXTURES_ENV]) if os.environ.get(_FIXTURES_ENV) else None
    )
    if directory is not None:
        return FixtureCcloud(directory), f"fixtures:{directory}"
    raise CcloudUnavailable(
        "no ccloud shim: set MAINLINE_STEWARD_CCLOUD_PROVIDER to the cloud lead's cc(), or "
        f"{_LIVE_ENV}=1 to use the binary, or {_FIXTURES_ENV} to a fixture directory. "
        "There is deliberately no silent default — an unrun custodian patrol must not be "
        "reportable as a clean one"
    )


class CustodianPatrol:
    """§8.6 I4's three reads, typed, with every field access mandatory.

    The authoritative ``custodian_attestation`` ledger row is written by the custody
    domain's Lambda, which holds a pgwire identity this package deliberately does not.
    What the Steward contributes is a *second, independently-identified* observation of
    the same three pages, committed through a different write path
    (``insert_rows`` on ``mainline_meas.external_attestation``). Two observers with
    different credentials is the point of I4: any ``DROP TRIGGER`` by a cluster admin has
    to survive in a stream the admin does not control, and one stream is one thing to
    compromise.
    """

    def __init__(self, shim: CcloudShim, *, cluster_id: str) -> None:
        """Bind a shim and the cluster whose custody is being observed."""
        if not cluster_id:
            raise ConfigurationRefused("the custodian patrol needs a cluster id")
        self._shim = shim
        self._cluster_id = cluster_id

    def cluster_info(self) -> CcloudPage:
        """``ccloud cluster info`` — the cluster's own description of itself."""
        argv = ["cluster", "info", self._cluster_id]
        command = "ccloud " + " ".join(argv)
        document = self._shim(argv)
        for field in ("id", "name", "state"):
            require_field(document, field, command=command)
        return CcloudPage.build(command, document, source="cluster_info")

    def backup_list(self) -> CcloudPage:
        """``ccloud cluster backup list`` — a restore nobody can point at is not a backup."""
        argv = ["cluster", "backup", "list", self._cluster_id]
        command = "ccloud " + " ".join(argv)
        document = self._shim(argv)
        require_field(document, "backups", command=command)
        return CcloudPage.build(command, document, source="backup_list")

    def audit_list(self, starting_from: str) -> CcloudPage:
        """``ccloud audit list --starting-from <ts>`` — the record an admin does not author."""
        if not starting_from:
            raise ConfigurationRefused(
                "audit_list needs an explicit --starting-from; an unbounded audit read is "
                "both a paging hazard and an unanswerable question about coverage"
            )
        argv = ["audit", "list", "--starting-from", starting_from]
        command = "ccloud " + " ".join(argv)
        document = self._shim(argv)
        require_field(document, "entries", command=command)
        return CcloudPage.build(command, document, source="audit_list")

    def run(self, *, starting_from: str) -> tuple[CcloudPage, ...]:
        """Run all three reads, in I4's order."""
        return (self.cluster_info(), self.backup_list(), self.audit_list(starting_from))
