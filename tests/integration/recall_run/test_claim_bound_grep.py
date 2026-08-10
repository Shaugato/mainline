# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The CI grep behind the one sentence that keeps PER honest.

    PER proves exhaustion of the retrieval that ran, not of the corpus.

C-SPANN is approximate and its trees mutate on every insert, so the strongest true statement
about a silence receipt is a statement about the *retrieval*, never about the corpus. The
recall lead's plan (section 4) requires that sentence to travel with the mechanism, and the
wire specification requires it as a field on every receipt. **A proof that overclaims is worse
than none** — an overclaiming receipt is not a weaker exhibit, it is an exhibit the other side
gets to destroy in front of the jury.

Two rings, because ownership is not uniform
-------------------------------------------
**Strict ring — verbatim.** The artefacts this domain owns: ``spec/wire/candidate-commitment
.md``, ``packages/trappoint-recall/``, the recall agent, and this test tree. Here the string
must appear byte for byte, because these are where the claim is *defined* and a definition
that drifts from its own constant is a definition nobody can rely on.

**Wide ring — semantic.** Everywhere else in the repository. Other domains render the claim in
their own medium — a TypeScript doc comment shouting the emphasis in capitals is still the same
claim — so the wide ring normalises case, whitespace and markdown emphasis and then requires
the *claim itself* to be unchanged. It catches the realistic failure, which is not deletion of
the caveat but a rewrite of it: ``not of the corpus`` quietly becoming ``of the corpus``, or the
subject sliding from the retrieval to the fonds.

Making the wide ring strict would have this suite fail on another domain's file, which is a
build break rather than a finding. The verbatim gap in the console is reported to that domain
instead; this test asserts what it is entitled to assert, and says which is which.

Artefacts that do not exist yet, or that make no PER claim at all, are reported as **skips with
a reason**, never as passes. The bound is owed wherever the claim is made.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trappoint_recall.per.errors import ExhaustionOverclaim
from trappoint_recall.per.leaf import CandidateScore
from trappoint_recall.per.receipt import PER_BOUND_SENTENCE, build_receipt
from trappoint_recall.per.verify import verify_receipt

REPO_ROOT = Path(__file__).resolve().parents[3]

SPEC = REPO_ROOT / "spec" / "wire" / "candidate-commitment.md"

#: The strict ring: paths whose contents this domain owns and may hold to the byte.
STRICT_RING: tuple[Path, ...] = (
    REPO_ROOT / "spec" / "wire",
    REPO_ROOT / "packages" / "trappoint-recall",
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent",
)

#: Dispatch records rather than artefacts: the worker briefs quote the requirement in prose
#: while describing it, which is not the same act as making the claim to a reader.
EXCLUDED_FROM_THE_GREP: tuple[Path, ...] = (
    REPO_ROOT / "docs" / "leads",
    Path(__file__).resolve(),
)

#: Artefacts other domains own that must carry the bound once they make the claim in prose.
DOWNSTREAM_CLAIMANTS: tuple[tuple[str, Path], ...] = (
    ("the repository README", REPO_ROOT / "README.md"),
)

#: What making the claim looks like in prose. A generated type name or a column called
#: ``candidate_root`` is not a claim about what the proof establishes.
_CLAIMS_PER = re.compile(r"Proof of Exhausted Recall")

#: The anchor the wide ring greps for. Everything after it must be the sanctioned claim.
_ANCHOR = "proves exhaustion"

#: The claim itself, minus the trailing full stop, so a sentence that continues with an em
#: dash or a closing quote is judged on its content rather than on its punctuation.
_CLAIM_TAIL = PER_BOUND_SENTENCE.split(_ANCHOR, 1)[1].rstrip(".")

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "evidence",
        "research",
        "htmlcov",
        "dist",
        "build",
    }
)

_TEXT_SUFFIXES = frozenset(
    {".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".sql", ".ts", ".tsx", ".rst"}
)

_EMPHASIS = re.compile(r"[*_`\\]+")
_WHITESPACE = re.compile(r"\s+")

#: What a medium puts at the START of a wrapped line and a reader never hears: `--` in
#: SQL, `//` in the C family, `#` in shell and Python, `>` in a markdown blockquote, `;`
#: in an ini file, `*` in a javadoc block. Anchored to a line start with ``(?m)``, so it
#: can only ever remove a continuation marker — never a word, never a comma, never the
#: `not` whose loss is the whole point of this file.
_LINE_LEAD = re.compile(r"(?m)^[ \t]*(?:--+|//+|;+|#+|>+|\*+)[ \t]*")

#: The seam a source language leaves when one sentence is split across two string
#: literals: ``'… of the ' +`` / ``+ 'retrieval …'``. The quotes and the operator belong
#: to TypeScript, JavaScript or Python; they are not part of the claim.
_CONCAT_SEAM = re.compile(r"['\"]\s*\+\s*['\"]")


def normalise(fragment: str) -> str:
    """Fold away case, whitespace, emphasis and line scaffolding — never a word.

    WHY THE SCAFFOLDING IS FOLDED, AND WHY THAT IS NOT A WIDENING. On 2026-08-10 this
    ring reported four offenders, and all four made the sanctioned claim exactly:

        0160_v_silence_summary.sql   `… of the retrieval\\n--    that ran, not of the corpus`
        console/src/verify/ledger.ts `… of the ' +\\n  'retrieval that ran, not of the corpus.'`
        …/verify/silenceroot.ts      `… of the RETRIEVAL THAT RAN, ' +\\n 'not of the corpus.'`
        console/docs/in-browser-….md `… of the\\n> retrieval that ran, not of the corpus.**`

    The claim had not drifted. The *instrument* was folding wrapping only for media
    where wrapping is free, so a claim reproduced faithfully in SQL, TypeScript or a
    blockquote was reported as a rewrite. That is the worst failure a checker of this
    kind can have: four false accusations teach a reader that its accusations are noise,
    and the fifth one — a real rewrite — is then read as more noise.

    Nothing here relaxes the claim. The folds are strictly punctuation a language emits
    at a line boundary; every word, every comma and the ordering are still required
    verbatim by the caller, and `test_red_*` below plants the rewrites that matter in
    each of these media and requires this function to keep catching them.
    """
    without_seams = _CONCAT_SEAM.sub("", fragment)
    without_leads = _LINE_LEAD.sub("", without_seams)
    return _WHITESPACE.sub(" ", _EMPHASIS.sub("", without_leads)).casefold().strip()


def _text_files() -> list[Path]:
    """Every text file worth grepping, excluding caches, vendored trees and dispatch records."""
    excluded = tuple(EXCLUDED_FROM_THE_GREP)
    found: list[Path] = []
    stack = [REPO_ROOT]
    while stack:
        directory = stack.pop()
        for entry in directory.iterdir():
            if entry.is_dir():
                if entry.name not in _SKIP_DIRS and entry not in excluded:
                    stack.append(entry)
            elif entry.suffix in _TEXT_SUFFIXES and entry not in excluded:
                found.append(entry)
    return found


def _read(path: Path) -> str | None:
    """Read a text file, or return ``None`` if it is not decodable UTF-8."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _in_strict_ring(path: Path) -> bool:
    """Whether this domain owns ``path`` and may hold it to the byte."""
    return any(path.is_relative_to(root) for root in STRICT_RING)


def _occurrences(text: str) -> list[str]:
    """Every claim fragment in ``text``: the anchor plus what follows it, generously bounded."""
    reach = len(_CLAIM_TAIL) + 24
    lowered = text.casefold()
    out: list[str] = []
    start = 0
    while (found := lowered.find(_ANCHOR, start)) != -1:
        out.append(text[found : found + len(_ANCHOR) + reach])
        start = found + len(_ANCHOR)
    return out


def _receipt():
    """A small receipt whose ``theta`` sits between two candidates."""
    receipt, _leaves = build_receipt(
        [
            CandidateScore(
                event_id="11111111-1111-4111-8111-111111111111",
                p_relevant=0.90,
                tau_applied=0.45,
                outcome="blocking",
            ),
            CandidateScore(
                event_id="22222222-2222-4222-8222-222222222222",
                p_relevant=0.10,
                tau_applied=0.45,
                outcome="silenced",
            ),
        ],
        run_id="33333333-3333-4333-8333-333333333333",
        permit_id="44444444-4444-4444-8444-444444444444",
        policy_version="recall/2026.08.08",
        index_generation="gen-1",
        corpus_root=bytes(32),
        certificate_verdict="partial",
    )
    return receipt


def test_the_specification_carries_the_sentence_verbatim() -> None:
    """Identity, not similarity: the document and the constant are the same bytes."""
    text = _read(SPEC)
    assert text is not None, f"{SPEC} is the normative wire format and must be readable"
    assert PER_BOUND_SENTENCE in text, (
        f"{SPEC} must reproduce PER_BOUND_SENTENCE verbatim. A change to its wording is a "
        "change to what the product claims and requires an ADR."
    )


def test_every_receipt_carries_the_bound_on_its_face() -> None:
    """The caveat is a field, not a footnote — it travels with the exhibit."""
    assert _receipt().to_json()["claim_bound"] == PER_BOUND_SENTENCE


def test_every_verifier_report_carries_the_bound() -> None:
    """Whoever checks the proof is told what it proves, in both output shapes."""
    report = verify_receipt(_receipt().to_json())
    assert report.ok, report.to_text()
    assert report.to_json()["claim_bound"] == PER_BOUND_SENTENCE
    assert PER_BOUND_SENTENCE in report.to_text()


def test_the_undetermined_refusal_quotes_the_bound() -> None:
    """The refusal that blocks an exhaustion claim explains itself in the same words."""
    with pytest.raises(ExhaustionOverclaim) as caught:
        build_receipt(
            [],
            run_id="33333333-3333-4333-8333-333333333333",
            permit_id="44444444-4444-4444-8444-444444444444",
            policy_version="recall/2026.08.08",
            index_generation="gen-1",
            corpus_root=bytes(32),
            certificate_verdict="UNDETERMINED",
        )
    assert PER_BOUND_SENTENCE in str(caught.value)


def test_the_strict_ring_carries_the_sentence_byte_for_byte() -> None:
    """Where this domain owns the file, the claim is the constant and nothing adjacent to it."""
    offenders: list[str] = []
    for path in _text_files():
        if not _in_strict_ring(path):
            continue
        text = _read(path)
        if text is None:
            continue
        for fragment in _occurrences(text):
            if PER_BOUND_SENTENCE not in text or _ANCHOR not in fragment:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {fragment.strip()!r}")
                continue
            claim = fragment.split(_ANCHOR, 1)[1]
            if not claim.startswith(_CLAIM_TAIL):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {fragment.strip()!r}")
    assert not offenders, (
        "inside the recall domain the sentence is reproduced verbatim or not at all:\n"
        + "\n".join(offenders)
    )


def claim_holds(fragment: str) -> bool:
    """Whether one ``proves exhaustion …`` fragment makes the sanctioned claim.

    One definition, used by the wide ring and by every planted rewrite below, so that a
    relaxation of the ring is necessarily a relaxation the reds see too.
    """
    tail = fragment.casefold().split(_ANCHOR, 1)[1]
    return normalise(tail).startswith(normalise(_CLAIM_TAIL))


def test_the_wide_ring_holds_the_claim_unchanged() -> None:
    """Everywhere else: emphasis and wrapping may differ, the claim may not."""
    offenders: list[str] = []
    for path in _text_files():
        text = _read(path)
        if text is None:
            continue
        for fragment in _occurrences(text):
            if not claim_holds(fragment):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {fragment.strip()!r}")
    assert not offenders, (
        "every statement built on 'proves exhaustion' must make the sanctioned claim. These "
        "make a different one, which is the failure mode that matters — nobody deletes the "
        "caveat, somebody rewrites it:\n" + "\n".join(offenders)
    )


# ── PL-2 for the normaliser: the folds must not have bought the green ────────────────────
#
# `normalise` was widened on 2026-08-10 to fold line-continuation scaffolding, because four
# faithful renderings were being reported as rewrites. A fold is exactly the move that could
# also let a real rewrite through, so each medium now carries both halves: the true claim as
# that medium actually writes it, and the rewrite that matters written the same way.

#: The four renderings that were reported as offenders and are not. Quoted from the files.
FAITHFUL_RENDERINGS: tuple[tuple[str, str], ...] = (
    (
        "SQL comment continuation",
        "proves exhaustion of the retrieval\n--    that ran, not of the corpus",
    ),
    (
        "TypeScript string concatenation",
        "proves exhaustion of the ' +\n  'retrieval that ran, not of the corpus.'",
    ),
    (
        "TypeScript, shouting the emphasis",
        "proves exhaustion of the RETRIEVAL THAT RAN, ' +\n        'not of the corpus.',",
    ),
    (
        "markdown blockquote",
        "proves exhaustion of the\n> retrieval that ran, not of the corpus.**",
    ),
)

#: The rewrite that matters, in each medium that the folds above now reach. Every one of
#: these still says "proves exhaustion" and every one makes a claim the receipt cannot
#: support. If a fold ever swallowed one of these, the fold would have bought a green.
REWRITES_THAT_MUST_STILL_BE_CAUGHT: tuple[tuple[str, str], ...] = (
    ("the corpus, plainly", "proves exhaustion of the corpus."),
    ("the `not` dropped", "proves exhaustion of the retrieval that ran, of the corpus."),
    ("both, joined", "proves exhaustion of the retrieval that ran, and of the corpus."),
    ("the subject slid", "proves exhaustion of the fonds that ran, not of the corpus."),
    ("hidden behind a SQL wrap", "proves exhaustion of the\n--    corpus."),
    ("hidden behind a TypeScript seam", "proves exhaustion of the ' +\n  'corpus.'"),
    ("hidden behind a blockquote", "proves exhaustion of the\n> corpus."),
    (
        "hidden behind a `//` wrap",
        "proves exhaustion of the retrieval that ran,\n// and of the corpus.",
    ),
)


@pytest.mark.parametrize(("medium", "fragment"), FAITHFUL_RENDERINGS, ids=lambda v: v[:40])
def test_green_a_faithful_rendering_in_another_medium_is_accepted(
    medium: str, fragment: str
) -> None:
    """The complement of the reds: the ring says yes to the claim as other domains write it."""
    assert claim_holds(fragment), (
        f"{medium}: this reproduces the sanctioned claim and the ring rejected it. A checker "
        f"that cries wolf four times teaches its reader to ignore the fifth."
    )


@pytest.mark.parametrize(
    ("label", "fragment"), REWRITES_THAT_MUST_STILL_BE_CAUGHT, ids=lambda v: v[:40]
)
def test_red_a_rewritten_claim_is_caught_in_every_medium_the_folds_reach(
    label: str, fragment: str
) -> None:
    """Red first. Folding scaffolding may not fold the difference between two claims."""
    assert not claim_holds(fragment), (
        f"{label}: the ring accepted a statement that claims exhaustion of the CORPUS. "
        f"A proof that overclaims is worse than none, and a normaliser that cannot tell "
        f"these apart has stopped asserting anything: {fragment!r}"
    )


def test_the_folds_remove_punctuation_and_never_a_letter() -> None:
    """The structural guarantee behind the folds, asserted rather than asserted-in-prose."""
    for _medium, fragment in FAITHFUL_RENDERINGS + REWRITES_THAT_MUST_STILL_BE_CAUGHT:
        before = re.sub(r"[^a-z]", "", fragment.casefold())
        after = re.sub(r"[^a-z]", "", normalise(fragment))
        assert before == after, (
            f"normalise() changed the letters of {fragment!r}: {before!r} -> {after!r}. "
            "It may fold case, whitespace, emphasis and line scaffolding, and nothing else."
        )


@pytest.mark.parametrize(("label", "target"), DOWNSTREAM_CLAIMANTS, ids=str)
def test_a_downstream_claimant_carries_the_bound_once_it_claims(label: str, target: Path) -> None:
    """Wherever the claim is made in prose, the bound is owed. Not yet written is a skip."""
    if not target.exists():
        pytest.skip(
            f"{label} ({target.relative_to(REPO_ROOT)}) does not exist yet — cross-domain "
            "dependency, reported rather than assumed"
        )
    text = _read(target)
    assert text is not None, f"{target} is not decodable UTF-8"
    if not _CLAIMS_PER.search(text):
        pytest.skip(
            f"{label} makes no Proof-of-Exhausted-Recall claim yet, so it owes no bound. The "
            "grep starts biting the moment it does."
        )
    assert PER_BOUND_SENTENCE in text, (
        f"{label} names Proof of Exhausted Recall without carrying the bound verbatim. A proof "
        "that overclaims is worse than none."
    )
