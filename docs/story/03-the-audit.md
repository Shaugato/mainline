<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE AUDIT THAT FOUND AGAINST US

Before a line of product code was written, this project ran a contest to decide what to build.
Eighteen problem areas were scanned, five ideas survived, and three simulated judges scored those
five under different lenses. The coordinating agent that ran all of it — the research corpus
calls it the **orchestrator** — then commissioned one more agent with a single instruction:
attack the result, and check me for bias.

It found against him.

Not against the answer — the winning idea stayed the winner. It found against the *reasoning*.
The explanation the orchestrator gave me for changing its mind was, the auditor wrote,
contradicted by its own scoring record. The decision file had been written and dated **before**
the evidence gathered to test it. Two of the three judges had been shown which idea was the
incumbent favourite before they scored it. And the section of the decision file that explains why
the choice changed should, the auditor concluded, be read as *"unreliable narration."*

The audit is unedited at `hackathon-research/research/04-final/audit.md`, dated 2026-08-02, in the
research repository beside this one. This page says what it found, why the verdict survived, and
the one contamination that cannot be cleaned.

---

## The words this page uses

- **orchestrator** — the coordinating agent that ran the research: it set the phases, briefed the
  other agents, and wrote the decision file.
- **judge** — one of three agents handed the five ideas under a different lens each: *venture*
  (would this be a company?), *hackathon* (would this win?), *novelty* (has anyone built it?).
- **rubric** — the list of things being scored. Which axes are on it decides the answer as much as
  the scores do (finding 1).
- **weighted mean** — the judges' totals averaged using my stated weights: startup
  potential `0.40`, hackathon `0.35`, originality `0.25`.
- **blind judging** — a judge not told which candidate the organiser already favours. Ours were not
  blind (finding 3).
- **prior-art search** — checking whether someone already shipped or published the idea.
- **MAINLINE** — the winning candidate, `safety-custody-memory` — this project. Its mean was 8.08
  against the runner-up's 7.49: a margin of **0.58**.

**One warning about every number below.** These are research-phase numbers — what research agents
concluded from desk research in early August 2026 — **not** measurements of the shipped system,
which are cited elsewhere to the artefacts that produced them.

---

## Finding 1 — the earlier favourite fell to the wrong rubric, not to the clock

Earlier, under an assumed fourteen-day deadline, a different candidate (`loop-ledger`) ranked
first. When the deadline assumption was dropped and the ranking changed, the orchestrator told the
me why: under a clock the tiebreakers were buildability and a three-minute demo, and removing
the clock removed both.

The auditor read the scorecards. Totals: `loop-ledger` 39, `safety-custody` 38, `person-owned` 38,
`memory-substrate` 37, `retrievability` 36. The entire gap between the top two was **one point, on
Real-World Impact** — 7 against 6. Buildability was scored 7/10 for three candidates alike and was
never inside the 50-point total. Production Readiness was 6 for all five, so the deadline
discounted the whole field equally rather than separating it. The stated reason was not supported
by its own record; the auditor's term was *"post-hoc rationalisation"* (`audit.md` §3.1).

Then the larger defect, which nobody had stated. Those scorecards measured **only the hackathon's
five judging criteria**. Startup potential — my own first criterion, stated twice — was
never a scored axis at all, so the earlier #1 ranked on one of his three criteria only. That is a
*wrong-rubric* artefact, worse than a deadline artefact, because the re-rank was necessary whether
or not the deadline existed — *"for a reason the orchestrator did not give."*

## Finding 2 — "correct in outcome, contaminated in process, misdescribed in rationale — all three at once"

That is the auditor's verdict, verbatim, on the decision to elevate MAINLINE to the winner
(`audit.md` §3.2). It named fingerprints, and named them real:

- **The pivot document overstated the row that drove the pivot.** `PLATFORM-THESIS.md` graded the
  winner's worst objection *"Yes — and it inverts"* — the only escalated verdict in a seven-row
  table of yes / no / partly. A case file written later by a different agent had to correct it: the
  grade holds for one half of that objection, and the other half is structural.
- **The most flattering argument in the corpus was orchestrator-introduced and never
  independently scored.** The claim that my digital-forensics background *is* chain of
  custody appears in the pivot document and the decision file and nowhere in the earlier research.
  The auditor calls it *"the exact shape of a self-serving conclusion"* — then says it is
  nonetheless true, and that judges reached it independently once told my profile. Both
  halves belong on the record.

## Finding 3 — judging was not blind, and the decision was dated before its own evidence

The mission log records the case-file task as *"Case file: safety-custody-memory **(MAINLINE)**"* —
the anointed name was inside the agent's brief. The resulting case file is titled MAINLINE, and one
judge's scoresheet reproduces the label verbatim. **Two of three judges scored a candidate that
arrived pre-labelled as the incumbent choice, and both ranked it first** (`audit.md` §3.2).

And the order of operations was backwards. `DECISION.md` was written 2026-08-02 18:42. The five
case files: 23:19–23:23. The three judges: 23:29, and 01:10 and 01:12 on 2026-08-04. The decision
preceded the evidence gathered to test it by five hours to two days — *"a verification round run
on a question already answered in a file titled DECISION — FINAL."*

(The file on disk now reads 2026-08-04 and supersedes earlier versions; the timestamps above are
the auditor's.)

## Finding 4 — read the rationale as unreliable narration

> *"Treat `DECISION.md` §'What changed from the earlier call' as **unreliable narration** and rely
> on the three judge files, which were produced independently and which agree with it for better
> reasons."* (`audit.md` §3.2)

`hackathon-research/DECISION.md` now carries that sentence about itself, with all four findings,
under its own heading *"The process critique"*.

---

## Why the verdict still stands

The persuasive half, and it is the auditor's reasoning, not ours:

1. **The judges corroborated non-uniformly.** #1 / #1 / #2, with the venture judge dissenting in
   writing for a stated reason — it picked a different candidate on category size and a route to
   customers needing no sales team. Anchoring produces agreement; a written dissent is what it does
   not produce.
2. **The judge with the sharpest instrument docked the winner and it still won.** The novelty judge
   ran the corpus's only systematic prior-art search, cut the winner's novelty from 9 to 8, named
   five classes of existing art against it, and ranked it first anyway. The auditor: *"Anchored
   judges inflate; they do not dock the thing they are anchored on and then hand it the win on the
   residue."*
3. **The load-bearing facts were externally verified rather than asserted.** A market pass on
   2026-08-02 checked four. A Queensland resource-safety statute whose critical-control regime came
   into force in June 2025. Personal legal exposure for a site senior executive under
   industrial-manslaughter law. A precedent making cross-company pooling of safety data
   liability-blocked, which is why the design is single-tenant. And a named-competitor sweep
   returning no product doing version-control semantics over a safety corpus. That last is a sweep
   run on a date, written down as one — never as *"none exists"*.
4. **Strip the most exposed scoresheet entirely and the winner still leads.** Remove the hackathon
   judge's sheet — the one that reproduced the label — and the remaining two means read **7.91
   against 7.71**. The lead does not come from the contaminated axis. It comes from novelty (8.67
   mean, from the search that docked it), and from being top-2 on all three criteria when no rival
   manages more than two.

## And one attack nobody on the panel had made

It also mounted an objection of its own, at the winner's best asset: the paid retrospective audit
meant to open the first customer. Its deliverable is a dated, named-author catalogue of a
customer's own un-reviewed weakenings of safety-critical controls, sold to that customer's chief
in-house lawyer. This project's earlier validation had already found such material
**discoverable** — a court can compel the company to produce it. A downgrade, not a kill: route the
engagement through external law firms, which also supplies the channel the panel said did not exist
(`audit.md` §2.3).

## The residual that cannot be cleared

Two of three judges saw the label, so the auditor could not certify the 0.58 margin as
uncontaminated, and neither can we. What can be said is narrower: the lead is not carried by the
contaminated axis, and it survives deleting the most exposed sheet. Both are different statements
from *"the margin is clean"*, which is the one this page does not make.

## Why this is in the story at all

A project whose claim is that a database refuses what a person would wave through cannot ask to be
taken at its word about how it picked what to build. The audit is that discipline one level up:
commission an attack on your own result, publish what it finds against you, and leave the finding
in the file it is about.

<!-- layer-1 opener 199 w (title→first `##`); caps 200/1,600. -->
<!-- word count 1591 · re-derive: `python -c "print(len(open('docs/story/03-the-audit.md',encoding='utf-8').read().split()))"` -->
