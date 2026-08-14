<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PUBLIC-FLIP-CHECKLIST — the record of an irreversible act

**Written as a gate by worker `w9-public-readiness` on 2026-08-11. Converted to a record by
`w10-stale-sweep` on 2026-08-12, after the flip.**

`github.com/Shaugato/mainline` is **PUBLIC**. This page was a list a human ticked
immediately before flipping it, and every item named the command that decided it. It is
kept, item for item, because after an irreversible act the checklist stops being a gate and
becomes the only durable answer to *what did you check, and what did you knowingly carry?*

**Nothing below is an action any more.** Items that were ticked say so. Items that were
carried red on purpose say so, and say who accepted them. One item — the exact-value
credential check — could only ever be run by the person holding the credential, and this
page does not assert it was.

Verified for this revision, from outside any authenticated session:

```
$ gh repo view Shaugato/mainline --json visibility,isPrivate,defaultBranchRef
{"defaultBranchRef":{"name":"master"},"isPrivate":false,"visibility":"PUBLIC"}
$ curl -sI https://github.com/Shaugato/mainline | head -1
HTTP/1.1 200 OK
```

The second is the load-bearing one. GitHub returns `404`, not `403`, for a private
repository, so an authenticated check cannot tell the two states apart.

---

## 0 · The irreversibility, kept verbatim because it was the whole point

> ## **THE FLIP IS IRREVERSIBLE, AND IT PUBLISHES ALL COMMITS ON ALL REFS — NOT THE TREE AT HEAD.**
>
> **GitHub's fork network, the GHArchive event stream, Software Heritage and search-engine
> caches all outlive a revert. Within minutes of the flip the history exists in places
> nobody in this project controls, and setting the repository back to `PRIVATE` retracts
> none of them.**
>
> **A value masked at `HEAD` but present in an earlier commit is published anyway.** Every
> line ever added on every published ref became readable at once: `git log -p`, the blame
> view, and any clone.
>
> **There was no partial flip and no undo. The only cheap day to change the history was a
> day before the flip, and after it there is no such day ever again.**

**The paragraph above used to carry the constant "ALL 44 COMMITS ON ALL 9 REFS", and the
constant is what has been removed.** Not because the act got smaller, but because a number
typed into a warning goes stale while the warning stays believable, which is the worst
combination available. Re-derive it; do not read it here:

```
git ls-remote --heads origin | wc -l      # branches a visitor can actually see
git rev-list --count origin/master        # commits on the default branch
git rev-list --all --count                # commits on THIS WORKSTATION - not the same thing
```

### 0.1 What was actually published, measured 2026-08-12

```
$ git ls-remote --heads origin | wc -l                                 4
$ git rev-list --count origin/master                                  47
$ git rev-list --count origin/master origin/w1/… origin/w5/… origin/w7/…    52
$ git for-each-ref refs/heads | wc -l                                 56     # never pushed
$ git rev-list --all --count                                         113     # this machine
```

**52 commits over 4 branches, 47 of them on `master`.** Confirmed independently against the
API — `gh api "repos/Shaugato/mainline/commits?sha=master&per_page=1" -i` reports
`page=47; rel="last"`.

**`git log --all` on this workstation reaches 113 over 67 refs, and 61 of those commits are
not published.** They live on 56 local `w8-p-*` and `w9/*` branches — the anti-vacuity
plants that prove CI lanes can go red — which were never pushed. The pre-flip audit walked
`--all`, which was the conservative choice while the act was still ahead: it could only
over-count, and over-counting an irreversible act is the safe direction to be wrong in.
After the flip it is simply the wrong instrument, and
`scripts/submission/audit_public_readiness.py` now measures the published surface as well
and prints the gap.

The six `origin/dependabot/*` branches this checklist enumerated on `2026-08-11` have since
been deleted on the remote. A stale remote-tracking cache still lists them here until
`git remote prune origin`, so the audit's own reading is `58 over 10`;
`git ls-remote --heads origin` is the live answer and it is `4`.

---

## 1 · The audit — ticked, and what it says now

```
python scripts/submission/audit_public_readiness.py --pre-flip     # the gate, reproducible
python scripts/submission/audit_public_readiness.py                # the standing register
python scripts/submission/audit_public_readiness.py --self-test
```

- [x] **1.1** `VERDICT: READY`, `$?` = `0`. **Ticked at `ead0f7c` on 2026-08-11.**
- [x] **1.2** `qa/public-readiness.json` showed `"verdict": "READY"`, `"failed_checks": []`,
      `"unresolved_findings": 0`.
- [x] **1.3** The self-test passed and exited 0.
- [x] **1.4** The detector fingerprint was
      `9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a`.

**State as measured 2026-08-11, at the flip: PASS.** 8 checks, 7 `PASS`, 1 `INFO`, 0 `FAIL`;
0 unresolved findings, 77 allowlisted, 92 disclosed.

**State as measured 2026-08-12, one day later: 54 undisposed findings and three `FAIL`
rows.** Fifty-four findings accumulated in files that landed during the completion wave, and
nobody has yet repaired them or written them into the register. They are enumerated by
domain in `PUBLIC-READINESS.md` §1.9 and **not one of them is a live credential**: no GitHub
token, no Slack token, no CockroachDB Cloud API key, no private key outside the deliberately
published `NOT-SECRET` set.

**State as measured 2026-08-14, three days after the flip: 160 undisposed findings and four
`FAIL` rows.** The trend is the wrong way and it is printed rather than smoothed. `python
scripts/submission/audit_public_readiness.py` exits **3** and reports
`160 UNRESOLVED, 81 ALLOWLISTED, 84 DISCLOSED` over 325 findings; the fourth `FAIL` is
`repo_state`, red only because this documents wave is uncommitted, and it clears with a push.
**The credential sentence above was re-checked on 2026-08-14 and is still true** — the five
families the scanner reports are `aws_access_key_id`, `aws_account_id`, `bearer_or_jwt`,
`high_entropy_secret` and `private_key_block`, and every `private_key_block` hit is inside the
published `NOT-SECRET` reference-ledger set.

**The one row that went the right way is the one that measures whether this page is honest:**
`disclosure_register` is **PASS** with **0 stale** — 59 entries granting 84 findings, and
every grant still names a finding that still exists. A register whose grants outlive their
findings has started to launder; this one has not.

`PUBLIC-READINESS.md` §1.9 remains an enumeration of the 54, explicitly relabelled there as a
**partial** list. Enumerating the other 106 is owed by the domains that created them.

The detector fingerprint is **unchanged**, re-verified after the post-flip mode landed:
`9cdd7b45…`, thirty allowlist entries, eight families, entropy floor `4.2`. **Adding a mode
that reports differently is exactly when somebody is tempted to change what is detected, so
that is the thing the self-test pins.**

**No red was carried into this flip that anybody hid.** Item 9 is the list that was
knowingly carried, and it is a list of CI lanes, not of findings.

---

## 2 · `origin/master` and `HEAD` — ticked at the flip

```
git rev-parse HEAD ; git rev-parse origin/master
git rev-list --left-right --count origin/master...HEAD
```

- [x] **2.1** Both SHAs written out in full at flip time.
- [x] **2.2** Identical, character for character.
- [x] **2.3** `0` and `0` — nothing ahead, nothing behind.

**Today, 2026-08-12:**

```
HEAD          1d41442798cf…
origin/master 1d41442798cf…
behind=0 ahead=0     working tree: 49 uncommitted path(s)
```

The 49 uncommitted paths carry a different weight than they did before the flip. They are no
longer files the judges will never see; they are files the public repository does not yet
show. The remedy is the same and it is a push.

---

## 3 · The working tree is clean — CARRIED, and it still is not

```
git status --porcelain ; git stash list
```

- [ ] **3.1** Output empty. **NOT MET at the flip (97 paths), NOT MET today (49).**
- [x] **3.2** `git stash list` empty.

This was the item most likely to be waved through, and it was: nine workers were landing
files into the tree while the checklist was being written. It is recorded as carried rather
than quietly ticked. Do not copy the number from this page — run the command.

---

## 4 · The licence file and `LICENSES/` — ticked, and item 4.3 has since gone green

```
git ls-files --error-unmatch LICENSE ; git ls-files LICENSES/ ; python scripts/qa/check_reuse.py
```

- [x] **4.1** `git ls-files --error-unmatch LICENSE` exits 0. A `LICENSE` that exists on
      disk but is untracked publishes a repository with no licence file and fails hackathon
      Stage One on a technicality. The audit before this one caught exactly that.
- [x] **4.2** `LICENSES/` is tracked and non-empty — four licence texts.
- [x] **4.3** `non_spdx_spelling.FSL-1.1-ALv2` was **1254** against a baseline of **1213**
      at the flip, and was expected to stay red.

**Re-measured 2026-08-12, and this one improved on its own terms:**

```
$ python scripts/qa/check_reuse.py | tail -2
  improved   metric=reuse_toml_patterns_matching_nothing baseline=5 measured=1
OK — 7402 tracked files, 0 uncovered, 4 licence texts, no counted number rose.
$ echo $?
0
```

`FSL-1.1-ALv2` resolves at **1213**, equal to its floor, against 4,860 for the
`LicenseRef-` form. **No baseline was lowered**; the migration closed the gap. The
`submission` workflow, whose only remaining red this was, is green on `master` at
`1d41442`.

---

## 5 · No credential is tracked — ticked at the flip

- [x] **5.1** `secrets_tracked` and `secrets_history` both `PASS`, `unresolved: 0`.
- [x] **5.2** `ignored_and_untracked` `PASS`: `.env` and `*.tfstate*` gitignored, untracked,
      **and never added in any commit on any ref**. The history half is the load-bearing
      half, and it still passes today.
- [x] **5.3** `disclosure_register` `PASS` with `0 stale`. Still `0 stale` today, over 59
      entries granting 80 findings.
- [x] **5.4** `docs/submission/DISCLOSURE-DECISIONS.yaml` read end to end before ratifying.
      **It is meant to be read, not trusted.** Delete any entry you disagree with and
      re-run — the finding comes back red.

**As measured at the flip: PASS**, 7,314 tracked paths and 901,810 added lines of history,
0 unresolved. **As measured 2026-08-12:** 7,402 tracked paths, 1,010,052 added lines,
37 unresolved across those two checks — see item 1 and `PUBLIC-READINESS.md` §1.9.

---

## 6 · The rotated `mainline_judge` password — the one item this page does not assert

**The password is shown once by `scripts/deploy/judge_access.py attest` and is not
recoverable afterwards, by design. Only the person holding it can run the exact-value
check.**

```
printf '%s' "$JUDGE_PASSWORD" | python scripts/submission/audit_public_readiness.py --assert-absent
```

- [ ] **6.1** Output ends `ABSENT: YES`, `$?` = `0`. **This page does not record that it was
      run, and does not assume it.**
- [ ] **6.2** Run after the final rotation and after the final push.
- [x] **6.3** The mode reads the value from **stdin only**, never an argument vector: an
      argument is visible in `ps`, lands in shell history, and is captured by CI logs. Only
      a SHA-256 prefix is printed.

**What was measurable without holding the credential, all after the rotation landed, and
re-measured today:**

* `bearer_or_jwt`: **0 unresolved findings** tree-wide, unchanged.
* `high_entropy_secret`: **0 at the flip, 5 today** — two model ids in `evidence/aws/COST.md`,
  a `docs/` path in a lead plan, AWS's own published secret-key placeholder in a redaction
  test, and the cluster hostname in `MCP-CONFIG.md`. **None is a password and none is in
  `docs/deploy/`, `scripts/deploy/` or `qa/`.** The zero is corrected rather than kept.
* A shape sweep for `secrets.token_urlsafe(24)` output — 32 characters of `[A-Za-z0-9_-]`,
  with **no key-name context requirement**, so strictly wider than any detector family —
  found 31 candidates tracked and 33 in history, in four files: `pnpm-lock.yaml` (22),
  `evidence/reference-ledger/bundle.json` (5), `console/tests/vectors/checkpoint.json` (3)
  and one reference-ledger `.NOT-SECRET` key. All pre-existing published material. **That
  sweep was taken on 2026-08-11 and has not been retaken.**
* `evidence/deploy/judge-run.json` `credential_hygiene`: `password_was_issued_this_run:
  true`, `bytes_scanned: 15633`, `matches: 0`, `holds: true`.

That is strong evidence and it is not the same thing as checking the value. **Item 6 was
never something this page could tick, and it does not tick it now.**

---

## 7 · The committer census — ticked, and it has moved since

- [x] **7.1** The founder saw the measured number rather than the briefed one. The brief for
      this work said "19 commits, 1 identity"; the measurement said 44 over 9 refs.
- [x] **7.2** The founder accepted that **`shaugato2003@gmail.com`, a real personal address,
      becomes permanently public**. No `users.noreply.github.com` alias is in use for the
      human author, and enabling GitHub's email-privacy setting afterwards does **not**
      retract commits already carrying it.
- [x] **7.3** The extra identities were bot accounts (`dependabot[bot]`, `GitHub`) and
      disclosed nothing a public repository would not already show.
- [x] **7.4** The six Dependabot branches have since been **deleted on the remote**.

**Measured 2026-08-12, over the four refs that are actually published:**

```
$ git log --format='%an <%ae>' origin/master origin/w1/… origin/w5/… origin/w7/… \
    | sort | uniq -c
     45 Shaugato Paroi <shaugato2003@gmail.com>
      7 MAINLINE certification <shaugato2003@gmail.com>
```

**Two identity strings, one real address, 52 published commits.** A third string,
`w8 <w8@local>`, appears on 39 commits on this workstation and on **none** that were pushed.

---

## 8 · The disclosure decisions the founder ratified

Twenty-three register entries name the founder as ratifier at this item, and they became
valid when it was ticked. They are recorded here in the past tense because they are now
facts about a public repository rather than proposals.

- [x] **8.1 The AWS account id `0229…8246` is permanently public.** It survives at HEAD in
      six documentation files as recorded evidence — quoted `aws sts get-caller-identity`
      output, a KMS transcript, the CloudFront `AccessDenied` refusal, a committed
      `terraform plan`. It is **not** a credential and grants nothing without a principal
      and a policy; the realistic cost is cross-account enumeration and more targeted
      phishing.
- [x] **8.2 Option A was taken on the history finding; Option B was refused.** The id is in
      commits `5ddaa3a` and `e518787`, both on `origin/master`. It was accepted in writing —
      fourteen `history-already-pushed` register entries, each naming its path, commit, date
      and decider — rather than removed by `git filter-repo --replace-text` and a
      force-push, because rewriting shared history to hide a non-credential is a worse trade
      than disclosing it and would invalidate every commit SHA this repository's own
      evidence cites. **That decision can no longer be reversed.**
- [x] **8.3 The Windows account name `shaug` is permanently public**, in nine files
      (`abs-path-username`, enumerated in `PUBLIC-READINESS.md` §1.6). It is a prefix of the
      already-public handle `Shaugato`, so the marginal disclosure is the local account name
      only.
- [x] **8.4 The directory layout `D:\CoackroachDBxAWS\mainline` is permanently public**, in
      35 files at the time of ratification (`abs-path-layout`), and in more now — see
      `PUBLIC-READINESS.md` §1.9.
- [x] **8.5 The five `NOT-SECRET` private keys under `evidence/reference-ledger/keys/` and
      the worked test-vector key in `spec/wire/checkpoint.md` are published on purpose**, so
      a third party can re-sign the reference bundle and reproduce every value in it. They
      sign nothing outside it.

**One consequence of 8.1 that only became visible after the flip.** The account id was
masked to `000000000000` in the plan artefacts and to `999999999999` in
`evidence/deploy/deploy-dry-run.json`, and **the mask is itself flagged** — by this audit as
an `aws_account_id` finding, and by `aws-evidence` CI as `[SEC-ACCOUNT-ID] … a bare 12-digit
run '999999999999' survives UUID/digest/decimal masking`. Two checkers disagree about
whether twelve identical digits is a mask or a value. Both are defensible, neither was
silenced, and recording the disagreement is cheaper than picking a winner.

---

## 9 · What was red on purpose, and stays red

The flip did not require these to be green, and **turning any of them green to make the flip
look tidier would have been the exact failure this repository exists to avoid.** They are
listed so nobody mistakes them for oversights.

- [x] **9.1** `submission` CI was red on
      `REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254`.
      **This one has since gone green on its own terms** — measured 1213 against a floor of
      1213, with no baseline lowered. See item 4.
- [x] **9.2** The MI ratchet and the custody chain. **The number recorded here at the flip
      was 28/30 and it was seven invariants out of date.** Re-derived 2026-08-12:

      ```
      $ python scripts/mi_ratchet.py | tail -1
      21 pending / 9 enforced
      ```

      **21 of 30 MAINLINE invariants are pending, and the lane stays red.** Correcting the
      number sharpens the red; it does not soften it. The custody chain is **7 of 16 checks
      unimplemented** — the cryptographic half — confirmed by running the verifier:
      `16 checks | 8 passed | 1 failed | 7 not checked`, exit 1.
- [x] **9.3** `demo-health` is red because no demo is deployed. It goes green on its own the
      moment `docs/submission/SUBMISSION.json` holds a `demo_url`, and not before. Its
      message says exactly that, in those words.
- [x] **9.4** No `continue-on-error` and no `|| true` was added anywhere to reach any of the
      above.

`docs/CI-STATE.md` is the current board, and it distinguishes reds that report a true
incompleteness from reds that are runner-infrastructure failures — a distinction a judge
reading the Actions tab cannot make unaided.

---

## 10 · The flip itself

- [x] **10.1** Item 2 re-run against the final commit and both SHAs written out.
- [x] **10.2** Item 1 re-run against that same commit, exit 0.
- [ ] **10.3** Item 6 run with the real password. **Not asserted here** — see item 6.
- [x] **10.4** Items 7 and 8 ratified by the founder, not by an agent.

**The command that was run:**

```
gh repo edit Shaugato/mainline --visibility public --accept-visibility-change-consequences
```

**Verified afterwards, and again for this revision:**

```
$ gh repo view Shaugato/mainline --json visibility,url
{"visibility":"PUBLIC","url":"https://github.com/Shaugato/mainline"}
$ curl -sI https://github.com/Shaugato/mainline | head -1
HTTP/1.1 200 OK
```

The signed-out `curl` is required, not decorative: GitHub returns `404` rather than `403`
for a private repository, so an authenticated check cannot distinguish the two states.

---

## What is still owed, now that none of it is a gate

1. **The undisposed findings** need a repair, a waiver or a register entry each. **54 on
   2026-08-12; 160 on 2026-08-14.** The 54 are listed by owning domain in
   `PUBLIC-READINESS.md` §1.9, which is now labelled a partial list; the other 106 are not yet
   enumerated anywhere and enumerating them is the work. None is a credential; all of them are
   somebody's hygiene.
2. **`qa/public-readiness.json` is stale** — generated `2026-08-11T07:44:29Z`, recording
   `verdict: READY, 0 unresolved`, against a live run that finds 160. Regenerating it is one
   command and it belongs to the public-readiness domain. `w10-stale-sweep` deliberately did
   not write it, and neither did the 2026-08-14 documents wave.
3. **Item 6 has never been recorded as run.** It costs one piped command and only the
   credential holder can do it.
4. **`evidence/provenance/commit-window.json` and `third-party.json` are stale**, and
   `scripts/submission/provenance_census.py --check` exits **1** saying so —
   `DRIFT … 12934 bytes on disk, 56903 generated`. They are anchored to `bb21962`; `HEAD` is
   70 commits later. The window verdict over all 86 commits is still `ALL INSIDE`, so the
   claim is unharmed; only the artefacts behind the `[src: …]` pointers in `DISCLOSURE.md`
   are old. Regenerating is one command and belongs to the provenance domain.
5. **`provenance_census.py` reports `bundles_third_party_code: true` on a false positive.**
   `docs/submission/LICENCE-CENSUS.md` is classified as a foreign licence file because its
   *filename* matches the scanner's licence-file pattern; its SPDX holder — which the scanner
   reads and never tests — is this project. Do not fix it by renaming the document.
   `DISCLOSURE.md` §4 carries the line numbers and the one honest repair.

---

## Provenance

Prepared as a gate by `w9-public-readiness`, 2026-08-11, from measurements taken on this
machine against the live remote. Files that worker owned and wrote:

* `scripts/submission/audit_public_readiness.py`
* `docs/submission/DISCLOSURE-DECISIONS.yaml`
* `docs/submission/PUBLIC-READINESS.md`
* `qa/public-readiness.json`
* `docs/submission/PUBLIC-FLIP-CHECKLIST.md`

**That worker did not run the flip.** The repository was `PRIVATE` when it started and
`PRIVATE` when it finished; the flip was the orchestrator's act, performed with the founder,
after the boxes above were ticked.

Converted from a gate to a record by `w10-stale-sweep`, 2026-08-12, at commit `1d41442`.
That worker did not run the flip either, did not rotate any credential, did not regenerate
`qa/public-readiness.json`, and did not run `terraform apply`. Every number it added was
re-derived on this machine and the command is printed beside it.
