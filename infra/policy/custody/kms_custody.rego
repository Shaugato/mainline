# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ══════════════════════════════════════════════════════════════════════════════════════
#  THE LOG SIGNING KEY — crypto-shredding is document destruction
# ══════════════════════════════════════════════════════════════════════════════════════
#
# ARCHITECTURE.md §11.6 states it as a rule of law rather than of engineering: *"the KMS
# key policy denies ScheduleKeyDeletion and DisableKey to every principal except a
# two-person break-glass role, unconditionally while any legal_hold row is open, and the
# demo/prod split reuses the key across rebuilds — a recreated key means yesterday's ledger
# is unreadable, which is the same offence committed by accident."*
#
# That sentence contains the whole of this file. A deleted signing key does not delete one
# checkpoint; it makes **every checkpoint ever signed by it** unverifiable at once. Nobody
# has to touch the ledger. The ledger simply stops being evidence, and the only people who
# find out are the ones who tried to rely on it.
#
# Input is `tofu show -json <planfile>`.
#
# **NOT EXECUTED IN THIS REPOSITORY'S CI.** `opa` is not installed on the machine this file
# was written on, so it has never been run against any fixture. The authoritative,
# fixture-proven implementation of these rules is
# `scripts/custody/check_evidence_plan.py` (rules KMS-1 … KMS-4). This file is the same
# policy in the dialect a customer's own change-management pipeline already speaks —
# verified by review only, until a CI lane runs `conftest` green. Saying so here is
# cheaper than being asked.
#
# ── WHAT THIS FILE CANNOT EXPRESS, AND WHY THAT IS SAID OUT LOUD ──────────────────────
#
# The "unconditionally while any `legal_hold` row is open" half of §11.6 is a condition on
# a DATABASE FACT. No key policy and no plan-time rule can see it. It belongs in an
# organisation-level SCP fed by the custodian patrol, and it is NOT implemented by anything
# in `infra/`. Its absence is a stated gap, not an oversight. A policy file that implied
# otherwise would be the exact overclaim this domain exists to refuse.

package custody.kms

import rego.v1

deletion_window_floor := 30

key_spec := "ECC_NIST_P256"

key_usage := "SIGN_VERIFY"

signing_algorithm := "ECDSA_SHA_256"

# The two calls that end the log. `DeleteImportedKeyMaterial` is here because a key with
# imported material can be emptied without being deleted, which reads as availability and
# behaves as destruction.
destructive_actions := {
	"kms:ScheduleKeyDeletion",
	"kms:DisableKey",
	"kms:DeleteImportedKeyMaterial",
}

keys contains change if {
	some change in input.resource_changes
	change.mode == "managed"
	change.type == "aws_kms_key"
}

action_matches(pattern, action) if {
	lower(pattern) == lower(action)
}

action_matches(pattern, action) if {
	endswith(pattern, "*")
	startswith(lower(action), lower(trim_suffix(pattern, "*")))
}

cast_array(value) := [value] if {
	is_string(value)
}

cast_array(value) := value if {
	is_array(value)
}

statements_of(document) := value if {
	parsed := json.unmarshal(document)
	value := parsed.Statement
}

# ── KMS-1 · destruction is denied to everyone but break-glass ─────────────────────────
#
# The idiom is Deny + NotPrincipal: deny these actions to every principal EXCEPT the listed
# one. It is also the sharpest edge in IAM — a role ARN in `NotPrincipal` does not cover the
# assumed-role session ARN in every evaluation context, which is why the module lists both
# forms. What this rule checks is that the statement EXISTS and covers both actions; that
# it lists both ARN forms is a review point called out in the module README.

deny contains msg if {
	some key in keys
	statements := statements_of(key.change.after.policy)
	some action in {"kms:ScheduleKeyDeletion", "kms:DisableKey"}
	not guarded(statements, action)
	msg := sprintf(
		"KMS-1 key-destruction-denied-outside-break-glass: %s has no Deny/NotPrincipal statement covering %s. A recreated key makes yesterday's ledger unverifiable — the same offence as destruction, committed by accident (ARCHITECTURE.md §11.6).",
		[key.address, action],
	)
}

guarded(statements, action) if {
	some statement in statements
	statement.Effect == "Deny"
	count(object.get(statement, "NotPrincipal", {})) > 0
	some pattern in cast_array(statement.Action)
	action_matches(pattern, action)
}

# An Allow of a destructive action to a principal the Deny/NotPrincipal statement does not
# exempt re-opens the hole the Deny closed.
deny contains msg if {
	some key in keys
	statements := statements_of(key.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	some action in destructive_actions
	action_matches(pattern, action)
	some principal in cast_array(statement.Principal.AWS)
	not principal in exempt_principals(statements)
	msg := sprintf(
		"KMS-1 key-destruction-denied-outside-break-glass: %s statement %q allows %s to %q, which the Deny/NotPrincipal statement does not exempt.",
		[key.address, object.get(statement, "Sid", "<unnamed>"), action, principal],
	)
}

exempt_principals(statements) := {principal |
	some statement in statements
	statement.Effect == "Deny"
	some principal in cast_array(object.get(statement, "NotPrincipal", {"AWS": []}).AWS)
}

# ── KMS-2 · no rotation on the log key ────────────────────────────────────────────────
#
# AWS cannot rotate an asymmetric KMS key at all. `enable_key_rotation = true` on a key
# that is supposed to be `ECC_NIST_P256` is therefore either a setting that does nothing
# while telling a reader it does something, or evidence that the key is symmetric and the
# whole signing path is wrong.

deny contains msg if {
	some key in keys
	key.change.after.enable_key_rotation == true
	msg := sprintf(
		"KMS-2 no-key-rotation: %s sets enable_key_rotation=true. AWS cannot rotate an asymmetric key; this is a no-op that misleads, or the wrong key type.",
		[key.address],
	)
}

deny contains msg if {
	some key in keys
	is_number(key.change.after.rotation_period_in_days)
	msg := sprintf(
		"KMS-2 no-key-rotation: %s sets rotation_period_in_days=%v.",
		[key.address, key.change.after.rotation_period_in_days],
	)
}

# ── KMS-3 · the deletion window is the maximum, and the key is enabled ────────────────
#
# The window is the ONLY time anyone has between a scheduled deletion and an unverifiable
# ledger. Seven days is the minimum AWS permits and it trades three weeks of notice for
# nothing.

deny contains msg if {
	some key in keys
	is_number(key.change.after.deletion_window_in_days)
	key.change.after.deletion_window_in_days < deletion_window_floor
	msg := sprintf(
		"KMS-3 no-short-deletion-window: %s sets deletion_window_in_days=%d, below the %d-day maximum. That window is the only time anyone has to notice a scheduled deletion and cancel it.",
		[key.address, key.change.after.deletion_window_in_days, deletion_window_floor],
	)
}

deny contains msg if {
	some key in keys
	key.change.after.is_enabled == false
	msg := sprintf(
		"KMS-3 no-short-deletion-window: %s is disabled. A disabled signing key cannot sign a checkpoint, and a log that stops checkpointing stops being evidence sixty seconds later.",
		[key.address],
	)
}

# ── KMS-4 · the key is the one C2SP note type 0x02 requires ───────────────────────────

deny contains msg if {
	some key in keys
	key.change.after.customer_master_key_spec != key_spec
	msg := sprintf(
		"KMS-4 signing-key-spec: %s has customer_master_key_spec %q, not %q. C2SP note type 0x02 is ECDSA P-256 only (ruling CU-3).",
		[key.address, key.change.after.customer_master_key_spec, key_spec],
	)
}

deny contains msg if {
	some key in keys
	key.change.after.key_usage != key_usage
	msg := sprintf(
		"KMS-4 signing-key-spec: %s has key_usage %q, not %q.",
		[key.address, key.change.after.key_usage, key_usage],
	)
}

# ── KMS-5 · kms:Sign reaches one role, and only for one algorithm ─────────────────────
#
# ARCHITECTURE.md §10.3: `relay_task` is the SOLE holder of `kms:Sign`. "The operator
# re-signed the history" must require compromising KMS rather than reading a secret, and
# that sentence stays true only while the grant has one principal on it.
#
# The algorithm condition is not decoration: a key that will sign under any algorithm is a
# key whose signatures a verifier has to be told how to check, and the verifier's whole
# claim is that it needs to be told nothing.

deny contains msg if {
	some key in keys
	statements := statements_of(key.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	action_matches(pattern, "kms:Sign")
	count(cast_array(statement.Principal.AWS)) > 1
	msg := sprintf(
		"KMS-5 sign-reaches-one-role: %s statement %q grants kms:Sign to %d principals. The sole holder is the relay task (ARCHITECTURE.md §10.3).",
		[key.address, object.get(statement, "Sid", "<unnamed>"), count(cast_array(statement.Principal.AWS))],
	)
}

deny contains msg if {
	some key in keys
	statements := statements_of(key.change.after.policy)
	some statement in statements
	statement.Effect == "Allow"
	some pattern in cast_array(statement.Action)
	action_matches(pattern, "kms:Sign")
	object.get(statement, ["Condition", "StringEquals", "kms:SigningAlgorithm"], "") != signing_algorithm
	msg := sprintf(
		"KMS-5 sign-reaches-one-role: %s statement %q grants kms:Sign without pinning kms:SigningAlgorithm to %q.",
		[key.address, object.get(statement, "Sid", "<unnamed>"), signing_algorithm],
	)
}
