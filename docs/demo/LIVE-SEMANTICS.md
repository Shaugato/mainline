<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# LIVE SEMANTICS — six memory semantics, each of them a `curl` a stranger can press

**Artefact:** [`evidence/demo/live-semantics.json`](../../evidence/demo/live-semantics.json)
**Producer:** [`scripts/proof/live_semantics.py`](../../scripts/proof/live_semantics.py)
**Owner:** extra-credit worker **W5**. Rulings **R4** and **R5** of
[`docs/submission/extra-credit-plan.md`](../submission/extra-credit-plan.md) bind it.

The Official Rules say the Project **"must function as depicted in the video and/or expressed in
the text description"**. `README.md`, `docs/submission/DEVPOST.md` and
`docs/submission/JUDGING-AXES.md` say that this system's memory has *semantics* — it is not a
document store with a search box — and that **each semantic is a live, anonymous `GET`** on the
deployed origin. That sentence is true. This page and its artefact are what make it
**demonstrable**: the program presses all six, records what came back, and asserts the exact
field each sentence leans on.

If a field ever moves, the verdict goes `NOT PROVEN` and the artefact names — by
`says_who` — the document whose sentence must be edited. **An assertion is never tuned to
recover a verdict.**

---

## The command, and the run

```bash
.venv/Scripts/python.exe scripts/proof/live_semantics.py \
  --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

| | |
|---|---|
| **taken** | **2026-08-16T12:26:03Z** (UTC) |
| exit code | **0** |
| verdict | **PROVEN** — `assertions_held` **45** of **45**, `assertions_failed: []` |
| requests | **7**, every one a `GET`; `write_requests_sent: 0` |
| bytes back | **21,929** over the seven |
| credentials | **none.** No DSN, no AWS profile, no token, no environment variable, no SSM parameter, no knowledge of the seed |
| target | `ok: true` · `mainline_demo` · deploy chain **271 of 271** · `migrations_applied: 0` |
| cluster | `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)` |
| schema fingerprint | `ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339` |

Every identifier was **discovered, not typed**. `GET /v1/demo/subjects` is the only source of the
clause uuid, the permit id, the run id and the receipt id; the artefact's `source_audit` records
`uuid_literals_in_the_source: 0` and `origin_host_occurrences_in_the_source: 0` over the
producer's own bytes (`source_sha256`
`a02b29ea742dc95eb780ed5402e3224de58eb4fdcba2c2acadc5fa3aea555811`, 57,148 bytes). Substituting
your own origin therefore probes *your* deployment rather than mismatching against this one.

---

## THE SIX. Substitute the demo URL for `$B`

Everything below is a **`GET`**. Nothing below needs an account, a token, a header or a clone.

The identifiers in these commands are **this** deployment's, and they are printed here only so
the commands are copy-pasteable. They are not knowledge the reader has to bring, and they are
not knowledge the producer has: `curl -s "$B/v1/demo/subjects"` answers with all of them, out of
`SELECT`s, and that is the one request `live_semantics.py` sends before any other.

### 1 · Provenance — the clause, and the incident that wrote it

```bash
curl -s "$B/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry"
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/blame_edges/0/basis` | `"asserted_document"` | `db:column` |
| `/data/blame_edges/0/evidence_quote_sha256` | `f83044c9…a7c9` (64-hex) | `db:column` |

The blame edge says **why** it exists, and the answer is a document somebody asserted — not a
similarity score, which is what a vector store would have offered instead. The quote the
attribution rests on is **digested**, so *"that is not what the report said"* is a checkable
claim rather than an argument.

### 2 · Ancestry — a commit DAG, walked

```bash
curl -s "$B/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry"   # the same request
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/commit_chain/0/control_delta` | `"introduce"` | `db:column` |
| `/data/closure/depth` | `1` | `db:column` |
| `/data/closure/ancestor_count` | `1` | `db:column` |

**Provenance and ancestry are one lookup, not two** — that is itself part of the claim, and the
artefact records both semantics against a single request. The chain records what each version
*did* to the control, not merely that it changed, and the ancestry is projected into a closure
the gate reads in one lookup.

### 3 · Severity floors — a fatality's relevance never decays

```bash
curl -s "$B/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks"
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/checks/0/precursor/severity_gate` | `4` | `db:column` |
| `/data/checks/0/precursor/severity_basis` | `"human_rated"` | `db:column` |
| `/data/checks/0/origin` | `"blame_ancestry"` | `db:column` |

**This is the field that decides axis one.** The severity on the obligation was *projected* by
`mainline.fn_check_project` from blame closure under invariant MI25, so a client never typed it.
**If that number were the client's own, memory here would be a cache and the axis-one claim
would be falsified.** The projection itself is proven separately and is not re-proven here:

* [`evidence/gate-refusal/proof-20260810T054407Z.json`](../../evidence/gate-refusal/proof-20260810T054407Z.json)
  `#projection` — `assertions_total: 10`, `assertions_held: 10`, the last of them reading
  `emitted=4 projected=4 supplied=0`.
* [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json) `#projection` — the
  seed line located on disk, and the `severity_was_projected_not_typed` /
  `virulence_was_projected_not_typed` assertions over it.

What **this** page adds is the **live** corroboration off the deployed origin: the same `4`, with
its `severity_basis` beside it, returned to an anonymous `curl`.

### 4 · Logged silence — what the recall declined to surface, with its arithmetic

```bash
curl -s "$B/v1/permits/dec0de00-0006-4000-8000-000000000001/silence"
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/receipt/corpus_root` | `91e35cc5…5329` | `db:column` |
| `/data/receipt/candidate_root` | `f23c0569…26ab` | `db:column` |
| `/data/receipt/theta` | `0.35` | `db:column` |
| `/data/receipt/s` | `1` | `db:column` |
| `/data/receipt/n` | `1` | `db:column` |
| `/data/receipt/boundary_proof/leaf_s/leaf_hash_hex` | `f23c0569…26ab` | `db:column` |
| `/data/receipt/boundary_proof/leaf_s/index` | `0` | `db:column` |
| `/data/receipt/policy_version` | `"demo-recall-1.0"` | `db:column` |

**Read this one honestly, because we do — ruling R4.** See the caveat below; it is not an
appendix, it is part of the claim.

### 5 · Retrieval accounting — the run auditing itself

```bash
curl -s "$B/v1/recall-runs/dec0de00-0009-4000-8000-000000000001"
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/counts/n_candidates` | `1` | `db:column` |
| `/data/counts/n_blocking` | `1` | `db:column` |
| `/data/counts/n_advisory` | `0` | `db:column` |
| `/data/counts/n_silenced` | `0` | `db:column` |
| `/data/counts/n_deduped` | `0` | `db:column` |
| `/data/index_plan_digest` | `d98e50a8…439b` | `db:column` |

The digest of the plan the pass ran is what makes the retrieval **reproducible rather than
recalled** — the difference between a memory system and a log of one.

### 6 · Exposure — who was shown the memory

```bash
curl -s "$B/v1/receipts/dec0de00-0008-4000-8000-000000000001"
```

| the field that proves it | it reads | chip |
|---|---|---|
| `/data/receipt_digest` | `993c00c3…af46` | `db:column` |
| `/data/actor_sub` | `"demo.signer"` | `db:column` |
| `/data/lines/0/payload_digest` | `d48e0eb9…c55b` | `db:column` |

A memory nobody was shown cannot bind anybody. The receipt is digested **per line**, not per
receipt, so one line can be produced without the rest.

---

## The two caveats, stated before anyone has to ask

### R4 · The silence ledger is complete and its `entries` list is **empty**

> **This run withheld nothing.** The silence receipt is complete — it carries `corpus_root`,
> `candidate_root`, `theta`, `s`, `n` and a boundary proof — and its **`entries` list is
> EMPTY**, which the recall run corroborates from a *different* response with
> `counts.n_silenced: 0`. What is demonstrated is the **apparatus**: the arithmetic a
> withholding would have to publish, bound to a corpus root and a threshold, on a run that
> suppressed no precursor at all. A reader who takes the empty list for a list of withheld
> precursors has read it backwards, and any sentence in this repository that could be read that
> way is a false claim.

That paragraph is not prose written beside the measurement — it is `R4_SENTENCE` in the producer
and it is written into the artefact verbatim, so every document that mentions the silence ledger
copies it rather than paraphrasing it.

**And it is mechanised.** The program counts the entries in the silence payload, reads
`counts.n_silenced` off the **recall-run response**, and asserts the two agree
(`the_silence_ledger_agrees_with_the_recall_run`, held: `entries=0`, `n_silenced=0`). One
endpoint asserting a withholding count is a fact about one reader; **two endpoints agreeing
about it is a fact about the database.**

### SYNTHETIC · The world these semantics are about is authored

Per [`docs/HONESTY.md`](../HONESTY.md) §SYNTHETIC: *"The procedures, clauses, setpoints,
incidents and permits under `verticals/mainline/` were written for this repository… No real
incident, no real fatality, no real site."* The corpus, the site, the operator and the incident
in every payload above are **manufactured inputs**, and the deployment says so in its own fields
— `title` and `evidence_summary` on the live responses both begin with the word `SYNTHETIC`.

What is proven here is that **the deployment answers these six questions about that world with
these fields**. It is not a claim that the world is anyone's.

---

## R5 · Every response says which half of its answer the database wrote

Every envelope carries a `provenance` array of per-field chips addressed by RFC 6901 pointer —
`db:column`, `derived`, `db:constraint`, `staged` — plus a top-level `staged` flag. Measured
across the six envelope responses:

| response | chips | kinds | `staged` |
|---|---:|---|---|
| `GET /v1/demo/subjects` | 52 | `db:column`, `derived` | `false` |
| `GET /v1/clauses/{clause_uuid}/ancestry` | 11 | `db:column`, `db:constraint`, `derived` | `false` |
| `GET /v1/permits/{permit_id}/blocking-checks` | 6 | `db:column`, `derived` | `false` |
| `GET /v1/recall-runs/{run_id}` | 17 | `db:column` | `false` |
| `GET /v1/permits/{permit_id}/silence` | 6 | `db:column`, `derived`, **`staged`** | **`true`** |
| `GET /v1/receipts/{receipt_id}` | 13 | `db:column` | `false` |

**Exactly one of the six declares itself staged, and it names the field.** The silence payload's
`staged_note` opens:

> *"`receipt.bound.statement` is the only value in this payload that no column produced.
> `mainline_meas.silence_receipt` carries `silence_receipt_id`, `run_id`, `permit_id`,
> `corpus_root`, `candidate_root`, `theta`, `s`, `n`, `boundary_proof`, `policy_version` and
> `issued_at`, and nothing else… `bound.index_generation` and `bound.index_plan_digest` **ARE**
> columns, of `mainline_meas.recall_run`."*

The chip array points at the same field by pointer rather than by prose —
`{"chip": "staged", "pointer": "/receipt/bound/statement"}` — and the artefact asserts all three
facts separately: that the flag is `true` on exactly one response, that the note names the
field, and that a chip addresses it. **A payload that flags its own non-column field is rarer
than the receipt itself, and it is quoted as a strength, never trimmed.**

`GET /v1/health` answers a bare object rather than a MAINLINE envelope — no `provenance`, no
`staged`, no `statement_refs`. That is recorded as a property of the route and **not** as a
failure, and the R5 assertions are scoped to the six that are envelopes.

---

## The nine joins that make six responses one world

None of these can hold by construction: each compares a value from **one** response against a
value from **another**. All nine held.

| join | holds because |
|---|---|
| `the_obligation_names_the_recall_run` | `blocking-checks /data/checks/0/recall_run_id` == `recall-runs /data/run_id` |
| `the_obligation_names_the_blamed_event` | `blocking-checks …/precursor_event_id` == `ancestry /data/blame_edges/0/event_id` |
| `the_obligation_cites_the_blamed_commit` | `blocking-checks …/commit_id` == `ancestry /data/blame_edges/0/commit_id` |
| `the_silence_receipt_is_of_that_run` | `silence /data/receipt/run_id` == `recall-runs /data/run_id` |
| `the_silence_receipt_is_bound_to_the_index_plan` | `silence /data/receipt/bound/index_plan_digest` == `recall-runs /data/index_plan_digest` |
| `the_exposure_receipt_names_that_silence_receipt` | `receipts /data/silence_receipt_id` == `silence /data/receipt/silence_receipt_id` |
| `the_exposure_receipt_is_over_the_same_corpus` | `receipts /data/corpus_root` == `silence /data/receipt/corpus_root` |
| `the_exposure_line_names_the_obligation` | `receipts /data/lines/0/check_id` == `blocking-checks /data/checks/0/check_id` |
| `retrieval_and_exposure_share_the_policy` | `receipts /data/policy_version` == `recall-runs /data/policy_version` |

---

## What this program sends, and what it will never send

**Seven `GET`s. No `POST`, no `PUT`, no `DELETE`, no write of any kind, of any shape, ever.**

```
GET /v1/demo/subjects                        GET /v1/recall-runs/{run_id}
GET /v1/health                               GET /v1/permits/{permit_id}/silence
GET /v1/clauses/{clause_uuid}/ancestry       GET /v1/receipts/{receipt_id}
GET /v1/permits/{permit_id}/blocking-checks
```

Not even `POST /v1/demo/gate-run`, which is safe and which the sibling transcript
[`scripts/proof/live_beats.py`](../../scripts/proof/live_beats.py) owns. The *act* half of the
loop — the refusal's `mus` and `naa` — is **that** file's claim and not this one's, and this page
does not borrow it.

The rule is **asserted against the program's own request list** rather than promised:
`request_discipline` records `total_requests: 7`, `methods: ["GET"]`,
`write_requests_sent: 0`, and `routes_sent_match_routes_declared: true`. It reads no credential,
no DSN, no AWS profile, no environment variable and no SSM parameter, and sends no header but
`accept`. There is nothing in the transcript to redact, which is why — unlike `live_beats.py` —
it runs no masker: a masking pass over a document that cannot contain a secret is theatre, and
theatre in an evidence pipeline teaches its reader to stop looking.

---

## What this program contributes, stated precisely

`scripts/proof/memory_loop.py` makes the **stronger** claim — that *no* value in its artefact
originates in its own source — and audits 79 values to prove it. **This file does not borrow that
claim, because here it would be false**, and the difference is written on the artefact's own
face:

* **Identifiers — none.** Every subject is resolved from `GET /v1/demo/subjects`. There is no
  UUID literal in the producer and `source_audit` counts them to prove it (`0`). `--base-url` is
  required for the same reason: a default origin would be a value in the artefact that came from
  the artefact's own producer.
* **Expectations — yes, deliberately.** The `CLAIMS` table carries the literal values the
  submission copy states, each tagged `says_who` with the document that states it. That is the
  point of a guard. `live_beats.py` asserts its four SQLSTATEs from a constant rather than
  reading them off the server's own verdict, for the same reason: **a checker that only records
  what it was told cannot go red, and a check that cannot fail is decoration**
  ([`docs/regression/GUARD.md`](../regression/GUARD.md)).

So the honest one-line claim is: **this file writes down what the copy says and asks the
deployment whether it is still true.**

---

## Check any of it in under a minute

1. **The six semantics, without a clone.** Run any `curl` above and read the field named beside
   it. No account, no token, no header.
2. **The whole thing, re-derived.** Run the command at the top of this page. It needs Python 3.13
   and the URL — no credential, no database, no AWS access. Expect exit `0`, `VERDICT PROVEN`,
   and a fresh `evidence/demo/live-semantics.json` differing only in the `read_at` stamps and the
   `observed_at` the server put on each response.
3. **That the assertions can go red.** The three tests are pure functions. Falsify them offline,
   with no network:

   ```bash
   .venv/Scripts/python.exe -c "import importlib.util,sys; \
   s=importlib.util.spec_from_file_location('p','scripts/proof/live_semantics.py'); \
   m=importlib.util.module_from_spec(s); sys.modules['p']=m; s.loader.exec_module(m); \
   print(m.holds(m.EQUALS,4,4), m.holds(m.EQUALS,4,0), m.holds(m.SHA256,None,'a'*63))"
   ```

   Expect `True False False`. Measured 2026-08-16 over nine cases — the contract value holds; a
   `severity_gate` of `0`, a `bool` wearing an `int`'s shape, a missed pointer, a 63-character
   digest and an uppercase digest all go red.
4. **That it sent no write.** `evidence/demo/live-semantics.json` → `request_discipline` →
   `requests_sent`. Seven entries, every `method` `GET`.

---

## What this artefact does **not** prove

Copied from `not_proven_by_this_artefact` in the file itself. Every line is a limit of *this*
artefact, not a known defect of the product.

* **Not that the world is anyone's.** SYNTHETIC, above.
* **Not the ACT half of the loop.** That is `POST /v1/demo/gate-run`, proven in
  [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) and narrated in
  [`docs/demo/LIVE-BEATS.md`](LIVE-BEATS.md). This program sends no `POST` at all.
* **Not that a screen renders any of this.** No browser ran; this is an HTTP client.
* **Not a latency figure.** No duration is recorded here at all, because a `GET` envelope on this
  API carries no server-measured duration and a wall clock wearing a server's name is how a demo
  narrates its own reveal delay as database latency.
* **Not that these semantics hold for every subject.** One seeded subject was read, once, and
  every identifier it was read by is in `request_discipline.identifiers`.
* **Not that the store is CockroachDB rather than any PostgreSQL-wire server.** What is recorded
  is the `cluster_version` string the deployment reported about itself.

---

## Related

| | |
|---|---|
| the **act** half — four beats, one transaction, one `ROLLBACK` | [`docs/demo/LIVE-BEATS.md`](LIVE-BEATS.md) · [`evidence/demo/live-beats.json`](../../evidence/demo/live-beats.json) |
| STORE → RETRIEVE → SHOWN TO → ACT, `23` of `23` assertions | [`docs/demo/MEMORY-LOOP.md`](MEMORY-LOOP.md) · [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json) |
| the rulings this page obeys | [`docs/submission/extra-credit-plan.md`](../submission/extra-credit-plan.md) §1 |
| what is manufactured, and what is staged | [`docs/HONESTY.md`](../HONESTY.md) §SYNTHETIC |
