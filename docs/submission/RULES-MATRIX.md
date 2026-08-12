<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RULES MATRIX — one row per hackathon rule, MET or UNMET, with the artefact that decides it

Two tables. **§1 is the rules**, one row each, every row carrying the **command** a reader
runs to overturn the verdict and the **artefact path** that command reads. **§2 is
generated** by a program that asks the filesystem, `git` and GitHub the same ten questions
every time and exits non-zero while any of them is unresolved.

Where the two disagree, **the program is right and this document is stale**, and the
command that resolves the disagreement is printed under §2.

```bash
python scripts/submission/check_submission_ready.py --markdown   # the table in §2
python scripts/submission/check_submission_ready.py --json       # the machine record
python scripts/submission/check_submission_ready.py              # the table + remedies
python scripts/submission/check_submission_ready.py --self-test  # the gate refusing
```

Exit codes: `0` every blocking row resolved · `1` at least one unresolved · `2` the gate
could not run. There is no fourth outcome and there is no flag that turns a red row green.

**UNMET rows are not this document's failure. They are its job.** A rules matrix in which
everything is MET six days before the deadline, with nothing deployed and no film shot,
would be the single least believable file in the repository.

---

## 0 · The state on 2026-08-12, in three sentences

**Six of the eight rules are MET. Two are UNMET, and only one of those is a Stage One
pass/fail:** no demo is deployed (R2, Stage One), and the video has not been recorded (R4,
not Stage One). Both are resolved by a person doing a thing, not by more engineering.

**R1 is now MET.** The repository is `PUBLIC` and carries Apache-2.0 — measured, not
remembered, at the top of §1's transcript. Every sentence in this file that once read
`PRIVATE` has been re-derived and rewritten; the row that used to carry the flip is the one
row a stranger can now check without asking us for anything.

Everything else is met and evidenced: the licence, the description, the window, three
CockroachDB tools against a floor of two, Bedrock executing against a floor of one, and the
documentation of both.

---

## 1 · The rules, one row each

Every **Deciding artefact** cell holds a literal command, a path in this repository, or
both. No row's verdict rests on a sentence written here, and the transcript under the table
is what those commands printed on this machine on 2026-08-12.

| # | Rule | Verdict | Deciding artefact | What it says |
|---|---|---|---|---|
| **R1** | Public repository with an open-source licence | **MET** | `gh repo view Shaugato/mainline --json visibility,licenseInfo` · `git ls-files LICENSE` · `LICENSE` · `docs/submission/LICENCE-CENSUS.md` | **Both halves met.** Public half: `visibility` is `PUBLIC`. Licence half: `LICENSE` is tracked (`git ls-files LICENSE` answers `LICENSE`), 11 357 bytes, reads as Apache-2.0, and GitHub independently resolves `licenseInfo.key` to `apache-2.0`. The tree behind the URL is the audited tree: `git rev-list --left-right --count origin/master...HEAD` answers `0 0`. |
| **R2** | A URL to a functional demo, free and unrestricted for judges | **UNMET — two halves, both open, for different reasons** | `docs/submission/SUBMISSION.json` → `demo_url` · `evidence/deploy/acceptance.json` · `evidence/deploy/terraform-plan-furl.txt` | **The origin does not exist.** `demo_url` holds the literal `UNRESOLVED`; `terraform apply` has never been run, so there is no MAINLINE Lambda, Function URL or bucket in the account. The plan that would create it is committed: 11 to add, 0 to change, 0 to destroy, `authorization_type = NONE`, `ap-southeast-1`. **The app does not yet answer.** `acceptance.json`, generated `2026-08-12T16:17:12Z`, reads `NOT PROVEN` against a local Function-URL emulator serving the unmodified handler: both gate runs returned `500 internal_error · resource=demo_gate_run · KeyError: 0`, so repeatability was not established. Nothing in that file was relaxed to reach a green. **The access half IS answered** — see the row below the table. |
| **R3** | A text description of the project's features | **MET** | `docs/submission/DEVPOST.md` · `python scripts/submission/check_submission_prose.py` | 40 515 bytes, 200 non-blank lines, 6 175 words, 5 fenced blocks. The prose gate scans it against nine SUB rules and the claim-hygiene table and reports **0 violations in this file**. (The gate exits 1 overall on one violation in `VIDEO-KIT.md`, quoted in R4 — a different file and a different owner.) |
| **R4** | A demo video under three minutes, on YouTube or Vimeo | **UNMET** | `docs/submission/SUBMISSION.json` → `video_url` · `docs/submission/VIDEO-KIT.md` · `verticals/mainline/demo/script/SHOT-LIST.yaml` | `video_url` holds `UNRESOLVED`. The kit exists — VO, timings, seeded state, the sentences that may not be said on camera — and `.github/workflows/claims.yml` runs the shot-list validator, so a script that drifts past the three-minute budget is a red build rather than a discovery made during the upload. Two facts a reader should have: nothing in this repository can resolve this row, and `check_submission_prose.py` currently **fails on `VIDEO-KIT.md:179` [SUB-06-migration-count]** — the kit quotes a remembered migration count instead of re-deriving one. |
| **R5** | A new project, created inside the submission window | **MET** | `docs/submission/DISCLOSURE.md` · `evidence/provenance/commit-window.json` | First commit `f80fefd`, authored **and** committed `2026-08-05T22:47:47+10:00` — inside the window, which opened `2026-08-05`. All **47** commits pass, and the check tests **both** the author date and the committer date, because a rebase moves one and not the other. The separate, earlier research repository is disclosed and holds no product code. |
| **R6** | At least two CockroachDB tools | **MET** | `docs/TOOL-USAGE.md` Part 1 · `evidence/tool-usage/crdb-features.json` | Four tools documented and **three carry an EXERCISED verdict in the census**: the database itself (v26.2.5, `evidence/gate-refusal/`, a real refusal on a real cluster), CockroachDB Cloud with the `ccloud` CLI (`evidence/deploy/cloud-chain.json`), and the Managed MCP Server (`evidence/deploy/judge-run.json`: 15 of 16 pack questions PASS over `https://cockroachlabs.cloud/mcp`). The fourth, Agent Skills, reads DESIGNED and is not counted. The floor is two and it is cleared without the third. |
| **R7** | At least one AWS service | **MET** | `evidence/deploy/aws-live.json` · `evidence/aws/probe/` · `evidence/tool-usage/aws-services.json` | Bedrock **executes** in `ap-southeast-2`. Four live calls, `calls_failed: []`, every one HTTP `200`, each with the AWS request id it returned: `sts:GetCallerIdentity` `04018eca-…`, `bedrock:ListFoundationModels` `d8c940e8-…`, `bedrock-runtime:InvokeModel` `b4d826e9-…` (Titan v2, a 1024-dimension embedding at L2 norm `1.0`), `bedrock-runtime:Converse` `3c7a283c-…` (Claude Haiku 4.5, `end_turn`). Total 1.75 s; the file's own verdict is `AWS BEDROCK EXECUTED`. The census marks **3 of 12** AWS rows EXERCISED, 8 DESIGNED because nothing is deployed, and 1 NOT-AVAILABLE because Bedrock Rerank is genuinely absent in the region. |
| **R8** | Documentation of **which** CockroachDB tools and AWS services, and **how** | **MET, with a regeneration owed** | `docs/TOOL-USAGE.md` · `evidence/tool-usage/` · `python scripts/submission/capture_tool_evidence.py --check` | `TOOL-USAGE.md` is 80 819 bytes. The CockroachDB census holds 14 rows — 4 tools and 10 engine features accounted separately, 12 EXERCISED and 2 DESIGNED; the AWS census holds 12 service rows. Every row carries a verdict, a `file:line` that does the work, and an `evidence/` artefact or an explicit "none — not applied"; the gate confirms **21 of 21 cited artefacts are present on disk**. `capture_tool_evidence.py --check` re-derives the counts from the tree with no network and no credential, and **exits 1 today**: both census files are stale in one field, `files_scanned` 7 388 on disk against 7 390 fresh. That is a regeneration owed, not a false claim, and it is owned by the domain that owns the generator. |

### The transcript — every verdict above, re-derived on 2026-08-12

Paste any line. The outputs below are what this machine printed; nothing here is quoted
from memory.

```console
$ gh repo view Shaugato/mainline --json visibility,licenseInfo            # R1
{"licenseInfo":{"key":"apache-2.0","name":"Apache License 2.0","nickname":""},
 "visibility":"PUBLIC"}

$ git ls-files LICENSE && ls -l LICENSE                                   # R1
LICENSE
11357

$ git rev-list --left-right --count origin/master...HEAD                  # R1
0	0

$ python -c "import json;d=json.load(open('docs/submission/SUBMISSION.json'));print(d['demo_url'],d['video_url'])"
UNRESOLVED UNRESOLVED                                                     # R2, R4

$ python -c "import json;d=json.load(open('evidence/deploy/acceptance.json'));print(d['generated_at'],d['verdict'])"
2026-08-12T16:17:12Z NOT PROVEN                                           # R2

$ python scripts/submission/check_submission_prose.py                     # R3, R4
  FAIL  docs/submission/VIDEO-KIT.md:179: [SUB-06-migration-count]
  1 submission-prose violation(s), 0 claim-hygiene violation(s)
  -> 0 violations in docs/submission/DEVPOST.md

$ git log --reverse --format='%H %aI %cI' | head -1                       # R5
f80fefd49168cf52b2aa22a75396d419d67345be 2026-08-05T22:47:47+10:00 2026-08-05T22:47:47+10:00

$ git rev-list --count HEAD                                               # R5
47

$ python -c "import json;d=json.load(open('evidence/tool-usage/crdb-features.json'));print(d['totals'])"
{'rows': 14, 'by_verdict': {'EXERCISED': 12, 'DESIGNED': 2, 'NOT-AVAILABLE': 0},
 'by_kind': {'tool': 4, 'feature': 10, 'service': 0}}                     # R6, R8

$ python -c "import json;d=json.load(open('evidence/deploy/aws-live.json'));print(d['verdict'],d['calls_failed'],d['total_seconds'])"
AWS BEDROCK EXECUTED [] 1.75                                              # R7

$ python -c "import json;d=json.load(open('evidence/tool-usage/aws-services.json'));print(d['totals']['by_verdict'])"
{'EXERCISED': 3, 'DESIGNED': 8, 'NOT-AVAILABLE': 1}                       # R7, R8

$ python scripts/submission/capture_tool_evidence.py --check              # R8
tool-usage census is STALE:
  evidence/tool-usage/crdb-features.json: same length (30253 bytes), different content;
    first difference at line 14:  on disk: "files_scanned": 7388,
                                  fresh:   "files_scanned": 7390,
  (exit 1)
```

### Two counts that legitimately disagree, and why

§2's generated row says **10 AWS services**; the census in R7 says **12**. Both are right
and they are counting different things. The gate holds a fixed table of ten AWS service
names and asks `docs/TOOL-USAGE.md` which of them it mentions; the census walks the tree and
emits one row per *distinct use*, so Bedrock appears three times — inference, embeddings and
Rerank. The same arithmetic explains "2 AWS service(s) marked as having run" against the
census's 3 EXERCISED rows: the gate counts the name **Amazon Bedrock** once.

A reader who spots a discrepancy between two numbers in this file should get this paragraph
rather than a silent reconciliation, because the alternative is to make one of the two
instruments lie.

### Why R2 is the only Stage One row still open

R1 and R2 are the **Stage One pass/fail** gates: a submission that fails either is not
assessed at all. **R1 closed on 2026-08-12.** R4 is a real gap and is not a Stage One gate.

What remains is one command the founder runs and one film the founder records:

```bash
# R2 — the apply; it prints the hostname that becomes demo_url
MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account <id>

# R2 — and then the half an apply cannot deliver: the app has to ANSWER
python scripts/deploy/demo_acceptance.py --url <the URL>
python scripts/submission/check_submission_ready.py --check-urls

# R4 — the shoot
python scripts/submission/seed_demo_state.py     # the state on camera
# record, upload UNLISTED, paste the URL into SUBMISSION.json
```

Writing a hostname into `demo_url` before **both** R2 halves hold would turn §2 green and
still hand a judge a page that answers `500`. That is the one failure `SUBMISSION.json`
exists to prevent, and it is why `--check-urls` fetches rather than trusts.

---

## 2 · The generated table

**The status column is not typed. It is generated.**

<!-- BEGIN GENERATED: check_submission_ready.py --markdown -->
Generated `2026-08-12T16:50:54Z` by `python scripts/submission/check_submission_ready.py --markdown`.
Exit code at that instant: **1**, with **3** unresolved rows: `remote_sync`, `demo_url`,
`video_url`. Two of those three are the founder's — an apply and a shoot. The third is a
dirty working tree and clears on a commit.

| Row | Requirement | Status | Observed | Evidence | Re-derive with |
|---|---|---|---|---|---|
| `licence_file` | 1 - public repo with an open-source LICENSE file | **PASS** | 11357 bytes, reads as Apache-2.0 | `LICENSE`, `LICENSES/`, `docs/submission/LICENCE-CENSUS.md` | `ls -l LICENSE && python scripts/qa/check_reuse.py` |
| `remote_sync` | 1 - public repo with an open-source LICENSE file | **WARN** | in sync with origin/master, but 76 path(s) are uncommitted and will not be published: .github/actions/setup-workspace/action.yml, .github/workflows/aws-evidence.yml, .github/workflows/ci.yml, .github/workflows/cloud-verify.yml, and 72 more (20 under docs/, 15 under evidence/, 10 under .github/, 10 under scripts/, 10 under verticals/, and 5 other top-level path(s)) | the remote itself - there is no local artefact for this row | `git rev-list --left-right --count origin/master...HEAD` |
| `repo_public` | 1 - public repo with an open-source LICENSE file | **PASS** | PUBLIC [gh repo view Shaugato/mainline --json visibility, asked live], repo_url https://github.com/Shaugato/mainline | `qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md` | `gh repo view Shaugato/mainline --json visibility` |
| `demo_url` | 2 - a URL to a functional demo app | **FAIL** | demo_url is UNRESOLVED | `docs/submission/SUBMISSION.json` key `demo_url` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `video_url` | 4 - demo video under 3 minutes on YouTube or Vimeo | **FAIL** | video_url is UNRESOLVED | `docs/submission/VIDEO-KIT.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `devpost_description` | 3 - text description of the features | **PASS** | docs/submission/DEVPOST.md: 40515 bytes, 200 non-blank lines | `docs/submission/DEVPOST.md` | `python scripts/submission/check_submission_prose.py` |
| `tool_usage` | 5 - documented CockroachDB and AWS usage (>=2 CRDB tools, >=1 AWS, >=1 run) | **PASS** | 4 CockroachDB tools, 10 AWS services; 2 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch); 21 of 21 cited artefacts present on disk | `docs/TOOL-USAGE.md`, `evidence/tool-usage/` | `python scripts/submission/capture_tool_evidence.py --check` |
| `judge_access` | 6 - free, unrestricted access for judges | **PASS** | resolved - credential required; how 463 chars, credentials_location 373 chars, and no credential value in the file | `docs/submission/SUBMISSION.json` key `judge_access`, `VERIFY.md` | `python scripts/submission/check_submission_ready.py --json` |
| `disclosure` | 7 - created in the submission window; pre-existing code disclosed | **PASS** | docs/submission/DISCLOSURE.md present (20445 bytes); 47 commits, all inside the window | `docs/submission/DISCLOSURE.md`, `evidence/provenance/commit-window.json` | `python scripts/submission/provenance_census.py --check` |
| `deadline` | deadline - 2026-08-18 17:00 EDT | **PASS** | 6d 4h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z) | the official rules page | `python scripts/submission/check_submission_ready.py` |
<!-- END GENERATED -->

**To regenerate this table**, replace everything between the two HTML comments above with
the output of:

```bash
python scripts/submission/check_submission_ready.py --markdown
```

Do not edit a cell by hand. A hand-edited status column is a claim with nothing behind
it, which is the one thing this repository is built not to ship.

### The `remote_sync` WARN is not noise, and it now names names

`HEAD` and `origin/master` are the same commit — `git rev-list --left-right --count` answers
`0 0` — so nothing that was ever committed here is missing from the server. That is why the
row is a `WARN` and not a `FAIL`.

What it still reports is **uncommitted** work: paths edited on this disk and therefore
invisible to a judge, who sees only what was pushed. The row used to print a bare
count, which told a reader that something was wrong and nothing about what, leaving them to
run `git status` themselves — the exact work the row exists to have already done. It now
names the first paths and buckets the remainder by top-level directory, and `--json` carries
the list under `rows[].detail.dirty_paths`.

The count moves with every edit, which is why it lives in the generated table above and not
in this sentence. It clears the moment those paths are committed and pushed.

---

## 3 · Requirement by requirement

### R1 — a public repository with an open-source licence

**MET, as of 2026-08-12.** Three separate facts have to hold, and the gate keeps them as
three rows because they fail independently and are fixed by different commands.

| fact | row | state on 2026-08-12 |
|---|---|---|
| a licence file exists at the root, and is tracked | `licence_file` | **met** — Apache-2.0, 11 357 bytes; `git ls-files LICENSE` answers |
| the tree on the server is the tree on this disk | `remote_sync` | **partial** — `HEAD` == `origin/master`, nothing unpushed; the uncommitted-path count and the paths themselves are in §2's generated row, because they move |
| the repository is publicly readable | `repo_public` | **met** — `visibility: PUBLIC` |

The flip happened, and the audit that gated it returned READY first: 8 checks, 7 passed, 0
failed, **0 unresolved findings** over 7 314 tracked paths. The AWS account id was masked at
`HEAD` before the flip.

The `repo_public` row reports **both** its facts on every path, whichever fails first: the
visibility *and* whether `repo_url` is written. It now also asks GitHub about
**the slug inside `repo_url`** rather than about whatever remote this checkout happens to
carry — before that change a `repo_url` pointing at one repository could have been blessed
`PUBLIC` by a clone of another, and a fork would have reported its upstream.

**The answer is never cached.** Visibility is the one fact in this gate that a person can
change from a browser between two runs, in either direction, so it is read live on every
run — from `$GITHUB_EVENT_PATH` inside Actions (no token, no network) or from `gh` on a
machine with a logged-in CLI. When neither can answer, the row is `NOTRUN`. It is never
assumed public, and it is never read back from `qa/public-readiness.json` or from a previous
report.

Re-derive: `gh repo view Shaugato/mainline --json visibility` — a submitted state prints
`PUBLIC`, and it does.

### R2 — a URL to a functional demo, free and unrestricted for judges

**UNMET, and precisely so.** Three things are named in the rule and they are in three
different states.

* **The origin — missing.** Nothing is deployed. The demo URL will be a public **Lambda
  Function URL** — HTTPS on an AWS-issued certificate, no account verification needed —
  because a real `terraform apply` on 2026-08-10 was refused by AWS with `AccessDenied: Your
  account must be verified before you can add new CloudFront resources`, quoted verbatim in
  `docs/deploy/RUNBOOK.md`. CloudFront is therefore excluded from the plan, and the plan
  reads 11 to add, 0 to change, 0 to destroy at an estimated ~USD 0.02/month.
* **The acceptance — failing, and named.** `evidence/deploy/acceptance.json` reads
  `NOT PROVEN` at `2026-08-12T16:17:12Z` against a local Function-URL emulator serving the
  unmodified handler against the live Cloud database. The 404 on `POST /v1/demo/gate-run`
  recorded on 2026-08-10 is **gone** — the route is reachable, seventeen routes are
  registered — and it now fails further in, on `KeyError: 0` in `demo_gate_run`, twice. That
  artefact moves as the defect is fixed. **Where this section and that file disagree, the
  file is right**; re-read it, or re-derive with `python scripts/deploy/demo_acceptance.py`.
* **"Free and unrestricted for judges" — answered.** `judge_access` in
  `docs/submission/SUBMISSION.json` names two paths a judge can take today against the live
  ledger, and `evidence/deploy/judge-access.json` measured both directions of the read-only
  login: **14 of 14** `mainline_audit` views readable, **11 of 11** base-table and write
  attempts refused with the expected SQLSTATE, verdict `PROVEN`, `failures: []`. The demo
  URL itself, when it exists, will need no credential at all — the plan sets
  `authorization_type = NONE`.

Re-derive: `python scripts/submission/check_submission_ready.py --check-urls`, which fetches
the URL and requires HTTP 200 rather than trusting that it was pasted correctly.

### R3 — a text description of the features

**MET as a source document.** `docs/submission/DEVPOST.md` is checked for size, structure
and unfinished-sentence markers by the `devpost_description` row, and its prose is checked
against nine SUB rules by `scripts/submission/check_submission_prose.py`, which reports zero
violations in it.

The gate deliberately does **not** fail this row because `DEVPOST.md` carries the literal
`UNRESOLVED` beside the two open URLs in its paste-order table. That marker is honest, and
it is already counted by the `demo_url` and `video_url` rows. Counting it twice would turn
one fact into two red rows and make this table overstate how much is wrong.

### R4 — a video under three minutes on YouTube or Vimeo

**UNMET, and the gap is a film, not a document.** The kit exists and is CI-validated; the
film does not exist. The gate also checks the *host*: a URL that is not on YouTube or Vimeo
fails, because the rules name those two.

One defect in the kit is open and is not this document's to fix:
`check_submission_prose.py` fails `VIDEO-KIT.md:179` under `SUB-06-migration-count`, because
the kit quotes a migration count instead of re-deriving one. The rule exists because the
number genuinely moves — an earlier committed proof records 246 of 261 applied with 15
failures; a run on this machine on 2026-08-12 recorded **271 of 271 applied, 0 failed**, and
the correct instruction is to read the count the run produces.

### R5 — a new project created inside the submission window

**MET.** The `disclosure` row re-reads the git history and checks **both** the author date
and the committer date of every one of the 47 commits against `2026-08-05` … `2026-08-18`
evaluated in EDT — one date is half a check, because a rebase moves one and not the other.

Re-derive: `python scripts/submission/provenance_census.py --check`, whose output is
committed at `evidence/provenance/commit-window.json`.

### R6, R7, R8 — the tools, the services, and how

**All three MET**, and the `tool_usage` row asserts the *floor*, not the ceiling, so it
stays honest if a tool is later withdrawn from the document.

That row asks two questions that counting names never answered:

* at least one AWS service must be marked **EXERCISED or EXECUTED**, so a table of pure
  intent cannot pass — it is the check that would have failed on 2026-08-10, when twelve
  AWS services were named and none had run;
* at least one `evidence/...` artefact the document cites must **exist on disk**, so a
  citation is a file a reader can open rather than a path somebody typed. Today: 21 of 21
  cited artefacts present.

**The regeneration R8 owes is real and is not hidden.**
`python scripts/submission/capture_tool_evidence.py --check` rebuilds both censuses from the
source tree and exits 1 if the committed files differ. It exits 1 today, on one field in
each file — `files_scanned`, 7 388 committed against 7 390 measured. Two files were added to
the tree after the census was taken. No verdict, count or citation moved. It is a
regeneration owed by the domain that owns the generator, and lowering the check to buy a
green is forbidden.

### Requirement 6 of the gate — free, unrestricted access, and no credential in this file

**Resolved.** All three `judge_access` members are answered:

| member | value shape | why it is what it is |
|---|---|---|
| `required` | `true`, a real JSON boolean | reading **our** ledger takes **our** login; the gate refuses the string `"false"`, which is truthy in most languages that will read this file |
| `how` | 463 characters naming both paths and the artefact that measured them | a sentence a judge can act on without asking us a question |
| `credentials_location` | 373 characters, a **pointer** | it names the submission form's credentials field and the command that generates the value — never the value |

**No credential value is ever written into `SUBMISSION.json`.** The file is world-readable
now, so the gate enforces this rather than trusting it: it scans every value for eight
credential shapes, for keys whose *names* say the value is a secret, and for bare
high-entropy blobs, and it fails the row if any of them matches — even if every URL beside
it is resolved.

It also refuses values that are *present but empty of content*: a `how` under 48 characters,
a `credentials_location` under 24 when a credential is required, a placeholder token in
either, or the contradiction `required: true` with `credentials_location: "none"`. Resolving
a field and answering it are different things.

---

## 4 · `docs/submission/SUBMISSION.json` — the schema, documented here because JSON holds no comments

One file is the single write point for every unresolved submission fact. Ten documents and
one workflow read it; nobody writes a URL into prose.

**Schema version 2**, bumped when the `notes` object was added. No existing key has changed
meaning since, and a version is bumped when a key is added or changes meaning — never when
a value changes.

| key | type | meaning |
|---|---|---|
| `schema_version` | integer | bumped when a key is added or changes meaning, never when a value changes |
| `schema_documented_in` | string | points back at this section |
| `read_by` | array of strings | every program and document that reads the file |
| `unresolved_sentinel` | string | the literal an unresolved field holds: `UNRESOLVED` |
| `never_write_a_credential_here` | string | the standing rule, in band, where a person editing the file will see it |
| `a_field_is_resolved_only_when_it_is_proven` | string | why two fields still hold the sentinel: the fact is not true yet, not untyped |
| `demo_url` | string | rule R2. `UNRESOLVED` until deployed **and** answering |
| `repo_url` | string | the URL a judge opens. **Resolved**, and the repository behind it is public |
| `video_url` | string | rule R4. `UNRESOLVED` until uploaded |
| `judge_access.required` | boolean, or `UNRESOLVED` | whether a judge needs a credential at all |
| `judge_access.how` | string, ≥ 48 chars | one sentence a judge can act on |
| `judge_access.credentials_location` | string, ≥ 24 chars when required | **a pointer to where a credential lives, never a credential** |
| `notes.{repo_url,demo_url,video_url}` | string | for each field: what is true today and the literal command that changes it |
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

**`notes.repo_url` was rewritten on 2026-08-12.** It used to say the URL answered 404 to
everyone but the owner. That sentence described a private repository and stopped being true
when the flip landed; it is now the measurement, dated.

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

The run also prints a **census of unasked questions**, even when it is zero — today,
`0 rows were NOT CHECKED: every question above was asked and answered`. A reader told how
many questions went unasked can weigh the verdict; a reader told nothing assumes the answer
was no.

The repository visibility row is where this matters. It reads the answer from one of two
sources and names which one answered:

1. `$GITHUB_EVENT_PATH` — inside GitHub Actions, the event payload already carries
   `repository.visibility`. No token, no network, no `gh`. This is what lets the CI lane
   assert the row without a credential.
2. `gh repo view <owner/name> --json visibility` — on a machine with a logged-in CLI, asked
   live, about the slug inside `repo_url`.

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
`rev-list` parsing, **`git status --porcelain` parsing including renames and quoted paths**,
**the `repo_url` → slug derivation**, URL classification, both visibility sources, the clock
arithmetic, description triviality, tool counting, the commit-window check including the
rebase case, the `NOTRUN` census, and the invariant that only `PASS` resolves a row.

**That lane is green at `HEAD`** — run `31604458802` on `1d41442`, conclusion `success`.
It was red on 2026-08-11 for a reason that had nothing to do with this document, a
repo-wide licence-header spelling migration recorded in `docs/CI-STATE.md`; that ratchet was
never lowered to buy the green. Many other lanes are still red on purpose, and
[`../CI-STATE.md`](../CI-STATE.md) says which and why.

---

## 7 · Related documents

Read these two first. They are the differentiator, and the rest of this directory points at
them rather than softening them.

* [`../HONESTY.md`](../HONESTY.md) — what is broken, published rather than hidden, every
  number carrying an inline reference to the artefact that produced it, and a test that
  fails the build when a number and its source disagree.
* [`../CI-STATE.md`](../CI-STATE.md) — every workflow's real conclusion, with run ids,
  including the lanes that are red on purpose and must stay red.

Then:

* [`JUDGE-START.md`](JUDGE-START.md) — ninety seconds, then five minutes, for a judge who
  has just landed on the repository.
* [`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md) — the same five minutes as a recording,
  including every way they go wrong.
* [`RUNBOOK.md`](RUNBOOK.md) — the founder's numbered D-day list, every step a literal
  command with its expected output.
* [`DEVPOST.md`](DEVPOST.md) — the description, field by field, in paste order, with one
  section per judging criterion.
* [`DISCLOSURE.md`](DISCLOSURE.md) — R5, and the research repository.
* [`PUBLIC-READINESS.md`](PUBLIC-READINESS.md) — what had to be true before the flip.
* [`VIDEO-KIT.md`](VIDEO-KIT.md) — R4's kit.
* [`JUDGING-AXES.md`](JUDGING-AXES.md) — the per-axis map a judge scores against.
* [`../TOOL-USAGE.md`](../TOOL-USAGE.md) — R6, R7 and R8.
