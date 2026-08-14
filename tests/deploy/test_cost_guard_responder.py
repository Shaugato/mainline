# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Proof that the cost guard's stop is wired, obtained without applying or calling AWS.

WHY THIS FILE IS THE PROOF AND NOT A FORMALITY
==============================================

An untriggered action is indistinguishable from no action. `infra/modules/cost-guard`
describes a mechanism -- Budgets/alarms -> SNS -> responder -> `PutFunctionConcurrency(0)`
-- and a Terraform plan can only show that the resources would be created, never that the
wire carries anything. Nobody in this wave may `terraform apply`, and nobody may make a
mutating AWS call, including "just to prove the responder works".

So the proof is here: the REAL AWS Budgets SNS envelope and the REAL CloudWatch-alarm SNS
envelope, fed to the real handler, with `botocore.stub.Stubber` standing where AWS would
be. Exactly one `PutFunctionConcurrency` with `ReservedConcurrentExecutions=0` and the
function name taken from the responder's own environment; zero for a malformed message, a
foreign topic, or an alarm going back to OK.

AND THE FALSIFICATION, WHICH IS THE PART THAT MAKES THE REST MEAN ANYTHING
=========================================================================

`test_falsification__deleting_the_stop_call_turns_the_proof_red` reads the responder's
source, deletes the stop call between its two anchor comments, executes the mutated module,
and asserts that the same envelope now makes NO call -- i.e. that the assertion which
passes above FAILS against a responder that does not stop anything.

This is not decoration. The recurring defect this wave exists to close is a test that
cannot disagree with the code it tests: the permit-id near-miss, the `dict_row` 500, and
beat 4's credential-id mismatch were all cases where the test and the code shared a
constant and agreed with each other while both diverged from what was deployed. A stop
whose test would pass with the stop removed is the same defect wearing a cost-control hat.

NO NETWORK, NO CREDENTIALS, NO MUTATION
=======================================

Every client here is built from an explicit `boto3.session.Session` with fabricated
credentials and a literal region, so nothing resolves the workstation's `mainline-dev`
profile or its config files, and an autouse fixture strips the AWS environment as well.
`Stubber` intercepts before the request is sent. No test in this file can reach AWS even if
the stub were removed, because the credentials are not credentials.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import types
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parents[2]
RESPONDER_PATH = ROOT / "scripts" / "deploy" / "cost_guard_responder.py"

REGION = "ap-southeast-1"
ACCOUNT = "123456789012"  # AWS's documentation placeholder; no real account appears here.
GUARDED_FUNCTION = "mainline-demo-api"
TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT}:mainline-demo-api-guard"
FOREIGN_TOPIC_ARN = f"arn:aws:sns:{REGION}:{ACCOUNT}:someone-elses-topic"

# The two anchor comments the responder carries so this file can find the stop call
# without matching on formatting. If they ever disappear, the falsification test fails
# loudly rather than mutating nothing and passing -- a falsification check that can be
# disabled by deleting a comment is not one.
ANCHOR_BEGIN = "# FALSIFY-ANCHOR-BEGIN"
ANCHOR_END = "# FALSIFY-ANCHOR-END"


# ══════════════════════════════════════════════════════════════════════════════════════
#  THE TWO REAL ENVELOPES
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Reproduced field for field from what AWS actually publishes, because a responder tested
# against a convenient shape is a responder tested against nothing. The single detail that
# matters most is that THE TWO `Sns.Message` PAYLOADS ARE NOT THE SAME KIND OF THING:
# CloudWatch sends a JSON document, AWS Budgets sends PLAIN TEXT. A responder that calls
# `json.loads` on both loses the entire Budgets leg, silently, because the Budgets leg
# fires so rarely that nobody would notice it never worked.

CLOUDWATCH_ALARM_MESSAGE = {
    "AlarmName": "mainline-demo-api-invocations-burst",
    "AlarmDescription": (
        "STOPS THE DEMO. More than 3000 invocations of mainline-demo-api in a single "
        "60-second window."
    ),
    "AWSAccountId": ACCOUNT,
    "AlarmConfigurationUpdatedTimestamp": "2026-08-13T09:14:02.351+0000",
    "NewStateValue": "ALARM",
    "NewStateReason": (
        "Threshold Crossed: 1 out of the last 1 datapoints [41822.0 (13/08/26 12:31:00)] "
        "was greater than the threshold (3000.0) (minimum 1 datapoint for OK -> ALARM "
        "transition)."
    ),
    "StateChangeTime": "2026-08-13T12:32:41.117+0000",
    "Region": "Asia Pacific (Singapore)",
    "AlarmArn": f"arn:aws:cloudwatch:{REGION}:{ACCOUNT}:alarm:mainline-demo-api-invocations-burst",
    "OldStateValue": "OK",
    "OKActions": [],
    "AlarmActions": [TOPIC_ARN],
    "InsufficientDataActions": [],
    "Trigger": {
        "MetricName": "Invocations",
        "Namespace": "AWS/Lambda",
        "StatisticType": "Statistic",
        "Statistic": "SUM",
        "Unit": None,
        "Dimensions": [{"value": GUARDED_FUNCTION, "name": "FunctionName"}],
        "Period": 60,
        "EvaluationPeriods": 1,
        "DatapointsToAlarm": 1,
        "ComparisonOperator": "GreaterThanThreshold",
        "Threshold": 3000.0,
        "TreatMissingData": "missing",
        "EvaluateLowSampleCountPercentile": "",
    },
}

# PLAIN TEXT. Not JSON. This is what AWS Budgets publishes to SNS.
BUDGET_TEXT_MESSAGE = """AWS Budget Notification August 13, 2026
AWS Account 123456789012

Dear AWS Customer,

You requested that we alert you when the ACTUAL Cost associated with your \
mainline-demo-api-guard budget is greater than $25.00 for the current month. \
The ACTUAL Cost associated with this budget is $27.13. You can find additional details \
below and by accessing the AWS Budgets dashboard.

Budget Name: mainline-demo-api-guard
Budget Type: Cost
Budgeted Amount: $25.00
Alert Type: ACTUAL
Alert Threshold: > $25.00
ACTUAL Amount: $27.13

Go to the AWS Budgets dashboard: https://console.aws.amazon.com/billing/home#/budgets

Sincerely,
The Amazon Web Services Team
"""

BUDGET_SUBJECT = "AWS Budgets: mainline-demo-api-guard has exceeded your alert threshold"
ALARM_SUBJECT = 'ALARM: "mainline-demo-api-invocations-burst" in Asia Pacific (Singapore)'


def sns_envelope(
    message: str,
    *,
    subject: str = "",
    topic_arn: str = TOPIC_ARN,
    records: int = 1,
) -> dict:
    """Wrap a message body in the SNS-to-Lambda event envelope AWS actually delivers."""
    record = {
        "EventSource": "aws:sns",
        "EventVersion": "1.0",
        "EventSubscriptionArn": f"{topic_arn}:0b6941ee-2e0f-4b52-9f2a-2d7c1f8a5f31",
        "Sns": {
            "Type": "Notification",
            "MessageId": "8c1e2b52-5f3a-52f8-9a4e-6f3f2a51c9b7",
            "TopicArn": topic_arn,
            "Subject": subject,
            "Message": message,
            "Timestamp": "2026-08-13T12:32:41.183Z",
            "SignatureVersion": "1",
            "Signature": "EXAMPLEpH+..",
            "SigningCertUrl": (
                "https://sns.ap-southeast-1.amazonaws.com/"
                "SimpleNotificationService-0000000000000000000000.pem"
            ),
            "UnsubscribeUrl": (
                f"https://sns.{REGION}.amazonaws.com/?Action=Unsubscribe&SubscriptionArn={topic_arn}"
            ),
            "MessageAttributes": {},
        },
    }
    return {"Records": [json.loads(json.dumps(record)) for _ in range(records)]}


def alarm_envelope(state: str = "ALARM", *, old: str = "OK") -> dict:
    """A CloudWatch-alarm envelope with the state transition set."""
    message = dict(CLOUDWATCH_ALARM_MESSAGE)
    message["NewStateValue"] = state
    message["OldStateValue"] = old
    return sns_envelope(json.dumps(message), subject=ALARM_SUBJECT)


def budget_envelope() -> dict:
    """The AWS Budgets envelope, with its plain-text body."""
    return sns_envelope(BUDGET_TEXT_MESSAGE, subject=BUDGET_SUBJECT)


class FakeContext:
    """The two attributes this responder reads off a Lambda context object."""

    aws_request_id = "5b0f3c1e-9c4f-4a8a-8a1b-1f0f7a2c3d4e"
    function_name = "mainline-demo-api-guard-responder"


# ══════════════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _hermetic_aws_env(monkeypatch, tmp_path):
    """Make it impossible for anything in this file to reach a real AWS account.

    The workstation has a live `mainline-dev` profile. Three things are done about it, and
    all three, because this file is about a MUTATING call and a test that reached AWS by
    accident would be the worst possible way to discover a gap:

    * the profile selectors are removed;
    * the credential and config files are pointed at paths inside `tmp_path` that do not
      exist, so nothing on disk is read at all;
    * fabricated credentials and a literal region are published, so client construction
      succeeds without discovering anything.

    `Stubber` then intercepts before the request is sent. Even with the stub removed, the
    credentials are not credentials.
    """
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.fixture
def responder(monkeypatch):
    """The real module, loaded from its real path, with the real environment published."""
    monkeypatch.setenv("MAINLINE_GUARDED_FUNCTION_NAME", GUARDED_FUNCTION)
    monkeypatch.setenv("MAINLINE_COST_GUARD_TOPIC_ARN", TOPIC_ARN)
    return load_responder()


def load_responder(source: str | None = None, name: str = "cost_guard_responder_under_test"):
    """Load the responder from disk, or from mutated source, as a fresh module object.

    `importlib` rather than a package import: `scripts/` is not a package (there is no
    `scripts/__init__.py`), and the falsification test needs to execute a source string
    that never touches the filesystem.
    """
    if source is None:
        spec = importlib.util.spec_from_file_location(name, RESPONDER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    module = types.ModuleType(name)
    module.__file__ = str(RESPONDER_PATH)
    exec(compile(source, str(RESPONDER_PATH), "exec"), module.__dict__)  # noqa: S102
    return module


def lambda_client():
    """A Lambda client that cannot reach AWS.

    Its credentials come from the fabricated environment `_hermetic_aws_env` publishes, so
    there is no credential-shaped literal in this call and nothing on this workstation is
    consulted.
    """
    return boto3.session.Session(region_name=REGION).client("lambda")


def expecting_one_stop(client, function_name: str = GUARDED_FUNCTION):
    """A Stubber primed with exactly ONE PutFunctionConcurrency(0) and nothing else.

    This is what makes "exactly one" checkable in both directions:

      zero calls -> the queued response is still pending and
                    `assert_no_pending_responses()` fails
      two calls  -> the second finds an empty queue and botocore raises
                    `UnStubbedResponseError`

    The expected parameters are asserted by the Stubber itself, so the function name and
    the reserved value are part of the contract rather than something a later assertion
    might forget to check.
    """
    stubber = Stubber(client)
    stubber.add_response(
        "put_function_concurrency",
        {"ReservedConcurrentExecutions": 0},
        {"FunctionName": function_name, "ReservedConcurrentExecutions": 0},
    )
    return stubber


def expecting_no_call(client):
    """A Stubber with an EMPTY queue: any call at all raises."""
    return Stubber(client)


# ══════════════════════════════════════════════════════════════════════════════════════
#  THE STOP FIRES — one call, right arguments, for each real envelope
# ══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("label", "event"),
    [
        ("cloudwatch-alarm", alarm_envelope()),
        ("aws-budgets-plain-text", budget_envelope()),
    ],
)
def test_real_envelope_makes_exactly_one_stop(responder, label, event):
    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        result = responder.handler(event, FakeContext(), lambda_client=client)
        # Fails if the handler made NO call: the queued response is still pending.
        stubber.assert_no_pending_responses()

    assert result["stopped"] is True, label
    assert result["function_name"] == GUARDED_FUNCTION
    assert result["reserved_concurrent_executions"] == 0


def test_budget_notification_is_plain_text_not_json(responder):
    """The detail a responder written from memory gets wrong, asserted directly.

    If AWS Budgets sent JSON this assertion would be wrong and the responder's text branch
    would be dead code. It sends text, `json.loads` raises on it, and the branch that
    catches that raise is the whole Budgets leg.
    """
    with pytest.raises(json.JSONDecodeError):
        json.loads(BUDGET_TEXT_MESSAGE)

    subject_only = sns_envelope("Budgeted amount exceeded.", subject=BUDGET_SUBJECT)
    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        result = responder.handler(subject_only, FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()
    assert result["stopped"] is True


def test_reserved_value_is_zero_and_never_minus_one(responder):
    """-1 is a Terraform sentinel; PutFunctionConcurrency's minimum is 0 and rejects -1.

    The Stubber asserts the parameters, so a responder that sent -1 would fail here rather
    than at 3 a.m. against a real API that refuses it.
    """
    assert responder.STOPPED_CONCURRENCY == 0

    client = lambda_client()
    stubber = Stubber(client)
    stubber.add_response(
        "put_function_concurrency",
        {"ReservedConcurrentExecutions": 0},
        {"FunctionName": GUARDED_FUNCTION, "ReservedConcurrentExecutions": 0},
    )
    with stubber:
        responder.handler(alarm_envelope(), FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()


def test_function_name_comes_from_the_environment_not_from_the_message(monkeypatch):
    """The alarm envelope names `mainline-demo-api` in its Trigger dimensions.

    The responder must NOT read it from there. A publisher who could name the function in
    the message could aim the stop at any function the role could reach -- which is one, by
    construction, but the principle is that the target comes from deployment configuration
    and never from a payload.
    """
    monkeypatch.setenv("MAINLINE_GUARDED_FUNCTION_NAME", "some-other-function")
    monkeypatch.setenv("MAINLINE_COST_GUARD_TOPIC_ARN", TOPIC_ARN)
    module = load_responder()

    client = lambda_client()
    stubber = expecting_one_stop(client, function_name="some-other-function")
    with stubber:
        result = module.handler(alarm_envelope(), FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()

    assert result["function_name"] == "some-other-function"


def test_many_breaching_records_still_make_exactly_one_call(responder):
    """Idempotent within one event: five records that all say stop produce one call.

    A per-record loop that called on each would make five identical calls, four of which
    are pure control-plane throttle risk at the exact moment the account is contended.
    """
    event = sns_envelope(json.dumps(CLOUDWATCH_ALARM_MESSAGE), subject=ALARM_SUBJECT, records=5)
    assert len(event["Records"]) == 5

    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        result = responder.handler(event, FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()
    assert result["stopped"] is True


def test_a_mixed_event_stops_if_any_record_breaches(responder):
    """One breaching record among refusable ones still stops, and still stops once."""
    ok_record = sns_envelope(
        json.dumps({**CLOUDWATCH_ALARM_MESSAGE, "NewStateValue": "OK"}), subject=ALARM_SUBJECT
    )["Records"][0]
    breach_record = alarm_envelope()["Records"][0]
    foreign_record = sns_envelope(BUDGET_TEXT_MESSAGE, topic_arn=FOREIGN_TOPIC_ARN)["Records"][0]

    event = {"Records": [ok_record, foreign_record, breach_record]}

    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        result = responder.handler(event, FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()
    assert result["stopped"] is True


# ══════════════════════════════════════════════════════════════════════════════════════
#  THE STOP DOES NOT FIRE — and "does not fire" means no call was even attempted
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Every test below runs against a Stubber with an EMPTY queue. A responder that called
# anything at all raises `UnStubbedResponseError` and the test goes red, so these prove
# "made no call", not merely "returned stopped=False".


@pytest.mark.parametrize("state", ["OK", "INSUFFICIENT_DATA"])
def test_alarm_not_in_alarm_state_makes_no_call(responder, state):
    client = lambda_client()
    with expecting_no_call(client):
        result = responder.handler(
            alarm_envelope(state=state, old="ALARM"), FakeContext(), lambda_client=client
        )
    assert result["stopped"] is False
    assert any(state in reason for reason in result["reasons"])


@pytest.mark.parametrize(
    ("label", "event"),
    [
        (
            "alarm-on-a-foreign-topic",
            sns_envelope(
                json.dumps(CLOUDWATCH_ALARM_MESSAGE),
                subject=ALARM_SUBJECT,
                topic_arn=FOREIGN_TOPIC_ARN,
            ),
        ),
        (
            "budget-on-a-foreign-topic",
            sns_envelope(BUDGET_TEXT_MESSAGE, subject=BUDGET_SUBJECT, topic_arn=FOREIGN_TOPIC_ARN),
        ),
    ],
)
def test_foreign_topic_makes_no_call(responder, label, event):
    """A Lambda can be subscribed to a second topic by anyone holding `sns:Subscribe`.

    The topic check is what makes such a subscription inert. Without it, creating an SNS
    topic -- an unprivileged act -- would be enough to stop the demo.
    """
    client = lambda_client()
    with expecting_no_call(client):
        result = responder.handler(event, FakeContext(), lambda_client=client)
    assert result["stopped"] is False, label
    assert any("not the guard topic" in reason for reason in result["reasons"])


def test_foreign_topic_arn_is_not_echoed_into_the_result(responder):
    """The refusal reason must not quote an attacker-chosen ARN back into the log."""
    event = sns_envelope(BUDGET_TEXT_MESSAGE, topic_arn=FOREIGN_TOPIC_ARN)
    client = lambda_client()
    with expecting_no_call(client):
        result = responder.handler(event, FakeContext(), lambda_client=client)
    assert FOREIGN_TOPIC_ARN not in json.dumps(result)


@pytest.mark.parametrize(
    ("label", "event"),
    [
        ("not-a-dict", ["Records"]),
        ("no-records-key", {"Message": "hello"}),
        ("records-not-a-list", {"Records": {"Sns": {}}}),
        ("records-empty", {"Records": []}),
        ("record-not-a-dict", {"Records": ["nope"]}),
        ("no-sns-object", {"Records": [{"EventSource": "aws:sns"}]}),
        ("sns-not-a-dict", {"Records": [{"Sns": "nope"}]}),
        ("empty-message", sns_envelope("")),
        ("whitespace-message", sns_envelope("   \n\t  ")),
        ("message-not-a-string", {"Records": [{"Sns": {"TopicArn": TOPIC_ARN, "Message": 17}}]}),
        ("json-array-message", sns_envelope("[1, 2, 3]")),
        ("json-object-that-is-neither", sns_envelope('{"hello": "world"}')),
        ("alarm-json-missing-state", sns_envelope('{"AlarmName": "x"}')),
        ("prose-that-is-not-a-budget", sns_envelope("the quick brown fox jumps over it")),
    ],
)
def test_malformed_message_makes_no_call(responder, label, event):
    client = lambda_client()
    with expecting_no_call(client):
        result = responder.handler(event, FakeContext(), lambda_client=client)
    assert result["stopped"] is False, label


def test_missing_environment_refuses_rather_than_guessing(monkeypatch):
    """A responder that guesses a function name can stop the wrong function.

    This raises rather than returning quietly: it is a DEPLOYMENT defect, fixed by an
    operator and not by waiting, and a responder that silently did nothing because it did
    not know which function to stop is the exact control-that-looks-present-and-is-not
    this module exists to close.
    """
    monkeypatch.delenv("MAINLINE_GUARDED_FUNCTION_NAME", raising=False)
    monkeypatch.setenv("MAINLINE_COST_GUARD_TOPIC_ARN", TOPIC_ARN)
    module = load_responder()

    client = lambda_client()
    with (
        expecting_no_call(client),
        pytest.raises(RuntimeError, match="MAINLINE_GUARDED_FUNCTION_NAME"),
    ):
        module.handler(alarm_envelope(), FakeContext(), lambda_client=client)

    # And an empty string is the same defect as an absent one: Terraform publishing "" and
    # Terraform publishing nothing must not produce two different behaviours.
    monkeypatch.setenv("MAINLINE_GUARDED_FUNCTION_NAME", GUARDED_FUNCTION)
    monkeypatch.setenv("MAINLINE_COST_GUARD_TOPIC_ARN", "   ")
    module = load_responder()
    with (
        expecting_no_call(client),
        pytest.raises(RuntimeError, match="MAINLINE_COST_GUARD_TOPIC_ARN"),
    ):
        module.handler(alarm_envelope(), FakeContext(), lambda_client=client)


# ══════════════════════════════════════════════════════════════════════════════════════
#  IT CAN NEVER RESTORE
# ══════════════════════════════════════════════════════════════════════════════════════


def test_source_never_calls_delete_function_concurrency():
    """Restore is a human running `kill_switch.sh --restore`, never this program.

    Asserted on the boto3 METHOD name (`delete_function_concurrency`), not on the API name
    (`DeleteFunctionConcurrency`), because the module docstring discusses the API at length
    and must be free to keep doing so. The IAM role carries an explicit Deny on the same
    action, so this is the second of three enforcements, not the only one.
    """
    source = RESPONDER_PATH.read_text(encoding="utf-8")
    assert "delete_function_concurrency" not in source

    # And it never sends the Terraform sentinel either. `PutFunctionConcurrency`'s minimum
    # is 0; a put of -1 is refused by the API, so a responder that tried it would fail at
    # exactly the moment it was needed.
    assert "ReservedConcurrentExecutions=-1" not in source
    assert "ReservedConcurrentExecutions=STOPPED_CONCURRENCY" in source


def test_module_does_not_import_boto3_at_module_scope():
    """A responder that imports boto3 at module scope cannot be tested without it.

    It also pays the import cost on a code path that was handed a client. The import lives
    inside `_default_client`, and this asserts it structurally rather than by reading.
    """
    tree = ast.parse(RESPONDER_PATH.read_text(encoding="utf-8"))
    top_level = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    imported = {
        alias.name.split(".")[0] for node in top_level for alias in getattr(node, "names", [])
    }
    assert "boto3" not in imported
    assert "botocore" not in imported


# ══════════════════════════════════════════════════════════════════════════════════════
#  THE FALSIFICATION — mandatory, and it runs every time
# ══════════════════════════════════════════════════════════════════════════════════════


def _mutated_source_without_the_stop() -> str:
    """Return the responder's source with the stop call deleted between its anchors."""
    source = RESPONDER_PATH.read_text(encoding="utf-8")

    # If the anchors are gone, FAIL. A falsification check that can be neutralised by
    # deleting a comment is not a falsification check.
    assert ANCHOR_BEGIN in source, (
        f"{RESPONDER_PATH} no longer carries {ANCHOR_BEGIN}. That comment is how this test "
        "finds the stop call in order to delete it. Restore the anchors, or this file's "
        "falsification proves nothing."
    )
    assert ANCHOR_END in source, f"{RESPONDER_PATH} no longer carries {ANCHOR_END}."

    head, _, rest = source.partition(ANCHOR_BEGIN)
    _, _, tail = rest.partition(ANCHOR_END)
    mutated = f"{head}pass{tail}"

    assert "put_function_concurrency" not in mutated, (
        "The mutation did not remove the stop call, so the falsification below would pass "
        "for the wrong reason. The call must live BETWEEN the two anchors and nowhere else."
    )
    return mutated


def test_falsification__deleting_the_stop_call_turns_the_proof_red(responder):
    """THE MANDATORY CHECK. Remove the stop, and the proof above must fail.

    Same envelope, same Stubber, same assertion. Against the real module the queued
    response is consumed and `assert_no_pending_responses()` is silent; against a module
    whose stop call has been deleted the response is still pending and it raises.

    That difference is the entire evidential value of this file. Without it, every
    assertion above would pass just as happily against a responder that returns
    `stopped=True` and calls nothing -- which is precisely what a documented-but-not-
    implemented bound looks like from the inside.
    """
    mutant = load_responder(_mutated_source_without_the_stop(), name="cost_guard_responder_mutant")

    # The real module: the response is consumed, so nothing is pending.
    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        responder.handler(alarm_envelope(), FakeContext(), lambda_client=client)
        stubber.assert_no_pending_responses()

    # The mutant: the identical assertion must now FAIL.
    mutant_client = lambda_client()
    mutant_stubber = expecting_one_stop(mutant_client)
    with mutant_stubber:
        mutant.handler(alarm_envelope(), FakeContext(), lambda_client=mutant_client)
        with pytest.raises(AssertionError):
            mutant_stubber.assert_no_pending_responses()


def test_falsification__the_budget_leg_is_falsifiable_too(responder):
    """The Budgets envelope, against the same mutant. Both legs, not just the alarm one.

    THIS TEST USED TO BE ONE-SIDED, AND A CONTROLLED EXPERIMENT CAUGHT IT. It took
    `responder` only via `@pytest.mark.usefixtures` -- for the environment, not the
    module -- and then asserted solely about the MUTANT. A mutant makes no call whether or
    not the real responder makes one, so the test passed identically against a healthy
    responder and against one whose stop had been deleted.

    MEASURED 2026-08-13, W4: with the stop call neutered in
    `scripts/deploy/cost_guard_responder.py` between its anchors and the whole module
    re-run, nine node ids in this file went red and THIS ONE STAYED GREEN. A falsification
    check that cannot go red when the thing it falsifies is removed is not one -- it is the
    same "a control that looks present and is not" shape the cost-guard module exists to
    close, wearing a test's hat.

    So it is now two-sided like its sibling above: the REAL module must consume the queued
    response for a Budgets envelope, and the mutant must leave it pending. The first half
    is what a deleted stop breaks.
    """
    mutant = load_responder(
        _mutated_source_without_the_stop(), name="cost_guard_responder_mutant_budget"
    )

    # THE HALF THAT WAS MISSING. Against the real module the Budgets envelope consumes the
    # queued response, so nothing is pending. Delete the stop and this line raises.
    real_client = lambda_client()
    real_stubber = expecting_one_stop(real_client)
    with real_stubber:
        real_result = responder.handler(budget_envelope(), FakeContext(), lambda_client=real_client)
        real_stubber.assert_no_pending_responses()
    assert real_result["stopped"] is True

    # And the mutant, on the identical envelope and the identical assertion, must fail.
    client = lambda_client()
    stubber = expecting_one_stop(client)
    with stubber:
        result = mutant.handler(budget_envelope(), FakeContext(), lambda_client=client)
        with pytest.raises(AssertionError):
            stubber.assert_no_pending_responses()
    # The mutant still CLAIMS it stopped, which is exactly why claiming is not proof.
    assert result["stopped"] is True
