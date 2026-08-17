<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# ARCHITECTURE LEAD — the plan

**Lead:** architecture. **Workers:** 6, paths disjoint. **Date:** 2026-08-17.
**Deliverable:** an architecture document a judge can follow and an engineer can check.

---

## 0. The finding that changes the brief

**There is no `ARCHITECTURE.md` in this repository.** The brief says to keep an existing
3,218-line implementer document and put a readable one in front of it. That document is not
here. `README.md` line 443 says so in the repository's own words:

> Design corpus: `ARCHITECTURE.md` and `BUILD_PLAN.md` live in a companion research
> repository, not this one.

Confirmed by `find . -iname "*ARCHITECT*"` over the tree excluding `.venv/`, `.git/` and the
mypy caches: zero hits. `git ls-files | grep -i arch`: zero hits.

So there is nothing behind which to put a front door, and **nothing is deleted by this wave**.
What exists instead is a precise, dense, scattered layer-3 corpus that is genuinely right and
genuinely unreadable in the order a newcomer meets it:

| Layer-3 source that already exists | Lines | What it is |
|---|---|---|
| `spec/TRAPPOINT-SPEC.md` | 442 | the normative substrate spec: PROJECT · PIN · REFUSE, the five SQLSTATEs, the sixteen invariants |
| `spec/invariants/I01…I16-*.md` | 16 files | one normative statement + mechanism + observable + conformance + **NOT CLAIMED** each |
| `docs/deploy/gate-run-contract.md` | 479 | the four beats, the savepoint discipline, why the demo persists nothing |
| `docs/demo/LIVE-SEMANTICS.md` | 372 | the six memory semantics, each as an anonymous `curl` with the field that proves it |
| `docs/HONESTY.md` | 1,206 | every claim with the artefact that produced it, checked by `tests/release/test_honesty_is_checkable.py` |
| `docs/TOOL-USAGE.md` | 1,751 | every CockroachDB tool and AWS service with a file, a line, and a verdict |
| `docs/CI-STATE.md` | 2,810 | every lane, and which reds report true incompleteness |

The failure the founder named is not that these are wrong. It is that **a reader meets them
first**. This wave writes the two layers in front of them and links down, and touches none of
them.

---

## 1. Rulings

Numbered so a worker can cite one back at me.

**R1 — No fabricated predecessor.** No worker invents an implementer-level `ARCHITECTURE.md`
to satisfy the brief's premise. The new document is created fresh; layer 3 is the corpus in
§0, reached by link. **W1 states this fact on the page**, with the README line that records
it, because a reader who goes looking for `ARCHITECTURE.md` on the strength of a mention
deserves to be told where it went.

**R2 — Shape: one front door, five chapters.** Six workers cannot edit one file. The front
door is `docs/ARCHITECTURE.md`; the chapters are `docs/architecture/0N-*.md`. The front door
carries the whole layer-1 reading — a person, a situation, a consequence — and hands off.

**R3 — Diagram format: ASCII/Unicode inside fenced code blocks.** No Mermaid, no images, no
SVG. There is **zero** Mermaid in this tree today (`grep -rn mermaid docs/ README.md`: no
hits), and `README.md` and `spec/TRAPPOINT-SPEC.md` §5.2 already draw in ASCII. ASCII renders
in GitHub's rendered view, in GitHub's *raw* view, in a terminal pager, and in a printed PDF.
A judge who lands on the raw file must still see the diagram.

**R4 — Exactly four diagrams, one owner each.** The component map (W1), the request path
(W3), the four beats of the gate run (W3), the blame-ancestry walk (W4). W2, W5 and W6 draw
nothing. A fifth diagram is argued for in the worker's returned summary; it is not added
unilaterally. **Decoration is a defect here** — every box must be a thing that exists at a
path.

**R5 — Citation convention, borrowed unchanged from `docs/HONESTY.md`.** A bare number
carries `[src: <path>#<json-pointer>]` into `qa/` or `evidence/`. Digits inside `code spans`
are **names**, not measurements — `v26.2.5`, SQLSTATE `23514`, `2026-08-16`. A claim about
code carries `path:line` or the `grep` that re-derives it. Layer 1 keeps its evidence path;
it moves the citation to the end of the sentence or into a footnote, it does not drop it.

**R6 — Nobody edits outside their owned list.** Not `tests/`, not `README.md`, not
`docs/HONESTY.md`, not `docs/CI-STATE.md`, not `spec/`, not `packages/`, not `verticals/`,
not `infra/`, not `qa/`, not `evidence/`. If the architecture document needs a claim that a
live document contradicts, the worker **reports the contradiction in its return** and writes
the true version on its own page. It does not reconcile by editing the other document.

**R7 — The `LIVE_DOCS` aperture, stated rather than closed.** The docs ratchet
(`tests/deploy/test_cost_model.py`, the `LIVE_DOCS` tuple at lines 96–127; swept by
`tests/deploy/test_docs_are_true.py`) does not include the new pages, and **no worker adds
them** — that file belongs to another lead and editing it risks the 1070/1069/0/0 baseline.
W1 writes one honest paragraph naming the file, the tuple, and the addition that would close
it. An unclosed ratchet named on the page is in register; a silent gap is not.

**R8 — Licence header on every new file**, the `docs/` form:

```
<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
```

**R9 — Length caps, because unreadable *is* the defect.** Front door ≤ 250 lines. Each
chapter ≤ 450 lines. Prose wrapped at ~95 columns, matching the tree. A worker who cannot fit
cuts scope and says so; it does not overflow.

**R10 — Findability is a hard gate.** A worker naming a module, table, function, route, file
or constant must have opened it or grepped it **in this session**, and must carry the path.
A component that cannot be located is **dropped, not softened**. "Roughly", "essentially",
"a component that handles" are all bans.

**R11 — The glossary list is fixed by §3 of this plan.** First use of any listed term in any
chapter links to `docs/architecture/GLOSSARY.md`. A term not on the list may not appear
without a plain-language gloss **in the same sentence**. This is what makes the six chapters
agree without a serialisation dependency between the workers.

**R12 — The CockroachDB critique is not this lead's deliverable.** Only two measured findings
are architectural, and only W6 may state them: `has_function_privilege()` returning `true`
where the behavioural truth was `42501`, and the vector index not being chosen by the
optimizer at demo scale. Each appears only if W6 re-derives it, or is marked verbatim as
*"recorded by this build and not re-measured in this session"* with the document that records
it. No other finding appears anywhere in the architecture document.

**R13 — The not-built list is enumerated, not left to judgement.** §4 below. W6 must name
every item on it or say in its return why an item was dropped.

**R14 — No writes, anywhere.** No worker runs the test suite, `terraform`, `docker`, any AWS
CLI call, any migration, or any `POST` against the demo URL. Read-only `GET` against the
public demo URL is permitted for verification. Nothing else touches the network.

**R15 — Do not commit.** The tree is left for the orchestrator.

---

## 2. The two rules that go in every brief, verbatim

Every worker brief in the structured output repeats these two blocks word for word. They are
the wave's whole reason for existing.

### THE READABILITY BAR

The founder — who has lived inside this project for weeks — read our own explainer and said:
*"Even after going through your briefing, I'm finding a very hard time to understand."* That
is the bar and we are currently failing it. **The fix is layering, not simplifying.** Nothing
becomes vaguer.

- **Layer 1** — a non-technical reader understands the problem, why it matters, and what we
  built, in sixty seconds. **Concrete before abstract.** Not "a diachronic gate over
  ancestry" but "someone got hurt, the lesson was written down, and eighteen months later the
  database refuses a job that ignores it."
- **Layer 2** — a technical reader sees the mechanism: the constraint, the trigger, the
  SQLSTATE, why it cannot be bypassed.
- **Layer 3** — a reviewer verifying a claim reaches the file, the line, the transcript.
  **This layer already exists and must not be weakened.**

- **No term used before it is defined.** Every term gets a plain-language gloss at first use
  or does not appear.
- **No marketing voice.** "Revolutionary", "seamless", "unprecedented", "powerful",
  "cutting-edge" would destroy more credibility than any missing feature. This product's
  entire claim is that it does not overstate.
- **A reader must be able to check you.** Every factual claim keeps its evidence path, even
  in layer 1 — moved to a footnote or the end of the sentence, never dropped.
- **If a sentence cannot be both true and simple, write two sentences.** Never weaken a claim
  to make it readable.

### THE NO-OVERCLAIM RULE

Never claim anything in a better state than it is.

- **Agent Skills is DESIGNED, not exercised.**
- **Bedrock runs in this repository and NOT in the demo request path.**
- **The change-request use case has no admission beat and says so.**
- The custody chain is **9 passed, 0 failed, 7 not checked, of 16**.
- 21 of 30 MAINLINE invariants are pending.
- The reference vertical has two objects no migration creates.

These scopings are why the rest is believable. **Never regress:** baseline 1070 collected /
1069 passed / 0 failed / 0 errors; gate proof `PROVEN`; `DEFAULT_MAX_RESPONSE_BYTES ==
136 * 1024` does not move. **Do not commit.**

---

## 3. The fixed glossary (R11)

W1 writes these into `docs/architecture/GLOSSARY.md` and may sharpen the wording; W2–W6 link
to them and must not contradict them. Every gloss is plain language first.

| Term | Anchor | The gloss |
|---|---|---|
| permit | `#permit` | A written authorisation for one specific dangerous job, at one place, for one window of time. Nobody starts work until it is issued. Table `mainline.permit`. |
| issue / merge | `#merge` | The moment a permit stops being a draft and becomes an authorisation. Here it is one database write, and it is the write the gate defends. |
| obligation / blocking check | `#obligation` | Something that must be settled before the permit may be issued — typically a past incident this job resembles, attached to this permit as a row. Table `mainline.blocking_check`. |
| disposition | `#disposition` | The signed answer to exactly one obligation: a named competent person recording what they did about it. Table `mainline.disposition`. |
| clause | `#clause` | One numbered rule inside a procedure or standard. Table `mainline.clause`. |
| blame / blame edge | `#blame` | A pointer from a clause to the event that caused it to be written, with the quoted evidence digested to a hash. `git blame`, for a safety rule. Table `mainline.blame_edge`; route `GET /v1/clauses/{id}/ancestry`. |
| ancestry | `#ancestry` | The chain of earlier versions and earlier incidents a clause descends from — walked as a graph, not read out of a field. |
| projection | `#projection` | A value the database writes onto a row **by itself**, derived from other rows, overwriting whatever the writer supplied. `mainline.permit.open_blocking` is one. |
| gate | `#gate` | The set of database objects that refuse the issue write: a `CHECK` constraint, a trigger, and a procedure. |
| epoch (`gate_epoch`) | `#epoch` | A counter on the permit that goes up every time a new obligation arrives. A completed issue points at one exact value of it, so a later obligation cannot be quietly attached to a finished permit. |
| SQLSTATE | `#sqlstate` | The five-character code the database returns to say what it did. `00000` accepted · `23514` a `CHECK` refused it · `P0001` a procedure refused it · `40001` undecided, ask again. |
| synchronic / diachronic | `#diachronic` | Synchronic: judged on how the world **is now**. Diachronic: judged on **how it got here**. Every shipping permit system is the first; this one is the second. |
| defeater | `#defeater` | A recorded reason why a past incident does not apply to this job — which must itself be evidence, not an opinion. |
| MUS — minimal unsatisfiable subset | `#mus` | The shortest set of facts that together force the refusal. Drop any one and the write would have gone through. |
| NAA — nearest admissible alternative | `#naa` | The closest version of the request the database would have accepted, where that can be computed. Where it cannot, the answer is `null` with a reason, never a guess. |
| canonicalisation | `#canonicalisation` | Writing a data structure in one fixed byte-for-byte form so two machines that hash it get the same answer. RFC 8785. |
| silence receipt | `#silence` | The record of what a search **declined** to show, with its arithmetic — so "nothing relevant was found" is a checkable claim rather than an absence. |
| TRAPPOINT | `#trappoint` | The substrate: a specification, deterministic SQL templates, and a conformance suite. Apache-2.0. It knows nothing about safety permits. |
| vertical | `#vertical` | A product built on that substrate. MAINLINE is one; `trappoint_ref` is the reference one. |
| conformance suite | `#conformance` | The machine-readable case list whose passing is the **only** meaning of "TRAPPOINT-compliant". |
| custody | `#custody` | The separate machinery for proving recorded evidence has not been altered since — hashes, Merkle trees, cosignatures. |
| projection drift | `#drift` | The projected value disagreeing with what the base rows say. The gate treats it as an attack, not as a rounding error. |
| refusal depth | `#refusal-depth` | How many independent mechanisms would each, on their own, have refused the same illegal write. |
| epoch pin | `#pin` | The composite foreign key `(subject_id, gate_epoch)` with `ON UPDATE RESTRICT` that turns "attaching an obligation to a finished permit" from a policy violation into a referential-integrity violation. |

---

## 4. The enumerated not-built list (R13)

W6 names every one of these or explains the omission in its return.

1. **The reference vertical references two objects nothing creates** —
   `trappoint_ref.clause` and `trappoint_ref.event`, under
   `packages/trappoint-sql/refvertical/sql/`; `trappoint migrate` refuses at
   `0058_blocking_check` with `42P01`. Recorded at `docs/CI-STATE.md:636` §2.1 and `:468`.
   Census: 22 tables created, 12 referenced, 2 with no producer (`docs/CI-STATE.md:674`).
2. **Custody: 9 passed, 0 failed, 7 not checked, of 16** — the seven named: `log_signature`,
   `rfc3161_upper_bound`, `beacon_lower_bound`, `witness_quorum`, `archive_object_lock`,
   `gate_self_attestation`, `webauthn_reverification`
   [src: qa/test-state.json#external_checks.custody_bundle_verification.counts]. Exit code 2.
3. **21 of 30 MAINLINE invariants pending** (`docs/CI-STATE.md`, `ci.yml:702`).
4. **Conformance: 71 declared, 55 could not run at all, 6 red, 10 held**
   (`qa/conformance-census.json`) — a first census, nowhere near a passing suite.
5. **Agent Skills: DESIGNED, not exercised.**
6. **Bedrock executes in this repository and not in the demo request path.**
7. **The change-request use case has no admission beat** — `admission_beat: null`, declared.
8. **`operator.html` is in the tree and not on the deployed origin** — `GET /operator.html`
   returns the console shell byte-for-byte identical to `GET /` (README §"The live demo").
9. **The silence receipt withheld nothing on the seeded run** — `n_silenced: 0`. What is
   demonstrated is the apparatus, not a withholding.
10. **Archival bonds and fixity are design, not routes** — `n_bonded_sev5: 0` and an empty
    `v_fixity_coverage`. A counter reading zero demonstrates nothing.
11. **The offline verifier returns `16 checks | 8 passed | 1 failed | 7 not checked`, exit 1**
    (`VERIFY.md`) — a genuine offline check of the Merkle structure and **not** a verified
    ledger.
12. **Every timing in the demo is a local timing** — single-node CockroachDB in Docker on one
    laptop. The Sydney-Bedrock/Singapore-database hop is unmeasured under load.

**Why leaving these visible is a choice.** Each one of them is a place where the shortest path
to a better-looking submission was to delete the question. §4 of the chapter must say that in
its own words, once, without self-congratulation.

---

## 5. Worker decomposition — 6 workers, disjoint paths

| # | Worker | Owns, literally |
|---|---|---|
| W1 | front door and glossary | `docs/ARCHITECTURE.md`, `docs/architecture/GLOSSARY.md` |
| W2 | the mechanism | `docs/architecture/01-the-mechanism.md` |
| W3 | the request path and the four beats | `docs/architecture/02-the-request-path.md` |
| W4 | memory: blame, ancestry, recall, silence | `docs/architecture/03-memory-and-blame.md` |
| W5 | the map: components, boundaries, chain, cloud | `docs/architecture/04-the-map.md` |
| W6 | what is not built | `docs/architecture/05-what-is-not-built.md` |

No path appears twice. `docs/architecture/` is created by whichever worker gets there first;
`Write` creates parents.

### Cross-references, fixed here so nobody has to negotiate

- W1 links to all five chapters in that order and to `GLOSSARY.md`.
- W2 hands off to W3 at the sentence "and this is what one request does with it".
- W3 hands off to W4 at "where the obligation came from in the first place".
- W4 hands off to W5 at "and every one of those lives somewhere in the tree".
- W5 hands off to W6 at "and here is what is missing from that map".
- W6 links back to `docs/HONESTY.md` and `docs/CI-STATE.md` and ends the document.

Every chapter opens with a one-line **"you are here"** and a link to the front door.

---

## 6. Order of the argument (the thing the founder actually asked for)

The reader meets it in this order and no other:

1. A person, a job, a consequence. *(W1)*
2. What every shipping system does instead, and why it cannot do this. *(W1)*
3. What a permit, an obligation and a disposition are. *(W1 glossary, W2 in prose)*
4. PROJECT · PIN · REFUSE — one mechanism in three parts. *(W2)*
5. Why the database and not the application. *(W2)*
6. One request, four beats, and the beat where the counter is forged. *(W3)*
7. Where the obligation came from: an incident, a clause, a blame edge, a walk. *(W4)*
8. The map: what is where, and the boundary that is simultaneously layer, licence and
   liability. *(W5)*
9. What is not built, and why it is still on the page. *(W6)*
