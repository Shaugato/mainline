<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PUBLIC-READINESS — what flipping the repository actually publishes

**Measured 2026-08-11 against the working tree at the repository root and the live remote
`https://github.com/Shaugato/mainline.git`.** Every row below carries the command that
produced it and what that command printed. Nothing here is asserted; regenerate all of it
with one command:

```
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
```

The program is standard-library only, starts no subprocess but `git`, and opens no socket.
All three claims are checkable: it runs to completion under `python -I -S`, which disables
site-packages entirely, and the file contains no `urllib`, `socket`, `http` or `ssl`
import. The YAML register introduced below is read by a strict minimal parser written into
the scanner rather than by `PyYAML`, precisely so that property survives.

**Current verdict: `READY`.** Eight checks: seven `PASS`, one `INFO`, zero `FAIL`.
**0 unresolved findings**, 77 allowlisted, 92 disclosed. The process exits 0.

That is a change of state and it deserves suspicion, so §2 is about exactly how it was
reached and what would have to be true for it to be dishonest.

---

## 0 · The irreversibility, stated first because it governs everything else

> **The flip from PRIVATE to PUBLIC is IRREVERSIBLE.** GitHub's fork network, the GHArchive
> event stream, Software Heritage and search-engine caches all outlive a revert, and the
> flip publishes **all 44 commits on all 9 refs**, not the tree at HEAD. A value masked at
> HEAD but present in an earlier commit is published anyway.

**That paragraph used to say "all 16 commits", and it was wrong by 28.** The number is now
computed from `git log --all` on every run rather than typed once and left. A constant that
describes a moving tree is a lie with a delay on it, and the one paragraph whose entire job
is to convey the size of the act was understating it.

The signed checklist for the flip itself is `docs/submission/PUBLIC-FLIP-CHECKLIST.md`.
**This document is the evidence; that document is the gate.**

---

## 1 · The checks, and what each printed

Eight checks. Status is one of `PASS` (gating, green), `FAIL` (gating, red) or `INFO`
(reported, never gating). The program exits non-zero if any check is `FAIL`.

| # | check | status | what it asserts |
|---|---|---|---|
| 1 | `secrets_tracked` | **PASS** | no unresolved secret in any tracked file at HEAD |
| 2 | `secrets_history` | **PASS** | no unresolved secret in any line ever added, on any ref |
| 3 | `ignored_and_untracked` | **PASS** | `.env` / `*.tfstate*` gitignored, untracked, never committed |
| 4 | `tracked_size` | **PASS** | no tracked blob over 5 MiB |
| 5 | `committer_census` | **INFO** | every commit and identity the flip will publish, on every ref |
| 6 | `absolute_paths` | **PASS** | absolute Windows paths, each classified and disposed of |
| 7 | `repo_state` | **PASS** | the tree that would actually be published is the tree on disk |
| 8 | `disclosure_register` | **PASS** | every `DISCLOSED` grant is named, dated and still load-bearing |

### 1.0 What the previous revision of this table said, and why that mattered

The committed version of this page claimed **checks 1, 3, 4 and 6 `PASS`, with only 2 and 7
`FAIL`**. When the ship lead re-measured on 2026-08-11 the program actually printed:

```
VERDICT NOT READY
failed_checks   ['secrets_tracked', 'secrets_history', 'absolute_paths']
totals          checks 7 · passed 3 · failed 3 · informational 1
                unresolved_findings 105 · allowlisted_findings 60
```

**The table was stale in the bad direction**: it showed green where the program showed red.
That is the worse of the two failure modes, and correcting it was the first act of this
revision. Three rows had regressed since the page was written, and one had genuinely
improved — `repo_state`, which is now `PASS` and is written up in §1.7 with both SHAs. A
page that only ever gets better is as untrustworthy as one that only ever gets worse, so
both directions are recorded.

### 1.1 `secrets_tracked` — PASS

```
git ls-files -z  |  scan 8 families over each file's content
```

```
7314 tracked paths scanned; 74 hits (0 unresolved, 45 allowlisted, 29 disclosed);
aws_access_key_id=39, aws_account_id=17, bearer_or_jwt=1, high_entropy_secret=9,
private_key_block=8
```

The eight families are AWS access key ids (`AKIA`/`ASIA` + 16), GitHub tokens
(`ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`/`github_pat_`), Slack tokens (`xox[baprs]-`), PEM
private-key blocks, CockroachDB Cloud API keys (`CCDB1_`), AWS twelve-digit account ids in
account or ARN context, bearer credentials and JWTs, and high-entropy tokens sitting beside
a secret-shaped key name.

Two of those eight are **contextual rather than bare**, and the narrowing is stated in the
source rather than hidden, because a detector that is silently blind is worse than one that
is loud:

* A bare twelve-digit scan returns **585 hits across 135 files** on this tree — synthetic
  corpus identifiers, almost all of them. Narrowed to twelve-digit runs that appear inside
  an ARN, after `iam::`, or on a line naming an account, it returns a handful. The
  founder's own account is additionally matched unconditionally, so the detector cannot be
  defeated by an edit that removes the surrounding word "account".
* A bare Shannon-entropy scan returns **1,021 hits across 66 files** — `pnpm-lock.yaml`
  integrity digests (424), `uv.lock` (243), the reference ledger bundle (132). Narrowed to
  "high-entropy token preceded on the same line by a secret-shaped key name, excluding
  dotted identifiers", it returns nine.

Both counts were measured before the thresholds were chosen, not after. **Neither was
touched by this revision** — see §2.1.

### 1.2 `secrets_history` — PASS

```
git log -p --all -U0 --no-color  |  scan 8 families over '+' lines
```

```
44 commits, 901810 added lines scanned; 44 distinct (commit,path,family) hits
(0 unresolved, 18 allowlisted, 26 disclosed);
aws_access_key_id=7, aws_account_id=21, bearer_or_jwt=1, high_entropy_secret=7,
private_key_block=8
```

Twenty-six of these are the account id in commits `5ddaa3a` and `e518787`, both already on
`origin/master`. §3 is about them and about the decision that closed them.

### 1.3 `ignored_and_untracked` — PASS

```
git check-ignore -q -- .env terraform.tfstate ;
git ls-files ;
git log --all --diff-filter=A -- .env '*.tfstate*'
```

```
check-ignore: {'.env': True, 'terraform.tfstate': True, 'terraform.tfstate.backup': True};
tracked .env-like: none; tracked tfstate: none;
history adds .env: none; history adds tfstate: none
```

The history probe is the load-bearing half: a file can be gitignored *today* and still be
sitting in a commit from last week. It is not. The only tracked path beginning `.env` is
`.env.example`.

### 1.4 `tracked_size` — PASS

```
git ls-files -s -z | git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
```

```
7314 tracked blobs, 53478169 bytes total (51.0 MiB);
largest verticals/mainline/fixtures/corpus/answer-key/clause_revision.jsonl
at 1673465 bytes (1.60 MiB); 0 over the limit
```

Blob sizes come from the object store, not from `stat`, so the number is what a clone
actually transfers. **51.0 MiB is a comfortable clone for a judge on a conference network.**

### 1.5 `committer_census` — INFO, and it is not what anybody expected

```
git log --all --format='%an <%ae>|%cn <%ce>' | sort | uniq -c ;
git log master --format=... ; git for-each-ref
```

```
44 commits over 9 ref(s), 3 distinct identity string(s):
  GitHub <noreply@github.com> x0
  Shaugato Paroi <shaugato2003@gmail.com> x38
  dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com> x6
master alone: 38 commits, 1 identity
2 identity string(s) reachable ONLY from a non-master ref:
  ['GitHub <noreply@github.com>',
   'dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>']
```

**The brief for this work said the census was "19 commits, 1 identity". It is not, in two
separate ways, and both are worth stating plainly.**

* **`master` carries 38 commits, not 19.** The brief's figure was simply out of date; the
  build has moved since it was written.
* **`git log --all` reaches 44 commits over 9 refs, not 38 over 1.** The extra six are
  Dependabot pull-request branches that live on `origin` — `origin/dependabot/uv/...`,
  `origin/dependabot/npm_and_yarn/...` and four more. `git log master` cannot see them and
  a census that only walks `master` therefore under-reports what a visitor can read.
  **Flipping visibility publishes every ref, not the default branch.**

This check now reports both numbers, and the check itself was changed to do so, because the
gap between them *is* the finding. The two extra identities are `dependabot[bot]` as author
and `GitHub <noreply@github.com>` as committer — both are bot accounts, neither is a person,
and neither leaks anything the GitHub UI would not already show on a public repository.

What does remain a real, permanent disclosure is the first identity: **`shaugato2003@gmail.com`,
a real personal address, on all 38 commits on `master`.** No `users.noreply.github.com`
alias is in use for the human author. That is a deliberate, ordinary choice for an
open-source project, and it is recorded here so that it is a choice rather than a surprise.
Enabling GitHub's email-privacy alias after the fact does not retract commits already
carrying the address.

### 1.6 `absolute_paths` — PASS

```
git ls-files -z  |  scan for (?<![A-Za-z0-9_])[A-Za-z]:\\?<segment>\ and :/<segment>/
```

```
44 file(s), 310 hit(s); 0 unresolved, 14 allowlisted, 37 disclosed.
9 file(s) disclose a Windows account name (abs-path-username):
  docs/submission/DISCLOSURE-DECISIONS.yaml, docs/submission/PUBLIC-READINESS.md,
  evidence/deploy/acceptance.json, qa/judge-dry-run.json, qa/public-readiness.json,
  qa/test-state.json, scripts/deploy/deploy.sh, scripts/deploy/teardown.sh,
  scripts/submission/audit_public_readiness.py
```

**The check now separates two disclosure classes that it used to lump together**, because
they are not the same thing:

| class | what it discloses | files |
|---|---|---|
| `abs-path-layout` | a directory layout: `D:\CoackroachDBxAWS\mainline`, `C:\Program Files\Docker`, `C:\Windows\System32`, `C:\Python314`, and placeholder profiles such as `C:\Users\someone` | 35 |
| `abs-path-username` | **the founder's local Windows account name**, `C:\Users\shaug\…` | 9 |

The second is a strictly larger disclosure and is counted apart so it can never be lost
inside the first one's total. The classification is derived by the scanner from each file's
own bytes (`path_disclosure_class()`), not asserted in the register — and check 8 **fails
the whole register** if any entry claims `abs-path-layout` for a file that names a real
profile directory. A username disclosure cannot be filed as layout, even by accident.

**A note on the regex, because the first one was wrong.** An initial draft matched
`[A-Za-z]:\\?.` and reported **113 files**. Reading them showed that 105 were assertion
messages of the form `"...NOT A PASS:\n"` — a letter, a colon, and an escaped newline.
Requiring a drive letter, then a path *segment*, then a further separator dropped the count
to the genuine cases. The false-positive rate of the first attempt is recorded here because
a scanner nobody audits is a scanner nobody should trust.

### 1.7 `repo_state` — PASS, and this row genuinely improved

```
git remote get-url origin ; git rev-parse --abbrev-ref HEAD ;
git rev-list --left-right --count origin/master...HEAD ; git status --porcelain
```

```
origin=https://github.com/Shaugato/mainline.git; branch=master; HEAD=ead0f7c;
origin/master=ead0f7c; behind=0 ahead=0; working tree: 97 uncommitted path(s)
```

**`HEAD` and `origin/master` are the same commit, `ead0f7c`.** Confirmed independently:

```
$ git rev-parse HEAD
ead0f7cf9b8dc471e91ff27d17f7d1c774395a3b
$ git rev-parse origin/master
ead0f7cf9b8dc471e91ff27d17f7d1c774395a3b
```

The previous revision of this page recorded `HEAD=bb21962; origin/master=174b29f; ahead=2`
and, worse, `LICENSE` untracked — meaning a flip that day would have published a tree
without the licence file and failed Stage One on a technicality. Both are fixed:
`git ls-files --error-unmatch LICENSE` now succeeds, and `LICENSES/` exists.

**The 97 uncommitted paths are the live number and will move**, because nine other workers
are landing files into this tree as this is written. It is reported and is *not* gating —
what gates is `ahead=0 behind=0`. But it is exactly why checklist item 2 requires the audit
to be re-run **after** the push, against the commit that will actually be published. The
tree audited here is the tree on disk; the tree published is the tree on the remote; today
those agree at `ead0f7c` and tomorrow they will agree at some later SHA.

### 1.8 `disclosure_register` — PASS (new check)

```
parse docs/submission/DISCLOSURE-DECISIONS.yaml with the strict reader in this file;
validate every entry; require each to have granted at least one finding
```

```
59 entry/entries granting 92 finding(s); 0 stale; classes
abs-path-layout=26, abs-path-username=6, aws-documentation-placeholder=2,
detector-context-artefact=2, history-already-pushed=14,
recorded-evidence-account-id=6, synthetic-test-fixture=3
```

This check exists so that the mechanism §2 introduces cannot rot. It is described there.

---

## 2 · How `NOT READY` became `READY` without weakening anything

This is the section to read sceptically. A green bought by loosening a scanner is worth
less than an honest red, and the change made here was designed to be checkable rather than
believed.

### 2.1 The scanner is *provably* exactly as strong

Decision **D2** (`docs/leads/ship-final.md` §1.6) added a third disposition:

| disposition | gating? | granted by |
|---|---|---|
| `UNRESOLVED` | **yes, red** | nothing — it is the default for every hit |
| `ALLOWLISTED` | no | a `Waiver` in the scanner's own source, keyed by exact path + family |
| `DISCLOSED` | no | **an entry in `docs/submission/DISCLOSURE-DECISIONS.yaml`** naming the exact path, with a family, a class, a date, a decider and a reason of at least 80 characters |

An occurrence in a file named by neither stays `UNRESOLVED` and stays red.

**No pattern was widened. No threshold was lowered. No family was removed.** That is not an
assertion; the scanner now carries a `DETECTOR_FINGERPRINT` — a SHA-256 over every detector
pattern, the entropy floor, the scan-line ceiling, the account-context regex, the AWS
documentation-account set and the family list — and `--self-test` fails if it moves.
Measured against the pre-change file taken straight out of `git show HEAD:`:

```
HEAD (pre-change) detectors  : 9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a
working tree      detectors  : 9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a
pinned DETECTOR_FINGERPRINT  : 9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a
IDENTICAL                    : True
families HEAD == now         : True   (8)
entropy floor HEAD -> now    : 4.2 -> 4.2
ALLOWLIST entries HEAD -> now: 30 -> 30
```

The code allowlist is byte-for-byte what it was: **thirty entries, none added**. Everything
new went into the register, which is data a reviewer can read in one sitting.

### 2.2 The register cannot behave like a blanket allowlist

Six properties, each enforced in code and each asserted by `--self-test`:

1. **Exact path plus family.** No globs, no prefixes, no wildcards.
2. **Scoped.** An entry declares `tracked`, `history` or both. Fourteen entries are
   `scopes: [history]` **only** — the account id is accepted in commits already pushed and
   is *not* accepted if it reappears at HEAD. Acceptance of the past is not permission for
   the future.
3. **A stale grant is a failure.** An entry that matched nothing on a run turns check 8
   red. An entry cannot sit there as standing permission for a hit nobody has looked at.
4. **It cannot print a value in full.** `DISCLOSED` previews are redacted exactly like
   `UNRESOLVED` ones.
5. **Fixed class vocabulary.** `class: fine` is a parse error, not a decision. So is an
   unknown family, a non-ISO date, a reason under 80 characters, an unknown scope, an
   unknown top-level key, a wrong schema, and an entry that duplicates a code allowlist
   entry.
6. **It cannot downgrade a username disclosure.** Check 8 re-derives the class from the
   file's bytes and refuses a register that calls a `C:\Users\shaug` hit mere layout.

`--self-test` proves all of it: it plants one secret of every family and requires each to
fire; it requires a clean control file to produce nothing; it grants one synthetic register
entry and requires the *same family at a different path* and the *same path in an
undeclared scope* to stay red; it requires the other eight families to remain red; it feeds
the loader nine malformed registers plus a **no-defect control** and requires the nine to be
refused and the control accepted; and it cross-checks the strict YAML reader against
`PyYAML` where `PyYAML` is importable.

```
SELF-TEST - one planted secret per family, scanner must fire on each
-----------------------------------------------------
  FIRED   aws_access_key_id    planted_aws_access_key_id.txt
  FIRED   github_token         planted_github_token.txt
  FIRED   slack_token          planted_slack_token.txt
  FIRED   private_key_block    planted_private_key_block.txt
  FIRED   crdb_cloud_api_key   planted_crdb_cloud_api_key.txt
  FIRED   aws_account_id       planted_aws_account_id.txt
  FIRED   bearer_or_jwt        planted_bearer_or_jwt.txt
  FIRED   high_entropy_secret  planted_high_entropy_secret.txt
  FIRED   abs_windows_path     planted_abs_windows_path.txt
-----------------------------------------------------
  control file (no secret)       : no findings

SELF-TEST - the DISCLOSED disposition, and the strength of the detectors
-----------------------------------------------------
  OK      every planted hit is UNRESOLVED with an empty register
  OK      every planted preview is redacted
  OK      clean control file produces no finding
  OK      detector fingerprint unchanged (no pattern widened, no threshold lowered,
          no family removed)
  OK      all 8 secret families still declared
  OK      entropy floor still 4.2
  OK      the register cannot set verbatim
  OK      redact_preview takes no verbatim escape hatch
  OK      a public-by-design value is still redacted in previews
  OK      a well-formed register parses with no errors
  OK      the named (path, family) becomes DISCLOSED
  OK      a DISCLOSED preview is still redacted (register cannot ask for verbatim)
  OK      the same family at an UNNAMED path stays UNRESOLVED
  OK      a tracked-only grant does not cover the history scope
  OK      one grant does not disarm the other 8 families
  OK      control: the same fixture with NO defect is ACCEPTED
  OK      register refused: unknown family
  OK      register refused: unknown class
  OK      register refused: missing decided_by
  OK      register refused: reason too short
  OK      register refused: date not ISO
  OK      register refused: unknown scope
  OK      register refused: wrong schema
  OK      register refused: duplicates a code ALLOWLIST entry
  OK      register refused: unknown top-level key
  OK      parser rejects: tab indentation
  OK      parser rejects: anchor
  OK      parser rejects: no colon
  OK      parser rejects: empty value
  OK      strict reader agrees with PyYAML on the register subset
-----------------------------------------------------
  detector fingerprint : 9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a
  PyYAML 6.0.3 agrees with the strict reader

SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 30 disposition/strength assertions, 0 failed
```

### 2.3 Two defects the self-test and the register found in their first hour

Neither was looked for. Both are recorded because a mechanism that only ever confirms its
author is not a mechanism.

**The parser accepted tab indentation.** `_indent_of()` counts leading spaces, so a
tab-indented key measured as indent 0 and was silently reparented to the document level —
the parser would have read a *different document* from the one an editor renders. The
self-test case `parser rejects: tab indentation` failed on its first run. The fix was in
the parser, not the test: any tab in leading whitespace now rejects the whole file.

**A register entry went stale within minutes, and the audit refused to pass.** An early
draft of the `scripts/deploy/judge_access.py` reason *reproduced* the token it was
explaining. Serialised into `qa/public-readiness.json`, that put the token back on a single
line next to a secret-shaped word, so the audit found it in its own output. Rewriting the
reason to *describe* rather than reproduce removed the hits at the source — and the grant
written for them then covered nothing, check 8 reported `granted nothing this run`, and the
audit stayed red until the entry was deleted. The deletion is recorded in §7 of the register
with the reasoning left in place.

The general rule, learned the hard way: **a reason must identify a value, not republish it.**

### 2.4 A third defect: the report was growing without bound

This one is the most serious of the three and it predates the register.

The scanner's `redact_preview()` used to take a `verbatim` flag. A waiver could mark a value
"public by design" — AWS's own documentation placeholders — and the preview would print it
in full, on the reasonable argument that redacting a value anybody can read tells the reader
less, not more. The argument is sound. The mechanism was not, because **the scanner scans
every tracked file and `qa/public-readiness.json` is a tracked file.** Each run wrote N
verbatim previews; the next run found all N and wrote N + 32:

```
$ git show HEAD:qa/public-readiness.json | grep -c AKIAIOSFODNN7EXAMPLE
8
$ python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
$ grep -c AKIAIOSFODNN7EXAMPLE qa/public-readiness.json
420
$ python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
$ grep -c AKIAIOSFODNN7EXAMPLE qa/public-readiness.json
452
```

A committed artefact growing monotonically, forever, with no fixed point. **It never went
red, because the pair was allowlisted — which is exactly why nobody noticed.**

The fix: **previews are now redacted in every disposition, with no escape hatch.** Nothing
is lost. Every waiver that used to set `verbatim` still names its value in its *reason*, in
prose, once each — `AKIAIOSFODNN7EXAMPLE` and `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
remain legible to a reviewer and no longer multiply. `Waiver.verbatim` survives in the JSON
as documentation that the value is public by design, and controls nothing. Detection is
untouched: same patterns, same thresholds, same families. Only the rendering changed, and
the self-test now asserts that `redact_preview` has no `verbatim` parameter at all.

The artefact reached a fixed point immediately and is now byte-stable:

```
run 1  exit=0 READY  456691 bytes  AKIA-literals 23
run 2  exit=0 READY  224167 bytes  AKIA-literals 23
run 3  exit=0 READY  224167 bytes  AKIA-literals 23   <- byte-identical to run 2
run 4  exit=0 READY  224167 bytes  AKIA-literals 23   <- byte-identical to run 2
```

Those figures were taken before the register's last two entries landed. The artefact is
now 226,649 bytes and byte-identical between consecutive runs, which is the property that
matters: it has a fixed point and reaches it in one regeneration.

---

## 3 · The AWS account id, and the decision that closed it

Commit `5ddaa3a` scattered the real twelve-digit account id across **18 tracked files and
37 lines**. D2 splits those by role.

**Where the id was an executable default it is gone**, removed by the infrastructure and
deploy workers in their own files — `EXPECTED_ACCOUNT` in `deploy.sh`, variable defaults in
`variables.tf`, the S3 `backend-config` example, the copied `terraform.tfvars.example`, an
interpolated bucket name in `main.tf`. `docs/deploy/RUNBOOK.md` §3 records `grep -c` over
the four deploy scripts returning `0`, and the tracked scan agrees: not one of
`infra/envs/demo/*.tf`, `infra/modules/*/*.tf`, `deploy.sh`, `deploy.ps1`, `teardown.sh` or
`bootstrap_state.sh` carries it at HEAD. The value is derived at run time from
`aws sts get-caller-identity`.

**Where it is recorded evidence it stays, and is declared.** Six paths, 22 findings: quoted
`aws sts get-caller-identity` output, the `kms list-aliases` transcript whose value is the
*absent* `TargetKeyId`, the recorded CloudFront `AccessDenied` refusal, a committed
`terraform plan` excerpt, and two lead plans' measured verification blocks. Redacting those
is the move `docs/HONESTY.md` refuses — *a redacted transcript is not a transcript*, and a
refusal with the account elided cannot be matched against an AWS support case.

**The exposure, stated rather than waved at.** An AWS account id is not a credential. It
appears in every ARN a partner is handed and grants nothing without a principal and a
policy. The realistic cost is cross-account enumeration and more targeted phishing against
the founder. That is a real cost, and it is smaller than the cost of a submission whose
evidence cannot be checked.

### 3.1 The history finding is closed as Option A, in writing

The previous revision of this page left one finding deliberately open: `docs/adr/0002-g1-platform-ground-truth.md`
printed the account id in commit `e518787`, **which is already on `origin/master`.** Masking
the working tree changes what a visitor reads at HEAD; it changes nothing about `git log -p`,
the blame view, or any clone. The page offered two honest resolutions and declined to pick:

* **Option A — accept it in writing.**
* **Option B — `git filter-repo --replace-text` and a force-push**, rewriting every commit
  hash from `e518787` forward.

**Option A is taken.** Fourteen `history-already-pushed` entries in the register are the
writing: each names its path, its commit, its date and its decider. Option B was refused for
a stated reason — rewriting shared history to hide a value that is not a credential is a
worse trade than disclosing it, and it would invalidate every commit SHA this repository's
own evidence artefacts cite.

Every one of those fourteen is `scopes: [history]` only. **If any of these values reappears
at HEAD, the tracked scan goes red and the flip is blocked.**

---

## 4 · Absolute paths: two classes, two dispositions

Per the brief, the two classes get different treatment and the register records which:

**RECOMMEND REGENERATION** — the producer can emit a path relative to the repository root,
and the owning domain should make it do so. Named per entry:
`evidence/chain/chain-20260810T062542Z.json` (release domain),
`evidence/deploy/chain-261.json` and `evidence/deploy/acceptance.json` (deploy domain),
`qa/conformance-census.json` (quality domain), `qa/judge-dry-run.json` (deploy domain).
When those producers are fixed, the corresponding register entries go **stale**, check 8
turns red, and somebody has to delete them. The mechanism cleans up after itself.

**RECORD, NOT REPAIR** — the artefact's value is that it was captured verbatim. Editing one
so that it looks tidier is precisely the move this repository refuses. This covers the
gate-refusal proofs' `migrations_dir`, the pasted pytest and migration-chain output, the
worked commands in the video kit and the submission runbooks, and — in the username class —
the `cygpath -m` transcripts in `deploy.sh:199` and `teardown.sh:117`, which exist to show
that Git-Bash `/tmp/probe.json` and the path `aws.exe` actually opens are *different*.
Paraphrasing that to `C:/Users/<you>/` would remove the only evidence that the conversion is
load-bearing.

On the marginal cost of the username class, stated honestly: `shaug` is a prefix of the
GitHub handle `Shaugato`, which is already in the repository URL, in `REUSE.toml`, in three
`pyproject.toml` files, in two workflow files and in the author line of all 38 commits on
`master`. What is newly disclosed is that the *local Windows account* is `shaug` rather than
something else. Small, not zero, and enumerated to nine files rather than gestured at.

---

## 5 · The rotated judge credential

`docs/deploy/JUDGE-PACK.md` publishes host, port, database, user `mainline_judge` and
`sslmode=verify-full`, and states that the password is not in this repository. The audit was
run **after** the rotation landed, and the password appears in no tracked file.

Three independent measurements, none of which required holding the credential:

1. **The family scan.** `high_entropy_secret` and `bearer_or_jwt` return **zero unresolved
   findings** over 7,314 tracked files and 901,810 added lines of history. The only
   `high_entropy_secret` hits anywhere near the judge path are two in `JUDGE-PACK.md` whose
   matched token is the *cluster hostname* and two in `judge_access.py` whose matched token
   is a *file path* — both armed by the literal placeholder
   `<PASSWORD-FROM-THE-SUBMISSION-FORM>` and by ordinary English words in a docstring.

2. **A shape sweep for the generator's output class.** `generate_password()` is
   `secrets.token_urlsafe(24)` — exactly 32 characters of `[A-Za-z0-9_-]`. Scanning the
   whole tree for that shape, **with no key-name context requirement at all** (strictly
   wider than the `high_entropy_secret` family, so it cannot be defeated by the value
   sitting alone on a line):

   ```
   tracked files scanned : 7312
   token_urlsafe(24)-shaped candidates : 31
        22  verticals/mainline/apps/console/pnpm-lock.yaml
         5  evidence/reference-ledger/bundle.json
         3  verticals/mainline/apps/console/tests/vectors/checkpoint.json
         1  evidence/reference-ledger/keys/reference-tsa.NOT-SECRET.key.pem
   history added lines scanned : 901810
   token_urlsafe(24)-shaped candidates : 33   (same four files)
   ```

   Four files, all pre-existing published lockfile and reference-ledger material with
   independent explanations. **None is in `docs/deploy/`, `scripts/deploy/` or `qa/` — none
   is anywhere the judge password could plausibly have been written.**

3. **`evidence/deploy/judge-run.json` self-scanned.** Its `credential_hygiene` block records
   `password_was_issued_this_run: true`, `bytes_scanned: 15633`, `matches: 0`, `holds: true`.

**What none of the three does is check the exact value**, because the password is shown once
and is not recoverable by this worker — which is the design working correctly. The scanner
therefore grew a mode for the person who does hold it:

```
printf '%s' "$PASSWORD" | python scripts/submission/audit_public_readiness.py --assert-absent
```

It reads one value from **stdin** — never an argument vector, never an environment variable,
never a file, so it cannot land in `ps`, a shell history or a CI log — scans every tracked
file and every added line, and prints only a SHA-256 prefix of what it checked. Verified in
all three directions:

```
a value that IS in the tree (the cluster hostname)  -> ABSENT: NO   exit 1
a value that is NOT in the tree                     -> ABSENT: YES  exit 0
a value shorter than 8 characters                   -> REFUSED      exit 2
```

**This is checklist item 6 and the orchestrator runs it.** It is the one check whose timing
matters and the one this worker cannot complete alone.

---

## 6 · Reproducing this document

```
$ python scripts/submission/audit_public_readiness.py --self-test
SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 30 disposition/strength assertions, 0 failed
$ echo $?
0

$ python -I -S scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
...
VERDICT: READY - every finding is resolved, allowlisted with a reason, or disclosed by a
dated register entry
$ echo $?
0
```

`-I -S` disables site-packages, which is how the standard-library-only claim is checked
rather than asserted. Both the audit and the self-test exit 0 under it.

The full machine rows — every finding, the complete allowlist, and the complete register
with every reason — are in `qa/public-readiness.json`
(`schema: mainline.qa.public-readiness/1`). The register itself, with the reasoning
organised into seven sections, is `docs/submission/DISCLOSURE-DECISIONS.yaml`.

### What this audit did not do

It did not push. **It did not flip visibility.** It did not rewrite history, and it edited
no file outside the five it owns: `scripts/submission/audit_public_readiness.py`,
`docs/submission/PUBLIC-READINESS.md`, `docs/submission/DISCLOSURE-DECISIONS.yaml`,
`qa/public-readiness.json` and `docs/submission/PUBLIC-FLIP-CHECKLIST.md`.

The gate is the checklist, not this page. `docs/submission/PUBLIC-FLIP-CHECKLIST.md`.
