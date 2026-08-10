#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none - this file makes no database claim. It asks the filesystem, `git` and
#     (when present) `gh` a fixed list of questions and reports the answers.
# I: SUB-GATE-1 - the submission is complete only when a program says so. No human
#    eyeballs a checklist at 16:50 EDT on 18 August 2026.
# RATIONALE: measured on this machine on 2026-08-10 -
#     `gh repo view --json visibility` -> {"visibility":"PRIVATE"}
#     `git rev-list --left-right --count origin/master...HEAD` -> `0<TAB>2`
#     `git diff --name-only origin/master..HEAD | wc -l` -> 98
#   Ninety-eight committed files - `scripts/proof/gate_refusal.py`, `conftest.py`,
#   `LICENSES/`, `docs/HONESTY.md` among them - exist on this disk and on no server.
#   Flipping the repository public before they are pushed publishes a tree in which the
#   proof this project is about does not exist. That is not a checklist item; it is the
#   single row this program exists to keep red until it is fixed.
"""The submission gate: exit non-zero while any rules requirement is unresolved.

Run it from the repository root::

    python scripts/submission/check_submission_ready.py
    python scripts/submission/check_submission_ready.py --json
    python scripts/submission/check_submission_ready.py --markdown
    python scripts/submission/check_submission_ready.py --check-urls
    python scripts/submission/check_submission_ready.py --self-test

Standard library only. No network unless ``--check-urls`` is given, and no credential
in any mode: repository visibility is read from ``$GITHUB_EVENT_PATH`` when running
inside GitHub Actions (the event payload already carries it, offline) and from ``gh``
when a logged-in CLI is on PATH. When neither can answer, the row is reported
``NOTRUN`` - "NOT CHECKED" - which is a refusal, never a pass.

The rows, one per official requirement plus the mechanical preconditions:

===  ======================  =========================================================
key                          asserts
===  ======================  =========================================================
 1   licence_file            root ``LICENSE`` exists and is non-empty
 2   remote_sync             ``origin/<branch>`` and ``HEAD`` are the same commit
 3   repo_public             ``repo_url`` resolved and the repository is public
 4   demo_url                ``demo_url`` resolved (and HTTP 200 under --check-urls)
 5   video_url               ``video_url`` resolved
 6   devpost_description     ``docs/submission/DEVPOST.md`` exists and is non-trivial
 7   tool_usage              ``docs/TOOL-USAGE.md`` names >=2 CRDB tools and >=1 AWS
 8   judge_access            ``judge_access`` resolved, and no credential in the file
 9   disclosure              ``DISCLOSURE.md`` exists; every commit inside the window
10   deadline                time remaining to 2026-08-18 17:00 EDT
===  ======================  =========================================================

Exit codes
----------

* ``0`` - every blocking row is PASS. The submission is mechanically complete.
* ``1`` - at least one blocking row is not PASS. A numbered remedy list follows the
  table, and each remedy is a literal command.
* ``2`` - the gate could not run (no repository, bad usage, unreadable JSON).

A row is resolved when, and only when, its status is ``PASS``. ``NOTRUN`` and ``WARN``
are unresolved by construction, so a check that did not run can never be mistaken for
a check that passed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── constants ────────────────────────────────────────────────────────────────────────────

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

#: The literal every unresolved field in `docs/submission/SUBMISSION.json` holds.
UNRESOLVED = "UNRESOLVED"

#: Deadline, both spellings. EDT is UTC-04:00, so 17:00 EDT is 21:00Z.
DEADLINE_UTC = datetime(2026, 8, 18, 21, 0, 0, tzinfo=UTC)
DEADLINE_LOCAL_TEXT = "2026-08-18 17:00 EDT"
EDT = timezone(timedelta(hours=-4), "EDT")

#: The declared submission window, evaluated in EDT, as published by
#: `docs/submission/DISCLOSURE.md` and `evidence/provenance/commit-window.json`.
WINDOW_START_EDT = datetime(2026, 8, 5, 0, 0, 0, tzinfo=EDT)
WINDOW_END_EDT = DEADLINE_UTC.astimezone(EDT)

#: Where the single write point lives, relative to the repository root.
SUBMISSION_JSON = Path("docs/submission/SUBMISSION.json")
DEVPOST_MD = Path("docs/submission/DEVPOST.md")
TOOL_USAGE_MD = Path("docs/TOOL-USAGE.md")
DISCLOSURE_MD = Path("docs/submission/DISCLOSURE.md")
LICENSE_FILE = Path("LICENSE")
READINESS_AUDIT = Path("scripts/submission/audit_public_readiness.py")

#: `owner/name`, used only to print an exact `gh` command in a remedy line.
GITHUB_SLUG = "Shaugato/mainline"

STATUS_PASS = "PASS"  # noqa: S105 - a status token, not a password
STATUS_FAIL = "FAIL"
STATUS_WARN = "WARN"
STATUS_NOTRUN = "NOTRUN"

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_CANNOT_RUN = 2

#: Minimum size for `DEVPOST.md` to count as a description rather than a stub. A Devpost
#: "about the project" field that is under this is not a description of five judging
#: axes; it is a placeholder somebody meant to come back to.
DEVPOST_MIN_BYTES = 1200
DEVPOST_MIN_LINES = 20

#: Tokens that mean "somebody meant to finish this sentence". Matched case-insensitively
#: and only as whole words.
#:
#: `UNRESOLVED` is deliberately NOT here. `docs/submission/DEVPOST.md` carries that
#: literal on purpose, in the field-by-field paste table, marking the three URLs that are
#: genuinely unresolved - which is the honest thing for it to do and is already reported
#: by the `demo_url`, `video_url` and `repo_public` rows. Counting it again here would
#: turn one fact into two red rows and make the table lie about how many distinct things
#: are wrong. `XXX` is absent for the opposite reason: it collides with identifier
#: conventions and fires on prose that is finished.
PLACEHOLDER_TOKENS = ("TODO", "TBD", "FIXME", "PLACEHOLDER")

#: The four CockroachDB tools the rules count. The requirement is ">= 2 CockroachDB
#: tools", and a tool is a product, not a SQL feature - `docs/TOOL-USAGE.md` names these
#: four and marks which are EXERCISED and which are DESIGNED.
CRDB_TOOLS: tuple[tuple[str, str], ...] = (
    ("CockroachDB (the database)", r"\bcockroachdb\s+v?\d+\.\d+|\bcockroachdb\s+itself\b"),
    ("CockroachDB Cloud / ccloud", r"\bcockroachdb\s+cloud\b|\bccloud\b"),
    ("CockroachDB Managed MCP Server", r"\bmcp\s+server\b"),
    ("CockroachDB Agent Skills", r"\bagent\s+skills\b"),
)

#: AWS services. One is required; naming more is not penalised.
AWS_SERVICES: tuple[tuple[str, str], ...] = (
    ("Amazon Bedrock", r"\bbedrock\b"),
    ("Amazon S3", r"\bs3\b|\bobject\s+lock\b"),
    ("AWS KMS", r"\bkms\b"),
    ("AWS CloudTrail", r"\bcloudtrail\b"),
    ("AWS Lambda", r"\blambda\b"),
    ("Amazon CloudFront", r"\bcloudfront\b"),
    ("Amazon CloudWatch", r"\bcloudwatch\b"),
    ("AWS IAM", r"\biam\b"),
    ("AWS SSM Parameter Store", r"\bssm\b|\bparameter\s+store\b"),
    ("Amazon EventBridge", r"\beventbridge\b"),
)

#: Value shapes that are credentials no matter what key they sit under. Each entry is
#: (family, compiled pattern). The gate refuses if any of them appears anywhere in
#: SUBMISSION.json, because that file is world-readable the instant the repo flips.
CREDENTIAL_SHAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws-temporary-key-id", re.compile(r"\bASIA[0-9A-Z]{16}\b")),
    (
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    ("openai-style-token", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("url-with-inline-password", re.compile(r"://[^/\s:@]+:[^/\s@]+@")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)

#: Keys whose *name* says the value is a secret. Matched as a WHOLE leaf name or as a
#: `_`-delimited suffix, never as a substring: measured on 2026-08-10, substring matching
#: fired on this repository's own documentation key `never_write_a_credential_here`,
#: which is a sentence about credentials and not a credential. `credentials_location` is
#: absent from both forms deliberately - a pointer to a vault is the one thing this file
#: is allowed to carry.
SECRETISH_KEYS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "passphrase",
    "credential",
)

#: Suffixes that make any key a secret-carrying key, however it is prefixed:
#: `aws_secret_access_key`, `judge_password`, `signing_key`.
SECRETISH_SUFFIXES = ("_key", "_secret", "_token", "_password", "_passwd", "_passphrase")


def key_names_a_secret(leaf: str) -> bool:
    """True when a key's own NAME says its value is a credential.

    Whole name or `_`-delimited suffix only. `never_write_a_credential_here` is a
    sentence; `aws_secret_access_key` is a key.
    """
    lowered = leaf.lower()
    if lowered in SECRETISH_KEYS:
        return True
    if any(lowered.endswith("_" + word) for word in SECRETISH_KEYS):
        return True
    return any(lowered.endswith(suffix) for suffix in SECRETISH_SUFFIXES)


#: A bare high-entropy blob: >= 32 characters drawn only from a base64/hex alphabet,
#: with none of the punctuation that makes a string a URL or a path. Long enough to
#: exclude every legitimate value this file holds, narrow enough to catch a pasted key.
OPAQUE_BLOB = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")


# ── the row ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Row:
    """One requirement, what was observed, and the literal command that resolves it."""

    key: str
    title: str
    requirement: str
    status: str
    observed: str
    remedy: list[str] = field(default_factory=list)
    blocking: bool = True
    detail: dict[str, Any] = field(default_factory=dict)
    #: The artefact a reader opens to check this row without trusting this program.
    evidence: str = ""
    #: The literal command that re-derives the status column. `docs/submission/RULES-MATRIX.md`
    #: prints this, so a reader never has to take the matrix's word for anything.
    rederive: str = ""

    @property
    def resolved(self) -> bool:
        """A row is resolved only when it PASSED. NOTRUN is not a pass; nor is WARN."""
        return self.status == STATUS_PASS

    @property
    def is_blocking_failure(self) -> bool:
        """True when this row alone is enough to refuse the submission."""
        return self.blocking and not self.resolved

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "requirement": self.requirement,
            "status": self.status,
            "observed": self.observed,
            "blocking": self.blocking,
            "resolved": self.resolved,
            "remedy": self.remedy,
            "detail": self.detail,
            "evidence": self.evidence,
            "rederive": self.rederive,
        }


class CannotRun(RuntimeError):
    """The gate could not ask its questions at all. Exit 2, never exit 0."""


# ── small helpers ────────────────────────────────────────────────────────────────────────


def _run(argv: list[str], cwd: Path, timeout: float = 20.0) -> tuple[int, str, str]:
    """Run *argv* with no shell. A missing binary is ``127``; a timeout is ``124``."""
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]}: timed out after {timeout:.0f}s"
    except OSError as exc:  # a wedged binary, a permission problem
        return 126, "", f"{argv[0]}: {exc}"
    return completed.returncode, completed.stdout, completed.stderr


def _survive_a_narrow_console() -> None:
    """Never let an encoding raise. A gate that dies printing is worse than no gate."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="replace")


def repo_root_of(start: Path) -> Path:
    """Walk up to the directory holding `.git`. Falls back to *start*."""
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return start.resolve()


def read_text(path: Path) -> str | None:
    """Read a file as UTF-8, or ``None`` when it is absent or unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


# ── pure analysis: everything below is exercised by --self-test ──────────────────────────


def parse_left_right(text: str) -> tuple[int, int]:
    """Parse ``git rev-list --left-right --count A...B`` into ``(behind, ahead)``.

    Left is the count reachable from *A* (the remote) and not *B*; right is the count
    reachable from *B* (``HEAD``) and not *A*. Measured on this repository on
    2026-08-10: ``0\t2`` - nothing to pull, two commits never pushed.

    Raises:
        ValueError: the output was not two integers.
    """
    fields = text.split()
    if len(fields) != 2:
        raise ValueError(f"expected two integers from rev-list --count, got {text!r}")
    try:
        return int(fields[0]), int(fields[1])
    except ValueError as exc:
        raise ValueError(f"non-integer in rev-list output {text!r}") from exc


def walk_json(node: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten a JSON document into ``(dotted.path, scalar)`` pairs, in document order."""
    out: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.extend(walk_json(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.extend(walk_json(value, f"{prefix}[{index}]"))
    else:
        out.append((prefix, node))
    return out


def find_unresolved(document: Any, only: tuple[str, ...] | None = None) -> list[str]:
    """Return the dotted paths whose value is the literal ``UNRESOLVED``.

    *only* restricts the search to paths that equal one of its entries or start with
    one followed by a dot, so `judge_access` covers `judge_access.how` without also
    covering the documentation strings that live beside it.
    """
    found: list[str] = []
    for path, value in walk_json(document):
        if only is not None and not any(path == p or path.startswith(p + ".") for p in only):
            continue
        if isinstance(value, str) and value.strip() == UNRESOLVED:
            found.append(path)
    return found


def scan_for_credentials(document: Any) -> list[str]:
    """Return one human-readable finding per credential-shaped value in *document*.

    Three families, in increasing order of how much they rely on judgement:

    1. a value matching a known credential shape, whatever key it sits under;
    2. a non-empty value under a key whose *name* says "secret";
    3. a bare high-entropy blob that is neither a URL nor a path.
    """
    findings: list[str] = []
    for path, value in walk_json(document):
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        for family, pattern in CREDENTIAL_SHAPES:
            if pattern.search(text):
                findings.append(f"{path}: looks like a {family}")
        leaf = path.rsplit(".", 1)[-1]
        if text != UNRESOLVED and key_names_a_secret(leaf):
            findings.append(f"{path}: a key named {leaf!r} carries a value")
        if text != UNRESOLVED and OPAQUE_BLOB.match(text):
            findings.append(f"{path}: a {len(text)}-character opaque blob")
    # Order-preserving de-duplication: one line per distinct finding.
    seen: set[str] = set()
    unique: list[str] = []
    for finding in findings:
        if finding not in seen:
            seen.add(finding)
            unique.append(finding)
    return unique


def classify_url(value: Any) -> tuple[bool, str]:
    """Is *value* a usable absolute http(s) URL? Return ``(ok, reason)``."""
    if not isinstance(value, str):
        return False, f"not a string ({type(value).__name__})"
    text = value.strip()
    if not text:
        return False, "empty"
    if text == UNRESOLVED:
        return False, "UNRESOLVED"
    if not text.lower().startswith(("http://", "https://")):
        return False, f"not an absolute http(s) URL: {text[:60]}"
    remainder = text.split("://", 1)[1]
    host = remainder.split("/", 1)[0]
    if not host or "." not in host:
        return False, f"no hostname in {text[:60]}"
    return True, text


def visibility_from_gh(stdout: str) -> str | None:
    """Pull ``visibility`` out of ``gh repo view --json visibility`` output."""
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    value = payload.get("visibility") if isinstance(payload, dict) else None
    return value.upper() if isinstance(value, str) and value else None


def visibility_from_event(payload: Any) -> str | None:
    """Pull visibility out of a GitHub Actions event payload, offline and unauthenticated.

    Every `push` and `pull_request` payload carries `repository.visibility` and
    `repository.private`. Reading them costs no token, no network and no `gh`, which is
    what lets the CI lane assert this row without a credential.
    """
    if not isinstance(payload, dict):
        return None
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return None
    stated = repository.get("visibility")
    if isinstance(stated, str) and stated:
        return stated.upper()
    private = repository.get("private")
    if isinstance(private, bool):
        return "PRIVATE" if private else "PUBLIC"
    return None


def remaining_to_deadline(
    now: datetime, deadline: datetime = DEADLINE_UTC
) -> tuple[int, int, float]:
    """Return ``(whole_days, leftover_hours, total_hours)``; all negative once past."""
    delta = deadline - now
    total_hours = delta.total_seconds() / 3600.0
    sign = -1 if total_hours < 0 else 1
    magnitude = abs(total_hours)
    days = int(magnitude // 24)
    hours = int(magnitude % 24)
    return sign * days, sign * hours, total_hours


def assess_description(text: str | None) -> tuple[bool, str, dict[str, Any]]:
    """Is a Devpost description present and non-trivial? Return ``(ok, reason, detail)``."""
    if text is None:
        return False, "absent", {"bytes": 0, "lines": 0}
    size = len(text.encode("utf-8"))
    lines = [line for line in text.splitlines() if line.strip()]
    detail: dict[str, Any] = {"bytes": size, "lines": len(lines), "placeholders": []}
    upper = text.upper()
    placeholders = [token for token in PLACEHOLDER_TOKENS if re.search(rf"\b{token}\b", upper)]
    detail["placeholders"] = placeholders
    if size < DEVPOST_MIN_BYTES:
        return False, f"{size} bytes, under the {DEVPOST_MIN_BYTES}-byte floor", detail
    if len(lines) < DEVPOST_MIN_LINES:
        return False, f"{len(lines)} non-blank lines, under {DEVPOST_MIN_LINES}", detail
    if placeholders:
        return False, "carries " + ", ".join(placeholders), detail
    return True, f"{size} bytes, {len(lines)} non-blank lines", detail


def count_named_tools(text: str | None) -> tuple[list[str], list[str]]:
    """Return ``(crdb_tools_named, aws_services_named)`` for a tool-usage document."""
    if not text:
        return [], []
    hay = text.lower()
    crdb = [name for name, pattern in CRDB_TOOLS if re.search(pattern, hay)]
    aws = [name for name, pattern in AWS_SERVICES if re.search(pattern, hay)]
    return crdb, aws


def parse_commit_log(stdout: str) -> list[dict[str, str]]:
    """Parse ``git log --format=%H%x1f%aI%x1f%cI%x1f%s`` into dictionaries."""
    commits: list[dict[str, str]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) < 4:
            continue
        commits.append(
            {"hash": parts[0], "author": parts[1], "committer": parts[2], "subject": parts[3]}
        )
    return commits


def window_violations(
    commits: list[dict[str, str]],
    start: datetime = WINDOW_START_EDT,
    end: datetime = WINDOW_END_EDT,
) -> list[str]:
    """Return one line per commit whose author OR committer date is outside the window.

    Both dates matter and for different reasons. The author date is when the work was
    written; the committer date is when it entered this history. A rebase that carries
    pre-window work into the tree moves only one of them, so checking one is checking
    half.
    """
    bad: list[str] = []
    for commit in commits:
        for field_name in ("author", "committer"):
            raw = commit.get(field_name, "")
            try:
                when = datetime.fromisoformat(raw)
            except ValueError:
                bad.append(f"{commit['hash'][:8]} has an unparseable {field_name} date {raw!r}")
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            if when < start or when > end:
                bad.append(
                    f"{commit['hash'][:8]} {field_name} date "
                    f"{when.isoformat()} is outside the window"
                )
    return bad


# ── collectors: each returns exactly one Row ─────────────────────────────────────────────


def row_licence_file(root: Path) -> Row:
    """Requirement 1a - an open-source licence file at the repository root."""
    path = root / LICENSE_FILE
    remedy = [
        "The root LICENSE is requirement 1 and a Stage One pass/fail. Restore it:",
        "    cp LICENSES/Apache-2.0.txt LICENSE",
        "    git add LICENSE && git commit -m 'chore: root LICENSE'",
    ]
    if not path.is_file():
        return Row(
            key="licence_file",
            title="root LICENSE",
            requirement="1 - public repo with an open-source LICENSE file",
            status=STATUS_FAIL,
            observed="LICENSE is not on disk",
            remedy=remedy,
        )
    size = path.stat().st_size
    if size == 0:
        return Row(
            key="licence_file",
            title="root LICENSE",
            requirement="1 - public repo with an open-source LICENSE file",
            status=STATUS_FAIL,
            observed="LICENSE is zero bytes",
            remedy=remedy,
        )
    head = (read_text(path) or "")[:4000]
    if "Apache License" in head:
        family = "Apache-2.0"
    elif "MIT License" in head:
        family = "MIT"
    elif "GNU GENERAL PUBLIC LICENSE" in head.upper():
        family = "GPL"
    else:
        family = "unrecognised text"
    return Row(
        key="licence_file",
        title="root LICENSE",
        requirement="1 - public repo with an open-source LICENSE file",
        status=STATUS_PASS,
        observed=f"{size} bytes, reads as {family}",
        detail={"bytes": size, "family": family},
    )


def row_remote_sync(root: Path, branch: str, remote: str) -> Row:  # noqa: PLR0911
    """Requirement 1b - the tree a judge clones is the tree on this disk.

    This is the row that matters most today. Ninety-eight files, the proof among them,
    are committed here and absent from the server.
    """
    requirement = "1 - public repo with an open-source LICENSE file"
    title = "remote is in sync"
    push_remedy = [
        "Push. Nothing else on this list matters while the server lacks the proof:",
        f"    git push {remote} {branch}",
        f"    git rev-list --left-right --count {remote}/{branch}...HEAD    # expect: 0<TAB>0",
    ]

    rc, out, err = _run(["git", "rev-parse", "--git-dir"], root)
    if rc != 0:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - git is unavailable here ({err.strip() or rc})",
            remedy=["Install git, or run this gate from inside the repository."],
        )

    rc, out, err = _run(["git", "rev-parse", "--verify", f"{remote}/{branch}"], root)
    if rc != 0:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - no ref {remote}/{branch} in this checkout",
            remedy=[
                "Fetch the remote-tracking ref this row compares against:",
                f"    git fetch {remote} {branch}",
                "In CI, check out with fetch-depth: 0 so the ref exists.",
            ],
        )

    rc, out, err = _run(
        ["git", "rev-list", "--left-right", "--count", f"{remote}/{branch}...HEAD"], root
    )
    if rc != 0:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - rev-list refused ({err.strip() or rc})",
            remedy=[f"    git fetch {remote} {branch}"],
        )
    try:
        behind, ahead = parse_left_right(out)
    except ValueError as exc:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - {exc}",
            remedy=[f"    git rev-list --left-right --count {remote}/{branch}...HEAD"],
        )

    _, diff_out, _ = _run(["git", "diff", "--name-only", f"{remote}/{branch}..HEAD"], root)
    unpushed_files = len([line for line in diff_out.splitlines() if line.strip()])
    _, porcelain, _ = _run(["git", "status", "--porcelain"], root)
    dirty = len([line for line in porcelain.splitlines() if line.strip()])
    detail = {"ahead": ahead, "behind": behind, "unpushed_files": unpushed_files, "dirty": dirty}

    if ahead > 0:
        noun = "commit" if ahead == 1 else "commits"
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=(
                f"{ahead} {noun} ahead of {remote}/{branch}, "
                f"{unpushed_files} file(s) on this disk and on no server"
            ),
            remedy=push_remedy,
            detail=detail,
        )
    if behind > 0:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{behind} commit(s) behind {remote}/{branch}",
            remedy=[
                "The server has work this checkout does not. Reconcile before publishing:",
                f"    git pull --ff-only {remote} {branch}",
            ],
            detail=detail,
        )
    if dirty > 0:
        return Row(
            key="remote_sync",
            title=title,
            requirement=requirement,
            status=STATUS_WARN,
            observed=(
                f"in sync with {remote}/{branch}, but {dirty} path(s) are uncommitted "
                "and will not be published"
            ),
            remedy=[
                "Uncommitted work is invisible to a judge. Commit it or discard it:",
                "    git status --porcelain",
                "    git add -A && git commit -m '<what changed>'",
                f"    git push {remote} {branch}",
            ],
            detail=detail,
        )
    return Row(
        key="remote_sync",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"HEAD == {remote}/{branch}, working tree clean",
        detail=detail,
    )


def read_visibility(root: Path) -> tuple[str | None, str]:
    """Return ``(visibility, source)``. Never guesses; ``None`` means nobody could say."""
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        text = read_text(Path(event_path))
        if text is not None:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            visibility = visibility_from_event(payload)
            if visibility is not None:
                return visibility, "$GITHUB_EVENT_PATH (no credential, no network)"
    if shutil.which("gh") is not None:
        rc, out, err = _run(["gh", "repo", "view", "--json", "visibility"], root, timeout=30.0)
        if rc == 0:
            visibility = visibility_from_gh(out)
            if visibility is not None:
                return visibility, "gh repo view --json visibility"
        return None, f"gh is present but refused ({(err or out).strip()[:80] or rc})"
    return None, "gh is not on PATH and this is not a GitHub Actions run"


def row_repo_public(root: Path, submission: dict[str, Any] | None) -> Row:
    """Requirement 1c - the repository a judge opens is public, and its URL is recorded."""
    requirement = "1 - public repo with an open-source LICENSE file"
    title = "repository is public"
    flip = [
        "Flipping visibility is IRREVERSIBLE in practice - forks, clones and caches",
        "outlive the flip. Run the readiness audit to exit 0 FIRST:",
        f"    python {READINESS_AUDIT.as_posix()}",
        (
            f"    gh repo edit {GITHUB_SLUG} --visibility public"
            " --accept-visibility-change-consequences"
        ),
    ]

    url_ok, url_reason = classify_url((submission or {}).get("repo_url"))
    visibility, source = read_visibility(root)

    if visibility is None:
        return Row(
            key="repo_public",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - {source}",
            remedy=[
                "Nothing answered, so nothing is asserted. Ask GitHub directly:",
                f"    gh repo view {GITHUB_SLUG} --json visibility",
                *flip,
            ],
            detail={"visibility": None, "source": source, "repo_url": url_reason},
        )
    if visibility != "PUBLIC":
        return Row(
            key="repo_public",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"visibility is {visibility} [{source}]",
            remedy=flip,
            detail={"visibility": visibility, "source": source, "repo_url": url_reason},
        )
    if not url_ok:
        return Row(
            key="repo_public",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"public [{source}], but repo_url is {url_reason}",
            remedy=[
                f"Write the URL a judge will open into {SUBMISSION_JSON.as_posix()}:",
                f'    "repo_url": "https://github.com/{GITHUB_SLUG}"',
            ],
            detail={"visibility": visibility, "source": source, "repo_url": url_reason},
        )
    return Row(
        key="repo_public",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"PUBLIC [{source}], repo_url {url_reason}",
        detail={"visibility": visibility, "source": source, "repo_url": url_reason},
    )


def http_status(url: str, timeout: float = 15.0) -> tuple[int | None, str]:
    """Fetch *url* and return ``(status, note)``. Imported lazily: no import, no network.

    A HEAD is tried first because it is cheaper and because a static host answers it;
    hosts that refuse HEAD get a GET. Anything that raises is reported, never swallowed.
    """
    import urllib.error
    import urllib.request

    for method in ("HEAD", "GET"):
        request = urllib.request.Request(  # noqa: S310 - scheme validated by classify_url
            url, method=method, headers={"User-Agent": "mainline-submission-gate/1"}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return int(response.status), f"{method} {response.status}"
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue
            return int(exc.code), f"{method} {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            if method == "HEAD":
                continue
            return None, f"{type(exc).__name__}: {exc}"
    return None, "both HEAD and GET failed"


def row_demo_url(submission: dict[str, Any] | None, check_urls: bool) -> Row:
    """Requirement 2 - a URL to a functional demo app. Stage One pass/fail."""
    requirement = "2 - a URL to a functional demo app"
    title = "demo URL"
    remedy = [
        f"There is exactly one place to write it - {SUBMISSION_JSON.as_posix()}:",
        '    "demo_url": "https://<the deployed console>"',
        "Then prove it answers, from a machine that is not the one that deployed it:",
        "    python scripts/submission/check_submission_ready.py --check-urls",
    ]
    if submission is None:
        return Row(
            key="demo_url",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - {SUBMISSION_JSON.as_posix()} is unreadable",
            remedy=remedy,
        )
    ok, reason = classify_url(submission.get("demo_url"))
    if not ok:
        return Row(
            key="demo_url",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"demo_url is {reason}",
            remedy=remedy,
            detail={"demo_url": submission.get("demo_url")},
        )
    if not check_urls:
        return Row(
            key="demo_url",
            title=title,
            requirement=requirement,
            status=STATUS_PASS,
            observed=f"{reason} (not fetched; pass --check-urls to require HTTP 200)",
            detail={"demo_url": reason, "fetched": False},
        )
    status, note = http_status(reason)
    if status != 200:
        return Row(
            key="demo_url",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{reason} answered {note}",
            remedy=[
                "A judge opening this URL sees what you just saw. Fix the deployment,",
                "then re-run:",
                "    python scripts/submission/check_submission_ready.py --check-urls",
            ],
            detail={"demo_url": reason, "http": note},
        )
    return Row(
        key="demo_url",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"{reason} -> {note}",
        detail={"demo_url": reason, "http": note, "fetched": True},
    )


def row_video_url(submission: dict[str, Any] | None, check_urls: bool) -> Row:
    """Requirement 4 - a video under three minutes, on YouTube or Vimeo."""
    requirement = "4 - demo video under 3 minutes on YouTube or Vimeo"
    title = "video URL"
    remedy = [
        "The script, the shot list and the seeded state are in the tree and CI-validated;",
        "the film is the founder's to record. Upload it UNLISTED, then:",
        f'    edit {SUBMISSION_JSON.as_posix()}: "video_url": "https://youtu.be/<id>"',
        "    (see docs/submission/VIDEO-KIT.md for the shot list and the VO)",
    ]
    if submission is None:
        return Row(
            key="video_url",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - {SUBMISSION_JSON.as_posix()} is unreadable",
            remedy=remedy,
        )
    ok, reason = classify_url(submission.get("video_url"))
    if not ok:
        return Row(
            key="video_url",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"video_url is {reason}",
            remedy=remedy,
            detail={"video_url": submission.get("video_url")},
        )
    host = reason.split("://", 1)[1].split("/", 1)[0].lower()
    known = any(marker in host for marker in ("youtube.com", "youtu.be", "vimeo.com"))
    if not known:
        return Row(
            key="video_url",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{reason} is not on YouTube or Vimeo (host {host})",
            remedy=["The rules name YouTube and Vimeo. Re-upload to one of them."],
            detail={"video_url": reason, "host": host},
        )
    if check_urls:
        status, note = http_status(reason)
        if status != 200:
            return Row(
                key="video_url",
                title=title,
                requirement=requirement,
                status=STATUS_FAIL,
                observed=f"{reason} answered {note}",
                remedy=[
                    "A private video is invisible to a judge. Set it to Unlisted or Public:",
                    "    open the video's visibility settings and re-run --check-urls",
                ],
                detail={"video_url": reason, "http": note},
            )
        return Row(
            key="video_url",
            title=title,
            requirement=requirement,
            status=STATUS_PASS,
            observed=f"{reason} -> {note}",
            detail={"video_url": reason, "http": note, "fetched": True},
        )
    return Row(
        key="video_url",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"{reason} (not fetched; pass --check-urls to require HTTP 200)",
        detail={"video_url": reason, "fetched": False},
    )


def row_devpost(root: Path) -> Row:
    """Requirement 3 - a text description of the features."""
    requirement = "3 - text description of the features"
    text = read_text(root / DEVPOST_MD)
    ok, reason, detail = assess_description(text)
    if ok:
        return Row(
            key="devpost_description",
            title="Devpost description",
            requirement=requirement,
            status=STATUS_PASS,
            observed=f"{DEVPOST_MD.as_posix()}: {reason}",
            detail=detail,
        )
    return Row(
        key="devpost_description",
        title="Devpost description",
        requirement=requirement,
        status=STATUS_FAIL,
        observed=f"{DEVPOST_MD.as_posix()}: {reason}",
        remedy=[
            "The Devpost form is a paste, not a writing session. Write the source of that",
            "paste, mapped to the five equally weighted judging axes:",
            f"    {DEVPOST_MD.as_posix()}",
            "Then check the prose against the nine SUB rules before pasting:",
            "    python scripts/submission/check_submission_prose.py",
        ],
        detail=detail,
    )


def row_tool_usage(root: Path) -> Row:
    """Requirement 5 - which CockroachDB and AWS services, and how."""
    requirement = "5 - documented CockroachDB and AWS usage (>=2 CRDB tools, >=1 AWS)"
    text = read_text(root / TOOL_USAGE_MD)
    crdb, aws = count_named_tools(text)
    detail = {"crdb_tools": crdb, "aws_services": aws}
    if text is None:
        return Row(
            key="tool_usage",
            title="tool usage documented",
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{TOOL_USAGE_MD.as_posix()} is not on disk",
            remedy=[
                "Write the document the rules ask for, naming each tool and what it does here:",
                f"    {TOOL_USAGE_MD.as_posix()}",
            ],
            detail=detail,
        )
    if len(crdb) < 2 or len(aws) < 1:
        return Row(
            key="tool_usage",
            title="tool usage documented",
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{len(crdb)} CockroachDB tool(s), {len(aws)} AWS service(s) named",
            remedy=[
                "The rules require at least two CockroachDB tools and at least one AWS",
                f"service, named and explained. Extend {TOOL_USAGE_MD.as_posix()}, then:",
                "    python scripts/submission/check_submission_ready.py",
            ],
            detail=detail,
        )
    return Row(
        key="tool_usage",
        title="tool usage documented",
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"{len(crdb)} CockroachDB tools, {len(aws)} AWS services named",
        detail=detail,
    )


def row_judge_access(submission: dict[str, Any] | None) -> Row:  # noqa: PLR0911
    """Requirement 6 - free, unrestricted judge access, and no credential in this file."""
    requirement = "6 - free, unrestricted access for judges"
    title = "judge access"
    remedy = [
        f"Resolve all three members in {SUBMISSION_JSON.as_posix()}:",
        '    "judge_access": {',
        '      "required": false,',
        '      "how": "<one sentence: what a judge does to get in>",',
        '      "credentials_location": "<where a credential lives, never the credential>"',
        "    }",
        "If access needs no credential, set required to false and say so in `how`;",
        '`credentials_location` then reads "none - no credential is required".',
    ]
    if submission is None:
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - {SUBMISSION_JSON.as_posix()} is unreadable",
            remedy=remedy,
        )

    leaks = scan_for_credentials(submission)
    if leaks:
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{len(leaks)} credential-shaped value(s) in {SUBMISSION_JSON.as_posix()}",
            remedy=[
                "This file goes public with the repository. Remove the value and leave a",
                "pointer in its place, then rotate whatever was written here:",
                *[f"    {leak}" for leak in leaks],
            ],
            detail={"credential_findings": leaks},
        )

    unresolved = find_unresolved(submission, only=("judge_access",))
    access = submission.get("judge_access")
    if not isinstance(access, dict):
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed="judge_access is not an object",
            remedy=remedy,
        )
    missing = [name for name in ("required", "how", "credentials_location") if name not in access]
    if missing:
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed="judge_access is missing " + ", ".join(missing),
            remedy=remedy,
            detail={"missing": missing},
        )
    if unresolved:
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{len(unresolved)} unresolved: " + ", ".join(unresolved),
            remedy=remedy,
            detail={"unresolved": unresolved},
        )
    if not isinstance(access.get("required"), bool):
        return Row(
            key="judge_access",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"judge_access.required is {access.get('required')!r}, not a boolean",
            remedy=remedy,
        )
    shape = "credential required" if access["required"] else "no credential required"
    return Row(
        key="judge_access",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=f"resolved - {shape}; no credential value in the file",
        detail={"required": access["required"]},
    )


def row_disclosure(root: Path) -> Row:
    """Requirement 7 - created inside the window, with pre-existing code disclosed."""
    requirement = "7 - created in the submission window; pre-existing code disclosed"
    title = "provenance disclosure"
    path = root / DISCLOSURE_MD
    if not path.is_file():
        return Row(
            key="disclosure",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{DISCLOSURE_MD.as_posix()} is not on disk",
            remedy=[
                "Disclose the separate research repository and the window, then re-derive:",
                f"    {DISCLOSURE_MD.as_posix()}",
                "    python scripts/submission/provenance_census.py --check",
            ],
        )
    size = path.stat().st_size

    rc, out, err = _run(["git", "log", "--format=%H%x1f%aI%x1f%cI%x1f%s"], root, timeout=60.0)
    if rc != 0:
        return Row(
            key="disclosure",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed=f"NOT CHECKED - git log refused ({err.strip() or rc})",
            remedy=["    python scripts/submission/provenance_census.py --check"],
            detail={"disclosure_bytes": size},
        )
    commits = parse_commit_log(out)
    if not commits:
        return Row(
            key="disclosure",
            title=title,
            requirement=requirement,
            status=STATUS_NOTRUN,
            observed="NOT CHECKED - git log returned no commits",
            remedy=["    python scripts/submission/provenance_census.py --check"],
            detail={"disclosure_bytes": size},
        )
    bad = window_violations(commits)
    detail = {
        "disclosure_bytes": size,
        "commits": len(commits),
        "window": f"{WINDOW_START_EDT.date()} .. {WINDOW_END_EDT.date()} (EDT)",
        "violations": bad,
    }
    if bad:
        return Row(
            key="disclosure",
            title=title,
            requirement=requirement,
            status=STATUS_FAIL,
            observed=f"{len(bad)} commit date(s) outside the window, of {len(commits)}",
            remedy=[
                "Every commit must fall inside the declared window, or the divergence must",
                "be disclosed. Re-derive the census and read the offending commits:",
                "    python scripts/submission/provenance_census.py --check",
                *[f"    {line}" for line in bad[:5]],
            ],
            detail=detail,
        )
    return Row(
        key="disclosure",
        title=title,
        requirement=requirement,
        status=STATUS_PASS,
        observed=(
            f"{DISCLOSURE_MD.as_posix()} present ({size} bytes); "
            f"{len(commits)} commits, all inside the window"
        ),
        detail=detail,
    )


def row_deadline(now: datetime) -> Row:
    """The clock. Not a requirement - the constraint every other row runs against."""
    days, hours, total = remaining_to_deadline(now)
    detail = {
        "now_utc": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "deadline_utc": DEADLINE_UTC.isoformat().replace("+00:00", "Z"),
        "deadline_local": DEADLINE_LOCAL_TEXT,
        "hours_remaining": round(total, 2),
    }
    if total <= 0:
        return Row(
            key="deadline",
            title="time remaining",
            requirement="deadline - 2026-08-18 17:00 EDT",
            status=STATUS_FAIL,
            observed=f"the deadline passed {abs(days)}d {abs(hours)}h ago",
            remedy=["The submission window is closed. Nothing this program checks can fix that."],
            detail=detail,
        )
    return Row(
        key="deadline",
        title="time remaining",
        requirement="deadline - 2026-08-18 17:00 EDT",
        status=STATUS_PASS,
        observed=f"{days}d {hours}h to {DEADLINE_LOCAL_TEXT} ({detail['deadline_utc']})",
        blocking=False,
        detail=detail,
    )


# ── assembly ─────────────────────────────────────────────────────────────────────────────


def load_submission(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read `SUBMISSION.json`. Return ``(document, error)``; never both."""
    path = root / SUBMISSION_JSON
    text = read_text(path)
    if text is None:
        return None, f"{SUBMISSION_JSON.as_posix()} is not on disk"
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"{SUBMISSION_JSON.as_posix()} is not valid JSON: {exc}"
    if not isinstance(document, dict):
        return None, f"{SUBMISSION_JSON.as_posix()} is not a JSON object"
    return document, None


#: For each row: the artefact a reader opens to check it WITHOUT trusting this program,
#: and the literal command that re-derives it. `docs/submission/RULES-MATRIX.md` prints
#: both columns straight out of `--json`, which is why its status column is generated
#: rather than typed.
EVIDENCE: dict[str, tuple[str, str]] = {
    "licence_file": (
        "`LICENSE`, `LICENSES/`, `docs/submission/LICENCE-CENSUS.md`",
        "`ls -l LICENSE && python scripts/qa/check_reuse.py`",
    ),
    "remote_sync": (
        "the remote itself - there is no local artefact for this row",
        "`git rev-list --left-right --count origin/master...HEAD`",
    ),
    "repo_public": (
        "`qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md`",
        "`gh repo view Shaugato/mainline --json visibility`",
    ),
    "demo_url": (
        "`docs/submission/SUBMISSION.json` key `demo_url`",
        "`python scripts/submission/check_submission_ready.py --check-urls`",
    ),
    "video_url": (
        "`docs/submission/VIDEO-KIT.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml`",
        "`python scripts/submission/check_submission_ready.py --check-urls`",
    ),
    "devpost_description": (
        "`docs/submission/DEVPOST.md`",
        "`python scripts/submission/check_submission_prose.py`",
    ),
    "tool_usage": (
        "`docs/TOOL-USAGE.md`, `evidence/tool-usage/`",
        "`python scripts/submission/capture_tool_evidence.py --check`",
    ),
    "judge_access": (
        "`docs/submission/SUBMISSION.json` key `judge_access`, `VERIFY.md`",
        "`python scripts/submission/check_submission_ready.py --json`",
    ),
    "disclosure": (
        "`docs/submission/DISCLOSURE.md`, `evidence/provenance/commit-window.json`",
        "`python scripts/submission/provenance_census.py --check`",
    ),
    "deadline": (
        "the official rules page",
        "`python scripts/submission/check_submission_ready.py`",
    ),
}


def collect(root: Path, *, branch: str, remote: str, check_urls: bool, now: datetime) -> list[Row]:
    """Every row, in the order a reader wants to be told about them."""
    submission, _ = load_submission(root)
    rows = [
        row_licence_file(root),
        row_remote_sync(root, branch, remote),
        row_repo_public(root, submission),
        row_demo_url(submission, check_urls),
        row_video_url(submission, check_urls),
        row_devpost(root),
        row_tool_usage(root),
        row_judge_access(submission),
        row_disclosure(root),
        row_deadline(now),
    ]
    for row in rows:
        evidence, rederive = EVIDENCE.get(row.key, ("", ""))
        row.evidence = evidence
        row.rederive = rederive
    return rows


def current_branch(root: Path, fallback: str = "master") -> str:
    """The checked-out branch, or *fallback* when HEAD is detached (as it is in CI)."""
    rc, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    name = out.strip()
    if rc != 0 or not name or name == "HEAD":
        return fallback
    return name


# ── rendering ────────────────────────────────────────────────────────────────────────────


def render_table(rows: list[Row], stream: Any) -> None:
    """Print the gate as one ASCII table, in `scripts/qa/doctor.py`'s shape."""
    width = max([len(row.title) for row in rows] + [len("CHECK")])
    header = f"{'STATUS':<6}  {'CHECK':<{width}}  OBSERVED"
    rule = f"{'-' * 6}  {'-' * width}  {'-' * 56}"
    print(header, file=stream)
    print(rule, file=stream)
    for row in rows:
        print(f"{row.status:<6}  {row.title:<{width}}  {row.observed}", file=stream)
    print(rule, file=stream)


def render_remedies(rows: list[Row], stream: Any) -> int:
    """Print the numbered remedy list. Return the count of blocking failures."""
    blocking = [row for row in rows if row.is_blocking_failure]
    advisory = [row for row in rows if not row.blocking and not row.resolved]

    if blocking:
        noun = "row" if len(blocking) == 1 else "rows"
        print(f"\nNOT READY - {len(blocking)} unresolved {noun}. In order:\n", file=stream)
        for number, row in enumerate(blocking, start=1):
            print(f"  {number}. {row.title}: {row.observed}", file=stream)
            print(f"     requirement {row.requirement}", file=stream)
            for line in row.remedy:
                print(f"     {line}", file=stream)
            print("", file=stream)
    else:
        print("\nREADY - every blocking row is resolved.", file=stream)
        print("        Re-run with --check-urls before pasting the Devpost form.\n", file=stream)

    if advisory:
        for row in advisory:
            print(f"advisory: {row.title}: {row.observed}", file=stream)
        print("", file=stream)

    print(
        "NOTRUN means NOT CHECKED. It is never a pass: a question nobody could answer is "
        "an unresolved row.",
        file=stream,
    )
    return len(blocking)


def _cell(text: str) -> str:
    """One markdown table cell: pipes escaped, newlines flattened."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render_markdown(rows: list[Row], stream: Any) -> None:
    """Emit the RULES-MATRIX status table. The document embeds this verbatim."""
    print("| Row | Requirement | Status | Observed | Evidence | Re-derive with |", file=stream)
    print("|---|---|---|---|---|---|", file=stream)
    for row in rows:
        print(
            f"| `{row.key}` | {_cell(row.requirement)} | **{row.status}** "
            f"| {_cell(row.observed)} | {_cell(row.evidence)} | {_cell(row.rederive)} |",
            file=stream,
        )


def as_report(rows: list[Row], root: Path, now: datetime) -> dict[str, Any]:
    """The `--json` document. `docs/submission/RULES-MATRIX.md` is generated from this."""
    blocking = [row for row in rows if row.is_blocking_failure]
    _, _, total_hours = remaining_to_deadline(now)
    return {
        "tool": "check_submission_ready",
        "schema_version": 1,
        "generated_at": now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "repo_root": root.as_posix(),
        "deadline_utc": DEADLINE_UTC.isoformat().replace("+00:00", "Z"),
        "deadline_local": DEADLINE_LOCAL_TEXT,
        "hours_remaining": round(total_hours, 2),
        "ready": not blocking,
        "blocking_count": len(blocking),
        "unresolved_rows": [row.key for row in blocking],
        "rows": [row.as_dict() for row in rows],
    }


# ── self-test ────────────────────────────────────────────────────────────────────────────


def _self_test() -> int:  # noqa: PLR0915 - a flat list of assertions reads better flat
    """Plant one of every family this gate must catch, and require it to fire.

    A gate that has never refused asserts nothing. Every branch below is a state the
    submission can actually be in on 18 August, written down so the branch that matters
    is exercised on a machine where it is not currently true.
    """
    import io

    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name}{(' - ' + detail) if detail else ''}")
            failures.append(name)

    print("check_submission_ready --self-test")

    # 1 - the unresolved sentinel, including nested and scoped.
    doc = {
        "demo_url": UNRESOLVED,
        "repo_url": "https://github.com/x/y",
        "judge_access": {"required": UNRESOLVED, "how": "walk in", "credentials_location": "none"},
    }
    check("sentinel found at top level", "demo_url" in find_unresolved(doc))
    check("sentinel found nested", "judge_access.required" in find_unresolved(doc))
    check(
        "scoping restricts the search",
        find_unresolved(doc, only=("judge_access",)) == ["judge_access.required"],
        str(find_unresolved(doc, only=("judge_access",))),
    )
    check("a resolved document has no sentinel", find_unresolved({"a": "b"}) == [])

    # 2 - credential families, one planted value each.
    planted = {
        "aws": "AKIAIOSFODNN7EXAMPLE",
        "gh": "ghp_" + "a" * 36,
        "pem": "-----BEGIN RSA PRIVATE KEY-----",
        "dsn": "postgresql://root:hunter2@localhost:26257/defaultdb",
        "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1g",
        "nested": {"password": "correct-horse-battery-staple"},
        "blob": "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6",
    }
    findings = scan_for_credentials(planted)
    for family in ("aws-access-key-id", "github-token", "private-key-block", "jwt"):
        check(
            f"credential family {family} fires",
            any(family in f for f in findings),
            str(findings),
        )
    check(
        "an inline password in a DSN fires",
        any("url-with-inline-password" in f for f in findings),
        str(findings),
    )
    check(
        "a key named 'password' fires",
        any("nested.password" in f for f in findings),
        str(findings),
    )
    check("an opaque blob fires", any("blob" in f for f in findings), str(findings))
    clean = json.loads(json.dumps(SELF_TEST_CLEAN_DOCUMENT))
    check(
        "the shipped shape is clean",
        scan_for_credentials(clean) == [],
        str(scan_for_credentials(clean)),
    )
    # 2b - the key-NAME rule fires on keys and not on sentences about keys. Measured
    # 2026-08-10: substring matching fired on this repository's own documentation key.
    check("an exact secret key name fires", key_names_a_secret("password") is True)
    check("a suffixed secret key name fires", key_names_a_secret("aws_secret_access_key") is True)
    check("a judge password fires", key_names_a_secret("judge_password") is True)
    check(
        "a documentation key does not fire",
        key_names_a_secret("never_write_a_credential_here") is False,
    )
    check("a pointer key does not fire", key_names_a_secret("credentials_location") is False)
    check("an ordinary key does not fire", key_names_a_secret("demo_url") is False)
    check(
        "an UNRESOLVED value under a secret key is not a leak",
        scan_for_credentials({"judge_password": UNRESOLVED}) == [],
        str(scan_for_credentials({"judge_password": UNRESOLVED})),
    )

    # 3 - rev-list parsing, the row that is red today.
    check("behind/ahead parses", parse_left_right("0\t2") == (0, 2))
    check("a synced remote parses", parse_left_right("0 0") == (0, 0))
    try:
        parse_left_right("garbage")
    except ValueError:
        check("garbage raises rather than reading as zero", True)
    else:
        check("garbage raises rather than reading as zero", False, "no exception")

    # 4 - URL classification.
    check("UNRESOLVED is not a URL", classify_url(UNRESOLVED)[0] is False)
    check("a bare word is not a URL", classify_url("mainline")[0] is False)
    check("a non-http scheme is refused", classify_url("ftp://example.com/x")[0] is False)
    check("a hostless URL is refused", classify_url("https://localhost")[0] is False)
    check("an https URL passes", classify_url("https://example.com/demo")[0] is True)
    check("a non-string is refused", classify_url(None)[0] is False)

    # 5 - visibility, from both sources, and from neither.
    check("gh PUBLIC parses", visibility_from_gh('{"visibility":"public"}') == "PUBLIC")
    check("gh PRIVATE parses", visibility_from_gh('{"visibility":"PRIVATE"}') == "PRIVATE")
    check("gh garbage is None, not a pass", visibility_from_gh("not json") is None)
    check(
        "event payload visibility parses",
        visibility_from_event({"repository": {"visibility": "public"}}) == "PUBLIC",
    )
    check(
        "event payload private flag parses",
        visibility_from_event({"repository": {"private": True}}) == "PRIVATE",
    )
    check("an empty payload is None", visibility_from_event({}) is None)

    # 6 - the clock.
    before = datetime(2026, 8, 10, 21, 0, 0, tzinfo=UTC)
    days, hours, total = remaining_to_deadline(before)
    check("eight days remain on 2026-08-10", (days, hours) == (8, 0), f"{days}d {hours}h")
    check("total hours are 192", abs(total - 192.0) < 1e-6, str(total))
    after = datetime(2026, 8, 19, 0, 0, 0, tzinfo=UTC)
    _, _, past = remaining_to_deadline(after)
    check("past the deadline is negative", past < 0, str(past))
    check(
        "a passed deadline is a FAIL row",
        row_deadline(after).status == STATUS_FAIL,
        row_deadline(after).status,
    )

    # 7 - description triviality.
    ok, reason, _ = assess_description(None)
    check("an absent description fails", ok is False and reason == "absent", reason)
    ok, _, _ = assess_description("# Title\n\nshort.\n")
    check("a stub fails on bytes", ok is False)
    body = "\n".join(f"line {n}: the database refuses the merge." for n in range(60))
    padded = "# MAINLINE\n\n" + body
    ok, reason, _ = assess_description(padded)
    check("a real description passes", ok is True, reason)
    ok, reason, _ = assess_description(padded + "\n\nTODO: write the impact section\n")
    check("a placeholder token fails", ok is False and "TODO" in reason, reason)
    ok, reason, _ = assess_description(padded + "\n\n| Video demo link | `UNRESOLVED` |\n")
    check(
        "an honest UNRESOLVED marker is not this row's business",
        ok is True,
        reason,
    )

    # 8 - tool counting.
    one_tool = "We use CockroachDB Cloud and Amazon Bedrock."
    crdb, aws = count_named_tools(one_tool)
    check("one CRDB tool is not two", len(crdb) == 1 and len(aws) == 1, f"{crdb} {aws}")
    two_tools = "CockroachDB v26.2.5 plus the CockroachDB Managed MCP Server, on Amazon S3."
    crdb, aws = count_named_tools(two_tools)
    check("two CRDB tools are counted", len(crdb) >= 2, str(crdb))
    check("an AWS service is counted", len(aws) >= 1, str(aws))
    crdb, aws = count_named_tools("CockroachDB v26.2.5 and CockroachDB Agent Skills, no cloud.")
    check("zero AWS services is zero", len(aws) == 0, str(aws))
    check("an empty document names nothing", count_named_tools(None) == ([], []))

    # 9 - the commit window, including the rebase case.
    def commit(author: str, committer: str) -> list[dict[str, str]]:
        return [{"hash": "a" * 40, "author": author, "committer": committer, "subject": "x"}]

    inside = commit("2026-08-06T10:00:00+10:00", "2026-08-06T10:00:00+10:00")
    check("an in-window commit is clean", window_violations(inside) == [])
    early = commit("2026-08-04T23:08:37+10:00", "2026-08-04T23:08:37+10:00")
    check("a pre-window commit fires", len(window_violations(early)) == 2)
    rebased = commit("2026-07-30T09:00:00+10:00", "2026-08-07T09:00:00+10:00")
    violations = window_violations(rebased)
    check(
        "a rebased commit fires on its author date alone",
        len(violations) == 1 and "author" in violations[0],
        str(violations),
    )
    unparseable = commit("not-a-date", "2026-08-07T09:00:00+10:00")
    check(
        "an unparseable date is a violation, not a pass",
        len(window_violations(unparseable)) == 1,
    )

    # 10 - log parsing.
    line = "abc\x1f2026-08-06T10:00:00+10:00\x1f2026-08-06T10:00:00+10:00\x1fa subject\n"
    parsed = parse_commit_log(line)
    check("the log parses into fields", len(parsed) == 1 and parsed[0]["hash"] == "abc")
    check("blank lines are skipped", parse_commit_log("\n\n") == [])

    # 11 - the invariant this whole file exists for: NOTRUN is never a pass.
    notrun = Row(
        key="k", title="t", requirement="r", status=STATUS_NOTRUN, observed="NOT CHECKED - x"
    )
    check("a NOTRUN row is unresolved", notrun.resolved is False)
    check("a NOTRUN row blocks", notrun.is_blocking_failure is True)
    warn = Row(key="k", title="t", requirement="r", status=STATUS_WARN, observed="x")
    check("a WARN row is unresolved", warn.resolved is False)
    passed = Row(key="k", title="t", requirement="r", status=STATUS_PASS, observed="x")
    check("only PASS resolves", passed.resolved is True and passed.is_blocking_failure is False)

    # 12 - rendering and aggregation, over a mixed table.
    rows = [passed, notrun, row_deadline(before)]
    buffer = io.StringIO()
    render_table(rows, buffer)
    rendered = buffer.getvalue()
    check("the table has doctor's header", "STATUS" in rendered and "OBSERVED" in rendered)
    buffer = io.StringIO()
    blocking = render_remedies(rows, buffer)
    check("one blocking row is counted", blocking == 1, str(blocking))
    check("the legend says NOTRUN is not a pass", "never a pass" in buffer.getvalue())
    report = as_report(rows, Path(), before)
    check("the report refuses", report["ready"] is False)
    check("the report names the unresolved row", report["unresolved_rows"] == ["k"], str(report))
    check("the report round-trips as JSON", json.loads(json.dumps(report))["blocking_count"] == 1)
    buffer = io.StringIO()
    render_markdown(rows, buffer)
    check("markdown emits a row per check", buffer.getvalue().count("\n") == len(rows) + 2)

    # 13 - the judge-access row end to end, including the quotation mark that would fool
    # a looser gate. `"false"` is truthy in most languages that will read this file.
    resolved_access = {
        "demo_url": "https://example.com",
        "judge_access": {
            "required": False,
            "how": "The demo is public and needs no sign-in.",
            "credentials_location": "none - no credential is required",
        },
    }
    check("a resolved judge_access passes", row_judge_access(resolved_access).status == STATUS_PASS)
    stringly = json.loads(json.dumps(resolved_access))
    stringly["judge_access"]["required"] = "false"
    row = row_judge_access(stringly)
    check(
        "the string 'false' is refused, not read as a boolean",
        row.status == STATUS_FAIL,
        row.observed,
    )
    missing_member = json.loads(json.dumps(resolved_access))
    del missing_member["judge_access"]["how"]
    check("a missing member is refused", row_judge_access(missing_member).status == STATUS_FAIL)
    leaky = json.loads(json.dumps(resolved_access))
    leaky["judge_access"]["credentials_location"] = "AKIAIOSFODNN7EXAMPLE"
    row = row_judge_access(leaky)
    check(
        "a credential beats a resolved field",
        row.status == STATUS_FAIL and "credential-shaped" in row.observed,
        row.observed,
    )
    check("an absent SUBMISSION.json is NOTRUN", row_judge_access(None).status == STATUS_NOTRUN)

    # 14 - a fully green table exits 0, so green is reachable and not merely absent.
    green = [
        Row(key="a", title="a", requirement="1", status=STATUS_PASS, observed="ok"),
        row_deadline(before),
    ]
    check("an all-PASS table is ready", as_report(green, Path(), before)["ready"] is True)

    print()
    if failures:
        print(f"SELF-TEST FAILED - {len(failures)} of the checks above did not hold")
        for name in failures:
            print(f"  - {name}")
        return EXIT_NOT_READY
    print("SELF-TEST PASSED")
    return EXIT_READY


#: The shape `docs/submission/SUBMISSION.json` ships with, inlined so the self-test can
#: assert that the file this repository publishes contains nothing credential-shaped
#: without needing the file on disk.
SELF_TEST_CLEAN_DOCUMENT: dict[str, Any] = {
    "schema_version": 1,
    "schema_documented_in": "docs/submission/RULES-MATRIX.md",
    "unresolved_sentinel": UNRESOLVED,
    "never_write_a_credential_here": (
        "judge_access.credentials_location is a POINTER to where a credential lives, "
        "never the credential itself."
    ),
    "demo_url": UNRESOLVED,
    "repo_url": UNRESOLVED,
    "video_url": UNRESOLVED,
    "judge_access": {
        "required": UNRESOLVED,
        "how": UNRESOLVED,
        "credentials_location": UNRESOLVED,
    },
    "deadline_utc": "2026-08-18T21:00:00Z",
    "deadline_local": DEADLINE_LOCAL_TEXT,
    "devpost_description_file": "docs/submission/DEVPOST.md",
    "tool_usage_file": "docs/TOOL-USAGE.md",
    "disclosure_file": "docs/submission/DISCLOSURE.md",
    "licence_file": "LICENSE",
}


# ── entry point ──────────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_submission_ready.py",
        description=(
            "The submission gate. Exits non-zero while any rules requirement is "
            "unresolved, and prints the exact command that resolves each one."
        ),
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="repository root (default: the repository containing this script)",
    )
    parser.add_argument(
        "--remote", default="origin", help="remote to compare HEAD against (default: origin)"
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="branch to compare against (default: the checked-out branch, else master)",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="fetch demo_url and video_url and require HTTP 200 (the only networked mode)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the report as JSON and nothing else"
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="emit the RULES-MATRIX status table and nothing else",
    )
    parser.add_argument(
        "--now",
        default=None,
        help="ISO-8601 instant to evaluate the clock at (default: now, UTC)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="plant every failure family and require a refusal"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _survive_a_narrow_console()
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    if args.now is None:
        now = datetime.now(UTC)
    else:
        try:
            now = datetime.fromisoformat(args.now)
        except ValueError:
            print(f"--now: {args.now!r} is not an ISO-8601 instant", file=sys.stderr)
            return EXIT_CANNOT_RUN
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)

    start = args.repo if args.repo is not None else REPO_ROOT_DEFAULT
    if not start.exists():
        print(f"--repo: {start} does not exist", file=sys.stderr)
        return EXIT_CANNOT_RUN
    root = repo_root_of(start)

    branch = args.branch or current_branch(root)
    rows = collect(root, branch=branch, remote=args.remote, check_urls=args.check_urls, now=now)

    if args.json:
        print(json.dumps(as_report(rows, root, now), indent=2, sort_keys=False))
    elif args.markdown:
        render_markdown(rows, sys.stdout)
    else:
        _, error = load_submission(root)
        print(f"MAINLINE submission gate - {SUBMISSION_JSON.as_posix()} is the only write point")
        print(f"repository: {root}    branch: {args.remote}/{branch}")
        if error:
            print(f"WARNING: {error}")
        print("")
        render_table(rows, sys.stdout)
        render_remedies(rows, sys.stdout)

    return EXIT_READY if all(not row.is_blocking_failure for row in rows) else EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
