#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Regenerate the reference evidence bundle, or assert that regenerating it changes nothing.

CU-6: ``just evidence-regen`` is byte-deterministic and CI asserts zero diff, mirroring
``trappoint render``. This script is that assertion.

Two failures are distinguished, because they mean opposite things:

``MANIFEST DRIFT``
    the committed files do not hash to what the committed ``MANIFEST.sha256`` says. Somebody
    edited an artefact by hand. The manifest is the tripwire and it just fired.

``REGENERATION DIFF``
    the committed files are internally consistent, but running ``generate.py`` again
    produces something else. Either the generator changed and the artefacts were not
    refreshed, or the generator is not deterministic — and a generator whose output varies
    run to run has no *"ordinarily"* to appeal to under Evidence Act 1995 (Cth) ss.146-147.

Usage:

.. code-block:: console

   $ python scripts/custody/regen_reference_ledger.py            # regenerate in place
   $ python scripts/custody/regen_reference_ledger.py --check    # assert zero diff (CI)
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
BUNDLE_DIR: Final = REPO_ROOT / "evidence" / "reference-ledger"
GENERATOR: Final = BUNDLE_DIR / "generate.py"
MANIFEST: Final = BUNDLE_DIR / "MANIFEST.sha256"

#: The artefacts a regeneration must reproduce byte for byte. `generate.py`, the READMEs and
#: the keys are INPUTS to generation, so they are covered by the manifest check but are not
#: compared against a regenerated copy — comparing a file to itself proves nothing.
GENERATED: Final = ("bundle.json", "MANIFEST.sha256")


def _lf(path: Path) -> bytes:
    """Bytes with CRLF folded to LF.

    Every hash in this repository that crosses a machine boundary is taken over
    LF-normalised bytes — ``canon_src_sha256`` states the rule normatively. Without it a
    Windows checkout with ``core.autocrlf=true`` reports a diff against a Linux runner and
    the alarm is about line endings rather than about evidence.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(_lf(path)).hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, relative = line.partition("  ")
        entries[relative.strip()] = digest.strip()
    return entries


def check_manifest() -> list[str]:
    """Return the committed files whose content disagrees with the committed manifest."""
    if not MANIFEST.is_file():
        return ["MANIFEST.sha256 does not exist"]
    problems: list[str] = []
    for relative, expected in read_manifest(MANIFEST).items():
        target = BUNDLE_DIR / relative
        if not target.is_file():
            problems.append(f"{relative}: named by the manifest and missing from disk")
            continue
        actual = _digest(target)
        if actual != expected:
            problems.append(f"{relative}: is {actual}, manifest pins {expected}")
    return problems


def regenerate(destination: Path) -> None:
    """Run ``generate.py --out destination`` in a subprocess.

    A subprocess rather than an import: the generator is the artefact under test, and a
    check that imports it shares its module state, its ``sys.path`` edits and any global it
    has already mutated. The thing CI is asserting is that *running it* is reproducible.
    """
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--out", str(destination)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(
            f"generate.py exited {result.returncode}. The reference bundle could not be "
            "regenerated at all, which is a harder failure than a diff."
        )
    sys.stdout.write(result.stdout)


def _json_shape_diff(committed: Path, produced: Path) -> list[str]:
    """A readable summary of where two bundles differ, for a one-line JSON file.

    ``bundle.json`` is stored as its own RFC 8785 canonical bytes, so a byte diff of it is
    one enormous line and tells a reader nothing. This walks the two parsed objects and
    names the first few paths that disagree, which is what somebody staring at a red CI job
    actually needs.
    """
    try:
        left = json.loads(committed.read_text(encoding="utf-8"))
        right = json.loads(produced.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"could not parse one of the bundles for a structural diff: {exc}"]

    differences: list[str] = []

    def walk(a: object, b: object, path: str) -> None:
        if len(differences) >= 12:
            return
        if type(a) is not type(b):
            differences.append(f"{path}: {type(a).__name__} became {type(b).__name__}")
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a:
                    differences.append(f"{path}.{key}: added")
                elif key not in b:
                    differences.append(f"{path}.{key}: removed")
                else:
                    walk(a[key], b[key], f"{path}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                differences.append(f"{path}: {len(a)} items became {len(b)}")
            for index, (x, y) in enumerate(zip(a, b, strict=False)):
                walk(x, y, f"{path}[{index}]")
        elif a != b:
            differences.append(f"{path}: {a!r} != {b!r}")

    walk(left, right, "$")
    return differences


def check(verbose: bool) -> int:
    problems = check_manifest()
    if problems:
        print("MANIFEST DRIFT — a committed artefact was edited by hand:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            "\nThe manifest is the tripwire and it has fired. Re-run "
            "`python scripts/custody/regen_reference_ledger.py` and commit the result; if "
            "the change was deliberate, the diff is what needs reviewing.",
            file=sys.stderr,
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="mainline-refledger-") as scratch:
        produced = Path(scratch)
        regenerate(produced)

        drifted: list[str] = []
        for relative in GENERATED:
            committed_path = BUNDLE_DIR / relative
            produced_path = produced / relative
            if not committed_path.is_file():
                drifted.append(f"{relative}: not committed")
                continue
            if _lf(committed_path) != _lf(produced_path):
                drifted.append(relative)

        if not drifted:
            print(
                f"reference bundle regeneration is a no-op: "
                f"{', '.join(GENERATED)} are byte-identical"
            )
            return 0

        print(
            "REGENERATION DIFF — running generate.py does not reproduce what is committed:",
            file=sys.stderr,
        )
        for relative in drifted:
            print(f"  {relative}", file=sys.stderr)
            if relative == "bundle.json" and (produced / relative).is_file():
                for line in _json_shape_diff(BUNDLE_DIR / relative, produced / relative):
                    print(f"      {line}", file=sys.stderr)
            elif verbose and (produced / relative).is_file():
                diff = difflib.unified_diff(
                    _lf(BUNDLE_DIR / relative).decode("utf-8", "replace").splitlines(),
                    _lf(produced / relative).decode("utf-8", "replace").splitlines(),
                    fromfile=f"committed/{relative}",
                    tofile=f"regenerated/{relative}",
                    lineterm="",
                )
                for line in list(diff)[:40]:
                    print(f"      {line}", file=sys.stderr)
        print(
            "\nCU-6: the reference bundle is byte-deterministic and CI asserts zero diff, "
            "mirroring `trappoint render`. Re-run "
            "`python scripts/custody/regen_reference_ledger.py` and commit the result.",
            file=sys.stderr,
        )
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; assert that regeneration produces no diff (the CI mode)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print a unified diff for text artefacts"
    )
    args = parser.parse_args(argv)

    if not GENERATOR.is_file():
        print(f"{GENERATOR} does not exist", file=sys.stderr)
        return 2
    if importlib.util.find_spec("cryptography") is None:
        # Not a skip. The reference bundle is the domain's Tier-1 artefact and a lane that
        # cannot regenerate it has not checked it; saying so is the whole point of loud SKIP.
        print(
            "SKIP(no-cryptography): `cryptography` is not importable, so the reference "
            "bundle cannot be regenerated and ZERO DIFF WAS NOT VERIFIED by this run.",
            file=sys.stderr,
        )
        return 0 if not args.check else 3

    if args.check:
        return check(args.verbose)

    regenerate(BUNDLE_DIR)
    # Regenerating in place leaves the temp-copy machinery unused, so the manifest is
    # re-read from disk to prove the write actually landed.
    problems = check_manifest()
    if problems:
        print("the freshly written bundle does not match its own manifest:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"regenerated {BUNDLE_DIR.relative_to(REPO_ROOT).as_posix()} and its manifest")
    return 0


if __name__ == "__main__":
    if shutil.which("git") is None:  # pragma: no cover — informational only
        pass
    raise SystemExit(main())
