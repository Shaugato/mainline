<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGING AXES — which artefact earns which score

Five axes, equally weighted: **Agentic Memory Design · Technological Implementation ·
Real-World Impact · Product Readiness · Creativity & Originality.**

**Those are the Official Rules' spellings and this page keeps them.** The contest's public
overview page renders two of the five differently; the Rules page is the authoritative one, the
criterion *text* is identical on both, and the discrepancy is recorded here rather than
"fixed".

**Equally weighted for the sum — and strictly ordered for the tie-break.** That ordering is not
an inference from the list above, it is a rule, and this page now reproduces it verbatim instead
of paraphrasing it — because the rule is what justifies this page's own shape, and a paraphrase
of the sentence that decides the contest is not something a judge should have to take on trust.
Official Rules §6, immediately below the criteria; the same text is quoted at
[`docs/demo/research/r1-judging.md`](../demo/research/r1-judging.md) §1.2, with that page's own
emphasis, which is dropped here so the sentence reads exactly as the Rules print it:

<!-- prose-hygiene: quoting -->
> **Tie Breaking** — For each Prize listed below, if two or more Submissions are tied, the tied Submission with the highest score in the first applicable criterion listed above will be considered the higher scoring Submission. In the event any ties remain, this process will be repeated, as needed, by comparing the tied Submissions' scores on the next applicable criterion. If two or more Submissions are tied on all applicable criteria, the panel of Judges will vote on the tied Submissions.

So Agentic Memory Design decides every tie, and **Product Readiness** — the axis this page
concedes at §4 — is **fourth**, behind three axes this repository is strong on. On a coarse
star scale ties are the expected case rather than the exception, which is what makes the
concession at §4 affordable: it is spent on the criterion the tie-break reaches last but one.

**Each criterion is two sentences, and until now this page answered only the first of each.**
The second sentence is where the scoring hook is, so §§1–5 each open by quoting it and
answering it in a line of prose before anything else. The full text of all five is
[`docs/demo/research/r1-judging.md`](../demo/research/r1-judging.md) §1.1, quoted there from the
Official Rules.

This page is written for someone filling in a score sheet, not for someone deciding whether
to keep reading — that is [`DEVPOST.md`](DEVPOST.md). Each section gives the one sentence to
take away, the two or three artefacts that earn it with their exact paths, and **the honest
counterweight for that same axis**, drawn from [`docs/HONESTY.md`](../HONESTY.md).

The counterweights are the point. A submission that argues five axes and concedes nothing is
asking to be disbelieved on all five. Every limitation below is one we published before a
judge could find it, and each is a number with a file behind it.

**Every relative path on this page was re-resolved against the working tree on `2026-08-16`,
after this revision's edits: `78` links, `0` broken** — *it read `70` and `0` earlier on
`2026-08-16` before this revision, `65` and `0` on `2026-08-15`, and `60` and `0` on
`2026-08-14`; the count rose because this revision added `8` links, and the denominator is
printed so the claim stays falsifiable.* The walk is: take every `](target)` that is not
`http`, `mailto` or a bare `#fragment`, strip any `#anchor`, and resolve what is left against
the file's own directory — **and skip fenced blocks and inline code spans, because a
`](target)` inside backticks is a *name*, exactly as a digit inside backticks is.** That last
clause used to be unwritten, and it is the difference between a reproducible count and an
unreproducible one: taken literally without it the walk scores this page's own description of
the walk as a link and reports one break that is not one. Run before this revision's edits, the
walk as now described reproduced this page's own `70` **exactly**, which is the only reason the
readings below are comparable to the ones this sentence used to carry. Over
[`RULES-MATRIX.md`](RULES-MATRIX.md) it returns `12` and `0`, unchanged. Over
[`DEVPOST.md`](DEVPOST.md) it returns `12` and `0` today where this sentence recorded `11`, and
over [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) `77` and `0` where the same walk read `75` about
an hour earlier in the same session, and where this sentence recorded `71` today and `40` on
`2026-08-15` — **both of those documents are being revised while this one is, so their figures
are readings with a timestamp rather than properties of the repository**, and every reading is
kept. A number that moved twice inside one hour is the clearest possible demonstration of why
the timestamp is printed with it. *(The same sentence read `2026-08-12` and gave no link count; a claim of
"none broken" with no denominator is unfalsifiable, so the denominator is now printed.)*
Every number carries the artefact that produced it. Digits inside `code spans` are
names (`v26.2.5`, SQLSTATE `23514`), not measurements. Where a figure below moved after an
earlier version of this page quoted it, the stale figure is named rather than deleted.

**Each of the five sections below is written to be scored alone.** A judge marking axis 3
reads §3 and nothing else: the take-away, the artefacts with their paths, the honest
counterweight, and — since `2026-08-14` — the **one path to open** that falsifies the section
if it does not say what the section says. The five axes are equally weighted by the rules, so
none of them is allowed to depend on another being read first.

**Fastest possible check — two minutes, no account, no credential:**

```bash
git clone -c core.longpaths=true <repo> && cd mainline
just up && just prove          # or: python scripts/proof/gate_refusal.py --dsn …
```

Expected last line: `VERDICT PROVEN`. If it says anything else, the central claim is
falsified and every axis below should be marked down. That is the intended failure mode.

---

## 1 · Agentic Memory Design

> **Take away:** memory here is not retrieval shown beside a decision — it is a
> **precondition of the state transition**, enforced by the database, so it cannot be
> dismissed, skipped, or routed around by a writer who did not use the application.

**The criterion's second sentence:** *"Is it used for more than toy queries — state,
embeddings, context, or transactional data at real scale?"*

**The answer.** It is **transactional data on the write path**, which is the strongest of the
four things that sentence lists and the hardest to fake: the obligation is a row, the counter is
a column a trigger projects onto the subject row, the gate is a plain `CHECK` over that column,
and all of it is inside one `SERIALIZABLE` transaction that a merge cannot commit around —
plus a composite foreign key onto `(subject_id, epoch)` with `ON UPDATE RESTRICT`, and C-SPANN
vector indexes for the recall prefix. **The falsification test is beat 3**: the projected counter
is forced to zero out of band and the merge is refused anyway, because the gate re-derives from
ancestry instead of trusting the number — a toy query cannot survive having its own input
falsified. **On *"at real scale"* this page concedes and does not argue**: the corpus is
authored, and there is no p50, no p99 and no load profile anywhere in this repository — the
counterweight below is the same concession and it stays.

**The criterion's *first* sentence, and the scope of its adjective.** *"Does CockroachDB
play a meaningful, production-grade role as the agent's memory layer?"* — Official Rules §6,
quoted at [`docs/demo/research/r1-judging.md`](../demo/research/r1-judging.md) §1.1.
**That adjective governs the memory layer; §4's concession governs the custody store and the
operator surface around it, and this page will not merge the two in either direction.** The
memory layer is `SERIALIZABLE`; a named `CHECK` whose *name* is the deliverable —
`gate_closed_when_issued`, `verticals/mainline/db/migrations/0050_permit.sql:114`; a
composite foreign key `(permit_id, gate_epoch)` from `mainline.merge_record` onto
`mainline.permit` with `ON UPDATE RESTRICT ON DELETE RESTRICT`,
`verticals/mainline/db/migrations/0071a_epoch_pin_permit.sql:35-39`; a counter no client may
write, projected by the trigger at `0120_trg_check_project.sql`; `FORCE ROW LEVEL SECURITY`
on `mainline.permit`, `verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54`, so
owners are not exempt either; and a `271`-file migration chain applied `271` of `271`
against managed CockroachDB Cloud ([`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json)).
**What §4 concedes — loudly, and nothing here softens it — is the other half: `7` of `16`
cryptographic custody checks never ran, and there is no p50, no p99 and no load profile.**
Two sentences about two different things.

| Artefact | What it earns |
|---|---|
| [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2 | The memory model is a **normative specification**, not an implementation detail: PROJECT · PIN · REFUSE, with rules `P-1`–`P-5` and `N-1`–`N-4`. `P-2` forbids deriving a gate value from the inserting row; `P-3` says absence of evidence **refuses, never admits**; `N-3` forbids `CASCADE` in both positions, because a cascade rewrites history. |
| [`verticals/mainline/db/migrations/0120_trg_check_project.sql`](../../verticals/mainline/db/migrations/0120_trg_check_project.sql) + [`0115_fn_permit_merge_gate.sql`](../../verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql) + [`0050_permit.sql`](../../verticals/mainline/db/migrations/0050_permit.sql) | The three steps as shipped SQL: the trigger that projects a cross-row fact onto a scalar of the subject row, the gate function that **re-derives** rather than trusts it, and the plain-column `CHECK` that refuses for every writer forever. |
| [`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json) | The design is not asserted, it is **executed**. `projection.severity`: the client supplied `0`, the trigger projected `4` onto a row the client never touched. A counter a client writes is a client's opinion; a counter a trigger writes is the database's. `10` projection assertions, all holding. |
| [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json) | **STORE → RETRIEVE → ACT executed against the deployed origin, not diagrammed.** `base_url` is the live Function URL, `generated_at 2026-08-15T14:18:20Z`: `40` rows over `5` live routes, every response `200`, **`verdict: PROVEN`, `assertions_total: 23`, `assertions_held: 23`, `assertions_failed: []`**. The RETRIEVE→ACT interval is a **subtraction of two columns off two live routes** — `mainline.blocking_check.materialised_at` minus `mainline_meas.recall_run.started_at`, `10.0` seconds at `#gap`, with `stated_anywhere_in_this_program: false` and both endpoints corroborated `AGREES` against the checked-in seed. And the program **audits itself**: `#self_audit` reports `values_audited: 79`, `values_found_in_the_source: []`, `uuid_literals_in_the_source: 0` against `scripts/proof/memory_loop.py` at `source_sha256 dc1935a6…` — **`0` of `79` audited values originate in the program that wrote the file.** A proof script that could have hard-coded its own answer and demonstrably did not. |
| **the three live routes themselves** — anonymous, read-only, re-read `2026-08-16` | **`GET /v1/permits/{id}/blocking-checks`** returns `precursor.severity_gate: 4` with `precursor.severity_basis: "human_rated"` and the check's `origin: "blame_ancestry"` — a severity the client never supplied, on a row it never touched. **`GET /v1/recall-runs/{id}`** returns the retrieval run accounting for itself: `n_candidates 1 · n_blocking 1 · n_advisory 0 · n_silenced 0 · n_deduped 0`, plus `index_plan_digest d98e50a8…` and `index_generation g1`. **`GET /v1/permits/{id}/silence`** returns the Merkle silence receipt — `corpus_root`, `candidate_root`, `theta 0.35`, `s 1`, `n 1`, `boundary_proof.leaf_s.leaf_hash_hex`, `policy_version demo-recall-1.0` — **and `entries` is empty, because `n_silenced` is `0` on this run.** The apparatus is live; the list of withheld precursors is genuinely nil, and this page says so rather than implying a display of withheld precursors it does not have. |

**Re-read those three yourself — no clone, no account, no credential.** With `$B` the demo
URL and `$P` = `dec0de00-0006-4000-8000-000000000001`:

```bash
curl -s $B/v1/permits/$P/blocking-checks    # precursor.severity_gate 4 · severity_basis human_rated · origin blame_ancestry
curl -s $B/v1/recall-runs/dec0de00-0009-4000-8000-000000000001   # the five counts + index_plan_digest
curl -s $B/v1/permits/$P/silence            # the receipt — and entries: []
```

Two of those three are among the `5` routes `evidence/demo/memory-loop.json` walks;
**`/silence` is not in that transcript at all**, and is quoted here as a live route rather
than as a line of it.

**Why the memory has semantics rather than being a document store:** provenance (clause → the
incident that wrote it), ancestry (a commit DAG that is walked, not a "related documents"
list), severity floors (a fatality's relevance never decays), archival bonds (recall keyed to
an activity taxonomy, not keywords), fixity (as-documented reconciled against as-operated),
and **logged silence** — every precursor the system *declined* to surface is recorded with
its arithmetic, at `GET /v1/permits/{id}/silence`, live and anonymous. The last one is the
unusual commitment: a recall system that cannot be audited on what it withheld is not
auditable at all — **and on this seeded run the receipt is complete while `entries` is
empty, because `n_silenced` is `0` and nothing was withheld**, so what is demonstrated is
the arithmetic a withholding would have to publish, bound to a corpus root and a threshold,
on a run that withheld nothing.

**Honest counterweight.** The corpus is **authored** — the compressor-setpoint story is a
designed worked example, no real incident, no real site, no real fatality
([`docs/HONESTY.md`](../HONESTY.md) § SYNTHETIC). The agent layer's model transcripts are
**recorded cassettes**; a green agent test proves the code handles that recorded exchange and
proves nothing about a live model today. An earlier version of this line went on to say that
no live Bedrock inference transcript was committed, and on `2026-08-11` that stopped being
true: [`evidence/deploy/aws-live.json`](../../evidence/deploy/aws-live.json) records four
calls in `ap-southeast-2`, each with an AWS request id, and a Titan v2 embedding of dimension
`1024` at L2 norm `1.0`. The cassettes remain what the *test suite* replays; the transcript is
a separate and narrower claim. And the recall path crosses a region boundary on every
embedding call with **no p50, no p99 and no load profile anywhere in the repository** — anyone
quoting MAINLINE's recall latency is guessing.

**OPEN THIS TO CHECK IT — [`spec/TRAPPOINT-SPEC.md`](../../spec/TRAPPOINT-SPEC.md) §2**, then
any file in [`evidence/gate-refusal/`](../../evidence/gate-refusal/). The single field that
decides this axis is `projection.severity`: the client supplied `0` and the trigger projected
`4` onto a row the client never touched, with `10` of `10` projection assertions holding
(`evidence/gate-refusal/proof-20260810T054407Z.json#projection`). If that field shows the
client's own number, memory here is a cache and this axis is falsified.

---

## 2 · Technological Implementation

> **Take away:** the refusal lives in CockroachDB — constraints, triggers, `SERIALIZABLE` —
> so it holds against `psql`, a migration script and a back-office correction alike, and the
> repository proves that by attacking it rather than by demonstrating it.

**The criterion's second sentence:** *"Does the agent use the tools correctly and safely?"*

**The answer.** *Correctly*: nothing in the application composes a SQLSTATE — `23514` and
`P0001` come out of CockroachDB through the driver's error object, and where a constraint name
had to be **parsed** out of a `RAISE` message rather than **reported** by the driver, the payload
says `constraint_source: parsed` and this page repeats it, because a run whose exhibits were
inferred must never look like a run whose exhibits were reported. *Safely*: the safety is in the
tool rather than around it — `POST /v1/demo/gate-run` is savepoint-fenced and ends in `ROLLBACK`,
which is why a hundred judges may press it concurrently; the seeded subject's own mutating route
answers `423 demo_subject_write_protected` with `use_instead` naming the safe one; the published
judge login has **no write surface at all**; and the transcript proves the claim rather than
asserting it, by counting rows over ten tables before and after and keying its verdict on a
minted disposition id no other writer could hold
[src: `evidence/demo/live-beats.json#gate_run.persistence_check`].

| Artefact | What it earns |
|---|---|
| [`scripts/proof/gate_refusal.py`](../../scripts/proof/gate_refusal.py) → [`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json) | Three beats, one command. `23514` `gate_closed_when_issued` (source `reported`); then **the same permit refused again at `P0001` `mainline.fn_permit_merge_gate` after the projected counter was forged to zero out of band** (source `parsed`); then `00000` ADMITTED after one signed disposition. Verdict `PROVEN`, `0` caveats. |
| [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) + [`evidence/tool-usage/`](../../evidence/tool-usage/) | The rules ask which CockroachDB and AWS services were used **and how**. `4` CockroachDB tools, `10` engine features accounted separately, `12` AWS services — each with a verdict of EXERCISED / DESIGNED / NOT-AVAILABLE and a file-and-line anchor. `python scripts/submission/capture_tool_evidence.py --check` exits 1 if any count is stale. |
| [`packages/trappoint-migrate/src/trappoint_migrate/attest.py`](../../packages/trappoint-migrate/src/trappoint_migrate/attest.py) | The gate is **self-attesting**: `pg_get_triggerdef()` and `pg_get_functiondef()` are hashed into a chained schema attestation, so the gate's own source text is inside the record. Nobody quietly weakens the gate that prevents quietly weakening controls. A fallback records `attestation_grade="weak"` instead of pretending equivalence. |
| [`evidence/deploy/judge-run.json`](../../evidence/deploy/judge-run.json) `#channels.mcp` | **The criterion's own text names the MCP Server, so here is the run.** The **Managed MCP Server** was exercised end-to-end against the live cluster: `endpoint https://cockroachlabs.cloud/mcp`, `protocol_version 2025-06-18`, `ran: true`, `sql_identity: "managed-mcp"` — not `root`, not the database owner, a purpose-built identity — `passed 15` of `total 16` pack questions, `generated_at 2026-08-11T00:23:29Z`. `#managed_mcp_availability` records that `initialize` returned HTTP `200` and a session id and that `tools/list` returned `12` tools. **Two caveats ride with every sentence of that, and neither is optional.** *(i)* The run's own `verdict` is **`DIVERGED — KNOWN GAP`** — divergence `N01`, where the `managed-mcp` identity **can** read `mainline_qa.v_disposition_profile`, which the design had asserted it could not; published at `#divergences`, `disposition: real_gap`, `by_design: false`, not reconciled away. *(ii)* The credential that reaches the endpoint is the account's Cloud service-account key, and `#managed_mcp_availability` records `credential_publishable: false` with its reasons. **So MCP is *demonstrated*, and it is *not* the judge access path** — that is the read-only `mainline_judge` SQL login at [`evidence/deploy/judge-access.json`](../../evidence/deploy/judge-access.json), and `#divergences` notes that this login refuses the very statement `N01` got away with, `42501`, no `USAGE` on the schema: **the credential this deployment actually publishes is the tighter of the two.** |

**The detail worth a second look.** The middle beat is the whole architecture under attack. A
"materialised conflict" design is only as good as its resistance to a forged projection, so
the proof forges one. The gate re-derives the obligation count and refuses anyway: **P2
projections are enforced, never trusted.** The third beat matters equally — a gate that
always refuses is broken, not safe.

**Using a tool correctly includes finding out when the tool is lying.**
[`docs/regression/GUARD.md`](../regression/GUARD.md) § *Two things this guard found on its
first run*: the PRIVILEGES family first asked `has_function_privilege(role, oid, 'EXECUTE')`,
and the guard's plant **P2** — its own numbering, unrelated to spec rule `P-2` above —
existed to make it answer `false` after a real `REVOKE`. On CockroachDB
`v26.2.5` it answered **`true`** — for that role, for `root`, for `admin`, for `public`, for
everybody — while the behavioural truth on the same scratch database was
`REFUSED 42501 … does not have EXECUTE privilege on procedure merge_permit`. **A check built
on it cannot fail, and a check that cannot fail is decoration.** It was replaced with a
`SHOW GRANTS` read plus explicit role-membership expansion — which costs the two things the
built-in would have done for free, stripping the signature off the object name and following
`mainline_api`'s membership in `agent_gate`, `auditor_ro` and `svc_disposition` — **and which
can go red.** `has_table_privilege` was put through the same control on the same database,
tracked the behaviour exactly, and is still trusted for relations. This was found **by a
plant, before the guard was ever run in anger**; without it the check would have been
permanently, invisibly green. **The falsification is local-only** and `GUARD.md` says so in
its own words: the same `REVOKE` was not performed against the Cloud cluster, because that
would mutate a live deployment, so the cloud path was exercised read-only and the *proof of
falsifiability* is the weaker, local claim.

**Honest counterweight.** An earlier version of this page said the AWS half had **nothing** in
the EXERCISED column. That was true when it was written and is not true now, and the honest
correction is small rather than flattering: the census at
[`evidence/tool-usage/aws-services.json`](../../evidence/tool-usage/aws-services.json) carries
`12` service rows and only `3` of them are EXERCISED — the two Bedrock rows and CloudWatch.
`8` are DESIGNED and `1` is NOT-AVAILABLE, every Terraform module is unapplied, and Bedrock
Rerank is absent in `ap-southeast-2` and listed as such rather than dropped. Re-derive it with
`python scripts/submission/capture_tool_evidence.py --check`, which exits non-zero when any
count in that file has gone stale — on `2026-08-14` it exits **`2`**, refusing before any count
is computed because two of its declared source anchors have drifted off their subject, and
`docs/TOOL-USAGE.md` names that regeneration as owed rather than hiding it.
*If you also run `python scripts/submission/check_submission_ready.py` you will read
`10 AWS services` there against the `12` here: the gate holds a fixed table of ten service
names and asks which this repository mentions, while the census emits one row per distinct
use and Bedrock appears three times. Neither number was moved to match the other; the
arithmetic is in `docs/TOOL-USAGE.md` Part 2 and in `RULES-MATRIX.md` §1.*
`ccloud` `0.6.12` has no headless service-account authentication,
and Cloud audit-log endpoints `404` on the Basic tier, so the control-plane half of "custody
of the custodian" has **no input source on this tier**.
Nothing has ever run against CockroachDB Cloud in CI.

**What CockroachDB Cloud does and does not carry, in the same words this repository uses
everywhere else.** The paragraph below is the ruling text, reproduced verbatim so that this
page, `docs/STATE-OF-THE-BUILD.md`, `docs/HONESTY.md` and `docs/CI-STATE.md` cannot drift
apart on it:

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain
> is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against
> `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`,
> CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514`
> `gate_closed_when_issued`, with `nothing_persisted: true`
> [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`,
> `#verification`].
>
> ~~**The four-beat run through the HTTP handler has NOT been recorded against Cloud.** The
> operator reports it in the body of commit `7535670`; that commit's diff carries no such
> artefact, and `evidence/` holds none. **OWED:** re-run `scripts/deploy/…` against Cloud with
> `--out evidence/deploy/cloud-gate-run.json`, and only then may a Cloud `PROVEN` appear on
> this page. Until it exists, the only `PROVEN` this repository holds is
> `evidence/gate-refusal/proof-20260814T032418Z.json`, and it is **local**
> (`cluster.database = w_qr_gate_refusal_proof`).~~
>
> **THE DEBT IS DISCHARGED — 2026-08-15.** The four beats have been recorded through the HTTP
> handler, over the **public Function URL**, against the deployed CockroachDB Cloud database,
> by a client holding no DSN, no AWS profile and no token:
> [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) —
> `verdict: PROVEN`, `failures: []`, `target_is_local_emulator: **false**`, `23514`
> `gate_closed_when_issued` *(reported)* and `P0001` `mainline.fn_permit_merge_gate`
> *(parsed)*. It was written to a different path than the one this ruling nominated, and the
> ruling's text is kept rather than re-pointed, because a debt is discharged by an artefact and
> not by an edit. The local `PROVEN` at
> `evidence/gate-refusal/proof-20260814T032418Z.json` is still local and this page still says
> so wherever it quotes it.

**OPEN THIS TO CHECK IT — [`scripts/proof/gate_refusal.py`](../../scripts/proof/gate_refusal.py).**
Run it against a bare local node and read the last line. The committed transcript it writes is
[`evidence/gate-refusal/proof-20260814T032418Z.json`](../../evidence/gate-refusal/proof-20260814T032418Z.json):
verdict `PROVEN`, `caveats: []`, chain `271/271`, `PROJECTION 10/10`,
`REFUSAL [23514]`, `DRIFT [P0001]`, `ADMISSION [00000]`. If that last word is anything but
`PROVEN`, this axis is falsified and should be scored as such.

---

## 3 · Real-World Impact

> **Take away:** the failure this addresses is not a missing document — it is a *defensible*
> change approved by people doing their jobs correctly, because the reason behind the rule
> left with the person who wrote it.

**The criterion's second sentence:** *"Is the use case meaningful, not just technically impressive?"*

**Both sentences, verbatim, because on this axis alone they pull against each other.** Official
Rules §6; the same text is quoted at
[`docs/demo/research/r1-judging.md`](../demo/research/r1-judging.md) §1.1:

<!-- prose-hygiene: quoting -->
> **Real-World Impact** — "How big of an impact could the project have on real users or workflows? Is the use case meaningful, not just technically impressive?"

**Why this is the sharpest sentence of the five, and why it is pointed at a project like this
one.** The other four second sentences reward depth. This one is the single place on the score
sheet where our own engineering can be held **against** us: `SERIALIZABLE` transactions, a
projection trigger, a composite foreign key with `ON UPDATE RESTRICT`, C-SPANN vector indexes and
a chained schema attestation are exactly the inventory that reads as *technically impressive* and
proves nothing about whether anybody needed it. So this section does not answer the sentence with
more mechanism. It answers with **who is worse off today without this, and what specifically
changes for them** — and the mechanism appears only as the reason the change is not reversible by
whoever is in a hurry.

**What this is, in one sentence.** Safety knowledge in a regulated operation is *institutional
memory in a person*, and the person leaves; what this builds instead is institutional memory as a
**version-controlled repository whose commits are written by incidents**, with the gate that reads
it enforced by the database rather than by the screen — so the memory is a **precondition of the
permit**, not a panel beside it.

**The answer.** The use case is the one where nobody is negligent. A permit is raised, every
approver does their job, and the control that would have mattered is weakened anyway because the
person who knew why it existed left in 2017 — that is the ordinary way a fatality's lesson is
undone, and no shipping permit system can express it, because every one of them gates on the
present state of the world rather than on ancestry. The surfaces this is built to be met in are
therefore **a permit-to-work screen and a change-request screen** rather than our own console,
because a control that only exists in a vendor's console is a control nobody meets at the moment
of the decision. **That framing is a design commitment, and the artefact behind it is not yet
clean, so it is named here rather than left for a judge to find**: the scripted capture of those
two screens,
[`evidence/demo/operator-capture.json`](../../evidence/demo/operator-capture.json), was taken
against a **local emulator** (`target.is_the_deployed_url: false`) and its own top-level `held`
is **`false`** — `19` of its `20` assertions hold and the twentieth, `raw-payload-drawer-is-byte-identical`,
does not. **What keeps this honest**: no real operator has used it, no real data is in it, and
the counterweight below says so before a judge has to find it.

**Who is worse off today, row by row — and every row's third column is a file, not an argument.**
The last row is a limit rather than a claim, and it is inside the table on purpose: a table of
beneficiaries with the "nobody yet" row moved to a footnote is an advertisement.

| Who is harmed today, and how | What changes for them — the mechanism | Where it is measured |
|---|---|---|
| **The approver signing the permit.** The reason a control exists is in a closed investigation nobody opens at the moment of signing. Every approver does their job, the change is defensible, and the control is weakened anyway — the ordinary shape of the failure, and the one no shipping permit system expresses, because they gate on the present state of the world rather than on ancestry | the open obligation is a **row**, and the gate is a plain `CHECK` over a column of the subject row inside one `SERIALIZABLE` transaction — so the merge is **refused**, not annotated, not warned about, not left to the approver's judgement at the end of a shift. `23514` `gate_closed_when_issued`, `constraint_source: reported` | `evidence/demo/live-beats.json#gate_run.beats`, beat `2` of `4`. Taken over the public Function URL by a client the transcript describes as holding *"none - no DSN, no AWS profile, no token; a stranger with the URL"*, `target_is_local_emulator: false`, `verdict: PROVEN`, `failures: []` |
| **The same approver, after somebody has quietly zeroed the counter.** This is how a control actually dies in a regulated operation: not overruled, made **invisible** — a disarmed projector, a back-office correction, a well-meant `UPDATE` — and everything downstream then reads clean and permits the change | the gate **re-derives** the obligation count from ancestry instead of trusting the column it is looking at, so the same merge is refused a **second** time on a forged input: `P0001` `mainline.fn_permit_merge_gate`, `constraint_source: parsed` — and the payload says `parsed` because the constraint name had to be read out of a `RAISE` rather than reported by the driver. A number a client can write is a client's opinion | the same file, beat `3` of `4`, named `projection_drift_attack` — the beat exists because the design was **attacked** rather than demonstrated. Re-run it yourself against the live origin: `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url <the demo URL>` |
| **The investigator asking, years later, whether the lesson was applied.** Today the answer is an interview with whoever is still there. The question that cannot be answered from a document store is not *"what does the rule say"* but *"which incident wrote this clause, who was shown it, and how long after being shown it did anybody become bound by it"* | the loop is **four columns on live GETs**, not a narrative: the incident reference is `mainline.event.external_ref`, who was shown the memory is `mainline.exposure_receipt.actor_sub`, and the interval between reading and being bound is a **subtraction of two timestamps** — `mainline.blocking_check.materialised_at` minus `mainline_meas.recall_run.started_at` — computed by the reader rather than stated by the server | `evidence/demo/memory-loop.json#loop` — `40` rows over `5` routes, every response `200`, `23` of `23` assertions held, `verdict: PROVEN`. Each row prints the bare `curl` that re-reads it and **none of the `40` carries an authorization header**. The interval is at `#gap`: `10.0` seconds, and the file corroborates both endpoints against the checked-in seed rather than against itself |
| **Nobody, yet — and that is the honest size of the claim.** No operator has used this and no operator's data is in it | *(no mechanism — this row exists to bound the three above)* | the three rows above measure that the mechanism **refuses**, not that it has ever refused for anybody. The corpus was authored for this repository and [`docs/HONESTY.md`](../HONESTY.md) § SYNTHETIC says so in its own words: the compressor-setpoint story is a designed worked example, no incident, no site, no fatality |

**And the artefacts that carry the axis, with their paths:**

| Artefact | What it earns |
|---|---|
| [`docs/HONESTY.md`](../HONESTY.md) | The impact claim is bounded by the same document that bounds everything else. A safety-critical system whose vendor publishes its own failing counts is the only kind a regulated operator can adopt without doing the audit themselves. |
| [`VERIFY.md`](../../VERIFY.md) | Three tiers ordered by how much you must take on faith. **Tier 1** verifies a signed ledger offline with no credential, no network and no cluster. **Tier 2** — clone, `just up`, `just prove` — reproduces the refusal on a stranger's laptop with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing. |
| [`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json) + [`evidence/deploy/chain-261.json`](../../evidence/deploy/chain-261.json) | The design has met a managed cluster, not only a laptop: the same `271` files applied against CockroachDB Cloud Basic in Singapore, `0` failed, `0` retries needed, `359.1` seconds (`#chain_seconds`; `#total_seconds` is `388.9` and includes bootstrap — open the file and you meet the larger number first, so both are named here) against `46.35` locally (`chain-261.json#wall_clock_seconds`). That ratio is the most useful number here for anyone budgeting a deployment, and it is measured rather than modelled. **It is a DDL measurement and not a retrieval one**, and this repository publishes no interval for the recall hop because nobody has taken one. |

**Cost, stated plainly.** The cluster's configured `spend_limit` is `2500` — US$25.00/month,
a ceiling and not a spend ([`evidence/ccloud/cluster-list.txt`](../../evidence/ccloud/cluster-list.txt)).
The arrangement that satisfies *"functional demo URL, free and unrestricted for judges"* is a
single Lambda Function URL with `authorization_type = NONE` serving both the console and
`/v1/*`, estimated at roughly **US$0.02/month** and planned at
`Plan: 24 to add, 0 to change, 0 to destroy.` — line `843` of
[`evidence/deploy/terraform-plan-furl.txt`](../../evidence/deploy/terraform-plan-furl.txt),
which is **`11` resources in `module.api[0]` and `13` in `module.guard[0]`**, the cost guard
`infra/envs/demo/main.tf:631` instantiates.
*This paragraph said `11 to add` until 2026-08-14. The `11` was never wrong and is still
there — it is the API module alone — but it stopped being the plan's total the moment the
guard was wired in, and nothing re-read the plan afterwards. The artefact was regenerated and
this sentence was corrected against it; the artefact was not touched.*
An earlier version of this paragraph costed a static console build with replay fixtures at
US$0/month; that shape was abandoned because the console alone does not exercise the gate, and
because CloudFront cannot be created on this account at all — see §4. The estimate is an
estimate: ~~**no bill has been observed, because nothing has been applied.**~~ **CORRECTED
2026-08-15 — the apply has run and the Function URL is serving, so the second half of that
sentence is no longer true. The first half still is: no bill has been observed.** This page
prints no cost figure it has not been handed one for, and an estimate does not become a
measurement because the resource it estimated now exists.

**Honest counterweight.** No real operator has used this, and no real data is in it. The
domain corpus was authored for this repository. **Inference is in Sydney and the database is
in Singapore, so any claim of end-to-end Australian data residency is false** for this
deployment — stated here, in `VERIFY.md`, in the README and in `docs/TOOL-USAGE.md`, and
nowhere rounded off. Every timing in the demo is a local timing against Docker on a laptop.
The AWS evidence store is **described, not exercised under load**: no bucket has been
applied, and the check that would compare object-lock modes against live object versions is
one of the seven cryptographic checks that did not run.

**OPEN THIS TO CHECK IT — [`VERIFY.md`](../../VERIFY.md).** Tier 2 is the one that decides
this axis: clone, `just up`, `just prove`, and the refusal reproduces on a stranger's laptop
with no account of ours and no model call. A safety claim a buyer cannot re-run is marketing.
The managed-cluster half is
[`evidence/deploy/cloud-chain.json`](../../evidence/deploy/cloud-chain.json) —
`files 271 · applied 271 · failed 0` against CockroachDB Cloud Basic in `aws-ap-southeast-1`.
**And if you would rather open one file than run anything**, open
[`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) at `#gate_run.beats` and
read the four `outcome` values in order: `read`, `refused`, `refused`, `admitted`. The second
`refused` is the whole of the "meaningful, not just technically impressive" answer — it is the
run where the gate's own input was falsified and the permit was refused anyway. If beat `3`
reads `admitted`, the mechanism trusts a number a writer can set, the **second** row of the
table above is false, and this axis should be marked down to whatever the prose alone is worth.

---

## 4 · Product Readiness — **the weakest axis, and we are saying so first**

> **Take away:** score this axis down. The engineering discipline here is real and the
> shipping readiness is not, and a submission that pretended otherwise would contradict the
> one thing it is actually selling.

**The criterion's second sentence:** *"Has the team thought about resilience, access control,
and what happens when things go wrong?"*

**The answer — and it is a different question from the one the take-away above concedes.** The
take-away concedes **maturity**: no SLO, no load profile, one deployment. Every number in the
table below stands, unsoftened, and none of it is retracted by what follows. But the criterion
does not ask how mature the deployment is; it asks whether the team **thought about** failure
and access control, and on that specific question this repository has an answer for every clause
of it:

| the criterion's own words | the answer | where it is measured |
|---|---|---|
| *what happens when things go wrong* | **the write path fails closed, and it was attacked to prove it.** A merge with an open obligation is refused `23514` `gate_closed_when_issued`. The projected counter is then forced to zero out of band — a disarmed projector, or a careless `UPDATE` — and the same merge is refused **again**, `P0001` `mainline.fn_permit_merge_gate`, because the gate re-derives the count instead of trusting the column | `evidence/demo/live-beats.json#gate_run.beats`, taken through the public URL with no credential |
| *what happens when the system cannot answer* | **it says so and grades itself down.** On its strongest refusal the payload reports `diagnosis: none`, `naa: null`, `naa_reason: not_computable`, and one minimal-unsatisfiable-subset atom of kind `capability_gap` naming the function — instead of shipping a plausible superset labelled declarative | `evidence/demo/live-beats.json#gate_run.beat_three_diagnosis` |
| *access control* — who may **sign** | **signer enrolment is resolved out of the database**, not derived in the application: `mainline.signing_credential` and `mainline.defeater_option`. `demo.signer` and `demo.countersigner` are enrolled and unrevoked, and that is a checked fact rather than a sentence | `.venv/Scripts/python.exe scripts/demo/demo_ready.py`, fact `signers` |
| *access control* — who may **read** | **measured from the other side rather than asserted**: 14 of 14 `mainline_audit` views readable, 11 of 11 base-table reads, inserts, `CREATE TABLE` and `DROP VIEW` attempts refused with the expected SQLSTATE | `evidence/deploy/judge-access.json`, verdict `PROVEN`, `failures: []` |
| *access control* — who may **write** | **the published login has no write surface at all** — narrower than our own documents used to describe (§7 of the judge pack records the correction). The one shared demo subject answers `423 demo_subject_write_protected` on its mutating route, naming the safe endpoint instead, so one caller cannot brick the demo for the next | `verticals/mainline/db/demo/judge_grants.sql:155`; `evidence/demo/live-beats.json#documented_traps` |
| *resilience* — history cannot be rewritten | **obligations and dispositions are append-only.** A disposition is retracted by writing a row that points at it (`retracted_by`), never by deleting one; a completed transition takes a composite foreign key onto `(subject_id, epoch)` and **`ON UPDATE RESTRICT` makes attaching a new obligation to a completed transition physically impossible**; `CASCADE` is forbidden in both positions, because a cascade rewrites history | `evidence/demo/memory-loop.json#published_sql`; `spec/TRAPPOINT-SPEC.md` §2 rules `N-1`–`N-4` |
| *resilience* — the schema is reproducible | the deployed database reports its chain at **`271` of `271` files**, applied by `scripts/deploy/cloud_chain.py`, beside a `schema_fingerprint` the endpoint publishes about itself | `evidence/demo/live-beats.json#world.health` — re-derive with `curl -s <the demo URL>/v1/health` |
| *observable* | **the honesty ledger is published and is a test, not a disclaimer.** `docs/HONESTY.md` carries an inline reference on every number, and `tests/release/test_honesty_is_checkable.py` fails the build when a number and its source disagree — **and fails it again when evidence appears that the document has not absorbed**, which is a rule that runs against us | `tests/release/test_honesty_is_checkable.py`, and the red it produced, quoted below |

**Two limits belong inside that table rather than after it, or the table is an advertisement.**
There is **no foreign key from `mainline.disposition` onto `mainline.defeater_option`**, so the
refusal of an unknown defeater code is the *application's* and not the database's — a smaller
claim than the rest of this section makes, and `MUST-NOT-CLAIM.md` families 13 and 14 govern it.
And the WebAuthn assertion on a signed disposition is **synthesised and labelled `staged: true`
on the wire**: this deployment has no authenticator and nothing in the schema verifies a
signature.

**So: score this axis down, and score it down for the reasons below rather than for the ones
above.** The concession is about maturity and it is correct. The criterion asked a narrower
question and this page now answers it before conceding, because losing a mark for failing to
answer the question that was actually asked is an avoidable cost and not an honest one.

**The measured reasons, each with its artefact.** Every row below was re-derived on
`2026-08-14` **from the artefact its own Source column names**, one row at a time and never
from the row above it — which is how four of them were found to have drifted. Where a figure
moved, the superseded one is named in the same cell.

| Finding | Measurement | Source |
|---|---|---|
| ~~**Nothing is deployed.** `terraform apply` has not been run~~ **SUPERSEDED 2026-08-15: the apply has run and the demo is live.** The finding that survives is narrower and is still a finding: **`demo_url` in the submission file has not been resolved to the hostname the apply produced**, so the repository's own gate still reports it unresolved while the wire answers `ok: true`. Where the two disagree the wire wins, and neither was edited to agree with the other | `demo_url` holds the literal `UNRESOLVED`; the deployment answers `ok: true` with the deploy chain at `271` of `271` files | [`docs/submission/SUBMISSION.json`](SUBMISSION.json); `python scripts/submission/check_submission_ready.py`; [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) |
| ~~The plan that would deploy it is written and unapplied~~ **the plan that deployed it, kept as a plan** | `Plan: 24 to add, 0 to change, 0 to destroy.` — `11` in `module.api[0]`, `13` in `module.guard[0]`, the cost guard `infra/envs/demo/main.tf:631` instantiates. *This cell said `11 to add` and cited `terraform-plan-furl.txt:339` until 2026-08-14. Both digits were stale, and the correction went one way only: the document was re-read against the artefact, and the artefact was not touched.* **The artefact is still a plan and is not re-labelled as a state file: it records what was going to be created, and what exists is measured over HTTP instead.** | [`evidence/deploy/terraform-plan-furl.txt`](../../evidence/deploy/terraform-plan-furl.txt) line `843` |
| The end-to-end acceptance run does not reach its contract | `"verdict": "NOT PROVEN"` at `generated_at 2026-08-13T01:47:58Z`, with `10` named failures — both runs reach beat `4` and are refused `23503 disposition_signer_credential_id_fkey`, with no `clearance_digest` on the admission beat. *This cell said `2026-08-11T05:43:54Z` with `4` failures, which was two regenerations behind; the count went UP and is published as it stands* | [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) |
| The conformance suite has never been demonstrated | `10` passed, `6` failed, `55` cannot-run, `0` errored, over `71` selected | [`qa/conformance-census.json`](../../qa/conformance-census.json) `totals`, `selected` |
| Lint is a published number, not a clean one | `671` `ruff` findings — down from the `847` an earlier version of this row carried — and `0` files `ruff format` would rewrite | [`qa/ruff-ratchet.json`](../../qa/ruff-ratchet.json) `lint.total`, `format.unformatted_files` |
| Types likewise, and this one is now a zero with its denominator | `0` `mypy` errors over `660` checked source files; the row used to read `12` over `477` | [`qa/mypy-ratchet.json`](../../qa/mypy-ratchet.json) `total_errors`, `source_files_checked` |
| The test suite is not green | `9290` tests with no cluster: `8323` passed, `44` failed, `923` skipped, generated `2026-08-09T22:44:59Z`. *This cell read `8845` / `8065` / `44` / `736` until 2026-08-14 — the census taken before the demo API's own rows were merged into it. `docs/HONESTY.md` and `DEVPOST.md` were re-derived against the artefact days before this page was, and for those days the two disagreed; the artefact was right both times* | [`qa/test-state.json`](../../qa/test-state.json) `totals.none` |
| One target cannot be measured at all | `tests/integration` under `--crdb=reuse` was killed at `2400.02` seconds having written no JUnit XML, so `tests: 0` there is *unmeasured*, not *none* | [`qa/test-state.json`](../../qa/test-state.json) `packages."tests/integration".runs.cluster` |
| Custody verification is deliberately **not** a pass | exit `2`: `9` checks held, `0` failed, `7` never ran, of `16` | [`qa/test-state.json`](../../qa/test-state.json) `external_checks.custody_bundle_verification.counts` |
| Master is more red than green, and got redder today | Latest run of each workflow: **`20` workflows, `8` success, `12` failure**. *The two figures this row has carried are both kept: `18` workflows at `8`/`10`, re-derived `2026-08-12T14:58Z` at `1d41442` <!-- claim-hygiene: quoting: a git object name recording when a run was taken, not a commit_id anybody chose -->; and `20` workflows at `11`/`9`, re-derived earlier on `2026-08-14`. The board moved against us between two runs of the same command on the same day, which is the reason this row prints the command and not a remembered number* | `gh run list --branch master --limit 300`, re-derived `2026-08-14` after the `04:29Z` push. `gh` lists `21` names because `cluster-lane-bites` appears twice, once under its file path; collapsed, `20` |

**Two rows that were on this list are off it, and the removal is recorded rather than
silent.** The repository was `PRIVATE` when this page was first written and is now `PUBLIC` —
`gh repo view Shaugato/mainline --json visibility,licenseInfo` answers
`{"visibility":"PUBLIC","licenseInfo":{"key":"apache-2.0"}}` — and the root `LICENSE`, which
was untracked, is tracked and reads as Apache-2.0 at `11357` bytes. Neither is an achievement;
they were table stakes, and the only reason to mention them is that a document which quietly
drops its own failing rows cannot be trusted with the ones it keeps.

**And one constraint that is not ours to fix.** The demo origin is a Lambda Function URL
rather than CloudFront because AWS will not create new CloudFront distributions on this
account. That is not a Terraform problem, an IAM problem or a module problem: a real apply on
`2026-08-10` reached the distribution and was refused, and the same refusal comes back from a
bare `aws cloudfront create-distribution` with a three-field config and no Terraform anywhere.
AWS's words, quoted verbatim and kept verbatim in
[`docs/deploy/RUNBOOK.md`](../deploy/RUNBOOK.md) Appendix A with the `RequestID` intact:

<!-- prose-hygiene: quoting -->
> `AccessDenied: Your account must be verified before you can add new CloudFront resources.`
> `To verify your account, please contact AWS Support and include this error message.`

Only AWS Support can lift it, the runbook is written as though it never clears, and the
identity that was refused holds `AdministratorAccess`.

**Now the part that should recover some of the mark: those numbers are falsifiable and
monotone.** Each is a **ratchet** — a frozen figure in a committed JSON file that may fall
and may not rise. `scripts/qa/ruff_ratchet.py` gates **per rule and per tree**, not on a
headline sum, so a change that removes twenty findings in one directory and adds five
hard-gate violations in another cannot buy its way past with the total.
[`scripts/qa/check_reuse.py`](../../scripts/qa/check_reuse.py) does the same for licence
headers against [`qa/reuse-ratchet.json`](../../qa/reuse-ratchet.json), separating *gated*
counts from *recorded* ones so numbers that legitimately move in both directions are not
pretended to be gates. Re-baselining is the only way a number rises, and it leaves a diff.

**And the discipline is enforced against the prose, not just the code.**
[`tests/release/test_honesty_is_checkable.py`](../../tests/release/test_honesty_is_checkable.py)
reads [`docs/HONESTY.md`](../HONESTY.md), extracts every number, follows every reference, and
fails when a number and its source disagree, when a citation points outside `qa/` or
`evidence/`, when a cited file is gone, or when a number carries no reference at all. It also
plants one of every violation family into a synthetic document and requires the checker to
fire on each — because a lint that has never been red asserts nothing.

**One rule runs the other way, and it is red as this page is written.**
`test_the_document_does_not_lag_a_family_that_landed` fails when evidence *appears* that the
prose has not absorbed. Run on `2026-08-10`:

```
1 failed, 33 passed
AssertionError: docs/HONESTY.md is behind its own evidence:
  family 'chain-run' has 1 file(s) on disk (evidence/chain/chain-20260810T062542Z.json) …
  family 'conformance-census' has 1 file(s) on disk (qa/conformance-census.json) …
```

One of those artefacts is **good news**: the forward-only deployment runner completed —
`271` of `271` files, `0` failed, nothing dirty, attestation head ordinal `271` at grade
`strong`, in `evidence/chain/chain-20260810T062542Z.json`.

The other is a census, and it is **not** a demonstration. The conformance suite has never been
demonstrated end to end: run against a bare node its cases error rather than skip, which is
why `qa/conformance-census.json` reports `55` of `71` as cannot-run with the missing object
named on each. Exactly two of the declared cases have been exercised anywhere in this
repository — CF-01 and CF-03 — and they were exercised by `scripts/proof/gate_refusal.py`
rather than by the suite. That is a smaller claim than "the suite ran", and it is the one this
page will make. An earlier version of this paragraph said the suite had been demonstrated end
to end for the first time; `scripts/submission/check_submission_prose.py` rule
`SUB-05-conformance-passes` caught the sentence in our own document and this is the
replacement it asked for.

The build went red on both artefacts anyway, because the document had not caught up. **A
repository that breaks its own build when its documentation lags its evidence is the readiness
signal here** — not the pass rate.

**Honest counterweight to the counterweight.** Do not over-credit that. *This paragraph said
`docs/HONESTY.md` "is stale right now, and the same section that predicted this breakage also
still says `qa/conformance-census.json` does not exist". Re-read on `2026-08-14`, that is no
longer true of the tree: `docs/HONESTY.md:837` now quotes its own superseded sentence and
absorbs the census in a table at `:846-853`, with `[src: qa/conformance-census.json#…]` on
every figure. The lag was real and it closed; the sentence is corrected rather than deleted,
because the correction is only checkable against the claim it corrects.* What has **not**
closed is the census itself — `55` of `71` still cannot run. Separately, an earlier version of
this paragraph said **no GitHub Actions run of the pipeline was recorded in this
repository**. That has since been fixed and the fix is not
flattering: [`docs/CI-STATE.md`](../CI-STATE.md) now names every workflow with its run id, and
what those run ids show is a board that is more red than green. Re-derived on `2026-08-14`
with `gh run list --branch master --limit 300`, taking the latest run of each: **`20`
workflows, `8` success, `12` failure.** *Two earlier readings of the same command are kept
beside it — `18` workflows at `8`/`10` on `2026-08-12` at commit `1d41442` <!-- claim-hygiene: quoting: a git object name recording when a reading was taken -->, and `20` at
`11`/`9` earlier on `2026-08-14`.* Several of the reds report a true incompleteness and are
meant to stay red; `docs/CI-STATE.md` is the page that says which, and it is not this page's
to write. The observation problem is solved; the lanes are not.

**OPEN THIS TO CHECK IT — [`docs/submission/SUBMISSION.json`](SUBMISSION.json), then
`python scripts/submission/check_submission_ready.py`.** The checker prints one row per
requirement with the literal command that resolves it and refuses to call the submission ready
while any row is unresolved. Run on `2026-08-14` against this working tree it printed
**`NOT READY`, `3` unresolved rows of `10`, `0` NOT CHECKED**: `demo_url` and `video_url`,
which are the two this page has always said are open, plus `remote_sync`, which is `4` commits
ahead of `origin/master` with uncommitted paths and clears on a push. A `FAIL` row on that
output is this axis, stated by a program rather than by us.

---

## 5 · Creativity & Originality

> **Take away:** the original move is a *category* distinction with a mechanism behind it —
> every shipping permit system gates on the present state of the world, and this one gates on
> **ancestry** — and the mechanism is three ordinary SQL features composed into something
> none of them does alone.

**The criterion's second sentence:** *"Does it demonstrate insight into what makes agentic
systems different from traditional apps?"*

**The answer.** A traditional app's user is in the application. An agent is not: it writes over
whatever surface it can reach, and it does not stop being an agent when it uses `psql`, a
migration script or a back-office correction. Two consequences follow and this project is built
on both. **First, an agent's memory has to be a precondition of the state transition rather than
a panel beside it** — a nag can be dismissed, a retrieval can go unread, and a constraint a
writer can route around is not a constraint. **Second, a refusal has to be explainable or it
gets engineered around**, so every refusal emits a minimal unsatisfiable subset and, where
computable, the nearest admissible alternative — and where it is *not* computable the system says
`not_computable` and names its own capability gap rather than inventing a plausible answer. The
third consequence is the demonstration itself: most systems prove memory by recalling something.
**This one proves memory by refusing something, and then proves the memory is real by refusing
again after the number it reads has been falsified.**

| Artefact | What it earns |
|---|---|
| [`skills/designing-diachronic-gates/`](../../skills/designing-diachronic-gates/) | The idiom is generalised out of the product into a **CockroachDB Agent Skill**, and it ships a program that falsifies it: [`scripts/assert_gate_refuses.py`](../../skills/designing-diachronic-gates/scripts/assert_gate_refuses.py) spins a throwaway node, replays an illegal history, and fails unless the expected SQLSTATE **and** constraint name are raised. A skill whose advice cannot be falsified is a blog post. |
| [`skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py`](../../skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py) | The second skill encodes a platform fact discovered the hard way — a prefix-constrained ANN query uses the C-SPANN index **only when the index is named in the query** — and fails when the plan stops choosing it. An ANN query that quietly fell back to a scan is otherwise indistinguishable from one that did not. |
| [`evidence/producers/producer-census-before.json`](../../evidence/producers/producer-census-before.json) | The most original *finding* in the build, and it is a negative result: **a defect census built from error messages measures only what the error messages can express.** CockroachDB names one absent relation per statement, so a table shadowed behind another in every view that joined them was invisible to a SQLSTATE census — permanently. The count read five; the truth was seven. |
| [`docs/ci/anti-vacuity.md`](../ci/anti-vacuity.md) | **A standing census of whether each CI lane can prove it is *able* to fail** — one row per workflow, including the rows that admit no negative control exists. The shape is fixed: *copy the lane's real input, plant **one** violation per failure family, run **the lane's own checker**, and assert both that it exits non-zero **and** that the message names the planted family.* That last clause is the whole idea, and the census gives the reason in its own words: **"an assertion that a program failed, without checking why, passes when the program fails to start."** The count: **`7` lanes carry a standing negative-control job after that wave, against `3` before it** (`claims`, `judge-pack`, `submission`), **and the table names the `8` that still have none** — `ci`, `db`, `db-schema`, `boundary` (partial: planted-reach tests, no lane-level job), `custody-chain`, `schema`, `nightly-differential`, `demo-health` — rather than omitting them. A green lane that cannot go red occupies the place a check would occupy. |
| [`evidence/mutation/README.md`](../../evidence/mutation/README.md) | **The mutation ratchet publishes Wilson lower bounds beside the point estimates, and deliberately gates nothing.** Three of three killed is a point estimate of `1.0` and a 95 % lower bound of **`0.438`**, and the README's reason is the unusual part: *"publishing `1.0` there is not optimism; it is a false statement about how much evidence exists."* Point estimates appear in every artefact labelled `point_estimate` and are never the claim; the interval is six lines of arithmetic in `wilson.py`, deliberately **not** `statsmodels`, so an opposing expert can check the bound with a calculator. And `mainline-mutation run` exits `0` whatever the kill rate is — **because the cheapest way to raise a mutation score is to delete the mutants you fail**, and a number that could stop a merge acquires an incentive to be high. The catalogue therefore keeps its survivors instead of tuning them away: `comparator_loosening` survives on `5` of `10` fixtures. The bounds are over a twelve-clause fixture corpus and the README says in its own voice that they generalise to nothing. |

**One denominator on that census is drifting, and it is printed rather than smoothed.**
Re-read `2026-08-16`, `docs/ci/anti-vacuity.md` §1 prints `17` workflow rows while its own
summary sentence says *"eighteen"*, and `ls .github/workflows/*.yml` counts `20` files today —
`aws-evidence`, `cluster-lane-bites` and `cluster-tests` are the three the table has not
absorbed. **The `8` with no control are countable off the table exactly as printed above. The
`7` is the census's own count and the table shows `8` lanes with a named job**, because
`submission`'s row records its control as *"pre-existing; not owned by this wave and not
re-examined here"* and the census's `7` counts what that wave stood up. Every one of those
figures is a reading with a date rather than a property of the repository, which is exactly
why the denominator is printed instead of the ratio alone.

**Three smaller ideas that are unusual on their own.** *Refusal is structurally redundant* —
an unwelding harness disables the trigger and drops the constraint, one at a time, and the
write still fails. *The ledger is gap-free by compare-and-swap, not by sequence* —
`CREATE SEQUENCE` is banned repo-wide because sequence updates are not rolled back, so a gap
**means** tampering. *Every refusal emits a minimal unsatisfiable subset* and, where
computable, the nearest admissible alternative — because a gate that only says "no" gets
routed around, and an invariant that is routed around is not an invariant.

**Honest counterweight.** The idea is the strong part and the demonstration is narrower than
the idea. `AS OF SYSTEM TIME` is deliberately **not** sold as "prove the state at time T" —
[`packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py`](../../packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py)
exists to show it cannot, and long-horizon reconstruction is an application-level commit DAG
instead. Six conformance capability tokens name relations this repository has **deliberately
not authored** — `propagation`, `observed_assertion`, `merge_conflict`, `frontier_move`,
`discordance_warrant`, `coverage_certificate` — so those cases cannot pass and report
cannot-run with the object named. The novel algorithms described in the design notes
(ORIGINDIFF and the salami defence among them) are **specified, not demonstrated**; no
committed artefact exercises them end to end.

**OPEN THIS TO CHECK IT — [`skills/designing-diachronic-gates/`](../../skills/designing-diachronic-gates/).**
Its `scripts/assert_gate_refuses.py` spins a throwaway node, replays an illegal history, and
fails unless the expected SQLSTATE **and** the expected constraint name are raised. If the
skill's own assertion cannot be made to go red, the idiom it teaches is unfalsifiable and this
axis is worth less than it claims.

---

## What a judge should do with all of this

1. **Run `just prove`.** Two minutes. If `VERDICT` is not `PROVEN`, mark the project down on
   axes 1 and 2 — that is what the artefact is for. The most recent committed transcript is
   [`evidence/gate-refusal/proof-20260814T032418Z.json`](../../evidence/gate-refusal/proof-20260814T032418Z.json),
   `2026-08-14`, verdict `PROVEN` with `caveats: []`, in a throwaway database on the pinned
   local node (`cluster.database = w_qr_gate_refusal_proof`): `chain 271/271 applied, 0 failed`,
   `PROJECTION 10/10 held`, `REFUSAL REFUSED [23514] gate_closed_when_issued (reported)`,
   `DRIFT REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)`,
   `ADMISSION ADMITTED [00000]`. **That `PROVEN` is local, and it stays labelled local.**
   ~~The equivalent four-beat run through the HTTP handler against CockroachDB Cloud is
   **OWED** and is quoted in full in §2.~~ **DISCHARGED 2026-08-15**: it exists, it was taken
   through the public Function URL with no credential, and it is
   [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) —
   `target_is_local_emulator: false`, `verdict: PROVEN`. §2 carries the ruling and its
   discharge side by side. Regenerate it yourself with
   `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url <the demo URL>`; the
   memory loop behind it is `scripts/proof/memory_loop.py`, and the frame-by-frame map from the
   film to both artefacts is [`docs/demo/JUDGE-90-SECONDS.md`](../demo/JUDGE-90-SECONDS.md).
2. **Open [`docs/HONESTY.md`](../HONESTY.md) before the README.** It is the shortest route to
   an accurate picture, and it was written to be used against us.
3. **Score Product Readiness low.** It is the weakest axis, the reasons are counted above,
   and we would rather be marked accurately than believed generously. The single sharpest
   check is `python scripts/submission/check_submission_ready.py`: re-run on `2026-08-14` it
   printed `3` unresolved rows of `10` with `0` NOT CHECKED and exited `1` — `demo_url`,
   `video_url` and `remote_sync`. It printed the same three on `2026-08-12`. Two of them are
   the founder's, and the third is a dirty working tree that clears on a push.
4. **Check one number at random.** Every figure on this page and in
   [`DEVPOST.md`](DEVPOST.md) resolves to a file under `qa/` or `evidence/`, or to a command
   printed beside it. If one does not, that is a defect — and
   [`docs/HONESTY.md`](../HONESTY.md) says to report it.
5. **Notice which claims on this page are written as "was X, is now Y", and which way each
   moved.** Toward us: the repository's visibility, the tracked `LICENSE`, `ruff` `847`→`671`
   with `245`→`0` unformatted, `mypy` `12`/`477`→`0`/`660`, the AWS EXERCISED column going
   from empty to `3` of `12`, a committed live Bedrock transcript where there was none, and
   recorded GitHub Actions runs where there were none. Away from us: the conformance suite,
   which this page previously said had been demonstrated end to end and which has in fact
   never been demonstrated; the demo's cost, which was written as US$0/month for a static
   console that was abandoned because it does not exercise the gate; the shipping plan, which
   this page quoted as `11 to add` while the committed artefact reads
   `Plan: 24 to add, 0 to change, 0 to destroy.`;
   the acceptance run, whose named failures went from `4` to `10`; and the no-cluster test
   census, which this page read as `8845`/`8065`/`44`/`736` while the artefact said
   `9290`/`8323`/`44`/`923`. Those recorded runs also showed a board that moved from `8` green
   / `10` red on `2026-08-12` to `8` green / `12` red on `2026-08-14`. A page that keeps only
   the flattering half of its own drift is not a register, it is an advertisement.

Related: [`DEVPOST.md`](DEVPOST.md) — the submission text.
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — which CockroachDB and AWS services, and how.
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md) — the judge's first five minutes, measured
on a fresh clone. [`VERIFY.md`](../../VERIFY.md) — three ways to check the claim without
trusting us.
