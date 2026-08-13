# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Controls for ``scripts/ci/plant_cluster_defect.py`` — the most dangerous script here.

WHAT THIS PROGRAM IS AND WHY IT NEEDED CONTROLS BEFORE ANYTHING ELSE DID.

``plant_cluster_defect.py`` writes into
``verticals/mainline/db/seeds/demo/demo_world.sql`` — the deployed demo seed, and the exact
file this repository has already been damaged through once. A worker replaced the
credential enrolment on line 124 with the constant ``gate_run`` derived, so that the SEED
matched the CODE and a red test went green. Three negative controls caught it. The plant
this program applies is a deliberate re-enactment of that damage, used to prove the cluster
lane can fail; a bug in the *reversal* would leave the real defect behind under the name of
a test.

So the properties below are not about coverage. They are the difference between a harness
that borrows the seed for ninety seconds and a harness that corrupts it:

  * ``--plant`` then ``--revert`` restores the file **byte for byte**, verified by SHA-256
    over the whole file rather than by re-running the substitution backwards.
  * ``--revert`` **proves** the restore before claiming it, and refuses if the bytes do not
    match what was taken. A revert that says it reverted and did not is how a planted
    defect reaches a merge.
  * ``--revert`` refuses when the file **moved under the plant**, rather than overwriting
    somebody else's edit. ``git checkout --`` was rejected for exactly this reason and the
    program says so; this file proves the replacement kept the property.
  * Every no-op is a **refusal**. A plant that matched nothing would leave both ``--crdb``
    cells of the 2x2 measuring an unplanted tree, and the 2x2 would report four results
    identical to a working run except for the one cell that then goes green when it should
    go red — a proof that proves nothing, which is worse than no proof.

NOTHING IN THIS FILE TOUCHES THE REAL WORKING TREE. Every scenario builds a throwaway
working tree under ``tmp_path`` — a ``.git`` directory and a copy of the seed — and drives
``main(["--repo-root", str(that)])``. The two controls that do read the real tree
(:func:`test_the_catalogue_anchor_appears_exactly_once_in_the_committed_seed` and
:func:`test_the_test_named_as_caught_by_exists_and_can_only_speak_with_a_cluster`) read it
and nothing else, because they are assertions ABOUT the shipped tree that no temporary copy
could make.

THE TWO CONTROLS THAT ARE NOT ABOUT THIS PROGRAM AT ALL.

A catalogue entry is a claim about two files it does not own. ``anchor`` claims a line
exists in the committed seed exactly once; ``caught_by`` claims a cluster-only test will
notice the edit. Both are silently falsifiable by an unrelated commit — someone reformats
the seed, someone renames the test — and when either goes stale the 2x2 keeps producing
four green-looking cells while proving nothing. The workflow cannot check them; it only
runs the program. These two controls check them here, in the suite, where a stale claim
becomes a red rather than a quiet loss of meaning.

WHAT A CONTROL HAS TO DO HERE TO COUNT, same standard as
``tests/ci/test_cluster_lane_report.py``: the load-bearing refusals are demonstrated by
MUTATION. The real program gives the safe answer and a version of itself with one named
property removed gives the unsafe one. ``mutate`` refuses an anchor that does not appear
exactly once, so a refactor produces a red asking to be re-anchored rather than a green
testing a mutation that never applied.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from types import ModuleType
from typing import Any, Final

import pytest

#: ``tests/ci/<this file>`` -> the repository root. Asserted below rather than assumed.
REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]

PROGRAM_PATH: Final = REPO_ROOT / "scripts/ci/plant_cluster_defect.py"
REAL_SEED: Final = REPO_ROOT / "verticals/mainline/db/seeds/demo/demo_world.sql"
SEED_RELPATH: Final = "verticals/mainline/db/seeds/demo/demo_world.sql"

SLUG: Final = "seed-credential-swap"
SNAPSHOT_DIR: Final = ".plant-cluster-defect"


def _source() -> str:
    assert PROGRAM_PATH.is_file(), (
        f"{PROGRAM_PATH} does not exist. This file is the control set for that program; if "
        "the program moved, these controls move with it in the same commit. A control set "
        "that cannot find its subject must fail, never skip."
    )
    return PROGRAM_PATH.read_text(encoding="utf-8")


def _load(source: str, name: str) -> ModuleType:
    """Execute ``source`` as a fresh module, under a name nothing else can import.

    The program declares ``from __future__ import annotations`` and defines ``Plant`` as a
    ``@dataclass``. Under PEP 563 every annotation is a string, and ``dataclasses`` resolves
    them through ``sys.modules[cls.__module__]`` to tell a real field from a ``ClassVar``.
    A module absent from ``sys.modules`` therefore makes the class statement itself raise,
    so the registration below is not convenience — without it this file cannot load its
    subject at all.

    It is removed again the moment the module body finishes, in a ``finally``: the entry is
    needed only while the ``@dataclass`` line runs, and leaving a mutated copy of a program
    that edits a deployed seed reachable by ``import`` is not a thing to do for tidiness.
    """
    module = ModuleType(name)
    module.__file__ = str(PROGRAM_PATH)
    sys.modules[name] = module
    try:
        exec(compile(source, str(PROGRAM_PATH), "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(name, None)
    return module


def real() -> ModuleType:
    """The program exactly as it is committed."""
    return _load(_source(), "plant_cluster_defect_real")


def mutate(anchor: str, replacement: str, name: str) -> ModuleType:
    """The program with one named property removed. The anchor must appear EXACTLY ONCE."""
    source = _source()
    found = source.count(anchor)
    assert found == 1, (
        f"the mutation anchor for {name!r} appears {found} time(s) in "
        f"{PROGRAM_PATH.name}, expected exactly 1.\n"
        "\n"
        "THIS IS NOT A FAILURE OF THE PROGRAM. It means plant_cluster_defect.py was "
        "reshaped and this control's demonstration no longer applies to it. Re-anchor the "
        "mutation against the new text IN THE SAME COMMIT. Do not delete the demonstration: "
        "an assertion with no demonstration behind it cannot tell you whether the property "
        "it names is still enforced.\n"
        "\n"
        f"anchor sought:\n{anchor}"
    )
    return _load(source.replace(anchor, replacement), name)


# ── the throwaway working tree every scenario runs against ─────────────────────────────


def _anchor_count(raw: bytes) -> int:
    anchor = real().catalogue()[SLUG].anchor
    return sum(1 for line in raw.decode("utf-8").splitlines() if line.strip() == anchor)


def unplanted_seed() -> bytes:
    """The seed's bytes WITHOUT a plant applied, whatever the working tree happens to hold.

    MEASURED, 2026-08-14: while these controls were being written, a parallel job had
    ``--plant seed-credential-swap`` applied to the real ``demo_world.sql``. Every scenario
    that copies the seed and then plants into the copy went red at once — twelve of them —
    because a planted seed no longer contains the anchor. Twelve identical failures about a
    condition that is transient, in another worker's job, and has nothing to do with the
    property under test.

    THE FIXTURE WAS THE THING THAT WAS WRONG, not the program and not the assertions. A
    control set whose scenarios are built from mutable working-tree state is a control set
    whose colour depends on what somebody else is doing at the time. CI runs against a clean
    checkout where this never arises; the fixture has to be as stable as that checkout.

    So the pre-plant bytes are taken from the plant's own snapshot when one exists — that
    file IS the seed as it was before the plant, verified by SHA-256 by the program that
    wrote it — and from the working tree otherwise. This hides nothing:
    :func:`test_the_catalogue_anchor_appears_exactly_once_in_the_committed_seed` reads the
    working-tree file directly and is the one control that goes red while a plant is live.
    One red that names the cause, instead of twelve that do not.
    """
    raw = REAL_SEED.read_bytes()
    if _anchor_count(raw) == 1:
        return raw
    snapshot = REPO_ROOT / SNAPSHOT_DIR / f"{SLUG}.orig"
    if snapshot.is_file():
        taken = snapshot.read_bytes()
        if _anchor_count(taken) == 1:
            return taken
    raise AssertionError(
        f"neither {SEED_RELPATH} nor {SNAPSHOT_DIR}/{SLUG}.orig contains the plant's anchor "
        "exactly once, so these scenarios have no unplanted seed to build from. If a plant "
        "is applied, revert it: `python scripts/ci/plant_cluster_defect.py --revert`. If the "
        "seed legitimately changed, the CATALOGUE is the derived side and moves to match it "
        "- never the other way about."
    )


def _tree(tmp_path: pathlib.Path, seed_text: str | bytes | None = None) -> pathlib.Path:
    """A stand-in working tree: a ``.git`` marker and one seed file.

    The seed defaults to a COPY OF THE REAL ONE, taken through :func:`unplanted_seed`. A
    synthetic two-line stand-in would test the substitution against a file whose shape
    nobody has to maintain; copying the shipped seed means these controls exercise the same
    100-plus-line document, the same encoding and the same single occurrence of the anchor
    that CI will hand the program.
    """
    root = tmp_path / "tree"
    (root / "verticals/mainline/db/seeds/demo").mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(exist_ok=True)
    target = root / SEED_RELPATH
    # write_bytes, never write_text: on Windows `write_text` translates "\n" to "\r\n", so a
    # scenario built from a str would land on disk as bytes the scenario never described and
    # every digest comparison below would be against the wrong document.
    if seed_text is None:
        target.write_bytes(unplanted_seed())
    elif isinstance(seed_text, bytes):
        target.write_bytes(seed_text)
    else:
        target.write_bytes(seed_text.encode("utf-8"))
    return root


def _seed(root: pathlib.Path) -> pathlib.Path:
    return root / SEED_RELPATH


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(
    module: ModuleType,
    argv: list[str],
    *,
    root: pathlib.Path | None = None,
    capsys: pytest.CaptureFixture[str] | None = None,
) -> tuple[int, str]:
    """Drive ``main()`` the way the workflow step drives it: argv in, exit code out."""
    if root is not None:
        argv = [*argv, "--repo-root", str(root)]
    code = module.main(argv)
    return code, (capsys.readouterr().out if capsys is not None else "")


def _manifest(root: pathlib.Path) -> dict[str, Any]:
    return json.loads((root / SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))


# ── 0. the control set can find what it controls ───────────────────────────────────────


def test_the_repository_root_resolved_to_the_right_place() -> None:
    """A wrong root would make every path here miss, and a control that reads nothing passes."""
    assert (REPO_ROOT / "pyproject.toml").is_file(), (
        f"{REPO_ROOT} is not this repository's root; every path in this file is relative to it."
    )
    assert PROGRAM_PATH.is_file()
    assert REAL_SEED.is_file()


# ── 1. the two claims the catalogue makes about files it does not own ───────────────────


def test_the_catalogue_anchor_appears_exactly_once_in_the_committed_seed() -> None:
    """The claim on which the entire 2x2 rests, checked against the seed that ships.

    ``plant_defect`` refuses a no-op, so a stale anchor cannot silently produce a false
    proof IN CI — but it does turn ``cluster-lane-bites`` red at the plant step with a
    message about the seed, days after whoever reformatted the seed has moved on. This
    control moves that discovery into the suite of the commit that causes it.

    READ-ONLY, against the real tree, on purpose: a temporary copy could not make this
    assertion, because the assertion IS about the shipped file. This is also the ONE control
    here that reads the working tree rather than :func:`unplanted_seed`, which makes it the
    one that goes red while a plant is applied — deliberately. A plant left applied is the
    single condition this whole harness exists to prevent, and a suite that stayed green
    through it would be the wrong suite.
    """
    anchor = real().catalogue()[SLUG].anchor
    hits = [
        index
        for index, line in enumerate(REAL_SEED.read_text(encoding="utf-8").splitlines(), start=1)
        if line.strip() == anchor
    ]
    live_plant = (REPO_ROOT / SNAPSHOT_DIR / "manifest.json").is_file()
    assert len(hits) == 1, (
        f"{SEED_RELPATH} contains {len(hits)} line(s) equal to the catalogue's anchor "
        f"{anchor!r} (lines {hits}); the plant needs exactly one.\n"
        "\n"
        + (
            f"A PLANT IS CURRENTLY APPLIED: {SNAPSHOT_DIR}/manifest.json exists. This is "
            "almost certainly the whole cause, and the fix is to revert it - "
            "`python scripts/ci/plant_cluster_defect.py --revert` - not to touch the seed "
            "or the catalogue. A planted defect must never survive the job that planted it.\n"
            if live_plant
            else f"No plant is recorded ({SNAPSHOT_DIR}/manifest.json is absent), so the "
            "seed itself has moved.\n"
        )
        + "\n"
        "THE SEED IS AUTHORITATIVE AND THE CATALOGUE IS THE DERIVED SIDE. If the seed "
        "legitimately changed, update the plant to name what it now edits, in the same "
        "commit, and say so. Do NOT edit demo_world.sql to restore this anchor - that is "
        "the exact edit this repository has already been damaged by once."
    )


def test_the_test_named_as_caught_by_exists_and_can_only_speak_with_a_cluster() -> None:
    """``caught_by`` is a claim about a test in another file, and the 2x2 asserts on it.

    Cell 4 of ``cluster-lane-bites.yml`` does not settle for "the cluster lane went red" —
    it requires that THIS named test be among the failures, because a red for an unrelated
    reason is not a falsifiability proof. That check is only as good as the name, and the
    name is a string in a catalogue that no rename would update.

    The ``requires_cluster`` marker is the second half and the sharper one: a plant caught
    by a test that runs WITHOUT a database would make cell 3 (plant present, ``--crdb=none``)
    red, and the whole argument - that the hermetic lane provably could not have seen this
    defect - would collapse.
    """
    caught_by = real().catalogue()[SLUG].caught_by
    path_part, _, test_name = caught_by.partition("::")
    module_path = REPO_ROOT / path_part
    assert module_path.is_file(), (
        f"the catalogue says plant {SLUG!r} is caught by {caught_by}, but {path_part} does "
        "not exist. cluster-lane-bites.yml asserts that this exact test is among cell 4's "
        "failures; a name that resolves to no file makes that assertion unsatisfiable."
    )
    text = module_path.read_text(encoding="utf-8")
    assert f"def {test_name}(" in text, (
        f"{path_part} carries no test named {test_name!r}. The catalogue's `caught_by` was "
        "left behind by a rename, and cell 4 of the 2x2 is asserting on a test that no "
        "longer exists."
    )
    marker_and_def = f"@pytest.mark.requires_cluster\ndef {test_name}("
    assert marker_and_def in text.replace("\r\n", "\n"), (
        f"{test_name} is no longer marked `requires_cluster`. If it can run without a "
        "database then it would fail in cell 3 as well - plant present, --crdb=none - and "
        "the 2x2 would no longer be showing that the hermetic lane could not have seen this "
        "defect. That is a finding about the plant, and the answer is a DIFFERENT PLANT, "
        "never a looser assertion."
    )


# ── 2. plant and revert, the round trip ────────────────────────────────────────────────


def test_plant_then_revert_restores_the_seed_byte_for_byte(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The property the whole harness exists to guarantee, with its own negative control.

    "Restored byte for byte" is trivially satisfied by a plant that never edited anything,
    which is why the middle assertion is here and is not decoration: the digest must MOVE
    when the plant is applied. A round trip that never left is not a round trip.
    """
    module = real()
    root = _tree(tmp_path)
    before = _sha(_seed(root))

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 0, f"the plant should have applied; it exited {code}\n{printed}"
    planted = _sha(_seed(root))
    assert planted != before, (
        "THE NEGATIVE CONTROL FAILED: --plant reported success and the seed's digest did not "
        "move, so the round trip below would prove nothing. A plant that silently no-ops is "
        "the failure mode this program is built to refuse."
    )
    assert (root / SNAPSHOT_DIR / "manifest.json").is_file()

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 0, f"the revert should have applied; it exited {code}\n{printed}"
    assert _sha(_seed(root)) == before, (
        "the seed was NOT restored byte for byte. This is the one failure in this program "
        "that leaves a deliberately planted credential defect in a deployed seed file."
    )
    assert not (root / SNAPSHOT_DIR).exists(), (
        f"{SNAPSHOT_DIR}/ survived the revert. The bites lane's final assertion is that "
        "`git status --porcelain` is EMPTY, which catches an untracked leftover as well as a "
        "modified file; a surviving snapshot directory is exactly such a leftover."
    )


def test_the_plant_edits_one_line_and_that_line_is_the_enrolment(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exactly one line differs, it is the line the manifest names, and it carries the swap.

    The specimen is the historical damage re-enacted: the enrolment expression replaced by
    the constant ``gate_run`` derived. The constant is DERIVED here, from the same
    expression the program derives it from, because a second copy of a 32-byte literal is
    the defect class this area of the repository keeps closing.
    """
    module = real()
    root = _tree(tmp_path)
    original = _seed(root).read_text(encoding="utf-8").splitlines()

    code, _ = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 0
    planted = _seed(root).read_text(encoding="utf-8").splitlines()

    assert len(planted) == len(original), "the plant changed the seed's line count"
    differing = [i for i, (a, b) in enumerate(zip(original, planted, strict=True)) if a != b]
    assert len(differing) == 1, f"the plant changed {len(differing)} lines, expected exactly 1"

    lineno = differing[0] + 1
    assert _manifest(root)["line"] == lineno, (
        f"the manifest records line {_manifest(root)['line']} but line {lineno} is what moved. "
        "The manifest is what a human reads to check the harness by hand."
    )

    derived = hashlib.sha256(b"credsigner").hexdigest()
    assert derived in planted[differing[0]], (
        "the planted line does not carry sha256(b'credsigner'), the value gate_run derived. "
        "This plant is a re-enactment of a specific historical edit, and a plant that swaps "
        "in some other value is not testing that the seed still refuses that one."
    )
    assert "digest(" not in planted[differing[0]]


def test_the_plant_preserves_indentation_and_line_endings(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CRLF in, CRLF out — because a whole-file rewrite would be a diff nobody planted.

    On Windows a checkout can carry CRLF. If the program normalised endings, every line in
    the file would differ, ``git status`` would report the seed modified for reasons nobody
    chose, and the bites lane's cleanliness assertion would fire on the wrong cause.
    """
    module = real()
    text = unplanted_seed().decode("utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
    root = _tree(tmp_path, text.encode("utf-8"))

    original_line = next(
        line for line in text.splitlines() if line.strip() == module.catalogue()[SLUG].anchor
    )
    indent = original_line[: len(original_line) - len(original_line.lstrip())]

    code, _ = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 0
    raw = _seed(root).read_bytes()
    assert raw.count(b"\r\n") == text.count("\r\n"), "the plant rewrote the file's line endings"
    assert b"\n" not in raw.replace(b"\r\n", b""), "the plant introduced a bare LF"

    lineno = _manifest(root)["line"]
    planted_line = raw.decode("utf-8").splitlines()[lineno - 1]
    assert planted_line.startswith(indent) and planted_line[len(indent)] != " ", (
        f"the planted line {planted_line!r} does not carry the anchor's own indentation "
        f"{indent!r}. Indentation and line endings are the FILE's business, not the "
        "catalogue's; a plant that reindents is a diff nobody planted."
    )
    assert "credsigner" not in planted_line, "the plant must write the derived value, not its input"
    assert hashlib.sha256(b"credsigner").hexdigest() in planted_line

    code, _ = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 0
    assert _seed(root).read_bytes() == text.encode("utf-8"), (
        "a CRLF seed did not come back byte for byte"
    )


# ── 3. every refusal ───────────────────────────────────────────────────────────────────


def test_planting_twice_refuses_and_leaves_the_first_plant_untouched(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Planting over a plant would make the snapshot describe a file that no longer exists.

    The revert would then restore the FIRST plant's "before" bytes over the SECOND plant's
    edit and verify successfully, leaving a defect in the seed and a job reporting a clean
    revert. So the second assertion here matters as much as the exit code: the refusal must
    leave the tree exactly as it found it.
    """
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    planted = _sha(_seed(root))
    first_manifest = _manifest(root)

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2, f"a second plant must refuse; it exited {code}\n{printed}"
    assert "a plant is already applied" in printed
    assert _sha(_seed(root)) == planted, "the refused second plant edited the seed anyway"
    assert _manifest(root) == first_manifest, (
        "the refused second plant overwrote the first plant's manifest, which is the record "
        "the revert restores from."
    )


def test_reverting_with_no_manifest_refuses_rather_than_reporting_a_clean_revert(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ "Nothing to revert" is a refusal, not a success, and the program says why in-file:
    a job that reverts nothing and says it reverted is how a planted defect reaches a merge.
    """
    module = real()
    root = _tree(tmp_path)

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2, f"a revert with no plant recorded must refuse; it exited {code}\n{printed}"
    assert "no plant is recorded" in printed


#: The mutant returns the text UNCHANGED rather than merely deleting the refusal. Deleting
#: it alone makes `hits[0]` raise IndexError, and a mutant that crashes demonstrates nothing
#: about the hazard: the hazard is a plant that reports success and edited nothing, which is
#: what a no-op `_substitute` produces. Measured — the first version of this mutant did
#: crash, at plant_cluster_defect.py:210, and was replaced rather than asserted around.
_NO_ANCHOR_ANCHOR: Final = "    if not hits:"
_NO_ANCHOR_TOLERATED: Final = (
    "    if not hits:\n"
    '        return text, 0, "", ""  # MUTANT: matching nothing is a silent no-op\n'
    "    if False:"
)


def test_a_missing_anchor_refuses_rather_than_planting_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The refusal that keeps the 2x2 from reporting a proof it never made.

    A plant that matched nothing leaves BOTH ``--crdb`` cells measuring an unplanted tree.
    The four results are then identical to a working run except for the one cell that goes
    green when it should go red — and that cell is the conclusion. The mutant demonstrates
    it: with the refusal removed, the program reports a successful plant over a seed it did
    not touch.
    """
    module = real()
    root = _tree(tmp_path, "-- a seed with no enrolment in it at all\nSELECT 1;\n")

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2, f"a plant with no anchor must refuse; it exited {code}\n{printed}"
    assert "would be a NO-OP" in printed
    assert not (root / SNAPSHOT_DIR).exists(), "the refused plant left a snapshot directory"

    mutant = mutate(_NO_ANCHOR_ANCHOR, _NO_ANCHOR_TOLERATED, "no_anchor_tolerated")
    mutant_root = _tree(tmp_path / "b", "-- a seed with no enrolment in it at all\nSELECT 1;\n")
    before = _sha(_seed(mutant_root))
    mutant_code, _ = _run(mutant, ["--plant", SLUG], root=mutant_root, capsys=capsys)
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the no-op refusal removed, a plant against a seed "
        f"containing no anchor was supposed to report success; it exited {mutant_code}."
    )
    assert _sha(_seed(mutant_root)) == before, (
        "the mutant was supposed to report a successful plant while changing nothing - that "
        "is what makes the real refusal load-bearing. The seed's digest moved instead, so "
        "this demonstration is no longer showing the hazard it names."
    )


_DUPLICATE_ANCHOR: Final = "    if len(hits) > 1:"
_DUPLICATE_TOLERATED: Final = "    if False:  # MUTANT: pick whichever enrolment comes first"


def test_a_duplicated_anchor_refuses_rather_than_choosing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two enrolments and the program will not choose between them.

    A seed that enrols two credentials through the same expression is a seed where the plant
    must be told which one it means. Editing the first is a silent guess, and the manifest
    would then record a line number that a reader checking the harness by hand would find
    innocent. The mutant makes that guess and the control names both line numbers.
    """
    module = real()
    text = unplanted_seed().decode("utf-8")
    anchor_line = next(
        line for line in text.splitlines() if line.strip() == real().catalogue()[SLUG].anchor
    )
    doubled = text.replace(anchor_line, anchor_line + "\n" + anchor_line, 1)
    root = _tree(tmp_path, doubled)

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2, f"a duplicated anchor must refuse; it exited {code}\n{printed}"
    assert "will not choose between them" in printed
    assert "contains 2 lines equal to" in printed, (
        "the refusal must say how many it found and where, or nobody can act on it"
    )
    assert _sha(_seed(root)) == _sha_of(doubled), "the refused plant edited the seed anyway"

    mutant = mutate(_DUPLICATE_ANCHOR, _DUPLICATE_TOLERATED, "duplicate_tolerated")
    mutant_root = _tree(tmp_path / "b", doubled)
    mutant_code, _ = _run(mutant, ["--plant", SLUG], root=mutant_root, capsys=capsys)
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the duplicate rule removed, the program was supposed "
        f"to silently edit the first of two enrolments; it exited {mutant_code}."
    )


def _sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_a_seed_that_already_carries_the_replacement_refuses_with_its_own_message(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unrecorded plant, or a seed edited to look like one — neither may be planted over.

    This is the branch that distinguishes "the seed changed" from "the damage is already
    here", and the distinction matters: the second is the historical defect present in the
    tree, not a stale catalogue entry, and it must not be reported as one.
    """
    module = real()
    derived = hashlib.sha256(b"credsigner").hexdigest()
    text = (
        unplanted_seed()
        .decode("utf-8")
        .replace(real().catalogue()[SLUG].anchor, f"decode('{derived}', 'hex'),", 1)
    )
    root = _tree(tmp_path, text)

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2, f"planting over an unrecorded plant must refuse; it exited {code}"
    assert "already contains this plant's replacement text" in printed
    assert "would be a NO-OP" not in printed, (
        "this seed must be reported as ALREADY PLANTED, not as a stale anchor. They are "
        "different findings with different owners."
    )


def test_an_unknown_slug_refuses_and_names_the_catalogue(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A typo in a workflow's ``--plant`` argument must not be a silent no-op."""
    module = real()
    root = _tree(tmp_path)
    code, printed = _run(module, ["--plant", "seed-credential-swop"], root=root, capsys=capsys)
    assert code == 2
    assert "no plant named" in printed
    assert SLUG in printed, "the refusal must name what IS available, or it is unactionable"


def test_a_directory_that_is_not_a_working_tree_refuses(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without a working tree there is nothing to prove the revert against.

    ``git status --porcelain`` is the bites lane's proof that the plant did not survive. A
    program willing to edit a directory that is not a checkout is a program whose edits
    nobody is watching.
    """
    module = real()
    root = tmp_path / "not-a-checkout"
    (root / "verticals/mainline/db/seeds/demo").mkdir(parents=True)
    (root / SEED_RELPATH).write_bytes(unplanted_seed())

    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2
    assert "is not the root of a git working tree" in printed
    code, printed = _run(module, ["--status"], root=root, capsys=capsys)
    assert code == 2, "--status must refuse the same directory --plant refuses"


def test_a_seed_that_is_not_there_refuses(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = real()
    root = _tree(tmp_path)
    _seed(root).unlink()
    code, printed = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 2
    assert "does not exist under" in printed


# ── 4. the revert's own proofs ─────────────────────────────────────────────────────────


def test_revert_refuses_when_the_file_moved_under_the_plant(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The reason ``git checkout --`` was rejected, kept working in the replacement.

    ``git checkout --`` restores from the INDEX and would discard uncommitted work in the
    seed — and the tree this program was written against had 144 uncommitted added lines in
    that file from another lead. Restoring a snapshot has the same hazard the moment
    somebody edits the file WHILE the plant is applied, so the revert hashes first and
    refuses. The assertion that matters is the second one: the other worker's edit is still
    on disk afterwards.
    """
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)

    meanwhile = _seed(root).read_text(encoding="utf-8") + "\n-- another lead was working here\n"
    _seed(root).write_text(meanwhile, encoding="utf-8")

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2, f"a revert over a modified file must refuse; it exited {code}\n{printed}"
    assert "Something edited the file while the plant was" in printed
    assert _seed(root).read_text(encoding="utf-8") == meanwhile, (
        "the refused revert overwrote the other edit anyway - which is the exact harm "
        "`git checkout --` was rejected for."
    )
    assert (root / SNAPSHOT_DIR / f"{SLUG}.orig").is_file(), (
        "the refusal must leave the snapshot in place; it is the only copy of the bytes "
        "taken before the plant, and the message tells the reader to diff it by hand."
    )


def test_revert_refuses_when_the_snapshot_is_gone(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest recording a plant whose snapshot vanished is a file this program will not
    reconstruct from a catalogue entry."""
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    (root / SNAPSHOT_DIR / f"{SLUG}.orig").unlink()

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2
    assert "is gone while the manifest still records" in printed


_RESTORE_PROOF_ANCHOR: Final = '    if restored != manifest["before_sha256"]:'
_RESTORE_PROOF_REMOVED: Final = "    if False:  # MUTANT: take the restore on trust"


def test_revert_proves_the_restore_instead_of_asserting_it(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE CONTROL ON THE CONTROL. A revert that says it reverted and did not is the worst
    outcome this harness can produce, because every downstream check believes it.

    The scenario corrupts the SNAPSHOT rather than the target, so the earlier "did the file
    move under the plant" check passes and execution reaches the post-restore hash. The
    real program writes the snapshot, re-hashes, sees a value that is not the one taken
    before the plant, and refuses. The mutant writes the same wrong bytes, deletes the
    snapshot directory, and reports a clean byte-for-byte revert — after which
    ``git status`` in CI is the only thing left that could notice, and on a lane whose
    artefacts live outside the checkout, it is looking at a file nobody expects to have
    changed.
    """
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    snapshot = root / SNAPSHOT_DIR / f"{SLUG}.orig"
    snapshot.write_bytes(snapshot.read_bytes() + b"\n-- not the bytes that were taken\n")

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2, f"a restore that does not match must refuse; it exited {code}\n{printed}"
    assert "The tree is NOT back to where it started" in printed
    assert (root / SNAPSHOT_DIR).exists(), (
        "the refusal removed the snapshot directory, so the evidence the message points at "
        "is gone and `git status` no longer shows that anything happened here."
    )

    mutant = mutate(_RESTORE_PROOF_ANCHOR, _RESTORE_PROOF_REMOVED, "restore_unproven")
    mutant_root = _tree(tmp_path / "b")
    _run(mutant, ["--plant", SLUG], root=mutant_root, capsys=capsys)
    mutant_snapshot = mutant_root / SNAPSHOT_DIR / f"{SLUG}.orig"
    mutant_snapshot.write_bytes(mutant_snapshot.read_bytes() + b"\n-- not the bytes\n")
    mutant_code, mutant_printed = _run(mutant, ["--revert"], root=mutant_root, capsys=capsys)
    assert mutant_code == 0, (
        "THE DEMONSTRATION FAILED: with the post-restore hash check removed, a revert that "
        f"put back the wrong bytes was supposed to report success; it exited {mutant_code}."
    )
    assert "restored byte-for-byte" in mutant_printed, (
        "the mutant was supposed to CLAIM a byte-for-byte restore it did not perform; that "
        "claim is what makes the real check load-bearing."
    )
    assert not (mutant_root / SNAPSHOT_DIR).exists(), (
        "the mutant was supposed to delete the evidence as well as mis-restore the file"
    )


def test_a_manifest_of_another_schema_refuses(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    path = root / SNAPSHOT_DIR / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = "mainline.ci.planted-defect/2"
    path.write_text(json.dumps(data), encoding="utf-8")

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2
    assert "declares schema" in printed


def test_an_unreadable_manifest_refuses_rather_than_guessing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A plant is recorded as applied and the program can no longer say what it replaced.

    Guessing here means running the substitution backwards against a catalogue entry that
    may since have changed. The program refuses and tells the operator to restore from git
    by hand, which is the only answer that cannot make it worse.
    """
    module = real()
    root = _tree(tmp_path)
    _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    (root / SNAPSHOT_DIR / "manifest.json").write_text("{ truncated", encoding="utf-8")

    code, printed = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 2
    assert "present but unreadable" in printed
    for argv in (["--status"], ["--plant", SLUG]):
        code, _ = _run(module, argv, root=root, capsys=capsys)
        assert code == 2, f"{argv} must refuse an unreadable manifest too, not work around it"


# ── 5. the negative controls: exit 0 is reachable, and --status can say "no" ────────────


def test_status_answers_zero_on_a_clean_tree_and_one_while_a_plant_is_present(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE NEGATIVE CONTROL FOR THIS HARNESS.

    Every other assertion in this file is of the form "it must refuse". A program hard-wired
    to ``return 2`` would satisfy all of them, and would make ``cluster-lane-bites``
    permanently red — the mirror image of a green that cannot fail and exactly as useless.
    ``--status`` is where both answers are observable in one control: 0 on a clean tree, 1
    while a plant is applied, 0 again after the revert.

    The workflow gates on this exact three-step sequence, at the start of the job and again
    at the end.
    """
    module = real()
    root = _tree(tmp_path)

    code, printed = _run(module, ["--status"], root=root, capsys=capsys)
    assert code == 0, f"a clean tree must answer 0; it answered {code}\n{printed}"
    assert "no plant is present" in printed

    code, _ = _run(module, ["--plant", SLUG], root=root, capsys=capsys)
    assert code == 0, "planting on a clean tree must succeed - exit 0 is reachable"

    code, printed = _run(module, ["--status"], root=root, capsys=capsys)
    assert code == 1, f"a planted tree must answer 1; it answered {code}\n{printed}"
    assert "PLANT PRESENT" in printed
    assert SEED_RELPATH in printed, "the status must name the file it says is planted"

    code, _ = _run(module, ["--revert"], root=root, capsys=capsys)
    assert code == 0, "reverting a planted tree must succeed - exit 0 is reachable"
    code, printed = _run(module, ["--status"], root=root, capsys=capsys)
    assert code == 0, f"the tree is back; --status must answer 0 again, not {code}\n{printed}"


def test_list_prints_the_catalogue_and_exits_zero_without_a_working_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--list`` is the one action that reads no tree, so it must not require one.

    It also carries the sentence a reviewer needs: which test is expected to catch the
    plant, and why the plant is invisible without a database. A catalogue that printed only
    slugs would be a menu, not a claim anybody could check.
    """
    module = real()
    code, printed = _run(module, ["--list"], capsys=capsys)
    assert code == 0, f"--list must exit 0 with no repository at all; it exited {code}"
    assert SLUG in printed
    assert "caught by" in printed
    assert module.catalogue()[SLUG].caught_by in printed
    assert "invisible" in printed
