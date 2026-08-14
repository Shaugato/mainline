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
everything is MET **four days** before the deadline (`4d 11h` remained when the gate was last
run on 2026-08-14; `4d 19h` eight hours earlier the same day), with nothing deployed and no
film shot, would be the single least believable
file in the repository. That sentence read "six days" when it was written on 2026-08-12; the
clock is the one number here that moves without anybody editing anything, which is why it is
generated in §2 and only paraphrased here.

---

## 0 · The state on 2026-08-14, in four sentences

*This section was headed "the state on 2026-08-12" and is re-derived here rather than
replaced: where a figure moved, both figures are given and the later one is dated.*

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

**And one fact that landed after every other sentence in this file was written: the
product's own tests have now run against a real CockroachDB in CI, for the first time.**
`.github/workflows/cluster-tests.yml` starts a pinned `cockroachdb/cockroach:v26.2.5`
container and runs the demo-api suite at `--crdb=reuse`. GitHub Actions run
[`31735341117`](https://github.com/Shaugato/mainline/actions/runs/31735341117), workflow
`cluster-tests`, `headSha eefae1c`, created `2026-08-13T19:20:30Z`, measured:

```
cluster lane: 528 collected, 518 executed, 10 skipped, 1 failed, 0 errored
1 failed, 517 passed, 10 skipped in 154.21s (0:02:34)
```

**That run's conclusion is `failure`, and this document is not going to dress it up.** Until
it existed, all eighteen workflows passed `--crdb=none`, so every cluster-backed test in the
product skipped and four separate NO-GO verdicts were reached against a suite that had never
executed. **The residual is the part worth reading.** Ten tests skipped against a ceiling of
**1** (`qa/cluster-known-red.json#floor.max_skipped`, beside `min_executed: 440`), and the
lane refuses that in its own words: *"A skip here means the suite could not reach the cluster
this job started, and a skip is indistinguishable from a green tick on a dashboard."* The ten
are the tree-reading halves of `test_response_contract.py` and `test_static_site.py`, which
read `out/lambda/mainline-demo-api-arm64.zip` — a `.gitignore`'d build output (`.gitignore:9`)
that this lane never builds, so the assertions did not run. Their skip text says so and
refuses the obvious shortcut: *"the packer's input tree is deliberately NOT accepted as a
stand-in."* The fix is to build the package in the lane, not to raise the ceiling — the
ceiling is correct and **`max_skipped` may fall and must never rise.**

**None of this changes a verdict in §1.** It is recorded because R6 and R8 rest on a database
this repository can now be seen to exercise in CI rather than only on a laptop, and because a
judge who reads "the tests pass" without reading which ones ran has been told nothing.

---

## 1 · The rules, one row each

Every **Deciding artefact** cell holds a literal command, a path in this repository, or
both. No row's verdict rests on a sentence written here. **There are two transcripts under
the table**: what those commands printed on this machine on 2026-08-12, and — kept beside it
rather than in place of it — the 2026-08-14 re-derivation of every line that moved, with the
authority that decided each one named.

| # | Rule | Verdict | Deciding artefact | What it says |
|---|---|---|---|---|
| **R1** | Public repository with an open-source licence | **MET** | `gh repo view Shaugato/mainline --json visibility,licenseInfo` · `git ls-files LICENSE` · `LICENSE` · `docs/submission/LICENCE-CENSUS.md` | **Both halves met.** Public half: `visibility` is `PUBLIC`. Licence half: `LICENSE` is tracked (`git ls-files LICENSE` answers `LICENSE`), 11 357 bytes, reads as Apache-2.0, and GitHub independently resolves `licenseInfo.key` to `apache-2.0`. *The tree behind the URL was the audited tree when this cell was written on 2026-08-12: `git rev-list --left-right --count origin/master...HEAD` answered `0 0`. Re-derived 2026-08-14 it answers `0<TAB>4` — four commits are here and on no server — which is why `remote_sync` is a `FAIL` in §2 and clears on a push. R1's own two facts, a public repository and a tracked open-source licence, are unaffected: both are true of the tree the server already carries.* |
| **R2** | A URL to a functional demo, free and unrestricted for judges | **UNMET — two halves, both open, for different reasons** | `docs/submission/SUBMISSION.json` → `demo_url` · `evidence/deploy/acceptance.json` · `evidence/deploy/terraform-plan-furl.txt` | **The origin does not exist.** `demo_url` holds the literal `UNRESOLVED`; `terraform apply` has never been run, so there is no MAINLINE Lambda, Function URL or bucket in the account. The plan that would create it is committed and reads **`Plan: 24 to add, 0 to change, 0 to destroy.`** at `evidence/deploy/terraform-plan-furl.txt:843` — **11** resources in `module.api[0]` and **13** in `module.guard[0]`, the cost guard that `infra/envs/demo/main.tf:631` instantiates — with `authorization_type = "NONE"` at `furl.txt:351`, in `ap-southeast-1`. **The app does not yet answer.** `acceptance.json`, generated `2026-08-13T01:47:58Z`, reads `NOT PROVEN` with **10** named failures: both runs now reach beat 4 and are refused `23503 disposition_signer_credential_id_fkey`, and neither carries a `clearance_digest`. Nothing in that file was relaxed to reach a green. **The access half IS answered** — see the row below the table. |
| **R3** | A text description of the project's features | **MET** | `docs/submission/DEVPOST.md` · `python scripts/submission/check_submission_prose.py` | Re-derived 2026-08-14, later the same day: **53 343 bytes, 219 non-blank lines, 8 110 words, 2 fenced blocks** (`wc -c`, non-blank line count, whitespace-split words, and lines beginning with a triple backtick ÷ 2). Over the fifteen **paste blocks only** — which is what a judge reads — the page's own one-liner returns `15` blocks, `6 583` words, and an elevator pitch of `163` characters against a cap of `200`. The prose gate scans it against nine SUB rules and the claim-hygiene table and reports **0 violations in this file**. *This cell read `40 515 / 200 / 6 175 / 5` on 2026-08-12 and `46 885 / 209 / 7 165 / 2` earlier on 2026-08-14. The page grew when Limitations took six more gaps. The `5` fenced blocks never reproduced: no derivation attempted on this machine returns it, and rather than keep a figure that cannot be re-derived, the count and the command that produced it are both given above.* (The gate now exits **0** on the surfaces it scans: `submission prose OK`, `claim hygiene OK`, with the three `docs/HONESTY.md` `[HYG-sha-literal]` reds closed by that file's owner under RULING 5. It previously exited 1 on them; the rule was not narrowed.) |
| **R4** | A demo video under three minutes, on YouTube or Vimeo | **UNMET** | `docs/submission/SUBMISSION.json` → `video_url` · `docs/submission/VIDEO-KIT.md` · `verticals/mainline/demo/script/SHOT-LIST.yaml` | `video_url` holds `UNRESOLVED`. The kit exists — VO, timings, seeded state, the sentences that may not be said on camera — and `.github/workflows/claims.yml` runs the shot-list validator, so a script that drifts past the three-minute budget is a red build rather than a discovery made during the upload. Two facts a reader should have. **Nothing in this repository can resolve this row.** And the kit defect this cell used to carry is **closed**: on 2026-08-12 `check_submission_prose.py` failed `VIDEO-KIT.md:179 [SUB-06-migration-count]`; re-run on 2026-08-14 the same program reports `submission prose OK` — **0** SUB violations across the 14 files it scans. *Earlier on 2026-08-14 it still exited `1` on three `docs/HONESTY.md` `[HYG-sha-literal]` reds; later the same day it exits **`0`**, because that file's owner closed them with the rule's own `claim-hygiene: quoting` escape hatch under RULING 5. The rule was not switched off, no scope list gained an entry, and the SHA is preserved so the two commands beside it still reproduce.* |
| **R5** | A new project, created inside the submission window | **MET** | `docs/submission/DISCLOSURE.md` · `evidence/provenance/commit-window.json` | First commit `f80fefd`, authored **and** committed `2026-08-05T22:47:47+10:00` — inside the window, which opened `2026-08-05`. All **86** commits pass (`git rev-list --count HEAD`, re-derived 2026-08-14 later the same day; this cell said `47` on 2026-08-12 and `80` earlier on 2026-08-14 — it is a count of commits, so it rises on its own and the gate re-reads the history rather than this cell), and the check tests **both** the author date and the committer date, because a rebase moves one and not the other. The separate, earlier research repository is disclosed and holds no product code. |
| **R6** | At least two CockroachDB tools | **MET** | `docs/TOOL-USAGE.md` Part 1 · `evidence/tool-usage/crdb-features.json` | Four tools documented and **three carry an EXERCISED verdict in the census**: the database itself (v26.2.5, `evidence/gate-refusal/`, a real refusal on a real cluster), CockroachDB Cloud with the `ccloud` CLI (`evidence/deploy/cloud-chain.json`), and the Managed MCP Server (`evidence/deploy/judge-run.json`: 15 of 16 pack questions PASS over `https://cockroachlabs.cloud/mcp`). The fourth, Agent Skills, reads DESIGNED and is not counted. The floor is two and it is cleared without the third. |
| **R7** | At least one AWS service | **MET** | `evidence/deploy/aws-live.json` · `evidence/aws/probe/` · `evidence/tool-usage/aws-services.json` | Bedrock **executes** in `ap-southeast-2`. Four live calls, `calls_failed: []`, every one HTTP `200`, each with the AWS request id it returned: `sts:GetCallerIdentity` `04018eca-…`, `bedrock:ListFoundationModels` `d8c940e8-…`, `bedrock-runtime:InvokeModel` `b4d826e9-…` (Titan v2, a 1024-dimension embedding at L2 norm `1.0`), `bedrock-runtime:Converse` `3c7a283c-…` (Claude Haiku 4.5, `end_turn`). Total 1.75 s; the file's own verdict is `AWS BEDROCK EXECUTED`. The census marks **3 of 12** AWS rows EXERCISED, 8 DESIGNED because nothing is deployed, and 1 NOT-AVAILABLE because Bedrock Rerank is genuinely absent in the region. |
| **R8** | Documentation of **which** CockroachDB tools and AWS services, and **how** | **MET, with a regeneration owed** | `docs/TOOL-USAGE.md` · `evidence/tool-usage/` · `python scripts/submission/capture_tool_evidence.py --check` | `TOOL-USAGE.md` is **92 665** bytes (80 819 on 2026-08-12, 87 355 earlier on 2026-08-14; it grew by each wave's corrections). The CockroachDB census holds 14 rows — 4 tools and 10 engine features accounted separately, 12 EXERCISED and 2 DESIGNED; the AWS census holds 12 service rows. Every row carries a verdict, a `file:line` that does the work, and an `evidence/` artefact or an explicit "none — not applied"; the gate confirms **24 of 24 cited artefacts are present on disk** — `21 of 21` until 2026-08-14, when the Cloud chain, the Cloud seed and the 2026-08-14 gate-refusal proof were cited by name. **The count rose and the denominator rose with it**, which is the only direction that means anything: the owed Cloud gate-run artefact is deliberately *not* named on that page, because a citation of a file that does not exist would have made this read `24 of 25`. `capture_tool_evidence.py --check` re-derives the counts from the tree with no network and no credential, and **exits 2 today, not 1** — and the reason changed as well as the number. On 2026-08-12 it exited `1` on one stale field (`files_scanned`, 7 388 committed against 7 390 fresh). On 2026-08-14 it refuses earlier and harder: **two anchors in `evidence/tool-usage/aws-services.json` have drifted off their subject** — `aws_lambda` cites `infra/modules/demo-api/main.tf:333` for `authorization_type` and that line now reads `handler = "mainline_demo_api.app.handler"`; `aws_ssm_parameter_store` cites `:215` for `ssm:GetParameter` and that line now reads `#`. *`scripts/aws/verify_evidence.py` failed the same two under `[CEN-ANCHORS]` when this cell was written; re-run later on 2026-08-14 it passes — `1016` assertions across `40` of `40` invariants — because it reads the JSON, and the JSON was edited to `:432`/`:280` while the generator that produces it still declares `:333`/`:215`. **Two programs that agreed now disagree, and the one still refusing is the one reading the authoritative side.** See "the regeneration R8 owes" below.* The generator writes nothing while an anchor is drifted, so **whether `files_scanned` is still fresh is `UNRESOLVED` today** — `--print` refuses too, and a figure nobody can re-derive on this machine does not go in this cell. That is a regeneration owed on `evidence/tool-usage/`, it is owned by the domain that owns the generator, and **the two anchors are the tree moving under a citation, which is the defect the census's own `anchor_must_contain` rule was added to catch.** It caught it. |

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

### The re-derivation on 2026-08-14 — every line above that moved, and which side moved

**The transcript above is kept.** It is what this machine printed on 2026-08-12 and deleting
it would leave the corrections in §1 with nothing to correct. Below is the same set of
commands re-run on 2026-08-14 at HEAD `eefae1c`. **Where a document and an artefact
disagreed, the artefact won and the prose moved** — the rule is stated in
`docs/deploy/terraform-plan.md` §0.1 (*"The committed plan artefact is authoritative and this
prose is derived"*) and enforced by
`tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`,
whose assertion ends *"Do NOT edit the evidence file to match the documents."* No file under
`evidence/` or `qa/` was touched to produce any line below.

```console
$ grep -n 'Plan: ' evidence/deploy/terraform-plan-furl.txt                 # R2
843:Plan: 24 to add, 0 to change, 0 to destroy.

$ grep -c 'will be created' evidence/deploy/terraform-plan-furl.txt        # R2 - the split
24                       # 11 under module.api[0], 13 under module.guard[0]

$ sed -n '351p' evidence/deploy/terraform-plan-furl.txt                    # R2
      + authorization_type = "NONE"

$ python -c "import json;d=json.load(open('evidence/deploy/acceptance.json'));print(d['generated_at'],d['verdict'],len(d['failures']))"
2026-08-13T01:47:58Z NOT PROVEN 10                                         # R2

$ python scripts/submission/check_submission_prose.py ; echo "exit=$?"     # R3, R4
  FAIL  docs/HONESTY.md:724: [HYG-sha-literal]
  FAIL  docs/HONESTY.md:746: [HYG-sha-literal]
  FAIL  docs/HONESTY.md:749: [HYG-sha-literal]
  3 claim-hygiene violation(s)
  submission prose OK          # 0 SUB violations - VIDEO-KIT.md:179 is FIXED
  exit=1

$ git rev-list --count HEAD                                               # R5
80

$ python scripts/submission/capture_tool_evidence.py --check ; echo "exit=$?"   # R8
REFUSING: anchor resolves but has drifted off its subject.
  AWS service: aws_lambda -> infra/modules/demo-api/main.tf:333
      expected the line to contain: 'authorization_type'
      the line actually reads:      'handler       = "mainline_demo_api.app.handler"'
  AWS service: aws_ssm_parameter_store -> infra/modules/demo-api/main.tf:215
      expected the line to contain: 'ssm:GetParameter'
      the line actually reads:      '#'
exit=2

$ gh run view 31735341117 --json name,headSha,conclusion,createdAt        # §0
{"conclusion":"failure","createdAt":"2026-08-13T19:20:30Z",
 "headSha":"eefae1c01a3d56d0db1640b8e50cad7bdda432e9","name":"cluster-tests"}
```

**Three of those lines are the whole point of this document.** `Plan: 24` had been written
here as `11 to add` while `DEVPOST.md` — the sibling file a judge reads in the same sitting —
already said `24` with the `11 + 13` split. Two submission documents in one directory
disagreed about a number a stranger settles with one `grep`. The 2026-08-12 cell was not
wrong when it was written; it was written before `module.guard[0]` was wired into
`infra/envs/demo/main.tf:631`, and nothing re-read it afterwards. **That is the failure mode
this repository sells against, found in its own rules matrix**, and it is recorded here
rather than quietly overwritten.

**Two of the three checks that moved got WORSE, and they are not being softened.**
`capture_tool_evidence.py` went from exit `1` to exit `2`; `acceptance.json` went from 4
named failures to 10. Both are the instruments getting sharper against a moving tree, which
is what they are for.

### Two counts that legitimately disagree, and why

§2's generated row says **10 AWS services**; the census in R7, and the heading of
`docs/TOOL-USAGE.md` Part 2, say **twelve**. Both are right and they are counting different
things. The gate holds a **fixed table of ten AWS service names** — `AWS_SERVICES` at
`scripts/submission/check_submission_ready.py:201` — and asks `docs/TOOL-USAGE.md` which of
them it mentions, so ten is its **ceiling**, not a census, and it prints `10` because that
page names all ten. The census walks the tree and
emits one row per *distinct use*, so Bedrock appears three times — inference, embeddings and
Rerank — and `evidence/tool-usage/aws-services.json#totals.rows` is `12`. The same arithmetic
explains "2 AWS service(s) marked as having run" against the
census's 3 EXERCISED rows: the gate counts the name **Amazon Bedrock** once, and two of the
three EXERCISED rows are Bedrock.

**Which side would have moved if one had to.** Neither, and the question was asked rather than
assumed on 2026-08-14: the heading is *derived from the census*, so changing it to ten would
have moved this documentation away from the artefact it is checked against in order to agree
with an instrument measuring a different quantity. That is the forbidden direction. The
identical paragraph now stands in `docs/TOOL-USAGE.md` Part 2, because the discrepancy is
visible from either page and a reader should meet the arithmetic wherever they meet the
numbers.

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
Generated `2026-08-14T09:40:51Z` by `python scripts/submission/check_submission_ready.py --markdown`.
Exit code at that instant: **1**, with **3** unresolved rows: `remote_sync`, `demo_url`,
`video_url`. Two of those three are the founder's — an apply and a shoot. The third is a
working tree four commits ahead of `origin/master` with uncommitted paths, and it clears on a
push. **The same three rows, in the same states, as the 2026-08-12 and the earlier 2026-08-14
generations**: nothing in this wave resolved a URL, and nothing was meant to. `remote_sync`
moved from `WARN` to `FAIL` between those two runs because four commits landed here and on no
server; the gate was not tightened.

| Row | Requirement | Status | Observed | Evidence | Re-derive with |
|---|---|---|---|---|---|
| `licence_file` | 1 - public repo with an open-source LICENSE file | **PASS** | 11357 bytes, reads as Apache-2.0 | `LICENSE`, `LICENSES/`, `docs/submission/LICENCE-CENSUS.md` | `ls -l LICENSE && python scripts/qa/check_reuse.py` |
| `remote_sync` | 1 - public repo with an open-source LICENSE file | **FAIL** | 4 commits ahead of origin/master, 22 file(s) on this disk and on no server: .github/actions/build-demo-package/action.yml, .github/workflows/cluster-lane-bites.yml, .gitignore, collected.txt, and 18 more (6 under verticals/, 5 under docs/, 4 under tests/, 2 under .github/, 2 under qa/, and 3 other top-level path(s)) | the remote itself - there is no local artefact for this row | `git rev-list --left-right --count origin/master...HEAD` |
| `repo_public` | 1 - public repo with an open-source LICENSE file | **PASS** | PUBLIC [gh repo view Shaugato/mainline --json visibility, asked live], repo_url https://github.com/Shaugato/mainline | `qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md` | `gh repo view Shaugato/mainline --json visibility` |
| `demo_url` | 2 - a URL to a functional demo app | **FAIL** | demo_url is UNRESOLVED | `docs/submission/SUBMISSION.json` key `demo_url` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `video_url` | 4 - demo video under 3 minutes on YouTube or Vimeo | **FAIL** | video_url is UNRESOLVED | `docs/submission/VIDEO-KIT.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `devpost_description` | 3 - text description of the features | **PASS** | docs/submission/DEVPOST.md: 53343 bytes, 219 non-blank lines | `docs/submission/DEVPOST.md` | `python scripts/submission/check_submission_prose.py` |
| `tool_usage` | 5 - documented CockroachDB and AWS usage (>=2 CRDB tools, >=1 AWS, >=1 run) | **PASS** | 4 CockroachDB tools, 10 AWS services; 2 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch); 24 of 24 cited artefacts present on disk | `docs/TOOL-USAGE.md`, `evidence/tool-usage/` | `python scripts/submission/capture_tool_evidence.py --check` |
| `judge_access` | 6 - free, unrestricted access for judges | **PASS** | resolved - credential required; how 463 chars, credentials_location 373 chars, and no credential value in the file | `docs/submission/SUBMISSION.json` key `judge_access`, `VERIFY.md` | `python scripts/submission/check_submission_ready.py --json` |
| `disclosure` | 7 - created in the submission window; pre-existing code disclosed | **PASS** | docs/submission/DISCLOSURE.md present (20445 bytes); 86 commits, all inside the window | `docs/submission/DISCLOSURE.md`, `evidence/provenance/commit-window.json` | `python scripts/submission/provenance_census.py --check` |
| `deadline` | deadline - 2026-08-18 17:00 EDT | **PASS** | 4d 11h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z) | the official rules page | `python scripts/submission/check_submission_ready.py` |
<!-- END GENERATED -->

**To regenerate this table**, replace everything between the two HTML comments above with
the output of:

```bash
python scripts/submission/check_submission_ready.py --markdown
```

Do not edit a cell by hand. A hand-edited status column is a claim with nothing behind
it, which is the one thing this repository is built not to ship.

### The `remote_sync` row is not noise, it names names, and it changed status on 2026-08-14

**This section described a `WARN` and now describes a `FAIL`, and the change is a real one
rather than a stricter rule.** It read: *"`HEAD` and `origin/master` are the same commit —
`git rev-list --left-right --count` answers `0 0` — so nothing that was ever committed here is
missing from the server. That is why the row is a `WARN` and not a `FAIL`."* Re-derived on
2026-08-14, that command answers `0<TAB>4`: **four commits exist here and on no server**, so
the sentence above is no longer true of this tree and the row is correctly a `FAIL`. Nothing in
the gate was tightened; the tree moved.

What it reports on top of that is **uncommitted** work: paths edited on this disk and therefore
invisible to a judge, who sees only what was pushed. The row used to print a bare
count, which told a reader that something was wrong and nothing about what, leaving them to
run `git status` themselves — the exact work the row exists to have already done. It now
names the first paths and buckets the remainder by top-level directory, and `--json` carries
the list under `rows[].detail.dirty_paths`.

Both counts move with every edit and every commit, which is why they live in the generated
table above and not in this sentence. The row clears when the work is committed **and pushed**
— committing alone converts the dirty-path half into the ahead-of-origin half, which is why the
gate reports the two together and refuses on either.

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
  reads **`Plan: 24 to add, 0 to change, 0 to destroy.`** — `evidence/deploy/terraform-plan-furl.txt:843`,
  **11** in `module.api[0]` and **13** in `module.guard[0]`. *This bullet said `11 to add`
  until 2026-08-14. The 11 is real and is still there; it is the API module alone, and it
  stopped being the plan's total when the cost guard was wired in at
  `infra/envs/demo/main.tf:631`.* The estimate remains ~USD 0.02/month for the idle stack;
  what an unbounded flood would cost is `docs/deploy/COST-BOUND.md`'s subject, not this row's.
* **The acceptance — failing, and named.** `evidence/deploy/acceptance.json` reads
  `NOT PROVEN` at `2026-08-13T01:47:58Z` with **10** named failures, against a local
  Function-URL emulator serving the unmodified handler against the live Cloud database. Two
  earlier symptoms are **gone**: the 404 on `POST /v1/demo/gate-run` recorded on 2026-08-10,
  and the `KeyError: 0` in `demo_gate_run` recorded on 2026-08-12. Both runs now get all the
  way to **beat 4** and are refused there — `23503 disposition_signer_credential_id_fkey`,
  the server's own verdict `NOT PROVEN`, and no `clearance_digest` on the admission beat,
  because an `ADMITTED` with no server-computed exhibit is an assertion rather than evidence.
  **That is the last beat of the demo, so a judge cannot yet complete it.** That artefact
  moves as the defect is fixed. **Where this section and that file disagree, the file is
  right**; re-read it, or re-derive with `python scripts/deploy/demo_acceptance.py`.
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

**The kit defect this section carried is closed, and it is named rather than deleted.** On
2026-08-12 `check_submission_prose.py` failed `VIDEO-KIT.md:179` under
`SUB-06-migration-count`, because the kit quoted a migration count instead of re-deriving
one. Re-run on 2026-08-14 the same program prints `submission prose OK` — **0** SUB
violations across the 14 files it scans. The rule that caught it exists because the number
genuinely moves: an earlier committed proof records 246 of 261 applied with 15 failures, and
a run on this machine on 2026-08-12 recorded **271 of 271 applied, 0 failed**. The correct
instruction is still to read the count the run produces.

`check_submission_prose.py` nonetheless **still exits 1**, and the reason is somebody else's:
**3 claim-hygiene violations, all `docs/HONESTY.md` `[HYG-sha-literal]`** at lines 724, 746
and 749, where the honesty ledger quotes the git SHA `2dc5c86` in a transcript. That file is
under an absolute prohibition for this document's owner and was not touched. It is reported
here, in the same place the `VIDEO-KIT.md` finding was reported when it was open, because a
document that names other people's red rows and stops naming them the moment they become
inconvenient is not a matrix, it is a brochure.

### R5 — a new project created inside the submission window

**MET.** The `disclosure` row re-reads the git history and checks **both** the author date
and the committer date of every one of the **86** commits against `2026-08-05` … `2026-08-18`
evaluated in EDT — one date is half a check, because a rebase moves one and not the other.
*(This said `47` on 2026-08-12 and `80` earlier on 2026-08-14. It is a count of commits, so it
rises on its own; the row is generated and the gate re-reads the history, which is why nothing
here had to be believed.)*

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
  citation is a file a reader can open rather than a path somebody typed. Today: **24 of 24**
  cited artefacts present, up from `21 of 21` — the numerator and the denominator rose
  together, because three real artefacts were cited by name on 2026-08-14 and no path was
  typed for a file that does not exist.

**The regeneration R8 owes is real, is not hidden, and got bigger between 2026-08-12 and
2026-08-14.** `python scripts/submission/capture_tool_evidence.py --check` rebuilds both
censuses from the source tree and exits non-zero if the committed files differ.

| | 2026-08-12 | 2026-08-14 |
|---|---|---|
| exit code | `1` | **`2`** |
| what it refused on | `scan.files_scanned`, 7 388 committed against 7 390 measured, in each file | **`[CEN-ANCHORS]` — two anchors declared in `capture_tool_evidence.py` have drifted off their subject in `infra/modules/demo-api/main.tf`** |
| does a second program agree? | — | it did, then it stopped. `verify_evidence.py` failed the same pair and now **passes** at `1016` assertions over `40` of `40` invariants, because it reads the JSON and the JSON moved while the generator did not |
| the drift, exactly | — | `aws_lambda` → `infra/modules/demo-api/main.tf:333` was `authorization_type = var.url_authorization_type` and now reads `handler = "mainline_demo_api.app.handler"`; `aws_ssm_parameter_store` → `:215` was `actions = ["ssm:GetParameter"]` and now reads `#` |
| what it does NOT say | — | the exit-2 refusal happens *before* any staleness is computed, and `--print` refuses identically, so **`files_scanned`'s freshness is UNRESOLVED today** rather than assumed |

The subjects both moved down the same file: `authorization_type` is at
`infra/modules/demo-api/main.tf:432` today and `ssm:GetParameter` at `:280`.

**And a later measurement on 2026-08-14 sharpened what "owed" means here, so it is recorded
rather than smoothed over.** `evidence/tool-usage/aws-services.json` was edited in the working
tree to carry `:432` and `:280`, while `scripts/submission/capture_tool_evidence.py` — which
*declares* each row's `anchor` and `anchor_must_contain`, and from which that JSON is
generated — still declares `:333` and `:215`. So `--check` prints the old pair and **still
exits `2`**. **The generator's table is the authoritative side and the JSON is derived from
it**: moving the derived file alone does not close the finding, it makes two files disagree
about which line a reader should open. Nothing in this document was changed to agree with
either; the two line numbers a reader should trust are the ones the tree holds, `:432` and
`:280`, and the exit code they should trust is the one the program prints.

**Read what that refusal actually is before reading it as a failure.** `docs/TOOL-USAGE.md`
records that on 2026-08-12 five of the twelve AWS anchors were found by hand to have drifted
onto a closing brace or a blank line while *resolving perfectly*, and that each row was given
an `anchor_must_contain` substring precisely so the next drift would be a red gate rather
than an archaeology exercise. This is the next drift, and the gate is red. **The mechanism
worked.** What is owed is a regeneration of `evidence/tool-usage/`, by the domain that owns
the generator; no verdict, count or citation in §1 rests on the two drifted line numbers, and
lowering the check to buy a green is forbidden.

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

One file is the single write point for every unresolved submission fact. **`read_by` lists ten
entries: one program, eight documents and one workflow.** Nobody writes a URL into prose.

*That list held six entries until 2026-08-14 while claiming to be "every program and document
that reads the file", which was not true: `DEVPOST.md`, `JUDGING-AXES.md`, `VIDEO-KIT.md` and
`PUBLIC-FLIP-CHECKLIST.md` each tell a reader to take `demo_url` or `video_url` from that file
rather than from their own prose, and that is reading. It was widened rather than the claim
being softened. Paths that merely NAME the file in a sentence — `README.md`, `docs/CI-STATE.md`,
`docs/TOOL-USAGE.md`, `docs/deploy/JUDGE-PACK.md`, `docs/deploy/OBSERVABILITY.md`,
`scripts/deploy/demo_acceptance.py`, `scripts/deploy/local_furl.py` — are deliberately absent,
and the file says so in its own `read_by_is_every_reader_not_every_mention` key: a list that
counted mentions would stop being the list of things that break when a value there changes.*

**Schema version 2**, bumped when the `notes` object was added. No existing key has changed
meaning since, and a version is bumped when a key is added or changes meaning — never when
a value changes.

| key | type | meaning |
|---|---|---|
| `schema_version` | integer | bumped when a key is added or changes meaning, never when a value changes |
| `schema_documented_in` | string | points back at this section |
| `read_by` | array of strings | every program and document that **reads a value out of** the file — ten entries since 2026-08-14, not every file that names it |
| `read_by_is_every_reader_not_every_mention` | string | why the four documents added on 2026-08-14 belong on that list and why the paths that merely mention the file do not |
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

**That lane is green** — re-derived on 2026-08-14 with `gh run list --branch master`, whose
latest `submission` run is [`31728043734`](https://github.com/Shaugato/mainline/actions/runs/31728043734)
at `1a6e10a`, conclusion `success`. *(This sentence named run `31604458802` at `1d41442`,
which was the latest when it was written on 2026-08-12 and is not the latest now. A run id in
prose is a snapshot; the command beside it is the measurement.)*
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
