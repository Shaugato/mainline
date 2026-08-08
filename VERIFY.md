<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# VERIFY — how a stranger checks this without trusting us

MAINLINE's claim is a **refusal**: the database will not merge a permit-to-work while a
recalled precursor carries no signed disposition. A refusal you cannot reproduce is a
slogan. This document is the set of ways to reproduce it, ordered by how much you have to
take on faith — which is, in every case, less than you would expect.

**Lead with Tier 2. It needs nothing from anyone.**

---

## The three tiers

| Tier | Credential | What it proves | Time |
|---|---|---|---|
| **1** | **none** | `pipx run trappoint-verify --bundle <bundle>` — offline verification of the checkpoint chain, the inclusion and consistency proofs, the timestamp bracket, and the gate's own trigger source inside the attestation. The exhibited refusal is in the ledger, and the signature on the exhibited disposition verifies against the enrolled key. | ~30 s |
| **2** | **none** | `git clone && just up && just migrate && just conform` — Docker CockroachDB, migrations, seed from committed fixtures *including embeddings*, then the conformance corpus replays the illegal histories and prints the same SQLSTATEs. **The merge refusal reproduces on a stranger's laptop with no cloud account and no model call.** | ~4 min |
| **3** | a published, scoped MCP key on a throwaway `mainline-verify` cluster | The audit surface, the vector-index proof and the silence ledger, read over **CockroachDB's own public managed endpoint — with none of our code in the path**. | ~2 min |

Tier 1 and Tier 2 are the ones that matter. Tier 3 is the one that is *fun*, because you
run it with your own agent against a Cockroach Labs endpoint we do not operate, and
nothing between your prompt and the row is ours.

---

## Tier 3 — pointing your own agent at the cluster

**Endpoint.** `https://cockroachlabs.cloud/mcp`, MCP Streamable HTTP.
**Auth.** `Authorization: Bearer <service-account key>`.
**Cluster pin.** The `mcp-cluster-id` header pins exactly one cluster; a tool call passing
a different `cluster_id` fails.

Point any MCP client at it. Ours (`packages/mainline-mcp`) exists to make the limits
diagnosable, not to be required:

```bash
export MAINLINE_MCP_API_KEY=...        # the scoped key published for judging
export MAINLINE_MCP_CLUSTER_ID=...     # the mainline-verify cluster
uv run pytest tests/integration/mcp -rs
```

With no key those suites **skip with a reason and never pass**, which is deliberate: a
green audit-surface run with nothing to talk to would assert nothing, and a green
*negative* run with nothing to talk to would assert the opposite of what it claims.

### The questions worth asking

Every audit question routes through a purpose-built `mainline_audit` view, aggregate-first,
shaped to ≤ 25 rows and measured under 8 KiB. The MCP response cap is 10 KiB and the server
**truncates rather than raising**, so the size of these views is a functional requirement
rather than an operational detail.

| Ask | View |
|---|---|
| Which weakenings of blood-written controls have no disposition? | `mainline_audit.v_weakenings_without_disposition` |
| What did you decline to surface, and with what arithmetic? | `mainline_audit.v_silence_summary` |
| Is the ledger healthy? | `mainline_audit.v_ledger_health` |
| What has the agent fleet been doing? | `mainline_audit.v_agent_actions` |
| What is blocking merges right now, and where? | `mainline_audit.v_open_gate_summary` |
| How complete is the blame ancestry, and where is it truncated? | `mainline_audit.v_blame_coverage` |
| Are dispositions keeping up with what was surfaced? | `mainline_audit.v_disposition_coverage` |
| How much of the recall was conserved, and did any arm degrade? | `mainline_audit.v_recall_conservation` |
| Is fixity being checked, and what was never checked at all? | `mainline_audit.v_fixity_coverage` |

Two of those views carry `ancestry_complete`. When it is false, the counts beneath it are
**lower bounds** — the ancestry walk was truncated and the view says so rather than
rounding the problem away.

### The negatives are the interesting part

A positive assertion beside no negative one is a claim, not a test. Try these; they must
all **fail**:

```sql
SELECT count(*) FROM mainline_qa.v_disposition_profile;   -- must fail, on every tier, forever
SELECT count(*) FROM crdb_internal.jobs;                  -- must fail
SELECT count(*) FROM pg_catalog.pg_class;                 -- must fail
SELECT count(*) FROM information_schema.tables;           -- must fail
```

…and an `insert_rows` into anything other than `mainline_meas.external_attestation` must be
rejected. `tests/integration/mcp/test_negative_reachability.py` asserts every one of those
over the live endpoint, deliberately bypassing our own client-side screen — because a
control that lives only in our client is a control an attacker skips by not using our
client.

That `crdb_internal` is unreachable is not an inconvenience we worked around. It is what
proves the `mainline_audit` views **are** the API rather than a bypass around one.

### The one thing you may write

`insert_rows` into `mainline_meas.external_attestation`, and nothing else. It is there so
your agent can record the outcome of *its own* verification into our log — a third party's
claim about our log, never our claim about the world. The insert-only write surface is an
exact match for append-only archival memory, which is why it is the only write surface
there is.

---

## The scoped-key policy

1. **A key is published only on the throwaway `mainline-verify` cluster**, restored
   nightly, carrying **synthetic data only**.
2. **No key is ever published on the demo cluster.** The write surface is insert-only, but
   it is real.
3. The published key is **revoked when judging closes**.
4. Whether publishing a service-account key to anonymous verifiers is within Cockroach
   Labs' terms is day-1 check `GT-17`. **If the answer is no, Tier 3 degrades to a recorded
   MCP session plus our own read-only aggregate endpoints, and this document says so on the
   day rather than quietly dropping the tier.**

---

## What we assume about the MCP identity — pessimistically, and out loud

> The Managed MCP identity is assumed **admin-equivalent** and RLS is assumed **not** to
> apply. `mainline_audit` views are therefore designed to be safe if read in full,
> `mainline_qa` never receives an account, and **we never market MCP as site-scoped.**

Which SQL identity `select_query` runs as is undocumented. Rather than guess favourably, we
built for the worst answer: every view on the MCP surface is aggregate-first and safe to
read in its entirety, and the schema that holds per-named-person deliberation measurement
(`mainline_qa`) has no MCP service account on any tier, ever. If day-1 check `GT-10` shows
the identity is a non-admin role, v26.2's `security_invoker` view option is the upside
lever — an improvement we would then be able to claim, not one we are claiming now.

---

## Where this runs, precisely

- **Database:** CockroachDB v26.2 (Basic tier), `aws-ap-southeast-1` — **Singapore**.
- **Inference:** Amazon Bedrock, `ap-southeast-2` — **Sydney**.

Sydney is Advanced-tier only for CockroachDB Cloud, so it is absent from the Basic region
list. **Any claim of end-to-end Australian data residency is false for this deployment.**
The split is stated here, in the README and in the deck, and nowhere is it rounded off.

---

## What none of this proves

- Not that a disposition was **sincere**. Non-repudiation is cryptographic, not moral.
- Not that the narrative in an ingested PDF is **true**. *Content authenticity is out of
  scope; provenance is in scope* — who submitted it, when, its hash, its Object Lock
  version.
- Not that the ANN search was exhaustive over the **corpus** — only over the retrieval that
  ran.
- Not anything about state at a past time via `AS OF SYSTEM TIME`. The measured
  `gc.ttlseconds` on this cluster is **4 500 s (75 minutes)**; long-horizon versioning is
  the application-level commit DAG, and a query past the window is **refused**, not
  silently wrong.
- Not split-view resistance until a genuinely adverse witness is live.
- Not that a Steward finding is **true**. *An LLM ops report is evidence that a review
  occurred, not evidence of a condition* — which is why every finding carries the SQL it
  ran and the sha256 of its result rows, so you can re-run it yourself.

---

## If something here does not reproduce

That is a defect and we would like to know. The suites that back this document are:

- `tests/integration/mcp/test_audit_surface.py` — every contracted view measured, with the
  bytes, the rows and the worst observed row printed.
- `tests/integration/mcp/test_negative_reachability.py` — every negative above, asserted
  against the live endpoint.
- `packages/mainline-mcp/tests/` — the same logic offline, including the transport itself,
  on a machine with no credential at all.
