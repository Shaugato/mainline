#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fail the build on any published sentence this project is not entitled to say.

    python scripts/demo/claim_hygiene.py                 # scan the published surface
    python scripts/demo/claim_hygiene.py --self-test     # prove the scanner can go RED
    python scripts/demo/claim_hygiene.py --check FILE...  # scan named files only
    python scripts/demo/claim_hygiene.py --list-rules     # print the rule table

WHY A GREP AND NOT A REVIEW. ARCHITECTURE.md §11.7 carries a must-not-claim list that is
binding on the README, the deck, the video and the MSA. Every item on it is a sentence that
is *plausible*, *flattering* and *wrong*, which is precisely the class of sentence a human
reviewer waves through at 02:00 on D-1. Three of BUILD_PLAN.md §5.5's four disqualifiers fail
silently; an overclaim fails worse than silently, because it fails later and in public. So the
list is a regex table with a CI job behind it.

THE SCANNER MUST BE ABLE TO GO RED. `--self-test` builds a file containing one banned claim,
one bare invariant number and one seven-hex SHA literal, scans it, and requires all three
families to fire. A hygiene check that has never fired is decoration (PL-2). The same property
is asserted from the other direction by `scripts/demo/fixtures/claim-hygiene-red.md`, which is
committed, deliberately non-compliant, and asserted non-zero by `.github/workflows/claims.yml`.

THE NEGATION EXEMPTION, STATED OUT LOUD. Every rule below is a claim; the honest form of the
same subject is a DENIAL of that claim, and this repository is full of honest denials — the
whole of `VERIFY.md`'s "What none of this proves" section is one. A line carrying an explicit
negation marker is therefore read as the RULE rather than as the OFFENCE. The exemption is
narrow, it is listed in `NEGATION` below where anybody can read it, and the alternative is a
check nobody can write documentation past.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── The published surface ─────────────────────────────────────────────────────────────────
# Everything a judge, a customer or an opposing expert can read without our help. Internal
# planning documents (`docs/leads/**`) are deliberately ABSENT: their job is to STATE these
# rules, and they state them by quoting the forbidden phrase.
TARGET_GLOBS: tuple[str, ...] = (
    "README.md",
    "VERIFY.md",
    "NOTICE",
    "TRADEMARKS.md",
    "docs/HONESTY.md",
    "docs/MECHANISMS.md",
    "verticals/mainline/demo/*.md",
    "verticals/mainline/demo/*.yaml",
    "verticals/mainline/demo/script/*.md",
    "verticals/mainline/demo/script/*.yaml",
    "verticals/mainline/demo/honesty/*.md",
    "verticals/mainline/demo/honesty/*.html",
    "verticals/mainline/demo/operator/*.md",
    # The deck source, whatever form it lands in. Absent today; reported as absent rather
    # than silently contributing nothing, because "nothing was scanned" is not "it passed".
    "docs/deck/**/*.md",
    "docs/deck/**/*.html",
    "docs/deck/**/*.txt",
)

# Paths that are never scanned even when a glob would reach them.
EXCLUDED_PARTS: frozenset[str] = frozenset({"node_modules", ".venv", "__pycache__", "research"})

# ── The negation exemption ────────────────────────────────────────────────────────────────
# A line matching this is read as stating the rule, not breaking it.
NEGATION = re.compile(
    r"\bnever\b"
    r"|\bmust not\b|\bmay not\b|\bdo not\b|\bdoes not\b|\bdid not\b|\bcannot\b|\bcan not\b"
    r"|\bis not\b|\bare not\b|\bwas not\b|\bwere not\b|\bhas not\b|\bhave not\b|\bwill not\b"
    r"|\bis false\b|\bare false\b|\bwas false\b|\bbe false\b|\bfalse for\b"
    r"|\bforbidden\b|\bbanned\b|\bprohibited\b|\brefus\w+\b"
    r"|\bnothing\b|\bnobody\b|\bno claim\b|\bnot claimed\b|\bunclaimed\b"
    r"|\bnot that\b|\bnot built\b|\bnot in scope\b|\bout of scope\b|\bnot verified\b"
    r"|\bwe do not\b|\bwe don't\b|\bdon't claim\b|\bstop claiming\b"
    r"|^\s*(?:[-*+>|]\s*)*not\b",
    re.IGNORECASE | re.MULTILINE,
)

#: A line naming the invariant-number rule is quoting it, not committing it. The dash class is
#: written as an escape rather than as a literal en dash because the documents that cite the
#: catalogue as a RANGE use U+2013, and a source file that mixes dash characters visually is a
#: source file somebody will "tidy" into a regex that no longer matches.
INVARIANT_RULE_MENTION = re.compile(
    "invariant number|invariant catalogue|\bI01[\u2013\u2014-]I16\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Rule:
    """One forbidden claim: an id, why it is forbidden, and how to see it."""

    rule_id: str
    why: str
    pattern: re.Pattern[str]


def _r(rule_id: str, why: str, pattern: str) -> Rule:
    return Rule(rule_id, why, re.compile(pattern, re.IGNORECASE))


# ── The must-not-claim table (ARCHITECTURE.md §11.7), one row per item ────────────────────
RULES: tuple[Rule, ...] = (
    _r(
        "MNC-01-rls-vs-rogue-admin",
        "RLS is a tenancy and least-privilege control. It is evaluated by the same server a "
        "cluster admin owns, so it defends against a confused query, never against the admin.",
        r"(row[- ]level security|\bRLS\b)[^.\n]{0,90}\b(rogue|malicious|compromised|hostile)\s+"
        r"(admin|administrator|superuser|operator|insider)"
        r"|(rogue|malicious|compromised|hostile)\s+(admin|administrator|superuser|insider)"
        r"[^.\n]{0,90}(row[- ]level security|\bRLS\b)",
    ),
    _r(
        "MNC-02-residency",
        "ADR 0002 F5: the cluster is aws-ap-southeast-1 (Singapore) and only Bedrock inference "
        "is in ap-southeast-2 (Sydney). End-to-end Australian residency is false here.",
        r"end[- ]to[- ]end\s+australian\s+(data\s+)?residency"
        r"|\b(data|database|records?)\b[^.\n]{0,40}\breside[sd]?\s+in\s+australia"
        r"|\bsydney\b[^.\n]{0,40}\bdata\s+residency"
        r"|\baustralian\s+data\s+residency\b",
    ),
    _r(
        "MNC-03-cmek-privatelink",
        "CMEK and PrivateLink are not available on the tier this deployment runs on. Naming "
        "them affirmatively claims a control that is not provisioned.",
        r"\b(CMEK|customer[- ]managed encryption keys?|PrivateLink|Private Link)\b",
    ),
    _r(
        "MNC-04-self-critical-analysis-privilege",
        "There is no self-critical-analysis privilege in Australian law. Asserting one in a "
        "customer document is worse than useless: it shapes behaviour around a protection "
        "that does not exist.",
        r"self[- ]critical[- ]analys(is|es)\s+privilege",
    ),
    _r(
        "MNC-05-privilege-scope",
        "Legal privilege does not extend over operational records or pre-engagement material.",
        r"privileg\w*[^.\n]{0,60}\b(operational records?|pre[- ]engagement)"
        r"|\b(operational records?|pre[- ]engagement)[^.\n]{0,60}privileg\w*",
    ),
    _r(
        "MNC-06-rubber-stamp",
        "Nothing in this data model distinguishes a considered disposition from a rubber "
        "stamp. It makes the question unavoidable and the record precise; it does not read "
        "sincerity. Claiming otherwise is the project's single worst available overclaim.",
        r"\b(distinguish\w*|tell\w*|separat\w*|detect\w*|identif\w*|spot\w*|catch\w*)\b"
        r"[^.\n]{0,60}rubber[- ]?stamp"
        r"|rubber[- ]?stamp[^.\n]{0,60}\b(detect\w*|identif\w*|flagg?\w*)\b",
    ),
    _r(
        "MNC-07-identity-proofing",
        "We enrol a credential and bind a signature to it. We do not identity-proof anybody; "
        "that is the customer's IdP's job and we never take the claim.",
        r"\bidentity[- ]proof(s|ed|ing)?\b|\bproof of identity\b|\bverif\w+ (their|the) identity\b",
    ),
    _r(
        "MNC-08-webauthn-precedent",
        "There is no judicial precedent for WebAuthn-signed safety records. Non-repudiation "
        "here is cryptographic, and its evidentiary weight is untested.",
        r"(judicial\s+)?(precedent|case law)[^.\n]{0,80}(webauthn|passkey)"
        r"|(webauthn|passkey)[^.\n]{0,80}(judicial\s+)?(precedent|case law)",
    ),
    _r(
        "MNC-09-time-travel",
        "ADR 0002 GT-07 measured gc.ttlseconds = 4500 (75 minutes). AS OF SYSTEM TIME cannot "
        "reach months back; all long-horizon versioning is the application-level commit DAG.",
        r"AS OF SYSTEM TIME[^.\n]{0,60}\b(months?|years?|decades?)\b"
        r"|\b(months?|years?|multi[- ]month)\b[^.\n]{0,60}AS OF SYSTEM TIME"
        r"|\bmulti[- ]month\s+time[- ]travel\b",
    ),
    _r(
        "MNC-10-ann-bit-identical",
        "An ANN result is not bit-identically replayable. What is claimed is replayability of "
        "the arithmetic and of the disclosed boundary, which is a different and weaker thing.",
        r"bit[- ]identical[^.\n]{0,60}(ann|vector|recall|retrieval|replay|result)"
        r"|(ann|vector|recall|retrieval)[^.\n]{0,60}bit[- ]identical",
    ),
    _r(
        "MNC-11-corpus-exhaustion",
        "Proof of exhausted recall is exhaustion of THE RETRIEVAL THAT RAN, never of the "
        "corpus. The distinction is the entire honesty of the mechanism.",
        r"exhaust\w*[^.\n]{0,30}\bthe corpus\b|\bthe corpus\b[^.\n]{0,30}\bexhaust\w*",
    ),
    _r(
        "MNC-12-live-ot",
        "There is no live OT connectivity and no auto-remediation. Ingestion is a periodic "
        "one-way export from the OT DMZ; the system detects and refuses.",
        r"live\s+OT\s+(connectivity|link|integration|feed)"
        r"|\bauto[- ]?remediat\w*|\bself[- ]heal\w*",
    ),
    _r(
        "MNC-13-enclave-signing",
        "Signing is not enclave-attested or enclave-bound in this deployment.",
        r"enclave[- ](attested|bound|backed)|attested\s+enclave",
    ),
    _r(
        "MNC-14-split-view",
        "Split-view resistance requires a live adverse witness. Until one is running, the "
        "ledger is tamper-evident to a party who holds a checkpoint, not split-view resistant.",
        r"split[- ]view\s+resistan\w*|resistant\s+to\s+a?\s*split[- ]view",
    ),
    _r(
        "MNC-15-upstream-merge",
        "We claim THE FILING, never the merge. Upstream acceptance is not ours to promise and "
        "nothing downstream depends on it.",
        r"(our|the)\s+(skill|contribution|pull request|\bPR\b)[^.\n]{0,60}"
        r"(was|has been|is|were|have been)\s+(merged|accepted)"
        r"|merged\s+(in)?to\s+upstream|upstream\s+(has\s+)?(merged|accepted)"
        r"|landed\s+(in\s+)?upstream",
    ),
    _r(
        "MNC-16-per-person-measurement",
        "No per-person measurement operates without a customer-signed notified policy. A "
        "sentence describing it must name that gate on the same line.",
        r"per[- ]person\s+(measur\w*|profil\w*|scor\w*|assay)"
        r"|(measur\w*|profil\w*|scor\w*)\s+(individual|named)\s+(signers?|people|persons?)",
    ),
    _r(
        "MNC-17-agentic-memory-lead",
        "Leading with 'an open-source agentic memory layer' buries the claim. Lead with the "
        "refusal: the database will not merge the permit.",
        r"open[- ]source\s+agentic\s+memory\s+layer",
    ),
    _r(
        "MNC-18-materialises-a-check",
        "The mechanism materialises a ROW — a blocking_check — which a plain-column CHECK then "
        "refuses over. Saying it 'materialises a blocking check' collapses the two halves of "
        "the idiom that make it work.",
        r"materiali[sz]\w*\s+(a|the|an)\s+blocking\s+check",
    ),
    _r(
        "MNC-19-not-applicable",
        "The shipped disposition constructor is `mechanism_absent`. `not_applicable` is a "
        "name from an earlier draft and it says something the schema cannot represent.",
        r"\bnot_applicable\b",
    ),
)

#: `I\d\d` outside `spec/`. Finding S6: two colliding invariant catalogues, one of them a
#: SemVer'd public API. TRAPPOINT keeps I01 through I16; MAINLINE's renumbered to MI01-MI30.
BARE_INVARIANT = re.compile(r"(?<![A-Za-z0-9_])I\d{2}(?![0-9])")

#: A COMMIT-SHA literal: a hex run of exactly 7 (git's abbreviation) or exactly 40 (a full
#: git object name). `commit_id` in this system is a sha256 over the JCS envelope — it cannot be
#: chosen — so a SHA written into a script or a deck is a SHA that will be wrong on the day.
#:
#: NARROWED TWICE, and both narrowings are load-bearing rather than convenient.
#:
#: 1. The token must carry BOTH a digit AND a hex letter. Without the digit requirement the
#:    pattern matches the English words "defaced", "acceded" and "effaced"; without the letter
#:    requirement it matches every seven-digit number.
#: 2. EXACTLY 7 or EXACTLY 40, never "7 or more". This repository renders its own content
#:    digests at 12 or 64 hex characters ON PURPOSE — `gen_card.py` documents the choice as
#:    "twelve, never seven" — precisely so that a content digest can never be mistaken for a
#:    git object name. A content digest of a committed artefact is reproducible and quotable;
#:    a commit id is neither. Honouring that convention here is what keeps this rule cheap
#:    enough to leave switched on.
SHA_LITERAL = re.compile(
    r"(?<![0-9a-zA-Z])"
    r"(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])"
    r"(?:[0-9a-f]{7}|[0-9a-f]{40})"
    r"(?![0-9a-zA-Z])"
)

#: A UUID is masked before the SHA scan runs. `clause_uuid` is a uuid5 over a stable name — it
#: is DERIVED and quotable, unlike a commit id, and the corpus publishes it on purpose. Masking
#: it is not a loophole: the mask is the exact 8-4-4-4-12 shape and nothing else.
UUID_SHAPE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

#: YAML keys whose whole purpose is to enumerate forbidden strings. A block under one of these
#: is QUOTING the ban, so it is exempt for as long as its indentation lasts. Without this, the
#: only way to write down a prohibition is to not write it down, and REFUSAL-STRINGS.yaml's
#: `never_filmed` list — the file's most useful section — becomes unwritable.
PROHIBITION_KEYS: frozenset[str] = frozenset(
    {
        "forbidden_on_camera",
        "forbidden",
        "must_not_claim",
        "must_not",
        "never_filmed",
        "never_claim",
        "banned_phrases",
        "not_built_yet",
        "dropped_from_full_cut",
        "dropped_from_submission_cut",
    }
)
BLOCK_KEY = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?:#.*)?$")

#: The visible escape hatch. A line carrying this marker is quoting a banned phrase on purpose,
#: and the marker survives in the diff so the exemption is reviewable rather than invisible.
INLINE_EXEMPT = re.compile(r"claim-hygiene:\s*quoting")


@dataclass(frozen=True, slots=True)
class Finding:
    """One violation, located precisely enough to fix without a conversation."""

    path: Path
    line_no: int
    rule_id: str
    excerpt: str
    why: str

    def render(self, root: Path) -> str:
        try:
            where = self.path.relative_to(root).as_posix()
        except ValueError:
            where = self.path.as_posix()
        return f"{where}:{self.line_no}: [{self.rule_id}] {self.excerpt}\n    {self.why}"


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_PARTS for part in path.parts)


def collect_targets(root: Path) -> tuple[list[Path], list[str]]:
    """Return the files to scan and the globs that matched nothing.

    An unmatched glob is REPORTED, never swallowed. "Nothing was scanned" and "it passed"
    are different results and this tool refuses to conflate them.
    """
    found: list[Path] = []
    empty: list[str] = []
    for glob in TARGET_GLOBS:
        matches = [p for p in sorted(root.glob(glob)) if p.is_file() and not _is_excluded(p)]
        if matches:
            found.extend(matches)
        else:
            empty.append(glob)
    # A glob may legitimately overlap another; scan each file once.
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique, empty


def scan_text(path: Path, text: str) -> list[Finding]:
    """Scan one file's text. Line-oriented, because a fix needs a line number."""
    findings: list[Finding] = []
    in_spec_tree = "spec" in path.parts
    # Indentation of the innermost prohibition block we are inside, or None.
    quoting_indent: int | None = None
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue

        indent = len(raw) - len(raw.lstrip())
        if quoting_indent is not None and indent <= quoting_indent:
            quoting_indent = None
        block = BLOCK_KEY.match(raw)
        if block is not None and block.group(2) in PROHIBITION_KEYS:
            quoting_indent = len(block.group(1))
            continue

        # TWO EXEMPTION STRENGTHS, deliberately different.
        #
        # A CLAIM has an honest inverse — "nothing here separates a considered disposition
        # from a rubber stamp" is the sentence we want people to write — so a negation marker
        # exempts it.
        #
        # A LITERAL has no honest inverse. "The commit is not 7c2e91a" still puts a SHA on a
        # page that must not carry one, and "not I07" is still a bare invariant number. So
        # literals are exempt ONLY inside a declared prohibition block or behind the visible
        # `claim-hygiene: quoting` marker, both of which survive in the diff.
        quoting = bool(INLINE_EXEMPT.search(line)) or quoting_indent is not None
        exempt = bool(NEGATION.search(line)) or quoting
        # A UUID is derived and quotable; a commit id is not. Mask the former before the
        # SHA scan so the two are never confused.
        sha_haystack = UUID_SHAPE.sub("<uuid>", line)

        for rule in RULES:
            match = rule.pattern.search(line)
            if match is None:
                continue
            if exempt:
                continue
            if rule.rule_id == "MNC-16-per-person-measurement" and re.search(
                r"\bpolic(y|ies)\b|\bnotified\b|\bconsent\b", line, re.IGNORECASE
            ):
                # The claim is permitted when the gate is named on the same line.
                continue
            findings.append(Finding(path, line_no, rule.rule_id, line[:160], rule.why))

        if not in_spec_tree and not quoting:
            for match in BARE_INVARIANT.finditer(line):
                if INVARIANT_RULE_MENTION.search(line) or re.search(r"\bspec\b|spec/", line, re.I):
                    # A line that names the catalogue or points at `spec/` is a pointer,
                    # not a bare citation. Narrow, deliberate, and visible here.
                    continue
                findings.append(
                    Finding(
                        path,
                        line_no,
                        "HYG-bare-invariant",
                        f"{match.group(0)} in: {line[:120]}",
                        "Finding S6: a bare I\\d\\d outside spec/ is ambiguous between two "
                        "catalogues. Cite a constraint name, or MI\\d\\d for MAINLINE's own.",
                    )
                )

        for match in SHA_LITERAL.finditer(sha_haystack if not quoting else ""):
            findings.append(
                Finding(
                    path,
                    line_no,
                    "HYG-sha-literal",
                    f"{match.group(0)} in: {line[:120]}",
                    "commit_id is sha256 over the JCS envelope and cannot be chosen. The film "
                    "shows whatever the DAG produced; no SHA is ever spoken or written.",
                )
            )
    return findings


def scan_paths(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  SKIP  {path} is not UTF-8 and was not scanned")
            continue
        findings.extend(scan_text(path, text))
    return findings


# ── RED BEFORE GREEN ──────────────────────────────────────────────────────────────────────
SELF_TEST_FIXTURE = """\
# A deliberately non-compliant page

Row-level security protects the record from a rogue admin, end to end.
Our contribution was merged into upstream last week.
See I07 for the invariant that governs this.
Reproduce it at commit 7c2e91a on the demo cluster.
"""

SELF_TEST_EXPECTED = {
    "MNC-01-rls-vs-rogue-admin",
    "MNC-15-upstream-merge",
    "HYG-bare-invariant",
    "HYG-sha-literal",
}


def self_test() -> int:
    """Prove the scanner can go RED. Exit 0 means it fired on every planted violation."""
    with tempfile.TemporaryDirectory() as tmp:
        fixture = Path(tmp) / "planted-violations.md"
        fixture.write_text(SELF_TEST_FIXTURE, encoding="utf-8")
        findings = scan_paths([fixture])

    fired = {finding.rule_id for finding in findings}
    missing = sorted(SELF_TEST_EXPECTED - fired)
    print(f"  planted {len(SELF_TEST_EXPECTED)} violation families, scanner fired on {len(fired)}")
    for finding in findings:
        print(f"    RED   [{finding.rule_id}] {finding.excerpt[:90]}")
    if missing:
        print("  SELF-TEST FAILED — the scanner did not fire on:")
        for rule_id in missing:
            print(f"    {rule_id}")
        print("  A hygiene check that cannot go red asserts nothing (PL-2).")
        return 1
    print("  self-test OK — the scanner goes red on every planted family")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--self-test", action="store_true", help="prove the scanner can go red")
    parser.add_argument("--list-rules", action="store_true", help="print the rule table")
    parser.add_argument("--check", nargs="+", metavar="FILE", help="scan only these files")
    parser.add_argument(
        "--root", default=str(REPO_ROOT), help="repository root (default: inferred)"
    )
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.list_rules:
        for rule in RULES:
            print(f"{rule.rule_id}\n    {rule.why}")
        print("HYG-bare-invariant\n    a bare I\\d\\d outside spec/ (finding S6)")
        print("HYG-sha-literal\n    a 7-40 hex commit literal; commit_id cannot be chosen")
        return 0

    if args.self_test:
        return self_test()

    if args.check:
        paths = [Path(name).resolve() for name in args.check]
        missing = [p for p in paths if not p.is_file()]
        for path in missing:
            print(f"  FAIL  {path} does not exist — nothing was scanned")
        if missing:
            return 2
        findings = scan_paths(paths)
        empty_globs: list[str] = []
    else:
        paths, empty_globs = collect_targets(root)
        if not paths:
            print("  FAIL  no published surface was found to scan")
            return 2
        findings = scan_paths(paths)

    print(f"  scanned {len(paths)} file(s) against {len(RULES) + 2} rules")
    for glob in empty_globs:
        print(f"  ABSENT  {glob} matched no file — not scanned, and therefore not passed")

    if not findings:
        print("  claim hygiene OK")
        return 0

    for finding in findings:
        print(f"  FAIL  {finding.render(root)}")
    print(f"  {len(findings)} claim-hygiene violation(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
