<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CRITIQUE PLAN — field notes for CockroachDB

**Lead:** cockroachdb-findings. **Date:** 2026-08-17. **Workers:** 5, disjoint paths.
**Deliverable:** a document CockroachDB would be glad to receive — seven measured findings,
three things that worked notably well, and an honest count of what we struck.

---

## 0. WHAT THIS IS, IN ONE PARAGRAPH A NON-TECHNICAL READER CAN USE

We built a real system on CockroachDB over several weeks. Along the way we hit sharp edges —
places where the database behaved differently from what its documentation or our expectations
led us to believe, and where the difference cost us hours. This document set writes those down
the way a colleague writes them down: what we expected, what actually happened, the smallest
program that shows it, the exact version and hosting tier it was measured on, why it cost us
time, and what a better version would look like. It also writes down what worked so well that
the product could not exist without it, because a critique with no praise is a grievance rather
than an assessment. Where our own misreading caused the problem, we say so in the finding
itself, not in a footnote.

---

## 1. THE STATE OF THE EVIDENCE BEFORE THIS WAVE

The material already exists and is largely correct. It is scattered across documents written
for a different purpose and is unreadable as a critique. **Read it before rewriting it.**

| Finding | Existing evidence already in the tree |
|---|---|
| `has_function_privilege` stub | `docs/regression/GUARD.md:368-393` (§*Two things this guard found on its first run*); `docs/submission/JUDGING-AXES.md:219-227`; `docs/submission/extra-credit-plan.md:212-218`, `:367-369`; **and the counter-reading at `docs/demo/cr-gate-measurements.md:56-69`** |
| `SHOW GRANTS` signature mismatch | `docs/regression/GUARD.md:238`, `:250-251`, `:383-386` |
| vector index not chosen by optimizer | `docs/adr/0002-g1-platform-ground-truth.md:18-19`, `:36`; `docs/leads/agents-mcp.md:148-150`; `docs/leads/algorithms.md:252-254`; `docs/HONESTY.md:1178`; `evidence/aws/ann/explain-unhinted.txt`, `evidence/aws/ann/explain-hinted.txt`, `evidence/aws/ann/ann-proof.json` |
| `crdb_internal` / `system` restricted | `docs/diagnosis/divergence-05-schema-expectations.md:342`; `docs/submission/census/crdb-four-tools.md:198`; `docs/demo/film/VO-CLOSE.md:1249` (`InsufficientPrivilege`, hint against `allow_unsafe_internals`) |
| 20,000 schema-object cap | `docs/submission/PRESHOOT-VERDICT.md:289`; `docs/submission/EXTRA-CREDIT-CLAIMS.md:362-367`; `docs/demo/film/CLAIMS-CLEARANCE.md:2152`, `:2213` |
| `convert_from()` untyped `<string>` | `verticals/mainline/db/seeds/demo/demo_world.sql:844-846` |
| `gc.ttlseconds` 4500 | `docs/adr/0002-g1-platform-ground-truth.md:22`, `:52`; `docs/deploy/cloud-database.md:41`, `:173`; **and the contradicting line at `docs/deploy/CLOUD-40001.md:75`** |

Two of those rows carry a **counter-reading in our own tree**. Those two are the ones most
likely to be an overclaim, and §3 rules on both.

Local node re-probed by this lead at plan time and reachable:
`CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00)` over
`postgresql://root@localhost:26257/defaultdb?sslmode=disable`.

---

## 2. WHERE IT GOES

`docs/upstream/` exists and is **empty**. It becomes the home, so no worker in this wave
collides with any other lead's wave.

```
docs/upstream/COCKROACHDB-FIELD-NOTES.md    layer 1 + layer 2, the front door        W5
docs/upstream/WHAT-WORKED.md                three things that carried the product    W4
docs/upstream/STRIKE-LEDGER.md              what we could not reproduce, and why     W5
docs/upstream/LINK-BLOCK.md                 paste-ready block for the docs lead      W5
docs/upstream/findings/F01..F07             layer 3, one file per finding            W1-W4
scripts/upstream/repro_*.py                 the minimal reproductions                W1-W4
scripts/upstream/verify_field_notes.py      independent re-run of every repro        W5
evidence/upstream/*.json                    transcripts, stamped and dated           W1-W5
```

---

## 3. RULINGS — the brief left these open; they are now closed

**R1 — Home.** `docs/upstream/`. Main document `docs/upstream/COCKROACHDB-FIELD-NOTES.md`.

**R2 — No file outside three trees.** `docs/upstream/`, `scripts/upstream/`, `evidence/upstream/`.
**No worker touches `README.md`, `docs/submission/DEVPOST.md`, `docs/submission/JUDGE-START.md`,
`docs/TOOL-USAGE.md`, or any product code, test, or migration.** Other leads are rewriting the
judge-facing documents in this same wave; we hand them `docs/upstream/LINK-BLOCK.md` to paste
rather than editing their files under them.

**R3 — Reproduction standard. Every finding carries exactly one label:**

- **`REPRODUCED-TODAY`** — re-run 2026-08-17 against the local single-node `v26.2.5`, with the
  transcript written to `evidence/upstream/`.
- **`ARCHIVED-EVIDENCE`** — measured on CockroachDB Cloud Basic on a stated earlier date and
  **not re-run today**, because re-running would mutate or cost against a shared live cluster.
  Cites the artefact path and its timestamp. The finding says plainly that it was not re-run.
- **`STRUCK`** — could not be demonstrated. It **does not appear in the findings body at all**;
  it appears only in `STRIKE-LEDGER.md`, with what we tried and what we saw instead.

A finding with none of these three labels does not ship. **Publishing an unreproduced finding is
the single worst outcome available to this wave** — it converts a credible critique into a
demonstration that we do not check ourselves.

**R4 — Nothing live is mutated.** No `terraform apply`, no AWS call, no SSM write, no credential
printed. No `REVOKE`, `GRANT`, `CONFIGURE ZONE`, `DROP` or DDL against **any** CockroachDB Cloud
cluster or against the shared `mainline_demo` database. Local reproductions create a scratch
database named `upstream_f<NN>_<8 hex chars>` and **drop it in a `finally:` block**. Our own F05
finding exists because scratch databases from earlier waves were never dropped; reproducing it by
leaving more behind would be self-refuting. Each repro script prints the database it created and
the database it dropped.

**R5 — The two overclaim risks, ruled explicitly. Do not inherit these; re-derive them.**

- **F01 `has_function_privilege`.** `docs/demo/cr-gate-measurements.md:67-69` reads one `true`
  as *"CockroachDB's platform default for `PUBLIC` on a routine"* — which would make it correct
  behaviour and our reading the error. The stub claim survives **only** if, on a fresh scratch
  database, after an explicit `REVOKE EXECUTE … FROM public` (and from the probe role), with the
  behavioural truth being a hard `42501 … does not have EXECUTE privilege on procedure …`, the
  function still answers `true`. If it answers `false` in that state, **the finding is struck**
  and the strike is reported as a number. `has_table_privilege` goes through the byte-identical
  control as the negative control; the finding's force comes from one tracking behaviour and the
  other not.
- **F06 `gc.ttlseconds`.** `docs/deploy/cloud-database.md:41` records *"requested 4500, accepted,
  read back as 4500"* and `docs/deploy/CLOUD-40001.md:75` records `14400` as the default with
  `4500` as our pin. If `4500` is **our** `CONFIGURE ZONE` value and not Basic's default, then
  *"defaults to 4500 on Basic"* is **false**. Restate it as what was measured, or strike it. Do
  not publish "defaults to" without a read of a Basic database nobody configured.

**R6 — Every finding names where we were wrong.** A mandatory `Where we were wrong` line, even
when it reads *"nothing — the platform behaviour is the whole finding."* **F02 is explicitly
ours:** comparing `SHOW GRANTS` output against `information_schema.routines` without normalising
the spelling is our bug. The finding is not "`SHOW GRANTS` is broken"; it is "the two catalogue
surfaces spell the same routine two ways and ship no normaliser between them, and a naive
comparison — ours — produces false positives." Admitting that is what makes F01 and F03 credible.

**R7 — Register.** A colleague reporting from the field. We chose this database, we built
something real on it, these are the edges we hit. **Every finding ends with "What better would
look like"** — one concrete, implementable change, not a wish. No severity ratings, no CVE
theatre, no "CockroachDB should". Prefer *"a one-line note in the `has_function_privilege` page
saying it is not signature-aware would have saved us the afternoon."*

**R8 — Praise is not decoration and is not last.** `WHAT-WORKED.md` is linked from layer 1 of the
front door, **above** the findings list. Its three entries carry the same evidence standard as
the criticisms: trigger and `CHECK` machinery carried the entire product thesis; `SERIALIZABLE`
being the default made the gate straightforward rather than a project; the SQLSTATEs are precise
enough that we put them on screen in a demo as exhibits.

**R9 — Layering is per-file, not just per-repo.** Every finding file opens with **"What happened"
in two sentences of plain language** — no jargon, no SQLSTATE, no function name if avoidable —
then the mechanism, then the transcript. **A reader who stops after two sentences must still be
correct.** Concrete before abstract, in every one of them.

**R10 — No term before its gloss.** Each of these gets a plain-language gloss at first use in
every file it appears in, or does not appear: `SQLSTATE`, `routine`, `ACL`, `catalogue`,
`optimizer plan`, `ANN`, `prefix-constrained`, `zone configuration`, `GC TTL`, `SERIALIZABLE`,
`trigger`, `CHECK constraint`, `scratch database`, `tier`.

**R11 — No regression, no commit.** Baseline 1070 / 1069 / 0 / 0 stands untouched; the gate proof
stays `PROVEN`; `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move. Nobody runs the product
suite, nobody edits product code. **Leave the tree for the orchestrator; do not commit.**

**R12 — Version and tier on every finding.** `v26.2.5` plus the build string, and which exam it
was measured on: `local single-node CCL` or `Cloud Basic, aws-ap-southeast-1`. **These are two
different exams.** A finding measured on one is not claimed for the other.

**R13 — The strike count is published.** W5 states the integer in `STRIKE-LEDGER.md` and in the
front door, whatever it is. A wave that strikes zero findings did not check.

---

## 4. WORKERS — five, disjoint, literally enumerated

**Order:** W1, W2, W3, W4 run in parallel. **W5 runs after all four.**

### W1 — Privileges: the stub, and our own naive comparison
Owns `docs/upstream/findings/F01-has-function-privilege.md`,
`docs/upstream/findings/F02-show-grants-signature.md`,
`scripts/upstream/repro_privileges.py`,
`evidence/upstream/F01-has-function-privilege.json`,
`evidence/upstream/F02-show-grants-signature.json`.
Carries R5's first half. Most likely worker to return a strike, and that is a success condition.

### W2 — The optimizer and the closed catalogue
Owns `docs/upstream/findings/F03-vector-index-not-chosen.md`,
`docs/upstream/findings/F04-crdb-internal-restricted.md`,
`scripts/upstream/repro_vector_and_catalogue.py`,
`evidence/upstream/F03-vector-index-not-chosen.json`,
`evidence/upstream/F04-crdb-internal-restricted.json`.
F03 is `ARCHIVED-EVIDENCE` for the Cloud arm and `REPRODUCED-TODAY` for whatever the local node
will show; the two are labelled separately, never merged.

### W3 — Limits that surface as something else
Owns `docs/upstream/findings/F05-schema-object-cap.md`,
`docs/upstream/findings/F06-gc-ttlseconds.md`,
`scripts/upstream/repro_limits.py`,
`evidence/upstream/F05-schema-object-cap.json`,
`evidence/upstream/F06-gc-ttlseconds.json`.
Carries R5's second half. F05 is the finding we caused ourselves and must own.

### W4 — SQL semantics, and the three things that worked
Owns `docs/upstream/findings/F07-convert-from-untyped.md`,
`docs/upstream/WHAT-WORKED.md`,
`scripts/upstream/repro_semantics_and_praise.py`,
`evidence/upstream/F07-convert-from-untyped.json`,
`evidence/upstream/WHAT-WORKED.json`.
Both halves are live SQL against the local node, which is why they are one worker.

### W5 — The front door, the strike ledger, and independent re-verification
Owns `docs/upstream/COCKROACHDB-FIELD-NOTES.md`, `docs/upstream/STRIKE-LEDGER.md`,
`docs/upstream/LINK-BLOCK.md`, `scripts/upstream/verify_field_notes.py`,
`evidence/upstream/verification.json`.
**Re-runs every repro script W1-W4 wrote, from a cold shell, and demotes any finding whose script
does not reproduce its claim.** W5 writes no finding file and edits none.

---

## 5. HOW WE WILL KNOW THIS FAILED

- A finding ships that a reader cannot reproduce from the file. **Worst outcome.**
- A finding is softened until it is no longer true, in the name of readability. R9 says write two
  sentences instead of one; it never says write a vaguer one.
- The document reads as blame. We chose this database and it carried a real product; the tone is
  a colleague's, and `WHAT-WORKED.md` above the fold is the structural guarantee of that.
- A worker edits a file another lead is rewriting this hour. R2 exists for exactly this.
