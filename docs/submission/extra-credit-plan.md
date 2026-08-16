<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# EXTRA-CREDIT PLAN — what earns points beyond the requirements, ranked by measured value

**Extra-credit lead · 2026-08-16 · repo `D:/CoackroachDBxAWS/mainline`, master at HEAD ·
live origin `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`**

Every number on this page was measured today against the live origin, the committed tree, or
the contest's own pages. Nothing here is re-derived from another document's summary.

---

## 0 · THE FINDING THAT REORDERS THE WHOLE PLAN

**The scoring facts, re-read from the source rather than from our own notes.** The Official
Rules page (<https://cockroachdb-ai.devpost.com/rules>, fetched 2026-08-16) gives criterion 1
as:

> **Agentic Memory Design** — *"Does CockroachDB play a meaningful, production-grade role as
> the agent's memory layer?"*

and criterion 2 as:

> **Technological Implementation** — *"Is the integration with CockroachDB tools (distributed
> vector index, MCP Server, ccloud CLI) quality software engineering?"*

and the tie-break as: *judges compare scores on the first criterion listed; if ties persist the
process repeats with the next.* The overview page
(<https://cockroachdb-ai.devpost.com/>) confirms the four CockroachDB tools (Managed MCP
Server · Distributed Vector Indexing · ccloud CLI · Agent Skills Repo), the ≥1 AWS service
rule, and lists **tool identification documentation** as a submission requirement — which
`docs/TOOL-USAGE.md` already satisfies and which most entrants will not have at all. The
Functionality rule reads *"must function as depicted in the video and/or expressed in the text
description"*. Deadline **2026-08-18 17:00 EDT**.

**Now the finding.** This project's problem is not that it lacks axis-one material. It is that
**the axis-one material it already has, live and anonymous, is almost entirely absent from the
submission page.** Measured:

| axis-one artefact | live / committed? | mentions in `DEVPOST.md` |
|---|---|---:|
| `evidence/demo/memory-loop.json` — STORE → RETRIEVE → ACT against the live URL, `verdict PROVEN`, `23` of `23` assertions held | committed, `base_url` is the live origin | **0** |
| `evidence/demo/live-beats.json` — the four beats off the deployed URL | committed | **0** |
| `GET /v1/permits/{id}/silence` — the Merkle silence receipt | **live, anonymous** | **0** |
| `GET /v1/recall-runs/{id}` — the retrieval run's own accounting | **live, anonymous** | **0** |
| `GET /v1/clauses/{uuid}/ancestry` — blame edge + closure + commit chain | **live, anonymous** | **0** |
| the refusal payload's **MUS** and **NAA** | **live, anonymous** | **0** (one sentence in `README.md:349`) |

Re-derive the zeros:
`grep -c "memory-loop\|live-beats\|/silence" docs/submission/DEVPOST.md` → `0`, `0`, `0`.

**So the highest-value hours left are surfacing hours, not building hours.** That conclusion is
not a compromise forced by the deadline; it is what the measurement says. An hour spent adding
a sixth AWS service moves axis 2 by nothing a judge will notice. An hour spent putting a
`curl` command next to the sentence "logged silence — every precursor the system declined to
surface is recorded, with its arithmetic" moves the axis that decides every tie, and it moves it
from *asserted* to *demonstrable*, which is the exact distinction the Functionality rule draws.

---

## 1 · RULINGS — what the brief left open, decided, with authority named

**R1 · The brief's Managed-MCP premise is stale. The gap is presentational, not evidential.**
The brief states there is *"no recorded end-to-end call — no `evidence/mcp/`"*. The second half
is true; the first half is not. **Authority:** `evidence/deploy/judge-run.json`, measured today,
carries `channels.mcp` = `{"channel": "mcp", "endpoint": "https://cockroachlabs.cloud/mcp",
"ran": true, "protocol_version": "2025-06-18", "sql_identity": "managed-mcp", "passed": 15,
"total": 16}` at `generated_at 2026-08-11T00:23:29Z`, with a `managed_mcp_availability` block
recording that `initialize` returned HTTP `200` and a session id and that `tools/list` returned
`12` tools. `docs/TOOL-USAGE.md:1317` already strikes the limitation through and §Tool 3
promoted `crdb_managed_mcp` DESIGNED → EXERCISED on `2026-08-12`. **The whole of the gap is
that the evidence is filed under a filename that says *deploy*.** Ruling: we surface it; we do
not re-run it. See R2.

**R2 · No new Managed-MCP capture is authorised.** **Authority:** the founder's absolute
prohibition on touching AWS, writing SSM, or printing a credential, plus the fact that a second
capture could *disagree* with the committed one two days before the deadline with no time to
reconcile. `evidence/mcp/` will be a **pointer directory** — a README plus a verbatim,
unaltered extract of the committed `channels.mcp` block — and it will say on its own face that
it is a pointer and name the file it points at.

**R3 · `docs/submission/SUBMISSION.json` is not edited by this wave, including its `notes`.**
**Authority:** that file's own single-write-point doctrine and the founder's *do not commit /
the orchestrator deploys* rule. It nonetheless carries a sentence that is now false:
`notes.demo_url` opens *"Unresolved because `terraform apply` has not been run: no MAINLINE
Lambda, no Function URL, no bucket exists in the account."* — contradicted by
`evidence/deploy/APPLIED.md` (`24 created, 0 changed, 0 destroyed`) and by the origin
answering `ok true` today. W6 **reports** this contradiction with the exact replacement text and
hands it to the orchestrator. W6 does **not** apply it, and nobody writes `demo_url`.

**R4 · Any sentence about the silence ledger must state that the demo run silenced nothing.**
**Authority:** measured 2026-08-16. `GET /v1/permits/dec0de00-0006-4000-8000-000000000001/silence`
returns a complete receipt — `corpus_root`, `candidate_root`, `theta 0.35`, `s 1`, `n 1`,
`boundary_proof.leaf_s.leaf_hash_hex`, `policy_version demo-recall-1.0` — **and `entries: []`**,
corroborated by `GET /v1/recall-runs/{id}` giving `counts.n_silenced: 0`. The *mechanism* is
live; the *list* is empty. A sentence implying withheld precursors are on display would be a
false claim under `MUST-NOT-CLAIM.md` family 10. The true sentence is written in §4 below and
every worker copies it rather than paraphrasing it.

**R5 · The `staged: true` flag is quoted as a strength, never trimmed.** **Authority:** the live
payload's own `staged_note`, which names `receipt.bound.statement` as the one value in that
response that no database column produced. Copy that quotes the receipt quotes the note in the
same breath. A payload that flags its own non-column field is rarer than the receipt itself.

**R6 · "Production-grade" is scoped to the memory layer, and axis 4's concession does not
move.** **Authority:** the Rules' criterion-1 text quoted in §0 — the phrase *production-grade*
sits inside **criterion one**, applied to *the agent's memory layer*, not inside criterion four.
The submission concedes Production Readiness globally and loudly (axis 4 opens *"Score this one
down"*), and **nothing anywhere draws the line that keeps that concession out of axis 1.** Ruling:
axis 1 gains one scoping sentence naming what *is* production-grade about the memory layer;
`docs/HONESTY.md`, `docs/CI-STATE.md` and the axis-4 block are not touched, softened or
re-scoped by anyone in this wave.

**R7 · No sixth AWS service, no fifth CockroachDB tool, no redeploy, no grant widening.**
**Authority:** the lexicographic tie-break plus the founder's prohibitions. The
`materialise_checks` / `exposure_receipt` INSERT gap stays exactly as open as it is.

**R8 · Beat 3's degraded refusal is quoted as a feature, not omitted.** **Authority:** the live
payload measured 2026-08-16 — on the projection-drift attack the refusal returns
`"naa": null`, `"naa_reason": "not_computable"`, and `mus[0].kind: "capability_gap"`. A refusal
that says it cannot compute the alternative rather than inventing one is the argument; hiding it
would be the opposite of the argument.

---

## 2 · THE RANKED LIST — three we do, then the ones we deliberately do not

### DO — EC-1 · The live memory loop becomes the axis-one headline

`evidence/demo/memory-loop.json`, generated `2026-08-15T14:18:20Z` against `base_url` = the live
Function URL: **`verdict PROVEN`, `assertions_total 23`, `assertions_held 23`,
`assertions_failed []`.** Its `self_audit` block asserts *"no value in this artefact originates
in `scripts/proof/memory_loop.py`"* and backs it with `values_audited: 79`,
`values_found_in_the_source: []`, `uuid_literals_in_the_source: 0`, and the source's own
sha256. Its `gap` block computes RETRIEVE → ACT as `10.0` seconds by subtracting
`mainline_meas.recall_run.started_at` (off `GET /v1/recall-runs/{run_id}`) from
`mainline.blocking_check.materialised_at` (off `GET /v1/permits/{permit_id}/blocking-checks`),
with `stated_anywhere_in_this_program: false` and a corroboration against the checked-in seed
reading `AGREES`. Its rulings include **R7: *"the loop needs no new endpoint; every word is
already a live GET."***

That is the criterion-1 question answered by one committed artefact and one command, and
`DEVPOST.md` does not mention it. **Value: highest available.** **Risk: zero** — the artefact
exists, is committed, and is not regenerated by this wave.

### DO — EC-2 · Six memory semantics, each with the live GET that returns it

`README.md` §*Why this is memory, not workflow* lists six semantics as bare bullets. Every one
is a live, anonymous route on the deployed origin. Measured 2026-08-16:

| semantic | live route | the field that proves it |
|---|---|---|
| **provenance** | `GET /v1/clauses/{uuid}/ancestry` | `blame_edges[0].basis: "asserted_document"`, `evidence_quote_sha256` |
| **ancestry** | same route | `commit_chain[0].control_delta: "introduce"`, `closure.depth 1`, `closure.ancestor_count 1` |
| **severity floors** | `GET /v1/permits/{id}/blocking-checks` | `precursor.severity_gate: 4`, `severity_basis: "human_rated"`, `origin: "blame_ancestry"` |
| **logged silence** | `GET /v1/permits/{id}/silence` | `corpus_root`, `candidate_root`, `theta 0.35`, `s 1`, `n 1` — **and `entries: []`, see R4** |
| **retrieval accounting** | `GET /v1/recall-runs/{run_id}` | `n_candidates 1 · n_blocking 1 · n_advisory 0 · n_silenced 0 · n_deduped 0`, `index_plan_digest` |
| **the act** | `POST /v1/demo/gate-run` | `refusal.mus[…]` and `refusal.naa`, see EC-3 |

And every one of those payloads carries a `provenance` array of per-field chips —
`{"chip": "db:column", "pointer": "/receipt/bound/index_plan_digest"}`,
`{"chip": "derived", "pointer": "/subject_kind"}`,
`{"chip": "staged", "pointer": "/receipt/bound/statement"}` — so the response states, field by
field, whether a database column produced it. **Value: converts six asserted semantics into six
`curl`-able ones on the tie-breaking axis.** **Risk: zero** — read-only GETs, no writes, no
credentials, nothing deployed.

### DO — EC-3 · The MUS and the NAA — the *act* half — promoted out of one README line

Live, measured 2026-08-16, `POST /v1/demo/gate-run` beat 2:

```
"mus": [{"kind": "obligation", "origin": "blame_ancestry", "severity": 4,
         "virulence": "blood_major", "detail": "open at gate_epoch 1; no live disposition"}]
"naa": {"kind": "dispose_obligations", "cardinality": 1,
        "description": "1 obligation(s) remain open on this subject; disposing of exactly
                        those restores admissibility",
        "legal_kinds": ["applied","mitigated","mechanism_absent","escalated","emergency_override"]}
```

and beat 3, the attack, degrades honestly per R8: `"naa": null`,
`"naa_reason": "not_computable"`, `mus[0].kind: "capability_gap"`. This is the entire
*retrieval-conditioned action* claim, live and anonymous, and it currently appears once, in
`README.md` line 349, and nowhere on the submission page. **Value: high.** **Risk: zero.**

### DO NOT — and here is why, so nobody re-proposes them at 02:00

| proposal | verdict | why |
|---|---|---|
| Re-run the MCP pack to create a fresh `evidence/mcp/` capture | **NO** | needs a Cloud service-account key and a live network run; could produce an artefact that *disagrees* with the committed one with no time to reconcile. Fails test two. R2. |
| Deploy `operator.html` so the two screens exist on the origin | **NO** | a redeploy, which is absolutely prohibited. `README.md` already publishes the gap (`GET /operator.html` returns the shell byte-for-byte identical to `GET /`), and a published gap outscores a rushed deploy that breaks a working demo. |
| Widen the `materialise_checks` / `exposure_receipt` INSERT grant so the loop writes live | **NO** | founder's call, unmade. The loop is already `PROVEN` read-only — the write would add nothing a judge scores and would widen the write surface of an unauthenticated endpoint. |
| Add a sixth AWS service or a fifth CockroachDB tool | **NO** | breadth on axis 2 behind depth on axis 1 is the worst hour available under a lexicographic tie-break. R7. |
| Re-run the mutation ratchet or the regression guard for fresher numbers | **NO** | both are standing measurements with committed artefacts. A fresh red at T-2 days is a cost with no upside, and the guard is *already* red for a true reason it publishes. |
| Rewrite the axis-4 block to sound better now the origin is live | **NO** | axis 4 is fourth. Its concession is the reason the other four are believed. R6 — the fix is a scoping sentence in axis **1**, not a softening in axis 4. |

### THE UNDER-SOLD RARITIES — placed by quotation, not by new work

These are real, committed, and none is on the submission page. They are assigned to workers
below as *quotations of existing artefacts*, never as new runs.

1. **The anti-vacuity census** (`docs/ci/anti-vacuity.md`) — one row per workflow, asking
   whether each lane can *prove it is able to fail*. Shape: *copy the lane's real input, plant
   ONE violation per failure family, run the lane's OWN checker, assert it exits non-zero **and**
   that the message names the planted family.* **`7` of `18` workflows have a standing negative
   control after that wave, against `3` before it, and the table names the `8` that still have
   none.** The last clause is the rare part: *"an assertion that a program failed, without
   checking why, passes when the program fails to start."*
2. **`has_function_privilege` is a stub on CockroachDB `v26.2.5`** (`docs/regression/GUARD.md`
   §*Two things this guard found on its first run*). Plant P2 was built to make it answer
   `false` after a real `REVOKE`; it answered `true` — for that role, for `root`, for `admin`,
   for `public`, for everybody, while the behavioural truth was `REFUSED 42501`. *"A check built
   on it cannot fail, and a check that cannot fail is decoration."* Replaced with `SHOW GRANTS`
   plus explicit role-membership expansion, which *can* go red. Found by a plant, before the
   guard was ever run in anger.
3. **The mutation ratchet publishes Wilson lower bounds and refuses to be a gate**
   (`evidence/mutation/README.md`). Three of three killed is a point estimate of `1.0` and a 95 %
   lower bound of `0.438`, *"and publishing `1.0` there is not optimism; it is a false statement
   about how much evidence exists."* It exits `0` whatever the kill rate is, because *"the
   cheapest way to raise a mutation score is to delete the mutants the system fails on"* — and
   it keeps them: `comparator_loosening` survives on five of ten fixtures.
4. **`staged: true` inside a live API payload** — R5.
5. **Severity was DERIVED, not typed** — the client supplied `0`, the trigger projected `4` onto
   a row the client never touched, `10` of `10` projection assertions holding. Already in both
   axis-1 blocks; it stays, and EC-2's `severity_basis: "human_rated"` off the live route is now
   the *live* corroboration of it.

---

## 3 · MANAGED MCP — the honest paragraph, since the premise changed

Facts, all from `evidence/deploy/judge-run.json` and `docs/TOOL-USAGE.md` §Tool 3, measured
today:

* endpoint `https://cockroachlabs.cloud/mcp`, MCP **Streamable HTTP**, protocol `2025-06-18`,
  an `mcp-cluster-id` header pinning exactly one cluster
* `initialize` → HTTP `200` + a session id; `tools/list` → `12` tools
* the endpoint runs as the SQL user **`managed-mcp`** — not `root`, not the database owner —
  which answers day-1 check GT-10 that `FALLBACK.md` recorded as unanswered and assumed
  pessimistically
* **`15` of `16`** pack questions PASS over the managed endpoint against the live Basic cluster
* server-side limits are read from `packages/mainline-mcp/src/mainline_mcp/limits.py`: `1`
  statement per call, `16384`-char statements, `20` s timeout, a **`10240`-byte response cap**,
  and a schema blocklist including `crdb_internal` and `pg_catalog`

**And the two caveats that ride with every sentence, per the no-false-claim rule.** The run's own
verdict is **`DIVERGED — KNOWN GAP`** — divergence `N01`, the `managed-mcp` identity *can* read
`mainline_qa.v_disposition_profile`, which the design had assumed it could not. And the MCP
credential is the account's Cloud service-account key, so it is **not publishable to anonymous
judges** — MCP is therefore *demonstrated*, and it is **not** the judge access path. The judge
access path is the read-only `mainline_judge` SQL login.

The claim we are allowed to make, in one line: **"The Managed MCP Server was exercised
end-to-end against the live cluster as the `managed-mcp` SQL identity — 15 of 16 pack questions
pass, the sixteenth is a divergence we publish, and the credential is not one we can hand a
stranger."**

---

## 4 · THE COPY — hand these to the workers verbatim

### 4.1 · `DEVPOST.md` → *Judged on — Agentic Memory Design* — two paragraphs to INSERT

> **The loop is not a diagram; it is three live GETs and a committed transcript.** STORE →
> RETRIEVE → ACT runs against the deployed origin and writes
> `evidence/demo/memory-loop.json`: `verdict PROVEN`, `23` of `23` assertions held, `0` failed.
> An incident dated `2019-03-14` names a clause; seven years later a permit relies on that
> clause; the retrieval pass finds the incident and **ten seconds** later the finding is an
> obligation the database will not let the permit be issued around. Those ten seconds are a
> **subtraction of two columns off two live routes** —
> `mainline_meas.recall_run.started_at` from `GET /v1/recall-runs/{run_id}`, and
> `mainline.blocking_check.materialised_at` from `GET /v1/permits/{permit_id}/blocking-checks`
> — with `stated_anywhere_in_this_program: false` in the artefact that computes it. The program
> that writes that file audits **itself**: `values_audited: 79`,
> `values_found_in_the_source: []`, `uuid_literals_in_the_source: 0`. A proof script that could
> have hard-coded its own answer, and demonstrably did not. **No endpoint was added to make any
> of this filmable** — the artefact's own ruling `R7` says the loop needed none.
>
> **The refusal is not a "no"; it is a minimal unsatisfiable set and the nearest admissible
> alternative.** `POST /v1/demo/gate-run` returns, for the blocked merge, a `mus` naming the one
> obligation — `origin: blame_ancestry`, `severity: 4`, `virulence: blood_major`, `detail: "open
> at gate_epoch 1; no live disposition"` — and an `naa` of `cardinality 1` describing the exact
> smallest repair, with the five dispositions the law of this system permits
> (`applied`, `mitigated`, `mechanism_absent`, `escalated`, `emergency_override`). A gate that
> only says "no" gets routed around, and an invariant that is routed around is not an invariant.
> **On the third beat — the attack — the payload degrades honestly rather than guessing:**
> `naa: null`, `naa_reason: "not_computable"`, `mus[0].kind: "capability_gap"`. A refusal that
> tells you it cannot compute the alternative is worth more than one that invents it.

### 4.2 · `DEVPOST.md` → axis-1 scoping sentence (per R6) — INSERT before the OPEN THIS line

> **On the criterion's own words — *"a meaningful, production-grade role as the agent's memory
> layer"* — the scope of that adjective is the memory layer, and this submission is careful
> about which half it is claiming.** The memory layer is `SERIALIZABLE`, a named `CHECK` whose
> name is the deliverable, a composite foreign key onto `(subject_id, gate_epoch)` with
> `ON UPDATE RESTRICT`, a counter no client may write, row-level security with `FORCE`, and a
> `271`-file migration chain applied `271` of `271` against managed CockroachDB Cloud. **What
> axis 4 concedes — and it concedes it loudly — is the custody store and the operator surface
> around that layer: `7` of `16` cryptographic custody checks unwritten, no p50, no p99, no load
> profile.** Those are two different sentences about two different things, and this page will
> not merge them in either direction.

### 4.3 · `DEVPOST.md` → axis-1 `OPEN THIS TO CHECK IT` — REPLACE the existing line

> **OPEN THIS TO CHECK IT — no clone, no account, no credential, one command:**
> `curl -s <demo_url>/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks`.
> The field that decides this axis is `precursor.severity_gate`. It reads `4` with
> `severity_basis: "human_rated"` and `origin: "blame_ancestry"` — a value the client never
> supplied and a trigger projected onto a row the client never touched
> (`evidence/gate-refusal/proof-20260810T054407Z.json#projection`, `10` of `10` assertions
> holding). **If that number is the client's own, memory here is a cache and this axis is
> falsified.** Then `spec/TRAPPOINT-SPEC.md` §2 for the normative `PROJECT · PIN · REFUSE`
> rules the projection obeys.

### 4.4 · `README.md` → replace the six bare bullets with the six live GETs

> ### Why this is memory, not workflow — and every line below is a URL, not a claim
>
> The memory is not a panel next to the transaction. It is a **precondition of the state
> transition**, enforced as a database invariant under `SERIALIZABLE`. The memory also has
> *semantics* rather than being a document store — and each semantic is a live, anonymous
> `GET` on the deployed origin. Measured `2026-08-16`; substitute the demo URL for `$B` and the
> seeded permit `dec0de00-0006-4000-8000-000000000001` for `$P`.
>
> | semantic | the command | what comes back |
> |---|---|---|
> | **provenance** — clause → the incident that wrote it | `curl $B/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry` | a `blame_edge` with `basis: asserted_document` and an `evidence_quote_sha256` |
> | **ancestry** — a commit DAG, walked | same route | `commit_chain` with `control_delta: introduce`, and a `closure` of `depth 1`, `ancestor_count 1` |
> | **severity floors** — a fatality's relevance never decays | `curl $B/v1/permits/$P/blocking-checks` | `severity_gate: 4`, `severity_basis: human_rated`, `origin: blame_ancestry` |
> | **logged silence** — what the recall *declined* to surface, with its arithmetic | `curl $B/v1/permits/$P/silence` | a Merkle receipt: `corpus_root`, `candidate_root`, `theta 0.35`, `s 1`, `n 1`, a boundary proof |
> | **retrieval accounting** — the run auditing itself | `curl $B/v1/recall-runs/dec0de00-0009-4000-8000-000000000001` | `n_candidates 1 · n_blocking 1 · n_advisory 0 · n_silenced 0 · n_deduped 0`, plus the `index_plan_digest` |
> | **the act** — recall conditioning the write | `curl -XPOST $B/v1/demo/gate-run -d '{}'` | the refusal's `mus` and `naa` |
>
> **Read the silence receipt honestly, because we do.** On this seeded run the receipt is
> complete and `entries` is **empty** — `n_silenced: 0`, nothing was withheld. What is
> demonstrated is the *apparatus*: the arithmetic a withholding would have to publish, bound to
> a corpus root and a threshold, on a run that withheld nothing. And the receipt says which of
> its own fields no column produced: `staged: true`, with a `staged_note` naming
> `receipt.bound.statement` as the single value in that payload that the database did not
> author. **Every one of those responses carries a `provenance` array of per-field chips —
> `db:column`, `derived`, `staged` — so you never have to guess which half of an answer came
> from the database.**

### 4.5 · The one-line claims — for the form, the README badge line, and the film's close block

Each is followed by the artefact that survives the question *"show me"*. **Use them exactly.**

1. "STORE → RETRIEVE → ACT is a committed transcript against the deployed URL: `PROVEN`, `23`
   of `23` assertions." — `evidence/demo/memory-loop.json`
2. "The RETRIEVE → ACT gap is a subtraction of two columns off two live routes, not a sentence:
   `10` seconds." — same file, `#gap`
3. "The proof script audits itself: `79` values, `0` of them originating in the program." —
   same file, `#self_audit`
4. "Every refusal returns a minimal unsatisfiable set and the nearest admissible alternative —
   and returns `naa_reason: not_computable` rather than a guess when it cannot." — live
   `POST /v1/demo/gate-run`
5. "Severity was derived by a trigger from blame closure, not typed by a client: supplied `0`,
   projected `4`." — `evidence/gate-refusal/proof-20260810T054407Z.json#projection`
6. "The Managed MCP Server was exercised end-to-end as the `managed-mcp` SQL identity: `15` of
   `16` pack questions pass, and the sixteenth is a divergence we publish." —
   `evidence/deploy/judge-run.json#channels.mcp`
7. "`7` of `18` workflows carry a job whose only purpose is to prove that lane can go red — and
   the census names the `8` that still have none." — `docs/ci/anti-vacuity.md`
8. "`has_function_privilege` is a stub on `v26.2.5`: it answered `true` after a real `REVOKE`
   while the call itself was refused `42501`. A check built on it cannot fail. We found it with
   a plant and replaced it." — `docs/regression/GUARD.md`
9. "Mutation scores are published as Wilson lower bounds and gate nothing, because the cheapest
   way to raise a mutation score is to delete the mutants you fail." —
   `evidence/mutation/README.md`
10. "The demo origin answers `GET /v1/health` with `deploy_chain 271/271` and
    `POST /v1/demo/gate-run` with verdict `PROVEN`, in one `SERIALIZABLE` transaction that ends
    in `ROLLBACK` — so a hundred judges may press it at once." — `evidence/deploy/live-health.json`,
    `evidence/deploy/live-gate-run.json`

### 4.6 · `evidence/mcp/README.md` — the pointer file's opening, verbatim

> **This directory holds no capture of its own, and that is deliberate.** The live Managed MCP
> session against `https://cockroachlabs.cloud/mcp` was recorded on `2026-08-11` and lives in
> `evidence/deploy/judge-run.json` under `channels.mcp`, because the program that made the call
> was the judge-access prober and evidence is filed under the program that produced it. This
> file exists because a reader looking for MCP evidence looks for a directory named `mcp`, and
> finding none is indistinguishable from there being none. **Nothing here was re-run to create
> it.** The extract below is copied byte-for-byte from that file; if the two ever disagree, that
> file is authoritative and this one is wrong.

---

## 5 · THE SIX WORKERS — disjoint paths, literally enumerated

No worker touches a path owned by another. **Every brief repeats the three standing rules.**

| # | worker | owns, exactly |
|---|---|---|
| W1 | Axis-one on the submission page | `docs/submission/DEVPOST.md` |
| W2 | The README's six live GETs | `README.md` |
| W3 | The score-sheet document | `docs/submission/JUDGING-AXES.md` |
| W4 | Managed MCP, surfaced | `docs/TOOL-USAGE.md`, `evidence/mcp/README.md`, `evidence/mcp/README.md.license`, `evidence/mcp/session-extract.json`, `evidence/mcp/session-extract.json.license` |
| W5 | The measurement that makes W1–W3 safe | `scripts/proof/live_semantics.py`, `evidence/demo/live-semantics.json`, `evidence/demo/live-semantics.json.license`, `docs/demo/LIVE-SEMANTICS.md` |
| W6 | The claim ledger and the verification sweep | `docs/submission/EXTRA-CREDIT-CLAIMS.md` |

**Nobody touches:** `docs/HONESTY.md`, `docs/CI-STATE.md`, `docs/submission/SUBMISSION.json`,
`docs/submission/MUST-NOT-CLAIM.md`, `qa/**`, `infra/**`, `verticals/**`, `spec/**`,
`packages/**`, `tests/**`, `.github/workflows/**`, `docs/demo/film/**`.

**W1–W3 are not blocked on W5.** Every value they need is measured in §2 and §4 of this page.
W5's artefact is the standing re-derivation, and W6 reconciles the two.

---

## 6 · THE THREE RULES EVERY WORKER OBEYS

1. **NO FALSE CLAIM.** Never claim a service, feature, tool or number that did not actually
   run. If something is real but not in the demo's request path, say exactly that — the
   repository already uses that construction for Bedrock and it reads as confidence, not
   hedging. Every number carries the artefact that produced it. Digits inside `code spans` are
   names, not measurements.
2. **NO REGRESSION.** Baseline **1070 collected / 1069 passed / 0 failed / 0 errors**. Gate
   proof stays `PROVEN` caveat-free. `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move.
   The console bundle headroom guard fails below `1,024` bytes and must not be approached.
   `continue-on-error` and `|| true` are banned. Do not weaken `HONESTY.md`, `CI-STATE.md` or
   any ratchet. Do not widen a database grant.
3. **NO DEPLOY.** Never `terraform apply`, never redeploy, never touch AWS, never write an SSM
   parameter, never print a credential. Read-only HTTP GETs against the public origin are the
   only network access permitted, and `POST /v1/demo/gate-run` is permitted only because it
   ends in `ROLLBACK`. **Do not commit** — leave the tree for the orchestrator.
