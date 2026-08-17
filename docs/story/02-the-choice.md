<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The choice — five finalists, three judges, one dissent

By 2 August 2026 the research had five ideas left and time to build one.

The founder threw out the scoring used until then and wrote the rules himself. Rank these
by whether each could become a company — that first. Then by whether each could win the
hackathon. Then by whether anyone had built it before. And ignore how long each would take
to build, so the answer would not depend on a calendar.

Three reviewers then scored all five, each reading through a different professional lens:
an early-stage investor choosing one company to fund, a panel of engineers watching the
forty-first three-minute demo of the day, and an examiner whose job is to find whoever
published your idea first.

MAINLINE won, 8.08 out of 10 against 7.49 for the runner-up. It also lost the investor's
vote outright, to a written dissent. Another candidate scored higher on the demo criterion.
And the reviewer who searched hardest for earlier work cut MAINLINE's originality score
before ranking it first.

That is the real shape of the decision, and the rest of this page is the record.

---

## What kind of numbers these are

Every figure below is a **research-phase finding** — what a research agent concluded on a
stated date, in the separate `hackathon-research/` repository — not a measurement of the
software this repository ships. Each carries its file. The demonstration's contents are
authored: no real incident, no real site, no real fatality.

## The reset

Until then the five had been scored out of 50 against the hackathon's own criteria.
Those totals were thrown out as stale: they priced a 14-day build clock the founder had
since removed (`hackathon-research/research/04-final/judge-hackathon.md:3`). The replacement
rules, in his order:

1. **Startup potential** — could this become a real company? Weight **0.40**.
2. **Winning the hackathon**, demonstration included. Weight **0.35**.
3. **Novelty** — our own methods, not somebody else's re-labelled. Weight **0.25**.
4. **No deadline constraint.** The only build-shaped penalty left was *this may not work at
   all*, and no candidate carried one (`hackathon-research/research/00-log.md:83`).

## The five

| slug | in one sentence |
|---|---|
| **safety-custody-memory** (later named MAINLINE) | Every clause of a safety procedure points back to the event that wrote it. The permit-to-work — the form a supervisor signs before a crew opens a live machine — is a protected branch the database refuses to merge while any recalled prior event lacks a signed answer from a named person. |
| **memory-substrate** | An open-source engine storing an AI agent's memory as governed database state, so a rule like *no memory may be unowned* is enforced by the database, not application code. |
| **loop-ledger** | Clinical follow-up as double-entry bookkeeping: every open loop is a debit against the patient and a credit to exactly one named custodian, so an unowned loop cannot be written. |
| **retrievability-engine** | Models how fast each worker forgets each lesson, and decides from that whether to stay silent, ask, or put the lesson in front of the crew. |
| **person-owned-care-memory** | A care record owned by the person receiving care rather than by any provider, so it survives the provider closing. |

## The panel

One trap in the headings: **the columns are judges, not criteria.** Each judge scored every
candidate on all three criteria and applied the 0.40 / 0.35 / 0.25 weights itself, so a cell
is that judge's weighted total out of 10.

| Candidate | Venture judge | Hackathon judge | Novelty judge | **Mean** |
|---|---|---|---|---|
| **safety-custody-memory (MAINLINE)** | 7.85 (#2) | **8.40 (#1)** | **7.98 (#1)** | **8.08** |
| memory-substrate | **8.08 (#1)** | 7.05 (#3) | 7.35 (#2) | 7.49 |
| loop-ledger | 6.75 (#4) | 6.98 (#4) | 7.23 (#3) | 6.99 |
| retrievability-engine | 6.45 (#5) | 7.50 (#2) | 6.68 (#4) | 6.88 |
| person-owned-care-memory | 6.85 (#3) | 6.88 (#5) | 6.55 (#5) | 6.76 |

Source: `hackathon-research/DECISION.md`, reproducing the three sheets in
`hackathon-research/research/04-final/`. *One coincidence:* memory-substrate's venture score
of 8.08 equals MAINLINE's mean. Unrelated numbers.

## Why MAINLINE won, and how narrowly

MAINLINE is the **only candidate top-two on all three criteria at once**.
Averaging each criterion across the three judges, it scored 7.33 on startup, 8.50 on the
hackathon and 8.67 on novelty. Every rival is top-two on at most two of the three
(`hackathon-research/DECISION.md`, *Why it won*).

The auditor who reviewed the panel is explicit that this is a **broad win, not a decisive
one on any single axis**, and the arithmetic agrees:

- On **startup** — the founder's own first criterion — the top two are 7.33 against 7.17.
  That is a dead heat.
- On the **hackathon** axis MAINLINE does not lead at all. Loop-ledger does, 8.83 against
  8.50, and the venture judge called it *"the portfolio's best demo"*
  (`hackathon-research/research/04-final/judge-venture.md:49`).
- The **novelty judge ran twice**, on two different models: the first pass ranked
  memory-substrate first at 8.10, the re-run — which produced the prior-art register below —
  ranked MAINLINE first at 7.98. The log reads the disagreement as *"genuine signal
  that substrate vs safety-custody is close on the novelty axis"*
  (`hackathon-research/research/00-log.md:99`).

What MAINLINE won on was the absence of a bad column — *"the only candidate with no weak
column"*, in the hackathon judge's phrase. The reason was engineering restraint, not
showmanship: it refused to claim database time travel across years, because the retention
window that would allow it is measured in hours, and built its own version history instead;
and it stated a throughput ceiling rather than claiming none existed
(`hackathon-research/DECISION.md`).

## The dissent

The venture judge did not pick MAINLINE. It picked **memory-substrate**, for category-scale
market size and the only route to customers needing no sales channel — open source plus
protocol distribution, reaching many agent frameworks without a sales call. Against MAINLINE
it recorded the opposite shape: the best buyer motive and founder fit in the set, but a
ceiling — *"profitable at three customers"* reads as bootstrap, not venture, in a market
where every credible entrant so far was incubated inside an operator, and with zero customer
conversations held
(`hackathon-research/research/04-final/judge-venture.md:21,31`).

Two details make it load-bearing.

First, it is a **dissent that still routes through MAINLINE**. Having picked
memory-substrate as the company, the same judge's board strategy is to *"monetize first via
the safety-permits wedge"* — to earn the first revenue through the candidate it ranked
second (`hackathon-research/DECISION.md`).

Second, the disagreement was never resolved by argument, and the panel says so. The
hackathon judge and the auditor isolate the same single flip condition, and it is a belief
about the world rather than a weighting: is a named mining buyer genuinely reachable by a
solo founder, or does protocol distribution substitute for the sales channel he lacks? If the
buyer is unreachable **and** distribution works channel-free, memory-substrate takes first
place, 7.65 against 7.40 (`hackathon-research/DECISION.md`). Only market contact settles it.

## The docking

The novelty judge ran under a patent-examiner lens and produced the corpus's only systematic
**prior-art search** — a hunt for anything already published or shipped that does the same.
It gave MAINLINE the field's highest novelty score, then **cut it from 9 to 8**,
naming five classes of earlier work against it
(`hackathon-research/research/04-final/judge-novelty.md:41,43`):

1. Git's blame and bisect, and protected branches with required status checks — a shipped
   GitHub product.
2. Documentation-as-code and policy-as-code — OPA/Rego gating a build pipeline.
3. The *"git for X"* genre — Dolt for data, legislation-in-git experiments.
4. Stable identity for a piece of a document that survives reflow — solved years ago by DITA
   element IDs, S1000D data module codes and Akoma Ntoso versioned identifiers. *Stronger
   than git's line heuristic* is true but understates the existing art.
5. Tamper-evident append-only ledgers, called **prior art in full** — AWS QLDB, immudb,
   Certificate Transparency (RFC 6962), S3 Object Lock. *"The invention is the gating, not
   the ledger."*

What survived was narrow and specific: a clause edit classified as *weakening* a control, on
a clause whose history contains a severe event, automatically raising a blocking check on the
open permit; and **diachronic gating**. Two sentences on that term; it has its own page.
*Synchronic* checking asks whether the world as it
stands now satisfies the rule as it stands now — what every shipping permit and document gate
the judge could find does. *Diachronic* checking asks instead what a decision depends on and
what has since happened to those dependencies, which is the condition MAINLINE's merge is
evaluated against; the argument in full is [`05-why-ancestry.md`](05-why-ancestry.md). Of
those two the judge wrote that they are *"the only claims in the field I could find no prior
art for"* (`hackathon-research/DECISION.md`).

The docking is the part worth dwelling on. A judge that has already picked the winner
inflates; it does not take a point off its favourite and hand it the round anyway. The
auditor's phrase: *"anchored judges inflate, they do not dock and still award"*
(`hackathon-research/DECISION.md`).

## What the prior-art search killed

The same search damaged two rivals' headline claims on the record. Both are worth stating,
because they show the search was not run to a foregone conclusion.

**The retrievability-engine's central claim was false as a universal.** Its inherited finding
— *nobody models the human holder's forgetting curve* — was answered by named, deployed art:
Duolingo's Half-Life Regression (Settles & Meeder, ACL 2016), which models the decay of each
item in each individual learner across hundreds of millions of people; FSRS, an off-the-shelf
spaced-repetition schedule the candidate adopted openly; and commercially Axonify (3.5
million workers), Qstream and Cerego. The claim holds only when
narrowed to *nobody does this inside the work-authorisation moment* — a narrowing the
candidate's own dossier had already made
(`hackathon-research/research/04-final/judge-novelty.md:77,132`).

**Memory-substrate's recall formula is a re-parameterisation, not an invention** — the same
equation with the variables renamed and re-tuned. Its `recall = similarity ×
retrievability^α × credence^β` maps onto Park et al.'s *Generative Agents* (2023), which
scores retrieval as a weighted combination of recency, importance and relevance, and onto
ACT-R base-level activation (Anderson & Schooler, 1991), the canonical decay-plus-match
retrieval equation and 35 years old
(`hackathon-research/research/04-final/judge-novelty.md:53,133`).

Neither finding dismissed its candidate — memory-substrate still placed second overall. They
are here because a prior-art search that only ever confirms the front-runner is not a search.

## What happened to the four that lost

None of the four was discarded whole (`hackathon-research/DECISION.md`):

- **memory-substrate** became the **factored kernel inside MAINLINE** — the same invariants,
  separated so they are not mining-specific — with the panel recommending it be open-sourced
  as a CockroachDB Agent Skill. That packaging is a recommendation, not something this
  repository has exercised: Agent Skills here are `DESIGNED`, meaning built with no captured
  run. Its case file supplied the reasoning: *"the contest is the entry's label, not the
  schema."*
- **retrievability-engine** contributed its **logged-silence ledger** — every prior event the
  gate considered and declined to surface, written down with the arithmetic behind that
  decision. `DECISION.md` records it as the piece to import; how far it landed is a question
  for the build documents. Its broad forgetting-curve claim was prior art; this narrow piece
  was not.
- **loop-ledger** is **vertical #2** — the next industry for the same kernel — and remains
  the field-best demonstration at 8.83, to be revisited if market contact validates its buyer.
- **person-owned-care-memory** was **shelved**: its dependency on care events reaching a
  person-owned store is structural, not a matter of build time, and its novelty claim did not
  survive the prior-art search.

## What this page does not tell you

It does not tell you what the audit found when it examined the process that produced this
result — including how much of the reasoning above the auditor was willing to call
unreliable, and what it upheld anyway. That is [`03-the-audit.md`](03-the-audit.md) — read
it next.

<!-- word count: 1997 · re-derive: python -c "import io;print(len(io.open('docs/story/02-the-choice.md',encoding='utf-8').read().split()))" -->
