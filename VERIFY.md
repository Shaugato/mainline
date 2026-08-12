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

**Every command on this page was executed on 2026-08-12, against the tree at the head of
`master`, and this revision records what each one actually printed.** Two of them do not do what earlier
revisions of this page said they did, and the corrections are in the tiers below rather
than in a footnote. `just`, `uv` and `pipx` are **not installed** on the machine these
measurements were taken on, so every command is given in a form that runs without them; the
`just` recipe is shown beside it because both are first-class.

---

## The three tiers

| Tier | Credential | What it proves | Measured |
|---|---|---|---|
| **1** | **none** | `trappoint-verify verify --bundle evidence/reference-ledger/bundle.json` — offline verification of the Merkle structure: leaf recomputation, inclusion, consistency across every consecutive checkpoint pair, link-chain density from a zero genesis, receipt coverage, bundle totality. **It exits 1 and it is meant to.** | **0.5 s, exit 1** |
| **2** | **none** | `git clone`, bring up Docker CockroachDB, `python scripts/proof/gate_refusal.py` — applies the whole migration chain into a throwaway database and attempts the merge three times. **The merge refusal reproduces on a stranger's laptop with no cloud account and no model call.** | **106 s, exit 0, `VERDICT PROVEN`** |
| **3** | a published, scoped MCP key on a throwaway `mainline-verify` cluster | The audit surface, the vector-index proof and the silence ledger, read over **CockroachDB's own public managed endpoint — with none of our code in the path**. | **not run here** — no key was held |

Tier 1 and Tier 2 are the ones that matter. Tier 3 is the one that is *fun*, because you
run it with your own agent against a Cockroach Labs endpoint we do not operate, and
nothing between your prompt and the row is ours.

---

## Tier 1 — the offline bundle, and the number it actually returns

```bash
python -m pip install -e packages/trappoint-verify      # or: pipx run trappoint-verify
trappoint-verify verify --bundle evidence/reference-ledger/bundle.json
```

Measured 2026-08-12:

```
16 checks | 8 passed | 1 failed | 7 not checked
exit 1: 1 finding(s). This bundle does not verify.
```

**Read that last line before anything else on this page.** Earlier revisions of this table
described Tier 1 as proving "the timestamp bracket, and the gate's own trigger source inside
the attestation", and as taking about thirty seconds. **All three clauses were wrong.** It
takes half a second, the timestamp bracket and the gate self-attestation are two of the
**seven checks that do not run at all**, and the tool exits non-zero.

| | |
|---|---|
| **8 PASSED** | leaf recomputation, inclusion, consistency across every consecutive checkpoint pair, link-chain density from a 32-zero-byte genesis, no sandbox leaf, closure-generation monotonicity, receipt coverage, bundle totality |
| **1 FAILED** | `canonicaliser_identity` — the bundle's signed `canon_src_sha256` is `260ed37d…`; the canonicaliser this verifier runs hashes to `d09036a8…`, so eight checkpoints' signed `canon:` lines disagree with the code that would recompute them. **This is real drift and the check is catching it**, which is the whole reason a bundle carries the hash of its own canonicaliser |
| **7 NOT CHECKED** | log signature, RFC-3161 timestamp bracket, beacon, witness quorum, S3 object-lock, gate self-attestation, WebAuthn re-verification — the cryptographic half. Each is registered, names its owner, and prints what it *would* have proved |

**Eight passes are not a verified ledger, and the tool refuses to let you round them up into
one.** What Tier 1 genuinely proves is that the Merkle structure is internally consistent
and that the exhibited refusal is in it. What it does not yet prove is that anybody signed
it. `docs/CI-STATE.md` §3.1 is the standing record, and `custody-chain` is red for exactly
this.

---

## Tier 2 — the refusal, on your laptop, in four commands

| The recipe | The same thing, plain |
|---|---|
| `just doctor` | `python scripts/qa/doctor.py` |
| `just setup` | `python -m pip install -e packages/trappoint-migrate` |
| `just up` | `docker compose -f compose.yaml up -d --wait` then `docker compose -f compose.yaml run --rm crdb-align` |
| `just prove` | `python scripts/proof/gate_refusal.py --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"` |

Measured 2026-08-12, from a `python -m venv` created for the purpose that had never seen
this workspace:

```
chain         271/271 applied, 0 failed, 55.611s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1 —
              outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
```

Exit 0, 106.2 seconds end to end. The script writes its own evidence file under
`evidence/gate-refusal/` and the earlier runs are kept beside it on purpose.

### The correction: `just migrate && just conform` is not the Tier 2 command

**Earlier revisions of this page gave Tier 2 as `git clone && just up && just migrate &&
just conform`. Run today, that sequence does not reach a refusal.** `just migrate` applies
the **reference vertical**, and the reference vertical is missing two producers:

```
$ trappoint migrate up --dsn <local> --tree trappoint-ref \
    --migrations packages/trappoint-sql/refvertical/sql ; echo $?
trappoint migrate: REFUSED: 0058_blocking_check:
  [42P01] relation "trappoint_ref.event" does not exist
1

$ trappoint-conform --dsn <local> --profile trappoint-ref ; echo $?
0/45 · spec 1.0.0-rc.1 · profile trappoint-ref · failed 6 · cannot_run 38 · error 1
1
```

Every one of those 44 non-passes names the object it wanted — `trappoint_ref.blocking_check`
or `trappoint_ref.permit_event` — which is the suite correctly refusing to call an unbuilt
world a refusal rather than reporting a green on nothing. **The `schema` workflow is red for
this, by name, with the owner on it** (KERNEL domain): `trappoint_ref.clause` and
`trappoint_ref.event` are referenced by `0058_blocking_check` and `0066_disposition` and
created by no file in `packages/trappoint-sql/refvertical/sql`.

So the conformance corpus **cannot** currently replay the illegal histories against the
reference vertical, and this page will not tell you it can. What reproduces the central
claim is the MAINLINE chain, which is what `just prove` runs and what the block above shows.
`just conform-mainline` runs the same suite against MAINLINE and resolves each case's
`requires` token against the live catalogue; `qa/conformance-census.json` is the committed
run of it, and it records 10 passed of 71 declared cases. That census is in
`docs/HONESTY.md` under NOT YET BUILT, where a modest first result belongs.

---

## Tier 3 — pointing your own agent at the cluster

**Not run for this revision.** No scoped key was held by the worker that re-measured this
page, so everything in this section is design and prior record, not a reading taken today.
The one thing that *was* checked is that it degrades honestly: with no key the suites skip
with a reason and never pass.

**Endpoint.** `https://cockroachlabs.cloud/mcp`, MCP Streamable HTTP.
**Auth.** `Authorization: Bearer <service-account key>`.
**Cluster pin.** The `mcp-cluster-id` header pins exactly one cluster; a tool call passing
a different `cluster_id` fails.

Point any MCP client at it. Ours (`packages/mainline-mcp`) exists to make the limits
diagnosable, not to be required:

```bash
export MAINLINE_MCP_API_KEY=...        # the scoped key published for judging
export MAINLINE_MCP_CLUSTER_ID=...     # the mainline-verify cluster
python -m pytest tests/integration/mcp -rs      # or: uv run pytest tests/integration/mcp -rs
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
- **Not that the reference ledger is signed.** Tier 1 verifies its Merkle structure and
  exits `1`; seven cryptographic checks are unimplemented and one has gone red on real
  canonicaliser drift.
- **Not that any AWS service other than Bedrock has run.** `evidence/deploy/aws-live.json`
  records four Bedrock-plane calls with AWS request ids and `calls_failed: []`. Lambda,
  CloudFront, S3, KMS, IAM roles and SSM are designed and unapplied — `terraform apply` has
  never been run — which is also why there is no demo URL to point you at.

---

## If something here does not reproduce

That is a defect and we would like to know. **The repository is public — open an issue and
quote the command and its output.** The suites that back this document are:

- `tests/integration/mcp/test_audit_surface.py` — every contracted view measured, with the
  bytes, the rows and the worst observed row printed.
- `tests/integration/mcp/test_negative_reachability.py` — every negative above, asserted
  against the live endpoint.
- `packages/mainline-mcp/tests/` — the same logic offline, including the transport itself,
  on a machine with no credential at all.

### What was executed for this revision, and what was not

| command | exit | note |
|---|---|---|
| `python scripts/qa/doctor.py` | 1 | on `uv` and `just` only; both remedies printed; does not block the proof |
| `docker compose -f compose.yaml config` | 0 | 0.9 s |
| `python -m pip install -e packages/trappoint-migrate` | 0 | into a fresh venv, 19.7 s, six packages |
| `python scripts/proof/gate_refusal.py --dsn …` | 0 | 106.2 s, `VERDICT PROVEN` |
| `python -m pytest --crdb=none --collect-only -q` | 0 | 9 324 tests, 0 errors, 13.7 s |
| `trappoint-verify verify --bundle …` | **1** | `8 passed, 1 failed, 7 not checked` — Tier 1 |
| `trappoint migrate up --tree trappoint-ref …` | **1** | `REFUSED: 0058_blocking_check [42P01]` |
| `trappoint-conform --profile trappoint-ref` | **1** | `0/45 · failed 6 · cannot_run 38 · error 1` |
| `pytest tests/integration/mcp` | — | **not run**; no scoped key was held. Tier 3 |

`just`, `uv` and `pipx` are absent from this machine, which is why every row above is the
plain form. That is not a workaround: `justfile`'s own header records that four recipes may
not mention `uv` precisely because a stranger's first command must not answer
`uv: command not found`.
