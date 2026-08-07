# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0

# E1 — no model IAM.
#
# ARCHITECTURE.md §8.2: the `mainline-kernel` task role carries a permissions
# boundary with an explicit Deny on `bedrock:*`, `bedrock-runtime:*` and
# `bedrock-agentcore:*`.
#
# This policy is deliberately STRICTER than the Python twin in one place: it
# requires an Action-based unconditional Deny with `Resource: "*"` and does not
# reason about `NotAction`. A NotAction-shaped deny may well be sound, but an
# auditor should not have to work that out, and the two implementations
# disagreeing is information rather than noise.

package mainline.boundary.e1

import rego.v1

import data.mainline.boundary.plan

denied_actions := {"bedrock:*", "bedrock-runtime:*", "bedrock-agentcore:*"}

kernel_roles contains addr if {
	some addr, r in plan.resources
	r.type == "aws_iam_role"
	plan.plane(r) == "kernel"
}

deny contains msg if {
	count(kernel_roles) == 0
	msg := "E1-KERNEL-ROLE-ABSENT: no aws_iam_role tagged Plane=kernel; E1 cannot be satisfied by a plan that does not contain the subject of the claim"
}

deny contains msg if {
	some role in kernel_roles
	count(plan.refs(role, "permissions_boundary")) == 0
	msg := sprintf("E1-BOUNDARY-UNRESOLVED: %s has no permissions_boundary reference this plan can follow to a policy document", [role])
}

deny contains msg if {
	some role in kernel_roles
	some policy in plan.refs(role, "permissions_boundary")
	count(statements(policy)) == 0
	msg := sprintf("E1-BOUNDARY-UNPARSEABLE: boundary policy %s attached to %s has no readable Statement list", [policy, role])
}

deny contains msg if {
	some role in kernel_roles
	some policy in plan.refs(role, "permissions_boundary")
	count(statements(policy)) > 0
	some action in denied_actions
	not unconditional_deny(policy, action)
	msg := sprintf("E1-DENY-MISSING: boundary %s on role %s does not carry an unconditional Deny with Resource \"*\" covering %s", [policy, role, action])
}

statements(policy_addr) := ss if {
	raw := object.get(plan.resources, [policy_addr, "values", "policy"], "")
	is_string(raw)
	raw != ""
	doc := json.unmarshal(raw)
	ss := statement_list(doc)
}

statement_list(doc) := ss if {
	is_array(doc.Statement)
	ss := doc.Statement
}

statement_list(doc) := ss if {
	is_object(doc.Statement)
	ss := [doc.Statement]
}

unconditional_deny(policy_addr, action) if {
	some s in statements(policy_addr)
	lower(object.get(s, "Effect", "")) == "deny"
	not has_condition(s)
	resource_is_star(s)
	some a in action_list(s)
	covers_action(a, action)
}

has_condition(s) if {
	c := object.get(s, "Condition", {})
	count(c) > 0
}

resource_is_star(s) if {
	object.get(s, "Resource", null) == "*"
}

resource_is_star(s) if {
	r := object.get(s, "Resource", null)
	is_array(r)
	"*" in r
}

action_list(s) := actions if {
	a := object.get(s, "Action", null)
	is_array(a)
	actions := a
}

action_list(s) := actions if {
	a := object.get(s, "Action", null)
	is_string(a)
	actions := [a]
}

covers_action(pattern, _) if {
	pattern == "*"
}

covers_action(pattern, action) if {
	pattern == action
}

covers_action(pattern, action) if {
	endswith(pattern, "*")
	startswith(action, trim_suffix(pattern, "*"))
}
