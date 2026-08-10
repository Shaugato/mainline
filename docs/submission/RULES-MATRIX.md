<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RULES MATRIX — one row per official requirement, and the program that writes the status column

The hackathon rules page lists seven requirements. This document has one row for each,
plus the mechanical preconditions that decide whether the first two can be met at all.

**The status column is not typed. It is generated.** Every value under **Status** below
came out of `scripts/submission/check_submission_ready.py`, which asks the filesystem,
`git` and GitHub the same ten questions every time and exits non-zero while any of them
is unresolved. If this document and the program disagree, the program is right and this
document is stale — and the command that resolves the disagreement is printed under the
table.

```
python scripts/submission/check_submission_ready.py --markdown   # the table below
python scripts/submission/check_submission_ready.py --json       # the machine record
python scripts/submission/check_submission_ready.py              # the table + remedies
```

Exit codes: `0` every blocking row resolved · `1` at least one unresolved · `2` the gate
could not run. There is no fourth outcome and there is no flag that turns a red row green.

---

## 0 · The state on 2026-08-10, in one sentence

**Requirements 1 and 2 are UNMET.** The repository is private, and nothing is deployed.
Both are Stage One pass/fail, so on the morning this document was written the submission
would not have been assessed at all. Everything else is either met or is a paste away.

The generated table below says so in its own words, and it will keep saying so until the
underlying fact changes.

---

## 1 · The generated table

Generated `2026-08-10T07:50:51Z` by `python scripts/submission/check_submission_ready.py --markdown`.
Exit code at that instant: **1**, with **5** unresolved rows.

| Row | Requirement | Status | Observed | Evidence | Re-derive with |
|---|---|---|---|---|---|
| `licence_file` | 1 - public repo with an open-source LICENSE file | **PASS** | 11357 bytes, reads as Apache-2.0 | `LICENSE`, `LICENSES/`, `docs/submission/LICENCE-CENSUS.md` | `ls -l LICENSE && python scripts/qa/check_reuse.py` |
| `remote_sync` | 1 - public repo with an open-source LICENSE file | **FAIL** | 2 commits ahead of origin/master, 98 file(s) on this disk and on no server | the remote itself - there is no local artefact for this row | `git rev-list --left-right --count origin/master...HEAD` |
| `repo_public` | 1 - public repo with an open-source LICENSE file | **FAIL** | visibility is PRIVATE [gh repo view --json visibility] | `qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md` | `gh repo view Shaugato/mainline --json visibility` |
| `demo_url` | 2 - a URL to a functional demo app | **FAIL** | demo_url is UNRESOLVED | `docs/submission/SUBMISSION.json` key `demo_url` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `video_url` | 4 - demo video under 3 minutes on YouTube or Vimeo | **FAIL** | video_url is UNRESOLVED | `docs/submission/VIDEO-KIT.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml` | `python scripts/submission/check_submission_ready.py --check-urls` |
| `devpost_description` | 3 - text description of the features | **PASS** | docs/submission/DEVPOST.md: 14637 bytes, 111 non-blank lines | `docs/submission/DEVPOST.md` | `python scripts/submission/check_submission_prose.py` |
| `tool_usage` | 5 - documented CockroachDB and AWS usage (>=2 CRDB tools, >=1 AWS) | **PASS** | 4 CockroachDB tools, 10 AWS services named | `docs/TOOL-USAGE.md`, `evidence/tool-usage/` | `python scripts/submission/capture_tool_evidence.py --check` |
| `judge_access` | 6 - free, unrestricted access for judges | **FAIL** | 3 unresolved: judge_access.required, judge_access.how, judge_access.credentials_location | `docs/submission/SUBMISSION.json` key `judge_access`, `VERIFY.md` | `python scripts/submission/check_submission_ready.py --json` |
| `disclosure` | 7 - created in the submission window; pre-existing code disclosed | **PASS** | docs/submission/DISCLOSURE.md present (20445 bytes); 16 commits, all inside the window | `docs/submission/DISCLOSURE.md`, `evidence/provenance/commit-window.json` | `python scripts/submission/provenance_census.py --check` |
| `deadline` | deadline - 2026-08-18 17:00 EDT | **PASS** | 8d 13h to 2026-08-18 17:00 EDT (2026-08-18T21:00:00Z) | the official rules page | `python scripts/submission/check_submission_ready.py` |

**To regenerate this table**, replace everything between the two horizontal rules of this
section with the output of:

```bash
python scripts/submission/check_submission_ready.py --markdown
```

Do not edit a cell by hand. A hand-edited status column is a claim with nothing behind
it, which is the one thing this repository is built not to ship.

---

## 2 · Requirement by requirement

### Requirement 1 — a public repository with an open-source LICENSE file

**UNMET.** Three separate facts have to hold, and the gate keeps them as three rows
because they fail independently and are fixed by different commands.

| fact | row | state on 2026-08-10 |
|---|---|---|
| a licence file exists at the root | `licence_file` | **met** — Apache-2.0, 11,357 bytes |
| the tree on the server is the tree on this disk | `remote_sync` | **unmet** — 2 commits, 98 files, never pushed |
| the repository is publicly readable | `repo_public` | **unmet** — `visibility: PRIVATE` |

`remote_sync` is the most consequential red row in this document and the least obvious.
The licence file, the refusal proof, `conftest.py`, `LICENSES/` and `docs/HONESTY.md` are
committed on the founder's disk and exist on no server. Flipping visibility before the
push publishes a tree in which the proof this project is about is absent. That is why
the runbook pushes first and flips second, and why the gate refuses on either.

Re-derive: `git rev-list --left-right --count origin/master...HEAD` — a submitted state
prints `0<TAB>0`.

### Requirement 2 — a URL to a functional demo app

**UNMET.** Nothing is deployed; `demo_url` in `docs/submission/SUBMISSION.json` holds the
literal `UNRESOLVED`. This is the second Stage One pass/fail and it is not this domain's
build — the deployment lead owns the target. What this domain owns is the binding: there
is exactly one place to write the URL, and the gate refuses until it is written.

Re-derive: `python scripts/submission/check_submission_ready.py --check-urls`, which
fetches the URL and requires HTTP 200 rather than trusting that it was pasted correctly.

### Requirement 3 — a text description of the features

**MET as a source document.** `docs/submission/DEVPOST.md` exists and is checked for
size, structure and unfinished-sentence markers by the `devpost_description` row, and its
prose is checked against the nine SUB rules by `scripts/submission/check_submission_prose.py`.

The gate deliberately does **not** fail this row because `DEVPOST.md` carries the literal
`UNRESOLVED` beside the three URLs in its paste-order table. That marker is honest, and
it is already counted by the `demo_url`, `video_url` and `repo_public` rows. Counting it
twice would turn one fact into two red rows and make this table overstate how much is
wrong.

### Requirement 4 — a video under three minutes on YouTube or Vimeo

**PARTIAL, and precisely so.** The kit exists and is CI-validated; the film does not
exist.

* `verticals/mainline/demo/script/SHOT-LIST.yaml` holds the shot list, and
  `.github/workflows/claims.yml` runs its validator, so a shot list that drifts past the
  three-minute budget is a red build rather than a discovery made during the upload.
* `docs/submission/VIDEO-KIT.md` holds the seeded state, the exact commands, the
  environment and the sentences that may not be said on camera.
* `video_url` holds `UNRESOLVED`, and the `video_url` row is **FAIL**.

The gate also checks the host: a URL that is not on YouTube or Vimeo fails, because the
rules name those two.

### Requirement 5 — which CockroachDB and AWS services were used, and how

**MET.** `docs/TOOL-USAGE.md` names four CockroachDB tools and ten AWS services, and
distinguishes what is exercised from what is designed. The rules floor is two CockroachDB
tools and one AWS service; the `tool_usage` row asserts the floor rather than the ceiling,
so the row stays honest if a tool is later withdrawn from the document.

Re-derive: `python scripts/submission/capture_tool_evidence.py --check`, which rebuilds
the census under `evidence/tool-usage/` from the source tree and exits 1 if the committed
files differ.

### Requirement 6 — free, unrestricted access for judges

**UNMET.** `judge_access` has three members and all three are `UNRESOLVED`. The row
resolves when `required` is a real boolean, `how` is a sentence a judge can act on, and
`credentials_location` says where a credential lives.

**No credential value is ever written into `SUBMISSION.json`.** The file becomes
world-readable the instant the repository flips, so `credentials_location` is a pointer
and never the thing itself. The gate enforces this rather than trusting it: it scans
every value in the file for eight credential shapes, for keys whose names say the value
is a secret, and for bare high-entropy blobs, and it fails the `judge_access` row if any
of them matches — even if every URL beside it is resolved.

### Requirement 7 — newly created in the submission window, with pre-existing code disclosed

**MET.** `docs/submission/DISCLOSURE.md` discloses the separate, earlier research
repository and states that it holds no product code. The `disclosure` row independently
re-reads the git history and checks **both** the author date and the committer date of
every commit against the window `2026-08-05` … `2026-08-18` evaluated in EDT — one date
is half a check, because a rebase moves one and not the other.

Re-derive: `python scripts/submission/provenance_census.py --check`, whose output is
committed at `evidence/provenance/commit-window.json`.

---

## 3 · `docs/submission/SUBMISSION.json` — the schema, documented here because JSON holds no comments

One file is the single write point for every unresolved submission fact. Nine documents
read it; nobody writes a URL into prose.

| key | type | meaning |
|---|---|---|
| `schema_version` | integer | bumped when a key changes meaning, never when a value changes |
| `schema_documented_in` | string | points back at this section |
| `read_by` | array of strings | every program and document that reads the file |
| `unresolved_sentinel` | string | the literal an unresolved field holds: `UNRESOLVED` |
| `never_write_a_credential_here` | string | the standing rule, in band, where a person editing the file will see it |
| `demo_url` | string | requirement 2. `UNRESOLVED` until deployed |
| `repo_url` | string | the URL a judge opens. `UNRESOLVED` until the repository is public |
| `video_url` | string | requirement 4. `UNRESOLVED` until uploaded |
| `judge_access.required` | boolean, or `UNRESOLVED` | whether a judge needs a credential at all |
| `judge_access.how` | string | one sentence a judge can act on |
| `judge_access.credentials_location` | string | **a pointer to where a credential lives, never a credential** |
| `deadline_utc` | string | `2026-08-18T21:00:00Z`, resolved |
| `deadline_local` | string | `2026-08-18 17:00 EDT`, resolved |
| `devpost_description_file` | string | `docs/submission/DEVPOST.md`, resolved |
| `tool_usage_file` | string | `docs/TOOL-USAGE.md`, resolved |
| `disclosure_file` | string | `docs/submission/DISCLOSURE.md`, resolved |
| `licence_file` | string | `LICENSE`, resolved |

Two notes a reader will otherwise have to reverse-engineer from the code.

**`judge_access.required` is typed twice on purpose.** Until it is answered it holds the
string `UNRESOLVED`, like every other unresolved field; once answered it must be a real
JSON boolean. The gate refuses both the sentinel and a string spelled `"false"`, because
`"false"` is truthy in most languages that will read this file and a submission gate that
can be fooled by a quotation mark is not a gate.

**The file carries no sidecar `.license`.** It is covered by the root `REUSE.toml` block
for `docs/submission/**`, which is why a JSON file with no comment syntax can still
declare a licence.

---

## 4 · `NOTRUN` is not a pass, and this is the whole design

The gate has four statuses. Only one of them resolves a row.

| status | meaning | resolves the row? |
|---|---|---|
| `PASS` | the question was asked and the answer was right | **yes** |
| `FAIL` | the question was asked and the answer was wrong | no |
| `WARN` | the answer was right but incomplete — for example, the remote is in sync and the working tree is dirty | no |
| `NOTRUN` | nobody could answer: no `gh`, no network, no ref, no git | no |

`NOTRUN` prints as `NOT CHECKED` in the observed column and blocks like a failure. A
question nobody could answer is an unresolved question, and the single most common way a
release checklist lies is by rendering "we could not check this" in the same colour as
"this is fine".

The repository visibility row is where this matters. It reads the answer from one of two
sources and names which one answered:

1. `$GITHUB_EVENT_PATH` — inside GitHub Actions, the event payload already carries
   `repository.visibility`. No token, no network, no `gh`. This is what lets the CI lane
   assert the row without a credential.
2. `gh repo view --json visibility` — on a machine with a logged-in CLI.

When neither can answer, the row is `NOTRUN`. It is never assumed public.

---

## 5 · What checks this document

`.github/workflows/submission.yml` runs, on every push and pull request, with egress
blocked and no credential:

1. `check_submission_ready.py --self-test` — plants one of every failure family the gate
   must catch and requires it to fire. A gate that has never refused asserts nothing.
2. `check_submission_ready.py` itself, report-only until D-3 and blocking after, so the
   lane is informative during the build and refuses during the submission window.
3. `check_path_lengths.py` and `scripts/qa/check_reuse.py`.

The self-test is the half that matters. It exercises the sentinel scan, all eight
credential shapes, the key-name rule, `rev-list` parsing, URL classification, both
visibility sources, the clock arithmetic, description triviality, tool counting, the
commit-window check including the rebase case, and the invariant that only `PASS`
resolves a row.

---

## 6 · Related documents

* [`RUNBOOK.md`](RUNBOOK.md) — the founder's numbered D-day list, every step a literal
  command with its expected output.
* [`DEVPOST.md`](DEVPOST.md) — the description, field by field, in paste order.
* [`DISCLOSURE.md`](DISCLOSURE.md) — requirement 7, and the research repository.
* [`PUBLIC-READINESS.md`](PUBLIC-READINESS.md) — what must be true before the flip.
* [`VIDEO-KIT.md`](VIDEO-KIT.md) — requirement 4's kit.
* [`../TOOL-USAGE.md`](../TOOL-USAGE.md) — requirement 5.
* [`../HONESTY.md`](../HONESTY.md) — what is broken, published rather than hidden. Every
  document in this directory links to it, and none of them softens it.
