<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W7 — ASSEMBLY REPORT

**`README.md` assembled 2026-08-17 from the six fragments under `docs/submission/readme-parts/`.
329 lines · 36 841 bytes · layer 1 91 lines.** Three things are not green and each is named
below with the exact remedy and whose file it lives in. Nothing was rewritten to make a check
pass, and no claim was cut.

---

## 1 · The three things an orchestrator has to decide

| # | what | where | who owns the fix |
|---|---|---|---|
| 1 | **`README.md` is 36 841 bytes against the 26 000 ceiling — 10 841 over, 42 %.** The line ceiling is met (329 of 340) and layer 1 is met (91 of 109). | whole file | the plan, or every fragment author — see §4 |
| 2 | One sentence runs 45 words against the 35-word ceiling. | `README.md:278`, from `06-verify.md` | W6 |
| 3 | `vector index` is used first with no gloss the checker can see. | `README.md:155`, from `04-platform.md` | W4 |

**And one that is not a README defect but breaks the README for a judge.**
[`qa/live2.json`](../../../qa/live2.json) is **untracked**. `git ls-files qa/` does not list it;
it exists only on this disk. Section C cites it three times — the use-case-two artefact cell,
the liveness paragraph, and footnote `[^src-cr-absent]` — and it is the *only* evidence the page
offers for use case two. A judge who clones `HEAD` gets a dead link and no artefact. Every other
one of the 30 relative link targets is tracked. **`git add qa/live2.json` before the commit, or
section C's second use case has no evidence at all.**

Two more, reported rather than fixed because the file is not mine:

* **One claim has no home.** `01-opening.claims.md` row 8 marks *"one row per frame"* `MOVED` to
  `docs/demo/JUDGE-90-SECONDS.md`; the grep does not land, and the assembled `README.md` no
  longer links that file at all. Details in §5.
* **One correction was dropped by both its authors.** The superseded sentence *"those three
  fields still hold `UNRESOLVED` because nothing is deployed and no film exists"* is `MOVED` by
  W1 to W2, `DROPPED` by W2 as archaeology bound for the `Corrections` table under **R10**, and
  the `Corrections` table in `06-verify.md` has no such row. Three rows are there; this is not
  one of them.

---

## 2 · What was assembled, and the two changes made in the assembly

Order is the one fixed in `readme-plan.md` §2: SPDX comment block, `# MAINLINE`, then
`01-opening.md`, `02-demo.md`, `03-mechanism.md`, `04-platform.md`, `05-findings.md`,
`06-verify.md`. No fragment file was edited.

**Change one — the duplicated footnote definitions.** `01-opening.md` and `02-demo.md` each
carried verbatim copies of `[^src-fiction]`, `[^src-story]` and `[^src-gate]`; W2 had already
collected them at the end of section C per **R11**, and W1 left a comment asking for exactly
this. W1's three definitions were dropped, W2's kept. GitHub would otherwise have seen each
label defined twice. This is the only text removed in assembly, and it is the only verbatim
cross-fragment duplication that exists — a sentence-level comparison across all fifteen
fragment pairs finds four duplicate sentences and all four are these footnotes.

**Change two — one citation form, no claim touched.** `03-mechanism.md:27` cites a bare `I02`.
`scripts/demo/claim_hygiene.py` rejects that as `HYG-bare-invariant`, because a bare `I\d\d`
outside `spec/` is ambiguous between two invariant catalogues; the rule's own remedy is to name
the path. `README.md` therefore reads `spec/invariants/I02-projected-refusal.md`, which is the
same document the same fragment already cites twice. Without it `check_submission_prose.py`
exits 1 on `README.md`. **W3 should make the same change in the fragment.**

Worker-to-worker HTML comments were stripped. The six `readme-parts/*.md` fragments and their
six ledgers are **a build input**: they are left in place as **R15** requires, and they may be
removed before commit. Nothing else in the tree was touched, and nothing was committed.

---

## 3 · Per-section line and byte counts

| § | rendered heading | lines | plan budget | bytes |
|---|---|---|---|---|
| — + A | SPDX block, `# MAINLINE`, the opening story | 27 | 6 + 30 | 1 475 |
| B | `## What this is` | 20 | 18 | 1 411 |
| C | `## See it refuse — live, with no account` | 44 | 55 | **8 198** |
| D | `## How it works` | 56 | 55 | 5 904 |
| E | `## What it is built on` | 46 | 45 | 4 181 |
| F | `## How we got here, and what we found out about CockroachDB` | 41 | 40 | 5 307 |
| G | `## Check us — clone it and reproduce the refusal` | 46 | 45 | 4 808 |
| H | `## What we are not claiming` | 15 | 22 | 2 061 |
| I | `## Repository, licence, status, corrections` | 35 | 28 | 3 488 |
| | **total** | **329** | **340** | **36 841** |

**Layer 1** — file start through the last footnote definition at the end of section C — is
**91 lines** against the 109 ceiling. Section A's mean sentence is **10.7 words** against the
22-word ceiling, over 21 sentences, longest 18. Across the whole file 213 prose sentences
average 15.5 words and exactly one exceeds 35.

---

## 4 · The byte overage, and the three least load-bearing passages

**The two ceilings are not consistent with each other for prose of this density.** 26 000 bytes
over 340 lines is 76 bytes a line. The assembled file averages 112, because the fragments are
hard-wrapped near 110 columns and section C's paragraphs are single unwrapped lines of 900 to
1 400 bytes each. Meeting 26 000 bytes at 329 lines means removing about 29 % of the words,
which is cutting claims. **Per the brief this worker did not cut, and asks instead.**

The three passages whose removal would cost the least, measured, and **none of them removed**:

| passage | bytes | why it is the cheapest, and what it costs |
|---|---|---|
| `README.md:75`, §C — *"The two operator screens are on the origin now."* | 626 | It is a self-correction, and **R10** names one home for self-corrections: the `Corrections` table at the end of §I. As a table row it is roughly 250 bytes. **Net ≈ 380, no claim lost** — this is a relocation, not a cut, and it needs W2 and W6 to agree. |
| §E `README.md:185–188` and §H `README.md:293`, the residency statement | ≈ 330 + 150 | Both say Sydney inference, Singapore database, no end-to-end Australian residency, hop unmeasured under load. **Not verbatim**, so this worker may not trim it; a fragment author could reduce one to a pointer. **≈ 150 recoverable.** |
| §B `README.md:44–46`, the pointer to `HONESTY.md` and `MUST-NOT-CLAIM.md` | 310 | §H opens by describing both files at greater length. Layer 1 arguably wants the pointer early; that is a judgement, not a measurement. **≈ 200 recoverable.** |

Together those are about 730 bytes of the 10 841. **There is no arrangement of the existing
claims that reaches 26 000.** The choices are: raise the ceiling to about 37 000; drop a named
section; or send fragments back with per-section byte budgets rather than line budgets.

Two passages that look expensive and are **not** candidates. `README.md:73`, the use-case-two
liveness paragraph, is 1 357 bytes and is required in full by **R5** — it publishes both
readings with their dates, which is the point. `README.md:71`, the two absent beats, is required
by **R13**; omitting it is the exact overclaim this project exists to refuse.

---

## 5 · Ledger reconciliation

Every `MOVED` row in the six ledgers was re-checked by re-running the grep the row prints
against the file the row names. **69 rows examined.**

* **55** printed a grep that re-ran and landed exactly as the row says.
* **4** printed a grep that did not land on the first re-run. Two of those cleared on
  inspection — one uses shell alternation (`\|`) that Python reads literally, one is recursive
  over a directory and needs a walk rather than a file read. **Two are downgraded**, below.
* **10** print no grep at all, because the destination is another section of `README.md` rather
  than an external file. Those were verified against the assembled file instead: **8 landed**,
  one is a claim W2 correctly `DROPPED` as falsified, and one is the orphaned correction in §1.

### Two downgrades, and one wrong citation

| ledger row | the row says | what re-running it found | disposition |
|---|---|---|---|
| `01-opening.claims.md:39` row 8 — *"one row per frame — the exact value, the route or file it came from, and the one command that regenerates it"* | `MOVED → readme-plan §2` | `grep -on "one row per frame" docs/demo/JUDGE-90-SECONDS.md` returns nothing. The ledger already says so and flags it to W2. W2 did not take it, and the assembled `README.md` does not link `docs/demo/JUDGE-90-SECONDS.md` anywhere. | **MOVED → DROPPED.** The front door no longer points at the per-frame number table. Orchestrator decision: add the pointer to §C, or accept the drop. |
| `05-findings.claims.md:56` — the `synchronic` / `diachronic` sentence | `MOVED` to `docs/submission/readme-parts/03-mechanism.md` | The destination is a fragment written in this same wave, not a pre-existing file. **R2** requires *a named existing file*, and §2 above records that `readme-parts/` is a build input which may be removed. | **MOVED → KEPT.** No claim is lost: both terms are in the assembled `README.md` §D, once each, which is what **R4** allows. |
| `06-verify.claims.md:101` row 53 — *"21 of 30 invariants pending"* | `MOVED`, citing `VIDEO-KIT.md:664`, `PUBLIC-FLIP-CHECKLIST.md:357`, `architecture-plan.md:170,226` | Re-run recursively: `docs/submission/architecture-plan.md` and `docs/submission/PUBLIC-FLIP-CHECKLIST.md` carry the string. **`docs/submission/VIDEO-KIT.md` does not** — the file exists and the string is absent. | **MOVED stands**, on two of the three named destinations. One cited destination is wrong and should be struck from the ledger. |

Two rows the reconciler first flagged and then cleared, recorded so the clearing is visible:
`01-opening.claims.md:88` prints `grep -on "synchronic\|diachronic"`, whose `\|` is shell
alternation and not Python's — the pattern does land in `docs/submission/DEVPOST.md`. Row 53's
grep is recursive over a directory, which needs a directory walk rather than a file read.

### Every DROPPED claim, so the orchestrator can veto

| # | ledger | the claim dropped | stated reason | this worker's note |
|---|---|---|---|---|
| 1 | `01-opening` r26 | the clause was written **2013-06-12** | factually wrong — `2013-06-12` is the incident date, `spine.json#dates` gives `strengthen_commit 2013-08-04` | correct; §A uses both real dates |
| 2 | `01-opening` r27 | the author **left the company in 2017** | factually wrong — every corpus artefact says `2021-07-16`; 2017 appears nowhere | correct; §A says 2021 |
| 3 | `01-opening` r28 | a disposition against a **thirteen-year-old death** | factually wrong and an overclaim inside the fiction — `severity_actual: 4`, nobody dies | correct; §A says two contractors burned |
| 4 | `02-demo` r3 | *"`SUBMISSION.json` still holds the sentinel"* said of `demo_url` | falsified — the file holds the origin, `notes.demo_url` opens `RESOLVED 2026-08-16` | **verified by reading the file**: `demo_url` is the origin, `video_url` is still `UNRESOLVED` |
| 5 | `02-demo` r12 | *"those three fields still hold `UNRESOLVED` because nothing is deployed and no film exists"* | archaeology, bound for the `Corrections` table under **R10** | **the `Corrections` table has no such row.** This one is genuinely gone — see §1 |
| 6 | `02-demo` r17 | *"a submission checklist that looks finished before it is finished…"* | budget, and it is rhetoric decorating a kept fact | agreed, nothing checkable lost |
| 7 | `02-demo` r24 | *"the screens ship when the orchestrator redeploys"* | falsified by the 2026-08-17 re-check | correct, and the replacement claims only that the entry point is served |
| 8 | `03-mechanism` r2.9 | *"Nobody quietly weakens the gate that prevents quietly weakening controls."* | asserts prevention where the mechanism gives evidence | agreed — this is the project's own discipline working |
| 9 | `03-mechanism` r4.8 | the `bonded_fatalities_all_blocking` `CHECK` and its `I13` citation | one of six named `CHECK`s the demo does not exercise; budget | agreed |
| 10 | `04-platform` | the struck *"Bedrock genuinely executes, and nothing else on AWS does"* | **R10** archaeology → `Corrections` | **verified present** as a `Corrections` row in §I |
| 11 | `04-platform` | the gate-vs-census AWS count reconciliation (`10`/`5` against `12`/`6`) | lives in full at `docs/TOOL-USAGE.md:1048–1083` | not re-verified line-for-line; the file exists and carries the section |
| 12 | `05-findings` d | `crdb_internal` / `system` restricted **on Basic tier** | the tier framing is wrong — a **version default**, refused on the local single node too | agreed, and the correction is published in §F. This is the wave's best catch |
| 13 | `05-findings` g | `gc.ttlseconds` **defaults** to 4500 on Basic | no artefact reads it on an unconfigured Basic database; 4500 is *our* `CONFIGURE ZONE` value | agreed. **W5 flags that the same page still asserts it elsewhere, and the flag is right: `README.md:258` (§G, W6's) reads *"the value CockroachDB Cloud Basic enforces"*.** W6 to reconcile |
| 14 | `05-findings` e | the 20 000 schema-object cap surfaces as *unrelated* failures | the briefed wording overstates it: the error names its own setting; it is our own scratch databases that filled the node | agreed; named with its citation in §F's closing line |
| 15 | `05-findings` f | `convert_from()` local-versus-Cloud divergence | the divergence half is a schema difference of ours, not an engine difference | agreed; the typing half is named in §F's closing line |
| 16 | `06-verify` r9 | the `dest + 1 + 141` column and the `7 437 dirty paths` count | derivable from the two kept numbers | agreed |
| 17 | `06-verify` r15 | the fresh-venv traceback above its last line | the `ModuleNotFoundError` line is kept | agreed |
| 18 | `06-verify` r46 | `capture_tool_evidence.py --check` as a re-derivation command | `docs/TOOL-USAGE.md` owns that census | agreed |
| 19 | `06-verify` r54 | the parenthetical that `GET /v1/health` now answers `ok: true` | §C owns live-demo status under **R5** | correct — §C carries it, with the 2026-08-17 timestamp |

---

## 6 · The mechanical invariants

| # | invariant | result |
|---|---|---|
| 1 | `git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git` in a copy-paste block — `judge_dry_run.py:805` | **present, verbatim** |
| 2 | the four documented commands — `judge_dry_run.py:834,917` | **`just doctor`, `just setup`, `just up`, `just prove` all present.** The grep at `documented_commands_block` tests the left column only; both columns are present. **One discrepancy to record:** `judge_dry_run.py:133–137` pairs `just setup` with `uv sync --all-packages`, and `README.md` gives `python -m pip install -e packages/trappoint-migrate`. Not a grep failure — the fallback is what the dry run *runs*, not what it greps — but the two disagree and W6 or the script should settle which is the documented plain form |
| 3 | `python -m pytest tests/boundary/test_ci_greps.py -q` | **37 passed, 1 failed — and the failure is not `README.md`'s.** `scan_must_not_claim` examined 46 files and found 2 violations, both `GREP-CLAIM-UPSTREAM-SKILLS-MERGE`, in `docs/submission/census/crdb-four-tools.md:630` and `docs/submission/feature-census.md:948`. Both files are **unmodified at HEAD** (`git status --porcelain` lists only `README.md` as modified), so this is pre-existing and owned by another lead. `README.md` contributes **zero** violations and `GREP-CLAIM-NO-README` did not fire |
| 4 | `check_submission_prose.py` | **clean.** `submission prose OK` for `SUB-01`…`SUB-09`, and `claim hygiene OK` over its own 23-file surface. It was **not** clean before the `I02` fixup in §2 |
| 5 | the SPDX block is the first four lines | **yes**, byte-identical to the previous `README.md` |
| 6 | every relative link resolves | **on disk, yes** — the `LNK` family in `check_readme_readability.py` walks every `[label](target)`, skips `http:`, `mailto:` and `#`, strips any `#anchor`, and resolves against both the file's directory and the repository root. Zero findings over 30 distinct targets. **In a clone, 29 of 30** — `qa/live2.json` is untracked, see §1 |

Also checked, not required: six footnote labels, six definitions, no label defined twice and
none referenced without a definition. And every relative link target was re-checked against
`git ls-files`, which is how the `qa/live2.json` gap was found — resolving on the author's disk
and resolving in the tree a judge clones are two different questions, and only the second one
matters to a reader.

---

## 7 · The readability gate

`scripts/submission/check_readme_readability.py`, standard library only, no network. Seven
families: `MKT` marketing words · `JRG` banned jargon and the two permitted-once terms ·
`GLS` glossed-term discipline · `LEN` sentence length · `L1` the layer-1 line budget ·
`BUD` the file's line and byte ceilings · `LNK` unresolved relative links.

**`--self-test` exits 0.** It plants violations in a temporary tree and requires every family
to go red; it currently fires **15 findings across all seven families**, including each `JRG`
sub-check separately — `canonicalisation`, `defeater`, `archival bond`, `fixity`, bare `MUS`,
`C-SPANN` outside a table row, and `diachronic` and `synchronic` used twice. Writing the
self-test found two real defects in the checker: the permitted-once check counted *blocks*
rather than occurrences, so two uses in one paragraph went unseen; and the budget check
measured a comment-stripped copy of the file rather than the file on disk, under-reporting by
94 bytes and three lines.

**On `README.md` it exits 1, with three findings**, all listed in §1 and none of them
fixable by this worker without rewriting somebody else's prose:

```
[BUD] README.md:329: 36841 bytes, 10841 over
[GLS] README.md:155: 'vector index' first used with no gloss
[LEN] README.md:278: 45 words
```

Two implementation decisions worth arguing with, both in the file's docstring. *"Line" means
the logical line*: the file is hard-wrapped near 110 columns, so a physical line boundary is a
fact about an editor and not about prose; every family runs over blocks, and `GLS` narrows to
the sentence of first use. *The ban is on the word as prose, not inside an identifier*:
`defeater` is banned, `resolve_defeater_vocabulary` is a name a reader can grep for, and Python
word boundaries treat `_` as a word character, so the identifier does not match and the bare
word does.

**`GLS` on `vector index` is a heuristic miss, and it is reported rather than tuned away.** The
sentence is `README.md:155`, from `04-platform.md`: *"A **vector index** finds the most similar
records without comparing every one."* That **is** a gloss — but by a defining verb, and the
marker set is em dash, colon, copula, `means`, `we call`, or an appositive comma. Widening the
set until this passes would make the family assert nothing. The one-word remedy, **W4's to
make**: *"A **vector index** is a way to find the most similar records without comparing every
one."*

---

## 8 · The cold read

**Restated using only `README.md` lines 1–91, everything above `## How it works`.**

**What problem does this solve?** A safety rule outlives the reason it was written. The reason
gets recorded once — a line in a revision history, an incident number — and then the document
is retypeset, renumbered, moved into a different standard, and the person who wrote it leaves.
When somebody later proposes undoing the rule, the reason is not on their screen. Permit
systems check whether the world is safe *right now*. None of them can answer *why is this limit
here*.

**Who has it?** The person issuing a permit to work at an industrial site, and the engineer
changing a written procedure. Both are named on the page: a site supervisor and a safety
engineer, each with the screen they use.

**Why does it matter?** Because the change gets approved. In the page's story a compressor seal
fire burns two contractors, the alarm is lowered from 150 °C to 135 °C for that reason, and
years later somebody with good reasons — the manufacturer specifies 150, the alarm trips on hot
afternoons — proposes putting it back. Every permit system on the market approves that change.
MAINLINE makes the database refuse the permit until a named person signs an answer to the open
question. Not a banner. A precondition.

**What can I click?** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
in any browser — no account, no login, no credential. Two screens: `/operator.html#/permit` and
`/operator.html#/change`.

### Could a reader who has never heard of a `CHECK` constraint do the same?

**For sections A and B — lines 8 to 46 — yes, without reservation.** Section A is entirely
story and uses no technical term at all. Section B introduces exactly three, and glosses each
where it stands: **blame** — *"who wrote this line, and why"*; **obligation** — *"one open
question attached to that permit"*; **disposition** — *"a signed answer to that one question"*.
That is the sixty seconds, and it holds.

**For section C — lines 48 to 91 — not everywhere.** Three sentences use an identifier as if it
had been defined. Named, quoted, and **not rewritten**:

1. **`README.md:71`, the primary failure.** *"**Use case two is short two beats, and names both
   rather than filling them in.** `admission_beat: null`."* `beat` was glossed one paragraph
   earlier, but `admission_beat` and `kernel_procedure_beat` arrive as bare field names, and
   *"is short two beats"* is an idiom a non-native reader will not parse as *"is missing two
   beats"*. **W2's sentence, W2's to fix.**
2. **`README.md:73`.** *"A route that was never deployed is not a gate that failed to refuse…"*
   `route` is never glossed in layer 1, and the sentence turns on the difference between two
   things a lay reader has no way to tell apart. The distinction is the honest and important
   one; the wording assumes a web developer.
3. **`README.md:68`, a table cell rather than a sentence.** `23514`, `gate_closed_when_issued`,
   `P0001` and `mainline.fn_permit_merge_gate` arrive with only the *category* glossed — the
   preceding paragraph says what a SQLSTATE is and that `00000` means the write went through,
   but not what `23514` or `P0001` mean. A reader can see the shape of the result without being
   able to read it.

**The honest summary: a stranger gets the problem, the person, the stake and the link from the
first 46 lines. Section C is where layer 1 starts asking for a reader who has seen an HTTP
route and a database error code.** That is a smaller gap than the one the founder named, and it
is a real one.
