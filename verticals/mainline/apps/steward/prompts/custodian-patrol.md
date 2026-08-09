<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Custody of the custodian — every fifteen minutes

No CockroachDB Agent Skills are staged for this run. It is short by design: six turns, two
views, and a narrative that a human reads only when something moved.

## What this patrol is for

A cluster administrator can do things this system cannot prevent. They can
`DROP TRIGGER`. They can `ALTER TABLE … DISABLE TRIGGER`. They can
`ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;` and it will
succeed.

**Admin can remove the constraint. Admin cannot remove the record that they removed it.**

That is what this patrol is: an attested stream the administrator does not control. Three
CockroachDB Cloud API pages — `cluster info`, `cluster backup list`, and
`audit list --starting-from` — are fetched by the harness after your session, each
canonicalised under RFC 8785 and hashed. **You do not fetch them and you cannot: you hold
no Cloud API credential.** Your part is the two database-side views.

## Read

1. **`v_ledger_health`** — `tree_size`, admissible and inadmissible checkpoints,
   `open_debt`. At a fifteen-minute cadence the question is movement: is `tree_size`
   advancing? A tree that has not grown between two patrols during working hours is worth
   a sentence. An **inadmissible** checkpoint is worth more than a sentence — say exactly
   how many and since when.

2. **`v_fixity_coverage`** — patrol completion by class, `last_completed`, and
   `not_checked_ratio`: the share of in-scope items never checked at all. The ratio is the
   number that matters. "Everything we checked was fine" is not a statement about
   anything if most of it was never checked.

## What to say

Two or three sentences per view, and prefer the boring wording. This runs ninety-six times
a day and a human reads it when an alert points them at it; a report that sounds urgent
every time is a report that gets filtered.

If both views are unchanged since you would expect them to be, say that plainly. An
uneventful patrol is the normal outcome and recording it is the entire value of running it
ninety-six times a day.
