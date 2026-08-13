<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The cluster lane's report, and the controls that can falsify it

**Worker:** W6. **Date:** 2026-08-14. **HEAD:** `e944407` (working tree dirty — five workers
share it). **Subject:** `scripts/ci/cluster_lane_report.py`,
`tests/ci/test_cluster_lane_report.py`, `.github/workflows/cluster-tests.yml:38`.

---

## 1 · The sentence, and why it was false

`cluster-tests.yml:38` tells its reader:

> It also refuses a run whose JUnit XML records failures while its caller claims pytest
> exited 0 — which is the one rewiring that would let a fully-inventoried red run present
> as green. **Both properties are exercised by controls; see that file.**

Measured on 2026-08-14, `tests/ci/` held exactly one file — `test_demo_seed_is_frozen.py`,
which is about the demo seed and says nothing about the report program. The sentence was
false. That matters more than a stale comment usually does, because the program it
describes exists **only** to be a refusal: it classifies failures against an inventory that
is one edit away from being a suppression list, and the argument that it cannot become one
is entirely an argument about its own code. A refusal nobody can falsify is decoration.

The sentence is now true. `tests/ci/test_cluster_lane_report.py` holds 21 controls, they
run in under five seconds, they need no cluster and no network, and they are collected by a
default `pytest` invocation (`testpaths` already names `tests`).

## 2 · What makes each of them a control rather than an assertion

A test that asserts *"the program refuses X"* proves nothing on its own: the program might
refuse X for a reason unrelated to the line the test is nominally about, or refuse
everything, or the test might never reach the code path at all. So **every property is
demonstrated by mutation**:

1. the real source is read off disk;
2. one *named anchor* is replaced by a version of itself with that property removed;
3. the mutant is executed as a live module (never registered in `sys.modules`);
4. the same scenario is driven through `main()` on both, and the control asserts **the real
   program gives the safe answer AND the mutant gives the unsafe one.**

If the second half stops holding, the assertion above it has stopped being evidence, and
the test says so in as many words rather than passing.

`mutate()` refuses an anchor that does not appear **exactly once**. This is the part that
keeps the demonstrations honest over time: a mutation that silently fails to apply produces
a mutant identical to the original, and a negative control against an unmutated program
passes for the wrong reason. When somebody reshapes `cluster_lane_report.py`, these tests go
red asking to be re-anchored — which is a conversation, not a defect.

Two controls are deliberately **positive**:
`test_a_green_run_over_the_floor_is_the_only_thing_that_exits_zero` and
`test_the_resolver_rebuilds_a_real_copy_pasteable_node_id`. Without them, every refusal
control in this file would be satisfied by a program that refuses everything — and a
resolver that refuses everything makes the inventory unmatchable, which is the same defect
wearing the opposite mask.

## 3 · The properties, the mutants, and the scenarios

| property | mutant (the property removed) | scenario | real | mutant |
|---|---|---|---|---|
| `--pytest-rc` is final | `return args.pytest_rc` → `return 1 if verdicts else 0` | every failing node id inventoried in `groups`, pytest exited 2 | **2** | 0 |
| the status is *pytest's value*, not merely non-zero | `return args.pytest_rc` → `return 1` | green XML, `--pytest-rc 5` | **5** | 1 |
| a refusal is never quieter than pytest | — (positive assertion) | no JUnit written, `--pytest-rc 4` | **4** | — |
| floor: no cluster, everything skipped | both floor tests → `if False:` | 186 collected, 186 skipped, rc 0 | **1** | 0 |
| floor: `min_executed` alone | `if run["executed"] < floor[…]` → `if False:` | 30 executed, 0 skipped | **1** | 0 |
| floor: `max_skipped` alone | `if run["skipped"] > floor[…]` → `if False:` | 600 executed, 13 skipped | **1** | 0 |
| ceiling: an inventoried id PASSES | `fixed = sorted(…)` → `fixed = []` | otherwise-perfect green run | **1** | 0 |
| a `classname` naming no file is hard | the `Refusal` → a silent invented id | the unresolvable case **passes** | **1** | 0 |
| `unstable` must carry a measurement | the `isinstance`/`observed > 0` refusal removed | entry with a `reason` and no numbers | **1** | 0 |
| `unstable` is not a home for a failing test | `if failed >= observed:` → `if False:` | entry claiming 3 failures in 3 runs | **1** | 0 |
| a group with no `cause` is refused | — (positive assertion) | `"cause": "  "` | **1** | — |
| the caller's status was dropped | the whole guard → `False` | inventoried failure, `--pytest-rc 0` | **1** | 0 |
| …and dropped in the XML's **body** | the guard as it stood at `e944407` | body has `<failure>`, summary says `failures="0"` | **1** | 0 |
| the guard is dead weight on honest runs | — (regression control) | clean green run | **0** | — |

Two further controls read the **workflow**, because two of the program's properties are
conditional on its caller and the program cannot check its own caller:
`test_the_workflow_hands_the_report_pytests_real_status` (the step still does `rc=$?` and
`--pytest-rc "${rc}"` in one step) and
`test_the_workflows_claim_about_these_controls_is_the_claim_this_file_answers`, which keeps
the sentence in §1 attached to the evidence for it. If that claim is ever withdrawn, the
withdrawal is made in the same commit as the controls it withdraws.

### The scenario choice that carries the resolver control

`test_a_classname_that_names_no_file_is_a_hard_failure` uses a **passing** test as the
unresolvable case, and that choice is the whole control. An unresolvable id on a *failing*
test is reported `NEW` under both the real program and a loosened one, so it cannot tell
them apart. On a *passing* test the two answers diverge completely: the real program refuses
the entire report, and a program whose matcher was loosened invents an id, matches nothing,
says nothing and exits 0. That is what the docstring's *"or, if the matching were loosened,
never reported"* means in practice.

## 4 · The defect a control found, and the one edit it earned

`test_a_body_full_of_failures_under_a_clean_summary_is_refused` **failed against the program
as committed at `e944407`.** Before writing the fix I reproduced it standalone:

```
cluster lane: 501 collected, 501 executed, 0 skipped, 0 failed, 0 errored

  known    [inventoried] failure: …/test_alpha.py::test_one

inventory: 1 known, 1 still failing, 0 now passing, 0 declared unstable, 0 NEW

EXIT CODE AS COMMITTED: 0
```

A JUnit document gives **two** accounts of a run. The `<testsuite>` element carries summary
attributes (`failures`, `errors`); the `<testcase>` children carry the outcomes. Guard 0 —
the guard whose entire subject is *"the caller has been rewired"* — read only the summary:

```python
if pytest_rc == 0 and (run["failures"] or run["errors"]):
```

So a document whose summary read `failures="0"` while its body carried `<failure>` children
went through the floor, the classification and the ceiling and **exited 0**, provided the
node ids were inventoried. The program printed the failure, called it `known`, and returned
green. That is precisely the outcome guard 0 exists to refuse, arriving through the half of
the document guard 0 was not reading.

**The fix adds one clause and relaxes nothing:**

```python
if pytest_rc == 0 and (run["failures"] or run["errors"] or run["bad"]):
```

`run["bad"]` is the parsed body — and it is the authoritative account here, because it is the
account the classification itself is computed from. A program that classifies from the body
while gating on the summary is trusting two different documents.

Three things about this edit, stated because the rule of this wave is that a code change
made to turn a test green is the defect it pretends to fix:

* **It moved the DERIVED side.** The summary attributes are derived by pytest from the
  cases; the cases are the record. The gate was reading the derivation and ignoring the
  record. Nothing authoritative moved.
* **It cannot change the verdict of any real run.** pytest computes those attributes from
  the same cases, so on every honest run the third clause is dead weight.
  `test_the_guard_does_not_fire_on_an_honest_green_run` is the regression control that
  keeps it that way, and the full-suite before/after in `docs/ci/demo-suite-random-order.md`
  shows no node id moved.
* **The mutant for that control is the committed line as it stood at `e944407`**, so the
  defect cannot be reintroduced without this control naming it.

This is the only edit made to `cluster_lane_report.py`, and it is the only one a control
proved was needed.

## 5 · What these controls deliberately do NOT assert

They do not read, pin, or edit the **contents** of `qa/cluster-known-red.json` beyond
checking that the committed file still *loads*. Its `groups` list is a ceiling expected to
be **deleted** rather than edited; a control that pinned its membership would be a second
ceiling somebody has to lower, which is how a ceiling acquires two owners and stops falling.
`qa/cluster-known-red.json` is byte-identical after this work.

They also do not assert anything about *which* tests are currently red. That is the
inventory's job, and duplicating it here would create two places to edit when a test is
fixed — the loophole in a different costume.

## 6 · Two findings about the lane that are NOT mine to repair

Both are reported here rather than routed around.

**(a) The inventory is stale against its own tree, in a way that matters to the CEILING.**
`qa/cluster-known-red.json`'s `reads-payloads-fixture-refuses-to-invent-a-subject` group
still names `cr_id` as the cause; `cr_id` was seeded and the cause is now `commit_v2`, with
`boundary_proof` behind it. Staleness in a `cause` field costs nothing by itself. What is
not free is what happens when W1/W2/W3 land: sixty-three node ids in that group turn green
at once and the CEILING fires — correctly, and by design — telling whoever fixed them to
delete the lines. Whoever lands that wave should expect that red and delete the group rather
than reading the red as a regression. The lead's plan already rules the group is to be
deleted, not edited. (W2 is reporting the same staleness.)

**(b) The FLOOR would refuse the current local run, for a reason that has nothing to do with
the database being absent.** My baseline (§ `docs/ci/demo-suite-random-order.md`) measured
**14 skips against `floor.max_skipped = 1`**, and thirteen of them are one message:

```
tests/test_row_factory_contract.py … 98 of 271 migrations did not apply into
w_w1_rowfactory; the gate objects may be absent.
```

That is a half-built scratch database on this host, not a cluster the lane could not reach —
but the floor cannot tell those apart, and it is right not to try. On a clean CI runner the
scratch database is built fresh, so this may not reproduce there; on this host it is a real
condition somebody should look at before reading a `the cluster lane skipped` verdict as an
infrastructure failure. **`floor.max_skipped` must not be raised to accommodate it** — that
is the single most damaging edit available in that file, and its own `why` field says so.
