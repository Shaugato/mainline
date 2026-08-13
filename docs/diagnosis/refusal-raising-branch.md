<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The raising branch of `trappoint.explain_refusal`, and the counter that reaches it

**Worker:** `w3-raising-branch` · **Measured 2026-08-13 on TRAPPOINT**, commit `073dfea`
**plus this wave's uncommitted working tree** (see §4 — the distinction turns out to be the
whole story), `.venv` pytest 9.1.1 / psycopg 3.3.4, local node CockroachDB CCL **v26.2.5**
on `127.0.0.1:26257`. Fixture database `w3_demo_api_123396ff6486` — the session-scoped
`demo_database`, 271 migrations plus `demo_world.sql` + `demo_permit.sql` applied through
`scripts/deploy/seed_demo.py`'s own applier, marker `built_at 2026-08-13T06:10:42Z`. Every
number below is the output of a statement printed beside it, and **every statement is a
read**. Nothing in this work touched a seed, a migration, a ceiling or an assertion.

## Verdict

`test_refusal_row_factory.py` needs, and has always needed, **a permit whose projected
counter is zero**. It named `gate_closed_when_issued` as the way to get one, and that was
true of the world the fixture used to BUILD. It is not true of the world the fixture now
APPLIES, and it cannot become true again. **Five of the six permit counter constraints
have a genuinely zero counter on the deployed seed**; all five raise `P0001`;
`identity_conserved_when_issued` is the one this file now uses. The assertion, the `0119a`
migration, `demo_world.sql` and `demo_permit.sql` are all untouched.

## 1 · The failure, reproduced in isolation

```
$ .venv/Scripts/python.exe -m pytest \
      verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py \
      --crdb=reuse -q --tb=short --timeout=180
........FF...                                                            [100%]
test_refusal_row_factory.py:361: assert explained is None
E   AssertionError: assert {'class': 'gate', 'constraint': 'gate_closed_when_issued',
    'diagnosis': 'declarative', 'gate_epoch': 1, ...} is None
test_refusal_row_factory.py:390: assert declined[0] is None and declined[1] is not None
2 failed, 11 passed in 139.93s (0:02:19)
```

The module runs alone, so this is **precondition drift, not cross-test contamination**.
Both negative controls passed.

## 2 · All six counters, measured

`0050_permit.sql:114-122` declares seven CHECK constraints on `mainline.permit`; six are
single-counter refusals and `0119a_fn_explain_refusal.sql` has one branch each (lines 112,
184, 214, 244, 274, 304). Each branch reads its counter and then

```sql
IF v_value IS NULL OR v_value <= 0 THEN
  RAISE EXCEPTION USING ERRCODE = 'P0001',
    MESSAGE = 'TRAPPOINT: the projected counter is zero — this refusal is not
               reproducible against the current row';
END IF;
```

On the seed's **one** permit — `dec0de00-0006-4000-8000-000000000001`,
`state='dispositioned'`, `gate_epoch=1`:

| counter | value | constraint (`0050`) | `explain_refusal` answers |
|---|---:|---|---|
| `open_blocking` | **1** | `gate_closed_when_issued` | **RETURNS** `diagnosis: declarative` |
| `open_residue` | **0** | `identity_conserved_when_issued` | **RAISES** `P0001` *not reproducible* |
| `open_conflicts` | **0** | `conflicts_resolved_when_issued` | **RAISES** `P0001` *not reproducible* |
| `open_warrants` | **0** | `no_open_warrant_when_issued` | **RAISES** `P0001` *not reproducible* |
| `unmodelled_asset_count` | **0** | `boundary_certified_when_issued` | **RAISES** `P0001` *not reproducible* |
| `unmet_floor_count` | **0** | `reading_floor_when_issued` | **RAISES** `P0001` *not reproducible* |

The right-hand column is `trappoint.explain_refusal('permit', <permit_id>, <constraint>,
NULL)` called once per row, and then `refusal._explain` itself, which returns `(None,
'TRAPPOINT: the projected counter is zero — this refusal is not reproducible against the
current row')`. `'not reproducible' in why_not` is **True** for all five.

Supporting counts in the same database: `mainline.permit` 1 row, `mainline.blocking_check`
1 row (`virulence='blood_major'`, **no** live disposition), `mainline.disposition` **0**
rows, `mainline.identity_residue` **0** rows.

## 3 · Why the old constant broke, and why it cannot come back

Two independent reasons, and the first is the one that actually happened.

**(a) The fixture's world was replaced.** `conftest.py` used to BUILD a world; it now
APPLIES the deployment's. Both worlds were measured on the same node on 2026-08-13:

| | permit | state | `open_blocking` | checks | dispositions |
|---|---|---|---:|---:|---:|
| the world the fixture used to build | `80c6bd4a-56e4-4ebf-b4dd-770e61ad5dcc` | `draft` | **0** | 1 | 1 live, `applied` |
| the world the deployment seeds | `dec0de00-0006-4000-8000-000000000001` | `dispositioned` | **1** | 1 | **0** |

The first row is `w3_demo_api_57a490c845e1` (marker `built_at 2026-08-13T10:59:18Z`),
produced by running this module against a checkout of commit `073dfea`. The second is
`w3_demo_api_123396ff6486`, produced by the working tree. **Five fixture databases still
on the node divide cleanly along that line**, which is the corroboration that this is a
world swap and not a one-off:

| database | built_at (UTC) | permit | state | `open_blocking` |
|---|---|---|---|---:|
| `w3_demo_api_d2a5ddd092e1` | 2026-08-12 23:48:37 | `3ccb6348-…` | `draft` | **0** |
| `w3_demo_api_57a490c845e1` | 2026-08-13 10:59:18 | `80c6bd4a-…` | `draft` | **0** |
| `w3_demo_api_123396ff6486` | 2026-08-13 06:10:42 | `dec0de00-0006-…` | `dispositioned` | **1** |
| `w3_demo_api_a9a973a40eec` | 2026-08-13 08:36:37 | `dec0de00-0006-…` | `dispositioned` | **1** |
| `w3_demo_api_a9373e7b6eb4` | 2026-08-13 08:36:51 | `dec0de00-0006-…` | `dispositioned` | **1** |

The two with a random-uuid `draft` permit are the ones built by the old fixture; the three
with `dec0de00-0006-…` are the ones built by the rewritten one. `git show
HEAD:verticals/mainline/apps/demo-api/tests/conftest.py | grep -c
'_deployer\|_Seed\|demo_world'` returns **0**; the working tree's copy is **+364/-563**
uncommitted against it. So the premise did not rot — the ground under it was deliberately
replaced by the rewrite that stopped the fixture inventing a subject, and this file was not
told. **`gate_closed_when_issued` genuinely raised against the parallel world.** It stopped
the day the fixture became honest, and nothing noticed because nothing ran this lane
against a cluster.

**(b) It could not be restored even if someone wanted to.** `open_blocking` is the counter
the demo exists to move, and four other places require it non-zero on this permit:

| file:line | assertion |
|---|---|
| `src/mainline_demo_api/gate_run.py:115` | `CF01_EXHIBIT: Final = "gate_closed_when_issued"` |
| `tests/test_gate_run.py:667-668` | `open_blocking_projected >= 1`, `open_blocking_derived >= 1` |
| `tests/test_gate_run.py:678` | beat 2 is `23514` naming `gate_closed_when_issued` |
| `tests/test_transitions.py:543` | the kernel refusal names `gate_closed_when_issued` |

One permit cannot have that counter both non-zero for beat 2 and zero for this file.

**Why `open_residue` and not the other four zeros.** It is the one whose being zero is a
claim the demo MAKES rather than an absence nobody got round to seeding.
`permit.open_residue` is projected by `fn_residue_counter` over `mainline.identity_residue`
(`0145b_trg_residue_project.sql:54-56`); that table holds 0 rows, and `demo_world.sql` §7
says the same of the commit it seeds — *"Nothing in this world is residue"* — which is why
its `cbm_account` is a balanced zero the conservation view can be asked to confirm on
camera.

## 4 · A warning this cost a run to learn, and it is W6's warning

The first falsification attempt was run in `git worktree add … 073dfea`, a clean checkout of
the commit. **The planted defect passed 14/14 there** — because that checkout carries the
OLD `conftest.py` and therefore the old world, in which the old constant is correct. A
falsification harness that plants a defect into a *checkout of HEAD* will silently certify
fixes that are not fixes, for as long as this wave's work is uncommitted. It must copy the
**working tree**. Recorded here because `w6-falsification-audit` is told to plant "by hand
in a scratch copy of the working tree" and the difference is not cosmetic.

A second trap in the same place: a fresh checkout of `073dfea` produces four migration
files whose bytes differ from this machine's working tree —
`0054_asset_edge.sql`, `0065_mechanism_predicate.sql`, `0069_carried_disposition.sql`,
`0152_v_blame_origin.sql`, LF in the commit and CRLF on disk — while `git diff` reports the
tree clean:

```
0054_asset_edge: blob=b91710c26a2f… worktree(hash-object)=8a837da05c27…
git diff --stat -- <all four>        # empty
git ls-files -v -- <all four>        # H, H, H, H — no assume-unchanged
```

`conftest._fingerprint()` hashes every migration's bytes, so those four alone move the
fixture database name. That is why the first attempt built a second database instead of
adopting the one every other measurement in this wave is made against. There is no
repository-root `.gitattributes` (only
`verticals/mainline/apps/console/fixtures/.gitattributes` and
`packages/mainline-agentkit/tests/cassettes_live/.gitattributes`), so nothing normalises
these paths today and a CI runner will compute a different fingerprint from this laptop and
rebuild all 271 migrations every job.

## 5 · What changed, and what did not

Changed, in `verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py` only:

* `_RAISES` is `identity_conserved_when_issued`; `_RAISES_COUNTER` / `_RAISES_COUNTER_SQL`
  name and read the counter it depends on.
* The module docstring carries all six measurements, the date, the database, both worlds
  in §3(a), and the contradiction in §3(b).
* The two failing tests' docstrings record which counter was measured and when.
* One test added — `test_the_counter_behind_the_raising_constraint_is_zero` — which reads
  `mainline.permit.open_residue` and fails with the counter's value and the instruction
  *"do NOT reshape the seed to restore this number"* if it ever stops being zero. Same
  instrument as the file's two existing negative controls: a measurement pinned as a
  premise, allowed to fail, updated deliberately. The module is therefore 13 tests → 14.

**Not changed, deliberately:** `assert "not reproducible" in why_not or "drift" in why_not`
is byte-identical; no regex widened; nothing `xfail`ed; `0119a_fn_explain_refusal.sql`
untouched (it carries `@rendered-by trappoint render` and `trappoint render --check` is a
zero-diff assertion); `demo_world.sql` and `demo_permit.sql` untouched; `refusal.py` and
`scenario.py` untouched — the defect was never in them.

## 6 · Falsification

Plant: `_RAISES` and its counter put back to `gate_closed_when_issued` / `open_blocking`,
in a scratch copy of the **working tree** (§4), against the same fixture database
`w3_demo_api_123396ff6486` — 149 s, i.e. adopted rather than rebuilt.

```
..F......FF...                                                           [100%]
FAILED …::test_the_counter_behind_the_raising_constraint_is_zero
E  AssertionError: mainline.permit.open_blocking is 1, not 0, on the seeded permit, so
   trappoint.explain_refusal will now DECOMPOSE 'gate_closed_when_issued' instead of
   refusing to (0119a:189). … do NOT weaken the assertions below, and do NOT reshape the
   seed to restore this number.
   assert 1 == 0
FAILED …::test_the_declined_branch_declines_identically_under_both_factories
E  AssertionError: assert {'constraint': 'gate_closed_when_issued',
   'diagnosis': 'declarative', ...} is None
FAILED …::test_the_savepoint_fence_survives_a_raise_inside_one_open_transaction
3 failed, 11 passed in 149.25s (0:02:29)
```

Unplanted, same file, same ground: **14 passed in 149.35 s**. The scratch tree is discarded;
nothing was planted in the repository.

The new message is the point of the exercise: the two original tests say *a dict is not
None*, and the premise test says *which counter, what value, and what not to do about it*.

## 7 · What this does not fix, and one thing worth a lead's ruling

These two tests exercise the **zero-counter guard** (`0119a:189` and its five siblings).
`0119a`'s *other* raising branch inside a counter constraint — the drift guard, `v_open_n =
0` while the counter is non-zero (`0119a:168`, `:393`) — fires when the projection
**disagrees with the re-derived witness set**. On this seed it is reachable only through
`gate_closed_when_issued`, whose counter is 1 and whose witness row exists, so reaching it
needs the two to disagree, which is a WRITE — and this file's docstring promises *"NOTHING
HERE WRITES"*.

`test_gate_run.py`'s beat 3 already drives exactly that disagreement, forging the counter
out of band (`test_gate_run.py:706-712`, `counter_forced_to == 0`), but it asserts the
**kernel's** refusal (`P0001 mainline.fn_permit_merge_gate`) and not `explain_refusal`'s.
So `'projected counter disagrees with the re-derived witness set — refusing on drift'` is,
on the demo seed, **asserted by no test in this suite**. Closing it means either a write
inside this file — a contract change, and a lead's call, not mine — or an assertion added
to beat 3's payload in `test_gate_run.py`, which is `w5-order-independence`'s file.
Recorded, not acted on.
