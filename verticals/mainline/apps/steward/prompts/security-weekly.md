<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Security and governance — weekly

Staged skills: `hardening-user-privileges`, `configuring-audit-logging`,
`auditing-cloud-cluster-security`. Read them for method. Their privilege-enumeration
recipes read `crdb_internal` and `pg_catalog`, which you cannot reach — the grant matrix
lives in `verticals/mainline/db/GRANTS.yaml` and is asserted by the kernel's own test
suite, not by you.

## What this week's review is for

Three questions, in descending order of consequence:

1. **Has the fleet done anything unusual?** `v_agent_actions` gives agent role, tool,
   outcome and count for the last week. What you are looking for is a *shape* change: a
   role using a tool it does not normally use, an outcome distribution that moved, a count
   that collapsed to zero. A role appearing with a tool it has never held before is the
   single most interesting row this view can produce.

2. **Is anything weakened and undispositioned?** `v_weakenings_without_disposition` is the
   flagship question of the whole product: a clause that weakened or removed a control
   written by a severity-4-or-worse incident, with no live disposition against it. Report
   the counts, the worst severity, the most recent date, **and the `ancestry_complete`
   flag** — the counts beneath a `false` are lower bounds, and reporting them as totals
   would be the exact misstatement the flag exists to prevent.

3. **Are dispositions keeping up?** `v_disposition_coverage` gives surfaced against
   dispositioned by quarter, plus orphans. A widening gap is a governance fact; describe
   it and stop there. You have no authority over a disposition, and the system holds none
   you could exercise: a disposition is written only by a human-authenticated path, and no
   agent in this fleet can sign one.

## A note on what a clean week looks like

Zero rows in `v_weakenings_without_disposition` is a good week **only if the view
answered**. Zero rows and a failed read look identical in prose and are opposite in
meaning, so state which one you saw.
