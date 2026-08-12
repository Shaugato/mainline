<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PUBLIC-READINESS — the standing disclosure register of a repository that is already public

**The flip happened on `2026-08-11`. This page stopped being a gate on that day and became
a record.** It is kept, rather than deleted, because a public repository owes its readers a
list of what it discloses and who signed for each item — and because the findings below are
the same findings, not a shorter list.

**Re-measured `2026-08-12` at commit `1d41442` on `master`, against the working tree and the
live remote `https://github.com/Shaugato/mainline.git`.** Every row carries the command that
produced it and what that command printed.

```
python scripts/submission/audit_public_readiness.py                       # the register
python scripts/submission/audit_public_readiness.py --pre-flip            # the old gate
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
```

The program is standard-library only, starts no subprocess but `git`, and opens no socket.
All three claims are checkable: it runs to completion under `python -I -S`, which disables
site-packages entirely, and the file contains no `urllib`, `socket`, `http` or `ssl`
import. The YAML register introduced below is read by a strict minimal parser written into
the scanner rather than by `PyYAML`, precisely so that property survives.

**The one thing this program cannot measure is the one thing it most needs.** Repository
visibility is not in the git object store, and this file opens no socket, so the flip is
recorded in the source as a dated constant (`FLIP`) that names its evidence and prints the
command that falsifies it on every run. Verified for this page:

```
$ gh repo view Shaugato/mainline --json visibility,isPrivate,defaultBranchRef
{"defaultBranchRef":{"name":"master"},"isPrivate":false,"visibility":"PUBLIC"}
$ curl -sI https://github.com/Shaugato/mainline | head -1
HTTP/1.1 200 OK
```

The second probe is the load-bearing one: GitHub answers `404`, not `403`, for a private
repository, so an authenticated check cannot tell the two states apart.

**Today's register: 214 findings, and not one of them was deleted to make this page
shorter.**

| disposition | findings | paths | meaning |
|---|---|---|---|
| `repaired` | 23 | 20 | gone at HEAD, present in published history. Real, and partial |
| `recorded-not-repaired` | 57 | 35 | still at HEAD on purpose, granted by a dated register entry |
| `waived-with-reason` | 80 | 23 | an exact-path waiver says why the value authenticates nothing |
| **`undisposed`** | **54** | **28** | **nobody has signed for these. RED, and they stay red** |

`python scripts/submission/audit_public_readiness.py` exits **3** — *this register is
incomplete* — and deliberately not `1`, because `1` meant *do not flip* and that sentence no
longer has a referent. §1.9 lists the 54 by domain.

**The committed `qa/public-readiness.json` is stale and is not this worker's file to
regenerate.** It records `verdict: READY`, `unresolved_findings: 0`, generated
`2026-08-11T07:44:29Z`; the live run on `2026-08-12` finds 54 unresolved. Regenerating it is
one command and it is owed by the public-readiness domain (`w9-public-readiness`, see the
provenance block at the foot of `PUBLIC-FLIP-CHECKLIST.md`). **Where this page and that
artefact disagree, this page is the live reading and the artefact is the older one.**

---

## 0 · The irreversibility, and the date it stopped being a warning

> **The flip from PRIVATE to PUBLIC was IRREVERSIBLE, and it has happened.** GitHub's fork
> network, the GHArchive event stream, Software Heritage and search-engine caches all
> outlive a revert. A value masked at `HEAD` but present in an earlier published commit is
> public anyway. There was never a partial flip and there is no undo.

**That paragraph used to say "all 16 commits", and it was wrong by 28; then it said 44, and
today it would say 113.** The number is computed on every run rather than typed once and
left — but *which* number is computed turned out to matter more than whether it was fresh.

### 0.1 `git log --all` is now the wrong instrument, and it fails in the flattering direction

Before the flip, `--all` was the conservative choice: it walks every ref on this
workstation, so it could only ever over-count, and over-counting an irreversible act is the
safe direction to be wrong in. After the flip it is simply wrong. Measured today:

```
$ git ls-remote --heads origin | wc -l                         4     # what is published
$ git rev-list --count origin/master                          47
$ git rev-list --count origin/master origin/w1/… origin/w5/… origin/w7/…   52
$ git for-each-ref refs/heads | wc -l                         56     # never pushed
$ git rev-list --all --count                                 113     # this workstation
$ git for-each-ref | wc -l                                    67
```

**A visitor can read 52 commits over 4 branches, 47 of them on `master`.** `git log --all`
on this machine reaches 113 over 67 refs, because 56 local branches — the `w8-p-*` and
`w9/*` anti-vacuity plants, which exist to prove CI lanes can go red — were never pushed and
never will be. Reporting those as published overstates the disclosure by 61 commits.

The scanner now measures both and prints the gap (`published_surface()`). One honest wrinkle
it prints rather than hides: `refs/remotes/origin/*` is a *cache*, and this checkout still
lists six `origin/dependabot/*` branches that have since been deleted on the remote, so the
audit's own reading is `58 over 10`. `git ls-remote --heads origin` is the live answer and
it is `4`. Pruning the cache is a write, and this program performs none.

### 0.2 The identities that are actually published

```
$ git log --format='%an <%ae>' origin/master origin/w1/… origin/w5/… origin/w7/… | sort | uniq -c
     45 Shaugato Paroi <shaugato2003@gmail.com>
      7 MAINLINE certification <shaugato2003@gmail.com>
```

**Two identity strings, one real personal address, on all 52 published commits.** No
`users.noreply.github.com` alias is in use for the human author, and enabling GitHub's
email-privacy setting now does not retract commits already carrying the address. That is a
deliberate, ordinary open-source choice and it is recorded here so it is a choice rather
than a surprise.

The `dependabot[bot]` and `GitHub <noreply@github.com>` identities that earlier revisions of
this page enumerated are **no longer reachable from any published ref** — the six Dependabot
branches are gone from the remote. A third identity, `w8 <w8@local>`, appears on 39 commits
on this workstation and on **none** that were pushed.

`docs/submission/PUBLIC-FLIP-CHECKLIST.md` is the record of the act itself.
**This document is the evidence; that document is the ticked list.**

---

## 1 · The checks, and what each printed

Eight checks. Under `--pre-flip` the status column gated an irreversible act: `PASS`
(green), `FAIL` (red), `INFO` (reported, never gating), and any `FAIL` exited 1. Post-flip
the same eight checks run and produce the same findings; what changes is that a finding is
now something to disposition rather than something to stop for.

| # | check | status today | what it asserts |
|---|---|---|---|
| 1 | `secrets_tracked` | **FAIL** | no unresolved secret in any tracked file at HEAD |
| 2 | `secrets_history` | **FAIL** | no unresolved secret in any line ever added, on any ref |
| 3 | `ignored_and_untracked` | **PASS** | `.env` / `*.tfstate*` gitignored, untracked, never committed |
| 4 | `tracked_size` | **PASS** | no tracked blob over 5 MiB |
| 5 | `committer_census` | **INFO** | every commit and identity that is published, on every ref |
| 6 | `absolute_paths` | **FAIL** | absolute Windows paths, each classified and disposed of |
| 7 | `repo_state` | **PASS** | the tree that is published is the tree on disk |
| 8 | `disclosure_register` | **PASS** | every `DISCLOSED` grant is named, dated and still load-bearing |

**Three `FAIL` rows, and the honest reading of them is not "the flip was a mistake".** It is
that 54 findings have accumulated since `2026-08-11` — almost all of them in files that
landed during the completion wave — and nobody has yet either repaired them or written them
into the register. §1.9 names them.

### 1.0 What the previous revisions of this table said, and why that matters

The revision before last claimed **checks 1, 3, 4 and 6 `PASS`, with only 2 and 7 `FAIL`**,
while the program printed `NOT READY` on three checks and 105 unresolved findings. **That
table was stale in the bad direction**: green where the program showed red.

The revision after it recorded `READY`, `0 unresolved, 77 allowlisted, 92 disclosed`, and it
was true at `ead0f7c` on `2026-08-11T07:44Z`.

Both are kept because the shape of the movement is the point: this page has now been wrong
in both directions and printed the correction each time. A page that only ever gets better
is as untrustworthy as one that only ever gets worse.

### 1.1 `secrets_tracked` — 19 unresolved today

```
git ls-files -z  |  scan 8 families over each file's content
```

```
7402 tracked paths scanned; 78 hits (19 unresolved, 46 allowlisted, 13 disclosed);
aws_access_key_id=43, aws_account_id=12, bearer_or_jwt=1, high_entropy_secret=14,
private_key_block=8
```

**One recursion, stated rather than hidden.** This page is a tracked file, so the scan above
includes it, and writing §1.9 moved the `allowlisted` column by one — a page that names the
values it waives is a page that then contains them. That is the intended behaviour and the
reason §2.4 removed the `verbatim` escape hatch: the counts move, the *previews* are
redacted in every disposition, and the artefact still reaches a fixed point in one
regeneration. **The `unresolved` column did not move**, which is the column that matters:
these eight documents introduced no new finding, verified by diffing the undisposed list
before and after they were written.

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

### 1.2 `secrets_history` — 18 unresolved today

```
git log -p --all -U0 --no-color  |  scan 8 families over '+' lines
```

```
107 commits, 1010052 added lines scanned; 69 distinct (commit,path,family) hits
(18 unresolved, 21 allowlisted, 30 disclosed);
aws_access_key_id=13, aws_account_id=35, bearer_or_jwt=1, high_entropy_secret=12,
private_key_block=8
```

**Read `107 commits` against §0.1 before reading anything else in that block.** This scan
walks `--all`, so 55 of those commits are on local branches nobody pushed and their contents
were never published. The scan is deliberately left wide — a scanner that narrows itself is
the failure mode this file exists to prevent — but a finding whose only occurrence is on an
unpushed branch is a finding about this workstation, not about the repository. Fourteen of
the eighteen unresolved history hits are in `6251c6effd78`, which **is** on `origin/master`.

The account id in commits `5ddaa3a` and `e518787`, both already on `origin/master`, is
covered by fourteen `history-already-pushed` register entries. §3 is about them and about
the decision that closed them.

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
7402 tracked blobs, 58322166 bytes total (55.6 MiB);
largest verticals/mainline/fixtures/corpus/answer-key/clause_revision.jsonl
at 1673465 bytes (1.60 MiB); 0 over the limit
```

Blob sizes come from the object store, not from `stat`, so the number is what a clone
actually transfers. **55.6 MiB is a comfortable clone for a judge on a conference network.**

### 1.5 `committer_census` — INFO, and post-flip it needs a third census

```
git log --all --format='%an <%ae>|%cn <%ce>' | sort | uniq -c ;
git log master --format=... ; git for-each-ref
```

```
113 commits over 67 ref(s), 5 distinct identity string(s):
  GitHub <noreply@github.com> x0
  MAINLINE certification <shaugato2003@gmail.com> x7
  Shaugato Paroi <shaugato2003@gmail.com> x61
  dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com> x6
  w8 <w8@local> x39
master alone: 47 commits, 2 identity strings
3 identity string(s) reachable ONLY from a non-master ref:
  ['GitHub <noreply@github.com>',
   'dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>',
   'w8 <w8@local>']
```

**Four of those five identity strings are not published, and `113` is not the number of
commits anybody can read.** §0.1 has the arithmetic: 56 of the 67 refs are local branches
that were never pushed, `w8 <w8@local>` exists only on them, and the six Dependabot
branches that carried the other two bot identities have since been deleted on the remote.
The published census is **52 commits over 4 refs, 2 identity strings, one real address**.

This check reports all three censuses — `--all`, `master`, and (added post-flip) the
remote-tracking surface under `detail.published_surface` — because the gap between them *is*
the finding, and after the flip the gap points the other way from before. A census that
over-reports what is public is not conservative; it is just wrong in the direction that
flatters nobody and misleads everybody.

`master` carries **47** commits, confirmed independently against the API:

```
$ gh api "repos/Shaugato/mainline/commits?sha=master&per_page=1" -i | grep -i '^link:'
…&page=47>; rel="last"
```

### 1.6 `absolute_paths` — 17 unresolved today

```
git ls-files -z  |  scan for (?<![A-Za-z0-9_])[A-Za-z]:\\?<segment>\ and :/<segment>/
```

```
60 file(s), 343 hit(s); 17 unresolved, 13 allowlisted, 37 disclosed.
9 file(s) disclose a Windows account name (abs-path-username):
  docs/submission/DISCLOSURE-DECISIONS.yaml, docs/submission/PUBLIC-READINESS.md,
  evidence/deploy/acceptance.json, qa/judge-dry-run.json, qa/public-readiness.json,
  qa/test-state.json, scripts/deploy/deploy.sh, scripts/deploy/teardown.sh,
  scripts/submission/audit_public_readiness.py
```

The username set is unchanged at nine files. The seventeen unresolved hits are all
`abs-path-layout` — `D:/CoackroachDBxAWS/mainline/` and `C:/Windows/` — in files that landed
after the register was written. They are listed in §1.9.

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

### 1.7 `repo_state` — PASS

```
git remote get-url origin ; git rev-parse --abbrev-ref HEAD ;
git rev-list --left-right --count origin/master...HEAD ; git status --porcelain
```

```
origin=https://github.com/Shaugato/mainline.git; branch=master; HEAD=1d41442;
origin/master=1d41442; behind=0 ahead=0; working tree: 56 uncommitted path(s)
```

That last figure read `40`, then `49`, then `56` over the three hours this revision took,
because other workers are landing files into the same tree. **Do not copy it — run the
command.**

**`HEAD` and `origin/master` are the same commit, `1d41442`.** An earlier revision of this
page recorded `HEAD=bb21962; origin/master=174b29f; ahead=2` and, worse, `LICENSE`
untracked — a flip that day would have published a tree without the licence file and failed
Stage One on a technicality. Both were fixed before the flip:
`git ls-files --error-unmatch LICENSE` succeeds, and `LICENSES/` exists.

**The 49 uncommitted paths are the live number and will move**, because other workers are
landing files into this tree as this is written. It is reported and is *not* gating — what
gates is `ahead=0 behind=0`. Post-flip it carries a different weight from before: an
uncommitted path is no longer a file the judges will never see, it is a file the public
repository does not yet show. The remedy is the same and it is a push.

### 1.8 `disclosure_register` — PASS

```
parse docs/submission/DISCLOSURE-DECISIONS.yaml with the strict reader in this file;
validate every entry; require each to have granted at least one finding
```

```
59 entry/entries granting 80 finding(s); 0 stale; classes
abs-path-layout=26, abs-path-username=6, aws-documentation-placeholder=2,
detector-context-artefact=2, history-already-pushed=14,
recorded-evidence-account-id=6, synthetic-test-fixture=3
```

Fifty-nine entries, `0 stale` — every grant still covers a real finding, which is the
property that stops the register from decaying into a blanket allowlist. It granted 92
findings on `2026-08-11` and 80 today; twelve findings it used to cover have been repaired
at the source, which is the mechanism cleaning up after itself exactly as §2.2 item 3
describes. This check exists so that the mechanism §2 introduces cannot rot.

### 1.9 The 54 undisposed findings, named, by the domain that owns each

**They are listed rather than summarised, because a count is not a disclosure register.**
None is a live credential: the family scan finds no GitHub token, no Slack token, no
CockroachDB Cloud API key, and no private key outside the deliberately-published
`NOT-SECRET` set anywhere in the tree or in history.

| what | count | where | owner |
|---|---|---|---|
| `abs_windows_path` — `D:/CoackroachDBxAWS/mainline/` in module docstrings | 11 | `scripts/aws/*.py` (8), `evidence/aws/{agent,probe}/*.json` (3) | AWS domain |
| `abs_windows_path` — the same layout in lead plans | 3 | `docs/leads/{aws-exec-final,ci-finish-final,ship-final}.md` | lead-plan domain |
| `abs_windows_path` — `C:/Windows/` in captured output | 2 | `evidence/deploy/gate-run-reachable.json`, `verticals/…/tests/test_static_site.py` | deploy, demo-api |
| `abs_windows_path` — `migrations_dir` in a proof artefact | 1 | `evidence/gate-refusal/proof-20260811T074629Z.json` | release domain |
| `aws_account_id` — the mask `000000000000` | 8 | `evidence/deploy/terraform-plan-furl.json` (6), `scripts/aws/_common.py`, `scripts/aws/verify_evidence.py` | deploy, AWS |
| `aws_account_id` — Bedrock inference-profile ARNs in a real region | 3 | `scripts/aws/embed_corpus.py` (2), `scripts/aws/verify_evidence.py` | AWS domain |
| `aws_access_key_id` — AWS's own `AKIAIOSFODNN7EXAMPLE`/`ASIA…` documentation values | 3 | `tests/unit/aws/test_common_redaction.py` (2), `scripts/aws/verify_evidence.py` | AWS domain |
| `high_entropy_secret` — model ids, a doc path, AWS's own placeholder, a DSN | 5 | `evidence/aws/COST.md` (2), `docs/leads/ship-final.md`, `tests/unit/aws/test_common_redaction.py`, `verticals/…/judge/MCP-CONFIG.md` | AWS, lead, demo |
| the same values in `6251c6ef`, already on `origin/master` | 17 | history scope | — |
| the mask `999999999999` in `1d41442798cf`, the current HEAD | 1 | `evidence/deploy/deploy-dry-run.json` | deploy domain |

**The mask is itself a finding, and that is not a bug in the scanner.** Six of the eight
`aws_account_id` hits in `evidence/deploy/terraform-plan-furl.json` are the literal
`000000000000` the account id was masked to before the flip, and `aws-evidence` CI is red on
the same value in `evidence/deploy/deploy-dry-run.json` with a precise message:

```
[SEC-ACCOUNT-ID] evidence/deploy/deploy-dry-run.json:409: a bare 12-digit run
'999999999999' survives UUID/digest/decimal masking and has the shape of an AWS
account id
```

Two checkers disagree about whether twelve identical digits is a mask or a value. Both are
defensible; neither was silenced. Recording the disagreement is cheaper and more honest than
picking a winner in a document that owns neither checker.

---

## 2 · The mechanism, and why adding a post-flip mode did not weaken it

This is the section to read sceptically. A green bought by loosening a scanner is worth
less than an honest red, and both changes made to this program — the `DISCLOSED`
disposition on `2026-08-11`, and the post-flip register on `2026-08-12` — were designed to
be checkable rather than believed.

**The post-flip mode is a relabelling, not a filter, and that is asserted rather than
described.** `--self-test` builds a synthetic finding set spanning all three pre-flip
dispositions and both scopes, runs the partition, and requires `sum(counts) == len(input)`;
it requires an `UNRESOLVED` finding to come out `undisposed` and stay red; it requires a
value still present at `HEAD` to read `recorded-not-repaired` and never `repaired`; and it
requires `postflip_disposition()` to answer `undisposed` for a finding no register names,
so no code path can invent a signature. Six assertions, and the self-test count moved from
30 to 35 because of them:

```
$ python -I -S scripts/submission/audit_public_readiness.py --self-test | tail -8
  OK      post-flip partitions the findings: none added, none dropped
  OK      every post-flip disposition is one of the four declared
  OK      an UNRESOLVED finding becomes `undisposed` and stays red
  OK      a history-only grant whose value is gone at HEAD reads `repaired`
  OK      a value still at HEAD is `recorded-not-repaired`, never `repaired`
  OK      post-flip cannot manufacture a disposition for an unnamed finding
  detector fingerprint : 9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a
SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 35 disposition/strength assertions, 0 failed
```

**`repaired` is the only disposition this program infers, and it infers it from two scans
rather than from a sentence anybody wrote:** a `(path, family)` that a register entry grants
in the `history` scope and that the tracked scan does *not* find at `HEAD` is a value
somebody removed. Everything else is a relabelling of a disposition a human already granted.

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

**Re-verified `2026-08-12`, after the post-flip mode landed**, because a mode that changes
what a program reports is exactly when somebody is tempted to change what it detects:

```
$ python -c "import audit_public_readiness as m; print(len(m.ALLOWLIST), len(m.FAMILIES),
             m.ENTROPY_FLOOR, m.detector_fingerprint() == m.DETECTOR_FINGERPRINT)"
30 8 4.2 True
```

Thirty allowlist entries, eight secret families, entropy floor `4.2`, and the fingerprint
still `9cdd7b45…`. **Not one detector was touched to produce the register in §1.**

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
`pyproject.toml` files, in two workflow files and in the author line of all 47 commits on
`master`. What is newly disclosed is that the *local Windows account* is `shaug` rather than
something else. Small, not zero, and enumerated to nine files rather than gestured at.

**Post-flip these two classes get a third column: what is still worth doing.** The layout
class is now published on 47 commits and cannot be retracted, so repairing a producer stops
being risk reduction and becomes hygiene — worth doing because a relative path is a better
artefact, not because it hides anything. The username class is identical in that respect.
**Nothing in §4 is urgent any more, and saying so is more useful than leaving a list that
reads like an outstanding action.**

---

## 5 · The rotated judge credential

`docs/deploy/JUDGE-PACK.md` publishes host, port, database, user `mainline_judge` and
`sslmode=verify-full`, and states that the password is not in this repository. The audit was
run **after** the rotation landed, and the password appears in no tracked file.

Three independent measurements, none of which required holding the credential:

1. **The family scan.** `bearer_or_jwt` returns **zero unresolved findings** over 7,402
   tracked files and 1,010,052 added lines of history.

   **`high_entropy_secret` no longer returns zero, and that sentence is corrected rather
   than kept.** On `2026-08-11` it did; on `2026-08-12` it returns **five** unresolved
   tracked hits, and each one was opened and read:

   | file | what the detector matched |
   |---|---|
   | `evidence/aws/COST.md` ×2 | the model ids `au.anthropic.claude-…` and `apac.anthropic.claude-…` |
   | `docs/leads/ship-final.md` | a `docs/…` path sitting after a colon |
   | `tests/unit/aws/test_common_redaction.py` | AWS's published `wJalrXUtnFEMI/…EXAMPLEKEY` placeholder |
   | `verticals/mainline/demo/judge/MCP-CONFIG.md` | the cluster hostname, beginning `mainli…` |

   **None is a password, and none is in `docs/deploy/`, `scripts/deploy/` or `qa/`** — none
   is anywhere the judge password could plausibly have been written. The hits in
   `JUDGE-PACK.md` (cluster hostname) and `judge_access.py` (a file path) remain waived
   with their reasons; they are armed by the literal placeholder
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

   That sweep was taken on `2026-08-11`, at 7,312 tracked files and 901,810 added lines;
   the tree is now 7,402 and 1,010,052. **It has not been retaken**, so read it as a
   statement about that tree. It is transcribed here rather than re-run because it is not
   a mode of the scanner and re-running it is somebody's deliberate act, not a side effect
   of writing this page.

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
$ python -I -S scripts/submission/audit_public_readiness.py --self-test
SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 35 disposition/strength assertions, 0 failed
$ echo $?
0

$ python -I -S scripts/submission/audit_public_readiness.py          # the register
...
REGISTER: INCOMPLETE - 54 finding(s) are undisposed. Nothing was deleted to reach
this number; each one is listed above with its path, and each needs a repair, a
Waiver, or a register entry.
$ echo $?
3

$ python -I -S scripts/submission/audit_public_readiness.py --pre-flip   # the old gate
...
VERDICT: NOT READY - failing checks: secrets_tracked, secrets_history, absolute_paths
$ echo $?
1
```

`-I -S` disables site-packages, which is how the standard-library-only claim is checked
rather than asserted. All three run to completion under it.

**Three exit codes, three different sentences.** `0` is *the register is complete*, `1` is
the historical *do not flip*, and `3` is *this register is incomplete*. `3` is deliberately
not `1`: a caller that treats "undisposed findings exist on a public repository" as "the
flip is blocked" would be acting on a sentence that no longer has a referent.

The full machine rows — every finding, the complete allowlist, the complete register with
every reason, and the post-flip partition under `post_flip_register` — are written to
`qa/public-readiness.json` (`schema: mainline.qa.public-readiness/1`) by `--json`. **The
committed copy of that artefact is from `2026-08-11T07:44:29Z` and this worker did not
regenerate it, because it is not this worker's file**; its owner is named in the provenance
block of `PUBLIC-FLIP-CHECKLIST.md`. Regenerating it is one command, and the artefact
reaches a byte-identical fixed point on the second run — measured here at 263,409 bytes on
runs 2, 3 and 4, which is the property that stopped it growing without bound (§2.4).

The register itself, with the reasoning organised into seven sections, is
`docs/submission/DISCLOSURE-DECISIONS.yaml`.

### What this audit did not do

It did not push. It did not rewrite history. **It did not change the repository's
visibility — the flip was already done, by the orchestrator with the founder, on
`2026-08-11`.** It edited no file outside the ones its worker owns; in particular it did
**not** regenerate `qa/public-readiness.json`, and the divergence between that artefact and
this page is stated in the header rather than papered over by writing a file this worker has
no title to.

The record of the act is the checklist, not this page.
`docs/submission/PUBLIC-FLIP-CHECKLIST.md`.
