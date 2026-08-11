# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The one migration-ID parser: MR-5 keys, ordered, and never silently dropped.

Why this module exists
----------------------
A migration ID is not an integer. Under **MR-5** it is a *pair* — four zero-padded digits
and an OPTIONAL single lowercase band-overflow letter — and the pair is the ordering key::

    (24, "") < (29, "") < (29, "a") < (30, "") < (49, "") < (49, "a") < (50, "")

Every place in this repository that reduced that pair to its first half has been wrong in
one of exactly two ways, and both were measured on 2026-08-10 against `master`:

* **It dropped the file without a word.** ``"0138a".isdigit()`` is ``False``, so a selector
  written as ``if head.isdigit()`` walked past every MR-5 suffixed file in the tree —
  ``0049b``, ``0049c``, ``0049d``, ``0049y``, ``0049z``, ``0114a``, ``0138a``, ``0155a``,
  ``0180a`` — and the duplicate-number guard behind it was disabled for precisely the files
  most likely to collide. A suffixed file is not a revision of the file before it:
  ``0114a`` carries ``mainline.fn_cue_coarse_project()``, an entire second projector that
  ``0114`` does not contain.
* **Or it swallowed a file that was never its own.** ``int(name[:4])`` truncates the key, so
  a band declared as ``0047``-``0049`` matched ``0049a_delta_witness.sql`` as well —
  a file whose owner is ``algorithms`` and not ``datamodel/dm-spine``.
  ``verticals/mainline/db/migrations.allocation.toml`` is explicit about this: the band
  ``first = "0047" / last = "0049"`` says *bare 0049 only; its letter space is the
  algorithms annexe below*, and the next band is ``first = "0049a" / last = "0049z"``.
  A ``last`` **without** a letter closes at the bare number; a ``last`` **with** one closes
  at that letter, so ``z`` means "this band owns the whole of its final number".

Both are the same defect: a selector that answers a question about a *key* by looking at
part of the key. So there is one parser, it returns a key, and it **raises** on anything it
cannot order.

The three properties this module is built to have
-------------------------------------------------
1. **It parses the whole key.** :func:`parse_id` accepts ``NNNN`` and ``NNNN[a-z]`` and
   nothing else, because that is what MR-5 says and what ``lint._BAND_KEY_RE`` enforces.
2. **It orders correctly.** :class:`MigrationId` is a comparable pair, so
   ``0138 < 0138a < 0139`` holds by construction rather than by a sort function somebody
   has to remember to pass.
3. **It never returns a sentinel.** Not ``None``, not ``False``, not ``-1``, not a skip.
   A name this parser cannot order raises :class:`MigrationIdInvalid`, and a directory
   containing such a name raises :class:`MigrationTreeMismatch` *naming the file*. A
   selector that can drop a file without saying so is the failure this module exists to
   make impossible, and returning a falsy value is how that failure is spelled.

What this module is not
-----------------------
It is not a second :mod:`trappoint_migrate.discovery`. ``discover()`` reads SQL, hashes it
and produces the apply stream; this reads *names* and produces *keys*, needs no file
contents, and is therefore usable from a static test that must run on a machine with no
cluster and no ``uv sync``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import MigrateError

__all__ = [
    "MIGRATION_FILENAME",
    "MIGRATION_ID",
    "MigrationId",
    "MigrationIdInvalid",
    "MigrationTreeMismatch",
    "ScannedMigration",
    "assert_declared_band_matches_tree",
    "id_of_filename",
    "parse_id",
    "scan_tree",
    "select_band",
]


class MigrationIdInvalid(MigrateError):
    """A name this parser cannot place in the MR-5 ordering.

    Raised, always — never signalled by a falsy return. The whole reason this class exists
    is that ``None`` at a call site becomes ``continue`` at the next line, and ``continue``
    is how a migration leaves the apply set without appearing in any log.
    """


class MigrationTreeMismatch(MigrateError):
    """A directory and a declaration disagree, or a directory holds a name nobody can order.

    The message always names the files on **each** side. "The band does not match" is not
    actionable; "``0049a_delta_witness.sql`` is on disk and not declared" is.
    """


#: MR-5's key, exactly: four decimal digits and at most one lowercase letter.
#: Identical in shape to ``lint._BAND_KEY_RE`` on purpose — the allocation file's band
#: endpoints and a migration's own id are the same alphabet, and a parser that accepted
#: more here than lint accepts there would place files lint refuses.
MIGRATION_ID = re.compile(r"^(?P<number>[0-9]{4})(?P<suffix>[a-z]?)$")

#: MR-5's filename, exactly: the key, an underscore, a lower-snake slug, ``.sql``.
#: **No second dot, ever** — ``0031_clause_embedding.fallback.sql`` yields a stem
#: ``discovery._VERSION_RE`` rejects, and ``discover()`` then refuses the ENTIRE directory.
MIGRATION_FILENAME = re.compile(
    r"^(?P<number>[0-9]{4})(?P<suffix>[a-z]?)_(?P<slug>[a-z0-9_]+)\.sql$"
)

#: Near-misses worth diagnosing by name. A message that says only "invalid" makes the
#: reader re-derive the rule; each of these was an actual failure mode in this tree.
_NEAR_MISSES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^[0-9]{4}[a-z]{2,}$"),
        (
            "more than one lowercase letter — MR-5's suffix is a SINGLE letter, and a "
            "second one has no defined position between `0138a` and `0139`"
        ),
    ),
    (
        re.compile(r"^[0-9]{4}[A-Za-z]*[A-Z][A-Za-z]*$"),
        (
            "an uppercase letter — MR-5's suffix is lowercase, and case-insensitive "
            "ordering is not the ordering the runner applies in"
        ),
    ),
    (
        re.compile(r"^[0-9]{1,3}[a-z]?$"),
        (
            "fewer than four digits — MR-5 zero-pads to exactly four so that "
            "lexicographic ordering on the stem is numeric ordering"
        ),
    ),
    (
        re.compile(r"^[0-9]{5,}[a-z]?$"),
        "more than four digits — MR-5 is exactly four, and 0200 and above is UNALLOCATED",
    ),
)


@dataclass(frozen=True, order=True, slots=True)
class MigrationId:
    """One migration's allocation key: ``(number, suffix)``, ordered pairwise.

    ``order=True`` is the entire mechanism. Comparison is on ``number`` first and ``suffix``
    second, and the empty string sorts before ``"a"``, so::

        MigrationId(138, "") < MigrationId(138, "a") < MigrationId(139, "")

    holds without anybody supplying a key function. Every ordering bug this module replaces
    came from a call site that had to remember to supply one.
    """

    number: int
    suffix: str = ""

    def __str__(self) -> str:
        """``MigrationId(138, "a")`` → ``"0138a"`` — the spelling used in every message."""
        return f"{self.number:04d}{self.suffix}"


@dataclass(frozen=True, order=True, slots=True)
class ScannedMigration:
    """One file on disk, with the key it claims. Ordered by key, then by path."""

    id: MigrationId
    path: Path

    @property
    def name(self) -> str:
        """The filename, which is what every failure message in this module prints."""
        return self.path.name


def _why_not(text: str) -> str:
    for pattern, reason in _NEAR_MISSES:
        if pattern.match(text):
            return reason
    return "it is not four digits followed by at most one lowercase letter"


def parse_id(text: str, *, where: str | None = None) -> MigrationId:
    """``"0138a"`` → ``MigrationId(138, "a")``. Raise rather than return a sentinel.

    Args:
        text: a bare MR-5 key — ``"0138"`` or ``"0138a"``. Not a filename; use
            :func:`id_of_filename` for that.
        where: optional context prepended to the failure, e.g. ``"SPINE_BANDS"``.

    Raises:
        MigrationIdInvalid: on anything this parser cannot order — including ``"0138A"``,
            ``"0138ab"``, ``"12345"`` and ``""``. Each of those was accepted, silently
            dropped or crashed on by one of the three parsers this module replaces.
    """
    match = MIGRATION_ID.match(text)
    if match is None:
        prefix = f"{where}: " if where else ""
        raise MigrationIdInvalid(
            f"{prefix}{text!r} is not a migration id — {_why_not(text)}.\n"
            "MR-5: `NNNN[a-z]` — exactly four decimal digits, zero-padded, and at most one "
            "lowercase letter, e.g. `0138` or `0138a`.\n"
            "This is raised rather than skipped on purpose: a name this band cannot order "
            "is a thing to report, never a thing to walk past."
        )
    return MigrationId(int(match.group("number")), match.group("suffix"))


def id_of_filename(name: str | Path, *, where: str | None = None) -> MigrationId:
    """``0138a_trg_cue_prefix_project_coarse.sql`` → ``MigrationId(138, "a")``.

    The WHOLE filename is matched, not a prefix. A prefix match would accept
    ``0031_clause_embedding.fallback.sql`` — the exact filename that made
    ``discovery.discover()`` raise ``MigrationTreeInvalid`` for all 121 files beside it,
    which is not "the fallback was skipped" but "no migration in MAINLINE applied at all".

    Raises:
        MigrationIdInvalid: on any name outside ``NNNN[a-z]_lower_snake_slug.sql``.
    """
    filename = name.name if isinstance(name, Path) else name
    match = MIGRATION_FILENAME.match(filename)
    if match is None:
        prefix = f"{where}: " if where else ""
        raise MigrationIdInvalid(
            f"{prefix}{filename!r} is not a migration filename.\n"
            "MR-5: `NNNN[a-z]_lower_snake_slug.sql` — four digits, at most one lowercase "
            "letter, a `[a-z0-9_]+` slug, and NO SECOND DOT. A `.fallback.sql` / `.v2.sql` "
            "stem fails `discovery._VERSION_RE` and makes the whole directory "
            "undiscoverable; a `.up.sql` twin claims a version its sibling already claims. "
            "Capability variants live in `verticals/<vertical>/db/ext/<topic>/`."
        )
    return MigrationId(int(match.group("number")), match.group("suffix"))


def scan_tree(root: Path, *, where: str | None = None) -> list[ScannedMigration]:
    """Every migration in *root*, keyed and ordered. Refuses; never skips.

    Three things are refusals rather than omissions, and each names the file:

    * an entry this parser cannot order — including a stray ``README.md`` or a
      ``.fallback.sql`` variant that wandered into the apply path;
    * two files claiming one key;
    * a *root* that is not a directory.

    An EMPTY directory is not an error — a binding whose SQL has not been rendered yet is a
    normal state — but a directory with an unnameable file in it is, because that file is
    the one a reader would never be told about.

    Raises:
        MigrationTreeMismatch: on an unnameable entry, a duplicate key, or a missing root.
    """
    label = where or str(root)
    if not root.is_dir():
        raise MigrationTreeMismatch(
            f"{label}: {root} is not a directory, so 'the tree' is a set nobody can "
            "enumerate. An absent migration tree is reported, not treated as empty."
        )

    found: dict[MigrationId, ScannedMigration] = {}
    unnameable: list[str] = []
    collisions: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            unnameable.append(f"{path.name} — is not a file")
            continue
        try:
            key = id_of_filename(path.name)
        except MigrationIdInvalid as exc:
            unnameable.append(f"{path.name} — {str(exc).splitlines()[0]}")
            continue
        if key in found:
            collisions.append(f"{key}: {found[key].name} and {path.name}")
            continue
        found[key] = ScannedMigration(id=key, path=path)

    problems: list[str] = []
    if unnameable:
        problems.append(
            "these entries are in the migration tree and this selector cannot order them, "
            "so it will not silently pretend they are absent:\n  " + "\n  ".join(unnameable)
        )
    if collisions:
        problems.append(
            "two files claim one migration key, so the applied order depends on which one "
            "the filesystem happens to yield first:\n  " + "\n  ".join(collisions)
        )
    if problems:
        raise MigrationTreeMismatch(f"{label}:\n\n" + "\n\n".join(problems))

    return sorted(found.values())


def select_band(
    files: Iterable[ScannedMigration],
    first: str | MigrationId,
    last: str | MigrationId,
    *,
    where: str | None = None,
) -> list[ScannedMigration]:
    """Return the files whose key is in ``[first, last]`` — endpoints included, keys not numbers.

    This is the half that ``int(name[:4])`` gets wrong. ``select_band(files, "0047", "0049")``
    returns ``0047``, ``0048`` and ``0049`` and **excludes** ``0049a``, because a ``last``
    without a letter closes at the bare number — which is exactly how
    ``migrations.allocation.toml`` hands ``0049``'s letter space to the ``algorithms``
    annexe without either band guessing. Pass ``"0049z"`` when a band really does own its
    final number's whole letter space.

    Raises:
        MigrationIdInvalid: if either endpoint is not an MR-5 key.
        MigrationTreeMismatch: if ``last`` sorts before ``first``.
    """
    label = where or "band"
    lo = first if isinstance(first, MigrationId) else parse_id(first, where=f"{label} first")
    hi = last if isinstance(last, MigrationId) else parse_id(last, where=f"{label} last")
    if hi < lo:
        raise MigrationTreeMismatch(
            f"{label}: the band {lo}-{hi} ends before it begins, so it selects nothing and "
            "would report an empty tree as a matching one"
        )
    return [entry for entry in sorted(files) if lo <= entry.id <= hi]


def assert_declared_band_matches_tree(
    root: Path,
    declared: Sequence[str],
    *,
    first: str | MigrationId,
    last: str | MigrationId,
    label: str,
    owner: str | None = None,
) -> list[Path]:
    """Assert the declared list IS the band on disk, or refuse and name the files on both sides.

    A hand-written file list is the right instrument — a glob would let another worker's
    stray file become a silent extra ``CREATE TABLE`` in the middle of a band — but only if
    disagreement between the list and the tree is a *refusal*. This is that refusal, and it
    prints the files on each side rather than a diff of two sorted sequences.

    The declaration is also checked against itself: every entry must be an MR-5 filename,
    entries must be unique, and the list must already be in applied order. A list that is
    correct as a *set* but wrong as a *sequence* applies a consumer before its producer,
    and that failure surfaces as an ``UndefinedFunction`` inside a fixture with nothing in
    it naming the file that was out of place.

    Args:
        root: the migration tree to enumerate.
        declared: filenames, in applied order, e.g. ``("0024_commit_obj.sql", …)``.
        first: inclusive band start key, e.g. ``"0024"``.
        last: inclusive band end key, e.g. ``"0031z"``.
        label: what to call this band in a failure message.
        owner: the band's owner from the allocation file, printed when the tree carries a
            file the declaration does not — because "this is not yours" is the actual
            finding and naming the owner is what makes it actionable.

    Returns:
        The declared files as paths, in applied order.

    Raises:
        MigrationTreeMismatch: on any disagreement, in either direction.
        MigrationIdInvalid: on a declaration entry that is not an MR-5 filename.
    """
    keyed: dict[MigrationId, str] = {}
    for name in declared:
        key = id_of_filename(name, where=f"{label} declaration")
        if key in keyed:
            raise MigrationTreeMismatch(
                f"{label}: the declaration names migration {key} twice "
                f"({keyed[key]!r} and {name!r})"
            )
        keyed[key] = name
    if list(keyed) != sorted(keyed):
        raise MigrationTreeMismatch(
            f"{label}: the declaration is not in applied order. The runner applies in the "
            "order files are declared, so a misplaced entry applies a consumer before its "
            f"producer.\n  declared: {list(declared)}\n"
            f"  ordered:  {[keyed[k] for k in sorted(keyed)]}"
        )

    on_disk = select_band(scan_tree(root, where=label), first, last, where=label)
    disk_names = {entry.name for entry in on_disk}
    declared_names = set(keyed.values())

    undeclared = sorted(name for name in disk_names if name not in declared_names)
    absent = sorted(name for name in declared_names if name not in disk_names)
    if undeclared or absent:
        lo = first if isinstance(first, MigrationId) else parse_id(first)
        hi = last if isinstance(last, MigrationId) else parse_id(last)
        lines = [
            f"{label}: the declared band and the tree disagree.",
            f"  band:      {lo} .. {hi} (endpoints included, compared as MR-5 KEYS)",
        ]
        if owner:
            lines.append(f"  owner:     {owner}")
        if undeclared:
            lines.append(f"  on disk, not declared: {undeclared}")
        if absent:
            lines.append(f"  declared, not on disk: {absent}")
        lines.append(
            "  A file inside the band that the declaration does not carry is either another "
            "worker writing into it — which corrupts the applied order — or a file this band "
            "gained and never wrote down. Check the band's endpoints against "
            "migrations.allocation.toml before widening the declaration: `last` WITHOUT a "
            "letter closes at the bare number and hands that number's letter space to the "
            "next band, so `0047`-`0049` does not include `0049a`."
        )
        raise MigrationTreeMismatch("\n".join(lines))

    return [root / keyed[key] for key in sorted(keyed)]
