# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""``trappoint migrate lint`` — the sequence ban, the citation rule, and the allocation.

Five rules. Two of them are why this command exists at all; three of them were added by
the migration reconciliation of 2026-08-08 (``docs/leads/migration-reconciliation.md``,
ruling MR-6) after two domains implemented the same section of the migration order under
two conventions and the pre-dispatch collision check — a literal string comparison
between one side's number *bands* and the other side's *file paths* — reported zero
collisions across twenty numbers.

**The three added rules, and what each one refuses.**

* **Rule A · ``filename-convention``.** Every discovered filename matches
  ``^\d{4}[a-z]?_[a-z0-9_]+\.sql$`` (MR-5). A second dot is the interesting failure:
  ``0031_clause_embedding.fallback.sql`` yields the stem ``0031_clause_embedding.fallback``,
  which ``discovery._VERSION_RE`` does not admit, and the runner then refuses the **whole
  directory** — one badly-named file makes every other migration in the tree
  undiscoverable.
* **Rule B · ``allocation-mode`` / ``allocation-unallocated``.** Every file's number is
  resolved against ``migrations.allocation.toml``, and the band's ``mode`` must agree
  with the file: a file carrying ``-- @rendered-by  trappoint render`` in an ``authored``
  band is a refusal, and so is a file without that banner in a ``rendered`` band. This is
  the rule that compares a file against a *declaration* rather than comparing two
  declarations with each other, which is the thing the collision check could not do.
* **Rule C · ``up-sql-suffix``.** ``.up.sql`` is a failure. **This rule is RED on the
  MAINLINE tree until reconciliation workers 3, 4 and 5 land their renames** — see
  ``_rule_c_up_sql``.

**And the two the command was written for.**

**THE SEQUENCE BAN (ruling D10).** ``CREATE SEQUENCE``, ``nextval(``, ``SERIAL`` and
``unique_rowid()`` are refused in every migration file and every rendered template.

The claim the ban protects is precise and it is worth stating in full, because it is
the thing that stops being true the moment one migration slips through. The event
ledger is gap-free **by compare-and-swap** — ``UNIQUE (subject, prev_seq)`` — and not
by a sequence. A sequence in CockroachDB is allowed to leave gaps: a rolled-back
transaction consumes a value, and ``unique_rowid()`` is not dense by construction. So
under a sequence, a gap in the ledger means *nothing*: it might be tampering or it
might be Tuesday. Under CAS, **a gap MEANS tampering**, and that sentence is the whole
evidentiary value of the ledger. One reintroduced sequence anywhere in the schema and
the sentence has to be withdrawn.

A convention cannot hold that. A lint can.

**THE CITATION RULE (ARCHITECTURE.md §18).** Every migration file cites at least one
``MI\\d\\d`` or ``I\\d\\d`` in its header comment. The repository becomes an instance of
its own thesis: every clause carries a pointer to what wrote it, including the clauses
of the schema.

The lint is run over code with comments stripped (see ``sqltext``), so this docstring
and the explanatory comments in a migration file are free to name the banned tokens —
which they must be, or the rule cannot be explained where it applies.
"""

from __future__ import annotations

import itertools
import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .discovery import MIGRATION_SUFFIXES, statement_count
from .errors import MigrationTreeInvalid
from .sqltext import header_comment, strip_sql_comments

__all__ = [
    "ALLOCATION_SUFFIX",
    "RENDERED_BANNER",
    "UP_SQL_DETAIL",
    "Allocation",
    "Band",
    "Finding",
    "LintReport",
    "find_allocation",
    "key_of_filename",
    "lint_paths",
    "lint_text",
    "load_allocation",
]

# Template sources are linted too: a banned token in a `.j2` becomes a banned token in
# every rendered vertical, and catching it at the template is catching it once.
LINTED_SUFFIXES: tuple[str, ...] = (*MIGRATION_SUFFIXES, ".sql.j2", ".j2")

_BANNED: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "create-sequence",
        re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.IGNORECASE),
        "a sequence makes a gap ambiguous; the ledger is gap-free by CAS so a gap MEANS tampering",
    ),
    (
        "nextval",
        re.compile(r"\bnextval\s*\(", re.IGNORECASE),
        (
            "nextval() reads a sequence, and a rolled-back transaction consumes a value "
            "without producing a row"
        ),
    ),
    (
        "serial",
        re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.IGNORECASE),
        "SERIAL is a sequence with a friendlier name",
    ),
    (
        "unique-rowid",
        re.compile(r"\bunique_rowid\s*\(", re.IGNORECASE),
        "unique_rowid() is unique but not dense, so it cannot carry a gap-free claim",
    ),
)

_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")

# MR-5, stated as one regex: four digits, at most one lowercase letter, a lower_snake
# slug, `.sql`, and nothing else. No second dot, ever.
_MIGRATION_NAME_RE = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")
_UP_SUFFIX = ".up.sql"

# Duplicated from `trappoint_sql.render` rather than imported, for the same reason the
# banned-token table is: `trappoint-migrate`'s CLI dispatches `trappoint render` into
# that distribution, so a dependency the other way is a genuine import cycle. One
# string is a cheaper price than a cycle.
RENDERED_BANNER = "-- @rendered-by  trappoint render"
_BANNER_WINDOW = 4096

#: The allocation file for a migration tree ``<dir>`` is ``<dir>.allocation.toml``,
#: its sibling. It sits beside the directory rather than inside it because a `.toml`
#: inside the apply path is one glob away from being read as a migration.
ALLOCATION_SUFFIX = ".allocation.toml"

_BAND_KEY_RE = re.compile(r"^(?P<num>\d{4})(?P<letter>[a-z]?)$")
_FILE_KEY_RE = re.compile(r"^(?P<num>\d{4})(?P<letter>[a-z]?)_")
_ALLOCATED_MODES = ("rendered", "authored")
_UNALLOCATED_MODE = "unallocated"
_UNALLOCATED_OWNER = "UNALLOCATED"
_BAND_FIELDS = ("first", "last", "owner", "mode", "contents")


def _parse_key(text: str, *, where: str) -> tuple[int, str]:
    """Parse ``NNNN`` or ``NNNNx`` into the ordered pair the allocation compares on."""
    match = _BAND_KEY_RE.match(text)
    if match is None:
        raise MigrationTreeInvalid(
            f"{where}: {text!r} is not a band endpoint. An endpoint is four decimal "
            "digits with at most one lowercase letter, e.g. '0049' or '0049z'."
        )
    return int(match.group("num")), match.group("letter")


def _successor(key: tuple[int, str]) -> tuple[int, str]:
    """Return the immediately following key in the (number, suffix) lattice.

    ``(6, "") -> (6, "a")``, ``(6, "a") -> (6, "b")``, ``(6, "z") -> (7, "")``. This is
    the function contiguity is defined by: a band that ends at a bare number hands that
    number's letter space to whoever comes next, and a band that ends at ``z`` owns its
    final number outright.
    """
    number, letter = key
    if not letter:
        return (number, "a")
    if letter == "z":
        return (number + 1, "")
    return (number, chr(ord(letter) + 1))


def key_of_filename(name: str) -> tuple[int, str] | None:
    """Return the allocation key a migration filename claims, or None if there is none.

    Reads only the ``NNNN[a-z]_`` prefix, so it answers for a badly-named file too —
    which matters, because a file the runner refuses is still a file that occupies a
    number somebody else was granted.
    """
    match = _FILE_KEY_RE.match(name)
    if match is None:
        return None
    return int(match.group("num")), match.group("letter")


@dataclass(frozen=True, slots=True)
class Band:
    """One row of ``migrations.allocation.toml``: a number range with one owner."""

    first: str
    last: str
    owner: str
    mode: str
    contents: str

    @property
    def first_key(self) -> tuple[int, str]:
        """Inclusive lower bound, as an ordered (number, suffix) pair."""
        return _parse_key(self.first, where=f"band {self.first}-{self.last}")

    @property
    def last_key(self) -> tuple[int, str]:
        """Inclusive upper bound, as an ordered (number, suffix) pair."""
        return _parse_key(self.last, where=f"band {self.first}-{self.last}")

    @property
    def label(self) -> str:
        """The band as a human writes it, e.g. ``0047-0049``."""
        return f"{self.first}-{self.last}"

    def covers(self, key: tuple[int, str]) -> bool:
        """Report whether *key* falls inside this band, endpoints included."""
        return self.first_key <= key <= self.last_key


@dataclass(frozen=True, slots=True)
class Allocation:
    """Every band, validated exhaustive and disjoint over the range it declares."""

    source: Path
    bands: tuple[Band, ...]

    def band_for(self, key: tuple[int, str]) -> Band | None:
        """Return the one band covering *key*, or None when no band grants that number."""
        for band in self.bands:
            if band.covers(key):
                return band
        return None


def load_allocation(path: Path) -> Allocation:
    """Parse and validate an allocation file.

    Validation is the point, not a formality. A band table that overlaps is a table that
    grants one number to two owners, which is the incident this file was written to end;
    a table with a gap is an unowned number, which is how the incident started. Both are
    refused here rather than discovered later by a reader.

    Raises:
        MigrationTreeInvalid: on malformed TOML, a missing or unknown key, an illegal
            ``mode``, a band whose ``last`` precedes its ``first``, or any gap or
            overlap between consecutive bands.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise MigrationTreeInvalid(f"{path}: not valid TOML: {exc}") from exc

    rows = data.get("band")
    if not isinstance(rows, list) or not rows:
        raise MigrationTreeInvalid(
            f"{path}: no [[band]] entries. The allocation is the authority; an empty "
            "one authorises nothing."
        )

    bands: list[Band] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MigrationTreeInvalid(f"{path}: [[band]] #{index + 1} is not a table")
        missing = [k for k in _BAND_FIELDS if k not in row]
        if missing:
            raise MigrationTreeInvalid(
                f"{path}: [[band]] #{index + 1} is missing {', '.join(missing)}"
            )
        unknown = sorted(set(row) - set(_BAND_FIELDS))
        if unknown:
            raise MigrationTreeInvalid(
                f"{path}: [[band]] #{index + 1} carries unknown key(s) "
                f"{', '.join(unknown)}; the shape is fixed so that a typo cannot become "
                "a silently ignored grant"
            )
        bands.append(
            Band(
                first=str(row["first"]),
                last=str(row["last"]),
                owner=str(row["owner"]),
                mode=str(row["mode"]),
                contents=str(row["contents"]),
            )
        )

    _validate_bands(path, bands)
    return Allocation(source=path, bands=tuple(bands))


def _validate_bands(path: Path, bands: Sequence[Band]) -> None:
    """Refuse an illegal mode, an inverted band, and any gap or overlap."""
    for band in bands:
        if band.mode == _UNALLOCATED_MODE:
            if band.owner != _UNALLOCATED_OWNER:
                raise MigrationTreeInvalid(
                    f"{path}: band {band.label} is mode 'unallocated' but its owner is "
                    f"{band.owner!r}. 'unallocated' means nobody may write here, so it "
                    f"is legal only on a band owned by {_UNALLOCATED_OWNER!r}."
                )
        elif band.mode not in _ALLOCATED_MODES:
            raise MigrationTreeInvalid(
                f"{path}: band {band.label} has mode {band.mode!r}. Mode is binding — it "
                "says which directory the file is written in — and the only allocated "
                "values are 'rendered' and 'authored'."
            )
        if band.last_key < band.first_key:
            raise MigrationTreeInvalid(f"{path}: band {band.label} ends before it begins")

    for previous, band in itertools.pairwise(bands):
        expected = _successor(previous.last_key)
        if band.first_key < expected:
            raise MigrationTreeInvalid(
                f"{path}: band {band.label} ({band.owner}) overlaps band "
                f"{previous.label} ({previous.owner}). One number, one owner — an "
                "overlapping grant is the incident of 2026-08-08 written down."
            )
        if band.first_key > expected:
            raise MigrationTreeInvalid(
                f"{path}: a gap between band {previous.label} ({previous.owner}) and "
                f"band {band.label} ({band.owner}). A number space with no owner is "
                "exactly what produced two conventions (MRR-7); close it or extend one "
                "of the two bands."
            )


def find_allocation(root: Path) -> Allocation | None:
    """Return the allocation governing *root*, or None when the tree declares none.

    None is not an error. Template directories and the reference vertical's SQL have no
    allocation of their own, and rule B is silent there rather than inventing a band.
    """
    directory = root if root.is_dir() else root.parent
    candidate = directory.parent / f"{directory.name}{ALLOCATION_SUFFIX}"
    if candidate.is_file():
        return load_allocation(candidate)
    return None


@dataclass(frozen=True, slots=True)
class Finding:
    """One refusal, located precisely enough to fix without searching."""

    path: Path
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        """Format the finding as a single ``path:line: rule — detail`` line."""
        return f"{self.path}:{self.line}: {self.rule} — {self.detail}"


@dataclass(frozen=True, slots=True)
class LintReport:
    """The outcome of a lint run."""

    files_checked: int
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        """True when nothing was refused."""
        return not self.findings


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


UP_SQL_DETAIL = ".up.sql names a down counterpart that is illegal by construction (MR-5)"


def _rule_c_up_sql(path: Path) -> Finding | None:
    """Rule C — ``.up.sql`` is a failure.

    **THIS RULE IS RED ON THE MAINLINE TREE, DELIBERATELY, AND IT MUST NOT BE
    SOFTENED.** It is the PL-2 artefact of the migration reconciliation of 2026-08-08:
    a guard that was *observed* red is a guard that asserts something, and a guard that
    only ever ran green is a guard nobody has evidence works. It goes green when
    reconciliation workers 3, 4 and 5 finish renaming the 49 hand-authored ``.up.sql``
    files, and not one commit before. There is no exemption list, no warning level and
    no environment variable that downgrades it; if it is inconvenient in the meantime,
    that is the rule working.

    The rule is not a style preference. ``.up.sql`` names a ``.down.sql`` counterpart,
    and there is no down migration and there never will be: the ledger tables below the
    protected floor cannot be un-applied (``discover()`` raises on ``.down.sql``; DM-14
    forbids one at or below the floor). So the suffix advertises a file that is illegal
    by construction. Worse, it is a *suffix chain*, and a suffix chain is exactly what
    let two conventions coexist in one directory invisibly — ``_version_of()`` strips
    ``.up.sql`` and ``.sql`` alike, so ``0010_type_control_delta.up.sql`` and
    ``0010_type_control_delta.sql`` both claim version ``0010_type_control_delta`` and
    the runner refuses the tree.

    A file condemned by this rule is not analysed by rules A or B. Its number and its
    authoring mode are re-evaluated after the rename, and reporting three findings for
    one file that is about to stop existing would bury the one finding that matters.
    """
    if not path.name.endswith(_UP_SUFFIX):
        return None
    return Finding(path=path, line=1, rule="up-sql-suffix", detail=UP_SQL_DETAIL)


def _rule_a_filename(path: Path) -> Finding | None:
    r"""Rule A — the filename must match ``^\\d{4}[a-z]?_[a-z0-9_]+\\.sql$`` (MR-5).

    The regex is the whole of the convention: four zero-padded decimal digits, at most
    one lowercase letter (a companion statement or a band overflow, never a primary
    object of a free number), a ``lower_snake`` slug, ``.sql``.
    """
    name = path.name
    if _MIGRATION_NAME_RE.match(name) is not None:
        return None
    detail = (
        f"{name!r} does not match ^\\d{{4}}[a-z]?_[a-z0-9_]+\\.sql$ (MR-5). "
        "A SECOND DOT MAKES THE WHOLE TREE UNDISCOVERABLE: discovery's version regex "
        "does not admit '.', so one such filename makes `trappoint migrate` refuse the "
        "entire directory and every correctly-named migration beside it goes unapplied. "
        "A capability variant belongs in db/ext/<topic>/ behind a render-time switch, "
        "never next to the primary in the apply path."
    )
    return Finding(path=path, line=1, rule="filename-convention", detail=detail)


def _rule_b_allocation(path: Path, text: str, allocation: Allocation) -> Finding | None:
    """Rule B — the file's number must fall in a band that grants it to its mode.

    The band table (``migrations.allocation.toml``) is the authority. A hand-authored
    file in a ``rendered`` band is a permanently-red tree: ``trappoint render --check``
    is a zero-diff assertion and a hand-authored twin is not a diff, so CI stays green
    while the runner refuses the tree — CI green, deploy dead. The reverse, a rendered
    file in an ``authored`` band, is the same fault seen from the other side: deleting
    it does not resolve anything, because the next render puts it back.
    """
    key = key_of_filename(path.name)
    if key is None:
        return None
    band = allocation.band_for(key)
    if band is None:
        return Finding(
            path=path,
            line=1,
            rule="allocation-unallocated",
            detail=(
                f"{path.name!r} claims a number no band in {allocation.source.name} "
                "grants. Every number has an owner or it has no file; an unowned number "
                "is what produced two conventions (MRR-7)."
            ),
        )
    if band.mode == _UNALLOCATED_MODE:
        return Finding(
            path=path,
            line=1,
            rule="allocation-unallocated",
            detail=(
                f"{path.name!r} sits in band {band.label}, owner {band.owner}, mode "
                f"{band.mode}. {band.contents}"
            ),
        )
    rendered = RENDERED_BANNER in text[:_BANNER_WINDOW]
    if band.mode == "rendered" and not rendered:
        return Finding(
            path=path,
            line=1,
            rule="allocation-mode",
            detail=(
                f"{path.name!r} carries no {RENDERED_BANNER!r} banner but sits in band "
                f"{band.label}, owner {band.owner}, mode {band.mode}. A hand-authored "
                "twin of a rendered file is not a render diff, so --check stays green "
                "while the runner refuses the tree. Move the semantics into the "
                "template and re-render both bindings."
            ),
        )
    if band.mode == "authored" and rendered:
        return Finding(
            path=path,
            line=1,
            rule="allocation-mode",
            detail=(
                f"{path.name!r} carries the {RENDERED_BANNER!r} banner but sits in band "
                f"{band.label}, owner {band.owner}, mode {band.mode}. Nothing renders "
                "into this band; either the file is stale output of a deleted template "
                "or the band is wrong, and both are decisions, not accidents."
            ),
        )
    return None


def _naming_findings(
    path: Path,
    text: str,
    allocation: Allocation | None,
) -> list[Finding]:
    """Rules C, A and B, in that precedence, at most one finding per file.

    Precedence is deliberate. Rule C condemns the file outright, so rules A and B have
    nothing to add about it; rule A means the number cannot be trusted, so rule B has no
    key to resolve. One file, one refusal, one fix.
    """
    condemned = _rule_c_up_sql(path)
    if condemned is not None:
        return [condemned]
    misnamed = _rule_a_filename(path)
    if misnamed is not None:
        return [misnamed]
    if allocation is None:
        return []
    misplaced = _rule_b_allocation(path, text, allocation)
    return [misplaced] if misplaced is not None else []


def lint_text(
    path: Path,
    text: str,
    *,
    require_citation: bool,
    allocation: Allocation | None = None,
    check_naming: bool = True,
) -> list[Finding]:
    """Lint one file's *text*, returning every finding.

    *require_citation* is False for template sources: a `.j2` renders into files that
    each carry their own header, and requiring the citation in both places would make
    the template's header the one nobody updates.

    *check_naming* is False for the same reason: ``0050_permit.sql.j2`` is a template
    name, not a migration name, and MR-5 governs the files a template *emits*.

    *allocation* is the parsed ``migrations.allocation.toml`` governing this file's
    tree. None means the tree declares none, and rule B is silent rather than inventing
    a band.
    """
    findings: list[Finding] = []
    if check_naming:
        findings.extend(_naming_findings(path, text, allocation))
    code = strip_sql_comments(text)

    for rule, pattern, detail in _BANNED:
        for match in pattern.finditer(code):
            findings.append(
                Finding(
                    path=path,
                    line=_line_of(code, match.start()),
                    rule=f"banned-token:{rule}",
                    detail=f"{match.group(0)!r} — {detail}",
                )
            )

    if require_citation:
        header = header_comment(text)
        if not _CITATION.search(header):
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    rule="missing-invariant-citation",
                    detail=(
                        "the header comment cites no MInn or Inn identifier; "
                        "ARCHITECTURE.md §18 requires every migration to declare which "
                        "invariant it realises, where a reviewer reads it"
                    ),
                )
            )

        count = statement_count(text)
        if count > 1:
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    rule="multiple-statements",
                    detail=(
                        f"{count} statements in one file. CockroachDB DDL is not "
                        "transactional across statements, so a failure here leaves a "
                        "half-applied file and an undiagnosable dirty marker. Split it, "
                        "using a lowercase letter suffix (ruling D7)."
                    ),
                )
            )

    return findings


def _iter_files(roots: Sequence[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and any(path.name.endswith(s) for s in LINTED_SUFFIXES):
                yield path


def lint_paths(roots: Sequence[Path], *, allocation: Allocation | None = None) -> LintReport:
    """Lint every migration and template under *roots*.

    An empty tree passes with zero findings and zero files checked. That is the correct
    answer, not a vacuous one: the ban is a statement about what the tree may contain,
    and an empty tree contains nothing banned. The count is reported so a run that
    checked nothing is never mistaken for a run that checked everything.

    *allocation* overrides the per-root lookup. Left as None — which is what the CLI
    passes — each root resolves its own sibling ``<root>.allocation.toml``, so linting a
    migration tree and a template directory in one invocation applies the band rule to
    the tree and not to the templates.
    """
    findings: list[Finding] = []
    checked = 0
    for root in roots:
        governing = allocation if allocation is not None else find_allocation(root)
        for path in _iter_files([root]):
            checked += 1
            text = path.read_text(encoding="utf-8")
            is_template = path.name.endswith(".j2")
            findings.extend(
                lint_text(
                    path,
                    text,
                    require_citation=not is_template,
                    allocation=governing,
                    check_naming=not is_template,
                )
            )
    return LintReport(files_checked=checked, findings=tuple(findings))
