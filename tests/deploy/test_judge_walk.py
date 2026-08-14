# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Every refusal in ``scripts/deploy/judge_walk.py``, demonstrated FIRING.

WHY THIS FILE EXISTS
====================
``docs/leads/cloud-hardening-final.md`` ruling **R8**, restated by
``docs/leads/package-and-verify-plan.md``: *a verifier that has never failed has never
discriminated.* The walk cannot be proven against the deployment it was written for, because
that deployment is in exactly one state — REPLAY console, no SSM parameter — and a program
that has only ever seen one state has only ever been observed agreeing with it.

So it is proven the other way, and the proof has two halves for every property:

  * the **REAL** program, fed a fault, refuses; and
  * a **MUTANT** of the program with that one check removed, fed the same fault, does **not**.

The second half is the one that matters. An assertion that only ever runs against the real
program passes just as happily against a program in which the check has rotted into a no-op.
That is the pattern ``tests/deploy/test_post_apply_verify.py`` established and this file is
held to it.

TWO OF THE PAIRINGS RUN THE OTHER WAY ROUND, ON PURPOSE
=======================================================
``dsn_unset`` and ``retry_40001`` are *permissions*, not refusals: the property is that the
walk does **not** go red for them. Their demonstrations are therefore inverted — the real
program answers ``REFUSED`` and exits 0, and the mutant with the named-reason branch removed
answers ``FAILED`` and exits 1 on the same input. Same discipline, opposite sign: if the
branch rots, the control turns red rather than passing quietly.

WHAT IS SYNTHETIC AND WHAT IS NOT
=================================
The HTTP answers and the file reads are synthetic; the **program is the committed one**, read
off disk every time (:func:`_source`). Nothing here monkeypatches an internal — the faults
arrive through :class:`judge_walk.Probes`, the same two collaborators production uses, and
every reading taken through them is stamped ``source="synthetic"`` so a document produced
under fault injection can never be mistaken for a measurement of any deployment.

WHAT NONE OF THESE TESTS DO
===========================
No socket is opened. No AWS call is made. No Terraform verb runs. Nothing is deployed,
nothing is applied, and the SSM parameter is neither read nor written. Every ``main()`` here
is given ``--out`` under ``tmp_path``, so ``evidence/deploy/judge-walk.json`` — the record of
the LIVE walk — is never written by a synthetic run.
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
from types import ModuleType
from typing import Any, Final

import pytest

REPO_ROOT: Final = pathlib.Path(__file__).resolve().parents[2]
PROGRAM: Final = REPO_ROOT / "scripts" / "deploy" / "judge_walk.py"

#: The synthetic origin. ``.invalid`` is reserved by RFC 2606 and resolves nowhere, so a test
#: that accidentally reached the real network would fail rather than quietly succeed against
#: somebody's server.
BASE: Final = "https://demo.invalid"

#: The permit the demo world seeds. Carried here because its last group is twelve digits,
#: which is what caught the masker out on the first live run of the walk.
SEEDED_PERMIT: Final = "dec0de00-0006-4000-8000-000000000001"


# ══════════════════════════════════════════════════════════════════════════════════════
#  loading the real program, and mutants of it
# ══════════════════════════════════════════════════════════════════════════════════════


def _source(path: pathlib.Path = PROGRAM) -> str:
    assert path.is_file(), (
        f"{path} does not exist. This file is the control set for that program; if the "
        "program moved, these controls move with it in the same commit. A control set that "
        "cannot find its subject must FAIL, never skip."
    )
    return path.read_text(encoding="utf-8")


def _load(source: str, name: str, path: pathlib.Path = PROGRAM) -> ModuleType:
    """Execute ``source`` as a fresh module.

    Registered in ``sys.modules`` for the duration of the exec and removed afterwards:
    ``dataclasses`` resolves the defining module out of ``sys.modules`` while it processes a
    class, and this program is full of dataclasses. Measured while writing this file — an
    unregistered module raises ``AttributeError: 'NoneType' object has no attribute
    '__dict__'`` at ``@dataclass``. Leaving it registered afterwards would let one scenario's
    mutant leak into the next, which is the failure mode that makes a mutation suite pass for
    the wrong reason.
    """
    module = ModuleType(name)
    module.__file__ = str(path)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def real() -> ModuleType:
    """The program exactly as it is committed."""
    return _load(_source(), "judge_walk_real")


def mutate(anchor: str, replacement: str, name: str) -> ModuleType:
    """The program with one named property removed.

    The anchor must appear EXACTLY ONCE. A mutation that fails to apply produces a mutant
    identical to the original, and a negative control against an unmutated program passes for
    the wrong reason — which is the failure mode this whole file exists to refuse.
    """
    source = _source()
    found = source.count(anchor)
    assert found == 1, (
        f"the mutation anchor for {name!r} appears {found} time(s) in {PROGRAM.name}, "
        "expected exactly 1.\n"
        "\n"
        "THIS IS NOT A FAILURE OF THE PROGRAM. It means the program was reshaped and this "
        "control's demonstration no longer applies to it. Re-anchor the mutation against the "
        "new text IN THE SAME COMMIT. Do not delete the demonstration: an assertion with no "
        "demonstration behind it cannot tell you whether the property it names is still "
        "enforced.\n"
        "\n"
        f"anchor sought:\n{anchor}"
    )
    return _load(source.replace(anchor, replacement), name)


# ══════════════════════════════════════════════════════════════════════════════════════
#  the synthetics — every one of them stamped, none of them a mode of the program
# ══════════════════════════════════════════════════════════════════════════════════════


class FakeHttp:
    """Answers by (method, path). An unscripted request is an error, never a 200.

    Defaulting an unscripted request to success is how a fault-injection harness comes to
    prove the wrong thing: the scenario forgets to script a call, the program takes a path
    nobody meant to exercise, and the control passes.
    """

    def __init__(self, module: ModuleType, script: dict[tuple[str, str], Any]) -> None:
        self._module = module
        self._script = script
        self.calls: list[tuple[str, str]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,  # noqa: ARG002 - interface fidelity
        headers: dict[str, str] | None = None,  # noqa: ARG002 - interface fidelity
    ) -> Any:
        assert url.startswith(BASE), (
            f"the program asked for {url!r}, which is not under the base URL it was given. A "
            "walk that reached another origin would be walking somebody else's deployment."
        )
        path = url[len(BASE) :] or "/"
        self.calls.append((method, path))
        for key in (path, path.split("?", 1)[0]):
            scripted = self._script.get((method, key))
            if scripted is None:
                continue
            answer = scripted() if callable(scripted) else scripted
            if isinstance(answer, Exception):
                raise answer
            return answer
        raise self._module.Unavailable(
            f"the control did not script {method} {path}; refusing to invent an answer."
        )


class FakeFiles:
    """A read-only filesystem of exactly what a scenario declares. Writes nothing, ever."""

    def __init__(self, module: ModuleType, tree: dict[pathlib.Path, bytes] | None = None) -> None:
        self._module = module
        self._tree = dict(tree or {})

    def exists(self, path: pathlib.Path) -> bool:
        return pathlib.Path(path) in self._tree

    def read_bytes(self, path: pathlib.Path) -> bytes:
        try:
            return self._tree[pathlib.Path(path)]
        except KeyError as exc:
            raise self._module.Unavailable(f"{path} is not in this control's tree.") from exc


def probes(module: ModuleType, http: FakeHttp, files: FakeFiles | None = None) -> Any:
    return module.Probes(http=http, files=files or FakeFiles(module), source="synthetic")


# ══════════════════════════════════════════════════════════════════════════════════════
#  building a synthetic deployment
# ══════════════════════════════════════════════════════════════════════════════════════


def answer(
    module: ModuleType, status: int, body: Any, headers: dict[str, str] | None = None
) -> Any:
    payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    return module.HttpAnswer(
        status=status,
        headers={"content-type": "application/json", **(headers or {})},
        body=payload,
        elapsed_ms=1.0,
    )


def html(
    module: ModuleType,
    *,
    doctype: bool = True,
    root: bool = True,
    assets: bool = True,
    status: int = 200,
) -> Any:
    parts = ["<!doctype html>" if doctype else "<html>"]
    if assets:
        parts.append('<link rel="stylesheet" href="./assets/index-bbb.css" />')
        parts.append('<script type="module" src="./assets/index-aaa.js"></script>')
    if root:
        parts.append('<div id="root"></div>')
    parts.append("</html>")
    return module.HttpAnswer(
        status=status,
        headers={"content-type": "text/html; charset=utf-8"},
        body="\n".join(parts).encode("utf-8"),
        elapsed_ms=1.0,
    )


def chunk(
    module: ModuleType,
    *,
    api_base: str = "/",
    bundle_url: str = "./bundle/",
    vkey: str = "",
    status: int = 200,
) -> Any:
    """An entry chunk carrying exactly the literals vite would inline.

    ``VITE_MAINLINE_LOG_VKEY`` is always present, and its being always present is FAULT 1b:
    ``build_lambda``'s old probe keyed on the variable NAME, so ``configured`` was never empty
    and the warning branch was unreachable. The walk keys on the trimmed VALUE.
    """
    text = "".join(
        [
            "const e={VITE_MAINLINE_API_BASE:",
            json.dumps(api_base),
            ",VITE_MAINLINE_BUNDLE_URL:",
            json.dumps(bundle_url),
            ",VITE_MAINLINE_LOG_VKEY:",
            json.dumps(vkey),
            ',MODE:"demo",DEV:!1};',
            'const b={buildId:"w4-control"};const h={buildId:"unknown"};export{e,b,h};',
        ]
    )
    return module.HttpAnswer(
        status=status,
        headers={"content-type": "text/javascript; charset=utf-8"},
        body=text.encode("utf-8"),
        elapsed_ms=1.0,
    )


def frame(
    method: str,
    path: str,
    status: int,
    *,
    query: list[dict[str, str]] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = path + ("?" + "&".join(f"{q['name']}={q['value']}" for q in query) if query else "")
    return {
        "frame_version": 1,
        "key": f"{method} {key}",
        "request": {
            "method": method,
            "path": path,
            "query": query or [],
            "body_b64": base64.b64encode(json.dumps(body).encode()).decode() if body else None,
        },
        "response": {
            "status": status,
            "headers": [{"name": "content-type", "value": "application/json"}],
        },
        "captured_at": "2026-08-10T04:04:53.057Z",
    }


DEFAULT_FRAMES: Final = (
    frame("GET", "/v1/audit", 200),
    frame("GET", f"/v1/permits/{SEEDED_PERMIT}", 200),
    frame(
        "POST",
        f"/v1/permits/{SEEDED_PERMIT}/merge",
        409,
        body={"subject_kind": "permit", "subject_id": SEEDED_PERMIT, "expected_gate_epoch": 1},
    ),
)


def frame_name(index: int) -> str:
    return f"frames/F{index:02d}.json"


def manifest(frames: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "bundle_id": "demo-cloud",
        "captured_at": "2026-08-10T04:04:53.057Z",
        "files": [
            {"path": frame_name(i), "sha256": "0" * 64, "bytes": 1, "key": f["key"]}
            for i, f in enumerate(frames)
        ]
        + [{"path": "sql/cluster.sql", "sha256": "1" * 64, "bytes": 1}],
    }


ENVELOPE: Final = {
    "envelope_version": 1,
    "resource": "audit",
    "schema_id": "https://console.mainline.trappoint.org/contracts/1.0/audit.schema.json",
    "data": {"rows": []},
}

DSN_UNSET_ERROR: Final = {
    "error": {
        "kind": "dsn_unset",
        "status": 503,
        "detail": (
            "SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1 answered "
            'HTTP 400: {"__type":"ParameterNotFound"}'
        ),
    }
}

DSN_UNSET_HEALTH: Final = {
    "ok": False,
    "reason": "dsn_unset",
    "detail": DSN_UNSET_ERROR["error"]["detail"],
}


def gate_run_payload(
    *,
    verdict: str = "PROVEN",
    outcome: str = "completed",
    sqlstates: tuple[str, str, str, str] = ("00000", "23514", "P0001", "00000"),
    declared: tuple[str, str, str, str] | None = None,
) -> dict[str, Any]:
    names = ("read", "merge", "projection_drift_attack", "admit")
    outcomes = ("read", "refused", "refused", "admitted")
    constraints = (None, "gate_closed_when_issued", "mainline.fn_permit_merge_gate", None)
    declared = declared or sqlstates
    return {
        "envelope_version": 1,
        "resource": "gate_run",
        "schema_id": "https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json",
        "data": {
            "run_id": "dec0de00-0010-4000-8000-000000000001",
            "outcome": outcome,
            "verdict": verdict,
            "failures": [] if verdict == "PROVEN" else ["something did not hold"],
            "persisted": False,
            "beats": [
                {
                    "ordinal": i + 1,
                    "name": names[i],
                    "outcome": outcomes[i],
                    "sqlstate": sqlstates[i],
                    "constraint": constraints[i],
                    "constraint_source": "reported",
                    "matched_expectation": True,
                    "expected": {"outcome": outcomes[i], "sqlstate": declared[i]},
                }
                for i in range(4)
            ],
            "persistence_check": {"self_persisted": False},
        },
    }


def origin(
    module: ModuleType,
    *,
    api_base: str = "/",
    bundle_url: str = "./bundle/",
    frames: tuple[dict[str, Any], ...] = DEFAULT_FRAMES,
    shell: Any | None = None,
    entry: Any | None = None,
    manifest_answer: Any | None = None,
    frame_answers: dict[str, Any] | None = None,
    api: Any | None = None,
    api_overrides: dict[tuple[str, str], Any] | None = None,
    gate_run: Any | None = None,
) -> dict[tuple[str, str], Any]:
    """A whole synthetic deployment, scripted request by request.

    Defaults describe the deployment the WAVE is aiming at: a LIVE console over a kernel that
    still answers ``dsn_unset`` because the SSM parameter is the founder's step.
    """
    script: dict[tuple[str, str], Any] = {
        ("GET", "/"): shell if shell is not None else html(module),
        ("GET", "/assets/index-aaa.js"): entry
        if entry is not None
        else chunk(module, api_base=api_base, bundle_url=bundle_url),
        ("GET", "/v1/health"): api if api is not None else answer(module, 503, DSN_UNSET_HEALTH),
        ("POST", "/v1/demo/gate-run"): gate_run
        if gate_run is not None
        else answer(module, 503, DSN_UNSET_ERROR),
    }
    if manifest_answer is not None or bundle_url:
        script[("GET", "/bundle/manifest.json")] = (
            manifest_answer
            if manifest_answer is not None
            else answer(module, 200, manifest(frames))
        )
    for index, one in enumerate(frames):
        path = f"/bundle/{frame_name(index)}"
        override = (frame_answers or {}).get(frame_name(index))
        script[("GET", path)] = override if override is not None else answer(module, 200, one)
        request = one["request"]
        script.setdefault(
            (request["method"], request["path"]),
            api if api is not None else answer(module, 503, DSN_UNSET_ERROR),
        )
    for key, value in (api_overrides or {}).items():
        script[key] = value
    return script


def walk(
    module: ModuleType, script: dict[tuple[str, str], Any], **kwargs: Any
) -> tuple[Any, dict[str, Any]]:
    """Drive the whole walk over a synthetic origin and return (steps, document)."""
    http = FakeHttp(module, script)
    bundle = probes(module, http, kwargs.pop("files", None))
    steps, context = module.walk(
        bundle,
        BASE,
        kwargs.pop("root", None),
        enumeration=kwargs.pop("enumeration", "auto"),
        allow_replay=kwargs.pop("allow_replay", False),
    )
    assert not kwargs, f"unused kwargs {sorted(kwargs)}"
    document = module.build_document(steps, context, bundle)
    return steps, document


def step(steps: list[Any], step_id: str) -> Any:
    for one in steps:
        if one.id == step_id:
            return one
    raise AssertionError(f"no step {step_id!r} among {[s.id for s in steps]}")


def run_main(
    module: ModuleType,
    script: dict[tuple[str, str], Any],
    tmp_path: pathlib.Path,
    extra: tuple[str, ...] = (),
    files: FakeFiles | None = None,
) -> tuple[int, dict[str, Any]]:
    """``main()`` end to end, always writing under ``tmp_path``.

    ``--out`` is never omitted here. A synthetic run that fell through to the default would
    overwrite ``evidence/deploy/judge-walk.json``, and while the document would still carry
    ``source: synthetic``, a control set that damages the record it is a control for is a
    control set nobody trusts.
    """
    out = tmp_path / "judge-walk.json"
    code = module.main(
        ["--base-url", BASE, "--out", str(out), *extra],
        probes=probes(module, FakeHttp(module, script), files),
    )
    return code, json.loads(out.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════════════════
#  R8 — the walk needs a URL and nothing else
# ══════════════════════════════════════════════════════════════════════════════════════


#: Every module ``judge_walk.py`` is allowed to import. All stdlib, all present in a bare
#: CPython: that is what "runs from a bare checkout with only a URL" means as an assertion
#: rather than a promise. ``post_apply_verify.py`` needs ``terraform output``, an AWS profile
#: and ``subprocess``; this program must need none of them, or the artefact a judge re-runs
#: is one they cannot run at all. Prose ABOUT terraform is fine and this check is on the
#: IMPORT GRAPH, because a grep over prose would forbid the paragraph that explains the rule.
PERMITTED_IMPORTS: Final = frozenset(
    {
        "__future__",
        "argparse",
        "base64",
        "dataclasses",
        "datetime",
        "gzip",
        "json",
        "pathlib",
        "re",
        "ssl",
        "sys",
        "time",
        "typing",
        "urllib",
        "urllib.error",
        "urllib.parse",
        "urllib.request",
    }
)


def test_the_program_reaches_for_no_credential_and_no_cloud() -> None:
    import ast

    tree = ast.parse(_source())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    unexpected = imported - PERMITTED_IMPORTS
    assert not unexpected, (
        f"judge_walk.py imports {sorted(unexpected)}, which is outside the enumerated surface "
        "R8 allows. If the new import is stdlib and genuinely needed, add it to "
        "PERMITTED_IMPORTS in the same commit and say why; if it is boto3, botocore, "
        "subprocess or a third-party package, the walk no longer runs from a bare checkout."
    )
    assert "subprocess" not in imported and "boto3" not in imported


def test_no_shortcut_appears_anywhere_in_the_program_or_this_control() -> None:
    """The tokens are assembled from fragments so this file does not fail its own check."""
    shortcuts = ("continue" + "-on-error", "|" + "| true", "pytest.mark." + "skip", "x" + "fail")
    for path in (PROGRAM, pathlib.Path(__file__)):
        text = path.read_text(encoding="utf-8")
        for shortcut in shortcuts:
            assert shortcut not in text, f"{path.name} carries {shortcut!r}"


# ══════════════════════════════════════════════════════════════════════════════════════
#  S1 — the shell
# ══════════════════════════════════════════════════════════════════════════════════════


def test_root_404_refuses_and_the_mutant_does_not() -> None:
    """The synthetic 404 carries the console's own HTML, so only the STATUS is the fault.

    A 404 whose body was an error page would be refused by the shell-identity check one
    branch further down, and the pairing would prove nothing about the status check. This is
    the isolation discipline every pairing in this file follows.
    """
    module = real()
    script = origin(module, shell=html(module, status=404))
    steps, document = walk(module, script)
    assert step(steps, "shell").outcome == module.FAILED
    assert "404" in step(steps, "shell").why
    assert document["exit_code"] == module.EXIT_FAILED

    mutant = mutate(
        "    if answer.status != 200:\n        return (\n"
        '            Step(\n                "shell",',
        "    if False:  # mutant: the shell status check removed\n"
        '        return (\n            Step(\n                "shell",',
        "judge_walk_no_shell_status",
    )
    steps, _ = walk(mutant, origin(mutant, shell=html(mutant, status=404)))
    assert step(steps, "shell").outcome != mutant.FAILED, (
        "the mutant with the status check removed still refused a 404 on /, so this control "
        "is not demonstrating that check."
    )


def test_a_200_that_is_not_the_console_refuses_and_the_mutant_does_not() -> None:
    module = real()
    script = origin(module, shell=html(module, doctype=False, root=False))
    steps, _ = walk(module, script)
    assert step(steps, "shell").outcome == module.FAILED
    assert "not the console shell" in step(steps, "shell").why

    mutant = mutate(
        '    if not detail["has_doctype"] or not detail["has_root_mount"]:',
        "    if False:  # mutant: the shell-identity check removed",
        "judge_walk_no_shell_identity",
    )
    steps, _ = walk(mutant, origin(mutant, shell=html(mutant, doctype=False, root=False)))
    assert step(steps, "shell").outcome != mutant.FAILED


def test_a_shell_with_no_entry_chunk_refuses_and_the_mutant_does_not() -> None:
    module = real()
    steps, _ = walk(module, origin(module, shell=html(module, assets=False)))
    assert step(steps, "shell").outcome == module.FAILED
    assert "entry chunk" in step(steps, "shell").why

    mutant = mutate(
        "    if not scripts or not styles:",
        "    if False:  # mutant: the asset-reference check removed",
        "judge_walk_no_asset_refs",
    )
    steps, _ = walk(mutant, origin(mutant, shell=html(mutant, assets=False)))
    assert step(steps, "shell").outcome != mutant.FAILED


# ══════════════════════════════════════════════════════════════════════════════════════
#  S2 — the transport, read out of the bytes. FAULT 1.
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_artefact_that_reached_the_founder_refuses_and_the_mutant_does_not() -> None:
    """The measured literals of the artefact serving the live URL on 2026-08-14."""
    module = real()
    steps, document = walk(module, origin(module, api_base="", bundle_url="./bundle/"))
    transport = step(steps, "transport")
    assert transport.outcome == module.FAILED
    assert "READS REPLAY, NOT LIVE" in transport.why
    assert transport.detail["selection"]["initial"] == "replay"
    assert document["context"]["transport_mode"] == "REPLAY"
    assert document["exit_code"] == module.EXIT_FAILED

    mutant = mutate(
        '    if selection["initial"] == "live":',
        '    if selection["initial"] in ("live", "replay"):  # mutant: LIVE no longer required',
        "judge_walk_replay_is_fine",
    )
    steps, _ = walk(mutant, origin(mutant, api_base="", bundle_url="./bundle/"))
    assert step(steps, "transport").outcome != mutant.FAILED


def test_an_artefact_with_no_source_refuses_and_the_mutant_does_not() -> None:
    module = real()
    steps, _ = walk(
        module,
        origin(
            module,
            api_base="",
            bundle_url="",
            manifest_answer=answer(module, 200, manifest(DEFAULT_FRAMES)),
        ),
    )
    transport = step(steps, "transport")
    assert transport.outcome == module.FAILED
    assert "NO SOURCE" in transport.why

    mutant = mutate(
        '    if selection["initial"] == "live":',
        "    if True:  # mutant: any compiled state accepted",
        "judge_walk_any_source",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            api_base="",
            bundle_url="",
            manifest_answer=answer(mutant, 200, manifest(DEFAULT_FRAMES)),
        ),
    )
    assert step(steps, "transport").outcome != mutant.FAILED


def test_whitespace_is_unset_exactly_as_it_is_in_the_browser() -> None:
    """FAULT 1b, isolated: ``trimmed()`` is the whole disagreement.

    ``source-select.ts`` trims, so ``VITE_MAINLINE_API_BASE="   "`` selects nothing. A reader
    that kept the raw string would call this artefact LIVE and put a badge on a console
    talking to no kernel at all.
    """
    module = real()
    steps, _ = walk(module, origin(module, api_base="   "))
    assert step(steps, "transport").outcome == module.FAILED
    assert step(steps, "transport").detail["selection"]["sources"]["live"] is None

    mutant = mutate(
        "    text = value.strip()",
        "    text = value  # mutant: the value is no longer trimmed before the empty test",
        "judge_walk_untrimmed",
    )
    steps, _ = walk(mutant, origin(mutant, api_base="   "))
    assert step(steps, "transport").outcome != mutant.FAILED


def test_an_unreadable_entry_chunk_refuses_and_the_mutant_does_not() -> None:
    """The synthetic 500 carries the LIVE literals ON PURPOSE.

    If the fault were "500 with no literals", the mutant would still refuse — at the LIVE
    check, one branch further down — and the pairing would prove nothing about the status
    check. Serving the right bytes under the wrong status isolates exactly the check under
    demonstration.
    """
    module = real()
    steps, _ = walk(module, origin(module, entry=chunk(module, status=500)))
    assert step(steps, "transport").outcome == module.FAILED
    assert "answered 500" in step(steps, "transport").why

    mutant = mutate(
        '        if answer.status != 200:\n            hint = ""',
        '        if False:  # mutant: the chunk status check removed\n            hint = ""',
        "judge_walk_no_chunk_status",
    )
    steps, _ = walk(mutant, origin(mutant, entry=chunk(mutant, status=500)))
    assert step(steps, "transport").outcome != mutant.FAILED


def test_a_413_names_the_gzip_cause_it_was_measured_with() -> None:
    """Measured 2026-08-14: identity 433,564 B is over the ceiling; gzip is how it is served.

    Same branch as the test above, so no second mutant: this control asserts the SENTENCE,
    because a reader who gets 413 with no explanation re-runs the walk instead of opening the
    package.
    """
    module = real()
    steps, _ = walk(
        module, origin(module, entry=answer(module, 413, {"error": {"kind": "too_large"}}))
    )
    why = step(steps, "transport").why
    assert "413" in why
    assert "accept-encoding: gzip" in why and ".gz sibling" in why


def test_a_live_artefact_satisfies_the_transport_step() -> None:
    module = real()
    steps, document = walk(module, origin(module, api_base="/", bundle_url="./bundle/"))
    transport = step(steps, "transport")
    assert transport.outcome == module.SATISFIED
    assert transport.detail["selection"]["switchable"] is True
    assert document["context"]["transport_mode"] == "LIVE"


def test_every_referenced_chunk_is_scanned_and_the_first_non_empty_value_wins() -> None:
    """A shell may reference more than one chunk, and the packer's rule is transcribed here.

    ``build_lambda.sh``'s ``_classify`` sorts the distinct literal values for a variable and
    takes the first that survives ``trimmed()``. Two readers of one fact must answer the same
    for the same bytes, or the guard that refuses a package and the walk that grades a
    deployment disagree — which is FAULT 1b one level up.
    """
    module = real()
    shell = module.HttpAnswer(
        status=200,
        headers={"content-type": "text/html"},
        body=(
            b"<!doctype html>"
            b'<link rel="stylesheet" href="./assets/index-bbb.css" />'
            b'<script type="module" src="./assets/index-aaa.js"></script>'
            b'<script type="module" src="./assets/index-ccc.js"></script>'
            b'<div id="root"></div>'
        ),
        elapsed_ms=1.0,
    )
    script = origin(module, api_base="", shell=shell)
    script[("GET", "/assets/index-ccc.js")] = chunk(module, api_base="/", bundle_url="")
    steps, document = walk(module, script)
    transport = step(steps, "transport")
    assert transport.outcome == module.SATISFIED
    assert transport.detail["selection"]["sources"]["live"] == "/"
    assert len(transport.detail["scanned"]) == 2
    assert document["context"]["transport_mode"] == "LIVE"


# ══════════════════════════════════════════════════════════════════════════════════════
#  R7 — the REPLAY opt-out is a sentence somebody wrote, not a default
# ══════════════════════════════════════════════════════════════════════════════════════


def test_allow_replay_must_be_typed_and_stamps_the_document(tmp_path: pathlib.Path) -> None:
    module = real()
    script = origin(module, api_base="", bundle_url="./bundle/")

    code, document = run_main(module, script, tmp_path / "bare")
    assert code == module.EXIT_FAILED
    assert document["context"]["allow_replay_declared"] is False

    code, document = run_main(module, script, tmp_path / "typed", extra=("--allow-replay",))
    assert code == module.EXIT_OK
    assert document["context"]["allow_replay_declared"] is True
    transport = next(s for s in document["steps"] if s["id"] == "transport")
    assert transport["outcome"] == module.REFUSED
    assert transport["reason"] == "console_replay_declared"
    assert "READS REPLAY, NOT LIVE" in transport["why"], (
        "the declared-REPLAY refusal must still say the loud sentence; a named reason is a "
        "reason, not a silence."
    )

    mutant = mutate(
        '    if allow_replay and selection["initial"] == "replay":',
        '    if selection["initial"] == "replay":  # mutant: the declaration no longer needed',
        "judge_walk_replay_without_declaring",
    )
    code, document = run_main(
        mutant, origin(mutant, api_base="", bundle_url="./bundle/"), tmp_path / "mutant"
    )
    assert code == mutant.EXIT_OK, (
        "the mutant that no longer requires the declaration still failed, so this control is "
        "not demonstrating that the flag is what makes the difference."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  S3 — health
# ══════════════════════════════════════════════════════════════════════════════════════


def test_health_200_with_ok_false_refuses_and_the_mutant_does_not() -> None:
    module = real()
    steps, _ = walk(
        module, origin(module, api=answer(module, 200, {"ok": False, "reason": "degraded"}))
    )
    assert step(steps, "health").outcome == module.FAILED
    assert "ok=true" in step(steps, "health").why

    mutant = mutate(
        '    if record.get("ok") is not True:',
        "    if False:  # mutant: the ok=true check removed",
        "judge_walk_no_ok_check",
    )
    steps, _ = walk(
        mutant, origin(mutant, api=answer(mutant, 200, {"ok": False, "reason": "degraded"}))
    )
    assert step(steps, "health").outcome != mutant.FAILED


def test_health_dsn_unset_is_a_named_refusal_and_the_mutant_calls_it_a_failure() -> None:
    """INVERTED PAIRING. The property is a permission, so the mutant goes red, not green."""
    module = real()
    steps, _ = walk(module, origin(module))
    health = step(steps, "health")
    assert health.outcome == module.REFUSED
    assert health.reason == "dsn_unset"
    assert "founder's remaining step" in health.why

    mutant = mutate(
        '    if is_dsn_unset(record):\n        return Step(\n            "health",',
        "    if False:  # mutant: the named-reason branch removed\n"
        '        return Step(\n            "health",',
        "judge_walk_health_no_named_reason",
    )
    steps, _ = walk(mutant, origin(mutant))
    assert step(steps, "health").outcome == mutant.FAILED, (
        "with the named-reason branch removed, dsn_unset must land in FAILED. It did not, so "
        "something else is granting the pass and this control is not demonstrating the branch."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
#  S4 — R10, the enumeration the artefact ships
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_walk_drives_every_declared_frame_and_the_mutant_drives_fewer() -> None:
    module = real()
    http = FakeHttp(module, origin(module))
    bundle = probes(module, http)
    steps, context = module.walk(bundle, BASE, None, enumeration="auto", allow_replay=False)
    driven = [s for s in steps if s.id.startswith("frame:")]
    assert len(driven) == len(DEFAULT_FRAMES)
    assert context["frames_driven"] == len(DEFAULT_FRAMES)
    for one in DEFAULT_FRAMES:
        assert (one["request"]["method"], one["request"]["path"]) in http.calls

    mutant = mutate(
        "    for request in requests:\n        steps.append(drive_frame(probes, base, request))",
        "    for request in requests[:1]:  # mutant: the enumeration no longer driven whole\n"
        "        steps.append(drive_frame(probes, base, request))",
        "judge_walk_partial_enumeration",
    )
    steps, _ = walk(mutant, origin(mutant))
    assert len([s for s in steps if s.id.startswith("frame:")]) < len(DEFAULT_FRAMES)


def test_an_unreadable_enumeration_refuses_and_the_mutant_walks_nothing_and_exits_zero(
    tmp_path: pathlib.Path,
) -> None:
    module = real()
    script = origin(module, manifest_answer=answer(module, 404, {"error": {"kind": "not_found"}}))
    code, document = run_main(module, script, tmp_path / "real", files=FakeFiles(module))
    assert code == module.EXIT_FAILED
    enumeration = next(s for s in document["steps"] if s["id"] == "enumeration")
    assert enumeration["outcome"] == module.FAILED
    assert "will not invent a list of endpoints" in enumeration["why"]

    mutant = mutate(
        '                FAILED,\n                "the request enumeration could not be read '
        'from "',
        "                SATISFIED,  # mutant: an unreadable enumeration is fine\n"
        '                "the request enumeration could not be read from "',
        "judge_walk_enumeration_optional",
    )
    code, document = run_main(
        mutant,
        origin(mutant, manifest_answer=answer(mutant, 404, {"error": {"kind": "not_found"}})),
        tmp_path / "mutant",
        files=FakeFiles(mutant),
    )
    assert code == mutant.EXIT_OK
    assert document["context"]["frames_driven"] == 0, (
        "the mutant is supposed to demonstrate a walk that drove NOTHING and still exited 0."
    )


def test_a_declared_frame_that_is_not_served_refuses_and_the_mutant_does_not() -> None:
    """The synthetic 404 carries the frame's real body, so only the STATUS is the fault."""
    module = real()
    missing = {frame_name(1): answer(module, 404, DEFAULT_FRAMES[1])}
    steps, _ = walk(module, origin(module, frame_answers=missing))
    enumeration = step(steps, "enumeration")
    assert enumeration.outcome == module.FAILED
    assert "declared frame that is not served" in enumeration.why

    mutant = mutate(
        "            if frame_answer.status != 200:\n                raise Unavailable(",
        "            if False:  # mutant: a declared frame may 404\n"
        "                raise Unavailable(",
        "judge_walk_frame_may_404",
    )
    steps, _ = walk(
        mutant,
        origin(mutant, frame_answers={frame_name(1): answer(mutant, 404, DEFAULT_FRAMES[1])}),
    )
    assert step(steps, "enumeration").outcome != mutant.FAILED


def test_an_empty_enumeration_refuses_and_the_mutant_exits_zero_having_driven_nothing(
    tmp_path: pathlib.Path,
) -> None:
    module = real()
    script = origin(module, frames=(), manifest_answer=answer(module, 200, manifest(())))
    code, document = run_main(module, script, tmp_path / "real")
    assert code == module.EXIT_FAILED
    assert (
        "declares NO frames"
        in next(s for s in document["steps"] if s["id"] == "enumeration")["why"]
    )

    mutant = mutate(
        "    if not requests:",
        "    if False:  # mutant: an empty enumeration is fine",
        "judge_walk_empty_enumeration",
    )
    code, document = run_main(
        mutant,
        origin(mutant, frames=(), manifest_answer=answer(mutant, 200, manifest(()))),
        tmp_path / "mutant",
    )
    assert code == mutant.EXIT_OK
    assert document["context"]["frames_driven"] == 0


def test_the_repo_fallback_is_named_and_the_mutant_misreports_it(tmp_path: pathlib.Path) -> None:
    """*Say which one it used.* A walk that drove the developer's tree while claiming the
    deployment would be the same defect one level down."""
    module = real()
    root = tmp_path / "checkout"
    directory = root / module.REPO_BUNDLE
    tree = {directory / "manifest.json": json.dumps(manifest(DEFAULT_FRAMES)).encode()}
    for index, one in enumerate(DEFAULT_FRAMES):
        tree[directory / frame_name(index)] = json.dumps(one).encode()

    script = origin(module, manifest_answer=answer(module, 404, {"error": {"kind": "not_found"}}))
    steps, document = walk(module, script, files=FakeFiles(module, tree), root=root)
    enumeration = step(steps, "enumeration")
    assert enumeration.outcome == module.SATISFIED
    assert enumeration.detail["used"] == "repo"
    assert "REPO copy" in enumeration.why
    assert document["context"]["enumeration_used"] == "repo"
    assert enumeration.detail["attempts"][0]["source"] == "origin"

    mutant = mutate(
        '        return frames, {\n            "used": "repo",',
        '        return frames, {\n            "used": "origin",  # mutant: provenance misreported',
        "judge_walk_lies_about_provenance",
    )
    tree_m = {directory / "manifest.json": json.dumps(manifest(DEFAULT_FRAMES)).encode()}
    for index, one in enumerate(DEFAULT_FRAMES):
        tree_m[directory / frame_name(index)] = json.dumps(one).encode()
    _, document = walk(
        mutant,
        origin(mutant, manifest_answer=answer(mutant, 404, {"error": {"kind": "x"}})),
        files=FakeFiles(mutant, tree_m),
        root=root,
    )
    assert document["context"]["enumeration_used"] == "origin", (
        "the mutant is supposed to demonstrate a document that names the wrong source."
    )


def test_a_headline_beat_with_no_replay_frame_is_recorded_and_not_graded() -> None:
    """R10's last sentence, answered from the enumeration alone.

    D7 asks for one screen from two sources. The bundle that ships today carries no frame for
    ``POST /v1/demo/gate-run``, so the beat renders LIVE only. The walk RECORDS that and does
    not colour it: the remedy is a capture, which belongs to another lane, and a red this
    program invented for somebody else's file is a red nobody acts on.
    """
    module = real()
    _, document = walk(module, origin(module, api_base="/"))
    assert document["context"]["gate_run_has_replay_counterpart"] is False
    assert document["steps_failed"] == 0

    with_frame = (*DEFAULT_FRAMES, frame("POST", "/v1/demo/gate-run", 200, body={}))
    _, document = walk(module, origin(module, api_base="/", frames=with_frame))
    assert document["context"]["gate_run_has_replay_counterpart"] is True


def test_the_enumeration_is_fetched_at_the_bundle_url_the_artefact_compiled() -> None:
    module = real()
    http = FakeHttp(
        module,
        {
            **origin(module, bundle_url="./bundle/"),
        },
    )
    bundle = probes(module, http)
    module.walk(bundle, BASE, None, enumeration="auto", allow_replay=False)
    assert ("GET", "/bundle/manifest.json") in http.calls


# ══════════════════════════════════════════════════════════════════════════════════════
#  driving a frame
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_frame_that_404s_refuses_and_the_mutant_does_not() -> None:
    module = real()
    not_declared = {
        ("GET", "/v1/audit"): answer(module, 404, {"error": {"kind": "route_not_declared"}})
    }
    steps, _ = walk(module, origin(module, api_overrides=not_declared))
    frame_step = step(steps, "frame:GET /v1/audit")
    assert frame_step.outcome == module.FAILED
    assert "does not serve a request the artefact's own EvidenceBundle" in frame_step.why

    mutant = mutate(
        "    if answer.status in (404, 405):",
        "    if False:  # mutant: an absent route is fine",
        "judge_walk_frame_404_fine",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            api_overrides={
                ("GET", "/v1/audit"): answer(mutant, 404, {"error": {"kind": "route_not_declared"}})
            },
        ),
    )
    assert step(steps, "frame:GET /v1/audit").outcome != mutant.FAILED


def test_a_404_is_not_laundered_as_the_founders_step() -> None:
    """The named-reason test is keyed on the WORD, never on the status.

    The mutant grants the named reason to whatever answered, which is exactly how a 404 comes
    to be filed under "the SSM parameter is the founder's step" and a judge is told a missing
    route is somebody else's homework.
    """
    module = real()
    steps, _ = walk(
        module,
        origin(
            module,
            api_overrides={
                ("GET", "/v1/audit"): answer(module, 404, {"error": {"kind": "route_not_declared"}})
            },
        ),
    )
    assert step(steps, "frame:GET /v1/audit").outcome == module.FAILED

    mutant = mutate(
        "    if is_dsn_unset(record):\n        return Step(\n            step_id,",
        "    if True:  # mutant: every refusal is the founder's step\n"
        "        return Step(\n            step_id,",
        "judge_walk_launders_everything",
    )
    steps, document = walk(
        mutant,
        origin(
            mutant,
            api_overrides={
                ("GET", "/v1/audit"): answer(mutant, 404, {"error": {"kind": "route_not_declared"}})
            },
        ),
    )
    assert step(steps, "frame:GET /v1/audit").outcome == mutant.REFUSED
    assert document["exit_code"] == mutant.EXIT_OK


def test_a_frame_that_500s_refuses_and_the_mutant_does_not() -> None:
    module = real()
    boom = {
        ("GET", "/v1/audit"): answer(module, 500, {"error": {"kind": "unhandled", "status": 500}})
    }
    steps, _ = walk(module, origin(module, api_overrides=boom))
    assert step(steps, "frame:GET /v1/audit").outcome == module.FAILED
    assert "not a named reason" in step(steps, "frame:GET /v1/audit").why

    mutant = mutate(
        "    if answer.status >= 500:",
        "    if False:  # mutant: any 5xx is fine",
        "judge_walk_frame_500_fine",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            api_overrides={
                ("GET", "/v1/audit"): answer(mutant, 500, {"error": {"kind": "unhandled"}})
            },
        ),
    )
    assert step(steps, "frame:GET /v1/audit").outcome != mutant.FAILED


def test_a_body_that_is_not_an_envelope_refuses_and_the_mutant_does_not() -> None:
    module = real()
    junk = {("GET", "/v1/audit"): answer(module, 200, b"<html>a proxy ate this</html>")}
    steps, _ = walk(module, origin(module, api_overrides=junk))
    assert step(steps, "frame:GET /v1/audit").outcome == module.FAILED
    assert "not a MAINLINE envelope" in step(steps, "frame:GET /v1/audit").why

    mutant = mutate(
        "    if not envelope_shaped(record):",
        "    if False:  # mutant: any body is an envelope",
        "judge_walk_any_body",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant, api_overrides={("GET", "/v1/audit"): answer(mutant, 200, b"<html>x</html>")}
        ),
    )
    assert step(steps, "frame:GET /v1/audit").outcome != mutant.FAILED


def test_a_frame_dsn_unset_is_a_named_refusal_and_the_mutant_calls_it_a_failure() -> None:
    """INVERTED PAIRING, and the sentence R8 requires."""
    module = real()
    steps, document = walk(module, origin(module))
    for one in [s for s in steps if s.id.startswith("frame:")]:
        assert one.outcome == module.REFUSED
        assert one.reason == "dsn_unset"
    assert document["exit_code"] == module.EXIT_OK
    assert (
        "the origin is up, the route is reachable, and the SSM parameter is the founder's "
        "remaining step" in module.NAMED_REASONS["dsn_unset"]
    )

    mutant = mutate(
        "    if is_dsn_unset(record):\n        return Step(\n            step_id,",
        "    if False:  # mutant: the named-reason branch removed\n"
        "        return Step(\n            step_id,",
        "judge_walk_frame_no_named_reason",
    )
    steps, document = walk(mutant, origin(mutant))
    assert all(s.outcome == mutant.FAILED for s in steps if s.id.startswith("frame:"))
    assert document["exit_code"] == mutant.EXIT_FAILED


def test_a_status_that_differs_from_the_recording_is_data_not_a_failure() -> None:
    """The demo world is writable and the bundle records a merge that SUCCEEDED (200).

    Re-driving it against a seeded cluster legitimately answers something else, so the walk
    records the disagreement and does not assert it. What it does assert is reachability.
    """
    module = real()
    merged = {
        ("POST", f"/v1/permits/{SEEDED_PERMIT}/merge"): answer(
            module, 200, {**ENVELOPE, "resource": "merge_permit"}
        )
    }
    steps, _ = walk(module, origin(module, api_overrides=merged))
    one = step(steps, f"frame:POST /v1/permits/{SEEDED_PERMIT}/merge")
    assert one.outcome == module.SATISFIED
    assert one.detail["recorded_status"] == 409
    assert one.detail["status_matches_recording"] is False
    assert "NOT the recorded status (409)" in one.why


def test_every_sqlstate_the_payload_carries_is_recorded_with_its_pointer() -> None:
    module = real()
    refusal = {
        ("POST", f"/v1/permits/{SEEDED_PERMIT}/merge"): answer(
            module,
            409,
            {
                **ENVELOPE,
                "resource": "merge_permit",
                "data": {"refusal": {"sqlstate": "23514", "constraint": "gate_closed_when_issued"}},
            },
        )
    }
    steps, _ = walk(module, origin(module, api_overrides=refusal))
    one = step(steps, f"frame:POST /v1/permits/{SEEDED_PERMIT}/merge")
    assert {"pointer": "/data/refusal/sqlstate", "sqlstate": "23514"} in one.detail["sqlstates"]
    assert "23514" in one.why


# ══════════════════════════════════════════════════════════════════════════════════════
#  S5 — the headline beat
# ══════════════════════════════════════════════════════════════════════════════════════


def test_gate_run_404_refuses_and_the_mutant_does_not() -> None:
    module = real()
    steps, _ = walk(
        module, origin(module, gate_run=answer(module, 404, {"error": {"kind": "not_found"}}))
    )
    assert step(steps, "gate_run").outcome == module.FAILED
    assert "not declared by this" in step(steps, "gate_run").why

    mutant = mutate(
        '    if is_dsn_unset(record):\n        return Step(\n            "gate_run",',
        "    if True:  # mutant: any refusal is the founder's step\n"
        '        return Step(\n            "gate_run",',
        "judge_walk_gate_run_launders",
    )
    steps, document = walk(
        mutant, origin(mutant, gate_run=answer(mutant, 404, {"error": {"kind": "not_found"}}))
    )
    assert step(steps, "gate_run").outcome == mutant.REFUSED
    assert document["exit_code"] == mutant.EXIT_OK


def test_gate_run_dsn_unset_says_the_route_exists() -> None:
    module = real()
    steps, document = walk(module, origin(module))
    gate = step(steps, "gate_run")
    assert gate.outcome == module.REFUSED
    assert gate.reason == "dsn_unset"
    assert "THE ROUTE EXISTS" in gate.why
    assert document["exit_code"] == module.EXIT_OK


def test_a_wrong_sqlstate_refuses_and_the_mutant_does_not() -> None:
    """Beat 3 observed 23514 where the gate must raise P0001, and SAYS it expected P0001.

    ``declared`` is left at the contract's values on purpose: a payload whose own expectation
    had also moved would be caught by the cross-check one branch down, and the pairing would
    prove nothing about the comparison against this walk's transcription.
    """
    module = real()
    contract = ("00000", "23514", "P0001", "00000")
    observed = ("00000", "23514", "23514", "00000")
    wrong = answer(module, 200, gate_run_payload(sqlstates=observed, declared=contract))
    steps, _ = walk(module, origin(module, gate_run=wrong))
    assert step(steps, "gate_run").outcome == module.FAILED
    assert "the contract requires 'P0001'" in step(steps, "gate_run").why

    mutant = mutate(
        '        if found.get("sqlstate") != expected["sqlstate"]:',
        "        if False:  # mutant: the SQLSTATE comparison removed",
        "judge_walk_any_sqlstate",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            gate_run=answer(mutant, 200, gate_run_payload(sqlstates=observed, declared=contract)),
        ),
    )
    assert step(steps, "gate_run").outcome != mutant.FAILED


def test_a_verdict_that_is_not_proven_refuses_and_the_mutant_does_not() -> None:
    module = real()
    steps, _ = walk(
        module, origin(module, gate_run=answer(module, 200, gate_run_payload(verdict="NOT PROVEN")))
    )
    assert step(steps, "gate_run").outcome == module.FAILED
    assert "not 'PROVEN'" in step(steps, "gate_run").why

    mutant = mutate(
        '    if payload.get("verdict") != "PROVEN":',
        "    if False:  # mutant: any verdict accepted",
        "judge_walk_any_verdict",
    )
    steps, _ = walk(
        mutant, origin(mutant, gate_run=answer(mutant, 200, gate_run_payload(verdict="NOT PROVEN")))
    )
    assert step(steps, "gate_run").outcome != mutant.FAILED


def test_the_payloads_own_expectation_is_compared_and_the_mutant_takes_it_on_trust() -> None:
    """Two places holding one fact are a hazard only when nobody compares them.

    The payload carries what each beat was *written against* precisely so a reader can check
    the driver's arithmetic. A server that quietly moved its own expectation to match what it
    produced would still say ``matched_expectation: true`` on every beat.
    """
    module = real()
    lying = answer(
        module,
        200,
        gate_run_payload(
            sqlstates=("00000", "23514", "P0001", "00000"),
            declared=("00000", "23514", "23514", "00000"),
        ),
    )
    steps, _ = walk(module, origin(module, gate_run=lying))
    assert step(steps, "gate_run").outcome == module.FAILED
    assert "One of the two is wrong and neither may be assumed" in step(steps, "gate_run").why

    mutant = mutate(
        "                if key in declared and declared[key] != expected[key]:",
        "                if False:  # mutant: the payload's own expectation taken on trust",
        "judge_walk_trusts_the_payload",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            gate_run=answer(
                mutant,
                200,
                gate_run_payload(
                    sqlstates=("00000", "23514", "P0001", "00000"),
                    declared=("00000", "23514", "23514", "00000"),
                ),
            ),
        ),
    )
    assert step(steps, "gate_run").outcome != mutant.FAILED


def test_a_40001_retry_is_a_named_refusal_and_the_mutant_calls_it_a_failure() -> None:
    """INVERTED PAIRING. 40001 leaves the transaction UNDECIDED, which is not a refusal."""
    module = real()
    retry = answer(module, 200, gate_run_payload(outcome="retry", verdict="NOT PROVEN"))
    steps, document = walk(module, origin(module, gate_run=retry))
    gate = step(steps, "gate_run")
    assert gate.outcome == module.REFUSED
    assert gate.reason == "retry_40001"
    assert document["exit_code"] == module.EXIT_OK

    mutant = mutate(
        '    if payload.get("outcome") == "retry":',
        "    if False:  # mutant: a retry is graded as a verdict",
        "judge_walk_retry_is_a_verdict",
    )
    steps, _ = walk(
        mutant,
        origin(
            mutant,
            gate_run=answer(mutant, 200, gate_run_payload(outcome="retry", verdict="NOT PROVEN")),
        ),
    )
    assert step(steps, "gate_run").outcome == mutant.FAILED


def test_a_proven_gate_run_satisfies_and_records_the_four_sqlstates() -> None:
    module = real()
    steps, _ = walk(module, origin(module, gate_run=answer(module, 200, gate_run_payload())))
    gate = step(steps, "gate_run")
    assert gate.outcome == module.SATISFIED
    assert "00000 -> 23514 -> P0001 -> 00000" in gate.why
    codes = [s["sqlstate"] for s in gate.detail["sqlstates"]]
    assert codes.count("P0001") >= 1 and codes.count("23514") >= 1


# ══════════════════════════════════════════════════════════════════════════════════════
#  the vocabulary, the stamp and the masker
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_named_reason_set_is_closed_and_the_mutant_lets_anything_in() -> None:
    module = real()
    with pytest.raises(ValueError, match="closed set of named reasons"):
        module.Step("x", "x", module.REFUSED, "why", reason="because_it_was_friday")
    with pytest.raises(ValueError, match="must name its reason"):
        module.Step("x", "x", module.REFUSED, "why")
    with pytest.raises(ValueError, match="only a REFUSED step carries a reason"):
        module.Step("x", "x", module.SATISFIED, "why", reason="dsn_unset")

    mutant = mutate(
        "            if self.reason not in NAMED_REASONS:",
        "            if False:  # mutant: the reason vocabulary opened up",
        "judge_walk_open_vocabulary",
    )
    accepted = mutant.Step("x", "x", mutant.REFUSED, "why", reason="because_it_was_friday")
    assert accepted.outcome == mutant.REFUSED


def test_a_synthetic_run_is_stamped_and_the_mutant_claims_it_was_live(
    tmp_path: pathlib.Path,
) -> None:
    module = real()
    code, document = run_main(module, origin(module), tmp_path / "real")
    assert code == module.EXIT_OK
    assert document["source"] == "synthetic"
    assert {s["source"] for s in document["steps"]} == {"synthetic"}

    mutant = mutate(
        '        "source": probes.source,\n        "source_note": (',
        '        "source": "live",  # mutant: the stamp forged\n        "source_note": (',
        "judge_walk_forged_stamp",
    )
    _, document = run_main(mutant, origin(mutant), tmp_path / "mutant")
    assert document["source"] == "live", (
        "the mutant is supposed to demonstrate a document that claims a live reading it did "
        "not take."
    )


def test_no_dsn_reaches_the_document_and_the_mutant_publishes_one(tmp_path: pathlib.Path) -> None:
    """The pairing uses a PASSWORDLESS DSN, because two maskers overlap on a password-bearing
    one and the second would hide the first's absence. Both are asserted, only one is paired.
    """
    leak = "postgresql://demo.invalid:26257/defaultdb?sslmode=verify-full"
    module = real()
    script = origin(
        module, api=answer(module, 503, {"ok": False, "reason": "dsn_unset", "detail": leak})
    )
    _, document = run_main(module, script, tmp_path / "real")
    text = json.dumps(document)
    assert leak not in text
    assert "<dsn>" in text
    assert "hunter2" not in module.mask("postgresql://mainline_api:hunter2@demo.invalid:26257/db")
    assert "hunter2" not in module.mask("PGPASSWORD=hunter2")

    mutant = mutate(
        '    out = _DSN.sub("<dsn>", text or "")',
        '    out = text or ""  # mutant: the DSN masker removed',
        "judge_walk_no_dsn_mask",
    )
    _, document = run_main(
        mutant,
        origin(
            mutant, api=answer(mutant, 503, {"ok": False, "reason": "dsn_unset", "detail": leak})
        ),
        tmp_path / "mutant",
    )
    assert leak in json.dumps(document), (
        "the mutant is supposed to demonstrate the leak the masker prevents."
    )


def test_an_account_id_is_masked_and_a_permit_uuid_is_not() -> None:
    """Measured on the first live run: a masker keyed on twelve digits alone ate the permits.

    ``dec0de00-0006-4000-8000-000000000001`` ends in twelve digits. Masking the demo's own
    identifiers would not be safety, it would be an evidence file no reader can check against
    the seed.
    """
    module = real()
    arn = "arn:aws:lambda:ap-southeast-1:123456789012:function:mainline-demo-api"
    assert module.mask(arn) == "arn:aws:lambda:ap-southeast-1:<account>:function:mainline-demo-api"
    assert module.mask(SEEDED_PERMIT) == SEEDED_PERMIT
    assert module.mask("1234REDACTED5678") == "<account>"

    mutant = mutate(
        '    return _UUID_OR_TWELVE_DIGITS.sub(lambda m: m.group(1) or "<account>", out)',
        '    return re.sub(r"\\b\\d{12}\\b", "<account>", out)  # mutant: UUIDs no longer spared',
        "judge_walk_masks_uuids",
    )
    assert mutant.mask(SEEDED_PERMIT) != SEEDED_PERMIT
    assert mutant.mask(arn) == module.mask(arn)


def test_plain_http_to_a_remote_host_is_refused_and_the_mutant_allows_it() -> None:
    module = real()
    with pytest.raises(module.Unavailable, match="not HTTPS has no certificate"):
        module.HttpClient._guard("http://demo.invalid/")
    module.HttpClient._guard("https://demo.invalid/")
    module.HttpClient._guard("http://127.0.0.1:8000/")

    mutant = mutate(
        '        if split.scheme == "http" and (split.hostname or "") in LOOPBACK_HOSTS:',
        '        if split.scheme == "http":  # mutant: plain HTTP anywhere',
        "judge_walk_any_scheme",
    )
    mutant.HttpClient._guard("http://demo.invalid/")


def test_usage_errors_exit_two_and_never_open_anything() -> None:
    module = real()
    assert module.main(["--base-url", "   "]) == module.EXIT_USAGE
    assert module.main(["--base-url", "demo.invalid"]) == module.EXIT_USAGE
    assert module.main(["--base-url", BASE, "--timeout", "0"]) == module.EXIT_USAGE


def test_a_base_url_copied_out_of_a_browser_walks_the_same(tmp_path: pathlib.Path) -> None:
    """A judge pastes the address bar, which carries a trailing slash. Same walk, same paths.

    Not cosmetic: every URL this program builds is a concatenation, and a doubled slash would
    turn every kernel route into a 404 that looks exactly like an absent route.
    """
    module = real()
    http = FakeHttp(module, origin(module, api_base="/"))
    out = tmp_path / "judge-walk.json"
    code = module.main(["--base-url", BASE + "/", "--out", str(out)], probes=probes(module, http))
    assert code == module.EXIT_OK
    assert ("GET", "/") in http.calls
    assert ("GET", "/bundle/manifest.json") in http.calls
    assert not any("//" in path for _method, path in http.calls)


# ══════════════════════════════════════════════════════════════════════════════════════
#  the whole thing, in the state the wave is aiming at
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_live_console_over_an_unset_dsn_exits_zero_and_says_why(tmp_path: pathlib.Path) -> None:
    """R8, end to end: the deployment the wave produces, with the founder's step outstanding.

    LIVE console, every kernel route answering ``dsn_unset``. Nothing FAILED, every refusal
    named, exit 0 — and the summary carries the sentence R8 requires rather than a silence.
    """
    module = real()
    code, document = run_main(module, origin(module, api_base="/"), tmp_path)
    assert code == module.EXIT_OK
    assert document["steps_failed"] == 0
    assert document["refused_reasons"] == ["dsn_unset"]
    assert document["verdict"] == "WALKED, NOTHING FAILED"
    assert document["context"]["transport_mode"] == "LIVE"
    assert document["context"]["frames_driven"] == len(DEFAULT_FRAMES)
    assert (
        "the origin is up, the route is reachable, and the SSM parameter is the founder's "
        "remaining step" in document["named_reasons"]["dsn_unset"]
    )


def test_a_fully_working_deployment_satisfies_every_step(tmp_path: pathlib.Path) -> None:
    """The other end of the range: nothing refused, nothing failed, everything measured."""
    module = real()
    script = origin(
        module,
        api_base="/",
        api=answer(module, 200, {"ok": True, "database": "mainline", "migrations_applied": 271}),
        gate_run=answer(module, 200, gate_run_payload()),
    )
    for one in DEFAULT_FRAMES:
        script[(one["request"]["method"], one["request"]["path"])] = answer(
            module, one["response"]["status"], ENVELOPE
        )
    code, document = run_main(module, script, tmp_path)
    assert code == module.EXIT_OK
    assert document["steps_failed"] == 0
    assert document["steps_refused"] == 0
    assert document["steps_satisfied"] == document["steps_total"]


def test_one_failure_anywhere_turns_the_whole_walk_red(tmp_path: pathlib.Path) -> None:
    module = real()
    script = origin(module, api_base="/")
    script[("GET", "/v1/audit")] = answer(module, 404, {"error": {"kind": "route_not_declared"}})
    code, document = run_main(module, script, tmp_path)
    assert code == module.EXIT_FAILED
    assert document["failed_ids"] == ["frame:GET /v1/audit"]
    assert document["steps_refused"] > 0, (
        "the named refusals must survive alongside the failure; a red walk that stopped "
        "recording would lose the reason the rest of the deployment is in the state it is in."
    )
