<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The demo presents TWO use cases, and names three capabilities it does not present

**Decision.** The demo story is exactly two use cases — the permit that cannot merge
(`DEMO-PTW-0001`) and the change request that inherits the same debt (`DEMO-MOC-0001`).
Three further capabilities are reachable on this deployment and are **named as capabilities
rather than staged as use cases**: propagation, the MCP agent surface, and split-view
resistance. Each is ruled out below with the measurement that rules it out, not with a
judgement of taste.

**Status:** decided. Ruling §4 of `docs/leads/demo-story-plan.md`, executed and corroborated
independently below. **Owner:** W1 (demo-story wave). **Date:** 2026-08-15.
**Measured against:** the live Function URL at `2026-08-15T04:00:07Z`, branch `master`,
deploy chain 271/271, `mainline_demo` on CockroachDB CCL v26.2.5, schema fingerprint
`ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339`.

Companion documents: `verticals/mainline/demo/USE-CASES.md` (the two, in full, with the
measurement table) and `verticals/mainline/demo/FIRST-RUN.md` (the fifteen-second script).

---

## 0 · THE DISTINCTION THIS RECORD EXISTS TO FIX

The demo kept growing a fourth and fifth "use case" out of whatever returned HTTP 200. A 200 is
not a use case. It is a route that answered.

### 0.1 The three-part test

A **use case** is a claim about the product that satisfies all three:

| # | test | why it is the test |
|---|---|---|
| **T1** | **Watchable** — a stranger can drive it, or read it end to end, against this deployment | a use case nobody can reach is a brochure |
| **T2** | **Grounded** — every value behind it is a column this deployment actually carries | a payload with no database behind it demonstrates the payload, not the product |
| **T3** | **Discriminating** — a weaker system would visibly fail it | if a spreadsheet passes too, it is not evidence of anything |

Failing any one of them does not make a thing worthless or false. It makes it a **capability**
— something the platform has and this demo does not exercise — and the honest move is to
**say so in one sentence** and move on.

### 0.2 The two things that are neither

* A **claim** is a sentence that is true and not demonstrated here. Claims are allowed in prose
  and must be marked. They may not be dramatised into scenes.
* A **capability** is something the kernel can do that this deployment does not exercise. It is
  named, never populated. **Populating one is the unforgivable move** — it converts an honest
  absence into a fabricated presence, and it is exactly how a demo becomes a lie that survives
  review.

### 0.3 The boundary case that makes the test non-trivial

Use case two, `DEMO-MOC-0001`, **fails T1 and passes T2 and T3.** There is no
`POST /v1/change-requests/{cr_id}/merge` on this deployment (measured 404; the 404 body declares
the whole route table and the permit's merge route is in it, the change request's is not), and
the console has no change-request surface (nine feature directories, none for change requests).

It is nevertheless a use case, **told and not driven**, because the failure is one of *surface*
and not of *ground*: the subject, its four `cr_*` gate constraints, its `open_blocking = 1`, its
obligation and that obligation's distinct defeater vocabulary are all columns, all measured, all
200. R1 rules exactly this: *admitted as data, refused as a driven demo*, with **both limits
written into the use-case document as limits**.

The contrast with §1 below is the whole point of the test. Use case two has rows and no route.
Propagation has a route and no rows. **Only one of those can honestly be told.**

---

## 1 · PROPAGATION IS NOT A USE CASE — it is staged in full, by its own envelope

`GET /v1/lessons/dec0de00-0005-4000-8000-000000000001/propagation` → **200, 4041 bytes.**

**Fails T2 outright.** Not marginally — completely.

### 1.1 The envelope says so before anyone asks

`staged: true`, and the `staged_note` is not a hedge, it is a confession with a reproduction
recipe:

> STAGED IN FULL. `propagation.schema.json` is governed by `mainline.lesson`,
> `mainline.propagation` and `mainline.merge_conflict`, and **NONE OF THE THREE EXISTS** …
> `to_regclass` returns NULL for all three on this cluster (probe carried in
> `statement_refs`). The contract requires a lesson object with eight non-null members, so
> there is no way to answer this resource from columns at all. Every value below is
> hand-authored demonstration material with no cluster behind it, every pointer is chipped
> `staged`, and the console renders STAGED across this surface. **It is not an empty list,
> because an empty list would be the claim that there are no lessons — a different sentence,
> and a false one.**

Measured corroboration:

* `provenance` carries **5 pointers, all chipped `staged`.** Not one `db:column`.
* `statement_refs` carries the probe itself, so the absence is re-runnable:
  `SELECT to_regclass('mainline.lesson'), to_regclass('mainline.propagation'), to_regclass('mainline.merge_conflict')`.

### 1.2 Every identifier in the payload is a hash of its own label

`reads.py:2118-2126` derives them from a fixed namespace:

```python
_STAGE_NS = uuid.UUID("6f3f4f8e-2b52-5c8b-9a5a-2f6f9a4f1c00")
_staged_uuid(label)   = uuid5(_STAGE_NS, f"mainline-demo-api/propagation/{label}")
_staged_digest(label) = sha256(f"mainline-demo-api/propagation/{label}").hexdigest()
```

Recomputed against the live payload on 2026-08-15 — three of three exact:

| payload member | recomputed from its label | matches |
|---|---|---|
| `lesson.patch_digest` | `sha256("mainline-demo-api/propagation/patch")` = `7b4ca7940b3edcaa95a2e215d4d7384b3ed14d75bff1505694299535cd7034f4` | **yes** |
| `lesson.merge_base` | `sha256("…/merge-base")` = `1d73e5332bd8f5a0704d7010494a1ed79add1c0db8dc51009458e3ae6e30eb9a` | **yes** |
| `lesson.anchor_event` | `uuid5(NS, "…/anchor-event")` = `5b663678-8514-588f-bba4-233e33a522b4` | **yes** |

The source comment states the ceiling exactly, and it is the right ceiling:

> That is the most a fabricated payload can honestly offer: **not evidence, but
> reproducibility.**

A digest of the string `"patch"` is not a commitment to a patch. It commits to the word.

### 1.3 A second reason, found while measuring

The staged payload reuses `dec0de00-0005-4000-8000-000000000001` — the identifier of the
**2019 incident `DEMO-INC-0001`**, *"SYNTHETIC — Stored energy release during intrusive work"* —
as its `lesson_id`, then titles that lesson *"Verify at zero before guard removal — strengthened
after INC-2024-0117"*. Same identifier, different subject, different year, different incident
reference.

Harmless while the surface is badged STAGED and nobody narrates it. **Actively misleading the
moment somebody tells it as a story next to use case one**, because a listener would reasonably
conclude the 2019 incident propagated to a fleet — which no row in this database says.

### 1.4 Ruling

Propagation **may** be linked from the landing under a STAGED label, and its screen renders as
it does today. It **may not** be narrated, demonstrated, put in the fifteen-second script, or
described as something the platform did. No table is created and no row is invented to promote
it. If the three tables are ever built, this ruling is revisited on the evidence, not amended by
preference.

---

## 2 · THE MCP AGENT SURFACE IS NOT A USE CASE — nothing has happened on it

**Fails T1 and T2.** There is nothing to watch, because no agent has called this deployment.

### 2.1 What was measured

`GET /v1/audit` → **200, 19439 bytes**, `views carried 14`, six populated:

| view | rows |
|---|---|
| `mainline_audit.v_agent_actions` | **0** |
| `mainline_audit.v_blame_coverage` | 1 |
| `mainline_audit.v_cbm_ledger` | 1 |
| `mainline_audit.v_changefeed_health` | 0 |
| `mainline_audit.v_disposition_coverage` | 1 |
| `mainline_audit.v_fixity_coverage` | 0 |
| `mainline_audit.v_gate_latency_daily` | 0 |
| `mainline_audit.v_ledger_health` | 1 |
| `mainline_audit.v_open_gate_summary` | 1 |
| `mainline_audit.v_recall_conservation` | 1 |
| `mainline_audit.v_silence_summary` | 0 |
| `mainline_audit.v_txn_restart_daily` | 0 |
| `mainline_audit.v_unused_indexes` | 0 |
| `mainline_audit.v_weakenings_without_disposition` | 0 |

The payload's `calls` array is `[]`, and `unreachable` carries one entry, quoted in full because
its precision is the point:

> `schema_name` `mainline_qa`, `outcome` **`not_probed`**, `sqlstate` `null` —
> *"not probed by the demo API: it connects as the demo's own read role, not as the Managed-MCP
> service account, so a refusal here would answer a different question than the one this field
> asks"*

That is the distinction that matters. The API did not try and fail; **it declined to run a probe
whose result would be misread.** A refusal from the wrong role would look like evidence about
the MCP surface and would be evidence about the demo's own grants.

### 2.2 Why this is honest emptiness and not a gap

`v_agent_actions` is empty for a reason with no defect in it: no MCP agent has called this
deployment. The view exists, is reachable, and correctly reports zero. Zero is the true answer.

It is also **first in alphabetical order**, which is why the audit screen appeared entirely
empty in the founder's screenshot — the first view a reader met was the one honest zero, ahead
of all six populated views.

### 2.3 Ruling

`v_agent_actions` **stays visible, stays empty, and keeps its sentence.** The audit screen
leads with views that carry rows and states *n of 14 views carried rows* in its header — an
ordering and a lead line, and nothing else.

**No agent-call row is invented. No view is hidden.** Hiding the empty view would be the same
lie as populating it, told by omission: a reader would conclude the demo exercises an agent
surface it does not.

---

## 3 · SPLIT-VIEW RESISTANCE IS NOT A USE CASE — and must not be claimed at all

**Fails T3, and is forbidden outright by the contract that carries the field.** This is the
strongest of the three rulings, because here the risk is not a boring screen but a **false
security claim**.

### 3.1 What was measured

`GET /v1/ledger?site_code=dec0de00-0001-4000-8000-000000000001` → **200, 10751 bytes**:
three checkpoints (`tree_size` 1, 2, 4) and three cosignatures, one over each.

| tree_size | witness_id | trust_domain | adverse |
|---|---|---|---|
| 1 | `witness.demo/hsr-1` | `union_hsr` | `true` |
| 2 | `witness.demo/hsr-1` | `union_hsr` | `true` |
| 4 | `witness.demo/hsr-1` | `union_hsr` | `true` |

Over the head checkpoint (`tree_size = 4`): **one** cosignature, **one** witness, **one** trust
domain. By `quorumShape` in `src/features/custody/model.ts`, that is **q = 1**.

### 3.2 The trap, and why it is recorded here

`adverse` reads **`true`**, which looks like the precondition being met. It is not, and the
generated contract says so on the field itself
(`src/data/types.generated.ts`, `LedgerCosignature.adverse`):

> A claim about legal interest, **not a cryptographic property**. With q=1 over our own
> infrastructure the verdict is PASS(not-adverse), and **split-view resistance MUST NOT be
> claimed by any screen rendered from this field.**

Two independent reasons it cannot be claimed, either sufficient:

1. **Structural.** Split-view resistance is not obtainable from one witness — it requires two
   or more mutually distrusting parties who would each notice being shown a different log.
   There is one witness here, and it is the demo's own (`witness.demo/hsr-1`). One party
   cannot disagree with itself.
2. **Semantic.** `adverse` records a claim about *legal interest*. Setting a boolean does not
   make a counterparty adversarial, and a cryptographic property cannot be conjured by a column
   asserting one.

### 3.3 The sentence that already exists, and stays

`src/verify/ledger.ts` exports it as a constant so that softening it is a visible diff in a file
whose whole subject is not overclaiming, and `custody.spec.ts` asserts the rendered text against
that string:

> **Until an adverse witness runs the cosigning service the quorum is q=1 and split-view
> resistance is NOT claimed.**

`model.ts` fixes the only condition under which any surface may raise the topic at all —
`adversePresent`, *"and even then only to say that the precondition is now met."*

### 3.4 Ruling

The sentence stays **exactly as written**. Split-view resistance is never claimed — not by a
screen, not by a caption, not by a shot list. Nobody seeds a second witness to make a stronger sentence
renderable — a second synthetic witness controlled by the same operator is the same q=1 wearing
a second name, and would convert an honest limit into a fabricated assurance.

**This is the one item on the list where a demo shortcut would be a security claim, and it is
the one to be most careful about.**

---

## 4 · WHAT THIS RULES, IN ONE TABLE

| subject | T1 watchable | T2 grounded | T3 discriminating | verdict |
|---|---|---|---|---|
| permit `DEMO-PTW-0001` | **yes** — `POST /v1/demo/gate-run`, four beats | **yes** — every value a column | **yes** — beat 3 refuses a *satisfied* CHECK | **USE CASE ONE** |
| change request `DEMO-MOC-0001` | **no** — no merge route, no console surface | **yes** | **yes** — a second subject kind inherits one clause's debt | **USE CASE TWO — told, not driven** (R1) |
| propagation | yes (a route answers) | **NO** — three tables absent, all pointers `staged` | no | capability — **named, linked STAGED, never narrated** |
| MCP agent surface | **NO** — nothing has happened | n/a — zero is the true answer | n/a | capability — **named, view stays visible and empty** |
| split-view resistance | n/a | q = 1 | **NO** — and contractually forbidden | limit — **stated verbatim, never claimed** |

---

## 5 · A CORRECTION THIS WAVE OWES THE PLAN

`docs/leads/demo-story-plan.md` §2 names `clearance_digest 41b9249ac28ce0bb…` as a value to
show. **It is run-varying and must never be printed as a constant.**

Measured across four gate-runs on 2026-08-15, four different digests. Migration
`0071_merge_record.sql:25` defines it as *"sha256 over the sorted (obligation_id,
disposition_id) set"*, and the `disposition_id` is a fresh uuid4 minted per run — the same uuid4
whose disappearance after rollback is the proof that nothing persisted.

**It cannot be stable, and if it ever became stable the rollback proof would be broken.** The
checkable claims are *64 hex characters*, *server-computed*, and *different every run*.

By contrast `merged_commit` was identical across all four runs
(`4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa`) and may be quoted.

No test, caption, shot list or screen asserts a literal `clearance_digest`. Full measurement in
`verticals/mainline/demo/USE-CASES.md` §4.1.

---

## 6 · WHAT WOULD CHANGE THIS RECORD

Stated so a later reader can reopen it on evidence rather than preference:

* **Propagation** becomes eligible when `mainline.lesson`, `mainline.propagation` and
  `mainline.merge_conflict` exist and the payload's provenance carries `db:column` pointers
  instead of `staged` ones. Re-run the `to_regclass` probe the envelope already carries.
* **The MCP agent surface** becomes eligible when a real agent call has been made against a
  deployment and `v_agent_actions` carries a row **that the call produced**. A seeded row does
  not qualify, and would be the fabrication this record exists to prevent.
* **Split-view resistance**, which is not claimed today, becomes eligible when a genuinely
  adverse witness — a party with its own legal interest, not a second key held by the same
  operator — cosigns the head checkpoint, making `q ≥ 2` over distinct trust domains. Even then
  the first honest sentence is only *"the precondition is now met."*
* **Use case two becomes drivable** if `POST /v1/change-requests/{cr_id}/merge` is implemented
  in the kernel and a console surface reads it. Until both exist, §3.4 of `USE-CASES.md` states
  the two limits and nothing is staged to simulate them.
