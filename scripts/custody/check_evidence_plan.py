#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The evidence-stack merge gate: policy-as-code over `tofu show -json` plan output.

Ruling **CU-10**: *Object Lock semantics are proven by policy-as-code over the OpenTofu
plan JSON, never by `moto`.* moto's Object Lock enforcement is incomplete, and a green
test against a mock that does not enforce the thing is worse than no test — it converts an
unproven property into a believed one. The plan-JSON assertion tests the actual control,
and GT-18 gives it no second chance: Object Lock and versioning cannot be retrofitted onto
a bucket, so the configuration is right on the first apply or it is a new bucket.

Fourteen rules. Each has a stable id, a one-line reason, and **at least one committed,
deliberately-broken plan fixture that it and only it rejects** — because a gate nobody has
watched refuse anything is a gate that asserts nothing (PL-2, red before green).

    python scripts/custody/check_evidence_plan.py                 # selftest: the default
    python scripts/custody/check_evidence_plan.py check PLAN.json
    python scripts/custody/check_evidence_plan.py regen-fixtures [--check]
    python scripts/custody/check_evidence_plan.py destroy-guard   # always refuses

Producing a plan for it to read, with no AWS credentials at all:

    cd infra/envs/evidence
    tofu init -backend=false
    tofu plan -refresh=false -out=tfplan.bin -var site_code=blk07 -var account_id=… …
    tofu show -json tfplan.bin > plan.json

Stdlib only, on purpose: this runs in CI before anything is installed, and a merge gate
that needs its own dependency resolution is a merge gate that gets disabled.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "infra" / "policy" / "custody" / "fixtures"
COMPLIANT_FIXTURE = FIXTURE_DIR / "plan_compliant.json"
INFRA_ROOT = REPO_ROOT / "infra"

#: The two directories permitted to declare a checkpoint bucket. GT-18's ordering
#: requirement — the evidence stack lands before any other Terraform in the repository can
#: apply — is enforced by refusing a second declaration anywhere else.
EVIDENCE_TF_DIRS = ("infra/modules/evidence-store", "infra/envs/evidence")

#: The tag the module stamps on every indelible resource. Rules key off it rather than off
#: a resource name, because a name is a convention and a tag is in the plan.
EVIDENCE_CLASS_TAG = "mainline:evidence-class"
CHECKPOINT_CLASS = "checkpoint"
INDELIBLE_TAG = "mainline:indelible"

RETENTION_YEARS_FLOOR = 7
RETENTION_DAYS_FLOOR = RETENTION_YEARS_FLOOR * 365
KMS_DELETION_WINDOW_FLOOR = 30
KMS_KEY_SPEC = "ECC_NIST_P256"
KMS_KEY_USAGE = "SIGN_VERIFY"

#: S3 actions that remove evidence or remove the control that protects it. Denied to every
#: principal, with no exception and no conditioned form.
#:
#: `s3:DeleteObject` is on this list even though a locked object version cannot be deleted,
#: because a DELETE MARKER can still be placed on top of one and AWS states that "delete
#: markers are not WORM-protected, regardless of any retention period or legal hold".
#: Hiding the checkpoint is not deleting it and works just as well on someone who does not
#: already suspect.
FORBIDDEN_S3_ACTIONS = (
    "s3:DeleteObject",
    "s3:DeleteObjectVersion",
    "s3:BypassGovernanceRetention",
    "s3:PutBucketVersioning",
    "s3:PutObjectLockConfiguration",
    "s3:DeleteBucket",
    "s3:DeleteBucketPolicy",
)

#: S3 actions that are required in order to SEND the `x-amz-object-lock-*` headers on
#: PutObject at all, and are therefore held by the writer — but only ever in a form
#: constrained by condition. See rule IAM-2.
CONSTRAINABLE_S3_ACTIONS = ("s3:PutObjectRetention", "s3:PutObjectLegalHold")

#: KMS actions that destroy or disable the log key. Crypto-shredding is document
#: destruction (ARCHITECTURE.md §11.6) and a rebuilt key makes yesterday's ledger
#: unverifiable, which is the same offence committed by accident.
FORBIDDEN_KMS_ACTIONS = (
    "kms:ScheduleKeyDeletion",
    "kms:DisableKey",
    "kms:DeleteImportedKeyMaterial",
)


# ══════════════════════════════════════════════════════════════════════════════════════
#  Plan model
# ══════════════════════════════════════════════════════════════════════════════════════


class PlanUnreadable(ValueError):
    """The file is not a `tofu show -json` plan this gate can read."""


@dataclass(frozen=True)
class PlannedResource:
    """One entry of `resource_changes`, flattened to what the rules ask about."""

    address: str
    module_address: str
    mode: str
    type: str
    name: str
    actions: tuple[str, ...]
    before: Mapping[str, Any]
    after: Mapping[str, Any]
    after_unknown: Mapping[str, Any]

    @property
    def tags(self) -> Mapping[str, Any]:
        for key in ("tags_all", "tags"):
            value = self.after.get(key)
            if isinstance(value, Mapping):
                return value
        return {}

    @property
    def is_checkpoint_class(self) -> bool:
        return self.tags.get(EVIDENCE_CLASS_TAG) == CHECKPOINT_CLASS

    @property
    def is_indelible(self) -> bool:
        return str(self.tags.get(INDELIBLE_TAG, "")).lower() == "true"

    def unknown(self, key: str) -> bool:
        return bool(self.after_unknown.get(key))


@dataclass(frozen=True)
class Plan:
    """A parsed plan."""

    path: str
    format_version: str
    resources: tuple[PlannedResource, ...]

    def managed(self, resource_type: str) -> tuple[PlannedResource, ...]:
        return tuple(r for r in self.resources if r.mode == "managed" and r.type == resource_type)

    def in_module(self, module_address: str, resource_type: str) -> tuple[PlannedResource, ...]:
        return tuple(r for r in self.managed(resource_type) if r.module_address == module_address)


def load_plan(path: Path) -> Plan:
    """Read a plan file.

    Args:
        path: A `tofu show -json` output, or a trimmed fixture carrying at least
            `resource_changes`.

    Returns:
        The parsed plan.

    Raises:
        PlanUnreadable: If the file is not JSON, or carries no `resource_changes`.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanUnreadable(f"{path} is not JSON: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise PlanUnreadable(f"{path} is JSON but not an object")
    changes = raw.get("resource_changes")
    if not isinstance(changes, list):
        raise PlanUnreadable(
            f"{path} carries no `resource_changes` array. This gate reads the output of "
            "`tofu show -json <planfile>`, not a state file and not `tofu plan` console "
            "output."
        )
    resources: list[PlannedResource] = []
    for entry in changes:
        if not isinstance(entry, Mapping):
            continue
        change = entry.get("change")
        change = change if isinstance(change, Mapping) else {}
        resources.append(
            PlannedResource(
                address=str(entry.get("address", "")),
                module_address=str(entry.get("module_address", "")),
                mode=str(entry.get("mode", "managed")),
                type=str(entry.get("type", "")),
                name=str(entry.get("name", "")),
                actions=tuple(str(a) for a in change.get("actions", ()) or ()),
                before=_as_mapping(change.get("before")),
                after=_as_mapping(change.get("after")),
                after_unknown=_as_mapping(change.get("after_unknown")),
            )
        )
    return Plan(
        path=str(path),
        format_version=str(raw.get("format_version", "")),
        resources=tuple(resources),
    )


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _block(values: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return the first element of a Terraform block list, or an empty mapping.

    Nested blocks arrive in plan JSON as single-element lists. A missing block and an empty
    block are the same thing to every rule here: the control was not configured.
    """
    raw = values.get(key)
    if isinstance(raw, list) and raw and isinstance(raw[0], Mapping):
        return raw[0]
    if isinstance(raw, Mapping):
        return raw
    return {}


# ══════════════════════════════════════════════════════════════════════════════════════
#  IAM policy model
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Statement:
    """One IAM policy statement, normalised."""

    sid: str
    effect: str
    actions: tuple[str, ...]
    principals: tuple[str, ...]
    not_principals: tuple[str, ...]
    conditions: Mapping[str, Mapping[str, Any]]

    def grants(self, action: str) -> bool:
        """Return whether an `Allow` statement reaches ``action``, wildcards included."""
        return self.effect == "Allow" and _matches_any(action, self.actions)

    def denies(self, action: str) -> bool:
        """Return whether a `Deny` statement reaches ``action``, wildcards included."""
        return self.effect == "Deny" and _matches_any(action, self.actions)

    def condition_values(self, operator_prefix: str, key: str) -> tuple[str, ...]:
        """Return the values of a condition, matched case-insensitively on the key."""
        out: list[str] = []
        for operator, mapping in self.conditions.items():
            if not operator.lower().startswith(operator_prefix.lower()):
                continue
            for condition_key, value in mapping.items():
                if condition_key.lower() != key.lower():
                    continue
                out.extend(value if isinstance(value, list) else [value])
        return tuple(str(v) for v in out)


def parse_policy(document: str) -> tuple[Statement, ...]:
    """Parse an IAM policy JSON string into normalised statements.

    Args:
        document: The policy JSON.

    Returns:
        The statements.

    Raises:
        PlanUnreadable: If the document is not a policy.
    """
    try:
        raw = json.loads(document)
    except json.JSONDecodeError as exc:
        raise PlanUnreadable(f"policy document is not JSON: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise PlanUnreadable("policy document is JSON but not an object")
    statements = raw.get("Statement", [])
    if isinstance(statements, Mapping):
        statements = [statements]
    if not isinstance(statements, list):
        raise PlanUnreadable("policy `Statement` is neither an object nor an array")
    out: list[Statement] = []
    for entry in statements:
        if not isinstance(entry, Mapping):
            continue
        out.append(
            Statement(
                sid=str(entry.get("Sid", "")),
                effect=str(entry.get("Effect", "")),
                actions=_string_list(entry.get("Action")) + _string_list(entry.get("Actions")),
                principals=_principal_list(entry.get("Principal")),
                not_principals=_principal_list(entry.get("NotPrincipal")),
                conditions=_condition_map(entry.get("Condition")),
            )
        )
    return tuple(out)


def _string_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    return ()


def _principal_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        out: list[str] = []
        for identifiers in value.values():
            out.extend(_string_list(identifiers))
        return tuple(out)
    return _string_list(value)


def _condition_map(value: Any) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for operator, mapping in value.items():
        if isinstance(mapping, Mapping):
            out[str(operator)] = dict(mapping)
    return out


def _matches_any(action: str, patterns: Iterable[str]) -> bool:
    """Return whether ``action`` is reached by any IAM action pattern.

    `s3:*`, `*`, `s3:Delete*` and `s3:DeleteObject*` all reach `s3:DeleteObject`. A gate
    that only compared exact strings would pass a policy granting `s3:*`, which is the
    most common way this control is actually lost.
    """
    target = action.lower()
    for pattern in patterns:
        regex = "^" + ".*".join(re.escape(part) for part in pattern.lower().split("*")) + "$"
        if re.match(regex, target):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════════════
#  Findings and rules
# ══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Finding:
    """The verdict for one rule."""

    rule_id: str
    rule_name: str
    failures: list[str] = field(default_factory=list)
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failures and self.skipped is None

    def render(self) -> str:
        if self.skipped is not None:
            # A SKIP is printed as loudly as a FAIL. A gate that quietly passes because it
            # did not look is the single worst artefact this domain could ship.
            return f"SKIP {self.rule_id:<9} {self.rule_name}\n        reason: {self.skipped}"
        if self.ok:
            return f"PASS {self.rule_id:<9} {self.rule_name}"
        body = "\n".join(f"        {line}" for line in self.failures)
        return f"FAIL {self.rule_id:<9} {self.rule_name}\n{body}"


@dataclass(frozen=True)
class Rule:
    """One merge-gate rule."""

    id: str
    name: str
    why: str
    check: Callable[[Plan], list[str]]


def _checkpoint_buckets(plan: Plan) -> tuple[PlannedResource, ...]:
    return tuple(r for r in plan.managed("aws_s3_bucket") if r.is_checkpoint_class)


# ── OL: the bucket itself ─────────────────────────────────────────────────────────────


def _rule_object_lock_at_creation(plan: Plan) -> list[str]:
    buckets = _checkpoint_buckets(plan)
    if not buckets:
        message = (
            f"no aws_s3_bucket in this plan carries {EVIDENCE_CLASS_TAG}={CHECKPOINT_CLASS!r}. "
            "The gate refuses rather than passing vacuously: a plan with no checkpoint "
            "bucket cannot be the evidence stack, and a rule with nothing to check is a "
            "rule that has stopped checking."
        )
        return [message]
    problems: list[str] = []
    for bucket in buckets:
        if bucket.after.get("object_lock_enabled") is not True:
            problems.append(
                f"{bucket.address}: object_lock_enabled is "
                f"{bucket.after.get('object_lock_enabled')!r}, not true. Object Lock can "
                "only be turned on WHEN THE BUCKET IS CREATED; there is no API that "
                "retrofits it (GT-18 has no fallback)."
            )
        if "create" not in bucket.actions and bucket.before.get("object_lock_enabled") is not True:
            problems.append(
                f"{bucket.address}: actions are {list(bucket.actions)} on a bucket that did "
                "not already have Object Lock. This plan is attempting to retrofit a "
                "control that cannot be retrofitted; it will fail at apply, after the "
                "bucket exists."
            )
    return problems


def _rule_versioning(plan: Plan) -> list[str]:
    problems: list[str] = []
    for bucket in _checkpoint_buckets(plan):
        versioning = plan.in_module(bucket.module_address, "aws_s3_bucket_versioning")
        if not versioning:
            problems.append(
                f"{bucket.address}: no aws_s3_bucket_versioning is declared alongside it. "
                "Object Lock requires versioning, and a bucket whose versioning is off is "
                "a bucket where an overwrite is a deletion."
            )
            continue
        for resource in versioning:
            status = _block(resource.after, "versioning_configuration").get("status")
            if status != "Enabled":
                problems.append(
                    f"{resource.address}: versioning status is {status!r}, not 'Enabled'."
                )
    return problems


def _rule_compliance_retention(plan: Plan) -> list[str]:
    problems: list[str] = []
    for bucket in _checkpoint_buckets(plan):
        configs = plan.in_module(bucket.module_address, "aws_s3_bucket_object_lock_configuration")
        if not configs:
            problems.append(
                f"{bucket.address}: no aws_s3_bucket_object_lock_configuration. The bucket "
                "would accept writes with no default retention at all, and PutObject "
                "succeeds silently in that case."
            )
            continue
        for config in configs:
            retention = _block(_block(config.after, "rule"), "default_retention")
            mode = retention.get("mode")
            if mode != "COMPLIANCE":
                problems.append(
                    f"{config.address}: default retention mode is {mode!r}, not "
                    "'COMPLIANCE'. GOVERNANCE can be bypassed by any principal holding "
                    "s3:BypassGovernanceRetention, which makes the object a copy rather "
                    "than a commitment."
                )
            years = retention.get("years")
            days = retention.get("days")
            if years is None and days is None:
                problems.append(f"{config.address}: default retention sets neither years nor days.")
            elif years is not None and int(years) < RETENTION_YEARS_FLOOR:
                problems.append(
                    f"{config.address}: default retention is {years} years, below the "
                    f"{RETENTION_YEARS_FLOOR}-year custody floor."
                )
            elif days is not None and years is None and int(days) < RETENTION_DAYS_FLOOR:
                problems.append(
                    f"{config.address}: default retention is {days} days, below the "
                    f"{RETENTION_DAYS_FLOOR}-day custody floor."
                )
    return problems


def _rule_public_access_blocked(plan: Plan) -> list[str]:
    problems: list[str] = []
    for bucket in _checkpoint_buckets(plan):
        blocks = plan.in_module(bucket.module_address, "aws_s3_bucket_public_access_block")
        if not blocks:
            problems.append(f"{bucket.address}: no aws_s3_bucket_public_access_block.")
            continue
        for block in blocks:
            for setting in (
                "block_public_acls",
                "block_public_policy",
                "ignore_public_acls",
                "restrict_public_buckets",
            ):
                if block.after.get(setting) is not True:
                    problems.append(
                        f"{block.address}: {setting} is {block.after.get(setting)!r}, not true."
                    )
    return problems


def _rule_no_shredding_surface(plan: Plan) -> list[str]:
    """The checkpoint bucket must not be encrypted under a deletable customer key.

    AWS states it directly: "if you encrypt your objects with AWS KMS server-side
    encryption and your AWS KMS key is deleted your objects may become unreadable." A
    checkpoint note is a public commitment carrying no personal information, so SSE-KMS
    buys no confidentiality here and adds a delete button to the one bucket whose entire
    purpose is that it has none.
    """
    problems: list[str] = []
    for bucket in _checkpoint_buckets(plan):
        configs = plan.in_module(
            bucket.module_address, "aws_s3_bucket_server_side_encryption_configuration"
        )
        for config in configs:
            default = _block(
                _block(config.after, "rule"), "apply_server_side_encryption_by_default"
            )
            algorithm = default.get("sse_algorithm")
            key = default.get("kms_master_key_id")
            if algorithm not in (None, "AES256"):
                problems.append(
                    f"{config.address}: sse_algorithm is {algorithm!r}. The checkpoint "
                    "bucket uses SSE-S3 so that deleting a KMS key cannot make the "
                    "evidence unreadable — crypto-shredding is document destruction "
                    "(ARCHITECTURE.md §11.6)."
                )
            if key:
                problems.append(
                    f"{config.address}: kms_master_key_id is set ({key!r}), which puts a "
                    "deletable key between a stranger and the evidence."
                )
    return problems


# ── IAM: what the policies grant ──────────────────────────────────────────────────────


def _policies(plan: Plan) -> Iterator[tuple[PlannedResource, tuple[Statement, ...]]]:
    """Yield every resolvable policy document in the plan, with its resource."""
    for resource in plan.resources:
        if resource.mode != "managed":
            continue
        document = resource.after.get("policy")
        if not isinstance(document, str) or not document.strip():
            continue
        try:
            yield resource, parse_policy(document)
        except PlanUnreadable:
            continue


def _s3_policies(plan: Plan) -> Iterator[tuple[PlannedResource, tuple[Statement, ...]]]:
    for resource, statements in _policies(plan):
        if resource.type in ("aws_s3_bucket_policy", "aws_iam_policy", "aws_iam_role_policy"):
            yield resource, statements


def _rule_no_destructive_object_actions(plan: Plan) -> list[str]:
    problems: list[str] = []
    for resource, statements in _s3_policies(plan):
        for statement in statements:
            for action in FORBIDDEN_S3_ACTIONS:
                if statement.grants(action):
                    problems.append(
                        f"{resource.address} statement {statement.sid or '<unnamed>'!r} "
                        f"ALLOWS {action} (matched by {list(statement.actions)}). No "
                        "principal in the write account may hold it: a locked version "
                        "cannot be deleted, but a delete marker can still be placed on "
                        "top of one and delete markers are not WORM-protected."
                    )
    return problems


def _rule_retention_grants_are_constrained(plan: Plan) -> list[str]:
    problems: list[str] = []
    for resource, statements in _s3_policies(plan):
        granted = [
            (statement, action)
            for statement in statements
            for action in CONSTRAINABLE_S3_ACTIONS
            if statement.grants(action)
        ]
        if not granted:
            continue
        missing = _missing_retention_guards(statements)
        for statement, action in granted:
            for guard in missing:
                problems.append(
                    f"{resource.address} statement {statement.sid or '<unnamed>'!r} allows "
                    f"{action} and the policy carries no {guard}. Both actions are required "
                    "merely to SEND the x-amz-object-lock-* headers on PutObject, so an "
                    "outright ban would make the writer unable to lock anything; an "
                    "UNCONSTRAINED grant, however, is the power to shorten a retention or "
                    "lift a hold."
                )
    return problems


def _missing_retention_guards(statements: Sequence[Statement]) -> list[str]:
    """Return the names of the Deny statements a constrained grant requires."""
    has_mode_guard = False
    has_term_guard = False
    has_hold_guard = False
    for statement in statements:
        if statement.effect != "Deny":
            continue
        if statement.denies("s3:PutObjectRetention") or statement.denies("s3:PutObject"):
            if statement.condition_values("StringNotEquals", "s3:object-lock-mode") == (
                "COMPLIANCE",
            ):
                has_mode_guard = True
            for value in statement.condition_values(
                "NumericLessThan", "s3:object-lock-remaining-retention-days"
            ):
                if int(value) >= RETENTION_DAYS_FLOOR:
                    has_term_guard = True
        if statement.denies("s3:PutObjectLegalHold") and statement.condition_values(
            "StringNotEquals", "s3:object-lock-legal-hold"
        ) == ("ON",):
            has_hold_guard = True
    missing: list[str] = []
    if not has_mode_guard:
        missing.append(
            "Deny on s3:PutObjectRetention/s3:PutObject where s3:object-lock-mode "
            "StringNotEquals COMPLIANCE"
        )
    if not has_term_guard:
        missing.append(
            "Deny on s3:PutObjectRetention/s3:PutObject where "
            f"s3:object-lock-remaining-retention-days NumericLessThan {RETENTION_DAYS_FLOOR}"
        )
    if not has_hold_guard:
        missing.append(
            "Deny on s3:PutObjectLegalHold where s3:object-lock-legal-hold StringNotEquals ON"
        )
    return missing


# ── KMS: the key that signs, and the two calls that destroy it ────────────────────────


#: The two calls the break-glass exemption is written around. `DeleteImportedKeyMaterial`
#: is denied alongside them but is not required to be, because a key MAINLINE generates in
#: KMS has no imported material to delete.
REQUIRED_KMS_GUARDS = ("kms:ScheduleKeyDeletion", "kms:DisableKey")


def _break_glass_exemption(statements: Sequence[Statement]) -> tuple[set[str], set[str]]:
    """Return ``(actions guarded by a Deny/NotPrincipal, principals it exempts)``."""
    guarded: set[str] = set()
    exempt: set[str] = set()
    for statement in statements:
        if statement.effect != "Deny" or not statement.not_principals:
            continue
        for action in FORBIDDEN_KMS_ACTIONS:
            if statement.denies(action):
                guarded.add(action)
                exempt.update(statement.not_principals)
    return guarded, exempt


def _ungated_destruction_grants(
    key: PlannedResource, statements: Sequence[Statement], exempt: set[str]
) -> list[str]:
    """Return one message per Allow that reaches key destruction outside the exemption."""
    problems: list[str] = []
    for statement in statements:
        if statement.effect != "Allow":
            continue
        for action in REQUIRED_KMS_GUARDS:
            if not statement.grants(action):
                continue
            outsiders = [p for p in statement.principals if p not in exempt]
            if outsiders:
                problems.append(
                    f"{key.address} statement {statement.sid or '<unnamed>'!r} allows "
                    f"{action} to {outsiders}, which the Deny/NotPrincipal statement "
                    "does not exempt. Key destruction is grantable to the two-person "
                    "break-glass role and to nobody else."
                )
    return problems


def _rule_key_destruction_denied(plan: Plan) -> list[str]:
    problems: list[str] = []
    keys = plan.managed("aws_kms_key")
    if not keys:
        return ["this plan declares no aws_kms_key; the evidence stack has no signing key."]
    for key in keys:
        document = key.after.get("policy")
        if not isinstance(document, str) or not document.strip():
            continue  # PLAN-1 reports an unresolved policy; this rule does not double-report.
        statements = parse_policy(document)
        guarded, exempt = _break_glass_exemption(statements)
        problems.extend(
            f"{key.address}: the key policy carries no Deny/NotPrincipal statement "
            f"covering {action}. Crypto-shredding is document destruction, and a "
            "recreated key makes yesterday's ledger unverifiable — the same "
            "offence as destruction, committed by accident (ARCHITECTURE.md §11.6)."
            for action in REQUIRED_KMS_GUARDS
            if action not in guarded
        )
        problems.extend(_ungated_destruction_grants(key, statements, exempt))
    return problems


def _rule_no_key_rotation(plan: Plan) -> list[str]:
    problems: list[str] = []
    for key in plan.managed("aws_kms_key"):
        if key.after.get("enable_key_rotation") is True:
            problems.append(
                f"{key.address}: enable_key_rotation is true. AWS cannot rotate an "
                "asymmetric key at all, so this is either a no-op that misleads a reader "
                "or a symmetric key where a signing key was intended — and a checkpoint "
                "signed by a key nobody can name is an unverifiable checkpoint."
            )
        period = key.after.get("rotation_period_in_days")
        if period not in (None, 0):
            problems.append(f"{key.address}: rotation_period_in_days is set to {period!r}.")
    return problems


def _rule_no_deletion_schedule(plan: Plan) -> list[str]:
    problems: list[str] = []
    for key in plan.managed("aws_kms_key"):
        window = key.after.get("deletion_window_in_days")
        if window is not None and int(window) < KMS_DELETION_WINDOW_FLOOR:
            problems.append(
                f"{key.address}: deletion_window_in_days is {window}, below the "
                f"{KMS_DELETION_WINDOW_FLOOR}-day maximum. The window is the ONLY time "
                "anyone has to notice a scheduled deletion and cancel it; shortening it "
                "trades a month of notice for nothing."
            )
        if key.after.get("is_enabled") is False:
            problems.append(
                f"{key.address}: is_enabled is false. A disabled signing key cannot sign a "
                "checkpoint, and a log that stops checkpointing stops being evidence "
                "sixty seconds later."
            )
    return problems


def _rule_signing_key_spec(plan: Plan) -> list[str]:
    problems: list[str] = []
    for key in plan.managed("aws_kms_key"):
        spec = key.after.get("customer_master_key_spec")
        usage = key.after.get("key_usage")
        if spec != KMS_KEY_SPEC:
            problems.append(
                f"{key.address}: customer_master_key_spec is {spec!r}, not {KMS_KEY_SPEC!r}. "
                "C2SP note type 0x02 is ECDSA P-256 only (ruling CU-3)."
            )
        if usage != KMS_KEY_USAGE:
            problems.append(f"{key.address}: key_usage is {usage!r}, not {KMS_KEY_USAGE!r}.")
    return problems


# ── GT-18 ordering, plan resolvability, and destroy ───────────────────────────────────


def _rule_single_checkpoint_bucket(plan: Plan) -> list[str]:
    buckets = _checkpoint_buckets(plan)
    if len(buckets) > 1:
        message = (
            "this plan declares "
            f"{len(buckets)} checkpoint buckets: {[b.address for b in buckets]}. There is "
            "one place a stranger is told to look for the commitments, and two is one more "
            "than that."
        )
        return [message]
    return []


def scan_for_foreign_checkpoint_buckets(root: Path) -> list[str]:
    """Scan `.tf` files for a checkpoint bucket declared outside the evidence stack.

    GT-18's ordering requirement is that the evidence stack lands **before any other
    Terraform in the repository can apply**. That cannot be read off one plan, so it is
    read off the tree: a textual scan for `aws_s3_bucket` with Object Lock, or for the
    `mainline:evidence-class = checkpoint` tag, anywhere outside the two permitted
    directories.

    Deliberately a regex scan and not an HCL parse. The rule is a tripwire — it exists to
    make a second checkpoint bucket impossible to add *accidentally* — and a tripwire that
    needs `python-hcl2` installed in CI is a tripwire that gets skipped.

    Args:
        root: The `infra/` directory to walk.

    Returns:
        One message per offending file.
    """
    problems: list[str] = []
    if not root.exists():
        return [f"{root} does not exist, so GT-18's single-bucket rule checked nothing"]
    for path in sorted(root.rglob("*.tf")):
        relative = path.relative_to(root.parent).as_posix()
        if any(relative.startswith(allowed) for allowed in EVIDENCE_TF_DIRS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        stripped = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        if re.search(r'"?mainline:evidence-class"?\s*=\s*"checkpoint"', stripped):
            problems.append(
                f"{relative} tags a resource {EVIDENCE_CLASS_TAG}={CHECKPOINT_CLASS!r}. Only "
                f"{EVIDENCE_TF_DIRS} may declare the checkpoint store."
            )
        if re.search(r"object_lock_enabled\s*=\s*true", stripped) or re.search(
            r'resource\s+"aws_s3_bucket_object_lock_configuration"', stripped
        ):
            problems.append(
                f"{relative} declares S3 Object Lock. GT-18 makes the evidence stack a "
                "one-shot that must land before any other Terraform in the repository "
                f"applies, so Object Lock is declared in {EVIDENCE_TF_DIRS} and nowhere else."
            )
    return problems


def _rule_no_foreign_checkpoint_bucket(plan: Plan) -> list[str]:  # noqa: ARG001 - tree rule
    return scan_for_foreign_checkpoint_buckets(INFRA_ROOT)


def _rule_policies_resolvable(plan: Plan) -> list[str]:
    problems: list[str] = []
    for resource in plan.resources:
        if resource.type not in ("aws_s3_bucket_policy", "aws_kms_key", "aws_iam_policy"):
            continue
        if resource.mode != "managed":
            continue
        document = resource.after.get("policy")
        if resource.unknown("policy") or not isinstance(document, str) or not document.strip():
            problems.append(
                f'{resource.address}: the policy is "known after apply", so this gate '
                "cannot read what it will grant. Derive the resource ARNs from inputs "
                "rather than from resource attributes (an S3 bucket ARN is "
                "arn:<partition>:s3:::<name> and needs no account or region), or run the "
                "gate against a post-apply plan. A gate that cannot read the policy must "
                "refuse, not shrug."
            )
            continue
        try:
            parse_policy(document)
        except PlanUnreadable as exc:
            problems.append(f"{resource.address}: {exc}")
    return problems


def _rule_no_destroy_of_indelible(plan: Plan) -> list[str]:
    problems: list[str] = []
    for resource in plan.resources:
        if "delete" not in resource.actions:
            continue
        indelible = (
            resource.is_indelible
            or str(_as_mapping(resource.before).get("tags_all", {}).get(INDELIBLE_TAG, "")).lower()
            == "true"
        )
        in_evidence_module = "evidence_store" in resource.module_address
        if indelible or in_evidence_module:
            problems.append(
                f"{resource.address}: planned actions {list(resource.actions)} include a "
                "delete on an indelible resource. `just destroy` must be honest about "
                "which stacks cannot be destroyed (CU-11); this stack is one of them."
            )
    return problems


RULES: tuple[Rule, ...] = (
    Rule(
        "OL-1",
        "bucket-object-lock-at-creation",
        "Object Lock cannot be enabled on an existing bucket. GT-18 has no fallback.",
        _rule_object_lock_at_creation,
    ),
    Rule(
        "OL-2",
        "bucket-versioning-enabled",
        "Object Lock requires versioning; without it an overwrite is a deletion.",
        _rule_versioning,
    ),
    Rule(
        "OL-3",
        "object-lock-compliance-retention",
        "COMPLIANCE for at least seven years. GOVERNANCE is bypassable and is not a commitment.",
        _rule_compliance_retention,
    ),
    Rule(
        "OL-4",
        "public-access-blocked",
        "All four public-access blocks on. Evidence is not served from a public bucket.",
        _rule_public_access_blocked,
    ),
    Rule(
        "OL-5",
        "no-crypto-shredding-surface",
        "SSE-S3, not SSE-KMS: deleting a KMS key must not be able to make evidence unreadable.",
        _rule_no_shredding_surface,
    ),
    Rule(
        "IAM-1",
        "no-destructive-object-actions",
        "No principal may hold DeleteObject*, BypassGovernanceRetention, or the control APIs.",
        _rule_no_destructive_object_actions,
    ),
    Rule(
        "IAM-2",
        "retention-grants-are-constrained",
        "PutObjectRetention / PutObjectLegalHold are grantable only in a condition-bound form.",
        _rule_retention_grants_are_constrained,
    ),
    Rule(
        "KMS-1",
        "key-destruction-denied-outside-break-glass",
        "ScheduleKeyDeletion and DisableKey reach the two-person break-glass role and nobody else.",
        _rule_key_destruction_denied,
    ),
    Rule(
        "KMS-2",
        "no-key-rotation",
        "A rotation setting on the log key is either a no-op that misleads or the wrong key type.",
        _rule_no_key_rotation,
    ),
    Rule(
        "KMS-3",
        "no-short-deletion-window",
        "Thirty days is the longest anyone gets to notice a scheduled deletion and cancel it.",
        _rule_no_deletion_schedule,
    ),
    Rule(
        "KMS-4",
        "signing-key-spec",
        "ECC_NIST_P256 / SIGN_VERIFY. C2SP note type 0x02 is ECDSA P-256 only (CU-3).",
        _rule_signing_key_spec,
    ),
    Rule(
        "GT18-1",
        "single-checkpoint-bucket-in-plan",
        "One place a stranger is told to look for the commitments.",
        _rule_single_checkpoint_bucket,
    ),
    Rule(
        "GT18-2",
        "no-checkpoint-bucket-in-another-root",
        "No other root module in the repository may declare a checkpoint bucket.",
        _rule_no_foreign_checkpoint_bucket,
    ),
    Rule(
        "PLAN-1",
        "policy-documents-resolvable",
        "A gate that cannot read the policy must refuse, not shrug.",
        _rule_policies_resolvable,
    ),
    Rule(
        "DESTROY-1",
        "no-destroy-of-indelible-resources",
        "The indelible stack has no destroy path (CU-11).",
        _rule_no_destroy_of_indelible,
    ),
)

RULES_BY_ID = {rule.id: rule for rule in RULES}


def evaluate(plan: Plan, *, only: Sequence[str] | None = None) -> list[Finding]:
    """Run every rule against a plan.

    Args:
        plan: The parsed plan.
        only: Restrict to these rule ids. Used by the selftest so that a fixture broken for
            one rule is judged by that rule.

    Returns:
        One finding per rule, in declaration order.
    """
    findings: list[Finding] = []
    for rule in RULES:
        if only is not None and rule.id not in only:
            continue
        findings.append(Finding(rule.id, rule.name, list(rule.check(plan))))
    return findings


# ══════════════════════════════════════════════════════════════════════════════════════
#  Fixtures — one deliberately-broken plan per rule
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Every mutation below is applied to the ONE compliant fixture, which is the byte-for-byte
# output of `tofu show -json` over `infra/envs/evidence`. Mutating a real plan rather than
# hand-writing a synthetic one matters: a synthetic fixture drifts from the shape the tool
# actually emits, and the day it drifts the gate starts passing plans it has never seen.
#
# The broken fixtures are trimmed to the keys the gate reads and minified, because a
# quarter-megabyte of duplicated plan per rule is a repository nobody clones.

FIXTURE_KEYS = ("format_version", "terraform_version", "planned_values", "resource_changes")


def _find_change(plan: dict[str, Any], address: str) -> dict[str, Any]:
    for entry in plan["resource_changes"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("address") == address:
            return entry
    raise KeyError(f"{address} is not in the compliant fixture")


def _after(plan: dict[str, Any], address: str) -> dict[str, Any]:
    after = _find_change(plan, address)["change"]["after"]
    if not isinstance(after, dict):
        raise TypeError(f"{address} has no `after` object to mutate")
    return after


_BUCKET = "module.evidence_store.aws_s3_bucket.evidence"
_VERSIONING = "module.evidence_store.aws_s3_bucket_versioning.evidence"
_LOCK_CONFIG = "module.evidence_store.aws_s3_bucket_object_lock_configuration.evidence"
_PAB = "module.evidence_store.aws_s3_bucket_public_access_block.evidence"
_SSE = "module.evidence_store.aws_s3_bucket_server_side_encryption_configuration.evidence"
_BUCKET_POLICY = "module.evidence_store.aws_s3_bucket_policy.evidence"
_KEY = "module.evidence_store.aws_kms_key.log_signing"
_TRAIL = "aws_cloudtrail.evidence"


def _break_object_lock(plan: dict[str, Any]) -> None:
    _after(plan, _BUCKET)["object_lock_enabled"] = False


def _break_versioning(plan: dict[str, Any]) -> None:
    _after(plan, _VERSIONING)["versioning_configuration"] = [{"status": "Suspended"}]


def _break_retention(plan: dict[str, Any]) -> None:
    _after(plan, _LOCK_CONFIG)["rule"] = [
        {"default_retention": [{"days": None, "mode": "GOVERNANCE", "years": 1}]}
    ]


def _break_public_access(plan: dict[str, Any]) -> None:
    _after(plan, _PAB)["block_public_policy"] = False


def _break_encryption(plan: dict[str, Any]) -> None:
    _after(plan, _SSE)["rule"] = [
        {
            "apply_server_side_encryption_by_default": [
                {
                    "sse_algorithm": "aws:kms",
                    "kms_master_key_id": "arn:aws:kms:ap-southeast-1:111122223333:key/deletable",
                }
            ],
            "bucket_key_enabled": True,
        }
    ]


def _rewrite_bucket_policy(plan: dict[str, Any], mutate: Callable[[list[Any]], None]) -> None:
    after = _after(plan, _BUCKET_POLICY)
    document = json.loads(after["policy"])
    mutate(document["Statement"])
    after["policy"] = json.dumps(document, separators=(",", ":"))


def _break_destructive_grant(plan: dict[str, Any]) -> None:
    def mutate(statements: list[Any]) -> None:
        for statement in statements:
            if statement.get("Sid") == "AllowTheWriterToPutAndToLockAndNothingElse":
                # The classic mistake: "the writer needs to clean up its own failed
                # uploads". It also needs to be unable to.
                statement["Action"].append("s3:DeleteObject")
                return
        raise KeyError("the writer Allow statement is not in the compliant fixture")

    _rewrite_bucket_policy(plan, mutate)


def _break_retention_constraint(plan: dict[str, Any]) -> None:
    def mutate(statements: list[Any]) -> None:
        statements[:] = [
            s for s in statements if s.get("Sid") != "DenyAnyRetentionModeOtherThanCompliance"
        ]

    _rewrite_bucket_policy(plan, mutate)


def _break_key_destruction_guard(plan: dict[str, Any]) -> None:
    after = _after(plan, _KEY)
    document = json.loads(after["policy"])
    document["Statement"] = [
        s for s in document["Statement"] if s.get("Sid") != "DenyKeyDestructionOutsideBreakGlass"
    ]
    after["policy"] = json.dumps(document, separators=(",", ":"))


def _break_key_rotation(plan: dict[str, Any]) -> None:
    _after(plan, _KEY)["enable_key_rotation"] = True


def _break_deletion_window(plan: dict[str, Any]) -> None:
    _after(plan, _KEY)["deletion_window_in_days"] = 7


def _break_key_spec(plan: dict[str, Any]) -> None:
    after = _after(plan, _KEY)
    after["customer_master_key_spec"] = "SYMMETRIC_DEFAULT"
    after["key_usage"] = "ENCRYPT_DECRYPT"


def _break_single_bucket(plan: dict[str, Any]) -> None:
    twin = copy.deepcopy(_find_change(plan, _BUCKET))
    twin["address"] = "module.evidence_store.aws_s3_bucket.evidence_second"
    twin["name"] = "evidence_second"
    twin["change"]["after"]["bucket"] = "mainline-custody-blk07-two"
    plan["resource_changes"].append(twin)


def _break_policy_resolvable(plan: dict[str, Any]) -> None:
    change = _find_change(plan, _BUCKET_POLICY)["change"]
    change["after"]["policy"] = None
    change.setdefault("after_unknown", {})["policy"] = True


def _break_destroy(plan: dict[str, Any]) -> None:
    # The CloudTrail and not the KMS key, deliberately. A delete plan has `after: null`, so
    # deleting the key would also trip KMS-4 and PLAN-1 and the fixture would prove that
    # *something* failed rather than that DESTROY-1 works. The trail is tagged
    # `mainline:indelible = true` and is read by no other rule, so this mutation is
    # surgical: exactly one rule refuses it.
    change = _find_change(plan, _TRAIL)["change"]
    change["actions"] = ["delete"]
    change["before"] = copy.deepcopy(change["after"])
    change["after"] = None
    change["after_unknown"] = {}


#: fixture file name → (rule it must fail, mutation). GT18-2 is absent: it is a rule over
#: the source tree, not over a plan, and its broken fixture is `foreign_bucket.tf.fixture`
#: below.
MUTATIONS: dict[str, tuple[str, Callable[[dict[str, Any]], None]]] = {
    "plan_broken_ol1_no_object_lock.json": ("OL-1", _break_object_lock),
    "plan_broken_ol2_versioning_suspended.json": ("OL-2", _break_versioning),
    "plan_broken_ol3_governance_one_year.json": ("OL-3", _break_retention),
    "plan_broken_ol4_public_policy_allowed.json": ("OL-4", _break_public_access),
    "plan_broken_ol5_sse_kms.json": ("OL-5", _break_encryption),
    "plan_broken_iam1_writer_can_delete.json": ("IAM-1", _break_destructive_grant),
    "plan_broken_iam2_unconstrained_retention.json": ("IAM-2", _break_retention_constraint),
    "plan_broken_kms1_destruction_ungated.json": ("KMS-1", _break_key_destruction_guard),
    "plan_broken_kms2_rotation_enabled.json": ("KMS-2", _break_key_rotation),
    "plan_broken_kms3_seven_day_window.json": ("KMS-3", _break_deletion_window),
    "plan_broken_kms4_symmetric_key.json": ("KMS-4", _break_key_spec),
    "plan_broken_gt18_two_buckets.json": ("GT18-1", _break_single_bucket),
    "plan_broken_plan1_unresolved_policy.json": ("PLAN-1", _break_policy_resolvable),
    "plan_broken_destroy1_key_deleted.json": ("DESTROY-1", _break_destroy),
}

#: The GT18-2 fixture. `.tf.fixture` rather than `.tf`, so that `tofu` never reads it and
#: `terraform fmt -recursive` never rewrites it, while the gate's own scan still can.
FOREIGN_BUCKET_FIXTURE = "foreign_bucket.tf.fixture"


def build_fixture(
    compliant: dict[str, Any], mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Return a trimmed, mutated copy of the compliant plan."""
    trimmed = {key: copy.deepcopy(compliant[key]) for key in FIXTURE_KEYS if key in compliant}
    mutate(trimmed)
    return trimmed


def regenerate_fixtures(*, check_only: bool) -> int:
    """Write, or verify, every broken fixture.

    Args:
        check_only: Compare against what is on disk instead of writing.

    Returns:
        A process exit code.
    """
    if not COMPLIANT_FIXTURE.exists():
        print(f"FAIL      the compliant fixture {COMPLIANT_FIXTURE} is missing")
        return 1
    compliant = json.loads(COMPLIANT_FIXTURE.read_text(encoding="utf-8"))
    drift = 0
    for name, (rule_id, mutate) in sorted(MUTATIONS.items()):
        path = FIXTURE_DIR / name
        rendered = json.dumps(build_fixture(compliant, mutate), separators=(",", ":")) + "\n"
        if check_only:
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current != rendered:
                drift += 1
                print(f"DRIFT {rule_id:<9} {name} differs from the mutation that declares it")
            else:
                print(f"OK    {rule_id:<9} {name}")
        else:
            path.write_text(rendered, encoding="utf-8")
            print(f"WROTE {rule_id:<9} {name}")
    if check_only and drift:
        print(
            f"\n{drift} fixture(s) drifted. Run `python scripts/custody/check_evidence_plan.py "
            "regen-fixtures` and commit the result."
        )
        return 1
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════
#  Commands
# ══════════════════════════════════════════════════════════════════════════════════════

DESTROY_REFUSAL = """\
REFUSED: `infra/envs/evidence` (stack 10-indelible) has no destroy path.

  Ruling CU-11. This stack holds the S3 Object Lock COMPLIANCE bucket, the ECDSA P-256
  log signing key and the CloudTrail that records who touched either.

  Destroying it is not a teardown, it is document destruction:

    * A COMPLIANCE-locked object cannot be deleted by anyone, including the account root,
      so the bucket cannot be emptied and `destroy` will fail partway through and leave
      the stack in a state whose state file no longer matches it.
    * A rebuilt KMS key makes every checkpoint signed by the old key unverifiable. Nobody
      deleted the ledger; the ledger simply stopped being evidence. That is the same
      offence as destruction, committed by accident (BUILD_PLAN.md K6, "fails how").
    * Crypto-shredding is document destruction under ARCHITECTURE.md §11.6, and doing it
      while a `legal_hold` row is open is a matter for counsel, not for a shell.

  `just destroy` tears down stacks 20-platform and 30-app. Those are the ones with a
  destroy path, and that is the whole reason the split exists.

  If a stack genuinely must go: it is a two-person break-glass procedure with the customer
  notified BEFORE the session (§11.6), and it is performed by a human who has read this
  message, not by a recipe that scripted past it.
"""


def command_check(argv: argparse.Namespace) -> int:
    """Run the gate against one plan file."""
    plan = load_plan(Path(argv.plan))
    findings = evaluate(plan)
    if argv.live:
        findings.append(
            Finding(
                "LIVE-1",
                "live-bucket-smoke-check",
                skipped=(
                    "SKIP(no-credentials): --live asks the running bucket whether it "
                    "actually reports COMPLIANCE, and no AWS credentials are valid on this "
                    "machine. This is printed as loudly as a FAIL on purpose — a gate that "
                    "quietly passes because it did not look is worse than no gate."
                ),
            )
        )
    print(f"evidence-plan gate · {plan.path} · format_version={plan.format_version or '?'}")
    for finding in findings:
        print(finding.render())
    failed = [f for f in findings if f.failures]
    skipped = [f for f in findings if f.skipped is not None]
    print(
        f"\n{len(findings) - len(failed) - len(skipped)} passed, {len(failed)} failed, "
        f"{len(skipped)} skipped"
    )
    return 1 if failed else 0


def _selftest_compliant() -> list[str]:
    """Assert the compliant fixture passes every rule, printing each verdict."""
    problems: list[str] = []
    for finding in evaluate(load_plan(COMPLIANT_FIXTURE)):
        if finding.ok:
            print(f"PASS {finding.rule_id:<9} {finding.rule_name}  [compliant fixture]")
        else:
            print(finding.render())
            problems.append(f"{finding.rule_id} rejected the COMPLIANT fixture")
    return problems


def _selftest_one_broken(name: str, rule_id: str) -> list[str]:
    """Assert one broken fixture is refused by the rule that declares it, and only by it."""
    path = FIXTURE_DIR / name
    if not path.exists():
        print(f"MISS {rule_id:<9} {name}")
        return [f"{rule_id}: broken fixture {name} is missing"]
    broken = load_plan(path)
    verdict = evaluate(broken, only=[rule_id])[0]
    problems: list[str] = []
    if verdict.failures:
        print(f"BITE {rule_id:<9} {name}")
        print(f"        {verdict.failures[0].splitlines()[0]}")
    else:
        problems.append(f"{rule_id}: {name} was NOT rejected — the rule asserts nothing")
        print(f"LIMP {rule_id:<9} {name} was accepted by the rule that declares it")
    # A fixture must break ONE rule. A mutation that trips three rules proves that
    # something failed, not that this rule works.
    collateral = [f.rule_id for f in evaluate(broken) if f.failures and f.rule_id != rule_id]
    if collateral:
        print(f"     {'':<9} (also tripped {collateral} — mutation is not surgical)")
    return problems


def _selftest_tree() -> list[str]:
    """Assert GT18-2 accepts the real tree and refuses the committed foreign-bucket fixture."""
    problems: list[str] = []
    tree_problems = scan_for_foreign_checkpoint_buckets(INFRA_ROOT)
    if tree_problems:
        problems.append("GT18-2 rejected the real tree: " + "; ".join(tree_problems))
        print(f"FAIL GT18-2    the repository tree: {tree_problems[0]}")
    else:
        print("PASS GT18-2    no checkpoint bucket outside the evidence stack  [real tree]")

    fixture = FIXTURE_DIR / FOREIGN_BUCKET_FIXTURE
    if not fixture.exists():
        print(f"MISS GT18-2    {FOREIGN_BUCKET_FIXTURE}")
        return [*problems, f"GT18-2: {FOREIGN_BUCKET_FIXTURE} is missing"]
    staged = _stage_foreign_fixture(fixture)
    if staged:
        print(f"BITE GT18-2    {FOREIGN_BUCKET_FIXTURE}")
        print(f"        {staged[0].splitlines()[0]}")
    else:
        problems.append(f"GT18-2: {FOREIGN_BUCKET_FIXTURE} was NOT rejected")
        print(f"LIMP GT18-2    {FOREIGN_BUCKET_FIXTURE} was accepted")
    return problems


def command_selftest(_argv: argparse.Namespace) -> int:
    """Prove the gate bites: the compliant plan passes, each broken plan fails its rule."""
    if not COMPLIANT_FIXTURE.exists():
        print(f"FAIL      the compliant fixture {COMPLIANT_FIXTURE} is missing")
        return 1

    problems = _selftest_compliant()
    print()
    for name, (rule_id, _mutate) in sorted(MUTATIONS.items(), key=lambda item: item[1][0]):
        problems.extend(_selftest_one_broken(name, rule_id))

    problems.extend(_selftest_tree())

    print()
    if problems:
        for problem in problems:
            print(f"SELFTEST FAILED: {problem}")
        return 1
    print(
        f"selftest OK · {len(RULES)} rules · the compliant plan passes all of them and "
        f"{len(MUTATIONS) + 1} deliberately-broken fixtures are each refused by the rule "
        "that declares them"
    )
    return 0


def _stage_foreign_fixture(fixture: Path) -> list[str]:
    """Run the GT18-2 tree scan over a temporary tree containing the broken fixture.

    The fixture is copied into a scratch directory rather than left in the repository as a
    live `.tf`, because a `.tf` file that declares a second Object Lock bucket would be
    read by `tofu` and rewritten by `terraform fmt` — a test fixture that participates in
    the build is not a fixture, it is a defect.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "infra"
        (root / "envs" / "someone-else").mkdir(parents=True)
        (root / "envs" / "someone-else" / "main.tf").write_text(
            fixture.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return scan_for_foreign_checkpoint_buckets(root)


def command_regen(argv: argparse.Namespace) -> int:
    """Write, or verify, the broken fixtures."""
    return regenerate_fixtures(check_only=argv.check)


def command_destroy_guard(_argv: argparse.Namespace) -> int:
    """Always refuse, with the reason."""
    print(DESTROY_REFUSAL, file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Return the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="check_evidence_plan.py",
        description=(
            "Merge gate over the OpenTofu plan for the indelible evidence stack. "
            "With no arguments it runs the selftest: the compliant fixture must pass every "
            "rule and each deliberately-broken fixture must be refused by the rule that "
            "declares it."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="run every rule against a `tofu show -json` plan")
    check.add_argument("plan", help="path to the plan JSON")
    check.add_argument(
        "--live",
        action="store_true",
        help=(
            "additionally ask the running bucket whether it reports COMPLIANCE. Reports "
            "SKIP(no-credentials) when AWS credentials are absent — loudly, never silently."
        ),
    )
    check.set_defaults(handler=command_check)

    selftest = sub.add_parser("selftest", help="prove every rule bites (the default)")
    selftest.set_defaults(handler=command_selftest)

    regen = sub.add_parser(
        "regen-fixtures", help="rebuild the broken fixtures from the compliant one"
    )
    regen.add_argument("--check", action="store_true", help="assert zero diff instead of writing")
    regen.set_defaults(handler=command_regen)

    guard = sub.add_parser(
        "destroy-guard",
        help="refuse to destroy the indelible stack, with the reason (exit 2)",
    )
    guard.set_defaults(handler=command_destroy_guard)

    parser.set_defaults(handler=command_selftest, live=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except PlanUnreadable as exc:
        print(f"FAIL PLAN-0    {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
