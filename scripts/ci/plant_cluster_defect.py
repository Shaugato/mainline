#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none - this file makes no database claim.
# I: CI-CLUSTER-2 - the cluster lane is FALSIFIABLE. A defect only a database can see
#    makes the cluster lane red and leaves the hermetic lane green, and this program is
#    what puts that defect in front of both of them.
"""Plant a defect that ONLY a cluster-backed test can see, then take it out again.

WHY A PROGRAM AND NOT THREE LINES OF `sed` IN A WORKFLOW.

`.github/workflows/cluster-lane-bites.yml` asserts a 2x2: a defect present or absent,
crossed with `--crdb=none` or `--crdb=reuse`. The cell that carries the whole argument is
*plant PRESENT, `--crdb=none`, GREEN* - the defect is invisible to every lane this
repository had before the cluster lane existed. A 2x2 whose plant silently failed to
apply reports exactly the same four results as a 2x2 whose plant worked, except for the
one cell that then goes green when it should be red. So the edit has to REFUSE rather
than no-op, and refusing needs somewhere to put the reason.

The second reason is that this repository has already been damaged once by an edit to the
file this program edits, and a program that writes into
`verticals/mainline/db/seeds/demo/demo_world.sql` is the single most dangerous script that
could exist here. Every safety property below is therefore structural:

  * **The edit is reversible byte-for-byte, and the reversal is verified.** `--plant`
    snapshots the exact bytes it is about to overwrite and records their SHA-256;
    `--revert` restores those bytes and re-hashes the restored file, refusing if the
    result is not identical to what was there before.
  * **`git checkout --` IS NOT USED, deliberately.** It would restore the file from the
    INDEX, which discards any uncommitted work another worker has in that file - and on
    the tree this was written against, `demo_world.sql` had 144 uncommitted added lines
    from a different lead. A revert that destroys somebody's work to prove a point about
    falsifiability is not a revert. Restoring the snapshot is equivalent to
    `git checkout --` on the clean checkout CI uses, and strictly safer everywhere else.
  * **The plant is never committed.** `--status` reports whether one is present, the
    workflow asserts a clean tree after reverting, and the snapshot directory is removed
    by `--revert` so that even an untracked leftover is visible to `git status`.

WHY *THIS* PLANT, AND WHY NOT THE OBVIOUS ONE.

The specimen is the reverted `demo_world.sql` credential swap. `demo_world.sql:124` enrols
`digest('mainline-demo/credential/demo.signer', 'sha256')`; a worker once replaced that
expression with the constant `sha256(b"credsigner")` that `gate_run` derived, so that a
red test would go green - making the SEED match the CODE. Three negative controls caught
it. One of them,
`test_credentials.py::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive`,
says so in as many words, and it is marked `requires_cluster`: it can only speak when a
database is there to be asked. That is precisely the property the 2x2 needs.

**The `transitions.py` reversion is the WRONG plant and must not be added to the
catalogue.** The ratchet `test_no_module_derives_a_credential_id` is an AST walk; it
catches that edit STATICALLY, under `--crdb=none`, so the top-right cell of the 2x2 would
be red and the proof would collapse into "we planted something both lanes can see."

The constant is DERIVED here (`sha256(b"credsigner")`) rather than written out. A second
copy of a 32-byte literal is the defect class this whole area of the repository keeps
closing, and the plant's job is to reproduce a historical DERIVATION - if the expression
that derivation used were ever changed, this plant should follow it rather than pin a hex
string nobody can check.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import pathlib
import shutil
import sys
from dataclasses import dataclass
from typing import Final

#: Where `--plant` puts the bytes it is about to overwrite. Untracked, and removed by
#: `--revert`, so a leftover is a `git status` line rather than a silent condition.
SNAPSHOT_DIR: Final = pathlib.Path(".plant-cluster-defect")
MANIFEST: Final = "manifest.json"
SCHEMA: Final = "mainline.ci.planted-defect/1"


class Refusal(Exception):
    """A condition under which this program refuses to edit, or to claim it reverted."""


@dataclass(frozen=True)
class Plant:
    """One reversible edit, and the sentence that says what it proves."""

    slug: str
    path: str
    #: The line to replace, compared after `str.strip()` so indentation and line endings
    #: are the file's business rather than this catalogue's.
    anchor: str
    #: What to put there instead, indented and terminated exactly as the anchor was.
    replacement: str
    #: Why this edit is invisible to a hermetic lane and fatal to a cluster-backed one.
    invisible_because: str
    #: The test that is expected to catch it, named so a reader can check the claim.
    caught_by: str


def _derived_signer_credential_hex() -> str:
    """`sha256(b"credsigner")` - what `gate_run` used to bind as `signer_credential_id`.

    Derived rather than restated. `test_credentials.py:94` derives the same value from the
    same expression for the same reason: it is a historical constant, and a hex literal
    copied into a second file is a hex literal nobody can check.
    """
    return hashlib.sha256(b"credsigner").hexdigest()


def catalogue() -> dict[str, Plant]:
    """The plants this program knows how to apply. Exactly one, on purpose."""
    return {
        "seed-credential-swap": Plant(
            slug="seed-credential-swap",
            path="verticals/mainline/db/seeds/demo/demo_world.sql",
            anchor="digest('mainline-demo/credential/demo.signer', 'sha256'),",
            replacement=f"decode('{_derived_signer_credential_hex()}', 'hex'),",
            invisible_because=(
                "no test that runs without a database ever reads this file's effect. The "
                "seed still applies cleanly, the API still resolves a credential for "
                "demo.signer, and every hermetic assertion in the demo-api suite passes "
                "unchanged - because they are assertions about code, and this is a fact "
                "about a database."
            ),
            caught_by=(
                "verticals/mainline/apps/demo-api/tests/test_credentials.py"
                "::test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive"
            ),
        ),
    }


# -- the tree ---------------------------------------------------------------------------


def _repo_root(explicit: pathlib.Path | None) -> pathlib.Path:
    root = (explicit or pathlib.Path.cwd()).resolve()
    if not (root / ".git").exists():
        raise Refusal(
            f"{root} is not the root of a git working tree. This program edits a deployed "
            "seed file and proves afterwards that it put the bytes back; without a "
            "working tree there is nothing to prove that against."
        )
    return root


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(root: pathlib.Path) -> pathlib.Path:
    return root / SNAPSHOT_DIR / MANIFEST


def read_manifest(root: pathlib.Path) -> dict[str, object] | None:
    path = _manifest_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refusal(
            f"{path} is present but unreadable ({exc}). A plant is recorded as applied and "
            "this program can no longer say what it replaced, so it will not guess: "
            "restore the file from git yourself and delete that directory."
        ) from exc
    if data.get("schema") != SCHEMA:
        raise Refusal(f"{path} declares schema {data.get('schema')!r}, expected {SCHEMA!r}")
    return data


# -- planting ---------------------------------------------------------------------------


def _substitute(text: str, plant: Plant) -> tuple[str, int, str, str]:
    """Return (new text, 1-based line number, the old line, the new line).

    The match is on the STRIPPED line and exactly one line may match. A plant that matched
    nothing would leave both `--crdb` cells measuring an unplanted tree and the 2x2 would
    report a proof it never made; a plant that matched twice would edit a line nobody
    chose. Both are refusals rather than best-effort edits.
    """
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if line.strip() == plant.anchor]
    if not hits:
        if plant.replacement in text:
            raise Refusal(
                f"{plant.path} already contains this plant's replacement text. Either a "
                "plant is present and was not recorded, or the file has been edited to "
                "look like one. Neither may be planted over."
            )
        raise Refusal(
            f"{plant.path} contains no line equal to {plant.anchor!r}, so plant "
            f"{plant.slug!r} would be a NO-OP. A 2x2 run against an unplanted tree reports "
            "the same four results as a working one except for the cell that then passes "
            "when it should fail, which is the exact shape of a proof that proves nothing. "
            "If the seed legitimately changed, update this plant in the same commit and "
            "say what it now edits."
        )
    if len(hits) > 1:
        found = ", ".join(str(i + 1) for i in hits)
        raise Refusal(
            f"{plant.path} contains {len(hits)} lines equal to {plant.anchor!r} (lines "
            f"{found}). This plant edits ONE enrolment and will not choose between them."
        )

    index = hits[0]
    old = lines[index]
    stripped = old.rstrip("\r\n")
    ending = old[len(stripped) :]
    indent = stripped[: len(stripped) - len(stripped.lstrip())]
    new = f"{indent}{plant.replacement}{ending}"
    lines[index] = new
    return "".join(lines), index + 1, old, new


def plant_defect(root: pathlib.Path, slug: str, out: list[str]) -> None:
    """Apply one plant, after snapshotting the exact bytes it overwrites."""
    plants = catalogue()
    if slug not in plants:
        raise Refusal(f"no plant named {slug!r}; known: {', '.join(sorted(plants))}")
    if read_manifest(root) is not None:
        raise Refusal(
            f"a plant is already applied (see {SNAPSHOT_DIR}/{MANIFEST}). Planting over a "
            "plant would make the snapshot describe a file that no longer exists, and the "
            "revert would silently restore the wrong bytes. Run --revert first."
        )

    plant = plants[slug]
    target = root / plant.path
    if not target.is_file():
        raise Refusal(f"{plant.path} does not exist under {root}")

    before_bytes = target.read_bytes()
    before_sha = hashlib.sha256(before_bytes).hexdigest()
    text = before_bytes.decode("utf-8")
    after_text, lineno, old_line, new_line = _substitute(text, plant)
    after_bytes = after_text.encode("utf-8")

    snapshot_dir = root / SNAPSHOT_DIR
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = snapshot_dir / f"{slug}.orig"
    snapshot.write_bytes(before_bytes)

    # The snapshot is written and verified BEFORE the target is touched: a plant whose
    # backup failed is a plant with no way home, and this file is the one file in this
    # repository where that is unacceptable.
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != before_sha:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise Refusal(
            "the snapshot did not read back as the bytes it was given, so the plant was "
            "NOT applied. Nothing was edited."
        )

    target.write_bytes(after_bytes)
    _manifest_path(root).write_text(
        json.dumps(
            {
                "schema": SCHEMA,
                "slug": slug,
                "path": plant.path,
                "line": lineno,
                "before_sha256": before_sha,
                "after_sha256": hashlib.sha256(after_bytes).hexdigest(),
                "snapshot": f"{SNAPSHOT_DIR.as_posix()}/{slug}.orig",
                "caught_by": plant.caught_by,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    out.append(f"planted {slug!r} in {plant.path}:{lineno}")
    out.append("")
    out.extend(
        line.rstrip("\n")
        for line in difflib.unified_diff(
            [old_line],
            [new_line],
            fromfile=f"a/{plant.path}",
            tofile=f"b/{plant.path}",
            lineterm="\n",
            n=0,
        )
    )
    out.append("")
    out.append(f"invisible to a hermetic lane because: {plant.invisible_because}")
    out.append(f"expected to be caught by: {plant.caught_by}")
    out.append(f"revert with: python {pathlib.Path(__file__).name} --revert")


def revert_defect(root: pathlib.Path, out: list[str]) -> None:
    """Put the snapshot back, prove it went back, and remove the snapshot."""
    manifest = read_manifest(root)
    if manifest is None:
        raise Refusal(
            f"no plant is recorded under {SNAPSHOT_DIR}/{MANIFEST}, so there is nothing to "
            "revert. This is a refusal rather than a silent success: a job that reverts "
            "nothing and says it reverted is how a planted defect reaches a merge."
        )

    target = root / str(manifest["path"])
    snapshot = root / str(manifest["snapshot"])
    if not snapshot.is_file():
        raise Refusal(
            f"the snapshot {manifest['snapshot']} is gone while the manifest still records "
            f"a plant in {manifest['path']}. This program will not reconstruct the file "
            "from a catalogue entry - restore it from git and inspect the diff by hand."
        )

    # The file must still be the planted file. If it is not, something edited it while the
    # plant was applied, and writing the snapshot over it would destroy that edit -
    # exactly the harm `git checkout --` was rejected for. Refuse, and say what is there.
    current = _sha256(target)
    if current != manifest["after_sha256"]:
        raise Refusal(
            f"{manifest['path']} hashes {current}, but the plant left it at "
            f"{manifest['after_sha256']}. Something edited the file while the plant was "
            f"applied. Restoring the snapshot would discard that edit, so nothing has been "
            f"written. The bytes taken before the plant are in {manifest['snapshot']}; "
            "diff them by hand and decide deliberately."
        )

    target.write_bytes(snapshot.read_bytes())
    restored = _sha256(target)
    if restored != manifest["before_sha256"]:
        raise Refusal(
            f"{manifest['path']} was restored from the snapshot and hashes {restored}, but "
            f"the bytes taken before the plant hashed {manifest['before_sha256']}. The tree "
            "is NOT back to where it started and no caller may be told that it is."
        )

    shutil.rmtree(root / SNAPSHOT_DIR, ignore_errors=True)
    if (root / SNAPSHOT_DIR).exists():
        raise Refusal(
            f"{SNAPSHOT_DIR} could not be removed. The file is restored, but an untracked "
            "directory naming a planted defect must not survive the job that planted it."
        )
    out.append(
        f"reverted {manifest['slug']!r}: {manifest['path']} restored byte-for-byte "
        f"(sha256 {restored[:12]}...) and {SNAPSHOT_DIR}/ removed"
    )


def status(root: pathlib.Path, out: list[str]) -> int:
    """Say whether a plant is present. Exit 1 when one is, so a caller can gate on it."""
    manifest = read_manifest(root)
    if manifest is None:
        out.append("no plant is present")
        return 0
    out.append(
        f"PLANT PRESENT: {manifest['slug']!r} in {manifest['path']}:{manifest['line']} "
        f"(snapshot {manifest['snapshot']})"
    )
    return 1


def list_plants(out: list[str]) -> None:
    for plant in catalogue().values():
        out.append(f"{plant.slug}")
        out.append(f"  file        {plant.path}")
        out.append(f"  replaces    {plant.anchor}")
        out.append(f"  with        {plant.replacement}")
        out.append(f"  caught by   {plant.caught_by}")
        out.append(f"  invisible   {plant.invisible_because}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plant, and take out again, a defect only a cluster-backed test can see. Used "
            "by .github/workflows/cluster-lane-bites.yml to assert that the cluster lane "
            "can fail."
        ),
        epilog=(
            "The plant is NEVER committed. --revert restores the exact bytes --plant "
            "snapshotted, verifies the restored file's SHA-256 against the one recorded "
            "before the edit, and removes the snapshot directory."
        ),
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="print the catalogue")
    action.add_argument("--plant", metavar="SLUG", help="apply a plant by slug")
    action.add_argument("--revert", action="store_true", help="restore the snapshot")
    action.add_argument(
        "--status",
        action="store_true",
        help="exit 0 when no plant is present, 1 when one is",
    )
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=None,
        help="the working tree to operate on (default: the current directory)",
    )
    args = parser.parse_args(argv)

    out: list[str] = []
    try:
        if args.list:
            list_plants(out)
            code = 0
        else:
            root = _repo_root(args.repo_root)
            if args.status:
                code = status(root, out)
            elif args.plant:
                plant_defect(root, args.plant, out)
                code = 0
            else:
                revert_defect(root, out)
                code = 0
    except Refusal as exc:
        print("\n".join(out))
        print(f"::error title=the planted-defect harness refused::{exc}")
        return 2

    print("\n".join(out))
    return code


if __name__ == "__main__":
    sys.exit(main())
