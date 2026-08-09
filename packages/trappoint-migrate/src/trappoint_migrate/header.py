# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""The mandatory header block, and why a comment is load-bearing here.

Every migration file carries four keys in its **leading comment block**::

    -- MI: MI01, MI17
    -- I: I01
    -- COUNSEL-GATED: no
    -- RATIONALE: <prose, wrapped, saying why this statement is written this way>

`ARCHITECTURE.md` §18 requires the citation; `docs/leads/datamodel.md` DM-8 makes the
citation checkable by resolving it against a *registry* rather than against a reader's
memory; DM-17 adds ``COUNSEL-GATED`` so that the five files whose shape depends on a
legal answer are addressable as a set rather than as a recollection.

**Why the block is enforced by a linter and not by a convention.** The catalogue
(``verticals/mainline/db/invariants/mi_catalogue.yaml``) says which invariants exist and
what enforces each one, and ``scripts/mi_ratchet.py`` *projects* ``owning_migrations``
out of these very headers — the same P2 discipline the schema applies to itself. A
projection is only as good as its source, so a header that cites ``MI31`` (an invariant
§16 does not contain) or omits ``MI:`` altogether does not produce a wrong number in a
report; it produces a **refusal here**, before the number is ever computed.

Three deliberate scoping decisions, each of which is a claim about correctness rather
than about taste:

* **The window is the leading comment block**, computed by
  :func:`trappoint_migrate.sqltext.header_comment`, not "the first N characters". A key
  found after the first statement is not a header, and a rule whose window can be
  widened by adding SQL is a rule that erodes. Measured on 2026-08-10: all 261 MAINLINE
  migrations and all 109 reference-vertical files satisfy the stricter reading.
* **The MI registry is resolved per tree**, exactly like ``lint``'s allocation: the
  catalogue governing ``<vertical>/db/migrations`` is ``<vertical>/db/invariants/
  mi_catalogue.yaml``. A tree with no catalogue (the reference vertical, template
  sources) is checked for *presence and shape* and not for membership — silence, not an
  invented registry.
* **The catalogue is read with a regex, not with a YAML parser.** This module is on the
  path of ``trappoint migrate lint``, which ``ci.yml``'s repository-wide sequence-ban job
  runs with **only** ``trappoint-migrate`` installed. Adding PyYAML to that path to read
  thirty identifiers out of a generated file would make the sequence ban depend on a
  parser it has no other use for. The identifier lines are emitted by
  ``scripts/mi_ratchet.py reconcile`` and are asserted byte-identical by
  ``mi_ratchet.py check``, so their shape is machine-guaranteed rather than assumed.

**What is NOT enforced by default, and why the exception is written down rather than
quietly taken.** ``I:`` cites TRAPPOINT's SemVer'd public invariants, ``I01`` to ``I16``.
Two files in this repository — ``0049y_meas_mutation_run.sql`` and
``0049z_meas_mutation_result.sql``, owned by another domain — cite ``I17``, which does
not exist. That is a real defect and :func:`header_findings` reports it under
``header-unknown-trappoint-invariant``, but only when *strict_trappoint_ids* is set. It
is off by default because turning it on would make ``ci.yml``'s repository-wide lint red
for a file this worker does not own, and changing another lane's colour is a decision for
that lane's owner, not a side effect of landing a linter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .lint import Finding
from .sqltext import header_comment

__all__ = [
    "CATALOGUE_RELPATH",
    "HEADER_KEYS",
    "TRAPPOINT_INVARIANT_IDS",
    "Header",
    "catalogue_ids",
    "find_catalogue",
    "header_findings",
    "parse_header",
]

#: The four keys, in the order a reader meets them. Order is not enforced — a header
#: that answers all four questions has answered them — but it is the order every file in
#: the repository uses and the order the templates emit.
HEADER_KEYS: tuple[str, ...] = ("MI", "I", "COUNSEL-GATED", "RATIONALE")

#: TRAPPOINT's SemVer'd public invariants. MAINLINE's schema invariants are ``MI*``; the
#: renumbering exists precisely so that these two sets cannot be confused.
TRAPPOINT_INVARIANT_IDS: frozenset[str] = frozenset(f"I{n:02d}" for n in range(1, 17))

#: Where a migration tree's invariant registry lives, relative to the tree's parent.
CATALOGUE_RELPATH: tuple[str, ...] = ("invariants", "mi_catalogue.yaml")

_KEY_RE: dict[str, re.Pattern[str]] = {
    key: re.compile(rf"^--[ \t]*{re.escape(key)}:[ \t]*(?P<value>.*)$", re.MULTILINE)
    for key in HEADER_KEYS
}
_MI_TOKEN = re.compile(r"\bMI\d{2}\b")
_TRAPPOINT_TOKEN = re.compile(r"\bI\d{2}\b")
_CATALOGUE_ID = re.compile(r"^\s*-\s+id:\s*(?P<id>MI\d{2})\s*$")
#: A top-level key in the catalogue, at column zero. Used to bound the ``invariants:``
#: block, because the file's other top-level block — ``proposed:`` — carries ``id:``
#: lines too and an id in it is emphatically **not** adopted.
_CATALOGUE_TOP_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:")
_CATALOGUE_ADOPTED_BLOCK = "invariants:"
_COUNSEL_VALUES = ("yes", "no")

#: A rationale shorter than this is a placeholder. The threshold matches the one
#: `scripts/mi_ratchet.py` applies to `statement` and `mechanism`, so "too short to be a
#: decision" means the same number of characters in both places.
_MIN_RATIONALE = 8

#: Keys a *downstream consumer* reads as a single line, so a second occurrence is a
#: refusal even when the two agree. ``scripts/mi_ratchet.py`` refuses a file carrying
#: anything but exactly one ``-- MI:`` line, and ``owning_migrations`` is projected from
#: it; a rule here that were laxer than the consumer would let a tree past the linter
#: that the ratchet then rejects, which is the worst possible division of labour.
_EXACTLY_ONCE: frozenset[str] = frozenset({"MI", "I", "RATIONALE"})

# COUNSEL-GATED is deliberately NOT in that set. DM-17 mandates the long form on the
# counsel-gated files —
#     -- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
# — and several of those files also carry the bare `-- COUNSEL-GATED: yes` summary line
# in the key block at the top, where a reader scanning four keys expects to find it. Two
# lines that give the SAME answer are redundancy, not ambiguity, and refusing them would
# be refusing the shape the ruling asked for. Two that give DIFFERENT answers are the
# actual failure, and that is what `header-conflicting-key` refuses.


@dataclass(frozen=True, slots=True)
class Header:
    """One file's header block, parsed. Absent keys are absent, never defaulted.

    Defaulting a missing key is how a linter starts reporting on a header that was never
    written: ``counsel_gated=False`` for a file with no ``COUNSEL-GATED:`` line would
    read, downstream, as an affirmative "this file is not counsel-gated".
    """

    block: str
    """The leading comment block the keys were read from, verbatim."""
    values: dict[str, str]
    """Key → the text after the colon on its first line, stripped."""
    occurrences: dict[str, list[str]]
    """Key → every value it was given, in order. Zero is a missing key; more than one is
    a finding for the keys in :data:`_EXACTLY_ONCE`, and a finding for any key whose
    repeated values disagree."""
    mi_ids: tuple[str, ...]
    """``MInn`` tokens on the ``MI:`` line, de-duplicated, in first-appearance order."""
    trappoint_ids: tuple[str, ...]
    """``Inn`` tokens on the ``I:`` line, de-duplicated, in first-appearance order."""

    @property
    def counsel_gated(self) -> bool | None:
        """True/False from the ``COUNSEL-GATED:`` line; None when absent or unreadable.

        None is the honest third answer and it is why this is not a plain ``bool``. A
        file whose header omits the key has not said "no"; it has said nothing, and the
        manifest records ``null`` rather than manufacturing a claim about counsel.

        When the key appears more than once and the occurrences disagree, this is also
        None — an ambiguous answer is not an answer — and
        :func:`header_findings` reports it as ``header-conflicting-key``.
        """
        answers = {_counsel_answer(raw) for raw in self.occurrences.get("COUNSEL-GATED", [])}
        if len(answers) != 1:
            return None
        return answers.pop()

    @property
    def rationale(self) -> str:
        """The ``RATIONALE:`` text, with continuation lines joined into one paragraph.

        A rationale is wrapped across ``--`` continuation lines in every file in the
        tree, so reading only the first line would make a two-line rationale look like a
        truncated one.
        """
        return _rationale_text(self.block)


def _counsel_answer(raw: str) -> bool | None:
    """``yes``/``no`` from a ``COUNSEL-GATED:`` value's first word, else None.

    The first word only, because DM-17's mandated long form continues past it:
    ``yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md``.
    """
    stripped = raw.strip()
    if not stripped:
        return None
    first = stripped.split()[0].lower()
    if first in _COUNSEL_VALUES:
        return first == "yes"
    return None


def _dedupe(tokens: list[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for token in tokens:
        seen.setdefault(token, None)
    return tuple(seen)


def _rationale_text(block: str) -> str:
    """Join the ``RATIONALE:`` line with every ``--`` continuation line that follows."""
    lines = block.splitlines()
    collected: list[str] = []
    started = False
    for line in lines:
        match = _KEY_RE["RATIONALE"].match(line)
        if match is not None:
            started = True
            collected.append(match.group("value").strip())
            continue
        if not started:
            continue
        stripped = line.strip()
        if not stripped.startswith("--"):
            break
        body = stripped[2:].strip()
        # A blank comment line ends the paragraph; a new `-- KEY:` line ends it too.
        if not body or any(pattern.match(line) is not None for pattern in _KEY_RE.values()):
            break
        if body.startswith("@"):
            break
        collected.append(body)
    return " ".join(part for part in collected if part).strip()


def parse_header(sql: str) -> Header:
    """Parse the leading comment block of *sql* into a :class:`Header`.

    Never raises. A file with no comment at all yields a header with no values and no
    occurrences, and :func:`header_findings` is what turns that into four refusals — so
    that a caller which only wants to *read* a header (the lock-file generator) is not
    forced to catch exceptions for files the linter will condemn anyway.
    """
    block = header_comment(sql)
    values: dict[str, str] = {}
    occurrences: dict[str, list[str]] = {}
    for key, pattern in _KEY_RE.items():
        matches = [str(match).strip() for match in pattern.findall(block)]
        occurrences[key] = matches
        if matches:
            values[key] = matches[0]
    return Header(
        block=block,
        values=values,
        occurrences=occurrences,
        mi_ids=_dedupe(_MI_TOKEN.findall(values.get("MI", ""))),
        trappoint_ids=_dedupe(_TRAPPOINT_TOKEN.findall(values.get("I", ""))),
    )


def find_catalogue(root: Path) -> Path | None:
    """Return the invariant registry governing the migration tree *root*, or None.

    ``<vertical>/db/migrations`` → ``<vertical>/db/invariants/mi_catalogue.yaml``. None
    is not an error: the reference vertical and the template directory have no catalogue,
    and membership is not checked there rather than being checked against an invented one.
    """
    directory = root if root.is_dir() else root.parent
    candidate = directory.parent.joinpath(*CATALOGUE_RELPATH)
    return candidate if candidate.is_file() else None


def catalogue_ids(path: Path) -> frozenset[str]:
    """Return every ``MInn`` identifier the catalogue at *path* has **adopted**.

    Adopted, not merely mentioned. The catalogue has two top-level blocks and only one of
    them is a registry: ``invariants:`` holds what §16 contains, and ``proposed:`` holds
    what a migration header has *asked* for and the architecture has not adopted (``MI31``
    today, proposed by migration ``0041``). Counting a proposal as adopted would make this
    function certify exactly the citation ``scripts/mi_ratchet.py`` exists to refuse —
    "§16 is amended by an ADR, not by a header comment" — so the scan is bounded to the
    ``invariants:`` block and stops at the next column-zero key.

    Read with a regex rather than with a YAML parser, for the dependency reason set out
    in this module's docstring. The lines are emitted by
    ``scripts/mi_ratchet.py reconcile`` and asserted byte-identical by its ``check``
    subcommand, so their shape is machine-guaranteed rather than assumed.

    Returns an empty set when the file exists but adopts nothing — which
    :func:`header_findings` treats as "no registry", never as "no invariant is valid".
    """
    found: set[str] = set()
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if _CATALOGUE_TOP_KEY.match(line) is not None:
            inside = line.startswith(_CATALOGUE_ADOPTED_BLOCK)
            continue
        if not inside:
            continue
        match = _CATALOGUE_ID.match(line)
        if match is not None:
            found.add(match.group("id"))
    return frozenset(found)


def _line_of_key(block: str, key: str, fallback: int = 1) -> int:
    """1-based line number of *key* within *block*, or *fallback* when it is absent."""
    for index, line in enumerate(block.splitlines(), start=1):
        if _KEY_RE[key].match(line) is not None:
            return index
    return fallback


def header_findings(  # noqa: PLR0912 - one branch per rule; a table would hide which
    path: Path,
    sql: str,
    *,
    known_mi_ids: frozenset[str] | None = None,
    strict_trappoint_ids: bool = False,
) -> list[Finding]:
    """Return every header refusal for one file, most-structural first.

    *known_mi_ids* is the registry the ``MI:`` line is resolved against. None means the
    tree declares no registry and membership is not checked — presence and shape still
    are.

    *strict_trappoint_ids* additionally refuses an ``Inn`` outside ``I01`` to ``I16``. Off
    by default; see this module's docstring for the exception and why it is written down.

    Rules, and the failure each one prevents:

    * ``header-missing-key`` — a file that cites nothing cannot be attributed to an
      invariant, so ``owning_migrations`` would silently under-report what is enforced.
    * ``header-duplicate-key`` — two ``MI:`` lines make "the file's claim" ambiguous, and
      ``scripts/mi_ratchet.py`` reads exactly one.
    * ``header-no-invariant`` — an empty ``MI:`` line satisfies a presence check while
      citing nothing; it is the shape a placeholder takes.
    * ``header-unknown-invariant`` — a comment cannot amend a numbered catalogue.
    * ``header-counsel-gated-value`` — DM-17's five files are addressable only if the
      value is one of two words.
    * ``header-empty-rationale`` — the rationale is what a reviewer reads instead of
      re-deriving the decision; a blank one is worse than no key, because it looks answered.
    """
    findings: list[Finding] = []
    header = parse_header(sql)

    for key in HEADER_KEYS:
        seen = header.occurrences.get(key, [])
        if not seen:
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    rule="header-missing-key",
                    detail=(
                        f"the leading comment block carries no '-- {key}:' line. The four "
                        f"keys {list(HEADER_KEYS)} are mandatory (ARCHITECTURE.md §18, "
                        "docs/leads/datamodel.md DM-8 and DM-17): the citation is projected "
                        "into the invariant catalogue, and a projection over a missing "
                        "source refuses rather than reporting that nothing enforces anything."
                    ),
                )
            )
        elif len(seen) > 1 and key in _EXACTLY_ONCE:
            findings.append(
                Finding(
                    path=path,
                    line=_line_of_key(header.block, key),
                    rule="header-duplicate-key",
                    detail=(
                        f"{len(seen)} '-- {key}:' lines in one header. This key is read as a "
                        "single line by scripts/mi_ratchet.py, which projects "
                        "owning_migrations out of it and refuses a file carrying anything "
                        "but exactly one — a linter laxer than its consumer lets a tree past "
                        "that the consumer then rejects."
                    ),
                )
            )
        elif (
            key == "COUNSEL-GATED"
            and len(seen) > 1
            and len({_counsel_answer(value) for value in seen}) > 1
        ):
            findings.append(
                Finding(
                    path=path,
                    line=_line_of_key(header.block, key),
                    rule="header-conflicting-key",
                    detail=(
                        f"the header answers '-- {key}:' more than once and the answers "
                        f"disagree: {seen}. Repeating the key is legitimate — DM-17 mandates "
                        "the long 'yes (G0) · DEFAULT: … · ADR: …' form beside the short "
                        "summary — but two different answers make the counsel-gated set "
                        "un-addressable, which is the whole thing the key exists for."
                    ),
                )
            )

    if len(header.occurrences.get("MI", [])) == 1 and not header.mi_ids:
        findings.append(
            Finding(
                path=path,
                line=_line_of_key(header.block, "MI"),
                rule="header-no-invariant",
                detail=(
                    "the '-- MI:' line names no MInn identifier. An empty citation passes a "
                    "presence check while asserting nothing, which is exactly the shape a "
                    "placeholder takes."
                ),
            )
        )

    if known_mi_ids is not None:
        for mi_id in header.mi_ids:
            if mi_id not in known_mi_ids:
                findings.append(
                    Finding(
                        path=path,
                        line=_line_of_key(header.block, "MI"),
                        rule="header-unknown-invariant",
                        detail=(
                            f"the '-- MI:' line cites {mi_id}, which the invariant catalogue "
                            "for this tree does not hold. §16 is amended by an ADR, not by a "
                            "header comment: adopt the invariant in mi_catalogue.yaml, or "
                            "record the ask in its `proposed:` block and cite an adopted id "
                            "here."
                        ),
                    )
                )

    if strict_trappoint_ids:
        for token in header.trappoint_ids:
            if token not in TRAPPOINT_INVARIANT_IDS:
                findings.append(
                    Finding(
                        path=path,
                        line=_line_of_key(header.block, "I"),
                        rule="header-unknown-trappoint-invariant",
                        detail=(
                            f"the '-- I:' line cites {token}; TRAPPOINT's public invariants "
                            "are I01-I16 and the set is SemVer'd. An identifier outside it "
                            "names a promise the substrate has not made."
                        ),
                    )
                )

    if (
        len({_counsel_answer(v) for v in header.occurrences.get("COUNSEL-GATED", [])}) == 1
        and header.counsel_gated is None
    ):
        findings.append(
            Finding(
                path=path,
                line=_line_of_key(header.block, "COUNSEL-GATED"),
                rule="header-counsel-gated-value",
                detail=(
                    f"'-- COUNSEL-GATED: {header.values.get('COUNSEL-GATED', '')}' does not "
                    f"begin with one of {list(_COUNSEL_VALUES)}. DM-17's counsel-gated set has "
                    "to be addressable as a set — a free-text answer makes it a search."
                ),
            )
        )

    rationale_lines = len(header.occurrences.get("RATIONALE", []))
    if rationale_lines == 1 and len(header.rationale) < _MIN_RATIONALE:
        findings.append(
            Finding(
                path=path,
                line=_line_of_key(header.block, "RATIONALE"),
                rule="header-empty-rationale",
                detail=(
                    "the '-- RATIONALE:' line carries no prose. The rationale is what a "
                    "reviewer reads instead of re-deriving the decision from the DDL; an "
                    "empty one is worse than a missing key, because it looks answered."
                ),
            )
        )

    return findings
