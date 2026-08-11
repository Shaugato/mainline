#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""PUBLIC-READINESS AUDIT: what a judge, a scraper and an archive would receive.

Flipping ``github.com/Shaugato/mainline`` from PRIVATE to PUBLIC is irreversible.
Forks, GitHub's own fork network, search-engine caches, Software Heritage and the
GHArchive stream all outlive a revert, and every one of the sixteen commits in the
history is published at once — not just the tree at HEAD.  This program is the
checklist that makes that decision defensible: seven checks, each of which emits a
machine row carrying the command that produced it and what that command printed.

Design commitments, in the style the repository already holds itself to:

* **Standard library only, and no network.**  No ``urllib``, no ``socket``, no
  ``requests``.  The only subprocess is ``git``.  An auditor can read this file
  top-to-bottom and know it phoned nobody.  The disclosure register is YAML, and it
  is read by a strict minimal parser in this file rather than by ``PyYAML``, so the
  program still runs to completion under ``python -I -S``.
* **A hit that does not gate is a documented decision, never a silent pass.**  There
  are exactly three dispositions and two of them require somebody's name:

  ``UNRESOLVED``   gating, red, the default for everything.
  ``ALLOWLISTED``  non-gating; granted by an :class:`Waiver` in ``ALLOWLIST`` below,
                   keyed by *exact path plus family*, each carrying a reason.
  ``DISCLOSED``    non-gating; granted **only** by an entry naming the exact path in
                   ``docs/submission/DISCLOSURE-DECISIONS.yaml`` that carries a
                   family, a class from a fixed vocabulary, a date, a decider and a
                   reason of at least 80 characters (decision D2,
                   ``docs/leads/ship-final.md`` §1.6).

  An occurrence in a file named by neither is ``UNRESOLVED`` and stays red.  A
  register entry that grants nothing this run is itself a failure — a stale grant is
  an allowlist quietly widening, and check 8 refuses it.
* **History is scanned, not just the working tree.**  Masking a value at HEAD does
  not remove it from a commit that is already on the remote.  Check 2 exists
  precisely so that difference cannot be papered over.  A register entry declares
  which scopes it covers, so a value accepted *in history* does not become
  acceptable if it reappears at HEAD.
* **Findings are redacted, always, in every disposition.**  A match preview is a
  six-character prefix plus a length, and there is no flag that turns that off.  An
  earlier design let a waiver mark a value ``verbatim`` when it was public by design;
  because this program scans every tracked file and ``qa/public-readiness.json`` is
  one, each run wrote N verbatim previews and the next run found N and wrote N + 32.
  See :func:`redact_preview` for the measured numbers.  Values that are public by
  design are still named — once each, in prose, in the waiver's own reason.

Exit status is 0 only when every finding is resolved, allowlisted with a reason, or
disclosed by a register entry, and every gating check passes.

    python scripts/submission/audit_public_readiness.py
    python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
    python scripts/submission/audit_public_readiness.py --self-test
    printf '%s' "$SECRET" | python scripts/submission/audit_public_readiness.py --assert-absent

``--self-test`` plants one secret of every family into a temporary tree and requires
the scanner to fire on each; a scanner that has quietly stopped detecting is worse
than no scanner, so the self-test is the thing that keeps this file honest.  Every
planted literal is assembled at runtime from fragments so that this source file does
not itself contain a string that its own scan would flag.  It additionally pins the
detector fingerprint — a digest over every pattern, the entropy floor and the family
list — so that widening a pattern, lowering a threshold or deleting a family fails
the self-test rather than quietly buying a green.

``--assert-absent`` reads one candidate value from **stdin** and proves it appears in
no tracked file and in no line ever added on any ref.  It exists for the rotated
``mainline_judge`` password: the value never reaches an argument vector, an
environment variable, a shell history or a file, and the program prints only a
SHA-256 prefix of what it checked, so the run is reproducible without republishing
the credential.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = "mainline.qa.public-readiness/1"
REPO_EXPECTED = "https://github.com/Shaugato/mainline.git"
BRANCH_EXPECTED = "master"
MAX_TRACKED_BYTES = 5 * 1024 * 1024  # 5 MiB
MAX_SCAN_LINE = 4000  # entropy tokenisation is skipped past this width

# ══════════════════════════════════════════════════════════════════════════════════
# Detector families
# ══════════════════════════════════════════════════════════════════════════════════
#
# Two kinds of detector.  KNOWN-PREFIX detectors match an issuer-assigned shape and
# are essentially noise-free.  CONTEXTUAL detectors (aws_account_id,
# high_entropy_secret) would be unusable as bare regexes over this tree — a plain
# 12-digit scan returns 585 hits across 135 files, and a bare entropy scan returns
# 1,021 — so each is narrowed by the context it appears in.  The narrowing is stated
# here rather than hidden in an allowlist, because a detector that is silently blind
# is a worse failure than a detector that is loud.

FAMILIES: dict[str, str] = {
    "aws_access_key_id": "AWS access key id (AKIA/ASIA + 16)",
    "github_token": "GitHub token (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_)",
    "slack_token": "Slack token (xoxb/xoxa/xoxp/xoxr/xoxs)",
    "private_key_block": "PEM private key block",
    "crdb_cloud_api_key": "CockroachDB Cloud API key (CCDB1_)",
    "aws_account_id": "AWS 12-digit account id in account/ARN context",
    "bearer_or_jwt": "Bearer credential or JWT",
    "high_entropy_secret": "high-entropy token next to a secret-shaped key name",
}

RE_KNOWN_PREFIX: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])"),
    "github_token": re.compile(
        r"(?<![A-Za-z0-9_])(?:gh[pousr]_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{40,})"
    ),
    "slack_token": re.compile(r"(?<![A-Za-z0-9])xox[baprs]-[0-9A-Za-z]{8,}(?:-[0-9A-Za-z]{8,})*"),
    # Assembled from fragments: a literal marker here would make this file match itself.
    "private_key_block": re.compile("-{5}BEGIN (?:[A-Z][A-Z ]{0,20} )?" + "PRIVATE KEY" + "-{5}"),
    "crdb_cloud_api_key": re.compile(r"(?<![A-Za-z0-9_])CCDB1_[0-9A-Za-z_-]{16,}"),
    "bearer_or_jwt": re.compile(
        r"(?<![A-Za-z0-9])eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{8,}"
        r"|(?i:bearer)\s+[0-9A-Za-z._~+/-]{24,}={0,2}"
    ),
}

# ── contextual: AWS account id ────────────────────────────────────────────────────
# A bare 12-digit run is meaningless here (synthetic corpus ids contain thousands).
# An account id is only flagged where the surrounding text says it is one: inside an
# ARN, after `iam::`, or on a line that names an account.  The founder's own account
# is additionally flagged unconditionally — it is the one value whose publication
# this audit exists to prevent, so it must not depend on context surviving an edit.
RE_TWELVE = re.compile(r"(?<![0-9A-Za-z])[0-9]{12}(?![0-9A-Za-z])")
RE_ACCOUNT_CONTEXT = re.compile(r"(?i)account|arn:aws|iam::|:sts:|:s3:|:kms:|:logs:")
FOUNDER_ACCOUNT = "0229" + "50218246"  # split so this file is not itself a hit

# AWS publishes these ids in its own documentation.  They identify nothing.
AWS_DOC_ACCOUNTS = frozenset(
    {"111122223333", "123456789012", "444455556666", "555555555555", "000000000000"}
)

# ── contextual: high-entropy secret ───────────────────────────────────────────────
# Entropy alone flags 1,021 tokens, almost all of them lockfile integrity digests and
# the deliberately-published ledger material.  Narrowing to "high-entropy token that
# sits after a secret-shaped key name on the same line" reduces that to a handful,
# each of which is a real decision.  Dotted identifiers (`FIXTURE_LOG_KEY.read_bytes`)
# are excluded: they are code, not credentials.
RE_SECRET_KEYNAME = re.compile(
    r"(?i)(?:secret|token|password|passwd|pwd|api[_-]?key|apikey|access[_-]?key"
    r"|private[_-]?key|credential|client[_-]?secret|authorization|auth[_-]?key"
    r"|session[_-]?key|signing[_-]?key)"
)
RE_CANDIDATE_TOKEN = re.compile(r"[A-Za-z0-9+/=_.~-]{24,}")
RE_DOTTED_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
ENTROPY_FLOOR = 4.2

# ── absolute Windows paths ────────────────────────────────────────────────────────
# Drive letter, one path segment, then another separator.  The segment requirement is
# what separates `D:\CoackroachDBxAWS\` from `NOT A PASS:\n` — an earlier draft of
# this regex without it returned 113 files, of which 105 were escaped newlines inside
# assertion messages.  Both the raw and the JSON-escaped (`D:\\`) spellings match.
RE_ABS_WIN_BACKSLASH = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z]:\\\\?[A-Za-z0-9_. $()-]{1,60}\\)")
RE_ABS_WIN_SLASH = re.compile(r"(?<![A-Za-z0-9_:])([A-Za-z]:/[A-Za-z0-9_.$-]{1,60}/)")


# ── the detector fingerprint ──────────────────────────────────────────────────────
# Adding a disposition to this program creates exactly one temptation: to buy a green
# by widening a pattern, lowering the entropy floor, or deleting a family, and to call
# the result "the scanner is unchanged". This digest covers every pattern source, the
# entropy floor, the scan-line ceiling, the account-context regex, the documentation
# account set and the family list. --self-test compares it to the constant below, so
# any of those edits fails the self-test loudly instead of passing quietly.
#
# Changing DETECTOR_FINGERPRINT is legitimate ONLY when the detectors got STRICTER,
# and the diff that changes it must say, in the commit message, which detector got
# stricter and how it was measured.


def detector_fingerprint() -> str:
    import hashlib

    parts: list[str] = [f"families={sorted(FAMILIES)}"]
    for name in sorted(RE_KNOWN_PREFIX):
        parts.append(f"{name}={RE_KNOWN_PREFIX[name].pattern}")
    parts.append(f"twelve={RE_TWELVE.pattern}")
    parts.append(f"acct_ctx={RE_ACCOUNT_CONTEXT.pattern}")
    parts.append(f"doc_accounts={sorted(AWS_DOC_ACCOUNTS)}")
    parts.append(f"keyname={RE_SECRET_KEYNAME.pattern}")
    parts.append(f"candidate={RE_CANDIDATE_TOKEN.pattern}")
    parts.append(f"dotted={RE_DOTTED_IDENT.pattern}")
    parts.append(f"floor={ENTROPY_FLOOR!r}")
    parts.append(f"maxline={MAX_SCAN_LINE!r}")
    parts.append(f"abs_bs={RE_ABS_WIN_BACKSLASH.pattern}")
    parts.append(f"abs_fs={RE_ABS_WIN_SLASH.pattern}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


DETECTOR_FINGERPRINT = "9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a"


# ══════════════════════════════════════════════════════════════════════════════════
# The allowlist — every entry is a decision somebody has to defend
# ══════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Waiver:
    """One allowlisted (path, family) pair and the reason it is safe to publish."""

    path: str
    family: str
    reason: str
    verbatim: bool = False


ALLOWLIST: tuple[Waiver, ...] = (
    # ── AWS documentation placeholders ────────────────────────────────────────────
    Waiver(
        path="infra/policy/custody/fixtures/README.md",
        family="aws_access_key_id",
        reason=(
            "AKIAIOSFODNN7EXAMPLE is the access key id AWS itself prints in its public "
            "documentation. It authenticates nothing and is not derived from any real "
            "key. Present so the custody fixture README shows the shape a reviewer "
            "should expect."
        ),
        verbatim=True,
    ),
    Waiver(
        path="infra/policy/custody/fixtures/plan_compliant.json",
        family="aws_access_key_id",
        reason=(
            "Same AWS documentation placeholder, embedded in a recorded terraform plan "
            "fixture. The plan was produced against the documentation account "
            "111122223333, not against account 0229...8246."
        ),
        verbatim=True,
    ),
    Waiver(
        path="infra/policy/custody/fixtures/README.md",
        family="high_entropy_secret",
        reason=(
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY is AWS's published secret-access-key "
            "placeholder, the counterpart to the AKIA...EXAMPLE id on the line above it."
        ),
        verbatim=True,
    ),
    # ── deliberately published cryptographic material ─────────────────────────────
    *(
        Waiver(
            path=f"evidence/reference-ledger/keys/reference-{name}.NOT-SECRET.key.pem",
            family="private_key_block",
            reason=(
                "Published on purpose. docs/HONESTY.md lines 173-174 state that every file "
                "under evidence/reference-ledger/keys/ is a private key committed "
                "deliberately, so that a third party can re-sign the reference bundle and "
                "reproduce every value in it. The filename carries NOT-SECRET. These keys "
                "sign nothing outside the reference ledger."
            ),
        )
        for name in ("log", "tsa", "tsa-root", "webauthn", "witness")
    ),
    Waiver(
        path="spec/wire/checkpoint.md",
        family="private_key_block",
        reason=(
            "The section 7.1 worked test vector. The document states in bold that the key "
            "is published deliberately so anyone can reproduce section 7, that it signs "
            "nothing but this document's example, and that it never was a MAINLINE log key. "
            "trappoint-verify and trappoint_ledger.note both read it out of this file, so "
            "removing it would break the spec/code anti-drift property."
        ),
    ),
    Waiver(
        path="packages/trappoint-ledger/tests/test_receipt.py",
        family="private_key_block",
        reason=(
            "No key here. The file contains the marker string only, as the index bounds "
            "used to slice the published key out of spec/wire/checkpoint.md at line 123-125."
        ),
    ),
    Waiver(
        path="packages/mainline-agentkit/tests/test_runtime.py",
        family="aws_account_id",
        reason=(
            "FOREIGN_ACCOUNT_ARN at line 62-64 uses the twelve-nines placeholder to assert "
            "that a Bedrock inference-profile ARN belonging to a DIFFERENT account is "
            "rejected. Twelve identical digits is a synthetic constant, not an account. The "
            "sibling constants on the same lines use twelve zeroes for the same reason."
        ),
        verbatim=True,
    ),
    Waiver(
        path="tests/security/injection/corpus/encoded-002-base64-exfil.json",
        family="high_entropy_secret",
        reason=(
            "A prompt-injection attack corpus entry. The base64 decodes to an instruction "
            "asking a model to print its system prompt and api key. It is the attack this "
            "repository tests its refusal against, not a credential."
        ),
    ),
    # ── absolute paths: recorded, not repaired ────────────────────────────────────
    #
    # Ruling: an evidence artefact is a record of a run. Editing one so that it looks
    # tidier is exactly the move this repository refuses; the honest repair is for the
    # next run to write a relative path. Each of these is therefore recorded with the
    # cost stated, and the owning domain decides.
    Waiver(
        path="evidence/gate-refusal/proof-20260809T213857Z.json",
        family="abs_windows_path",
        reason=(
            "migrations_dir records the absolute path the proof actually ran against. "
            "Leaks the founder's directory layout (D:\\CoackroachDBxAWS\\mainline), not a "
            "credential and not a username. RECORDED, NOT REPAIRED: rewriting a committed "
            "evidence artefact to look tidier is refused. The next proof run decides."
        ),
    ),
    Waiver(
        path="evidence/gate-refusal/proof-20260810T004200Z.json",
        family="abs_windows_path",
        reason="Identical to the 20260809T213857Z proof: migrations_dir, recorded not repaired.",
    ),
    Waiver(
        path="tests/eval/recall_calibration/artefacts/calibration_report.json",
        family="abs_windows_path",
        reason=(
            "A generated calibration artefact recording the absolute fixture path it read. "
            "Same class as the gate-refusal proofs: directory layout, no username, recorded "
            "not repaired. Owned by the recall domain."
        ),
    ),
    Waiver(
        path="qa/test-state.json",
        family="abs_windows_path",
        reason=(
            "52 occurrences of C:\\Users\\shaug\\AppData\\Local\\Temp\\mainline-census-*\\"
            "junit.xml — pytest temporary directories captured verbatim by the test census. "
            "This DOES disclose the founder's Windows account name. 'shaug' is a prefix of "
            "the already-public GitHub handle Shaugato, so the marginal disclosure is the "
            "local account name only. RECORDED, NOT REPAIRED - owned by the quality domain, "
            "and the next census run can emit relative paths."
        ),
    ),
    Waiver(
        path="docs/release/gate-refusal-proof.md",
        family="abs_windows_path",
        reason=(
            "Pasted pytest failure output, including D:\\CoackroachDBxAWS\\mainline\\tests\\"
            "release\\ and a C:\\Users\\shaug\\AppData\\Local\\Temp\\pytest-of-shaug\\ tmpdir. "
            "Same disclosure class as qa/test-state.json. The captured output is the point of "
            "the document; paraphrasing it would weaken the evidence. RECORDED, NOT REPAIRED."
        ),
    ),
    Waiver(
        path="docs/STATE-OF-THE-BUILD.md",
        family="abs_windows_path",
        reason=(
            "C:\\Users\\<name>\\Documents\\projects\\ is a documentation example with a "
            "literal <name> placeholder, used to explain the Windows MAX_PATH clone failure. "
            "Plus D:/CoackroachDBxAWS/mainline in worked commands. Layout only, no username."
        ),
    ),
    Waiver(
        path="packages/trappoint-testkit/src/trappoint_testkit/cluster.py",
        family="abs_windows_path",
        reason=(
            "C:\\Program Files\\Docker\\docker.exe appears in a comment at line 511 "
            "explaining why the docker-binary check must not match on a Linux runner. A "
            "Docker Desktop install location is not personal data."
        ),
    ),
    Waiver(
        path="packages/trappoint-testkit/tests/test_shared_cluster_contract.py",
        family="abs_windows_path",
        reason=(
            "The same Docker Desktop path as a test vector at line 109, asserting the "
            "binary-name extraction handles a Windows absolute path. Not personal data."
        ),
    ),
    Waiver(
        path="docs/leads/workers.json",
        family="abs_windows_path",
        reason=(
            "Nine occurrences of D:/CoackroachDBxAWS/mainline/... inside worker briefs that "
            "quote commands. Directory layout only, no username. Owned by the lead-plan "
            "domain."
        ),
    ),
    Waiver(
        path="docs/adr/0040-custody-red-before-green.md",
        family="abs_windows_path",
        reason="One D:/CoackroachDBxAWS/mainline/ command path. Layout only, no username.",
    ),
    # ── this audit's own output ───────────────────────────────────────────────────
    Waiver(
        path="qa/public-readiness.json",
        family="aws_access_key_id",
        reason=(
            "This program's own machine output. It quotes the AWS documentation placeholder "
            "verbatim because an audit that redacts a value which is public by design tells "
            "the reader less, not more. Unresolved findings are redacted to a prefix and a "
            "length; see redact_preview()."
        ),
        verbatim=True,
    ),
    Waiver(
        path="docs/submission/PUBLIC-READINESS.md",
        family="aws_access_key_id",
        reason="Same as qa/public-readiness.json: the human-readable rendering of this audit.",
        verbatim=True,
    ),
    Waiver(
        path="docs/submission/PUBLIC-READINESS.md",
        family="high_entropy_secret",
        reason=(
            "Section 2.2 of the report quotes AWS's published secret-access-key placeholder "
            "so the reader can see the exact value that was waived. Waiving a value while "
            "refusing to print it would make the waiver unreviewable."
        ),
        verbatim=True,
    ),
    Waiver(
        path="docs/submission/PUBLIC-READINESS.md",
        family="aws_account_id",
        reason=(
            "Section 2.2 quotes the twelve-nines synthetic constant from "
            "packages/mainline-agentkit/tests/test_runtime.py for the same reason. The real "
            "account id is never printed in this report: section 4.1 refers to it only as "
            "'the twelve digits' and shows the masked form."
        ),
        verbatim=True,
    ),
    Waiver(
        path="scripts/submission/audit_public_readiness.py",
        family="aws_access_key_id",
        reason=(
            "This scanner's own allowlist reasons name AKIAIOSFODNN7EXAMPLE, because a "
            "waiver that does not say which value it waives is not a waiver. The planted "
            "self-test key is assembled from fragments at runtime and so does not appear "
            "as a literal anywhere in this file."
        ),
        verbatim=True,
    ),
    Waiver(
        path="scripts/submission/audit_public_readiness.py",
        family="high_entropy_secret",
        reason=(
            "Three hits, all synthetic: the Slack, CockroachDB-Cloud and generic-secret "
            "fixtures in planted_samples(), which exist so --self-test can prove the scanner "
            "still fires. Plus AWS's published secret-access-key placeholder quoted in a "
            "waiver reason. None of the four authenticates against anything."
        ),
        verbatim=True,
    ),
    Waiver(
        path="docs/submission/PUBLIC-READINESS.md",
        family="abs_windows_path",
        reason=(
            "This audit's own report quotes the absolute paths it found, because a row that "
            "says 'a path was found' without saying which path is not evidence."
        ),
    ),
    Waiver(
        path="scripts/submission/audit_public_readiness.py",
        family="abs_windows_path",
        reason=(
            "This scanner's allowlist reasons quote the paths they waive, and its docstrings "
            "quote the Docker Desktop example. Quoting the finding is the point of the file."
        ),
    ),
)

WAIVER_INDEX: dict[tuple[str, str], Waiver] = {(w.path, w.family): w for w in ALLOWLIST}

ALL_FAMILIES: frozenset[str] = frozenset(FAMILIES) | {"abs_windows_path"}


# ══════════════════════════════════════════════════════════════════════════════════
# The disclosure register — decision D2, docs/leads/ship-final.md §1.6
# ══════════════════════════════════════════════════════════════════════════════════
#
# The allowlist above is code: changing it is a diff somebody reviews.  That is the
# right home for a handful of structural waivers and the wrong home for "this
# recorded transcript quotes the AWS account id, and publishing it is the point of
# the transcript" — a class of decision that is numerous, per-path, dated, and owned
# by whoever captured the artefact.  Those live in data:
#
#     docs/submission/DISCLOSURE-DECISIONS.yaml
#
# The register is strictly weaker than the allowlist in what it can do.  It cannot
# set `verbatim`, so a disclosed value is still printed masked.  It cannot name a
# family that does not exist.  It cannot cover a scope it does not declare.  It
# cannot duplicate an allowlist entry.  And an entry that matches nothing is a
# failure, so the register cannot silently accumulate grants for hits that are gone.

REGISTER_DEFAULT = "docs/submission/DISCLOSURE-DECISIONS.yaml"
REGISTER_SCHEMA = "mainline.submission.disclosure-decisions/1"
REGISTER_TOP_KEYS = frozenset({"schema", "note", "generated_by", "decisions"})
REGISTER_REQUIRED = ("path", "family", "class", "date", "decided_by", "reason")
REGISTER_KEYS = frozenset(REGISTER_REQUIRED) | {"scopes"}
REGISTER_SCOPES = frozenset({"tracked", "history"})
MIN_REASON_CHARS = 80

# A fixed vocabulary. A worker cannot invent `class: fine` to get past this program;
# an unknown class is a parse failure, and the classes are chosen so that the shape
# of what was accepted is legible from the JSON without reading a single reason.
REGISTER_CLASSES: dict[str, str] = {
    "aws-documentation-placeholder": (
        "A value AWS itself publishes in its own documentation. Authenticates nothing."
    ),
    "synthetic-test-fixture": (
        "A credential-shaped literal that exists so some other program's self-test can "
        "prove its own scanner fires. Never authenticated against anything."
    ),
    "detector-context-artefact": (
        "A true positive of the pattern and a false positive of the intent: the matched "
        "token is a hostname, a file path or similar, and the secret-shaped key name "
        "that triggered the detector is a placeholder. The detector is not changed."
    ),
    "recorded-evidence-account-id": (
        "The twelve-digit AWS account id inside a quoted command, a refusal transcript "
        "or a committed plan. Not a credential; publication is the point of the record."
    ),
    "history-already-pushed": (
        "The occurrence is in a commit that is already on origin/master. Masking HEAD "
        "does not retract it; only a history rewrite would, and that trade was refused."
    ),
    "abs-path-layout": (
        "An absolute Windows path that discloses directory layout only "
        "(D:/CoackroachDBxAWS/mainline, C:/Program Files/...). No account name."
    ),
    "abs-path-username": (
        "An absolute Windows path that DOES disclose the founder's local Windows "
        "account name. A strictly larger disclosure than abs-path-layout and counted "
        "separately so it can never be lost inside the layout total."
    ),
}


class RegisterSyntaxError(ValueError):
    """The register did not parse. Never swallowed: a register that does not parse
    grants nothing, and check 8 fails."""


@dataclass(frozen=True)
class Disclosure:
    path: str
    family: str
    cls: str
    date: str
    decided_by: str
    reason: str
    scopes: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "path": self.path,
            "family": self.family,
            "class": self.cls,
            "scopes": list(self.scopes),
            "date": self.date,
            "decided_by": self.decided_by,
            "reason": self.reason,
        }


# ── a strict minimal YAML reader ──────────────────────────────────────────────────
# Supports exactly what the register uses: top-level `key: value`, one top-level
# `decisions:` sequence of mappings, plain / single- / double-quoted scalars, flow
# sequences of plain scalars, and `>`/`|` block scalars with an optional `-` chomp.
# Everything else raises. That is deliberate: a parser that guesses is a parser that
# can be fed a document meaning something other than it reads.


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skippable(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _parse_scalar(raw: str, lineno: int) -> object:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items = [piece.strip() for piece in inner.split(",")]
        for item in items:
            if not item or any(ch in item for ch in "[]{}'\"#"):
                raise RegisterSyntaxError(f"line {lineno}: bad flow-sequence item {item!r}")
        return items
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        body = raw[1:-1]
        if "\\" in body or raw[0] in body:
            raise RegisterSyntaxError(f"line {lineno}: escapes are not supported in scalars")
        return body
    if any(ch in raw for ch in "{}[]") or raw.startswith(("&", "*", "!", "%")):
        raise RegisterSyntaxError(f"line {lineno}: unsupported YAML construct in {raw!r}")
    return raw


def parse_minimal_yaml(text: str) -> dict[str, object]:  # noqa: PLR0915 - one grammar,
    # read top to bottom; splitting the readers apart would scatter the rules they enforce
    """Parse the register subset. Raises RegisterSyntaxError on anything unexpected."""
    lines = text.splitlines()
    total = len(lines)

    def read_block_scalar(start: int, owner_indent: int, style: str, chomp: str) -> tuple[str, int]:
        body: list[str] = []
        cursor = start
        while cursor < total:
            line = lines[cursor]
            if line.strip() and _indent_of(line) <= owner_indent:
                break
            body.append(line)
            cursor += 1
        while body and not body[-1].strip():
            body.pop()
        if not body:
            raise RegisterSyntaxError(f"line {start}: empty block scalar")
        base = min(_indent_of(b) for b in body if b.strip())
        body = [b[base:] if len(b) >= base else "" for b in body]
        if style == "|":
            out = "\n".join(body)
        else:
            paragraphs: list[str] = []
            run: list[str] = []
            for b in body:
                if b.strip():
                    run.append(b.strip())
                else:
                    paragraphs.append(" ".join(run))
                    run = []
            if run:
                paragraphs.append(" ".join(run))
            out = "\n".join(paragraphs)
        if chomp != "-":
            out += "\n"
        return out, cursor

    def read_pair(target: dict[str, object], cursor: int, content: str, key_indent: int) -> int:
        key, sep, rest = content.partition(":")
        if not sep:
            raise RegisterSyntaxError(f"line {cursor + 1}: expected 'key: value'")
        key = key.strip()
        rest = rest.strip()
        if not key:
            raise RegisterSyntaxError(f"line {cursor + 1}: empty key")
        if key in target:
            raise RegisterSyntaxError(f"line {cursor + 1}: duplicate key {key!r}")
        if rest[:1] in ("|", ">"):
            style = rest[0]
            chomp = rest[1:]
            if chomp not in ("", "-"):
                raise RegisterSyntaxError(
                    f"line {cursor + 1}: unsupported block indicator {rest!r}"
                )
            value, nxt = read_block_scalar(cursor + 1, key_indent, style, chomp)
            target[key] = value
            return nxt
        if not rest:
            raise RegisterSyntaxError(f"line {cursor + 1}: empty value for {key!r}")
        target[key] = _parse_scalar(rest, cursor + 1)
        return cursor + 1

    def read_item(cursor: int, dash_indent: int) -> tuple[dict[str, object], int]:
        mapping: dict[str, object] = {}
        key_indent = dash_indent + 2
        cursor = read_pair(mapping, cursor, lines[cursor].strip()[2:], key_indent)
        while cursor < total:
            line = lines[cursor]
            if _skippable(line):
                cursor += 1
                continue
            here = _indent_of(line)
            if here < key_indent or line.strip().startswith("- "):
                break
            if here > key_indent:
                raise RegisterSyntaxError(f"line {cursor + 1}: over-indented key in list item")
            cursor = read_pair(mapping, cursor, line.strip(), key_indent)
        return mapping, cursor

    def read_sequence(start: int) -> tuple[list[dict[str, object]], int]:
        items: list[dict[str, object]] = []
        cursor = start
        dash_indent: int | None = None
        while cursor < total:
            line = lines[cursor]
            if _skippable(line):
                cursor += 1
                continue
            here = _indent_of(line)
            if not line.strip().startswith("- "):
                break
            if dash_indent is None:
                dash_indent = here
                if here == 0:
                    raise RegisterSyntaxError(f"line {cursor + 1}: sequence must be indented")
            elif here != dash_indent:
                break
            item, cursor = read_item(cursor, dash_indent)
            items.append(item)
        return items, cursor

    # YAML forbids tabs in indentation, and this reader measures indentation in spaces,
    # so a tab would be counted as zero and silently reparent a nested key to the
    # document level. Refuse the whole file rather than parse a different document
    # from the one an editor renders. (Found by the self-test, not by review.)
    for lineno, line in enumerate(lines, 1):
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise RegisterSyntaxError(f"line {lineno}: tab in indentation; YAML forbids it")

    doc: dict[str, object] = {}
    i = 0
    while i < total:
        line = lines[i]
        if _skippable(line):
            i += 1
            continue
        if _indent_of(line) != 0:
            raise RegisterSyntaxError(f"line {i + 1}: unexpected indentation at document level")
        key, sep, rest = line.partition(":")
        if not sep:
            raise RegisterSyntaxError(f"line {i + 1}: expected 'key: value' at document level")
        key = key.strip()
        rest = rest.strip()
        if key in doc:
            raise RegisterSyntaxError(f"line {i + 1}: duplicate document key {key!r}")
        if not rest:
            seq, i = read_sequence(i + 1)
            if not seq:
                raise RegisterSyntaxError(f"line {i}: {key!r} has no value and no sequence")
            doc[key] = seq
            continue
        if rest[:1] in ("|", ">"):
            style = rest[0]
            chomp = rest[1:]
            if chomp not in ("", "-"):
                raise RegisterSyntaxError(f"line {i + 1}: unsupported block indicator {rest!r}")
            doc[key], i = read_block_scalar(i + 1, 0, style, chomp)
            continue
        doc[key] = _parse_scalar(rest, i + 1)
        i += 1
    return doc


def validate_register(  # noqa: PLR0912, PLR0915 - one branch per rule, and the rules ARE
    # the check; a reader must be able to see every way a register entry can be refused
    doc: object,
    root: Path,
) -> tuple[list[Disclosure], list[str]]:
    """Turn a parsed register into entries plus every reason it is not acceptable."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return [], ["register did not parse to a mapping"]
    unknown_top = sorted(set(doc) - REGISTER_TOP_KEYS)
    if unknown_top:
        errors.append(f"unknown top-level key(s): {unknown_top}")
    if doc.get("schema") != REGISTER_SCHEMA:
        errors.append(f"schema is {doc.get('schema')!r}, expected {REGISTER_SCHEMA!r}")
    raw_entries = doc.get("decisions")
    if not isinstance(raw_entries, list) or not raw_entries:
        return [], [*errors, "`decisions:` is missing or empty"]

    entries: list[Disclosure] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_entries, 1):
        where = f"decisions[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: not a mapping")
            continue
        unknown = sorted(set(raw) - REGISTER_KEYS)
        if unknown:
            errors.append(f"{where}: unknown key(s) {unknown}")
        missing = [k for k in REGISTER_REQUIRED if not raw.get(k)]
        if missing:
            errors.append(f"{where}: missing required key(s) {missing}")
            continue
        path = str(raw["path"])
        family = str(raw["family"])
        cls = str(raw["class"])
        date = str(raw["date"])
        decided_by = str(raw["decided_by"])
        reason = str(raw["reason"]).strip()
        scopes_raw = raw.get("scopes", ["tracked", "history"])
        if isinstance(scopes_raw, str):
            scopes_raw = [scopes_raw]
        if not isinstance(scopes_raw, list) or not scopes_raw:
            errors.append(f"{where}: `scopes` must be a non-empty sequence")
            continue
        scopes = tuple(str(s) for s in scopes_raw)
        where = f"{where} {path}::{family}"
        if family not in ALL_FAMILIES:
            errors.append(f"{where}: unknown family (known: {sorted(ALL_FAMILIES)})")
        if cls not in REGISTER_CLASSES:
            errors.append(f"{where}: unknown class {cls!r} (known: {sorted(REGISTER_CLASSES)})")
        bad_scopes = sorted(set(scopes) - REGISTER_SCOPES)
        if bad_scopes:
            errors.append(f"{where}: unknown scope(s) {bad_scopes}")
        try:
            datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            errors.append(f"{where}: date {date!r} is not YYYY-MM-DD")
        if len(reason) < MIN_REASON_CHARS:
            errors.append(
                f"{where}: reason is {len(reason)} chars, minimum {MIN_REASON_CHARS} - "
                "a one-line reason is not a decision somebody can check"
            )
        if (path, family) in seen:
            errors.append(f"{where}: duplicate (path, family)")
        seen.add((path, family))
        if (path, family) in WAIVER_INDEX:
            errors.append(f"{where}: already granted by the code ALLOWLIST; grant it once")
        if "tracked" in scopes and not (root / path).exists():
            errors.append(f"{where}: scope 'tracked' but the path does not exist at HEAD")
        entries.append(
            Disclosure(
                path=path,
                family=family,
                cls=cls,
                date=date,
                decided_by=decided_by,
                reason=reason,
                scopes=scopes,
            )
        )
    return entries, errors


# Module state. `install_register` is the only writer, so the self-test can swap in a
# synthetic register and restore the real one without the scan functions knowing.
REGISTER_INDEX: dict[tuple[str, str], Disclosure] = {}
REGISTER_USED: set[tuple[str, str]] = set()


def install_register(entries: Sequence[Disclosure]) -> None:
    REGISTER_INDEX.clear()
    REGISTER_USED.clear()
    for entry in entries:
        REGISTER_INDEX[(entry.path, entry.family)] = entry


def load_register(
    root: Path, rel: str = REGISTER_DEFAULT
) -> tuple[list[Disclosure], list[str], bool]:
    """Read, parse and validate the register. Never raises; errors are returned."""
    target = root / rel
    if not target.exists():
        return [], [], False
    text = read_text(target)
    if text is None:
        return [], [f"{rel}: not readable as UTF-8 text"], True
    try:
        doc = parse_minimal_yaml(text)
    except RegisterSyntaxError as exc:
        return [], [f"{rel}: {exc}"], True
    entries, errors = validate_register(doc, root)
    return entries, [f"{rel}: {e}" for e in errors], True


# ══════════════════════════════════════════════════════════════════════════════════
# Result model
# ══════════════════════════════════════════════════════════════════════════════════


@dataclass
class Finding:
    path: str
    line: int
    family: str
    preview: str
    scope: str  # "tracked" | "history" | "self-test"
    disposition: str  # "UNRESOLVED" | "ALLOWLISTED" | "DISCLOSED"
    reason: str = ""
    commit: str = ""
    disclosure_class: str = ""
    decided: str = ""
    decided_by: str = ""

    def to_json(self) -> dict[str, object]:
        row: dict[str, object] = {
            "path": self.path,
            "line": self.line,
            "family": self.family,
            "preview": self.preview,
            "scope": self.scope,
            "disposition": self.disposition,
        }
        if self.commit:
            row["commit"] = self.commit
        if self.disclosure_class:
            row["class"] = self.disclosure_class
            row["date"] = self.decided
            row["decided_by"] = self.decided_by
        if self.reason:
            row["reason"] = self.reason
        return row


@dataclass
class Row:
    check: str
    title: str
    status: str  # PASS | FAIL | INFO
    command: str
    observed: str
    findings: list[Finding] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        return {
            "check": self.check,
            "title": self.title,
            "status": self.status,
            "command": self.command,
            "observed": self.observed,
            "unresolved": sum(1 for f in self.findings if f.disposition == "UNRESOLVED"),
            "allowlisted": sum(1 for f in self.findings if f.disposition == "ALLOWLISTED"),
            "disclosed": sum(1 for f in self.findings if f.disposition == "DISCLOSED"),
            "findings": [f.to_json() for f in self.findings],
            "detail": self.detail,
        }


# ══════════════════════════════════════════════════════════════════════════════════
# Primitives
# ══════════════════════════════════════════════════════════════════════════════════


def git(root: Path, *args: str, check: bool = True) -> str:
    """Run git and return stdout. The only subprocess this program ever starts."""
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed [{proc.returncode}]: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout.decode("utf-8", "replace")


def git_status(root: Path, *args: str) -> int:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    return proc.returncode


def shannon(token: str) -> float:
    counts = Counter(token)
    n = len(token)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def redact_preview(value: str) -> str:
    """EVERY preview is redacted, in every disposition, with no exception.

    This used to take a `verbatim` flag: a waiver could mark a value "public by design"
    — AWS's own documentation placeholders — and the preview would print it in full, on
    the argument that an audit which redacts a value anybody can read tells the reader
    less, not more. The argument is sound and the mechanism was not, because this
    program scans every TRACKED file and `qa/public-readiness.json` is a tracked file:

        HEAD's committed copy         8 occurrences of the placeholder
        after one regeneration      420
        after the next              452          (+32 per run, unbounded)

    Each run wrote N verbatim previews; the next run found all N and wrote N + 32. The
    artefact grew monotonically and would never have reached a fixed point. It never
    went red, because the pair was allowlisted — which is precisely why it went
    unnoticed.

    Nothing is lost by redacting uniformly. Every waiver that used to set `verbatim`
    names its value in its REASON, in prose, once: `AKIAIOSFODNN7EXAMPLE` and
    `wJalrXUtnFEMI/...` are still legible to a reviewer, still exactly once each, and no
    longer multiply. `Waiver.verbatim` survives as documentation — it is reported in the
    JSON as an assertion that the value is public by design — and no longer controls
    what gets printed. Detection is untouched: same patterns, same thresholds, same
    families, same dispositions. Only the rendering changed.
    """
    return f"{value[:6]}...(redacted, len {len(value)})"


def read_text(path: Path) -> str | None:
    """Return decoded text, or None for binary/unreadable files."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


# ══════════════════════════════════════════════════════════════════════════════════
# The scan itself — one function, used by the tracked scan, the history scan and the
# self-test, so the self-test exercises the code the audit actually runs.
# ══════════════════════════════════════════════════════════════════════════════════


def scan_line(line: str) -> Iterator[tuple[str, str]]:
    """Yield (family, matched_text) for every secret-family hit on one line."""
    for family, pattern in RE_KNOWN_PREFIX.items():
        for match in pattern.finditer(line):
            yield family, match.group(0)

    # AWS account id, contextual.
    has_context = RE_ACCOUNT_CONTEXT.search(line) is not None
    for match in RE_TWELVE.finditer(line):
        value = match.group(0)
        if value == FOUNDER_ACCOUNT or (has_context and value not in AWS_DOC_ACCOUNTS):
            yield "aws_account_id", value

    # High-entropy token beside a secret-shaped key name.
    if len(line) <= MAX_SCAN_LINE and RE_SECRET_KEYNAME.search(line):
        for match in RE_CANDIDATE_TOKEN.finditer(line):
            token = match.group(0)
            if RE_DOTTED_IDENT.match(token):
                continue
            preamble = line[max(0, match.start() - 60) : match.start()]
            if not RE_SECRET_KEYNAME.search(preamble):
                continue
            if shannon(token) >= ENTROPY_FLOOR:
                yield "high_entropy_secret", token


def scan_text(path: str, text: str, scope: str, commit: str = "") -> list[Finding]:
    out: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for family, matched in scan_line(line):
            out.append(build_finding(path, lineno, family, matched, scope, commit))
    return out


def build_finding(
    path: str, lineno: int, family: str, matched: str, scope: str, commit: str = ""
) -> Finding:
    """Assign one of the three dispositions. Order matters and is checked: the code
    allowlist wins, then the register, then red. A register entry that duplicates an
    allowlist entry is a validation error, so the two can never disagree silently."""
    waiver = WAIVER_INDEX.get((path, family))
    if waiver is not None:
        return Finding(
            path=path,
            line=lineno,
            family=family,
            preview=redact_preview(matched),
            scope=scope,
            disposition="ALLOWLISTED",
            reason=waiver.reason,
            commit=commit,
        )
    entry = REGISTER_INDEX.get((path, family))
    if entry is not None and scope in entry.scopes:
        REGISTER_USED.add((path, family))
        return Finding(
            path=path,
            line=lineno,
            family=family,
            # A disclosed value is masked, like every other. See redact_preview().
            preview=redact_preview(matched),
            scope=scope,
            disposition="DISCLOSED",
            reason=entry.reason,
            commit=commit,
            disclosure_class=entry.cls,
            decided=entry.date,
            decided_by=entry.decided_by,
        )
    return Finding(
        path=path,
        line=lineno,
        family=family,
        preview=redact_preview(matched),
        scope=scope,
        disposition="UNRESOLVED",
        commit=commit,
    )


def scan_paths(root: Path, rel_paths: Sequence[str], scope: str) -> list[Finding]:
    out: list[Finding] = []
    for rel in rel_paths:
        text = read_text(root / rel)
        if text is None:
            continue
        out.extend(scan_text(rel, text, scope))
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# Checks
# ══════════════════════════════════════════════════════════════════════════════════


def tracked_files(root: Path) -> list[str]:
    return [p for p in git(root, "ls-files", "-z").split("\0") if p]


def summarise(findings: Iterable[Finding]) -> tuple[int, int, int, Counter[str]]:
    findings = list(findings)
    unresolved = sum(1 for f in findings if f.disposition == "UNRESOLVED")
    allowlisted = sum(1 for f in findings if f.disposition == "ALLOWLISTED")
    disclosed = sum(1 for f in findings if f.disposition == "DISCLOSED")
    by_family: Counter[str] = Counter(f.family for f in findings)
    return unresolved, allowlisted, disclosed, by_family


def check_secrets_tracked(root: Path, files: Sequence[str]) -> Row:
    findings = scan_paths(root, files, "tracked")
    unresolved, allowlisted, disclosed, by_family = summarise(findings)
    families = ", ".join(f"{k}={v}" for k, v in sorted(by_family.items())) or "no hits"
    return Row(
        check="secrets_tracked",
        title="Secret scan over every tracked file at HEAD",
        status="FAIL" if unresolved else "PASS",
        command="git ls-files -z  |  scan 8 families over each file's content",
        observed=(
            f"{len(files)} tracked paths scanned; {len(findings)} hits "
            f"({unresolved} unresolved, {allowlisted} allowlisted, {disclosed} disclosed); "
            f"{families}"
        ),
        findings=findings,
        detail={"tracked_paths": len(files), "families": dict(by_family)},
    )


def iter_history_additions(root: Path) -> Iterator[tuple[str, str, str]]:
    """Yield (commit, path, added_line) for every '+' line in every commit, all refs."""
    proc = subprocess.Popen(
        [
            "git",
            "log",
            "-p",
            "--all",
            "-U0",
            "--no-color",
            "--no-renames",
            "--format=%x01commit %H",
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.stdout is None:  # pragma: no cover - stdout=PIPE guarantees a stream
        raise RuntimeError("git log -p produced no stdout stream")
    commit = ""
    path = ""
    try:
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("\x01commit "):
                commit = line[8:].strip()[:12]
                path = ""
                continue
            if line.startswith("+++ b/"):
                path = line[6:]
                continue
            if line.startswith("+++ /dev/null"):
                path = ""
                continue
            if line.startswith("+") and not line.startswith("+++") and path:
                yield commit, path, line[1:]
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()


def check_secrets_history(root: Path) -> Row:
    findings: list[Finding] = []
    lines = 0
    commits: set[str] = set()
    for commit, path, added in iter_history_additions(root):
        lines += 1
        commits.add(commit)
        for family, matched in scan_line(added):
            findings.append(build_finding(path, 0, family, matched, "history", commit))
    # Collapse: one row per (commit, path, family) is enough to act on.
    collapsed: dict[tuple[str, str, str], Finding] = {}
    for f in findings:
        collapsed.setdefault((f.commit, f.path, f.family), f)
    findings = sorted(collapsed.values(), key=lambda f: (f.disposition, f.path, f.family))
    unresolved, allowlisted, disclosed, by_family = summarise(findings)
    families = ", ".join(f"{k}={v}" for k, v in sorted(by_family.items())) or "no hits"
    return Row(
        check="secrets_history",
        title="Secret scan over every added line in every commit, all refs",
        status="FAIL" if unresolved else "PASS",
        command="git log -p --all -U0 --no-color  |  scan 8 families over '+' lines",
        observed=(
            f"{len(commits)} commits, {lines} added lines scanned; "
            f"{len(findings)} distinct (commit,path,family) hits "
            f"({unresolved} unresolved, {allowlisted} allowlisted, {disclosed} disclosed); "
            f"{families}"
        ),
        findings=findings,
        detail={"commits": len(commits), "added_lines": lines, "families": dict(by_family)},
    )


def check_ignored_and_untracked(root: Path, files: Sequence[str]) -> Row:
    probes = [".env", "terraform.tfstate", "terraform.tfstate.backup"]
    ignored = {p: git_status(root, "check-ignore", "-q", "--", p) == 0 for p in probes}
    tracked_env = [
        f for f in files if f == ".env" or (f.startswith(".env.") and f != ".env.example")
    ]
    tracked_state = [f for f in files if ".tfstate" in f]
    history_env = git(root, "log", "--all", "--oneline", "--diff-filter=A", "--", ".env").strip()
    history_state = git(
        root, "log", "--all", "--oneline", "--diff-filter=A", "--", "*.tfstate*"
    ).strip()
    ok = (
        all(ignored.values())
        and not tracked_env
        and not tracked_state
        and not history_env
        and not history_state
    )
    return Row(
        check="ignored_and_untracked",
        title=".env and *.tfstate* are gitignored, untracked, and never were committed",
        status="PASS" if ok else "FAIL",
        command=(
            "git check-ignore -q -- .env terraform.tfstate ; git ls-files ; "
            "git log --all --diff-filter=A -- .env '*.tfstate*'"
        ),
        observed=(
            f"check-ignore: {ignored}; tracked .env-like: {tracked_env or 'none'}; "
            f"tracked tfstate: {tracked_state or 'none'}; "
            f"history adds .env: {history_env or 'none'}; "
            f"history adds tfstate: {history_state or 'none'}"
        ),
        detail={
            "ignored": ignored,
            "tracked_env_like": tracked_env,
            "tracked_tfstate": tracked_state,
            "history_add_env": history_env,
            "history_add_tfstate": history_state,
        },
    )


def check_tracked_sizes(root: Path) -> Row:
    listing = git(root, "ls-files", "-s", "-z").split("\0")
    shas: list[tuple[str, str]] = []
    for entry in listing:
        if not entry:
            continue
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) >= 2:
            shas.append((parts[1], path))
    proc = subprocess.run(
        ["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        cwd=root,
        input="\n".join(sha for sha, _ in shas).encode("ascii"),
        capture_output=True,
        check=True,
    )
    sizes: dict[str, int] = {}
    for out_line in proc.stdout.decode("ascii", "replace").splitlines():
        bits = out_line.split()
        if len(bits) == 3 and bits[1] == "blob":
            sizes[bits[0]] = int(bits[2])
    total = 0
    oversize: list[dict[str, object]] = []
    biggest: list[tuple[int, str]] = []
    for sha, path in shas:
        size = sizes.get(sha, 0)
        total += size
        biggest.append((size, path))
        if size > MAX_TRACKED_BYTES:
            oversize.append({"path": path, "bytes": size})
    biggest.sort(reverse=True)
    top = [{"path": p, "bytes": s} for s, p in biggest[:5]]
    return Row(
        check="tracked_size",
        title=f"No tracked blob exceeds {MAX_TRACKED_BYTES // (1024 * 1024)} MiB",
        status="FAIL" if oversize else "PASS",
        command=(
            "git ls-files -s -z | "
            "git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'"
        ),
        observed=(
            f"{len(shas)} tracked blobs, {total} bytes total ({total / 1048576:.1f} MiB); "
            f"largest {biggest[0][1]} at {biggest[0][0]} bytes "
            f"({biggest[0][0] / 1048576:.2f} MiB); {len(oversize)} over the limit"
        ),
        detail={
            "blobs": len(shas),
            "total_bytes": total,
            "total_mib": round(total / 1048576, 2),
            "limit_bytes": MAX_TRACKED_BYTES,
            "oversize": oversize,
            "largest": top,
        },
    )


def _census(root: Path, *revs: str) -> tuple[int, Counter[str], Counter[str]]:
    raw = git(root, "log", *revs, "--format=%an <%ae>\x1f%cn <%ce>")
    authors: Counter[str] = Counter()
    committers: Counter[str] = Counter()
    commits = 0
    for line in raw.splitlines():
        if not line.strip():
            continue
        commits += 1
        author, _, committer = line.partition("\x1f")
        authors[author.strip()] += 1
        committers[committer.strip()] += 1
    return commits, authors, committers


def check_committer_census(root: Path) -> Row:
    """Two censuses, not one.

    `git log --all` walks every ref, and this repository has six `origin/dependabot/*`
    branches that `master` does not contain. Flipping visibility publishes those refs
    too, so a census of `master` alone understates what a visitor can read. Both
    numbers are reported: the gap between them IS the finding."""
    all_commits, all_authors, all_committers = _census(root, "--all")
    br_commits, br_authors, br_committers = _census(root, BRANCH_EXPECTED)
    all_ids = sorted(set(all_authors) | set(all_committers))
    br_ids = sorted(set(br_authors) | set(br_committers))
    extra_ids = [i for i in all_ids if i not in br_ids]
    noreply = [i for i in all_ids if "noreply" in i]
    refs = [
        ln.strip()
        for ln in git(root, "for-each-ref", "--format=%(refname)").splitlines()
        if ln.strip()
    ]
    return Row(
        check="committer_census",
        title="Every commit and every identity the flip will publish, on every ref",
        status="INFO",
        command=(
            "git log --all --format='%an <%ae>|%cn <%ce>' | sort | uniq -c ; "
            f"git log {BRANCH_EXPECTED} --format=... ; git for-each-ref"
        ),
        observed=(
            f"{all_commits} commits over {len(refs)} ref(s), {len(all_ids)} distinct "
            f"identity string(s): "
            + "; ".join(f"{i} x{all_authors.get(i, 0)}" for i in all_ids)
            + f" | {BRANCH_EXPECTED} alone: {br_commits} commits, {len(br_ids)} identity"
            + ("" if len(br_ids) == 1 else " strings")
            + (
                f" | {len(extra_ids)} identity string(s) reachable ONLY from a "
                f"non-{BRANCH_EXPECTED} ref: {extra_ids}"
                if extra_ids
                else ""
            )
        ),
        detail={
            "commits_all_refs": all_commits,
            "commits_on_branch": br_commits,
            "branch": BRANCH_EXPECTED,
            "refs": refs,
            "authors": dict(all_authors),
            "committers": dict(all_committers),
            "identities": all_ids,
            "identities_on_branch": br_ids,
            "identities_only_off_branch": extra_ids,
            "noreply_identities": noreply,
        },
    )


# An absolute path that names a user profile directory discloses the founder's local
# Windows account name. That is a strictly larger disclosure than a project directory
# layout, and the two are counted apart so the larger one can never be lost inside the
# smaller one's total. This classifies the *finding*; the register classifies the
# *decision*, and check 8 refuses a register that calls a username hit `abs-path-layout`.
RE_USER_PROFILE = re.compile(r"(?i)[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}([A-Za-z0-9_.<>-]+)")
PLACEHOLDER_USERS = frozenset({"someone", "user", "username", "you", "name", "<name>", "<you>"})


def path_disclosure_class(text: str) -> str:
    """`abs-path-username` if any hit names a real-looking profile directory."""
    for match in RE_USER_PROFILE.finditer(text):
        who = match.group(1)
        if who.lower() not in PLACEHOLDER_USERS and not who.startswith("<"):
            return "abs-path-username"
    return "abs-path-layout"


def check_absolute_paths(root: Path, files: Sequence[str]) -> Row:
    findings: list[Finding] = []
    per_file: Counter[str] = Counter()
    slash_only: Counter[str] = Counter()
    username_files: list[str] = []
    for rel in files:
        text = read_text(root / rel)
        if text is None:
            continue
        first_hit: dict[str, tuple[int, str]] = {}
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in RE_ABS_WIN_BACKSLASH.finditer(line):
                per_file[rel] += 1
                first_hit.setdefault("bs", (lineno, match.group(1)))
            for match in RE_ABS_WIN_SLASH.finditer(line):
                per_file[rel] += 1
                slash_only[rel] += 1
                first_hit.setdefault("fs", (lineno, match.group(1)))
        if not first_hit:
            continue
        if path_disclosure_class(text) == "abs-path-username":
            username_files.append(rel)
        for _kind, (lineno, matched) in sorted(first_hit.items()):
            findings.append(build_finding(rel, lineno, "abs_windows_path", matched, "tracked"))
    unresolved = sum(1 for f in findings if f.disposition == "UNRESOLVED")
    allowlisted = sum(1 for f in findings if f.disposition == "ALLOWLISTED")
    disclosed = sum(1 for f in findings if f.disposition == "DISCLOSED")
    return Row(
        check="absolute_paths",
        title="Absolute Windows paths in tracked files (drive letter + segment)",
        status="FAIL" if unresolved else "PASS",
        command=(
            r"git ls-files -z  |  scan for (?<![A-Za-z0-9_])[A-Za-z]:\\?<segment>\ "
            r"and :/<segment>/"
        ),
        observed=(
            f"{len(per_file)} file(s), {sum(per_file.values())} hit(s); "
            f"{unresolved} unresolved, {allowlisted} allowlisted, {disclosed} disclosed. "
            f"{len(username_files)} file(s) disclose a Windows account name "
            f"(abs-path-username): {sorted(username_files) or 'none'}"
        ),
        findings=findings,
        detail={
            "files": len(per_file),
            "hits": sum(per_file.values()),
            "per_file": dict(sorted(per_file.items())),
            "forward_slash_files": dict(sorted(slash_only.items())),
            "username_class_files": sorted(username_files),
            "layout_class_files": sorted(set(per_file) - set(username_files)),
        },
    )


def check_disclosure_register(
    root: Path,
    entries: Sequence[Disclosure],
    errors: Sequence[str],
    present: bool,
    rows: Sequence[Row],
) -> Row:
    """Check 8 — the register is only as trustworthy as its own audit.

    An allowlist that can only grow is an allowlist that stops meaning anything. This
    row refuses four ways for the register to decay:

    1. it does not parse, or an entry is missing a field / names an unknown family or
       class / carries a reason too short to be a decision;
    2. an entry granted nothing this run — the hit it was written for is gone, so the
       grant is now a standing permission for a future hit nobody looked at;
    3. an entry claims scope `tracked` for a path that no longer exists at HEAD;
    4. an entry classifies a Windows-account-name disclosure as mere layout.

    (1) and (3) are enforced in validate_register(); (2) and (4) here, because they
    need the scan results."""
    problems = list(errors)
    granted = {(e.path, e.family) for e in entries}
    unused = sorted(granted - REGISTER_USED)
    for path, family in unused:
        problems.append(
            f"{REGISTER_DEFAULT}: {path}::{family} granted nothing this run - "
            "delete the entry rather than leave a standing permission"
        )
    # (4) a username disclosure may not be filed as layout.
    misclassified: list[str] = []
    for entry in entries:
        if entry.family != "abs_windows_path" or "tracked" not in entry.scopes:
            continue
        text = read_text(root / entry.path)
        if text is None:
            continue
        actual = path_disclosure_class(text)
        if actual == "abs-path-username" and entry.cls != "abs-path-username":
            misclassified.append(f"{entry.path}: class {entry.cls!r} but the file names an account")
    problems.extend(
        f"{REGISTER_DEFAULT}: {m} - reclassify as abs-path-username" for m in misclassified
    )

    by_class: Counter[str] = Counter(e.cls for e in entries)
    disclosed_total = sum(1 for r in rows for f in r.findings if f.disposition == "DISCLOSED")
    if not present:
        observed = (
            f"{REGISTER_DEFAULT} is absent; nothing is DISCLOSED and every hit that is "
            "not in the code ALLOWLIST is UNRESOLVED"
        )
    else:
        observed = (
            f"{len(entries)} entry/entries granting {disclosed_total} finding(s); "
            f"{len(unused)} stale; classes "
            + (", ".join(f"{k}={v}" for k, v in sorted(by_class.items())) or "none")
        )
    return Row(
        check="disclosure_register",
        title="Every DISCLOSED grant is named, dated, classified and still load-bearing",
        status="FAIL" if problems else "PASS",
        command=(
            f"parse {REGISTER_DEFAULT} with the strict reader in this file; "
            "validate every entry; require each to have granted at least one finding"
        ),
        observed=observed,
        detail={
            "register": REGISTER_DEFAULT,
            "present": present,
            "entries": len(entries),
            "granted_findings": disclosed_total,
            "by_class": dict(by_class),
            "stale_entries": [f"{p}::{f}" for p, f in unused],
            "problems": problems,
            "class_vocabulary": REGISTER_CLASSES,
            "decisions": [e.to_json() for e in entries],
        },
    )


def check_repo_state(root: Path) -> Row:
    try:
        remote = git(root, "remote", "get-url", "origin").strip()
    except RuntimeError:
        remote = ""
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    head = git(root, "rev-parse", "--short", "HEAD").strip()
    upstream = f"origin/{BRANCH_EXPECTED}"
    behind = ahead = -1
    remote_head = ""
    try:
        counts = git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD").split()
        behind, ahead = int(counts[0]), int(counts[1])
        remote_head = git(root, "rev-parse", "--short", upstream).strip()
    except (RuntimeError, ValueError, IndexError):
        pass
    dirty = [ln for ln in git(root, "status", "--porcelain").splitlines() if ln.strip()]
    problems: list[str] = []
    if remote != REPO_EXPECTED:
        problems.append(f"origin is {remote!r}, expected {REPO_EXPECTED!r}")
    if branch != BRANCH_EXPECTED:
        problems.append(f"on branch {branch!r}, expected {BRANCH_EXPECTED!r}")
    if ahead != 0:
        problems.append(
            f"{ahead} commit(s) on HEAD are NOT on {upstream} - flipping public would "
            f"publish a tree that does not contain them"
        )
    if behind != 0:
        problems.append(f"{behind} commit(s) on {upstream} are not on HEAD")
    return Row(
        check="repo_state",
        title="The tree that would actually be published",
        status="PASS" if not problems else "FAIL",
        command=(
            "git remote get-url origin ; git rev-parse --abbrev-ref HEAD ; "
            f"git rev-list --left-right --count {upstream}...HEAD ; git status --porcelain"
        ),
        observed=(
            f"origin={remote or 'NONE'}; branch={branch}; HEAD={head}; "
            f"{upstream}={remote_head or 'UNKNOWN'}; behind={behind} ahead={ahead}; "
            f"working tree: {len(dirty)} uncommitted path(s)"
        ),
        detail={
            "remote": remote,
            "branch": branch,
            "head": head,
            "upstream": upstream,
            "upstream_head": remote_head,
            "behind": behind,
            "ahead": ahead,
            "uncommitted_paths": len(dirty),
            "problems": problems,
        },
    )


# ══════════════════════════════════════════════════════════════════════════════════
# Self-test
# ══════════════════════════════════════════════════════════════════════════════════


def planted_samples() -> dict[str, str]:
    """One line per family. Assembled from fragments so this file is not a hit itself."""
    b = "\\"
    return {
        # exactly 16 characters after the AKIA prefix - an earlier draft used 18 and the
        # self-test caught it, which is the whole reason this mode exists.
        "aws_access_key_id": "aws_access_key_id = " + "AKI" + "A" + "Q3RTVEXAMPLE7XKC",
        "github_token": "token: " + "ghp" + "_" + ("aB3" * 12),
        "slack_token": "slack = " + "xox" + "b-" + "12345678901-98765432109-aBcDeFgHiJkLmNoP",
        "private_key_block": "-" * 5 + "BEGIN " + "PRIVATE KEY" + "-" * 5,
        "crdb_cloud_api_key": "CRDB key " + "CCDB1" + "_" + "9wKq2ZtVn4Lm8XcR7bYs3PdF",
        "aws_account_id": "role_arn = arn:aws:iam::" + FOUNDER_ACCOUNT + ":role/mainline-dev",
        "bearer_or_jwt": (
            "Authorization: Bearer "
            "eyJ"
            "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        ),
        "high_entropy_secret": 'api_key = "' + "Zq7Z9vK2pR4tW8xL1nB6mC3hJ5sD0gF7yA2eU4iO" + '"',
        "abs_windows_path": f"path = Z:{b}Secret{b}Layout{b}thing.txt",
    }


LONG_REASON = (
    "A synthetic reason long enough to clear the minimum, planted by the self-test so "
    "that the surrounding defect is the only thing under examination."
)


def bad_register(**overrides: object) -> str:
    """One well-formed register entry with exactly one thing wrong with it.

    Written as a builder rather than nine hand-typed blobs so that each fixture differs
    from the good case in exactly the field its label names. A hand-written fixture with
    two defects would pass the self-test while only proving one of them is caught."""
    fields: dict[str, object] = {
        "path": "planted_github_token.txt",
        "family": "github_token",
        "class": "synthetic-test-fixture",
        "date": "2026-08-11",
        "decided_by": "self-test",
        "reason": f">-\n      {LONG_REASON}",
    }
    schema = str(overrides.pop("__schema__", REGISTER_SCHEMA))
    extra = str(overrides.pop("__extra_top__", ""))
    for key in list(overrides):
        if overrides[key] is None:
            fields.pop(key, None)
            overrides.pop(key)
    fields.update(overrides)  # type: ignore[arg-type]
    items = list(fields.items())
    head = f"  - {items[0][0]}: {items[0][1]}\n"
    tail = "".join(f"    {k}: {v}\n" for k, v in items[1:])
    return f"schema: {schema}\n{extra}decisions:\n{head}{tail}"


# Nine ways for a register to be wrong. Each must be refused; the self-test asserts it.
BAD_REGISTERS: tuple[tuple[str, str], ...] = (
    ("unknown family", bad_register(family="not_a_family")),
    ("unknown class", bad_register(**{"class": "it-is-fine"})),
    ("missing decided_by", bad_register(decided_by=None)),
    ("reason too short", bad_register(reason="fine")),
    ("date not ISO", bad_register(date="last tuesday")),
    ("unknown scope", bad_register(scopes="[everywhere]")),
    ("wrong schema", bad_register(__schema__="something.else/9")),
    (
        "duplicates a code ALLOWLIST entry",
        bad_register(
            path="spec/wire/checkpoint.md", family="private_key_block", scopes="[history]"
        ),
    ),
    ("unknown top-level key", bad_register(__extra_top__="please_pass: true\n")),
)


def self_test() -> int:  # noqa: PLR0912, PLR0915 - one linear proof, read top to bottom
    import shutil
    import tempfile

    samples = planted_samples()
    tmp = Path(tempfile.mkdtemp(prefix="mainline-readiness-selftest-"))
    failures: list[str] = []
    results: list[tuple[str, str, bool]] = []
    saved = dict(REGISTER_INDEX)
    got: set[str] = set()
    checks: list[tuple[str, bool, str]] = []

    def expect(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        if not ok:
            failures.append(name)

    try:
        install_register([])
        for family, payload in samples.items():
            rel = f"planted_{family}.txt"
            (tmp / rel).write_text(f"# planted fixture for {family}\n{payload}\n", encoding="utf-8")

        for family in samples:
            rel = f"planted_{family}.txt"
            text = (tmp / rel).read_text(encoding="utf-8")
            if family == "abs_windows_path":
                fired = any(
                    RE_ABS_WIN_BACKSLASH.search(ln) or RE_ABS_WIN_SLASH.search(ln)
                    for ln in text.splitlines()
                )
            else:
                fired = any(fam == family for fam, _matched in scan_text_families(text))
            results.append((family, rel, fired))
            if not fired:
                failures.append(f"{family} did not fire")

        # A scan over the whole planted tree must classify every hit UNRESOLVED:
        # nothing in a temp dir is allowlisted, so a silent pass would show up here.
        planted_paths = sorted(p.name for p in tmp.iterdir())
        findings = scan_paths(tmp, planted_paths, "self-test")
        got = {f.family for f in findings}
        expect(
            "every planted hit is UNRESOLVED with an empty register",
            all(f.disposition == "UNRESOLVED" for f in findings),
            str(sorted({f.disposition for f in findings})),
        )

        # Redaction must actually redact.
        expect(
            "every planted preview is redacted",
            all("redacted" in f.preview for f in findings),
            "",
        )

        # The self-test must also prove the negative: clean text fires nothing.
        (tmp / "clean.txt").write_text(
            "def hello() -> str:\n    return 'the database refused, and said why'\n",
            encoding="utf-8",
        )
        expect(
            "clean control file produces no finding",
            not scan_paths(tmp, ["clean.txt"], "self-test"),
        )

        # ── the detectors are exactly as strong as they were ──────────────────────
        measured_fp = detector_fingerprint()
        expect(
            "detector fingerprint unchanged (no pattern widened, no threshold lowered, "
            "no family removed)",
            measured_fp == DETECTOR_FINGERPRINT,
            f"measured {measured_fp}",
        )
        expect("all 8 secret families still declared", len(FAMILIES) == 8, str(sorted(FAMILIES)))
        expect("entropy floor still 4.2", ENTROPY_FLOOR == 4.2, repr(ENTROPY_FLOOR))
        expect(
            "the register cannot set verbatim",
            "verbatim" not in REGISTER_KEYS and "verbatim" not in REGISTER_TOP_KEYS,
        )
        # The amplification guard: no disposition, and no waiver flag, may cause a
        # matched value to be echoed in full. Checked against a real waiver that used
        # to be verbatim, not against a synthetic one.
        expect(
            "redact_preview takes no verbatim escape hatch",
            "verbatim" not in redact_preview.__code__.co_varnames,
        )
        echoed = redact_preview("AKIA" + "IOSFODNN7EXAMPLE")
        expect(
            "a public-by-design value is still redacted in previews",
            "IOSFODNN7EXAMPLE" not in echoed and "redacted" in echoed,
            echoed,
        )

        # ── DISCLOSED is granted only by an exact-path register entry ─────────────
        good = (
            f"schema: {REGISTER_SCHEMA}\n"
            "decisions:\n"
            "  - path: planted_github_token.txt\n"
            "    family: github_token\n"
            "    class: synthetic-test-fixture\n"
            "    scopes: [tracked]\n"
            "    date: 2026-08-11\n"
            "    decided_by: self-test\n"
            "    reason: >-\n"
            f"      {LONG_REASON}\n"
        )
        (tmp / "register.yaml").write_text(good, encoding="utf-8")
        entries, errors, present = load_register(tmp, "register.yaml")
        expect("a well-formed register parses with no errors", present and not errors, str(errors))
        install_register(entries)
        granted = scan_paths(tmp, ["planted_github_token.txt"], "tracked")
        expect(
            "the named (path, family) becomes DISCLOSED",
            bool(granted) and all(f.disposition == "DISCLOSED" for f in granted),
            str([f.disposition for f in granted]),
        )
        expect(
            "a DISCLOSED preview is still redacted (register cannot ask for verbatim)",
            all("redacted" in f.preview for f in granted),
        )

        # …and nothing else. Same family, different path: still red.
        (tmp / "elsewhere.txt").write_text(samples["github_token"] + "\n", encoding="utf-8")
        other = scan_paths(tmp, ["elsewhere.txt"], "tracked")
        expect(
            "the same family at an UNNAMED path stays UNRESOLVED",
            bool(other) and all(f.disposition == "UNRESOLVED" for f in other),
            str([f.disposition for f in other]),
        )
        # …and not in a scope it did not declare.
        hist = scan_paths(tmp, ["planted_github_token.txt"], "history")
        expect(
            "a tracked-only grant does not cover the history scope",
            bool(hist) and all(f.disposition == "UNRESOLVED" for f in hist),
            str([f.disposition for f in hist]),
        )
        # …and a still-planted secret in a file the register never names is still red.
        every = scan_paths(tmp, planted_paths, "tracked")
        still_red = {f.family for f in every if f.disposition == "UNRESOLVED"}
        expect(
            "one grant does not disarm the other 8 families",
            still_red == (set(samples) - {"github_token", "abs_windows_path"}),
            str(sorted(still_red)),
        )

        # ── every way of writing a bad register is refused ────────────────────────
        # The control first: bad_register() with NO override must be accepted. Without
        # it, a builder that emitted garbage would make all nine fixtures "fail
        # correctly" and prove nothing at all.
        (tmp / "control.yaml").write_text(bad_register(), encoding="utf-8")
        _c_entries, control_errors, _c_present = load_register(tmp, "control.yaml")
        expect(
            "control: the same fixture with NO defect is ACCEPTED",
            not control_errors,
            str(control_errors),
        )
        for label, blob in BAD_REGISTERS:
            (tmp / "bad.yaml").write_text(blob, encoding="utf-8")
            _bad_entries, bad_errors, _present = load_register(tmp, "bad.yaml")
            expect(f"register refused: {label}", bool(bad_errors), str(bad_errors))

        # Malformed YAML must raise rather than silently yield a partial document.
        for label, blob in (
            ("tab indentation", "schema: x\n\tdecisions: []\n"),
            ("anchor", f"schema: {REGISTER_SCHEMA}\nnote: &a hello\n"),
            ("no colon", f"schema: {REGISTER_SCHEMA}\nthis line has no key\n"),
            ("empty value", f"schema: {REGISTER_SCHEMA}\ndecisions:\n  - path:\n"),
        ):
            raised = False
            try:
                parse_minimal_yaml(blob)
            except RegisterSyntaxError:
                raised = True
            expect(f"parser rejects: {label}", raised)

        # ── the strict reader agrees with PyYAML, where PyYAML is available ───────
        cross = "PyYAML not importable - cross-check skipped"
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            pass
        else:
            mine = parse_minimal_yaml(good)
            theirs = yaml.safe_load(good)
            for entry in theirs.get("decisions", []):
                if "date" in entry:
                    entry["date"] = str(entry["date"])
            expect(
                "strict reader agrees with PyYAML on the register subset",
                mine == theirs,
                f"{mine} != {theirs}",
            )
            cross = f"PyYAML {yaml.__version__} agrees with the strict reader"
    finally:
        install_register(list(saved.values()))
        shutil.rmtree(tmp, ignore_errors=True)

    width = max(len(f) for f in samples)
    print("SELF-TEST - one planted secret per family, scanner must fire on each")
    print("-" * (width + 34))
    for family, rel, fired in results:
        print(f"  {'FIRED ' if fired else 'MISSED'}  {family.ljust(width)}  {rel}")
    print("-" * (width + 34))
    print(f"  families reached by scan_text(): {sorted(got)}")
    print("  control file (no secret)       : no findings")
    print()
    print("SELF-TEST - the DISCLOSED disposition, and the strength of the detectors")
    print("-" * (width + 34))
    for name, ok, detail in checks:
        suffix = f"   [{detail}]" if detail and not ok else ""
        print(f"  {'OK    ' if ok else 'FAILED'}  {name}{suffix}")
    print("-" * (width + 34))
    print(f"  detector fingerprint : {DETECTOR_FINGERPRINT}")
    print(f"  {cross}")
    if failures:
        print(f"\nSELF-TEST FAILED: {failures}")
        return 1
    print(
        f"\nSELF-TEST PASSED: {len(samples)} families, {len(samples)} fired, 0 missed; "
        f"{len(checks)} disposition/strength assertions, 0 failed"
    )
    return 0


def scan_text_families(text: str) -> Iterator[tuple[str, str]]:
    for line in text.splitlines():
        yield from scan_line(line)


# ══════════════════════════════════════════════════════════════════════════════════
# Reporting
# ══════════════════════════════════════════════════════════════════════════════════


def irreversibility(rows: Sequence[Row]) -> str:
    """The commit count is measured, not written down.

    An earlier version of this file hard-coded 'ALL 16 COMMITS'. By the time anybody
    read it the repository held 44 across 8 refs, so the one paragraph whose whole job
    is to make the reader feel the size of the act was understating it by 28 commits.
    A constant that describes a moving tree is a lie with a delay on it."""
    census = next((r for r in rows if r.check == "committer_census"), None)
    commits = census.detail.get("commits_all_refs", "?") if census else "?"
    refs = len(census.detail.get("refs", [])) if census else 0  # type: ignore[arg-type]
    return (
        "The flip from PRIVATE to PUBLIC is IRREVERSIBLE. GitHub's fork network, the "
        "GHArchive event stream, Software Heritage and search-engine caches all outlive "
        f"a revert, and the flip publishes ALL {commits} COMMITS on ALL {refs} REFS, not "
        "the tree at HEAD. A value masked at HEAD but present in an earlier commit is "
        "published anyway."
    )


def print_table(rows: Sequence[Row]) -> None:
    check_w = max(len(r.check) for r in rows)
    print()
    print("PUBLIC-READINESS AUDIT - github.com/Shaugato/mainline")
    print("=" * 100)
    print(f"{'STATUS'.ljust(7)}{'CHECK'.ljust(check_w + 2)}OBSERVED")
    print("-" * 100)
    for row in rows:
        print(f"{row.status.ljust(7)}{row.check.ljust(check_w + 2)}{row.observed}")
    print("-" * 100)

    unresolved = [f for r in rows for f in r.findings if f.disposition == "UNRESOLVED"]
    allowlisted = [f for r in rows for f in r.findings if f.disposition == "ALLOWLISTED"]
    disclosed = [f for r in rows for f in r.findings if f.disposition == "DISCLOSED"]
    print(
        f"findings: {len(unresolved)} UNRESOLVED, {len(allowlisted)} ALLOWLISTED, "
        f"{len(disclosed)} DISCLOSED"
    )

    if unresolved:
        print("\nUNRESOLVED - each of these must be fixed, allowlisted, or entered in")
        print(f"{REGISTER_DEFAULT} with a class, a date, a decider and a reason:")
        for f in unresolved:
            where = f"{f.commit}:{f.path}" if f.commit else f"{f.path}:{f.line}"
            print(f"  [{f.family}] {where}  {f.preview}")

    if disclosed:
        by_class: dict[str, list[Finding]] = {}
        for f in disclosed:
            by_class.setdefault(f.disclosure_class, []).append(f)
        print(f"\nDISCLOSED - granted by {REGISTER_DEFAULT}, grouped by class:")
        for cls in sorted(by_class):
            group = by_class[cls]
            seen_paths = sorted({f.path for f in group})
            print(f"  {cls}  ({len(group)} finding(s), {len(seen_paths)} path(s))")
            print(f"      {REGISTER_CLASSES.get(cls, '')}")
            for path in seen_paths:
                first = next(f for f in group if f.path == path)
                scopes = sorted({g.scope for g in group if g.path == path})
                print(
                    f"      - {path}  [{first.family}] {scopes}  {first.decided} {first.decided_by}"
                )

    if allowlisted:
        print("\nALLOWLISTED - documented decisions, grouped by (path, family):")
        seen: set[tuple[str, str]] = set()
        for f in allowlisted:
            key = (f.path, f.family)
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{f.family}] {f.path}")
            print(f"      {f.reason}")

    problems = [p for r in rows for p in r.detail.get("problems", [])]  # type: ignore[union-attr]
    if problems:
        print("\nBLOCKING PRECONDITIONS:")
        for p in problems:
            print(f"  - {p}")

    print()
    print(irreversibility(rows))
    print()


def build_document(
    rows: Sequence[Row], root: Path, entries: Sequence[Disclosure]
) -> dict[str, object]:
    unresolved = [f for r in rows for f in r.findings if f.disposition == "UNRESOLVED"]
    allowlisted = [f for r in rows for f in r.findings if f.disposition == "ALLOWLISTED"]
    disclosed = [f for r in rows for f in r.findings if f.disposition == "DISCLOSED"]
    failed = [r.check for r in rows if r.status == "FAIL"]
    by_class: Counter[str] = Counter(f.disclosure_class for f in disclosed)
    return {
        "schema": SCHEMA,
        "note": (
            "Measured, not asserted. Every row carries the command that produced it and "
            "what that command printed. Regenerate with "
            "`python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json`."
        ),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/submission/audit_public_readiness.py",
        "repo_root": root.name,
        "detector_fingerprint": detector_fingerprint(),
        "irreversibility": irreversibility(rows),
        "verdict": "READY" if not failed else "NOT READY",
        "failed_checks": failed,
        "dispositions": {
            "UNRESOLVED": "gating; the default for every hit",
            "ALLOWLISTED": f"non-gating; granted by ALLOWLIST in {Path(__file__).name}",
            "DISCLOSED": f"non-gating; granted by an exact-path entry in {REGISTER_DEFAULT}",
        },
        "totals": {
            "checks": len(rows),
            "passed": sum(1 for r in rows if r.status == "PASS"),
            "failed": len(failed),
            "informational": sum(1 for r in rows if r.status == "INFO"),
            "unresolved_findings": len(unresolved),
            "allowlisted_findings": len(allowlisted),
            "disclosed_findings": len(disclosed),
            "disclosed_by_class": dict(sorted(by_class.items())),
        },
        "families": FAMILIES,
        "allowlist": [
            {"path": w.path, "family": w.family, "verbatim": w.verbatim, "reason": w.reason}
            for w in ALLOWLIST
        ],
        "disclosure_register": {
            "path": REGISTER_DEFAULT,
            "schema": REGISTER_SCHEMA,
            "classes": REGISTER_CLASSES,
            "entries": [e.to_json() for e in entries],
        },
        "rows": [r.to_json() for r in rows],
    }


# ══════════════════════════════════════════════════════════════════════════════════
# --assert-absent: prove a rotated credential is nowhere, without republishing it
# ══════════════════════════════════════════════════════════════════════════════════


def assert_absent(root: Path, candidate: str) -> int:
    """Read one value from stdin; prove it is in no tracked file and no added line.

    Deliberately not a flag with a value: an argument vector is visible in `ps`, lands
    in a shell history, and would be captured by any CI log. The value is consumed
    from stdin, held in one local, and the only thing printed is a SHA-256 prefix, so
    the run is reproducible by anyone who holds the same secret and discloses nothing
    to anyone who does not."""
    import hashlib

    candidate = candidate.strip()
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    print("ASSERT-ABSENT - is this value anywhere in the repository?")
    print(f"  sha256(value)  {digest[:16]}...  (length {len(candidate)})")
    if len(candidate) < 8:
        print("  REFUSED: a value shorter than 8 characters would match everywhere.")
        return 2

    tracked_hits: list[str] = []
    for rel in tracked_files(root):
        text = read_text(root / rel)
        if text is None or candidate not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if candidate in line:
                tracked_hits.append(f"{rel}:{lineno}")
    history_hits: list[str] = []
    added = 0
    for commit, path, line in iter_history_additions(root):
        added += 1
        if candidate in line:
            history_hits.append(f"{commit}:{path}")
    print(f"  tracked files  {len(tracked_files(root))} scanned -> {len(tracked_hits)} hit(s)")
    print(f"  history        {added} added lines scanned -> {len(history_hits)} hit(s)")
    for hit in tracked_hits[:20]:
        print(f"    TRACKED  {hit}")
    for hit in sorted(set(history_hits))[:20]:
        print(f"    HISTORY  {hit}")
    if tracked_hits or history_hits:
        print("\nABSENT: NO - the value is in the repository. Rotate it again; do not flip.")
        return 1
    print("\nABSENT: YES - the value appears in no tracked file and in no added line.")
    return 0


# ══════════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════════


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_public_readiness",
        description=(
            "Evidence-backed checklist for the irreversible PRIVATE -> PUBLIC flip. "
            "Standard library only; the only subprocess is git; no network access."
        ),
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="write the machine rows to PATH (e.g. qa/public-readiness.json)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="plant one secret of every family in a temp tree; require the scanner to fire",
    )
    parser.add_argument(
        "--assert-absent",
        action="store_true",
        help=(
            "read ONE candidate value from stdin and prove it is in no tracked file and "
            "no added line on any ref. For the rotated mainline_judge password."
        ),
    )
    parser.add_argument(
        "--register",
        default=REGISTER_DEFAULT,
        help=f"the disclosure register (default: {REGISTER_DEFAULT})",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="repository root (default: the current directory)",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    if args.self_test:
        return self_test()

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"ERROR: {root} is not a git repository root. Run from the repo root.")
        return 2

    if args.assert_absent:
        return assert_absent(root, sys.stdin.read())

    entries, register_errors, register_present = load_register(root, args.register)
    # A register that does not validate grants nothing: entries are installed only when
    # every one of them is well-formed, so a typo cannot half-open the gate.
    install_register([] if register_errors else entries)

    files = tracked_files(root)
    rows = [
        check_secrets_tracked(root, files),
        check_secrets_history(root),
        check_ignored_and_untracked(root, files),
        check_tracked_sizes(root),
        check_committer_census(root),
        check_absolute_paths(root, files),
        check_repo_state(root),
    ]
    rows.append(check_disclosure_register(root, entries, register_errors, register_present, rows))

    print_table(rows)

    if args.json:
        out = Path(args.json)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(build_document(rows, root, entries), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {out}")

    failed = [r.check for r in rows if r.status == "FAIL"]
    if failed:
        print(f"VERDICT: NOT READY - failing checks: {', '.join(failed)}")
        return 1
    print(
        "VERDICT: READY - every finding is resolved, allowlisted with a reason, or "
        "disclosed by a dated register entry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
