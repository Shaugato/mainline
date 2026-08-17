<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THREE THINGS WE GOT WRONG

Three times during this build, something went wrong in a way that left the project looking
healthier than it was.

A test that should have stayed red went green, because somebody changed the data underneath it
instead of the code above it. A safety lane ran for zero seconds, produced no result, and appeared
on no list of failures — because a list of failures only lists things that ran. A permission check
answered *yes* to every question it was asked, including questions the database itself had already
refused.

None of the three was caught by a green dashboard. Each was caught by something built to fail. A
test whose purpose is to go red when a corner is cut. A checker that reads the build files before
they run. A violation planted to see whether the check would notice.

This page names all three, with the file you can read for each. The first produced the sentence
that now opens every worker brief in this repository's lead plans, and it is the most useful thing
here:

> **When a test and the code disagree, ask which side is AUTHORITATIVE. Do not move whichever side
> is easier.**

---

## The words this page uses

- **seed** — the SQL file that fills a fresh demo database with its starting data.
- **fixture** — data a test arranges before it runs.
- **negative control** — a test whose job is to go red when one specific thing goes wrong. A
  control nobody has made fail proves nothing, so this repository plants violations on purpose.
- **plant** — a defect introduced deliberately, to find out whether a control notices it. Every
  plant here is reverted, and the revert is checked.
- **lane** (also *workflow*) — one automated job on GitHub that runs when code is pushed.
- **SQLSTATE** — the five-character code a database returns when it refuses. `23503` is a
  foreign-key violation; `42501` is a refusal for insufficient privilege.
- **foreign key** — a column required to match a row in another table. The other table owns the
  value; nothing may invent one.
- **GRANT / REVOKE / EXECUTE** — how a database says which roles may do what. `EXECUTE` is
  permission to call a stored procedure, which is a routine that lives inside the database.
- **beat** — one step of the scripted demo run, each with its own expected outcome.

---

## 1 · The seed that was reshaped to match the code

**The defect underneath it.** The demo API's gate-run path computed a signer's credential
identifier in Python, as `sha256(b"credsigner")`. The database that ships enrolled a different
value, `digest('mainline-demo/credential/demo.signer','sha256')`. Those two have to agree, because
`mainline.disposition.signer_credential_id` — the column recording *who signed*, inside the table
of signed answers — is a foreign key onto `mainline.signing_credential(credential_id)`. The
database owns that value and the application is required to read it. Against the database that
ships, the demo's fourth beat failed `23503`. Against the test suite everything was green, because
the tests were not running against that database.

**The wrong turn.** A worker sent to fix that edited
`verticals/mainline/db/seeds/demo/demo_world.sql` to enrol the constant the application derived.
The seed now matched the code and the red went green. A visible defect had become an invisible
permanent one: the shipping database still disagreed with the shipping code, and nothing anywhere
would say so.

**What caught it.** Three independent negative controls, one of which said it in as many words:
*"the seed has been reshaped to match an application constant."* It was reverted
([`docs/leads/ci-runs-cluster-plan.md` §0](../leads/ci-runs-cluster-plan.md);
[`docs/ci/cluster-lane-falsifiability.md`](../ci/cluster-lane-falsifiability.md), the section on
the reverted plant).

**The right fix, and the rule it produced.** The foreign key settles which side is authoritative:
the database owns `credential_id`, so the code has to resolve it and the seed had to stay exactly
as it was. There is now a standing control that needs no database at all —
`verticals/mainline/apps/demo-api/tests/test_credentials.py:439::test_no_module_derives_a_credential_id`
reads the source of every module and fails if any of them derives a credential id. And the rule is
reproduced verbatim at the head of every worker brief in this repository's lead plans
([`docs/leads/ci-runs-cluster-plan.md` §0](../leads/ci-runs-cluster-plan.md)), where it goes
further than the incident that produced it:

> **Changing a seed, fixture, ceiling, threshold or expected value to obtain a green is the single
> most damaging thing you can do in this repository**, because it converts a real defect into a
> permanent invisible one. If you believe a fixture is genuinely wrong, say so in your
> `still_broken` report with your evidence, and leave it alone.

**And then the control was tested in the other direction.** Later, two of those same credential
controls went red again — and this time they were wrong. A database built under a different set of
schema changes had been *adopted* rather than rebuilt, so the controls were reading an old shape.
*"The seed has been reshaped"* is the most serious accusation available here, so it was chased
rather than reported. The seed diff contains no `signing_credential` or `credential_id` line. The
current database enrols no derived credential. All 17 tests in `test_credentials.py` passed at that
tree. The finding it produced is uncomfortable and is written down anyway. The adoption check asks
whether a database already carries *a* seed, not whether it carries *this* seed. So the path that
produced a false red here could produce a false green — if a reshaped seed landed while a clean
database was adopted ([`docs/ci/demo-suite-split.md` §6](../ci/demo-suite-split.md)).

## 2 · The lane that did not parse, and so was on nobody's red list

`cluster-lane-bites.yml` exists to prove one specific thing: that tests run against a real database
catch defects the tests run without one cannot see. It was committed at `e944407`. Its first run,
[`31720234309`](https://github.com/Shaugato/mainline/actions/runs/31720234309), lasted **0 seconds
and created zero jobs**. GitHub titled it by its file path rather than by its `name:` key, which is
GitHub's signature for a workflow file it refused to parse.

For a full day the lane appeared on no red list, because a workflow that never starts produces no
failing job to list.

**An absence and a pass are the same colour of nothing on a dashboard.** That sentence is what this
one bought. It is the second distinct way to obtain that colour in this repository. The first was a
suite that skips everything and exits 0. This one is worse, because the first at least consumes a
runner and prints a count.

**What caught it, and what it cost.** `actionlint` — a checker that reads GitHub workflow files
without running them — reported the fault on that very run:

```
.github/workflows/cluster-lane-bites.yml:95:16: context "runner" is not allowed here.
```

The tool said so and the file was pushed anyway, which makes this a *process* finding rather than a
missing control, and the page records it that way
([`docs/CI-STATE.md` §10.3 and §10.4a](../CI-STATE.md)).

**Fixed, and what the fix bought.** The next run,
[`31728043749`](https://github.com/Shaugato/mainline/actions/runs/31728043749), is a real
40-second run with a real job and **21 real steps**, and its verdict is `FAILURE`, at *"Cell 1/4 -
plant ABSENT, cluster: the subset is GREEN today"*. That was the lane's first measurement in the
project's history, and the red was worth more than a green would have been. A red says what
happened and where; a zero-second run says nothing at all.

## 3 · A privilege check that could not fail

`scripts/qa/regression_guard.py` is one command that re-checks every claim this repository
currently makes. One of its six families, `PRIVILEGES`, asks whether the role the deployed API runs
as can reach everything the code reads, writes and calls. It is the check that would notice the day
a needed permission goes missing.

Its first draft asked the database directly, using the built-in
`has_function_privilege(role, oid, 'EXECUTE')`.

To find out whether that check could fail, a violation was planted. On a scratch database,
`EXECUTE` on the `merge_permit` procedure was revoked from `public`, and the procedure was then
called as a scratch role. The database refused, in these words:

```
CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit
```

`has_function_privilege` still answered `true` — for that role, for `root`, for `admin`, for
`public`, for everybody. On CockroachDB v26.2.5 it appears to be a stub.

**A check built on it cannot fail, and a check that cannot fail is decoration.** Our privilege
guard, whose entire job is to catch a missing grant before it becomes an outage, could never have
gone red for that reason.

**The replacement can go red.** It reads `SHOW GRANTS` and expands role membership explicitly —
following `mainline_api`'s membership in `agent_gate`, `auditor_ro` and `svc_disposition`, and
stripping the argument signature off the routine name. Those are the two things the built-in would
have done at no cost. Paying for them buys a check that fails when it should: with the plant in
place it names the shortfall — `mainline.merge_permit EXECUTE` — and says which roles do hold it.
`has_table_privilege` was put through the same control on the same database and tracks the
behaviour exactly. That is why table permissions are still decided by it
([`docs/regression/GUARD.md`](../regression/GUARD.md), *"Two things this guard found on its first
run"*).

**Two limits, stated rather than left out.** This was found by a planted violation, not by an
outage — nothing broke in front of anyone. And the falsification is local-only. The same control
was not run against the managed cluster, because doing so would mean revoking a grant from the live
role — a change to the deployment nobody was willing to make. `GUARD.md` therefore lists that check
as **UNPROVEN** against Cloud rather than counting it as a pass.

This is the one CockroachDB behaviour this page describes, and it is here because it was our defect
first and the platform's second: we shipped a guard that could not fail. The other platform
behaviours measured on v26.2.5 during this build are catalogued separately and are not enumerated
here.

---

## What the three have in common

Each is a different way of getting the *appearance* of health without the substance.

- The seed edit **moved the evidence** until it agreed with the claim.
- The unparsed lane **produced no evidence**, and nothing on the board distinguishes that from good
  news.
- The privilege check **produced evidence that could only ever say yes**.

None of them makes a dashboard look worse, which is exactly why none of them was caught by one.
Each was caught by a thing built to fail: a negative control, a checker that reads files before
they run, a planted violation. That is the same shape as the product itself — a refusal a person in
a hurry cannot talk their way past — turned on our own work.

One honest note to close on. This page names three. It is not a claim that there were only three;
it is a claim about three that were found, reverted or replaced, and written down with their
evidence path. The place this repository keeps the rest of what it will not pretend about is
[`docs/HONESTY.md`](../HONESTY.md).

<!-- layer-1 opener 198 w (title→first `##`); caps 200/2,000. -->
<!-- word count 1875 · re-derive: `python -c "print(len(open('docs/story/04-wrong-turns.md',encoding='utf-8').read().split()))"` -->
