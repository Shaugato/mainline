<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# READABILITY VERDICT — two readers, one pass

**VERDICT: NOT READY.**

Not because the writing is bad. Because three specific, fixable things are wrong, and one of
them is the exact failure the founder named. Everything else in this document is the evidence
for that call, and most of it is good news.

The rule this verdict was given: *if Reader A stumbles anywhere, that is NOT READY regardless of
how good Reader B found it.* Reader A stumbles in one place, hard, and it is measurable.

---

## The three blockers, in the order they should be fixed

| # | what is wrong | where | why it blocks |
|---|---|---|---|
| **B1** | Section C of `README.md` is 1,091 words of verification forensics sitting **inside layer 1**, before the mechanism has been explained | `README.md` lines 48–91, worst at 71, 73, 75 | This is the founder's sentence. A reader who understood the problem at 59 seconds is stopped for four and a half minutes by artefact reconciliation |
| **B2** | `qa/live2.json` is **not tracked by git** | cited at `README.md` line 69 and footnote `[^src-cr-absent]` | It is use case two's **only** artefact. A judge who clones the repository gets a dead link where the evidence should be |
| **B3** | `docs/ARCHITECTURE.md` contradicts the answer key on the authored story | `docs/ARCHITECTURE.md` lines 20–21 | It is judge-facing — `DEVPOST.md` line 546 sends judges there for optional requirement 6 — and it dates the same fictional incident differently from `README.md` |

Nothing else found in this pass blocks. The suite did not regress, the gate proof is still
`PROVEN`, and 18 of 21 sampled claims held exactly.

---

## READER A — the intelligent non-specialist

Read `README.md` top to bottom once, at normal speed, no re-reading, nothing looked up.

### How many seconds until I understood the problem? **59.**

The bar was sixty. It is met, and it is met by a real margin of design rather than luck.

| what I was reading | words | seconds at 240 wpm |
|---|---:|---:|
| the story, title → `## What this is` | 236 | **59** |
| what MAINLINE does, → `## See it refuse` | 229 | 57 |
| **the problem, understood** | | **59** |
| **what it does about it, understood** | | **116** |

### The sentence I would say

*"A rule got written because somebody got hurt. Years later the reason has drifted out of reach
— renumbered, moved, the author gone — so the next person sees a number with no story behind it
and undoes it. MAINLINE makes the database refuse to approve that job until a qualified person
answers for the original accident."*

I could write that sentence after one pass. That is the thing that was failing before, and it is
fixed. The opening is concrete before abstract, it uses a person and a consequence, and it does
not reach for a single word of marketing.

### What MAINLINE does about it

The reason a rule exists is attached to the rule. Approving a job is treated like merging a code
change. Before it lands the database looks up what wrote each rule the job leans on, and any past
event nobody has answered for becomes an open question that blocks the approval until a named
person signs an answer. The refusal lives in the database, not in the screen, so turning the
screen off does not turn the refusal off.

I got all of that. **The layering at the top of the page works.**

### Where I stumbled — B1

Then the page hands a non-specialist this, at roughly a quarter of the way in, before anything
has explained how the mechanism works:

> **Line 71** — *"`kernel_procedure_beat: null`. The database's own merge procedure,
> `CALL mainline.merge_change_request(…)`, is not played."*

> **Line 73** — *"The newer file, `qa/live2.json` at 2026-08-16T21:11:57Z, reads `verdict:
> PROVEN` with the three beats above — but the origin's hostname appears nowhere in it, so on its
> own it does not say where it ran."*

> **Line 75** — *"`/operator.html` is byte-for-byte identical to
> `verticals/mainline/apps/console/dist/operator.html` in this tree — the same sha256 content
> hash, `a7a685e8…`."*

Every one of those sentences is **true, careful, and admirable**. Not one of them belongs in the
first sixty seconds. They are layer 3 — a reviewer verifying a claim — and they are sitting in
layer 1's territory.

Measured, so it is arguable rather than asserted:

| | |
|---|---|
| layer 1 as the repository's own gate defines it (title → `## How it works`) | **1,556 words = 6 min 29 s** |
| section C alone (`## See it refuse` → `## How it works`) | **1,091 words = 4 min 33 s** |
| backticked technical tokens inside layer 1 | **96** |
| whole README | **5,368 words = 22 min**, against a judge's ten |

**The repository's own readability gate does not catch this, and the reason is instructive.** The
gate budgets layer 1 at 109 *lines* and layer 1 runs 91, so it passes. But lines 62, 71, 73 and
75 are 116, 122, 189 and 91 words each. The line budget is measuring the author's text editor,
not the reader's clock. *A line budget cannot see a wall of text; a word budget can.*

### Terms used before they were defined

The founder's named list is **fully handled** — I checked every one:

| term | verdict |
|---|---|
| `projection` | glossed at first use, line 102 |
| `blame ancestry` | glossed at first use, line 98 |
| `epoch` | glossed at first use, line 107 |
| `disposition` | glossed at first use, line 36 |
| `obligation` | glossed at first use, line 35 |
| `defeater` | does not appear as prose — only inside the identifier `resolve_defeater_vocabulary`, which the gate deliberately permits |
| `canonicalisation` | does not appear |
| `MUS` | does not appear as a bare acronym; written out as *"the smallest unmet obligation set"* |

The first genuinely undefined term a non-specialist meets is **`SERIALIZABLE`**, at line 145, in
the layer diagram. It is glossed 83 lines later at line 228 — *"concurrent writes behave as if
run one after another"* — which is a good gloss arriving far too late. Also unglossed, all in
layer 2 where the audience is technical and the cost is therefore lower: `ON UPDATE RESTRICT ON
DELETE RESTRICT` (109), `READ COMMITTED` and the bare case name `CF-45` (118), `compare-and-swap`
(120), `pg_get_triggerdef()` and *row-level security* (121), `C-SPANN` (163).

**Sentences that lost me:** README lines 71, 73 and 75, quoted above. Nothing in the story,
nothing in *What this is*, nothing in *How it works*.

### The other judge-facing documents — these pass

Three of the four open with an explicit sixty-second, no-jargon section, and they are good:

* `docs/submission/JUDGE-START.md` — *"Sixty seconds first — no jargon, and nothing to install"*
* `docs/submission/HOW-WE-GOT-HERE.md` — *"Who it is for. The first section is for anyone."*
* `docs/ARCHITECTURE.md` — *"The first section takes about a minute and needs no knowledge of databases."*

`docs/submission/DEVPOST.md` opens with a long meta-preamble about word counts, but that
preamble is explicitly for the founder filling in the form, not for a judge. What the judge
actually reads is the paste block at line 189, **and it is the best writing in the repository** —
concrete, every term defined at first use, evidence moved to a closing italic line, no marketing
voice. It is the model the README's section C should be measured against.

---

## READER B — the judge, ten minutes

### Claims checked: 21 sampled, **18 held exactly**

| # | claim | result |
|---|---|---|
| 1 | `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` | **HELD** — `static_site.py:323`, unmoved |
| 2 | gate proof `PROVEN`, no caveats | **HELD** — `proof-20260816T151248Z.json`, `caveats: []` |
| 3 | refusal `23514 gate_closed_when_issued`, reported | **HELD** — verbatim in the artefact |
| 4 | drift refusal `P0001 mainline.fn_permit_merge_gate`, parsed | **HELD** — verbatim |
| 5 | AWS "six EXERCISED, five DESIGNED, one NOT-AVAILABLE" | **HELD** — census reads exactly `{"EXERCISED": 6, "DESIGNED": 5, "NOT-AVAILABLE": 1}` |
| 6 | **Agent Skills reads DESIGNED** | **HELD** — and `find evidence -ipath "*skill*"` returns nothing, so the verdict is not merely stated, it is *correct* |
| 7 | MCP response cap 10,240 bytes at `limits.py` line 60 | **HELD** — exact line, exact value |
| 8 | conformance 71 declared = 55 `cannot_run` + 6 red + 10 held | **HELD** — exact |
| 9 | `has_function_privilege()` stub | **HELD** — reproducible in `docs/regression/GUARD.md` §*Two things this guard found on its first run* |
| 10 | vector index not chosen at ~5,200 rows | **HELD** — ADR 0002 GT-06/GT-06b and `evidence/aws/ann/explain-unhinted.txt` |
| 11 | `ccloud` 0.6.12 has no headless login | **HELD** — `evidence/ccloud/README.md` line 37, including `CC_API_KEY` being ignored |
| 12–17 | the six story dates against the answer key | **HELD** — all six match `spine.json` exactly |
| 18 | the quoted 2013 line, byte-for-byte | **HELD** — README renders the canonical `→` and `—` |
| 19 | use case 1 artefact | **HELD** — `PROVEN`, `2026-08-15T14:11:35Z`, `base_url` is the live origin, `target_is_local_emulator false`, credentials `none` |
| 20 | use case 2 artefact fields | **HELD** — `PROVEN`, `2026-08-16T21:11:57Z`, `admission_beat` null, `kernel_procedure_beat` null, `42501` |
| 21 | Bedrock not in the demo request path | **HELD** — no Bedrock reference anywhere in `demo-api/src/` |
| — | **`tests/unit/corpus`**, cited by footnote `[^src-story]` | **FAILED** — the path does not exist |
| — | **`qa/live2.json`** tracked | **FAILED** — untracked, not ignored |
| — | **`docs/ARCHITECTURE.md`** story dates | **FAILED** — contradicts the answer key |

Evidence-path sweep of the whole README: **54 of 55 distinct paths resolve.** The one that does
not is `tests/unit/corpus`. The real asserter is
`verticals/mainline/demo/script/validate_shotlist.py`, which does check that the `→` and `—` are
intact. The claim is true; the pointer to it is wrong.

### Is anything stated better than the evidence supports? **No.**

This is the strongest thing about the submission and it should not be lost in the fixes above.

* **Agent Skills reads `DESIGNED`**, with the sentence *"Nothing this repository records has run
  them"*, and an explicit refusal to promote the row to make the table look even. Verified: there
  is no skills evidence.
* Use case two **names its two missing beats rather than filling them in**, and quotes its own
  payload's reason fields for why.
* The README **argues against its own artefact** at line 73 — the older file said `404`, the
  newer says `PROVEN`, both readings are printed with their dates, and the page declines to claim
  use case two beat-for-beat over the public origin because no artefact names the origin. I
  confirmed the hostname genuinely is absent from `qa/live2.json`. That is a project marking its
  own homework down.
* One refusal is **conceded to the application layer** rather than rounded up to the database.
* A sixth CockroachDB finding **was retracted** after checking (see below).

### Does the story explain why this approach rather than another? **Yes.**

`README.md` §*How we got here* does the thing most submissions skip: it names the obvious
alternative — show the reason next to the Approve button — and says *"We did not build that"*,
then gives the reason. An agent writes over whatever surface it can reach, and it does not stop
being an agent when it uses `psql`; a panel can be dismissed and a retrieval can go unread. So
the refusal has to be a property of the write. That is a real argument, and it earns the
architecture rather than asserting it.

### The CockroachDB findings — reproducible, and they read as a colleague

**Register: correct.** Each row names its kind, and one is labelled **`ours`** — *"That was our
bug"* — which is what stops the section reading as blame-shifting. The page also carries a *"What
we would keep unchanged"* paragraph that gives credit specifically rather than politely.

The discipline the brief demanded — *verify every one, do not publish one you cannot reproduce* —
**was actually applied.** Of the seven findings handed to this project, the published set is
five. `crdb_internal`/`system` restriction was **struck** after measurement showed it is a v26.2.5
default everywhere, local single node included, and not a Basic-tier constraint. The 20,000
schema-object ceiling and the untyped `convert_from()` were moved to where they happened. A sixth
finding, the managed MCP endpoint truncating silently at 10,240 bytes, was added. **A team that
retracts one of its own critique items in public is a team whose other six are worth believing.**

I reproduced the two that carry the most weight:

* **`has_function_privilege()`** — `GUARD.md` shows the behavioural control (`42501 … does not
  have EXECUTE privilege on procedure merge_permit`) beside the function answering `true` for the
  probe role, `root`, `admin` and `public`, and shows `has_table_privilege` passing the identical
  control. It names what replacing it cost. This is a genuinely useful bug report.
* **`ccloud` 0.6.12** — `evidence/ccloud/README.md` line 37, verbatim, including that
  `CC_API_KEY` is ignored and the cached session is not readable from a non-interactive shell.

---

## NO REGRESSION

The first run made here was **invalid and is discarded**: a bare `pytest` from the repository root
collects ~7,600 tests, not the baseline's 1,070. The baseline is a named selection, and the
canonical argv is recorded at `scripts/qa/regression_guard.py:225-227`. Re-run with that:

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests tests/deploy \
    --crdb=reuse -q -p no:cacheprovider --timeout=900 --junitxml=<out>
```

Read from the `--junitxml` **root element**, never a terminal tail:

| run | collected | passed | failed | errors | skipped | time |
|---|---:|---:|---:|---:|---:|---:|
| `qa/film.xml` — the named baseline | 1070 | 1069 | 0 | 0 | 1 | — |
| `qa/recert.xml` — independent later run | 1070 | 1069 | 0 | 0 | 1 | — |
| **this pass, 2026-08-18** | **1070** | **1069** | **0** | **0** | **1** | 193.7 s |

**Exit 0. Collection did not move; nothing failed; nothing errored.** The single skip is the
documented one — `test_payload_validates_against_the_json_schema`, *"jsonschema is not a
workspace dependency"* — the same skip recorded in all three earlier runs.

**NO REGRESSION. HELD.**

Other baselines confirmed unmoved:

| baseline | reading |
|---|---|
| `DEFAULT_MAX_RESPONSE_BYTES` | `136 * 1024` at `static_site.py:323` — unmoved |
| gate proof | `PROVEN`, `caveats: []` |
| refusal / drift | `23514 gate_closed_when_issued` · `P0001 mainline.fn_permit_merge_gate` |

---

## The readability gate is itself red

`scripts/submission/check_readme_readability.py` exits **1** on `README.md`. Its `--self-test`
plants one violation per family and **all seven fire**, so the gate is real and not decorative.

| finding | assessment |
|---|---|
| `[BUD]` 36,841 bytes, **10,841 over** the 26,000 ceiling | **TRUE POSITIVE.** 42 % over. This is B1 measured a second way |
| `[LEN]` line 278, a 45-word sentence | **TRUE POSITIVE.** Straightforwardly over the 35-word rule |
| `[LNK]` `qa/live2.json` is not tracked by git | **TRUE POSITIVE, and it is B2** |
| `[GLS]` `vector index` first used with no gloss | **FALSE POSITIVE.** The sentence *"A vector index finds the most similar records without comparing every one"* is a perfectly good gloss. The gate only recognises a copula, a colon, an em dash or an appositive comma, and this gloss uses the verb *finds*. Fix the pattern, not the prose |

---

## What would make this READY

1. **B1 — move section C's forensics below `## How it works`.** Nothing needs to be deleted or
   softened. Lines 71, 73 and 75 keep every word; they change position. Leave in layer 1 only the
   demo address, the two-use-case table, and the three read-only commands. This also fixes `[BUD]`.
2. **B2 — `git add qa/live2.json`** (and `qa/live1.json`, same status). It is not ignored; it was
   simply never added.
3. **B3 — correct `docs/ARCHITECTURE.md` lines 20–21** against
   `verticals/mainline/fixtures/corpus/answer-key/spine.json`: the rule was written
   `2013-08-04` (`strengthen_commit`), not `2013-06-12` (which is `incident`, the fire); the
   author left `2021-07-16` (`author_separated`), not 2017. Render the quote with the canonical
   `→`, not "to".
4. **Minor** — repoint footnote `[^src-story]` from `tests/unit/corpus` to
   `verticals/mainline/demo/script/validate_shotlist.py`; split the 45-word sentence at line 278;
   gloss `SERIALIZABLE` at line 145 instead of 228; teach the `[GLS]` pattern to accept a
   definitional verb.

Items 1–3 are the verdict. Item 4 is tidying.

**One closing note, because it would be unfair to leave it out.** The founder's complaint was
that the writing defeated him after weeks on the project. That complaint has largely been
answered: the problem now lands in 59 seconds, the named jargon is gone or glossed, three of four
judge-facing documents open with a genuine sixty-second section, and the Devpost opener is
excellent. What remains is not a writing problem. It is a **placement** problem in one section of
one file, plus two file-hygiene bugs. That is a much better position than the brief assumed.
