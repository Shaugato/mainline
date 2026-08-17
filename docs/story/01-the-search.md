<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The search — eighteen domains, twelve verdicts, zero STRONG

We did not start with an idea. We started with a search, and the search was built to kill its own ideas.

The plan was ordinary: find an industry where people forget something that matters, then build
software that remembers it. Eighteen industries were scanned — mining, hospitals, banks, insurers,
laboratories, child-protection agencies, farms, schools, factories, power grids. Twelve of the
problems found there went to a second round, in which a researcher was told to **kill** each idea
rather than confirm it, usually by finding the company that already sells it.

Twelve went in. Nothing came back healthy. Six were graded `WEAK` — the problem is real, the
business is not. Six were graded `KILL`. Both of the ideas we had privately expected to win were
among the casualties.

That reads like failure. It is the most useful thing we have. Everything downstream of this page
survived a process that killed its own favourites, and the reasons the others died are specific
enough to check: a named competitor, a dated product launch, a statistic that turned out to have
been refuted.

This page is that list.

## How to read every number below

Each figure on this page is a **research-phase finding** — what a research agent concluded on a
date in early August 2026, written to a separate repository at
`D:/CoackroachDBxAWS/hackathon-research/`. **None of them is a measurement of the software this
project shipped**; product measurements live elsewhere and never share a sentence with these. Where a
figure is a judgement rather than a count, it says so, and each is cited to the file that holds
it — so a reader who disagrees can disagree with the source.

## Phase 1 — eighteen domains, seventy problems

Eighteen researchers, one per industry, in three batches of six, each asked what that industry
actually loses track of and how good the evidence is. All eighteen returned
(`hackathon-research/research/00-log.md`). The scan produced roughly seventy problems, which the
synthesis collapsed into five recurring shapes: a machine or a person whose history outlives its
custodians; lessons on paper that nobody recalls at the moment someone acts; a case that outlives
the caseworker holding it in their head; an open item known now and forgotten by the time it
matters; and a history that must be provable later but was never kept that way
(`hackathon-research/research/01-domains/00-phase1-synthesis.md`).

Twelve of those problems were selected for validation. The eight cuts were recorded with reasons
rather than dropped quietly: customer support because it is the most contested AI market on earth,
contract obligations because Ironclad and Evisort own it, construction because Procore and Autodesk
own the data (same file).

## The first thing that died was our own arithmetic

Phase 1's researchers were instructed to re-verify the statistics an earlier pass had been leaning
on. Several did not survive:

- *"61% of ignored alerts later proved critical"* — untraceable in any source; recorded as dead.
- *"2.8M manufacturing retirements by 2033"* — a misquote of a Deloitte scenario whose actual
  upper bound is a different claim entirely.
- *"75% of smallholder farmers lack extension access"* — folklore, no primary source.
- *"68% of medication errors at discharge"* — from a single cohort of elderly intensive-care
  patients; the defensible general figure is around 41% discrepancies, of which about 30% carry
  harm potential.

What survived that audit became the evidence floor for everything after it: SANS finding 43% of
organisations re-attacked with methods they had already defeated, peer-reviewed evidence that a
plant's process-safety memory decays over roughly three years, Roy's finding that physicians were
unaware of 61.6% of post-discharge test results, the Brady Review's fatality-cycle findings in
Queensland mining, and Reproducibility Project: Cancer Biology's 0 of 193 experiments reproducible
from their own published records (same file). One of those survivors was itself killed in the next
phase — see `credit-precedent` below.

## Phase 2 — twelve adversarial validations, zero STRONG

Each of the twelve went to a validator whose written mandate was *kill this candidate, do not
confirm it*. Four validators were killed themselves by a session limit mid-phase and were re-run;
the log records which (`hackathon-research/research/00-log.md`). The final tally, recorded in the
same log and in `hackathon-research/research/02-validation/00-phase2-synthesis.md`, is **0 STRONG /
6 WEAK / 6 KILL**.

*Strength* and *crowding* are the validator's own 0–10 judgements, not measurements: how well the
candidate survived attack, and how occupied its market already is, 10 meaning full.

| Candidate | Verdict | Strength | Crowding |
|---|---|---|---|
| incident-memory-safety | `WEAK` | 5 | 7 |
| discharge-followthrough | `WEAK` | 4 | 7 |
| care-continuity-au | `WEAK` | 4 | 7 |
| grid-asset-memory | `WEAK` | 4 | 7 |
| parcel-memory | `WEAK` | 4 | 7 |
| machine-biography | `WEAK` | 3 | 9 |
| casework-continuity | `KILL` | 3 | 7 |
| lab-memory | `KILL` | 3 | 9 |
| remediation-amnesia | `KILL` | 3 | 8 |
| claims-memory | `KILL` | 3 | 9 |
| credit-precedent | `KILL` | 3 | 8 |
| soc-memory | `KILL` | 2 | 10 |

Both prior favourites are in that table. `machine-biography` — lifelong memory for industrial
machines — came back `WEAK` at strength 3 against crowding 9, because the sketch had already
shipped as the headline feature of MaintainX, Maximo, Senseye and Veryon. `soc-memory` came back
`KILL` at strength 2 against crowding 10, the worst pair on the board.

## The six kills, each for a different reason

**`lab-memory` — the record-owner shipped it, and the last company to try died.** The idea was a
laboratory that remembers how an experiment was actually run rather than how it was written up.
Benchling, which already holds those records for 1,300+ biotechs, shipped closed-loop capture across
200+ instruments on 28 May 2026 — about ten weeks before the scan. The older signal was worse:
Riffyn built this exact product, raised roughly $20–27.5M with Siemens among its investors, and
ended as an intellectual-property asset sale in March 2022, since listed as inactive
(`hackathon-research/research/02-validation/lab-memory.md`).

**`claims-memory` — the incumbent's press release was our product description.** Guidewire, whose
software insurance adjusters sit inside all day, launched ProNavigator on 16 April 2026 and
described it as institutional knowledge surfaced at the moment of decision. The candidate's
best-quantified pillar — $15B a year in missed subrogation, meaning money an insurer never recovered
from the party at fault — was traced by full-text extraction of the NAIC journal paper that
supposedly established it to a single trade-press article cited in passing
(`hackathon-research/research/02-validation/claims-memory.md`).

**`casework-continuity` — 46% of the market already had it, from this ecosystem's own partners.**
Binti covers 550+ agencies across 36 states and DC — a research-phase estimate of 46% of US child
welfare — and had launched conversational question-answering over case notes, forms and agency
policy with Anthropic; Northwoods runs the adjacent product on AWS. The demo would have been shown
to judges who had seen it from their own partners
(`hackathon-research/research/02-validation/casework-continuity.md`).

**`credit-precedent` — the statistic underneath it had been refuted.** The candidate rested on the
GAO finding that transferring students lose 43% of their credits, one of the anchors Phase 1 had
graded as genuinely verified. The validator found a 2025 CUNY study measuring applicability directly
across the transfer event and putting transfer-specific loss near 2.7%, with statewide studies at
3.9–7.2%; the GAO figure came from 2004–2009 cohorts and aggregated losses from many causes.
CollegeSource TES, EdVisorly and Ellucian were already shipping the precedent-memory product
(`hackathon-research/research/02-validation/credit-precedent.md`).

**`remediation-amnesia` — the flagship evidence was a counterexample to the thesis.** The thesis was
that institutions forget what they promised regulators, anchored on TD Bank's ~$3.09B
money-laundering resolution and Citi's penalties. The DOJ record shows the opposite: an employee
emailed executives about the historical underspend causing systemic deficiencies in transaction
monitoring, and executives took no action; the regulator's remedy for Citi was to force a
resource-allocation process. The institution's memory worked and its willingness to spend did not —
which is where we learned that **not every forgetting problem is a memory problem**
(`hackathon-research/research/02-validation/remediation-amnesia.md`).

**`soc-memory` — "memory" was already the competitors' marketing word.** In security operations,
Dropzone ships "Context Memory", Prophet ships "institutional memory", and Torq had launched "SOC
Brain" days before the scan. The one observation that survived — each vendor's memory is locked
inside its own platform and cannot travel — argues for a standard rather than a product, and the
validator said so (`hackathon-research/research/02-validation/soc-memory.md`).

## And one WEAK that taught the same lesson faster

`care-continuity-au` — memory for aged-care and disability clients across staff churn — was graded
`WEAK`, not `KILL`, and its evidence was the best-sourced in the set: an Australian Royal Commission,
Australia's disability-scheme review, the national audit office. It failed on timing. AlayaCare shipped AI summaries of
progress notes in March 2026 and The Lookout Way shipped handover-summary agents in June 2026 — the
four months immediately before the scan opened on 2026-08-01
(`hackathon-research/research/02-validation/care-continuity-au.md`). We were not early to a gap; we
were watching it close.

## What the six kills had in common

Each one looked like a memory problem and was really something else.

- **Distribution.** `lab-memory`, `claims-memory`, `casework-continuity` and `credit-precedent` all
  died because whoever owns the record owns the memory over it, and that was never going to be us.
- **Incentives.** `remediation-amnesia` died because the warnings had already been read and
  ignored, and `credit-precedent` had the same shape underneath: the institution is sometimes
  motivated to make the decision that harms the student, so better recall speeds up the wrong answer.
- **Capture, not recall.** `grid-asset-memory` failed on the same axis: the binding constraint was
  getting the history written down at all, not finding it afterwards
  (`hackathon-research/research/02-validation/00-phase2-synthesis.md`).

The residue that no validator could kill was named in the same synthesis: not memory as storage and
retrieval, but memory that carries **semantics** — decay and reinforcement, obligations that stay
open until someone answers them, custody and provenance (who held a record, and where it came
from), belief that is calibrated rather than summarised, and sharing that crosses an organisational
boundary without carrying the private detail across. That list is what the contest calls agentic
memory, and it is where the five finalists came from.

## Where Phase 2 ended: five candidates, no winner

Alongside the twelve validations, eight further agents each crossed one surviving industry with an
unrelated field — double-entry bookkeeping, air-crash investigation, spaced repetition, immune
memory, archival provenance, the version-history semantics of git — producing forty hypotheses in
all (`hackathon-research/research/00-log.md`). Phase 3 was handed five candidates assembled from
the least-weak industries crossed with their strongest of those hypothesis stacks, plus one
horizontal candidate — a general engine rather than one industry's product — that came directly out
of the cross-cutting finding above
(`hackathon-research/research/02-validation/00-phase2-synthesis.md`):

| Candidate | Built from |
|---|---|
| loop-ledger | discharge-followthrough × double-entry accounting, timeouts for results that never arrive, seed vaults |
| safety-custody-memory | incident-memory-safety × archival provenance and git semantics |
| retrievability-engine | incident-memory-safety × forgetting curves and fading immunity |
| person-owned-care-memory | care-continuity-au × flight recorders and reinsurance treaties |
| memory-substrate | the cross-cutting finding — the horizontal engine |

One of those crossings is where MAINLINE came from. Every permit system we looked at — the software
behind the form a supervisor signs before a crew opens a live machine — is **synchronic**: it checks
the world as it is right now, asking whether the current document satisfies the current rule.
MAINLINE is **diachronic** — it checks what a decision depends on and what has since happened to
those dependencies. That distinction is argued in full, with its
dated prior-art sweep, in [`05-why-ancestry.md`](05-why-ancestry.md), and it is not argued here.

Which of the five won, under which three judges, over which written dissent, is
[`02-the-choice.md`](02-the-choice.md). Nothing on this page scores them.

<!-- word count: `python -c "import sys;print(len(open('docs/story/01-the-search.md',encoding='utf-8').read().split()))"` -->
