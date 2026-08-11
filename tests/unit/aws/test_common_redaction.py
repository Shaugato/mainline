# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The two safety functions in ``scripts/aws/_common.py``, tested with nothing attached.

``redact`` and ``assert_in_region`` are the fleet's only structural defences: one stops a
credential reaching a committed file, the other stops an Australian safety narrative
leaving ``ap-southeast-2``.  Both are pure functions over strings, and this module proves
them with **no AWS credentials, no network and no ``boto3`` import** — which is why
``_common.py`` imports ``boto3`` and ``psycopg`` inside the functions that need them.

Two of the tests below exist because of false positives that this fleet actually
produced, not because of imagined ones:

* :func:`test_a_sha256_digest_survives_redaction` — the account-id rule is twelve digits,
  and a 64-character hex digest contains twelve-digit runs.
* :func:`test_a_decimal_fraction_is_not_an_account_id` — the first probe artefact recorded
  an L2 norm of ``1.000000060059``.

A redactor that quietly corrupts the evidence it is protecting is worse than one that
leaks, because the leak is visible and the corruption is not.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    # `tests/unit` carries no `__init__.py`, so pytest's prepend import mode puts
    # `tests/unit` on sys.path and not the repository root. `scripts` is a namespace
    # package; this is what makes `scripts.aws._common` importable here.
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.aws._common import (  # noqa: E402 - after the sys.path bootstrap above
    REDACTED,
    REGION,
    USD_PER_1K_TOKENS,
    CostCeilingExceeded,
    ResidencyError,
    artefact,
    assert_in_region,
    check_cost_ceiling,
    ledger_total,
    redact,
    sha256_hex,
    token_ledger_entry,
    with_retry,
)

# A structurally valid but entirely fictional account id: twelve digits that are not this
# project's account. Committing the real one to a test would be the defect under test.
FAKE_ACCOUNT = "111122223333"
FAKE_ARN = f"arn:aws:iam::{FAKE_ACCOUNT}:user/mainline-dev"

# AWS's own published example credentials, used in its documentation for exactly this
# purpose. They authenticate nothing.
EXAMPLE_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
EXAMPLE_SECRET_KEY = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"

FAKE_DSN = (
    "postgresql://mainline_app:n0t-a-real-password@"
    "mainline-dev-1234.aws-ap-southeast-1.cockroachlabs.cloud:26257/"
    "mainline_demo?sslmode=verify-full"
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · redact() removes the account id
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_a_bare_account_id_is_removed() -> None:
    assert redact(FAKE_ACCOUNT) == REDACTED


def test_an_arn_loses_its_account_field_and_keeps_everything_else() -> None:
    """The ARN must stay recognisable. A redactor that eats the whole string destroys the
    evidence that the call was made by the identity we say it was."""
    scrubbed = redact(FAKE_ARN)
    assert FAKE_ACCOUNT not in scrubbed
    assert scrubbed == f"arn:aws:iam::{REDACTED}:user/mainline-dev"


def test_the_account_id_is_removed_wherever_it_is_nested() -> None:
    payload = {
        "identity": {"arn": FAKE_ARN, "account": FAKE_ACCOUNT},
        "trace": [f"caller {FAKE_ACCOUNT}", {"deep": [[FAKE_ACCOUNT]]}],
    }
    assert FAKE_ACCOUNT not in json.dumps(redact(payload))


def test_a_foundation_model_arn_has_no_account_to_lose() -> None:
    """Bedrock foundation-model ARNs carry an empty account field. Redaction must be a
    no-op on them, or every model id in every artefact becomes unreadable."""
    arn = f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
    assert redact(arn) == arn


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · redact() removes DSN passwords
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_a_dsn_password_is_removed_and_the_host_survives() -> None:
    scrubbed = redact(FAKE_DSN)
    assert "n0t-a-real-password" not in scrubbed
    assert scrubbed.startswith(f"postgresql://mainline_app:{REDACTED}@")
    assert "mainline_demo" in scrubbed, "the database name is not a secret and is evidence"


def test_a_driver_error_quoting_the_dsn_is_scrubbed() -> None:
    """``psycopg.OperationalError`` quotes the connection string on nearly every failure
    path, and that message is exactly what a program writes into an artefact."""
    message = f'connection failed: connection to server at "{FAKE_DSN}" refused'
    assert "n0t-a-real-password" not in redact(message)


def test_a_keyword_password_is_removed() -> None:
    for form in (
        "password=n0t-a-real-password",
        "password = 'n0t-a-real-password'",
        "PASSWORD=n0t-a-real-password;sslmode=require",
    ):
        assert "n0t-a-real-password" not in redact(form), form


def test_a_value_under_a_credential_key_is_removed_whatever_it_looks_like() -> None:
    payload = {"password": 12345, "dsn": FAKE_DSN, "CC_API_KEY": "CCDB1_short"}
    scrubbed = redact(payload)
    assert scrubbed == {"password": REDACTED, "dsn": REDACTED, "CC_API_KEY": REDACTED}


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · redact() removes AWS key shapes
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_an_access_key_id_is_removed() -> None:
    assert redact(EXAMPLE_ACCESS_KEY_ID) == REDACTED
    assert EXAMPLE_ACCESS_KEY_ID not in redact(f"AWS_ACCESS_KEY_ID={EXAMPLE_ACCESS_KEY_ID}")


def test_a_temporary_session_key_id_is_removed() -> None:
    assert redact("ASIAIOSFODNN7EXAMPLE") == REDACTED


def test_a_forty_character_secret_key_shape_is_removed() -> None:
    assert redact(EXAMPLE_SECRET_KEY) == REDACTED
    line = f"aws_secret_access_key={EXAMPLE_SECRET_KEY}"
    assert EXAMPLE_SECRET_KEY not in redact(line)


def test_an_all_alphanumeric_secret_is_caught_by_its_name() -> None:
    """The 40-character shape rule requires a ``+``/``/``/``=`` so it cannot eat a hex
    digest. An all-alphanumeric secret is therefore caught by its key, not its shape —
    and this test is what stops that seam from being theoretical."""
    alnum = "wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEYXX"
    assert len(alnum) == 40
    assert redact({"aws_secret_access_key": alnum}) == {"aws_secret_access_key": REDACTED}
    assert alnum not in redact(f"aws_secret_access_key = {alnum}")


def test_a_session_token_key_is_removed() -> None:
    payload = {"sessionToken": "FwoGZXIvYXdzEB//////////wEaD", "aws_session_token": "x"}
    assert redact(payload) == {"sessionToken": REDACTED, "aws_session_token": REDACTED}


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · redact() does NOT corrupt the evidence it protects
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_a_sha256_digest_survives_redaction() -> None:
    """Every artefact in this fleet is addressed by a SHA-256, and a 64-character hex
    digest contains twelve-digit runs by chance. Search until one does, then prove it."""
    for seed in range(4000):
        digest = sha256_hex(str(seed).encode("utf-8"))
        if re.search(r"(?<![0-9A-Za-z])\d{12}", digest):
            assert redact(digest) == digest, f"redaction mangled digest of {seed}"
            return
    pytest.skip("no digest in the search space contained a twelve-digit run")


def test_a_decimal_fraction_is_not_an_account_id() -> None:
    """The first artefact this fleet wrote recorded an L2 norm of ``1.000000060059``."""
    assert redact("l2 norm 1.000000060059 measured") == "l2 norm 1.000000060059 measured"


def test_token_counts_are_never_mistaken_for_credentials() -> None:
    """``inputTextTokenCount`` and ``inputTokens`` contain the word ``token``. A
    substring rule on ``token`` would delete the numbers this fleet exists to publish."""
    usage = {
        "inputTextTokenCount": 36,
        "inputTokens": 22,
        "outputTokens": 8,
        "totalTokens": 30,
        "token_ledger": [{"input_tokens": 58}],
    }
    assert redact(usage) == usage


def test_redaction_does_not_mutate_the_callers_object() -> None:
    original = {"arn": FAKE_ARN, "nested": {"account": FAKE_ACCOUNT}}
    redact(original)
    assert original["arn"] == FAKE_ARN
    assert original["nested"]["account"] == FAKE_ACCOUNT


def test_redaction_output_is_json_serialisable() -> None:
    """Everything redact() returns is bound for ``json.dump``; a value that cannot be
    serialised is a failure at the worst possible moment — after the calls were paid for."""
    payload = {"tuple": (1, 2), "set": {"b", "a"}, "bytes": b"plain", 7: "int key"}
    json.dumps(redact(payload))


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · assert_in_region
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_global_cohere_profile_is_refused() -> None:
    """The named case from the plan: on this account ``global.cohere.embed-v4:0`` is the
    *only* identifier that serves embed-v4, and taking it would trade away the residency
    guarantee ``ARCHITECTURE §10.1`` makes. The refusal is the design."""
    with pytest.raises(ResidencyError) as caught:
        assert_in_region("global.cohere.embed-v4:0")
    message = str(caught.value)
    assert "global" in message
    assert REGION in message, "a refusal must name the region it is protecting"


def test_the_au_haiku_profile_is_accepted_and_returned_unchanged() -> None:
    model_id = "au.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert assert_in_region(model_id) == model_id


@pytest.mark.parametrize(
    "model_id",
    [
        "amazon.titan-embed-text-v2:0",
        "cohere.embed-english-v3",
        "cohere.embed-v4:0",
        "au.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ],
)
def test_in_region_identifiers_are_accepted(model_id: str) -> None:
    assert assert_in_region(model_id) == model_id


@pytest.mark.parametrize(
    "model_id",
    [
        "global.cohere.embed-v4:0",
        "global.anthropic.claude-opus-4-5-20251101-v1:0",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "apac.amazon.nova-lite-v1:0",
    ],
)
def test_cross_region_routing_prefixes_are_refused(model_id: str) -> None:
    with pytest.raises(ResidencyError):
        assert_in_region(model_id)


def test_apac_is_refused_even_though_the_region_is_in_apac() -> None:
    """``ap-southeast-2`` is in APAC, so this one looks safe and is not: an ``apac.``
    profile may serve the request from Tokyo or Mumbai, and 'somewhere in Asia-Pacific' is
    not the promise made about Australian safety narratives."""
    with pytest.raises(ResidencyError):
        assert_in_region("apac.anthropic.claude-3-5-sonnet-20241022-v2:0")


@pytest.mark.parametrize("model_id", ["", None, 17])
def test_a_non_identifier_is_refused_rather_than_waved_through(model_id: object) -> None:
    with pytest.raises(ResidencyError):
        assert_in_region(model_id)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · The artefact envelope, the ledger, and the 40001 loop — all offline
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_envelope_is_deterministic_and_redacted(tmp_path: Path) -> None:
    target = tmp_path / "probe.json"
    artefact(
        target,
        {"identity": FAKE_ARN, "dsn": FAKE_DSN, "width": 1024},
        kind="unit-test",
        caveats=["written by a unit test; measures nothing"],
        synthetic=True,
    )
    text = target.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    envelope = json.loads(text)
    assert sorted(envelope) == [
        "artefact",
        "caveats",
        "generated_at",
        "generated_by",
        "kind",
        "payload",
        "region",
        "synthetic",
    ]
    assert envelope["region"] == REGION
    assert envelope["synthetic"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", envelope["generated_at"])
    assert FAKE_ACCOUNT not in text and "n0t-a-real-password" not in text
    assert list(envelope) == sorted(envelope), "keys must be sorted for a readable diff"


def test_an_unpriced_model_is_a_hole_in_the_ledger_not_a_free_one() -> None:
    entry = token_ledger_entry("amazon.nova-not-a-real-model", 1, 1000, 0)
    assert entry["priced"] is False
    assert entry["usd_total"] is None, "an unknown price must not silently become zero"
    assert ledger_total([entry])["unpriced_entries"] == 1


def test_the_titan_price_is_declared_with_its_basis() -> None:
    entry = token_ledger_entry("amazon.titan-embed-text-v2:0", 1, 1000, 0)
    assert entry["usd_total"] == pytest.approx(USD_PER_1K_TOKENS[entry["model_id"]]["input"])
    assert "declared, not measured" in entry["price_basis"]


def test_the_cost_ceiling_refuses_before_the_spend() -> None:
    assert check_cost_ceiling(0.01) == 0.01
    with pytest.raises(CostCeilingExceeded):
        check_cost_ceiling(5.0, what="a corpus pass")


def test_the_retry_loop_retries_40001_and_reports_how_often() -> None:
    class Serialization(Exception):
        sqlstate = "40001"

    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise Serialization("RETRY_SERIALIZABLE")
        return "committed"

    value, retries = with_retry(flaky, attempts=8, sleep=lambda _: None, rand=lambda: 0.5)
    assert (value, retries) == ("committed", 2)


def test_the_retry_loop_does_not_retry_a_gate_refusal() -> None:
    """``23514`` and ``P0001`` are the gate saying no. Retrying a refusal is a way of
    asking the same forbidden question eight times."""

    class Refused(Exception):
        sqlstate = "23514"

    attempts: list[int] = []

    def refused() -> None:
        attempts.append(1)
        raise Refused("gate_closed_when_issued")

    with pytest.raises(Refused):
        with_retry(refused, attempts=8, sleep=lambda _: None, rand=lambda: 0.5)
    assert len(attempts) == 1, "a refusal was retried"


def test_the_retry_loop_gives_up_after_the_attempt_budget() -> None:
    class Serialization(Exception):
        sqlstate = "40001"

    attempts: list[int] = []

    def always() -> None:
        attempts.append(1)
        raise Serialization("RETRY_SERIALIZABLE")

    with pytest.raises(Serialization):
        with_retry(always, attempts=3, sleep=lambda _: None, rand=lambda: 0.5)
    assert len(attempts) == 3


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · The committed evidence, checked from outside the program that wrote it
# ═══════════════════════════════════════════════════════════════════════════════════════

_TWELVE_DIGITS = re.compile(r"(?<![0-9A-Za-z])(?<!\d\.)\d{12}(?![0-9A-Za-z])(?!\.\d)")
_KEY_ID = re.compile(r"(?<![0-9A-Za-z])(?:AKIA|ASIA)[0-9A-Z]{16}(?![0-9A-Za-z])")
_DSN_WITH_PASSWORD = re.compile(r"postgres(?:ql)?://[^:/@\s]+:(?!<redacted>)[^@\s]+@")


def _probe_artefacts() -> list[Path]:
    return sorted((_REPO_ROOT / "evidence" / "aws" / "probe").glob("*.json"))


def test_the_probe_wrote_its_five_artefacts() -> None:
    names = {p.name for p in _probe_artefacts()}
    assert names >= {
        "bedrock-probe.json",
        "model-availability.json",
        "raw-titan-invoke.json",
        "raw-haiku-converse.json",
        "raw-cohere-refusal.json",
    }, f"missing probe artefacts; found {sorted(names)}"


def test_no_probe_artefact_carries_an_account_id_a_key_or_a_password() -> None:
    """The acceptance criterion, asserted by a test rather than by a claim in a report.

    This runs with no credentials: it does not need to know the account id to prove the
    file contains none, because the *shape* is the thing that must be absent.
    """
    offenders: list[str] = []
    for path in _probe_artefacts():
        text = path.read_text(encoding="utf-8")
        for label, pattern in (
            ("12-digit account id", _TWELVE_DIGITS),
            ("AWS access key id", _KEY_ID),
            ("DSN with a password", _DSN_WITH_PASSWORD),
        ):
            found = pattern.search(text)
            if found is not None:
                offenders.append(f"{path.name}: {label} at offset {found.start()}")
    assert not offenders, "; ".join(offenders)


def test_every_probe_artefact_states_its_region_and_its_caveats() -> None:
    for path in _probe_artefacts():
        envelope = json.loads(path.read_text(encoding="utf-8"))
        assert envelope["region"] == REGION, path.name
        assert isinstance(envelope["caveats"], list), path.name
        assert envelope["caveats"], f"{path.name} claims to have no caveats at all"
