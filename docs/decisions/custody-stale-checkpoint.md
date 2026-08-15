<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Two of custody's four red checks are one superseded row, and it is fixed at the row

**Decision.** The `tree_size = 1` checkpoint in `mainline.ledger_checkpoint` — whose
`root_hash` is the SHA-256 of a string naming itself and commits to nothing — is **deleted**,
together with its cosignature, by `scripts/deploy/reconcile_demo_checkpoints.sql`. Custody
checks **2 (`inclusion_proof`)** and **3 (`consistency_proof_every_pair`)** turn green as a
consequence. **No check is weakened, skipped or exempted; no signature is forged; no row is
invented.** Checks **4 (`log_signature`)** and **10 (`canonicaliser_identity`)** are *not*
fixed here — they are attributed below, and what is true about them is stated rather than
repaired.

**Status:** decided and proved locally; **not applied to AWS**. The orchestrator applies.
**Owner:** W6 (demo-story wave). **Authority:** ruling **R5** of
`docs/leads/demo-story-plan.md` — *"Custody's red is real, is named, and is fixed at the row
— never at the check."* **Date:** 2026-08-15.
**Measured against:** `w_w6`, a private database on the local cluster (CockroachDB v26.2.5),
restored byte-for-byte from the local `mainline_demo` and then given the defect back.

---

## 1 · What the custody screen actually reports, and which checks are which

Measured by running the console's **own** verifier — `src/verify/ledger.ts`'s `verifyLedger`,
the code that runs in a judge's browser — over the payload the demo API's **own** reader
(`mainline_demo_api.reads.read_ledger`, the function behind `GET /v1/ledger`) emitted from
`w_w6` with the superseded row present. Four checks fail. Verbatim:

| check | status | the verifier's own first line |
|---|---|---|
| 2 `inclusion_proof` | **FAIL** | `seq 0 → size 1: the path reconstructs 032980be3a0d1fb7a62074e18f06b66ae45bb837151ab4bda2ad89948db7bdb2, which is not the root 74f0845f11c5992bb6e69ba250d899975fc73d551b1eeab96a8502eaca508c8f.` |
| 3 `consistency_proof_every_pair` | **FAIL** | `1→2: the proof reconstructs 08141776d25480ec2010a63d4e9f41d56e595d01e7abb613ce057f91706a71e6 for size 2, which is not the recorded root bf5dc3e5b2458a8e578db9841c969027bbb37430f13fcb81124a13777b50d091.` |
| 4 `log_signature` | **FAIL** | `a checkpoint note will not parse: the note has no empty line, so it has no signature section (spec §2) — and read as note text on its own it does not parse either: the root line decodes to 48 bytes; spec §3 requires exactly 32 bytes.` |
| 10 `canonicaliser_identity` | **FAIL** | `the checkpoint at tree_size 1 carries a note that will not parse, so the code that produced its leaves is not named in bytes anyone can read.` (and the same line for 2 and for 4) |

Everything else passes or skips honestly: 1 `leaf_hash_recomputation` PASS, 9
`link_chain_and_density` PASS, 13 `no_sandbox_leaf` PASS, 7 `witness_quorum` PASS,
0 `payload_vs_canon_bytes` PASS, and six SKIPs that name what they could not reach.

**That tally is `5 passed / 4 failed / 6 not run` — the same three numbers the lead measured
on the live URL** (`docs/leads/demo-story-plan.md` §0.4(ii)), and the same four check ids. The
reproduction is local, and no claim here is a claim about AWS; but a local database that
answers with the deployed database's exact tally is the strongest available evidence that what
is attributed below is what a judge is looking at.

**Two of the four are one row. The other two are one note.** That split is the whole finding,
and it is the reason this document exists rather than a commit message.

## 2 · The row: a checkpoint that commits to nothing

`GET /v1/ledger` served three checkpoints. Two of them are real:

| tree_size | recorded `root_hash` | is it a node in `mainline.ledger_node`? |
|---|---|---|
| 1 | `74f0845f11c5992bb6e69ba250d899975fc73d551b1eeab96a8502eaca508c8f` | **no** |
| 2 | `bf5dc3e5b2458a8e578db9841c969027bbb37430f13fcb81124a13777b50d091` | yes — node (1,0) |
| 4 | `49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983` | yes — node (2,0) |

`74f0845f…` is `digest('mainline-demo/ledger/root/1', 'sha256')` — the SHA-256 of a string
that names itself. The RFC 6962 Merkle Tree Hash of the first leaf the product's own appender
actually wrote is `032980be3a0d1fb7a62074e18f06b66ae45bb837151ab4bda2ad89948db7bdb2`, and for
a tree of size 1 the MTH **is** the leaf hash, so the inclusion proof for `seq 0` against
`tree_size 1` is the empty path and the recomputation admits no ambiguity at all. The `1 → 2`
consistency proof is anchored on the same fiction and disagrees for the same reason.

Recomputed against every checkpoint, by `scripts/deploy/verify_demo_checkpoints.py`:

```
tree_size 1: MTH 032980be3a0d1fb7a62074e18f06b66ae45bb837151ab4bda2ad89948db7bdb2 != recorded 74f0845f11c5992bb6e69ba250d899975fc73d551b1eeab96a8502eaca508c8f
tree_size 2: MTH bf5dc3e5b2458a8e578db9841c969027bbb37430f13fcb81124a13777b50d091 == recorded bf5dc3e5b2458a8e578db9841c969027bbb37430f13fcb81124a13777b50d091
tree_size 4: MTH 49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983 == recorded 49b22526023f4932c8dbd8cd2df1bc22e612cf8ddf40768d84b9e07d09498983
```

**Every size-2 and size-4 path agrees.** The verifier is not wrong about anything. It is
working perfectly on a row that should not be there — which is the outcome a verifier is
supposed to produce, and the reason the fix is at the row.

### 2.1 Why the row is still there

`verticals/mainline/db/seeds/demo/demo_world.sql` §8 seeded exactly that checkpoint until
2026-08-14, over a `mainline.ledger_leaf` that held **zero rows**; the file says so in its own
words at line 392. It now seeds `tree_size` 2 and 4 and reads both roots back out of
`mainline.ledger_node`.

But every insert in §8 is guarded by `ON CONFLICT DO NOTHING` / `WHERE NOT EXISTS`, and
nothing in the chain has ever deleted anything. **Removing the statement removed the row from
every database seeded from scratch afterwards and from no database that already held it.**
`git show 8e6a195:…/demo_world.sql` is where the two superseded statements are read from;
`scripts/deploy/verify_demo_checkpoints.py::REPRODUCE_SQL` carries them verbatim so the defect
is reproduced rather than imagined.

This is a *class* of defect, not one row: **an idempotent seed cannot retire anything.** The
second instance of it is §7 below.

## 3 · The remedy, as a predicate

`scripts/deploy/reconcile_demo_checkpoints.sql`, two statements, no `BEGIN`/`COMMIT` (it is
applied as one batch on `cloud_chain.Applier`'s autocommit connection, exactly like the seed
files, so CockroachDB can restart it server-side on `40001`). The cosignature goes first
because `mainline.cosignature` has `FOREIGN KEY (site_code, tree_size) REFERENCES
mainline.ledger_checkpoint` (migration 0076) and deleting under a live cosignature is `23503`.

Three conjuncts, each load-bearing:

1. `root_hash = digest('mainline-demo/ledger/root/' || tree_size, 'sha256')` — **the signature
   of the defect.** A root that is the hash of its own name.
2. `NOT EXISTS (a row of mainline.ledger_node carrying that hash)` — **the clause that makes it
   safe to run for ever.** A checkpoint whose root is a node the appender built is a checkpoint
   over real leaves, and no such row can match, whatever it is numbered.
3. `EXISTS (a surviving admissible, cosigned checkpoint at the same site whose tree_size is at
   least this one's)` — **the clause that protects every anchor the deleted row could have
   satisfied.** `mainline.fn_recall_policy_anchored` (migration 0112) asks for precisely that
   predicate; this statement refuses to remove the row answering it unless another row answers
   it at least as well.

There is no `tree_size = 1` literal, no blanket `DELETE`, and no `WHERE` that widens if the
demo grows a fifth leaf. On a database that never carried the defect both statements delete
zero rows.

## 4 · The proof, and why a `DELETE` needed one

`scripts/deploy/verify_demo_checkpoints.py` runs the reconciliation between two full
measurements of the same database and exits non-zero unless seven claims hold. The measured
run, on `w_w6`:

```
[HELD] A · before, checks 2 and 3 both FAIL
[HELD] B · after, checks 2 and 3 both PASS
[HELD] C · every surviving checkpoint, leaf and node is unchanged
[HELD] D · exactly two tables changed, each losing exactly one row, none modified
[HELD] E · the row that left is the one the predicate describes
[HELD] F · every recall policy is still anchored inside a cosigned checkpoint
[HELD] G · a second application changes nothing at all

VERDICT RECONCILED — 7/7 claims held.
```

What each one is worth:

* **A is the discriminating half.** A proof that starts from green proves nothing, so the
  script reproduces the defect first (`--reproduce`) using the pre-2026-08-14 statements
  themselves. It is refused on `mainline_demo`, `defaultdb`, `postgres` and `system`: a
  database other lanes read is not a place to insert a row known to be false, even locally.
* **D is "nothing else changed" made checkable.** Every base table in `mainline`,
  `mainline_audit`, `mainline_meas`, `mainline_ops`, `mainline_qa` and `trappoint` — **89 of
  them** here — is measured as a row count **and** an order-independent content digest, `md5`
  over the sorted per-row `md5(row::STRING)`, so an `UPDATE` that preserved a count could not
  hide. `trappoint` is censused precisely because the reconciliation has no business there: a
  census that only watched the tables one expects to move cannot be surprised. Measured:
  exactly `mainline.ledger_checkpoint −1` and `mainline.cosignature −1`, and every surviving
  row of both byte-identical to one that was there before.
* **E names the row that left**: `tree_size 1 root 74f0845f… (root_is_its_own_name=True,
  root_is_a_node=False); kept [2, 4]`.
* **F re-asks migration 0112's own predicate**: `demo-recall-1.0 anchored at 1 → 2 admissible
  cosigned checkpoint(s) at or above`. The anchor survives on the rows that commit to leaves.
* **G asserts idempotence by running it**, not by reading the `WHERE` clause.

The RFC 6962 arithmetic in that script is `trappoint_ledger.merkle` — the repository's own
tree, the one the sequencer appends with. It is **not** the console's TypeScript verifier;
that one runs in the reader's browser and its verdicts are what the custody screen prints.
Both were run over the same bytes here, and both say the same thing, which is the useful kind
of redundancy: two implementations of one RFC, and a disagreement between them would itself
have been a finding.

**This was proved on a local cluster and applied to nothing else.** The script refuses any DSN
whose host is not `localhost` / `127.0.0.1` / `::1`, and there is no flag that overrides it.

## 5 · Check 10 `canonicaliser_identity`, attributed

The lead did not decompose this one. Measured, in three states:

| state of the payload | check 10 |
|---|---|
| with the `tree_size = 1` row, notes carrying a **hex** root line | **FAIL** — *"the checkpoint at tree_size 1 / 2 / 4 carries a note that will not parse"* |
| after reconciliation, notes still **hex** | **FAIL** — the same sentence, for `tree_size` 2 and 4 |
| after reconciliation, notes carrying a **base64** root line | **SKIP** — *"the checkpoint(s) at tree_size 2, 4 carry no `canon:` extension line … and this console pins none either. There are two silences here and no comparison between them"* |

So: **check 10 is not caused by the stale checkpoint, and the reconciliation does not move
it.** Its cause is the note text. While a note will not parse, `src/verify/ledger.ts` cannot
read an extension line out of it and records a finding; once a note parses, the absence of a
`canon:` line with no console-side pin to compare it against is a **SKIP**, and
`spec/wire/checkpoint.md` §4 makes that correct — the `canon:` line is an extension, and a
checkpoint that omits an extension has broken no rule. Turning that SKIP into a comparison
needs two things nobody should fake: checkpoints published with a `canon:` line, and
`VITE_MAINLINE_CANON_SHA256` set from `spec/custody/canon-registry.yaml`.

## 6 · Check 4 `log_signature` — what is true, and one correction to the brief

The brief says check 4 *"fails because the seeded note has no signature section"*. **Measured,
that is half of it, and the half that is not the failure.** The console's verifier treats an
unsigned-but-well-formed note as a **SKIP**, not a FAIL — deliberately, and it says why:

> *"this checkpoint carries no signature at all. Its note text parses … Nothing here has been
> verified and nothing has been accused: a checkpoint nobody could check is not a checkpoint
> that failed."*

What makes it **FAIL** is that the note does not parse at all: line 3 of a C2SP tlog
checkpoint is *base64* of the 32-byte root (`spec/wire/checkpoint.md` §3), and the seed wrote
the **hex** spelling, which is 64 characters that also happen to be legal base64 and decode to
**48 bytes**. The parser refuses on the length before any signature question is reached.

Both facts are true and both are stated. The one that belongs in `DEMO-HONESTY.md` §3 STAGED
is the first, because it is a property of a synthetic corpus rather than a defect:

> **The demo's checkpoints carry no signature.** `demo_world.sql` §8 writes `log_sig`,
> `tsa_token` and `beacon` as synthetic values and marks them so, and the checkpoint note it
> writes is origin / size / root with no signature section after it. So the custody screen's
> check 4 `log_signature` reports **NOT CHECKED**, with the verifier's own sentence: *a
> checkpoint nobody could check is not a checkpoint that failed.* A real checkpoint's value is
> that it left the trust boundary before we could change our minds about the tree; these did
> not. **Nothing here is signed and nothing here claims to be.** No signature is manufactured
> to close this check, and `VITE_MAINLINE_LOG_VKEY` ships empty for the same reason: a key we
> issued to ourselves, verifying a signature we wrote, is arithmetic and not evidence.

`verticals/mainline/demo/DEMO-HONESTY.md` is owned by nobody in this wave's §7 table, so this
worker did not edit it. **The bullet above is the routing**, and placing it in §3 is the
orchestrator's to schedule.

## 7 · The second instance of the same class, named and not fixed here

`demo_world.sql` §8.5 was corrected on 2026-08-15 to write the note's root line in base64. That
correction has **exactly the reach the deleted checkpoint's did**: the insert is guarded by
`NOT EXISTS`, there is no `UPDATE` anywhere in §8, and no database that already holds a
checkpoint will ever receive the new spelling. Measured on `w_w6`, whose checkpoints were
seeded before the change:

```
note  tree_size 2: signature_section=False root_line_decodes_to=48B canon_extension=False
note  tree_size 4: signature_section=False root_line_decodes_to=48B canon_extension=False
```

`48B` is the hex spelling. With it, checks 4 and 10 are **FAIL**; with the base64 spelling and
nothing else changed, they are **SKIP** and the custody report goes from `fail` to `bounded`
with zero failures.

**This document does not fix it, and `reconcile_demo_checkpoints.sql` does not touch it.** The
reason is scope discipline rather than doubt: this worker's remedy is bounded to rows the
current seed does not produce, and its proof asserts that nothing else in the database moved.
A note repair is an `UPDATE` of `body` on rows the seed *does* produce, re-encoding the row's
own `root_hash` — no new value, no typed digest — and it belongs with whoever owns
`demo_world.sql`. **Whether the deployed `mainline_demo` carries the hex spelling or the
base64 one was not measured by this worker**; it depends on when that database was last seeded
from scratch, and the honest inference — from the lead's live quotation of check 4's message,
which is the message the parser emits for a note it refused — is that it carries hex. That is
an inference, and it is labelled as one.

## 8 · What this decision does not do

* **It does not touch AWS.** Nothing was deployed, no Lambda was updated, no SSM parameter was
  written, no DSN or credential was printed. The reconciliation is applied to the deployed
  database by the orchestrator.
* **It does not weaken a check.** R5 is absolute: no verifier check is weakened, skipped or
  exempted. Checks 4 and 10 stay exactly as red as the bytes make them.
* **It does not forge a signature**, and it does not edit a seed to agree with a constant. The
  only statement it adds is a `DELETE` narrowed by a predicate over the defect.
* **It does not repair the checkpoint note** — §7 says so, says who it belongs to, and says
  what the repair would be.

## 9 · How to check this document is not lying

```
# your own database, restored or seeded; never mainline_demo
.venv/Scripts/python.exe scripts/deploy/verify_demo_checkpoints.py \
    --dsn 'postgresql://root@localhost:26257/<yours>?sslmode=disable' \
    --reproduce --apply --json evidence/custody/reconcile-<utc>.json
```

Exit `0` and `VERDICT RECONCILED — 7/7 claims held.` is the whole claim.

**A verifier that has never failed has never discriminated**, so this one was run against
broken reconciliations before it was trusted. Three demonstrations, each measured on `w_w6`,
each with the scratch mutant thrown away afterwards:

| what was broken | what happened | exit |
|---|---|---|
| **the predicate widened to the site alone** — `DELETE … WHERE site_code = …`, both statements | the demo API's own reader refuses the site: `no mainline.ledger_checkpoint rows for site_code 'dec0de00-0001-…'`. That is the 404 the founder met on the custody screen, arriving as a stated refusal. | **1** |
| **the two statements in the wrong order** — checkpoint before cosignature | the database refuses: `SQLSTATE 23503 … violates foreign key constraint "fk_cp" on table "cosignature" … Key (site_code, tree_size)=('dec0de00-0001-…', 1) is still referenced`. | **1** |
| **conjunct 3 given something to protect** — checkpoints 2 and 4 removed first, so the self-naming row is the site's ONLY checkpoint and deleting it would leave migration 0112's predicate unsatisfiable | the real reconciliation deletes **nothing**: `checkpoints before/after 1 → 1`, the row is still there, and `demo-recall-1.0 anchored at 1` still finds `1` admissible cosigned checkpoint at or above. The clause is not decoration. | — |

Conjunct 2 (`NOT EXISTS` a node carrying that root) is **not** discriminated by this data, and
saying so is more useful than a demonstration that proves nothing: no row in this seed can
have a root that is both the hash of its own name and a node the appender built, because those
are different values by construction. It is a clause about databases this one is not, and it
is what stops the predicate widening if the demo ever grows a fifth leaf.
