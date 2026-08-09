<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# Upstream proposal issue — `verifying-a-restore-by-merkle-root`

**Target repository:** [`cockroachlabs/cockroachdb-skills`](https://github.com/cockroachlabs/cockroachdb-skills) (Apache-2.0)
**Route:** the repository's own issue form, `.github/ISSUE_TEMPLATE/new-skill.yml` — a
proposal issue first, then a pull request on an `add-skill/<domain>/<name>` branch, as
`CONTRIBUTING.md` describes. There is no CLA.
**Skill, ready to file:** [`skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/`](../../skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/)

Everything below the rule is the body to paste into the form, field by field. Nothing above
it is submitted.

---

## Domain

**Resilience and Disaster Recovery**

*(Chosen from the dropdown the issue form offers. Verified 2026-08-10: the option exists,
and `skills/cockroachdb-resilience-and-disaster-recovery/` contains only a `.gitkeep` — this
would be the first skill in it.)*

## Skill name

`verifying-a-restore-by-merkle-root`

## Description

Proves that a restored CockroachDB table reproduces a Merkle root committed before the
backup was taken, so a restore is verified rather than assumed. A `RESTORE` job that reports
success has established that bytes moved; it has not established that the rows you needed
are the rows you got. For an audit trail, an evidence table or any append-only record, the
failure that hurts is not a corrupt file — it is a table that is quietly shorter and reads
perfectly.

## Scope

**In scope.** Committing to a table's contents before a backup (root, height, head hash);
canonical row encoding so two runs on the same data produce identical bytes; domain-separated
Merkle construction; recomputing after `RESTORE` and requiring all three values to match;
locating the first divergent block; binding the verification to the backup it claims via
`SHOW BACKUP`.

**Out of scope.** Choosing a backup schedule or storage layout; incremental-backup strategy;
cluster-to-cluster replication; key management for signing the checkpoint; anything about
what the rows mean. The skill deliberately answers one question — *did the restored table
reproduce the value we committed to?*

## Expected inputs and outputs

**Inputs:** a table with a deterministic total order over its rows; a checkpoint JSON stored
outside the cluster; read access to the restored table.

**Outputs:** a pass/fail verdict on three separate bindings (root, row count, head hash), and
on failure the first divergent block with both hashes. Exit `0` verified, `1` not verified,
`2` the input was unusable — never `0` for the last two.

## Safety considerations

Four silent-degradation traps, each of which produces a green result on data that is wrong:

1. **A chain verified only forward misses truncation at the head.** Walking `prev_hash`
   links from the first row proves every surviving link is intact and says nothing about
   rows missing from the end. Every check passes; the table is short. This is why the skill
   binds the row count and the head hash separately, and why the bundled script's self-test
   demonstrates a forward walk *accepting* a truncated table that the root check refuses.
2. **A row-level TTL policy can garbage-collect a lineage the root commits to.** A table
   under TTL and also under a committed root will fail verification later for a reason
   nobody remembers configuring — and a restore carries the TTL storage parameters with it,
   re-arming the same deletion against the restored rows.
3. **Reading the expected root from the restored cluster is circular.** Anything that could
   rewrite the rows could rewrite the root. It must come from outside, over a path the
   cluster's own credentials cannot write.
4. **Duplicating the last node of an odd Merkle level** lets two different row sets produce
   the same root. The skill promotes the odd node instead, and says why.

It also notes that `AS OF SYSTEM TIME` cannot read past the zone's `gc.ttlseconds`, so
"read the old version" is not a substitute for having committed to the data at the time.

## Documentation references

Links only, no copied prose: `RESTORE`, `BACKUP`, `SHOW BACKUP`, Backup Validation,
`AS OF SYSTEM TIME`, Batch Delete Expired Data with Row-Level TTL, Configure Replication
Zones (`gc.ttlseconds`), and the Disaster Recovery Overview.

## Motivation

Restore drills are common; *verified* restore drills are rare, because the verification step
usually reduces to "the job succeeded and the row count looks right". Teams that keep an
audit trail, an evidence ledger or a compliance record need a stronger statement, and the
pieces are all standard — a hash, an ordering, and somewhere outside the cluster to keep one
value. What is missing is a single-task procedure that names the traps, because every one of
the four above yields a passing check on data that is wrong.

The skill is single-task, script-bearing and de-branded: the bundled
`verify_restore_merkle_root.py` uses only the Python standard library, needs no cluster for
its self-test, and demonstrates each failure mode rather than asserting it in prose.

---

## Notes for us, not for the issue

**The sentence is: "these two PRs have had no maintainer engagement."** Never characterise
the repository itself as stalled, dead, abandoned or unmaintained — it is none of those. PR
#18 merged 2026-07-22, and earlier external PRs merged in minutes to days. Two community
skill proposals (#15, #17) have simply had no comments for weeks. The permitted sentence is
a fact about two pull requests; the forbidden one is a claim about a team, and it would be
both wrong and rude. The CI grep in `.github/workflows/skills.yml` enforces the difference.

**Claim the filing, never the merge.** Anywhere this contribution is mentioned — README,
deck, video, submission — the claim is that we *filed* it. Upstream acceptance is not on any
critical path and is not ours to promise. `.github/workflows/skills.yml` greps our own
documentation for merge claims and fails the build on one.

**Do not file a vector-index or agent-memory skill.** PR #17 already proposes
`designing-agent-memory-schemas` covering prefix-filtered vector index design; filing over a
pending proposal reads as a landgrab and gets closed. Our claim is tamper-evident ledgers
and refusal gates — a different and less crowded noun. `designing-vector-recall-prefixes`
stays in our own tree under our own brand.

**Re-check before filing.** The empty-domain claim is the reason for the target and it is
perishable: re-enumerate `skills/cockroachdb-resilience-and-disaster-recovery/` at `main`
immediately before opening the issue, and re-confirm the domain is still in the dropdown.
