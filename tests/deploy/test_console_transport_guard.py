# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The packaging guard that refuses a REPLAY console for an origin with a live kernel.

WHY THIS FILE EXISTS
--------------------
On 2026-08-14 the founder opened
``https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`` and the
header read ``TRANSPORT REPLAY (staged)``. Every byte on that screen was a recorded
``EvidenceBundle`` rather than the kernel the page was sitting on. The artefact carried,
measured out of the served bundle and not inferred::

    VITE_MAINLINE_API_BASE: ""
    VITE_MAINLINE_BUNDLE_URL: "./bundle/"
    buildId: "dev"

``scripts/deploy/build_lambda.sh`` had a check for exactly this and it **never fired, and
could not**. ``probe_console()`` collected ``found.setdefault(key, value)`` — keyed on the
variable **NAME**, with no test on the **VALUE** — and its caller branched on ``if
console["configured"]``. ``.env.demo`` *declares* ``VITE_MAINLINE_API_BASE`` and leaves it
empty on purpose, so vite inlines ``VITE_MAINLINE_API_BASE:""`` into every build, ``found``
was never empty, and the warning branch was unreachable. The packer printed a cheerful
``console VITE_MAINLINE_API_BASE=(empty), VITE_MAINLINE_BUNDLE_URL=./bundle/`` and packaged
it. The machinery to notice existed; it was measuring the wrong thing.

**A guard with no test that proves it fires is a guard nobody has run.** So the headline
case here is a FALSIFICATION: a synthetic dist carrying *exactly* the three literals above
must be **REFUSED** under ``--console-transport live`` and **ACCEPTED** under
``--console-transport replay``. Against the pre-2026-08-14 packer that test cannot pass —
``probe_console`` reports no ``effective`` key, ``console_gate`` does not exist, and the
packer accepts every dist it is handed.

WHAT IS UNDER TEST, AND HOW IT IS REACHED
------------------------------------------
``build_lambda.sh`` is a shell wrapper around an embedded Python program, and
``build_lambda.ps1`` carries a byte-identical copy so that "the two builders agree" is a
hash a reader can compare. This file extracts that program out of the ``.sh``, asserts the
``.ps1`` copy is identical to the byte, and then drives it two ways:

* **as functions** — ``probe_console`` and ``console_gate`` over synthetic asset files, so
  each rule is pinned separately and a failure names the rule;
* **as a program** — ``--mode preflight`` in a subprocess against a synthetic ``dist/`` and
  the repository's real handler package and evidence bundle, so the *wiring* is proved too.
  A gate that is correct and unreachable is the defect this file was written about.

NOTHING HERE BUILDS THE CONSOLE. This worker does not own ``dist/``; every asset below is
a few hundred bytes written into ``tmp_path``. The literals are the ones the deployed
artefact carries, transcribed from the measurement in ``docs/leads/console-live-plan.md``
§0.2, so the synthetic dist is a faithful stand-in for the artefact that shipped.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
BUILD_SH: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.sh"
BUILD_PS1: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.ps1"
DEPLOY_SH: Final = REPO_ROOT / "scripts" / "deploy" / "deploy.sh"
DEPLOY_PS1: Final = REPO_ROOT / "scripts" / "deploy" / "deploy.ps1"

#: The real inputs preflight needs beside the dist. They are read, never written.
SOURCE_PKG: Final = (
    REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src" / "mainline_demo_api"
)
EVIDENCE_BUNDLE: Final = (
    REPO_ROOT
    / "verticals"
    / "mainline"
    / "apps"
    / "console"
    / "fixtures"
    / "bundles"
    / "demo-cloud"
)

#: The heredoc markers each wrapper wraps the embedded packer in.
SH_BEGIN: Final = "cat > \"$PACKER.crlf\" <<'PACKER_EOF'"
SH_END: Final = "PACKER_EOF"
PS_BEGIN: Final = "$Packer = @'"
PS_END: Final = "'@"

#: **The artefact that shipped.** Transcribed from console-live-plan.md §0.2, which read
#: them out of the served bundle. ``VITE_MAINLINE_API_BASE`` is PRESENT and EMPTY — that
#: is the whole defect, and it is why a name-keyed probe called this dist "configured".
DEPLOYED_ENV: Final = (
    'VITE_MAINLINE_API_BASE:""',
    'VITE_MAINLINE_BUNDLE_URL:"./bundle/"',
    'VITE_MAINLINE_LOG_VKEY:""',
)
#: Both buildId literals the deployed chunk carries. ``"unknown"`` is ``honesty.ts``'s
#: EMPTY constant and is in every build ever made; ``"dev"`` is what ``vite.config.ts``
#: substitutes when ``MAINLINE_BUILD_ID`` was not supplied. Measured on this workstation's
#: ``dist/assets/index-DzVoV1YM.js``, both are present — which is why the guard keys on the
#: PRESENCE of ``"dev"`` and never on "there is exactly one build id".
DEPLOYED_BUILD_IDS: Final = ('buildId:"dev"', 'buildId:"unknown"')

#: A build id that names the artefact it came from, as ``MAINLINE_BUILD_ID`` would supply.
NAMED_BUILD_IDS: Final = ('buildId:"2026-08-14T09:14:02Z-9f3c1ab"', 'buildId:"unknown"')


def _packer_body(path: Path, begin: str, end: str) -> str:
    """The embedded packer, LF-normalised exactly as both wrappers normalise it."""
    lines = path.read_text(encoding="utf-8").split("\n")
    start = lines.index(begin) + 1
    stop = lines.index(end, start)
    return "\n".join(line.rstrip("\r") for line in lines[start:stop]) + "\n"


@pytest.fixture(scope="module")
def packer_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The packer, extracted from ``build_lambda.sh`` the way the wrapper extracts it."""
    target = tmp_path_factory.mktemp("packer") / "_pack_under_test.py"
    target.write_text(_packer_body(BUILD_SH, SH_BEGIN, SH_END), encoding="utf-8", newline="")
    return target


@pytest.fixture(scope="module")
def packer(packer_path: Path) -> Any:
    """Import the extracted packer by path. It is a program, not a package."""
    spec = importlib.util.spec_from_file_location("mainline_packer_under_test", packer_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.fail(f"{packer_path} is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_refusals(packer: Any) -> None:
    """``refusals`` is a module global. One test's refusal must not be another's."""
    packer.refusals[:] = []


def write_dist(
    root: Path,
    env: tuple[str, ...] = DEPLOYED_ENV,
    build_ids: tuple[str, ...] = DEPLOYED_BUILD_IDS,
    mode: str = 'MODE:"demo"',
    chunks: int = 1,
    asset_suffix: str = ".js",
) -> Path:
    """Write a synthetic ``dist/`` carrying the given compiled-in literals.

    Shaped like vite output, because the probe reads vite output: ``index.html`` naming its
    entry with a ``./assets/`` reference, and minified-looking chunks under ``assets/``.
    Nothing here builds the console — this worker does not own ``dist/``.
    """
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    names = [f"index-Synth{index}{asset_suffix}" for index in range(chunks)]
    for name in names:
        body = (
            "const q={" + ",".join(env) + "," + mode + ',BASE_URL:"./",DEV:!1,PROD:!0};'
            "const h={" + ",".join(build_ids) + ',signaturePath:"unknown"};'
            "export{q as e,h as o};\n"
        )
        (assets / name).write_text(body, encoding="utf-8", newline="")
    entry = names[0].replace(asset_suffix, ".js")
    (root / "index.html").write_text(
        '<!doctype html><html><head><script type="module" crossorigin '
        f'src="./assets/{entry}"></script></head><body><div id="root"></div></body></html>\n',
        encoding="utf-8",
        newline="",
    )
    return root


def run_gate(
    packer: Any, root: Path, transport: str
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Probe ``root`` and gate it, returning (report, refusals, warnings)."""
    packer.refusals[:] = []
    console: dict[str, Any] = packer.probe_console(str(root))
    warnings: list[str] = list(packer.console_gate(console, transport))
    return console, list(packer.refusals), warnings


def codes(refusals: list[str]) -> set[str]:
    """The bracketed refusal codes, so an assertion pins the rule and not the prose."""
    return {line.split("[", 1)[1].split("]", 1)[0] for line in refusals if "[" in line}


# --------------------------------------------------------------------------------------
# The two builders carry one program
# --------------------------------------------------------------------------------------


def test_both_builders_embed_the_same_packer_byte_for_byte() -> None:
    """A guard that lives in one of the twins and not the other is half a guard.

    Both wrappers print the packer's sha256 for exactly this reason. This asserts the
    property the digest is evidence of, so a fix applied to the ``.sh`` and forgotten in the
    ``.ps1`` fails here rather than at 03:00 on whichever machine ran the other one.
    """
    assert _packer_body(BUILD_SH, SH_BEGIN, SH_END) == _packer_body(BUILD_PS1, PS_BEGIN, PS_END)


def test_the_packer_stays_ascii_only() -> None:
    """Its own docstring says why: a smart quote is one byte in one extraction and two in
    the other, and the equality proof above would become a proof about encodings."""
    assert _packer_body(BUILD_SH, SH_BEGIN, SH_END).isascii()


# --------------------------------------------------------------------------------------
# THE FALSIFICATION: the literals the deployed artefact carries
# --------------------------------------------------------------------------------------


def test_the_deployed_artefacts_literals_are_refused_under_live(
    packer: Any, tmp_path: Path
) -> None:
    """THE case. A dist carrying what the live URL serves must not package as ``live``.

    ``VITE_MAINLINE_API_BASE:""`` with ``VITE_MAINLINE_BUNDLE_URL:"./bundle/"`` is a
    REPLAY-only console: ``src/app/source-select.ts:104`` trims the value and treats an
    empty string as unset, so ``selectSource`` starts it REPLAY and there is no control.
    Packaged for an origin with a live kernel behind it, that is a judge looking at a
    recording of a run that happened somewhere else.

    ``buildId:"dev"`` is the second defect in the same artefact and it refuses here too
    (ruling R5): an artefact that cannot name itself cannot be the artefact a screenshot
    names, which ``docs/deploy/console-build.md`` §1 says is the entire reason the field
    exists.
    """
    console, refusals, _warnings = run_gate(packer, write_dist(tmp_path), "live")

    assert console["effective"] == ["replay"]
    assert console["sources"]["live"] is None
    assert console["initial"] == "replay"
    assert console["switchable"] is False
    assert console["names_itself"] is False

    assert codes(refusals) == {"CONSOLE TRANSPORT", "CONSOLE BUILD ID"}
    joined = "\n".join(refusals)
    assert "VITE_MAINLINE_API_BASE=(empty)" in joined
    assert "VITE_MAINLINE_BUNDLE_URL=./bundle/" in joined
    assert "MAINLINE_BUILD_ID" in joined


def test_the_same_dist_is_accepted_under_replay(packer: Any, tmp_path: Path) -> None:
    """The other half of the falsification: the guard must not simply refuse everything.

    The identical bytes, declared honestly, package cleanly. The ``dev`` build id becomes an
    advisory here and not a refusal, because ``.github/actions/build-demo-package`` leaves
    ``MAINLINE_BUILD_ID`` unset ON PURPOSE — inlining a run id would move the content hash
    of ``assets/index-<hash>.js`` on every run and unpin the byte counts the cost ratchets
    read. That is a good reason, and it is only a good reason for an artefact nobody
    deploys.
    """
    _console, refusals, warnings = run_gate(packer, write_dist(tmp_path), "replay")

    assert refusals == []
    assert len(warnings) == 1
    assert 'buildId:"dev"' in warnings[0]


def test_the_same_dist_is_refused_under_both(packer: Any, tmp_path: Path) -> None:
    """``both`` claims a switchable badge. A replay-only artefact has no control to show."""
    _console, refusals, _warnings = run_gate(packer, write_dist(tmp_path), "both")

    assert "CONSOLE TRANSPORT" in codes(refusals)
    assert "CONSOLE BUILD ID" in codes(refusals)


# --------------------------------------------------------------------------------------
# The rule is `selectSource`, transcribed — not a second rule that can drift
# --------------------------------------------------------------------------------------


def test_an_empty_string_is_unset_exactly_as_the_console_reads_it(
    packer: Any, tmp_path: Path
) -> None:
    """``trimmed()`` in ``src/app/source-select.ts:104``, and the defect in three lines.

    The old probe answered "is the key there"; the console has always answered "is the value
    non-empty after a trim". Whitespace is the case that separates the two most sharply, and
    it is not hypothetical: on Git Bash a bare ``/`` becomes ``C:/Program Files/Git/``
    through MSYS path conversion, so what lands in the artefact is routinely not what was
    typed.
    """
    root = write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:"   "', 'VITE_MAINLINE_BUNDLE_URL:"./bundle/"'),
    )
    console, refusals, _warnings = run_gate(packer, root, "live")

    assert console["sources"]["live"] is None
    assert console["effective"] == ["replay"]
    assert "CONSOLE TRANSPORT" in codes(refusals)


def test_a_live_dist_passes_under_live_and_under_both(packer: Any, tmp_path: Path) -> None:
    """The Phase-2 artefact: ``.env.demo`` plus ``VITE_MAINLINE_API_BASE`` in the environment.

    ``.env.demo`` sets ``VITE_MAINLINE_BUNDLE_URL`` unconditionally, so a live build carries
    BOTH sources — and ``selectSource`` starts it LIVE, with REPLAY one control away. A gate
    that demanded a live-ONLY artefact would refuse the exact build the plan asks for, so
    ``live`` asks what the console DOES ON LOAD and ``both`` asks the stronger question.
    """
    root = write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:"/"', 'VITE_MAINLINE_BUNDLE_URL:"./bundle/"'),
        build_ids=NAMED_BUILD_IDS,
    )
    console, live_refusals, live_warnings = run_gate(packer, root, "live")

    assert console["initial"] == "live"
    assert console["switchable"] is True
    assert console["sources"]["live"] == "/"
    assert console["names_itself"] is True
    assert live_refusals == []
    assert live_warnings == []

    _console, both_refusals, both_warnings = run_gate(packer, root, "both")
    assert both_refusals == []
    assert both_warnings == []


def test_a_live_dist_is_refused_under_replay(packer: Any, tmp_path: Path) -> None:
    """``replay`` says a judge first sees the bundle. With a live source, they do not."""
    root = write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:"/"', 'VITE_MAINLINE_BUNDLE_URL:"./bundle/"'),
        build_ids=NAMED_BUILD_IDS,
    )
    _console, refusals, _warnings = run_gate(packer, root, "replay")

    assert codes(refusals) == {"CONSOLE TRANSPORT"}
    assert "--console-transport both" in "\n".join(refusals)


def test_a_live_only_dist_is_refused_under_both(packer: Any, tmp_path: Path) -> None:
    """``both`` is strictly more than ``live``: it also asserts the REPLAY control exists."""
    root = write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:"/"', 'VITE_MAINLINE_BUNDLE_URL:""'),
        build_ids=NAMED_BUILD_IDS,
    )
    console, refusals, _warnings = run_gate(packer, root, "both")

    assert console["effective"] == ["live"]
    assert console["switchable"] is False
    assert codes(refusals) == {"CONSOLE TRANSPORT"}

    _again, live_refusals, _w = run_gate(packer, root, "live")
    assert live_refusals == []


# --------------------------------------------------------------------------------------
# The cases the old code could never reach
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("transport", ["live", "replay", "both"])
def test_carrying_neither_source_is_refused_in_every_mode(
    packer: Any, tmp_path: Path, transport: str
) -> None:
    """The check the packer already had, now that it can actually fire.

    ``build_lambda.sh:879`` warned about exactly this before 2026-08-14 and was dead code:
    the branch was guarded by a truthiness test on a dict keyed by variable NAME, and
    ``.env.demo`` guarantees the names are there. It is a refusal now, in all three modes,
    because a site that loads and renders NO SOURCE on every surface is a website with no
    data whichever transport somebody meant it to have.
    """
    root = write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:""', 'VITE_MAINLINE_BUNDLE_URL:""'),
        build_ids=NAMED_BUILD_IDS,
    )
    console, refusals, _warnings = run_gate(packer, root, transport)

    assert console["initial"] is None
    assert codes(refusals) == {"CONSOLE NO SOURCE"}
    assert "NO SOURCE" in "\n".join(refusals)


def test_two_chunks_that_disagree_are_refused(packer: Any, tmp_path: Path) -> None:
    """Two builds' chunks in one tree. No declaration can be true of both halves."""
    write_dist(
        tmp_path,
        env=('VITE_MAINLINE_API_BASE:"/"', 'VITE_MAINLINE_BUNDLE_URL:"./bundle/"'),
        build_ids=NAMED_BUILD_IDS,
    )
    (tmp_path / "assets" / "index-Stale.js").write_text(
        'const q={VITE_MAINLINE_API_BASE:"https://elsewhere.example",'
        'VITE_MAINLINE_BUNDLE_URL:"./bundle/",MODE:"demo"};export{q as e};\n',
        encoding="utf-8",
        newline="",
    )
    _console, refusals, _warnings = run_gate(packer, tmp_path, "live")

    assert "MIXED CONSOLE" in codes(refusals)
    assert "VITE_MAINLINE_API_BASE" in "\n".join(refusals)


def test_a_dist_with_no_javascript_is_refused(packer: Any, tmp_path: Path) -> None:
    """A guard that cannot see must not vouch. Silence is not a pass."""
    (tmp_path / "index.html").write_text("<!doctype html>\n", encoding="utf-8", newline="")
    console, refusals, _warnings = run_gate(packer, tmp_path, "replay")

    assert console["scanned"] == 0
    assert codes(refusals) == {"NO CONSOLE ASSETS"}


def test_the_gz_siblings_are_not_scanned_as_a_second_opinion(packer: Any, tmp_path: Path) -> None:
    """``.js.gz`` siblings sit beside every chunk in the staged tree.

    They are the same bytes under one name (interface I1), and reading a gzip container as
    text would either find nothing or find a fragment. ``scanned`` counts ``*.js`` only.
    """
    root = write_dist(tmp_path)
    gz_header = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff"
    (root / "assets" / "index-Synth0.js.gz").write_bytes(gz_header)
    console, _refusals, _warnings = run_gate(packer, root, "replay")

    assert console["scanned"] == 1


# --------------------------------------------------------------------------------------
# The declaration is REQUIRED, and the gate is reachable from the command line
# --------------------------------------------------------------------------------------


def preflight_argv(dist: Path) -> list[str]:
    """The preflight arguments both wrappers pass, minus the transport."""
    return [
        "--mode",
        "preflight",
        "--source-pkg",
        str(SOURCE_PKG),
        "--dist",
        str(dist),
        "--bundle",
        str(EVIDENCE_BUNDLE),
    ]


def run_packer(packer_path: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(packer_path), *argv],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO_ROOT),
    )


def test_the_declaration_is_required_and_the_refusal_explains_itself(
    packer_path: Path, tmp_path: Path
) -> None:
    """No default. A default would be the program guessing what the operator meant.

    The guess that shipped a REPLAY console to a live origin was exactly that, so the flag
    has to be written down. The message is checked as well as the exit code: an operator who
    hits this needs to learn what the three words mean, not that an argument is missing.
    """
    result = run_packer(packer_path, preflight_argv(write_dist(tmp_path)))

    assert result.returncode == 1
    assert "--console-transport is REQUIRED" in result.stderr
    for word in ("live", "replay", "both"):
        assert f"  {word}" in result.stderr


def test_a_transport_that_is_not_one_of_the_three_is_rejected(
    packer_path: Path, tmp_path: Path
) -> None:
    """``choices`` catches a typo before anything is read off disk."""
    argv = [*preflight_argv(write_dist(tmp_path)), "--console-transport", "livee"]
    result = run_packer(packer_path, argv)

    assert result.returncode == 2
    assert "--console-transport" in result.stderr


def test_preflight_refuses_the_deployed_literals_under_live(
    packer_path: Path, tmp_path: Path
) -> None:
    """END TO END, through ``main()``: the gate is wired, not merely correct.

    A rule that is right and unreachable is precisely the defect this file exists about, so
    the falsification is repeated here as a program: real handler package, real evidence
    bundle, synthetic ``dist/`` carrying the three literals the live URL serves.
    """
    argv = [*preflight_argv(write_dist(tmp_path)), "--console-transport", "live"]
    result = run_packer(packer_path, argv)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED [CONSOLE TRANSPORT]" in result.stderr
    assert "REFUSED [CONSOLE BUILD ID]" in result.stderr


def test_preflight_accepts_the_same_dist_under_replay(packer_path: Path, tmp_path: Path) -> None:
    """And the honest declaration passes, with the build id as an advisory."""
    argv = [*preflight_argv(write_dist(tmp_path)), "--console-transport", "replay"]
    result = run_packer(packer_path, argv)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "preflight ok" in result.stdout
    assert "--console-transport replay" in result.stdout
    assert "WARNING" in result.stdout


def test_preflight_runs_before_pip_touches_the_network(packer_path: Path) -> None:
    """The gate is in ``preflight``, which both wrappers run before the wheelhouse step.

    Discovering the wrong transport after a 7 MB download and a 200-file install wastes a
    minute the build did not have to spend; discovering it after the upload wastes the demo.
    """
    body = packer_path.read_text(encoding="utf-8")
    preflight_at = body.index("def preflight(args):")
    gate_at = body.index("console_gate(probe_console(args.dist)")
    build_at = body.index("def build(args):")
    assert preflight_at < gate_at < build_at


# --------------------------------------------------------------------------------------
# Both wrappers, and both deployers, in step
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "flag", "to_preflight", "to_build"),
    [
        (
            BUILD_SH,
            "--console-transport",
            '--console-transport "$CONSOLE_TRANSPORT"',
            '--console-transport "$CONSOLE_TRANSPORT"',
        ),
        (
            BUILD_PS1,
            "-ConsoleTransport",
            "--console-transport $ConsoleTransport",
            "'--console-transport', $ConsoleTransport",
        ),
    ],
)
def test_both_builders_take_the_flag_and_forward_it_to_both_packer_modes(
    path: Path, flag: str, to_preflight: str, to_build: str
) -> None:
    """A wrapper that accepts the declaration and drops it is a guard with no input.

    Both modes, not one. ``preflight`` is where the refusal costs nothing — it runs before
    pip touches the network — and ``build`` is where the artefact that would be uploaded is
    actually judged. A wrapper that armed one and not the other would refuse late or not at
    all depending on which half an operator reached.
    """
    text = path.read_text(encoding="utf-8")
    assert flag in text
    assert to_preflight in text
    assert to_build in text
    # The forwarding must appear at least twice: once per packer invocation. A single
    # occurrence would mean one mode is being run without a declaration.
    assert text.count("--console-transport") >= 2


def test_the_shell_builder_refuses_a_missing_declaration_before_it_does_any_work() -> None:
    """Validated in the wrapper as well as the packer, so a typo costs no pip run."""
    text = BUILD_SH.read_text(encoding="utf-8")
    validate_at = text.index("--console-transport is REQUIRED")
    pip_at = text.index("pip download --dest")
    assert validate_at < pip_at


@pytest.mark.parametrize(
    ("path", "needles"),
    [
        (DEPLOY_SH, ("--console-transport live", "-ConsoleTransport live")),
        (DEPLOY_PS1, ("'--console-transport', 'live'", "'-ConsoleTransport', 'live'")),
    ],
)
def test_both_deployers_declare_live_for_both_builder_spellings(
    path: Path, needles: tuple[str, ...]
) -> None:
    """This origin has a live kernel behind it, so ``live`` is the only honest declaration.

    Each deployer can reach either builder — ``deploy.sh`` falls back to ``build_lambda.ps1``
    and ``deploy.ps1`` falls back to ``build_lambda.sh`` — so BOTH spellings must carry the
    flag. A branch that forwards it and a sibling branch that does not is a guard that
    depends on which shell an operator happened to have.
    """
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        assert needle in text


@pytest.mark.parametrize("path", [BUILD_SH, BUILD_PS1, DEPLOY_SH, DEPLOY_PS1])
def test_no_continue_on_error_survives_in_these_scripts(path: Path) -> None:
    """``continue-on-error`` is banned outright. A refusal, never a swallowed one."""
    assert "continue-on-error" not in path.read_text(encoding="utf-8")


def test_neither_deployer_swallows_the_builders_exit_status() -> None:
    """The other half of the same rule, asserted where it means something.

    A bare ``|| true`` scan over these four files is NOT this rule: ``build_lambda.sh``
    resolves its interpreter with ``$(command -v python3 || command -v python || true)`` and
    then refuses on an empty result with ``|| die``, and ``deploy.sh`` names ``|| true`` in a
    comment explaining why the health probe does not use it. Both are correct, both predate
    this guard, and a test that had to special-case them would be a test about its own
    exclusion list. What matters is that the line which INVOKES the builder cannot succeed
    when the builder refused, so that is what is asserted, on the lines this worker wrote.
    Comment lines are skipped: the paragraph above each invocation names the flag too, and a
    scan that could not tell an explanation from an instruction would be asserting prose.
    """
    invocations = 0
    for line in DEPLOY_SH.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "--console-transport live" in line or "-ConsoleTransport live" in line:
            invocations += 1
            assert "|| die" in line, line
    for line in DEPLOY_PS1.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        if "'--console-transport', 'live'" in line or "'-ConsoleTransport', 'live'" in line:
            invocations += 1
            assert "-OnFail" in line, line
    # Two spellings per deployer: each can reach either builder. A scan that found none
    # would pass vacuously, which is the failure mode this counter exists to refuse.
    assert invocations == 4
