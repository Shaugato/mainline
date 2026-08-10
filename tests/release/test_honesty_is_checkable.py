# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`docs/HONESTY.md` is a checkable document, not a disclaimer.

A disclaimer is prose that nobody can falsify. This repository's distinguishing claim is
that it does not overclaim, and a claim of that shape is worth exactly as much as the
mechanism that would catch it lying. This module is that mechanism.

THE RULE, in one sentence: **every quantity printed in `docs/HONESTY.md` carries an
inline, machine-readable reference to the file under `qa/` or `evidence/` that produced
it, and the value at that reference must be the value printed.**

    Local CockroachDB, DDL plus 5000 vector inserts: 2.4 s
    [src: qa/test-state.json#platform.local_benchmark.seconds]

Four things are enforced, and each one catches a different way a document rots:

* a number with no reference          -> someone wrote a figure from memory
* a reference to a path that is gone  -> the evidence was deleted, the prose was not
* a reference outside qa/ or evidence -> the source is prose, so the number is hearsay
* a reference whose value has moved   -> the tool was re-run and the document was not

The fourth is the one that matters in six months. `qa/ruff-ratchet.json` is regenerated
whenever the lint debt moves; if `HONESTY.md` says the debt is one number and the ratchet
says another, this file goes red and names both.

REFERENCE FAMILIES, AND THE RATCHET THAT RUNS THE OTHER WAY
-----------------------------------------------------------
A fifth failure appeared the moment this repository grew more than one evidence
generator: **the document lags its own evidence.** A wave lands a new artefact, nobody
re-bases the prose, and the page keeps quoting the world as it was. The four rules above
cannot see that, because a stale citation to a still-existing file resolves fine.

So every citable artefact is declared here as a *family* — a glob, a sentence saying what
the family is for, and the keys a file in that family owes this document. Two rules run
off the registry:

* **an undeclared citation is refused.** A number sourced from some corner of `evidence/`
  that nobody registered is a number with no owner.
* **a family that exists on disk must be cited.** :func:`families_landed_but_uncited` is
  the rule that goes red *when new evidence lands*, not when it disappears. If a worker
  writes `evidence/chain/run-<UTC>.json` and `docs/HONESTY.md` does not mention it, this
  file fails and names the family. That is deliberate, and it is the point: the honest
  document is the one that cannot fall behind its own artefacts.

WHAT IS NOT A QUANTITY. Digits inside a code span are **names**: `ap-southeast-2`,
`v26.2.5`, `0121_trg_check_materialised.sql`, SQLSTATE `23514`, a date like `2026-08-10`.
A name is not a measurement and pointing a JSON pointer at one would be theatre. So the
extractor blanks code spans before it looks for numbers, and the document is written so
that anything a skeptic would want to re-derive is a bare number outside backticks.

PL-2, RED BEFORE GREEN. The tests at the bottom of this file plant one of every violation
family into a synthetic document and require the extractor to fire on each — including one
per *reference* family, because a family rule that has only ever been satisfied asserts
nothing about the families it governs. A checker that has never been red asserts nothing
about the document it checks.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.release

# ── locating the artefacts ───────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent


def _repo_root() -> Path:
    for parent in [HERE, *HERE.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "compose.yaml").is_file():
            return parent
    raise RuntimeError(f"cannot locate the repository root above {HERE}")


ROOT = _repo_root()
HONESTY = ROOT / "docs" / "HONESTY.md"
TEST_STATE = ROOT / "qa" / "test-state.json"

#: The only two directories a quantity may be sourced from. `docs/` is deliberately absent:
#: a number whose only source is another document is a number nobody measured.
ALLOWED_ROOTS = ("qa/", "evidence/")

#: The four sections the document must have. Their names are the argument: a reader who
#: skips to one of them learns what kind of statement they are reading before they read it.
REQUIRED_SECTIONS = ("PROVEN", "SYNTHETIC", "NOT YET BUILT", "GEOGRAPHY AND LATENCY")

#: The relations whose consumers were written and whose producer never was. There are
#: SEVEN, and the count is the lesson. A census that classified SQLSTATEs found five,
#: because CockroachDB names only the *first* absent relation in a statement: two views
#: named `mainline_meas.standing` before `mainline_meas.person_measure_policy`, so the
#: second never surfaced in an error string at all. `mainline_ops.site_register_signal`
#: blocked no migration — only a negative RLS assertion — so it was invisible to a chain
#: census too. Naming all seven in the honesty document is not optional, and naming why
#: two of them hid is worth more than the fix.
UNPRODUCED_TABLES = (
    "mainline_ops.outbox",
    "mainline.identity_assignment",
    "mainline.patrol_run",
    "mainline_meas.agent_action",
    "mainline_meas.standing",
    "mainline_meas.person_measure_policy",
    "mainline_ops.site_register_signal",
)

#: The two that a SQLSTATE census could not have seen. The document must not merely list
#: them; it must say why the measurement missed them.
SHADOWED_TABLES = (
    "mainline_meas.person_measure_policy",
    "mainline_ops.site_register_signal",
)

# ── the reference families ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Family:
    """One registered kind of citable artefact.

    `pattern` is matched with :mod:`fnmatch` against the repo-relative POSIX path a
    citation names. `owes` lists dotted pointers every file in the family must carry, so
    that "cite the chain artefact" cannot degrade into "cite a file that happens to sit in
    that directory".
    """

    name: str
    pattern: str
    why: str
    owes: tuple[str, ...] = ()
    cite_when_present: bool = True

    def matches(self, path: str) -> bool:
        return fnmatch.fnmatch(path, self.pattern)

    def on_disk(self, root: Path = ROOT) -> list[Path]:
        return sorted(p for p in root.glob(self.pattern) if p.is_file())


FAMILIES: tuple[Family, ...] = (
    Family(
        name="test-census",
        pattern="qa/test-state.json",
        why="one pytest subprocess per distribution, twice: no cluster and one shared node",
        owes=("totals.none.passed", "totals.cluster.errored", "packages"),
    ),
    Family(
        name="ruff-ratchet",
        pattern="qa/ruff-ratchet.json",
        why="the frozen lint debt, which may fall and may not rise",
        owes=("lint.total", "format.unformatted_files"),
    ),
    Family(
        name="mypy-ratchet",
        pattern="qa/mypy-ratchet.json",
        why="the frozen type-error count and the distributions it was pointed at",
        owes=("total_errors", "source_files_checked"),
    ),
    Family(
        name="gate-refusal",
        pattern="evidence/gate-refusal/proof-*.json",
        why="the product's central claim: refuse, refuse under a forged projection, admit",
        owes=("verdict", "chain.files", "refusal", "drift_refusal", "admission"),
    ),
    Family(
        name="producer-census",
        pattern="evidence/producers/producer-census-*.json",
        why=(
            "the producer-absent lint differenced over the tree — the observed RED that "
            "found seven missing producers where a SQLSTATE census found five"
        ),
        owes=(
            "before.files",
            "before.absent_relations",
            "cli_transcript.before.findings",
            "cli_transcript.after.findings",
        ),
    ),
    Family(
        name="deploy-chain-local",
        pattern="evidence/deploy/chain-*.json",
        why="every migration file executed against the pinned local node, continuing past failures",
        owes=("files", "applied", "failed"),
    ),
    Family(
        name="deploy-chain-cloud",
        pattern="evidence/deploy/cloud-chain.json",
        why="the same chain applied to the CockroachDB Cloud cluster in Singapore",
        owes=("files", "applied", "failed", "chain_seconds"),
    ),
    Family(
        name="chain-run",
        pattern="evidence/chain/*.json",
        why=(
            "the forward-only `trappoint migrate up` record run — the runner a deployment "
            "actually uses, which halts on the first refusal instead of censusing past it"
        ),
        # Shape per `evidence/chain/README.md`: the runner's own counts live under
        # `result`, and `result.complete` is the only field that means "a deployment of
        # this tree would have succeeded" — applied == files AND nothing left dirty.
        owes=("result.files", "result.applied", "result.complete"),
    ),
    Family(
        name="conformance-census",
        pattern="qa/conformance-census.json",
        why="the conformance suite executed to completion, per case, with a reason per cannot-run",
        owes=("totals",),
    ),
)


#: Index by name, so a test can name the family it is exercising rather than a position.
FAMILY_INDEX = {fam.name: index for index, fam in enumerate(FAMILIES)}


def family_for(path: str) -> Family | None:
    for family in FAMILIES:
        if family.matches(path):
            return family
    return None


def families_landed_but_uncited(
    cited: set[str], root: Path = ROOT, families: tuple[Family, ...] = FAMILIES
) -> list[str]:
    """Families with a file on disk that the document cites nothing from.

    This is the rule that fires when *new* evidence lands. Every other rule in this module
    fires when evidence goes missing or moves; none of them can see a document that simply
    never mentioned an artefact that now exists.
    """
    behind: list[str] = []
    for fam in families:
        if not fam.cite_when_present:
            continue
        present = fam.on_disk(root)
        if not present:
            continue
        if any(fam.matches(path) for path in cited):
            continue
        names = ", ".join(p.relative_to(root).as_posix() for p in present[:3])
        behind.append(
            f"family {fam.name!r} has {len(present)} file(s) on disk ({names}) and "
            f"docs/HONESTY.md cites none of them — {fam.why}"
        )
    return behind


# ── the grammar ──────────────────────────────────────────────────────────────────────────

#: `[src: <path>#<pointer>]` or `[src: <path>]`. The pointer is a dotted path into JSON,
#: with integer segments indexing lists, optionally suffixed `|len` (length of a list,
#: dict or string) or `|lines` (non-empty lines of a text file).
REF_RE = re.compile(r"\[src:\s*(?P<path>[^\]\s#]+)(?:#(?P<pointer>[^\]\s]+))?\]")

#: A quantity: an optionally comma-grouped integer or decimal, not glued to a word.
NUMBER_RE = re.compile(r"(?<![\w.$#/=-])(\d[\d,]*(?:\.\d+)?)(?![\w])")

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_CODESPAN_RE = re.compile(r"`[^`]*`")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class Ref:
    """One inline citation."""

    path: str
    pointer: str | None
    raw: str

    @property
    def under_allowed_root(self) -> bool:
        return self.path.startswith(ALLOWED_ROOTS)

    @property
    def family(self) -> Family | None:
        return family_for(self.path)


@dataclass
class Line:
    """One prose line of the document, with its quantities and its citations."""

    number: int
    text: str
    quantities: list[str] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)


def visible_lines(markdown: str) -> list[tuple[int, str]]:
    """Every line that is prose: HTML comments and fenced code blocks removed.

    Line numbers are preserved so a failure message names the line a human can open.
    """
    without_comments = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), markdown)
    out: list[tuple[int, str]] = []
    in_fence = False
    for index, raw in enumerate(without_comments.splitlines(), start=1):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        out.append((index, raw))
    return out


def parse(markdown: str) -> list[Line]:
    """Extract, per line, the quantities claimed and the citations offered for them."""
    parsed: list[Line] = []
    for number, raw in visible_lines(markdown):
        refs = [
            Ref(path=m.group("path"), pointer=m.group("pointer"), raw=m.group(0))
            for m in REF_RE.finditer(raw)
        ]
        # Citations carry paths and pointers full of digits; they are not claims.
        stripped = REF_RE.sub(" ", raw)
        # Code spans are names, not measurements.
        stripped = _CODESPAN_RE.sub(lambda m: " " * len(m.group(0)), stripped)
        quantities = [m.group(1) for m in NUMBER_RE.finditer(stripped)]
        parsed.append(Line(number=number, text=raw, quantities=quantities, refs=refs))
    return parsed


def as_number(token: str) -> float:
    """`5,000` and `5000` are the same quantity; a document may print either."""
    return float(token.replace(",", ""))


def decimals(token: str) -> int:
    return len(token.split(".", 1)[1]) if "." in token else 0


def _descend(value: Any, pointer: str, raw: str) -> Any:
    """Walk a dotted pointer into already-parsed JSON. Integer segments index lists."""
    for segment in [s for s in pointer.split(".") if s]:
        if isinstance(value, list):
            try:
                value = value[int(segment)]
            except (ValueError, IndexError) as exc:
                raise KeyError(f"{raw}: cannot index {segment!r} into a list") from exc
        elif isinstance(value, dict):
            if segment not in value:
                raise KeyError(f"{raw}: {segment!r} is not a key at that depth")
            value = value[segment]
        else:
            raise KeyError(f"{raw}: {segment!r} descends into a scalar")
    return value


def resolve(ref: Ref, root: Path = ROOT) -> Any:
    """Look the cited value up in the cited file. Raises with the reason when it cannot."""
    target = root / ref.path
    if not target.is_file():
        raise FileNotFoundError(f"{ref.raw}: {ref.path} does not exist")
    if ref.pointer is None:
        return None
    pointer, _, modifier = ref.pointer.partition("|")
    if modifier == "lines":
        return len([ln for ln in target.read_text(encoding="utf-8").splitlines() if ln.strip()])
    if target.suffix != ".json":
        raise ValueError(f"{ref.raw}: a dotted pointer needs a JSON file, {ref.path} is not one")
    value = _descend(json.loads(target.read_text(encoding="utf-8")), pointer, ref.raw)
    if modifier == "len":
        try:
            return len(value)
        except TypeError as exc:
            raise ValueError(f"{ref.raw}: |len applied to a scalar") from exc
    if modifier:
        raise ValueError(f"{ref.raw}: unknown modifier |{modifier}")
    return value


def cited_values(line: Line, root: Path = ROOT) -> list[tuple[Ref, float]]:
    """Every numeric value the line's pointers resolve to, with the pointer that found it."""
    found: list[tuple[Ref, float]] = []
    for ref in line.refs:
        if ref.pointer is None:
            continue
        value = resolve(ref, root)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        found.append((ref, float(value)))
    return found


def matches(token: str, value: float) -> bool:
    """A printed token matches a cited value exactly, or as that value rounded to it.

    `2.4` may cite `2.412`: printing three decimals of a benchmark is noise. `2.5` may not.
    """
    printed = as_number(token)
    return printed == value or printed == round(value, decimals(token))


# ── the document ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def markdown() -> str:
    if not HONESTY.is_file():
        pytest.fail(
            f"{HONESTY.relative_to(ROOT).as_posix()} does not exist. "
            "`.github/workflows/claims.yml` already gates on this path."
        )
    return HONESTY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def lines(markdown: str) -> list[Line]:
    return parse(markdown)


def test_the_four_sections_are_present(markdown: str) -> None:
    """A reader must know which kind of statement they are reading before they read it."""
    missing = [name for name in REQUIRED_SECTIONS if f"## {name}" not in markdown]
    assert not missing, f"docs/HONESTY.md is missing section heading(s): {missing}"


def test_every_quantity_carries_a_source_reference(lines: list[Line]) -> None:
    """The rule this file exists for: no number without a citation on the same line."""
    offenders = [
        f"line {line.number}: {line.quantities} with no [src: …] — {line.text.strip()[:110]}"
        for line in lines
        if line.quantities and not line.refs
    ]
    assert not offenders, "uncited quantities in docs/HONESTY.md:\n" + "\n".join(offenders)


def test_every_reference_is_under_qa_or_evidence_and_exists(lines: list[Line]) -> None:
    """A number sourced from prose is hearsay; a number sourced from a deleted file is worse."""
    problems: list[str] = []
    for line in lines:
        for ref in line.refs:
            if not ref.under_allowed_root:
                problems.append(
                    f"line {line.number}: {ref.raw} is not under {' or '.join(ALLOWED_ROOTS)}"
                )
            elif not (ROOT / ref.path).is_file():
                problems.append(f"line {line.number}: {ref.raw} names a file that does not exist")
    assert not problems, "bad source references in docs/HONESTY.md:\n" + "\n".join(problems)


def test_every_pointer_resolves(lines: list[Line]) -> None:
    """A citation that cannot be followed is decoration."""
    problems: list[str] = []
    for line in lines:
        for ref in line.refs:
            if ref.pointer is None:
                continue
            try:
                resolve(ref)
            except (FileNotFoundError, KeyError, ValueError) as exc:
                problems.append(f"line {line.number}: {exc}")
    assert not problems, "unresolvable pointers in docs/HONESTY.md:\n" + "\n".join(problems)


def test_every_quantity_equals_the_value_it_cites(lines: list[Line]) -> None:
    """Coverage AND agreement: each printed number is one a pointer on that line resolves to."""
    problems: list[str] = []
    for line in lines:
        if not line.quantities:
            continue
        try:
            available = cited_values(line)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            problems.append(f"line {line.number}: {exc}")
            continue
        if not available:
            problems.append(
                f"line {line.number}: prints {line.quantities} but no pointer on the line "
                f"resolves to a number — {line.text.strip()[:110]}"
            )
            continue
        for token in line.quantities:
            if not any(matches(token, value) for _, value in available):
                problems.append(
                    f"line {line.number}: prints {token} but its citations resolve to "
                    f"{[value for _, value in available]} — {line.text.strip()[:110]}"
                )
    assert not problems, "quantities that disagree with their source:\n" + "\n".join(problems)


def test_no_citation_is_decorative(lines: list[Line]) -> None:
    """A pointer whose value is nowhere on its line is citing something the line does not say."""
    problems: list[str] = []
    for line in lines:
        try:
            available = cited_values(line)
        except (FileNotFoundError, KeyError, ValueError):
            continue  # reported by test_every_pointer_resolves
        for ref, value in available:
            if not any(matches(token, value) for token in line.quantities):
                problems.append(
                    f"line {line.number}: {ref.raw} resolves to {value}, which the line "
                    f"does not print — {line.text.strip()[:110]}"
                )
    assert not problems, "decorative citations:\n" + "\n".join(problems)


# ── the reference-family rules ───────────────────────────────────────────────────────────


def test_every_reference_belongs_to_a_declared_family(lines: list[Line]) -> None:
    """A citation into an unregistered corner of `evidence/` is a number with no owner.

    Declaring the family here is cheap and forces one sentence about what the artefact is
    for. Skipping it lets a document lean on a file nobody maintains.
    """
    problems = [
        f"line {line.number}: {ref.raw} matches no family in FAMILIES — declare it there, "
        f"with the pointers the document is allowed to lean on"
        for line in lines
        for ref in line.refs
        if ref.family is None
    ]
    assert not problems, "citations outside every declared family:\n" + "\n".join(problems)


def test_every_declared_family_on_disk_keeps_its_shape() -> None:
    """The contract each generator owes this document, checked against what it wrote."""
    problems: list[str] = []
    for fam in FAMILIES:
        for path in fam.on_disk():
            rel = path.relative_to(ROOT).as_posix()
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                problems.append(f"{rel}: not JSON ({exc})")
                continue
            for pointer in fam.owes:
                try:
                    _descend(doc, pointer, rel)
                except KeyError:
                    problems.append(
                        f"{rel}: family {fam.name!r} owes {pointer!r} and the file has no such key"
                    )
    assert not problems, "artefacts that broke their family contract:\n" + "\n".join(problems)


def test_the_document_does_not_lag_a_family_that_landed(lines: list[Line]) -> None:
    """The ratchet that fires when evidence APPEARS.

    Every other rule here fires when an artefact moves or vanishes. This one fires when a
    wave writes a new artefact and nobody re-bases the prose — the failure mode that
    turned "246 of 261 applied" into a sentence this repository quoted for a tree that
    no longer looked like that.
    """
    cited = {ref.path for line in lines for ref in line.refs}
    behind = families_landed_but_uncited(cited)
    assert not behind, (
        "docs/HONESTY.md is behind its own evidence:\n"
        + "\n".join(behind)
        + "\n\nRe-base the document on the artefact, or delete the artefact. A page that "
        "does not mention evidence that exists is a page choosing what to look at."
    )


def test_the_seven_unproduced_tables_are_named(markdown: str) -> None:
    """The largest gap in the tree is named in full, not summarised as "some tables"."""
    missing = [name for name in UNPRODUCED_TABLES if name not in markdown]
    assert not missing, f"docs/HONESTY.md does not name the unproduced table(s): {missing}"


def test_the_document_says_why_two_of_them_were_invisible(markdown: str) -> None:
    """Five was not a smaller problem than seven; it was a smaller measurement.

    CockroachDB reports the *first* absent relation in a statement, so a census built on
    SQLSTATE strings could not have seen `person_measure_policy` behind `standing`. That
    is a limit of the instrument, and a document that prints the corrected count without
    the reason has recorded a fix and thrown away the lesson.
    """
    for name in SHADOWED_TABLES:
        assert name in markdown, f"docs/HONESTY.md does not name the shadowed table {name!r}"
    lowered = markdown.lower()
    assert "first absent relation" in lowered, (
        "docs/HONESTY.md names seven unproduced tables but never says why a SQLSTATE "
        "census found five — the phrase 'first absent relation' is the explanation, and "
        "without it the corrected count reads as a correction rather than as a lesson "
        "about the limits of the measurement"
    )
    assert "evidence/producers/" in markdown, (
        "docs/HONESTY.md must cite the producer census that observed the red"
    )


@pytest.mark.parametrize(
    "fact",
    [
        "ap-southeast-2",
        "ap-southeast-1",
        "Sydney",
        "Singapore",
        "Rerank",
    ],
)
def test_the_geography_split_is_stated(markdown: str, fact: str) -> None:
    """Inference in Australia, database in Singapore, and no Rerank where the inference is."""
    assert fact in markdown, f"docs/HONESTY.md does not mention {fact!r}"


def test_the_census_is_cited_at_all(lines: list[Line]) -> None:
    """The document must lean on the census; adjectives where a count exists are the defect."""
    cited = {ref.path for line in lines for ref in line.refs}
    assert "qa/test-state.json" in cited, (
        "docs/HONESTY.md cites no number from qa/test-state.json — the per-package census is "
        "the most-cited artefact this document has, and a document that omits it is asserting "
        "test state from memory"
    )


def test_the_census_carries_per_package_counts_and_skip_reasons() -> None:
    """The contract `report_test_state.py` owes this document."""
    if not TEST_STATE.is_file():
        pytest.fail("qa/test-state.json does not exist; run scripts/qa/report_test_state.py")
    doc = json.loads(TEST_STATE.read_text(encoding="utf-8"))
    assert doc.get("schema") == "mainline.qa.test-state/1"
    assert doc["packages"], "the census names no packages"
    for name, row in doc["packages"].items():
        assert row["runs"], f"{name} has no runs"
        for pass_name, run in row["runs"].items():
            for key in ("passed", "failed", "errored", "skipped"):
                assert isinstance(run[key], int), f"{name}/{pass_name}: {key} is not an integer"
            for entry in run["skip_reasons"]:
                assert entry["reason"].strip(), (
                    f"{name}/{pass_name}: a skip with an empty reason string. A skip with no "
                    "reason is indistinguishable from a deleted test."
                )
                assert isinstance(entry["count"], int)


# ── PL-2: the checker must be able to go red ─────────────────────────────────────────────
#
# Each of these plants one violation family into a synthetic document and requires the
# corresponding assertion to fire. Without them, every green above could mean "the rule is
# satisfied" or "the rule was never applied", and those are different things.


def _lines(text: str) -> list[Line]:
    return parse(text)


def test_red_an_uncited_number_is_caught() -> None:
    offenders = [ln for ln in _lines("The suite has 4210 passing tests.\n") if ln.quantities]
    assert offenders and not offenders[0].refs


def test_red_a_citation_outside_qa_or_evidence_is_caught() -> None:
    line = _lines("Lint findings: 847 [src: docs/leads/quality-repair.md#lint.total]\n")[0]
    assert line.refs and not line.refs[0].under_allowed_root


def test_red_a_reference_to_a_missing_file_is_caught() -> None:
    line = _lines("Findings: 847 [src: qa/no-such-ratchet.json#lint.total]\n")[0]
    with pytest.raises(FileNotFoundError):
        resolve(line.refs[0])


def test_red_a_pointer_that_does_not_resolve_is_caught() -> None:
    line = _lines("Findings: 847 [src: qa/ruff-ratchet.json#lint.no_such_key]\n")[0]
    with pytest.raises(KeyError):
        resolve(line.refs[0])


def test_red_a_number_that_disagrees_with_its_source_is_caught() -> None:
    line = _lines("Findings: 999999 [src: qa/ruff-ratchet.json#lint.total]\n")[0]
    values = cited_values(line)
    assert values and not any(matches(line.quantities[0], value) for _, value in values)


def test_red_a_decorative_citation_is_caught() -> None:
    line = _lines("The lint debt is published. [src: qa/ruff-ratchet.json#lint.total]\n")[0]
    values = cited_values(line)
    assert values and not any(
        matches(token, value) for token in line.quantities for _, value in values
    )


# ── PL-2 for the reference families ──────────────────────────────────────────────────────
#
# One planted violation per family the producer-completion wave introduced. A family rule
# that has only ever been satisfied asserts nothing about the family it governs.


def test_red_a_citation_into_an_undeclared_family_is_caught() -> None:
    """`evidence/` is not a licence to cite anything under it."""
    line = _lines("Rows written: 12 [src: evidence/scratch/somebodys-notes.json#rows]\n")[0]
    assert line.refs and line.refs[0].under_allowed_root
    assert line.refs[0].family is None, (
        "evidence/scratch/ resolved to a declared family — the undeclared-citation rule "
        "can no longer go red, so it is asserting nothing"
    )


def test_red_a_missing_chain_run_artefact_is_caught() -> None:
    """Family `chain-run`: the forward-only `trappoint migrate up` record."""
    line = _lines("Applied: 271 [src: evidence/chain/no-such-run.json#result.applied]\n")[0]
    assert line.refs[0].family is not None
    assert line.refs[0].family.name == "chain-run"
    with pytest.raises(FileNotFoundError):
        resolve(line.refs[0])


def test_red_a_producer_census_pointer_that_does_not_resolve_is_caught() -> None:
    """Family `producer-census`: the observed RED behind the seven missing producers."""
    line = _lines(
        "Relations with no producer: 7 "
        "[src: evidence/producers/producer-census-before.json#before.no_such_field]\n"
    )[0]
    assert line.refs[0].family is not None and line.refs[0].family.name == "producer-census"
    with pytest.raises(KeyError):
        resolve(line.refs[0])


def test_red_a_producer_census_number_that_disagrees_is_caught() -> None:
    """The same family, and the failure mode that matters: a count that moved."""
    census = ROOT / "evidence" / "producers" / "producer-census-before.json"
    if not census.is_file():
        pytest.skip("evidence/producers/producer-census-before.json is not on disk")
    line = _lines(
        "Relations with no producer: 999 "
        "[src: evidence/producers/producer-census-before.json#before.absent_relations|len]\n"
    )[0]
    values = cited_values(line)
    assert values and not any(matches(line.quantities[0], value) for _, value in values)


def test_red_a_deploy_chain_number_that_disagrees_is_caught() -> None:
    """Family `deploy-chain-local`: the census that says the whole tree applies."""
    candidates = FAMILIES[FAMILY_INDEX["deploy-chain-local"]].on_disk()
    if not candidates:
        pytest.skip("no evidence/deploy/chain-*.json on disk")
    rel = candidates[0].relative_to(ROOT).as_posix()
    line = _lines(f"Applied: 999999 [src: {rel}#applied]\n")[0]
    assert line.refs[0].family is not None and line.refs[0].family.name == "deploy-chain-local"
    values = cited_values(line)
    assert values and not any(matches(line.quantities[0], value) for _, value in values)


def test_red_a_conformance_census_pointer_is_caught_whether_or_not_it_exists() -> None:
    """Family `conformance-census`: absent today, and the rule must bite either way.

    While `qa/conformance-census.json` does not exist, a citation to it must raise
    :class:`FileNotFoundError`. Once it exists, a bogus status key must raise
    :class:`KeyError`. Writing the test for both states means the day the artefact lands
    is not the day this assertion silently stops meaning anything.
    """
    line = _lines("Cases that passed: 3 [src: qa/conformance-census.json#totals.no_such_status]\n")[
        0
    ]
    assert line.refs[0].family is not None
    assert line.refs[0].family.name == "conformance-census"
    landed = (ROOT / "qa" / "conformance-census.json").is_file()
    expected: type[Exception] = KeyError if landed else FileNotFoundError
    with pytest.raises(expected):
        resolve(line.refs[0])


def test_red_a_document_that_ignores_a_landed_family_is_caught() -> None:
    """The appearing-evidence ratchet, with nothing cited at all.

    `families_landed_but_uncited` must name every family that has a file on disk. If this
    returns empty against an empty citation set, the rule cannot fire and the document
    could quietly stop mentioning any artefact it liked.
    """
    behind = families_landed_but_uncited(cited=set())
    on_disk = [fam.name for fam in FAMILIES if fam.cite_when_present and fam.on_disk()]
    assert on_disk, "no declared family has a file on disk; the ratchet governs nothing"
    for name in on_disk:
        assert any(name in message for message in behind), (
            f"family {name!r} has files on disk but the uncited-family rule did not name it"
        )


def test_green_a_correct_line_passes_every_rule() -> None:
    """The complement of the reds above: the same machinery says yes to a true sentence.

    The sentence is built from the census at run time rather than frozen as a literal, so
    the green half cannot rot into a red the moment the suite is re-censused — which would
    make it a test of last Tuesday's numbers rather than of the machinery.
    """
    if not TEST_STATE.is_file():
        pytest.skip("qa/test-state.json does not exist; run scripts/qa/report_test_state.py")
    passed = json.loads(TEST_STATE.read_text(encoding="utf-8"))["totals"]["none"]["passed"]
    line = _lines(f"Passed, no cluster: {passed} [src: qa/test-state.json#totals.none.passed]\n")[0]
    assert line.quantities and line.refs
    assert line.refs[0].under_allowed_root
    assert line.refs[0].family is not None and line.refs[0].family.name == "test-census"
    values = cited_values(line)
    assert values and all(
        any(matches(token, value) for token in line.quantities) for _, value in values
    )


def test_code_spans_are_names_not_quantities() -> None:
    """`v26.2.5` is an identifier. If this stops holding, the rule becomes unwriteable."""
    line = _lines("The node is `CockroachDB v26.2.5` and SQLSTATE `23514` was returned.\n")[0]
    assert line.quantities == []


def test_every_family_name_is_unique_and_every_pattern_is_reachable() -> None:
    """A registry with a shadowed pattern silently mis-attributes citations."""
    names = [fam.name for fam in FAMILIES]
    assert len(names) == len(set(names)), f"duplicate family names in FAMILIES: {names}"
    for index, fam in enumerate(FAMILIES):
        earlier = [other for other in FAMILIES[:index] if other.matches(fam.pattern)]
        assert not earlier, (
            f"family {fam.name!r} is shadowed by {[o.name for o in earlier]}: "
            "family_for() walks FAMILIES in order and would never reach it"
        )
