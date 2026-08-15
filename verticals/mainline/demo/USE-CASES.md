<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# THE TWO USE CASES — what MAINLINE refuses, and why that is hard

**Owner:** W1 (demo-story wave) · **Date:** 2026-08-15
**Target:** <https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws>
**Measured at:** `2026-08-15T04:00:07Z` · **Deployment:** `mainline_demo`, deploy chain 271/271,
schema fingerprint `ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339`
**Authority:** `docs/leads/demo-story-plan.md` §2, §3, R1, R9, R10.

---

## 0 · HOW TO READ THIS

Every section is written twice, in one column, in this order:

1. **THE LEAD** — plain language. No acronym before it is earned. If you know nothing about
   this product, the lead is complete on its own.
2. **THE EXHIBIT** — the identifiers, the SQLSTATEs, the constraint predicates, the digests.
   If you know everything, nothing has been left out of the exhibit to make the lead read well.

The lead never states something the exhibit does not support. Where the two seem to differ,
**the exhibit is authoritative** — the lead is a shorter way of saying the same thing, never a
weaker one.

**Everything below is synthetic.** The seeded corpus says so in its own text: the clause reads
`SYNTHETIC — Before any intrusive work…`, the incident is titled `SYNTHETIC — Stored energy
release…`. That prefix is a column value, not a disclaimer added here. No real permit, real
incident or real person is described.

---

## 1 · MEASUREMENT — every identifier this document names

One pass, one script, one timestamp: `2026-08-15T04:00:07Z`. Read-only except the gate-run,
which is a single SERIALIZABLE transaction that rolls itself back (§2.6). Byte counts are the
response body as `curl` received it.

| what it addresses | method | path | status | bytes |
|---|---|---|---|---|
| deployment identity | `GET` | `/v1/health` | **200** | 410 |
| permit `DEMO-PTW-0001` | `GET` | `/v1/permits/dec0de00-0006-4000-8000-000000000001` | **200** | 5691 |
| the permit's obligations | `GET` | `/v1/permits/dec0de00-0006-4000-8000-000000000001/blocking-checks` | **200** | 2408 |
| obligation `0007` lattice + defeaters | `GET` | `/v1/checks/dec0de00-0007-4000-8000-000000000001/disposition` | **200** | 3805 |
| exposure receipt | `GET` | `/v1/receipts/dec0de00-0008-4000-8000-000000000001` | **200** | 1817 |
| recall run | `GET` | `/v1/recall-runs/dec0de00-0009-4000-8000-000000000001` | **200** | 2223 |
| silence receipt | `GET` | `/v1/permits/dec0de00-0006-4000-8000-000000000001/silence` | **200** | 2386 |
| clause version `§7.3.2(b)` | `GET` | `/v1/clauses/dec0de00-0004-4000-8000-000000000001/versions/9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39` | **200** | 3230 |
| clause ancestry + blame | `GET` | `/v1/clauses/dec0de00-0004-4000-8000-000000000001/ancestry` | **200** | 3744 |
| custody / ledger | `GET` | `/v1/ledger?site_code=dec0de00-0001-4000-8000-000000000001` | **200** | 10751 |
| change request `DEMO-MOC-0001` | `GET` | `/v1/change-requests/dec0de00-000c-4000-8000-000000000001` | **200** | 3295 |
| obligation `000d` lattice + defeaters | `GET` | `/v1/checks/dec0de00-000d-4000-8000-000000000001/disposition` | **200** | 3850 |
| audit views | `GET` | `/v1/audit` | **200** | 19439 |
| evidence bundle manifest | `GET` | `/bundle/manifest.json` | **200** | 8435 |
| the four beats | `POST` | `/v1/demo/gate-run` | **200** | 10500 |

**Every identifier named in this document returns HTTP 200.** Nothing here is addressed that
the seed does not carry.

### 1.1 Negative probes — measured absence, recorded as absence

These are in the table because §3 relies on them being **404**. They are the evidence for R1,
and they are the reason use case two is told and not driven.

| what | method | path | status | bytes |
|---|---|---|---|---|
| merge the change request | `POST` | `/v1/change-requests/dec0de00-000c-4000-8000-000000000001/merge` | **404** | 664 |
| the change request's obligations | `GET` | `/v1/change-requests/dec0de00-000c-4000-8000-000000000001/blocking-checks` | **404** | 673 |

The 404 body is not a bare error. It **declares the entire route table**, which is how the
absence was confirmed rather than assumed:

```
/v1/audit                                     /v1/permits/{permit_id}
/v1/change-requests/{cr_id}                   /v1/permits/{permit_id}/blocking-checks
/v1/checks/{check_id}/disposition             /v1/permits/{permit_id}/checks:materialise
/v1/clauses/{clause_uuid}/ancestry            /v1/permits/{permit_id}/merge
/v1/clauses/{clause_uuid}/versions/{commit_id}  /v1/permits/{permit_id}/silence
/v1/demo/gate-run                             /v1/permits/{permit_id}/suspend
/v1/ledger                                    /v1/recall-runs/{run_id}
/v1/lessons/{lesson_id}/propagation           /v1/receipts/{receipt_id}
```

`/v1/permits/{permit_id}/merge` is there. There is no change-request equivalent. The kernel
says so itself.

---

## 2 · USE CASE ONE — the permit that could not merge

> **In one sentence:** *A 2019 incident blamed a safety rule. Today's permit relies on that
> same rule. The database refuses to let the work start — and it will not be talked out of it
> by editing the number it checks.*

### 2.1 THE LEAD

A crew needs to open a machine and work inside it. Before they can, somebody has to approve a
permit. In most organisations that approval is a signature on a form, and the form does not
know anything.

This one does. When the permit was opened, the database went looking for reasons this
particular job might be dangerous — not in a checklist somebody remembered to write, but in
the organisation's own history of things that went wrong. It found one. In March 2019 a worker
was hurt when stored energy was released during exactly this kind of work, and the
investigation into that incident named a specific safety rule as the control that failed.

Today's permit depends on that same rule.

So the database attached a debt to the permit: *this specific past failure has never been
answered for this specific job.* Until somebody answers it, the permit cannot merge. Not
"should not" — **cannot**. The rule is a constraint the storage engine enforces, and there is
no code path around it.

Three things then happen, and they are the whole product:

1. **You press merge. It refuses**, and it tells you the one unanswered thing that caused it.
2. **You cheat.** You reach into the database and set the counter it checks to zero, which is
   what a broken projector or a careless `UPDATE` would leave behind. **It refuses anyway** —
   because it does not trust that counter. It counts again, from the underlying rows.
3. **You answer the debt properly**, with a signed disposition, and it admits the merge. A gate
   that always refuses is broken, not safe.

Then the whole thing is undone, and the system proves it was undone rather than telling you so.

### 2.2 THE SUBJECT

| field | value | source |
|---|---|---|
| permit | `DEMO-PTW-0001` — `dec0de00-0006-4000-8000-000000000001` | `db:column` |
| ref | `refs/permits/demo-0001` | `db:column` |
| state | `dispositioned` | `db:column` |
| gate epoch / head seq | `1` / `2` | `db:column` |
| site | `dec0de00-0001-4000-8000-000000000001` | `db:column` |
| opened / horizon | `2026-08-02T00:00:00Z` / `2027-08-02T00:00:00Z` | `db:column` |

Seven counters, and **each one is welded to the CHECK constraint that reads it**. This is the
part a technical reader should look at first, because it is what makes the gate structural
rather than procedural:

| constraint | predicate | counter | value |
|---|---|---|---|
| `gate_closed_when_issued` | `CHECK ((state != 'merged') OR (open_blocking = 0))` | `open_blocking` | **1** |
| `conflicts_resolved_when_issued` | `CHECK ((state != 'merged') OR (open_conflicts = 0))` | `open_conflicts` | 0 |
| `identity_conserved_when_issued` | `CHECK ((state != 'merged') OR (open_residue = 0))` | `open_residue` | 0 |
| `boundary_certified_when_issued` | `CHECK ((state != 'merged') OR (unmodelled_asset_count = 0))` | `unmodelled_asset_count` | 0 |
| `no_open_warrant_when_issued` | `CHECK ((state != 'merged') OR (open_warrants = 0))` | `open_warrants` | 0 |
| `reading_floor_when_issued` | `CHECK (((state != 'merged') OR (unmet_floor_count = 0)) OR (countersigned_count > 0))` | `unmet_floor_count` / `countersigned_count` | 0 / 0 |
| `merge_evidence` | `CHECK ((state != 'merged') OR (merged_commit IS NOT NULL))` | — | — |

Six of the seven are satisfied. **One is not.** That is the entire story.

### 2.3 WHERE THE DEBT CAME FROM

**The rule.** `DEMO-SOP-0001 §7.3.2(b)` — clause `dec0de00-0004-4000-8000-000000000001` at
commit `9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39`:

> SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and verified
> at zero by a competent person.

`canon_sha256 = 9b15260145501b966ab79c97430953ed827db157725609b79323284a2ec50e7b`,
`printed_label 7.3.2(b)`, `gen 1`, `control_delta introduce`, `sev_max 4`,
`anchor_set [LOTO, ZERO_ENERGY]`, `doc_id dec0de00-0003-4000-8000-000000000001`.

**The incident.** `DEMO-INC-0001` — event `dec0de00-0005-4000-8000-000000000001`:

| field | value |
|---|---|
| title | `SYNTHETIC — Stored energy release during intrusive work` |
| occurred | `2019-03-14T06:20:00Z` |
| severity (gate / actual / potential) | `4` / `4` / `4` |
| severity basis | `human_rated` |
| source document | `demo/incident-0001.pdf` |
| source SHA-256 | `1f84f023f5f891fadab55ef7e9f16f08285b3803f65c509f514476ea6770ba46` |

**The blame is a foreign key, not a sentence.** The investigation naming that clause is a
`blame_edge` row, `basis asserted_document`, `state active`, carrying
`evidence_quote_sha256 f83044c99f6eedbc228fe69ca2c03648da1ed274034d3710470feae25f2ea7c9` — the
digest of the quoted passage that does the blaming. Its attribution reads *"SYNTHETIC — the
investigation names this clause as the control that failed."*

The closure computed over it: `ancestor_count 1`, `depth 1`, `closure_gen 0`,
`max_severity 4`, `virulence blood_major`, `truncated false`, `projector_ver demo-1`.
Corpus root `49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983`.

### 2.4 THE OBLIGATION, AND WHY NOBODY CHOSE IT

Obligation `dec0de00-0007-4000-8000-000000000001`:

| field | measured value |
|---|---|
| origin | `blame_ancestry` |
| severity | **4** |
| virulence | **`blood_major`** |
| closure_gen | `0` |
| open | `true` |
| dedupe key | `c4bd7e3a46a5c52c60384a8bef53e40a716dd46d2a5bad38f7f36528d312329c` |
| materialised | `2026-08-02T03:00:10Z` |
| recall run | `dec0de00-0009-4000-8000-000000000001` |

**"Nobody chose those numbers" is checkable, and here is how to check it.** The seed writes
this obligation at `severity 0, virulence 'routine'` —
`verticals/mainline/db/seeds/demo/demo_permit.sql`, with the comment `-- projected over by
fn_check_project (MI25)`. The live payload reads `severity 4, virulence blood_major`.

The seed and the deployment disagree, **on purpose**, and the difference is exactly the
projection. A severity nobody typed is the difference between a system that records a judgement
and a system that derives one.

### 2.5 THE FOUR BEATS

Measured `2026-08-15T04:00:07Z`. `verdict PROVEN`, `failures []`, all four
`matched_expectation true`.

| # | beat | outcome | SQLSTATE | constraint | source | elapsed |
|---|---|---|---|---|---|---|
| 1 | `read` | `read` | `00000` | — | — | 0.011 ms |
| 2 | `merge` | **REFUSED** | `23514` | `gate_closed_when_issued` | **reported** | 521.134 ms |
| 3 | `projection_drift_attack` | **REFUSED** | `P0001` | `mainline.fn_permit_merge_gate` | *parsed* | 568.505 ms |
| 4 | `admit` | `admitted` | `00000` | — | — | 537.324 ms |

Total `1785.258 ms`.

**Beat 2 — the refusal.** Message, verbatim:

```
failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))
```

`class gate`, `diagnosis declarative`. The refusal carries two structures a reader should not
have to derive:

* **MUS** — the minimal unsatisfiable subset, cardinality **1**: obligation
  `dec0de00-0007-…0001`, `origin blame_ancestry`, `severity 4`, `virulence blood_major`,
  detail *"open at gate_epoch 1; no live disposition"*, tracing to clause `…0004…` and event
  `…0005…`. One row. Not "something is wrong" — *this* is wrong.
* **NAA** — the nearest admissible alternative: `kind dispose_obligations`, `cardinality 1`,
  description *"1 obligation(s) remain open on this subject; disposing of exactly those
  restores admissibility"*, with the five legal kinds `applied`, `mitigated`,
  `mechanism_absent`, `escalated`, `emergency_override`.

A refusal that says what would fix it is the difference between a gate and a wall.

**`constraint_source: reported` matters.** The constraint name came from the database's own
error fields, not from string-matching a message. Beat 3's is `parsed`, and the console renders
that as a weakened diagnosis — *a parsed exhibit must never look like a reported one* (R7).

**Beat 3 — the attack.** The statement is run in the open:

```sql
UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s;
CALL mainline.merge_permit(...)
```

`counter_forced_to 0`, `open_blocking_derived 1`. The CHECK constraint of beat 2 is now
*satisfied* — `open_blocking` really does read zero. It is refused anyway:

```
MAINLINE: merge refused by mainline.fn_permit_merge_gate —
re-derived open obligation count is 1 while the projected counter reads zero
```

**This is the claim the product actually rests on.** The gate does not trust the column it
guards. It recounts from the obligation rows and refuses on the disagreement itself. An
attacker who owns the counter does not own the gate.

Honest note, carried in the payload rather than hidden: beat 3's refusal has
`naa: null`, `naa_reason: not_computable`, `diagnosis: none`, and its MUS is a
`capability_gap` — *"outside the declarative decomposition; the general algorithm is QuickXplain
over savepoint probes, in a separate transaction and never on the completion path."* The system
refuses correctly **and** reports that it cannot compute a nearest-admissible answer for this
class. It does not manufacture one.

**Beat 4 — admission.** One disposition of kind `applied` is signed against the obligation.
`open_blocking_after_signature 0`. Merge record: `permit_state merged`,
`permit_open_blocking 0`, `permit_head_seq 3`, `gate_epoch 1`,
`merged_commit 4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa`.

**The signer is shown a fixed vocabulary and must pick from it.** Obligation `0007` offers
three defeaters, all pinned to `vocab_sha256
2ccb08a3d9d1f89e66267c00101fc1de18d2dda95b669eef9d71ab69c548b579`:

| code | prompt |
|---|---|
| `ENERGY_SOURCE_ABSENT` | Which stored-energy source was surveyed and found absent within this permit's boundary, and by whom? |
| `MECHANISM_PRESENT_AND_VERIFIED` | Which isolation point was locked, and who verified it at zero? |
| `WORK_NOT_INTRUSIVE` | Which task in this permit's scope was assessed as non-intrusive, and against which method statement? |

The disposition pins the **digest of the option set the signer was shown**. So *"nobody told me
those were my options"* stops being an argument and becomes a checkable claim.

What a disposition costs is not uniform. The lattice for `blood_major` at `policy_version cl-1.0`:

| kind | min signer rank | second signer | foreign org | compensating | predicate | reassert | max TTL |
|---|---|---|---|---|---|---|---|
| `applied` | 3 | no | no | no | no | no | — |
| `mitigated` | 3 | yes | no | **yes** | no | no | — |
| `escalated` | 3 | yes | no | no | no | no | — |
| `mechanism_absent` | 4 | yes | **yes** | no | **yes** | **yes** | — |
| `emergency_override` | **5** | yes | **yes** | no | no | no | **12 h** |

Claiming the mechanism does not exist costs a rank-4 signer, an outside organisation, a
predicate and a re-assertion. Claiming an emergency costs rank 5 and expires in twelve hours.
**The cost of an excuse is proportional to how much it assumes.**

### 2.6 IT ALL ROLLS BACK, AND THE PAYLOAD PROVES IT

`persisted false` · `single_transaction true` · `isolation SERIALIZABLE` ·
`disposition rolled_back` · savepoints `gate_run_beat_2`, `_3`, `_4` ·
opened and closed logical timestamp **identical**: `1786766438407444113.0000000000`.

The interesting part is *how* it proves it, because a whole-table row count cannot tell
"I persisted something" from "somebody else did":

* `identical: true` — every table the four beats can write, counted before and after, plus
  `mainline.permit`'s own columns (because the attack beat mutates a column without changing a
  count).
* `self_persisted: false` — **this run's own evidence.** Beat 4 minted
  `disposition_id 3e0db8f4-ef49-455f-8382-9e77cecef717`, a uuid4 no other writer holds.
  `minted_disposition_rows_after_rollback: 0`. It is gone.

The permit row after the run is byte-identical to before: `state dispositioned`,
`open_blocking 1`, `head_seq 2`, `merged_commit null`.

**Press it as many times as you like.** Each run mints a fresh uuid4 and destroys it.

---

## 3 · USE CASE TWO — the edit that inherits the same debt

> **In one sentence:** *Somebody proposes to rewrite the very rule the 2019 incident blamed.
> The same debt attaches to the proposal — because the debt was never attached to a form, it
> was attached to the rule.*

### 3.1 THE LEAD

Use case one is about doing work. This one is about **changing the rule itself**.

`DEMO-MOC-0001` is a management-of-change request. It proposes to edit `§7.3.2(b)` — the exact
clause version the permit in use case one relies on, and the one the 2019 investigation blamed.

Here is why that matters. In a document-workflow system, an obligation lives on a *form*: this
permit has an open action item. Close the permit and the item goes with it. Open a different
kind of record — a change request, say — and the system has no idea the two are related,
because they are different forms.

MAINLINE attaches the obligation to the **clause**. So it follows the clause into every gated
subject that touches it. A permit that relies on the rule, and a proposal to change the rule,
both inherit the same 2019 debt from the same closure. Two different kinds of subject, one
repository, one debt.

And the question each is asked is **not the same question**, which is the point of §3.3.

### 3.2 THE SUBJECT

| field | measured value |
|---|---|
| change request | `DEMO-MOC-0001` — `dec0de00-000c-4000-8000-000000000001` |
| ref / target | `refs/changes/demo-0001` → `refs/heads/main` |
| state | `checks_materialised` |
| gate epoch / head seq | `1` / `1` |
| opened | `2026-08-01T03:00:00Z` |
| counters | `open_blocking` **1**, `open_conflicts` 0, `open_residue` 0 |

Its own gate constraints — a parallel set, named for the subject kind:

| constraint | predicate | counter |
|---|---|---|
| `cr_gate_closed_when_merged` | `CHECK ((state != 'merged') OR (open_blocking = 0))` | `open_blocking` = **1** |
| `cr_conflicts_resolved_when_merged` | `CHECK ((state != 'merged') OR (open_conflicts = 0))` | `open_conflicts` = 0 |
| `cr_identity_conserved_when_merged` | `CHECK ((state != 'merged') OR (open_residue = 0))` | `open_residue` = 0 |
| `cr_merge_evidence` | `CHECK ((state != 'merged') OR (merged_commit IS NOT NULL))` | — |

**"It proposes to edit that clause" is a foreign key.** `mainline.cr_clause` carries
`(cr_id dec0de00-000c-…, clause_uuid dec0de00-0004-…, commit_id 9f12114d…, relation 'edits')`,
and `fk_cr_clause_version` names the exact `(clause_uuid, commit_id)` pair. `relation` is drawn
from `cr_clause_relation_known` — `'edits' | 'introduces' | 'retires'`.

> **Not in a read payload.** `GET /v1/change-requests/{cr_id}` returns the subject, its counters
> and its constraints — it does **not** include the `cr_clause` row. The claim above is
> supported from the seed — `verticals/mainline/db/seeds/demo/demo_world.sql`,
> `INSERT INTO mainline.cr_clause` — and not from a measured payload. It is stated here with
> its source rather than presented as something the API showed.

**The obligation is on the change request and on nothing else.** Obligation
`dec0de00-000d-4000-8000-000000000001` is seeded with `subject_kind change_request`,
`cr_id dec0de00-000c-…`, and `permit_id` **absent**. Migration 0058's
`CONSTRAINT exactly_one_subject CHECK ((permit_id IS NULL) <> (cr_id IS NULL))` is what stops
one obligation being counted twice and cleared once.

Same precursor: `precursor_event_id dec0de00-0005-…` — the 2019 incident. Same projection
story: seeded `severity 0, virulence 'routine'`, and the live disposition read returns
**`virulence: blood_major`**. Measured, not asserted.

### 3.3 THE DEFEATERS ARE DIFFERENT ON PURPOSE

Obligation `000d` offers three options, and none of them is one of the permit's:

| code | prompt |
|---|---|
| `CONTROL_PRESERVED_BY_EDIT` | Which control from the precursor's corrective set does the proposed text still require, and where in it? |
| `EDIT_OUTSIDE_BLAMED_ANCHOR` | Which anchor does this edit touch, and why is it not the one the precursor's blame reaches? |
| `PRECURSOR_ANSWERED_ELSEWHERE` | Which other clause version already carries the control DEMO-INC-0001 called for, and at which commit? |

**The two vocabularies have different digests, and that is the exhibit:**

| obligation | subject | vocab SHA-256 |
|---|---|---|
| `dec0de00-0007-…` | permit | `2ccb08a3d9d1f89e66267c00101fc1de18d2dda95b669eef9d71ab69c548b579` |
| `dec0de00-000d-…` | change request | `d9c837c25bb174d1afd6b22f9496dcb197ffa6c69e5562b8fe76e3300fea3bbe` |

This is migration 0064 working, not an inconsistency. `PRIMARY KEY (check_id, defeater_code)`:
**a code is unique within a check and meaningless outside it**, because the prompt beside it is
what gives it meaning.

The permit's obligation asks about a **job** — *was this stored energy isolated before this
work?* The change request's asks about an **edit** — *does the new text still require the
control, does it touch the blamed anchor, was the finding already answered elsewhere?*

Reusing `WORK_NOT_INTRUSIVE` on a document edit would be a code that reads plausibly and means
nothing — worse than an absent row, because it survives review.

### 3.4 THE HONEST LIMITS OF THIS USE CASE (R1)

Both are limits of the **demo surface**, not of the kernel, and neither is being worked around.

**Limit 1 — there is no merge route for a change request. It cannot be pressed.**

`POST /v1/change-requests/dec0de00-000c-…/merge` returns **404 / 664 B** (§1.1). The 404 body
declares the route table, and it contains `/v1/permits/{permit_id}/merge` with no
change-request equivalent. `GET …/blocking-checks` is **404 / 673 B** for the same reason:
the permit has that route, the change request does not.

So use case two is told from the read payload, the disposition read and the seeded rows.
**No route is staged, and no press is narrated that cannot happen.** The gate constraint
`cr_gate_closed_when_merged` is real and would refuse a merge — but *this deployment offers no
way to attempt one*, and that sentence is the honest end of the story rather than a gap to
paper over.

**Limit 2 — the console has no change-request surface.**

Measured against `verticals/mainline/apps/console/src/features/`: nine feature directories —
`ancestry`, `audit`, `custody`, `diff`, `evidence`, `gate`, `overview`, `propagation`,
`silence`. None for change requests. The resource *is* declared in `data/resources.ts`
(`change_request`, `GET /v1/change-requests/{cr_id}`, *"The second gated subject. The
repository is the protected branch; the permit is one of its refs."*) — it has a contract and a
transport, and no screen.

Use case two therefore reaches a judge through the **Diff** screen (the clause version it
proposes to edit) and through this document. That is written down here rather than hidden.

---

## 4 · CORRECTIONS TO THE PLAN, MEASURED

R10 forbids invention; it also forbids repeating a number because a planning document carried
it. Two identifiers in `docs/leads/demo-story-plan.md` §2 did not survive measurement.

### 4.1 `clearance_digest` is run-varying — do not print it as a constant

The plan §2 and the worker brief both name `clearance_digest 41b9249ac28ce0bb…`. Measured
across four gate-runs on 2026-08-15:

| run | minted `disposition_id` | `clearance_digest` |
|---|---|---|
| 1 | `e559e439-fe77-4713-936b-861cdc222d01` | `5e16e6a22cb284c333c7761a1a98381cc61986581a261a0897f04c438abcdd07` |
| 2 | `f6e57dd7-9ee2-4d55-8494-57598c953247` | `e0beb38db36c68cbfd157593b255cb54907c794b9ee36f0f4780d756c4b7d198` |
| 3 | `73cb1ea9-eb4f-4f3e-b346-f6bb8efe0803` | `3e65ddcd02a96a11a5ddf3012363f3492b8e38296bee39087d2542878ae46047` |
| 4 | `3e0db8f4-ef49-455f-8382-9e77cecef717` | `98178c9fcc80a828ce55db91b1c10a0c1f321874f922343d48cd4f3a716ae40d` |

**It varies every run, and it is supposed to.** Migration `0071_merge_record.sql:25` defines it
as *"sha256 over the sorted (obligation_id, disposition_id) set"*. The `disposition_id` is a
fresh uuid4 minted per run — the same uuid4 whose disappearance proves the rollback (§2.6).
A digest over a fresh uuid4 cannot be stable, and if it ever were, the rollback proof would be
broken.

**Consequence:** no screen, script, caption or test may assert a literal `clearance_digest`.
The checkable claims are *"64 hex characters"*, *"server-computed"*, and *"different on every
run"*. `41b9249ac28ce0bb…` is one historical run's value and must not be reproduced as a fact.

`merged_commit`, by contrast, **is** stable across all four runs
(`4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa`) and may be quoted.

### 4.2 The clause text carries a `SYNTHETIC — ` prefix

The plan §2 quotes the clause as *"Before any intrusive work, stored energy shall be
isolated…"*. The seeded `canon_text` and `raw_text` both begin `SYNTHETIC — `. The prefix is
inside the string the `canon_sha256` covers. Quoting it without the prefix quotes a different
string from the one the digest commits to, so §2.3 quotes it in full.

### 4.3 The cosignature `adverse` flag reads `true`, and split-view is still not claimed

Recorded here because it is the kind of field that invites an overclaim. All three seeded
cosignatures carry `adverse: true`, `trust_domain union_hsr`, `witness_id
witness.demo/hsr-1`. That does **not** license a split-view claim, for two measured reasons:
one cosignature over the head checkpoint, from one witness, in one trust domain — **q = 1** —
and the generated contract's own note on the field: *"A claim about legal interest, not a
cryptographic property… split-view resistance MUST NOT be claimed by any screen rendered from
this field."* See `docs/decisions/demo-use-cases.md` §3.

---

## 5 · WHAT THIS DOCUMENT DOES NOT CLAIM

* **No real-world claim.** Every subject is synthetic and labelled so in its own column values.
  No assertion is made about any actual site, permit, incident or person.
* **No claim about the change-request merge path.** It has never been exercised over HTTP on
  this deployment, because no route exists to exercise it (§3.4).
* **No claim that the demo exercises everything the kernel does.** Three capabilities are
  reachable and deliberately **not** presented as use cases: propagation, the MCP agent
  surface, and split-view resistance — which this deployment does not have and never claims.
  Each is named, measured and ruled out in `docs/decisions/demo-use-cases.md`.
* **No claim about persistence.** Every gate-run is rolled back. Nothing in §2.5 changed the
  database, and §2.6 is the proof rather than the assurance.

---

## 6 · REPRODUCING EVERY NUMBER IN THIS DOCUMENT

```sh
BASE=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
P=dec0de00-0006-4000-8000-000000000001
C=dec0de00-0004-4000-8000-000000000001
K=9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39

curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/permits/$P"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/permits/$P/blocking-checks"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/checks/dec0de00-0007-4000-8000-000000000001/disposition"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/clauses/$C/versions/$K"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/clauses/$C/ancestry"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/change-requests/dec0de00-000c-4000-8000-000000000001"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/checks/dec0de00-000d-4000-8000-000000000001/disposition"
curl -s -X POST -w '\n%{http_code} %{size_download}\n' "$BASE/v1/demo/gate-run"

# The two absences §3.4 depends on. Both MUST be 404.
curl -s -X POST -w '\n%{http_code} %{size_download}\n' "$BASE/v1/change-requests/dec0de00-000c-4000-8000-000000000001/merge"
curl -s -w '\n%{http_code} %{size_download}\n' "$BASE/v1/change-requests/dec0de00-000c-4000-8000-000000000001/blocking-checks"
```

Read-only apart from the gate-run, which rolls itself back. Byte counts drift only if the
payload changes; a changed byte count is a signal, not noise.
