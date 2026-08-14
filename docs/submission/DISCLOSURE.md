<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Disclosure

The hackathon's seventh rule asks for two things: that the project was **newly created
inside the submission window**, and that any **pre-existing code be disclosed**. Both are
true here, and neither had been written down. This page writes them down, and — because
prose is the one form of evidence this repository does not accept from itself — hands the
checking to a program.

**Measured 2026-08-10 against the working tree at `D:/CoackroachDBxAWS/mainline`, at
`HEAD = bb21962f188fa1c23a231463018282b3c2959bf0`.** Every factual claim below carries the
command that produced it. Run the commands. Where a number and your terminal disagree, the
terminal is right and this page is stale.

Numbers carry a `[src: …]` reference in the style of [`docs/HONESTY.md`](../HONESTY.md).
Digits inside `code spans` are names, not measurements.

> ## ⚠ RE-DERIVED 2026-08-14 · THE COUNTS BELOW ARE FROM 2026-08-10 AND THE TREE HAS MOVED
>
> Every command in §§1, 3 and 4 was re-run on **2026-08-14** against `HEAD =
> `d098721fd70a3ea0833150f2af43e911ee4984de`. **The commands still produce the answers this
> page's arguments depend on. Four of its counts are stale, and two of its sentences are now
> false.** They are corrected in place, beside the 2026-08-10 reading, rather than overwritten
> — the older reading is a dated record and re-typing it would falsify history.
>
> | what | 2026-08-10 | **2026-08-14** | does the argument survive? |
> |---|---:|---:|---|
> | commits on `HEAD` | 16 | **86** | yes — all 86 inside the window |
> | distinct author identities | 1 | **2** | **the sentence "one author and one committer" is now FALSE** — §1 |
> | commits carrying `Co-Authored-By` | 0 | **67** | **the "one honest gap" has closed** — §3 |
> | manifests (`pyproject.toml` + `package.json`) | 32 | **33** | yes |
> | first-party distributions | 30 | **31** | yes |
> | Python development dependencies | 9 | **10** | yes |
> | tracked files under `research/` | 0 | **0** | yes — the gate that matters is unmoved |
>
> **And the census artefacts are stale, which the census itself refuses to be quiet about:**
>
> ```
> $ .venv/Scripts/python.exe scripts/submission/provenance_census.py --check
> ...
> window verdict    ALL INSIDE
> DRIFT  evidence/provenance/commit-window.json — differs (12934 bytes on disk, 56903 generated)
> DRIFT  evidence/provenance/third-party.json — differs (26962 bytes on disk, 27797 generated)
> CHECK FAILED — regenerate with: python scripts/submission/provenance_census.py
> $ echo $?
> 1
> ```
>
> **`--check` is RED.** The committed JSON is anchored to `bb21962` and `HEAD` is seventy
> commits later, exactly as §7's third bullet predicted it would be. Regenerating those two
> artefacts is one command and it is **owed**; it was not run in this revision because a
> documents wave does not write into `evidence/`. Until it is run, **every `[src: evidence/
> provenance/…]` reference on this page points at the 2026-08-10 snapshot**, and the live
> answer is the command, not the file.
>
> The one thing `--check` does *not* say is that anything is wrong with the claim. It prints
> `window verdict ALL INSIDE` over all 86 commits before it reports the drift, and
> `check_submission_ready.py` agrees independently: `provenance disclosure … 86 commits, all
> inside the window` — **PASS**.

---

## 0 · The one command

```bash
python scripts/submission/provenance_census.py
```

Standard library only. No network — the only subprocess it runs is `git`. It writes
[`evidence/provenance/commit-window.json`](../../evidence/provenance/commit-window.json)
and [`evidence/provenance/third-party.json`](../../evidence/provenance/third-party.json),
and it **exits non-zero if a single commit falls outside the declared window**, or if any
file under `research/` has become tracked. A claim of newness that would go red if it were
false is a different kind of sentence from a claim of newness.

Three more modes:

```bash
python scripts/submission/provenance_census.py --self-test        # plants each failure, requires it to fire
python scripts/submission/provenance_census.py --check            # committed JSON == generated JSON
python scripts/submission/provenance_census.py --check-licences   # licence table == installed metadata
```

`--self-test` runs 36 assertions with no repository and no network, including three that
build a throwaway git history and require the window check to fire on a commit smuggled in
from before the window — **and on a rebased commit whose committer date is inside the
window while its author date is not**. A checker that has never been red asserts nothing.

---

## 1 · This repository was created inside the submission window

The first commit is
`f80fefd49168cf52b2aa22a75396d419d67345be`
[src: evidence/provenance/commit-window.json#first_commit.hash], authored and committed at
**2026-08-05T22:47:47+10:00** (`2026-08-05T12:47:47Z`)
[src: evidence/provenance/commit-window.json#first_commit.author_date], subject
*"chore: repository skeleton, README, licence scaffolding"*.

```bash
$ git log --reverse --format='%H %aI %s' | head -1
f80fefd49168cf52b2aa22a75396d419d67345be 2026-08-05T22:47:47+10:00 chore: repository skeleton, README, licence scaffolding
```

There is no earlier commit and no grafted history:

```bash
$ git rev-list --count HEAD
16
$ git log --format='%aI' | sort | head -1
2026-08-05T22:47:47+10:00
```

16 commits [src: evidence/provenance/commit-window.json#commit_count], every one of them
inside the declared window `2026-08-05` … `2026-08-18`, evaluated in **UTC-04:00 (EDT)**
because that is the timezone the rules page states the deadline in. Both the *author*
instant and the *committer* instant of every commit are tested, because a rebase moves one
and not the other, and the author date is the one that gives the game away.

```
all_commits_inside_window : true    [src: evidence/provenance/commit-window.json#all_commits_inside_window]
violations                : 0       [src: evidence/provenance/commit-window.json#violations]
```

To see the check refuse rather than pass, narrow the window by one day and watch the first
two commits fall out of it:

```bash
$ python scripts/submission/provenance_census.py --check --window-start 2026-08-06
window verdict    2 OUTSIDE
    OUTSIDE  f80fefd  author=2026-08-05T22:47:47+10:00  committer=2026-08-05T22:47:47+10:00  chore: repository skeleton, README, licence scaffolding
    OUTSIDE  9ba926b  author=2026-08-05T23:20:07+10:00  committer=2026-08-05T23:20:07+10:00  docs(leads): 8 domain implementation plans + 80 worker briefs (0 path collisions)
$ echo $?
1
```

### Who wrote it

**As measured on 2026-08-10** — one author and one committer, on all 16 commits
[src: evidence/provenance/commit-window.json#identity_census.distinct_authors]:

| name | email | commits |
|---|---|---|
| Shaugato Paroi | shaugato2003@gmail.com | 16 |

```bash
$ git log --format='%an <%ae>' | sort | uniq -c
     16 Shaugato Paroi <shaugato2003@gmail.com>
$ git log --format='%cn <%ce>' | sort | uniq -c
     16 Shaugato Paroi <shaugato2003@gmail.com>
```

> **CORRECTED 2026-08-14. "One author and one committer" is no longer true, and the correction
> is smaller than the sentence makes it sound.** There are now **two identity strings behind
> one email address**:
>
> ```console
> $ git log --format='%an <%ae>' | sort | uniq -c
>      79 Shaugato Paroi <shaugato2003@gmail.com>
>       7 MAINLINE certification <shaugato2003@gmail.com>
> $ git log --format='%cn <%ce>' | sort | uniq -c
>      79 Shaugato Paroi <shaugato2003@gmail.com>
>       7 MAINLINE certification <shaugato2003@gmail.com>
> ```
>
> **One human, one mailbox, two `user.name` values** — seven commits were made with the git
> identity set to `MAINLINE certification`, which is a label rather than a person. There is
> still **no second contributor to disclose**: the email is identical on all 86 commits, and
> nobody else's work is in this repository.
>
> The structural claim the section actually rests on is unchanged and was re-checked directly
> rather than read off the stale artefact — **author and committer are identical on every one
> of the 86 commits**, `0` mismatches, so no commit was applied on somebody else's behalf and
> no history was rewritten under a second identity:
>
> ```console
> $ git log --format='%an|%ae|%cn|%ce' | awk -F'|' '$1!=$3 || $2!=$4' | wc -l
> 0
> ```
>
> `docs/submission/PUBLIC-READINESS.md` §0.2 records the same two strings from the other
> direction, over the *published* refs, and has done since 2026-08-12. This page had not
> caught up.

---

## 2 · What existed before this repository

**Design documents did. Product code did not.**

Before 2026-08-05 there was a separate, private research repository on the founder's
machine, holding the design corpus this build was written against: `ARCHITECTURE.md`,
`BUILD_PLAN.md`, `DECISION.md`, `PLATFORM-THESIS.md` and the research that produced them —
domain surveys, hypothesis validation, feasibility work, and a novelty review. Those
documents were produced by a 40-agent design operation and then hardened by an adversarial
review and an independent feasibility verification; the corrections from both were applied
before any product code was written. That description is not new here — `README.md` §Status
has carried it since the first commit — and the research repository's own history records
it:

```bash
$ git -C <research-repo> log --format='%aI %s' | head -1
2026-08-04T23:08:37+10:00 Phase 5 complete: MAINLINE ARCHITECTURE.md + BUILD_PLAN.md (40-agent design op, 28 adversarial + 5 feasibility corrections applied)
```

That corpus is **100 files, and all 100 are Markdown**:

```bash
$ git -C <research-repo> ls-files | wc -l
100
$ git -C <research-repo> ls-files | grep -v '\.md$' | wc -l
0
$ git -C <research-repo> rev-list --count HEAD
14
```

Zero `.py`, zero `.sql`, zero `.ts`, zero `.tf`. **There is no pre-existing product code**,
because there was none to bring: the corpus is prose and decisions, and the first line of
product code in this project was written after `f80fefd`.

### What a judge can verify, and what they cannot

Be precise about this, because it is the one claim on this page that a judge cannot check
from the submitted repository. The research repository is **private and unpublished** —
`git remote -v` inside it returns nothing; it has never been pushed anywhere. So the two
commands above are the founder's to run, not yours.

What *is* checkable from here is the half that rule 7 actually turns on: that **nothing
from that corpus is in this repository**. The tree is excluded by the first line of
`.gitignore` and not one byte of it is tracked:

```bash
$ head -1 .gitignore
research/
$ git check-ignore -v research/
.gitignore:1:research/  research/
$ git ls-files research/ | wc -l
0
```

`0` [src: evidence/provenance/commit-window.json#excluded_tree.tracked_file_count]. The
census program **exits non-zero** the day that number stops being zero, so this is a gate
and not an assurance.

If the judging panel would like to read the corpus, the founder will share it on request.
It is withheld for length, not for concealment: it is 100 documents of design deliberation,
and none of it is code.

---

## 3 · AI assistance

**AI assistance was used extensively in authoring this repository.** Not "assisted by" in
the sense of autocomplete — the architecture documents, the domain plans, the migrations,
the Python and TypeScript, the tests, this page: an AI coding agent drafted most of it,
directed by the founder, who reviewed, corrected, rejected and ran everything.

This is stated flatly because it is permitted, and because hedging it would contradict the
only thing this project actually claims to be good at. A repository whose central document
is [`docs/HONESTY.md`](../HONESTY.md) — a page that publishes its own 15 failing migrations
by name — cannot then be coy about how it was written.

The structure is visible in the history rather than inferred from it:

```bash
$ git log --format='%s' | grep -icE 'worker|fleet|agent'
6
$ git ls-files docs/leads/ | wc -l
15
$ git log --format='%s' --reverse | sed -n '2p;12p'
docs(leads): 8 domain implementation plans + 80 worker briefs (0 path collisions)
feat: 80-worker build fleet complete — all 8 domains delivered
```

`docs/leads/` holds the plans those fleets were dispatched against, and each one was
written to be read by a judge, not just executed.

One honest gap, since the point of this section is not to look tidy: **no commit carries a
`Co-Authored-By` trailer**, so the machine-readable record of AI authorship is this page and
the commit subjects above, not a trailer on each commit.

```bash
$ git log --format='%b' | grep -ci 'co-authored-by'
0
```

That was not a decision; it was an omission, and it is disclosed rather than backfilled — a
trailer added today to 16 commits written over five days would be a tidier record and a
less true one.

> **CLOSED, 2026-08-14 — and closed the right way, forwards.** The gap above is a true record
> of the first 16 commits and stays. From roughly the second wave onward the trailer has been
> present:
>
> ```console
> $ git log --format='%b' | grep -c 'Co-Authored-By:'
> 67
> $ git log --format='%b' | grep '^Co-Authored-By:' | sort -u
> Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
> ```
>
> **67 of 86 commits** now carry a machine-readable AI-authorship trailer, and there is
> exactly **one** distinct co-author string. The remaining 19 are the early ones this
> paragraph describes, and **they were not backfilled** — which is the same decision, held.
> A repository that fixed its history to match its disclosure would have destroyed the thing
> the disclosure was about.

**What AI assistance does not change.** Every claim this repository makes is checked by a
program that a stranger can run, and the checks were the point of the exercise rather than
a garnish on it. `python scripts/proof/gate_refusal.py` either prints `PROVEN` on your
machine or it does not. Who typed the file is not the evidence; the file refusing is.

---

## 4 · Third-party dependencies

Nothing third-party is **copied into** this repository. Things third-party are **depended
on**, and here they are.

```bash
$ python scripts/submission/provenance_census.py
$ git ls-files '*pyproject.toml' '*package.json' | grep -v node_modules | wc -l
32
```

31 [src: evidence/provenance/third-party.json#manifests.pyproject_toml_count]
`pyproject.toml` files and 1
[src: evidence/provenance/third-party.json#manifests.package_json_count] `package.json`,
declaring 30 [src: evidence/provenance/third-party.json#first_party_distribution_count]
first-party distributions of our own. First-party is *computed*, not asserted: a
requirement naming any `project.name` found in the tree is ours, everything else is
somebody else's.

> **RE-DERIVED 2026-08-14: 32 `pyproject.toml` + 1 `package.json` = 33 manifests, declaring
> 31 first-party distributions.** One package was added since 2026-08-10. The live census
> line reads:
>
> ```
> manifests         32 pyproject.toml, 1 package.json
> first-party dists 31
> third-party       python runtime 17, python dev 10, npm runtime 6, npm dev 22
> ```
>
> **Python development dependencies are 10, not 9.** The runtime figure (17) and both npm
> figures (6 and 22) are unchanged, so the tables below are current except for the
> development count. The `[src: …]` pointers in this paragraph resolve into the **stale**
> committed artefact — see the box at the head of this page.

### Python

**Runtime and optional** — 17
[src: evidence/provenance/third-party.json#third_party.distinct_count.python_runtime]
distinct distributions:

| distribution | licence |
|---|---|
| `anthropic` | MIT |
| `boto3` | Apache-2.0 |
| `cryptography` | Apache-2.0 OR BSD-3-Clause |
| `httpx` | BSD-3-Clause |
| `hypothesis` | **MPL-2.0** |
| `jinja2` | BSD-3-Clause |
| `numpy` | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| `pint` | BSD-3-Clause |
| `psycopg` | **LGPL-3.0-only** |
| `psycopg-binary` | **LGPL-3.0-only** |
| `psycopg-pool` | **LGPL-3.0-only** |
| `pydantic` | MIT |
| `pyyaml` | MIT |
| `rapidfuzz` | MIT |
| `scikit-learn` | BSD-3-Clause |
| `scipy` | BSD-3-Clause |
| `sentence-transformers` | **UNVERIFIED** — see below |

**Development** — 9
[src: evidence/provenance/third-party.json#third_party.distinct_count.python_development]:
`hypothesis` (MPL-2.0), `import-linter` (BSD-2-Clause), `mypy` (MIT), `psycopg` and
`psycopg-binary` (LGPL-3.0-only), `pytest` (MIT), `pytest-timeout` (MIT), `ruff` (MIT),
`types-PyYAML` (Apache-2.0).

### npm — `verticals/mainline/apps/console`

**Runtime** — 6
[src: evidence/provenance/third-party.json#third_party.distinct_count.npm_runtime], all
MIT: `react`, `react-dom`, `three`, `@react-three/fiber`, `@react-three/drei`, `motion`.

**Development** — 22
[src: evidence/provenance/third-party.json#third_party.distinct_count.npm_development]. All
MIT except `typescript` and `@playwright/test` (Apache-2.0) and `@axe-core/playwright`
(**MPL-2.0**).

### The four entries that deserve a sentence each

* **`psycopg` is LGPL-3.0-only**, and so are its `binary` and `pool` extras. That is
  copyleft, and it is the driver every database path in this repository imports. No psycopg
  source is copied into, modified by, or redistributed inside any MAINLINE distribution; it
  is installed from PyPI and imported unmodified, which is the use the LGPL is written for.
  It is named here because a dependency census that quietly omits its only strong-copyleft
  entry is not a census.
* **`hypothesis` and `@axe-core/playwright` are MPL-2.0** — weak, file-scoped copyleft on
  test tooling that never enters a shipped artefact.
* **`sentence-transformers` is recorded `UNVERIFIED`.** It is declared only by the
  `mainline-recall-agent[local-embed]` extra, which is not installed in this environment, so
  its licence was not measured on this machine. Its published licence is easy to look up;
  this page does not repeat it, because the rule here is that a number carries the artefact
  that produced it and there is no artefact for this one.
* **`numpy`'s licence is a compound expression**, not a slip: it covers components numpy
  itself vendors.

### How the licences were established

Not from memory, and not from the internet. Each licence was read from installed package
metadata on 2026-08-10 — Python core metadata (`License-Expression`, then `License`, then
the trove classifier), npm `package.json#license` — and frozen into a table inside the
census program, together with the exact string the machine printed and the version it was
read at. The artefact is therefore deterministic on a machine with no virtualenv and no
`node_modules`, and the table cannot rot silently:

```bash
$ python scripts/submission/provenance_census.py --check-licences
LICENCE TABLE AUDIT — declared table vs installed distributions
  SKIPPED   pypi:sentence-transformers — not installed in this environment
  50 verified, 1 skipped, 0 mismatched
$ echo $?
0
```

### Vendored code: one directory, and it is ours

The census scans every tracked path for a directory named `vendor`, `vendors`, `_vendor`,
`third_party`, `third-party`, `thirdparty`, `3rdparty` or `node_modules`, and for any
licence file travelling beside code. One directory matches:

```
packages/trappoint-verify/src/trappoint_verify/vendor/   2 files   -> internal-copy
```

Every file in it carries this project's own `SPDX-FileCopyrightText: 2026 MAINLINE
contributors`, so it is a copy of **our** code, not somebody else's: `canon_v1.py` is a
byte-identical duplicate of `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py`, kept so
that `trappoint-verify`'s "one dependency, and it is `cryptography`" claim stays literally
true. `scripts/custody/check_vendored_canon.py` asserts the two copies are byte-equal.

Third-party vendored directories: **0**
[src: evidence/provenance/third-party.json#vendored_scan.third_party_directory_count]. The
foreign-licence-file list at
[src: evidence/provenance/third-party.json#vendored_scan.foreign_licence_files] is empty,
and `bundles_third_party_code` is therefore `false`
[src: evidence/provenance/third-party.json#vendored_scan.bundles_third_party_code].

> **⚠ RE-RUN 2026-08-14: the LIVE scan now says `bundles_third_party_code: true`, and it is a
> FALSE POSITIVE caused by a filename in this very directory.** This is disclosed rather than
> fixed, because fixing it means changing something and the honest options are not this
> document's to take.
>
> `third_party_directory_count` is still **0** and `vendored_directories` still holds exactly
> the one internal copy above. What flipped the flag is the *foreign licence file* list, which
> now holds one entry:
>
> ```json
> "foreign_licence_files": [
>   { "path": "docs/submission/LICENCE-CENSUS.md",
>     "copyright": "2026 MAINLINE contributors",
>     "licence": "CC-BY-4.0" }
> ]
> ```
>
> **`docs/submission/LICENCE-CENSUS.md` is ours.** `provenance_census.py:120` matches
> licence-shaped filenames with `^(LICEN[CS]E|COPYING|COPYRIGHT|NOTICE)([._-][A-Za-z0-9._+-]+)?$`,
> which `LICENCE-CENSUS.md` satisfies as `LICENCE` + `-CENSUS.md`. The scanner then *reads* the
> SPDX holder at line 832 — and never tests it — before appending the file to
> `foreign_licence_files` at line 833. The holder it read is `2026 MAINLINE contributors`.
> `bundles_third_party_code` is `bool(foreign_licence_files)`, so one of our own documents
> makes the repository report that it bundles somebody else's code.
>
> **Three ways to make it green, and only one of them is honest.**
>
> * ❌ **Rename `LICENCE-CENSUS.md`.** Moving a document so a scanner stops matching it is
>   moving the derived side to satisfy the deriving side. The file's name is correct for what
>   it holds.
> * ❌ **Add the path to `OWN_LICENCE_PATHS`.** That is a one-path exemption, and a one-path
>   exemption is how a scanner learns to be quiet about the next file too.
> * ✅ **Test the holder the scanner already read.** `_spdx_of` returns it two lines above;
>   a file whose SPDX copyright names this project is by definition not a foreign licence
>   file. That is a change to `scripts/submission/provenance_census.py`, which this document
>   does not own. **Raised as a cross-domain finding, with the line numbers.**
>
> Until it is taken, the honest reading is: **the committed artefact says `false`, the live
> scan says `true`, and the live scan is wrong for a reason that is written down.** The root
> `NOTICE`'s sentence — *"MAINLINE bundles no third-party code at this time"* — remains true,
> and §4's own list of what is depended on is the statement about the dependency closure.

The self-test proves that scan can go red: it plants a `libs/third_party/zlib/` tree
carrying somebody else's copyright and a bare `LICENSE`, and requires the scanner to
classify it `third-party`, report the licence file, and flip `bundles_third_party_code` to
`true`.

The root `NOTICE` therefore says *"MAINLINE bundles no third-party code at this time"*, and
the scan supports it — read as a statement about **bundling**, which is what it says. It is
not a statement about the dependency closure; §4 above is.

---

## 5 · `skills/upstream/` — outbound, not inbound

`skills/upstream/` holds 4 tracked files
[src: evidence/provenance/third-party.json#outbound_contribution.file_count] — one skill
document, one script, and their two `.license` sidecars:

```bash
$ git ls-files skills/upstream/
skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/SKILL.md
skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/SKILL.md.license
skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/scripts/verify_restore_merkle_root.py
skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/scripts/verify_restore_merkle_root.py.license
```

It is easy to mistake this tree for something taken in, so state what it is: **work
authored here, de-branded, and laid out in another project's directory shape** as a
prepared contribution to
[`cockroachlabs/cockroachdb-skills`](https://github.com/cockroachlabs/cockroachdb-skills).
It carries none of this project's vocabulary, is deliberately absent from
`.claude-plugin/marketplace.json` so it is never loaded as one of our skills, and carries no
inline SPDX header — its licensing travels in `.license` sidecars precisely because a file
destined for somebody else's repository should not have our project name inside it.

What that means for provenance, plainly:

* **It is not pre-existing code.** Nothing was copied in. Both files were written inside
  the submission window like everything else here:

  ```bash
  $ git log --diff-filter=A --format='%h %aI %s' -- skills/upstream/
  904f1b4 2026-08-10T05:42:24+10:00 feat: 80-worker build fleet complete — all 8 domains delivered
  ```
* **It carries no inbound licence obligation**, because nothing was received.
* **Its outbound licence is an open question.** Here it is Apache-2.0. If the receiving
  project's contribution terms require something else, that is settled at the time of the
  offer, not assumed now. No contribution has been offered yet.

---

## 6 · Used, not authored

The following are other people's work, used as tools. None of it is claimed as this
project's, and none of it is redistributed here.

| | what it is | what we wrote |
|---|---|---|
| **CockroachDB** (`v26.2.5`, Cockroach Labs) | the database; the engine behind every refusal | the schema, the gates, the migrations that use it |
| **AWS** — Bedrock, S3, KMS and others | model inference and the evidence store | the boundary, the policies, the custody rules |
| **OpenTofu** | the infrastructure planner | `infra/modules/**` and the policy fixtures under `infra/policy/` |
| **pytest**, **Hypothesis**, **ruff**, **mypy** | the test and lint toolchain | the suites and the ratchets |
| **Vite**, **React**, **three.js** | the console's build and rendering | `verticals/mainline/apps/console/src/**` |
| **Docker** | the local single-node cluster | `compose.yaml` and the testkit that drives it |

Which CockroachDB tools and which AWS services, with the file and line that uses each and a
verdict on whether it has actually run, is the subject of its own document —
[`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — and is not restated here.

Trademarks belong to their owners; [`TRADEMARKS.md`](../../TRADEMARKS.md) governs the use of
the names. This project's own licences are in `LICENSES/` and are explained in
[`docs/submission/LICENSING.md`](LICENSING.md).

---

## 7 · What this page does not cover

* **It does not audit the transitive dependency closure.** The census reads *declared*
  dependencies from 32 manifests; it does not resolve `uv.lock` or `pnpm-lock.yaml` and walk
  what those pull in. The console has a separate gate that does walk its installed tree —
  `verticals/mainline/apps/console/scripts/check-licences.ts` — and refuses a package with
  a denied, absent or unknown licence. There is no equivalent for the Python closure.
  Recorded here rather than glossed.
* **It does not verify the research repository for you.** §2 says so, and says why.
* **It is a snapshot of one commit.** The artefacts carry no wall-clock field on purpose —
  they are anchored to `head`, so `--check` can prove that the committed JSON is the JSON the
  program produces. When HEAD moves, regenerate. When a number here disagrees with
  `evidence/provenance/`, the JSON is right.

Everything this project knows to be broken is listed by name in
[`docs/HONESTY.md`](../HONESTY.md). This page is its provenance chapter, and it is written
to the same rule: a truthful red beats a fabricated green.
