<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The cluster lane's diagnosis: why a reader had to grep, and what was done about it

**Worker:** W5, LANE-HONEST wave. **Date:** 2026-08-14. **HEAD:** `eefae1c`, branch
`master` (working tree dirty — six workers share it). **Subject:**
`scripts/ci/lane_log_digest.py`, `scripts/ci/cluster_lane_report.py`,
`.github/workflows/cluster-tests.yml`.

**Governing ruling:** `docs/leads/lane-honest-plan.md` **R6**. This document is the
measurement behind that ruling, the four-part fix it directs, and — the part that matters
most for whoever reads this next — **the reason the CockroachDB container log is kept.**

---

## 0. The finding, in one sentence

> **The cluster lane's diagnosis is not missing and it is not buried in the middle. It is
> at the END of a 1,023-line log, roughly 180 lines above the bottom, with 60 lines of
> CockroachDB session log printed after it — so a reader who opens a failed run lands on
> the database's log and never sees the one assertion that failed.**

Nothing was suppressed and no message was wrong. The lane's error messages are the best in
this repository and none of them was touched by this work. The defect was purely that
**nothing printed the short version**, and the short version is what a reader needs first.

---

## 1. The measurement

Taken by the lane-honest lead over the **full 1,023-line log** of GitHub Actions run
**`31735341117`** (`cluster-tests`, HEAD `eefae1c`), read as a whole log rather than as a
summary. Recorded here so that the fix below can be checked against a number rather than
against an impression.

| region | lines | content |
|---|---|---|
| the assertion that failed | **830** | one line |
| the `FAILURES` block and the verdict | **760–919** | the actual diagnosis |
| `docker logs "${CRDB_CONTAINER}" 2>&1 \| tail -60` | **943–1003** | **60 lines of `4@util/log/event_log.go:90`** |
| GitHub echoing `run:` bodies | **186 lines total** | mostly this repository's (excellent, long) step comments |
| **whole log** | **1,023** | |

The run itself:

```
cluster lane: 528 collected, 518 executed, 10 skipped, 1 failed, 0 errored
1 failed, 517 passed, 10 skipped in 154.21s (0:02:34)
```

One failing assertion, at line 830 of 1,023. **113 of the lines after it are not about
it.** That is why the orchestrator reading this lane had to `grep` for its own failure,
and a lane whose result can only be found with `grep` is a lane whose result most people
will take from the red dot alone.

### 1.1 Why the `run:` echo matters, and why it is not the villain

GitHub echoes the *body* of every `run:` step into the log and does **not** echo `#`
comments that sit above the step. This repository writes long, load-bearing rationale
inside `run:` bodies — 186 of the 1,023 lines are that rationale being printed back. The
prose is worth keeping in full; it simply does not need to be printed twice per run. Moving
it above the step is a pure relocation and is part 4 of the fix.

---

## 2. The four-part fix

All four are **additive**. None removes an assertion, a message, a floor, a ceiling or a
verdict. From ruling **R6**:

| # | change | owner |
|---|---|---|
| 1 | wrap the container log in `::group::` / `::endgroup::` so the UI collapses it | W1 (`cluster-tests.yml`) |
| 2 | make `--summary` carry the failing node ids **and their assertion text** | **W5 — landed, §3** |
| 3 | upload the JUnit XML and the raw pytest stdout as a job artifact | W1 |
| 4 | move long rationale out of `run:` bodies into `#` comments **above** the step | W1 |

W5 additionally wrote `scripts/ci/lane_log_digest.py` (§4), the interface fixed by
`docs/leads/lane-honest-plan.md` §3 and called by W1 from the workflow.

**Part 1 is collapsing, not deleting.** `::group::` folds a block in the GitHub UI; every
line is still in the log and still in `gh run view --log`. A reader who wants the database's
account clicks once. A reader who does not, no longer has it as the last thing on the page.

---

## 3. What `--summary` carries now

`$GITHUB_STEP_SUMMARY` renders at the **top of the run page**, which is where a reader
actually lands — above the job list, before any log is opened. Until 2026-08-14 the cluster
lane's summary carried the *classification* (a counts table: collected, executed, skipped,
known-red still failing, NEW, pytest exit status) but **not the sentence that failed**. So
the one surface positioned where a reader lands was the one surface that did not say what
broke.

`scripts/ci/cluster_lane_report.py` now **appends** a `### failing tests` section beneath
that table. Nothing in the table changed and nothing was replaced. The new section carries,
for every failing node id:

* the id, copy-pasteable;
* its classification — ``known [`slug`]``, `unstable (f/o runs)`, or **NEW** — the same
  classification the log already printed, so the two cannot drift;
* the assertion text, in a fenced block.

Rendered against this wave's real 33-failure run, the section opens:

```
### failing tests

33 failing test(s), each with the assertion that failed. The verdict is above and in the
job's exit status; this section is what failed, not whether the lane passed.

20. known [`reads-payloads-fixture-refuses-to-invent-a-subject`] — `failure` —
    `verticals/mainline/apps/demo-api/tests/test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`
```

### 3.1 Three properties of that section, and why each is written the way it is

**It changes no verdict.** `summary_failures()` is called from `main()` *after* every gate
has already run, and its return value is written to a file. Delete the function and every
refusal in `cluster_lane_report.py` behaves identically. That is the property that made it
safe to add code to the program that owns the verdict. `--pytest-rc` is still final, the
floor and the ceiling still fire, and the refusal of a run whose JUnit records failures
while the caller claims `rc 0` is untouched.

**Its truncation is explicit.** Every failing id is listed. The assertion *text* is rendered
for the first `SUMMARY_ASSERTIONS_RENDERED = 20`, and when there are more the section says
so in words. This is not a display preference: **GitHub truncates `$GITHUB_STEP_SUMMARY` at
1 MiB silently**, and a summary cut off by GitHub is a summary whose end nobody can tell was
removed. An explicit cap that names itself is the alternative to an invisible one. Neither
constant is read by any gate.

**Its code fence is computed, not fixed.** An assertion diff in this repository can contain
a triple backtick, because these messages quote code. A fence the text can close would make
the summary render as garbage from that point down — silently swallowing every failure
listed after it. `_fence()` returns a fence longer than the longest backtick run in the text
it is about to wrap.

### 3.2 The extraction, and the mistake it was written to avoid

pytest's `<failure>` body is the whole longrepr, and **the assertion is at its end**: the
fixture reprs come first, then the test source *including its docstring*, then the `>` line
that failed, then the `E` block, then `file:line: ExceptionType`.

The calibration case is
`test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements` —
**53 lines, 3,554 characters, of which the first ~40 are the test's docstring.** A digest
that truncated from the top would print that docstring and hide the assertion: the 1,023-line
log's defect, faithfully reproduced inside the tool built to end it.

So `assertion_of()` selects the `>` failing statement, the `E` block, and the trailing
location line. Where a body carries **no** `E` block — a fixture that raised during setup,
which is how 13 of the calibration run's 33 cases arrived — it takes the **tail**, and says
that it did, because a tail is a weaker claim than an extracted assertion and the reader must
be able to tell which one they are looking at.

`assertion_of()` is deliberately **not** imported from `lane_log_digest.py`, though the two
do the same job. `cluster_lane_report.py` is the program that must be able to report; an
`import` of a sibling module is a new way for it to fail before it reaches `load_inventory`.
Twenty duplicated lines are cheaper than a new failure mode in the verdict program.

---

## 4. `scripts/ci/lane_log_digest.py`

The CLI is fixed by `docs/leads/lane-honest-plan.md` §3 and W1 calls it from
`cluster-tests.yml`:

```
python scripts/ci/lane_log_digest.py \
  --junit <path to junit xml> \
  --stdout <path to captured pytest stdout> \
  [--summary <path, appended as Markdown>] \
  [--max-failures N]     # default 20
```

> **Note for W1:** `--stdout` needs pytest's output captured to a file. The step named
> **"The suite against the cluster, and the verdict"** (`cluster-tests.yml:319`, and its
> pytest invocation at `:342`, as the file stood at `eefae1c` — W1 owns that file and may
> renumber it, so the step name is the durable reference) currently lets pytest's output
> go straight to the log. A `tee` into the same file that part 3 uploads satisfies both at
> once. The digest **degrades cleanly** if that file is absent — it prints the JUnit-form
> ids with an explanatory note and still exits 0 — so W1 is not blocked either way.

It prints, in this order: the one-line totals from the `<testsuite>` attributes; then each
failing node id with its assertion text; then the skip census grouped by message with
counts.

### 4.1 It exits 0 always, and this is the only property of it that matters

**A repository whose lane can go red in two places has two places a verdict can hide, and
the second one is always the one nobody reads.** The verdict belongs to pytest's exit status
and to `cluster_lane_report.py`. The digest is diagnosis. It therefore exits **0** on a green
run, on a red run, on a missing JUnit, on unparseable XML, on a missing stdout capture and on
a body it could not parse — every failure mode degrades into a printed sentence — and it
emits **no GitHub `::error` or `::warning` annotation at all**, because the annotation channel
is where a reader looks for the verdict and there must be exactly one of those.

Two consequences worth stating, because both are easy to mistake for sloppiness:

* **`--max-failures` is a display cap, not a filter.** The total is always printed, the cap
  names itself in the output, and no gate anywhere reads the number.
* **Printing cannot raise.** The calibration body carries `⚠`; a Windows console defaults to
  cp1252. A diagnosis program that raised `UnicodeEncodeError` while printing the assertion
  it exists to show would fail exactly when the assertion was interesting.

### 4.2 Two judgement calls, recorded so they can be argued with

**Node ids come from pytest's own `short test summary info`, not reconstructed.** JUnit
records `classname` + `name` (`tests.test_reads`), which is not a path. The digest has no
`--suite-root` and must never refuse, so it looks up the id pytest itself printed. Where it
cannot — normal for a *skipped* case, which that block does not list by id — it prints the
JUnit form marked `[junit id]` and explains the marker once. **Inventing a plausible path
would be worse:** a reader would paste it and be told the file does not exist, rather than
that the tool could not resolve it.

**Byte-identical assertion text is folded, with a back-reference.** The calibration run
carried 13 cases sharing one 67-line setup traceback. Printing it 13 times would rebuild the
wall this program exists to end. Each id is still listed, each still prints its headline, and
the fold names the entry holding the identical text and this case's own body length. The
claim is deliberately about the *extracted assertion* and not about the whole body, which may
differ.

---

## 5. WHY THE CONTAINER LOG IS KEPT

**This is the section to read before deleting anything.**

The 60 lines of `4@util/log/event_log.go:90` at lines 943–1003 are the most obviously
deletable thing in the log. They are repetitive, they are last, and they are what a reader
sees first. **Do not delete them, and do not quiet them with a CockroachDB stderr log
filter.**

The reasons, in the order they should be weighed:

1. **It is the only place a database-shaped failure shows up.** When the suite fails for a
   reason that is about the cluster rather than about the code — the container died, the node
   never became ready, a range was unavailable, the session was killed — the pytest output
   shows a connection error and nothing else. The container's own account is the diagnosis.
   The step is titled *"The container's own account of the run"* for that reason.

2. **A log filter would silence exactly the case it exists for.** The tempting fix is to
   suppress `event_log.go` chatter. But the noisy channel and the diagnostic channel are the
   same channel; a filter tuned to today's noise is a filter that will drop tomorrow's
   `panic`. The failure mode of that edit is invisible and arrives on the worst day.

3. **Two workflows stand behind it, in two different ways — checked rather than assumed.**
   `cluster-tests.yml:354-363` argues it in a step comment: the step *"decides nothing, and
   it runs only when the job has ALREADY failed, so it can neither mask a verdict nor create
   one"*, and *"it suppresses nothing: this directory permits exactly one suppressed command,
   `db.yml`'s container cleanup, and a second would make that ban unenforceable."* `db.yml`
   makes the case in **code** rather than in prose, and the stronger of the two: at
   `db.yml:431-432` the container log is dumped on the line immediately after
   `::error::the cluster never answered SQL` — the exact database-shaped failure that pytest
   cannot describe — and again at `db.yml:558-560` as a `Cluster logs on failure` step.
   (Reference is by line number as the files stood at `eefae1c`; W1 owns `cluster-tests.yml`
   and may renumber it.)

4. **It is not the defect.** The defect was that nothing printed the short version — not that
   something printed a long one. Once the digest and the step summary put the failing
   assertion where a reader lands, the container log's position at the bottom stops mattering,
   and part 1 of the fix collapses it behind a `::group::` so it costs a click rather than a
   scroll. **Collapsing is reversible by the reader; deletion is not.**

The general form of the rule, because it will come up again: **a diagnostic that is noisy on
the days it is not needed is not thereby a diagnostic worth removing.** The cost of the noise
is paid on every run; the cost of removing it is paid once, on the run where it was the only
evidence. Those are not comparable quantities, and this repository has already decided which
way it errs.

---

## 6. What was verified, and how

Every number below is from a command run in the same sitting as this document, on
`.venv/Scripts/python.exe`.

**The report's own control set is unchanged and still passes.**

```
.venv/Scripts/python.exe -m pytest tests/ci/test_cluster_lane_report.py --crdb=none -q \
  -p no:cacheprovider --junitxml=<report>
  -> BEFORE this change: tests=116 failures=0 errors=0 skipped=0
  ->  AFTER this change: tests=116 failures=0 errors=0 skipped=0
```

That file demonstrates each of the report's properties **by mutation**, and its `_mutate`
helper refuses an anchor that does not appear in the source **exactly once**. So 116 green
after the edit is direct evidence that no anchored line — `--pytest-rc`'s finality, either
half of the floor, the ceiling, the resolver's refusal, the two `unstable` rules, the
lost-status guard, the schema check — was moved, reshaped or duplicated. That is the check
that mattered, because the edit touched `read_run()` and `main()`.

**The digest was calibrated against real artefacts, not synthetic ones.** Both were produced
by the pinned interpreter against the working tree:

| artefact | shape | what it exercises |
|---|---|---|
| `--crdb=reuse` run | `tests=557 failures=20 errors=13 skipped=0` | 33 failing ids against a default cap of 20; a 53-line assert-set body; 13 bodies with no `E` block; 3,554-character longreprs; non-ASCII |
| `--crdb=none` run | `tests=557 failures=0 errors=0 skipped=213` | the skip census: 213 skips grouped to **1** distinct message |

**Degenerate inputs all exit 0**, checked one at a time: a JUnit path that does not exist; a
file that is not XML; a `--stdout` path that does not exist; a document whose root is
`<testsuite>` rather than `<testsuites>`; `--max-failures 0`; `--max-failures -5`. Each
printed a clear sentence and returned **0**.

**Lint.** `ruff check` and `ruff format --check` clean on both scripts. `ruff`'s `SIM222`
caught a real defect in the first draft of `assertion_of()` — a one-element list is always
truthy, so the fallback branch could never have been reached. It is fixed and the reason is
recorded in the code.

### 6.1 One thing this document does NOT claim

The full-suite `--crdb=reuse` before/after numbers for this wave are reported in W5's
handoff, and they are **not** attributable to this change in either direction: six workers
share one working tree, and the demo-api suite does not import anything under `scripts/ci/`.
The BEFORE reading taken at the start of this task was
`tests=557 failures=20 errors=13 skipped=0` — **not** the lead's clean-tree baseline of
`528 / 1 failed / 1 skipped`, because concurrent edits to `gate_run.py`, `transitions.py` and
the new `defeaters.py` were in the tree at the time. The 116-test control set above is the
measurement that *is* attributable to this change, and it is the one to re-run when
`cluster_lane_report.py` is next edited.

---

## 7. How to read a failed cluster run, once all four parts have landed

1. **Open the run page and read the top.** The step summary now names the failing tests and
   the assertions. For most failures this is where you stop.
2. **If you need more than the assertion**, download the artifact (part 3): the JUnit XML and
   the raw pytest stdout, as files, instead of 1,023 lines of interleaved log.
3. **If the failure looks like the database rather than the code**, expand
   *"The container's own account of the run"*. It is collapsed, not gone. That is what it is
   for.
4. **If the report itself refused to run** — `::error title=the cluster lane cannot be
   reported::` — the inventory or the JUnit is malformed. The refusal names which. It never
   exits 0 and never returns a status quieter than pytest's.

**And the standing rule this whole wave is under:** a collection error, a skip above the
ceiling, or a `NEW` failure is answered by landing what is missing. It is never answered by
lowering `COLLECTED_FLOOR`, by `-k`, by `--deselect`, by stubbing an import, or by editing
any number in this document.

---

## 8. RE-MEASURED AT THE PUBLIC TIP — the defect is MITIGATED, not CLOSED

**Worker:** D3, DOCS-TRUE wave, 2026-08-14. **Run:**
[31770005759](https://github.com/Shaugato/mainline/actions/runs/31770005759) — `cluster-tests`,
push, HEAD **`7535670`**, the public tip. **Job:** `94673769475`, read whole with
`gh api "repos/Shaugato/mainline/actions/jobs/94673769475/logs"`.

§§0–7 above were measured at run **31735341117**, HEAD `eefae1c`. This section re-measures the
same property at the tip, because §0's finding is the kind that decays quietly: a fix lands, a
log grows, and the fix stops being enough without anybody re-reading it.

### 8.1 The line geometry, at the tip, with the command that produced it

| region | run 31735341117 (`eefae1c`) | run 31770005759 (`7535670`) |
|---|---:|---:|
| whole job log | **1,023 lines** | **2,061 lines** |
| `FAILURES` block opens | 760 | **1,283** |
| pytest's `short test summary info` | — | **1,653** |
| the lane's own verdict line (`cluster lane: …`) | — | **1,716** |
| **`lane_log_digest.py` — the one-screen digest** | *did not exist* | **1,742 → ~1,947** |
| `docker logs "${CRDB_CONTAINER}" \| tail -60` | 943–1003 | **1,970 → 2,030** |
| lines of CockroachDB `event_log.go` after the digest | 60 | **58** |
| lines between the end of the digest and the end of the log | *(n/a)* | **≈ 114** |

Counted with `grep -c 'event_log.go'` over the fetched log and by line number, not by
impression — §1's own methodological rule, which was earned on a `tail -25` that cut three
lines off a five-line list.

### 8.2 What improved, stated first because it is real

**The four-part fix landed and it works.** `scripts/ci/lane_log_digest.py` is invoked at line
1742 with `--summary "$GITHUB_STEP_SUMMARY"`, and it printed, for this run, a per-failure
digest naming all eight failing node ids with the assertion text for each, plus a skip census
reading `skips: 1 across 1 distinct message(s)`. **The short version now exists.** §0's
finding — *"nothing printed the short version"* — is discharged.

The digest even carries its own anti-vacuity sentence, which is the standard the rest of this
repository is measured against and is quoted rather than paraphrased:

> *"A skip is indistinguishable from a green tick on a dashboard. This census does not judge
> it — `qa/cluster-known-red.json`'s `floor.max_skipped` does, through
> `scripts/ci/cluster_lane_report.py`."*

### 8.3 What did not close, and is therefore still a live defect

**A reader who opens the failed run and scrolls to the bottom of the raw log still lands on
CockroachDB's session log, not on the diagnosis.** The digest ends around line 1,947; the last
114 lines are artifact-upload chatter and then 58 lines of
`4@util/log/event_log.go:90 … "EventType":"client_session_end"`.

The absolute distance shrank — 113 lines after the assertion at `eefae1c`, ≈114 after the
digest at `7535670` — but **the log itself doubled**, from 1,023 lines to 2,061, and the
proportion of it that is CockroachDB's own event log is unchanged. **The defect §0 describes
is a defect of where a reader lands, and where a reader lands has not moved.**

§5 argues at length for keeping the container log and that argument is not reopened here: the
container's account is what separates *"the code is wrong"* from *"the database was not
there"*, and deleting it to shorten a log would be trading a diagnosis for a scroll bar. **The
finding is not that the container log should go. It is that it should not be the last thing on
the page.**

### 8.4 The one thing this document cannot measure, said rather than assumed

The digest is written to `$GITHUB_STEP_SUMMARY` as well as to stdout, and the rendered summary
appears **above** the job list on the run page — which, if a reader opens the run page rather
than the raw log, means the diagnosis is the first thing they see and this defect is closed for
them. **This document does not claim that, because it cannot check it.** GitHub's API does not
expose which surface an account opened, and `gh run view` returns the log, not the rendered
summary. What is measured here is the raw log, because the raw log is what
`gh run view <id> --log` returns and what an orchestrator or a CI-reading script gets.

**A defect that is closed on one surface and open on another is open.** The cure is one line
of ordering in `.github/workflows/cluster-tests.yml` — emit the digest, or a pointer to it,
*after* the container log rather than before — and that file is not this documents wave's to
edit. Recorded, with the run id and the line numbers, for whoever owns the lane.
