# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The four commands in QUICKSTART.md must exist, be reachable, and need no credential.

A judge's first five minutes are: clone, read, run one command, look at CI. On
2026-08-10 the first command could not work. `uv` was not installed on the machine this
repository is built on, `just` was not installed either, and **every recipe in the
justfile began with `uv run`** — so a stranger's first command answered
`uv: command not found` from a file whose own header promised it ran on a stranger's
laptop. Nothing in the tree noticed, because nothing in the tree read the justfile.

This module reads it. It asserts, without a cluster, without a network and without an
installed workspace:

* every recipe QUICKSTART.md names is a recipe the justfile actually defines;
* the recipes that must run BEFORE `just setup` — `doctor`, `pin`, `up` — do not
  mention `uv`, which is the specific defect above expressed as a test;
* every `uv run` elsewhere is SCOPED, as the justfile's own preamble requires;
* `test` means the hermetic suite (`--crdb=none`) and `test-cluster` means the shared
  one (`--crdb=reuse`) — the difference between a suite and thirteen CockroachDB
  containers taking the machine down;
* compose.yaml still carries the `trappoint:crdb-image-pin` marker, still with the
  `image:` key on the very next line, and **trappoint_testkit.image reads the same
  value** the doctor and the raw `grep -A1` in five workflows read;
* no recipe references a credential, and `.env.example` contains no filled-in secret.

`just` itself is deliberately NOT required to run this file. It was not installed here,
and a release test that can only run where the tool is installed cannot assert anything
about the machine where it is not.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

#: The recipes QUICKSTART.md is allowed to name, and the six the brief requires exist.
REQUIRED_RECIPES = ("doctor", "setup", "prove", "test", "test-cluster", "console")

#: Recipes that run before `just setup` has installed anything. Measured: `up` used to
#: call `just image`, which is `uv run …`, so `just up` could not run on a fresh clone.
PRE_SETUP_RECIPES = ("doctor", "pin", "up")

#: The marker comment that carries the one version constant. Byte-identical to
#: ``trappoint_testkit.image.IMAGE_PIN_MARKER`` and to ``scripts/qa/doctor.py``'s copy.
IMAGE_PIN_MARKER = "trappoint:crdb-image-pin"

#: Substrings that mean "this recipe needs something a stranger does not have". Chosen
#: to be specific: `--profile trappoint-ref` and `--profile mainline` are conformance
#: profiles, so the bare word `profile` is deliberately NOT here, while `aws` is.
CREDENTIAL_MARKERS = (
    "aws",
    "bedrock",
    "secret",
    "password",
    "api_key",
    "api-key",
    "apikey",
    "token",
    "credential",
    "cockroachlabs.cloud",
    "sslmode=verify-full",
    "cc_service_account",
    ".env",
)

#: Keys in `.env.example` that may never carry a value. The file is committed; `.env`
#: is not. A filled-in example is a leaked secret with a friendly filename.
SECRETISH_KEYS = re.compile(
    r"^(?!#)\s*(?P<key>[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|DSN|ACCOUNT)[A-Z0-9_]*)\s*="
    r"\s*(?P<value>.*)$"
)

#: A recipe header: `name:`, `name arg:`, `name: dep dep`. Never `NAME := value`
#: (the `(?!=)` after the colon) and never `set shell := [...]` (same reason).
_RECIPE_HEADER = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?P<params>[^:=\n]*):(?!=)(?P<deps>[^\n]*)$"
)

#: `just <recipe>` as QUICKSTART.md writes it, in prose or in a fenced block.
_JUST_INVOCATION = re.compile(r"\bjust\s+(?P<name>[a-z][a-z0-9-]*)\b")

#: Words that follow `just` in QUICKSTART.md but are flags or prose, not recipes.
_NOT_RECIPES = frozenset({"list", "the", "a", "an", "is", "as", "run", "runs"})


@dataclass(frozen=True)
class Recipe:
    """One recipe: its name, its dependencies and its body, as written."""

    name: str
    dependencies: tuple[str, ...]
    body: tuple[str, ...]
    doc: str | None

    @property
    def text(self) -> str:
        """The body as one string, for substring questions."""
        return "\n".join(self.body)


def parse_justfile(source: str) -> dict[str, Recipe]:
    """Parse a justfile into ``{name: Recipe}``.

    Deliberately a parser and not a shell-out to ``just --dump``: ``just`` was not
    installed on the machine this repository is built on, which is the entire reason
    this module exists.
    """
    lines = source.splitlines()
    recipes: dict[str, Recipe] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _RECIPE_HEADER.match(line)
        if match is None or line.startswith("#") or line[:1].isspace():
            index += 1
            continue
        name = match.group("name")
        if name == "set":  # `set dotenv-load := false` has no `:=` when it is `:` alone
            index += 1
            continue
        doc = None
        if index > 0 and lines[index - 1].startswith("# "):
            doc = lines[index - 1][2:].strip()
        body: list[str] = []
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if candidate.strip() and not candidate[:1].isspace():
                break
            if candidate.strip():
                body.append(candidate.strip())
            cursor += 1
        recipes[name] = Recipe(
            name=name,
            dependencies=tuple(match.group("deps").split()),
            body=tuple(body),
            doc=doc,
        )
        index = cursor
    return recipes


def reachable_lines(
    recipes: dict[str, Recipe], name: str, _seen: set[str] | None = None
) -> list[tuple[str, str]]:
    """Every line `just <name>` can end up running, as ``(recipe, line)`` pairs.

    Dependencies AND `just <other>` calls inside a body are followed, because the
    original defect hid exactly one hop away: `up` did not mention `uv`, it called
    `just image`, and `image` is `uv run --package trappoint-migrate …`. A test that
    only read the body it was pointed at would have called that recipe clean.
    """
    seen = set() if _seen is None else _seen
    if name in seen or name not in recipes:
        return []
    seen.add(name)
    recipe = recipes[name]
    collected = [(name, line) for line in recipe.body]
    callees = list(recipe.dependencies)
    for line in recipe.body:
        callees.extend(_JUST_INVOCATION.findall(line))
    for callee in callees:
        collected.extend(reachable_lines(recipes, callee, seen))
    return collected


def load_testkit_image_module(repo_root: Path) -> Any:
    """Load ``trappoint_testkit/image.py`` by path — the package __init__ needs psycopg."""
    path = repo_root / "packages" / "trappoint-testkit" / "src" / "trappoint_testkit" / "image.py"
    assert path.is_file(), f"the testkit's pin reader is missing: {path}"
    spec = importlib.util.spec_from_file_location("_release_testkit_image", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── fixtures ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def justfile_text(repo_root: Path) -> str:
    """The justfile as a stranger will read it."""
    path = repo_root / "justfile"
    assert path.is_file(), "there is no justfile; QUICKSTART.md names four `just` commands"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recipes(justfile_text: str) -> dict[str, Recipe]:
    """Every recipe the justfile defines."""
    parsed = parse_justfile(justfile_text)
    assert parsed, "the justfile parsed to zero recipes; the parser or the file is wrong"
    return parsed


@pytest.fixture(scope="module")
def quickstart_text(repo_root: Path) -> str:
    """QUICKSTART.md, which is the contract this module enforces."""
    path = repo_root / "docs" / "release" / "QUICKSTART.md"
    assert path.is_file(), f"{path} is the four commands; it must exist"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose_text(repo_root: Path) -> str:
    """compose.yaml, the single home of the CockroachDB version constant."""
    return (repo_root / "compose.yaml").read_text(encoding="utf-8")


# ── the recipes exist ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", REQUIRED_RECIPES)
def test_required_recipe_exists(recipes: dict[str, Recipe], name: str) -> None:
    """The six recipes the one-command loop is made of."""
    assert name in recipes, (
        f"`just {name}` is named in the release brief but the justfile defines only "
        f"{sorted(recipes)}"
    )


def test_every_recipe_quickstart_names_exists(
    quickstart_text: str, recipes: dict[str, Recipe]
) -> None:
    """QUICKSTART.md may not promise a command that does not exist."""
    named = {
        match.group("name")
        for match in _JUST_INVOCATION.finditer(quickstart_text)
        if match.group("name") not in _NOT_RECIPES
    }
    assert named, "QUICKSTART.md names no `just` command at all"
    missing = sorted(name for name in named if name not in recipes)
    assert not missing, (
        f"QUICKSTART.md tells a stranger to run {missing}, and the justfile has no such "
        f"recipe. Defined: {sorted(recipes)}"
    )


def test_quickstart_names_the_four_commands(quickstart_text: str) -> None:
    """The four, in the order a stranger runs them."""
    for name in ("doctor", "setup", "up", "prove"):
        assert f"just {name}" in quickstart_text, (
            f"QUICKSTART.md does not name `just {name}`; it is one of the four commands"
        )


def test_every_public_recipe_is_documented(recipes: dict[str, Recipe]) -> None:
    """`just --list` prints the comment above each recipe; a blank one teaches nothing."""
    undocumented = sorted(
        name for name, recipe in recipes.items() if not name.startswith("_") and not recipe.doc
    )
    assert not undocumented, (
        f"these recipes would print no description in `just --list`: {undocumented}"
    )


# ── the bootstrap ordering: what must work before uv exists ──────────────────────────


@pytest.mark.parametrize("name", PRE_SETUP_RECIPES)
def test_pre_setup_recipes_do_not_need_uv(recipes: dict[str, Recipe], name: str) -> None:
    """`doctor`, `pin` and `up` run on a machine where `just setup` has not run yet.

    This is the measured defect, expressed as a test: on 2026-08-10 `uv` was not
    installed here, `just up` called `just image` which is `uv run …`, and the first
    command a stranger ran answered `uv: command not found`.

    The whole REACHABLE set is checked, not the recipe's own body. Written the naive
    way this test passed while `up` still called `just image`, because `up`'s own body
    never says `uv` — the defect was one hop away, which is where defects live.
    """
    offending = [
        f"{owner}: {line}"
        for owner, line in reachable_lines(recipes, name)
        if re.search(r"\buv\b", line)
    ]
    assert not offending, (
        f"`just {name}` runs before `just setup` has installed uv, so nothing it can "
        f"reach may mention uv. Offending line(s): {offending}"
    )


def test_setup_installs_uv_when_it_is_absent(recipes: dict[str, Recipe]) -> None:
    """`just setup` is the one recipe allowed to assume uv is missing."""
    body = recipes["setup"].text
    assert "command -v uv" in body, "`just setup` must check whether uv is present at all"
    assert "astral.sh/uv/install" in body, (
        "`just setup` must install uv when it is absent; that is the whole point of it"
    )
    assert "uv sync --all-packages" in body, (
        "`just setup` must install every workspace member, not a subset"
    )


def test_doctor_recipe_runs_the_doctor(recipes: dict[str, Recipe], repo_root: Path) -> None:
    """`just doctor` runs the script this brief's `done_when` names."""
    assert "scripts/qa/doctor.py" in recipes["doctor"].text
    assert (repo_root / "scripts" / "qa" / "doctor.py").is_file()


def test_prove_runs_the_gate_refusal_proof(recipes: dict[str, Recipe], repo_root: Path) -> None:
    """`just prove` runs W3's proof, and nothing stands between a judge and it."""
    body = recipes["prove"].text
    assert "scripts/proof/gate_refusal.py" in body, (
        "`just prove` must run the gate-refusal proof; it is the product's central claim"
    )
    assert (repo_root / "scripts" / "proof" / "gate_refusal.py").is_file()


# ── scoping and the cluster modes ────────────────────────────────────────────────────


def test_every_uv_run_is_scoped(recipes: dict[str, Recipe]) -> None:
    """The justfile's own preamble: a bare `uv run` builds every workspace member."""
    unscoped: list[str] = []
    for recipe in recipes.values():
        for line in recipe.body:
            if not re.search(r"\buv run\b", line):
                continue
            if not re.search(r"--package\b|--only-group\b|--all-packages\b", line):
                unscoped.append(f"{recipe.name}: {line}")
    assert not unscoped, (
        "every `uv run` must carry --package, --only-group or --all-packages; a bare "
        f"`uv run` builds the whole graph. Unscoped: {unscoped}"
    )


def test_test_is_the_hermetic_suite(recipes: dict[str, Recipe]) -> None:
    """`just test` must mean the hermetic suite, not one package's tests.

    `--crdb=none` starts no container and skips every cluster test with the reason its
    own fixture writes. Without it, a full run started THIRTEEN single-node CockroachDB
    containers concurrently, all thirteen exited 7 or 8, and they took the real node
    down with them.
    """
    body = recipes["test"].text
    assert "pytest" in body, "`just test` must run pytest"
    assert "--crdb=none" in body, (
        "`just test` must be hermetic: `--crdb=none`. Anything else can start containers."
    )


def test_test_cluster_reuses_the_one_container(recipes: dict[str, Recipe]) -> None:
    """`just test-cluster` uses the node `just up` started and never starts a second."""
    recipe = recipes["test-cluster"]
    assert "--crdb=reuse" in recipe.text, (
        "`just test-cluster` must be `--crdb=reuse`: reuse the ONE shared container, "
        "never start another"
    )
    assert "up" in recipe.dependencies, (
        "`just test-cluster` must depend on `up`, or `--crdb=reuse` has nothing to reuse"
    )


def test_console_runs_the_console_gate(recipes: dict[str, Recipe], repo_root: Path) -> None:
    """`just console` is the 278 TypeScript files' own gate, which had no CI at all."""
    body = recipes["console"].text
    assert "pnpm run ci" in body, "`just console` must run the console's own `ci` script"
    package_json = repo_root / "verticals" / "mainline" / "apps" / "console" / "package.json"
    assert package_json.is_file()
    assert '"ci"' in package_json.read_text(encoding="utf-8"), (
        "the console's package.json must define the `ci` script `just console` runs"
    )


# ── no recipe needs a credential ─────────────────────────────────────────────────────


def test_no_recipe_references_a_credential(recipes: dict[str, Recipe]) -> None:
    """PL-1: every proof runs on a machine that has never held one of our credentials."""
    offences: list[str] = []
    for recipe in recipes.values():
        for line in recipe.body:
            lowered = line.lower()
            for marker in CREDENTIAL_MARKERS:
                if marker in lowered:
                    offences.append(f"{recipe.name}: {marker!r} in {line!r}")
    assert not offences, (
        "a recipe in the justfile reaches for something a stranger does not have. "
        f"PL-1 forbids it: {offences}"
    )


def test_local_dsn_carries_no_password(justfile_text: str) -> None:
    """The local node is `--insecure` and loopback-bound; a password here would be a lie."""
    for match in re.finditer(r"postgresql://[^\s'\"]+", justfile_text):
        dsn = match.group(0)
        authority = dsn.split("//", 1)[1].split("/", 1)[0]
        assert ":" not in authority.split("@", 1)[0], (
            f"{dsn} carries a password. The local cluster is --insecure and bound to "
            "loopback; nothing real belongs in it."
        )


# ── the one version constant ─────────────────────────────────────────────────────────


def test_compose_carries_the_pin_marker(compose_text: str) -> None:
    """The marker exists, exactly once as a marker, with `image:` on the very next line.

    Adjacency is not cosmetic. Five workflows parse this with
    `grep -A1 'trappoint:crdb-image-pin' compose.yaml | tail -n1`, which reads the ONE
    line after the marker and nothing else.
    """
    lines = compose_text.splitlines()
    marker_indices = [
        index
        for index, line in enumerate(lines)
        if IMAGE_PIN_MARKER in line and line.strip().startswith("#")
    ]
    # The header prose quotes the marker inside a sentence; the marker proper is the
    # LAST such comment line, which is exactly what `tail -n1` selects.
    assert marker_indices, f"compose.yaml carries no `{IMAGE_PIN_MARKER}` comment at all"
    marker = marker_indices[-1]
    assert marker + 1 < len(lines), "the marker is the last line of compose.yaml"
    following = lines[marker + 1]
    assert re.match(r"^\s*image:\s*\S+\s*$", following), (
        f"the line after the `{IMAGE_PIN_MARKER}` marker must be a bare `image:` key "
        f"with one token on it; it is {following!r}"
    )


def test_testkit_and_doctor_read_the_same_pin(repo_root: Path) -> None:
    """What trappoint_testkit.image parses is what the doctor prints. One constant."""
    testkit = load_testkit_image_module(repo_root)
    through_testkit = testkit.read_pin(repo_root / "compose.yaml")
    assert through_testkit.startswith("cockroachdb/cockroach:"), through_testkit
    assert ":latest" not in through_testkit, (
        f"the pin is a FLOATING tag ({through_testkit}); a floating tag is exactly the "
        "dev/CI skew the schema fingerprint exists to catch"
    )

    completed = subprocess.run(  # fixed argv, no shell
        [sys.executable, str(repo_root / "scripts" / "qa" / "doctor.py"), "--print-pin"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=repo_root,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == through_testkit, (
        f"the doctor prints {completed.stdout.strip()!r} and trappoint_testkit.image "
        f"reads {through_testkit!r}; there is supposed to be one version constant"
    )


def test_grep_a1_parser_still_works(repo_root: Path) -> None:
    """The `grep -A1 … | tail -n1 | sed` parser five workflows use, reproduced exactly."""
    testkit = load_testkit_image_module(repo_root)
    expected = testkit.read_pin(repo_root / "compose.yaml")
    lines = (repo_root / "compose.yaml").read_text(encoding="utf-8").splitlines()
    grepped: list[str] = []
    for index, line in enumerate(lines):
        if IMAGE_PIN_MARKER in line:
            grepped.append(line)
            if index + 1 < len(lines):
                grepped.append(lines[index + 1])
    assert grepped, "nothing to grep"
    tail = grepped[-1]
    assert re.sub(r".*image: *", "", tail) == expected, (
        "`grep -A1 … | tail -n1 | sed 's/.*image: *//'` — the parser in db.yml, "
        f"db-schema.yml, schema.yml, custody-chain.yml and mutation-ratchet.yml — reads "
        f"{tail!r}, not {expected!r}"
    )


def test_compose_aligns_gc_ttl_with_cloud(compose_text: str) -> None:
    """Local defaults to 14400; Cloud enforces 4500. Local is the MORE permissive one."""
    assert "gc.ttlseconds = 4500" in compose_text, (
        "compose.yaml must carry the Cloud alignment (gc.ttlseconds = 4500); local's "
        "14400 default is four hours of MVCC history against Cloud's seventy-five "
        "minutes, and the difference hides time-travel assumptions until the nightly run"
    )
    assert "crdb-align" in compose_text, "the alignment must be a named, runnable step"


def test_compose_does_not_bind_insecure_to_a_named_host(compose_text: str) -> None:
    """Measured against the pinned image: `--listen-addr=0.0.0.0:26257` exits 1.

        error: hostname of listen_addr must be "127.0.0.1" or "localhost"

    An EMPTY hostname (`:26257`) is accepted and still binds every interface, which is
    what the published port mapping needs. This file could not start a node before that
    change, so the assertion is not hypothetical.
    """
    # Comment lines are excluded on purpose: the block above the `command:` key quotes
    # the broken form verbatim, and the first run of this test failed on that quotation.
    # What is asserted is what the container is actually given.
    arguments = [line for line in compose_text.splitlines() if not line.lstrip().startswith("#")]
    for flag in ("--listen-addr", "--http-addr"):
        offending = [line for line in arguments if re.search(rf"{re.escape(flag)}=(?!:)\S", line)]
        assert not offending, (
            f"{flag} must have an empty hostname under --insecure; CockroachDB refuses "
            f"a named non-loopback bind and the container exits 1. Offending: {offending}"
        )


# ── .env.example ─────────────────────────────────────────────────────────────────────


def test_env_example_exists_and_is_empty_of_secrets(repo_root: Path) -> None:
    """`.env` is gitignored; `.env.example` is committed. A filled-in example is a leak."""
    path = repo_root / ".env.example"
    assert path.is_file(), ".env.example is what a stranger copies; it must exist"
    filled: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SECRETISH_KEYS.match(line)
        if match is None:
            continue
        value = match.group("value").strip()
        if value and not value.startswith("postgresql://root@127.0.0.1"):
            filled.append(line)
    assert not filled, (
        f".env.example assigns a value to a credential-shaped key: {filled}. The example "
        "is committed; only the local --insecure loopback DSN may carry one."
    )


def test_env_example_does_not_leak_the_real_env(repo_root: Path) -> None:
    """If a developer's `.env` exists here, none of its values may appear in the example."""
    real = repo_root / ".env"
    if not real.is_file():
        pytest.skip("no local .env on this machine; nothing to leak")
    example = (repo_root / ".env.example").read_text(encoding="utf-8")
    leaked: list[str] = []
    for line in real.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Short values are words like `mainline-dev`; the risk is keys and DSNs.
        if len(value) >= 24 and value in example:
            leaked.append(key.strip())
    assert not leaked, f".env.example carries the real value of {leaked}"


def test_env_example_documents_every_dsn_spelling(repo_root: Path) -> None:
    """All four spellings the fixtures honour, or a reader will set the wrong one."""
    text = (repo_root / ".env.example").read_text(encoding="utf-8")
    for name in ("MAINLINE_TEST_DSN", "TRAPPOINT_DSN", "COCKROACH_URL", "CRDB_URL"):
        assert name in text, f"{name} is honoured by every cluster fixture and is undocumented"


# ── the doctor itself ────────────────────────────────────────────────────────────────


def test_doctor_reports_a_table_and_an_honest_exit_code(repo_root: Path) -> None:
    """Run it. It must print the table, and its exit code must agree with the table.

    Not asserted: that this machine is READY. It very likely is not — that is the point
    of the script, and a test that demanded a green preflight would fail on exactly the
    machine the doctor was written for.
    """
    completed = subprocess.run(  # fixed argv, no shell
        [sys.executable, str(repo_root / "scripts" / "qa" / "doctor.py")],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=repo_root,
    )
    out = completed.stdout
    assert "STATUS" in out and "CHECK" in out and "OBSERVED" in out, out[:800]
    assert completed.returncode in (0, 1), (
        f"the doctor exited {completed.returncode}; 0 is ready, 1 is not ready, and "
        f"anything else means it could not run: {completed.stderr[:800]}"
    )
    has_blocking_fail = "NOT READY" in out
    assert has_blocking_fail == (completed.returncode == 1), (
        "the exit code and the table disagree, which makes both untrustworthy:\n" + out[:2000]
    )


def test_doctor_json_is_machine_readable(repo_root: Path) -> None:
    """`--json` is what a workflow reads; it must parse and name every check."""
    import json

    completed = subprocess.run(  # fixed argv, no shell
        [sys.executable, str(repo_root / "scripts" / "qa" / "doctor.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=repo_root,
    )
    assert completed.returncode in (0, 1), completed.stderr[:800]
    report = json.loads(completed.stdout)
    assert report["schema"] == "mainline.qa.doctor/1"
    keys = {check["key"] for check in report["checks"]}
    for expected in ("uv", "just", "docker-engine", "crdb-pin", "clock", "gc-ttl"):
        assert expected in keys, f"the doctor does not check {expected!r}; it must"
    assert report["ready"] == (not report["blocking"])
