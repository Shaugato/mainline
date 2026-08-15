<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# FIRST RUN — the fifteen seconds a stranger spends before they decide

**Owner:** W1 (demo-story wave) · **Date:** 2026-08-15
**Target:** <https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws>
**Measured at:** `2026-08-15T04:00:07Z` · **Authority:** `docs/leads/demo-story-plan.md` §5, R2, R9, R11.
**Companion:** `verticals/mainline/demo/USE-CASES.md` — every identifier below is measured there.

---

## 0 · THE ONE DECISION THIS DOCUMENT MAKES

**The first control a judge presses is `RUN ALL`. It is not `MERGE`.**

`MERGE` shows one refusal. On its own, a refusal is indistinguishable from a system that is
merely strict, or broken, or badly configured — and a stranger has no way to tell which. The
interesting claim is not *"it refused"*. It is:

> it refused · it refused **again** when the counter it checks was forged · it **admitted**
> when the debt was properly answered · and none of it persisted.

That is four beats, and they only mean something **together**. `RUN ALL` is the control that
tells the whole argument in one exchange.

It is also what the kernel already forces. All four beats arrive in **one** already-rolled-back
SERIALIZABLE transaction (`single_transaction: true`, `disposition: rolled_back`, identical
opened and closed logical timestamps). Revealing them one at a time is a **reading aid over one
completed transaction**, and the panel says so in a sentence (R11). The demo should embrace the
discipline the transaction already imposes rather than fight it.

**`MERGE` remains reachable and is never removed.** A judge who wants to press exactly one
thing and see exactly one refusal must still be able to.

---

## 1 · THE SCRIPT

### Second 0–3 · Landing

A judge opens the bare URL with no hash. They land on the **overview**, not on the gate.

The gate is the headline screen and it must **not** be the landing, because it renders the gate
of ONE subject and — correctly, by its own doctrine — does not choose one for you. A bare URL
carries no `?permit=`, so landing there greets a stranger with *"NO SUBJECT ADDRESSED — address
a permit by its identifier `#/gate?permit=<uuid>`"*: an instruction to type a UUID they do not
have, on the headline screen, in the first three seconds. That was measured on the live URL and
it is the defect this document exists to close.

Two ways to fix it; only one is honest. Giving the gate a default permit would delete the rule
that makes it trustworthy — *a screen that picks a subject for you is a screen that can pick the
flattering one*. **The rule stays verbatim and the landing moves.**

What the landing must carry, and nothing more:

1. **One headline** — what this system refuses, and why that is hard.
2. **One orientation line** — *two gated subjects, one 2019 incident, one database that
   recounts.*
3. **One unmissable primary control** — below.

The honesty strip above it already reads `TRANSPORT LIVE` and its build id.

### Second 3–6 · The one control

> ### ▸ RUN THE GATE
> `#/gate?permit=dec0de00-0006-4000-8000-000000000001`

One primary control, visually unmissable, landing on the gate **already addressed**, with the
driver in view and `RUN ALL` primed. The judge presses `RUN ALL`.

Nothing else on the landing competes with it. Secondary doors are present but quiet.

### Second 6–15 · Four beats

| # | what lands | the reading |
|---|---|---|
| 1 | `read` · `00000` | the permit, and the one obligation still open on it |
| 2 | **REFUSED** · `23514` · `gate_closed_when_issued` · **reported** | a 2019 incident blamed the rule this permit relies on, and nobody has answered for it |
| 3 | **REFUSED** · `P0001` · `mainline.fn_permit_merge_gate` · *parsed* | the counter was forced to zero out of band. It refused anyway — it recounts |
| 4 | `admitted` · `00000` | one signed disposition, and it merges. A gate that always refuses is broken, not safe |

**Beat 2 must land loudly, in the screen's own refusal band** — the constraint, the SQLSTATE,
the `constraint_source`, the one obligation in the minimal unsatisfiable subset, and the
payload's own answer to *what would fix this*: **"disposing of exactly those restores
admissibility."** A refusal that says what would fix it is the difference between a gate and a
wall.

**Beat 3 is the beat that wins the argument.** Beat 2 alone shows a constraint doing its job —
any database can do that. Beat 3 shows the constraint being *satisfied by an attacker* and the
merge being refused anyway, because the gate re-derives the count instead of trusting the
column it guards. If a judge takes one thing away, this is it.

**Beat 3's diagnosis is weaker than beat 2's, and must look weaker.** Its `constraint_source` is
`parsed`, its `naa` is `null` with `naa_reason: not_computable`. A parsed exhibit must never be
rendered as though it were a reported one.

**Timing.** Each reveal step is CSS-only and ≤ 160 ms; `prefers-reduced-motion` renders all four
at once. The per-beat `elapsed_ms` shown is **the payload's own number**, never the reveal
delay. The resting state after the sequence is the complete panel, so a screenshot taken at any
moment is a truthful screenshot.

### After · Three addressed doors

Each already measured at HTTP 200 (`USE-CASES.md` §1). Each carries its subject in the URL — a
judge never types a UUID.

| the words on the door | where it goes |
|---|---|
| **where the blame comes from** | `#/diff?clause=dec0de00-0004-4000-8000-000000000001&commit=9f12114dc1a94f43ffe3eaae9f95b861efa7a6a88d7a9d90b1196aa06cd49a39` |
| **what the log can prove** | `#/custody?site=dec0de00-0001-4000-8000-000000000001` |
| **what the recall did not show you** | `#/silence?permit=dec0de00-0006-4000-8000-000000000001` |

The link grammar is not invented here. It is pinned in `src/app/subjects.ts`
(`SUBJECT_SLOTS`), whose test asserts each parameter name against the constant exported by the
feature that reads it — so a surface that renames its parameter produces a red test rather than
a link that looks addressed and is not. `diff` takes `clause` **and** `commit` together or not
at all: *a clause with no commit addresses no version.*

---

## 2 · WHAT A JUDGE WILL SEE THAT IS RED, AND WHAT TO SAY

Do not let these ambush the demo. Each is true, each is stated on its own screen, and **none of
them is fixed by making a screen quieter.**

### 2.1 Custody reports `verification FAILED`, and that is the verifier working

The ledger read at the seeded site carries **three** checkpoints — `tree_size` 1, 2 and 4. The
`tree_size = 1` checkpoint is **superseded seed state still resident in the cloud**: the current
seed writes only `tree_size` 2 and 4, and it is `ON CONFLICT DO NOTHING` / `WHERE NOT EXISTS`
throughout, so it never deletes what an earlier version wrote.

Checks 2 (`inclusion_proof`) and 3 (`consistency_proof_every_pair`) disagree on exactly that
row and agree on every other path. **The verifier is right and the row is wrong.**

The honest fix is at the **row**, never at the check: delete the superseded checkpoint and its
cosignature. No check is weakened, skipped or exempted. Until that reconciliation is applied,
the screen must name *which* checkpoint failed and why, rather than showing a bare
`verification FAILED`.

**If asked, say:** *"That is a stale row from an earlier seed, and the verifier caught it. We
fixed it by deleting the row, not by relaxing the check."*

### 2.2 Check 4 `log_signature` fails, and it is stated rather than fixed

*"A checkpoint note has no empty line, so it has no signature section."* The seeded note is
`mainline/<site>\n<size>\n<root>\n` with no signature block. This is a true fact about a
synthetic corpus. It belongs in `DEMO-HONESTY.md` §3 STAGED. **Nobody forges a signature.**

### 2.3 Split-view resistance is NOT claimed, and the screen says so first

*"Until an adverse witness runs the cosigning service the quorum is q=1 and split-view
resistance is NOT claimed."* That sentence is a constant in `src/verify/ledger.ts`
(`SPLIT_VIEW_LIMIT`), rendered literally, asserted by the custody spec against that string —
so softening it is a diff in a file whose whole subject is not overclaiming. It stays exactly
as written. See `docs/decisions/demo-use-cases.md` §3.

### 2.4 Eight of fourteen audit views carry no rows

Measured: **14 views carried, 6 populated.** The eight empty ones are honestly empty.
`v_agent_actions` is empty because no MCP agent has called this deployment, and it is first in
alphabetical order — which is why the screen must lead with views that carry rows and state
*n of 14 views carried rows*. **No view is hidden and no agent-call row is invented.**

### 2.5 Propagation is badged STAGED, in full

`GET /v1/lessons/…/propagation` returns 200, and its envelope declares `staged: true` with a
note explaining that the three tables behind it do not exist on this cluster. It may be linked
under a STAGED label. **It may not be narrated as a use case.** See
`docs/decisions/demo-use-cases.md` §1.

### 2.6 Silence is badged STAGED for exactly one sentence

Narrower than propagation, and worth saying precisely because the badge alone overstates it.
Every value in the silence receipt is a column of `mainline_meas.silence_receipt` **except**
`receipt.bound.statement`, the bounding sentence the contract requires on every exhibit, which
is reproduced verbatim from spec. *"PER proves exhaustion of the retrieval that ran, not of the
corpus."*

---

## 3 · THE DEPENDENCY THIS SCRIPT HAS ON THE PENDING DEPLOY

**Measured, and it matters for the first three seconds.**

The console's addressed navigation resolves its subjects from `GET /v1/demo/subjects` —
`src/data/demo-subjects.ts` reads it, `src/app/subjects.ts` distributes the members into query
parameters. There is deliberately **no identifier literal** in either file: the console asks the
kernel which subjects this database carries rather than carrying a guess.

**On the deployment as it stands today, that route returns 404.**

```
GET /v1/demo/subjects   →  404   (measured 2026-08-15T04:00Z)
```

The route exists in the API source (`app.py`, the eighteenth route). The deployed Lambda
declares **16** of the source's 17 distinct paths in its own 404 body, and
`/v1/demo/subjects` is the one missing — the deployed build predates it.

**Consequences, stated rather than worked around:**

* The degradation path is already correct and already written: `subjectParamsFor` returns `[]`,
  every nav link falls back to its bare path, and each surface renders its own named absence
  carrying the emitter's reason. Nothing crashes and nothing lies.
* But bare paths are exactly the defect this document closes. **The console and the API must
  ship in the same deploy** — a console from this tree against the currently deployed API
  yields unaddressed doors.
* **The explicit deep links in §1 are immune.** An explicit query parameter always wins over
  the resolved index (`src/app/subjects.ts` fixes that precedence in one place). Every link in
  this document carries its identifier literally, so a judge handed one of these URLs reaches an
  addressed screen whether or not the index resolved.

**Fallback if the deploy has not landed:** open the addressed gate link from §1 directly. It is
measured at HTTP 200 and does not depend on `/v1/demo/subjects` at all.

*Deploying is the orchestrator's action, not this wave's. This section is a measurement and a
handover note, not an instruction to deploy.*

---

## 4 · THE TWO READERS (R9)

Every screen on this path carries two layers **in one column**, never a toggle that hides a
claim.

* **The lead** — plain language, above the fold, no acronym before it is earned.
  *"The database refused this merge. Here is the one unanswered thing that caused it."*
* **The exhibit** — everything that is on the screen today, verbatim and unmoved in meaning:
  SQLSTATE, constraint predicate, provenance chip, canon digest, the RFC 8785 / RFC 6962 /
  ECDSA P-256 paragraph, the recomputation tables.

The RFC paragraph does not go away. **It moves down.** A `SHOW THE ARITHMETIC` affordance may
collapse an exhibit only if the collapsed state still names what is inside it and the expanded
state is the print and screenshot default.

**The test, and it is not subjective:** a reader who knows nothing understands the first
paragraph; a reader who knows everything finds nothing missing further down. If a rewrite makes
a claim vaguer, weaker or less checkable, it is wrong.

---

## 5 · DONE

A stranger who has never heard of MAINLINE opens the bare URL, presses **one** control within
fifteen seconds, watches a database refuse a merge twice — once on ancestry, once under a forged
counter — admit it on a signature, and can then click through to the blame that caused it and
the log that can prove it, **without typing a UUID and without meeting a 404 or an unnamed red
tick.**

Every number they see is one the database emitted. Nothing on the path was invented to make it
work.
