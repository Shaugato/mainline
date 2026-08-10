# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Residency: ``au.*`` or refuse to serve, resolved at start-up and never hard-coded.

§10.1 and decisions A3/AR-2. No test here needs AWS: the resolver takes an injected
client, so the *logic* that decides whether a profile is Australian is covered offline
and the only thing a live credential would add is the network round trip.

The honest statement this suite protects (F5, and repeated in the README): inference
runs in Australia; on the free demo tier the database is in Singapore, so end-to-end
Australian residency is FALSE for that deployment and is never claimed.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mainline_agentkit import (
    AgentkitSettings,
    ResidencyRefused,
    TransportUnavailable,
    assert_australian_profile,
    resolve_inference_profile,
    select_transport,
)

AU_ARN = "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/au.anthropic.claude-opus-5"


class FakeBedrock:
    """A ``bedrock`` control-plane client that paginates, for the resolver."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def list_inference_profiles(self, **kwargs):
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def _page(ids, next_token=None):
    page = {
        "inferenceProfileSummaries": [
            {
                "inferenceProfileId": profile_id,
                "inferenceProfileArn": (
                    f"arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/{profile_id}"
                ),
                "status": "ACTIVE",
            }
            for profile_id in ids
        ]
    }
    if next_token:
        page["nextToken"] = next_token
    return page


@pytest.mark.parametrize(
    "identifier",
    ["au.anthropic.claude-opus-5", AU_ARN],
)
def test_australian_identifiers_are_accepted(identifier):
    assert assert_australian_profile(identifier) == "au.anthropic.claude-opus-5"


@pytest.mark.parametrize(
    "identifier",
    [
        "global.anthropic.claude-opus-5",
        "apac.anthropic.claude-opus-5",
        "us.anthropic.claude-opus-5",
        "eu.anthropic.claude-opus-5",
        "arn:aws:bedrock:us-east-1:1:inference-profile/us.anthropic.claude-opus-5",
    ],
)
def test_cross_region_profiles_are_refused(identifier):
    with pytest.raises(ResidencyRefused) as excinfo:
        assert_australian_profile(identifier)
    assert "cross-region profile prefix" in excinfo.value.reason


def test_a_bare_foundation_model_id_is_refused():
    # Bedrock would accept it. We do not: a bare model id bypasses the inference
    # profile that the VPC-endpoint policy enumerates, so the control would still be in
    # the policy and no longer in the path.
    with pytest.raises(ResidencyRefused, match="bypasses"):
        assert_australian_profile("anthropic.claude-opus-5-v1:0")


def test_an_arn_that_is_not_an_inference_profile_is_refused():
    with pytest.raises(ResidencyRefused, match="does not name an inference profile"):
        assert_australian_profile(
            "arn:aws:bedrock:ap-southeast-2:1:foundation-model/au.anthropic.claude-opus-5"
        )


def test_an_empty_identifier_is_refused():
    with pytest.raises(ResidencyRefused, match="empty"):
        assert_australian_profile("")


def test_the_resolver_paginates_and_pins_the_australian_arn():
    client = FakeBedrock(
        [
            _page(["global.anthropic.claude-opus-5", "us.anthropic.claude-sonnet-5"], "more"),
            _page(["apac.anthropic.claude-opus-5", "au.anthropic.claude-opus-5"]),
        ]
    )
    resolved = resolve_inference_profile("claude-opus-5", client=client)
    assert resolved.profile_id == "au.anthropic.claude-opus-5"
    assert resolved.profile_arn == AU_ARN
    assert resolved.region == "ap-southeast-2"
    assert len(client.calls) == 2
    assert client.calls[1]["nextToken"] == "more"


def test_no_australian_profile_is_a_refusal_naming_ar2():
    client = FakeBedrock([_page(["global.anthropic.claude-opus-6"])])
    with pytest.raises(ResidencyRefused) as excinfo:
        resolve_inference_profile("claude-opus-6", client=client)
    assert "AR-2" in str(excinfo.value)


def test_the_live_provider_needs_two_locks_open():
    with pytest.raises(TransportUnavailable, match="MAINLINE_AGENT_ALLOW_LIVE"):
        select_transport(AgentkitSettings(provider="bedrock"))


def test_an_unknown_provider_is_refused():
    with pytest.raises(TransportUnavailable, match="unknown provider"):
        select_transport(AgentkitSettings(provider="ollama"))


def test_the_cassette_provider_refuses_to_guess_a_store():
    with pytest.raises(TransportUnavailable, match="never falls through"):
        select_transport(AgentkitSettings(provider="cassette", cassette_dir=None))


def test_replaying_a_missing_store_says_so(tmp_path: Path):
    with pytest.raises(TransportUnavailable, match="does not exist"):
        select_transport(
            AgentkitSettings(provider="cassette", cassette_dir=tmp_path / "nope"),
        )


# ── the offline path reaches no AWS SDK, measured in a process of its own ───────────
#
# WHY THIS IS A SUBPROCESS, AND WHAT THE OLD IN-PROCESS ASSERTION ACTUALLY MEASURED.
#
# This test used to be two lines: `assert "boto3" not in sys.modules`. That is not a
# statement about `mainline_agentkit`. It is a statement about every test that has run
# in the same interpreter before it, and on 2026-08-10 it started failing for a reason
# that has nothing to do with this package. Measured, with a `sys.meta_path` tracer over
# the full `pytest --crdb=none tests` run:
#
#   tests/unit/recall_providers/test_offline_guarantee.py:62
#     test_a_live_judge_reports_unreachable_rather_than_guessing -> get_judge_provider()
#   verticals/.../mainline_recall_agent/providers/registry.py:135 -> resolve_inference_profile()
#   verticals/.../mainline_recall_agent/providers/resolve.py:184  -> import boto3
#
# That is a DIFFERENT package's live path, lazily imported exactly as it should be, and
# driven on purpose by a test proving it reports `unreachable` rather than guessing. It
# leaves `boto3` in `sys.modules` for the remaining ~2 000 tests, and `packages/` sorts
# after `tests/`, so this file was told the SDK had leaked and blamed itself. Grepping
# every module-scope import in the tree finds none: the accusation was false and the
# instrument produced it.
#
# So the claim is measured where the claim lives — in a fresh interpreter that imports
# `mainline_agentkit`, drives the cassette path end to end, and reports what it pulled
# in. It cannot be polluted by a sibling suite, it cannot pass because nothing ran, and
# when it fails it NAMES THE FILE AND LINE that asked for the SDK. This is the shape
# `packages/trappoint-ledger/tests/test_signer.py` already uses for the same claim.

_OFFLINE_PROBE = r'''
import importlib
import importlib.abc
import json
import sys
import traceback

AWS_ROOTS = ("boto3", "botocore")
OFFENCES = []


def _asked_for_it():
    """The first frame outside the import machinery — i.e. the file that did it."""
    for frame in reversed(traceback.extract_stack()[:-2]):
        name = frame.filename.replace("\\", "/")
        if name.startswith("<frozen importlib") or "/importlib/" in name:
            continue
        return {
            "file": frame.filename,
            "line": frame.lineno,
            "function": frame.name,
            "source": (frame.line or "").strip(),
        }
    return {"file": "<unknown>", "line": 0, "function": "<unknown>", "source": ""}


class Tripwire(importlib.abc.MetaPathFinder):
    """Refuse the AWS SDK, and record who asked.

    Refusing rather than merely observing matters twice over. A module-scope import
    fails loudly with a traceback instead of silently succeeding, and an import wrapped
    in `try: ... except ImportError:` — which would defeat a check that only looked at
    `sys.modules` afterwards — is still recorded here.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in AWS_ROOTS:
            return None
        OFFENCES.append({"module": fullname, "importer": _asked_for_it()})
        raise ImportError(
            fullname + " is refused on the offline path by the MAINLINE residency probe"
        )


sys.meta_path.insert(0, Tripwire())
for _name in [n for n in sys.modules if n.split(".")[0] in AWS_ROOTS]:
    del sys.modules[_name]

steps = []
died = None


def drive_the_offline_path():
    """Everything a cassette run touches, in the order a caller touches it."""
    import mainline_agentkit as kit
    steps.append("import mainline_agentkit (and every module it re-exports)")

    import make_cassettes as recipes
    steps.append("import the committed cassette recipes")

    settings = kit.AgentkitSettings.from_env({})
    assert settings.provider == "cassette", settings.provider
    steps.append("AgentkitSettings.from_env({}) -> provider=" + settings.provider)

    offline = kit.AgentkitSettings(
        provider="cassette", cassette_dir=recipes.CASSETTE_DIR, cassette_mode="replay"
    )
    transport = kit.select_transport(offline)
    steps.append("select_transport -> " + type(transport).__name__)

    result = kit.quarantined_call(
        kit.TRIAGE,
        recipes.DOC_PROCEDURE,
        recipes.CTX_SITE,
        transport=transport,
        model_id=recipes.MODEL_ID,
        sentinel=recipes.SENTINEL,
    )
    assert result.attempts == 1, result.attempts
    steps.append("quarantined_call replayed a cassette in " + str(result.attempts) + " attempt")

    kit.boot_runtime(settings=offline, inference_profile_arn=recipes.MODEL_ID)
    steps.append("boot_runtime -> serving=" + str(kit.is_serving()))
    kit.shutdown_runtime()
    steps.append("shutdown_runtime -> serving=" + str(kit.is_serving()))


# The tripwire RAISES, so a module-scope `import boto3` anywhere on this chain kills the
# run here. The verdict is still printed — a probe that died without saying why would
# tell the next reader nothing, and OFFENCES already holds the file that did it.
try:
    drive_the_offline_path()
except Exception:
    died = traceback.format_exc()

leaked = sorted(n for n in sys.modules if n.split(".")[0] in AWS_ROOTS)
offences = list(OFFENCES)

# ANTI-VACUITY, in the same process and on every run: prove the tripwire is armed by
# tripping it deliberately. Without this the whole probe could report a clean offline
# path because the finder was never consulted.
OFFENCES.clear()
try:
    importlib.import_module("boto3")
    self_test = {"tripped": False, "importer": None}
except ImportError:
    self_test = {
        "tripped": bool(OFFENCES),
        "importer": OFFENCES[0]["importer"] if OFFENCES else None,
    }

print(
    "MAINLINE-RESIDENCY-VERDICT "
    + json.dumps(
        {
            "steps": steps,
            "leaked": leaked,
            "offences": offences,
            "self_test": self_test,
            "died": died,
        }
    )
)
'''


def _run_offline_probe() -> dict:
    """Drive the offline path in a fresh interpreter and return its verdict."""
    tests_dir = Path(__file__).resolve().parent
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tests_dir.parent / "src"), str(tests_dir), *[entry for entry in sys.path if entry]]
    )
    # A fixed interpreter and an in-repo script constant: no shell, no user input.
    completed = subprocess.run(
        [sys.executable, "-c", _OFFLINE_PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=90,
        check=False,
    )
    marker = "MAINLINE-RESIDENCY-VERDICT "
    for line in completed.stdout.splitlines():
        if line.startswith(marker):
            return json.loads(line[len(marker) :])
    raise AssertionError(
        "the offline residency probe produced no verdict, which means it died before it "
        "finished driving the cassette path. If the traceback below ends in an ImportError "
        "for boto3 or botocore, the file named in it is the one that moved the AWS SDK onto "
        f"the offline path.\n--- exit {completed.returncode} ---\n"
        f"--- stdout ---\n{completed.stdout}\n--- stderr ---\n{completed.stderr}"
    )


def test_the_offline_path_imports_no_aws_sdk():
    """PL-1: a completed offline run must never have pulled the AWS SDK into memory.

    ``boto3`` is imported inside two functions in ``transport.py``, both on the live path
    only. ``mainline-boundary``'s E3 SBOM scan reads this import graph and the submission
    is about to lean on it, so the claim is measured rather than asserted about.
    """
    verdict = _run_offline_probe()

    # ORDER MATTERS. The offence report names the file; every other assertion here is a
    # weaker statement about the same run, so a planted module-scope import must be read
    # out as "this file did it" and never as "the probe completed no steps".
    assert verdict["self_test"]["tripped"] is True, (
        "the probe's own tripwire did not fire when it deliberately imported boto3, so "
        "this run measured nothing at all: "
        f"{json.dumps(verdict['self_test'], indent=2)}"
    )

    offenders = "\n".join(
        f"  {entry['module']} <- {entry['importer']['file']}:{entry['importer']['line']} "
        f"in {entry['importer']['function']} | {entry['importer']['source']}"
        for entry in verdict["offences"]
    )
    assert not verdict["offences"], (
        "the AWS SDK was requested while driving MAINLINE's offline path. The lazy import "
        "that keeps it off the cassette path has been moved to module scope, or a new "
        "module-scope import has been added. THE FILE THAT ASKED FOR IT:\n"
        f"{offenders}\n"
        f"offline steps completed before the request: {verdict['steps']}\n"
        f"{verdict['died'] or ''}"
    )
    assert not verdict["leaked"], (
        "the offline path finished with the AWS SDK resident in sys.modules: "
        f"{verdict['leaked']}. The tripwire recorded no request, so it arrived by some "
        "route other than an import statement."
    )
    assert verdict["died"] is None, (
        "the offline path did not complete, so this run proved nothing about the AWS SDK. "
        f"steps completed: {verdict['steps']}\n{verdict['died']}"
    )
    assert len(verdict["steps"]) == 7, (
        "the probe finished without driving the whole offline path, so a clean verdict "
        f"would be vacuous. steps: {verdict['steps']}"
    )


def test_settings_default_to_the_offline_provider():
    settings = AgentkitSettings.from_env({})
    assert settings.provider == "cassette"
    assert settings.allow_live is False
    assert settings.ar1_enabled is False
    assert settings.region == "ap-southeast-2"


def test_settings_read_the_documented_environment_variables(cassette_dir):
    settings = AgentkitSettings.from_env(
        {
            "MAINLINE_AGENT_PROVIDER": "BEDROCK",
            "MAINLINE_AGENT_ALLOW_LIVE": "1",
            "MAINLINE_AR1_FALLBACK": "1",
            "MAINLINE_BEDROCK_REGION": "ap-southeast-2",
            "MAINLINE_CASSETTE_DIR": str(cassette_dir),
            "MAINLINE_WARM_TIMEOUT_S": "5",
        }
    )
    assert settings.provider == "bedrock"
    assert settings.allow_live is True
    assert settings.ar1_enabled is True
    assert settings.warm_timeout_s == 5.0
    assert settings.cassette_dir == cassette_dir
