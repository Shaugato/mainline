<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PUBLIC-READINESS — what flipping the repository actually publishes

**Measured 2026-08-10 against the working tree at the repository root and the live remote
`https://github.com/Shaugato/mainline.git`.** Every row below carries the command that
produced it and what that command printed. Nothing here is asserted; regenerate all of it
with one command:

```
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
```

The program is standard-library only, starts no subprocess but `git`, and opens no socket.
Both claims are checkable: it runs to completion under `python -I -S`, which disables
site-packages entirely, and the file contains no `urllib`, `socket`, `http` or `ssl`
import.

**Current verdict: `NOT READY`. Two rows are red, one unresolved finding.** The red is the
point. Details in §4.

---

## 0 · The irreversibility, stated first because it governs everything else

> **The flip from PRIVATE to PUBLIC is IRREVERSIBLE.** GitHub's fork network, the GHArchive
> event stream, Software Heritage and search-engine caches all outlive a revert, and the
> flip publishes **all 16 commits**, not the tree at HEAD. A value masked at HEAD but
> present in an earlier commit is published anyway.

That last sentence is not a generality. It is the single unresolved finding in this audit,
and §4.1 is about exactly it.

---

## 1 · The checks, and what each printed

Seven checks. Status is one of `PASS` (gating, green), `FAIL` (gating, red) or `INFO`
(reported, never gating). The program exits non-zero if any check is `FAIL`.

| # | check | status | what it asserts |
|---|---|---|---|
| 1 | `secrets_tracked` | **PASS** | no unresolved secret in any tracked file at HEAD |
| 2 | `secrets_history` | **FAIL** | no unresolved secret in any line ever added, on any ref |
| 3 | `ignored_and_untracked` | **PASS** | `.env` / `*.tfstate*` gitignored, untracked, never committed |
| 4 | `tracked_size` | **PASS** | no tracked blob over 5 MiB |
| 5 | `committer_census` | **INFO** | every identity the history will publish |
| 6 | `absolute_paths` | **PASS** | absolute Windows paths, each waived with a stated cost |
| 7 | `repo_state` | **FAIL** | the tree that would actually be published is the tree on disk |

### 1.1 `secrets_tracked` — PASS

Command:

```
git ls-files -z  |  scan 8 families over each file's content
```

Observed:

```
7120 tracked paths scanned; 12 hits (0 unresolved, 12 allowlisted);
aws_access_key_id=2, aws_account_id=1, high_entropy_secret=2, private_key_block=7
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
  an ARN, after `iam::`, or on a line naming an account, it returns 3. The founder's own
  account is additionally matched unconditionally, so the detector cannot be defeated by
  an edit that removes the surrounding word "account".
* A bare Shannon-entropy scan (`>= 4.5` bits/char, `>= 40` chars) returns **1,021 hits
  across 66 files** — `pnpm-lock.yaml` integrity digests (424), `uv.lock` (243), the
  reference ledger bundle (132). Narrowed to "high-entropy token preceded on the same line
  by a secret-shaped key name, excluding dotted identifiers", it returns 2.

Both counts were measured before the thresholds were chosen, not after.

### 1.2 `secrets_history` — **FAIL**

Command:

```
git log -p --all -U0 --no-color  |  scan 8 families over '+' lines
```

Observed:

```
16 commits, 805266 added lines scanned; 13 distinct (commit,path,family) hits
(1 unresolved, 12 allowlisted);
aws_access_key_id=2, aws_account_id=2, high_entropy_secret=2, private_key_block=7
```

The one unresolved finding is §4.1.

### 1.3 `ignored_and_untracked` — PASS

Command:

```
git check-ignore -q -- .env terraform.tfstate ;
git ls-files ;
git log --all --diff-filter=A -- .env '*.tfstate*'
```

Observed:

```
check-ignore: {'.env': True, 'terraform.tfstate': True, 'terraform.tfstate.backup': True};
tracked .env-like: none; tracked tfstate: none;
history adds .env: none; history adds tfstate: none
```

`.env` exists on disk (557 bytes, mtime 2026-08-07) and is matched by `.gitignore:6`;
`*.tfstate*` by `.gitignore:7`. The history probe is the load-bearing half: a file can be
gitignored *today* and still be sitting in a commit from last week. It is not. The only
tracked path beginning `.env` is `.env.example`.

### 1.4 `tracked_size` — PASS

Command:

```
git ls-files -s -z | git cat-file --batch-check='%(objectname) %(objecttype) %(objectsize)'
```

Observed:

```
7120 tracked blobs, 49075427 bytes total (46.8 MiB);
largest verticals/mainline/fixtures/corpus/answer-key/clause_revision.jsonl
at 1673465 bytes (1.60 MiB); 0 over the limit
```

Blob sizes come from the object store, not from `stat`, so the number is what a clone
actually transfers rather than what this checkout happens to hold. **46.8 MiB is a
comfortable clone for a judge on a conference network.**

### 1.5 `committer_census` — INFO

Command:

```
git log --all --format='%an <%ae>|%cn <%ce>' | sort | uniq -c
```

Observed:

```
16 commits, 1 distinct identity string(s): Shaugato Paroi <shaugato2003@gmail.com> x16
```

One identity, author and committer, across every commit on every ref. No co-author
trailers introduce a second address, and no `users.noreply.github.com` alias is in use —
which means **the flip publishes a real personal email address, permanently and by
design.** That is a deliberate, ordinary choice for an open-source project and it is
recorded here so it is a choice rather than a surprise. Enabling GitHub's email-privacy
alias after the fact does not retract the sixteen commits already carrying the address.

### 1.6 `absolute_paths` — PASS (11 waivers, each with a stated cost)

Command:

```
git ls-files -z  |  scan for (?<![A-Za-z0-9_])[A-Za-z]:\\?<segment>\ and :/<segment>/
```

Observed:

```
10 file(s), 76 hit(s); 0 unresolved, 11 allowlisted. Backslash form:
docs/release/gate-refusal-proof.md(4),
evidence/gate-refusal/proof-20260809T213857Z.json(1),
evidence/gate-refusal/proof-20260810T004200Z.json(1),
packages/trappoint-testkit/src/trappoint_testkit/cluster.py(1),
packages/trappoint-testkit/tests/test_shared_cluster_contract.py(1),
qa/test-state.json(52),
tests/eval/recall_calibration/artefacts/calibration_report.json(1)
```

**A note on the regex, because the first one was wrong.** An initial draft matched
`[A-Za-z]:\\?.` and reported **113 files**. Reading them showed that 105 were assertion
messages of the form `"...NOT A PASS:\n"` — a letter, a colon, and an escaped newline.
Requiring a drive letter, then a path *segment*, then a further separator drops the count
to the 10 files above, all of which are genuine. The false-positive rate of the first
attempt is recorded here because a scanner nobody audits is a scanner nobody should trust.

### 1.7 `repo_state` — **FAIL**

Command:

```
git remote get-url origin ; git rev-parse --abbrev-ref HEAD ;
git rev-list --left-right --count origin/master...HEAD ; git status --porcelain
```

Observed:

```
origin=https://github.com/Shaugato/mainline.git; branch=master; HEAD=bb21962;
origin/master=174b29f; behind=0 ahead=2; working tree: 59 uncommitted path(s)
```

The uncommitted count is a live number and will move as other workers land files — it was
59 at the moment this document was generated, including this audit's own three new paths.
`ahead=2` is the stable part, and it is the part that blocks. See §4.2.

---

## 2 · Every allowlisted finding, and why it is safe

An allowlist entry is keyed by **exact path plus family** and carries a reason string, so a
waived hit is a decision somebody signed rather than a silent pass. 30 entries produce 35
waived findings across the tracked and history scans (12 tracked, 12 history, 11 paths). They are printed by the program on
every run and written to `qa/public-readiness.json` under `allowlist`.

### 2.1 Published on purpose — cryptographic material (7 findings)

| path | family | why it is safe |
|---|---|---|
| `evidence/reference-ledger/keys/reference-log.NOT-SECRET.key.pem` | `private_key_block` | `docs/HONESTY.md:173-174` states that every file under `evidence/reference-ledger/keys/` is a private key committed deliberately, so a third party can re-sign the reference bundle and reproduce every value in it. The filename carries `NOT-SECRET`. These keys sign nothing outside the reference ledger. |
| `…/reference-tsa.NOT-SECRET.key.pem` | `private_key_block` | as above |
| `…/reference-tsa-root.NOT-SECRET.key.pem` | `private_key_block` | as above |
| `…/reference-webauthn.NOT-SECRET.key.pem` | `private_key_block` | as above |
| `…/reference-witness.NOT-SECRET.key.pem` | `private_key_block` | as above |
| `spec/wire/checkpoint.md` | `private_key_block` | The §7.1 worked test vector. The document says in bold that the key is published deliberately so anyone can reproduce §7, that it signs nothing but this document's example, and that it never was a MAINLINE log key. `trappoint-verify` and `trappoint_ledger.note` both read it out of this file, so deleting it would break the spec/code anti-drift property. |
| `packages/trappoint-ledger/tests/test_receipt.py` | `private_key_block` | **No key here.** The file contains the marker string only, as the `str.index` bounds used at lines 123–125 to slice the published key out of `spec/wire/checkpoint.md`. |

The brief for this audit anticipated five such files. The scan found **seven**; the two
extra are the last two rows, and both are benign for the reasons given. That is why the
scan runs rather than the list being trusted.

### 2.2 AWS's own documentation placeholders (4 findings)

| path | family | why it is safe |
|---|---|---|
| `infra/policy/custody/fixtures/README.md:53` | `aws_access_key_id` | `AKIAIOSFODNN7EXAMPLE` is the access key id AWS prints in its own public documentation. It authenticates nothing and is not derived from any real key. |
| `infra/policy/custody/fixtures/README.md:54` | `high_entropy_secret` | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` is AWS's published secret-access-key placeholder, the counterpart to the id on the line above. |
| `infra/policy/custody/fixtures/plan_compliant.json` | `aws_access_key_id` | The same AWS placeholder inside a recorded terraform plan. The plan was produced against the documentation account `111122223333`, not against the real account. |
| `packages/mainline-agentkit/tests/test_runtime.py:62-64` | `aws_account_id` | `FOREIGN_ACCOUNT_ARN` uses `999999999999` to assert that a Bedrock inference-profile ARN belonging to a *different* account is rejected. Twelve identical digits is a synthetic constant; the sibling ARNs on the same lines use twelve zeroes for the same reason. |

### 2.3 A test corpus that contains an attack, not a credential (1 finding)

| path | family | why it is safe |
|---|---|---|
| `tests/security/injection/corpus/encoded-002-base64-exfil.json:8` | `high_entropy_secret` | A prompt-injection attack corpus entry. The base64 decodes to an instruction asking a model to print its system prompt and any api key. It is the attack this repository tests its refusal against. |

### 2.4 Absolute paths — recorded, not repaired (11 findings)

**Ruling.** An evidence artefact is a record of a run. Editing one so that it looks tidier
is precisely the move this repository refuses. Each of these is therefore recorded with its
cost stated, and the domain that owns the file decides. Nothing in this section is a
credential; the disclosure is directory layout, and in two cases a local Windows account
name.

| path | hits | what it discloses | disposition |
|---|---|---|---|
| `qa/test-state.json` | 52 | `C:\Users\shaug\AppData\Local\Temp\mainline-census-*\junit.xml` — pytest temp dirs captured verbatim by the test census. **Discloses the founder's Windows account name, 52 times.** `shaug` is a prefix of the already-public GitHub handle `Shaugato`, so the marginal disclosure is the local account name only. | recorded, not repaired — quality domain; the next census run can emit relative paths |
| `docs/release/gate-refusal-proof.md` | 4 | Pasted pytest output: `D:\CoackroachDBxAWS\mainline\tests\release\` and a `C:\Users\shaug\AppData\Local\Temp\pytest-of-shaug\` tmpdir. The captured output *is* the document's evidence; paraphrasing it would weaken it. | recorded, not repaired |
| `evidence/gate-refusal/proof-20260809T213857Z.json` | 1 | `migrations_dir` = the absolute path the proof ran against. Layout only. | recorded, not repaired — the next proof run decides |
| `evidence/gate-refusal/proof-20260810T004200Z.json` | 1 | identical | recorded, not repaired |
| `tests/eval/recall_calibration/artefacts/calibration_report.json` | 1 | absolute fixture path in a generated calibration artefact. Layout only. | recorded, not repaired — recall domain |
| `docs/leads/workers.json` | 9 | `D:/CoackroachDBxAWS/mainline/...` inside worker briefs quoting commands. Layout only. | recorded, not repaired — lead-plan domain |
| `docs/STATE-OF-THE-BUILD.md` | 5 | `C:\Users\<name>\Documents\projects\` is a documentation example with a literal `<name>` placeholder, explaining the Windows `MAX_PATH` clone failure; plus `D:/CoackroachDBxAWS/mainline` in worked commands. | safe as written |
| `docs/adr/0040-custody-red-before-green.md` | 1 | one `D:/CoackroachDBxAWS/mainline/` command path. Layout only. | recorded, not repaired |
| `packages/trappoint-testkit/src/trappoint_testkit/cluster.py:511` | 1 | `C:\Program Files\Docker\docker.exe` in a comment explaining why the docker-binary check must not match on a Linux runner. | **not personal data** — safe |
| `packages/trappoint-testkit/tests/test_shared_cluster_contract.py:109` | 1 | the same Docker Desktop path as a test vector. | **not personal data** — safe |

### 2.5 This audit's own output (3 waivers)

`qa/public-readiness.json`, `docs/submission/PUBLIC-READINESS.md` and the scanner itself
quote the values they report. An audit that redacts a value which is public by design tells
the reader less, not more — so AWS's documentation placeholders are quoted verbatim.
**Unresolved findings are never quoted in full:** the program redacts them to a six-character
prefix plus a length, and the self-test asserts that redaction happens.

---

## 3 · Two claims the brief asked to be verified against the tree

**Trademarks.** `TRADEMARKS.md` asserts that no third-party trademarks are used. Measured:

```
$ git ls-files | grep -icE '\.(png|jpg|jpeg|gif|svg|ico|webp|bmp)$'
0
```

**The repository tracks zero image files of any kind**, so no third-party logo can be
present and nothing can imply endorsement by way of a mark. CockroachDB, AWS, Bedrock,
Docker and GitHub are named throughout in running text to say which product was used — that
is nominative use and it is fine. One wording note, raised as a cross-domain item because
this audit does not own the file: the sentence *"No third-party trademarks are used in this
repository"* is strictly stronger than the tree supports, since naming a product *is* use of
its mark, albeit permitted. *"No third-party trademark is used other than nominatively, and
no third-party logo or mark appears"* would be exactly true.

**Committer identity.** Verified independently in §1.5: one identity, sixteen commits,
no second address.

---

## 4 · The unresolved finding and the blocking precondition

### 4.1 The masked account number is still in a commit that is already on the remote

`docs/adr/0002-g1-platform-ground-truth.md:64` printed the real twelve-digit AWS account
id. It is not a credential, but a published account id enables cross-account enumeration
and there is no reason to publish one. **It has been masked to `0229…8246`**, with a
bracketed sentence stating that the full value lives in the founder's gitignored `.env`.
The edit is one line:

```
$ git diff --stat -- docs/adr/0002-g1-platform-ground-truth.md
 docs/adr/0002-g1-platform-ground-truth.md | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

$ grep -c '<the twelve digits>' docs/adr/0002-g1-platform-ground-truth.md
0
```

**That is necessary and it is not sufficient, and this is the finding that matters.**

```
$ git branch -r --contains e518787
  origin/HEAD -> origin/master
  origin/master
```

The value was introduced by commit `e518787` (*"docs(adr): 0002 G1 platform ground truth"*),
**and `e518787` is already on `origin/master`.** Masking the working tree changes what a
visitor reads at HEAD. It changes nothing about what `git log -p` prints, what the GitHub
"blame" view shows, or what any clone contains. Flipping the repository public publishes
that commit along with the other fifteen.

The audit therefore keeps this row red rather than closing it, and there are exactly two
honest ways to clear it. **Neither is chosen here — the choice is the founder's, and it must
be made before the flip, not after.**

* **Option A — accept it, in writing.** A twelve-digit AWS account id is not a credential.
  AWS treats it as semi-sensitive rather than secret: it appears in every ARN a partner is
  given, and possession of it grants nothing without a matching principal and policy. The
  realistic exposure is cross-account enumeration and targeted phishing. To take this
  option, add this entry to `ALLOWLIST` in the scanner, which makes the acceptance a
  reviewable line of code rather than a shrug:

  ```python
  Waiver(
      path="docs/adr/0002-g1-platform-ground-truth.md",
      family="aws_account_id",
      reason=(
          "Present in commit e518787, which was pushed to origin/master before the value "
          "was masked at HEAD. Accepted: an AWS account id is not a credential and grants "
          "nothing without a principal. Masked at HEAD so it is not the first thing a "
          "reader sees; history not rewritten because rewriting shared history to hide a "
          "non-secret is a worse trade than disclosing it."
      ),
  )
  ```

* **Option B — rewrite history before the flip.** `git filter-repo --replace-text` over the
  single value, then a force-push. This rewrites every commit hash from `e518787` forward.
  Because the repository is still **private and has no forks**, the blast radius today is
  one developer's local clone — which is the smallest it will ever be. **After the flip it
  is unbounded.** If Option B is ever going to be taken, today is the cheapest day to take
  it.

The audit's job is to make sure this is decided rather than defaulted. It exits non-zero
until one of the two is done.

### 4.2 `repo_state` — the tree on the remote is not the tree on disk

```
$ git rev-list --left-right --count origin/master...HEAD
0	2
$ git status --porcelain | wc -l
59
$ git ls-files --error-unmatch LICENSE
error: pathspec 'LICENSE' did not match any file(s) known to git
```

Two commits — `c76c454` (*gate refusal proven, test infra consolidated, honesty docs*) and
`bb21962` (*independent re-run of the refusal proof*) — exist locally and are not on
`origin/master`. A further 59 paths are uncommitted, and **the root `LICENSE` is among
them: it is not tracked at all.**

Flipping visibility today would publish `174b29f`, a tree in which the proof script, the
consolidated test infrastructure, `docs/HONESTY.md` and the licence file do not exist.
Requirement 1 of the hackathon rules — *public repo with an open-source LICENSE file* — is
a Stage One pass/fail, and it would fail on a technicality that is entirely avoidable.

This check is red on purpose and will stay red until `git push` has happened. **This audit
does not push and does not flip.**

---

## 5 · Preconditions for the flip

The flip is irreversible. It may be performed only when **all five** of the following hold.
The first four are mechanical and this program checks three of them.

| # | precondition | checked by | state today |
|---|---|---|---|
| **P1** | The root `LICENSE` is committed, and every intended path is committed. | `repo_state` (`git status --porcelain` is empty) | **NOT MET** — 59 uncommitted paths, `LICENSE` untracked |
| **P2** | `origin/master` and `HEAD` are the same commit — the remote holds the tree that was audited. | `repo_state` (`ahead=0 behind=0`) | **NOT MET** — 2 ahead |
| **P3** | The account-number-in-history finding (§4.1) is disposed of by Option A or Option B, in writing. | `secrets_history` | **NOT MET** — 1 unresolved |
| **P4** | `python scripts/submission/audit_public_readiness.py` exits **0**, re-run against the exact commit that will be published. | itself | **NOT MET** — exits 1 |
| **P5** | The founder accepts, explicitly, that `shaugato2003@gmail.com` (§1.5), the deliberate `NOT-SECRET` private keys (§2.1), the `shaug` Windows account name in `qa/test-state.json` (§2.4) and the `D:\CoackroachDBxAWS\mainline` layout become permanently public. | human judgement — nothing automates this | **OPEN** |

P4 is not a formality. Re-run the audit **against the commit that will actually be
published**, after the push, not against the working tree beforehand: §4.2 exists precisely
because those two things are different today.

### What this audit did not do

It did not push. It did not flip visibility. It did not rewrite history, edit any evidence
artefact, or touch any file outside the four it owns
(`scripts/submission/audit_public_readiness.py`, `qa/public-readiness.json`, this document,
and the one-line mask in `docs/adr/0002-g1-platform-ground-truth.md`).

---

## 6 · Reproducing this document

```
$ python scripts/submission/audit_public_readiness.py --self-test
SELF-TEST PASSED: 9 families, 9 fired, 0 missed

$ python -I -S scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
...
VERDICT: NOT READY - failing checks: secrets_history, repo_state
$ echo $?
1
```

`--self-test` plants one secret of every family into a temporary tree and requires the
scanner to fire on each, requires a clean control file to produce nothing, and requires
every planted hit to be classified `UNRESOLVED` — so an allowlist that had grown too broad
would be caught. It found a real defect on its first run: the planted `AKIA` sample was 18
characters where the family requires 16, and the scanner correctly did not fire. That is
what the mode is for.

The full machine rows, including every finding and the complete allowlist with reasons, are
in `qa/public-readiness.json` (`schema: mainline.qa.public-readiness/1`).
