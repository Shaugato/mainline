#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Extend the forbidden-sentence discipline to the submission surface.

    python scripts/submission/check_submission_prose.py              # the full check
    python scripts/submission/check_submission_prose.py --self-test  # prove it goes red
    python scripts/submission/check_submission_prose.py --no-delegate
    python scripts/submission/check_submission_prose.py --check FILE...
    python scripts/submission/check_submission_prose.py --list-rules

WHAT THIS IS FOR. `scripts/demo/claim_hygiene.py` guards the *published product* surface —
the README, VERIFY.md, the demo directory — against `ARCHITECTURE.md` §11.7's must-not-claim
table. The *submission* surface is different prose written for a different reader under a
deadline, it lives in files claim_hygiene's globs do not reach (`docs/submission/**`,
`docs/TOOL-USAGE.md`), and it can go wrong in nine ways claim_hygiene has no rule for. Those
nine are `docs/submission/MUST-NOT-CLAIM.md`, and they are SUB-01 to SUB-09 below.

IT INVOKES claim_hygiene, IT DOES NOT REIMPLEMENT IT. Two ways, both deliberate:

* **Delegation.** `claim_hygiene.main(["--root", …])` runs unchanged over its own surface,
  and its exit code is carried into this program's exit code. A submission check that
  reported green while the product check was red would be worse than no check.
* **Reuse.** `claim_hygiene.scan_text` — its rule table, its negation exemption, its bare-
  invariant and commit-SHA literals — is applied to the submission files its globs miss. One
  rule table, two surfaces.

THE NEGATION EXEMPTION IS NOT UNIFORM HERE, AND THAT IS THE POINT. claim_hygiene reads a line
carrying a negation marker as stating a rule rather than breaking it, which is right for its
families: "nothing here separates a considered disposition from a rubber stamp" is the
sentence we want people to write. It is WRONG for residency. *"Your safety records never
leave the country"* carries `never` and is a lie. So each rule below declares whether it
honours negation, `SUB-01` does not, and the reason travels with the rule.

REGISTERS ARE QUOTED IN FULL, AND SAYING SO IS PART OF THE OUTPUT. `MUST-NOT-CLAIM.md` has to
print the forbidden sentence beside the true one or it cannot do its job. A file whose head
carries the marker `prose-hygiene: register` is therefore not scanned — and it is REPORTED as
not scanned, in the same breath, because "nothing was scanned" and "it passed" are different
results and this repository does not conflate them.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

#: The submission surface. `README.md` is here as well as in claim_hygiene's globs on
#: purpose: it is the one file both readers land on, and the SUB families do not overlap
#: with the MNC families, so scanning it twice is two different questions, not one twice.
TARGET_GLOBS: tuple[str, ...] = (
    "README.md",
    "ROADMAP.md",
    "docs/submission/*.md",
    "docs/TOOL-USAGE.md",
)

#: A file that quotes prohibitions in full. Not scanned; always reported as not scanned.
REGISTER_MARKER = re.compile(r"prose-hygiene:\s*register")
REGISTER_HEAD_LINES = 40

#: The visible per-line escape hatch, spelled the same way claim_hygiene spells its own so
#: that a reader who has learned one has learned both.
INLINE_EXEMPT = re.compile(r"prose-hygiene:\s*quoting|claim-hygiene:\s*quoting")

#: A number that carries the artefact that produced it. `docs/HONESTY.md`'s whole discipline
#: in one regex: a count is allowed when the line says where it came from.
SOURCED = re.compile(
    r"\[src:|evidence/|qa/[a-z-]+\.json|proof-\d{8}T\d{6}Z|"
    r"gate_refusal\.py|seed_demo_state\.py|re-derive",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    why: str
    say_instead: str
    pattern: re.Pattern[str]
    honours_negation: bool = True
    #: When set, a match is forgiven if the line also matches this — the narrow, named
    #: exception, visible in the rule table rather than buried in the scanner.
    forgiven_if: re.Pattern[str] | None = None


def _r(
    rule_id: str,
    why: str,
    say_instead: str,
    pattern: str,
    *,
    honours_negation: bool = True,
    forgiven_if: str | None = None,
) -> Rule:
    return Rule(
        rule_id,
        why,
        say_instead,
        re.compile(pattern, re.IGNORECASE),
        honours_negation,
        re.compile(forgiven_if, re.IGNORECASE) if forgiven_if else None,
    )


# ── The nine, in the order docs/submission/MUST-NOT-CLAIM.md lists them ───────────────────
RULES: tuple[Rule, ...] = (
    _r(
        "SUB-01-residency-absolute",
        "ADR 0002 F5: inference is ap-southeast-2 (Sydney), the database is "
        "aws-ap-southeast-1 (Singapore). Nothing about this deployment keeps data in "
        "Australia, and 'never leaves' is the phrasing a buyer will quote back at you.",
        "Inference runs in Sydney; the database is in Singapore because ap-southeast-2 is "
        "Advanced-tier only. There is no end-to-end Australian residency.",
        r"\b(never|not)\s+leaves?\s+(the\s+country|australia|australian\s+soil)\b"
        r"|\b(everything|the\s+whole\s+(stack|system|thing)|all\s+of\s+(it|your\s+data))\b"
        r"[^.\n]{0,40}\bin\s+australia\b"
        r"|\bruns?\s+(entirely|wholly|only|exclusively)\s+in\s+australia\b"
        r"|\bdata\s+(stays?|remains?|stay)\s+in\s+australia\b"
        r"|\baustralian\s+data\s+sovereignty\b",
        # THE ONE RULE THAT IGNORES NEGATION. "never leaves the country" is not a denial of
        # a claim, it IS the claim, and claim_hygiene's exemption would wave it through.
        honours_negation=False,
    ),
    _r(
        "SUB-02-demo-timings",
        "Every timing in this repository is a single-node CockroachDB in Docker on one "
        "laptop. The managed cluster is in another region and the cross-region hop is "
        "unmeasured under load anywhere in the tree (docs/HONESTY.md).",
        "Every timing you see is local Docker. There is no p50 and no p99 for the "
        "cross-region hop, because nobody has measured it.",
        r"\b(refus\w+|merges?|responds?|returns?|answers?|completes?)\b[^.\n]{0,32}"
        r"\bin\s+(milliseconds|under\s+a\s+second|sub[- ]second)\b"
        r"|\b(sub[- ]second|millisecond)\b[^.\n]{0,32}\b(in\s+)?production\b"
        r"|\b(production|managed\s+cluster|cloud)\s+(latency|p50|p99)\s+(is|of|:)\b"
        r"|\bproduction\s+(timings?|benchmarks?)\s+(show|are|is)\b",
        # MEASURED INTERACTION, not a preference. claim_hygiene's NEGATION table contains
        # `\brefus\w+\b`, and "refuse" is this product's central verb — so honouring
        # negation here silently disables the rule on the exact sentence it exists to
        # catch ("the gate refuses in milliseconds in production"). The patterns above are
        # assertions of speed; none of them has an honest inverse anybody writes.
        honours_negation=False,
    ),
    _r(
        "SUB-03-corpus-is-real",
        "The corpus, the incident, the fatality, the operator and the site are AUTHORED "
        "for this repository (docs/HONESTY.md § SYNTHETIC). Kestrel Resources is fictional "
        "and the film burns a watermark saying so.",
        "Every clause, incident, permit, operator and site in this demo was written for "
        "this repository. The mechanism is real; the inputs are authored.",
        r"\b(a|this|the)\s+real\s+(incident|fatality|accident|operator|site|customer|permit)\b"
        r"|\breal[- ]world\s+(incident|corpus|operator|site|permit)\b"
        r"|\b(it|this|that)\s+(actually|really)\s+happened\b"
        r"|\bbased\s+on\s+(a|an)\s+(real|actual)\s+\w+"
        r"|\bkestrel\s+resources\b[^.\n]{0,40}\b(customer|client|our\s+operator|user)\b",
    ),
    _r(
        "SUB-04-live-model",
        "Agent tests replay recorded cassettes. A green agent test proves our code handles "
        "that recorded exchange and proves nothing about a live model today "
        "(docs/HONESTY.md § SYNTHETIC).",
        "Agent tests replay recorded request/response cassettes. Where a live call is "
        "genuinely required the test skips, and the skip reason is in the census.",
        r"\btested\s+(against|with|on)\s+(claude|bedrock|a\s+live\s+model|live\s+inference)\b"
        r"|\blive\s+(model|inference)\s+(tests?|coverage|verification)\b"
        r"|\b(agent|model)\s+tests?\b[^.\n]{0,40}\bprove[sd]?\b[^.\n]{0,30}\bmodel\b",
    ),
    _r(
        "SUB-05-conformance-passes",
        "The conformance suite has NEVER been demonstrated: against a bare node its cases "
        "error rather than skip. docs/HONESTY.md calls this the single largest gap between "
        "what the repository contains and what it has shown.",
        "The conformance suite has never been demonstrated. Two cases — CF-01 and CF-03 — "
        "are demonstrated instead by scripts/proof/gate_refusal.py, which is a smaller "
        "claim and a true one.",
        r"\bconformance\s+(suite|cases?|tests?)\b[^.\n]{0,40}"
        r"\b(pass\w*|green|clean|demonstrated|verified|succeed\w*)\b"
        r"|\b(we\s+are|it\s+is|fully)\s+conformance[- ]tested\b"
        r"|\b\d+\s+conformance\s+cases?\s+(pass|passed|passing)\b",
    ),
    _r(
        "SUB-06-migration-count",
        "The migration count MOVES. evidence/gate-refusal/proof-20260810T004200Z.json "
        "records 246 of 261; the same tree measured 271 of 271 a day later once producer "
        "migrations for the five unproduced tables appeared. Quote the artefact, or "
        "re-derive it — never a remembered number, and never 'cleanly'.",
        "Re-derive it: run scripts/proof/gate_refusal.py or "
        "scripts/submission/seed_demo_state.py and read the count that run produced.",
        r"\b(all|every)\s+(the\s+)?migrations?\s+(apply|applies|pass|passed)\b"
        r"|\b(migration\s+)?chain\s+(applies|is)\s+(clean|cleanly|complete|fully)\b"
        r"|\bschema\s+applies\s+cleanly\b"
        r"|\b\d{2,3}\s*(of|/)\s*\d{2,3}\b[^.\n]{0,24}\bmigrations?\b"
        r"|\bchain\s+applies\b[^.\n]{0,24}\b\d{2,3}\s*(of|/)\s*\d{2,3}\b",
        # A COUNT IS A LITERAL, and claim_hygiene's own header says why literals get a
        # narrower exemption than claims: a claim has an honest inverse, a literal does
        # not. "246 of 261" is still a stale number on a page that a negation elsewhere in
        # the sentence does nothing to fix. Measured: README.md:55 carries the count in a
        # sentence containing the word "never", so honouring negation hid it completely.
        honours_negation=False,
        # A count that names the artefact it came from is the behaviour this repository
        # asks for everywhere else. Forgive it here rather than punish honesty.
        forgiven_if=SOURCED.pattern,
    ),
    _r(
        "SUB-07-ledger-keys",
        "The private keys under evidence/reference-ledger/keys/ are published ON PURPOSE, "
        "carry NOT-SECRET in their own filenames, and exist so a stranger can verify the "
        "offline bundle without asking for a credential. Calling them a mistake invents an "
        "incident; calling them real invents a risk.",
        "They are published NOT-SECRET fixtures, committed deliberately so the custody "
        "bundle verifies offline. They are worthless and must never be reused.",
        r"\b(leaked|accidentally|by\s+mistake|by\s+accident|inadvertently)\b[^.\n]{0,40}"
        r"\b(keys?|credentials?|secrets?)\b"
        r"|\b(keys?|credentials?|secrets?)\b[^.\n]{0,40}"
        r"\b(leaked|accidentally|by\s+mistake|by\s+accident|inadvertently)\b"
        r"|\b(committed|published|exposed)\b[^.\n]{0,20}\bby\s+(mistake|accident)\b"
        # "are named NOT-SECRET because they are" is the SENTENCE WE WANT, and a bare
        # `secret` alternative matches inside `NOT-SECRET`. Measured on README.md:61.
        # So the claim has to be asserted, not merely adjacent.
        r"|\breference[- ]ledger\s+keys?\b[^.\n]{0,40}"
        r"\b(are\s+secure|are\s+secret|are\s+real|are\s+production|in\s+production)\b",
    ),
    _r(
        "SUB-08-custody-verified",
        "trappoint-verify exits 2 over the reference ledger: nine of sixteen checks ran and "
        "held, SEVEN DID NOT RUN, and the seven are the cryptographic half. Exit 2 is the "
        "tool saying this is not a clean verification "
        "(qa/test-state.json#external_checks.custody_bundle_verification).",
        "Nine of sixteen checks ran and every one held; seven did not run at all. What is "
        "verified is the Merkle structure, not the signatures over it.",
        r"\bcustody\s+bundle\b[^.\n]{0,40}\b(verifies|verified|passes|passed|is\s+clean)\b"
        r"|\bcryptographically\s+verified\b"
        r"|\b(all|every)\s+(sixteen|16|custody\s+)?checks?\s+(pass\w*|held|hold)\b"
        r"|\btrappoint-verify\b[^.\n]{0,32}\b(passes|is\s+clean|is\s+green|exits\s+0)\b",
    ),
    _r(
        "SUB-09-cloud-in-ci",
        "Nothing has ever run against CockroachDB Cloud in CI; the nightly truth check is "
        "designed, not scheduled (docs/HONESTY.md). A captured ccloud transcript under "
        "evidence/ccloud/ is a human session, not a lane.",
        "Nothing has ever run against CockroachDB Cloud in CI. The cluster exists and there "
        "is a captured transcript; no automated lane has ever pointed at it.",
        r"\b(CI|nightly|pipeline|workflow|github\s+actions)\b[^.\n]{0,40}"
        r"\bcockroachdb\s+cloud\b"
        r"|\bcockroachdb\s+cloud\b[^.\n]{0,40}\b(in\s+CI|nightly\s+lane|on\s+every\s+push)\b"
        r"|\btested\s+against\s+(the\s+)?(managed|cloud)\s+cluster\b"
        r"|\b(runs?|running)\s+(on|against)\s+cockroachdb\s+cloud\b",
    ),
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: Path
    line_no: int
    rule_id: str
    excerpt: str
    why: str
    say_instead: str

    def render(self, root: Path) -> str:
        try:
            where = self.path.relative_to(root).as_posix()
        except ValueError:
            where = self.path.as_posix()
        return (
            f"{where}:{self.line_no}: [{self.rule_id}] {self.excerpt}\n"
            f"    WHY  {self.why}\n"
            f"    SAY  {self.say_instead}"
        )


# ═════════════════════════════════════════════════════════════════════════════════════════
# claim_hygiene, imported rather than copied
# ═════════════════════════════════════════════════════════════════════════════════════════


def repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    return Path(__file__).resolve().parents[2]


def load_claim_hygiene(root: Path) -> ModuleType:
    path = root / "scripts" / "demo" / "claim_hygiene.py"
    if not path.is_file():
        raise SystemExit(
            f"check_submission_prose: {path} is not on disk. This tool invokes the claim "
            "hygiene scanner rather than reimplementing it; without it, half the rules "
            "this program reports on do not exist and reporting green would be a lie."
        )
    spec = importlib.util.spec_from_file_location("mainline_claim_hygiene", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"check_submission_prose: could not load {path} as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ═════════════════════════════════════════════════════════════════════════════════════════
# scanning
# ═════════════════════════════════════════════════════════════════════════════════════════


def is_register(text: str) -> bool:
    head = "\n".join(text.splitlines()[:REGISTER_HEAD_LINES])
    return bool(REGISTER_MARKER.search(head))


def scan_text(path: Path, text: str, hygiene: ModuleType) -> list[Finding]:
    """Apply the SUB rules to one file, honouring each rule's own negation policy.

    A KNOWN BLIND SPOT, RECORDED 2026-08-18 RATHER THAN LEFT AS FOLKLORE. This scans PHYSICAL
    lines, so a rule's negation exemption only sees the words on the same wrapped line. That
    cuts both ways and the second way is the dangerous one:

    * A sanctioned sentence that happens to wrap FIRES. `ROADMAP.md` hit this the first time
      it was scanned: it carried SUB-09's `say_instead` verbatim, hard-wrapped, and the word
      `Nothing` landed on the line above the match. Worked around by keeping the sentence on
      one line, which is a convention and not a fix.
    * A real claim whose disclaimer sits ONE LINE AWAY passes, and nothing reports that it
      passed for a reason nobody chose.

    `scripts/submission/check_readme_readability.py` made the opposite call for its own
    families and wrote down why -- where a line ends is a fact about the author's editor and
    not about the prose -- and this program should be moved onto the same block model. It has
    not been, because doing it an hour before a deadline is how a checker starts lying.
    """
    findings: list[Finding] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if INLINE_EXEMPT.search(line):
            continue
        negated = bool(hygiene.NEGATION.search(line))
        for rule in RULES:
            if rule.pattern.search(line) is None:
                continue
            if rule.honours_negation and negated:
                continue
            if rule.forgiven_if is not None and rule.forgiven_if.search(line):
                continue
            findings.append(
                Finding(path, line_no, rule.rule_id, line[:150], rule.why, rule.say_instead)
            )
    return findings


def collect_targets(root: Path) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    empty: list[str] = []
    for glob in TARGET_GLOBS:
        matches = [p for p in sorted(root.glob(glob)) if p.is_file()]
        if matches:
            found.extend(matches)
        else:
            empty.append(glob)
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in found:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique, empty


#: Rules from claim_hygiene that are NOT re-applied to the submission surface, each with
#: the reason, because a scoping decision that is not written down is indistinguishable
#: from a rule somebody quietly switched off.
#:
#: `HYG-sha-literal` bans a 7- or 40-hex git-object literal. That ban is about the FILM and
#: the DECK: MAINLINE's `commit_id` is a sha256 over a JCS envelope and cannot be chosen in
#: advance, so a SHA written into a script is a promise the DAG has not made. A submission
#: document has the opposite job. `docs/submission/DISCLOSURE.md` must name
#: `f80fefd49168cf52b2aa22a75396d419d67345be` — quoting the first commit is the *entire
#: mechanism* of a pre-existing-code disclosure, and `PUBLIC-READINESS.md` must name the
#: commit that introduced the value it is asking someone to mask. Measured: applying the
#: rule to these files produced 18 findings and every one of them was the document working.
#:
#: `HYG-bare-invariant` is NOT excluded. A bare `I07` in a submission document is ambiguous
#: between two catalogues for a judge exactly as it is for a customer.
NOT_REAPPLIED: dict[str, str] = {
    "HYG-sha-literal": (
        "a provenance disclosure's job is to quote git commits; the ban is on SHAs in the "
        "film and the deck, where commit_id cannot be chosen in advance"
    ),
}


def scan_paths(
    paths: list[Path], hygiene: ModuleType, *, already_covered: frozenset[Path] = frozenset()
) -> tuple[list[Finding], list[Finding], list[Path]]:
    """Return ``(sub_findings, mnc_findings, registers)``.

    `mnc_findings` come from `claim_hygiene.scan_text` run over the SUBMISSION files —
    the ones its own globs never reach. Same rule table, wider surface. Files claim_hygiene
    already scans for itself are skipped here: reporting one finding twice, under two
    programs, makes a reader hunt for a second defect that does not exist.
    """
    sub: list[Finding] = []
    mnc: list[Finding] = []
    registers: list[Path] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  SKIP  {path} is not UTF-8 and was not scanned")
            continue
        if is_register(text):
            registers.append(path)
            continue
        sub.extend(scan_text(path, text, hygiene))
        if path in already_covered:
            continue
        for f in hygiene.scan_text(path, text):
            if f.rule_id in NOT_REAPPLIED:
                continue
            mnc.append(
                Finding(
                    f.path,
                    f.line_no,
                    f.rule_id,
                    f.excerpt,
                    f.why,
                    "see scripts/demo/claim_hygiene.py --list-rules",
                )
            )
    return sub, mnc, registers


# ═════════════════════════════════════════════════════════════════════════════════════════
# RED BEFORE GREEN
# ═════════════════════════════════════════════════════════════════════════════════════════

#: One planted sentence per family, in rule order. Each is a sentence somebody could
#: plausibly write at 02:00 on D-1, which is the only kind worth planting.
SELF_TEST_FIXTURE = """\
# A deliberately non-compliant submission page

Your safety records never leave the country.
The gate refuses in milliseconds in production.
The compressor setpoint story is a real incident from an operating mine.
Every retrieval path is tested against Claude on live inference.
The conformance suite passes end to end.
All the migrations apply, so the schema is sound.
The reference-ledger private keys were committed by mistake and we rotated them.
The custody bundle verifies, so the ledger is sound.
Our nightly CI lane runs against CockroachDB Cloud before every release.
"""

SELF_TEST_EXPECTED = {rule.rule_id for rule in RULES}

#: A register quotes prohibitions in full and must be reported as unscanned, never as a
#: pass. Planting the identical violations behind the marker proves the exemption works AND
#: that it announces itself.
SELF_TEST_REGISTER = "<!-- prose-hygiene: register -->\n" + SELF_TEST_FIXTURE


def self_test(hygiene: ModuleType) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        planted = Path(tmp) / "planted-violations.md"
        planted.write_text(SELF_TEST_FIXTURE, encoding="utf-8")
        register = Path(tmp) / "register.md"
        register.write_text(SELF_TEST_REGISTER, encoding="utf-8")
        sub, _mnc, registers = scan_paths([planted, register], hygiene)

    fired = {f.rule_id for f in sub}
    missing = sorted(SELF_TEST_EXPECTED - fired)
    print(f"  planted {len(SELF_TEST_EXPECTED)} violation families, scanner fired on {len(fired)}")
    for finding in sorted(sub, key=lambda f: f.rule_id):
        print(f"    RED   [{finding.rule_id}] {finding.excerpt[:88]}")

    failed = False
    if missing:
        print("  SELF-TEST FAILED - the scanner did not fire on:")
        for rule_id in missing:
            print(f"    {rule_id}")
        failed = True
    if [f for f in sub if f.path == register]:
        print("  SELF-TEST FAILED - the register marker did not exempt the register file")
        failed = True
    if register not in registers:
        print("  SELF-TEST FAILED - the register file was not REPORTED as unscanned")
        failed = True

    # The delegation is part of the contract, so the self-test proves claim_hygiene's own
    # red still works through this program rather than assuming it.
    if hygiene.self_test() != 0:
        print("  SELF-TEST FAILED - the delegated claim_hygiene self-test did not pass")
        failed = True

    if failed:
        print("  A hygiene check that cannot go red asserts nothing (PL-2).")
        return EXIT_FINDINGS
    print("  self-test OK - every planted family fired, and the register announced itself")
    return EXIT_OK


# ═════════════════════════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911, PLR0912
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--self-test", action="store_true", help="prove the scanner can go red")
    parser.add_argument("--list-rules", action="store_true", help="print the rule table")
    parser.add_argument("--check", nargs="+", metavar="FILE", help="scan only these files")
    parser.add_argument(
        "--no-delegate",
        action="store_true",
        help="skip the claim_hygiene run over its own surface (this program's rules only)",
    )
    parser.add_argument("--root", default=None, help="repository root (default: inferred)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root()
    hygiene = load_claim_hygiene(root)

    if args.list_rules:
        for rule in RULES:
            print(f"{rule.rule_id}   (negation honoured: {rule.honours_negation})")
            print(f"    WHY  {rule.why}")
            print(f"    SAY  {rule.say_instead}")
        print("\nplus every rule in scripts/demo/claim_hygiene.py, applied to the same files:")
        return hygiene.main(["--list-rules"])

    if args.self_test:
        return self_test(hygiene)

    delegated = EXIT_OK
    if not args.no_delegate and not args.check:
        print("== claim_hygiene, over its own published surface (delegated, not reimplemented)")
        delegated = hygiene.main(["--root", str(root)])
        print()

    if args.check:
        paths = [Path(name).resolve() for name in args.check]
        absent = [p for p in paths if not p.is_file()]
        for path in absent:
            print(f"  FAIL  {path} does not exist — nothing was scanned")
        if absent:
            return EXIT_USAGE
        empty_globs: list[str] = []
    else:
        paths, empty_globs = collect_targets(root)
        if not paths:
            print("  FAIL  no submission surface was found to scan")
            return EXIT_USAGE

    print(f"== submission surface: {len(RULES)} SUB rules + the claim_hygiene table")
    covered, _ = hygiene.collect_targets(root)
    sub, mnc, registers = scan_paths(paths, hygiene, already_covered=frozenset(covered))
    print(f"  scanned {len(paths) - len(registers)} file(s)")
    for rule_id, why in NOT_REAPPLIED.items():
        print(f"  SCOPED   {rule_id} is not re-applied here — {why}")
    for path in sorted(set(paths) & set(covered)):
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        print(f"  DELEGATED {rel} carries the claim_hygiene table above; SUB rules only here")
    for glob in empty_globs:
        print(f"  ABSENT   {glob} matched no file — not scanned, and therefore not passed")
    for path in registers:
        rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
        print(f"  REGISTER {rel} quotes prohibitions in full — not scanned, not passed")

    for finding in sub:
        print(f"  FAIL  {finding.render(root)}")
    for finding in mnc:
        print(f"  FAIL  {finding.render(root)}")

    total = len(sub) + len(mnc)
    if total:
        print(f"  {len(sub)} submission-prose violation(s), {len(mnc)} claim-hygiene violation(s)")
    else:
        print("  submission prose OK")

    if total:
        return EXIT_FINDINGS
    if delegated != EXIT_OK:
        print(
            f"  claim_hygiene exited {delegated} over its own surface. This program's rules "
            "are clean; that one is not, and its result is carried rather than swallowed."
        )
        return delegated
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
