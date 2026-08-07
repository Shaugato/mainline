# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0

# Shared plan-reading helpers for the E1/E2/E4 Rego policies.
#
# These policies exist because ARCHITECTURE.md §8.2 says E2 "is the one that
# convinces a security reviewer, because it does not depend on our code being
# correct". A Python checker we wrote is our code. A Rego policy evaluated by
# OPA is not. Where the Python and the Rego disagree, one of them is wrong and
# the suite says so — which is worth strictly more than either alone.
#
# The one structural assumption: everything security-relevant lives in the root
# module. `e2_network.rego` denies outright if the plan contains module calls,
# because this policy resolves configuration references by unqualified address
# and would otherwise silently analyse the wrong thing.

package mainline.boundary.plan

import rego.v1

# Every planned resource, keyed by address. `walk` descends into child_modules
# without needing to know they are there.
resources[addr] := value if {
	walk(input.planned_values, [_, value])
	is_object(value)
	is_string(value.address)
	is_string(value.type)
	addr := value.address
}

# Every configured resource, keyed by address. This is where references live,
# and references are the only way to link a role to its boundary policy while
# the policy ARN is still known-after-apply.
config_resources[addr] := value if {
	walk(input.configuration.root_module, [_, value])
	is_object(value)
	is_string(value.address)
	is_object(value.expressions)
	addr := value.address
}

# The Plane tag (ARCHITECTURE.md §8.1). Total: an untagged resource reports "".
plane(resource) := p if {
	p := lower(object.get(resource, ["values", "tags", "Plane"], ""))
}

# The Serves tag on endpoint-plane resources.
serves(resource) := s if {
	s := lower(object.get(resource, ["values", "tags", "Serves"], ""))
}

# Normalised resource addresses referenced by `<addr>.<attribute>`.
# "aws_iam_policy.kernel_boundary.arn" -> "aws_iam_policy.kernel_boundary".
# Anything that is not an aws_* resource reference (var./local./each.) is
# dropped, and the callers treat an empty result as a violation rather than a
# pass.
refs(addr, attribute) := out if {
	raw := object.get(config_resources, [addr, "expressions", attribute, "references"], [])
	out := {n |
		some x in raw
		parts := split(x, ".")
		count(parts) >= 2
		startswith(parts[0], "aws_")
		n := concat(".", [parts[0], parts[1]])
	}
}

# Literal values an attribute may carry, taken from planned_values first and
# from a configuration constant second, so a rule is caught however it was
# written.
literal(addr, attribute) := out if {
	planned := object.get(resources, [addr, "values", attribute], null)
	configured := object.get(config_resources, [addr, "expressions", attribute, "constant_value"], null)
	out := {v |
		some v in [planned, configured]
		v != null
	}
}

egress_rules contains addr if {
	some addr, r in resources
	r.type == "aws_vpc_security_group_egress_rule"
}

kernel_security_groups contains addr if {
	some addr, r in resources
	r.type == "aws_security_group"
	plane(r) == "kernel"
}

# Egress rules whose source security group is a kernel-plane group.
kernel_egress contains addr if {
	some addr in egress_rules
	some sg in refs(addr, "security_group_id")
	sg in kernel_security_groups
}

# Security groups the kernel is permitted to send packets to.
kernel_reachable_security_groups contains sg if {
	some addr in kernel_egress
	some sg in refs(addr, "referenced_security_group_id")
}

port_covered(addr, port) if {
	from := object.get(resources, [addr, "values", "from_port"], null)
	to := object.get(resources, [addr, "values", "to_port"], null)
	is_number(from)
	is_number(to)
	from <= port
	to >= port
}

single_port(addr) := port if {
	from := object.get(resources, [addr, "values", "from_port"], null)
	to := object.get(resources, [addr, "values", "to_port"], null)
	is_number(from)
	is_number(to)
	from == to
	port := from
}

is_model_endpoint(resource) if {
	resource.type == "aws_vpc_endpoint"
	contains(lower(object.get(resource, ["values", "service_name"], "")), "bedrock")
}
