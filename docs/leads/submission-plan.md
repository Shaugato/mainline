<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SUBMISSION — the lead plan

**Measured 2026-08-10 against the working tree at `D:/CoackroachDBxAWS/mainline`, the live
local node `mainline-crdb` (CockroachDB CCL v26.2.5), and `github.com/Shaugato/mainline`
via `gh`.** Nothing below is quoted from another lead's report. Every number carries the
command that produced it.

Deadline **2026-08-18 17:00 EDT**. Eight days.

---

## 0 · The finding that reorders everything

I checked the repository a judge would actually see, not the one on this disk.

```
$ gh repo view Shaugato/mainline --json visibility,licenseInfo,homepageUrl
{"visibility":"PRIVATE","licenseInfo":null,"homepageUrl":""}

$ git rev-list --left-right --count origin/master...HEAD
0	2            # behind / ahead

$ git diff --name-only origin/master..HEAD | wc -l
98
```

**98 files are committed locally and have never been pushed.** Among them:

| path | on `origin/master`? |
|---|---|
| `scripts/proof/gate_refusal.py` | **no** |
| `conftest.py` | **no** |
| `qa/test-state.json` | **no** |
| `LICENSES/Apache-2.0.txt` | **no** |
| `docs/HONESTY.md` | **no** |
| `docs/release/QUICKSTART.md` | **no** |
| `packages/trappoint-testkit/pyproject.toml` | **no** |
| `evidence/gate-refusal/proof-*.json` | **no** |
| `README.md` | yes — **the older one, without the four commands** |

`docs/STATE-OF-THE-BUILD.md` §4.1 called this out when those paths were *untracked*. They
are tracked now — `git status --porcelain` returns zero lines — and the finding survived
the fix in a different form: they were committed and not pushed. Flipping the repository
public today publishes a tree in which `just prove` does not exist, `pytest` cannot
collect, `LICENSES/` is absent, and the README promises four commands that are not there.

**Consequence for sequencing.** Two of the three Stage One gates are `git push` and
`gh repo edit --visibility public`, and *both must happen after* the licence file lands,
not before. Flipping visibility is irreversible. Pushing is not mine to do unasked; it is
item 1 of the founder runbook (S10) and the submission-ready gate refuses while
`origin/master != HEAD`.

---

## 1 · Measured state, by requirement

Seven requirements are on the official rules page. Here is where each stands, measured.

| # | Requirement | State | Evidence |
|---|---|---|---|
| 1 | Public repo with an OSI LICENSE file | **FAIL ×2** — `visibility: PRIVATE`; no root `LICENSE` (`ls LICENSE*` → nothing) | `gh repo view`; `ls -la` |
| 2 | URL to a functional demo app | **FAIL** — `homepageUrl` empty, nothing deployed | `gh repo view` |
| 3 | Text description of features | absent as a submission artefact; the raw material is excellent | `README.md`, `docs/HONESTY.md` |
| 4 | Video < 3 min | **script, shot list and VO already exist and are CI-validated** — 25 shots, 171 s, 9 s headroom | `verticals/mainline/demo/script/SHOT-LIST.yaml`, `VO.md`, `.github/workflows/claims.yml` |
| 5 | Which CockroachDB + AWS services, **and how** | no such document | `docs/TOOL-USAGE.md` does not exist |
| 6 | Free, unrestricted judge access | designed (`VERIFY.md` Tier 3), not provisioned | `VERIFY.md` |
| 7 | Newly created in window; disclose pre-existing | true and undisclosed | first commit `f80fefd` **2026-08-05 22:47 +1000** |

### What is already strong, and must not be rebuilt

The video kit is **not** a greenfield job. `verticals/mainline/demo/script/` holds a locked
VO, two shot lists (submission cut 171 s, minimum-winnable 158 s), camera strings, a
generated cut diff and `validate_shotlist.py`, and `.github/workflows/claims.yml` runs the
validator so a shot list that drifts past budget is a red build. `verticals/mainline/demo/`
holds `REFUSAL-STRINGS.yaml` verified against the migrations that define each SQLSTATE, a
judge question pack with its own CI lane, and an honesty card generator. **S8 binds to
those files and adds only what a founder holding a microphone still lacks: the seeded
state, the exact commands, the environment, and the sentences he may not say.** S8 owns no
file under `verticals/`.

### Licence reality, counted

```
$ git grep -h -o -E "SPDX-License-Identifier: .*" | sed 's/.*: //' | sort | uniq -c | sort -rn
   1167 FSL-1.1-ALv2
    750 Apache-2.0
    375 LicenseRef-FSL-1.1-ALv2
     49 CC-BY-4.0
```

`LICENSES/` holds exactly two files: `Apache-2.0.txt` and `LicenseRef-FSL-1.1-ALv2.txt`.
So **1,167 files name a licence whose text is not in the tree**, and **49 name `CC-BY-4.0`,
whose text is not in the tree either**. Coverage, measured over all 7,120 tracked files:

```
header or .license sidecar : 2,602
UNCOVERED                  : 4,518   (4,461 of them .json, 4,369 under verticals/)
```

`.github/workflows/ci.yml` job `checkers` enumerates five programs and exits 1 if any is
absent. **`scripts/qa/check_reuse.py` is not on disk.** Every substantive job declares
`needs: [checkers]`, so *sixteen workflows are dead at job zero*. A public repository whose
Actions tab is entirely red is a Product Readiness failure a judge reads in ten seconds.

**Ruling L-1 — we do not mass-edit 1,167 headers.** Rewriting the bare `FSL-1.1-ALv2`
spelling to `LicenseRef-FSL-1.1-ALv2` would touch files owned by all eight build domains
and is forbidden by the ownership rule. Instead: ship *both* filenames in `LICENSES/`
holding byte-identical text, make `check_reuse.py` accept both, and **publish the split as
a counted number in `qa/reuse-ratchet.json` that may fall but not rise.** A truthful
counted divergence beats a silent mass edit. `docs/submission/LICENSING.md` states the
alias and why.

### The judge's first command, measured

```
$ git ls-files | awk '{print length($0), $0}' | sort -rn | head -1
214 verticals/mainline/apps/console/fixtures/bundles/blk-07/frames/GET~20~2Fv1~2Fclauses~2F…json
```

Windows `MAX_PATH` is 260, so any clone destination longer than **45 characters** fails.
I reproduced it: cloning into a deep path produced 20+ `Filename too long` errors and a
`Clone succeeded, but checkout failed` tree.

**Ruling L-2 — the fix is a clone flag, not a rename.** Frame filenames are *derived* from
the request by `verticals/mainline/apps/console/src/data/resources.ts:373`
(`return \`frames/${out}.json\``), so renaming the files breaks the console loader and the
bundle manifest. `git clone -c core.longpaths=true` costs one flag, changes no code, and is
a no-op off Windows. S04 measures the exact threshold and S05 puts the flag in the README's
copy-paste block. The deeper fix — a truncate-and-hash encoding in `resources.ts` — is a
**cross-domain note to the UI lead**, not this fleet's work.

### Secrets and sensitive data

`git log --diff-filter=A -- .env` is empty; `.env` was never committed and is gitignored.
The private keys in the tree are the deliberate `evidence/reference-ledger/keys/*.NOT-SECRET.key.pem`
fixtures. `AKIAIOSFODNN7EXAMPLE` and account `111122223333` are AWS's own documentation
placeholders. One genuine item: **`docs/adr/0002-g1-platform-ground-truth.md:64` prints the
real AWS account `0229REDACTED8246`.** Not a credential, but account numbers enable
cross-account enumeration and there is no reason to publish one. S03 masks it. A second,
cosmetic: `evidence/gate-refusal/proof-*.json` embeds `D:\CoackroachDBxAWS\mainline\…`,
leaking the founder's directory layout. Recorded, not repaired — rewriting an evidence
artefact to look tidier is precisely the move this repository refuses.

---

## 2 · Strategy

Four commitments, in priority order.

**A. Clear Stage One mechanically, and prove it is cleared.** A root `LICENSE`, a pushed
remote, a public flip, a demo URL. Three of the four are one command each; every one of
them is checked by `scripts/submission/check_submission_ready.py`, which exits non-zero
while any is unresolved. The founder does not audit a checklist by eye at 16:50 EDT on
D-day; he runs one program that refuses.

**B. Every submission document is generated against, or checked by, an artefact.** The
repository's differentiator is that its prose is falsifiable. Submission prose inherits
that: `docs/TOOL-USAGE.md` cites file paths and captured JSON; `RULES-MATRIX.md` derives
its met/unmet column from `check_submission_ready.py`; the licence census is a ratchet;
the judge's five minutes is a recorded dry run against a real fresh clone, not a claim.

**C. Surface `docs/HONESTY.md`, do not bury it.** Five judging axes, equally weighted. On
*Product Readiness* a candid limits section costs a little; on *Technological
Implementation* and *Real-World Impact* — safety-critical permit-to-work — a project that
publishes its own 15 failing migrations reads as the only credible entry in the field. The
README already links it in the second section. Keep it there. Every submission artefact
links to it.

**D. Own nothing another lead owns.** No worker in this fleet touches `verticals/`,
`packages/`, `spec/`, `infra/`, `skills/`, or `verticals/mainline/db/migrations/`. New
namespaces: `docs/submission/`, `scripts/submission/`, `evidence/tool-usage/`,
`evidence/provenance/`. The four exceptions are enumerated below and each is a single file
with a one-line reason.

### The four files owned outside my namespaces

| file | worker | why |
|---|---|---|
| `LICENSE`, `LICENSES/*` , `REUSE.toml` | S01 | the Stage One blocker; nobody else owns them |
| `scripts/qa/check_reuse.py`, `qa/reuse-ratchet.json` | S02 | `ci.yml` names this exact path; sixteen workflows are dead without it |
| `docs/adr/0002-g1-platform-ground-truth.md` | S03 | mask one AWS account number before an irreversible public flip |
| `README.md` | S05 | the judge-facing front door is this domain's core deliverable |

### Sequencing across the eight days

* **D-8 (today).** S01 and S02 land the licence and unblock CI. S03, S04, S06, S08, S09
  run in parallel — none depends on anything.
* **D-7.** Founder runs runbook item 1 (`git push`) once S01 is in. S10 lands the gate and
  `SUBMISSION.json`. S07 follows S06.
* **D-6.** S05 lands the README against measured dry-run numbers and the resolved token.
* **D-5 → D-2.** Deployment lead resolves the demo URL; `check_submission_ready.py` goes
  from RED to GREEN one row at a time. Founder records the video from S08's kit.
* **D-1.** Public flip. Devpost form is a copy-paste from `docs/submission/DEVPOST.md`.

---

## 3 · The demo URL, and cost

Not this domain's build — the deployment lead owns the target. This domain owns the
*binding*: one file, `docs/submission/SUBMISSION.json`, carries `demo_url`, `repo_url`,
`video_url` and `judge_access`, each initialised to the literal string
`"UNRESOLVED"`. Every document renders from it and the gate refuses while any field is
`UNRESOLVED`. There is exactly one place to paste a URL and exactly one program that says
whether it is done.

**Cost estimate, submission scope: US$0/month.** Everything this domain produces is text,
Python and CI on GitHub's free tier for public repositories. The cheapest deployment that
satisfies "functional demo URL, free and unrestricted for judges" is a **static console
build on GitHub Pages** — `verticals/mainline/apps/console` already produces `dist/` and
ships replay fixtures, so the recorded evidence bundle renders with no server, no
credential and no egress — **US$0/month**, against roughly **US$5–8/month** for the
cheapest always-on container. The database side is already capped: `ccloud cluster list`
reports `spend_limit: 2500` (US$25.00) on `mainline-dev`, which is a ceiling, not a spend.
Recommendation to the deployment lead, not a decision taken here.

---

## 4 · Worker fleet — 10 workers, disjoint literal paths

No globs, no bands, no ranges. Every path below is a literal file. The union has no
duplicates; I checked pairwise.

| id | title | files | deps |
|---|---|---|---|
| S01 | Licence texts and the root LICENSE | 5 | — |
| S02 | The REUSE checker CI names, and its ratchet | 4 | S01 |
| S03 | Public-repo readiness audit | 4 | — |
| S04 | The judge's first five minutes, measured on a fresh clone | 4 | — |
| S05 | The judge-facing README | 2 | S04, S10 |
| S06 | `docs/TOOL-USAGE.md` and captured evidence | 5 | — |
| S07 | Devpost description mapped to the five axes | 2 | S06 |
| S08 | Video kit for the founder | 4 | — |
| S09 | Pre-existing-code disclosure and provenance | 4 | — |
| S10 | Rules matrix, submission gate, founder runbook | 5 | S01 |

Full briefs are in the structured output that accompanies this file. Three rules bind
every worker:

1. **Ownership is absolute.** Touch only your enumerated paths. Anything else goes in
   `cross_domain_notes`.
2. **Never claim what you cannot prove.** Every number in a document you write carries the
   command or the artefact path that produced it, in the style of `docs/HONESTY.md`.
3. **No TODOs.** A file that ships is complete and runnable.

---

## 5 · Cross-domain notes raised by this plan

* **UI lead.** `verticals/mainline/apps/console/fixtures/bundles/blk-07/frames/` contains
  two paths of 214 and 206 characters. On default Windows Git any clone target over 45
  characters fails checkout. Frame names are derived by `src/data/resources.ts:373`, so the
  repair is a truncate-and-hash in the encoder plus a manifest regeneration — not a rename.
  Mitigated for judges by a clone flag; not fixed.
* **Datamodel lead.** `mainline_ops.outbox` remains the single highest-value missing
  artefact in the repository. `docs/STATE-OF-THE-BUILD.md` §1.5 shows its exact seven-column
  shape and shows that it converts the proof from *refuse-with-a-caveat* to
  *refuse → dispose → admit* unassisted, and the chain from 246/261 to 248/261. The demo
  and the video both improve materially the day it lands.
* **Quality lead.** `docs/STATE-OF-THE-BUILD.md` §4.1 is now stale — the paths it lists as
  untracked are committed. Its §3.5 finding (missing `check_reuse.py`) is fixed by S02.
  Both sections need a factual update; I own neither file.
* **Deployment lead.** `docs/submission/SUBMISSION.json` is the single write point for
  `demo_url`. Please write it there rather than into prose; nine documents read it.
</content>
