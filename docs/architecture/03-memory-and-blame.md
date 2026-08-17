<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# 03 · Memory and blame — where the obligation came from

*You are here: chapter 3 of 5. Start at the front door, [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).
Chapter 2 showed one request being refused. This chapter answers the question it left open:
**who decided that this permit owed anything at all?***

---

## 1 · The sequence, before any schema

A **permit** is a written authorisation for one specific dangerous job — one place, one crew, one
window of time ([glossary](GLOSSARY.md#permit)). A **clause** is one numbered rule inside a
procedure or standard ([glossary](GLOSSARY.md#clause)). Here is the whole chapter as a sequence of
five things that happened, in order. Everything after this section is the mechanism underneath it.

**1. Something went wrong, and it was written down.** On 14 March 2019 an isolation was signed off
without verification at zero, and residual hydraulic pressure released while a guard was being
removed. That incident became one row, with a date and a severity rated by a person rather than by
a model. [src: `verticals/mainline/db/seeds/demo/demo_world.sql:272`, served live at
`/data/events/0/occurred_at`. Incident, site and operator are **authored** — see §8.]

**2. Somebody changed a rule because of it — and recorded *why*.** The clause that now governs that
work carries a pointer back to the 2019 incident. That pointer is not a note in a change log; it is
a row saying *this event wrote this clause*, carrying the **digest of the quoted words** the
attribution rests on. A digest is a fixed-length fingerprint of a piece of text: change one
character and it changes completely. So *"that is not what the report said"* becomes something a
reader checks in one command rather than something two people argue about. [src: `demo_world.sql:299`
is the `INSERT INTO mainline.blame_edge`; digest served at `/data/blame_edges/0/evidence_quote_sha256`.]

**3. Seven years later, a permit relied on that clause.** Not on the clause in general — on **one
version** of it, identified by the commit the version landed in. A later rewrite of the same
paragraph is a different version, and the memory does not slide onto it by itself.

**4. A retrieval pass went looking, and found the incident.** It walked backwards from the clause
version through the record of which incidents wrote it and which earlier incidents those descend
from. That walk is **blame ancestry**: the chain of earlier versions and earlier incidents a clause
descends from, walked as a graph rather than read out of a field ([glossary](GLOSSARY.md#ancestry)).

**5. Ten seconds later the finding was an obligation on the permit — and the database stopped
issuing it.** An **obligation** (in the schema, a *blocking check*) is something that must be settled
before the permit may be issued ([glossary](GLOSSARY.md#obligation)). From the instant that row
existed, a `CHECK` on the permit refused the write that would have turned it into an authorisation.
Nobody had to remember. Nobody had to be on shift.

**The interval really is ten seconds, and it is a subtraction of two columns off two different live
routes rather than a sentence somebody wrote** — §6 shows the arithmetic
[src: [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json)`#gap.seconds`].

**What this is not.** Not a search box over incident PDFs, and not a similarity score — a score
would have said *these two documents look alike*. What is stored is the claim *a named document,
at a quotable byte range, says this incident wrote this rule*, with the four possible kinds of
claim kept apart on purpose (§2.3).

---

## 2 · The rows that make step 2 and step 4 possible

### 2.1 The incident — `mainline.event`

Four relations carry the whole of it, each opened in this session at the path given. The first is
`verticals/mainline/db/migrations/0033_event.sql`, where two columns decide everything downstream:
`severity_gate` (the number this system acts on — `4` on the demo row) and `severity_basis`
(**who says so** — `human_rated`). One `CHECK` in that file ties the two together:

```sql
CONSTRAINT model_cannot_arm CHECK (severity_gate < 4 OR severity_basis <> 'model_rated')
```

A model-rated severity **cannot reach 4**. It is refused by the database, not discouraged by a
policy document. Everything in this chapter that leans on the number `4` leans on a row that a
person is on the hook for.

### 2.2 The clause version — `mainline.clause_version`

`0029_clause_version.sql`. A clause is not one row; each version is a row, keyed by the commit it
landed in, with `parent_version` pointing at the version before it. Two columns matter here:

* `control_delta` — **what the edit did to the control**, not merely that it changed. The enum at
  `0010_type_control_delta.sql:26-32` has exactly five values: `introduce`, `strengthen`,
  `restate`, `weaken`, `remove`. The demo's version reads `introduce`.
* `canon_sha256` — the digest of the clause text after **canonicalisation**: writing the text in
  one fixed byte-for-byte form so two machines that hash it get the same answer
  ([glossary](GLOSSARY.md#canonicalisation)).

`mainline.commit_edge` (`0025_commit_edge.sql`) is the commit graph those versions sit in.

### 2.3 The pointer — `mainline.blame_edge`

`0037_blame_edge.sql`. One row says: *this event wrote this clause*. Its `basis` column carries
**four different claims, not four confidences of the same claim** — the file's own framing — and
`basis` is part of the primary key, so all four can coexist about the same pair:

| `basis` | what it means | what the schema demands of it |
|---|---|---|
| `asserted_document` | a source document says so, at a byte range we can quote | `asserted_needs_quote` — refused without `evidence_quote_sha256` |
| `asserted_human` | a named person signed for the link | `human_needs_signature` — refused without `review_sig` |
| `derived_documentary` | re-derivable by machine from recorded control failures | `scored_needs_features` — a score arrives with its evidence |
| `inferred_semantic` | a model thought these were about the same thing | `inference_never_blocks` — **may never be `active`** |

```sql
CONSTRAINT inference_never_blocks CHECK (basis <> 'inferred_semantic' OR state <> 'active')
```

The closure walk (§2.4) filters `state = 'active'`. So a model's guess is recorded, shown and
argued with — and it can never raise the severity that arms a gate. Promoting one is an *insert* of
a second row with `basis = 'asserted_human'` and a signature, never an update, so the machine's
original guess stays visible beside the person's endorsement of it. The demo's edge is
`asserted_document`, `active`.

### 2.4 The walk, run once — `mainline.clause_blame_closure`

`0038_clause_blame_closure.sql`, written by the recursive query at
`verticals/mainline/db/queries/closure_write.sql:152-167`. The walk goes up
`mainline.blame_edge` and then up `mainline.event_edge` (`0034_event_edge.sql`, whose `relation`
is closed to `recurrence_of`, `precursor_of`, `supersedes`), and collapses the result into **one
row** carrying `depth`, `ancestor_count`, `max_severity` and `virulence`.

The view `mainline.clause_blame_current` (`0039_clause_blame_current.sql:109`) picks the highest
`closure_gen` per `(clause_uuid, as_of_commit)`. **That is the one lookup the gate does.** The
graph walk happens when the memory is written, not when a permit is being issued.

Two constraints in `0038` keep the row from lying about itself:

```sql
CONSTRAINT truncation_is_declared  CHECK (truncated = true OR (ancestor_count < 512 AND depth < 64))
CONSTRAINT count_matches_the_array CHECK (ancestor_count = coalesce(array_length(ancestor_events,1),0))
```

A walk that stopped early cannot be stored as if it finished, and the count cannot disagree with
the list. The direction rule — a child's ancestry may extend its parent's and its inherited
severity may not fall, except by a signed second rater's dated act — is
[`I05`](../../spec/invariants/I05-ancestry-monotone.md); §9 carries what it does **not** claim.

---

## 3 · Diagram — the blame ancestry walk

Every box below is a relation, a route or a trigger located at a path in §2 and §4.

```
 THE WALK — up from the permit to the incident that wrote the rule
 ══════════════════════════════════════════════════════════════════════════════════

  mainline.permit                              GET /v1/permits/{permit_id}
    state 'dispositioned'  ·  open_blocking 1
        │  one row per obligation
        ▼
  mainline.blocking_check                      GET /v1/permits/{permit_id}/blocking-checks
    origin 'blame_ancestry'  ·  severity 4  ·  virulence 'blood_major'
    (clause_uuid, commit_id) ── names a clause VERSION, never a bare clause
        │
        ▼
  mainline.clause_version                      GET /v1/clauses/{clause_uuid}/ancestry
    gen 0 · commit 9f12114d… · control_delta 'introduce' · sev_max 4
        ▲   parent_version → the version before it   (NULL here: birth version)
        │   the commit DAG behind it is mainline.commit_edge (child_id → parent_id)
        │   control_delta ∈ introduce · strengthen · restate · weaken · remove
        │
  mainline.clause ◀── mainline.blame_edge ──▶ mainline.event
    dec0de00-0004-…       basis 'asserted_document'    external_ref 'DEMO-INC-0001'
                          state 'active'               occurred_at 2019-03-14T06:20:00Z
                          evidence_quote_sha256        severity_gate 4
                            f83044c9…a7c9              severity_basis 'human_rated'
                                                             │
                                                             │ mainline.event_edge
                                                             ▼ precursor_of · recurrence_of
                                                       earlier events, walked

 THE CLOSURE — that walk, run once at write time, stored as ONE row
 ══════════════════════════════════════════════════════════════════════════════════

  queries/closure_write.sql  ──writes──▶  mainline.clause_blame_closure   (append-only)
                                                │  highest closure_gen wins
                                                ▼
                                  VIEW mainline.clause_blame_current
                                    key  (clause_uuid, as_of_commit)
                                    depth 1 · ancestor_count 1
                                    max_severity 4 · virulence 'blood_major'
                                  ── ONE LOOKUP. The gate never re-walks the graph. ──

 THE PROJECTION — back down onto the obligation
 ══════════════════════════════════════════════════════════════════════════════════

  mainline.clause_blame_current
        │  read by mainline.fn_check_project()        migration 0100, MI25
        │  welded BEFORE INSERT FOR EACH ROW as TRIGGER check_project   (0120)
        │  no IF-guard: the value the writer supplied is overwritten unconditionally
        ▼
  mainline.blocking_check.severity    := max_severity  →  4
  mainline.blocking_check.virulence   := virulence     →  'blood_major'
  mainline.blocking_check.closure_gen := closure_gen   →  0
        │  the seed wrote  0, 'routine', 0   at demo_permit.sql:318
        ▼  the deployment serves  4, 'blood_major', 0
  mainline.permit.open_blocking = 1
        └─ read by CHECK gate_closed_when_issued   (0050_permit.sql:114) → chapter 02
```

---

## 4 · The arrow back down: the severity is written by the database, not supplied

A **projection** is a value the database writes onto a row **by itself**, derived from other rows,
overwriting whatever the writer supplied ([glossary](GLOSSARY.md#projection)). The obligation's
severity is one. `mainline.fn_check_project()` (`0100_fn_check_project.sql:60-84`) reads one row of
`mainline.clause_blame_current` by `(clause_uuid = NEW.clause_uuid, as_of_commit = NEW.commit_id)`,
and then:

```sql
-- UNCONDITIONAL. A supplied value is overwritten whether or not it agrees.
NEW.severity   := v_severity;
NEW.virulence  := v_virulence;
NEW.closure_gen := v_closure_gen;
```

If there is no closure row it raises `P0001` — *"no blame closure for this clause version — cannot
arm a check"*. **Absence of evidence refuses; it never defaults.** The function is inert until it is
attached, and `0120_trg_check_project.sql:28-29` attaches it `BEFORE INSERT FOR EACH ROW` on
`mainline.blocking_check`. Both files carry `MI: MI25` in their headers. Why it exists: an agent
role that could write an obligation could otherwise choose its own severity band, and the clearance
rules downstream would then enforce a claim the writer made about itself. The function's own
rationale block names that as *"Finding S1"*.

**The check that this actually ran.** The seed writes `0, 'routine', 0` onto that obligation
(`verticals/mainline/db/seeds/demo/demo_permit.sql:318`, comment `-- projected over by
fn_check_project (MI25)`). The deployment serves `4` and `blood_major`. Those two are compared,
seed against wire, as assertions that can turn a verdict red
[src: [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json)`#projection`].
*Nobody typed the four* is only true because the projection ran, so the sentence is never printed
without the projector's name.

---

## 5 · The six memory semantics, each an anonymous `GET`

Substitute the demo origin for `$B`. Nothing below needs an account, a token, a header or a clone.
Every field in the "reads" column was **re-read live from the deployed origin this session**; the
recorded run asserting each of them is
[`evidence/demo/live-semantics.json`](../../evidence/demo/live-semantics.json), taken
`2026-08-16T12:26:03Z`, verdict `PROVEN`, `45` of `45` assertions held, `7` requests, all `GET`,
`write_requests_sent: 0`. Narrated in [`docs/demo/LIVE-SEMANTICS.md`](../demo/LIVE-SEMANTICS.md).

### 1 · Provenance — the incident that wrote the clause

```bash
curl -s "$B/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry"
```

| the field that proves it | reads |
|---|---|
| `/data/blame_edges/0/basis` | `"asserted_document"` |
| `/data/blame_edges/0/evidence_quote_sha256` | `f83044c9…a7c9` (64 hex) |

**A document somebody asserted — not a similarity score, which is what a vector store would have
offered instead.** The quote is digested, so the attribution is checkable.

### 2 · Ancestry — the versions, and the closure — *from the very same request*

| the field that proves it | reads |
|---|---|
| `/data/commit_chain/0/control_delta` | `"introduce"` |
| `/data/closure/depth` | `1` |
| `/data/closure/ancestor_count` | `1` |

**Provenance and ancestry are one lookup, not two** — that is itself part of the claim, and the
artefact records both semantics against a single request.

### 3 · Severity floors — and the sentence that decides the axis

```bash
curl -s "$B/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks"
```

| the field that proves it | reads |
|---|---|
| `/data/checks/0/precursor/severity_gate` | `4` |
| `/data/checks/0/precursor/severity_basis` | `"human_rated"` |
| `/data/checks/0/origin` | `"blame_ancestry"` |

The `4` was projected by `mainline.fn_check_project` under MI25 (§4), so a client never typed it.
**If that number were the client's own, memory here would be a cache** and the claim that this
system's memory has semantics would be falsified.

### 4 · Logged silence — the arithmetic a withholding would have to publish

```bash
curl -s "$B/v1/permits/dec0de00-0006-4000-8000-000000000001/silence"
```

| the field that proves it | reads |
|---|---|
| `/data/receipt/corpus_root` | `91e35cc5…5329` |
| `/data/receipt/theta` | `0.35` (the threshold) · `/s` `1` · `/n` `1` |
| `/data/receipt/policy_version` | `"demo-recall-1.0"` |
| `/data/entries` | `[]` — **empty. Read §7 before quoting this one.** |

### 5 · Retrieval accounting — the run auditing itself

```bash
curl -s "$B/v1/recall-runs/dec0de00-0009-4000-8000-000000000001"
```

| the field that proves it | reads |
|---|---|
| `/data/counts/n_candidates` · `n_blocking` · `n_advisory` | `1` · `1` · `0` |
| `/data/counts/n_silenced` · `n_deduped` | `0` · `0` |
| `/data/index_plan_digest` | `d98e50a8…439b` |

`mainline_meas.recall_run` (`0081_recall_run.sql:49`) carries `CONSTRAINT candidates_conserved
CHECK (n_candidates = n_blocking + n_advisory + n_silenced + n_deduped)` — the universe is exactly
partitioned by `CHECK`, per [`I13`](../../spec/invariants/I13-silence-logged.md). The plan digest
is what makes the retrieval reproducible rather than merely recalled.

### 6 · The act — who was shown it, and what it stopped

```bash
curl -s "$B/v1/receipts/dec0de00-0008-4000-8000-000000000001"
```

| the field that proves it | reads |
|---|---|
| `/data/actor_sub` | `"demo.signer"` |
| `/data/receipt_digest` | `993c00c3…af46` |
| `/data/lines/0/payload_digest` | `d48e0eb9…c55b` |
| `/data/lines/0/check_id` | equals `blocking-checks` `/data/checks/0/check_id` — a cross-response join |

A memory nobody was shown cannot bind anybody. The receipt is digested **per line**, so *"I was
never told about that one"* is a checkable claim. The *refusal* half of the act — the `23514` on the
issue write — is chapter 02's, proven by `POST /v1/demo/gate-run` and narrated in
[`docs/demo/LIVE-BEATS.md`](../demo/LIVE-BEATS.md); this chapter sends no `POST`.

---

## 6 · The ten seconds, and why it is a subtraction rather than a sentence

```
mainline_meas.recall_run.started_at       2026-08-02T03:00:00Z  GET /v1/recall-runs/{run_id}
mainline.blocking_check.materialised_at   2026-08-02T03:00:10Z  GET /v1/permits/{id}/blocking-checks
                                          ────────────────────
                                                        10.0 s
```

Both are **columns**, arriving in **two different responses**. The gap is the subtraction of one
ISO-8601 string from the other, and **the number ten is nowhere in the program that computed it**
[src: [`evidence/demo/memory-loop.json`](../../evidence/demo/memory-loop.json)`#gap.seconds`, with
`gap.stated_anywhere_in_this_program: false`]. Both instants are then corroborated against the seed
at `demo_permit.sql:250` and `:321`, each with its own status so *not found* is never read as
*agreed*.

**The producer audits itself.** `evidence/demo/memory-loop.json` records `23` of `23` assertions
held, verdict `PROVEN`; its `self_audit` block reports `values_audited: 79`,
`values_found_in_the_source: []` and `uuid_literals_in_the_source: 0` — the producer reads its own
bytes and searches them for every value it recorded, so a value the program supplied to itself
would turn the verdict red. That check has already gone red once, on prose in the producer's own
docstrings; the prose was changed and the check was not weakened.

**What ten seconds is and is not.** It is what the retrieval-to-obligation path costs in this
seeded world — a narrative interval in an authored history, not a benchmark of the running system.
The artefact says so by naming the two columns rather than calling it a latency. Full narration in
[`docs/demo/MEMORY-LOOP.md`](../demo/MEMORY-LOOP.md).

---

## 7 · The silence receipt, read the way the repository reads it

A **silence receipt** is the record of what a search *declined* to show, with its arithmetic — so
*"nothing relevant was found"* is a checkable claim, not an absence ([glossary](GLOSSARY.md#silence)).

**On the seeded run, `entries` is EMPTY and `n_silenced` is `0`. Nothing was withheld.** What is
demonstrated is the **apparatus** — the arithmetic a withholding would have to publish, bound to a
corpus root and a threshold — on a run that suppressed no precursor at all. **A reader who takes
the empty list for a list of withheld precursors has read it backwards.**

That is not a caveat written beside the measurement. It is `R4_SENTENCE` at
`scripts/proof/live_semantics.py:133`, written verbatim into the artefact, so every document that
mentions the silence ledger copies it rather than paraphrasing. And it is mechanised: the program
counts the entries in the silence payload, reads `counts.n_silenced` off the **recall-run
response**, and asserts the two agree. One endpoint asserting a withholding count is a fact about
one reader; two endpoints agreeing is a fact about the database.

**One value in that payload the database did not author.** The silence response is the only one of
the six that sets `staged: true`, and it names the field: `receipt.bound.statement`.
`mainline_meas.silence_receipt` (`0083_silence_receipt.sql:40`) carries `silence_receipt_id`,
`run_id`, `permit_id`, `corpus_root`, `candidate_root`, `theta`, `s`, `n`, `boundary_proof`,
`policy_version` and `issued_at`, **and nothing else** — while `bound.index_generation` and
`bound.index_plan_digest` *are* columns, of `mainline_meas.recall_run`. A per-field chip
`{"chip": "staged", "pointer": "/receipt/bound/statement"}` addresses it by RFC 6901 pointer rather
than by prose. Verified live this session; recorded in
[`live-semantics.json`](../../evidence/demo/live-semantics.json).

The normative side — a declined surfacing must be written **with its arithmetic, in the same
transaction as the decision** — is [`I13`](../../spec/invariants/I13-silence-logged.md). Its
companions are [`I07`](../../spec/invariants/I07-universe-commitment.md) (a retrieval must commit
to the universe it drew from, and a threshold must not be adjustable afterwards) and
[`I08`](../../spec/invariants/I08-certified-null.md) (*"nothing found"* is not insertable as a bare
fact). Each ends with its own **NOT CLAIMED** section: `I07` does not claim the corpus was
exhausted, and `I08` does not claim the empty answer is correct.

---

## 8 · What is designed here and not exercised — stated plainly

Leaving these visible costs a better-looking page; deleting the question was the shorter path, and
this section is the record of not taking it.

* **Archival bonds and fixity are design, not routes.** `mainline_meas.recall_run.n_bonded_sev5`
  reads `0` on the live run, and `mainline_audit.v_fixity_coverage` answers with an empty rows
  array — `row_count: 0`, `rows: []`
  [src: [`evidence/mcp/auditor-live.json`](../../evidence/mcp/auditor-live.json)`#questions/8`].
  **A counter reading zero demonstrates nothing.** The `CHECK` that would make a bonded fatality
  always blocking exists and is named (`bonded_fatalities_all_blocking`, `0081_recall_run.sql`) —
  and with `n_bonded_sev5` at `0`, the seeded run gave it nothing to refuse.
* **Bedrock executes in this repository and NOT in the demo request path.** The embedding tables
  are real and located — `mainline.clause_embedding` (`0031`) and `mainline.event_cue_embedding`
  (`0041`), both `VECTOR(1024)` — but the deployed read routes in §5 do not call a model and do not
  embed anything. **The recall design's model calls are not what the demo does.**
* **The corpus is authored.** The procedures, clauses, setpoints, incidents and permits under
  `verticals/mainline/` were written for this repository. No real incident, no real fatality, no
  real site — and the deployment says so in its own fields: `title` and `evidence_summary` on the
  live responses begin with the word `SYNTHETIC` [src: [`docs/HONESTY.md`](../HONESTY.md)
  §SYNTHETIC].
* **The model transcripts are recorded cassettes.** Agent tests replay captured request/response
  pairs. A green agent test proves the code handles that recorded exchange; it does not prove
  anything about a live model's behaviour today [src: `docs/HONESTY.md:505`].

---

## 9 · What this chapter does not claim

* **Not that the ancestry is complete.** An edge nobody derived is not in the closure. What the
  monotonicity rule forecloses is *shrinkage* — the path where a control is reworded across four
  revisions until nobody recalls what wrote it
  ([`I05`](../../spec/invariants/I05-ancestry-monotone.md)) — and **not** that the severity is
  correct: `I05` constrains its *direction over lineage*, not its value.
* **Not that the silence was correct.** `I13` claims it is *recorded with its arithmetic*, so a
  reviewer can reconstruct the decision and disagree with it.
* **Not that these semantics hold for every subject.** One seeded subject was read, and every
  identifier it was read by is in the artefact's `request_discipline.identifiers`. **Not a latency
  figure** either: no duration is recorded on these `GET`s at all.

---

The permit, the obligation, the clause version, the blame edge, the closure, the recall run and the
two receipts — **and every one of those lives somewhere in the tree.**

**Next:** [04 · The map](04-the-map.md) · [front door](../ARCHITECTURE.md) · [glossary](GLOSSARY.md)
