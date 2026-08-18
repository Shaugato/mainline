<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEVPOST NARRATIVE — four paste-ready blocks, drop-in, edits nothing

**This file changes no other file.** In particular it does **not** edit
[`docs/submission/DEVPOST.md`](../submission/DEVPOST.md), which belongs to another owner and was
byte-identical before and after this page was written. These four blocks are a **drop-in**:
whoever owns that page decides whether any of them lands, and where. Nothing here is submitted by
existing.

**House style, taken from `DEVPOST.md`.** Everything between a `<!-- PASTE -->` marker and the
next horizontal rule is the pasteable text; everything else — this preamble, the note above each
marker — is for the person filling in the form. **Every number inside a block names the artefact
that produced it.** Digits inside `code spans` are *names* (a date, a run identifier, SQLSTATE
`23514`), not measurements. **Every block ends with a line beginning `OPEN THIS TO CHECK IT`**
naming the one path a sceptic opens to falsify the block above it. If that path does not say what
the block says, the block is wrong.

**Where these blocks go is not decided here, and three of them have no obvious home.** Block 1 is
a replacement candidate for the *Inspiration* field. Blocks 2, 3 and 4 map onto no Devpost field
by name; the closest homes are *What we learned* and the *About the project* body. **Do not paste
block 1 alongside the existing *Inspiration* block** — they answer the same field two different
ways, and the existing one is not weakened by being replaced, only by being duplicated.

**Two classes of number appear below and they are never mixed inside one sentence.**
*Research-phase findings* come from `hackathon-research/`, are labelled as what a research agent
concluded on a stated date, and are **not** measurements of the shipped system. *Product
measurements* come from this repository and carry the artefact that produced them.
**`hackathon-research/` is a separate git repository. It is not inside the tree we submitted and
it has no remote** — a judge cloning this project cannot open those files. Blocks 2, 3 and 4 say
so in their own words rather than pointing a reader at a path that will not resolve.

---

## Block 1 · Inspiration, rewritten

> **Devpost field:** *Inspiration*. **446 words.** Written to be finished in about sixty seconds
> by somebody who has never heard of a permit to work. No SQLSTATE, no term used before it is
> glossed, and the authored-corpus disclaimer sits on the same screen as the story rather than in
> a footnote.

<!-- PASTE -->

Before a crew opens a live machine — a pump, a compressor — a supervisor signs a form authorising that exact work on that exact day. The industry calls it a **permit to work**. It lists what has to be true first: lock this off, drain that, confirm the pressure is at zero before the guard comes off.

Some of those steps exist because something went wrong once. A machine was opened while it still held pressure — the isolation had been signed off without anybody verifying it was at zero. Somebody wrote the lesson into the procedure as a numbered rule — a **clause**. Then that person moved on, and so did everyone in the room. What is left is a line in a document with no reason attached.

Seven years later a supervisor fills in a permit that leans on that clause, and presses the button that authorises the work.

**The database refuses the write.**

Not a warning. Not a banner. Not a pop-up dismissed at 3 a.m. by somebody who has seen it forty times. The permit stays unauthorised until a named, qualified person reads the original event and signs a specific answer: the step still applies, or here is why it does not — in their own name, on the record.

The database can refuse because the clause is not stored as text alone. It carries a pointer to the event that caused it to be written: its **blame ancestry**, the chain of events behind a rule, held as database rows rather than as prose. And the refusal is a rule the database enforces on every write, not a check our application performs — so it holds against our own software, against somebody typing SQL by hand, and against a back-office correction by a person with credentials and a deadline — which is how controls get bypassed.

**Everything in the demonstration was written for this repository.** The event is dated `2019-03-14` and the database records it as a severity-four stored-energy release during intrusive work. Its own narrative column ends: *"No real incident, no real site, no real fatality: this narrative was written for the MAINLINE demonstration and describes nobody."* The data labels itself `SYNTHETIC` wherever it appears. The mechanism is real; the inputs are authored. Nobody's safety has been improved by this yet, and a submission implying otherwise would be doing the exact thing this project exists to refuse.

**OPEN THIS TO CHECK IT — `verticals/mainline/db/seeds/demo/demo_world.sql`.** Every fact in that last paragraph is a column value in that file: the date, the severity, the clause text, and the sentence saying it describes nobody. If the disclaimer is missing, believe nothing else here.

---

## Block 2 · The search that got us here

> **Devpost field:** none by name — closest homes are *What we learned* or the *About the
> project* body. **442 words.** Every figure here is a **research-phase** finding: what an agent
> concluded on a stated date, not a measurement of the shipped system.

<!-- PASTE -->

We did not start with mining safety. We started with a question — where does an organisation forgetting something actually hurt somebody? — and spent the first days of August 2026 trying to kill every answer.

Eighteen domains were scanned: cybersecurity operations, aviation maintenance, aged care, insurance claims, government casework, mining and twelve more. Twenty candidate problems were cut to twelve, and each went to a validator briefed to check it against the companies already selling there.

**Zero came back STRONG.** Six came back WEAK and six came back KILL (`hackathon-research/research/00-log.md`, tally recorded `2026-08-02`). The kills are the useful part, because each names something real:

- **Insurance-claims memory — KILL.** Guidewire ProNavigator *is* the product.
- **Laboratory as-run records — KILL.** Benchling shipped it; Riffyn, the nearest precedent, had already died.
- **Child-welfare casework continuity — KILL.** Binti, with Anthropic, already covers 46 % of US child welfare.
- **Transfer-credit records — KILL.** The statistic the opportunity rested on had been refuted, and incumbents owned the wedge anyway.
- **Regulator-commitment amnesia — KILL.** The named failures were an *incentive* failure, not a memory failure.

Two of our own favourites went down in the same pass: machine biography, the idea we liked most on day one, came back WEAK at `3` of `10`; the security-operations centre that never forgets came back KILL, crowding `10` of `10`.

Five candidates were assembled from what survived, each written up by an agent told to argue for it honestly rather than sell it. Three judges scored all five under three lenses — seed investor, hackathon panel, patent examiner — weighted `0.40` / `0.35` / `0.25` on the founder's stated priorities.

**MAINLINE won broadly rather than decisively, and the record says so in those terms.** It was the only candidate top-two on all three criteria at once; every rival was top-two on at most two. It did **not** lead on the demo axis — another candidate did. **The investor judge dissented in writing.** And **the novelty judge, the only one who ran a systematic prior-art search, cut our originality score from `9` to `8`, named five classes of existing art against us, and ranked us first anyway** (`hackathon-research/research/04-final/judge-novelty.md`, `2026-08-02`). A judge who docks the candidate they are supposed to be anchored on, then awards it on the residue, is the most useful judge in the set.

**That research corpus is a separate repository and is not inside the code we submitted.**

**OPEN THIS TO CHECK IT — `docs/story/01-the-search.md`**, which carries the funnel into this repository with every verdict, every kill and the file each came from, marking each line that traces to the corpus rather than this tree.

---

## Block 3 · What we got wrong

> **Devpost field:** none by name — closest home is *What we learned*, after the existing
> entries. **447 words.** One decision-level failure and two build-level ones, each named with
> the control that caught it, because a failure without its control is an anecdote.

<!-- PASTE -->

**We commissioned somebody to attack our own decision, and it found against us.**

Once the panel had picked MAINLINE, an adversarial auditor was handed the whole research corpus and two jobs: overturn the result if it could, and check whether the process had a thumb on the scale. It upheld the outcome. It did not uphold the reasoning.

The reason we had published for changing an earlier pick — a deadline, we said — was contradicted by our own scoring record. The real defect was a **wrong rubric**: those earlier scorecards measured only the hackathon's five judging criteria, so my own first criterion had never been a scored axis at all. It also found our decision file was timestamped hours before the evidence gathered to test it, and the judging not blind, because the winner's name was in the brief. Its verdict is three findings at once — *"correct in outcome, contaminated in process, misdescribed in rationale"* — and it tells the reader to treat our own account of the change as **"unreliable narration"** (`hackathon-research/research/04-final/audit.md`, `2026-08-02`, a separate repository; `docs/story/03-the-audit.md` carries it here). We kept that sentence. It is why the rest of the record is worth reading.

**We reshaped a seed to match the code, and three controls caught it.** A test was failing because the application derived one identifier for a signing credential while the database enrolled a different one. The database owns that value; the code reads it. A worker sent to fix the failure edited the *seed data* to enrol the constant the application derived — turning a test green by making the evidence agree with the defect. Three independent negative controls refused it, the edit was reverted, and that original defect is now the deliberately planted one a CI lane uses to prove it sees faults a database-less lane cannot (`docs/ci/cluster-lane-falsifiability.md` § 9).

**And a CI lane that failed to parse appeared on no red list at all.** `cluster-lane-bites.yml` was committed, and its run `31720234309` lasted **0 seconds and created zero jobs**, titled by its file path rather than its name — GitHub's signature for a workflow it refused to read. For a day the lane was invisible: a workflow that never starts produces no failing job to list. **An absence and a pass are the same colour of nothing on a dashboard.** The standing guard against that class is now `actionlint`, running in the main lane.

**OPEN THIS TO CHECK IT — `docs/CI-STATE.md` § 10.3.** That section records the unparsed lane with its run identifier, in a document whose job is naming every failing workflow with a quoted log line. The identifier opens on GitHub with no account of ours.

---

## Block 4 · Why ancestry, and not state

> **Devpost field:** none by name — closest home is the *About the project* body, before the
> five judging-criteria blocks. **465 words.** The intellectual core, stated once. The full-depth
> version is `docs/story/05-why-ancestry.md`; the normative version is `spec/TRAPPOINT-SPEC.md`
> § 2.

<!-- PASTE -->

Every permit and document-control system we found asks one question at approval: **does the paperwork in front of me satisfy the rule as it stands today?** Isolation in place, gas test valid, signature present. There is a word for checking the world as it is right now — **synchronic** — and it fits them all.

Nothing in that question can express *why* a rule says what it says. So when its author leaves, the reason goes too, and what remains is a step that looks arbitrary and gets relaxed by somebody reasonable.

MAINLINE asks the other question: **what does this decision depend on, and what happened to those things?** That is **diachronic** — checking across time rather than at an instant. The gate is evaluated over the clause's ancestry, not the current state of the form.

A prior-art search run on `2026-08-02` by an independent reviewer with a patent-examiner brief swept the shipping products — Veeva QualityDocs, MasterControl, Enablon/Cority — and returned *"no prior art found"* for a gate conditioned on ancestry rather than current state. **One dated sweep by one reviewer, not a claim that nothing exists anywhere** (`hackathon-research/research/04-final/judge-novelty.md`, a separate repository; `docs/story/05-why-ancestry.md` carries it here).

**Why a refusal and not a banner.** The obvious build shows the old event beside the Approve button. It fails for a reason with nothing to do with software: a panel beside a button is a nag, and nags get dismissed. The failure mode is not absent memory — it is memory present and ignored. So recall is not displayed next to the decision; it is a precondition of it.

Three steps do it, all inside the database rather than our code:

- **PROJECT** — a trigger, a small program the database runs on every write, copies the cross-row fact onto the permit's row, read from an authoritative table and never from the writer.
- **PIN** — a completed decision is tied to a counter of open questions, and a foreign-key rule makes attaching a new one afterwards impossible rather than forbidden.
- **REFUSE** — a `CHECK` constraint over that copied column refuses the write, for every writer, for ever.

In place of a banner there is the five-character code a database returns when it declines — a **SQLSTATE**. `23514` is a violated `CHECK`, and the constraint's name, `gate_closed_when_issued`, survives into JSON a browser can read. Once a qualified person signs the answer, the same history is **admitted**, `00000`: a gate that always refuses is broken, not safe (`evidence/gate-refusal/proof-20260814T032418Z.json`, verdict `PROVEN`, `caveats: []`, local node).

**OPEN THIS TO CHECK IT — `spec/TRAPPOINT-SPEC.md` § 2.** PROJECT, PIN and REFUSE are normative there, in the words the schema implements. If the constraint lives in our application rather than the database, the argument above is wrong and should be scored down.

---

## What this page does not claim

Kept outside the blocks, because these are scope statements for the person pasting and they are
already stated at length in [`docs/submission/DEVPOST.md`](../submission/DEVPOST.md) and
[`docs/HONESTY.md`](../HONESTY.md).

- **CockroachDB Agent Skills is `DESIGNED`, not `EXERCISED`.** Two skills ship with executable
  assertion scripts; no run of either is captured under `evidence/`. Do not promote that verdict
  to fill a block.
- **Amazon Bedrock runs in this repository and is _not_ in the demo's request path.** The beats
  the deployed origin answers are SQL against CockroachDB and call no model.
- **The change request has no admission beat.** Use case 2 refuses and declares; it is told, not
  driven.
- **The corpus is authored.** No real incident, no real site, no real fatality. Block 1 carries
  that on the same screen as the story, which is the only place it is any use.
- **The CockroachDB platform findings this project measured are catalogued separately** and are
  deliberately not enumerated on this page.

<!-- word count over the four paste blocks only:
python -c "import re;t=open('docs/story/DEVPOST-NARRATIVE.md',encoding='utf-8').read();b=re.findall(r'<!-- PASTE -->\n(.*?)(?=\n---\n)',t,re.S);print(len(b),[len(x.split()) for x in b],sum(len(x.split()) for x in b))"
-->
