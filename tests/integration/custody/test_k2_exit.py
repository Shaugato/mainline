# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""K2 THE CHAIN — the six exit criteria, committed as a **failing** test.

PL-2, red before green. For a product whose deliverable is a refusal, a test suite that has
never been red asserts nothing: a green suite is equally consistent with "the mechanism
works" and "the mechanism was never wired up". So the six exit criteria of milestone K2 are
written *first*, as executable assertions, **before a single line of ledger code exists**,
and the failing run is itself the proof artefact. Its URL is recorded in
``docs/adr/0040-custody-red-before-green.md``.

**These six assertions are made green by building artefacts, never by editing the
assertions.** Any commit that weakens one of them without an accompanying ADR is a commit
that removed a criterion rather than met it.

The criteria, from ``BUILD_PLAN.md`` §3 K2:

1. A deliberate tamper test — delete a leaf, renumber, re-link — is caught by a
   **consistency proof**, not by inspection.
2. A deliberate closure-rewrite test is caught by **verifier check 14**.
3. ``trappoint-verify`` confirms an exported bundle **on a machine that has never touched
   the cluster**, with no credential.
4. Checkpoint cadence is **measured**, and the ``checkpoint_age_seconds`` deadman is
   defined.
5. ``spec/wire/checkpoint.md`` is tagged **v1.0** with a CHANGELOG entry.
6. Migration attestation is chained, and the fingerprint is **stable across two consecutive
   computations**.

Why the criterion tests assert on *artefacts* rather than driving a live cluster: three of
the six describe outcomes that only exist once the nemesis harness, the verifier and the
reference bundle exist, and a test that skipped for want of a cluster would be green-by-
absence — the exact failure mode this file exists to refuse. Each criterion therefore
asserts the existence and shape of the evidence that the criterion was met, and the nemesis
suite is what produces that evidence from a real run against a real cluster.

Auxiliary tests in this file (the ones the evidentiary map and the check registry name)
**skip loudly** when their dependency is absent, because they are not exit criteria.

Where the six stand, measured 2026-08-10
----------------------------------------
Three are met. K2.1 and K2.2 became green when ``evidence/CUSTODY_ATTACK_MATRIX.md`` was
regenerated from a nemesis run that executed 14 of the 15 attacks as real SQL against a
disposable CockroachDB v26.2.5 — A1 caught by check 3, A10 caught by check 14 in 251 ms —
and when ``spec/custody/checks.yaml`` was corrected to record the nine structural checks as
``implemented``, which is what they had already been for days. K2.3 was green already.

Three are not met, and each of the three is blocked on **an artefact that does not exist,
owned by somebody outside custody**. Their assertions below name that artefact by path and
name its owner, because "K2.4 NOT MET" tells a reader nothing they can act on. The
thresholds are untouched: no sample count was lowered, no field was made optional, and no
criterion was rewritten to describe what happens to exist. A criterion that cannot be met
today fails today, and it says whose desk it is on.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

SPEC = REPO_ROOT / "spec"
EVIDENCE = REPO_ROOT / "evidence"
PACKAGES = REPO_ROOT / "packages"

# Make the workspace's own source trees importable without an editable install, so that
# `python -m pytest tests/integration/custody/test_k2_exit.py` from a fresh clone reports
# the true state of the milestone rather than a wall of SKIPs. A criterion that skips
# because of a missing `uv sync` is a criterion that is green by absence, which is the
# failure mode this file exists to refuse.
for _source_root in (
    PACKAGES / "trappoint-jcs" / "src",
    PACKAGES / "trappoint-ledger" / "src",
    PACKAGES / "trappoint-verify" / "src",
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-custody-patrol" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} does not exist"
    return path.read_text(encoding="utf-8")


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _load_yaml(relative: str) -> dict:
    yaml = pytest.importorskip("yaml", reason="PyYAML absent; registry parsing skipped")
    return yaml.safe_load(_read(relative))


# =======================================================================================
# The six exit criteria. Each of these MUST fail until its artefact exists.
# =======================================================================================


def test_k2_1_tamper_is_caught_by_a_consistency_proof() -> None:
    """Criterion 1 — attack A1 is detected by check 3, proven by a run, not by prose.

    ``A1 delete_and_relink`` is *the* attack: delete leaf k, renumber k+1..n, and recompute
    every ``link_hash`` in one ``UPDATE … FROM generate_series``. Afterwards the table is
    perfectly self-consistent and the link chain verifies. Only a consistency proof against
    a root that already left our control catches it.

    The evidence that this is true is ``evidence/CUSTODY_ATTACK_MATRIX.md``, generated from
    an actual nemesis run against a disposable cluster — not from ``attacks.yaml``, which
    records only what we *expect*.
    """
    matrix = EVIDENCE / "CUSTODY_ATTACK_MATRIX.md"
    harness = REPO_ROOT / "tests/integration/custody/nemesis/test_ledger_attacks.py"

    assert harness.is_file(), (
        "K2.1 NOT MET: the nemesis harness does not exist. A1 (delete_and_relink) has never "
        "been executed against a real cluster, so 'caught by a consistency proof' is a "
        "claim rather than an observation. Expected "
        "tests/integration/custody/nemesis/test_ledger_attacks.py."
    )
    assert matrix.is_file(), (
        "K2.1 NOT MET: evidence/CUSTODY_ATTACK_MATRIX.md does not exist. The matrix is "
        "generated from a nemesis run and is the only artefact that proves an attack was "
        "detected rather than merely listed."
    )
    text = matrix.read_text(encoding="utf-8")
    assert re.search(r"\bA1\b.*\bcheck 3\b", text) or re.search(r"\bA1\b.*\|\s*3\b", text), (
        "K2.1 NOT MET: the attack matrix does not record A1 as detected by check 3 "
        "(consistency proof). Detection by check 9 alone would mean the tamper was caught "
        "by chain inspection, which the criterion explicitly excludes."
    )


def test_k2_2_closure_rewrite_is_caught_by_check_14() -> None:
    """Criterion 2 — attack A10 is detected by check 14.

    Adversarial-review finding S2: the blame closure sits under every ancestry gate and was
    mutable, un-granted, un-ledgered and unguarded. One ``UPDATE … SET max_severity = 0``
    from a Lambda execution role evaporates every weakening gate while every coverage view
    reports full coverage. Check 14 — generations dense from 1, ``max_severity``
    non-decreasing — is what makes that visible to somebody who has never touched the
    cluster.
    """
    matrix = EVIDENCE / "CUSTODY_ATTACK_MATRIX.md"
    assert matrix.is_file(), (
        "K2.2 NOT MET: evidence/CUSTODY_ATTACK_MATRIX.md does not exist, so A10 "
        "(closure_mass_rewrite) has never been run against check 14."
    )
    text = matrix.read_text(encoding="utf-8")
    assert re.search(r"\bA10\b.*\b(check )?14\b", text), (
        "K2.2 NOT MET: the attack matrix does not record A10 as detected by check 14."
    )

    registry = _load_yaml("spec/custody/checks.yaml")
    check14 = next(c for c in registry["checks"] if c["id"] == 14)
    assert check14["status"] in ("implemented", "implemented_but_not_adverse"), (
        "K2.2 NOT MET: spec/custody/checks.yaml still records check 14 with status "
        f"{check14['status']!r}. A deferred check reports SKIP(not-implemented) at runtime "
        "and cannot have caught anything."
    )


def test_k2_3_bundle_verifies_with_no_cluster_and_no_credential() -> None:
    """Criterion 3 — a stranger's machine, offline, no credential.

    This is the sentence the whole domain exists to make true. It has three parts, and all
    three have to hold: the reference bundle exists and is committed; the verifier exists;
    and the verifier's dependency floor is ``cryptography`` alone, so that "a stranger can
    run it" is a 200 ms fact rather than an instruction to install our stack.
    """
    bundle = EVIDENCE / "reference-ledger" / "bundle.json"
    assert bundle.is_file(), (
        "K2.3 NOT MET: evidence/reference-ledger/bundle.json does not exist. Without a "
        "committed reference bundle there is nothing for a stranger to verify before they "
        "ever run the product."
    )
    assert _module_available("trappoint_verify"), (
        "K2.3 NOT MET: trappoint_verify is not importable. The offline verifier is the "
        "executable form of the specification; content written before it is content "
        "written against nothing."
    )
    floor_test = PACKAGES / "trappoint-verify" / "tests" / "test_dependency_floor.py"
    network_test = PACKAGES / "trappoint-verify" / "tests" / "test_no_network.py"
    assert floor_test.is_file() and network_test.is_file(), (
        "K2.3 NOT MET: the dependency-floor test and the socket-patched no-network test "
        "must both exist. 'Requires no cooperation from us' is a test, not a promise."
    )


def test_k2_4_checkpoint_cadence_measured_and_deadman_defined() -> None:
    """Criterion 4 — the 60-second window is a measurement, not an aspiration.

    A ledger that claims a zero window of undetectable mutation is lying. Ours is ~60 s and
    the honest thing to do with that number is measure it and alarm on it. The deadman
    (``checkpoint_age_seconds``) is *defined* in K2 and *fires* from K6.
    """
    measurement = EVIDENCE / "k2-checkpoint-cadence.json"
    assert measurement.is_file(), (
        "K2.4 NOT MET — MISSING ARTEFACT: evidence/k2-checkpoint-cadence.json\n"
        "  owner: the `sequencer` worker (measurement), cloud lead (deadman) — "
        "docs/adr/0040-custody-red-before-green.md\n"
        "  what would make it green: a file at that path carrying keys 'samples' (>= 30), "
        "'p50_seconds', 'p95_seconds', 'max_seconds' and 'measured_at', written by observing "
        "consecutive checkpoint publications against a running sequencer. Nothing in the "
        "repository writes that file today: no producer names the path.\n"
        "  why it is not faked here: the ~60 s window of undetectable mutation is the single "
        "honest number the whole custody argument turns on. A number this test invented would "
        "be a number nobody measured."
    )
    data = json.loads(measurement.read_text(encoding="utf-8"))
    for field in ("samples", "p50_seconds", "p95_seconds", "max_seconds", "measured_at"):
        assert field in data, (
            f"K2.4 NOT MET: evidence/k2-checkpoint-cadence.json exists but is missing "
            f"{field!r}. Owner: the `sequencer` worker."
        )
    assert data["samples"] >= 30, (
        f"K2.4 NOT MET: evidence/k2-checkpoint-cadence.json records {data['samples']} "
        "cadence samples; 30 is the floor and it is not negotiable downward — a handful of "
        "samples cannot carry a p95. Owner: the `sequencer` worker."
    )
    assert "checkpoint_age_seconds" in _read("spec/custody/checks.yaml") or any(
        "checkpoint_age_seconds" in p.read_text(encoding="utf-8", errors="ignore")
        for p in (REPO_ROOT / "infra").rglob("*.tf")
    ), (
        "K2.4 NOT MET — MISSING DEFINITION: the `checkpoint_age_seconds` deadman is defined "
        "in no file under infra/ (searched infra/**/*.tf) and in no row of "
        "spec/custody/checks.yaml.\n"
        "  owner: cloud lead — docs/adr/0040-custody-red-before-green.md\n"
        "  what would make it green: a CloudWatch metric alarm named checkpoint_age_seconds "
        "declared in infra/modules or infra/envs. It FIRES from K6; it is DEFINED in K2, "
        "because an alarm invented after the incident is not an alarm."
    )


def test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry() -> None:
    """Criterion 5 — the format is frozen, and the freeze is recorded where consumers look.

    Freezing the document without a CHANGELOG entry freezes it only for people who already
    knew to read it. The wire format is the interface a third-party implementer builds
    against; the CHANGELOG is where they find out it exists.
    """
    checkpoint = _read("spec/wire/checkpoint.md")
    assert "`v1.0`" in checkpoint and "frozen" in checkpoint.lower(), (
        "K2.5 NOT MET: spec/wire/checkpoint.md does not declare itself frozen at v1.0."
    )
    changelog = _read("spec/CHANGELOG.md")
    entry = re.search(
        r"`?wire/checkpoint\.md`?[^\n]*?v1\.0|v1\.0[^\n]*?`?wire/checkpoint\.md`?",
        changelog,
    )
    assert entry, (
        "K2.5 NOT MET — MISSING ENTRY: spec/CHANGELOG.md carries no line naming "
        "`wire/checkpoint.md` at v1.0.\n"
        "  owner: kernel lead, who owns spec/CHANGELOG.md — "
        "docs/adr/0040-custody-red-before-green.md\n"
        "  the other half is already green: spec/wire/checkpoint.md declares itself frozen "
        "at `v1.0`, so this criterion is blocked on one line in a file custody does not own. "
        "Custody supplies the text and the entry lands there.\n"
        "  why it matters: until the entry exists, the freeze is documented only for people "
        "who already knew the file exists — which is everyone except the third-party "
        "implementer the format was frozen for."
    )


def test_k2_6_migration_attestation_chained_with_a_stable_fingerprint() -> None:
    """Criterion 6 — the deploy is itself evidence, and the fingerprint is reproducible.

    ``SHOW CREATE ALL TABLES`` does not guarantee intra-category ordering, so a naive schema
    fingerprint differs between two consecutive computations against an unchanged database.
    A fingerprint that is not stable cannot detect a change, which makes it worse than no
    fingerprint: it produces alarm fatigue and then gets switched off.
    """
    assert _module_available("mainline_custody_patrol"), (
        "K2.6 NOT MET — MISSING MODULE: mainline_custody_patrol is not importable, so no "
        "schema fingerprint is computed and no migration attestation is chained into the "
        "ledger. Expected at verticals/mainline/packages/mainline-custody-patrol/src/. "
        "Owner: the `witness-and-custodian` worker."
    )
    attestation = EVIDENCE / "k2-migration-attestation.json"
    assert attestation.is_file(), (
        "K2.6 NOT MET — MISSING ARTEFACT: evidence/k2-migration-attestation.json\n"
        "  owner: the `witness-and-custodian` worker — "
        "docs/adr/0040-custody-red-before-green.md\n"
        "  the computation already exists and is unwired, which is the whole of the gap: "
        "mainline_custody_patrol.fingerprint.stable_schema_fingerprint() is present and "
        "tested, and nothing calls it against a migrated cluster twice and writes the "
        "result. What would make this green is a file at that path carrying "
        "'fingerprint_run_1', 'fingerprint_run_2' and 'chained_leaf_seq'.\n"
        "  why the last key is not optional: a fingerprint that lives outside the tree is a "
        "file we could edit, so an unchained attestation attests to nothing."
    )
    data = json.loads(attestation.read_text(encoding="utf-8"))
    first, second = data.get("fingerprint_run_1"), data.get("fingerprint_run_2")
    assert first and second, (
        "K2.6 NOT MET: evidence/k2-migration-attestation.json records fewer than two "
        "consecutive fingerprint computations, so stability was asserted rather than "
        "observed. Owner: the `witness-and-custodian` worker."
    )
    assert first == second, (
        "K2.6 NOT MET: the schema fingerprint is not stable across two consecutive "
        f"computations ({first} != {second}). SHOW CREATE ALL TABLES does not guarantee "
        "intra-category ordering; normalise before hashing rather than relaxing this "
        "assertion. Owner: the `witness-and-custodian` worker."
    )
    assert data.get("chained_leaf_seq") is not None, (
        "K2.6 NOT MET: evidence/k2-migration-attestation.json carries no 'chained_leaf_seq', "
        "so the attestation is not chained into the ledger; a fingerprint that lives outside "
        "the tree is a file we could edit. Owner: the `witness-and-custodian` worker."
    )


# =======================================================================================
# Auxiliary assertions named by other normative documents. These SKIP rather than fail:
# they are not exit criteria, and exactly six failures is itself part of the deliverable.
# =======================================================================================

#: Files that normatively DEFINE the vocabulary prohibition, and must therefore be allowed
#: to quote the strings they ban. An allowlist beats a cleverer regex: it is auditable.
_VOCABULARY_RULE_DEFINITIONS = frozenset(
    {
        "spec/custody/evidentiary-map.md",
        "spec/wire/evidence-bundle.md",
        "spec/custody/threat-model.md",
        "docs/leads/custody.md",
        "tests/integration/custody/test_k2_exit.py",
        "docs/adr/0040-custody-red-before-green.md",
        "docs/adr/0041-checkpoint-wire-format.md",
    }
)

_BANNED_PHRASES = ("defence exhibit", "for litigation", "court-ready")


def test_no_litigation_vocabulary() -> None:
    """CU-12 — Evidence Act 1995 (Cth) s.69(3): a ledger built to be evidence is not a
    business record.

    Copy that leads with the exhibit is discoverable and is an admission of purpose. The
    operational sentence — *"the preconditions the database enforced before work was
    permitted to start"* — is not a softer way of saying the same thing; it is the accurate
    description, and the accurate description is the admissible one.
    """
    offenders: list[str] = []
    for root in (SPEC / "custody", SPEC / "wire", PACKAGES, REPO_ROOT / "scripts" / "custody"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".md", ".py", ".yaml", ".toml"}:
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative in _VOCABULARY_RULE_DEFINITIONS:
                continue
            lowered = path.read_text(encoding="utf-8", errors="ignore").lower()
            offenders.extend(
                f"{relative}: {phrase!r}" for phrase in _BANNED_PHRASES if phrase in lowered
            )
    assert not offenders, "CU-12 vocabulary violations:\n  " + "\n  ".join(offenders)


def test_offline_claim_matches_registry() -> None:
    """The product claim is computed from the check registry, never written in prose.

    *"Checks 1-7 and 9-16 require no access to our database and no cooperation from us"* is
    the deliverable sentence of the whole custody domain. It is derived here from the
    ``offline`` field of every check, so that adding a check which quietly needs the cluster
    breaks the build rather than the claim.
    """
    registry = _load_yaml("spec/custody/checks.yaml")
    checks = registry["checks"]
    assert [c["id"] for c in checks] == list(range(1, 17)), (
        "the registry must carry check ids 1..16 exactly once each, in order"
    )
    offline = sorted(c["id"] for c in checks if c["offline"])
    expected = sorted(set(range(1, 17)) - {8})
    assert offline == expected, (
        f"the offline check set is {offline}, but the claim sentence in checks.yaml names "
        f"{expected}. Change one and the other must change in the same commit."
    )
    assert "no access to our database" in registry["claim"]["sentence"]


def test_check_registry_totality() -> None:
    """Rule 2 of the registry: an `implemented` check must name a module AND a test."""
    registry = _load_yaml("spec/custody/checks.yaml")
    broken: list[str] = []
    for check in registry["checks"]:
        if check["status"] not in ("implemented", "implemented_but_not_adverse"):
            continue
        module_root = check["module"].split(".")[0]
        test_path = REPO_ROOT / check["test"].split("::")[0]
        if not _module_available(module_root):
            broken.append(f"check {check['id']}: module {check['module']} not importable")
        if not test_path.is_file():
            broken.append(f"check {check['id']}: test {check['test']} does not exist")
    assert not broken, (
        "checks marked implemented without a module and a test:\n  " + "\n  ".join(broken)
    )


def test_attack_registry_has_no_undetected_attack() -> None:
    """ATTACK-DEPTH, the static half: every attack names at least one detecting check."""
    attacks = _load_yaml("spec/custody/attacks.yaml")["attacks"]
    check_ids = {c["id"] for c in _load_yaml("spec/custody/checks.yaml")["checks"]}
    assert [a["id"] for a in attacks] == [f"A{n}" for n in range(1, 16)]
    for attack in attacks:
        assert attack["detected_by"], (
            f"{attack['id']} is detected by zero checks; an attack with no detector is a "
            "hole in the argument, not a row in a table"
        )
        unknown = set(attack["detected_by"]) - check_ids
        assert not unknown, f"{attack['id']} names unknown checks {sorted(unknown)}"
        assert attack["primary_detector"] in attack["detected_by"]


def test_canonicaliser_registry_is_pinned_and_retained() -> None:
    """Every shipped canonicaliser still exists and still hashes to its pin.

    Removing one would not break any code — new leaves would use the next version quite
    happily — it would make every leaf ever written under it permanently unverifiable.
    """
    registry = _load_yaml("spec/custody/canon-registry.yaml")
    entries = registry["canonicalisers"]
    assert entries, "the canonicaliser registry must never be empty"
    for entry in entries:
        source = REPO_ROOT / entry["source"]
        assert source.is_file(), (
            f"{entry['name']}: {entry['source']} is missing — removing a canonicaliser is a "
            "breaking change to evidence"
        )
        digest = hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert digest == entry["sha256"], (
            f"{entry['name']}: {entry['source']} hashes to {digest}, registry pins "
            f"{entry['sha256']}"
        )


def test_wire_vector_round_trips_through_the_canonicaliser() -> None:
    """The five leaves in ``checkpoint.md`` §7.2 are reproduced from their payloads.

    The wire document and the canonicaliser cannot drift, because this reads the canonical
    bytes out of the markdown fence and hashes them.
    """
    if not _module_available("trappoint_jcs"):
        pytest.skip("trappoint_jcs not importable in this environment")
    from trappoint_jcs.canon_v1 import canonicalise_payload

    text = _read("spec/wire/checkpoint.md")
    canon_lines = re.findall(r"^(\{\"[^\n]*\})$", text, flags=re.MULTILINE)
    leaf_hashes = re.findall(r"^leaf_hash ([0-9a-f]{64})$", text, flags=re.MULTILINE)
    assert len(canon_lines) >= 5 and len(leaf_hashes) == 5

    for canonical, expected in zip(canon_lines[:5], leaf_hashes, strict=True):
        raw = canonical.encode("utf-8")
        assert canonicalise_payload(json.loads(raw)) == raw, (
            "a canon_bytes line in checkpoint.md §7.2 is not canonical under canon_v1"
        )
        assert hashlib.sha256(b"\x00" + raw).hexdigest() == expected


def test_gate_depends_on_ledger() -> None:
    """Evidence Act s.69 — the ledger is what lets work start, not a record of it.

    Needs a live cluster: the assertion is that a merge is *refused* when the disposition
    leaf is absent, which is a database refusal and not a file on disk.
    """
    pytest.skip(
        "SKIP(no-cluster): requires a disposable single-node CockroachDB. Green from K2 "
        "onward via tests/integration/custody/nemesis/test_gate_attacks.py."
    )


def test_no_ttl_on_ledger() -> None:
    """Crimes (Document Destruction) Act 2006 (Vic) — no silent expiry of an evidentiary row."""
    pytest.skip(
        "SKIP(no-cluster): reads the live schema for row-level TTL on any ledger_* table."
    )


def test_verifier_determinism() -> None:
    """Evidence Act ss.146-147 — the device/process presumption needs an 'ordinarily'.

    ss.146 and 147 let a court presume that a device or process produced the outcome it
    ordinarily produces. *Ordinarily* is the load-bearing word, and it is a claim about
    repetition rather than about correctness: a verifier whose report varied between two
    runs over identical bytes would forfeit the presumption even if every individual verdict
    were right, because there would be no "ordinarily" to point at.

    So this runs the shipped verifier twice over the committed reference bundle, from a
    fresh parse each time, and requires the exit code, the rendered text and the JSON to be
    identical **byte for byte**. Dict iteration order, set iteration order, an unsorted
    ``json.dumps``, a timestamp in the header, a path rendered as ``PosixPath(...)`` — every
    one of those is a real way for this to fail, and each of them is the presumption gone.

    The two anti-vacuity guards below matter as much as the comparison. Two runs of a
    verifier that checked nothing are also identical, so the run has to be shown to have
    done work: at least the nine structural checks must have produced a verdict, and the
    report has to be substantial rather than an empty shell.
    """
    if not _module_available("trappoint_verify"):
        pytest.skip(
            "SKIP(not-importable): trappoint_verify is not on the path. It ships in "
            "packages/trappoint-verify and this file bootstraps that src/ directory, so "
            "this skip means the package is absent from the checkout, not merely uninstalled."
        )

    bundle_path = EVIDENCE / "reference-ledger" / "bundle.json"
    assert bundle_path.is_file(), (
        "evidence/reference-ledger/bundle.json does not exist, so there is nothing to run "
        "the verifier over twice. K2.3 covers its absence as an exit criterion."
    )

    import trappoint_verify
    from trappoint_verify.bundle import load_bundle
    from trappoint_verify.checks import VerifyOptions, load_all, registered, run_all
    from trappoint_verify.report import Verdict

    load_all()
    bound = set(registered())
    structural = {1, 2, 3, 9, 10, 13, 14, 15, 16}
    assert structural <= bound, (
        f"only checks {sorted(bound)} have a runner bound, so a determinism comparison over "
        f"this run would be a comparison over almost nothing. Missing: "
        f"{sorted(structural - bound)}."
    )

    def one_run() -> tuple[int, str, str]:
        """Load and verify from scratch. A shared parsed bundle would test less than this."""
        bundle = load_bundle(bundle_path)
        report = run_all(bundle, VerifyOptions(), tool_version=trappoint_verify.__version__)
        verdicts = {outcome.check_id for outcome in report.outcomes}
        assert structural <= verdicts, (
            f"the run produced no verdict for checks {sorted(structural - verdicts)}; a "
            "determinism assertion over a run that skipped the work is vacuous"
        )
        wrong = [
            f"check {outcome.check_id} {outcome.verdict.value} {outcome.code}"
            for outcome in report.outcomes
            if outcome.check_id in structural and outcome.verdict is not Verdict.PASS
        ]
        unclean = (
            "the committed reference bundle does not pass its own structural checks, so a "
            f"determinism comparison would compare two identical failures: {'; '.join(wrong)}"
        )
        assert not wrong, unclean
        return report.exit_code, report.render(colour=False), report.as_json_text()

    first_exit, first_text, first_json = one_run()
    second_exit, second_text, second_json = one_run()

    assert first_exit == second_exit, (
        f"two runs over identical bytes exited {first_exit} and {second_exit}. The device/"
        "process presumption under Evidence Act ss.146-147 is a claim about what the process "
        "ordinarily does, and a verifier with two answers has no 'ordinarily'."
    )
    assert first_text == second_text, (
        "two runs over identical bytes rendered different reports. First divergence: "
        + _first_divergence(first_text, second_text)
    )
    assert first_json == second_json, (
        "two runs over identical bytes serialised different JSON, so the machine-readable "
        "form is not reproducible even though the text form is. First divergence: "
        + _first_divergence(first_json, second_json)
    )
    assert len(first_text.splitlines()) > len(structural), (
        f"the report is {len(first_text.splitlines())} lines long, which is fewer lines than "
        "there are structural checks. Two identical empty reports are identical."
    )


def _first_divergence(left: str, right: str) -> str:
    """Name the first line at which two reports differ, for a message worth reading."""
    left_lines, right_lines = left.splitlines(), right.splitlines()
    for number, (one, other) in enumerate(zip(left_lines, right_lines, strict=False), start=1):
        if one != other:
            return f"line {number}: {one!r} vs {other!r}"
    return f"line counts {len(left_lines)} vs {len(right_lines)}"
