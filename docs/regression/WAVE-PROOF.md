<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE WAVE, BRACKETED — what was true before, what is true after

**Worker:** P4 of the proof-and-polish wave (`docs/demo/proof-and-polish-plan.md` §2).
**Tree:** `D:/CoackroachDBxAWS/mainline`, branch `master`, HEAD `4af05e1` throughout — no
worker in this wave committed, so both runs are the same commit with a different working tree.

This file answers one question and nothing else: **is anything that used to be true no longer
true?** Two full suite runs and two full 31-check guard runs bracket a wave in which seven
workers and two operator-UI leads edited the console, the seed, the copy and the docs at once.

Every number here is read from the `--junitxml` **root element** or from a guard JSON written
in this sitting. **Not one figure was taken from a terminal summary line** — `docs/regression/GUARD.md`
records first-hand why: a run printed a `Timeout` traceback and no summary at all while the XML
on disk carried `tests="579" failures="8"`.

---

## 1 · THE HEADLINE

| | collected | passed | failed | errors | skipped |
|---|---|---|---|---|---|
| **pre-wave anchor** — `qa/final6.xml`, lead-measured | 988 | 987 | 0 | 0 | 1 |
| **before** — `qa/wave-before.xml` | 997 | 996 | 0 | 0 | 1 |
| **after** — `qa/wave-after.xml` | **998** | **997** | **0** | **0** | **1** |

**After ≥ before, and after ≥ pre-wave. Nothing failed, nothing errored, nothing was removed.**
Ten tests were added across the wave and every one of them is named in §3.

| | 31-check guard |
|---|---|
| **before** | 28 PASS · 3 FAIL · 0 SKIP |
| **after** | **30 PASS · 1 FAIL · 0 SKIP** |

Two of the three before-FAILs were the guard's own stale baseline reporting a false regression;
both are gone because the baseline was re-recorded to the measured figure. The one remaining
FAIL is a **known, committed, deliberately-open finding** that this wave did not cause and did
not change (§5.1).

---

## 2 · PROVENANCE — every run, and the command that produced it

The argv is identical for all three suite runs, and is what `SUITE_PATHS` names:

```
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests tests/deploy \
    --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=<out>
```

`--timeout=900` and not the root ini's `timeout=120`: run together the common ancestor is the
repo root, so the root ini binds, and the demo-api fixtures apply the 271-file deploy chain.

| XML | root-element timestamp | `time` | tree at that moment |
|---|---|---|---|
| `qa/final6.xml` | `2026-08-15T18:09:01.467467+10:00` | 205.555 s | HEAD `4af05e1`, clean — measured by the lead |
| `qa/wave-before.xml` | `2026-08-16T01:01:59.650845+10:00` | 272.564 s | HEAD `4af05e1`, **36 paths already changed** |
| `qa/wave-after.xml` | `2026-08-16T01:39:22.159577+10:00` | 197.257 s | HEAD `4af05e1`, 52 paths changed |

Guard runs, both `--junit`-fed so the SUITES numbers are the XML above rather than a fourth run:

| guard JSON | generated (UTC) | seconds | totals |
|---|---|---|---|
| before | `2026-08-15T15:09:19Z` | 112.818 | 31 checks · 28 PASS · 3 FAIL · 0 SKIP |
| after | `2026-08-15T15:43:42Z` | 112.966 | 31 checks · 30 PASS · 1 FAIL · 0 SKIP |

### 2.1 · A limit on `wave-before.xml`, stated rather than buried

The brief asked for `qa/wave-before.xml` **at HEAD `4af05e1` before any other worker had edited
a file. That was no longer possible when P4 started**: `git status --porcelain` already listed
**36 changed paths** — P1's `scripts/demo/demo_ready.py`, P2's and P3's `scripts/proof/*`, the
memory-visible lead's `tests/deploy/test_memory_page_is_served.py`, and the operator-UI leads'
`console/operator.html`, `console/src/operator/` and `console/public/`.

Rather than fabricate a pristine run, this file uses **three** columns. `qa/final6.xml` is the
genuine pre-wave anchor — measured by the lead at HEAD `4af05e1` on a clean tree, from a root
element, with the same argv — and `wave-before.xml` is an honest mid-wave checkpoint. **The
regression question is answered against the pre-wave anchor** (§3.2), which is the stricter of
the two comparisons and the one that actually matters.

### 2.2 · What the after-run covers, and what it does not

Nothing but `qa/wave-after.xml` itself was written to the tree between the run starting
(`01:39:22`) and finishing — verified by walking every mtime in the tree afterwards, so the
snapshot is coherent with the tree it measured.

The run was taken after a 30-minute watch in which the tree had been quiet for **438 seconds**.
Only two paths inside `SUITE_PATHS` moved during the whole wave, and both are accounted for in §3:

* `verticals/mainline/apps/demo-api/tests/test_static_site.py` (P5)
* `tests/deploy/test_memory_page_is_served.py` (memory-visible lead, new file)

**The honest limit:** `tests/deploy/test_docs_are_true.py` carries 54 tests that READ
`README.md`, `docs/TOOL-USAGE.md`, `docs/deploy/JUDGE-PACK.md`, `docs/submission/*` and others,
and P6 and P7 were still editing exactly those files late in the watch. Those 54 tests passed
against the docs **as they stood at `2026-08-16T01:39:22+10:00`**. Any doc edit landing after
that timestamp is not covered by this run, and the cheap confirmation is to re-run the argv in
§2 once the copy workers are finished.

---

## 3 · EVERY DELTA, BY NODE ID

### 3.1 · before → after: **+1**, nothing removed

```
collected       997 ->    998   delta +1
passed          996 ->    997   delta +1
failed            0 ->      0   delta +0
errors            0 ->      0   delta +0
skipped           1 ->      1   delta +0

ADDED   1
  + verticals.mainline.apps.demo-api.tests.test_static_site::
        test_the_console_ci_budget_goes_red_before_the_origin_does
REMOVED 0
```

That single test is **P5's**, and it is the one this wave most needed: it asserts the console's
CI budget goes red *before* the origin starts answering `413` to its own entry JavaScript.

### 3.2 · pre-wave anchor → after: **+10**, nothing removed

```
collected       988 ->    998   delta +10
passed          987 ->    997   delta +10
failed            0 ->      0   delta +0
errors            0 ->      0   delta +0
skipped           1 ->      1   delta +0

ADDED   10
  + tests.deploy.test_memory_page_is_served::test_a_direct_request_for_a_gz_path_is_a_404
  + tests.deploy.test_memory_page_is_served::test_a_file_under_console_public_lands_in_the_served_web_root
  + tests.deploy.test_memory_page_is_served::test_every_file_the_memory_panel_adds_is_under_the_wire_ceiling
  + tests.deploy.test_memory_page_is_served::test_no_memory_file_can_enter_a_budgets_json_root
  + tests.deploy.test_memory_page_is_served::test_the_ceiling_assertion_above_refuses_a_file_that_crosses_it
  + tests.deploy.test_memory_page_is_served::test_the_deploy_chain_copies_the_whole_of_dist_into_the_web_root
  + tests.deploy.test_memory_page_is_served::test_the_memory_page_is_negotiated_to_its_gz_sibling_when_the_client_can_read_one
  + tests.deploy.test_memory_page_is_served::test_the_memory_panel_is_these_files_and_no_others
  + tests.deploy.test_memory_page_is_served::test_the_sibling_this_file_writes_is_the_one_build_lambda_writes
  + verticals.mainline.apps.demo-api.tests.test_static_site::
        test_the_console_ci_budget_goes_red_before_the_origin_does
REMOVED 0
```

**REMOVED is 0 in both directions.** That is the line that matters: a wave this size can grow the
count while quietly deleting a test, and the arithmetic would still look healthy.

### 3.3 · The one skip, unchanged in all three runs

```
verticals.mainline.apps.demo-api.tests.test_gate_run::
    test_payload_validates_against_the_json_schema
```

Reason: *jsonschema is not a workspace dependency*. It is **not** a pass, it is counted
separately everywhere in this file, and the guard's verdict line refuses the word GREEN whenever
a check skips — demonstrated by running `--only LIVE --no-live`, which prints
`VERDICT NO REGRESSION FOUND, 4 of 4 checks NOT RUN — LIVE were skipped, not passed`.

### 3.4 · `tests/demo/` is deliberately not in these counts

P1 added `tests/demo/test_demo_ready.py` and the memory lead added
`tests/demo/test_memory_loop_contract.py`. Both are under the root `testpaths` (`tests`) and are
collected by a bare `pytest`, but **neither is under `SUITE_PATHS`**, which names
`tests/deploy` specifically and not its parent. They therefore do not appear in any figure above.
Named here rather than inferred by arithmetic, because "the count went up by ten" and "ten tests
were added" are different claims.

---

## 4 · THE GUARD, FAMILY BY FAMILY, BEFORE AND AFTER

| family | checks | before | after | moved? |
|---|---|---|---|---|
| KERNEL | 7 | 7 PASS | 7 PASS | no |
| SUITES | 5 | 3 PASS · **2 FAIL** | **5 PASS** | yes — §5.2 |
| BOUNDS | 3 | 3 PASS | 3 PASS | no |
| PRIVILEGES | 5 | 4 PASS · **1 FAIL** | 4 PASS · **1 FAIL** | one check's *content* changed — §5.3 |
| LIVE | 4 | 4 PASS | 4 PASS | no |
| SEED | 7 | 7 PASS | 7 PASS | no |

**KERNEL held exactly.** The four beats came back `PROVEN` with empty caveats, refusal
`23514 gate_closed_when_issued`, drift `P0001 mainline.fn_permit_merge_gate`, admission
`ADMITTED [00000]` — the same SQLSTATEs before and after. A different SQLSTATE would have been a
regression even with the verdict still reading PROVEN, and there was none.

**BOUNDS did not move, in either direction.** `DEFAULT_MAX_RESPONSE_BYTES` is still the
expression `136 * 1024 == 139264`; the straddle is still `138177 < 139264 < 490950`; exactly one
identity object (`assets/index-LoN3Sn_L.js`) is still above the ceiling. Ruling R3 held:
nobody raised the ceiling to make arithmetic agree.

> The BOUNDS family reads `out/lambda/mainline-demo-api-arm64.zip`, which was built at
> `2026-08-15T17:13` and does **not** contain `web/operator.html` or `web/memory.html`. That is
> not a gap this file leaves open — it is the deliberate finding P5 documents in
> `qa/bundle-headroom.json`: no archive was built in this sitting because building one would
> overwrite the deploy artefact from a `dev` buildId. P5 measured the new entry chunk with the
> packer's own gzip function, falsified that function against all 69 objects in the shipping
> archive (69 of 69 byte-identical), and reports the operator-screen entry chunk at
> **137,887** wire bytes — *below* the 138,177 the pre-wave artefact carries. The entry chunk
> shrank. BOUNDS will re-measure it for real the first time the orchestrator rebuilds.

**LIVE and SEED held exactly**, before and after: `ok=true`, `deploy_chain_applied 271`,
`VERDICT PROVEN`, four beats matched by outcome, SQLSTATE, exhibit **and exhibit source**; and
the seeded world still carries 6 defeater options across 2 checks with one digest each, 4 ledger
leaves, 3 nodes, a consistent checkpoint, and the permit, obligations and two enrolled
credentials.

---

## 5 · FINDINGS

### 5.1 · The one FAIL that remains — a known, committed, open finding

```
PRIVILEGES  relations  FAIL   expected mainline_api reaches every relation the code reads or writes
                              observed 2 shortfall(s)
                            ! mainline.exposure_line INSERT; mainline.exposure_receipt INSERT
```

**This wave did not cause it, and this wave did not change it.** The evidence, measured rather
than recalled:

1. `git diff --stat HEAD -- verticals/mainline/apps/demo-api/src` is **empty**. The half of the
   comparison that lives in this repository is byte-identical to HEAD `4af05e1`.
2. The requirement is real: `transitions.py:891` issues `INSERT INTO mainline.exposure_receipt`
   and `transitions.py:969` issues `INSERT INTO mainline.exposure_line`.
3. The committed matrix `verticals/mainline/db/GRANTS.yaml:644-649` grants **SELECT only**, on
   purpose, and says so in a `census_note` on the rows themselves: *"That is R4b of the lead
   plan, OPEN: either the path is unreachable from the deployed surface or it is a 42501 waiting
   for the first judge who drives it. NO GRANT IS ADDED HERE until W1's census or W4's probe
   establishes which — an unreachable code path and a missing privilege look identical from a
   test's side and are different findings."*
4. The cluster agrees with the matrix. Asked directly on `mainline_demo`: `mainline_api` holds
   SELECT `True` / INSERT `False` on both tables. **And membership does not rescue it** —
   `agent_gate` holds INSERT on both in the matrix (`GRANTS.yaml:550-551`) and `mainline_api` is
   a member of `agent_gate`, but on this database `agent_gate` holds *nothing at all* on those
   two tables, so `has_table_privilege`'s membership resolution has nothing to resolve.

So the guard is right, the matrix is right to leave it open, and **it is not this wave's**. It is
recorded here so that nobody reads a green wave as a green cluster. The four filmed beats do not
traverse it: `LIVE gate_run_beats` matched all four, before and after.

**It was not made green.** Softening this check to make the run look clean is the exact move the
PRIVILEGES family exists to refuse.

### 5.2 · The guard's own baseline was 87 tests below the truth, and reported a false regression

`SUITE_BASELINE` read `{collected 911, passed 910}` — measured against `qa/final5.xml` earlier
the same day. Run against the measured before-XML it produced this, verbatim:

```
SUITES  collected  FAIL  expected 911   observed 997
SUITES  passed     FAIL  expected 910   observed 996
VERDICT  REGRESSION - 2 of 5 checks FAILED in SUITES (3 PASS, 0 SKIP)
```

A guard 87 tests below the truth **cannot see 87 tests disappear**. Under ruling R6 it was
re-recorded **upward** to the measured figure — `998 / 997 / 0 / 0 / 1` — carrying the date, the
XML, the argv, and the reason it rose, with each step of `911 → 988 → 998` and the node ids
behind the `+10`. Both checks now PASS against `qa/wave-after.xml`.

**Nothing was re-recorded downward.** A count that falls is a regression that stops the wave; it
is never lowered to make a run green.

### 5.3 · A guard check had gone silent — it was passing while asserting nothing

This is the finding this worker exists to catch, and it was not in the brief.

`PRIVILEGES gate_chain` asks whether `mainline_api` can read every table the merge transaction's
trigger cascade touches — the list discovered the expensive way, one `42501` at a time, after
five live outages in one day. The guard read that list by `ast.literal_eval`ing
`cloud_roles.API_GATE_READ`.

**On 2026-08-15 that assignment stopped being a literal.** It became a generator comprehension
deriving from `GRANTS.yaml`. `literal_eval` cannot evaluate a comprehension, so the reader began
returning `[]` — and the check is `not gate_denied`, which is **vacuously true over an empty
list**. It printed `PASS` while asking the cluster nothing at all. Its own detail line said so in
plain sight and nobody read it:

```
PRIVILEGES  gate_chain  PASS  observed 0 shortfall(s)
                            ! 0 tables from cloud_roles.py:API_GATE_READ
```

It was still printing PASS after the matrix had grown to **fourteen** tables.
`scripts/deploy/cloud_roles.py:546-560` names the defect, the consequence and the repair in its
own margin, and correctly says the repair is not that module's to make. **It is this worker's:
`scripts/qa/regression_guard.py` is a P4-owned file.** Repaired in three parts:

1. The read set now comes from `verticals/mainline/db/GRANTS.yaml` — the file `cloud_roles.py`
   itself derives from — applying the same four predicates in the same order, including *both*
   spellings `_is_gate_chain` accepts (`demand: gate_chain` and `gate_chain: true`). The reader
   was checked against `cloud_roles.API_GATE_READ` and reproduces it exactly: **14 objects,
   identical set**. The literal reader is kept as a fallback so `--cloud-roles` remains a
   falsification seam.
2. **An empty read set is now a FAIL**, never a pass. A check that iterates nothing reports no
   shortfalls for exactly the same reason it would report no successes.
3. A new `--grants-matrix` flag points the check at a planted copy of the matrix.

The check now reads **14 tables** and all 14 hold — a real PASS where there was a vacuous one.

**Falsified before being believed**, against temp copies in a scratch directory; no file this
worker does not own was edited, and both plants were deleted:

| plant | what was planted | the guard's answer, verbatim |
|---|---|---|
| **A** | a `demand: gate_chain` row naming `mainline.p4_no_such_table` | `FAIL … observed 1 shortfall(s) over 15 table(s)` · `! mainline.p4_no_such_table SELECT` |
| **B** | every `gate_chain` marker stripped, so the read set resolves empty | `FAIL … observed 0 shortfall(s) over 0 table(s)` · `! NOTHING WAS CHECKED - the gate-chain read set resolved empty` |

Plant B is the important one: **it is the exact condition that was silently passing**, and it now
goes red.

### 5.4 · Two documents are now stale, and neither is P4's to edit

Reported, not touched, because a worker editing a file it does not own is how a wave loses track
of itself:

* **`docs/regression/GUARD.md:66-69`** states the SUITES baseline as *"911 collected / 910
  passed"*. That is now `998 / 997`. The same file's PRIVILEGES paragraph says *"**10 tables**
  from `API_GATE_READ`"*; the matrix now carries **14**, and the sentence describing the read set
  as coming from `cloud_roles.API_GATE_READ` is superseded by §5.3.
* **`docs/regression/GUARD.md`'s plant P4** — a temp copy of `cloud_roles.py` with a bogus
  relation added to the tuple — no longer discriminates, exactly as `cloud_roles.py:558-560`
  predicted. **Plants A and B in §5.3 above are its replacement** and are ready to be transcribed.
* **`scripts/deploy/cloud_roles.py:546-560`** carries a margin note beginning *"ONE CONSUMER
  STILL READS THIS BY PARSING THIS FILE, AND IT NO LONGER MATCHES"*. That is no longer true — the
  repair it prescribes has landed. Its cross-reference to `gate_chain_reads` *"(line 827)"* is
  also stale; the function is now at line 961.

---

## 6 · WHAT P4 CHANGED

Only in `scripts/qa/regression_guard.py`, the one code file P4 owns:

| change | why |
|---|---|
| `SUITE_BASELINE` `911/910` → `998/997` | R6, §5.2 — re-recorded upward with date, XML, argv and the named `+10` |
| `gate_chain_reads()` rewritten to read `GRANTS.yaml` | §5.3 — the check had gone silent |
| `gate_chain` FAILs on an empty read set | §5.3 — a loop over nothing cannot fail |
| `--grants-matrix` flag added | a falsification seam for the new source |
| module docstring: the fifth PRIVILEGES trap | a trap nobody wrote down is a trap that gets re-sprung |

`ruff check` passes and `ruff format --check` reports the file already formatted. `mypy` reports
**8 errors — the identical 8 it reports on the HEAD version of the same file** (psycopg
`fetchone()` Optional narrowing in `family_seed`, which P4 did not touch). No new type error was
introduced. No ratchet, assertion, `HONESTY.md` or `CI-STATE.md` was weakened; no
`continue-on-error` or `|| true` exists anywhere in this worker's output.

Nothing was committed. No `terraform` verb ran, no AWS API was called, no SSM parameter was
written, and no credential appears in any artefact — the DSN is read from `.env` and redacted
before it reaches any file.

---

## 7 · REPRODUCE

```bash
# the two suite runs, identical argv
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests tests/deploy \
    --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=qa/wave-after.xml

# the counts, from the ROOT ELEMENT and never a terminal tail
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -c \
  "import xml.etree.ElementTree as ET; r=ET.parse('qa/wave-after.xml').getroot(); \
   s=r if r.tag=='testsuite' else r.find('testsuite'); print(dict(s.attrib))"

# the full 31-check guard, fed the XML above so SUITES is not re-run
D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/qa/regression_guard.py \
    --junit qa/wave-after.xml --kernel-database w_p4 --json qa/regression-guard.json
```

Exit `0` when no check FAILED, `1` when any did. Today it exits `1`, for §5.1 and for nothing
else.

---

## 8 · VERDICT

**NO REGRESSION WAS INTRODUCED BY THIS WAVE.**

998 collected, 997 passed, 0 failed, 0 errors, 1 skipped — up 10 from the pre-wave 988, with
every added test named and **zero tests removed**. KERNEL, BOUNDS, LIVE and SEED held exactly.
SUITES went from red to green because the guard's baseline was corrected upward to the truth,
never downward to fit a run. The single remaining FAIL is a finding the repository had already
written down and deliberately left open, and it is unchanged.

The wave also cost the repository nothing and gained it one thing it did not have this morning:
a `gate_chain` check that is once again capable of failing.
