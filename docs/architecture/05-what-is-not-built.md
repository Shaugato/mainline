<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Chapter 5 — What is not built, and why it is still on the page

*You are here: chapter 5 of 5. Front door: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).
Linked terms are defined in [`GLOSSARY.md`](GLOSSARY.md).*

Chapter 4 ended by saying that some of the boxes on its map are outlines rather than things.
This chapter names every one of them, with the file that measures each, and then says why
they are here rather than deleted.

---

## 1 · Sixty seconds

Twelve items are on this project's not-built list, each written down with the artefact that
measures it. In plain terms:

* **The tamper-evidence machinery — the part that would prove a stored record has not been
  altered since it was stored — is half-built.** Seven of its sixteen checks have never been
  written, and those seven are the ones involving signatures. Nine pass, none fails, seven do
  not run. "Nothing failed" and "everything was checked" are different findings.
* **The reference copy of the shared foundation this product sits on does not install.** It
  refers to two database tables that no file in it creates, so the installer stops at the first.
* **The suite that would certify a build against that foundation has been counted, not passed.**
  Of 71 declared test cases, 10 passed, 6 failed outright, and 55 could not be attempted at all
  — 46 of those 55 because one column is missing from one table.
* **Twenty-one of the project's own thirty safety rules are not yet enforced by the database.**
* **Four designed things have never been demonstrated:** the skills an AI agent would load, the
  model calls in the live request path, one signing step in the second demo, and the long-term
  evidence-preservation machinery.
* **Two measurements show their apparatus rather than a result.** A counter reading zero shows
  the arithmetic exists; it does not show the arithmetic ever had to refuse anything.
* **Every stopwatch reading in the demo was taken on one laptop.**

None of that is a caveat added at the end. Each item below carries the file, the count and the
line a reader can open. Sections 3 to 7 are the twelve items with their mechanism and their
numbers; section 8 is the argument for keeping them visible.

---

## 2 · How to read a number on this page

Three distinctions do most of the work, and collapsing any of them would make this page useless.

| The distinction | Why it matters |
|---|---|
| **failed** vs. **not checked** | A check that ran and disagreed is a finding. A check with no code behind it is an absence. A dashboard that shows one red light for both loses the difference. |
| **red** vs. **could not run** | A test that reached the database and got the wrong answer tells you about the database. A test whose setup statements were refused never asked the database anything. |
| **a counter reading zero** vs. **a demonstrated refusal** | Zero withheld items proves the counting apparatus exists. It does not prove the apparatus would refuse anything. |

**Citations.** A bare number carries `[src: <path>#<pointer>]` into `qa/` or `evidence/`, or
names a line of a document. Digits inside `code spans` are names, not measurements —
[SQLSTATE](GLOSSARY.md#sqlstate) `42P01`, the date `2026-08-15`. Items re-derived in the session
that wrote this page say so; the rest quote the artefact that recorded them, with its date.

---

## 3 · The substrate: not fully installable, and counted rather than passed

**TRAPPOINT** ([glossary](GLOSSARY.md#trappoint)) is the general-purpose layer underneath this
product: a specification, SQL templates, and a machine-readable case list. A **vertical**
([glossary](GLOSSARY.md#vertical)) is a product built on it. MAINLINE is one vertical;
`trappoint_ref` is meant to be a second, minimal one whose only job is to prove the templates
render for somebody other than us.

### Item 1 — the reference vertical refers to two tables nothing creates

`trappoint_ref` refers to `trappoint_ref.clause` and `trappoint_ref.event`, and no migration
under `packages/trappoint-sql/refvertical/sql/` creates either. The installer stops at the first
one it reaches: `trappoint migrate` refuses at `0058_blocking_check` with SQLSTATE `42P01` — the
database saying *that table does not exist* ([`docs/CI-STATE.md:468`](../CI-STATE.md)). The
lane's own census, printed by the job before it refuses, reads:

```
reference vertical: 22 tables created, 12 referenced, 2 with no producer
```

quoted at [`docs/CI-STATE.md:674`](../CI-STATE.md) from job `94445138416`. What closes it is a
`CREATE TABLE` migration for each of the two. What does **not** close it, in the runner's own
words at [`docs/CI-STATE.md:636`](../CI-STATE.md), is narrowing the matrix, skipping the job or
dropping the foreign key — *"each closes the lane by deleting the question"*.

**The consequence for the architecture, stated plainly:** the claim that TRAPPOINT is a substrate
rather than a private template engine rests on two bindings that both render. Today one renders.

### Item 4 — the conformance census is a first count, not a passing suite

The **conformance suite** ([glossary](GLOSSARY.md#conformance)) is the case list whose passing is
the only meaning of "TRAPPOINT-compliant". It has been run once, against a database built from
this tree, and the result is a census:

| | |
|---|---|
| declared cases | **71** [src: qa/conformance-census.json#run/manifest_declared_case_count] |
| passed | **10** [src: qa/conformance-census.json#totals/passed] |
| failed | **6** [src: qa/conformance-census.json#totals/failed] |
| could not run at all | **55** [src: qa/conformance-census.json#totals/cannot_run] |
| errored · pending · skipped | **0 · 0 · 0** [src: qa/conformance-census.json#totals/error, #totals/pending, #totals/skipped] |

**46 of the 55 share one cause.** The census records it verbatim: *"CANNOT RUN: legal world could
not be built at 'clause\_version' — column `body_sha256` does not exist. Nothing was asked of the
gate, so this is not a red gate: it is a setup statement the database refused."*
[src: qa/conformance-census.json#systemic_causes/0/n]. One missing column keeps 46 of the 71
declared cases from ever reaching their subject — the **gate** being the set of database objects
that refuse the illegal write ([glossary](GLOSSARY.md#gate)).

The census is *complete as a census* — every declared case carries a status and every non-passing
case carries a reason naming an object [src: qa/conformance-census.json#completeness/complete].
That is the only thing it is. Ten passing cases out of seventy-one is not a compliance claim,
and this document makes none.

### Item 3 — 21 of 30 MAINLINE invariants are pending

MAINLINE keeps its own catalogue of thirty rules the database is supposed to enforce.
**9 are marked enforced and 21 are marked pending**; the intentional-red message in the build
records the figure at [`.github/workflows/ci.yml:850`](../../.github/workflows/ci.yml). The
board breaks the 21 down at [`docs/CI-STATE.md:846-847`](../CI-STATE.md):

```
5 HELD (the red law refuses on these — see REFUSED below) · 2 RED (an owning test fails; the
law holds) · 14 UNWITNESSED (no owning test resolves at all).
```

*Held* means the catalogue wants to promote a rule to enforced and a red-before-green law refuses,
because promoting a rule on tests that all pass would record an enforcement nobody ever observed
refusing anything. *Unwitnessed* means no owning test resolves at all — fourteen of the twenty-one
are in that third state, the weakest of the three, and it is not rounded up into either other.

---

## 4 · The custody chain: nine checks hold, seven have no code

**Custody** ([glossary](GLOSSARY.md#custody)) is the separate machinery for proving that a
recorded piece of evidence has not been altered since it was recorded — hashes, a Merkle tree
(a structure where each record's hash folds into its parent, so changing any record changes a
single value at the top), and cosignatures from independent parties.

### Item 2 — the census: 9 passed, 0 failed, 7 not checked, of 16

The offline bundle verifier is run as an external check by the test census, and the result is
recorded rather than summarised. Every figure below is at
`qa/test-state.json#external_checks/custody_bundle_verification`:

| | | pointer under that key |
|---|---|---|
| total checks | **16** | `counts/total` |
| passed | **9** | `counts/passed` |
| failed | **0** | `counts/failed` |
| not checked | **7** | `counts/not_checked` |
| exit code | **2** — *"everything that ran held, and at least one check did not run"* | `exit_code` |

The seven, by name, at `not_checked` under that same key:

| # | check | what it would have proved |
|---|---|---|
| 4 | `log_signature` | somebody signed the log |
| 5 | `rfc3161_upper_bound` | a timestamp authority says it existed no later than *t* |
| 6 | `beacon_lower_bound` | a public randomness beacon says it existed no earlier than *t* |
| 7 | `witness_quorum` | independent parties cosigned the same root, at least one adverse |
| 8 | `archive_object_lock` | the archive copy cannot be overwritten |
| 11 | `gate_self_attestation` | the gate's own source text is inside the attestation |
| 12 | `webauthn_reverification` | a human re-authenticated with a hardware key |

That list is the entire cryptographic half. `0 failed` and `7 not checked` are kept in separate
columns on purpose; [`docs/CI-STATE.md:470`](../CI-STATE.md) states the rule in one line —
*"marking a not-checked check as passed"* is what does **not** turn the lane green.

### Item 11 — the offline verifier exits `1`, and what that does and does not prove

A stranger can run the verifier with no account and no credential. [`VERIFY.md:48-49`](../../VERIFY.md)
records what it printed on `2026-08-12`:

```
16 checks | 8 passed | 1 failed | 7 not checked
exit 1: 1 finding(s). This bundle does not verify.
```

The one failure is `canonicaliser_identity`: the bundle's signed hash of its own
[canonicaliser](GLOSSARY.md#canonicalisation) disagrees with the canonicaliser the verifier
runs, so eight checkpoints' signed lines disagree with the code that would recompute them.
**The check is catching real drift**, which is why a bundle carries the hash of its own
canonicaliser in the first place.

**What Tier 1 genuinely proves** is that the Merkle structure is internally consistent and that
the exhibited refusal is inside it. **What it does not prove is that anybody signed it.**

**This page does not reconcile its two readings of the same tool, and neither should a reader.**
The census above (`9 passed, 0 failed`, exit `2`) was generated `2026-08-09`
[src: qa/test-state.json#generated_utc]; `VERIFY.md`'s reading (`8 passed, 1 failed`, exit `1`)
was taken `2026-08-12`; and [`docs/CI-STATE.md`](../CI-STATE.md) §2.4 records a third state in
which check 10 passes. Three dates, three readings, one command. The resolution is to run the
command — `python -m trappoint_verify.cli verify --bundle evidence/reference-ledger/bundle.json`
— which needs nothing from us. **Seven of the sixteen will not run whichever day you run it.**

---

## 5 · Four things that are designed and not demonstrated

### Item 5 — Agent Skills: DESIGNED, not exercised

Two authored skills and one staged upstream contribution are on disk under `skills/`, each
shipping a script that fails when its guarantee does not hold. **No run of either script is
captured under `evidence/`**, so the honest answer to *what did an agent do with them* is: they
are shipped and not evidenced. `README.md:166` records the verdict as `DESIGNED` and says in its
own row that the row is *"not promoted to make the table look even"*; the long form is
[`docs/TOOL-USAGE.md:875`](../TOOL-USAGE.md) §*Tool 4*.

### Item 6 — Bedrock executes in this repository and not in the demo request path

Amazon Bedrock is AWS's hosted-model service. Real model calls were made from this repository and
recorded with AWS request ids. **The deployed demo does not make one.** Its read routes return
rows; they do not call a model and do not compute an embedding (a numeric fingerprint of text
used for similarity search). The embedding tables exist and are located —
`mainline.clause_embedding` and `mainline.event_cue_embedding`, both `VECTOR(1024)` — and the
live routes do not write to them.

There is a second half, recorded at `README.md:185-187`: inference runs in Sydney,
`ap-southeast-2`, while the database is in Singapore, `aws-ap-southeast-1`, because
`ap-southeast-2` is Advanced-tier only on CockroachDB Cloud. **There is no end-to-end Australian
data residency.**

### Item 7 — the change-request use case has no admission beat

The demo runs two use cases. Each is a short sequence of database steps the repository calls
*beats*; the **admission beat** is the one where a named competent person signs off on the open
obligation. The second use case — a code change landing on a protected branch — plays three beats
where the first plays four, and it names the missing one rather than leaving the field out:

```
"admission_beat": null
```

with a written reason in the same payload [src: qa/live2.json#data/admission_beat]. The reason,
quoted from `qa/live2.json#data/admission_absent_reason`, is that signing a
[disposition](GLOSSARY.md#disposition) requires a receipt proving this
[obligation](GLOSSARY.md#obligation) was actually shown to somebody; no such row exists for this
change request, and the demo's database login may read `mainline.exposure_receipt` but may not
write to it — the payload names the two grant lines, `db/GRANTS.yaml:644` and `:647`, as its
authority. **A fourth beat marked "skipped" and dressed to look passing would be a fabricated
exhibit.** A second beat is absent for the same kind of reason: the database's own merge procedure
is not called, because under that login it answers `42501` — a privilege error — before the gate
is ever reached, and a privilege error shown as a gate refusal would also be a fabricated exhibit
[src: qa/live2.json#data/kernel_procedure_absent_sqlstate].

Use case one **does** have the admission beat, and it answers `00000`. A gate that always refuses
is broken, not safe, so the admitting step is not optional — it is missing from *this run*, not
from the demo.

### Item 10 — archival bonds and fixity are design, not routes

Two long-term-preservation ideas are specified and not reachable over the API.

* `mainline_meas.recall_run.n_bonded_sev5` — the count of fatality-severity precursors bound to
  this retrieval — **reads `0`**. Re-derived in this session with a read-only
  `GET /v1/recall-runs/dec0de00-0009-4000-8000-000000000001` against the deployed origin: `200`,
  2,223 bytes, `data.counts.n_bonded_sev5` = `0`.
* `mainline_audit.v_fixity_coverage` — the view that would say which stored items were re-checked
  against their hashes and which never were — **answers with no rows**: `row_count` `0`, `rows`
  `[]` [src: evidence/mcp/auditor-live.json#questions/8].

The `CHECK` constraint that would make a bonded fatality always blocking exists and is named
(`bonded_fatalities_all_blocking`, `0081_recall_run.sql`). With the counter at `0`, the seeded
run gave it nothing to refuse. **A counter reading zero demonstrates nothing.**

---

## 6 · Two measurements that show their apparatus rather than a result

### Item 9 — the silence receipt withheld nothing

A **silence receipt** ([glossary](GLOSSARY.md#silence)) is the record of what a search *declined*
to show, with its arithmetic, so that "nothing relevant was found" is a checkable claim rather
than an absence.

**On the seeded run its `entries` list is empty and `n_silenced` is `0`. Nothing was withheld.**
Re-derived in this session from the same read-only `GET` above: `data.counts.n_silenced` = `0`.
The recall run and the silence route are two different responses and they agree, which is a fact
about the database rather than about one reader
[src: evidence/demo/live-semantics.json#silence_ledger/entries_in_the_silence_payload,
 evidence/demo/live-semantics.json#silence_ledger/n_silenced_in_the_recall_run].

What is demonstrated is the **apparatus** — the arithmetic a withholding would have to publish,
bound to a corpus root and a threshold — on a run that suppressed no precursor at all.
**A reader who takes the empty list for a list of withheld precursors has read it backwards.**
That sentence is `R4_SENTENCE` at `scripts/proof/live_semantics.py:133`, written into the
artefact verbatim so that documents mentioning the silence ledger copy it rather than paraphrase.

### Item 12 — every timing in the demo is a local timing

The stopwatch readings quoted anywhere in this project were taken against **a single-node
CockroachDB running in Docker on one laptop** — `win32`, CockroachDB CCL `v26.2.5`
[src: qa/test-state.json#tool/platform, qa/test-state.json#cluster/version]. They are not
throughput numbers, they were not taken under concurrent load, and no distributed cluster was
involved. The cross-region hop described in item 6 — Sydney inference, Singapore database — is
**unmeasured under load**, recorded in those words at `README.md:293`. This page has not
re-measured it and does not estimate it.

---

## 7 · One item on this list closed while this chapter was being written

### Item 8 — `operator.html`

The enumerated list this chapter was written from records
[`operator.html`](../../verticals/mainline/apps/console/dist/operator.html) as *in the tree and
not on the deployed origin*, on the evidence that `GET /operator.html` returned the console shell
byte-for-byte identical to `GET /` — which is what a not-yet-deployed second entry point looks
like. That was measured on `2026-08-15` and it is recorded at `README.md:75`.

**It is no longer true, and this page states the current reading rather than the inherited one.**
Re-derived in this session with two read-only `GET`s against the deployed origin:

| | bytes | sha256 |
|---|---|---|
| `GET /` | 4,749 | `3178150a…6cc1ca` |
| `GET /operator.html` | 5,097 | `a7a685e8…e28110` |
| `verticals/mainline/apps/console/dist/operator.html` (this tree) | 5,097 | `a7a685e8…e28110` |

The two documents differ, and the served operator page is byte-for-byte identical to the one in
this tree. Its script and stylesheet answer `200` as well (`/assets/operator-C7FDTjCb.js`,
108,862 bytes; `/assets/operator-D8s_r_O9.css`, 33,690 bytes).

**The residual gap, which is what remains on the list:** what was checked is that the entry point
is *served*. Nobody drove the screens. "The file is reachable" and "the interface works" are
different claims, and only the first has evidence behind it.

---

## 8 · Why these are on the page rather than deleted

The argument is structural, not moral.

Every one of the twelve is a place where the shortest path to a better-looking submission was to
**delete the question rather than answer it**. The moves are cheap and they are all available.
Narrow the check until it cannot fail. Drop the lane that will not go green. Stop counting the
cases that could not run, and report the ten that passed. Mark a not-checked check as passed,
since nothing failed. Round a `null` field up to a step that was "skipped". Each of those
produces a document with fewer gaps in it and a system that knows less about itself, and the two
happen in the same edit.

That path is closed here for a specific reason rather than a general one. This product's only
claim is a **refusal**: the database will not issue a [permit](GLOSSARY.md#permit) while an
obligation on it is open, and a refusal is worth exactly as much as it is hard to talk around.
Talking our way around our own measurements would be the same move, performed on the same page
that describes the mechanism for preventing it. The twelve items are not an apology attached to
the architecture; they are what the architecture's own rule produces when it is pointed inward.

**And it is mechanised, so it does not rest on anyone's intention.**
[`tests/release/test_honesty_is_checkable.py`](../../tests/release/test_honesty_is_checkable.py)
reads [`docs/HONESTY.md`](../HONESTY.md), follows every reference into `qa/` or `evidence/`, and
fails the build when a quantity and the artefact it cites disagree
(`test_every_quantity_equals_the_value_it_cites`, line 466). Three companion rules fail when a
citation points outside `qa/` or `evidence/`, when a referenced file is missing, and when a
pointer does not resolve.

One rule runs the other way, and it is the one that matters here.
`test_the_document_does_not_lag_a_family_that_landed` (line 549) **fails when evidence appears
that the page has not absorbed** — a new artefact under a declared family that `docs/HONESTY.md`
does not mention. Its docstring names the failure it was written for: prose that kept quoting the
world as it was after the artefacts had moved. Its failure message is *"Re-base the document on
the artefact, or delete the artefact. A page that does not mention evidence that exists is a page
choosing what to look at."*

That is not hypothetical for this chapter. Item 8 was on the not-built list on the strength of a
measurement taken `2026-08-15`, and two read-only requests in this session showed it had closed.
The list moved and the page moved with it — this time in the favourable direction, by the same
rule that would have moved it the other way.

Every test named in this section is red-before-green: the bottom of that file plants one of every
violation into a synthetic document and requires the extractor to fire on each, because a checker
that has never been red asserts nothing about the document it checks.

---

## 9 · Two CockroachDB findings that are architectural, and what each changed

The full set of measured findings about CockroachDB belongs to a separate document. Two of them
changed decisions in *this* architecture, so they belong here. **Neither was re-measured in the
session that wrote this chapter**, and each is marked as such.

### `has_function_privilege()` appears to be a stub on `v26.2.5`

> *Recorded by this build and not re-measured in this session.* Source:
> [`docs/regression/GUARD.md:370-391`](../regression/GUARD.md) §*Two things this guard found on
> its first run* — local node, `2026-08-15`.

On a scratch database where `EXECUTE` had been revoked and the behavioural truth was a hard
refusal —

```
CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit
```

— `has_function_privilege()` still answered `true`: for that role, for `root`, for `admin`, for
`public`. `has_table_privilege` was put through the identical control on the same database and
tracked behaviour exactly.

**What it changed here.** A privilege check built on a function that cannot answer `false` cannot
fail, and a check that cannot fail is decoration. Every privilege claim in this architecture
therefore rests on **observed behaviour** — a `SHOW GRANTS` read with explicit role-membership
expansion, and, where it matters, an actual call that answers `42501` — and not on that built-in.
Item 7 above is one visible consequence: the change-request use case drops a beat because a real
`CALL` really does answer `42501` under the demo's login.

### The vector index is not chosen by the optimizer at demo scale

> *Recorded by this build and not re-measured in this session.* Source:
> [`docs/adr/0002-g1-platform-ground-truth.md`](../adr/0002-g1-platform-ground-truth.md) GT-06 and
> GT-06b, with the plan capture at
> [`evidence/aws/ann/explain-unhinted.txt`](../../evidence/aws/ann/explain-unhinted.txt).

At about 5,200 rows the unhinted query plan reads `top-k → render → filter → scan`: the database
scans and then filters. Named explicitly — `FROM tbl@idx_name` — the index is traversed and the
approximate-nearest-neighbour path works. **The index is not broken; a cost-based planner
legitimately prefers a scan on a small table**, and that is correct behaviour that broke our
assumption.

**What it changed here.** The recall path names the index in the statement, then reads the query
plan back and asserts the index was chosen rather than assuming it. Without that, the plan is a
declared full scan, every row is read, and **the results still look plausible** — so a silent
degradation would be indistinguishable from working retrieval. The decision recorded in that ADR
is to pin the index explicitly rather than rely on optimizer choice.

---

## 10 · The fuller accounts, and the way back

This chapter summarises twelve items. Three documents carry the complete versions, and all three
are longer and denser than this page on purpose — they are written to be verified, not to be met
first.

| Document | What it is |
|---|---|
| [`docs/HONESTY.md`](../HONESTY.md) | Every claim with the artefact that produced it, and every claim that is **not** proven, by name. Checked on every build by `tests/release/test_honesty_is_checkable.py`. |
| [`docs/CI-STATE.md`](../CI-STATE.md) | Every build lane with its run id and a quoted log line, separating the lanes that are red on purpose from the ones that are red on a defect. §2.1 is item 1 above; §2.4 is item 2; §2.5 is item 3. |
| [`VERIFY.md`](../../VERIFY.md) | The three ways a stranger can check this without trusting us, ordered by how much has to be taken on faith. Item 11 above is its Tier 1. |

The suite that guards the rest of the tree stands at **1,070 collected, 1,069 passed, 1 skipped,
0 failed, 0 errors** [src: qa/audit-suites.xml — `testsuite` attributes `tests`, `failures`,
`errors`, `skipped`]. That number is not a rebuttal to anything on this page. It is the state of
the tests that exist, beside twelve records of the tests, checks and routes that do not.

---

*End of chapter 5, and of the architecture document. Back to the front door:*
[**`docs/ARCHITECTURE.md`**](../ARCHITECTURE.md).
