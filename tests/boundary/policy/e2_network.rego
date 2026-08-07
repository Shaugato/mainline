# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0

# E2 — no model network path.
#
# ARCHITECTURE.md §8.2: "Kernel subnets contain no `bedrock-runtime` interface
# endpoint; the kernel SG permits TCP/443 only to the interface-endpoint SG.
# Bedrock is HTTPS — with no endpoint and no 443-to-internet rule there is no
# route, not merely no permission."
#
# §10.3's endpoint matrix marks `bedrock-runtime` ✘ on the kernel row and says
# in words: *that absence is the boundary*.
#
# The reachability argument is made twice, on purpose. Once on subnet placement
# (a human can read it) and once on the security-group graph (a packet obeys it).

package mainline.boundary.e2

import rego.v1

import data.mainline.boundary.plan

internet_cidrs := {"0.0.0.0/0", "::/0"}

plane_tagged_types := {"aws_subnet", "aws_security_group", "aws_vpc_endpoint"}

# --- fail closed on anything this policy cannot see --------------------------

deny contains msg if {
	count(object.get(input.configuration.root_module, "module_calls", {})) > 0
	msg := "E2-MODULE-CALLS-UNANALYSED: this plan contains module calls, whose resource addresses this policy resolves unqualified. Refusing to report a pass over a plan it cannot fully read"
}

deny contains msg if {
	some addr, r in plan.resources
	r.type in plane_tagged_types
	plan.plane(r) == ""
	msg := sprintf("E2-PLANE-UNTAGGED: %s carries no Plane tag; an untagged %s cannot be excluded from the kernel plane", [addr, r.type])
}

deny contains msg if {
	count(plan.kernel_security_groups) == 0
	msg := "E2-KERNEL-SG-ABSENT: no aws_security_group tagged Plane=kernel, so nothing was asserted about the kernel's egress"
}

# --- the bedrock endpoint must be nowhere near the kernel --------------------

deny contains msg if {
	some addr, r in plan.resources
	plan.is_model_endpoint(r)
	some subnet in plan.refs(addr, "subnet_ids")
	plan.plane(plan.resources[subnet]) == "kernel"
	msg := sprintf("E2-BEDROCK-ENDPOINT-IN-KERNEL-SUBNET: %s (%s) is placed in kernel subnet %s", [addr, object.get(r, ["values", "service_name"], "?"), subnet])
}

deny contains msg if {
	some addr, r in plan.resources
	plan.is_model_endpoint(r)
	count(plan.refs(addr, "subnet_ids")) == 0
	msg := sprintf("E2-ENDPOINT-SUBNETS-UNRESOLVED: %s has no resolvable subnet_ids, so it cannot be shown to be outside the kernel subnets", [addr])
}

deny contains msg if {
	some addr, r in plan.resources
	plan.is_model_endpoint(r)
	some sg in plan.refs(addr, "security_group_ids")
	sg in plan.kernel_reachable_security_groups
	msg := sprintf("E2-BEDROCK-ENDPOINT-KERNEL-REACHABLE: %s is fronted by %s, which the kernel security group is permitted to reach", [addr, sg])
}

# --- the kernel's 443 rule ---------------------------------------------------

deny contains msg if {
	some addr in plan.kernel_egress
	plan.port_covered(addr, 443)
	some cidr in plan.literal(addr, "cidr_ipv4")
	cidr in internet_cidrs
	msg := sprintf("E2-KERNEL-443-TO-INTERNET: %s permits kernel TCP/443 to %s; Bedrock is HTTPS, so this one rule reinstates the route the boundary claim rests on", [addr, cidr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	plan.port_covered(addr, 443)
	some cidr in plan.literal(addr, "cidr_ipv6")
	cidr in internet_cidrs
	msg := sprintf("E2-KERNEL-443-TO-INTERNET: %s permits kernel TCP/443 to %s", [addr, cidr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	plan.port_covered(addr, 443)
	count(endpoint_targets(addr)) == 0
	msg := sprintf("E2-KERNEL-443-NOT-ENDPOINT-SG: %s permits kernel TCP/443 but does not target a security group tagged Plane=endpoint", [addr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	plan.port_covered(addr, 443)
	some sg in endpoint_targets(addr)
	s := plan.serves(plan.resources[sg])
	s != ""
	s != "kernel"
	msg := sprintf("E2-ENDPOINT-SERVES-MISMATCH: %s lets the kernel reach endpoint group %s, which is tagged Serves=%s", [addr, sg, s])
}

endpoint_targets(addr) := out if {
	out := {sg |
		some sg in plan.refs(addr, "referenced_security_group_id")
		plan.plane(plan.resources[sg]) == "endpoint"
	}
}

# --- inline egress blocks are unauditable ------------------------------------

deny contains msg if {
	some addr, r in plan.resources
	r.type == "aws_security_group"
	plan.plane(r) == "kernel"
	count(object.get(r, ["values", "egress"], [])) > 0
	msg := sprintf("E2-KERNEL-INLINE-EGRESS: %s declares inline egress blocks, which have no resource address and so cannot be cited in a finding", [addr])
}
