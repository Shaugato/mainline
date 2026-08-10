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

WHAT IS NOT A QUANTITY. Digits inside a code span are **names**: `ap-southeast-2`,
`v26.2.5`, `0121_trg_check_materialised.sql`, SQLSTATE `23514`, a date like `2026-08-10`.
A name is not a measurement and pointing a JSON pointer at one would be theatre. So the
extractor blanks code spans before it looks for numbers, and the document is written so
that anything a skeptic would want to re-derive is a bare number outside backticks.

PL-2, RED BEFORE GREEN. Six tests at the bottom of this file plant one of every violation
family into a synthetic document and require the extractor to fire on each. A checker that
has never been red asserts nothing about the document it checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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

#: The five tables whose consumers were written and whose producer never was. Naming them
#: in the honesty document is not optional; they are the largest single gap in the tree.
UNPRODUCED_TABLES = (
    "mainline_ops.outbox",
    "mainline.identity_assignment",
    "mainline.patrol_run",
    "mainline_meas.agent_action",
    "mainline_meas.standing",
)

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


@dataclass
class Line:
    """One prose line of the document, with its quantities and its citations."""

    number: int
    text: str
    quantities: list[str]
    refs: list[Ref]


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


def test_the_five_unproduced_tables_are_named(markdown: str) -> None:
    """The largest gap in the tree is named in full, not summarised as "some tables"."""
    missing = [name for name in UNPRODUCED_TABLES if name not in markdown]
    assert not missing, f"docs/HONESTY.md does not name the unproduced table(s): {missing}"


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


def test_green_a_correct_line_passes_every_rule() -> None:
    """The complement of the six above: the same machinery says yes to a true sentence.

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
    values = cited_values(line)
    assert values and all(
        any(matches(token, value) for token in line.quantities) for _, value in values
    )


def test_code_spans_are_names_not_quantities() -> None:
    """`v26.2.5` is an identifier. If this stops holding, the rule becomes unwriteable."""
    line = _lines("The node is `CockroachDB v26.2.5` and SQLSTATE `23514` was returned.\n")[0]
    assert line.quantities == []
