<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PUBLIC-FLIP-CHECKLIST — the gate on an irreversible act

**Prepared by worker `w9-public-readiness` on 2026-08-11.**
**The last line of this document records that this worker did not run the flip.**

This is not a summary. It is a list a human ticks, in order, immediately before flipping
`github.com/Shaugato/mainline` from `PRIVATE` to `PUBLIC`. Every item names the command
that decides it and the output that counts as a pass. **An item that cannot be ticked stops
the flip.** The evidence behind each is in `docs/submission/PUBLIC-READINESS.md`; the
machine rows are in `qa/public-readiness.json`.

---

## 0 · Read this before item 1

> ## **THE FLIP IS IRREVERSIBLE, AND IT PUBLISHES ALL 44 COMMITS ON ALL 9 REFS — NOT THE TREE AT HEAD.**
>
> **GitHub's fork network, the GHArchive event stream, Software Heritage and search-engine
> caches all outlive a revert. Within minutes of the flip the history exists in places
> nobody in this project controls, and setting the repository back to `PRIVATE` retracts
> none of them.**
>
> **A value masked at `HEAD` but present in an earlier commit is published anyway.** Every
> line ever added on every ref becomes readable at once: `git log -p`, the blame view, and
> any clone. Six of the nine refs are Dependabot branches that `git log master` cannot see
> and that a census of the default branch alone would miss entirely.
>
> **There is no partial flip and no undo. The only cheap day to change the history is a day
> before the flip, and after it there is no such day ever again.**

The count is measured, not written down. Re-derive it at flip time:

```
git rev-list --all --count      # 44 at the time of writing
git for-each-ref | wc -l        # 9 at the time of writing
```

If those numbers have moved, the paragraph above is stale and the checklist is being run
against a different repository than the one it was written for. Re-run the audit.

---

## 1 · The audit exits 0

```
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
echo $?
```

- [ ] **1.1** The last line reads `VERDICT: READY` and `$?` is `0`.
- [ ] **1.2** `qa/public-readiness.json` shows `"verdict": "READY"`, `"failed_checks": []`,
      and `"unresolved_findings": 0`.
- [ ] **1.3** The self-test passes and exits 0:
      ```
      python scripts/submission/audit_public_readiness.py --self-test
      ```
      Expect `SELF-TEST PASSED: 9 families, 9 fired, 0 missed; 30 disposition/strength
      assertions, 0 failed`.
- [ ] **1.4** The detector fingerprint printed by the self-test is
      `9cdd7b45074eae6de5043d66f6b6bcf29747be99caf91f7f5041488b89d40c1a`.
      **If it differs, a detector was changed.** That is legitimate only if a detector got
      *stricter*, and the commit that changed it must say which one and how it was
      measured. A changed fingerprint with no such commit message stops the flip.

**State as measured 2026-08-11: PASS.** 8 checks, 7 `PASS`, 1 `INFO`, 0 `FAIL`.
0 unresolved findings, 77 allowlisted, 92 disclosed.

**No red is being carried into this flip, so there is no accepted-red list to sign.** Had
there been one, it would be here, named finding by finding with the accepting party on each.

---

## 2 · `origin/master` and `HEAD` are the same commit, written out in full

```
git rev-parse HEAD
git rev-parse origin/master
git rev-list --left-right --count origin/master...HEAD
```

- [ ] **2.1** Both SHAs are written into this checklist **in full, by hand, at flip time**:

      HEAD          ________________________________________
      origin/master ________________________________________

- [ ] **2.2** They are identical, character for character.
- [ ] **2.3** `git rev-list --left-right --count origin/master...HEAD` prints `0` and `0`
      — nothing ahead, nothing behind.

**As measured 2026-08-11, before the remaining workers land:**

```
HEAD          ead0f7cf9b8dc471e91ff27d17f7d1c774395a3b
origin/master ead0f7cf9b8dc471e91ff27d17f7d1c774395a3b
behind=0 ahead=0
```

> **This will not be the flip-time SHA.** Nine workers were landing files into this tree
> when the checklist was written; `git status --porcelain` showed 97 uncommitted paths and
> the number moved twice while this page was being written. The
> audit must be **re-run after the final push, against the commit that will actually be
> published**, and item 2.1 filled in with that commit — not with `ead0f7c`. An audit of
> the working tree is not an audit of the remote.

---

## 3 · The working tree is clean

```
git status --porcelain
```

- [ ] **3.1** The output is **empty**. Not "only untracked files", not "only my own
      scratch" — empty.
- [ ] **3.2** `git stash list` is empty, so nothing intended for publication is parked.

**As measured 2026-08-11: NOT MET — 97 uncommitted paths, and still moving.** That is
expected and not alarming at the time of writing: the other nine workers had not finished,
and this worker's own five files are among the 97. It is listed here because it is the item
most likely to be waved through, and an uncommitted path at flip time is a file the judges
will never see. Do not copy the number from this page — run the command.

---

## 4 · The licence file and `LICENSES/` exist and are tracked

```
git ls-files --error-unmatch LICENSE
git ls-files LICENSES/ | head
python scripts/qa/check_reuse.py
```

- [ ] **4.1** `git ls-files --error-unmatch LICENSE` **succeeds** (exit 0). A `LICENSE` that
      exists on disk but is untracked publishes a repository with no licence file, which
      fails hackathon Stage One on a technicality. The previous audit caught exactly this.
- [ ] **4.2** `LICENSES/` is tracked and non-empty.
- [ ] **4.3** `check_reuse.py` measures `non_spdx_spelling.FSL-1.1-ALv2` at **1254 or
      lower**. It is a ratchet against a baseline of 1213 and is **expected to still be
      red** — see item 9.

**As measured 2026-08-11:** `LICENSE` (Apache-2.0) is tracked; `LICENSES/` exists;
`non_spdx_spelling.FSL-1.1-ALv2 = 1254`, unchanged by this worker.

---

## 5 · No credential is tracked

```
python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json
```

- [ ] **5.1** Rows `secrets_tracked` and `secrets_history` are both `PASS` with
      `unresolved: 0`.
- [ ] **5.2** Row `ignored_and_untracked` is `PASS`: `.env` and `*.tfstate*` are gitignored,
      untracked, **and were never added in any commit on any ref**. The history half is the
      load-bearing half.
- [ ] **5.3** Row `disclosure_register` is `PASS` with `0 stale`. Every non-gating grant is
      named, dated, classified and still covering a real finding.
- [ ] **5.4** Skim `docs/submission/DISCLOSURE-DECISIONS.yaml` end to end. **It is meant to
      be read, not trusted.** 59 entries in seven classes; the largest are 26
      `abs-path-layout`, 14 `history-already-pushed` and 6 `recorded-evidence-account-id`.
      Delete any entry you disagree with and re-run — the finding comes back red and the
      flip is blocked until it is settled again.

**As measured 2026-08-11: PASS**, 7,314 tracked paths and 901,810 added lines of history,
0 unresolved.

---

## 6 · The rotated `mainline_judge` password appears nowhere — run this one last

**This is the one item whose timing matters, and the one this worker could not complete.**
The password is shown once by `scripts/deploy/judge_access.py attest` and is not recoverable
afterwards, by design. Only the person holding it can run the exact-value check.

```
printf '%s' "$JUDGE_PASSWORD" | python scripts/submission/audit_public_readiness.py --assert-absent
echo $?
```

- [ ] **6.1** The output ends `ABSENT: YES - the value appears in no tracked file and in no
      added line`, and `$?` is `0`.
- [ ] **6.2** The run was done **after** the final rotation and **after** the final push, not
      before either.
- [ ] **6.3** The password was piped from stdin, never passed as an argument. The mode
      refuses to accept it any other way for exactly this reason: an argument vector is
      visible in `ps`, lands in shell history, and is captured by CI logs. Only a SHA-256
      prefix is printed.

**What this worker could measure without holding the credential, all after the rotation
landed:**

* `high_entropy_secret` and `bearer_or_jwt`: **0 unresolved findings** tree-wide.
* A shape sweep for `secrets.token_urlsafe(24)` output — 32 characters of `[A-Za-z0-9_-]`,
  **with no key-name context requirement**, so strictly wider than any detector family —
  found 31 candidates in the tracked tree and 33 in history, in exactly four files:
  `pnpm-lock.yaml` (22), `evidence/reference-ledger/bundle.json` (5),
  `console/tests/vectors/checkpoint.json` (3) and one reference-ledger `.NOT-SECRET` key.
  All four are pre-existing published material. **None is in `docs/deploy/`,
  `scripts/deploy/` or `qa/`.**
* `evidence/deploy/judge-run.json` `credential_hygiene`: `password_was_issued_this_run:
  true`, `bytes_scanned: 15633`, `matches: 0`, `holds: true`.

That is strong evidence and it is not the same thing as checking the value. **Item 6 is
still required.**

---

## 7 · The committer census is what the founder expects to publish

```
git log --all --format='%an <%ae>|%cn <%ce>' | sort | uniq -c
git rev-list --all --count ; git rev-list master --count ; git for-each-ref
```

> **This item was briefed as "19 commits, 1 identity, Shaugato Paroi
> <shaugato2003@gmail.com>". That is not what is there.** Measured 2026-08-11:

```
44 commits over 9 refs, 3 distinct identity strings
   Shaugato Paroi <shaugato2003@gmail.com>                              x38   (author + committer)
   dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>  x6    (author)
   GitHub <noreply@github.com>                                          x6    (committer)

master alone: 38 commits, 1 identity
2 identity strings are reachable ONLY from a non-master ref
```

- [ ] **7.1** The founder has seen the number **44**, not 19 and not 38, and understands it
      counts six Dependabot branches on `origin` that `git log master` cannot see.
- [ ] **7.2** The founder accepts that **`shaugato2003@gmail.com`, a real personal address,
      becomes permanently public on 38 commits.** No `users.noreply.github.com` alias is in
      use for the human author, and enabling GitHub's email-privacy setting afterwards does
      **not** retract commits already carrying the address.
- [ ] **7.3** The two extra identities are bot accounts (`dependabot[bot]`, `GitHub`) and
      disclose nothing a public repository would not already show.
- [ ] **7.4** *Optional, and cheapest today:* if the six Dependabot branches are not wanted
      in the published history, delete them on the remote **before** the flip. After it,
      they are archived regardless.

---

## 8 · The founder ratifies the disclosure decisions

Twenty-three register entries name the founder as ratifier at **this item**. They are not
valid until this box is ticked. Read `docs/submission/DISCLOSURE-DECISIONS.yaml` §1, §2 and
§6 before doing so.

- [ ] **8.1 The AWS account id `0229…8246` becomes permanently public.** It survives at HEAD
      in six documentation files as recorded evidence — quoted `aws sts get-caller-identity`
      output, a KMS transcript, the CloudFront `AccessDenied` refusal, a committed
      `terraform plan`. It is **not** a credential and grants nothing without a principal
      and a policy; the realistic cost is cross-account enumeration and more targeted
      phishing.
- [ ] **8.2 Option A is taken on the history finding, and Option B is refused.** The id is
      in commits `5ddaa3a` and `e518787`, both already on `origin/master`. It is accepted in
      writing rather than removed by `git filter-repo --replace-text` and a force-push,
      because rewriting shared history to hide a non-credential is a worse trade than
      disclosing it and would invalidate every commit SHA this repository's own evidence
      cites. **Today is the cheapest day this decision can be reversed. After the flip it
      cannot be reversed at all.**
- [ ] **8.3 The Windows account name `shaug` becomes permanently public**, in nine files
      (`abs-path-username` class, enumerated in PUBLIC-READINESS.md §1.6). It is a prefix of
      the already-public handle `Shaugato`,
      so the marginal disclosure is the local account name only.
- [ ] **8.4 The directory layout `D:\CoackroachDBxAWS\mainline` becomes permanently
      public**, in 35 files (`abs-path-layout` class).
- [ ] **8.5 The five `NOT-SECRET` private keys under `evidence/reference-ledger/keys/` and
      the worked test-vector key in `spec/wire/checkpoint.md` are published on purpose**, so
      a third party can re-sign the reference bundle and reproduce every value in it. They
      sign nothing outside it.

---

## 9 · What is red on purpose, and stays red

The flip does not require these to be green, and **turning any of them green to make the
flip look tidier would be the exact failure this repository exists to avoid.** They are
listed so nobody mistakes them for oversights at the last minute.

- [ ] **9.1** `submission` CI is red on
      `REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254`.
      Forty-one files spell the identifier without the `LicenseRef-` prefix. Repairing it is
      a repo-wide header sweep across every domain. **Confirm the measured value is still
      1254 or lower** and that nobody lowered the baseline to buy a green.
- [ ] **9.2** The MI ratchet sits at **28/30 invariants** and the custody chain at **7/16
      unimplemented**. Both are true incompleteness counters and stay red.
- [ ] **9.3** `demo-health` is red because no demo is deployed. It must go green on its own
      the moment one is, and not before.
- [ ] **9.4** No `continue-on-error` and no `|| true` was added anywhere to reach any of the
      above.

---

## 10 · The flip

Everything above is ticked. Nothing below is reversible.

- [ ] **10.1** Item 2 re-run against the **final** commit and both SHAs written into 2.1.
- [ ] **10.2** Item 1 re-run against that same commit, exit 0.
- [ ] **10.3** Item 6 run with the real password, exit 0.
- [ ] **10.4** Items 7 and 8 ratified by the founder, not by an agent.

**The exact command the orchestrator runs:**

```
gh repo edit Shaugato/mainline --visibility public --accept-visibility-change-consequences
```

Verify immediately afterwards:

```
gh repo view Shaugato/mainline --json visibility,url
# expect: {"visibility":"PUBLIC","url":"https://github.com/Shaugato/mainline"}
```

Then confirm from outside any authenticated session — a signed-out browser or
`curl -sI https://github.com/Shaugato/mainline` returning `200`, not `404`. GitHub returns
`404` rather than `403` for a private repository, so an authenticated check cannot tell the
two states apart and is not sufficient.

---

## Provenance of this checklist

Prepared by `w9-public-readiness`, 2026-08-11, from measurements taken on this machine
against the live remote. Files owned and written by this worker:

* `scripts/submission/audit_public_readiness.py`
* `docs/submission/DISCLOSURE-DECISIONS.yaml`
* `docs/submission/PUBLIC-READINESS.md`
* `qa/public-readiness.json`
* `docs/submission/PUBLIC-FLIP-CHECKLIST.md`

**This worker did not run the flip.** It did not run
`gh repo edit --visibility public`, it did not push, and it did not change the visibility of
`github.com/Shaugato/mainline` by any other means. The repository was `PRIVATE` when this
worker started and `PRIVATE` when it finished. The flip is the orchestrator's act, performed
with the founder, after every box above is ticked.
