<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RULES MATRIX — one row per hackathon rule, MET or UNMET, with the artefact that decides it

Two tables. **§1 is the rules**, one row each, every row carrying the **artefact path** a
reader opens to overturn the verdict. **§2 is generated** by a program that asks the
filesystem, `git` and GitHub the same ten questions every time and exits non-zero while
any of them is unresolved.

Where the two disagree, **the program is right and this document is stale**, and the
command that resolves the disagreement is printed under §2.

```
python scripts/submission/check_submission_ready.py --markdown   # the table in §2
python scripts/submission/check_submission_ready.py --json       # the machine record
python scripts/submission/check_submission_ready.py              # the table + remedies
```

Exit codes: `0` every blocking row resolved · `1` at least one unresolved · `2` the gate
could not run. There is no fourth outcome and there is no flag that turns a red row green.

**UNMET rows are not this document's failure. They are its job.** A rules matrix in which
everything is MET on 2026-08-11, seven days before the deadline and with nothing deployed,
would be the single least believable file in the repository.

---

## 0 · The state on 2026-08-11, in three sentences

**Six of the eight rules are MET. Two are UNMET, and both are Stage One pass/fail:** the
repository is `PRIVATE`, and no demo is deployed. The video is a third open row — the kit
is committed and CI-validated, the film is the founder's to record — and it is not Stage
One.

Everything else is met and evidenced: the licence, the description, the window, the two
CockroachDB tools, the AWS service, and the documentation of both.

---

## 1 · The rules, one row each

Every **Deciding artefact** is a path in this repository (or a literal command whose output
a reader can reproduce). No row's verdict rests on a sentence written here.

| # | Rule | Verdict | Deciding artefact | What it says |
|---|---|---|---|---|
| **R1** | Public repository with an open-source licence | **UNMET** | `gh repo view Shaugato/mainline --json visibility,licenseInfo` · `LICENSE` · `docs/submission/LICENCE-CENSUS.md` | Licence half **met**: `LICENSE` is tracked (`git ls-files LICENSE` answers), 11 357 bytes, reads as Apache-2.0, and GitHub already resolves `licenseInfo.key` to `apache-2.0`. Public half **unmet**: `visibility` is `PRIVATE`. The flip is one irreversible command and it is gated on `scripts/submission/audit_public_readiness.py` exiting 0. |
| **R2** | A URL to a functional demo, free and unrestricted for judges | **UNMET** | `docs/submission/SUBMISSION.json` → `demo_url` · `evidence/deploy/acceptance.json` | `demo_url` holds the literal `UNRESOLVED`. `terraform apply` has never been run: no MAINLINE Lambda, Function URL or bucket exists in the account. The end-to-end acceptance verdict is `NOT PROVEN`, and that artefact names the two defects and the source lines that cause them. The plan that would create the origin is committed at `evidence/deploy/terraform-plan-furl.txt`. |
| **R3** | A text description of the project's features | **MET** | `docs/submission/DEVPOST.md` | 28 503 bytes, 161 non-blank lines, 15 paste blocks, 3 415 words, elevator pitch 163 characters against a 200 cap. Five of the blocks answer the five judging criteria one apiece. `scripts/submission/check_submission_prose.py` scans it against nine SUB rules and the claim-hygiene table; it reports **0 violations in this file**. |
| **R4** | A demo video under three minutes, on YouTube or Vimeo | **UNMET** | `docs/submission/SUBMISSION.json` → `video_url` · `docs/submission/VIDEO-KIT.md` · `verticals/mainline/demo/script/SHOT-LIST.yaml` | `video_url` holds `UNRESOLVED`. The kit exists — VO, timings, seeded state, the sentences that may not be said on camera — and `.github/workflows/claims.yml` runs the shot-list validator, so a script that drifts past the three-minute budget is a red build rather than a discovery made during the upload. Nothing in this repository can resolve this row. |
| **R5** | A new project, created inside the submission window | **MET** | `docs/submission/DISCLOSURE.md` · `evidence/provenance/commit-window.json` | First commit `f80fefd`, authored and committed `2026-08-05T22:47:47+10:00` — inside the window, which opened `2026-08-05`. All 38 commits pass, and the check tests **both** the author date and the committer date, because a rebase moves one and not the other. The separate, earlier research repository is disclosed and holds no product code. |
| **R6** | At least two CockroachDB tools | **MET** | `docs/TOOL-USAGE.md` Part 1 · `evidence/tool-usage/crdb-features.json` | Four tools documented; **two carry an EXERCISED verdict in the census** — the database itself (`evidence/gate-refusal/`, a real refusal on a real cluster) and CockroachDB Cloud with the `ccloud` CLI (`evidence/deploy/cloud-chain.json`, `evidence/ccloud/`). A third, the Managed MCP Server, now has a live session too (`evidence/deploy/judge-run.json`: 15 of 16 pack questions PASS over `https://cockroachlabs.cloud/mcp`) although the census has not been regenerated and still reads DESIGNED. The floor is two and the floor is cleared without counting the third. |
| **R7** | At least one AWS service | **MET** | `evidence/deploy/aws-live.json` · `evidence/aws/probe/` · `evidence/tool-usage/aws-services.json` | Bedrock **executes** in `ap-southeast-2`: Titan v2 `InvokeModel` returned HTTP `200`, a 1024-dimension embedding at L2 norm `1.0` for 13 input-text tokens; Claude Haiku 4.5 `Converse` returned HTTP `200` and `MAINLINE gate online` for 16 in / 8 out / 24 total tokens. Both carry AWS request ids. Three AWS rows are EXERCISED (Bedrock inference, Bedrock embeddings, CloudWatch read-only), eight are DESIGNED because nothing is deployed, one is NOT-AVAILABLE because Bedrock Rerank is genuinely absent in the region. |
| **R8** | Documentation of **which** CockroachDB tools and AWS services, and **how** | **MET** | `docs/TOOL-USAGE.md` · `evidence/tool-usage/` | 4 CockroachDB tools with 10 engine features accounted separately, and 12 AWS services. Every row carries a verdict, a `file:line` that does the work, and an `evidence/` artefact or an explicit "none — not applied". `python scripts/submission/capture_tool_evidence.py --check` re-derives the counts from the tree with no network and no credential; it reports the census **stale by 8 bytes** today, which is a regeneration owed, not a false claim. |

### Why R1 and R2 are the only two that matter today

They are the **Stage One pass/fail** gates: a submission that fails either is not assessed
at all, and the other six rows are worth nothing behind them. R4 is a real gap and not a
Stage One gate.

Both are resolvable by a person, not by more engineering:

```bash
# R2 — the apply the founder approves; it prints the hostname that becomes demo_url
MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account <id>

# R1 — the audit must exit 0 first; the flip is irreversible in practice
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
gh repo edit Shaugato/mainline --visibility public --accept-visibility-change-consequences
```

---

## 2 · The generated table

**The status column is not typed. It is generated.**

Generated `2026-08-11T06:46:41Z` by `python scripts/submission/check_submission_ready.py --markdown`.
Exit code at that instant: **1**, with **4** unresolved rows.

| Row | Requirement | Status | Observed | Evidence | Re-derive with |
|---|---|---|---|---|---|
| `licence_file` | 1 - public repo with an open-source LICENSE file | **PASS** | 11357 bytes, reads as Apache-2.0 | `LICENSE`, `LICENSES/`, `docs/submission/LICENCE-CENSUS.md` | `ls -l LICENSE && python scripts/qa/check_reuse.py` |
| `remote_sync` | 1 - public repo with an open-source LICENSE file | **WARN** | in sync with origin/master, but 94 path(s) are uncommitted and will not be published | the remote itself - there is no local artefact for this row | `git rev-list --left-right --count origin/master...HEAD` |
| `repo_public` | 1 - public repo with an open-source LICENSE file | **FAIL** | visibility is PRIVATE [gh repo view --json visibility]; repo_url https://github.com/Shaugato/mainline; a judge opening it today gets 404. Missing: the flip | `qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md` | `gh repo view Shaugato/mainline --json visibility` |
| `demo_url` | 2 - a URL to a functional demo app | **FAIL** | demo_url is UNRESOLVED | `docs/submission/SUBMISSION.json` key `demo_url` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `video_url` | 4 - demo video under 3 minutes on YouTube or Vimeo | **FAIL** | video_url is UNRESOLVED | `docs/submission/VIDEO-KIT.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `devpost_description` | 3 - text description of the features | **PASS** | docs/submission/DEVPOST.md: 28503 bytes, 161 non-blank lines | `docs/submission/DEVPOST.md` | `python scripts/submission/check_submission_prose.py` |
| `tool_usage` | 5 - documented CockroachDB and AWS usage (>=2 CRDB tools, >=1 AWS, >=1 run) | **PASS** | 4 CockroachDB tools, 10 AWS services; 2 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch); 18 of 18 cited artefacts present on disk | `docs/TOOL-USAGE.md`, `evidence/tool-usage/` | `python scripts/submission/capture_tool_evidence.py --check` |
| `judge_access` | 6 - free, unrestricted access for judges | **PASS** | resolved - credential required; how 463 chars, credentials_location 373 chars, and no credential value in the file | `docs/submission/SUBMISSION.json` key `judge_access`, `VERIFY.md` | `python scripts/submission/check_submission_ready.py --json` |
| `disclosure` | 7 - created in the submission window; pre-existing code disclosed | **PASS** | docs/submission/DISCLOSURE.md present (20445 bytes); 38 commits, all inside the window | `docs/submission/DISCLOSURE.md`, `evidence/provenance/commit-window.json` | `python scripts/submission/provenance_census.py --check` |
| `deadline` | deadline - 2026-08-18 17:00 EDT | **PASS** | 7d 14h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z) | the official rules page | `python scripts/submission/check_submission_ready.py` |

**To regenerate this table**, replace everything between the two horizontal rules of this
section with the output of:

```bash
python scripts/submission/check_submission_ready.py --markdown
```

Do not edit a cell by hand. A hand-edited status column is a claim with nothing behind
it, which is the one thing this repository is built not to ship.

### The `remote_sync` WARN is not noise

It counts the paths that are uncommitted — a number that moves with every edit, which is
why the count lives in the generated table above and not in this sentence. Uncommitted
work is invisible to a judge, so the row
refuses to read green while it is true, and it clears the moment those paths are committed
and pushed. It is a `WARN` rather than a `FAIL` because `HEAD` and `origin/master` are the
same commit — nothing is *missing* from the server that was ever committed here.

---

## 3 · Requirement by requirement

### R1 — a public repository with an open-source licence

**UNMET.** Three separate facts have to hold, and the gate keeps them as three rows
because they fail independently and are fixed by different commands.

| fact | row | state on 2026-08-11 |
|---|---|---|
| a licence file exists at the root, and is tracked | `licence_file` | **met** — Apache-2.0, 11 357 bytes; `git ls-files LICENSE` answers, which it did not on 2026-08-10 |
| the tree on the server is the tree on this disk | `remote_sync` | **partial** — `HEAD` == `origin/master`; the uncommitted-path count is in §2's generated row, because it moves |
| the repository is publicly readable | `repo_public` | **unmet** — `visibility: PRIVATE` |

The `repo_public` row reports **both** its facts on every path, whichever fails first:
the visibility *and* whether `repo_url` is written. `repo_url` is written —
`https://github.com/Shaugato/mainline`, which is the correct address regardless of
visibility — and the row still fails, on the flip alone, and says so in those words.

Re-derive: `gh repo view Shaugato/mainline --json visibility` — a submitted state prints
`PUBLIC`.

### R2 — a URL to a functional demo, free and unrestricted for judges

**UNMET, and precisely so.** Two things are missing and they are different:

* **the origin.** Nothing is deployed. The demo URL will be a public **Lambda Function
  URL** — HTTPS on an AWS-issued certificate, no account verification needed — because a
  real `terraform apply` on 2026-08-10 was refused by AWS with `AccessDenied: Your account
  must be verified before you can add new CloudFront resources`, quoted verbatim in
  `docs/deploy/RUNBOOK.md`. CloudFront is now optional and defaults off.
* **the acceptance.** `evidence/deploy/acceptance.json` reads `NOT PROVEN` against a local
  Function-URL emulator serving the unmodified handler against the live Cloud database.
  The 404 on `POST /v1/demo/gate-run` recorded there on 2026-08-10 is **gone** — the route
  is reachable — and it now fails further in, on two named defects. Nothing in that file
  was relaxed to reach a green.

**"Free and unrestricted for judges"** is the half that *is* answered:
`judge_access` in `docs/submission/SUBMISSION.json` names two paths a judge can take today
against the live ledger, and `evidence/deploy/judge-access.json` measured both directions
of the read-only login — 14 of 14 `mainline_audit` views readable, 11 of 11 base-table and
write attempts refused with the expected SQLSTATE.

Re-derive: `python scripts/submission/check_submission_ready.py --check-urls`, which
fetches the URL and requires HTTP 200 rather than trusting that it was pasted correctly.

### R3 — a text description of the features

**MET as a source document.** `docs/submission/DEVPOST.md` is checked for size, structure
and unfinished-sentence markers by the `devpost_description` row, and its prose is checked
against nine SUB rules by `scripts/submission/check_submission_prose.py`.

The gate deliberately does **not** fail this row because `DEVPOST.md` carries the literal
`UNRESOLVED` beside the two open URLs in its paste-order table. That marker is honest, and
it is already counted by the `demo_url` and `video_url` rows. Counting it twice would turn
one fact into two red rows and make this table overstate how much is wrong.

### R4 — a video under three minutes on YouTube or Vimeo

**UNMET, and the gap is a film, not a document.** The kit exists and is CI-validated; the
film does not exist. The gate also checks the *host*: a URL that is not on YouTube or
Vimeo fails, because the rules name those two.

### R5 — a new project created inside the submission window

**MET.** The `disclosure` row re-reads the git history and checks **both** the author date
and the committer date of every commit against `2026-08-05` … `2026-08-18` evaluated in
EDT — one date is half a check, because a rebase moves one and not the other.

Re-derive: `python scripts/submission/provenance_census.py --check`, whose output is
committed at `evidence/provenance/commit-window.json`.

### R6, R7, R8 — the tools, the services, and how

**All three MET**, and the `tool_usage` row asserts the *floor*, not the ceiling, so it
stays honest if a tool is later withdrawn from the document.

Since 2026-08-11 that row asks two questions it did not ask before, because counting names
was never evidence of use:

* at least one AWS service must be marked **EXERCISED or EXECUTED**, so a table of pure
  intent cannot pass — it is the check that would have failed on 2026-08-10, when twelve
  AWS services were named and none had run;
* at least one `evidence/...` artefact the document cites must **exist on disk**, so a
  citation is a file a reader can open rather than a path somebody typed. Today: 18 of 18
  cited artefacts present.

Re-derive: `python scripts/submission/capture_tool_evidence.py --check`, which rebuilds the
census under `evidence/tool-usage/` from the source tree and exits 1 if the committed files
differ. It exits 1 today, by 8 bytes on the AWS census, which is a regeneration owed by the
domain that owns the generator.

### Requirement 6 of the gate — free, unrestricted access, and no credential in this file

**Resolved 2026-08-11.** All three `judge_access` members are answered:

| member | value shape | why it is what it is |
|---|---|---|
| `required` | `true`, a real JSON boolean | reading **our** ledger takes **our** login; the gate refuses the string `"false"`, which is truthy in most languages that will read this file |
| `how` | 463 characters naming both paths and the artefact that measured them | a sentence a judge can act on without asking us a question |
| `credentials_location` | 373 characters, a **pointer** | it names the submission form's credentials field and the command that generates the value — never the value |

**No credential value is ever written into `SUBMISSION.json`.** The file becomes
world-readable the instant the repository flips, so the gate enforces this rather than
trusting it: it scans every value for eight credential shapes, for keys whose *names* say
the value is a secret, and for bare high-entropy blobs, and it fails the row if any of them
matches — even if every URL beside it is resolved.

Since 2026-08-11 it also refuses values that are *present but empty of content*: a `how`
under 48 characters, a `credentials_location` under 24 when a credential is required, a
placeholder token in either, or the contradiction `required: true` with
`credentials_location: "none"`. Resolving a field and answering it are different things,
and until that change only the first was checked.

---

## 4 · `docs/submission/SUBMISSION.json` — the schema, documented here because JSON holds no comments

One file is the single write point for every unresolved submission fact. Ten documents and
one workflow read it; nobody writes a URL into prose.

**Schema version 2**, bumped on 2026-08-11 when the `notes` object was added. No existing
key changed meaning.

| key | type | meaning |
|---|---|---|
| `schema_version` | integer | bumped when a key is added or changes meaning, never when a value changes |
| `schema_documented_in` | string | points back at this section |
| `read_by` | array of strings | every program and document that reads the file |
| `unresolved_sentinel` | string | the literal an unresolved field holds: `UNRESOLVED` |
| `never_write_a_credential_here` | string | the standing rule, in band, where a person editing the file will see it |
| `a_field_is_resolved_only_when_it_is_proven` | string | why two fields still hold the sentinel: the fact is not true yet, not untyped |
| `demo_url` | string | rule R2. `UNRESOLVED` until deployed |
| `repo_url` | string | the URL a judge opens. **Resolved** — the address does not depend on visibility |
| `video_url` | string | rule R4. `UNRESOLVED` until uploaded |
| `judge_access.required` | boolean, or `UNRESOLVED` | whether a judge needs a credential at all |
| `judge_access.how` | string, ≥ 48 chars | one sentence a judge can act on |
| `judge_access.credentials_location` | string, ≥ 24 chars when required | **a pointer to where a credential lives, never a credential** |
| `notes.{repo_url,demo_url,video_url}` | string | for each field a human must resolve: what is missing and the literal command that resolves it |
| `deadline_utc` / `deadline_local` | string | `2026-08-18T21:00:00Z` / `2026-08-18 17:00 EDT`, resolved |
| `devpost_description_file` | string | `docs/submission/DEVPOST.md` |
| `rules_matrix_file` | string | this document |
| `tool_usage_file` | string | `docs/TOOL-USAGE.md` |
| `disclosure_file` | string | `docs/submission/DISCLOSURE.md` |
| `honesty_file` | string | `docs/HONESTY.md` — what is broken, counted |
| `ci_state_file` | string | `docs/CI-STATE.md` — every lane's real conclusion |
| `licence_file` | string | `LICENSE` |

Two notes a reader will otherwise have to reverse-engineer from the code.

**`judge_access.required` is typed twice on purpose.** Until it is answered it holds the
string `UNRESOLVED`, like every other unresolved field; once answered it must be a real
JSON boolean. The gate refuses both the sentinel and a string spelled `"false"`, because
a submission gate that can be fooled by a quotation mark is not a gate.

**The file carries no sidecar `.license`.** It is covered by the root `REUSE.toml` block
for `docs/submission/**`, which is why a JSON file with no comment syntax can still
declare a licence.

---

## 5 · `NOTRUN` is not a pass, and this is the whole design

The gate has four statuses. Only one of them resolves a row.

| status | meaning | resolves the row? |
|---|---|---|
| `PASS` | the question was asked and the answer was right | **yes** |
| `FAIL` | the question was asked and the answer was wrong | no |
| `WARN` | the answer was right but incomplete — the remote is in sync and the working tree is dirty | no |
| `NOTRUN` | nobody could answer: no `gh`, no network, no ref, no git | no |

`NOTRUN` prints as `NOT CHECKED` in the observed column and blocks like a failure. A
question nobody could answer is an unresolved question, and the single most common way a
release checklist lies is by rendering "we could not check this" in the same colour as
"this is fine".

Since 2026-08-11 the run also prints a **census of unasked questions**, even when it is
zero — today, `0 rows were NOT CHECKED: every question above was asked and answered`. A
reader told how many questions went unasked can weigh the verdict; a reader told nothing
assumes the answer was no.

The repository visibility row is where this matters. It reads the answer from one of two
sources and names which one answered:

1. `$GITHUB_EVENT_PATH` — inside GitHub Actions, the event payload already carries
   `repository.visibility`. No token, no network, no `gh`. This is what lets the CI lane
   assert the row without a credential.
2. `gh repo view --json visibility` — on a machine with a logged-in CLI.

When neither can answer, the row is `NOTRUN`. It is never assumed public.

---

## 6 · What checks this document

`.github/workflows/submission.yml` runs, on every push and pull request, with egress
blocked and no credential:

1. `check_submission_ready.py --self-test` — plants one of every failure family the gate
   must catch and requires it to fire. A gate that has never refused asserts nothing.
2. `check_submission_ready.py` itself, report-only until D-3 and blocking after, so the
   lane is informative during the build and refuses during the submission window.
3. `check_path_lengths.py` and `scripts/qa/check_reuse.py`.

The self-test is the half that matters. It exercises the sentinel scan, all eight
credential shapes, the key-name rule, the judge-access substance floors including the
`required: true` / `"none"` contradiction, the tool-usage evidence rule in both directions,
`rev-list` parsing, URL classification, both visibility sources, the clock arithmetic,
description triviality, tool counting, the commit-window check including the rebase case,
the `NOTRUN` census, and the invariant that only `PASS` resolves a row.

**That lane is red today** for a reason that is nothing to do with this document:
`REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254`. The
repository is mid-migration between two spellings of one licence identifier. It is a
repo-wide header sweep, it is recorded in `docs/CI-STATE.md` §4.1, and lowering the
baseline to buy the green is forbidden.

---

## 7 · Related documents

* [`RUNBOOK.md`](RUNBOOK.md) — the founder's numbered D-day list, every step a literal
  command with its expected output.
* [`DEVPOST.md`](DEVPOST.md) — the description, field by field, in paste order, with one
  section per judging criterion.
* [`DISCLOSURE.md`](DISCLOSURE.md) — R5, and the research repository.
* [`PUBLIC-READINESS.md`](PUBLIC-READINESS.md) — what must be true before the flip.
* [`VIDEO-KIT.md`](VIDEO-KIT.md) — R4's kit.
* [`JUDGING-AXES.md`](JUDGING-AXES.md) — the per-axis map a judge scores against.
* [`../TOOL-USAGE.md`](../TOOL-USAGE.md) — R6, R7 and R8.
* [`../CI-STATE.md`](../CI-STATE.md) — every workflow's real conclusion, with run ids.
* [`../HONESTY.md`](../HONESTY.md) — what is broken, published rather than hidden. Every
  document in this directory links to it, and none of them softens it.
