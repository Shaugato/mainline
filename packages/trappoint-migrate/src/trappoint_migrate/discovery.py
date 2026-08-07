# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Finding migration files, ordering them, and hashing them.

Two rules from ARCHITECTURE.md §18 and kernel ruling D7, and neither is negotiable:

**One DDL statement per file.** The runner does not wrap a migration body in a
transaction — CockroachDB DDL inside a multi-statement transaction can fail at COMMIT
even when every statement succeeded — so a multi-statement file is not atomic and a
failure leaves a half-applied file that nobody can diagnose. One statement makes
``dirty`` answerable in seconds.

**Lexicographic ordering on the FULL filename.** A slot that needs more than one
statement takes a lowercase letter suffix (``0071a_merge_record.sql``,
``0071b_epoch_pin_permit.sql``), and ``0071a`` sorting before ``0071b`` is the whole
mechanism. Sorting on a parsed integer version would make those two collide.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import MigrationTreeInvalid, UsageError
from .sqltext import header_comment, strip_sql_comments

__all__ = [
    "MIGRATION_SUFFIXES",
    "MigrationFile",
    "discover",
    "statement_count",
]

# `.up.sql` is accepted because the repository already carries files written in that
# convention. There are no down migrations and there will not be: append-only means
# append-only, and a `.down.sql` file is refused loudly rather than ignored quietly.
MIGRATION_SUFFIXES: tuple[str, ...] = (".sql", ".up.sql")

_DOWN_SUFFIX = ".down.sql"
_VERSION_RE = re.compile(r"^(?P<num>\d{4})(?P<letter>[a-z]*)_(?P<slug>[a-z0-9_]+)$")
_INVARIANT_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")


@dataclass(frozen=True, slots=True)
class MigrationFile:
    """One migration: one statement, one file, one SHA-256."""

    path: Path
    version: str
    """The full filename stem with any suffix chain removed, e.g. ``0071a_merge_record``.

    This is what ``trappoint.schema_migration.version`` stores and what ``force`` names.
    It is the ordering key, so it is the *whole* stem: ``0071a`` and ``0071b`` are two
    versions, not two parts of one.
    """
    sql: str
    sha256: bytes

    @property
    def sort_key(self) -> str:
        """Ordering key: the version stem, compared as text.

        Text comparison is deliberate. ``0071a`` < ``0071b`` < ``0072`` holds because
        the numeric part is zero-padded to four digits everywhere in §18, and text
        comparison is the only rule under which a letter suffix means what D7 says it
        means.
        """
        return self.version

    @property
    def cited_invariants(self) -> tuple[str, ...]:
        """Invariant identifiers cited in the file's header comment block, in order."""
        return tuple(_INVARIANT_CITATION.findall(header_comment(self.sql)))


def _version_of(path: Path) -> str:
    name = path.name
    for suffix in sorted(MIGRATION_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def discover(root: Path) -> list[MigrationFile]:
    """Return every migration under *root*, ordered lexicographically by version.

    An empty or absent directory yields an empty list rather than an error: a binding
    whose SQL has not been rendered yet is a normal state on the way to K1, and
    ``trappoint migrate up`` against it is a legitimate no-op.

    Raises:
        MigrationTreeInvalid: on a ``.down.sql`` file, on a filename that does not match
            the ``NNNN[a-z]*_slug`` shape, or on two files claiming the same version.
    """
    if not root.exists():
        return []
    if not root.is_dir():
        raise UsageError(f"{root} is not a directory")

    found: dict[str, MigrationFile] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if path.name.endswith(_DOWN_SUFFIX):
            raise MigrationTreeInvalid(
                f"{path} is a down migration. This runner is forward-only by design: "
                "the ledger tables below the protected floor cannot be un-applied, and "
                "a down migration that only works above the floor is a trap."
            )
        if not any(path.name.endswith(s) for s in MIGRATION_SUFFIXES):
            continue

        version = _version_of(path)
        if _VERSION_RE.match(version) is None:
            raise MigrationTreeInvalid(
                f"{path.name} does not match NNNN[a-z]*_lower_snake_slug. Ordering is "
                "lexicographic on the whole stem (ruling D7), so a filename that does "
                "not carry a zero-padded four-digit number has no defined position."
            )
        if version in found:
            raise MigrationTreeInvalid(
                f"two files claim version {version!r}: {found[version].path.name} and {path.name}"
            )
        sql = path.read_text(encoding="utf-8")
        found[version] = MigrationFile(
            path=path,
            version=version,
            sql=sql,
            sha256=hashlib.sha256(sql.encode("utf-8")).digest(),
        )

    return sorted(found.values(), key=lambda m: m.sort_key)


def statement_count(sql: str) -> int:
    """Count top-level statements in *sql*, ignoring comments and quoted regions.

    Used by the lint to enforce one statement per file. Semicolons inside a
    dollar-quoted PL/pgSQL body are not statement terminators, which is why this counts
    over the lexed text rather than over ``sql.split(";")``.
    """
    stripped = strip_sql_comments(sql)
    depth_safe = _mask_quoted(stripped)
    parts = [part for part in depth_safe.split(";") if part.strip()]
    return len(parts)


def _mask_quoted(sql: str) -> str:
    """Replace the contents of quoted regions with spaces, preserving length.

    Only the semicolon-hiding property matters here, so the cheapest correct thing is to
    blank the interiors and leave the delimiters.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "$":
            match = re.compile(r"\$(?:[A-Za-z_]\w*)?\$").match(sql, i)
            if match is not None:
                tag = match.group(0)
                close = sql.find(tag, match.end())
                end = n if close == -1 else close + len(tag)
                out.append(" " * (end - i))
                i = end
                continue
        if ch in "'\"":
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            out.append(" " * (j - i))
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)
