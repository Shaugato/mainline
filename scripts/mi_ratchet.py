#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The MI ratchet — PL-2 red-before-green, made mechanical (DM-8).

    python scripts/mi_ratchet.py                     # the catalogue, its counts, its witnesses
    python scripts/mi_ratchet.py check               # hermetic: integrity, projection, currency
    python scripts/mi_ratchet.py reconcile --write   # re-project owning_migrations, re-render
    python scripts/mi_ratchet.py red                 # the pending law  (mi-red CI job)
    python scripts/mi_ratchet.py green               # the enforced law (mi-green CI job)
    python scripts/mi_ratchet.py nodeids --status pending
    python scripts/mi_ratchet.py demote-check --base <old.yaml> --message "<commit body>"
    python scripts/mi_ratchet.py pl2-red             # the by-design-RED suites, by file
    python scripts/mi_ratchet.py selftest            # prove both laws bite

Why this file exists
--------------------
MAINLINE's deliverable is a **refusal**. A test suite for a refusal that has never been
red asserts nothing: it is indistinguishable from a suite that exercises a mechanism
which does not exist. Every worker on this build is capable of writing a confidently
green test against an empty schema, and a green board is exactly what such a test buys.

So `docs/leads/datamodel.md` §1.2 (DM-8) makes red-before-green a *data-driven CI gate*
rather than a habit. `verticals/mainline/db/invariants/mi_catalogue.yaml` carries all
thirty MAINLINE invariants (`ARCHITECTURE.md` §16) with a `status` of `pending` or
`enforced`, and two jobs run against the same suite:

**mi-green** — every `enforced` invariant's owning tests must pass. A skip is not a pass:
an invariant certified by a test that did not run is the failure mode this whole file
exists to prevent, so `green` refuses to certify on a skip.

**mi-red** — every `pending` invariant must have at least one owning test that currently
**fails**. A pending invariant whose tests all pass fails the build with

    MI25 is pending but its tests pass — promote it in mi_catalogue.yaml

Promotion is therefore a pull request that shows up in blame, and `demote-check` makes
the ratchet one-way: going back from `enforced` to `pending` needs an `ADR-` reference in
the commit body. This is MAINLINE's own O-Ring Ratchet turned on MAINLINE's test suite.

That refusal is an *instruction to review*, never an instruction to obey. A test may carry
``@pytest.mark.mi("MI22")`` — the author claiming to prove MI22 — and still assert nothing
that MI22's mechanism produces; promoting on it would record `enforced` against evidence
that would survive the mechanism being dropped, which is the false green this whole file
exists to forbid. So the refusal prints, beside the passing tests, **the enforcing object
the invariant's `mechanism` field names and where in the migration tree it was located** —
or that it is absent from all of them. A reviewer can then answer the only question that
matters: *would one of these tests still pass if that object were deleted?*

Two states the tree distinguishes, and they call for opposite actions:

*the object is absent* — `MI21`'s `CHECK undetermined_never_blocks` is in no migration in
the tree, so its passing witnesses cannot be exercising it. The catalogue is right and the
**marker** is misplaced; promotion would be a lie.

*the object is present but unexercised* — `MI22`'s merge-gate trigger is welded to
`mainline.permit`, but its ten witnesses assert file shape and the absence of RLS on the
CDC sources. The mechanism is real; the *witness* is not one. The fix is a test that makes
the gate refuse, not a status flip.

The projection discipline, applied to the build system
------------------------------------------------------
P2 says *a column a gate reads is written from an authoritative source, never trusted
from the writer*. The same rule holds here. `owning_migrations` is **not** a declaration:
it is a projection of `verticals/mainline/db/migrations.lock.json`, whose `invariants`
array is itself derived from the `-- MI:` header block of each migration file. `check`
recomputes the projection and refuses on drift; `reconcile --write` rewrites it. And, as
with every projecting trigger in the schema, a **missing** authoritative source is a hard
refusal (:class:`SourceMissing`, exit 2) rather than an empty projection — because an
empty projection would silently report that no migration enforces anything.

`MI-CATALOGUE.md` is rendered from the YAML by this script and asserted byte-identical by
`check`, following the `REFUSAL_DEPTH.md` / `ANOMALY_COVERAGE.md` convention already used
elsewhere in this repository: a generated document that is committed and current.

How an invariant finds its tests
--------------------------------
Two sources, unioned, because at S0 most owning tests do not exist yet and a catalogue
full of guessed node ids would be a catalogue full of lies:

*declared* — `owning_tests` holds selectors. Three forms, all resolved against the real
collected-test universe: an exact node id (``path.py::test_name``), an fnmatch glob on
the test name (``path.py::test_mi25_*``) and a bare module (``path.py``, every test in
it). A glob is a promise about naming; an exact id is a promise about a function. A
selector that matches nothing is reported as **unresolved** — legitimate while the owning
worker has not landed, fatal for anything `enforced`.

*discovered* — any test carrying ``@pytest.mark.mi("MIxx")`` is an owning test of that
invariant whether or not the catalogue says so, because that marker is the author
claiming to prove it. A bare ``miNN`` token in a *function name* is **not** a witness; it
is recorded as a *mention* and reported, and it never moves a status. The repository
already contains ``test_undetermined_forces_advisory_because_mi21_would_refuse_otherwise``
— a pure-Python unit test that asserts what a caller does *given* MI21 and never touches
the database. Promoting MI21 off that would be a false green of exactly the kind this
file exists to prevent.

Discovery is static (an :mod:`ast` walk, not a pytest collection) so it keeps working when
a suite cannot be collected at all — which, at the time of writing, is the state of
``tests/integration/schema/`` (see "Known repository defect" below).

*unwitnessed* — an invariant with neither. This is the normal state at S0 and it is
**reported, not fatal** (``red --require-witness`` makes it fatal, intended from K3). A
bare list of fourteen identifiers reads as fourteen things nobody is doing, which is the
opposite of true, so each one is printed with the refusal a witness would have to observe,
the selector the catalogue already reserves for it, and the band owner — read from
``verticals/mainline/db/migrations.allocation.toml``, the allocation authority — who is
building the mechanism it would observe.

The by-design-RED vocabulary
----------------------------
:data:`PL2_RED_MARKER` (``pl2_red``) is the registered name for a suite that is **red on
purpose**: `tests/integration/schema/test_mi_boundary_override.py`'s
``test_pl2_red_fn_boundary_project_does_not_exist_yet`` asserts that a mechanism does *not*
exist yet and fails until it does. Such a suite must not be deselected, `xfail`-swallowed
or run in the same lane as the ordinary suite, where a contributor cannot tell a designed
red from a regression. It belongs in an inverted job that fails when the red goes green —
the pattern `db-schema.yml`'s `mi-red` already uses.

The name is registered here rather than in `pyproject.toml` because this file is what
decides what "red on purpose" means in this repository; ``mi_ratchet.py pl2-red`` lists
every file that holds such a case, which is the list of files that should carry the marker.
Applying it is the owning suite's edit, not this script's.

Exit codes
----------
=====  ============================================================================
``0``  the law held.
``1``  the law was violated — a promotion is owed, a regression happened, drift.
``2``  the law could not be evaluated: an authoritative source is missing, or the
       suite could not be collected. A ratchet that reports a colour it did not
       measure is worse than a ratchet that fails.
=====  ============================================================================

Known repository defect (2026-08-09, reported upward, not worked around here)
-----------------------------------------------------------------------------
`tests/integration/schema/conftest.py` (owned by worker `dm-runner`) has not landed, so
`test_mi_foundation.py` uses `@pytest.mark.shape` / `.schema` / `.mi` with nothing having
registered them and `--strict-markers` turns collection into an error. `red` reports that
as *cannot determine* (exit 2) with the file named, and deliberately does **not** monkey-
patch the markers in: silently registering another worker's markers would convert a
visible build defect into an invisible one.

Dependencies: PyYAML (already in `uv.lock`) and, for `red`/`green` only, pytest.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final
from xml.etree import ElementTree

import yaml

# ── Layout ────────────────────────────────────────────────────────────────────────────

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

CATALOGUE_RELPATH: Final[str] = "verticals/mainline/db/invariants/mi_catalogue.yaml"
RENDERED_RELPATH: Final[str] = "verticals/mainline/db/invariants/MI-CATALOGUE.md"
LOCK_RELPATH: Final[str] = "verticals/mainline/db/migrations.lock.json"
MIGRATIONS_RELPATH: Final[str] = "verticals/mainline/db/migrations"
ALLOCATION_RELPATH: Final[str] = "verticals/mainline/db/migrations.allocation.toml"
RED_SUITE_RELPATH: Final[str] = "tests/integration/schema/test_mi_ratchet.py"
TEST_ROOT_RELPATH: Final[str] = "tests"

#: The window `trappoint_migrate.lint` reads a migration's header block from. Kept
#: identical so that "the linter saw this header" and "the ratchet saw this header" can
#: never be different sentences.
HEADER_WINDOW: Final[int] = 4096

EXIT_OK: Final = 0
EXIT_VIOLATION: Final = 1
EXIT_CANNOT_DETERMINE: Final = 2

# ── The vocabulary the catalogue is allowed to use ────────────────────────────────────

#: ARCHITECTURE.md §16: "`23514` / `23503` / `23505` / `P0001` are **gate refusals**".
GATE_SQLSTATES: Final[frozenset[str]] = frozenset({"23514", "23503", "23505", "P0001"})

#: "**`40001` is the only retryable code.**" A retry is not a refusal, so no invariant
#: may name it as the state it produces.
RETRYABLE_SQLSTATE: Final[str] = "40001"

#: TRAPPOINT's SemVer'd public API. An MI either instantiates one of these or is marked
#: as instantiating nothing, "and that is the interesting case" (§16).
TRAPPOINT_INVARIANTS: Final[frozenset[str]] = frozenset(f"I{n:02d}" for n in range(1, 17))

STATUSES: Final[tuple[str, ...]] = ("pending", "enforced")

MI_ID_RE: Final[re.Pattern[str]] = re.compile(r"^MI(0[1-9]|[12][0-9]|30)$")
ANY_MI_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"MI\d\d")
MI_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"^--\s*MI:\s*(?P<ids>.*)$", re.MULTILINE)
MIGRATION_NUMBER_RE: Final[re.Pattern[str]] = re.compile(r"^(?P<number>\d{4}[a-z]?)_")
ADR_REFERENCE_RE: Final[re.Pattern[str]] = re.compile(r"\bADR-\d{4}\b")
MI_IN_TESTNAME_RE: Final[re.Pattern[str]] = re.compile(r"(?:^|_)mi(\d\d)(?:_|$)")
RED_CASE_PREFIX: Final[str] = "test_red_"

# ── The by-design-RED vocabulary ──────────────────────────────────────────────────────
#
# Registered here, and nowhere else, because this file is what decides what "red on
# purpose" means in this repository. `ci.yml`'s pytest lane runs the ordinary suite and
# these suites together, so a designed red and a regression arrive in one number and a
# contributor cannot tell them apart. The marker is the selector that lets the two lanes
# separate — the by-design set into an INVERTED job that fails when the red goes green,
# which is the pattern `db-schema.yml`'s `mi-red` job already uses.

#: The pytest marker name. Registered in this vocabulary; applied by the owning suites.
PL2_RED_MARKER: Final[str] = "pl2_red"

#: The one-line registration `pyproject.toml`'s `markers` list needs, verbatim, so that
#: the description a contributor reads and the description this file means are one string.
PL2_RED_MARKER_DESCRIPTION: Final[str] = (
    "pl2_red: RED BY DESIGN (PL-2). This case asserts that a mechanism does NOT exist yet "
    "and fails until it lands. It is not a regression and it is never xfailed: it belongs "
    "in an inverted job that fails when it goes GREEN. Registered in scripts/mi_ratchet.py; "
    "list the files that hold such cases with `mi_ratchet.py pl2-red`."
)

#: The naming convention the tree already uses for such a case, e.g.
#: `test_pl2_red_fn_boundary_project_does_not_exist_yet`.
PL2_RED_NAME_PREFIX: Final[str] = "test_pl2_red_"

#: Phrases a by-design-RED case states in its own assertion text or docstring. Discovery
#: is by *self-description*: a case that says "RED BY DESIGN" in its failure message has
#: already told the reader what it is, and that sentence is the authority — not a list of
#: file names kept somewhere else, which is a second place to forget.
PL2_RED_SELF_DESCRIPTIONS: Final[tuple[str, ...]] = (
    "RED BY DESIGN",
    "PL-2 RED",
    "PL2 RED",
    "red by design",
)

REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "statement",
        "instantiates",
        "mechanism",
        "sqlstate",
        "headline",
        "owning_migrations",
        "owning_tests",
        "status",
        "adr",
    }
)

# Outcome vocabulary. `missing` is ours: a node the catalogue resolved but pytest never
# reported on. It is emphatically not a pass.
PASSED: Final = "passed"
FAILED: Final = "failed"
ERROR: Final = "error"
SKIPPED: Final = "skipped"
XFAILED: Final = "xfailed"
XPASSED: Final = "xpassed"
MISSING: Final = "missing"

#: Outcomes that constitute evidence the mechanism works. `xpassed` is excluded on
#: purpose: a test that was expected to fail and did not has not been read by anyone.
GREEN_OUTCOMES: Final[frozenset[str]] = frozenset({PASSED})


class RatchetError(Exception):
    """Base for every condition this script refuses on."""


class CatalogueError(RatchetError):
    """The catalogue is not a well-formed statement about thirty invariants."""


class SourceMissing(RatchetError):
    """An authoritative source a projection reads is absent.

    The projecting-trigger discipline (P2): a projection over a missing source is not an
    empty projection, it is a refusal. Exit 2, never a quiet zero.
    """


# ── Paths ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Paths:
    """Every file this script reads, resolvable so tests can point it at a temp tree."""

    repo_root: Path
    catalogue: Path
    rendered: Path
    lock: Path
    migrations: Path
    allocation: Path
    red_suite: Path
    test_root: Path

    @classmethod
    def under(cls, repo_root: Path) -> Paths:
        root = repo_root.resolve()
        return cls(
            repo_root=root,
            catalogue=root / CATALOGUE_RELPATH,
            rendered=root / RENDERED_RELPATH,
            lock=root / LOCK_RELPATH,
            migrations=root / MIGRATIONS_RELPATH,
            allocation=root / ALLOCATION_RELPATH,
            red_suite=root / RED_SUITE_RELPATH,
            test_root=root / TEST_ROOT_RELPATH,
        )

    def with_overrides(
        self,
        *,
        catalogue: Path | None = None,
        rendered: Path | None = None,
        lock: Path | None = None,
        migrations: Path | None = None,
        allocation: Path | None = None,
        red_suite: Path | None = None,
        test_root: Path | None = None,
    ) -> Paths:
        return Paths(
            repo_root=self.repo_root,
            catalogue=catalogue or self.catalogue,
            rendered=rendered or self.rendered,
            lock=lock or self.lock,
            migrations=migrations or self.migrations,
            allocation=allocation or self.allocation,
            red_suite=red_suite or self.red_suite,
            test_root=test_root or self.test_root,
        )


DEFAULT_PATHS: Final[Paths] = Paths.under(REPO_ROOT)


# ── The catalogue ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Invariant:
    """One row of ARCHITECTURE.md §16, plus the build-time fields DM-8 adds."""

    mi_id: str
    statement: str
    instantiates: str | None
    mechanism: str
    sqlstate: tuple[str, ...]
    headline: bool
    owning_migrations: tuple[str, ...]
    owning_tests: tuple[str, ...]
    status: str
    adr: str | None

    @property
    def is_enforced(self) -> bool:
        return self.status == "enforced"


@dataclass(frozen=True, slots=True)
class Proposal:
    """A statement a migration header asks for that §16 has not adopted.

    A comment cannot amend a numbered, versioned catalogue. Recording proposals here
    keeps the ask visible — and keeps the ratchet from either crashing on it or, worse,
    silently absorbing it as though a worker had made an architectural decision.
    """

    mi_id: str
    statement: str
    proposed_by: str
    owning_migrations: tuple[str, ...]
    disposition: str


@dataclass(frozen=True, slots=True)
class Catalogue:
    """Thirty invariants, in order, with the header fields of the source file."""

    schema_version: int
    source: str
    invariants: tuple[Invariant, ...]
    proposed: tuple[Proposal, ...] = ()

    def __iter__(self) -> Iterator[Invariant]:
        return iter(self.invariants)

    def __len__(self) -> int:
        return len(self.invariants)

    def by_id(self, mi_id: str) -> Invariant:
        for inv in self.invariants:
            if inv.mi_id == mi_id:
                return inv
        raise CatalogueError(f"{mi_id} is not in the catalogue")

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(inv.mi_id for inv in self.invariants)

    def with_status(self, status: str) -> tuple[Invariant, ...]:
        return tuple(inv for inv in self.invariants if inv.status == status)


def _require_mapping(raw: object, path: Path) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        raise CatalogueError(f"{path}: the top level must be a mapping, not {type(raw).__name__}")
    return raw


def _string_sequence(value: object, *, mi_id: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CatalogueError(f"{mi_id}.{key} must be a list, not {type(value).__name__}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CatalogueError(f"{mi_id}.{key} holds a non-string or empty entry: {item!r}")
        out.append(item)
    return tuple(out)


def _validate_sqlstates(states: tuple[str, ...], mi_id: str) -> None:
    if not states:
        raise CatalogueError(f"{mi_id}.sqlstate is empty; every refusal has a code")
    for state in states:
        if state == RETRYABLE_SQLSTATE:
            raise CatalogueError(
                f"{mi_id}.sqlstate names {RETRYABLE_SQLSTATE}, which is the only RETRYABLE code "
                f"(ARCHITECTURE.md §16). A retry is not a refusal."
            )
        if state not in GATE_SQLSTATES:
            raise CatalogueError(
                f"{mi_id}.sqlstate names {state!r}, which is not a gate refusal. "
                f"Allowed: {sorted(GATE_SQLSTATES)}"
            )


def _validate_instantiates(value: object, mi_id: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in TRAPPOINT_INVARIANTS:
        raise CatalogueError(
            f"{mi_id}.instantiates is {value!r}; expected one of I01..I16, or null for the "
            f"invariants §16 marks '—'"
        )
    return value


def _parse_invariant(raw: object, index: int) -> Invariant:
    if not isinstance(raw, Mapping):
        raise CatalogueError(f"invariants[{index}] must be a mapping")
    keys = set(raw.keys())
    if keys != REQUIRED_KEYS:
        missing = sorted(REQUIRED_KEYS - keys)
        extra = sorted(keys - REQUIRED_KEYS)
        raise CatalogueError(f"invariants[{index}]: missing={missing} unexpected={extra}")
    mi_id = raw["id"]
    if not isinstance(mi_id, str) or not MI_ID_RE.match(mi_id):
        raise CatalogueError(f"invariants[{index}].id is {mi_id!r}; expected MI01..MI30")
    statement = raw["statement"]
    mechanism = raw["mechanism"]
    for name, value in (("statement", statement), ("mechanism", mechanism)):
        if not isinstance(value, str) or len(value.strip()) < 8:
            raise CatalogueError(f"{mi_id}.{name} is absent or too short to be the §16 text")
    status = raw["status"]
    if status not in STATUSES:
        raise CatalogueError(f"{mi_id}.status is {status!r}; expected one of {STATUSES}")
    headline = raw["headline"]
    if not isinstance(headline, bool):
        raise CatalogueError(f"{mi_id}.headline must be a boolean")
    adr = raw["adr"]
    if adr is not None and (not isinstance(adr, str) or not ADR_REFERENCE_RE.search(adr)):
        raise CatalogueError(f"{mi_id}.adr is {adr!r}; expected null or a string naming ADR-NNNN")
    sqlstate = _string_sequence(raw["sqlstate"], mi_id=mi_id, key="sqlstate")
    _validate_sqlstates(sqlstate, mi_id)
    owning_tests = _string_sequence(raw["owning_tests"], mi_id=mi_id, key="owning_tests")
    for selector in owning_tests:
        validate_selector(selector, mi_id)
    return Invariant(
        mi_id=mi_id,
        statement=str(statement).strip(),
        instantiates=_validate_instantiates(raw["instantiates"], mi_id),
        mechanism=str(mechanism).strip(),
        sqlstate=sqlstate,
        headline=headline,
        owning_migrations=_string_sequence(
            raw["owning_migrations"], mi_id=mi_id, key="owning_migrations"
        ),
        owning_tests=owning_tests,
        status=str(status),
        adr=adr,
    )


PROPOSAL_KEYS: Final[frozenset[str]] = frozenset(
    {"id", "statement", "proposed_by", "owning_migrations", "disposition"}
)


def _parse_proposal(raw: object, index: int) -> Proposal:
    if not isinstance(raw, Mapping):
        raise CatalogueError(f"proposed[{index}] must be a mapping")
    if set(raw.keys()) != PROPOSAL_KEYS:
        raise CatalogueError(
            f"proposed[{index}]: keys must be exactly {sorted(PROPOSAL_KEYS)}, got "
            f"{sorted(raw.keys())}"
        )
    mi_id = raw["id"]
    if not isinstance(mi_id, str) or not re.fullmatch(r"MI\d\d", mi_id):
        raise CatalogueError(f"proposed[{index}].id is {mi_id!r}; expected an MInn identifier")
    if MI_ID_RE.match(mi_id):
        raise CatalogueError(
            f"{mi_id} is in MI01..MI30, so it is an invariant, not a proposal. An id may not "
            f"appear in both blocks."
        )
    for key in ("statement", "proposed_by", "disposition"):
        value = raw[key]
        if not isinstance(value, str) or len(value.strip()) < 8:
            raise CatalogueError(f"{mi_id}.{key} is absent or too short to be a decision")
    return Proposal(
        mi_id=mi_id,
        statement=str(raw["statement"]).strip(),
        proposed_by=str(raw["proposed_by"]).strip(),
        owning_migrations=_string_sequence(
            raw["owning_migrations"], mi_id=mi_id, key="owning_migrations"
        ),
        disposition=str(raw["disposition"]).strip(),
    )


def proposal_drift(catalogue: Catalogue, projection: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Reconcile the `proposed:` block against what the migration tree actually asks for."""
    asked = set(proposed_ids(projection))
    recorded = {proposal.mi_id: proposal for proposal in catalogue.proposed}
    drift: list[str] = []
    for mi_id in sorted(asked - set(recorded)):
        drift.append(
            f"migrations {list(projection[mi_id])} propose {mi_id}, which is neither in the "
            f"catalogue nor in its `proposed:` block. §16 is amended by an ADR, not by a header "
            f"comment — record the ask and its disposition, or correct the header."
        )
    for mi_id in sorted(set(recorded) - asked):
        drift.append(f"{mi_id} is recorded as proposed but no migration proposes it any more")
    for mi_id in sorted(asked & set(recorded)):
        if recorded[mi_id].owning_migrations != projection[mi_id]:
            drift.append(
                f"{mi_id}.owning_migrations (proposed) declares "
                f"{list(recorded[mi_id].owning_migrations)}, the tree says "
                f"{list(projection[mi_id])}"
            )
    return drift


def load_catalogue(path: Path) -> Catalogue:
    """Parse and validate the catalogue. Every failure names the invariant."""
    if not path.exists():
        raise SourceMissing(f"the invariant catalogue is absent: {path}")
    raw = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), path)
    entries = raw.get("invariants")
    if not isinstance(entries, list):
        raise CatalogueError(f"{path}: 'invariants' must be a list")
    invariants = tuple(_parse_invariant(entry, i) for i, entry in enumerate(entries))
    expected = tuple(f"MI{n:02d}" for n in range(1, 31))
    actual = tuple(inv.mi_id for inv in invariants)
    if actual != expected:
        raise CatalogueError(
            "the catalogue must hold MI01..MI30 exactly once each, in order; got "
            f"{len(actual)} entries starting {actual[:3]} — a gap here is an invariant nobody owns"
        )
    version = raw.get("schema_version")
    if version != 1:
        raise CatalogueError(f"{path}: schema_version must be 1, got {version!r}")
    source = raw.get("source")
    if not isinstance(source, str) or not source:
        raise CatalogueError(f"{path}: 'source' must name the document these statements come from")
    raw_proposed = raw.get("proposed") or []
    if not isinstance(raw_proposed, list):
        raise CatalogueError(f"{path}: 'proposed' must be a list")
    proposed = tuple(_parse_proposal(entry, i) for i, entry in enumerate(raw_proposed))
    return Catalogue(
        schema_version=version, source=source, invariants=invariants, proposed=proposed
    )


# ── owning_migrations is a projection, not a declaration ──────────────────────────────


@dataclass(frozen=True, slots=True)
class MigrationCitation:
    """What one migration file's header block says about the invariants it serves."""

    number: str
    filename: str
    #: the ids on the mandatory `-- MI:` line — the file's claim of ownership
    owning: tuple[str, ...]
    #: `MInn` tokens elsewhere in the header (a `-- proposes:` line, a cross-reference)
    #: that are outside MI01-MI30. A proposal, never an invariant.
    proposed: tuple[str, ...]


def scan_migrations(migrations_dir: Path) -> tuple[MigrationCitation, ...]:
    """Read the `-- MI:` header of every migration. This is the authoritative source.

    Not `migrations.lock.json`: the lock is a *manifest derived from* these headers, and a
    manifest that has fallen behind the tree would make `owning_migrations` a projection
    of a stale source — which is the exact failure P2 exists to prevent. The lock is kept
    as a cross-check (:func:`lock_disagreements`), not as the authority.
    """
    if not migrations_dir.exists():
        raise SourceMissing(
            f"the migration tree is absent: {migrations_dir}. owning_migrations projects from "
            f"the `-- MI:` header of every file in it; a projection over a missing source "
            f"refuses rather than reporting that nothing enforces anything."
        )
    citations: list[MigrationCitation] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        number_match = MIGRATION_NUMBER_RE.match(path.name)
        if number_match is None:
            raise SourceMissing(
                f"{path.name} does not begin with a migration number (NNNN[a-z]_), so it cannot "
                f"be attributed to an invariant"
            )
        head = path.read_text(encoding="utf-8")[:HEADER_WINDOW]
        header_lines = MI_HEADER_RE.findall(head)
        if len(header_lines) != 1:
            raise SourceMissing(
                f"{path.name} carries {len(header_lines)} `-- MI:` lines in its first "
                f"{HEADER_WINDOW} characters; the header block mandates exactly one"
            )
        owning = tuple(sorted(set(ANY_MI_TOKEN_RE.findall(header_lines[0]))))
        elsewhere = set(ANY_MI_TOKEN_RE.findall(head)) - set(owning)
        citations.append(
            MigrationCitation(
                number=number_match.group("number"),
                filename=path.name,
                owning=owning,
                proposed=tuple(sorted(t for t in elsewhere if not MI_ID_RE.match(t))),
            )
        )
    if not citations:
        raise SourceMissing(f"{migrations_dir} holds no migrations")
    return tuple(citations)


def unknown_citations(citations: Sequence[MigrationCitation]) -> list[str]:
    """A `-- MI:` line naming something §16 does not contain is a refusal, not a proposal."""
    return [
        f"migration {c.number} ({c.filename}) cites {mi_id} on its `-- MI:` line, which is not "
        f"one of MI01..MI30. The header block may only cite an invariant the catalogue holds."
        for c in citations
        for mi_id in c.owning
        if not MI_ID_RE.match(mi_id)
    ]


def project_owning_migrations(
    citations: Sequence[MigrationCitation],
) -> dict[str, tuple[str, ...]]:
    """MI id → the migration numbers whose `-- MI:` line cites it, sorted, deduplicated."""
    projection: dict[str, set[str]] = {f"MI{n:02d}": set() for n in range(1, 31)}
    for citation in citations:
        for mi_id in citation.owning:
            projection.setdefault(mi_id, set()).add(citation.number)
    return {mi_id: tuple(sorted(numbers)) for mi_id, numbers in projection.items()}


def project_proposals(citations: Sequence[MigrationCitation]) -> dict[str, tuple[str, ...]]:
    """Proposed id → the migrations whose header asks for it."""
    projection: dict[str, set[str]] = {}
    for citation in citations:
        for mi_id in citation.proposed:
            projection.setdefault(mi_id, set()).add(citation.number)
    return {mi_id: tuple(sorted(numbers)) for mi_id, numbers in projection.items()}


def load_lock(path: Path) -> Mapping[str, object] | None:
    """The migration manifest, when it exists. A cross-check, never the authority."""
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or not isinstance(raw.get("migrations"), list):
        raise SourceMissing(f"{path} is not a migration lock: no 'migrations' array")
    return raw


def lock_disagreements(
    citations: Sequence[MigrationCitation], lock: Mapping[str, object] | None
) -> list[str]:
    """Where the manifest contradicts the header it was derived from."""
    if lock is None:
        return []
    entries = lock["migrations"]
    if not isinstance(entries, list):  # pragma: no cover - load_lock already refused
        return []
    recorded: dict[str, set[str]] = {}
    for entry in entries:
        if isinstance(entry, Mapping) and isinstance(entry.get("file"), str):
            cited = entry.get("invariants") or []
            recorded[str(entry["file"])] = {
                name for name in cited if isinstance(name, str) and ANY_MI_TOKEN_RE.fullmatch(name)
            }
    return [
        f"migrations.lock.json says {c.filename} serves {sorted(recorded[c.filename])}, its "
        f"`-- MI:` header says {list(c.owning)} — regenerate the lock"
        for c in citations
        if c.filename in recorded and not set(c.owning) <= recorded[c.filename]
    ]


def lock_staleness(
    citations: Sequence[MigrationCitation], lock: Mapping[str, object] | None
) -> list[str]:
    """Files the manifest has never seen. Reported, never fatal: the lock is not the source."""
    if lock is None:
        return ["migrations.lock.json is absent; the header scan stands alone"]
    entries = lock["migrations"]
    if not isinstance(entries, list):  # pragma: no cover - load_lock already refused
        return []
    known = {
        str(entry["file"])
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("file"), str)
    }
    unseen = sorted(c.filename for c in citations if c.filename not in known)
    if not unseen:
        return []
    notice = (
        f"migrations.lock.json is stale: {len(unseen)} migrations on disk are absent from it "
        f"(first: {unseen[0]}, last: {unseen[-1]}). The catalogue projects from the `-- MI:` "
        f"headers, so this does not corrupt it — but the lock is a K1 deliverable and owner "
        f"`dm-runner` should regenerate it."
    )
    return [notice]


def proposed_ids(projection: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Every `MInn` a migration cites that §16 does not contain."""
    return tuple(sorted(mi_id for mi_id in projection if not MI_ID_RE.match(mi_id)))


def migration_drift(catalogue: Catalogue, projection: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Every place the declared ownership disagrees with the tree."""
    drift: list[str] = []
    for inv in catalogue:
        declared = tuple(inv.owning_migrations)
        actual = projection[inv.mi_id]
        if declared == actual:
            continue
        undeclared = sorted(set(actual) - set(declared))
        phantom = sorted(set(declared) - set(actual))
        parts: list[str] = []
        if undeclared:
            parts.append(f"cited by {undeclared} but not declared")
        if phantom:
            parts.append(f"declares {phantom}, which no migration cites")
        if not parts:
            parts.append(f"declared out of order: {declared} != {actual}")
        drift.append(f"{inv.mi_id}.owning_migrations " + "; ".join(parts))
    return drift


def rewrite_owning_migrations(text: str, projection: Mapping[str, tuple[str, ...]]) -> str:
    """Re-project the `owning_migrations` lines in place, preserving every comment.

    Line surgery rather than a YAML round-trip: the catalogue's prose is the point of the
    file, and PyYAML's emitter would delete every comment in it.
    """
    id_re = re.compile(r"^(?P<lead>\s*-\s+id:\s*)(?P<value>MI\d\d)\s*$")
    field_re = re.compile(r"^(?P<indent>\s*)owning_migrations:.*$")
    out: list[str] = []
    current: str | None = None
    for line in text.splitlines(keepends=True):
        id_match = id_re.match(line.rstrip("\r\n"))
        if id_match:
            current = id_match.group("value")
            out.append(line)
            continue
        field_match = field_re.match(line.rstrip("\r\n"))
        if field_match and current is not None:
            newline = line[len(line.rstrip("\r\n")) :]
            indent = field_match.group("indent")
            numbers = projection.get(current, ())
            out.append(f"{indent}owning_migrations: {_flow_seq(numbers)}{newline}")
            continue
        out.append(line)
    return "".join(out)


def _flow_seq(values: Sequence[str]) -> str:
    """A YAML flow sequence of quoted scalars.

    Quoted because YAML 1.1 reads `0020` as octal and `0029` as decimal 29; a migration
    number that silently becomes an integer is a projection that silently stops matching.
    """
    if not values:
        return "[]"
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


# ── Where the mechanism actually is ───────────────────────────────────────────────────
#
# The red law can say "these tests pass". It cannot, on its own, say whether they pass
# *because the mechanism works* or merely alongside it. Nothing static can answer that
# question outright — but the cheap half of it is answerable, and answering the cheap half
# is what turns "promote it" from an instruction into something a reviewer can check:
#
#   does the object the invariant's own `mechanism` field names exist in the tree at all?
#
# A `no` settles it — a passing test cannot be exercising a constraint that is in none of
# the 271 migrations, so the promotion is unjustified and the *marker* is what is wrong.
# A `yes` does not settle it, and the message says so rather than implying otherwise.


def strip_sql_comments(text: str) -> str:
    """Remove `--` and `/* */` comments, leaving string literals intact.

    Load-bearing, not hygiene. `fn_boundary_project` is named four times in the migration
    tree and defined nowhere: every one of those four is a `--` line in a header block
    explaining what the function *will* do when band 0140-0149z lands. A locator that
    searched raw text would report it PRESENT and the promotion it licensed would be false.

    Single-quoted literals are tracked so `'a--b'` survives; `''` self-escaping falls out
    of the state machine. Dollar-quoted bodies are not tracked as a unit because `--`
    inside a PL/pgSQL body is a comment there too — the one construct this would misread
    is an odd number of apostrophes inside such a body, which the tree does not contain
    (asserted by :func:`_selftest_locator`).
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "'":
                in_string = False
            i += 1
            continue
        if ch == "'":
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and text.startswith("--", i):
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        if ch == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


#: A SQL identifier as this schema writes them: lower snake_case, at least one underscore.
#: `mechanism` is prose with backticks in it, and one underscore is what reliably separates
#: `gate_closed_when_issued` from "trigger", "grants" and "RESTRICTIVE RLS".
MECHANISM_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

#: The states a named object can be in, worst first. `ABSENT` is the one that decides a
#: review; `NAMED` covers a column or an identifier that appears in executable SQL without
#: a `CREATE`/`CONSTRAINT` of its own, which is a true and unalarming answer.
OBJECT_ABSENT: Final = "absent"
OBJECT_NAMED: Final = "named"
OBJECT_DEFINED: Final = "defined"


def _definition_patterns(name: str) -> tuple[re.Pattern[str], ...]:
    """The ways this tree spells "here is the object called `name`"."""
    ident = re.escape(name)
    qualified = r"(?:[a-z_][a-z0-9_]*\s*\.\s*)?"
    return tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            rf"\bCONSTRAINT\s+{ident}\b",
            rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+{qualified}{ident}\s*\(",
            rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+{ident}\b",
            rf"\bCREATE\s+(?:UNIQUE\s+)?(?:INVERTED\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?{ident}\b",
            (
                rf"\bCREATE\s+(?:TABLE|VIEW|TYPE|ROLE|SEQUENCE|MATERIALIZED\s+VIEW)"
                rf"\s+(?:IF\s+NOT\s+EXISTS\s+)?{qualified}{ident}\b"
            ),
            rf"\bADD\s+CONSTRAINT\s+{ident}\b",
        )
    )


@dataclass(frozen=True, slots=True)
class MechanismObject:
    """One identifier out of an invariant's `mechanism`, and where the tree puts it."""

    mi_id: str
    name: str
    state: str
    #: migrations that DEFINE it (state `defined`), else that merely name it in SQL.
    files: tuple[str, ...]
    #: how many migration files were searched, so `absent` is a measured quantifier.
    searched: int

    def __str__(self) -> str:
        if self.state == OBJECT_DEFINED:
            where = ", ".join(self.files[:3])
            more = f" (+{len(self.files) - 3} more)" if len(self.files) > 3 else ""
            return f"`{self.name}` — DEFINED by {where}{more}"
        if self.state == OBJECT_NAMED:
            where = ", ".join(self.files[:3])
            more = f" (+{len(self.files) - 3} more)" if len(self.files) > 3 else ""
            return (
                f"`{self.name}` — named in executable SQL by {where}{more}, but no "
                f"CREATE/CONSTRAINT defines an object of that name (a column, or a name "
                f"used only in a RAISE)"
            )
        return (
            f"`{self.name}` — **ABSENT** from all {self.searched} migrations. A passing "
            f"test cannot be exercising it."
        )


def mechanism_identifiers(mechanism: str) -> tuple[str, ...]:
    """The SQL identifiers an invariant's `mechanism` names, in order, deduplicated.

    §16's mechanism column is prose: "revoked grants + `BEFORE UPDATE/DELETE` trigger +
    RESTRICTIVE RLS" names three real things and no identifier. That is not a failure of
    this function — it is the honest answer, and the caller says so rather than inventing
    a name to search for.
    """
    seen: dict[str, None] = {}
    for match in MECHANISM_IDENTIFIER_RE.finditer(mechanism):
        seen.setdefault(match.group(0), None)
    return tuple(seen)


def read_migration_bodies(migrations_dir: Path) -> dict[str, str]:
    """Every migration's executable SQL, comment-stripped, keyed by filename."""
    if not migrations_dir.exists():
        raise SourceMissing(
            f"the migration tree is absent: {migrations_dir}. The enforcing object a "
            f"promotion would be recorded against is located in it."
        )
    bodies = {
        path.name: strip_sql_comments(path.read_text(encoding="utf-8"))
        for path in sorted(migrations_dir.glob("*.sql"))
    }
    if not bodies:
        raise SourceMissing(f"{migrations_dir} holds no migrations")
    return bodies


def locate_mechanisms(
    catalogue: Catalogue, bodies: Mapping[str, str]
) -> dict[str, tuple[MechanismObject, ...]]:
    """MI id → where the tree puts each object its `mechanism` names."""
    searched = len(bodies)
    located: dict[str, tuple[MechanismObject, ...]] = {}
    for inv in catalogue:
        found: list[MechanismObject] = []
        for name in mechanism_identifiers(inv.mechanism):
            patterns = _definition_patterns(name)
            word = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            defining = [f for f, body in bodies.items() if any(p.search(body) for p in patterns)]
            naming = [f for f, body in bodies.items() if word.search(body)]
            if defining:
                state, files = OBJECT_DEFINED, defining
            elif naming:
                state, files = OBJECT_NAMED, naming
            else:
                state, files = OBJECT_ABSENT, []
            found.append(
                MechanismObject(
                    mi_id=inv.mi_id,
                    name=name,
                    state=state,
                    files=tuple(sorted(files)),
                    searched=searched,
                )
            )
        located[inv.mi_id] = tuple(found)
    return located


# ── Bands: who is building the thing a witness would have to observe ──────────────────


@dataclass(frozen=True, slots=True)
class Band:
    """One row of `migrations.allocation.toml` — the number-allocation authority."""

    first: str
    last: str
    owner: str

    @property
    def span(self) -> str:
        return f"{self.first}-{self.last}"


def _allocation_key(prefix: str) -> tuple[int, str]:
    """`0049a` → `(49, "a")`. The empty suffix sorts before `a`, as the file specifies."""
    digits = prefix[:4]
    return (int(digits), prefix[4:5].lower())


def load_bands(path: Path) -> tuple[Band, ...]:
    """The band table, or `()` when the authority is not there.

    Not a :class:`SourceMissing`: bands decorate an advisory line. A ratchet that refused
    to evaluate the red law because a *reporting* input was missing would be conflating
    "I could not measure the law" with "I could not annotate the output", and exit 2 is
    reserved for the first.
    """
    if not path.exists():
        return ()
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("band")
    if not isinstance(entries, list):
        return ()
    bands: list[Band] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        first, last, owner = entry.get("first"), entry.get("last"), entry.get("owner")
        if isinstance(first, str) and isinstance(last, str) and isinstance(owner, str):
            bands.append(Band(first=first, last=last, owner=owner))
    return tuple(bands)


def band_for(number: str, bands: Sequence[Band]) -> Band | None:
    """The band owning a migration number, or `None` when nothing claims it."""
    if len(number) < 4 or not number[:4].isdigit():
        return None
    key = _allocation_key(number)
    for band in bands:
        if _allocation_key(band.first) <= key <= _allocation_key(band.last):
            return band
    return None


def owners_of(numbers: Sequence[str], bands: Sequence[Band]) -> tuple[str, ...]:
    """The distinct band owners building a set of migrations, in first-seen order."""
    seen: dict[str, None] = {}
    for number in numbers:
        band = band_for(number, bands)
        if band is not None:
            seen.setdefault(f"{band.owner} ({band.span})", None)
    return tuple(seen)


# ── The collected-test universe, read statically ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TestFn:
    """One test function, addressed the way pytest addresses it.

    `marked` and `mentioned` are deliberately different fields, and only `marked` counts
    as a witness. `@pytest.mark.mi("MI11")` is the test author *claiming* to prove MI11;
    an `miNN` token in a function name is not. The distinction is not pedantry — the
    repository already contains `test_undetermined_forces_advisory_because_mi21_would_
    refuse_otherwise`, a pure-Python unit test that asserts what the caller does *given*
    MI21 and never touches the database. Counting it as MI21's witness would promote an
    invariant on evidence that its mechanism was never exercised, which is the exact false
    green PL-2 exists to forbid. Mentions are reported; they never move a status.
    """

    relpath: str
    name: str
    marked: tuple[str, ...]
    mentioned: tuple[str, ...] = ()
    #: this case is RED BY DESIGN — it asserts a mechanism does *not* exist yet. Detected
    #: from the `pl2_red` marker, the `test_pl2_red_` name prefix, or the case saying so
    #: in its own assertion text. Never a witness of anything; see :data:`PL2_RED_MARKER`.
    pl2_red: bool = False

    @property
    def nodeid(self) -> str:
        return f"{self.relpath}::{self.name}"


def _marked_invariants(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """The invariants a test explicitly claims, via `@pytest.mark.mi("MIxx")`."""
    found: set[str] = set()
    for decorator in node.decorator_list:
        text = ast.unparse(decorator)
        found.update(re.findall(r"mark\.mi\(\s*['\"](MI\d\d)['\"]", text))
    return tuple(sorted(found))


def _mentioned_invariants(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """The invariants a test's *name* refers to. Advisory only — never a witness."""
    return tuple(sorted({f"MI{suffix}" for suffix in MI_IN_TESTNAME_RE.findall(node.name)}))


def _is_pl2_red(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Is this case red on purpose? Three signals, any one of which is the author saying so.

    The marker is the one w1's `ci.yml` split selects on; the other two exist because the
    tree already holds such cases and they were written before the marker was registered.
    Detecting all three is what makes `pl2-red` a complete list rather than a list of the
    files somebody remembered to annotate.
    """
    for decorator in node.decorator_list:
        if re.search(rf"mark\.{PL2_RED_MARKER}\b", ast.unparse(decorator)):
            return True
    if node.name.startswith(PL2_RED_NAME_PREFIX):
        return True
    body = ast.unparse(node)
    return any(phrase in body for phrase in PL2_RED_SELF_DESCRIPTIONS)


def _functions_in(tree: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef):
                    yield inner


def collect_universe(test_root: Path, repo_root: Path) -> tuple[TestFn, ...]:
    """Every `test_*` function under `test_root`, with the invariants it claims.

    Static, because the schema tier does not currently collect under pytest and a
    resolution step that dies with the suite is a resolution step that cannot report
    *why* the suite is red.
    """
    if not test_root.exists():
        raise SourceMissing(f"the test root is absent: {test_root}")
    found: list[TestFn] = []
    for path in sorted(test_root.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise SourceMissing(f"{path} does not parse: {exc}") from exc
        relpath = path.resolve().relative_to(repo_root.resolve()).as_posix()
        for node in _functions_in(tree):
            if node.name.startswith("test_"):
                found.append(
                    TestFn(
                        relpath=relpath,
                        name=node.name,
                        marked=_marked_invariants(node),
                        mentioned=_mentioned_invariants(node),
                        pl2_red=_is_pl2_red(node),
                    )
                )
    return tuple(found)


def pl2_red_cases(universe: Sequence[TestFn]) -> dict[str, tuple[str, ...]]:
    """Test file → the by-design-RED cases in it. The files that should carry the marker."""
    found: dict[str, list[str]] = {}
    for fn in universe:
        if fn.pl2_red:
            found.setdefault(fn.relpath, []).append(fn.name)
    return {relpath: tuple(sorted(names)) for relpath, names in sorted(found.items())}


def mentions(catalogue: Catalogue, universe: Sequence[TestFn]) -> dict[str, tuple[str, ...]]:
    """MI id → tests whose *name* refers to it but which claim nothing. Advisory."""
    found: dict[str, list[str]] = {inv.mi_id: [] for inv in catalogue}
    for fn in universe:
        for mi_id in fn.mentioned:
            if mi_id in found and mi_id not in fn.marked:
                found[mi_id].append(fn.nodeid)
    return {mi_id: tuple(sorted(nodes)) for mi_id, nodes in found.items()}


# ── Selectors ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Selector:
    """A declared claim on tests: a module, a node id, or a glob over node names."""

    relpath: str
    name_glob: str | None

    @property
    def text(self) -> str:
        return self.relpath if self.name_glob is None else f"{self.relpath}::{self.name_glob}"

    def matches(self, fn: TestFn) -> bool:
        if fn.relpath != self.relpath:
            return False
        if self.name_glob is None:
            return True
        return fnmatch.fnmatchcase(fn.name, self.name_glob)


def validate_selector(selector: str, mi_id: str) -> Selector:
    """Refuse a selector that cannot address a test, before anything tries to run it."""
    if selector.count("::") > 1:
        raise CatalogueError(f"{mi_id}: selector {selector!r} has more than one '::'")
    relpath, _, name = selector.partition("::")
    if not relpath.startswith("tests/") or not relpath.endswith(".py"):
        raise CatalogueError(
            f"{mi_id}: selector {selector!r} must name a .py file under tests/ — the catalogue "
            f"addresses tests, not modules"
        )
    if "\\" in selector:
        raise CatalogueError(f"{mi_id}: selector {selector!r} uses a backslash; node ids are POSIX")
    if "::" in selector and not name.startswith("test_"):
        raise CatalogueError(f"{mi_id}: selector {selector!r} does not name a test_ function")
    return Selector(relpath=relpath, name_glob=name or None)


@dataclass(frozen=True, slots=True)
class Witnesses:
    """What actually witnesses one invariant, and what was claimed but is not there."""

    mi_id: str
    declared: tuple[str, ...]
    discovered: tuple[str, ...]
    unresolved: tuple[str, ...]

    @property
    def nodeids(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.declared) | set(self.discovered)))

    @property
    def is_unwitnessed(self) -> bool:
        return not self.nodeids


def resolve(catalogue: Catalogue, universe: Sequence[TestFn]) -> dict[str, Witnesses]:
    """Bind each invariant to the tests that currently exist for it."""
    by_mark: dict[str, list[str]] = {inv.mi_id: [] for inv in catalogue}
    for fn in universe:
        for mi_id in fn.marked:
            if mi_id in by_mark:
                by_mark[mi_id].append(fn.nodeid)
    resolution: dict[str, Witnesses] = {}
    for inv in catalogue:
        declared: list[str] = []
        unresolved: list[str] = []
        for text in inv.owning_tests:
            selector = validate_selector(text, inv.mi_id)
            hits = [fn.nodeid for fn in universe if selector.matches(fn)]
            if hits:
                declared.extend(hits)
            else:
                unresolved.append(text)
        resolution[inv.mi_id] = Witnesses(
            mi_id=inv.mi_id,
            declared=tuple(sorted(set(declared))),
            discovered=tuple(sorted(set(by_mark[inv.mi_id]) - set(declared))),
            unresolved=tuple(unresolved),
        )
    return resolution


# ── Outcomes ──────────────────────────────────────────────────────────────────────────


@dataclass(slots=True, eq=False)
class OutcomeCollector:
    """A pytest plugin that records one outcome per node id, and every collection error.

    `eq=False` is load-bearing, not stylistic: pytest keeps registered plugins in a set,
    and a dataclass with generated `__eq__` has `__hash__ = None`. With `eq=True` the run
    dies inside pytest's own fixture manager *after* the plugin is registered, which read
    from the outside as a suite that measured nothing and a law that held vacuously.
    """

    outcomes: dict[str, str] = field(default_factory=dict)
    collect_errors: list[str] = field(default_factory=list)
    #: pytest's own exit status. 0 and 1 are measurements; anything else is not.
    exit_code: int = 0

    def pytest_collectreport(self, report: object) -> None:
        if getattr(report, "failed", False):
            nodeid = getattr(report, "nodeid", "<unknown>")
            self.collect_errors.append(f"{nodeid}: {getattr(report, 'longreprtext', '')}".strip())

    def pytest_runtest_logreport(self, report: object) -> None:
        outcome = _outcome_of(report)
        if outcome is None:
            return
        nodeid = _normalise_nodeid(str(getattr(report, "nodeid", "")))
        previous = self.outcomes.get(nodeid)
        # A node has three phases; the worst news wins, so a passing call after a failing
        # setup never overwrites the failure.
        if previous is None or _severity(outcome) > _severity(previous):
            self.outcomes[nodeid] = outcome


def _outcome_of(report: object) -> str | None:
    when = getattr(report, "when", None)
    outcome = getattr(report, "outcome", None)
    if not isinstance(outcome, str):
        return None
    if outcome == "failed":
        return ERROR if when in {"setup", "teardown"} else FAILED
    if outcome == "skipped":
        return XFAILED if hasattr(report, "wasxfail") else SKIPPED
    if outcome == "passed":
        if when != "call":
            return None
        return XPASSED if hasattr(report, "wasxfail") else PASSED
    return None


def _severity(outcome: str) -> int:
    order = {PASSED: 0, XPASSED: 1, XFAILED: 2, SKIPPED: 3, MISSING: 4, FAILED: 5, ERROR: 6}
    return order.get(outcome, 5)


def _normalise_nodeid(nodeid: str) -> str:
    """`a/b.py::test_x[param]` → `a/b.py::test_x`, and Windows separators → POSIX."""
    return nodeid.replace("\\", "/").split("[", 1)[0]


def run_pytest(
    targets: Sequence[str], repo_root: Path, extra_args: Sequence[str]
) -> OutcomeCollector:
    """Run pytest in-process over the given files. pytest is the authority on colour."""
    import pytest  # imported here so `report`/`check` never need pytest at all

    collector = OutcomeCollector()
    argv = ["-q", "--no-header", *extra_args, *(str(repo_root / t) for t in targets)]
    collector.exit_code = int(pytest.main(argv, plugins=[collector]))
    return collector


def _junit_relpath(case: ElementTree.Element) -> str | None:
    """The test file a `<testcase>` came from.

    `file` is present under `junit_family=xunit1` and absent under the xunit2 default, so
    `classname` — a dotted module path, optionally suffixed with a test class — is the
    fallback. Class components are dropped by the only signal available in the string: a
    leading capital, which is PEP 8's rule and pytest's own `Test*` convention.
    """
    file_attr = case.get("file")
    if file_attr:
        return file_attr
    classname = case.get("classname")
    if not classname:
        return None
    parts = classname.split(".")
    while parts and parts[-1][:1].isupper():
        parts.pop()
    if not parts:
        return None
    return "/".join(parts) + ".py"


def read_junit(path: Path) -> OutcomeCollector:
    """Read outcomes out of a JUnit XML pytest already produced."""
    if not path.exists():
        raise SourceMissing(f"the JUnit report is absent: {path}")
    collector = OutcomeCollector()
    root = ElementTree.parse(path).getroot()  # noqa: S314 - our own CI artefact
    for case in root.iter("testcase"):
        relpath = _junit_relpath(case)
        name = case.get("name")
        if not relpath or not name:
            continue
        nodeid = _normalise_nodeid(f"{relpath}::{name}")
        outcome = PASSED
        if case.find("failure") is not None:
            outcome = FAILED
        elif case.find("error") is not None:
            outcome = ERROR
        elif case.find("skipped") is not None:
            outcome = SKIPPED
        collector.outcomes[nodeid] = outcome
    if not collector.outcomes:
        raise SourceMissing(
            f"{path} yielded no test outcomes — a report that names nothing cannot be turned "
            f"into a verdict"
        )
    return collector


def outcomes_for(witnesses: Witnesses, outcomes: Mapping[str, str]) -> dict[str, str]:
    return {nodeid: outcomes.get(nodeid, MISSING) for nodeid in witnesses.nodeids}


# ── The two laws ──────────────────────────────────────────────────────────────────────


#: The prefix of the red law's refusal. Held as a constant because it is asserted verbatim
#: by `tests/integration/schema/test_mi_ratchet.py` and quoted in `MI-CATALOGUE.md`: the
#: sentence is part of the contract, and only what follows it is free to get better.
RED_VIOLATION_PREFIX: Final[str] = "is pending but its tests pass — promote it in mi_catalogue.yaml"


def _mechanism_report(inv: Invariant, objects: Sequence[MechanismObject] | None) -> list[str]:
    """The enforcing object, as the migration tree has it: the mechanism line, then one
    line per identifier §16 names — or one line saying why no identifier could be read."""
    lines = [f'    mechanism (§16): "{inv.mechanism}" — refuses {"/".join(inv.sqlstate)}']
    if objects is None:
        lines.append(
            "    enforcing object: NOT LOCATED — the migration tree was not read on this run, "
            "so this promotion has no object beside it. Re-run where "
            "verticals/mainline/db/migrations is present."
        )
        return lines
    if not objects:
        claimed = len(inv.owning_migrations)
        cited = ", ".join(inv.owning_migrations[:6]) or "none"
        more = f" (+{claimed - 6} more)" if claimed > 6 else ""
        lines.append(
            f"    enforcing object: the mechanism names no SQL identifier, so it cannot be "
            f"located by name. Its only locator is the `-- MI:` citation: "
            f"{len(inv.owning_migrations)} migrations claim it ({cited}{more})."
        )
        return lines
    lines.append("    enforcing object(s), located in verticals/mainline/db/migrations:")
    lines.extend(f"      {obj}" for obj in objects)
    return lines


def _review_note(objects: Sequence[MechanismObject] | None) -> str:
    """What the reviewer is being asked to decide, stated as the decision it is."""
    if objects and any(obj.state == OBJECT_ABSENT for obj in objects):
        return (
            "    REVIEW: at least one object above is ABSENT from the tree, so no test can be "
            "exercising it and this promotion would be false. The defect is the witness, not "
            "the status — either the `@pytest.mark.mi` marker is on the wrong tests, or the "
            "mechanism is owed by the band that builds it."
        )
    return (
        "    REVIEW: promote only if one of the tests above makes an object above REFUSE. A "
        "test that would still pass with that object dropped witnesses nothing, and an "
        "`enforced` row recorded on it is the false green PL-2 exists to forbid."
    )


def red_violations(
    catalogue: Catalogue,
    resolution: Mapping[str, Witnesses],
    outcomes: Mapping[str, str],
    *,
    objects: Mapping[str, tuple[MechanismObject, ...]] | None = None,
) -> list[str]:
    """A pending invariant whose owning tests all pass is a promotion nobody made.

    `objects` is optional and *only* enriches the message: the law is unchanged, its
    threshold is unchanged, and the same set of invariants refuses with it or without it.
    What it buys is that the refusal stops being a bare instruction to flip a status and
    becomes a reviewable claim — the passing tests on one side, the object the invariant
    says does the refusing on the other, and the question between them.
    """
    violations: list[str] = []
    for inv in catalogue.with_status("pending"):
        witnesses = resolution[inv.mi_id]
        if witnesses.is_unwitnessed:
            continue
        observed = outcomes_for(witnesses, outcomes)
        if not all(outcome in GREEN_OUTCOMES for outcome in observed.values()):
            continue
        found = None if objects is None else objects.get(inv.mi_id, ())
        lines = [f"{inv.mi_id} {RED_VIOLATION_PREFIX}"]
        lines.extend(_mechanism_report(inv, found))
        lines.append(f"    passing owning tests ({len(observed)}):")
        lines.extend(f"      {nodeid}" for nodeid in sorted(observed))
        lines.append(_review_note(found))
        violations.append("\n".join(lines))
    return violations


def unwitnessed(
    catalogue: Catalogue, resolution: Mapping[str, Witnesses], status: str
) -> list[str]:
    return [
        inv.mi_id for inv in catalogue.with_status(status) if resolution[inv.mi_id].is_unwitnessed
    ]


def describe_unwitnessed(
    catalogue: Catalogue,
    resolution: Mapping[str, Witnesses],
    status: str,
    *,
    objects: Mapping[str, tuple[MechanismObject, ...]] | None = None,
    bands: Sequence[Band] = (),
) -> list[str]:
    """Say, per invariant, what a witness would have to be and who is building it.

    `unwitnessed (14): MI03, MI04, …` is fourteen identifiers and no information, and it
    reads — wrongly — as fourteen things nobody is doing. Every one of them has a mechanism
    named in §16, a selector this catalogue already reserves for it, and a band owner of
    record. Printing those three turns a list of gaps into a list of assignments.
    """
    lines: list[str] = []
    for mi_id in unwitnessed(catalogue, resolution, status):
        inv = catalogue.by_id(mi_id)
        found = () if objects is None else objects.get(mi_id, ())
        absent = [obj.name for obj in found if obj.state == OBJECT_ABSENT]
        present = [obj for obj in found if obj.state != OBJECT_ABSENT]
        lines.append(
            f"  {mi_id}  wanted: a test observing {'/'.join(inv.sqlstate)} from "
            f"{inv.mechanism} — {inv.statement}"
        )
        if absent and not present:
            lines.append(
                f"        in the tree: NOTHING — {', '.join(absent)} is in none of the "
                f"{found[0].searched} migrations, so such a test would be RED on arrival, "
                f"which is exactly the state PL-2 wants it written in"
            )
        elif absent:
            lines.append(
                f"        in the tree: {', '.join(o.name for o in present)} — but "
                f"{', '.join(absent)} is ABSENT, so the mechanism is only half built"
            )
        elif present:
            first = present[0]
            where = ", ".join(first.files[:2])
            more = f" +{len(first.files) - 2} more" if len(first.files) > 2 else ""
            names = ", ".join(o.name for o in present)
            lines.append(f"        in the tree: {names} — {where}{more}")
        reserved = ", ".join(resolution[mi_id].unresolved)
        lines.append(
            f"        reserved:    {reserved} (unwritten)"
            if reserved
            else "        reserved:    nothing — the catalogue names no test for it at all"
        )
        owners = owners_of(inv.owning_migrations, bands)
        if owners:
            shown = "; ".join(owners[:3])
            more = f"; +{len(owners) - 3} more" if len(owners) > 3 else ""
            lines.append(
                f"        owned by:    {shown}{more} "
                f"({len(inv.owning_migrations)} migrations cite it)"
            )
        elif not inv.owning_migrations:
            lines.append(
                "        owned by:    nobody — no migration cites it on a `-- MI:` line, so "
                "this one is unowned as well as unwitnessed"
            )
    return lines


def green_violations(
    catalogue: Catalogue,
    resolution: Mapping[str, Witnesses],
    outcomes: Mapping[str, str],
) -> list[str]:
    """An enforced invariant must be green, and a skip is not green."""
    violations: list[str] = []
    for inv in catalogue.with_status("enforced"):
        witnesses = resolution[inv.mi_id]
        if witnesses.is_unwitnessed:
            violations.append(
                f"{inv.mi_id} is enforced but no test resolves to it — an invariant nothing "
                f"witnesses is not enforced, it is asserted"
            )
            continue
        observed = outcomes_for(witnesses, outcomes)
        bad = {node: state for node, state in observed.items() if state not in GREEN_OUTCOMES}
        if bad:
            detail = ", ".join(f"{node} [{state}]" for node, state in sorted(bad.items()))
            violations.append(f"{inv.mi_id} is enforced but not green: {detail}")
    return violations


def demotion_violations(before: Catalogue, after: Catalogue, message: str) -> list[str]:
    """The ratchet is one-way: enforced → pending needs an ADR in the commit body."""
    cited = bool(ADR_REFERENCE_RE.search(message))
    violations: list[str] = []
    for inv in after:
        was = before.by_id(inv.mi_id)
        if was.is_enforced and not inv.is_enforced and not cited:
            violations.append(
                f"{inv.mi_id} is demoted from enforced to pending with no ADR-NNNN in the commit "
                f"body. A mechanism that stops being enforced is a decision, and decisions in "
                f"this repository are written down."
            )
    return violations


# ── The red suite's own shape ─────────────────────────────────────────────────────────


def red_case_names(red_suite: Path) -> tuple[str, ...]:
    """The deliberately-red cases in the ratchet's own suite, by naming convention."""
    if not red_suite.exists():
        raise SourceMissing(f"the ratchet's own suite is absent: {red_suite}")
    tree = ast.parse(red_suite.read_text(encoding="utf-8"), filename=str(red_suite))
    return tuple(fn.name for fn in _functions_in(tree) if fn.name.startswith(RED_CASE_PREFIX))


def red_suite_violations(red_suite: Path) -> list[str]:
    names = red_case_names(red_suite)
    if len(names) == 1:
        return []
    violation = (
        f"{red_suite.name} holds {len(names)} `{RED_CASE_PREFIX}*` cases {list(names)}; PL-2 wants "
        f"exactly one, so that 'the suite is red' has a single, nameable cause"
    )
    return [violation]


# ── Rendering ─────────────────────────────────────────────────────────────────────────

_RENDER_HEADER: Final[str] = """<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

<!-- GENERATED BY scripts/mi_ratchet.py — DO NOT EDIT. Run `python scripts/mi_ratchet.py
     reconcile --write`. `check` asserts this file is byte-identical to the render, so a
     hand edit is a failing build, not a divergent document. -->

# MAINLINE invariant catalogue — `MI01`-`MI30`
"""


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def _status_cell(inv: Invariant) -> str:
    if inv.is_enforced:
        return "**enforced**"
    return "pending"


def _render_summary(catalogue: Catalogue) -> list[str]:
    enforced = len(catalogue.with_status("enforced"))
    pending = len(catalogue.with_status("pending"))
    return [
        "",
        f"Source of the statements: **{catalogue.source}**. Renumbered from `I01-I24` to end",
        "the collision with TRAPPOINT's SemVer'd public API: TRAPPOINT keeps `I01-I16`, MAINLINE's",
        "schema invariants are `MI*`, and the third column maps each `MI` to the `I` it",
        "instantiates — where it maps to nothing, that is the interesting case and it reads `—`.",
        "",
        f"**{pending} pending · {enforced} enforced · {len(catalogue)} total.**",
        "",
        "`pending` does not mean unwritten. It means *no owning test has been observed to pass*,",
        "and CI **requires** at least one owning test of every pending invariant to be failing",
        "right now (`mi-red`). Promotion to `enforced` is a pull request; demotion needs an ADR.",
        "",
    ]


def _render_main_table(catalogue: Catalogue) -> list[str]:
    lines = [
        "## The thirty",
        "",
        "| # | Invariant | Instantiates | Mechanism | SQLSTATE | Status |",
        "|---|---|---|---|---|---|",
    ]
    for inv in catalogue:
        statement = _md_escape(inv.statement)
        if inv.headline:
            statement = f"**{statement}**"
        lines.append(
            f"| **{inv.mi_id}** | {statement} | {inv.instantiates or '—'} "
            f"| {_md_escape(inv.mechanism)} | {' / '.join(f'`{s}`' for s in inv.sqlstate)} "
            f"| {_status_cell(inv)} |"
        )
    lines.extend(
        [
            "",
            "`40001` is the only retryable code. `23514` / `23503` / `23505` / `P0001` are gate",
            "refusals: attempted exactly once, ever, and written to the refusal ledger with the",
            "constraint name. Any other SQLSTATE fails the suite, because it means the database",
            "refused for a reason nobody modelled.",
            "",
        ]
    )
    return lines


def _render_witness_table(catalogue: Catalogue) -> list[str]:
    lines = [
        "## The witness ledger",
        "",
        "`owning_migrations` is a **projection** of the `-- MI:` header of every file in",
        "`verticals/mainline/db/migrations`. It is never hand-written: `check` recomputes it and",
        "refuses on drift, and a missing migration tree refuses rather than projecting nothing.",
        "",
        "`owning_tests` is a declaration — the selectors the owning worker promised — unioned at",
        'resolution time with every test carrying `@pytest.mark.mi("MIxx")`. A bare `miNN` token',
        "in a test *name* is a **mention**, not a witness, and never moves a status: a unit test",
        "named for an invariant it reasons about has not exercised the mechanism that enforces it.",
        "",
        "| # | Status | Owning migrations | Declared owning tests |",
        "|---|---|---|---|",
    ]
    for inv in catalogue:
        migrations = ", ".join(f"`{m}`" for m in inv.owning_migrations) or "—"
        tests = "<br>".join(f"`{_md_escape(t)}`" for t in inv.owning_tests) or "—"
        lines.append(f"| `{inv.mi_id}` | {_status_cell(inv)} | {migrations} | {tests} |")
    lines.append("")
    return lines


_RENDER_CONTRACT: Final[tuple[str, ...]] = (
    "## The ratchet",
    "",
    "```",
    "python scripts/mi_ratchet.py check     # hermetic: integrity, projection, currency",
    "python scripts/mi_ratchet.py red       # the pending law. GREEN when pending are red",
    "python scripts/mi_ratchet.py green     # the enforced law. A skip is not a pass",
    "```",
    "",
    "**mi-green** — every `enforced` invariant's owning tests must pass. A skipped test does not",
    "certify an invariant: an invariant proven by a test that did not run is precisely the",
    "assertion-free green that PL-2 exists to forbid, so `green` refuses to certify on a skip.",
    "",
    "**mi-red** — every `pending` invariant must have at least one owning test that currently",
    "fails. A pending invariant whose tests all pass fails the build with",
    "",
    "```",
    "MI25 is pending but its tests pass — promote it in mi_catalogue.yaml",
    "```",
    "",
    "A pending invariant with no owning test at all is reported as **unwitnessed** and is not yet",
    "fatal — at S0 most owning workers have not landed. `red --require-witness` makes it fatal and",
    "is intended to be switched on at K3, when every table band exists.",
    "",
    "### Promotion",
    "",
    "1. The mechanism lands (a migration, a trigger, a constraint).",
    "2. Its owning test goes green on a real cluster.",
    "3. `mi-red` fails with `MIxx is pending but its tests pass — promote it`.",
    "4. A pull request flips `status: pending` to `status: enforced`. That PR *is* the",
    "   promotion, and it is in blame forever.",
    "",
    "### Demotion",
    "",
    "```",
    'python scripts/mi_ratchet.py demote-check --base <catalogue@base> --message "<body>"',
    "```",
    "",
    "`enforced` → `pending` requires an `ADR-NNNN` reference in the commit body. The ratchet is",
    "one-way by construction: an invariant that stops being enforced is a decision about what this",
    "system no longer promises, and decisions here are written down.",
    "",
    "### Wiring",
    "",
    "`.github/workflows/db-schema.yml` is owned by worker `dm-runner` and does not exist yet.",
    "Three steps are all it needs; the first two are hermetic and the third needs a cluster.",
    "",
    "```yaml",
    "- name: The catalogue must be committed and current",
    "  run: python scripts/mi_ratchet.py check          # exit 1 on drift, 2 on a missing source",
    "",
    "- name: mi-red — every pending invariant must have a failing owning test",
    "  run: python scripts/mi_ratchet.py red --on-collect-error-red",
    "",
    "- name: mi-green — every enforced invariant's owning tests must pass",
    "  run: python scripts/mi_ratchet.py green          # needs TRAPPOINT_DSN; a skip is a failure",
    "",
    "- name: The ratchet is one-way",
    "  run: |",
    "    BASE=${{ github.event.pull_request.base.sha }}",
    "    CAT=verticals/mainline/db/invariants/mi_catalogue.yaml",
    "    git show $BASE:$CAT > /tmp/base.yaml",
    "    python scripts/mi_ratchet.py demote-check --base /tmp/base.yaml \\",
    '      --message "$(git log -1 --format=%B)"',
    "```",
    "",
    "Exit `2` means *could not determine*, and is a different sentence from exit `1`, *the law was",
    "broken*. A job that conflates them publishes colours it never measured.",
    "",
    "### Currency is a step, not a test",
    "",
    "`tests/integration/schema/test_mi_ratchet.py` asserts that drift **would be caught**; it does",
    "not assert that the tree and the catalogue agree today. That check lives in the `check` step",
    "above, for the same reason `REFUSAL_DEPTH.md` and `ANOMALY_COVERAGE.md` are checked in",
    "`schema.yml` rather than in pytest — and for one more: PL-2's signal requires that suite to",
    "have exactly one cause of redness, and a currency assertion would hand every unrelated",
    "migration the power to add a second.",
    "",
)


def _render_proposals(catalogue: Catalogue) -> list[str]:
    if not catalogue.proposed:
        return []
    lines = [
        "## Proposed, not adopted",
        "",
        "A migration header may *ask* for an invariant. It cannot create one: `MI01`-`MI30` is a",
        "numbered, versioned catalogue and amending it is an ADR, not a comment. Every such ask is",
        "recorded here with its disposition, and `mi_ratchet check` refuses if the migration tree",
        "asks for something this block does not answer.",
        "",
    ]
    for proposal in catalogue.proposed:
        migrations = ", ".join(f"`{m}`" for m in proposal.owning_migrations) or "—"
        lines.extend(
            [
                f"### `{proposal.mi_id}` — {_md_escape(proposal.statement)}",
                "",
                f"* **proposed by** {proposal.proposed_by}",
                f"* **in migrations** {migrations}",
                f"* **disposition** {proposal.disposition}",
                "",
            ]
        )
    return lines


def render_markdown(catalogue: Catalogue) -> str:
    """The committed rendering of the catalogue. Deterministic — no clock, no host."""
    lines: list[str] = [_RENDER_HEADER.rstrip("\n")]
    lines.extend(_render_summary(catalogue))
    lines.extend(_render_main_table(catalogue))
    lines.extend(_render_witness_table(catalogue))
    lines.extend(_render_proposals(catalogue))
    lines.extend(_RENDER_CONTRACT)
    return "\n".join(lines).rstrip("\n") + "\n"


# ── Reporting ─────────────────────────────────────────────────────────────────────────


def summary_line(catalogue: Catalogue) -> str:
    pending = len(catalogue.with_status("pending"))
    enforced = len(catalogue.with_status("enforced"))
    return f"{pending} pending / {enforced} enforced"


def _print_report(
    catalogue: Catalogue,
    resolution: Mapping[str, Witnesses],
    mentioned: Mapping[str, tuple[str, ...]],
) -> None:
    print(f"MAINLINE invariant catalogue — {len(catalogue)} invariants ({catalogue.source})")
    print("")
    header = f"{'MI':<5} {'status':<9} {'sqlstate':<14} {'migs':>5} {'tests':>6}  witnesses"
    print(header)
    print("-" * len(header))
    for inv in catalogue:
        witnesses = resolution[inv.mi_id]
        note = "unwitnessed" if witnesses.is_unwitnessed else f"{len(witnesses.nodeids)} resolved"
        if witnesses.unresolved:
            note += f", {len(witnesses.unresolved)} not yet written"
        # A test can both satisfy a declared selector and mention the invariant in its
        # name. Only the ones that are *nothing but* a mention are worth reporting.
        mention_only = set(mentioned.get(inv.mi_id, ())) - set(witnesses.nodeids)
        if mention_only:
            note += f", {len(mention_only)} mention only"
        print(
            f"{inv.mi_id:<5} {inv.status:<9} {'/'.join(inv.sqlstate):<14} "
            f"{len(inv.owning_migrations):>5} {len(witnesses.nodeids):>6}  {note}"
        )
    print("")
    for proposal in catalogue.proposed:
        print(f"proposed (not adopted): {proposal.mi_id} — {proposal.proposed_by}")
    print(summary_line(catalogue))


# ── Commands ──────────────────────────────────────────────────────────────────────────


def _paths_from_args(args: argparse.Namespace) -> Paths:
    paths = Paths.under(Path(args.repo_root).resolve())
    return paths.with_overrides(
        catalogue=Path(args.catalogue).resolve() if args.catalogue else None,
        rendered=Path(args.rendered).resolve() if args.rendered else None,
        lock=Path(args.lock).resolve() if args.lock else None,
        migrations=Path(args.migrations).resolve() if args.migrations else None,
    )


def full_projection(citations: Sequence[MigrationCitation]) -> dict[str, tuple[str, ...]]:
    """Adopted invariants and proposals in one map, which is what line surgery needs."""
    return {**project_owning_migrations(citations), **project_proposals(citations)}


def cmd_report(args: argparse.Namespace) -> int:
    paths = _paths_from_args(args)
    catalogue = load_catalogue(paths.catalogue)
    universe = collect_universe(paths.test_root, paths.repo_root)
    _print_report(catalogue, resolve(catalogue, universe), mentions(catalogue, universe))
    return EXIT_OK


def check_violations(paths: Paths) -> list[str]:
    """Everything `check` asserts, as a list of failures. Empty means the build may proceed."""
    catalogue = load_catalogue(paths.catalogue)
    citations = scan_migrations(paths.migrations)
    violations = unknown_citations(citations)
    violations.extend(migration_drift(catalogue, project_owning_migrations(citations)))
    violations.extend(proposal_drift(catalogue, project_proposals(citations)))
    violations.extend(lock_disagreements(citations, load_lock(paths.lock)))
    if not paths.rendered.exists():
        violations.append(f"{paths.rendered} has never been rendered")
    elif paths.rendered.read_text(encoding="utf-8") != render_markdown(catalogue):
        violations.append(
            f"{paths.rendered.name} has drifted from the catalogue — "
            f"run `python scripts/mi_ratchet.py reconcile --write`"
        )
    violations.extend(red_suite_violations(paths.red_suite))
    return violations


def check_notices(paths: Paths) -> list[str]:
    """True, useful and not this file's to fix. Printed, never fatal."""
    return lock_staleness(scan_migrations(paths.migrations), load_lock(paths.lock))


def cmd_check(args: argparse.Namespace) -> int:
    paths = _paths_from_args(args)
    violations = check_violations(paths)
    for notice in check_notices(paths):
        print(f"NOTICE: {notice}")
    for violation in violations:
        print(f"REFUSED: {violation}")
    if violations:
        return EXIT_VIOLATION
    print(f"catalogue integrity OK — {summary_line(load_catalogue(paths.catalogue))}")
    return EXIT_OK


def cmd_reconcile(args: argparse.Namespace) -> int:
    paths = _paths_from_args(args)
    if not paths.catalogue.exists():
        raise SourceMissing(f"the invariant catalogue is absent: {paths.catalogue}")
    projection = full_projection(scan_migrations(paths.migrations))
    original = paths.catalogue.read_text(encoding="utf-8")
    rewritten = rewrite_owning_migrations(original, projection)
    if args.write:
        if rewritten != original:
            paths.catalogue.write_text(rewritten, encoding="utf-8", newline="\n")
        catalogue = load_catalogue(paths.catalogue)
        paths.rendered.parent.mkdir(parents=True, exist_ok=True)
        paths.rendered.write_text(render_markdown(catalogue), encoding="utf-8", newline="\n")
        print(f"wrote {paths.catalogue.name} and {paths.rendered.name} — {summary_line(catalogue)}")
        return EXIT_OK
    drifted = rewritten != original
    print(f"owning_migrations: {'DRIFTED' if drifted else 'current'}")
    catalogue = load_catalogue(paths.catalogue)
    current = paths.rendered.exists() and paths.rendered.read_text(
        encoding="utf-8"
    ) == render_markdown(catalogue)
    print(f"{paths.rendered.name}: {'current' if current else 'DRIFTED'}")
    return EXIT_VIOLATION if drifted or not current else EXIT_OK


def cmd_nodeids(args: argparse.Namespace) -> int:
    paths = _paths_from_args(args)
    catalogue = load_catalogue(paths.catalogue)
    universe = collect_universe(paths.test_root, paths.repo_root)
    resolution = resolve(catalogue, universe)
    wanted = catalogue.invariants if args.status == "all" else catalogue.with_status(args.status)
    nodeids: set[str] = set()
    for inv in wanted:
        nodeids.update(resolution[inv.mi_id].nodeids)
    for nodeid in sorted(nodeids):
        print(nodeid)
    return EXIT_OK


def _gather_outcomes(
    args: argparse.Namespace, paths: Paths, nodeids: Iterable[str]
) -> OutcomeCollector:
    if args.junit:
        return read_junit(Path(args.junit).resolve())
    files = sorted({nodeid.split("::", 1)[0] for nodeid in nodeids})
    if not files:
        return OutcomeCollector()
    extra = list(args.pytest_arg or [])
    if args.on_collect_error_red:
        # Without this pytest aborts the whole session on the first collection error and
        # exits 2, so the flag would promise a measurement it could not take.
        extra.insert(0, "--continue-on-collection-errors")
    return run_pytest(files, paths.repo_root, extra)


#: pytest exit statuses that mean "the run produced a measurement": all tests passed, or
#: some failed. 2 (interrupted), 3 (internal error) and 4 (usage error) mean the colours
#: on the floor are not the colours of the suite.
MEASURABLE_PYTEST_EXITS: Final[frozenset[int]] = frozenset({0, 1})


def _undetermined(
    collector: OutcomeCollector, targets: Iterable[str], *, allow_collect_errors: bool
) -> list[str]:
    """Every reason this run cannot be turned into a verdict."""
    reasons: list[str] = []
    if collector.collect_errors and not allow_collect_errors:
        reasons.extend(collector.collect_errors)
    if collector.exit_code not in MEASURABLE_PYTEST_EXITS:
        reasons.append(
            f"pytest exited {collector.exit_code} (not a pass/fail run), so the outcomes "
            f"recorded are not the outcomes of the suite"
        )
    if list(targets) and not collector.outcomes and not collector.collect_errors:
        reasons.append(
            "the run reported on no node at all, yet nodes were resolved — the suite was "
            "not executed"
        )
    return reasons


def _locate_for_report(
    catalogue: Catalogue, paths: Paths
) -> tuple[dict[str, tuple[MechanismObject, ...]] | None, tuple[Band, ...], str | None]:
    """Read the tree for the *message*, and never let that reading break the *law*.

    Locating the enforcing object is reporting, not measurement. If the tree cannot be
    read the law is still evaluable and must still be evaluated — so the failure is
    returned as a sentence to print, not raised. Exit 2 stays reserved for "the colour of
    the suite could not be measured", which is a different thing entirely.
    """
    try:
        objects = locate_mechanisms(catalogue, read_migration_bodies(paths.migrations))
    except (SourceMissing, OSError) as exc:
        return None, load_bands(paths.allocation), str(exc)
    return objects, load_bands(paths.allocation), None


def _law_command(args: argparse.Namespace, status: str) -> int:
    paths = _paths_from_args(args)
    catalogue = load_catalogue(paths.catalogue)
    universe = collect_universe(paths.test_root, paths.repo_root)
    resolution = resolve(catalogue, universe)
    targets: set[str] = set()
    for inv in catalogue.with_status(status):
        targets.update(resolution[inv.mi_id].nodeids)
    collector = _gather_outcomes(args, paths, targets)
    undetermined = _undetermined(collector, targets, allow_collect_errors=args.on_collect_error_red)
    if undetermined:
        for reason in undetermined:
            print(f"CANNOT DETERMINE: {reason}")
        print(
            "No colour was measured, so neither law was evaluated. "
            "Pass --on-collect-error-red only if an uncollectable suite should count as red."
        )
        return EXIT_CANNOT_DETERMINE
    objects: dict[str, tuple[MechanismObject, ...]] | None = None
    bands: tuple[Band, ...] = ()
    if status != "pending":
        # The green law needs no locator: an enforced invariant's owning tests are either
        # green or they are not, and where the object lives changes neither answer.
        violations = green_violations(catalogue, resolution, collector.outcomes)
    else:
        objects, bands, locator_note = _locate_for_report(catalogue, paths)
        if locator_note is not None:
            print(f"NOTICE: the enforcing objects could not be located — {locator_note}")
        violations = red_violations(catalogue, resolution, collector.outcomes, objects=objects)
    silent = unwitnessed(catalogue, resolution, status)
    if status == "pending" and silent:
        print(
            f"unwitnessed ({len(silent)}): {', '.join(silent)} — pending, with no owning test "
            f"resolved. Not fatal at S0 (`--require-witness` makes it fatal, intended from K3). "
            f"Each one below names the refusal a witness must observe, the selector this "
            f"catalogue already reserves for it, and the band owner building the mechanism."
        )
        for line in describe_unwitnessed(
            catalogue, resolution, status, objects=objects, bands=bands
        ):
            print(line)
        if args.require_witness:
            violations.extend(f"{mi_id} is pending and no test witnesses it" for mi_id in silent)
    for violation in violations:
        print(f"REFUSED: {violation}")
    if violations:
        return EXIT_VIOLATION
    print(f"{status} law holds over {len(targets)} node ids — {summary_line(catalogue)}")
    return EXIT_OK


def cmd_red(args: argparse.Namespace) -> int:
    return _law_command(args, "pending")


def cmd_green(args: argparse.Namespace) -> int:
    return _law_command(args, "enforced")


def cmd_pl2_red(args: argparse.Namespace) -> int:
    """List every by-design-RED case, by file. The files that should carry the marker.

    Printed rather than applied: the marker goes on a test, and a test belongs to the suite
    that owns it. A script that reached into another worker's file to annotate it would be
    making that worker's decision and hiding it in a diff nobody reviewed.
    """
    paths = _paths_from_args(args)
    universe = collect_universe(paths.test_root, paths.repo_root)
    cases = pl2_red_cases(universe)
    total = sum(len(names) for names in cases.values())
    print(f"marker: {PL2_RED_MARKER}")
    print(f"register in pyproject.toml `markers` as:\n  {PL2_RED_MARKER_DESCRIPTION}")
    print("")
    print(f"{total} by-design-RED case(s) in {len(cases)} file(s) — these files should carry it:")
    for relpath, names in cases.items():
        print(f"  {relpath}  ({len(names)})")
        if args.verbose:
            for name in names:
                print(f"      {name}")
    print("")
    print(
        "A case is by-design RED when it carries the marker, is named "
        f"`{PL2_RED_NAME_PREFIX}*`, or says so in its own assertion text "
        f"({' / '.join(PL2_RED_SELF_DESCRIPTIONS[:3])}). Such a case must never be "
        "deselected or xfailed: put it in an inverted job that fails when it goes GREEN."
    )
    return EXIT_OK


def cmd_demote_check(args: argparse.Namespace) -> int:
    paths = _paths_from_args(args)
    before = load_catalogue(Path(args.base).resolve())
    after = load_catalogue(paths.catalogue)
    violations = demotion_violations(before, after, args.message or "")
    for violation in violations:
        print(f"REFUSED: {violation}")
    if violations:
        return EXIT_VIOLATION
    print("no unexplained demotion")
    return EXIT_OK


def _selftest_catalogue(statuses: Mapping[str, str]) -> Catalogue:
    invariants = tuple(
        Invariant(
            mi_id=f"MI{n:02d}",
            statement=f"selftest invariant {n:02d}",
            instantiates="I02",
            mechanism="a selftest mechanism",
            sqlstate=("23514",),
            headline=False,
            owning_migrations=(),
            owning_tests=(),
            status=statuses.get(f"MI{n:02d}", "pending"),
            adr=None,
        )
        for n in range(1, 31)
    )
    return Catalogue(schema_version=1, source="selftest", invariants=invariants)


def _selftest_locator() -> list[tuple[str, bool]]:
    """Prove the locator tells `defined` from `named in a comment` from `absent`.

    The first distinction is the one a promotion rests on: `fn_boundary_project` is named
    four times in the real tree and defined nowhere, every mention being a `--` line in a
    header explaining what the function will do when its band lands. A locator that read
    raw text would report it present, and the promotion it licensed would be false.
    """
    bodies = {
        "0027_doc.sql": strip_sql_comments(
            "-- MI: MI19\n"
            "-- the CHECK fn_boundary_project WILL project onto this table one day\n"
            "CREATE TABLE mainline.doc (\n"
            "  doc_id UUID PRIMARY KEY,\n"
            "  CONSTRAINT no_orphan_controls CHECK (state <> 'superseded' OR n = 0)\n"
            ");"
        ),
        "0115_fn_permit_merge_gate.sql": strip_sql_comments(
            "-- MI: MI22\n"
            "CREATE OR REPLACE FUNCTION mainline.fn_permit_merge_gate() RETURNS TRIGGER AS $$\n"
            "BEGIN RAISE EXCEPTION 'no_orphan_controls is not why'; END; $$ LANGUAGE plpgsql;"
        ),
    }

    def _probe(mi_id: str, mechanism: str, number: str) -> Invariant:
        return Invariant(
            mi_id=mi_id,
            statement="a selftest statement",
            instantiates="I02",
            mechanism=mechanism,
            sqlstate=("23514",),
            headline=False,
            owning_migrations=(number,),
            owning_tests=(),
            status="pending",
            adr=None,
        )

    located = locate_mechanisms(
        Catalogue(
            schema_version=1,
            source="selftest",
            invariants=(
                _probe("MI19", "`CHECK no_orphan_controls`", "0027"),
                _probe("MI06", "`fn_boundary_project` and `fn_permit_merge_gate`", "0115"),
            ),
        ),
        bodies,
    )
    by_name = {obj.name: obj for objs in located.values() for obj in objs}
    return [
        (
            "a CONSTRAINT in executable SQL is located as DEFINED",
            by_name["no_orphan_controls"].state == OBJECT_DEFINED,
        ),
        (
            "an object named ONLY in a `--` comment is ABSENT, not present",
            by_name["fn_boundary_project"].state == OBJECT_ABSENT,
        ),
        (
            "a CREATE FUNCTION is located as DEFINED even when another file only names it",
            by_name["fn_permit_merge_gate"].state == OBJECT_DEFINED,
        ),
        (
            "a `--` inside a string literal is not treated as a comment",
            "'a--b'" in strip_sql_comments("SELECT 'a--b' -- gone\n"),
        ),
        (
            "the mechanism identifier reader ignores prose and reads identifiers",
            mechanism_identifiers("revoked grants + `BEFORE UPDATE/DELETE` trigger") == ()
            and mechanism_identifiers("`CHECK gate_closed_when_issued` + counter trigger")
            == ("gate_closed_when_issued",),
        ),
        (
            "band lookup orders 0049 before 0049a and finds each one's owner",
            _allocation_key("0049") < _allocation_key("0049a")
            and owners_of(
                ("0049", "0049c"),
                (
                    Band(first="0047", last="0049", owner="datamodel/dm-spine"),
                    Band(first="0049a", last="0049z", owner="algorithms"),
                ),
            )
            == ("datamodel/dm-spine (0047-0049)", "algorithms (0049a-0049z)"),
        ),
        (
            "a by-design-RED case is recognised by name, by marker and by its own text",
            all(
                _is_pl2_red(ast.parse(src).body[0])  # type: ignore[arg-type]
                for src in (
                    "def test_pl2_red_a_thing_does_not_exist_yet(): assert False",
                    f"@pytest.mark.{PL2_RED_MARKER}\ndef test_a(): assert False",
                    "def test_b(): assert x, 'RED BY DESIGN (PL-2). Owner: dm-functions'",
                )
            )
            and not _is_pl2_red(ast.parse("def test_ordinary(): assert 1").body[0]),  # type: ignore[arg-type]
        ),
    ]


def cmd_selftest(_args: argparse.Namespace) -> int:
    """Prove both laws bite, with no repository, no cluster and no pytest."""
    catalogue = _selftest_catalogue({"MI02": "enforced"})
    node = "tests/integration/schema/test_selftest.py::test_mi01_thing"
    resolution = {
        inv.mi_id: Witnesses(
            mi_id=inv.mi_id,
            declared=(node,) if inv.mi_id in {"MI01", "MI02"} else (),
            discovered=(),
            unresolved=(),
        )
        for inv in catalogue
    }
    checks: list[tuple[str, bool]] = [
        (
            "the red law fires on a pending invariant whose tests pass",
            len(red_violations(catalogue, resolution, {node: PASSED})) == 1,
        ),
        (
            "the red law is silent when the owning test fails",
            red_violations(catalogue, resolution, {node: FAILED}) == [],
        ),
        (
            "a missing test is not a passing test",
            red_violations(catalogue, resolution, {}) == [],
        ),
        (
            "the green law fires when an enforced invariant regresses",
            any("MI02" in v for v in green_violations(catalogue, resolution, {node: FAILED})),
        ),
        (
            "the green law refuses to certify on a skip",
            any("MI02" in v for v in green_violations(catalogue, resolution, {node: SKIPPED})),
        ),
        (
            "an enforced invariant nothing witnesses is refused",
            any(
                "MI03" in v
                for v in green_violations(
                    _selftest_catalogue({"MI03": "enforced"}), resolution, {node: PASSED}
                )
            ),
        ),
        (
            "an unchanged catalogue provokes no demotion complaint",
            demotion_violations(_selftest_catalogue({"MI02": "enforced"}), catalogue, "fix things")
            == [],
        ),
        (
            "demotion of an enforced invariant without an ADR is refused",
            len(
                demotion_violations(
                    _selftest_catalogue({"MI05": "enforced"}), catalogue, "fix things"
                )
            )
            == 1,
        ),
        (
            "demotion citing an ADR is admitted",
            demotion_violations(
                _selftest_catalogue({"MI05": "enforced"}), catalogue, "revert per ADR-0007"
            )
            == [],
        ),
        (
            "the red law's refusal still opens with the sentence the contract fixes",
            red_violations(catalogue, resolution, {node: PASSED})[0].startswith(
                f"MI01 {RED_VIOLATION_PREFIX}"
            ),
        ),
        (
            "the refusal names the passing tests it was measured over",
            node in red_violations(catalogue, resolution, {node: PASSED})[0],
        ),
        (
            "the refusal names an ABSENT object and says the promotion would be false",
            "ABSENT"
            in red_violations(
                catalogue,
                resolution,
                {node: PASSED},
                objects={
                    "MI01": (
                        MechanismObject(
                            mi_id="MI01",
                            name="a_constraint_that_is_not_there",
                            state=OBJECT_ABSENT,
                            files=(),
                            searched=271,
                        ),
                    )
                },
            )[0],
        ),
        (
            "enriching the refusal changes no verdict: the same invariants refuse either way",
            len(red_violations(catalogue, resolution, {node: PASSED}))
            == len(red_violations(catalogue, resolution, {node: PASSED}, objects={})),
        ),
        *_selftest_locator(),
    ]
    failures = [name for name, held in checks if not held]
    for name, held in checks:
        print(f"{'ok  ' if held else 'FAIL'} {name}")
    if failures:
        print(f"REFUSED: the ratchet does not bite: {failures}")
        return EXIT_VIOLATION
    print(f"selftest: {len(checks)} laws bite")
    return EXIT_OK


# ── CLI ───────────────────────────────────────────────────────────────────────────────


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--catalogue", default=None)
    parser.add_argument("--rendered", default=None)
    parser.add_argument("--lock", default=None)
    parser.add_argument("--migrations", default=None)


def _add_law_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--junit", default=None, help="read outcomes from a JUnit XML pytest wrote")
    parser.add_argument(
        "--pytest-arg", action="append", default=None, help="extra argument passed to pytest"
    )
    parser.add_argument(
        "--on-collect-error-red",
        action="store_true",
        help="treat an uncollectable suite as red instead of refusing to report a colour",
    )
    parser.add_argument(
        "--require-witness",
        action="store_true",
        help="fail when a pending invariant has no owning test at all (intended from K3)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mi_ratchet",
        description="PL-2 red-before-green over the MAINLINE invariant catalogue (DM-8).",
    )
    _add_common(parser)
    parser.set_defaults(handler=cmd_report)
    sub = parser.add_subparsers()

    report = sub.add_parser("report", help="the catalogue, its counts, its witnesses")
    _add_common(report)
    report.set_defaults(handler=cmd_report)

    check = sub.add_parser("check", help="hermetic integrity, projection and currency")
    _add_common(check)
    check.set_defaults(handler=cmd_check)

    reconcile = sub.add_parser("reconcile", help="re-project owning_migrations and re-render")
    _add_common(reconcile)
    reconcile.add_argument("--write", action="store_true")
    reconcile.set_defaults(handler=cmd_reconcile)

    nodeids = sub.add_parser("nodeids", help="the node ids owned by a status")
    _add_common(nodeids)
    nodeids.add_argument("--status", choices=("pending", "enforced", "all"), default="pending")
    nodeids.set_defaults(handler=cmd_nodeids)

    red = sub.add_parser("red", help="the pending law: pending invariants must be red")
    _add_common(red)
    _add_law_args(red)
    red.set_defaults(handler=cmd_red)

    green = sub.add_parser("green", help="the enforced law: enforced invariants must be green")
    _add_common(green)
    _add_law_args(green)
    green.set_defaults(handler=cmd_green)

    pl2_red = sub.add_parser("pl2-red", help="the by-design-RED suites, by file")
    _add_common(pl2_red)
    pl2_red.add_argument("--verbose", action="store_true", help="name every case, not just files")
    pl2_red.set_defaults(handler=cmd_pl2_red)

    demote = sub.add_parser("demote-check", help="refuse an unexplained enforced → pending")
    _add_common(demote)
    demote.add_argument("--base", required=True, help="the catalogue as it is at the merge base")
    demote.add_argument("--message", default="", help="the commit body to search for ADR-NNNN")
    demote.set_defaults(handler=cmd_demote_check)

    selftest = sub.add_parser("selftest", help="prove both laws bite")
    _add_common(selftest)
    selftest.set_defaults(handler=cmd_selftest)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    # The statements are §16's, em dashes and all. A Windows runner whose console is cp1252
    # must not turn a refusal message into a UnicodeEncodeError traceback.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except SourceMissing as exc:
        print(f"CANNOT DETERMINE: {exc}")
        return EXIT_CANNOT_DETERMINE
    except RatchetError as exc:
        print(f"REFUSED: {exc}")
        return EXIT_VIOLATION
    if not isinstance(result, int):  # pragma: no cover - every handler returns an int
        raise RatchetError(f"handler returned {result!r}, not an exit code")
    return result


if __name__ == "__main__":
    sys.exit(main())
