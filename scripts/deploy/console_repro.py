# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Is the console build reproducible? Measure it; never assume it.

WHY THIS FILE EXISTS
--------------------
``verticals/mainline/apps/demo-api/tests/test_response_contract.py`` and
``tests/deploy/test_furl_compression.py`` both pin a **content-hashed filename** as a
constant. A content hash is a legitimate constant only if the build that produces it is
reproducible: otherwise the constant is a record of one machine's afternoon, and the next
person to re-record it is copying a number nobody can re-derive.

The tree carries two *different* content hashes for the same entry chunk at an **identical**
433,564 bytes:

* ``assets/index-BKZMI9SJ.js`` — ``docs/ci/cluster-lane-package.md`` §4, "the fresh build at
  HEAD ``eefae1c``", with a 124,173 B gzipped sibling;
* ``assets/index-DzVoV1YM.js`` — the demo-api tests, ``out/lambda/…-arm64.zip`` and the live
  Function URL, with a 124,177 B gzipped sibling.

Same length, different content. That is not explained by the ``define`` defaults in
``vite.config.ts`` (``'dev'``\\=3, ``'unknown'``\\=7, ``'absent'``\\=6,
``'g1-attestation.json'``\\=19 characters — all different lengths), and
``git diff eefae1c HEAD -- verticals/mainline/apps/console`` is **empty**, so it is not
explained by the source at those two commits either. Something of equal length varies, or a
record is mislabelled. This script settles which by building and hashing, N times, and
writing every digest down.

WHAT IT RECORDS, AND WHY EACH FIELD IS THERE
--------------------------------------------
A build is a function of its inputs. An input that reaches the emitted bytes and is not
written down is *ambient*, and an ambient input is exactly how two hashes end up in one
repository with nobody able to say which is which. So the record carries:

``command``
    the exact argv, not a prose description of it.
``environment``
    every variable the build reads, by name, with the value it resolved to — including the
    ones that were **unset**, because "unset" is a value that reaches the bytes.
``source``
    the digest of every source file that entered the build, plus the digest of the same
    paths **as committed**. When those two disagree the build is not this repository's
    build, and the record says so instead of implying otherwise by silence.
``builds[]``
    per run, every emitted asset by name, byte size and sha256.
``compiled``
    the literals read back **out of the emitted bytes** — the mode the artefact will run in
    is a property of the artefact, not of the command somebody meant to type.

USAGE
-----
::

    .venv/Scripts/python.exe scripts/deploy/console_repro.py --builds 3
    .venv/Scripts/python.exe scripts/deploy/console_repro.py --builds 3 --api-base /
    .venv/Scripts/python.exe scripts/deploy/console_repro.py --builds 3 --source rev:HEAD

``--source rev:<rev>`` exports that revision's console subtree with ``git archive`` into a
scratch directory and builds **there**, so a working tree another worker is editing is never
touched and never contributes bytes. ``node_modules`` is reused from the real console
through a junction/symlink: it is installed from the frozen lockfile and is not source.

**Environment variables are set in this process, not on a shell line.** On Windows,
``VITE_MAINLINE_API_BASE=/ pnpm exec vite build`` typed into Git Bash is rewritten by MSYS
path conversion and the artefact is compiled with ``C:/Program Files/Git/`` — measured, and
recorded in ``docs/deploy/console-build.md`` §1. ``subprocess`` with an explicit ``env``
mapping has no shell in it to do that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
CONSOLE: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console"
CONSOLE_REL: Final = "verticals/mainline/apps/console"
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "deploy" / "console-repro.json"

#: The build command this repository performs. `--mode demo` is what makes Vite read
#: `.env.demo`; everything else about the artefact's identity is an input, not a flag.
BUILD_ARGV: Final = ("pnpm", "exec", "vite", "build", "--mode", "demo")

#: EVERY variable that reaches the emitted bytes, by name.
#:
#: The four `VITE_*` names are read by Vite itself (from `.env.demo` first, then from the
#: process environment, which Vite applies last and which is therefore how a deploy supplies
#: one without editing a committed file). The two `MAINLINE_*` names are read by
#: `vite.config.ts` directly and become `define` substitutions.
#:
#: This tuple is the *declaration*. `tests/deploy/test_console_repro.py` checks it against
#: what `vite.config.ts` and `.env.demo` actually read, so a seventh input added to either
#: one and not added here fails a test rather than becoming ambient.
BUILD_INPUT_NAMES: Final = (
    "VITE_MAINLINE_API_BASE",
    "VITE_MAINLINE_BUNDLE_URL",
    "VITE_MAINLINE_LOG_VKEY",
    "VITE_MAINLINE_CANON_SHA256",
    "MAINLINE_BUILD_ID",
    "MAINLINE_ATTESTATION",
)

#: Filesystem inputs `vite.config.ts` probes for. A file that is *absent* is as much an
#: input as one that is present — `readSignaturePath()` compiles `unknown`/`absent` when
#: neither exists, and that pair reaches the bytes.
ATTESTATION_CANDIDATES: Final = (
    "evidence/attestations/g1-attestation.json",
    "evidence/g1-attestation.json",
)

#: Directories skipped when digesting the console's SOURCE. `node_modules` is derived from
#: the frozen lockfile (which is itself a source file and IS included); `dist` is the output.
#:
#: This set is deliberately NOT applied to the output tree. `dist/.vite/manifest.json` is an
#: emitted file — `scripts/check-budgets.ts` reads it, and the budget gate is a test (D13) —
#: so it is hashed like every other asset. A record that quietly omitted an emitted file
#: would be a reproducibility claim with a hole in it exactly where the gate looks.
SOURCE_EXCLUDE_DIRS: Final = frozenset({"node_modules", "dist", "__pycache__"})


# ── digests ────────────────────────────────────────────────────────────────────────────


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digests(
    root: Path, *, exclude_dirs: frozenset[str] = frozenset()
) -> dict[str, dict[str, Any]]:
    """Every file under ``root``, by POSIX-relative name, with size and sha256.

    ``exclude_dirs`` is empty by default: when this walks an OUTPUT tree, everything the
    build emitted is part of what "reproducible" means.
    """
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(part in exclude_dirs for part in rel.parts[:-1]):
            continue
        out[rel.as_posix()] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return out


def rollup_digest(entries: Mapping[str, Mapping[str, Any]]) -> str:
    """One digest over a whole tree: sha256 of ``name\\0size\\0sha256\\n`` per entry, sorted.

    A single value is what makes "these two builds are the same" a comparison a reader can
    do by eye, and what makes it quotable in a report without quoting fifty lines.
    """
    payload = "".join(
        f"{name}\0{meta['bytes']}\0{meta['sha256']}\n" for name, meta in sorted(entries.items())
    )
    return sha256_bytes(payload.encode("utf-8"))


# ── git ────────────────────────────────────────────────────────────────────────────────


def git(*args: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def committed_source_digests(rev: str) -> dict[str, dict[str, Any]]:
    """The console's source **as committed at ``rev``**, digested the same way as a tree.

    This is the other half of the line-ending question. ``git ls-files --eol`` reports what
    git *believes*; this reads the blob bytes, which is what a build would actually see from
    a clean export.
    """
    listing = git("ls-tree", "-r", "-z", "--format=%(objectname) %(path)", rev, CONSOLE_REL)
    out: dict[str, dict[str, Any]] = {}
    for raw_record in listing.split("\0"):
        record = raw_record.strip()
        if not record:
            continue
        oid, _, path = record.partition(" ")
        rel = path[len(CONSOLE_REL) + 1 :] if path.startswith(CONSOLE_REL + "/") else path
        if any(part in SOURCE_EXCLUDE_DIRS for part in Path(rel).parts[:-1]):
            continue
        blob = subprocess.run(
            ["git", "cat-file", "blob", oid],
            cwd=str(REPO_ROOT),
            capture_output=True,
            check=True,
        ).stdout
        out[rel] = {"bytes": len(blob), "sha256": sha256_bytes(blob)}
    return out


def eol_census(rev_worktree: bool = True) -> dict[str, Any]:
    """How many tracked console files sit in the worktree with CRLF, and which.

    CSS-module class names are a hash of the module's **bytes**, so one file checked out
    CRLF changes every scoped class name in the bundle — and a hash is a fixed-length
    string, so the bundle changes content **without changing length**. That is the only
    mechanism this worker found that produces two different digests at an identical
    433,564 B, and it is why this census is part of the record rather than a footnote.
    """
    del rev_worktree
    listing = git("ls-files", "--eol", CONSOLE_REL)
    counts: dict[str, int] = {}
    crlf_in_worktree: list[str] = []
    for line in listing.splitlines():
        if not line.strip():
            continue
        fields = line.split("\t")
        eols = fields[0].split()
        path = fields[-1].strip()
        key = " ".join(eols[:2])
        counts[key] = counts.get(key, 0) + 1
        if len(eols) > 1 and eols[1] in {"w/crlf", "w/mixed"}:
            crlf_in_worktree.append(path)
    return {
        "counts": dict(sorted(counts.items())),
        "worktree_crlf_paths": sorted(crlf_in_worktree),
        "how_to_reproduce": f"git ls-files --eol {CONSOLE_REL}",
        "newline_only_drift": newline_only_drift(),
    }


def newline_only_drift(rev: str = "HEAD") -> dict[str, Any]:
    """Tracked console files whose worktree bytes differ from ``rev`` **only** in newlines.

    THIS IS THE AMBIENT INPUT THAT PRODUCED TWO HASHES AT ONE LENGTH, and it is invisible
    to ``git status``. Git for Windows ships ``core.autocrlf=true`` at system scope; a file
    checked out under it holds CRLF in the worktree and LF in the index, and the index's
    **cached stat size** is the CRLF size — so ``git status`` never re-reads the file and
    reports the tree clean. Measured on this tree, ``instrument.module.css``:

        index blob  4eee3112…  4,429 B, 0 CRLF
        worktree               4,563 B, 134 CRLF
        git status             (clean)

    A *real* edit is not drift and is not reported here: it changes bytes other than
    newlines, git sees it, and a worker meant it. The distinction is the whole point — a
    check that refused every uncommitted change would be red for the wrong reason on every
    machine and would teach its reader to ignore it.
    """
    listing = git("ls-files", "-z", CONSOLE_REL)
    drifted: list[dict[str, Any]] = []
    edited: list[str] = []
    for raw_path in listing.split("\0"):
        path = raw_path.strip()
        if not path:
            continue
        rel = Path(path).relative_to(CONSOLE_REL).as_posix()
        if any(part in SOURCE_EXCLUDE_DIRS for part in Path(rel).parts[:-1]):
            continue
        disk = REPO_ROOT / path
        if not disk.is_file():
            continue
        blob = subprocess.run(
            ["git", "show", f"{rev}:{path}"], cwd=str(REPO_ROOT), capture_output=True, check=False
        )
        if blob.returncode != 0:
            continue
        committed = blob.stdout
        current = disk.read_bytes()
        if current == committed:
            continue
        if current.replace(b"\r\n", b"\n") == committed:
            drifted.append(
                {
                    "path": path,
                    "reaches_vite_build": rel.startswith("src/"),
                    "committed_bytes": len(committed),
                    "worktree_bytes": len(current),
                    "crlf_lines": current.count(b"\r\n"),
                }
            )
        else:
            edited.append(path)
    return {
        "rev": rev,
        "newline_only": drifted,
        "newline_only_count": len(drifted),
        "reaching_vite_build": sorted(d["path"] for d in drifted if d["reaches_vite_build"]),
        "genuinely_edited": sorted(edited),
        "why_git_status_is_silent": (
            "the index caches the CRLF worktree size, so git declares the entry unmodified "
            "without re-reading it"
        ),
    }


# ── the build ──────────────────────────────────────────────────────────────────────────


def tool_version(argv: Sequence[str]) -> str:
    """The version of a tool whose output is part of the artefact's identity.

    ``shell=True`` on Windows because ``pnpm`` is a ``.cmd`` shim and ``CreateProcess``
    cannot start one. Recorded rather than assumed: rollup and esbuild ship
    platform-specific native binaries, so "which node, which pnpm" is a build input.
    """
    try:
        proc = subprocess.run(
            list(argv), capture_output=True, text=True, check=False, shell=(os.name == "nt")
        )
    except OSError as exc:  # pragma: no cover - depends on PATH
        return f"<not runnable: {exc}>"
    output = (proc.stdout or proc.stderr).strip()
    return output.splitlines()[0] if output else ""


def build_env(overrides: Mapping[str, str]) -> dict[str, str]:
    """The environment the build runs in, with every declared input made explicit.

    An input is either *supplied* (present in ``overrides``) or *removed* (deleted from the
    inherited environment). It is never inherited by accident: a variable left over in the
    caller's shell is precisely the ambient input this whole script exists to refuse.
    """
    env = dict(os.environ)
    for name in BUILD_INPUT_NAMES:
        env.pop(name, None)
    env.update(overrides)
    # A Vite build with `CI` set skips nothing that changes bytes, but it does change
    # reporter output; pin it so the recorded command is the whole command.
    env.setdefault("CI", "true")
    return env


def resolve_inputs(overrides: Mapping[str, str], root: Path) -> dict[str, Any]:
    """What each declared input resolved to, and from where."""
    dotenv = parse_dotenv(root / ".env.demo")
    resolved: dict[str, Any] = {}
    for name in BUILD_INPUT_NAMES:
        if name in overrides:
            resolved[name] = {
                "value": overrides[name],
                "from": "environment (supplied by this run)",
            }
        elif name in dotenv:
            resolved[name] = {"value": dotenv[name], "from": ".env.demo (committed)"}
        else:
            resolved[name] = {"value": None, "from": "unset"}
    probes = []
    for candidate in ATTESTATION_CANDIDATES:
        path = REPO_ROOT / candidate
        probes.append({"path": candidate, "exists": path.is_file()})
    resolved["__attestation_probe__"] = {
        "candidates": probes,
        "read_by": "verticals/mainline/apps/console/vite.config.ts readSignaturePath()",
        "compiles_to_when_all_absent": {
            "signature_path": "unknown",
            "attestation_source": "absent",
        },
    }
    return resolved


def parse_dotenv(path: Path) -> dict[str, str]:
    """`.env.demo`, as Vite reads it: ``NAME=VALUE``, ``#`` comments, no interpolation used."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, sep, value = stripped.partition("=")
        if not sep:
            continue
        values[name.strip()] = value.strip()
    return values


def run_build(root: Path, overrides: Mapping[str, str]) -> dict[str, Any]:
    """One clean build: remove ``dist`` first, then run the command, then hash everything."""
    dist = root / "dist"
    if dist.exists():
        shutil.rmtree(dist)
    env = build_env(overrides)
    started = time.monotonic()
    proc = subprocess.run(  # noqa: PLW1510 - returncode is inspected below, so check=False
        list(BUILD_ARGV),
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        shell=(os.name == "nt"),
    )
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(BUILD_ARGV)} exited {proc.returncode} in {root}\n"
            f"--- stdout ---\n{proc.stdout[-4000:]}\n--- stderr ---\n{proc.stderr[-4000:]}"
        )
    assets = tree_digests(dist)
    return {
        "seconds": round(elapsed, 2),
        "entries": len(assets),
        "bytes": sum(meta["bytes"] for meta in assets.values()),
        "tree_digest": rollup_digest(assets),
        "assets": assets,
    }


# ── reading the artefact back ──────────────────────────────────────────────────────────

_VITE_LITERAL: Final = re.compile(r"(VITE_MAINLINE_[A-Z0-9_]+):\"((?:[^\"\\]|\\.)*)\"")
_MODE_LITERAL: Final = re.compile(r"\bMODE:\"((?:[^\"\\]|\\.)*)\"")
_HONESTY_INITIAL: Final = re.compile(
    r"buildId:\"((?:[^\"\\]|\\.)*)\",signaturePath:\"((?:[^\"\\]|\\.)*)\""
)


def read_compiled(dist: Path) -> dict[str, Any]:
    """The artefact's own account of itself, read out of the emitted JavaScript.

    ``source-select.ts`` trims each value and treats ``""`` as **unset**, so this reports
    both the raw literal and the selector's verdict. Two places holding one fact is one
    place for them to disagree; this reads the place that ships.
    """
    entries = sorted((dist / "assets").glob("index-*.js"))
    if not entries:
        return {"error": "no dist/assets/index-*.js emitted"}
    entry = entries[0]
    text = entry.read_text("utf-8", errors="replace")
    literals: dict[str, str] = {}
    for name, value in _VITE_LITERAL.findall(text):
        literals.setdefault(name, value)
    mode = _MODE_LITERAL.search(text)
    honesty = _HONESTY_INITIAL.search(text)

    def trimmed(name: str) -> str | None:
        raw = literals.get(name)
        if raw is None:
            return None
        return raw.strip() or None

    api = trimmed("VITE_MAINLINE_API_BASE")
    bundle = trimmed("VITE_MAINLINE_BUNDLE_URL")
    if api and bundle:
        selected = "LIVE (with a control that switches to REPLAY)"
    elif api:
        selected = "LIVE (single source, no control)"
    elif bundle:
        selected = "REPLAY (single source, no control)"
    else:
        selected = "NO SOURCE"
    return {
        "entry": entry.name,
        "entry_bytes": entry.stat().st_size,
        "entry_sha256": sha256_file(entry),
        "vite_literals": dict(sorted(literals.items())),
        "mode": mode.group(1) if mode else None,
        "build_id": honesty.group(1) if honesty else None,
        "signature_path": honesty.group(2) if honesty else None,
        # TWO `buildId` LITERALS ARE IN EVERY ARTEFACT and only one is this build's answer:
        # `App.tsx` compiles the folded `__MAINLINE_BUILD_ID__` ternary, and `honesty.ts`
        # carries `buildId: 'unknown'` as the EMPTY record's constant, which is in every
        # build ever made and says nothing about this one. `build_id` above is read from the
        # `initial:{buildId,signaturePath}` pair, which is App.tsx's. Both are listed so a
        # reader running the grep from docs/deploy/console-build.md §7.1 is not left guessing.
        "build_id_literals_present": sorted(set(re.findall(r"buildId:\"([^\"]*)\"", text))),
        "mentions_g1_attestation_json": "g1-attestation.json" in text,
        "source_select_verdict": selected,
        "read_from": "the emitted bytes, not the command line",
    }


# ── building from a clean export ───────────────────────────────────────────────────────


def export_rev(rev: str, into: Path) -> Path:
    """``git archive`` the console subtree at ``rev`` into ``into`` and link ``node_modules``.

    The export carries **index bytes**, so line endings are whatever the repository stores
    rather than whatever this checkout happens to hold. That is the tree the two disputed
    records both claim to describe, and building it is how the dispute is settled.
    """
    into.mkdir(parents=True, exist_ok=True)
    archive = into.parent / f"{rev.replace('/', '_')}.tar"
    with archive.open("wb") as handle:
        subprocess.run(
            ["git", "archive", "--format=tar", rev, CONSOLE_REL],
            cwd=str(REPO_ROOT),
            stdout=handle,
            check=True,
        )
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if m.name.startswith(CONSOLE_REL + "/")]
        for member in members:
            member.name = member.name[len(CONSOLE_REL) + 1 :]
        tar.extractall(into, members=members, filter="data")
    archive.unlink()

    link = into / "node_modules"
    if not link.exists():
        real = CONSOLE / "node_modules"
        if not real.is_dir():
            raise RuntimeError(
                f"{real} is absent; run `pnpm install --frozen-lockfile` in {CONSOLE} first"
            )
        try:
            # `Path.symlink_to` rather than `os.symlink`, per PTH211. The argument order is
            # the reverse of os.symlink's — the LINK is the receiver and the TARGET is the
            # argument — which is the whole reason the rule is worth obeying rather than
            # silencing: the os form reads as "link real to link" at a glance and is easy to
            # get backwards, and a symlink pointing the wrong way here would make the build
            # read its own output directory.
            Path(link).symlink_to(real, target_is_directory=True)
        except OSError:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(real)],
                check=True,
                capture_output=True,
            )
    return into


# ── report ─────────────────────────────────────────────────────────────────────────────


def compare(builds: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    digests = [b["tree_digest"] for b in builds]
    identical = len(set(digests)) == 1
    differing: list[str] = []
    if not identical:
        names = set()
        for build in builds:
            names |= set(build["assets"])
        for name in sorted(names):
            seen = {json.dumps(b["assets"].get(name), sort_keys=True) for b in builds}
            if len(seen) > 1:
                differing.append(name)
    return {
        "runs": len(builds),
        "tree_digests": digests,
        "byte_identical": identical,
        "assets_that_differ": differing,
    }


def build_report(
    *,
    builds: int,
    overrides: Mapping[str, str],
    source: str,
    root: Path,
    rev: str | None,
) -> dict[str, Any]:
    results = [run_build(root, overrides) for _ in range(builds)]
    verdict = compare(results)
    worktree_source = tree_digests(root, exclude_dirs=SOURCE_EXCLUDE_DIRS)
    head = git("rev-parse", "HEAD").strip()
    committed = committed_source_digests(rev or "HEAD")
    only_in_tree = sorted(set(worktree_source) - set(committed))
    only_committed = sorted(set(committed) - set(worktree_source))
    changed = sorted(
        name
        for name in set(worktree_source) & set(committed)
        if worktree_source[name]["sha256"] != committed[name]["sha256"]
    )
    return {
        "what": "Is the console build reproducible, and what does the artefact carry?",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repository": {
            "head": head,
            "console": CONSOLE_REL,
            "source_of_build": source,
            "exported_rev": rev,
        },
        "command": {
            "argv": list(BUILD_ARGV),
            "cwd": str(root),
            "environment_overrides": dict(sorted(overrides.items())),
            "note": (
                "Environment is set by subprocess, not by a shell prefix. On Windows, "
                "`VITE_MAINLINE_API_BASE=/ pnpm exec vite build` typed into Git Bash is "
                "rewritten by MSYS path conversion to `C:/Program Files/Git/` and the "
                "artefact carries that; there is no shell here to do it."
            ),
        },
        "toolchain": {
            "node": tool_version(["node", "--version"]),
            "pnpm": tool_version(["pnpm", "--version"]),
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
        "build_inputs": resolve_inputs(overrides, root),
        "build_input_names_declared": list(BUILD_INPUT_NAMES),
        "source": {
            "worktree_digest": rollup_digest(worktree_source),
            "committed_digest": rollup_digest(committed),
            "worktree_matches_committed": (not only_in_tree and not only_committed and not changed),
            "files_only_in_worktree": only_in_tree,
            "files_only_committed": only_committed,
            "files_whose_bytes_differ": changed,
            "eol": eol_census(),
        },
        "reproducibility": verdict,
        "builds": results,
        "compiled": read_compiled(root / "dist"),
    }


# ── the command line ───────────────────────────────────────────────────────────────────
#
# WHY THIS SECTION EXISTS AT ALL, AND WHY THERE IS NO `# noqa: PLR0912` ON `main()`.
#
# `main()` was written as one function and measured at 18 branches / 74 statements, which
# `PLR0912`/`PLR0915` refused against a `scripts/` baseline of 0 and 1. A `noqa` would have
# been defensible ONLY if those branches were an interface — the irreducible shape of a
# command line, where each flag is one arm and collapsing them would hide the surface. They
# were not. Reading them, the function was doing FIVE separable jobs, and only the first was
# about the command line:
#
#   1. DECLARE the flags                     -> build_parser()
#   2. RESOLVE flags into build inputs,      -> resolve_overrides()
#      including the MSYS refusal
#   3. RESOLVE where to build                -> resolve_source()
#      (worktree, or a clean export)
#   4. WRITE the record (merge or replace)   -> write_record()
#      and its licence sidecar
#   5. PRINT the human summary               -> print_summary()
#
# Only 3 has genuinely alternative arms; the rest were sequential work that happened to
# contain `if`s. Each extracted function is independently readable and independently
# testable, which the single function was not, and `main()` is now the control flow it
# always claimed to be. The count fell because the complexity fell — which is the only
# reason a count is allowed to fall.


def build_parser() -> argparse.ArgumentParser:
    """The flags this script accepts. Declaration only: nothing here inspects a value."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--builds", type=int, default=3, help="how many clean builds (>=3)")
    parser.add_argument(
        "--api-base",
        default=None,
        help="value for VITE_MAINLINE_API_BASE; `/` is the Phase-2 value (same origin)",
    )
    parser.add_argument("--build-id", default=None, help="value for MAINLINE_BUILD_ID")
    parser.add_argument(
        "--source",
        default="worktree",
        help="`worktree` or `rev:<rev>` to build a clean `git archive` export",
    )
    parser.add_argument("--out", type=Path, default=None, help="where to write the JSON record")
    parser.add_argument(
        "--label",
        default=None,
        help=(
            "name this run and MERGE it into --out under `runs[<label>]` instead of "
            "replacing the file"
        ),
    )
    parser.add_argument("--print", action="store_true", help="also print the record to stdout")
    return parser


def resolve_overrides(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, str]:
    """The declared build inputs THIS run supplies, or a refusal if one is not a value.

    Separate from `build_parser()` because a flag's declared type is not its meaning:
    `--api-base` is a string to argparse and a URL base to the artefact, and the gap between
    those two is where the MSYS conversion below hides.
    """
    overrides: dict[str, str] = {}
    if args.api_base is not None:
        # MEASURED, ON THIS MACHINE, BY THIS WORKER. `--api-base /` typed at a Git Bash
        # command line arrives here as `C:/Program Files/Git/`: MSYS rewrites a bare `/`
        # argument into the MSYS root before Python is started, so the guard cannot live in
        # the subprocess environment — by then the damage is an argv this process believes.
        # `docs/deploy/console-build.md` §1 recorded the same conversion happening to an
        # env-var *prefix*; it happens to a plain argument too, and the artefact compiles
        # `VITE_MAINLINE_API_BASE:"C:/Program Files/Git/"` and names a path on somebody's
        # laptop from a page served on the internet. Refuse it here, loudly.
        if re.match(r"^[A-Za-z]:[\\/]", args.api_base) or "\\" in args.api_base:
            parser.error(
                f"--api-base {args.api_base!r} looks like an MSYS-converted path, not a URL base. "
                "A bare `/` is rewritten to the MSYS root by Git Bash before this process "
                "starts. Re-run from PowerShell, or prefix the line with MSYS_NO_PATHCONV=1. "
                "The value that belongs in the artefact is `/` — one origin, no hostname."
            )
        overrides["VITE_MAINLINE_API_BASE"] = args.api_base
    if args.build_id is not None:
        overrides["MAINLINE_BUILD_ID"] = args.build_id
    return overrides


def resolve_source(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[Path, str | None, tempfile.TemporaryDirectory[str] | None]:
    """Which tree gets built: this worktree, or a clean `git archive` export of one revision.

    Returns ``(root, rev, scratch)``. The scratch directory is HANDED BACK rather than
    cleaned up here: the export has to outlive this call by exactly as long as the build
    takes to read it, so its lifetime belongs to `main()`'s `finally` — where a failed build
    still removes it.
    """
    if args.source == "worktree":
        return CONSOLE, None, None
    if not args.source.startswith("rev:"):
        parser.error("--source must be `worktree` or `rev:<rev>`")
    rev = git("rev-parse", args.source[4:]).strip()
    scratch = tempfile.TemporaryDirectory(prefix="mainline-console-repro-")
    return export_rev(rev, Path(scratch.name) / "console"), rev, scratch


def discard_export(scratch: tempfile.TemporaryDirectory[str] | None) -> None:
    """Remove the scratch export, detaching `node_modules` BEFORE the tree walk.

    `TemporaryDirectory.cleanup()` recurses, and on Windows a directory junction is recursed
    *into*: cleaning up naively would delete the real console's lockfile-installed
    `node_modules`. `unlink` handles the symlink case; `rmdir` is the junction case, which
    `unlink` raises `OSError` on.
    """
    if scratch is None:
        return
    link = Path(scratch.name) / "console" / "node_modules"
    if link.exists():
        try:
            link.unlink()
        except OSError:
            subprocess.run(["cmd", "/c", "rmdir", str(link)], check=False, capture_output=True)
    scratch.cleanup()


def write_record(out: Path, report: Mapping[str, Any], label: str | None) -> None:
    """Write the record: MERGED under ``runs[<label>]`` when labelled, replacing it when not.

    A labelled run is merged so the Phase-1 and Phase-2 measurements sit in one file and can
    be compared without opening two. A corrupt file on disk is replaced rather than raised
    on: the measurement in hand is worth more than the one that failed to parse.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    if not label:
        out.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    else:
        document: dict[str, Any] = {}
        if out.is_file():
            try:
                document = json.loads(out.read_text("utf-8"))
            except json.JSONDecodeError:
                document = {}
        document.setdefault(
            "what",
            "Console build reproducibility, measured. Each entry of `runs` is one invocation "
            "of scripts/deploy/console_repro.py; nothing here is copied from another document.",
        )
        document.setdefault("produced_by", "scripts/deploy/console_repro.py")
        document.setdefault("checked_by", "tests/deploy/test_console_repro.py")
        runs = document.setdefault("runs", {})
        runs[label] = report
        document["last_written"] = report["measured_at"]
        out.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    licence = out.with_suffix(out.suffix + ".license")
    if not licence.exists():
        licence.write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: CC-BY-4.0\n",
            encoding="utf-8",
        )


def print_summary(out: Path, report: Mapping[str, Any]) -> None:
    """The few lines a reader needs before deciding whether to open the JSON."""
    verdict = report["reproducibility"]
    compiled = report["compiled"]
    print(f"wrote {out}")
    print(f"  builds            {verdict['runs']}")
    print(f"  byte identical    {verdict['byte_identical']}")
    if not verdict["byte_identical"]:
        print(f"  assets differing  {verdict['assets_that_differ'][:8]}")
    print(f"  entry             {compiled.get('entry')}  {compiled.get('entry_bytes')} B")
    print(f"  source verdict    {compiled.get('source_select_verdict')}")
    print(f"  worktree==commit  {report['source']['worktree_matches_committed']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.builds < 3:
        parser.error(
            "--builds must be at least 3: two agreeing runs is a coincidence, three is a "
            "measurement"
        )

    overrides = resolve_overrides(args, parser)
    root, rev, scratch = resolve_source(args, parser)
    try:
        report = build_report(
            builds=args.builds, overrides=overrides, source=args.source, root=root, rev=rev
        )
    finally:
        discard_export(scratch)

    out = args.out or DEFAULT_OUT
    write_record(out, report, args.label)
    print_summary(out, report)
    if args.print:
        json.dump(report, sys.stdout, indent=2)
        print()
    return 0 if report["reproducibility"]["byte_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
