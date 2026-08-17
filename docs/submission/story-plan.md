<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STORY LEAD — the plan

**Lead:** story. **Written 2026-08-17.** Repo `D:/CoackroachDBxAWS/mainline`, master, HEAD `9e91467`.
Research corpus read at `D:/CoackroachDBxAWS/hackathon-research/` (a separate git repository, one
directory up from this one — **it is not inside this tree and no worker writes to it**).

**What this wave produces:** the origin story — how the idea was found, what was explored, what
was rejected and why, what was got wrong on the way, and why *this* is the solution that was
needed. It is the Devpost narrative, and it is scored under **Creativity & Originality** and
**Real-World Impact**.

**Why it does not exist yet.** Every judge-facing document in this repository is written to be
*verified*. That is the right register for a reviewer checking a claim and the wrong register for
anyone meeting the project for the first time. The founder read our own explainer and said he had
*"a very hard time to understand"* it. A judge reading cold has less context than the founder and
less patience. The material is not missing — it is spread across a 100-file research corpus in a
different repository and a 198-file `docs/` tree in this one, and nowhere is it a story.

---

## 0 · THE TWO RULES THAT BIND EVERY WORKER

These two paragraphs are reproduced **verbatim** at the head of all six worker briefs. They are
not boilerplate.

### 0.1 The readability bar

> **A non-technical reader must understand the problem, why it matters, and what we built, in
> sixty seconds.** The fix is *layering*, not simplifying — nothing becomes vaguer, what changes
> is what a reader meets first. **Layer 1:** concrete before abstract — a person, a situation, a
> consequence. **Layer 2:** the mechanism — the constraint, the trigger, the SQLSTATE, why it
> cannot be bypassed. **Layer 3:** the file, the line, the transcript. *Layer 3 already exists in
> this repository and must not be weakened.*
>
> **No term is used before it is defined.** `projection`, `blame ancestry`, `defeater`, `epoch`,
> `disposition`, `obligation`, `canonicalisation`, `MUS`, `synchronic`, `diachronic`, `commit
> DAG`, `SQLSTATE` — each gets a plain-language gloss at first use in your file, or it does not
> appear in your file. **No marketing voice**: `revolutionary`, `seamless`, `unprecedented`,
> `game-changing`, `cutting-edge`, `effortless`, `magic`, `simply`, `just`, `powerful`,
> `robust`, `leverage` are banned words. This product's entire claim is that it does not
> overstate; one of those words costs more credibility than any missing feature.
> **A reader must be able to check you** — every factual claim keeps its evidence path, moved to
> a link or a parenthesis rather than dropped.

### 0.2 The no-overclaim rule

> **NEVER claim anything in a better state than it is.** Agent Skills is `DESIGNED`, not
> `EXERCISED`. Bedrock runs in this repository and **not in the demo's request path**. The change
> request has **no admission beat** and says so. The corpus is **authored**: no real incident, no
> real site, no real fatality. These scopings are why the rest is believable — a verdict word is
> never softened, and a `DESIGNED` promoted to `EXERCISED` is the one edit this wave forbids
> outright.
>
> **NEVER weaken a claim to make it readable.** If a sentence cannot be both true and simple,
> write two sentences. Deleting a precise claim to make room for a friendly one is the failure
> mode of this entire wave. **NEVER regress**: baseline `1070` collected / `1069` passed / `0`
> failed / `0` errors; gate proof `PROVEN`, caveats none; `DEFAULT_MAX_RESPONSE_BYTES == 136 *
> 1024` does not move. **Never `terraform apply`, never redeploy, never touch AWS, never write an
> SSM parameter, never print a credential. Do not commit** — leave the tree for the orchestrator.

---

## 1 · RULINGS — what the brief left open, decided here

**R1 — The story lives in a new namespace, `docs/story/`, and no worker edits an existing file.**
Other leads in this wave own `README.md`, the architecture documents and the submission materials.
A plan that reaches into those guarantees a conflict and buys nothing: the origin story is a *new*
artefact, not a rewrite of an old one. Eight new files, one directory, zero edits outside it.
Cross-references into existing docs are **links**, never edits.

**R2 — The CockroachDB platform critique is NOT this lead's to author.** The founder's ask #3 (the
seven measured platform findings) went to every lead in the shared brief; a canonical critique
register does not exist yet and belongs to whichever lead owns it. Story workers **do not
enumerate, re-derive or publish the seven findings.** *One exception:* `has_function_privilege()`
appears in `04-wrong-turns.md` because it is **our** defect first — we shipped a privilege guard
whose check could never fail — and a platform observation second. Everything else gets at most a
one-sentence pointer of the form *"the platform findings we measured are catalogued separately."*
No story file may be the place a reader first learns a CockroachDB defect claim.

**R3 — Layering is per-file, not per-corpus.** Every one of the eight files opens with a layer-1
passage a non-technical reader can finish, then descends. There is no "the simple file" and "the
true file"; that split is exactly what failed the founder. Word budgets in §3 make the promise
checkable.

**R4 — The corpus is authored, and every story file says so on the same screen it uses it.**
The compressor-setpoint example (`135` ← `150`, `INC-2013-044`) is a **designed worked example**.
The seeded demo incident is `DEMO-INC-0001`, `2019-03-14T06:20:00Z`, and its own `narrative`
column ends *"No real incident, no real site, no real fatality: this narrative was written for the
MAINLINE demonstration and describes nobody"*
(`verticals/mainline/db/seeds/demo/demo_world.sql:276-278`). **Never write "injury", "a worker was
hurt", "someone died", or any sentence about a person.** Prefer the column: *"a severity-four
stored-energy release during intrusive work."* **Never write `2024`** — the only `2024` near this
story is `INC-2024-0117` inside a STAGED propagation payload that may not be narrated at all
(`docs/decisions/demo-use-cases.md:126-142`). Leave the `SYNTHETIC —` prefix visible wherever seed
text is quoted.

**R5 — Two classes of number, and they are never mixed in one sentence.** *(a) Research-phase
findings* come from `hackathon-research/` and are cited to `hackathon-research/<path>` and
labelled as what a research agent concluded on a date — they are **not** measurements of the
shipped system. *(b) Product measurements* come from this repository and are cited to the artefact
that produced them. **No worker re-derives a product number**; quote the artefact and its path. If
a worker believes a number is stale, they report it in their `still_broken` note and leave it
alone.

**R6 — Competitor claims are dated sweeps, never universals.** The corpus's prior-art search found
no diachronic permit gate among Veeva QualityDocs, MasterControl and Enablon/Cority
(`hackathon-research/research/04-final/judge-novelty.md:146`). Write *"a prior-art search run on
2026-08-02 found none, and here is the file"* — never *"none exists"*. **Do not add a competitor
the corpus does not name.**

**R7 — Verdict words are load-bearing and are copied, not paraphrased.** `EXERCISED`, `DESIGNED`,
`NOT-AVAILABLE`, `PROVEN`, `REFUSED`, `ADMITTED`, `OWED`, `STAGED`, `UNRESOLVED` keep their exact
spelling and their exact subject. A story file may say a thing is `DESIGNED`; it may not say it is
"built" or "ready".

**R8 — The wrong turns are mandatory content, not optional colour.** A story that admits a wrong
turn is more persuasive than one that does not, and this project has genuinely good ones. Three
are named in §2/W4 and all three must appear with the control that caught them. A worker who
cannot verify one reports it and drops it — they do not invent a fourth.

**R9 — The intellectual core is stated in full in exactly one file.** `05-why-ancestry.md` owns
the synchronic/diachronic argument at full depth. Every other file states it in **at most two
sentences** and links there. Six files each trying to be the centrepiece is how a corpus becomes
unreadable, which is the condition this wave exists to fix.

**R10 — Nobody says the hackathon's own words back to it in layer 1.** *"Agentic memory"* as a
self-description is banned above the fold; show the memory instead. The phrase may appear once,
low in a file, where it names the contest.

**R11 — Length is a budget, and each file prints its own word count.** §3 sets the caps. A file
that busts its cap is not finished, it is unedited. Each worker ends its file with a one-line
HTML comment carrying the word count and the command that re-derives it.

**R12 — `still_broken` is a required output.** Every worker returns, in its final message, a
`still_broken` list: any claim it could not verify, any number it found stale, any source it could
not open. Silence there is read as "nothing found", so it must be true.

---

## 2 · THE DECOMPOSITION — 6 workers, 8 files, disjoint

```
docs/story/
  ORIGIN.md              W1  the sixty-second story and the map down
  GLOSSARY.md            W1  the term ledger every other file must obey
  01-the-search.md       W2  eighteen domains, twelve verdicts, six kills
  02-the-choice.md       W3  five finalists, three judges, one dissent
  03-the-audit.md        W4  the audit that found against its own commissioner
  04-wrong-turns.md      W4  three things we got wrong, and what caught them
  05-why-ancestry.md     W5  synchronic vs diachronic — the intellectual core
  DEVPOST-NARRATIVE.md   W6  paste-ready blocks, drop-in, edits nothing
```

**Why this cut.** W2→W3→W4 is the chronology (search, choose, be wrong about it). W5 is the idea
the chronology was in service of, and it is the one thing a competitor cannot also show. W1 is the
door and the vocabulary. W6 is the artefact that actually gets scored, and it is written **from
the same sources as W1–W5, not from their outputs**, so no worker waits on another.

**Dependency: none.** All six run concurrently. W1's `GLOSSARY.md` is *binding on* W2–W6 in
principle, so the glossary's initial term list is fixed here in §4 and W1 may only add to it.

---

## 3 · WORD BUDGETS AND SHAPE

| file | layer-1 opener | whole file | must contain |
|---|---|---|---|
| `ORIGIN.md` | **≤ 400 w**, and it is the first thing on the page | ≤ 1,400 w | the sixty-second story; the map to 01–05; the three scope lines from §0.2 |
| `GLOSSARY.md` | ≤ 120 w | ≤ 1,200 w | every term in §4, each with a plain gloss **and** the file that defines it formally |
| `01-the-search.md` | ≤ 200 w | ≤ 2,000 w | the 18/12/5 funnel; at least six named kills with their reasons |
| `02-the-choice.md` | ≤ 200 w | ≤ 2,000 w | the panel table; the venture dissent; the prior-art casualties |
| `03-the-audit.md` | ≤ 200 w | ≤ 1,600 w | wrong-rubric-not-clock; "unreliable narration"; residual contamination |
| `04-wrong-turns.md` | ≤ 200 w | ≤ 2,000 w | the three wrong turns, each with the control that caught it |
| `05-why-ancestry.md` | ≤ 200 w | ≤ 2,400 w | synchronic vs diachronic; PROJECT / PIN / REFUSE; the dated sweep |
| `DEVPOST-NARRATIVE.md` | n/a | ≤ 1,800 w **of paste blocks** | four blocks, each word-counted, each drop-in |

Layer-1 openers are measured from the first word after the title to the first `##` heading.

---

## 4 · THE TERM LEDGER — fixed here, W1 may extend, nobody may contradict

Each term gets **one** plain-language gloss, and every file uses that gloss at first use.

| term | the gloss every file uses | formal source |
|---|---|---|
| **clause** | one numbered rule inside a procedure — "isolate at zero and verify" | `spec/TRAPPOINT-SPEC.md` |
| **blame ancestry** | the chain of events that caused a rule to say what it says, held as database rows rather than as prose | `hackathon-research/research/05-architecture/commit-dag.md` |
| **synchronic** | checking the world as it is right now | `05-why-ancestry.md` |
| **diachronic** | checking what a decision depends on and what happened to it | `05-why-ancestry.md` |
| **permit-to-work** | the form a supervisor signs before a crew opens a live machine | `verticals/mainline/demo/USE-CASES.md` |
| **obligation** | a debt the system raised against a decision — someone must answer it before the decision can complete | `spec/TRAPPOINT-SPEC.md` §2 |
| **disposition** | a named person's signed answer to one obligation | `spec/TRAPPOINT-SPEC.md` §2 |
| **defeater** | one of the specific reasons the system will accept for setting an obligation aside — each is a question, not a checkbox | `docs/demo/research/r4-story.md` §5 B6 |
| **projection** | a trigger copying a cross-row fact onto the row being written, derived from an authoritative table and never from whoever is writing | `docs/submission/DEVPOST.md` *What it does* |
| **epoch** | a counter that increments whenever a new obligation appears, so a completed decision cannot have one attached afterwards | same |
| **SQLSTATE** | the five-character code a database returns when it refuses — `23514` is a violated CHECK constraint, `P0001` is a trigger raising | PostgreSQL/CockroachDB standard |
| **commit DAG** | a version history shaped like git's, where each version points at what it came from | `hackathon-research/research/05-architecture/commit-dag.md` |
| **MUS** | minimal unsatisfiable subset — the smallest set of reasons that explains a refusal | `docs/demo/research/r4-story.md` §4.2 |
| **canonicalisation** | turning a record into one exact byte string, so two runs on the same data hash identically | `docs/adr/0041-checkpoint-wire-format.md` |
| **EXERCISED / DESIGNED / NOT-AVAILABLE** | we ran it and captured the run / we built it and captured no run / the platform would not let us | `evidence/tool-usage/` |

---

## 5 · THE SOURCE MAP — where each worker reads

**The research repository** (`D:/CoackroachDBxAWS/hackathon-research/`, read-only for this wave):

- `research/00-log.md` — the swarm log. Every phase, every agent, every verdict, every
  session-limit interruption. **The spine of W2 and W3.**
- `research/01-domains/` — 18 domain scans + `00-phase1-synthesis.md`.
- `research/02-validation/` — 12 validations + 8 hypothesis stacks + `00-phase2-synthesis.md`.
- `research/03-feasibility/` — the 5 finalists' architecture-and-market dossiers.
- `research/04-final/` — 5 honest-broker case files, 3 judge sheets, `audit.md`. **W3 and W4.**
- `research/05-architecture/` — `merge-gate-invariant.md`, `diachronic-recall.md`,
  `commit-dag.md`, `clause-identity.md`. **W5.**
- `research/07-novelty/` — 10 cross-domain invention papers.
- `DECISION.md` — the panel-confirmed decision, including its own process critique. **W3, W4.**
- `PLATFORM-THESIS.md` — the deadline-artifact test; flagged in `audit.md` as contaminated.

**This repository:**

- `docs/submission/DEVPOST.md` — the current *Inspiration* / *What it does* blocks. **Read
  before rewriting.** Much of it is right and merely unreadable.
- `docs/demo/research/r4-story.md` — the narrative research: what makes a safety story land, why
  the identifiable-victim lever is closed to us, where the emotional weight actually sits.
- `docs/submission/MUST-NOT-CLAIM.md` — the sentence blacklist. Every worker reads it.
- `docs/HONESTY.md`, `docs/CI-STATE.md`, `docs/regression/GUARD.md`, `docs/STATE-OF-THE-BUILD.md`.
- `docs/leads/ci-runs-cluster-plan.md` §0, `docs/ci/demo-suite-split.md` — the reshaped seed.
- `docs/CI-STATE.md` §10.3 — the lane that did not parse.
- `spec/TRAPPOINT-SPEC.md` §2 — PROJECT / PIN / REFUSE, normative.

---

## 6 · THE SIX BRIEFS, IN OUTLINE

Full briefs go to the workers; this is the lead's record of what each owns.

**W1 · SPINE AND VOCABULARY** — `docs/story/ORIGIN.md`, `docs/story/GLOSSARY.md`.
The door. Sixty seconds, concrete, no jargon: a rule was written because something went wrong; the
person who wrote it left; eighteen months later a database refuses a job that ignores it. Then the
map down to 01–05, and the three scope lines (Agent Skills `DESIGNED`, Bedrock not in the request
path, change request has no admission beat) stated plainly rather than buried. `GLOSSARY.md` is
§4 expanded, and it is what makes "no term before it is defined" enforceable across six files.

**W2 · THE SEARCH** — `docs/story/01-the-search.md`.
Eighteen domains scanned, twelve problems validated against incumbents, **zero came back STRONG**.
Six WEAK, six KILL. The kills are the story: an idea dies because Benchling already shipped it,
because Guidewire ProNavigator *is* the product, because Binti × Anthropic already covers 46 % of
US child welfare, because a cited statistic turned out to be refuted, because the failure was an
incentive failure and not a memory failure at all. Ends where Phase 2 ended: five candidates
assembled from the least-weak verticals.

**W3 · THE CHOICE** — `docs/story/02-the-choice.md`.
Five finalists, three judges under different lenses (venture, hackathon, novelty), weighted
0.40 / 0.35 / 0.25 on the founder's stated priorities. The table. Why MAINLINE won — *the only
candidate top-2 on all three criteria at once*, a **broad win, not a decisive one**. The venture
judge's written dissent. The prior-art casualties, including two candidates' headline claims
falling to Duolingo HLR / FSRS and to Generative Agents / ACT-R. The novelty judge **docking
MAINLINE 9→8 and ranking it first anyway.**

**W4 · WHAT WE GOT WRONG** — `docs/story/03-the-audit.md`, `docs/story/04-wrong-turns.md`.
The audit file is the decision-level wrong turn: an adversarial auditor was commissioned to attack
the consensus and check the orchestrator for bias, and **it found against the orchestrator** —
the earlier #1 was a wrong-rubric artefact, not a deadline artefact; the elevation was *"correct
in outcome, contaminated in process, misdescribed in rationale"*; `DECISION.md` was timestamped
before its own inputs; judging was not blind; and the file's own rationale section should be read
as *"unreliable narration"*. It upheld the outcome anyway, and the reasoning for that is the
persuasive part. The wrong-turns file is the build-level three: **a seed reshaped to match an
application constant** (caught by three independent negative controls, reverted, and now the rule
at the head of every worker brief); **a CI lane that did not parse and therefore appeared on no
red list** (`cluster-lane-bites.yml`, run `31720234309`, 0 s, zero jobs — an absence and a pass are
the same colour of nothing); and **a privilege guard whose own check could never fail**
(`has_function_privilege` returned `true` after a real `REVOKE` while the behavioural truth was
`42501`, found by a planted violation, replaced with `SHOW GRANTS` plus role expansion).

**W5 · WHY ANCESTRY** — `docs/story/05-why-ancestry.md`.
The intellectual core, currently buried. Every shipping permit and document-control system is
**synchronic** — it asks *does the current document satisfy the current rule?* A dated prior-art
sweep across Veeva QualityDocs, MasterControl and Enablon/Cority found no gate conditioned on
ancestry. MAINLINE is **diachronic**: the merge condition is evaluated over what the decision
depends on and what happened to it. Then the mechanism at layer 2 — PROJECT / PIN / REFUSE — and
why this had to be a database refusal rather than a warning banner: *a document shown next to an
Approve button is a UI nag, and a UI nag gets dismissed.*

**W6 · THE DEVPOST NARRATIVE** — `docs/story/DEVPOST-NARRATIVE.md`.
Four paste-ready blocks — *Inspiration (rewritten)*, *The search that got us here*, *What we got
wrong*, *Why ancestry and not state* — each independently readable, each word-counted, each with
a `<!-- PASTE -->` marker in the house style. **This file does not edit `docs/submission/DEVPOST.md`.**
It is a drop-in whose owner decides whether and where it lands.

---

## 7 · DONE

The wave is done when eight files exist under `docs/story/`, every one of them opens with a
passage a non-technical reader can finish, every term in §4 is glossed before use, no verdict word
has been promoted, no file outside `docs/story/` has changed, `git status` shows only additions
under that directory, the suite still reads `1070` / `1069` / `0` / `0`, and every worker has
returned a `still_broken` list.

<!-- word count: `python -c "import sys;print(len(open('docs/submission/story-plan.md',encoding='utf-8').read().split()))"` -->
