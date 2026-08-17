<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# COMPLETENESS LEDGER — every new claim this wave made, re-derived by somebody who did not write it

**Auditor:** W6 · **Audit closed:** `2026-08-18T03:28:33+10:00` · repo `D:/CoackroachDBxAWS/mainline`,
`master`, working tree uncommitted.

**The rule this page runs on.** *A worker's word is not evidence.* For every new factual claim
made by W1–W5 in this wave, this page names the artefact or route that produces it, records the
value **re-derived first-hand by this auditor**, and gives the one command a sceptic runs to prove
the sentence wrong. Where a claim has no falsifying command it is **not softened** — it is listed
in §2 REFUSED, naming the worker and the sentence, and handed back.

**This page edits no file but itself and `HOW-WE-GOT-HERE.md`.** Where a defect was found in
somebody else's file it is written out in full here, with the exact replacement text, and left for
the orchestrator. §7 discloses the one side-effect this audit itself had on the tree.

**This page does not touch `docs/submission/EXTRA-CREDIT-CLAIMS.md`**, which is the previous
wave's dated record and stands.

---

## 0 · The state of the board at audit close

Five workers were briefed. **Three finished, two were still running when this audit closed**, and
that is recorded rather than waited out, because this page is worth more accurate than complete.

| worker | file it owns | at audit close |
|---|---|---|
| **W1** | `docs/submission/DEVPOST.md` | **PRESENT** — `+56 / -0` |
| **W2** | `docs/upstream/COCKROACHDB-FINDINGS.md` | **PRESENT** — new file, 42 209 bytes |
| **W3** | `docs/submission/JUDGE-START.md` | **PRESENT** — `+263 / -0` |
| **W3** | `docs/submission/FIRST-FIVE-MINUTES.md` | **PRESENT** — `+40 / -0` |
| **W4** | `scripts/submission/check_doc_links.py` | **PRESENT** — new file |
| **W4** | `docs/submission/MECHANICAL-SWEEP.md` | **PRESENT** — landed `03:35`, audited at §1.6 |
| **W5** | `docs/submission/diagrams/architecture.svg` | **PRESENT** — new file |
| **W5** | `docs/submission/diagrams/story.svg` | **PRESENT** — landed `03:33`, audited at §1.7 |
| **W5** | `docs/submission/DIAGRAMS.md` | **ABSENT AT AUDIT CLOSE** — §8 |

**Audit close was extended once**, from `03:28` to `03:35`, because W4's and W5's remaining files
landed while §1 was being written. **Nothing already audited was re-opened**; §1.6 and §1.7 are
additions.

Re-derive this table:

```bash
git diff --numstat -- docs/submission/DEVPOST.md docs/submission/JUDGE-START.md \
  docs/submission/FIRST-FIVE-MINUTES.md
ls docs/submission/MECHANICAL-SWEEP.md docs/submission/DIAGRAMS.md \
   docs/submission/diagrams/ docs/upstream/COCKROACHDB-FINDINGS.md
```

---

## 1 · THE CLAIM LEDGER

**How to read a row.** *Claim* is what the worker's file says. *Re-derived* is the value this
auditor obtained by running the command in the *Falsified by* column, on this machine, at audit
time. **A row whose two middle columns disagree is a defect, and there are none in this table** —
the defects are in §2.

### 1.1 · W1 — `docs/submission/DEVPOST.md`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 1 | The wave's insert is additive: no existing paste block was rewritten, shortened or re-ordered (ruling R-A / R-B) | `56` insertions, **`0` deletions** | `git diff --numstat -- docs/submission/DEVPOST.md` — a non-zero second field falsifies it |
| 2 | The worked example's dates are transcribed, not invented: seal fire `2013-06-12`, setpoint lowered `2013-08-04`, procedure retypeset `2016`, re-numbered again `2019`, author leaves `2021` | `incident 2013-06-12`, `strengthen_commit 2013-08-04`, `retypeset 2016-11-21`, `split 2019-02-19`, `author_separated 2021-07-16` | `python -c "import json;print(json.load(open('verticals/mainline/fixtures/corpus/answer-key/spine.json'))['dates'])"` |
| 3 | The rule is renumbered `7.3` → `5.2.1` → `9.2.1` | `label_2011 = 7.3`, `label_2016 = 5.2.1`, `label_2019 = 9.2.1` | `python -c "import json;d=json.load(open('verticals/mainline/fixtures/corpus/answer-key/spine.json'));print(d['label_2011'],d['label_2016'],d['label_2019'])"` |
| 4 | Today's proposal is to put the alarm back to `150 °C` | `proposed_2026[0]`: `setpoint_from 135.0`, `setpoint_to 150.0`, `proposed_on 2026-07-28`, `control_delta weaken` | same file, key `proposed_2026` |
| 5 | The quoted 2013 change line is byte-equal across four files | The string is present verbatim at `CAMERA-STRINGS.yaml:64`, and the file's own header (`:10-13`) names the four files and the test that asserts it (`tests/unit/corpus`, assertion **CA**). **The assertion itself was read, not executed** — see §8. | `grep -n commit_message_2013 verticals/mainline/demo/script/CAMERA-STRINGS.yaml` |
| 6 | The invented incident is severity `4` | `projected_onto_the_check: 4` | `python -c "import json;print(json.load(open('evidence/gate-refusal/proof-20260810T054407Z.json'))['projection']['severity'])"` |
| 7 | **C-SPANN** is CockroachDB's vector index type | `docs/TOOL-USAGE.md:179` — *"Distributed vector index — C-SPANN `VECTOR INDEX`"* | `grep -n "C-SPANN" docs/TOOL-USAGE.md` |
| 8 | The fuller vocabulary is `docs/architecture/GLOSSARY.md` and no gloss here may contradict one there | the file exists (another lead's wave) | `ls docs/architecture/GLOSSARY.md` |
| 9 | The block discloses the corpus is authored **before** it narrates the injury | first sentence of the paste block is *"Read the story below knowing it is invented"*; the burn sentence is third | read `docs/submission/DEVPOST.md` at the `<!-- PASTE -->` under *Read this first* |

**On row 9, and why it is in this table rather than §2.** `docs/submission/MUST-NOT-CLAIM.md` §3
forbids *"Two contractors were burned at this site."* **spoken as fact.** W1's block is not
spoken as fact: the invention is declared in the sentence above it, and the closing footnote
repeats it. **This is the correct handling of that corpus and it is the standard §2.1 measures
another worker against.**

### 1.2 · W2 — `docs/upstream/COCKROACHDB-FINDINGS.md`

**This file was audited hardest, because it is the one a CockroachDB engineer will read most
carefully.** Its two headline findings were re-derived by running W2's own reproduction script
end to end on this machine.

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 10 | **F01** — asked whether a *named* role may `EXECUTE` a routine, `has_function_privilege` answers `true` after a real `REVOKE` that the engine then enforces | verdict **`STUB-CONFIRMED`**, exit `0`, run by W6 at audit time on CockroachDB CCL `v26.2.5` local | `.venv/Scripts/python.exe scripts/upstream/repro_privileges.py` — a verdict other than `STUB-CONFIRMED` falsifies it |
| 11 | **F01 narrowed** — only the **role-named** three-argument form is blind; the two-argument *"may I"* form answers correctly | the script's own table reproduced both forms in the same session; the run's summary printed the same split | same command |
| 12 | **F01 has a negative control** — `has_table_privilege` gets the identical question right on the same database in the same session | `has_table_privilege negative control tracks behaviour: True` | same command — a `False` here falsifies the whole finding, because it would mean the probe, not the built-in, is broken |
| 13 | **F02** — `SHOW GRANTS` and `information_schema.routines` spell one routine two different ways and neither carries the other's spelling | verdict **`SPELLINGS-DIFFER`**: `merge_permit(uuid, bytea, text, text, jsonb, bytea, int2, bytea)` versus `merge_permit`; the naive comparison reported `matched: False` **for a procedure the probe had demonstrably just run** | same command |
| 14 | **F03 is STRUCK, not softened** — the vector-index claim was refuted twice and is published as refuted | the section headed *"Reported, not reproduced on this machine"* exists and carries F03 under *"We do not report this as unreproduced. We report it as refuted"* | `grep -n "Reported, not reproduced" docs/upstream/COCKROACHDB-FINDINGS.md` — its absence falsifies ruling R-D compliance |
| 15 | **Six of the seven findings the wave was briefed with were narrowed or withdrawn on re-measurement** | the withdrawal table lists six: `has_function_privilege` scope, `crdb_internal` tier attribution, the 20 000-object error quality, `gc.ttlseconds` default (**withdrawn completely**), `convert_from` return type (**withdrawn**), and the local-versus-Cloud difference (**withdrawn**) | read the table under *"Sentences from our own earlier notes that did not survive re-measurement"* |
| 16 | No finding on this page was measured against CockroachDB Cloud in this wave | no Cloud artefact appears in `git status`; every Cloud reading in the file is dated and labelled archived | `git status --porcelain evidence/` — a new Cloud transcript would falsify it |

**Row 15 is the single most important line in this ledger.** The wave brief listed seven measured
CockroachDB findings as settled fact. After re-measurement **only F02 survives as briefed.** A
page that had published the seven as given would have handed a CockroachDB engineer five claims
they could disprove in an afternoon.

### 1.3 · W3 — `docs/submission/JUDGE-START.md`, `docs/submission/FIRST-FIVE-MINUTES.md`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 17 | Both inserts are additive | `263 / 0` and `40 / 0` | `git diff --numstat -- docs/submission/JUDGE-START.md docs/submission/FIRST-FIVE-MINUTES.md` |
| 18 | *"Seven lanes have a standing negative control after this wave, against three before it"*, at line 55, and the next sentence names the eight that still have none | line **55** matches exactly; line 56 reads *"Eight of the eighteen workflows still have none"* | `grep -n "standing negative control" docs/ci/anti-vacuity.md` |
| 19 | Mutation ratchet: undamaged Wilson lower bound `0.909774`, with one rule off `0.802164` | both literals present at `docs/ci/anti-vacuity.md:645-646` and again at `:685-686` | `grep -n "wilson_lower" docs/ci/anti-vacuity.md` |
| 20 | The ratchet *"is still never a gate"* | the sentence is at `docs/ci/anti-vacuity.md:672` | `grep -n "never a gate" docs/ci/anti-vacuity.md` |
| 21 | The `42501` probe transcript is verbatim from `GUARD.md` line 378 | line **378** is exactly `CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit` | `sed -n '378p' docs/regression/GUARD.md` |
| 22 | `GUARD.md` still carries the **wider** wording at lines 381–382, reported rather than edited | lines 381–382 read *"for `public`, for everybody"* — the over-broad claim W2 retracted | `sed -n '381,382p' docs/regression/GUARD.md` |
| 23 | `HONESTY.md`'s `## NOT YET BUILT` runs from line 557 to 1109 | `## NOT YET BUILT` is at **557**; the next `## ` heading is at **1111** | `grep -n "^## " docs/HONESTY.md` |
| 24 | `CI-STATE.md`'s board reads `20 workflows  8 GREEN  12 RED  0 never-run` | verbatim at `docs/CI-STATE.md:14` | `grep -n "20 workflows" docs/CI-STATE.md` |
| 25 | The published one-liner prints the NAA description, then `None not_computable` | **ran it.** Printed `1 obligation(s) remain open on this subject; disposing of exactly those restores admissibility` then `None not_computable` | the command as printed in `JUDGE-START.md` item 4 |
| 26 | The published one-liner prints the projected severity and `10 of 10 assertions held` | **ran it.** Printed `{'supplied_by_this_script': 0, 'projected_onto_the_check': 4, 'virulence_projected': 'blood_major', 'closure_gen_projected': 0}` then `10 of 10 assertions held` | the command as printed in `JUDGE-START.md` item 5 |
| 27 | `cr-gate-live.json`'s top-level verdict is `UNANSWERABLE` and the `gate_run` block inside it is a separate `200` | `verdict UNANSWERABLE`, `gate_run.status 200` | `python -c "import json;d=json.load(open('evidence/deploy/cr-gate-live.json'));print(d['verdict'],d['gate_run']['status'])"` |
| 28 | The block promotes nothing: Agent Skills designed-not-exercised, Bedrock not in the demo request path, change request has no admission beat, Managed MCP `15` of `16` at `DIVERGED — KNOWN GAP` | all four hold — see §3 | §3 |

### 1.4 · W4 — `scripts/submission/check_doc_links.py`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 29 | Every relative link and every cited evidence path in the six judge-facing documents resolves | **ran it twice.** At `03:27`: `128` links, `226` citations. Re-run at `03:36`, after W1's and W3's inserts had fully landed: **`140` links, `226` citations**, `1` external not fetched, `1` declared-absent path named, `OK`, exit `0` — matching W4's own headline exactly | `python scripts/submission/check_doc_links.py` |
| 30 | `--self-test` proves the checker can go red **and names the planted defect**, and proves it does not simply refuse everything | **ran it.** `A1` control exits `0`; `A2` planted exits `1`; `A3` and `A4` name `nope/PLANTED-MISSING-DOC.md` and `evidence/nope/PLANTED-MISSING-EVIDENCE.json` literally. All four `PASS`, exit `0` | `python scripts/submission/check_doc_links.py --self-test` |
| 31 | The one suppression is two-way: a `DECLARED_ABSENT` path that *appears* is reported `STALE` and fails the run | the mechanism is declared and printed on every run; **the `STALE` branch itself was not observed firing** — no plant exists for it. Recorded as unproven rather than counted as a pass. | producing `evidence/deploy/cloud-gate-run.json` and re-running would falsify it |
| 32 | The checker is wired into no CI workflow (ruling R-H) | `0` occurrences under `.github/`, and `0` workflow files modified in this wave | `grep -rn check_doc_links .github/ \| wc -l` and `git status --porcelain .github/` |

### 1.5 · W5 — `docs/submission/diagrams/architecture.svg`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 33 | The diagram contains all three things contest requirement 6 names — CockroachDB, AWS services, and the agent | text nodes name `CockroachDB` (11), `Lambda` (6), `Bedrock` (6), `IAM` (1), `CloudWatch` (2), `Function URL` (2), and `agent`/`Agent` (5). **This is the substance the old three-box README diagram lacked.** | `python -c "import re;s=open('docs/submission/diagrams/architecture.svg',encoding='utf-8').read();print([t for t in ('CockroachDB','Lambda','Bedrock','Agent') if t in s])"` |
| 34 | The SVG is self-contained — no external font, image or script | `0` non-fragment `href`/`src`/`xlink:href` attributes | `python -c "import re;print(re.findall(r'(?:xlink:href\|href\|src)=\"(?!#)[^\"]*\"',open('docs/submission/diagrams/architecture.svg',encoding='utf-8').read()))"` |
| 35 | It carries an inline SPDX header | present | `head -6 docs/submission/diagrams/architecture.svg` |

### 1.6 · W4 — `docs/submission/MECHANICAL-SWEEP.md`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 36 | Check 3 — `140` links, `0` broken | **ran the checker.** `140` relative links, `0` broken, exit `0` | `python scripts/submission/check_doc_links.py` |
| 37 | Check 5 — `226` citations, `0` broken, `1` absence declared on purpose | **ran the checker.** `226` evidence/qa citations checked, `0` broken, `evidence/deploy/cloud-gate-run.json` named as the one declared absence | same command |
| 38 | The counts are a reading at an instant, not a constant — an earlier run of the same tool over the same six files counted `112` and `213` | **independently confirmed by accident.** This auditor's own first run, mid-wave, read `128` and `226` — a **third** value, between W4's two. The six documents were being written while all three runs happened | run the checker twice with a worker's insert in between |
| 39 | The checker is in none of the `20` workflow files under `.github/workflows/` | `0` matches under `.github/`; `20` workflow files present | `grep -rn check_doc_links .github/ \| wc -l` and `ls .github/workflows/ \| wc -l` |

**Row 38 is the one worth reading.** Three runs of one tool over one set of files produced three
different counts inside ninety minutes, and **W4's page already says so before a reader can catch
it out.** That is the correct handling of a moving number, and it is the same discipline
`DEVPOST.md` applies to every superseded reading it keeps.

**One benign staleness, caused partly by this page.** W4's §3c prints a `grep -rl "check_doc_links"`
naming two files. There are now **four**: the ruling, the script, `MECHANICAL-SWEEP.md` itself, and
this ledger. **The load-bearing half of the claim — no match anywhere under `.github/` — still
holds**, and that is the half the ruling is about. Falsify with the grep as W4 prints it.

### 1.7 · W5 — `docs/submission/diagrams/story.svg`

| # | claim | re-derived by W6 | falsified by |
|---|---|---|---|
| 40 | Four panels a non-technical reader finishes, using no technical term | extracted every visible text node: `2013`/`2013`/`2021`/`2026`, plain English throughout. **No SQLSTATE, no constraint name, no `merge`, no `obligation`, no `disposition`** appears anywhere in the visible text | `python -c "import re;s=re.sub(r'<!--.*?-->','',open('docs/submission/diagrams/story.svg',encoding='utf-8').read(),flags=re.S);print(re.findall(r'<(?:text\|tspan)[^>]*>([^<]*)<',s))"` |
| 41 | Every date and number is transcribed from the corpus | `2013` fire, `2013` fix `150 → 135`, `2021` author leaves, `2026` proposal back to `150` — all four match `spine.json` rows 2–4 of §1.1 | `python -c "import json;print(json.load(open('verticals/mainline/fixtures/corpus/answer-key/spine.json'))['dates'])"` |
| 42 | The visible diagram discloses that the story is authored | the closing caption reads *"The people, the plant and the incident number in this story are invented. The refusal is not: it happens on a real database, and the record of it is in this project."* **This is the right disclosure in the right place.** | extract the visible text as in row 40 |
| 43 | Self-contained — no external font, image, script, logo or trademark | `0` non-fragment `href`/`src`/`xlink:href`; SPDX header present | `python -c "import re;print(re.findall(r'(?:xlink:href\|href\|src)=\"(?!#)[^\"]*\"',open('docs/submission/diagrams/story.svg',encoding='utf-8').read()))"` |

---

## 2 · REFUSED — claims and defects handed back

A claim is refused when this auditor could not obtain a command that would prove it wrong, or when
the artefact it cites says something different. **Nothing here is softened on the worker's behalf.**

### 2.1 · REFUSED · W3 · *"In March 2019 a worker was hurt doing this same kind of work."*

**Where:** `docs/submission/JUDGE-START.md` and `docs/submission/FIRST-FIVE-MINUTES.md`, second
paragraph of each new sixty-second block, **in bold**.

**Why it is refused.** The word does not exist in the artefact. The seeded incident's own narrative
reads *"An isolation was signed off without verification at zero; residual hydraulic pressure
released while the guard was removed. No real incident, no real site, no real fatality."* **Nobody
is hurt in the record. The injury is the worker's addition.** And
`docs/submission/MUST-NOT-CLAIM.md` §3 lists exactly this shape under **MUST NOT SAY** —
*"Two contractors were burned at this site." (spoken as fact)*.

**The aggravating detail is the ordering, not the sentence alone.** W1 solved the same problem
correctly: its block opens *"Read the story below knowing it is invented"* and narrates afterwards.
W3 states the injury in bold in paragraph two and discloses the invention in paragraph five. **A
judge who reads two paragraphs and stops has been told a person was hurt.**

**Falsifying command:**

```bash
grep -c -i "hurt\|injur" verticals/mainline/db/seeds/demo/demo_world.sql   # prints 0
```

**Exact replacement text, for both files** (the two blocks carry the sentence near-identically):

> **The demonstration data describes a March 2019 failure of this same kind of work, and it is
> invented.** A machine was recorded as locked off without anyone confirming it was actually at
> zero pressure, and residual hydraulic pressure released while a guard was being removed. The
> record says so about itself: the incident row is titled `SYNTHETIC — Stored energy release
> during intrusive work` and its narrative field ends *"No real incident, no real site, no real
> fatality: this narrative was written for the MAINLINE demonstration and describes nobody"*
> (`verticals/mainline/db/seeds/demo/demo_world.sql:275-278`). The investigation named in that
> record cites the written rule meant to prevent exactly that: *"Before any intrusive work, stored
> energy shall be isolated, locked and verified at zero by a competent person."*

The later paragraph beginning *"The story is invented, and the data says so about itself"* then
becomes a repetition rather than a first disclosure, which is the right way round.

**Note for the orchestrator:** `python scripts/submission/check_submission_prose.py` **exits `0` on
the tree as it stands.** Rule SUB-03 does not catch this phrasing. That is a gap in the checker as
well as a defect in the prose, and the checker is another domain's file.

### 2.2 · REFUSED · W3 · citation `demo_world.sql:275` for a quotation that is not on line 275

**Where:** both new blocks, in the sentence disclosing the corpus is authored.

**Why.** Line `275` is the incident **title**. The quoted narrative — *"No real incident, no real
site, no real fatality…"* — is a three-line SQL string literal spanning lines `276-278`. The
citation is right about the title and wrong about the sentence it is attached to.

**Falsifying command:**

```bash
sed -n '275,278p' verticals/mainline/db/seeds/demo/demo_world.sql
```

**Exact replacement:** `verticals/mainline/db/seeds/demo/demo_world.sql:275-278`.

**Severity: low.** It is a pointer that lands one line short, not a false claim. It is here because
this repository's whole argument is *check us*, and a reader who checks and lands on the wrong line
learns the wrong lesson about our citations.

### 2.3 · REFUSED · W4 · the `STALE` branch of `DECLARED_ABSENT` has never been observed firing

**Where:** `scripts/submission/check_doc_links.py`, module docstring — *"the moment the path appears
the entry becomes a lie about the tree and this program says `STALE` and exits non-zero."*

**Why it is refused rather than accepted.** It is the correct design and it is the *only* assertion
in that file with no plant behind it. `--self-test` plants a missing link and a missing citation;
it does not plant a *present* declared-absent path. By the program's own standard — *"a self-test
that plants a defect and asserts the program exited non-zero passes when the program fails to
start"* — an unexercised branch is not evidence.

**Not a defect in the code.** It is a claim without a falsifying command, which is what this
section is for. **Recommended fix, and it is small:** add a third self-test phase that writes an
empty file at the declared-absent path inside the temporary fixture tree and asserts the output
contains the literal word `STALE` and the path's own name. That keeps the file's own rule.

### 2.4 · REFUSED · W5 · `story.svg`'s accessible description narrates the injury and omits the disclosure

**Where:** `docs/submission/diagrams/story.svg`, the `<desc>` element.

**Why it is refused.** The **visible** diagram gets this right (row 42): the closing caption says
the people, the plant and the incident number are invented. The `<desc>` element — the text a
screen reader speaks, and the text most tools extract when the image is embedded elsewhere — does
not. It opens *"June 2013: a seal on a big machine catches fire and two contractors working nearby
are burned"* and **never says the story is authored.** The disclosure that exists in the file
outside the visible caption is inside an **HTML comment**, which no reader and no assistive
technology ever sees.

**So the disclosure is present for a sighted reader and absent for a screen-reader user**, and this
diagram is the artefact most likely to be lifted out of the repository and pasted alone into a
submission gallery, where the caption may not travel with it.

**Falsifying command:**

```bash
python -c "import re;print(re.search(r'<desc[^>]*>(.*?)</desc>',open('docs/submission/diagrams/story.svg',encoding='utf-8').read(),re.S).group(1)[:160])"
```

**Exact replacement — one sentence, at the head of `<desc>`, before the existing first word:**

> An authored worked example: the people, the plant and the incident number are invented, and the
> database refusal in the fourth panel is not. Four panels. June 2013: …

*(the rest of the existing description follows unchanged.)*

### 2.5 · HANDED BACK · W5 · a scratch file was left at the repository root

`.w5-check.html`, 15 558 bytes, written `03:26`, untracked, at the top level of a **public**
repository. Falsify with `ls -la .w5-check.html`. **Delete it before the tree is committed.** This
is housekeeping, not a claim, and it is recorded here because the root of a public repository is
the first thing a judge sees in a file listing.

---

## 3 · AUDIT (i) · NO PROMOTION — **VERDICT: HELD**

Ruling R-J: *a verdict that moved in this wave is a defect in this wave.* Four verdicts were
checked. **None moved.** Each was re-derived from a machine-readable artefact, not from prose.

| verdict | required reading | re-derived by W6 | falsified by |
|---|---|---|---|
| **Agent Skills is `DESIGNED`** | `DESIGNED`, never `EXERCISED` | `crdb_agent_skills` → **`DESIGNED`** | `python -c "import json;print(json.load(open('evidence/tool-usage/crdb-features.json'))['rows']['crdb_agent_skills']['verdict'])"` — printing `EXERCISED` falsifies it |
| **Bedrock — both halves** | real **in this repository** *and* **not in the demo's request path** | *first half:* `aws_bedrock_runtime` → **`EXERCISED`**, basis a live `Converse` returning HTTP `200` with an AWS request id, plus `7` live `InvokeModel` legs in `evidence/aws/agent/live-run.json`. *second half:* **zero** imports of `boto3`, `anthropic`, `bedrock`, `openai` or `langchain` anywhere in the demo-api source | `python -c "import json;print(json.load(open('evidence/tool-usage/aws-services.json'))['rows']['aws_bedrock_runtime']['verdict'])"` and `grep -rEc "boto3\|anthropic\|bedrock" verticals/mainline/apps/demo-api/src/mainline_demo_api/*.py` |
| **The change request has no admission beat** | `admission_beat` is null and declared | `cr_gate_run.py:820` emits `"admission_beat": None`, and `test_cr_gate_run.py:500` asserts it | `grep -n '"admission_beat": None' verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py` |
| **Managed MCP is `15` of `16` at `DIVERGED — KNOWN GAP`** | not rounded to 16, not promoted | `evidence/mcp/pack-run.json`: `passed 15`, `total 16`, `verdict DIVERGED — KNOWN GAP`. Independently, `evidence/deploy/judge-run.json`: `channels.mcp.passed 15`, `total 16`, same verdict | `python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],d['total'],d['verdict'])"` |

**One observation, recorded and deliberately not raised as a defect.** W3's closing line spells the
first verdict in prose — *"Agent Skills is **designed and not exercised**"* — rather than as the
verdict token `DESIGNED`. It does not promote anything and the plain-English form is the readable
one. **If a house rule requires the token spelling in judge-facing prose, this is where it would be
fixed; this auditor does not rule that it must be.**

---

## 4 · AUDIT (ii) · NO REGRESSION — **VERDICT: HELD**

### 4.1 · The suite baseline

**`1070` collected · `1069` passed · `0` failed · `0` errors · `1` skipped.**

Re-derived by this auditor from the JUnit XML root elements of **two independent runs**, rather
than quoted from any document:

| artefact | timestamp | collected | passed | failed | errors | skipped |
|---|---|---:|---:|---:|---:|---:|
| `qa/film.xml` — the named baseline | `2026-08-16T16:39:53+10:00` | 1070 | 1069 | 0 | 0 | 1 |
| `qa/recert.xml` — an independent later run | `2026-08-17T01:03:29+10:00` | 1070 | 1069 | 0 | 0 | 1 |

```bash
python -c "import xml.etree.ElementTree as ET;a=ET.parse('qa/recert.xml').getroot().attrib;print(a['tests'],a['failures'],a['errors'],a['skipped'])"
```

**No suite was re-run by this wave and none needed to be**, because §4.2 shows that nothing the
suite reads was touched.

### 4.2 · What this wave touched

| surface | modified in this wave | command |
|---|---|---|
| `tests/**` | **none** | `git status --porcelain -- tests/` |
| `.github/**` (workflows) | **none** | `git status --porcelain -- .github/` |
| `packages/**` | **none** | `git status --porcelain -- packages/` |
| `verticals/**` | **none** | `git status --porcelain -- verticals/` |
| `spec/**` | **none** | `git status --porcelain -- spec/` |
| `scripts/proof/**` | **none** | `git status --porcelain -- scripts/proof/` |

**`DEFAULT_MAX_RESPONSE_BYTES` did not move:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py:323`
still reads `DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024`, and the file it lives in is not
modified.

```bash
sed -n '323p' verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py
git status --porcelain -- verticals/mainline/apps/demo-api/src/
```

**The gate proof verdict did not move:** `evidence/gate-refusal/proof-20260810T054407Z.json` reads
`verdict PROVEN` with `caveats []`, and the file is unmodified.

### 4.3 · One tracked file is modified that this wave's rulings put out of bounds

`README.md` is modified — `266` insertions, `412` deletions. **Ruling R-G says `README.md` is
untouched by every worker in this wave.** No worker in this wave owns it, and the change is dated to the concurrent
README lead's wave, whose plan is on disk at `docs/submission/readme-plan.md` alongside
`docs/submission/readme-parts/` and `scripts/submission/check_readme_readability.py`.

**This auditor's verdict: not a regression by this wave, and not this wave's to resolve.** It is
recorded because a later reader diffing the tree will see it and must not attribute it here.
Falsify with `git diff --stat -- README.md` and `ls docs/submission/readme-plan.md`.

---

## 5 · AUDIT (iii) · READABILITY — gloss coverage of every new layer-1 block — **VERDICT: HELD, WITH TWO NAMED EXCEPTIONS (§5.1, §5.2)**

The wave's gloss list (`extra-credit-plan.md` §1) names eighteen terms that may not appear in a
layer-1 block without a plain-language gloss at first use. Each new layer-1 block was read for
every one of them.

| block | listed terms it uses | glossed before use? |
|---|---|---|
| **W1** · `DEVPOST.md` *Read this first* | `obligation`, `disposition`, `permit-to-work`, `projection`\*, `SQLSTATE`\*, `MUS`\*, `NAA`\*, `C-SPANN`\*, `epoch`\*, `blame ancestry`\*, `synchronic`\*, `diachronic`\* | **YES.** `obligation` and `disposition` are glossed in the sentence that introduces them (*"one open question attached to that permit"*; *"that signed answer is called a **disposition**"*), `permit-to-work` in the clause that first uses it. The starred terms are **not used in the layer-1 block at all** — they are defined in the twelve-word table W1 placed *above* it, which is the layering the wave asked for. |
| **W3** · `JUDGE-START.md` *Sixty seconds first* | `merge` (not on the list, glossed anyway), `SQLSTATE`\*, `MUS`\*, `NAA`\*, `projection`\*, `blame ancestry`\*, `negative control`\*, `Wilson lower bound`\* | **YES for the block, with one named gap below it.** No listed term is used ungossed inside the sixty-second block; `merge` is glossed parenthetically at first use, which the list did not require. In the *Five things* section beneath it, `negative control`, `Wilson lower bound`, `MUS`, `NAA`, `blame ancestry` and `projection` each carry an explicit gloss at first use. **`SQLSTATE` does not** — see below. |
| **W3** · `FIRST-FIVE-MINUTES.md` *Sixty seconds first* | none from the list | **YES**, vacuously — the block is written entirely in plain words. |
| **W6** · `HOW-WE-GOT-HERE.md` | `permit-to-work`, `clause`, `blame ancestry`, `synchronic`, `diachronic`, `obligation`, `disposition`, `projection`, `epoch`, `SQLSTATE`, `negative control`, `canonicalisation` | **YES.** Machine-checked: every one of the twelve first appears inside the file's own *"The words this page uses"* section, which sits above every section that uses them. |

\* *listed term that appears in the file but not inside its layer-1 block.*

### 5.1 · Terms NOT glossed before use, named as the brief requires

**One, and it is small.** In `docs/submission/JUDGE-START.md` the word **`SQLSTATE`** first appears
at line `211`, inside W3's new *Five things* item 4, with no gloss attached to the word itself. The
nearest thing to one is at line `135`, in item 2: *"(`42501` is the five-character code the
database attaches to 'you do not have permission to do that'.)"* — which glosses **an example of
the thing** and never says that the thing is called a `SQLSTATE`. A reader can infer the link. The
gloss rule exists so that they do not have to.

```bash
grep -n "SQLSTATE" docs/submission/JUDGE-START.md | head -1     # 211
grep -n "five-character" docs/submission/JUDGE-START.md          # 135
```

**Exact fix — six words, at line 135, replacing the existing parenthesis:**

> (`42501` is a **SQLSTATE** — the five-character code a database returns to say what it did; this
> one means *"you do not have permission to do that"*.)

**Nothing else on the list is used before its gloss in any new block.**

### 5.2 · The finding that gloss coverage cannot catch

**The one substantive readability finding is §2.1, and it is not a gloss failure.** It is an
*ordering* failure: W3's block is written in plain words throughout, and the plain words say
something the artefact does not. **A block can pass every gloss test and still mislead, which is
why this audit has three parts and not one.**

Re-derive the W6 row:

```bash
python - <<'EOF'
t=open('docs/submission/HOW-WE-GOT-HERE.md',encoding='utf-8').read()
a,b=t.index('## The words this page uses'),t.index('## Part one')
for term in ["projection","blame ancestry","epoch","disposition","obligation","diachronic",
             "synchronic","canonicalisation","SQLSTATE","negative control","permit-to-work","clause"]:
    print(f'{term:18s}', 'OK' if t.lower().find(term.lower()) >= a else 'BEFORE-GLOSS')
EOF
```

---

## 6 · DEFECTS FOUND OUTSIDE THIS WAVE'S FILES — reported, not edited

Each is in a file ruling R-G places out of bounds. **Exact replacement text is given so the
orchestrator can act without re-deriving anything.**

### 6.1 · `docs/TOOL-USAGE.md:179` and `:361` still assert the claim W2's F03 struck

**The tension.** `TOOL-USAGE.md:179` says *"the unhinted plan is a declared `FULL SCAN`"*, measured
`2026-08-12` on the pinned local node, and `:361` repeats it. W2's F03 records that on a re-run
across `0`, `200`, `1,100` and `5,300` rows the plan naming **no** index contained a vector-search
step — the hinted and unhinted plans were the same plan.

**This is reported as a tension, not as a proven contradiction**, and the distinction is
deliberate: the two measurements name **different relations** (`ce@ce_ann` in `TOOL-USAGE.md`,
`t_clause_embedding@t_ann` in F03) and were taken five days apart. One of them may be measuring a
query shape the other is not. **This auditor did not re-run either sweep and will not assert which
is right.**

**What the orchestrator should do.** Have whoever owns `docs/TOOL-USAGE.md` re-run
`skills/designing-vector-recall-prefixes/scripts/assert_prefix_index_used.py` against the relation
that document names. If the unhinted plan now uses the index, the sentence needs this treatment —
the same treatment `DEVPOST.md` gives every superseded number, keeping both readings:

> *"Measured on the pinned local node `2026-08-12`, the unhinted plan was a declared `FULL SCAN`.
> **Re-measured `2026-08-17` on a differently-shaped table, the unhinted plan chose the index**
> (`docs/upstream/COCKROACHDB-FINDINGS.md` F03). Which of the two the optimizer picks is not
> settled by either run alone, and the assertion is kept for the reason it was written: a silent
> degradation from index to scan would return plausible rows either way."*

**Falsifying command:** `grep -n "FULL SCAN" docs/TOOL-USAGE.md`.

**Why this matters more than its size.** F03 is the finding W2 chose to publish as *refuted* rather
than quietly drop. If a judge follows that strike back and finds the struck claim still asserted
two documents away, the strike stops being evidence of discipline and starts being evidence of
drift.

### 6.2 · `docs/story/05-why-ancestry.md` ends with stray tool markup

The file's last two lines are `</content>` and `</invoke>` — an artefact of the tool call that
wrote it, below the word-count comment. It is another lead's wave and another lead's file.

**Falsifying command:** `tail -3 docs/story/05-why-ancestry.md`.

**Exact fix:** delete both lines. Nothing else in the file is affected.

### 6.3 · `scripts/submission/check_submission_prose.py` rule SUB-03 does not catch §2.1

Recorded under §2.1 and repeated here so the checker's owner sees it in the list addressed to them.
The checker currently exits `0` on a tree containing *"a worker was hurt"* stated as fact. The
register it is meant to enforce is in `MUST-NOT-CLAIM.md` §3.

---

## 7 · WHAT THIS AUDIT ITSELF DID TO THE TREE — disclosed

**This auditor wrote two files by intent — `HOW-WE-GOT-HERE.md` and this one — and caused two more
to be rewritten as a side-effect. That is a deviation and it is recorded rather than omitted.**

Re-deriving W2's F01 and F02 first-hand meant running W2's own reproduction script, and that script
writes its transcripts as it goes:

```
wrote evidence/upstream/F01-has-function-privilege.json
wrote evidence/upstream/F02-show-grants-signature.json
```

**What changed and what did not.** Both files are **untracked** — created by this wave, in no
commit. Both were regenerated with the **same verdicts** (`STUB-CONFIRMED`, `SPELLINGS-DIFFER`,
control `True`). What differs is the run's timestamp and the random 8-hex suffix of the scratch
role and database, which the script prints and then drops (`scratch databases left behind by this
run: 0`).

**The alternative was to take W2's word for its own headline finding, which is the one thing this
page exists not to do.** If the orchestrator would rather hold W2's original transcripts, restore
them from W2's own session before committing.

---

## 8 · NOT AUDITED, AND WHY

Named rather than omitted, because a completeness ledger that hides its own gaps is the artefact it
was written to replace.

1. **`docs/submission/DIAGRAMS.md` (W5) — absent at audit close.** Both SVGs landed and were
   audited (rows 33–35, 40–43); the page that frames them had not. **Every claim that file makes is
   unaudited.** If it restates the SVG contents, rows 33–35 and 40–43 are the commands that check
   it; if it makes new claims, they are unaudited and this page does not vouch for them.
2. **W4's `MECHANICAL-SWEEP.md` was audited only on the four checks this page could re-derive
   cheaply** (rows 36–39). Its check 1 (licence detectability), check 2 (the video privacy
   instruction), check 4 (the origin answered from outside) and check 6 (the expected `STALE` and
   the question for the founder) were **not** independently re-derived here. Check 4 in particular
   would require a network request against the public origin, which this auditor did not make.
3. **The four-file byte-equality assertion behind W1 row 5 was read, not executed.** Running
   `tests/unit/corpus` would have executed it. This wave's no-regression rule and the T-1-day
   posture argued against starting test processes for a claim whose artefact could be read
   directly.
4. **W2's F04, F05, F06 and F07 were not re-run.** F05's central refusal requires deliberately
   creating twenty thousand schema objects, which W2 itself declined for good reason; every Cloud
   reading requires statements against a shared cluster under a judging freeze. **For these four,
   this page carries W2's own labelling rather than an independent measurement, and says so.**
   Rows 10–13 are the ones this auditor stands behind personally.
5. **No suite was executed and no measurement was taken against AWS, the deployed origin, or
   CockroachDB Cloud.** The only cluster this audit touched is the local single-node
   `postgresql://root@127.0.0.1:26257`, and the only database it created was a scratch one that the
   script dropped.

---

## 9 · THE VERDICT

| audit | verdict |
|---|---|
| **(i) no promotion** | **HELD** — four verdicts checked against machine-readable artefacts; none moved |
| **(ii) no regression** | **HELD** — baseline `1070 / 1069 / 0 / 0` re-derived from two JUnit roots; no test, workflow, package, vertical, spec or proof script modified; `DEFAULT_MAX_RESPONSE_BYTES` unmoved |
| **(iii) readability** | **HELD, with two named exceptions** — no listed term is used before its gloss in any new **layer-1 block**; one term (`SQLSTATE`, `JUDGE-START.md:211`) is ungossed in the section beneath one, named at §5.1 with a six-word fix; §2.1 is an ordering failure rather than a gloss failure |
| **claims re-derived** | **43**, of which **14** were re-derived by executing a program rather than reading a file |
| **refused** | **4**, at §2.1, §2.2, §2.3 and §2.4, each with the exact replacement text |
| **handed back** | **1** housekeeping item at §2.5, **3** out-of-bounds defects at §6 |
| **unaudited** | **1** worker file absent at close, plus four of W4's six checks, listed at §8 |

**The best evidence this wave was honest is not in this table.** It is W2's decision to publish
`F03` as *refuted* and to print, in its own words, that **six of the seven findings it was handed
did not survive re-measurement.** A wave that arrives at a deadline with fewer claims than it
started with, and says why, is the only kind whose remaining claims are worth checking.

<!-- word count: `python -c "print(len(open('docs/submission/COMPLETENESS-LEDGER.md',encoding='utf-8').read().split()))"` -->
