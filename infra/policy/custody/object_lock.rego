# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ══════════════════════════════════════════════════════════════════════════════════════
#  S3 OBJECT LOCK — the half of ruling CU-10 an OPA-native pipeline can run
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Input is `tofu show -json <planfile>` — the same document
# `scripts/custody/check_evidence_plan.py` reads. Two implementations of one policy is a
# deliberate and unusual choice, so the reason is stated rather than assumed:
#
#   * The PYTHON gate is authoritative and is what CI runs today. It is stdlib-only, it
#     needs nothing installed, and it carries the fixture harness that proves each rule
#     bites — `python scripts/custody/check_evidence_plan.py` and a green line is the
#     merge gate.
#   * THIS FILE is for the customer's pipeline, not for ours. A mining company's platform
#     team already runs `conftest`/OPA over every plan, and a control they can read in the
#     language their own gate speaks is a control they will actually enforce. Shipping the
#     rules in their dialect is the difference between "MAINLINE checks this" and "our
#     change management checks this".
#
# **NOT EXECUTED IN THIS REPOSITORY'S CI, and said so here rather than discovered later.**
# `opa` is not installed on the machine this file was written on, so it has never been
# run — not against the compliant fixture and not against the broken ones. Treat it as a
# specification of the rules in Rego, verified only by review, until a CI lane runs
# `conftest test -p infra/policy/custody infra/policy/custody/fixtures/*.json` green. The
# Python gate has no such caveat: every rule in it is observed refusing a committed
# fixture.
#
#   conftest test --policy infra/policy/custody \
#     infra/policy/custody/fixtures/plan_compliant.json
#
# Rego v1 syntax (`if` / `contains`), which OPA 1.0 requires and OPA >= 0.59 accepts.

package custody.object_lock

import rego.v1

# The tag the evidence-store module stamps on every checkpoint resource. Rules key off the
# tag and not off a resource name, because a name is a convention and a tag is in the plan.
evidence_class_tag := "mainline:evidence-class"

checkpoint_class := "checkpoint"

retention_years_floor := 7

retention_days_floor := 2555

# S3 actions that remove evidence, or remove the control that protects it.
#
# `s3:DeleteObject` is here even though a locked object version cannot be deleted, because
# a DELETE MARKER can still be placed on top of one and AWS states that delete markers are
# not WORM-protected regardless of any retention period or legal hold. Hiding a checkpoint
# is not deleting it and works just as well on a reader who does not already suspect.
forbidden_actions := {
	"s3:DeleteObject",
	"s3:DeleteObjectVersion",
	"s3:BypassGovernanceRetention",
	"s3:PutBucketVersioning",
	"s3:PutObjectLockConfiguration",
	"s3:DeleteBucket",
	"s3:DeleteBucketPolicy",
}

# ── helpers ───────────────────────────────────────────────────────────────────────────

# A function rather than a partial rule: `managed("aws_s3_bucket")` reads the same in every
# rule below and avoids the multi-value-rule-with-a-key form, which is the corner of Rego
# most likely to differ between OPA versions.
managed(resource_type) := [change |
	some change in input.resource_changes
	change.mode == "managed"
	change.type == resource_type
]

checkpoint_buckets contains change if {
	some change in managed("aws_s3_bucket")
	change.change.after.tags[evidence_class_tag] == checkpoint_class
}

# An IAM action pattern reaches a concrete action. `s3:*`, `*` and `s3:Delete*` all reach
# `s3:DeleteObject`; a rule that compared exact strings would pass `s3:*`, which is the
# most common way this control is actually lost.
action_matches(pattern, action) if {
	lower(pattern) == lower(action)
}

action_matches(pattern, action) if {
	endswith(pattern, "*")
	prefix := trim_suffix(pattern, "*")
	startswith(lower(action), lower(prefix))
}

statements_of(document) := value if {
	parsed := json.unmarshal(document)
	value := parsed.Statement
}

# ── OL-1 · Object Lock is enabled AT BUCKET CREATION ──────────────────────────────────
#
# There is no API that retrofits Object Lock onto an existing bucket. GT-18 has no
# fallback: this is right on the first apply or it is a new bucket.

deny contains msg if {
	count(checkpoint_buckets) == 0
	msg := sprintf(
		"OL-1 bucket-object-lock-at-creation: no aws_s3_bucket carries %s=%q. A rule with nothing to check is a rule that has stopped checking.",
		[evidence_class_tag, checkpoint_class],
	)
}

deny contains msg if {
	some bucket in checkpoint_buckets
	bucket.change.after.object_lock_enabled != true
	msg := sprintf(
		"OL-1 bucket-object-lock-at-creation: %s has object_lock_enabled=%v. Object Lock can only be turned on when the bucket is created (GT-18).",
		[bucket.address, bucket.change.after.object_lock_enabled],
	)
}

# ── OL-2 · versioning is Enabled ──────────────────────────────────────────────────────

deny contains msg if {
	some bucket in checkpoint_buckets
	count([v |
		some v in managed("aws_s3_bucket_versioning")
		v.module_address == bucket.module_address
	]) == 0
	msg := sprintf(
		"OL-2 bucket-versioning-enabled: %s has no aws_s3_bucket_versioning. Object Lock requires versioning, and without it an overwrite is a deletion.",
		[bucket.address],
	)
}

deny contains msg if {
	some versioning in managed("aws_s3_bucket_versioning")
	some configuration in versioning.change.after.versioning_configuration
	configuration.status != "Enabled"
	msg := sprintf(
		"OL-2 bucket-versioning-enabled: %s has versioning status %q, not \"Enabled\".",
		[versioning.address, configuration.status],
	)
}

# ── OL-3 · COMPLIANCE, for at least seven years ───────────────────────────────────────

deny contains msg if {
	some bucket in checkpoint_buckets
	count([c |
		some c in managed("aws_s3_bucket_object_lock_configuration")
		c.module_address == bucket.module_address
	]) == 0
	msg := sprintf(
		"OL-3 object-lock-compliance-retention: %s has no aws_s3_bucket_object_lock_configuration, so the bucket would accept writes with no default retention at all — and PutObject succeeds silently in that case.",
		[bucket.address],
	)
}

deny contains msg if {
	some configuration in managed("aws_s3_bucket_object_lock_configuration")
	some rule in configuration.change.after.rule
	some retention in rule.default_retention
	retention.mode != "COMPLIANCE"
	msg := sprintf(
		"OL-3 object-lock-compliance-retention: %s sets mode %q. GOVERNANCE is bypassable by any principal holding s3:BypassGovernanceRetention, which makes the object a copy rather than a commitment.",
		[configuration.address, retention.mode],
	)
}

deny contains msg if {
	some configuration in managed("aws_s3_bucket_object_lock_configuration")
	some rule in configuration.change.after.rule
	some retention in rule.default_retention
	is_number(retention.years)
	retention.years < retention_years_floor
	msg := sprintf(
		"OL-3 object-lock-compliance-retention: %s retains for %d years, below the %d-year custody floor.",
		[configuration.address, retention.years, retention_years_floor],
	)
}

deny contains msg if {
	some configuration in managed("aws_s3_bucket_object_lock_configuration")
	some rule in configuration.change.after.rule
	some retention in rule.default_retention
	is_number(retention.days)
	retention.days < retention_days_floor
	msg := sprintf(
		"OL-3 object-lock-compliance-retention: %s retains for %d days, below the %d-day custody floor.",
		[configuration.address, retention.days, retention_days_floor],
	)
}

# ── OL-4 · public access blocked, all four ────────────────────────────────────────────

deny contains msg if {
	some block in managed("aws_s3_bucket_public_access_block")
	some setting in {"block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"}
	block.change.after[setting] != true
	msg := sprintf(
		"OL-4 public-access-blocked: %s has %s=%v, not true.",
		[block.address, setting, block.change.after[setting]],
	)
}

# ── OL-5 · no crypto-shredding surface under the evidence ─────────────────────────────
#
# AWS states it plainly: if you encrypt objects with SSE-KMS and the key is deleted, the
# objects may become unreadable. A checkpoint note is a public commitment carrying no
# personal information, so SSE-KMS buys no confidentiality here and adds a delete button to
# the one bucket whose entire purpose is that it has none.

deny contains msg if {
	some encryption in managed("aws_s3_bucket_server_side_encryption_configuration")
	some rule in encryption.change.after.rule
	some default in rule.apply_server_side_encryption_by_default
	default.sse_algorithm != "AES256"
	msg := sprintf(
		"OL-5 no-crypto-shredding-surface: %s uses sse_algorithm %q. The checkpoint bucket uses SSE-S3 so that deleting a KMS key cannot make the evidence unreadable (ARCHITECTURE.md §11.6: crypto-shredding is document destruction).",
		[encryption.address, default.sse_algorithm],
	)
}

# ── IAM-1 · no principal may hold a destructive object action ─────────────────────────

deny contains msg if {
	some policy in managed("aws_s3_bucket_policy")
	some statement in statements_of(policy.change.after.policy)
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	some action in forbidden_actions
	action_matches(pattern, action)
	msg := sprintf(
		"IAM-1 no-destructive-object-actions: %s statement %q allows %s (matched by %q).",
		[policy.address, object.get(statement, "Sid", "<unnamed>"), action, pattern],
	)
}

# ── IAM-2 · a retention grant must be constrained by condition ────────────────────────
#
# `s3:PutObjectRetention` and `s3:PutObjectLegalHold` are required merely to SEND the
# x-amz-object-lock-* headers on PutObject, so banning them outright would leave the writer
# unable to lock anything. An UNCONSTRAINED grant, however, is the power to shorten a
# retention or lift a hold — so the grant is legal only alongside the three Deny statements
# that pin it to COMPLIANCE, the full term, and hold-ON.

deny contains msg if {
	some policy in managed("aws_s3_bucket_policy")
	statements := statements_of(policy.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	some action in {"s3:PutObjectRetention", "s3:PutObjectLegalHold"}
	action_matches(pattern, action)
	not has_mode_guard(statements)
	msg := sprintf(
		"IAM-2 retention-grants-are-constrained: %s allows %s with no Deny on s3:object-lock-mode StringNotEquals COMPLIANCE.",
		[policy.address, action],
	)
}

deny contains msg if {
	some policy in managed("aws_s3_bucket_policy")
	statements := statements_of(policy.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	action_matches(pattern, "s3:PutObjectRetention")
	not has_term_guard(statements)
	msg := sprintf(
		"IAM-2 retention-grants-are-constrained: %s allows s3:PutObjectRetention with no Deny on s3:object-lock-remaining-retention-days NumericLessThan %d.",
		[policy.address, retention_days_floor],
	)
}

deny contains msg if {
	some policy in managed("aws_s3_bucket_policy")
	statements := statements_of(policy.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	action_matches(pattern, "s3:PutObjectLegalHold")
	not has_hold_guard(statements)
	msg := sprintf(
		"IAM-2 retention-grants-are-constrained: %s allows s3:PutObjectLegalHold with no Deny on s3:object-lock-legal-hold StringNotEquals ON.",
		[policy.address],
	)
}

has_mode_guard(statements) if {
	some statement in statements
	statement.Effect == "Deny"
	statement.Condition.StringNotEquals["s3:object-lock-mode"] == "COMPLIANCE"
}

has_term_guard(statements) if {
	some statement in statements
	statement.Effect == "Deny"
	to_number(statement.Condition.NumericLessThan["s3:object-lock-remaining-retention-days"]) >= retention_days_floor
}

has_hold_guard(statements) if {
	some statement in statements
	statement.Effect == "Deny"
	statement.Condition.StringNotEquals["s3:object-lock-legal-hold"] == "ON"
}

# ── GT18-1 · exactly one checkpoint bucket ────────────────────────────────────────────

deny contains msg if {
	count(checkpoint_buckets) > 1
	msg := sprintf(
		"GT18-1 single-checkpoint-bucket-in-plan: %d checkpoint buckets in one plan. There is one place a stranger is told to look for the commitments, and two is one more than that.",
		[count(checkpoint_buckets)],
	)
}

# ── PLAN-1 · the gate must be able to READ the policy ─────────────────────────────────
#
# A bucket policy that is "known after apply" is a policy this gate cannot evaluate, and a
# gate that cannot read the policy must refuse rather than shrug. The fix is in the module:
# derive the bucket ARN from its name (`arn:<partition>:s3:::<name>` needs no account and
# no region) instead of from `aws_s3_bucket.…arn`.

deny contains msg if {
	some policy in managed("aws_s3_bucket_policy")
	policy.change.after_unknown.policy == true
	msg := sprintf(
		"PLAN-1 policy-documents-resolvable: %s has a policy that is \"known after apply\". Derive resource ARNs from inputs, or run the gate against a post-apply plan.",
		[policy.address],
	)
}

# ── DESTROY-1 · the indelible stack has no destroy path ───────────────────────────────

deny contains msg if {
	some change in input.resource_changes
	"delete" in change.change.actions
	change.change.before.tags["mainline:indelible"] == "true"
	msg := sprintf(
		"DESTROY-1 no-destroy-of-indelible-resources: %s is planned for deletion. `just destroy` must be honest about which stacks cannot be destroyed (CU-11).",
		[change.address],
	)
}

# `Action` is a string or an array of strings; normalise it so one rule handles both.
cast_array(value) := [value] if {
	is_string(value)
}

cast_array(value) := value if {
	is_array(value)
}
