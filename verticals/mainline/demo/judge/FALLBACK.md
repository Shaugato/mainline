<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# If the key cannot be published — what Tier 3 degrades to, decided in advance

Tier 3 rests on one thing we do not control: whether publishing a scoped service-account key
to anonymous verifiers is within Cockroach Labs' terms for the Managed MCP Server. That is
day-1 check **GT-17**, and it is the kind of question that is answered late and answered
once.

So the degrade path is written down now, before the answer is known, and the pack runs the
same either way. A fallback improvised on the day is a fallback that quietly drops a claim;
a fallback written on D-14 is a claim stated at its true strength.

## The rule that does not change under any branch

**No key is ever published on the demo cluster.** Not a weaker one; none. The Managed MCP
write surface is insert-only and bound to `mainline_meas.external_attestation`, but
insert-only is still real, and a real write surface on the cluster the film was shot against
is not something a published credential should reach.

Everything below concerns `mainline-verify` — a separate throwaway cluster, restored from the
demo cluster, holding synthetic data only: a fictional operator, fictional people, fictional
incidents. The key is revoked when judging closes.

## Branch A — the key can be published

The pack runs as written. A judge adds the endpoint to their own MCP client and asks the
questions in [`PACK.md`](PACK.md). None of our code sits between the prompt and the row.

```bash
python verticals/mainline/demo/judge/cli.py run --via mcp
```

## Branch B — the key cannot be published

Three substitutes, in the order they should be believed. **None of them is presented as
equal to Branch A**, and the difference is stated rather than absorbed.

### B1 · The same statements, on the judge's own cluster (unchanged strength)

Every positive question in the pack runs over pgwire against a local single-node
CockroachDB the judge started themselves, seeded from the committed fixtures:

```bash
just corpus:up && just corpus:seed
export TRAPPOINT_DSN=postgresql://root@localhost:26257/mainline?sslmode=disable
python verticals/mainline/demo/judge/cli.py run --via sql
```

This checks everything about the **questions** that Branch A checks: that each parses, that
every column exists, that the plan really shows a vector search on a named index with a
non-empty prefix span, and that the result fits the budget. It is in one respect *stronger*
than Branch A, because the judge controls the cluster and the data is theirs to inspect.

What it does not carry is the sentence Branch A carries: *asked over CockroachDB's own
public managed endpoint, with none of our code in the path.* That sentence is about the
transport, and no local run can supply it.

### B2 · The negatives do not survive this branch, and we say so

The four negatives are marked `mcp_only` in the pack and the runner **skips** them here,
with the reason printed:

> over a pgwire connection as cluster admin this statement SUCCEEDS. Running it here and
> reporting a pass would invert its meaning.

`crdb_internal` is unreachable *over the Managed MCP surface*. It is perfectly reachable
over SQL, and the bypass beat of the film exists precisely to show what a cluster
administrator can in fact do. A run that reported these as passing would be claiming a
property of the wrong transport.

Their server-side half stays in `tests/integration/mcp/test_negative_reachability.py`, which
skips with a reason and never passes when no key is present. Under Branch B those assertions
are **unrun**, not green, and the submission says "unrun" — see
[`../DEMO-HONESTY.md`](../DEMO-HONESTY.md) §4.

### B3 · A recorded session, labelled as a recording

The film's beat 5 becomes a recorded Managed-MCP session against `mainline-verify`, captured
before submission, with the round trips written to `evidence/demo-run-<ts>/mcp/` and hashed
into the custody ledger. A recording is evidence that a session occurred; it is not
something a stranger can re-run, and the on-screen label says which of the two it is.

Alongside it, our own read-only aggregate endpoints serve the same `mainline_audit` views
over HTTP. That path has our code in it, which is the whole difference, and the honesty card
prints the difference rather than the claim.

## What changes in each artefact, and who changes it

| Artefact | Under Branch B |
|---|---|
| `PACK.md` | unchanged — the questions are the questions. `run --via sql` is the invocation |
| `demo/VERIFY.md` | its Tier-3 section states the degrade; that file's owner makes the edit, not this pack |
| `demo/honesty/card.html` | generated; the MCP row reads "recorded session" because the attestation says so |
| `tests/integration/mcp/` | skips with a reason. Skipped is reported as skipped, never as passed |
| the submission text | says "over our own read-only endpoints plus a recorded managed session", never "over CockroachDB's endpoint" |

## The trigger, and who pulls it

The branch is chosen by the **G1 ground-truth attestation's GT-17 entry**, not by a
judgement call on the day. When that entry records that key publication is outside terms,
Branch B is in force from that moment and the artefacts above are updated in the same
change. An unanswered GT-17 counts as a failed one: the fallback executes and the question
becomes a standing nightly assertion the same day.

## What is never claimed under either branch

- That a run of this pack proves the retrieval was exhaustive. It is exhaustive over the
  retrieval that ran, and the difference is the whole honesty of the mechanism.
- That an approximate-nearest-neighbour result replays bit for bit. What is claimed is
  replayability of the arithmetic and of the disclosed boundary.
- That the audit views are site-scoped by the MCP identity. Which SQL identity the managed
  endpoint runs as is day-1 check GT-10; the pessimistic answer is assumed, the views are
  built to be safe when read in full, and MCP is never marketed as site-scoped.
- That the cluster is in Australia. The database is in Singapore and Bedrock inference is in
  Sydney. Any claim of end-to-end Australian data residency is false for this deployment and
  appears nowhere.
