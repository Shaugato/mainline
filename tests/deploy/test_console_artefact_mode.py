# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The packaged console's transport, asserted on the PACKAGED BYTES and nowhere else.

WHY THIS FILE EXISTS
====================
On 2026-08-14 the deployed demo served a **REPLAY** console: `VITE_MAINLINE_API_BASE` was
compiled into the artefact as `""`, `src/app/source-select.ts` trims that to `null` and
treats it as absent, so every byte a judge would have read came from the recorded
EvidenceBundle in `web/bundle/` while a live kernel sat behind the same origin. The founder
found it. Every local test passed over it, because every local test that looked at the
console looked at a **tree on the filesystem** — `verticals/mainline/apps/console/dist`, the
packer's input — and the thing that was uploaded, served and opened was a **zip**.

So the subject of every assertion below is the `web/` entries of
`out/lambda/mainline-demo-api-*.zip`, read through the archive's **central directory**.
Never `console/dist`. Never source. Ruling **R6** of `docs/leads/package-and-verify-plan.md`
says so, and `verticals/mainline/apps/demo-api/tests/test_response_contract.py:880-882` had
already ruled the same way about a cost question: *the packer's input tree is deliberately
NOT accepted as a stand-in.*

THE PROOF SHAPE: A CHECK THAT HAS NEVER FAILED HAS NEVER DISCRIMINATED
======================================================================
`tests/deploy/test_post_apply_verify.py` established the pattern this file follows, and it
has two halves for every property:

  * the **REAL** program — the packer embedded in `scripts/deploy/build_lambda.sh`, read off
    disk every time, never a copy of it kept here — fed a REPLAY artefact, **REFUSES**; and
  * a **MUTANT** of that program with the one line removed, fed the same artefact, does
    **NOT**.

The second half is the one that matters. An assertion that only ever runs against the real
program cannot tell you whether the property it names is still enforced; it passes just as
happily against a program in which the check has rotted into a no-op. The mutants below are
not hypothetical rot: `_mutant_untrimmed` restores the exact semantics this packer had on
the morning of 2026-08-14, and it accepts the exact artefact that reached the founder.

WHAT IS SYNTHETIC AND WHAT IS NOT
=================================
The zips built in `tmp_path` are synthetic, and they are minimal on purpose — a `web/`
entry, an `index.html`, a handler stub. The **program is the committed one**, extracted from
the shell builder exactly as that builder extracts it. And the reading of the artefact that
actually shipped is not synthetic at all: it is recorded, verbatim and by sha256, in
`evidence/deploy/console-mode.json`, and :func:`test_the_recorded_readings_reclassify` puts
every one of those recorded readings back through the committed classifier.

WHAT NONE OF THESE TESTS DO
===========================
Nothing here builds a package, runs `pip`, opens a socket, reads a DSN, or touches AWS. The
two real artefacts under `out/lambda/` are opened **read-only**, and no test writes to them:
they are the bytes that were deployed, and a control set that destroys its own subject
proves nothing twice.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import zipfile
from types import ModuleType
from typing import Any, Final

import pytest

REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]
BUILDER_SH: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.sh"
BUILDER_PS1: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.ps1"
OUT_LAMBDA: Final = REPO_ROOT / "out" / "lambda"
EVIDENCE: Final = REPO_ROOT / "evidence" / "deploy" / "console-mode.json"

#: The three literals the shipped artefact carried, measured from
#: ``out/lambda/mainline-demo-api-arm64.zip`` on 2026-08-14 and recorded by the packer
#: itself in that zip's ``.json`` sidecar. Written out here so the REPLAY fixture below is
#: the artefact that reached the founder rather than an invention resembling it, and so this
#: file keeps proving the refusal after the package on disk has been rebuilt LIVE.
SHIPPED_LITERALS: Final = {
    "VITE_MAINLINE_API_BASE": "",
    "VITE_MAINLINE_BUNDLE_URL": "./bundle/",
    "VITE_MAINLINE_LOG_VKEY": "",
}


# ══════════════════════════════════════════════════════════════════════════════════════
#  the real program, and mutants of it
# ══════════════════════════════════════════════════════════════════════════════════════


def _packer_source() -> str:
    """The embedded packer, extracted from the shell builder the way the builder does.

    Read off disk on every call. This file is a control set for that program; if the
    program moves, these controls move with it in the same commit, and a control set that
    cannot find its subject must FAIL rather than skip.
    """
    assert BUILDER_SH.is_file(), (
        f"{BUILDER_SH} does not exist. It carries the program every assertion in this file "
        "is about."
    )
    text = BUILDER_SH.read_text(encoding="utf-8").replace("\r\n", "\n")
    opening = "cat > \"$PACKER.crlf\" <<'PACKER_EOF'\n"
    assert opening in text, (
        "build_lambda.sh no longer opens its packer heredoc with the line this extractor "
        "looks for. The extractor and the builder must agree; fix them together."
    )
    start = text.index("\n", text.index(opening)) + 1
    return text[start : text.index("\nPACKER_EOF\n", start) + 1]


def _ps1_packer_source() -> str:
    """The same program as `build_lambda.ps1` extracts it, for the parity assertion."""
    text = BUILDER_PS1.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("\n", text.index("$Packer = @'\n")) + 1
    # The `+ 1` keeps the newline before the closing `'@`: the here-string drops its final
    # newline and the wrapper adds exactly one back, so the extracted program must carry it.
    return text[start : text.index("\n'@\n", start) + 1]


def _load(source: str, name: str) -> ModuleType:
    """Execute ``source`` as a fresh module, registered only for the duration of the exec."""
    module = ModuleType(name)
    module.__file__ = str(BUILDER_SH)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(source, f"{BUILDER_SH}::packer", "exec"), module.__dict__)  # noqa: S102
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def _replace(source: str, old: str, new: str, label: str) -> str:
    """One substitution, and it must bite. A mutant that did not mutate proves nothing."""
    assert source.count(old) == 1, (
        f"the {label} mutation expected exactly one occurrence of its anchor and found "
        f"{source.count(old)}. The program moved; move the mutant with it, do not delete it."
    )
    return source.replace(old, new)


@pytest.fixture(name="packer")
def _packer() -> ModuleType:
    """The committed packer, loaded fresh so one test's refusals never reach another."""
    return _load(_packer_source(), "mainline_packer_real")


def _mutant_name_keyed() -> ModuleType:
    """The packer as it behaved before 2026-08-14: keyed on the variable NAME, not its VALUE.

    This is not an invented weakness, and it is not a one-character edit chosen to be easy
    to make. It is the rule the program actually applied: `.env.demo` DECLARES
    `VITE_MAINLINE_API_BASE` and leaves it empty on purpose, the old probe recorded the key
    as present, and the branch that would have complained was reachable only when NO
    `VITE_MAINLINE_*` literal at all was found. Restore that rule and the artefact which
    reached the founder is accepted, which is what happened.
    """
    source = _replace(
        _packer_source(),
        '    initial = "live" if sources["live"] else ("replay" if sources["replay"] else None)\n',
        "    initial = (\n"
        '        "live"\n'
        '        if SOURCE_VARIABLE["live"] in literals\n'
        '        else ("replay" if SOURCE_VARIABLE["replay"] in literals else None)\n'
        "    )\n",
        "name-keyed",
    )
    return _load(source, "mainline_packer_name_keyed")


def _mutant_untrimmed() -> ModuleType:
    """The packer with `trimmed()` reduced to the identity function."""
    source = _replace(
        _packer_source(),
        "    if value is None:\n        return None\n    text = value.strip()\n"
        '    return None if text == "" else text\n',
        "    return value\n",
        "untrimmed",
    )
    return _load(source, "mainline_packer_untrimmed")


def _mutant_no_package_gate() -> ModuleType:
    """The packer with the packaged-bytes gate removed, leaving only the directory probe."""
    source = _replace(
        _packer_source(),
        "    if not transport_satisfied(packaged, transport):\n        refuse(\n"
        '            "PACKAGE CONSOLE TRANSPORT",\n',
        '    if False:\n        refuse(\n            "PACKAGE CONSOLE TRANSPORT",\n',
        "no-package-gate",
    )
    return _load(source, "mainline_packer_no_package_gate")


# ══════════════════════════════════════════════════════════════════════════════════════
#  synthetic artefacts
# ══════════════════════════════════════════════════════════════════════════════════════


def _chunk(literals: dict[str, str], build_id: str = "unknown", mode: str = "demo") -> str:
    """A JavaScript chunk carrying the `define` literals vite inlines, in vite's shape."""
    pairs = ", ".join(f'{key}:"{value}"' for key, value in sorted(literals.items()))
    return (
        "const e={" + pairs + f', MODE:"{mode}"' + "};"
        f'const h={{buildId:"{build_id}"}};'
        "export{e as env,h as honesty};\n"
    )


def _package(
    directory: pathlib.Path,
    name: str,
    literals: dict[str, str] | None,
    *,
    build_id: str = "unknown",
    extra_chunk: dict[str, str] | None = None,
) -> pathlib.Path:
    """A minimal zip shaped like the real package: a handler, an index, web/assets/*.js.

    ``literals is None`` writes a chunk with no VITE_MAINLINE_* literal at all, which is
    what a console built without ``--mode demo`` produces — and what
    ``out/lambda/mainline-demo-api-x86_64.zip`` carries today.
    """
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "mainline_demo_api/app.py", "def handler(event, context):\n    return {}\n"
        )
        archive.writestr("web/index.html", '<!doctype html><script src="./assets/index-a.js">\n')
        archive.writestr("web/assets/index-a.js", _chunk(literals or {}, build_id=build_id))
        if extra_chunk is not None:
            archive.writestr("web/assets/surface-b.js", _chunk(extra_chunk, build_id=build_id))
        # A .gz sibling of the same chunk. Interface I1 gives it no name of its own, and a
        # probe that read it as text would count one artefact twice.
        archive.writestr("web/assets/index-a.js.gz", b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff")
    return path


LIVE_ONLY: Final = {"VITE_MAINLINE_API_BASE": "/", "VITE_MAINLINE_LOG_VKEY": ""}
BOTH_SOURCES: Final = {
    "VITE_MAINLINE_API_BASE": "/",
    "VITE_MAINLINE_BUNDLE_URL": "./bundle/",
    "VITE_MAINLINE_LOG_VKEY": "",
}


def _verdict(packer: ModuleType, package: pathlib.Path, transport: str) -> list[str]:
    """Refusals the packaged-bytes gate raises for ``package`` under ``transport``."""
    packer.refusals[:] = []
    packaged = packer.probe_console_package(str(package))
    packer.package_console_gate(packaged, packaged, transport)
    return list(packer.refusals)


# ══════════════════════════════════════════════════════════════════════════════════════
#  (a) the two builders carry one program
# ══════════════════════════════════════════════════════════════════════════════════════


def test_both_builders_embed_the_same_packer() -> None:
    """`build_lambda.ps1` cannot ship what `build_lambda.sh` refuses, or the reverse.

    The guard is worth nothing if a second entry point into the same build does not carry
    it, and "the two agree" has to be a comparison rather than a claim — which is the
    reason both scripts print the extracted program's sha256.
    """
    assert _packer_source() == _ps1_packer_source(), (
        "the embedded packer has drifted between build_lambda.sh and build_lambda.ps1. "
        "Both scripts print its sha256 at build time precisely so this is one line of "
        "output apart; whichever was edited, the other has to follow in the same commit."
    )


def test_both_builders_require_the_transport_declaration() -> None:
    """Neither entry point has a default for what the console is meant to do on load."""
    sh = BUILDER_SH.read_text(encoding="utf-8")
    ps1 = BUILDER_PS1.read_text(encoding="utf-8")
    assert 'CONSOLE_TRANSPORT=""' in sh, "build_lambda.sh gave --console-transport a default"
    assert "$ConsoleTransport = ''" in ps1, "build_lambda.ps1 gave -ConsoleTransport a default"
    assert "--console-transport" in sh and "-ConsoleTransport is REQUIRED" in ps1


def test_the_packer_offers_the_consolecheck_mode(packer: ModuleType) -> None:
    """An artefact already on disk can be held to the rule without being rebuilt.

    This is the mode that made the demonstration in `evidence/deploy/console-mode.json`
    possible: the package that reached the founder is still on disk, and re-building it to
    find out what it was would have destroyed the only copy of the bytes a judge met.
    """
    assert callable(packer.consolecheck)
    assert callable(packer.probe_console_package)
    assert callable(packer.package_console_gate)


# ══════════════════════════════════════════════════════════════════════════════════════
#  (b) the subject is the archive
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_build_reads_the_finished_zip_and_not_the_input_tree() -> None:
    """Ruling R6, pinned in the program's own text rather than in a comment here."""
    source = _packer_source()
    assert "packaged = probe_console_package(args.out)" in source, (
        "build() no longer reads the finished artefact. R6 makes the packaged web/ entries "
        "the subject; console/dist is this program's INPUT and <stage>/web is its SCRATCH, "
        "and a check on either of them is the check that passed over the artefact which "
        "reached the founder."
    )
    assert "package_console_gate(console, packaged, args.console_transport)" in source
    # The archive must be read AFTER it is written, or it is not the archive being read.
    assert source.index("entries, unzipped = pack(stage, args.out)") < source.index(
        "packaged = probe_console_package(args.out)"
    )


def test_probe_console_package_will_not_accept_a_directory(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """A directory is not a package, and the reader must not quietly treat one as one."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "index-a.js").write_text(_chunk(LIVE_ONLY), encoding="utf-8")
    with pytest.raises((IsADirectoryError, PermissionError, OSError)):
        packer.probe_console_package(str(dist))


def test_a_live_input_tree_does_not_excuse_a_replay_archive(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """The exact substitution R6 forbids, driven: the directory says LIVE, the zip says not.

    This is the shape of the 2026-08-14 defect generalised. Whatever a tree on the
    filesystem carries, the bytes that are uploaded are the ones that answer for the demo,
    and the gate refuses on those.
    """
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "index-a.js").write_text(_chunk(BOTH_SOURCES), encoding="utf-8")
    staged = packer.probe_console(str(dist))
    assert staged["initial"] == "live", "the fixture's input tree must be the LIVE one"

    package = _package(tmp_path, "replay.zip", dict(SHIPPED_LITERALS))
    packer.refusals[:] = []
    packaged = packer.probe_console_package(str(package))
    packer.package_console_gate(staged, packaged, "live")
    codes = " ".join(packer.refusals)
    assert "PACKAGE CONSOLE TRANSPORT" in codes
    assert "PACKAGE CONSOLE DRIFT" in codes, (
        "an input tree that carries a different transport from the archive packed out of it "
        "is a packing defect, and it is invisible to any check that reads only one of them."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  (c) it refuses REPLAY, and it accepts LIVE
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_shipped_literals_read_as_replay(packer: ModuleType, tmp_path: pathlib.Path) -> None:
    """`VITE_MAINLINE_API_BASE:""` is compiled in, and it is ABSENT. Both are true."""
    package = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS), build_id="dev")
    reading = packer.probe_console_package(str(package))
    assert reading["literals"]["VITE_MAINLINE_API_BASE"] == [""], (
        "the reading must keep the compiled value verbatim: an empty string that was "
        "compiled in is a different fact from a variable that was never named, and a "
        "reader of the sidecar has to be able to tell them apart."
    )
    assert reading["sources"]["live"] is None, "an empty API base is UNSET, as in the browser"
    assert reading["initial"] == "replay"
    assert reading["switchable"] is False
    assert reading["effective"] == ["replay"]


def test_the_gate_refuses_the_artefact_that_reached_the_founder(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """The headline. A REPLAY package declared LIVE is REFUSED, not warned about."""
    package = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS), build_id="dev")
    refusals = _verdict(packer, package, "live")
    assert refusals, (
        "the packaged-bytes gate accepted a REPLAY artefact under --console-transport live. "
        "That is the artefact the founder opened on 2026-08-14."
    )
    assert any("PACKAGE CONSOLE TRANSPORT" in line for line in refusals)
    assert any("REFUSED" in line for line in refusals), "a warning is not a refusal"


def test_the_gate_accepts_a_live_archive(packer: ModuleType, tmp_path: pathlib.Path) -> None:
    """And it accepts the artefact the wave exists to produce. Both halves, or neither."""
    package = _package(tmp_path, "live.zip", dict(LIVE_ONLY))
    assert _verdict(packer, package, "live") == []


def test_the_gate_accepts_a_switchable_archive(packer: ModuleType, tmp_path: pathlib.Path) -> None:
    """Both sources compiled in: LIVE on load, REPLAY one control away. R2's artefact."""
    package = _package(tmp_path, "both.zip", dict(BOTH_SOURCES))
    assert _verdict(packer, package, "both") == []
    assert _verdict(packer, package, "live") == [], (
        "selectSource starts a both-carrying build LIVE, so --console-transport live is a "
        "true description of it."
    )
    assert _verdict(packer, package, "replay") != [], (
        "with both compiled in the page starts LIVE, so 'replay' would be a false "
        "description of what it does on load."
    )


def test_a_deliberate_replay_package_is_still_buildable(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """The opt-out is a sentence somebody typed, and it is never a default.

    `--console-transport replay` is that sentence. It is REQUIRED — there is no build
    without it — which is strictly more than an opt-out flag asks for: it is impossible to
    produce a REPLAY package by omission.
    """
    package = _package(tmp_path, "replay.zip", dict(SHIPPED_LITERALS))
    assert _verdict(packer, package, "replay") == []


def test_a_no_source_archive_is_refused_under_every_declaration(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """A site that loads and renders nothing is not a Phase-1 demo, and no flag makes it one.

    `out/lambda/mainline-demo-api-x86_64.zip` is in exactly this state today: 18 chunks,
    `MODE:"production"`, and not one VITE_MAINLINE_* literal.
    """
    package = _package(tmp_path, "nosource.zip", None)
    reading = packer.probe_console_package(str(package))
    assert reading["initial"] is None and reading["effective"] == []
    for transport in ("live", "replay", "both"):
        assert _verdict(packer, package, transport) != [], (
            f"--console-transport {transport} accepted an artefact carrying no source at all"
        )


def test_an_archive_with_no_web_assets_is_refused(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """Nothing to read is not the same as nothing wrong, and it must not read as accepted."""
    path = tmp_path / "bare.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mainline_demo_api/app.py", "\n")
    packer.refusals[:] = []
    packaged = packer.probe_console_package(str(path))
    assert packaged["scanned"] == 0
    packer.package_console_gate({"scanned": 4}, packaged, "live")
    assert any("PACKAGE NO CONSOLE ASSETS" in line for line in packer.refusals)


def test_the_gz_siblings_are_not_read_as_text(packer: ModuleType, tmp_path: pathlib.Path) -> None:
    """One set of bytes, one name. Under interface I1 a `.gz` is not separately servable."""
    package = _package(tmp_path, "live.zip", dict(LIVE_ONLY))
    with zipfile.ZipFile(package) as archive:
        assert "web/assets/index-a.js.gz" in archive.namelist(), "the fixture must carry one"
    assert packer.probe_console_package(str(package))["scanned"] == 1


def test_two_chunks_disagreeing_is_two_builds_in_one_tree(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """A key with two values across chunks cannot be described by any single declaration."""
    package = _package(
        tmp_path,
        "mixed.zip",
        dict(LIVE_ONLY),
        extra_chunk={"VITE_MAINLINE_API_BASE": "https://elsewhere.example"},
    )
    reading = packer.probe_console_package(str(package))
    assert reading["literals"]["VITE_MAINLINE_API_BASE"] == ["/", "https://elsewhere.example"]
    packer.refusals[:] = []
    packer.console_gate(reading, "live")
    assert any("MIXED CONSOLE" in line for line in packer.refusals)


# ══════════════════════════════════════════════════════════════════════════════════════
#  (d) the mutants — the half that proves the check discriminates
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_name_keyed_packer_accepts_what_the_real_one_refuses(
    tmp_path: pathlib.Path,
) -> None:
    """The 2026-08-14 rule, restored, on the 2026-08-14 artefact. It passes.

    This is the whole finding in one assertion. The mutant is not a strawman: it is the
    rule the program applied, and the package it accepts is the package that was served.
    """
    package = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS), build_id="dev")

    real = _load(_packer_source(), "mainline_packer_real_for_mutation")
    assert _verdict(real, package, "live") != [], "the real program must refuse it"

    mutant = _mutant_name_keyed()
    assert _verdict(mutant, package, "live") == [], (
        "a packer that asks whether VITE_MAINLINE_API_BASE was NAMED, rather than what it "
        "was set TO, accepts the REPLAY artefact -- which is what happened. If this "
        "assertion fails, the real program's refusal is coming from somewhere other than "
        "the value test, and the property this file names is not the property enforced."
    )


def test_removing_trimmed_alone_does_not_restore_the_defect(
    tmp_path: pathlib.Path,
) -> None:
    """MEASURED, not assumed: empty-is-unset is enforced in two independent places.

    `trimmed()` returns `None` for `""`, and `_classify` then selects on the TRUTH of the
    chosen value rather than on its presence. Reduce `trimmed()` to the identity and the
    empty string survives as far as `sources["live"] == ""`, where the second test catches
    it and the artefact is still refused.

    This assertion exists because the obvious mutation did NOT discriminate when it was
    first tried, and the honest response to a mutant that fails to kill the program is to
    record why rather than to reach for a mutation that flatters the test. Depth here is
    worth having: a single line rotting in either place does not silently re-open the door
    the founder walked through.
    """
    package = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS))
    mutant = _mutant_untrimmed()
    assert mutant.trimmed("") == "", "the mutation must actually reach trimmed()"
    assert _verdict(mutant, package, "live") != [], (
        "the second defence is gone: _classify no longer tests the VALUE it chose, so "
        "empty-is-unset now rests on trimmed() alone."
    )


def test_a_packer_without_the_packaged_gate_accepts_a_replay_archive(
    tmp_path: pathlib.Path,
) -> None:
    """Remove the gate on the packaged bytes and the REPLAY archive walks through."""
    package = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS))
    mutant = _mutant_no_package_gate()
    assert _verdict(mutant, package, "live") == []
    real = _load(_packer_source(), "mainline_packer_real_for_gate_mutation")
    assert _verdict(real, package, "live") != []


# ══════════════════════════════════════════════════════════════════════════════════════
#  (e) the recorded measurement of the artefact that actually shipped
# ══════════════════════════════════════════════════════════════════════════════════════


def _evidence() -> dict[str, Any]:
    assert EVIDENCE.is_file(), (
        f"{EVIDENCE} does not exist. It records what the packaged console carried on the day "
        "the founder opened the demo; without it that measurement survives only in prose."
    )
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_the_recorded_readings_reclassify(packer: ModuleType) -> None:
    """Every recorded reading, put back through the committed classifier, agrees with itself.

    The zips under `out/` are gitignored and will be rebuilt; this record is the permanent
    copy of what was measured, keyed by sha256. Re-deriving the verdict from the recorded
    literals — rather than re-reading a file that has since moved — is what keeps the proof
    true after W5 rebuilds the package LIVE.
    """
    readings = _evidence()["readings"]
    assert readings, "the record names no readings at all"
    for reading in readings:
        console = reading["console"]
        # `literals` is reported as {key: [values]}; _classify wants {key: {value: [names]}}.
        literals = {
            key: {value: [] for value in values} for key, values in console["literals"].items()
        }
        again = packer._classify(literals, {}, set(), console["scanned"], None)
        for field in ("sources", "effective", "initial", "switchable"):
            assert again[field] == console[field], (
                f"{reading['artifact']}: the committed classifier no longer reads the "
                f"recorded literals the way they were recorded ({field}). Either the record "
                "is stale or the rule moved; both are findings, and neither is fixed by "
                "editing the record to match."
            )
        satisfied = packer.transport_satisfied(console, reading["transport_declared"])
        assert satisfied == (reading["verdict"] == "ACCEPTED"), (
            f"{reading['artifact']} was recorded as {reading['verdict']} under "
            f"--console-transport {reading['transport_declared']}, and the committed gate "
            "no longer agrees."
        )


def test_the_record_holds_the_refusal_of_the_artefact_that_shipped() -> None:
    """At least one recorded reading is a REFUSAL of a real, deployed artefact under `live`.

    A record made only of acceptances would document a guard that has never fired.
    """
    refused = [
        reading
        for reading in _evidence()["readings"]
        if reading["verdict"] == "REFUSED"
        and reading["transport_declared"] == "live"
        and reading.get("synthetic") is not True
    ]
    assert refused, (
        "the record contains no refusal of a real artefact under --console-transport live. "
        "The demonstration that this guard discriminates is the demonstration that it "
        "refused the package which was serving when the founder opened it."
    )
    for reading in refused:
        assert reading["console"]["initial"] != "live"
        assert len(reading["sha256"]) == 64


def test_the_record_names_the_program_that_produced_it() -> None:
    """The reading is only evidence if a reader can tell which program took it.

    No `packer` fixture: this assertion is about the RECORD on disk, not about the loaded
    program. Taking the fixture would have loaded a module the test never reads.
    """
    record = _evidence()
    assert record["program"]["builder"] == "scripts/deploy/build_lambda.sh"
    assert record["program"]["packer_sha256"] == record["program"]["twin_packer_sha256"], (
        "the record was taken from a tree in which the two builders had drifted"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  (f) the artefacts on disk, if this machine has built any
# ══════════════════════════════════════════════════════════════════════════════════════


def test_every_package_on_disk_agrees_with_its_own_gate(packer: ModuleType) -> None:
    """For each real zip present: refused exactly when it does not start LIVE.

    Deliberately an INVARIANT and not a mode. `out/lambda/*.zip` is gitignored and is REPLAY
    today and LIVE after the rebuild this wave calls for; a test that pinned today's mode
    would have to be edited to let the fix land, and a ratchet you edit to pass is not one.
    What may never change is that the verdict follows the reading.
    """
    for package in sorted(OUT_LAMBDA.glob("*.zip")):
        reading = packer.probe_console_package(str(package))
        for transport in ("live", "replay", "both"):
            packer.refusals[:] = []
            packer.package_console_gate(reading, reading, transport)
            refused = bool(packer.refusals)
            assert refused == (not packer.transport_satisfied(reading, transport)), (
                f"{package.name} under --console-transport {transport}"
            )


def _tree(tmp_path: pathlib.Path, literals: dict[str, str]) -> dict[str, str]:
    """The four inputs `--mode build` copies, plus the two wheels it insists on finding."""
    stage = tmp_path / "stage"
    (stage / "psycopg").mkdir(parents=True)
    (stage / "psycopg" / "__init__.py").write_text("\n", encoding="utf-8")
    (stage / "psycopg_binary").mkdir()
    (stage / "psycopg_binary" / "__init__.py").write_text("\n", encoding="utf-8")

    pkg = tmp_path / "mainline_demo_api"
    pkg.mkdir()
    (pkg / "app.py").write_text("def handler(event, context):\n    return {}\n", encoding="utf-8")

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><script src="./assets/index-a.js"></script>\n', encoding="utf-8"
    )
    (dist / "assets" / "index-a.js").write_text(
        _chunk(literals, build_id="w2-control"), encoding="utf-8"
    )

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_text('{"frames": []}\n', encoding="utf-8")

    (tmp_path / "wheels").mkdir()
    return {
        "stage": str(stage),
        "source_pkg": str(pkg),
        "dist": str(dist),
        "bundle": str(bundle),
        "wheelhouse": str(tmp_path / "wheels"),
        "out": str(tmp_path / "api.zip"),
    }


def _build(packer: ModuleType, tree: dict[str, str], transport: str) -> int:
    packer.refusals[:] = []
    return packer.main(
        [
            "--mode",
            "build",
            "--stage",
            tree["stage"],
            "--out",
            tree["out"],
            "--arch",
            "arm64",
            "--platform-tag",
            "manylinux_2_28_aarch64",
            "--source-pkg",
            tree["source_pkg"],
            "--dist",
            tree["dist"],
            "--bundle",
            tree["bundle"],
            "--wheelhouse",
            tree["wheelhouse"],
            "--console-transport",
            transport,
        ]
    )


def test_a_whole_build_records_what_the_archive_carries(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """End to end: copy, prune, strip, pre-compress, pack — and then read the ARCHIVE.

    The sidecar manifest is what Terraform and every later step read, so the packaged
    reading has to survive into it. A build whose only console record described a directory
    is how "the tree I built" came to stand in for "the bytes I shipped".
    """
    tree = _tree(tmp_path, dict(BOTH_SOURCES))
    assert _build(packer, tree, "both") == 0, packer.refusals

    manifest = json.loads(pathlib.Path(tree["out"] + ".json").read_text(encoding="utf-8"))
    packaged = manifest["console"]["packaged"]
    assert packaged["initial"] == "live" and packaged["switchable"] is True
    assert packaged["note"].startswith("read from the central directory of api.zip")
    for field in ("literals", "sources", "effective", "initial", "switchable"):
        assert packaged[field] == manifest["console"][field], (
            "the archive and the staging tree disagree about the console, and the build did "
            "not say so"
        )


def test_a_whole_build_that_is_refused_leaves_no_zip_behind(
    packer: ModuleType, tmp_path: pathlib.Path
) -> None:
    """A package this program will not vouch for must not be left where a step could upload it."""
    tree = _tree(tmp_path, dict(SHIPPED_LITERALS))
    assert _build(packer, tree, "live") == 2
    assert not pathlib.Path(tree["out"]).exists(), "the refused zip is still on disk"
    assert not pathlib.Path(tree["out"] + ".json").exists()


def _mutant_no_dist_gate() -> ModuleType:
    """The packer with the DIRECTORY gate reduced to a no-op, leaving only the packaged one.

    Not a hypothetical. The directory gate is the one that was pointed at the wrong thing on
    2026-08-14 — it existed, it ran, and it did not object — so "what does this build do when
    the tree-level check is wrong?" is the question this program was reopened to answer, and
    the answer has to be that the archive still gets read.
    """
    source = _replace(
        _packer_source(),
        '    warnings = []\n\n    if console["scanned"] == 0:\n',
        '    warnings = []\n    return warnings\n\n    if console["scanned"] == 0:\n',
        "no-dist-gate",
    )
    return _load(source, "mainline_packer_no_dist_gate")


def test_the_packaged_gate_catches_what_the_directory_gate_missed(
    tmp_path: pathlib.Path,
) -> None:
    """The whole chain, with the tree-level check disabled: pack, read the ARCHIVE, refuse, delete.

    In a healthy program the packaged gate is defence in depth — `main()` runs preflight
    first, so a REPLAY dist declared LIVE never reaches `build()`, which is what the test
    above measures. This one removes the check that failed in the field and asks whether the
    artefact is still held to the declaration. It is: `pack()` writes the zip, the gate reads
    it through its own central directory, refuses, and `main()` removes the file so no later
    step can upload a package this program would not vouch for.
    """
    mutant = _mutant_no_dist_gate()
    tree = _tree(tmp_path, dict(SHIPPED_LITERALS))

    assert _build(mutant, tree, "live") == 2, (
        "with the directory gate disabled, nothing refused a REPLAY archive declared LIVE. "
        "The assertion this file exists for is then resting entirely on a check that has "
        "already been observed to look at the wrong tree."
    )
    codes = " ".join(mutant.refusals)
    assert "PACKAGE CONSOLE TRANSPORT" in codes, f"refusals seen: {mutant.refusals}"
    assert "CONSOLE TRANSPORT]" not in codes.replace("PACKAGE CONSOLE TRANSPORT", ""), (
        "the directory gate was supposed to be disabled in this mutant"
    )
    assert not pathlib.Path(tree["out"]).exists(), (
        "the zip the packaged gate refused is still on disk, where terraform's "
        "filebase64sha256 would hash it and a later step would upload it"
    )
    assert not pathlib.Path(tree["out"] + ".json").exists()

    # And the same tree, declared honestly, builds and keeps its archive.
    fresh = _tree(tmp_path / "honest", dict(SHIPPED_LITERALS))
    assert _build(mutant, fresh, "replay") == 0, mutant.refusals
    assert pathlib.Path(fresh["out"]).is_file()


def test_the_consolecheck_command_line_refuses_and_accepts(tmp_path: pathlib.Path) -> None:
    """The refusal is reachable from a COMMAND LINE, not only from an imported function.

    A gate that only a test can call is a gate no build runs. This drives the extracted
    program the way `build_lambda.sh` drives it, and checks the process exit code, because
    that is what `set -euo pipefail` in the wrapper acts on.
    """
    program = tmp_path / "_pack.py"
    program.write_text(_packer_source(), encoding="utf-8", newline="")
    replay = _package(tmp_path, "shipped.zip", dict(SHIPPED_LITERALS))
    live = _package(tmp_path, "live.zip", dict(LIVE_ONLY))

    def run(package: pathlib.Path, transport: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(program),
                "--mode",
                "consolecheck",
                "--package",
                str(package),
                "--console-transport",
                transport,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    refused = run(replay, "live")
    assert refused.returncode == 2, refused.stderr
    assert "PACKAGE CONSOLE TRANSPORT" in refused.stderr

    accepted = run(live, "live")
    assert accepted.returncode == 0, accepted.stderr
    assert "ACCEPTED" in accepted.stdout

    deliberate = run(replay, "replay")
    assert deliberate.returncode == 0, deliberate.stderr

    untyped = subprocess.run(
        [sys.executable, str(program), "--mode", "consolecheck", "--package", str(live)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert untyped.returncode == 1, "the declaration is required, never inferred"
    assert "--console-transport is REQUIRED" in untyped.stderr
