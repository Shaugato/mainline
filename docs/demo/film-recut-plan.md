<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes forbidden sentences beside sanctioned ones so the founder can see which is
which. It therefore carries the `prose-hygiene: register` marker in the same form
docs/demo/research/r6-honesty.md, docs/submission/MUST-NOT-CLAIM.md and
docs/demo/film/VO-CLOSE.md use. Every quoted offence sits on a line carrying an explicit
negation marker (`MUST NOT SAY:`), which the scanner's documented negation exemption reads as
stating the rule rather than committing it.
-->

# FILM RE-CUT PLAN — two use cases inside 2:52

**Film re-cut lead** · 2026-08-16 · repo `D:/CoackroachDBxAWS/mainline`, master, HEAD `240cff1`
· live origin `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

Binding: `docs/demo/film/BEATS.yaml` (spine), `docs/demo/research/r6-honesty.md` (register),
`docs/submission/MUST-NOT-CLAIM.md` (standing register, precedence), `docs/HONESTY.md`.

No commit id is written here. `claim_hygiene.py`'s `HYG-sha-literal` rule fires on tree hashes
in headers and the rule is right: a commit id cannot be chosen in advance, so none is written
or spoken anywhere in this wave.

---

## 0 · THE VERDICT, FIRST

> ## PROCEED — CONDITIONALLY. And the close compression is not optional; it is a defect fix.

Three findings decide this, and two of them were not in my brief.

1. **The committed film is 180 s today, which `BEATS.yaml` itself calls a disqualified cut.**
   Not 2:58. See §1.1. This is true whatever happens to use case two.
2. **The 24 s use case two needs is genuinely free.** It comes out of close *dwell* and out of
   the one segment the film's own pre-committed cut ladder already ranks first for removal. Use
   case one is not shortened by a single second. See §2.
3. **Use case two cannot be shot today, and it needs two pieces of software, not one.** The
   merge route is absent *and* the console's approve control is hard-disabled in the shipped
   bundle. See §1.4. This is the condition.

The honest answer to the question the brief asked me to be willing to give — *does the second
case fit without hurting the first?* — is **yes, it fits, and it does not hurt the first.** But
it is contingent on work I do not own, and §6 specifies the fallback in full so that a NO-GO on
that work costs the film nothing and still leaves it legal.

---

## 1 · WHAT I MEASURED, BEFORE PLANNING ANYTHING

Everything in this section is a reading taken today against the live origin or against the tree.
Nothing is taken from the brief's description.

### 1.1 · The film is at the ceiling, and nobody noticed

`VO-DEMO.md` was edited today at 09:37 to insert **`B0b · WHY IT MATTERS`, 8 s at `[0:12]`**, at
the founder's direction, for the public-YouTube audience. It is a good beat and it stays.

**The insert propagated to nothing.** Measured across the committed tree:

| file | state |
|---|---|
| `VO-DEMO.md` | has `B0b`; **but B2..B8 still carry the pre-insert timecodes** — `B1 [0:20]` runs 10 s and the next header reads `B2 [0:22]` |
| `VO-DEMO.md` §2 arithmetic table | omits `B0b` entirely; still totals **120 s / 225 words** |
| `BEATS.yaml` | **no `b0b` beat at all**; `demo_s: 120`, `total_s: 172` |
| `CLICKS.md` §5 | titled *"THE NINE BEATS"*; `B0 0:00→0:12`, `B1 0:12→0:22` — pre-insert throughout |
| `ONSCREEN-TEXT.yaml` | `beats:` list runs `b0, b1, b2 …` — no `b0b` |
| `VO-CLOSE.md` | close still in-points at `2:00` |

**The true running time of the committed film:**

```
B0 12 + B0b 8 + B1 10 + B2 14 + B3 18 + B4 10 + B5 16 + B6 18 + B7 12 + B8 10  = 128 s (2:08)
close                                                                          =  50 s
end card                                                                       =   2 s
                                                                          TOTAL = 180 s (3:00)
```

`BEATS.yaml`'s own `budget` block says: `ceiling_s: 180 # The contest rule. A 180 s cut is a
disqualified cut; never approach it.` **The film as committed is sitting exactly on it.** The
founder's "2:58" is 2:08 + 50 and does not count the 2 s end card.

**This is the strongest argument for the re-cut and it has nothing to do with use case two.**
Even under a NO-GO, W1 and W3 must land.

### 1.2 · Two more committed timings that are now false

* **`BEATS.yaml: first_refusal_at_s: 22`.** With `B0b`, the click lands at `0:20` and the
  refusal is visible at `0:30`, not `0:22`. `VO-DEMO.md`'s `B0b` note claims the *click* is
  still inside the organiser's 20–30 s window — true of the click, and the file says click.
  `BEATS.yaml` says *refusal*, and 30 is the outer edge.
  **RULING R-1 · authority: the organiser's own wording, quoted at `SPINE.md` §1.3.** Correct
  the field to `30` and record beside it that live product is on screen from frame one, which
  is what the organiser's tip actually asks for. **Do not** buy the seconds back by executing
  the old ladder's rank-2 (`b0 12→8`): B0 carries 19 fixed, verbatim words, and 19 words in 8 s
  is 2.4 w/s, over every rate ceiling in the kit. The old rank-2 cuts picture out from under
  words that span it and is arithmetically unexecutable as written. It is removed in §4.
* **`VO-DEMO.md` §2** states *"213 words ÷ 112.1 s"* and *"120 s"*. With `B0b`'s 28 words the
  demo is **241 words over 128 s**. The table must be rebuilt, not patched.

### 1.3 · The route table, re-measured today

`GET`/`POST` against the live origin, verbatim outcomes:

```
GET  /v1/health                                             200   ok:true · 271/271 · v26.2.5
GET  /v1/demo/subjects                                      200   cr_id · state checks_materialised
GET  /v1/change-requests/dec0de00-000c-…-000000000001        200   3,295 B
GET  /v1/checks/dec0de00-000d-…-000000000001/disposition     200   3,850 B
GET  /v1/change-requests/{cr_id}/checks                      404
GET  /v1/change-requests/{cr_id}/blocking-checks             404
GET  /v1/change-requests/{cr_id}/merge                       404
POST /v1/change-requests/{cr_id}/merge                       404
POST /v1/demo/gate-run                                       200   verdict PROVEN · persisted false
```

17 routes declared, exactly as briefed. **The brief's measurement is confirmed in every
particular.** Two details it did not carry, both of which matter:

* `GET /v1/change-requests/{cr_id}` **already returns all four `cr_*` constraints with their
  predicates and live counters** — `cr_gate_closed_when_merged` with
  `CHECK (((state != 'merged') OR (open_blocking = 0)))` and `open_blocking: 1`. The refusal's
  *grounds* are already public and already renderable. Only the *attempt* is missing.
* The obligation at `/v1/checks/dec0de00-000d-…/disposition` returns **three defeater prompts
  under one `vocab_sha256`** (`d9c837c2…`) and a `blood_major` lattice whose
  `emergency_override` row requires `min_signer_rank 5`, `req_foreign_org true`,
  `req_second_signer true`, `max_ttl_hours 12`. That is a *different* vocabulary from the
  permit's, generated for a different act, and it is the single best asset use case two has.

### 1.4 · THE FINDING THAT CHANGES THE SHAPE OF THE WAVE

**`docs/demo/research/r6-honesty.md` §A13.5 says there is "no console surface" for the change
request. That is out of date, and I measured it out of date.**

`GET /operator.html` now answers **200, 5,097 bytes, `sha256 37454502…`, `<title>Control of
Work`** — no longer byte-identical to `GET /` (4,749 B, `9bd68bcd…`). It loads its own entry
`assets/operator-D24tzVGh.js`, **96,734 bytes**. `CLAIMS-CLEARANCE.md`'s condition 1 — *"the
film scored in CLICKS.md has no pixels on this origin today"* — **has been closed since that
audit.** Nobody told the film documents.

That bundle already contains a complete Management-of-Change surface. Strings extracted from
the deployed asset today:

```
"Management of change"          "Proposed wording"        "Compare with clause of record"
"Approve change"                "moc-proposed-text"       "Authorization requirements for the proposed change"
"Merged commit"                 "cow-clause-text"         "The technical basis for the proposed change"
"type the proposed wording"     "moc-source-of-change"    "Impact of change on safety and health"
```

**And two things in it are decisive.**

1. **The approve control is hard-disabled in the shipped bytes.** The constructor reads
   `o.disabled=!0; o.setAttribute("aria-disabled","true")` and it never becomes enabled — there
   is no CR merge call anywhere in the bundle. It renders a reason instead:
   `` `Cannot approve. ${openBlocking} blocking obligation is outstanding on this change
   request.` `` followed by the constraint name and predicate.
2. **The bundle calls `v1/change-requests/{}/blocking-checks`, which 404s today.** The obligation
   panel on that screen is wired to a route that does not exist. Anyone who opens the MoC screen
   on camera right now films a broken panel.

**So use case two needs two landings, not one:** the demo-safe attempt endpoint, *and* an
approve control that calls it. And the console bundle sits under a **1,325-byte** headroom
guard that fails below 1,024 — enabling a button and adding a call is not free. That measurement
belongs to whoever owns the console; **the film plan must not assume it, and §6 assumes it does
not happen.**

### 1.5 · The one thing this finding *gives* the film

`FALLBACKS.md` F-8 forbids rendering a proposed clause string: *"the table carries none, so a
plausible one would be hard-coded, and hard-coding a plausible string is the same class of act
as reshaping a seed to match a constant."* **That objection is fully answered and the answer
was already in the tree.** The console's own field is `"type the proposed wording"`, and
`CLICKS.md` §4 is titled *"THE CONVENTION A JUDGE CAN CHECK IN TWO SECONDS: TYPED CARRIES NO
CHIP"*.

**RULING R-2 · authority: `CLICKS.md` §4, the film's own standing convention.** The proposed
wording in use case two is **typed by the founder on camera, into the console's own input,
carrying no provenance chip**. It is visibly a human's proposal, never a database claim. This
is the same discipline the work-description tail in B0 already uses. F-8's prohibition is
satisfied, not waived — nothing is hard-coded and nothing is asserted by the product.

---

## 2 · THE ARITHMETIC — where 24 seconds come from, and what they cost

### 2.1 · The budget

| | s |
|---|---:|
| committed film today (§1.1) | **180** |
| close: 50 → 22 | **−28** |
| `b8` 10 → 6 — its second half is the read-only CR cut, superseded by use case two | **−4** |
| **recovered** | **−32** |
| new `b9` | **+12** |
| new `b10` | **+12** |
| **NEW TOTAL** | **172 s · 2:52** |

`172 ≤ 172` target · `172 < 174` hard stop, 2 s margin · `172 < 180` ceiling, 8 s margin —
**the exact margins `BEATS.yaml` was designed with.** 8 s of the 32 recovered is banked, not
spent.

New demo: `12 + 8 + 10 + 14 + 18 + 10 + 16 + 18 + 12 + 6 + 12 + 12 = 148 s`.
Check: `148 + 22 + 2 = 172`. ✔

### 2.2 · Why the 24 s does not come out of use case one

Every beat `b0`..`b7` is untouched. The only demo second removed is `b8` 10→6, and `b8`'s second
half is **rank 1 on the film's own pre-committed cut ladder**, whose stated reason is:

> *"it is the weakest-supported second on camera: that subject is shown read-only and told
> rather than driven."*

Use case two is precisely the removal of "told rather than driven." **The 4 s is not a cost; it
is the ladder's first choice being spent on the thing it was complaining about.** The rollback
proof — `persisted false`, `SERIALIZABLE`, the minted disposition id with zero surviving rows —
is entirely in `b8`'s first half and survives at 6 s intact.

### 2.3 · THE COST, STATED PLAINLY — the brief asked for this and here it is

The scoring is lexicographic with **Agentic Memory Design first**. Three costs, none hidden.

**COST 1 — the close loses 28 s of dwell, and `C1` is the beat that pays most.** `C1 · THE
LOOP` is the only close block whose primary axis is `agentic_memory_design`. It goes 12 s → 6 s.
Content is preserved to the character (§3); what is lost is the *time a judge has to sit with
STORE / RETRIEVE / ACT before the next card arrives*. This is a real axis-1 loss and it is the
sharpest thing in this plan.

**COST 2 — the criterion rail can no longer build one line per block.** Today four rail lines
fade in at `2:00 / 2:16 / 2:32 / 2:42`, each answering the criterion the block under it serves.
Across 22 s and three cards, four staggered lines are unreadable. **RULING R-3 · authority:
`VO-CLOSE.md` §0.3, which already designs the rail to lift into the final block complete.** The
rail arrives **whole, in the final card**. The cost is that a judge no longer sees each
criterion answered *beside* the block answering it — the answers are all there, the adjacency
is gone.

**COST 3 — the second case ends on a refusal, with no admission to mirror `b7`.** The brief
forbids a committing route and it is right to. Use case one runs refuse → answer → **admit**;
use case two runs refuse → *here is the question that would answer it*, and stops. A judge could
read that as *"the system just says no."* **RULING R-4 · authority: `BEATS.yaml`'s own
`b6` design, which makes the defeaters the answer rather than the merge.** `b10` must hold the
**three live defeater prompts** from `/v1/checks/dec0de00-000d-…/disposition` on screen. The way
through is shown; only the walking through it is not.

### 2.4 · Where I disagree with my own brief, and why it matters

My brief states that a second use case *"broadens Real-World Impact without deepening axis
one."* **I do not think that is right, and the difference decides whether this wave is worth
doing.**

Use case two is not a second refusal. It is the **same precursor's blame**, reaching the **same
clause `dec0de00-0004-…`**, arriving at a **different subject kind** through a **different gate
family** (`cr_*`, not `permit`), and generating a **different defeater vocabulary** for the
different act. That is a claim about how the memory is *attached* — to the clause, not to the
workflow — and *that is an axis-1 property*, not a Real-World Impact one. It is the answer to
*"what makes agentic systems different from traditional apps?"*: the constraint follows the
knowledge, and it follows it into the process that would erase it.

**But it only lands as axis-1 if it is shot as a memory beat.** Hence:

> **RULING R-5 · BINDING ON W2, W4 AND W5, AND NON-NEGOTIABLE.** The shared clause
> `dec0de00-0004-…` (label `7.3.2(b)`) **and** the shared precursor `DEMO-INC-0001` **must be
> visible in the same frame as the change-request refusal**, legible, with the same identifiers
> a judge already saw in `b3`. If those two identifiers are not in that frame, use case two is
> a second refusal, the axis-1 trade in §2.3 is a straight loss, and **the wave should be
> abandoned in favour of §6.**

---

## 3 · THE CLOSE — 50 s → 22 s, with nothing dropped

**RULING R-6 · authority: the founder's instruction, and Devpost's own wording.** Devpost asks
that the services and features be *"on screen (text overlay or slide) so judges can confirm them
quickly."* It never asks for them narrated, and `VO-CLOSE.md` §3.2 already rules that *"the
service names are not read aloud."* **The saving is taken entirely from dwell, from speech, and
from running two sequential cards in parallel. Not one service, feature, label, caveat or
concession leaves the screen.**

### 3.1 · The mechanism — three cards, and the big saving is parallelism

`C2 · AWS` (16 s) and `C3 · CockroachDB` (14 s) are both *name-the-surfaces* cards, both already
built on the same three-label discipline (`IN THIS REQUEST` / `IN THE APPLY` · `EARLIER` / `NOT
IN THIS PATH`). Running them **side by side in one card instead of one after the other** saves
their sequence, not their substance.

| new | title | dur | replaces | spoken |
|---|---|---:|---|---:|
| `k1` | THE LOOP | **6 s** | `c1` (12 s) | 10 w |
| `k2` | THE STACK — AWS ∥ CockroachDB | **10 s** | `c2` + `c3` (30 s) | 16 w |
| `k3` | THE LIMIT, THE RAIL, THE URLs | **6 s** | `c4` (8 s) | 10 w |
| | | **22 s** | | **36 w** |
| `end` | end card | 2 s | unchanged | 0 |

**36 words ÷ 22 s = 1.64 w/s — identical, to two decimals, to the current close's deliberate
1.64 w/s.** The reading pace a judge's eye needs is not compressed at all. That is the whole
proof that this is delivery and not content: *the words-per-second does not move.*

### 3.2 · What each card must carry, in full

* **`k1`** — `STORE` / `RETRIEVE` / `ACT`, each with its table and its timestamp, exactly the
  lines already cleared in `VO-CLOSE.md` §2.5. Spoken, ~10 w.
* **`k2`** — **every line of §3.1 and every line of §4.1 of `VO-CLOSE.md`, verbatim**, in two
  columns, with all three labels intact, the Bedrock `NOT IN THIS PATH` exception in its own
  boxed position, the Singapore/Sydney residency split, the three `It did not run in this
  request.` lines, and `One cluster. One region. This repository holds no load profile, and we
  do not claim scale.` Nothing is abbreviated, no evidence path is dropped.
  Spoken, ~16 w — one sentence, whose only job is to say the list has a rule and to say the
  Bedrock line out loud.
* **`k3`** — the three-line limit **on screen in full**, the complete four-line criterion rail,
  and both URLs.
  **Spoken: the first sentence only.** *"We measure deliberation and never threshold it"* moves
  from the mouth to the screen, where it already is. That is 6 spoken words saved and zero
  content lost, and it is the single cleanest trade in this plan.

### 3.3 · The two constraints on `k2` that keep it honest

1. **Highlight sweep: at most four landings in 10 s.** `VO-CLOSE.md` §4.1 already fixes the
   order — `23514` → `P0001` → the enum inside the predicate → the `It did not run in this
   request.` column. Four landings, and everything else on the card is **pause material by
   design**, which is what "confirm them quickly" means for a list this long.
2. **The grouping is the honesty and it survives at any size.** `VO-CLOSE.md` §3.1: *"a flat
   list would let 'S3' borrow the credibility of 'Lambda', and S3 was never in the request."*
   **MUST NOT SAY / MUST NOT SHOW:** a single ungrouped stack list. If the two columns will not
   fit legibly with their labels, `k2` gets 12 s and the 8 s bank in §2.1 pays for it — it does
   **not** get flattened.

---

## 4 · THE TWO NEW BLOCKS

Numbered `b9` and `b10`, appended after `b8`. **Nothing before them renumbers** — `b0`..`b8`
keep their ids; only `b8`'s `dur` changes, and the `b0b` id already in `VO-DEMO.md` is adopted
as-is by every other file rather than being renumbered into the sequence.

### 4.1 · `b9 · THE OTHER WAY IN` — 12 s, ~20 w, `axis: [agentic_memory_design, real_world_impact]`

Draft line, to be finalised by W2 against the register:

> "Fine. Then don't use the clause — change it. ·hold 0.4· Same paragraph. Same incident behind
> it. This request asks to edit it."

20 w / 12 s = **1.67 w/s**. Register check against the existing standard (*"Nobody typed that
four"*, *"Not a checkbox — a question"*): short, concrete, no uncashed jargon, no marketing
register. It answers the judge's question in the judge's own words.

**On screen:** the console's Management-of-Change screen for `DEMO-MOC-0001` — `state
checks_materialised`, the clause of record at `7.3.2(b)`, **clause `dec0de00-0004-…` and
`DEMO-INC-0001` both legible (R-5)** — and the founder **typing the proposed wording on camera**
into `moc-proposed-text`, no provenance chip on it (R-2).

### 4.2 · `b10 · REFUSED AGAIN` — 12 s, ~22 w, `axis: [agentic_memory_design, technological_implementation]`

> "Refused. Same SQLSTATE, a different constraint — this one guards the edit. ·hold 0.6· You
> can't use the clause. You can't quietly edit it away either."

22 w / 12 s = **1.83 w/s**, with a 0.6 s hold. The last sentence is the mirror the whole wave
exists for, and it is the one line in this plan that can go wrong.

> **RULING R-7 · authority: `VO-CLOSE.md` §5.3, which rules on exactly this failure for the word
> "here".** The clause **can** be edited — by disposing of the obligation first, which is what
> the three defeaters are for. The scope word **"quietly"** is doing all the work, and dropping
> it converts a true statement into a false one.
>
> **MUST NOT SAY:** *"the clause cannot be changed"* · *"the database won't let anyone edit the
> rule"* · *"the memory is immutable"* · *"you can't edit it."*
> **TRUE INSTEAD:** *"you can't **quietly** edit it away"* — or, if the adverb reads oddly on
> the day, *"not without answering the question first."*
> **W6 must file a REFUSE row against every variant that drops the scope word.**

**On screen:** the refusal, `23514`, `cr_gate_closed_when_merged`, its own predicate
`((state != 'merged') OR (open_blocking = 0))` and `open_blocking: 1` — **beside the three live
defeater prompts** from `/v1/checks/dec0de00-000d-…/disposition` with `severity 4` and the
`blood_major` lattice (R-4). Shared clause and shared precursor still in frame (R-5).

### 4.3 · Standing honesty rules re-applied to both new blocks

* **The seeded incident describes nobody. No date, no site, no job title, no injury** — spoken
  or written — in `b9` or `b10`. `demo_world.sql`'s own narrative column records that the
  precursor describes nobody; `B0b` already sets the frame with *"years ago"* and names no year.
* **`blood_major` is never spoken.** It is a column value and it appears on screen only. Saying
  it aloud edges toward inventing an injury, which is the one thing this repository has refused
  at every turn.
* **`r6-honesty.md` A3's two-incident trap.** `DEMO-INC-0001` is dated **2019** on screen, and
  the staged propagation payload reuses that same uuid while titling it *"strengthened after
  INC-2024-0117"*. **Both must never be in the same shot**, and the propagation one is never
  narrated. W4 must confirm the MoC screen does not render the propagation title.
* **A5, present tense.** **MUST NOT SAY:** *"watch it remember"* · *"the system just retrieved
  the incident and blocked the change."* The recall **already ran**; both blocks speak of it in
  the past tense, exactly as `b3` does.
* **A13.5 is superseded, not overruled.** Its `MUST NOT SAY: "watch the same debt block the
  change request"` was correct on the day it was measured and is correct *until the endpoint
  lands*. **RULING R-8 · authority: precedence — `r6-honesty.md` is a dated research record;
  `CLAIMS-CLEARANCE.md` is the film's live clearance sheet.** W6 files a **superseding
  clearance row** in `CLAIMS-CLEARANCE.md` citing the measurement that retires it. **Nobody
  edits `docs/demo/research/r6-honesty.md`** — a research record is not rewritten because the
  world moved; it is cited and superseded.

### 4.4 · Two spine constraints that must be amended, one of them carefully

* **`one_post_per_film: true` → `posts_per_film: 2`.** Ruled by necessity. Each POST is to a
  `/v1/demo/*` rolled-back endpoint, each returns its own `persisted: false` **measured by the
  endpoint from its own fingerprint, never claimed**. `b1`'s line *"One request — four beats came
  back inside it"* stays true of *that* request; the disclosure strap becomes per-request.
* **`FALLBACKS.md` F-11 — amend as a TIGHTENING, never a loosening.** F-11 today says a second
  POST row means *stop the take*; it is a fake-detection rule and its force must not be reduced
  to make room for a beat. **RULING R-9 · authority: the anti-fake rules in `CLICKS.md` §6,
  which F-11 serves.** The new form is: *exactly two mutating requests, each narrated while it
  is in flight, each visible in the panel; **any third row, or either row appearing without its
  narration, stops the take.*** That is strictly stronger than the current rule at two requests,
  because it adds a narration condition that does not exist today.

---

## 5 · THE NEW CUT LADDER

The old ladder is void: its rank 1 (`b8`'s CR cut) no longer exists, its rank 2 is
arithmetically unexecutable (§1.2), and its rank 5 targets a `c4` that no longer exists.

| rank | beat | from | to | saves | film after | what goes |
|---:|---|---:|---:|---:|---:|---|
| 1 | `b9` | 12 | 8 | 4 | 168 | the typing of the proposed wording; arrive on it composed |
| 2 | `b6` | 18 | 14 | 4 | 164 | one of the three permit defeaters (two carry the point) |
| 3 | `b7` | 12 | 9 | 3 | 161 | the dwell on the post-merge fields |
| 4 | `k3` | 6 | 4 | 2 | 159 | the spoken limit; the screen keeps all three lines |
| 5 | `b10` | 12 | 8 | 4 | 155 | the hold after the mirror line |

`never_cut: [b3, b5]` — unchanged. Floor **155 s**.

> **RULING R-10 · USE CASE TWO IS ATOMIC.** No step may take `b10` below 8 s, and **`b9` may
> never be cut without `b10`.** A setup with no answer is worse than neither: it spends 8–12 s
> raising the judge's question and never answers it. If the cut must go past rank 5, **drop
> `b9` and `b10` together (24 s) and restore `b8` to 10 s** — net −20 s, film 152 s, and the
> film is back to one clean use case rather than one and a half.

---

## 6 · THE NO-GO PATH — fully specified, and it is a legitimate outcome

**Decision gate.** Before W2, W4 and W5 commit their new-block material, one measurement decides
it, and it is a measurement, not a promise:

```
POST <the demo-safe CR attempt endpoint>        → 200, persisted:false measured from a fingerprint
GET  /v1/change-requests/{cr_id}/blocking-checks → 200
GET  /operator.html  → the approve control is enabled and calls that endpoint
```

**If all three do not hold, use case two is NO-GO, and that is not a failure of this plan.**

Under NO-GO:

* **W1 and W3 land anyway, in full.** They are the defect fix. `b9`/`b10` are simply never added;
  `b8` is **restored to 10 s** and keeps its read-only CR cut.
* **Film total: `128 + 22 + 2 = 152 s · 2:32`** — 28 s under the ceiling, comfortably legal, and
  every service and feature still named.
* **`b8`'s read-only CR moment is *strengthened*, not merely kept.** §1.4's finding means the
  MoC screen genuinely exists now, and the disabled approve control renders **the constraint
  name and predicate as its own reason** — better than the read-only cut F-8 was written for.
  W6 updates F-8's `SAY:` block accordingly, keeping its `MUST NOT SAY` intact.
* **The `blocking-checks` 404 must still be handled**, because it breaks a panel on that screen
  today. If the route has not landed, the MoC screen is filmed **only** in the state that
  renders clean, or not at all.
* **W6's `SAY:` line for the judge's live question is the mitigation** — *"there is no merge
  route for it yet, so I'm telling you about it rather than driving it"* — which is already
  written, already cleared, and remains true.

**Do not treat NO-GO as a reason to build a committing route, to enable the approve button
without the demo-safe endpoint behind it, or to grant `mainline_api` any write it does not hold
today.** The standing `transitions.materialise_checks` INSERT-without-privilege finding stays
open and is not this wave's to close. `transitions._demo_guard`'s `423 Locked` stays.

---

## 7 · THE SIX WORKERS — disjoint paths, literally enumerated

| worker | owns, exclusively |
|---|---|
| **W1 · spine and timing** | `docs/demo/film/BEATS.yaml` · `docs/demo/film/SPINE.md` |
| **W2 · demo VO and the two new blocks** | `docs/demo/film/VO-DEMO.md` |
| **W3 · close compression** | `docs/demo/film/VO-CLOSE.md` |
| **W4 · on-screen text** | `docs/demo/film/ONSCREEN-TEXT.yaml` |
| **W5 · shoot choreography** | `docs/demo/film/CLICKS.md` |
| **W6 · fallbacks and clearance** | `docs/demo/film/FALLBACKS.md` · `docs/demo/film/CLAIMS-CLEARANCE.md` |

No path appears twice. **W1 lands first and everyone else inherits its numbers**; `BEATS.yaml`
is the timing authority and a worker whose document disagrees with it is wrong.

---

## 8 · RULES BINDING EVERY WORKER, WITHOUT EXCEPTION

1. **NEVER fake a refusal, a SQLSTATE, a row, a latency, a digest or a seal.** Every value on
   screen is what the kernel returned on the run that is filmed. A staged beat violates the
   contest rule that the project *"must function as depicted in the video"*.
2. **NEVER `terraform apply`, redeploy, touch AWS, write an SSM parameter, or print a
   credential.** The orchestrator deploys. `GET`/`POST` against the public origin is the only
   contact with anything deployed.
3. **NEVER regress what works.** Baseline **998 collected / 997 passed / 0 failed / 0 errors**;
   gate proof `PROVEN` caveat-free; `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` may not move;
   console headroom is **1,325 bytes** with a guard failing below **1,024**.
4. **Do not weaken `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion.** `continue-on-error`
   and `|| true` are banned. F-11 is amended only as the tightening in R-9.
5. **Do not commit.** Leave the tree for the orchestrator.
6. **Re-derive, never quote from a plan.** Every per-beat `elapsed_ms`, byte count, digest and
   field value comes from the run actually filmed. `clearance_digest` is different every run and
   is never printed as a constant. No 7- or 40-hex run appears on camera.
7. **The seeded incident describes nobody.** No date, no site, no job title, no injury.
8. **Timings in these documents are budgets and must be labelled as such**, exactly as
   `BEATS.yaml` already labels them. The four SQLSTATEs are the only kernel values in them.

---

## 9 · WHAT THIS PLAN DOES NOT DECIDE

* **Whether the demo-safe CR attempt endpoint gets built.** Not mine. §6 is the answer to either
  outcome.
* **Whether the console's approve control can be enabled inside 1,325 bytes of headroom.** A
  measurement for whoever owns the console; prefer the existing `operator` entry over the main
  chunk.
* **Whether `mainline_api` should be granted INSERT.** It should not, on this plan's evidence,
  and it is the founder's call regardless.
* **The final wording of every new line.** W2 and W3 draft; **W6 clears**, and W6's REFUSE is
  final.
