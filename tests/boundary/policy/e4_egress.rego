# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0

# E4 — no model prompt path.
#
# ARCHITECTURE.md §8.2: "The kernel's only outbound protocols are pgwire and
# HTTPS to enumerated in-VPC endpoints." §10.3: "Kernel: TCP/26257 to the
# database path and TCP/443 to the endpoint SG only — no 443 to 0.0.0.0/0."
#
# E2 asks whether the kernel can reach Bedrock. E4 asks the stronger, duller
# question: what is the complete set of protocols the kernel can speak? A
# boundary argued destination-by-destination is one new destination away from
# being wrong.
#
# The FIS blackhole experiment that §8.2 names as E4's live assertion is
# SPECIFIED AND UNRUN (§19 GT-16). It is recorded as data in
# packages/mainline-boundary/src/mainline_boundary/data/fis-blackhole.yaml and
# asserted by tests/boundary/test_e4_egress.py, not here — a plan cannot speak
# to it either way.

package mainline.boundary.e4

import rego.v1

import data.mainline.boundary.plan

permitted_ports := {443, 26257}

enumerated_destination_planes := {"endpoint", "database"}

deny contains msg if {
	some addr in plan.kernel_egress
	protocol := object.get(plan.resources, [addr, "values", "ip_protocol"], "")
	protocol != "tcp"
	msg := sprintf("E4-PROTOCOL-NOT-TCP: %s uses ip_protocol %q; '-1' makes the protocol set unbounded and UDP is not one of the two protocols §8.2 E4 permits", [addr, protocol])
}

deny contains msg if {
	some addr in plan.kernel_egress
	not plan.single_port(addr)
	msg := sprintf("E4-PORT-RANGE-WIDE: %s does not declare a single from_port == to_port; each permitted protocol must be its own single-port rule so the set can be read off the plan", [addr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	port := plan.single_port(addr)
	not port in permitted_ports
	msg := sprintf("E4-PORT-NOT-PERMITTED: %s permits kernel egress to TCP/%v, outside the closed set {443, 26257}", [addr, port])
}

deny contains msg if {
	not 26257 in observed_ports
	count(plan.kernel_security_groups) > 0
	msg := "E4-PROTOCOL-SET-INCOMPLETE: the kernel has no pgwire egress rule; a kernel that cannot open a database session cannot refuse a merge either — it fails to start"
}

deny contains msg if {
	not 443 in observed_ports
	count(plan.kernel_security_groups) > 0
	msg := "E4-PROTOCOL-SET-INCOMPLETE: the kernel has no HTTPS egress rule to its interface endpoints"
}

# Destinations must be enumerated: an interface-endpoint security group, or a
# managed prefix list carrying the database path. A raw CIDR is not enumeration.
deny contains msg if {
	some addr in plan.kernel_egress
	count(plan.literal(addr, "cidr_ipv4")) > 0
	msg := sprintf("E4-DESTINATION-NOT-ENUMERATED: %s targets a raw IPv4 CIDR; §10.3 requires an enumerated destination", [addr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	count(plan.literal(addr, "cidr_ipv6")) > 0
	msg := sprintf("E4-DESTINATION-NOT-ENUMERATED: %s targets a raw IPv6 CIDR; §10.3 requires an enumerated destination", [addr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	count(destination_planes(addr)) == 0
	msg := sprintf("E4-DESTINATION-UNRESOLVED: %s has no destination this plan can resolve to a Plane-tagged security group or prefix list", [addr])
}

deny contains msg if {
	some addr in plan.kernel_egress
	some p in destination_planes(addr)
	not p in enumerated_destination_planes
	msg := sprintf("E4-DESTINATION-NOT-ENUMERATED: %s targets a %q-plane destination; permitted destination planes are {endpoint, database}", [addr, p])
}

deny contains msg if {
	some addr in plan.kernel_egress
	plan.single_port(addr) == 443
	some p in destination_planes(addr)
	p != "endpoint"
	msg := sprintf("E4-HTTPS-NOT-IN-VPC-ENDPOINT: %s sends kernel HTTPS to a %q-plane destination; §8.2 E4 permits HTTPS only to enumerated in-VPC interface endpoints", [addr, p])
}

observed_ports contains port if {
	some addr in plan.kernel_egress
	port := plan.single_port(addr)
}

destination_planes(addr) := out if {
	out := {p |
		some target in destination_targets(addr)
		p := plan.plane(plan.resources[target])
		p != ""
	}
}

destination_targets(addr) := out if {
	sgs := plan.refs(addr, "referenced_security_group_id")
	pls := plan.refs(addr, "prefix_list_id")
	out := sgs | pls
}
