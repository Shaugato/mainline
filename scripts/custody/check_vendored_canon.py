#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Vendoring is a CI equality, not a promise (custody plan §1.4a).

``trappoint-verify`` claims a dependency floor of ``cryptography`` and nothing else. It
therefore cannot import ``trappoint-jcs``; it carries a **byte-identical copy** of
``canon_v1.py`` instead. That claim dies quietly the moment the copy drifts from the
original, and the failure is invisible: the verifier keeps passing on old bundles and
starts failing on new ones, or worse, keeps passing on both because the drift is in a
branch neither exercises.

Three assertions, in this order:

1. **Retention.** Every canonicaliser listed in ``spec/custody/canon-registry.yaml`` still
   has a source file. Deleting one makes every leaf written under it permanently
   unverifiable — *removing a canonicaliser is a breaking change to evidence.*
2. **Integrity.** Every entry's recorded ``sha256`` still matches its source, over
   LF-normalised bytes.
3. **Vendoring.** Every ``vendored_into`` copy is byte-identical to its source, again over
   LF-normalised bytes.

Exit codes
----------
``0``  every applicable assertion held (possibly with SKIPs, printed loudly).
``1``  an assertion failed, or ``--strict`` was given and something was skipped.

A SKIP is printed in the same column and the same voice as a FAIL, because a check that
quietly reports success when it did not look is the single worst artefact this repository
could contain.

Usage
-----
::

    python scripts/custody/check_vendored_canon.py
    python scripts/custody/check_vendored_canon.py --strict     # SKIP becomes failure
    python scripts/custody/check_vendored_canon.py --repo-root .

Zero third-party dependencies, deliberately: this runs in CI lanes that install nothing,
including the lane that proves the verifier's dependency floor. PyYAML is used only as a
**cross-check** when it happens to be importable.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

REGISTRY_RELATIVE = Path("spec/custody/canon-registry.yaml")

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


def sha256_lf(path: Path) -> str:
    """SHA-256 over the file's bytes with CRLF normalised to LF.

    Stated normatively in ``spec/custody/canon-registry.yaml`` and in
    ``spec/wire/checkpoint.md`` §5. Without it the pin fingerprints the checkout rather
    than the code, and a Windows contributor breaks the build by cloning.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# --------------------------------------------------------------------------------------
# A deliberately small registry reader
# --------------------------------------------------------------------------------------


def _scalar(value: str) -> str | int | None:
    """Coerce the four scalar shapes this registry is specified to use, and no others.

    Extracted from :func:`read_registry` so that the walk over the file and the decision
    about what a scalar *means* are two readable things rather than one long one. The
    block-scalar markers (``>-``, ``|``, ``>``) collapse to the empty string because every
    field this gate reads is a scalar; a folded prose field is one it ignores.
    """
    if value in ("", ">-", "|", ">"):
        return ""
    if value == "null":
        return None
    if value.isdigit():
        return int(value)
    return value.strip("'\"")


def read_registry(path: Path) -> list[dict[str, Any]]:
    """Return the ``canonicalisers`` entries, reading only the fields this gate needs.

    This is not a YAML parser and does not pretend to be one. It reads the exact shape
    ``spec/custody/canon-registry.yaml`` is specified to have — a top-level
    ``canonicalisers:`` sequence whose items carry scalar fields and one nested
    ``vendored_into:`` sequence — and it ignores prose fields entirely. Anything outside
    that shape raises, rather than being silently skipped, so a malformed registry fails
    the build instead of emptying it.
    """
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_canonicalisers = False
    in_vendored = False
    wanted = {"payload_ver", "name", "source", "sha256", "status", "withdrawn"}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 0:
            in_canonicalisers = stripped == "canonicalisers:"
            in_vendored = False
            continue
        if not in_canonicalisers:
            continue

        if stripped.startswith("- ") and indent == 2:
            current = {"vendored_into": []}
            entries.append(current)
            in_vendored = False
            stripped = stripped[2:]
            indent = 4

        if current is None:
            continue

        if in_vendored and stripped.startswith("- "):
            current["vendored_into"].append(stripped[2:].strip())
            continue

        if stripped.startswith("- "):
            # A list item under a key this gate does not read.
            continue

        key, separator, value = stripped.partition(":")
        if not separator:
            # A continuation line of a folded (`>-`) scalar.
            continue
        key = key.strip()
        value = value.strip()
        in_vendored = key == "vendored_into" and value == ""
        if key in wanted:
            current[key] = _scalar(value)

    if not entries:
        raise ValueError(
            f"{path} lists no canonicalisers; a registry that empties itself is a defect"
        )
    return entries


def cross_check_with_pyyaml(path: Path, entries: list[dict[str, Any]]) -> str | None:
    """When PyYAML happens to be importable, prove the small reader agrees with it."""
    try:
        # Optional, and deliberately absent from the dependency-floor CI lane. No stubs are
        # installed for it either, so this import is untyped on purpose.
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return None
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    reference = parsed["canonicalisers"]
    if len(reference) != len(entries):
        return (
            "registry reader disagrees with PyYAML on entry count: "
            f"{len(entries)} vs {len(reference)}"
        )
    for small, full in zip(entries, reference, strict=True):
        for key in ("payload_ver", "name", "source", "sha256"):
            if small.get(key) != full.get(key):
                return f"registry reader disagrees with PyYAML on {full.get('name')}.{key}"
        if small["vendored_into"] != list(full.get("vendored_into") or []):
            return f"registry reader disagrees with PyYAML on {full.get('name')}.vendored_into"
    return None


# --------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.failed = 0
        self.skipped = 0

    def record(self, verdict: str, message: str) -> None:
        self.lines.append((verdict, message))
        if verdict == FAIL:
            self.failed += 1
        elif verdict == SKIP:
            self.skipped += 1

    def emit(self) -> None:
        for verdict, message in self.lines:
            print(f"{verdict:<4}  {message}")


def selftest() -> int:
    """Prove the three assertions actually bite, on a throwaway tree.

    A guard nobody has watched fail is a guard nobody knows is wired up (PL-2). This
    builds a miniature repository in a temporary directory, breaks it three ways, and
    asserts a non-zero exit each time — then repairs it and asserts a zero exit.
    """
    import tempfile

    source_text = "# SPDX-License-Identifier: Apache-2.0\nMARKER = 1\n"
    digest = hashlib.sha256(source_text.encode()).hexdigest()

    def build(root: Path, *, pin: str, source: str | None, copy: str | None) -> None:
        (root / "spec" / "custody").mkdir(parents=True, exist_ok=True)
        (root / "pkg").mkdir(parents=True, exist_ok=True)
        (root / "vendor").mkdir(parents=True, exist_ok=True)
        (root / REGISTRY_RELATIVE).write_text(
            "schema_version: 1\n"
            "canonicalisers:\n"
            "  - payload_ver: 1\n"
            "    name: canon_v1\n"
            "    source: pkg/canon_v1.py\n"
            f"    sha256: {pin}\n"
            "    vendored_into:\n"
            "      - vendor/canon_v1.py\n",
            encoding="utf-8",
            newline="\n",
        )
        if source is not None:
            (root / "pkg" / "canon_v1.py").write_text(source, encoding="utf-8", newline="\n")
        if copy is not None:
            (root / "vendor" / "canon_v1.py").write_text(copy, encoding="utf-8", newline="\n")

    cases: list[tuple[str, dict[str, str | None], int]] = [
        ("intact tree", {"pin": digest, "source": source_text, "copy": source_text}, 0),
        ("canonicaliser deleted", {"pin": digest, "source": None, "copy": source_text}, 1),
        (
            "canonicaliser modified",
            {"pin": digest, "source": source_text + "X = 2\n", "copy": source_text},
            1,
        ),
        (
            "vendored copy drifted",
            {"pin": digest, "source": source_text, "copy": source_text + "X = 2\n"},
            1,
        ),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as raw_root:
        for label, keyword_arguments, expected in cases:
            root = Path(raw_root) / label.replace(" ", "_")
            build(root, **keyword_arguments)  # type: ignore[arg-type]
            import io
            from contextlib import redirect_stdout

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                actual = main(["--repo-root", str(root), "--strict"])
            verdict = PASS if actual == expected else FAIL
            if verdict == FAIL:
                failures += 1
            print(f"{verdict:<4}  selftest · {label}: expected exit {expected}, got {actual}")
    print(f"\nselftest: {len(cases) - failures} passed, {failures} failed")
    return 1 if failures else 0


def check_entry(root: Path, entry: dict[str, Any], report: Report) -> None:
    """Run the three assertions against one registry entry, recording each verdict.

    Extracted from :func:`main` so that the three assertions the module docstring names
    are one function a reader can hold, and ``main`` is argument parsing plus a loop.
    Records rather than returns, because a single entry can produce several verdicts (one
    per vendored copy) and the report is the artefact.
    """
    name = entry.get("name", "<unnamed>")
    source_relative = entry.get("source")
    if not source_relative:
        report.record(FAIL, f"{name}: registry entry has no `source`")
        return
    source = root / source_relative

    # 1 — retention
    if not source.is_file():
        report.record(
            FAIL,
            f"{name}: source {source_relative} is missing — "
            "removing a canonicaliser is a breaking change to evidence",
        )
        return

    # 2 — integrity
    actual = sha256_lf(source)
    pinned = entry.get("sha256")
    if pinned != actual:
        report.record(
            FAIL,
            f"{name}: {source_relative} hashes to {actual} but the registry pins "
            f"{pinned} — modifying a shipped canonicaliser is a breaking change to "
            "evidence; ship canon_v"
            f"{int(entry.get('payload_ver', 0)) + 1} instead",
        )
        return
    report.record(PASS, f"{name}: {source_relative} matches its pin ({actual[:16]}…)")

    # 3 — vendoring
    vendored = entry.get("vendored_into") or []
    if not vendored:
        report.record(SKIP, f"{name}: registry declares no vendored copy")
        return
    for copy_relative in vendored:
        copy_path = root / copy_relative
        if not copy_path.is_file():
            report.record(
                SKIP,
                f"{name}: vendored copy {copy_relative} does not exist yet "
                "(trappoint-verify has not landed) — NOT CHECKED",
            )
            continue
        copy_digest = sha256_lf(copy_path)
        if copy_digest != actual:
            report.record(
                FAIL,
                f"{name}: vendored copy {copy_relative} has drifted "
                f"({copy_digest[:16]}… != {actual[:16]}…) — the verifier's "
                "one-dependency claim is false while this differs",
            )
        else:
            report.record(PASS, f"{name}: vendored copy {copy_relative} is byte-identical")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="repository root (defaults to the one containing this script)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat any SKIP as a failure; the K2 exit gate uses this",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the three assertions bite, on a throwaway tree, then exit",
    )
    arguments = parser.parse_args(argv)

    if arguments.selftest:
        return selftest()

    root: Path = arguments.repo_root.resolve()
    registry_path = root / REGISTRY_RELATIVE
    report = Report()

    if not registry_path.is_file():
        print(f"{FAIL}  registry not found at {registry_path}")
        print("\ncanonicaliser registry: 1 failed")
        return 1

    entries = read_registry(registry_path)

    disagreement = cross_check_with_pyyaml(registry_path, entries)
    if disagreement is None:
        report.record(PASS, "registry reader agrees with PyYAML (or PyYAML is absent)")
    else:
        report.record(FAIL, disagreement)

    for entry in entries:
        check_entry(root, entry, report)

    report.emit()

    strict_failure = arguments.strict and report.skipped
    total = len(report.lines)
    summary = (
        f"\ncanonicaliser registry: {total - report.failed - report.skipped} passed, "
        f"{report.failed} failed, {report.skipped} skipped"
    )
    print(summary)
    if report.skipped:
        print(
            "NOT CHECKED: the run above skipped "
            f"{report.skipped} assertion(s). A skipped check proves nothing; it is printed "
            "here as loudly as a failure so that it cannot be mistaken for one that passed."
        )
    if report.failed or strict_failure:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
