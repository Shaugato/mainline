# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The check registry: sixteen rows, the runners bound to them, and the run loop.

Two registries, deliberately kept apart
---------------------------------------
:data:`SPEC_ROWS` is a copy of ``spec/custody/checks.yaml`` — *what each check proves,
what it defeats, which module owns it, and its declared status*. It is duplicated into
this package for exactly one reason: ``trappoint-verify`` is meant to be run by a stranger
with ``uvx``, from a wheel, with no MAINLINE checkout anywhere near it, and
``explain-check 14`` has to work there. The duplication is guarded the same way the
vendored canonicaliser is —
``packages/trappoint-verify/tests/test_checks_totality.py`` asserts row-by-row equality
against the real YAML whenever the repository is present, so drift fails the build rather
than shipping.

:data:`registered` is the *runtime* registry: check id → the function that actually runs.
Worker 6 registers the nine structural checks; worker 7 registers the seven cryptographic
ones through the same hook. A check with a row and no runner is not silently absent — it
reports ``SKIP(not-implemented)``, names the module that would have implemented it, and
appears in the ``NOT CHECKED`` banner like any other skip.

The lag between the two, stated rather than hidden
--------------------------------------------------
``spec/custody/checks.yaml`` was frozen with every check at ``status: deferred``, which was
the honest state on 2026-08-07 because no verifier existed. That file has a single owner
(the custody spec worker) and this package does not edit it. So there is a window in which
a check is *implemented here* and still *declared deferred there*.
:data:`SPEC_STATUS_LAG` names exactly which ids are in that window, the totality test
asserts the set is neither larger nor smaller than reality, and ``explain-check`` prints
the discrepancy instead of picking whichever answer looks better.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from trappoint_verify.bundle import Bundle
from trappoint_verify.report import Outcome, Report, failed, skipped

__all__ = [
    "CHECK_IDS",
    "SPEC_ROWS",
    "SPEC_STATUS_LAG",
    "CheckContext",
    "CheckSpec",
    "LoadReport",
    "ModuleLoad",
    "VerifyOptions",
    "load_all",
    "modules_for_checks",
    "register",
    "register_runner",
    "registered",
    "run_all",
    "spec_for",
    "unregister",
]


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """One row of ``spec/custody/checks.yaml``, verbatim."""

    id: int
    name: str
    proves: str
    defeats: str
    offline: bool
    module: str
    test: str
    status: str
    target_status: str
    owner: str


SPEC_ROWS: Final[tuple[CheckSpec, ...]] = (
    CheckSpec(
        id=1,
        name="leaf_hash_recomputation",
        proves="Each leaf's hash is SHA-256(0x00 || canon_bytes), dispatched on payload_ver.",
        defeats="record substitution",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_leaf_hash",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=2,
        name="inclusion_proof",
        proves="Leaf i is in the tree committed by checkpoint n (RFC 6962 2.1.1).",
        defeats="'this was never in the log'",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_inclusion",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=3,
        name="consistency_proof_every_pair",
        proves=(
            "The tree at size m is a prefix of the tree at size n, for EVERY consecutive "
            "checkpoint pair."
        ),
        defeats="deletion and rewrite (A1, A2)",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_consistency",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=4,
        name="log_signature",
        proves=(
            "The checkpoint note was signed by the pinned log key (C2SP note type 0x02, "
            "ECDSA P-256, DER)."
        ),
        defeats="forged log; forged receipt",
        offline=True,
        module="trappoint_verify.checks.signature",
        test="packages/trappoint-verify/tests/crypto/test_signature.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=5,
        name="rfc3161_upper_bound",
        proves=(
            "messageImprint == SHA-256(note text); the token chains to a trusted root; "
            "genTime is extracted."
        ),
        defeats="backdating forward (A8)",
        offline=True,
        module="trappoint_verify.checks.tsa",
        test="packages/trappoint-verify/tests/crypto/test_tsa.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=6,
        name="beacon_lower_bound",
        proves="The checkpoint quotes a beacon value that did not exist before its round time.",
        defeats="backdating backward (A9)",
        offline=True,
        module="trappoint_verify.checks.beacon",
        test="packages/trappoint-verify/tests/crypto/test_beacon.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=7,
        name="witness_quorum",
        proves=(
            "At least q cosignatures over the SAME (size, root), across distinct trust "
            "domains, at least one adverse."
        ),
        defeats="split view",
        offline=True,
        module="trappoint_verify.checks.witness",
        test="packages/trappoint-verify/tests/crypto/test_witness_quorum.py",
        status="deferred",
        target_status="implemented_but_not_adverse",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=8,
        name="archive_object_lock",
        proves=(
            "The archived object bytes equal the note; ObjectLockMode is COMPLIANCE; "
            "LastModified falls inside the time bracket."
        ),
        defeats="archive tampering (T2), A15",
        offline=False,
        module="trappoint_verify.checks.archive",
        test="packages/trappoint-verify/tests/crypto/test_archive.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=9,
        name="link_chain_and_density",
        proves="link_hash recomputes across every leaf, and seq is dense 0..n-1.",
        defeats="jury-legible chain integrity; A2",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_link_chain",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=10,
        name="canonicaliser_identity",
        proves=(
            "canon_src_sha256 in the checkpoint equals the SHA-256 of the canonicaliser the "
            "verifier is running."
        ),
        defeats="canonicaliser downgrade (A5); the scheme's own code being outside the scheme",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_canon_identity",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=11,
        name="gate_self_attestation",
        proves=(
            "The trigger definitions captured at migration time are inside the ledger and "
            "match the gate source in the bundle."
        ),
        defeats="trigger disable / silent gate removal (A13)",
        offline=True,
        module="trappoint_verify.checks.attestation",
        test="packages/trappoint-verify/tests/crypto/test_attestation.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=12,
        name="webauthn_reverification",
        proves=(
            "The assertion verifies against the ENROLLED COSE key, and the challenge "
            "reconstructs from the stored exposure receipt."
        ),
        defeats="'your server says he signed'",
        offline=True,
        module="trappoint_verify.checks.webauthn",
        test="packages/trappoint-verify/tests/crypto/test_webauthn.py",
        status="deferred",
        target_status="implemented",
        owner="verify-crypto",
    ),
    CheckSpec(
        id=13,
        name="no_sandbox_leaf",
        proves="No leaf in an evidentiary bundle carries is_sandbox = true.",
        defeats="anonymous demo writes inside an evidentiary tree (A12)",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_no_sandbox",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=14,
        name="closure_generation_monotone",
        proves=(
            "For every (clause_uuid, as_of_commit), closure generations are dense from 1 and "
            "max_severity is non-decreasing."
        ),
        defeats="a mass closure rewrite (S2, attack A10)",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_closure_monotone",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=15,
        name="receipt_coverage",
        proves=(
            "Every Signed Disposition Receipt whose MMD has expired has its leaf present and "
            "included under a checkpoint."
        ),
        defeats="receipt orphaning (A14); silent non-merge of a disposition",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_structural_checks.py::test_receipt_coverage",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
    CheckSpec(
        id=16,
        name="bundle_totality",
        proves=(
            "The bundle is internally consistent and the run looked at everything: each "
            "checkpoint's index fields match its parsed note, every leaf has an inclusion "
            "proof, every consecutive checkpoint pair has a consistency proof, every "
            "checkpoint's canon line matches the bundle's declared canonicaliser, and every "
            "absent optional section produced a named SKIP."
        ),
        defeats="a verifier that passes because it did not look",
        offline=True,
        module="trappoint_verify.checks.structural",
        test="packages/trappoint-verify/tests/test_checks_totality.py",
        status="deferred",
        target_status="implemented",
        owner="verify-core",
    ),
)

#: The sixteen ids, in the order a run walks them. Check 16 is last because it reads the
#: outcomes of the other fifteen: it is the check that makes them honest.
CHECK_IDS: Final[tuple[int, ...]] = tuple(row.id for row in SPEC_ROWS)

#: Checks this build implements while ``spec/custody/checks.yaml`` still declares them
#: ``deferred``. The registry file has one owner and this package does not edit it; the
#: totality test asserts this tuple equals the real discrepancy, so it cannot rot in
#: either direction.
SPEC_STATUS_LAG: Final[tuple[int, ...]] = (1, 2, 3, 9, 10, 13, 14, 15, 16)


def spec_for(check_id: int) -> CheckSpec:
    """Return the registry row for *check_id*, or raise ``KeyError``."""
    for row in SPEC_ROWS:
        if row.id == check_id:
            return row
    raise KeyError(f"no check with id {check_id}; the registry holds {CHECK_IDS}")


def modules_for_checks() -> dict[str, tuple[int, ...]]:
    """Group the registry rows by module: ``dotted name -> the check ids it owns``."""
    grouped: dict[str, list[int]] = {}
    for row in SPEC_ROWS:
        grouped.setdefault(row.module, []).append(row.id)
    return {module: tuple(ids) for module, ids in grouped.items()}


# --------------------------------------------------------------------------------------
# Options and context
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VerifyOptions:
    """Everything a check may consult besides the bundle.

    Every online capability is **opt-in and off by default** (CU-7). Absence downgrades
    the affected check to ``SKIP(offline)``; it never upgrades it to a quiet pass.
    """

    log_key: str = ""
    kms_pubkey: str = ""
    tile_url: str = ""
    s3: bool = False
    redact_webauthn: bool = False


@dataclass(frozen=True, slots=True)
class CheckContext:
    """What a runner is given: the bundle, the options, and the outcomes so far.

    ``prior`` exists for check 16 alone. A totality check that could not see the other
    fifteen verdicts could only assert that the bundle is self-consistent, not that the
    run looked at all of it — which is the more important half.
    """

    bundle: Bundle
    options: VerifyOptions
    prior: tuple[Outcome, ...] = ()
    selection: tuple[int, ...] | None = None


CheckRunner = Callable[[CheckContext], Outcome]

_RUNNERS: dict[int, CheckRunner] = {}


def register_runner(check_id: int, runner: CheckRunner) -> None:
    """Bind *runner* to *check_id*. Refuses an id that has no registry row."""
    spec_for(check_id)
    _RUNNERS[check_id] = runner


def register(check_id: int) -> Callable[[CheckRunner], CheckRunner]:
    """Return a decorator that binds the decorated function to *check_id*."""

    def bind(runner: CheckRunner) -> CheckRunner:
        register_runner(check_id, runner)
        return runner

    return bind


def unregister(check_id: int) -> None:
    """Remove the runner for *check_id* if one is bound. Used by tests, not by the CLI."""
    _RUNNERS.pop(check_id, None)


def registered() -> Mapping[int, CheckRunner]:
    """Return a read-only view of the runtime registry."""
    return dict(_RUNNERS)


# --------------------------------------------------------------------------------------
# Module loading
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ModuleLoad:
    """Whether one check module imported, and why not when it did not."""

    module: str
    loaded: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class LoadReport:
    """The result of :func:`load_all`."""

    modules: tuple[ModuleLoad, ...] = ()

    def missing(self) -> tuple[ModuleLoad, ...]:
        """Modules that did not import."""
        return tuple(entry for entry in self.modules if not entry.loaded)


def _import_check_module(dotted: str) -> ModuleLoad:
    """Import one optional check module, reporting rather than raising.

    Every import below is a **literal** module name. That is not verbosity for its own
    sake: ``tests/test_dependency_floor.py`` walks this package's AST and asserts the
    top-level import set is a subset of the standard library plus ``cryptography``, and an
    AST walk cannot see through ``__import__(name)`` or ``importlib.import_module(name)``.
    A dependency floor that a dynamic import can step over is a floor in name only, so the
    dispatch is written out and adding a check module is a visible edit here.

    The ``type: ignore[attr-defined, unused-ignore]`` on each line is deliberate and is
    stable in **both** states: today the module does not exist and mypy is right to say so;
    once worker 7 lands it the ignore would become unused, and ``warn_unused_ignores`` would
    turn that into a new error in someone else's commit. Naming ``unused-ignore`` too means
    this file needs no edit either way.
    """
    short = dotted.rsplit(".", 1)[-1]
    try:
        if short == "signature":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                signature,  # noqa: F401
            )
        elif short == "tsa":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                tsa,  # noqa: F401
            )
        elif short == "beacon":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                beacon,  # noqa: F401
            )
        elif short == "witness":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                witness,  # noqa: F401
            )
        elif short == "archive":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                archive,  # noqa: F401
            )
        elif short == "attestation":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                attestation,  # noqa: F401
            )
        elif short == "webauthn":
            from trappoint_verify.checks import (  # type: ignore[attr-defined, unused-ignore]
                webauthn,  # noqa: F401
            )
        else:
            return ModuleLoad(
                module=dotted,
                loaded=False,
                reason=(
                    "no importer is wired for this module in checks/__init__.py, so its "
                    "checks can never run"
                ),
            )
    except ImportError as exc:
        return ModuleLoad(module=dotted, loaded=False, reason=str(exc))
    return ModuleLoad(module=dotted, loaded=True)


def load_all() -> LoadReport:
    """Import every check module named in :data:`SPEC_ROWS`, tolerating absent ones.

    ``checks.structural`` is mandatory: if it does not import, the installation is broken
    and the ``ImportError`` propagates. Every other module is optional at import time,
    because ``trappoint-verify`` must be usable — and must be *honest* — while worker 7's
    cryptographic checks are still landing.
    """
    from trappoint_verify.checks import structural  # noqa: F401

    results = [ModuleLoad(module="trappoint_verify.checks.structural", loaded=True)]
    for dotted in modules_for_checks():
        if dotted.endswith(".structural"):
            continue
        results.append(_import_check_module(dotted))
    return LoadReport(modules=tuple(results))


# --------------------------------------------------------------------------------------
# The run loop
# --------------------------------------------------------------------------------------


def _not_implemented(spec: CheckSpec) -> Outcome:
    return skipped(
        spec.id,
        spec.name,
        "not-implemented",
        f"no runner is bound to check {spec.id}",
        detail=(
            f"{spec.module} did not import or did not register a runner.",
            (
                f"Registry says: status={spec.status}, target={spec.target_status}, "
                f"owner={spec.owner}."
            ),
            f"This check would have proved: {spec.proves}",
        ),
    )


def _guarded(spec: CheckSpec, runner: CheckRunner, context: CheckContext) -> Outcome:
    """Run one check, converting an escaping exception into a finding.

    Every byte a check reads may have been chosen by an adversary. A traceback where a
    verdict belongs is a denial of service against the person holding the bundle, and it
    is also a verdict — an unreadable one. So the exception becomes ``FAIL``, named.
    """
    try:
        return runner(context)
    except Exception as exc:  # noqa: BLE001 — see the docstring; this is the point.
        return failed(
            spec.id,
            spec.name,
            "check-raised",
            f"the check raised {type(exc).__name__} instead of returning a verdict",
            detail=(
                str(exc),
                "This is a defect in the verifier or a bundle shape it does not model.",
            ),
        )


def run_all(
    bundle: Bundle,
    options: VerifyOptions | None = None,
    *,
    only: tuple[int, ...] | None = None,
    tool_version: str = "0.0.0",
) -> Report:
    """Run the selected checks over *bundle* and return the report.

    Checks run in registry order, and check 16 therefore runs last and sees the other
    fifteen verdicts. A selection (``only``) is not a quiet subset: the report opens with
    a ``SELECTED RUN`` banner naming what was not run.
    """
    resolved = options if options is not None else VerifyOptions()
    runners = registered()
    report = Report(subject=bundle.subject, tool_version=tool_version, selection=only)
    prior: list[Outcome] = []
    for check_id in CHECK_IDS:
        if only is not None and check_id not in only:
            continue
        spec = spec_for(check_id)
        runner = runners.get(check_id)
        context = CheckContext(bundle=bundle, options=resolved, prior=tuple(prior), selection=only)
        outcome = _not_implemented(spec) if runner is None else _guarded(spec, runner, context)
        prior.append(outcome)
        report.add(outcome)
    return report
