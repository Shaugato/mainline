# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""No build input reaches the console's bytes without being written down.

WHAT THIS FILE IS FOR
---------------------
``verticals/mainline/apps/demo-api/tests/test_response_contract.py`` and
``tests/deploy/test_furl_compression.py`` pin a **content-hashed filename** as a constant.
That is only legitimate if the build is reproducible, and a build is reproducible only if
every input that reaches its bytes is either a committed constant or an input somebody
named. An input nobody named is *ambient*, and this repository already paid for one:

    docs/ci/cluster-lane-package.md §4   assets/index-BKZMI9SJ.js   433,564 B
    the tests, the package, the live URL assets/index-DzVoV1YM.js   433,564 B

Two different files, the same length, both recorded as "the build at HEAD", and
``git diff eefae1c HEAD -- verticals/mainline/apps/console`` is **empty**. Measured by
``scripts/deploy/console_repro.py`` and recorded in ``evidence/deploy/console-repro.json``:
the committed source builds ``index-DzVoV1YM.js``, three times out of three, byte for byte,
and its sha256 equals the object inside ``out/lambda/mainline-demo-api-arm64.zip`` that the
Function URL is serving. ``index-BKZMI9SJ.js`` is what the **same source** builds when
``src/design/primitives/instrument.module.css`` is checked out CRLF: a CSS-module scoped
class name is a hash of the module's bytes, and a hash is a **fixed-length** string, so its
value moves and the bundle's length does not.

That input was ambient in the worst way — ``git status`` reported the tree clean, because
the index caches the CRLF worktree size and git therefore never re-read the file. So the
checks below are not about newlines. They are about the general shape: **a thing that
changes the artefact must be visible to somebody reading the repository.**

WHAT WOULD MAKE EACH TEST FAIL, IN ONE LINE EACH
-------------------------------------------------
* a new ``process.env[...]`` in ``vite.config.ts`` that nobody added to the declaration;
* a new ``VITE_*`` in ``.env.demo`` likewise;
* a new file the config probes for, unnamed;
* a ``define`` fed from something that is neither a declared input nor a literal;
* a recorded build whose runs disagree, or that records fewer than three;
* an asset recorded without a digest;
* ``.env.demo``'s committed Phase-1 values edited by a deploy instead of supplied to it;
* a console source file whose worktree bytes differ from the committed bytes **only** in
  line endings — which is drift, not work, and which git will not show you.

This file runs with ``--crdb=none``: nothing here needs a database.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "deploy"))

import console_repro  # noqa: E402  (path is established immediately above)

CONSOLE: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console"
VITE_CONFIG: Final = CONSOLE / "vite.config.ts"
ENV_DEMO: Final = CONSOLE / ".env.demo"
EVIDENCE: Final = REPO_ROOT / "evidence" / "deploy" / "console-repro.json"
BUILD_DOC: Final = REPO_ROOT / "docs" / "deploy" / "console-build.md"

#: `.env.demo`'s Phase-1 values are AUTHORITATIVE and a deploy may not edit them. The file
#: says so itself: *"Phase 2 adds the live API by supplying the variable in the ENVIRONMENT,
#: which Vite applies after every .env file, so no committed file is edited by a deploy."*
#: Pinning them here is what makes that sentence a rule rather than an intention.
COMMITTED_ENV_DEMO: Final = {
    "VITE_MAINLINE_BUNDLE_URL": "./bundle/",
    "VITE_MAINLINE_API_BASE": "",
    "VITE_MAINLINE_LOG_VKEY": "",
    "VITE_MAINLINE_CANON_SHA256": "",
}

#: Every `define` key `vite.config.ts` is allowed to compile in. A fourth one is not
#: forbidden — it is *undeclared*, which is a different and fixable thing.
DECLARED_DEFINES: Final = frozenset(
    {"__MAINLINE_BUILD_ID__", "__MAINLINE_SIGNATURE_PATH__", "__MAINLINE_ATTESTATION_SOURCE__"}
)

_ENV_READ: Final = re.compile(r"process\.env\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]")
_ENV_DOT_READ: Final = re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)")
_DEFINE_KEY: Final = re.compile(r"^\s*(__[A-Z0-9_]+__)\s*:", re.MULTILINE)
_RESOLVE_LITERAL: Final = re.compile(r"resolve\(\s*here\s*,\s*['\"]([^'\"]+)['\"]\s*\)")
_CANDIDATE_BLOCK: Final = re.compile(
    r"const\s+ATTESTATION_CANDIDATES\s*=\s*\[(?P<body>.*?)\]", re.DOTALL
)
_QUOTED: Final = re.compile(r"['\"]([^'\"]+)['\"]")


@pytest.fixture(scope="module")
def config_source() -> str:
    return VITE_CONFIG.read_text("utf-8")


@pytest.fixture(scope="module")
def evidence() -> dict[str, Any]:
    if not EVIDENCE.is_file():
        pytest.fail(
            f"{EVIDENCE.relative_to(REPO_ROOT)} is absent. It is not optional: it is the only "
            "record that the content hash pinned as a constant elsewhere in this repository "
            "can be re-derived. Produce it with "
            "`python scripts/deploy/console_repro.py --builds 3 --source rev:HEAD "
            "--label committed-phase1`."
        )
    return json.loads(EVIDENCE.read_text("utf-8"))


# ── the declaration covers what the config actually reads ──────────────────────────────


def test_every_environment_variable_the_config_reads_is_declared(config_source: str) -> None:
    """A `define` fed from an undeclared variable is an artefact nobody can account for."""
    read = set(_ENV_READ.findall(config_source)) | set(_ENV_DOT_READ.findall(config_source))
    undeclared = sorted(read - set(console_repro.BUILD_INPUT_NAMES))
    assert not undeclared, (
        f"vite.config.ts reads {undeclared} from the environment, and "
        "scripts/deploy/console_repro.py BUILD_INPUT_NAMES does not list them. Add them "
        "there, so the next reproducibility record resolves and prints them, rather than "
        "leaving a value that reaches the emitted bytes with nowhere for a reader to find it."
    )


def test_every_vite_variable_in_the_env_file_is_declared() -> None:
    """`.env.demo` is read by Vite and every name in it lands in `import.meta.env`."""
    names = set(console_repro.parse_dotenv(ENV_DEMO))
    undeclared = sorted(names - set(console_repro.BUILD_INPUT_NAMES))
    assert not undeclared, (
        f".env.demo sets {undeclared}, which scripts/deploy/console_repro.py does not declare. "
        "Every one of those is compiled into the artefact as an `import.meta.env` literal."
    )


def test_every_file_the_config_probes_for_is_declared(config_source: str) -> None:
    """An absent file is an input too: it is what compiles `unknown`/`absent`.

    Two places hold this list — the config that probes and the recorder that reports — and
    the day they disagree is the day a record says "absent" about a file the build read.
    """
    block = _CANDIDATE_BLOCK.search(config_source)
    assert block, (
        "vite.config.ts no longer declares ATTESTATION_CANDIDATES as an array literal. The "
        "filesystem paths a build probes must be enumerable by reading the file."
    )
    probed = {literal.split("../")[-1].lstrip("./") for literal in _QUOTED.findall(block["body"])}
    inline = {
        literal.split("../")[-1].lstrip("./") for literal in _RESOLVE_LITERAL.findall(config_source)
    }
    declared = set(console_repro.ATTESTATION_CANDIDATES)
    assert probed == declared, (
        f"vite.config.ts probes {sorted(probed)}; console_repro.ATTESTATION_CANDIDATES lists "
        f"{sorted(declared)}. Whether a file exists is a build input, and a record of a build "
        "can only report the probes it was told about."
    )
    undeclared_inline = sorted(inline - declared)
    assert not undeclared_inline, (
        f"vite.config.ts probes {undeclared_inline} inline rather than through "
        "ATTESTATION_CANDIDATES, so it is invisible to the recorder."
    )


def test_the_defines_are_exactly_the_declared_three(config_source: str) -> None:
    keys = set(_DEFINE_KEY.findall(config_source))
    assert keys == set(DECLARED_DEFINES), (
        f"vite.config.ts compiles {sorted(keys)}; this test declares {sorted(DECLARED_DEFINES)}. "
        "A define is a value substituted into every module before minification: adding one "
        "changes the artefact, so adding one changes this list too, deliberately."
    )


def test_no_define_is_fed_by_something_undeclared(config_source: str) -> None:
    """Each `define` value must resolve from a declared input, a probe, or a literal.

    Read as a whole-file property rather than by parsing the expression: the config's only
    sources of variability are the environment and the filesystem probe, both checked above,
    so what is left to refuse is a third one — a clock, a random, a hostname, a git call.
    """
    forbidden = {
        "Date.now": "a clock makes every build unique and every recorded hash unrepeatable",
        "new Date(": "same",
        "Math.random": "a random value in a define is nondeterminism by construction",
        "os.hostname": "the machine's name is not a property of this repository",
        "execSync": "shelling out makes the artefact depend on whatever is on PATH",
        "spawnSync": "same",
        "process.cwd": "the artefact would depend on where somebody stood when they built it",
    }
    found = sorted(token for token in forbidden if token in config_source)
    assert not found, (
        "vite.config.ts contains "
        + ", ".join(f"`{token}` ({forbidden[token]})" for token in found)
        + ". A build input that reaches the bytes must be a committed constant or a named, "
        "recorded input."
    )


# ── the recorded measurement is a measurement ──────────────────────────────────────────


def test_the_evidence_records_at_least_one_run_of_at_least_three_builds(
    evidence: dict[str, Any],
) -> None:
    runs = evidence.get("runs")
    assert runs, f"{EVIDENCE.name} records no runs"
    for label, run in runs.items():
        count = run["reproducibility"]["runs"]
        assert count >= 3, (
            f"run {label!r} records {count} build(s). Two agreeing builds is a coincidence; "
            "three is a measurement."
        )


def test_every_recorded_run_is_byte_identical_across_its_builds(evidence: dict[str, Any]) -> None:
    for label, run in evidence["runs"].items():
        verdict = run["reproducibility"]
        assert verdict["byte_identical"], (
            f"run {label!r} did not reproduce: {verdict['assets_that_differ'][:10]} differ across "
            f"{verdict['runs']} builds with the same inputs. The fix is to remove the "
            "nondeterminism at its source, never to re-record a hash that cannot be re-measured."
        )
        assert len(set(verdict["tree_digests"])) == 1


def test_every_recorded_asset_carries_a_digest(evidence: dict[str, Any]) -> None:
    """A size is not an identity. Two files of 433,564 B is exactly how this began."""
    for label, run in evidence["runs"].items():
        for build_index, build in enumerate(run["builds"]):
            assert build["assets"], f"{label}[{build_index}] recorded no assets"
            for name, meta in build["assets"].items():
                assert re.fullmatch(r"[0-9a-f]{64}", meta.get("sha256", "")), (
                    f"{label}[{build_index}] records {name} without a sha256"
                )
                assert isinstance(meta.get("bytes"), int)


def test_every_declared_input_is_resolved_in_every_recorded_run(evidence: dict[str, Any]) -> None:
    """Including the unset ones. "Unset" is a value, and it reaches the bytes."""
    for label, run in evidence["runs"].items():
        resolved = run["build_inputs"]
        missing = sorted(set(console_repro.BUILD_INPUT_NAMES) - set(resolved))
        assert not missing, f"run {label!r} does not say what {missing} resolved to"
        assert "__attestation_probe__" in resolved, (
            f"run {label!r} does not record whether the g1 attestation files were present"
        )


def test_the_recorded_command_is_the_command(evidence: dict[str, Any]) -> None:
    for label, run in evidence["runs"].items():
        assert run["command"]["argv"] == list(console_repro.BUILD_ARGV), (
            f"run {label!r} records argv {run['command']['argv']}, which is not the build this "
            f"repository performs ({list(console_repro.BUILD_ARGV)})"
        )


def test_a_live_capable_artefact_is_recorded_and_carries_both_sources(
    evidence: dict[str, Any],
) -> None:
    """R2: the artefact that ships carries BOTH sources, not LIVE instead of REPLAY.

    Read out of the emitted bytes, because that is where the fault the founder found lived:
    the command somebody meant to type is not evidence about what shipped.
    """
    live = [
        (label, run)
        for label, run in evidence["runs"].items()
        if run["compiled"]["source_select_verdict"].startswith("LIVE (with a control")
    ]
    assert live, (
        "no recorded run produced an artefact carrying both sources. The Phase-2 build is "
        "`VITE_MAINLINE_API_BASE=/ pnpm exec vite build --mode demo` — see "
        "docs/deploy/console-build.md §1."
    )
    for label, run in live:
        literals = run["compiled"]["vite_literals"]
        api = literals["VITE_MAINLINE_API_BASE"]
        assert api.strip(), f"run {label!r} claims LIVE with an empty API base"
        assert not re.match(r"^[A-Za-z]:[\\/]", api), (
            f"run {label!r} compiled VITE_MAINLINE_API_BASE={api!r} — an MSYS-converted path, "
            "not a URL base. A bare `/` typed at a Git Bash line becomes the MSYS root before "
            "the build starts, and the artefact then names a directory on somebody's laptop."
        )
        assert literals["VITE_MAINLINE_BUNDLE_URL"].strip(), (
            f"run {label!r} dropped the REPLAY source. R2 is BOTH sources: the demo that "
            "cannot fail stays one control away."
        )


# ── the committed side may not be moved to make a build easier ─────────────────────────


def test_the_env_file_still_commits_phase_one() -> None:
    """`.env.demo` prescribes its own rule; this is that rule, enforced.

    If a deploy ever "fixes" the REPLAY artefact by writing a hostname into this file, the
    committed build stops being the demo that cannot fail, and the build a judge gets stops
    being a function of the command that produced it.
    """
    values = console_repro.parse_dotenv(ENV_DEMO)
    assert values == COMMITTED_ENV_DEMO, (
        f".env.demo now sets {values}, not the committed Phase-1 values {COMMITTED_ENV_DEMO}. "
        "Phase 2 is supplied in the ENVIRONMENT, which Vite applies after every .env file, so "
        "no committed file is edited by a deploy."
    )


def test_the_build_document_states_the_phase_two_command() -> None:
    text = BUILD_DOC.read_text("utf-8")
    assert "VITE_MAINLINE_API_BASE=/" in text, (
        "docs/deploy/console-build.md must state the command that yields a LIVE-capable "
        "artefact; the deploy that reached the founder ran the Phase-1 one."
    )


# ── the input git will not show you ────────────────────────────────────────────────────


def test_no_console_source_file_differs_from_the_commit_only_in_line_endings() -> None:
    """The ambient input that produced two hashes at one length.

    Only ``src/**`` is failed here, and deliberately: that is the tree ``vite build`` reads,
    measured — CRLF in ``src/design/primitives/instrument.module.css`` alone moved the entry
    chunk from ``index-DzVoV1YM.js`` to ``index-BKZMI9SJ.js`` at an identical 433,564 B and
    moved ``Counter-*.css`` by five bytes, while CRLF in the other fifty drifted files moved
    **only source maps**, which the packer strips. Drift outside ``src/`` is reported by
    ``console_repro.newline_only_drift()`` and belongs to whoever owns those trees; this
    assertion is scoped to what reaches the artefact.

    A genuine edit is not drift and does not fail here: it changes bytes other than newlines,
    and a worker meant it.
    """
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git checkout; the committed bytes are not available to compare against")
    try:
        drift = console_repro.newline_only_drift()
    except (RuntimeError, subprocess.CalledProcessError) as exc:  # pragma: no cover
        pytest.skip(f"git is not usable here: {exc}")
    reaching = drift["reaching_vite_build"]
    assert not reaching, (
        f"{len(reaching)} console source file(s) differ from HEAD only in line endings, and "
        f"`vite build` reads all of them: {reaching}. `git status` will not show you this — "
        "the index caches the CRLF worktree size, so git declares the entry unmodified without "
        "re-reading it. A build from this tree does not produce this repository's artefact. "
        "Restore the committed bytes (`git checkout-index -f -- <path>` after clearing the "
        "stale stat, or re-clone with core.autocrlf=false), and do not re-record any hash "
        "measured while this was true."
    )
