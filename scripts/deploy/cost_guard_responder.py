#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The cost-guard responder: the one thing in this repository that can stop the demo.

WHY THIS FILE EXISTS
====================

The demo origin is a Lambda Function URL with ``authorization_type = NONE`` -- the
founder's chosen posture, not an oversight. Before this file, the worst case was
**USD 33,250 per 30 days** and the only bound in force was an AWS account concurrency
quota of 10 that nobody chose and that AWS marks ``Adjustable: true``. Every other control
in the tree bounds ONE invocation (``timeout``, ``memory_size``) or bounds STORAGE
(``log_retention_days``); none of them bounds the RATE, and none of them bounds the third
factor of ``rate x bytes x time-until-something-stops-it``, which sat at *thirty days*.

This program is that third factor. It brings it to minutes.

THERE IS NO NATIVE PATH TO HERE, AND THAT IS WHY THIS IS A LAMBDA
=================================================================

``aws_budgets_budget_action`` exists and cannot stop a Lambda. Its three action types are
``APPLY_IAM_POLICY`` (denies a *principal*; an anonymous Function URL caller is not one),
``APPLY_SCP_POLICY`` (AWS Organizations only, which this account is not in) and
``RUN_SSM_DOCUMENTS`` (EC2 and RDS documents; there is no Lambda one). So the path is
built explicitly:

    Budgets notification ──┐
    Invocations / 60 s   ──┼──► one SNS topic ──► THIS FUNCTION ──► PutFunctionConcurrency(0)
    Invocations / 3600 s ──┤
    Logs IncomingBytes   ──┘

``infra/modules/cost-guard`` is the Terraform that wires it. Read its header for the
three-timescale argument and for the residual this design cannot close.

WHAT IT DOES, EXACTLY
=====================

One call, on one function, with one argument::

    lambda:PutFunctionConcurrency(FunctionName=<from env>, ReservedConcurrentExecutions=0)

Reserving zero means Lambda accepts no invocations at all: a Function URL caller receives
HTTP 429 with no body from the handler, and spend from the function goes to zero except
for whatever is already in flight.

IT IS IDEMPOTENT, IN BOTH SENSES
================================

*Within one event*: at most ONE API call is made no matter how many SNS records the event
carries or how many of them say "stop". The decision is taken over the whole event and the
call is made once.

*Across events*: ``PutFunctionConcurrency(0)`` on an already-stopped function is a no-op at
the API, and this program never reads the current reservation first. A read-before-write
would be a second call that can fail and a second decision that can be wrong, and the only
thing it could buy is skipping a call that is already free.

IT NEVER RESTORES, AND THAT IS ENFORCED THREE TIMES
===================================================

Restore is ``scripts/deploy/kill_switch.sh --restore``, run by a human against a real
credential. Read that script's header before editing this one: **restore is
DeleteFunctionConcurrency, not PutFunctionConcurrency(-1)**. The ``-1`` is a *Terraform*
sentinel meaning "no reservation"; the API's minimum is 0 and it rejects -1 outright, so a
restore written as a put of -1 would fail exactly when it was needed.

The refusal to restore is enforced at three levels, deliberately, because it is the
sentence the whole residual argument rests on:

1. this program contains no restore call;
2. ``tests/deploy/test_cost_guard_responder.py`` asserts the boto3 method name does not
   appear in this source at all;
3. the responder's IAM role carries an explicit **Deny** on
   ``lambda:DeleteFunctionConcurrency`` -- so even a rewritten responder cannot, and an
   explicit Deny cannot be overridden by any Allow.

A stop that the stopped thing can undo is not a stop.

THE TRADE THIS MAKES
====================

**It converts a cost attack into an availability attack.** Anyone who can generate a flood
can stop the demo, and the demo stays stopped until a human restores it. That is the right
trade against an unbounded bill -- an outage is recoverable by one command and a bill is
not -- but it is a trade, and it belongs in a residual column rather than in a footnote.

THE TWO MESSAGE SHAPES, AND WHY THEY ARE NOT BOTH JSON
======================================================

This is the detail a responder written from memory gets wrong.

**CloudWatch alarm notifications** put a JSON *document* in ``Sns.Message``: ``AlarmName``,
``NewStateValue``, ``OldStateValue``, ``Trigger`` and so on. ``NewStateValue`` is the field
that matters -- an alarm publishes on ``OK`` and ``INSUFFICIENT_DATA`` transitions too, if
anyone wires those actions, and neither is a reason to stop anything.

**AWS Budgets notifications put PLAIN TEXT in ``Sns.Message``.** Not JSON. A human-readable
paragraph beginning "AWS Budget Notification <date>" and carrying ``Budget Name:``,
``Budgeted Amount:``, ``Alert Type:`` and ``ACTUAL Amount:`` lines. A responder that calls
``json.loads`` on it and lets the exception escape drops the entire Budgets leg -- the one
leg that catches what the alarms miss -- and the failure is silent, because the leg fires
so rarely that nobody notices it never worked.

Both shapes are exercised, byte-for-byte, by ``tests/deploy/test_cost_guard_responder.py``.

WHAT IT REFUSES
===============

* a record from a **foreign topic** -- anything whose ``TopicArn`` is not
  ``MAINLINE_COST_GUARD_TOPIC_ARN``. A Lambda can be subscribed to a second topic by
  anyone holding ``sns:Subscribe``; this check is what makes such a subscription inert.
* an alarm transition to **OK** or **INSUFFICIENT_DATA**.
* a **malformed** message: no ``Records``, no ``Sns``, an empty ``Message``, JSON that is
  not an alarm, or text that carries none of the Budgets markers.

Every refusal returns normally with the reason in the result and in one log line. It does
not raise: a raised handler is retried by Lambda's asynchronous queue, and retrying a
message that will never be valid is a loop that costs money to run.

The one thing that DOES raise is a missing or empty environment variable. That is a
deployment defect rather than a message defect, it is fixed by an operator and not by
waiting, and a responder that quietly did nothing because it did not know which function to
stop would be the exact "control that looks present and is not" this wave exists to close.

CONFIGURATION
=============

``MAINLINE_GUARDED_FUNCTION_NAME``
    The function to stop. **No default.** A responder that guesses a function name is a
    responder that can stop the wrong function.

``MAINLINE_COST_GUARD_TOPIC_ARN``
    The only topic whose messages are obeyed. **No default**, for the same reason: a
    responder that accepted any topic would accept the one an attacker subscribed it to.

Both are published by ``infra/modules/cost-guard/main.tf`` from the same values that build
the IAM grant, so a disagreement between the grant and the environment is an AccessDenied
in this function's log rather than a wrong function stopped.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

__all__ = [
    "BUDGET_TEXT_MARKERS",
    "ENV_GUARDED_FUNCTION_NAME",
    "ENV_TOPIC_ARN",
    "STOPPED_CONCURRENCY",
    "handler",
]

# NO `setLevel` HERE, AND THAT IS DELIBERATE. Under `log_format = "JSON"` the managed
# python3.13 runtime configures the ROOT logger from the function's
# `logging_config.application_log_level`, which `infra/modules/cost-guard` sets from
# `var.responder_log_level`. A level pinned in this file would silently outrank that
# variable, so the variable would be a knob that looks configured and does nothing -- the
# same defect, one layer down, that this whole module exists to close.
LOGGER = logging.getLogger(__name__)

#: The value written to ``ReservedConcurrentExecutions``. Zero, and it is a named constant
#: rather than a literal so that the falsification test in
#: ``tests/deploy/test_cost_guard_responder.py`` can assert on the name and so that a
#: reader grepping for "what does this set it to" finds one answer.
#:
#: It is NOT -1. See the module docstring: -1 is a Terraform sentinel and the API rejects
#: it. The minimum this API accepts is 0, and 0 is what stops the function.
STOPPED_CONCURRENCY = 0

ENV_GUARDED_FUNCTION_NAME = "MAINLINE_GUARDED_FUNCTION_NAME"
ENV_TOPIC_ARN = "MAINLINE_COST_GUARD_TOPIC_ARN"

#: Lower-cased substrings that identify an AWS Budgets notification body. Budgets sends
#: plain text, so recognition is by marker rather than by field. All four come from the
#: notification AWS actually sends; matching ANY one of them is enough, because a future
#: wording change that dropped one should not drop the whole Budgets leg.
BUDGET_TEXT_MARKERS = (
    "aws budget notification",
    "budget name:",
    "budgeted amount:",
    "alert threshold:",
)

#: Lower-cased prefix of the ``Subject`` AWS Budgets sets. Checked in addition to the body
#: markers, not instead of them: ``Subject`` is optional on an SNS notification and a body
#: match alone is sufficient.
BUDGET_SUBJECT_MARKER = "aws budgets"

#: Keys that identify a budget notification delivered as JSON rather than as text. This is
#: DEFENSIVE and is not the shape AWS Budgets sends today -- it sends the text above. It is
#: here because the direction of error matters: an unrecognised budget message is a
#: backstop that silently never fires, and the topic policy already restricts who may
#: publish here at all.
BUDGET_JSON_KEYS = ("budgetName", "budgetType")

#: The only alarm state that means "stop". CloudWatch also publishes ``OK`` and
#: ``INSUFFICIENT_DATA`` transitions to whatever actions are wired for them.
ALARM_STATE_BREACHING = "ALARM"

_CLIENT: Any = None


def _default_client() -> Any:
    """Build (once) and return the Lambda control-plane client.

    Cached at module scope so a warm container reuses the connection, which matters here:
    this function is invoked during a flood, when the account's ten concurrent executions
    are contended and a cold start is time the bill keeps running.

    ``boto3`` is imported inside the function rather than at module scope so that
    ``tests/deploy/test_cost_guard_responder.py`` can import and exercise every decision
    path -- and the falsification mutant -- without boto3 being installed, and so that the
    import cost is not paid by a code path that was handed a client.
    """
    global _CLIENT  # noqa: PLW0603 - one process-wide warm client is the point
    if _CLIENT is None:
        import boto3

        _CLIENT = boto3.client("lambda")
    return _CLIENT


def _require_env(name: str) -> str:
    """Read one required environment variable, or refuse loudly.

    Empty counts as absent. Terraform publishing ``""`` and Terraform publishing nothing
    are the same deployment defect and must not produce two different behaviours.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        missing = (
            "which function to stop"
            if name == ENV_GUARDED_FUNCTION_NAME
            else "which topic to trust"
        )
        raise RuntimeError(
            f"{name} is unset or empty, so this responder does not know {missing}. "
            "It refuses to guess. infra/modules/cost-guard/main.tf publishes both "
            f"{ENV_GUARDED_FUNCTION_NAME} and {ENV_TOPIC_ARN} from the same values that build "
            "the IAM grant; if one is missing the deployment is the defect, not the message."
        )
    return value


def _looks_like_budget_notification(subject: str, message: str) -> bool:
    """Is this the plain-text body AWS Budgets sends?

    Budgets does not send JSON. See the module docstring; this is the detail that decides
    whether the Budgets leg works at all.
    """
    if subject.strip().lower().startswith(BUDGET_SUBJECT_MARKER):
        return True
    lowered = message.lower()
    return any(marker in lowered for marker in BUDGET_TEXT_MARKERS)


def _classify_text_message(subject: str, message: str) -> tuple[bool, str]:
    """Classify a message body that is not JSON. This is the AWS Budgets path."""
    if _looks_like_budget_notification(subject, message):
        return True, "budget: AWS Budgets actual-cost notification (plain text)"
    return False, "malformed: message is neither JSON nor a recognised AWS Budgets notification"


def _classify_json_message(parsed: Any) -> tuple[bool, str]:
    """Classify a message body that parsed as JSON. This is the CloudWatch alarm path."""
    if not isinstance(parsed, dict):
        return False, "malformed: JSON message is not an object"

    if "AlarmName" in parsed and "NewStateValue" in parsed:
        state = parsed.get("NewStateValue")
        if state == ALARM_STATE_BREACHING:
            return True, "alarm: CloudWatch alarm entered ALARM"
        return False, f"ignored: CloudWatch alarm transitioned to {state!r}, which is not a breach"

    if any(key in parsed for key in BUDGET_JSON_KEYS):
        return True, "budget: AWS Budgets notification delivered as JSON"

    return False, "malformed: JSON message is neither a CloudWatch alarm nor a budget notification"


def _classify_message(subject: str, message: str) -> tuple[bool, str]:
    """Decide whether one SNS message body means "stop", and say why.

    Returns ``(stop, reason)``. ``reason`` is a short fixed string -- never the message
    body, which keeps this function's own log output bounded and free of anything a
    publisher chose.

    THE `try` IS THE WHOLE POINT AND NOT DEFENSIVE PADDING. CloudWatch sends JSON and AWS
    Budgets sends plain text, so a `json.loads` failure here is not an error condition --
    it is how the Budgets leg is recognised. A responder that let this exception escape
    would drop that leg silently.
    """
    if not message.strip():
        return False, "malformed: empty Sns.Message"

    try:
        parsed = json.loads(message)
    except (TypeError, ValueError):
        return _classify_text_message(subject, message)

    return _classify_json_message(parsed)


def _decide(event: Any, expected_topic_arn: str) -> tuple[bool, list[str]]:
    """Fold the whole event down to one decision and one reason per record.

    ONE decision for the whole event, not one per record: that is what makes this
    idempotent within an invocation. A ten-record event in which every record says "stop"
    produces exactly one API call.
    """
    reasons: list[str] = []

    if not isinstance(event, dict):
        return False, ["malformed: event is not an object"]

    records = event.get("Records")
    if not isinstance(records, list) or not records:
        return False, ["malformed: event carries no Records list"]

    stop = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            reasons.append(f"record[{index}] malformed: not an object")
            continue

        sns = record.get("Sns")
        if not isinstance(sns, dict):
            reasons.append(f"record[{index}] malformed: no Sns object")
            continue

        topic_arn = sns.get("TopicArn")
        if topic_arn != expected_topic_arn:
            # THE FOREIGN-TOPIC REFUSAL. The ARN is not echoed into the reason: it is
            # attacker-chosen in exactly the case this branch exists for, and a log line
            # that quotes it is a log line an attacker writes.
            reasons.append(f"record[{index}] refused: TopicArn is not the guard topic")
            continue

        subject = sns.get("Subject") or ""
        message = sns.get("Message")
        if not isinstance(message, str):
            reasons.append(f"record[{index}] malformed: Sns.Message is not a string")
            continue
        if not isinstance(subject, str):
            subject = ""

        record_stop, reason = _classify_message(subject, message)
        reasons.append(f"record[{index}] {reason}")
        stop = stop or record_stop

    return stop, reasons


def _stop(client: Any, function_name: str) -> None:
    """Make the one call this program exists to make.

    Kept as its own function with nothing else in it so that
    ``tests/deploy/test_cost_guard_responder.py`` can delete the call between the anchors
    below, re-execute this module, and prove that the test which passes against the real
    module FAILS against a module that does not stop anything. An untriggered action is
    indistinguishable from no action, and nobody in this wave may apply anything or make a
    mutating AWS call -- so the falsification is the proof.

    Do not put anything between the anchor comments except the call.
    """
    # FALSIFY-ANCHOR-BEGIN -- deleted wholesale by tests/deploy/test_cost_guard_responder.py
    client.put_function_concurrency(
        FunctionName=function_name,
        ReservedConcurrentExecutions=STOPPED_CONCURRENCY,
    )
    # FALSIFY-ANCHOR-END


def handler(event: Any, context: Any = None, *, lambda_client: Any = None) -> dict[str, Any]:
    """Lambda entry point. One event in, at most one ``PutFunctionConcurrency`` out.

    ``lambda_client`` is keyword-only and defaults to ``None`` so that Lambda's own
    ``handler(event, context)`` call works unchanged while the test can hand in a
    ``botocore.stub.Stubber``-backed client. It is the seam that makes the stop provable
    without touching AWS.
    """
    function_name = _require_env(ENV_GUARDED_FUNCTION_NAME)
    expected_topic_arn = _require_env(ENV_TOPIC_ARN)

    stop, reasons = _decide(event, expected_topic_arn)

    result: dict[str, Any] = {
        "stopped": False,
        "function_name": function_name,
        "reasons": reasons,
        # Carried so that one log line ties a decision to the invocation that made it,
        # which is what an operator correlates against the alarm's StateChangeTime.
        "request_id": getattr(context, "aws_request_id", None),
    }

    if not stop:
        LOGGER.info("cost-guard: no stop. %s", json.dumps(result, default=str))
        return result

    client = lambda_client if lambda_client is not None else _default_client()
    _stop(client, function_name)

    result["stopped"] = True
    result["reserved_concurrent_executions"] = STOPPED_CONCURRENCY
    LOGGER.warning(
        "cost-guard: STOPPED %s at reserved concurrency %d. It stays stopped until a human "
        "runs scripts/deploy/kill_switch.sh --restore (DeleteFunctionConcurrency, not a put "
        "of -1). %s",
        function_name,
        STOPPED_CONCURRENCY,
        json.dumps(result, default=str),
    )
    return result
