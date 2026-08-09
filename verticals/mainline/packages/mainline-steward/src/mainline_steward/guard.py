# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The occurrence guard: at-least-once delivery, made survivable and named as such.

EventBridge Scheduler delivers at least once (§8.5), so a Steward task will sometimes be
started twice for one ``(schedule_id, occurrence_ts)``. This module holds the guard that
makes the second start a deliberate no-op.

**What the guard is, precisely.** A durable set of occurrence keys, consulted before the
reads and written after the attestation is accepted. The default implementation is a
file per key under a directory the task mounts; a deployment that wants a stronger
store implements :class:`OccurrenceStore` over one.

**What the guard is not.** It is not exactly-once, and this module does not pretend
otherwise. Three gaps, all of them structural rather than fixable here:

* A task that dies between the write and the guard record will re-run its occurrence and
  produce a second attestation. That is the correct side to fail on — a missing review is
  worse than a duplicated one.
* Two tasks racing for the same occurrence on a directory with no atomic create would
  both proceed. :class:`FileOccurrenceStore` uses ``O_EXCL`` creation, which is atomic on
  POSIX and on Windows, so the race is closed *within one filesystem*; it is not closed
  across two tasks with two different volumes.
* The writing identity (``mainline_auditor``) holds ``INSERT`` on
  ``mainline_meas.external_attestation`` and no ``SELECT`` anywhere, so this package
  cannot ask the database whether the occurrence was already attested. The durable answer
  would be a ``UNIQUE (attestor, subject_kind, subject_ref)`` on that table, which is the
  data-model lead's to add.

Because none of the three is hidden, the occurrence key is carried inside the
attestation's ``subject_ref`` as well: a duplicate is always identifiable and collapsible
by a reader with no access to this guard at all.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from .digest import sha256_hex
from .errors import OccurrenceAlreadyAttested

__all__ = [
    "FileOccurrenceStore",
    "MemoryOccurrenceStore",
    "OccurrenceGuard",
    "OccurrenceStore",
]


@runtime_checkable
class OccurrenceStore(Protocol):
    """A durable set of occurrence keys with an atomic "claim if absent" operation."""

    def claim(self, key: str) -> bool:
        """Record ``key`` and return ``True``, or return ``False`` if it was already there."""
        ...

    def contains(self, key: str) -> bool:
        """Whether ``key`` has been recorded."""
        ...

    def release(self, key: str) -> None:
        """Remove ``key``, so a failed run's occurrence can be re-attempted."""
        ...


class MemoryOccurrenceStore:
    """An in-process store. Correct for one process, useless across restarts — by design.

    The default when no state directory is configured, because the honest failure of an
    unconfigured guard is "it deduplicates within this task and nothing else", not "it
    silently pretends to be durable".
    """

    def __init__(self) -> None:
        """Start empty."""
        self._keys: set[str] = set()

    def claim(self, key: str) -> bool:
        """Add ``key`` if absent."""
        if key in self._keys:
            return False
        self._keys.add(key)
        return True

    def contains(self, key: str) -> bool:
        """Whether ``key`` is present."""
        return key in self._keys

    def release(self, key: str) -> None:
        """Discard ``key``."""
        self._keys.discard(key)


class FileOccurrenceStore:
    """One file per occurrence key, created with ``O_EXCL`` so the claim is atomic.

    The key is hashed into the file name rather than used raw: an occurrence key contains
    a colon and, on some filesystems, that is not a legal name. The unhashed key is
    written into the file so a human listing the directory can still read what is there.
    """

    def __init__(self, directory: Path) -> None:
        """Create the state directory if it does not exist."""
        directory.mkdir(parents=True, exist_ok=True)
        self._directory = directory

    @property
    def directory(self) -> Path:
        """Where the claims are kept."""
        return self._directory

    def _path(self, key: str) -> Path:
        return self._directory / f"{sha256_hex(key.encode('utf-8'))}.claim"

    def claim(self, key: str) -> bool:
        """Atomically create the claim file, returning ``False`` if it already existed."""
        path = self._path(key)
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(key)
        return True

    def contains(self, key: str) -> bool:
        """Whether the claim file exists."""
        return self._path(key).is_file()

    def release(self, key: str) -> None:
        """Delete the claim file, if it is there."""
        self._path(key).unlink(missing_ok=True)


class OccurrenceGuard:
    """Claims an occurrence before a run and releases it if the run does not attest."""

    def __init__(self, store: OccurrenceStore) -> None:
        """Bind a store."""
        self._store = store

    @classmethod
    def for_directory(cls, directory: Path | None) -> OccurrenceGuard:
        """Build a file-backed guard, or an in-process one when no directory is given."""
        if directory is None:
            return cls(MemoryOccurrenceStore())
        return cls(FileOccurrenceStore(directory))

    def claim(self, key: str) -> None:
        """Claim ``key`` or refuse.

        Raises:
            OccurrenceAlreadyAttested: this occurrence has already produced an
                attestation. The caller — the CLI — catches this by name and exits 0,
                because a redelivery that does nothing is the *correct* behaviour of an
                at-least-once schedule and must not page anybody.
        """
        if not self._store.claim(key):
            raise OccurrenceAlreadyAttested(
                f"{key} has already been attested. EventBridge Scheduler is at-least-once, "
                "so this is an expected redelivery and not a fault"
            )

    def release(self, key: str) -> None:
        """Give the claim back, so a run that failed before attesting can be retried."""
        self._store.release(key)

    def holds(self, key: str) -> bool:
        """Whether ``key`` has been claimed."""
        return self._store.contains(key)
