#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Call AWS for real, once, and commit the transcript — or fail loudly and commit that.

WHAT THIS IS FOR
----------------
The hackathon requires **at least one AWS service, and evidence of how it is used**.
Until today this repository could only claim a *design*: ``docs/STATE-OF-THE-BUILD.md``
§3.3 recorded that every Bedrock call in this account was refused with

    ValidationException: Operation not allowed

which made every Bedrock code path in the tree unreachable and the AWS claim aspirational.
That refusal is gone. This program is the artefact that says so **in a form a judge can
check**, because "we fixed the model access" is an assertion and
``evidence/deploy/aws-live.json`` is a measurement.

FOUR CALLS, IN THIS ORDER, AND WHY EACH ONE IS HERE
---------------------------------------------------
**The order is a published interface.** ``scripts/submission/capture_tool_evidence.py``
cites ``evidence/deploy/aws-live.json#/calls/2/embedding_dimension`` and
``#/calls/3/usage/output_tokens`` — by *index*. Anything added to this program appends at
index 4 or later. Reordering or inserting silently retargets two JSON pointers in the
submission evidence at the wrong call, which is the shape of defect this repository exists
to refuse.

1. ``sts:GetCallerIdentity`` — *who is calling.* Without it the other three prove that
   somebody's credentials work, not that this project's do.
2. ``bedrock:ListFoundationModels`` — *the control-plane answers, and the two models this
   project names are actually offered in this region.* Free, and it separates "the model id
   is wrong" from "the invocation is refused", which are different defects with different
   fixes.
3. ``bedrock-runtime:InvokeModel`` on Titan Text Embeddings V2 — *the data plane answers
   with a vector.* This is the call the memory design depends on: MAINLINE's recall path
   stores 1024-dimension embeddings in a CockroachDB vector index, and a 1024-length float
   array coming back from AWS is the join between the two halves of the submission.
4. ``bedrock-runtime:Converse`` on Claude Haiku 4.5 — *the data plane answers with tokens.*
   Reported with the API's own ``usage`` block, so the token counts are AWS's numbers and
   not this program's arithmetic.

THE FIFTH CALL — THE ALARM READER, AND WHY IT LIVES HERE AND NOT IN CI
----------------------------------------------------------------------
``--alarms`` adds ``cloudwatch:DescribeAlarms`` **at index 4**, and ``--alarms-only`` runs
identity plus that call and nothing else.

``infra/modules/demo-api`` declares four alarms and plans ``alarm_actions = []``. They
notify nobody by design, so they are only worth anything if **something reads them**. The
module's own comment used to say the hourly ``demo-health`` workflow would; it does not,
and it cannot. ``.github/workflows/demo-health.yml`` runs with ``permissions: contents:
read``, never calls ``cloudwatch``, and ``aws-evidence.yml`` goes out of its way to *unset*
every ``AWS_*`` variable. **No AWS credential exists anywhere in this repository's CI**, so
a CI-based alarm reader is not a thing that was skipped — it is a thing that cannot be
built without first putting a credential into a public repository's workflows. This
program, run by an operator against their own profile, is therefore the only reader that
can exist. ``docs/deploy/OBSERVABILITY.md`` §3 states that in prose; this is the code.

What it refuses to let you misread:

* **``INSUFFICIENT_DATA`` is printed as loudly as ``ALARM``.** It is not a shrug. With
  ``treat_missing_data = "missing"`` it is the honest state of an alarm on a function
  nobody has called, and it is *the state a freshly applied demo should be in*. Under the
  old ``notBreaching`` it would have rendered ``OK`` — four green alarms meaning "nobody
  called this function", which is a green that measured nothing.
* **Zero alarms matching the prefix is not a pass.** It means the stack is not applied.
  ``--alarms-only`` exits **3** and names the missing alarms rather than printing an empty
  table over a zero-length list, which reads as calm.
* **An SNS action is verified, not believed.** If ``alarm_actions`` is ever wired, each
  topic's subscriptions are read and any whose ``SubscriptionArn`` is the literal string
  ``PendingConfirmation`` is reported as **UNCONFIRMED — NOTIFIES NOBODY**. An alarm
  pointing at a topic with an unconfirmed subscription is a control that looks present and
  is not, which is the exact defect ``duration_p99``'s ``lifecycle.precondition`` exists to
  forbid one resource away in the same file. Subscription endpoints are e-mail addresses:
  the endpoint is **never** printed, only its protocol and a SHA-256 prefix.

WHAT THIS DELIBERATELY DOES **NOT** RECORD
------------------------------------------
* **No credential, ever.** No access key, no session token, no environment dump. The boto3
  session resolves the profile; this program never reads the resolved secret and never
  writes it.
* **Not the whole embedding.** 1024 floats is ~20 kB of JSON that nobody reads and that
  makes every future diff of this file unreadable. What is recorded is the dimension, the
  first eight components, the L2 norm and the SHA-256 of the full vector — enough to
  recognise the same vector again, far too little to be a corpus.
* **Not the AWS account id, in the clear.** It is not a credential, but it is also not
  something to scatter through a repository about to be made public, and
  ``scripts/submission/audit_public_readiness.py`` flags every literal occurrence. The ARN
  is written with the account digits replaced by ``<account>`` and the id's SHA-256 is
  recorded beside it, so two artefacts can still be proved to name the same account.
  ``docs/leads/ship-final.md`` DECISION D2 owns that policy; this file complies with it by
  never creating the occurrence in the first place.

**A failure is recorded, never swallowed.** Each of the four calls is attempted even if an
earlier one failed, so one report shows every wall at once, and any failure sets the exit
code to 1. The exception's type and message are written down verbatim — the sole
transformation is masking the account id, and the file says that it was applied. A probe
that hid a failure would be worse than no probe: it would make the next reader trust the
green.

Usage::

    .venv/Scripts/python.exe scripts/deploy/aws_live_probe.py
    .venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --region ap-southeast-2 \\
        --profile mainline-dev --out evidence/deploy/aws-live.json

    # the alarm reader — read-only, and the only one that can exist (see above)
    .venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --alarms-only
    .venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --alarms-only \\
        --alarm-region ap-southeast-1 --alarm-prefix mainline-demo-api

Exit codes:

* ``0`` — every call attempted succeeded, and under ``--alarms-only`` all four alarms
  exist and none is in ``ALARM``.
* ``1`` — at least one call failed, or a response did not carry what it must. The evidence
  file is still written, and it names the failure. **Publish it.**
* ``2`` — boto3 is not importable, or no region could be determined, or ``--alarms-only``
  was pointed at the Bedrock evidence file.
* ``3`` — ``--alarms-only`` only: every call succeeded and **what the alarms say is not
  healthy** — one is in ``ALARM``, or an expected alarm does not exist. A finding, not a
  failure, and a different number so a script cannot confuse the two.

``--alarms-only`` **writes no evidence file unless ``--out`` is given, and refuses an
``--out`` that resolves to ``evidence/deploy/aws-live.json``.** That file's calls 2 and 3
are cited by JSON pointer from the submission evidence; a two-call alarm run overwriting it
would leave those pointers aimed at calls that no longer exist.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CALL_FAILED = 1
EXIT_USAGE = 2
#: Distinct from EXIT_CALL_FAILED on purpose: "AWS would not answer me" and "AWS answered,
#: and the answer is that something is wrong with the demo" are different incidents with
#: different first moves, and a caller that cannot tell them apart will take the wrong one.
EXIT_ALARM_FINDING = 3

#: The embedding model, and the dimension MAINLINE's schema is built for. Titan Text
#: Embeddings V2 can emit 256/512/1024; the vector columns in the migration chain are
#: 1024, so a different answer here is a schema mismatch and not a preference.
DEFAULT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
EXPECTED_DIMENSION = 1024

#: The chat model, addressed through its Australian cross-region inference profile. The
#: bare ``anthropic.claude-haiku-4-5-...`` id is listed by the control plane in this region
#: but is served through the ``au.`` profile, which is why the id carries the prefix.
DEFAULT_CHAT_MODEL = "au.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Region and profile. ``ap-southeast-2`` is where this account's Bedrock model access was
#: granted; the CockroachDB cluster is in ``aws-ap-southeast-1``, and the two being
#: different is a fact about the accounts, not an oversight — see docs/deploy/RUNBOOK.md.
DEFAULT_REGION = "ap-southeast-2"
DEFAULT_PROFILE = "mainline-dev"

#: The alarms live where the demo is deployed — ``ap-southeast-1``, beside the CockroachDB
#: Cloud cluster — NOT where Bedrock answers. The two regions differ, so the alarm reader
#: takes its own region rather than inheriting ``--region`` and quietly reading an empty
#: list out of the wrong one. An empty list from the wrong region and an empty list from an
#: unapplied stack are indistinguishable, and one of them is a lie.
DEFAULT_ALARM_REGION = "ap-southeast-1"

#: ``var.name_prefix``-derived function name. The four alarms are ``${function_name}``
#: followed by these suffixes — see ``infra/modules/demo-api/main.tf``. They are listed here
#: so that a *missing* alarm is a finding rather than a shorter table nobody counts.
DEFAULT_ALARM_PREFIX = "mainline-demo-api"
ALARM_SUFFIXES = ("-errors", "-throttles", "-duration-p99", "-concurrency")

#: What AWS puts in ``SubscriptionArn`` for a subscription nobody has clicked the
#: confirmation link for. It is a literal string, not an ARN, and it is the whole tell.
PENDING_CONFIRMATION = "PendingConfirmation"

#: Kept short on purpose. The point is that the data plane answers, not that it writes an
#: essay: two calls, well under a cent, on an account whose whole budget is a few dollars.
DEFAULT_EMBED_TEXT = "MAINLINE permit gate: an open obligation blocks the merge."
DEFAULT_PROMPT = "Reply with exactly: MAINLINE gate online"
MAX_OUTPUT_TOKENS = 32

_TWELVE_DIGITS = re.compile(r"\b\d{12}\b")


# ═════════════════════════════════════════════════════════════════════════════════════
# environment, without importing anything from the deploy package
# ═════════════════════════════════════════════════════════════════════════════════════


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "verticals").is_dir() and (candidate / "packages").is_dir():
            return candidate
    return Path.cwd().resolve()


# `scripts/deploy/cloud_chain.py` has a `load_dotenv` too, and this is deliberately not an
# import of it: that module imports psycopg, and a probe of AWS should not refuse to run on
# a machine with no PostgreSQL driver. Ten duplicated lines buy an artefact that boto3 alone
# can produce, which is what the brief asks for.
def load_dotenv(root: Path) -> None:
    """Read ``.env`` into the environment without overwriting anything already set."""
    env_file = root / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class Masker:
    """Replaces the AWS account id wherever it appears, including inside error messages.

    Constructed empty and *armed* once ``sts:GetCallerIdentity`` answers. If that call
    fails the mask still runs: any bare twelve-digit run in an error message is replaced,
    because the one place an account id most often leaks is the ``is not authorized to
    perform`` message, which is exactly the message a failing probe records.
    """

    def __init__(self) -> None:
        self.account: str | None = None

    def arm(self, account: str) -> None:
        self.account = account

    def __call__(self, text: str) -> str:
        if self.account:
            text = text.replace(self.account, "<account>")
        return _TWELVE_DIGITS.sub("<account>", text)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════════════
# one call, measured
# ═════════════════════════════════════════════════════════════════════════════════════


class Call:
    """One AWS API call: what it was, how long it took, and what came back or blew up.

    Every call in this program goes through here so that the success shape and the failure
    shape are the same shape. A reader comparing a green run with a red one should be
    diffing values, not looking for a differently named key.
    """

    def __init__(self, api: str, mask: Masker) -> None:
        self.api = api
        self._mask = mask
        self.record: dict[str, Any] = {"api": api, "ok": False}

    def __enter__(self) -> Call:
        self._started = time.time()
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        self.record["latency_ms"] = round((time.time() - self._started) * 1000, 1)
        if exc is None:
            self.record["ok"] = True
            return False
        self.record["ok"] = False
        self.record["exception_type"] = f"{type(exc).__module__}.{type(exc).__qualname__}"
        # VERBATIM, apart from the account mask. An error message paraphrased by the tool
        # that failed is the least trustworthy sentence in any incident report.
        self.record["message"] = self._mask(str(exc))
        self.record["message_transformations"] = "account id masked; otherwise verbatim"
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            meta = response.get("ResponseMetadata", {})
            self.record["http_status"] = meta.get("HTTPStatusCode")
            self.record["request_id"] = meta.get("RequestId")
            self.record["error_code"] = response.get("Error", {}).get("Code")
        return True  # handled: the next call still runs, and the exit code remembers


def http_of(response: dict[str, Any]) -> dict[str, Any]:
    meta = response.get("ResponseMetadata", {})
    return {"http_status": meta.get("HTTPStatusCode"), "request_id": meta.get("RequestId")}


# ═════════════════════════════════════════════════════════════════════════════════════
# the four calls
# ═════════════════════════════════════════════════════════════════════════════════════


def probe_identity(session: Any, mask: Masker) -> dict[str, Any]:
    with Call("sts:GetCallerIdentity", mask) as call:
        identity = session.client("sts").get_caller_identity()
        account = str(identity["Account"])
        mask.arm(account)
        call.record.update(http_of(identity))
        call.record["arn"] = mask(str(identity["Arn"]))
        call.record["user_id_prefix"] = str(identity.get("UserId", ""))[:4]
        call.record["account_id_sha256"] = sha256_hex(account)
        call.record["account_id_note"] = (
            "The account id is NOT written here in the clear. Its SHA-256 is, so that two "
            "artefacts can be shown to name the same account without publishing it. See "
            "docs/leads/ship-final.md DECISION D2."
        )
    return call.record


def probe_models(session: Any, region: str, mask: Masker, wanted: list[str]) -> dict[str, Any]:
    with Call("bedrock:ListFoundationModels", mask) as call:
        summaries = session.client("bedrock", region_name=region).list_foundation_models()
        call.record.update(http_of(summaries))
        models = summaries.get("modelSummaries", [])
        call.record["models_offered_in_region"] = len(models)
        by_id = {str(model.get("modelId", "")): model for model in models}
        found: list[dict[str, Any]] = []
        for want in wanted:
            # An inference-profile id (`au.anthropic...`) is not itself a foundation-model
            # id; the control plane lists the underlying model. Matching on the suffix is
            # what makes "the model this project invokes is offered here" a true statement
            # rather than a lookup that mysteriously misses.
            base = want.split(".", 1)[1] if want[:3] in {"au.", "us.", "eu.", "ap."} else want
            model = by_id.get(want) or by_id.get(base)
            found.append(
                {
                    "requested": want,
                    "listed_as": str(model.get("modelId")) if model else None,
                    "present": model is not None,
                    "provider": str(model.get("providerName")) if model else None,
                    "input_modalities": model.get("inputModalities") if model else None,
                    "output_modalities": model.get("outputModalities") if model else None,
                    "inference_types": model.get("inferenceTypesSupported") if model else None,
                }
            )
        call.record["models"] = found
        if not all(entry["present"] for entry in found):
            missing = [entry["requested"] for entry in found if not entry["present"]]
            raise LookupError(f"model(s) not offered in {region}: {', '.join(missing)}")
    return call.record


def probe_embedding(
    session: Any, region: str, mask: Masker, model: str, text: str
) -> dict[str, Any]:
    with Call("bedrock-runtime:InvokeModel", mask) as call:
        call.record["model_id"] = model
        runtime = session.client("bedrock-runtime", region_name=region)
        response = runtime.invoke_model(
            modelId=model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": text, "dimensions": EXPECTED_DIMENSION}),
        )
        call.record.update(http_of(response))
        payload = json.loads(response["body"].read())
        vector = payload.get("embedding") or []
        call.record["input_text"] = text
        call.record["input_text_tokens"] = payload.get("inputTextTokenCount")
        call.record["embedding_dimension"] = len(vector)
        call.record["expected_dimension"] = EXPECTED_DIMENSION
        call.record["embedding_first_eight"] = [round(float(x), 6) for x in vector[:8]]
        call.record["embedding_l2_norm"] = round(sum(float(x) * float(x) for x in vector) ** 0.5, 6)
        call.record["embedding_sha256"] = sha256_hex(
            json.dumps([float(x) for x in vector], separators=(",", ":"))
        )
        call.record["embedding_note"] = (
            "The full vector is NOT stored: dimension, first eight components, L2 norm and "
            "the SHA-256 of the whole array are enough to recognise it again and are three "
            "orders of magnitude smaller."
        )
        if len(vector) != EXPECTED_DIMENSION:
            raise ValueError(
                f"{model} returned {len(vector)} dimensions, expected {EXPECTED_DIMENSION}"
            )
    return call.record


def probe_converse(
    session: Any, region: str, mask: Masker, model: str, prompt: str
) -> dict[str, Any]:
    with Call("bedrock-runtime:Converse", mask) as call:
        call.record["model_id"] = model
        runtime = session.client("bedrock-runtime", region_name=region)
        # No sampling parameter is set here, and none may be added. Boundary rule A6
        # (docs/leads/agents-mcp.md, ARCHITECTURE.md §8.2) bans them in the fleet's
        # request builders, and `temperature: 0.0` was the exact shape it bans: it reads
        # as a promise that the reply is reproducible. It is not. What this repository
        # claims is replayability of the *transcript* and arithmetic reproducibility of
        # the gate — never that a model returns the same sentence twice. This probe
        # asserts the call succeeded and the tokens were counted, which needs no sampler.
        response = runtime.converse(
            modelId=model,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": MAX_OUTPUT_TOKENS},
        )
        call.record.update(http_of(response))
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        reply = "".join(str(block.get("text", "")) for block in blocks).strip()
        usage = response.get("usage", {})
        call.record["prompt"] = prompt
        call.record["reply"] = reply
        call.record["stop_reason"] = response.get("stopReason")
        call.record["usage"] = {
            "input_tokens": usage.get("inputTokens"),
            "output_tokens": usage.get("outputTokens"),
            "total_tokens": usage.get("totalTokens"),
        }
        call.record["usage_note"] = "token counts are the Bedrock API's own, not counted here"
        call.record["latency_ms_reported_by_bedrock"] = response.get("metrics", {}).get("latencyMs")
        if not reply:
            raise ValueError(f"{model} returned an empty message")
    return call.record


# ═════════════════════════════════════════════════════════════════════════════════════
# the fifth call — the alarm reader
# ═════════════════════════════════════════════════════════════════════════════════════


def _subscriptions_of(session: Any, region: str, mask: Masker, topic_arn: str) -> dict[str, Any]:
    """Read one SNS topic's subscriptions and say whether any of them notifies a human.

    Read-only. The endpoint — an e-mail address, a phone number or an HTTPS URL — is
    **never recorded**. Its protocol and a SHA-256 prefix are, which is enough to tell two
    subscriptions apart across two runs and far too little to be a contact list.
    """
    # Imported here, not at module scope, for the same reason boto3 is: `--help` has to
    # work on a machine that has neither.
    from botocore.exceptions import BotoCoreError, ClientError

    summary: dict[str, Any] = {"topic_arn": mask(topic_arn), "subscriptions": []}
    try:
        sns = session.client("sns", region_name=region)
        pages = sns.get_paginator("list_subscriptions_by_topic").paginate(TopicArn=topic_arn)
        for page in pages:
            for sub in page.get("Subscriptions", []):
                arn = str(sub.get("SubscriptionArn", ""))
                summary["subscriptions"].append(
                    {
                        "protocol": sub.get("Protocol"),
                        "endpoint_sha256_prefix": sha256_hex(str(sub.get("Endpoint", "")))[:16],
                        "confirmed": arn != PENDING_CONFIRMATION,
                        "subscription_arn_state": (
                            PENDING_CONFIRMATION if arn == PENDING_CONFIRMATION else "confirmed"
                        ),
                    }
                )
    # Narrow on purpose. A refused or throttled SNS read is recorded and the alarm table -
    # the primary result - still prints. Anything OUTSIDE these two types is not something
    # this function understands, so it propagates to Call.__exit__ and is recorded as a
    # failure of the alarm read rather than swallowed into a footnote.
    except (BotoCoreError, ClientError) as exc:
        summary["read_failed"] = f"{type(exc).__name__}: {mask(str(exc))}"
        summary["read_failed_note"] = (
            "The subscriptions behind this topic could NOT be read, so whether anybody is "
            "notified is UNKNOWN. Do not read this as 'nobody' and do not read it as "
            "'somebody'."
        )
        return summary

    confirmed = [s for s in summary["subscriptions"] if s["confirmed"]]
    summary["subscription_count"] = len(summary["subscriptions"])
    summary["confirmed_count"] = len(confirmed)
    summary["notifies_anybody"] = bool(confirmed)
    if summary["subscriptions"] and not confirmed:
        summary["finding"] = (
            "EVERY subscription on this topic is PendingConfirmation. The alarm has an "
            "action, the action has a topic, the topic has a subscriber, and NOBODY IS "
            "NOTIFIED. This is a control that looks present and is not."
        )
    return summary


def probe_alarms(session: Any, region: str, mask: Masker, prefix: str) -> dict[str, Any]:
    """``cloudwatch:DescribeAlarms`` over one name prefix — the only reader that can exist.

    Records every alarm's state INCLUDING ``INSUFFICIENT_DATA``, its ``treat_missing_data``
    (because that word decides what its state *means*), and whether anything is wired to
    read it. ``call.record["ok"]`` reflects only whether **AWS answered**; whether what AWS
    said is *healthy* is a separate key, so a caller can tell a broken credential from a
    broken demo.
    """
    with Call("cloudwatch:DescribeAlarms", mask) as call:
        call.record["alarm_region"] = region
        call.record["alarm_name_prefix"] = prefix
        expected = [f"{prefix}{suffix}" for suffix in ALARM_SUFFIXES]
        call.record["expected_alarms"] = expected

        cloudwatch = session.client("cloudwatch", region_name=region)
        found: dict[str, dict[str, Any]] = {}
        # Kept OUT of the record: masking is one-way, so the masked ARN in the record can
        # never be handed back to SNS. The unmasked ARNs live in this local for the length
        # of the call and are written nowhere.
        raw_actions: set[str] = set()
        composite = 0
        pages = cloudwatch.get_paginator("describe_alarms").paginate(AlarmNamePrefix=prefix)
        last_response: dict[str, Any] = {}
        for page in pages:
            last_response = page
            composite += len(page.get("CompositeAlarms", []))
            for alarm in page.get("MetricAlarms", []):
                name = str(alarm.get("AlarmName", ""))
                raw_actions.update(str(a) for a in alarm.get("AlarmActions", []))
                actions = [mask(str(a)) for a in alarm.get("AlarmActions", [])]
                found[name] = {
                    "alarm_name": name,
                    "state": alarm.get("StateValue"),
                    "state_reason": mask(str(alarm.get("StateReason", ""))),
                    "state_updated_utc": (
                        alarm["StateUpdatedTimestamp"]
                        .astimezone(UTC)
                        .strftime("%Y-%m-%dT%H:%M:%SZ")
                        if alarm.get("StateUpdatedTimestamp")
                        else None
                    ),
                    "actions_enabled": alarm.get("ActionsEnabled"),
                    "alarm_action_count": len(actions),
                    "alarm_actions": actions,
                    "metric_name": alarm.get("MetricName"),
                    "namespace": alarm.get("Namespace"),
                    "statistic": alarm.get("Statistic") or alarm.get("ExtendedStatistic"),
                    "comparison_operator": alarm.get("ComparisonOperator"),
                    "threshold": alarm.get("Threshold"),
                    "period_seconds": alarm.get("Period"),
                    "evaluation_periods": alarm.get("EvaluationPeriods"),
                    "treat_missing_data": alarm.get("TreatMissingData"),
                }
        call.record.update(http_of(last_response))
        call.record["composite_alarms_seen"] = composite
        call.record["alarms_found"] = len(found)
        call.record["alarms"] = [found[name] for name in sorted(found)]

        missing = [name for name in expected if name not in found]
        in_alarm = sorted(n for n, a in found.items() if a["state"] == "ALARM")
        insufficient = sorted(n for n, a in found.items() if a["state"] == "INSUFFICIENT_DATA")
        call.record["expected_missing"] = missing
        call.record["in_alarm"] = in_alarm
        call.record["insufficient_data"] = insufficient

        # A reader is only real if some subscription is confirmed. Verify, do not believe.
        topics = sorted(arn for arn in raw_actions if ":sns:" in arn)
        call.record["sns_topics_referenced"] = len(topics)
        call.record["sns"] = [_subscriptions_of(session, region, mask, arn) for arn in topics]
        if not topics:
            call.record["reader_note"] = (
                "No alarm references an SNS topic: alarm_actions is empty, as the module "
                "plans it. These alarms notify NOBODY. This program, run by an operator, "
                "is the reader - there is no CI reader and none can be built, because no "
                "AWS credential exists in any workflow in this repository."
            )

        if not found:
            call.record["finding"] = (
                f"NO alarm whose name begins {prefix!r} exists in {region}. This is NOT a "
                "quiet system: it is an unapplied stack, or the wrong region, or the wrong "
                "account. An empty table is not a green one."
            )
        elif missing:
            call.record["finding"] = (
                f"{len(missing)} of {len(expected)} expected alarms do not exist: "
                f"{', '.join(missing)}."
            )
        elif in_alarm:
            call.record["finding"] = f"IN ALARM: {', '.join(in_alarm)}."
        else:
            call.record["finding"] = (
                f"All {len(expected)} alarms exist and none is in ALARM. "
                f"{len(insufficient)} are INSUFFICIENT_DATA, which under "
                "treat_missing_data=missing means NO DATAPOINTS, not health."
            )
        call.record["healthy"] = bool(found) and not missing and not in_alarm
        call.record["state_semantics"] = (
            "OK means the metric was published and stayed under the threshold. "
            "INSUFFICIENT_DATA means the metric was not published at all - under "
            "treat_missing_data=missing that is reported honestly instead of being "
            "rendered as OK, which is what treat_missing_data=notBreaching did. "
            "See docs/deploy/OBSERVABILITY.md section 3."
        )
    return call.record


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


def _call_named(calls: list[dict[str, Any]], api: str) -> dict[str, Any]:
    """The call record for ``api``, or an empty dict if this mode did not make that call."""
    return next((call for call in calls if call.get("api") == api), {})


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    import boto3  # imported here so --help works without it

    mask = Masker()
    started = time.time()
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
    except Exception as exc:  # botocore raises several unrelated types from this one call
        # "there is no such profile" and "Bedrock refused the call" are different findings and
        # only one of them is about this project's AWS access. A traceback would make them look
        # like the same class of problem to whoever reads the terminal.
        print(
            f"aws_live_probe: could not build a session for profile {args.profile!r} in "
            f"{args.region}: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE) from exc

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE AWS live probe",
        "spdx_file_copyright_text": "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "spdx_license_identifier": "SPDX-License-Identifier: CC-BY-4.0",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/deploy/aws_live_probe.py",
        "what_this_proves": (
            (
                "What the four declared CloudWatch alarms SAY right now, read from the live "
                "account. Nothing about Bedrock: --alarms-only skipped both inference calls. "
                "This is the alarm reader, and it is the only one that can exist - no AWS "
                "credential is present in any workflow in this repository."
            )
            if args.alarms_only
            else (
                "That AWS Bedrock EXECUTES for this project, in this region, today - not "
                "that it is designed for. Four calls were made against the live AWS APIs "
                "and every response below is what came back."
            )
        ),
        "supersedes": (
            "docs/STATE-OF-THE-BUILD.md 3.3 recorded 'ValidationException: Operation not "
            "allowed' for every Bedrock call and concluded that no AWS service had ever "
            "executed. That finding is stale as of this file's timestamp. Correcting the "
            "page is W10's task; this file is the evidence it cites."
        ),
        "no_credentials_recorded": (
            "No access key, session token or password appears in this file. The account id "
            "is masked and its SHA-256 recorded instead."
        ),
        "target": {
            "profile": args.profile,
            "region": args.region,
            "botocore_version": None,
            "boto3_version": boto3.__version__,
        },
        "calls": [],
    }
    with contextlib.suppress(ImportError, AttributeError):
        import botocore  # type: ignore[import-untyped]

        evidence["target"]["botocore_version"] = botocore.__version__

    calls = [probe_identity(session, mask)]
    if not args.alarms_only:
        calls += [
            probe_models(session, args.region, mask, [args.embed_model, args.chat_model]),
            probe_embedding(session, args.region, mask, args.embed_model, args.text),
            probe_converse(session, args.region, mask, args.chat_model, args.prompt),
        ]
    # APPENDED, NEVER INSERTED. capture_tool_evidence.py cites #/calls/2 and #/calls/3 by
    # index; the alarm read is index 4 when the Bedrock calls ran, and index 1 in
    # --alarms-only mode, which is why that mode may not write to aws-live.json at all.
    if args.alarms or args.alarms_only:
        calls.append(probe_alarms(session, args.alarm_region, mask, args.alarm_prefix))
    evidence["calls"] = calls
    evidence["total_seconds"] = round(time.time() - started, 2)

    failed = [call["api"] for call in calls if not call["ok"]]
    evidence["calls_attempted"] = len(calls)
    evidence["calls_failed"] = failed

    # Looked up by api name, NOT by index. The indices are a published interface for
    # readers of the file; inside this program, indexing would break the moment a mode
    # omitted a call — which --alarms-only does.
    chat = _call_named(calls, "bedrock-runtime:Converse")
    alarms = _call_named(calls, "cloudwatch:DescribeAlarms")

    if args.alarms_only:
        evidence["cost"] = (
            "No billable inference call was made. sts:GetCallerIdentity and "
            "cloudwatch:DescribeAlarms are both free and both read-only. USD 0.00."
        )
    else:
        evidence["cost"] = (
            "Two billable inference calls. Titan Text Embeddings V2 is charged per input "
            "token and this probe sends a single short sentence; Claude Haiku 4.5 charged "
            f"{chat.get('usage', {}).get('input_tokens')} in / "
            f"{chat.get('usage', {}).get('output_tokens')} out. Well under USD 0.01 per run."
        )

    if args.alarms_only:
        if failed:
            evidence["verdict"] = "AWS CALL FAILED"
            return EXIT_CALL_FAILED, evidence
        # AWS answered. Whether the answer is good news is a DIFFERENT question and gets a
        # different exit code, so a caller can route "fix my credentials" away from "wake
        # somebody up about the demo".
        evidence["verdict"] = (
            "ALARMS HEALTHY" if alarms.get("healthy") else "ALARM FINDING - SEE calls[].finding"
        )
        return (EXIT_OK if alarms.get("healthy") else EXIT_ALARM_FINDING), evidence

    evidence["verdict"] = "AWS BEDROCK EXECUTED" if not failed else "AWS CALL FAILED"
    return (EXIT_OK if not failed else EXIT_CALL_FAILED), evidence


def summarise_alarms(record: dict[str, Any]) -> None:
    """Print every alarm and its state, INSUFFICIENT_DATA as loudly as ALARM.

    A state column that reads ``OK OK OK OK`` on an idle demo is the failure mode this
    whole function exists to prevent, so the meaning of each state is printed beside it
    rather than left to the reader's memory of what ``treat_missing_data`` was set to.
    """
    meaning = {
        "OK": "measured, under threshold",
        "ALARM": "measured, OVER THRESHOLD",
        "INSUFFICIENT_DATA": "NO DATAPOINTS - nothing called it, or missing_data=missing",
    }
    print()
    print(
        f"alarms        prefix {record.get('alarm_name_prefix')!r} in {record.get('alarm_region')}"
    )
    if not record.get("ok"):
        print(f"  FAILED      {record.get('exception_type')}: {record.get('message', '')[:200]}")
        return
    for alarm in record.get("alarms", []):
        state = str(alarm.get("state"))
        print(
            f"  {state:<18} {alarm.get('alarm_name'):<34} "
            f"{alarm.get('statistic')} {alarm.get('comparison_operator')} "
            f"{alarm.get('threshold')}  missing_data={alarm.get('treat_missing_data')}  "
            f"actions={alarm.get('alarm_action_count')}"
        )
        print(f"  {'':<18} -> {meaning.get(state, 'unrecognised state')}")
    for name in record.get("expected_missing", []):
        print(f"  {'DOES NOT EXIST':<18} {name}")
    for topic in record.get("sns", []):
        for sub in topic.get("subscriptions", []):
            flag = "confirmed" if sub.get("confirmed") else "UNCONFIRMED - NOTIFIES NOBODY"
            print(f"  sns           {sub.get('protocol')} {flag}")
        if topic.get("finding"):
            print(f"  sns           {topic['finding']}")
    if record.get("reader_note"):
        print(f"  reader        {record['reader_note']}")
    print(f"  finding       {record.get('finding')}")


def summarise(evidence: dict[str, Any]) -> None:
    target = evidence["target"]
    print()
    print(f"profile       {target['profile']}")
    print(f"region        {target['region']}")
    for call in evidence["calls"]:
        status = "ok" if call["ok"] else "FAILED"
        print(f"  {status:<7} {call['api']:<34} {call.get('latency_ms')} ms")
        if not call["ok"]:
            print(f"          {call.get('exception_type')}: {call.get('message', '')[:220]}")
    empty: dict[str, Any] = {}
    embed = next((c for c in evidence["calls"] if c["api"].endswith("InvokeModel")), empty)
    chat = next((c for c in evidence["calls"] if c["api"].endswith("Converse")), empty)
    if embed.get("ok"):
        print(
            f"embedding     {embed['embedding_dimension']}-dim, "
            f"inputTextTokenCount={embed['input_text_tokens']}, "
            f"|v|={embed['embedding_l2_norm']}"
        )
        print(f"first eight   {embed['embedding_first_eight']}")
    if chat.get("ok"):
        usage = chat["usage"]
        print(f"reply         {chat['reply']!r}")
        print(
            f"tokens        in {usage['input_tokens']} / out {usage['output_tokens']} / "
            f"total {usage['total_tokens']}  stop={chat['stop_reason']}"
        )
    alarms = _call_named(evidence["calls"], "cloudwatch:DescribeAlarms")
    if alarms:
        summarise_alarms(alarms)
    print(f"VERDICT       {evidence['verdict']}")


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    path.with_suffix(path.suffix + ".license").write_text(
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aws_live_probe",
        description=(
            "Call STS and Bedrock for real and write the transcript to "
            "evidence/deploy/aws-live.json. Exits non-zero if any call fails."
        ),
    )
    parser.add_argument("--profile", default=None, help="AWS profile (default: AWS_PROFILE)")
    parser.add_argument("--region", default=None, help="AWS region (default: BEDROCK_REGION)")
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)
    parser.add_argument("--text", default=DEFAULT_EMBED_TEXT, help="text to embed")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="prompt for the chat model")
    parser.add_argument("--out", type=Path, default=None, help="evidence path")
    parser.add_argument(
        "--alarms",
        action="store_true",
        help="also read the four CloudWatch alarms, appended as call index 4",
    )
    parser.add_argument(
        "--alarms-only",
        action="store_true",
        help=(
            "read identity and the alarms and nothing else: no Bedrock call, no charge. "
            "Writes no evidence file unless --out is given, and refuses an --out that is "
            "the Bedrock evidence file."
        ),
    )
    parser.add_argument(
        "--alarm-region",
        default=DEFAULT_ALARM_REGION,
        help=f"region the alarms live in (default: {DEFAULT_ALARM_REGION}, NOT --region)",
    )
    parser.add_argument(
        "--alarm-prefix",
        default=DEFAULT_ALARM_PREFIX,
        help=f"alarm name prefix (default: {DEFAULT_ALARM_PREFIX})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root)
    args = build_parser().parse_args(argv)
    args.profile = args.profile or os.environ.get("AWS_PROFILE") or DEFAULT_PROFILE
    args.region = (
        args.region
        or os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or DEFAULT_REGION
    )
    bedrock_evidence = (root / "evidence" / "deploy" / "aws-live.json").resolve()

    # THE GUARD. `aws-live.json` is cited by JSON pointer at #/calls/2 and #/calls/3 from
    # scripts/submission/capture_tool_evidence.py. An --alarms-only run makes two calls, so
    # letting it write that path would leave two submission citations pointing at calls
    # that no longer exist — a green scanner over evidence that had been quietly replaced.
    # Refusing costs one flag; the alternative costs a false claim in the submission.
    if args.alarms_only:
        out = args.out.resolve() if args.out else None
        if out is not None and out == bedrock_evidence:
            print(
                "aws_live_probe: --alarms-only may not write "
                f"{bedrock_evidence.as_posix()}. That file records the four Bedrock calls "
                "and scripts/submission/capture_tool_evidence.py cites its calls 2 and 3 by "
                "index; an alarm run has neither. Choose another --out, or omit --out and "
                "read the table on stdout.",
                file=sys.stderr,
            )
            return EXIT_USAGE
    else:
        out = args.out.resolve() if args.out else bedrock_evidence

    try:
        import boto3  # noqa: F401
    except ImportError as exc:
        print(f"aws_live_probe: boto3 is not importable: {exc}", file=sys.stderr)
        return EXIT_USAGE

    code, evidence = run(args)
    if out is not None:
        write_evidence(out, evidence)
    summarise(evidence)
    print(f"evidence      {out if out is not None else 'not written (--alarms-only, no --out)'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
